"""Vuốt 1ms hai mép đưa bước nhảy ở chỗ nối về 0 — đúng theo định nghĩa.

Lô 1 mất hai chương vì `join discontinuity` (003: 0,219; 016: 0,216). Vì mọi ranh giới đoạn
đều có khoảng lặng chèn vào, bước nhảy tại chỗ nối **chính là** biên độ mẫu mép của đoạn; vuốt
mép về 0 thì bước nhảy về 0, bất kể khâu master khuếch đại bao nhiêu.
"""
from __future__ import annotations

import numpy as np

from ebook_reader.pipeline import (
    EDGE_FADE_MIN_AMPLITUDE,
    EDGE_FADE_SECONDS,
    edge_amplitude,
    fade_edges,
)

RATE = 48_000


def _take_starting_mid_waveform() -> np.ndarray:
    """Bản thu bắt đầu và kết thúc giữa chừng sóng âm - đúng thứ đã giết chương 003."""
    t = np.arange(RATE) / RATE
    return (0.3 * np.sin(2 * np.pi * 220 * t + 1.2)).astype(np.float32)


def test_the_edge_step_becomes_zero() -> None:
    audio = _take_starting_mid_waveform()
    assert edge_amplitude(audio) > 0.2, "mẫu thử phải thật sự có mép lớn"

    faded = fade_edges(audio.copy(), RATE)

    assert edge_amplitude(faded) == 0.0


def test_it_only_touches_one_millisecond() -> None:
    """Phần giữa không được đụng tới - 1ms là 48 mẫu ở 48 kHz."""
    audio = _take_starting_mid_waveform()
    faded = fade_edges(audio.copy(), RATE)
    n = int(round(RATE * EDGE_FADE_SECONDS))

    assert np.array_equal(faded[n:-n], audio[n:-n])
    assert n == 48


def test_a_clean_take_is_unchanged_where_it_matters() -> None:
    """Mép đã ở 0 thì vuốt không đổi gì - đó là lý do ngưỡng chỉ là chuyện hiệu năng.

    Bản thu thật bắt đầu và kết thúc bằng **im lặng**, không phải giữa chừng sóng âm: đo trên
    lô 1, trung vị biên độ mép là 0,0000 ở cả năm chương đầu.

    (Bản đầu của test này dùng một sin trọn giây làm "sạch" và nó **đỏ**: sin ấy kết thúc
    trước điểm cắt không đúng một mẫu, để lại mép 0,0086 - to hơn cả mép lớn nhất của bốn
    chương sạch thật. Một tín hiệu tổng hợp không tự nhiên giống dữ liệu thật.)
    """
    t = np.arange(RATE) / RATE
    clean = (0.3 * np.sin(2 * np.pi * 220 * t)).astype(np.float32)
    clean[:200] = 0.0
    clean[-200:] = 0.0
    assert edge_amplitude(clean) < EDGE_FADE_MIN_AMPLITUDE

    faded = fade_edges(clean.copy(), RATE)

    assert np.array_equal(faded, clean), "vuốt vùng đã là im lặng thì không đổi một mẫu nào"


def test_a_very_short_take_is_left_alone() -> None:
    """Ngắn hơn hai lần cửa sổ vuốt thì không vuốt, để không nuốt cả đoạn."""
    tiny = np.full(10, 0.5, dtype=np.float32)
    assert np.array_equal(fade_edges(tiny.copy(), RATE), tiny)
