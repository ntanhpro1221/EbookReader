"""Một cách đọc nối bằng gạch ngang là NHIỀU âm tiết - `I-xờ-hờ-ta-ra` là năm, không phải một.

Chương 084 của lô 3 mất vì bộ đếm âm tiết đếm theo khoảng trắng, bốn tiếng sau khi chính bộ đếm
ấy vào cây để cứu chương 075. Cùng một hình dạng lỗi mà nó được viết ra để sửa: đếm chữ viết
thay vì đếm cái giọng đọc phát ra.
"""
from __future__ import annotations

from ebook_reader.audio_io import (
    PACE_SYLLABLES_PER_SECOND_FLOOR,
    pace_is_outlier,
    spoken_speakable_chars,
    spoken_syllables,
)

NORMAL = (12.5, 24.5)
# Đúng văn bản đọc của đoạn đã mất, sau khi thay cách đọc từ sổ phát âm.
LOST_LINE_084 = "Chúng tôi đang đến Thành phố I-xờ-hờ-ta-ra (I-xờ-hờ-ta-ra Xi-ti)."


def test_a_hyphenated_reading_counts_every_syllable() -> None:
    assert spoken_syllables("I-xờ-hờ-ta-ra") == 5
    assert spoken_syllables("Mai-cồ") == 2
    assert spoken_syllables("A-ca-đe-mi Xi-ti") == 6


def test_the_lost_line_of_chapter_084_reads_at_a_normal_pace() -> None:
    speakable = spoken_speakable_chars(LOST_LINE_084)
    syllables = spoken_syllables(LOST_LINE_084)
    assert (speakable, syllables) == (45, 18), "9 âm tiết là con số cũ, và nó làm mất chương"

    speech_seconds = speakable / 12.20
    rate = syllables / speech_seconds
    assert rate > PACE_SYLLABLES_PER_SECOND_FLOOR["normal"]
    assert not pace_is_outlier(12.20, rate, "normal", NORMAL), (
        "đọc 4,88 âm tiết/giây là bình thường; sàn chỉ nên bắt bản thu thật sự chậm"
    )


def test_a_genuinely_slow_take_is_still_caught() -> None:
    """Không phải nới sàn: cùng câu ấy đọc chậm thật thì vẫn bị bắt."""
    syllables = spoken_syllables(LOST_LINE_084)
    speech_seconds = spoken_speakable_chars(LOST_LINE_084) / 8.0
    assert pace_is_outlier(8.0, syllables / speech_seconds, "normal", NORMAL)


def test_plain_vietnamese_counts_exactly_as_before() -> None:
    """Câu không có gạch ngang phải đếm y hệt bản cũ - thay đổi chỉ chạm cách đọc nối gạch."""
    plain = "Và Alice đã ở đó để tận dụng sơ hở ấy."
    assert spoken_syllables(plain) == len(plain.split()) == 11


def test_an_em_dash_between_words_is_a_separator_not_a_syllable() -> None:
    assert spoken_syllables("KENG—!") == 1
    assert spoken_syllables("một — hai") == 2
