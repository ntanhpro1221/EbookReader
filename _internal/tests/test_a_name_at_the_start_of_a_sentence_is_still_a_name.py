"""Tên nước ngoài đứng đầu câu vẫn được phiên âm; từ tiếng Việt đầu câu vẫn không bị tưởng là tên."""
from __future__ import annotations

from ebook_reader.analysis import _name_candidate_contexts


def _candidates(*texts: str) -> dict[str, tuple[int, int]]:
    rows = [{"speaker": "NARRATOR", "text": text, "kind": "narration"} for text in texts]
    return {
        c["surface"]: (c["sentence_initial_occurrences"], c["mid_sentence_occurrences"])
        for c in _name_candidate_contexts(rows)
    }


def test_a_foreign_name_that_only_opens_a_sentence_is_a_candidate() -> None:
    # Chương 370 lô 8: cả đoạn là cái tên, nên nó chỉ bao giờ ở đầu câu.
    assert _candidates("“Gauci Cromwell.”") == {"Gauci Cromwell": (1, 0)}
    assert "Max Planck" in _candidates("Max Planck đã nói thế.")


def test_capitalised_vietnamese_words_at_the_start_are_still_not_names() -> None:
    assert _candidates("May mắn thay, cậu vẫn ổn. Xen lẫn trong đó còn có tóc đỏ.") == {}


def test_a_vietnamese_word_is_stripped_off_the_name_it_opens() -> None:
    found = _candidates("Khi Lucien bước vào. Nghe Morris gọi. Do Chloe đến muộn.")
    assert set(found) == {"Lucien", "Morris", "Chloe"}
    assert found["Lucien"] == (0, 1), "sau khi bóc, tên đứng sau một từ - không còn là đầu câu"
