"""Vá analysis.py: luật host "tên đứng đầu câu kể sau câu thoại là người nói" biết lúc nào phải im.

Chạy: python patch_the_name_after_a_quote_is_not_always_its_speaker.py <root>

## Vì sao (20-09, 01:0x)

`_explicit_speaker_attribution` khoá người nói của một câu thoại bằng tên riêng mở đầu câu kể ngay sau nó, cùng đoạn văn
(“…” Lucien nói.). Luật này đè lên câu trả lời của model. Đo trên toàn bộ đáp án chuẩn (vòng 1-5, 16 chương, 6 truyện):
nó bắn 52 lần, đúng 50 - đáng giữ. Hai lần sai cho thấy hai lỗ, và đếm trên cả hai cuốn sản xuất (7.374 lần bắn) cho
biết lỗ rộng cỡ nào:

1. **Chữ tiếng Việt đầu câu không phải tên.** "Lo lắng phu nhân Tess có thể mất kiểm soát..." (TMA 378:25, đáp án
   WELLS) thành người nói "Lo". `LATIN_PROPER_NAME_SURFACE_PATTERN` chỉ bắt chữ ASCII, nên chữ Việt có dấu tự thoát;
   chữ Việt KHÔNG dấu thì không: hai cuốn có ~40 lần như thế - Tay (trái), Cho (rằng), Y (đại từ "y"), Sinh (mệnh),
   Vong (linh), Lo (lắng), Xem (chừng), Hy (vọng), Uy (lực), Xung (quanh), May (thay), Ma (thuật), Xoa, Nhanh, So (với),
   Men (theo), Sao, Tra (khảo), Khe, Quai (hàm), Quay (người), Kim (giây), Ly (vang), Xe (bò). Mỗi lần là một "nhân vật"
   không tồn tại được giao một giọng. Thêm chúng vào `ATTRIBUTION_SENTENCE_START_EXCLUSIONS` - đúng cơ chế 4 mục cuối
   (Nghe, Tin, Giai, Im) đã dùng. Đã kiểm: không chữ nào xuất hiện viết hoa GIỮA câu như tên người trong hai cuốn (chỉ
   trong tựa/thuật ngữ: "Găng Tay Trắng", "Sao chủ", "Y Liệu"). Bỏ ngoài: Ham, Lich - có thể là nhân vật thật.
2. **Người được nêu tên CHƯA nói.** "Lucien còn chưa kịp làm gì khác, một giọng nói trang nghiêm... vọng đến" (TMA
   407:78, đáp án BEYER) khoá câu của Beyer cho Lucien. Hai cuốn có ~15 câu "X (còn) chưa kịp đáp / làm gì / phản ứng /
   đứng vững, Y đã..." - X là người NGHE, câu thoại là của Y hoặc của giọng mới. Nhưng "X chưa kịp nói dứt câu / nói gì
   thêm / dứt lời" thì X CHÍNH LÀ người vừa nói (bị ngắt) - giữ khoá. Luật mới: sau tên là "(còn) chưa/không kịp" mà
   không phải "nói dứt/nói hết/nói xong/nói thêm/nói tiếp/dứt lời" thì luật im, model quyết.

Im lặng ở đây nghĩa là giữ câu trả lời của model (và lượt phản biện), không đoán người khác. Không đụng hai cuốn cho tới
khi đúc lại: chỉ đổi kết quả phân tích của lô sau ranh giới.
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


replace_once('''ATTRIBUTION_SENTENCE_START_EXCLUSIONS = {
    "ban", "cung", "du", "khi", "luc", "neu", "ngoai", "sau", "suy", "thay",
    "theo", "trong", "truoc", "tuy", "vi",
    "giai", "im", "nghe", "tin",
}''', '''#
# Hàng cuối (20-09) cũng là ca thật, đếm trên cả hai cuốn: chữ Việt KHÔNG dấu mở câu kể sau câu thoại ("Lo lắng phu nhân
# Tess...", "Tay trái của Lucien...", "Y chỉ vào ghế...", "Cho rằng...") - khoảng 40 câu thành người nói không tồn tại.
# Không chữ nào viết hoa giữa câu như tên người trong hai cuốn. Ham và Lich cố ý để ngoài: có thể là nhân vật thật.
ATTRIBUTION_SENTENCE_START_EXCLUSIONS = {
    "ban", "cung", "du", "khi", "luc", "neu", "ngoai", "sau", "suy", "thay",
    "theo", "trong", "truoc", "tuy", "vi",
    "giai", "im", "nghe", "tin",
    "cho", "hy", "khe", "kim", "lo", "ly", "ma", "may", "men", "nhanh", "quai", "quay", "sao", "sinh", "so", "tay",
    "tra", "uy", "vong", "xe", "xem", "xoa", "xung", "y",
}
# "Lucien còn chưa kịp làm gì khác, một giọng nói... vọng đến": tên mở câu kể là người CHƯA nói - câu thoại trước là của
# người khác. Trừ khi cái chưa kịp chính là nói cho xong ("chưa kịp nói dứt câu", "chưa kịp dứt lời"): khi đó người
# được nêu tên đúng là người vừa nói và bị ngắt.
NOT_YET_SPOKEN_PATTERN = re.compile(
    r"^\\s*(?:còn\\s+)?(?:chưa|không)\\s+kịp\\s+"
    r"(?!nói\\s+(?:gì\\s+|được\\s+)?(?:thêm|hết|xong|dứt|tiếp)|dứt\\s+lời|nói\\s+dứt)",
    re.IGNORECASE,
)''')

replace_once('''def _trailing_speech_attribution(text: str) -> str | None:''', '''def _names_someone_who_had_not_spoken(text: str, name: str) -> bool:
    """Câu kể mở bằng `name` rồi "(còn) chưa kịp đáp/làm gì..." - người ấy chưa nói, câu thoại trước không phải của họ."""
    stripped = text.lstrip()
    if not stripped.startswith(name):
        return False
    return NOT_YET_SPOKEN_PATTERN.match(stripped[len(name) :]) is not None


def _trailing_speech_attribution(text: str) -> str | None:''')

replace_once('''        if following_data is not None and following_data["kind"] == "narration":
            attributed_speaker = _leading_proper_name(str(following["text"]))
            if attributed_speaker is None:''', '''        if following_data is not None and following_data["kind"] == "narration":
            attributed_speaker = _leading_proper_name(str(following["text"]))
            if attributed_speaker is not None and _names_someone_who_had_not_spoken(
                str(following["text"]), attributed_speaker
            ):
                # Im lặng, không đoán người khác: câu trả lời của model và lượt phản biện quyết.
                return None
            if attributed_speaker is None:''')
io.open(p, "w", encoding="utf-8").write(s)
print(f"da va {p}")

test = root / "tests" / "test_the_name_after_a_quote_is_not_always_its_speaker.py"
test.write_text('''"""Luật "tên đầu câu kể sau câu thoại là người nói" im khi tên là chữ Việt hoặc người ấy chưa nói (đáp án chuẩn 378, 407)."""
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
''', encoding="utf-8")
print(f"da viet {test}")
