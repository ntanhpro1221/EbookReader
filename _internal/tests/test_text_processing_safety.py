from __future__ import annotations

from pathlib import Path

import pytest

from ebook_reader.io_utils import decode_text_bytes, sha256_file
from ebook_reader.text_processing import (
    TEXT_SFX_KIND,
    VOCAL_EFFECT_KIND,
    build_chapter_manifest,
    load_and_segment_chapter,
    segment_chapter_text,
)


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


def test_inline_quoted_terms_remain_one_narration_segment() -> None:
    text = 'Lucien nghĩ đến những từ như “cơ duyên”, “kho báu”, “sổ tay ma thuật”.'

    rows = segment_chapter_text(1, text)

    assert [row["text"] for row in rows] == [text]
    assert [row["kind_hint"] for row in rows] == ["narration"]


def test_direct_speech_is_separated_from_narration() -> None:
    rows = segment_chapter_text(1, 'Cô hỏi: “Anh có khỏe không?”')

    assert [row["text"] for row in rows] == ["Cô hỏi:", "“Anh có khỏe không?”"]
    assert [row["kind_hint"] for row in rows] == ["narration", "dialogue"]


def test_multiline_dialogue_and_inner_thought_keep_their_kind() -> None:
    text = (
        "Cô ta nguyền rủa:\n\n"
        "“Từ trong biển lửa, ta sẽ chứng kiến thiên quốc sụp đổ.\n\n"
        "Ta sẽ chứng kiến giáo đường tan nát.\n\n"
        "Các ngươi sẽ vĩnh viễn trầm luân!”\n\n"
        "‘Đây không phải thế giới cũ…’"
    )

    rows = segment_chapter_text(1, text)

    assert [row["kind_hint"] for row in rows] == [
        "narration",
        "dialogue",
        "dialogue",
        "dialogue",
        "thought",
    ]


def test_multiline_ascii_quotes_keep_dialogue_state() -> None:
    rows = segment_chapter_text(
        1,
        'Cô ta nói: "Câu đầu.\n\nCâu tiếp theo.\n\nCâu cuối."\n\nLời kể.',
    )

    assert [row["kind_hint"] for row in rows] == [
        "narration",
        "dialogue",
        "dialogue",
        "dialogue",
        "narration",
    ]


def test_inline_curly_single_quote_is_an_inner_thought() -> None:
    rows = segment_chapter_text(1, "Hạ Phong không khỏi nghĩ: ‘Mình phải rời khỏi đây.’")

    assert [row["kind_hint"] for row in rows] == ["narration", "thought"]


def test_punctuation_only_content_never_becomes_tts_segment() -> None:
    rows = segment_chapter_text(1, "Một câu kể.\n…\n,\nMột câu khác.")

    assert [row["text"] for row in rows] == ["Một câu kể.", "Một câu khác."]
    assert all(any(char.isalnum() for char in row["text"]) for row in rows)
    assert segment_chapter_text(1, "…\n,\n.") == []


def test_standalone_vocalizations_become_vocal_effect_segments() -> None:
    rows = segment_chapter_text(1, '“Ha…”\n“Ha ha ha...”\n“Haiz…”\n“Hầy...”\n“Hừm...”\n“Khụ khụ...”\n“Ha?”')

    assert [row["kind_hint"] for row in rows] == [
        VOCAL_EFFECT_KIND,
        VOCAL_EFFECT_KIND,
        VOCAL_EFFECT_KIND,
        VOCAL_EFFECT_KIND,
        VOCAL_EFFECT_KIND,
        VOCAL_EFFECT_KIND,
        "dialogue",
    ]


def test_inline_effect_and_text_sfx_are_split_into_independent_segments() -> None:
    rows = segment_chapter_text(1, '— [cười] Ta thắng rồi!\n\nRầm! Cánh cửa bật mở.')

    assert [(row["text"], row["kind_hint"]) for row in rows] == [
        ("[cười]", VOCAL_EFFECT_KIND),
        ("Ta thắng rồi!", "dialogue"),
        ("Rầm!", TEXT_SFX_KIND),
        ("Cánh cửa bật mở.", "narration"),
    ]
