"""Vá database.py + analysis.py: cụm trích nằm GIỮA một câu kể thì người nói là NGƯỜI KỂ, không phải nhân vật.

Chạy: python patch_a_term_quoted_mid_sentence_is_the_narrators_own_line.py <root>

## Vì sao (20-09, 10:2x)

`patch_a_quoted_term_is_not_the_paragraphs_line.py` (ranh giới 9) đã dạy host ĐỪNG khoá người nói cho những cụm trích
ấy - nhưng nó chỉ ngăn host gán SAI, còn câu trả lời của model thì vẫn đứng nguyên. Ở chương 426 lô 10:

  [8]  Lucien đương nhiên không thể bảo đây chỉ là một sở thích xấu bỗng nhiên phát tác của cậu. Nếu là   (kể)
  [9]  “Khoa Học”                                                                                        <- model: LUCIEN
  [10] thì đòi hỏi phải tạo ra từ mới và xác định ý nghĩa cho nó, còn                                    (kể)
  [11] “Tự Nhiên”                                                                                        <- model: LUCIEN
  [12] thì có thể trực tiếp trích dẫn mà sử dụng luôn.                                                   (kể)

Người kể đang gọi tên hai tập san giữa câu của chính mình; gán cho Lucien là đổi giọng hai lần giữa một câu. Đây là
kiểu lỗi lớn thứ tư của model ở lô 9: 17 trên 133 chỗ lệch.

Vá: sau mọi bản sửa khác, đoạn nào `_is_quoted_inside_a_sentence` nhận là cụm trích giữa câu kể thì người nói thành
NARRATOR, kèm dấu vết host `IN_SENTENCE_QUOTE_NARRATOR_NOTE` (để phản biện đạo diễn biết host đã sửa, y như bốn bản
sửa cũ). Loại đoạn KHÔNG đổi: bộ tách đoạn đã khoá nó là thoại, và đáp án chuẩn ghi đúng thế (`D NARRATOR`).

Đo trên CẢ 41 chương đáp án chuẩn: 29 đoạn bị luật này chạm, đáp án nhận NARRATOR **đủ điểm cả 29**, KHÔNG có đoạn
nào đáp án từ chối NARRATOR. (27 ở Throne of Magical Arcana, 1 Nageki no Bourei, 1 Đã bảo là cùng nhau tự sát.)
Đặt CUỐI chuỗi sửa để khoá đoạn văn và khoá thoại-nối-tiếp không ghi đè lại.
"""
import io
import sys
from pathlib import Path

root = Path(sys.argv[1])


def patch(path: Path, old: str, new: str) -> None:
    source = io.open(path, encoding="utf-8").read()
    assert source.count(old) == 1, f"khong khop mot lan duy nhat trong {path.name}: {old.splitlines()[0]!r}"
    io.open(path, "w", encoding="utf-8").write(source.replace(old, new, 1))
    print(f"da va {path}")


patch(
    root / "ebook_reader" / "database.py",
    '''CROWD_SPEAKER_LOCK_NOTE = "đã khóa người nói từ lời dẫn tập thể kế tiếp"''',
    '''CROWD_SPEAKER_LOCK_NOTE = "đã khóa người nói từ lời dẫn tập thể kế tiếp"
IN_SENTENCE_QUOTE_NARRATOR_NOTE = "đã trả cụm trích giữa câu kể về người kể"''',
)

patch(
    root / "ebook_reader" / "database.py",
    '''    CHAPTER_HEADING_NOTE,
    CROWD_SPEAKER_LOCK_NOTE,
)''',
    '''    CHAPTER_HEADING_NOTE,
    CROWD_SPEAKER_LOCK_NOTE,
    IN_SENTENCE_QUOTE_NARRATOR_NOTE,
)''',
)

patch(
    root / "ebook_reader" / "database.py",
    '''        PARAGRAPH_SPEAKER_LOCK_NOTE,
        CONTINUED_DIALOGUE_LOCK_NOTE,
    }
)''',
    '''        PARAGRAPH_SPEAKER_LOCK_NOTE,
        CONTINUED_DIALOGUE_LOCK_NOTE,
        IN_SENTENCE_QUOTE_NARRATOR_NOTE,
    }
)''',
)

patch(
    root / "ebook_reader" / "analysis.py",
    '''    ADDRESSEE_REPAIR_NOTE,
    ANALYSIS_ACTIVE_PRIDE_CUE_FRAGMENT,''',
    '''    ADDRESSEE_REPAIR_NOTE,
    IN_SENTENCE_QUOTE_NARRATOR_NOTE,
    ANALYSIS_ACTIVE_PRIDE_CUE_FRAGMENT,''',
)

patch(
    root / "ebook_reader" / "analysis.py",
    '''    CONTINUED_DIALOGUE_LOCK_NOTE: "continued_dialogue",
}''',
    '''    CONTINUED_DIALOGUE_LOCK_NOTE: "continued_dialogue",
    IN_SENTENCE_QUOTE_NARRATOR_NOTE: "in_sentence_quote",
}''',
)

patch(
    root / "ebook_reader" / "analysis.py",
    '''    _repair_continued_dialogue_speakers(group, result)
    _canonicalize_analysis_notes(result)''',
    '''    _repair_continued_dialogue_speakers(group, result)
    # CUỐI chuỗi sửa: hai khoá trên (đoạn văn, thoại nối tiếp) sẽ ghi đè nếu chạy sau.
    _repair_in_sentence_quote_speakers(group, result)
    _canonicalize_analysis_notes(result)''',
)

patch(
    root / "ebook_reader" / "analysis.py",
    '''def _repair_same_paragraph_speakers(''',
    '''def _repair_in_sentence_quote_speakers(
    group: list[Any],
    result: dict[str, dict[str, Any]],
) -> None:
    """Cụm trích giữa một câu kể là chữ của NGƯỜI KỂ: "...không thể bảo đây là “Khoa Học” thì đòi hỏi...".

    Đo trên 41 chương đáp án chuẩn: 29 đoạn bị chạm, đáp án nhận NARRATOR đủ điểm cả 29, không đoạn nào từ chối.
    Loại đoạn để nguyên - bộ tách đoạn đã khoá là thoại, và đáp án ghi đúng thế.
    """
    for index, row in enumerate(group):
        data = result.get(str(row["stable_id"]))
        if data is None or data["kind"] != "dialogue":
            continue
        if normalize_speaker_name(str(data["speaker"])) == "narrator":
            continue
        if not _is_quoted_inside_a_sentence(group, index, result):
            continue
        data["speaker"] = "NARRATOR"
        _record_host_note_marker(data, IN_SENTENCE_QUOTE_NARRATOR_NOTE)


def _repair_same_paragraph_speakers(''',
)

test = root / "tests" / "test_a_term_quoted_mid_sentence_is_the_narrators_own_line.py"
test.write_text('''"""Cụm trích giữa câu kể trả về NGƯỜI KỂ; câu thoại thật thì không bị chạm."""
from __future__ import annotations

from ebook_reader.analysis import _repair_in_sentence_quote_speakers
from ebook_reader.database import IN_SENTENCE_QUOTE_NARRATOR_NOTE


def row(stable_id: str, paragraph: int, text: str) -> dict[str, object]:
    return {"stable_id": stable_id, "chapter_id": 1, "paragraph_index": paragraph, "text": text}


def data(kind: str, speaker: str) -> dict[str, object]:
    return {"kind": kind, "speaker": speaker, "personality_hint": "", "notes": ""}


def test_a_term_between_two_halves_of_a_sentence_goes_back_to_the_narrator() -> None:
    group = [
        row("a", 3, "Lucien không thể bảo rằng nếu là"),
        row("b", 3, "“Khoa Học”"),
        row("c", 3, "thì đòi hỏi phải tạo ra từ mới."),
    ]
    result = {"a": data("narration", "NARRATOR"), "b": data("dialogue", "LUCIEN"),
              "c": data("narration", "NARRATOR")}
    _repair_in_sentence_quote_speakers(group, result)
    assert result["b"]["speaker"] == "NARRATOR"
    assert IN_SENTENCE_QUOTE_NARRATOR_NOTE in result["b"]["_host_note_markers"]


def test_a_real_line_keeps_its_speaker() -> None:
    group = [
        row("a", 3, "Lucien mỉm cười nói:"),
        row("b", 3, "“Tôi đã tìm ra lời giải.”"),
        row("c", 4, "Cả phòng lặng đi."),
    ]
    result = {"a": data("narration", "NARRATOR"), "b": data("dialogue", "LUCIEN"),
              "c": data("narration", "NARRATOR")}
    _repair_in_sentence_quote_speakers(group, result)
    assert result["b"]["speaker"] == "LUCIEN"
    assert "_host_note_markers" not in result["b"]


def test_a_term_in_another_paragraph_is_not_touched() -> None:
    group = [
        row("a", 3, "Lucien không thể bảo rằng nếu là"),
        row("b", 4, "“Khoa Học”"),
        row("c", 5, "thì đòi hỏi phải tạo ra từ mới."),
    ]
    result = {"a": data("narration", "NARRATOR"), "b": data("dialogue", "LUCIEN"),
              "c": data("narration", "NARRATOR")}
    _repair_in_sentence_quote_speakers(group, result)
    assert result["b"]["speaker"] == "LUCIEN"
''', encoding="utf-8")
print(f"da viet {test}")
