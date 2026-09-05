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
