"""The anchor check was grading Whisper's spelling and calling it pronunciation.

Every exact form the anchor accepts compares Whisper's output to a Vietnamese
transliteration, and the two cannot agree on a name Whisper recognises: it writes "Kaiser"
where the anchor holds "cai-dờ". alpha.51 paid for that on `c00005_s0000013`. The repair
loop produced the correct reading twice - rounds 0 and 2, "Samen Kaiser theo bên" - rejected
both, and kept the original, "Sam Min Kaiser theo bên". The owner listened on 2026-09-07 and
confirmed the kept take is the broken one: "tôi nghe đọc như là xa-min ấy".

Two cheaper repairs were measured and discarded before this one, and both are worth knowing
about because both look obviously right until measured:

- Sentence similarity cannot see the defect at all. Good take 0.818, broken take 0.816.
- Similarity scoped to the name separates those (0.800 / 0.667) but cannot be thresholded:
  "Lucian" against a locked "Lucien" scores 0.833, above the take that has to pass. Any
  threshold admitting the right reading admits a different name.

So this compares sounds. "xa" and "sa" are one phoneme in Vietnamese while "men" and "min"
are two, which is the distinction the ear made, and no threshold is involved.
"""
from __future__ import annotations

import pytest

from ebook_reader.asr import (
    _locked_name_anchor_component_match,
    _locked_name_anchor_components,
)

ANCHOR = {
    "surface": "Samael Kaizer Theosbane",
    "normalized_surface": "samael kaizer theosbane",
    "spoken_form": "Xa-men cai-dờ theo-bên",
}


def _passes(transcript: str, anchor: dict = ANCHOR) -> bool:
    result = _locked_name_anchor_component_match(anchor, transcript.split())
    assert result is not None
    return bool(result["passed"])


def test_the_reading_the_owner_confirmed_correct_passes() -> None:
    """Rounds 0 and 2 of the real repair loop. Both were rejected; both were right."""
    assert _passes("tên tôi là samen kaiser theo bên")


def test_the_reading_the_owner_confirmed_broken_fails() -> None:
    """The take that was kept and shipped to a listener. "Sam Min", not "Xa-men"."""
    assert not _passes("tên tôi là sam min kaiser theo bên")


def test_the_defect_is_pinned_to_the_syllable_that_was_wrong() -> None:
    """The whole point of scoring components: say which part of the name failed. Sentence
    metrics put these two takes 0.002 apart and could name nothing."""
    result = _locked_name_anchor_component_match(
        ANCHOR, "tên tôi là sam min kaiser theo bên".split()
    )

    assert result["component_matched"][0] is False, "Samael is the part that was misread"


def test_a_mangled_take_fails_too() -> None:
    """Round 4: "Kai rửa theo binh". The check must not simply pass everything."""
    assert not _passes("tên tôi là samen kai rửa theo binh")


def test_whisper_spelling_of_a_name_is_not_a_pronunciation_error() -> None:
    """The case with the widest blast radius: every locked English name in the book.
    `c00010_s0000017` is this exact shape and the owner said "đúng rồi". "kaizer" and
    "kaiser" sound out identically; no letter comparison will ever agree on them."""
    assert _passes(
        "ông ta chính là cha tôi arthur kaiser theo bên",
        {"surface": "Arthur Kaizer Theosbane", "spoken_form": "A-thờ cai-dờ theo-bên"},
    )


def test_a_name_that_is_simply_absent_fails() -> None:
    assert not _passes("hôm nay trời rất đẹp và tôi đi dạo")


def test_every_component_must_be_found_not_a_majority() -> None:
    """Two parts read perfectly must not carry a third that was never said."""
    assert not _passes("tên tôi là quang kaizer theosbane")


def test_a_different_name_that_merely_looks_similar_is_refused() -> None:
    """The reason similarity was abandoned. These differ by one letter and are two people."""
    lucien = {"surface": "Lucien", "spoken_form": "Lu-si-en"}

    assert _passes("anh lucien đến", lucien)
    assert not _passes("anh lucian đến", lucien)


def test_a_longer_name_is_not_swallowed_by_a_shorter_one() -> None:
    """Sound alone would accept this: the phonemiser reads "enne" and "en" identically. The
    spelling-length guard is what keeps "Lucien" from claiming "Lusienne"."""
    assert not _passes("anh lusienne đến", {"surface": "Lucien", "spoken_form": "Lu-si-en"})


def test_components_are_taken_in_order_and_consume_what_they_match() -> None:
    """Parts of one name cannot be gathered out of order from across a sentence."""
    assert not _passes("theo bên kaiser samen là tên tôi")


def test_a_claimed_token_is_invisible() -> None:
    """How an occurrence required three times is stopped from being satisfied three times by
    one reading: whatever another occurrence matched is not there to be matched again."""
    tokens = "anh lucien đến".split()
    anchor = {"surface": "Lucien", "spoken_form": "Lu-si-en"}

    assert _locked_name_anchor_component_match(anchor, tokens)["passed"]
    assert not _locked_name_anchor_component_match(
        anchor, tokens, blocked_tokens={1}
    )["passed"]


def test_components_come_from_the_hyphen_convention() -> None:
    assert _locked_name_anchor_components(ANCHOR) == [
        ("Samael", ("Xa", "men")),
        ("Kaizer", ("cai", "dờ")),
        ("Theosbane", ("theo", "bên")),
    ]


def test_a_spoken_form_that_does_not_line_up_is_declined_rather_than_guessed() -> None:
    """Wrong is worse than absent: a bad alignment would score real names against the wrong
    parts. The caller keeps the exact forms and loses nothing it had before."""
    assert (
        _locked_name_anchor_components(
            {"surface": "Samael Kaizer Theosbane", "spoken_form": "Xa men cai dờ theo bên"}
        )
        == []
    )
    assert (
        _locked_name_anchor_component_match(
            {"surface": "A B C", "spoken_form": "x"}, ["a", "b", "c"]
        )
        is None
    )


@pytest.mark.parametrize("transcript", ["", "   "])
def test_an_empty_transcript_does_not_pass_anything(transcript: str) -> None:
    assert _locked_name_anchor_component_match(ANCHOR, transcript.split()) is None


# The four verdicts above, through the real entry point rather than the helper. Worth the
# duplication: an earlier version of this fix passed every helper test and failed all four
# here, because it pinned the search to the alignment's position for the anchor - and when
# an anchor cannot match, the alignment parks it wherever the edit cost is cheapest, which
# for a six-token name read back as one token is the far end of the sentence.


def _adjudicate(expected: str, transcript: str, surface: str, spoken: str) -> dict:
    from tests.test_asr_locked_name_anchors import _anchor, _asr_result

    from ebook_reader.asr import adjudicate_locked_name_anchors

    return adjudicate_locked_name_anchors(
        expected,
        _asr_result(transcript),
        [_anchor(surface, spoken, spoken_start=expected.index(spoken.split()[0]))],
    )


CHAPTER_5 = ("Tên tôi là Xa-men cai-dờ theo-bên.", "Samael Kaizer Theosbane", "Xa-men cai-dờ theo-bên")


def test_end_to_end_the_take_that_reads_the_name_correctly_is_accepted() -> None:
    expected, surface, spoken = CHAPTER_5
    result = _adjudicate(expected, "Tên tôi là Samen Kaiser theo bên.", surface, spoken)

    assert result["passed"] is True


def test_end_to_end_the_take_the_owner_called_broken_is_still_refused() -> None:
    """The whole fix is worthless if it simply passes more. This take is the one that
    shipped, and the one a listener said was wrong."""
    expected, surface, spoken = CHAPTER_5
    result = _adjudicate(expected, "Tên tôi là Sam Min Kaiser theo bên.", surface, spoken)

    assert result["passed"] is False


def test_end_to_end_a_mangled_take_is_still_refused() -> None:
    expected, surface, spoken = CHAPTER_5
    result = _adjudicate(expected, "Tên tôi là Samen Kai rửa theo binh.", surface, spoken)

    assert result["passed"] is False


def test_end_to_end_a_spelling_disagreement_no_longer_needs_a_listener() -> None:
    """`c00010_s0000017`. The owner listened and said "đúng rồi", and the only thing wrong
    was that Whisper spells "Kaizer" as "Kaiser".

    Note what this does *not* claim. The same chapter's `c00010_s0000016` reads "Tai Ương
    Bình Minh (Dawn's Scourge)" against an anchor of "Đon Xờ-cớt", and Whisper heard "đon sờ
    cướp" - and that one still fails, correctly, because "cướp" is not "cớt". The fix removes
    the listener from spelling disagreements, not from real mispronunciations. Chapter 10
    publishes on this fix *plus* the acceptance already recorded for that other segment."""
    result = _adjudicate(
        "Ông ta chính là cha tôi, A-thờ cai-dờ theo-bên.",
        "Ông ta chính là cha tôi, Arthur Kaiser theo bên.",
        "Arthur Kaizer Theosbane",
        "A-thờ cai-dờ theo-bên",
    )

    assert result["passed"] is True


def test_a_real_mispronunciation_is_still_refused_after_the_fix() -> None:
    """The other blocked segment of chapter 10, and the guard against declaring victory: a
    fix that only ever passes more has not distinguished anything."""
    result = _locked_name_anchor_component_match(
        {"surface": "Dawn's Scourge", "spoken_form": "Đon Xờ-cớt"},
        "tài hương bình mình đon sờ cướp".split(),
    )

    assert result["component_matched"] == [True, False]
    assert result["passed"] is False


def test_a_hyphen_in_the_english_spelling_does_not_disable_the_check() -> None:
    """The convention is "hyphen inside a name part, space between them", and it holds for
    names. It breaks for game terms whose *English* spelling carries the hyphen: "Safe-Zone"
    is one whitespace part against a spoken "Xây Dôn" that is two, so the components did not
    line up and the check switched itself off. Five of this book's 112 seeded readings are
    that shape, and they are common words in it: A-rank, B-rank, SS-rank, Safe-Zone, Western
    Safe-Zone."""
    assert _locked_name_anchor_components(
        {"surface": "Safe-Zone", "spoken_form": "Xây Dôn"}
    ) == [("Safe", ("Xây",)), ("Zone", ("Dôn",))]

    assert _passes(
        "khu xây dôn phía tây", {"surface": "Safe-Zone", "spoken_form": "Xây Dôn"}
    )


def test_the_hyphen_fallback_cannot_take_apart_a_name_that_already_worked() -> None:
    """It runs only after the plain split has failed, which is what makes it safe to add: a
    hyphenated *name* read as one hyphenated spoken part stays one component, exactly as
    before. Measured on the 112 seeded readings: 107 aligned without this, 112 with it, and
    not one of the 107 changed."""
    assert _locked_name_anchor_components(
        {"surface": "Jean-Luc", "spoken_form": "Giăng-Luých"}
    ) == [("Jean-Luc", ("Giăng", "Luých"))]

    assert _locked_name_anchor_components(ANCHOR) == [
        ("Samael", ("Xa", "men")),
        ("Kaizer", ("cai", "dờ")),
        ("Theosbane", ("theo", "bên")),
    ]


def test_a_multi_word_term_with_a_hyphen_inside_it_lines_up() -> None:
    assert _locked_name_anchor_components(
        {"surface": "Western Safe-Zone", "spoken_form": "Goét-tờn Xây Dôn"}
    ) == [("Western", ("Goét", "tờn")), ("Safe", ("Xây",)), ("Zone", ("Dôn",))]
