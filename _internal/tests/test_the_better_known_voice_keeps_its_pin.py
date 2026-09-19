"""Hai người cùng ghim một giọng gặp nhau: người quen hơn TRÊN CẢ CUỐN giữ giọng (lô 8, VICTOR/MORRIS)."""
from __future__ import annotations

import sqlite3
from pathlib import Path

from ebook_reader.character_registry import _book_exposure, _drop_pins_that_share_a_chapter

VOICE = "preset_thai_son_f100_p+00"


def _rows() -> list[dict]:
    # Lô 8, chương 18 của project: VICTOR 1 câu, MORRIS 3 câu, cùng chương, cùng giọng đã ghim.
    return [
        {"speaker": "VICTOR", "chapter_id": 18},
        {"speaker": "MORRIS", "chapter_id": 18},
        {"speaker": "MORRIS", "chapter_id": 18},
        {"speaker": "MORRIS", "chapter_id": 19},
    ]


def test_without_a_ledger_the_one_with_more_lines_in_the_batch_keeps_it() -> None:
    kept = _drop_pins_that_share_a_chapter(_rows(), {"VICTOR": VOICE, "MORRIS": VOICE}, lambda _m: None)
    assert kept == {"MORRIS": VOICE}


def test_with_the_ledger_the_better_known_person_keeps_it() -> None:
    said: list[str] = []
    kept = _drop_pins_that_share_a_chapter(
        _rows(), {"VICTOR": VOICE, "MORRIS": VOICE}, said.append, exposure={"VICTOR": 329, "MORRIS": 54}
    )
    assert kept == {"VICTOR": VOICE}
    assert said and "MORRIS" in said[0] and "54 cả cuốn" in said[0] and "329 cả cuốn" in said[0]


class _DB:
    def __init__(self, path: Path) -> None:
        self.path = path

    def connect(self):
        return sqlite3.connect(self.path)


def test_the_ledger_is_read_by_canonical_key_and_is_optional(tmp_path: Path) -> None:
    database = tmp_path / "project.sqlite3"
    connection = sqlite3.connect(database)
    connection.execute("CREATE TABLE character_exposure (canonical_name TEXT, dialogue_lines INT, batches INT)")
    connection.executemany("INSERT INTO character_exposure VALUES (?, ?, ?)", [("Victor", 329, 18), ("MORRIS", 54, 5)])
    connection.commit()
    connection.close()

    assert _book_exposure(_DB(database)) == {"VICTOR": 329, "MORRIS": 54}
    assert _book_exposure(_DB(tmp_path / "empty.sqlite3")) == {}
    assert _book_exposure(object()) == {}
