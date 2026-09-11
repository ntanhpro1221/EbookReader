"""`scripts/name_marks.py` và `character_registry` phải cho cùng câu trả lời về tên rơi dấu.

Hai bản tồn tại vì lý do thời điểm: script gieo phải gộp được THU LÃNH / THỦ LÃNH **ngay**,
trước ranh giới lô, còn registry chỉ đổi được ở ranh giới. Hai bản của một luật thì sớm muộn
lệch nhau, và bài này là cái giữ chúng không lệch.

Nửa đầu chạy được ngay (chỉ cần `name_marks`); nửa sau chỉ chạy khi registry đã mang bản chính,
và trong khi chưa mang thì **bỏ qua có nói lý do** chứ không xanh giả.
"""
from __future__ import annotations

import pytest

from scripts.name_marks import dropped_marks_variant_of, fold_dropped_marks

PAIRS = [
    ("THU LÃNH", "THỦ LÃNH", True),
    ("THỦ LÃNH", "THU LÃNH", False),
    ("NGUOI TRA LOI", "NGƯỜI TRẢ LỜI", True),
    ("NGƯỜI TRA LOI", "NGƯỜI TRẢ LỜI", True),
    ("Thu Lãnh", "THỦ LÃNH", True),
    ("MÁ", "MÀ", False),
    ("MÀ", "MÁ", False),
    ("SAMAEL", "SAMAELE", False),
    ("SAMAEL", "SAMAEL", False),
    # Gạch dưới là khoảng trắng: bản ASCII nối gạch của một tên đủ dấu là bản rơi dấu của nó.
    ("NGUOI_TRA_LOI", "NGƯỜI TRẢ LỜI", True),
    ("NGƯỜI_TRẢ_LỜI", "NGƯỜI TRẢ LỜI", False),
]


@pytest.mark.parametrize("loser, winner, expected", PAIRS)
def test_dropped_marks_rule(loser: str, winner: str, expected: bool) -> None:
    assert dropped_marks_variant_of(loser, winner) is expected


def test_fold_prefers_the_spelling_with_more_marks_not_the_frequent_one() -> None:
    """Đúng tỉ lệ lô 3: bản rơi dấu 160 lần, bản đúng 46 — bản đúng vẫn phải thắng."""
    folded = fold_dropped_marks(
        ["NGUOI TRA LOI", "NGƯỜI TRẢ LỜI", "THU LÃNH", "THỦ LÃNH", "MÁ", "MÀ", "KANG"],
        {"NGUOI TRA LOI": 160, "NGƯỜI TRẢ LỜI": 46, "THU LÃNH": 66, "THỦ LÃNH": 32},
    )
    assert folded == {"NGUOI TRA LOI": "NGƯỜI TRẢ LỜI", "THU LÃNH": "THỦ LÃNH"}
    assert "MÁ" not in folded and "MÀ" not in folded, "hai từ khác nhau không được gộp"


def test_the_script_copy_agrees_with_the_registry() -> None:
    registry = pytest.importorskip("ebook_reader.character_registry")
    if not hasattr(registry, "dropped_marks_variant_of"):
        pytest.skip(
            "registry chưa mang bản chính - patch_dropped_marks_are_the_same_name chưa áp"
        )
    for loser, winner, expected in PAIRS:
        assert registry.dropped_marks_variant_of(loser, winner) is expected, (loser, winner)
        assert registry.dropped_marks_variant_of(loser, winner) is dropped_marks_variant_of(
            loser, winner
        )
