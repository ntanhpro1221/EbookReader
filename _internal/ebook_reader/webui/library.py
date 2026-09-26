"""Thư viện sách và tuỳ chọn của người dùng.

Thư viện = các thư mục sách nằm TRỰC TIẾP trong thư mục thư viện, cộng những sách người dùng tự mở ở nơi khác
("gần đây"). Server chỉ đọc sách nằm trong tập ấy: mã sách là đường dẫn mã hoá, nên không có tập cho phép thì
bất kỳ trang nào gọi được server cũng đọc được mọi file SQLite trên máy.

Tuỳ chọn và vị trí nghe dở lưu ở `%LOCALAPPDATA%/Ebook Reader/preferences.json` - ghi atomic.
"""
from __future__ import annotations

import base64
import json
import os
import threading
import time
from pathlib import Path
from typing import Any

from . import store

DEFAULT_PREFERENCES: dict[str, Any] = {
    "libraryRoot": "",
    "recents": [],
    "theme": "system",
    "positions": {},
    "playbackRate": 1.0,
    "volume": 0.9,
    "syncEnabled": False,
    # Hẹn giờ ngủ: nhỏ dần bao lâu trước khi tắt, và mỗi lần "nghe thêm" cộng bao nhiêu phút.
    "sleepFadeSeconds": 30,
    "sleepExtendMinutes": 10,
    # Lưới an toàn ngủ quên: phát liên tục chừng này giờ không ai chạm máy thì tự dừng (0 = tắt).
    "safetyStopHours": 2,
    # Lịch đêm tự hẹn giờ: {"from": "22:00", "to": "06:00", "minutes": 30} hoặc None.
    "sleepSchedule": None,
}
MAX_RECENTS = 30


def preferences_path() -> Path:
    override = os.environ.get("EBOOK_READER_PREFERENCES")
    if override:
        return Path(override)
    base = os.environ.get("LOCALAPPDATA")
    root = Path(base) / "Ebook Reader" if base else Path.home() / ".ebook_reader"
    return root / "preferences.json"


def _legacy_output_folder() -> str:
    """Thư mục "Nơi lưu" của giao diện cũ (QSettings), để người dùng cũ mở app mới thấy ngay sách của mình."""
    try:
        from PySide6.QtCore import QSettings

        value = QSettings("OpenAI", "EbookReader").value("output", "", str)
        return str(value or "")
    except Exception:  # noqa: BLE001 - không có Qt hoặc registry lỗi: dùng mặc định
        return ""


def book_id(path: Path) -> str:
    return base64.urlsafe_b64encode(str(path).encode("utf-8")).decode("ascii").rstrip("=")


def _decode_id(value: str) -> Path | None:
    try:
        padded = value + "=" * (-len(value) % 4)
        return Path(base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8"))
    except (ValueError, UnicodeError):
        return None


def _key(path: Path) -> str:
    return os.path.normcase(os.path.normpath(str(path)))


class Preferences:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or preferences_path()
        self._lock = threading.Lock()
        self._data = self._load()

    def _load(self) -> dict[str, Any]:
        data = json.loads(json.dumps(DEFAULT_PREFERENCES))
        try:
            data.update(json.loads(self.path.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            pass
        if not data.get("libraryRoot"):
            data["libraryRoot"] = _legacy_output_folder() or str(Path.home() / "Audiobooks")
        return data

    def get(self) -> dict[str, Any]:
        with self._lock:
            return json.loads(json.dumps(self._data))

    def update(self, changes: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            for key, value in changes.items():
                if key in DEFAULT_PREFERENCES:
                    self._data[key] = value
            self._save()
            return json.loads(json.dumps(self._data))

    def remember_position(self, book: str, chapter_id: int, seconds: float, duration: float) -> None:
        with self._lock:
            positions = self._data.setdefault("positions", {})
            positions[book] = {"chapterId": int(chapter_id), "seconds": round(float(seconds), 1),
                               "duration": round(float(duration), 1), "at": time.time()}
            self._save()

    def add_recent(self, path: Path) -> None:
        with self._lock:
            recents = [item for item in self._data.get("recents", []) if _key(Path(item)) != _key(path)]
            self._data["recents"] = [str(path), *recents][:MAX_RECENTS]
            self._save()

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(self._data, ensure_ascii=False, indent=1), encoding="utf-8")
        os.replace(temporary, self.path)


class Library:
    def __init__(self, preferences: Preferences) -> None:
        self.preferences = preferences
        self._cache: dict[str, tuple[float, dict[str, Any]]] = {}
        self._lock = threading.Lock()

    @property
    def root(self) -> Path:
        return Path(self.preferences.get()["libraryRoot"]).expanduser()

    def projects(self) -> list[Path]:
        found: dict[str, Path] = {}
        root = self.root
        try:
            children = sorted(root.iterdir()) if root.is_dir() else []
        except OSError:
            children = []
        for child in children:
            if child.is_dir() and store.is_project(child):
                found.setdefault(_key(child), child.resolve())
        for item in self.preferences.get().get("recents", []):
            path = Path(item)
            if store.is_project(path):
                found.setdefault(_key(path), path.resolve())
        return list(found.values())

    def resolve(self, value: str) -> Path | None:
        path = _decode_id(value)
        if path is None:
            return None
        allowed = {_key(project): project for project in self.projects()}
        return allowed.get(_key(path))

    def summary(self, project: Path, *, running: bool, starting: bool = False) -> dict[str, Any]:
        stamp = store.touched(project)
        key = _key(project)
        with self._lock:
            cached = self._cache.get(key)
        if cached and cached[0] == stamp and not running and not cached[1].get("running") and not starting:
            result = dict(cached[1])
        else:
            result = store.summarize(project, running=running)
            with self._lock:
                self._cache[key] = (stamp, result)
            result = dict(result)
        result["id"] = book_id(project)
        result["starting"] = starting
        position = self.preferences.get().get("positions", {}).get(result["id"])
        result["position"] = position
        return result
