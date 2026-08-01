from __future__ import annotations

from pathlib import Path

import numpy as np

from e_book_reader.audio_io import atomic_write_wav
from e_book_reader.config import build_settings, settings_hash
from e_book_reader.database import ProjectDB
from e_book_reader.models import ProjectPaths
from e_book_reader.recovery import recover_project


def setup_db(tmp_path: Path):
    paths = ProjectPaths.build(tmp_path / "project")
    settings = build_settings(overrides={"tts": {"min_seconds_per_100_chars": 0.5}})
    db = ProjectDB(paths.db)
    db.initialize_book(
        title="T",
        project_root=paths.root,
        settings=settings,
        settings_hash=settings_hash(settings),
        input_manifest_hash="manifest",
    )
    source = tmp_path / "001.txt"
    source.write_text("Xin chào thế giới", encoding="utf-8")
    chapter_id = db.ensure_chapters([
        {
            "chapter_index": 1,
            "title": "001",
            "input_path": source,
            "input_sha256": "hash",
            "input_size": source.stat().st_size,
            "output_mp3": paths.chapters / "001.mp3",
        }
    ])[0]
    db.replace_chapter_segments(chapter_id, [{
        "stable_id": "c1s1",
        "seq": 0,
        "text": "Xin chào thế giới",
        "text_sha256": "text",
        "kind_hint": "narration",
    }])
    return paths, settings, db, db.list_segments(chapter_id=chapter_id)[0]


def test_recovery_preserves_valid_committed_wav_and_removes_part(tmp_path: Path) -> None:
    paths, settings, db, row = setup_db(tmp_path)
    wav = paths.chunks / "c.wav"
    audio = np.sin(np.linspace(0, 30, 48000, dtype=np.float32)) * 0.1
    checksum, metrics = atomic_write_wav(wav, audio, 48000, row["text"], settings)
    db.mark_signal_passed(
        int(row["id"]), wav_path=wav, wav_sha256=checksum,
        duration=metrics["duration"], signal=metrics,
    )
    part = paths.chunks / "orphan.part.wav"
    part.write_bytes(b"partial")
    report = recover_project(paths, db, settings)
    fresh = db.list_segments()[0]
    assert fresh["status"] == "signal_passed"
    assert Path(fresh["wav_path"]).exists()
    assert report.removed_part_files >= 1
    assert not part.exists()


def test_recovery_rebuilds_completed_mp3_when_artifact_checksum_mismatches(tmp_path: Path, monkeypatch) -> None:
    paths, settings, db, row = setup_db(tmp_path)
    chapter = db.list_chapters()[0]
    output = Path(str(chapter["output_mp3"]))
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(b"ID3" + b"x" * 5000)
    db.register_artifact(
        artifact_key=f"chapter_mp3:{chapter['chapter_index']}",
        kind="chapter_mp3",
        path=output,
        sha256="0" * 64,
        verified=True,
    )
    db.update_chapter_status(int(chapter["id"]), "completed")
    monkeypatch.setattr("e_book_reader.recovery.verify_mp3", lambda _path: (True, "ok"))

    report = recover_project(paths, db, settings)

    assert report.invalid_mp3 == 1
    assert db.list_chapters()[0]["status"] == "warning"


def test_recovery_invalidates_corrupt_voice_reference(tmp_path: Path) -> None:
    paths, settings, db, _row = setup_db(tmp_path)
    profile_id = db.upsert_voice_profile({
        "voice_key": "char_test",
        "engine": "voxcpm2",
        "description": "Giọng thử",
        "seed": 123,
    })
    reference = paths.voices / "char_test.wav"
    reference.write_bytes(b"not-a-wave")
    db.update_voice_reference(profile_id, reference_wav=reference, reference_sha256="bad")

    report = recover_project(paths, db, settings)
    fresh = db.voice_profile(profile_id)

    assert report.invalid_voice_references == 1
    assert fresh["reference_wav"] is None
    assert fresh["reference_sha256"] is None
    assert fresh["status"] == "planned"
