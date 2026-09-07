"""Find every chapter the parser will refuse, in one pass instead of one per run.

`run` chunks chapters in order and raises on the first bad one, so a book with several bad
chapters costs one edit-and-restart cycle each. On this source that is 13 cycles: measured
2026-09-07, 13 of 478 chapters carry an unclosed dialogue quote, and the first of them
(019.txt) killed alpha.55 four seconds after it started.

`create` does not catch it either, so a project can be created, seeded with pronunciations,
verdicts and casting, and only then refuse to run.

    python scripts/check_sources.py <thư mục nguồn> [--range 000..477]

Reports the file, the line where the quote opens and is never closed, and the text of that
line, so the whole set can be fixed in one sitting.

**It does not edit anything.** The missing quote could belong at the end of a verse, at the
end of a paragraph, or the stray one could be the typo - deciding that is reading the book,
not counting characters.
"""
from __future__ import annotations

import glob
import re
import sys
from pathlib import Path

# Both shapes, because the parser accepts both and pairs them across shapes: its pattern is
# [“"] … [”"]. Counting only the straight one blamed five chapters that are perfectly fine,
# which is what the first version of this script did.
QUOTES = '"“”'


def _say_safely(line: str) -> None:
    try:
        print(line)
    except (UnicodeEncodeError, OSError, ValueError):
        try:
            sys.stdout.buffer.write(line.encode("utf-8", "replace") + b"\n")
        except Exception:  # noqa: BLE001
            pass


def unclosed_quote(text: str) -> tuple[int, str] | None:
    """(line number, that line) of the first line whose quotes do not pair off, or None.

    The first odd line is the answer and tracking depth is not, which the first version of
    this got wrong. Once one quote is unmatched every pair after it is read off by one, so a
    depth counter starts calling closers openers and reports a line far past the fault - on
    019.txt it pointed at line 357, a sentence that opens and closes cleanly, when the verse
    that never closes starts at 309.
    """
    if sum(text.count(mark) for mark in QUOTES) % 2 == 0:
        return None
    for number, line in enumerate(text.splitlines(), 1):
        if sum(line.count(mark) for mark in QUOTES) % 2:
            return number, line.strip()
    return None


def check(source_dir: Path, pattern: str = "*.txt") -> list[tuple[Path, int, str]]:
    found: list[tuple[Path, int, str]] = []
    for path in sorted(Path(p) for p in glob.glob(str(source_dir / pattern))):
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            _say_safely(f"  KHÔNG ĐỌC ĐƯỢC {path.name}: {exc}")
            continue
        problem = unclosed_quote(text)
        if problem is not None:
            found.append((path, problem[0], problem[1]))
    return found


def main(argv: list[str]) -> int:
    positional = [value for value in argv if not value.startswith("--")]
    if len(positional) != 1:
        _say_safely("dùng: check_sources.py <thư mục nguồn>")
        return 2
    source_dir = Path(positional[0]).resolve()
    if not source_dir.is_dir():
        _say_safely(f"không phải thư mục: {source_dir}")
        return 2

    problems = check(source_dir)
    total = len(glob.glob(str(source_dir / "*.txt")))
    if not problems:
        _say_safely(f"{total} chương, không chương nào có dấu ngoặc kép treo")
        return 0

    _say_safely(f"{len(problems)}/{total} chương có dấu ngoặc kép MỞ MÀ KHÔNG ĐÓNG:")
    _say_safely("")
    for path, number, line in problems:
        _say_safely(f"  {path.name}  dòng {number}")
        _say_safely(f"    {line[:110]}")
    _say_safely("")
    _say_safely(
        "Mỗi chương này sẽ làm `run` dừng ngay khi chia đoạn. Sửa hết một lượt rồi hãy chạy."
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
