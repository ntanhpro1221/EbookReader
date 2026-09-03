"""The synthesis pool is sized against the card that is present, not the one it was fitted on.

Nothing in this project could see VRAM until now. ResourceSnapshot carried GPU temperature
and a foreground GPU percentage, but never how much memory the card had or had left - so
every VRAM-sensitive number was fitted by hand against one 8151 MiB card and written into
the defaults. They were right here and wrong anywhere else, which is what a number that
cannot be measured always becomes.

Three workers were measured holding 5484 MiB and five holding 7318, which is about 917 MiB
a worker over a shared 2733 MiB. Applied to the card actually present, a bigger machine
gets more workers with nobody editing a constant, and a smaller one gets fewer instead of
failing outright.
"""
from __future__ import annotations

from ebook_reader.tts_pool import (
    TTS_POOL_BASE_VRAM_MB,
    TTS_POOL_FOREGROUND_RESERVE_MB,
    TTS_POOL_WORKER_VRAM_MB,
    workers_for_vram,
)


def test_the_card_it_was_fitted_on_still_gets_what_it_measured() -> None:
    """8151 MiB with the models unloaded: the three workers docs/THROUGHPUT.md measured."""
    assert workers_for_vram(3, 8151) == 3


def test_a_smaller_card_runs_slower_instead_of_failing() -> None:
    """The failure this replaces: a default fitted on 8 GiB applied to a 4 GiB card asks
    for memory that is not there."""
    assert workers_for_vram(3, 4096) == 0
    assert workers_for_vram(3, 6000) == 2


def test_a_bigger_card_gets_more_without_anyone_editing_a_constant() -> None:
    assert workers_for_vram(8, 24576) == 8
    assert workers_for_vram(16, 24576) > 8


def test_the_setting_stays_a_ceiling_that_measurement_can_only_lower() -> None:
    """A number in the settings is a permission, not a demand - the same contract the
    perceptual pool already uses."""
    assert workers_for_vram(3, 65536) == 3
    assert workers_for_vram(0, 65536) == 0
    assert workers_for_vram(1, 65536) == 1, "below two there is no pool to size"


def test_room_is_left_for_whoever_else_is_using_the_computer() -> None:
    """Five workers were 1.3% faster than three and held 7318 of 8151 MiB, leaving nothing
    for the foreground or for keeping Whisper resident. That trade is refused on purpose."""
    exactly_three = TTS_POOL_BASE_VRAM_MB + 3 * TTS_POOL_WORKER_VRAM_MB
    assert workers_for_vram(3, exactly_three) < 3
    assert workers_for_vram(3, exactly_three + TTS_POOL_FOREGROUND_RESERVE_MB) == 3


def test_a_card_that_cannot_be_measured_changes_nothing() -> None:
    """No nvidia-smi, no NVIDIA card, a probe that timed out: every run before this one
    used the configured number, and an unanswered question is not a reason to change that.
    """
    assert workers_for_vram(3, None) == 3
    assert workers_for_vram(3, 0) == 3


def test_one_worker_is_not_a_pool() -> None:
    """A pool of one is the sequential path with process machinery around it: the cost
    without the reason."""
    barely = TTS_POOL_BASE_VRAM_MB + TTS_POOL_FOREGROUND_RESERVE_MB + TTS_POOL_WORKER_VRAM_MB
    assert workers_for_vram(3, barely) == 0
