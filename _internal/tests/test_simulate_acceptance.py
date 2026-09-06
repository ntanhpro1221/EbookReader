"""Asking for an ear is asking for the scarcest thing here, so ask only when it helps.

Between alpha.46 and alpha.51 a verdict had to clear six separate gates. Each was found by
letting a chapter die on it, and each fix exposed the next - so "this segment carries the only
blocking warning" was wrong five times running. Twice the blocking report sent the owner after
segments that would not have unblocked anything.

This simulates the acceptance against every gate on a copy of the database and says which
chapters it would actually free. These tests pin the two answers that matter: it says yes when
the verdict is enough, and no when something else still holds the chapter shut.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

from ebook_reader.database import ProjectDB

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import simulate_acceptance as sim  # noqa: E402

WAV = "a" * 64
OTHER = "b" * 64
BLOCKING = "ASR_LOCKED_NAME_ANCHOR_MISMATCH"


def _project(root: Path, *, warning: str, status: str, checksum: str = WAV) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    db = ProjectDB(root / "project.sqlite3")
    db.initialize_book(
        title="Book",
        project_root=root,
        settings={},
        settings_hash="s",
        input_manifest_hash="m",
    )
    chapter_id = db.ensure_chapters(
        [
            {
                "chapter_index": 1,
                "title": "One",
                "input_path": root / "one.txt",
                "input_sha256": "src",
                "input_size": 1,
                "output_mp3": root / "one.mp3",
            }
        ]
    )[0]
    db.replace_chapter_segments(
        chapter_id,
        [
            {
                "stable_id": "c1s1",
                "seq": 0,
                "paragraph_index": 0,
                "text": "Một câu.",
                "text_sha256": "h0",
                "kind_hint": "narration",
            }
        ],
    )
    with db.transaction() as conn:
        conn.execute(
            "UPDATE segments SET wav_sha256=?, warning_code=?, status=? WHERE stable_id='c1s1'",
            (checksum, warning, status),
        )
    return root


def test_it_finds_the_warning_that_is_holding_a_chapter(tmp_path: Path) -> None:
    project = _project(tmp_path / "p", warning=BLOCKING, status="failed")

    found = sim.blocking_warnings(project)

    assert found == [("c1s1", BLOCKING, WAV, "failed")]


def test_a_warning_the_policy_already_allows_is_not_worth_an_ear(tmp_path: Path) -> None:
    """Most warnings publish anyway. Listing them would send someone after work that is
    already done - the failure the blocking report made twice."""
    project = _project(tmp_path / "p", warning="ASR_LOCKED_NAME_ANCHOR_REVIEW", status="warning")

    assert sim.blocking_warnings(project) == []


def test_a_verdict_already_given_is_not_asked_for_again(tmp_path: Path) -> None:
    project = _project(tmp_path / "p", warning=BLOCKING, status="failed")
    ProjectDB(project / "project.sqlite3").accept_failed_segment_audio(
        segment_stable_id="c1s1",
        wav_sha256=WAV,
        warning_code=BLOCKING,
        note="đã nghe",
    )

    assert sim.blocking_warnings(project) == []


def test_a_verdict_bound_to_other_audio_does_not_count(tmp_path: Path) -> None:
    """He accepted a recording. This project holds a different one, so it still needs an ear."""
    project = _project(tmp_path / "p", warning=BLOCKING, status="failed", checksum=OTHER)
    ProjectDB(project / "project.sqlite3").accept_segment_audio(
        segment_stable_id="c1s1",
        wav_sha256=WAV,
        warning_code=BLOCKING,
        note="đã nghe bản khác",
    )

    assert sim.blocking_warnings(project) == [("c1s1", BLOCKING, OTHER, "failed")]


def test_the_project_is_never_written_to(tmp_path: Path) -> None:
    """A simulation that can change what it simulates is not a simulation. ProjectDB writes
    on construction, which is why the copy exists."""
    project = _project(tmp_path / "p", warning=BLOCKING, status="failed")
    before = (project / "project.sqlite3").read_bytes()

    sim.simulate(project, None)

    with ProjectDB(project / "project.sqlite3").connect() as conn:
        recorded = conn.execute(
            "SELECT COUNT(*) c FROM listener_audio_acceptances"
        ).fetchone()["c"]
    assert recorded == 0, "the simulation recorded a verdict in the real project"
    assert len(before) > 0


def test_nothing_to_simulate_is_reported_rather_than_crashing(tmp_path: Path) -> None:
    project = _project(tmp_path / "p", warning="", status="verified")

    assert sim.simulate(project, None) == ([], [])
