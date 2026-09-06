"""Carry a book's locked name readings into the next version, before it starts.

A name's reading is not stable across runs. Measured over four versions of the same book,
112 names each: alpha.46 differs from alpha.48 on 4, alpha.49 on 3, alpha.47 on none. About
3%, and always the uncertain ones - `Rare` came out `Ra`, `Rây` and `Rê-ay`; `Theosbane` came
out `theo-bên`, `Theo-bên` and `Thê-ô-ban`.

It is not a seeding problem. The name request already runs at `temperature: 0.0`, and greedy
decoding does not sample, so a seed would change nothing. What moves is the arithmetic: on a
near-tie between two tokens, GPU reductions do not have to land the same way twice. That is
why it hits exactly the names the model is unsure about.

The cost is not the reading itself but what it drags with it. Every drifted name changes the
audio of every segment containing it, and a listener's verdict is bound to a recording - so a
name that drifts silently voids the listening already spent on those segments. It is also why
`pronounce` has always felt like it does not stick: it fixes one project, and the next version
starts from nothing.

`normalize_name_pronunciations` skips any name that already has a locked reading, so seeding
the table before `run` is enough: those names are never sent to the model at all. Stable
readings, a smaller name phase, and a correction that survives the version it was made in.

    python scripts/port_pronunciations.py <source_project> <target_project> [--dry-run]

Run it **between `create` and `run`**. It refuses a target whose segments have been analysed:
changing a reading after that point moves the spoken text under audio that already exists,
which is the same trap that makes `pronounce` refuse to run mid-project.
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ebook_reader.database import LISTENER_PRONUNCIATION_SOURCE, ProjectDB  # noqa: E402


def _say_safely(line: str) -> None:
    """Windows hands scripts a cp1252 stdout and every message here is Vietnamese."""
    try:
        print(line)
    except (UnicodeEncodeError, OSError, ValueError):
        try:
            sys.stdout.buffer.write(line.encode("utf-8", "replace") + b"\n")
        except Exception:  # noqa: BLE001
            pass


def locked_readings(project: Path) -> list[tuple[str, str, str, str, float]]:
    """(surface, normalized_surface, spoken_form, source, confidence), locked rows only."""
    connection = sqlite3.connect(f"file:{project / 'project.sqlite3'}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        return [
            (
                str(row["surface"]),
                str(row["normalized_surface"]),
                str(row["spoken_form"]),
                str(row["source"]),
                float(row["confidence"] or 0.0),
            )
            for row in connection.execute(
                "SELECT surface, normalized_surface, spoken_form, source, confidence "
                "FROM pronunciations WHERE locked=1 ORDER BY normalized_surface"
            )
        ]
    finally:
        connection.close()


def analysed_segment_count(project: Path) -> int:
    """How far the target has got. Anything above zero means it is too late to seed."""
    connection = sqlite3.connect(f"file:{project / 'project.sqlite3'}?mode=ro", uri=True)
    try:
        row = connection.execute(
            "SELECT COUNT(*) FROM segments WHERE status <> 'pending'"
        ).fetchone()
        return int(row[0]) if row else 0
    except sqlite3.OperationalError:
        return 0
    finally:
        connection.close()


def existing_keys(project: Path) -> set[str]:
    connection = sqlite3.connect(f"file:{project / 'project.sqlite3'}?mode=ro", uri=True)
    try:
        return {
            str(key)
            for (key,) in connection.execute(
                "SELECT normalized_surface FROM pronunciations WHERE locked=1"
            )
        }
    except sqlite3.OperationalError:
        return set()
    finally:
        connection.close()


def port(source: Path, target: Path, *, dry_run: bool = False) -> tuple[int, int]:
    """Seed the target's locked readings from the source. Returns (carried, examined)."""
    readings = locked_readings(source)
    if not readings:
        _say_safely(f"{source.name}: không có cách đọc nào đã khóa")
        return 0, 0

    analysed = analysed_segment_count(target)
    if analysed:
        _say_safely(
            f"TỪ CHỐI: {target.name} đã phân tích {analysed} segment. Đổi cách đọc lúc này "
            "làm trôi spoken text dưới audio đã có - chạy script này giữa `create` và `run`."
        )
        return 0, len(readings)

    already = existing_keys(target)
    database = None if dry_run else ProjectDB(target / "project.sqlite3")
    carried = 0
    for surface, key, spoken_form, source_name, confidence in readings:
        if key in already:
            _say_safely(f"  bỏ qua  {surface}: bản mới đã có cách đọc khóa sẵn")
            continue
        marker = " [người nghe chọn]" if source_name == LISTENER_PRONUNCIATION_SOURCE else ""
        _say_safely(f"  CHUYỂN  {surface} -> {spoken_form}{marker}")
        carried += 1
        if database is None:
            continue
        if source_name == LISTENER_PRONUNCIATION_SOURCE:
            # Keeps the source as listener_choice, which is what stops the machine - and
            # `relock_machine_pronunciation` - from ever rewriting it again.
            database.set_listener_pronunciation(
                surface=surface,
                normalized_surface=key,
                spoken_form=spoken_form,
                source=LISTENER_PRONUNCIATION_SOURCE,
            )
        else:
            database.upsert_pronunciation(
                surface=surface,
                normalized_surface=key,
                spoken_form=spoken_form,
                confidence=confidence,
                source=source_name,
                locked=True,
            )
    return carried, len(readings)


def main(argv: list[str]) -> int:
    dry_run = "--dry-run" in argv
    positional = [value for value in argv if not value.startswith("--")]
    if len(positional) != 2:
        _say_safely("dùng: port_pronunciations.py <project nguồn> <project đích> [--dry-run]")
        return 2
    source, target = (Path(value).resolve() for value in positional)
    for project in (source, target):
        if not (project / "project.sqlite3").exists():
            _say_safely(f"không phải project: {project}")
            return 2
    carried, examined = port(source, target, dry_run=dry_run)
    _say_safely(f"{carried}/{examined} cách đọc được chuyển{' (thử khan)' if dry_run else ''}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
