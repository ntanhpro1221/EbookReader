"""Time is attributed the way a sequential pipeline spends it, or not at all.

quality_checks has no duration column - it records when each piece of evidence was written,
not how long producing it took. The cost of a stage is therefore inferred, and every way of
inferring it wrong has already been hit once: a gap that spans a pause reported hours of
work for a two-segment chapter, and a per-segment check that leaves chapter_id NULL made
99.8% of the rows invisible.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from scripts.stage_costs import MAX_ATTRIBUTABLE_GAP_SECONDS, read_costs


def _database(tmp_path: Path, rows: list[tuple]) -> Path:
    """A project with just the two tables this reads, and the columns it names."""
    path = tmp_path / "project.sqlite3"
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        CREATE TABLE segments (id INTEGER PRIMARY KEY, chapter_id INTEGER);
        CREATE TABLE quality_checks (
            id INTEGER PRIMARY KEY,
            chapter_id INTEGER,
            segment_id INTEGER,
            stage TEXT,
            created_at TEXT
        );
        """
    )
    for segment_id, chapter_id in {(row[1], row[0]) for row in rows if row[1] is not None}:
        connection.execute(
            "INSERT OR IGNORE INTO segments (id, chapter_id) VALUES (?, ?)",
            (segment_id, chapter_id),
        )
    for index, (chapter_id, segment_id, stage, created_at) in enumerate(rows, 1):
        connection.execute(
            "INSERT INTO quality_checks (id, chapter_id, segment_id, stage, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (index, None if segment_id is not None else chapter_id, segment_id, stage, str(created_at)),
        )
    connection.commit()
    connection.close()
    return path


def test_a_gap_belongs_to_the_stage_that_ended_it(tmp_path) -> None:
    """The work happened between the two rows, and the second row is what it produced."""
    database = _database(
        tmp_path,
        [
            (1, 10, "asr", 1000.0),
            (1, 11, "asr", 1010.0),
            (1, 12, "perceptual", 1030.0),
        ],
    )
    seconds, counts, _per_chapter = read_costs(database)

    assert seconds["asr"] == 10.0
    assert seconds["perceptual"] == 20.0
    assert counts == {"asr": 2, "perceptual": 1}


def test_a_pause_between_phases_is_not_charged_to_a_stage(tmp_path) -> None:
    """The failure this guard exists for: a two-segment chapter reported hours of TTS
    because the gap it was given spanned the machine being idle."""
    database = _database(
        tmp_path,
        [
            (1, 10, "asr", 1000.0),
            (1, 11, "asr", 1000.0 + MAX_ATTRIBUTABLE_GAP_SECONDS + 1),
        ],
    )
    seconds, _counts, _per_chapter = read_costs(database)
    assert seconds.get("asr", 0.0) == 0.0


def test_the_gap_between_two_chapters_belongs_to_neither(tmp_path) -> None:
    database = _database(
        tmp_path,
        [
            (1, 10, "asr", 1000.0),
            (2, 20, "asr", 1005.0),
            (2, 21, "asr", 1008.0),
        ],
    )
    seconds, _counts, per_chapter = read_costs(database)

    assert seconds["asr"] == 3.0, "only the within-chapter gap counts"
    assert 1 not in per_chapter
    assert per_chapter[2]["asr"] == 3.0


def test_a_check_that_names_only_a_segment_still_finds_its_chapter(tmp_path) -> None:
    """Per-segment checks leave chapter_id NULL. Reading chapter_id alone found ten rows
    out of four thousand and reported that the run cost nothing."""
    database = _database(
        tmp_path,
        [
            (3, 30, "asr", 2000.0),
            (3, 31, "asr", 2004.0),
        ],
    )
    seconds, _counts, per_chapter = read_costs(database)

    assert per_chapter[3]["asr"] == 4.0
    assert seconds["asr"] == 4.0


def test_time_running_backwards_is_ignored_rather_than_subtracted(tmp_path) -> None:
    """Rows written in the same second can be ordered arbitrarily by the query; a negative
    gap must not be able to reduce a stage's measured cost."""
    database = _database(
        tmp_path,
        [
            (1, 10, "asr", 1000.0),
            (1, 11, "asr", 999.0),
            (1, 12, "asr", 1002.0),
        ],
    )
    seconds, _counts, _per_chapter = read_costs(database)
    assert seconds["asr"] >= 0.0
