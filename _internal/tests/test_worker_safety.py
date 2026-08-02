from __future__ import annotations

import json
from pathlib import Path

import pytest

from e_book_reader.config import build_settings, save_settings, settings_hash
from e_book_reader.database import ProjectDB
from e_book_reader.io_utils import atomic_write_json, sha256_file
from e_book_reader.models import ProjectPaths
from e_book_reader.worker import ProjectRunLock, _load_locked_settings, _validate_project_inputs


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


def test_worker_hydrates_legacy_settings_after_verifying_original_hash(tmp_path: Path) -> None:
    paths = ProjectPaths.build(tmp_path / "legacy-project")
    legacy = build_settings()
    legacy["tts"]["failure_policy"] = "retry_split_fallback_fail"
    legacy["tts"].pop("pace_chars_per_second")
    legacy["tts"].pop("rate_check_min_chars")
    atomic_write_json(paths.settings, legacy)
    db = ProjectDB(paths.db)
    db.initialize_book(
        title="Legacy",
        project_root=paths.root,
        settings=legacy,
        settings_hash=settings_hash(legacy),
        input_manifest_hash="manifest",
    )

    loaded = _load_locked_settings(paths, db)

    assert settings_hash(legacy) == str(db.book()["settings_hash"])
    assert loaded["tts"]["pace_chars_per_second"]["normal"] == [10.5, 22.0]
    assert loaded["tts"]["failure_policy"] == "retry_split_fallback_fail"


def test_worker_rejects_changed_source_file(tmp_path: Path) -> None:
    paths, settings, db, source = _project(tmp_path)
    source.write_text("Nội dung nguồn đã bị thay đổi.", encoding="utf-8")

    with pytest.raises(RuntimeError, match="đã đổi kích thước|đã thay đổi nội dung"):
        _validate_project_inputs(paths, db, settings)


def test_project_run_lock_is_exclusive(tmp_path: Path) -> None:
    first = ProjectRunLock(tmp_path / ".worker.lock")
    second = ProjectRunLock(tmp_path / ".worker.lock")
    first.acquire()
    try:
        with pytest.raises(RuntimeError, match="worker khác"):
            second.acquire()
    finally:
        first.release()
