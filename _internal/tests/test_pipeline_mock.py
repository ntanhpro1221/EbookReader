from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from ebook_reader.audio_io import atomic_write_wav
from ebook_reader.config import build_settings
from ebook_reader.models import ResourceLevel
from ebook_reader.pipeline import BookPipeline, CriticalResourceStop, unresolved_asr_is_fatal
from ebook_reader.project import create_or_open_project
from ebook_reader.resource_manager import ResourceSnapshot


class FakeTTS:
    def __init__(self, settings, db):
        self.settings = settings
        self.db = db
        self.unload_calls = 0

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

    def synthesize_atomic(self, row, output, seed_salt=""):
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
    assert unresolved_asr_is_fatal({"severe": False}, "warning_continue") is False
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
    settings = build_settings(overrides={
        "analysis": {"enabled": False},
        "asr": {"enabled": False},
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
        return "chapterhash"

    monkeypatch.setattr("ebook_reader.pipeline.assemble_chapter_atomic", fake_chapter)
    monkeypatch.setattr("ebook_reader.pipeline.verify_mp3", lambda path: (path.exists(), "ok"))
    verify_calls = 0
    verified_texts: list[str] = []

    def fake_verify(_verifier, expected, wav_path):
        nonlocal verify_calls
        verify_calls += 1
        verified_texts.append(expected)
        passed = verify_calls > 1
        return {
            "passed": passed,
            "transcript": expected if passed else "sai nội dung",
            "similarity": 1.0 if passed else 0.0,
            "wer": 0.0 if passed else 1.0,
            "reason": "ok" if passed else "ASR_MISMATCH",
            "repairable": True,
        }

    monkeypatch.setattr("ebook_reader.pipeline.WhisperVerifier.verify", fake_verify)

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
