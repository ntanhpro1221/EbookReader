"""Bao nhiêu người mang hai giọng qua cả sách **vì** giọng của họ đang bị người khác tranh?

    python scripts/measure_who_contends_for_a_voice.py

Chỉ đọc: đọc cuốn sách đã ghép qua đúng hai module đang chạy thật (`one_person_one_voice` cho
"ai mang nhiều giọng" và `pin_the_book_cast` cho "ai tranh giọng của ai"), không tự dựng lại phép
đếm nào.

## Câu hỏi

Kho giọng của cuốn 2 đã cấp hết (nam 14/14), nên **mọi** pin mới đều dùng chung một giọng với
người đã ghim. `pin_the_book_cast` cho phép đúng khi hai người **chưa từng cùng chương** — đúng
luật holder của bộ cấp giọng. Nhưng `port_casting` thì quyết quyền sở hữu theo **lô nguồn**: ai đã
NÓI ở đó thắng ai đang GHIM. Hai luật ấy đánh nhau, và cái giá đã đo được: chương 090 lên sách với
NATASHA (42 chương) ở giọng thiểu số vì CHELY nói trong lô 4 còn bà ấy im (xem
`scripts/measure_did_the_recast_help.py`).

Script này trả lời: lớp ấy **to bằng nào** — bao nhiêu trong số những người đang mang hơn một
giọng qua cả sách là người có giọng đang bị tranh, và ai tranh của ai.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

try:
    from scripts.book_paths import BOOK, VERSIONS, describe
    from scripts.one_person_one_voice import shipped_genders, shipped_voices, split_voices
    from scripts.pin_the_book_cast import fold_names, majority_voices, shipped_rows
except ImportError:  # chạy trực tiếp
    from book_paths import BOOK, VERSIONS, describe
    from one_person_one_voice import shipped_genders, shipped_voices, split_voices
    from pin_the_book_cast import fold_names, majority_voices, shipped_rows


def say(line: str = "") -> None:
    try:
        print(line, flush=True)
    except UnicodeEncodeError:
        print(line.encode("ascii", "backslashreplace").decode("ascii"), flush=True)


def main() -> int:
    say(describe())
    say("")

    rows = fold_names(shipped_rows(book=BOOK, versions=VERSIONS))
    majority = majority_voices(rows)           # {tên: (giọng, số chương giọng ấy, tổng chương)}
    chapters_of: dict[str, set[str]] = {}
    for row in rows:
        chapters_of.setdefault(str(row["name"]), set()).add(str(row["chapter"]))

    # Ai tranh giọng nào: theo giọng ĐA SỐ của từng người, vì đó chính là thứ `pin_the_book_cast`
    # đem đi ghim và thứ `port_casting` có thể trao cho người khác.
    holders_of: dict[str, list[str]] = {}
    for name, (voice, _here, _total) in majority.items():
        holders_of.setdefault(voice, []).append(name)

    # Ai đang mang hơn một giọng qua cả sách (cùng phép đo của báo cáo hằng ngày).
    _inside, across = split_voices(shipped_voices(book=BOOK, versions=VERSIONS), shipped_genders())

    say(f"{len(majority)} người có giọng đa số; {len(across)} người mang hơn một giọng qua cả sách")
    say("")
    contended_split = uncontended_split = 0
    lines: list[tuple[int, str]] = []
    for name in across:
        voice = majority.get(name, (None, 0, 0))[0]
        rivals = [other for other in holders_of.get(voice, []) if other != name]
        total = len(chapters_of.get(name, ()))
        if not rivals:
            uncontended_split += 1
            continue
        contended_split += 1
        detail = []
        for other in sorted(rivals, key=lambda n: -len(chapters_of.get(n, ()))):
            shared = chapters_of.get(name, set()) & chapters_of.get(other, set())
            detail.append(
                f"{other} ({len(chapters_of.get(other, ()))} chương"
                + (f", CÙNG chương {sorted(shared)[:3]}" if shared else ", chưa từng cùng chương")
                + ")"
            )
        lines.append((
            total,
            f"   {name:<16} {total:>3} chương, giọng đa số {str(voice).replace('preset_', ''):<26}"
            f" bị tranh bởi: {'; '.join(detail)}",
        ))
    for _total, line in sorted(lines, reverse=True):
        say(line)
    say("")
    say(f"mang hai giọng VÀ bị tranh giọng : {contended_split}")
    say(f"mang hai giọng mà KHÔNG bị tranh : {uncontended_split}")
    say("")
    say("Người bị tranh mà chưa từng cùng chương là người mà CẢ HAI đều ghim được: luật holder")
    say("cho phép, và `port_casting` là chỗ duy nhất còn chọn một người rồi bỏ người kia.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
