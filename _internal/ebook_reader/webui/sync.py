"""Đồng bộ sách sang điện thoại qua Wi-Fi: tìm máy, ghép nối, tải gói sách, đồng bộ chỗ đang nghe.

Tách hẳn khỏi server giao diện (chỉ nghe 127.0.0.1): server này nghe trên mạng LAN nên chỉ mở đúng các đường
đồng bộ, mọi yêu cầu (trừ ghép nối) phải mang mã thiết bị, và chỉ chạy khi người dùng bật "Cho phép điện thoại kết
nối" trong Cài đặt. Không dùng thư viện ngoài (zeroconf...): thêm gói Python là đổi `uv.lock`, tức đổi hash chất
lượng của dây chuyền giữa cuốn sách. Tìm máy bằng UDP broadcast, thư viện chuẩn là đủ.

Gói sách (`book.json`) cùng hình dạng với phía Nghe trên máy tính (listen_view.py), cộng đường dẫn file:

    chapters/<tên>.mp3      audio chương
    scripts/<chapterId>.json  văn bản + mốc thời gian để đọc theo
    cast.json               dàn nhân vật
    samples/<segmentId>.wav   câu mẫu của từng nhân vật
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import socket
import threading
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit

from . import listen_view, store
from .library import Library, book_id
from .listening import Listening

SYNC_PORT = 47630
DISCOVERY_PORT = 47631
DISCOVERY_PROBE = b"EBOOKREADER_DISCOVER"
PAIRING_SECONDS = 300
CHUNK = 256 * 1024
MAX_BODY = 2 * 1024 * 1024


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class Devices:
    """Điện thoại đã ghép nối: lưu băm của mã (không lưu mã thật), tên, lần thấy cuối."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = threading.Lock()
        try:
            self._data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            self._data = {"devices": {}}
        self._pairing: tuple[str, float] | None = None

    def pairing_code(self, *, renew: bool = False) -> dict[str, Any]:
        with self._lock:
            now = time.time()
            if renew or self._pairing is None or self._pairing[1] <= now:
                self._pairing = (f"{secrets.randbelow(10**6):06d}", now + PAIRING_SECONDS)
            return {"code": self._pairing[0], "expiresAt": self._pairing[1]}

    def pair(self, code: str, name: str) -> str | None:
        with self._lock:
            if not self._pairing or self._pairing[1] <= time.time():
                return None
            if not secrets.compare_digest(code.strip(), self._pairing[0]):
                return None
            self._pairing = None  # mã dùng một lần
            token = secrets.token_urlsafe(32)
            self._data["devices"][_hash(token)] = {"name": name.strip()[:80] or "Điện thoại",
                                                   "pairedAt": time.time(), "lastSeen": time.time()}
            self._save()
            return token

    def check(self, token: str) -> bool:
        key = _hash(token)
        with self._lock:
            device = self._data["devices"].get(key)
            if device is None:
                return False
            if time.time() - device.get("lastSeen", 0) > 60:
                device["lastSeen"] = time.time()
                self._save()
            return True

    def list(self) -> list[dict[str, Any]]:
        with self._lock:
            return [{"id": key[:12], **value} for key, value in self._data["devices"].items()]

    def revoke(self, short_id: str) -> None:
        with self._lock:
            self._data["devices"] = {key: value for key, value in self._data["devices"].items() if key[:12] != short_id}
            self._save()

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(self._data, ensure_ascii=False, indent=1), encoding="utf-8")
        os.replace(temporary, self.path)


def manifest(project_root: Path, book: str, listening: Listening) -> dict[str, Any]:
    """`book.json` của một cuốn: chỉ các chương ĐÃ nghe được, kèm tên file để điện thoại tải về."""
    summary = store.summarize(project_root)
    summary["id"] = book
    view = listen_view.book(project_root, book, summary, listening.get(book))
    chapters = []
    for chapter in view.get("chapters", []):
        path = store.chapter_audio_path(project_root, chapter["id"]) if chapter["available"] else None
        chapters.append({
            **chapter,
            "available": path is not None,
            "file": f"chapters/{path.name}" if path else None,
            "size": path.stat().st_size if path else 0,
            "script": f"scripts/{chapter['id']}.json" if path else None,
        })
    cast = store.cast(project_root)
    samples = sorted({person["sampleId"] for person in cast["characters"] + cast["extras"] if person.get("sampleId")})
    version = hashlib.sha256(json.dumps([(c["id"], c["size"]) for c in chapters]).encode()).hexdigest()[:16]
    return {
        "format": listen_view.FORMAT,
        "id": book,
        "title": view["title"],
        "narrator": view["narrator"],
        "duration": view["duration"],
        "chaptersTotal": view["chaptersTotal"],
        "chaptersAvailable": sum(1 for chapter in chapters if chapter["available"]),
        "complete": view["complete"],
        "version": version,
        "chapters": chapters,
        "cast": "cast.json",
        "samples": [f"samples/{sample}.wav" for sample in samples],
    }


class SyncApp:
    def __init__(self, library: Library, listening: Listening, devices: Devices, name: str) -> None:
        self.library = library
        self.listening = listening
        self.devices = devices
        self.name = name

    def book(self, value: str) -> Path | None:
        return self.library.resolve(value)

    def library_view(self) -> list[dict[str, Any]]:
        out = []
        for path in self.library.projects():
            try:
                summary = store.summarize(path)
            except Exception:  # noqa: BLE001 - sách hỏng không làm hỏng danh sách
                continue
            if summary["chapters"]["completed"] <= 0:
                continue
            identifier = book_id(path)
            summary["id"] = identifier
            view = listen_view.book(path, identifier, summary, self.listening.get(identifier), with_chapters=False)
            out.append({key: view[key] for key in ("id", "title", "narrator", "duration", "chaptersTotal",
                                                    "chaptersAvailable", "complete", "updatedAt")})
        return out

    def resolve_file(self, project_root: Path, relative: str) -> Path | bytes | None:
        """Đường dẫn file của gói (chỉ các tên trong manifest; không đi ra ngoài thư mục sách)."""
        if relative == "cast.json":
            return json.dumps(store.cast(project_root), ensure_ascii=False).encode("utf-8")
        match = re.fullmatch(r"scripts/(\d+)\.json", relative)
        if match:
            script = store.chapter_script(project_root, int(match.group(1)))
            return json.dumps(script, ensure_ascii=False).encode("utf-8") if script else None
        match = re.fullmatch(r"samples/(\d+)\.wav", relative)
        if match:
            cast = store.cast(project_root)
            allowed = {person.get("sampleId") for person in cast["characters"] + cast["extras"]}
            return store.sample_audio_path(project_root, int(match.group(1))) if int(match.group(1)) in allowed else None
        match = re.fullmatch(r"chapters/([^/\\]+\.mp3)", relative)
        if match:
            for chapter in store.chapters(project_root):
                path = store.chapter_audio_path(project_root, chapter["id"]) if chapter["playable"] else None
                if path is not None and path.name == match.group(1):
                    return path
        return None


class SyncHandler(BaseHTTPRequestHandler):
    server_version = "EbookReaderSync"
    protocol_version = "HTTP/1.1"
    app: SyncApp

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        return

    def _json(self, status: int, payload: Any) -> None:
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
            return {}
        try:
            data = json.loads(self.rfile.read(length).decode("utf-8")) if length else {}
        except (ValueError, UnicodeDecodeError):
            return {}
        return data if isinstance(data, dict) else {}

    def _authorized(self) -> bool:
        header = self.headers.get("Authorization") or ""
        return header.startswith("Bearer ") and self.app.devices.check(header[7:].strip())

    def _file(self, path: Path) -> None:
        size = path.stat().st_size
        start, end, status = 0, size - 1, HTTPStatus.OK
        match = re.match(r"bytes=(\d*)-(\d*)$", self.headers.get("Range") or "")
        if match and size:
            first, last = match.groups()
            if first:
                start = int(first)
                end = min(int(last), size - 1) if last else size - 1
            elif last:
                start = max(0, size - int(last))
            if start > end:
                self.send_response(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE)
                self.send_header("Content-Range", f"bytes */{size}")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            status = HTTPStatus.PARTIAL_CONTENT
        self.send_response(status)
        self.send_header("Content-Type", "audio/mpeg" if path.suffix == ".mp3" else "audio/wav")
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(end - start + 1))
        if status == HTTPStatus.PARTIAL_CONTENT:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.end_headers()
        with path.open("rb") as handle:
            handle.seek(start)
            remaining = end - start + 1
            while remaining > 0:
                chunk = handle.read(min(CHUNK, remaining))
                if not chunk:
                    break
                self.wfile.write(chunk)
                remaining -= len(chunk)

    def _route(self, method: str) -> None:
        path = urlsplit(self.path).path
        try:
            if method == "POST" and path == "/sync/v1/pair":
                body = self._body()
                token = self.app.devices.pair(str(body.get("code", "")), str(body.get("device", "")))
                if token is None:
                    self._json(HTTPStatus.FORBIDDEN, {"error": "Mã ghép nối sai hoặc đã hết hạn"})
                else:
                    self._json(HTTPStatus.OK, {"token": token, "name": self.app.name})
                return
            if not self._authorized():
                self._json(HTTPStatus.UNAUTHORIZED, {"error": "Thiết bị chưa ghép nối"})
                return
            if method == "GET" and path == "/sync/v1/library":
                self._json(HTTPStatus.OK, {"name": self.app.name, "books": self.app.library_view()})
                return
            match = re.fullmatch(r"/sync/v1/books/([A-Za-z0-9_-]+)/(manifest|state|files/(.+))", path)
            project = self.app.book(match.group(1)) if match else None
            if not match or project is None:
                self._json(HTTPStatus.NOT_FOUND, {"error": "Không có sách này"})
                return
            book = match.group(1)
            if method == "GET" and match.group(2) == "manifest":
                self._json(HTTPStatus.OK, manifest(project, book, self.app.listening))
            elif method == "POST" and match.group(2) == "state":
                self._json(HTTPStatus.OK, self.app.listening.merge(book, self._body()))
            elif method == "GET" and match.group(3):
                target = self.app.resolve_file(project, unquote(match.group(3)))
                if target is None:
                    self._json(HTTPStatus.NOT_FOUND, {"error": "Không có file này"})
                elif isinstance(target, bytes):
                    self.send_response(HTTPStatus.OK)
                    self.send_header("Content-Type", "application/json; charset=utf-8")
                    self.send_header("Content-Length", str(len(target)))
                    self.end_headers()
                    self.wfile.write(target)
                else:
                    self._file(target)
            else:
                self._json(HTTPStatus.METHOD_NOT_ALLOWED, {"error": "Không hỗ trợ"})
        except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError):
            return
        except Exception as error:  # noqa: BLE001 - lỗi nào cũng về thành JSON cho điện thoại
            self._json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": f"{type(error).__name__}: {error}"})

    def do_GET(self) -> None:  # noqa: N802
        self._route("GET")

    def do_POST(self) -> None:  # noqa: N802
        self._route("POST")


class Discovery(threading.Thread):
    """Trả lời điện thoại đang tìm máy tính trong cùng mạng Wi-Fi (UDP broadcast)."""

    def __init__(self, name: str, port: int, discovery_port: int = DISCOVERY_PORT) -> None:
        super().__init__(name="sync-discovery", daemon=True)
        self.name_text = name
        self.port = port
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.socket.bind(("0.0.0.0", discovery_port))
        self.socket.settimeout(1.0)
        self._stop = threading.Event()

    def run(self) -> None:
        reply = json.dumps({"app": "ebook-reader", "name": self.name_text, "port": self.port}).encode("utf-8")
        while not self._stop.is_set():
            try:
                data, address = self.socket.recvfrom(512)
            except (TimeoutError, socket.timeout):
                continue
            except OSError:
                break
            if data.strip() == DISCOVERY_PROBE:
                try:
                    self.socket.sendto(reply, address)
                except OSError:
                    pass

    def stop(self) -> None:
        self._stop.set()
        self.socket.close()


class SyncServer:
    """`host="0.0.0.0"` mở cho cả mạng LAN (kèm trả lời tìm máy). Khi phát triển dùng `127.0.0.1`: máy ảo Android
    gọi được qua 10.0.2.2 mà không mở cổng ra mạng, nên Windows không hỏi tường lửa."""

    def __init__(self, app: SyncApp, *, host: str = "0.0.0.0", port: int = SYNC_PORT,
                 discovery_port: int = DISCOVERY_PORT) -> None:
        handler = type("BoundSyncHandler", (SyncHandler,), {"app": app})
        self.httpd = ThreadingHTTPServer((host, port), handler)
        self.httpd.daemon_threads = True
        self.port = int(self.httpd.server_address[1])
        self.discovery = Discovery(app.name, self.port, discovery_port) if host == "0.0.0.0" else None
        self._thread: threading.Thread | None = None

    def start(self) -> "SyncServer":
        self._thread = threading.Thread(target=self.httpd.serve_forever, name="sync", daemon=True)
        self._thread.start()
        if self.discovery:
            self.discovery.start()
        return self

    def stop(self) -> None:
        if self.discovery:
            self.discovery.stop()
        self.httpd.shutdown()
        self.httpd.server_close()


def local_addresses() -> list[str]:
    """Địa chỉ LAN của máy (để hiện cho người dùng khi điện thoại không tự tìm thấy)."""
    addresses: set[str] = set()
    try:
        probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        probe.connect(("10.255.255.255", 1))
        addresses.add(probe.getsockname()[0])
        probe.close()
    except OSError:
        pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            address = info[4][0]
            if not address.startswith("127."):
                addresses.add(address)
    except OSError:
        pass
    return sorted(addresses)
