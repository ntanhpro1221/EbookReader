"""A formula is read as words: "+" is "cộng" and "=" is "bằng", for the voice and for the check alike.

Book 2, batch 1, chapter 025: the alchemy recipe "A + B + C = D" was spoken correctly - Whisper
wrote "cộng" and "bằng" - and failed anyway, because the comparison string still carried the
symbols. Five repair candidates fell the same way. The take was right; the ruler was wrong.
Measured before patching: 40 "+" and 26 "=" across 28 lines of the 915-chapter source; "%" needs
nothing (Whisper writes "25%" back as a symbol, 6/6 verified in book 1).
"""
from __future__ import annotations

from ebook_reader.text_processing import spoken_symbols_to_words


def test_an_alchemy_recipe_is_read_as_words() -> None:
    assert (
        spoken_symbols_to_words("Nấm xác chết + Mô não thủy quỷ + Bụi oán linh = Linh Hồn Than Khóc")
        == "Nấm xác chết cộng Mô não thủy quỷ cộng Bụi oán linh bằng Linh Hồn Than Khóc"
    )


def test_goldbach_and_einstein() -> None:
    assert spoken_symbols_to_words("Ví dụ như 4 = 2 + 2, 10 = 7 + 3.") == "Ví dụ như 4 bằng 2 cộng 2, 10 bằng 7 cộng 3."
    assert spoken_symbols_to_words("chứng minh ‘1+1’ đó") == "chứng minh ‘1 cộng 1’ đó"
    assert spoken_symbols_to_words("“E = mc^2.”") == "“E bằng mc mũ 2.”"
    assert spoken_symbols_to_words("Nhưng với N ≥ 3, đặc biệt") == "Nhưng với N lớn hơn hoặc bằng 3, đặc biệt"


def test_a_double_arrow_is_a_pause_not_an_equals_sign() -> None:
    assert spoken_symbols_to_words("khác nhau => đưa 2 bình vào") == "khác nhau, đưa 2 bình vào"
    # Leading arrow: nothing precedes it, so nothing to separate - same as a bullet.
    assert spoken_symbols_to_words("=> Hiện tượng trên gây mâu thuẫn") == "Hiện tượng trên gây mâu thuẫn"


def test_percent_is_left_for_the_transcriber_to_write_back() -> None:
    assert spoken_symbols_to_words("bị trừ 25% điểm số") == "bị trừ 25% điểm số"


def test_stable_on_its_own_output() -> None:
    once = spoken_symbols_to_words("Dạng 1+2: 1 số nguyên tố + 2 số nguyên tố (ví dụ 10 = 5 + (2 + 3))")
    assert once == spoken_symbols_to_words(once)
    assert "+" not in once and "=" not in once


def test_a_vocal_cue_still_passes_through() -> None:
    assert spoken_symbols_to_words("[thở dài] 1 + 1 = 2") == "[thở dài] 1 cộng 1 bằng 2"
