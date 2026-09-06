"""The fifth gate that overruled a listener, found by a resume undoing published chapters.

alpha.48 published chapters 7 and 9, each carrying a segment whose warning the owner had
ruled on. A resume an hour later requeued both takes - "Recovery requires ASR and perceptual
QA under the current locked quality policy" - and both chapters came back as "MP3 must be
rebuilt because one or more segment checkpoints are invalid".

Nothing was lost that time: a requeue re-runs ASR on the same audio rather than re-cutting
it, and every acceptance still matched its recording afterwards. But the repair loop that
follows a failed ASR pass does re-cut, and a re-cut take voids the verdict for good - so the
next resume after that one would have spent the owner's listening rather than a chapter.

The cause is the same one three earlier gates had: an acceptance leaves the machine's stored
verdict at `fail` on purpose, because a person overruled it rather than it changing its mind.
Four places had been taught to read the acceptance table. `recovery.py` walks every segment
in the book on every resume and was the one that had not.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from ebook_reader.database import ProjectDB
from ebook_reader.recovery import _listener_accepted_takes, _segment_has_current_audio_qa

HEARD = "a" * 64
OTHER = "b" * 64
WARNING = "PERCEPTUAL_NATURALNESS_REVIEW"
SETTINGS = {"perceptual_qa": {"enabled": True}}


@pytest.fixture()
def project(tmp_path: Path) -> ProjectDB:
    db = ProjectDB(tmp_path / "project.sqlite3")
    db.initialize_book(
        title="Book",
        project_root=tmp_path,
        settings={},
        settings_hash="settings",
        input_manifest_hash="manifest",
    )
    chapter_id = db.ensure_chapters(
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
    db.replace_chapter_segments(
        chapter_id,
        [
            {
                "stable_id": "c1s1",
                "seq": 0,
                "paragraph_index": 0,
                "text": "Một câu.",
                "text_sha256": "texthash",
                "kind_hint": "narration",
            }
        ],
    )
    with db.transaction() as conn:
        conn.execute(
            "UPDATE segments SET wav_sha256=?, warning_code=?, status='warning' "
            "WHERE stable_id='c1s1'",
            (HEARD, WARNING),
        )
    return db


def _segment_id(db: ProjectDB) -> int:
    with db.connect() as conn:
        return int(conn.execute("SELECT id FROM segments WHERE stable_id='c1s1'").fetchone()["id"])


def test_without_a_verdict_the_scan_still_asks_for_evidence(project: ProjectDB) -> None:
    """The gate must keep working. Nothing here weakens it for an unheard take."""
    assert (
        _segment_has_current_audio_qa(
            project,
            SETTINGS,
            segment_id=_segment_id(project),
            artifact_sha256=HEARD,
            stable_id="c1s1",
            accepted=_listener_accepted_takes(project),
        )
        is False
    )


def test_a_heard_take_is_evidence(project: ProjectDB) -> None:
    """The recording a person listened to is the only evidence these segments will ever have."""
    project.accept_segment_audio(
        segment_stable_id="c1s1",
        wav_sha256=HEARD,
        warning_code=WARNING,
        note="chủ sách đã nghe: đọc đúng",
    )

    assert (
        _segment_has_current_audio_qa(
            project,
            SETTINGS,
            segment_id=_segment_id(project),
            artifact_sha256=HEARD,
            stable_id="c1s1",
            accepted=_listener_accepted_takes(project),
        )
        is True
    )


def test_a_verdict_does_not_carry_to_a_re_cut_take(project: ProjectDB) -> None:
    """He accepted a recording, not a row. A different take has to earn its own evidence."""
    project.accept_segment_audio(
        segment_stable_id="c1s1",
        wav_sha256=HEARD,
        warning_code=WARNING,
        note="chủ sách đã nghe: đọc đúng",
    )

    assert (
        _segment_has_current_audio_qa(
            project,
            SETTINGS,
            segment_id=_segment_id(project),
            artifact_sha256=OTHER,
            stable_id="c1s1",
            accepted=_listener_accepted_takes(project),
        )
        is False
    )


def test_the_scan_falls_back_to_asking_when_it_was_given_no_table(project: ProjectDB) -> None:
    """Called without the loaded table, it must behave exactly as it did before."""
    project.accept_segment_audio(
        segment_stable_id="c1s1",
        wav_sha256=HEARD,
        warning_code=WARNING,
        note="chủ sách đã nghe: đọc đúng",
    )

    assert (
        _segment_has_current_audio_qa(
            project,
            SETTINGS,
            segment_id=_segment_id(project),
            artifact_sha256=HEARD,
        )
        is False
    )


def test_the_table_is_read_as_segment_and_checksum_pairs(project: ProjectDB) -> None:
    project.accept_segment_audio(
        segment_stable_id="c1s1",
        wav_sha256=HEARD,
        warning_code=WARNING,
        note="chủ sách đã nghe: đọc đúng",
    )

    assert _listener_accepted_takes(project) == {("c1s1", HEARD)}
