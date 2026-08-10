from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path

import pytest

from ebook_reader.database import (
    CHAPTER_POST_ENCODE_QUALITY_STAGE,
    QUALITY_SCOPE_CHAPTER,
    QUALITY_SCOPE_SEGMENT,
    QUALITY_VERDICT_PASS,
    SCHEMA_VERSION,
    SEGMENT_AUDIO_QUALITY_STAGE,
    ProjectDB,
)
from ebook_reader.models import CONTEXTUAL_ENGLISH_NAME_PRONUNCIATION_SOURCE
from ebook_reader.config import build_settings
from ebook_reader.tts import TTSCoordinator


def _segment_db(tmp_path: Path) -> tuple[ProjectDB, int]:
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
    db.replace_chapter_segments(
        chapter_id,
        [
            {
                "stable_id": "c1s1",
                "seq": 0,
                "text": "Text",
                "text_sha256": "text",
                "kind_hint": "narration",
            }
        ],
    )
    return db, int(db.list_segments()[0]["id"])


def test_warning_codes_are_merged_without_duplicates(tmp_path: Path) -> None:
    db, segment_id = _segment_db(tmp_path)

    db.set_segment_warning_code(segment_id, "TTS_SPLIT_RECOVERY")
    db.mark_verified(segment_id, warning_code="ASR_ERROR")
    db.set_segment_warning_code(segment_id, "TTS_SPLIT_RECOVERY")

    assert db.get_segment(segment_id)["warning_code"] == "TTS_SPLIT_RECOVERY|ASR_ERROR"


def test_new_generation_clears_old_audio_warnings_but_keeps_analysis_warning(
    tmp_path: Path,
) -> None:
    db, segment_id = _segment_db(tmp_path)
    db.set_segment_warning_code(segment_id, "LOW_ANALYSIS_CONFIDENCE")
    db.set_segment_warning_code(segment_id, "SEGMENT_FAILED")
    db.set_segment_warning_code(segment_id, "TTS_GENERATION_CEILING_REACHED")
    db.set_segment_warning_code(segment_id, "ASR_SEVERE_MISMATCH")
    db.mark_asr_result(
        segment_id,
        passed=False,
        transcript="wrong",
        similarity=0.0,
        wer=1.0,
        warning_code="ASR_MISMATCH_UNRESOLVED",
    )

    db.mark_generating(segment_id, seed=17)

    row = db.get_segment(segment_id)
    assert row["status"] == "generating"
    assert row["warning_code"] == "LOW_ANALYSIS_CONFIDENCE"
    assert row["asr_text"] is None
    assert row["asr_similarity"] is None
    assert row["asr_wer"] is None
    assert row["error"] is None


def test_audio_reset_keeps_locked_analysis_and_casting(tmp_path: Path) -> None:
    db, segment_id = _segment_db(tmp_path)
    db.update_analysis(
        segment_id,
        {
            "kind": "dialogue",
            "speaker": "LUCIEN",
            "gender": "male",
            "age": "adult",
            "emotion": "neutral",
            "intensity": 1,
            "pace": "normal",
            "volume": "normal",
            "confidence": 1.0,
        },
    )
    profile_id = db.upsert_voice_profile({
        "voice_key": "lucien",
        "engine": "vieneu",
        "preset_name": "Xuân Vĩnh",
        "description": "Lucien",
        "seed": 1,
        "pitch_semitones": 0,
        "status": "ready",
    })
    with db.connect() as conn:
        conn.execute(
            "UPDATE segments SET voice_profile_id=? WHERE id=?",
            (profile_id, segment_id),
        )

    db.reset_segment_pending(segment_id, "WAV needs regeneration")

    row = db.get_segment(segment_id)
    assert row["status"] == "analyzed"
    assert row["kind"] == "dialogue"
    assert row["speaker"] == "LUCIEN"
    assert row["voice_profile_id"] == profile_id

    db.mark_generating(segment_id, seed=23)
    assert db.reset_in_progress_segments("Interrupted generation") == 1

    recovered = db.get_segment(segment_id)
    assert recovered["status"] == "analyzed"
    assert recovered["kind"] == "dialogue"
    assert recovered["speaker"] == "LUCIEN"
    assert recovered["voice_profile_id"] == profile_id


def test_pronunciation_keeps_higher_confidence_value(tmp_path: Path) -> None:
    db = ProjectDB(tmp_path / "project.sqlite3")
    db.upsert_pronunciation(
        surface="Edelweiss",
        normalized_surface="edelweiss",
        spoken_form="Ê đen vai",
        confidence=0.9,
    )
    db.upsert_pronunciation(
        surface="Edelweiss",
        normalized_surface="edelweiss",
        spoken_form="Sai",
        confidence=0.4,
    )

    row = db.list_pronunciations()[0]
    assert row["spoken_form"] == "Ê đen vai"
    assert row["confidence"] == pytest.approx(0.9)


def test_locked_name_pronunciation_is_applied_and_cannot_be_overwritten(tmp_path: Path) -> None:
    db = ProjectDB(tmp_path / "project.sqlite3")
    db.upsert_pronunciation(
        surface="Michael",
        normalized_surface="michael",
        spoken_form="Mai-cồ",
        confidence=0.55,
        source="english_name_transliteration",
        locked=True,
    )
    db.upsert_pronunciation(
        surface="Michael",
        normalized_surface="michael",
        spoken_form="Cách đọc sai",
        confidence=0.99,
        source="analysis",
    )

    row = db.list_pronunciations(minimum_confidence=0.95)[0]
    assert row["spoken_form"] == "Mai-cồ"
    assert row["source"] == "english_name_transliteration"
    assert row["locked"] == 1


def test_pronunciation_is_applied_by_vieneu_coordinator(tmp_path: Path) -> None:
    db = ProjectDB(tmp_path / "project.sqlite3")
    db.upsert_pronunciation(
        surface="Edelweiss",
        normalized_surface="edelweiss",
        spoken_form="Ê đen vai",
        confidence=0.95,
    )
    coordinator = TTSCoordinator(build_settings(), db, lambda _message: None)

    assert coordinator.spoken_text({"text": "Edelweiss nở hoa."}) == "Ê đen vai nở hoa."


def test_vocalization_normalization_is_applied_without_changing_source_row(tmp_path: Path) -> None:
    db = ProjectDB(tmp_path / "project.sqlite3")
    coordinator = TTSCoordinator(build_settings(), db, lambda _message: None)
    row = {"text": "[thở dài] Haizzzzz.... Tôi hiểu rồi."}

    assert coordinator.spoken_text(row) == "Hầy... Hầy... Tôi hiểu rồi."
    assert row["text"] == "[thở dài] Haizzzzz.... Tôi hiểu rồi."


def test_contextual_english_name_pronunciation_preserves_lowercase_vietnamese_word(
    tmp_path: Path,
) -> None:
    db = ProjectDB(tmp_path / "project.sqlite3")
    db.upsert_pronunciation(
        surface="May",
        normalized_surface="may",
        spoken_form="Mây",
        confidence=0.95,
        source=CONTEXTUAL_ENGLISH_NAME_PRONUNCIATION_SOURCE,
        locked=True,
    )
    coordinator = TTSCoordinator(build_settings(), db, lambda _message: None)

    assert coordinator.spoken_text({"text": "May đang may một chiếc áo."}) == "Mây đang may một chiếc áo."


def test_legacy_v0_migration_uses_a_versioned_backup_and_is_idempotent(tmp_path: Path) -> None:
    path = tmp_path / "project.sqlite3"
    legacy = ProjectDB(path)
    legacy.initialize_book(
        title="Legacy",
        project_root=tmp_path,
        settings={"locked": True},
        settings_hash="legacy-settings",
        input_manifest_hash="legacy-manifest",
    )
    chapter_id = legacy.ensure_chapters(
        [
            {
                "chapter_index": 1,
                "title": "Chapter",
                "input_path": tmp_path / "chapter.txt",
                "input_sha256": "source",
                "input_size": 123,
                "output_mp3": tmp_path / "chapter.mp3",
            }
        ]
    )[0]
    legacy.finalize_casting()
    legacy.update_book(status="synthesizing", stage="chapter_synthesis")
    legacy.update_chapter_status(chapter_id, "completed")
    before = dict(legacy.book())
    before_chapter = dict(legacy.list_chapters()[0])
    with legacy.connect() as conn:
        conn.execute("DROP TABLE quality_checks")
        conn.execute("DROP TABLE quality_policies")
        conn.execute("PRAGMA user_version=0")

    stale_backup = path.with_suffix(path.suffix + ".pre-migration.bak")
    with closing(sqlite3.connect(stale_backup)) as conn:
        conn.execute("CREATE TABLE stale_backup(marker TEXT NOT NULL)")
        conn.execute("INSERT INTO stale_backup(marker) VALUES('old')")
        conn.commit()

    migrated = ProjectDB(path)
    versioned_backup = path.with_name(
        f"{path.name}.pre-v0-to-v{SCHEMA_VERSION}.bak"
    )

    assert versioned_backup.is_file()
    assert versioned_backup != stale_backup
    with migrated.connect() as conn:
        assert int(conn.execute("PRAGMA user_version").fetchone()[0]) == SCHEMA_VERSION
        assert conn.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='quality_policies'"
        ).fetchone()[0] == 1
        assert conn.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='quality_checks'"
        ).fetchone()[0] == 1
    with closing(sqlite3.connect(versioned_backup)) as conn:
        conn.row_factory = sqlite3.Row
        backup_book = dict(conn.execute("SELECT * FROM book WHERE id=1").fetchone())
        backup_chapter = dict(conn.execute("SELECT * FROM chapters WHERE id=?", (chapter_id,)).fetchone())
        assert int(conn.execute("PRAGMA user_version").fetchone()[0]) == 0

    assert dict(migrated.book()) == before
    assert dict(migrated.list_chapters()[0]) == before_chapter
    assert backup_book == before
    assert backup_chapter == before_chapter
    backup_mtime = versioned_backup.stat().st_mtime_ns

    reopened = ProjectDB(path)

    assert reopened.current_quality_policy() is None
    assert versioned_backup.stat().st_mtime_ns == backup_mtime
    assert dict(reopened.book()) == before
    assert dict(reopened.list_chapters()[0]) == before_chapter


def test_chapter_artifact_requires_passing_metadata_for_the_current_quality_policy(
    tmp_path: Path,
) -> None:
    db, _segment_id = _segment_db(tmp_path)
    chapter = db.list_chapters()[0]
    chapter_id = int(chapter["id"])
    chapter_index = int(chapter["chapter_index"])
    output = Path(str(chapter["output_mp3"]))
    output.write_bytes(b"ID3" + b"x" * 5000)
    db.set_current_quality_policy(
        policy_hash="policy-v1",
        policy_version=1,
        policy={"profile": "audiobook"},
    )
    db.register_artifact(
        artifact_key=f"chapter_mp3:{chapter_index}",
        kind="chapter_mp3",
        path=output,
        sha256="a" * 64,
        verified=True,
        metadata={"chapter_id": chapter_id},
    )

    assert db.chapter_artifact_is_current_qa_verified(chapter_index) is False

    quality = db.quality_metadata_for_current_policy()
    db.register_artifact(
        artifact_key=f"chapter_mp3:{chapter_index}",
        kind="chapter_mp3",
        path=output,
        sha256="a" * 64,
        verified=True,
        metadata={"chapter_id": chapter_id, "quality": quality},
    )

    assert db.chapter_artifact_is_current_qa_verified(chapter_index) is False

    db.record_quality_check(
        scope=QUALITY_SCOPE_CHAPTER,
        stage=CHAPTER_POST_ENCODE_QUALITY_STAGE,
        artifact_sha256="b" * 64,
        policy_hash=str(quality["policy_hash"]),
        policy_version=int(quality["policy_version"]),
        verdict=QUALITY_VERDICT_PASS,
        chapter_id=chapter_id,
    )

    assert db.chapter_artifact_is_current_qa_verified(chapter_index) is False

    check_id = db.record_quality_check(
        scope=QUALITY_SCOPE_CHAPTER,
        stage=CHAPTER_POST_ENCODE_QUALITY_STAGE,
        artifact_sha256="a" * 64,
        policy_hash=str(quality["policy_hash"]),
        policy_version=int(quality["policy_version"]),
        verdict=QUALITY_VERDICT_PASS,
        chapter_id=chapter_id,
        metrics={"loudness_lufs": -18.0},
    )
    db.register_artifact(
        artifact_key=f"chapter_mp3:{chapter_index}",
        kind="chapter_mp3",
        path=output,
        sha256="a" * 64,
        verified=True,
        metadata={"chapter_id": chapter_id, "quality": quality},
    )

    latest = db.latest_quality_check(
        scope=QUALITY_SCOPE_CHAPTER,
        stage=CHAPTER_POST_ENCODE_QUALITY_STAGE,
        chapter_id=chapter_id,
    )
    assert latest is not None
    assert int(latest["id"]) == check_id
    assert latest["verdict"] == QUALITY_VERDICT_PASS
    assert db.chapter_artifact_is_current_qa_verified(chapter_index) is True

    db.set_current_quality_policy(
        policy_hash="policy-v2",
        policy_version=2,
        policy={"profile": "audiobook", "true_peak_db": -2.0},
    )

    assert db.chapter_artifact_is_current_qa_verified(chapter_index) is False
    assert db.latest_quality_check(
        scope=QUALITY_SCOPE_CHAPTER,
        stage=CHAPTER_POST_ENCODE_QUALITY_STAGE,
        chapter_id=chapter_id,
    ) is None


def test_segment_audio_requires_matching_current_policy_pass_check(tmp_path: Path) -> None:
    db, segment_id = _segment_db(tmp_path)
    wav_sha256 = "c" * 64
    db.mark_signal_passed(
        segment_id,
        wav_path=tmp_path / "segment.wav",
        wav_sha256=wav_sha256,
        duration=1.0,
        signal={"duration": 1.0},
    )
    db.set_current_quality_policy(
        policy_hash="segment-policy-v1",
        policy_version=1,
        policy={"profile": "audiobook"},
    )
    quality = db.quality_metadata_for_current_policy()

    assert db.segment_audio_is_current_qa_verified(
        segment_id,
        wav_sha256,
        SEGMENT_AUDIO_QUALITY_STAGE,
    ) is False

    db.record_quality_check(
        scope=QUALITY_SCOPE_SEGMENT,
        stage=SEGMENT_AUDIO_QUALITY_STAGE,
        artifact_sha256="d" * 64,
        policy_hash=str(quality["policy_hash"]),
        policy_version=int(quality["policy_version"]),
        verdict=QUALITY_VERDICT_PASS,
        segment_id=segment_id,
    )

    assert db.segment_audio_is_current_qa_verified(
        segment_id,
        wav_sha256,
        SEGMENT_AUDIO_QUALITY_STAGE,
    ) is False

    db.record_quality_check(
        scope=QUALITY_SCOPE_SEGMENT,
        stage=SEGMENT_AUDIO_QUALITY_STAGE,
        artifact_sha256=wav_sha256,
        policy_hash=str(quality["policy_hash"]),
        policy_version=int(quality["policy_version"]),
        verdict=QUALITY_VERDICT_PASS,
        segment_id=segment_id,
    )

    assert db.segment_audio_is_current_qa_verified(
        segment_id,
        wav_sha256,
        SEGMENT_AUDIO_QUALITY_STAGE,
    ) is True

    db.set_current_quality_policy(
        policy_hash="segment-policy-v2",
        policy_version=2,
        policy={"profile": "audiobook", "strict": True},
    )

    assert db.segment_audio_is_current_qa_verified(
        segment_id,
        wav_sha256,
        SEGMENT_AUDIO_QUALITY_STAGE,
    ) is False
