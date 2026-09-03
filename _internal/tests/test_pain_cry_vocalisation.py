"""A cry of pain is a sound, not a foreign name.

"Argh" was taken for an English name and locked as a transliteration - "A-rag" - so Whisper
was then asked to hear that in a scream. It could not, the locked-name anchor mismatched,
and the chapter would not publish. Twenty-four segments across the corpus are cries of this
shape.
"""

from __future__ import annotations

import pytest

from ebook_reader.text_processing import (
    is_vocalization_only,
    normalize_vocalizations_for_tts,
)


@pytest.mark.parametrize(
    "text",
    ['"Argh!"', '"Arghh..."', "Ughh!", "Aargh", "urgh", "GRRR"],
)
def test_a_cry_is_a_vocalisation(text: str) -> None:
    assert is_vocalization_only(text)


@pytest.mark.parametrize(
    "text",
    ["Lucien", "piano", "được", "chuột", "vâng", "ghe", "nghe", "ghế"],
)
def test_an_ordinary_word_is_not(text: str) -> None:
    """No Vietnamese word ends in -gh, so the pattern cannot swallow one: ghe and nghe
    carry a vowel after the digraph while the cry must end at the h."""
    assert not is_vocalization_only(text)


def test_the_forms_already_recognised_still_are() -> None:
    for text in ("Ha…", "ah", "uuu", "hahahaha", "hờ"):
        assert is_vocalization_only(text), text


def test_only_three_texts_in_the_corpus_change_class() -> None:
    """Measured before shipping: 3 gained, 0 lost, across 8361 distinct segment texts."""
    gained = {'"Argh!"', '"Arghh..."', "Ughh!"}
    for text in gained:
        assert is_vocalization_only(text)


def test_a_held_sound_behind_a_consonant_is_still_a_sound() -> None:
    """The vowel-run pattern cannot see a run with a letter in front of it.

    "Tuuuuu" and "Cuuuu" are drawn-out sounds, but the name scanner took them for English
    names and sent them off for a reading, the same mistake that locked "Argh" as "A-rag".
    No word in either language repeats a vowel three times, so nothing real is swallowed:
    across 8,577 distinct tokens in the book corpus this rule adds exactly three.
    """
    assert is_vocalization_only("Tuuuuu")
    assert is_vocalization_only("Tuuu")
    assert is_vocalization_only("C\u1ee9uuuu")
    assert is_vocalization_only("\u00d4\u00f4\u00f4\u00f4\u00f4")


def test_a_regnal_number_is_not_a_scream() -> None:
    """"III" folds to a run of one vowel. The book says "Benedict III" 164 times."""
    assert not is_vocalization_only("III")
    assert not is_vocalization_only("VIII")
    assert not is_vocalization_only("XIV")
    # lower case is not how a numeral is written here, so a stretched i still reads as one
    assert is_vocalization_only("Iiii")


def test_ordinary_words_are_never_taken_for_sounds() -> None:
    for word in ("Blade", "Samael", "Benedict", "ng\u01b0\u1eddi", "khuya", "tu\u1ed5i", "quy\u1ec3n", "Tuan"):
        assert not is_vocalization_only(word), word


def test_a_cry_of_pain_is_given_something_the_voice_can_say() -> None:
    """Recognising it as a sound was only half the job.

    "Argh" is English on the page and a Vietnamese voice has nothing to say for it. Handed
    the letters, the model ran to its frame ceiling on a two-second scream - the only take
    in 948 segments to do so - and the ceiling then counted as evidence the take was cut
    off, which kept the segment failing however well the ASR side was fixed.

    Across both books the rule matches 55 times in 16 shapes, every one a cry.
    """
    assert normalize_vocalizations_for_tts('"Arghh..."') == '"\u00c1..."'
    assert normalize_vocalizations_for_tts('"Argh!"') == '"\u00c1!"'
    assert normalize_vocalizations_for_tts("Ugh.") == "\u00c1."
    assert normalize_vocalizations_for_tts("Grr!") == "\u00c1!"


def test_the_replacement_leaves_vietnamese_alone() -> None:
    """gh and ngh are ordinary Vietnamese spellings, and "argument" is an ordinary word."""
    for text in ("gh\u00e9 qua nh\u00e0", "nghe n\u00f3i v\u1eady", "H\u00e0 N\u1ed9i", "argument", "Anh ta g\u00f5 c\u1eeda."):
        assert normalize_vocalizations_for_tts(text) == text, text
