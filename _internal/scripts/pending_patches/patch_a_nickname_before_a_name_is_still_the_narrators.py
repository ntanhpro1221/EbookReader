"""Vá analysis.py: cụm trích giữa câu kể vẫn là chữ của người kể khi câu kể SAU mở bằng một cái TÊN.

Chạy: python patch_a_nickname_before_a_name_is_still_the_narrators.py <root>

## Vì sao (20-09, 05:3x)

`_is_quoted_inside_a_sentence` (bản vá ranh giới 9) đòi hai điều: câu kể trước chưa kết thúc VÀ câu kể sau mở bằng chữ
thường hay dấu câu. Điều kiện thứ hai hỏng đúng lối viết đặt biệt danh trước tên:

    Sau khi thu xếp xong đồ đạc và uống một lọ thuốc để bảo vệ cổ họng, “Sơn Ca” Samantha rảo bước ra khỏi phòng chờ.
    Victor đã “bảo vệ” Lucien bằng rất nhiều lời cảnh báo.
    ...gần bằng với chốn “thiên đường trần gian” Đế chế Ma thuật cổ đại!

Câu kể sau mở bằng "Samantha", "Lucien", "Đế chế" - chữ hoa - nên luật không nhận ra cụm trích nằm giữa câu, và khoá
"một đoạn văn một người nói" lại gán cụm ấy cho người nói của đoạn (bắt được khi phát lại đáp án TMA 449:65: “Sơn Ca” ->
Samantha, đáp án là NARRATOR). Cuốn 2 có 23 chỗ như thế.

Luật mới: khi THẤY câu kể trước và nó chưa kết thúc câu (không có dấu câu cuối), thế là đủ - không đòi thêm gì ở câu kể
sau. Chỉ khi không thấy câu kể trước (cụm trích ở mép lô phân tích) mới cần câu kể sau mở bằng chữ thường hay dấu câu.
Điều kiện "dáng thuật ngữ" giữ nguyên: cụm trích không kết thúc bằng dấu câu như một câu nói, nên “Đi thôi,” hắn nói
vẫn là câu thoại.
"""
import io
import sys
from pathlib import Path

root = Path(sys.argv[1])
p = root / "ebook_reader" / "analysis.py"
s = io.open(p, encoding="utf-8").read()

old = '''    if before is not None and str(before["text"]).rstrip().endswith(IN_SENTENCE_QUOTE_OPEN_ENDINGS):
        return False
    if after is not None:
        first = str(after["text"]).lstrip()[:1]
        if not (first.islower() or first in ",;.)?!…"):
            return False
    return True'''
new = '''    if before is not None:
        if str(before["text"]).rstrip().endswith(IN_SENTENCE_QUOTE_OPEN_ENDINGS):
            return False
        # Câu kể trước chưa kết thúc: cụm trích nằm giữa câu, dù câu kể sau mở bằng một cái TÊN
        # (“Sơn Ca” Samantha rảo bước..., Victor đã “bảo vệ” Lucien bằng...). 23 chỗ như thế ở cuốn 2.
        return True
    first = str(after["text"]).lstrip()[:1]
    return bool(first.islower() or first in ",;.)?!…")'''
assert s.count(old) == 1, "khong khop mot lan duy nhat"
s = s.replace(old, new, 1)

# Cùng lỗi ấy đi qua HAI luật: khoá theo đoạn văn, và "tên đầu câu kể sau" (449:65 bị luật thứ hai lấy - câu kể sau mở
# bằng "Samantha rảo bước..."). Cụm trích giữa câu kể không phải một câu thoại, nên cả hai luật đều phải bỏ qua nó.
old_attribution = '''def _explicit_speaker_attribution(
    group: list[Any],
    index: int,
    result: dict[str, dict[str, Any]],
) -> str | None:
    row = group[index]
    data = result.get(str(row["stable_id"]))
    if data is None or data["kind"] != "dialogue":
        return None'''
new_attribution = '''def _explicit_speaker_attribution(
    group: list[Any],
    index: int,
    result: dict[str, dict[str, Any]],
) -> str | None:
    row = group[index]
    data = result.get(str(row["stable_id"]))
    if data is None or data["kind"] != "dialogue":
        return None
    if _is_quoted_inside_a_sentence(group, index, result):
        # Chữ của người kể trích giữa câu ("Sơn Ca” Samantha rảo bước...") - không phải câu thoại của ai.
        return None'''
assert s.count(old_attribution) == 1, "khong khop _explicit_speaker_attribution"
s = s.replace(old_attribution, new_attribution, 1)
io.open(p, "w", encoding="utf-8").write(s)
print(f"da va {p}")

test = root / "tests" / "test_a_nickname_before_a_name_is_still_the_narrators.py"
test.write_text('''"""Cụm trích giữa câu kể vẫn của người kể khi câu kể sau mở bằng một cái tên (đáp án chuẩn TMA 449:65)."""
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
''', encoding="utf-8")
print(f"da viet {test}")
