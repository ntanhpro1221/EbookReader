"""The onset click detector: a tall narrow spike at the start of speech.

A listener reported that one preset made the word "Mẹ" unintelligible behind a sound like a
water drop hitting steel, while the same word mid-sentence was fine. These pin the two
halves of the test, because either half alone matches ordinary speech.
"""

from __future__ import annotations

import numpy as np
import pytest

from ebook_reader.audio_io import (
    SEGMENT_ONSET_CLICK_MAX_WIDTH_MS,
    SEGMENT_ONSET_CLICK_RATIO,
    onset_click_metrics,
    signal_metrics,
)

RATE = 24000


def _voiced(seconds: float, f0: float = 180.0) -> np.ndarray:
    t = np.arange(int(RATE * seconds)) / RATE
    wave = sum(np.sin(2 * np.pi * f0 * n * t) / n for n in (1, 2, 3, 4))
    return (0.25 * wave / np.max(np.abs(wave))).astype(np.float32)


def _flagged(audio: np.ndarray) -> bool:
    ratio, width = onset_click_metrics(audio, RATE)
    return ratio > SEGMENT_ONSET_CLICK_RATIO and 0.0 < width < SEGMENT_ONSET_CLICK_MAX_WIDTH_MS


def test_clean_speech_is_not_flagged() -> None:
    assert not _flagged(_voiced(2.0))


def test_narrow_spike_at_onset_is_flagged() -> None:
    audio = _voiced(2.0).copy()
    spike = int(RATE * 0.002)
    audio[spike : spike + max(1, int(RATE * 0.002))] += 0.7
    assert _flagged(audio)


def test_wide_burst_at_onset_is_not_flagged() -> None:
    """A plosive is just as loud but carries into aspiration, so it must survive."""
    audio = _voiced(2.0).copy()
    start = int(RATE * 0.002)
    width = int(RATE * 0.030)
    audio[start : start + width] += 0.7 * np.hanning(width).astype(np.float32)
    assert not _flagged(audio)


def test_spike_late_in_the_utterance_is_not_flagged() -> None:
    """The same word mid-sentence was judged good, so only the opening is policed."""
    audio = _voiced(3.0).copy()
    late = int(RATE * 1.6)
    audio[late : late + max(1, int(RATE * 0.002))] += 0.7
    assert not _flagged(audio)


def test_silence_and_tiny_buffers_are_safe() -> None:
    assert onset_click_metrics(np.zeros(RATE, dtype=np.float32), RATE) == (0.0, 0.0)
    assert onset_click_metrics(np.zeros(8, dtype=np.float32), RATE) == (0.0, 0.0)


@pytest.mark.parametrize("audio", [np.zeros(0, dtype=np.float32), _voiced(1.0)])
def test_signal_metrics_always_carries_the_keys(audio: np.ndarray) -> None:
    metrics = signal_metrics(audio, RATE)
    assert "onset_click_ratio" in metrics
    assert "onset_click_width_ms" in metrics
