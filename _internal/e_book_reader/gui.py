from __future__ import annotations

import json
import multiprocessing as mp
import os
import sys
from pathlib import Path
from queue import Empty
from typing import Any

from PySide6.QtCore import QSettings, Qt, QTimer, QUrl
from PySide6.QtGui import QColor, QCloseEvent, QDesktopServices, QPalette
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from .config import build_settings, load_settings
from .database import ProjectDB
from .io_utils import discover_txt_files, natural_key
from .models import ProjectPaths
from .notifier import WindowsNotifier
from .process_utils import terminate_process_tree
from .project import create_or_open_project
from .worker import run_worker


WORKER_TERMINATION_GRACE_SECONDS = 0.5
TEXT_SELECTION_COLOR = "#0078D4"


CHAPTER_STATUS_LABELS = {
    "pending": "Chờ xử lý",
    "synthesizing": "Đang tạo audio",
    "verifying": "Đang kiểm tra",
    "completed": "Hoàn tất",
    "failed": "Lỗi",
    "warning": "Cần tạo lại",
}


class MainWindow(QMainWindow):
    def __init__(
        self,
        *,
        settings_store: QSettings | None = None,
        restore_recent: bool = True,
    ) -> None:
        super().__init__()
        self.setWindowTitle("E Book Reader")
        self.resize(1280, 820)
        self.setMinimumSize(900, 620)
        self.settings_store = settings_store or QSettings("OpenAI", "EBookReader")
        self.files: list[Path] = []
        self.project_paths: ProjectPaths | None = None
        self.db: ProjectDB | None = None
        self.process: mp.Process | None = None
        self.message_queue: Any = None
        self.pause_event: Any = None
        self.stop_event: Any = None
        self.received_finished = False
        self.was_user_stop = False
        self._chapter_snapshot: tuple[Any, ...] | None = None
        self.notifier = WindowsNotifier()
        self._build_ui()
        self._restore_ui(restore_recent=restore_recent)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._poll)
        self.timer.start(1000)

    def _build_ui(self) -> None:
        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(10)
        root.setStyleSheet(
            "QGroupBox { font-weight: 600; margin-top: 8px; padding-top: 10px; }"
            "QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; }"
            "QPushButton { min-height: 28px; padding: 2px 10px; }"
            "QPushButton:disabled { color: palette(mid); background-color: palette(dark); "
            "border: 1px solid palette(mid); }"
            "QLineEdit, QComboBox, QSpinBox { min-height: 27px; }"
        )
        book_box = QGroupBox("Book")
        top = QGridLayout(book_box)
        top.setColumnStretch(1, 1)
        self.title_edit = QLineEdit()
        self.title_edit.setPlaceholderText("Tên book; để trống sẽ lấy tên thư mục hoặc file")
        self.output_edit = QLineEdit()
        self.output_edit.setPlaceholderText("Thư mục chứa các book project")
        self.choose_output_button = QPushButton("Chọn nơi lưu")
        self.choose_output_button.clicked.connect(self._choose_output)
        self.add_files_button = QPushButton("Chọn nhiều TXT")
        self.add_files_button.clicked.connect(self._add_files)
        self.add_folder_button = QPushButton("Thêm thư mục")
        self.add_folder_button.clicked.connect(self._add_folder)
        self.remove_files_button = QPushButton("Xóa file đã chọn")
        self.remove_files_button.clicked.connect(self._remove_files)
        self.open_project_button = QPushButton("Mở project khác")
        self.open_project_button.clicked.connect(self._open_project)
        self.new_book_button = QPushButton("Book mới")
        self.new_book_button.clicked.connect(self._new_book)
        top.addWidget(QLabel("Tên book:"), 0, 0)
        top.addWidget(self.title_edit, 0, 1, 1, 3)
        top.addWidget(QLabel("Nơi lưu:"), 1, 0)
        top.addWidget(self.output_edit, 1, 1)
        top.addWidget(self.choose_output_button, 1, 2)
        top.addWidget(self.open_project_button, 1, 3)
        top.addWidget(self.new_book_button, 2, 0)
        top.addWidget(self.add_files_button, 2, 1)
        top.addWidget(self.add_folder_button, 2, 2)
        top.addWidget(self.remove_files_button, 2, 3)
        layout.addWidget(book_box)

        self.main_splitter = QSplitter(Qt.Vertical)
        self.main_splitter.setChildrenCollapsible(False)
        self.main_splitter.setHandleWidth(7)
        self.source_splitter = QSplitter(Qt.Horizontal)
        self.source_splitter.setChildrenCollapsible(False)
        self.source_splitter.setHandleWidth(7)
        files_box = QGroupBox("TXT thuộc cùng một book")
        files_layout = QVBoxLayout(files_box)
        self.file_list = QListWidget()
        self.file_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.file_list.setAlternatingRowColors(True)
        self._apply_item_view_palette(self.file_list)
        files_layout.addWidget(self.file_list)
        self.source_splitter.addWidget(files_box)

        self.settings_box = QGroupBox("Thiết lập cho book mới")
        form = QFormLayout(self.settings_box)
        self.profile_combo = QComboBox()
        self.profile_combo.addItem("Cân bằng", "balanced")
        self.profile_combo.addItem("Nhanh", "fast")
        self.profile_combo.addItem("Chất lượng cao", "high_quality")
        self.resource_combo = QComboBox()
        self.resource_combo.addItem("Tối đa an toàn + tự nhường foreground", "max_safe_adaptive_foreground")
        self.resource_combo.addItem("Luôn tối đa, chỉ giảm vì an toàn", "max_safe")
        self.max_temp = QSpinBox()
        self.max_temp.setRange(75, 92)
        self.max_temp.setValue(86)
        self.max_temp.setSuffix(" °C")
        self.keep_wav = QCheckBox("Giữ WAV segment đã kiểm tra (bắt buộc trong alpha để recovery an toàn)")
        self.keep_wav.setChecked(True)
        self.keep_wav.setEnabled(False)
        self.full_book = QCheckBox("Tạo thêm một MP3 toàn book")
        self.full_book.setChecked(False)
        self.full_book.setToolTip(
            "Tắt: mỗi file TXT tạo một MP3 chapter. Bật: tạo thêm một MP3 ghép toàn book."
        )
        form.addRow("Chất lượng:", self.profile_combo)
        form.addRow("Tài nguyên:", self.resource_combo)
        form.addRow("Ngưỡng GPU nóng:", self.max_temp)
        form.addRow(self.keep_wav)
        form.addRow(self.full_book)
        self.settings_note = QLabel("Sau khi bấm Bắt đầu, app không bật hộp thoại yêu cầu lựa chọn.")
        self.settings_note.setWordWrap(True)
        self.settings_note.setStyleSheet("color:#777")
        form.addRow(self.settings_note)
        self.source_splitter.addWidget(self.settings_box)
        self.source_splitter.setSizes([650, 520])
        self.main_splitter.addWidget(self.source_splitter)

        self.work_splitter = QSplitter(Qt.Horizontal)
        self.work_splitter.setChildrenCollapsible(False)
        self.work_splitter.setHandleWidth(7)
        chapters_box = QGroupBox("Tiến độ xử lý")
        chapters_layout = QVBoxLayout(chapters_box)
        progress_layout = QHBoxLayout()
        self.stage_label = QLabel("Sẵn sàng")
        self.stage_label.setMinimumWidth(220)
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setTextVisible(True)
        progress_layout.addWidget(self.stage_label)
        progress_layout.addWidget(self.progress, 1)
        chapters_layout.addLayout(progress_layout)
        self.chapter_table = QTableWidget(0, 5)
        self.chapter_table.setHorizontalHeaderLabels(
            ["#", "Chapter", "Giai đoạn", "Audio đã kiểm tra", "MP3"]
        )
        self.chapter_table.verticalHeader().setVisible(False)
        self.chapter_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.chapter_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.chapter_table.setAlternatingRowColors(True)
        self._apply_item_view_palette(self.chapter_table)
        header = self.chapter_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.Stretch)
        self.chapter_table.doubleClicked.connect(self._open_selected_mp3)
        chapters_layout.addWidget(self.chapter_table)
        self.work_splitter.addWidget(chapters_box)

        log_box = QGroupBox("Nhật ký")
        log_layout = QVBoxLayout(log_box)
        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setLineWrapMode(QTextEdit.NoWrap)
        log_layout.addWidget(self.log)
        self.work_splitter.addWidget(log_box)
        self.work_splitter.setSizes([820, 400])
        self.main_splitter.addWidget(self.work_splitter)
        self.main_splitter.setSizes([290, 460])
        layout.addWidget(self.main_splitter, 1)

        controls = QHBoxLayout()
        self.start_button = QPushButton("Bắt đầu")
        self.start_button.clicked.connect(self._start)
        self.pause_button = QPushButton("Tạm dừng")
        self.pause_button.clicked.connect(self._toggle_pause)
        self.pause_button.setEnabled(False)
        self.stop_button = QPushButton("Dừng")
        self.stop_button.setToolTip("Dừng xử lý. Phần chưa commit sẽ được kiểm tra và làm lại khi tiếp tục.")
        self.stop_button.clicked.connect(self._stop)
        self.stop_button.setEnabled(False)
        self.open_folder_button = QPushButton("Mở thư mục project")
        self.open_folder_button.clicked.connect(self._open_project_folder)
        controls.addWidget(self.start_button)
        controls.addWidget(self.pause_button)
        controls.addWidget(self.stop_button)
        controls.addStretch(1)
        controls.addWidget(self.open_folder_button)
        layout.addLayout(controls)

    @staticmethod
    def _apply_item_view_palette(view: QAbstractItemView) -> None:
        palette = view.palette()
        base = palette.color(QPalette.ColorRole.Base)
        alternate = base.lighter(106) if base.lightness() < 128 else base.darker(103)
        palette.setColor(QPalette.ColorRole.AlternateBase, alternate)
        palette.setColor(QPalette.ColorRole.Highlight, QColor(TEXT_SELECTION_COLOR))
        palette.setColor(QPalette.ColorRole.HighlightedText, QColor(Qt.GlobalColor.white))
        view.setPalette(palette)

    def _restore_ui(self, *, restore_recent: bool) -> None:
        self.output_edit.setText(self.settings_store.value("output", str(Path.home() / "Audiobooks"), str))
        self.max_temp.setValue(self.settings_store.value("max_temp", 86, int))
        self._set_project_selected(False)
        for key, splitter in (
            ("splitter_main", self.main_splitter),
            ("splitter_source", self.source_splitter),
            ("splitter_work", self.work_splitter),
        ):
            state = self.settings_store.value(key)
            if state is not None:
                splitter.restoreState(state)
        if restore_recent:
            candidate = self._recent_project_candidate()
            if candidate is not None:
                try:
                    self._load_project(candidate, announce=False)
                except Exception as exc:  # noqa: BLE001
                    self._append_log(f"Không thể tự mở project gần đây: {exc}")

    def _save_ui(self) -> None:
        self.settings_store.setValue("output", self.output_edit.text().strip())
        self.settings_store.setValue("max_temp", self.max_temp.value())
        self.settings_store.setValue("splitter_main", self.main_splitter.saveState())
        self.settings_store.setValue("splitter_source", self.source_splitter.saveState())
        self.settings_store.setValue("splitter_work", self.work_splitter.saveState())
        self.settings_store.sync()

    def _recent_project_candidate(self) -> Path | None:
        saved = self.settings_store.value("recent_project", "", str).strip()
        if saved:
            selected = Path(saved).expanduser()
            if (selected / "project.sqlite3").is_file() and (selected / "book_settings.json").is_file():
                return selected.resolve()
        output = Path(self.output_edit.text().strip()).expanduser()
        if not output.is_dir():
            return None
        try:
            candidates = [
                path
                for path in output.iterdir()
                if path.is_dir()
                and (path / "project.sqlite3").is_file()
                and (path / "book_settings.json").is_file()
            ]
        except OSError:
            return None
        if not candidates:
            return None
        return max(candidates, key=lambda path: (path / "project.sqlite3").stat().st_mtime).resolve()

    def _remember_project(self, path: Path) -> None:
        self.settings_store.setValue("recent_project", str(path.resolve()))
        self.settings_store.sync()

    def _append_log(self, text: str) -> None:
        self.log.append(text)
        scrollbar = self.log.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def _show_progress(self, label: str, done: int | None = None, total: int | None = None) -> None:
        self.stage_label.setText(label)
        if done is None or total is None or total <= 0:
            self.progress.setRange(0, 0)
            return
        self.progress.setRange(0, total)
        self.progress.setValue(max(0, min(done, total)))
        self.progress.setFormat("%v/%m — %p%")

    def _set_project_selected(self, selected: bool) -> None:
        running = bool(self.process and self.process.is_alive())
        self.title_edit.setReadOnly(selected)
        self.output_edit.setReadOnly(selected)
        self.choose_output_button.setEnabled(not selected and not running)
        self.add_files_button.setEnabled(not running)
        self.add_folder_button.setEnabled(not running)
        self.remove_files_button.setEnabled(not selected and not running)
        self.new_book_button.setEnabled(not running)
        self.open_project_button.setEnabled(not running)
        self.profile_combo.setEnabled(not selected and not running)
        self.resource_combo.setEnabled(not selected and not running)
        self.max_temp.setEnabled(not selected and not running)
        self.full_book.setEnabled(not selected and not running)
        self.open_folder_button.setEnabled(selected)
        if selected:
            self.settings_box.setTitle("Thiết lập đã khóa của project")
            self.settings_note.setText(
                "Project đã bắt đầu nên thiết lập được giữ nguyên khi Tiếp tục. "
                "Chọn Book mới, nhiều TXT hoặc thư mục để tạo book với thiết lập khác."
            )
        else:
            self.settings_box.setTitle("Thiết lập cho book mới")
            self.settings_note.setText("Sau khi bấm Bắt đầu, app không bật hộp thoại yêu cầu lựa chọn.")
        self._update_start_button()

    def _update_start_button(self) -> None:
        self.start_button.setText("Tiếp tục" if self.project_paths is not None else "Bắt đầu")

    def _merge_input_files(self, paths: list[Path]) -> int:
        if paths and self.project_paths is not None:
            self._new_book()
        existing = {str(path).casefold() for path in self.files}
        added = 0
        for path in paths:
            resolved = path.resolve()
            key = str(resolved).casefold()
            if key not in existing:
                self.files.append(resolved)
                existing.add(key)
                added += 1
        self.files.sort(key=lambda path: natural_key(path.name))
        self._refresh_file_list()
        return added

    def _add_files(self) -> None:
        start_dir = self.settings_store.value("input_folder", "", str)
        names, _ = QFileDialog.getOpenFileNames(
            self,
            "Chọn TXT của cùng một book",
            start_dir,
            "Text files (*.txt)",
        )
        paths = [Path(name) for name in names]
        if paths:
            self.settings_store.setValue("input_folder", str(paths[0].resolve().parent))
        self._merge_input_files(paths)

    def _add_folder(self) -> None:
        start_dir = self.settings_store.value("input_folder", "", str)
        directory = QFileDialog.getExistingDirectory(self, "Chọn folder chứa chapter TXT", start_dir)
        if not directory:
            return
        folder = Path(directory).resolve()
        self.settings_store.setValue("input_folder", str(folder))
        try:
            discovered = discover_txt_files(folder)
        except OSError as exc:
            QMessageBox.critical(self, "Không thể đọc folder", str(exc))
            return
        if not discovered:
            QMessageBox.information(
                self,
                "Không tìm thấy TXT",
                "Folder không có file .txt trực tiếp bên trong. Tool không tự quét thư mục con.",
            )
            return
        added = self._merge_input_files(discovered)
        if not self.title_edit.text().strip():
            self.title_edit.setText(folder.name)
        self._append_log(
            f"Đã tìm thấy {len(discovered)} file TXT trong folder; thêm mới {added} file. "
            "Không quét thư mục con."
        )

    def _remove_files(self) -> None:
        if self.process and self.process.is_alive():
            return
        selected = {item.text() for item in self.file_list.selectedItems()}
        self.files = [path for path in self.files if str(path) not in selected]
        self._refresh_file_list()

    def _refresh_file_list(self) -> None:
        self.file_list.clear()
        self.file_list.addItems([str(path) for path in self.files])

    def _choose_output(self) -> None:
        directory = QFileDialog.getExistingDirectory(self, "Chọn thư mục đầu ra", self.output_edit.text())
        if directory:
            self.output_edit.setText(directory)

    def _build_settings(self) -> dict[str, Any]:
        profile = str(self.profile_combo.currentData())
        overrides = {
            "resources": {
                "mode": str(self.resource_combo.currentData()),
                "max_gpu_temp_c": self.max_temp.value(),
                "resume_gpu_temp_c": max(60, self.max_temp.value() - 6),
                "critical_gpu_temp_c": min(98, self.max_temp.value() + 5),
            },
            "audio": {
                "keep_verified_wav": self.keep_wav.isChecked(),
                "combine_full_book": self.full_book.isChecked(),
            },
        }
        return build_settings(profile, overrides)

    def _start(self) -> None:
        if self.process and self.process.is_alive():
            return
        self._dispose_ipc()
        if self.project_paths is None and not self.files:
            QMessageBox.warning(self, "Thiếu đầu vào", "Hãy chọn ít nhất một file TXT hoặc một folder chứa TXT.")
            return
        try:
            if self.project_paths is None:
                output = Path(self.output_edit.text().strip()).expanduser()
                paths, db, used_settings = create_or_open_project(
                    self.files,
                    output,
                    self._build_settings(),
                    self.title_edit.text().strip() or None,
                )
                self.project_paths, self.db = paths, db
                self._remember_project(paths.root)
                self._set_project_selected(True)
                if used_settings["quality_profile"] != str(self.profile_combo.currentData()):
                    self._append_log("Project cũ được mở lại bằng settings đã khóa từ lần chạy đầu.")
            assert self.project_paths is not None
            self._save_ui()
            ctx = mp.get_context("spawn")
            self.message_queue = ctx.Queue()
            self.pause_event = ctx.Event()
            self.stop_event = ctx.Event()
            self.received_finished = False
            self.was_user_stop = False
            self.process = ctx.Process(
                target=run_worker,
                args=(
                    str(self.project_paths.root),
                    self.message_queue,
                    self.pause_event,
                    self.stop_event,
                    os.getpid(),
                ),
                daemon=False,
            )
            self.process.start()
            self._running_controls(True)
            self._append_log("Worker đã bắt đầu. Mọi phần hoàn tất đều được lưu để có thể tiếp tục an toàn.")
            self._refresh_chapters()
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Không thể bắt đầu", str(exc))

    def _toggle_pause(self) -> None:
        if not self.pause_event:
            return
        if self.pause_event.is_set():
            self.pause_event.clear()
            self.pause_button.setText("Tạm dừng")
        else:
            self.pause_event.set()
            self.pause_button.setText("Chạy tiếp")

    def _stop(self) -> None:
        if self.stop_event:
            self.was_user_stop = True
            self.stop_event.set()
            self.stop_button.setEnabled(False)
            self.pause_button.setEnabled(False)
            self._show_progress("Đang dừng…")
            self._append_log("Đang dừng. Phần chưa commit sẽ được recovery kiểm tra khi tiếp tục.")

    def _running_controls(self, running: bool) -> None:
        self.start_button.setEnabled(not running)
        self.pause_button.setEnabled(running)
        self.stop_button.setEnabled(running)
        self._set_project_selected(self.project_paths is not None)
        if not running:
            self.pause_button.setText("Tạm dừng")
            self._update_start_button()

    def _terminate_worker_for_exit(self) -> None:
        process = self.process
        if process is None or not process.is_alive():
            return
        self.was_user_stop = True
        if self.stop_event is not None:
            self.stop_event.set()
        terminate_process_tree(
            process.pid,
            grace_seconds=WORKER_TERMINATION_GRACE_SECONDS,
        )
        try:
            process.join(timeout=WORKER_TERMINATION_GRACE_SECONDS)
        except (AssertionError, OSError):
            pass
        self.process = None
        self._dispose_ipc()

    def _dispose_ipc(self) -> None:
        if self.process is not None and not self.process.is_alive():
            try:
                self.process.join(timeout=0.2)
            except (AssertionError, OSError):
                pass
            self.process = None
        if self.process is not None:
            return
        if self.message_queue is not None:
            try:
                self.message_queue.close()
                self.message_queue.join_thread()
            except (OSError, ValueError):
                pass
        self.message_queue = None
        self.pause_event = None
        self.stop_event = None

    def _open_project(self) -> None:
        if self.process and self.process.is_alive():
            return
        directory = QFileDialog.getExistingDirectory(self, "Chọn thư mục book project", self.output_edit.text())
        if not directory:
            return
        try:
            self._load_project(Path(directory).resolve(), announce=True)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Không mở được project", str(exc))

    def _load_project(self, selected: Path, *, announce: bool) -> None:
        if not (selected / "project.sqlite3").is_file() or not (selected / "book_settings.json").is_file():
            raise ValueError("Thư mục không có project.sqlite3 và book_settings.json")
        paths = ProjectPaths.build(selected.resolve())
        db = ProjectDB(paths.db)
        chapters = db.list_chapters()
        try:
            locked_settings = load_settings(paths.settings)
        except (KeyError, TypeError, ValueError):
            locked_settings = json.loads(str(db.book()["settings_json"]))
        self.project_paths = paths
        self.db = db
        self.files = [Path(str(row["input_path"])) for row in chapters]
        self.title_edit.setText(str(db.book()["title"]))
        self.output_edit.setText(str(paths.root.parent))
        self._apply_locked_settings(locked_settings)
        self._chapter_snapshot = None
        self._refresh_file_list()
        self._set_project_selected(True)
        self._remember_project(paths.root)
        self._refresh_chapters()
        if announce:
            self._append_log("Đã mở project. Khi tiếp tục sẽ dùng nguyên settings và voice mapping đã khóa.")

    def _new_book(self) -> None:
        if self.process and self.process.is_alive():
            return
        self.project_paths = None
        self.db = None
        self.files = []
        self.title_edit.clear()
        self.file_list.clear()
        self.chapter_table.setRowCount(0)
        self._show_progress("Sẵn sàng", 0, 100)
        self._chapter_snapshot = None
        self._set_project_selected(False)
        self._append_log("Đã chuyển sang book mới; project cũ vẫn nguyên vẹn trên ổ đĩa.")

    def _apply_locked_settings(self, settings: dict[str, Any]) -> None:
        profile_index = self.profile_combo.findData(str(settings.get("quality_profile", "balanced")))
        if profile_index >= 0:
            self.profile_combo.setCurrentIndex(profile_index)
        resources = settings.get("resources", {})
        resource_index = self.resource_combo.findData(str(resources.get("mode", "")))
        if resource_index >= 0:
            self.resource_combo.setCurrentIndex(resource_index)
        self.max_temp.setValue(int(resources.get("max_gpu_temp_c", 86)))
        audio = settings.get("audio", {})
        self.keep_wav.setChecked(bool(audio.get("keep_verified_wav", True)))
        self.full_book.setChecked(bool(audio.get("combine_full_book", False)))

    def _refresh_chapters(self) -> None:
        if not self.db:
            return
        try:
            chapters = self.db.list_chapters()
            book = self.db.book()
        except Exception:
            return
        snapshot = tuple(
            (
                int(row["id"]),
                str(row["status"]),
                int(row["verified_segments"]),
                int(row["warning_segments"]),
                int(row["total_segments"]),
                Path(str(row["output_mp3"])).exists(),
            )
            for row in chapters
        )
        snapshot += ((str(book["status"]), str(book["stage"])),)
        if snapshot == self._chapter_snapshot:
            return
        self._chapter_snapshot = snapshot
        self.chapter_table.setRowCount(len(chapters))
        done = 0
        for index, row in enumerate(chapters):
            self.chapter_table.setItem(index, 0, QTableWidgetItem(str(row["chapter_index"])))
            self.chapter_table.setItem(index, 1, QTableWidgetItem(str(row["title"])))
            status = str(row["status"])
            self.chapter_table.setItem(
                index,
                2,
                QTableWidgetItem(CHAPTER_STATUS_LABELS.get(status, status)),
            )
            accepted = int(row["verified_segments"]) + int(row["warning_segments"])
            total = int(row["total_segments"])
            self.chapter_table.setItem(index, 3, QTableWidgetItem(f"{accepted}/{total}"))
            output = str(row["output_mp3"])
            published = str(row["status"]) == "completed" and Path(output).exists()
            item = QTableWidgetItem(output if published else "")
            item.setData(Qt.UserRole, output if published else "")
            self.chapter_table.setItem(index, 4, item)
            if status == "completed":
                done += 1
        running = bool(self.process and self.process.is_alive())
        if not running:
            book_status = str(book["status"])
            if book_status == "completed":
                self._show_progress("Đã hoàn tất", len(chapters), len(chapters))
            elif book_status == "stopped":
                self._show_progress("Đã dừng", done, len(chapters))
            elif book_status == "error":
                self._show_progress("Đã dừng vì lỗi", done, len(chapters))
            else:
                self._show_progress("Project sẵn sàng", done, len(chapters))

    def _poll(self) -> None:
        if self.message_queue:
            while True:
                try:
                    message = self.message_queue.get_nowait()
                except Empty:
                    break
                kind = message.get("kind")
                if kind == "log":
                    self._append_log(str(message.get("text", "")))
                elif kind == "state":
                    text = str(message.get("text", ""))
                    self._append_log(text)
                    self._show_progress(text)
                elif kind == "analysis_progress":
                    done, total = int(message.get("done", 0)), int(message.get("total", 0))
                    self._show_progress("Phân tích nội dung và nhân vật", done, total)
                elif kind == "work_progress":
                    done = message.get("done")
                    total = message.get("total")
                    self._show_progress(
                        str(message.get("label", "Đang xử lý")),
                        int(done) if done is not None else None,
                        int(total) if total is not None else None,
                    )
                elif kind == "chapter_progress":
                    done, total = int(message.get("done", 0)), int(message.get("total", 0))
                    self._show_progress("Hoàn tất chapter", done, total)
                elif kind == "chapter_completed":
                    self._append_log(f"Có thể nghe ngay: {message.get('path')}")
                elif kind == "finished":
                    self.received_finished = True
                    self._append_log(str(message.get("text", "")))
                    self._running_controls(False)
                    if message.get("stopped"):
                        self._show_progress("Đã dừng", 0, 100)
                    elif not message.get("ok", False):
                        self._show_progress("Đã dừng vì lỗi", 0, 100)
        self._refresh_chapters()
        if self.process and not self.process.is_alive():
            exitcode = self.process.exitcode
            if not self.received_finished and not self.was_user_stop:
                title = str(self.db.book()["title"]) if self.db else "Audiobook"
                root = self.project_paths.root if self.project_paths else Path.cwd()
                notify = True
                if self.project_paths is not None:
                    try:
                        notify = bool(
                            load_settings(self.project_paths.settings)["safety"].get(
                                "notify_on_critical_stop", True
                            )
                        )
                    except Exception:
                        notify = True
                if notify:
                    self.notifier.critical_stop(
                        title, f"Worker thoát bất ngờ, exit code {exitcode}", root
                    )
                self._append_log(f"Worker thoát bất ngờ, exit code {exitcode}. Lần sau recovery sẽ kiểm tra checkpoint.")
            self._running_controls(False)
            self._dispose_ipc()

    def _open_selected_mp3(self) -> None:
        row = self.chapter_table.currentRow()
        if row < 0:
            return
        item = self.chapter_table.item(row, 4)
        if item:
            path = Path(str(item.data(Qt.UserRole) or ""))
            if path.exists():
                QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def _open_project_folder(self) -> None:
        if self.project_paths and self.project_paths.root.exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.project_paths.root)))

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        self._save_ui()
        self._terminate_worker_for_exit()
        event.accept()


def run_gui() -> int:
    mp.freeze_support()
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    return app.exec()
