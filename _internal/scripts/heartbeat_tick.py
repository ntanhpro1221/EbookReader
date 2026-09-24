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

## Một cây là một gốc, dù nó có bốn tiến trình

Từ 24-09 ranh giới chạy RỜI (`scripts/run_detached.py`): `pythonw` của venv → `pythonw` gốc → Git Bash
`bin/bash.exe` → `usr/bin/bash.exe`, và cả bốn đều mang `boundary.sh 17` trong dòng lệnh mà không cái nào là
`bash -c`. Phép lọc theo chuỗi báo "4 gốc" cho đúng một ranh giới (nhịp 22:01 ngày 24-09). Nên giờ đếm theo
cây: một tiến trình khớp chỉ là gốc khi CHA của nó không khớp.
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


STAMP = ROOT / "runtime" / "heartbeat_last.txt"


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


def processes() -> list[tuple[int, int, str]]:
    """(pid, pid cha, dòng lệnh) của mọi tiến trình. JSON thay vì dòng trần: không cần nháy lồng nhau."""
    import json

    try:
        raw = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                "Get-CimInstance Win32_Process | Select-Object ProcessId,ParentProcessId,CommandLine"
                " | ConvertTo-Json -Compress",
            ],
            capture_output=True,
            text=True,
            # utf-8 + replace: với bảng mã mặc định, một dòng lệnh có ký tự lạ làm luồng đọc
            # stdout chết và `.stdout` về None - nhịp tim 17-09 23:4x nổ AttributeError đúng thế.
            encoding="utf-8",
            errors="replace",
            timeout=60,
        ).stdout or "[]"
        rows = json.loads(raw)
    except (OSError, subprocess.SubprocessError, ValueError) as exc:
        say(f"(không đếm được tiến trình: {exc!r})")
        return []
    if isinstance(rows, dict):
        rows = [rows]
    return [
        (int(row.get("ProcessId") or 0), int(row.get("ParentProcessId") or 0), row.get("CommandLine") or "")
        for row in rows
    ]


def tree_roots(procs: list[tuple[int, int, str]], pattern: str) -> list[str]:
    """Dòng lệnh của các tiến trình khớp `pattern` mà cha KHÔNG khớp - mỗi cây đếm một lần."""
    matching = {
        pid: (parent, line)
        for pid, parent, line in procs
        if re.search(pattern, line) and " -c " not in line
    }
    return [line for parent, line in matching.values() if parent not in matching]


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
            # Xong rồi thì không "bay", dù DB vừa bị chạm: ranh giới ghi sổ cộng dồn vào MỌI project cũ
            # (`backfill_exposure`) ngay trước khi thả lô kế, và nhịp 17:55 ngày 19-09 in ra cả trăm dòng
            # "đang bay" cho những project đã xong từ tuần trước.
            # `created` KHÔNG tính là xong ở đây: một lô vừa tạo đúng là đang bay.
            if book["status"] == "completed" or book["stage"] in FINISHED_STAGES:
                continue
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
            # Trạng thái CHƯƠNG, không chỉ đoạn: nhịp tim của chủ sách hỏi đúng thứ này, và một
            # lô có thể thu đều mà vẫn không chương nào `completed` (chương chỉ xong khi mọi đoạn
            # của nó xong, rồi mới tới ghép MP3 + kiểm chất lượng chương).
            chapters = ", ".join(
                f"{row['status']} {row['n']}"
                for row in connection.execute(
                    "SELECT status, COUNT(*) n FROM chapters GROUP BY status ORDER BY n DESC"
                )
            )
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
        out.append(f"{'':<26} chương: {chapters}")
    return out


STOPPED_WINDOW_SECONDS = 12 * 3600.0
FINISHED_STATUSES = {"completed", "created"}
# Lô đã chạy HẾT nhưng có chương hỏng: `error|completed_with_errors`. Đó là một lô xong - chương hỏng
# của nó đi qua project vá riêng - chứ không phải một lượt chết giữa chừng. Và ranh giới ghi sổ cộng dồn
# vào mọi project cũ (`backfill_exposure`), nên chúng luôn "bị chạm trong 12 giờ qua": không loại ra thì
# mỗi nhịp tim sau một ranh giới kêu CHẾT cho lô 1, 2, 3 (thấy ngay lần chạy thật đầu tiên, 23:2x).
FINISHED_STAGES = {"completed", "completed_with_errors"}


def stopped(versions: Path = Path(VERSIONS), now: float | None = None) -> list[str]:
    """Project bị chạm trong 12 giờ qua mà giờ ĐÃ CHẾT (`error`) hoặc ĐỨNG IM giữa chừng.

    Vì sao (18-09 23:0x): lô 7 chết lúc 22:41 ở bước phân vai, và nhịp tim 23:06 chỉ in "project đang
    bay: (không có)" - đúng về chữ, im về điều duy nhất cần biết. Một project không còn bị chạm trong 5
    phút thì rơi khỏi `flying()`, dù nó dừng vì xong, vì lỗi, hay vì máy tắt (19:24 cùng ngày). Mục này
    nói ra hai trường hợp sau, kèm lỗi và số phút.
    """
    now = time.time() if now is None else now
    out: list[str] = []
    for database in sorted(glob.glob(str(Path(versions) / "*" / "*" / "project.sqlite3"))):
        path = Path(database)
        idle = now - path.stat().st_mtime
        if idle <= TOUCHED_SECONDS or idle > STOPPED_WINDOW_SECONDS:
            continue
        connection = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
        try:
            status, stage, error = connection.execute(
                "SELECT status, stage, last_error FROM book"
            ).fetchone()
        except (sqlite3.Error, TypeError):
            continue
        finally:
            connection.close()
        if status in FINISHED_STATUSES or stage in FINISHED_STAGES:
            continue
        what = "CHẾT" if status == "error" else "ĐỨNG IM"
        out.append(
            f"{what} {path.parent.name}: {status}|{stage}, không ai chạm {idle / 60:.0f} phút"
            + (f" - {str(error)[:140]}" if error else "")
        )
    return out


def power_line() -> str | None:
    """Máy đang chạy PIN thì nói to; cắm sạc thì im.

    Ca thật 24-09: sạc rút lúc ~22:50, GPU bị hạ xuống 480 MHz / 15 W, phân tích tụt từ 56 xuống 3,8 tok/s,
    và nhịp tim 00:07 mới thấy - lúc pin còn 5%, Windows sắp ngủ đông. Một dòng ở mọi nhịp thì thấy ngay.
    `ctypes` thay vì PowerShell: nhanh và không mở tiến trình con.
    """
    if sys.platform != "win32":
        return None
    import ctypes

    class _Status(ctypes.Structure):
        _fields_ = [("ac", ctypes.c_ubyte), ("flag", ctypes.c_ubyte), ("percent", ctypes.c_ubyte),
                    ("saver", ctypes.c_ubyte), ("seconds", ctypes.c_ulong), ("full", ctypes.c_ulong)]

    status = _Status()
    if not ctypes.windll.kernel32.GetSystemPowerStatus(ctypes.byref(status)) or status.ac != 0:
        return None
    percent = "?" if status.percent == 255 else f"{status.percent}%"
    return f"!!! NGUỒN: ĐANG CHẠY PIN ({percent}) - GPU bị hạ xung, phân tích chậm ~15 lần; 2% thì Windows ngủ đông"


UPSTREAM_AUDIT = ROOT / "runtime" / "dependency_audit.json"
UPSTREAM_STALE_HOURS = 24.0


def upstream_line(audit: Path = UPSTREAM_AUDIT, now: float | None = None) -> str:
    """Lần kiểm thượng nguồn cuối cách đây bao lâu, và nó thấy gì - một dòng.

    Vì sao ở đây: `check_dependency_updates.py` nằm im 18 ngày (30-08 → 17-09) trong khi VieNeu ra
    16 bản, và chủ sách phải tự hỏi. Việc chạy nó là trách nhiệm thường trực (docs/DEPENDENCIES.md);
    một dòng đỏ ở MỌI nhịp tim khi đã quá 24 giờ thì không thể quên được nữa.
    """
    import json

    now = time.time() if now is None else now
    try:
        data = json.loads(audit.read_text(encoding="utf-8"))
        age_hours = (now - float(data["checked_at"])) / 3600.0
    except (OSError, ValueError, KeyError, TypeError):
        return "thượng nguồn: CHƯA TỪNG KIỂM - chạy scripts/check_dependency_updates.py"
    found = [*data.get("outdated_packages", []), *data.get("retagged_ollama_models", []),
             *data.get("hf_models_behind_main", []), *data.get("git_pins_behind", [])]
    summary = f"{len(found)} thứ có bản mới ({', '.join(found[:6])}{'…' if len(found) > 6 else ''})" if found else "không có gì mới"
    if age_hours > UPSTREAM_STALE_HOURS:
        return f"thượng nguồn: QUÁ {age_hours:.0f} GIỜ CHƯA KIỂM - chạy scripts/check_dependency_updates.py (lần trước: {summary})"
    return f"thượng nguồn: kiểm {age_hours:.1f} giờ trước - {summary}"


def main() -> int:
    say(f"=== nhịp tim {time.strftime('%H:%M:%S ngày %d-%m')} ===")
    power = power_line()
    if power:
        say(power)
    say(describe())
    procs = processes()
    roots = tree_roots(procs, r"boundary\.sh \d")
    say(f"tiến trình boundary.sh (gốc thật): {len(roots)}")
    for line in tree_roots(procs, r"launch_(repair|batch)\.sh \d"):
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
    dead = stopped()
    if dead:
        say("")
        say("!!! project CHẾT / ĐỨNG IM (bị chạm trong 12 giờ qua, không xong):")
        for line in dead:
            say(f"    {line}")
    say("")
    dirty = subprocess.run(
        ["git", "status", "--porcelain"], cwd=str(ROOT), capture_output=True, text=True
    ).stdout.strip()
    say(f"cây git: {'sạch' if not dirty else f'{len(dirty.splitlines())} file đổi'}")
    say(upstream_line())
    say(
        subprocess.run(
            ["git", "log", "--oneline", "-1"], cwd=str(ROOT), capture_output=True, text=True
        ).stdout.strip()
    )
    # Dấu thời gian để một canh nền biết nhịp tim có còn đập không: 18-09 01:0x nhịp chết vì tôi
    # quên thả lại lệnh nền, và chủ sách phải là người phát hiện. Không ai nên phải làm việc ấy.
    STAMP.parent.mkdir(parents=True, exist_ok=True)
    STAMP.write_text(time.strftime("%Y-%m-%d %H:%M:%S"), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
