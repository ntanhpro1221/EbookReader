from __future__ import annotations

from pathlib import Path

import pytest

from ebook_reader.io_utils import decode_text_bytes, sha256_file
from ebook_reader.text_processing import (
    build_chapter_manifest,
    is_vocalization_only,
    load_and_segment_chapter,
    normalize_vocalizations_for_tts,
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


def test_chapter_031_mismatched_thought_closer_does_not_run_into_narration() -> None:
    text = (
        "‘Mình cần phải dừng phản ứng ma thuật lại đúng lúc lưu huỳnh cháy.\n\n"
        "‘Ghi chép có đề cập rằng nó sẽ gây phản phệ, thậm chí còn tệ hơn.”\n\n"
        "Phân tích cấu trúc của phép thuật, Lucien chỉ giữ lại lửa lưu huỳnh.\n\n"
        "“Lùi lại!”"
    )

    rows = segment_chapter_text(32, text)

    assert [row["kind_hint"] for row in rows] == [
        "thought",
        "thought",
        "narration",
        "dialogue",
    ]


def test_chapter_091_nested_unclosed_thought_stays_inside_outer_dialogue() -> None:
    text = (
        "Ilia tiếp tục nói: “Ngân Bạch Chi Chủ cho ta một mặc khải. "
        "‘Một ngôi sao rơi xuống mang đến hỗn loạn. Kẻ vô thần sẽ bước lên vũ đài hoa lệ.”\n\n"
        "“Mặc khải này có ý gì?” Dragan hỏi.\n\n"
        "Sau đó mọi người im lặng."
    )

    rows = segment_chapter_text(92, text)

    later_rows = [row for row in rows if int(row["paragraph_index"]) > 0]
    assert all(row["kind_hint"] != "thought" for row in rows)
    assert any(
        row["kind_hint"] == "dialogue" and "Một ngôi sao" in str(row["text"])
        for row in rows
    )
    assert [row["kind_hint"] for row in later_rows] == [
        "dialogue",
        "narration",
        "narration",
    ]


def test_unclosed_ascii_quote_nested_in_balanced_dialogue_does_not_escape() -> None:
    rows = segment_chapter_text(
        1,
        'Ilia nói: “Ông ấy gọi nó là "Arcana.”\n\nĐây là lời kể tiếp theo.',
    )

    assert rows[-1]["kind_hint"] == "narration"


@pytest.mark.parametrize(
    ("malformed_quote", "expected_kind"),
    [
        ("‘Tiệc tùng rồi lại tiệc tùng!”", "thought"),
        ('“Aha! Tôi nghe rõ lắm đấy! "Để xem điều gì sẽ xảy ra."', "dialogue"),
        (
            "‘Căn nhà gỗ ở phía Tây…” Lucien tra cứu bản đồ. “Nó nằm trong rừng!’",
            "thought",
        ),
    ],
)
def test_terminal_mismatched_quote_marks_do_not_open_cross_paragraph_state(
    malformed_quote: str,
    expected_kind: str,
) -> None:
    rows = segment_chapter_text(
        1,
        f"{malformed_quote}\n\nĐây là lời kể ở đoạn tiếp theo.",
    )

    assert rows[0]["kind_hint"] == expected_kind
    assert rows[-1]["kind_hint"] == "narration"


def test_unclosed_quote_state_fails_closed_at_chapter_boundary() -> None:
    with pytest.raises(RuntimeError, match="Unclosed dialogue quote at the end of chapter 7"):
        segment_chapter_text(7, "“Câu thoại chưa được đóng.\n\nVẫn còn trong lời thoại.")


def test_inline_curly_single_quote_is_an_inner_thought() -> None:
    rows = segment_chapter_text(1, "Hạ Phong không khỏi nghĩ: ‘Mình phải rời khỏi đây.’")

    assert [row["kind_hint"] for row in rows] == ["narration", "thought"]


def test_nested_curly_term_inside_dialogue_is_not_duplicated() -> None:
    text = (
        "Bà nói: “Nếu đánh thức được ‘Thần ân’ trong huyết mạch và trở thành hiệp sĩ thực sự, "
        "cậu sẽ trở thành một quý tộc đáng kính đấy.”"
    )

    rows = segment_chapter_text(1, text)

    assert [row["kind_hint"] for row in rows] == ["narration", "dialogue"]
    spoken = " ".join(row["text"] for row in rows)
    assert spoken.count("Thần ân") == 1
    assert spoken.count("trong huyết mạch") == 1


def test_nested_quote_regressions_preserve_every_spoken_token_once() -> None:
    samples = [
        (
            "“Đây là ‘Nightingale đen’ từ Vương quốc Holm, chỉ có quý tộc thực thụ mới mua nổi "
            "thôi. Cậu lấy nó ở đâu vậy?”"
        ),
        (
            "“Nếu đánh thức được ‘Thần ân’ trong huyết mạch và trở thành hiệp sĩ thực sự, "
            "cậu sẽ trở thành một quý tộc đáng kính đấy.”"
        ),
    ]

    for text in samples:
        rows = segment_chapter_text(1, text)
        joined = " ".join(str(row["text"]) for row in rows)
        assert joined.count("Nightingale đen") == text.count("Nightingale đen")
        assert joined.count("Thần ân") == text.count("Thần ân")


def test_inline_reference_markers_are_removed_before_segmentation() -> None:
    source = "Định luật Murphy[note54359] đang nhắc nhở. [cười] Ta hiểu rồi."

    rows = segment_chapter_text(1, source)

    assert [row["text"] for row in rows] == ["Định luật Murphy đang nhắc nhở. [cười] Ta hiểu rồi."]
    assert "[note" in source


def test_punctuation_only_content_never_becomes_tts_segment() -> None:
    rows = segment_chapter_text(1, "Một câu kể.\n…\n,\nMột câu khác.")

    assert [row["text"] for row in rows] == ["Một câu kể.", "Một câu khác."]
    assert all(any(char.isalnum() for char in row["text"]) for row in rows)
    assert segment_chapter_text(1, "…\n,\n.") == []


def test_vocalizations_remain_ordinary_dialogue_segments() -> None:
    rows = segment_chapter_text(1, '“Ha…”\n“Ha ha ha...”\n“Haiz…”\n“Hầy...”\n“Hừm...”\n“Khụ khụ...”\n“Ha?”')

    assert [row["kind_hint"] for row in rows] == ["dialogue"] * 7
    assert [row["text"] for row in rows] == [
        '“Ha…”',
        '“Ha ha ha...”',
        '“Haiz…”',
        '“Hầy...”',
        '“Hừm...”',
        '“Khụ khụ...”',
        '“Ha?”',
    ]


def test_vocal_cues_and_onomatopoeia_stay_in_their_spoken_sentences() -> None:
    rows = segment_chapter_text(1, '— [cười] Ta thắng rồi!\n\nRầm! Cánh cửa bật mở.')

    assert [(row["text"], row["kind_hint"]) for row in rows] == [
        ("— [cười] Ta thắng rồi!", "dialogue"),
        ("Rầm! Cánh cửa bật mở.", "narration"),
    ]


@pytest.mark.parametrize(
    ("source", "spoken"),
    [
        ('“Ha…”', '“Hà... hà...”'),
        ('“Haiz…”', '“Hầy…”'),
        ('“Haizzzzz....”', '“Hầy...”'),
        ('“Hừmmmm...”', '“Hừm...”'),
        ('“Hahaha!”', '“Ha ha ha!”'),
        ('“Aaaaah!”', '“A... a!”'),
        ('“Uuu…”', '“U... u…”'),
        ("[cười] Ta thắng rồi!", "Ha ha... Ta thắng rồi!"),
        ("[thở dài].", "Hầy..."),
        ("[hắng giọng] Tôi xin nói tiếp.", "Khụ khụ... Tôi xin nói tiếp."),
    ],
)
def test_vocalizations_are_normalized_only_for_tts(source: str, spoken: str) -> None:
    assert normalize_vocalizations_for_tts(source) == spoken


@pytest.mark.parametrize(
    "text",
    ["Hức hức hức…", "“S… Hự!”", "“Aaaaah!”", "“Uuu…”", "Ha, ha, ho."],
)
def test_non_lexical_vocalizations_are_recognized(text: str) -> None:
    assert is_vocalization_only(text)


@pytest.mark.parametrize("text", ["Paso.", "Gaya.", "Cảm ơn.", "Anh Lucien!"])
def test_lexical_text_is_not_a_vocalization(text: str) -> None:
    assert not is_vocalization_only(text)
