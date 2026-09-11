"""Một con số được đọc trọn vẹn, kể cả từ 1000 trở lên - và thước nhịp đếm đúng cái đọc ra.

Chương 106 của lô 4 mất vì một đoạn chứa "123456": sáu ký tự, một âm tiết theo thước cũ, trong
khi giọng đọc phát ra ít nhất "một hai ba bốn năm sáu". 10/10 lần thử ở 12,35 kt/s, sàn 12,5.
"""
from __future__ import annotations

import pytest

from ebook_reader.asr import NUMBER_FOLD_CEILING, normalize_transcript
from ebook_reader.audio_io import (
    PACE_SYLLABLES_PER_SECOND_FLOOR,
    pace_is_outlier,
    spoken_speakable_chars,
    spoken_syllables,
)
from ebook_reader.text_processing import vietnamese_number_words

NORMAL = (12.5, 24.5)
LOST_LINE_106 = (
    "Tôi bắt đầu thử những mật khẩu dễ đoán nhất như, \"password\", \"123456\", "
    "thậm chí là \"qwerty1234\"."
)


def test_numbers_from_a_thousand_up_are_spelled_by_grammar() -> None:
    assert vietnamese_number_words(1000) == "một nghìn"
    assert vietnamese_number_words(1005) == "một nghìn không trăm lẻ năm"
    assert vietnamese_number_words(2024) == "hai nghìn không trăm hai mươi tư"
    assert vietnamese_number_words(10_015) == "mười nghìn không trăm mười lăm"
    assert vietnamese_number_words(123_456) == "một trăm hai mươi ba nghìn bốn trăm năm mươi sáu"
    assert vietnamese_number_words(1_000_000) == "một triệu"
    assert vietnamese_number_words(2_000_005) == "hai triệu không trăm lẻ năm"
    assert vietnamese_number_words(1_234_567_890) == (
        "một tỷ hai trăm ba mươi tư triệu năm trăm sáu mươi bảy nghìn tám trăm chín mươi"
    )
    with pytest.raises(ValueError):
        vietnamese_number_words(1_000_000_000_000)


def test_below_a_thousand_nothing_changed() -> None:
    for value, spoken in ((15, "mười lăm"), (21, "hai mươi mốt"), (105, "một trăm lẻ năm")):
        assert vietnamese_number_words(value) == spoken


def test_a_digit_run_counts_the_shorter_of_its_two_readings() -> None:
    assert spoken_syllables("123456") == 6, "từng chữ số: sáu; như một số: mười một"
    assert spoken_syllables("1000") == 2, "một nghìn - ngắn hơn bốn chữ số"
    assert spoken_syllables("năm 2024") == 1 + 4
    assert spoken_syllables("22") == 3, "tới 999 đọc như một số, như alpha.57 đo"
    assert spoken_syllables("qwerty1234") == 5


def test_the_lost_line_of_chapter_106_reads_at_a_normal_pace() -> None:
    speakable = spoken_speakable_chars(LOST_LINE_106)
    syllables = spoken_syllables(LOST_LINE_106)
    assert (speakable, syllables) == (88, 26), "70 ký tự / 17 âm tiết là con số cũ, và nó làm mất chương"
    # Đúng thời lượng của bản thu đã mất: 70 ký tự cũ ở 12,35 kt/s.
    speech_seconds = 70 / 12.35
    rate = speakable / speech_seconds
    syllable_rate = syllables / speech_seconds
    assert rate > NORMAL[0] and syllable_rate > PACE_SYLLABLES_PER_SECOND_FLOOR["normal"]
    assert not pace_is_outlier(rate, syllable_rate, "normal", NORMAL)


def test_a_genuinely_slow_take_is_still_caught() -> None:
    speakable = spoken_speakable_chars(LOST_LINE_106)
    syllables = spoken_syllables(LOST_LINE_106)
    speech_seconds = speakable / 8.0
    assert pace_is_outlier(8.0, syllables / speech_seconds, "normal", NORMAL)


def test_the_transcript_fold_still_leaves_a_year_as_written() -> None:
    """ASR không đổi: gộp số trong bản ghi vẫn dừng ở trần cũ."""
    assert NUMBER_FOLD_CEILING == 999
    assert normalize_transcript("năm 2026") == "năm 2026"
