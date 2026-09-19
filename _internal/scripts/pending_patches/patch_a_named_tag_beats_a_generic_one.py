"""Vá analysis.py: lời dẫn có TÊN nhân vật thì luật "người nói chung chung" (người phụ nữ, cô gái...) phải im; và câu thoại
có lời dẫn riêng (câu kể liền trước kết thúc bằng dấu hai chấm) không bị khoá "một đoạn văn một người nói".

Chạy: python patch_a_named_tag_beats_a_generic_one.py <root>

## Vì sao (20-09, 01:5x)

Phát lại đáp án chuẩn vòng 8-9 (TMA 418, 426, 436) qua bộ phân tích đã vá đủ bảy bản trước vẫn trượt ba câu, hai luật:

1. `_generic_speaker_attribution` khoá câu thoại cho một NHÃN CHUNG khi câu kể liền trước kết thúc bằng ":" và có nhắc một
   danh từ trong `GENERIC_SPEAKER_TRAITS` - bất kể câu kể ấy nêu tên ai:

       Đứng trước hai người đàn ông và một người phụ nữ, James chỉ vào Lucien rồi nói:   -> "người phụ nữ"   (418:37)
       Người đàn ông trung niên có vẻ ngoài luộm thuộm, Salgueiro, cau mày nói:          -> NPC, không phải Salgueiro (426:22-23)

   Trên toàn bộ đáp án chuẩn luật này bắn 2 lần, sai cả 2. Trên cuốn 2 nó bắn 304 lần, phần lớn câu kể có tên riêng:
   "Chưa từng hẹn hò với bất kỳ cô gái nào trước đây, Lucien nói như tự giễu." -> "cô gái"; "Joanna cẩn thận hỏi người
   phụ nữ." -> người NGHE; "Felipe quay sang giới thiệu người đàn ông trung niên ..., sau đó nói tiếp." -> người được giới
   thiệu. Luật mới: câu kể có một tên nhân vật thật (chữ Latin viết hoa >= 3 chữ cái, không nằm trong danh sách loại trừ,
   không phải âm tiết tiếng Việt) thì im - model đọc được tên ấy. Nhãn chung chỉ còn khoá khi lời dẫn thật sự vô danh
   ("Một người phụ nữ trung niên bước tới nói:").

2. `_repair_same_paragraph_speakers` gán mọi câu thoại trong một đoạn văn cho người nói được neo. Nhưng một đoạn văn có thể
   chứa một lượt NGẮT lời:

       “Việc này…” Raventi đang định nói thêm, Florencia liền mỉm cười và cắt ngang: “Sau khi đọc [Tự Nhiên]...”   (436:61)

   Câu sau có lời dẫn RIÊNG (câu kể liền trước, cùng đoạn, kết thúc bằng ":") nên không phải "câu cùng người" của đoạn.
   Luật mới: câu thoại như thế không bị khoá theo đoạn - lời dẫn của nó (model, lượt phản biện, hay luật lời dẫn) quyết.
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


replace_once('''def _generic_speaker_attribution(text: str, *, prefer_last: bool) -> str | None:
    if (
        not text.rstrip().endswith((":", "："))
        and GENERIC_SPEECH_ATTRIBUTION_PATTERN.search(text) is None
    ):
        return None''', '''CHARACTER_NAME_IN_TEXT_PATTERN = re.compile(
    r"(?<![\\wÀ-ỹĐđ])[A-Z][a-z]{2,}(?:['’-][A-Za-z]+)*(?![\\wÀ-ỹĐđ])"
)


def _names_a_character(text: str) -> bool:
    """Câu kể có nêu tên một nhân vật thật (Latin viết hoa, >= 3 chữ cái, không phải chữ Việt hay từ loại trừ)."""
    for match in CHARACTER_NAME_IN_TEXT_PATTERN.finditer(text):
        key = _name_candidate_key(match.group(0))
        if (
            key not in NAME_CANDIDATE_EXCLUSIONS
            and key not in ATTRIBUTION_SENTENCE_START_EXCLUSIONS
            and not is_vietnamese_syllable(match.group(0))
        ):
            return True
    return False


def _generic_speaker_attribution(text: str, *, prefer_last: bool) -> str | None:
    if (
        not text.rstrip().endswith((":", "："))
        and GENERIC_SPEECH_ATTRIBUTION_PATTERN.search(text) is None
    ):
        return None
    if _names_a_character(text):
        # "..., James chỉ vào Lucien rồi nói:" có nhắc "người phụ nữ" vẫn là câu của James; "Joanna cẩn thận hỏi người
        # phụ nữ." - người phụ nữ là người NGHE. Lời dẫn có tên thì nhãn chung không được khoá; model đọc được tên.
        return None''')

replace_once('''        if _is_quoted_inside_a_sentence(group, index, result):
            # Chữ của người kể trích giữa câu (quy tắc 8 của đáp án chuẩn) - không phải câu của người nói trong đoạn.
            continue''', '''        if _is_quoted_inside_a_sentence(group, index, result):
            # Chữ của người kể trích giữa câu (quy tắc 8 của đáp án chuẩn) - không phải câu của người nói trong đoạn.
            continue
        if _has_its_own_speech_tag(group, index, result):
            # "Raventi đang định nói thêm, Florencia liền mỉm cười và cắt ngang: “...”" - một lượt ngắt lời trong cùng đoạn.
            continue''')

replace_once('''def _repair_same_paragraph_speakers(''', '''def _has_its_own_speech_tag(
    group: list[Any],
    index: int,
    result: dict[str, dict[str, Any]],
) -> bool:
    """Câu kể liền trước, cùng đoạn văn, kết thúc bằng dấu hai chấm: câu thoại này có lời dẫn riêng."""
    if index == 0:
        return False
    before, row = group[index - 1], group[index]
    data = result.get(str(before["stable_id"]))
    return bool(
        data is not None
        and data["kind"] == "narration"
        and _same_paragraph(before, row)
        and str(before["text"]).rstrip().endswith((":", "："))
    )


def _repair_same_paragraph_speakers(''')
io.open(p, "w", encoding="utf-8").write(s)
print(f"da va {p}")

test = root / "tests" / "test_a_named_tag_beats_a_generic_one.py"
test.write_text('''"""Lời dẫn có tên thì nhãn chung phải im; lời dẫn riêng thắng khoá theo đoạn (đáp án chuẩn TMA 418:37, 426:22, 436:61)."""
from __future__ import annotations

from ebook_reader.analysis import _generic_speaker_attribution, _validate


def _row(seq: int, kind_hint: str, text: str, paragraph: int = 3) -> dict:
    return {"stable_id": f"s{seq}", "kind_hint": kind_hint, "text": text, "chapter_id": 1, "seq": seq,
            "paragraph_index": paragraph}


def _item(seq: int, kind: str, speaker: str, gender: str = "male") -> dict:
    return {"id": f"s{seq}", "kind": kind, "speaker": speaker, "gender": gender, "age": "adult",
            "emotion": "neutral", "intensity": 0, "pace": "normal", "volume": "normal", "confidence": 0.9}


def test_a_named_tag_is_not_given_to_a_generic_label() -> None:
    for text in (
        "Đứng trước hai người đàn ông và một người phụ nữ, James chỉ vào Lucien rồi nói:",
        "Người đàn ông trung niên có vẻ ngoài luộm thuộm, Salgueiro, cau mày nói:",
        "Chưa từng hẹn hò với bất kỳ cô gái nào trước đây, Lucien nói như tự giễu:",
    ):
        assert _generic_speaker_attribution(text, prefer_last=True) is None, text


def test_an_anonymous_tag_still_gets_its_generic_label() -> None:
    assert _generic_speaker_attribution("Một người phụ nữ trung niên bước tới nói:", prefer_last=True) == "người phụ nữ"
    # "Người", "Nhìn" mở câu không phải tên.
    assert _generic_speaker_attribution("Nhìn đám đông, người đàn ông trung niên lặng lẽ thở dài:", prefer_last=True)


def test_the_model_keeps_the_named_speaker() -> None:
    group = [
        _row(0, "narration", "Người đàn ông trung niên có vẻ ngoài luộm thuộm, Salgueiro, cau mày nói:"),
        _row(1, "dialogue", "“Nhưng làm sao chúng ta có thể phân biệt được?”"),
    ]
    result = _validate(group, {"segments": [_item(0, "narration", "NARRATOR"), _item(1, "dialogue", "Salgueiro")]})
    assert result["s1"]["speaker"].casefold() == "salgueiro"


def test_an_interruption_in_the_same_paragraph_keeps_its_own_speaker() -> None:
    group = [
        _row(0, "dialogue", "“Việc này…”"),
        _row(1, "narration", "Raventi đang định nói thêm, Florencia liền mỉm cười và cắt ngang:"),
        _row(2, "dialogue", "“Sau khi đọc tập san, Oliver đồng tình với lập luận của cậu lắm đấy.”"),
    ]
    payload = {"segments": [
        _item(0, "dialogue", "Raventi"), _item(1, "narration", "NARRATOR"), _item(2, "dialogue", "Florencia", "female"),
    ]}
    result = _validate(group, payload)
    assert result["s0"]["speaker"].casefold() == "raventi"
    assert result["s2"]["speaker"].casefold() == "florencia"
''', encoding="utf-8")
print(f"da viet {test}")
