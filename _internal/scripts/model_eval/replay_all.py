"""Phát lại MỌI chương đáp án chuẩn qua đúng bộ phân tích sản xuất: dữ liệu huấn luyện + kiểm host, một lệnh.

    python scripts/model_eval/replay_all.py --root D:/Novels/Audiobooks/_model_eval_gold/replay_YYYYMMDD
    python scripts/model_eval/build_training_set.py <root>/train_*.jsonl --out D:/Novels/LLM_Train/data

Mỗi thư mục trong `gold/` thành một project nháp (make_eval_project.py, model `gold-replay:all`) chứa đúng các chương có
đáp án, rồi `gold_replay.py` chạy `analyze_all` với câu trả lời đúng và ghi `<root>/train_<truyện>.jsonl`, rồi
`score_models.py` chấm lại. Bảng cuối: một truyện dưới 100% người nói nghĩa là luật host đè đáp án đúng (hoặc đáp án
lệch luật - xem dòng LỆCH LUẬT). Không cần GPU, không gọi mạng. Chạy lại được: `--root` mới mỗi lần.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
GOLD = HERE / "gold"
CORPUS = ROOT.parent / "Corpus"

# Thư mục đáp án -> thư mục truyện trong Corpus/ (None = cuốn 2, nguồn sản xuất Text_Tmp, mặc định của make_eval_project).
BOOKS: dict[str, str | None] = {
    "throne_of_magical_arcana": None,
    "young_masters_pov": "Young Master's PoV Woke Up As A Villain In A Game One Day",
    "da_bao_la_cung_nhau_tu_sat": "Đã bảo là cùng nhau tự sát, cớ sao lại thành sống chung",
    "huong_dan_sinh_ton": "Hướng dẫn sinh tồn trong học viện",
    "nise_seiken": "Nise Seiken Monogatari",
    "nageki_no_bourei": "Nageki no Bourei wa Intai Shitai",
    "yamiyo_no_hotaru": "Yamiyo no Hotaru",
    "nang_luc_ba_dao": "Năng lực bá đạo của tôi trong game tử thần là những thiếu nữ xinh đẹp",
    "love_unseen": "Love Unseen Beneath the Clear Night Sky",
    "two_childhood_friends": "Two Childhood Friends Who Have the Strongest Power Kick Each Other in the Dungeon With All Their Might",
}


def run(args: list[str]) -> str:
    result = subprocess.run([sys.executable, *args], cwd=str(ROOT), text=True, capture_output=True, encoding="utf-8",
                            errors="replace")
    return result.stdout + result.stderr


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", type=Path, required=True, help="thư mục mới cho các project phát lại")
    parser.add_argument("--only", nargs="*", default=None, help="chỉ các thư mục đáp án này")
    args = parser.parse_args()
    if args.root.exists() and any(args.root.iterdir()):
        raise SystemExit(f"{args.root} đã có dữ liệu - chọn --root mới")

    missing = sorted(p.name for p in GOLD.iterdir() if p.is_dir() and p.name not in BOOKS)
    if missing:
        raise SystemExit(f"thư mục đáp án chưa khai trong BOOKS: {missing}")

    table = []
    for gold, book in BOOKS.items():
        if args.only and gold not in args.only:
            continue
        chapters = sorted(p.stem for p in (GOLD / gold).glob("*.txt"))
        if not chapters:
            continue
        where = args.root / gold
        make = ["scripts/model_eval/make_eval_project.py", "gold-replay:all", "--chapters", *chapters, "--root", str(where)]
        if book:
            make += ["--book", book]
        run(make)
        project = next(where.rglob("project.sqlite3"), None)
        if project is None:
            table.append((gold, len(chapters), "KHÔNG TẠO ĐƯỢC PROJECT", ""))
            continue
        replay = run(["scripts/model_eval/gold_replay.py", str(project.parent), "--gold", gold,
                      "--out", str(args.root / f"train_{gold}.jsonl")])
        conflicts = [line.strip() for line in replay.splitlines() if "LỆCH LUẬT" in line]
        score = run(["scripts/model_eval/score_models.py", str(project.parent), "--gold", gold, "--misses", "20"])
        row = next((line for line in score.splitlines() if line.startswith("gold-replay:all")), "")
        numbers = re.findall(r"\d+\.\d+", row)
        misses = [line.strip() for line in score.splitlines() if line.strip().startswith("- ")]
        table.append((gold, len(chapters), f"điểm {numbers[0]} người nói {numbers[1]}" if len(numbers) > 1 else row,
                      "\n      ".join(conflicts + misses)))
        print(f"{gold}: {table[-1][2]}", flush=True)

    print("\n=== tổng kết")
    for gold, n, summary, detail in table:
        print(f"{gold:28} {n:3} chương  {summary}")
        if detail:
            print(f"      {detail}")


if __name__ == "__main__":
    main()
