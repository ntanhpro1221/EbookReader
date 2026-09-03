"""Is the 369 ms fixed cost the encoder chewing a window padded to 30 seconds?

One real take, padded with silence to increasing lengths. The speech is identical, so the
decoder has the same tokens to produce every time. If the encoder always processes a
padded 30-second window, every length below 30s costs the same and there is a step at 30.
If instead the encoder scales with what it is given, cost climbs with the padding.
"""
from __future__ import annotations

import sqlite3
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, "D:/Novels/Ebook Reader_dev/_internal")
import numpy as np

from ebook_reader.asr import load_audio_for_whisper

DB = (
    "D:/Novels/Audiobooks/_versions/v0.2.0-alpha.32/alpha32_02502ba320/project.sqlite3"
)
LENGTHS = [3.0, 6.0, 12.0, 20.0, 28.0, 31.0, 45.0, 58.0, 61.0]
REPEATS = 3


def main() -> int:
    connection = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    row = connection.execute(
        "SELECT wav_path, wav_duration FROM segments "
        "WHERE wav_path IS NOT NULL AND wav_duration BETWEEN 2.0 AND 3.0 "
        "ORDER BY id LIMIT 1"
    ).fetchone()
    connection.close()
    if row is None or not Path(str(row["wav_path"])).is_file():
        print("không tìm được bản thu ngắn")
        return 1

    speech = load_audio_for_whisper(Path(str(row["wav_path"])))
    speech_seconds = len(speech) / 16000
    print(f"bản thu gốc: {speech_seconds:.2f}s ({row['wav_path']})")

    import torch  # noqa: F401
    from faster_whisper import WhisperModel

    model = WhisperModel("turbo", device="cuda", compute_type="float16")
    options = {
        "language": "vi",
        "task": "transcribe",
        "temperature": 0.0,
        "condition_on_previous_text": False,
        "beam_size": 1,
    }
    list(model.transcribe(speech, **options)[0])  # warm

    print()
    print(f"{'độ dài':>8}  {'giải mã':>10}  {'ký tự':>6}")
    results: list[tuple[float, float]] = []
    for target in LENGTHS:
        padded = np.zeros(int(target * 16000), dtype=speech.dtype)
        padded[: len(speech)] = speech[: len(padded)]
        timings = []
        text = ""
        for _ in range(REPEATS):
            started = time.perf_counter()
            segments, _info = model.transcribe(padded, **options)
            text = "".join(item.text for item in segments).strip()
            timings.append(time.perf_counter() - started)
        best = min(timings)
        results.append((target, best))
        print(f"{target:7.1f}s  {best * 1000:9.1f}ms  {len(text):6d}")

    print()
    under = [seconds for length, seconds in results if length < 30]
    over = [seconds for length, seconds in results if 30 < length < 60]
    if under and over:
        print(f"  trung vị dưới 30s : {statistics.median(under) * 1000:7.1f} ms")
        print(f"  trung vị 31-58s   : {statistics.median(over) * 1000:7.1f} ms")
        spread = (max(under) - min(under)) / min(under)
        print(f"  chênh lệch trong nhóm dưới 30s: {spread:.1%}")
        print()
        if spread < 0.25 and statistics.median(over) > statistics.median(under) * 1.5:
            print("ĐÚNG: chi phí phẳng dưới 30 giây rồi nhảy bậc - encoder ăn cả cửa sổ đệm.")
        elif spread < 0.25:
            print("Phẳng dưới 30s nhưng không nhảy rõ ở 30 - encoder cố định, cần xem thêm.")
        else:
            print("SAI: chi phí tăng theo phần đệm - không phải cửa sổ 30 giây cố định.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
