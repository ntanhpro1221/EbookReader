from __future__ import annotations

from pathlib import Path

import numpy as np

from ebook_reader.audio_io import atomic_write_wav
from ebook_reader.config import build_settings
from ebook_reader.pipeline import BookPipeline
from ebook_reader.project import create_or_open_project


class FakeTTS:
    def __init__(self, settings, db):
        self.settings = settings
        self.db = db

    def prepare_voice_presets(self):
        return None

    def unload_idle_models(self, keep_engine=None):
        return None

    def unload_all(self):
        return None

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
    assert segments[0]["kind"] == "text_sfx"
    assert segments[0]["status"] in {"verified", "warning"}
    assert "Rầm!" not in verified_texts
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
    monkeypatch.setattr(
        "ebook_reader.analysis.OllamaBookAnalyzer.reconcile_aliases",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("casting ran again")),
    )
    resumed.run()
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
