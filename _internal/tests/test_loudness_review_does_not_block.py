"""Lệch độ to dưới ngưỡng cứng không chặn chương; những cờ nghe thấy được thì vẫn chặn.

Chương đầu tiên của lượt sản xuất hỏng ngày 2026-09-09 vì `loudness delta 0.62 LU` — nằm giữa
ngưỡng review 0,30 và ngưỡng cứng 0,75, tức phép kiểm tự nhận nó chưa chắc. Cả hai đoạn của
chương đều `verified`.

Bản vá cố ý hẹp. Đếm trên mọi project đã lưu, chỉ ba loại cờ review tầng chương từng gặp:
`unexpected silence` (4), `join discontinuity` (2), `loudness delta` (2). Hai loại đầu nghe
thấy được và vẫn chặn.
"""
from __future__ import annotations

from ebook_reader.audio_io import (
    CHAPTER_LOUDNESS_HARD_TOLERANCE_LU,
    CHAPTER_LOUDNESS_REVIEW_TOLERANCE_LU,
    chapter_review_flags_that_block,
)


def test_a_loudness_flag_alone_no_longer_blocks() -> None:
    """Đúng ca đã giết chương 000 của lô 1."""
    assert chapter_review_flags_that_block(["loudness delta 0.62 LU"]) == []


def test_an_audible_silence_still_blocks() -> None:
    """Một giây mất tiếng thì nghe thấy. Không cho qua."""
    assert chapter_review_flags_that_block(["unexpected silence 1.02s"]) == [
        "unexpected silence 1.02s"
    ]


def test_a_join_click_still_blocks() -> None:
    """`join discontinuity` là phép kiểm đã đo được là hiệu chỉnh đúng - đừng vô hiệu hoá nó."""
    assert chapter_review_flags_that_block(["join discontinuity 0.183"]) == [
        "join discontinuity 0.183"
    ]


def test_a_mixed_chapter_still_blocks_on_the_audible_one() -> None:
    """Cho qua độ to không được kéo theo phần còn lại."""
    flags = ["loudness delta 0.40 LU", "unexpected silence 1.02s"]
    assert chapter_review_flags_that_block(flags) == ["unexpected silence 1.02s"]


def test_the_hard_line_is_what_makes_this_safe() -> None:
    """Ranh giới không phải do ai bịa: chính dự án đặt vạch cứng ở 0,75.

    Cờ review chỉ tồn tại trong khoảng giữa hai vạch; vượt vạch cứng là `hard_failures`, và
    đường đó không đi qua hàm này.
    """
    assert CHAPTER_LOUDNESS_REVIEW_TOLERANCE_LU < CHAPTER_LOUDNESS_HARD_TOLERANCE_LU
    assert CHAPTER_LOUDNESS_HARD_TOLERANCE_LU == 0.75
