"""Xuất sách ra một thư mục MP3 nghe được bằng MỌI trình phát (điện thoại, xe hơi, Voice, Smart AudioBook Player...).

MP3 chương do dây chuyền ghi mang tag của nội bộ sản xuất: album là tên project của lô ("lo16"), title là tên file
nguồn ("645"). Mở bằng trình phát khác thì thấy sách "lo16" với các chương "645", "646" (thử 26-09 trên Voice). Code
ghi MP3 nằm trong các file bị khoá của dây chuyền, nên sửa ở đây: chép nguyên luồng âm thanh (không mã hoá lại - nhanh,
không mất chất lượng) sang thư mục mới với tag đúng - tên sách, tên chương thật, giọng kể, số thứ tự, ảnh bìa - kèm
danh sách phát `.m3u8`. File chưa xong ghi ra `.part` rồi mới đổi tên, như mọi file âm thanh khác của dự án.
"""
from __future__ import annotations

import base64
import os
import re
from pathlib import Path
from typing import Any

from ..io_utils import ffmpeg_executable, run_hidden
from . import listen_view, store

_UNSAFE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def safe_name(text: str, limit: int = 120) -> str:
    """Tên file hợp lệ trên Windows, giữ nguyên chữ tiếng Việt."""
    cleaned = _UNSAFE.sub(" ", text).strip().strip(".")
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned[:limit].rstrip() or "Sach"


def _cover_file(folder: Path, cover: str | None) -> Path | None:
    """Ảnh bìa gửi từ giao diện (data URL PNG do trình duyệt vẽ, cùng kiểu bìa trong app)."""
    match = re.fullmatch(r"data:image/png;base64,([A-Za-z0-9+/=]+)", cover or "")
    if not match:
        return None
    data = base64.b64decode(match.group(1))
    if not data.startswith(b"\x89PNG") or len(data) > 4 * 1024 * 1024:
        return None
    path = folder / "cover.png"
    path.write_bytes(data)
    return path


def export_book(project_root: Path, target_root: Path, *, cover: str | None = None) -> dict[str, Any]:
    summary = store.summarize(project_root)
    title = summary["title"] or project_root.name
    narrator = summary["settings"]["narrator"] or ""
    chapters = [chapter for chapter in listen_view.chapters(project_root) if chapter["available"]]
    if not chapters:
        raise ValueError("Sách chưa có chương nào nghe được để xuất")
    folder = target_root / safe_name(title)
    folder.mkdir(parents=True, exist_ok=True)
    cover_path = _cover_file(folder, cover)
    ffmpeg = ffmpeg_executable()
    total = len(chapters)
    width = max(2, len(str(total)))
    playlist = ["#EXTM3U", f"#PLAYLIST:{title}"]
    written: list[str] = []
    for number, chapter in enumerate(chapters, start=1):
        source = store.chapter_audio_path(project_root, chapter["id"])
        if source is None:
            continue
        name = f"{number:0{width}d} - {safe_name(chapter['fullTitle'], 90)}.mp3"
        final = folder / name
        partial = folder / f"{name}.part"
        command = [ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-i", str(source)]
        if cover_path:
            command += ["-i", str(cover_path), "-map", "0:a", "-map", "1:v", "-c:v", "copy",
                        "-disposition:v", "attached_pic", "-metadata:s:v", "title=Album cover",
                        "-metadata:s:v", "comment=Cover (front)"]
        else:
            command += ["-map", "0:a"]
        command += [
            "-c:a", "copy", "-map_metadata", "-1", "-id3v2_version", "3", "-write_id3v1", "1",
            "-metadata", f"title={chapter['fullTitle']}",
            "-metadata", f"album={title}",
            "-metadata", f"artist={narrator}",
            "-metadata", f"album_artist={narrator}",
            "-metadata", f"track={number}/{total}",
            "-metadata", "genre=Audiobook",
            "-f", "mp3", str(partial),
        ]
        run_hidden(command, timeout=300)
        os.replace(partial, final)
        written.append(name)
        playlist += [f"#EXTINF:{int(round(chapter['duration']))},{chapter['fullTitle']}", name]
    (folder / f"{safe_name(title)}.m3u8").write_text("\n".join(playlist) + "\n", encoding="utf-8")
    return {"folder": str(folder), "files": len(written), "chaptersTotal": summary["chapters"]["total"]}
