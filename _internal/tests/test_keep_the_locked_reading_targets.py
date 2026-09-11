"""`keep_the_locked_reading --book` chạm đúng chương mà sách SẼ lấy - người thắng theo `completed_at`.

Ở ranh giới, bước 4b đúc lại một chương xong rồi bước 6b mới đề cử lại; manifest của lần ghép trước
vẫn trỏ về project cũ. Ghép lại project cũ là đóng cho nó `completed_at` mới hơn bản đúc lại vừa
xong, và bước 7 lấy nhầm chương cũ. Nên lượt này phải hỏi đúng câu bước 7 hỏi.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from scripts.keep_the_locked_reading import shipped_projects


def _project(root: Path, name: str, chapters: list[tuple[str, float]]) -> Path:
    project = root / name
    (project / "output").mkdir(parents=True)
    conn = sqlite3.connect(str(project / "project.sqlite3"))
    try:
        conn.execute(
            "CREATE TABLE chapters (id INTEGER PRIMARY KEY, title TEXT, status TEXT,"
            " output_mp3 TEXT, completed_at REAL)"
        )
        for title, completed_at in chapters:
            mp3 = project / "output" / f"{title}.mp3"
            mp3.write_bytes(b"x" * 16)
            conn.execute(
                "INSERT INTO chapters (title, status, output_mp3, completed_at) VALUES (?,?,?,?)",
                (title, "completed", str(mp3), completed_at),
            )
        conn.commit()
    finally:
        conn.close()
    return project


def test_the_newest_completed_project_owns_the_chapter(tmp_path: Path) -> None:
    versions = tmp_path / "_versions"
    old = _project(versions / "v0.2.0-lo02v", "lo02v_031_x", [("031", 100.0)])
    batch = _project(versions / "v0.2.0-lo02", "lo02_x", [("031", 50.0), ("032", 60.0)])
    recast = _project(versions / "v0.2.0-lo02r", "lo02r_031_x", [("031", 200.0)])

    targets = shipped_projects(versions=versions)

    assert targets == {recast: {"031"}, batch: {"032"}}
    assert old not in targets, "bản cũ của 031 không được ghép lại - nó sẽ đoạt lại chỗ trong sách"


def test_a_completed_row_without_its_mp3_does_not_count(tmp_path: Path) -> None:
    versions = tmp_path / "_versions"
    newer = _project(versions / "v0.2.0-lo02r", "lo02r_031_x", [("031", 200.0)])
    (newer / "output" / "031.mp3").unlink()
    older = _project(versions / "v0.2.0-lo02", "lo02_x", [("031", 50.0)])

    assert shipped_projects(versions=versions) == {older: {"031"}}
