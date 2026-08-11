from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from ebook_reader.audio_io import atomic_write_wav
from ebook_reader.background_runner import BACKGROUND_DIRECTORY
from ebook_reader.config import build_settings, settings_hash
from ebook_reader.database import (
    CHAPTER_POST_ENCODE_QUALITY_STAGE,
    QUALITY_SCOPE_CHAPTER,
    QUALITY_SCOPE_SEGMENT,
    QUALITY_VERDICT_PASS,
    SEGMENT_AUDIO_QUALITY_STAGE,
    SEGMENT_PERCEPTUAL_QUALITY_STAGE,
    ProjectDB,
)
from ebook_reader.io_utils import sha256_file
from ebook_reader.models import ProjectPaths
from ebook_reader.recovery import RecoveryError, recover_project


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
            "input_sha256": sha256_file(source),
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


def test_recovery_never_deletes_background_control_part_files(tmp_path: Path) -> None:
    paths, settings, db, _row = setup_db(tmp_path)
    control_root = paths.root / BACKGROUND_DIRECTORY
    control_root.mkdir(parents=True, exist_ok=True)
    active_control_write = control_root / "state.json.part"
    active_control_write.write_text("in progress", encoding="utf-8")
    abandoned_audio_write = paths.work / "orphan.wav.part"
    abandoned_audio_write.write_bytes(b"partial")

    report = recover_project(paths, db, settings)

    assert active_control_write.is_file()
    assert not abandoned_audio_write.exists()
    assert report.removed_part_files == 1


def complete_project_with_current_qa(paths, settings, db, row):
    wav = paths.chunks / "chapter_00001" / "0000000.wav"
    audio = np.sin(np.linspace(0, 30, 48_000, dtype=np.float32)) * 0.1
    wav_checksum, metrics = atomic_write_wav(wav, audio, 48_000, row["text"], settings)
    db.mark_signal_passed(
        int(row["id"]),
        wav_path=wav,
        wav_sha256=wav_checksum,
        duration=metrics["duration"],
        signal=metrics,
    )
    db.mark_verified(int(row["id"]))
    db.set_current_quality_policy(
        policy_hash="quality-v1",
        policy_version=1,
        policy={"profile": "audiobook"},
    )
    quality = db.quality_metadata_for_current_policy()
    db.record_quality_check(
        scope=QUALITY_SCOPE_SEGMENT,
        stage=SEGMENT_AUDIO_QUALITY_STAGE,
        artifact_sha256=wav_checksum,
        policy_hash=str(quality["policy_hash"]),
        policy_version=int(quality["policy_version"]),
        verdict=QUALITY_VERDICT_PASS,
        segment_id=int(row["id"]),
    )
    db.record_quality_check(
        scope=QUALITY_SCOPE_SEGMENT,
        stage=SEGMENT_PERCEPTUAL_QUALITY_STAGE,
        artifact_sha256=wav_checksum,
        policy_hash=str(quality["policy_hash"]),
        policy_version=int(quality["policy_version"]),
        verdict=QUALITY_VERDICT_PASS,
        segment_id=int(row["id"]),
    )
    chapter = db.list_chapters()[0]
    chapter_output = Path(str(chapter["output_mp3"]))
    chapter_output.parent.mkdir(parents=True, exist_ok=True)
    chapter_output.write_bytes(b"ID3" + b"c" * 5000)
    chapter_checksum = sha256_file(chapter_output)
    db.record_quality_check(
        scope=QUALITY_SCOPE_CHAPTER,
        stage=CHAPTER_POST_ENCODE_QUALITY_STAGE,
        artifact_sha256=chapter_checksum,
        policy_hash=str(quality["policy_hash"]),
        policy_version=int(quality["policy_version"]),
        verdict=QUALITY_VERDICT_PASS,
        chapter_id=int(chapter["id"]),
    )
    db.register_artifact(
        artifact_key=f"chapter_mp3:{chapter['chapter_index']}",
        kind="chapter_mp3",
        path=chapter_output,
        sha256=chapter_checksum,
        verified=True,
        metadata={"quality": quality},
    )
    db.update_chapter_status(int(chapter["id"]), "completed")
    db.update_book(status="completed", stage="completed")
    return chapter


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


def test_recovery_resets_committed_wav_with_wrong_sample_rate(tmp_path: Path) -> None:
    paths, settings, db, row = setup_db(tmp_path)
    wav = paths.chunks / "wrong-rate.wav"
    wav.parent.mkdir(parents=True, exist_ok=True)
    audio = np.sin(np.linspace(0, 30, 24_000, dtype=np.float32)) * 0.1
    sf.write(wav, audio, 24_000, subtype="PCM_16")
    checksum = sha256_file(wav)
    db.mark_signal_passed(
        int(row["id"]),
        wav_path=wav,
        wav_sha256=checksum,
        duration=1.0,
        signal={"duration": 1.0, "rms": 0.1},
    )
    db.mark_verified(int(row["id"]))

    report = recover_project(paths, db, settings)

    fresh = db.list_segments()[0]
    assert report.reset_missing_or_corrupt == 1
    assert fresh["status"] == "pending"
    assert fresh["wav_path"] is None
    assert fresh["wav_sha256"] is None


def test_recovery_resets_segment_killed_during_atomic_wav_write(tmp_path: Path) -> None:
    paths, settings, db, row = setup_db(tmp_path)
    db.mark_generating(int(row["id"]), seed=1234)
    part = paths.chunks / "chapter_00001" / "0000000.part.wav"
    part.parent.mkdir(parents=True, exist_ok=True)
    part.write_bytes(b"incomplete wav")

    report = recover_project(paths, db, settings)

    fresh = db.list_segments()[0]
    assert report.reset_in_progress == 1
    assert fresh["status"] == "pending"
    assert fresh["wav_path"] is None
    assert fresh["wav_sha256"] is None
    assert not part.exists()


def test_recovery_does_not_trust_wav_replaced_before_sqlite_commit(tmp_path: Path) -> None:
    paths, settings, db, row = setup_db(tmp_path)
    wav = paths.chunks / "chapter_00001" / "0000000.wav"
    audio = np.sin(np.linspace(0, 30, 48000, dtype=np.float32)) * 0.1
    db.mark_generating(int(row["id"]), seed=5678)
    atomic_write_wav(wav, audio, 48000, row["text"], settings)

    report = recover_project(paths, db, settings)

    fresh = db.list_segments()[0]
    assert report.reset_in_progress == 1
    assert fresh["status"] == "pending"
    assert fresh["wav_path"] is None
    assert wav.exists()


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
    monkeypatch.setattr("ebook_reader.recovery.verify_mp3", lambda _path: (True, "ok"))

    report = recover_project(paths, db, settings)

    assert report.invalid_mp3 == 1
    assert db.list_chapters()[0]["status"] == "warning"


def test_completed_project_uses_verified_mp3_fast_path(tmp_path: Path, monkeypatch) -> None:
    paths, settings, db, row = setup_db(tmp_path)
    complete_project_with_current_qa(paths, settings, db, row)
    monkeypatch.setattr("ebook_reader.recovery.verify_mp3", lambda _path: (True, "ok"))
    monkeypatch.setattr(
        "ebook_reader.recovery.inspect_wav",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("deep recovery ran")),
    )

    report = recover_project(paths, db, settings)

    assert report.completed_verified is True


def test_completed_project_without_perceptual_evidence_is_requeued(tmp_path: Path, monkeypatch) -> None:
    paths, settings, db, row = setup_db(tmp_path)
    complete_project_with_current_qa(paths, settings, db, row)
    with db.connect() as conn:
        conn.execute(
            "DELETE FROM quality_checks WHERE scope=? AND stage=?",
            (QUALITY_SCOPE_SEGMENT, SEGMENT_PERCEPTUAL_QUALITY_STAGE),
        )
    monkeypatch.setattr("ebook_reader.recovery.verify_mp3", lambda _path: (True, "ok"))

    report = recover_project(paths, db, settings)

    assert report.completed_verified is False
    assert report.requeued_asr == 1
    assert db.get_segment(int(row["id"]))["status"] == "signal_passed"
    assert report.recovered_verified == 0


@pytest.mark.parametrize(
    ("source_mutation", "expected_error"),
    [
        ("missing", "Source chapter is missing"),
        ("size_change", "Source chapter size changed"),
        ("same_size_content_change", "Source chapter content changed"),
    ],
)
def test_completed_fast_path_rejects_missing_or_changed_source(
    tmp_path: Path,
    monkeypatch,
    source_mutation: str,
    expected_error: str,
) -> None:
    paths, settings, db, row = setup_db(tmp_path)
    chapter = complete_project_with_current_qa(paths, settings, db, row)
    source = Path(str(chapter["input_path"]))
    original = source.read_bytes()
    if source_mutation == "missing":
        source.unlink()
    elif source_mutation == "size_change":
        source.write_bytes(original + b"changed")
    else:
        source.write_bytes(bytes([original[0] ^ 1]) + original[1:])
        assert source.stat().st_size == len(original)
    monkeypatch.setattr(
        "ebook_reader.recovery.verify_mp3",
        lambda _path: (_ for _ in ()).throw(AssertionError("MP3 validation ran first")),
    )

    with pytest.raises(RecoveryError, match=expected_error):
        recover_project(paths, db, settings)


def test_completed_project_without_current_quality_metadata_is_not_fast_pathed(
    tmp_path: Path,
    monkeypatch,
) -> None:
    paths, settings, db, row = setup_db(tmp_path)
    wav = paths.chunks / "chapter_00001" / "0000000.wav"
    audio = np.sin(np.linspace(0, 30, 48_000, dtype=np.float32)) * 0.1
    checksum, metrics = atomic_write_wav(wav, audio, 48_000, row["text"], settings)
    db.mark_signal_passed(
        int(row["id"]),
        wav_path=wav,
        wav_sha256=checksum,
        duration=metrics["duration"],
        signal=metrics,
    )
    db.mark_verified(int(row["id"]))
    db.set_current_quality_policy(
        policy_hash="quality-v2",
        policy_version=2,
        policy={"profile": "audiobook", "true_peak_db": -2.0},
    )
    quality = db.quality_metadata_for_current_policy()
    db.record_quality_check(
        scope=QUALITY_SCOPE_SEGMENT,
        stage=SEGMENT_AUDIO_QUALITY_STAGE,
        artifact_sha256=checksum,
        policy_hash=str(quality["policy_hash"]),
        policy_version=int(quality["policy_version"]),
        verdict=QUALITY_VERDICT_PASS,
        segment_id=int(row["id"]),
    )
    db.record_quality_check(
        scope=QUALITY_SCOPE_SEGMENT,
        stage=SEGMENT_PERCEPTUAL_QUALITY_STAGE,
        artifact_sha256=checksum,
        policy_hash=str(quality["policy_hash"]),
        policy_version=int(quality["policy_version"]),
        verdict=QUALITY_VERDICT_PASS,
        segment_id=int(row["id"]),
    )
    chapter = db.list_chapters()[0]
    chapter_output = Path(str(chapter["output_mp3"]))
    chapter_output.parent.mkdir(parents=True, exist_ok=True)
    chapter_output.write_bytes(b"ID3" + b"c" * 5000)
    db.register_artifact(
        artifact_key=f"chapter_mp3:{chapter['chapter_index']}",
        kind="chapter_mp3",
        path=chapter_output,
        sha256=sha256_file(chapter_output),
        verified=True,
        metadata={
            "quality": {
                "policy_hash": "quality-v1",
                "policy_version": 1,
                "verdict": "pass",
            }
        },
    )
    db.update_chapter_status(int(chapter["id"]), "completed")
    db.update_book(status="completed", stage="completed")
    monkeypatch.setattr("ebook_reader.recovery.verify_mp3", lambda _path: (True, "ok"))

    report = recover_project(paths, db, settings)

    assert report.completed_verified is False
    assert report.invalid_mp3 == 1
    updated = db.list_chapters()[0]
    assert updated["status"] == "warning"
    assert "current locked quality policy" in str(updated["last_error"])


def test_recovery_requeues_legacy_verified_wav_for_asr_without_resetting_audio(
    tmp_path: Path,
) -> None:
    paths, settings, db, row = setup_db(tmp_path)
    wav = paths.chunks / "chapter_00001" / "0000000.wav"
    audio = np.sin(np.linspace(0, 30, 48_000, dtype=np.float32)) * 0.1
    checksum, metrics = atomic_write_wav(wav, audio, 48_000, row["text"], settings)
    db.mark_signal_passed(
        int(row["id"]),
        wav_path=wav,
        wav_sha256=checksum,
        duration=metrics["duration"],
        signal=metrics,
        generation_seed=17,
    )
    db.set_segment_warning_code(int(row["id"]), "LOW_ANALYSIS_CONFIDENCE")
    db.set_segment_warning_code(int(row["id"]), "TTS_PACE_OUTLIER")
    db.mark_asr_result(
        int(row["id"]),
        passed=False,
        transcript="sai nội dung",
        similarity=0.1,
        wer=1.0,
        warning_code="ASR_MISMATCH_UNRESOLVED",
    )
    db.mark_verified(int(row["id"]))
    db.set_current_quality_policy(
        policy_hash="quality-v1",
        policy_version=1,
        policy={"profile": "audiobook"},
    )
    before = dict(db.get_segment(int(row["id"])))

    report = recover_project(paths, db, settings)

    updated = db.get_segment(int(row["id"]))
    assert report.requeued_asr == 1
    assert report.reset_missing_or_corrupt == 0
    assert updated["status"] == "signal_passed"
    assert updated["wav_path"] == before["wav_path"]
    assert updated["wav_sha256"] == before["wav_sha256"]
    assert updated["wav_duration"] == before["wav_duration"]
    assert updated["signal_json"] == before["signal_json"]
    assert updated["generation_seed"] == before["generation_seed"]
    assert updated["attempt_count"] == before["attempt_count"]
    assert updated["asr_text"] is None
    assert updated["asr_similarity"] is None
    assert updated["asr_wer"] is None
    assert updated["warning_code"] == "LOW_ANALYSIS_CONFIDENCE|TTS_PACE_OUTLIER"
    assert "current locked quality policy" in str(updated["error"])


def test_recovery_preserves_incumbent_and_exposes_candidate_resume_plan(tmp_path: Path) -> None:
    paths, settings, db, row = setup_db(tmp_path)
    profile_id = db.upsert_voice_profile(
        {
            "voice_key": "recovery-candidate-voice",
            "engine": "vieneu",
            "preset_name": "Recovery Candidate",
            "description": "Recovery candidate test voice",
            "seed": 9,
            "pitch_semitones": 0,
            "status": "ready",
        }
    )
    with db.connect() as conn:
        conn.execute(
            "UPDATE segments SET voice_profile_id=? WHERE id=?",
            (profile_id, int(row["id"])),
        )
    wav = paths.chunks / "chapter_00001" / "0000000.wav"
    audio = np.sin(np.linspace(0, 30, 48_000, dtype=np.float32)) * 0.1
    wav_sha256, metrics = atomic_write_wav(wav, audio, 48_000, row["text"], settings)
    db.mark_signal_passed(
        int(row["id"]),
        wav_path=wav,
        wav_sha256=wav_sha256,
        duration=float(metrics["duration"]),
        signal=metrics,
        generation_seed=11,
    )
    db.set_current_quality_policy(
        policy_hash="candidate-recovery-policy",
        policy_version=1,
        policy={"asr": {"repair_rounds": int(settings["asr"]["repair_rounds"])}},
    )
    candidate = db.allocate_segment_candidate(
        segment_id=int(row["id"]),
        policy_hash="candidate-recovery-policy",
        repair_round=0,
        max_repair_rounds=int(settings["asr"]["repair_rounds"]),
        incumbent_sha256=wav_sha256,
        generation_seed=21,
        wav_path=paths.work / "candidates" / "c1s1" / "r0.wav",
        candidates_root=paths.work / "candidates",
    )
    db.mark_generating(
        int(row["id"]),
        seed=21,
        delivery_mode="clarity",
        repair_round=0,
        policy_hash="candidate-recovery-policy",
    )

    report = recover_project(paths, db, settings)
    recovered = db.get_segment(int(row["id"]))

    assert report.reset_in_progress == 0
    assert recovered["status"] == "signal_passed"
    assert recovered["wav_path"] == str(wav.resolve())
    assert recovered["wav_sha256"] == wav_sha256
    assert report.candidate_resume_plans == [
        {
            "segment_id": int(row["id"]),
            "policy_hash": "candidate-recovery-policy",
            "action": "generate",
            "candidate_id": int(candidate["id"]),
            "repair_round": 0,
            "state": "generating",
            "generation_seed": 21,
            "tts_attempt": 0,
            "wav_path": str((paths.work / "candidates" / "c1s1" / "r0.wav").resolve()),
            "wav_sha256": "",
        }
    ]


def test_recovery_invalidates_corrupt_candidate_and_advances_round(tmp_path: Path) -> None:
    paths, settings, db, row = setup_db(tmp_path)
    profile_id = db.upsert_voice_profile(
        {
            "voice_key": "recovery-corrupt-candidate",
            "engine": "vieneu",
            "preset_name": "Recovery Candidate",
            "description": "Recovery corrupt candidate test voice",
            "seed": 10,
            "pitch_semitones": 0,
            "status": "ready",
        }
    )
    with db.connect() as conn:
        conn.execute(
            "UPDATE segments SET voice_profile_id=? WHERE id=?",
            (profile_id, int(row["id"])),
        )
    incumbent = paths.chunks / "chapter_00001" / "0000000.wav"
    audio = np.sin(np.linspace(0, 30, 48_000, dtype=np.float32)) * 0.1
    incumbent_sha256, incumbent_metrics = atomic_write_wav(
        incumbent,
        audio,
        48_000,
        row["text"],
        settings,
    )
    db.mark_signal_passed(
        int(row["id"]),
        wav_path=incumbent,
        wav_sha256=incumbent_sha256,
        duration=float(incumbent_metrics["duration"]),
        signal=incumbent_metrics,
        generation_seed=31,
    )
    db.set_current_quality_policy(
        policy_hash="candidate-corrupt-policy",
        policy_version=1,
        policy={"asr": {"repair_rounds": int(settings["asr"]["repair_rounds"])}},
    )
    candidate_path = paths.work / "candidates" / "c1s1" / "r0.wav"
    candidate_path.parent.mkdir(parents=True, exist_ok=True)
    candidate_path.write_bytes(b"candidate-before-corruption")
    candidate_sha256 = sha256_file(candidate_path)
    candidate = db.allocate_segment_candidate(
        segment_id=int(row["id"]),
        policy_hash="candidate-corrupt-policy",
        repair_round=0,
        max_repair_rounds=int(settings["asr"]["repair_rounds"]),
        incumbent_sha256=incumbent_sha256,
        generation_seed=32,
        wav_path=candidate_path,
        candidates_root=paths.work / "candidates",
    )
    db.checkpoint_segment_candidate_signal(
        int(candidate["id"]),
        expected_generation_seed=32,
        wav_path=candidate_path,
        wav_sha256=candidate_sha256,
        duration=1.0,
        signal={
            "duration": 1.0,
            "tts_delivery_mode": "clarity",
            "asr_clarity_repair_round": 0,
            "spoken_text_sha256": "1" * 64,
            "voice_profile_id": profile_id,
            "pitch_semitones": 0,
            "effective_pitch_semitones": 0,
            "pitch_variant_skipped": False,
            "pitch_variant_mixed": False,
        },
    )
    candidate_path.write_bytes(b"candidate-after-corruption")

    report = recover_project(paths, db, settings)

    assert report.invalidated_candidates == 1
    assert db.get_segment_candidate(int(candidate["id"]))["state"] == "invalid"
    assert db.get_segment(int(row["id"]))["wav_sha256"] == incumbent_sha256
    assert report.candidate_resume_plans == [
        {
            "segment_id": int(row["id"]),
            "policy_hash": "candidate-corrupt-policy",
            "action": "allocate",
            "candidate_id": None,
            "repair_round": 1,
        }
    ]
