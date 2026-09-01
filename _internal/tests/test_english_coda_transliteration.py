"""An English word must not lose its ending when it becomes Vietnamese.

Only seven codas were mapped and every other one fell silent, so "Card" came out "Ca",
"Soul" as "Xô" and "Seed" as "Xi" - the syllable ended early and the word stopped being the
word. The additions follow what 289 accepted transliterations in this project already did:
final s became t eight times against four dropped, l became n seven times against four, th
became t, c stayed c.
"""

from __future__ import annotations

import pytest

from ebook_reader.analysis import (
    _cmu_pronunciation_to_vietnamese,
    _cmu_pronunciations,
    _valid_vietnamese_spoken_form,
)


def _read(word: str) -> str:
    pronunciation = _cmu_pronunciations([word])[word.casefold()]
    return _cmu_pronunciation_to_vietnamese(word, pronunciation)


@pytest.mark.parametrize(
    ("word", "expected"),
    [
        ("Card", "Cac"),
        ("Soul", "Xôn"),
        ("Seed", "Xit"),
        ("Path", "Pet"),
        ("Void", "Voit"),
        ("Safe", "Xâyp"),
    ],
)
def test_the_final_consonant_survives(word: str, expected: str) -> None:
    assert _read(word) == expected


def test_card_ends_in_c_because_of_the_r() -> None:
    """A listener gave this one directly: "card" is read "cạc", not "cát"."""
    assert _read("Card").endswith("c")


def test_a_plain_final_d_is_t_not_c() -> None:
    """The backing is the r's doing, so it must not spread to every d."""
    assert _read("Seed").endswith("t")


def test_readings_that_already_worked_are_unchanged() -> None:
    for word, expected in (
        ("Deck", "Đec"),
        ("Epic", "E-pic"),
        ("Juli", "Giu-li"),
        ("Lily", "Li-li"),
        ("Noah", "Nô-a"),
        ("Gate", "Gâyt"),
        ("Game", "Gâym"),
        ("Dawn", "Đon"),
    ):
        assert _read(word) == expected, word


def test_every_new_reading_is_legal_vietnamese() -> None:
    """A coda outside -c -ch -m -n -ng -nh -p -t is not a Vietnamese syllable at all."""
    for word in ("Card", "Soul", "Seed", "Path", "Void", "Eyes", "Gods", "Safe", "Zone"):
        assert _valid_vietnamese_spoken_form(word, _read(word)), word
