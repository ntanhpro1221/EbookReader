"""Chạy server giao diện độc lập - để phát triển frontend trong trình duyệt, không cần cửa sổ Qt.

    python -m ebook_reader.webui --dev --port 8765 --library <thư mục thư viện> --preferences <file.json>

`--dev` bỏ mã phiên (Vite proxy không mang được nó) và dùng bộ chạy giả, nên bấm "Bắt đầu" không khởi động
worker thật. `--real-runner` bật lại worker thật; `--read-only` khoá mọi thao tác ghi.
"""
from __future__ import annotations

import argparse
import sys
import threading
from pathlib import Path

from . import actions
from .library import Preferences
from .server import App, Server, new_token


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m ebook_reader.webui")
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--library", type=Path, default=None)
    parser.add_argument("--preferences", type=Path, default=None)
    parser.add_argument("--dev", action="store_true")
    parser.add_argument("--real-runner", action="store_true")
    parser.add_argument("--read-only", action="store_true")
    parser.add_argument("--sync-host", default=None, help="bật đồng bộ điện thoại, chỉ nghe địa chỉ này (dev: 127.0.0.1)")
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    preferences = Preferences(args.preferences)
    if args.library is not None:
        preferences.update({"libraryRoot": str(args.library.resolve())})
    runner: actions.Runner = actions.BackgroundRunner() if args.real_runner or not args.dev else actions.FakeRunner()
    app = App(
        preferences=preferences,
        runner=runner,
        token=None if args.dev else new_token(),
        read_only=args.read_only,
        version="dev" if args.dev else "",
    )
    if args.sync_host:
        app.sync_host = args.sync_host
        app.set_sync(True)
    server = Server(app, port=args.port).start()
    print(f"Ebook Reader UI: {server.url}  (thư viện: {preferences.get()['libraryRoot']})", flush=True)
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        server.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
