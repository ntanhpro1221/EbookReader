"""Danh sách kiểm bắt buộc trước khi bắt đầu một lô, chạy tự động thay vì nhớ.

    python scripts/before_a_batch.py

Kỷ luật này ra đời từ một cái giá thật, 2026-09-08: lô 1 chạy 1 giờ 40, phân tích 1.406/3.727
đoạn, rồi chết vì một nửa cặp surrogate lạc. Vá xong thì `resume` bị worker từ chối — *"Analysis
implementation changed after analysis started; create a clean project"* — nên **toàn bộ 1,7 giờ
phân tích mất trắng**, không chỉ phần còn lại.

Với lô 13 giờ thì sửa giữa chừng đắt hơn nhiều so với kiểm 10 phút trước khi chạy. Nhưng một
kỷ luật chỉ ghi trong tài liệu là một kỷ luật phụ thuộc trí nhớ, nên nó nằm ở đây.

Chỉ đọc và chạy test; không sửa gì, không khởi động lô nào.
"""
from __future__ import annotations

import argparse
import os
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
VERSIONS = Path(r"D:\Novels\Audiobooks\_versions")
LEASE_STALE_SECONDS = 180.0


def _say(line: str) -> None:
    try:
        print(line)
    except (UnicodeEncodeError, OSError, ValueError):
        sys.stdout.buffer.write(line.encode("utf-8", "replace") + b"\n")


def _runs_in_flight() -> list[str]:
    """Lô nào đang bay. Đọc nhịp tim `worker_leases`, không đọc file khoá.

    Cùng ngưỡng và cùng lý do như `scripts/pending_patches/apply_all.py`: file khoá nằm lại
    sau khi tiến trình chết, nên một bộ canh dựa vào nó lúc nào cũng kêu.
    """
    if not VERSIONS.is_dir():
        return []
    now = time.time()
    live: list[str] = []
    for database in sorted(VERSIONS.glob("*/*/project.sqlite3")):
        try:
            connection = sqlite3.connect(f"file:{database}?mode=ro", uri=True)
            connection.row_factory = sqlite3.Row
            try:
                rows = connection.execute(
                    "SELECT worker_name, state, heartbeat_at FROM worker_leases"
                ).fetchall()
            finally:
                connection.close()
        except sqlite3.Error:
            continue
        for row in rows:
            if str(row["state"]) != "running":
                continue
            if now - float(row["heartbeat_at"] or 0.0) <= LEASE_STALE_SECONDS:
                live.append(str(database.parent))
    return live


def _pending_patches() -> list[str]:
    sys.path.insert(0, str(HERE / "pending_patches"))
    try:
        import apply_all  # noqa: PLC0415
    except Exception:  # noqa: BLE001
        return []
    return list(getattr(apply_all, "ORDER", ()))


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--skip-tests",
        action="store_true",
        help="Bỏ bộ test đầy đủ. Chỉ dùng khi vừa chạy nó xong.",
    )
    args = parser.parse_args(argv)

    problems: list[str] = []

    _say("=== 1. có lô nào đang bay không ===")
    live = _runs_in_flight()
    if live:
        for path in live:
            _say(f"   ĐANG CHẠY: {path}")
        problems.append("có lô đang bay - đừng bắt đầu lô mới, và đừng vá gì")
    else:
        _say("   không có.")

    _say("")
    _say("=== 2. cây git sạch chưa ===")
    status = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=str(ROOT.parent),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    dirty = [line for line in (status.stdout or "").splitlines() if line.strip()]
    if dirty:
        for line in dirty[:8]:
            _say(f"   {line}")
        problems.append(f"{len(dirty)} file chưa commit - lô chạy trên mã không truy lại được")
    else:
        _say("   sạch.")

    _say("")
    _say("=== 3. bản vá còn trong hàng chờ ===")
    pending = _pending_patches()
    if pending:
        for name in pending:
            _say(f"   CHỜ: {name}")
        problems.append(
            f"{len(pending)} bản vá chưa áp - áp bây giờ, giữa hai lô, chứ đừng giữa lô"
        )
    else:
        _say("   hàng chờ rỗng.")

    _say("")
    _say("=== 4. hợp đồng runtime (model đã ghim đúng chưa) ===")
    os.environ.setdefault("EBOOK_READER_RUNTIME", str(ROOT / "runtime"))
    sys.path.insert(0, str(ROOT))
    try:
        from ebook_reader.runtime_contract import voice_model_check  # noqa: PLC0415

        result = voice_model_check(Path(os.environ["EBOOK_READER_RUNTIME"]))
        _say(f"   {result['detail']}")
        if not result["ok"]:
            problems.append("model giọng không khớp revision đã ghim")
    except Exception as exc:  # noqa: BLE001
        _say(f"   không kiểm được: {exc}")
        problems.append("không chạy được kiểm model giọng")

    if not args.skip_tests:
        _say("")
        _say("=== 5. bộ test đầy đủ ===")
        tests = subprocess.run(
            [sys.executable, "-m", "pytest", "-o", "addopts=", "-q"],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        tail = (tests.stdout or "").strip().splitlines()[-1:] or ["(không có output)"]
        _say(f"   {tail[0]}")
        if tests.returncode != 0:
            problems.append("bộ test đỏ")

    _say("")
    if problems:
        _say("CHƯA CHẠY ĐƯỢC:")
        for item in problems:
            _say(f"  - {item}")
        return 1
    _say("Đủ điều kiện bắt đầu lô. Xem docs/PRODUCTION_PLAN.md cho dải chương và thứ tự gieo.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
