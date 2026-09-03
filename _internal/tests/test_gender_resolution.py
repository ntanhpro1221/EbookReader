"""A character's gender is decided once, from the best evidence available.

alpha.30 finished all 948 segments of analysis and then died at the casting gate:

    Casting input quality gate failed: gender conflicts={'NOAH': {'female': 2, 'male': 2}}

Two places decided this and they disagreed by construction. The gate refused any
disagreement at all, so a 2-2 split was fatal; _majority() answered "unknown" on a tie, so
loosening the gate would have cast that character with no gender. Neither looked at the
text, where the narration calls Noah "cậu" eighteen times.

Vietnamese marks gender in nearly every word it uses for a person, which makes the text a
better witness than the model here - for Noah the model answered male twice, female twice
and unknown ten times, while the words in the segments naming him run 47 male to 4 female.
"""
from __future__ import annotations

from ebook_reader.character_registry import (
    GENDER_EVIDENCE_MINIMUM_HITS,
    _gendered_word_evidence,
    resolve_gender,
)


class _Row(dict):
    """Segment rows are sqlite3.Row in production; only __getitem__ is used."""


def _rows(*specs: tuple[str, str, str]) -> list[_Row]:
    return [_Row(speaker=speaker, gender=gender, text=text) for speaker, gender, text in specs]


def test_the_model_is_believed_when_it_agrees_with_itself() -> None:
    identity = _rows(("LAN", "female", "..."), ("LAN", "female", "..."))
    assert resolve_gender(identity, identity) == ("female", "model")


def test_a_majority_settles_it_without_reading_anything() -> None:
    identity = _rows(
        ("LAN", "female", "..."), ("LAN", "female", "..."), ("LAN", "male", "...")
    )
    gender, reason = resolve_gender(identity, identity)
    assert (gender, reason) == ("female", "model_majority")


def test_a_tie_is_settled_by_what_the_narration_calls_them() -> None:
    """The case that killed alpha.30 after ninety minutes of analysis."""
    identity = _rows(("NOAH", "male", "..."), ("NOAH", "female", "..."))
    narration = _rows(
        *[
            ("NARRATOR", "unknown", "Cha của Noah đã nói với cậu câu đó từ khi cậu còn bé.")
            for _ in range(4)
        ]
    )
    gender, reason = resolve_gender(identity, identity + narration)
    assert gender == "male"
    assert reason.startswith("text:")


def test_a_scene_full_of_the_other_gender_does_not_flip_the_answer() -> None:
    """Noah's own segments carry "ông" for his father and "bà" for his mother. Evidence is
    never pure, so the margin has to be wide rather than merely positive."""
    identity = _rows(("NOAH", "male", "..."), ("NOAH", "female", "..."))
    narration = _rows(
        ("NARRATOR", "unknown", "Noah nhìn cậu ấy. Cậu im lặng. Cậu bước đi. Cậu quay lại."),
        ("NARRATOR", "unknown", "Mẹ của Noah, bà ấy đã bỏ đi cùng một gã nhà giàu."),
    )
    assert resolve_gender(identity, identity + narration)[0] == "male"


def test_evidence_that_does_not_point_hard_enough_stays_unresolved() -> None:
    """Unknown is the honest answer, and it is what makes the gate still fail - a wrong
    gender is a wrong voice for the whole book."""
    identity = _rows(("KIM", "male", "..."), ("KIM", "female", "..."))
    narration = _rows(
        ("NARRATOR", "unknown", "Kim và anh ấy đứng đó. Cô nhìn anh. Anh nhìn cô. Cô cười."),
    )
    assert resolve_gender(identity, identity + narration) == ("unknown", "unresolved")


def test_a_handful_of_words_is_not_evidence() -> None:
    """One or two gendered words in a book is a coincidence, not a witness."""
    identity = _rows(("KIM", "male", "..."), ("KIM", "female", "..."))
    narration = _rows(("NARRATOR", "unknown", "Kim gặp cậu bé."))
    assert resolve_gender(identity, identity + narration) == ("unknown", "unresolved")

    plenty = _rows(
        ("NARRATOR", "unknown", "Kim. " + "Cậu đi. " * GENDER_EVIDENCE_MINIMUM_HITS),
    )
    assert resolve_gender(identity, identity + plenty)[0] == "male"


def test_only_segments_naming_the_character_are_counted() -> None:
    """Otherwise every character in the book inherits every other character's pronouns."""
    everything = _rows(
        ("NARRATOR", "unknown", "Noah bước vào. Cậu ngồi xuống."),
        ("NARRATOR", "unknown", "Bà ấy khóc. Cô ấy bỏ đi. Chị ấy quay lại. Nàng im lặng."),
    )
    assert _gendered_word_evidence(everything, {"Noah"}) == {"male": 1}


def test_words_used_for_either_gender_are_left_out() -> None:
    """"em", "con", "bác" and "người" carry no signal, so counting them adds noise."""
    rows = _rows(("NARRATOR", "unknown", "Noah và em và con và bác và người ấy."))
    assert _gendered_word_evidence(rows, {"Noah"}) == {}


def test_a_character_nobody_named_gets_no_evidence() -> None:
    rows = _rows(("NARRATOR", "unknown", "Cậu ấy đi. Cậu ấy về."))
    assert _gendered_word_evidence(rows, set()) == {}
    assert _gendered_word_evidence(rows, {""}) == {}
