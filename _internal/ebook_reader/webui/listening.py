"""Trạng thái NGHE của người dùng: đã nghe tới đâu từng chương, dấu trang, tốc độ riêng mỗi cuốn.

Tách khỏi dữ liệu sản xuất (SQLite của sách là của dây chuyền, giao diện không ghi vào đó) và khỏi tuỳ chọn app.
Cùng một hình dạng với trạng thái mà trình phát Android giữ trên điện thoại, để hai bên đồng bộ được với nhau
(`merge`: mỗi mục mang mốc thời gian, mục mới hơn thắng; dấu trang hợp theo id).

    {"<bookId>": {
        "last": {"chapterId": 3, "seconds": 812.4, "at": 1790...},
        "chapters": {"3": {"heard": 812.4, "done": false, "at": ...}},
        "rate": 1.25,
        "finished": false,
        "bookmarks": [{"id": "...", "chapterId": 3, "seconds": 64.0, "note": "", "at": ...}],
        "updatedAt": ...}}
"""
from __future__ import annotations

import json
import os
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from .library import preferences_path

# Nghe tới cách cuối chương dưới 20 giây là coi như nghe xong chương (đoạn cuối thường là khoảng lặng + lời
# chuyển chương, người nghe hay bấm sang chương kế trước khi nó hết).
DONE_TAIL_SECONDS = 20.0


def listening_path() -> Path:
    return preferences_path().with_name("listening.json")


class Listening:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or listening_path()
        self._lock = threading.Lock()
        try:
            self._data: dict[str, Any] = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            self._data = {}

    def _book(self, book: str) -> dict[str, Any]:
        entry = self._data.setdefault(book, {})
        entry.setdefault("chapters", {})
        entry.setdefault("bookmarks", [])
        return entry

    def get(self, book: str) -> dict[str, Any]:
        with self._lock:
            return json.loads(json.dumps(self._data.get(book) or {"chapters": {}, "bookmarks": []}))

    def all(self) -> dict[str, Any]:
        with self._lock:
            return json.loads(json.dumps(self._data))

    def progress(self, book: str, chapter_id: int, seconds: float, duration: float) -> dict[str, Any]:
        now = time.time()
        with self._lock:
            entry = self._book(book)
            entry["last"] = {"chapterId": int(chapter_id), "seconds": round(float(seconds), 1), "at": now}
            chapter = entry["chapters"].setdefault(str(int(chapter_id)), {"heard": 0.0, "done": False})
            chapter["heard"] = round(max(float(chapter.get("heard", 0.0)), float(seconds)), 1)
            if duration > 0 and duration - float(seconds) <= DONE_TAIL_SECONDS:
                chapter["done"] = True
            chapter["duration"] = round(float(duration), 1) if duration > 0 else chapter.get("duration", 0)
            chapter["at"] = now
            entry["updatedAt"] = now
            self._save()
            return json.loads(json.dumps(entry))

    def set_chapter_done(self, book: str, chapter_id: int, done: bool) -> dict[str, Any]:
        with self._lock:
            entry = self._book(book)
            chapter = entry["chapters"].setdefault(str(int(chapter_id)), {"heard": 0.0, "done": False})
            chapter["done"] = bool(done)
            if not done:
                chapter["heard"] = 0.0
            chapter["at"] = entry["updatedAt"] = time.time()
            self._save()
            return json.loads(json.dumps(entry))

    def set_finished(self, book: str, finished: bool) -> dict[str, Any]:
        with self._lock:
            entry = self._book(book)
            entry["finished"] = bool(finished)
            entry["finishedAt"] = entry["updatedAt"] = time.time()
            self._save()
            return json.loads(json.dumps(entry))

    def set_rate(self, book: str, rate: float) -> None:
        with self._lock:
            entry = self._book(book)
            entry["rate"] = float(rate)
            entry["rateAt"] = entry["updatedAt"] = time.time()
            self._save()

    def add_bookmark(self, book: str, chapter_id: int, seconds: float, note: str = "") -> dict[str, Any]:
        mark = {"id": uuid.uuid4().hex[:12], "chapterId": int(chapter_id), "seconds": round(float(seconds), 1),
                "note": note.strip()[:500], "at": time.time()}
        with self._lock:
            entry = self._book(book)
            entry["bookmarks"].append(mark)
            entry["updatedAt"] = mark["at"]
            self._save()
        return mark

    def update_bookmark(self, book: str, mark_id: str, note: str) -> None:
        with self._lock:
            entry = self._book(book)
            for mark in entry["bookmarks"]:
                if mark["id"] == mark_id:
                    mark["note"] = note.strip()[:500]
            entry["updatedAt"] = time.time()
            self._save()

    def delete_bookmark(self, book: str, mark_id: str) -> None:
        with self._lock:
            entry = self._book(book)
            entry["bookmarks"] = [mark for mark in entry["bookmarks"] if mark["id"] != mark_id]
            entry.setdefault("deleted", {})[mark_id] = time.time()
            entry["updatedAt"] = time.time()
            self._save()

    def merge(self, book: str, incoming: dict[str, Any]) -> dict[str, Any]:
        """Gộp trạng thái từ thiết bị khác (điện thoại). Mỗi phần mang mốc thời gian riêng, bên mới hơn thắng;
        dấu trang hợp theo id, dấu trang đã xoá ở một bên (tombstone) thì xoá ở cả hai."""
        with self._lock:
            entry = self._book(book)
            merged = merge_states(entry, incoming)
            self._data[book] = merged
            self._save()
            return json.loads(json.dumps(merged))

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(self._data, ensure_ascii=False, indent=1), encoding="utf-8")
        os.replace(temporary, self.path)


def book_progress(state: dict[str, Any], chapters: list[dict[str, Any]]) -> dict[str, Any]:
    """Đã nghe bao nhiêu phần của cuốn: tính theo thời lượng, chương đánh dấu xong tính trọn."""
    total = sum(float(chapter.get("duration") or 0.0) for chapter in chapters)
    heard = 0.0
    done_chapters = 0
    for chapter in chapters:
        record = state.get("chapters", {}).get(str(chapter["id"]))
        length = float(chapter.get("duration") or 0.0)
        if not record:
            continue
        if record.get("done"):
            heard += length
            done_chapters += 1
        else:
            heard += min(length, float(record.get("heard") or 0.0))
    return {
        "heardSeconds": round(heard, 1),
        "totalSeconds": round(total, 1),
        "fraction": round(heard / total, 4) if total else 0.0,
        "chaptersDone": done_chapters,
        "finished": bool(state.get("finished")) or (bool(chapters) and done_chapters == len(chapters)),
    }


def merge_states(ours: dict[str, Any], theirs: dict[str, Any]) -> dict[str, Any]:
    result = json.loads(json.dumps(ours))
    result.setdefault("chapters", {})
    result.setdefault("bookmarks", [])
    if (theirs.get("last") or {}).get("at", 0) > (result.get("last") or {}).get("at", 0):
        result["last"] = theirs["last"]
    for key, record in (theirs.get("chapters") or {}).items():
        mine = result["chapters"].get(key)
        if not mine or float(record.get("at") or 0) > float(mine.get("at") or 0):
            result["chapters"][key] = record
    for field, stamp in (("rate", "rateAt"), ("finished", "finishedAt")):
        if field in theirs and float(theirs.get(stamp) or 0) > float(result.get(stamp) or 0):
            result[field] = theirs[field]
            result[stamp] = theirs[stamp]
    deleted = dict(result.get("deleted") or {})
    deleted.update(theirs.get("deleted") or {})
    marks = {mark["id"]: mark for mark in result["bookmarks"]}
    for mark in theirs.get("bookmarks") or []:
        current = marks.get(mark["id"])
        if not current or float(mark.get("at") or 0) >= float(current.get("at") or 0):
            marks[mark["id"]] = mark
    result["bookmarks"] = sorted((mark for mark in marks.values() if mark["id"] not in deleted),
                                 key=lambda mark: mark.get("at") or 0)
    result["deleted"] = deleted
    result["updatedAt"] = max(float(result.get("updatedAt") or 0), float(theirs.get("updatedAt") or 0))
    return result
