"""A cry of pain is a sound, not a foreign name.

"Argh" was taken for an English name and locked as a transliteration - "A-rag" - so Whisper
was then asked to hear that in a scream. It could not, the locked-name anchor mismatched,
and the chapter would not publish. Twenty-four segments across the corpus are cries of this
shape.
"""

from __future__ import annotations

import pytest

from ebook_reader.text_processing import is_vocalization_only


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
