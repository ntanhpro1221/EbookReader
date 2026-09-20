"""Vá analysis.py + database.py: đoạn `thought` nằm NGOÀI mọi nhịp ngoặc thì đọc bằng giọng người kể.

Chạy: python patch_a_thought_outside_every_quote_belongs_to_the_narrator.py <root>

## Luật này đến từ đâu: lỗi mà NHIỀU MODEL CÙNG MẮC (21-09 04:3x)

Lượt so model 21-09 cho một nguồn dữ liệu mới: ba model trả lời CÙNG bốn chương đáp án. Lỗi chỉ một model
mắc là chuyện của model ấy; lỗi **mọi model cùng mắc** là chỗ luật host còn thiếu, và vá host thì mọi model
đều lợi. Trên 177 đoạn cả ba đều trả lời: 17 đoạn mọi model cùng sai người nói, và lớp lớn nhất là

    363:70  thought  LUCIEN   | Ở giữa không trung, ngay trên đầu Bellak, Lucien Evans thật xuất hiện...
    363:71  thought  LUCIEN   | Một tia không màu, không mùi, cũng không phát sáng nhanh chóng bắn thẳng vào Bellak.
    363:72  thought  LUCIEN   | Trước loại tia ma thuật đem lại dự cảm nguy hiểm này, hắn không dám bất cẩn...

Đây là **lời kể ngôi ba** về việc bên ngoài. Bộ tách đoạn gọi chúng là `thought` (hint bất biến, host không
được đổi), nên cái sai duy nhất còn sửa được là NGƯỜI NÓI: model nêu một người nghĩ, và host tin người được
nêu - đúng theo quyết định 20-09 "nội tâm đọc bằng giọng người đang nghĩ". Quyết định ấy đúng cho nội tâm
thật; chỗ này thì không có nội tâm nào.

## Ba phép thử, hai cái đầu BỊ LOẠI - ghi lại để không ai thử lại

1. **"hint=narration thì không được thành thought"**: qua cổng đáp án (đáp án chưa bao giờ ĐÒI thought:
   1.283 dòng hint=narration, chỉ 40 dòng đáp án *cho phép* thought và cả 40 vẫn nhận narration) nhưng
   **lợi = 0** và cả sách chỉ 23 đoạn khớp. Sai địa chỉ: 363:70-72 có hint là `thought`, không phải narration.
2. **"thought không có đại từ ngôi thứ nhất thì về người kể"**: **PHÁ 29 dòng đáp án**. Tiếng Việt cho trống
   chủ ngữ, nên nội tâm thật thường chẳng có ngôi 1 nào: `‘Không, chắc chắn sai ở đâu rồi.’` (344:59, CHLOE).
3. **"thought ngoài mọi nhịp ngoặc"** - cái được chọn. Nội tâm trực tiếp trong sách này luôn nằm trong ngoặc
   ‘…’ hoặc “…”, còn ba dòng 363:70-72 thì không có ngoặc nào.

Phải đếm theo **nhịp** chứ không theo từng đoạn: bản chỉ xét một đoạn PHÁ 6 dòng, cả 6 là đoạn NỐI của một
lượt nội tâm nhiều đoạn - `Phải xử lý việc này trước.’` (381:89) đóng ngoặc mà ngoặc mở nằm ở đoạn trước.
Cùng lối `_repair_continued_dialogue_speakers` đã dùng cho thoại nối.

## Số đo của bản được chọn

| | |
|---|---|
| lợi, `qwen3:8b` trên 4 chương đáp án | **sửa 11, phá 0** |
| lợi, `gemma4:e2b-it-qat` | **sửa 11, phá 0** |
| cổng phát lại ĐÁP ÁN, 41 chương | 12 dòng bị chạm, **0 dòng mất điểm** |
| sách thật 11 lô (49.991 đoạn) | **3 đoạn** (0,006%) - LEVSKI 423:217, LUCIEN 444:13 và 480:24 |

Nói thẳng: nó **không cứu sản xuất hôm nay**. Ba dòng. Lý do ghim nó vẫn là lý do tốt: giá 0 (phá 0 câu
đúng trên 41 chương đáp án), và giá trị của nó tăng đúng lúc ta đổi model - trong lượt đo thì CẢ HAI model
có đủ dữ liệu đều mắc 11 lần chỉ trên 4 chương, tức đây là một cái bẫy đang chờ sẵn cho mọi model tương lai.

## Chỗ đặt: CUỐI chuỗi sửa

Sau `_repair_in_sentence_quote_speakers`, vì hai khoá đoạn-văn và thoại-nối-tiếp sẽ ghi đè nếu chúng chạy
sau - đúng lý do dòng chú thích đã có ở đó. `database.py` chỉ thêm MỘT hằng số ghi chú, không chạm ba cổng
bằng chứng.
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
    '''IN_SENTENCE_QUOTE_NARRATOR_NOTE = "đã trả cụm trích giữa câu kể về người kể"''',
    '''IN_SENTENCE_QUOTE_NARRATOR_NOTE = "đã trả cụm trích giữa câu kể về người kể"
THOUGHT_OUTSIDE_QUOTES_NARRATOR_NOTE = "đã trả đoạn nội tâm ngoài mọi nhịp ngoặc về người kể"''',
)

patch(
    root / "ebook_reader" / "database.py",
    '''ANALYSIS_HOST_NOTE_MARKERS = (
    EXPLICIT_ATTRIBUTION_NOTE,''',
    '''ANALYSIS_HOST_NOTE_MARKERS = (
    THOUGHT_OUTSIDE_QUOTES_NARRATOR_NOTE,
    EXPLICIT_ATTRIBUTION_NOTE,''',
)

patch(
    root / "ebook_reader" / "analysis.py",
    '''    IN_SENTENCE_QUOTE_NARRATOR_NOTE,''',
    '''    IN_SENTENCE_QUOTE_NARRATOR_NOTE,
    THOUGHT_OUTSIDE_QUOTES_NARRATOR_NOTE,''',
)

patch(
    root / "ebook_reader" / "analysis.py",
    '''    IN_SENTENCE_QUOTE_NARRATOR_NOTE: "in_sentence_quote",
}''',
    '''    IN_SENTENCE_QUOTE_NARRATOR_NOTE: "in_sentence_quote",
    THOUGHT_OUTSIDE_QUOTES_NARRATOR_NOTE: "thought_outside_quotes",
}''',
)

patch(
    root / "ebook_reader" / "analysis.py",
    '''def _repair_same_paragraph_speakers(''',
    '''# Mỗi truyện viết nội tâm bằng một loại ngoặc khác nhau, và bỏ sót một loại là trả nội tâm thật về
# người kể. `(`/`)` nằm đây vì `yamiyo_no_hotaru` dùng CHÚNG cho nội tâm - cổng phát lại đáp án bắt được
# đúng ba dòng (155:10, 155:12 của TAMAKI và 189:117 của TOMOBE) khi bản đầu của luật này còn thiếu chúng.
QUOTE_SPAN_OPENERS = "\\u2018\\u201c\\u300c\\u300e\\u00ab(\\uff08\\u3014"
QUOTE_SPAN_CLOSERS = "\\u2019\\u201d\\u300d\\u300f\\u00bb)\\uff09\\u3015"
QUOTE_SPAN_NEUTRAL = "\\"'"


def _segments_outside_every_quote_span(group: list[Any]) -> list[bool]:
    """Đoạn nào nằm NGOÀI mọi nhịp ngoặc, kể cả nhịp mở ở đoạn trước và đóng ở đoạn sau.

    Phải đếm theo nhịp: bản chỉ xét từng đoạn riêng lẻ phá 6 dòng đáp án, cả 6 là đoạn NỐI của một lượt
    nội tâm nhiều đoạn (`Phải xử lý việc này trước.’` ở 381:89 đóng một ngoặc mở từ đoạn trước).
    Ngoặc "trung tính" (`"` và `'`) không nói được mở hay đóng, nên chỉ cần CÓ là đã coi là trong nhịp.

    Danh sách ngoặc phải phủ MỌI truyện, không chỉ cuốn đang thu: `yamiyo_no_hotaru` viết nội tâm bằng
    `( … )`, và bản đầu thiếu chúng đã trả ba dòng nội tâm thật về người kể - cổng phát lại đáp án bắt được.
    """
    flags: list[bool] = []
    depth = 0
    for row in group:
        text = str(row["text"] or "")
        inside = depth > 0 or any(
            character in text
            for character in QUOTE_SPAN_OPENERS + QUOTE_SPAN_CLOSERS + QUOTE_SPAN_NEUTRAL
        )
        flags.append(not inside)
        for character in text:
            if character in QUOTE_SPAN_OPENERS:
                depth += 1
            elif character in QUOTE_SPAN_CLOSERS:
                depth = max(0, depth - 1)
    return flags


def _repair_thought_outside_quotes(
    group: list[Any],
    result: dict[str, dict[str, Any]],
) -> None:
    """Đoạn `thought` không nằm trong nhịp ngoặc nào thì không phải nội tâm của ai - về người kể.

    Nội tâm đọc bằng giọng người đang nghĩ (quyết định 20-09), và luật này KHÔNG chạm nội tâm thật: nội tâm
    trực tiếp của sách này luôn có ngoặc ‘…’ hay “…”. Thứ nó chạm là lời kể ngôi ba mà bộ tách đoạn đã gọi là
    `thought` - hint bất biến nên loại đoạn giữ nguyên, chỉ người nói trả về NARRATOR.

    Rút ra từ lỗi NHIỀU MODEL CÙNG MẮC (lượt so model 21-09): `qwen3:8b` và `gemma4:e2b-it-qat` mỗi model
    sửa 11 phá 0 trên 4 chương đáp án; cổng phát lại đáp án 41 chương: 12 đoạn bị chạm, 0 đoạn mất điểm.
    Trong sách thật 11 lô thì chỉ 3 đoạn - nó là bảo hiểm cho lần đổi model, không phải cứu hộ hôm nay.
    """
    for row, outside in zip(group, _segments_outside_every_quote_span(group)):
        data = result.get(str(row["stable_id"]))
        if data is None or data["kind"] != "thought" or not outside:
            continue
        if normalize_speaker_name(str(data["speaker"])) in {"narrator", "unknown", ""}:
            continue
        data["speaker"] = "NARRATOR"
        data["gender"] = "unknown"
        data["age"] = "unknown"
        _record_host_note_marker(data, THOUGHT_OUTSIDE_QUOTES_NARRATOR_NOTE)


def _repair_same_paragraph_speakers(''',
)

patch(
    root / "ebook_reader" / "analysis.py",
    '''    # CUỐI chuỗi sửa: hai khoá trên (đoạn văn, thoại nối tiếp) sẽ ghi đè nếu chạy sau.
    _repair_in_sentence_quote_speakers(group, result)''',
    '''    # CUỐI chuỗi sửa: hai khoá trên (đoạn văn, thoại nối tiếp) sẽ ghi đè nếu chạy sau.
    _repair_in_sentence_quote_speakers(group, result)
    _repair_thought_outside_quotes(group, result)''',
)

test = root / "tests" / "test_a_thought_outside_every_quote_belongs_to_the_narrator.py"
test.write_text('''"""Đoạn `thought` ngoài mọi nhịp ngoặc đọc bằng giọng người kể; nội tâm trong ngoặc giữ người nghĩ.

Ca thật (lượt so model 21-09, chương 363 đoạn 70-72): ba model cùng gán LUCIEN làm người nghĩ cho lời kể
ngôi ba về việc bên ngoài - "Một tia không màu... bắn thẳng vào Bellak." Bộ tách đoạn gọi chúng là `thought`
nên loại đoạn bất biến; chỉ người nói sửa được.

Đoạn NỐI của một lượt nội tâm nhiều đoạn phải được giữ: `Phải xử lý việc này trước.’` (381:89) đóng một
ngoặc mở từ đoạn trước, và bản luật chỉ-xét-một-đoạn đã phá đúng 6 dòng đáp án như thế.
"""
from __future__ import annotations

from ebook_reader.analysis import (
    _repair_thought_outside_quotes,
    _segments_outside_every_quote_span,
)


def _row(stable_id: str, text: str) -> dict:
    return {"stable_id": stable_id, "text": text}


def test_a_quote_span_covers_the_segments_between_its_ends() -> None:
    group = [
        _row("s1", "Hắn nhíu mày."),
        _row("s2", "\\u2018Không được... Không được ngủ."),
        _row("s3", "Phải xử lý việc này trước.\\u2019"),
        _row("s4", "Ánh sao ngưng tụ thành áo choàng."),
    ]
    assert _segments_outside_every_quote_span(group) == [True, False, False, True]


def test_the_narration_the_parser_called_a_thought_goes_back_to_the_narrator() -> None:
    group = [_row("s1", "Một tia không màu, không mùi bắn thẳng vào Bellak.")]
    result = {"s1": {"kind": "thought", "speaker": "LUCIEN", "gender": "male", "age": "adult"}}
    _repair_thought_outside_quotes(group, result)
    assert result["s1"]["speaker"] == "NARRATOR"
    assert result["s1"]["gender"] == "unknown"
    assert result["s1"]["kind"] == "thought", "hint là ranh giới nguồn bất biến - loại đoạn KHÔNG đổi"


def test_real_inner_speech_keeps_its_thinker() -> None:
    group = [_row("s1", "\\u2018Không, chắc chắn sai ở đâu rồi!\\u2019")]
    result = {"s1": {"kind": "thought", "speaker": "CHLOE", "gender": "female", "age": "adult"}}
    _repair_thought_outside_quotes(group, result)
    assert result["s1"]["speaker"] == "CHLOE", "nội tâm đọc bằng giọng người đang nghĩ (20-09)"


def test_a_continuation_segment_of_one_inner_speech_keeps_its_thinker() -> None:
    group = [
        _row("s1", "\\u2018Ma cà rồng bình thường biến mất thì chẳng có gì to tát."),
        _row("s2", "Phải xử lý việc này trước.\\u2019"),
    ]
    result = {
        "s1": {"kind": "thought", "speaker": "LUCIEN", "gender": "male", "age": "adult"},
        "s2": {"kind": "thought", "speaker": "LUCIEN", "gender": "male", "age": "adult"},
    }
    _repair_thought_outside_quotes(group, result)
    assert [result[key]["speaker"] for key in ("s1", "s2")] == ["LUCIEN", "LUCIEN"]


def test_dialogue_and_narration_are_untouched() -> None:
    group = [_row("s1", "Hắn bước tới cửa."), _row("s2", "Hắn nói gì đó.")]
    result = {
        "s1": {"kind": "narration", "speaker": "NARRATOR", "gender": "unknown", "age": "unknown"},
        "s2": {"kind": "dialogue", "speaker": "LUCIEN", "gender": "male", "age": "adult"},
    }
    _repair_thought_outside_quotes(group, result)
    assert result["s2"]["speaker"] == "LUCIEN"
''', encoding="utf-8")
print(f"da viet {test}")
