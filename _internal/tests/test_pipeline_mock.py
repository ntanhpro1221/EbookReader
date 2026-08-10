from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from ebook_reader.asr import ASR_INCONCLUSIVE, ASR_MISMATCH, ASR_PASS
from ebook_reader.audio_io import ChapterQualityError, atomic_write_wav
from ebook_reader.config import build_settings
from ebook_reader.database import (
    QUALITY_SCOPE_CHAPTER,
    QUALITY_SCOPE_SEGMENT,
    SEGMENT_AUDIO_QUALITY_STAGE,
)
from ebook_reader.models import ResourceLevel
from ebook_reader.pipeline import BookPipeline, CriticalResourceStop, unresolved_asr_is_fatal
from ebook_reader.project import create_or_open_project
from ebook_reader.quality_policy import (
    ANALYSIS_CASTING_STAGE,
    CHAPTER_QUALITY_STAGE,
    QUALITY_POLICY_VERSION,
    TEXT_SEGMENTATION_STAGE,
    quality_policy_hash,
)
from ebook_reader.resource_manager import ResourceSnapshot


class FakeTTS:
    def __init__(self, settings, db):
        self.settings = settings
        self.db = db
        self.unload_calls = 0
        self.synthesize_calls = 0

    def prepare_voice_presets(self):
        return None

    def unload_idle_models(self, keep_engine=None):
        return None

    def unload_all(self):
        self.unload_calls += 1

    def generation_seed(self, row, seed_salt=""):
        return 1

    def spoken_text(self, row):
        return str(row["text"])

    def synthesize_atomic(self, row, output, seed_salt="", *, repair_short_utterance=False):
        self.synthesize_calls += 1
        audio = np.sin(np.linspace(0, 50, 96000, dtype=np.float32)) * 0.12
        checksum, metrics = atomic_write_wav(
            output,
            audio,
            48000,
            row["text"],
            self.settings,
            segment=row,
        )
        return checksum, metrics, 1


class FakeNotifier:
    def __init__(self):
        self.critical_calls = []

    def notify(self, *_args, **_kwargs):
        return True

    def critical_stop(self, *args, **kwargs):
        self.critical_calls.append((args, kwargs))


def test_severe_asr_mismatch_is_fatal_even_under_warning_policy() -> None:
    assert unresolved_asr_is_fatal({"severe": True}, "warning_continue") is True
    assert unresolved_asr_is_fatal({"passed": False, "severe": False}, "warning_continue") is True
    assert unresolved_asr_is_fatal({"severe": False}, "fail") is True


def test_tts_circuit_breaker_counts_only_consecutive_identical_complete_failures() -> None:
    pipeline = object.__new__(BookPipeline)
    pipeline._last_tts_failure_signature = None
    pipeline._tts_failure_streak = 0

    assert pipeline._record_tts_failure("same error") == 1
    assert pipeline._record_tts_failure("same   error") == 2
    pipeline._reset_tts_failure_streak()
    assert pipeline._record_tts_failure("same error") == 1
    assert pipeline._record_tts_failure("different error") == 1


def test_high_quality_blocks_unreviewed_segment_warnings() -> None:
    pipeline = object.__new__(BookPipeline)
    pipeline.settings = {"quality_profile": "high_quality"}
    rows = [
        {"id": 1, "stable_id": "c1s1", "warning_code": "TTS_SPLIT_RECOVERY"},
        {
            "id": 2,
            "stable_id": "c1s2",
            "warning_code": "LOW_ANALYSIS_CONFIDENCE|TTS_PACE_OUTLIER",
        },
    ]

    assert pipeline._high_quality_blocking_segment_warnings(rows) == [
        {
            "segment_id": 2,
            "stable_id": "c1s2",
            "warning_codes": ["LOW_ANALYSIS_CONFIDENCE", "TTS_PACE_OUTLIER"],
        }
    ]

    pipeline.settings = {"quality_profile": "balanced"}
    assert pipeline._high_quality_blocking_segment_warnings(rows) == []


@pytest.mark.parametrize(
    ("initial_verdict", "initial_reason"),
    [
        (ASR_MISMATCH, "ASR_MISMATCH"),
        (ASR_INCONCLUSIVE, "ASR_TRANSCRIPT_TIMELINE_IMPOSSIBLE"),
    ],
)
def test_successful_confirmation_decode_clears_initial_asr_false_negative(
    tmp_path: Path,
    initial_verdict: str,
    initial_reason: str,
) -> None:
    source = tmp_path / "001.txt"
    expected = "Một câu đủ dài để xác nhận nội dung bằng Whisper lần thứ hai."
    source.write_text(expected, encoding="utf-8")
    settings = build_settings(overrides={"tts": {"min_seconds_per_100_chars": 0.2}})
    paths, db, settings = create_or_open_project(
        [source],
        tmp_path / "out",
        settings,
        "ASR confirmation",
    )
    pipeline = BookPipeline(
        paths=paths,
        db=db,
        settings=settings,
        pause_requested=lambda: False,
        stop_requested=lambda: False,
        emit=lambda _kind, _payload: None,
    )
    pipeline.tts = FakeTTS(settings, db)
    pipeline._recover()
    pipeline._ensure_segments()
    chapter = db.list_chapters()[0]
    row = db.list_segments(chapter_id=int(chapter["id"]))[0]
    wav = pipeline._chunk_path(row)
    audio = np.sin(np.linspace(0, 50, 96_000, dtype=np.float32)) * 0.12
    checksum, metrics = atomic_write_wav(
        wav,
        audio,
        48_000,
        str(row["text"]),
        settings,
        segment=row,
    )
    db.mark_signal_passed(
        int(row["id"]),
        wav_path=wav,
        wav_sha256=checksum,
        duration=float(metrics["duration"]),
        signal=metrics,
    )

    class ScriptedVerifier:
        def __init__(self) -> None:
            self.calls = 0

        def unload(self) -> None:
            return None

        def can_verify_repeated_short(self, _text: str) -> bool:
            return False

        def verify(self, _text: str, _wav: Path, *, confirmation: bool = False):
            self.calls += 1
            if not confirmation:
                return {
                    "passed": False,
                    "verdict": initial_verdict,
                    "transcript": "nội dung nhận nhầm",
                    "similarity": 0.1,
                    "wer": 0.9,
                    "reason": initial_reason,
                    "repairable": True,
                }
            return {
                "passed": True,
                "verdict": ASR_PASS,
                "transcript": expected,
                "similarity": 1.0,
                "wer": 0.0,
                "reason": "ok",
                "repairable": False,
            }

    verifier = ScriptedVerifier()
    pipeline._verify_chapter_audio(chapter, verifier)

    fresh = db.get_segment(int(row["id"]))
    assert verifier.calls == 2
    assert str(fresh["status"]) == "verified"
    assert pipeline.tts.synthesize_calls == 0
    assert db.segment_audio_is_current_qa_verified(
        int(row["id"]),
        str(fresh["wav_sha256"]),
        SEGMENT_AUDIO_QUALITY_STAGE,
    )


def resource_snapshot(free_ram_gb: float) -> ResourceSnapshot:
    return ResourceSnapshot(
        cpu_percent=20.0,
        free_ram_gb=free_ram_gb,
        disk_free_gb=100.0,
        disk_active_percent=5.0,
        gpu_temp_c=70,
        foreground_cpu_percent=5.0,
        foreground_gpu_percent=0.0,
        seconds_since_user_input=30.0,
    )


def test_mock_pipeline_completes_without_interactive_prompt(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "001.txt"
    source.write_text("Rầm! Cánh cửa mở ra.\n\nĐây là một đoạn kể chuyện đủ dài để kiểm tra pipeline.", encoding="utf-8")
    settings = build_settings(profile="balanced", overrides={
        "analysis": {"enabled": False},
        "asr": {
            "enabled": False,
            "required": False,
            "failure_policy": "warning_continue",
        },
        "resources": {"min_free_disk_gb": 0.01, "critical_free_disk_gb": 0.001},
        "tts": {"min_seconds_per_100_chars": 0.2},
    })
    paths, db, settings = create_or_open_project([source], tmp_path / "out", settings, "Test Book")
    pronunciation_passes = 0

    def fake_name_pronunciations(*_args, **_kwargs):
        nonlocal pronunciation_passes
        pronunciation_passes += 1
        return 0

    monkeypatch.setattr(
        "ebook_reader.analysis.OllamaBookAnalyzer.reconcile_name_pronunciations",
        fake_name_pronunciations,
    )

    def fake_chapter(wavs, output, settings, **kwargs):
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(b"ID3" + b"x" * 5000)
        quality = SimpleNamespace(
            to_dict=lambda: {"hard_failures": [], "review_flags": []},
            review_flags=(),
        )
        return SimpleNamespace(checksum="chapterhash", quality=quality)

    monkeypatch.setattr("ebook_reader.pipeline.assemble_chapter_atomic_with_metrics", fake_chapter)
    monkeypatch.setattr("ebook_reader.pipeline.verify_mp3", lambda path: (path.exists(), "ok"))
    verify_calls = 0
    verify_calls_by_path: dict[str, int] = {}
    verified_texts: list[str] = []

    def fake_verify(_verifier, expected, wav_path, *, confirmation=False):
        nonlocal verify_calls
        verify_calls += 1
        path_key = str(wav_path)
        verify_calls_by_path[path_key] = verify_calls_by_path.get(path_key, 0) + 1
        verified_texts.append(expected)
        passed = verify_calls_by_path[path_key] > 2
        return {
            "passed": passed,
            "transcript": expected if passed else "sai nội dung",
            "similarity": 1.0 if passed else 0.0,
            "wer": 0.0 if passed else 1.0,
            "reason": "ok" if passed else "ASR_MISMATCH",
            "repairable": True,
        }

    monkeypatch.setattr("ebook_reader.pipeline.WhisperVerifier.verify", fake_verify)
    monkeypatch.setattr(
        "ebook_reader.pipeline.WhisperVerifier.can_verify_repeated_short",
        lambda _verifier, _expected: False,
    )

    events = []
    pipeline = BookPipeline(
        paths=paths,
        db=db,
        settings=settings,
        pause_requested=lambda: False,
        stop_requested=lambda: False,
        emit=lambda kind, payload: events.append((kind, payload)),
    )
    pipeline.tts = FakeTTS(settings, db)
    pipeline.run()

    assert db.book()["status"] == "completed"
    assert db.list_chapters()[0]["status"] == "completed"
    assert db.casting_is_finalized() is True
    segments = db.list_segments()
    assert int(segments[0]["generation_seed"]) == 1
    assert segments[0]["kind"] == "narration"
    assert segments[0]["text"] == "Rầm! Cánh cửa mở ra."
    assert segments[0]["status"] in {"verified", "warning"}
    assert "Rầm! Cánh cửa mở ra." in verified_texts
    assert any(kind == "chapter_completed" for kind, _ in events)
    progress_labels = [
        str(payload["label"])
        for kind, payload in events
        if kind == "work_progress"
    ]
    assert any(label.startswith("Chuẩn bị và chia văn bản") for label in progress_labels)
    assert any(label.startswith("Tạo audio chapter") for label in progress_labels)
    assert any(label.startswith("Kiểm tra phát âm chapter") for label in progress_labels)
    assert any(label.startswith("Sửa audio chapter") for label in progress_labels)
    assert any(label.startswith("Ghép và kiểm tra MP3 chapter") for label in progress_labels)
    assert pronunciation_passes == 1

    # A full resume/reopen pass must preserve locked voice identities and skip valid output.
    resumed = BookPipeline(
        paths=paths,
        db=db,
        settings=settings,
        pause_requested=lambda: False,
        stop_requested=lambda: False,
        emit=lambda kind, payload: events.append((kind, payload)),
    )
    resumed.tts = FakeTTS(settings, db)
    resumed.run()
    assert pronunciation_passes == 1
    assert db.book()["status"] == "completed"

    # A legacy verified/warning WAV has no policy-bound segment QA evidence. Resume must
    # reuse the valid waveform, rerun ASR, and avoid paying for TTS generation again.
    with db.connect() as conn:
        conn.execute(
            "DELETE FROM quality_checks WHERE scope=?",
            (QUALITY_SCOPE_SEGMENT,),
        )
        legacy_segments = list(conn.execute("SELECT id,seq FROM segments ORDER BY seq"))
        for legacy_segment in legacy_segments:
            status = "verified" if int(legacy_segment["seq"]) % 2 == 0 else "warning"
            warning = None if status == "verified" else "ASR_TRANSCRIPT_TIMELINE_IMPOSSIBLE"
            conn.execute(
                "UPDATE segments SET status=?,warning_code=? WHERE id=?",
                (status, warning, int(legacy_segment["id"])),
            )
        conn.execute("UPDATE chapters SET status='failed'")
        conn.execute("UPDATE book SET status='error',stage='completed_with_errors'")

    calls_before_legacy_resume = verify_calls
    legacy_resume = BookPipeline(
        paths=paths,
        db=db,
        settings=settings,
        pause_requested=lambda: False,
        stop_requested=lambda: False,
        emit=lambda kind, payload: events.append((kind, payload)),
    )
    legacy_resume.tts = FakeTTS(settings, db)
    legacy_resume.run()

    assert legacy_resume.tts.synthesize_calls == 0
    assert verify_calls > calls_before_legacy_resume
    for segment in db.list_segments():
        assert db.segment_audio_is_current_qa_verified(
            int(segment["id"]),
            str(segment["wav_sha256"]),
            SEGMENT_AUDIO_QUALITY_STAGE,
        )
        assert "ASR_TRANSCRIPT_TIMELINE_IMPOSSIBLE" not in str(segment["warning_code"] or "")


def test_completed_with_errors_notifies_and_emits_error_state(tmp_path: Path) -> None:
    source = tmp_path / "001.txt"
    source.write_text("Nội dung chapter sẽ được đánh dấu lỗi.", encoding="utf-8")
    settings = build_settings()
    paths, db, settings = create_or_open_project([source], tmp_path / "out", settings, "Test Book")
    chapter = db.list_chapters()[0]
    db.update_chapter_status(int(chapter["id"]), "failed", error="segment lỗi")
    events = []
    notifier = FakeNotifier()
    pipeline = BookPipeline(
        paths=paths,
        db=db,
        settings=settings,
        pause_requested=lambda: False,
        stop_requested=lambda: False,
        emit=lambda kind, payload: events.append((kind, payload)),
    )
    pipeline.notifier = notifier

    pipeline._finalize_book()

    book = db.book()
    assert book["status"] == "error"
    assert book["stage"] == "completed_with_errors"
    assert len(notifier.critical_calls) == 1
    assert any(
        kind == "state" and payload["state"] == "error"
        for kind, payload in events
    )


def test_resume_rejects_segments_from_a_different_parser_fingerprint(tmp_path: Path) -> None:
    source = tmp_path / "001.txt"
    source.write_text("Nội dung đủ dài để kiểm tra fingerprint parser.", encoding="utf-8")
    settings = build_settings()
    paths, db, settings = create_or_open_project(
        [source],
        tmp_path / "out",
        settings,
        "Parser fingerprint",
    )
    original = BookPipeline(
        paths=paths,
        db=db,
        settings=settings,
        pause_requested=lambda: False,
        stop_requested=lambda: False,
        emit=lambda _kind, _payload: None,
    )
    original._recover()
    original._ensure_segments()

    changed = BookPipeline(
        paths=paths,
        db=db,
        settings=settings,
        pause_requested=lambda: False,
        stop_requested=lambda: False,
        emit=lambda _kind, _payload: None,
    )
    changed.quality_policy["stage_fingerprints"][TEXT_SEGMENTATION_STAGE] = "changed"
    changed.quality_policy_hash = quality_policy_hash(changed.quality_policy)

    with pytest.raises(RuntimeError, match="Text segmentation implementation changed"):
        changed._recover()


def test_resume_rejects_locked_casting_from_a_different_fingerprint(tmp_path: Path) -> None:
    source = tmp_path / "001.txt"
    source.write_text("Nội dung đủ dài để kiểm tra fingerprint casting.", encoding="utf-8")
    settings = build_settings()
    paths, db, settings = create_or_open_project(
        [source],
        tmp_path / "out",
        settings,
        "Casting fingerprint",
    )
    original = BookPipeline(
        paths=paths,
        db=db,
        settings=settings,
        pause_requested=lambda: False,
        stop_requested=lambda: False,
        emit=lambda _kind, _payload: None,
    )
    original._recover()
    original._ensure_segments()
    db.finalize_casting()

    changed = BookPipeline(
        paths=paths,
        db=db,
        settings=settings,
        pause_requested=lambda: False,
        stop_requested=lambda: False,
        emit=lambda _kind, _payload: None,
    )
    changed.quality_policy["stage_fingerprints"][ANALYSIS_CASTING_STAGE] = "changed"
    changed.quality_policy_hash = quality_policy_hash(changed.quality_policy)

    with pytest.raises(RuntimeError, match="Analysis/casting implementation changed"):
        changed._recover()


def test_chapter_quality_failure_is_checkpointed_and_later_chapters_continue(
    tmp_path: Path,
    monkeypatch,
) -> None:
    sources = []
    for index in range(2):
        source = tmp_path / f"{index:03d}.txt"
        source.write_text(f"Nội dung chapter {index + 1} đủ dài để kiểm tra.", encoding="utf-8")
        sources.append(source)
    settings = build_settings()
    paths, db, settings = create_or_open_project(
        sources,
        tmp_path / "out",
        settings,
        "Quality containment",
    )
    events = []
    pipeline = BookPipeline(
        paths=paths,
        db=db,
        settings=settings,
        pause_requested=lambda: False,
        stop_requested=lambda: False,
        emit=lambda kind, payload: events.append((kind, payload)),
    )
    db.set_current_quality_policy(
        policy_hash=pipeline.quality_policy_hash,
        policy_version=QUALITY_POLICY_VERSION,
        policy=pipeline.quality_policy,
    )
    processed: list[int] = []

    def fail_first_chapter(chapter, _verifier) -> None:
        chapter_index = int(chapter["chapter_index"])
        processed.append(chapter_index)
        if chapter_index == 1:
            raise ChapterQualityError(
                "forced perceptual review",
                artifact_sha256="f" * 64,
                metrics={"review_flags": ["join discontinuity"]},
                failure_codes=("CHAPTER_QA_REVIEW_REQUIRED",),
                review_required=True,
            )
        db.update_chapter_status(int(chapter["id"]), "completed")

    monkeypatch.setattr(pipeline, "_process_chapter", fail_first_chapter)

    pipeline._process_all_chapters(SimpleNamespace())

    chapters = db.list_chapters()
    assert processed == [1, 2]
    assert [str(chapter["status"]) for chapter in chapters] == ["failed", "completed"]
    assert "forced perceptual review" in str(chapters[0]["last_error"])
    failure = db.latest_quality_check(
        scope=QUALITY_SCOPE_CHAPTER,
        stage=CHAPTER_QUALITY_STAGE,
        chapter_id=int(chapters[0]["id"]),
    )
    assert failure is not None
    assert failure["verdict"] == "fail"
    assert failure["artifact_sha256"] == "f" * 64
    assert failure["failure_codes_json"] == '["CHAPTER_QA_REVIEW_REQUIRED"]'
    assert json.loads(str(failure["metrics_json"]))["review_required"] is True
    assert any(kind == "chapter_failed" for kind, _payload in events)
    assert len([kind for kind, _payload in events if kind == "chapter_progress"]) == 2

    pipeline._export_reports()
    chapter_report = json.loads(
        (paths.reports / "chapter_quality.json").read_text(encoding="utf-8")
    )
    assert len(chapter_report) == 2
    assert chapter_report[0]["status"] == "failed"
    assert chapter_report[0]["artifact_verified"] is False
    assert chapter_report[0]["current_policy_verified"] is False
    assert chapter_report[0]["latest_quality_check"]["verdict"] == "fail"
    assert chapter_report[0]["latest_quality_check"]["metrics"]["review_required"] is True
    assert chapter_report[1]["status"] == "completed"
    quality_report = json.loads(
        (paths.reports / "audiobook_quality_report.json").read_text(encoding="utf-8")
    )
    assert quality_report["schema_version"] == 1
    assert quality_report["book"]["chapters_total"] == 2
    assert quality_report["book"]["failed"] == 1
    assert len(quality_report["review_required"]["chapters"]) == 2

    resumed: list[int] = []

    def complete_failed_chapter(chapter, _verifier) -> None:
        if str(chapter["status"]) == "completed":
            return
        resumed.append(int(chapter["chapter_index"]))
        db.update_chapter_status(int(chapter["id"]), "completed")

    monkeypatch.setattr(pipeline, "_process_chapter", complete_failed_chapter)
    pipeline._process_all_chapters(SimpleNamespace())

    assert resumed == [1]
    assert [str(chapter["status"]) for chapter in db.list_chapters()] == [
        "completed",
        "completed",
    ]


def test_critical_ram_unloads_models_and_continues_after_recovery(
    tmp_path: Path,
    monkeypatch,
) -> None:
    source = tmp_path / "001.txt"
    source.write_text("Nội dung kiểm tra phục hồi RAM.", encoding="utf-8")
    settings = build_settings()
    paths, db, settings = create_or_open_project([source], tmp_path / "out", settings, "Test Book")
    events = []
    notifier = FakeNotifier()
    pipeline = BookPipeline(
        paths=paths,
        db=db,
        settings=settings,
        pause_requested=lambda: False,
        stop_requested=lambda: False,
        emit=lambda kind, payload: events.append((kind, payload)),
    )
    pipeline.tts = FakeTTS(settings, db)
    pipeline.notifier = notifier
    snapshots = iter((resource_snapshot(0.8), resource_snapshot(8.0)))
    monkeypatch.setattr(pipeline.resources, "snapshot", lambda force=False: next(snapshots))
    monkeypatch.setattr("ebook_reader.pipeline.time.sleep", lambda _seconds: None)

    decision = pipeline._resource_gate("chapter 1 segment 75", keep_engine="vieneu")

    assert decision.level != ResourceLevel.CRITICAL_STOP
    assert decision.critical is False
    assert decision.allow_new_gpu_batch is True
    assert pipeline.tts.unload_calls == 1
    assert notifier.critical_calls == []
    assert db.book()["status"] != "stopped"
    assert any(
        kind == "log" and "0.8 → 8.0 GB" in str(payload["text"])
        for kind, payload in events
    )


def test_critical_ram_stops_only_when_recovery_is_insufficient(
    tmp_path: Path,
    monkeypatch,
) -> None:
    source = tmp_path / "001.txt"
    source.write_text("Nội dung kiểm tra RAM vẫn thiếu.", encoding="utf-8")
    settings = build_settings()
    paths, db, settings = create_or_open_project([source], tmp_path / "out", settings, "Test Book")
    notifier = FakeNotifier()
    pipeline = BookPipeline(
        paths=paths,
        db=db,
        settings=settings,
        pause_requested=lambda: False,
        stop_requested=lambda: False,
        emit=lambda _kind, _payload: None,
    )
    pipeline.tts = FakeTTS(settings, db)
    pipeline.notifier = notifier
    snapshots = iter((resource_snapshot(0.8), resource_snapshot(0.7)))
    monkeypatch.setattr(pipeline.resources, "snapshot", lambda force=False: next(snapshots))
    monkeypatch.setattr("ebook_reader.pipeline.time.sleep", lambda _seconds: None)

    with pytest.raises(CriticalResourceStop, match="available RAM 0.7 GB"):
        pipeline._resource_gate("chapter 1 segment 75", keep_engine="vieneu")

    assert pipeline.tts.unload_calls == 1
    assert db.book()["status"] == "stopped"
    assert db.book()["stage"] == "critical_stop"
    assert len(notifier.critical_calls) == 1
