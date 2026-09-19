"""Vá analysis.py: khoá "một đoạn văn một người nói" không nuốt cụm trích NẰM GIỮA một câu kể.

Chạy: python patch_a_quoted_term_is_not_the_paragraphs_line.py <root>

## Vì sao (20-09, 01:2x)

Phát lại MỌI chương đáp án chuẩn (16 chương, 6 truyện) qua đúng khâu phân tích sản xuất với câu trả lời đúng: năm truyện
ra 100 điểm; cuốn 2 trượt ở bốn kiểu host đè đáp án - ba kiểu đã có bản vá trong hàng chờ (nội tâm về người kể, "Lo" là
tên, "chưa kịp" ...). Kiểu thứ tư là cái này. TMA 419, đoạn văn 13:

    “Đào tạo nhân công lành nghề với số lượng lớn sẽ mất rất nhiều thời gian…” Arthur không hiểu “dây chuyền lắp ráp”
    hay “tiêu chuẩn hóa” là gì, nhưng tạm thời ông cũng không có hứng hỏi...

Parser khoá hai thuật ngữ trong ngoặc là thoại. Model (và đáp án, quy tắc 8 của docs/GOLD_GUIDE.md) để chúng cho người
kể - đổi giọng giữa một câu kể là sai. Nhưng `_repair_same_paragraph_speakers` thấy đoạn văn có một người nói được neo
(Arthur, nhờ lời dẫn sau câu đầu) và gán MỌI câu thoại khác trong đoạn cho Arthur: người nghe đọc câu kể bằng giọng người
kể, tới hai chữ "dây chuyền lắp ráp" thì đổi sang giọng Arthur, rồi đổi lại.

Hai cuốn sản xuất có 561 cụm trích nằm giữa câu kể như thế (câu kể trước không kết thúc bằng dấu câu, câu kể sau mở bằng
chữ thường hay dấu phẩy: “phấn khích”, “mực ma thuật”, “ngài X”, “số”, “bất lực”, “giận”, “tuần”...), khoảng 66 cụm nằm
trong đoạn có người nói được neo và bị khoá như trên. Luật mới: cụm trích nằm giữa một câu kể không tham gia khoá theo
đoạn - câu trả lời của model và lượt phản biện quyết. Câu thoại đứng riêng (có dấu câu kết thúc trước nó, hay là cuối
đoạn) vẫn khoá như cũ.
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


replace_once('''def _repair_same_paragraph_speakers(
    group: list[Any],
    result: dict[str, dict[str, Any]],
) -> None:
    by_paragraph: dict[tuple[int, int], list[tuple[Any, dict[str, Any]]]] = defaultdict(list)
    for row in group:
        data = result.get(str(row["stable_id"]))
        if data is None or data["kind"] != "dialogue":
            continue
''', '''IN_SENTENCE_QUOTE_OPEN_ENDINGS = tuple(".!?…:;\\"”’)")


def _is_quoted_inside_a_sentence(
    group: list[Any],
    index: int,
    result: dict[str, dict[str, Any]],
) -> bool:
    """Cụm trích nằm GIỮA một câu kể: "Arthur không hiểu “dây chuyền lắp ráp” hay ...".

    Câu kể trước chưa kết thúc (không có dấu câu cuối) và câu kể sau nối tiếp nó (mở bằng chữ thường hay dấu câu), cùng
    một đoạn văn. Đó là chữ của người kể trích lời/thuật ngữ, không phải một câu thoại của người nói trong đoạn.

    Lô phân tích chỉ có vài đoạn, nên cụm trích ở MÉP lô chỉ thấy một phía (TMA 419:26 là đoạn cuối lô của nó). Khi ấy
    phía nhìn thấy phải khớp, và cụm trích phải có dáng thuật ngữ - không kết thúc bằng dấu câu như một câu nói
    (“Đi thôi,” hắn nói. vẫn là câu thoại).
    """
    row = group[index]
    quoted = str(row["text"]).strip().strip("“”\\"'‘’").rstrip()
    if not quoted or quoted.endswith((",", ".", "!", "?", "…")):
        return False
    before = group[index - 1] if index > 0 else None
    after = group[index + 1] if index + 1 < len(group) else None
    if before is None and after is None:
        return False
    for neighbour in (before, after):
        if neighbour is None:
            continue
        data = result.get(str(neighbour["stable_id"]))
        if data is None or data["kind"] != "narration" or not _same_paragraph(neighbour, row):
            return False
    if before is not None and str(before["text"]).rstrip().endswith(IN_SENTENCE_QUOTE_OPEN_ENDINGS):
        return False
    if after is not None:
        first = str(after["text"]).lstrip()[:1]
        if not (first.islower() or first in ",;.)?!…"):
            return False
    return True


def _repair_same_paragraph_speakers(
    group: list[Any],
    result: dict[str, dict[str, Any]],
) -> None:
    by_paragraph: dict[tuple[int, int], list[tuple[Any, dict[str, Any]]]] = defaultdict(list)
    for index, row in enumerate(group):
        data = result.get(str(row["stable_id"]))
        if data is None or data["kind"] != "dialogue":
            continue
        if _is_quoted_inside_a_sentence(group, index, result):
            # Chữ của người kể trích giữa câu (quy tắc 8 của đáp án chuẩn) - không phải câu của người nói trong đoạn.
            continue
''')
io.open(p, "w", encoding="utf-8").write(s)
print(f"da va {p}")

test = root / "tests" / "test_a_quoted_term_is_not_the_paragraphs_line.py"
test.write_text('''"""Khoá "một đoạn văn một người nói" không nuốt cụm trích nằm giữa một câu kể (đáp án chuẩn TMA 419:24, 26)."""
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
''', encoding="utf-8")
print(f"da viet {test}")
