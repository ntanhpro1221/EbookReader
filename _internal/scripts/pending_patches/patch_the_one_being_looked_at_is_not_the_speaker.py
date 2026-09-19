"""Vá analysis.py: "X nhìn Y nói:" - Y là người NGHE; luật host "tên ngay trước 'nói:' là người nói" phải im.

Chạy: python patch_the_one_being_looked_at_is_not_the_speaker.py <root>

## Vì sao (20-09, 01:4x)

`_trailing_speech_attribution` khoá câu thoại cho tên riêng đứng NGAY trước "nói/hỏi/đáp...:" ở câu kể liền trước, cùng
đoạn văn. Đúng khi tên là chủ ngữ ("Lucien nói:"). Sai khi tên là TÂN NGỮ của một động từ hướng về người nghe - tiếng Việt
đặt người nói ở đầu câu và người nghe ngay trước "nói:":

    Levski quay sang Lucien nói:                     -> khoá cho Lucien (người nghe)
    Ông đưa đôi mắt xám bạc nhìn Lucien nói:         -> Lucien
    Công tước James nghiêm nghị nhìn Tử tước Harrison nói:   -> Harrison
    Lucien khẽ gật đầu rồi dùng giọng Beaulac nói:   -> Beaulac (tên cải trang)
    Nghĩ vậy, ông liền phối hợp với Heidi nói:       -> Heidi

Và khi `LATIN_PROPER_NAME_SURFACE_PATTERN` (chỉ chữ ASCII) cắt cụt một tên có dấu: "Triết Gia hỏi:" -> người nói "Gia";
"túm lấy tai Trịnh Vĩnh Mong nói:" -> "Mong" (bắt được khi phát lại đáp án chuẩn Năng lực bá đạo 0135:103).

Đếm trên cuốn 2 (915 chương): luật bắn 78 lần, ~29 lần khoá cho người nghe hoặc cho mẩu tên - trong đó 003, 192, 231, 301,
368, 406 đã thu, 426-870 còn ở các lô sau. Kho truyện tên Hán-Việt (Năng lực bá đạo): 115 lần, 52 lần tên bị cắt cụt.

Luật mới - im (câu trả lời của model và lượt phản biện quyết) khi: từ ngay trước tên viết hoa và "tên" là một âm tiết
tiếng Việt (mẩu của một tên có dấu bị cắt), hoặc là "một/của/đám/người/trò" (danh từ chung hay nhóm), hoặc ba từ ngay trước
tên có một động từ/giới từ hướng về người nghe: nhìn, sang, với, giọng, tai, chỗ, phía, hướng. Chủ ngữ có chức vị viết
thường vẫn khoá như cũ ("tổng giám mục Augustus nói:", "Đại hồng y mới tấn thăng Philip nói:", "thế nên Raventi nói:").
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


replace_once('''def _trailing_speech_attribution(text: str) -> str | None:
    match = SPEECH_ATTRIBUTION_PATTERN.search(text.strip())
    if match is None:
        return None
    speaker = match.group("speaker")
    if _name_candidate_key(speaker) in NAME_CANDIDATE_EXCLUSIONS:
        return None
    return speaker''', '''# "Levski quay sang Lucien nói:", "nhìn Tử tước Harrison nói:", "dùng giọng Beaulac nói:": trong ba từ trước tên có một
# từ hướng về người NGHE - tên là tân ngữ, người nói là chủ ngữ ở đầu câu.
LISTENER_DIRECTED_WORDS = frozenset({"nhìn", "sang", "với", "giọng", "tai", "chỗ", "phía", "hướng"})
# "của một Arcanist nói:", "đám học trò Annick nói:", "đám người Lucien nói:": danh từ chung hay một nhóm.
NOT_A_SPEAKER_BEFORE_NAME_WORDS = frozenset({"một", "của", "đám", "người", "trò"})


def _trailing_speech_attribution(text: str) -> str | None:
    stripped = text.strip()
    match = SPEECH_ATTRIBUTION_PATTERN.search(stripped)
    if match is None:
        return None
    speaker = match.group("speaker")
    if _name_candidate_key(speaker) in NAME_CANDIDATE_EXCLUSIONS:
        return None
    before = stripped[: match.start("speaker")].split()
    if before:
        previous = before[-1]
        if previous[:1].isupper() and previous[-1:].isalpha() and is_vietnamese_syllable(speaker.split()[0]):
            # Mẫu tên chỉ bắt chữ ASCII nên "Triết Gia", "Trịnh Vĩnh Mong" còn lại "Gia", "Mong": mẩu một tên có dấu,
            # không phải một tên. ("Rồi Lucien nói:" vẫn khoá: "Lucien" không phải âm tiết tiếng Việt.)
            return None
        if previous.casefold() in NOT_A_SPEAKER_BEFORE_NAME_WORDS:
            return None
        if any(word.casefold().strip(",.;") in LISTENER_DIRECTED_WORDS for word in before[-3:]):
            return None
    return speaker''')
io.open(p, "w", encoding="utf-8").write(s)
print(f"da va {p}")

test = root / "tests" / "test_the_one_being_looked_at_is_not_the_speaker.py"
test.write_text('''"""Luật "tên ngay trước 'nói:' là người nói" im khi tên là người NGHE hay mẩu tên bị cắt (cuốn 2: ~29 câu)."""
from __future__ import annotations

from ebook_reader.analysis import _trailing_speech_attribution


def test_the_listener_named_before_the_speech_verb_is_not_the_speaker() -> None:
    for text in (
        "Nhìn Neeshka, Salgueiro và các ủy viên khác rời đi, Levski quay sang Lucien nói:",
        "Ông đưa đôi mắt xám bạc nhìn Lucien nói:",
        "Công tước James nghiêm nghị nhìn Tử tước Harrison nói:",
        "Lucien khẽ gật đầu rồi dùng giọng Beaulac nói:",
        "Nghĩ vậy, ông liền phối hợp với Heidi nói:",
        "Xong xuôi tất cả, Benjamin nhìn đám người Lucien nói:",
        "Lucien cười cười quan sát Heidi, sau đó quay sang đám học trò Annick nói:",
        "Lucien không đáp ngay mà dùng phong thái nghiêm cẩn của một Arcanist nói:",
    ):
        assert _trailing_speech_attribution(text) is None, text


def test_a_name_cut_short_by_its_accents_is_not_a_name() -> None:
    assert _trailing_speech_attribution("Cảm thấy khó hiểu trước hành vi này của Giáo Sư, Triết Gia hỏi:") is None
    assert _trailing_speech_attribution("một phát túm lấy tai Trịnh Vĩnh Mong nói:") is None


def test_the_subject_still_takes_the_line() -> None:
    assert _trailing_speech_attribution("Lucien nói:") == "Lucien"
    assert _trailing_speech_attribution("Rồi Lucien nói:") == "Lucien"
    assert _trailing_speech_attribution("Sau đó, Lucien hỏi:") == "Lucien"
    assert _trailing_speech_attribution("Khi những người lùn bắt đầu cảnh giác, tổng giám mục Augustus nói:") == "Augustus"
    assert _trailing_speech_attribution("Đại hồng y mới tấn thăng Philip nói:") == "Philip"
    assert _trailing_speech_attribution("Nhìn Natasha một cách đầy thành khẩn, Bá tước Barady nói:") == "Barady"
    assert _trailing_speech_attribution("chưa kể nó cũng rất phù hợp, thế nên Raventi nói:") == "Raventi"
''', encoding="utf-8")
print(f"da viet {test}")
