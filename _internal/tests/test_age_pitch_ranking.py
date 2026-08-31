"""Casting prefers the preset that needs the smallest age pitch shift.

The age warp costs about 0.85 MOS on the pitch axis against 0.50 on the formant axis, and
the damage tracks the size of the shift (docs/CHILD_VOICE_TRANSFORM.md). Ranking used to
weigh tract reach and ignore the shift entirely.
"""

from __future__ import annotations

from ebook_reader.voice_catalog import (
    AGE_PITCH_RANK_BUCKET,
    EXCLUDED_PRESETS,
    LAST_RESORT_PRESETS,
    age_pitch_semitones,
    casting_presets,
    preset_age_reach,
    preset_reaches_age_pitch,
)


def _eligible(age: str, gender: str) -> list[str]:
    return [
        str(preset["name"])
        for preset in casting_presets(gender)
        if preset_reaches_age_pitch(str(preset["name"]), age, gender)
    ]


def test_the_bucket_is_wide_enough_to_ignore_a_single_semitone() -> None:
    assert AGE_PITCH_RANK_BUCKET >= 2
    assert 1 // AGE_PITCH_RANK_BUCKET == 0


def test_a_large_shift_outranks_a_small_one_only_across_a_bucket() -> None:
    assert 2 // AGE_PITCH_RANK_BUCKET < 11 // AGE_PITCH_RANK_BUCKET


def test_child_casting_has_presets_that_differ_in_shift() -> None:
    """If every candidate needed the same shift the ranking term would be inert."""
    for gender in ("male", "female"):
        shifts = {
            abs(age_pitch_semitones("child", gender, name)) // AGE_PITCH_RANK_BUCKET
            for name in _eligible("child", gender)
        }
        assert len(shifts) > 1, f"{gender}: pitch ranking cannot discriminate"


def test_reach_still_outranks_shift() -> None:
    """A clean voice that sounds like the wrong person is not the cheaper option."""
    import inspect

    from ebook_reader import character_registry

    source = inspect.getsource(character_registry.PresetAllocator.choose)
    reach = source.index("preset_age_reach(name, age, gender)")
    shift = source.index("age_pitch_semitones(age, gender, name)")
    assert reach < shift


def test_demoted_and_excluded_presets_are_unaffected_by_the_new_term() -> None:
    for gender in ("male", "female"):
        names = _eligible("child", gender)
        assert not (set(names) & EXCLUDED_PRESETS)
        assert LAST_RESORT_PRESETS.isdisjoint(names[:1]) or len(names) == 1


def test_reach_is_still_measured_for_every_eligible_preset() -> None:
    for gender in ("male", "female"):
        for name in _eligible("child", gender):
            assert preset_age_reach(name, "child", gender) >= 0.0
