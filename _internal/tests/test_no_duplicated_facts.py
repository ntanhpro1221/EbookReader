"""Facts that must exist exactly once.

Five bugs in this project have been one value stated twice and the copies drifting: the
version pin across three files, the torch pin across two, "what counts as a delta" across
analysis and database, an ASR rule across two gates, and a flag that named a branch instead
of reading the verdict. None was visible by reading one file.

These pin the two that an audit of the package found still open. `scripts/audit_duplicated_facts.py`
lists the rest for a human to judge; most are coincidence.
"""

from __future__ import annotations

from ebook_reader import expression, quality_policy, tts
from ebook_reader.database import CHAPTER_POST_ENCODE_QUALITY_STAGE


def test_the_voice_pitch_range_has_one_definition() -> None:
    """The one time these disagreed, a shifted word stopped being a word."""
    assert expression.PITCH_FLOOR_HZ is tts.VOICE_VARIANT_PITCH_FLOOR_HZ
    assert expression.PITCH_CEILING_HZ is tts.VOICE_VARIANT_PITCH_CEILING_HZ


def test_the_pitch_range_is_a_voice_not_an_analysis_window() -> None:
    """A shift of fifteen semitones deliberately lands outside the measured window, so the
    clamp has to be what a voice can be."""
    assert tts.VOICE_VARIANT_PITCH_FLOOR_HZ <= 70.0
    assert tts.VOICE_VARIANT_PITCH_CEILING_HZ >= 500.0


def test_the_chapter_quality_stage_has_one_definition() -> None:
    """Writer and reader must look the evidence up under the same name."""
    assert quality_policy.CHAPTER_QUALITY_STAGE is CHAPTER_POST_ENCODE_QUALITY_STAGE


def test_expression_still_imports_cleanly_on_its_own() -> None:
    """Sharing the constant must not have introduced an import cycle."""
    import importlib

    for name in ("ebook_reader.expression", "ebook_reader.quality_policy"):
        assert importlib.import_module(name) is not None
