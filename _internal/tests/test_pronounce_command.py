"""A listener can pin how a name is read.

A four-letter word once stopped a ten-chapter book: "Deck" was refused by the CMUdict path
for needing contextual review and by the local fallback for having a CMUdict entry, and
high-quality analysis will not publish a name it could not resolve. The caution is right;
what was missing was any way for a person to settle it short of editing SQLite by hand.
"""

from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

import pytest

from ebook_reader.cli import LISTENER_PRONUNCIATION_SOURCE, _command_pronounce
from ebook_reader.database import ProjectDB


@pytest.fixture()
def project(tmp_path: Path) -> Path:
    root = tmp_path / "book"
    (root / "work").mkdir(parents=True)
    ProjectDB(root / "project.sqlite3")
    # _existing_project_paths refuses a directory without settings, which is what stops
    # the command being pointed at an arbitrary folder.
    (root / "book_settings.json").write_text("{}", encoding="utf-8")
    return root


def _run(root: Path, surface: str, spoken: str):
    return _command_pronounce(
        argparse.Namespace(project_root=root, surface=surface, spoken=spoken, json=False)
    )


def _rows(root: Path) -> list[sqlite3.Row]:
    return ProjectDB(root / "project.sqlite3").list_pronunciations(0.0)


def test_it_pins_the_reading_and_locks_it(project: Path) -> None:
    result = _run(project, "Deck", "Deck")
    assert result.exit_code == 0
    assert result.data["locked"] is True
    row = next(row for row in _rows(project) if str(row["surface"]) == "Deck")
    assert str(row["spoken_form"]) == "Deck"
    assert int(row["locked"]) == 1


def test_a_human_decision_is_never_mistaken_for_a_machine_one(project: Path) -> None:
    _run(project, "Deck", "Deck")
    row = next(row for row in _rows(project) if str(row["surface"]) == "Deck")
    assert str(row["source"]) == LISTENER_PRONUNCIATION_SOURCE
    assert str(row["source"]) != "english_name_transliteration"
    assert float(row["confidence"]) == 1.0


def test_reading_the_name_as_written_is_allowed(project: Path) -> None:
    """The automatic validator rejects spoken == surface; a listener may still choose it."""
    assert _run(project, "Deck", "Deck").exit_code == 0


def test_it_replaces_an_earlier_choice_and_says_so(project: Path) -> None:
    _run(project, "Deck", "Đec")
    result = _run(project, "Deck", "Deck")
    assert result.data["replaced"] is True
    assert result.data["previous_spoken_form"] == "Đec"
    assert len([row for row in _rows(project) if str(row["surface"]) == "Deck"]) == 1


def test_empty_input_is_refused_rather_than_stored(project: Path) -> None:
    for surface, spoken in (("", "Deck"), ("Deck", ""), ("  ", "  ")):
        result = _run(project, surface, spoken)
        assert result.exit_code != 0
        assert result.error
    assert not _rows(project)


def test_the_decision_is_recorded_as_an_event(project: Path) -> None:
    _run(project, "Deck", "Deck")
    database = ProjectDB(project / "project.sqlite3")
    with database.connect() as conn:
        codes = [
            str(row[0])
            for row in conn.execute("SELECT code FROM runtime_events ORDER BY id")
        ]
    assert "PRONUNCIATION_SET_BY_LISTENER" in codes
