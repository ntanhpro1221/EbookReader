r"""Chia cả cuốn thành các lô cân nhau THEO SỐ TỪ, rồi in sẵn lệnh `create --range`.

    python scripts/plan_batches.py <thư mục nguồn>                  # cân theo giờ máy
    python scripts/plan_batches.py <thư mục nguồn> --by words --words 73000
    python scripts/plan_batches.py <thư mục nguồn> --hours 12

Vì sao không theo số chương: chương dài ngắn rất khác nhau, nên "30 chương một lô" cho ra
những lô dài ngắn tuỳ may rủi.

Vì sao mặc định KHÔNG phải số từ, dù số từ đã tốt hơn số chương nhiều: đo trên chính nguồn
này thì số từ vẫn là thước đo kém cho thời gian. Chia theo 73.000 từ một lô cho ra các lô từ
6,4 đến 9,2 giờ - lô 000..026 và lô 145..171 chênh nhau đúng 13 từ mà chênh 2,7 giờ máy.

Lý do: máy tính tiền theo **segment**, không theo từ. Chương nhiều đối thoại băm ra rất nhiều
segment ngắn; chương tự sự thì ít segment mà dài. Cùng số từ, số segment chênh tới 40%.

Nên mặc định cân theo **giờ máy** (tức theo segment). `--by words` vẫn còn đó nếu muốn.

Chương vẫn là đơn vị **không thể cắt** - mỗi chương ra một file MP3 - nên script gom trọn
chương cho tới khi thêm một chương nữa sẽ đi xa mục tiêu hơn là dừng lại.

Thời gian ước tính lấy từ **giây/segment đo thật**, không phải từ số từ: xem THROUGHPUT.md,
alpha.55 cho 7,78 giây/segment trên chương mới tinh. Số segment thì đếm bằng chính bộ chia
đoạn chứ không ước.
"""
from __future__ import annotations

import argparse
import glob
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ebook_reader.text_processing import segment_chapter_text  # noqa: E402

SECONDS_PER_SEGMENT = 7.78  # alpha.55, chương mới, mã hiện tại


def _say(line: str) -> None:
    try:
        print(line)
    except (UnicodeEncodeError, OSError, ValueError):
        sys.stdout.buffer.write(line.encode("utf-8", "replace") + b"\n")


class Chapter:
    __slots__ = ("stem", "words", "segments", "blocked")

    def __init__(self, stem: str, words: int, segments: int, blocked: str | None) -> None:
        self.stem = stem
        self.words = words
        self.segments = segments
        self.blocked = blocked


def read_chapters(source_dir: Path) -> list[Chapter]:
    chapters: list[Chapter] = []
    for index, path in enumerate(sorted(Path(p) for p in glob.glob(str(source_dir / "*.txt"))), 1):
        text = path.read_text(encoding="utf-8")
        words = len(text.split())
        try:
            segments = len(segment_chapter_text(index, text))
            blocked = None
        except RuntimeError as exc:
            segments = 0
            blocked = str(exc)
        chapters.append(Chapter(path.stem, words, segments, blocked))
    return chapters


def plan(chapters: list[Chapter], target: float, cost) -> list[list[Chapter]]:
    """Gom trọn chương, dừng khi thêm một chương nữa sẽ lệch xa mục tiêu hơn là dừng.

    ``cost`` lấy ra đại lượng đang cân - số từ hay số segment. Chương không cắt được, nên
    đây là chỗ tốt nhất có thể làm mà vẫn giữ nguyên chương.
    """
    batches: list[list[Chapter]] = []
    current: list[Chapter] = []
    total = 0.0
    for chapter in chapters:
        if current:
            stop_gap = abs(target - total)
            go_gap = abs(target - (total + cost(chapter)))
            if go_gap > stop_gap:
                batches.append(current)
                current, total = [], 0.0
        current.append(chapter)
        total += cost(chapter)
    if current:
        batches.append(current)
    return batches


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_dir", type=Path)
    parser.add_argument("--by", choices=("hours", "words"), default="hours",
                        help="Cân theo giờ máy (mặc định, sát thực tế hơn) hay theo số từ")
    parser.add_argument("--words", type=int, help="Số từ mỗi lô, chỉ dùng với --by words")
    parser.add_argument("--hours", type=float, default=8.0, help="Số giờ máy mỗi lô, mặc định 8")
    args = parser.parse_args(argv)

    source_dir = args.source_dir.resolve()
    if not source_dir.is_dir():
        _say(f"không phải thư mục: {source_dir}")
        return 2

    chapters = read_chapters(source_dir)
    if not chapters:
        _say(f"không có .txt nào trong {source_dir}")
        return 2

    blocked = [c for c in chapters if c.blocked]
    total_words = sum(c.words for c in chapters)
    total_segments = sum(c.segments for c in chapters)

    if args.by == "words":
        target = float(args.words or 73_000)
        batches = plan(chapters, target, lambda c: c.words)
        goal = f"{int(target):,} từ"
    else:
        target = args.hours * 3600 / SECONDS_PER_SEGMENT
        batches = plan(chapters, target, lambda c: c.segments)
        goal = f"{args.hours:g} giờ máy ({int(target):,} segment)"

    _say(f"{len(chapters)} chương · {total_words:,} từ · {total_segments:,} segment")
    _say(f"cân theo: {args.by} · mục tiêu mỗi lô: {goal}")
    if blocked:
        _say("")
        _say(f"CẢNH BÁO: {len(blocked)} chương bộ chia đoạn còn từ chối, "
             "chúng được tính 0 segment nên ước lượng giờ của lô chứa chúng sẽ THẤP hơn thật:")
        for c in blocked:
            _say(f"   {c.stem}: {c.blocked}")
    _say("")
    _say(f"{'lô':>4} {'chương':>17} {'số chương':>10} {'từ':>10} {'segment':>9} {'giờ máy':>9}")
    for number, batch in enumerate(batches, 1):
        words = sum(c.words for c in batch)
        segs = sum(c.segments for c in batch)
        hours = segs * SECONDS_PER_SEGMENT / 3600
        span = f"{batch[0].stem}..{batch[-1].stem}"
        _say(f"{number:>4} {span:>17} {len(batch):>10} {words:>10,} {segs:>9,} {hours:>8.1f}h")

    _say("")
    _say("Lệnh cho từng lô:")
    for batch in batches:
        _say(f'  --source-dir "{source_dir}" --range {batch[0].stem}..{batch[-1].stem}')
    _say("")
    _say("Casting mang sang giữa các lô bằng scripts/port_casting.py — nếu bỏ bước đó thì "
         "cùng một nhân vật sẽ đổi giọng giữa hai lô.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
