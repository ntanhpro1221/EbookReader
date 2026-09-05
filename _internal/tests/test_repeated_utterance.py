"""The voice sometimes says a short line twice, and nothing else in the pipeline can see it.

The owner heard c00007_s0000045 - "Mẹ kiếp!" - read twice, and asked why a real defect was
being left unfixed. The waveform shows it plainly: two syllables, 0.72s of silence, the same
two syllables again.

Three gates all have a hole in the same place. ASR skips a six-character line as too short to
transcribe. The pace gate skips anything under rate_check_min_chars. And the duration ceiling
for that text is 9.30s, so 1.60s of audio for 0.4s of speech passes easily.

Two cheaper signals were measured and rejected before this one. Seconds-per-character puts
the doubled take ninth of the book's 132 short segments, behind "C", "B" and "—RẦM!!", so any
ceiling tight enough to catch it rejects single letters and sound effects. The energy
envelope alone put it third by autocorrelation and outside the top twelve by half-similarity.

Comparing the MFCCs of the two halves separates it cleanly: first of 613 splittable segments
at 0.441, with the next at 0.244.
"""
from __future__ import annotations

import numpy as np
import pytest

from ebook_reader.audio_io import (
    REPEATED_UTTERANCE_MIN_GAP_SECONDS,
    REPEATED_UTTERANCE_THRESHOLD,
    repeated_utterance_score,
)

SAMPLE_RATE = 24_000


def _tone(seconds: float, frequency: float, *, seed: int = 0) -> np.ndarray:
    """A voiced-ish burst: a tone with harmonics, so MFCCs have structure to compare."""
    t = np.linspace(0.0, seconds, int(SAMPLE_RATE * seconds), endpoint=False)
    rng = np.random.default_rng(seed)
    wave = (
        np.sin(2 * np.pi * frequency * t)
        + 0.5 * np.sin(2 * np.pi * frequency * 2 * t)
        + 0.25 * np.sin(2 * np.pi * frequency * 3 * t)
    )
    return (wave * 0.3 + rng.normal(0, 0.005, t.size)).astype(np.float32)


def _silence(seconds: float) -> np.ndarray:
    return np.zeros(int(SAMPLE_RATE * seconds), dtype=np.float32)


def test_the_same_utterance_twice_scores_high() -> None:
    """What the owner heard: one line, a gap, the same line again."""
    said = np.concatenate([_tone(0.25, 220), _tone(0.2, 330)])
    audio = np.concatenate([said, _silence(0.7), said])

    score = repeated_utterance_score(audio, SAMPLE_RATE)

    assert score is not None
    assert score > REPEATED_UTTERANCE_THRESHOLD, score


def test_two_different_utterances_score_low() -> None:
    """A sentence with an ordinary pause says different things either side."""
    audio = np.concatenate(
        [_tone(0.25, 220), _tone(0.2, 330), _silence(0.7), _tone(0.3, 700), _tone(0.15, 140)]
    )

    score = repeated_utterance_score(audio, SAMPLE_RATE)

    assert score is not None
    assert score < REPEATED_UTTERANCE_THRESHOLD, score


def test_audio_with_no_internal_silence_is_not_judged() -> None:
    """Most audio has nothing to split on, and guessing a split would invent a verdict."""
    audio = np.concatenate([_tone(0.4, 220), _tone(0.4, 330)])
    assert repeated_utterance_score(audio, SAMPLE_RATE) is None


def test_a_gap_shorter_than_the_minimum_is_not_a_split() -> None:
    """A breath between clauses is not the pause a repeat leaves behind."""
    brief = REPEATED_UTTERANCE_MIN_GAP_SECONDS / 2
    said = _tone(0.25, 220)
    audio = np.concatenate([said, _silence(brief), said])
    assert repeated_utterance_score(audio, SAMPLE_RATE) is None


def test_leading_and_trailing_silence_are_not_splits() -> None:
    """Otherwise every clip with a quiet edge would be compared against nothing."""
    audio = np.concatenate([_silence(0.6), _tone(0.4, 220), _tone(0.3, 330), _silence(0.6)])
    assert repeated_utterance_score(audio, SAMPLE_RATE) is None


def test_silent_audio_yields_no_score() -> None:
    assert repeated_utterance_score(_silence(2.0), SAMPLE_RATE) is None


@pytest.mark.parametrize("seconds", [0.05, 0.1])
def test_audio_too_short_to_analyse_yields_no_score(seconds: float) -> None:
    assert repeated_utterance_score(_tone(seconds, 220), SAMPLE_RATE) is None
