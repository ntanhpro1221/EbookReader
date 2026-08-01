from __future__ import annotations

from pathlib import Path

from e_book_reader.character_registry import VIENEU_PRESETS, build_registry_and_cast
from e_book_reader.config import build_settings
from e_book_reader.database import ProjectDB


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


def test_casting_uses_full_vieneu_catalog_before_reusing_and_separates_local_npcs(
    tmp_path: Path,
) -> None:
    db = _casting_db(tmp_path)

    build_registry_and_cast(db, build_settings(), {}, lambda _message: None)

    profiles = db.list_voice_profiles()
    assert len(profiles) == len(VIENEU_PRESETS)
    assert {str(profile["preset_name"]) for profile in profiles} == {
        preset["name"] for preset in VIENEU_PRESETS
    }
    rows = db.list_segments()
    local_rows = [row for row in rows if str(row["speaker"]).startswith("NPC_LOCAL::")]
    assert len({int(row["canonical_character_id"]) for row in local_rows}) == 2
    assert len({int(row["voice_profile_id"]) for row in local_rows}) == 2

    anonymous = [row for row in rows if str(row["speaker"]) == "UNKNOWN"]
    assert len({int(row["canonical_character_id"]) for row in anonymous}) == 2
    profile_by_id = {int(profile["id"]): str(profile["preset_name"]) for profile in profiles}
    gender_by_preset = {preset["name"]: preset["gender"] for preset in VIENEU_PRESETS}
    assert {
        gender_by_preset[profile_by_id[int(row["voice_profile_id"])]] for row in anonymous
    } == {"male", "female"}
