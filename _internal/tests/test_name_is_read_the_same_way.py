"""Hai câu hỏi, hai cột: "thoả cổng neo tên" khác "được đọc giống nhau mỗi lần".

Lô 3 gắn cờ 170 đoạn vì neo tên, và trộn hai câu ấy làm một thì đọc 170 cờ thành 170 lỗi -
hoặc, tệ hơn, thành không lỗi nào. `Awakened` đọc giống nhau 66/66 lần mà trượt cổng 68 lần
(cổng sai); `Jake → Giếch` cho 89 dạng khác nhau trên 752 lần (dạng đọc đã ghim sai). Bài này
ghim đúng chỗ phân biệt ấy.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from scripts.name_is_read_the_same_way import (
    duplicate_ledger_rows,
    read_anchors,
)


def _project(root: Path, name: str, checks: list[list[dict[str, object]]]) -> Path:
    """Mỗi phần tử của `checks` là một phép kiểm, mang một danh sách neo."""
    folder = root / name
    folder.mkdir(parents=True)
    conn = sqlite3.connect(str(folder / "project.sqlite3"))
    try:
        conn.execute(
            "CREATE TABLE quality_checks (id INTEGER PRIMARY KEY, metrics_json TEXT,"
            " failure_codes_json TEXT)"
        )
        for anchors in checks:
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
    return folder


def _anchor(surface: str, spoken: str, *, matched: bool, heard: list[str]) -> dict[str, object]:
    return {
        "surface": surface,
        "spoken_form": spoken,
        "matched": matched,
        "aligned_tokens": heard,
    }


def test_a_name_read_the_same_way_every_time_scores_a_full_peak(tmp_path: Path) -> None:
    """Ca `Awakened`: cổng trượt mọi lần, mà giọng đọc chỉ có MỘT dạng - lỗi của cổng."""
    project = _project(
        tmp_path,
        "lo03",
        [[_anchor("Awakened", "Awakened", matched=False, heard=["awaken"])] for _ in range(20)],
    )

    anchors = read_anchors(project)
    row = anchors[("Awakened", "Awakened")]

    assert row["anchors"] == 20
    assert row["match_percent"] == 0.0
    assert row["distinct_forms"] == 1
    assert row["peak_percent"] == 100.0


def test_a_name_read_a_different_way_each_time_scores_a_low_peak(tmp_path: Path) -> None:
    """Ca `Jake → Giếch`: cùng một câu ra 'Giật' rồi 'Dịch' - hai âm, không phải hai chính tả."""
    heard = ["giết", "giếc", "kha", "giật", "dịch", "khe", "ha", "khả"]
    project = _project(
        tmp_path,
        "lo03",
        [[_anchor("Jake", "Giếch", matched=False, heard=[form])] for form in heard],
    )

    row = read_anchors(project)[("Jake", "Giếch")]

    assert row["distinct_forms"] == len(heard)
    assert row["peak_percent"] == 100.0 / len(heard)


def test_a_dropped_anchor_is_counted_apart_from_a_misread_one(tmp_path: Path) -> None:
    """Cửa sổ ghép rỗng nghĩa là bộ ghép coi neo bị BỎ HẲN - khác với đọc sai, nên đếm riêng."""
    project = _project(
        tmp_path,
        "lo03",
        [
            [_anchor("Rob", "Rốp", matched=False, heard=[])],
            [_anchor("Rob", "Rốp", matched=False, heard=[])],
            [_anchor("Rob", "Rốp", matched=False, heard=["rốt"])],
        ],
    )

    row = read_anchors(project)[("Rob", "Rốp")]

    assert row["dropped"] == 2
    assert row["distinct_forms"] == 1, "hai lần bỏ hẳn không phải một 'dạng đọc'"
    assert row["peak_percent"] == 100.0


def test_a_matched_anchor_contributes_to_match_percent_only(tmp_path: Path) -> None:
    project = _project(
        tmp_path,
        "lo03",
        [
            [_anchor("Michael", "Mai-cồ", matched=True, heard=[])],
            [_anchor("Michael", "Mai-cồ", matched=True, heard=[])],
            [_anchor("Michael", "Mai-cồ", matched=True, heard=[])],
            [_anchor("Michael", "Mai-cồ", matched=False, heard=["củ"])],
        ],
    )

    row = read_anchors(project)[("Michael", "Mai-cồ")]

    assert row["anchors"] == 4 and row["matched"] == 3
    assert row["match_percent"] == 75.0
    assert row["peak_percent"] == 100.0, "đỉnh% tính trên phần dư, nên nó nhỏ mẫu và vô hại"


def test_several_anchors_in_one_check_are_counted_separately(tmp_path: Path) -> None:
    project = _project(
        tmp_path,
        "lo03",
        [
            [
                _anchor("Jake", "Giếch", matched=False, heard=["giết"]),
                _anchor("Willem", "Guy-lem", matched=False, heard=["lem"]),
            ]
        ],
    )

    anchors = read_anchors(project)

    assert anchors[("Jake", "Giếch")]["anchors"] == 1
    assert anchors[("Willem", "Guy-lem")]["anchors"] == 1


def test_two_delivery_variants_of_one_name_are_reported_best_first(tmp_path: Path) -> None:
    """KHÔNG phải hai dòng trong sổ - sổ có đúng một dòng mỗi tên. Hai thứ được so là hai **biến
    thể giao** mà đường ống sinh cho mỗi đoạn: đọc theo dạng đã ghim (`Xa-men`, khớp 69%) và đọc
    thẳng chữ viết gốc (`Samael`, khớp 2%). Tôi đã đọc chúng thành hai dòng sổ và viết thế vào
    tài liệu trước khi chạy `SELECT * FROM pronunciations WHERE surface='Samael'`; có đúng một
    dòng. Tên hàm này giữ lại bài học ấy."""
    project = _project(
        tmp_path,
        "lo03",
        [[_anchor("Samael", "Xa-men", matched=True, heard=[])] for _ in range(7)]
        + [[_anchor("Samael", "Xa-men", matched=False, heard=["simon"])] for _ in range(3)]
        + [[_anchor("Samael", "Samael", matched=False, heard=["samuel"])] for _ in range(10)],
    )

    duplicates = duplicate_ledger_rows(read_anchors(project))

    assert list(duplicates) == ["Samael"]
    assert [row["spoken_form"] for row in duplicates["Samael"]] == ["Xa-men", "Samael"]
    assert duplicates["Samael"][0]["match_percent"] == 70.0


def test_a_project_without_anchor_checks_reads_as_empty(tmp_path: Path) -> None:
    project = _project(tmp_path, "lo03", [])

    assert read_anchors(project) == {}
    assert duplicate_ledger_rows({}) == {}
