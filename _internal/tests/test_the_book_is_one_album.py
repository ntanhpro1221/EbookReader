"""Cuốn sách phải là MỘT đĩa, và số track phải là số chương thật.

Đo 01:30 ngày 2026-09-12 trên sách 118 chương đã ghép: `album` mang **38** giá trị khác nhau, mỗi
giá trị là slug của project (`lo01b`, `lo03r_060`), và `track` là số thứ tự trong project nên 36
file cùng mang `track=1`. Máy nghe nhạc sắp theo thẻ sẽ thấy 38 "đĩa" và trộn thứ tự chương; sách
chỉ nghe đúng nếu người nghe sắp theo tên file. Không cổng nào của dự án nhìn vào thẻ.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from ebook_reader.io_utils import ffmpeg_executable, run_hidden
from scripts.assemble_book import (
    DEFAULT_ALBUM,
    copy_needed,
    previous_manifest,
    retag,
    retag_needed,
    wanted_tags,
)


def test_the_whole_book_is_one_album_numbered_by_real_chapter() -> None:
    first = wanted_tags("000", "Truyện thử", 478)
    later = wanted_tags("118", "Truyện thử", 478)

    assert first["album"] == later["album"] == "Truyện thử", "một đĩa, không phải 38"
    assert (first["track"], later["track"]) == ("0/478", "118/478")
    assert (first["title"], later["title"]) == ("000", "118")


def test_without_a_source_count_the_track_is_still_the_chapter() -> None:
    assert wanted_tags("007", "X", 0)["track"] == "7"


def test_the_placeholder_album_is_not_a_project_slug() -> None:
    """Tên thật của truyện không có trong dữ liệu; chỗ giữ chỗ phải rõ là chỗ giữ chỗ."""
    assert DEFAULT_ALBUM and not DEFAULT_ALBUM.startswith("lo")


def test_copying_is_decided_by_provenance_not_by_the_size_on_disk(tmp_path: Path) -> None:
    """Ghi thẻ đổi kích thước file đích; luật cũ sẽ chép lại cả cuốn sách mỗi lần ghép."""
    destination = tmp_path / "000.mp3"
    destination.write_bytes(b"x" * 100)
    item = {"version": "v0.2.0-lo01", "project": "lo01b_x", "bytes": 90}
    same = {"version": "v0.2.0-lo01", "project": "lo01b_x", "bytes": 90}

    assert copy_needed(destination, item, same) is False, "cùng gốc gác thì không chép lại"
    assert copy_needed(destination, item, None) is True, "chưa có manifest thì chép"
    assert copy_needed(destination, item, {**same, "project": "lo01r_000_x"}) is True
    assert copy_needed(destination, item, {**same, "bytes": 91}) is True
    assert copy_needed(tmp_path / "khong-co.mp3", item, same) is True


def test_a_freshly_copied_chapter_is_always_retagged() -> None:
    want = wanted_tags("005", "Truyện thử", 478)

    assert retag_needed(True, want, {"tags": want}) is True, "bản vừa chép mang thẻ của lô"
    assert retag_needed(False, want, {"tags": want}) is False
    assert retag_needed(False, want, {"tags": {**want, "album": "lo01b"}}) is True
    assert retag_needed(False, want, {}) is True, "manifest cũ chưa ghi thẻ - phải ghi lại"
    assert retag_needed(False, want, None) is True


def test_previous_manifest_reads_both_shapes(tmp_path: Path) -> None:
    (tmp_path / "manifest.json").write_text(
        json.dumps({"chapters": [{"title": "000", "bytes": 7}]}), encoding="utf-8"
    )
    assert previous_manifest(tmp_path)["000"]["bytes"] == 7

    (tmp_path / "manifest.json").write_text(json.dumps([{"title": "001"}]), encoding="utf-8")
    assert set(previous_manifest(tmp_path)) == {"001"}

    assert previous_manifest(tmp_path / "nowhere") == {}


def test_retagging_a_real_mp3_keeps_the_audio_and_changes_the_tags(tmp_path: Path) -> None:
    """Chạy ffmpeg thật: `-c copy` không được đổi một mẫu nào của audio."""
    ffmpeg = ffmpeg_executable()
    source = tmp_path / "chapter.mp3"
    try:
        run_hidden(
            [
                ffmpeg, "-v", "error", "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=1",
                "-metadata", "album=lo01b", "-metadata", "track=1", str(source),
            ],
            timeout=120.0,
        )
    except Exception as exc:  # noqa: BLE001 - máy không có ffmpeg thì bỏ qua, có nói lý do
        pytest.skip(f"không chạy được ffmpeg: {exc}")
    before_audio = _decoded(tmp_path, source, "before.pcm")

    assert retag(source, wanted_tags("042", "Truyện thử", 478)) is True

    after_audio = _decoded(tmp_path, source, "after.pcm")
    assert after_audio == before_audio, "`-c copy` phải giữ nguyên từng mẫu"
    raw = source.read_bytes()
    assert b"Truy\xe1\xbb\x87n th\xe1\xbb\xad" in raw or b"Truy" in raw
    assert not (tmp_path / "chapter.retag.mp3").exists(), "file tạm phải được thay vào chỗ"


def _decoded(tmp_path: Path, source: Path, name: str) -> bytes:
    out = tmp_path / name
    run_hidden(
        [ffmpeg_executable(), "-v", "error", "-y", "-i", str(source), "-f", "s16le", str(out)],
        timeout=120.0,
    )
    return out.read_bytes()


def test_a_tag_failure_does_not_raise(tmp_path: Path) -> None:
    """Thẻ sai thì audio vẫn đúng; một lỗi ghi thẻ không được làm chết bước ghép sách."""
    missing = tmp_path / "khong-co.mp3"

    assert retag(missing, {"album": "X"}) is False
    assert not (tmp_path / "khong-co.retag.mp3").exists()


def test_verify_says_what_is_wrong_and_what_it_could_not_check(tmp_path: Path) -> None:
    """`--verify` trả lời "cuốn sách có đúng là thứ manifest nói không", và nói cả khi không đo được.

    Manifest ghi gốc gác nhưng chưa ai kiểm rằng file trong sách thật là chương ấy. Một lần chép
    sai, hay một project bị xoá sau khi ghép, đều im lặng: tên file đúng, thẻ đúng, người nghe
    mới là người phát hiện.
    """
    from scripts.assemble_book import verify

    checked, complaints = verify(tmp_path / "nowhere")
    assert checked == 0 and "manifest" in complaints[0]

    (tmp_path / "manifest.json").write_text(
        json.dumps(
            {
                "chapters": [
                    {
                        "title": "000",
                        "file": "000.mp3",
                        "version": "v0.2.0-lo01",
                        "project": "khong-co-project",
                        "source_file": "00001_000.mp3",
                        "bytes": 10,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    checked, complaints = verify(tmp_path)

    assert checked == 0
    assert len(complaints) == 1
    assert "thiếu 000.mp3" in complaints[0] or "ffprobe" in complaints[0]
