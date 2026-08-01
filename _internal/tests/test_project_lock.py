from __future__ import annotations

from pathlib import Path

import pytest

from e_book_reader.config import build_settings, settings_hash
from e_book_reader.database import ProjectDB
from e_book_reader.project import create_or_open_project


def test_project_uses_original_locked_settings(tmp_path: Path) -> None:
    source = tmp_path / "001.txt"
    source.write_text("Đây là một đoạn kể chuyện.", encoding="utf-8")
    first = build_settings("balanced")
    paths, db, used = create_or_open_project([source], tmp_path / "out", first, "Truyện")
    assert used["quality_profile"] == "balanced"
    second = build_settings("fast")
    paths2, db2, used2 = create_or_open_project([source], tmp_path / "out", second, "Truyện")
    assert paths2.root == paths.root
    assert used2["quality_profile"] == "balanced"
    assert db2.book()["settings_hash"] == db.book()["settings_hash"]


def test_runtime_fingerprint_is_locked_after_first_worker(tmp_path: Path) -> None:
    db = ProjectDB(tmp_path / "project.sqlite3")
    settings = build_settings()
    db.initialize_book(
        title="Book",
        project_root=tmp_path,
        settings=settings,
        settings_hash=settings_hash(settings),
        input_manifest_hash="manifest",
    )
    db.bind_runtime_fingerprint({"python": "3.11.9"}, "a" * 64)
    db.bind_runtime_fingerprint({"python": "3.11.9"}, "a" * 64)

    with pytest.raises(RuntimeError, match="Runtime/model fingerprint"):
        db.bind_runtime_fingerprint({"python": "3.11.10"}, "b" * 64)
