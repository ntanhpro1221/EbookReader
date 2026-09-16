"""Một nhịp tim: ranh giới đang ở đâu, project nào đang bay, cây git có sạch — in gọn một lần.

    python scripts/heartbeat_tick.py

Chỉ đọc. Dùng cho nhịp tim **TỰ CHẠY**, và đó là lý do nó tồn tại:

    bash -c 'sleep 1500; python scripts/heartbeat_tick.py' &     # nền

Khi lệnh nền ấy **kết thúc**, phiên làm việc được đánh thức và nhịp tim kế tiếp bắt đầu — kể cả
khi phiên đang im. Một việc cron thì **chỉ phát khi REPL rảnh**, nên trong lúc `boundary.sh` chạy
nền hàng giờ thì nó im **đúng lúc cần nhất**: chủ sách bắt được hai lần, và lần thứ hai là 06:25 →
07:09 ngày 16-09, khi ranh giới 4 đang qua bước 4b.

## Hai con số, không một

`status != 'analyzed'` là số đoạn **đã thu** trong pha tổng hợp, nhưng trong pha **phân tích** nó
lại là số đoạn **chưa** phân tích (đoạn mới sinh mang `pending`). Một con số duy nhất vì thế đọc
ngược hẳn giữa hai pha — nhịp 08:20 báo "3486/3717" cho một lô vừa chạy 16 phút. Nên in cả hai,
có nhãn. Một nhịp tim nói dối còn tệ hơn không có nhịp tim.

## Đếm gốc `boundary.sh` bằng Python, không bằng PowerShell lồng nhau

Chính shell bọc ngoài của lệnh cũng chứa chuỗi `boundary.sh 4 ...` trong dòng lệnh của nó
(`bash -c "... boundary.sh 4 ..."`), nên phép đếm thô báo "3 gốc" khi chỉ có **một**. Và một phép
lọc viết trong `-Command` phải qua hai tầng nháy (Python rồi PowerShell); bản đầu của nó trả về
rỗng **trong im lặng** và đếm ra 0 gốc trong khi có 1. Nên PowerShell chỉ làm một việc — đổ ra
từng dòng lệnh — còn lọc thì làm trong Python.
"""
from __future__ import annotations

import glob
import re
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from scripts.book_paths import VERSIONS, describe  # noqa: E402
except ImportError:  # chạy trực tiếp
    from book_paths import VERSIONS, describe  # noqa: E402

TOUCHED_SECONDS = 300.0


def say(line: str = "") -> None:
    try:
        print(line, flush=True)
    except UnicodeEncodeError:
        print(line.encode("ascii", "backslashreplace").decode("ascii"), flush=True)


def newest_log() -> Path | None:
    logs = sorted(ROOT.glob("runtime/boundary_*.log"), key=lambda p: p.stat().st_mtime)
    return logs[-1] if logs else None


def last_lines(log: Path, count: int = 6) -> list[str]:
    text = log.read_text(encoding="utf-8", errors="replace").splitlines()
    marks = [
        line
        for line in text
        if re.match(r"^\d\d-\d\d \d\d:\d\d:\d\d ", line)
        or line.startswith("=== chuong ")
        or line.startswith("  project: ")
    ]
    return marks[-count:]


def command_lines() -> list[str]:
    try:
        return subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                "Get-CimInstance Win32_Process | ForEach-Object { $_.CommandLine }",
            ],
            capture_output=True,
            text=True,
            timeout=60,
        ).stdout.splitlines()
    except (OSError, subprocess.SubprocessError) as exc:
        say(f"(không đếm được tiến trình: {exc!r})")
        return []


def flying() -> list[str]:
    out: list[str] = []
    now = time.time()
    for database in sorted(glob.glob(str(Path(VERSIONS) / "*" / "*" / "project.sqlite3"))):
        path = Path(database)
        if now - path.stat().st_mtime > TOUCHED_SECONDS:
            continue  # không ai chạm vào trong 5 phút - không phải project đang bay
        connection = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
        connection.row_factory = sqlite3.Row
        try:
            book = connection.execute("SELECT status, stage FROM book").fetchone()
            total = connection.execute("SELECT COUNT(*) FROM segments").fetchone()[0]
            analysed = connection.execute(
                "SELECT COUNT(*) FROM segments WHERE status = 'analyzed'"
            ).fetchone()[0]
            recorded = connection.execute(
                "SELECT COUNT(*) FROM segments WHERE wav_sha256 IS NOT NULL AND wav_sha256 != ''"
            ).fetchone()[0]
            failed = connection.execute(
                "SELECT COUNT(*) FROM segments WHERE status = 'failed'"
            ).fetchone()[0]
            drift = connection.execute(
                "SELECT COUNT(*) FROM segments WHERE (wav_path IS NOT NULL AND wav_path != '') "
                "!= (wav_sha256 IS NOT NULL AND wav_sha256 != '')"
            ).fetchone()[0]
            lease = connection.execute("SELECT MAX(heartbeat_at) h FROM worker_leases").fetchone()["h"]
        except sqlite3.Error as exc:
            out.append(f"{path.parent.name}: không đọc được ({exc})")
            continue
        finally:
            connection.close()
        age = round(now - float(lease), 1) if lease else -1.0
        out.append(
            f"{path.parent.name:<26} {book['status']}|{book['stage']:<22}"
            f" phân tích {analysed}/{total} | thu {recorded}/{total}"
            f" | hỏng {failed} | lệch wav {drift} | nhịp {age}s"
        )
    return out


def main() -> int:
    say(f"=== nhịp tim {time.strftime('%H:%M:%S ngày %d-%m')} ===")
    say(describe())
    lines = command_lines()
    roots = [line for line in lines if re.search(r"boundary\.sh \d", line) and " -c " not in line]
    say(f"tiến trình boundary.sh (gốc thật): {len(roots)}")
    for line in lines:
        if re.search(r"launch_(repair|batch)\.sh \d", line) and " -c " not in line:
            say(f"    con: {' '.join(line.split())[-90:]}")
    log = newest_log()
    if log is not None:
        stamp = time.strftime("%H:%M:%S", time.localtime(log.stat().st_mtime))
        say(f"log: {log.name}  (sửa lần cuối {stamp})")
        for line in last_lines(log):
            say(f"    {line[:150]}")
    say("")
    say("project đang bay (DB bị chạm trong 5 phút qua):")
    for line in flying() or ["    (không có)"]:
        say(f"    {line}")
    say("")
    dirty = subprocess.run(
        ["git", "status", "--porcelain"], cwd=str(ROOT), capture_output=True, text=True
    ).stdout.strip()
    say(f"cây git: {'sạch' if not dirty else f'{len(dirty.splitlines())} file đổi'}")
    say(
        subprocess.run(
            ["git", "log", "--oneline", "-1"], cwd=str(ROOT), capture_output=True, text=True
        ).stdout.strip()
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
