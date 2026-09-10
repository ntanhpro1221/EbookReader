"""Ai là cửa sổ tiền cảnh khi bộ điều tiết nhường? Ghi TÊN, vì bộ điều tiết chỉ ghi phần trăm.

    python scripts/foreground_watch.py [--seconds 5] [--threshold 20] [--log runtime/foreground_watch.log]

`resource_manager.py` (file khoá) đo CPU của tiến trình sở hữu **cửa sổ tiền cảnh**
(`GetForegroundWindow`) — không phải "mọi tiến trình ngoài đường ống". Đo 2026-09-10: ba lượt bộ
test đầy đủ chạy trong console nền không làm nó đổi chế độ, còn "foreground CPU 81%" lúc 17:48
(65,6 phút `yield_heavy` cả lô 3, 17 segment) thì không ghi tên ai. Script này đứng ngoài, đo
cùng một cách, và ghi tên — để biết cái máy đang nhường cho ai: chủ sách, trình duyệt, hay chính
ứng dụng đang hiển thị phiên làm việc này.

Chạy nền, dừng bằng cách giết. Ghi một dòng khi tiến trình tiền cảnh đổi và khi CPU của nó vượt
ngưỡng; mỗi 10 phút ghi tổng số giây trên ngưỡng nhường (35%) theo tên.
"""
from __future__ import annotations

import argparse
import ctypes
import os
import sys
import time
from collections import Counter
from pathlib import Path

import psutil

ROOT = Path(__file__).resolve().parents[1]
YIELD_TRIGGER = 35.0  # foreground_cpu_trigger trong settings - ngưỡng bộ điều tiết chuyển yield_heavy


def foreground_pid() -> int | None:
    if os.name != "nt":
        return None
    try:
        user32 = ctypes.windll.user32
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return None
        pid = ctypes.c_ulong()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        return int(pid.value) or None
    except Exception:  # noqa: BLE001
        return None


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--seconds", type=float, default=5.0)
    parser.add_argument("--threshold", type=float, default=20.0, help="ghi dòng khi CPU tiền cảnh ≥ ngần này")
    parser.add_argument("--log", default=str(ROOT / "runtime" / "foreground_watch.log"))
    args = parser.parse_args(argv)

    log_path = Path(args.log)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    samples: dict[int, psutil.Process] = {}
    above_trigger: Counter[str] = Counter()
    last_pid: int | None = None
    last_summary = time.time()

    def say(line: str) -> None:
        stamp = time.strftime("%m-%d %H:%M:%S")
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write(f"{stamp} {line}\n")

    say(f"bắt đầu, mỗi {args.seconds:g}s, ghi khi ≥ {args.threshold:g}%, nhường ở ≥ {YIELD_TRIGGER:g}%")
    while True:
        pid = foreground_pid()
        name = "?"
        cpu: float | None = None
        if pid:
            try:
                proc = samples.get(pid)
                if proc is None or not proc.is_running():
                    proc = psutil.Process(pid)
                    proc.cpu_percent(None)
                    samples[pid] = proc
                    cpu = 0.0
                else:
                    cpu = proc.cpu_percent(None)
                name = proc.name()
            except (psutil.Error, OSError):
                samples.pop(pid, None)
                cpu = None
        if pid != last_pid:
            say(f"tiền cảnh đổi -> {name} (pid {pid})")
            last_pid = pid
        if cpu is not None and cpu >= args.threshold:
            flag = "  NHƯỜNG" if cpu >= YIELD_TRIGGER else ""
            say(f"{name:24s} pid {pid:<6} cpu {cpu:5.0f}%{flag}")
        if cpu is not None and cpu >= YIELD_TRIGGER:
            above_trigger[name] += args.seconds
        if time.time() - last_summary >= 600:
            last_summary = time.time()
            if above_trigger:
                top = ", ".join(f"{n} {int(s)}s" for n, s in above_trigger.most_common(5))
                say(f"tổng giây trên ngưỡng nhường theo tên: {top}")
            else:
                say("10 phút: không ai trên ngưỡng nhường")
        time.sleep(args.seconds)


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv[1:]))
    except KeyboardInterrupt:
        raise SystemExit(0)
