"""Cuốn sách quyết cách viết nào là thật - bản chính của luật, trong registry.

Nguồn ghi `Selene` 198 lần và `Selne` 0 lần, còn `SELNE` nói 32 câu và `SELENE` chỉ 7. Số câu là
đúng thứ vòng phản hồi làm nhiễm, nên nó không được quyết; cuốn sách thì quyết được.
"""
from __future__ import annotations

from pathlib import Path

from ebook_reader.character_registry import (
    build_registry_and_cast,
    fold_to_source_spelling,
    source_occurrences,
)
from ebook_reader.config import build_settings

from tests.test_character_casting import _identity_db


def test_the_spelling_in_the_book_wins_however_little_it_speaks() -> None:
    book = "selene buoc vao. " * 20
    folded = fold_to_source_spelling(
        ["SELNE", "SELENE", "SELNE VALKRYN"], book, {"SELNE": 32, "SELENE": 7}
    )

    assert folded == {"SELNE": "SELENE", "SELNE VALKRYN": "SELENE"}


def test_two_real_characters_one_letter_apart_are_left_alone() -> None:
    """`SỐ BA` và `SỐ BẢY` lệch một ký tự sau khi bỏ dấu và là hai người. Cả hai có trong nguồn,
    nên luật im lặng. Đây là bài quan trọng nhất trong file: một luật "lệch một ký tự thì gộp"
    sẽ nhập hai nhân vật thật làm một, tức lỗi ngược và tệ hơn."""
    book = "so ba noi. so bay dap. " * 5

    assert source_occurrences("SỐ BA", book) > 0
    assert source_occurrences("SỐ BẢY", book) > 0
    assert fold_to_source_spelling(["SỐ BA", "SỐ BẢY"], book, {"SỐ BA": 2, "SỐ BẢY": 7}) == {}


def test_no_source_means_no_folding() -> None:
    """Không đọc được nguồn thì luật phải TẮT, không được đoán."""
    assert fold_to_source_spelling(["SELNE", "SELENE"], "", {"SELNE": 32}) == {}


def test_a_name_with_no_close_neighbour_stays() -> None:
    assert fold_to_source_spelling(["NARRATOR", "SELENE"], "selene buoc vao.", {}) == {}


def test_the_two_spellings_cast_as_one_character(tmp_path: Path) -> None:
    """Đúng ca lô 3: bản sai nói nhiều hơn bản đúng, và bản đúng vẫn phải thắng vì sách viết nó."""
    # `_identity_db` trỏ `input_path` vào `tmp_path/"one.txt"` và không tạo file ấy; tạo nó ở
    # đây để luật có nguồn mà đọc. Không có file thì luật tự tắt, và bài này sẽ không kiểm gì.
    (tmp_path / "one.txt").write_text("Selene buoc vao. " * 30, encoding="utf-8")
    db = _identity_db(
        tmp_path,
        [("SELNE", "female")] * 6 + [("SELENE", "female")] * 2 + [("KANG", "male")],
    )

    build_registry_and_cast(db, build_settings(), lambda _message: None)

    rows = db.list_segments()
    assert {str(row["speaker"]) for row in rows} == {"SELENE", "KANG"}, (
        "người thắng là cách viết CÓ trong sách, dù ít câu hơn"
    )
    selene = [row for row in rows if str(row["speaker"]) == "SELENE"]
    assert len(selene) == 8
    assert len({int(row["voice_profile_id"]) for row in selene}) == 1
