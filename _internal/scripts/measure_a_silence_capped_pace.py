r"""Chặn ngân sách nghỉ bằng khoảng lặng CÓ THẬT thì cứu bao nhiêu câu, và giết bao nhiêu?

    python scripts/measure_a_silence_capped_pace.py --limit 4000
    python scripts/measure_a_silence_capped_pace.py --limit 1500 --floors -30,-35,-40

Chỉ đọc: mở WAV đã lưu và database ở chế độ read-only, không sinh audio, không cần GPU,
không ghi gì vào project.

## Vì sao phải đo trước khi viết mã

`validate_audio_array` tính nhịp đọc bằng cách trừ một **ngân sách nghỉ** phỏng đoán:

    pause = min(PAUSE_GROUP_SECONDS × số nhóm dấu câu, thời lượng × MAX_PAUSE_FRACTION)
    rate  = ký tự đọc được / (thời lượng − pause)

Phép thử GPU 08:30 ngày 2026-09-15 cho thấy phỏng đoán ấy sai hẳn ở câu ngắn: bốn dạng văn
bản của **cùng một câu** (có/không nháy, có/không ngoặc đơn lồng) cho cùng một thời lượng tới
hai chữ số thập phân — giọng đọc KHÔNG nghỉ ở dấu ngoặc — trong khi ngân sách vẫn tính 0,276
giây mỗi dấu. Với một câu thoại 2 giây, ngân sách chạm trần `MAX_PAUSE_FRACTION` và ăn 60%
thời lượng: nhịp bị thổi từ 16,17 lên 30,09 kt/s và câu bị kết tội "đọc quá nhanh". Cuốn 2 mất
hẳn bản thu của ba đoạn vì đúng cơ chế ấy (chương 082, 131 — cả hai có ngoặc đơn lồng — và 090).

Hai cách chữa hiển nhiên đã bị số liệu bác bỏ (`measure_pause_budget_vs_silence.py` giữ phép
đo): rút dấu ngoặc khỏi mẫu đếm làm 248 đoạn "đạt → ngoài băng" để cứu 3, vì ngân sách được
chỉnh chuẩn *cùng với* những dấu ấy. Hướng còn lại là đừng đoán: `pause = min(ngân sách,
khoảng lặng ĐO ĐƯỢC)`.

Chặn như thế chỉ **hạ** nhịp đo được, nên nó chỉ có thể cứu ở cận TRÊN và chỉ có thể giết ở
cận DƯỚI. Script này đếm đúng hai con số ấy trên kho bản thu thật, cho từng ngưỡng im lặng:

    chặn   : ngân sách bị khoảng lặng cắt bớt (số đoạn thật sự đổi số)
    cứu    : trước bị kết tội (ngoài băng, hoặc vượt hẳn dải an toàn), sau thì không
    giết   : trước đạt, sau bị kết tội

Ngưỡng đo **so với đỉnh** chứ không phải dBFS tuyệt đối, vì `atomic_write_wav` gọi
`validate_audio_array` hai lần — một lần trước khi cân âm lượng và một lần sau — và phép đo
phải cho cùng một câu trả lời ở cả hai lần, nếu không cùng một bản thu sẽ đạt ở lần này và
trượt ở lần kia. Nhân một hệ số vào toàn sóng âm không đổi tỉ số rms/đỉnh.
"""
from __future__ import annotations

import argparse
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
    MIN_SPEECH_SECONDS,
    PAUSE_GROUP_SECONDS,
    RATE_HARD_MAX_FACTOR,
    RATE_HARD_MIN_FACTOR,
    pace_is_outlier,
    pause_group_count,
    spoken_speakable_chars,
    spoken_syllables,
)

try:
    from scripts.book_paths import VERSIONS  # noqa: E402
except ImportError:  # chạy trực tiếp
    from book_paths import VERSIONS  # noqa: E402

DEFAULT_BANDS = {"slow": (7.0, 19.0), "normal": (12.5, 24.5), "fast": (14.0, 30.0)}
FRAME_SECONDS = 0.010
MIN_GAP_SECONDS = 0.05
# tts.rate_check_min_chars: dưới ngưỡng này phép kiểm nhịp không chạy, nên cũng không đếm.
RATE_CHECK_MIN_CHARS = 24


def _say(line: str) -> None:
    try:
        print(line, flush=True)
    except UnicodeEncodeError:
        print(line.encode("ascii", "backslashreplace").decode("ascii"), flush=True)


def silence_seconds(
    array: np.ndarray,
    sample_rate: int,
    *,
    floor_below_peak: float,
    frame_seconds: float = FRAME_SECONDS,
    min_gap: float = MIN_GAP_SECONDS,
) -> float:
    """Tổng số giây im lặng: các quãng liên tiếp dưới ngưỡng, mỗi quãng dài hơn `min_gap`."""
    if array.size == 0 or sample_rate <= 0:
        return 0.0
    peak = float(np.max(np.abs(array)))
    if peak <= 0.0:
        return float(array.size / sample_rate)
    hop = max(1, int(round(sample_rate * frame_seconds)))
    usable = array.size - array.size % hop
    if usable < hop:
        return 0.0
    frames = array[:usable].reshape(-1, hop).astype(np.float64)
    rms = np.sqrt(np.maximum((frames**2).mean(axis=1), 1e-20))
    quiet = 20.0 * np.log10(rms / peak) < floor_below_peak
    if not quiet.any():
        return 0.0
    padded = np.concatenate(([False], quiet, [False]))
    edges = np.flatnonzero(padded[1:] != padded[:-1])
    runs = edges[1::2] - edges[0::2]
    frame = hop / sample_rate
    # So bằng SỐ KHUNG như `audio_io.measured_silence_seconds`, không bằng giây: 5 × 0,01 không
    # đúng bằng 0,05 trong số thực nhị phân, và một quãng đúng bằng ngưỡng sẽ được tính hay
    # không tùy vào lỗi làm tròn. Phép đo phải là đúng phép đo mà mã đã vá dùng.
    min_frames = max(1, int(round(min_gap / frame)))
    return float(runs[runs >= min_frames].sum() * frame)


def verdict(
    text: str,
    duration: float,
    pace: str,
    bounds: tuple[float, float],
    silence: float | None = None,
) -> tuple[bool, bool, float, float]:
    """(ngoài băng, vượt dải an toàn, nhịp, ngân sách) — y phép tính của `validate_audio_array`."""
    chars = spoken_speakable_chars(text)
    budget = min(PAUSE_GROUP_SECONDS * pause_group_count(text), duration * MAX_PAUSE_FRACTION)
    if silence is not None:
        budget = min(budget, silence)
    speech = max(duration - budget, MIN_SPEECH_SECONDS)
    rate = chars / speech
    syllable_rate = spoken_syllables(text) / speech
    hard = rate < bounds[0] * RATE_HARD_MIN_FACTOR or rate > bounds[1] * RATE_HARD_MAX_FACTOR
    return pace_is_outlier(rate, syllable_rate, pace, bounds), hard, rate, budget


def _bands(root: Path) -> dict[str, tuple[float, float]]:
    settings = root / "book_settings.json"
    if not settings.is_file():
        return dict(DEFAULT_BANDS)
    try:
        raw = json.loads(settings.read_text(encoding="utf-8"))
        ranges = raw.get("tts", {}).get("pace_chars_per_second", {})
        got = {key: (float(value[0]), float(value[1])) for key, value in ranges.items()}
        return got or dict(DEFAULT_BANDS)
    except Exception:  # noqa: BLE001
        return dict(DEFAULT_BANDS)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--limit", type=int, default=4000, help="số đoạn tối đa (đọc WAV là phần tốn)")
    parser.add_argument("--floors", default="-30,-35,-40", help="ngưỡng im lặng so với đỉnh, dB")
    parser.add_argument("--min-gap", type=float, default=MIN_GAP_SECONDS)
    parser.add_argument("--versions", type=Path, default=VERSIONS)
    args = parser.parse_args(argv)

    floors = [float(piece) for piece in args.floors.split(",") if piece.strip()]
    tally = {floor: {"capped": 0, "cured": 0, "cured_hard": 0, "killed": 0, "killed_hard": 0}
             for floor in floors}
    examples: dict[float, list[str]] = {floor: [] for floor in floors}
    seen = 0
    skipped_short = 0

    for database in sorted(glob.glob(str(args.versions / "*" / "*" / "project.sqlite3"))):
        if seen >= args.limit:
            break
        root = Path(database).parent
        bands = _bands(root)
        connection = sqlite3.connect(f"file:{Path(database).as_posix()}?mode=ro", uri=True)
        connection.row_factory = sqlite3.Row
        try:
            rows = connection.execute(
                "SELECT stable_id, text, pace, wav_path, wav_duration FROM segments "
                "WHERE wav_path IS NOT NULL AND wav_duration > 0"
            ).fetchall()
        except sqlite3.Error:
            continue
        finally:
            connection.close()
        for row in rows:
            if seen >= args.limit:
                break
            text = str(row["text"])
            if spoken_speakable_chars(text) < RATE_CHECK_MIN_CHARS:
                skipped_short += 1
                continue
            path = Path(str(row["wav_path"]))
            if not path.is_file():
                continue
            try:
                array, sample_rate = sf.read(str(path), dtype="float32", always_2d=False)
            except (OSError, RuntimeError):
                continue
            if getattr(array, "ndim", 1) > 1:
                array = array.mean(axis=1)
            array = np.asarray(array, dtype=np.float32)
            pace = str(row["pace"] or "normal")
            bounds = bands.get(pace, bands.get("normal", DEFAULT_BANDS["normal"]))
            duration = float(row["wav_duration"])
            was_outlier, was_hard, rate_now, budget_now = verdict(text, duration, pace, bounds)
            seen += 1
            for floor in floors:
                quiet = silence_seconds(
                    array, int(sample_rate), floor_below_peak=floor, min_gap=args.min_gap
                )
                now_outlier, now_hard, rate_new, budget_new = verdict(
                    text, duration, pace, bounds, silence=quiet
                )
                cell = tally[floor]
                if budget_new < budget_now - 1e-9:
                    cell["capped"] += 1
                if was_outlier and not now_outlier:
                    cell["cured"] += 1
                if was_hard and not now_hard:
                    cell["cured_hard"] += 1
                if not was_outlier and now_outlier:
                    cell["killed"] += 1
                    if len(examples[floor]) < 5:
                        examples[floor].append(
                            f"{row['stable_id']} {pace} {rate_now:.2f} -> {rate_new:.2f} "
                            f"(sàn {bounds[0]:.1f}) ngân sách {budget_now:.2f} -> {budget_new:.2f} "
                            f"lặng {quiet:.2f}s  {text[:60]}"
                        )
                if not was_hard and now_hard:
                    cell["killed_hard"] += 1

    _say(f"{seen} đoạn đo được (bỏ {skipped_short} đoạn dưới {RATE_CHECK_MIN_CHARS} ký tự đọc)")
    _say(f"quãng lặng tối thiểu {args.min_gap*1000:.0f} ms, cửa sổ {FRAME_SECONDS*1000:.0f} ms")
    _say("")
    _say(f"{'ngưỡng':>8} {'chặn':>7} {'cứu':>7} {'cứu-cứng':>10} {'giết':>7} {'giết-cứng':>10}")
    for floor in floors:
        cell = tally[floor]
        _say(
            f"{floor:>7.0f}dB {cell['capped']:>7} {cell['cured']:>7} {cell['cured_hard']:>10}"
            f" {cell['killed']:>7} {cell['killed_hard']:>10}"
        )
    for floor in floors:
        if examples[floor]:
            _say("")
            _say(f"đoạn bị giết ở {floor:.0f}dB:")
            for line in examples[floor]:
                _say(f"  {line}")
    _say("")
    _say("cứu = trước bị kết tội, sau thì không. giết = ngược lại. Chỉ vá khi cứu ≫ giết.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
