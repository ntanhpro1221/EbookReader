"""Bản thu tự kết thúc thay bản bị cắt: đề cử THẬT phải qua, không chỉ bốn điều kiện.

Fixture: bản sao đóng băng của lô 9 (`D:/Novels/Audiobooks/_fixtures/lo09_223_cut_off`), chương
223, đoạn "Gục đi!": đương nhiệm 1,92 s chạm trần, ứng viên #11 0,64 s tự kết thúc, hai đường
phiên ASR đều trượt vì văn bản dưới ngưỡng phán xử. Finder đã chọn #11 từ trước bản vá; cái hỏng
là chốt "hai đường phiên đều qua" trong `promote_segment_candidate`, và chỉ đề cử thật mới chạm
tới nó.
"""
from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path

import pytest

from ebook_reader.database import SEGMENT_CANDIDATE_PROMOTED, ProjectDB

FIXTURE = Path("D:/Novels/Audiobooks/_fixtures/lo09_223_cut_off")
SEGMENT_SUFFIX = "5b7f60a11624"  # "Gục đi!"


def _copy(tmp_path: Path) -> ProjectDB:
    if not (FIXTURE / "project.sqlite3").is_file():
        pytest.skip(f"không có fixture {FIXTURE.name} trên máy này")
    shutil.copyfile(FIXTURE / "project.sqlite3", tmp_path / "project.sqlite3")
    if (FIXTURE / "book_settings.json").is_file():
        shutil.copyfile(FIXTURE / "book_settings.json", tmp_path / "book_settings.json")
    return ProjectDB(tmp_path / "project.sqlite3")


def _segment(db: ProjectDB) -> sqlite3.Row:
    with db.connect() as conn:
        row = conn.execute(
            "SELECT * FROM segments WHERE stable_id LIKE ?", (f"%{SEGMENT_SUFFIX}",)
        ).fetchone()
    assert row is not None
    return row


def _next_attempt(db: ProjectDB, segment_id: int) -> int:
    with db.connect() as conn:
        row = conn.execute(
            "SELECT coalesce(max(attempt), 0) FROM quality_checks WHERE segment_id=?",
            (segment_id,),
        ).fetchone()
    return int(row[0]) + 1


def _eligible_candidate(db: ProjectDB, segment: sqlite3.Row) -> sqlite3.Row:
    policy_hash = str(db.current_quality_policy()["policy_hash"])
    candidate = db.find_finished_take_over_a_cut_off_incumbent(int(segment["id"]), policy_hash)
    assert candidate is not None, "fixture phải còn ứng viên đủ bốn điều kiện"
    if not Path(str(candidate["wav_path"])).is_file():
        pytest.skip("wav của ứng viên không còn trên đĩa (project lô 9 đã bị xoá?)")
    return candidate


def test_the_real_cut_off_case_is_promoted(tmp_path: Path) -> None:
    db = _copy(tmp_path)
    segment = _segment(db)
    candidate = _eligible_candidate(db, segment)

    promoted = db.promote_segment_candidate(
        int(candidate["id"]),
        validated_wav_sha256=str(candidate["wav_sha256"]),
        repair_action="promote_finished_take_over_cut_off_incumbent",
        attempt=_next_attempt(db, int(segment["id"])),
        warning_code="ASR_UNVERIFIABLE_SHORT_TEXT",
        over_a_cut_off_incumbent=True,
    )

    assert str(promoted["state"]) == SEGMENT_CANDIDATE_PROMOTED
    after = _segment(db)
    assert str(after["wav_sha256"]).casefold() == str(candidate["wav_sha256"]).casefold()


def test_without_the_flag_two_failed_decodes_still_refuse(tmp_path: Path) -> None:
    """Chốt không bị tháo: đề cử thường vẫn đòi hai đường phiên đều qua."""
    db = _copy(tmp_path)
    segment = _segment(db)
    candidate = _eligible_candidate(db, segment)

    # Không có cờ, cửa đóng ngay ở tập trạng thái (dual_failed không đề cử được) - trước cả chốt
    # "two passing checks". Cả hai thông điệp đều là "từ chối"; bài này khẳng định cửa đóng.
    with pytest.raises(RuntimeError, match="two passing checks|before both ASR decodes pass"):
        db.promote_segment_candidate(
            int(candidate["id"]),
            validated_wav_sha256=str(candidate["wav_sha256"]),
            repair_action="promote_dual_decode_clarity_candidate",
            attempt=_next_attempt(db, int(segment["id"])),
            warning_code=None,
        )
