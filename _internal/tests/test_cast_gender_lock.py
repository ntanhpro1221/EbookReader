"""A listener can settle a character's gender, and nothing asks again.

alpha.30 finished all 948 segments of its analysis and then refused to cast, because the
model called NOAH male twice and female twice. Refusing is right - a character voiced as
the wrong sex for a whole book is worse than a run that stops - but there was nothing a
person could do about it. The gender lives in the analysis, the analysis is fingerprinted,
and any code change able to settle the tie invalidates that fingerprint and costs the whole
phase again. A model error a listener could answer in one second cost an hour of machine
time instead.

This is `pronounce` for casting.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from ebook_reader.character_registry import resolve_gender
from ebook_reader.config import build_settings
from ebook_reader.project import create_or_open_project


class _Row(dict):
    pass


def _rows(*specs: tuple[str, str, str]) -> list[_Row]:
    return [_Row(speaker=speaker, gender=gender, text=text) for speaker, gender, text in specs]


def _project(tmp_path: Path):
    source = tmp_path / "001.txt"
    source.write_text("Một câu để mở project.", encoding="utf-8")
    _paths, db, _settings = create_or_open_project(
        [source], tmp_path / "out", build_settings(), "Cast lock"
    )
    return db


def test_a_pinned_gender_is_read_back_the_way_casting_keys_characters(tmp_path) -> None:
    db = _project(tmp_path)
    db.lock_character_gender("Noah", "male")
    assert db.locked_character_genders() == {"NOAH": "male"}


def test_the_answer_can_be_given_before_casting_has_ever_run(tmp_path) -> None:
    """The failure happens at the end of an hour of analysis. Being able to answer only
    afterwards would mean paying for that hour twice."""
    db = _project(tmp_path)
    db.lock_character_gender("Nobody Cast Yet", "female")
    assert db.locked_character_genders()["NOBODY CAST YET"] == "female"


def test_a_pin_outranks_a_model_that_disagrees_with_it(tmp_path) -> None:
    """They have read the book and the model has not."""
    identity = _rows(("NOAH", "female", "..."), ("NOAH", "female", "..."))
    assert resolve_gender(identity, identity) == ("female", "model")
    assert resolve_gender(identity, identity, {"NOAH": "male"}) == ("male", "listener")


def test_a_pin_outranks_the_text_as_well(tmp_path) -> None:
    identity = _rows(("NOAH", "male", "..."), ("NOAH", "female", "..."))
    narration = _rows(("NARRATOR", "unknown", "Noah. Cậu đi. Cậu về. Cậu ngồi. Cậu đứng. Cậu cười."))
    assert resolve_gender(identity, identity + narration)[0] == "male"
    assert resolve_gender(identity, identity + narration, {"NOAH": "female"}) == (
        "female",
        "listener",
    )


def test_a_pin_for_someone_else_changes_nothing(tmp_path) -> None:
    identity = _rows(("LAN", "female", "..."), ("LAN", "female", "..."))
    assert resolve_gender(identity, identity, {"NOAH": "male"}) == ("female", "model")


def test_the_model_cannot_overwrite_a_pinned_gender(tmp_path) -> None:
    """upsert_character runs after the resolver and used to write gender unconditionally,
    so a lock that only the resolver respected would still be lost on the way to the row."""
    db = _project(tmp_path)
    db.lock_character_gender("Noah", "male")
    character_id = db.upsert_character(
        canonical_name="NOAH",
        display_name="Noah",
        gender="female",
        age="adult",
        personality="",
        mentions=14,
        importance="main",
        confidence=0.5,
    )
    with db.connect() as conn:
        row = conn.execute(
            "SELECT gender, locked, display_name, mention_count FROM characters WHERE id=?",
            (character_id,),
        ).fetchone()
    assert row["gender"] == "male"
    assert row["locked"] == 1
    # Everything else is still the model's to update.
    assert row["display_name"] == "Noah"
    assert row["mention_count"] == 14


def test_an_unlocked_character_is_still_the_models_to_decide(tmp_path) -> None:
    db = _project(tmp_path)
    character_id = db.upsert_character(
        canonical_name="LAN",
        display_name="Lan",
        gender="female",
        age="adult",
        personality="",
        mentions=3,
        importance="minor",
        confidence=0.5,
    )
    db.upsert_character(
        canonical_name="LAN",
        display_name="Lan",
        gender="male",
        age="adult",
        personality="",
        mentions=4,
        importance="minor",
        confidence=0.5,
    )
    with db.connect() as conn:
        row = conn.execute(
            "SELECT gender FROM characters WHERE id=?", (character_id,)
        ).fetchone()
    assert row["gender"] == "male"


def test_only_a_real_gender_can_be_pinned(tmp_path) -> None:
    """"unknown" is what the run already had; pinning it would record a decision nobody
    made."""
    db = _project(tmp_path)
    for value in ("unknown", "", "Male ", "nam"):
        with pytest.raises(ValueError):
            db.lock_character_gender("Noah", value)
    with pytest.raises(ValueError):
        db.lock_character_gender("   ", "male")
