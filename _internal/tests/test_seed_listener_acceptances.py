"""Carrying a verdict has been a race, and alpha.52 lost it by four seconds.

Chapter 3 failed at 11:46:00 over `c00003_s0000029`; the watcher carried that segment's
verdict at 11:46:04. The verdict was right, the checksum matched, and the chapter died
anyway - a fifteen-second poll cannot reliably win a window that short.

Seeding removes the race rather than tightening it. An acceptance is keyed by
(segment, checksum, code) and every gate compares it against the segment's *current*
checksum, so writing it before the audio exists is inert until matching audio appears - and
never matches anything if the take comes back different, which is the property `retry`
relies on.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

from ebook_reader.database import ProjectDB

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import seed_listener_acceptances as seeder  # noqa: E402

HEARD = "a" * 64
OTHER = "b" * 64
CODE = "ASR_LOCKED_NAME_ANCHOR_MISMATCH"


def _project(root: Path, *, checksum: str | None) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    db = ProjectDB(root / "project.sqlite3")
    db.initialize_book(
        title="Book",
        project_root=root,
        settings={},
        settings_hash="s",
        input_manifest_hash="m",
    )
    chapter_id = db.ensure_chapters(
        [
            {
                "chapter_index": 1,
                "title": "One",
                "input_path": root / "one.txt",
                "input_sha256": "src",
                "input_size": 1,
                "output_mp3": root / "one.mp3",
            }
        ]
    )[0]
    db.replace_chapter_segments(
        chapter_id,
        [
            {
                "stable_id": "c1s1",
                "seq": 0,
                "paragraph_index": 0,
                "text": "Một câu.",
                "text_sha256": "h0",
                "kind_hint": "narration",
            }
        ],
    )
    if checksum:
        with db.transaction() as conn:
            conn.execute(
                "UPDATE segments SET wav_sha256=?, warning_code=?, status='warning' "
                "WHERE stable_id='c1s1'",
                (checksum, CODE),
            )
    return root


def _source(root: Path) -> Path:
    project = _project(root, checksum=HEARD)
    ProjectDB(project / "project.sqlite3").accept_segment_audio(
        segment_stable_id="c1s1",
        wav_sha256=HEARD,
        warning_code=CODE,
        note="chủ sách đã nghe",
    )
    return project


def _recorded(project: Path) -> set[tuple[str, str]]:
    return set(ProjectDB(project / "project.sqlite3").accepted_segment_warnings())


def test_a_verdict_lands_before_the_audio_it_is_about(tmp_path: Path) -> None:
    """The whole point. The target has no audio at all yet."""
    source = _source(tmp_path / "old")
    target = _project(tmp_path / "new", checksum=None)

    assert seeder.seed(source, target) == (1, 0)
    assert ("c1s1", HEARD) in _recorded(target)


def test_a_seeded_verdict_applies_the_moment_matching_audio_arrives(tmp_path: Path) -> None:
    """No window to miss: the gate finds it already there."""
    source = _source(tmp_path / "old")
    target = _project(tmp_path / "new", checksum=None)
    seeder.seed(source, target)

    db = ProjectDB(target / "project.sqlite3")
    with db.transaction() as conn:
        conn.execute("UPDATE segments SET wav_sha256=? WHERE stable_id='c1s1'", (HEARD,))

    assert db.accepted_segment_warnings().get(("c1s1", HEARD)) == {CODE}


def test_a_seeded_verdict_is_inert_when_the_take_comes_back_different(tmp_path: Path) -> None:
    """Seeding early must not weaken what `retry` depends on: a verdict is about a
    recording, so different audio means no verdict."""
    source = _source(tmp_path / "old")
    target = _project(tmp_path / "new", checksum=None)
    seeder.seed(source, target)

    db = ProjectDB(target / "project.sqlite3")
    with db.transaction() as conn:
        conn.execute("UPDATE segments SET wav_sha256=? WHERE stable_id='c1s1'", (OTHER,))

    assert db.accepted_segment_warnings().get(("c1s1", OTHER)) is None


def test_seeding_twice_changes_nothing(tmp_path: Path) -> None:
    source = _source(tmp_path / "old")
    target = _project(tmp_path / "new", checksum=None)

    assert seeder.seed(source, target) == (1, 0)
    assert seeder.seed(source, target) == (0, 1)


def test_a_dry_run_writes_nothing(tmp_path: Path) -> None:
    source = _source(tmp_path / "old")
    target = _project(tmp_path / "new", checksum=None)

    assert seeder.seed(source, target, dry_run=True) == (1, 0)
    assert _recorded(target) == set()


def test_a_source_with_no_verdicts_is_reported_not_crashed(tmp_path: Path) -> None:
    source = _project(tmp_path / "old", checksum=HEARD)
    target = _project(tmp_path / "new", checksum=None)

    assert seeder.seed(source, target) == (0, 0)
