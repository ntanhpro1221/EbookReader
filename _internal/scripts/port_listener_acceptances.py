"""Carry a listener's verdicts from one version's project to the next.

Listening is the scarcest resource in this project. On 2026-09-04 the owner sat through
fourteen segments and gave a verdict on each; eleven became acceptances. Those live in
alpha.44's database. alpha.45 and alpha.46 were fresh projects, so both started with zero,
and alpha.46 duly failed chapter 3 on c00003_s0000014 - a segment whose audio is
byte-identical to the one he had already listened to and passed.

Nothing was wrong with how the acceptance is stored. It is keyed by
(segment_stable_id, wav_sha256, warning_code): a person accepts *a recording*, not a row,
so re-cutting the take voids it. That is exactly right, and it is what makes this script
safe - an acceptance can only ever be carried to audio that is byte-identical to what was
heard.

    python scripts/port_listener_acceptances.py <source_project> <target_project> [--dry-run]

Refuses to carry a verdict when:
  - the target has no such segment, or has not synthesized it yet
  - the target's audio differs by a single byte from what was heard
  - the target segment no longer carries that warning
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ebook_reader.database import ProjectDB  # noqa: E402


def _say_safely(line: str) -> None:
    """Windows hands scripts a cp1252 stdout and every message here is Vietnamese."""
    try:
        print(line)
    except (UnicodeEncodeError, OSError, ValueError):
        try:
            sys.stdout.buffer.write(line.encode("utf-8", "replace") + b"\n")
        except Exception:  # noqa: BLE001
            pass


def read_acceptances(project: Path) -> list[tuple[str, str, str, str]]:
    """(stable_id, wav_sha256, warning_code, note) a listener recorded in this project."""
    connection = sqlite3.connect(project / "project.sqlite3")
    try:
        return [
            (str(a), str(b), str(c), str(d or ""))
            for a, b, c, d in connection.execute(
                "SELECT segment_stable_id, wav_sha256, warning_code, note "
                "FROM listener_audio_acceptances ORDER BY segment_stable_id"
            )
        ]
    finally:
        connection.close()


def target_segment(project: Path, stable_id: str) -> tuple[str, set[str], str] | None:
    """(wav_sha256, warnings, status) for one segment, or None when it is not there."""
    connection = sqlite3.connect(project / "project.sqlite3")
    connection.row_factory = sqlite3.Row
    try:
        row = connection.execute(
            "SELECT wav_sha256, warning_code, status FROM segments WHERE stable_id=?",
            (stable_id,),
        ).fetchone()
    finally:
        connection.close()
    if row is None:
        return None
    warnings = {value for value in str(row["warning_code"] or "").split("|") if value}
    return str(row["wav_sha256"] or ""), warnings, str(row["status"] or "")


def port(source: Path, target: Path, *, dry_run: bool = False) -> tuple[int, int]:
    """Carry every verdict that still applies. Returns (carried, examined)."""
    acceptances = read_acceptances(source)
    if not acceptances:
        _say_safely(f"{source.name}: không có phán quyết nào để chuyển")
        return 0, 0

    database = ProjectDB(target / "project.sqlite3") if not dry_run else None
    carried = 0
    for stable_id, heard_checksum, code, note in acceptances:
        found = target_segment(target, stable_id)
        if found is None:
            _say_safely(f"  bỏ qua  {stable_id} [{code}]: bản mới không có segment này")
            continue
        checksum, warnings, status = found
        if not checksum:
            _say_safely(f"  bỏ qua  {stable_id} [{code}]: bản mới chưa thu segment này")
            continue
        if checksum != heard_checksum:
            # The whole reason this is safe. He passed a recording; this is a different
            # one, and nobody has heard it.
            _say_safely(f"  bỏ qua  {stable_id} [{code}]: bản thu đã khác, phải nghe lại")
            continue
        if code not in warnings:
            _say_safely(f"  bỏ qua  {stable_id} [{code}]: bản mới không còn cảnh báo đó")
            continue
        _say_safely(f"  CHUYỂN  {stable_id} [{code}]")
        carried += 1
        if dry_run or database is None:
            continue
        carried_note = note or f"đã nghe ở {source.parent.name}"
        if status == "failed":
            # A failed segment needs its status moved too: a chapter publishes only when
            # nothing is failed, so suppressing the warning alone leaves it blocked.
            database.accept_failed_segment_audio(
                segment_stable_id=stable_id,
                wav_sha256=checksum,
                warning_code=code,
                note=carried_note,
            )
        else:
            database.accept_segment_audio(
                segment_stable_id=stable_id,
                wav_sha256=checksum,
                warning_code=code,
                note=carried_note,
            )
    return carried, len(acceptances)


def main(argv: list[str]) -> int:
    dry_run = "--dry-run" in argv
    positional = [value for value in argv if not value.startswith("--")]
    if len(positional) != 2:
        _say_safely(
            "dùng: port_listener_acceptances.py <project nguồn> <project đích> [--dry-run]"
        )
        return 2
    source, target = Path(positional[0]), Path(positional[1])
    for project in (source, target):
        if not (project / "project.sqlite3").is_file():
            _say_safely(f"không phải project: {project}")
            return 2

    carried, examined = port(source, target, dry_run=dry_run)
    _say_safely(
        f"{carried}/{examined} phán quyết được chuyển"
        f"{' (thử khan)' if dry_run else ''}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
