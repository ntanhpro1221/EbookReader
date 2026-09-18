"""Vá voice_catalog.py + tts.py: một hằng số TỐC ĐỘ cho mỗi giọng, áp bằng WORLD, giữ nguyên cao độ.

Chạy: python patch_a_slow_voice_reads_at_its_own_speed.py <root>

**XẾP Ở RANH GIỚI 6**, cùng lượt với nâng VieNeu 3.8.1. Bản vá này chỉ thêm CƠ CHẾ — bảng
`PRESET_SPEED_FACTOR` để rỗng, tức mọi giọng giữ tốc độ gốc và hành vi y như trước. Con số cho từng
giọng do bản vá thêm giọng điền, sau khi chủ sách nghe thử và chọn.

## Vì sao (18-09)

Chủ sách nhận Đức Trí làm người dẫn chuyện và thấy giọng ấy "đọc hơi chậm". Đo bằng đúng cổng nhịp
của dây chuyền (`validate_audio_array`, băng normal 12,5..24,5 kt/s): 23/25 câu của Đức Trí ngoài
băng, Thiền Tâm Đức 21, Kim Thanh 24, Mỹ Duyên 8 — cả bốn là giọng kiểu đọc truyện. Dùng nguyên thì
gần hết lời kể bị thu lại liên tục.

`PRESET_BASE_PITCH_SEMITONES` (cái −4 của Thanh Bình) KHÔNG làm được việc này, và cũng không thể
nhét tốc độ vào `apply_pitch_variant`: hàm ấy tổng hợp WORLD trên cùng trục thời gian rồi **cắt hoặc
đệm về đúng độ dài gốc** — một câu nói nhanh hơn sẽ bị đệm im lặng cho đủ độ dài cũ. Nên tốc độ là
một bước riêng, `apply_speed_change`, chạy sau bước cao độ: phân tích WORLD với đúng hằng số của
`tts.py`, rồi tổng hợp với chu kỳ khung nhỏ đi `speed` lần. Mọi khung giữ nguyên F0 và phổ, chỉ phát
nhanh hơn. `scripts/preview_voice_adjustments.py` là bản thử của đúng hàm này; các mức ×1,20..×1,35
đều đưa 25/25 câu về trong băng.

Bỏ qua tiếng cười "ha" (`HA_VOCALIZATION_DELIVERY_PROFILE`): đường ấy có bất biến số mẫu thô, và
đoạn ấy ngắn tới mức cổng nhịp không soi.
"""
import io
import sys
from pathlib import Path

root = Path(sys.argv[1])


def replace_once(path: Path, old: str, new: str) -> None:
    text = io.open(path, encoding="utf-8").read()
    assert text.count(old) == 1, f"{path.name}: khong khop mot lan duy nhat: {old.splitlines()[0]!r}"
    io.open(path, "w", encoding="utf-8").write(text.replace(old, new, 1))


# ------------------------------------------------------------------ voice_catalog.py
catalog = root / "ebook_reader" / "voice_catalog.py"
replace_once(catalog, '''PRESET_BASE_PITCH_SEMITONES = {
    "Thanh Bình": -4,
}''', '''PRESET_BASE_PITCH_SEMITONES = {
    "Thanh Bình": -4,
}
# Reading speed per preset, as a factor on the tempo: 1.25 says a line in 80% of the time, with
# the same pitch and the same spectrum. Register (above) cannot do this - WORLD resynthesises on
# the same time axis and `apply_pitch_variant` trims or pads back to the original length - so a
# slow preset needs its own knob. Measured 2026-09-18 with the pipeline's own pace gate: the
# storytelling presets of VieNeu 3.8.1 read at 10.9-12.7 chars/s against a normal band that
# starts at 12.5, which put 21-24 of 25 lines out of band. The owner chose each value by ear.
PRESET_SPEED_FACTOR: dict[str, float] = {}
SPEED_FACTOR_MIN = 0.80
SPEED_FACTOR_MAX = 1.50''')
replace_once(catalog, '''def base_pitch_for_preset(preset_name: str) -> int:
    """The calibrated reading register for this preset, in semitones."""
    return int(PRESET_BASE_PITCH_SEMITONES.get(preset_name, 0))''', '''def base_pitch_for_preset(preset_name: str) -> int:
    """The calibrated reading register for this preset, in semitones."""
    return int(PRESET_BASE_PITCH_SEMITONES.get(preset_name, 0))


def speed_factor_for_preset(preset_name: str) -> float:
    """The calibrated reading speed for this preset; 1.0 when none was set."""
    return float(PRESET_SPEED_FACTOR.get(str(preset_name), 1.0))''')
print(f"da va {catalog}")

# ------------------------------------------------------------------ tts.py
tts = root / "ebook_reader" / "tts.py"
replace_once(tts, "from .voice_catalog import FORMANT_RATIO_MAX, FORMANT_RATIO_MIN\n",
             "from .voice_catalog import (\n"
             "    FORMANT_RATIO_MAX,\n"
             "    FORMANT_RATIO_MIN,\n"
             "    SPEED_FACTOR_MAX,\n"
             "    SPEED_FACTOR_MIN,\n"
             "    speed_factor_for_preset,\n"
             ")\n")
replace_once(tts, '''def apply_voice_variant(
    audio: Any,
    sample_rate: int,
    pitch_semitones: int,
    formant_ratio: float,
) -> np.ndarray:''', '''def apply_speed_change(audio: Any, sample_rate: int, speed: float) -> np.ndarray:
    """Read the same line `speed` times faster, keeping pitch and spectrum.

    WORLD analysis with the same constants as `apply_pitch_variant`, then synthesis with a frame
    period `speed` times shorter: every frame keeps its F0 and envelope, it is only played
    faster. Unlike `apply_pitch_variant` the length changes on purpose, so nothing is trimmed or
    padded. See `PRESET_SPEED_FACTOR` for why a slow preset needs this.
    """
    array = np.asarray(audio, dtype=np.float32).reshape(-1)
    speed = float(speed)
    if abs(speed - 1.0) <= 1e-6 or array.size == 0:
        return array
    if not SPEED_FACTOR_MIN <= speed <= SPEED_FACTOR_MAX:
        raise ValueError(f"speed factor {speed} is outside [{SPEED_FACTOR_MIN}, {SPEED_FACTOR_MAX}]")
    if sample_rate < 8_000:
        raise ValueError(f"WORLD speed change requires at least 8000 Hz, got {sample_rate}")
    waveform = np.asarray(array, dtype=np.float64)
    f0, time_axis = pyworld.harvest(
        waveform,
        sample_rate,
        f0_floor=WORLD_F0_FLOOR_HZ,
        f0_ceil=WORLD_F0_CEIL_HZ,
        frame_period=WORLD_FRAME_PERIOD_MS,
    )
    f0 = pyworld.stonemask(waveform, f0, time_axis, sample_rate)
    if int(np.count_nonzero(f0 > 0.0)) < WORLD_MIN_VOICED_FRAMES:
        raise ValueError("WORLD could not find enough voiced frames for a speed change")
    spectral_envelope = pyworld.cheaptrick(waveform, f0, time_axis, sample_rate)
    aperiodicity = pyworld.d4c(waveform, f0, time_axis, sample_rate)
    faster = pyworld.synthesize(
        f0,
        spectral_envelope,
        aperiodicity,
        sample_rate,
        frame_period=WORLD_FRAME_PERIOD_MS / speed,
    )
    peak = float(np.max(np.abs(waveform))) or 1.0
    faster_peak = float(np.max(np.abs(faster))) or 1.0
    return np.asarray(faster * min(1.0, peak / faster_peak), dtype=np.float32)


def apply_voice_variant(
    audio: Any,
    sample_rate: int,
    pitch_semitones: int,
    formant_ratio: float,
) -> np.ndarray:''')
replace_once(tts, '''                self.log(
                    f"Bỏ biến thể cao độ {pitch_steps:+d} cho segment {row['stable_id']} "
                    f"vì xử lý pitch lỗi: {exc}"
                )
            vocalization_provenance: dict[str, Any] = {}''', '''                self.log(
                    f"Bỏ biến thể cao độ {pitch_steps:+d} cho segment {row['stable_id']} "
                    f"vì xử lý pitch lỗi: {exc}"
                )
            # Tốc độ riêng của giọng (PRESET_SPEED_FACTOR), sau cao độ vì hàm cao độ giữ nguyên
            # độ dài. Bỏ qua tiếng cười "ha": đường ấy có bất biến số mẫu thô.
            speed_factor = speed_factor_for_preset(str(_row_value(profile, "preset_name", "")))
            speed_change_skipped = False
            if (
                abs(speed_factor - 1.0) > 1e-6
                and vocalization_delivery_profile != HA_VOCALIZATION_DELIVERY_PROFILE
            ):
                try:
                    audio = apply_speed_change(audio, self.vieneu.sample_rate, speed_factor)
                except Exception as exc:  # noqa: BLE001
                    speed_change_skipped = True
                    self.log(
                        f"Bỏ hệ số tốc độ x{speed_factor:.2f} cho segment {row['stable_id']} "
                        f"vì xử lý lỗi: {exc}"
                    )
            vocalization_provenance: dict[str, Any] = {}''')
replace_once(tts, '''            metrics["effective_pitch_semitones"] = (
                0 if pitch_variant_skipped else pitch_steps
            )''', '''            metrics["effective_pitch_semitones"] = (
                0 if pitch_variant_skipped else pitch_steps
            )
            metrics["speed_factor"] = float(speed_factor)
            metrics["effective_speed_factor"] = 1.0 if speed_change_skipped else float(speed_factor)''')
print(f"da va {tts}")

# ------------------------------------------------------------------ test
test = root / "tests" / "test_a_slow_voice_reads_at_its_own_speed.py"
test.write_text('''"""Hằng số tốc độ mỗi giọng: nhanh hơn thật, giữ cao độ, và mặc định không đổi gì.

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
    pitch_at = source.index("pitched_audio = apply_pitch_variant(\\n                        audio,\\n                        self.vieneu.sample_rate,\\n                        pitch_steps,\\n                    )")
    speed_at = source.index("audio = apply_speed_change(audio, self.vieneu.sample_rate, speed_factor)")
    assert pitch_at < speed_at
    assert "vocalization_delivery_profile != HA_VOCALIZATION_DELIVERY_PROFILE" in source[pitch_at:speed_at]
''', encoding="utf-8")
print(f"da viet {test}")
