"""Tiến độ một lượt đo model, đếm ĐÚNG cột - dùng thay cho truy vấn tự viết.

    python scripts/model_eval/eval_progress.py D:/Novels/Audiobooks/_model_eval_v2/21-09-no-counts

Tồn tại vì tôi đã tự viết truy vấn sai ngay trong buổi có lượt đo (21-09, xem `docs/LLM_EVAL.md`):

  - **SAI**: `count(*) where speaker is not null and speaker<>''`. Cột `speaker` CÓ mặc định, nên câu này
    báo "đủ 100%" ngay khi chương vừa chia đoạn: một project 97 đoạn với 85 đoạn còn `pending` vẫn hiện
    `NARRATOR` 52 và `UNKNOWN` 40.
  - **ĐÚNG cho tiến độ**: `status<>'pending'`.
  - **ĐÚNG cho "xong hẳn"**: có file `model_eval_run.json`. Sau `analyze_all` còn `local_identities` -
    bước hợp nhất NPC vào nhân vật có tên - và nó ĐỔI `speaker`, nên chấm trước khi có file ấy là đo một
    mục tiêu đang di chuyển (gemma4:e2b ra 74,8 rồi 77,2 trên cùng bốn chương).

In thêm dòng nhịp cuối trong `runtime_events` của chương đang chạy, vì đó là chỗ duy nhất thấy được batch
thứ mấy trên bao nhiêu.
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path


def chapter_state(directory: Path) -> str:
    db = next(directory.rglob("project.sqlite3"), None)
    if db is None:
        return "đang dựng project"
    finished = next(directory.rglob("model_eval_run.json"), None)
    connection = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        total, = connection.execute("select count(*) from segments").fetchone()
        done, = connection.execute("select count(*) from segments where status<>'pending'").fetchone()
        last = connection.execute(
            "select message from runtime_events order by id desc limit 1"
        ).fetchone()
    finally:
        connection.close()
    if finished is not None:
        record = json.loads(finished.read_text(encoding="utf-8"))
        return f"{done}/{total}  XONG HẲN trong {record['total_seconds']:.0f}s"
    trace = " ".join(str(last[0]).split())[:70] if last else ""
    return f"{done}/{total}  đang chạy | {trace}"


def main() -> int:
    root = Path(sys.argv[1])
    if not root.is_dir():
        print(f"không có thư mục {root}")
        return 1
    table = root / "eval_models.json"
    for model_dir in sorted(p for p in root.iterdir() if p.is_dir()):
        print(model_dir.name)
        for chapter_dir in sorted((p for p in model_dir.iterdir() if p.is_dir()), key=lambda p: p.name):
            print(f"   {chapter_dir.name}: {chapter_state(chapter_dir)}")
    print(f"\nbảng {table.name}: " + ("đã ghi" if table.exists() else "chưa ghi"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
