from __future__ import annotations

import numpy as np
import pytest

from ebook_reader.expression import (
    EXPRESSION_GAIN_LIMIT_DB,
    EXPRESSION_TEMPO_LIMIT,
    NARRATION_AFFECT_WEIGHT,
    PAD,
    prosody_targets,
    shape_segment,
)


def _speechlike(seconds: float, rate: int = 48_000) -> np.ndarray:
    t = np.arange(int(rate * seconds)) / rate
    wave = 0.3 * np.sin(2 * np.pi * 120 * t) * (1 + 0.3 * np.sin(2 * np.pi * 3 * t))
    return wave.astype(np.float32)


def test_a_neutral_line_is_returned_untouched() -> None:
    """Most of a book carries no affect and must pay nothing for the feature.

    Measured on a real chapter set, 143 of 199 segments are neutral. Running those through
    a vocoder round trip would cost quality everywhere to add expression nowhere.
    """
    audio = _speechlike(3.0)

    for emotion, intensity in (("neutral", 2), ("angry", 0), ("neutral", 0)):
        out, target = shape_segment(audio, 48_000, emotion, intensity, "dialogue")
        assert target is None
        assert out is audio or np.array_equal(out, audio)


def test_a_narrator_carries_less_than_the_character_they_relate() -> None:
    """A narrator conveys the story's feeling; they are not living it.

    Shaping narration at full weight made the reading sound hurried and unsteady to a
    listener. Skipping it entirely lost the story's colour. The weight sits between.
    """
    character = prosody_targets("afraid", 2, seconds=7.0)
    narrator = prosody_targets("afraid", 2, weight=NARRATION_AFFECT_WEIGHT, seconds=7.0)

    assert 0.0 < NARRATION_AFFECT_WEIGHT < 1.0
    assert abs(narrator["pitch_semitones"]) < abs(character["pitch_semitones"])
    assert abs(narrator["range_ratio"] - 1.0) < abs(character["range_ratio"] - 1.0)
    assert abs(narrator["tempo"] - 1.0) <= abs(character["tempo"] - 1.0)


@pytest.mark.parametrize("emotion", sorted(set(PAD) - {"neutral"}))
@pytest.mark.parametrize("intensity", [1, 2, 3])
def test_tempo_and_level_stay_inside_what_a_listener_can_sit_through(
    emotion: str,
    intensity: int,
) -> None:
    """Speed and loudness are the two levers that cost comprehension, so they are bounded.

    This is hours of continuous listening. Pitch and pitch range carry expression without
    touching intelligibility, so they are where expression lives; tempo and level are
    seasoning and are held to a limit no emotion may exceed on an ordinary line.
    """
    target = prosody_targets(emotion, intensity, seconds=8.0)

    assert abs(target["tempo"] - 1.0) <= EXPRESSION_TEMPO_LIMIT + 1e-9
    assert abs(target["gain_db"]) <= EXPRESSION_GAIN_LIMIT_DB + 1e-9


def test_a_short_exclamation_may_move_further_than_a_paragraph() -> None:
    """A shout is over before it can tire anyone, and flattening it loses the one place
    the extra range belongs."""
    long_line = prosody_targets("angry", 3, seconds=8.0)
    short_line = prosody_targets("angry", 3, seconds=1.2)

    assert abs(short_line["tempo"] - 1.0) > abs(long_line["tempo"] - 1.0)
    assert abs(short_line["gain_db"]) > abs(long_line["gain_db"])


def test_shaping_preserves_length_unless_tempo_was_asked_for() -> None:
    """Chapters are assembled from these end to end, so a segment that was not
    time-scaled must come back at exactly the length it went in."""
    audio = _speechlike(2.5)

    out, target = shape_segment(audio, 48_000, "sad", 1, "narration")

    assert target is not None
    expected = round(len(audio) / target["tempo"])
    # Frame quantisation: WORLD works in 5 ms frames, so the result lands on a frame
    # boundary rather than on the exact sample the ratio asks for.
    assert abs(len(out) - expected) <= 48_000 * 0.010

    # A segment nobody asked to time-scale comes back at exactly its own length, because
    # chapters are assembled from these end to end.
    unshaped, no_target = shape_segment(audio, 48_000, "neutral", 0, "narration")
    assert no_target is None
    assert len(unshaped) == len(audio)
