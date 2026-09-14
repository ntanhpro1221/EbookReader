"""Đoạn nào có bản thu mà chuỗi nói đã đổi thì phải bị tìm ra, và chỉ đoạn ấy.

Lô 1 cuốn 2 chết hai lần ở chương 025 sau bản vá "+ đọc là cộng": bản thu cũ ghi checksum của chuỗi
cũ, `pipeline._spoken_text_and_anchors` băm lại từ mã mới và ném `spoken-text checksum drifted`.
`scripts/resync_spoken_text.py` đặt lại đúng những đoạn ấy về chờ thu, và không đụng đoạn nào khác.

Project thật trong thư mục tạm; đoạn được đặt vào bằng API của DB (`create_or_open_project` chỉ tạo
chương — đoạn chỉ có sau khi chia đoạn trong một lượt chạy), như tests/test_cli.py làm. Không trỏ vào
project sống.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import sqlite3
from pathlib import Path

from ebook_reader.cli import _open_project
from ebook_reader.config import build_settings
from ebook_reader.database import ProjectDB
from ebook_reader.project import create_or_open_project

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "resync_spoken_text", ROOT / "scripts" / "resync_spoken_text.py"
)
resync = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(resync)

DRIFTED_TEXT = "“Nấm xác chết + Bụi oán linh = Linh Hồn Than Khóc”"
SEGMENTS = (
    ("c1s0", "Chương một, một câu thường."),
    ("c1s1", DRIFTED_TEXT),
    ("c1s2", "Câu thường thứ hai, không có ký hiệu nào."),
)


def _project(tmp_path: Path) -> Path:
    source = tmp_path / "text"
    source.mkdir(parents=True, exist_ok=True)
    (source / "000.txt").write_text("Chương một.\n", encoding="utf-8")
    paths, db, _settings = create_or_open_project(
        [source / "000.txt"], tmp_path / "out", build_settings("high_quality"), "Resync Test"
    )
    db.replace_chapter_segments(
        int(db.list_chapters()[0]["id"]),
        [
            {
                "stable_id": stable_id,
                "seq": index,
                "text": text,
                "text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
                "kind_hint": "narration",
            }
            for index, (stable_id, text) in enumerate(SEGMENTS)
        ],
    )
    return paths.root


def _give_every_segment_a_take(project: Path, *, spoil: str | None) -> None:
    """Gắn cho mỗi đoạn một bản thu giả với checksum ĐÚNG của chuỗi nói hiện tại.

    `spoil` là văn bản của đoạn được cố ý ghi checksum sai — đúng hình của một bản thu có từ trước
    một bản vá đổi chuỗi nói.
    """
    paths, db, settings = _open_project(project)
    reader = resync._reader(paths, db, settings)
    with db.connect() as conn:
        conn.row_factory = sqlite3.Row
        rows = [dict(row) for row in conn.execute("SELECT * FROM segments ORDER BY seq")]
    for item in rows:
        spoken, _anchors = reader._spoken_text_and_anchors(dict(item, signal_json=None))
        digest = hashlib.sha256(spoken.encode("utf-8")).hexdigest()
        stored = "0" * 64 if spoil is not None and str(item["text"]) == spoil else digest
        with db.connect() as conn:
            conn.execute(
                "UPDATE segments SET wav_sha256=?, wav_path=?, signal_json=? WHERE id=?",
                (
                    "a" * 64,
                    str(project / "work" / f"{item['stable_id']}.wav"),
                    json.dumps({"spoken_text_sha256": stored, "duration": 1.0}),
                    int(item["id"]),
                ),
            )


def _rows(project: Path) -> dict[str, sqlite3.Row]:
    db = ProjectDB(project / "project.sqlite3")
    return {str(row["text"]): row for row in db.list_segments()}


def test_a_take_whose_spoken_text_moved_is_found_and_only_that_one(tmp_path: Path) -> None:
    project = _project(tmp_path)
    _give_every_segment_a_take(project, spoil=DRIFTED_TEXT)
    paths, db, settings = _open_project(project)

    found = resync.drifted(paths, db, settings)

    assert [str(row["text"]) for row in found] == [DRIFTED_TEXT]


def test_nothing_is_reported_when_every_checksum_still_matches(tmp_path: Path) -> None:
    project = _project(tmp_path)
    _give_every_segment_a_take(project, spoil=None)
    paths, db, settings = _open_project(project)

    assert resync.drifted(paths, db, settings) == []
    assert resync.main([str(project)]) == 0


def test_apply_resets_only_the_drifted_segment_and_clears_its_evidence(tmp_path: Path) -> None:
    project = _project(tmp_path)
    _give_every_segment_a_take(project, spoil=DRIFTED_TEXT)

    assert resync.main([str(project)]) == 1  # chỉ xem: báo có, chưa sửa
    assert _rows(project)[DRIFTED_TEXT]["wav_sha256"] is not None

    assert resync.main([str(project), "--apply"]) == 0
    rows = _rows(project)
    assert rows[DRIFTED_TEXT]["wav_sha256"] is None
    assert rows[DRIFTED_TEXT]["signal_json"] is None
    for text, row in rows.items():
        if text != DRIFTED_TEXT:
            assert row["wav_sha256"] is not None, "đoạn không lệch phải giữ nguyên bản thu"

    assert resync.main([str(project), "--apply"]) == 0  # chạy lại: không còn gì lệch


def test_a_segment_without_a_take_is_never_reported(tmp_path: Path) -> None:
    """Chưa thu thì không có bằng chứng nào để lệch — và không được đặt lại."""
    project = _project(tmp_path)
    paths, db, settings = _open_project(project)

    assert resync.drifted(paths, db, settings) == []
