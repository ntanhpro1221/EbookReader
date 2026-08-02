from __future__ import annotations

from pathlib import Path

from ebook_reader.character_registry import build_registry_and_cast
from ebook_reader.config import build_settings
from ebook_reader.database import ProjectDB
from ebook_reader.voice_catalog import (
    REGION_CENTRAL,
    REGION_NORTH,
    REGION_SOUTH,
    STYLE_NEWS,
    preset_by_name,
)


def _casting_db(tmp_path: Path) -> ProjectDB:
    db = ProjectDB(tmp_path / "project.sqlite3")
    db.initialize_book(
        title="Book",
        project_root=tmp_path,
        settings={},
        settings_hash="settings",
        input_manifest_hash="manifest",
    )
    chapter_id = db.ensure_chapters(
        [
            {
                "chapter_index": 1,
                "title": "One",
                "input_path": tmp_path / "one.txt",
                "input_sha256": "source",
                "input_size": 1,
                "output_mp3": tmp_path / "one.mp3",
            }
        ]
    )[0]
    speakers = [("NARRATOR", "unknown")]
    speakers.extend((f"Nam {index}", "male") for index in range(1, 7))
    speakers.extend((f"Nữ {index}", "female") for index in range(1, 8))
    speakers.extend(
        [
            ("NPC_LOCAL::c00001::b0001::áo xanh", "male"),
            ("NPC_LOCAL::c00001::b0001::áo đỏ", "male"),
            ("NPC_LOCAL::c00001::b0001::áo vàng", "male"),
            ("NPC_LOCAL::c00001::b0001::áo tím", "male"),
            ("UNKNOWN", "male"),
            ("UNKNOWN", "female"),
        ]
    )
    rows = []
    for seq, (speaker, gender) in enumerate(speakers):
        rows.append(
            {
                "stable_id": f"c1s{seq}",
                "seq": seq,
                "text": f"Câu thoại thử nghiệm số {seq}.",
                "text_sha256": f"text{seq}",
                "kind_hint": "narration" if speaker == "NARRATOR" else "dialogue",
                "kind": "narration" if speaker == "NARRATOR" else "dialogue",
                "speaker": speaker,
                "gender": gender,
                "confidence": 0.95,
                "status": "analyzed",
            }
        )
    db.replace_chapter_segments(chapter_id, rows)
    return db


def test_casting_prioritizes_standard_voices_reuses_with_pitch_and_limits_regional_to_npcs(
    tmp_path: Path,
) -> None:
    db = _casting_db(tmp_path)

    build_registry_and_cast(db, build_settings(), {}, lambda _message: None)

    profiles = db.list_voice_profiles()
    assert all(preset_by_name(str(profile["preset_name"]))["style"] != STYLE_NEWS for profile in profiles)
    assert all(abs(int(profile["pitch_semitones"])) <= 2 for profile in profiles)
    rows = db.list_segments()
    local_rows = [row for row in rows if str(row["speaker"]).startswith("NPC_LOCAL::")]
    assert len({int(row["canonical_character_id"]) for row in local_rows}) == 4
    assert len({int(row["voice_profile_id"]) for row in local_rows}) == 4

    profile_by_id = {int(profile["id"]): profile for profile in profiles}
    named_rows = [
        row for row in rows
        if str(row["speaker"]) not in {"NARRATOR", "UNKNOWN"}
        and not str(row["speaker"]).startswith("NPC_LOCAL::")
    ]
    named_presets = [
        preset_by_name(str(profile_by_id[int(row["voice_profile_id"])]["preset_name"]))
        for row in named_rows
    ]
    assert {preset["region"] for preset in named_presets} <= {REGION_NORTH, REGION_SOUTH}

    local_presets = [
        preset_by_name(str(profile_by_id[int(row["voice_profile_id"])]["preset_name"]))
        for row in local_rows
    ]
    assert any(preset["region"] == REGION_CENTRAL for preset in local_presets)
    assert any(preset["region"] != REGION_CENTRAL for preset in local_presets)

    named_male_profiles = [
        profile_by_id[int(row["voice_profile_id"])]
        for row in named_rows
        if str(row["gender"]) == "male"
    ]
    pitches_by_preset: dict[str, set[int]] = {}
    for profile in named_male_profiles:
        pitches_by_preset.setdefault(str(profile["preset_name"]), set()).add(
            int(profile["pitch_semitones"])
        )
    assert any(len(pitches) > 1 for pitches in pitches_by_preset.values())

    anonymous = [row for row in rows if str(row["speaker"]) == "UNKNOWN"]
    assert len({int(row["canonical_character_id"]) for row in anonymous}) == 2
    assert {
        preset_by_name(str(profile_by_id[int(row["voice_profile_id"])]["preset_name"]))["gender"]
        for row in anonymous
    } == {"male", "female"}
