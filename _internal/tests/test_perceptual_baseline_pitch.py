"""The perceptual baseline is a property of the grading policy, not of the take.

A perceptual score is measured on the raw audio and compared against the preset's untouched
preview, because the voice variant is applied on the way into the chapter, after every gate.
The pipeline chose that deliberately and the database validator compared the recorded
baseline against the take's own pitch, so any voice carrying a register shift could satisfy
neither: seven candidates read at -1 semitone stopped a ten-chapter run twice, at the same
line.
"""

from __future__ import annotations

import inspect

from ebook_reader.database import ProjectDB
from ebook_reader.perceptual_contract import PERCEPTUAL_BASELINE_PITCH_SEMITONES
from ebook_reader.pipeline import BookPipeline


def test_the_baseline_register_is_the_untouched_preview() -> None:
    assert PERCEPTUAL_BASELINE_PITCH_SEMITONES == 0


def test_the_pipeline_grades_against_that_baseline() -> None:
    source = inspect.getsource(BookPipeline._effective_perceptual_profile)
    assert "PERCEPTUAL_BASELINE_PITCH_SEMITONES" in source
    assert "return profile, 0" not in source, "the shared name, not a repeated literal"


def test_the_validator_checks_the_policy_not_the_take() -> None:
    """Against the take's pitch, a register-shifted voice can never pass."""
    source = inspect.getsource(ProjectDB)
    marker = "candidate perceptual baseline pitch is not the graded reference"
    assert marker in source
    window = source[source.index(marker) - 400 : source.index(marker)]
    assert "PERCEPTUAL_BASELINE_PITCH_SEMITONES" in window
    assert 'effective_pitch_semitones"]' not in window.split("if baseline_pitch")[-1]


def test_a_register_shifted_voice_is_not_excluded_by_construction() -> None:
    """The narration register for one preset is -4; the check must survive that."""
    from ebook_reader.voice_catalog import REGISTER_FORMANT_TRADE_PER_SEMITONE

    assert REGISTER_FORMANT_TRADE_PER_SEMITONE > 0, "register shifts are a real feature"
    assert PERCEPTUAL_BASELINE_PITCH_SEMITONES == 0, (
        "a baseline that tracked the register would compare raw audio "
        "against a transformed reference"
    )
