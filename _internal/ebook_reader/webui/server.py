"""Server HTTP cục bộ cho giao diện: JSON API + audio (có Range để tua) + frontend đã build.

Chỉ nghe trên 127.0.0.1. Mọi `/api` và `/media` cần mã phiên (header `X-Ebook-Token` hoặc `?t=`), và `Host`
phải là chính server - không thì một trang web bất kỳ trong trình duyệt của người dùng gọi được
`127.0.0.1:<cổng>` (hoặc qua DNS rebinding) để đọc sách hay bấm "Bắt đầu" thay họ.
"""
from __future__ import annotations

import json
import mimetypes
import re
import secrets
import threading
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from typing import Any, Callable, Protocol
from urllib.parse import parse_qs, unquote, urlsplit

from . import actions, listen_view, store
from .library import Library, Preferences, book_id
from .listening import Listening
from .reviews import Reviews, review_view
from .sync import Devices, ExclusiveHTTPServer, SyncApp, SyncServer, local_addresses, SYNC_PORT

STATIC_DIR = Path(__file__).resolve().parent / "static"
ASSET_DIR = Path(__file__).resolve().parents[1] / "assets"
VOICE_PREVIEW_DIR = ASSET_DIR / "voice_previews"
CHUNK = 256 * 1024
MAX_BODY = 1024 * 1024
TYPES = {
    ".js": "text/javascript; charset=utf-8",
    ".mjs": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".html": "text/html; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".svg": "image/svg+xml",
    ".woff2": "font/woff2",
    ".woff": "font/woff",
    ".png": "image/png",
    ".ico": "image/x-icon",
    ".mp3": "audio/mpeg",
    ".wav": "audio/wav",
}


class Dialogs(Protocol):
    def pick_folder(self, title: str, start: str) -> str | None: ...
    def pick_files(self, title: str, start: str) -> list[str]: ...


class ApiError(Exception):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message


class App:
    def __init__(
        self,
        *,
        preferences: Preferences,
        runner: actions.Runner,
        token: str | None,
        dialogs: Dialogs | None = None,
        read_only: bool = False,
        static_dir: Path = STATIC_DIR,
        version: str = "",
        listening: Listening | None = None,
    ) -> None:
        self.preferences = preferences
        self.listening = listening or Listening(preferences.path.with_name("listening.json"))
        self.devices = Devices(preferences.path.with_name("devices.json"))
        self.sync_server: SyncServer | None = None
        self.sync_host = "0.0.0.0"
        self.sync_port = SYNC_PORT
        self.sync_error = ""
        self.library = Library(preferences)
        self.jobs = actions.Jobs(runner)
        self.runner = runner
        self.token = token
        self.dialogs = dialogs
        self.read_only = read_only
        self.static_dir = static_dir
        self.version = version
        self.reviews = Reviews(preferences.path.with_name("reviews.json"))
        # Thư mục đã xuất trong phiên này - chỉ những thư mục này được mở bằng "Mở thư mục" sau khi xuất.
        self.exports: set[str] = set()
        # Hàng đợi sản xuất: hai cuốn chạy cùng lúc tranh nhau GPU (phân tích cần ~6,2 GB trên card 8 GB), nên cuốn
        # thứ hai xếp hàng và tự bắt đầu khi cuốn đang chạy xong. Hàng đợi sống cùng app (đóng app là bỏ hàng).
        self.queue: list[str] = []
        self._queue_lock = threading.RLock()  # summary() lấy lại khoá này từ trong start/stop
        self._queue_thread: threading.Thread | None = None

    # ---- sách ------------------------------------------------------------------------------------------

    def _book(self, value: str) -> Path:
        path = self.library.resolve(value)
        if path is None:
            raise ApiError(HTTPStatus.NOT_FOUND, "Không tìm thấy sách này trong thư viện")
        return path

    def summary(self, path: Path) -> dict[str, Any]:
        running = self.runner.running(path)
        result = self.library.summary(path, running=running, starting=self.jobs.starting(path))
        result["startError"] = self.jobs.error(path)
        result.pop("position", None)
        with self._queue_lock:
            result["queuePosition"] = self.queue.index(result["id"]) + 1 if result["id"] in self.queue else None
        return result

    def _busy_elsewhere(self, path: Path) -> Path | None:
        for other in self.library.projects():
            if other != path and (self.runner.running(other) or self.jobs.starting(other)):
                return other
        return None

    def _drain_queue(self) -> None:
        while True:
            time.sleep(15)
            with self._queue_lock:
                if not self.queue:
                    self._queue_thread = None
                    return
                head = self.queue[0]
            path = self.library.resolve(head)
            if path is None:
                with self._queue_lock:
                    self.queue.remove(head)
                continue
            if self._busy_elsewhere(path) is None:
                with self._queue_lock:
                    if self.queue and self.queue[0] == head:
                        self.queue.pop(0)
                self.jobs.start(path)

    def library_view(self) -> dict[str, Any]:
        books = []
        for path in self.library.projects():
            try:
                books.append(self.summary(path))
            except Exception as exc:  # noqa: BLE001 - một sách hỏng không được làm mất cả thư viện
                books.append({"id": book_id(path), "path": str(path), "title": path.name, "broken": str(exc)})
        books.sort(key=lambda book: book.get("updatedAt") or 0, reverse=True)
        return {"root": str(self.library.root), "books": books}

    def book_view(self, value: str) -> dict[str, Any]:
        path = self._book(value)
        return {"book": self.summary(path), "chapters": store.chapters(path)}

    def _mutating(self) -> None:
        if self.read_only:
            raise ApiError(HTTPStatus.FORBIDDEN, "Giao diện đang ở chế độ chỉ xem")

    def start(self, value: str, *, now: bool = False) -> dict[str, Any]:
        self._mutating()
        path = self._book(value)
        if self.runner.running(path):
            return self.summary(path)
        if not now and self._busy_elsewhere(path) is not None:
            with self._queue_lock:
                if value not in self.queue:
                    self.queue.append(value)
                if self._queue_thread is None:
                    self._queue_thread = threading.Thread(target=self._drain_queue, name="production-queue", daemon=True)
                    self._queue_thread.start()
            return self.summary(path)
        with self._queue_lock:
            if value in self.queue:
                self.queue.remove(value)
        self.jobs.start(path)
        return self.summary(path)

    def stop(self, value: str) -> dict[str, Any]:
        self._mutating()
        path = self._book(value)
        with self._queue_lock:
            queued = value in self.queue
            if queued:
                # Đang xếp hàng: "Dừng" nghĩa là bỏ khỏi hàng, không có gì để dừng.
                self.queue.remove(value)
        if queued:
            return self.summary(path)  # ngoài khoá: summary() cũng lấy khoá này (Lock không vào lại được)
        self.jobs.stop(path)
        return self.summary(path)

    def create(self, body: dict[str, Any]) -> dict[str, Any]:
        self._mutating()
        paths = [str(item) for item in body.get("paths", [])]
        root = actions.create_book(
            self.library.root, paths, str(body.get("title", "")), str(body.get("profile", "high_quality")),
            str(body.get("narrator", "")),
        )
        self.preferences.add_recent(root)
        if body.get("start"):
            self.jobs.start(root)
        return {"id": book_id(root)}

    def open_existing(self, body: dict[str, Any]) -> dict[str, Any]:
        path = Path(str(body.get("path", ""))).expanduser()
        if not store.is_project(path):
            raise ApiError(HTTPStatus.BAD_REQUEST, "Thư mục này không phải một sách của Ebook Reader")
        self.preferences.add_recent(path.resolve())
        return {"id": book_id(path.resolve())}

    # ---- đồng bộ điện thoại ------------------------------------------------------------------------------

    def sync_view(self) -> dict[str, Any]:
        running = self.sync_server is not None
        return {
            "enabled": running,
            "wanted": bool(self.preferences.get().get("syncEnabled")),
            "error": self.sync_error,
            "name": socket_name(),
            "port": self.sync_server.port if running else self.sync_port,
            "addresses": local_addresses() if self.sync_host == "0.0.0.0" else [self.sync_host],
            "pairing": self.devices.pairing() if running else None,
            "pairingBlocked": running and self.devices.blocked,
            "devices": sorted(self.devices.list(), key=lambda device: -float(device.get("lastSeen") or 0)),
        }

    def set_sync(self, enabled: bool) -> dict[str, Any]:
        """Bật/tắt đồng bộ. Tuỳ chọn lưu Ý MUỐN của người dùng, không lưu kết quả: cổng bận một lần lúc khởi
        động không được tự tắt đồng bộ vĩnh viễn - lần mở sau thử lại."""
        if enabled and self.sync_server is None:
            try:
                app = SyncApp(self.library, self.listening, self.devices, socket_name())
                self.sync_server = SyncServer(app, host=self.sync_host, port=self.sync_port).start()
                self.sync_error = ""
            except OSError as error:
                self.sync_error = f"Không mở được cổng đồng bộ {self.sync_port}: {error.strerror or error}"
        elif not enabled:
            self.sync_error = ""
            self.devices.cancel_pairing()
            if self.sync_server is not None:
                self.sync_server.stop()
                self.sync_server = None
        if self.preferences.get().get("syncEnabled") != enabled:
            self.preferences.update({"syncEnabled": enabled})
        return self.sync_view()

    def close(self) -> None:
        """App đóng: tắt cổng đồng bộ nhưng giữ nguyên lựa chọn của người dùng cho lần mở sau."""
        if self.sync_server is not None:
            self.sync_server.stop()
            self.sync_server = None

    # ---- nghe ------------------------------------------------------------------------------------------

    def listen_library(self) -> list[dict[str, Any]]:
        """Sách nghe được: mọi sách đã có ít nhất một chương xong - đang sản xuất cũng nghe được phần đã xong. Sách vừa
        tạo, đang làm mà chưa có chương nào, cũng có mặt (chưa nghe được) - người mới tạo sách hỏi "sách của tôi đâu?"."""
        books = []
        for path in self.library.projects():
            try:
                summary = self.summary(path)
            except Exception:  # noqa: BLE001 - sách hỏng thì phía Studio báo; phía Nghe bỏ qua
                continue
            producing = bool(summary.get("running") or summary.get("starting"))
            if summary.get("chapters", {}).get("completed", 0) <= 0 and not producing:
                continue
            view = listen_view.book(path, summary["id"], summary, self.listening.get(summary["id"]), with_chapters=False)
            view["eta"] = summary.get("eta")
            books.append(view)
        books.sort(key=lambda item: ((item["state"].get("last") or {}).get("at") or 0, item.get("updatedAt") or 0),
                   reverse=True)
        return books

    def listen_book(self, value: str) -> dict[str, Any]:
        path = self._book(value)
        return listen_view.book(path, value, self.summary(path), self.listening.get(value))

    def voices(self) -> list[dict[str, Any]]:
        from ..voice_catalog import DEFAULT_NARRATOR_BY_GENDER, VOICE_PREVIEW_FILENAMES, narrator_presets

        defaults = set(DEFAULT_NARRATOR_BY_GENDER.values())
        return [
            {
                "name": preset["name"],
                "gender": {"male": "Nam", "female": "Nữ"}.get(preset["gender"], ""),
                "region": preset["region"],
                "style": {"tu_nhien": "Tự nhiên", "doc_truyen": "Kể chuyện"}.get(preset["style"], preset["style"]),
                "recommended": preset["name"] in defaults,
                "preview": bool(VOICE_PREVIEW_FILENAMES.get(preset["name"])),
            }
            for preset in narrator_presets()
        ]

    def voice_file(self, name: str) -> Path | None:
        from ..voice_catalog import VOICE_PREVIEW_FILENAMES

        filename = VOICE_PREVIEW_FILENAMES.get(name)
        path = VOICE_PREVIEW_DIR / filename if filename else None
        return path if path and path.is_file() else None


# ---- HTTP ------------------------------------------------------------------------------------------------

Route = tuple[str, re.Pattern[str], Callable[..., Any]]


class Handler(BaseHTTPRequestHandler):
    server_version = "EbookReader"
    protocol_version = "HTTP/1.1"
    app: App
    port: int

    # Không in log ra stderr: server sống trong pythonw, không có console.
    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        return

    # ---- khung chung -----------------------------------------------------------------------------------

    def _allowed_host(self) -> bool:
        host = (self.headers.get("Host") or "").lower()
        return host in {f"127.0.0.1:{self.port}", f"localhost:{self.port}"}

    def _authorized(self, query: dict[str, list[str]]) -> bool:
        token = self.app.token
        if token is None:
            return True
        supplied = self.headers.get("X-Ebook-Token") or (query.get("t") or [""])[0]
        return secrets.compare_digest(supplied, token)

    def _send_json(self, status: int, payload: Any) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_BODY:
            raise ApiError(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "Yêu cầu quá lớn")
        if not length:
            return {}
        try:
            data = json.loads(self.rfile.read(length).decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as exc:
            raise ApiError(HTTPStatus.BAD_REQUEST, "JSON không hợp lệ") from exc
        return data if isinstance(data, dict) else {}

    def _send_file(self, path: Path, *, cache: bool = False) -> None:
        size = path.stat().st_size
        content_type = TYPES.get(path.suffix.lower()) or mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        start, end = 0, size - 1
        status = HTTPStatus.OK
        match = re.match(r"bytes=(\d*)-(\d*)$", self.headers.get("Range") or "")
        if match and size:
            first, last = match.groups()
            if first:
                start = int(first)
                end = min(int(last), size - 1) if last else size - 1
            elif last:
                start = max(0, size - int(last))
            if start > end or start >= size:
                self.send_response(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE)
                self.send_header("Content-Range", f"bytes */{size}")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            status = HTTPStatus.PARTIAL_CONTENT
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(end - start + 1))
        if status == HTTPStatus.PARTIAL_CONTENT:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.send_header("Cache-Control", "public, max-age=31536000, immutable" if cache else "no-cache")
        self.end_headers()
        if self.command == "HEAD":
            return
        with path.open("rb") as handle:
            handle.seek(start)
            remaining = end - start + 1
            while remaining > 0:
                chunk = handle.read(min(CHUNK, remaining))
                if not chunk:
                    break
                self.wfile.write(chunk)
                remaining -= len(chunk)

    def _static(self, path_text: str) -> None:
        root = self.app.static_dir
        relative = unquote(path_text).lstrip("/") or "index.html"
        candidate = (root / relative).resolve()
        try:
            candidate.relative_to(root.resolve())
        except ValueError:
            candidate = root / "index.html"
        if not candidate.is_file():
            candidate = root / "index.html"
        if not candidate.is_file():
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "Chưa build giao diện (npm run build trong ui/)"})
            return
        self._send_file(candidate, cache="/assets/" in candidate.as_posix())

    # ---- định tuyến ------------------------------------------------------------------------------------

    def _dispatch(self, method: str) -> None:
        parts = urlsplit(self.path)
        query = parse_qs(parts.query)
        try:
            if not self._allowed_host():
                raise ApiError(HTTPStatus.FORBIDDEN, "Host không hợp lệ")
            path = parts.path
            if not (path.startswith("/api/") or path.startswith("/media/")):
                if method not in ("GET", "HEAD"):
                    raise ApiError(HTTPStatus.METHOD_NOT_ALLOWED, "Không hỗ trợ")
                self._static(path)
                return
            if not self._authorized(query):
                raise ApiError(HTTPStatus.UNAUTHORIZED, "Thiếu mã phiên")
            for verb, pattern, handler in ROUTES:
                if verb != method and not (verb == "GET" and method == "HEAD"):
                    continue
                match = pattern.fullmatch(path)
                if match:
                    handler(self, query, *[unquote(group) for group in match.groups()])
                    return
            raise ApiError(HTTPStatus.NOT_FOUND, "Không có đường dẫn này")
        except ApiError as error:
            self._send_json(error.status, {"error": error.message})
        except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError):
            return
        except FileNotFoundError as error:
            self._send_json(HTTPStatus.NOT_FOUND, {"error": f"Không thấy file: {error}"})
        except ValueError as error:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(error)})
        except Exception as error:  # noqa: BLE001 - lỗi bất kỳ vẫn phải về thành JSON cho giao diện
            self._send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": f"{type(error).__name__}: {error}"})

    def do_GET(self) -> None:  # noqa: N802
        self._dispatch("GET")

    def do_HEAD(self) -> None:  # noqa: N802
        self._dispatch("HEAD")

    def do_POST(self) -> None:  # noqa: N802
        self._dispatch("POST")

    def do_PUT(self) -> None:  # noqa: N802
        self._dispatch("PUT")

    def do_DELETE(self) -> None:  # noqa: N802
        self._dispatch("DELETE")

    # ---- các đường dẫn ---------------------------------------------------------------------------------

    def get_app(self, _query: dict[str, list[str]]) -> None:
        prefs = self.app.preferences.get()
        self._send_json(HTTPStatus.OK, {
            "version": self.app.version,
            "readOnly": self.app.read_only,
            "dialogs": self.app.dialogs is not None,
            "libraryRoot": prefs["libraryRoot"],
            "theme": prefs["theme"],
            "playbackRate": prefs["playbackRate"],
            "volume": prefs["volume"],
            "sleepFadeSeconds": prefs.get("sleepFadeSeconds", 30),
            "sleepExtendMinutes": prefs.get("sleepExtendMinutes", 10),
            "safetyStopHours": prefs.get("safetyStopHours", 2),
            "sleepSchedule": prefs.get("sleepSchedule"),
        })

    def get_library(self, _query: dict[str, list[str]]) -> None:
        self._send_json(HTTPStatus.OK, self.app.library_view())

    def get_book(self, _query: dict[str, list[str]], value: str) -> None:
        self._send_json(HTTPStatus.OK, self.app.book_view(value))

    def get_cast(self, _query: dict[str, list[str]], value: str) -> None:
        self._send_json(HTTPStatus.OK, store.cast(self.app._book(value)))

    def get_activity(self, query: dict[str, list[str]], value: str) -> None:
        technical = (query.get("technical") or ["0"])[0] == "1"
        self._send_json(HTTPStatus.OK, store.activity(self.app._book(value), technical=technical))

    def get_script(self, _query: dict[str, list[str]], value: str, chapter: str) -> None:
        script = store.chapter_script(self.app._book(value), int(chapter))
        if script is None:
            raise ApiError(HTTPStatus.NOT_FOUND, "Không có chương này")
        self._send_json(HTTPStatus.OK, script)

    def post_start(self, _query: dict[str, list[str]], value: str) -> None:
        self._send_json(HTTPStatus.ACCEPTED, self.app.start(value))

    def post_stop(self, _query: dict[str, list[str]], value: str) -> None:
        self._send_json(HTTPStatus.ACCEPTED, self.app.stop(value))

    def post_reveal(self, _query: dict[str, list[str]], value: str) -> None:
        actions.reveal(self.app._book(value))
        self._send_json(HTTPStatus.OK, {"ok": True})

    def post_export(self, _query: dict[str, list[str]], value: str) -> None:
        from .export import export_book

        project = self.app._book(value)
        body = self._body()
        target = str(body.get("target") or "").strip()
        root = Path(target) if target else Path(self.app.preferences.get()["libraryRoot"]) / "Đã xuất"
        try:
            result = export_book(project, root, cover=body.get("cover"))
        except ValueError as error:
            raise ApiError(HTTPStatus.CONFLICT, str(error)) from error
        self.app.exports.add(result["folder"])
        self._send_json(HTTPStatus.OK, result)

    def get_review(self, query: dict[str, list[str]], value: str) -> None:
        project = self.app._book(value)
        verdicts = self.app.reviews.get(value)
        self._send_json(HTTPStatus.OK, review_view(project, verdicts, include_minor=query.get("all") == ["1"]))

    def post_review(self, _query: dict[str, list[str]], value: str) -> None:
        self.app._book(value)
        body = self._body()
        verdict = body.get("verdict")
        if verdict not in (None, "ok", "redo"):
            raise ApiError(HTTPStatus.BAD_REQUEST, "Phán quyết không hợp lệ")
        self.app.reviews.set(value, str(body.get("stableId", ""))[:80], verdict, int(body.get("chapterId", 0)))
        self._send_json(HTTPStatus.OK, {"ok": True})

    def post_reveal_export(self, _query: dict[str, list[str]]) -> None:
        folder = str(self._body().get("folder", ""))
        if folder not in self.app.exports:
            raise ApiError(HTTPStatus.FORBIDDEN, "Không mở được thư mục này")
        actions.reveal(Path(folder))
        self._send_json(HTTPStatus.OK, {"ok": True})

    def get_sync(self, _query: dict[str, list[str]]) -> None:
        self._send_json(HTTPStatus.OK, self.app.sync_view())

    def post_sync(self, _query: dict[str, list[str]]) -> None:
        self._mutating_guard()
        self._send_json(HTTPStatus.OK, self.app.set_sync(bool(self._body().get("enabled"))))

    def post_sync_pairing(self, _query: dict[str, list[str]]) -> None:
        self._mutating_guard()
        if self.app.sync_server is None:
            raise ApiError(HTTPStatus.CONFLICT, "Bật đồng bộ trước rồi mới ghép điện thoại")
        self.app.devices.start_pairing()
        self._send_json(HTTPStatus.OK, self.app.sync_view())

    def delete_sync_pairing(self, _query: dict[str, list[str]]) -> None:
        self.app.devices.cancel_pairing()
        self._send_json(HTTPStatus.OK, self.app.sync_view())

    def delete_sync_device(self, _query: dict[str, list[str]], device: str) -> None:
        self._mutating_guard()
        self.app.devices.revoke(device)
        self._send_json(HTTPStatus.OK, self.app.sync_view())

    def _mutating_guard(self) -> None:
        if self.app.read_only:
            raise ApiError(HTTPStatus.FORBIDDEN, "Giao diện đang ở chế độ chỉ xem")

    def get_listen_library(self, _query: dict[str, list[str]]) -> None:
        self._send_json(HTTPStatus.OK, self.app.listen_library())

    def get_listen_book(self, _query: dict[str, list[str]], value: str) -> None:
        self._send_json(HTTPStatus.OK, self.app.listen_book(value))

    def post_progress(self, _query: dict[str, list[str]], value: str) -> None:
        self.app._book(value)
        body = self._body()
        state = self.app.listening.progress(
            value, int(body.get("chapterId", 0)), float(body.get("seconds", 0)), float(body.get("duration", 0))
        )
        self._send_json(HTTPStatus.OK, state)

    def post_chapter_done(self, _query: dict[str, list[str]], value: str, chapter: str) -> None:
        self.app._book(value)
        state = self.app.listening.set_chapter_done(value, int(chapter), bool(self._body().get("done", True)))
        self._send_json(HTTPStatus.OK, state)

    def post_finished(self, _query: dict[str, list[str]], value: str) -> None:
        self.app._book(value)
        self._send_json(HTTPStatus.OK, self.app.listening.set_finished(value, bool(self._body().get("finished", True))))

    def post_rate(self, _query: dict[str, list[str]], value: str) -> None:
        self.app._book(value)
        self.app.listening.set_rate(value, float(self._body().get("rate", 1.0)))
        self._send_json(HTTPStatus.OK, {"ok": True})

    def post_bookmark(self, _query: dict[str, list[str]], value: str) -> None:
        self.app._book(value)
        body = self._body()
        mark = self.app.listening.add_bookmark(
            value, int(body.get("chapterId", 0)), float(body.get("seconds", 0)), str(body.get("note", ""))
        )
        self._send_json(HTTPStatus.CREATED, mark)

    def put_bookmark(self, _query: dict[str, list[str]], value: str, mark: str) -> None:
        self.app._book(value)
        self.app.listening.update_bookmark(value, mark, str(self._body().get("note", "")))
        self._send_json(HTTPStatus.OK, {"ok": True})

    def delete_bookmark(self, _query: dict[str, list[str]], value: str, mark: str) -> None:
        self.app._book(value)
        self.app.listening.delete_bookmark(value, mark)
        self._send_json(HTTPStatus.OK, {"ok": True})

    def post_bookmark_restore(self, _query: dict[str, list[str]], value: str) -> None:
        self.app._book(value)
        body = self._body()
        if not re.fullmatch(r"[0-9a-f]{6,40}", str(body.get("id", ""))):
            raise ApiError(HTTPStatus.BAD_REQUEST, "Dấu trang không hợp lệ")
        self._send_json(HTTPStatus.OK, self.app.listening.restore_bookmark(value, body))

    def get_sessions(self, _query: dict[str, list[str]], value: str) -> None:
        self.app._book(value)
        self._send_json(HTTPStatus.OK, self.app.listening.sessions(value))

    def post_session(self, _query: dict[str, list[str]], value: str) -> None:
        self.app._book(value)
        self.app.listening.add_session(value, self._body())
        self._send_json(HTTPStatus.OK, {"ok": True})

    def post_reading(self, _query: dict[str, list[str]], value: str) -> None:
        self.app._book(value)
        body = self._body()
        self.app.listening.set_reading(value, int(body.get("chapterId", 0)), int(body.get("index", 0)))
        self._send_json(HTTPStatus.OK, {"ok": True})

    def post_night(self, _query: dict[str, list[str]], value: str) -> None:
        self.app._book(value)
        self.app.listening.save_night(value, self._body())
        self._send_json(HTTPStatus.OK, {"ok": True})

    def get_night(self, _query: dict[str, list[str]]) -> None:
        self._send_json(HTTPStatus.OK, self.app.listening.latest_night())

    def post_night_dismiss(self, _query: dict[str, list[str]]) -> None:
        body = self._body()
        self.app.listening.dismiss_night(str(body.get("bookId", "")), str(body.get("id", "")))
        self._send_json(HTTPStatus.OK, {"ok": True})

    def post_open(self, _query: dict[str, list[str]]) -> None:
        self._send_json(HTTPStatus.OK, self.app.open_existing(self._body()))

    def post_create(self, _query: dict[str, list[str]]) -> None:
        self._send_json(HTTPStatus.CREATED, self.app.create(self._body()))

    def post_scan(self, _query: dict[str, list[str]]) -> None:
        body = self._body()
        self._send_json(HTTPStatus.OK, actions.scan_inputs([str(item) for item in body.get("paths", [])]))

    def get_voices(self, _query: dict[str, list[str]]) -> None:
        self._send_json(HTTPStatus.OK, self.app.voices())

    def get_preferences(self, _query: dict[str, list[str]]) -> None:
        self._send_json(HTTPStatus.OK, self.app.preferences.get())

    def put_preferences(self, _query: dict[str, list[str]]) -> None:
        body = self._body()
        allowed = {key: body[key] for key in ("theme", "libraryRoot", "playbackRate", "volume") if key in body}
        # Hai tuỳ chọn hẹn giờ ngủ chỉ nhận đúng các mức giao diện đưa ra.
        if body.get("sleepFadeSeconds") in (10, 30, 60):
            allowed["sleepFadeSeconds"] = body["sleepFadeSeconds"]
        if body.get("sleepExtendMinutes") in (5, 10, 15):
            allowed["sleepExtendMinutes"] = body["sleepExtendMinutes"]
        if body.get("safetyStopHours") in (0, 1, 2, 3):
            allowed["safetyStopHours"] = body["safetyStopHours"]
        if "sleepSchedule" in body:
            schedule = body["sleepSchedule"]
            clock = re.compile(r"([01]\d|2[0-3]):[0-5]\d")
            if schedule is None:
                allowed["sleepSchedule"] = None
            elif (isinstance(schedule, dict) and clock.fullmatch(str(schedule.get("from", "")))
                  and clock.fullmatch(str(schedule.get("to", ""))) and schedule.get("minutes") in (15, 30, 45, 60)):
                allowed["sleepSchedule"] = {"from": schedule["from"], "to": schedule["to"], "minutes": schedule["minutes"]}
        self._send_json(HTTPStatus.OK, self.app.preferences.update(allowed))

    def post_pick_folder(self, _query: dict[str, list[str]]) -> None:
        if self.app.dialogs is None:
            raise ApiError(HTTPStatus.NOT_IMPLEMENTED, "Không có hộp thoại chọn thư mục ở chế độ này")
        body = self._body()
        path = self.app.dialogs.pick_folder(str(body.get("title", "Chọn thư mục")), str(body.get("start", "")))
        self._send_json(HTTPStatus.OK, {"path": path})

    def post_pick_files(self, _query: dict[str, list[str]]) -> None:
        if self.app.dialogs is None:
            raise ApiError(HTTPStatus.NOT_IMPLEMENTED, "Không có hộp thoại chọn file ở chế độ này")
        body = self._body()
        paths = self.app.dialogs.pick_files(str(body.get("title", "Chọn file TXT")), str(body.get("start", "")))
        self._send_json(HTTPStatus.OK, {"paths": paths})

    def media_voice(self, _query: dict[str, list[str]], name: str) -> None:
        path = self.app.voice_file(name)
        if path is None:
            raise ApiError(HTTPStatus.NOT_FOUND, "Không có bản nghe thử cho giọng này")
        self._send_file(path, cache=True)

    def media_chapter(self, _query: dict[str, list[str]], value: str, chapter: str) -> None:
        path = store.chapter_audio_path(self.app._book(value), int(chapter))
        if path is None:
            raise ApiError(HTTPStatus.NOT_FOUND, "Chương này chưa nghe được")
        self._send_file(path)

    def media_sample(self, _query: dict[str, list[str]], value: str, segment: str) -> None:
        path = store.sample_audio_path(self.app._book(value), int(segment))
        if path is None:
            raise ApiError(HTTPStatus.NOT_FOUND, "Không có câu mẫu")
        self._send_file(path)


BOOK = r"/api/books/([A-Za-z0-9_-]+)"
LISTEN = r"/api/listen/books/([A-Za-z0-9_-]+)"
ROUTES: list[Route] = [
    ("GET", re.compile(r"/api/app"), Handler.get_app),
    ("GET", re.compile(r"/api/library"), Handler.get_library),
    ("GET", re.compile(r"/api/voices"), Handler.get_voices),
    ("GET", re.compile(r"/api/preferences"), Handler.get_preferences),
    ("PUT", re.compile(r"/api/preferences"), Handler.put_preferences),
    ("POST", re.compile(r"/api/scan"), Handler.post_scan),
    ("POST", re.compile(r"/api/books"), Handler.post_create),
    ("POST", re.compile(r"/api/books/open"), Handler.post_open),
    ("POST", re.compile(r"/api/dialog/folder"), Handler.post_pick_folder),
    ("POST", re.compile(r"/api/dialog/files"), Handler.post_pick_files),
    ("GET", re.compile(BOOK), Handler.get_book),
    ("GET", re.compile(BOOK + r"/cast"), Handler.get_cast),
    ("GET", re.compile(BOOK + r"/activity"), Handler.get_activity),
    ("GET", re.compile(BOOK + r"/chapters/(\d+)/script"), Handler.get_script),
    ("POST", re.compile(BOOK + r"/start"), Handler.post_start),
    ("POST", re.compile(BOOK + r"/stop"), Handler.post_stop),
    ("POST", re.compile(BOOK + r"/reveal"), Handler.post_reveal),
    ("POST", re.compile(BOOK + r"/export"), Handler.post_export),
    ("GET", re.compile(BOOK + r"/review"), Handler.get_review),
    ("POST", re.compile(BOOK + r"/review"), Handler.post_review),
    ("POST", re.compile(r"/api/reveal-export"), Handler.post_reveal_export),
    ("GET", re.compile(r"/api/sync"), Handler.get_sync),
    ("POST", re.compile(r"/api/sync"), Handler.post_sync),
    ("POST", re.compile(r"/api/sync/pairing"), Handler.post_sync_pairing),
    ("DELETE", re.compile(r"/api/sync/pairing"), Handler.delete_sync_pairing),
    ("DELETE", re.compile(r"/api/sync/devices/([0-9a-f]+)"), Handler.delete_sync_device),
    ("GET", re.compile(r"/api/listen/library"), Handler.get_listen_library),
    ("GET", re.compile(LISTEN), Handler.get_listen_book),
    ("POST", re.compile(LISTEN + r"/progress"), Handler.post_progress),
    ("POST", re.compile(LISTEN + r"/chapters/(\d+)/done"), Handler.post_chapter_done),
    ("POST", re.compile(LISTEN + r"/finished"), Handler.post_finished),
    ("POST", re.compile(LISTEN + r"/rate"), Handler.post_rate),
    ("POST", re.compile(LISTEN + r"/bookmarks"), Handler.post_bookmark),
    ("PUT", re.compile(LISTEN + r"/bookmarks/([0-9a-f]+)"), Handler.put_bookmark),
    ("DELETE", re.compile(LISTEN + r"/bookmarks/([0-9a-f]+)"), Handler.delete_bookmark),
    ("POST", re.compile(LISTEN + r"/bookmarks/restore"), Handler.post_bookmark_restore),
    ("POST", re.compile(LISTEN + r"/night"), Handler.post_night),
    ("POST", re.compile(LISTEN + r"/reading"), Handler.post_reading),
    ("GET", re.compile(LISTEN + r"/sessions"), Handler.get_sessions),
    ("POST", re.compile(LISTEN + r"/sessions"), Handler.post_session),
    ("GET", re.compile(r"/api/listen/night"), Handler.get_night),
    ("POST", re.compile(r"/api/listen/night/dismiss"), Handler.post_night_dismiss),
    ("GET", re.compile(r"/media/voices/([^/]+)"), Handler.media_voice),
    ("GET", re.compile(r"/media/books/([A-Za-z0-9_-]+)/chapters/(\d+)"), Handler.media_chapter),
    ("GET", re.compile(r"/media/books/([A-Za-z0-9_-]+)/samples/(\d+)"), Handler.media_sample),
]


class Server:
    """Server chạy trên một luồng nền; `url` là địa chỉ để cửa sổ (hoặc trình duyệt khi phát triển) mở."""

    def __init__(self, app: App, *, port: int = 0) -> None:
        handler = type("BoundHandler", (Handler,), {"app": app})
        self.httpd = ExclusiveHTTPServer(("127.0.0.1", port), handler)
        handler.port = self.httpd.server_address[1]
        self.app = app
        self.port = int(self.httpd.server_address[1])
        self._thread: threading.Thread | None = None

    @property
    def url(self) -> str:
        suffix = f"?t={self.app.token}" if self.app.token else ""
        return f"http://127.0.0.1:{self.port}/{suffix}"

    def start(self) -> "Server":
        self._thread = threading.Thread(target=self.httpd.serve_forever, name="webui", daemon=True)
        self._thread.start()
        return self

    def stop(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()


def new_token() -> str:
    return secrets.token_urlsafe(24)



def socket_name() -> str:
    """Tên máy hiện trên điện thoại khi tìm thấy nó."""
    import socket

    return socket.gethostname() or "Máy tính"

