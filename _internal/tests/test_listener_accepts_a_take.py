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
