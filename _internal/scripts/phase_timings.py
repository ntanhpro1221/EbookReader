"""How long each stage of a run actually held the machine.

Written to answer one question - is overlapping chapter N-1's verification with chapter N's
synthesis worth building - and it has to be answered from a real run, because the stages are
not close to equal and the ratio decides everything.

Two ways this measurement goes wrong, both hit while writing it:

- **Spanning resumes.** A project's log covers every attempt. Taking the first and last
  timestamp for a stage gave 8524 seconds of TTS for a two-segment chapter. The tell was
  that the number was impossible, not that anything reported an error. Stages are therefore
  read as contiguous blocks, and only the last block of each is kept.
- **Measuring a resumed run.** The final successful pass of a project that failed four times
  regenerates almost nothing, so it reported 6.8 seconds of TTS for 77 segments. A resumed
  run cannot answer how long synthesis takes. Pass --require-fresh to refuse one.

Read-only: parses the log file, touches nothing.
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime
from pathlib import Path

PHASES = (
    ("phân tích", "Đang phân tích"),
    ("TTS", "Tạo audio chapter"),
    ("Whisper", "Kiểm tra phát âm chapter"),
    ("Perceptual", "Perceptual QA chapter"),
    ("MP3", "Ghép và kiểm tra MP3 chapter"),
)
LINE = re.compile(
    r"^([\d\-]+ [\d:,]+) \| \w+ \| EVENT work_progress \{'label': '([^']+)'"
)
BLOCK_GAP_SECONDS = 300.0
MIN_FRESH_TTS_SHARE = 0.10


def _events(log_path: Path) -> list[tuple[datetime, str, str]]:
    found: list[tuple[datetime, str, str]] = []
    for line in log_path.read_text(encoding="utf-8", errors="replace").splitlines():
        match = LINE.match(line)
        if not match:
            continue
        stamp = datetime.strptime(match.group(1), "%Y-%m-%d %H:%M:%S,%f")
        label = match.group(2)
        for name, prefix in PHASES:
            if label.startswith(prefix):
                chapter = label.rsplit("chapter", 1)[-1].strip().split(":")[0].strip()
                found.append((stamp, name, chapter or "-"))
                break
    found.sort()
    return found


def _last_blocks(events: list[tuple[datetime, str, str]]) -> dict[tuple[str, str], float]:
    """Seconds in the final contiguous run of each (chapter, stage)."""
    blocks: dict[tuple[str, str], float] = {}
    current: list | None = None
    for stamp, name, chapter in events:
        key = (chapter, name)
        if current and current[0] == key and (stamp - current[2]).total_seconds() < BLOCK_GAP_SECONDS:
            current[2] = stamp
            continue
        if current:
            blocks[current[0]] = (current[2] - current[1]).total_seconds()
        current = [key, stamp, stamp]
    if current:
        blocks[current[0]] = (current[2] - current[1]).total_seconds()
    return blocks


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project_root", type=Path)
    parser.add_argument(
        "--require-fresh",
        action="store_true",
        help="Refuse a run whose synthesis time is too small to be real work",
    )
    args = parser.parse_args()

    log_path = args.project_root / "logs" / "ebook_reader.log"
    if not log_path.is_file():
        print(f"Không thấy log: {log_path}", file=sys.stderr)
        return 66
    blocks = _last_blocks(_events(log_path))
    if not blocks:
        print("Log không chứa mốc giai đoạn nào.", file=sys.stderr)
        return 65

    chapters = sorted({chapter for chapter, _name in blocks} - {"-"}, key=str)
    names = [name for name, _prefix in PHASES if name != "phân tích"]
    print(f"{'chương':>7s} " + " ".join(f"{name:>10s}" for name in names) + f"{'ngoài TTS':>12s}")
    synthesis = other = 0.0
    for chapter in chapters:
        cells, chapter_tts, chapter_rest = [], 0.0, 0.0
        for name in names:
            seconds = blocks.get((chapter, name), 0.0)
            cells.append(f"{seconds:9.1f}s")
            if name == "TTS":
                chapter_tts = seconds
            else:
                chapter_rest += seconds
        synthesis += chapter_tts
        other += chapter_rest
        print(f"{chapter:>7s} " + " ".join(cells) + f"{chapter_rest:11.1f}s")

    analysis = sum(value for (_c, name), value in blocks.items() if name == "phân tích")
    print(f"\n  phân tích {analysis:.1f}s | TTS {synthesis:.1f}s | ngoài TTS {other:.1f}s")

    # Judged as a share, not as seconds per chapter. Seconds per chapter needs a threshold
    # that depends on how long a chapter is, and the first one - one second - let a plainly
    # resumed run through at 3.45 s per chapter. In a fresh run synthesis is a large part of
    # the work; in a resume it is the rounding error left over from audio that already
    # existed.
    share_of_work = synthesis / max(1e-9, synthesis + other)
    if args.require_fresh and share_of_work < MIN_FRESH_TTS_SHARE:
        print(
            f"\nTỪ CHỐI: TTS chỉ chiếm {100 * share_of_work:.1f}% công việc "
            f"({synthesis:.1f}s trên {synthesis + other:.1f}s) - đây là một lần resume, "
            "không phải run mới. Số liệu không trả lời được câu hỏi chồng lấn.",
            file=sys.stderr,
        )
        return 65

    ceiling = min(synthesis, other)
    share = 100.0 * ceiling / max(1e-9, synthesis + other)
    print(
        f"  chồng lấn tiết kiệm tối đa = min(TTS, ngoài TTS) = {ceiling:.1f}s ({share:.0f}%)"
    )
    print("  (trần lý thuyết: giả định chồng lấn hoàn hảo và không tranh tài nguyên)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
