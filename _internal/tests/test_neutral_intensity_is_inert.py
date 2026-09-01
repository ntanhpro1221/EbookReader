"""Intensity does nothing on a neutral segment, and 95.8% of segments are neutral.

Measured over 16953 analysed segments (docs/EMOTION_IN_PRODUCTION.md). Worth pinning for two
reasons: it is what makes the odd intensity distribution on neutral segments harmless, and it
is the thing that makes "intensity agreement" a misleading way to compare two analysis
configurations.
"""

from __future__ import annotations

import pytest

from ebook_reader.expression import prosody_targets


@pytest.mark.parametrize("intensity", [0, 1, 2, 3])
def test_neutral_is_unchanged_at_every_intensity(intensity: int) -> None:
    target = prosody_targets("neutral", intensity, weight=1.0, seconds=10.0)
    assert target["pitch_semitones"] == 0.0
    assert target["range_ratio"] == 1.0
    assert target["gain_db"] == 0.0


def test_a_real_emotion_does_scale_with_intensity() -> None:
    """Otherwise the field would be inert everywhere, which is a different bug."""
    steps = [
        prosody_targets("sad", intensity, weight=1.0, seconds=10.0)["pitch_semitones"]
        for intensity in (0, 1, 2, 3)
    ]
    assert steps[0] == 0.0
    assert steps[1] > steps[2] > steps[3], "sad must lower pitch further as it deepens"


def test_the_scale_is_monotonic_in_range_and_gain_too() -> None:
    ranges = [
        prosody_targets("sad", intensity, weight=1.0, seconds=10.0)["range_ratio"]
        for intensity in (1, 2, 3)
    ]
    gains = [
        prosody_targets("sad", intensity, weight=1.0, seconds=10.0)["gain_db"]
        for intensity in (1, 2, 3)
    ]
    assert ranges[0] > ranges[1] > ranges[2]
    assert gains[0] > gains[1] > gains[2]


def test_narration_weight_softens_but_does_not_invert() -> None:
    """Narration carries the story's feeling at half strength, not the opposite of it."""
    full = prosody_targets("sad", 3, weight=1.0, seconds=10.0)["pitch_semitones"]
    half = prosody_targets("sad", 3, weight=0.5, seconds=10.0)["pitch_semitones"]
    assert full < half < 0.0
