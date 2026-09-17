"""Một bản đúc lại chỉ được lên sách khi nó GIÚP nhiều người hơn nó HẠI. Cổng tự động, chạy ngay khi thu xong.

    python scripts/ship_only_recasts_that_help.py <project>            # chỉ phán, không dời gì
    python scripts/ship_only_recasts_that_help.py <project> --apply    # project hại thì dời ra quarantine

Mã thoát: `0` = lên sách được, hoặc không có gì để phán; `10` = hại nhiều hơn giúp (đã dời ra
nếu có `--apply`); `1`/`2`/`3` = lỗi, không phải project, hoặc project đang chạy.

`launch_repair.sh` gọi nó ở chế độ đúc lại, ngay sau khi chương thu xong. Gặp mã `10` thì chương
ấy KHÔNG thành project gieo cho chương kế tiếp, và vì đã ra khỏi `_versions` nên bước 7
(`assemble_book`) không thấy nó: sách giữ bản cũ.

## Vì sao phải là một cổng, không phải một việc người làm

Tối 16-09, ranh giới 5 đúc lại năm chương khi không ai trông. Một lỗi (`pin_the_book_cast` nổ trước
vòng ghim giọng đa số) làm cả năm ra tệ hơn bản đang ở trên sách: tốt hơn 2, xấu hơn 8, đo bằng
`measure_did_the_recast_help.py`. Nếu máy không tắt giữa chừng thì bước 7 đã ghép cả năm lên sách.
Thước đo đã có sẵn từ ranh giới 4. Chỉ thiếu một chỗ **bắt buộc** hỏi nó trước khi ghép. Sáng 17-09
tôi đọc thước bằng tay rồi dời bốn project ra `book2/_quarantine_2026-09-17/`. Script này làm đúng
việc ấy, ở đúng lúc ấy, không cần người.

## Phán thế nào

Với mỗi chương `completed` của project mà đã có một bản thu xong KHÁC. Bản khác ấy là bản trên sách, hoặc
bản `completed` mới nhất trong `_versions` với chương của lô vừa xong mà bước 7 chưa ghép; cùng một
nguồn với `keep_the_chapter_cast.rows_as_they_will_ship`:

- giọng CŨ của mỗi người = giọng nhiều câu nhất của họ ở chương ấy trong bản khác ấy;
- giọng MỚI = giọng nhiều câu nhất của họ ở chương ấy trong project này;
- giọng ĐA SỐ = giọng họ dùng ở nhiều chương nhất trên sách-như-sẽ-ghép, **trừ chính chương này** ra, để phép so
  không tự chứng minh (cùng luật với `measure_did_the_recast_help.py`).

Người đổi giọng mà mới == đa số (cũ thì không) là TỐT HƠN. Cũ == đa số mà mới thì không là XẤU HƠN.
Còn lại là không rõ, không tính.

**Lên sách khi và chỉ khi tốt hơn > xấu hơn.** `0 | 0` cũng KHÔNG lên: lần đúc lại không sửa được ai,
và bản đang ở trên sách là bản đã biết là ổn. Chương 027 ngày 17-09 đúng là ca ấy.

Chương chưa từng thu xong ở đâu khác (lô vá chương hỏng) không có gì để so, và project đã được ghép
lên sách rồi thì không còn bản cũ để so: cả hai trả `0` và nói rõ lý do.
"""
from __future__ import annotations

import argparse
import collections
import shutil
import sqlite3
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.book_paths import AUDIOBOOKS_ROOT  # noqa: E402
from scripts.name_marks import fold_dropped_marks  # noqa: E402
from scripts.pin_the_book_cast import majority_voices  # noqa: E402
from scripts.keep_the_chapter_cast import rows_as_they_will_ship  # noqa: E402
from scripts.voice_matches_the_person import read_rows  # noqa: E402

HARMFUL = 10
BETTER = "TOT HON"
WORSE = "XAU HON"
UNCLEAR = "khong ro"


def _say(line: str = "") -> None:
    try:
        print(line, flush=True)
    except UnicodeEncodeError:
        print(line.encode("ascii", "backslashreplace").decode("ascii"), flush=True)


def _main_voice(rows: list[dict], chapter: str) -> dict[str, str]:
    """{tên: giọng nhiều câu nhất} của một chương."""
    lines: dict[str, collections.Counter[str]] = collections.defaultdict(collections.Counter)
    for row in rows:
        if str(row["chapter"]) == chapter:
            lines[str(row["name"])][str(row["voice"])] += int(row["lines"])
    return {name: voices.most_common(1)[0][0] for name, voices in lines.items()}


def judge(chapter: str, book: list[dict], project: list[dict]) -> list[tuple[str, str, str, str, str]]:
    """[(tên, giọng cũ, giọng mới, đa số trừ chương này, phán quyết)] cho người ĐỔI giọng."""
    folded = fold_dropped_marks(sorted({str(r["name"]) for r in book} | {str(r["name"]) for r in project}))
    book = [{**r, "name": folded.get(str(r["name"]), str(r["name"]))} for r in book]
    project = [{**r, "name": folded.get(str(r["name"]), str(r["name"]))} for r in project]
    old = _main_voice(book, chapter)
    new = _main_voice(project, chapter)
    majority = majority_voices([r for r in book if str(r["chapter"]) != chapter])
    verdicts = []
    for name in sorted(set(old) & set(new)):
        if old[name] == new[name]:
            continue
        top = majority.get(name, ("", 0, 0))[0]
        if top and new[name] == top and old[name] != top:
            verdict = BETTER
        elif top and old[name] == top and new[name] != top:
            verdict = WORSE
        else:
            verdict = UNCLEAR
        verdicts.append((name, old[name], new[name], top, verdict))
    return verdicts


def completed_chapters(target: Path) -> set[str]:
    connection = sqlite3.connect(f"file:{(target / 'project.sqlite3').as_posix()}?mode=ro", uri=True)
    try:
        return {
            str(row[0])
            for row in connection.execute("SELECT title FROM chapters WHERE status = 'completed'")
        }
    finally:
        connection.close()


def quarantine_path(target: Path, root: Path = AUDIOBOOKS_ROOT) -> Path:
    """`<gốc sách>/_quarantine_<ngày>/<thư mục phiên bản>/<project>` - ngoài `_versions`, không xoá."""
    return root / f"_quarantine_{time.strftime('%Y-%m-%d')}" / target.parent.name / target.name


def decide(target: Path, *, apply: bool, root: Path = AUDIOBOOKS_ROOT) -> int:
    book = rows_as_they_will_ship(exclude=target)
    mine = read_rows(target)
    on_book: dict[str, set[str]] = collections.defaultdict(set)
    for row in book:
        on_book[str(row["chapter"])].add(str(row.get("project", "")))

    better = worse = judged = 0
    for chapter in sorted(completed_chapters(target)):
        if chapter not in on_book:
            _say(f"  chuong {chapter}: khong co ban nao khac da thu xong - khong co ban cu de so")
            continue
        if target.name in on_book[chapter]:
            _say(f"  chuong {chapter}: sach DANG phat chinh project nay - khong con ban cu de so")
            continue
        judged += 1
        verdicts = judge(chapter, book, mine)
        good = sum(1 for v in verdicts if v[4] == BETTER)
        bad = sum(1 for v in verdicts if v[4] == WORSE)
        better += good
        worse += bad
        _say(f"  chuong {chapter}: {len(verdicts)} nguoi doi giong | tot hon {good} | xau hon {bad}")
        for name, old, new, top, verdict in verdicts:
            _say(
                f"      {name:18s} {old.replace('preset_', ''):22s} -> {new.replace('preset_', ''):22s}"
                f" {verdict:9s} (da so: {top.replace('preset_', '') or '-'})"
            )

    if not judged:
        _say(f"{target.name}: khong co chuong nao de phan - de nguyen.")
        return 0
    if better > worse:
        _say(f"{target.name}: tot hon {better} > xau hon {worse} - LEN SACH.")
        return 0
    destination = quarantine_path(target, root)
    _say(
        f"{target.name}: tot hon {better} <= xau hon {worse} - KHONG len sach;"
        f" {'da doi' if apply else 'se doi'} sang {destination}"
    )
    if apply:
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(target), str(destination))
    return HARMFUL


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("project", type=Path)
    parser.add_argument("--apply", action="store_true", help="doi project hai ra quarantine")
    args = parser.parse_args(argv)
    target = args.project.expanduser().resolve()
    if not (target / "project.sqlite3").is_file():
        _say(f"khong phai project: {target}")
        return 2
    from ebook_reader.background_runner import get_status

    if get_status(target).running:
        _say(f"{target.name} dang chay - chua co gi de phan.")
        return 3
    try:
        return decide(target, apply=args.apply)
    except (sqlite3.Error, OSError) as exc:
        _say(f"loi khi phan {target.name}: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
