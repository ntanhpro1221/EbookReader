from __future__ import annotations

from pathlib import Path

import numpy as np

from e_book_reader.audio_io import atomic_write_wav
from e_book_reader.config import build_settings
from e_book_reader.pipeline import BookPipeline
from e_book_reader.project import create_or_open_project


class FakeTTS:
    def __init__(self, settings, db):
        self.settings = settings
        self.db = db

    def prepare_voice_references(self, stop_requested, before_profile=None):
        return None

    def unload_idle_models(self, keep_engine=None):
        return None

    def unload_all(self):
        return None

    def generation_seed(self, row, seed_salt=""):
        return 1

    def spoken_text(self, row):
        return str(row["text"])

    def synthesize_vieneu_batch_atomic(self, rows, outputs, batch_size):
        results = []
        for row, output in zip(rows, outputs):
            audio = np.sin(np.linspace(0, 50, 96000, dtype=np.float32)) * 0.12
            checksum, metrics = atomic_write_wav(output, audio, 48000, row["text"], self.settings)
            results.append((checksum, metrics, 1))
        return results

    def synthesize_atomic(self, row, output, seed_salt=""):
        audio = np.sin(np.linspace(0, 50, 96000, dtype=np.float32)) * 0.12
        checksum, metrics = atomic_write_wav(output, audio, 48000, row["text"], self.settings)
        return checksum, metrics, 1

    def fallback_atomic(self, row, output):
        return self.synthesize_atomic(row, output, "fallback")


def test_mock_pipeline_completes_without_interactive_prompt(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "001.txt"
    source.write_text("Đây là một đoạn kể chuyện đủ dài để kiểm tra pipeline.", encoding="utf-8")
    settings = build_settings(overrides={
        "analysis": {"enabled": False},
        "asr": {"enabled": False},
        "audio": {"combine_full_book": True},
        "resources": {"pause_on_battery": False, "min_free_disk_gb": 0.01, "critical_free_disk_gb": 0.001},
        "tts": {"min_seconds_per_100_chars": 0.2},
    })
    paths, db, settings = create_or_open_project([source], tmp_path / "out", settings, "Test Book")

    def fake_chapter(wavs, output, settings, **kwargs):
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(b"ID3" + b"x" * 5000)
        return "chapterhash"

    def fake_full(chapters, output, title):
        output.write_bytes(b"ID3" + b"y" * 5000)
        return "fullhash"

    monkeypatch.setattr("e_book_reader.pipeline.assemble_chapter_atomic", fake_chapter)
    monkeypatch.setattr("e_book_reader.pipeline.combine_full_book_atomic", fake_full)
    monkeypatch.setattr("e_book_reader.pipeline.verify_mp3", lambda path: (path.exists(), "ok"))

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
    assert int(db.list_segments()[0]["generation_seed"]) == 1
    assert any(kind == "chapter_completed" for kind, _ in events)

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
        "e_book_reader.analysis.OllamaBookAnalyzer.reconcile_aliases",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("casting ran again")),
    )
    resumed.run()
    assert db.book()["status"] == "completed"
