"""The report has to describe the book the pipeline sees, not a kinder one.

alpha.46 printed "chương 3, 9, 10 - không có gì chặn" and the resume then refused all three.
Two layers decide whether a chapter publishes and this script only knew one: the blocking
warning codes on a segment, and a stored segment_audio QA verdict that the chapter gate
requires to pass. A row can sit at `warning` with every code accepted and still stop its
chapter on the second layer, which is what SEGMENT_QA_EVIDENCE_MISSING is.

Over-promising here is worse than saying nothing: it sends the owner to bed thinking the
book is one listen away.
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import what_blocks_publication as report  # noqa: E402

WAV = "a" * 64


def _connection(verdict: str | None, *, accepted_wav: str | None = None):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE segments (id INTEGER PRIMARY KEY, stable_id TEXT)")
    conn.execute("INSERT INTO segments (id, stable_id) VALUES (1, 'c1s1')")
    conn.execute(
        "CREATE TABLE quality_checks (id INTEGER PRIMARY KEY, scope TEXT, stage TEXT, "
        "segment_id INTEGER, verdict TEXT)"
    )
    if verdict is not None:
        conn.execute(
            "INSERT INTO quality_checks (scope, stage, segment_id, verdict) "
            "VALUES ('segment','segment_audio_v1',1,?)",
            (verdict,),
        )
    accepted = set()
    if accepted_wav:
        accepted = {("c1s1", "ASR_LOCKED_NAME_ANCHOR_MISMATCH", accepted_wav)}
    return conn, accepted


def _row(wav: str = WAV):
    return {"stable_id": "c1s1", "wav_sha256": wav}


def test_a_stored_failure_nobody_overruled_is_reported() -> None:
    """The layer the report was blind to, and the reason it over-promised."""
    conn, accepted = _connection("fail")

    assert report._stale_qa_failure(conn, _row(), accepted) is True


def test_an_inconclusive_verdict_counts_too() -> None:
    conn, accepted = _connection("asr_inconclusive")

    assert report._stale_qa_failure(conn, _row(), accepted) is True


def test_a_passing_verdict_is_not_reported() -> None:
    conn, accepted = _connection("pass")

    assert report._stale_qa_failure(conn, _row(), accepted) is False


def test_a_listener_who_overruled_it_settles_it() -> None:
    """Their ear is the evidence, which is the whole point of `accept`."""
    conn, accepted = _connection("fail", accepted_wav=WAV)

    assert report._stale_qa_failure(conn, _row(), accepted) is False


def test_an_acceptance_for_other_audio_does_not_settle_it() -> None:
    """Keyed by artifact, like every other use: a re-cut take is one nobody has heard."""
    conn, accepted = _connection("fail", accepted_wav="b" * 64)

    assert report._stale_qa_failure(conn, _row(), accepted) is True


def test_a_segment_with_no_audio_yet_reports_nothing_extra() -> None:
    conn, accepted = _connection("fail")

    assert report._stale_qa_failure(conn, _row(wav=""), accepted) is False


def test_a_project_without_the_table_is_not_an_error() -> None:
    """Older projects predate quality_checks; the point is to stop over-promising, not to
    invent a new way to fail."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE segments (id INTEGER PRIMARY KEY, stable_id TEXT)")

    assert report._stale_qa_failure(conn, _row(), set()) is False


def test_a_perceptual_warning_after_an_aborted_repair_is_not_a_request() -> None:
    """The report's job is to spend the owner's listening only where it is needed.

    A chapter that stops on the perceptual precondition never reaches the repair loop, so the
    perceptual warnings left on its segments are what that loop would have re-cut. alpha.50
    listed seven such segments as work for a person; alpha.48, where the loop ran, re-cut
    eleven of thirteen and asked for none.
    """
    assert report.is_collateral_warning(
        "Perceptual QA requires current ASR evidence for c1s1",
        "PERCEPTUAL_NATURALNESS_REVIEW",
    ) is True


def test_a_perceptual_warning_from_a_completed_pass_is_a_request() -> None:
    """The loop ran and still could not fix it, which is exactly when an ear is needed."""
    assert report.is_collateral_warning(
        "High-quality policy requires repair or review for segment warnings: c1s1=...",
        "PERCEPTUAL_NATURALNESS_REVIEW",
    ) is False


def test_an_anchor_mismatch_is_never_collateral() -> None:
    """The perceptual repair loop would not have touched it, so the abort is irrelevant."""
    assert report.is_collateral_warning(
        "Perceptual QA requires current ASR evidence for c1s1",
        "ASR_LOCKED_NAME_ANCHOR_MISMATCH",
    ) is False


def test_a_chapter_with_no_error_recorded_is_not_collateral() -> None:
    assert report.is_collateral_warning(None, "PERCEPTUAL_NATURALNESS_REVIEW") is False
