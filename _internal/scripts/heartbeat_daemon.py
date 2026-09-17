"""Nhịp tim chạy rời: cứ N phút gọi `heartbeat_tick.py` và ghi vào `runtime/heartbeat_log.txt`.

    runtime/.venv/Scripts/pythonw.exe scripts/heartbeat_daemon.py [--every 1800]
    (dừng: tạo file runtime/heartbeat_daemon.stop, hoặc taskkill theo pid trong runtime/heartbeat_daemon.pid)

## Vì sao có (18-09 01:5x)

Nhịp tim trước là một lệnh nền của phiên làm việc: nó đập MỘT nhịp rồi tắt, nên phụ thuộc vào việc
trợ lý nhớ thả lại — và đã quên hai lần, cả hai lần chủ sách là người phát hiện. Cron của phiên thì
**không bắn khi có lệnh nền đang chạy**: đo được lúc 01:43 ngày 18-09, cron đặt ở phút 13/43 không
bắn vì một lệnh nền đang chờ. Hai cơ chế ấy cùng hỏng theo một kiểu: nhịp nằm trong phiên.

Tiến trình rời này nằm ngoài phiên. Nó không đánh thức phiên được — cron làm việc ấy khi phiên rảnh —
nhưng nó bảo đảm **bản ghi** không bao giờ đứt: mỗi nhịp có một khối trong log kèm giờ, nên lượt thức
kế tiếp đọc được cả quãng vừa qua chứ không mất trắng. `pythonw.exe` để không có cửa sổ console nháy
(xem memory `windows-console-flags`).
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RUNTIME = ROOT / "runtime"
LOG = RUNTIME / "heartbeat_log.txt"
PID = RUNTIME / "heartbeat_daemon.pid"
STOP = RUNTIME / "heartbeat_daemon.stop"
TICK = ROOT / "scripts" / "heartbeat_tick.py"
KEEP_BYTES = 400_000


def alive(pid: int) -> bool:
    out = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH"], capture_output=True, text=True,
                         encoding="utf-8", errors="replace").stdout
    return str(pid) in out


def one_tick(python: Path) -> str:
    started = time.strftime("%Y-%m-%d %H:%M:%S")
    result = subprocess.run([str(python), str(TICK)], cwd=str(ROOT), capture_output=True, text=True,
                            encoding="utf-8", errors="replace",
                            env={**os.environ, "PYTHONIOENCODING": "utf-8"}, timeout=600)
    body = (result.stdout or "").strip() or f"(nhịp tim không in gì; mã {result.returncode})"
    if result.returncode != 0:
        body += f"\n(mã thoát {result.returncode}) {(result.stderr or '').strip()[-400:]}"
    return f"\n########## {started} ##########\n{body}\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--every", type=int, default=1800, help="giây giữa hai nhịp")
    args = parser.parse_args()
    RUNTIME.mkdir(parents=True, exist_ok=True)
    # Một tiến trình thôi: nếu pid cũ còn sống thì thoát, để lệnh khởi động thành ra tự nó idempotent.
    if PID.exists():
        try:
            old = int(PID.read_text(encoding="utf-8").strip())
        except ValueError:
            old = 0
        if old and old != os.getpid() and alive(old):
            return 0
    PID.write_text(str(os.getpid()), encoding="utf-8")
    STOP.unlink(missing_ok=True)
    python = Path(sys.executable)
    python = python.with_name("python.exe") if python.name.lower() == "pythonw.exe" else python
    while not STOP.exists():
        try:
            block = one_tick(python)
        except subprocess.TimeoutExpired:
            block = f"\n########## {time.strftime('%Y-%m-%d %H:%M:%S')} ##########\n(nhịp tim treo > 600s)\n"
        if LOG.exists() and LOG.stat().st_size > KEEP_BYTES:
            LOG.write_text(LOG.read_text(encoding="utf-8", errors="replace")[-KEEP_BYTES // 2:], encoding="utf-8")
        with LOG.open("a", encoding="utf-8") as handle:
            handle.write(block)
        for _ in range(max(args.every, 60)):
            if STOP.exists():
                break
            time.sleep(1)
    PID.unlink(missing_ok=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
