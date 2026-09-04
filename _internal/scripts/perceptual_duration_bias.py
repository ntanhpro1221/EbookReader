"""Does the perceptual gate ask for a human ear more often just because a clip is short?

`c00003_s0000014` - "Tất cả đều đã ra đi.", 1.5 seconds - blocked its chapter in both
alpha.32 and alpha.43, with ASR hearing it perfectly. Several other blocked segments are
also short. That is enough of a pattern to ask whether the gate has a length bias.

It does, and the shape of it decides the remedy. If short clips simply score worse, the
gate is right and short synthesis is bad. If they score the same but scatter more, then a
fixed absolute threshold is harvesting the tail of a noisier estimator, and "worst" quietly
means something different at each length.

    python scripts/perceptual_duration_bias.py <project_root> [review_delta]

Read-only: opens the project database read-only and writes nothing.
"""
from __future__ import annotations

import json
import sqlite3
import statistics
import sys
from pathlib import Path

DEFAULT_REVIEW_DELTA = -0.8
BUCKETS = (("<2s", 0.0, 2.0), ("2-3s", 2.0, 3.0), ("3-5s", 3.0, 5.0),
           ("5-8s", 5.0, 8.0), (">=8s", 8.0, float("inf")))
LONG_CLIP_SECONDS = 5.0


def _bucket(seconds: float) -> str:
    for name, low, high in BUCKETS:
        if low <= seconds < high:
            return name
    return BUCKETS[-1][0]


def main(project_root: str, review_delta: float) -> int:
    database = Path(project_root) / "project.sqlite3"
    if not database.is_file():
        print(f"không tìm thấy project: {database}")
        return 2
    connection = sqlite3.connect(f"file:{database}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    points: list[tuple[float, float]] = []
    candidates = 0
    for row in connection.execute(
        "SELECT metrics_json FROM quality_checks WHERE stage LIKE '%percept%'"
    ):
        metrics = json.loads(str(row["metrics_json"] or "{}"))
        seconds, delta = metrics.get("duration_seconds"), metrics.get("baseline_delta")
        if not seconds or delta is None:
            continue
        # Repair candidates are re-takes of segments already judged suspect, so they sit
        # lower than the population and would drag the threshold down with them: on
        # alpha.32 their median at under two seconds is -0.815 against -0.434 for primary
        # takes. They are only 4.7% of the sample, so the effect is small - the sub-2s
        # threshold moves from -1.079 to -1.063 - but a gate calibrated partly on its own
        # rejects is the wrong shape of measurement whatever the size of the error.
        if metrics.get("candidate_repair_requirement"):
            candidates += 1
            continue
        points.append((float(seconds), float(delta)))
    connection.close()
    if len(points) < 50:
        print("chưa đủ điểm perceptual để nói gì")
        return 1

    grouped: dict[str, list[float]] = {}
    for seconds, delta in points:
        grouped.setdefault(_bucket(seconds), []).append(delta)

    print(f"{len(points)} phép chấm perceptual trên bản thu chính "
          f"({candidates} phép chấm candidate sửa đã loại), ngưỡng review_delta = {review_delta}")
    print()
    print(f"{'độ dài':>7}  {'n':>5}  {'delta trung vị':>14}  {'độ lệch chuẩn':>13}  {'gắn cờ':>7}")
    for name, _low, _high in BUCKETS:
        values = grouped.get(name, [])
        if len(values) < 10:
            continue
        flagged = sum(1 for value in values if value < review_delta)
        print(f"{name:>7}  {len(values):5d}  {statistics.median(values):14.3f}"
              f"  {statistics.pstdev(values):13.3f}  {flagged / len(values):6.1%}")

    long_clips = [delta for seconds, delta in points if seconds >= LONG_CLIP_SECONDS]
    median, spread = statistics.median(long_clips), statistics.pstdev(long_clips)
    if not spread:
        print("\nđoạn dài không có độ tán - không suy ra được ngưỡng theo sigma")
        return 1
    sigmas = (median - review_delta) / spread

    print()
    print(f"Trên đoạn >= {LONG_CLIP_SECONDS:.0f}s, {review_delta} nằm ở trung vị trừ "
          f"{sigmas:.2f} sigma và gắn cờ {sum(1 for v in long_clips if v < review_delta) / len(long_clips):.1%}.")
    print("Áp cùng số sigma ấy cho mọi độ dài, tức cùng một mức khắt khe thay vì cùng một số:")
    print()
    print(f"{'độ dài':>7}  {'ngưỡng':>9}  {'gắn cờ nay':>11}  {'gắn cờ mới':>11}")
    before = after = 0
    for name, _low, _high in BUCKETS:
        values = grouped.get(name, [])
        if len(values) < 10:
            continue
        threshold = statistics.median(values) - sigmas * statistics.pstdev(values)
        now = sum(1 for value in values if value < review_delta)
        then = sum(1 for value in values if value < threshold)
        before += now
        after += then
        print(f"{name:>7}  {threshold:9.3f}  {now:4d} ({now / len(values):4.1%})"
              f"  {then:4d} ({then / len(values):4.1%})")
    print()
    print(f"tổng gắn cờ: {before} -> {after}")
    print(
        "\nLưu ý cách đọc: đây **không phải** nới lỏng. Nó siết đoạn dài lại và nới đoạn "
        "ngắn ra, để 'tệ nhất' có cùng một nghĩa ở mọi độ dài.\n"
        "\nChưa phân giải được: phần tán thêm ở đoạn ngắn là *nhiễu của thước đo* hay là "
        "chất lượng thật sự dao động hơn. Phép thử tự nhiên - so điểm giữa các bản thu khác "
        "seed của cùng một câu - trả về biên độ 0,000 ở mọi nhóm, vì các hàng lặp lại chấm "
        "đúng một file âm thanh chứ không phải các bản thu khác nhau. Kết quả rỗng, đã ghi "
        "lại để không ai thử lại đúng cách ấy."
    )
    return 0


if __name__ == "__main__":
    if not 1 <= len(sys.argv) - 1 <= 2:
        print(__doc__)
        raise SystemExit(2)
    raise SystemExit(
        main(sys.argv[1], float(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_REVIEW_DELTA)
    )
