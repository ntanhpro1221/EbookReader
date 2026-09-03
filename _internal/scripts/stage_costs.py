"""Where a run's time went, per quality stage, read from the durable ledger.

Complements scripts/phase_timings.py rather than replacing it. That one parses the log and
refuses a resumed project, because a resumed run regenerates almost nothing and cannot say
how long synthesis takes. This one reads quality_checks, which records one row per piece of
evidence the run actually produced - so it still answers for a project whose *analysis* was
resumed as long as its audio was made in one pass.

It is the measurement that found the project had the wrong cost centre: ASR is 3,870
seconds on alpha.25 against TTS's 2,055, and perceptual scoring 2,538 more that ran after
ASR, on the CPU, while the GPU had nothing left to do.

    python scripts/stage_costs.py <project_root> [<other_project_root>]

Pass a second project to compare them. That is how the perceptual/ASR overlap is verified:
with scoring prefetched beside ASR, the perceptual verdicts left in the sequential timeline
are cheap, so the stage's cost should collapse while ASR's stays put.
"""
from __future__ import annotations

import sqlite3
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

# A gap longer than this is the run being paused, throttled or restarted between phases,
# not one stage taking that long. Attributing it to a stage is how a two-segment chapter
# ends up reporting hours of work.
MAX_ATTRIBUTABLE_GAP_SECONDS = 600.0

ASR_STAGE_HINTS = ("audio_quality", "asr")
PERCEPTUAL_STAGE_HINT = "perceptual"


def _moment(value: str) -> float:
    """created_at is a unix float, whatever the column name suggests."""
    try:
        return float(value)
    except ValueError:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()


def _is_asr(stage: str) -> bool:
    return any(hint in stage.casefold() for hint in ASR_STAGE_HINTS)


def _is_perceptual(stage: str) -> bool:
    return PERCEPTUAL_STAGE_HINT in stage.casefold()


def read_costs(database: Path) -> tuple[dict[str, float], dict[str, int], dict[int, dict[str, float]]]:
    """Seconds and row counts per stage, and the same split by chapter.

    Time is attributed the way a sequential pipeline spends it: each gap between two
    consecutive checks belongs to the stage of the later one. Per-segment checks leave
    chapter_id NULL and name a segment instead, so the chapter comes from the segment.
    """
    connection = sqlite3.connect(f"file:{database}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    rows = connection.execute(
        "SELECT COALESCE(q.chapter_id, s.chapter_id) AS chapter_id, q.stage, q.created_at "
        "FROM quality_checks q LEFT JOIN segments s ON s.id = q.segment_id "
        "WHERE COALESCE(q.chapter_id, s.chapter_id) IS NOT NULL "
        "ORDER BY COALESCE(q.chapter_id, s.chapter_id), q.created_at"
    ).fetchall()
    connection.close()

    seconds: dict[str, float] = defaultdict(float)
    counts: dict[str, int] = defaultdict(int)
    per_chapter: dict[int, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    previous_chapter: object = None
    previous_time: float | None = None
    for row in rows:
        stage = str(row["stage"])
        counts[stage] += 1
        now = _moment(str(row["created_at"]))
        if row["chapter_id"] == previous_chapter and previous_time is not None:
            gap = now - previous_time
            if 0.0 <= gap < MAX_ATTRIBUTABLE_GAP_SECONDS:
                seconds[stage] += gap
                per_chapter[int(row["chapter_id"])][stage] += gap
        previous_chapter = row["chapter_id"]
        previous_time = now
    return dict(seconds), dict(counts), {k: dict(v) for k, v in per_chapter.items()}


def _totals(seconds: dict[str, float]) -> tuple[float, float, float]:
    asr = sum(value for stage, value in seconds.items() if _is_asr(stage))
    perceptual = sum(value for stage, value in seconds.items() if _is_perceptual(stage))
    return sum(seconds.values()), asr, perceptual


def report(label: str, database: Path) -> tuple[float, float, float]:
    seconds, counts, per_chapter = read_costs(database)
    if not seconds:
        print(f"{label}: chưa có check nào để đo")
        return 0.0, 0.0, 0.0
    total, asr, perceptual = _totals(seconds)
    print(f"=== {label} ===")
    print(f"{'giai đoạn':<38}{'lượt':>7}{'giây':>10}{'%':>7}")
    for stage, value in sorted(seconds.items(), key=lambda item: -item[1]):
        print(f"{stage:<38}{counts[stage]:>7}{value:>10.1f}{value / total:>6.0%}")
    print(f"{'TỔNG':<38}{sum(counts.values()):>7}{total:>10.1f}")
    print()
    print(f"  ASR (GPU)      {asr:9.1f}s")
    print(f"  cảm thụ (CPU)  {perceptual:9.1f}s")
    print()
    print("  theo chương:")
    for chapter_id in sorted(per_chapter):
        stages = per_chapter[chapter_id]
        chapter_asr = sum(v for k, v in stages.items() if _is_asr(k))
        chapter_perceptual = sum(v for k, v in stages.items() if _is_perceptual(k))
        print(
            f"    ch{chapter_id:<3} ASR {chapter_asr:8.1f}s | cảm thụ {chapter_perceptual:8.1f}s"
        )
    print()
    return total, asr, perceptual


def main(arguments: list[str]) -> int:
    projects = []
    for value in arguments:
        root = Path(value)
        database = root if root.suffix == ".sqlite3" else root / "project.sqlite3"
        if not database.is_file():
            print(f"không tìm thấy project: {database}")
            return 2
        projects.append((root.name or str(root), database))

    measured = [(label, *report(label, database)) for label, database in projects]
    if len(measured) < 2:
        return 0

    (first_label, _first_total, first_asr, first_perceptual) = measured[0]
    (second_label, _second_total, second_asr, second_perceptual) = measured[1]
    print("=== so sánh ===")
    print(f"  ASR      {first_label} {first_asr:9.1f}s -> {second_label} {second_asr:9.1f}s")
    print(
        f"  cảm thụ  {first_label} {first_perceptual:9.1f}s -> "
        f"{second_label} {second_perceptual:9.1f}s"
    )
    if first_perceptual > 0:
        saved = first_perceptual - second_perceptual
        print(
            f"  cảm thụ còn lại trên dòng thời gian tuần tự: "
            f"{second_perceptual / first_perceptual:.0%} "
            f"({saved:+.1f}s)"
        )
        print()
        print(
            "  Chấm điểm chạy cạnh ASR thì phần cảm thụ còn nằm trên dòng thời gian tuần "
            "tự chỉ là các verdict, vốn rất rẻ khi điểm đã có sẵn. ASR đứng yên là dấu "
            "hiệu chồng lấn không lấn sang thời gian của nó."
        )
    return 0


if __name__ == "__main__":
    if not 1 <= len(sys.argv) - 1 <= 2:
        print(__doc__)
        raise SystemExit(2)
    raise SystemExit(main(sys.argv[1:]))
