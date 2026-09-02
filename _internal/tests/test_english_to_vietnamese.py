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
    _cmu_phrase_to_vietnamese,
    _cmu_pronunciation_to_vietnamese,
    _without_tone,
    _cmu_pronunciations,
    _valid_vietnamese_spoken_form,
    _vowel_letter_groups,
    is_vietnamese_syllable,
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
    assert _read("Blade").startswith("Bờ-")
    assert _read("Street").startswith("Xờ-")


def test_a_velar_coda_takes_the_front_spelling_only_after_i() -> None:
    """"kinh" and "pích" are words; "king" and "đech" are not."""
    assert _read("King") == "Kinh"
    assert _read("Epic").endswith("ch")
    assert _read("Deck").endswith("c")
    assert _read("Rank").endswith("ng")


def test_an_offglide_gives_way_to_a_final_consonant() -> None:
    """"ất" is a rime; "ấyt" is not."""
    assert _read("Gate") == "Gết"
    assert _read("Void") == "Vót"


def test_a_glide_survives_when_nothing_follows_it() -> None:
    """The reduction is forced by the coda, not a dislike of diphthongs."""
    assert _read("Noah") == "Nô-a"
    assert _read("Juli") == "Giu-li"


def test_an_unstressed_schwa_is_not_read_as_a_full_a() -> None:
    """CMUdict writes /ʌ/ and /ə/ both as AH and tells them apart only by stress. Reading
    both as "a" gave *incredible* as "in-cơ-re-đa-bồ"; the schwa is mid-central, and so is
    Vietnamese ơ.

    Where the spelling says a, the schwa follows the spelling instead - "Noah" is "Nô-a" and
    "natasha" is "na-ta-sa", which is how Vietnamese writes those names.
    """
    assert _read("Incredible") == "In-cờ-re-đi-bồ"
    assert "nơ" in _read("Benedict")


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
    assert "r" not in _read("Guard").casefold()


def test_an_r_before_a_final_d_backs_the_stop() -> None:
    """The one mark the r leaves behind, and the table always said so in a comment.

    Vietnamese borrowed both of these words and ends both in -c: a card is "cạc" and a
    guard post is "gác". Reading them "cát" and "gát" changes the final consonant, and a
    listener asked for "cạc" by name. Only an r that is actually in the coda counts, so
    "Bird" and "Third", whose r is inside the vowel, are unaffected.
    """
    assert _read("Card").endswith("c")
    assert _read("Guard") == "Gác"
    assert _read("Bird").endswith("t")
    assert _read("Third").endswith("t")


def test_the_final_consonant_is_never_simply_lost() -> None:
    """Seven codas were mapped and the rest fell silent, so "Card" came out "Ca"."""
    for word in ("Card", "Soul", "Seed", "Path", "Void", "Safe"):
        reading = _read(word)
        assert reading[-1].casefold() in "cmnpt" or reading.endswith(("ch", "ng", "nh")), word


def test_a_name_of_several_words_is_read_word_by_word() -> None:
    """CMUdict is keyed on words, so a phrase missed it entirely and fell to the spelling.

    Every multi-word name in the book took that route: "Eagle Eyes" came back "I-glê-ếiêt",
    with a cluster no Vietnamese syllable can begin and a silent e read aloud. 35 of 189
    locked readings in the corpus broke the project's own syllable rule that way, four of
    them character names.
    """
    assert _cmu_phrase_to_vietnamese("Eagle Eyes") == "I-gồ Át"
    assert _cmu_phrase_to_vietnamese("Oldest Death") == "Ôn-đớt Đét"


def test_a_phrase_keeps_hyphens_for_syllables_and_spaces_for_words() -> None:
    """The shape a listener wrote them in: "he-rồ ọp âu-đít đét"."""
    reading = _cmu_phrase_to_vietnamese("Juliana Vox Blade")
    assert reading is not None
    assert len(reading.split(" ")) == 3, reading
    assert "-" in reading.split(" ")[0]


def test_a_phrase_the_dictionary_cannot_cover_is_left_alone() -> None:
    """An invented name has no entry, and guessing at one is worse than asking."""
    assert _cmu_phrase_to_vietnamese("Samael Kaizer Theosbane") is None


def test_a_single_word_is_not_treated_as_a_phrase() -> None:
    assert _cmu_phrase_to_vietnamese("Blade") is None


def test_a_possessive_is_not_given_a_syllable() -> None:
    """The book reads "Dawn’s Scourge" as two names, not three."""
    assert _cmu_phrase_to_vietnamese("Dawn's Scourge") == "Đon Xớch"


def test_an_r_before_a_consonant_closes_the_syllable_it_follows() -> None:
    """"Arthur" is AR-thur. Left in the next onset it built the cluster "rth", which the
    repair then spelled out as a syllable the name never had: "A-rơ-thơ"."""
    assert _read("Arthur") == "A-thơ"
    assert _read("Portals") == "Po-tồ"
    assert _read("Market") == "Ma-cớt"


def test_an_r_before_a_vowel_is_still_an_onset() -> None:
    """The rule is about clusters only; a listener reads Herald "he-rồ"."""
    assert _read("Herald") == "He-rồ"


def test_d_is_an_onset_the_splitter_can_peel() -> None:
    """"đ" and "d" are different onsets and both are real. With "đ" missing from the set the
    splitter found no legal head in "đr", gave up, and left "Dragon" with an onset cluster."""
    assert "đ" in VIETNAMESE_SYLLABLE_ONSETS
    reading = _read("Dragon")
    assert _valid_vietnamese_spoken_form("Dragon", reading), reading


def test_a_syllabic_l_needs_a_schwa_in_front_of_it() -> None:
    """A stressed AH is a full /ʌ/ with an ordinary /l/ behind it.

    Treating the two alike swallowed the last consonant of the word: "Gulf" read "Gồ" while
    "Golf", the same rime, read with an -n. Bulk, Result and Adult lost theirs the same way.
    """
    assert _read("Gulf").endswith("n")
    assert _read("Bulk").endswith("n")
    assert _read("Hull").endswith("n")
    # the schwa cases the rule is actually for
    assert _read("Michael") == "Mai-cồ"
    assert _read("Cable") == "Cê-bồ"


def test_the_vowel_reacts_to_the_coda_that_is_written() -> None:
    """Both vowel rules were keyed on the phone N, so a coda that reads "n" because an /l/
    survived the cluster missed them. "Golf" is "gôn" in Vietnamese - the ordinary word for
    the game - and came out "Gan"."""
    assert _read("Golf") == "Gôn"
    assert _read("Rudolf") == "Ru-đôn"
    assert _read("Waldo") == "Uôn-đô"
    # unchanged: these reach the same rule through a real N
    assert _read("John") == "Giôn"



def test_an_english_word_already_shaped_like_a_vietnamese_one_is_left_alone() -> None:
    """A listener asked for this by name: "may" needs no reading invented for it.

    The hand-written exclusion list covered 28 of the 366 such words among the ten
    thousand commonest English words.
    """
    for word in ("may", "man", "top", "long", "song", "cat", "bay", "run", "pain"):
        assert is_vietnamese_syllable(word), word
    for word in ("Blade", "Card", "King", "Seed", "Deck", "Rank", "Samael", "Theosbane"):
        assert not is_vietnamese_syllable(word), word


def test_the_recogniser_knows_real_vietnamese() -> None:
    """Checked against 6,282 distinct tone-bearing tokens in the book: 99.6% accepted."""
    for word in (
        "nguy\u1ec5n", "tr\u01b0\u1eddng", "khuya", "quy\u1ec3n", "ng\u01b0\u1eddi", "\u0111\u01b0\u1eddng", "tuy\u1ec7t",
        "nhi\u00ean", "vi\u1ec7c", "ti\u1ebfng", "t\u01b0\u01a1ng", "lu\u00f4n", "mi\u1ec7ng", "y\u00eau", "khu\u00f4n", "chi\u1ebfc",
    ):
        assert is_vietnamese_syllable(word), word


def test_the_velar_spelling_rule_knows_the_diphthong() -> None:
    """-nh/-ch only after a simple i or \u00ea. "kinh" is a syllable, "king" is not, and
    "ti\u1ebfng" and "chi\u1ebfc" keep the velar spelling because their nucleus is i\u00ea."""
    assert is_vietnamese_syllable("kinh")
    assert not is_vietnamese_syllable("king")
    assert is_vietnamese_syllable("ti\u1ebfng")
    assert is_vietnamese_syllable("chi\u1ebfc")


def test_a_tone_is_folded_but_a_vowel_is_not() -> None:
    """Breve, circumflex and horn spell a different vowel, so folding them away made
    "nhi\u00ean" read "nhien" and stop looking like a syllable."""
    assert _without_tone("nhi\u00ean") == "nhi\u00ean"
    assert _without_tone("\u0111\u01b0\u1eddng") == "\u0111\u01b0\u01a1ng"
    assert _without_tone("ti\u1ebfng") == "ti\u00eang"


def test_the_vowel_follows_the_letter_it_is_spelled_with() -> None:
    """A listener wrote these out, and they do not follow English vowel reduction.

    "dragon" is "\u0111\u1edd-ra-gon", not "\u0110\u01a1-re-g\u00e2n"; "natasha" is "na-ta-sa". These names are
    read from the letters, and the pronunciation only chooses among the values a letter can
    take - which is what a Vietnamese reader writing down an English word does.
    """
    assert _read("Dragon") == "\u0110\u1edd-ra-gon"
    assert _read("Zombie") == "Dom-bi"
    assert _read("Vampire") == "Vam-pai"
    assert _read("Natasha") == "Na-ta-sa"
    assert _read("Sophia") == "X\u00f4-phi-a"


def test_an_inserted_syllable_carries_the_huyen_tone() -> None:
    """Every epenthesis a listener has written is huy\u1ec1n: "in-c\u1edd-ri-\u0111i-b\u1ed3", "\u0111\u1edd-ra-gon",
    "b\u1edd-l\u1ebft". It is a weak syllable that was never in the word."""
    assert _read("Blade") == "B\u1edd-l\u1ebft"
    assert _read("Dragon").startswith("\u0110\u1edd-")


def test_an_er_ending_is_the_schwa_not_a_full_e() -> None:
    """"cai-d\u01a1", not "cai-d\u00ea". Keyed on the letter, -er and -or both land on \u01a1."""
    assert _read("Water").endswith("t\u01a1")
    assert _read("Master").endswith("t\u01a1")
    assert _read("Doctor").endswith("t\u01a1")


def test_a_silent_e_before_a_plural_s_spells_no_vowel() -> None:
    """"James" spells one vowel, not two; counting two left the word unaligned and the
    reading fell back to the phone alone, giving "Gi\u00e2m"."""
    assert _vowel_letter_groups("james") == ["a"]
    assert _read("James") == "Gi\u00eam"


def test_a_word_that_cannot_be_lined_up_still_reads() -> None:
    """Alignment covers 95.8% of the English words in the book; the rest fall back to the
    phone table rather than refusing to read."""
    for word in ("Rhythm", "Queue", "Beautiful", "Sergeant"):
        reading = _read(word)
        assert _valid_vietnamese_spoken_form(word, reading), (word, reading)
