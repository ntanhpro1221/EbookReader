r"""Whisper viết `10h`, sách viết `mười giờ` — phép so ASR mất bao nhiêu, và nở đơn vị cứu được bao nhiêu?

    python scripts/measure_a_number_with_a_unit.py
    python scripts/measure_a_number_with_a_unit.py --all-books --limit 0

Chỉ đọc: mở database project ở chế độ read-only, không sinh audio, không ghi gì.

## Vì sao

`normalize_transcript` đã nở **token toàn chữ số** thành chữ (`_fold_number_digits`, tới 999), nên
`24` gặp `hai mươi bốn` là khớp. Nhưng token có **đơn vị dính liền** thì không phải toàn chữ số:

    sách:   "Hẹn nhau lúc mười giờ ba mươi."
    Whisper: "Hẹn nhau lúc 10h30."          -> `10h30` giữ nguyên, hai bên lệch hẳn ba từ

Dấu `%` còn tệ hơn một cách âm thầm: `normalize_transcript` thay mọi ký tự không phải chữ/số
bằng dấu cách, nên `25%` thành `25` (rồi nở thành `hai mươi lăm`) và chữ **phần trăm** của sách
không có gì để khớp.

## Script này đo gì

Với mọi đoạn đã có `asr_text`: tìm những đoạn mà **một trong hai bên** chứa số dính đơn vị, rồi
tính độ giống theo `asr.transcript_metrics` **hiện tại** và theo cách nở đơn vị, in ra:

    số đoạn có hình ấy
    số đoạn ĐANG dưới ngưỡng (min_similarity = 0.58) hoặc dưới 0.90
    số đoạn phép nở cứu (đi từ dưới 0.90 lên trên)
    số đoạn phép nở làm TỆ HƠN  (phải là 0 - phép nở lấy max của hai cách đọc)

Con số cuối là điều kiện để vá: một phép chuẩn hoá chỉ được thêm cơ hội khớp, không được lấy đi.
"""
from __future__ import annotations

import argparse
import glob
import re
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ebook_reader.asr import transcript_metrics  # noqa: E402
from ebook_reader.text_processing import vietnamese_number_words  # noqa: E402

try:
    from scripts.book_paths import VERSIONS  # noqa: E402
except ImportError:  # chạy trực tiếp
    from book_paths import VERSIONS  # noqa: E402

# `10h`, `10h30`, `25%`, `12kg`, `5km`… - số rồi tới đơn vị viết liền, không có dấu cách.
UNIT_NUMBER = re.compile(r"(?<![0-9A-Za-zÀ-ỹ])([0-9]{1,3})\s*(h|%|kg|km|m|cm|độ|°)(?![0-9A-Za-zÀ-ỹ])")
HOUR_MINUTE = re.compile(r"(?<![0-9A-Za-zÀ-ỹ])([0-9]{1,2})\s*h\s*([0-9]{1,2})(?![0-9A-Za-zÀ-ỹ])")
UNIT_WORDS = {
    "h": "giờ",
    "%": "phần trăm",
    "kg": "ki lô gam",
    "km": "ki lô mét",
    "m": "mét",
    "cm": "xen ti mét",
    "độ": "độ",
    "°": "độ",
}


def _say(line: str) -> None:
    try:
        print(line, flush=True)
    except UnicodeEncodeError:
        print(line.encode("ascii", "backslashreplace").decode("ascii"), flush=True)


def fold_number_units(text: str) -> str:
    """`10h30` → `mười giờ ba mươi`, `25%` → `hai mươi lăm phần trăm`. Không có thì trả nguyên."""

    def _hour_minute(match: re.Match[str]) -> str:
        hour, minute = int(match.group(1)), int(match.group(2))
        return f"{vietnamese_number_words(hour)} giờ {vietnamese_number_words(minute)}"

    def _unit(match: re.Match[str]) -> str:
        value, unit = int(match.group(1)), match.group(2)
        return f"{vietnamese_number_words(value)} {UNIT_WORDS[unit]}"

    return UNIT_NUMBER.sub(_unit, HOUR_MINUTE.sub(_hour_minute, text))


def has_unit_number(text: str) -> bool:
    return bool(UNIT_NUMBER.search(text) or HOUR_MINUTE.search(text))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--versions", type=Path, default=VERSIONS)
    parser.add_argument("--all-books", action="store_true")
    parser.add_argument("--limit", type=int, default=0, help="0 = không giới hạn")
    parser.add_argument("--floor", type=float, default=0.90)
    args = parser.parse_args(argv)

    roots = [args.versions]
    if args.all_books:
        for base in (args.versions.parent, args.versions.parent.parent):
            if base.is_dir():
                roots.append(base / "_versions")
                roots.extend(sorted(base.glob("*/_versions")))
    seen_root: set[str] = set()
    databases: list[str] = []
    for root in roots:
        key = str(root).casefold()
        if key in seen_root or not root.is_dir():
            continue
        seen_root.add(key)
        databases.extend(sorted(glob.glob(str(root / "*" / "*" / "project.sqlite3"))))

    total = 0
    with_shape = 0
    below = 0
    rescued: list[tuple[float, float, str, str]] = []
    harmed: list[tuple[float, float, str, str]] = []
    swapped_worse: list[tuple[float, float, str, str]] = []
    for database in databases:
        connection = sqlite3.connect(f"file:{Path(database).as_posix()}?mode=ro", uri=True)
        connection.row_factory = sqlite3.Row
        try:
            rows = connection.execute(
                "SELECT text, asr_text, asr_similarity FROM segments"
                " WHERE asr_text IS NOT NULL AND asr_text != ''"
            ).fetchall()
        except sqlite3.Error:
            continue
        finally:
            connection.close()
        for row in rows:
            total += 1
            expected, actual = str(row["text"]), str(row["asr_text"])
            if not (has_unit_number(expected) or has_unit_number(actual)):
                continue
            with_shape += 1
            now, _wer = transcript_metrics(expected, actual)
            swapped, _wer2 = transcript_metrics(
                fold_number_units(expected), fold_number_units(actual)
            )
            # Đúng phép tính sẽ ship: **cách đọc tốt hơn của hai**, không phải thay thẳng. Đo
            # thẳng thì 5 đoạn tệ hơn (`chín rưỡi` gặp `9h30` 0,93 -> 0,92), và một phép chuẩn
            # hoá chỉ được thêm cơ hội khớp, không được lấy đi - cùng lý lẽ mà
            # `tone_folded_similarity` đã dùng ("provably unable to fail anything the plain
            # comparison passed").
            after = max(now, swapped)
            if swapped < now - 1e-9:
                swapped_worse.append((now, swapped, expected, actual))
            if now < args.floor:
                below += 1
                if after >= args.floor:
                    rescued.append((now, after, expected, actual))
            if after < now - 1e-9:
                harmed.append((now, after, expected, actual))
            if args.limit and with_shape >= args.limit:
                break

    _say(f"{total} đoạn có bản ghi ASR trong {len(databases)} project")
    _say(f"{with_shape} đoạn có số dính đơn vị ở một trong hai bên")
    _say(f"{below} đoạn đang dưới {args.floor:.2f}")
    _say(f"{len(rescued)} đoạn phép nở đơn vị cứu lên trên {args.floor:.2f}")
    _say(f"{len(swapped_worse)} đoạn sẽ tệ hơn nếu THAY THẲNG bản nở vào")
    _say(f"{len(harmed)} đoạn tệ hơn khi lấy cách đọc tốt hơn của hai  (phải là 0)")
    for now, after, expected, actual in rescued[:8]:
        _say("")
        _say(f"  CỨU {now:.2f} -> {after:.2f}")
        _say(f"    sách  : {expected[:100]}")
        _say(f"    nghe  : {actual[:100]}")
    for now, after, expected, actual in (harmed or swapped_worse)[:5]:
        _say("")
        _say(f"  {'TỆ HƠN' if harmed else 'thay thẳng thì tệ hơn'} {now:.2f} -> {after:.2f}")
        _say(f"    sách  : {expected[:100]}")
        _say(f"    nghe  : {actual[:100]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
