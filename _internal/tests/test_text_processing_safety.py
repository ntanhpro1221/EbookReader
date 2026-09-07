from __future__ import annotations

from pathlib import Path

import pytest

from ebook_reader.io_utils import decode_text_bytes, sha256_file
from ebook_reader.text_processing import (
    CLAUSE_SPLIT_MAX_CHARS,
    build_chapter_manifest,
    is_standalone_ha_gasp,
    is_vocalization_only,
    load_and_segment_chapter,
    normalize_vocalizations_for_tts,
    segment_chapter_text,
    split_long_text,
    split_text_by_clauses,
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


def test_long_text_split_prefers_sentence_boundaries_without_rewriting() -> None:
    text = (
        "Câu đầu tiên đủ dài để tạo thành phần thứ nhất mà không cần cắt giữa từ. "
        "Câu thứ hai cũng giữ nguyên dấu câu và trở thành phần tiếp theo an toàn."
    )

    parts = split_long_text(text, 90)

    assert parts == [
        "Câu đầu tiên đủ dài để tạo thành phần thứ nhất mà không cần cắt giữa từ.",
        "Câu thứ hai cũng giữ nguyên dấu câu và trở thành phần tiếp theo an toàn.",
    ]
    assert " ".join(parts) == text


def test_clause_split_keeps_seq44_boundaries_bounded_without_rewriting() -> None:
    text = (
        "Cha bị tiếng nheo nhéo của mẹ làm cho chịu không nổi, trời vừa sáng đã "
        "nhờ thằng nhóc thối nhà Simon báo tin tới trang viên của ngài Tước sĩ "
        "Wayne để gọi anh hai về. Bây giờ anh ấy đã là cận vệ hiệp sĩ rồi, mấy "
        "tên thầy thuốc của nhà từ thiện đó không dám hét cái giá nực cười, thái "
        "quá trước mặt anh ấy đâu!”"
    )

    parts = split_text_by_clauses(text, CLAUSE_SPLIT_MAX_CHARS)

    assert [len(part) for part in parts] == [53, 111, 40, 102]
    assert all(len(part) <= CLAUSE_SPLIT_MAX_CHARS for part in parts)
    assert " ".join(parts) == text


def test_clause_split_rejects_an_unbroken_token_over_max_chars() -> None:
    text = "a" * (CLAUSE_SPLIT_MAX_CHARS + 1)

    with pytest.raises(ValueError, match="unbroken token"):
        split_text_by_clauses(text, CLAUSE_SPLIT_MAX_CHARS)


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


def test_unclosed_quote_is_recovered_instead_of_refusing_the_chapter() -> None:
    """A missing quote mark used to refuse the chapter, which stops a whole book on a typo.

    Eight of this book's 478 chapters trip it, in a source nobody here wrote. The chapter has
    to come out; being cast slightly wrong is a smaller loss than not existing.
    """
    warnings: list[str] = []

    rows = segment_chapter_text(
        7,
        "“Câu thoại chưa được đóng.\n\nVẫn còn trong lời thoại.",
        warnings=warnings,
    )

    assert rows, "chương phải chia ra được, không được từ chối"
    assert warnings and "chapter 7" in warnings[0].lower()


def test_recovery_never_drops_a_spoken_word() -> None:
    """The point of the whole exercise: recover the casting, never the words.

    segment_chapter_text already proves this for itself on every chapter through its token
    check; this pins the promise so nobody relaxes that check later.
    """
    text = (
        "“Mở ra mà không đóng lại.\n\n"
        "Một đoạn kể bình thường ở giữa.\n\n"
        "“Một câu thoại khác, đóng đàng hoàng.”\n\n"
        "Đoạn kể cuối cùng."
    )

    rows = segment_chapter_text(3, text)
    spoken = " ".join(str(row["text"]) for row in rows)

    for word in ("Mở", "đóng", "bình", "thường", "đàng", "hoàng", "cuối", "cùng"):
        assert word in spoken


def test_a_quote_spanning_paragraphs_still_closes_where_it_should() -> None:
    """Recovery must not punish the legitimate case that made the state cross-paragraph.

    Chapter 019 of this book carries a six-line oath: one opening mark, five paragraphs, then
    the closing mark. That is not a defect and must keep its single dialogue reading.
    """
    text = (
        "“Món nợ của Theosbane luôn được trả,\n\n"
        "Lời hứa của Zynx không bao giờ lung lay,\n\n"
        "Danh dự của Kallith còn quý hơn cả vàng.”\n\n"
        "Tôi liếc xuống nhìn cậu ta."
    )
    warnings: list[str] = []

    rows = segment_chapter_text(19, text, warnings=warnings)

    assert warnings == [], "lời thề đóng đúng chỗ, không được coi là hỏng"
    assert [row["kind_hint"] for row in rows][-1] == "narration"
    assert rows[0]["kind_hint"] == "dialogue"


def test_recovery_closes_the_offending_paragraph_not_the_innocent_one() -> None:
    """Chapter 019's real shape, with the straight quotes it really uses.

    The oath opens in one paragraph and closes two later - legitimate, and only possible
    because the quote state crosses paragraphs. The real fault is a later paragraph ending
    with a mark it never opened. With straight quotes the opener and the closer are the same
    character, so that stray mark reads as an opening and hangs to the end of the chapter.
    That is the whole class of defect.

    A recovery that blamed the first odd paragraph would break the oath and leave the real
    fault in place - exactly what two earlier versions of check_sources.py did.
    """
    text = "\n\n".join(
        [
            '"Món nợ của Theosbane luôn được trả,',
            'Danh dự của Kallith còn quý hơn cả vàng."',
            "Trước khi hai người kia kịp phản hồi, gã nhóc lên tiếng.",
            'Đúng là vậy, nhưng tiền nong có hơi eo hẹp."',
            "À, đương nhiên rồi nhỉ.",
        ]
    )
    warnings: list[str] = []

    rows = segment_chapter_text(19, text, warnings=warnings)

    assert len(warnings) == 1, warnings
    assert "paragraph 4" in warnings[0], warnings[0]
    # lời thề vẫn là lời thoại trải hai đoạn, recovery không đụng vào
    assert rows[0]["kind_hint"] == "dialogue"
    assert str(rows[0]["text"]).startswith('"Món nợ')


def test_recovery_terminates_on_a_chapter_of_nothing_but_open_quotes() -> None:
    """The lever is applied one paragraph at a time, so it has to be proved to terminate."""
    text = "\n\n".join(f"“Đoạn thứ {index} không bao giờ đóng." for index in range(12))
    warnings: list[str] = []

    rows = segment_chapter_text(4, text, warnings=warnings)

    assert rows
    assert len(warnings) == 1


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
        ('“Ha…”', '“Ha ha.”'),
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
    [
        "Hức hức hức…",
        "“S… Hự!”",
        "“Aaaaah!”",
        "“Uuu…”",
        "Ha, ha, ho.",
        "Haha,",
        "Hahaha!",
    ],
)
def test_non_lexical_vocalizations_are_recognized(text: str) -> None:
    assert is_vocalization_only(text)


@pytest.mark.parametrize(
    "text",
    ["Paso.", "Gaya.", "Cảm ơn.", "Anh Lucien!", "Haha, tốt cả."],
)
def test_lexical_text_is_not_a_vocalization(text: str) -> None:
    assert not is_vocalization_only(text)


@pytest.mark.parametrize(
    "text",
    ['“Ha…”', '"ha..."', "— Ha…", "  'HA..'  "],
)
def test_standalone_ha_gasp_is_narrowly_recognized(text: str) -> None:
    assert is_standalone_ha_gasp(text)


@pytest.mark.parametrize(
    "text",
    ["Ha?", "Ha ha.", "Hà Hà.", "“Ha…” Hạ Phong bật dậy.", "Ah…”"],
)
def test_non_standalone_ha_text_does_not_activate_gasp_delivery(text: str) -> None:
    assert not is_standalone_ha_gasp(text)


def test_load_and_segment_chapter_forwards_the_warnings_list() -> None:
    """The recovery is only useful if it reaches whoever is watching."""
    import inspect

    from ebook_reader.text_processing import load_and_segment_chapter

    signature = inspect.signature(load_and_segment_chapter)

    assert "warnings" in signature.parameters


def test_the_pipeline_asks_for_the_warnings_and_says_them_out_loud() -> None:
    """A chapter recovered in silence is the defect this was built to prevent.

    segment_chapter_text recovers a source that never closes a quote instead of refusing the
    chapter, and the recovery may read a stretch as dialogue that was narration - a chapter
    cast slightly wrong rather than a chapter that does not exist. That trade is worth making
    only when somebody is told, because a mis-cast stretch nobody recorded is exactly what
    reaches the finished book unnoticed.

    Eight of this source's 478 chapters recover, and when this was first written the pipeline
    called load_and_segment_chapter without the argument, so all eight would have been
    recovered without a word in the log.
    """
    import inspect

    from ebook_reader.pipeline import BookPipeline

    source = inspect.getsource(BookPipeline)

    assert "warnings=segmentation_warnings" in source, (
        "bộ chia đoạn phải được hỏi nó đã phục hồi những gì"
    )
    assert "SOURCE_QUOTE_RECOVERED" in source, (
        "phục hồi phải để lại một sự kiện đọc được, không chỉ một dòng log"
    )
