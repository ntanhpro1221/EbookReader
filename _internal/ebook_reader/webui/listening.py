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
        "night": {"id": "...", "startedAt": ..., "endedAt": ..., "events": [...], "timeline": [...]},
        "updatedAt": ...}}

`night` là nhật ký của lần nghe có hẹn giờ ngủ gần nhất (thiết bị nào cũng được): lúc hẹn giờ, những lần chạm, lúc
bắt đầu nhỏ dần, lúc tự dừng - kèm vị trí. Sáng dậy, thẻ "Tối qua" dựng lại từ đó (MorningRecap).
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
# Hai dấu trang cùng chương cách nhau không quá chừng này là một: bấm hai lần liền (hay Space lặp lại nút vừa
# bấm) không được đẻ ra dấu trùng.
BOOKMARK_MERGE_SECONDS = 5.0
# Thẻ "Tối qua" chỉ nói về đêm vừa rồi: nhật ký cũ hơn chừng này thì thôi.
NIGHT_RECENT_SECONDS = 20 * 3600
NIGHT_MAX_POINTS = 480


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
        """Dấu trang mới - hoặc dấu đã có ngay chỗ ấy (±5 giây cùng chương), kèm cờ `existing`."""
        mark = {"id": uuid.uuid4().hex[:12], "chapterId": int(chapter_id), "seconds": round(float(seconds), 1),
                "note": note.strip()[:500], "at": time.time()}
        with self._lock:
            entry = self._book(book)
            for current in entry["bookmarks"]:
                if (int(current.get("chapterId", -1)) == mark["chapterId"]
                        and abs(float(current.get("seconds", 0.0)) - mark["seconds"]) <= BOOKMARK_MERGE_SECONDS):
                    if mark["note"] and not current.get("note"):
                        current["note"] = mark["note"]
                        current["at"] = entry["updatedAt"] = mark["at"]
                        self._save()
                    return {**current, "existing": True}
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

    def restore_bookmark(self, book: str, mark: dict[str, Any]) -> dict[str, Any]:
        """Hoàn tác xoá: đặt lại đúng dấu cũ (cùng id) và gỡ tombstone của nó."""
        with self._lock:
            entry = self._book(book)
            restored = {"id": str(mark["id"])[:40], "chapterId": int(mark["chapterId"]),
                        "seconds": round(float(mark["seconds"]), 1), "note": str(mark.get("note", ""))[:500],
                        "at": time.time()}
            entry["bookmarks"] = [item for item in entry["bookmarks"] if item["id"] != restored["id"]] + [restored]
            (entry.get("deleted") or {}).pop(restored["id"], None)
            entry["updatedAt"] = restored["at"]
            self._save()
            return restored

    def save_night(self, book: str, night: dict[str, Any]) -> None:
        """Nhật ký đêm của trình phát trên máy này (điện thoại gửi của nó qua `merge`)."""
        with self._lock:
            entry = self._book(book)
            entry["night"] = merge_nights(entry.get("night"), _clean_night(night))
            entry["updatedAt"] = time.time()
            self._save()

    def latest_night(self, now: float | None = None) -> dict[str, Any] | None:
        """Đêm gần nhất chưa bị gạt đi, của bất kỳ cuốn nào: `{"bookId", "night"}`."""
        now = time.time() if now is None else now
        with self._lock:
            found: tuple[str, dict[str, Any]] | None = None
            for book, entry in self._data.items():
                night = entry.get("night")
                if not night or night.get("dismissed") or not night.get("events"):
                    continue
                if now - float(night.get("endedAt") or night.get("startedAt") or 0) > NIGHT_RECENT_SECONDS:
                    continue
                if found is None or float(night.get("startedAt") or 0) > float(found[1].get("startedAt") or 0):
                    found = (book, night)
            return None if found is None else json.loads(json.dumps({"bookId": found[0], "night": found[1]}))

    def dismiss_night(self, book: str, night_id: str) -> None:
        with self._lock:
            night = self._book(book).get("night")
            if night and night.get("id") == night_id:
                night["dismissed"] = True
                night["dismissedAt"] = time.time()
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


def book_progress(state: dict[str, Any], chapters: list[dict[str, Any]], *, complete: bool = True) -> dict[str, Any]:
    """Đã nghe bao nhiêu phần của cuốn: tính theo thời lượng, chương đánh dấu xong tính trọn.

    `chapters` là các chương NGHE ĐƯỢC. Sách đang sản xuất dở (`complete=False`) nghe hết phần đã có thì chưa phải
    "nghe xong" - nó "đã theo kịp" (`caughtUp`): trước đây nó lọt vào bộ lọc "Đã xong", rơi khỏi thẻ "Đang nghe dở",
    và "Nghe tiếp" phát lại từ đầu.
    """
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
    all_heard = bool(chapters) and done_chapters == len(chapters)
    return {
        "heardSeconds": round(heard, 1),
        "totalSeconds": round(total, 1),
        "fraction": round(heard / total, 4) if total else 0.0,
        "chaptersDone": done_chapters,
        "finished": bool(state.get("finished")) or (complete and all_heard),
        "caughtUp": not complete and all_heard and not state.get("finished"),
    }


def _clean_night(night: dict[str, Any]) -> dict[str, Any]:
    events = [event for event in night.get("events") or [] if isinstance(event, dict)][-200:]
    timeline = [point for point in night.get("timeline") or [] if isinstance(point, dict)][-NIGHT_MAX_POINTS:]
    return {
        "id": str(night.get("id") or uuid.uuid4().hex[:12])[:40],
        "device": str(night.get("device") or "")[:40],
        "bookTitle": str(night.get("bookTitle") or "")[:200],
        "startedAt": float(night.get("startedAt") or time.time()),
        "endedAt": float(night["endedAt"]) if night.get("endedAt") else None,
        "dismissed": bool(night.get("dismissed")),
        "events": events,
        "timeline": timeline,
    }


def merge_nights(ours: dict[str, Any] | None, theirs: dict[str, Any] | None) -> dict[str, Any] | None:
    """Đêm mới hơn thắng; cùng một đêm (cùng id) thì bản ghi dài hơn thắng, còn "đã gạt đi" ở đâu cũng giữ."""
    if not ours or not theirs:
        return ours or theirs
    if ours.get("id") != theirs.get("id"):
        return ours if float(ours.get("startedAt") or 0) >= float(theirs.get("startedAt") or 0) else theirs
    longer = ours if len(ours.get("events") or []) >= len(theirs.get("events") or []) else theirs
    result = json.loads(json.dumps(longer))
    result["dismissed"] = bool(ours.get("dismissed")) or bool(theirs.get("dismissed"))
    result["endedAt"] = ours.get("endedAt") or theirs.get("endedAt")
    return result


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
    night = merge_nights(result.get("night"), theirs.get("night"))
    if night:
        result["night"] = night
    result["updatedAt"] = max(float(result.get("updatedAt") or 0), float(theirs.get("updatedAt") or 0))
    return result
