"""Which locked names got through only because the phoneme rescue let them, and what they said.

The rescue exists because the anchor check was comparing Whisper's spelling to a Vietnamese
transliteration and calling the difference a mispronunciation. It is meant to **discriminate**,
not to be generous: on alpha.52's data it accepted "Samen Kaiser theo bên" and still refused
"Sam Min Kaiser theo bên", which is the whole point.

A fix that only ever passes more has not distinguished anything - it has moved the defect from
refusing good takes to accepting bad ones, and that second kind writes the flaw into the book
where only a listener will find it. So this lists every take the rescue carried, with what
Whisper actually heard, cheaply enough to skim after a run.

    python scripts/anchor_rescue_report.py <project_root> [--limit 40]

Read it looking for the thing that should worry you: a transcript where the name is genuinely
wrong and the rescue took it anyway.
"""
from __future__ import annotations

import collections
import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _say_safely(line: str) -> None:
    try:
        print(line)
    except (UnicodeEncodeError, OSError, ValueError):
        try:
            sys.stdout.buffer.write(line.encode("utf-8", "replace") + b"\n")
        except Exception:  # noqa: BLE001
            pass


def rescues(project: Path) -> tuple[collections.Counter, list[tuple[str, str, str]]]:
    """(status counts, [(surface, spoken_form, transcript)] for rescued anchors)."""
    connection = sqlite3.connect(
        f"file:{project / 'project.sqlite3'}?mode=ro", uri=True
    )
    connection.row_factory = sqlite3.Row
    counts: collections.Counter = collections.Counter()
    carried: list[tuple[str, str, str]] = []
    seen: set[tuple[str, str]] = set()
    try:
        rows = connection.execute(
            "SELECT metrics_json FROM quality_checks WHERE stage='segment_asr_decode_v1'"
        )
        for row in rows:
            try:
                metrics = json.loads(row["metrics_json"] or "{}")
            except ValueError:
                continue
            transcript = str(metrics.get("transcript") or "")
            anchors = (metrics.get("locked_name_anchor_metrics") or {}).get("anchors")
            for anchor in anchors or []:
                status = str(anchor.get("status"))
                counts[status] += 1
                if status != "matched_by_component_phonemes":
                    continue
                key = (str(anchor.get("surface")), transcript)
                if key in seen:
                    continue
                seen.add(key)
                carried.append(
                    (str(anchor.get("surface")), str(anchor.get("spoken_form")), transcript)
                )
    finally:
        connection.close()
    return counts, carried


def main(argv: list[str]) -> int:
    limit = 40
    for index, value in enumerate(argv):
        if value == "--limit" and index + 1 < len(argv):
            limit = int(argv[index + 1])
    positional = [
        value
        for index, value in enumerate(argv)
        if not value.startswith("--") and not (index and argv[index - 1] == "--limit")
    ]
    if len(positional) != 1:
        _say_safely("dùng: anchor_rescue_report.py <project_root> [--limit 40]")
        return 2
    project = Path(positional[0]).resolve()
    if not (project / "project.sqlite3").is_file():
        _say_safely(f"không phải project: {project}")
        return 2

    counts, carried = rescues(project)
    total = sum(counts.values())
    _say_safely("trạng thái neo tên:")
    for status, number in counts.most_common():
        share = f"{100 * number / total:.1f}%" if total else "-"
        _say_safely(f"  {status:34} {number:5}  {share}")
    _say_safely("")
    _say_safely(
        f"{len(carried)} bản thu đi qua được NHỜ khớp âm — soát xem có cái nào đọc SAI tên "
        "mà vẫn lọt:"
    )
    for surface, spoken, transcript in carried[:limit]:
        _say_safely(f"  {surface} ({spoken})")
        _say_safely(f"    Whisper: {transcript[:100]}")
    if len(carried) > limit:
        _say_safely(f"  … còn {len(carried) - limit} cái nữa (--limit để xem thêm)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
