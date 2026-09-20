"""Cụm trích giữa câu kể vẫn của người kể khi câu kể sau mở bằng một cái tên (đáp án chuẩn TMA 449:65)."""
from __future__ import annotations

from ebook_reader.analysis import _validate


def _row(seq: int, kind_hint: str, text: str) -> dict:
    return {"stable_id": f"s{seq}", "kind_hint": kind_hint, "text": text, "chapter_id": 1, "seq": seq,
            "paragraph_index": 37}


def _item(seq: int, kind: str, speaker: str, gender: str = "unknown") -> dict:
    return {"id": f"s{seq}", "kind": kind, "speaker": speaker, "gender": gender, "age": "unknown",
            "emotion": "neutral", "intensity": 0, "pace": "normal", "volume": "normal", "confidence": 0.9}


def test_a_nickname_quoted_before_a_name_stays_the_narrators() -> None:
    group = [
        _row(0, "dialogue", "“Tôi là một chiêm tinh sư.”"),
        _row(1, "narration", "Sau khi thu xếp xong đồ đạc và uống một lọ thuốc để bảo vệ cổ họng,"),
        _row(2, "dialogue", "“Sơn Ca”"),
        _row(3, "narration", "Samantha rảo bước ra khỏi phòng chờ để chuẩn bị ra về."),
    ]
    payload = {"segments": [
        _item(0, "dialogue", "Samantha", "female"), _item(1, "narration", "NARRATOR"),
        _item(2, "dialogue", "NARRATOR"), _item(3, "narration", "NARRATOR"),
    ]}
    result = _validate(group, payload)
    assert result["s0"]["speaker"].casefold() == "samantha"
    assert result["s2"]["speaker"].casefold() != "samantha"


def test_a_spoken_line_after_a_finished_sentence_is_still_the_paragraphs() -> None:
    group = [
        _row(0, "dialogue", "“Chúng ta đi thôi.”"),
        _row(1, "narration", "Samantha nói."),
        _row(2, "dialogue", "“Trời sắp tối rồi.”"),
        _row(3, "narration", "Cô nhìn ra ngoài cửa sổ."),
    ]
    payload = {"segments": [
        _item(0, "dialogue", "Samantha", "female"), _item(1, "narration", "NARRATOR"),
        _item(2, "dialogue", "Lucien", "male"), _item(3, "narration", "NARRATOR"),
    ]}
    result = _validate(group, payload)
    assert result["s2"]["speaker"].casefold() == "samantha"
