"""Chuông A: reo ĐÚNG LÚC máy làm xong việc tôi giao - hoặc hỏng giữa chừng - không đợi tới giờ.

    runtime/.venv/Scripts/python.exe scripts/heartbeat_event.py     # Bash run_in_background; thoát = reo

Chủ sách, 26-09: *"heartbeat A: bạn phải làm cách nào đó để heartbeat này reo đúng lúc công việc bạn giao cho máy
tính đã được thực hiện xong"*. Ca thật đúng sáng ấy: ranh giới 17 xong 08:47, nhịp 2 tiếng thức 09:43. Xem `bells.py`.

Việc tôi giao cho máy có hai loại, và chỉ loại thứ hai cần chuông:
- lệnh nền của phiên (bộ test, phép đo): harness tự đánh thức phiên khi nó xong;
- việc RỜI (ranh giới thả bằng `run_detached.py`, để sống qua phiên): harness không biết nó xong. Chuông này lo phần ấy.

Reo khi, so với những gì chuông đã thấy:
1. `runtime/detached_runs.log` có dòng "xong (mã N)" mới - một việc rời vừa xong, kèm mã thoát. Reo ngay.
2. một ranh giới đang chạy biến mất - xong mà không kịp ghi sổ, hoặc chết. Ranh giới MỚI xuất hiện (tôi vừa thả)
   thì không reo, chỉ thêm vào danh sách canh.
3. một project mới CHẾT / ĐỨNG IM (`heartbeat_tick.stopped`).
4. máy chuyển sang chạy PIN - 24-09 sạc rút lúc 22:50 mà tới 00:07 mới biết, pin còn 5%.

Sườn, không mức: một thứ đã sai từ trước khi chuông canh thì không reo lại mãi - chuông B và nhịp tim đầy đủ lo phần
ấy. Mọi thay đổi trừ (1) phải đứng qua HAI lần dò liền nhau mới reo: ngay sau khi thả một ranh giới, phép đếm tiến
trình có thể thấy những cái bóng vài giây (tick từng báo 3, 4, 7 gốc).

Đọc tiến trình bằng `psutil`, không bằng PowerShell: dò mỗi 60 giây thì không đáng mở một PowerShell mỗi lần.
"""
from __future__ import annotations

import argparse
import os
import re
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import bells  # noqa: E402
import heartbeat_tick as tick  # noqa: E402

DETACHED_LOG = bells.RUNTIME / "detached_runs.log"
BOUNDARY = r"boundary\.sh \d"


def processes() -> list[tuple[int, int, str]] | None:
    """(pid, pid cha, dòng lệnh) như `heartbeat_tick.processes`, hoặc None khi không đọc được - đừng để một
    lần đọc hỏng trông như mọi ranh giới vừa chết."""
    try:
        import psutil
    except ImportError:
        return None
    rows = []
    for process in psutil.process_iter(["pid", "ppid", "cmdline"]):
        info = process.info
        rows.append((int(info["pid"]), int(info.get("ppid") or 0), " ".join(info.get("cmdline") or [])))
    return rows or None


def boundary_roots(procs: list[tuple[int, int, str]] | None) -> list[str] | None:
    if procs is None:
        return None
    names = set()
    for line in tick.tree_roots(procs, BOUNDARY):
        match = re.search(r"boundary\.sh \d+", line)
        if match:
            names.add(match.group(0))
    return sorted(names)


def finished_runs(log: Path = DETACHED_LOG) -> list[str]:
    try:
        text = log.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    return [line for line in text.splitlines() if "xong (mã" in line]


def snapshot() -> dict:
    done = finished_runs()
    return {
        "roots": boundary_roots(processes()),
        "done": len(done),
        "last_done": done[-5:],
        # "CHẾT lo18_x: error|..." -> "CHẾT lo18_x": đổi từ ĐỨNG IM sang CHẾT cũng là tin mới.
        "problems": sorted(line.split(":", 1)[0] for line in tick.stopped()),
        "battery": tick.power_line() is not None,
    }


class Watch:
    """Nhớ những gì đã thấy; `observe` trả về các câu cần reo (rỗng = canh tiếp)."""

    def __init__(self, first: dict) -> None:
        self.roots = set(first["roots"] or [])
        self.done = int(first["done"])
        self.problems = set(first["problems"])
        self.battery = bool(first["battery"])
        self.suspect: set[str] = set()  # thay đổi thấy ở lần dò trước, chưa đủ hai lần

    def observe(self, now: dict) -> list[str]:
        ring: list[str] = []
        seen: set[str] = set()
        if now["done"] > self.done:
            fresh = now["last_done"][-min(now["done"] - self.done, len(now["last_done"])):]
            ring.append("việc rời xong: " + " | ".join(line.strip() for line in fresh))
        if now["roots"] is not None:
            current = set(now["roots"])
            for root in sorted(self.roots - current):
                key = f"gone:{root}"
                seen.add(key)
                if key in self.suspect:
                    ring.append(f"{root} không còn chạy (xong hoặc chết)")
            for root in sorted(current - self.roots):
                key = f"new:{root}"
                seen.add(key)
                if key in self.suspect:
                    self.roots.add(root)
        for problem in sorted(set(now["problems"]) - self.problems):
            key = f"problem:{problem}"
            seen.add(key)
            if key in self.suspect:
                ring.append(f"project {problem}")
        if now["battery"] and not self.battery:
            seen.add("battery")
            if "battery" in self.suspect:
                ring.append("máy chuyển sang chạy PIN")
        elif not now["battery"]:
            self.battery = False  # cắm sạc lại: lần rút sau lại là tin mới
        self.suspect = seen
        return ring


def main(argv: list[str]) -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--every", type=float, default=60.0, help="giây giữa hai lần dò")
    args = parser.parse_args(argv)

    other = bells.claim(bells.EVENT_STATE, bells.EVENT_MARKER, {"every": args.every})
    if other:
        print(f"đã có chuông A (pid {other['pid']}) - không thả thêm. {bells.describe()}")
        return 3
    started = float(bells.read_state(bells.EVENT_STATE)["started_at"])
    try:
        first = snapshot()
        for _ in range(5):
            if first["roots"] is not None:
                break
            time.sleep(args.every)
            first = snapshot()
        watch = Watch(first)
        print(f"chuông A canh từ {time.strftime('%H:%M:%S ngày %d-%m')}: ranh giới {sorted(watch.roots) or 'không có'}"
              f" | {watch.done} việc rời đã xong | vấn đề sẵn có: {sorted(watch.problems) or 'không'}"
              f" | {'PIN' if watch.battery else 'cắm sạc'}", flush=True)
        while True:
            time.sleep(args.every)
            ring = watch.observe(snapshot())
            bells.write_state(bells.EVENT_STATE, {"pid": os.getpid(), "started_at": started,
                                                  "every": args.every, "last_poll": time.time(),
                                                  "watching": sorted(watch.roots)})
            if ring:
                break
    finally:
        bells.release(bells.EVENT_STATE)

    import heartbeat_wait  # muộn: chỉ cần khi đã reo

    print(f"=== CHUÔNG A lúc {time.strftime('%H:%M:%S ngày %d-%m')} ===")
    for line in ring:
        print(f"  {line}")
    print(heartbeat_wait.tick())
    print("=== việc tiếp: xử lý, rồi thả lại A và ĐẶT LẠI B (heartbeat_timeout.py --reset) ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
