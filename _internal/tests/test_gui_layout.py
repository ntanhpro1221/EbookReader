from __future__ import annotations

import os
import re
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, QSettings, Qt
from PySide6.QtGui import QCloseEvent, QPalette
from PySide6.QtTest import QTest
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QHeaderView,
    QLabel,
    QTableWidgetItem,
)

from e_book_reader.config import build_settings
from e_book_reader.gui import APP_ICON_PATH, MainWindow
from e_book_reader.project import create_or_open_project


def _window(tmp_path: Path) -> tuple[QApplication, MainWindow, QSettings]:
    app = QApplication.instance() or QApplication([])
    store = QSettings(str(tmp_path / "ui.ini"), QSettings.Format.IniFormat)
    window = MainWindow(settings_store=store, restore_recent=False)
    window.timer.stop()
    return app, window, store


def test_gui_has_compact_header_nested_splitters_and_one_stop(tmp_path: Path) -> None:
    _app, window, _store = _window(tmp_path)

    assert window.start_button.text() == "Bắt đầu"
    assert window.start_button.isEnabled() is False
    assert "E Book Reader" not in {label.text() for label in window.findChildren(QLabel)}
    assert window.file_list.selectionMode() == QAbstractItemView.SelectionMode.ExtendedSelection
    assert window.main_splitter.orientation() == Qt.Orientation.Vertical
    assert window.source_splitter.orientation() == Qt.Orientation.Horizontal
    assert window.work_splitter.orientation() == Qt.Orientation.Horizontal
    assert window.source_splitter.count() == 2
    assert window.work_splitter.count() == 2
    assert not hasattr(window, "full_book")
    assert not hasattr(window, "keep_wav")
    assert window.stop_button.text() == "Dừng"
    assert window.book_box.title() == "Sách"
    assert window.files_box.title() == "Chapter nguồn"
    assert window.settings_box.title() == "Thiết lập"
    assert window.chapters_box.title() == "Tiến độ"
    assert window.log_box.title() == "Log"
    assert window.add_files_button.text() == "Thêm file"
    assert window.open_project_button.text() == "Mở sách khác"
    assert window.open_folder_button.text() == "Hiển thị sách trong Explorer"
    assert window.show_action.text() == "Hiện E Book Reader"
    assert window.hide_action.text() == "Ẩn xuống system tray"
    assert window.quit_action.text() == "Thoát hoàn toàn"
    assert window.narrator_gender_combo.currentData() == "male"
    assert window.narrator_voice_combo.currentData() == "Phạm Tuyên"
    assert "Minh Đức" not in {
        window.narrator_voice_combo.itemData(index)
        for index in range(window.narrator_voice_combo.count())
    }
    assert APP_ICON_PATH.is_file()
    assert window.windowIcon().isNull() is False
    assert window.tray_icon.icon().isNull() is False
    assert not hasattr(window, "pause_button")
    assert not hasattr(window, "stop_now_button")
    assert not hasattr(window, "pause_battery")
    assert not hasattr(window, "resource_label")
    top = window.book_box.layout()
    open_button_index = top.indexOf(window.open_project_button)
    assert top.getItemPosition(open_button_index) == (0, 3, 1, 1)
    for button in (
        window.new_book_button,
        window.add_files_button,
        window.add_folder_button,
        window.remove_files_button,
    ):
        assert window.input_actions.stretch(window.input_actions.indexOf(button)) == 1
    window.close()


def test_primary_button_owns_pause_and_resume_states(tmp_path: Path) -> None:
    _app, window, _store = _window(tmp_path)

    class FakeProcess:
        @staticmethod
        def is_alive() -> bool:
            return True

    class FakeEvent:
        paused = False

        def is_set(self) -> bool:
            return self.paused

        def set(self) -> None:
            self.paused = True

        def clear(self) -> None:
            self.paused = False

    pause_event = FakeEvent()
    window.process = FakeProcess()
    window.pause_event = pause_event
    window._running_controls(True)

    assert window.start_button.text() == "Tạm dừng"
    assert window.start_button.isEnabled() is True
    window._handle_primary_action()
    assert pause_event.is_set() is True
    assert window.start_button.text() == "Tiếp tục"
    window._handle_primary_action()
    assert pause_event.is_set() is False
    assert window.start_button.text() == "Tạm dừng"

    window.process = None
    window.close()


def test_start_button_requires_at_least_one_source_chapter(tmp_path: Path) -> None:
    _app, window, _store = _window(tmp_path)

    assert window.start_button.isEnabled() is False
    window.files = [tmp_path / "001.txt"]
    window._refresh_file_list()
    assert window.start_button.isEnabled() is True
    window.files = []
    window._refresh_file_list()
    assert window.start_button.isEnabled() is False
    window.close()


def test_gui_log_prefixes_each_line_with_a_timestamp(tmp_path: Path) -> None:
    _app, window, _store = _window(tmp_path)

    window._append_log("Dòng một\nDòng hai")

    lines = window.log.toPlainText().splitlines()
    assert len(lines) == 2
    assert all(re.fullmatch(r"\[\d{2}:\d{2}:\d{2}\] Dòng (một|hai)", line) for line in lines)
    window.close()


def test_item_views_use_subtle_alternating_rows_and_text_selection_blue(tmp_path: Path) -> None:
    _app, window, _store = _window(tmp_path)

    for view in (window.file_list, window.chapter_table):
        palette = view.palette()
        base = palette.color(QPalette.ColorRole.Base)
        alternate = palette.color(QPalette.ColorRole.AlternateBase)
        log_highlight = window.log.palette().color(
            QPalette.ColorGroup.Active,
            QPalette.ColorRole.Highlight,
        )
        assert base != alternate
        assert alternate.lightness() < base.lightness()
        assert 5 <= abs(base.lightness() - alternate.lightness()) <= 24
        assert (
            palette.color(QPalette.ColorGroup.Active, QPalette.ColorRole.Highlight)
            == log_highlight
        )
        assert (
            palette.color(QPalette.ColorGroup.Inactive, QPalette.ColorRole.Highlight)
            == log_highlight
        )
        assert "::item:selected" in view.styleSheet()
        assert log_highlight.name() in view.styleSheet()
    assert "QPushButton:disabled" in window.centralWidget().styleSheet()
    assert "background-color: palette(dark)" in window.centralWidget().styleSheet()
    header = window.chapter_table.horizontalHeader()
    assert window.chapter_table.columnCount() == 7
    assert "Chia đoạn" not in {
        window.chapter_table.horizontalHeaderItem(column).text()
        for column in range(window.chapter_table.columnCount())
    }
    assert header.sectionsMovable() is True
    assert all(
        header.sectionResizeMode(column) == QHeaderView.ResizeMode.Interactive
        for column in range(window.chapter_table.columnCount())
    )
    assert window.chapter_table.textElideMode() == Qt.TextElideMode.ElideNone
    window.close()


def test_window_close_hides_to_available_system_tray(tmp_path: Path, monkeypatch) -> None:
    app, window, _store = _window(tmp_path)
    window._tray_available = True
    window.show()
    app.processEvents()
    terminated: list[bool] = []
    messages: list[tuple[object, ...]] = []
    monkeypatch.setattr(window, "_terminate_worker_for_exit", lambda: terminated.append(True))
    monkeypatch.setattr(window.tray_icon, "showMessage", lambda *args: messages.append(args))
    event = QCloseEvent()

    window.closeEvent(event)

    assert event.isAccepted() is False
    assert window.isHidden() is True
    assert terminated == []
    assert len(messages) == 1
    window._force_quit = True
    window.close()


def test_tray_quit_terminates_worker_without_waiting_for_checkpoint(tmp_path: Path, monkeypatch) -> None:
    _app, window, _store = _window(tmp_path)
    calls: list[tuple[int, float]] = []

    class FakeProcess:
        pid = 12345

        @staticmethod
        def is_alive() -> bool:
            return True

        @staticmethod
        def join(timeout: float) -> None:
            assert timeout > 0

    class FakeEvent:
        was_set = False

        def set(self) -> None:
            self.was_set = True

    stop_event = FakeEvent()
    window.process = FakeProcess()
    window.stop_event = stop_event
    window._force_quit = True
    monkeypatch.setattr(
        "e_book_reader.gui.terminate_process_tree",
        lambda pid, *, grace_seconds: calls.append((pid, grace_seconds)),
    )
    event = QCloseEvent()

    window.closeEvent(event)

    assert event.isAccepted()
    assert stop_event.was_set is True
    assert calls == [(FakeProcess.pid, 0.5)]
    assert window.process is None


def test_remove_files_removes_every_selected_row(tmp_path: Path) -> None:
    _app, window, _store = _window(tmp_path)
    window.files = [tmp_path / "001.txt", tmp_path / "002.txt", tmp_path / "003.txt"]
    window._refresh_file_list()
    window.file_list.item(0).setSelected(True)
    window.file_list.item(2).setSelected(True)
    assert window.remove_files_button.isEnabled() is True

    window._remove_files()

    assert window.files == [tmp_path / "002.txt"]
    assert window.remove_files_button.isEnabled() is False
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
    assert window.start_button.text() == "Tiếp tục"
    assert window.start_button.isEnabled() is True
    assert window.add_files_button.isEnabled() is True
    assert window.add_folder_button.isEnabled() is True
    assert window.profile_combo.isEnabled() is True
    assert window.narrator_gender_combo.isEnabled() is True
    assert window.narrator_voice_combo.isEnabled() is True
    assert window.resource_combo.isEnabled() is True
    assert window.max_temp.isEnabled() is True
    assert window.settings_box.title() == "Thiết lập"
    assert window.settings_note.isHidden() is True
    window.file_list.item(0).setSelected(True)
    assert window.remove_files_button.isEnabled() is True

    fast_index = window.profile_combo.findData("fast")
    window.profile_combo.setCurrentIndex(fast_index)

    assert window.project_paths is None
    assert window.files == [source.resolve()]
    assert window.start_button.text() == "Bắt đầu"
    assert window.profile_combo.isEnabled() is True
    assert window.settings_box.title() == "Thiết lập"
    assert window.settings_note.isHidden() is False
    window.close()


def test_narrator_gender_filters_safe_voices_and_builds_matching_settings(tmp_path: Path) -> None:
    _app, window, _store = _window(tmp_path)
    female_index = window.narrator_gender_combo.findData("female")

    window.narrator_gender_combo.setCurrentIndex(female_index)

    available = {
        window.narrator_voice_combo.itemData(index)
        for index in range(window.narrator_voice_combo.count())
    }
    assert window.narrator_voice_combo.currentData() == "Ngọc Linh"
    assert available == {"Trúc Ly", "Đoan Trang", "Ngọc Linh", "Thục Đoan"}
    settings = window._build_settings()
    assert settings["voices"]["narrator_gender"] == "female"
    assert settings["voices"]["narrator_voice"] == "Ngọc Linh"
    window.close()


def test_removing_from_open_book_creates_draft_without_mutating_old_project(tmp_path: Path) -> None:
    _app = QApplication.instance() or QApplication([])
    sources = [tmp_path / "001.txt", tmp_path / "002.txt"]
    for index, source in enumerate(sources, 1):
        source.write_text(f"Chapter {index}.", encoding="utf-8")
    paths, _db, _settings = create_or_open_project(
        sources,
        tmp_path / "books",
        build_settings(),
        "Sách đang mở",
    )
    store = QSettings(str(tmp_path / "remove.ini"), QSettings.Format.IniFormat)
    store.setValue("recent_project", str(paths.root))
    window = MainWindow(settings_store=store, restore_recent=True)
    window.timer.stop()
    window.file_list.item(0).setSelected(True)

    window._remove_files()

    assert window.project_paths is None
    assert window.db is None
    assert window.files == [sources[1].resolve()]
    assert paths.db.exists()
    assert window.profile_combo.isEnabled() is True
    window.close()


def test_chapter_table_shows_every_stage_and_full_mp3_path(tmp_path: Path) -> None:
    _app = QApplication.instance() or QApplication([])
    source = tmp_path / "001.txt"
    source.write_text("Một chapter để kiểm tra đầy đủ các bước.", encoding="utf-8")
    paths, db, _settings = create_or_open_project(
        [source],
        tmp_path / "books",
        build_settings(),
        "Book có đường dẫn MP3 dài để kiểm tra",
    )
    chapter = db.list_chapters()[0]
    db.replace_chapter_segments(
        int(chapter["id"]),
        [{
            "stable_id": "chapter-progress-segment",
            "seq": 0,
            "text": "Một chapter để kiểm tra đầy đủ các bước.",
            "text_sha256": "text-sha",
            "kind_hint": "narration",
        }],
    )
    segment = db.list_segments()[0]
    db.update_analysis(int(segment["id"]), {"confidence": 0.99})
    wav = paths.chunks / "chapter_00001" / "0000000.wav"
    db.mark_generating(int(segment["id"]), seed=123)
    db.mark_signal_passed(
        int(segment["id"]),
        wav_path=wav,
        wav_sha256="wav-sha",
        duration=1.0,
        signal={"duration": 1.0},
    )
    db.mark_asr_result(
        int(segment["id"]),
        passed=True,
        transcript="Một chapter để kiểm tra đầy đủ các bước.",
        similarity=1.0,
        wer=0.0,
    )
    db.mark_verified(int(segment["id"]))
    output = Path(str(chapter["output_mp3"]))
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(b"ID3")
    db.update_chapter_status(int(chapter["id"]), "completed")
    store = QSettings(str(tmp_path / "progress.ini"), QSettings.Format.IniFormat)
    store.setValue("recent_project", str(paths.root))

    window = MainWindow(settings_store=store, restore_recent=True)
    window.timer.stop()

    assert window.chapter_table.item(0, 2).text() == "1/1"
    assert window.chapter_table.item(0, 3).text() == "1/1"
    assert window.chapter_table.item(0, 4).text() == "1/1"
    assert window.chapter_table.item(0, 5).text() == "Hoàn tất"
    assert window.chapter_table.item(0, 6).text() == str(output)
    assert window.chapter_table.item(0, 6).toolTip() == str(output)
    expected_width = window.chapter_table.fontMetrics().horizontalAdvance(str(output))
    assert window.chapter_table.columnWidth(6) >= expected_width
    window.close()


def test_double_clicking_empty_mp3_cell_does_not_open_explorer(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _app, window, _store = _window(tmp_path)
    window.chapter_table.setRowCount(1)
    window.chapter_table.setItem(0, 6, QTableWidgetItem(""))
    window.chapter_table.setCurrentCell(0, 6)
    opened: list[object] = []
    monkeypatch.setattr(
        "e_book_reader.gui.QDesktopServices.openUrl",
        lambda url: opened.append(url),
    )

    window._open_selected_mp3()

    assert opened == []
    window.close()


def test_repeated_clicks_on_long_mp3_cell_do_not_move_horizontal_scroll(tmp_path: Path) -> None:
    app, window, _store = _window(tmp_path)
    window.resize(850, 700)
    window.show()
    app.processEvents()
    table = window.chapter_table
    table.setRowCount(1)
    for column in range(table.columnCount()):
        table.setItem(0, column, QTableWidgetItem("x"))
    for column in range(6):
        table.setColumnWidth(column, 120)
    mp3_item = table.item(0, 6)
    mp3_item.setText("C:/" + "chapter-source/" * 40 + "chapter.mp3")
    mp3_item.setData(Qt.ItemDataRole.UserRole, "")
    table.setColumnWidth(6, 1000)
    app.processEvents()
    scrollbar = table.horizontalScrollBar()
    scrollbar.setValue(500)
    app.processEvents()
    before = scrollbar.value()
    rect = table.visualItemRect(mp3_item)
    click_position = rect.topLeft() + QPoint(20, rect.height() // 2)

    QTest.mouseClick(table.viewport(), Qt.MouseButton.LeftButton, pos=click_position)
    QTest.qWait(100)
    QTest.mouseClick(table.viewport(), Qt.MouseButton.LeftButton, pos=click_position)
    QTest.qWait(QApplication.doubleClickInterval() + 300)
    app.processEvents()

    assert table.hasAutoScroll() is False
    assert scrollbar.value() == before
    window.close()
