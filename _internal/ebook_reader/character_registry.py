from __future__ import annotations

import re
from collections import Counter, defaultdict
from typing import Any, Callable

from .analysis import (
    CONTINUED_DIALOGUE_LOCK_NOTE,
    DIALOGUE_CLOSERS,
    DIALOGUE_OPENERS,
    EXPLICIT_ATTRIBUTION_NOTE,
    _canonical_speaker,
    is_local_speaker,
    local_speaker_display,
    local_speaker_label,
)
from .database import ProjectDB
from .io_utils import slugify, stable_int
from .voice_catalog import (
    STYLE_NEWS,
    VIENEU_PRESETS,
    casting_preset_priority,
    casting_presets,
    preset_by_name,
    pitch_variants_for_preset,
)


LOCAL_SPEAKER_CONTINUITY_MAX_SEGMENT_GAP = 12
LOCAL_ROLE_CONTINUITY_MAX_SEGMENT_GAP = 40
LOCAL_CHILD_LABEL_PREFIXES = (
    "cậu bé",
    "cô bé",
    "đứa bé",
    "đứa trẻ",
    "trẻ em",
    "trẻ nhỏ",
)
LOCAL_LABEL_STOPWORDS = {"mac", "nguoi"}
LOCAL_PERSONALITY_ROLE_FAMILIES = {
    "bishop": "religious_officiant",
    "giam_muc": "religious_officiant",
    "madwoman": "condemned_woman",
    "priest": "religious_officiant",
    "witch": "condemned_woman",
}
CROWD_DIALOGUE_BLOCK_MAX_SEGMENTS = 8
CROWD_ATTRIBUTION_PATTERN = re.compile(
    r"(?:người dân|dân nghèo|dân chúng|đám đông|mọi người).{0,180}"
    r"(?:gào|hét|hô|la|thét|kêu)",
    flags=re.IGNORECASE,
)
CROWD_ANALYSIS_NOTES = "personality=crowd; đã khóa người nói từ lời dẫn tập thể kế tiếp"


PRONOUNS = {
    "hắn", "nàng", "cô ấy", "anh ấy", "ông ấy", "bà ấy", "người đó", "kẻ đó",
    "ta", "tôi", "mình", "chúng ta", "bọn họ",
}
RESERVED_SPEAKERS = {"narrator": "NARRATOR", "unknown": "UNKNOWN"}
HONORIFIC_PREFIX_PATTERN = re.compile(
    r"^(?:anh|chị|cô|dì|chú|bác|ông|bà|ngài|quý cô|quý ông|bá tước|công tước|đức ngài)\s+(.+)$",
    flags=re.IGNORECASE,
)
ASCII_PROPER_NAME_PATTERN = re.compile(
    r"[A-Z][A-Za-z]*(?:[\s'-][A-Z][A-Za-z]*)*"
)

def normalize_name(name: str) -> str:
    return " ".join(name.strip().casefold().split())


def canonical_key(name: str) -> str:
    return normalize_name(name).upper()


def _looks_like_proper_name(value: str) -> bool:
    return ASCII_PROPER_NAME_PATTERN.fullmatch(value.strip()) is not None


def _honorific_target(value: str) -> str | None:
    match = HONORIFIC_PREFIX_PATTERN.fullmatch(" ".join(value.split()))
    if match is None:
        return None
    candidate = match.group(1).strip()
    return candidate if _looks_like_proper_name(candidate) else None


def _canonicalize_named_speakers(
    db: ProjectDB,
    log: Callable[[str], None],
) -> dict[str, set[str]]:
    counts = Counter(str(row["speaker"]) for row in db.list_segments())
    cleaned_counts: Counter[str] = Counter()
    cleaned_by_original: dict[str, str] = {}
    for original, count in counts.items():
        cleaned = _canonical_speaker(original)
        cleaned_by_original[original] = cleaned
        normalized = normalize_name(cleaned)
        if (
            is_local_speaker(cleaned)
            or cleaned.casefold() in RESERVED_SPEAKERS
            or normalized in PRONOUNS
        ):
            continue
        cleaned_counts[cleaned] += count

    representatives: dict[str, str] = {}
    variants_by_key: dict[str, Counter[str]] = defaultdict(Counter)
    for cleaned, count in cleaned_counts.items():
        variants_by_key[normalize_name(cleaned)][cleaned] += count
    for key, variants in variants_by_key.items():
        representatives[key] = min(
            variants,
            key=lambda candidate: (-variants[candidate], candidate.casefold(), candidate),
        )

    aliases_by_target: dict[str, set[str]] = defaultdict(set)
    rewritten_segments = 0
    for original, cleaned in cleaned_by_original.items():
        normalized = normalize_name(cleaned)
        if (
            is_local_speaker(cleaned)
            or cleaned.casefold() in RESERVED_SPEAKERS
            or normalized in PRONOUNS
        ):
            continue
        target_key = normalized
        honorific_target = _honorific_target(cleaned)
        if honorific_target is not None:
            honorific_key = normalize_name(honorific_target)
            if honorific_key in representatives:
                target_key = honorific_key
        target = representatives[target_key]
        aliases_by_target[target].update((original, cleaned))
        if original != target:
            rewritten_segments += db.rewrite_speaker(original, target)

    if rewritten_segments:
        alias_count = sum(
            len(aliases - {target})
            for target, aliases in aliases_by_target.items()
        )
        log(
            f"Đã chuẩn hóa {rewritten_segments} segment thuộc {alias_count} alias nhân vật "
            "rõ ràng trước khi khóa voice."
        )
    return aliases_by_target


def _validate_casting_inputs(rows: list[Any], minimum_named_mentions: int) -> None:
    rows_by_identity: dict[str, list[Any]] = defaultdict(list)
    for row in rows:
        speaker = str(row["speaker"])
        normalized = normalize_name(speaker)
        if speaker.casefold() in RESERVED_SPEAKERS or normalized in PRONOUNS:
            continue
        rows_by_identity[canonical_key(speaker)].append(row)

    gender_conflicts: dict[str, dict[str, int]] = {}
    missing_named_genders: dict[str, int] = {}
    identity_instability: dict[str, dict[str, list[Any]]] = {}
    for identity, identity_rows in rows_by_identity.items():
        gender_counts = Counter(
            str(row["gender"])
            for row in identity_rows
            if str(row["gender"]) in {"male", "female"}
        )
        if len(gender_counts) > 1:
            gender_conflicts[identity] = dict(sorted(gender_counts.items()))
        if (
            len(identity_rows) >= minimum_named_mentions
            and not gender_counts
            and not is_local_speaker(str(identity_rows[0]["speaker"]))
        ):
            missing_named_genders[identity] = len(identity_rows)

        surfaces = sorted({str(row["speaker"]) for row in identity_rows}, key=str.casefold)
        character_ids = sorted(
            {int(row["canonical_character_id"]) for row in identity_rows if row["canonical_character_id"] is not None}
        )
        profile_ids = sorted(
            {int(row["voice_profile_id"]) for row in identity_rows if row["voice_profile_id"] is not None}
        )
        if len(surfaces) > 1 or len(character_ids) > 1 or len(profile_ids) > 1:
            identity_instability[identity] = {
                "speakers": surfaces,
                "character_ids": character_ids,
                "voice_profile_ids": profile_ids,
            }

    issues: list[str] = []
    if gender_conflicts:
        issues.append(f"gender conflicts={gender_conflicts}")
    if missing_named_genders:
        issues.append(f"named speakers missing gender={missing_named_genders}")
    if identity_instability:
        issues.append(f"voice identity instability={identity_instability}")
    if issues:
        raise RuntimeError("Casting input quality gate failed: " + "; ".join(issues))


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
    try:
        return preset_by_name(name)
    except ValueError as exc:
        raise ValueError(f"VieNeu narrator preset is not in the locked catalog: {name!r}") from exc


class PresetAllocator:
    def __init__(self, narrator_voice: str, max_pitch_shift: int) -> None:
        self.narrator_voice = narrator_voice
        self.max_pitch_shift = max(0, int(max_pitch_shift))
        self.pool_usage: dict[str, Counter[str]] = {
            "named": Counter(),
            "npc": Counter(),
        }
        self.variant_usage: Counter[str] = Counter()

    def choose(self, gender: str, *, npc: bool) -> tuple[dict[str, str], int]:
        candidates = [
            preset
            for preset in casting_presets(gender, include_regional=npc)
            if preset["name"] != self.narrator_voice
        ]
        if not candidates:
            candidates = [
                preset
                for preset in VIENEU_PRESETS
                if preset["name"] != self.narrator_voice and preset["style"] != STYLE_NEWS
            ]
        pool = "npc" if npc else "named"
        usage = self.pool_usage[pool]
        selected = min(
            candidates,
            key=lambda preset: (usage[preset["name"]], *casting_preset_priority(preset)),
        )
        usage[selected["name"]] += 1
        variants = pitch_variants_for_preset(selected["name"], self.max_pitch_shift)
        pitch_steps = variants[self.variant_usage[selected["name"]] % len(variants)]
        self.variant_usage[selected["name"]] += 1
        return selected, pitch_steps


def _profile_for_preset(
    db: ProjectDB,
    preset: dict[str, str],
    pitch_steps: int,
    cache: dict[str, int],
) -> int:
    name = preset["name"]
    pitch_key = f"m{abs(pitch_steps)}" if pitch_steps < 0 else f"p{pitch_steps}"
    profile_key = f"{name}::{pitch_key}"
    if profile_key not in cache:
        pitch_description = "cao độ gốc" if pitch_steps == 0 else f"cao độ {pitch_steps:+d} bán âm"
        cache[profile_key] = db.upsert_voice_profile(
            {
                "voice_key": f"preset_{slugify(name)}_{pitch_key}",
                "engine": "vieneu",
                "preset_name": name,
                "description": f"{preset['description']} · {pitch_description}",
                "seed": stable_int(f"voice::vieneu::{name}::{pitch_steps}"),
                "pitch_semitones": pitch_steps,
                "status": "ready",
            }
        )
    return cache[profile_key]


def _personality(rows: list[Any]) -> str:
    return next((str(row["analysis_notes"]) for row in rows if row["analysis_notes"]), "")[:300]


def _merge_local_speakers_with_named_identity(
    db: ProjectDB,
    log: Callable[[str], None],
) -> None:
    rows = list(db.list_segments())
    named_by_chapter_and_label: dict[tuple[int, str], Counter[str]] = defaultdict(Counter)
    for row in rows:
        speaker = str(row["speaker"])
        normalized = normalize_name(speaker)
        if (
            is_local_speaker(speaker)
            or speaker.casefold() in RESERVED_SPEAKERS
            or normalized in PRONOUNS
        ):
            continue
        named_by_chapter_and_label[(int(row["chapter_id"]), normalized)][speaker] += 1

    local_speakers = {
        str(row["speaker"])
        for row in rows
        if is_local_speaker(row["speaker"])
    }
    for local_speaker in sorted(local_speakers, key=str.casefold):
        matching_rows = [row for row in rows if str(row["speaker"]) == local_speaker]
        if not matching_rows:
            continue
        chapter_id = int(matching_rows[0]["chapter_id"])
        label = normalize_name(local_speaker_label(local_speaker))
        candidates = named_by_chapter_and_label.get((chapter_id, label))
        if not candidates:
            continue
        named_speaker = sorted(
            candidates,
            key=lambda candidate: (-candidates[candidate], candidate.casefold()),
        )[0]
        rewritten = db.rewrite_speaker(local_speaker, named_speaker)
        if rewritten:
            log(
                f"Hợp nhất nhân vật cục bộ cùng chapter: "
                f"{local_speaker_display(local_speaker)} → {named_speaker} "
                f"({rewritten} segment)."
            )


def _compatible_local_traits(left: list[Any], right: list[Any], field: str) -> bool:
    left_values = {str(row[field]) for row in left if str(row[field]) != "unknown"}
    right_values = {str(row[field]) for row in right if str(row[field]) != "unknown"}
    return not left_values or not right_values or bool(left_values & right_values)


def _personality_role_family(rows: list[Any]) -> str | None:
    families: set[str] = set()
    for row in rows:
        match = re.match(r"personality=([^;]+)", str(row["analysis_notes"] or ""))
        if match is None:
            continue
        role = slugify(match.group(1))
        family = LOCAL_PERSONALITY_ROLE_FAMILIES.get(role)
        if family is not None:
            families.add(family)
    return next(iter(families)) if len(families) == 1 else None


def _semantic_local_label(label: str) -> str:
    tokens = [
        token
        for token in slugify(label).split("_")
        if token and token not in LOCAL_LABEL_STOPWORDS
    ]
    return "_".join(tokens)


def _local_continuity_family(speaker: str, rows: list[Any]) -> str:
    label = normalize_name(local_speaker_label(speaker))
    if any(
        label == prefix or label.startswith(f"{prefix} ")
        for prefix in LOCAL_CHILD_LABEL_PREFIXES
    ):
        return f"child::{_majority(rows, 'gender')}"
    role_family = _personality_role_family(rows)
    if role_family is not None:
        return f"role::{role_family}"
    return f"label::{_semantic_local_label(label)}"


def _local_speaker_with_label(speaker: str, label: str) -> str | None:
    if not is_local_speaker(speaker):
        return None
    prefix, _separator, _old_label = speaker.rpartition("::")
    return f"{prefix}::{label}" if prefix else None


def _repair_cross_batch_dialogue_continuations(
    db: ProjectDB,
    log: Callable[[str], None],
) -> None:
    rows = sorted(db.list_segments(), key=lambda row: (int(row["chapter_id"]), int(row["seq"])))
    previous: dict[str, Any] | None = None
    repaired = 0
    for row in rows:
        current = {
            "row": row,
            "kind": str(row["kind"]),
            "speaker": str(row["speaker"]),
            "gender": str(row["gender"]),
            "age": str(row["age"]),
            "analysis_notes": str(row["analysis_notes"] or ""),
        }
        if previous is not None:
            previous_row = previous["row"]
            same_chapter = int(previous_row["chapter_id"]) == int(row["chapter_id"])
            adjacent_paragraph = int(row["paragraph_index"]) == int(
                previous_row["paragraph_index"]
            ) + 1
            previous_text = str(previous_row["text"]).rstrip()
            text = str(row["text"]).lstrip()
            continuation = bool(
                same_chapter
                and adjacent_paragraph
                and previous["kind"] == "dialogue"
                and current["kind"] == "dialogue"
                and previous_text
                and text
                and previous_text[-1] not in DIALOGUE_CLOSERS
                and text[0] not in DIALOGUE_OPENERS
            )
            if continuation and current["speaker"] != previous["speaker"]:
                notes = str(previous["analysis_notes"])
                if CONTINUED_DIALOGUE_LOCK_NOTE not in notes:
                    notes = (
                        f"{notes}; {CONTINUED_DIALOGUE_LOCK_NOTE}"
                        if notes
                        else CONTINUED_DIALOGUE_LOCK_NOTE
                    )
                repaired += db.rewrite_segment_speakers(
                    [int(row["id"])],
                    speaker=str(previous["speaker"]),
                    gender=str(previous["gender"]),
                    age=str(previous["age"]),
                    analysis_notes=notes,
                )
                current.update(
                    {
                        "speaker": previous["speaker"],
                        "gender": previous["gender"],
                        "age": previous["age"],
                        "analysis_notes": notes,
                    }
                )
        previous = current
    if repaired:
        log(f"Đã giữ identity xuyên batch cho {repaired} câu thoại nối tiếp.")


def _repair_crowd_dialogue_blocks(
    db: ProjectDB,
    log: Callable[[str], None],
) -> None:
    rows = sorted(db.list_segments(), key=lambda row: (int(row["chapter_id"]), int(row["seq"])))
    repaired = 0
    for index, row in enumerate(rows):
        if str(row["kind"]) != "narration" or CROWD_ATTRIBUTION_PATTERN.search(str(row["text"])) is None:
            continue
        block: list[Any] = []
        cursor = index - 1
        while cursor >= 0 and len(block) < CROWD_DIALOGUE_BLOCK_MAX_SEGMENTS:
            candidate = rows[cursor]
            if int(candidate["chapter_id"]) != int(row["chapter_id"]):
                break
            if str(candidate["kind"]) != "dialogue":
                break
            if EXPLICIT_ATTRIBUTION_NOTE in str(candidate["analysis_notes"] or ""):
                break
            block.append(candidate)
            cursor -= 1
        if not block:
            continue
        by_target: dict[str, list[int]] = defaultdict(list)
        for candidate in block:
            target = _local_speaker_with_label(str(candidate["speaker"]), "người dân")
            if target is not None:
                by_target[target].append(int(candidate["id"]))
        for target, segment_ids in by_target.items():
            repaired += db.rewrite_segment_speakers(
                segment_ids,
                speaker=target,
                gender="unknown",
                age="unknown",
                analysis_notes=CROWD_ANALYSIS_NOTES,
            )
    if repaired:
        log(f"Đã sửa {repaired} câu hô của đám đông từ lời dẫn tập thể kế tiếp.")


def _merge_adjacent_local_speakers(
    db: ProjectDB,
    log: Callable[[str], None],
) -> None:
    rows = list(db.list_segments())
    identities: dict[tuple[int, str], list[Any]] = defaultdict(list)
    for row in rows:
        speaker = str(row["speaker"])
        if not is_local_speaker(speaker):
            continue
        identities[(int(row["chapter_id"]), speaker)].append(row)

    grouped: dict[tuple[int, str], dict[str, list[Any]]] = defaultdict(dict)
    for (chapter_id, speaker), speaker_rows in identities.items():
        family = _local_continuity_family(speaker, speaker_rows)
        grouped[(chapter_id, family)][speaker] = speaker_rows

    for (_chapter_id, family), identities in grouped.items():
        ordered = sorted(
            identities.items(),
            key=lambda item: min(int(row["seq"]) for row in item[1]),
        )
        if len(ordered) < 2:
            continue
        canonical_speaker, canonical_rows = ordered[0]
        canonical_last_seq = max(int(row["seq"]) for row in canonical_rows)
        for speaker, speaker_rows in ordered[1:]:
            first_seq = min(int(row["seq"]) for row in speaker_rows)
            compatible = _compatible_local_traits(
                canonical_rows,
                speaker_rows,
                "gender",
            ) and _compatible_local_traits(canonical_rows, speaker_rows, "age")
            gap = first_seq - canonical_last_seq
            max_gap = (
                LOCAL_ROLE_CONTINUITY_MAX_SEGMENT_GAP
                if family.startswith("role::")
                else LOCAL_SPEAKER_CONTINUITY_MAX_SEGMENT_GAP
            )
            if (
                gap <= 0
                or gap > max_gap
                or not compatible
            ):
                canonical_speaker = speaker
                canonical_rows = speaker_rows
                canonical_last_seq = max(int(row["seq"]) for row in speaker_rows)
                continue
            rewritten = db.rewrite_speaker(speaker, canonical_speaker)
            if rewritten:
                log(
                    "Hợp nhất NPC cục bộ liền cảnh: "
                    f"{local_speaker_display(speaker)} → "
                    f"{local_speaker_display(canonical_speaker)} ({rewritten} segment)."
                )
            canonical_rows = [*canonical_rows, *speaker_rows]
            canonical_last_seq = max(
                canonical_last_seq,
                max(int(row["seq"]) for row in speaker_rows),
            )


def build_registry_and_cast(
    db: ProjectDB,
    settings: dict[str, Any],
    log: Callable[[str], None],
) -> None:
    normalized_thoughts = db.normalize_thought_speakers()
    if normalized_thoughts:
        log(f"Đã chuyển {normalized_thoughts} đoạn nội tâm sang giọng người kể.")

    for speaker in {str(row["speaker"]) for row in db.list_segments()}:
        reserved = RESERVED_SPEAKERS.get(speaker.casefold())
        if reserved and speaker != reserved:
            db.rewrite_speaker(speaker, reserved)

    _repair_cross_batch_dialogue_continuations(db, log)
    _repair_crowd_dialogue_blocks(db, log)
    aliases_by_speaker = _canonicalize_named_speakers(db, log)
    _merge_adjacent_local_speakers(db, log)
    _merge_local_speakers_with_named_identity(db, log)

    rows = [row for row in db.list_segments() if str(row["status"]) != "pending"]
    voice_cfg = settings["voices"]
    minimum_main_mentions = int(voice_cfg["minimum_named_character_mentions"])
    _validate_casting_inputs(rows, minimum_main_mentions)
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

    narrator_voice = str(voice_cfg["narrator_voice"])
    narrator_preset = _preset_by_name(narrator_voice)
    allocator = PresetAllocator(
        narrator_voice,
        int(voice_cfg.get("max_character_pitch_semitones", 2)),
    )
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
            "pitch_semitones": 0,
            "status": "ready",
        }
    )
    profile_cache[f"{narrator_voice}::p0"] = narrator_profile
    db.set_character_for_speaker("NARRATOR", narrator_character_id)
    db.set_voice_for_character_segments(narrator_character_id, narrator_profile)

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
        for alias in sorted(aliases_by_speaker.get(speaker, {speaker}), key=str.casefold):
            db.add_alias(character_id, alias, normalize_name(alias), confidence, "analysis")
        db.set_character_for_speaker(speaker, character_id)
        preset, pitch_steps = allocator.choose(gender, npc=local)
        profile_id = _profile_for_preset(db, preset, pitch_steps, profile_cache)
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
        preset, pitch_steps = allocator.choose(gender, npc=True)
        profile_id = _profile_for_preset(db, preset, pitch_steps, profile_cache)
        db.set_character_and_voice_for_segments(
            [int(row["id"]) for row in anonymous_rows],
            character_id,
            profile_id,
        )
        anonymous_count += 1

    used_voices = len({str(profile["preset_name"]) for profile in db.list_voice_profiles()})
    voice_variants = len(profile_cache)
    profiles_by_speaker: dict[str, set[int]] = defaultdict(set)
    for row in db.list_segments():
        speaker = str(row["speaker"])
        normalized = normalize_name(speaker)
        if speaker == "UNKNOWN" or is_local_speaker(speaker) or normalized in PRONOUNS:
            continue
        profile_id = row["voice_profile_id"]
        if profile_id is None:
            raise RuntimeError(f"Speaker {speaker!r} has no locked voice profile")
        profiles_by_speaker[normalized].add(int(profile_id))
    unstable = {
        speaker: sorted(profile_ids)
        for speaker, profile_ids in profiles_by_speaker.items()
        if len(profile_ids) != 1
    }
    if unstable:
        raise RuntimeError(f"A speaker name resolved to multiple voice profiles: {unstable}")
    log(
        f"Đã khóa voice casting VieNeu: dùng {used_voices}/{len(VIENEU_PRESETS)} preset; "
        f"{voice_variants} biến thể giọng; "
        f"{local_count} NPC có danh tính cục bộ, {anonymous_count} nhóm NPC generic theo giới tính."
    )
