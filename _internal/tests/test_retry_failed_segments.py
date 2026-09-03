"""A fix can reach the segment it was written for, without redoing the analysis.

A failed segment used to be failed for the life of the project: _verify_chapter_audio skips
anything already marked failed, so resuming after fixing an ASR defect re-verifies nothing
and the chapter fails again on the same segments. The only way to benefit was a clean run -
an hour of analysis to re-cut five segments.

alpha.32 made that concrete. Chapter 6 was refused over one segment whose voice read it
correctly and whose transcript differed only in "tháng Mười hai" against "tháng 12". The fix
for that landed while the run was still going, and there was no way to apply it.
"""
from __future__ import annotations

from pathlib import Path

from ebook_reader.config import build_settings
from ebook_reader.models import ChapterStatus, SegmentStatus
from ebook_reader.project import create_or_open_project


def _project(tmp_path: Path):
    source = tmp_path / "001.txt"
    source.write_text(
        "\n\n".join(f"Doan van thu {index} du dai de thanh mot segment." for index in range(1, 5)),
        encoding="utf-8",
    )
    paths, db, settings = create_or_open_project(
        [source], tmp_path / "out", build_settings(), "Retry"
    )
    from ebook_reader.text_processing import load_and_segment_chapter

    chapter = db.list_chapters()[0]
    rows = load_and_segment_chapter(dict(chapter), max_chars=int(settings["tts"]["max_segment_chars"]))
    db.replace_chapter_segments(int(chapter["id"]), rows)
    return db, chapter


def _fail(db, segment_id: int) -> None:
    db.mark_failed(segment_id, "ASR mismatch remained after all immutable repair candidates")


def test_a_failed_segment_goes_back_to_analysed_not_to_nothing(tmp_path) -> None:
    """The analysis and the casting cost an hour; only the audio and the ASR evidence are
    the ones that were wrong."""
    db, chapter = _project(tmp_path)
    segments = db.list_segments(chapter_id=int(chapter["id"]))
    _fail(db, int(segments[0]["id"]))

    reset = db.retry_failed_segments("test")

    assert reset == [str(segments[0]["stable_id"])]
    row = db.list_segments(chapter_id=int(chapter["id"]))[0]
    assert str(row["status"]) in {
        SegmentStatus.ANALYZED.value,
        SegmentStatus.PENDING.value,
    }
    assert row["wav_path"] is None
    assert row["asr_text"] is None
    assert not str(row["warning_code"] or "")


def test_the_chapter_stops_being_marked_failed(tmp_path) -> None:
    """Leaving the verdict standing over audio that no longer exists would keep refusing a
    chapter for a recording nobody can listen to."""
    db, chapter = _project(tmp_path)
    segments = db.list_segments(chapter_id=int(chapter["id"]))
    _fail(db, int(segments[0]["id"]))
    db.update_chapter_status(int(chapter["id"]), ChapterStatus.FAILED.value, "one segment failed")

    db.retry_failed_segments("test")

    assert str(db.list_chapters()[0]["status"]) != ChapterStatus.FAILED.value


def test_only_the_named_segment_is_retried_when_one_is_named(tmp_path) -> None:
    db, chapter = _project(tmp_path)
    segments = db.list_segments(chapter_id=int(chapter["id"]))
    for row in segments[:2]:
        _fail(db, int(row["id"]))

    reset = db.retry_failed_segments("test", stable_id=str(segments[0]["stable_id"]))

    assert reset == [str(segments[0]["stable_id"])]
    still_failed = [
        row
        for row in db.list_segments(chapter_id=int(chapter["id"]))
        if str(row["status"]) == SegmentStatus.FAILED.value
    ]
    assert [str(row["stable_id"]) for row in still_failed] == [str(segments[1]["stable_id"])]


def test_a_segment_that_did_not_fail_is_left_alone(tmp_path) -> None:
    """Retrying a verified segment would throw away audio that passed."""
    db, chapter = _project(tmp_path)
    segments = db.list_segments(chapter_id=int(chapter["id"]))

    assert db.retry_failed_segments("test") == []
    assert db.retry_failed_segments("test", stable_id=str(segments[0]["stable_id"])) == []


def test_retrying_everything_names_everything_it_reset(tmp_path) -> None:
    """The caller reports what happened, so a write that did not happen cannot be reported
    as success - the same rule pronounce and cast already follow."""
    db, chapter = _project(tmp_path)
    segments = db.list_segments(chapter_id=int(chapter["id"]))
    for row in segments:
        _fail(db, int(row["id"]))

    reset = db.retry_failed_segments("test")

    assert sorted(reset) == sorted(str(row["stable_id"]) for row in segments)
