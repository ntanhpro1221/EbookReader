"""Reading an English word as Vietnamese: one rule set, no favourites.

Built from the phonology rather than from a list of examples. Vietnamese allows six
syllable-final consonants and no onset cluster at all, so every English word has to be
rebuilt inside those limits; docs/ENGLISH_TO_VIETNAMESE.md records where each rule comes
from.

A listener's own examples - seed as "xít", king as "kinh" - are used here as checks on the
rule set, not as entries in a lookup table. If the rules stop producing them, the rules are
wrong, not the examples.
"""

from __future__ import annotations

import unicodedata

import pytest

from ebook_reader.analysis import (
    VIETNAMESE_SYLLABLE_ONSETS,
    _cmu_pronunciation_to_vietnamese,
    _cmu_pronunciations,
    _valid_vietnamese_spoken_form,
)

CORPUS = (
    "Seed", "King", "Card", "Deck", "Epic", "Incredible", "Blade", "Gate", "Game",
    "Path", "Void", "Safe", "Street", "Cable", "Rank", "Soul", "Zone", "Dawn",
    "Juli", "Lily", "Noah", "Golf", "Light", "House", "Point", "Sound", "Beast", "Guard",
)
TONE_MARKS = {"́", "̀", "̃", "̉", "̣"}


def _read(word: str) -> str:
    return _cmu_pronunciation_to_vietnamese(
        word, _cmu_pronunciations([word])[word.casefold()]
    )


def _onset_of(syllable: str) -> str:
    onset = ""
    # đ is a plain onset consonant; the production validator folds it to d before
    # checking, and a test that does not is testing its own spelling.
    for character in syllable.casefold().replace("đ", "d"):
        if unicodedata.normalize("NFD", character)[0] in "aeiouy":
            break
        onset += character
    return onset


def test_a_listeners_examples_fall_out_of_the_rules() -> None:
    """Not hard-coded: these are what the phonology produces on its own."""
    assert _read("Seed") == "Xít"
    assert _read("King") == "Kinh"


@pytest.mark.parametrize("word", CORPUS)
def test_every_reading_is_a_legal_vietnamese_word(word: str) -> None:
    assert _valid_vietnamese_spoken_form(word, _read(word))


@pytest.mark.parametrize("word", CORPUS)
def test_no_syllable_closes_on_a_stop_without_a_tone(word: str) -> None:
    """A syllable closed by p, t, c or ch takes sắc or nặng; the level tone is impossible."""
    for syllable in _read(word).split("-"):
        if not syllable.endswith(("ch", "c", "p", "t")):
            continue
        marks = set(unicodedata.normalize("NFD", syllable)) & TONE_MARKS
        assert marks, f"{word}: {syllable!r} closes on a stop with no tone"


@pytest.mark.parametrize("word", CORPUS)
def test_no_reading_contains_an_onset_cluster(word: str) -> None:
    """Vietnamese has none beyond /Cw/, so "bl" and "cr" have to be broken up."""
    for syllable in _read(word).split("-"):
        assert _onset_of(syllable) in VIETNAMESE_SYLLABLE_ONSETS, f"{word}: {syllable!r}"


def test_an_onset_cluster_is_broken_with_an_inserted_vowel() -> None:
    """Epenthesis, not deletion - the consonant survives in its own syllable."""
    assert _read("Blade").startswith("Bơ-")
    assert _read("Street").startswith("Xơ-")


def test_a_velar_coda_takes_the_front_spelling_only_after_i() -> None:
    """"kinh" and "pích" are words; "king" and "đech" are not."""
    assert _read("King") == "Kinh"
    assert _read("Epic").endswith("ch")
    assert _read("Deck").endswith("c")
    assert _read("Rank").endswith("ng")


def test_an_offglide_gives_way_to_a_final_consonant() -> None:
    """"ất" is a rime; "ấyt" is not."""
    assert _read("Gate") == "Gất"
    assert _read("Void") == "Vót"


def test_a_glide_survives_when_nothing_follows_it() -> None:
    """The reduction is forced by the coda, not a dislike of diphthongs."""
    assert _read("Noah") == "Nô-ơ"
    assert _read("Juli") == "Giu-li"


def test_an_unstressed_schwa_is_not_read_as_a_full_a() -> None:
    """CMUdict writes /ʌ/ and /ə/ both as AH and tells them apart only by stress. Reading
    both as "a" gave *incredible* as "in-cơ-re-đa-bồ"; the schwa is mid-central, and so is
    Vietnamese ơ."""
    assert _read("Incredible") == "In-cơ-re-đơ-bồ"
    assert _read("Noah").endswith("ơ")


def test_hand_chosen_readings_still_win() -> None:
    """Separating the schwa renamed a phone the override table is keyed on; folding it back
    at lookup is what keeps a listener's approved reading from silently lapsing."""
    assert _read("Benjamin") == "Ben-gia-min"
    assert _read("Lucien") == "Lu-si-en"
    assert _read("Michael") == "Mai-cồ"


def test_an_initial_w_becomes_the_medial_glide() -> None:
    """Vietnamese has no /w/ consonant; it is the glide written o or u, which is why
    *Washington* is "Oa-sinh-tơn". Writing it in front of a vowel spelt the same way gave
    "uu", which is not a nucleus."""
    assert _read("Wolf") == "Uôn"


def test_a_sonorant_outranks_an_obstruent_in_a_final_cluster() -> None:
    """/valv/ becomes "van"; English golf is "gôn" in Vietnamese for the same reason."""
    assert _read("Golf").endswith("n")
    assert _read("Sound").endswith("n")


def test_r_is_dropped_rather_than_read() -> None:
    """Non-rhotic English has already lost it before Vietnamese sees the word."""
    assert "r" not in _read("Card").casefold()
    assert _read("Guard") == "Gát"


def test_the_final_consonant_is_never_simply_lost() -> None:
    """Seven codas were mapped and the rest fell silent, so "Card" came out "Ca"."""
    for word in ("Card", "Soul", "Seed", "Path", "Void", "Safe"):
        reading = _read(word)
        assert reading[-1].casefold() in "cmnpt" or reading.endswith(("ch", "ng", "nh")), word
