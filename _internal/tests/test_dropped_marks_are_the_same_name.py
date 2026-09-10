"""Một tên rơi dấu vẫn là tên ấy: THU LÃNH là THỦ LÃNH, và giọng phải là một.

Đo trên lô 2 và lô 3 (2026-09-10): hai cặp như thế, và ở lô 3 bản rơi dấu đã thành bản trội —
THU LÃNH 66 lần nhắc so với THỦ LÃNH 32, NGUOI TRA LOI 160 so với NGƯỜI TRẢ LỜI 46. Nguồn văn
bản không chứa chuỗi nào trong số ấy: là nhãn Ollama tự đặt và rơi dấu ngẫu nhiên, rồi
`_known_summary` đưa bản nhiều lần hơn vào prompt kế tiếp nên cái sai tự củng cố. Mỗi bản tách
một chiếm một chỗ trong kho 14 giọng nam, và cùng một người đọc bằng hai giọng.
"""
from __future__ import annotations

from pathlib import Path

from ebook_reader.character_registry import (
    build_registry_and_cast,
    dropped_marks_variant_of,
)
from ebook_reader.config import build_settings

from tests.test_character_casting import _identity_db


def test_a_dropped_tone_mark_is_the_same_name() -> None:
    assert dropped_marks_variant_of("THU LÃNH", "THỦ LÃNH")
    assert dropped_marks_variant_of("NGUOI TRA LOI", "NGƯỜI TRẢ LỜI")
    assert dropped_marks_variant_of("Thu Lãnh", "THỦ LÃNH"), "hoa/thường không đổi kết luận"


def test_it_only_goes_one_way() -> None:
    """Bản đủ dấu không phải biến thể của bản thiếu dấu - hướng gộp cố định."""
    assert not dropped_marks_variant_of("THỦ LÃNH", "THU LÃNH")


def test_two_different_words_are_not_merged() -> None:
    """Tiếng Việt phân biệt từ bằng dấu: MÁ và MÀ cùng chữ trần nhưng là hai từ.

    Luật chỉ nhận **tập con** dấu, không nhận "bỏ dấu ra giống nhau"; đây là chỗ một luật rộng
    hơn sẽ gộp nhầm hai nhân vật thành một, tức lỗi ngược và tệ hơn.
    """
    assert not dropped_marks_variant_of("MÁ", "MÀ")
    assert not dropped_marks_variant_of("MÀ", "MÁ")
    assert not dropped_marks_variant_of("SAMAEL", "SAMAELE")


def test_the_two_spellings_cast_as_one_character_with_one_voice(tmp_path: Path) -> None:
    """Đúng ca lô 3, kể cả tỉ lệ: bản rơi dấu nhiều hơn bản đúng, và bản đúng vẫn phải thắng."""
    db = _identity_db(
        tmp_path,
        [("THU LÃNH", "male")] * 3 + [("THỦ LÃNH", "male")] * 2 + [("KANG", "male")],
    )

    build_registry_and_cast(db, build_settings(), lambda _message: None)

    rows = db.list_segments()
    assert {str(row["speaker"]) for row in rows} == {"THỦ LÃNH", "KANG"}, (
        "người thắng là bản ĐỦ DẤU dù ít lần hơn, vì số lần đã bị vòng phản hồi làm nhiễm"
    )
    leader = [row for row in rows if str(row["speaker"]) == "THỦ LÃNH"]
    assert len(leader) == 5
    assert len({int(row["canonical_character_id"]) for row in leader}) == 1
    assert len({int(row["voice_profile_id"]) for row in leader}) == 1
