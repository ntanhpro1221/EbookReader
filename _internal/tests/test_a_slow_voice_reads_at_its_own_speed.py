"""Hằng số tốc độ mỗi giọng: nhanh hơn thật, giữ cao độ, và mặc định không đổi gì.

Vì sao có: bốn giọng kiểu đọc truyện của VieNeu 3.8.1 đọc 10,9-12,7 kt/s, dưới sàn 12,5 của cổng
nhịp - Đức Trí, người dẫn chuyện chủ sách chọn, ngoài băng 23/25 câu. Cao độ gốc không chữa được vì
`apply_pitch_variant` giữ nguyên độ dài câu. Xem `PRESET_SPEED_FACTOR`.
"""
from __future__ import annotations

import numpy as np
import pytest
import pyworld

from ebook_reader.tts import apply_speed_change
from ebook_reader.voice_catalog import (
    PRESET_SPEED_FACTOR,
    SPEED_FACTOR_MAX,
    SPEED_FACTOR_MIN,
    speed_factor_for_preset,
)

RATE = 24_000


def voiced(seconds: float = 1.2, f0: float = 150.0) -> np.ndarray:
    t = np.arange(int(RATE * seconds)) / RATE
    tone = sum(np.sin(2 * np.pi * f0 * k * t) / k for k in range(1, 8))
    envelope = 0.6 + 0.4 * np.sin(2 * np.pi * 3.0 * t)
    return (0.2 * tone * envelope).astype(np.float32)


def median_f0(audio: np.ndarray) -> float:
    f0, _ = pyworld.harvest(audio.astype(np.float64), RATE, f0_floor=55.0, f0_ceil=600.0)
    return float(np.median(f0[f0 > 0]))


@pytest.mark.parametrize("speed", [1.20, 1.27, 1.35])
def test_a_speed_factor_shortens_the_line_by_that_factor(speed: float) -> None:
    audio = voiced()
    faster = apply_speed_change(audio, RATE, speed)
    assert faster.size / audio.size == pytest.approx(1.0 / speed, rel=0.03)


def test_a_speed_factor_keeps_the_pitch() -> None:
    audio = voiced(f0=150.0)
    faster = apply_speed_change(audio, RATE, 1.30)
    assert median_f0(faster) == pytest.approx(median_f0(audio), rel=0.03)


def test_no_factor_means_no_change_at_all() -> None:
    audio = voiced()
    assert np.array_equal(apply_speed_change(audio, RATE, 1.0), audio)
    assert speed_factor_for_preset("a preset nobody tuned") == 1.0


def test_a_factor_outside_the_range_is_refused() -> None:
    with pytest.raises(ValueError):
        apply_speed_change(voiced(), RATE, SPEED_FACTOR_MAX + 0.1)
    with pytest.raises(ValueError):
        apply_speed_change(voiced(), RATE, SPEED_FACTOR_MIN - 0.1)


def test_every_catalogued_factor_is_inside_the_range() -> None:
    for name, factor in PRESET_SPEED_FACTOR.items():
        assert SPEED_FACTOR_MIN <= factor <= SPEED_FACTOR_MAX, name


def test_the_speed_step_runs_after_pitch_and_skips_the_laugh() -> None:
    # Hàm cao độ cắt/đệm về độ dài gốc, nên tốc độ PHẢI chạy sau nó; và tiếng cười "ha" có bất
    # biến số mẫu thô nên không được đổi tốc độ. Soi thẳng mã, vì dựng cả engine TTS cho một thứ
    # tự hai dòng là quá nặng.
    from pathlib import Path

    source = (Path(__file__).resolve().parent.parent / "ebook_reader" / "tts.py").read_text(encoding="utf-8")
    pitch_at = source.index("pitched_audio = apply_pitch_variant(\n                        audio,\n                        self.vieneu.sample_rate,\n                        pitch_steps,\n                    )")
    speed_at = source.index("audio = apply_speed_change(audio, self.vieneu.sample_rate, speed_factor)")
    assert pitch_at < speed_at
    assert "vocalization_delivery_profile != HA_VOCALIZATION_DELIVERY_PROFILE" in source[pitch_at:speed_at]
