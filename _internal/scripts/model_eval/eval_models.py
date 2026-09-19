"""So các model phân tích: MỖI CHƯƠNG một project, độ tin cậy tách khỏi độ chính xác.

    python scripts/model_eval/eval_models.py qwen3:8b gemma4:e4b-it-qat --root D:/Novels/Audiobooks/_model_eval_v2/20-09 \
        [--chapters 351 363 378 381] [--timeout 1200] [--no-think-for qwen3 qwen3.5]

Bài học đêm 20-09 (docs/LLM_EVAL.md): chạy cả 4 chương trong một project thì một lô rơi ID ("LLM returned 4/5 IDs") là
`analyze_all` ném lỗi bắt buộc và mất trắng cả bài đo - gemma4:12b, ministral-3:8b chết ở lô 7-8, dòng qwen3.5 và
qwen3:4b trả 0 ID ngay lô 1. Ở đây mỗi chương chạy riêng (`analysis_only.py`, có trần giờ), nên:

  - ĐỘ TIN CẬY = số chương chạy trọn / số chương thử, cộng số lần thử lại vì thiếu ID. Trong sản xuất một chương không
    chạy trọn là một lô đứng - model trượt cổng này thì độ chính xác không cứu được;
  - ĐỘ CHÍNH XÁC chấm trên các chương chạy trọn (gộp mọi đoạn, cùng trọng số với score_models.py).

`--no-think-for` gửi "think": false cho các model có tên bắt đầu bằng các tiền tố ấy (analysis_only.py --no-think).
Chạy chỉ khi GPU rảnh (ranh giới lô): nó tự khởi động Ollama như sản xuất.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))

from score_models import GOLD_ROOT, WEIGHTS, load_gold, read_project, score_rows  # noqa: E402

RETRY_PATTERN = re.compile(r"lỗi lần \d+: LLM returned (\d+)/(\d+) IDs")


def slug(model: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", model.lower()).strip("-")


def run_chapter(model: str, chapter: str, root: Path, book: str | None, timeout: int, no_think: bool) -> dict:
    where = root / slug(model) / chapter
    make = [sys.executable, "scripts/model_eval/make_eval_project.py", model, "--chapters", chapter, "--root", str(where)]
    if book:
        make += ["--book", book]
    subprocess.run(make, cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8", errors="replace")
    project = next(where.rglob("project.sqlite3"), None)
    if project is None:
        return {"chapter": chapter, "ok": False, "why": "không tạo được project"}
    command = [sys.executable, "scripts/model_eval/analysis_only.py", str(project.parent)]
    if no_think:
        command.append("--no-think")
    started = time.perf_counter()
    try:
        done = subprocess.run(command, cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8",
                              errors="replace", timeout=timeout)
        output, code = done.stdout + done.stderr, done.returncode
    except subprocess.TimeoutExpired as expired:
        output = (expired.stdout or "") + (expired.stderr or "") if isinstance(expired.stdout, str) else ""
        code = "timeout"
    seconds = round(time.perf_counter() - started, 1)
    retries = RETRY_PATTERN.findall(output)
    why = ""
    if code != 0:
        last = [line for line in output.splitlines() if "RuntimeError" in line or "thất bại" in line]
        why = (last[-1] if last else f"exit {code}")[:160]
    return {"chapter": chapter, "ok": code == 0, "project": str(project.parent), "seconds": seconds,
            "id_retries": len(retries), "why": why}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("models", nargs="+")
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--chapters", nargs="+", default=["351", "363", "378", "381"])
    parser.add_argument("--book", default=None, help="thư mục truyện trong Corpus/ (mặc định cuốn 2)")
    parser.add_argument("--gold", default="throne_of_magical_arcana")
    parser.add_argument("--timeout", type=int, default=1200, help="giây cho MỘT chương")
    parser.add_argument("--no-think-for", nargs="*", default=["qwen3"], help="tiền tố tên model được gửi think=false")
    args = parser.parse_args()

    gold = load_gold(GOLD_ROOT / args.gold)
    gold_chapters = {chapter for chapter, _ in gold}
    summary = []
    for model in args.models:
        no_think = any(model.startswith(prefix) for prefix in args.no_think_for)
        runs = []
        for chapter in args.chapters:
            result = run_chapter(model, chapter, args.root, args.book, args.timeout, no_think)
            runs.append(result)
            print(f"{model} {chapter}: {'OK' if result['ok'] else 'HỎNG'} {result.get('seconds', '')}s "
                  f"thử lại vì thiếu ID {result.get('id_retries', 0)} {result.get('why', '')}", flush=True)
        rows = []
        for result in runs:
            if result["ok"]:
                chapter_rows, _meta = read_project(Path(result["project"]), gold_chapters)
                rows += chapter_rows
        scored = score_rows(gold, rows) if rows else {"score": 0.0, "rates": {name: 0.0 for name in WEIGHTS}}
        entry = {
            "model": model, "no_think": no_think,
            "chapters_ok": sum(r["ok"] for r in runs), "chapters": len(runs),
            "id_retries": sum(r.get("id_retries", 0) for r in runs),
            "seconds_ok": round(sum(r.get("seconds", 0) for r in runs if r["ok"]), 1),
            "score": scored["score"], "rates": scored["rates"], "runs": runs,
        }
        summary.append(entry)

    summary.sort(key=lambda e: (-(e["chapters_ok"] == e["chapters"]), -e["score"]))
    print(f"\n{'model':24} {'tin cậy':>8} {'thử lại':>7} {'điểm':>5} {'người nói':>9} {'cảm xúc':>7} {'giây':>7}")
    for e in summary:
        print(f"{e['model'][:24]:24} {e['chapters_ok']:>3}/{e['chapters']:<4} {e['id_retries']:>7} {e['score']:5.1f} "
              f"{e['rates']['speaker']:9.1f} {e['rates']['emotion']:7.1f} {e['seconds_ok']:7.0f}")
    args.root.mkdir(parents=True, exist_ok=True)
    (args.root / "eval_models.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
