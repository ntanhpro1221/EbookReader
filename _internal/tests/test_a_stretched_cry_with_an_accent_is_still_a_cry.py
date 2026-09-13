"""Tiếng hét kéo dài bắt đầu bằng một nguyên âm có dấu vẫn là một tiếng hét.

Lô 9, chương 223: `"ÁAAAAA!!"` đi nguyên vào TTS vì mẫu nguyên-âm-kéo-dài đòi token chỉ gồm một
nguyên âm lặp; bộ sinh chạy tới trần khung, ASR bịa ra câu chào cuối video, chương hỏng.
"""
from __future__ import annotations

from ebook_reader.text_processing import normalize_vocalizations_for_tts


def test_an_accented_lead_vowel_joins_the_held_sound() -> None:
    assert normalize_vocalizations_for_tts('"ÁAAAAA!!"') == '"Á... a!!"'


def test_a_plain_held_vowel_keeps_the_old_form() -> None:
    assert normalize_vocalizations_for_tts('"AAAAA!"') == '"A... a!"'


def test_a_circumflex_vowel_with_a_tone_mark_still_matches_its_base() -> None:
    assert normalize_vocalizations_for_tts('"Ốôôôô!"') == '"Ố... ô!"'


def test_a_different_base_letter_is_not_one_sound() -> None:
    assert normalize_vocalizations_for_tts('"Ôaaa"') == '"Ôaaa"'


def test_a_stretch_inside_a_word_is_still_left_alone() -> None:
    """Đây là việc khác: "Khôôôông" là một từ kéo dài, không phải tiếng hét trần trụi."""
    assert normalize_vocalizations_for_tts("Khôôôông") == "Khôôôông"
