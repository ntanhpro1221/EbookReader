"""The review page exists to spend a listener's attention well, not just to list warnings.

Met 28 times in a row, one class of warning gets re-derived 28 times. Met once with its
explanation, the rest is a rhythm. So cards are grouped by cause, each cause explained once,
smallest group first - the varied ones deserve fresh attention, the big uniform one is where
it is safe to settle into a rhythm.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

from ebook_reader.database import ProjectDB

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import build_review_page as page  # noqa: E402


def _project(tmp_path: Path, segments: list[tuple[str, str]]) -> Path:
    root = tmp_path / "project"
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
                "output_mp3": root / "one.mp3",  # never created, so the chapter is unpublished
            }
        ]
    )[0]
    db.replace_chapter_segments(
        chapter_id,
        [
            {
                "stable_id": stable_id,
                "seq": index,
                "paragraph_index": index,
                "text": f"Câu {index}.",
                "text_sha256": f"hash{index}",
                "kind_hint": "narration",
            }
            for index, (stable_id, _code) in enumerate(segments)
        ],
    )
    with db.transaction() as conn:
        for stable_id, code in segments:
            conn.execute(
                "UPDATE segments SET warning_code=?, status='warning', wav_duration=1.0 "
                "WHERE stable_id=?",
                (code, stable_id),
            )
    return root


def _build(tmp_path: Path, segments: list[tuple[str, str]]) -> str:
    root = _project(tmp_path, segments)
    out = tmp_path / "review.html"
    page.main(str(root), str(out))
    return out.read_text(encoding="utf-8")


# Blocking codes on purpose. ASR_LOCKED_NAME_ANCHOR_REVIEW, TTS_SPLIT_RECOVERY and
# ASR_UNVERIFIABLE_SHORT_TEXT are in HIGH_QUALITY_ALLOWED_SEGMENT_WARNINGS - listed for a
# human but not blocking - so _blocking drops them and the page would come out empty.
REVIEW = "ASR_LOCKED_NAME_ANCHOR_MISMATCH"
PERCEPT = "PERCEPTUAL_NATURALNESS_REVIEW"


def test_cards_of_one_cause_are_contiguous(tmp_path: Path) -> None:
    """Interleaved, the listener switches context on every card."""
    html = _build(
        tmp_path,
        [("a", REVIEW), ("b", PERCEPT), ("c", REVIEW), ("d", PERCEPT), ("e", REVIEW)],
    )
    order = re.findall(r'<span class="tag [a-z]+">([A-Z_]+)</span>', html)

    assert order == sorted(order, key=order.index), "regex sanity"
    runs = [code for index, code in enumerate(order) if index == 0 or order[index - 1] != code]
    assert len(runs) == len(set(runs)), f"a cause appears in two separate runs: {order}"


def test_the_smallest_group_leads(tmp_path: Path) -> None:
    """The varied causes get fresh attention; the big uniform one is a rhythm."""
    html = _build(
        tmp_path,
        [("a", REVIEW), ("b", REVIEW), ("c", REVIEW), ("d", PERCEPT)],
    )
    headings = re.findall(r'<section class="grp"><h2>([A-Z_]+)', html)

    assert headings == [PERCEPT, REVIEW]


def test_each_cause_is_explained_once_not_per_card(tmp_path: Path) -> None:
    html = _build(tmp_path, [("a", REVIEW), ("b", REVIEW), ("c", REVIEW)])

    assert html.count('<section class="grp">') == 1
    assert html.count("3 đoạn") >= 1
    assert html.count("<article>") == 3


def test_the_group_button_carries_every_command_in_it(tmp_path: Path) -> None:
    """Its whole purpose: settle a known class in one paste rather than N."""
    html = _build(tmp_path, [("a", REVIEW), ("b", REVIEW)])
    button = re.search(r'<button class="all" data-cmd="([^"]+)"', html)

    assert button is not None
    assert button.group(1).count("--segment") == 2


def test_no_class_note_points_at_another_group(tmp_path: Path) -> None:
    """Groups are ordered by size, so which ones appear and in what order changes with the
    data. A note saying "as above" pointed at nothing the moment the other group was empty -
    which is exactly what the first version did on a real project."""
    positional = ("như trên", "như dưới", "nhóm trên", "nhóm dưới", "ở trên", "ở dưới")
    for code, (trigger, evidence, listen) in page.CLASS_NOTES.items():
        blob = f"{trigger} {evidence} {listen}".casefold()
        for phrase in positional:
            assert phrase not in blob, f"{code} refers to another group by position"


def test_every_note_says_what_to_listen_for(tmp_path: Path) -> None:
    """A class explanation that does not end in an instruction leaves the listener to
    re-judge the whole clip, which is the friction the page exists to remove."""
    for code, (_trigger, _evidence, listen) in page.CLASS_NOTES.items():
        assert listen.strip(), f"{code} has no listening instruction"
        assert len(listen) > 20, f"{code}'s instruction is too thin to act on"
