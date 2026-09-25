"""Thoát 0 khi GPU còn đủ VRAM trống cho pha phân tích; thoát 1 khi chưa.

    runtime/.venv/Scripts/python.exe scripts/heartbeat_wait.py --until scripts/gpu_has_room.py

Vì sao (25-09 08:2x): sau khi máy khởi động lại, Unity Editor + Rider của chủ máy giữ 1.954 MiB, còn trống
6.197 MiB - trong khi `qwen3:8b` với `num_ctx` 7.168 cần ~6.204 MiB (docs/THROUGHPUT.md, mục "Một Unity Editor
MỞ MÀ NẰM IM"). Thả lô vào khe ấy thì Ollama tự tháo model giữa lượt và phân tích bò ~15 lần chậm hơn - mà lô
17 vừa phải chạy lại từ đầu chính vì pha phân tích bị ngắt. Nên chờ có chỗ rồi mới thả, và để nhịp tim thức
ngay khi có chỗ thay vì đợi hết giờ.

Ngưỡng mặc định 6.500 MiB = 6.204 cần + ~300 dư, đúng khoảng dư mà lần 21-09 thiếu.
"""
from __future__ import annotations

import os
import subprocess
import sys

NEEDED_MIB = 6500
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000) if os.name == "nt" else 0


def free_mib() -> int | None:
    try:
        output = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.used,memory.total", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=30, creationflags=NO_WINDOW,
        ).stdout
        used, total = (int(value) for value in output.splitlines()[0].split(","))
    except (OSError, subprocess.SubprocessError, ValueError, IndexError):
        return None
    return total - used


def main(argv: list[str]) -> int:
    needed = int(argv[0]) if argv else NEEDED_MIB
    free = free_mib()
    if free is None:
        print("không đọc được nvidia-smi")
        return 1
    print(f"VRAM trống {free} MiB, cần {needed} MiB: {'ĐỦ' if free >= needed else 'chưa đủ'}")
    return 0 if free >= needed else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
