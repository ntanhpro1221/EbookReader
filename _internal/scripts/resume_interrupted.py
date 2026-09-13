"""Restart any book that was running when the machine went away.

The pipeline checkpoints constantly and `resume` picks up where it stopped, so nothing is
lost to a shutdown - but nothing pressed the button either. The supervisor runs one worker
and exits when that worker dies, and there is no entry in Task Scheduler or the startup
folder. So a machine that slept, hibernated or restarted mid-book left it stopped until
somebody noticed.

Detecting an interrupted run needs no PID handling here: get_status already validates the
recorded supervisor against the process actually holding that id, and reports "lost" when
the record says active but the process is gone. That is exactly the state this looks for.

Deliberately narrow about what it will restart:
  - "lost" only. A finished book is not active, so it can never be lost, and a running one
    is left alone.
  - never after a stop request. Someone asking a run to stop and having it come back after
    a reboot would be worse than the problem being solved.

    python scripts/resume_interrupted.py [versions_root] [--dry-run]

Written for Task Scheduler at logon; safe to run by hand at any time.
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import datetime as _dt  # noqa: E402

from ebook_reader.background_runner import get_status, start_background  # noqa: E402

try:
    from scripts.book_paths import VERSIONS as _BOOK_VERSIONS  # noqa: E402
except ImportError:  # chạy trực tiếp: python scripts/x.py
    from book_paths import VERSIONS as _BOOK_VERSIONS  # noqa: E402
DEFAULT_VERSIONS_ROOT = _BOOK_VERSIONS
LOG_NAME = "_auto_resume.log"

# Two different interruptions, and the state file distinguishes them.
#
# "lost": the machine went away and took the process with it. get_status reports this when
# the record says active but the process holding that pid is gone.
#
# "stopped" + gpu_context_lost: the process is alive but its CUDA context died under it,
# which is what suspending the machine does. The worker cannot rebuild a context it lost,
# so it ends the run as a clean stop and asks for a fresh process. It looks exactly like a
# stop somebody requested, which is why the marker matters - see _wants_a_fresh_process.
RESUMABLE_STATE = "lost"
SELF_STOPPED_STATE = "stopped"
GPU_CONTEXT_LOST_KEY = "gpu_context_lost"


def _wants_a_fresh_process(status) -> bool:
    """A stop nobody asked for, because the GPU context died and only a new process fixes it."""
    if str(status.state) != SELF_STOPPED_STATE:
        return False
    last_event = status.last_event
    if not isinstance(last_event, dict):
        return False
    return bool(last_event.get(GPU_CONTEXT_LOST_KEY))


def _say_safely(line: str) -> None:
    """Print without letting the console's encoding decide whether the book resumes.

    Every message here is Vietnamese and Windows hands scripts a cp1252 stdout more
    often than not - Task Scheduler included - where printing raises UnicodeEncodeError.
    Losing a night of audio because a console could not render "bỏ qua" would be absurd.
    """
    try:
        print(line)
    except (UnicodeEncodeError, OSError, ValueError):
        try:
            sys.stdout.buffer.write(line.encode("utf-8", "replace") + b"\n")
        except Exception:  # noqa: BLE001 - stdout may be closed entirely under pythonw
            pass


def _log_line(root: Path, line: str) -> None:
    """Nobody is watching stdout at logon, so leave a trail beside the projects.

    Outside the repo, and a file rather than a directory so the version scan skips it.
    A logging failure must never be the reason a book fails to resume.
    """
    stamp = _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        with (root / LOG_NAME).open("a", encoding="utf-8") as handle:
            handle.write(f"{stamp}  {line}\n")
    except OSError:
        pass


def projects_under(root: Path) -> list[Path]:
    """Every project directory: a version folder holds one project folder holding the db."""
    found: list[Path] = []
    if not root.is_dir():
        return found
    for version in sorted(root.iterdir()):
        if not version.is_dir():
            continue
        for candidate in sorted(version.iterdir()):
            if (candidate / "project.sqlite3").is_file():
                found.append(candidate)
    return found


def pending_analysis_count(project: Path) -> int:
    """How many segments are still unanalysed, or -1 when it cannot be read.

    A resume that lands inside the analysis phase does not merely continue - it changes what
    the analysis produces. The interrupted group is re-analysed as a fragment of itself with
    truncated neighbour context, so speakers are assigned differently, the character registry
    shifts, casting shifts with it, and every listener verdict on the affected audio dies.
    Proven by controlled experiment on 2026-09-07: one stop at 620/948 took the character
    count from 23 to 19, with all 18 speaker changes after the interruption point.

    The watchdog still resumes - a run lying dead until morning is worse than a slightly
    different book - but the fact has to be on the record, or the next person comparing two
    versions spends three hours discovering it again, as I did.
    """
    database = project / "project.sqlite3"
    if not database.is_file():
        return -1
    connection = sqlite3.connect(f"file:{database}?mode=ro", uri=True)
    try:
        row = connection.execute(
            "SELECT COUNT(*) FROM segments WHERE status='pending'"
        ).fetchone()
        return int(row[0]) if row else -1
    except sqlite3.OperationalError:
        return -1
    finally:
        connection.close()


def main(argv: list[str]) -> int:
    dry_run = "--dry-run" in argv
    positional = [value for value in argv if not value.startswith("--")]
    root = Path(positional[0]) if positional else DEFAULT_VERSIONS_ROOT

    def say(line: str) -> None:
        # Log first: printing is the fragile half, and a print that dies must not
        # take the record with it. Every line here contains Vietnamese, and a
        # console this lands on may be cp1252 - Task Scheduler's especially.
        _log_line(root, line)
        _say_safely(line)

    projects = projects_under(root)
    if not projects:
        _say_safely(f"không tìm thấy project nào dưới {root}")
        return 0

    resumed = 0
    for project in projects:
        status = get_status(project)
        label = f"{project.parent.name}/{project.name}"
        if status.stop_requested:
            say(f"  bỏ qua  {label}: đã có yêu cầu dừng, không tự chạy lại")
            continue
        if str(status.state) != RESUMABLE_STATE and not _wants_a_fresh_process(status):
            say(f"  bỏ qua  {label}: trạng thái {status.state}")
            continue
        detail = str(status.detail or "").strip()
        say(f"  TIẾP TỤC {label}: {detail or 'bị ngắt giữa chừng'}")
        unanalysed = pending_analysis_count(project)
        if unanalysed > 0:
            say(
                f"     CẢNH BÁO: còn {unanalysed} đoạn chưa phân tích, nên lần resume này "
                "rơi vào GIỮA PHA PHÂN TÍCH. Bản phân tích sẽ khác bản chạy liền mạch: "
                "người nói, sổ nhân vật, casting và audio đều có thể đổi, và phán quyết "
                "của người nghe trên những đoạn ấy hết hiệu lực. Xem VERSIONS.md."
            )
        if dry_run:
            resumed += 1
            continue
        try:
            start_background(project)
            resumed += 1
        except Exception as error:  # noqa: BLE001 - one bad project must not stop the rest
            say(f"     không chạy lại được: {error!r}")

    say(f"{len(projects)} project, {resumed} được chạy tiếp{' (thử khan)' if dry_run else ''}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
