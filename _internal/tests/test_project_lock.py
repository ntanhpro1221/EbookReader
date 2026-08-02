from __future__ import annotations

from pathlib import Path

from ebook_reader.config import build_settings, settings_hash
from ebook_reader.project import create_or_open_project


def test_changed_settings_create_a_separate_project(tmp_path: Path) -> None:
    source = tmp_path / "001.txt"
    source.write_text("Đây là một đoạn kể chuyện.", encoding="utf-8")
    first = build_settings("balanced")
    paths, db, used = create_or_open_project([source], tmp_path / "out", first, "Truyện")
    assert used["quality_profile"] == "balanced"
    second = build_settings("fast")
    paths2, db2, used2 = create_or_open_project([source], tmp_path / "out", second, "Truyện")
    assert paths2.root != paths.root
    assert used2["quality_profile"] == "fast"
    assert db.book()["settings_hash"] == settings_hash(first)
    assert db2.book()["settings_hash"] == settings_hash(second)
