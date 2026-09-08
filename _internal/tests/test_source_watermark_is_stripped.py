"""Thuỷ ấn ẩn của trang nguồn không được chạm tới `text_sha256`.

Xem [docs/THE_SOURCE_IS_WATERMARKED.md]. Tóm tắt: 15 file nguồn mang 53 ký tự U+200C/U+200D
xen kẽ - một dãy nhị phân vô hình. Chúng không hại chất lượng (đoạn mang thuỷ ấn ở alpha.56 ra
`verified`, sim 0,966) nhưng `stable_id` là hash của văn bản và hạt giống sinh audio lấy từ
`stable_id`, nên thuỷ ấn đổi là audio đổi và mọi phán quyết của người nghe cho đoạn ấy hết
hiệu lực - với một câu chữ y hệt.
"""
from __future__ import annotations

from ebook_reader.text_processing import normalize_text, segment_chapter_text

WATERMARK = "\u200c\u200d" * 26 + "\u200c"
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
    xuoi = "\u200c\u200d" * 26
    nguoc = "\u200d\u200c" * 26
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
