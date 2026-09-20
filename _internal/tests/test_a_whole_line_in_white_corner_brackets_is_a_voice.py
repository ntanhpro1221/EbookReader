"""Một dòng nguyên vẹn trong 『…』 là một giọng nói; 『…』 giữa câu kể vẫn là chữ của người kể."""
from __future__ import annotations

from ebook_reader.analysis import DIALOGUE_CLOSERS, DIALOGUE_OPENERS
from ebook_reader.text_processing import segment_chapter_text


def _kinds(text: str) -> list[tuple[str, str]]:
    return [(row["kind_hint"], row["text"]) for row in segment_chapter_text(1, text)]


def test_a_whole_line_is_a_voice() -> None:
    rows = _kinds("『Ting.』\n\n『Số người chơi: 8』\n\nCả phòng lặng đi.")
    assert rows == [("dialogue", "『Ting.』"), ("dialogue", "『Số người chơi: 8』"),
                    ("narration", "Cả phòng lặng đi.")]


def test_a_term_inside_a_sentence_stays_narration() -> None:
    assert _kinds("『Dị năng』 của cô ấy rất mạnh.") == [("narration", "『Dị năng』 của cô ấy rất mạnh.")]
    assert _kinds("Cấp Linh Hồn: C 『Hấp thụ 300 Tinh Hoa Linh Hồn để thăng cấp』") == [
        ("narration", "Cấp Linh Hồn: C 『Hấp thụ 300 Tinh Hoa Linh Hồn để thăng cấp』")
    ]


def test_two_voices_in_a_row_are_not_chained_to_one_speaker() -> None:
    # Khoá "thoại nối tiếp" bỏ qua câu mở bằng dấu ngoặc thoại; 『 và 』 phải nằm trong hai tập ấy.
    assert "『" in DIALOGUE_OPENERS and "』" in DIALOGUE_CLOSERS


def test_a_book_without_white_corner_brackets_is_untouched() -> None:
    text = "“Lucien, cậu có quyền đặt tên cho nó.”\n\nDouglas cười nói."
    assert _kinds(text) == [("dialogue", "“Lucien, cậu có quyền đặt tên cho nó.”"),
                            ("narration", "Douglas cười nói.")]
