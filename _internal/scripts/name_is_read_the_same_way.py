"""Một cái tên có được đọc GIỐNG NHAU mỗi lần không — và đó không phải câu hỏi cổng neo tên hỏi.

    python scripts/name_is_read_the_same_way.py <project> [--min 20] [--csv <file>]

Hai câu hỏi khác nhau, và tài liệu cũ trộn chúng làm một:

1. **Bản thu có thoả cổng neo tên không** (`khớp%`) — cổng so chuỗi Whisper viết với dạng đọc đã
   ghim, qua bốn chế độ (`normalized_exact`, `diacritic_folded_exact`, `vietnamese_phoneme_exact`,
   `component_phonemes`). Trượt hết bốn thì `ASR_LOCKED_NAME_ANCHOR_MISMATCH` / `_REVIEW`.
2. **Cái tên có được đọc như nhau mỗi lần không** (`đỉnh%`) — trong những lần KHÔNG khớp,
   Whisper viết bao nhiêu dạng khác nhau, và dạng hay gặp nhất chiếm bao nhiêu phần. Một tên đọc
   ổn định mà cổng không nhận thì là lỗi của **cổng**; một tên mỗi lần một kiểu thì người nghe
   thật sự nghe hai người khác nhau, và đó là lỗi của **dạng đọc đã ghim**.

Đo trên lô 3 (2026-09-10, 3.923 phép kiểm neo, 60 tên có ≥20 lần): xem
docs/A_NAME_READ_MANY_WAYS.md. Con số dẫn tới cả hai kết luận cùng lúc — `Jake` → `Giếch` đọc
752 lần, 0% khớp, **89 dạng**, đỉnh 13%: mỗi lần một kiểu, đây là lỗi thật; còn 16 tên có âm
chèm "ờ" thì khớp 2,4% (so với 27,4%) mà **đỉnh 50,0% so với 51,9% — không khác** nghĩa là chúng
đọc ổn định và chỉ cổng không nhận.

`đỉnh%` tính trên các lần KHÔNG khớp, nên một tên khớp gần hết (Michael 85%) có `đỉnh%` thấp mà
vẫn tốt: mẫu của nó là phần dư nhỏ. Đọc hai cột cùng nhau, đừng đọc một cột.
"""
from __future__ import annotations

import argparse
import collections
import json
import sqlite3
import sys
from pathlib import Path

ANCHOR_METRIC_KEY = "locked_name_anchor_metrics"


def _say(line: str) -> None:
    try:
        print(line)
    except (UnicodeEncodeError, OSError, ValueError):
        sys.stdout.buffer.write(line.encode("utf-8", "replace") + b"\n")


def read_anchors(project: Path) -> dict[tuple[str, str], dict[str, object]]:
    """{(tên nguồn, dạng đọc đã ghim): số đo}. Một phép kiểm mang nhiều neo, đếm từng neo."""
    conn = sqlite3.connect(f"file:{project / 'project.sqlite3'}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT metrics_json FROM quality_checks"
            " WHERE failure_codes_json LIKE '%LOCKED_NAME_ANCHOR%'"
        ).fetchall()
    finally:
        conn.close()
    heard: dict[tuple[str, str], collections.Counter[str]] = collections.defaultdict(
        collections.Counter
    )
    matched: collections.Counter[tuple[str, str]] = collections.Counter()
    total: collections.Counter[tuple[str, str]] = collections.Counter()
    for row in rows:
        try:
            anchors = json.loads(row["metrics_json"])[ANCHOR_METRIC_KEY]["anchors"]
        except (ValueError, KeyError, TypeError):
            continue
        for anchor in anchors:
            key = (str(anchor.get("surface") or "?"), str(anchor.get("spoken_form") or ""))
            total[key] += 1
            if anchor.get("matched"):
                matched[key] += 1
                continue
            # Cửa sổ token mà bộ ghép gán cho neo này - tức "Whisper viết gì ở chỗ cái tên".
            # Rỗng nghĩa là bộ ghép coi neo bị BỎ HẲN, không phải đọc sai; đếm riêng.
            form = " ".join(str(t) for t in (anchor.get("aligned_tokens") or [])).strip()
            heard[key][form] += 1
    found: dict[tuple[str, str], dict[str, object]] = {}
    for key, count in total.items():
        forms = {f: n for f, n in heard[key].items() if f}
        spoken_count = sum(forms.values())
        dropped = heard[key].get("", 0)
        found[key] = {
            "surface": key[0],
            "spoken_form": key[1],
            "anchors": int(count),
            "matched": int(matched[key]),
            "match_percent": matched[key] / count * 100 if count else 0.0,
            "forms": collections.Counter(forms),
            "distinct_forms": len(forms),
            "peak_percent": (max(forms.values()) / spoken_count * 100) if spoken_count else None,
            "dropped": int(dropped),
        }
    return found


def duplicate_ledger_rows(
    anchors: dict[tuple[str, str], dict[str, object]],
) -> dict[str, list[dict[str, object]]]:
    """Tên nào có HAI dạng đọc đã ghim cùng lúc, và dạng nào đo tốt hơn.

    Sổ phát âm có cả `Jake → Giếch` và `Jake → Jake`, cả `Samael → Xa-men` và `Samael → Samael`;
    dạng nào được dùng phụ thuộc biến thể giao (`pronunciation_delivery_variant`). Với Samael,
    hai dạng đo lệch hẳn nhau - 69% so với 2% - nên một trong hai là lựa chọn tệ đang được dùng
    hàng trăm lần.
    """
    by_surface: dict[str, list[dict[str, object]]] = collections.defaultdict(list)
    for row in anchors.values():
        by_surface[str(row["surface"])].append(row)
    return {
        surface: sorted(rows, key=lambda r: -float(r["match_percent"]))
        for surface, rows in by_surface.items()
        if len(rows) > 1
    }


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("project", type=Path)
    parser.add_argument("--min", type=int, default=20, help="bỏ tên có ít hơn ngần này neo")
    parser.add_argument("--csv", type=Path, default=None)
    args = parser.parse_args(argv)

    if not (args.project / "project.sqlite3").is_file():
        _say(f"không phải project: {args.project}")
        return 2
    anchors = read_anchors(args.project)
    if not anchors:
        _say("Không có phép kiểm neo tên nào - project chưa chạy ASR, hoặc không có tên đã ghim.")
        return 0
    watched = [row for row in anchors.values() if int(row["anchors"]) >= args.min]
    watched.sort(key=lambda row: (row["peak_percent"] is None, row["peak_percent"]))

    _say(f"{len(anchors)} cặp (tên, dạng đọc); {len(watched)} cặp có ≥{args.min} neo.")
    _say("")
    _say(f"{'tên':16s} {'dạng đọc đã ghim':24s} {'neo':>5s} {'khớp%':>6s} {'dạng':>5s} {'đỉnh%':>6s}  Whisper hay viết")
    _say("-" * 116)
    for row in watched:
        top = ", ".join(f"{f!r}×{n}" for f, n in row["forms"].most_common(3))
        peak = f"{row['peak_percent']:5.0f}%" if row["peak_percent"] is not None else "    -"
        _say(
            f"{str(row['surface'])[:15]:16s} {str(row['spoken_form'])[:23]:24s}"
            f" {row['anchors']:5d} {row['match_percent']:5.0f}% {row['distinct_forms']:5d} {peak}  {top}"
        )
    _say("")
    _say("khớp% = thoả cổng neo tên.  đỉnh% = trong các lần KHÔNG khớp, dạng hay gặp nhất chiếm")
    _say("bao nhiêu. đỉnh% thấp + neo nhiều = mỗi lần đọc một kiểu, người nghe nghe hai người.")
    _say("đỉnh% thấp mà khớp% cao thì vô hại: mẫu chỉ là phần dư nhỏ.")

    duplicates = duplicate_ledger_rows({k: v for k, v in anchors.items() if v in watched})
    if duplicates:
        _say("")
        _say(f"{len(duplicates)} tên có NHIỀU dạng đọc trong sổ cùng lúc (dạng đo tốt nhất trước):")
        for surface, rows in sorted(duplicates.items()):
            forms = "  |  ".join(
                f"{row['spoken_form']!r} {row['match_percent']:.0f}% ({row['anchors']} neo)"
                for row in rows
            )
            _say(f"  {surface:20s} {forms}")

    if args.csv:
        lines = ["surface,spoken_form,anchors,match_percent,distinct_forms,peak_percent"]
        for row in sorted(anchors.values(), key=lambda r: -int(r["anchors"])):
            peak = "" if row["peak_percent"] is None else f"{row['peak_percent']:.1f}"
            lines.append(
                f"\"{row['surface']}\",\"{row['spoken_form']}\",{row['anchors']},"
                f"{row['match_percent']:.1f},{row['distinct_forms']},{peak}"
            )
        args.csv.write_text("\n".join(lines) + "\n", encoding="utf-8")
        _say("")
        _say(f"đã ghi {args.csv} ({len(anchors)} dòng)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
