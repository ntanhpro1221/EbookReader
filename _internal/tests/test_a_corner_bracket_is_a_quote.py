"""Ngoặc góc 「…」 của bản dịch light novel Nhật là ngoặc thoại (patch_a_corner_bracket_is_a_quote)."""
from __future__ import annotations

from ebook_reader.analysis import DIALOGUE_OPENERS
from ebook_reader.text_processing import normalize_text, segment_chapter_text


def _kinds(text: str) -> list[tuple[str, str]]:
    return [(row["kind_hint"], row["text"]) for row in segment_chapter_text(1, text)]


def test_a_whole_line_in_corner_brackets_is_dialogue() -> None:
    rows = _kinds("「Thôi nhé. Như đã nói, tôi đi đây.」\n\n「Ừ. Hiểu rồi.」\n\nHai người lặng lẽ trao đổi.")
    assert rows == [
        ("dialogue", "“Thôi nhé. Như đã nói, tôi đi đây.”"),
        ("dialogue", "“Ừ. Hiểu rồi.”"),
        ("narration", "Hai người lặng lẽ trao đổi."),
    ]


def test_two_corner_bracket_lines_each_open_their_own_quote() -> None:
    # Khoá "thoại nối tiếp cùng người nói" của analysis bỏ qua câu mở bằng ngoặc thoại. 「 không nằm trong
    # DIALOGUE_OPENERS, nên câu phải tới đó dưới dạng “.
    rows = segment_chapter_text(1, "「Đi đâu vậy?」\n\n「Ra chợ.」")
    assert all(str(row["text"])[0] in DIALOGUE_OPENERS for row in rows)


def test_a_term_in_corner_brackets_inside_narration_stays_narration() -> None:
    rows = _kinds("Chiếc Omamori cô ấy「ban cho」anh đã được thấm nhuần thuật thức giám sát tâm trí.")
    assert [kind for kind, _ in rows] == ["narration"]


def test_white_corner_brackets_are_left_alone() -> None:
    # 『』 là thuật ngữ, bảng hệ thống, ngoặc lồng - không phải ngoặc thoại.
    assert normalize_text("Cấp Linh Hồn: C 『Hấp thụ 300 Tinh Hoa Linh Hồn để thăng cấp』") == (
        "Cấp Linh Hồn: C 『Hấp thụ 300 Tinh Hoa Linh Hồn để thăng cấp』"
    )
    assert _kinds("『Dị năng』 của cô ấy rất mạnh.") == [("narration", "『Dị năng』 của cô ấy rất mạnh.")]


def test_a_text_without_corner_brackets_is_unchanged() -> None:
    text = "“Lucien, cậu có quyền đặt tên cho nó.”\n\nDouglas cười nói."
    assert normalize_text(text) == text
