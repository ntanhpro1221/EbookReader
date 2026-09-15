"""Bao nhieu muc trong NAME_CANDIDATE_EXCLUSIONS chua tung khop gi, va gop dau se dap ai?

`_name_candidate_key(value) = value.replace("'", "'").casefold()` - KHONG bo dau. Nhung danh
sach loai tru lai viet KHONG DAU ("toi", "minh", "nguoi", "khong"...), nen nhung muc ay khong
bao gio khop mot ten tieng Viet co dau. Script do hai chieu:

  (1) hom nay danh sach that su chan duoc nhung ten nao trong kho
  (2) neu doi `_name_candidate_key` sang gop dau thi nhung ten NAO bi chan them

Chi doc.
"""
import glob
import sqlite3
import sys
import unicodedata
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ebook_reader.analysis import (  # noqa: E402
    ATTRIBUTION_SENTENCE_START_EXCLUSIONS,
    NAME_CANDIDATE_EXCLUSIONS,
    _name_candidate_key,
)

ROOTS = (r"D:/Novels/Audiobooks/book2/_versions", r"D:/Novels/Audiobooks/_versions")
RESERVED = {"narrator", "unknown", "none", ""}


def say(line):
    try:
        print(line, flush=True)
    except UnicodeEncodeError:
        print(line.encode("ascii", "backslashreplace").decode("ascii"), flush=True)


def ascii_fold(value: str) -> str:
    lowered = value.replace("\u2019", "'").casefold().replace("\u0111", "d")
    decomposed = unicodedata.normalize("NFD", lowered)
    return "".join(char for char in decomposed if not unicodedata.combining(char))


def main() -> int:
    speakers: Counter[str] = Counter()
    for root in ROOTS:
        for database in sorted(glob.glob(str(Path(root) / "*" / "*" / "project.sqlite3"))):
            connection = sqlite3.connect(f"file:{Path(database).as_posix()}?mode=ro", uri=True)
            try:
                rows = connection.execute(
                    "SELECT speaker, COUNT(*) FROM segments WHERE speaker IS NOT NULL"
                    " GROUP BY speaker"
                ).fetchall()
            except sqlite3.Error:
                continue
            finally:
                connection.close()
            for name, count in rows:
                name = str(name).strip()
                if name and name.casefold() not in RESERVED:
                    speakers[name] += count

    say(f"{len(speakers)} ten nguoi noi trong kho, {sum(speakers.values())} cau")
    say("")

    folded_hits = {}
    current_hits = {}
    for name, count in speakers.items():
        key = _name_candidate_key(name)
        folded = ascii_fold(name)
        if key in NAME_CANDIDATE_EXCLUSIONS:
            current_hits[name] = count
        elif folded in NAME_CANDIDATE_EXCLUSIONS:
            folded_hits[name] = count

    say(f"[1] hom nay danh sach chan {len(current_hits)} ten:")
    for name, count in sorted(current_hits.items(), key=lambda item: -item[1]):
        say(f"      {count:>5}  {name}")
    say("")
    say(f"[2] gop dau se chan THEM {len(folded_hits)} ten:")
    for name, count in sorted(folded_hits.items(), key=lambda item: -item[1]):
        say(f"      {count:>5}  {name}   (khoa gop dau: {ascii_fold(name)})")
    say("")
    starts = {
        name: count
        for name, count in speakers.items()
        if _name_candidate_key(name.split()[0]) in ATTRIBUTION_SENTENCE_START_EXCLUSIONS
    }
    say(f"[3] danh sach mo-dau-cau chan {len(starts)} ten: {sorted(starts)}")
    say("")
    marked = sum(1 for entry in NAME_CANDIDATE_EXCLUSIONS if ascii_fold(entry) != entry)
    say(
        f"NAME_CANDIDATE_EXCLUSIONS co {len(NAME_CANDIDATE_EXCLUSIONS)} muc, {marked} muc co dau"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
