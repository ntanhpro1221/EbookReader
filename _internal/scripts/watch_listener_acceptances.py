"""Carry a listener's verdicts into a running project the moment they can apply.

`port_listener_acceptances.py` is correct but can only ever act on audio that already
exists, and a chapter is judged the moment its audio exists. That ordering is what cost
alpha.48 chapter 3: the verdict on `c00003_s0000029` had been given on 2026-09-04, the
audio it was given against came back byte-identical, and the chapter still failed - because
the port had not been run in the window between synthesis and verification, so ASR marked
the segment failed and three gates refused it. Running the port afterwards repaired it, but
only a resume can publish the chapter, and every remaining chapter with a waiting verdict
would have cost another one.

The window is real and it is wide. A chapter synthesizes every segment first, then unloads
TTS, then verifies the whole chapter with Whisper. Anything that lands in between is seen
by the verifier: `_listener_ruled_on_this_take` keeps the segment out of `mark_failed`, and
the chapter's warning gate skips a code a person has accepted. So the chapter publishes on
its first pass instead of failing and waiting for a human to resume it.

    python scripts/watch_listener_acceptances.py <source_project> <target_project>
                                                 [--interval 60] [--once]

It writes to a live database, so it does as little as it possibly can. Every cycle is a
read-only comparison; `ProjectDB` is constructed - and a write transaction taken - only in
the cycles where a verdict has actually become applicable, which over a ten-chapter run is
a handful of times rather than a hundred. It exits on its own when the run finishes.
"""
from __future__ import annotations

import json
import sqlite3
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.port_listener_acceptances import (  # noqa: E402
    _say_safely,
    port,
    read_acceptances,
    target_segment,
)

DEFAULT_INTERVAL_SECONDS = 60.0


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


def pending_verdicts(source: Path, target: Path) -> list[tuple[str, str, str]]:
    """Verdicts that would be carried right now and have not been carried yet.

    Read-only by construction: this is what decides whether the cycle is allowed to open a
    write transaction against a database a pipeline is using.
    """
    already = _target_acceptances(target)
    pending: list[tuple[str, str, str]] = []
    for stable_id, heard_checksum, code, _note in read_acceptances(source):
        if (stable_id, heard_checksum, code) in already:
            continue
        found = target_segment(target, stable_id)
        if found is None:
            continue
        checksum, warnings, _status = found
        if not checksum or checksum != heard_checksum or code not in warnings:
            continue
        pending.append((stable_id, heard_checksum, code))
    return pending


def run_is_over(target: Path) -> bool:
    """True once the background run has finished, so the watcher can stop by itself."""
    state_path = target / "runtime" / "background" / "state.json"
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        # No state file, or a half-written one: say nothing and look again next cycle.
        return False
    return str(state.get("state") or "") not in {"running", "starting"}


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
            "[--interval 60] [--once]"
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
