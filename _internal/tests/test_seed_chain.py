"""Cái cuối chuỗi là cái để gieo, và "cuối" đo bằng `book.created_at`, không bằng mtime thư mục.

Đo 2026-09-10: `ls -dt` xếp `lo02_4d783ac744` trước ba project vá của nó, vì SQLite tạo và xoá
`-wal`/`-shm` mỗi lần ai đó mở DB và mtime thư mục đi theo. Một launcher tin `ls -dt` sẽ gieo lô
4 từ lô 3 thay vì từ project đúc lại giọng cuối cùng, và người vừa được đúc lại sẽ có giọng thứ
ba ở lô 4.
"""
from __future__ import annotations

import os
import sqlite3
from pathlib import Path

from scripts.seed_chain import batch_project, chain, repairs, seed_project


def _project(root: Path, tag: str, name: str, created: float) -> Path:
    folder = root / tag / name
    folder.mkdir(parents=True)
    conn = sqlite3.connect(str(folder / "project.sqlite3"))
    try:
        conn.execute("CREATE TABLE book (created_at REAL)")
        conn.execute("INSERT INTO book VALUES (?)", (created,))
        conn.commit()
    finally:
        conn.close()
    return folder


def _tree(root: Path) -> dict[str, Path]:
    made = {
        "lo01": _project(root, "v0.2.0-lo01", "lo01_a", 1.0),
        "lo01b": _project(root, "v0.2.0-lo01", "lo01b_b", 2.0),
        "lo02": _project(root, "v0.2.0-lo02", "lo02_c", 3.0),
        "lo02v_031": _project(root, "v0.2.0-lo02v", "lo02v_031_d", 4.0),
        "lo02v_043": _project(root, "v0.2.0-lo02v", "lo02v_043_e", 5.0),
        "lo02r_066": _project(root, "v0.2.0-lo02r", "lo02r_066_f", 6.0),
    }
    # Thư mục lô 2 "trẻ" nhất theo mtime - đúng cái bẫy đã đo - và không được tính.
    os.utime(made["lo02"], (9_999_999_999, 9_999_999_999))
    return made


def test_the_seed_is_the_last_repair_not_the_batch_with_the_freshest_mtime(tmp_path: Path) -> None:
    made = _tree(tmp_path)

    assert seed_project(2, tmp_path) == made["lo02r_066"]
    assert batch_project(2, tmp_path) == made["lo02"]


def test_batch_one_picks_the_rerun_inside_the_same_folder(tmp_path: Path) -> None:
    made = _tree(tmp_path)

    assert batch_project(1, tmp_path) == made["lo01b"]
    assert seed_project(1, tmp_path) == made["lo01b"]
    assert chain(1, tmp_path) == [made["lo01b"]]


def test_the_chain_ends_at_the_seed_and_lists_repairs_in_creation_order(tmp_path: Path) -> None:
    made = _tree(tmp_path)

    links = chain(2, tmp_path)

    assert links == [
        made["lo01b"],
        made["lo02"],
        made["lo02v_031"],
        made["lo02v_043"],
        made["lo02r_066"],
    ]
    assert links[-1] == seed_project(2, tmp_path)
    assert repairs(2, tmp_path) == links[2:]


def test_a_batch_with_nothing_yet_has_no_seed(tmp_path: Path) -> None:
    _tree(tmp_path)

    assert seed_project(3, tmp_path) is None
    assert chain(3, tmp_path) == [
        batch_project(1, tmp_path),
        batch_project(2, tmp_path),
    ], "chuỗi của lô chưa tồn tại là các lô trước nó - dùng để gieo lô ấy"
