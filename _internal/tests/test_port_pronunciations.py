"""A name's reading drifts between runs, and every drift spends listening nobody gets back.

Measured across four versions of the same book, 112 names each: alpha.46 differs from
alpha.48 on four names, alpha.49 on three, alpha.47 on none. Always the uncertain ones -
`Rare` came out `Ra`, `Rây` and `Rê-ay`. The name request already runs at temperature 0, so
this is not sampling: greedy decoding on a near-tie is at the mercy of GPU arithmetic.

The reading is not the expensive part. A drifted name changes the audio of every segment
containing it, and a verdict binds to a recording - so the drift quietly voids listening
already spent. Carrying the readings forward fixes the reading, the audio and the verdict at
once, and `normalize_name_pronunciations` skips any name already locked, so seeded names are
never sent to the model.

These tests pin the refusal above all: seeding after analysis moves the spoken text under
audio that already exists.
"""
from __future__ import annotations

import sys
from pathlib import Path

from ebook_reader.database import LISTENER_PRONUNCIATION_SOURCE, ProjectDB

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import port_pronunciations as porter  # noqa: E402

MACHINE = "english_name_transliteration"


def _project(root: Path) -> Path:
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
                "text": "Theosbane.",
                "text_sha256": "texthash",
                "kind_hint": "narration",
            }
        ],
    )
    return root


def _source(root: Path) -> Path:
    project = _project(root)
    db = ProjectDB(project / "project.sqlite3")
    db.upsert_pronunciation(
        surface="Kaizer",
        normalized_surface="kaizer",
        spoken_form="cai-dờ",
        confidence=0.9,
        source=MACHINE,
        locked=True,
    )
    db.set_listener_pronunciation(
        surface="Theosbane",
        normalized_surface="theosbane",
        spoken_form="theo-bên",
        source=LISTENER_PRONUNCIATION_SOURCE,
    )
    return project


def _readings(project: Path) -> dict[str, tuple[str, str]]:
    with ProjectDB(project / "project.sqlite3").connect() as conn:
        return {
            str(r["normalized_surface"]): (str(r["spoken_form"]), str(r["source"]))
            for r in conn.execute("SELECT * FROM pronunciations")
        }


def test_readings_carry_into_a_fresh_project(tmp_path: Path) -> None:
    source = _source(tmp_path / "old")
    target = _project(tmp_path / "new")

    carried, examined = porter.port(source, target)

    assert (carried, examined) == (2, 2)
    assert _readings(target)["kaizer"] == ("cai-dờ", MACHINE)


def test_a_persons_choice_stays_a_persons_choice(tmp_path: Path) -> None:
    """Carried as listener_choice, or the next run's reconciler would rewrite it."""
    source = _source(tmp_path / "old")
    target = _project(tmp_path / "new")

    porter.port(source, target)

    assert _readings(target)["theosbane"] == ("theo-bên", LISTENER_PRONUNCIATION_SOURCE)


def test_seeding_is_refused_once_segments_are_analysed(tmp_path: Path) -> None:
    """The whole safety property: after analysis, a new reading moves spoken text under
    audio that already exists."""
    source = _source(tmp_path / "old")
    target = _project(tmp_path / "new")
    with ProjectDB(target / "project.sqlite3").transaction() as conn:
        conn.execute("UPDATE segments SET status='analyzed' WHERE stable_id='c1s1'")

    carried, _examined = porter.port(source, target)

    assert carried == 0
    assert _readings(target) == {}


def test_a_reading_the_target_already_locked_is_left_alone(tmp_path: Path) -> None:
    source = _source(tmp_path / "old")
    target = _project(tmp_path / "new")
    ProjectDB(target / "project.sqlite3").upsert_pronunciation(
        surface="Kaizer",
        normalized_surface="kaizer",
        spoken_form="khác-hẳn",
        confidence=0.9,
        source=MACHINE,
        locked=True,
    )

    carried, _examined = porter.port(source, target)

    assert carried == 1
    assert _readings(target)["kaizer"] == ("khác-hẳn", MACHINE)


def test_dry_run_decides_everything_and_writes_nothing(tmp_path: Path) -> None:
    source = _source(tmp_path / "old")
    target = _project(tmp_path / "new")

    carried, _examined = porter.port(source, target, dry_run=True)

    assert carried == 2
    assert _readings(target) == {}


def test_a_source_with_no_locked_readings_carries_nothing(tmp_path: Path) -> None:
    source = _project(tmp_path / "old")
    target = _project(tmp_path / "new")

    assert porter.port(source, target) == (0, 0)
