"""Trỏ lại nguồn .txt của project sau khi thư mục nguồn dời chỗ — có kiểm hash, có sổ để hoàn tác.

    python scripts/repoint_the_source.py "D:/Novels/Ebook Reader/Text"                 # mọi project dưới VERSIONS của cuốn hiện tại, CHỈ XEM
    python scripts/repoint_the_source.py "D:/Novels/Ebook Reader/Text" --apply         # ghi thật
    python scripts/repoint_the_source.py "D:/Novels/Ebook Reader/Text" --project <dir> [--apply]
    python scripts/repoint_the_source.py --root <_versions> ...                         # gốc khác (cuốn khác): hoặc `source scripts/book1.env`
    python scripts/repoint_the_source.py --undo <project dir>                           # trả lại đường cũ theo sổ

Vì sao có file này (2026-09-13, 23:30): thư mục nguồn của cuốn 1 (`D:/Novels/Tools/Text`, 478 chương) bị
xoá giữa lô 10, rồi chủ sách bảo khôi phục *nhưng chuyển vào thư mục project* (`D:/Novels/Ebook Reader/Text`).
Project ghi **đường dẫn tuyệt đối** của từng chương vào `chapters.input_path` lúc `create`, và khoá cả
danh sách bằng `book.input_manifest_hash` = sha256 của `chapter_index|input_path|input_sha256|input_size`
mọi chương. Dời thư mục là 118 project của cuốn 1 cùng trỏ vào chỗ trống: `cli run` dừng ngay ("Source
chapter is missing"), `cli verify` đỏ ở `source_files`, và luật "tên này có trong sách không" của
`character_registry` (đọc *thư mục* của input_path để lấy bằng chứng) tự tắt vì không thấy thư mục.

Nối lại bằng junction ở chỗ cũ là giấu vết: `Tools/` là thư mục chủ sách đang sắp xếp lại. Sửa tay từng
DB là cách để sai một cái. Nên: một công cụ, làm đúng một việc, và **không tin tên file** — mỗi chương
chỉ được trỏ sang file mới khi file ấy có đúng `input_sha256` và `input_size` đã khoá lúc create. Một
chương lệch là **cả project bị bỏ qua**, không có chuyện trỏ nửa vời. Băm lại `input_manifest_hash` bằng
chính `text_processing.input_manifest_hash` (cùng hàm `cli verify` dùng để so), nên `verify` xanh lại
đúng nghĩa chứ không phải vì tắt kiểm.

Không đụng gì khác: `book.last_error` và `runtime_events` còn nhắc đường cũ là **lịch sử**, để nguyên.
Không dùng `ProjectDB` vì mở bằng lớp ấy có thể kéo theo di trú schema trên DB cũ (alpha.*); sqlite3
thẳng, một transaction cho mỗi project.

Sổ: `<project>/source_repoint_ledger.json` — mỗi lượt ghi một mục (giờ, thư mục mới, hash cũ/mới, từng
chương cũ → mới). `--undo` đọc mục cuối, kiểm đường hiện tại đúng là "mới" của mục ấy, trả lại đường
cũ + hash cũ, rồi bỏ mục khỏi sổ. Sổ nằm ngoài DB nên schema không đổi.

Mã thoát: 0 nếu không project nào phải bỏ qua; 1 nếu có (đọc dòng `BỎ QUA:` để biết vì sao — project
trỏ một nguồn *khác hẳn* (ví dụ alpha.10 đọc `Text_Tmp` tháng 8) cũng hiện ở đây, đó là đúng: nó không
thuộc thư mục mới, và không ai được trỏ nó sang).
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from scripts.book_paths import VERSIONS  # noqa: E402
except ImportError:  # chạy trực tiếp: scripts/ là sys.path[0]
    from book_paths import VERSIONS  # noqa: E402

from ebook_reader.text_processing import input_manifest_hash, sha256_file  # noqa: E402

LEDGER_NAME = "source_repoint_ledger.json"


def _say(text: str) -> None:
    try:
        print(text, flush=True)
    except UnicodeEncodeError:
        print(text.encode("ascii", "backslashreplace").decode("ascii"), flush=True)


def _read(database: Path) -> tuple[list[dict], str]:
    connection = sqlite3.connect(f"file:{database.as_posix()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        rows = [
            dict(row)
            for row in connection.execute(
                "SELECT id, chapter_index, input_path, input_sha256, input_size "
                "FROM chapters ORDER BY chapter_index"
            )
        ]
        locked = str(connection.execute("SELECT input_manifest_hash FROM book").fetchone()[0])
    finally:
        connection.close()
    return rows, locked


def plan(project: Path, new_source_dir: Path) -> dict:
    """Xem một project: chương nào đổi sang đâu, chương nào không thể. Không ghi gì."""
    database = project / "project.sqlite3"
    rows, locked = _read(database)
    changes: list[dict] = []
    unchanged = 0
    problems: list[str] = []
    for row in rows:
        old = str(row["input_path"])
        target = (new_source_dir / Path(old).name).resolve()
        new = str(target)
        if new == old:
            unchanged += 1
            continue
        if not target.is_file():
            problems.append(f"{Path(old).name}: không có trong {new_source_dir}")
            continue
        size = target.stat().st_size
        if size != int(row["input_size"]):
            problems.append(f"{Path(old).name}: kích cỡ {size} ≠ {row['input_size']} đã khoá")
            continue
        digest = sha256_file(target)
        if digest != str(row["input_sha256"]):
            problems.append(f"{Path(old).name}: sha256 khác bản đã khoá (nguồn khác, không phải cùng file)")
            continue
        changes.append({"id": int(row["id"]), "old": old, "new": new})
    new_hash = locked
    if changes and not problems:
        by_id = {change["id"]: change["new"] for change in changes}
        manifest = [
            {
                "chapter_index": row["chapter_index"],
                "input_path": by_id.get(int(row["id"]), row["input_path"]),
                "input_sha256": row["input_sha256"],
                "input_size": row["input_size"],
            }
            for row in rows
        ]
        new_hash = input_manifest_hash(manifest)
    return {
        "project": project,
        "chapters": len(rows),
        "changes": changes,
        "unchanged": unchanged,
        "problems": problems,
        "old_hash": locked,
        "new_hash": new_hash,
    }


def apply(planned: dict, new_source_dir: Path) -> None:
    """Ghi kế hoạch đã kiểm vào DB (một transaction) và chép vào sổ."""
    project: Path = planned["project"]
    database = project / "project.sqlite3"
    connection = sqlite3.connect(database)
    try:
        connection.execute("BEGIN")
        for change in planned["changes"]:
            connection.execute(
                "UPDATE chapters SET input_path = ? WHERE id = ? AND input_path = ?",
                (change["new"], change["id"], change["old"]),
            )
        connection.execute(
            "UPDATE book SET input_manifest_hash = ? WHERE input_manifest_hash = ?",
            (planned["new_hash"], planned["old_hash"]),
        )
        connection.execute("COMMIT")
    except Exception:
        connection.execute("ROLLBACK")
        raise
    finally:
        connection.close()
    ledger_path = project / LEDGER_NAME
    ledger = json.loads(ledger_path.read_text(encoding="utf-8")) if ledger_path.is_file() else []
    ledger.append(
        {
            "at": time.time(),
            "new_source_dir": str(new_source_dir),
            "old_manifest_hash": planned["old_hash"],
            "new_manifest_hash": planned["new_hash"],
            "chapters": planned["changes"],
        }
    )
    ledger_path.write_text(json.dumps(ledger, ensure_ascii=False, indent=1), encoding="utf-8")


def undo(project: Path) -> int:
    """Trả lại đường cũ theo mục cuối của sổ. Chỉ làm khi DB đúng là đang ở trạng thái 'mới' của mục ấy."""
    ledger_path = project / LEDGER_NAME
    if not ledger_path.is_file():
        _say(f"không có sổ {LEDGER_NAME} trong {project}")
        return 1
    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    if not ledger:
        _say("sổ rỗng - không có gì để hoàn tác")
        return 1
    entry = ledger[-1]
    rows, locked = _read(project / "project.sqlite3")
    current = {int(row["id"]): str(row["input_path"]) for row in rows}
    drift = [
        change for change in entry["chapters"] if current.get(int(change["id"])) != change["new"]
    ]
    if drift or locked != entry["new_manifest_hash"]:
        _say(
            f"DB không còn ở trạng thái của mục cuối trong sổ ({len(drift)} chương lệch, "
            f"hash {'khớp' if locked == entry['new_manifest_hash'] else 'lệch'}) - không hoàn tác mù."
        )
        return 1
    connection = sqlite3.connect(project / "project.sqlite3")
    try:
        connection.execute("BEGIN")
        for change in entry["chapters"]:
            connection.execute(
                "UPDATE chapters SET input_path = ? WHERE id = ?", (change["old"], change["id"])
            )
        connection.execute(
            "UPDATE book SET input_manifest_hash = ?", (entry["old_manifest_hash"],)
        )
        connection.execute("COMMIT")
    except Exception:
        connection.execute("ROLLBACK")
        raise
    finally:
        connection.close()
    ledger.pop()
    ledger_path.write_text(json.dumps(ledger, ensure_ascii=False, indent=1), encoding="utf-8")
    _say(f"đã trả {len(entry['chapters'])} chương về đường cũ; hash {entry['old_manifest_hash'][:12]}…")
    return 0


def _projects_under(root: Path) -> list[Path]:
    return sorted(database.parent for database in root.glob("*/*/project.sqlite3"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("new_source_dir", nargs="?", help="thư mục .txt mới")
    parser.add_argument("--project", type=Path, help="chỉ một project (mặc định: mọi project dưới --root)")
    parser.add_argument("--root", type=Path, default=VERSIONS, help=f"gốc _versions (mặc định {VERSIONS})")
    parser.add_argument("--apply", action="store_true", help="ghi thật (mặc định chỉ xem)")
    parser.add_argument("--undo", type=Path, metavar="PROJECT", help="hoàn tác lượt cuối theo sổ của project")
    args = parser.parse_args(argv)

    if args.undo:
        return undo(args.undo.resolve())
    if not args.new_source_dir:
        parser.error("cần thư mục nguồn mới (hoặc --undo)")
    new_source_dir = Path(args.new_source_dir).resolve()
    if not new_source_dir.is_dir():
        _say(f"không phải thư mục: {new_source_dir}")
        return 2

    projects = [args.project.resolve()] if args.project else _projects_under(args.root.resolve())
    if not projects:
        _say(f"không có project nào dưới {args.root}")
        return 2
    _say(f"nguồn mới: {new_source_dir}   ({'GHI THẬT' if args.apply else 'CHỈ XEM - thêm --apply để ghi'})")
    skipped = 0
    written = 0
    touched_chapters = 0
    for project in projects:
        try:
            planned = plan(project, new_source_dir)
        except sqlite3.Error as exc:
            _say(f"  {project.parent.name}/{project.name}: không đọc được DB ({exc})")
            skipped += 1
            continue
        label = f"{project.parent.name}/{project.name}"
        if planned["problems"]:
            skipped += 1
            _say(
                f"  {label}: chương={planned['chapters']} BỎ QUA: {len(planned['problems'])} chương "
                f"không khớp - {planned['problems'][0]}"
                + (f" (+{len(planned['problems']) - 1})" if len(planned["problems"]) > 1 else "")
            )
            continue
        if not planned["changes"]:
            _say(f"  {label}: chương={planned['chapters']} đã trỏ đúng, không đổi")
            continue
        if args.apply:
            apply(planned, new_source_dir)
            written += 1
            verb = "ĐÃ GHI"
        else:
            verb = "sẽ đổi"
        touched_chapters += len(planned["changes"])
        _say(
            f"  {label}: chương={planned['chapters']} {verb} {len(planned['changes'])} "
            f"(giữ {planned['unchanged']}); hash {planned['old_hash'][:10]}… → {planned['new_hash'][:10]}…"
        )
    _say(
        f"tổng: {len(projects)} project, {written if args.apply else 'sẽ ghi ' + str(len(projects) - skipped)} "
        f"{'đã ghi' if args.apply else ''}, {touched_chapters} chương đổi đường, {skipped} bỏ qua"
    )
    return 1 if skipped else 0


if __name__ == "__main__":
    sys.exit(main())
