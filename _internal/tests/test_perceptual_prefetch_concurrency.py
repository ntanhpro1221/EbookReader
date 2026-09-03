"""Scoring runs beside ASR, and refuses to when that would cost something.

ASR is the most expensive stage of a run - 3,870 seconds on alpha.25 against TTS's 2,055 -
and it holds the GPU. Perceptual scoring is 2,538 seconds of pure CPU reading that ran
afterwards, with the GPU idle. Overlapping them is free only as long as the overlap never
blocks the ASR it is hiding behind and never lets a score outlive the audio it heard.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import soundfile as sf

from ebook_reader.config import build_settings
from ebook_reader.io_utils import sha256_file
from ebook_reader.models import ResourceDecision, ResourceLevel
from ebook_reader.pipeline import BookPipeline
from ebook_reader.project import create_or_open_project
from ebook_reader.voice_catalog import VOICE_PREVIEW_FILENAMES


class _StubPool:
    """Stands in for the process pool: records what it was asked and answers instantly."""

    instances: list["_StubPool"] = []
    # Answers are set on the class before the pool is built: the thread starts inside
    # _start_perceptual_prefetch and has already read them by the time it returns.
    next_scores: dict[str, float] = {}

    def __init__(self, settings, log, *, workers: int, threads: int = 2) -> None:
        self.settings = settings
        self.log = log
        self.workers = workers
        self.asked: list[str] = []
        self.scores: dict[str, float] = dict(_StubPool.next_scores)
        self.usable = workers
        _StubPool.instances.append(self)

    def usable_for(
        self, job_count: int, free_ram_gb: float, *, reserve_ram_gb: float = 0.0
    ) -> int:
        return min(self.usable, job_count)

    def score_many(self, wav_paths, *, free_ram_gb, reserve_ram_gb: float = 0.0):
        self.asked = list(wav_paths)
        self.log("pool da noi mot cau")
        return dict(self.scores)


def _pipeline(tmp_path: Path):
    checkpoint = tmp_path / "utmos.pth"
    checkpoint.write_bytes(b"locked checkpoint")
    source = tmp_path / "001.txt"
    # Several paragraphs, because a pool of fewer than two workers is not a pool and the
    # code declines to build one; a one-segment chapter would test the decline instead.
    source.write_text(
        "\n\n".join(
            f"Doan van thu {index} du dai de tao thanh mot segment rieng biet trong chuong."
            for index in range(1, 7)
        ),
        encoding="utf-8",
    )
    settings = build_settings(
        overrides={
            "perceptual_qa": {
                "checkpoint_path": str(checkpoint),
                "device": "cpu",
                "enabled": True,
                "parallel_workers": 8,
            },
            "tts": {"min_seconds_per_100_chars": 0.2},
        }
    )
    paths, db, settings = create_or_open_project(
        [source], tmp_path / "out", settings, "Prefetch beside ASR"
    )
    pipeline = BookPipeline(
        paths=paths,
        db=db,
        settings=settings,
        pause_requested=lambda: False,
        stop_requested=lambda: False,
        emit=lambda _kind, _payload: None,
    )
    pipeline._recover()
    pipeline._ensure_segments()
    chapter = db.list_chapters()[0]
    preset_name = next(iter(VOICE_PREVIEW_FILENAMES))
    profile_id = db.upsert_voice_profile(
        {
            "voice_key": "prefetch-test",
            "engine": "vieneu",
            "preset_name": preset_name,
            "description": "locked test voice",
            "seed": 1,
            "status": "ready",
        }
    )
    rows = db.list_segments(chapter_id=int(chapter["id"]))
    for index, row in enumerate(rows):
        with db.connect() as conn:
            conn.execute(
                "UPDATE segments SET voice_profile_id=? WHERE id=?",
                (profile_id, int(row["id"])),
            )
        wav = paths.chunks / "chapter_00001" / f"{index:07d}.wav"
        wav.parent.mkdir(parents=True, exist_ok=True)
        sf.write(wav, np.zeros(16_000, dtype=np.float32) + index * 1e-4, 16_000)
        db.mark_signal_passed(
            int(row["id"]),
            wav_path=wav,
            wav_sha256=sha256_file(wav),
            duration=1.0,
            signal={},
        )
    return pipeline, db, chapter


def _allow(**overrides) -> ResourceDecision:
    return ResourceDecision(level=ResourceLevel.MAXIMUM, reason="test", **overrides)


def _arrange(tmp_path, monkeypatch, *, decision: ResourceDecision | None = None):
    _StubPool.instances.clear()
    _StubPool.next_scores = {}
    pipeline, db, chapter = _pipeline(tmp_path)
    monkeypatch.setattr("ebook_reader.pipeline.PerceptualScorePool", _StubPool)
    monkeypatch.setattr(pipeline.resources, "decide", lambda _s: decision or _allow())
    return pipeline, db, chapter


def test_scoring_starts_beside_asr_and_hands_its_scores_over(tmp_path, monkeypatch) -> None:
    pipeline, db, chapter = _arrange(tmp_path, monkeypatch)
    rows = db.list_segments(chapter_id=int(chapter["id"]))
    expected = {str(row["wav_sha256"]): 3.0 + index for index, row in enumerate(rows)}

    _StubPool.next_scores = expected
    pipeline._start_perceptual_prefetch(chapter)
    assert _StubPool.instances, "the pool was never built"

    collected = pipeline._collect_perceptual_prefetch(int(chapter["id"]))

    assert collected == expected
    assert len(_StubPool.instances[0].asked) == len(rows)


def test_a_busy_machine_keeps_todays_behaviour_instead_of_stalling_asr(
    tmp_path, monkeypatch
) -> None:
    """The blocking gate loops until the machine is ready. Looping here would stall the
    very ASR this is meant to hide behind, so a refusal has to mean "not now", not "wait".
    """
    pipeline, _db, chapter = _arrange(
        tmp_path, monkeypatch, decision=_allow(allow_cpu_heavy_work=False)
    )

    pipeline._start_perceptual_prefetch(chapter)

    assert _StubPool.instances == []
    assert pipeline._collect_perceptual_prefetch(int(chapter["id"])) == {}


def test_a_critical_machine_does_not_start_more_processes(tmp_path, monkeypatch) -> None:
    pipeline, _db, chapter = _arrange(tmp_path, monkeypatch, decision=_allow(critical=True))
    pipeline._start_perceptual_prefetch(chapter)
    assert _StubPool.instances == []


def test_gpu_scoring_never_runs_beside_asr(tmp_path, monkeypatch) -> None:
    """Both would be on the same card, and the card is why ASR is the expensive stage."""
    pipeline, _db, chapter = _arrange(tmp_path, monkeypatch)
    pipeline.settings["perceptual_qa"]["device"] = "cuda"
    pipeline._start_perceptual_prefetch(chapter)
    assert _StubPool.instances == []


def test_disabled_perceptual_qa_starts_nothing(tmp_path, monkeypatch) -> None:
    pipeline, _db, chapter = _arrange(tmp_path, monkeypatch)
    pipeline.settings["perceptual_qa"]["enabled"] = False
    pipeline._start_perceptual_prefetch(chapter)
    assert _StubPool.instances == []


def test_starting_twice_does_not_start_two_pools(tmp_path, monkeypatch) -> None:
    """The callback fires after the first decode of a stage, and a chapter has more than
    one stage. Firing again must not put a second set of workers on the machine."""
    pipeline, _db, chapter = _arrange(tmp_path, monkeypatch)
    pipeline._start_perceptual_prefetch(chapter)
    pipeline._start_perceptual_prefetch(chapter)
    assert len(_StubPool.instances) == 1


def test_scores_prefetched_for_one_chapter_are_not_read_by_another(
    tmp_path, monkeypatch
) -> None:
    """A handle left behind by a chapter that failed part way is scores for other audio."""
    pipeline, _db, chapter = _arrange(tmp_path, monkeypatch)
    _StubPool.next_scores = {"deadbeef": 4.0}
    pipeline._start_perceptual_prefetch(chapter)

    assert pipeline._collect_perceptual_prefetch(int(chapter["id"]) + 1) == {}
    assert pipeline._collect_perceptual_prefetch(int(chapter["id"])) == {}, "handle is spent"


def test_the_pools_log_lines_are_replayed_on_the_main_thread(tmp_path, monkeypatch) -> None:
    """Written from a worker thread they would interleave with the ASR progress of a
    different stage and make the log lie about the order of events."""
    pipeline, _db, chapter = _arrange(tmp_path, monkeypatch)
    lines: list[str] = []
    monkeypatch.setattr(pipeline, "log", lines.append)

    pipeline._start_perceptual_prefetch(chapter)
    during = list(lines)
    pipeline._collect_perceptual_prefetch(int(chapter["id"]))

    assert "pool da noi mot cau" not in during
    assert "pool da noi mot cau" in lines
