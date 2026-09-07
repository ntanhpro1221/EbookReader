"""Carry listener verdicts into a new project *before* its audio exists.

`port_listener_acceptances.py` and `watch_listener_acceptances.py` both wait for the take to
exist and match, which makes them a race against the gate that reads them. alpha.52 lost that
race by **four seconds**: chapter 3 failed at 11:46:00 over `c00003_s0000029`, and the watcher
carried that segment's verdict at 11:46:04. The verdict was correct, the checksum matched, and
the chapter still died - because a 15-second poll cannot reliably win a window that short.

Seeding removes the race instead of tightening it. An acceptance is keyed by
`(segment_stable_id, wav_sha256, warning_code)` and every gate that reads one compares it
against the segment's **current** checksum, so recording it early is inert until the matching
audio appears:

- the take comes back byte-identical, which is the common case for an unchanged segment, and
  the verdict is already there when the gate runs - no window at all;
- the take comes back different and the acceptance simply never matches anything, which is the
  same safety property `retry` relies on.

So this is not a weaker `port`, it is the same rule applied earlier. It writes verdicts a
person actually gave, for audio they actually heard; it cannot approve a recording nobody has
listened to.

    python scripts/seed_listener_acceptances.py <project nguồn> <project đích> [--dry-run]

Run it right after `create`, next to `port_pronunciations.py` - the two do the same job for
the two kinds of human decision this project stores.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ebook_reader.database import ProjectDB  # noqa: E402

from scripts.port_listener_acceptances import _say_safely, read_acceptances  # noqa: E402


def existing(project: Path) -> set[tuple[str, str, str]]:
    database = project / "project.sqlite3"
    if not database.is_file():
        return set()
    with ProjectDB(database).connect() as conn:
        return {
            (str(a), str(b), str(c))
            for a, b, c in conn.execute(
                "SELECT segment_stable_id, wav_sha256, warning_code "
                "FROM listener_audio_acceptances"
            )
        }


def seed(source: Path, target: Path, *, dry_run: bool = False) -> tuple[int, int]:
    """Returns (seeded, already present)."""
    verdicts = read_acceptances(source)
    if not verdicts:
        _say_safely("project nguồn không có phán quyết nào")
        return 0, 0
    already = existing(target)
    database = ProjectDB(target / "project.sqlite3") if not dry_run else None
    seeded = skipped = 0
    for stable_id, checksum, code, note in verdicts:
        if (stable_id, checksum, code) in already:
            skipped += 1
            continue
        _say_safely(f"  GIEO  {stable_id} [{code}]")
        seeded += 1
        if database is not None:
            database.accept_segment_audio(
                segment_stable_id=stable_id,
                wav_sha256=checksum,
                warning_code=code,
                note=note or "gieo trước từ bản trước",
            )
    return seeded, skipped


def main(argv: list[str]) -> int:
    dry_run = "--dry-run" in argv
    positional = [value for value in argv if not value.startswith("--")]
    if len(positional) != 2:
        _say_safely(
            "dùng: seed_listener_acceptances.py <project nguồn> <project đích> [--dry-run]"
        )
        return 2
    source, target = (Path(value).resolve() for value in positional)
    for project in (source, target):
        if not (project / "project.sqlite3").is_file():
            _say_safely(f"không phải project: {project}")
            return 2

    seeded, skipped = seed(source, target, dry_run=dry_run)
    _say_safely("")
    _say_safely(
        f"{seeded} phán quyết được gieo"
        + (f", {skipped} đã có sẵn" if skipped else "")
        + (" (chạy thử, chưa ghi)" if dry_run else "")
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
