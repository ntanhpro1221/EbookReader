"""Chương nào của một lô cần chạy lại, và lệnh `create` để chạy lại đúng chúng.

    python scripts/plan_repair_batch.py <project cua lo vua chay>

Sinh ra từ lô 1 (docs/PRODUCTION_PLAN.md, mục *"Khi một lô có chương hỏng"*): chạy lại cả lô
tốn ~13 giờ, còn chạy lại riêng những chương hỏng tốn ~4. Chương đã `completed` là sản phẩm
hoàn chỉnh; việc `resume` bị từ chối sau khi vá chỉ chặn **project ấy**, không chặn việc tạo
một project mới bao đúng dải chương hỏng.

`--range` của CLI nhận một dải liên tục, nên script in ra **từng cụm liền nhau** — chương hỏng
thường rải rác, và ba cụm nhỏ chạy nhanh hơn một dải to bao cả những chương đã tốt.

Chỉ đọc; không tạo project, không chạy gì.
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path


def _say(line: str) -> None:
    try:
        print(line)
    except (UnicodeEncodeError, OSError, ValueError):
        sys.stdout.buffer.write(line.encode("utf-8", "replace") + b"\n")


def _runs(numbers: list[int]) -> list[tuple[int, int]]:
    """[0, 3, 7, 8, 9] -> [(0,0), (3,3), (7,9)]"""
    spans: list[tuple[int, int]] = []
    for number in sorted(numbers):
        if spans and number == spans[-1][1] + 1:
            spans[-1] = (spans[-1][0], number)
        else:
            spans.append((number, number))
    return spans


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("project", type=Path)
    parser.add_argument("--tag", default="<tag mới>", help="Tên phiên bản cho lô vá")
    args = parser.parse_args(argv)

    database = args.project / "project.sqlite3"
    if not database.is_file():
        _say(f"Không thấy {database}")
        return 2
    conn = sqlite3.connect(f"file:{database}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row

    rows = list(conn.execute("SELECT title, status, last_error FROM chapters ORDER BY title"))
    done = [r for r in rows if str(r["status"]) == "completed"]
    # Tách "hỏng" khỏi "chưa chạy". Chạy giữa chừng thì mọi chương chưa tới lượt đều đọc thành
    # cần vá, và một danh sách như thế đọc lúc năm giờ sáng là chạy lại thừa cả chục chương.
    unfinished = [
        r for r in rows
        if str(r["status"]) in {"pending", "analyzing", "synthesizing", "verifying"}
    ]
    broken = [
        r for r in rows
        if str(r["status"]) != "completed" and r not in unfinished
    ]

    _say(f"{len(done)}/{len(rows)} chương đã xong.")
    if unfinished:
        _say(
            f"  LƯU Ý: {len(unfinished)} chương CHƯA CHẠY XONG "
            f"({', '.join(str(r['title']) for r in unfinished[:8])}...) - đợi lô xong đã."
        )
    if not broken:
        _say("Không có chương nào hỏng.")
        return 0
    _say(f"{len(broken)} chương hỏng, cần chạy lại.")

    _say("")
    _say("Chương hỏng, kèm lý do:")
    for row in broken:
        _say(f"  {row['title']}  {str(row['last_error'] or '')[:96]}")

    numbers: list[int] = []
    for row in broken:
        try:
            numbers.append(int(str(row["title"])))
        except ValueError:
            _say(f"  (bỏ qua {row['title']}: tiêu đề không phải số)")
    spans = _runs(numbers)

    _say("")
    _say(f"{len(spans)} cụm liền nhau. Lệnh cho từng cụm:")
    width = max((len(str(row["title"])) for row in broken), default=3)
    for first, last in spans:
        _say(
            f'  --range "{first:0{width}d}..{last:0{width}d}" --width {width} '
            f'--title "{args.tag}"'
        )

    _say("")
    _say("Trước khi chạy: `python scripts/before_a_batch.py`, và gieo từ chính project này")
    _say("(port_pronunciations → port_casting → seed_listener_acceptances) để giọng không đổi.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
