from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any, Callable

from .analysis import is_local_speaker, local_speaker_display
from .database import ProjectDB
from .io_utils import slugify, stable_int


PRONOUNS = {
    "hắn", "nàng", "cô ấy", "anh ấy", "ông ấy", "bà ấy", "người đó", "kẻ đó",
    "ta", "tôi", "mình", "chúng ta", "bọn họ",
}
RESERVED_SPEAKERS = {"narrator": "NARRATOR", "unknown": "UNKNOWN"}

VIENEU_PRESETS: tuple[dict[str, str], ...] = (
    {"name": "Phạm Tuyên", "gender": "male", "style": "tu_nhien", "description": "Nam · Bắc · Tự nhiên"},
    {"name": "Thái Sơn", "gender": "male", "style": "doc_truyen", "description": "Nam · Nam · Kể chuyện"},
    {"name": "Thanh Bình", "gender": "male", "style": "doc_truyen", "description": "Nam · Bắc · Kể chuyện"},
    {"name": "Xuân Vĩnh", "gender": "male", "style": "tu_nhien", "description": "Nam · Nam · Tự nhiên"},
    {"name": "Quang Sơn", "gender": "male", "style": "tu_nhien", "description": "Nam · Trung · Tự nhiên"},
    {"name": "Minh Đức", "gender": "male", "style": "tin_tuc", "description": "Nam · Bắc · Tin tức"},
    {"name": "Minh Triết", "gender": "male", "style": "tin_tuc", "description": "Nam · Nam · Tin tức"},
    {"name": "Ngọc Linh", "gender": "female", "style": "doc_truyen", "description": "Nữ · Bắc · Kể chuyện"},
    {"name": "Thục Đoan", "gender": "female", "style": "doc_truyen", "description": "Nữ · Nam · Kể chuyện"},
    {"name": "Trúc Ly", "gender": "female", "style": "tu_nhien", "description": "Nữ · Bắc · Tự nhiên"},
    {"name": "Đoan Trang", "gender": "female", "style": "tu_nhien", "description": "Nữ · Bắc · Tự nhiên"},
    {"name": "Ngọc Trân", "gender": "female", "style": "tu_nhien", "description": "Nữ · Trung · Tự nhiên"},
    {"name": "Mai Anh", "gender": "female", "style": "tin_tuc", "description": "Nữ · Bắc · Tin tức"},
    {"name": "Thùy Dung", "gender": "female", "style": "tin_tuc", "description": "Nữ · Nam · Tin tức"},
)


def normalize_name(name: str) -> str:
    return " ".join(name.strip().casefold().split())


def canonical_key(name: str) -> str:
    return normalize_name(name).upper()


def _majority(rows: list[Any], column: str, default: str = "unknown") -> str:
    counts = Counter(
        str(row[column])
        for row in rows
        if str(row[column]) not in {"", "unknown"}
    )
    if not counts:
        return default
    ranked = counts.most_common()
    if len(ranked) > 1 and ranked[0][1] == ranked[1][1]:
        return default
    return ranked[0][0]


def _preset_by_name(name: str) -> dict[str, str]:
    for preset in VIENEU_PRESETS:
        if preset["name"] == name:
            return preset
    raise ValueError(f"VieNeu narrator preset is not in the locked catalog: {name!r}")


class PresetAllocator:
    def __init__(self, narrator_voice: str) -> None:
        self.candidates = [preset for preset in VIENEU_PRESETS if preset["name"] != narrator_voice]
        self.usage: Counter[str] = Counter()

    def choose(self, gender: str) -> dict[str, str]:
        matching = [preset for preset in self.candidates if preset["gender"] == gender]
        candidates = matching or self.candidates
        minimum_usage = min(self.usage[preset["name"]] for preset in candidates)
        selected = next(
            preset for preset in candidates if self.usage[preset["name"]] == minimum_usage
        )
        self.usage[selected["name"]] += 1
        return selected


def _profile_for_preset(
    db: ProjectDB,
    preset: dict[str, str],
    cache: dict[str, int],
) -> int:
    name = preset["name"]
    if name not in cache:
        cache[name] = db.upsert_voice_profile(
            {
                "voice_key": f"preset_{slugify(name)}",
                "engine": "vieneu",
                "preset_name": name,
                "description": preset["description"],
                "seed": stable_int(f"voice::vieneu::{name}"),
                "status": "ready",
            }
        )
    return cache[name]


def _personality(rows: list[Any]) -> str:
    return next((str(row["analysis_notes"]) for row in rows if row["analysis_notes"]), "")[:300]


def build_registry_and_cast(
    db: ProjectDB,
    settings: dict[str, Any],
    alias_map: dict[str, str],
    log: Callable[[str], None],
) -> None:
    for alias, canonical in alias_map.items():
        rewritten = db.rewrite_speaker(alias, canonical)
        if rewritten:
            log(f"Hợp nhất bí danh: {alias} → {canonical} ({rewritten} segment).")

    for speaker in {str(row["speaker"]) for row in db.list_segments()}:
        reserved = RESERVED_SPEAKERS.get(speaker.casefold())
        if reserved and speaker != reserved:
            db.rewrite_speaker(speaker, reserved)

    rows = [row for row in db.list_segments() if str(row["status"]) != "pending"]
    by_speaker: dict[str, list[Any]] = defaultdict(list)
    anonymous_by_gender: dict[str, list[Any]] = defaultdict(list)
    for row in rows:
        speaker = str(row["speaker"])
        normalized = normalize_name(speaker)
        if speaker.casefold() == "unknown" or normalized in PRONOUNS:
            gender = str(row["gender"])
            anonymous_by_gender[gender if gender in {"male", "female"} else "unknown"].append(row)
        else:
            by_speaker[speaker].append(row)

    voice_cfg = settings["voices"]
    narrator_voice = str(voice_cfg["narrator_voice"])
    narrator_preset = _preset_by_name(narrator_voice)
    allocator = PresetAllocator(narrator_voice)
    profile_cache: dict[str, int] = {}

    narrator_rows = by_speaker.pop("NARRATOR", [])
    narrator_character_id = db.upsert_character(
        canonical_name="NARRATOR",
        display_name="Người kể",
        gender=narrator_preset["gender"],
        age="unknown",
        personality="professional audiobook narrator",
        mentions=len(narrator_rows),
        importance="narrator",
        confidence=1.0,
    )
    narrator_profile = db.upsert_voice_profile(
        {
            "voice_key": "narrator",
            "engine": "vieneu",
            "preset_name": narrator_voice,
            "description": str(voice_cfg["narrator_description"]),
            "seed": stable_int("voice::narrator"),
            "status": "ready",
        }
    )
    profile_cache[narrator_voice] = narrator_profile
    db.set_character_for_speaker("NARRATOR", narrator_character_id)
    db.set_voice_for_character_segments(narrator_character_id, narrator_profile)

    minimum_main_mentions = int(voice_cfg["minimum_named_character_mentions"])
    speaker_groups = sorted(
        by_speaker.items(),
        key=lambda item: (-len(item[1]), item[0].casefold()),
    )
    local_count = 0
    for speaker, speaker_rows in speaker_groups:
        gender = _majority(speaker_rows, "gender")
        age = _majority(speaker_rows, "age")
        local = is_local_speaker(speaker)
        display_name = local_speaker_display(speaker) if local else speaker
        canonical = canonical_key(speaker if local else display_name)
        confidence = sum(float(row["confidence"]) for row in speaker_rows) / max(1, len(speaker_rows))
        importance = "minor" if local or len(speaker_rows) < minimum_main_mentions else "main"
        character_id = db.upsert_character(
            canonical_name=canonical,
            display_name=display_name,
            gender=gender,
            age=age,
            personality=_personality(speaker_rows),
            mentions=len(speaker_rows),
            importance=importance,
            confidence=confidence,
        )
        db.add_alias(character_id, speaker, normalize_name(speaker), confidence, "analysis")
        db.set_character_for_speaker(speaker, character_id)
        preset = allocator.choose(gender)
        profile_id = _profile_for_preset(db, preset, profile_cache)
        db.set_voice_for_character_segments(character_id, profile_id)
        local_count += int(local)

    anonymous_labels = {
        "male": "NPC vô danh nam",
        "female": "NPC vô danh nữ",
        "unknown": "NPC vô danh chưa rõ giới tính",
    }
    anonymous_count = 0
    for gender in ("male", "female", "unknown"):
        anonymous_rows = anonymous_by_gender.get(gender, [])
        if not anonymous_rows:
            continue
        display_name = anonymous_labels[gender]
        confidence = sum(float(row["confidence"]) for row in anonymous_rows) / len(anonymous_rows)
        character_id = db.upsert_character(
            canonical_name=f"ANONYMOUS_{gender.upper()}",
            display_name=display_name,
            gender=gender,
            age=_majority(anonymous_rows, "age"),
            personality="minor local characters without a stable identity",
            mentions=len(anonymous_rows),
            importance="minor",
            confidence=confidence,
        )
        preset = allocator.choose(gender)
        profile_id = _profile_for_preset(db, preset, profile_cache)
        db.set_character_and_voice_for_segments(
            [int(row["id"]) for row in anonymous_rows],
            character_id,
            profile_id,
        )
        anonymous_count += 1

    used_voices = len(profile_cache)
    log(
        f"Đã khóa voice casting VieNeu: dùng {used_voices}/{len(VIENEU_PRESETS)} preset; "
        f"{local_count} NPC có danh tính cục bộ, {anonymous_count} nhóm NPC generic theo giới tính."
    )
