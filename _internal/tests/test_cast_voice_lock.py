"""A casting decision can be pinned, and it survives into the next version.

`port_pronunciations.py` carries how a name is read and `seed_listener_acceptances.py`
carries what a listener ruled. Casting had no equivalent, and the gap cost two things.

It made batching unsafe: every project casts from scratch and the allocator ranks on
`usage[name]`, so the character set a batch happens to see decides the voices. alpha.52
showed the sensitivity - one label changing its name string, same room id, moved a segment
from voice 16 to voice 14.

And it made a casting decision unrepeatable. alpha.52 lost chapter 6 because voice 14 cannot
say "Mẹ kiếp" while voice 16 can, and there was no way to pin voice 16 back: `cast` only
changes gender, and the gender was already right.

The pinned value is a `voice_profiles.voice_key` - preset, formant and pitch together -
because all three decide the timbre, and the formant comes from the allocator's variant
counter, which depends on the order characters were cast in.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from ebook_reader.character_registry import PresetAllocator
from ebook_reader.config import build_settings
from ebook_reader.project import create_or_open_project

KEY = "preset_thanh_binh_f109_p-01"


def _project(tmp_path: Path):
    tmp_path.mkdir(parents=True, exist_ok=True)
    source = tmp_path / "001.txt"
    source.write_text("Một câu để mở project.", encoding="utf-8")
    paths, db, _settings = create_or_open_project(
        [source], tmp_path / "out", build_settings(), "Voice lock"
    )
    db.project_root = paths.root
    return db


def test_a_pinned_voice_is_read_back_the_way_casting_keys_characters(tmp_path) -> None:
    db = _project(tmp_path)
    db.set_locked_character_voice("Noah", KEY)
    assert db.locked_character_voices() == {"NOAH": KEY}


def test_the_pin_can_be_made_before_the_project_has_analysed(tmp_path) -> None:
    """The whole point of porting: it runs between `create` and `run`, so the allocator
    finds the decision already made instead of making its own and being overruled."""
    db = _project(tmp_path)
    db.set_locked_character_voice("Nobody Analysed Yet", KEY)
    assert db.locked_character_voices()["NOBODY ANALYSED YET"] == KEY


def test_the_same_character_typed_two_ways_is_one_pin(tmp_path) -> None:
    db = _project(tmp_path)
    db.set_locked_character_voice("  noah  ", KEY)
    assert db.locked_character_voices() == {"NOAH": KEY}


def test_a_project_with_no_pins_reports_none(tmp_path) -> None:
    """The property that matters most: a project that never ported casts exactly as it did
    before, because there is nothing for the allocator to find."""
    db = _project(tmp_path)
    assert db.locked_character_voices() == {}


def test_a_pin_needs_both_a_name_and_a_voice(tmp_path) -> None:
    db = _project(tmp_path)
    for name, key in (("", KEY), ("Noah", ""), ("   ", KEY)):
        with pytest.raises(ValueError):
            db.set_locked_character_voice(name, key)


def test_repinning_replaces_rather_than_accumulates(tmp_path) -> None:
    db = _project(tmp_path)
    db.set_locked_character_voice("Noah", KEY)
    db.set_locked_character_voice("Noah", "preset_thai_son_f100_p+00")

    assert db.locked_character_voices() == {"NOAH": "preset_thai_son_f100_p+00"}


def test_a_reserved_preset_is_taken_in_both_pools(tmp_path: Path) -> None:
    """The bug alpha.55 found by running. The first version reserved only the pinned
    character's own pool, so CÔNG TƯỚC pinned in the named pool and ÔNG LÃO allocated in the
    NPC pool came out with the identical voice_key. alpha.54 cast the same book with no
    pinning and had no collisions at all, so the carry introduced them.

    A voice that belongs to somebody is taken everywhere, not taken in one ledger.
    """
    baseline = PresetAllocator("Phạm Tuyên", 2)
    npc_first, _r, _p = baseline.choose("male", npc=True)

    allocator = PresetAllocator("Phạm Tuyên", 2)
    allocator.reserve(str(npc_first["name"]))
    npc_after, _r2, _p2 = allocator.choose("male", npc=True)
    named_after, _r3, _p3 = PresetAllocator("Phạm Tuyên", 2).choose("male", npc=False)

    assert str(npc_after["name"]) != str(npc_first["name"]), "NPC pool must see the reservation"

    named = PresetAllocator("Phạm Tuyên", 2)
    named.reserve(str(named_after["name"]))
    npc_side, _r4, _p4 = named.choose("male", npc=True)

    assert str(npc_side["name"]) != str(named_after["name"]), (
        "a voice reserved for a named character must not be handed to an NPC"
    )


def test_reserving_a_preset_stops_the_next_character_being_handed_it() -> None:
    """The hazard in the whole mechanism. A pinned voice is invisible to the ranking unless
    it is counted, and an unused preset always sorts first - so the very next character
    would be given the voice somebody had just pinned to someone else. Two people, one
    voice, and the invariant in verify_casting checks the opposite direction."""
    allocator = PresetAllocator("Phạm Tuyên", 2)
    first, _ratio, _pitch = allocator.choose("male", npc=False)

    allocator_two = PresetAllocator("Phạm Tuyên", 2)
    allocator_two.reserve(str(first["name"]))
    after_reserve, _ratio2, _pitch2 = allocator_two.choose("male", npc=False)

    assert str(after_reserve["name"]) != str(first["name"])


def test_the_pools_stay_separate_for_ordinary_allocation() -> None:
    """Reserving crosses the pools on purpose, but ordinary casting does not: a named
    character using a preset should not push NPCs off it, which is what the two counters are
    for."""
    allocator = PresetAllocator("Phạm Tuyên", 2)
    named, _r, _p = allocator.choose("male", npc=False)
    npc, _r2, _p2 = allocator.choose("male", npc=True)

    assert str(npc["name"]) == str(named["name"])


# The carry itself. It copies the voice profiles as well as the mapping, because a pinned
# key has to resolve to a real profile in the target - and the profiles are deterministic
# from preset, formant and pitch, so copying reproduces the sound rather than approximating.

import sys as _sys

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
_sys.path.insert(0, str(SCRIPTS))

import port_casting as porter  # noqa: E402


def _cast_project(tmp_path: Path, *, name: str, voice_key: str):
    db = _project(tmp_path)
    profile_id = db.upsert_voice_profile(
        {
            "voice_key": voice_key,
            "engine": "vieneu",
            "preset_name": "Thanh Bình",
            "description": "Nam · Bắc · Kể chuyện",
            "seed": 1191426086,
            "pitch_semitones": -1,
            "formant_ratio": 1.09,
            "status": "ready",
        }
    )
    character_id = db.upsert_character(
        canonical_name=name,
        display_name=name,
        gender="male",
        age="adult",
        personality="",
        mentions=3,
        importance="main",
        confidence=0.9,
    )
    with db.connect() as conn:
        chapter_id = int(conn.execute("SELECT id FROM chapters LIMIT 1").fetchone()["id"])
    db.replace_chapter_segments(
        chapter_id,
        [
            {
                "stable_id": "c1s1",
                "seq": 0,
                "paragraph_index": 0,
                "text": "Một câu.",
                "text_sha256": "h0",
                "kind_hint": "dialogue",
            }
        ],
    )
    with db.transaction() as conn:
        conn.execute(
            "UPDATE segments SET canonical_character_id=?, voice_profile_id=?",
            (character_id, profile_id),
        )
    return db


def test_the_carry_pins_the_voice_and_brings_the_profile_with_it(tmp_path: Path) -> None:
    """Both halves matter: without the profile the pinned key resolves to nothing and the
    allocator casts afresh, which is the outcome the carry exists to prevent."""
    source_db = _cast_project(tmp_path / "old", name="NOAH", voice_key=KEY)
    target = _project(tmp_path / "new")

    assert porter.port(source_db.project_root, target.project_root) == (1, 0)
    assert target.locked_character_voices() == {"NOAH": KEY}
    assert target.voice_profile_by_key(KEY)["preset_name"] == "Thanh Bình"


def test_carrying_twice_changes_nothing(tmp_path: Path) -> None:
    source_db = _cast_project(tmp_path / "old", name="NOAH", voice_key=KEY)
    target = _project(tmp_path / "new")

    assert porter.port(source_db.project_root, target.project_root) == (1, 0)
    assert porter.port(source_db.project_root, target.project_root) == (0, 1)


def test_a_dry_run_writes_nothing(tmp_path: Path) -> None:
    source_db = _cast_project(tmp_path / "old", name="NOAH", voice_key=KEY)
    target = _project(tmp_path / "new")

    assert porter.port(source_db.project_root, target.project_root, dry_run=True) == (1, 0)
    assert target.locked_character_voices() == {}


def test_a_source_that_never_cast_carries_nothing(tmp_path: Path) -> None:
    source_db = _project(tmp_path / "old")
    target = _project(tmp_path / "new")

    assert porter.port(source_db.project_root, target.project_root) == (0, 0)


def test_the_anonymous_groups_are_pinned_too(tmp_path: Path) -> None:
    """Casting happens at two call sites, and the first version of this patched one.

    The unnamed groups - ANONYMOUS_MALE and its siblings - are cast separately from the
    named speaker loop. A listener hears "the unnamed men in this scene" as a voice, and it
    changing between versions is the same defect however minor the characters are. alpha.51
    had an ANONYMOUS_UNKNOWN with a real voice, so this is not hypothetical.
    """
    db = _project(tmp_path)
    db.set_locked_character_voice("ANONYMOUS_MALE", KEY)

    assert db.locked_character_voices()["ANONYMOUS_MALE"] == KEY


def test_a_pinned_key_naming_no_profile_falls_back_and_says_so(tmp_path: Path) -> None:
    """A carried decision that has gone stale must not kill the run - casting afresh is a
    defensible answer. Doing it silently is not: somebody chose that voice."""
    from ebook_reader.character_registry import _pinned_profile_id

    db = _project(tmp_path)
    said: list[str] = []

    result = _pinned_profile_id(
        db, {"NOAH": "preset_that_does_not_exist"}, "NOAH", None, False, said.append
    )

    assert result is None
    assert said and "preset_that_does_not_exist" in said[0]


def test_two_characters_on_one_voice_is_reported(tmp_path: Path) -> None:
    """The invariant that was missing. `assert_voice_stability` checked one character
    resolving to several voices and never the reverse, so alpha.55 shipped two pairs of
    characters sharing a voice_key and nothing downstream noticed: every segment verified,
    every chapter published, and only a listener would hear that two people sound identical.

    Reported rather than raised - at some book size sharing becomes unavoidable, and killing
    a run over an inevitability would be worse than saying so.
    """
    from ebook_reader.character_registry import assert_voice_stability

    db = _project(tmp_path)
    profile = db.upsert_voice_profile(
        {
            "voice_key": KEY,
            "engine": "vieneu",
            "preset_name": "Thanh Bình",
            "description": "d",
            "seed": 1,
            "pitch_semitones": 0,
            "formant_ratio": 1.0,
            "status": "ready",
        }
    )
    first = db.upsert_character(
        canonical_name="MỘT", display_name="Một", gender="male", age="adult",
        personality="", mentions=2, importance="main", confidence=0.9,
    )
    second = db.upsert_character(
        canonical_name="HAI", display_name="Hai", gender="male", age="adult",
        personality="", mentions=2, importance="main", confidence=0.9,
    )
    with db.connect() as conn:
        chapter_id = int(conn.execute("SELECT id FROM chapters LIMIT 1").fetchone()["id"])
    db.replace_chapter_segments(
        chapter_id,
        [
            {"stable_id": "s1", "seq": 0, "paragraph_index": 0, "text": "A.",
             "text_sha256": "h1", "kind_hint": "dialogue"},
            {"stable_id": "s2", "seq": 1, "paragraph_index": 0, "text": "B.",
             "text_sha256": "h2", "kind_hint": "dialogue"},
        ],
    )
    with db.transaction() as conn:
        conn.execute(
            "UPDATE segments SET speaker='MỘT', canonical_character_id=?, voice_profile_id=? "
            "WHERE stable_id='s1'", (first, profile))
        conn.execute(
            "UPDATE segments SET speaker='HAI', canonical_character_id=?, voice_profile_id=? "
            "WHERE stable_id='s2'", (second, profile))

    said: list[str] = []
    assert_voice_stability(db, said.append)

    assert said, "sharing a voice must be reported"
    assert "chung một giọng" in said[0]
