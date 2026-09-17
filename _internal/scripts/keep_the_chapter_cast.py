"""Đúc lại một chương mà CHỈ đổi người cần đổi: ghim dàn giọng của chính chương ấy trên sách.

    python scripts/keep_the_chapter_cast.py <project>              # in kế hoạch, không ghi
    python scripts/keep_the_chapter_cast.py <project> --apply      # ghim thật (launch_repair gọi)
    python scripts/keep_the_chapter_cast.py --chapters 094 136     # mô phỏng trên sách, chưa cần project

`launch_repair.sh` gọi nó ở chế độ đúc lại, SAU `port_casting` và `pin_the_book_cast`, TRƯỚC `run`.
Nó chỉ đụng tới người **nói trong những chương của project đã có trên sách**; chương chưa lên sách
(lô vá một chương hỏng) thì không có gì để giữ và script đi qua.

## Vì sao

Một lượt đúc lại cấp giọng lại cho **cả chương**, trong khi lý do gọi nó chỉ là **một** người mang
giọng thiểu số. Ai khác trong chương mà không có pin đều đi qua bộ cấp giọng. Nếu giọng đa số của
họ đang bị một pin khác giữ chỗ **trên cả cuốn** (dù người giữ không có mặt ở chương này), họ nhận
một giọng mới. Đo ngày 17-09 bằng `measure_did_the_recast_help.py`:

    ranh gioi 4 (pin chay dung)                 tot 9 | xau 2
    ranh gioi 5 (pin_the_book_cast no truoc     tot 2 | xau 8
                 vong ghim da so)
    lo02r_094, chay thu pin_the_book_cast da sua:
        CHRISTOPHER, LOTT, HERODOTUS, MAG van "khong ghim duoc ... dang giu va co cung chuong"

Luật của dự án cấm **hai người một giọng trong CÙNG chương**, không phải "trên cả cuốn". Với một
chương đã lên sách, ta **biết** ai nói trong chương ấy, nên chỉ cần xét trong chương đó.

## Luật gán (ba nhóm, theo thứ tự ai được giữ chỗ trước)

1. **NEO** - nói ở >= 2 chương và giọng ở chương này ĐÃ là giọng đa số: giữ nguyên.
2. **THIỂU SỐ** - nói ở >= 2 chương mà giọng ở đây khác đa số: về đa số nếu trong chương còn trống,
   không thì giữ giọng cũ. Không bao giờ sang một giọng thứ ba.
3. **MỘT CHƯƠNG** - không có danh tính qua các chương để giữ: **không ghim**. Bộ cấp giọng tự tránh
   giọng của người đã ghim trong cùng chương. Ghim họ là giữ chỗ một giọng trên cả cuốn cho một cái
   tên sẽ không quay lại (cùng lý do `pin_the_book_cast --min-chapters 2`).

Trong mỗi nhóm, người nhiều chương trên sách hơn đi trước, rồi tới người nhiều câu trong chương hơn.

Bản mô phỏng đầu gán thẳng theo hạng, và chương 136 lộ ra cái giá. SIMON (4 chương) lấy lại `f116`,
thế là IM - người đang nói bằng `f116` ngay trong chương ấy - bị đẩy sang giọng mới. Sửa một người
bằng cách làm hỏng một người khác chính là cái lỗi mà script này được viết ra để tránh, nên mới có
thứ tự nhóm.

Người nói trong chương mà **không** được ghim, nếu đang mang một pin cũ trùng giọng vừa gán cho
người khác trong chương, thì bị bỏ pin ấy. Để yên thì `_drop_pins_that_share_a_chapter` của registry
sẽ giữ người **nhiều câu hơn trong lô**, và có thể bỏ đúng người vừa được sửa.

## Kết quả mô phỏng (17-09, sách 219 chương; 8 chương chờ đúc lại)

    --chapters 010 027 094 105 136 137 139 167
    ve da so 15 | giu nguyen 39 | khong ghim 1 (IM, 136 - mot chuong)

    094: EVANS ve thai_son_f097 (23 chuong); CHRISTOPHER, LOTT, HERODOTUS, JULIAN, MEKANZI GIU
         nguyen - dung nam nguoi ma lan duc lai 16-09 day ra khoi giong da so.

"Xấu hơn" chỉ còn có thể đến từ hai chỗ: người một chương (không ai nghe ra), và **phân tích lại đổi
nhãn** - lượt đúc lại chạy lại LLM, nên một người có thể mang nhãn khác và không khớp pin. Chỗ thứ
hai chỉ có một cách biết: đo bằng `measure_did_the_recast_help.py` sau khi chạy.
"""
from __future__ import annotations

import argparse
import collections
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ebook_reader.database import ProjectDB  # noqa: E402
from scripts.pin_the_book_cast import (  # noqa: E402
    majority_voices,
    pinned_character_names,
    project_chapters,
    unpin_character,
    voice_profile,
)
from scripts.voice_matches_the_person import VERSIONS, fold_names, shipped_rows  # noqa: E402

MIN_CHAPTERS = 2
KEEP_MAJORITY = "giu (da la da so)"
TO_MAJORITY = "ve da so"
KEEP_MINORITY = "giu (da so dang co nguoi trong chuong dung)"
ONE_CHAPTER = "mot chuong - de bo cap giong chon"
TIED_ANCHOR = "KHONG GHIM - hai nguoi neo cung giong trong chuong"


def _say(line: str = "") -> None:
    try:
        print(line, flush=True)
    except UnicodeEncodeError:
        print(line.encode("ascii", "backslashreplace").decode("ascii"), flush=True)


def is_person(name: str) -> bool:
    """NPC theo chương, người vô danh, người kể và UNKNOWN không có danh tính qua chương để giữ."""
    upper = name.upper()
    return not (
        name.startswith("NPC_LOCAL::")
        or upper.startswith("ANONYMOUS")
        or upper in {"NARRATOR", "UNKNOWN"}
    )


def plan_chapter(
    chapter: str,
    rows: list[dict],
    majority: dict[str, tuple[str, int, int]],
    min_chapters: int = MIN_CHAPTERS,
) -> list[tuple[str, str, str, str]]:
    """[(tên, giọng trên sách, giọng sẽ ghim hoặc "", lý do)] cho mọi người nói trong chương."""
    here: dict[str, dict] = {}
    for row in rows:
        if str(row["chapter"]) != chapter or not is_person(str(row["name"])):
            continue
        slot = here.setdefault(str(row["name"]), {"voices": collections.Counter(), "lines": 0})
        slot["voices"][str(row["voice"])] += int(row["lines"])
        slot["lines"] += int(row["lines"])

    def shipped_of(name: str) -> str:
        return here[name]["voices"].most_common(1)[0][0]

    def group(name: str) -> int:
        wanted, _count, total = majority.get(name, ("", 0, 0))
        if not wanted or total < min_chapters:
            return 3
        return 1 if wanted == shipped_of(name) else 2

    def rank(name: str) -> tuple[int, int, int, str]:
        return (group(name), -majority.get(name, ("", 0, 0))[2], -here[name]["lines"], name)

    taken: set[str] = set()
    plan: list[tuple[str, str, str, str]] = []
    for name in sorted(here, key=rank):
        shipped = shipped_of(name)
        wanted = majority.get(name, ("", 0, 0))[0]
        kind = group(name)
        if kind == 3:
            plan.append((name, shipped, "", ONE_CHAPTER))
        elif kind == 1 and shipped not in taken:
            taken.add(shipped)
            plan.append((name, shipped, shipped, KEEP_MAJORITY))
        elif kind == 1:
            plan.append((name, shipped, "", TIED_ANCHOR))
        elif wanted not in taken:
            taken.add(wanted)
            plan.append((name, shipped, wanted, TO_MAJORITY))
        elif shipped not in taken:
            taken.add(shipped)
            plan.append((name, shipped, shipped, KEEP_MINORITY))
        else:
            plan.append((name, shipped, "", "KHONG GHIM - ca hai giong da co nguoi trong chuong"))
    return plan


def _book() -> tuple[list[dict], dict[str, tuple[str, int, int]]]:
    rows = fold_names(shipped_rows())
    return rows, majority_voices(rows)


def _print_plan(chapter: str, plan: list[tuple[str, str, str, str]]) -> tuple[int, int, int]:
    moved = sum(1 for p in plan if p[3] == TO_MAJORITY)
    loose = sum(1 for p in plan if not p[2])
    kept = len(plan) - moved - loose
    _say(f"=== chuong {chapter}: {len(plan)} nguoi | ve da so {moved} | giu {kept} | khong ghim {loose}")
    for name, shipped, target, why in plan:
        if why == KEEP_MAJORITY:
            continue
        target_text = target.replace("preset_", "") or "-"
        _say(f"    {name:18s} {shipped.replace('preset_', ''):24s} -> {target_text:24s} {why}")
    return moved, kept, loose


def keep(target: Path, *, apply: bool, versions: Path = VERSIONS) -> int:
    """Ghim dàn giọng của các chương đã lên sách trong project. Trả về số pin đã (sẽ) ghi."""
    rows, majority = _book()
    on_book = {str(r["chapter"]) for r in rows}
    chapters = sorted(project_chapters(target) & on_book)
    if not chapters:
        _say(f"{target.name}: không chương nào đã lên sách - không có dàn giọng để giữ.")
        return 0

    wanted: dict[str, str] = {}
    conflicted: set[str] = set()
    taken_by: dict[str, set[str]] = collections.defaultdict(set)
    speakers: set[str] = set()
    for chapter in chapters:
        plan = plan_chapter(chapter, rows, majority)
        _print_plan(chapter, plan)
        for name, _shipped, voice, _why in plan:
            speakers.add(name)
            if not voice:
                continue
            taken_by[voice].add(name)
            if wanted.get(name, voice) != voice:
                conflicted.add(name)
            wanted.setdefault(name, voice)
    for name in sorted(conflicted):
        _say(f"  {name}: hai chương trong project muốn hai giọng khác nhau - không ghim, để bộ cấp giọng chọn")
        wanted.pop(name, None)

    database = ProjectDB(target / "project.sqlite3")
    written = 0
    for name, voice in sorted(wanted.items()):
        profile = voice_profile(voice, versions)
        if profile is None:
            _say(f"  BỎ QUA {name}: không tìm thấy hàng voice_profiles cho {voice}")
            continue
        written += 1
        if not apply:
            continue
        database.upsert_voice_profile(
            {
                "voice_key": voice,
                "engine": profile["engine"],
                "preset_name": profile["preset_name"],
                "description": profile["description"],
                "seed": profile["seed"],
                "pitch_semitones": profile["pitch_semitones"],
                "formant_ratio": profile["formant_ratio"],
                "status": "ready",
            }
        )
        database.set_locked_character_voice(name, voice)

    # Người nói trong chương mà không được ghim nhưng mang một pin CŨ trùng giọng vừa gán cho người
    # khác: bỏ pin ấy, kẻo registry giữ người nhiều câu hơn và bỏ đúng người vừa được sửa.
    freed = 0
    for name, voice in sorted(pinned_character_names(target).items()):
        if name not in speakers or name in wanted:
            continue
        if taken_by.get(voice, set()) - {name}:
            freed += 1
            _say(f"  BỎ PIN {name}: {voice.replace('preset_', '')} đã gán cho người khác trong chương")
            if apply:
                unpin_character(database, name)

    verb = "đã" if apply else "sẽ"
    _say(f"{written} pin {verb} ghi, {freed} pin cũ {verb} bỏ, trong {target.name}.")
    if not apply:
        _say("Lượt thử, chưa ghi gì. Thêm --apply để ghim.")
    return written


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("project", nargs="?", type=Path)
    parser.add_argument("--apply", action="store_true", help="ghim thật (mặc định chỉ in kế hoạch)")
    parser.add_argument("--chapters", nargs="+", default=None, help="mô phỏng trên sách, không cần project")
    args = parser.parse_args(argv)

    if args.chapters:
        rows, majority = _book()
        if not rows:
            _say("không đọc được cuốn sách đã ghép")
            return 1
        totals = [0, 0, 0]
        for chapter in args.chapters:
            for index, value in enumerate(_print_plan(chapter, plan_chapter(chapter, rows, majority))):
                totals[index] += value
        _say()
        _say(f"tong: ve da so {totals[0]} | giu nguyen {totals[1]} | khong ghim {totals[2]}")
        return 0

    if args.project is None:
        parser.error("cần <project> hoặc --chapters")
    target = args.project.expanduser().resolve()
    if not (target / "project.sqlite3").is_file():
        _say(f"không phải project: {target}")
        return 2
    from ebook_reader.background_runner import get_status

    if get_status(target).running:
        _say(f"{target.name} đang chạy - ghim giọng lúc này là đổi dàn giọng giữa lượt. Dừng.")
        return 3
    try:
        keep(target, apply=args.apply)
    except sqlite3.Error as exc:
        _say(f"lỗi cơ sở dữ liệu: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
