"""Chạy một lệnh dài (vd `bash scripts/boundary.sh 17`) TÁCH khỏi phiên Claude, không mở cửa sổ nào.

    powershell: Start-Process -FilePath runtime\\.venv\\Scripts\\pythonw.exe `
        -ArgumentList 'scripts\\run_detached.py','bash','scripts/boundary.sh','17' `
        -WorkingDirectory <_internal> -WindowStyle Hidden

## Vì sao (24-09 20:4x)

Ranh giới thả bằng lệnh nền của phiên (`Bash run_in_background`) là con của phiên, nên chết khi phiên chết:
phiên đóng đêm 23-09 (lệnh nền thoát mã 4), `boundary.sh 16` chết theo, lô 16 vẫn tự xong lúc 24-09 15:15
nhưng không còn ai ghép sách và thả lô 17 - **mất 5,5 giờ sản xuất** cho tới khi phiên mới mở. Trong khi đó
daemon nhịp tim, thả bằng `Start-Process pythonw.exe`, đã sống qua mọi lần đổi phiên từ 18-09.

Nên script này là đúng cái khuôn ấy: `pythonw` (không console) khởi chạy lệnh và ĐỢI nó. Con phải mang
`CREATE_NO_WINDOW` - `pythonw` chỉ lo cho chính nó, và thiếu cờ ấy thì bash sẽ bật một cửa sổ terminal
(xem `tests/test_a_windowless_daemon_opens_no_window.py`, lỗi 21-09 của `heartbeat_daemon.py`).

Mã thoát và giờ chạy ghi vào `runtime/detached_runs.log`, vì không có ai đọc stdout của một tiến trình rời.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOG = ROOT / "runtime" / "detached_runs.log"
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000) if os.name == "nt" else 0
GIT_BASH = Path(r"C:\Program Files\Git\bin\bash.exe")


def _resolve(program: str) -> str:
    """`bash` phải là Git Bash: `bash.exe` của WSL cũng nằm trên PATH và chạy một hệ điều hành khác."""
    if program == "bash" and GIT_BASH.is_file():
        return str(GIT_BASH)
    return shutil.which(program) or program


def _note(line: str) -> None:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as handle:
        handle.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} pid={os.getpid()} {line}\n")


def main(argv: list[str]) -> int:
    if not argv:
        _note("không có lệnh nào để chạy")
        return 2
    command = [_resolve(argv[0]), *argv[1:]]
    _note(f"bắt đầu: {' '.join(argv)}")
    completed = subprocess.run(
        command, cwd=str(ROOT), stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL, creationflags=NO_WINDOW,
    )
    _note(f"xong (mã {completed.returncode}): {' '.join(argv)}")
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
