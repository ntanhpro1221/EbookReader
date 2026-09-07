"""Find every chapter the parser will refuse, in one pass instead of one per run.

`run` chunks chapters in order and raises on the first bad one, so a book with several bad
chapters costs one edit-and-restart cycle each. On this source that is 8 cycles: measured
2026-09-07, 8 of 478 chapters carry an unclosed dialogue quote, and the first of them
(019.txt) killed alpha.55 four seconds after it started.

`create` does not catch it either, so a project can be created, seeded with pronunciations,
verdicts and casting, and only then refuse to run.

    python scripts/check_sources.py <thư mục nguồn>

**It does not edit anything.** The missing quote could belong at the end of a verse, at the
end of a paragraph, or the stray one could be the typo - deciding that is reading the book,
not counting characters.

Two earlier versions of this script reported the wrong line, both times by trying to find
the fault with arithmetic on quote characters:

1. A depth counter. Once one quote is unmatched every pair after it is read off by one, so
   the counter starts calling closers openers and reports a line far past the fault.
2. The first odd line. Better, and still wrong on 019.txt, where it accused line 309 - the
   opening of a six-line oath that closes correctly at line 319. A quotation that spans
   blank-line-separated paragraphs is legitimate and puts an odd count on two lines that
   pair off with each other. The real fault in that chapter is line 339, a speech that lost
   its opening quote, thirty lines further on.

So this version does not guess. It asks the segmenter itself which chapters refuse, then
prints *every* odd line in those chapters and leaves the pairing to the reader. On a healthy
chapter the odd lines pair up; the unpaired one is the fault.
"""
from __future__ import annotations

import glob
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ebook_reader.text_processing import segment_chapter_text  # noqa: E402

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


def odd_quote_lines(text: str) -> list[tuple[int, str]]:
    """Every line whose quote characters do not pair off within the line.

    Not "the fault" - the candidates. A multi-paragraph quotation contributes two of these
    that belong together.
    """
    return [
        (number, line.strip())
        for number, line in enumerate(text.splitlines(), 1)
        if line.strip() and sum(line.count(mark) for mark in QUOTES) % 2
    ]


def refuses_to_segment(chapter_index: int, text: str) -> str | None:
    """The segmenter's own verdict, which is the only one that decides whether `run` stops."""
    try:
        segment_chapter_text(chapter_index, text)
    except RuntimeError as exc:
        return str(exc)
    return None


def check(source_dir: Path, pattern: str = "*.txt") -> tuple[list[tuple[Path, str, list[tuple[int, str]]]], int, int]:
    problems: list[tuple[Path, str, list[tuple[int, str]]]] = []
    total = 0
    segments = 0
    for index, path in enumerate(sorted(Path(p) for p in glob.glob(str(source_dir / pattern))), 1):
        total += 1
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            _say_safely(f"  KHÔNG ĐỌC ĐƯỢC {path.name}: {exc}")
            continue
        reason = refuses_to_segment(index, text)
        if reason is None:
            segments += len(segment_chapter_text(index, text))
            continue
        problems.append((path, reason, odd_quote_lines(text)))
    return problems, total, segments


def main(argv: list[str]) -> int:
    positional = [value for value in argv if not value.startswith("--")]
    if len(positional) != 1:
        _say_safely("dùng: check_sources.py <thư mục nguồn>")
        return 2
    source_dir = Path(positional[0]).resolve()
    if not source_dir.is_dir():
        _say_safely(f"không phải thư mục: {source_dir}")
        return 2

    problems, total, segments = check(source_dir)
    if not problems:
        _say_safely(f"{total} chương chia đoạn được hết — {segments:,} segment.")
        return 0

    _say_safely(f"{len(problems)}/{total} chương làm BỘ CHIA ĐOẠN DỪNG:")
    _say_safely("")
    for path, reason, odd in problems:
        _say_safely(f"  {path.name}  {reason}")
        if not odd:
            _say_safely("    (không có dòng nào lẻ dấu ngoặc — lỗi thuộc loại khác)")
        for number, line in odd:
            _say_safely(f"    dòng {number:>5}: {line[:104]}")
        if len(odd) > 1:
            _say_safely(
                "    ^ nhiều hơn một dòng lẻ: trích dẫn trải nhiều đoạn góp hai dòng"
                " ăn khớp nhau; dòng lẻ loi mới là lỗi."
            )
        _say_safely("")
    _say_safely(
        "Mỗi chương này sẽ làm `run` dừng ngay khi chia đoạn. Sửa hết một lượt rồi hãy chạy."
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
