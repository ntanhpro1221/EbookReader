"""A listener's verdict has to outlive the resume that re-checks the segment.

alpha.51 chapter 10, with timestamps. 08:46 the verdict was recorded and
`accept_failed_segment_audio` moved the row from `failed` to `warning`, as designed. All
four gates then read open, and `simulate_acceptance.py` agreed. 08:48 the resume ran. 08:52
the chapter failed on SEGMENT_QA_EVIDENCE_MISSING with the row back at `failed` - over audio
a person had listened to and let stand, still matching the checksum the acceptance names.
Accepting again only ran the loop again, so the chapter could not be published at all.

The exemption for accepted takes was already in this gate. It sat *after* the status check,
and the rows it was written for are exactly the ones the machine gave up on - so it was
unreachable for every segment it names. That is the seventh gate of this shape since
alpha.46; the previous six are in docs/LISTENER_VERDICTS.md.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from ebook_reader.database import (
    QUALITY_SCOPE_SEGMENT,
    SEGMENT_AUDIO_QUALITY_STAGE,
    ProjectDB,
)
from ebook_reader.models import SegmentStatus

WAV = "d" * 64
OTHER = "e" * 64
CODE = "ASR_LOCKED_NAME_ANCHOR_MISMATCH"


@pytest.fixture()
def project(tmp_path: Path) -> tuple[ProjectDB, int]:
    db = ProjectDB(tmp_path / "project.sqlite3")
    db.initialize_book(
        title="Book",
        project_root=tmp_path,
        settings={},
        settings_hash="s",
        input_manifest_hash="m",
    )
    chapter_id = db.ensure_chapters(
        [
            {
                "chapter_index": 1,
                "title": "One",
                "input_path": tmp_path / "one.txt",
                "input_sha256": "src",
                "input_size": 1,
                "output_mp3": tmp_path / "one.mp3",
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
                "text": "Tên tôi là Samael Kaizer Theosbane.",
                "text_sha256": "h0",
                "kind_hint": "narration",
            }
        ],
    )
    with db.transaction() as conn:
        conn.execute(
            "UPDATE segments SET wav_sha256=?, warning_code=?, status=? WHERE stable_id='c1s1'",
            (WAV, CODE, SegmentStatus.FAILED.value),
        )
    return db, chapter_id


def _accept(db: ProjectDB, checksum: str = WAV) -> None:
    db.accept_segment_audio(
        segment_stable_id="c1s1",
        wav_sha256=checksum,
        warning_code=CODE,
        note="chủ sách đã nghe",
    )


def _refail(db: ProjectDB) -> None:
    """What the resume does: re-verify, disagree again, put the row back to `failed`."""
    with db.transaction() as conn:
        conn.execute(
            "UPDATE segments SET status=? WHERE stable_id='c1s1'",
            (SegmentStatus.FAILED.value,),
        )


def test_an_accepted_take_is_evidence_even_while_the_row_says_failed(
    project: tuple[ProjectDB, int],
) -> None:
    """The whole bug in one assertion. `failed` is the state an overruled segment is in."""
    db, chapter_id = project
    _accept(db)
    _refail(db)

    assert db.chapter_segments_have_current_audio_qa(
        chapter_id, SEGMENT_AUDIO_QUALITY_STAGE
    )


def test_the_verdict_survives_being_re_checked_more_than_once(
    project: tuple[ProjectDB, int],
) -> None:
    """A person should not have to listen again for every resume."""
    db, chapter_id = project
    _accept(db)
    for _ in range(3):
        _refail(db)
        assert db.chapter_segments_have_current_audio_qa(
            chapter_id, SEGMENT_AUDIO_QUALITY_STAGE
        )


def test_a_failed_segment_nobody_ruled_on_still_blocks(
    project: tuple[ProjectDB, int],
) -> None:
    """The gate has to keep doing its job. Only a verdict lifts it."""
    db, chapter_id = project
    _refail(db)

    assert not db.chapter_segments_have_current_audio_qa(
        chapter_id, SEGMENT_AUDIO_QUALITY_STAGE
    )


def test_a_verdict_given_on_different_audio_does_not_carry(
    project: tuple[ProjectDB, int],
) -> None:
    """Acceptances bind to a recording, not to a row - so a re-cut voids them. Moving the
    exemption earlier must not weaken that, or `retry` would stop meaning anything."""
    db, chapter_id = project
    _accept(db, checksum=OTHER)
    _refail(db)

    assert not db.chapter_segments_have_current_audio_qa(
        chapter_id, SEGMENT_AUDIO_QUALITY_STAGE
    )


def test_a_segment_with_no_audio_at_all_still_blocks(
    project: tuple[ProjectDB, int],
) -> None:
    db, chapter_id = project
    _accept(db)
    with db.transaction() as conn:
        conn.execute("UPDATE segments SET wav_sha256='' WHERE stable_id='c1s1'")

    assert not db.chapter_segments_have_current_audio_qa(
        chapter_id, SEGMENT_AUDIO_QUALITY_STAGE
    )
