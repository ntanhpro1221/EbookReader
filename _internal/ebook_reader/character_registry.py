from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any, Callable

from .analysis import is_local_speaker, local_speaker_display, local_speaker_label
from .database import ProjectDB
from .io_utils import slugify, stable_int
from .voice_catalog import (
    STYLE_NEWS,
    VIENEU_PRESETS,
    casting_presets,
    preset_by_name,
    pitch_variants_for_preset,
    preset_priority,
)


PRONOUNS = {
    "hắn", "nàng", "cô ấy", "anh ấy", "ông ấy", "bà ấy", "người đó", "kẻ đó",
    "ta", "tôi", "mình", "chúng ta", "bọn họ",
}
RESERVED_SPEAKERS = {"narrator": "NARRATOR", "unknown": "UNKNOWN"}

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
            key=lambda preset: (usage[preset["name"]], *preset_priority(preset)),
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

    _merge_local_speakers_with_named_identity(db, log)

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
    log(
        f"Đã khóa voice casting VieNeu: dùng {used_voices}/{len(VIENEU_PRESETS)} preset; "
        f"{voice_variants} biến thể giọng; "
        f"{local_count} NPC có danh tính cục bộ, {anonymous_count} nhóm NPC generic theo giới tính."
    )
