"""Cuốn sách là quan toà: cách viết có trong nguồn thắng cách viết không có.

Lô 3 gộp `SELNE VALKRYN` → `SELNE` theo số câu thoại (32 so với 3), và người thắng là **lỗi
chính tả của model**: nguồn có `Selene` 198 lần và `Selne` 0 lần. Số câu đã bị vòng phản hồi làm
nhiễm; nguồn thì không. Trên 30 nhân vật có tên của lô 3, đúng 4 tên có 0 lần trong nguồn và
không nhân vật thật nào có 0.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from scripts.source_spellings import (
    fold,
    fold_to_source_spelling,
    occurrences,
    source_paths,
    source_text,
)

# Đúng tỉ lệ lô 3: bản sai nói nhiều hơn bản đúng.
LINES = {"SELNE": 32, "SELENE": 7, "SELNE VALKRYN": 3, "SAMAEL": 19, "SAMAELE": 1}


def _book(root: Path, chapters: dict[str, str]) -> Path:
    """Thư mục nguồn + một project trỏ tới nó, giống bố cục thật."""
    text_dir = root / "Text"
    text_dir.mkdir(parents=True)
    for name, body in chapters.items():
        (text_dir / f"{name}.txt").write_text(body, encoding="utf-8")
    project = root / "lo03"
    project.mkdir()
    conn = sqlite3.connect(str(project / "project.sqlite3"))
    try:
        conn.execute("CREATE TABLE chapters (id INTEGER PRIMARY KEY, input_path TEXT)")
        conn.executemany(
            "INSERT INTO chapters (input_path) VALUES (?)",
            [(str(text_dir / f"{name}.txt"),) for name in chapters],
        )
        conn.commit()
    finally:
        conn.close()
    return project


def test_the_misspelling_loses_to_the_spelling_in_the_book(tmp_path: Path) -> None:
    project = _book(
        tmp_path,
        {
            "000": "Selene bước vào. " * 20,
            "001": "Samael nhìn Selene. " * 20,
        },
    )
    text = source_text(project)

    assert occurrences("Selene", text) == 40
    assert occurrences("Selne", text) == 0

    folded = fold_to_source_spelling(
        ["SELNE", "SELENE", "SELNE VALKRYN", "SAMAEL", "SAMAELE"], text, LINES
    )

    assert folded == {
        "SELNE": "SELENE",
        "SELNE VALKRYN": "SELENE",
        "SAMAELE": "SAMAEL",
    }, "số câu thoại KHÔNG được quyết: bản sai nói nhiều hơn ở cả hai cặp"


def test_two_real_characters_one_letter_apart_are_left_alone(tmp_path: Path) -> None:
    """`SỐ BA` và `SỐ BẢY` lệch một ký tự sau khi bỏ dấu, và là hai người. Cả hai có trong
    nguồn, nên luật này im lặng - đây là bài quan trọng nhất trong file."""
    project = _book(tmp_path, {"000": "Số Ba nói. Số Bảy đáp. " * 5})
    text = source_text(project)

    assert occurrences("SỐ BA", text) > 0 and occurrences("SỐ BẢY", text) > 0
    assert fold_to_source_spelling(["SỐ BA", "SỐ BẢY"], text, {"SỐ BA": 2, "SỐ BẢY": 7}) == {}


def test_a_name_the_book_never_writes_and_has_no_neighbour_stays(tmp_path: Path) -> None:
    """`NARRATOR` không có trong nguồn và không gần tên nào - để nguyên, đừng gộp bừa."""
    project = _book(tmp_path, {"000": "Selene bước vào. " * 5})
    text = source_text(project)

    assert fold_to_source_spelling(["NARRATOR", "SELENE"], text, {}) == {}


def test_both_spellings_absent_means_this_rule_says_nothing(tmp_path: Path) -> None:
    """`THU LÃNH` / `THỦ LÃNH` là nhãn model tự đặt. Bỏ dấu thì cả hai trỏ về cùng một chuỗi;
    nếu nguồn không có chuỗi ấy thì luật này im và luật rơi dấu quyết. Hai luật không tranh."""
    project = _book(tmp_path, {"000": "Không ai nói gì cả. " * 5})
    text = source_text(project)

    assert fold_to_source_spelling(["THU LÃNH", "THỦ LÃNH"], text, {}) == {}


def test_a_one_chapter_repair_project_still_reads_the_whole_book(tmp_path: Path) -> None:
    """Project vá một chương chỉ trỏ tới MỘT file. Hỏi "tên này có trong sách không" bằng một
    chương thì gần như luôn trả lời "không" - tức luật sẽ gộp bừa đúng lúc ít bằng chứng nhất."""
    project = _book(tmp_path, {"000": "Selene bước vào. " * 10, "001": "Samael đáp. " * 10})
    text_dir = tmp_path / "Text"
    only_one = tmp_path / "lo03v_001"
    only_one.mkdir()
    conn = sqlite3.connect(str(only_one / "project.sqlite3"))
    try:
        conn.execute("CREATE TABLE chapters (id INTEGER PRIMARY KEY, input_path TEXT)")
        conn.execute(
            "INSERT INTO chapters (input_path) VALUES (?)", (str(text_dir / "001.txt"),)
        )
        conn.commit()
    finally:
        conn.close()

    assert len(source_paths(only_one)) == 1, "project chỉ biết một chương"
    text = source_text(only_one)

    assert occurrences("Selene", text) == 10, "vẫn phải thấy tên ở chương nó không chạy"
    assert fold_to_source_spelling(["SELNE", "SELENE"], text, LINES) == {"SELNE": "SELENE"}


def test_no_source_on_disk_means_no_folding_at_all(tmp_path: Path) -> None:
    """Không đọc được nguồn thì không được đoán: trả về rỗng, để luật khác quyết."""
    project = tmp_path / "lo03"
    project.mkdir()
    conn = sqlite3.connect(str(project / "project.sqlite3"))
    try:
        conn.execute("CREATE TABLE chapters (id INTEGER PRIMARY KEY, input_path TEXT)")
        conn.execute("INSERT INTO chapters (input_path) VALUES (?)", ("D:/khong-co-that.txt",))
        conn.commit()
    finally:
        conn.close()

    assert source_text(project) == ""
    assert fold_to_source_spelling(["SELNE", "SELENE"], "", LINES) == {}


def test_folding_ignores_case_and_diacritics_in_the_prose(tmp_path: Path) -> None:
    project = _book(tmp_path, {"000": "SELENE hét lên. selene thì thầm. Selene im lặng."})
    text = source_text(project)

    assert fold("Selene") == "selene"
    assert occurrences("SELENE", text) == 3
