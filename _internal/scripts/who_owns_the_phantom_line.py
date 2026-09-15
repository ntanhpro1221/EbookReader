"""Neu bo mot nguoi noi bia ra, ai la chu cua cau ay? In ngu canh de doc bang tay.

    python who_owns_the_phantom_line.py [--book2|--book1] [--name Nghe]
"""
import argparse
import glob
import sqlite3
import sys
from pathlib import Path

PHANTOMS = ("T\u00f4i", "M\u00ecnh", "Nghe", "Giai", "Tin")
RESERVED = {"narrator", "ng\u01b0\u1eddi d\u1eabn truy\u1ec7n", "unknown", "", "none"}


def say(line):
    try:
        print(line, flush=True)
    except UnicodeEncodeError:
        print(line.encode("ascii", "backslashreplace").decode("ascii"), flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=r"D:/Novels/Audiobooks/book2/_versions")
    parser.add_argument("--name", default=None)
    parser.add_argument("--before", type=int, default=5)
    parser.add_argument("--after", type=int, default=2)
    parser.add_argument("--limit", type=int, default=12)
    args = parser.parse_args()

    names = (args.name,) if args.name else PHANTOMS
    shown = 0
    for database in sorted(glob.glob(str(Path(args.root) / "*" / "*" / "project.sqlite3"))):
        if shown >= args.limit:
            break
        connection = sqlite3.connect(f"file:{Path(database).as_posix()}?mode=ro", uri=True)
        connection.row_factory = sqlite3.Row
        try:
            rows = connection.execute(
                "SELECT chapter_id, seq, speaker, kind, text FROM segments ORDER BY chapter_id, seq"
            ).fetchall()
        except sqlite3.Error:
            connection.close()
            continue
        connection.close()
        by_chapter = {}
        for row in rows:
            by_chapter.setdefault(row["chapter_id"], []).append(row)
        for chapter, items in by_chapter.items():
            for index, row in enumerate(items):
                if str(row["speaker"] or "") not in names or shown >= args.limit:
                    continue
                shown += 1
                nearest = None
                for earlier in reversed(items[:index]):
                    speaker = str(earlier["speaker"] or "").strip()
                    if (
                        speaker
                        and speaker not in names
                        and speaker.casefold() not in RESERVED
                    ):
                        nearest = speaker
                        break
                say("")
                say(
                    f"=== {Path(database).parent.name} ch{chapter} seq{row['seq']} "
                    f"[{row['speaker']}]  gan nhat truoc do: {nearest or '(khong co)'}"
                )
                for item in items[max(0, index - args.before) : index + args.after + 1]:
                    mark = ">>" if item["seq"] == row["seq"] else "  "
                    speaker = str(item["speaker"] or "-")
                    say(f" {mark} seq{item['seq']:>4} [{speaker:<12}] {str(item['text'])[:96]}")
    say("")
    say(f"{shown} ca")
    return 0


if __name__ == "__main__":
    sys.exit(main())
