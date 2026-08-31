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
    LAST_RESORT_PRESETS,
    child_voice_preference,
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


def test_boys_are_ranked_by_theory_alone() -> None:
    """No male list: the listener asked for boys to be cast from the whole catalogue."""
    assert "male" not in CHILD_VOICE_PREFERENCE
    for name in ("Phạm Tuyên", "Ngọc Linh", "Trúc Ly"):
        assert child_voice_preference(name, "child", "male") == 0


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
