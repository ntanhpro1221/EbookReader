"""Before asking for an ear: would that verdict actually unblock the chapter?

Listening is the scarcest resource in this project, and a chapter can be held shut by more
than one thing. Between alpha.46 and alpha.51 a verdict had to pass six separate gates, each
one found by letting a chapter die on it, and each fix revealed the next - so "this segment
carries the only blocking warning" has been wrong five times in a row.

This answers the question properly: copy the database, record the acceptances, and run every
gate a chapter must pass. If a chapter still stops afterwards, the listening would have been
spent for nothing and the report should say so before the person sits down.

    python scripts/simulate_acceptance.py <project_root>
    python scripts/simulate_acceptance.py <project_root> --segment c00005_s0000013_… --segment …

With no `--segment`, it simulates accepting every blocking warning the project currently
carries - the optimistic case, which is the useful one: if even that does not reach 10/10,
listening is not what is missing.

Never touches the project. The copy is made in a temporary directory and thrown away, because
`ProjectDB` writes on construction and a simulation must not be able to change the thing it is
simulating.
"""
from __future__ import annotations

import json
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ebook_reader.database import ProjectDB  # noqa: E402
from ebook_reader.pipeline import (  # noqa: E402
    HIGH_QUALITY_ALLOWED_SEGMENT_WARNINGS,
    SEGMENT_AUDIO_QUALITY_STAGE,
    SEGMENT_PERCEPTUAL_QUALITY_STAGE,
)


def _say_safely(line: str) -> None:
    """Windows hands scripts a cp1252 stdout and every message here is Vietnamese."""
    try:
        print(line)
    except (UnicodeEncodeError, OSError, ValueError):
        try:
            sys.stdout.buffer.write(line.encode("utf-8", "replace") + b"\n")
        except Exception:  # noqa: BLE001
            pass


def blocking_warnings(project: Path) -> list[tuple[str, str, str, str]]:
    """(stable_id, warning_code, wav_sha256, status) for every warning holding a chapter."""
    connection = sqlite3.connect(f"file:{project / 'project.sqlite3'}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        rows = connection.execute(
            "SELECT stable_id, warning_code, wav_sha256, status FROM segments "
            "WHERE warning_code IS NOT NULL AND warning_code <> ''"
        ).fetchall()
        accepted = {
            (str(a), str(b))
            for a, b in connection.execute(
                "SELECT segment_stable_id, wav_sha256 FROM listener_audio_acceptances"
            )
        }
    finally:
        connection.close()
    out: list[tuple[str, str, str, str]] = []
    for row in rows:
        checksum = str(row["wav_sha256"] or "")
        if not checksum or (str(row["stable_id"]), checksum) in accepted:
            continue
        for code in sorted(
            {value for value in str(row["warning_code"]).split("|") if value}
            - HIGH_QUALITY_ALLOWED_SEGMENT_WARNINGS
        ):
            out.append((str(row["stable_id"]), code, checksum, str(row["status"])))
    return out


def perceptual_qa_enabled(project: Path) -> bool:
    """Does this project actually run the perceptual check?

    It stopped being part of `high_quality` on 2026-09-07, and the pipeline skips its
    evidence entirely when it is off. A simulation that demands that evidence anyway reports
    chapters blocked on a gate the real run does not have - which sends somebody to listen
    for nothing, the exact failure this script exists to prevent.
    """
    settings_file = project / "book_settings.json"
    if not settings_file.is_file():
        return True
    try:
        settings = json.loads(settings_file.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        # Unreadable settings must not silently relax a gate: assume the stricter world.
        return True
    return bool((settings.get("perceptual_qa") or {}).get("enabled", False))


def chapter_verdicts(db: ProjectDB, *, perceptual: bool = True) -> dict[int, dict[str, bool]]:
    """Every gate a chapter must pass, per chapter, under the acceptances now recorded."""
    accepted = db.accepted_segment_warnings()
    verdicts: dict[int, dict[str, bool]] = {}
    with db.connect() as conn:
        chapters = conn.execute(
            "SELECT id, chapter_index FROM chapters ORDER BY chapter_index"
        ).fetchall()
    for chapter in chapters:
        chapter_id = int(chapter["id"])
        blocking = []
        for row in db.list_segments(chapter_id=chapter_id):
            codes = {value for value in str(row["warning_code"] or "").split("|") if value}
            heard = accepted.get(
                (str(row["stable_id"]), str(row["wav_sha256"] or "")), frozenset()
            )
            if sorted(codes - HIGH_QUALITY_ALLOWED_SEGMENT_WARNINGS - set(heard)):
                blocking.append(str(row["stable_id"]))
        verdicts[int(chapter["chapter_index"])] = {
            "cảnh báo": not blocking,
            "bằng chứng ASR": db.chapter_segments_have_current_audio_qa(
                chapter_id, SEGMENT_AUDIO_QUALITY_STAGE
            ),
            "bằng chứng cảm thụ": (
                not perceptual
                or db.chapter_segments_have_current_audio_qa(
                    chapter_id, SEGMENT_PERCEPTUAL_QUALITY_STAGE
                )
            ),
            "đếm status": db.chapter_is_publishable(chapter_id),
        }
    return verdicts


def simulate(project: Path, wanted: set[str] | None) -> tuple[list[int], list[int]]:
    """Accept the chosen warnings on a copy. Returns (chapters freed, chapters still shut)."""
    candidates = [
        item for item in blocking_warnings(project)
        if wanted is None or item[0] in wanted
    ]
    if not candidates:
        _say_safely("không có cảnh báo nào đang chặn để mô phỏng")
        return [], []

    with tempfile.TemporaryDirectory() as workspace:
        copy = Path(workspace) / "sim"
        copy.mkdir()
        shutil.copy2(project / "project.sqlite3", copy / "project.sqlite3")
        db = ProjectDB(copy / "project.sqlite3")
        perceptual = perceptual_qa_enabled(project)
        before = chapter_verdicts(db, perceptual=perceptual)
        for stable_id, code, checksum, status in candidates:
            _say_safely(f"  chấp nhận {stable_id} [{code}] (đang {status})")
            record = (
                db.accept_failed_segment_audio
                if status == "failed"
                else db.accept_segment_audio
            )
            record(
                segment_stable_id=stable_id,
                wav_sha256=checksum,
                warning_code=code,
                note="mô phỏng",
            )
        after = chapter_verdicts(db, perceptual=perceptual)

    freed, stuck = [], []
    for index, gates in sorted(after.items()):
        was_open = all(before[index].values())
        now_open = all(gates.values())
        if was_open:
            continue
        (freed if now_open else stuck).append(index)
        if not now_open:
            failing = [name for name, ok in gates.items() if not ok]
            _say_safely(f"  chương {index}: VẪN CHẶN ở {', '.join(failing)}")
    return freed, stuck


def main(argv: list[str]) -> int:
    wanted = {
        argv[index + 1]
        for index, value in enumerate(argv)
        if value == "--segment" and index + 1 < len(argv)
    } or None
    positional = [
        value
        for index, value in enumerate(argv)
        if not value.startswith("--") and not (index and argv[index - 1] == "--segment")
    ]
    if len(positional) != 1:
        _say_safely(
            "dùng: simulate_acceptance.py <project_root> [--segment <stable_id> ...]"
        )
        return 2
    project = Path(positional[0]).resolve()
    if not (project / "project.sqlite3").is_file():
        _say_safely(f"không phải project: {project}")
        return 2

    freed, stuck = simulate(project, wanted)
    _say_safely("")
    if freed:
        _say_safely(f"nghe xong sẽ gỡ được: chương {freed}")
    if stuck:
        _say_safely(
            f"KHÔNG gỡ được dù có nghe: chương {stuck} — nghe những đoạn này là phí công, "
            "chúng còn chặn ở cổng khác"
        )
    if not freed and not stuck:
        _say_safely("không chương nào đang chờ quyết định")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
