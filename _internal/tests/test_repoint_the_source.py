"""`scripts/repoint_the_source.py`: dời thư mục nguồn rồi trỏ lại project — có kiểm hash, có hoàn tác.

Dựng project THẬT bằng `create_or_open_project` trong thư mục tạm (đúng schema, đúng
`input_manifest_hash`), dời thư mục .txt đi, rồi xem công cụ có làm `cli.validate_project` xanh lại
mà không tắt kiểm nào không. Không trỏ vào project sống.
"""
from __future__ import annotations

import importlib.util
import json
import shutil
import sqlite3
from pathlib import Path

from ebook_reader import cli
from ebook_reader.config import build_settings
from ebook_reader.project import create_or_open_project

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "repoint_the_source", ROOT / "scripts" / "repoint_the_source.py"
)
repoint = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(repoint)


def _sources(root: Path, names: list[str]) -> list[Path]:
    root.mkdir(parents=True, exist_ok=True)
    paths = []
    for index, name in enumerate(names):
        path = root / name
        path.write_text(f"Chương {index + 1}. Nội dung kiểm thử trỏ lại nguồn.", encoding="utf-8")
        paths.append(path)
    return paths


def _project(tmp_path: Path) -> tuple[Path, Path]:
    sources = _sources(tmp_path / "text_a", ["000.txt", "001.txt", "002.txt"])
    paths, _db, _settings = create_or_open_project(
        sources, tmp_path / "out", build_settings("high_quality"), "Repoint Test"
    )
    return paths.root, tmp_path / "text_a"


def _paths_and_hash(project: Path) -> tuple[list[str], str]:
    connection = sqlite3.connect(project / "project.sqlite3")
    try:
        paths = [
            row[0]
            for row in connection.execute("SELECT input_path FROM chapters ORDER BY chapter_index")
        ]
        locked = connection.execute("SELECT input_manifest_hash FROM book").fetchone()[0]
    finally:
        connection.close()
    return paths, locked


def test_moved_sources_are_repointed_and_verify_goes_green_again(tmp_path: Path) -> None:
    project, text_a = _project(tmp_path)
    before_paths, before_hash = _paths_and_hash(project)
    assert cli.validate_project(project)["checks"]["source_files"] is True

    text_b = tmp_path / "text_b"
    shutil.move(str(text_a), str(text_b))
    broken = cli.validate_project(project)
    assert broken["checks"]["source_files"] is False

    # Chỉ xem: không đổi gì.
    assert repoint.main([str(text_b), "--project", str(project)]) == 0
    assert _paths_and_hash(project) == (before_paths, before_hash)

    # Ghi thật: đường mới, hash khoá tính lại bằng cùng hàm verify dùng, verify xanh cả hai kiểm.
    assert repoint.main([str(text_b), "--project", str(project), "--apply"]) == 0
    after_paths, after_hash = _paths_and_hash(project)
    assert [Path(p).parent for p in after_paths] == [text_b.resolve()] * 3
    assert [Path(p).name for p in after_paths] == ["000.txt", "001.txt", "002.txt"]
    assert after_hash != before_hash
    fixed = cli.validate_project(project)
    assert fixed["checks"]["input_manifest_hash"] is True
    assert fixed["checks"]["source_files"] is True

    ledger = json.loads((project / repoint.LEDGER_NAME).read_text(encoding="utf-8"))
    assert len(ledger) == 1
    assert ledger[0]["old_manifest_hash"] == before_hash
    assert ledger[0]["new_manifest_hash"] == after_hash
    assert [c["old"] for c in ledger[0]["chapters"]] == before_paths

    # Chạy lại là "đã trỏ đúng", không ghi thêm mục sổ.
    assert repoint.main([str(text_b), "--project", str(project), "--apply"]) == 0
    assert len(json.loads((project / repoint.LEDGER_NAME).read_text(encoding="utf-8"))) == 1


def test_a_different_file_with_the_same_name_is_refused_for_the_whole_project(tmp_path: Path) -> None:
    project, text_a = _project(tmp_path)
    before = _paths_and_hash(project)
    text_c = tmp_path / "text_c"
    shutil.copytree(text_a, text_c)
    (text_c / "001.txt").write_text("Một chương khác hẳn, cùng tên file.", encoding="utf-8")

    assert repoint.main([str(text_c), "--project", str(project), "--apply"]) == 1
    # Không trỏ nửa vời: cả 000 và 002 (khớp) cũng giữ nguyên.
    assert _paths_and_hash(project) == before
    assert not (project / repoint.LEDGER_NAME).exists()


def test_undo_restores_the_old_paths_and_the_locked_hash(tmp_path: Path) -> None:
    project, text_a = _project(tmp_path)
    before_paths, before_hash = _paths_and_hash(project)
    text_b = tmp_path / "text_b"
    shutil.move(str(text_a), str(text_b))
    assert repoint.main([str(text_b), "--project", str(project), "--apply"]) == 0

    assert repoint.main(["--undo", str(project)]) == 0
    assert _paths_and_hash(project) == (before_paths, before_hash)
    assert json.loads((project / repoint.LEDGER_NAME).read_text(encoding="utf-8")) == []
    # Sổ rỗng thì không có gì để hoàn tác nữa.
    assert repoint.main(["--undo", str(project)]) == 1


def test_undo_refuses_when_the_database_drifted_since_the_ledger_entry(tmp_path: Path) -> None:
    project, text_a = _project(tmp_path)
    text_b = tmp_path / "text_b"
    shutil.move(str(text_a), str(text_b))
    assert repoint.main([str(text_b), "--project", str(project), "--apply"]) == 0
    connection = sqlite3.connect(project / "project.sqlite3")
    try:
        connection.execute("UPDATE chapters SET input_path = 'X:/ai-do-doi-tay.txt' WHERE chapter_index = 2")
        connection.commit()
    finally:
        connection.close()
    assert repoint.main(["--undo", str(project)]) == 1
