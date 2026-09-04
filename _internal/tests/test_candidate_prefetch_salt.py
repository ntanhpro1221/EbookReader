"""The pooled candidate prefetch must compute the same seed salt the claim path expects.

The repair loop is the most expensive phase of a run and the only one that never used the
synthesis pool - 4,707s on alpha.32 against 2,658s for ordinary synthesis. Pooling it uses
the prefetch shape the main path already uses: workers synthesize, the serial loop claims
each result only after re-deriving the seed and checking it.

That check is what makes the failure mode silent. A candidate's salt carries its repair
round *and* its pronunciation variant, and a batch mixes both - alpha.32 used
locked_spoken_v1 526 times and source_spelling_v1 357. If the prefetch computed the salt any
differently from the loop, every claim would be declined, every take regenerated inline, and
the pool would cost its VRAM while returning nothing. Nothing would raise; the measurement
would simply say pooling does not help.

So these pin that the two sides agree, rather than pinning that the code runs.
"""
from __future__ import annotations

import pytest

from ebook_reader.audio_transform_contract import POSTPROCESS_PROFILE_NONE
from ebook_reader.database import (
    GENERATION_STRATEGY_SPLIT,
    PRONUNCIATION_DELIVERY_LOCKED,
    PRONUNCIATION_DELIVERY_SOURCE,
)
from ebook_reader.pipeline import BookPipeline
from ebook_reader.tts_pool import TTS_POOL_MIN_BATCH

VARIANTS = (PRONUNCIATION_DELIVERY_LOCKED, PRONUNCIATION_DELIVERY_SOURCE)


class _CapturingPool:
    """Stands in for SynthesisPool and keeps the jobs it was handed."""

    def __init__(self) -> None:
        self.jobs: list[dict] = []

    def synthesize_many(self, jobs):
        self.jobs = jobs
        return []


def _candidate(repair_round: int, variant: str, *, attempt: int = 0, strategy: str = "direct"):
    return {
        "tts_attempt": attempt,
        "generation_strategy": strategy,
        "postprocess_profile": POSTPROCESS_PROFILE_NONE,
        "repair_round": repair_round,
        "pronunciation_delivery_variant": variant,
        "wav_path": f"/tmp/c{repair_round}.wav",
    }


def _row(index: int):
    return {"id": index, "stable_id": f"c00001_s{index:07d}", "seq": index, "text": "xin chào"}


def _prefetch_with(pairs) -> _CapturingPool:
    pipeline = object.__new__(BookPipeline)
    pool = _CapturingPool()
    pipeline._synthesis_pool = lambda: pool
    BookPipeline._prefetch_candidate_batch(pipeline, pairs)
    return pool


@pytest.mark.parametrize("repair_round", [0, 1, 2, 4])
@pytest.mark.parametrize("variant", VARIANTS)
def test_the_pool_is_asked_for_the_salt_the_loop_will_claim(repair_round, variant) -> None:
    """The trap this file exists for, exercised rather than restated.

    An earlier version of this test compared _segment_candidate_seed_salt to itself, which
    proves the function is deterministic and nothing about whether the prefetch uses it the
    way the committing loop does. This drives the real prefetch and reads the salt out of
    the job it built.
    """
    pairs = [(_row(i), _candidate(repair_round, variant)) for i in range(TTS_POOL_MIN_BATCH)]
    pool = _prefetch_with(pairs)

    assert pool.jobs, "the batch met the minimum, so the pool should have been asked"
    expected = BookPipeline._segment_candidate_seed_salt(repair_round, 0, variant)
    for job in pool.jobs:
        assert job["seed_salt"] == expected
        assert job["kwargs"]["pronunciation_delivery_variant"] == variant


def test_a_mixed_batch_gets_a_salt_per_job_not_one_for_the_batch() -> None:
    """alpha.32 used locked_spoken 526 times and source_spelling 357, interleaved.

    One prefix for the whole batch - which is what the main path's prefetch sends - would
    give most of these jobs the wrong seed, and every claim would then be declined.
    """
    pairs = [
        (_row(0), _candidate(0, PRONUNCIATION_DELIVERY_LOCKED)),
        (_row(1), _candidate(2, PRONUNCIATION_DELIVERY_SOURCE)),
        (_row(2), _candidate(1, PRONUNCIATION_DELIVERY_LOCKED)),
    ]
    pool = _prefetch_with(pairs)
    salts = [job["seed_salt"] for job in pool.jobs]

    assert len(set(salts)) == 3, f"each job needs its own salt, got {salts}"
    assert salts[0] == BookPipeline._segment_candidate_seed_salt(0, 0, PRONUNCIATION_DELIVERY_LOCKED)
    assert salts[1] == BookPipeline._segment_candidate_seed_salt(2, 0, PRONUNCIATION_DELIVERY_SOURCE)


def test_only_first_attempts_and_direct_candidates_are_offered() -> None:
    """A later attempt exists because the take before it was wrong; a split is not retried."""
    pairs = [
        (_row(0), _candidate(0, PRONUNCIATION_DELIVERY_LOCKED)),
        (_row(1), _candidate(0, PRONUNCIATION_DELIVERY_LOCKED, attempt=1)),
        (_row(2), _candidate(0, PRONUNCIATION_DELIVERY_LOCKED, strategy=GENERATION_STRATEGY_SPLIT)),
        (_row(3), _candidate(0, PRONUNCIATION_DELIVERY_LOCKED)),
        (_row(4), _candidate(0, PRONUNCIATION_DELIVERY_LOCKED)),
    ]
    pool = _prefetch_with(pairs)
    offered = {job["row"]["stable_id"] for job in pool.jobs}
    assert offered == {_row(0)["stable_id"], _row(3)["stable_id"], _row(4)["stable_id"]}


def test_a_batch_below_the_minimum_never_starts_a_pool() -> None:
    """TTS_POOL_MIN_BATCH is measured: two segments gained nothing and held 3291 MiB."""
    started = []
    pipeline = object.__new__(BookPipeline)
    pipeline._synthesis_pool = lambda: started.append(1) or _CapturingPool()
    result = BookPipeline._prefetch_candidate_batch(
        pipeline,
        [(_row(i), _candidate(0, PRONUNCIATION_DELIVERY_LOCKED)) for i in range(TTS_POOL_MIN_BATCH - 1)],
    )
    assert result == {}
    assert not started, "a pool must not be built for a batch too small to benefit"


@pytest.mark.parametrize("variant", VARIANTS)
def test_the_variant_reaches_the_salt(variant: str) -> None:
    """A batch mixes both variants, so one prefix for the batch would be wrong for most."""
    locked = BookPipeline._segment_candidate_seed_salt(0, 0, PRONUNCIATION_DELIVERY_LOCKED)
    other = BookPipeline._segment_candidate_seed_salt(
        0, 0, PRONUNCIATION_DELIVERY_SOURCE
    )
    assert locked != other, "two variants must not share a salt, or one gets the other's audio"
    assert BookPipeline._segment_candidate_seed_salt(0, 0, variant) in (locked, other)


def test_the_round_reaches_the_salt() -> None:
    """Rounds differ within one batch too - a later round is a different take."""
    salts = {
        BookPipeline._segment_candidate_seed_salt(r, 0, PRONUNCIATION_DELIVERY_LOCKED)
        for r in range(5)
    }
    assert len(salts) == 5


def test_a_later_attempt_never_shares_the_first_attempt_salt() -> None:
    """Only attempt 0 is prefetched; if attempt 1 shared its salt it could claim that audio."""
    first = BookPipeline._segment_candidate_seed_salt(0, 0, PRONUNCIATION_DELIVERY_LOCKED)
    later = [
        BookPipeline._segment_candidate_seed_salt(0, n, PRONUNCIATION_DELIVERY_LOCKED)
        for n in range(1, 10)
    ]
    assert first not in later
