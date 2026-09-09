from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import time
import unicodedata
from pathlib import Path
from typing import Any, Iterable


def natural_key(value: str) -> list[Any]:
    return [int(part) if part.isdigit() else part.casefold() for part in re.split(r"(\d+)", value)]


def discover_txt_files(directory: Path) -> list[Path]:
    """Return direct child TXT files in deterministic natural order.

    Folder import is intentionally non-recursive so selecting a book folder cannot
    silently pull unrelated TXT files from nested metadata, backup, or output folders.
    """
    directory = directory.expanduser().resolve()
    if not directory.exists():
        raise FileNotFoundError(directory)
    if not directory.is_dir():
        raise NotADirectoryError(directory)
    return sorted(
        (path.resolve() for path in directory.iterdir() if path.is_file() and path.suffix.casefold() == ".txt"),
        key=lambda path: natural_key(path.name),
    )


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


LONE_SURROGATE_PATTERN = re.compile("[\ud800-\udfff]")


def strip_lone_surrogates(text: str) -> str:
    """Bỏ những code point là **một nửa** của cặp surrogate.

    Đặt ở đây chứ không ở `analysis.py` vì đã có **hai** nguồn cần nó: phản hồi Ollama và
    transcript của Whisper. Cả hai là văn bản do model sinh ra, và cả hai đều tạo ra được một
    `str` hợp lệ trong bộ nhớ mà **không mã hoá UTF-8 được** - thứ giết lô 1 ngày 2026-09-08
    ngay dưới đây ở `sha256_text`, và cũng bị chính sqlite từ chối lúc `INSERT`.

    Xoá đúng khoảng D800-DFFF: mọi cặp hợp lệ đã được bộ giải mã ghép thành ký tự thật, nên
    thứ còn sót trong khoảng ấy chắc chắn là nửa lạc.
    """
    return LONE_SURROGATE_PATTERN.sub("", text)


def sha256_text(text: str) -> str:
    return sha256_bytes(text.encode("utf-8"))


def sha256_file(path: Path, block_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(block_size):
            digest.update(chunk)
    return digest.hexdigest()


def stable_int(text: str, low: int = 1, high: int = 2_147_483_000) -> int:
    if high <= low:
        return low
    value = int(hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()[:16], 16)
    return low + (value % (high - low))


def slugify(text: str, max_length: int = 90) -> str:
    import unicodedata

    text = text.replace("đ", "d").replace("Đ", "D")
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"[^A-Za-z0-9._-]+", "_", text).strip("._-")
    return (text[:max_length] or "item").lower()


def decode_text_bytes(raw: bytes) -> str:
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        return unicodedata.normalize("NFC", raw.decode("utf-16"))

    encodings = ["utf-8-sig", "utf-8", "cp1258", "windows-1252"]
    if raw:
        even_nuls = raw[0::2].count(0)
        odd_nuls = raw[1::2].count(0)
        nul_ratio = (even_nuls + odd_nuls) / len(raw)
        if nul_ratio >= 0.2:
            utf16_encoding = "utf-16-be" if even_nuls > odd_nuls else "utf-16-le"
            encodings.insert(0, utf16_encoding)

    for encoding in encodings:
        try:
            text = raw.decode(encoding)
            if "�" not in text:
                return unicodedata.normalize("NFC", text)
        except UnicodeDecodeError:
            continue
    return unicodedata.normalize("NFC", raw.decode("utf-8", errors="replace"))


REPLACE_RETRY_ATTEMPTS = 12
REPLACE_RETRY_DELAY_SECONDS = 0.05


def _replace_with_retry(temp: Path, path: Path) -> None:
    """os.replace, but survive a reader holding the destination open.

    On Windows a rename onto an open file fails with PermissionError (WinError 5), and
    every reader of these files opens them the ordinary way - so *reading* a state file can
    break the process writing it. It is not hypothetical: alpha.50 died 44 minutes into its
    analysis on

        PermissionError: [WinError 5] Access is denied:
        'runtime/background/state.json.part' -> 'runtime/background/state.json'

    because a script was polling that state file every 15 seconds. `cli status` reads the
    same file, so a person checking on their own run could have done it just as easily.

    The window is microseconds wide, so retrying briefly closes it: twelve attempts across
    about 0.6s. If it still fails the error is raised unchanged, because a rename that is
    blocked for that long is not this race.
    """
    for attempt in range(REPLACE_RETRY_ATTEMPTS):
        try:
            os.replace(temp, path)
            return
        except PermissionError:
            if attempt == REPLACE_RETRY_ATTEMPTS - 1:
                raise
            time.sleep(REPLACE_RETRY_DELAY_SECONDS)


def atomic_write_bytes(path: Path, data: bytes, *, fsync: bool = True) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".part")
    with temp.open("wb") as handle:
        handle.write(data)
        handle.flush()
        if fsync:
            os.fsync(handle.fileno())
    _replace_with_retry(temp, path)


def atomic_write_json(path: Path, data: Any, *, fsync: bool = True) -> None:
    payload = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
    atomic_write_bytes(path, payload, fsync=fsync)


def atomic_write_text(path: Path, text: str, *, fsync: bool = True) -> None:
    atomic_write_bytes(path, text.encode("utf-8"), fsync=fsync)


def remove_part_files(
    root: Path,
    *,
    excluded_roots: Iterable[Path] = (),
) -> list[Path]:
    removed: list[Path] = []
    if not root.exists():
        return removed
    excluded = tuple(path.resolve() for path in excluded_roots)

    def is_excluded(path: Path) -> bool:
        resolved = path.resolve()
        return any(resolved == item or resolved.is_relative_to(item) for item in excluded)

    for path in root.rglob("*.part"):
        if is_excluded(path):
            continue
        try:
            path.unlink()
            removed.append(path)
        except OSError:
            pass
    for path in root.rglob("*.part.*"):
        if is_excluded(path):
            continue
        try:
            path.unlink()
            removed.append(path)
        except OSError:
            pass
    return removed


def ffmpeg_executable() -> str:
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return "ffmpeg.exe" if os.name == "nt" else "ffmpeg"


def run_hidden(command: Iterable[str], *, timeout: float | None = None, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(command),
        capture_output=True,
        text=True,
        timeout=timeout,
        check=check,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0,
    )
