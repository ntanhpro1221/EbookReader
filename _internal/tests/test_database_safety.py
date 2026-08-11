from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from pathlib import Path

import pytest

from ebook_reader.database import (
    CHAPTER_POST_ENCODE_QUALITY_STAGE,
    GENERATION_DELIVERY_CLARITY,
    GENERATION_DELIVERY_PRIMARY,
    QUALITY_SCOPE_CHAPTER,
    QUALITY_SCOPE_SEGMENT,
    QUALITY_VERDICT_PASS,
    SCHEMA_VERSION,
    SEGMENT_ASR_DECODE_QUALITY_STAGE,
    SEGMENT_AUDIO_QUALITY_STAGE,
    SEGMENT_PERCEPTUAL_QUALITY_STAGE,
    ProjectDB,
)
from ebook_reader.io_utils import sha256_file
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


def _candidate_db(tmp_path: Path) -> tuple[ProjectDB, int, str, Path]:
    db, segment_id = _segment_db(tmp_path)
    profile_id = db.upsert_voice_profile(
        {
            "voice_key": "candidate-narrator",
            "engine": "vieneu",
            "preset_name": "Candidate Voice",
            "description": "Candidate test voice",
            "seed": 7,
            "pitch_semitones": 0,
            "status": "ready",
        }
    )
    with db.connect() as conn:
        conn.execute(
            "UPDATE segments SET voice_profile_id=? WHERE id=?",
            (profile_id, segment_id),
        )
    incumbent_sha256 = "a" * 64
    incumbent_path = tmp_path / "incumbent.wav"
    db.mark_signal_passed(
        segment_id,
        wav_path=incumbent_path,
        wav_sha256=incumbent_sha256,
        duration=1.0,
        signal={"duration": 1.0, "spoken_text_sha256": "1" * 64},
        generation_seed=11,
    )
    db.set_current_quality_policy(
        policy_hash="candidate-policy-v1",
        policy_version=1,
        policy={"asr": {"repair_rounds": 2}},
    )
    return db, segment_id, incumbent_sha256, incumbent_path


def _checkpoint_candidate_signal(
    db: ProjectDB,
    candidate_id: int,
    *,
    repair_round: int,
    generation_seed: int,
    wav_path: Path,
    wav_sha256: str,
    signal_overrides: dict | None = None,
) -> None:
    candidate = db.get_segment_candidate(candidate_id)
    signal = {
        "duration": 1.25,
        "tts_delivery_mode": "clarity",
        "asr_clarity_repair_round": repair_round,
        "spoken_text_sha256": "2" * 64,
        "voice_profile_id": int(candidate["expected_voice_profile_id"]),
        "pitch_semitones": 0,
        "effective_pitch_semitones": 0,
        "pitch_variant_skipped": 0.0,
        "pitch_variant_mixed": 0.0,
    }
    signal.update(signal_overrides or {})
    db.checkpoint_segment_candidate_signal(
        candidate_id,
        expected_generation_seed=generation_seed,
        wav_path=wav_path,
        wav_sha256=wav_sha256,
        duration=1.25,
        signal=signal,
    )


def _candidate_decode_check(
    db: ProjectDB,
    *,
    segment_id: int,
    artifact_sha256: str,
    repair_round: int,
    generation_seed: int,
    confirmation: bool,
    verdict: str,
    reason: str,
    metrics_overrides: dict | None = None,
) -> int:
    segment = db.get_segment(segment_id)
    metrics_verdict = (
        "pass" if verdict == "pass" else "inconclusive" if verdict == "inconclusive" else "mismatch"
    )
    metrics = {
        "verdict": metrics_verdict,
        "passed": verdict == "pass",
        "reason": reason,
        "decode_mode": "greedy" if confirmation else "beam5",
        "selected": True,
        "delivery_mode": "clarity",
        "repair_round": repair_round,
        "generation_seed": generation_seed,
        "spoken_text_sha256": "2" * 64,
        "voice_profile_id": int(segment["voice_profile_id"]),
        "pitch_semitones": 0,
        "effective_pitch_semitones": 0,
        "pitch_variant_skipped": False,
        "pitch_variant_mixed": False,
        "transcript": "Text",
        "similarity": 1.0 if verdict == "pass" else 0.2,
        "wer": 0.0 if verdict == "pass" else 1.0,
    }
    metrics.update(metrics_overrides or {})
    return db.record_quality_check(
        scope=QUALITY_SCOPE_SEGMENT,
        stage=SEGMENT_ASR_DECODE_QUALITY_STAGE,
        segment_id=segment_id,
        artifact_sha256=artifact_sha256,
        policy_hash="candidate-policy-v1",
        policy_version=1,
        verdict=verdict,
        metrics=metrics,
    )


def _candidate_perceptual_check(
    db: ProjectDB,
    *,
    segment_id: int,
    artifact_sha256: str,
    verdict: str,
    perceptual_verdict: str,
    reason: str,
    review_required: bool,
    baseline_pitch_semitones: int = 0,
) -> int:
    return db.record_quality_check(
        scope=QUALITY_SCOPE_SEGMENT,
        stage=SEGMENT_PERCEPTUAL_QUALITY_STAGE,
        segment_id=segment_id,
        artifact_sha256=artifact_sha256,
        policy_hash="candidate-policy-v1",
        policy_version=1,
        verdict=verdict,
        metrics={
            "verdict": perceptual_verdict,
            "reason": reason,
            "review_required": review_required,
            "score": 3.8,
            "baseline_score": 4.0,
            "baseline_delta": -0.2,
            "baseline_pitch_semitones": baseline_pitch_semitones,
        },
    )


def _write_candidate_artifact(path: Path, label: str) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(f"candidate-audio:{label}".encode("utf-8"))
    return sha256_file(path)


def _dual_pass_candidate(
    db: ProjectDB,
    *,
    segment_id: int,
    incumbent_sha256: str,
    candidate_path: Path,
    generation_seed: int,
    perceptual_required: bool,
) -> tuple[sqlite3.Row, str]:
    candidate_sha256 = _write_candidate_artifact(candidate_path, str(generation_seed))
    candidate = db.allocate_segment_candidate(
        segment_id=segment_id,
        policy_hash="candidate-policy-v1",
        repair_round=0,
        max_repair_rounds=2,
        incumbent_sha256=incumbent_sha256,
        generation_seed=generation_seed,
        wav_path=candidate_path,
        candidates_root=candidate_path.parent,
        perceptual_required=perceptual_required,
    )
    candidate_id = int(candidate["id"])
    _checkpoint_candidate_signal(
        db,
        candidate_id,
        repair_round=0,
        generation_seed=generation_seed,
        wav_path=candidate_path,
        wav_sha256=candidate_sha256,
    )
    for confirmation in (False, True):
        check_id = _candidate_decode_check(
            db,
            segment_id=segment_id,
            artifact_sha256=candidate_sha256,
            repair_round=0,
            generation_seed=generation_seed,
            confirmation=confirmation,
            verdict="pass",
            reason="ok",
        )
        db.checkpoint_segment_candidate_decode(
            candidate_id,
            quality_check_id=check_id,
            confirmation=confirmation,
        )
    return db.get_segment_candidate(candidate_id), candidate_sha256


def test_warning_codes_are_merged_without_duplicates(tmp_path: Path) -> None:
    db, segment_id = _segment_db(tmp_path)

    db.set_segment_warning_code(segment_id, "TTS_SPLIT_RECOVERY")
    db.mark_verified(segment_id, warning_code="ASR_ERROR")
    db.set_segment_warning_code(segment_id, "TTS_SPLIT_RECOVERY")

    assert db.get_segment(segment_id)["warning_code"] == "TTS_SPLIT_RECOVERY|ASR_ERROR"


def test_signal_checkpoint_commits_derived_warnings_atomically(tmp_path: Path) -> None:
    db, segment_id = _segment_db(tmp_path)
    wav_path = tmp_path / "segment.wav"
    wav_path.write_bytes(b"wav")

    db.mark_signal_passed(
        segment_id,
        wav_path=wav_path,
        wav_sha256="a" * 64,
        duration=1.0,
        signal={"pitch_variant_skipped": 1.0},
        generation_seed=17,
        warning_codes=(
            "TTS_SPLIT_RECOVERY",
            "TTS_PITCH_VARIANT_SKIPPED",
            "TTS_PITCH_VARIANT_SKIPPED",
        ),
    )

    row = db.get_segment(segment_id)
    assert row["status"] == "signal_passed"
    assert row["warning_code"] == (
        "TTS_SPLIT_RECOVERY|TTS_PITCH_VARIANT_SKIPPED"
    )


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


def test_short_ceiling_frame_cap_survives_interruption_and_reopen(tmp_path: Path) -> None:
    db, segment_id = _segment_db(tmp_path)
    db.set_segment_generation_frame_cap(segment_id, 12)
    db.mark_generating(segment_id, seed=17)

    reopened = ProjectDB(db.path)
    assert reopened.reset_in_progress_segments() == 1
    recovered = reopened.get_segment(segment_id)

    assert recovered["generation_frame_cap"] == 12
    reopened.mark_verified(segment_id)
    assert reopened.get_segment(segment_id)["generation_frame_cap"] is None


def test_clarity_generation_checkpoint_survives_interruption_until_explicit_reset(
    tmp_path: Path,
) -> None:
    db, segment_id = _segment_db(tmp_path)
    with pytest.raises(ValueError, match="clarity generation requires"):
        db.mark_generating(
            segment_id,
            seed=16,
            delivery_mode=GENERATION_DELIVERY_CLARITY,
            policy_hash="policy-v1",
        )
    db.mark_generating(
        segment_id,
        seed=17,
        delivery_mode=GENERATION_DELIVERY_CLARITY,
        repair_round=0,
        policy_hash="policy-v1",
    )

    reopened = ProjectDB(db.path)
    assert reopened.reset_in_progress_segments() == 1
    recovered = reopened.get_segment(segment_id)
    assert recovered["status"] == "pending"
    assert recovered["generation_delivery_mode"] == GENERATION_DELIVERY_CLARITY
    assert recovered["generation_repair_round"] == 0
    assert recovered["generation_policy_hash"] == "policy-v1"

    reopened.reset_segment_pending(segment_id, "explicit clean regeneration")
    reset = reopened.get_segment(segment_id)
    assert reset["generation_delivery_mode"] == GENERATION_DELIVERY_PRIMARY
    assert reset["generation_repair_round"] is None
    assert reset["generation_policy_hash"] is None


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


def test_schema_v2_without_generation_frame_cap_migrates_to_current(tmp_path: Path) -> None:
    path = tmp_path / "project.sqlite3"
    legacy = ProjectDB(path)
    with legacy.connect() as conn:
        conn.execute("ALTER TABLE segments DROP COLUMN generation_frame_cap")
        conn.execute("PRAGMA user_version=2")
        columns = {str(row[1]) for row in conn.execute("PRAGMA table_info(segments)")}
    assert "generation_frame_cap" not in columns

    migrated = ProjectDB(path)
    backup = path.with_name(f"{path.name}.pre-v2-to-v{SCHEMA_VERSION}.bak")
    with migrated.connect() as conn:
        columns = {str(row[1]) for row in conn.execute("PRAGMA table_info(segments)")}
        version = int(conn.execute("PRAGMA user_version").fetchone()[0])
    assert backup.is_file()
    with closing(sqlite3.connect(backup)) as conn:
        backup_columns = {
            str(row[1]) for row in conn.execute("PRAGMA table_info(segments)")
        }
        backup_version = int(conn.execute("PRAGMA user_version").fetchone()[0])

    assert "generation_frame_cap" in columns
    assert version == SCHEMA_VERSION
    assert "generation_frame_cap" not in backup_columns
    assert backup_version == 2


def test_schema_v3_adds_durable_generation_context(tmp_path: Path) -> None:
    path = tmp_path / "project.sqlite3"
    legacy = ProjectDB(path)
    context_columns = {
        "generation_delivery_mode",
        "generation_repair_round",
        "generation_policy_hash",
    }
    with legacy.connect() as conn:
        for column in reversed(tuple(context_columns)):
            conn.execute(f"ALTER TABLE segments DROP COLUMN {column}")
        conn.execute("PRAGMA user_version=3")
        columns = {str(row[1]) for row in conn.execute("PRAGMA table_info(segments)")}
    assert context_columns.isdisjoint(columns)

    migrated = ProjectDB(path)
    backup = path.with_name(f"{path.name}.pre-v3-to-v{SCHEMA_VERSION}.bak")
    with migrated.connect() as conn:
        columns = {str(row[1]) for row in conn.execute("PRAGMA table_info(segments)")}
        version = int(conn.execute("PRAGMA user_version").fetchone()[0])
    with closing(sqlite3.connect(backup)) as conn:
        backup_columns = {
            str(row[1]) for row in conn.execute("PRAGMA table_info(segments)")
        }
        backup_version = int(conn.execute("PRAGMA user_version").fetchone()[0])

    assert backup.is_file()
    assert context_columns.issubset(columns)
    assert version == SCHEMA_VERSION
    assert context_columns.isdisjoint(backup_columns)
    assert backup_version == 3


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
        stage=SEGMENT_ASR_DECODE_QUALITY_STAGE,
        artifact_sha256=wav_sha256,
        policy_hash=str(quality["policy_hash"]),
        policy_version=int(quality["policy_version"]),
        verdict=QUALITY_VERDICT_PASS,
        segment_id=segment_id,
        metrics={"decode_mode": "beam5", "selected": True},
    )

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


def test_schema_v4_migrates_candidate_ledger_with_versioned_backup(tmp_path: Path) -> None:
    path = tmp_path / "project.sqlite3"
    ProjectDB(path)
    with sqlite3.connect(path) as conn:
        conn.execute("DROP TABLE segment_candidates")
        conn.execute("PRAGMA user_version=4")

    migrated = ProjectDB(path)
    backup = path.with_name(f"{path.name}.pre-v4-to-v{SCHEMA_VERSION}.bak")

    with migrated.connect() as conn:
        columns = {str(row[1]) for row in conn.execute("PRAGMA table_info(segment_candidates)")}
        assert int(conn.execute("PRAGMA user_version").fetchone()[0]) == SCHEMA_VERSION
    with sqlite3.connect(backup) as conn:
        backup_table = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='segment_candidates'"
        ).fetchone()
        assert int(conn.execute("PRAGMA user_version").fetchone()[0]) == 4

    assert {
        "segment_id",
        "policy_hash",
        "repair_round",
        "expected_voice_profile_id",
        "expected_pitch_semitones",
        "state",
        "final_check_id",
    } <= columns
    assert backup_table is None
    assert ProjectDB(path).list_segment_candidates() == []


def test_schema_v5_migrates_existing_candidate_perceptual_ledger(tmp_path: Path) -> None:
    db, segment_id, incumbent_sha256, _incumbent_path = _candidate_db(tmp_path)
    candidate_path = tmp_path / "candidates" / "r0.wav"
    candidate = db.allocate_segment_candidate(
        segment_id=segment_id,
        policy_hash="candidate-policy-v1",
        repair_round=0,
        max_repair_rounds=2,
        incumbent_sha256=incumbent_sha256,
        generation_seed=71,
        wav_path=candidate_path,
        candidates_root=tmp_path / "candidates",
    )
    path = db.path
    with sqlite3.connect(path) as conn:
        conn.execute("ALTER TABLE segment_candidates RENAME TO segment_candidates_v6_source")
        conn.execute(
            """
            CREATE TABLE segment_candidates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                segment_id INTEGER NOT NULL REFERENCES segments(id) ON DELETE CASCADE,
                policy_hash TEXT NOT NULL REFERENCES quality_policies(policy_hash),
                repair_round INTEGER NOT NULL CHECK (repair_round >= 0),
                incumbent_sha256 TEXT NOT NULL,
                expected_voice_profile_id INTEGER NOT NULL REFERENCES voice_profiles(id),
                expected_pitch_semitones INTEGER NOT NULL,
                state TEXT NOT NULL,
                tts_attempt INTEGER NOT NULL DEFAULT 0 CHECK (tts_attempt >= 0),
                generation_seed INTEGER NOT NULL,
                wav_path TEXT NOT NULL UNIQUE,
                wav_sha256 TEXT,
                wav_duration REAL,
                signal_json TEXT,
                beam_result_json TEXT,
                greedy_result_json TEXT,
                beam_check_id INTEGER REFERENCES quality_checks(id),
                greedy_check_id INTEGER REFERENCES quality_checks(id),
                final_check_id INTEGER REFERENCES quality_checks(id),
                failure_reason TEXT,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL,
                promoted_at REAL,
                UNIQUE(segment_id, policy_hash, repair_round)
            )
            """
        )
        conn.execute(
            """
            INSERT INTO segment_candidates(
                id,segment_id,policy_hash,repair_round,incumbent_sha256,
                expected_voice_profile_id,expected_pitch_semitones,state,
                tts_attempt,generation_seed,wav_path,wav_sha256,wav_duration,
                signal_json,beam_result_json,greedy_result_json,beam_check_id,
                greedy_check_id,final_check_id,failure_reason,created_at,updated_at,promoted_at
            )
            SELECT
                id,segment_id,policy_hash,repair_round,incumbent_sha256,
                expected_voice_profile_id,expected_pitch_semitones,state,
                tts_attempt,generation_seed,wav_path,wav_sha256,wav_duration,
                signal_json,beam_result_json,greedy_result_json,beam_check_id,
                greedy_check_id,final_check_id,failure_reason,created_at,updated_at,promoted_at
            FROM segment_candidates_v6_source
            """
        )
        conn.execute("DROP TABLE segment_candidates_v6_source")
        conn.execute("PRAGMA user_version=5")

    migrated = ProjectDB(path)
    backup = path.with_name(f"{path.name}.pre-v5-to-v{SCHEMA_VERSION}.bak")
    migrated_candidate = migrated.get_segment_candidate(int(candidate["id"]))
    with migrated.connect() as conn:
        columns = {str(row[1]) for row in conn.execute("PRAGMA table_info(segment_candidates)")}
        version = int(conn.execute("PRAGMA user_version").fetchone()[0])
    with sqlite3.connect(backup) as conn:
        backup_columns = {
            str(row[1]) for row in conn.execute("PRAGMA table_info(segment_candidates)")
        }
        backup_version = int(conn.execute("PRAGMA user_version").fetchone()[0])

    assert version == SCHEMA_VERSION
    assert backup_version == 5
    assert {"repair_budget", "perceptual_required", "perceptual_result_json", "perceptual_check_id"} <= columns
    assert "repair_budget" not in backup_columns
    assert int(migrated_candidate["repair_budget"]) == 1
    assert int(migrated_candidate["perceptual_required"]) == 0
    assert migrated.segment_candidate_resume_plan(segment_id, "candidate-policy-v1")["action"] == "generate"


def test_candidate_allocation_is_idempotent_budgeted_and_policy_scoped(tmp_path: Path) -> None:
    db, segment_id, incumbent_sha256, incumbent_path = _candidate_db(tmp_path)
    candidate_path = tmp_path / "candidates" / "r0.wav"
    with pytest.raises(RuntimeError, match="collides"):
        db.allocate_segment_candidate(
            segment_id=segment_id,
            policy_hash="candidate-policy-v1",
            repair_round=0,
            max_repair_rounds=2,
            incumbent_sha256=incumbent_sha256,
            generation_seed=100,
            wav_path=incumbent_path.with_name(incumbent_path.name.swapcase()),
            candidates_root=tmp_path,
        )
    first = db.allocate_segment_candidate(
        segment_id=segment_id,
        policy_hash="candidate-policy-v1",
        repair_round=0,
        max_repair_rounds=2,
        incumbent_sha256=incumbent_sha256,
        generation_seed=101,
        wav_path=candidate_path,
        candidates_root=tmp_path / "candidates",
    )
    replay = db.allocate_segment_candidate(
        segment_id=segment_id,
        policy_hash="candidate-policy-v1",
        repair_round=0,
        max_repair_rounds=2,
        incumbent_sha256=incumbent_sha256,
        generation_seed=101,
        wav_path=candidate_path,
        candidates_root=tmp_path / "candidates",
    )

    assert int(replay["id"]) == int(first["id"])
    assert db.segment_candidate_resume_plan(segment_id, "candidate-policy-v1", 2)["action"] == "generate"
    with pytest.raises(RuntimeError, match="resume metadata"):
        db.allocate_segment_candidate(
            segment_id=segment_id,
            policy_hash="candidate-policy-v1",
            repair_round=0,
            max_repair_rounds=2,
            incumbent_sha256=incumbent_sha256,
            generation_seed=102,
            wav_path=candidate_path,
            candidates_root=tmp_path / "candidates",
        )
    with pytest.raises(RuntimeError, match="terminal failure"):
        db.allocate_segment_candidate(
            segment_id=segment_id,
            policy_hash="candidate-policy-v1",
            repair_round=1,
            max_repair_rounds=2,
            incumbent_sha256=incumbent_sha256,
            generation_seed=202,
            wav_path=tmp_path / "candidates" / "r1.wav",
            candidates_root=tmp_path / "candidates",
        )

    advanced = db.restart_segment_candidate_generation(
        int(first["id"]),
        expected_generation_seed=101,
        generation_seed=102,
        tts_attempt=1,
    )
    replayed_advance = db.restart_segment_candidate_generation(
        int(first["id"]),
        expected_generation_seed=101,
        generation_seed=102,
        tts_attempt=1,
    )
    assert int(advanced["generation_seed"]) == 102
    assert int(replayed_advance["generation_seed"]) == 102
    db.mark_segment_candidate_tts_failed(
        int(first["id"]),
        expected_generation_seed=102,
        error="TTS failed",
    )
    replayed_failure = db.mark_segment_candidate_tts_failed(
        int(first["id"]),
        expected_generation_seed=102,
        error="TTS failed",
    )
    assert replayed_failure["state"] == "tts_failed"
    with pytest.raises(RuntimeError, match="replay payload"):
        db.mark_segment_candidate_tts_failed(
            int(first["id"]),
            expected_generation_seed=102,
            error="different TTS failure",
        )
    assert db.segment_candidate_resume_plan(segment_id, "candidate-policy-v1", 2) == {
        "segment_id": segment_id,
        "policy_hash": "candidate-policy-v1",
        "action": "allocate",
        "candidate_id": None,
        "repair_round": 1,
    }
    with db.connect() as conn:
        conn.execute("UPDATE segments SET wav_sha256=? WHERE id=?", ("d" * 64, segment_id))
    assert db.segment_candidate_resume_plan(segment_id, "candidate-policy-v1", 2)["action"] == (
        "stale_incumbent"
    )
    with pytest.raises(RuntimeError, match="stale incumbent"):
        db.allocate_segment_candidate(
            segment_id=segment_id,
            policy_hash="candidate-policy-v1",
            repair_round=1,
            max_repair_rounds=2,
            incumbent_sha256=incumbent_sha256,
            generation_seed=202,
            wav_path=tmp_path / "candidates" / "r1.wav",
            candidates_root=tmp_path / "candidates",
        )
    with db.connect() as conn:
        conn.execute("UPDATE segments SET wav_sha256=? WHERE id=?", (incumbent_sha256, segment_id))
    db.set_current_quality_policy(
        policy_hash="candidate-policy-v2",
        policy_version=1,
        policy={"asr": {"repair_rounds": 2}, "changed": True},
    )
    assert db.segment_candidate_resume_plan(segment_id, "candidate-policy-v1", 2)["action"] == (
        "stale_policy"
    )
    with pytest.raises(RuntimeError, match="no longer active"):
        db.restart_segment_candidate_generation(
            int(first["id"]),
            expected_generation_seed=101,
            generation_seed=102,
            tts_attempt=1,
        )


def test_candidate_requires_locked_casting_and_thought_uses_narrator(tmp_path: Path) -> None:
    db, segment_id = _segment_db(tmp_path)
    incumbent_sha256 = "a" * 64
    db.mark_signal_passed(
        segment_id,
        wav_path=tmp_path / "incumbent.wav",
        wav_sha256=incumbent_sha256,
        duration=1.0,
        signal={"duration": 1.0},
        generation_seed=1,
    )
    db.set_current_quality_policy(
        policy_hash="candidate-policy-v1",
        policy_version=1,
        policy={"asr": {"repair_rounds": 1}},
    )
    with pytest.raises(RuntimeError, match="assigned locked voice"):
        db.allocate_segment_candidate(
            segment_id=segment_id,
            policy_hash="candidate-policy-v1",
            repair_round=0,
            max_repair_rounds=1,
            incumbent_sha256=incumbent_sha256,
            generation_seed=10,
            wav_path=tmp_path / "candidates" / "missing-cast.wav",
            candidates_root=tmp_path / "candidates",
        )

    character_profile = db.upsert_voice_profile(
        {
            "voice_key": "thought-character",
            "engine": "vieneu",
            "preset_name": "Character",
            "description": "Character voice",
            "seed": 2,
            "pitch_semitones": 0,
            "status": "ready",
        }
    )
    narrator_profile = db.upsert_voice_profile(
        {
            "voice_key": "NARRATOR",
            "engine": "vieneu",
            "preset_name": "Narrator",
            "description": "Narrator voice",
            "seed": 3,
            "pitch_semitones": -1,
            "status": "ready",
        }
    )
    with db.connect() as conn:
        conn.execute(
            "UPDATE segments SET kind='thought',voice_profile_id=? WHERE id=?",
            (character_profile, segment_id),
        )
    candidate = db.allocate_segment_candidate(
        segment_id=segment_id,
        policy_hash="candidate-policy-v1",
        repair_round=0,
        max_repair_rounds=1,
        incumbent_sha256=incumbent_sha256,
        generation_seed=11,
        wav_path=tmp_path / "candidates" / "thought.wav",
        candidates_root=tmp_path / "candidates",
    )
    assert int(candidate["expected_voice_profile_id"]) == narrator_profile
    assert int(candidate["expected_pitch_semitones"]) == -1


def test_candidate_rejects_casting_change_after_allocation(tmp_path: Path) -> None:
    db, segment_id, incumbent_sha256, _incumbent_path = _candidate_db(tmp_path)
    candidate_path = tmp_path / "candidates" / "casting.wav"
    candidate_sha256 = _write_candidate_artifact(candidate_path, "casting-change")
    candidate = db.allocate_segment_candidate(
        segment_id=segment_id,
        policy_hash="candidate-policy-v1",
        repair_round=0,
        max_repair_rounds=2,
        incumbent_sha256=incumbent_sha256,
        generation_seed=33,
        wav_path=candidate_path,
        candidates_root=tmp_path / "candidates",
    )
    replacement_profile = db.upsert_voice_profile(
        {
            "voice_key": "replacement-voice",
            "engine": "vieneu",
            "preset_name": "Replacement",
            "description": "Replacement voice",
            "seed": 4,
            "pitch_semitones": 0,
            "status": "ready",
        }
    )
    with db.connect() as conn:
        conn.execute(
            "UPDATE segments SET voice_profile_id=? WHERE id=?",
            (replacement_profile, segment_id),
        )
    with pytest.raises(RuntimeError, match="casting changed"):
        _checkpoint_candidate_signal(
            db,
            int(candidate["id"]),
            repair_round=0,
            generation_seed=33,
            wav_path=candidate_path,
            wav_sha256=candidate_sha256,
        )


def test_candidate_promotion_is_atomic_idempotent_and_preserves_incumbent_on_abort(
    tmp_path: Path,
) -> None:
    db, segment_id, incumbent_sha256, _incumbent_path = _candidate_db(tmp_path)
    candidate_path = tmp_path / "candidates" / "r0.wav"
    candidate_sha256 = _write_candidate_artifact(candidate_path, "atomic-promotion")
    candidate = db.allocate_segment_candidate(
        segment_id=segment_id,
        policy_hash="candidate-policy-v1",
        repair_round=0,
        max_repair_rounds=2,
        incumbent_sha256=incumbent_sha256,
        generation_seed=101,
        wav_path=candidate_path,
        candidates_root=tmp_path / "candidates",
    )
    candidate_id = int(candidate["id"])
    _checkpoint_candidate_signal(
        db,
        candidate_id,
        repair_round=0,
        generation_seed=101,
        wav_path=candidate_path,
        wav_sha256=candidate_sha256,
    )
    beam_check = _candidate_decode_check(
        db,
        segment_id=segment_id,
        artifact_sha256=candidate_sha256,
        repair_round=0,
        generation_seed=101,
        confirmation=False,
        verdict="pass",
        reason="ok",
    )
    db.checkpoint_segment_candidate_decode(
        candidate_id,
        quality_check_id=beam_check,
        confirmation=False,
    )
    assert db.get_segment(segment_id)["wav_sha256"] == incumbent_sha256
    assert db.segment_candidate_resume_plan(segment_id, "candidate-policy-v1", 2)["action"] == (
        "decode_greedy"
    )

    greedy_check = _candidate_decode_check(
        db,
        segment_id=segment_id,
        artifact_sha256=candidate_sha256,
        repair_round=0,
        generation_seed=101,
        confirmation=True,
        verdict="pass",
        reason="ok",
    )
    db.checkpoint_segment_candidate_decode(
        candidate_id,
        quality_check_id=greedy_check,
        confirmation=True,
    )
    with db.connect() as conn:
        conn.execute(
            f"""
            CREATE TRIGGER abort_candidate_promotion
            BEFORE UPDATE OF wav_sha256 ON segments
            WHEN NEW.wav_sha256='{candidate_sha256}'
            BEGIN SELECT RAISE(ABORT, 'simulated promotion crash'); END
            """
        )
    with pytest.raises(sqlite3.IntegrityError, match="simulated promotion crash"):
        db.promote_segment_candidate(
            candidate_id,
            validated_wav_sha256=candidate_sha256,
            repair_action="clarity_repair",
            attempt=1,
            warning_code="ASR_CLARITY_REPAIR",
        )
    with db.connect() as conn:
        stray_passes = conn.execute(
            """
            SELECT COUNT(*) FROM quality_checks
            WHERE stage=? AND artifact_sha256=? AND verdict='pass'
            """,
            (SEGMENT_AUDIO_QUALITY_STAGE, candidate_sha256),
        ).fetchone()[0]
        conn.execute("DROP TRIGGER abort_candidate_promotion")
    assert stray_passes == 0
    assert db.get_segment(segment_id)["wav_sha256"] == incumbent_sha256
    assert db.get_segment_candidate(candidate_id)["state"] == "dual_passed"

    promoted = db.promote_segment_candidate(
        candidate_id,
        validated_wav_sha256=candidate_sha256,
        repair_action="clarity_repair",
        attempt=1,
        warning_code="ASR_CLARITY_REPAIR",
    )
    replay = db.promote_segment_candidate(
        candidate_id,
        validated_wav_sha256=candidate_sha256,
        repair_action="clarity_repair",
        attempt=1,
        warning_code="ASR_CLARITY_REPAIR",
    )
    assert promoted["state"] == "promoted"
    assert int(replay["id"]) == candidate_id
    assert db.get_segment(segment_id)["wav_sha256"] == candidate_sha256
    assert db.segment_candidate_resume_plan(segment_id, "candidate-policy-v1", 2)["action"] == (
        "complete"
    )
    with db.connect() as conn:
        pass_count = conn.execute(
            """
            SELECT COUNT(*) FROM quality_checks
            WHERE stage=? AND artifact_sha256=? AND verdict='pass'
            """,
            (SEGMENT_AUDIO_QUALITY_STAGE, candidate_sha256),
        ).fetchone()[0]
    assert pass_count == 1
    final_check = db.latest_quality_check(
        scope=QUALITY_SCOPE_SEGMENT,
        stage=SEGMENT_AUDIO_QUALITY_STAGE,
        segment_id=segment_id,
    )
    final_metrics = json.loads(str(final_check["metrics_json"]))
    assert final_metrics["transcript"] == "Text"
    assert final_metrics["confirmation_verdicts"] == ["pass", "pass"]
    assert len(final_metrics["decode_evidence"]) == 2
    with pytest.raises(RuntimeError, match="replay"):
        db.promote_segment_candidate(
            candidate_id,
            validated_wav_sha256=candidate_sha256,
            repair_action="different_repair",
            attempt=1,
            warning_code="ASR_CLARITY_REPAIR",
        )
    with pytest.raises(RuntimeError, match="replay"):
        db.promote_segment_candidate(
            candidate_id,
            validated_wav_sha256=candidate_sha256,
            repair_action="clarity_repair",
            attempt=1,
            warning_code="DIFFERENT_WARNING",
        )


def test_candidate_requires_current_perceptual_pass_before_atomic_promotion(
    tmp_path: Path,
) -> None:
    db, segment_id, incumbent_sha256, _incumbent_path = _candidate_db(tmp_path)
    candidate, candidate_sha256 = _dual_pass_candidate(
        db,
        segment_id=segment_id,
        incumbent_sha256=incumbent_sha256,
        candidate_path=tmp_path / "candidates" / "perceptual-pass.wav",
        generation_seed=211,
        perceptual_required=True,
    )
    candidate_id = int(candidate["id"])

    assert db.segment_candidate_resume_plan(segment_id, "candidate-policy-v1") == {
        "segment_id": segment_id,
        "policy_hash": "candidate-policy-v1",
        "action": "verify_perceptual",
        "candidate_id": candidate_id,
        "repair_round": 0,
        "state": "dual_passed",
        "generation_seed": 211,
        "tts_attempt": 0,
        "wav_path": str((tmp_path / "candidates" / "perceptual-pass.wav").resolve()),
        "wav_sha256": candidate_sha256,
        "perceptual_required": True,
    }
    with pytest.raises(RuntimeError, match="before perceptual QA passes"):
        db.promote_segment_candidate(
            candidate_id,
            validated_wav_sha256=candidate_sha256,
            repair_action="clarity_repair",
            attempt=1,
        )

    perceptual_check_id = _candidate_perceptual_check(
        db,
        segment_id=segment_id,
        artifact_sha256=candidate_sha256,
        verdict="pass",
        perceptual_verdict="ok",
        reason="PERCEPTUAL_OK",
        review_required=False,
    )
    checkpointed = db.checkpoint_segment_candidate_perceptual(
        candidate_id,
        quality_check_id=perceptual_check_id,
    )
    replay = db.checkpoint_segment_candidate_perceptual(
        candidate_id,
        quality_check_id=perceptual_check_id,
    )

    assert checkpointed["state"] == "dual_passed"
    assert int(replay["perceptual_check_id"]) == perceptual_check_id
    assert db.segment_candidate_resume_plan(segment_id, "candidate-policy-v1")["action"] == (
        "promote"
    )
    promoted = db.promote_segment_candidate(
        candidate_id,
        validated_wav_sha256=candidate_sha256,
        repair_action="clarity_repair",
        attempt=1,
    )
    final_check = db.latest_quality_check(
        scope=QUALITY_SCOPE_SEGMENT,
        stage=SEGMENT_AUDIO_QUALITY_STAGE,
        segment_id=segment_id,
    )
    final_metrics = json.loads(str(final_check["metrics_json"]))

    assert promoted["state"] == "promoted"
    assert db.get_segment(segment_id)["wav_sha256"] == candidate_sha256
    assert db.segment_audio_is_current_qa_verified(
        segment_id,
        candidate_sha256,
        SEGMENT_PERCEPTUAL_QUALITY_STAGE,
    )
    assert final_metrics["perceptual_required"] is True
    assert final_metrics["perceptual_quality_check_id"] == perceptual_check_id
    assert final_metrics["perceptual_evidence"]["verdict"] == "ok"


def test_candidate_perceptual_review_is_terminal_and_advances_same_budget(
    tmp_path: Path,
) -> None:
    db, segment_id, incumbent_sha256, _incumbent_path = _candidate_db(tmp_path)
    candidate, candidate_sha256 = _dual_pass_candidate(
        db,
        segment_id=segment_id,
        incumbent_sha256=incumbent_sha256,
        candidate_path=tmp_path / "candidates" / "perceptual-review.wav",
        generation_seed=221,
        perceptual_required=True,
    )
    candidate_id = int(candidate["id"])
    wrong_pitch_check = _candidate_perceptual_check(
        db,
        segment_id=segment_id,
        artifact_sha256=candidate_sha256,
        verdict="pass",
        perceptual_verdict="ok",
        reason="PERCEPTUAL_OK",
        review_required=False,
        baseline_pitch_semitones=1,
    )
    with pytest.raises(RuntimeError, match="baseline pitch"):
        db.checkpoint_segment_candidate_perceptual(
            candidate_id,
            quality_check_id=wrong_pitch_check,
        )

    review_check = _candidate_perceptual_check(
        db,
        segment_id=segment_id,
        artifact_sha256=candidate_sha256,
        verdict="inconclusive",
        perceptual_verdict="review",
        reason="PERCEPTUAL_NATURALNESS_REVIEW",
        review_required=True,
    )
    reviewed = db.checkpoint_segment_candidate_perceptual(
        candidate_id,
        quality_check_id=review_check,
    )
    plan = db.segment_candidate_resume_plan(segment_id, "candidate-policy-v1")

    assert reviewed["state"] == "dual_failed"
    assert plan == {
        "segment_id": segment_id,
        "policy_hash": "candidate-policy-v1",
        "action": "allocate",
        "candidate_id": None,
        "repair_round": 1,
    }
    with pytest.raises(RuntimeError, match="repair budget differs"):
        db.segment_candidate_resume_plan(segment_id, "candidate-policy-v1", 1)
    with pytest.raises(RuntimeError, match="perceptual requirements"):
        db.allocate_segment_candidate(
            segment_id=segment_id,
            policy_hash="candidate-policy-v1",
            repair_round=1,
            max_repair_rounds=2,
            incumbent_sha256=incumbent_sha256,
            generation_seed=222,
            wav_path=tmp_path / "candidates" / "r1.wav",
            candidates_root=tmp_path / "candidates",
            perceptual_required=False,
        )


def test_candidate_decode_and_promotion_reject_tampered_locked_provenance(
    tmp_path: Path,
) -> None:
    db, segment_id, incumbent_sha256, _incumbent_path = _candidate_db(tmp_path)
    candidate_path = tmp_path / "candidates" / "r0.wav"
    candidate_sha256 = _write_candidate_artifact(candidate_path, "tampered-provenance")
    candidate = db.allocate_segment_candidate(
        segment_id=segment_id,
        policy_hash="candidate-policy-v1",
        repair_round=0,
        max_repair_rounds=2,
        incumbent_sha256=incumbent_sha256,
        generation_seed=301,
        wav_path=candidate_path,
        candidates_root=tmp_path / "candidates",
    )
    candidate_id = int(candidate["id"])
    _checkpoint_candidate_signal(
        db,
        candidate_id,
        repair_round=0,
        generation_seed=301,
        wav_path=candidate_path,
        wav_sha256=candidate_sha256,
    )
    contradictory_check = _candidate_decode_check(
        db,
        segment_id=segment_id,
        artifact_sha256=candidate_sha256,
        repair_round=0,
        generation_seed=301,
        confirmation=False,
        verdict="pass",
        reason="contradictory",
        metrics_overrides={"verdict": "mismatch", "passed": False},
    )
    with pytest.raises(RuntimeError, match="contradicts"):
        db.checkpoint_segment_candidate_decode(
            candidate_id,
            quality_check_id=contradictory_check,
            confirmation=False,
        )
    wrong_voice_check = db.record_quality_check(
        scope=QUALITY_SCOPE_SEGMENT,
        stage=SEGMENT_ASR_DECODE_QUALITY_STAGE,
        segment_id=segment_id,
        artifact_sha256=candidate_sha256,
        policy_hash="candidate-policy-v1",
        policy_version=1,
        verdict="pass",
        metrics={
            "verdict": "pass",
            "passed": True,
            "decode_mode": "beam5",
            "selected": True,
            "delivery_mode": "clarity",
            "repair_round": 0,
            "generation_seed": 301,
            "spoken_text_sha256": "2" * 64,
            "voice_profile_id": 99,
            "pitch_semitones": 0,
            "effective_pitch_semitones": 0,
            "pitch_variant_skipped": False,
            "pitch_variant_mixed": False,
        },
    )
    with pytest.raises(RuntimeError, match="locked provenance"):
        db.checkpoint_segment_candidate_decode(
            candidate_id,
            quality_check_id=wrong_voice_check,
            confirmation=False,
        )
    missing_transcript_check = _candidate_decode_check(
        db,
        segment_id=segment_id,
        artifact_sha256=candidate_sha256,
        repair_round=0,
        generation_seed=301,
        confirmation=False,
        verdict="pass",
        reason="ok",
        metrics_overrides={"transcript": ""},
    )
    with pytest.raises(RuntimeError, match="requires a transcript"):
        db.checkpoint_segment_candidate_decode(
            candidate_id,
            quality_check_id=missing_transcript_check,
            confirmation=False,
        )
    assert db.get_segment_candidate(candidate_id)["state"] == "signal_passed"


@pytest.mark.parametrize("damage", ["missing", "tampered"])
def test_candidate_promotion_invalidates_missing_or_tampered_artifact(
    tmp_path: Path,
    damage: str,
) -> None:
    db, segment_id, incumbent_sha256, _incumbent_path = _candidate_db(tmp_path)
    candidate_path = tmp_path / "candidates" / "damaged.wav"
    candidate_sha256 = _write_candidate_artifact(candidate_path, damage)
    candidate = db.allocate_segment_candidate(
        segment_id=segment_id,
        policy_hash="candidate-policy-v1",
        repair_round=0,
        max_repair_rounds=2,
        incumbent_sha256=incumbent_sha256,
        generation_seed=321,
        wav_path=candidate_path,
        candidates_root=tmp_path / "candidates",
    )
    candidate_id = int(candidate["id"])
    _checkpoint_candidate_signal(
        db,
        candidate_id,
        repair_round=0,
        generation_seed=321,
        wav_path=candidate_path,
        wav_sha256=candidate_sha256,
    )
    for confirmation in (False, True):
        check_id = _candidate_decode_check(
            db,
            segment_id=segment_id,
            artifact_sha256=candidate_sha256,
            repair_round=0,
            generation_seed=321,
            confirmation=confirmation,
            verdict="pass",
            reason="ok",
        )
        db.checkpoint_segment_candidate_decode(
            candidate_id,
            quality_check_id=check_id,
            confirmation=confirmation,
        )
    if damage == "missing":
        candidate_path.unlink()
    else:
        candidate_path.write_bytes(b"tampered-candidate")

    invalid = db.promote_segment_candidate(
        candidate_id,
        validated_wav_sha256=candidate_sha256,
        attempt=1,
    )
    assert invalid["state"] == "invalid"
    expected_failure_text = "missing" if damage == "missing" else "checksum"
    assert expected_failure_text in str(invalid["failure_reason"])
    assert db.get_segment(segment_id)["wav_sha256"] == incumbent_sha256
    assert db.segment_candidate_resume_plan(segment_id, "candidate-policy-v1", 2)["action"] == (
        "allocate"
    )
    replay = db.mark_segment_candidate_invalid(
        candidate_id,
        expected_wav_sha256=candidate_sha256,
        reason=str(invalid["failure_reason"]),
    )
    assert replay["state"] == "invalid"
    with pytest.raises(RuntimeError, match="replay payload"):
        db.mark_segment_candidate_invalid(
            candidate_id,
            expected_wav_sha256=candidate_sha256,
            reason="different invalidation reason",
        )


@pytest.mark.parametrize(
    ("blocking_flag", "signal_overrides", "decode_overrides"),
    [
        (
            "pitch_variant_skipped",
            {"pitch_variant_skipped": 1.0},
            {"pitch_variant_skipped": True},
        ),
        (
            "pitch_variant_mixed",
            {"pitch_variant_mixed": 1.0, "effective_pitch_semitones": None},
            {"pitch_variant_mixed": True, "effective_pitch_semitones": None},
        ),
        ("generation_endpoint_active", {"generation_endpoint_active": 1.0}, {}),
        ("pace_outlier", {"pace_outlier": 1.0}, {}),
    ],
)
def test_candidate_promotion_rejects_blocking_signal_flags(
    tmp_path: Path,
    blocking_flag: str,
    signal_overrides: dict,
    decode_overrides: dict,
) -> None:
    db, segment_id, incumbent_sha256, _incumbent_path = _candidate_db(tmp_path)
    candidate_path = tmp_path / "candidates" / "r0.wav"
    candidate_sha256 = _write_candidate_artifact(
        candidate_path,
        f"blocking-{blocking_flag}",
    )
    candidate = db.allocate_segment_candidate(
        segment_id=segment_id,
        policy_hash="candidate-policy-v1",
        repair_round=0,
        max_repair_rounds=2,
        incumbent_sha256=incumbent_sha256,
        generation_seed=351,
        wav_path=candidate_path,
        candidates_root=tmp_path / "candidates",
    )
    candidate_id = int(candidate["id"])
    _checkpoint_candidate_signal(
        db,
        candidate_id,
        repair_round=0,
        generation_seed=351,
        wav_path=candidate_path,
        wav_sha256=candidate_sha256,
        signal_overrides=signal_overrides,
    )
    for confirmation in (False, True):
        check_id = _candidate_decode_check(
            db,
            segment_id=segment_id,
            artifact_sha256=candidate_sha256,
            repair_round=0,
            generation_seed=351,
            confirmation=confirmation,
            verdict="pass",
            reason="ok",
            metrics_overrides=decode_overrides,
        )
        db.checkpoint_segment_candidate_decode(
            candidate_id,
            quality_check_id=check_id,
            confirmation=confirmation,
        )
    blocked = db.get_segment_candidate(candidate_id)
    assert blocked["state"] == "dual_failed"
    assert blocking_flag in str(blocked["failure_reason"])
    with pytest.raises(RuntimeError, match="before both"):
        db.promote_segment_candidate(
            candidate_id,
            validated_wav_sha256=candidate_sha256,
            attempt=1,
        )
    assert db.get_segment(segment_id)["wav_sha256"] == incumbent_sha256
    assert db.get_segment_candidate(candidate_id)["state"] == "dual_failed"


def test_candidate_exhaustion_keeps_incumbent_and_uses_incumbent_evidence(
    tmp_path: Path,
) -> None:
    db, segment_id, incumbent_sha256, incumbent_path = _candidate_db(tmp_path)
    trigger_check = db.record_quality_check(
        scope=QUALITY_SCOPE_SEGMENT,
        stage=SEGMENT_AUDIO_QUALITY_STAGE,
        segment_id=segment_id,
        artifact_sha256=incumbent_sha256,
        policy_hash="candidate-policy-v1",
        policy_version=1,
        verdict="repair",
        metrics={
            "reason": "ASR_MISMATCH",
            "transcript": "primary transcript",
            "similarity": 0.7,
            "wer": 0.4,
        },
        failure_codes=("ASR_MISMATCH",),
    )
    first = db.allocate_segment_candidate(
        segment_id=segment_id,
        policy_hash="candidate-policy-v1",
        repair_round=0,
        max_repair_rounds=2,
        incumbent_sha256=incumbent_sha256,
        generation_seed=401,
        wav_path=tmp_path / "candidates" / "r0.wav",
        candidates_root=tmp_path / "candidates",
    )
    db.mark_segment_candidate_tts_failed(
        int(first["id"]),
        expected_generation_seed=401,
        error="round zero failed",
    )
    with pytest.raises(RuntimeError, match="every configured"):
        db.finalize_segment_candidate_exhaustion(
            segment_id=segment_id,
            policy_hash="candidate-policy-v1",
            max_repair_rounds=2,
            incumbent_sha256=incumbent_sha256,
            trigger_quality_check_id=trigger_check,
            error="repair exhausted",
            warning_code="ASR_MISMATCH_UNRESOLVED",
        )
    second = db.allocate_segment_candidate(
        segment_id=segment_id,
        policy_hash="candidate-policy-v1",
        repair_round=1,
        max_repair_rounds=2,
        incumbent_sha256=incumbent_sha256,
        generation_seed=402,
        wav_path=tmp_path / "candidates" / "r1.wav",
        candidates_root=tmp_path / "candidates",
    )
    db.mark_segment_candidate_tts_failed(
        int(second["id"]),
        expected_generation_seed=402,
        error="round one failed",
    )
    final_check_id = db.finalize_segment_candidate_exhaustion(
        segment_id=segment_id,
        policy_hash="candidate-policy-v1",
        max_repair_rounds=2,
        incumbent_sha256=incumbent_sha256,
        trigger_quality_check_id=trigger_check,
        error="repair exhausted",
        warning_code="ASR_MISMATCH_UNRESOLVED",
    )
    replay_check_id = db.finalize_segment_candidate_exhaustion(
        segment_id=segment_id,
        policy_hash="candidate-policy-v1",
        max_repair_rounds=2,
        incumbent_sha256=incumbent_sha256,
        trigger_quality_check_id=trigger_check,
        error="repair exhausted",
        warning_code="ASR_MISMATCH_UNRESOLVED",
    )
    final = db.get_segment(segment_id)
    check = db.latest_quality_check(
        scope=QUALITY_SCOPE_SEGMENT,
        stage=SEGMENT_AUDIO_QUALITY_STAGE,
        segment_id=segment_id,
    )
    metrics = json.loads(str(check["metrics_json"]))

    assert replay_check_id == final_check_id
    assert final["wav_path"] == str(incumbent_path.resolve())
    assert final["wav_sha256"] == incumbent_sha256
    assert final["asr_text"] == "primary transcript"
    assert metrics["incumbent_sha256"] == incumbent_sha256
    assert [attempt["state"] for attempt in metrics["candidate_attempts"]] == [
        "tts_failed",
        "tts_failed",
    ]
    for changed_payload in (
        {"error": "different error"},
        {"warning_code": "DIFFERENT_WARNING"},
        {"final_verdict": "inconclusive"},
        {"failure_codes": ("DIFFERENT_FAILURE",)},
    ):
        replay_payload = {
            "segment_id": segment_id,
            "policy_hash": "candidate-policy-v1",
            "max_repair_rounds": 2,
            "incumbent_sha256": incumbent_sha256,
            "trigger_quality_check_id": trigger_check,
            "error": "repair exhausted",
            "warning_code": "ASR_MISMATCH_UNRESOLVED",
            **changed_payload,
        }
        with pytest.raises(RuntimeError, match="replay payload"):
            db.finalize_segment_candidate_exhaustion(**replay_payload)
