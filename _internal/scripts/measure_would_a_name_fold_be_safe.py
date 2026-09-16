"""Luật đề xuất: "nhãn vắng mặt trong CHÍNH văn bản của project, và có ĐÚNG MỘT tên trong văn bản
cách nó <= 2 phép sửa, thì hai cái là một người". Nó có gộp sai ca nào không?

    python scripts/measure_would_a_name_fold_be_safe.py [book2|book1]

Chỉ đọc. Đây là phép "đo trước khi vá" cho mục hàng chờ "một cái tên không có trong nguồn thì
không phải tên". Tầng phân tích chỉ thấy **các chương của project mình**, nên luật phải dùng đúng
chừng ấy bằng chứng — không phải cả cuốn sách như hai script đo trước.

In ba nhóm:

    GOP DUOC   vang mat + dung MOT ung vien  -> luat gop, va gop dung
    LUONG LU   vang mat + NHIEU ung vien     -> luat bo qua (phai the)
    KHONG RO   vang mat + KHONG ung vien nao -> luat bo qua; co the la ten that
                                                chi duoc goi o chuong khac
"""
from __future__ import annotations

import glob
import re
import sqlite3
import sys
import unicodedata
from collections import defaultdict
from pathlib import Path

BOOK = sys.argv[1] if len(sys.argv) > 1 else "book2"
VERSIONS = Path(
    "D:/Novels/Audiobooks/book2/_versions" if BOOK == "book2" else "D:/Novels/Audiobooks/_versions"
)
LATIN_NAME = re.compile(r"^[A-Za-z][A-Za-z'.-]*(?: [A-Za-z][A-Za-z'.-]*)*$")
RESERVED = {"NARRATOR", "UNKNOWN"}


def say(line: str = "") -> None:
    try:
        print(line, flush=True)
    except UnicodeEncodeError:
        print(line.encode("ascii", "backslashreplace").decode("ascii"), flush=True)


def fold(text: str) -> str:
    stripped = "".join(
        ch
        for ch in unicodedata.normalize("NFD", text.casefold())
        if unicodedata.category(ch) != "Mn"
    )
    return unicodedata.normalize("NFC", stripped).replace("đ", "d")


def distance(left: str, right: str, limit: int = 2) -> int | None:
    if abs(len(left) - len(right)) > limit:
        return None
    previous = list(range(len(right) + 1))
    for i, a in enumerate(left, 1):
        current = [i]
        for j, b in enumerate(right, 1):
            current.append(min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (a != b)))
        if min(current) > limit:
            return None
        previous = current
    return previous[-1] if previous[-1] <= limit else None


def main() -> int:
    foldable: dict[tuple[str, str], list[str]] = defaultdict(list)
    ambiguous: dict[tuple[str, str], list[str]] = defaultdict(list)
    orphan: dict[str, list[str]] = defaultdict(list)

    for database in sorted(glob.glob(str(VERSIONS / "*" / "*" / "project.sqlite3"))):
        path = Path(database)
        connection = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
        connection.row_factory = sqlite3.Row
        try:
            names = [
                str(row["canonical_name"]).strip()
                for row in connection.execute("SELECT canonical_name FROM characters")
            ]
            text = fold(
                "\n".join(
                    str(row[0] or "") for row in connection.execute("SELECT text FROM segments")
                )
            )
        except sqlite3.Error:
            connection.close()
            continue
        connection.close()

        names = [n for n in names if n.upper() not in RESERVED and LATIN_NAME.match(n)]
        present = [
            n for n in names if re.search(rf"(?<!\w){re.escape(fold(n))}(?!\w)", text)
        ]
        for name in names:
            if name in present:
                continue
            near = sorted(
                {
                    other
                    for other in present
                    if distance(fold(name), fold(other)) not in (None, 0)
                }
            )
            if len(near) == 1:
                foldable[(name, near[0])].append(path.parent.name)
            elif near:
                ambiguous[(name, ", ".join(near))].append(path.parent.name)
            else:
                orphan[name].append(path.parent.name)

    say(f"{BOOK}: luat se GOP {len(foldable)} cap; bo qua {len(ambiguous)} ca luong lu"
        f" va {len(orphan)} ca khong co ung vien")
    say("")
    say("### GOP DUOC (vang mat + dung MOT ung vien trong van ban cua project)")
    for (name, other), projects in sorted(foldable.items(), key=lambda kv: -len(kv[1])):
        say(f"  {name:<22} -> {other:<22} o {len(projects)} project: {', '.join(projects[:3])}")
    say("")
    say("### LUONG LU - luat bo qua")
    for (name, others), projects in sorted(ambiguous.items(), key=lambda kv: -len(kv[1]))[:12]:
        say(f"  {name:<22} <-> {others[:60]:<60} o {len(projects)} project")
    say("")
    say(f"### KHONG CO UNG VIEN - luat bo qua ({len(orphan)} nhan)")
    for name, projects in sorted(orphan.items(), key=lambda kv: -len(kv[1]))[:12]:
        say(f"  {name:<22} o {len(projects)} project")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
