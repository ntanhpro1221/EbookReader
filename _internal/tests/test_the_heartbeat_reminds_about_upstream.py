"""Mỗi nhịp tim nói lần kiểm thượng nguồn cuối cách đây bao lâu - và la lên khi quá 24 giờ.

`check_dependency_updates.py` từng nằm im 18 ngày (30-08 → 17-09) trong khi VieNeu ra 16 bản, và chủ
sách phải tự hỏi "vietneu có bản mới chưa?". Một việc thường trực mà không có gì nhắc thì sẽ bị quên.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from scripts.heartbeat_tick import upstream_line


def _audit(tmp_path: Path, hours_ago: float, **found: list[str]) -> Path:
    path = tmp_path / "dependency_audit.json"
    path.write_text(json.dumps({"checked_at": time.time() - hours_ago * 3600, **found}), encoding="utf-8")
    return path


def test_never_checked_says_so(tmp_path: Path) -> None:
    assert "CHƯA TỪNG KIỂM" in upstream_line(tmp_path / "missing.json")


def test_a_stale_audit_is_loud_and_names_the_command(tmp_path: Path) -> None:
    line = upstream_line(_audit(tmp_path, 30, outdated_packages=["vieneu"]))
    assert "QUÁ 30 GIỜ" in line and "check_dependency_updates.py" in line and "vieneu" in line


def test_a_fresh_audit_reports_what_it_found(tmp_path: Path) -> None:
    line = upstream_line(_audit(tmp_path, 2, outdated_packages=["torch", "vieneu"], retagged_ollama_models=[]))
    assert "QUÁ" not in line and "2 thứ có bản mới" in line and "torch" in line


def test_a_fresh_audit_with_nothing_new(tmp_path: Path) -> None:
    assert "không có gì mới" in upstream_line(_audit(tmp_path, 1))
