"""Characters the voice cannot say become words it can, or a pause - never nothing.

The owner heard "Thường (Common) (C) » Hiếm (Rare) (B)" come out as one unbroken run:
"Thường Common C hiếm, Ray B". A guillemet is not a pause and a bracket the voice ignores is
not one either, so an annotation gets swallowed into the sentence as though it were part of
it.

Two rules, and the second is the one that is easy to get wrong:

  - A character that MEANS something becomes a word. "↓ 1.000 Đơn vị" means *giảm* 1.000
    units; dropping the arrow drops the meaning of the line.
  - A character that SEPARATES becomes a comma, never nothing. Dropping it silently is the
    defect being fixed, not a tidier version of it.

Measured on c00009_s0000018: the pace metric budgeted 6.90s of silence out of 11.80s of
audio for punctuation the voice never paused at, inflating the rate from 10.76 to 25.92
chars/s and tripping the upper bound. Commas make the voice take the pauses the metric
already assumed, so the two agree.
"""
from __future__ import annotations

from ebook_reader.text_processing import spoken_symbols_to_words


def test_guillemet_becomes_a_pause() -> None:
    assert spoken_symbols_to_words("C » B » A » S") == "C, B, A, S"


def test_arrows_become_their_meaning() -> None:
    """Dropping these would lose the sentence's meaning, not just its punctuation."""
    assert spoken_symbols_to_words("↓ 1.000 Đơn vị") == "giảm 1.000 Đơn vị"
    assert spoken_symbols_to_words("↑ 500 điểm") == "tăng 500 điểm"


def test_an_annotation_is_set_off_by_commas() -> None:
    """Not dropped: without the pause the annotation reads as part of the sentence."""
    assert spoken_symbols_to_words("Tiềm Năng ở [A-rank], họ chỉ") == "Tiềm Năng ở, A-rank, họ chỉ"
    assert spoken_symbols_to_words("Thường (Common) tiếp") == "Thường, Common, tiếp"


def test_a_vocal_cue_survives_untouched() -> None:
    """[thở dài] is a stage direction the vocalization pass turns into a breath.

    Converting its brackets to commas destroys the cue before that pass sees it. Both kinds
    of bracket appear in this book, so the cue is matched first and passed through.
    """
    assert spoken_symbols_to_words("[thở dài] Mây rồi May") == "[thở dài] Mây rồi May"
    assert spoken_symbols_to_words("[cười] rồi (Common) tiếp") == "[cười] rồi, Common, tiếp"


def test_a_bullet_leaves_no_comma_behind() -> None:
    """Nothing precedes a list marker, so there is nothing to separate it from."""
    assert spoken_symbols_to_words("• Hệ thống Sức mạnh") == "Hệ thống Sức mạnh"


def test_ordinary_text_is_untouched() -> None:
    for line in (
        "Câu bình thường không có gì lạ.",
        "Tên tôi là Samael Kaizer Theosbane.",
        "Anh ấy nói: “không thể nào!”",
    ):
        assert spoken_symbols_to_words(line) == line


def test_no_hanging_or_doubled_commas() -> None:
    assert spoken_symbols_to_words("(Spirit Essence Units)") == "Spirit Essence Units"
    assert ",," not in spoken_symbols_to_words("(A) (B) » (C)")
    assert not spoken_symbols_to_words("xong (chú thích)").endswith(",")


# --- stability on fragments of its own output -----------------------------------------
# The repair path splits a long segment into pieces of the already-converted text and then
# re-derives each piece, requiring the boundary text not to move. alpha.45 died on that at
# chapter 2 after ~40 minutes of work: a rule anchored to the end of the string sees a
# fragment's end, which is not the end of the text the fragment came from.

ALPHA45_KILLER = (
    "Ví dụ, nếu một người có Tiềm năng hạng A, họ sẽ chỉ có thể sử dụng tối đa Thẻ bài "
    "cấp Sử thi (Epic), hoặc trong một số trường hợp cực đoan là cấp Huyền thoại (Legendary)."
)


def test_the_segment_that_killed_alpha45_is_stable_when_cut_at_its_commas() -> None:
    """(Legendary) became ", Legendary," which pushed the text past the splitter's cap,
    so it cut at a comma this function had just created - and the second pass trimmed
    that now-trailing comma back off."""
    converted = spoken_symbols_to_words(ALPHA45_KILLER)
    assert converted.count("(") == 0

    cut = converted.rindex(",") + 1
    head, tail = converted[:cut], converted[cut:].strip()

    assert head.endswith(","), "the case only bites when a piece ends on a comma"
    assert spoken_symbols_to_words(head) == head
    assert spoken_symbols_to_words(tail) == tail


def test_every_piece_of_converted_text_is_left_alone() -> None:
    """The property, not just the one case: cut anywhere on a word boundary and re-derive."""
    samples = [
        ALPHA45_KILLER,
        "Thường (Common) (C) » Hiếm (Rare) » Sử thi (Epic)",
        "Cấp 1-3 là Cổng Tự nhiên (Natural Portals) tự động mở. Chỉ Ấu Linh (Infant) qua được.",
        "↓ 1.000 Đơn vị (SEU) » còn lại 4.000",
        "[thở dài] Thôi được rồi (đành vậy), đi thôi.",
    ]
    for sample in samples:
        converted = spoken_symbols_to_words(sample)
        assert spoken_symbols_to_words(converted) == converted, sample
        # Where the splitter actually cuts: after a sentence ender, and after a comma when
        # a segment runs past the character cap. Cutting inside a vocal cue is not a case
        # to defend - "[thở" is no longer a cue whatever this function does to it.
        cuts = [
            index + 1
            for index, character in enumerate(converted)
            if character in ",.!?…" and index + 1 < len(converted)
        ]
        for cut in cuts:
            for piece in (converted[:cut], converted[cut:].strip()):
                if not piece:
                    continue
                assert spoken_symbols_to_words(piece) == piece, (sample, piece)


def test_a_vocal_cue_at_the_very_start_keeps_its_brackets() -> None:
    """The brackets delimiting a cue are separators too; trimming the ends ate the opening
    one, and the cue read out as the words "thở dài" instead of becoming a breath."""
    assert spoken_symbols_to_words("[thở dài] Mây rồi May") == "[thở dài] Mây rồi May"
    assert spoken_symbols_to_words("Mây rồi May [thở dài]") == "Mây rồi May [thở dài]"


def test_a_comma_the_author_wrote_at_the_end_is_kept() -> None:
    """Verse lines in this book end on a comma. Trimming it deleted a pause somebody meant."""
    line = "Sinh ra từ bóng tối, mang trên mình lời nguyền,"
    assert spoken_symbols_to_words(line) == line


def test_a_separator_at_either_end_still_leaves_no_hanging_comma() -> None:
    """What the removed trimming was for, done before conversion instead of after."""
    assert spoken_symbols_to_words("» Hiếm") == "Hiếm"
    assert spoken_symbols_to_words("Thường (Common)") == "Thường, Common"
    assert spoken_symbols_to_words("(Common)") == "Common"
