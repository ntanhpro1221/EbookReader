r"""Ngân sách nghỉ của thước nhịp có khớp khoảng lặng CÓ THẬT trong bản thu không? — đo, không đoán.

    python scripts/measure_pause_budget_vs_silence.py            # lấy mẫu mọi project của cuốn hiện tại
    python scripts/measure_pause_budget_vs_silence.py --per-band 40 --db-floor -40

Chỉ đọc: mở WAV đã lưu, đo im lặng, so với ngân sách. Không sinh audio, không cần GPU, không ghi gì
vào project.

## Câu hỏi

`inspect_wav` tính nhịp đọc bằng cách **trừ đi một ngân sách nghỉ** rồi chia:

    pause = min(PAUSE_GROUP_SECONDS × số nhóm dấu câu, thời lượng × MAX_PAUSE_FRACTION)
    rate  = ký tự đọc được / (thời lượng − pause)

Ngân sách ấy là một phỏng đoán: 0,276 giây cho mỗi nhóm dấu câu. Phép thử GPU 08:30 ngày 2026-09-15
cho thấy nó sai hẳn ở câu ngắn — bốn dạng văn bản của cùng một câu (có/không ngoặc kép, có/không
ngoặc đơn lồng) cho **cùng một thời lượng tới hai chữ số thập phân**, nghĩa là giọng đọc **không nghỉ**
ở dấu ngoặc, trong khi ngân sách vẫn tính 0,276 giây cho mỗi dấu. Với một câu thoại 2 giây, ngân sách
chạm trần `MAX_PAUSE_FRACTION` và ăn 60% thời lượng; nhịp bị thổi từ 16,17 lên 30,09 kt/s và câu bị
kết tội "đọc quá nhanh". Ba đoạn của cuốn 2 mất hẳn bản thu vì đúng cơ chế ấy (chương 082, 131 — cả
hai có ngoặc đơn lồng — và 090).

Hai cách chữa hiển nhiên đều đã bị **số liệu bác bỏ**:

    bỏ mọi dấu ngoặc khỏi mẫu     → 248 đoạn "đạt → ngoài băng", cứu được 3   (30.474 đoạn)
    bỏ riêng nháy/ngoặc đơn       →  12 đoạn "đạt → ngoài băng", cứu được 3   (33.106 đoạn)

Vì ngân sách được chỉnh chuẩn *cùng với* những dấu ấy: rút chúng ra làm nhịp tụt và cận **dưới** bắt
đầu kết tội. Nên hướng còn lại là đừng đoán nữa: `pause = min(ngân sách, khoảng lặng ĐO ĐƯỢC)`.

## Script này đo gì

Với mẫu đoạn theo từng dải thời lượng: khoảng lặng thật (tổng các quãng dưới `--db-floor`, mỗi quãng
dài hơn `--min-gap`), ngân sách hiện tại, và tỉ số. Bảng in ra trả lời đúng câu cần trả lời trước khi
viết mã:

- Câu **dài** có ngân sách ≈ khoảng lặng thật? Nếu có, `min()` không đổi gì cho chúng - tức cận dưới
  không bị đụng, và 248/12 ca "đạt → ngoài băng" ở trên không xảy ra.
- Câu **ngắn** có ngân sách ≫ khoảng lặng thật? Nếu có, đó chính là chỗ nó kết tội oan, và `min()`
  chữa đúng chỗ ấy.
"""
from __future__ import annotations

import argparse
import collections
import glob
import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402
import soundfile as sf  # noqa: E402

from ebook_reader.audio_io import (  # noqa: E402
    MAX_PAUSE_FRACTION,
    PAUSE_GROUP_SECONDS,
    pause_group_count,
)

try:
    from scripts.book_paths import VERSIONS  # noqa: E402
except ImportError:  # chạy trực tiếp
    from book_paths import VERSIONS  # noqa: E402

BANDS = ((0.0, 2.0), (2.0, 4.0), (4.0, 8.0), (8.0, 16.0), (16.0, 1e9))


def _say(line: str) -> None:
    try:
        print(line, flush=True)
    except UnicodeEncodeError:
        print(line.encode("ascii", "backslashreplace").decode("ascii"), flush=True)


def measured_silence(path: Path, *, db_floor: float, min_gap: float) -> float | None:
    """Tổng số giây im lặng trong file: các quãng liên tiếp dưới ngưỡng, dài hơn `min_gap`."""
    try:
        array, rate = sf.read(str(path), dtype="float32", always_2d=False)
    except (OSError, RuntimeError):
        return None
    if array.ndim > 1:
        array = array.mean(axis=1)
    if array.size == 0:
        return None
    hop = max(int(rate * 0.01), 1)  # cửa sổ 10 ms
    frames = array[: array.size - array.size % hop].reshape(-1, hop)
    rms = np.sqrt(np.maximum((frames**2).mean(axis=1), 1e-12))
    quiet = 20.0 * np.log10(rms) < db_floor
    total = 0.0
    run = 0
    for flag in quiet:
        if flag:
            run += 1
            continue
        if run * 0.01 >= min_gap:
            total += run * 0.01
        run = 0
    if run * 0.01 >= min_gap:
        total += run * 0.01
    return total


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--per-band", type=int, default=30, help="số đoạn mẫu mỗi dải thời lượng")
    parser.add_argument("--db-floor", type=float, default=-40.0, help="dBFS coi là im lặng")
    parser.add_argument("--min-gap", type=float, default=0.05, help="quãng ngắn hơn thì không tính")
    parser.add_argument("--versions", type=Path, default=VERSIONS)
    args = parser.parse_args(argv)

    picked: dict[tuple[float, float], list[dict]] = collections.defaultdict(list)
    for database in sorted(glob.glob(str(args.versions / "*" / "*" / "project.sqlite3"))):
        if all(len(rows) >= args.per_band for rows in picked.values()) and len(picked) == len(BANDS):
            break
        connection = sqlite3.connect(f"file:{Path(database).as_posix()}?mode=ro", uri=True)
        connection.row_factory = sqlite3.Row
        try:
            rows = connection.execute(
                "SELECT text, wav_path, wav_duration, signal_json FROM segments "
                "WHERE wav_path IS NOT NULL AND wav_duration > 0"
            ).fetchall()
        except sqlite3.Error:
            continue
        finally:
            connection.close()
        for row in rows:
            duration = float(row["wav_duration"])
            band = next(b for b in BANDS if b[0] <= duration < b[1])
            if len(picked[band]) >= args.per_band:
                continue
            path = Path(str(row["wav_path"]))
            if not path.is_file():
                continue
            picked[band].append({"text": str(row["text"]), "duration": duration, "path": path,
                                 "signal": row["signal_json"]})

    _say(f"ngưỡng im lặng {args.db_floor:.0f} dBFS, quãng ≥ {args.min_gap*1000:.0f} ms")
    _say("")
    _say(f"{'dải giây':>12} {'n':>4} {'ngân sách':>10} {'lặng thật':>10} {'ngân sách/lặng':>15} {'chạm trần':>10}")
    for band in BANDS:
        rows = picked.get(band, [])
        if not rows:
            continue
        budgets: list[float] = []
        silences: list[float] = []
        capped = 0
        for item in rows:
            groups = pause_group_count(item["text"])
            raw = PAUSE_GROUP_SECONDS * groups
            budget = min(raw, item["duration"] * MAX_PAUSE_FRACTION)
            capped += int(raw > item["duration"] * MAX_PAUSE_FRACTION)
            silence = measured_silence(item["path"], db_floor=args.db_floor, min_gap=args.min_gap)
            if silence is None:
                continue
            budgets.append(budget)
            silences.append(silence)
        if not budgets:
            continue
        ratio = sum(budgets) / max(sum(silences), 1e-6)
        label = f"{band[0]:.0f}–{band[1]:.0f}" if band[1] < 1e9 else f"{band[0]:.0f}+"
        _say(
            f"{label:>12} {len(budgets):>4} {sum(budgets)/len(budgets):>9.2f}s"
            f" {sum(silences)/len(silences):>9.2f}s {ratio:>14.2f}x {capped:>9}"
        )
    _say("")
    _say("ngân sách/lặng > 1 = thước đo trừ nhiều hơn số giây giọng thật sự im.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
