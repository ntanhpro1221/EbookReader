"""No gender evidence must not kill a book: it is a weaker signal than a disagreement.

Book 2, batch 2 died at 19:30 on 2026-09-14 after 5.5 hours of analysis over all 3,749 segments,
because two names carried seven lines between them and the model offered no gender for either. The
same function had already stopped killing runs over a *disagreement*, for the reason written in its
own body: a check that cannot judge must not block, and this gate costs the whole book.

Two further facts this file pins down: a listener's locked gender counts as evidence (otherwise the
remedy the error message names cannot open the gate), and `identity_instability` still raises - one
identity holding two voice profiles is self-contradicting data, not an unanswerable question.
"""
from __future__ import annotations

import pytest

from ebook_reader.character_registry import _validate_casting_inputs


def _row(speaker: str, gender: str = "unknown", **extra):
    row = {
        "speaker": speaker,
        "gender": gender,
        "text": f"“{speaker} nói một câu.”",
        "chapter_id": 1,
        "canonical_character_id": None,
        "voice_profile_id": None,
    }
    row.update(extra)
    return row


def test_a_named_speaker_with_no_gender_evidence_is_reported_not_raised() -> None:
    said: list[str] = []
    rows = [_row("Luke") for _ in range(4)] + [_row("Lucien", "male") for _ in range(9)]

    unresolved = _validate_casting_inputs(rows, 3, said.append, {})

    assert "LUKE" in unresolved, unresolved
    assert unresolved["LUKE"]["gender_evidence"] == "none"
    assert unresolved["LUKE"]["mentions"] == 4
    assert any("cli cast --character LUKE" in line for line in said)
    assert "LUCIEN" not in unresolved


def test_a_speaker_the_model_did_gender_is_not_reported() -> None:
    rows = [_row("Victor", "male") for _ in range(5)]

    assert _validate_casting_inputs(rows, 3, lambda _m: None, {}) == {}


def test_one_identity_holding_two_voice_profiles_still_raises() -> None:
    rows = [
        _row("Victor", "male", canonical_character_id=1, voice_profile_id=1),
        _row("Victor", "male", canonical_character_id=1, voice_profile_id=2),
        _row("Victor", "male", canonical_character_id=1, voice_profile_id=2),
    ]

    with pytest.raises(RuntimeError, match="voice identity instability"):
        _validate_casting_inputs(rows, 3, lambda _m: None, {})


def test_a_locked_gender_is_evidence_and_is_not_reported() -> None:
    rows = [_row("Luke") for _ in range(4)]

    assert _validate_casting_inputs(rows, 3, lambda _m: None, {"LUKE": "male"}) == {}
