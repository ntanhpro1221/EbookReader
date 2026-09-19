"""Vá analysis.py: tên nước ngoài đứng ĐẦU CÂU vẫn được phiên âm sang tiếng Việt.

Chạy: python patch_a_name_at_the_start_of_a_sentence_is_still_a_name.py <root>

**XẾP Ở RANH GIỚI 9**, cùng lượt với `patch_the_better_known_voice_keeps_its_pin.py`. `analysis.py` nằm
trong `QUALITY_IMPLEMENTATION_FILES`; lô 9 đã phân tích bằng luật cũ.

## Vì sao (19-09, 21:4x)

Chủ sách hỏi VieNeu đọc tên tiếng Anh thế nào, rồi **chọn giữ phương pháp Việt hoá** (*"tôi vẫn chọn phương
pháp việt hoá"*). Đo trên lô 7/8: lớp phiên âm của dự án phủ 99,4% / 98,8% số lần tên nước ngoài xuất hiện;
phần còn lại đi NGUYÊN CHỮ vào VieNeu, sea-g2p đưa sang bộ máy tiếng Anh, và đọc kiểu Anh - có khi sai: đoạn
hỏng chương 370 `“Gauci Cromwell.”` được Whisper nghe "Gà Yusai Cromwell" vì G2P cắt `Gauci` thành "Gau"
(Việt) + "ci" (Anh, "yu-sai").

Chỗ lọt nằm ở `_name_candidate_contexts`: tên không phải người nói mà **chỉ xuất hiện ở đầu câu** bị bỏ
(`mid_sentence_occurrences == 0`). Luật ấy có từ 03-08 để chặn TỪ TIẾNG VIỆT viết hoa đầu câu ("May mắn thay",
"Xen lẫn") bị tưởng là tên. Sau đó `is_vietnamese_syllable` chặn từ tiếng Việt ngay trong `register()`, bất
kể vị trí - nên luật đầu câu chỉ còn một việc thật: chặn cụm "từ Việt + tên" ("Khi Lucien", "Nghe Morris",
"Do Chloe") mà mẫu tên Latin nuốt chung. Và nó làm việc ấy bằng cách vứt LUÔN tên nước ngoài thật đứng đầu câu.

Nên: ở đầu câu, **bóc các từ là âm tiết tiếng Việt đứng trước** ra khỏi cụm ("Khi Lucien" → "Lucien", tính là
giữa câu vì đứng sau một từ), rồi bỏ luật "phải có ở giữa câu". Đo trên chính hai lô (so ứng viên trước/sau):

    lô 7: 142 -> 147, thêm Beever, Miller, Haizz, Keke, Kekeke; mất: không
    lô 8: 166 -> 171, thêm Gauci Cromwell, Lydia, Max Planck, Morris Hoffenberg, Thomson; mất: không

Bỏ luật mà KHÔNG bóc thì thêm cả rác: "Khi Lucien", "Nghe Morris", "Anh Lucien", "Do Chloe", "Tim Lucien"...
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


replace_once('''def _name_candidate_contexts(rows: list[Any]) -> list[dict[str, Any]]:''', '''def _strip_sentence_initial_vietnamese(text: str, match: re.Match[str]) -> tuple[str, int]:
    """A capitalised run at the start of a sentence, with its leading Vietnamese words removed.

    The Latin-name pattern swallows a capitalised Vietnamese word together with the name after
    it - "Khi Lucien", "Nghe Morris", "Do Chloe" - because at the start of a sentence both are
    capitalised. Those words are Vietnamese syllables; stripping them leaves the name, which now
    stands after a word and so is not sentence-initial any more. A run made only of Vietnamese
    words keeps its last word, and `register()` rejects it as before.
    """
    surface, start = match.group(0), match.start()
    if not _is_sentence_initial_token(text, start):
        return surface, start
    words = list(re.finditer(r"\\S+", surface))
    index = 0
    while index < len(words) - 1 and is_vietnamese_syllable(words[index].group(0)):
        index += 1
    if index == 0:
        return surface, start
    return surface[words[index].start():], start + words[index].start()


def _name_candidate_contexts(rows: list[Any]) -> list[dict[str, Any]]:''')
replace_once('''            start = max(0, match.start() - 80)
            end = min(len(text), match.end() + 80)
            register(
                match.group(0),
                example=text[start:end],
                sentence_initial=_is_sentence_initial_token(text, match.start()),
                text_occurrence=True,
            )
''', '''            surface, surface_start = _strip_sentence_initial_vietnamese(text, match)
            if not surface:
                continue
            start = max(0, surface_start - 80)
            end = min(len(text), match.end() + 80)
            register(
                surface,
                example=text[start:end],
                sentence_initial=_is_sentence_initial_token(text, surface_start),
                text_occurrence=True,
            )
''')
replace_once('''        if (
            key not in speaker_keys
            and key not in isolated_dialogue_keys
            and mid_sentence_occurrences[key] == 0
        ):
            continue
''', '''        # No "must also appear mid-sentence" rule any more (19-09): it existed to keep capitalised
        # Vietnamese words at the start of a sentence out, which `is_vietnamese_syllable` in
        # `register()` now does wherever they stand, and the "Vietnamese word + name" runs it also
        # caught are split by `_strip_sentence_initial_vietnamese`. What it still did was drop a
        # foreign name that only ever opened a sentence - "Gauci Cromwell." went to VieNeu raw and
        # was read "Gà Yusai Cromwell".
''')
io.open(p, "w", encoding="utf-8").write(s)
print(f"da va {p}")

test = root / "tests" / "test_a_name_at_the_start_of_a_sentence_is_still_a_name.py"
test.write_text('''"""Tên nước ngoài đứng đầu câu vẫn được phiên âm; từ tiếng Việt đầu câu vẫn không bị tưởng là tên."""
from __future__ import annotations

from ebook_reader.analysis import _name_candidate_contexts


def _candidates(*texts: str) -> dict[str, tuple[int, int]]:
    rows = [{"speaker": "NARRATOR", "text": text, "kind": "narration"} for text in texts]
    return {
        c["surface"]: (c["sentence_initial_occurrences"], c["mid_sentence_occurrences"])
        for c in _name_candidate_contexts(rows)
    }


def test_a_foreign_name_that_only_opens_a_sentence_is_a_candidate() -> None:
    # Chương 370 lô 8: cả đoạn là cái tên, nên nó chỉ bao giờ ở đầu câu.
    assert _candidates("“Gauci Cromwell.”") == {"Gauci Cromwell": (1, 0)}
    assert "Max Planck" in _candidates("Max Planck đã nói thế.")


def test_capitalised_vietnamese_words_at_the_start_are_still_not_names() -> None:
    assert _candidates("May mắn thay, cậu vẫn ổn. Xen lẫn trong đó còn có tóc đỏ.") == {}


def test_a_vietnamese_word_is_stripped_off_the_name_it_opens() -> None:
    found = _candidates("Khi Lucien bước vào. Nghe Morris gọi. Do Chloe đến muộn.")
    assert set(found) == {"Lucien", "Morris", "Chloe"}
    assert found["Lucien"] == (0, 1), "sau khi bóc, tên đứng sau một từ - không còn là đầu câu"
''', encoding="utf-8")
print(f"da viet {test}")
