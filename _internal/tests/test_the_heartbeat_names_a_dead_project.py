"""Nhịp tim phải nói ra project đã CHẾT hoặc ĐỨNG IM - lô 7 chết 22:41 ngày 18-09 mà nhịp 23:06 im lặng."""
from __future__ import annotations

import os
import sqlite3
import time
from pathlib import Path

import scripts.heartbeat_tick as tick


def _project(root: Path, name: str, status: str, stage: str, error: str | None, idle_minutes: float) -> None:
    folder = root / "v0.3.0-lo07" / name
    folder.mkdir(parents=True)
    database = folder / "project.sqlite3"
    connection = sqlite3.connect(database)
    connection.execute("CREATE TABLE book (status TEXT, stage TEXT, last_error TEXT)")
    connection.execute("INSERT INTO book VALUES (?, ?, ?)", (status, stage, error))
    connection.commit()
    connection.close()
    stamp = time.time() - idle_minutes * 60
    os.utime(database, (stamp, stamp))


def test_a_dead_or_stalled_project_is_named_and_a_finished_one_is_not(tmp_path: Path) -> None:
    _project(tmp_path, "lo07_dead", "error", "unrecoverable_error",
             "Voice profile narrator is locked and cannot change during resume", 25)
    _project(tmp_path, "lo07_stalled", "synthesizing", "chapter_synthesis", None, 111)
    _project(tmp_path, "lo06_done", "completed", "completed", None, 60)
    _project(tmp_path, "lo07_flying", "synthesizing", "chapter_synthesis", None, 1)
    _project(tmp_path, "lo01_old_error", "error", "x", "cu", 60 * 30)
    # Lô đã xong kèm chương hỏng, bị ranh giới ghi sổ vào 8 giờ trước: không phải một lượt chết.
    _project(tmp_path, "lo01_c0d8", "error", "completed_with_errors", "1 chapter chưa thể xuất MP3", 485)

    lines = tick.stopped(tmp_path)

    assert len(lines) == 2
    dead = next(line for line in lines if "lo07_dead" in line)
    assert dead.startswith("CHẾT") and "narrator is locked" in dead and "25 phút" in dead
    assert next(line for line in lines if "lo07_stalled" in line).startswith("ĐỨNG IM")
