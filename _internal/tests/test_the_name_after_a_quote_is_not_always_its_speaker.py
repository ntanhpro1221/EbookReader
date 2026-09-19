"""Luật "tên đầu câu kể sau câu thoại là người nói" im khi tên là chữ Việt hoặc người ấy chưa nói (đáp án chuẩn 378, 407)."""
from __future__ import annotations

from ebook_reader.analysis import _leading_proper_name, _names_someone_who_had_not_spoken, _validate


def _row(seq: int, kind_hint: str, text: str) -> dict:
    return {"stable_id": f"s{seq}", "kind_hint": kind_hint, "text": text, "chapter_id": 1, "seq": seq,
            "paragraph_index": 7}


def _item(seq: int, kind: str, speaker: str, gender: str = "male") -> dict:
    return {"id": f"s{seq}", "kind": kind, "speaker": speaker, "gender": gender, "age": "adult",
            "emotion": "neutral", "intensity": 0, "pace": "normal", "volume": "normal", "confidence": 0.9}


def _speaker_of_the_quote(narration: str, model_says: str) -> str:
    group = [_row(0, "dialogue", "“Không ngờ ở đây lại có một mật thất đấy.”"), _row(1, "narration", narration)]
    result = _validate(group, {"segments": [_item(0, "dialogue", model_says), _item(1, "narration", "NARRATOR")]})
    return str(result["s0"]["speaker"]).casefold()


def test_a_vietnamese_word_opening_the_sentence_is_not_a_name() -> None:
    for text in ("Lo lắng phu nhân Tess có thể mất kiểm soát, ông vội nói.", "Tay trái của Lucien nắm chặt.",
                 "Y chỉ vào ghế sofa ở bên cạnh và nói.", "Cho rằng như vậy thật bất lịch sự, hắn nói.",
                 "Hy vọng tiêu tan, Beyer liền ngã xuống.", "Xung quanh đó là những con số."):
        assert _leading_proper_name(text) is None, text
    assert _leading_proper_name("Victor giải thích thêm một lần nữa.") == "Victor"
    assert _leading_proper_name("Ray nói, đánh trống lảng sang chuyện khác.") == "Ray"


def test_someone_who_had_not_spoken_yet_does_not_take_the_line() -> None:
    assert _names_someone_who_had_not_spoken("Lucien còn chưa kịp làm gì khác, một giọng nói vọng đến.", "Lucien")
    assert _names_someone_who_had_not_spoken("Lucien chưa kịp đáp, Jacob đã nói tiếp.", "Lucien")
    assert _names_someone_who_had_not_spoken("Fernando còn chưa kịp nói gì, Antec đã kêu lên.", "Fernando")
    # Bị ngắt khi đang nói: người được nêu tên CHÍNH là người vừa nói.
    assert not _names_someone_who_had_not_spoken("Lucien chưa kịp nói dứt câu, Natasha đã cắt ngang.", "Lucien")
    assert not _names_someone_who_had_not_spoken("Dieppe còn chưa kịp nói dứt lời, tiếng gầm vang lên.", "Dieppe")
    assert not _names_someone_who_had_not_spoken("Lucien còn chưa kịp nói gì thêm, Alferris đã chộp lấy.", "Lucien")
    assert not _names_someone_who_had_not_spoken("Fernando lặp lại, nhưng chưa kịp dứt lời.", "Fernando")


def test_the_model_keeps_the_line_when_the_named_person_had_not_spoken() -> None:
    narration = "Lucien còn chưa kịp làm gì khác, một giọng nói trang nghiêm bỗng vọng đến từ đầu bên kia."
    assert _speaker_of_the_quote(narration, "Beyer") == "beyer"


def test_the_named_person_still_takes_the_line_when_the_sentence_says_so() -> None:
    assert _speaker_of_the_quote("Lucien nói, giọng trầm xuống.", "Beyer") == "lucien"
    assert _speaker_of_the_quote("Lucien chưa kịp nói dứt câu, Natasha đã cắt ngang.", "Natasha") == "lucien"
