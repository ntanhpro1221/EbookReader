"""Ba script ranh giới phải ít nhất PHÂN TÍCH được — chúng chạy lúc không có ai nhìn.

`boundary.sh` được thả trước khi lô xong và đọc tiếp file khi tới bước sau; một lỗi cú pháp ở
bước 6 chỉ lộ ra lúc ba giờ sáng, sau khi bốn bản vá đã áp và hai lô vá đã chạy. `bash -n`
bắt đúng lớp lỗi ấy trong một phần mười giây. Bỏ qua (có nói lý do) khi máy không có bash.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ["boundary.sh", "launch_batch.sh", "launch_repair.sh"]


def _bash() -> str | None:
    found = shutil.which("bash")
    if found:
        return found
    git_bash = Path("C:/Program Files/Git/bin/bash.exe")
    return str(git_bash) if git_bash.is_file() else None


@pytest.mark.parametrize("name", SCRIPTS)
def test_the_script_parses(name: str) -> None:
    bash = _bash()
    if bash is None:
        pytest.skip("không có bash trên máy này")
    result = subprocess.run(
        [bash, "-n", str(ROOT / "scripts" / name)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    assert result.returncode == 0, result.stderr


def test_every_launcher_seeds_through_seed_chain() -> None:
    """Một luật cho cả ba: "gieo từ đâu" trả lời bởi seed_chain.py, không bởi `ls -dt`."""
    for name in SCRIPTS:
        text = (ROOT / "scripts" / name).read_text(encoding="utf-8")
        assert "seed_chain.py" in text, name
        assert "ls -dt" not in text, f"{name}: mtime thư mục không xếp được project (xem seed_chain.py)"
