"""Vá analysis.py: "Arthen NGHIÊM NGHỊ hỏi:" vẫn là câu kể nêu tên người nói.

Chạy: python patch_a_modifier_between_a_name_and_said_still_names_the_speaker.py <root>

## Vì sao (20-09, 09:0x)

`SPEECH_ATTRIBUTION_PATTERN` đòi động từ nói DÍNH LIỀN tên: `<Tên> (nói|hỏi|đáp|...):`. Tiếng Việt chen trạng ngữ
vào giữa suốt ngày - "Arthen nghiêm nghị hỏi:", "James mỉm cười nói:", "Lucien từ tốn nói:", "Lazar đột nhiên hỏi:" -
nên host KHÔNG biết người nói và để nguyên đáp án của model. Đo trên bản thu lô 9 (`score_models.py --dispute-out`):
chỉ 2 lần luật cũ bắt được trong cả 9 chương đáp án, còn 122 câu thoại có câu kể liền trước thì host mù.

Nới ra: cho phép 1-3 chữ THƯỜNG giữa tên và động từ nói (không dấu phẩy - dấu phẩy là đã sang mệnh đề khác), kèm ba
chốt:

  - chữ giữa không được là chữ hướng tới người nghe (`LISTENER_DIRECTED_WORDS`): "nhìn", "sang", "với"...;
  - GIỚI TỪ ngay trước tên thì tên ấy là đối tượng, không phải chủ ngữ: "James chỉ vào Lucien rồi nói:" -> không gán
    (chỉ xét MỘT chữ liền kề, vì "Bước vào phòng, Sophia nói:" thì Sophia vẫn là người nói);
  - tên bị cắt cụt ("Trịnh Vĩnh Mong" -> "Mong", "Sơn Ca" -> "Ca", vì `LATIN_PROPER_NAME_SURFACE_PATTERN` chỉ bắt
    âm cuối) đã bị chốt sẵn từ `patch_the_one_being_looked_at_is_not_the_speaker.py` ở ranh giới 9 - bản vá này
    KHÔNG thêm chốt ấy nữa, chỉ dựa vào nó.

Đo trên cả 41 chương đáp án chuẩn (chia đoạn thật, so với đáp án): **17 câu gán ĐÚNG thêm, 0 câu gán SAI thêm.**
Hai chốt mới là hai chỗ đã đo ra sai rồi sửa (James chỉ vào Lucien; Lucien nhìn sang nói).
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
    root / "ebook_reader" / "analysis.py",
    '''SPEECH_ATTRIBUTION_PATTERN = re.compile(
    rf"(?P<speaker>{LATIN_PROPER_NAME_SURFACE_PATTERN.pattern})\\s+"
    r"(?:nói|hỏi|đáp|trả lời|lên tiếng|thì thầm|quát|kêu|thốt lên)\\s*[:：]\\s*$"
)''',
    '''# Trạng ngữ chen giữa tên và động từ nói là lối viết thường ngày: "Arthen nghiêm nghị hỏi:", "James mỉm cười
# nói:". Cho phép 1-3 chữ THƯỜNG ở giữa; dấu phẩy thì không, vì dấu phẩy là đã sang mệnh đề khác.
SPEECH_ATTRIBUTION_PATTERN = re.compile(
    rf"(?P<speaker>{LATIN_PROPER_NAME_SURFACE_PATTERN.pattern})\\s+"
    r"(?P<middle>(?:[a-zà-ỹđ]+\\s+){1,3})?"
    r"(?:nói|hỏi|đáp|trả lời|lên tiếng|thì thầm|quát|kêu|thốt lên)\\s*[:：]\\s*$"
)
# Giới từ ngay trước một cái tên: tên ấy là ĐỐI TƯỢNG của hành động, không phải người nói
# ("James chỉ vào Lucien rồi nói:"). Chỉ xét MỘT chữ liền kề - "Bước vào phòng, Sophia nói:" thì Sophia vẫn nói.
OBJECT_MARKER_BEFORE_NAME_WORDS = frozenset({"vào", "cho", "tới", "đến", "về", "lên", "quanh"})''',
)

patch(
    root / "ebook_reader" / "analysis.py",
    '''    speaker = match.group("speaker")
    if _name_candidate_key(speaker) in NAME_CANDIDATE_EXCLUSIONS:
        return None
    before = stripped[: match.start("speaker")].split()''',
    '''    speaker = match.group("speaker")
    if _name_candidate_key(speaker) in NAME_CANDIDATE_EXCLUSIONS:
        return None
    if any(word.casefold() in LISTENER_DIRECTED_WORDS for word in (match.group("middle") or "").split()):
        return None
    before = stripped[: match.start("speaker")].split()''',
)

patch(
    root / "ebook_reader" / "analysis.py",
    '''        if previous.casefold() in NOT_A_SPEAKER_BEFORE_NAME_WORDS:
            return None
        if any(word.casefold().strip(",.;") in LISTENER_DIRECTED_WORDS for word in before[-3:]):
            return None
    return speaker''',
    '''        if previous.casefold() in NOT_A_SPEAKER_BEFORE_NAME_WORDS:
            return None
        if previous.casefold() in OBJECT_MARKER_BEFORE_NAME_WORDS:
            return None
        if any(word.casefold().strip(",.;") in LISTENER_DIRECTED_WORDS for word in before[-3:]):
            return None
    return speaker''',
)

test = root / "tests" / "test_a_modifier_between_a_name_and_said_still_names_the_speaker.py"
test.write_text('''"""Trạng ngữ giữa tên và động từ nói không xoá người nói; ba chốt chống gán sai."""
from __future__ import annotations

from ebook_reader.analysis import _trailing_speech_attribution


def test_a_modifier_between_a_name_and_said() -> None:
    assert _trailing_speech_attribution("Arthen nghiêm nghị hỏi:") == "Arthen"
    assert _trailing_speech_attribution("James mỉm cười nói:") == "James"
    assert _trailing_speech_attribution("Sau khi tán gẫu một hồi, Lazar đột nhiên hỏi:") == "Lazar"
    assert _trailing_speech_attribution("Rút tay về, Sophia thở hổn hển nói:") == "Sophia"


def test_the_plain_form_still_works() -> None:
    assert _trailing_speech_attribution("Lucien nói:") == "Lucien"
    assert _trailing_speech_attribution("Không có tên nào ở đây cả.") is None


def test_an_object_is_not_the_speaker() -> None:
    # Giới từ liền trước tên -> tên là đối tượng.
    assert _trailing_speech_attribution("James chỉ vào Lucien rồi nói:") is None
    # Nhưng giới từ ở xa thì không cản.
    assert _trailing_speech_attribution("Bước vào phòng, Sophia lạnh lùng nói:") == "Sophia"


def test_a_listener_directed_word_in_the_middle_is_not_an_attribution() -> None:
    assert _trailing_speech_attribution("Lucien nhìn sang nói:") is None


def test_a_truncated_vietnamese_name_is_refused() -> None:
    # LATIN_PROPER_NAME chỉ bắt âm cuối; gán "Mong" hay "Ca" là sinh ra nhân vật mới.
    assert _trailing_speech_attribution("Trịnh Vĩnh Mong nhíu mày nói:") is None
    assert _trailing_speech_attribution("Sơn Ca cười khúc khích nói:") is None
''', encoding="utf-8")
print(f"da viet {test}")
