"""Hai chương cùng thời lượng chưa phải chép sai; hai chương cùng NỘI DUNG mới là.

`--verify` phàn nàn khi hai chương trùng thời lượng ở mức 0,01 giây, vì một bản chép sai sẽ
trùng khít. Nhưng nó cũng trùng khít khi chỉ là xác suất: sách cuốn 2 lúc 09:49 ngày 2026-09-15
có 98 chương, và cặp 050/086 trùng ở 0,01 giây — cùng 9.476.447 byte (MP3 CBR cùng thời lượng
thì cùng cỡ) nhưng **khác sha256**, khác `source_file`, hai chương nguồn khác nhau hẳn. Với 915
chương ~6 phút, trùng ở mức 10 ms là chuyện thường, và một lời phàn nàn kêu suốt là một lời
phàn nàn bị bỏ qua đúng lúc nó cần được tin.

Nên phép kiểm hỏi thêm một câu, chỉ cho những file đã trùng thời lượng: nội dung có giống nhau
không? Bài này giữ cả hai nửa của câu trả lời.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from ebook_reader.io_utils import ffmpeg_executable, run_hidden
from scripts.assemble_book import verify


def _tone(path: Path, *, seconds: float, frequency: int) -> None:
    """Một file MP3 thật, vì `verify` gọi `ffprobe` chứ không tin phần mở rộng tên file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    run_hidden(
        [
            ffmpeg_executable(), "-y", "-f", "lavfi",
            "-i", f"sine=frequency={frequency}:duration={seconds}",
            "-ac", "1", "-ar", "24000", "-b:a", "128k", str(path),
        ],
        timeout=120.0,
    )


def _book(tmp_path: Path, pairs: list[tuple[str, int]], *, seconds: float) -> Path:
    """Sách gồm các chương (tiêu đề, tần số) — cùng thời lượng, nội dung theo tần số."""
    out = tmp_path / "book"
    versions = tmp_path / "_versions"
    chapters = []
    for index, (title, frequency) in enumerate(pairs, 1):
        source = versions / "v0.9.0-lo01" / "lo01_x" / "output" / "chapters" / f"{index:05d}_{title}.mp3"
        _tone(source, seconds=seconds, frequency=frequency)
        destination = out / f"{title}.mp3"
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(source.read_bytes())
        chapters.append(
            {
                "title": title,
                "file": destination.name,
                "version": "v0.9.0-lo01",
                "project": "lo01_x",
                "source_file": source.name,
                "bytes": destination.stat().st_size,
            }
        )
    (out / "manifest.json").write_text(
        json.dumps({"chapters": chapters}, ensure_ascii=False), encoding="utf-8"
    )
    return out, versions


@pytest.fixture(autouse=True)
def _versions_root(monkeypatch):
    """`verify` đọc project gốc qua `VERSIONS`; trỏ nó vào cây tạm của bài test."""
    yield


def test_two_chapters_of_equal_length_but_different_sound_are_not_a_complaint(
    tmp_path: Path, monkeypatch
) -> None:
    out, versions = _book(tmp_path, [("050", 440), ("086", 660)], seconds=1.0)
    monkeypatch.setattr("scripts.assemble_book.VERSIONS", versions)

    checked, complaints = verify(out)

    assert checked == 2
    assert complaints == [], complaints


def test_the_same_audio_in_two_slots_is_still_caught(tmp_path: Path, monkeypatch) -> None:
    out, versions = _book(tmp_path, [("050", 440), ("086", 440)], seconds=1.0)
    monkeypatch.setattr("scripts.assemble_book.VERSIONS", versions)
    # Chép sai thật: cùng một file nằm ở hai chỗ.
    (out / "086.mp3").write_bytes((out / "050.mp3").read_bytes())

    _checked, complaints = verify(out)

    assert any("CHÉP SAI CHƯƠNG" in line and "050" in line and "086" in line for line in complaints), (
        complaints
    )
