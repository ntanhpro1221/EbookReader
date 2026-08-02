from __future__ import annotations

import json
import multiprocessing as mp
import os
import sys
from datetime import datetime
from pathlib import Path
from queue import Empty, Full
from typing import Any

from PySide6.QtCore import QSize, QSettings, QSignalBlocker, Qt, QTimer, QUrl
from PySide6.QtGui import QAction, QCloseEvent, QDesktopServices, QIcon, QPainter, QPalette, QPixmap
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
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
    QMenu,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QSplitter,
    QStyle,
    QStyleOption,
    QSystemTrayIcon,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QToolButton,
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
from .voice_catalog import (
    DEFAULT_NARRATOR_BY_GENDER,
    GENDER_FEMALE,
    GENDER_MALE,
    REGION_CENTRAL,
    REGION_NORTH,
    REGION_SOUTH,
    VOICE_PREVIEW_FILENAMES,
    narrator_presets,
    preset_by_name,
)
from .worker import run_worker


WORKER_TERMINATION_GRACE_SECONDS = 0.5
APP_NAME = "Ebook Reader"
APP_USER_MODEL_ID = "EbookReader.Desktop"
INSTANCE_SERVER_NAME = f"{APP_USER_MODEL_ID}.SingleInstance"
INSTANCE_ACTIVATE_MESSAGE = b"activate"
INSTANCE_CONNECT_TIMEOUT_MS = 250
STARTUP_READY_FILE_ENV = "EBOOK_READER_READY_FILE"
APP_ASSET_DIR = Path(__file__).resolve().parent / "assets"
APP_ICON_PATH = APP_ASSET_DIR / ("ebook_reader.ico" if os.name == "nt" else "ebook_reader.png")
VOICE_PREVIEW_DIR = APP_ASSET_DIR / "voice_previews"
CHAPTER_TABLE_HEADERS = (
    "#",
    "Chapter",
    "Phân tích",
    "Tạo audio",
    "Kiểm tra",
    "Giai đoạn",
    "MP3",
)
CHAPTER_TABLE_DEFAULT_WIDTHS = (45, 160, 110, 115, 130, 155, 480)
MP3_COLUMN = 6
DEFAULT_QUALITY_PROFILE = "balanced"
DEFAULT_NARRATOR_FILTER = ""
DEFAULT_NARRATOR_VOICE = DEFAULT_NARRATOR_BY_GENDER[GENDER_MALE]
VOICE_FOLDOUT_LABEL = "Giọng kể chuyện:"
VOICE_FOLDOUT_ICON_SIZE = 12
VOICE_CHILD_INDENT_SAMPLE = "oooo"


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
        self.setWindowTitle(APP_NAME)
        self.resize(1280, 820)
        self.setMinimumSize(900, 620)
        self.settings_store = settings_store or QSettings("OpenAI", "EbookReader")
        self.files: list[Path] = []
        self.project_paths: ProjectPaths | None = None
        self.db: ProjectDB | None = None
        self.process: mp.Process | None = None
        self.message_queue: Any = None
        self.resource_settings_queue: Any = None
        self.pause_event: Any = None
        self.stop_event: Any = None
        self.received_finished = False
        self.was_user_stop = False
        self._force_quit = False
        self._tray_message_shown = False
        self._applying_locked_settings = False
        self._chapter_snapshot: tuple[Any, ...] | None = None
        self.notifier = WindowsNotifier()
        self.preview_audio_output = QAudioOutput(self)
        self.preview_audio_output.setVolume(0.8)
        self.preview_player = QMediaPlayer(self)
        self.preview_player.setAudioOutput(self.preview_audio_output)
        self._build_ui()
        self._setup_tray()
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
        self.book_box = QGroupBox("Sách")
        top = QGridLayout(self.book_box)
        top.setColumnStretch(1, 1)
        self.title_edit = QLineEdit()
        self.title_edit.setPlaceholderText("Tên sách; để trống sẽ lấy tên thư mục hoặc file")
        self.output_edit = QLineEdit()
        self.output_edit.setPlaceholderText("Thư mục chứa các sách")
        self.choose_output_button = QPushButton("Chọn nơi lưu")
        self.choose_output_button.clicked.connect(self._choose_output)
        self.add_files_button = QPushButton("Thêm file")
        self.add_files_button.clicked.connect(self._add_files)
        self.add_folder_button = QPushButton("Thêm thư mục")
        self.add_folder_button.clicked.connect(self._add_folder)
        self.remove_files_button = QPushButton("Xóa file đã chọn")
        self.remove_files_button.clicked.connect(self._remove_files)
        self.open_project_button = QPushButton("Mở sách khác")
        self.open_project_button.clicked.connect(self._open_project)
        self.new_book_button = QPushButton("Sách mới")
        self.new_book_button.clicked.connect(self._new_book)
        top.addWidget(QLabel("Tên sách:"), 0, 0)
        top.addWidget(self.title_edit, 0, 1, 1, 2)
        top.addWidget(self.open_project_button, 0, 3)
        top.addWidget(QLabel("Nơi lưu:"), 1, 0)
        top.addWidget(self.output_edit, 1, 1, 1, 2)
        top.addWidget(self.choose_output_button, 1, 3)
        self.input_actions = QHBoxLayout()
        self.input_actions.setSpacing(8)
        self.input_actions.addWidget(self.new_book_button, 1)
        self.input_actions.addWidget(self.add_files_button, 1)
        self.input_actions.addWidget(self.add_folder_button, 1)
        self.input_actions.addWidget(self.remove_files_button, 1)
        top.addLayout(self.input_actions, 2, 0, 1, 4)
        layout.addWidget(self.book_box)

        self.main_splitter = QSplitter(Qt.Vertical)
        self.main_splitter.setChildrenCollapsible(False)
        self.main_splitter.setHandleWidth(7)
        self.source_splitter = QSplitter(Qt.Horizontal)
        self.source_splitter.setChildrenCollapsible(False)
        self.source_splitter.setHandleWidth(7)
        self.files_box = QGroupBox("Chapter nguồn")
        files_layout = QVBoxLayout(self.files_box)
        self.file_list = QListWidget()
        self.file_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.file_list.itemSelectionChanged.connect(self._update_remove_files_button)
        self.file_list.setAlternatingRowColors(True)
        self._apply_item_view_palette(self.file_list)
        files_layout.addWidget(self.file_list)
        self.source_splitter.addWidget(self.files_box)

        self.settings_box = QGroupBox("Thiết lập")
        settings_layout = QVBoxLayout(self.settings_box)
        settings_layout.setSpacing(8)
        self.book_settings_box = QGroupBox("Thiết lập sách")
        book_form = QFormLayout(self.book_settings_box)
        self.profile_combo = QComboBox()
        self.profile_combo.addItem("Cân bằng", "balanced")
        self.profile_combo.addItem("Nhanh", "fast")
        self.profile_combo.addItem("Chất lượng cao", "high_quality")
        self.narrator_gender_combo = QComboBox()
        self.narrator_gender_combo.addItem("Mọi giới tính", "")
        self.narrator_gender_combo.addItem("Nam", GENDER_MALE)
        self.narrator_gender_combo.addItem("Nữ", GENDER_FEMALE)
        self.narrator_gender_combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        self.narrator_gender_combo.setAccessibleName("Lọc giọng theo giới tính")
        self.narrator_region_combo = QComboBox()
        self.narrator_region_combo.addItem("Mọi miền", "")
        self.narrator_region_combo.addItem(REGION_NORTH, REGION_NORTH)
        self.narrator_region_combo.addItem(REGION_SOUTH, REGION_SOUTH)
        self.narrator_region_combo.addItem(REGION_CENTRAL, REGION_CENTRAL)
        self.narrator_region_combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        self.narrator_region_combo.setAccessibleName("Lọc giọng theo miền")
        self.narrator_voice_combo = QComboBox()
        self._populate_narrator_voices(DEFAULT_NARRATOR_BY_GENDER[GENDER_MALE])
        self.preview_button = QPushButton("Nghe thử")
        self.preview_button.clicked.connect(self._play_narrator_preview)
        self.voice_foldout_button = QToolButton()
        self.voice_foldout_button.setText(VOICE_FOLDOUT_LABEL)
        self.voice_foldout_button.setCheckable(True)
        self.voice_foldout_button.setChecked(True)
        self.voice_foldout_button.setArrowType(Qt.ArrowType.NoArrow)
        self.voice_foldout_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.voice_foldout_button.setIconSize(
            QSize(VOICE_FOLDOUT_ICON_SIZE, VOICE_FOLDOUT_ICON_SIZE)
        )
        self.voice_foldout_button.setIcon(self._voice_foldout_icon(expanded=True))
        self.voice_foldout_button.setAutoRaise(True)
        self.voice_foldout_button.setStyleSheet(
            "QToolButton { border: none; background: transparent; padding: 0; }"
        )
        self.voice_tools_widget = QWidget()
        self.voice_tools_layout = QFormLayout(self.voice_tools_widget)
        voice_child_indent = self.fontMetrics().horizontalAdvance(VOICE_CHILD_INDENT_SAMPLE)
        self.voice_tools_layout.setContentsMargins(voice_child_indent, 0, 0, 0)
        self.voice_tools_layout.setHorizontalSpacing(8)
        self.voice_tools_layout.setVerticalSpacing(6)
        self.voice_gender_label = QLabel("Giới tính:")
        self.voice_region_label = QLabel("Miền:")
        self.voice_preview_label = QLabel("Nghe thử:")
        voice_child_label_width = self.voice_foldout_button.sizeHint().width()
        for label in (
            self.voice_gender_label,
            self.voice_region_label,
            self.voice_preview_label,
        ):
            label.setMinimumWidth(voice_child_label_width)
        self.voice_tools_layout.addRow(self.voice_preview_label, self.preview_button)
        self.voice_tools_layout.addRow(self.voice_gender_label, self.narrator_gender_combo)
        self.voice_tools_layout.addRow(self.voice_region_label, self.narrator_region_combo)
        self.voice_foldout_button.toggled.connect(self._set_voice_options_expanded)
        self.narrator_voice_combo.currentIndexChanged.connect(self._narrator_voice_changed)

        book_form.addRow("Chất lượng:", self.profile_combo)
        book_form.addRow(self.voice_foldout_button, self.narrator_voice_combo)
        book_form.setAlignment(
            self.voice_foldout_button,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
        )
        book_form.addRow(self.voice_tools_widget)
        settings_layout.addWidget(self.book_settings_box)

        self.global_settings_box = QGroupBox("Thiết lập chung")
        global_form = QFormLayout(self.global_settings_box)
        self.resource_combo = QComboBox()
        self.resource_combo.addItem("Tối đa an toàn + tự nhường foreground", "max_safe_adaptive_foreground")
        self.resource_combo.addItem("Luôn tối đa, chỉ giảm vì an toàn", "max_safe")
        self.max_temp = QSpinBox()
        self.max_temp.setRange(75, 92)
        self.max_temp.setValue(86)
        self.max_temp.setSuffix(" °C")
        self.narrator_gender_combo.currentIndexChanged.connect(self._narrator_filter_changed)
        self.narrator_region_combo.currentIndexChanged.connect(self._narrator_filter_changed)
        self.resource_combo.currentIndexChanged.connect(self._global_settings_edited)
        self.max_temp.valueChanged.connect(self._global_settings_edited)
        global_form.addRow("Tài nguyên:", self.resource_combo)
        global_form.addRow("Ngưỡng GPU nóng:", self.max_temp)
        settings_layout.addWidget(self.global_settings_box)
        settings_layout.addStretch(1)
        locked_tip = "Được lưu cùng sách và khóa sau khi sách đã bắt đầu."
        for control in (
            self.profile_combo,
            self.narrator_voice_combo,
            self.narrator_gender_combo,
            self.narrator_region_combo,
        ):
            control.setToolTip(locked_tip)
        global_tip = "Thiết lập global; có thể đổi cho mọi sách, kể cả khi worker đang chạy."
        self.resource_combo.setToolTip(global_tip)
        self.max_temp.setToolTip(global_tip)
        self.source_splitter.addWidget(self.settings_box)
        self.source_splitter.setSizes([650, 520])
        self.main_splitter.addWidget(self.source_splitter)

        self.work_splitter = QSplitter(Qt.Horizontal)
        self.work_splitter.setChildrenCollapsible(False)
        self.work_splitter.setHandleWidth(7)
        self.chapters_box = QGroupBox("Tiến độ")
        chapters_layout = QVBoxLayout(self.chapters_box)
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
        self.chapter_table = QTableWidget(0, len(CHAPTER_TABLE_HEADERS))
        self.chapter_table.setHorizontalHeaderLabels(CHAPTER_TABLE_HEADERS)
        self.chapter_table.verticalHeader().setVisible(False)
        self.chapter_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.chapter_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.chapter_table.setAlternatingRowColors(True)
        self.chapter_table.setTextElideMode(Qt.TextElideMode.ElideNone)
        self.chapter_table.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.chapter_table.setAutoScroll(False)
        self._apply_item_view_palette(self.chapter_table)
        header = self.chapter_table.horizontalHeader()
        header.setSectionsMovable(True)
        header.setMinimumSectionSize(40)
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        for column, width in enumerate(CHAPTER_TABLE_DEFAULT_WIDTHS):
            self.chapter_table.setColumnWidth(column, width)
        self._mp3_column_initialized = False
        self.chapter_table.doubleClicked.connect(self._open_selected_mp3)
        chapters_layout.addWidget(self.chapter_table)
        self.work_splitter.addWidget(self.chapters_box)

        self.log_box = QGroupBox("Log")
        log_layout = QVBoxLayout(self.log_box)
        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setLineWrapMode(QTextEdit.NoWrap)
        log_layout.addWidget(self.log)
        self._match_item_selection_to_log()
        self.work_splitter.addWidget(self.log_box)
        self.work_splitter.setSizes([820, 400])
        self.main_splitter.addWidget(self.work_splitter)
        self.main_splitter.setSizes([290, 460])
        layout.addWidget(self.main_splitter, 1)

        controls = QHBoxLayout()
        self.start_button = QPushButton("Bắt đầu")
        self.start_button.clicked.connect(self._handle_primary_action)
        self.stop_button = QPushButton("Dừng")
        self.stop_button.setToolTip("Dừng xử lý. Phần chưa commit sẽ được kiểm tra và làm lại khi tiếp tục.")
        self.stop_button.clicked.connect(self._stop)
        self.stop_button.setEnabled(False)
        self.open_folder_button = QPushButton("Hiển thị sách trong Explorer")
        self.open_folder_button.clicked.connect(self._open_project_folder)
        controls.addWidget(self.start_button)
        controls.addWidget(self.stop_button)
        controls.addStretch(1)
        controls.addWidget(self.open_folder_button)
        layout.addLayout(controls)
        self.narrator_voice_combo.ensurePolished()
        self.voice_foldout_button.setMinimumHeight(self.narrator_voice_combo.sizeHint().height())

    def _setup_tray(self) -> None:
        icon = QIcon(str(APP_ICON_PATH))
        self.setWindowIcon(icon)
        self.tray_icon = QSystemTrayIcon(icon, self)
        self.tray_icon.setToolTip(APP_NAME)
        self.tray_menu = QMenu(self)
        self.show_action = QAction(f"Hiện {APP_NAME}", self)
        self.show_action.triggered.connect(self._show_from_tray)
        self.hide_action = QAction("Ẩn xuống system tray", self)
        self.hide_action.triggered.connect(self._hide_to_tray)
        self.quit_action = QAction("Thoát hoàn toàn", self)
        self.quit_action.triggered.connect(self._quit_from_tray)
        self.tray_menu.addAction(self.show_action)
        self.tray_menu.addAction(self.hide_action)
        self.tray_menu.addSeparator()
        self.tray_menu.addAction(self.quit_action)
        self.tray_icon.setContextMenu(self.tray_menu)
        self.tray_icon.activated.connect(self._handle_tray_activation)
        self._tray_available = QSystemTrayIcon.isSystemTrayAvailable()
        if self._tray_available:
            self.tray_icon.show()

    def _show_from_tray(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def _hide_to_tray(self) -> None:
        if self._tray_available:
            self.hide()

    def _handle_tray_activation(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason in {
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick,
        }:
            self._show_from_tray()

    def _quit_from_tray(self) -> None:
        self._force_quit = True
        self.close()
        app = QApplication.instance()
        if app is not None:
            app.quit()

    @staticmethod
    def _apply_item_view_palette(view: QAbstractItemView) -> None:
        palette = view.palette()
        base = palette.color(QPalette.ColorRole.Base)
        alternate = base.darker(115 if base.lightness() < 128 else 104)
        palette.setColor(QPalette.ColorRole.AlternateBase, alternate)
        view.setPalette(palette)

    def _match_item_selection_to_log(self) -> None:
        log_palette = self.log.palette()
        highlight = log_palette.color(QPalette.ColorGroup.Active, QPalette.ColorRole.Highlight)
        highlighted_text = log_palette.color(
            QPalette.ColorGroup.Active,
            QPalette.ColorRole.HighlightedText,
        )
        for view, selector in (
            (self.file_list, "QListWidget"),
            (self.chapter_table, "QTableWidget"),
        ):
            palette = view.palette()
            for group in (QPalette.ColorGroup.Active, QPalette.ColorGroup.Inactive):
                palette.setColor(group, QPalette.ColorRole.Highlight, highlight)
                palette.setColor(group, QPalette.ColorRole.HighlightedText, highlighted_text)
            view.setPalette(palette)
            view.setStyleSheet(
                f"{selector}::item:selected {{"
                f"background-color: {highlight.name()};"
                f"color: {highlighted_text.name()};"
                "}"
            )

    def _restore_ui(self, *, restore_recent: bool) -> None:
        self.output_edit.setText(self.settings_store.value("output", str(Path.home() / "Audiobooks"), str))
        resource_blocker = QSignalBlocker(self.resource_combo)
        temperature_blocker = QSignalBlocker(self.max_temp)
        resource_mode = self.settings_store.value(
            "resource_mode",
            "max_safe_adaptive_foreground",
            str,
        )
        resource_index = self.resource_combo.findData(resource_mode)
        if resource_index >= 0:
            self.resource_combo.setCurrentIndex(resource_index)
        self.max_temp.setValue(self.settings_store.value("max_temp", 86, int))
        del resource_blocker, temperature_blocker
        self._reset_book_settings_controls()
        voice_options_expanded = self.settings_store.value("voice_options_expanded", True, bool)
        self.voice_foldout_button.setChecked(voice_options_expanded)
        self._set_voice_options_expanded(voice_options_expanded, persist=False)
        self._set_project_selected(False)
        for key, splitter in (
            ("splitter_main", self.main_splitter),
            ("splitter_source", self.source_splitter),
            ("splitter_work", self.work_splitter),
        ):
            state = self.settings_store.value(key)
            if state is not None:
                splitter.restoreState(state)
        header_state = self.settings_store.value("chapter_header_v3")
        if header_state is not None:
            self.chapter_table.horizontalHeader().restoreState(header_state)
            self._mp3_column_initialized = True
        if restore_recent:
            candidate = self._recent_project_candidate()
            if candidate is not None:
                try:
                    self._load_project(candidate, announce=False)
                except Exception as exc:  # noqa: BLE001
                    self._append_log(f"Không thể tự mở sách gần đây: {exc}")

    def _save_ui(self) -> None:
        self.settings_store.setValue("output", self.output_edit.text().strip())
        self.settings_store.setValue("resource_mode", self.resource_combo.currentData())
        self.settings_store.setValue("max_temp", self.max_temp.value())
        self.settings_store.setValue("voice_options_expanded", self.voice_foldout_button.isChecked())
        self.settings_store.setValue("splitter_main", self.main_splitter.saveState())
        self.settings_store.setValue("splitter_source", self.source_splitter.saveState())
        self.settings_store.setValue("splitter_work", self.work_splitter.saveState())
        self.settings_store.setValue("chapter_header_v3", self.chapter_table.horizontalHeader().saveState())
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
        timestamp = datetime.now().strftime("%H:%M:%S")
        lines = str(text).splitlines() or [""]
        for line in lines:
            self.log.append(f"[{timestamp}] {line}")
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
        book_settings_editable = not selected and not running
        self.title_edit.setReadOnly(selected)
        self.output_edit.setReadOnly(selected)
        self.choose_output_button.setEnabled(not selected and not running)
        self.add_files_button.setEnabled(not running)
        self.add_folder_button.setEnabled(not running)
        self.new_book_button.setEnabled(selected and not running)
        self.open_project_button.setEnabled(not running)
        self.profile_combo.setEnabled(book_settings_editable)
        self.narrator_gender_combo.setEnabled(book_settings_editable)
        self.narrator_region_combo.setEnabled(book_settings_editable)
        self.narrator_voice_combo.setEnabled(book_settings_editable)
        self.voice_tools_layout.setRowVisible(
            self.narrator_gender_combo,
            book_settings_editable,
        )
        self.voice_tools_layout.setRowVisible(
            self.narrator_region_combo,
            book_settings_editable,
        )
        self.preview_button.setEnabled(bool(self.narrator_voice_combo.currentData()))
        self.voice_foldout_button.setEnabled(True)
        self.resource_combo.setEnabled(True)
        self.max_temp.setEnabled(True)
        self.open_folder_button.setEnabled(selected)
        self.settings_box.setTitle("Thiết lập")
        self._update_remove_files_button()
        self._update_start_button()

    def _global_settings_edited(self, *_args: Any) -> None:
        if self._applying_locked_settings:
            return
        self._save_ui()
        if self.resource_settings_queue is not None:
            try:
                self.resource_settings_queue.put_nowait(self._runtime_resource_overrides())
            except (Full, OSError, ValueError):
                pass

    def _populate_narrator_voices(self, preferred_voice: str | None = None) -> None:
        previous_voice = str(self.narrator_voice_combo.currentData() or "")
        gender = str(self.narrator_gender_combo.currentData() or "")
        region = str(self.narrator_region_combo.currentData() or "")
        blocker = QSignalBlocker(self.narrator_voice_combo)
        self.narrator_voice_combo.clear()
        available = narrator_presets(gender or None, region or None)
        for preset in available:
            self.narrator_voice_combo.addItem(preset["name"], preset["name"])
        target = preferred_voice or previous_voice
        if self.narrator_voice_combo.findData(target) < 0 and gender in DEFAULT_NARRATOR_BY_GENDER:
            target = DEFAULT_NARRATOR_BY_GENDER[gender]
        index = self.narrator_voice_combo.findData(target)
        self.narrator_voice_combo.setCurrentIndex(index if index >= 0 else 0)
        del blocker

    def _voice_foldout_icon(self, *, expanded: bool) -> QIcon:
        icon_size = QSize(VOICE_FOLDOUT_ICON_SIZE, VOICE_FOLDOUT_ICON_SIZE)
        pixmap = QPixmap(icon_size)
        pixmap.fill(Qt.GlobalColor.transparent)
        option = QStyleOption()
        option.initFrom(self.voice_foldout_button)
        option.rect = pixmap.rect()
        primitive = (
            QStyle.PrimitiveElement.PE_IndicatorArrowDown
            if expanded
            else QStyle.PrimitiveElement.PE_IndicatorArrowRight
        )
        painter = QPainter(pixmap)
        self.voice_foldout_button.style().drawPrimitive(
            primitive,
            option,
            painter,
            self.voice_foldout_button,
        )
        painter.end()
        return QIcon(pixmap)

    def _set_voice_options_expanded(self, expanded: bool, *, persist: bool = True) -> None:
        self.voice_tools_widget.setVisible(expanded)
        self.voice_foldout_button.setIcon(self._voice_foldout_icon(expanded=expanded))
        if persist:
            self.settings_store.setValue("voice_options_expanded", expanded)
            self.settings_store.sync()

    def _narrator_voice_changed(self, *_args: Any) -> None:
        self._play_narrator_preview()

    def _play_narrator_preview(self) -> None:
        voice_name = str(self.narrator_voice_combo.currentData() or "")
        filename = VOICE_PREVIEW_FILENAMES.get(voice_name)
        if not filename:
            self._append_log(f"Không có preview cho giọng {voice_name or 'chưa chọn'}.")
            return
        preview = (VOICE_PREVIEW_DIR / filename).resolve()
        if not preview.is_file():
            self._append_log(f"Thiếu file preview giọng: {preview}")
            return
        self.preview_player.stop()
        self.preview_player.setSource(QUrl.fromLocalFile(str(preview)))
        self.preview_player.play()

    def _narrator_filter_changed(self, *_args: Any) -> None:
        self._populate_narrator_voices()

    def _update_start_button(self) -> None:
        running = bool(self.process and self.process.is_alive())
        if running:
            paused = bool(self.pause_event and self.pause_event.is_set())
            self.start_button.setText("Tiếp tục" if paused else "Tạm dừng")
            stopping = bool(self.stop_event and self.stop_event.is_set())
            self.start_button.setEnabled(not self.received_finished and not stopping)
            return
        self.start_button.setText("Tiếp tục" if self.project_paths is not None else "Bắt đầu")
        self.start_button.setEnabled(bool(self.files))

    def _detach_project_as_draft(self) -> None:
        if self.project_paths is None:
            return
        self.project_paths = None
        self.db = None
        self.chapter_table.setRowCount(0)
        self._show_progress("Sẵn sàng", 0, 100)
        self._chapter_snapshot = None
        self._set_project_selected(False)
        self._append_log("Đang tạo bản sách mới; sách hiện tại vẫn nguyên vẹn trên ổ đĩa.")

    def _merge_input_files(self, paths: list[Path]) -> int:
        existing = {str(path).casefold() for path in self.files}
        additions: list[Path] = []
        for path in paths:
            resolved = path.resolve()
            key = str(resolved).casefold()
            if key not in existing:
                additions.append(resolved)
                existing.add(key)
        if additions and self.project_paths is not None:
            self._detach_project_as_draft()
        self.files.extend(additions)
        self.files.sort(key=lambda path: natural_key(path.name))
        self._refresh_file_list()
        return len(additions)

    def _add_files(self) -> None:
        start_dir = self.settings_store.value("input_folder", "", str)
        names, _ = QFileDialog.getOpenFileNames(
            self,
            "Thêm TXT vào sách",
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
        if not selected:
            return
        if self.project_paths is not None:
            self._detach_project_as_draft()
        self.files = [path for path in self.files if str(path) not in selected]
        self._refresh_file_list()

    def _update_remove_files_button(self) -> None:
        running = bool(self.process and self.process.is_alive())
        self.remove_files_button.setEnabled(bool(self.file_list.selectedItems()) and not running)

    def _refresh_file_list(self) -> None:
        self.file_list.clear()
        self.file_list.addItems([str(path) for path in self.files])
        self._update_remove_files_button()
        self._update_start_button()

    def _choose_output(self) -> None:
        directory = QFileDialog.getExistingDirectory(self, "Chọn thư mục đầu ra", self.output_edit.text())
        if directory:
            self.output_edit.setText(directory)

    def _build_settings(self) -> dict[str, Any]:
        profile = str(self.profile_combo.currentData())
        overrides = {
            "voices": {
                "narrator_voice": str(self.narrator_voice_combo.currentData()),
            },
        }
        return build_settings(profile, overrides)

    def _runtime_resource_overrides(self) -> dict[str, Any]:
        return {
            "mode": str(self.resource_combo.currentData()),
            "max_gpu_temp_c": self.max_temp.value(),
            "resume_gpu_temp_c": max(60, self.max_temp.value() - 6),
            "critical_gpu_temp_c": min(98, self.max_temp.value() + 5),
        }

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
            self.resource_settings_queue = ctx.Queue()
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
                    self._runtime_resource_overrides(),
                    self.resource_settings_queue,
                ),
                daemon=False,
            )
            self.process.start()
            self._running_controls(True)
            self._append_log("Worker đã bắt đầu. Mọi phần hoàn tất đều được lưu để có thể tiếp tục an toàn.")
            self._refresh_chapters()
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Không thể bắt đầu", str(exc))

    def _handle_primary_action(self) -> None:
        if self.process and self.process.is_alive():
            self._toggle_pause()
            return
        self._start()

    def _toggle_pause(self) -> None:
        if not self.pause_event:
            return
        if self.pause_event.is_set():
            self.pause_event.clear()
        else:
            self.pause_event.set()
        self._update_start_button()

    def _stop(self) -> None:
        if self.stop_event:
            self.was_user_stop = True
            self.stop_event.set()
            self.stop_button.setEnabled(False)
            self.start_button.setEnabled(False)
            self._show_progress("Đang dừng…")
            self._append_log("Đang dừng. Phần chưa commit sẽ được recovery kiểm tra khi tiếp tục.")

    def _running_controls(self, running: bool) -> None:
        self.stop_button.setEnabled(running)
        self._set_project_selected(self.project_paths is not None)
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
        if self.resource_settings_queue is not None:
            try:
                self.resource_settings_queue.close()
                self.resource_settings_queue.join_thread()
            except (OSError, ValueError):
                pass
        self.message_queue = None
        self.resource_settings_queue = None
        self.pause_event = None
        self.stop_event = None

    def _open_project(self) -> None:
        if self.process and self.process.is_alive():
            return
        directory = QFileDialog.getExistingDirectory(self, "Chọn thư mục sách", self.output_edit.text())
        if not directory:
            return
        try:
            self._load_project(Path(directory).resolve(), announce=True)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Không mở được sách", str(exc))

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
            self._append_log("Đã mở sách. Khi tiếp tục sẽ dùng nguyên settings và voice mapping đã khóa.")

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
        self._reset_book_settings_controls()
        self._set_project_selected(False)
        self._append_log("Đã chuyển sang sách mới; sách cũ vẫn nguyên vẹn trên ổ đĩa.")

    def _set_book_settings_controls(
        self,
        *,
        quality_profile: str,
        narrator_voice: str,
    ) -> None:
        was_applying_locked_settings = self._applying_locked_settings
        self._applying_locked_settings = True
        blockers = (
            QSignalBlocker(self.profile_combo),
            QSignalBlocker(self.narrator_gender_combo),
            QSignalBlocker(self.narrator_region_combo),
        )
        try:
            profile_index = self.profile_combo.findData(quality_profile)
            if profile_index < 0:
                profile_index = self.profile_combo.findData(DEFAULT_QUALITY_PROFILE)
            self.profile_combo.setCurrentIndex(profile_index)
            self.narrator_gender_combo.setCurrentIndex(
                self.narrator_gender_combo.findData(DEFAULT_NARRATOR_FILTER)
            )
            self.narrator_region_combo.setCurrentIndex(
                self.narrator_region_combo.findData(DEFAULT_NARRATOR_FILTER)
            )
            self._populate_narrator_voices(narrator_voice)
        finally:
            del blockers
            self._applying_locked_settings = was_applying_locked_settings

    def _reset_book_settings_controls(self) -> None:
        self._set_book_settings_controls(
            quality_profile=DEFAULT_QUALITY_PROFILE,
            narrator_voice=DEFAULT_NARRATOR_VOICE,
        )

    def _apply_locked_settings(self, settings: dict[str, Any]) -> None:
        quality_profile = str(settings.get("quality_profile", DEFAULT_QUALITY_PROFILE))
        voices = settings.get("voices", {})
        narrator_voice = str(voices.get("narrator_voice", DEFAULT_NARRATOR_VOICE))
        try:
            preset_by_name(narrator_voice)
        except ValueError:
            narrator_voice = DEFAULT_NARRATOR_VOICE
        self._set_book_settings_controls(
            quality_profile=quality_profile,
            narrator_voice=narrator_voice,
        )

    def _refresh_chapters(self) -> None:
        if not self.db:
            return
        try:
            chapters = self.db.list_chapters()
            segment_progress = self.db.chapter_progress_counts()
            book = self.db.book()
        except Exception:
            return
        snapshot = tuple(
            (
                int(row["id"]),
                str(row["status"]),
                segment_progress.get(int(row["id"]), {}).get("analysis", 0),
                segment_progress.get(int(row["id"]), {}).get("audio", 0),
                int(row["verified_segments"]),
                int(row["warning_segments"]),
                int(row["failed_segments"]),
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
            chapter_id = int(row["id"])
            progress = segment_progress.get(chapter_id, {"analysis": 0, "audio": 0})
            self.chapter_table.setItem(index, 0, QTableWidgetItem(str(row["chapter_index"])))
            self.chapter_table.setItem(index, 1, QTableWidgetItem(str(row["title"])))
            total = int(row["total_segments"])
            self.chapter_table.setItem(
                index,
                2,
                QTableWidgetItem(f"{progress['analysis']}/{total}" if total else "0/0"),
            )
            self.chapter_table.setItem(
                index,
                3,
                QTableWidgetItem(f"{progress['audio']}/{total}" if total else "0/0"),
            )
            accepted = int(row["verified_segments"]) + int(row["warning_segments"])
            failed = int(row["failed_segments"])
            verification_text = f"{accepted}/{total}" if total else "0/0"
            if failed:
                verification_text += f" · {failed} lỗi"
            self.chapter_table.setItem(index, 4, QTableWidgetItem(verification_text))
            status = str(row["status"])
            self.chapter_table.setItem(
                index,
                5,
                QTableWidgetItem(CHAPTER_STATUS_LABELS.get(status, status)),
            )
            output = str(row["output_mp3"])
            published = str(row["status"]) == "completed" and Path(output).exists()
            mp3_text = output if published else ""
            if not published and status == "verifying":
                mp3_text = "Đang kiểm tra / ghép"
            elif not published and status == "failed":
                mp3_text = "Lỗi — chưa xuất MP3"
            item = QTableWidgetItem(mp3_text)
            item.setData(Qt.UserRole, output if published else "")
            item.setToolTip(output if published else str(row["last_error"] or mp3_text))
            self.chapter_table.setItem(index, MP3_COLUMN, item)
            if status == "completed":
                done += 1
        if not self._mp3_column_initialized:
            published_paths = [
                str(row["output_mp3"])
                for row in chapters
                if str(row["status"]) == "completed" and Path(str(row["output_mp3"])).exists()
            ]
            if published_paths:
                content_width = max(
                    self.chapter_table.fontMetrics().horizontalAdvance(path) for path in published_paths
                )
                self.chapter_table.setColumnWidth(
                    MP3_COLUMN,
                    max(CHAPTER_TABLE_DEFAULT_WIDTHS[MP3_COLUMN], content_width + 28),
                )
                self._mp3_column_initialized = True
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
                self._show_progress("Sách sẵn sàng", done, len(chapters))

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
        item = self.chapter_table.item(row, MP3_COLUMN)
        if not item:
            return
        path_text = str(item.data(Qt.UserRole) or "").strip()
        if not path_text:
            return
        path = Path(path_text)
        if path.is_file():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def _open_project_folder(self) -> None:
        if self.project_paths and self.project_paths.root.exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.project_paths.root)))

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        if self._tray_available and not self._force_quit:
            self._save_ui()
            event.ignore()
            self.hide()
            if not self._tray_message_shown:
                self.tray_icon.showMessage(
                    f"{APP_NAME} vẫn đang chạy",
                    "Bấm biểu tượng ở system tray để mở lại hoặc chọn Thoát hoàn toàn.",
                    QSystemTrayIcon.MessageIcon.Information,
                    4000,
                )
                self._tray_message_shown = True
            return
        self._save_ui()
        self._terminate_worker_for_exit()
        self.tray_icon.hide()
        event.accept()


def _set_windows_app_identity() -> None:
    if os.name != "nt":
        return
    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_USER_MODEL_ID)
    except (AttributeError, OSError):
        pass


def _notify_running_instance(server_name: str = INSTANCE_SERVER_NAME) -> bool:
    socket = QLocalSocket()
    socket.connectToServer(server_name)
    if not socket.waitForConnected(INSTANCE_CONNECT_TIMEOUT_MS):
        socket.abort()
        return False
    socket.write(INSTANCE_ACTIVATE_MESSAGE)
    socket.flush()
    socket.waitForBytesWritten(INSTANCE_CONNECT_TIMEOUT_MS)
    socket.disconnectFromServer()
    return True


def _claim_single_instance(
    app: QApplication,
    server_name: str = INSTANCE_SERVER_NAME,
) -> QLocalServer | None:
    if _notify_running_instance(server_name):
        return None

    server = QLocalServer(app)
    if server.listen(server_name):
        return server

    if _notify_running_instance(server_name):
        return None

    QLocalServer.removeServer(server_name)
    if server.listen(server_name):
        return server
    raise RuntimeError(f"Không thể khóa single-instance: {server.errorString()}")


def _signal_startup_ready() -> None:
    ready_path = os.environ.get(STARTUP_READY_FILE_ENV, "").strip()
    if not ready_path:
        return
    try:
        Path(ready_path).write_text(str(os.getpid()), encoding="ascii")
    except OSError:
        # Launcher vẫn còn đường dự phòng bằng MainWindowHandle và process exit.
        pass


def _connect_instance_activation(server: QLocalServer, window: MainWindow) -> None:
    def activate_pending_instance() -> None:
        received = False
        while server.hasPendingConnections():
            connection = server.nextPendingConnection()
            if connection is None:
                continue
            connection.readAll()
            connection.disconnectFromServer()
            received = True
        if received:
            window._show_from_tray()

    window._instance_server = server
    window._instance_activation_handler = activate_pending_instance
    server.newConnection.connect(activate_pending_instance)
    QTimer.singleShot(0, activate_pending_instance)


def run_gui() -> int:
    mp.freeze_support()
    _set_windows_app_identity()
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setWindowIcon(QIcon(str(APP_ICON_PATH)))
    instance_server = _claim_single_instance(app)
    if instance_server is None:
        _signal_startup_ready()
        return 0
    window = MainWindow()
    _connect_instance_activation(instance_server, window)
    window.show()
    app.processEvents()
    _signal_startup_ready()
    return app.exec()
