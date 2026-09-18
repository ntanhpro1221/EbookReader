"""Thử một hằng số TỐC ĐỘ cho giọng dựng sẵn, trên audio thật, trước khi đưa nó vào dây chuyền.

    runtime/.venv/Scripts/python.exe scripts/preview_voice_adjustments.py --rows <audition.json> \
        --preset "Đức Trí" --speed 1.27 [--pitch 0] [--out <thư mục preview>]

Chỉ đọc audio đã có (các lượt `audition_presets.py`), không cần GPU.

## Vì sao có (18-09 10:3x)

Chủ sách nhận Đức Trí làm người dẫn chuyện, và thấy giọng ấy "đọc hơi chậm". Đo bằng ĐÚNG cổng
nhịp của dây chuyền (`audio_io.validate_audio_array`, băng `normal` [12,5 .. 24,5] kt/s), 23/25 câu
của Đức Trí bị gọi là ngoài băng; Thiền Tâm Đức 21/25, Kim Thanh 24/25, Mỹ Duyên 8/25 — cả bốn đều
là giọng kiểu "đọc truyện/kể chuyện". Dùng nguyên như thế thì gần hết lời kể bị thu lại liên tục.

`PRESET_BASE_PITCH_SEMITONES` (cái −4 của Thanh Bình) không chữa được: `tts.apply_pitch_variant`
tổng hợp lại bằng WORLD **trên cùng trục thời gian**, nên độ dài câu không đổi một mili giây. Cần
một hằng số tốc độ riêng. WORLD làm được luôn việc ấy mà không đụng cao độ: phân tích F0 / phổ /
aperiodicity y như `apply_pitch_variant`, rồi tổng hợp với chu kỳ khung nhỏ hơn — mọi khung giữ
nguyên, chỉ phát nhanh hơn. Script này dùng đúng các hằng số WORLD của `tts.py`, để thứ chủ sách nghe
thử là thứ dây chuyền sẽ tạo ra.
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path

import numpy as np
import pyworld
import soundfile as sf

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ebook_reader.audio_io import AudioQualityError, validate_audio_array  # noqa: E402
from ebook_reader.config import build_settings  # noqa: E402
from ebook_reader.tts import (  # noqa: E402
    WORLD_F0_CEIL_HZ,
    WORLD_F0_FLOOR_HZ,
    WORLD_FRAME_PERIOD_MS,
    apply_pitch_variant,
)


def change_speed(audio: np.ndarray, sample_rate: int, speed: float) -> np.ndarray:
    """Nhanh hơn `speed` lần, giữ nguyên cao độ và phổ: tổng hợp WORLD với chu kỳ khung / speed."""
    if abs(speed - 1.0) <= 1e-6:
        return np.asarray(audio, dtype=np.float32)
    waveform = np.asarray(audio, dtype=np.float64).reshape(-1)
    f0, time_axis = pyworld.harvest(waveform, sample_rate, f0_floor=WORLD_F0_FLOOR_HZ,
                                    f0_ceil=WORLD_F0_CEIL_HZ, frame_period=WORLD_FRAME_PERIOD_MS)
    f0 = pyworld.stonemask(waveform, f0, time_axis, sample_rate)
    envelope = pyworld.cheaptrick(waveform, f0, time_axis, sample_rate)
    aperiodicity = pyworld.d4c(waveform, f0, time_axis, sample_rate)
    out = pyworld.synthesize(f0, envelope, aperiodicity, sample_rate, WORLD_FRAME_PERIOD_MS / speed)
    peak = float(np.max(np.abs(waveform))) or 1.0
    out_peak = float(np.max(np.abs(out))) or 1.0
    return np.asarray(out * min(1.0, peak / out_peak), dtype=np.float32)


def pace_report(rows: list[dict], preset: str, speed: float, pitch: int, settings: dict,
                out: Path | None) -> dict:
    rates, outliers, errors, written = [], 0, 0, []
    for row in rows:
        if row["preset"] != preset:
            continue
        audio, rate = sf.read(row["wav"], dtype="float32")
        if pitch:
            audio = apply_pitch_variant(audio, rate, pitch)
        audio = change_speed(audio, rate, speed)
        try:
            _, metrics = validate_audio_array(audio, row["text"], settings, rate,
                                              {"pace": "normal", "kind": "narration", "text": row["text"]})
        except AudioQualityError:
            errors += 1
            continue
        if "chars_per_second" in metrics:
            rates.append(metrics["chars_per_second"])
            outliers += int(metrics.get("pace_outlier", 0) > 0)
        if out is not None and int(row["index"]) in (0, 1, 12, 18, 23):
            out.mkdir(parents=True, exist_ok=True)
            path = out / f"{int(row['index']):02d}.wav"
            sf.write(str(path), audio, rate, subtype="PCM_16")
            written.append(path.name)
    measured = len(rates) + errors
    return {"preset": preset, "speed": speed, "pitch": pitch, "median": statistics.median(rates) if rates else 0.0,
            "outliers": outliers + errors, "measured": measured, "written": written}


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--rows", type=Path, required=True, action="append")
    parser.add_argument("--preset", required=True)
    parser.add_argument("--speed", type=float, default=1.0)
    parser.add_argument("--pitch", type=int, default=0)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()
    rows = [row for path in args.rows for row in json.loads(path.read_text(encoding="utf-8"))["rows"]]
    report = pace_report(rows, args.preset, args.speed, args.pitch, build_settings("high_quality"), args.out)
    print(f"{report['preset']:14} toc do x{report['speed']:.2f} cao do {report['pitch']:+d} | "
          f"trung vi {report['median']:5.2f} kt/s | ngoai bang {report['outliers']}/{report['measured']}"
          + (f" | preview: {', '.join(report['written'])}" if report["written"] else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
