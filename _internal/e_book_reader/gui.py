from __future__ import annotations

import multiprocessing as mp
import os
import sys
from pathlib import Path
from queue import Empty
from typing import Any

from PySide6.QtCore import QSettings, Qt, QTimer, QUrl
from PySide6.QtGui import QCloseEvent, QDesktopServices
from PySide6.QtWidgets import (
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

from .config import build_settings
from .database import ProjectDB
from .io_utils import discover_txt_files, natural_key
from .models import ProjectPaths
from .notifier import WindowsNotifier
from .project import create_or_open_project
from .worker import run_worker


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("E Book Reader — v0.2 alpha.8")
        self.resize(1180, 780)
        self.settings_store = QSettings("OpenAI", "EBookReader")
        self.files: list[Path] = []
        self.project_paths: ProjectPaths | None = None
        self.db: ProjectDB | None = None
        self.process: mp.Process | None = None
        self.message_queue: Any = None
        self.pause_event: Any = None
        self.stop_event: Any = None
        self.received_finished = False
        self.was_user_stop = False
        self.notifier = WindowsNotifier()
        self._build_ui()
        self._restore_ui()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._poll)
        self.timer.start(350)

    def _build_ui(self) -> None:
        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        title = QLabel("E Book Reader")
        title.setStyleSheet("font-size: 25px; font-weight: 700;")
        layout.addWidget(title)
        layout.addWidget(
            QLabel(
                "Phân tích toàn book trước, khóa voice casting, chạy tự động không hỏi giữa chừng, "
                "checkpoint an toàn và tự nhường tài nguyên cho ứng dụng foreground."
            )
        )

        top = QGridLayout()
        self.title_edit = QLineEdit()
        self.title_edit.setPlaceholderText("Tên book; để trống sẽ lấy tên thư mục hoặc file")
        self.output_edit = QLineEdit()
        self.output_edit.setPlaceholderText("Thư mục chứa các book project")
        choose_output = QPushButton("Chọn thư mục đầu ra")
        choose_output.clicked.connect(self._choose_output)
        add_files = QPushButton("Thêm TXT")
        add_files.clicked.connect(self._add_files)
        add_folder = QPushButton("Thêm folder")
        add_folder.clicked.connect(self._add_folder)
        remove_files = QPushButton("Xóa file đã chọn")
        remove_files.clicked.connect(self._remove_files)
        open_project = QPushButton("Mở project cũ")
        open_project.clicked.connect(self._open_project)
        top.addWidget(QLabel("Tên book:"), 0, 0)
        top.addWidget(self.title_edit, 0, 1, 1, 3)
        top.addWidget(QLabel("Nơi lưu:"), 1, 0)
        top.addWidget(self.output_edit, 1, 1)
        top.addWidget(choose_output, 1, 2)
        top.addWidget(open_project, 1, 3)
        top.addWidget(add_files, 2, 1)
        top.addWidget(add_folder, 2, 2)
        top.addWidget(remove_files, 2, 3)
        layout.addLayout(top)

        splitter = QSplitter(Qt.Vertical)
        upper = QWidget()
        upper_layout = QHBoxLayout(upper)
        upper_layout.setContentsMargins(0, 0, 0, 0)
        files_box = QGroupBox("TXT thuộc cùng một book")
        files_layout = QVBoxLayout(files_box)
        self.file_list = QListWidget()
        files_layout.addWidget(self.file_list)
        upper_layout.addWidget(files_box, 1)

        settings_box = QGroupBox("Settings khóa trước khi chạy book")
        form = QFormLayout(settings_box)
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
        self.full_book = QCheckBox("Tạo MP3 toàn book")
        self.full_book.setChecked(True)
        self.pause_battery = QCheckBox("Tự tạm dừng khi chuyển sang pin")
        self.pause_battery.setChecked(True)
        form.addRow("Chất lượng:", self.profile_combo)
        form.addRow("Tài nguyên:", self.resource_combo)
        form.addRow("Ngưỡng GPU nóng:", self.max_temp)
        form.addRow(self.keep_wav)
        form.addRow(self.full_book)
        form.addRow(self.pause_battery)
        note = QLabel("Sau khi bấm Bắt đầu, app không bật hộp thoại yêu cầu lựa chọn.")
        note.setWordWrap(True)
        note.setStyleSheet("color:#666")
        form.addRow(note)
        upper_layout.addWidget(settings_box, 1)
        splitter.addWidget(upper)

        lower = QWidget()
        lower_layout = QHBoxLayout(lower)
        lower_layout.setContentsMargins(0, 0, 0, 0)
        chapters_box = QGroupBox("Tiến độ chapter")
        chapters_layout = QVBoxLayout(chapters_box)
        self.chapter_table = QTableWidget(0, 5)
        self.chapter_table.setHorizontalHeaderLabels(["#", "Chapter", "Trạng thái", "Segment", "MP3"])
        self.chapter_table.verticalHeader().setVisible(False)
        self.chapter_table.setSelectionBehavior(QTableWidget.SelectRows)
        header = self.chapter_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.Stretch)
        self.chapter_table.doubleClicked.connect(self._open_selected_mp3)
        chapters_layout.addWidget(self.chapter_table)
        lower_layout.addWidget(chapters_box, 2)

        log_box = QGroupBox("Nhật ký")
        log_layout = QVBoxLayout(log_box)
        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setLineWrapMode(QTextEdit.NoWrap)
        log_layout.addWidget(self.log)
        lower_layout.addWidget(log_box, 1)
        splitter.addWidget(lower)
        splitter.setSizes([260, 430])
        layout.addWidget(splitter, 1)

        controls = QHBoxLayout()
        self.start_button = QPushButton("Bắt đầu / Tiếp tục")
        self.start_button.clicked.connect(self._start)
        self.pause_button = QPushButton("Tạm dừng")
        self.pause_button.clicked.connect(self._toggle_pause)
        self.pause_button.setEnabled(False)
        self.safe_stop_button = QPushButton("Dừng tại checkpoint")
        self.safe_stop_button.clicked.connect(self._safe_stop)
        self.safe_stop_button.setEnabled(False)
        self.stop_now_button = QPushButton("Dừng ngay")
        self.stop_now_button.clicked.connect(self._stop_now)
        self.stop_now_button.setEnabled(False)
        open_folder = QPushButton("Mở thư mục project")
        open_folder.clicked.connect(self._open_project_folder)
        self.resource_label = QLabel("Tài nguyên: chưa chạy")
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        controls.addWidget(self.start_button)
        controls.addWidget(self.pause_button)
        controls.addWidget(self.safe_stop_button)
        controls.addWidget(self.stop_now_button)
        controls.addWidget(open_folder)
        controls.addWidget(self.resource_label)
        controls.addWidget(self.progress, 1)
        layout.addLayout(controls)

    def _restore_ui(self) -> None:
        self.output_edit.setText(self.settings_store.value("output", str(Path.home() / "Audiobooks"), str))
        self.max_temp.setValue(self.settings_store.value("max_temp", 86, int))

    def _save_ui(self) -> None:
        self.settings_store.setValue("output", self.output_edit.text().strip())
        self.settings_store.setValue("max_temp", self.max_temp.value())

    def _append_log(self, text: str) -> None:
        self.log.append(text)
        scrollbar = self.log.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def _merge_input_files(self, paths: list[Path]) -> int:
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
                "pause_on_battery": self.pause_battery.isChecked(),
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
            self.start_button.setEnabled(False)
            self.pause_button.setEnabled(True)
            self.safe_stop_button.setEnabled(True)
            self.stop_now_button.setEnabled(True)
            self._append_log("Worker đã bắt đầu. Có thể đóng app; checkpoint và recovery sẽ bảo vệ phần đã hoàn tất.")
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
            self.pause_button.setText("Tiếp tục")

    def _safe_stop(self) -> None:
        if self.stop_event:
            self.was_user_stop = True
            self.stop_event.set()
            self._append_log("Đã yêu cầu dừng tại checkpoint gần nhất.")

    def _stop_now(self) -> None:
        if not self.process or not self.process.is_alive():
            return
        self.was_user_stop = True
        if self.stop_event:
            self.stop_event.set()
        self.process.terminate()
        self.process.join(timeout=4)
        if self.process.is_alive():
            try:
                self.process.kill()
            except Exception:
                pass
            self.process.join(timeout=2)
        self._append_log("Worker đã bị dừng ngay. File .part sẽ bị loại bỏ trong recovery scan lần sau.")
        self._running_controls(False)
        self._dispose_ipc()

    def _running_controls(self, running: bool) -> None:
        self.start_button.setEnabled(not running)
        self.pause_button.setEnabled(running)
        self.safe_stop_button.setEnabled(running)
        self.stop_now_button.setEnabled(running)
        if not running:
            self.pause_button.setText("Tạm dừng")

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
        selected = Path(directory).resolve()
        if not (selected / "project.sqlite3").exists() or not (selected / "book_settings.json").exists():
            QMessageBox.warning(self, "Không phải project", "Thư mục không có project.sqlite3 và book_settings.json.")
            return
        try:
            paths = ProjectPaths.build(selected)
            self.project_paths = paths
            self.db = ProjectDB(paths.db)
            chapters = self.db.list_chapters()
            self.files = [Path(str(row["input_path"])) for row in chapters]
            self.title_edit.setText(str(self.db.book()["title"]))
            self.output_edit.setText(str(paths.root.parent))
            self._refresh_file_list()
            self._refresh_chapters()
            self._append_log("Đã mở project. Khi tiếp tục sẽ dùng nguyên settings và voice mapping đã khóa.")
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Không mở được project", str(exc))

    def _refresh_chapters(self) -> None:
        if not self.db:
            return
        try:
            chapters = self.db.list_chapters()
        except Exception:
            return
        self.chapter_table.setRowCount(len(chapters))
        done = 0
        for index, row in enumerate(chapters):
            self.chapter_table.setItem(index, 0, QTableWidgetItem(str(row["chapter_index"])))
            self.chapter_table.setItem(index, 1, QTableWidgetItem(str(row["title"])))
            self.chapter_table.setItem(index, 2, QTableWidgetItem(str(row["status"])))
            accepted = int(row["verified_segments"]) + int(row["warning_segments"])
            total = int(row["total_segments"])
            self.chapter_table.setItem(index, 3, QTableWidgetItem(f"{accepted}/{total}"))
            output = str(row["output_mp3"])
            item = QTableWidgetItem(output if Path(output).exists() else "")
            item.setData(Qt.UserRole, output)
            self.chapter_table.setItem(index, 4, item)
            if row["status"] == "completed":
                done += 1
        self.progress.setValue(round(done * 100 / max(1, len(chapters))))

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
                    self._append_log(str(message.get("text", "")))
                elif kind == "resource":
                    self.resource_label.setText(
                        f"Tài nguyên: {message.get('level')} — {message.get('reason')}"
                    )
                elif kind == "analysis_progress":
                    done, total = int(message.get("done", 0)), int(message.get("total", 0))
                    self.progress.setValue(round(done * 100 / max(1, total)))
                elif kind == "chapter_completed":
                    self._append_log(f"Có thể nghe ngay: {message.get('path')}")
                elif kind == "finished":
                    self.received_finished = True
                    self._append_log(str(message.get("text", "")))
                    self._running_controls(False)
        self._refresh_chapters()
        if self.process and not self.process.is_alive():
            exitcode = self.process.exitcode
            if not self.received_finished and not self.was_user_stop:
                title = str(self.db.book()["title"]) if self.db else "Audiobook"
                root = self.project_paths.root if self.project_paths else Path.cwd()
                self.notifier.critical_stop(title, f"Worker thoát bất ngờ, exit code {exitcode}", root)
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
        # No confirmation dialog: closing at any moment must be safe and unattended-friendly.
        if self.process and self.process.is_alive():
            self.was_user_stop = True
            if self.stop_event:
                self.stop_event.set()
            self.process.join(timeout=2.0)
            if self.process.is_alive():
                self.process.terminate()
                self.process.join(timeout=2.0)
            if self.process.is_alive():
                try:
                    self.process.kill()
                except Exception:
                    pass
            if not self.process.is_alive():
                self._dispose_ipc()
        event.accept()


def run_gui() -> int:
    mp.freeze_support()
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    return app.exec()
