"""Speech rate is measured with the pauses subtracted.

Dividing characters by wall-clock time measures punctuation density as much as speed. Over
3781 committed segments the two correlated at -0.62, and a segment in the densest tenth was
260 times likelier to be called too slow than one in the lightest, for reading its
punctuation properly. One such segment blocked a whole chapter from publishing.
"""

from __future__ import annotations

import pytest

from ebook_reader.audio_io import (
    MIN_SPEECH_SECONDS,
    PAUSE_GROUP_SECONDS,
    pause_group_count,
)
from ebook_reader.config import build_settings


def _rate(text: str, duration: float) -> float:
    speakable = sum(char.isalnum() for char in text)
    return speakable / max(duration - PAUSE_GROUP_SECONDS * pause_group_count(text), MIN_SPEECH_SECONDS)


def test_adjacent_punctuation_is_one_pause() -> None:
    """"): " is one silence however many characters spell it."""
    assert pause_group_count("Rare (Hiếm - B): Mạnh hơn / khó tìm hơn.") == 5
    assert pause_group_count("a), b") == 1, "a run of adjacent marks is one silence"
    assert pause_group_count("a), b.") == 2, "separated marks are separate silences"
    assert pause_group_count('Anh ta nói: "Thôi!"') == 3


def test_text_without_punctuation_asks_for_no_pause() -> None:
    assert pause_group_count("mọi thứ thật xa lạ") == 0
    assert pause_group_count("") == 0


def test_the_segment_that_blocked_a_chapter_now_passes() -> None:
    text = "Rare (Hiếm - B): Mạnh hơn / khó tìm hơn."
    speakable = sum(char.isalnum() for char in text)
    duration = speakable / 9.77  # what it actually measured, below the old 10.5 floor
    bounds = build_settings("high_quality")["tts"]["pace_chars_per_second"]["normal"]
    assert speakable / duration < 10.5, "the raw metric rejected it"
    assert float(bounds[0]) <= _rate(text, duration) <= float(bounds[1])


def test_punctuation_no_longer_decides_the_verdict() -> None:
    """Same words, same speaking rate, different punctuation: same answer."""
    plain = "Anh ta bước vào phòng và nhìn quanh một lượt rồi ngồi xuống ghế"
    dotted = "Anh ta bước vào phòng, nhìn quanh - một lượt; rồi ngồi xuống ghế."
    speakable = sum(char.isalnum() for char in plain)
    seconds = speakable / 16.9  # the corpus median speaking rate
    dotted_duration = seconds + PAUSE_GROUP_SECONDS * pause_group_count(dotted)
    assert _rate(plain, seconds) == pytest.approx(_rate(dotted, dotted_duration), rel=0.05)


def test_bounds_moved_with_the_metric() -> None:
    """Compensation shifts the corpus median from 14.50 to 16.90; the old 22.0 upper bound
    never fired before and would start firing at the 98th percentile if left alone."""
    normal = build_settings("high_quality")["tts"]["pace_chars_per_second"]["normal"]
    assert float(normal[0]) > 10.5
    assert float(normal[1]) > 22.0


def test_every_pace_keeps_increasing_bounds() -> None:
    paces = build_settings("high_quality")["tts"]["pace_chars_per_second"]
    for name in ("slow", "normal", "fast"):
        lower, upper = (float(value) for value in paces[name])
        assert 0 < lower < upper, name
    assert float(paces["slow"][0]) < float(paces["normal"][0]) < float(paces["fast"][0])


def test_a_pause_budget_can_never_consume_the_whole_duration() -> None:
    """Punctuation-only text must not divide by zero or go negative."""
    assert _rate("... --- ,,,", 0.4) >= 0.0
    assert _rate("Xong.", 0.05) > 0.0
