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

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ebook_reader.background_runner import get_status, start_background  # noqa: E402

DEFAULT_VERSIONS_ROOT = Path("D:/Novels/Audiobooks/_versions")
RESUMABLE_STATE = "lost"


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


def main(argv: list[str]) -> int:
    dry_run = "--dry-run" in argv
    positional = [value for value in argv if not value.startswith("--")]
    root = Path(positional[0]) if positional else DEFAULT_VERSIONS_ROOT

    projects = projects_under(root)
    if not projects:
        print(f"không tìm thấy project nào dưới {root}")
        return 0

    resumed = 0
    for project in projects:
        status = get_status(project)
        label = f"{project.parent.name}/{project.name}"
        if status.stop_requested:
            print(f"  bỏ qua  {label}: đã có yêu cầu dừng, không tự chạy lại")
            continue
        if str(status.state) != RESUMABLE_STATE:
            print(f"  bỏ qua  {label}: trạng thái {status.state}")
            continue
        detail = str(status.detail or "").strip()
        print(f"  TIẾP TỤC {label}: {detail or 'bị ngắt giữa chừng'}")
        if dry_run:
            resumed += 1
            continue
        try:
            start_background(project)
            resumed += 1
        except Exception as error:  # noqa: BLE001 - one bad project must not stop the rest
            print(f"     không chạy lại được: {error!r}")

    print(f"{len(projects)} project, {resumed} được chạy tiếp{' (thử khan)' if dry_run else ''}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
