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
from ebook_reader.analysis import _local_name_fallback
from ebook_reader.text_processing import vietnamese_number_words

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


def test_an_offglide_and_a_final_consonant_cannot_both_stay() -> None:
    """"ết" is a rime; "âyt" is not, so one of the two has to go.

    Which one depends on whether Vietnamese has a vowel of the same quality to fall back
    on. "ây" has one - "ê" - so *blade* is "bờ-lết" and *lake* "lếch", consonant kept.
    "ai", "ao" and "oi" have none: flattening them would leave "a" or "o" and lose the
    word, so the consonant goes instead. A listener writes *light* "lai", *house* "hau",
    *sound* "sao", *point* "poi", *mouse* "mau".
    """
    assert _read("Gate") == "Gết"
    assert _read("Lake") == "Lếch"
    assert _read("Light") == "Lai"
    assert _read("Point") == "Poi"
    assert _read("Void") == "Voi"


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
    assert _read("Benedict") == "Be-ne-đích"


def test_hand_chosen_readings_still_win() -> None:
    """Separating the schwa renamed a phone the override table is keyed on; folding it back
    at lookup is what keeps a listener's approved reading from silently lapsing."""
    assert _read("Benjamin") == "Ben-gia-min"
    assert _read("Lucien") == "Lu-si-en"
    assert _read("Michael") == "Mai-cồ"


def test_an_initial_w_is_written_with_a_g_in_front_of_the_glide() -> None:
    """Standard Vietnamese spells [w] as a bare medial - "Oa-sinh-tơn", "Uy-li-am" - but a
    listener asked for the g: *water* "goát-tờ", *west* "goét", *wind* "guyn", *william*
    "guy-li-am", *wolf* "gốp". A glide with nothing in front of it invites the voice to read
    it as a syllable of its own."""
    assert _read("West") == "Goét"
    assert _read("Win") == "Guyn"
    assert _read("Wolf").startswith("G")


def test_uy_keeps_its_final_consonant() -> None:
    """"uy" is a medial glide plus its nucleus, not an off-glide: "guyn", "huynh"."""
    assert _read("Win") == "Guyn"
    assert _read("Wing") == "Guynh"


def _unused_initial_w() -> None:
    """Vietnamese has no /w/ consonant; it is the glide written o or u, which is why
    *Washington* is "Oa-sinh-tơn". Writing it in front of a vowel spelt the same way gave
    "uu", which is not a nucleus."""
    assert _read("Wolf") == "Uôn"


def test_a_sonorant_outranks_an_obstruent_in_a_final_cluster() -> None:
    """/valv/ becomes "van"; English golf is "gôn" in Vietnamese for the same reason."""
    assert _read("Golf").endswith("n")
    # "Sound" no longer reaches this rule: the off-glide keeps the syllable and the coda
    # goes, so it reads "Xao". *Golf* has no off-glide and still shows the sonorant winning.
    assert _read("Valve").endswith("n")


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

    Both come out with nặng, because a voiced final that has to be written -c has moved
    further than one that lands on -t. That is the listener's own "cạc"; "gạc" follows from
    the same rule rather than from the loan Vietnamese happens to have.
    """
    assert _read("Card") == "Cạc"
    assert _read("Guard") == "Gạc"
    assert _read("Bird").endswith("t")
    assert _read("Third").endswith("t")


def test_the_final_consonant_is_never_simply_lost() -> None:
    """Seven codas were mapped and the rest fell silent, so "Card" came out "Ca"."""
    # Void and Safe are excluded: their consonant is dropped on purpose now, to keep the
    # diphthong, which is what the listener's own readings do.
    for word in ("Card", "Soul", "Seed", "Path"):
        reading = _read(word)
        assert reading[-1].casefold() in "cmnpt" or reading.endswith(("ch", "ng", "nh")), word


def test_a_name_of_several_words_is_read_word_by_word() -> None:
    """CMUdict is keyed on words, so a phrase missed it entirely and fell to the spelling.

    Every multi-word name in the book took that route: "Eagle Eyes" came back "I-glê-ếiêt",
    with a cluster no Vietnamese syllable can begin and a silent e read aloud. 35 of 189
    locked readings in the corpus broke the project's own syllable rule that way, four of
    them character names.
    """
    assert _cmu_phrase_to_vietnamese("Eagle Eyes") == "I-gồ Ai"
    assert _cmu_phrase_to_vietnamese("Oldest Death") == "Ôn-đít Đét"


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
    assert _cmu_phrase_to_vietnamese("Dawn's Scourge") == "Đon Xờ-cớt"


def test_an_r_before_a_consonant_closes_the_syllable_it_follows() -> None:
    """"Arthur" is AR-thur. Left in the next onset it built the cluster "rth", which the
    repair then spelled out as a syllable the name never had: "A-rơ-thơ"."""
    assert _read("Arthur") == "A-thờ"
    assert _read("Portals") == "Po-tồ"
    assert _read("Market") == "Ma-két"  # as in the loan "mác-két"


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
    # "Cây-bồ": the diphthong only gives way when a consonant follows it, and this
    # syllable is open. A listener writes *cable* "cây-bồ" and *table* "tây-bồ".
    assert _read("Cable") == "Cây-bồ"
    assert _read("Table") == "Tây-bồ"


def test_the_vowel_reacts_to_the_coda_that_is_written() -> None:
    """Both vowel rules were keyed on the phone N, so a coda that reads "n" because an /l/
    survived the cluster missed them. "Golf" is "gôn" in Vietnamese - the ordinary word for
    the game - and came out "Gan"."""
    assert _read("Golf") == "Gôn"
    assert _read("Rudolf") == "Ru-đôn"
    assert _read("Waldo") == "Gôn-đô"  # the w now carries a g
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
        "nguyễn", "trường", "khuya", "quyển", "người", "đường", "tuyệt",
        "nhiên", "việc", "tiếng", "tương", "luôn", "miệng", "yêu", "khuôn", "chiếc",
    ):
        assert is_vietnamese_syllable(word), word


def test_the_velar_spelling_rule_knows_the_diphthong() -> None:
    """-nh/-ch only after a simple i or ê. "kinh" is a syllable, "king" is not, and
    "tiếng" and "chiếc" keep the velar spelling because their nucleus is iê."""
    assert is_vietnamese_syllable("kinh")
    assert not is_vietnamese_syllable("king")
    assert is_vietnamese_syllable("tiếng")
    assert is_vietnamese_syllable("chiếc")


def test_a_tone_is_folded_but_a_vowel_is_not() -> None:
    """Breve, circumflex and horn spell a different vowel, so folding them away made
    "nhiên" read "nhien" and stop looking like a syllable."""
    assert _without_tone("nhiên") == "nhiên"
    assert _without_tone("đường") == "đương"
    assert _without_tone("tiếng") == "tiêng"


def test_the_vowel_follows_the_letter_it_is_spelled_with() -> None:
    """A listener wrote these out, and they do not follow English vowel reduction.

    "dragon" is "đờ-ra-gon", not "Đơ-re-gân"; "natasha" is "na-ta-sa". These names are
    read from the letters, and the pronunciation only chooses among the values a letter can
    take - which is what a Vietnamese reader writing down an English word does.
    """
    assert _read("Dragon") == "Đờ-ra-gon"
    assert _read("Zombie") == "Dom-bi"
    assert _read("Vampire") == "Vam-pai"
    assert _read("Natasha") == "Na-ta-sa"
    assert _read("Sophia") == "Xô-phi-a"


def test_an_inserted_syllable_carries_the_huyen_tone() -> None:
    """Every epenthesis a listener has written is huyền: "in-cờ-ri-đi-bồ", "đờ-ra-gon",
    "bờ-lết". It is a weak syllable that was never in the word."""
    assert _read("Blade") == "Bờ-lết"
    assert _read("Dragon").startswith("Đờ-")


def test_an_er_ending_is_the_schwa_not_a_full_e() -> None:
    """"cai-dơ", not "cai-dê". Keyed on the letter, -er and -or both land on ơ."""
    assert _read("Water").endswith("tờ")
    assert _read("Master").endswith("tờ")
    assert _read("Doctor").endswith("tờ")


def test_a_silent_e_before_a_plural_s_spells_no_vowel() -> None:
    """"James" spells one vowel, not two; counting two left the word unaligned and the
    reading fell back to the phone alone, giving "Giâm"."""
    assert _vowel_letter_groups("james") == ["a"]
    assert _read("James") == "Giêm"


def test_a_word_that_cannot_be_lined_up_still_reads() -> None:
    """Alignment covers 95.8% of the English words in the book; the rest fall back to the
    phone table rather than refusing to read."""
    for word in ("Rhythm", "Queue", "Beautiful", "Sergeant"):
        reading = _read(word)
        assert _valid_vietnamese_spoken_form(word, reading), (word, reading)


def test_a_stop_final_syllable_takes_nang_when_the_coda_moved_furthest() -> None:
    """The whole difference between the two tones in the readings a listener wrote.

    A voiced English final that lands on -t keeps its place and takes sắc: *seed* is "xít",
    *blade* "bờ-lết". One that has to be written -c or -p has moved further and takes nặng:
    *card* is "cạc", *of* "ọp". A voiceless final always takes sắc, which is every other
    reading in the set - *box*, *cat*, *death*, *desk*, *top*.
    """
    assert _read("Card") == "Cạc"
    assert _read("Of") == "Ọp"
    assert _read("Seed") == "Xít"
    assert _read("Blade") == "Bờ-lết"
    assert _read("Box") == "Bóc"
    assert _read("Death") == "Đét"
    assert _read("George") == "Gióch"


def test_a_vowel_is_short_before_a_voiceless_consonant() -> None:
    """English clips a vowel before a voiceless consonant and holds it before a voiced one,
    and Vietnamese spells the difference: "au" is the short one, "ao" the long. A listener
    writes *house* and *mouse*, both before /s/, "hau" and "mau", and *sound*, before /nd/,
    "sao"."""
    assert _read("House") == "Hau"
    assert _read("Mouse") == "Mau"
    assert _read("Sound") == "Xao"


def test_a_schwa_before_a_nasal_opens_into_a_full_e() -> None:
    """*carmen* is "ca-men" and *elena* "e-le-na", where *benedict*, whose schwa meets a
    stop, is "be-nơ-đích"."""
    assert _read("Carmen") == "Ca-men"
    assert _read("Elena") == "E-le-na"
    assert _read("Rebecca") == "Re-be-ca"


def test_a_stressed_o_stays_open_before_a_consonant() -> None:
    """*tony* is "to-ni"; it rounds when unstressed (*sophia* "xô-phi-a"), when a consonant
    closes the syllable (*oldest* "ôn-đớt") and before a vowel (*noah* "nô-a")."""
    assert _read("Tony") == "To-ni"
    assert _read("Sophia") == "Xô-phi-a"
    assert _read("Noah") == "Nô-a"


def test_a_stressed_u_before_a_nasal_is_the_short_a() -> None:
    """*month* is "măn", *dungeon* "đăng-giừng"."""
    assert _read("Month") == "Măn"
    assert _read("Dungeon").startswith("Đă")


def test_a_final_k_is_written_ch_unless_an_s_closes_the_syllable_first() -> None:
    """*jack* is "dách", *action* "ách-sừn", *text* "tếch" - the vowel raising with the coda,
    because -ech is not a rime and -êch is. *mask*, *task* and *desk*, all /sk/, keep -c."""
    assert _read("Jack").endswith("ch")
    assert _read("Text") == "Tếch"
    assert _read("Next") == "Nếch"
    assert _read("Mask") == "Mác"
    assert _read("Task") == "Tác"
    assert _read("Desk") == "Đéc"
    # -och and -uch are not rimes, so a back vowel keeps -c whatever precedes the k
    assert _read("Box") == "Bóc"
    assert _read("Book") == "Búc"


def test_a_coarse_word_is_not_reached_by_a_rule_that_is_otherwise_right() -> None:
    """"Deck" lands on "Đếch" by every rule here, and the book says "Bộ Thẻ (Deck)" nine
    times. The override table is where a reading gets chosen by hand."""
    assert _read("Deck") == "Đéc"


def test_the_tion_suffix_is_read_sun() -> None:
    assert _read("Nation") == "Nây-sừn"
    assert _read("Station") == "Xờ-tây-sừn"
    assert _read("Vision") == "Vi-sừn"


def test_a_run_that_vietnamese_can_begin_a_syllable_with_stays_an_onset() -> None:
    """*katrina* is "ca-tri-na", not "cát-ri-na": "tr" is a Vietnamese onset."""
    assert _read("Katrina") == "Ca-tri-na"
    # and one it cannot begin with is still split across the two syllables
    assert _read("Arthur") == "A-thờ"


def test_an_s_between_a_sonorant_and_a_stop_joins_the_coda() -> None:
    """*monster* is "môn-tơ"; left in the onset the s became a syllable of its own."""
    assert _read("Monster").endswith("tờ")
    assert len(_read("Monster").split("-")) == 2


def test_a_diphthong_gives_up_its_glide_to_a_stop_but_not_to_a_fricative() -> None:
    """Designed off the English IPA, as a listener asked: *lake* /leɪk/ is "lếch" and
    *blade* /bleɪd/ "bờ-lết", the stop keeping the syllable, while *space* /speɪs/ is
    "xờ-pây", the fricative giving way. A nasal behaves like a stop: *name* is "nêm"."""
    assert _read("Lake") == "Lếch"
    assert _read("Blade") == "Bờ-lết"
    assert _read("Space") == "Xờ-pây"
    assert _read("Name") == "Nêm"
    assert _read("Game") == "Gêm"


def test_the_superlative_suffix_has_an_i() -> None:
    """CMUdict writes -est as AH0 S T in every word - biggest, fastest, largest, oldest -
    but the vowel of that suffix is /ɪ/, and a listener reads *oldest* "ôn-đít". A word that
    merely ends in those letters is untouched: *west* is "goét"."""
    assert _read("Oldest") == "Ôn-đít"
    assert _read("Biggest") == "Bi-gít"
    assert _read("West") == "Goét"
    assert _read("Best") == "Bét"


def test_a_regnal_number_is_said_not_spelled() -> None:
    """The book says "Benedict III" 164 times and the transliterator read the letters:
    "Bê-nê-đíc-iii". A regnal number is a number."""
    assert _cmu_phrase_to_vietnamese("Benedict III") == "Be-ne-đích thứ ba"
    assert _cmu_phrase_to_vietnamese("Henry VIII") == "Hen-ri thứ tám"
    assert _cmu_phrase_to_vietnamese("Louis XIV") == "Lu-ít thứ mười bốn"
    # a numeral on its own is not a name at all
    assert _cmu_phrase_to_vietnamese("III") is None


def test_the_number_words_follow_vietnamese_not_arithmetic() -> None:
    """15 is "mười lăm", and from twenty up 1 is "mốt" and 4 "tư"."""
    assert vietnamese_number_words(15) == "mười lăm"
    assert vietnamese_number_words(21) == "hai mươi mốt"
    assert vietnamese_number_words(24) == "hai mươi tư"
    assert vietnamese_number_words(25) == "hai mươi lăm"
    assert vietnamese_number_words(10) == "mười"


def test_the_spelling_route_says_a_final_er_as_the_schwa() -> None:
    """*Kaizer* came back "Cai-dên" where a listener writes "cai-dờ"; the route had no
    notion of the ending. It also read a silent e out loud - *Zone* was "Dô-nê" - which
    could not be fixed until the coda table stopped losing b, d, j and y."""
    assert _local_name_fallback("Kaizer") == "Cai-dờ"
    assert _local_name_fallback("Zone") == "Dôn"
    assert _local_name_fallback("Blade") == "Bờ-lát"
    assert _local_name_fallback("Safe") == "Xáp"


def test_a_dark_l_takes_a_diphthong_as_a_whole_rime() -> None:
    """*sale* is "xeo" and the mail of *email* "meo", not "x\u00ean" and "m\u00ean"; Vietnamese has
    "eo" for exactly this."""
    assert _read("Sale") == "Xeo"
    assert _read("Mail") == "Meo"


def test_the_onset_spelling_follows_the_vowel_that_is_written() -> None:
    """The dark /l/ of *scale* makes the rime "eo", and the onset came out "X\u1edd-ceo" where
    Vietnamese writes k before e. *market* becomes "Ma-k\u00e9t", which is the loan the language
    already has. Only c: a listener writes *game* "g\u00eam", not "gh\u00eam"."""
    assert _read("Scale") == "X\u1edd-keo"
    assert _read("Skill") == "X\u1edd-kiu"
    assert _read("Market") == "Ma-k\u00e9t"
    assert _read("Game") == "G\u00eam"
    assert _read("Gate") == "G\u1ebft"


def test_the_validator_checks_the_rime_not_just_the_edges() -> None:
    """Two readings got through this session on that gap, and both were found by printing
    readings for a person to look at rather than by any check here: "X\u0103-mon", where \u0103 cannot
    stand alone, and "X\u1edd-taiu", where "aiu" is not a rime at all."""
    assert not _valid_vietnamese_spoken_form("zz", "X\u0103-mon")
    assert not _valid_vietnamese_spoken_form("zz", "X\u1edd-taiu")
    assert not _valid_vietnamese_spoken_form("zz", "U\u0103n")
    assert not _valid_vietnamese_spoken_form("zz", "X\u1edd-cin")
    assert _valid_vietnamese_spoken_form("zz", "Xa-mon")
    assert _valid_vietnamese_spoken_form("zz", "O\u0103n")


def test_a_medial_glide_is_spelled_the_way_vietnamese_spells_it() -> None:
    """Reading 24,061 words produced 46 syllables the language does not have, every one a
    /w/ glide against the wrong vowel letter. Only the spelling was wrong."""
    assert _read("One") == "O\u0103n"
    assert _read("Twenty").startswith("T\u1edd-oen")
    assert _read("Schwartz") == "S\u1edd-o\u00f3t"


def test_the_c_and_ng_spellings_are_settled_both_ways() -> None:
    """Keyed on the phone it went one spelling too far each way: "Ka" for *care*, whose
    written vowel is a, and "E-ng\u1ebft" for *engaged*, whose written vowel is \u00ea."""
    assert _read("Care") == "Ca"
    assert _read("Karen") == "Ca-ren"
    assert _read("Engaged") == "E-ngh\u1ebft"
    assert _read("Shanghai") == "Sa-ngai"
    assert _read("Market") == "Ma-k\u00e9t"


def test_the_spelling_route_never_leaves_a_rime_the_language_lacks() -> None:
    """*Zytherion* read "Di-th\u00ea-ri\u00f4n" and *Theosbane* "Th\u00ea\u00f4-x\u1edd-ban"; "i\u00f4" and "\u00ea\u00f4" are not
    rimes. Across both books, all 757 names CMUdict lacks now read as Vietnamese."""
    for name in ("Zytherion", "Theosbane", "Brawler", "Hollowveil", "Aglaea", "Snownia"):
        reading = _local_name_fallback(name)
        assert _valid_vietnamese_spoken_form(name, reading), (name, reading)


def test_a_plural_s_yields_to_the_consonant_it_follows() -> None:
    """*gates* is "G\u1ebft", not "G\u00e2y": taking the s left a fricative for the diphthong rule to
    drop and the word lost its consonant. Where the s comes first the other one still goes,
    so *oldest* stays "\u00d4n-\u0111\u00edt"."""
    assert _read("Gates") == "G\u1ebft"
    assert _read("Cards") == "C\u1ea1c"
    assert _read("Oldest") == "\u00d4n-\u0111\u00edt"


def test_the_spelling_route_reads_a_phrase_one_word_at_a_time() -> None:
    """It used to run a phrase through as a single stream of syllables joined by hyphens:
    "Xa-men-cai-d\u00ean-th\u00ea-\u00f4-x\u1edd-ban" - one long word, with the -er ending never seen because it
    was not at the end of anything. A listener writes "sa-men cai-d\u01a1 theo-b\u00ean"."""
    reading = _local_name_fallback("Samael Kaizer Theosbane")
    assert reading == "Xa-men cai-d\u1edd th\u00ea-\u00f4-x\u1edd-ban"
    assert len(reading.split(" ")) == 3


def test_a_single_letter_is_a_grade_not_a_hundred() -> None:
    """This book ranks things "C \u00bb B \u00bb A \u00bb S", and C was being read as a Roman hundred -
    which then crashed the number words, because they stopped at ninety-nine."""
    from ebook_reader.text_processing import roman_numeral_value

    assert roman_numeral_value("C") is None
    assert roman_numeral_value("D") is None
    assert roman_numeral_value("I") == 1
    assert roman_numeral_value("XIV") == 14
    assert vietnamese_number_words(105) == "m\u1ed9t tr\u0103m l\u1ebb n\u0103m"
    assert vietnamese_number_words(120) == "m\u1ed9t tr\u0103m hai m\u01b0\u01a1i"
