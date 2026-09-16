"""Một người, nhiều NHÃN: tên gõ sai và tên thiếu họ — mỗi nhãn giữ một giọng riêng.

    python scripts/measure_one_person_many_labels.py [book2|book1]

Chỉ đọc. `one_person_one_voice.py` đo "một **tên** hai giọng". Phép đo này đo lớp nó không thấy
được: **một NGƯỜI nhiều tên**, vì mỗi tên là một dòng `characters` riêng với pin riêng.

## Ca thật (cuốn 1, đo 09:50 ngày 2026-09-16)

    ten              nhac  project  pin
    SELENE             80       61  ngoc_linh_f097
    SELENE VALKRYN      2       38  doan_trang_f115
    SELNE              32        8  doan_trang_f115
    SELNE VALKRYN       3        8  doan_trang_f104

Một nhân vật — `Selene` xuất hiện **198 lần** trong nguồn, `Selne` **0 lần** — tồn tại thành **bốn
danh tính giữ ba giọng khác nhau**. Người nghe nghe cùng một người bằng ba giọng tuỳ chương, và
`one_person_one_voice` im lặng vì bốn cái tên là bốn cái tên.

Hai lớp khác nhau, cần hai cách chữa khác nhau:

- **gõ sai**: `SELNE` / `SAMAELE` / `NATHASA` — chuỗi ấy **không hề có trong nguồn**, nên nó không
  thể là tên. Xem `scripts/measure_a_name_that_is_not_in_the_source.py`.
- **thiếu họ**: `SELENE` so với `SELENE VALKRYN` — cả hai đều có trong nguồn và đều đúng; chúng là
  cùng một người được gọi bằng tên và bằng tên đầy đủ. `patch_stray_surname_is_the_same_name` đã
  gộp **họ đứng một mình** về tên đầy đủ; nó không gộp **tên đứng một mình**, và đó là ca này.

Phép đo chỉ **nêu tên** các nhóm; nó không gộp gì. Hai người thật có thể trùng tên riêng (`JOHN`
và `JOHN SMITH` có thể là hai người), nên mỗi nhóm phải đọc bằng mắt trước khi ai đó viết luật.
"""
from __future__ import annotations

import glob
import re
import sqlite3
import sys
import unicodedata
from pathlib import Path

BOOK = sys.argv[1] if len(sys.argv) > 1 else "book2"
if BOOK == "book2":
    VERSIONS = Path("D:/Novels/Audiobooks/book2/_versions")
    SOURCE = Path("D:/Novels/Ebook Reader/Text_Tmp")
else:
    VERSIONS = Path("D:/Novels/Audiobooks/_versions")
    SOURCE = Path("D:/Novels/Ebook Reader/Text")

# Chỉ tên chữ La-tinh: nhãn mô tả tiếng Việt (`NGƯỜI TRẢ LỜI`, `TỬ TƯỚC CARENDIA`) là vai, và một
# vai trùng chữ với một vai khác không có nghĩa gì.
LATIN_NAME = re.compile(r"^[A-Za-z][A-Za-z'.-]*(?: [A-Za-z][A-Za-z'.-]*)*$")
RESERVED = {"NARRATOR", "UNKNOWN"}


def fold(text: str) -> str:
    """Bỏ dấu + đ→d, cùng một luật với `analysis._name_candidate_key`.

    Phải bỏ dấu **cả hai bên** khi hỏi "chuỗi này có trong nguồn không". Bản trước so nguyên dấu
    và vì thế gắn cờ `NGUOI TRA LOI` (160 lần nhắc, có pin) cùng `DAO GAM` là "không có trong
    nguồn" — trong khi nguồn viết `NGƯỜI TRẢ LỜI` và `Dao Găm` đủ dấu. Chúng là **nhãn rơi dấu**,
    một lớp đã có đường chữa riêng (`dropped_marks`, `identity_key`), không phải tên mô hình bịa.
    """
    stripped = "".join(
        ch
        for ch in unicodedata.normalize("NFD", text.casefold())
        if unicodedata.category(ch) != "Mn"
    )
    return unicodedata.normalize("NFC", stripped).replace("đ", "d")


def say(line: str = "") -> None:
    try:
        print(line, flush=True)
    except UnicodeEncodeError:
        print(line.encode("ascii", "backslashreplace").decode("ascii"), flush=True)


def characters() -> dict[str, dict]:
    out: dict[str, dict] = {}
    for database in sorted(glob.glob(str(VERSIONS / "*" / "*" / "project.sqlite3"))):
        connection = sqlite3.connect(f"file:{Path(database).as_posix()}?mode=ro", uri=True)
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
            if name.upper() in RESERVED or not LATIN_NAME.match(name):
                continue
            entry = out.setdefault(name, {"pins": set(), "mentions": 0, "projects": 0})
            entry["projects"] += 1
            entry["mentions"] = max(entry["mentions"], int(row["mention_count"] or 0))
            if row["locked_voice_key"]:
                entry["pins"].add(str(row["locked_voice_key"]))
    return out


def main() -> int:
    people = characters()
    source = fold(
        "\n".join(
            p.read_text(encoding="utf-8", errors="replace") for p in sorted(SOURCE.glob("*.txt"))
        )
    )

    def in_source(name: str) -> bool:
        return bool(re.search(rf"(?<!\w){re.escape(fold(name))}(?!\w)", source))

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

    # HAI lớp, báo riêng, vì hai lớp cần hai cách chữa và có hai mức chắc chắn khác nhau.
    #
    # Bản đầu của phép đo này gom mọi nhãn cách nhau <= 2 phép sửa, và nó gom sai ngay: `KANG`
    # (81 nhắc) với `KAIN REICHARDT` (8) - hai người khác nhau, cách nhau một ký tự; `LILY` với
    # `LIORA` với `TIS`. Cả ba đều CÓ trong nguồn, nên không có gì cho phép gộp chúng. Giữ đúng
    # thứ bằng chứng cho phép: **vắng mặt trong nguồn** là nhị phân, còn "gần giống" thì không.
    in_source_names = {name for name in people if in_source(name)}
    say("### LỚP 1 - CHẮC CHẮN: nhãn KHÔNG có trong nguồn (không thể là tên)")
    say("")
    class_one = 0
    for name in sorted(people, key=lambda n: -people[n]["mentions"]):
        if name in in_source_names:
            continue
        entry = people[name]
        near = [
            other
            for other in in_source_names
            if distance(name.casefold(), other.casefold()) not in (None, 0)
        ]
        near.sort(key=lambda n: -people[n]["mentions"])
        class_one += 1
        say(
            f"  {name:<22}{entry['mentions']:>5} nhắc {entry['projects']:>4} project"
            f"  pin: {sorted(x.replace('preset_', '') for x in entry['pins']) or '-'}"
        )
        if near:
            best = near[0]
            say(f"      gần nhất CÓ trong nguồn: {best} ({people[best]['mentions']} nhắc,"
                f" pin {sorted(x.replace('preset_', '') for x in people[best]['pins']) or '-'})")
        else:
            say("      không có nhãn nào trong nguồn cách nó <= 2 phép sửa")
    say("")
    say("### LỚP 2 - CẦN ĐỌC: tên riêng so với tên đầy đủ, CẢ HAI đều có trong nguồn")
    say("")
    class_two = 0
    for short in sorted(in_source_names, key=lambda n: -people[n]["mentions"]):
        if " " in short:
            continue
        longer = [
            other
            for other in in_source_names
            if other != short and other.split()[0].upper() == short.upper() and " " in other
        ]
        if not longer:
            continue
        pins = {pin for name in [short, *longer] for pin in people[name]["pins"]}
        if len(pins) < 2:
            continue
        class_two += 1
        say(f"  {short} + {', '.join(longer)}  ->  {len(pins)} giọng đã ghim")
        for name in [short, *longer]:
            entry = people[name]
            say(
                f"      {name:<22}{entry['mentions']:>5} nhắc"
                f"  pin: {sorted(x.replace('preset_', '') for x in entry['pins']) or '-'}"
            )
    say("")
    say(f"lớp 1 (chắc chắn): {class_one} nhãn | lớp 2 (cần đọc): {class_two} nhóm")
    say("")
    say("Lớp 1 gộp được bằng bằng chứng: chuỗi ấy không có trong nguồn nên không thể là tên.")
    say("Lớp 2 thì PHẢI đọc: `JOHN` và `JOHN SMITH` có thể là hai người, và phép đo không gộp gì.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
