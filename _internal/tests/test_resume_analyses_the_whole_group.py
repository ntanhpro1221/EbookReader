"""A resume used to produce a different book, and the reason was a fragment.

Proven by controlled experiment on 2026-09-07: same code, same source, same seeded readings,
one deliberate stop at 620/948. The uninterrupted run found 23 characters; the interrupted one
found 19, with 18 speaker assignments changed - every one after the interruption point, running
to the end of the book because the registry merges are global.

The cause is not re-batching. `stable_groups` is built from all rows, so the grouping is
identical either way, which the stored group fingerprints confirm: 200 of them, the same in
both runs. What differed is that only the rows still `pending` were sent, so an interrupted
group was analysed as a *fragment of itself* - and `_analysis_context_hash` takes each row's
neighbours from within the group, so a fragment carries different context than the whole.

Two halves, and the second fails silently on its own. Sending the whole group means some rows
arrive already `analyzed`, and the analysis UPDATE guards on `status=?`. Hard-coding "pending"
there matches zero rows and drops the result without raising.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from ebook_reader.analysis import _group_rows_to_analyse
from ebook_reader.database import ProjectDB
from ebook_reader.models import SegmentStatus


class _Row(dict):
    def keys(self):  # noqa: D102
        return list(super().keys())


def _group(*statuses: str) -> list[_Row]:
    return [
        _Row(stable_id=f"c1s{index}", status=status, seq=index)
        for index, status in enumerate(statuses)
    ]


def test_an_untouched_group_is_sent_whole() -> None:
    """Every group of an uninterrupted run looks like this, which is why the change cannot
    alter what such a run produces."""
    group = _group("pending", "pending", "pending")

    assert _group_rows_to_analyse(group) == [group]


def test_a_finished_group_is_not_sent_again() -> None:
    """A resume must not re-analyse the chapters it already got right."""
    assert _group_rows_to_analyse(_group("analyzed", "analyzed")) == []


def test_a_partly_finished_group_is_sent_whole_not_as_its_remainder() -> None:
    """The whole point. Sending rows 2 and 3 alone gives them neighbours they never had."""
    group = _group("analyzed", "pending", "pending")

    sent = _group_rows_to_analyse(group)

    assert sent == [group], "the finished row must travel with the group, as context"
    assert len(sent[0]) == 3


def test_a_gap_in_the_middle_still_travels_as_one_group() -> None:
    """The old code split this into two runs, which is two fragments and two wrong contexts."""
    group = _group("pending", "analyzed", "pending")

    assert _group_rows_to_analyse(group) == [group]


def test_a_warning_row_counts_as_finished() -> None:
    """`warning` is an analysed row that scored low confidence, not an unanalysed one."""
    assert _group_rows_to_analyse(_group("warning", "warning")) == []
    assert _group_rows_to_analyse(_group("warning", "pending")) != []


@pytest.fixture()
def project(tmp_path: Path) -> ProjectDB:
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
                "stable_id": "c1s0",
                "seq": 0,
                "paragraph_index": 0,
                "text": "Một câu.",
                "text_sha256": "h0",
                "kind_hint": "narration",
            }
        ],
    )
    db.lock_analysis_model("test-model", "test-digest")
    return db


def _segment(db: ProjectDB) -> dict:
    with db.connect() as conn:
        row = conn.execute("SELECT id, stable_id, text_sha256, status, speaker FROM segments").fetchone()
    return {key: row[key] for key in row.keys()}


def _update(db: ProjectDB, *, expected_status: str, speaker: str) -> None:
    from ebook_reader.database import canonical_analysis_note

    row = _segment(db)
    data = {
        "kind": "narration",
        "speaker": speaker,
        "gender": "unknown",
        "age": "unknown",
        "emotion": "neutral",
        "intensity": 1,
        "pace": "normal",
        "volume": "normal",
        "confidence": 0.9,
        "personality_hint": "",
        "notes": "",
    }
    data["notes"] = canonical_analysis_note(data)
    db.update_analysis_batch_with_event(
        [
            {
                "segment_id": int(row["id"]),
                "stable_id": str(row["stable_id"]),
                "text_sha256": str(row["text_sha256"]),
                "expected_status": expected_status,
                "data": data,
            }
        ],
        low_confidence_threshold=0.58,
        event_level="info",
        event_code="TEST",
        event_message="test",
        event_details={},
        analysis_model_name="test-model",
        analysis_model_digest="test-digest",
    )


def test_re_analysing_a_finished_row_needs_its_real_status(project: ProjectDB) -> None:
    """The silent half. With "pending" hard-coded the UPDATE matches nothing and the new
    answer is thrown away without an error - which is how a fix here would look like it
    worked while changing nothing at all."""
    _update(project, expected_status=SegmentStatus.PENDING.value, speaker="FIRST")
    assert _segment(project)["speaker"] == "FIRST"
    assert _segment(project)["status"] == SegmentStatus.ANALYZED.value

    # What the old hard-coded value would do on a resume: silently nothing.
    with pytest.raises(Exception):
        _update(project, expected_status=SegmentStatus.PENDING.value, speaker="STALE")

    _update(project, expected_status=SegmentStatus.ANALYZED.value, speaker="SECOND")
    assert _segment(project)["speaker"] == "SECOND"
