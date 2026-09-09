"""Lô này mất bao nhiêu thời gian vì nhường máy cho người đang dùng nó.

    python scripts/throttle_report.py <project>

Sinh ra từ một phép đo trên lô vá (docs/THE_MACHINE_IS_SHARED.md): chương 003 sinh 121 segment
trong 25,9 phút, trong khi ở tốc độ `maximum` nó chỉ cần 8,9 — **chậm gấp 2,91 lần**, vì 60%
thời gian nằm trong `yield_heavy` và trong 60% ấy đường ống làm được đúng hai segment.

Nhường máy cho người đang ngồi trước nó là **đúng**; script này không phán xét việc nhường. Nó
tồn tại để một lô chậm không bị đọc nhầm thành một lô treo lúc ba giờ sáng, và để con số giờ
trong PRODUCTION_PLAN.md được hiểu đúng là ước lượng cho máy rảnh.

Gán segment vào chế độ bằng `updated_at` và mốc đổi chế độ gần nhất trước đó. Gần đúng ở ranh
giới, và số mẫu trong các chế độ hiếm thì nhỏ — nên script in **cả số segment lẫn số phút**,
để đọc được "2 segment trong 15 phút" thay vì chỉ một tỉ lệ dựng trên hai mẫu.

Chỉ đọc; chạy được khi project đang chạy.
"""
from __future__ import annotations

import argparse
import bisect
import collections
import sqlite3
import sys
from pathlib import Path

MODE_ORDER = ("maximum", "yield_light", "yield_heavy", "pause_new_work")


def _say(line: str) -> None:
    try:
        print(line)
    except (UnicodeEncodeError, OSError, ValueError):
        sys.stdout.buffer.write(line.encode("utf-8", "replace") + b"\n")


def _mode_of(message: str) -> str:
    """'Resource mode: yield_heavy — foreground CPU 65%' -> 'yield_heavy'"""
    tail = str(message).split(":", 1)[-1]
    return tail.split("—")[0].strip()


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("project", type=Path)
    args = parser.parse_args(argv)

    database = args.project / "project.sqlite3"
    if not database.is_file():
        _say(f"Không thấy {database}")
        return 2
    conn = sqlite3.connect(f"file:{database}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row

    changes = [
        (float(row["timestamp"]), _mode_of(row["message"]))
        for row in conn.execute(
            "SELECT timestamp, message FROM runtime_events "
            "WHERE message LIKE 'Resource mode%' ORDER BY id"
        )
    ]
    if not changes:
        _say("Chưa có lần đổi chế độ nào — lô chưa chạy đủ lâu, hoặc máy đang rảnh hoàn toàn.")
        return 0
    end = float(conn.execute("SELECT max(timestamp) FROM runtime_events").fetchone()[0])
    done = [
        float(row[0])
        for row in conn.execute(
            "SELECT updated_at FROM segments WHERE wav_sha256 IS NOT NULL ORDER BY updated_at"
        )
    ]

    starts = [when for when, _mode in changes]
    seconds: collections.Counter[str] = collections.Counter()
    made: collections.Counter[str] = collections.Counter()
    for index, (when, mode) in enumerate(changes):
        nxt = changes[index + 1][0] if index + 1 < len(changes) else end
        seconds[mode] += max(0.0, nxt - when)
    for when in done:
        index = bisect.bisect_right(starts, when) - 1
        if index >= 0:
            made[changes[index][1]] += 1

    _say("chế độ         phút   segment   segment/phút")
    total_segments = total_seconds = 0.0
    for mode in MODE_ORDER + tuple(m for m in seconds if m not in MODE_ORDER):
        if seconds[mode] <= 0:
            continue
        minutes = seconds[mode] / 60.0
        total_segments += made[mode]
        total_seconds += seconds[mode]
        _say(f"  {mode:13s} {minutes:5.1f}  {made[mode]:7d}   {made[mode] / minutes:9.2f}")
    if total_seconds <= 0:
        return 0
    _say(f"  {'TỔNG':13s} {total_seconds / 60:5.1f}  {int(total_segments):7d}"
         f"   {total_segments / (total_seconds / 60):9.2f}")

    best = made["maximum"] / (seconds["maximum"] / 60.0) if seconds["maximum"] else 0.0
    if best <= 0 or total_segments <= 0:
        _say("")
        _say("Chưa có đủ thời gian ở chế độ maximum để so — chưa kết luận được gì.")
        return 0
    ideal = total_segments / best
    _say("")
    _say(
        f"Ở tốc độ maximum ({best:.2f}/phút) thì {int(total_segments)} segment tốn"
        f" {ideal:.1f} phút; thực tế {total_seconds / 60:.1f} phút"
        f"  ->  chậm gấp {(total_seconds / 60) / ideal:.2f} lần."
    )
    _say("")
    _say("Lý do được ghi lại, gần nhất trước:")
    for row in conn.execute(
        "SELECT message FROM runtime_events WHERE message LIKE 'Resource mode%' "
        "ORDER BY id DESC LIMIT 6"
    ):
        _say(f"  {str(row['message'])[15:110]}")
    _say("")
    _say("Chậm KHÁC treo: nhịp tim worker_leases vẫn dưới 180s và lý do nhường có ghi ở trên.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
