"""Hai chuông của nhịp tim - phần dùng chung. A: `heartbeat_event.py`, B: `heartbeat_timeout.py`.

Chủ sách, 26-09 09:2x: *"đặt heartbeat 2 tiếng thì sẽ bỏ lỡ những lúc máy tính đã hoàn thành công việc nhưng
phải chờ 1 đến 2 tiếng thì heartbeat mới kích hoạt"*. Đúng sáng hôm ấy: ranh giới 17 xong lúc 08:47 (thả lô 18),
nhịp 2 tiếng chỉ thức lúc 09:43. Nên nhịp tim tách làm hai chuông chạy song song:

- **A** reo đúng lúc máy làm xong việc tôi giao (hoặc hỏng giữa chừng) - theo sự kiện, không theo giờ;
- **B** reo khi đã N giờ mà A không reo - *"cái heartbeat B sẽ đóng vai trò như một cái timeout trigger"*.
  Mỗi lần A reo và tôi xử lý xong, B đếm lại từ đầu.

Cả hai là lệnh nền của phiên (Bash `run_in_background`), nên việc chúng THOÁT là thứ đánh thức phiên. Trạng thái
nằm ở `runtime/heartbeat_event.json` và `runtime/heartbeat_timeout.json`, để `heartbeat_tick.py` - kể cả bản
daemon chạy mỗi 30 phút - nói được chuông nào còn canh.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "runtime"
EVENT_STATE = RUNTIME / "heartbeat_event.json"
TIMEOUT_STATE = RUNTIME / "heartbeat_timeout.json"
# Chạm file này = B đếm lại từ đầu. TÔI chạm nó sau khi xử lý xong một lần A reo, chứ A không tự chạm lúc reo:
# nếu thông báo của A lạc (22-09 đã lạc một lần, 07:50 -> 08:48) thì B vẫn phải reo đúng hẹn cũ.
TIMEOUT_RESET = RUNTIME / "heartbeat_timeout.reset"

EVENT_MARKER = "heartbeat_event.py"
TIMEOUT_MARKER = "heartbeat_timeout.py"
# A dò mỗi 60 giây; im quá 10 phút thì nó treo, dù tiến trình còn đó.
EVENT_STALE_SECONDS = 600.0


def write_state(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(temporary, path)


def read_state(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def alive(pid: object, marker: str) -> bool:
    """Tiến trình `pid` còn sống VÀ đúng là script `marker` - pid bị Windows cấp lại cho ai khác thì không tính.

    Không dùng `os.kill(pid, 0)`: trên Windows lệnh ấy gọi TerminateProcess - nó giết chứ không hỏi.
    """
    try:
        import psutil

        return any(marker in part for part in psutil.Process(int(pid)).cmdline())
    except Exception:  # noqa: BLE001 - NoSuchProcess, AccessDenied, pid rác: đều là "không sống"
        return False


def claim(path: Path, marker: str, extra: dict) -> dict | None:
    """Nhận làm chuông này. Đã có một chuông cùng loại đang sống thì trả về trạng thái của nó và KHÔNG ghi gì -
    hai chuông A cùng canh thì mỗi sự kiện reo hai lần."""
    current = read_state(path)
    if current and current.get("pid") != os.getpid() and alive(current.get("pid"), marker):
        return current
    write_state(path, {"pid": os.getpid(), "started_at": time.time(), **extra})
    return None


def release(path: Path) -> None:
    current = read_state(path)
    if current and current.get("pid") == os.getpid():
        try:
            path.unlink()
        except OSError:
            pass


def reset_mtime(path: Path = TIMEOUT_RESET) -> float | None:
    try:
        return path.stat().st_mtime
    except OSError:
        return None


def timeout_deadline(started_at: float, hours: float, reset_at: float | None) -> float:
    """B reo `hours` giờ sau mốc muộn hơn trong hai mốc: lúc B bắt đầu, lúc B được đặt lại lần cuối."""
    return max(started_at, reset_at or 0.0) + hours * 3600.0


def describe(now: float | None = None) -> str:
    """Một dòng cho nhịp tim: hai chuông có còn canh không, và B hẹn reo lúc nào."""
    now = time.time() if now is None else now
    event = read_state(EVENT_STATE)
    if event and alive(event.get("pid"), EVENT_MARKER):
        age = now - float(event.get("last_poll") or event.get("started_at") or now)
        a = f"A canh (dò {age:.0f}s trước)" if age <= EVENT_STALE_SECONDS else f"A TREO (dò cuối {age / 60:.0f} phút trước)"
    else:
        a = "A KHÔNG CHẠY"
    timeout = read_state(TIMEOUT_STATE)
    if timeout and alive(timeout.get("pid"), TIMEOUT_MARKER):
        deadline = timeout_deadline(float(timeout["started_at"]), float(timeout["hours"]), reset_mtime())
        b = f"B reo lúc {time.strftime('%H:%M %d-%m', time.localtime(deadline))}"
    else:
        b = "B KHÔNG CHẠY"
    return f"chuông: {a} | {b}"
