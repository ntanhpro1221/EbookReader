from __future__ import annotations

import json
import os
import sys
import threading
from pathlib import Path
from queue import Empty, Queue
from typing import Any

from ebook_reader.database import ProjectDB
from ebook_reader.models import BookStatus, ProjectPaths
from ebook_reader.worker import run_worker


def _print_message(message: dict[str, Any]) -> None:
    print(json.dumps(message, ensure_ascii=False, default=str), flush=True)


def _drain_messages(message_queue: Queue, run_finished: threading.Event) -> None:
    while not run_finished.is_set() or not message_queue.empty():
        try:
            message = message_queue.get(timeout=1.0)
        except Empty:
            continue
        if isinstance(message, dict):
            try:
                _print_message(message)
            except Exception as exc:  # noqa: BLE001
                print(f"message_drain_error: {exc!r}", file=sys.stderr, flush=True)


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="replace")
    if len(sys.argv) != 2:
        print("Usage: run_book_job.py <project-root>", file=sys.stderr)
        return 64

    project_root = Path(sys.argv[1]).expanduser().resolve()
    paths = ProjectPaths.build(project_root)
    message_queue: Queue = Queue()
    pause_event = threading.Event()
    stop_event = threading.Event()
    run_finished = threading.Event()
    message_thread = threading.Thread(
        target=_drain_messages
        , args=(message_queue, run_finished)
        , name="ebook-reader-message-drain"
        , daemon=True
    )
    message_thread.start()

    _print_message({"kind": "runner_started", "pid": os.getpid(), "project_root": str(project_root)})
    try:
        run_worker(
            str(project_root)
            , message_queue
            , pause_event
            , stop_event
            , os.getpid()
        )
    finally:
        run_finished.set()
        message_thread.join(timeout=10.0)

    db = ProjectDB(paths.db)
    book = db.book()
    status = str(book["status"])
    _print_message(
        {
            "kind": "runner_finished"
            , "status": status
            , "stage": str(book["stage"])
            , "last_error": str(book["last_error"] or "")
        }
    )
    return 0 if status == BookStatus.COMPLETED.value else 2


if __name__ == "__main__":
    raise SystemExit(main())
