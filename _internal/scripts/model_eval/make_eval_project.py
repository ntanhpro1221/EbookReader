r"""Tạo project nháp để đo MỘT model phân tích trên cùng một đề bài với mọi model khác.

    python scripts/model_eval/make_eval_project.py qwen3.5:9b
    python scripts/model_eval/make_eval_project.py qwen3:8b --chapters 351 363

Đề bài cố định (19-09, chủ sách giao việc chọn model phân tích):

  - chương: 351 363 378 381 của cuốn 2 (file nguồn; tiêu đề trong file lệch một số). Bốn kiểu khó
    khác nhau: 351 nhiều người nói nhất lô 8 (13), 363 nhiều độc thoại nội tâm (15), 378 dài và đông
    (120 đoạn, 11 người), 381 nhiều nhân vật không tên (5 NPC);
  - cấu hình: `settings_json` của lô 8 (`lo08_270cda51cf`), chỉ đổi `analysis.model`. Cùng
    `num_ctx`, nhiệt, seed, critic, ngưỡng tự tin - tức đúng những gì sản xuất đã chạy;
  - dàn nhân vật đã biết: gieo từ đúng project đã gieo cho lô 8 (`lo06r_266_22b5598370`), bằng
    `port_pronunciations` + `port_casting` như `launch_batch.sh`. Model nào cũng mở đầu với cùng
    danh sách "nhân vật đã biết" và cùng bảng phiên âm.

Project nằm ngoài `book2/_versions` nên không lọt vào nhịp tim, watchdog hay chuỗi gieo của sách.
Chạy lại cùng model thì MỞ LẠI project cũ (tên theo nội dung) - xoá thư mục của model ấy để đo lại.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ebook_reader.config import normalize_legacy_locked_settings, validate_settings  # noqa: E402
from ebook_reader.project import create_or_open_project  # noqa: E402

PY = ROOT / "runtime" / ".venv" / "Scripts" / "python.exe"
EVAL_ROOT = Path("D:/Novels/Audiobooks/_model_eval")
REFERENCE = Path("D:/Novels/Audiobooks/book2/_versions/v0.3.0-lo08/lo08_270cda51cf")
SEED = Path("D:/Novels/Audiobooks/book2/_versions/v0.3.0-lo06r/lo06r_266_22b5598370")
SOURCE = Path("D:/Novels/Ebook Reader/Text_Tmp")
CHAPTERS = ("351", "363", "378", "381")


def slug(model: str) -> str:
    """`qwen3.5:9b` -> `qwen3_5-9b`: một tên thư mục an toàn, không đụng nhau giữa các tag."""
    return model.replace(".", "_").replace(":", "-").replace("/", "_")


def reference_settings(model: str) -> dict:
    connection = sqlite3.connect(f"file:{REFERENCE / 'project.sqlite3'}?mode=ro", uri=True)
    try:
        settings = json.loads(connection.execute("SELECT settings_json FROM book").fetchone()[0])
    finally:
        connection.close()
    settings["analysis"]["model"] = model
    validate_settings(normalize_legacy_locked_settings(settings))
    return settings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("model")
    parser.add_argument("--chapters", nargs="+", default=list(CHAPTERS))
    parser.add_argument("--root", type=Path, default=EVAL_ROOT)
    parser.add_argument("--no-seed", action="store_true", help="không gieo dàn nhân vật (chỉ để thử máy)")
    args = parser.parse_args(argv)

    files = [SOURCE / f"{chapter}.txt" for chapter in args.chapters]
    missing = [str(path) for path in files if not path.is_file()]
    if missing:
        print("thiếu file nguồn: " + ", ".join(missing), file=sys.stderr)
        return 2
    settings = reference_settings(args.model)
    output_root = args.root / slug(args.model)
    title = f"eval_{slug(args.model)}"
    paths, db, _used = create_or_open_project(files, output_root, settings, title)
    fresh = not db.list_characters()
    print(f"project: {paths.root}")
    if not args.no_seed and fresh:
        for script in ("port_pronunciations.py", "port_casting.py"):
            subprocess.run([str(PY), str(ROOT / "scripts" / script), str(SEED), str(paths.root)], check=True)
    elif not fresh:
        print("đã gieo từ trước - giữ nguyên")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
