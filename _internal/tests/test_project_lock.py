from __future__ import annotations

import threading
import time
from pathlib import Path

from ebook_reader import project as project_module
from ebook_reader.config import build_settings, load_settings, settings_hash
from ebook_reader.database import ProjectDB
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


def test_concurrent_creators_with_different_settings_cannot_cross_lock_files(
    tmp_path: Path,
    monkeypatch,
) -> None:
    source = tmp_path / "001.txt"
    source.write_text("Đây là nội dung kiểm thử khóa tạo project.", encoding="utf-8")
    output_root = tmp_path / "out"
    settings_by_profile = {
        "balanced": build_settings("balanced"),
        "fast": build_settings("fast"),
    }
    original_save_settings = project_module.save_settings
    first_save_entered = threading.Event()
    allow_first_save = threading.Event()
    call_lock = threading.Lock()
    save_calls = 0

    def delayed_save_settings(path, settings) -> None:
        nonlocal save_calls
        with call_lock:
            save_calls += 1
            call_index = save_calls
        if call_index == 1:
            first_save_entered.set()
            assert allow_first_save.wait(5.0)
        original_save_settings(path, settings)

    monkeypatch.setattr(project_module, "save_settings", delayed_save_settings)
    results: dict[str, Path] = {}
    errors: list[BaseException] = []

    def create(profile: str) -> None:
        try:
            paths, _db, _settings = create_or_open_project(
                [source],
                output_root,
                settings_by_profile[profile],
                "Concurrent Book",
            )
            results[profile] = paths.root
        except BaseException as exc:  # noqa: BLE001 - assertion reports thread failures.
            errors.append(exc)

    first = threading.Thread(target=create, args=("balanced",), daemon=True)
    second = threading.Thread(target=create, args=("fast",), daemon=True)
    first.start()
    assert first_save_entered.wait(5.0)
    second.start()
    time.sleep(0.1)
    assert second.is_alive()
    allow_first_save.set()
    first.join(10.0)
    second.join(10.0)

    assert not first.is_alive()
    assert not second.is_alive()
    assert errors == []
    assert set(results) == {"balanced", "fast"}
    assert results["balanced"] != results["fast"]
    for profile, root in results.items():
        requested_hash = settings_hash(settings_by_profile[profile])
        assert settings_hash(load_settings(root / "book_settings.json")) == requested_hash
        assert str(ProjectDB(root / "project.sqlite3").book()["settings_hash"]) == requested_hash
