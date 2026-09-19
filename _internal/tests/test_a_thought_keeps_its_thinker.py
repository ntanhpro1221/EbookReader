"""Câu nội tâm giữ người đang nghĩ; chỉ câu nội tâm không ai nhận mới về người kể (7e4d74c + chỗ bị sót)."""
from __future__ import annotations

from ebook_reader.analysis import _validate


def _row(seq: int, kind_hint: str, text: str) -> dict:
    return {"stable_id": f"s{seq}", "kind_hint": kind_hint, "text": text, "chapter_id": 1, "seq": seq,
            "paragraph_index": seq}


def _item(seq: int, kind: str, speaker: str, gender: str = "male") -> dict:
    return {"id": f"s{seq}", "kind": kind, "speaker": speaker, "gender": gender, "age": "adult",
            "emotion": "neutral", "intensity": 0, "pace": "normal", "volume": "normal", "confidence": 0.9}


def test_a_thought_keeps_the_thinker_and_narration_stays_the_narrators() -> None:
    group = [_row(0, "thought", "‘Chắc chắn sai ở đâu rồi.’"), _row(1, "narration", "Chloe thầm hét lên.")]
    result = _validate(group, {"segments": [_item(0, "thought", "Chloe"), _item(1, "narration", "Chloe")]})
    assert result["s0"]["speaker"].upper() == "CHLOE"
    assert result["s0"]["gender"] == "male"
    assert result["s1"]["speaker"] == "NARRATOR"


def test_an_unattributed_thought_falls_back_to_the_narrator() -> None:
    group = [_row(0, "thought", "‘Đây là đâu?’"), _row(1, "thought", "‘Ai vậy?’")]
    result = _validate(group, {"segments": [_item(0, "thought", "UNKNOWN"), _item(1, "thought", "NARRATOR")]})
    assert result["s0"]["speaker"] == "NARRATOR" and result["s0"]["gender"] == "unknown"
    assert result["s1"]["speaker"] == "NARRATOR"
