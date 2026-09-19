"""Vá analysis.py: câu nội tâm (kind=thought) GIỮ người đang nghĩ mà model đã nhận ra; chỉ câu không ai nhận mới về người kể.

Chạy: python patch_a_thought_keeps_its_thinker.py <root>

## Vì sao (20-09, 00:5x)

**Quyết định của chủ sách, 20-09 ~01:00**: *"lần trước tôi nói giọng nội tâm bất kể của ai thì đều do người kể đọc,
nhưng giờ tôi nghĩ lại rồi, giọng ai thì chính người đó đọc"*. Dòng trong `_validate` dưới đây chính là quyết định cũ
ấy; bản vá này thực thi quyết định mới. Lô đã thu vẫn đọc nội tâm bằng người kể cho tới khi được đúc lại.

Lịch sử: 7e4d74c (31-08, "give a thought back to whoever is thinking it") sửa theo lời người nghe: nội tâm của một nhân vật
đang bị đọc bằng giọng người khác. Commit ấy ghi đã gỡ quy tắc "nội tâm = người kể" ở BA chỗ - prompt, một lệnh SQL
(`normalize_thought_speakers`), mốc chấm cảm nhận. Còn một chỗ thứ TƯ bị sót, trong `_validate`:

    if kind in {"narration", "thought"}:
        speaker = "NARRATOR"

Nên từ 31-08 đến nay, prompt dặn model trả người đang nghĩ (quy tắc 3 của SYSTEM_PROMPT), model trả đúng, rồi host
vứt đi. Bắt được nhờ `scripts/model_eval/gold_replay.py`: phát lại đáp án chuẩn qua đúng khâu phân tích sản xuất,
10/10 câu nội tâm của chương 344-347 (Eric, Chloe, Sonia, Felipe, Lauren) ra NARRATOR - tức điểm "người nói" bị chặn
trần ~92% bất kể model giỏi đến đâu.

Luật mới: thought giữ speaker như dialogue (chuẩn hoá tên, NPC cục bộ được gắn scope); thought mà speaker trống,
UNKNOWN hoặc NARRATOR thì về NARRATOR - đúng như docstring của `normalize_thought_speakers`: "an unidentified thinker
has no voice to use". Lời kể (narration) vẫn luôn là NARRATOR.
"""
import io
import sys
from pathlib import Path

root = Path(sys.argv[1])
p = root / "ebook_reader" / "analysis.py"
s = io.open(p, encoding="utf-8").read()


def replace_once(old: str, new: str) -> None:
    global s
    assert s.count(old) == 1, f"khong khop mot lan duy nhat: {old.splitlines()[0]!r}"
    s = s.replace(old, new, 1)


replace_once('''        if kind in {"narration", "thought"}:
            speaker = "NARRATOR"
            gender = "unknown"
            age = "unknown"
        else:
            speaker = _canonical_local_request(speaker, gender)
            speaker = _scope_local_speaker(speaker, rows_by_id[seg_id], local_scope)''', '''        # Lời kể luôn là của người kể. Nội tâm là của người đang nghĩ (7e4d74c, 31-08) - chỉ khi model không
        # nhận ra ai nghĩ thì mới về người kể. Dòng cũ gộp cả hai thành NARRATOR và là chỗ thứ tư 7e4d74c bỏ sót.
        unattributed_thought = kind == "thought" and speaker.casefold() in {"", "narrator", "unknown"}
        if kind == "narration" or unattributed_thought:
            speaker = "NARRATOR"
            gender = "unknown"
            age = "unknown"
        else:
            speaker = _canonical_local_request(speaker, gender)
            speaker = _scope_local_speaker(speaker, rows_by_id[seg_id], local_scope)''')
io.open(p, "w", encoding="utf-8").write(s)
print(f"da va {p}")

# Test cũ (a899001, 03-08) khoá đúng hành vi mà 7e4d74c định gỡ - chỗ thứ năm bị sót. Viết lại theo luật mới,
# giữ nguyên hai nửa đầu (nội tâm NARRATOR/UNKNOWN vẫn về người kể).
tp = root / "tests" / "test_analysis_required.py"
ts = io.open(tp, encoding="utf-8").read()
old_test = """def test_every_thought_uses_narrator_without_character_identity() -> None:"""
new_test = """def test_a_thought_uses_the_narrator_only_when_nobody_is_thinking_it() -> None:"""
assert ts.count(old_test) == 1
ts = ts.replace(old_test, new_test, 1)
old_tail = '''    character_thought = {**narrator_thought, "speaker": "Alisa", "gender": "female"}
    validated = _validate([row], {"segments": [character_thought]})

    assert validated[row["stable_id"]]["kind"] == "thought"
    assert validated[row["stable_id"]]["speaker"] == "NARRATOR"
    assert validated[row["stable_id"]]["gender"] == "unknown"'''
new_tail = '''    # 7e4d74c (31-08): nội tâm là của người đang nghĩ và đọc bằng giọng người ấy. Test này (03-08) từng khoá
    # điều ngược lại, cùng với dòng trong `_validate` mà 7e4d74c bỏ sót.
    character_thought = {**narrator_thought, "speaker": "Alisa", "gender": "female"}
    validated = _validate([row], {"segments": [character_thought]})

    assert validated[row["stable_id"]]["kind"] == "thought"
    assert validated[row["stable_id"]]["speaker"] == "Alisa"
    assert validated[row["stable_id"]]["gender"] == "female"'''
assert ts.count(old_tail) == 1, "khong khop duoi test cu"
ts = ts.replace(old_tail, new_tail, 1)
io.open(tp, "w", encoding="utf-8").write(ts)
print(f"da sua {tp}")

test = root / "tests" / "test_a_thought_keeps_its_thinker.py"
test.write_text('''"""Câu nội tâm giữ người đang nghĩ; chỉ câu nội tâm không ai nhận mới về người kể (7e4d74c + chỗ bị sót)."""
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
''', encoding="utf-8")
print(f"da viet {test}")
