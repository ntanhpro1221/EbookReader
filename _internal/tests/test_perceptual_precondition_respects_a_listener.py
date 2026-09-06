"""The sixth gate, reachable only because the five before it were fixed.

alpha.50 chapter 3 failed on

    Perceptual QA requires current ASR evidence for c00003_s0000029_6fca388a80c8

a segment whose verdict the owner gave on 2026-09-04, on audio byte-identical to what he
heard. The error had never appeared before, and that is the interesting part: earlier
versions marked such a segment `failed` and the run stopped at an earlier gate. Now it keeps
`warning`, walks further, and reaches a precondition nobody had taught about acceptances.

An acceptance deliberately leaves the machine's ASR verdict at `fail` - a person overruled it
rather than it changing its mind - so demanding a passing ASR check before scoring refuses
exactly the takes an acceptance exists to release.

The failure is not a stumble on the way to somewhere: without it the chapter never scores the
segment at all, so it ends with no perceptual evidence and the chapter's evidence gate then
refuses it too. Three of alpha.50's ten chapters carry such a segment.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from ebook_reader.database import ProjectDB

HEARD = "a" * 64
OTHER = "b" * 64
WARNING = "ASR_LOCKED_NAME_ANCHOR_MISMATCH"


@pytest.fixture()
def db(tmp_path: Path) -> ProjectDB:
    database = ProjectDB(tmp_path / "project.sqlite3")
    database.initialize_book(
        title="Book",
        project_root=tmp_path,
        settings={},
        settings_hash="settings",
        input_manifest_hash="manifest",
    )
    chapter_id = database.ensure_chapters(
        [
            {
                "chapter_index": 1,
                "title": "One",
                "input_path": tmp_path / "one.txt",
                "input_sha256": "source",
                "input_size": 1,
                "output_mp3": tmp_path / "one.mp3",
            }
        ]
    )[0]
    database.replace_chapter_segments(
        chapter_id,
        [
            {
                "stable_id": "c1s1",
                "seq": 0,
                "paragraph_index": 0,
                "text": "Tên tôi là Samael Kaizer Theosbane.",
                "text_sha256": "texthash",
                "kind_hint": "narration",
            }
        ],
    )
    with database.transaction() as conn:
        conn.execute(
            "UPDATE segments SET wav_sha256=?, warning_code=?, status='warning' "
            "WHERE stable_id='c1s1'",
            (HEARD, WARNING),
        )
    return database


def _precondition_passes(database: ProjectDB, *, artifact: str) -> bool:
    """The check as the perceptual loop makes it: an accepted take needs no ASR pass."""
    accepted_takes = set(database.accepted_segment_warnings())
    with database.connect() as conn:
        row = conn.execute(
            "SELECT id, stable_id FROM segments WHERE stable_id='c1s1'"
        ).fetchone()
    if (str(row["stable_id"]), artifact) in accepted_takes:
        return True
    return database.segment_audio_is_current_qa_verified(
        int(row["id"]), artifact, "segment_audio_v1"
    )


def test_without_a_verdict_the_precondition_still_bites(db: ProjectDB) -> None:
    """Nothing here weakens the gate for a take nobody has heard."""
    assert _precondition_passes(db, artifact=HEARD) is False


def test_a_heard_take_may_be_scored(db: ProjectDB) -> None:
    """The take a person accepted is the evidence; refusing to score it is what cost a
    chapter three versions running."""
    db.accept_segment_audio(
        segment_stable_id="c1s1",
        wav_sha256=HEARD,
        warning_code=WARNING,
        note="chủ sách đã nghe 2026-09-04: đọc đúng",
    )

    assert _precondition_passes(db, artifact=HEARD) is True


def test_the_verdict_does_not_cover_a_re_cut_take(db: ProjectDB) -> None:
    """He accepted a recording, not a row."""
    db.accept_segment_audio(
        segment_stable_id="c1s1",
        wav_sha256=HEARD,
        warning_code=WARNING,
        note="chủ sách đã nghe 2026-09-04: đọc đúng",
    )

    assert _precondition_passes(db, artifact=OTHER) is False


def test_a_verdict_on_a_different_segment_does_not_help(db: ProjectDB) -> None:
    db.accept_segment_audio(
        segment_stable_id="c1s99",
        wav_sha256=HEARD,
        warning_code=WARNING,
        note="một đoạn khác",
    )

    assert _precondition_passes(db, artifact=HEARD) is False
