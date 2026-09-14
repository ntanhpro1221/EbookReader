"""A promoted finished take must survive every validator that runs after promotion.

Book 2, batch 1, 06:55 on 2026-09-14: the pipeline replaced a cut-off take with a finished one
exactly as the batch-9 patch allows, and the very next report export killed the run -
`_validated_promoted_candidate_conn` only knew the keep-locked-reading exemption. Same lesson
as batch 9, one layer down: relaxed at the promotion, not at the check.

Fixture: the frozen batch-9 copy (`_fixtures/lo09_223_cut_off`), chapter 223, "Gục đi!" - a real
cut-off incumbent with a real finished candidate. The promotion is the real one; then the three
call sites of the validator are exercised on its result.
"""
from __future__ import annotations

import re
import shutil
import sqlite3
from pathlib import Path

import pytest

from ebook_reader.database import (
    PROMOTE_FINISHED_TAKE_ACTION,
    SEGMENT_CANDIDATE_PROMOTED,
    ProjectDB,
)

FIXTURE = Path("D:/Novels/Audiobooks/_fixtures/lo09_223_cut_off")
SEGMENT_SUFFIX = "5b7f60a11624"  # "Gục đi!"
ROOT = Path(__file__).resolve().parents[1]


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


def _promote_the_real_finished_take(db: ProjectDB) -> tuple[int, str, int]:
    segment = _segment(db)
    policy_hash = str(db.current_quality_policy()["policy_hash"])
    candidate = db.find_finished_take_over_a_cut_off_incumbent(int(segment["id"]), policy_hash)
    assert candidate is not None, "fixture phải còn ứng viên đủ bốn điều kiện"
    if not Path(str(candidate["wav_path"])).is_file():
        pytest.skip("wav của ứng viên không còn trên đĩa (project lô 9 đã bị xoá?)")
    promoted = db.promote_segment_candidate(
        int(candidate["id"]),
        validated_wav_sha256=str(candidate["wav_sha256"]),
        repair_action=PROMOTE_FINISHED_TAKE_ACTION,
        attempt=_next_attempt(db, int(segment["id"])),
        warning_code="ASR_UNVERIFIABLE_SHORT_TEXT",
        over_a_cut_off_incumbent=True,
    )
    assert str(promoted["state"]) == SEGMENT_CANDIDATE_PROMOTED
    return int(segment["id"]), policy_hash, int(candidate["id"])


def test_the_promoted_finished_take_passes_every_validator_after_promotion(tmp_path: Path) -> None:
    db = _copy(tmp_path)
    segment_id, policy_hash, candidate_id = _promote_the_real_finished_take(db)

    # 1. The report export that killed the batch.
    summary = db.segment_candidate_attempt_summary(segment_id, policy_hash)
    assert any(
        int(row["candidate_id"]) == candidate_id and row.get("state") == SEGMENT_CANDIDATE_PROMOTED
        for row in summary
    )
    # 2. Recovery's artifact reconciliation, which validates every promoted candidate.
    db.reconcile_segment_candidate_artifacts(policy_hash)
    # 3. The resume plan, which validates the single promoted candidate before saying "complete".
    plan = db.segment_candidate_resume_plan(segment_id, policy_hash)
    assert plan["action"] == "complete"
    assert plan["candidate_id"] == candidate_id


def test_without_its_substitution_row_the_finished_take_is_refused(tmp_path: Path) -> None:
    """The exemption is bound to the evidence the promotion wrote, not to the action name alone."""
    db = _copy(tmp_path)
    segment_id, policy_hash, _candidate_id = _promote_the_real_finished_take(db)
    with db.transaction() as conn:
        conn.execute(
            "DELETE FROM machine_take_substitutions WHERE segment_stable_id LIKE ?",
            (f"%{SEGMENT_SUFFIX}",),
        )
    with pytest.raises(RuntimeError, match="substitution evidence.*no_machine_take_substitution_row"):
        db.segment_candidate_attempt_summary(segment_id, policy_hash)


def test_the_keep_locked_reading_exemption_is_unchanged(tmp_path: Path) -> None:
    """A promoted candidate with a failing ledger and neither action is still refused."""
    db = _copy(tmp_path)
    segment_id, policy_hash, candidate_id = _promote_the_real_finished_take(db)
    with db.transaction() as conn:
        final_check_id = conn.execute(
            "SELECT final_check_id FROM segment_candidates WHERE id=?", (candidate_id,)
        ).fetchone()[0]
        conn.execute(
            "UPDATE quality_checks SET repair_action='promote_dual_decode_clarity_candidate' WHERE id=?",
            (final_check_id,),
        )
    with pytest.raises(RuntimeError, match="dual-decode ledger is not passing"):
        db.segment_candidate_attempt_summary(segment_id, policy_hash)


def test_the_action_name_is_the_one_the_pipeline_writes() -> None:
    source = (ROOT / "ebook_reader" / "pipeline.py").read_text(encoding="utf-8")
    assert re.search(r'repair_action="' + re.escape(PROMOTE_FINISHED_TAKE_ACTION) + '"', source)
