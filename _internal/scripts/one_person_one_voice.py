"""Một người có được đọc bằng MỘT giọng không — trên cả cuốn sách, không phải trong một lô.

    python scripts/one_person_one_voice.py                    # cuốn sách đã ghép (manifest.json)
    python scripts/one_person_one_voice.py <project>          # một project
    python scripts/one_person_one_voice.py --chapters         # chỉ in danh sách chương cần đúc lại
    python scripts/one_person_one_voice.py --across [--min-chapters 5]
                                                              # in `B:NNN` cho boundary.sh --recast:
                                                              # chương mang giọng THIỂU SỐ của một người

`voice_pool_pressure.py` hỏi **hai người có dùng chung một giọng không**. Câu ngược lại — *một
người có mang hai giọng không* — chưa ai hỏi, và nó là câu đắt hơn: hai người giống giọng thì
người nghe lẫn hai nhân vật, còn một người đổi giọng giữa chương thì người nghe mất luôn nhân
vật ấy.

Đo lần đầu 2026-09-11 trên cuốn sách 90 chương đã ghép: **21 chương có một người hai giọng ngay
trong cùng chương**, 202 câu thoại. Hai cái tên gánh gần hết:

    NGƯỜI TRẢ LỜI   19 chương   doan_trang_f100 (69 chương cả sách) vs ngoc_linh_f108 (26)
    THỦ LÃNH         7 chương   thanh_binh_f100_p-07 (55) vs thanh_binh_f090_p-04 (20)

Nguyên nhân là lớp **tách danh tính do rơi dấu**: `THU LÃNH` và `THỦ LÃNH` là hai dòng
`characters` khác nhau nên mỗi bản được đúc một giọng riêng, hoàn toàn hợp lệ dưới mọi cổng —
`verify_casting` kiểm "một người nói ra một giọng", và dưới mắt nó đây là **hai** người.
`patch_dropped_marks_are_the_same_name` chặn lớp ấy từ lô 4 trở đi; những chương đã đúc rồi thì
vẫn mang hai giọng cho tới khi được đọc lại.

Vì sao phải so **sau khi gộp tên**: nếu không gộp thì công cụ này thấy hai cái tên, mỗi tên một
giọng, và báo "không có gì". Đúng cái mù đã để 202 câu đi vào sách.

Mặt còn lại của cùng lớp lỗi, đo 23:30 ngày 2026-09-11 trên sách 116 chương: **một người một
giọng trong mỗi chương, nhưng giọng khác nhau giữa các chương** — NGƯỜI TRẢ LỜI doan_trang_f100 ở
90 chương và ngoc_linh_f108 ở 6, THỦ LÃNH f100 ở 83 và f090 ở 7; giọng thứ hai luôn nằm ở dòng
viết rơi dấu trong project đúc trước bản vá gộp tên. `--across` in ra đúng những chương ấy dưới
dạng `B:NNN` để `boundary.sh --recast` đúc lại; luật là phía **ít chương hơn** đúc lại theo phía
nhiều hơn, và chỉ với người có đủ chương (`--min-chapters`) để "đa số" có nghĩa.
"""
from __future__ import annotations

import argparse
import collections
import json
import re
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.name_marks import fold_dropped_marks  # noqa: E402

try:
    from scripts.book_paths import BOOK, VERSIONS  # noqa: E402
except ImportError:  # chạy trực tiếp: python scripts/x.py
    from book_paths import BOOK, VERSIONS  # noqa: E402

VOICES_SQL = """
SELECT ch.title AS chapter, c.canonical_name AS name, v.voice_key AS voice_key,
       count(*) AS lines
FROM segments s
  JOIN characters c ON c.id = s.canonical_character_id
  JOIN voice_profiles v ON v.id = s.voice_profile_id
  JOIN chapters ch ON ch.id = s.chapter_id
WHERE s.kind = 'dialogue' AND v.voice_key <> 'narrator'
  AND c.canonical_name NOT LIKE 'NPC/_%' ESCAPE '/'
  AND upper(c.canonical_name) NOT LIKE 'ANONYMOUS%'
GROUP BY ch.id, c.id, v.id
"""


def _say(line: str) -> None:
    try:
        print(line)
    except (UnicodeEncodeError, OSError, ValueError):
        sys.stdout.buffer.write(line.encode("utf-8", "replace") + b"\n")


def read_voices(project: Path) -> list[tuple[str, str, str, int]]:
    """[(chương, tên, voice_key, số câu)] của một project. Rỗng nếu không đọc được."""
    try:
        conn = sqlite3.connect(f"file:{project / 'project.sqlite3'}?mode=ro", uri=True)
    except sqlite3.Error:
        return []
    try:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(VOICES_SQL).fetchall()
    except sqlite3.Error:
        return []
    finally:
        conn.close()
    return [
        (str(r["chapter"]), str(r["name"]), str(r["voice_key"]), int(r["lines"])) for r in rows
    ]


def shipped_voices(book: Path = BOOK, versions: Path = VERSIONS) -> list[tuple[str, str, str, int]]:
    """Giọng của những chương **đã lên sách**, theo `manifest.json`.

    Đọc theo manifest chứ không đọc mọi project: một chương có thể có bốn bản, và ba trong bốn
    không nằm trong sách. Hỏi "cuốn sách có nhất quán không" bằng cả bốn bản là hỏi sai câu.
    """
    try:
        payload = json.loads((book / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    entries = payload if isinstance(payload, list) else payload.get("chapters", [])
    # Đúng PROJECT manifest ghi, không phải "mọi project trong thư mục phiên bản". Một thư mục
    # có thể chứa hai bản của cùng chương - `lo01r_007` bị dừng dở và `lo01r_007b` lên sách - và
    # bản đầu của hàm này đọc cả hai, cộng 12 câu `f115` của bản bỏ đi vào chương đã sạch, rồi
    # báo "một người hai giọng" cho đúng hai chương vừa được đúc lại để xoá lỗi ấy (đo 17:41
    # ngày 2026-09-11). Manifest có cột `project` từ khi `assemble_book` ghi gốc gác; dùng nó.
    wanted: dict[str, tuple[str, str]] = {}
    for item in entries:
        title = str(item.get("title") or "")
        if title:
            wanted[title] = (str(item.get("version") or ""), str(item.get("project") or ""))
    found: list[tuple[str, str, str, int]] = []
    for version, project_name in sorted(set(wanted.values())):
        folder = versions / version
        if not folder.is_dir():
            continue
        candidates = (
            [folder / project_name] if project_name and (folder / project_name).is_dir()
            else sorted(p for p in folder.iterdir() if (p / "project.sqlite3").is_file())
        )
        for project in candidates:
            if not (project / "project.sqlite3").is_file():
                continue
            for chapter, name, voice_key, lines in read_voices(project):
                if wanted.get(chapter) == (version, project_name if project_name else wanted[chapter][1]):
                    found.append((chapter, name, voice_key, lines))
    return found


def split_voices(
    rows: list[tuple[str, str, str, int]],
) -> tuple[dict[str, dict[str, dict[str, int]]], dict[str, dict[str, set[str]]]]:
    """(một người hai giọng **trong cùng chương**, một người hai giọng **qua các chương**).

    Gộp cách viết rơi dấu trước khi so - xem docstring của module.
    """
    names = sorted({name for _chapter, name, _voice, _lines in rows})
    folded = fold_dropped_marks(names)

    per_chapter: dict[str, dict[str, dict[str, int]]] = collections.defaultdict(
        lambda: collections.defaultdict(lambda: collections.defaultdict(int))
    )
    per_name: dict[str, dict[str, set[str]]] = collections.defaultdict(
        lambda: collections.defaultdict(set)
    )
    for chapter, name, voice_key, lines in rows:
        target = folded.get(name, name)
        per_chapter[chapter][target][voice_key] += lines
        per_name[target][voice_key].add(chapter)

    inside = {
        chapter: {name: dict(voices) for name, voices in names_.items() if len(voices) > 1}
        for chapter, names_ in per_chapter.items()
    }
    inside = {chapter: hits for chapter, hits in inside.items() if hits}
    across = {
        name: {voice: set(chapters) for voice, chapters in voices.items()}
        for name, voices in per_name.items()
        if len(voices) > 1
    }
    return inside, across


def chapter_batches(book: Path = BOOK) -> dict[str, int]:
    """{chương: số lô} theo `manifest.json` - lô đọc từ tên phiên bản (`v0.2.0-lo03r` → 3)."""
    try:
        payload = json.loads((book / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    entries = payload if isinstance(payload, list) else payload.get("chapters", [])
    batches: dict[str, int] = {}
    for item in entries:
        match = re.search(r"lo(\d+)", str(item.get("version") or ""))
        title = str(item.get("title") or "")
        if match and title:
            batches[title] = int(match.group(1))
    return batches


def minority_chapters(
    across: dict[str, dict[str, set[str]]],
    *,
    min_chapters: int,
) -> dict[str, tuple[str, dict[str, set[str]]]]:
    """{tên: (giọng đa số, {giọng thiểu số: {chương}})} cho người có ít nhất `min_chapters` chương.

    Đa số = giọng có nhiều chương nhất; hoà thì lấy giọng đứng trước theo bảng chữ, để hai lần
    chạy cho cùng một câu trả lời. Người dưới `min_chapters` bỏ qua: với hai chương thì "đa số"
    là một đồng xu, và đúc lại một chương vì đồng xu là phí GPU.
    """
    result: dict[str, tuple[str, dict[str, set[str]]]] = {}
    for name, voices in across.items():
        total = sum(len(chapters) for chapters in voices.values())
        if total < min_chapters:
            continue
        majority = sorted(voices.items(), key=lambda kv: (-len(kv[1]), kv[0]))[0][0]
        minority = {voice: set(chapters) for voice, chapters in voices.items() if voice != majority}
        if minority:
            result[name] = (majority, minority)
    return result


def recast_arguments(
    minority: dict[str, tuple[str, dict[str, set[str]]]],
    batches: dict[str, int],
) -> list[str]:
    """`B:NNN` cho từng chương thiểu số, không trùng, theo thứ tự chương; chương không rõ lô bị bỏ."""
    seen: set[str] = set()
    for _majority, voices in minority.values():
        for chapters in voices.values():
            seen |= set(chapters)
    return [f"{batches[chapter]}:{chapter}" for chapter in sorted(seen) if chapter in batches]


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("project", nargs="?", type=Path, default=None)
    parser.add_argument(
        "--chapters",
        action="store_true",
        help="chỉ in số chương cần đúc lại, cách nhau bằng dấu cách",
    )
    parser.add_argument(
        "--across",
        action="store_true",
        help="in `B:NNN` cho boundary.sh --recast: chương mang giọng thiểu số của một người",
    )
    parser.add_argument(
        "--min-chapters",
        type=int,
        default=5,
        help="chỉ xét người có ít nhất bấy nhiêu chương (mặc định 5)",
    )
    args = parser.parse_args(argv)

    if args.project is not None:
        rows = read_voices(args.project)
        where = args.project.name
    else:
        rows = shipped_voices()
        where = "cuốn sách đã ghép"
    if not rows:
        _say(f"không đọc được giọng nào từ {where}")
        return 2

    inside, across = split_voices(rows)
    if args.chapters:
        _say(" ".join(sorted(inside)))
        return 0
    if args.across:
        minority = minority_chapters(across, min_chapters=args.min_chapters)
        _say(" ".join(recast_arguments(minority, chapter_batches())))
        return 0

    chapters = {chapter for chapter, _name, _voice, _lines in rows}
    _say(f"{where}: {len(chapters)} chương, {len({n for _c, n, _v, _l in rows})} cách viết tên.")
    _say("")
    if not inside:
        _say("Không chương nào có một người hai giọng trong cùng chương.")
    else:
        lines_hit = sum(sum(v.values()) for hits in inside.values() for v in hits.values())
        _say(
            f"{len(inside)} chương có MỘT NGƯỜI HAI GIỌNG trong cùng chương"
            f" ({lines_hit} câu thoại) - người nghe mất nhân vật, không chỉ lẫn nhân vật:"
        )
        for chapter, hits in sorted(inside.items()):
            for name, voices in sorted(hits.items()):
                detail = "  ".join(
                    f"{voice.replace('preset_', '')}={lines}câu"
                    for voice, lines in sorted(voices.items(), key=lambda kv: -kv[1])
                )
                _say(f"  chương {chapter}  {name:22s} {detail}")
        _say("")
        _say("Đúc lại chúng: bash scripts/launch_repair.sh <lô> --chapters $(python"
             " scripts/one_person_one_voice.py --chapters)")
    if across:
        _say("")
        _say(f"{len(across)} người mang nhiều hơn một giọng qua cả cuốn sách:")
        for name, voices in sorted(across.items(), key=lambda kv: -sum(len(c) for c in kv[1].values())):
            total = sum(len(c) for c in voices.values())
            _say(f"  {name:22s} {len(voices)} giọng / {total} chương")
            for voice, in_chapters in sorted(voices.items(), key=lambda kv: -len(kv[1])):
                shown = ", ".join(sorted(in_chapters)[:6])
                more = " ..." if len(in_chapters) > 6 else ""
                _say(f"      {voice:34s} {len(in_chapters):3d} chương: {shown}{more}")
        minority = minority_chapters(across, min_chapters=args.min_chapters)
        arguments = recast_arguments(minority, chapter_batches())
        if arguments:
            _say("")
            _say(
                f"Đúc lại phía thiểu số của người có ≥ {args.min_chapters} chương ở ranh giới: "
                f"bash scripts/boundary.sh <lô> --recast auto {' '.join(arguments)}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
