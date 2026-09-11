"""Một đoạn chỉ có MỘT bản được đề cử, và mọi lỗi của đường "thay bản thu" chỉ là "thôi không thay".

`patch_keep_the_locked_reading` sửa CAS trạng thái ứng viên, và nhờ thế đường
`over_a_cut_off_incumbent` - có sẵn từ lâu, chưa từng chạy thành công (0 dòng
`machine_take_substitutions` trên 47 project lô) - chạy được lần đầu từ lô 6. Hai chỗ hở nó mang
theo được vá ở đây: hai bản `promoted` cho một đoạn, và một ngoại lệ giết cả chương.
"""
from __future__ import annotations

import shutil
import sqlite3
import sys
from pathlib import Path

import pytest

from ebook_reader.cli import _open_project
from ebook_reader.database import (
    KEEP_LOCKED_READING_ACTION,
    SEGMENT_CANDIDATE_PROMOTED,
    ProjectDB,
)

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

REAL = Path("D:/Novels/Audiobooks/_versions/v0.2.0-lo03r/lo03r_084b_9455372a18")
LOST_LINE_SUFFIX = "feeb9dd9dda2"


def _copy(tmp_path: Path) -> Path:
    if not (REAL / "project.sqlite3").is_file() or not (REAL / "book_settings.json").is_file():
        pytest.skip(f"không có project thật {REAL.name} trên máy này")
    shutil.copyfile(REAL / "project.sqlite3", tmp_path / "project.sqlite3")
    shutil.copyfile(REAL / "book_settings.json", tmp_path / "book_settings.json")
    return tmp_path


def _promoted_per_segment(db: ProjectDB) -> dict[int, int]:
    with db.connect() as conn:
        return {
            int(row["segment_id"]): int(row["n"])
            for row in conn.execute(
                "SELECT segment_id, count(*) AS n FROM segment_candidates "
                "WHERE state=? GROUP BY segment_id",
                (SEGMENT_CANDIDATE_PROMOTED,),
            )
        }


def test_no_segment_ends_up_with_two_promoted_candidates(tmp_path: Path) -> None:
    """Bất biến phát biểu thành một câu, và kiểm trên cả project sau khi đề cử lại thật."""
    root = _copy(tmp_path)
    db = ProjectDB(root / "project.sqlite3")
    before = _promoted_per_segment(db)
    assert before and max(before.values()) == 1, "project thật phải đang thoả bất biến"

    with db.connect() as conn:
        segment = conn.execute(
            "SELECT * FROM segments WHERE stable_id LIKE ?", (f"%{LOST_LINE_SUFFIX}",)
        ).fetchone()
        attempt = int(
            conn.execute(
                "SELECT coalesce(max(attempt), 0) FROM quality_checks WHERE segment_id=?",
                (int(segment["id"]),),
            ).fetchone()[0]
        ) + 1
    candidate = db.find_locked_reading_that_lost_only_the_spelling_test(
        int(segment["id"]), str(segment["generation_policy_hash"])
    )
    assert candidate is not None

    db.promote_segment_candidate(
        int(candidate["id"]),
        validated_wav_sha256=str(candidate["wav_sha256"]),
        repair_action=KEEP_LOCKED_READING_ACTION,
        attempt=attempt,
        warning_code="ASR_LOCKED_NAME_ANCHOR_MISMATCH",
        keeping_the_locked_reading=True,
    )

    after = _promoted_per_segment(db)
    assert max(after.values()) == 1, "một đoạn, nhiều nhất một bản được đề cử"
    assert after[int(segment["id"])] == 1
    # Và kế hoạch tiếp tục dựng được cho mọi đoạn có bản được đề cử (nó ném khi thấy hai bản).
    for segment_id in after:
        with db.connect() as conn:
            policy_hash = str(
                conn.execute(
                    "SELECT generation_policy_hash FROM segments WHERE id=?", (segment_id,)
                ).fetchone()[0]
            )
        db.segment_candidate_resume_plan(segment_id, policy_hash)


def test_the_cut_off_substitution_swallows_its_own_failures(tmp_path: Path) -> None:
    """Lớp bọc: một ngoại lệ ở đây phải thành "thôi không thay", không phải "chương hỏng"."""
    from scripts.keep_the_locked_reading import bare_pipeline

    root = _copy(tmp_path)
    paths, db, settings = _open_project(root)
    pipeline = bare_pipeline(paths, db, settings)
    with db.connect() as conn:
        segment = conn.execute(
            "SELECT * FROM segments WHERE stable_id LIKE ?", (f"%{LOST_LINE_SUFFIX}",)
        ).fetchone()

    def boom(*_args, **_kwargs):
        raise RuntimeError("segment candidate pronunciation variant or spoken-text checksum drifted")

    db.find_finished_take_over_a_cut_off_incumbent = boom

    assert (
        pipeline._promote_a_finished_take_over_a_cut_off_one(
            dict(segment), int(segment["id"]), "084"
        )
        is False
    )
    assert str(db.get_segment(int(segment["id"]))["wav_sha256"]) == str(segment["wav_sha256"])
