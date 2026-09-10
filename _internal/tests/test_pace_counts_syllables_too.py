"""Một bản thu chỉ chậm khi chậm theo cả chữ lẫn âm tiết — chương 075 của lô 3 là ca gốc.

"Và Alice đã ở đó để tận dụng sơ hở ấy." mất 10/10 lần ở 10,64–11,80 chars/s (sàn 12,5) vì câu
có 2,25 chữ mỗi từ so với trung vị kho 3,33; theo âm tiết nó đọc 4,48/giây, gần trung vị kho
4,67. Cùng họ với lỗi chữ số (`spoken_speakable_chars`): thước đếm sai cái nó nhận là đếm.
"""
from __future__ import annotations

from ebook_reader.audio_io import (
    PACE_SYLLABLES_PER_SECOND_FLOOR,
    pace_is_outlier,
    spoken_speakable_chars,
    spoken_syllables,
)

NORMAL = (12.5, 24.5)
SENTENCE_075 = "Và Alice đã ở đó để tận dụng sơ hở ấy."


def test_the_lost_sentence_of_chapter_075_is_not_slow() -> None:
    speakable = spoken_speakable_chars(SENTENCE_075)
    syllables = spoken_syllables(SENTENCE_075)
    assert (speakable, syllables) == (27, 11)
    for chars_per_second in (10.64, 11.00, 11.38, 11.80):
        speech_seconds = speakable / chars_per_second
        syllable_rate = syllables / speech_seconds
        assert syllable_rate > PACE_SYLLABLES_PER_SECOND_FLOOR["normal"]
        assert not pace_is_outlier(chars_per_second, syllable_rate, "normal", NORMAL), (
            chars_per_second
        )


def test_a_take_slow_by_both_counts_is_still_slow() -> None:
    """Không phải nới sàn: một bản thu 11 chars/s VÀ 3,0 âm tiết/giây vẫn là chậm."""
    assert pace_is_outlier(11.0, 3.0, "normal", NORMAL)


def test_the_upper_bound_is_untouched() -> None:
    assert pace_is_outlier(26.0, 7.0, "normal", NORMAL)
    assert not pace_is_outlier(20.0, 6.0, "normal", NORMAL)


def test_bands_scale_like_the_character_bands() -> None:
    """slow và fast tỉ lệ theo dải chữ như cũ: 7/12,5 và 14/12,5."""
    normal = PACE_SYLLABLES_PER_SECOND_FLOOR["normal"]
    assert abs(PACE_SYLLABLES_PER_SECOND_FLOOR["slow"] - normal * 7.0 / 12.5) < 0.05
    assert abs(PACE_SYLLABLES_PER_SECOND_FLOOR["fast"] - normal * 14.0 / 12.5) < 0.05
    # 4,0 âm tiết/giây: đủ cho 'normal' (sàn 3,75), chưa đủ cho 'fast' (sàn 4,2).
    assert not pace_is_outlier(12.0, 4.0, "normal", NORMAL)
    assert pace_is_outlier(13.0, 4.0, "fast", (14.0, 30.0))


def test_syllables_are_counted_short_on_names_and_digits_on_purpose() -> None:
    """Đếm thiếu là chiều an toàn: nhịp âm tiết đo thấp hơn thật thì chỉ giữ cờ, không tha."""
    assert spoken_syllables("Alice") == 1
    assert spoken_syllables("Chương 22") == 2
    assert spoken_syllables("— …") == 0
