from __future__ import annotations

import re
from collections import Counter, defaultdict
from typing import Any, Callable

from .database import ProjectDB
from .io_utils import slugify, stable_int


PRONOUNS = {
    "hắn", "nàng", "cô ấy", "anh ấy", "ông ấy", "bà ấy", "người đó", "kẻ đó",
    "ta", "tôi", "mình", "chúng ta", "bọn họ",
}
RESERVED_SPEAKERS = {"narrator": "NARRATOR", "unknown": "UNKNOWN"}

VOICE_ARCHETYPES: dict[str, str] = {
    "male_child": "Giọng bé trai Việt Nam trong sáng, rõ chữ, tự nhiên",
    "female_child": "Giọng bé gái Việt Nam trong sáng, rõ chữ, tự nhiên",
    "male_young": "Giọng nam trẻ Việt Nam, sáng, linh hoạt, rõ chữ",
    "female_young": "Giọng nữ trẻ Việt Nam, trong, linh hoạt, giàu cảm xúc",
    "male_adult": "Giọng nam Việt Nam trưởng thành, vững, rõ chữ",
    "female_adult": "Giọng nữ Việt Nam trưởng thành, ấm, rõ chữ",
    "male_elderly": "Giọng nam lớn tuổi Việt Nam, trầm, chậm vừa, rõ chữ",
    "female_elderly": "Giọng nữ lớn tuổi Việt Nam, ấm, chậm vừa, rõ chữ",
    "unknown": "Giọng Việt Nam trung tính, rõ chữ, tự nhiên",
}


def normalize_name(name: str) -> str:
    value = re.sub(r"\s+", " ", name.strip()).casefold()
    return value


def canonical_key(name: str) -> str:
    return normalize_name(name).upper()


def _majority(rows: list[Any], column: str, default: str = "unknown") -> str:
    values = [str(row[column]) for row in rows if str(row[column]) not in {"", "unknown"}]
    return Counter(values).most_common(1)[0][0] if values else default


def _archetype(gender: str, age: str) -> str:
    if gender not in {"male", "female"}:
        return "unknown"
    if age == "child":
        return f"{gender}_child"
    if age in {"teen", "young"}:
        return f"{gender}_young"
    if age == "elderly":
        return f"{gender}_elderly"
    return f"{gender}_adult"


def build_registry_and_cast(
    db: ProjectDB,
    settings: dict[str, Any],
    alias_map: dict[str, str],
    log: Callable[[str], None],
) -> None:
    # Apply only the high-confidence alias map from the full-book reconciliation pass.
    for alias, canonical in alias_map.items():
        rewritten = db.rewrite_speaker(alias, canonical)
        if rewritten:
            log(f"Hợp nhất bí danh: {alias} → {canonical} ({rewritten} segment).")

    for speaker in {str(row["speaker"]) for row in db.list_segments()}:
        reserved = RESERVED_SPEAKERS.get(speaker.casefold())
        if reserved and speaker != reserved:
            db.rewrite_speaker(speaker, reserved)

    # Use the entire book, including already synthesized/verified segments. Restricting this to
    # only currently analyzed rows would change mention counts/personality hints on resume and could
    # destabilize locked voice profiles.
    rows = [row for row in db.list_segments() if str(row["status"]) != "pending"]
    by_speaker: dict[str, list[Any]] = defaultdict(list)
    for row in rows:
        by_speaker[str(row["speaker"])].append(row)

    voice_cfg = settings["voices"]
    max_unique = int(voice_cfg["max_unique_character_voices"])
    min_mentions = int(voice_cfg["minimum_named_character_mentions"])

    named_counts = Counter(
        speaker for speaker, items in by_speaker.items()
        if speaker.casefold() not in RESERVED_SPEAKERS and normalize_name(speaker) not in PRONOUNS
        for _ in items
    )
    ranked = [name for name, count in named_counts.most_common() if count >= min_mentions]
    unique_names = set(ranked[:max_unique])

    # Narrator is locked and uses the stable Vietnamese preset by default.
    narrator_character_id = db.upsert_character(
        canonical_name="NARRATOR",
        display_name="Người kể",
        gender="unknown",
        age="unknown",
        personality="professional audiobook narrator",
        mentions=len(by_speaker.get("NARRATOR", [])),
        importance="narrator",
        confidence=1.0,
    )
    narrator_profile = db.upsert_voice_profile(
        {
            "voice_key": "narrator",
            "engine": str(voice_cfg["narrator_engine"]),
            "preset_name": str(voice_cfg["narrator_voice"]),
            "description": str(voice_cfg["narrator_description"]),
            "seed": stable_int("voice::narrator"),
            "status": "planned",
        }
    )
    db.set_character_for_speaker("NARRATOR", narrator_character_id)
    db.set_voice_for_character_segments(narrator_character_id, narrator_profile)

    generic_profiles: dict[str, int] = {}
    for speaker, speaker_rows in sorted(by_speaker.items(), key=lambda item: item[0].casefold()):
        if speaker.casefold() == "narrator":
            continue
        gender = _majority(speaker_rows, "gender")
        age = _majority(speaker_rows, "age")
        personality = next((str(r["analysis_notes"]) for r in speaker_rows if r["analysis_notes"]), "")[:300]
        confidence = sum(float(r["confidence"]) for r in speaker_rows) / max(1, len(speaker_rows))
        normalized = normalize_name(speaker)
        is_unknown = speaker.casefold() == "unknown" or normalized in PRONOUNS
        display_name = speaker if not is_unknown else f"Nhân vật phụ {gender}/{age}"
        canonical = canonical_key(display_name)
        importance = "main" if speaker in unique_names else "minor"
        character_id = db.upsert_character(
            canonical_name=canonical,
            display_name=display_name,
            gender=gender,
            age=age,
            personality=personality,
            mentions=len(speaker_rows),
            importance=importance,
            confidence=confidence,
        )
        db.add_alias(character_id, speaker, normalize_name(speaker), confidence, "analysis")
        db.set_character_for_speaker(speaker, character_id)

        if speaker in unique_names and not is_unknown:
            voice_key = f"char_{slugify(speaker)}_{stable_int(speaker, 1000, 9999)}"
            description = (
                f"Giọng {gender} Việt Nam, nhóm tuổi {age}, rõ chữ, tự nhiên; "
                f"tính cách gợi ý: {personality or 'phù hợp nhân vật light novel'}"
            )
            profile_id = db.upsert_voice_profile(
                {
                    "voice_key": voice_key,
                    "engine": str(voice_cfg["character_engine"]),
                    "description": description,
                    "seed": stable_int(f"voice::{canonical}"),
                    "status": "planned",
                }
            )
        else:
            archetype = _archetype(gender, age)
            if archetype not in generic_profiles:
                generic_profiles[archetype] = db.upsert_voice_profile(
                    {
                        "voice_key": f"generic_{archetype}",
                        "engine": str(voice_cfg["character_engine"]),
                        "description": VOICE_ARCHETYPES[archetype],
                        "seed": stable_int(f"voice::generic::{archetype}"),
                        "status": "planned",
                    }
                )
            profile_id = generic_profiles[archetype]
        db.set_voice_for_character_segments(character_id, profile_id)

    log(
        f"Đã khóa voice casting toàn book: {len(unique_names)} nhân vật có giọng riêng, "
        f"{len(generic_profiles)} voice pool cho nhân vật phụ."
    )
