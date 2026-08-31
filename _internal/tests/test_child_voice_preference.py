"""A listener's ranking of child voices outranks the computed proxies.

Tract reach and pitch distance only estimate how good a warped voice will sound. Between
them they placed Ngọc Linh last of the three girl voices, and the listener placed it first.
Where a verdict exists it wins; where none exists the theory still decides.
"""

from __future__ import annotations

import inspect

from ebook_reader import character_registry
from ebook_reader.voice_catalog import (
    CHILD_VOICE_PREFERENCE,
    age_pitch_semitones,
    LAST_RESORT_PRESETS,
    child_voice_preference,
    preset_age_reach,
)


def test_the_girl_ranking_is_the_one_that_was_given() -> None:
    assert CHILD_VOICE_PREFERENCE["female"] == ("Ngọc Linh", "Đoan Trang", "Trúc Ly")


def test_ranked_presets_sort_in_the_order_given() -> None:
    order = CHILD_VOICE_PREFERENCE["female"]
    ranks = [child_voice_preference(name, "child", "female") for name in order]
    assert ranks == sorted(ranks) == list(range(len(order)))


def test_an_unheard_preset_sorts_after_every_ranked_one() -> None:
    ranked = CHILD_VOICE_PREFERENCE["female"]
    assert child_voice_preference("Thục Đoan", "child", "female") == len(ranked)


def test_the_boy_ranking_is_the_one_that_was_given() -> None:
    assert CHILD_VOICE_PREFERENCE["male"] == (
        "Phạm Tuyên",
        "Ngọc Linh",
        "Đoan Trang",
        "Trúc Ly",
    )


def test_the_boy_ranking_overrides_the_theory_not_merely_agrees_with_it() -> None:
    """Phạm Tuyên is the worst boy voice on paper and the listener's first choice."""
    best = CHILD_VOICE_PREFERENCE["male"][0]
    rivals = CHILD_VOICE_PREFERENCE["male"][1:]
    assert all(
        preset_age_reach(best, "child", "male") > preset_age_reach(name, "child", "male")
        for name in rivals
    )
    assert all(
        abs(age_pitch_semitones("child", "male", best))
        > abs(age_pitch_semitones("child", "male", name))
        for name in rivals
    )


def test_the_female_presets_keep_their_girl_order_as_boys() -> None:
    girls = CHILD_VOICE_PREFERENCE["female"]
    boys = [name for name in CHILD_VOICE_PREFERENCE["male"] if name in girls]
    assert boys == list(girls)


def test_adults_are_untouched_by_it() -> None:
    for age in ("adult", "teen", "elderly", "unknown"):
        assert child_voice_preference("Ngọc Linh", age, "female") == 0
        assert child_voice_preference("Thục Đoan", age, "female") == 0


def test_preference_outranks_reach_and_shift_but_not_demotion() -> None:
    source = inspect.getsource(character_registry.PresetAllocator.choose)
    demoted = source.index("name in LAST_RESORT_PRESETS")
    preference = source.index("child_voice_preference(name, age, gender)")
    reach = source.index("preset_age_reach(name, age, gender)")
    shift = source.index("age_pitch_semitones(age, gender, name)")
    assert demoted < preference < reach < shift


def test_no_ranked_preset_is_also_demoted() -> None:
    """A voice cannot be both a listener favourite and a last resort."""
    for names in CHILD_VOICE_PREFERENCE.values():
        assert LAST_RESORT_PRESETS.isdisjoint(names)
