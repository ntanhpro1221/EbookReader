"""Carry a listener's verdicts into a running project the moment they can apply.

`port_listener_acceptances.py` is correct but can only ever act on audio that already
exists, and a chapter is judged the moment its audio exists. That ordering is what cost
alpha.48 chapter 3: the verdict on `c00003_s0000029` had been given on 2026-09-04, the
audio it was given against came back byte-identical, and the chapter still failed - because
the port had not been run in the window between synthesis and verification, so ASR marked
the segment failed and three gates refused it. Running the port afterwards repaired it, but
only a resume can publish the chapter, and every remaining chapter with a waiting verdict
would have cost another one.

The window differs by which warning is waiting, and the narrow one sets the poll interval.

An ASR anchor mismatch is raised while Whisper verifies the chapter, and the chapter's gate
is minutes of repair rounds later - wide. A perceptual review is raised near the end: scored,
sent to the repair loop, and gated. The repair loop re-cuts and re-verifies, so it is still
minutes rather than seconds, but it is the narrow case and it is why every cycle here is one
connection and one query instead of a connection per verdict.

Anything that lands inside either window is seen by the gates: `_listener_ruled_on_this_take`
keeps the segment out of `mark_failed`, and the chapter's warning gate skips a code a person
has accepted. So the chapter publishes on its first pass instead of failing and waiting for
a human to resume it. Missing the window is not a failure - it costs a resume, which is what
happened before this existed.

    python scripts/watch_listener_acceptances.py <source_project> <target_project>
                                                 [--interval 15] [--once]

It writes to a live database, so it does as little as it possibly can. Every cycle is a
read-only comparison; `ProjectDB` is constructed - and a write transaction taken - only in
the cycles where a verdict has actually become applicable, which over a ten-chapter run is
a handful of times rather than a hundred. It exits on its own when the run finishes.
"""
from __future__ import annotations

import sqlite3
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.port_listener_acceptances import (  # noqa: E402
    _say_safely,
    port,
    read_acceptances,
)

DEFAULT_INTERVAL_SECONDS = 15.0


def _target_acceptances(project: Path) -> set[tuple[str, str, str]]:
    """The (segment, checksum, code) triples this project already holds."""
    connection = sqlite3.connect(f"file:{project / 'project.sqlite3'}?mode=ro", uri=True)
    try:
        return {
            (str(a), str(b), str(c))
            for a, b, c in connection.execute(
                "SELECT segment_stable_id, wav_sha256, warning_code "
                "FROM listener_audio_acceptances"
            )
        }
    except sqlite3.OperationalError:
        # The table arrives with the schema; a project mid-creation simply has nothing yet.
        return set()
    finally:
        connection.close()


def _target_segments(project: Path, stable_ids: list[str]) -> dict[str, tuple[str, set[str]]]:
    """(wav_sha256, warnings) for the segments a verdict could apply to, in one read.

    `port_listener_acceptances.target_segment` opens a connection per segment, which is
    right for a command a person runs a few times. This runs every few seconds against a
    database a pipeline is writing to, so the whole cycle is one connection and one query.
    """
    if not stable_ids:
        return {}
    connection = sqlite3.connect(f"file:{project / 'project.sqlite3'}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        placeholders = ",".join("?" * len(stable_ids))
        rows = connection.execute(
            f"SELECT stable_id, wav_sha256, warning_code FROM segments "
            f"WHERE stable_id IN ({placeholders})",
            stable_ids,
        ).fetchall()
    finally:
        connection.close()
    return {
        str(row["stable_id"]): (
            str(row["wav_sha256"] or ""),
            {value for value in str(row["warning_code"] or "").split("|") if value},
        )
        for row in rows
    }


def pending_verdicts(source: Path, target: Path) -> list[tuple[str, str, str]]:
    """Verdicts that would be carried right now and have not been carried yet.

    Read-only by construction: this is what decides whether the cycle is allowed to open a
    write transaction against a database a pipeline is using.
    """
    already = _target_acceptances(target)
    waiting = [
        (stable_id, heard_checksum, code)
        for stable_id, heard_checksum, code, _note in read_acceptances(source)
        if (stable_id, heard_checksum, code) not in already
    ]
    segments = _target_segments(target, sorted({item[0] for item in waiting}))
    pending: list[tuple[str, str, str]] = []
    for stable_id, heard_checksum, code in waiting:
        checksum, warnings = segments.get(stable_id, ("", set()))
        if not checksum or checksum != heard_checksum or code not in warnings:
            continue
        pending.append((stable_id, heard_checksum, code))
    return pending


# Whether the worker process is alive, asked of the operating system. Two earlier signals
# were wrong: `state.json` cannot be polled without breaking the supervisor's own writes on
# Windows, and the lease heartbeat is not a liveness signal at all - alpha.51 was publishing
# chapters with a lease 2,380 seconds stale, which sent this watcher home three minutes into
# every run. The pid is read from SQLite, so nothing here opens a file the pipeline writes.


def _process_is_alive(pid: int) -> bool:
    """Ask the OS, because every cheaper signal in this project has turned out to lie."""
    if pid <= 0:
        return False
    try:
        import psutil
    except ImportError:
        # Without psutil, keep watching rather than guess: an extra cycle costs a read, and
        # a wrong "it finished" costs every verdict the rest of the run would have carried.
        return True
    try:
        process = psutil.Process(pid)
        return process.is_running() and process.status() != psutil.STATUS_ZOMBIE
    except psutil.NoSuchProcess:
        return False
    except psutil.Error:
        return True


def run_is_over(target: Path) -> bool:
    """True once the background run has finished, so the watcher can stop by itself.

    Deliberately does **not** read `runtime/background/state.json`. On Windows a rename onto
    an open file fails, so polling that file every fifteen seconds eventually lands inside
    the supervisor's own write and kills the run with

        PermissionError: [WinError 5] Access is denied: 'state.json.part' -> 'state.json'

    which is exactly how alpha.50 died 44 minutes into its analysis, at the hand of this
    watcher.

    The replacement was wrong too, and worse for being quiet. I used the lease heartbeat and
    wrote that "the pipeline heartbeats far more often" than the three-minute margin. It does
    not: alpha.51 was publishing chapters with a lease 2,380 seconds stale, so the watcher
    went home three minutes into the run and every verdict after that went uncarried. A
    watcher that quits early fails in silence, which is the worst way for this particular
    tool to fail.

    So ask the operating system whether the worker process is alive. The pid comes from
    SQLite - built for concurrent readers - and no file the pipeline writes is ever opened.
    """
    database = target / "project.sqlite3"
    if not database.is_file():
        return False
    connection = sqlite3.connect(f"file:{database}?mode=ro", uri=True)
    try:
        row = connection.execute(
            "SELECT pid FROM worker_leases WHERE state='running' ORDER BY heartbeat_at DESC "
            "LIMIT 1"
        ).fetchone()
    except sqlite3.OperationalError:
        return False
    finally:
        connection.close()
    if row is None or row[0] is None:
        # No running lease recorded yet. A project that has not started must not be read as
        # one that has finished, or the watcher quits before the run it was pointed at.
        return False
    return not _process_is_alive(int(row[0]))


def watch(
    source: Path,
    target: Path,
    *,
    interval: float = DEFAULT_INTERVAL_SECONDS,
    once: bool = False,
) -> int:
    """Poll until the run ends. Returns how many verdicts were carried in total."""
    carried_total = 0
    while True:
        pending = pending_verdicts(source, target)
        if pending:
            names = ", ".join(f"{sid} [{code}]" for sid, _sha, code in pending)
            _say_safely(f"{time.strftime('%H:%M:%S')} chuyển được {len(pending)}: {names}")
            carried, _examined = port(source, target)
            carried_total += carried
        if once:
            return carried_total
        if run_is_over(target):
            _say_safely(
                f"{time.strftime('%H:%M:%S')} run đã dừng; tổng cộng chuyển {carried_total}"
            )
            return carried_total
        time.sleep(interval)


def main(argv: list[str]) -> int:
    once = "--once" in argv
    interval = DEFAULT_INTERVAL_SECONDS
    for index, value in enumerate(argv):
        if value == "--interval" and index + 1 < len(argv):
            interval = float(argv[index + 1])
    positional = [
        value
        for index, value in enumerate(argv)
        if not value.startswith("--") and not (index and argv[index - 1] == "--interval")
    ]
    if len(positional) != 2:
        _say_safely(
            "dùng: watch_listener_acceptances.py <project nguồn> <project đích> "
            "[--interval 15] [--once]"
        )
        return 2
    source = Path(positional[0]).resolve()
    target = Path(positional[1]).resolve()
    for project in (source, target):
        if not (project / "project.sqlite3").exists():
            _say_safely(f"không phải project: {project}")
            return 2
    watch(source, target, interval=interval, once=once)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
