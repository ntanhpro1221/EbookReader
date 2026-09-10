"""Phòng thử cách đọc: đếm đúng, và **từ chối chạy** khi có lô đang bay.

Script này sinh audio thật, nên chạy nó song song với một lô là lấy GPU của lô ấy. Cửa từ chối
là phần quan trọng nhất ở đây - một công cụ đo mà làm chậm chính thứ nó đo thì vô dụng.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from scripts.try_a_pronunciation import heard_forms, report, slug


def _project(root: Path, anchors_per_check: list[list[dict[str, object]]]) -> Path:
    project = root / "pron_test"
    project.mkdir(parents=True)
    conn = sqlite3.connect(str(project / "project.sqlite3"))
    try:
        conn.execute(
            "CREATE TABLE quality_checks (id INTEGER PRIMARY KEY, metrics_json TEXT,"
            " failure_codes_json TEXT)"
        )
        for anchors in anchors_per_check:
            conn.execute(
                "INSERT INTO quality_checks (metrics_json, failure_codes_json) VALUES (?,?)",
                (
                    json.dumps({"locked_name_anchor_metrics": {"anchors": anchors}}),
                    json.dumps(["ASR_LOCKED_NAME_ANCHOR_REVIEW"]),
                ),
            )
        conn.commit()
    finally:
        conn.close()
    return project


def _anchor(surface: str, heard: list[str], *, matched: bool = False) -> dict[str, object]:
    return {"surface": surface, "matched": matched, "aligned_tokens": heard}


def test_it_counts_what_whisper_wrote_per_form(tmp_path: Path) -> None:
    project = _project(
        tmp_path,
        [
            [_anchor("Jake", ["giết"])],
            [_anchor("Jake", ["giết"])],
            [_anchor("Jake", ["giếc"])],
            [_anchor("Jake", [])],
            [_anchor("Jake", ["x"], matched=True)],
        ],
    )

    forms = heard_forms(project, "Jake")

    assert forms["giết"] == 2
    assert forms["giếc"] == 1
    assert forms["(bỏ hẳn)"] == 1, "cửa sổ ghép rỗng là 'neo bị bỏ', không phải một cách đọc"
    assert forms["(khớp cổng)"] == 1


def test_another_name_in_the_same_check_is_not_counted(tmp_path: Path) -> None:
    project = _project(tmp_path, [[_anchor("Jake", ["giết"]), _anchor("Willem", ["lem"])]])

    assert dict(heard_forms(project, "Jake")) == {"giết": 1}


def test_a_project_without_checks_counts_nothing(tmp_path: Path) -> None:
    assert heard_forms(_project(tmp_path, []), "Jake") == {}
    assert heard_forms(tmp_path / "khong-co", "Jake") == {}


def test_slug_keeps_folder_names_usable() -> None:
    """Cách đọc có dấu và gạch ngang phải thành tên thư mục hợp lệ mà vẫn phân biệt được nhau."""
    assert slug("Giếch") != slug("Giếc")
    assert slug("Giây-cơ") == "gi_y_c"
    assert slug("---") == "x", "không được trả về tên thư mục rỗng"


def test_report_says_so_when_nothing_has_been_run(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("scripts.try_a_pronunciation.LAB", tmp_path)

    assert report("Jake") == 1, "chưa chạy gì thì phải thoát khác 0, đừng in một bảng rỗng"
