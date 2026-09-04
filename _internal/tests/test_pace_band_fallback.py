"""Losing a shade of delivery beats losing the sentence - but the listener is told.

tts.pace_chars_per_second has three bands and analysis assigns one per segment. `fast`
raises the *lower* bound to 14.0, so a directive meaning "say this faster" turns into "this
take is too slow". alpha.43 lost c00007_s0000074 exactly that way: four takes at 12.70,
12.26, 12.26 and 12.70 against a floor of 14.0, where alpha.32 had passed the identical
12.70 take with the same line marked `normal`. Only the acting directive changed.

The rescue replays the same salts with the band relaxed and keeps the first take that
clears the normal floor. It runs only after the direct attempts and the split have both
failed, so an unreachable directive costs the sentence only when nothing else works.
"""
from __future__ import annotations

from ebook_reader.pipeline import (
    HIGH_QUALITY_ALLOWED_SEGMENT_WARNINGS,
    PACE_BAND_RELAXED_METRIC,
    PACE_BAND_RELAXED_WARNING,
    BookPipeline,
)


def test_the_relaxation_is_reported_to_the_listener() -> None:
    """The whole reason this is a warning and not a silent fix."""
    codes = BookPipeline._signal_warning_codes({PACE_BAND_RELAXED_METRIC: 1.0})
    assert PACE_BAND_RELAXED_WARNING in codes


def test_an_untouched_take_carries_no_such_warning() -> None:
    assert PACE_BAND_RELAXED_WARNING not in BookPipeline._signal_warning_codes({})


def test_the_warning_blocks_publication_so_a_person_hears_it() -> None:
    """Flattening a reading is a trade someone should hear before it ships.

    It is still strictly better than the alternative it replaces: "no audio at all, nothing
    to listen to" becomes "audio, plus a decision".
    """
    assert PACE_BAND_RELAXED_WARNING not in HIGH_QUALITY_ALLOWED_SEGMENT_WARNINGS


def test_a_normal_segment_never_pays_for_this() -> None:
    """The common path: 98% of segments are already `normal` and must return at once."""
    pipeline = object.__new__(BookPipeline)
    reason = BookPipeline._retry_in_normal_pace_band(
        pipeline,
        {"pace": "normal", "stable_id": "c00001_s0000001"},
        None,
        delivery_mode="primary",
        seed_salt_prefix="primary",
        repair_short_utterance=True,
        asr_repair_round=None,
    )
    assert reason == "pace_band=already normal"


def test_a_segment_with_no_pace_field_counts_as_normal() -> None:
    pipeline = object.__new__(BookPipeline)
    reason = BookPipeline._retry_in_normal_pace_band(
        pipeline,
        {"stable_id": "c00001_s0000001"},
        None,
        delivery_mode="primary",
        seed_salt_prefix="primary",
        repair_short_utterance=True,
        asr_repair_round=None,
    )
    assert reason == "pace_band=already normal"
