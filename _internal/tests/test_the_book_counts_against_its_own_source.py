"""Phép kiểm "nguồn có N chương, thiếu M" phải đọc nguồn của CUỐN ĐANG GHÉP.

`assemble_book.py` ghim cứng `SOURCE = D:/Novels/Tools/Text` — thư mục nguồn **cũ** của cuốn 1,
bị xoá ngày 13-09 và khôi phục sang `Ebook Reader/Text`. Hệ quả im lặng: `_expected()` đọc một
thư mục không tồn tại, trả về rỗng, nên phép kiểm thiếu-chương **chưa bao giờ chạy cho cuốn
nào** — kể cả cuốn 2, vốn chưa từng dùng đường dẫn ấy.

Sửa xong (00:15 ngày 2026-09-16) nó nói ngay:

    cuốn 1:  nguồn có 478 chương; thiếu 217
    cuốn 2:  nguồn có 915 chương; thiếu 776   -> thiếu: 082, 140, 141, ...

`082` là chương chưa bao giờ có bản thu, và lưới này lẽ ra phải nói câu ấy từ 14-09.

Đây là chỗ **thứ ba** cùng họ trong một ngày (`before_a_batch._versions`, bộ canh của
`apply_all`, và đây), nên bài này khoá cả hình dạng: đường dẫn lấy từ `book_paths`, không chép
tay. Mỗi lần `book_paths` dẹp một đường dẫn, những chỗ còn lại phải bị tìm ra ngay hôm ấy —
chúng không tự hiện, chúng chỉ im.

Và nó **không** hỏi file nào "đáng đọc": mọi `.txt` trong thư mục nguồn là một chương. Chủ sách
ra lệnh thế ngày 16-09 sau khi tôi tự dựng một cơ chế loại trừ — *"ném vào là nó đọc thôi"*.
"""
from __future__ import annotations

from pathlib import Path

import pytest

import scripts.assemble_book as assemble_book
from scripts.book_paths import SOURCE_DIR


def test_the_source_folder_comes_from_book_paths() -> None:
    assert assemble_book.SOURCE == SOURCE_DIR


def test_no_hand_copied_source_path_is_left_in_the_file() -> None:
    text = Path(assemble_book.__file__).read_text(encoding="utf-8")
    for line in text.splitlines():
        if line.lstrip().startswith("#"):
            continue  # chú thích được phép nhắc đường dẫn cũ để giải thích lịch sử
        assert "Tools" not in line or "SOURCE" not in line, line


def test_every_txt_in_the_source_is_a_chapter(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Không lọc gì: thứ gì ném vào thư mục nguồn cũng là một chương để đọc."""
    folder = tmp_path / "Text"
    folder.mkdir()
    for stem in ("000", "001", "002"):
        (folder / f"{stem}.txt").write_text("Chương gì đó", encoding="utf-8")
    (folder / "ghi_chu.txt").write_text("một file người ta ném vào", encoding="utf-8")
    monkeypatch.setattr(assemble_book, "SOURCE", folder)

    assert assemble_book._expected() == ["000", "001", "002", "ghi_chu"]


def test_a_missing_source_folder_is_not_a_crash(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Thư mục nguồn của cuốn khác có thể không có ở máy này; im lặng đúng ở đây là đúng."""
    monkeypatch.setattr(assemble_book, "SOURCE", tmp_path / "khong-ton-tai")

    assert assemble_book._expected() == []
