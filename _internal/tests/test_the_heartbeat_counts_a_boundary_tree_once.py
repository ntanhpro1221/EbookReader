"""Một ranh giới chạy rời là bốn tiến trình nhưng chỉ một gốc.

Nhịp tim 22:01 ngày 24-09 báo "4 gốc" cho đúng một `boundary.sh 17`, vì `run_detached.py` dựng chuỗi
pythonw (venv) → pythonw (gốc) → Git Bash `bin/bash.exe` → `usr/bin/bash.exe`, cả bốn mang `boundary.sh 17`
trong dòng lệnh. Các pid dưới đây là cây thật lúc ấy.
"""
from __future__ import annotations

import scripts.heartbeat_tick as tick

PATTERN = r"boundary\.sh \d"

DETACHED_17 = [
    (25992, 1000, "C:\\Windows\\explorer.exe"),
    (24536, 25992, '"runtime\\.venv\\Scripts\\pythonw.exe" scripts\\run_detached.py bash scripts/boundary.sh 17'),
    (56044, 24536, '"C:\\Python311\\pythonw.exe" scripts\\run_detached.py bash scripts/boundary.sh 17'),
    (33104, 56044, '"C:\\Program Files\\Git\\bin\\bash.exe" scripts/boundary.sh 17'),
    (34616, 33104, '"C:\\Program Files\\Git\\bin\\..\\usr\\bin\\bash.exe" scripts/boundary.sh 17'),
]


def test_a_detached_boundary_is_one_root() -> None:
    roots = tick.tree_roots(DETACHED_17, PATTERN)
    assert len(roots) == 1
    assert "run_detached.py" in roots[0]


def test_two_separate_boundaries_are_two_roots() -> None:
    """Cái phép đếm phải bắt được: hai ranh giới cùng chạy là lỗi thật, không được gộp mất."""
    second = [
        (70000, 25992, '"C:\\Program Files\\Git\\bin\\bash.exe" scripts/boundary.sh 18'),
        (70001, 70000, '"C:\\Program Files\\Git\\bin\\..\\usr\\bin\\bash.exe" scripts/boundary.sh 18'),
    ]
    assert len(tick.tree_roots(DETACHED_17 + second, PATTERN)) == 2


def test_a_session_wrapper_shell_is_not_a_root() -> None:
    """Lối cũ: lệnh nền của phiên bọc trong `bash -c "... boundary.sh 4 ..."` - cái vỏ không phải ranh giới."""
    procs = [
        (100, 1, 'bash -c "cd /d/x && bash scripts/boundary.sh 4 > runtime/boundary_04.log"'),
        (101, 100, "bash scripts/boundary.sh 4"),
    ]
    assert tick.tree_roots(procs, PATTERN) == ["bash scripts/boundary.sh 4"]


def test_no_boundary_is_zero_roots() -> None:
    assert tick.tree_roots(DETACHED_17[:1], PATTERN) == []
