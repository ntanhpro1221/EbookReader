"""Carry a book's voice casting into the next version, before it starts.

`port_pronunciations.py` carries how names are read and `seed_listener_acceptances.py`
carries what a listener ruled. Casting had no equivalent, and that gap costs two things.

**It makes batching unsafe.** Every project analyses and casts from scratch, and the
allocator ranks on `usage[name]` - it depends on the character set that project happens to
see. Split a book into batches and the same character can get one voice in chapter 40 and
another in chapter 60. Measured on alpha.52: one label changing its name string, same room
id, moved a segment from voice 16 to voice 14.

**And it makes a casting decision unrepeatable.** alpha.52 lost chapter 6 because voice 14
cannot say "Mẹ kiếp" while voice 16 can, and there was no way to pin voice 16 back: `cast`
only changes gender, and the gender was already right.

    python scripts/port_casting.py <project nguồn> <project đích> [--dry-run]

Copies the voice profiles themselves as well as the mapping, because a pinned `voice_key`
has to resolve to a real profile in the target. The profiles are deterministic - preset,
formant ratio and pitch decide the key and the seed - so copying them reproduces the sound
rather than approximating it.

Run it between `create` and `run`, next to the other two.
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ebook_reader.database import ProjectDB  # noqa: E402

from scripts.port_listener_acceptances import _say_safely  # noqa: E402


def read_casting(source: Path) -> list[tuple[str, str, dict]]:
    """(canonical_name, voice_key, profile row) for every character with a voice."""
    connection = sqlite3.connect(f"file:{source / 'project.sqlite3'}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        rows = connection.execute(
            """
            SELECT DISTINCT c.canonical_name AS canonical_name, v.*
            FROM characters c
            JOIN segments s ON s.canonical_character_id = c.id
            JOIN voice_profiles v ON v.id = s.voice_profile_id
            ORDER BY c.canonical_name
            """
        ).fetchall()
    except sqlite3.OperationalError:
        return []
    finally:
        connection.close()
    out: list[tuple[str, str, dict]] = []
    seen: set[str] = set()
    for row in rows:
        name = str(row["canonical_name"])
        if name in seen:
            # A character with two voices is a bug the source project should have caught;
            # carrying either one would make it permanent, so carry neither and say so.
            _say_safely(f"  BỎ QUA {name}: nguồn có nhiều hơn một giọng cho nhân vật này")
            continue
        seen.add(name)
        out.append((name, str(row["voice_key"]), {key: row[key] for key in row.keys()}))
    return out


def read_known_characters(source: Path) -> list[dict]:
    """Every character the source batch established, with what it learnt about them.

    Casting is not the only thing a batch boundary throws away. The analysis prompt carries
    a section headed "Nhân vật đã biết từ các phần trước", built from the characters this
    project has already seen; a fresh batch starts that section empty and the model re-guesses
    a cast it should simply have been told about.

    Measured on this book's own text: from batch two onward, **80% of the proper nouns in a
    batch have already appeared in an earlier one**, and by batch nine it is 95%. So an empty
    known-character list is not a small loss at the seam - it is most of the cast.

    (An earlier measurement of mine said 6%. It compared analysed speaker labels between
    chapters 000-009 and 010-018, which is the least representative window in the book: the
    opening chapters introduce and discard people faster than anywhere else.)
    """
    connection = sqlite3.connect(f"file:{source / 'project.sqlite3'}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        rows = connection.execute(
            """
            SELECT canonical_name, display_name, gender, age, personality,
                   importance, mention_count, confidence
            FROM characters
            WHERE mention_count > 0 AND gender IN ('male','female')
            ORDER BY mention_count DESC
            """
        ).fetchall()
    except sqlite3.OperationalError:
        return []
    finally:
        connection.close()
    from ebook_reader.analysis import RESERVED_SPEAKERS, is_local_speaker

    kept = []
    for row in rows:
        name = str(row["canonical_name"])
        # The same two filters _known_summary applies, for the same reasons. NARRATOR and
        # UNKNOWN are roles rather than people. A chapter-local NPC is scoped to a chapter of
        # the SOURCE batch - "NPC_LOCAL::C00001::..." names nothing in the next batch, and
        # carrying it would put a stranger at the top of the prompt.
        if name.casefold() in RESERVED_SPEAKERS or is_local_speaker(name):
            continue
        # ANONYMOUS_MALE and friends are casting buckets, not characters.
        if name.upper().startswith("ANONYMOUS"):
            continue
        kept.append({key: row[key] for key in row.keys()})
    return kept


def port(source: Path, target: Path, *, dry_run: bool = False) -> tuple[int, int]:
    """Returns (characters pinned, characters already pinned)."""
    casting = read_casting(source)
    if not casting:
        _say_safely("project nguồn chưa có casting để mang đi")
        return 0, 0
    database = ProjectDB(target / "project.sqlite3") if not dry_run else None
    already = (
        set(ProjectDB(target / "project.sqlite3").locked_character_voices())
        if (target / "project.sqlite3").is_file()
        else set()
    )
    from ebook_reader.character_registry import canonical_key

    pinned = skipped = 0
    for name, voice_key, profile in casting:
        if canonical_key(name) in already:
            skipped += 1
            continue
        _say_safely(f"  GHIM  {name} -> {voice_key}")
        pinned += 1
        if database is None:
            continue
        database.upsert_voice_profile(
            {
                "voice_key": voice_key,
                "engine": profile["engine"],
                "preset_name": profile["preset_name"],
                "description": profile["description"],
                "seed": profile["seed"],
                "pitch_semitones": profile["pitch_semitones"],
                "formant_ratio": profile["formant_ratio"],
                "status": "ready",
            }
        )
        database.set_locked_character_voice(name, voice_key)

    # Carry what the source batch learnt about who these people are, so the next batch's
    # analysis prompt opens with the cast instead of "(Chưa có nhân vật đã biết)".
    #
    # Deliberately NOT locked. `locked` means a person decided, and outranks the model
    # permanently; this is one machine telling the next what it worked out, which the model
    # should still be free to revise if the book says otherwise.
    known = read_known_characters(source)
    for character in known:
        _say_safely(
            f"  BIẾT  {character['canonical_name']}"
            f" ({character['gender']}, đã gặp {character['mention_count']})"
        )
        if database is None:
            continue
        database.upsert_character(
            canonical_name=str(character["canonical_name"]),
            display_name=str(character["display_name"] or character["canonical_name"]),
            gender=str(character["gender"]),
            age=str(character["age"] or "unknown"),
            personality=str(character["personality"] or ""),
            mentions=int(character["mention_count"] or 0),
            importance=str(character["importance"] or "minor"),
            confidence=float(character["confidence"] or 0.5),
        )
    if known:
        _say_safely(f"  mang sang {len(known)} nhân vật đã biết (tên, giới tính, số lần gặp)")
    return pinned, skipped


def main(argv: list[str]) -> int:
    dry_run = "--dry-run" in argv
    positional = [value for value in argv if not value.startswith("--")]
    if len(positional) != 2:
        _say_safely("dùng: port_casting.py <project nguồn> <project đích> [--dry-run]")
        return 2
    source, target = (Path(value).resolve() for value in positional)
    for project in (source, target):
        if not (project / "project.sqlite3").is_file():
            _say_safely(f"không phải project: {project}")
            return 2

    pinned, skipped = port(source, target, dry_run=dry_run)
    _say_safely("")
    _say_safely(
        f"{pinned} nhân vật được ghim giọng"
        + (f", {skipped} đã ghim từ trước" if skipped else "")
        + (" (chạy thử, chưa ghi)" if dry_run else "")
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
