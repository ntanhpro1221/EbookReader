"""Chuông B: reo khi đã `--hours` giờ không ai đặt lại nó - tức chuông A im, hoặc thông báo của A đã lạc.

    runtime/.venv/Scripts/python.exe scripts/heartbeat_timeout.py --hours 2    # Bash run_in_background
    runtime/.venv/Scripts/python.exe scripts/heartbeat_timeout.py --reset      # đếm lại từ đầu

Chủ sách, 26-09: *"heartbeat B: luôn reo định kỳ mỗi x giờ để tránh trường hợp heartbeat A bằng cách nào đó không
được kích hoạt ... mỗi khi heartbeat A được reo lên thì reset luôn heartbeat B lại từ đầu"*. Xem `bells.py`.

**Cố ý ngu.** Không đọc sách, không đếm tiến trình - chỉ đếm giờ. Nó tồn tại để bắt đúng những lúc A hỏng (A treo
giữa một lần dò, thông báo của A lạc), nên nó không được đi chung đường nào với A ngoài cái file hẹn giờ.

Đặt lại không giết B: `--reset` chạm `runtime/heartbeat_timeout.reset`, và B đang chạy tự dời hẹn theo file ấy ở lần
dò kế. Nhờ vậy đặt lại không sinh một lần thức vô ích (giết một lệnh nền cũng đánh thức phiên).
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path
from typing import Callable

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import bells  # noqa: E402


def wait_out(
    started: float,
    hours: float,
    every: float,
    *,
    clock: Callable[[], float] = time.time,
    sleep: Callable[[float], None] = time.sleep,
    reset: Callable[[], float | None] = bells.reset_mtime,
) -> float:
    """Chờ tới hạn, đọc lại file đặt lại mỗi lần dò. Trả về cái hạn đã tới."""
    while True:
        deadline = bells.timeout_deadline(started, hours, reset())
        remaining = deadline - clock()
        if remaining <= 0:
            return deadline
        sleep(min(every, remaining))


def reset() -> None:
    bells.TIMEOUT_RESET.parent.mkdir(parents=True, exist_ok=True)
    bells.TIMEOUT_RESET.touch()
    os.utime(bells.TIMEOUT_RESET, None)


def main(argv: list[str]) -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--hours", type=float, default=2.0)
    parser.add_argument("--every", type=float, default=60.0, help="giây giữa hai lần đọc file đặt lại")
    parser.add_argument("--reset", action="store_true", help="đặt lại B đang chạy về 0 rồi thoát")
    args = parser.parse_args(argv)
    if args.reset:
        reset()
        print(f"chuông B đếm lại từ {time.strftime('%H:%M:%S')}: {bells.describe()}")
        return 0

    other = bells.claim(bells.TIMEOUT_STATE, bells.TIMEOUT_MARKER, {"hours": args.hours})
    if other:
        print(f"đã có chuông B (pid {other['pid']}) - không thả thêm. {bells.describe()}")
        return 3
    started = float(bells.read_state(bells.TIMEOUT_STATE)["started_at"])
    try:
        wait_out(started, args.hours, args.every)
    finally:
        bells.release(bells.TIMEOUT_STATE)

    import heartbeat_wait  # muộn: chỉ cần khi đã reo

    print(f"=== CHUÔNG B lúc {time.strftime('%H:%M:%S ngày %d-%m')}: {args.hours:g} giờ không ai đặt lại "
          "- chuông A im hoặc thông báo của nó đã lạc ===")
    warning = heartbeat_wait.daemon_warning()
    if warning:
        print(warning)
    print(heartbeat_wait.tick())
    print("=== việc tiếp: kiểm chuông A còn canh không (dòng 'chuông:'), làm việc, rồi thả lại B ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
