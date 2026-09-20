"""Nhãn vắng mặt trong sách lệch hai ký tự thì gom, nhưng chỉ khi đích duy nhất và nhãn đủ dài."""
from __future__ import annotations

from ebook_reader.character_registry import fold_for_source_search, fold_to_source_spelling

SOURCE = fold_for_source_search(
    "Jocelyn quay sang Artil. Artil im lặng. Jocelyn nói với Artil rằng Norman đã tới. "
    "Norman gật đầu với Jocelyn."
)


def test_two_letters_off_folds_to_the_one_spelling_in_the_book() -> None:
    folded = fold_to_source_spelling(["Jocelyn", "JOCLEYN", "ARTIL", "ARTELI", "Norman"], SOURCE)
    assert folded == {"JOCLEYN": "Jocelyn", "ARTELI": "ARTIL"}


def test_a_name_in_the_book_is_never_folded() -> None:
    assert fold_to_source_spelling(["Jocelyn", "Norman", "Artil"], SOURCE) == {}


def test_two_different_targets_are_not_guessed() -> None:
    source = fold_for_source_search("Marina và Karina cùng bước vào. Marina nói. Karina đáp.")
    # "SARINO" lệch đúng hai ký tự với CẢ Marina lẫn Karina -> hai đích khác nhau, không đoán.
    assert fold_to_source_spelling(["Marina", "Karina", "SARINO"], source) == {}


def test_a_short_label_is_not_folded_by_two_edits() -> None:
    source = fold_for_source_search("Tom bước vào. Tom nói. Tom đi ra.")
    # "TAP" lệch hai ký tự với "Tom" nhưng chỉ dài 3 -> không gom.
    assert fold_to_source_spelling(["Tom", "TAP"], source) == {}
    assert fold_to_source_spelling(["Tom", "ROM"], source) == {"ROM": "Tom"}  # lệch một, luật cũ
