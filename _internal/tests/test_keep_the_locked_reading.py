"""Giữ cách đọc ghim khi chỉ bài chính tả neo tên phàn nàn — thử trên bản sao của project THẬT.

Chương 084 đúc lại (`lo03r_084b`) là ca gốc: bản đọc-ghim `I-xờ-hờ-ta-ra` qua nhịp, chết ở neo
tên trên cả hai đường phiên (`dual_failed`), và bản đọc theo chữ viết được đề cử. Đồ thị ứng
viên với đủ provenance quá nặng để dựng tay, nên bài này chép project thật vào thư mục tạm và
đề cử lại ở đó — WAV được tham chiếu bằng đường dẫn tuyệt đối nên chốt chặn file vẫn chạy thật.
Bỏ qua (có nói lý do) khi máy không có project ấy.
"""
from __future__ import annotations

import json
import shutil
import sqlite3
from pathlib import Path

import pytest

from ebook_reader.database import (
    KEEP_LOCKED_READING_ACTION,
    PRONUNCIATION_DELIVERY_LOCKED,
    PRONUNCIATION_DELIVERY_SOURCE,
    SEGMENT_CANDIDATE_INVALID,
    SEGMENT_CANDIDATE_PROMOTED,
    ProjectDB,
)

REAL = Path("D:/Novels/Audiobooks/_versions/v0.2.0-lo03r/lo03r_084b_9455372a18")
LOST_LINE_SUFFIX = "feeb9dd9dda2"  # 'Chúng tôi đang đến Thành phố Ishtara (Ishtara City).'


def _copy(tmp_path: Path) -> ProjectDB:
    if not (REAL / "project.sqlite3").is_file():
        pytest.skip(f"không có project thật {REAL.name} trên máy này")
    target = tmp_path / "project.sqlite3"
    shutil.copyfile(REAL / "project.sqlite3", target)
    return ProjectDB(target)


def _segment(db: ProjectDB) -> sqlite3.Row:
    with db.connect() as conn:
        row = conn.execute(
            "SELECT * FROM segments WHERE stable_id LIKE ?", (f"%{LOST_LINE_SUFFIX}",)
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


def _promoted_rows(db: ProjectDB, segment_id: int) -> list[sqlite3.Row]:
    with db.connect() as conn:
        return list(
            conn.execute(
                "SELECT * FROM segment_candidates WHERE segment_id=? AND state=?",
                (segment_id, SEGMENT_CANDIDATE_PROMOTED),
            )
        )


def test_the_locked_reading_that_lost_only_the_spelling_test_is_found(tmp_path: Path) -> None:
    db = _copy(tmp_path)
    segment = _segment(db)

    candidate = db.find_locked_reading_that_lost_only_the_spelling_test(
        int(segment["id"]), str(segment["generation_policy_hash"])
    )

    assert candidate is not None
    assert str(candidate["pronunciation_delivery_variant"]) == PRONUNCIATION_DELIVERY_LOCKED
    assert "ASR_LOCKED_NAME_ANCHOR" in str(candidate["failure_reason"])
    # Đương nhiệm hiện tại là bản đọc theo chữ viết - đúng cái ta muốn thay.
    with db.connect() as conn:
        incumbent = conn.execute(
            "SELECT pronunciation_delivery_variant FROM segment_candidates "
            "WHERE segment_id=? AND state=? AND lower(wav_sha256)=lower(?)",
            (int(segment["id"]), SEGMENT_CANDIDATE_PROMOTED, str(segment["wav_sha256"])),
        ).fetchone()
    assert incumbent is not None and str(incumbent[0]) == PRONUNCIATION_DELIVERY_SOURCE


def test_keeping_the_locked_reading_moves_the_segment_onto_it(tmp_path: Path) -> None:
    db = _copy(tmp_path)
    segment = _segment(db)
    before = str(segment["wav_sha256"])
    candidate = db.find_locked_reading_that_lost_only_the_spelling_test(
        int(segment["id"]), str(segment["generation_policy_hash"])
    )
    assert candidate is not None
    assert len(_promoted_rows(db, int(segment["id"]))) == 1

    promoted = db.promote_segment_candidate(
        int(candidate["id"]),
        validated_wav_sha256=str(candidate["wav_sha256"]),
        repair_action=KEEP_LOCKED_READING_ACTION,
        attempt=_next_attempt(db, int(segment["id"])),
        warning_code="ASR_LOCKED_NAME_ANCHOR_MISMATCH",
        keeping_the_locked_reading=True,
    )

    assert str(promoted["state"]) == SEGMENT_CANDIDATE_PROMOTED
    after = db.get_segment(int(segment["id"]))
    assert str(after["wav_sha256"]).casefold() == str(candidate["wav_sha256"]).casefold()
    assert str(after["wav_sha256"]) != before
    assert str(after["wav_path"]) == str(candidate["wav_path"])
    # Một đoạn chỉ có MỘT bản được đề cử: bản đọc theo chữ viết bị hạ, có lý do, cùng giao dịch.
    still_promoted = _promoted_rows(db, int(segment["id"]))
    assert [int(r["id"]) for r in still_promoted] == [int(candidate["id"])]
    with db.connect() as conn:
        sibling = conn.execute(
            "SELECT state, failure_reason FROM segment_candidates "
            "WHERE segment_id=? AND lower(wav_sha256)=lower(?)",
            (int(segment["id"]), before),
        ).fetchone()
    assert str(sibling["state"]) == SEGMENT_CANDIDATE_INVALID
    assert str(sibling["failure_reason"]).startswith("superseded: ")
    # Kế hoạch tiếp tục của đoạn vẫn dựng được (nó ném nếu có hai bản được đề cử).
    db.segment_candidate_resume_plan(int(segment["id"]), str(segment["generation_policy_hash"]))
    # Việc thay được ghi vào sổ, có lý do - báo cáo không im lặng về nó.
    reasons = [str(r["reason"]) for r in db.list_take_substitutions()]
    assert any("giữ cách đọc ghim" in r for r in reasons)


def test_without_the_flag_the_old_contract_still_refuses(tmp_path: Path) -> None:
    db = _copy(tmp_path)
    segment = _segment(db)
    candidate = db.find_locked_reading_that_lost_only_the_spelling_test(
        int(segment["id"]), str(segment["generation_policy_hash"])
    )
    assert candidate is not None

    with pytest.raises(RuntimeError, match="cannot be promoted before both ASR decodes pass"):
        db.promote_segment_candidate(
            int(candidate["id"]),
            validated_wav_sha256=str(candidate["wav_sha256"]),
            repair_action=KEEP_LOCKED_READING_ACTION,
            attempt=_next_attempt(db, int(segment["id"])),
            warning_code="ASR_LOCKED_NAME_ANCHOR_MISMATCH",
        )
    # Và không có gì đổi: đương nhiệm vẫn là bản đọc theo chữ viết.
    assert str(db.get_segment(int(segment["id"]))["wav_sha256"]) == str(segment["wav_sha256"])


def test_any_other_failure_code_refuses_and_names_the_clause(tmp_path: Path) -> None:
    """Một mã ngoài họ neo tên nói bản thu HỎNG; lúc ấy bài chính tả không phải lý do duy nhất."""
    db = _copy(tmp_path)
    segment = _segment(db)
    candidate = db.find_locked_reading_that_lost_only_the_spelling_test(
        int(segment["id"]), str(segment["generation_policy_hash"])
    )
    assert candidate is not None
    with sqlite3.connect(str(tmp_path / "project.sqlite3")) as conn:
        row = conn.execute(
            "SELECT failure_codes_json FROM quality_checks WHERE id=?",
            (int(candidate["beam_check_id"]),),
        ).fetchone()
        codes = json.loads(row[0] or "[]") + ["ASR_MISMATCH_UNRESOLVED"]
        conn.execute(
            "UPDATE quality_checks SET failure_codes_json=? WHERE id=?",
            (json.dumps(codes), int(candidate["beam_check_id"])),
        )

    assert db.find_locked_reading_that_lost_only_the_spelling_test(
        int(segment["id"]), str(segment["generation_policy_hash"])
    ) is None
    with pytest.raises(RuntimeError, match="có mã trượt ngoài họ neo tên"):
        db.promote_segment_candidate(
            int(candidate["id"]),
            validated_wav_sha256=str(candidate["wav_sha256"]),
            repair_action=KEEP_LOCKED_READING_ACTION,
            attempt=_next_attempt(db, int(segment["id"])),
            warning_code="ASR_LOCKED_NAME_ANCHOR_MISMATCH",
            keeping_the_locked_reading=True,
        )


def test_a_missing_wav_refuses(tmp_path: Path) -> None:
    db = _copy(tmp_path)
    segment = _segment(db)
    candidate = db.find_locked_reading_that_lost_only_the_spelling_test(
        int(segment["id"]), str(segment["generation_policy_hash"])
    )
    assert candidate is not None
    with sqlite3.connect(str(tmp_path / "project.sqlite3")) as conn:
        conn.execute(
            "UPDATE segment_candidates SET wav_path=? WHERE id=?",
            (str(tmp_path / "khong-co.wav"), int(candidate["id"])),
        )

    assert db.find_locked_reading_that_lost_only_the_spelling_test(
        int(segment["id"]), str(segment["generation_policy_hash"])
    ) is None


def test_a_drifted_spoken_text_checksum_is_skipped_not_raised(tmp_path: Path) -> None:
    """Checksum văn bản đọc trôi là lỗi thật của `_segment_candidate_item`; ở đây nó chỉ là "thôi".

    Đường ống chạy móc này giữa vòng sửa của MỌI chương, nên một ngoại lệ thoát ra sẽ giết chương
    đang phiên. alpha.47 cho thấy checksum ấy trôi được thật: ghim một cách đọc giữa lượt chạy.
    """
    if not (REAL / "book_settings.json").is_file():
        pytest.skip(f"không có project thật {REAL.name} trên máy này")
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from scripts.keep_the_locked_reading import bare_pipeline

    from ebook_reader.cli import _open_project

    shutil.copyfile(REAL / "project.sqlite3", tmp_path / "project.sqlite3")
    shutil.copyfile(REAL / "book_settings.json", tmp_path / "book_settings.json")
    with sqlite3.connect(str(tmp_path / "project.sqlite3")) as conn:
        conn.row_factory = sqlite3.Row
        segment = conn.execute(
            "SELECT * FROM segments WHERE stable_id LIKE ?", (f"%{LOST_LINE_SUFFIX}",)
        ).fetchone()
        conn.execute(
            "UPDATE segment_candidates SET expected_spoken_text_sha256=? "
            "WHERE segment_id=? AND pronunciation_delivery_variant=?",
            ("0" * 64, int(segment["id"]), PRONUNCIATION_DELIVERY_LOCKED),
        )
    paths, db, settings = _open_project(tmp_path)
    pipeline = bare_pipeline(paths, db, settings)

    assert pipeline._keep_the_locked_reading(dict(db.get_segment(int(segment["id"])))) is False
    assert str(db.get_segment(int(segment["id"]))["wav_sha256"]) == str(segment["wav_sha256"]), (
        "không giữ được thì không được đổi gì"
    )
