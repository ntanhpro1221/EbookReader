"""Cửa sổ app máy tính: giao diện web (ebook_reader/webui) trong Qt WebEngine - thứ PySide6 đã có sẵn.

Giữ các bất biến của GUI cũ (gui.py): một phiên bản duy nhất theo phiên người dùng (lần mở sau chỉ kích hoạt cửa
sổ đang chạy), báo "đã sẵn sàng" cho trình khởi động (start_windows.ps1) sau khi trang vẽ xong, không hỏi người
dùng giữa lúc chạy sách. Sách chạy qua supervisor nền nên đóng cửa sổ không dừng sách.

GPU của trang web bị tắt: dây chuyền cần ~6,2 GB trên card 8 GB khi phân tích, và docs/THROUGHPUT.md đã đo một
Unity Editor nằm im (1,6 GB) là đủ đẩy Ollama tháo model giữa chừng. Giao diện này vẽ bằng CPU là đủ mượt.
"""
from __future__ import annotations

import os
import sys
import threading
from importlib import metadata
from typing import Any, Callable

from .gui import (
    APP_ICON_PATH,
    APP_NAME,
    _claim_single_instance,
    _connect_instance_activation,
    _set_windows_app_identity,
    _signal_startup_ready,
)

WEB_FLAGS = "--disable-gpu --disable-gpu-compositing --disable-features=Translate"


def _version() -> str:
    try:
        return metadata.version("ebook-reader")
    except metadata.PackageNotFoundError:
        return ""


def run_desktop() -> int:
    os.environ.setdefault("QTWEBENGINE_CHROMIUM_FLAGS", WEB_FLAGS)
    from PySide6.QtCore import QObject, QSettings, Qt, QUrl, Signal, Slot
    from PySide6.QtGui import QColor, QIcon
    from PySide6.QtWebEngineCore import QWebEnginePage
    from PySide6.QtWebEngineWidgets import QWebEngineView
    from PySide6.QtWidgets import QApplication, QFileDialog, QMainWindow

    from .webui import actions
    from .webui.library import Preferences
    from .webui.server import App, Server, new_token

    class Dialogs(QObject):
        """Hộp thoại của Windows, gọi từ luồng server HTTP nhưng phải chạy trên luồng giao diện Qt."""

        request = Signal(object)

        def __init__(self, window: QMainWindow) -> None:
            super().__init__()
            self.window = window
            self.request.connect(self._run, Qt.ConnectionType.QueuedConnection)

        @Slot(object)
        def _run(self, job: Callable[[], None]) -> None:
            job()

        def _call(self, function: Callable[[], Any]) -> Any:
            done = threading.Event()
            box: dict[str, Any] = {}

            def job() -> None:
                try:
                    box["value"] = function()
                finally:
                    done.set()

            self.request.emit(job)
            done.wait()
            return box.get("value")

        def pick_folder(self, title: str, start: str) -> str | None:
            return self._call(lambda: QFileDialog.getExistingDirectory(self.window, title, start) or None)

        def pick_files(self, title: str, start: str) -> list[str]:
            return self._call(lambda: QFileDialog.getOpenFileNames(self.window, title, start, "Chương truyện (*.txt)")[0])

    class Window(QMainWindow):
        def __init__(self) -> None:
            super().__init__()
            self.setWindowTitle(APP_NAME)
            self.setMinimumSize(1024, 680)  # hẹp hơn thì bảng Studio và thanh phát không còn chỗ
            self.settings = QSettings("EbookReader", "Desktop")
            geometry = self.settings.value("geometry")
            if geometry is not None:
                self.restoreGeometry(geometry)
            else:
                self.resize(1320, 860)
            self.view = QWebEngineView(self)
            page = QWebEnginePage(self.view)
            page.setBackgroundColor(QColor("#0e1115"))
            self.view.setPage(page)
            self.view.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)
            self.setCentralWidget(self.view)

        def _show_from_tray(self) -> None:
            """Lần mở thứ hai của app gọi hàm này (qua khoá một phiên bản) để đưa cửa sổ lên trước."""
            self.showNormal()
            self.raise_()
            self.activateWindow()

        def closeEvent(self, event: Any) -> None:  # noqa: N802
            self.settings.setValue("geometry", self.saveGeometry())
            super().closeEvent(event)

    _set_windows_app_identity()
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setWindowIcon(QIcon(str(APP_ICON_PATH)))
    instance_server = _claim_single_instance(app)
    if instance_server is None:
        _signal_startup_ready()
        return 0

    window = Window()
    preferences = Preferences()
    web = App(
        preferences=preferences,
        # EBOOK_READER_FAKE_RUNNER=1: thử cửa sổ mà không khởi động worker thật (máy đang sản xuất sách).
        runner=actions.FakeRunner() if os.environ.get("EBOOK_READER_FAKE_RUNNER") == "1" else actions.BackgroundRunner(),
        token=new_token(),
        dialogs=Dialogs(window),
        version=_version(),
    )
    if preferences.get().get("syncEnabled"):
        web.set_sync(True)
    http = Server(web).start()
    window.view.loadFinished.connect(lambda _ok: _signal_startup_ready())
    window.view.setUrl(QUrl(http.url))
    _connect_instance_activation(instance_server, window)  # type: ignore[arg-type]
    window.show()
    try:
        return app.exec()
    finally:
        web.close()
        http.stop()
