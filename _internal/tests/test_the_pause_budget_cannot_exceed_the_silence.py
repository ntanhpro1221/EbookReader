"""Cận trên của phép kiểm nhịp phải xét khoảng lặng CÓ THẬT, không xét ngân sách đoán.

Ba đoạn của cuốn 2 mất hẳn bản thu vì bị kết tội "đọc quá nhanh" khi không hề nhanh: chương 082
(`“Tôi không biết ‘xoay’ đâu, Felicia.”`, 22 lần thử, 29–32,50 kt/s), chương 131 (`“Chà… Cậu
‘nếu’ nhiều thật đấy, Lucien.”`, 11 lần thử, 26,37) và chương 090.

Nhịp không phải ký tự chia thời lượng: `validate_audio_array` trừ trước một **ngân sách nghỉ**
0,276 giây mỗi nhóm dấu câu. Ngân sách ấy cứu những câu đọc đúng dấu câu khỏi bị gọi là chậm,
nhưng nó là phỏng đoán chỉnh chuẩn trên câu dài. Phép thử GPU 08:30 ngày 2026-09-15: bốn dạng
văn bản của cùng một câu (có/không nháy, có/không ngoặc đơn lồng) cho **cùng một thời lượng tới
hai chữ số thập phân** — giọng đọc không nghỉ ở dấu ngoặc. Với câu thoại 2,16 giây, ngân sách
chạm trần `MAX_PAUSE_FRACTION`, đòi 1,296 giây ở chỗ chỉ có 0,46 giây im lặng, và nhịp bị thổi
từ 15,29 lên 30,09 kt/s. Cả 12 bản thu thật của câu ấy đều đi từ NGOÀI BĂNG về đạt khi trừ đúng
số giây im lặng.

Nên cận TRÊN có thêm một thước: nhịp tính với khoảng lặng đo được. Nó luôn nhỏ hơn hoặc bằng
nhịp cũ, nên thay đổi là **một chiều** — chỉ bớt lời kết tội, không thêm. Cận DƯỚI giữ nguyên
thước cũ: đo trên 3000 đoạn đã chốt, chặn cả hai cận biến 2 đoạn đang đạt thành ngoài băng ở
cận dưới, và `“Chào, Felicia. Và… cậu ở đây sao, Lucien!”` (13,75 → 10,27) là một trong hai.
"""
from __future__ import annotations

import inspect

import numpy as np
import pytest

from ebook_reader import audio_io
from ebook_reader.audio_io import (
    MAX_PAUSE_FRACTION,
    MIN_SPEECH_SECONDS,
    PAUSE_GROUP_SECONDS,
    measured_silence_seconds,
    pace_is_outlier,
    pause_group_count,
    spoken_speakable_chars,
    spoken_syllables,
)

NORMAL = (12.5, 24.5)
SAMPLE_RATE = 24_000
# Đúng câu đã mất bản thu ở chương 082 sau 22 lần thử.
LOST_LINE = "\u201cTôi không biết \u2018xoay\u2019 đâu, Felicia.\u201d"
# Một trong hai đoạn mà chặn ở cận dưới sẽ giết; nó đang đạt và phải tiếp tục đạt.
SLOW_LINE = "\u201cChào, Felicia. Và\u2026 cậu ở đây sao, Lucien!\u201d"
ONE_FRAME = 0.011


def _take(speech_seconds: float, silence_seconds: float, *, amplitude: float = 0.3) -> np.ndarray:
    """Sóng âm hình "nói - im - nói", đúng số giây yêu cầu ở mỗi phần."""
    half = max(1, int(round(SAMPLE_RATE * speech_seconds / 2)))
    quiet = int(round(SAMPLE_RATE * silence_seconds))
    tone = np.sin(np.linspace(0.0, 200.0 * np.pi, half, dtype=np.float32)) * amplitude
    return np.concatenate([tone, np.zeros(quiet, dtype=np.float32), tone])


def _budget(text: str, duration: float) -> float:
    return min(PAUSE_GROUP_SECONDS * pause_group_count(text), duration * MAX_PAUSE_FRACTION)


def _rate(text: str, duration: float, pause: float) -> float:
    return spoken_speakable_chars(text) / max(duration - pause, MIN_SPEECH_SECONDS)


def test_the_measured_silence_finds_the_gap() -> None:
    assert measured_silence_seconds(_take(1.70, 0.46), SAMPLE_RATE) == pytest.approx(
        0.46, abs=ONE_FRAME
    )


def test_a_gain_does_not_change_the_measured_silence() -> None:
    """`atomic_write_wav` đo cùng một bản thu hai lần, trước và sau khi cân âm lượng.

    Ngưỡng dBFS tuyệt đối sẽ cho hai con số khác nhau ở hai lần ấy, và cùng một bản thu có thể
    đạt ở lần này rồi trượt ở lần kia. Ngưỡng so với đỉnh thì miễn nhiễm với phép nhân.
    """
    take = _take(1.70, 0.46)

    assert (
        measured_silence_seconds(take, SAMPLE_RATE)
        == measured_silence_seconds(take * 0.12, SAMPLE_RATE)
        == measured_silence_seconds(take * 3.0, SAMPLE_RATE)
    )


def test_a_gap_too_short_to_be_a_pause_is_not_counted() -> None:
    assert measured_silence_seconds(_take(1.70, 0.02), SAMPLE_RATE) == 0.0


def test_speech_without_a_gap_measures_no_silence() -> None:
    assert measured_silence_seconds(_take(2.16, 0.0), SAMPLE_RATE) == 0.0


def test_an_empty_or_silent_take_does_not_raise() -> None:
    assert measured_silence_seconds(np.zeros(0, dtype=np.float32), SAMPLE_RATE) == 0.0
    assert measured_silence_seconds(np.zeros(SAMPLE_RATE, dtype=np.float32), SAMPLE_RATE) == 1.0
    assert measured_silence_seconds(_take(1.0, 0.5), 0) == 0.0


def test_the_lost_line_is_no_longer_called_too_fast() -> None:
    duration = 2.16  # một trong 12 bản thu thật của phép thử GPU sáng 2026-09-15
    silence = measured_silence_seconds(_take(duration - 0.46, 0.46), SAMPLE_RATE)
    budget = _budget(LOST_LINE, duration)
    charged = _rate(LOST_LINE, duration, budget)
    heard = _rate(LOST_LINE, duration, min(budget, silence))
    syllables = spoken_syllables(LOST_LINE) / max(duration - budget, MIN_SPEECH_SECONDS)

    assert budget == pytest.approx(1.296), "ngân sách chạm trần MAX_PAUSE_FRACTION"
    assert charged == pytest.approx(30.09, rel=0.001), "con số đã kết tội bản thu"
    assert heard == pytest.approx(15.29, rel=0.001), "nhịp thật, giữa dải 12,5-24,5"
    assert pace_is_outlier(charged, syllables, "normal", NORMAL), "thước cũ vẫn kết tội"
    assert not pace_is_outlier(charged, syllables, "normal", NORMAL, fast_rate=heard)


def test_a_take_that_really_is_rushed_is_still_rejected() -> None:
    """Cửa vẫn phải đóng: cùng văn bản ấy đọc trong 1 giây thì nhanh theo cả hai thước."""
    duration = 1.00
    silence = measured_silence_seconds(_take(0.95, 0.05), SAMPLE_RATE)
    budget = _budget(LOST_LINE, duration)
    charged = _rate(LOST_LINE, duration, budget)
    heard = _rate(LOST_LINE, duration, min(budget, silence))
    syllables = spoken_syllables(LOST_LINE) / max(duration - budget, MIN_SPEECH_SECONDS)

    assert heard > float(NORMAL[1]), heard
    assert pace_is_outlier(charged, syllables, "normal", NORMAL, fast_rate=heard)


def test_with_no_silence_at_all_the_rate_is_characters_over_duration() -> None:
    """Không có khoảng lặng nào thì không trừ gì, và 26 ký tự trong 2,16 giây không phải nhanh."""
    duration = 2.16
    silence = measured_silence_seconds(_take(duration, 0.0), SAMPLE_RATE)
    budget = _budget(LOST_LINE, duration)
    heard = _rate(LOST_LINE, duration, min(budget, silence))

    assert silence == 0.0
    assert heard == pytest.approx(spoken_speakable_chars(LOST_LINE) / duration)
    assert heard == pytest.approx(12.04, rel=0.001)


def test_the_second_ruler_can_only_remove_a_verdict() -> None:
    """Thước mới không được thêm một lời kết tội nào - `fast_rate` luôn <= `rate`."""
    assert not pace_is_outlier(30.0, 7.0, "normal", NORMAL, fast_rate=20.0)
    assert pace_is_outlier(30.0, 7.0, "normal", NORMAL, fast_rate=26.0)
    assert pace_is_outlier(30.0, 7.0, "normal", NORMAL)


def test_the_slow_side_keeps_the_old_ruler() -> None:
    """Đoạn `“Chào, Felicia...”`: 13,75 kt/s với ngân sách, 10,27 với khoảng lặng thật.

    Nó đang đạt. Nếu khoảng lặng đo được cũng chặn cận dưới thì nó thành "đọc quá chậm" - 1
    trong 2 đoạn như thế trên 3000 đoạn đã chốt, và đúng lý do cận dưới giữ thước cũ.
    """
    duration = spoken_speakable_chars(SLOW_LINE) / 13.75 + 1.656
    budget = _budget(SLOW_LINE, duration)
    charged = _rate(SLOW_LINE, duration, budget)
    heard = _rate(SLOW_LINE, duration, min(budget, 0.94))
    syllables = spoken_syllables(SLOW_LINE) / max(duration - budget, MIN_SPEECH_SECONDS)

    assert charged == pytest.approx(13.75, rel=0.001)
    assert heard < float(NORMAL[0]), "nhịp với khoảng lặng thật nằm dưới sàn"
    assert not pace_is_outlier(charged, syllables, "normal", NORMAL, fast_rate=heard)


def test_the_gate_reads_the_measured_silence_from_the_waveform() -> None:
    """Chỗ gọi phải đưa sóng âm vào phép đo, và chỉ đưa nó tới cận trên."""
    source = inspect.getsource(audio_io.validate_audio_array)

    assert "measured_silence_seconds(array, sample_rate)" in source
    assert "fast_rate=heard_rate" in source
    assert "if rate < hard_lower or heard_rate > hard_upper:" in source
