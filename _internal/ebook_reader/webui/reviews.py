"""Hàng chờ "Cần nghe lại" của Studio: những câu mà khâu tự kiểm tra không chắc, xếp theo mức đáng lo.

Đo trên lô 18 (26-09, 3.682 câu): 6 câu hỏng (`failed` - chương không xuất được), 22 câu Whisper "nghe" ra một câu
không thể có trong độ dài ấy (ảo giác quen thuộc: "Cảm ơn các bạn đã theo dõi..." cho một câu "Cái..."), 766 câu tên
riêng viết khác chính tả của Whisper - độ khớp trung bình 94%, gần hết là ổn. Nên hàng chờ không liệt kê phẳng: hỏng
trước, rồi chưa kiểm được, rồi tên riêng có độ khớp thấp; tên riêng khớp cao ẩn đi trừ khi xin xem.

Phán quyết của người nghe ("ổn" / "cần thu lại") lưu ở file riêng cạnh tuỳ chọn, KHÔNG ghi vào SQLite của sách (đó là
của dây chuyền). Các chương có câu "cần thu lại" là danh sách đúc lại cho ranh giới lô kế tiếp.
"""
from __future__ import annotations

import json
import os
import threading
import time
from contextlib import closing
from pathlib import Path
from typing import Any

from . import store

LOW_SIMILARITY = 0.8
KINDS = ("failed", "unverified", "name-low", "name")
REASONS = {
    "failed": "Thu âm hỏng sau mọi lần thử - chương này chưa xuất được",
    "unverified": "Máy nghe lại không kiểm được (câu quá ngắn) - nên nghe bằng tai",
    "name-low": "Tên riêng đọc khác nhiều so với chữ viết",
    "name": "Tên riêng đọc hơi khác chữ viết - thường vẫn ổn",
}


def speaker_label(raw: str) -> str:
    """Tên người nói cho người đọc: vai phụ cục bộ "NPC_LOCAL::c00006::r0b2…::người lùn" -> "người lùn"."""
    if not raw:
        return ""
    if raw.upper() == "NARRATOR":
        return "Người kể"
    from .humanize import person_name

    return person_name(raw)


def _kind(status: str, code: str, similarity: float | None) -> str:
    if status == "failed":
        return "failed"
    if code == "ASR_TRANSCRIPT_TIMELINE_IMPOSSIBLE":
        return "unverified"
    if similarity is not None and similarity < LOW_SIMILARITY:
        return "name-low"
    return "name"


def review_items(project_root: Path) -> list[dict[str, Any]]:
    with closing(store.connect(project_root)) as connection:
        rows = connection.execute(
            "SELECT id, stable_id, chapter_id, seq, text, asr_text, asr_similarity, status, warning_code, speaker,"
            " wav_path FROM segments WHERE status IN ('warning', 'failed') ORDER BY chapter_id, seq"
        ).fetchall()
        names = store.chapter_names(connection)
    items = []
    for row in rows:
        similarity = float(row["asr_similarity"]) if row["asr_similarity"] is not None else None
        kind = _kind(str(row["status"]), str(row["warning_code"] or ""), similarity)
        chapter = names.get(int(row["chapter_id"]), {})
        items.append({
            "segmentId": int(row["id"]),
            "stableId": str(row["stable_id"]),
            "chapterId": int(row["chapter_id"]),
            "chapterTitle": chapter.get("full") or f"Chương {row['chapter_id']}",
            "text": str(row["text"] or ""),
            "heard": str(row["asr_text"] or ""),
            "similarity": similarity,
            "speaker": speaker_label(str(row["speaker"] or "")),
            "kind": kind,
            "reason": REASONS[kind],
            "playable": store.segment_audio(project_root, row["wav_path"]) is not None,
        })
    items.sort(key=lambda item: (KINDS.index(item["kind"]), item["similarity"] if item["similarity"] is not None else 1.0))
    return items


def reviews_path() -> Path:
    from .library import preferences_path

    return preferences_path().with_name("reviews.json")


class Reviews:
    """Phán quyết theo `stable_id` của câu (bền qua các lần mở lại sách)."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or reviews_path()
        self._lock = threading.Lock()
        try:
            self._data: dict[str, Any] = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            self._data = {}

    def get(self, book: str) -> dict[str, Any]:
        with self._lock:
            return json.loads(json.dumps(self._data.get(book) or {}))

    def set(self, book: str, stable_id: str, verdict: str | None, chapter_id: int) -> None:
        if verdict not in (None, "ok", "redo"):
            raise ValueError("verdict")
        with self._lock:
            entry = self._data.setdefault(book, {})
            if verdict is None:
                entry.pop(stable_id, None)
            else:
                entry[stable_id] = {"verdict": verdict, "chapterId": int(chapter_id), "at": time.time()}
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.path.with_suffix(".tmp")
            temporary.write_text(json.dumps(self._data, ensure_ascii=False, indent=1), encoding="utf-8")
            os.replace(temporary, self.path)


def review_view(project_root: Path, verdicts: dict[str, Any], *, include_minor: bool) -> dict[str, Any]:
    items = review_items(project_root)
    counts = {kind: 0 for kind in KINDS}
    pending = 0
    for item in items:
        counts[item["kind"]] += 1
        item["verdict"] = (verdicts.get(item["stableId"]) or {}).get("verdict")
        if item["kind"] != "name" and not item["verdict"]:
            pending += 1
    redo = sorted({int(value["chapterId"]) for value in verdicts.values() if value.get("verdict") == "redo"})
    shown = items if include_minor else [item for item in items if item["kind"] != "name" or item["verdict"]]
    return {"counts": counts, "pending": pending, "redoChapters": redo, "items": shown[:600]}
