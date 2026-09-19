"""In các đoạn của một project đã chia đoạn thành văn bản nguồn cho người gán nhãn đáp án.

    python scripts/model_eval/dump_segments.py <project> [--out src.txt]

Mỗi dòng: `[seq] p<đoạn văn> <loại parser khoá: N/D/T> | văn bản` - đúng dạng người gán nhãn A và B đọc
trong các vòng làm đáp án (docs/GOLD_GUIDE.md). Nếu project có nhiều chương, mỗi chương mở đầu bằng `== <tên>`.
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

LETTER = {"narration": "N", "dialogue": "D", "thought": "T"}


def dump(project: Path) -> list[str]:
    connection = sqlite3.connect(f"file:{project / 'project.sqlite3'}?mode=ro", uri=True)
    chapters = connection.execute("select id, title from chapters order by chapter_index").fetchall()
    lines: list[str] = []
    for chapter_id, title in chapters:
        if len(chapters) > 1:
            lines.append(f"== {title}")
        for seq, paragraph, kind, text in connection.execute(
            "select seq, paragraph_index, kind_hint, text from segments where chapter_id = ? order by seq",
            (chapter_id,),
        ):
            lines.append(f"[{seq}] p{paragraph} {LETTER.get(kind, kind)} | {text}")
    return lines


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("project", type=Path)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    text = "\n".join(dump(args.project)) + "\n"
    if args.out:
        args.out.write_text(text, encoding="utf-8")
        print(f"{args.out}: {text.count(chr(10))} dòng")
    else:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stdout.write(text)


if __name__ == "__main__":
    main()
