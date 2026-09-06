"""Carrying a verdict late is not the same as carrying it in time.

alpha.48 had the verdict, had byte-identical audio, and still failed chapter 3. Nothing was
broken: `port_listener_acceptances` can only act on audio that exists, and the chapter is
judged the moment its audio exists. The port ran afterwards, repaired the row, and the
chapter then needed a human to resume it before it could publish.

The watcher exists to land inside the window a chapter leaves open between synthesizing its
audio and verifying it. These tests pin the two things that makes it safe to point at a
database a pipeline is writing to: it decides read-only, and it carries a verdict once.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

from ebook_reader.database import ProjectDB

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import port_listener_acceptances as porter  # noqa: E402
import watch_listener_acceptances as watcher  # noqa: E402

def _a_pid_nobody_is_using() -> int:
    """A pid that is certainly not running, so "the worker is gone" can be tested."""
    import psutil

    for candidate in range(600000, 610000):
        if not psutil.pid_exists(candidate):
            return candidate
    raise AssertionError("no free pid found")


HEARD = "a" * 64
OTHER = "b" * 64
WARNING = "PERCEPTUAL_NATURALNESS_REVIEW"


def _project(root: Path, *, checksum: str | None, warning: str, status: str) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    db = ProjectDB(root / "project.sqlite3")
    db.initialize_book(
        title="Book",
        project_root=root,
        settings={},
        settings_hash="settings",
        input_manifest_hash="manifest",
    )
    chapter_id = db.ensure_chapters(
        [
            {
                "chapter_index": 1,
                "title": "One",
                "input_path": root / "one.txt",
                "input_sha256": "source",
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
                "text_sha256": "texthash",
                "kind_hint": "narration",
            }
        ],
    )
    with db.transaction() as conn:
        conn.execute(
            "UPDATE segments SET wav_sha256=?, warning_code=?, status=? WHERE stable_id='c1s1'",
            (checksum, warning, status),
        )
    return root


def _source(root: Path) -> Path:
    project = _project(root, checksum=HEARD, warning=WARNING, status="warning")
    ProjectDB(project / "project.sqlite3").accept_segment_audio(
        segment_stable_id="c1s1",
        wav_sha256=HEARD,
        warning_code=WARNING,
        note="chủ sách đã nghe: đọc đúng",
    )
    return project


def _synthesize(target: Path, checksum: str) -> None:
    """What the pipeline does to a segment just before it verifies the chapter."""
    with ProjectDB(target / "project.sqlite3").transaction() as conn:
        conn.execute(
            "UPDATE segments SET wav_sha256=?, status='warning' WHERE stable_id='c1s1'",
            (checksum,),
        )


def _lease(target: Path, *, pid: int, age_seconds: float = 0.0) -> None:
    """A running worker lease for `pid`, last heartbeat `age_seconds` ago.

    Age is a parameter only so a test can prove it is *ignored*. alpha.51 published chapters
    with a lease 2,380 seconds stale, so treating the heartbeat as liveness sent the watcher
    home three minutes into every run.
    """
    with ProjectDB(target / "project.sqlite3").transaction() as conn:
        conn.execute("DELETE FROM worker_leases")
        conn.execute(
            "INSERT INTO worker_leases(worker_name,pid,generation,state,heartbeat_at) "
            "VALUES('pipeline',?,1,'running',?)",
            (pid, time.time() - age_seconds),
        )


def test_nothing_is_pending_until_the_audio_exists(tmp_path: Path) -> None:
    """The whole reason a watcher is needed: the verdict is ready long before its audio."""
    source = _source(tmp_path / "old")
    target = _project(tmp_path / "new", checksum=None, warning=WARNING, status="pending")

    assert watcher.pending_verdicts(source, target) == []

    _synthesize(target, HEARD)

    assert watcher.pending_verdicts(source, target) == [("c1s1", HEARD, WARNING)]


def test_a_carried_verdict_stops_being_pending(tmp_path: Path) -> None:
    """This is what keeps the watcher off a live database. A verdict that is already
    carried must not read as work, or every cycle would open a write transaction against a
    project the pipeline is using."""
    source = _source(tmp_path / "old")
    target = _project(tmp_path / "new", checksum=HEARD, warning=WARNING, status="warning")

    assert watcher.pending_verdicts(source, target)

    porter.port(source, target)

    assert watcher.pending_verdicts(source, target) == []


def test_a_different_recording_is_never_pending(tmp_path: Path) -> None:
    """The watcher decides on its own before delegating, so it has to refuse for itself."""
    source = _source(tmp_path / "old")
    target = _project(tmp_path / "new", checksum=OTHER, warning=WARNING, status="warning")

    assert watcher.pending_verdicts(source, target) == []


def test_one_cycle_carries_what_is_ready_and_reports_it(tmp_path: Path) -> None:
    source = _source(tmp_path / "old")
    target = _project(tmp_path / "new", checksum=HEARD, warning=WARNING, status="warning")

    assert watcher.watch(source, target, once=True) == 1
    assert ProjectDB(target / "project.sqlite3").accepted_segment_warnings()


def test_a_cycle_with_nothing_ready_touches_nothing(tmp_path: Path) -> None:
    source = _source(tmp_path / "old")
    target = _project(tmp_path / "new", checksum=None, warning=WARNING, status="pending")

    assert watcher.watch(source, target, once=True) == 0
    assert ProjectDB(target / "project.sqlite3").accepted_segment_warnings() == {}


def test_the_watcher_stops_when_the_worker_process_goes(tmp_path: Path) -> None:
    """It is pointed at a running project and has to let go of it without being told."""
    target = _project(tmp_path / "new", checksum=HEARD, warning=WARNING, status="warning")

    _lease(target, pid=os.getpid())
    assert watcher.run_is_over(target) is False

    _lease(target, pid=_a_pid_nobody_is_using())
    assert watcher.run_is_over(target) is True


def test_a_stale_heartbeat_does_not_end_the_watch(tmp_path: Path) -> None:
    """The bug this replaced. alpha.51 was publishing chapters with a lease 2,380 seconds
    stale, and a watcher keyed on that heartbeat quit three minutes in and carried nothing
    for the rest of the run - silently, which is the worst way for this tool to fail."""
    target = _project(tmp_path / "new", checksum=HEARD, warning=WARNING, status="warning")

    _lease(target, pid=os.getpid(), age_seconds=4000)

    assert watcher.run_is_over(target) is False


def test_the_state_file_has_no_say(tmp_path: Path) -> None:
    """This is the whole point. Polling state.json every fifteen seconds is what killed
    alpha.50: on Windows the supervisor's rename onto an open file fails outright. So the
    file is left alone, and a state.json insisting the run is alive must change nothing."""
    target = _project(tmp_path / "new", checksum=HEARD, warning=WARNING, status="warning")
    directory = target / "runtime" / "background"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "state.json").write_text(json.dumps({"state": "running"}), encoding="utf-8")

    _lease(target, pid=_a_pid_nobody_is_using())

    assert watcher.run_is_over(target) is True


def test_a_project_with_no_lease_yet_is_not_read_as_finished(tmp_path: Path) -> None:
    """A run that has not written its first lease must not end the watch before it starts."""
    target = _project(tmp_path / "new", checksum=HEARD, warning=WARNING, status="warning")

    assert watcher.run_is_over(target) is False

    _lease(target, pid=os.getpid())

    assert watcher.run_is_over(target) is False
