from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
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


def atomic_write_bytes(path: Path, data: bytes, *, fsync: bool = True) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".part")
    with temp.open("wb") as handle:
        handle.write(data)
        handle.flush()
        if fsync:
            os.fsync(handle.fileno())
    os.replace(temp, path)


def atomic_write_json(path: Path, data: Any, *, fsync: bool = True) -> None:
    payload = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
    atomic_write_bytes(path, payload, fsync=fsync)


def atomic_write_text(path: Path, text: str, *, fsync: bool = True) -> None:
    atomic_write_bytes(path, text.encode("utf-8"), fsync=fsync)


def remove_part_files(root: Path) -> list[Path]:
    removed: list[Path] = []
    if not root.exists():
        return removed
    for path in root.rglob("*.part"):
        try:
            path.unlink()
            removed.append(path)
        except OSError:
            pass
    for path in root.rglob("*.part.*"):
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
