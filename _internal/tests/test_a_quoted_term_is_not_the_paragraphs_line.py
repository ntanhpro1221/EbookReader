"""Khoá "một đoạn văn một người nói" không nuốt cụm trích nằm giữa một câu kể (đáp án chuẩn TMA 419:24, 26)."""
from __future__ import annotations

from ebook_reader.analysis import _validate


def _row(seq: int, kind_hint: str, text: str) -> dict:
    return {"stable_id": f"s{seq}", "kind_hint": kind_hint, "text": text, "chapter_id": 1, "seq": seq,
            "paragraph_index": 13}


def _item(seq: int, kind: str, speaker: str, gender: str = "unknown") -> dict:
    return {"id": f"s{seq}", "kind": kind, "speaker": speaker, "gender": gender, "age": "unknown",
            "emotion": "neutral", "intensity": 0, "pace": "normal", "volume": "normal", "confidence": 0.9}


def test_a_term_quoted_inside_a_sentence_keeps_its_own_reading() -> None:
    group = [
        _row(0, "dialogue", "“Đào tạo nhân công lành nghề với số lượng lớn sẽ mất rất nhiều thời gian…”"),
        _row(1, "narration", "Arthur không hiểu"),
        _row(2, "dialogue", "“dây chuyền lắp ráp”"),
        _row(3, "narration", "hay"),
        _row(4, "dialogue", "“tiêu chuẩn hóa”"),
        _row(5, "narration", "là gì, nhưng tạm thời ông cũng không có hứng hỏi."),
    ]
    payload = {"segments": [
        _item(0, "dialogue", "Arthur", "male"), _item(1, "narration", "NARRATOR"),
        _item(2, "dialogue", "NARRATOR"), _item(3, "narration", "NARRATOR"),
        _item(4, "dialogue", "NARRATOR"), _item(5, "narration", "NARRATOR"),
    ]}
    result = _validate(group, payload)
    assert result["s0"]["speaker"].casefold() == "arthur"
    assert result["s2"]["speaker"].casefold() != "arthur"
    assert result["s4"]["speaker"].casefold() != "arthur"


def test_a_term_at_the_edge_of_an_analysis_batch_is_still_seen() -> None:
    # 419:26 là đoạn cuối lô của nó: không thấy câu kể phía sau.
    group = [
        _row(0, "dialogue", "“Đào tạo nhân công lành nghề với số lượng lớn sẽ mất rất nhiều thời gian…”"),
        _row(1, "narration", "Arthur không hiểu"),
        _row(2, "dialogue", "“dây chuyền lắp ráp”"),
        _row(3, "narration", "hay"),
        _row(4, "dialogue", "“tiêu chuẩn hóa”"),
    ]
    payload = {"segments": [
        _item(0, "dialogue", "Arthur", "male"), _item(1, "narration", "NARRATOR"),
        _item(2, "dialogue", "NARRATOR"), _item(3, "narration", "NARRATOR"), _item(4, "dialogue", "NARRATOR"),
    ]}
    result = _validate(group, payload)
    assert result["s4"]["speaker"].casefold() != "arthur"


def test_a_spoken_line_with_a_lowercase_tag_is_still_the_paragraphs() -> None:
    group = [
        _row(0, "dialogue", "“Đi thôi,”"),
        _row(1, "narration", "hắn nói, rồi quay sang Arthur."),
        _row(2, "dialogue", "“Chúng ta đi thôi.”"),
        _row(3, "narration", "Arthur nói."),
    ]
    payload = {"segments": [
        _item(0, "dialogue", "Lucien", "male"), _item(1, "narration", "NARRATOR"),
        _item(2, "dialogue", "Arthur", "male"), _item(3, "narration", "NARRATOR"),
    ]}
    result = _validate(group, payload)
    assert result["s0"]["speaker"].casefold() == "arthur"


def test_a_line_standing_on_its_own_is_still_the_paragraphs() -> None:
    group = [
        _row(0, "dialogue", "“Chúng ta đi thôi.”"),
        _row(1, "narration", "Arthur nói."),
        _row(2, "dialogue", "“Trời sắp tối rồi.”"),
    ]
    payload = {"segments": [
        _item(0, "dialogue", "Arthur", "male"), _item(1, "narration", "NARRATOR"), _item(2, "dialogue", "Lucien", "male"),
    ]}
    result = _validate(group, payload)
    assert result["s2"]["speaker"].casefold() == "arthur"
