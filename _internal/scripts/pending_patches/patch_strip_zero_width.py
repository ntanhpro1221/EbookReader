"""Va text_processing.py: xoa moi ky tu zero-width, khong chi mot cai.

CHUA AP. Xem docs/THE_SOURCE_IS_WATERMARKED.md - ban va nay doi `text_sha256` cua dung 15
doan tren ca cuon, nen phai ap GIUA HAI LO chu khong phai giua chung mot lo.
"""
import io
import sys
from pathlib import Path

root = Path(sys.argv[1])
p = root / "ebook_reader" / "text_processing.py"
s = io.open(p, encoding="utf-8").read()

OLD = '''    text = text.replace("\\u00a0", " ").replace("\\u200b", "")'''

NEW = '''    text = text.replace("\\u00a0", " ")
    # Cả họ zero-width, không chỉ U+200B. Dòng cũ đã có đúng ý định này và chỉ bắt một trong
    # bốn ký tự - đủ để đọc như đã xong.
    #
    # Nguồn có **thuỷ ấn ẩn**: 53 ký tự U+200C/U+200D xen kẽ nhau thành một dãy nhị phân,
    # chèn vào một chỗ trong 15 file (015, 026, 038, 086, 092, 097, 114, 127, 140, 164, 176,
    # 188, 229, 256, 278). Mắt không thấy, và không phép kiểm nào của dự án nhìn chúng.
    #
    # Chúng KHÔNG hại chất lượng - đo ở alpha.56: đoạn mang thuỷ ấn ra `verified`, sim 0,966,
    # vì VieNeu đọc lướt qua và `speakable_chars` đếm `isalnum()`. Cái chúng hại là **tính
    # tái lập**: `stable_id` là hash của văn bản, hạt giống sinh audio lấy từ `stable_id`, nên
    # trang nguồn cấp lại một dãy nhị phân khác - đúng việc mà thuỷ ấn sinh ra để làm - sẽ đổi
    # audio của một câu chữ y hệt, và mọi phán quyết của người nghe cho đoạn ấy lặng lẽ hết
    # hiệu lực.
    #
    # ZWJ có nghĩa thật trong chuỗi emoji và trong Devanagari/Ả Rập. Trong văn xuôi tiếng Việt
    # thì không, và nguồn này không có chữ nào ngoài Latin - đã quét cả 478 file.
    for zero_width in ("\\u200b", "\\u200c", "\\u200d", "\\u2060", "\\ufeff"):
        text = text.replace(zero_width, "")'''

assert OLD in s, "khong khop normalize_text"
s = s.replace(OLD, NEW, 1)
io.open(p, "w", encoding="utf-8").write(s)
print(f"da va {p}")

# ---------------------------------------------------------------------- test
p = root / "tests" / "test_source_watermark_is_stripped.py"
p.write_text(
    '''"""Thuỷ ấn ẩn của trang nguồn không được chạm tới `text_sha256`.

Xem [docs/THE_SOURCE_IS_WATERMARKED.md]. Tóm tắt: 15 file nguồn mang 53 ký tự U+200C/U+200D
xen kẽ - một dãy nhị phân vô hình. Chúng không hại chất lượng (đoạn mang thuỷ ấn ở alpha.56 ra
`verified`, sim 0,966) nhưng `stable_id` là hash của văn bản và hạt giống sinh audio lấy từ
`stable_id`, nên thuỷ ấn đổi là audio đổi và mọi phán quyết của người nghe cho đoạn ấy hết
hiệu lực - với một câu chữ y hệt.
"""
from __future__ import annotations

from ebook_reader.text_processing import normalize_text, segment_chapter_text

WATERMARK = "\\u200c\\u200d" * 26 + "\\u200c"
CAU = "Vì tôi đã bất tỉnh gần hai ngày, Juliana đã"


def test_two_texts_that_look_identical_hash_identically() -> None:
    """Cái đắt nhất: hai file trông y hệt nhau trên màn hình phải cho cùng một stable_id."""
    sach = f"{CAU} đưa ra một quyết định khôn ngoan là khởi hành ngay sáng nay."
    co_an = f"{CAU}{WATERMARK} đưa ra một quyết định khôn ngoan là khởi hành ngay sáng nay."

    assert normalize_text(co_an) == normalize_text(sach)

    a = segment_chapter_text(1, sach, 320)
    b = segment_chapter_text(1, co_an, 320)
    assert [row["stable_id"] for row in a] == [row["stable_id"] for row in b]


def test_a_watermark_that_changes_does_not_change_the_audio_seed() -> None:
    """Thuỷ ấn sinh ra để đổi. Đó là lý do lọc, chứ không phải vì nó xấu."""
    # Ghép bằng `+` chứ không f-string: dấu gạch chéo ngược trong biểu thức f-string là
    # SyntaxError trên Python 3.11, và runtime của dự án là 3.11.9.
    xuoi = "\\u200c\\u200d" * 26
    nguoc = "\\u200d\\u200c" * 26
    duoi = " đưa ra một quyết định khôn ngoan là khởi hành ngay sáng nay."
    mot = CAU + xuoi + duoi
    hai = CAU + nguoc + duoi

    assert mot != hai
    assert [r["stable_id"] for r in segment_chapter_text(1, mot, 320)] == [
        r["stable_id"] for r in segment_chapter_text(1, hai, 320)
    ]


def test_the_visible_text_is_untouched() -> None:
    """Lọc ký tự vô hình, không đụng gì khác - kể cả dấu bullet, thứ TTS đã đọc lướt đúng."""
    assert normalize_text("• Hệ thống Sức mạnh") == "• Hệ thống Sức mạnh"
    assert normalize_text("Nhiệt độ 40° và mũi tên ↓") == "Nhiệt độ 40° và mũi tên ↓"
    assert normalize_text("C 『Hấp thụ 300 Tinh Hoa』") == "C 『Hấp thụ 300 Tinh Hoa』"
''',
    encoding="utf-8",
)
print(f"da tao {p}")
