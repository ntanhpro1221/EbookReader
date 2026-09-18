"""Chờ nền CÓ TRẦN: thoát khi điều kiện đạt HOẶC hết trần 30 phút - nên lệnh nền nào cũng là một nhịp tim.

    runtime/.venv/Scripts/python.exe scripts/heartbeat_wait.py                         # chỉ nhịp tim
    runtime/.venv/Scripts/python.exe scripts/heartbeat_wait.py --until <x.py> [đối số]  # thức sớm khi x.py thoát 0

Thoát thì in lý do thức, rồi in nguyên một nhịp `heartbeat_tick.py`. Trợ lý đọc đúng khối ấy khi được
đánh thức, làm việc, rồi thả lại chính lệnh này.

## Vì sao (18-09, 22:3x - lần thứ ba chủ sách phải nhắc "lại quên heartbeat")

Cả ba lần hỏng cùng một kiểu: một lệnh nền KHÔNG có trần. Cron của phiên không bắn khi có lệnh nền
đang chạy (đo 18-09 01:43), nên một lệnh chờ kéo dài hàng giờ là tắt tiếng mọi nhịp tim trong hàng
giờ ấy. Lần này: sau khi máy khởi động lại lúc 21:13, trợ lý thả một vòng "chờ đủ 40 đoạn lời kể của
Đức Trí" hỏi mỗi 5 phút - trong khi lô 7 còn ~2 giờ phân tích. Từ 21:17 tới khi chủ sách nhắc lúc
22:3x, không gì đánh thức phiên; tiến trình rời `heartbeat_daemon.py` vẫn ghi đều 21:16 / 21:46 /
22:16 nhưng nó không đánh thức được ai.

Luật mới đơn giản hơn mọi lớp trước: **không có lệnh nền nào được chờ quá 30 phút**. Mọi phép chờ đi
qua script này. Nó có hai trạng thái, và cả hai đều giữ nhịp:
- đang chạy -> tự thoát trong <= 30 phút, và việc thoát đánh thức phiên;
- trợ lý quên thả lại -> không còn lệnh nền nào -> cron 13/43 bắn.

`--max` không được vượt 30 phút: đó là toàn bộ ý nghĩa của script, nên vượt thì nó từ chối chứ không
kẹp lặng lẽ.

Nó cũng soi `heartbeat_daemon.py`: `runtime/heartbeat_last.txt` im quá 35 phút nghĩa là tiến trình rời
đã chết (máy khởi động lại là đủ giết nó), và dòng cảnh báo in ra kèm đúng lệnh thả lại. Script không
tự thả daemon: tiến trình con của một lệnh nền có thể bị dọn cùng lệnh ấy, còn `Start-Process` từ
PowerShell thì đã sống qua được (21:16 -> nay).
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parent.parent
RUNTIME = ROOT / "runtime"
TICK = ROOT / "scripts" / "heartbeat_tick.py"
LAST = RUNTIME / "heartbeat_last.txt"
CAP_SECONDS = 1800
DAEMON_SILENT_SECONDS = 35 * 60
RESTART_DAEMON = (
    'Start-Process -FilePath "' + str(ROOT / "runtime" / ".venv" / "Scripts" / "pythonw.exe") + '" '
    '-ArgumentList "scripts\\heartbeat_daemon.py","--every","1800" '
    '-WorkingDirectory "' + str(ROOT) + '" -WindowStyle Hidden'
)
CONDITION_MET = "dieu kien dat"
CAP_REACHED = "het tran"


def _python() -> str:
    exe = Path(sys.executable)
    return str(exe.with_name("python.exe") if exe.name.lower() == "pythonw.exe" else exe)


def condition_holds(until: list[str]) -> tuple[bool, str]:
    """Chạy điều kiện một lần: thoát 0 là đạt. `x.py` chạy bằng chính interpreter này."""
    command = [_python(), *until] if until[0].lower().endswith(".py") else list(until)
    try:
        done = subprocess.run(command, cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8",
                              errors="replace", env={**os.environ, "PYTHONIOENCODING": "utf-8"}, timeout=300)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, f"(dieu kien loi: {exc})"
    return done.returncode == 0, (done.stdout or "").strip()


def wait(
    until: list[str] | None,
    max_seconds: int,
    every: int,
    *,
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
    check: Callable[[list[str]], tuple[bool, str]] = condition_holds,
) -> tuple[str, str]:
    """(lý do, đầu ra điều kiện). Không bao giờ quá `max_seconds`, kể cả khi `every` lớn hơn phần còn lại."""
    if max_seconds > CAP_SECONDS:
        raise ValueError(f"--max {max_seconds}s vuot tran {CAP_SECONDS}s: day la ly do script ton tai")
    deadline = clock() + max_seconds
    while True:
        if until:
            ok, output = check(until)
            if ok:
                return CONDITION_MET, output
        remaining = deadline - clock()
        if remaining <= 0:
            return CAP_REACHED, ""
        sleep(min(float(every), remaining))


def daemon_warning(now: float | None = None) -> str:
    """Rỗng nếu tiến trình rời vừa ghi nhịp; không thì một dòng cảnh báo kèm lệnh thả lại."""
    now = time.time() if now is None else now
    try:
        age = now - LAST.stat().st_mtime
    except OSError:
        return f"CANH BAO: khong thay {LAST.name} - heartbeat_daemon chua tung chay. Tha: {RESTART_DAEMON}"
    if age > DAEMON_SILENT_SECONDS:
        return (f"CANH BAO: heartbeat_daemon im {age / 60:.0f} phut (may khoi dong lai?). "
                f"Tha lai bang PowerShell: {RESTART_DAEMON}")
    return ""


def tick() -> str:
    try:
        done = subprocess.run([_python(), str(TICK)], cwd=str(ROOT), capture_output=True, text=True,
                              encoding="utf-8", errors="replace",
                              env={**os.environ, "PYTHONIOENCODING": "utf-8"}, timeout=600)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return f"(nhip tim loi: {exc})"
    return (done.stdout or "").strip() or f"(nhip tim khong in gi; ma {done.returncode})"


def main(argv: list[str]) -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--max", type=int, default=CAP_SECONDS, help=f"giay, toi da {CAP_SECONDS}")
    parser.add_argument("--every", type=int, default=120, help="giay giua hai lan hoi dieu kien")
    parser.add_argument("--until", nargs=argparse.REMAINDER, default=None,
                        help="lenh dieu kien (x.py chay bang interpreter nay); thoat 0 = thuc som")
    args = parser.parse_args(argv)
    started = time.strftime("%H:%M:%S")
    try:
        reason, output = wait(args.until or None, args.max, max(1, args.every))
    except ValueError as exc:
        print(f"TU CHOI: {exc}")
        return 2
    print(f"=== THUC luc {time.strftime('%H:%M:%S')} (tha luc {started}): {reason} ===")
    if output:
        print(output)
    warning = daemon_warning()
    if warning:
        print(warning)
    print(tick())
    print("=== viec tiep: lam viec, roi THA LAI heartbeat_wait.py (quen thi cron 13/43 se ban) ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
