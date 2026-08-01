from __future__ import annotations

from pathlib import Path

import pytest

from e_book_reader.io_utils import decode_text_bytes, sha256_file
from e_book_reader.text_processing import build_chapter_manifest, load_and_segment_chapter


def test_cp1258_is_not_misdecoded_as_utf16() -> None:
    text = "Tôi đọc truyện Việt Nam."
    raw = text.encode("cp1258")

    assert decode_text_bytes(raw) == "Tôi đọc truyện Việt Nam."


def test_utf16_without_bom_uses_nul_heuristic() -> None:
    text = "Một chương truyện tiếng Việt."

    assert decode_text_bytes(text.encode("utf-16-le")) == text


def test_segmentation_rejects_same_size_source_mutation(tmp_path: Path) -> None:
    source = tmp_path / "chapter.txt"
    source.write_text("AAAA", encoding="utf-8")
    chapter = build_chapter_manifest([source], tmp_path / "out")[0]
    assert chapter["input_sha256"] == sha256_file(source)

    source.write_text("BBBB", encoding="utf-8")

    with pytest.raises(RuntimeError, match="changed while it was being loaded"):
        load_and_segment_chapter(chapter, max_chars=340)


def test_output_filename_is_sanitized_and_bounded(tmp_path: Path) -> None:
    source = tmp_path / ("Chương: Một? " + "rất-dài-" * 20 + ".txt")
    source.write_text("Nội dung", encoding="utf-8")

    output = Path(build_chapter_manifest([source], tmp_path / "out")[0]["output_mp3"])

    assert len(output.name) <= 82
    assert ":" not in output.name
    assert "?" not in output.name
