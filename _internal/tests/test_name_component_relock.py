"""One name, one reading — and the one thing this must never overwrite.

`name_component_corrections` has existed and been tested since alpha.47 and was never called,
because a correction can only be computed after every reading exists and by then all of them
are locked. `upsert_pronunciation` refuses locked rows, so there was nowhere for the repair
to go.

alpha.49 showed what that costs. It locked `Thê-ô-ban` for the bare surname and `theo-bên`
inside both full names - the protagonist's family name read two ways across four of the ten
chapters. alpha.47 had the same split and a person repaired it by hand with `pronounce`;
alpha.48 agreed only by luck, differing in case alone, which the detector ignores.

`relock_machine_pronunciation` draws the line at the *source* rather than the lock: the
machine may correct its own guess, and `listener_choice` is untouchable. These tests pin
both halves, because a repair that can overwrite a person's decision is worse than no repair.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from ebook_reader.analysis import name_component_corrections
from ebook_reader.database import LISTENER_PRONUNCIATION_SOURCE, ProjectDB

MACHINE = "english_name_transliteration"
CONSISTENCY = "name_component_consistency"


@pytest.fixture()
def db(tmp_path: Path) -> ProjectDB:
    database = ProjectDB(tmp_path / "project.sqlite3")
    database.initialize_book(
        title="Book",
        project_root=tmp_path,
        settings={},
        settings_hash="settings",
        input_manifest_hash="manifest",
    )
    return database


def _lock(database: ProjectDB, surface: str, reading: str, source: str = MACHINE) -> None:
    database.upsert_pronunciation(
        surface=surface,
        normalized_surface=surface.casefold(),
        spoken_form=reading,
        confidence=0.9,
        source=source,
        locked=True,
    )


def _reading(database: ProjectDB, surface: str) -> str:
    with database.connect() as conn:
        row = conn.execute(
            "SELECT spoken_form FROM pronunciations WHERE normalized_surface=?",
            (surface.casefold(),),
        ).fetchone()
    return str(row["spoken_form"])


def test_the_alpha49_split_is_detected(db: ProjectDB) -> None:
    """The real readings alpha.49 locked, three days after a person fixed the same split."""
    readings = {
        "Theosbane": "Thê-ô-ban",
        "Samael Kaizer Theosbane": "Xa-men cai-dờ theo-bên",
        "Arthur Kaizer Theosbane": "A-thờ cai-dờ theo-bên",
    }

    assert name_component_corrections(readings) == {"Theosbane": "theo-bên"}


def test_the_machine_may_correct_its_own_guess(db: ProjectDB) -> None:
    _lock(db, "Theosbane", "Thê-ô-ban")

    changed = db.relock_machine_pronunciation(
        normalized_surface="theosbane", spoken_form="theo-bên", source=CONSISTENCY
    )

    assert changed is True
    assert _reading(db, "Theosbane") == "theo-bên"


def test_a_persons_decision_is_never_overwritten(db: ProjectDB) -> None:
    """The whole reason this method exists rather than a blanket unlock."""
    db.set_listener_pronunciation(
        surface="Theosbane",
        normalized_surface="theosbane",
        spoken_form="theo-bên",
        source=LISTENER_PRONUNCIATION_SOURCE,
    )

    changed = db.relock_machine_pronunciation(
        normalized_surface="theosbane", spoken_form="Thê-ô-ban", source=CONSISTENCY
    )

    assert changed is False
    assert _reading(db, "Theosbane") == "theo-bên"


def test_a_reading_that_already_agrees_is_not_rewritten(db: ProjectDB) -> None:
    """Returning False here is what lets the caller report what it actually did."""
    _lock(db, "Theosbane", "theo-bên")

    assert (
        db.relock_machine_pronunciation(
            normalized_surface="theosbane", spoken_form="theo-bên", source=CONSISTENCY
        )
        is False
    )


def test_an_unknown_name_is_not_created(db: ProjectDB) -> None:
    """This repairs disagreement; it is not a second way to add a reading."""
    assert (
        db.relock_machine_pronunciation(
            normalized_surface="nobody", spoken_form="khong-ai", source=CONSISTENCY
        )
        is False
    )
    with db.connect() as conn:
        assert conn.execute("SELECT COUNT(*) c FROM pronunciations").fetchone()["c"] == 0


def test_case_alone_is_not_a_disagreement(db: ProjectDB) -> None:
    """alpha.48's readings differed only in case and needed no repair."""
    assert name_component_corrections({
        "Theosbane": "Theo-bên",
        "Samael Kaizer Theosbane": "Xa-men cai-dờ theo-bên",
    }) == {}


def test_an_empty_reading_is_refused(db: ProjectDB) -> None:
    _lock(db, "Theosbane", "Thê-ô-ban")
    with pytest.raises(ValueError):
        db.relock_machine_pronunciation(
            normalized_surface="theosbane", spoken_form="   ", source=CONSISTENCY
        )
