"""Vá text_processing.py: ngoặc góc 「…」 là dấu ngoặc thoại, như “…”.

Chạy: python patch_a_corner_bracket_is_a_quote.py <root>

## Vì sao (20-09, 01:0x)

Bản dịch light novel Nhật trên Hako hay giữ ngoặc góc của bản gốc: 「Ừ. Hiểu rồi.」 thay cho “Ừ. Hiểu rồi.”. Bộ tách đoạn
chỉ biết “…”, "…" và ‘…’, nên mọi câu thoại trong ngoặc góc bị khoá là LỜI KỂ - người kể đọc hết, model phân tích không
được phép gán người nói (loại bị khoá). Đo trên kho truyện (`Corpus/`, 20-09):

- Yamiyo no Hotaru: 30.941 dòng thoại nguyên dòng 「…」 trên 310 chương - gần như cả truyện là một giọng. Chương 155
  (Chap 126): 54/107 đoạn là thoại, cả 54 bị khoá narration.
- Nise Seiken Monogatari: 26 dòng thoại 「…」 (còn lại là trích truyện/vở kịch).
- Hai cuốn đang sản xuất: KHÔNG có 「 nào (cuốn 2: 0/915 file; cuốn 1: 0/478 - ba file có 『』 trong bảng trạng thái).

Sửa ở `normalize_text`, một chỗ duy nhất trước khi chia đoạn: 「 -> “, 」 -> ”. Nhờ vậy MỌI luật phía sau thấy đúng
dấu ngoặc chúng đã biết - heuristic thoại/không-thoại (`_quoted_span_is_dialogue`: cả dòng trong ngoặc là thoại, một
thuật ngữ trong ngoặc giữa câu kể vẫn là lời kể), trạng thái ngoặc nhiều dòng và lượt cứu ngoặc chưa đóng, khoá "thoại
nối tiếp cùng người nói" của analysis (`DIALOGUE_OPENERS`: câu mở bằng 「 KHÔNG nằm trong đó, nên hai câu thoại 「」 ở hai
đoạn liền nhau sẽ bị khoá thành cùng một người nếu chỉ vá bộ tách đoạn), các regex luật host có lớp ký tự ngoặc, và chỗ
ngắt nghỉ của TTS. Vá từng chỗ thay vì chuẩn hoá thì sót một chỗ là một lỗi lặng.

Không đụng 『…』: kho truyện dùng nó cho thuật ngữ (『Dị năng』), bảng hệ thống (『Ting.』), tiếng qua loa/điện thoại, và
cho ngoặc LỒNG trong 「…」 theo lối Nhật - đổi 『』 thành “” sẽ lồng “ trong “ và cắt vụn câu thoại.

Chữ lưu trong DB đổi 「 thành “ - cùng nghĩa trong văn bản tiếng Việt. Truyện không có 「 thì `normalize_text` trả đúng
chuỗi cũ (thay thế rỗng), nên `stable_id`, hạt giống audio, mọi phán quyết đã có của hai cuốn đang sản xuất không đổi -
chứng minh bằng cách chia đoạn lại toàn bộ 915 + 478 chương trước/sau bản vá (xem lượt thử trong commit).
"""
import io
import sys
from pathlib import Path

root = Path(sys.argv[1])
p = root / "ebook_reader" / "text_processing.py"
s = io.open(p, encoding="utf-8").read()


def replace_once(old: str, new: str) -> None:
    global s
    assert s.count(old) == 1, f"khong khop mot lan duy nhat: {old.splitlines()[0]!r}"
    s = s.replace(old, new, 1)


replace_once('''    for zero_width in ("\\u200b", "\\u200c", "\\u200d", "\\u2060", "\\ufeff"):
        text = text.replace(zero_width, "")
''', '''    for zero_width in ("\\u200b", "\\u200c", "\\u200d", "\\u2060", "\\ufeff"):
        text = text.replace(zero_width, "")
    # Ngoặc góc của bản dịch light novel Nhật (「Ừ. Hiểu rồi.」) là ngoặc thoại: đổi thành “…” ở đây, một chỗ, để mọi luật
    # phía sau - tách thoại, ngoặc nhiều dòng, khoá thoại nối tiếp, luật host, ngắt nghỉ TTS - thấy đúng dấu chúng biết.
    # Yamiyo no Hotaru có 30.941 dòng thoại như thế từng bị khoá là lời kể. 『…』 thì để yên: truyện dùng nó cho thuật
    # ngữ, bảng hệ thống và ngoặc lồng trong 「…」. Truyện không có 「 thì chuỗi không đổi - stable_id không đổi.
    text = text.replace("\\u300c", "\\u201c").replace("\\u300d", "\\u201d")
''')
io.open(p, "w", encoding="utf-8").write(s)
print(f"da va {p}")

test = root / "tests" / "test_a_corner_bracket_is_a_quote.py"
test.write_text('''"""Ngoặc góc 「…」 của bản dịch light novel Nhật là ngoặc thoại (patch_a_corner_bracket_is_a_quote)."""
from __future__ import annotations

from ebook_reader.analysis import DIALOGUE_OPENERS
from ebook_reader.text_processing import normalize_text, segment_chapter_text


def _kinds(text: str) -> list[tuple[str, str]]:
    return [(row["kind_hint"], row["text"]) for row in segment_chapter_text(1, text)]


def test_a_whole_line_in_corner_brackets_is_dialogue() -> None:
    rows = _kinds("「Thôi nhé. Như đã nói, tôi đi đây.」\\n\\n「Ừ. Hiểu rồi.」\\n\\nHai người lặng lẽ trao đổi.")
    assert rows == [
        ("dialogue", "“Thôi nhé. Như đã nói, tôi đi đây.”"),
        ("dialogue", "“Ừ. Hiểu rồi.”"),
        ("narration", "Hai người lặng lẽ trao đổi."),
    ]


def test_two_corner_bracket_lines_each_open_their_own_quote() -> None:
    # Khoá "thoại nối tiếp cùng người nói" của analysis bỏ qua câu mở bằng ngoặc thoại. 「 không nằm trong
    # DIALOGUE_OPENERS, nên câu phải tới đó dưới dạng “.
    rows = segment_chapter_text(1, "「Đi đâu vậy?」\\n\\n「Ra chợ.」")
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
    text = "“Lucien, cậu có quyền đặt tên cho nó.”\\n\\nDouglas cười nói."
    assert normalize_text(text) == text
''', encoding="utf-8")
print(f"da viet {test}")
