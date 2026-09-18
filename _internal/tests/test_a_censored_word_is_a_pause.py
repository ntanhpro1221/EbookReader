"""Chữ bị che bằng ký hiệu đọc thành khoảng ngừng - xem patch_a_censored_word_is_a_pause.py."""
from __future__ import annotations

import pytest

from ebook_reader.text_processing import spoken_symbols_to_words


@pytest.mark.parametrize(
    ("text", "spoken"),
    [
        ("\u201cC\u00e1i #&!@! Kh\u00f4ng ph\u1ea3i l\u1ea1i n\u1eefa ch\u1ee9?\u201d",
         "\u201cC\u00e1i\u2026 Kh\u00f4ng ph\u1ea3i l\u1ea1i n\u1eefa ch\u1ee9?\u201d"),
        ("\u0111\u1ea7u ng\u01b0\u01a1i \u0111\u1ec3 d\u01b0\u1edbi *** \u00e0?",
         "\u0111\u1ea7u ng\u01b0\u01a1i \u0111\u1ec3 d\u01b0\u1edbi\u2026 \u00e0?"),
    ],
    ids=["chuong 225 #&!@!", "chuong 385 ***"],
)
def test_a_censored_word_becomes_a_pause(text: str, spoken: str) -> None:
    assert spoken_symbols_to_words(text) == spoken


@pytest.mark.parametrize(
    ("text", "spoken"),
    [
        ("Vua Tai H\u1ecda Viken?**", "Vua Tai H\u1ecda Viken?"),
        ("ch\u1ec9 \u1edf c\u1ea5p A*?*", "ch\u1ec9 \u1edf c\u1ea5p A?"),
        ("H\u1ea3?!?", "H\u1ea3?!?"),
        ("Tr\u1eddi \u01a1i!!!", "Tr\u1eddi \u01a1i!!!"),
        ("\u0111\u1ee7 100%!!", "\u0111\u1ee7 100%!!"),
        ("***", ""),
    ],
    ids=["dau in dam sot lai", "dau nghieng sot lai", "?!?", "!!!", "phan tram", "dong ngan canh"],
)
def test_what_is_not_a_censored_word_keeps_its_old_reading(text: str, spoken: str) -> None:
    assert spoken_symbols_to_words(text) == spoken


def test_the_pause_is_stable_on_its_own_output_and_on_its_fragments() -> None:
    once = spoken_symbols_to_words("\u201cC\u00e1i #&!@! Kh\u00f4ng ph\u1ea3i l\u1ea1i n\u1eefa ch\u1ee9?\u201d")
    assert spoken_symbols_to_words(once) == once
    for cut in range(1, len(once)):
        for piece in (once[:cut], once[cut:]):
            assert spoken_symbols_to_words(spoken_symbols_to_words(piece)) == spoken_symbols_to_words(piece)
