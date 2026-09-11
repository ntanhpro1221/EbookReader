"""`scripts/source_spellings.py` và `character_registry` phải cho cùng câu trả lời.

Hai bản tồn tại vì lý do thời điểm, y như luật rơi dấu: script gieo phải gộp được ngay ở ranh
giới lô, còn registry chỉ đổi được khi có một ranh giới để áp bản vá. Hai bản của một luật thì
sớm muộn lệch nhau, và bài này là cái giữ chúng không lệch.
"""
from __future__ import annotations

import pytest

from scripts.source_spellings import fold_to_source_spelling as script_fold
from scripts.source_spellings import occurrences as script_occurrences

BOOK = "selene buoc vao. samael dap. so ba noi. so bay dap. " * 5

CASES = [
    (["SELNE", "SELENE"], {"SELNE": 32, "SELENE": 7}),
    (["SELNE VALKRYN", "SELENE"], {"SELNE VALKRYN": 3, "SELENE": 7}),
    (["SAMAELE", "SAMAEL"], {"SAMAELE": 1, "SAMAEL": 19}),
    (["SỐ BA", "SỐ BẢY"], {"SỐ BA": 2, "SỐ BẢY": 7}),
    (["NARRATOR", "SELENE"], {}),
    (["SELNE", "SELENE"], {}),
]


@pytest.mark.parametrize("names, counts", CASES)
def test_the_two_copies_agree(names: list[str], counts: dict[str, int]) -> None:
    registry = pytest.importorskip("ebook_reader.character_registry")
    if not hasattr(registry, "fold_to_source_spelling"):
        pytest.skip("registry chưa mang bản chính - patch_the_book_decides_the_spelling chưa áp")

    assert registry.fold_to_source_spelling(names, BOOK, counts) == script_fold(
        names, BOOK, counts
    )
    for name in names:
        assert registry.source_occurrences(name, BOOK) == script_occurrences(name, BOOK)
