from __future__ import annotations

from pathlib import Path

from e_book_reader.database import ProjectDB


def test_voice_profile_resume_preserves_committed_reference(tmp_path: Path) -> None:
    db = ProjectDB(tmp_path / "project.sqlite3")
    profile = {
        "voice_key": "char_lan",
        "engine": "voxcpm2",
        "preset_name": None,
        "description": "Giọng nữ trẻ Việt Nam",
        "seed": 1234,
        "status": "planned",
    }
    profile_id = db.upsert_voice_profile(profile)
    reference = tmp_path / "lan.wav"
    reference.write_bytes(b"wav")
    db.update_voice_reference(profile_id, reference_wav=reference, reference_sha256="abc")

    same_id = db.upsert_voice_profile(profile)
    fresh = db.voice_profile(same_id)

    assert same_id == profile_id
    assert fresh["reference_wav"] == str(reference.resolve())
    assert fresh["reference_sha256"] == "abc"
    assert fresh["status"] == "ready"
