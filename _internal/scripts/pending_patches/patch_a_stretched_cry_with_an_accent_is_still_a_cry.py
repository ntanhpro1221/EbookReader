"""Va text_processing.py: tieng het keo dai bat dau bang mot nguyen am CO DAU cung la mot tieng het.

Lo 9, chuong 223, doan c00002_s0000076_bc79179b863f: `"ÁAAAAA!!"`. Bo chuan hoa cho TTS
(`normalize_vocalizations_for_tts`) co san luat cho nguyen am keo dai - `STRETCHED_OPEN_VOWEL_PATTERN`
bien "aaaa" thanh "A... a" de bo sinh khong chay toi tran khung - nhung mau ay doi token chi
gom MOT nguyen am lap lai. "ÁAAAAA" bat dau bang Á (U+00C1), ky tu khac A, nen "AAAAA" phia sau
dung sau mot ky tu chu -> (?<!\\w) that -> khong khop -> chuoi di nguyen vao TTS -> 5 ung vien
deu 0,96 s roi ban cuoi 1,92 s cham tran khung (cap 12), ASR bia ra cau chao cuoi video, chuong
hong. Cung hinh voi "Argh" ma tai lieu o dau file da ke: "handed the letters, the model ran to
its frame ceiling on a two-second scream".

Sua: mau nhan them mot nguyen am dan dau tuy chon; ham thay chi nhan khi chu cai goc cua no
(bo dau thanh, giu mu/moc/trang) trung voi nguyen am keo dai. "ÁAAAAA" -> "Á... a".
"Ôaaa" (goc khac) giu nguyen. "Khôôôông" (giua tu) van khong dung toi - do la viec khac.
"""
import io
import sys
from pathlib import Path

root = Path(sys.argv[1])
p = root / "ebook_reader" / "text_processing.py"
s = io.open(p, encoding="utf-8").read()

OLD_PATTERN = '''STRETCHED_OPEN_VOWEL_PATTERN = re.compile(
    r"(?<!\\w)(?P<vowel>[aeiouyưăâêôơ])(?P=vowel){2,}h*(?!\\w)",
    re.IGNORECASE,
)
'''
NEW_PATTERN = '''# Một nguyên âm dẫn đầu CÓ DẤU THANH được phép: "ÁAAAAA" là một tiếng hét chứ không phải hai.
# Bản trước đòi token chỉ gồm một nguyên âm lặp, nên Á (một ký tự khác A) đứng trước làm
# `(?<!\\w)` thất bại và cả chuỗi đi nguyên vào TTS - lô 9 chương 223: năm ứng viên 0,96 s rồi
# bản cuối chạm trần khung, cùng hình với "Argh" ở đầu file. Hàm thay kiểm chữ cái gốc của
# nguyên âm dẫn đầu (bỏ dấu thanh, giữ mũ/móc/trăng) có trùng nguyên âm kéo dài không.
STRETCHED_OPEN_VOWEL_PATTERN = re.compile(
    r"(?<!\\w)(?P<lead>[À-ỹ])?(?P<vowel>[aeiouyưăâêôơ])(?P=vowel){2,}h*(?!\\w)",
    re.IGNORECASE,
)
_TONE_MARKS = frozenset({"\\u0300", "\\u0301", "\\u0303", "\\u0309", "\\u0323"})


def _without_tone_marks(letter: str) -> str:
    """Chữ cái gốc: bỏ dấu thanh (huyền, sắc, ngã, hỏi, nặng), giữ mũ, móc và trăng."""
    import unicodedata

    decomposed = unicodedata.normalize("NFD", letter)
    kept = "".join(ch for ch in decomposed if ch not in _TONE_MARKS)
    return unicodedata.normalize("NFC", kept).casefold()
'''
assert s.count(OLD_PATTERN) == 1, "khong khop STRETCHED_OPEN_VOWEL_PATTERN"
s = s.replace(OLD_PATTERN, NEW_PATTERN, 1)

OLD_REPL = '''    def separate_stretched_vowel(match: re.Match[str]) -> str:
        vowel = match.group("vowel").casefold()
        return f"{vowel.upper()}... {vowel}"
'''
NEW_REPL = '''    def separate_stretched_vowel(match: re.Match[str]) -> str:
        vowel = match.group("vowel").casefold()
        lead = match.group("lead") or ""
        if lead:
            # "ÁAAAAA" là một tiếng hét: giữ nguyên âm có dấu làm đầu tiếng. "Ôaaa" thì không
            # phải một âm kéo dài - để yên, đừng đoán.
            if _without_tone_marks(lead) != vowel:
                return match.group(0)
            return f"{lead}... {vowel}"
        return f"{vowel.upper()}... {vowel}"
'''
assert s.count(OLD_REPL) == 1, "khong khop separate_stretched_vowel"
s = s.replace(OLD_REPL, NEW_REPL, 1)
io.open(p, "w", encoding="utf-8", newline="\n").write(s)
print(f"da va {p}")

TEST = '''"""Tiếng hét kéo dài bắt đầu bằng một nguyên âm có dấu vẫn là một tiếng hét.

Lô 9, chương 223: `"ÁAAAAA!!"` đi nguyên vào TTS vì mẫu nguyên-âm-kéo-dài đòi token chỉ gồm một
nguyên âm lặp; bộ sinh chạy tới trần khung, ASR bịa ra câu chào cuối video, chương hỏng.
"""
from __future__ import annotations

from ebook_reader.text_processing import normalize_vocalizations_for_tts


def test_an_accented_lead_vowel_joins_the_held_sound() -> None:
    assert normalize_vocalizations_for_tts('"ÁAAAAA!!"') == '"Á... a!!"'


def test_a_plain_held_vowel_keeps_the_old_form() -> None:
    assert normalize_vocalizations_for_tts('"AAAAA!"') == '"A... a!"'


def test_a_circumflex_vowel_with_a_tone_mark_still_matches_its_base() -> None:
    assert normalize_vocalizations_for_tts('"Ốôôôô!"') == '"Ố... ô!"'


def test_a_different_base_letter_is_not_one_sound() -> None:
    assert normalize_vocalizations_for_tts('"Ôaaa"') == '"Ôaaa"'


def test_a_stretch_inside_a_word_is_still_left_alone() -> None:
    """Đây là việc khác: "Khôôôông" là một từ kéo dài, không phải tiếng hét trần trụi."""
    assert normalize_vocalizations_for_tts("Khôôôông") == "Khôôôông"
'''
t = root / "tests" / "test_a_stretched_cry_with_an_accent_is_still_a_cry.py"
io.open(t, "w", encoding="utf-8", newline="\n").write(TEST)
print(f"da tao {t}")
