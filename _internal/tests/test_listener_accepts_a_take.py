"""A listener who has heard a take can accept it, and only that take.

High-quality policy refuses to publish a chapter whose segments carry warnings it does not
allow, and PERCEPTUAL_NATURALNESS_REVIEW is one of them. The verifier is honest about what
that means - a score well below the preset's own preview, asking for a human ear rather
than proving a bad take - and the repair loop re-cuts the segment and sometimes cannot do
better. Then nothing can clear the warning and the chapter never publishes.

alpha.25 published 2 chapters of 10, and chapter 8 failed with zero failed segments and
eight warnings. That is a wall, not a gate. It is the third of these: `pronounce` exists
because a reading needed a person, `cast` because a gender did, and this because a
recording does.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from ebook_reader.config import build_settings
from ebook_reader.project import create_or_open_project

WARNING = "PERCEPTUAL_NATURALNESS_REVIEW"


class _Row(dict):
    pass


def _db(tmp_path: Path):
    source = tmp_path / "001.txt"
    source.write_text("Một câu để mở project.", encoding="utf-8")
    _paths, db, _settings = create_or_open_project(
        [source], tmp_path / "out", build_settings(), "Accept"
    )
    return db


def test_an_accepted_warning_is_recorded_against_the_audio_that_was_heard(tmp_path) -> None:
    db = _db(tmp_path)
    db.accept_segment_audio(
        segment_stable_id="c00003_s0000001",
        wav_sha256="ABC123",
        warning_code=WARNING,
        note="đã nghe, chấp nhận",
    )
    assert db.accepted_segment_warnings() == {("c00003_s0000001", "abc123"): {WARNING}}


def test_recutting_the_take_voids_the_acceptance(tmp_path) -> None:
    """What was accepted is a recording, not a row. The same reasoning that files a
    perceptual score under the checksum of the audio it heard."""
    db = _db(tmp_path)
    db.accept_segment_audio(
        segment_stable_id="c00003_s0000001", wav_sha256="old", warning_code=WARNING
    )
    accepted = db.accepted_segment_warnings()

    assert accepted.get(("c00003_s0000001", "old")) == {WARNING}
    assert accepted.get(("c00003_s0000001", "new")) is None


def test_accepting_twice_is_one_decision_not_two(tmp_path) -> None:
    db = _db(tmp_path)
    for note in ("lần đầu", "nghĩ lại vẫn được"):
        db.accept_segment_audio(
            segment_stable_id="c00003_s0000001",
            wav_sha256="abc",
            warning_code=WARNING,
            note=note,
        )
    assert db.accepted_segment_warnings() == {("c00003_s0000001", "abc"): {WARNING}}


def test_accepting_one_warning_does_not_accept_another(tmp_path) -> None:
    """A person who listened for naturalness has not thereby ruled on the content."""
    db = _db(tmp_path)
    db.accept_segment_audio(
        segment_stable_id="c00003_s0000001", wav_sha256="abc", warning_code=WARNING
    )
    assert db.accepted_segment_warnings()[("c00003_s0000001", "abc")] == {WARNING}


def test_an_acceptance_needs_all_three_of_its_parts(tmp_path) -> None:
    db = _db(tmp_path)
    for segment, checksum, code in (
        ("", "abc", WARNING),
        ("seg", "", WARNING),
        ("seg", "abc", ""),
        ("  ", "abc", WARNING),
    ):
        with pytest.raises(ValueError):
            db.accept_segment_audio(
                segment_stable_id=segment, wav_sha256=checksum, warning_code=code
            )


def test_the_gate_stops_blocking_on_a_warning_that_was_accepted(monkeypatch) -> None:
    """The whole point, seen from the check that refuses the chapter."""
    import ebook_reader.pipeline as pipeline_module

    pipeline = object.__new__(pipeline_module.BookPipeline)
    pipeline.settings = {"quality_profile": "high_quality"}

    rows = [
        _Row(id=1, stable_id="c00003_s0000001", wav_sha256="abc", warning_code=WARNING),
    ]

    class _DB:
        def __init__(self, accepted):
            self._accepted = accepted

        def accepted_segment_warnings(self):
            return self._accepted

    pipeline.db = _DB({})
    assert pipeline._high_quality_blocking_segment_warnings(rows), "unaccepted must block"

    pipeline.db = _DB({("c00003_s0000001", "abc"): {WARNING}})
    assert pipeline._high_quality_blocking_segment_warnings(rows) == []


def test_an_acceptance_of_different_audio_does_not_clear_this_one(monkeypatch) -> None:
    import ebook_reader.pipeline as pipeline_module

    pipeline = object.__new__(pipeline_module.BookPipeline)
    pipeline.settings = {"quality_profile": "high_quality"}
    rows = [_Row(id=1, stable_id="c00003_s0000001", wav_sha256="new", warning_code=WARNING)]

    class _DB:
        def accepted_segment_warnings(self):
            return {("c00003_s0000001", "old"): {WARNING}}

    pipeline.db = _DB()
    assert pipeline._high_quality_blocking_segment_warnings(rows), "a recut must be judged again"


def _db_with_segment(tmp_path: Path):
    """The earlier tests only needed the acceptance table; these need a real row to move."""
    source = tmp_path / "001.txt"
    paragraphs = [f"Doan van thu {index} du dai." for index in range(1, 4)]
    source.write_text((chr(10) + chr(10)).join(paragraphs), encoding="utf-8")
    _paths, db, settings = create_or_open_project(
        [source], tmp_path / "out", build_settings(), "Accept failed"
    )
    from ebook_reader.text_processing import load_and_segment_chapter

    chapter = db.list_chapters()[0]
    rows = load_and_segment_chapter(
        dict(chapter), max_chars=int(settings["tts"]["max_segment_chars"])
    )
    db.replace_chapter_segments(int(chapter["id"]), rows)
    return db


def test_a_failed_segment_moves_to_warning_so_its_chapter_can_publish(tmp_path) -> None:
    """Suppressing the warning is not enough for a segment the machine gave up on.

    chapter_is_publishable requires every segment to be verified or warning and none
    failed, so a failed row keeps its chapter blocked no matter what a listener says about
    the warning. It moves to `warning`, never to `verified`: the code stays on the row and
    the report still shows it, because what happened is that a person overruled the machine,
    not that the machine changed its mind.
    """
    db = _db_with_segment(tmp_path)
    with db.connect() as conn:
        conn.execute(
            "UPDATE segments SET status='failed', warning_code=?, wav_sha256=? WHERE id=("
            "SELECT id FROM segments LIMIT 1)",
            ("ASR_LOCKED_NAME_ANCHOR_MISMATCH", "abc123"),
        )
        row = conn.execute("SELECT stable_id, chapter_id FROM segments LIMIT 1").fetchone()

    moved = db.accept_failed_segment_audio(
        segment_stable_id=str(row["stable_id"]),
        wav_sha256="abc123",
        warning_code="ASR_LOCKED_NAME_ANCHOR_MISMATCH",
        note="đã nghe, chữ đọc đúng",
    )

    assert moved is True
    with db.connect() as conn:
        after = conn.execute(
            "SELECT status, warning_code FROM segments WHERE stable_id=?",
            (str(row["stable_id"]),),
        ).fetchone()
    assert after["status"] == "warning"
    assert "ASR_LOCKED_NAME_ANCHOR_MISMATCH" in str(after["warning_code"])


def test_only_a_failed_row_is_moved(tmp_path) -> None:
    """A verified segment has nothing to overrule."""
    db = _db_with_segment(tmp_path)
    with db.connect() as conn:
        conn.execute(
            "UPDATE segments SET status='verified', wav_sha256='abc123' WHERE id=("
            "SELECT id FROM segments LIMIT 1)"
        )
        row = conn.execute("SELECT stable_id FROM segments LIMIT 1").fetchone()

    assert (
        db.accept_failed_segment_audio(
            segment_stable_id=str(row["stable_id"]),
            wav_sha256="abc123",
            warning_code=WARNING,
        )
        is False
    )


def test_accepting_audio_the_segment_no_longer_has_is_refused(tmp_path) -> None:
    """Between listening and accepting, a retry may have re-cut the take. Vouching for a
    recording nobody heard is exactly what the checksum is here to prevent."""
    db = _db_with_segment(tmp_path)
    with db.connect() as conn:
        conn.execute(
            "UPDATE segments SET status='failed', warning_code=?, wav_sha256='new' WHERE id=("
            "SELECT id FROM segments LIMIT 1)",
            (WARNING,),
        )
        row = conn.execute("SELECT stable_id FROM segments LIMIT 1").fetchone()

    with pytest.raises(RuntimeError, match="not the audio"):
        db.accept_failed_segment_audio(
            segment_stable_id=str(row["stable_id"]),
            wav_sha256="old",
            warning_code=WARNING,
        )
