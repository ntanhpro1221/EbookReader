"""Script chạy bằng `pythonw.exe` không được khởi chạy chương trình console nào mà thiếu `creationflags`.

`pythonw.exe` không có console. Chương trình console nó khởi chạy mà không mang `CREATE_NO_WINDOW` thì Windows
cấp cho một console MỚI, và Windows 11 mở một cửa sổ terminal để hiện nó - nháy lên rồi tắt.

Ca thật: `scripts/heartbeat_daemon.py` chạy `python.exe heartbeat_tick.py` mỗi 30 phút từ 18-09 21:16 mà
thiếu cờ, và chủ sách hỏi ngày 21-09 "thi thoảng tôi cứ thấy cái terminal nó pop ra rồi biến mất". Docstring
của chính daemon ấy ghi nó dùng `pythonw.exe` "để không có cửa sổ console nháy" - `pythonw` chỉ lo cho bản
thân nó, không lo cho con. Cùng loại lỗi `ebook_reader/background_runner.py` đã sửa hôm 11-09.

Kiểm bằng cây cú pháp: mọi lệnh gọi `subprocess.run` / `subprocess.Popen` / `subprocess.call` /
`subprocess.check_output` trong các script chạy bằng `pythonw` phải truyền `creationflags`.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

# Các script mà dự án khởi chạy bằng pythonw.exe (daemon nhịp tim, tác vụ Task Scheduler tự chạy lại lô).
WINDOWLESS_SCRIPTS = (
    "scripts/heartbeat_daemon.py",
    "scripts/resume_interrupted.py",
)
SPAWNING_CALLS = {"run", "Popen", "call", "check_call", "check_output"}


def _subprocess_calls_without_flags(path: Path) -> list[int]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    missing = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr not in SPAWNING_CALLS:
            continue
        owner = node.func.value
        if not (isinstance(owner, ast.Name) and owner.id == "subprocess"):
            continue
        if not any(keyword.arg == "creationflags" for keyword in node.keywords):
            missing.append(node.lineno)
    return missing


@pytest.mark.parametrize("relative", WINDOWLESS_SCRIPTS)
def test_every_child_of_a_windowless_script_is_windowless_too(relative: str) -> None:
    path = ROOT / relative
    assert path.is_file(), f"{relative} đã đổi chỗ - cập nhật WINDOWLESS_SCRIPTS"
    missing = _subprocess_calls_without_flags(path)
    assert missing == [], (
        f"{relative}: lệnh gọi subprocess ở dòng {missing} thiếu creationflags - mỗi lần chạy sẽ nháy một "
        "cửa sổ terminal vì cha là pythonw.exe (không có console)"
    )


def test_the_check_would_catch_the_original_bug(tmp_path: Path) -> None:
    """Chính bản lỗi của heartbeat_daemon.py (trước 21-09) phải bị bắt - không thì test trên vô nghĩa."""
    probe = tmp_path / "old_heartbeat_daemon.py"
    probe.write_text(
        "import subprocess\n"
        "def one_tick(python, tick):\n"
        "    return subprocess.run([str(python), str(tick)], capture_output=True, timeout=600)\n",
        encoding="utf-8",
    )
    assert _subprocess_calls_without_flags(probe) == [3]
