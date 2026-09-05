"""Listening is the scarcest resource here, and it was being thrown away every version.

On 2026-09-04 the owner listened to fourteen segments; eleven became acceptances, stored in
alpha.44's project. alpha.45 and alpha.46 were fresh projects and started with none, so
alpha.46 failed chapter 3 on c00003_s0000014 - audio byte-identical to the take he had
already passed.

The storage was never wrong. An acceptance is keyed by (segment, wav_sha256, warning) so it
binds to the recording a person heard, not to the row. That is what makes carrying them
forward safe, and most of these tests pin the refusals rather than the carry.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

from ebook_reader.database import ProjectDB
from ebook_reader.io_utils import sha256_file

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import port_listener_acceptances as porter  # noqa: E402

HEARD = "a" * 64
OTHER = "b" * 64


def _project(root: Path, *, checksum: str | None, warning: str, status: str) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    db = ProjectDB(root / "project.sqlite3")
    db.initialize_book(
        title="Book",
        project_root=root,
        settings={},
        settings_hash="settings",
        input_manifest_hash="manifest",
    )
    chapter_id = db.ensure_chapters(
        [
            {
                "chapter_index": 1,
                "title": "One",
                "input_path": root / "one.txt",
                "input_sha256": "source",
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
                "text_sha256": "texthash",
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


def _source(root: Path, *, checksum: str = HEARD, warning: str = "PERCEPTUAL_NATURALNESS_REVIEW") -> Path:
    project = _project(root, checksum=checksum, warning=warning, status="warning")
    ProjectDB(project / "project.sqlite3").accept_segment_audio(
        segment_stable_id="c1s1",
        wav_sha256=checksum,
        warning_code=warning,
        note="chủ sách đã nghe: đọc đúng",
    )
    return project


def _accepted(project: Path) -> set:
    return {
        code
        for codes in ProjectDB(project / "project.sqlite3").accepted_segment_warnings().values()
        for code in codes
    }


def test_a_verdict_carries_to_byte_identical_audio(tmp_path: Path) -> None:
    """The case that cost a chapter: same segment, same recording, verdict already given."""
    source = _source(tmp_path / "old")
    target = _project(
        tmp_path / "new", checksum=HEARD, warning="PERCEPTUAL_NATURALNESS_REVIEW", status="warning"
    )

    carried, examined = porter.port(source, target)

    assert (carried, examined) == (1, 1)
    assert "PERCEPTUAL_NATURALNESS_REVIEW" in _accepted(target)


def test_a_verdict_never_carries_to_a_different_recording(tmp_path: Path) -> None:
    """The safety property the whole design rests on. He passed a recording, and this is
    not that recording - nobody has heard this one."""
    source = _source(tmp_path / "old")
    target = _project(
        tmp_path / "new", checksum=OTHER, warning="PERCEPTUAL_NATURALNESS_REVIEW", status="warning"
    )

    carried, _examined = porter.port(source, target)

    assert carried == 0
    assert _accepted(target) == set()


def test_a_segment_not_synthesized_yet_is_left_for_later(tmp_path: Path) -> None:
    """Accepting audio that does not exist would accept whatever gets made next."""
    source = _source(tmp_path / "old")
    target = _project(
        tmp_path / "new", checksum=None, warning="PERCEPTUAL_NATURALNESS_REVIEW", status="pending"
    )

    assert porter.port(source, target)[0] == 0
    assert _accepted(target) == set()


def test_a_warning_that_is_gone_is_not_re_accepted(tmp_path: Path) -> None:
    """Nothing to forgive; recording an acceptance for it would be noise in the evidence."""
    source = _source(tmp_path / "old")
    target = _project(tmp_path / "new", checksum=HEARD, warning="", status="verified")

    assert porter.port(source, target)[0] == 0
    assert _accepted(target) == set()


def test_dry_run_decides_everything_and_writes_nothing(tmp_path: Path) -> None:
    source = _source(tmp_path / "old")
    target = _project(
        tmp_path / "new", checksum=HEARD, warning="PERCEPTUAL_NATURALNESS_REVIEW", status="warning"
    )

    carried, _examined = porter.port(source, target, dry_run=True)

    assert carried == 1, "it must still report what it would do"
    assert _accepted(target) == set(), "and must not have done it"


def test_a_failed_segment_has_its_status_moved_too(tmp_path: Path) -> None:
    """A chapter publishes only when nothing is failed, so suppressing the warning alone
    would record the verdict and leave the chapter blocked anyway."""
    source = _source(tmp_path / "old", warning="ASR_LOCKED_NAME_ANCHOR_MISMATCH")
    target = _project(
        tmp_path / "new",
        checksum=HEARD,
        warning="ASR_LOCKED_NAME_ANCHOR_MISMATCH",
        status="failed",
    )

    assert porter.port(source, target)[0] == 1
    db = ProjectDB(target / "project.sqlite3")
    assert str(db.list_segments()[0]["status"]) != "failed"


def test_a_source_with_no_verdicts_is_not_an_error(tmp_path: Path) -> None:
    source = _project(tmp_path / "old", checksum=HEARD, warning="X", status="warning")
    target = _project(tmp_path / "new", checksum=HEARD, warning="X", status="warning")

    assert porter.port(source, target) == (0, 0)


@pytest.mark.parametrize("missing", ["old", "new"])
def test_a_path_that_is_not_a_project_is_refused(tmp_path: Path, missing: str) -> None:
    source = _source(tmp_path / "old")
    target = _project(
        tmp_path / "new", checksum=HEARD, warning="PERCEPTUAL_NATURALNESS_REVIEW", status="warning"
    )
    paths = {"old": str(source), "new": str(target)}
    paths[missing] = str(tmp_path / "nowhere")

    assert porter.main([paths["old"], paths["new"]]) == 2
