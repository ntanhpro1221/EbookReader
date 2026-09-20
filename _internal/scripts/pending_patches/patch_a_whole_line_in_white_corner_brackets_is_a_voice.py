"""Vá text_processing.py + analysis.py: một dòng NGUYÊN VẸN trong 『…』 là một giọng nói, không phải lời kể.

Chạy: python patch_a_whole_line_in_white_corner_brackets_is_a_voice.py <root>

## Vì sao (20-09, 08:3x - chủ sách: "『』 xử lý theo cách bạn thấy ok nhất đi")

Bản dịch light novel Nhật dùng hai loại ngoặc. `「…」` là ngoặc thoại thường - đã vá ở ranh giới 9
(`patch_a_corner_bracket_is_a_quote.py`). `『…』` thì mỗi truyện một nghĩa, và khi nó chiếm TRỌN một dòng thì luôn là
một giọng nói, chỉ khác ai nói:

| truyện | 『…』 nguyên dòng là gì | số dòng |
|---|---|---|
| Yamiyo no Hotaru | kẻ nhập xác nói qua miệng người bị nhập ("Miệng của sư phụ, nhưng giọng lại không phải của sư phụ") | 6.185 |
| Năng lực bá đạo của tôi trong game tử thần | bảng thông báo của game (`『Ting.』`, `『Số người chơi: 8』`) | 5.048 |
| Two Childhood Friends | tiếng qua loa, qua điện thoại | 691 |

Hiện bộ tách đoạn khoá tất cả thành lời kể, nên NGƯỜI KỂ đọc hết: ở Yamiyo 189 có 29 câu của kẻ phản diện Yuusei bị
người kể đọc (bắt được khi làm đáp án chuẩn chương ấy, vòng 8).

Vá HẸP nhất có thể - chỉ dòng nguyên vẹn `『…』`:

  - `『Dị năng』 của cô ấy rất mạnh.` (thuật ngữ giữa câu kể) KHÔNG đổi: đổi giọng giữa một câu kể là sai, và đó là
    cách Yamiyo dùng 『』 nhiều thứ hai;
  - không thêm 『 vào `CURLY_QUOTE_SPECS`, nên 『 không mở trạng thái ngoặc nhiều dòng: theo lối Nhật `『』` là ngoặc
    LỒNG trong `「…」`, mà `「」` nay đã thành `“”`, nên coi 『』 là ngoặc ngoài sẽ cắt vụn câu thoại;
  - cuốn 1 và cuốn 2 KHÔNG có dòng nguyên vẹn nào như thế (cuốn 1 có ba file dùng 『』 trong bảng trạng thái, đều nằm
    giữa câu: "Cấp Linh Hồn: C 『Hấp thụ 300 Tinh Hoa Linh Hồn để thăng cấp』"), nên hai cuốn đang chạy không đổi một
    đoạn nào - chứng minh bằng cách chia đoạn lại cả 915 + 478 chương trước/sau (xem lượt thử trong commit).

Phần analysis: `DIALOGUE_OPENERS`/`DIALOGUE_CLOSERS` nhận thêm 『 và 』. Nếu không, khoá "thoại nối tiếp cùng người nói"
sẽ thấy hai dòng 『…』 liền nhau đều không mở bằng dấu ngoặc nó biết và gán cả hai cho MỘT người - sai ngay ở Two
Childhood Friends, nơi hai giọng qua loa nói liên tiếp.
"""
import io
import sys
from pathlib import Path

root = Path(sys.argv[1])


def patch(path: Path, old: str, new: str) -> None:
    source = io.open(path, encoding="utf-8").read()
    assert source.count(old) == 1, f"khong khop mot lan duy nhat trong {path.name}: {old.splitlines()[0]!r}"
    io.open(path, "w", encoding="utf-8").write(source.replace(old, new, 1))
    print(f"da va {path}")


patch(
    root / "ebook_reader" / "text_processing.py",
    '''QUOTE_CLOSING_MARKS = {"”", "’", '"'}''',
    '''QUOTE_CLOSING_MARKS = {"”", "’", '"'}
# Một dòng NGUYÊN VẸN trong 『…』 là một giọng nói: kẻ nhập xác (Yamiyo no Hotaru), bảng thông báo game (Năng lực bá
# đạo), tiếng qua loa/điện thoại (Two Childhood Friends). Cụm 『…』 nằm GIỮA câu kể là thuật ngữ - để yên, vì đổi giọng
# giữa một câu kể là sai. 『 cố ý KHÔNG vào CURLY_QUOTE_SPECS: theo lối Nhật nó là ngoặc lồng trong 「…」 (nay là “”).
WHITE_CORNER_QUOTE_LINE_PATTERN = re.compile(r"『[^』]{1,1600}』")''',
)

patch(
    root / "ebook_reader" / "text_processing.py",
    '''def _line_pieces(line: str) -> list[tuple[str, str]]:
    if re.match(r"^[—–-]\\s*\\S", line):
        return [(line, "dialogue")]''',
    '''def _line_pieces(line: str) -> list[tuple[str, str]]:
    if re.match(r"^[—–-]\\s*\\S", line):
        return [(line, "dialogue")]
    stripped = line.strip()
    if WHITE_CORNER_QUOTE_LINE_PATTERN.fullmatch(stripped) and has_spoken_content(stripped):
        return [(line, "dialogue")]''',
)

patch(
    root / "ebook_reader" / "analysis.py",
    '''DIALOGUE_OPENERS = frozenset({'"', "'", "“", "‘"})
DIALOGUE_CLOSERS = frozenset({'"', "'", "”", "’"})''',
    '''# 『 và 』: một dòng nguyên vẹn trong 『…』 là một giọng nói (xem text_processing). Thiếu chúng ở đây thì khoá "thoại
# nối tiếp cùng người nói" gán hai dòng 『…』 liền nhau cho một người - hai giọng qua loa nói liên tiếp là một ca thật.
DIALOGUE_OPENERS = frozenset({'"', "'", "“", "‘", "『"})
DIALOGUE_CLOSERS = frozenset({'"', "'", "”", "’", "』"})''',
)

test = root / "tests" / "test_a_whole_line_in_white_corner_brackets_is_a_voice.py"
test.write_text('''"""Một dòng nguyên vẹn trong 『…』 là một giọng nói; 『…』 giữa câu kể vẫn là chữ của người kể."""
from __future__ import annotations

from ebook_reader.analysis import DIALOGUE_CLOSERS, DIALOGUE_OPENERS
from ebook_reader.text_processing import segment_chapter_text


def _kinds(text: str) -> list[tuple[str, str]]:
    return [(row["kind_hint"], row["text"]) for row in segment_chapter_text(1, text)]


def test_a_whole_line_is_a_voice() -> None:
    rows = _kinds("『Ting.』\\n\\n『Số người chơi: 8』\\n\\nCả phòng lặng đi.")
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
    text = "“Lucien, cậu có quyền đặt tên cho nó.”\\n\\nDouglas cười nói."
    assert _kinds(text) == [("dialogue", "“Lucien, cậu có quyền đặt tên cho nó.”"),
                            ("narration", "Douglas cười nói.")]
''', encoding="utf-8")
print(f"da viet {test}")
