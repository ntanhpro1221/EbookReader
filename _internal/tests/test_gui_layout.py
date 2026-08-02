from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QSettings, Qt
from PySide6.QtWidgets import QAbstractItemView, QApplication

from e_book_reader.config import build_settings
from e_book_reader.gui import MainWindow
from e_book_reader.project import create_or_open_project


def _window(tmp_path: Path) -> tuple[QApplication, MainWindow, QSettings]:
    app = QApplication.instance() or QApplication([])
    store = QSettings(str(tmp_path / "ui.ini"), QSettings.Format.IniFormat)
    window = MainWindow(settings_store=store, restore_recent=False)
    window.timer.stop()
    return app, window, store


def test_gui_has_multi_file_selection_nested_splitters_and_one_safe_stop(tmp_path: Path) -> None:
    _app, window, _store = _window(tmp_path)

    assert window.file_list.selectionMode() == QAbstractItemView.SelectionMode.ExtendedSelection
    assert window.main_splitter.orientation() == Qt.Orientation.Vertical
    assert window.source_splitter.orientation() == Qt.Orientation.Horizontal
    assert window.work_splitter.orientation() == Qt.Orientation.Horizontal
    assert window.source_splitter.count() == 2
    assert window.work_splitter.count() == 2
    assert window.full_book.isChecked() is False
    assert window.stop_button.text() == "Dừng"
    assert not hasattr(window, "stop_now_button")
    assert not hasattr(window, "pause_battery")
    assert not hasattr(window, "resource_label")
    window.close()


def test_remove_files_removes_every_selected_row(tmp_path: Path) -> None:
    _app, window, _store = _window(tmp_path)
    window.files = [tmp_path / "001.txt", tmp_path / "002.txt", tmp_path / "003.txt"]
    window._refresh_file_list()
    window.file_list.item(0).setSelected(True)
    window.file_list.item(2).setSelected(True)

    window._remove_files()

    assert window.files == [tmp_path / "002.txt"]
    window.close()


def test_recent_project_prefers_explicit_last_selection_then_latest_database(tmp_path: Path) -> None:
    _app, window, store = _window(tmp_path)
    output = tmp_path / "books"
    older = output / "older"
    newer = output / "newer"
    for project in (older, newer):
        project.mkdir(parents=True)
        (project / "project.sqlite3").write_bytes(b"db")
        (project / "book_settings.json").write_text("{}", encoding="utf-8")
    os.utime(older / "project.sqlite3", (1, 1))
    os.utime(newer / "project.sqlite3", (2, 2))
    window.output_edit.setText(str(output))

    assert window._recent_project_candidate() == newer.resolve()

    store.setValue("recent_project", str(older))
    assert window._recent_project_candidate() == older.resolve()
    window.close()


def test_startup_opens_the_last_selected_project(tmp_path: Path) -> None:
    _app = QApplication.instance() or QApplication([])
    source = tmp_path / "001.txt"
    source.write_text("Một chapter để kiểm tra giao diện.", encoding="utf-8")
    paths, _db, _settings = create_or_open_project(
        [source],
        tmp_path / "books",
        build_settings(),
        "Book gần đây",
    )
    store = QSettings(str(tmp_path / "recent.ini"), QSettings.Format.IniFormat)
    store.setValue("recent_project", str(paths.root))

    window = MainWindow(settings_store=store, restore_recent=True)
    window.timer.stop()

    assert window.project_paths is not None
    assert window.project_paths.root == paths.root
    assert window.title_edit.text() == "Book gần đây"
    assert window.file_list.count() == 1
    window.close()
