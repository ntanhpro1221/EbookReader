"""Nguồn của truyện mạng có lẫn thứ không phải truyện, và cuốn sách nói phải biết loại nó.

Ca thật, tìm ra 00:10 ngày 2026-09-16: `000.txt` của cuốn 1 là một bài **"Chuyên mục bổ mắt"**
dài 183 byte nói về ảnh fan art, và nó đã thành `000.mp3` dài **6 giây** — tức thứ **đầu tiên**
người nghe mở cuốn sách ra là lời nhắn về fan art. Không cổng nào bắt được: file `.txt` ấy hợp
lệ, chương ấy `completed`, MP3 ấy đúng thời lượng so với nguồn của nó.

Cuốn 2 có bốn file cuối (911–914) là **hồ sơ nhân vật** ("01 - John", "02 - Maskelyne"…), chưa
tới lượt sản xuất; chúng nằm trong file danh sách dưới dạng chú thích, để chủ sách quyết.

Và cùng lúc ấy lộ ra một lỗ im lặng: `SOURCE` của `assemble_book.py` ghim cứng
`D:/Novels/Tools/Text` — thư mục nguồn CŨ của cuốn 1, bị xoá ngày 13-09 — nên `_expected()`
đọc một thư mục không tồn tại, trả về rỗng, và phép kiểm "nguồn có N chương, **thiếu M**" chưa
bao giờ chạy cho cuốn nào. Sau khi sửa, cuốn 2 lập tức chỉ ra `082`, chương chưa bao giờ có
bản thu.
"""
from __future__ import annotations

import importlib
from pathlib import Path

import pytest

import scripts.assemble_book as assemble_book


@pytest.fixture()
def source(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    folder = tmp_path / "Text"
    folder.mkdir()
    for stem in ("000", "001", "002", "003"):
        (folder / f"{stem}.txt").write_text("Chương gì đó", encoding="utf-8")
    monkeypatch.setattr(assemble_book, "SOURCE", folder)
    return folder


def test_no_list_means_nothing_is_excluded(source: Path) -> None:
    assert assemble_book.not_a_chapter() == set()
    assert assemble_book._expected() == ["000", "001", "002", "003"]


def test_the_listed_file_leaves_the_book(source: Path) -> None:
    (source / assemble_book.NOT_A_CHAPTER_FILE).write_text(
        "# bài về fan art, 6 giây\n000\n", encoding="utf-8"
    )

    assert assemble_book.not_a_chapter() == {"000"}
    assert assemble_book._expected() == ["001", "002", "003"]


def test_the_list_file_does_not_count_itself_as_a_chapter(source: Path) -> None:
    """Bản đầu đếm nó thành chương: cuốn 1 báo "nguồn có 478 chương" thay vì 477."""
    (source / assemble_book.NOT_A_CHAPTER_FILE).write_text("000\n", encoding="utf-8")

    expected = assemble_book._expected()

    assert Path(assemble_book.NOT_A_CHAPTER_FILE).stem not in expected
    assert len(expected) == 3


def test_comments_and_blank_lines_are_not_chapter_numbers(source: Path) -> None:
    (source / assemble_book.NOT_A_CHAPTER_FILE).write_text(
        "# 911 hồ sơ nhân vật - để chủ sách quyết\n\n  002  # có chú thích đuôi\n",
        encoding="utf-8",
    )

    assert assemble_book.not_a_chapter() == {"002"}


def test_the_source_folder_comes_from_book_paths_not_from_a_typed_path() -> None:
    """Đường dẫn chép tay ở đây đã làm tắt phép kiểm "thiếu bao nhiêu chương" cho CẢ HAI cuốn."""
    module = importlib.reload(assemble_book)
    from scripts.book_paths import SOURCE_DIR

    assert module.SOURCE == SOURCE_DIR
    text = Path(module.__file__).read_text(encoding="utf-8")
    assert "Novels\\Tools\\Text" not in text and "Novels/Tools/Text" not in text.replace(
        "`D:/Novels/Tools/Text`", ""
    )
