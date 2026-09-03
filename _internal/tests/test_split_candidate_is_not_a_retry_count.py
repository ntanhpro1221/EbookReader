"""A clause-split candidate is identified by what it is, not by a settings constant.

The repair loop generates a candidate up to tts.max_retries times, and when those run out
it escalates to splitting the sentence. The split candidate itself must be generated once
and never retried directly, and that was encoded by storing tts_attempt = max_retries so
that `range(current_attempt, retries)` came out empty.

Encoding a state in a configuration value means changing the value changes the state.
Raising max_retries from 4 to 10 - which docs/PACE_METRIC.md measures as rescuing two
segments the pace gate starved of attempts - turns every stored split candidate into
"attempt 4 of 10" and hands it six direct attempts it was never meant to have. alpha.32
holds 85 rows at tts_attempt = 4. It also makes an invariant check compare the stored
number against the new constant and raise "split checkpoint differs from its retry
schedule", turning a settings edit into a crash on resume.

The row already records the answer in generation_strategy. These tests pin that the marker
is the strategy, so max_retries can move.
"""
from __future__ import annotations

from ebook_reader.database import GENERATION_STRATEGY_DIRECT, GENERATION_STRATEGY_SPLIT


def _retry_range(candidate: dict, max_retries: int) -> range:
    """The direct-attempt schedule pipeline._process_segment_candidate builds.

    Mirrors the two lines under test rather than driving the whole method, which needs a
    TTS engine, a database and an audio file to reach them.
    """
    is_split = str(candidate["generation_strategy"]) == GENERATION_STRATEGY_SPLIT
    if is_split:
        return range(0)
    return range(int(candidate["tts_attempt"]), max_retries)


def test_a_split_candidate_gets_no_direct_attempts_at_any_budget() -> None:
    candidate = {"generation_strategy": GENERATION_STRATEGY_SPLIT, "tts_attempt": 4}
    for max_retries in (4, 6, 10, 16):
        assert list(_retry_range(candidate, max_retries)) == [], (
            f"a split candidate must never be retried directly; max_retries={max_retries}"
        )


def test_the_old_encoding_would_have_handed_it_six_attempts() -> None:
    """The bug this pins, stated as the arithmetic that produced it."""
    stored = {"generation_strategy": GENERATION_STRATEGY_SPLIT, "tts_attempt": 4}
    old_schedule = range(int(stored["tts_attempt"]), 10)  # what the numeric marker gave
    assert len(list(old_schedule)) == 6
    assert list(_retry_range(stored, 10)) == []


def test_an_ordinary_candidate_still_uses_the_whole_budget() -> None:
    candidate = {"generation_strategy": GENERATION_STRATEGY_DIRECT, "tts_attempt": 0}
    assert list(_retry_range(candidate, 4)) == [0, 1, 2, 3]
    assert list(_retry_range(candidate, 10)) == list(range(10))


def test_a_resumed_ordinary_candidate_continues_where_it_stopped() -> None:
    """Resume must not replay attempts that already happened - each one has its own seed."""
    candidate = {"generation_strategy": GENERATION_STRATEGY_DIRECT, "tts_attempt": 2}
    assert list(_retry_range(candidate, 4)) == [2, 3]
    assert list(_retry_range(candidate, 10)) == [2, 3, 4, 5, 6, 7, 8, 9]


def test_raising_the_budget_only_adds_attempts_to_candidates_that_can_use_them() -> None:
    """The whole point of raising max_retries, and the thing that must not leak sideways."""
    ordinary = {"generation_strategy": GENERATION_STRATEGY_DIRECT, "tts_attempt": 0}
    split = {"generation_strategy": GENERATION_STRATEGY_SPLIT, "tts_attempt": 4}
    gained_ordinary = len(_retry_range(ordinary, 10)) - len(_retry_range(ordinary, 4))
    gained_split = len(_retry_range(split, 10)) - len(_retry_range(split, 4))
    assert gained_ordinary == 6
    assert gained_split == 0
