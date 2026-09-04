"""Do parenthetical English glosses break segments, and if so which ones?

Three of alpha.32's blocked segments read a Vietnamese phrase followed by its English
source in brackets, and the voice says both:

    1.000 Đơn vị Tinh hoa Linh hồn (Spirit Essence Units)  ->  heard "S&P ZIT ESEN UNIT"
    Hắn là Hoàng Tử Quỷ Thứ Mười (Tenth Demon Prince)      ->  heard "tên Demon Prince"

Two remedies suggest themselves and both are wrong, which is why this script exists rather
than a patch. Measured over the whole book it prints the base rate, the rate inside the
class, and the breakdown by gloss length, so the next person to have either idea can see
the numbers before acting on them.

    python scripts/english_gloss_risk.py <project_root>

Read-only: opens the project database read-only and writes nothing.
"""
from __future__ import annotations

import re
import sqlite3
import sys
from pathlib import Path

VIETNAMESE_DIACRITIC = re.compile(
    r"[àáảãạăằắẳẵặâầấẩẫậèéẻẽẹêềếểễệìíỉĩịòóỏõọôồốổỗộơờớởỡợùúúủũụưừứửữựỳýỷỹỵđ]", re.I
)
PARENTHETICAL = re.compile(r"\(([^()]{2,60})\)")
ENGLISH_WORD = re.compile(r"[A-Za-z][A-Za-z'’.]*")


def gloss_words(text: str) -> list[str] | None:
    """The English words inside the first bracket that carries no Vietnamese diacritic."""
    for match in PARENTHETICAL.finditer(text or ""):
        inner = match.group(1)
        if re.search(r"[A-Za-z]", inner) and not VIETNAMESE_DIACRITIC.search(inner):
            words = ENGLISH_WORD.findall(inner)
            if words:
                return words
    return None


def _is_blocked(row: sqlite3.Row) -> bool:
    return str(row["status"]) == "failed" or "ANCHOR_MISMATCH" in str(row["warning_code"] or "")


def main(project_root: str) -> int:
    database = Path(project_root) / "project.sqlite3"
    if not database.is_file():
        print(f"không tìm thấy project: {database}")
        return 2
    connection = sqlite3.connect(f"file:{database}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    rows = connection.execute(
        "SELECT stable_id, status, warning_code, text FROM segments"
    ).fetchall()
    connection.close()
    if not rows:
        print("project chưa có segment nào")
        return 1

    by_length: dict[int, list[bool]] = {}
    in_class = 0
    for row in rows:
        words = gloss_words(str(row["text"] or ""))
        if not words:
            continue
        in_class += 1
        by_length.setdefault(len(words), []).append(_is_blocked(row))

    blocked_overall = sum(1 for row in rows if _is_blocked(row))
    blocked_in_class = sum(sum(values) for values in by_length.values())
    if not in_class:
        print("không có chú thích tiếng Anh nào trong ngoặc")
        return 0

    base_rate = blocked_overall / len(rows)
    class_rate = blocked_in_class / in_class
    print(f"{len(rows)} segment, {in_class} có chú thích tiếng Anh trong ngoặc "
          f"({in_class / len(rows):.1%})")
    print(f"  hỏng trong lớp này : {blocked_in_class}/{in_class} = {class_rate:.1%}")
    print(f"  hỏng toàn sách     : {blocked_overall}/{len(rows)} = {base_rate:.1%}")
    if base_rate:
        print(f"  rủi ro so với nền  : {class_rate / base_rate:.1f} lần")
    if blocked_overall:
        print(f"  chiếm {blocked_in_class}/{blocked_overall} tổng số chỗ hỏng của sách")

    print()
    print(f"{'số từ':>6}  {'n':>4}  {'hỏng':>5}  tỉ lệ")
    for length in sorted(by_length):
        values = by_length[length]
        print(f"{length:6d}  {len(values):4d}  {sum(values):5d}  {sum(values) / len(values):6.1%}")

    print()
    # Both remedies are refuted by these numbers, and both are tempting enough that the
    # refutation is the point of the script. Guarded so it never claims more than it has.
    if blocked_in_class < 5:
        print(
            f"Chỉ {blocked_in_class} chỗ hỏng trong lớp này - quá ít để phân loại nhỏ hơn. "
            "Đừng đọc bảng theo số từ như một quy luật: nó là nhiễu."
        )
    print(
        "Hai cách sửa dễ nghĩ ra, cả hai đều sai:\n"
        "  1. 'Bỏ chú thích trong ngoặc đi.' Nhưng đây là truyện LitRPG và người đọc thể "
        "loại này biết thuật ngữ tiếng Anh - nghe 'Thẻ Kỹ năng, Skill Card' có thể đúng "
        "là điều họ muốn. Đó là quyết định thẩm mỹ của chủ sách, không phải của máy.\n"
        "  2. 'Chú thích dài mới hỏng.' Bảng trên nói không: loại 4 từ hỏng 0."
    )
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__)
        raise SystemExit(2)
    raise SystemExit(main(sys.argv[1]))
