"""Bộ canh "có lượt nào đang bay" của `apply_all` phải nhìn MỌI cuốn, không riêng cuốn 1.

`apply_all` ghi vào những file trong `QUALITY_IMPLEMENTATION_FILES`, nên ghi giữa một lượt đang
chạy làm `quality_implementation_hash()` đổi và lượt ấy bị từ chối khi resume. Vì thế nó có bộ
canh đọc nhịp tim `worker_leases`, và `boundary.sh` dùng **chính** hàm ấy cho `wait_gpu_free`.

Bộ canh ghim cứng `D:\\Novels\\Audiobooks\\_versions` — gốc của cuốn 1. Từ 13-09 cuốn 2 sản xuất
ở `.../book2/_versions`, nên bộ canh soi một thư mục không có lượt nào và luôn trả lời "không có
lượt nào đang chạy": đo lúc 16:45 ngày 15-09, lô 3 đang chạy với nhịp tim cách 4 giây mà
`apply_all` vẫn nói không có gì bay. Cùng họ với lỗi `before_a_batch.py` (`_versions` của cuốn 1)
đã sửa sáng cùng ngày.

Bài này khoá hai điều: gốc quét lấy từ `book_paths` (theo biến môi trường, không chép tay), và
một lượt của cuốn **nào** cũng bị thấy.
"""
from __future__ import annotations

import importlib.util
import sqlite3
import time
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[1]
APPLY_ALL = ROOT / "scripts" / "pending_patches" / "apply_all.py"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("apply_all_under_test", APPLY_ALL)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _project_with_a_live_lease(root: Path, *, state: str, age: float) -> Path:
    project = root / "v9.9.9-lo01" / "lo01_deadbeef"
    project.mkdir(parents=True)
    connection = sqlite3.connect(project / "project.sqlite3")
    try:
        connection.execute(
            "CREATE TABLE worker_leases (worker_name TEXT, pid INTEGER, state TEXT,"
            " heartbeat_at REAL)"
        )
        connection.execute(
            "INSERT INTO worker_leases VALUES (?, ?, ?, ?)",
            ("pipeline", 4242, state, time.time() - age),
        )
        connection.commit()
    finally:
        connection.close()
    return project


def test_the_roots_come_from_book_paths_not_from_a_typed_path() -> None:
    module = _load()
    from scripts.book_paths import VERSIONS as CONFIGURED

    assert module.VERSIONS == CONFIGURED
    source = APPLY_ALL.read_text(encoding="utf-8")
    assert "Audiobooks\\_versions" not in source, "đường dẫn chép tay đã quay lại"


def test_a_sibling_book_is_scanned_too(tmp_path: Path, monkeypatch) -> None:
    """Hình thật: cuốn 1 ở `Audiobooks/_versions`, cuốn 2 ở `Audiobooks/book2/_versions`."""
    audiobooks = tmp_path / "Audiobooks"
    book_one = audiobooks / "_versions"
    book_two = audiobooks / "book2" / "_versions"
    book_one.mkdir(parents=True)
    book_two.mkdir(parents=True)
    module = _load()
    monkeypatch.setattr(module, "VERSIONS", book_two)

    roots = module._version_roots()

    assert book_two in roots, roots
    assert book_one in roots, "một lượt của cuốn 1 cũng làm bản vá hỏng, phải nhìn nó"
    assert len(roots) == len(set(roots)), roots


def test_a_live_run_in_the_configured_book_is_seen(tmp_path: Path, monkeypatch) -> None:
    versions = tmp_path / "Audiobooks" / "book2" / "_versions"
    versions.mkdir(parents=True)
    project = _project_with_a_live_lease(versions, state="running", age=4.0)
    module = _load()
    monkeypatch.setattr(module, "VERSIONS", versions)

    live = module._runs_in_flight()

    assert [path for path, _why in live] == [project], live
    assert "nhịp cách 4s" in live[0][1]


def test_a_live_run_in_the_other_book_is_seen(tmp_path: Path, monkeypatch) -> None:
    audiobooks = tmp_path / "Audiobooks"
    book_one = audiobooks / "_versions"
    book_two = audiobooks / "book2" / "_versions"
    book_one.mkdir(parents=True)
    book_two.mkdir(parents=True)
    project = _project_with_a_live_lease(book_one, state="running", age=2.0)
    module = _load()
    monkeypatch.setattr(module, "VERSIONS", book_two)

    assert [path for path, _why in module._runs_in_flight()] == [project]


def test_a_finished_project_does_not_block_a_patch(tmp_path: Path, monkeypatch) -> None:
    """Một bộ canh lúc nào cũng kêu chỉ dạy người ta gõ `--force`.

    Project đã xong **xoá** dòng lease (đo trên 10 project cuốn 2 lúc 16:40 ngày 15-09: không
    cái nào còn dòng nào), và một dòng cũ còn sót thì nhịp tim đã quá hạn.
    """
    versions = tmp_path / "Audiobooks" / "book2" / "_versions"
    versions.mkdir(parents=True)
    module = _load()
    monkeypatch.setattr(module, "VERSIONS", versions)
    stale = _project_with_a_live_lease(versions, state="running", age=module.LEASE_STALE_SECONDS + 30)

    assert module._runs_in_flight() == []
    assert (stale / "project.sqlite3").is_file()


def test_a_missing_versions_directory_is_not_an_error(tmp_path: Path, monkeypatch) -> None:
    module = _load()
    monkeypatch.setattr(module, "VERSIONS", tmp_path / "khong-ton-tai")

    assert module._version_roots() == [] or module._runs_in_flight() == []
