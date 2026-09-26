"""Việc giao diện làm thay người dùng: quét nguồn, tạo sách, chạy, dừng, mở thư mục.

Chạy sách đi đúng đường của CLI và dây chuyền sản xuất: `background_runner.start_background` - supervisor
tách rời, nên đóng cửa sổ (hay cửa sổ sập) không dừng sách, và "Dừng" là `request_stop` (worker dừng ở ranh giới
gần nhất; AGENTS.md: GUI chỉ có MỘT lệnh Dừng).

`FakeRunner` cho lúc phát triển giao diện: bấm "Bắt đầu" không được khởi động worker thật trên máy đang sản xuất
(nó sẽ tranh GPU với lô đang chạy).
"""
from __future__ import annotations

import os
import subprocess
import threading
import time
from pathlib import Path
from typing import Any, Callable, Protocol

from ..io_utils import discover_txt_files, natural_key
from . import humanize

# Tiếng Việt đọc ~4,3 âm tiết/giây ở tốc độ kể chuyện; một "từ" tách bằng dấu cách là một âm tiết.
SYLLABLES_PER_SECOND = 4.3
SCAN_WORD_LIMIT_BYTES = 4 * 1024 * 1024


class Runner(Protocol):
    def start(self, project_root: Path) -> None: ...
    def stop(self, project_root: Path) -> None: ...
    def running(self, project_root: Path) -> bool: ...


class BackgroundRunner:
    """Supervisor thật (`background_runner`)."""

    def start(self, project_root: Path) -> None:
        from ..background_runner import start_background

        start_background(project_root)

    def stop(self, project_root: Path) -> None:
        from ..background_runner import request_stop

        request_stop(project_root, wait=False)

    def running(self, project_root: Path) -> bool:
        from ..background_runner import get_status

        try:
            return bool(get_status(project_root).running)
        except Exception:  # noqa: BLE001 - state hỏng thì coi như không chạy; summary vẫn đọc lease
            return False


class FakeRunner:
    """Giả chạy/dừng cho lúc phát triển giao diện - không đụng tiến trình hay file nào của sách."""

    def __init__(self) -> None:
        self._running: set[str] = set()

    def start(self, project_root: Path) -> None:
        time.sleep(1.2)
        self._running.add(str(project_root))

    def stop(self, project_root: Path) -> None:
        self._running.discard(str(project_root))

    def running(self, project_root: Path) -> bool:
        return str(project_root) in self._running


def _count_words(path: Path) -> int:
    try:
        with path.open("rb") as handle:
            raw = handle.read(SCAN_WORD_LIMIT_BYTES)
    except OSError:
        return 0
    for encoding in ("utf-8-sig", "cp1258"):
        try:
            return len(raw.decode(encoding).split())
        except UnicodeDecodeError:
            continue
    return len(raw.decode("utf-8", errors="replace").split())


def _first_line(path: Path) -> str:
    try:
        with path.open("r", encoding="utf-8-sig", errors="replace") as handle:
            for line in handle:
                if line.strip():
                    return line.strip()[:120]
    except OSError:
        pass
    return ""


def scan_inputs(paths: list[str]) -> dict[str, Any]:
    """Những gì người dùng sắp đưa vào sách: file TXT (thư mục chỉ quét một tầng, như app cũ), xếp tự nhiên."""
    files: list[Path] = []
    seen: set[str] = set()
    skipped: list[str] = []
    for item in paths:
        path = Path(item).expanduser()
        candidates = discover_txt_files(path) if path.is_dir() else [path]
        for candidate in candidates:
            if not candidate.is_file() or candidate.suffix.casefold() != ".txt":
                skipped.append(str(candidate))
                continue
            key = os.path.normcase(str(candidate.resolve()))
            if key not in seen:
                seen.add(key)
                files.append(candidate.resolve())
    files.sort(key=lambda path: natural_key(path.name))
    rows = []
    total_words = 0
    for path in files:
        words = _count_words(path)
        total_words += words
        rows.append({
            "path": str(path),
            "name": path.name,
            "title": humanize.chapter_title(path.stem),
            "firstLine": _first_line(path),
            "words": words,
            "bytes": path.stat().st_size,
        })
    title = ""
    if files:
        from ..project import infer_book_title

        title = infer_book_title(files)
    return {
        "files": rows,
        "skipped": skipped,
        "suggestedTitle": title,
        "totals": {
            "chapters": len(rows),
            "words": total_words,
            "audioSeconds": round(total_words / SYLLABLES_PER_SECOND),
        },
    }


def create_book(library_root: Path, paths: list[str], title: str, profile: str, narrator: str) -> Path:
    from ..config import build_settings
    from ..project import create_or_open_project

    files = [Path(row["path"]) for row in scan_inputs(paths)["files"]]
    if not files:
        raise ValueError("Chưa có file TXT nào để làm sách")
    settings = build_settings(profile, {"voices": {"narrator_voice": narrator}} if narrator else None)
    library_root.mkdir(parents=True, exist_ok=True)
    paths_created, _db, _settings = create_or_open_project(files, library_root, settings, title.strip() or None)
    return paths_created.root


class Jobs:
    """Theo dõi các lệnh chạy đang khởi động (start_background đợi worker bắt tay, có thể mất vài giây)."""

    def __init__(self, runner: Runner) -> None:
        self.runner = runner
        self._starting: dict[str, float] = {}
        self._errors: dict[str, str] = {}
        self._lock = threading.Lock()

    def starting(self, project_root: Path) -> bool:
        with self._lock:
            return str(project_root) in self._starting

    def error(self, project_root: Path) -> str:
        with self._lock:
            return self._errors.get(str(project_root), "")

    def start(self, project_root: Path, on_done: Callable[[], None] | None = None) -> None:
        key = str(project_root)
        with self._lock:
            if key in self._starting:
                return
            self._starting[key] = time.time()
            self._errors.pop(key, None)

        def work() -> None:
            try:
                self.runner.start(project_root)
            except Exception as exc:  # noqa: BLE001 - lỗi khởi động phải tới được người dùng
                with self._lock:
                    self._errors[key] = str(exc)
            finally:
                with self._lock:
                    self._starting.pop(key, None)
                if on_done:
                    on_done()

        threading.Thread(target=work, name=f"start {project_root.name}", daemon=True).start()

    def stop(self, project_root: Path) -> None:
        self.runner.stop(project_root)


def reveal(path: Path) -> None:
    """Mở thư mục (hoặc chọn sẵn file) trong File Explorer."""
    if os.name != "nt":
        subprocess.Popen(["xdg-open", str(path if path.is_dir() else path.parent)])
        return
    if path.is_file():
        subprocess.Popen(["explorer", "/select,", str(path)])
    else:
        os.startfile(str(path))  # noqa: S606 - mở thư mục của chính người dùng
