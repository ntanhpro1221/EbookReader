"""Va pipeline.py: vuot 1ms hai mep doan truoc khi ghep, de cho noi khong bi nhay.

CHUA AP. Lo 1b dang tong hop luc viet.

Lo 1 mat hai chuong vi `join discontinuity` (003: 0.219, 016: 0.216). Xem
docs/ONSET_CLICK.md, muc *"Khong nham voi join discontinuity"*, cho toan bo chuoi do.
"""
import io
import os
import sys
import tempfile
from pathlib import Path


def write_atomic(path: Path, text: str) -> None:
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    os.close(fd)
    io.open(tmp, "w", encoding="utf-8").write(text)
    os.replace(tmp, path)


root = Path(sys.argv[1])
p = root / "ebook_reader" / "pipeline.py"
s = io.open(p, encoding="utf-8").read()

# ---------------------------------------------------------------- hằng số + hàm
ANCHOR = "CHAPTER_REVIEW_STATUS = \"warning\""
assert ANCHOR in s, "khong khop cho chen"
HELPER = '''EDGE_FADE_SECONDS = 0.001
EDGE_FADE_MIN_AMPLITUDE = 0.001
"""Vuốt 1ms hai mép mỗi đoạn trước khi ghép, nhưng chỉ khi mép thật sự không ở gần 0.

Lô 1 mất hai chương vì `join discontinuity` (chương 003: 0,219; chương 016: 0,216). Chuỗi đo
đầy đủ ở docs/ONSET_CLICK.md; tóm tắt:

  - Phép kiểm **đúng**: cùng thống kê ấy đo tại 360 vị trí ngẫu nhiên cho trung vị 0,004 và
    cực đại 0,071, không giá trị nào chạm ngưỡng review 0,18.
  - Đứt gãy **không đến từ đoạn**: mép lớn nhất trong cả 121 đoạn của chương 003 là 0,052.
    Nó sinh ra ở khâu master, khi đoạn ở −25 LUFS được `loudnorm` kéo lên −20.
  - Nên **sinh lại seed là vô ích** — khác hẳn tiếng "tóp" đầu câu, thứ nằm trong đầu ra thô
    của model.

Vì mọi ranh giới đều có khoảng lặng chèn vào, bước nhảy tại chỗ nối **chính là** biên độ mẫu
mép. Vuốt mép về 0 thì bước nhảy về 0 — đúng theo định nghĩa, không cần đo để tin.

`EDGE_FADE_MIN_AMPLITUDE` **không phải một ngưỡng phán xử**. Vuốt một mép vốn đã bằng 0 thì
không đổi gì cả, nên nó chỉ quyết định *có bõ công chép file ra không*. Đo trên năm chương đầu
lô 1: trung vị mép là 0,0000 ở mọi chương, bốn chương sạch có cực đại 0,0011–0,0076, chương
hỏng có 0,0519. Với 0,001 thì gần như mọi đoạn vẫn đi đường tắt không chép.

1ms là 48 mẫu ở 48 kHz. Âm tiết mở đầu rộng từ 10ms, và xung "tóp" đo được rộng 5–22ms, nên
1ms không chạm tới cái nào.
"""


def fade_edges(audio, sample_rate: int):
    """Vuốt tuyến tính `EDGE_FADE_SECONDS` ở đầu và cuối. Trả về chính mảng đã sửa tại chỗ."""
    length = int(round(sample_rate * EDGE_FADE_SECONDS))
    if length < 1 or audio.size < 2 * length:
        return audio
    ramp = np.linspace(0.0, 1.0, length, endpoint=False, dtype=np.float32)
    audio[:length] *= ramp
    audio[-length:] *= ramp[::-1]
    return audio


def edge_amplitude(audio) -> float:
    if audio.size < 1:
        return 0.0
    return float(max(abs(float(audio[0])), abs(float(audio[-1]))))


CHAPTER_REVIEW_STATUS = "warning"'''
s = s.replace(ANCHOR, HELPER, 1)

# ---------------------------------------------------------------- đường tắt: vẫn phải vuốt
OLD = """            if (
                pitch_steps == 0
                and abs(formant_ratio - 1.0) <= 1e-6
                and not expressive
            ):
                rendered.append((source, break_ms))
                continue"""
NEW = """            if (
                pitch_steps == 0
                and abs(formant_ratio - 1.0) <= 1e-6
                and not expressive
            ):
                # Đường tắt cũ dùng thẳng file gốc. Vẫn dùng thẳng - trừ khi mép của nó đủ
                # lớn để thành một bước nhảy sau khi master kéo mức lên. Đo trên lô 1: đúng
                # một đoạn trong 121 rơi vào diện này.
                probe, probe_rate = sf.read(source, dtype="float32", always_2d=False)
                probe = np.asarray(probe, dtype=np.float32).reshape(-1)
                if edge_amplitude(probe) <= EDGE_FADE_MIN_AMPLITUDE:
                    rendered.append((source, break_ms))
                    continue
                delivery_root.mkdir(parents=True, exist_ok=True)
                destination = delivery_root / f"{int(row['seq']):07d}.wav"
                faded = fade_edges(probe.copy(), int(probe_rate))
                temp = destination.with_suffix(".part.wav")
                sf.write(temp, faded, int(probe_rate), subtype="PCM_16")
                os.replace(temp, destination)
                rendered.append((destination, break_ms))
                faded_edges += 1
                continue"""
assert OLD in s, "khong khop duong tat"
s = s.replace(OLD, NEW, 1)

# ---------------------------------------------------------------- đường có biến đổi
OLD = """            temp = destination.with_suffix(".part.wav")
            sf.write(temp, shifted, int(sample_rate), subtype="PCM_16")
            os.replace(temp, destination)
            rendered.append((destination, break_ms))
            transformed += 1"""
NEW = """            # Biến đổi âm sắc cũng có thể để lại mép không ở 0, nên vuốt ở đây luôn. Rẻ:
            # bản sao đã được ghi ra rồi.
            shifted = fade_edges(np.asarray(shifted, dtype=np.float32).reshape(-1), int(sample_rate))
            temp = destination.with_suffix(".part.wav")
            sf.write(temp, shifted, int(sample_rate), subtype="PCM_16")
            os.replace(temp, destination)
            rendered.append((destination, break_ms))
            transformed += 1"""
assert OLD in s, "khong khop duong bien doi"
s = s.replace(OLD, NEW, 1)

OLD = """        rendered: list[tuple[Path, int]] = []
        transformed = 0"""
NEW = """        rendered: list[tuple[Path, int]] = []
        transformed = 0
        faded_edges = 0"""
assert OLD in s, "khong khop bien dem"
s = s.replace(OLD, NEW, 1)

OLD = """        if transformed:
            self.log(
                f"Áp âm sắc nhân vật cho {transformed}/{len(rows)} segment của chapter "
                f"{chapter['chapter_index']} trước khi ghép."
            )"""
NEW = """        if transformed:
            self.log(
                f"Áp âm sắc nhân vật cho {transformed}/{len(rows)} segment của chapter "
                f"{chapter['chapter_index']} trước khi ghép."
            )
        if faded_edges:
            self.log(
                f"Vuốt mép {faded_edges}/{len(rows)} segment của chapter "
                f"{chapter['chapter_index']}: mép không ở 0 thành bước nhảy ở chỗ nối "
                "sau khi master kéo mức lên."
            )"""
assert OLD in s, "khong khop log"
s = s.replace(OLD, NEW, 1)

write_atomic(p, s)
print(f"da va {p}")

q = root / "tests" / "test_edge_fade_kills_the_join_jump.py"
write_atomic(
    q,
    '''"""Vuốt 1ms hai mép đưa bước nhảy ở chỗ nối về 0 — đúng theo định nghĩa.

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
''',
)
print(f"da tao {q}")
