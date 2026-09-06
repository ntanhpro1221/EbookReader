"""The perceptual repair loop synthesized candidates one at a time beside an idle pool.

`_prefetch_candidate_batch` has existed since the pool was introduced and the *clarity*
repair loop has used it all along. The perceptual repair loop does the same work - generate
candidate takes for segments a reviewer flagged - and was never wired to it.

The queue's item 1 measured the phase this belongs to at 4,707s over 826 jobs with the GPU
averaging 23.7%, which is what an idle pool looks like from outside.

These tests pin the two things that make the prefetch safe to point at a second caller: the
producer must offer only what the committing loop would build identically, and a take it
declines must cost a regeneration rather than wrong audio.
"""
from __future__ import annotations

from typing import Any

import pytest

from ebook_reader.pipeline import (
    DELIVERY_CLARITY,
    GENERATION_STRATEGY_SPLIT,
    POSTPROCESS_PROFILE_NONE,
    TTS_POOL_MIN_BATCH,
)


class _Row(dict):
    """A sqlite3.Row stand-in: subscriptable and able to list its own keys."""

    def keys(self):  # noqa: D102
        return list(super().keys())


def _segment(stable_id: str, seq: int) -> _Row:
    return _Row(stable_id=stable_id, seq=seq, text="Một câu ngắn.", warning_code="")


def _candidate(
    candidate_id: int,
    *,
    attempt: int = 0,
    strategy: str = "direct",
    variant: str = "locked_spoken_v1",
    repair_round: int = 0,
) -> _Row:
    return _Row(
        id=candidate_id,
        tts_attempt=attempt,
        generation_strategy=strategy,
        postprocess_profile=POSTPROCESS_PROFILE_NONE,
        pronunciation_delivery_variant=variant,
        repair_round=repair_round,
        wav_path=f"C:/tmp/cand_{candidate_id}.wav",
    )


class _Pipeline:
    """Only the collaborators _prefetch_candidate_batch actually touches."""

    def __init__(self, pool: Any) -> None:
        self._pool = pool
        self._tts_pool_failed = False
        self.logged: list[str] = []

    def _synthesis_pool(self) -> Any:
        return self._pool

    def _close_synthesis_pool(self) -> None:
        self._pool = None

    def log(self, message: str) -> None:
        self.logged.append(message)

    @staticmethod
    def _segment_candidate_seed_salt(
        repair_round: int, tts_attempt: int, variant: str
    ) -> str:
        prefix = f"asr_clarity_candidate_{int(repair_round)}"
        if variant == "locked_spoken_v1":
            return f"{prefix}_{int(tts_attempt)}"
        return f"{prefix}_{variant}_{int(tts_attempt)}"


class _Pool:
    def __init__(self) -> None:
        self.seen: list[dict] = []

    def synthesize_many(self, jobs: list[dict]) -> list[dict]:
        self.seen = jobs
        return [
            {"stable_id": job["row"]["stable_id"], "checksum": "x" * 64, "seed": 1, "metrics": {}}
            for job in jobs
        ]


def _prefetch(pipeline: _Pipeline, pairs: list[tuple[Any, Any]]) -> dict:
    from ebook_reader.pipeline import BookPipeline

    return BookPipeline._prefetch_candidate_batch(pipeline, pairs)


def _pairs(count: int, **candidate_kwargs: Any) -> list[tuple[Any, Any]]:
    return [
        (_segment(f"c1s{index}", index), _candidate(index, **candidate_kwargs))
        for index in range(count)
    ]


def test_the_batch_carries_the_same_generation_parameters_as_the_loop() -> None:
    """The claim checks seed, file and checksum - never the generation parameters. If the
    worker builds under a different frame cap the loop accepts it as its own."""
    pool = _Pool()
    _prefetch(_Pipeline(pool), _pairs(TTS_POOL_MIN_BATCH))

    assert pool.seen, "nothing was offered to the pool"
    for job in pool.seen:
        assert job["kwargs"]["repair_short_utterance"] is True
        assert job["kwargs"]["delivery_mode"] == DELIVERY_CLARITY


def test_each_job_carries_its_own_salt() -> None:
    """One book holds both pronunciation variants at differing repair rounds, so a batch is
    never homogeneous. A shared prefix would compute the wrong seed for most of it."""
    pool = _Pool()
    pairs = [
        (_segment("c1s0", 0), _candidate(0, variant="locked_spoken_v1", repair_round=0)),
        (_segment("c1s1", 1), _candidate(1, variant="source_spelling_v1", repair_round=1)),
        (_segment("c1s2", 2), _candidate(2, variant="locked_spoken_v1", repair_round=2)),
    ]

    _prefetch(_Pipeline(pool), pairs)

    assert [job["seed_salt"] for job in pool.seen] == [
        "asr_clarity_candidate_0_0",
        "asr_clarity_candidate_1_source_spelling_v1_0",
        "asr_clarity_candidate_2_0",
    ]


def test_a_split_candidate_is_never_offered() -> None:
    """It is generated once and never runs the attempt loop, so a take for it is unclaimable."""
    pool = _Pool()

    result = _prefetch(_Pipeline(pool), _pairs(TTS_POOL_MIN_BATCH, strategy=GENERATION_STRATEGY_SPLIT))

    assert result == {}
    assert pool.seen == []


def test_a_later_attempt_is_never_offered() -> None:
    """A second attempt exists because the take before it was wrong; guessing at the repair
    would mean synthesizing for a decision nobody has made."""
    pool = _Pool()

    assert _prefetch(_Pipeline(pool), _pairs(TTS_POOL_MIN_BATCH, attempt=1)) == {}


def test_a_batch_below_the_pool_minimum_stays_sequential() -> None:
    """Spawning workers to share two jobs costs VRAM and buys nothing."""
    pool = _Pool()

    assert _prefetch(_Pipeline(pool), _pairs(TTS_POOL_MIN_BATCH - 1)) == {}
    assert pool.seen == []


def test_a_broken_pool_returns_nothing_rather_than_failing_the_book() -> None:
    class _Broken(_Pool):
        def synthesize_many(self, jobs: list[dict]) -> list[dict]:
            raise RuntimeError("worker died")

    pipeline = _Pipeline(_Broken())
    pipeline.db = None  # type: ignore[attr-defined]

    class _DB:
        def event(self, *args: Any, **kwargs: Any) -> None:
            pass

    pipeline.db = _DB()  # type: ignore[attr-defined]

    assert _prefetch(pipeline, _pairs(TTS_POOL_MIN_BATCH)) == {}
    assert pipeline._tts_pool_failed is True
