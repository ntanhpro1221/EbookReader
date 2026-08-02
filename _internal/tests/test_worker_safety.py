from __future__ import annotations

import json
from pathlib import Path

import pytest

from ebook_reader.config import build_settings, save_settings, settings_hash
from ebook_reader.database import ProjectDB
from ebook_reader.io_utils import sha256_file
from ebook_reader.models import ProjectPaths
from ebook_reader.worker import (
    ProjectRunLock,
    _apply_runtime_resource_overrides,
    _load_locked_settings,
    _validate_project_inputs,
)


def _project(tmp_path: Path):
    paths = ProjectPaths.build(tmp_path / "project")
    settings = build_settings()
    save_settings(paths.settings, settings)
    db = ProjectDB(paths.db)
    db.initialize_book(
        title="Book",
        project_root=paths.root,
        settings=settings,
        settings_hash=settings_hash(settings),
        input_manifest_hash="manifest",
    )
    source = tmp_path / "001.txt"
    source.write_text("Nội dung nguồn đã khóa.", encoding="utf-8")
    db.ensure_chapters([{
        "chapter_index": 1,
        "title": "001",
        "input_path": source,
        "input_sha256": sha256_file(source),
        "input_size": source.stat().st_size,
        "output_mp3": paths.chapters / "001.mp3",
    }])
    return paths, settings, db, source


def test_worker_rejects_external_settings_that_differ_from_sqlite(tmp_path: Path) -> None:
    paths, settings, db, _source = _project(tmp_path)
    tampered = json.loads(json.dumps(settings))
    tampered["tts"]["batch_size"] += 1
    save_settings(paths.settings, tampered)

    with pytest.raises(RuntimeError, match="khác settings đã khóa"):
        _load_locked_settings(paths, db)


def test_worker_rejects_changed_source_file(tmp_path: Path) -> None:
    paths, settings, db, source = _project(tmp_path)
    source.write_text("Nội dung nguồn đã bị thay đổi.", encoding="utf-8")

    with pytest.raises(RuntimeError, match="đã đổi kích thước|đã thay đổi nội dung"):
        _validate_project_inputs(paths, db, settings)


def test_runtime_resources_override_global_values_without_mutating_book_settings() -> None:
    locked = build_settings()
    updated = _apply_runtime_resource_overrides(
        locked,
        {
            "mode": "max_safe",
            "max_gpu_temp_c": 82,
            "resume_gpu_temp_c": 76,
            "critical_gpu_temp_c": 87,
        },
    )

    assert locked["resources"]["mode"] == "max_safe_adaptive_foreground"
    assert locked["resources"]["max_gpu_temp_c"] == 86
    assert updated["resources"]["mode"] == "max_safe"
    assert updated["resources"]["max_gpu_temp_c"] == 82
    assert updated["voices"] == locked["voices"]


def test_project_run_lock_is_exclusive(tmp_path: Path) -> None:
    first = ProjectRunLock(tmp_path / ".worker.lock")
    second = ProjectRunLock(tmp_path / ".worker.lock")
    first.acquire()
    try:
        with pytest.raises(RuntimeError, match="worker khác"):
            second.acquire()
    finally:
        first.release()
