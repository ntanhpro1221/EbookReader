"""Một lượt cải thiện thất bại KHÔNG được gỡ chương khỏi cuốn sách.

`assemble_book._candidates()` chỉ nhận dòng `chapters` có `status='completed'`. Bản đầu của
`reassemble` đặt chương sang `verifying` trước khi ghép, và mọi đường lỗi để nó ở đó (hoặc ở
`failed`, do `_record_chapter_quality_failure`) - nên một chương đang nằm trong sách sẽ **rơi ra**
dù MP3 cũ còn nguyên trên đĩa, và bước 7 của ranh giới chỉ lặng lẽ báo "thiếu 1 chương".
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

import pytest

from ebook_reader.models import ChapterStatus
from scripts.keep_the_locked_reading import reassemble, restore_shipped_state, shipped_state

SHIPPED_AT = 1_789_000_000.0


class _DB:
    """Chỉ những phương thức `reassemble` gọi, trên một sqlite thật để CAS/kiểu dữ liệu là thật."""

    def __init__(self, path: Path) -> None:
        self.path = path
        with self.connect() as conn:
            conn.executescript(
                """
                CREATE TABLE chapters (
                    id INTEGER PRIMARY KEY, chapter_index INTEGER, title TEXT, status TEXT,
                    completed_at REAL, last_error TEXT
                );
                CREATE TABLE artifacts (
                    artifact_key TEXT PRIMARY KEY, kind TEXT, path TEXT, sha256 TEXT,
                    verified INTEGER, metadata_json TEXT
                );
                """
            )
            conn.execute(
                "INSERT INTO chapters (id, chapter_index, title, status, completed_at, last_error)"
                " VALUES (1, 1, '084', 'completed', ?, NULL)",
                (SHIPPED_AT,),
            )
            conn.execute(
                "INSERT INTO artifacts VALUES ('chapter_mp3:1','chapter_mp3',?,'abc123',1,?)",
                (str(path.parent / "084.mp3"), json.dumps({"quality": {"verdict": "pass"}})),
            )

    def connect(self):  # noqa: ANN201
        conn = sqlite3.connect(str(self.path), isolation_level=None)
        conn.row_factory = sqlite3.Row
        return conn

    def list_chapters(self) -> list[sqlite3.Row]:
        with self.connect() as conn:
            return list(conn.execute("SELECT * FROM chapters"))

    def chapter(self) -> sqlite3.Row:
        return self.list_chapters()[0]

    def artifact_by_key(self, key: str) -> sqlite3.Row | None:
        with self.connect() as conn:
            return conn.execute("SELECT * FROM artifacts WHERE artifact_key=?", (key,)).fetchone()

    def register_artifact(self, *, artifact_key, kind, path, sha256, verified, metadata=None):
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO artifacts VALUES (?,?,?,?,?,?)"
                " ON CONFLICT(artifact_key) DO UPDATE SET path=excluded.path,"
                " sha256=excluded.sha256, verified=excluded.verified,"
                " metadata_json=excluded.metadata_json",
                (artifact_key, kind, str(path), sha256, 1 if verified else 0,
                 json.dumps(metadata) if metadata else None),
            )

    def update_chapter_status(self, chapter_id: int, status: str, error: str | None = None) -> None:
        with self.connect() as conn:
            if status == ChapterStatus.COMPLETED.value:
                conn.execute(
                    "UPDATE chapters SET status=?, completed_at=99999999.0, last_error=NULL WHERE id=?",
                    (status, chapter_id),
                )
            else:
                conn.execute(
                    "UPDATE chapters SET status=?, last_error=? WHERE id=?",
                    (status, error, chapter_id),
                )

    def chapter_artifact_is_current_qa_verified(self, chapter_index: int) -> bool:
        return True


class _Pipeline:
    def __init__(self, db: _DB, publish) -> None:
        self.db = db
        self._publish = publish
        self.said: list[str] = []

    def log(self, message: str) -> None:
        self.said.append(message)

    def _publish_verified_chapter(self, chapter: Any) -> None:
        self._publish(chapter)

    def _record_chapter_quality_failure(self, chapter: Any, error: Exception) -> None:
        self.db.update_chapter_status(int(chapter["id"]), ChapterStatus.FAILED.value, str(error))


def _db(tmp_path: Path) -> _DB:
    (tmp_path / "084.mp3").write_bytes(b"x" * 32)
    return _DB(tmp_path / "project.sqlite3")


@pytest.mark.parametrize(
    "boom",
    [
        RuntimeError("Source chapter content changed during the job: 084.txt"),
        OSError("ffmpeg died"),
    ],
    ids=["source-changed", "ffmpeg"],
)
def test_a_failed_reassembly_leaves_the_chapter_shipped(tmp_path: Path, boom: Exception) -> None:
    db = _db(tmp_path)
    before = shipped_state(db, db.chapter())

    def publish(_chapter):
        raise boom

    ok, word = reassemble(_Pipeline(db, publish), db.chapter(), kept=7)

    assert ok is False
    assert type(boom).__name__ in word and "đặt lại trạng thái đã lên sách" in word
    after = db.chapter()
    assert str(after["status"]) == "completed", "chương phải còn trong sách"
    assert float(after["completed_at"]) == SHIPPED_AT, "giữ nguyên mốc hoàn thành cũ"
    assert shipped_state(db, db.chapter()) == before, "kể cả artifact: verified và metadata cũ"
    assert bool(db.artifact_by_key("chapter_mp3:1")["verified"]) is True, (
        "artifact đã bị đánh dấu hết hiệu lực trước khi ghép; thất bại thì phải trả lại"
    )


def test_a_quality_gate_refusal_also_leaves_it_shipped(tmp_path: Path) -> None:
    """Cổng chất lượng chương đặt `failed`; lượt cải thiện phải hoàn nguyên."""
    from ebook_reader.audio_io import ChapterQualityError

    db = _db(tmp_path)
    before = shipped_state(db, db.chapter())

    def publish(_chapter):
        raise ChapterQualityError("loudness out of band", metrics={}, failure_codes=("X",))

    ok, word = reassemble(_Pipeline(db, publish), db.chapter(), kept=7)

    assert ok is False and "cổng chất lượng" in word
    assert str(db.chapter()["status"]) == "completed"
    assert shipped_state(db, db.chapter()) == before


def test_a_successful_reassembly_keeps_the_new_state(tmp_path: Path) -> None:
    db = _db(tmp_path)

    def publish(chapter):
        db.register_artifact(
            artifact_key="chapter_mp3:1",
            kind="chapter_mp3",
            path=tmp_path / "084.mp3",
            sha256="def456",
            verified=True,
            metadata={"quality": {"verdict": "pass"}},
        )
        db.update_chapter_status(int(chapter["id"]), ChapterStatus.COMPLETED.value)

    ok, word = reassemble(_Pipeline(db, publish), db.chapter(), kept=7)

    assert ok is True and "MP3 mới def456" in word
    assert float(db.chapter()["completed_at"]) == 99999999.0
    assert bool(db.artifact_by_key("chapter_mp3:1")["verified"]) is True


def test_the_artifact_is_marked_stale_before_the_attempt(tmp_path: Path) -> None:
    """Giữa lúc ghép, artifact phải là `verified=0`: bị ngắt thì `cli run` biết phải ghép lại."""
    db = _db(tmp_path)
    seen: list[bool] = []

    def publish(chapter):
        seen.append(bool(db.artifact_by_key("chapter_mp3:1")["verified"]))
        db.update_chapter_status(int(chapter["id"]), ChapterStatus.COMPLETED.value)

    reassemble(_Pipeline(db, publish), db.chapter(), kept=3)

    assert seen == [False]


def test_restore_is_a_no_op_when_there_was_no_artifact(tmp_path: Path) -> None:
    db = _db(tmp_path)
    with db.connect() as conn:
        conn.execute("DELETE FROM artifacts")
    state = shipped_state(db, db.chapter())
    assert state["artifact"] is None

    db.update_chapter_status(1, "verifying")
    restore_shipped_state(db, db.chapter(), state)

    assert str(db.chapter()["status"]) == "completed"
    assert db.artifact_by_key("chapter_mp3:1") is None


def test_a_chapter_that_never_shipped_is_left_to_cli_run(tmp_path: Path) -> None:
    """Lượt này chữa chương ĐANG trong sách. Một chương `failed` không phải việc của nó.

    Đo trên bản sao `lo01b`: lượt đầu đưa ba chương từ `failed` sang `completed`, vì
    `_publish_verified_chapter` xuất bản bất cứ chương nào qua ba cổng chặn. Hậu quả: một chương
    hỏng cũ có `completed_at` mới nhất và đoạt chỗ trong sách của bản đúc lại vừa xong.
    """
    import sqlite3 as _sqlite3

    from ebook_reader.cli import _open_project
    from scripts.keep_the_locked_reading import run_project

    real = Path("D:/Novels/Audiobooks/_versions/v0.2.0-lo03r/lo03r_084b_9455372a18")
    if not (real / "project.sqlite3").is_file() or not (real / "book_settings.json").is_file():
        pytest.skip(f"không có project thật {real.name} trên máy này")
    import shutil

    shutil.copyfile(real / "project.sqlite3", tmp_path / "project.sqlite3")
    shutil.copyfile(real / "book_settings.json", tmp_path / "book_settings.json")
    with _sqlite3.connect(str(tmp_path / "project.sqlite3")) as conn:
        conn.execute("UPDATE chapters SET status='failed'")
    if not hasattr(_open_project(tmp_path)[1], "find_locked_reading_that_lost_only_the_spelling_test"):
        pytest.skip("cây mã chưa có bản vá giữ cách đọc ghim")

    code = run_project(tmp_path, apply=True)

    assert code == 0
    with _sqlite3.connect(str(tmp_path / "project.sqlite3")) as conn:
        conn.row_factory = _sqlite3.Row
        statuses = {str(r["status"]) for r in conn.execute("SELECT status FROM chapters")}
        promoted = conn.execute(
            "SELECT count(*) FROM segment_candidates WHERE state='promoted'"
            " AND pronunciation_delivery_variant='locked_spoken_v1'"
        ).fetchone()[0]
    assert statuses == {"failed"}, "không được xuất bản một chương chưa lên sách"
    assert promoted == 2, "và cũng không đề cử lại gì cho chương ấy"
