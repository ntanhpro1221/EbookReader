"""Nhân vật nào mang một cái tên KHÔNG có trong nguồn — và nó có đang giữ một giọng không?

    python scripts/measure_a_name_that_is_not_in_the_source.py [book2|book1]

Chỉ đọc. Kho giọng nam của cuốn 2 đã cấp hết (14/14), nên mỗi cái tên được cast là một chỗ trong
kho. Một cái tên **mô hình bịa ra** (không có trong văn bản nguồn) mà lại giữ một giọng là một chỗ
mất không.

Ca thật: cuốn 1 có `SAMAELE` (2 chương) được ghim `thai_son_f093`, trong khi chuỗi `Samaele` xuất
hiện **0 lần** trong toàn bộ nguồn 478 chương — `Samael` thì 1.375 lần. Tức một chữ `e` thừa trong
một lần khai của mô hình đã lấy đi một giọng và tách nhân vật chính thành hai người.

Nhãn mô tả (`NGƯỜI TRẢ LỜI`, `NGƯỜI HỌC VIỆC`, `TỬ TƯỚC`) cố ý không có trong nguồn - chúng là vai
chứ không phải tên. Nên chỉ xét tên **một từ, chữ La-tinh**, đúng lớp mà `SAMAELE` thuộc về.

## Kết quả (09:45 ngày 2026-09-16)

    cuon 2  267 ten, 154 ten mot-tu La-tinh -> 6 ten khong co trong nguon (ngoai NARRATOR)
              NATHANAS   3 nhac, 21 project, GIU doan_trang_f087
              NATHASA    1 nhac, 21 project, GIU doan_trang_f115
              JOELENS, NATHANIEL, MUSICIANS, ANHEID          khong giu giong nao

    cuon 1  263 ten, 71 ten mot-tu La-tinh -> 3 ten khong co trong nguon
              SELNE     32 nhac,  8 project, GIU doan_trang_f115
              SAMAELE    3 nhac, 12 project, GIU thanh_binh_f097
              REVISIA   12 nhac, 16 project, khong giu giong nao

`NATHANAS` va `NATHASA` deu la NATASHA bi go sai, va **moi cai giu mot giong nu da ghim**. Chung
ton tai qua **21 project** vi `port_casting` mang pin di theo danh tinh - mot lan go sai cua mo
hinh thanh mot cho mat khong, mai mai.

Kho giong nam cua cuon 2 da cap het (14/14) va nu dung 15/27, nen bon cho ay khong phai chuyen
nho. Xem docs/OPTIMISATION_QUEUE.md, muc "mot cai ten khong co trong nguon thi khong phai ten".
"""
from __future__ import annotations

import glob
import re
import sqlite3
import sys
from pathlib import Path

BOOK = sys.argv[1] if len(sys.argv) > 1 else "book2"
if BOOK == "book2":
    VERSIONS = Path("D:/Novels/Audiobooks/book2/_versions")
    SOURCE = Path("D:/Novels/Ebook Reader/Text_Tmp")
else:
    VERSIONS = Path("D:/Novels/Audiobooks/_versions")
    SOURCE = Path("D:/Novels/Ebook Reader/Text")

LATIN_ONE_WORD = re.compile(r"^[A-Za-z][A-Za-z'-]{2,}$")


def say(line: str = "") -> None:
    try:
        print(line, flush=True)
    except UnicodeEncodeError:
        print(line.encode("ascii", "backslashreplace").decode("ascii"), flush=True)


def main() -> int:
    source_text = "\n".join(
        p.read_text(encoding="utf-8", errors="replace") for p in sorted(SOURCE.glob("*.txt"))
    ).casefold()

    # Mọi nhân vật của mọi project, kèm việc nó có pin ở đâu không.
    seen: dict[str, dict] = {}
    for database in sorted(glob.glob(str(VERSIONS / "*" / "*" / "project.sqlite3"))):
        path = Path(database)
        connection = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
        connection.row_factory = sqlite3.Row
        try:
            rows = connection.execute(
                "SELECT canonical_name, locked_voice_key, mention_count FROM characters"
            ).fetchall()
        except sqlite3.Error:
            connection.close()
            continue
        connection.close()
        for row in rows:
            name = str(row["canonical_name"]).strip()
            entry = seen.setdefault(name, {"pin": "", "mentions": 0, "projects": 0})
            entry["projects"] += 1
            entry["mentions"] = max(entry["mentions"], int(row["mention_count"] or 0))
            if row["locked_voice_key"]:
                entry["pin"] = str(row["locked_voice_key"])

    missing = []
    for name, entry in seen.items():
        if not LATIN_ONE_WORD.match(name):
            continue
        if re.search(rf"(?<!\w){re.escape(name.casefold())}(?!\w)", source_text):
            continue
        missing.append((entry["mentions"], name, entry))

    say(f"{BOOK}: {len(seen)} tên nhân vật trong mọi project; "
        f"{sum(1 for n in seen if LATIN_ONE_WORD.match(n))} tên một-từ chữ La-tinh")
    say("")
    if not missing:
        say("Không tên một-từ nào vắng mặt trong nguồn.")
        return 0
    say(f"{len(missing)} tên KHÔNG có trong nguồn:")
    say(f"{'ten':<20}{'nhac':>6}{'project':>9}   pin")
    for mentions, name, entry in sorted(missing, reverse=True):
        say(f"{name:<20}{mentions:>6}{entry['projects']:>9}   {entry['pin'].replace('preset_', '') or '(khong)'}")
    say("")
    pinned = [m for m in missing if m[2]["pin"]]
    say(f"Trong đó ĐANG GIỮ một giọng: {len(pinned)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
