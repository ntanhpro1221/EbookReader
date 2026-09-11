r"""Va text_processing.py + audio_io.py: mot con so duoc doc TRON VEN, ke ca tu 1000 tro len.

CHUA AP luc viet (2026-09-11 19:00) - lo 5 dang chay. Ap o ranh gioi lo 5 -> 6, sau
patch_keep_the_locked_reading.

Chuong 106 (lo 4, va lai o lo04v_106) chet vi MOT doan, 10/10 lan thu:

    Toi bat dau thu nhung mat khau de doan nhat nhu, "password", "123456", tham chi la "qwerty1234".

    thuoc chu    70 ky tu doc duoc  o 12,35 kt/s   -> duoi san 12,5 dung 0,15
    thuoc am tiet 17 am tiet         o ~3,0 at/s    -> duoi san 3,75

Ca hai thuoc cung sai mot kieu: `123456` dem la SAU ky tu va MOT am tiet, trong khi giong doc
phat ra it nhat "mot hai ba bon nam sau" (17 ky tu, 6 am tiet) hoac "mot tram hai muoi ba nghin
bon tram nam muoi sau" (11 am tiet). `spoken_speakable_chars` da no so ra chu tu alpha.57 - nhung
`vietnamese_number_words` chi toi 999 va nem loi tren do, nen moi so tu 1000 (nam thang, so tien,
mat khau) van dem theo chu viet. Docstring cu goi do la "co y khong lap bang phong doan". Dung
o cho khong bia he so; sai o cho co mot cach dem KHONG phai phong doan:

  1. `vietnamese_number_words` doc tron ven toi duoi 10^12 theo ngu phap so dem: nhom ba chu so
     tu phai sang (nghin, trieu, ty); nhom giua duoi 100 doc "khong tram" (va "le" neu duoi 10):
     1.005 = "mot nghin khong tram le nam", 2.024 = "hai nghin khong tram hai muoi tu". Day la
     ngu phap, khong phai uoc luong.
  2. Cho phep do nhip, mot day chu so tu 1000 tro len lay CAN DUOI cua hai cach doc co the -
     doc nhu mot so, hay doc tung chu so - theo am tiet. "123456" trong mat khau va "2024" trong
     mot nam khong doc giong nhau, va chua do VieNeu chon cach nao; lay cach ngan hon thi dem
     thieu chi GIU co, dem thua moi THA NHAM. Toi 999 giu nguyen cach cu (do duoc o alpha.57).
  3. `spoken_syllables` dem tren cung van ban da no so, nen "22" la ba am tiet chu khong phai
     mot, va "qwerty1234" la nam.

Doan cua chuong 106 sau ban va, o cung thoi luong ~5,67 giay: 88 ky tu (15,5 kt/s) va 26 am tiet
(4,6 at/s) - ca hai giua dai binh thuong. ASR KHONG doi: `_fold_number_digits` van dung tran
`NUMBER_FOLD_CEILING = 999` va de nam thang nguyen chu viet (bai `test_a_year_is_left_as_it_was_
written` giu nguyen).
"""
import io
import os
import sys
import tempfile
from pathlib import Path


def write_atomic(path: Path, text: str) -> None:
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    os.close(fd)
    io.open(tmp, "w", encoding="utf-8").write(text)
    os.replace(tmp, path)


root = Path(sys.argv[1])

# ============================================================ text_processing.py
p = root / "ebook_reader" / "text_processing.py"
s = io.open(p, encoding="utf-8").read()

OLD = '''        if rest < 10:
            return f"{head} lẻ {VIETNAMESE_UNITS[rest]}"
        return f"{head} {vietnamese_number_words(rest)}"
    raise ValueError(f"number beyond what a book numbers things with: {value}")
'''
NEW = '''        if rest < 10:
            return f"{head} lẻ {VIETNAMESE_UNITS[rest]}"
        return f"{head} {vietnamese_number_words(rest)}"
    if value < 1_000_000_000_000:
        # Nhóm ba chữ số từ phải sang: nghìn, triệu, tỷ. Nhóm giữa mà dưới 100 đọc "không
        # trăm" (và "lẻ" nếu dưới 10): 1.005 là "một nghìn không trăm lẻ năm", 2.024 là "hai
        # nghìn không trăm hai mươi tư"; nhóm bằng 0 bỏ hẳn. Đây là ngữ pháp số đếm, không phải
        # ước lượng - và `asr.py` vẫn dừng ở `NUMBER_FOLD_CEILING`, vì năm tháng trong bản ghi
        # không có một dạng nói duy nhất để gộp.
        groups: list[int] = []
        remaining = value
        while remaining:
            remaining, group = divmod(remaining, 1000)
            groups.append(group)
        words: list[str] = []
        for index in range(len(groups) - 1, -1, -1):
            group = groups[index]
            if group == 0:
                continue
            if index == len(groups) - 1:
                spoken = vietnamese_number_words(group)
            elif group < 10:
                spoken = f"không trăm lẻ {VIETNAMESE_UNITS[group]}"
            elif group < 100:
                spoken = f"không trăm {vietnamese_number_words(group)}"
            else:
                spoken = vietnamese_number_words(group)
            words.append(spoken if index == 0 else f"{spoken} {VIETNAMESE_SCALES[index]}")
        return " ".join(words)
    raise ValueError(f"number beyond what a book numbers things with: {value}")
'''
assert s.count(OLD) == 1, "khong khop duoi vietnamese_number_words"
s = s.replace(OLD, NEW, 1)

OLD = '''VIETNAMESE_UNITS = (
    "không", "một", "hai", "ba", "bốn", "năm", "sáu", "bảy", "tám", "chín",
)
'''
NEW = '''VIETNAMESE_UNITS = (
    "không", "một", "hai", "ba", "bốn", "năm", "sáu", "bảy", "tám", "chín",
)
# Bậc của từng nhóm ba chữ số, từ phải sang: nhóm 0 không có tên.
VIETNAMESE_SCALES = ("", "nghìn", "triệu", "tỷ")
'''
assert s.count(OLD) == 1, "khong khop VIETNAMESE_UNITS"
s = s.replace(OLD, NEW, 1)

write_atomic(p, s)
print("da va", p)

# ============================================================ audio_io.py
p = root / "ebook_reader" / "audio_io.py"
s = io.open(p, encoding="utf-8").read()

OLD = "from .text_processing import vietnamese_number_words\n"
NEW = "from .text_processing import VIETNAMESE_UNITS, vietnamese_number_words\n"
assert s.count(OLD) == 1, "khong khop import"
s = s.replace(OLD, NEW, 1)

# ---- mot dau doc chung cho ca hai thuoc
OLD = '''def spoken_syllables(text: str) -> int:
    """Số âm tiết đọc ra: tiếng Việt đơn âm, nên mỗi âm tiết là một cụm chữ giữa hai dấu tách.
'''
NEW = '''def _digit_run_spoken(digits: str) -> str:
    """Cách đọc một dãy chữ số, cho phép đo nhịp: cận dưới của những cách đọc có thể.

    Tới 999: đọc như một số ("22" → "hai mươi hai") - đo được ở alpha.57, giữ nguyên. Từ 1000:
    VieNeu có thể đọc như một số ("một nghìn hai trăm ba mươi tư") hoặc từng chữ số ("một hai
    ba bốn") - "123456" trong một mật khẩu và "2024" trong một năm không đọc giống nhau, và chưa
    đo nó chọn cách nào. Lấy cách NGẮN HƠN theo âm tiết: đếm thiếu chỉ giữ cờ, đếm thừa mới tha
    nhầm. Chương 106 của lô 4 mất vì "123456" đếm là một âm tiết và sáu ký tự.
    """
    value = int(digits)
    if value <= 999:
        return vietnamese_number_words(value)
    by_digit = " ".join(VIETNAMESE_UNITS[int(digit)] for digit in digits)
    try:
        as_number = vietnamese_number_words(value)
    except (ValueError, OverflowError):
        return by_digit
    return min((as_number, by_digit), key=lambda form: len(form.split()))


def _spoken_form(text: str) -> str:
    """Văn bản như giọng đọc phát ra: mọi dãy chữ số nở thành chữ, tách khỏi chữ đứng cạnh."""
    return _DIGIT_RUN.sub(lambda match: f" {_digit_run_spoken(match.group())} ", text)


def spoken_syllables(text: str) -> int:
    """Số âm tiết đọc ra: tiếng Việt đơn âm, nên mỗi âm tiết là một cụm chữ giữa hai dấu tách.
'''
assert s.count(OLD) == 1, "khong khop dau spoken_syllables"
s = s.replace(OLD, NEW, 1)

OLD = '''    Vẫn còn đếm thiếu ở chữ số (`22` đọc ba âm tiết mà viết là một cụm) và ở tên chưa có cách
    đọc trong sổ. Cả hai đều đo được và sửa được; không lấp bằng phỏng đoán ở đây.
    """
    return sum(
        1 for token in _SYLLABLE_SPLIT.split(text) if any(char.isalnum() for char in token)
    )'''
NEW = '''    Chữ số đếm như đọc ra (`22` là ba âm tiết; từ 1000 lấy cận dưới của hai cách đọc - xem
    `_digit_run_spoken`). Còn đếm thiếu ở tên chưa có cách đọc trong sổ ("password" là một):
    đo được, và chỉ giữ cờ chứ không tha thêm.
    """
    return sum(
        1
        for token in _SYLLABLE_SPLIT.split(_spoken_form(text))
        if any(char.isalnum() for char in token)
    )'''
assert s.count(OLD) == 1, "khong khop than spoken_syllables"
s = s.replace(OLD, NEW, 1)

OLD = '''    **Giới hạn còn lại, cố ý không lấp bằng phỏng đoán:** `vietnamese_number_words` chỉ nở tới
    999 và ném lỗi trên số lớn hơn. Số từ 1000 trở lên vẫn được đếm theo chữ viết, tức vẫn bị
    tính thiếu. Bịa một hệ số ước cho chúng sẽ là đoán, và đoán chính là thứ đã tạo ra lỗi này.
    """
    def expand(match: "re.Match[str]") -> str:
        try:
            return vietnamese_number_words(int(match.group()))
        except (ValueError, OverflowError):
            return match.group()

    return sum(char.isalnum() for char in _DIGIT_RUN.sub(expand, text))'''
NEW = '''    Từ 1000 trở lên: bản đầu để nguyên chữ viết ("cố ý không lấp bằng phỏng đoán"), và chương
    106 của lô 4 mất vì "123456" đếm sáu ký tự trong khi giọng đọc phát ra ít nhất mười bảy.
    Giờ nở bằng ngữ pháp số đếm (`vietnamese_number_words` tới dưới 10^12) và lấy cận dưới của
    hai cách đọc có thể - xem `_digit_run_spoken`. Không phải hệ số ước.
    """
    return sum(char.isalnum() for char in _spoken_form(text))'''
assert s.count(OLD) == 1, "khong khop spoken_speakable_chars"
s = s.replace(OLD, NEW, 1)

write_atomic(p, s)
print("da va", p)

# ============================================================ tests/test_pace_counts_syllables_too.py
# Bai cu ghim viec dem THIEU chu so "co chu y"; tu ban va nay chu so dem nhu doc ra, ten chua co
# cach doc van dem thieu.
p = root / "tests" / "test_pace_counts_syllables_too.py"
s = io.open(p, encoding="utf-8").read()
OLD = """def test_syllables_are_counted_short_on_names_and_digits_on_purpose() -> None:
    \"\"\"Đếm thiếu là chiều an toàn: nhịp âm tiết đo thấp hơn thật thì chỉ giữ cờ, không tha.\"\"\"
    assert spoken_syllables("Alice") == 1
    assert spoken_syllables("Chương 22") == 2
    assert spoken_syllables("— …") == 0"""
NEW = """def test_syllables_are_counted_short_on_names_without_a_reading_on_purpose() -> None:
    \"\"\"Đếm thiếu là chiều an toàn: nhịp âm tiết đo thấp hơn thật thì chỉ giữ cờ, không tha.

    Chữ số thì không còn đếm thiếu - `patch_a_number_is_read_in_full`: "22" đọc "hai mươi hai",
    ba âm tiết, và chương 106 mất vì "123456" từng đếm là một.
    \"\"\"
    assert spoken_syllables("Alice") == 1
    assert spoken_syllables("Chương 22") == 4
    assert spoken_syllables("— …") == 0"""
assert s.count(OLD) == 1, "khong khop bai thu dem thieu"
s = s.replace(OLD, NEW, 1)
write_atomic(p, s)
print("da sua", p)

# ============================================================ tests/test_audio_assembly.py
# Bai cu ghim "so > 999 de nguyen chu viet, co chu y"; gio no duoc doc tron ven.
p = root / "tests" / "test_audio_assembly.py"
s = io.open(p, encoding="utf-8").read()
OLD = """def test_a_number_too_large_to_spell_is_left_alone_rather_than_guessed() -> None:
    \"\"\"vietnamese_number_words stops at 999 and raises above it.

    Those stay counted as written, so they are still undercounted - a known and deliberate
    gap. Inventing a multiplier for them would be guessing, and guessing is what produced
    this bug in the first place.
    \"\"\"
    from ebook_reader.audio_io import spoken_speakable_chars

    text = "Chương 1000 - 1000: xa quá"

    assert spoken_speakable_chars(text) == sum(char.isalnum() for char in text)"""
NEW = """def test_a_number_from_a_thousand_up_is_counted_as_it_is_read() -> None:
    \"\"\"vietnamese_number_words used to stop at 999; the digits above it were counted as written.

    Chapter 106 of batch 4 died on "123456" counted as six characters and one syllable. The
    speller now reaches below 10^12 by the grammar of counting, and a digit run from 1000 up
    counts the shorter of its two possible readings - never a made-up multiplier.
    \"\"\"
    from ebook_reader.audio_io import spoken_speakable_chars

    text = "Chương 1000 - 1000: xa quá"
    spoken = "Chương một nghìn - một nghìn: xa quá"

    assert spoken_speakable_chars(text) == sum(char.isalnum() for char in spoken)
    assert spoken_speakable_chars(text) > sum(char.isalnum() for char in text)"""
assert s.count(OLD) == 1, "khong khop bai thu so lon"
s = s.replace(OLD, NEW, 1)
write_atomic(p, s)
print("da sua", p)

# ============================================================ tests
TEST = '''"""Một con số được đọc trọn vẹn, kể cả từ 1000 trở lên - và thước nhịp đếm đúng cái đọc ra.

Chương 106 của lô 4 mất vì một đoạn chứa "123456": sáu ký tự, một âm tiết theo thước cũ, trong
khi giọng đọc phát ra ít nhất "một hai ba bốn năm sáu". 10/10 lần thử ở 12,35 kt/s, sàn 12,5.
"""
from __future__ import annotations

import pytest

from ebook_reader.asr import NUMBER_FOLD_CEILING, normalize_transcript
from ebook_reader.audio_io import (
    PACE_SYLLABLES_PER_SECOND_FLOOR,
    pace_is_outlier,
    spoken_speakable_chars,
    spoken_syllables,
)
from ebook_reader.text_processing import vietnamese_number_words

NORMAL = (12.5, 24.5)
LOST_LINE_106 = (
    "Tôi bắt đầu thử những mật khẩu dễ đoán nhất như, \\"password\\", \\"123456\\", "
    "thậm chí là \\"qwerty1234\\"."
)


def test_numbers_from_a_thousand_up_are_spelled_by_grammar() -> None:
    assert vietnamese_number_words(1000) == "một nghìn"
    assert vietnamese_number_words(1005) == "một nghìn không trăm lẻ năm"
    assert vietnamese_number_words(2024) == "hai nghìn không trăm hai mươi tư"
    assert vietnamese_number_words(10_015) == "mười nghìn không trăm mười lăm"
    assert vietnamese_number_words(123_456) == "một trăm hai mươi ba nghìn bốn trăm năm mươi sáu"
    assert vietnamese_number_words(1_000_000) == "một triệu"
    assert vietnamese_number_words(2_000_005) == "hai triệu không trăm lẻ năm"
    assert vietnamese_number_words(1_234_567_890) == (
        "một tỷ hai trăm ba mươi tư triệu năm trăm sáu mươi bảy nghìn tám trăm chín mươi"
    )
    with pytest.raises(ValueError):
        vietnamese_number_words(1_000_000_000_000)


def test_below_a_thousand_nothing_changed() -> None:
    for value, spoken in ((15, "mười lăm"), (21, "hai mươi mốt"), (105, "một trăm lẻ năm")):
        assert vietnamese_number_words(value) == spoken


def test_a_digit_run_counts_the_shorter_of_its_two_readings() -> None:
    assert spoken_syllables("123456") == 6, "từng chữ số: sáu; như một số: mười một"
    assert spoken_syllables("1000") == 2, "một nghìn - ngắn hơn bốn chữ số"
    assert spoken_syllables("năm 2024") == 1 + 4
    assert spoken_syllables("22") == 3, "tới 999 đọc như một số, như alpha.57 đo"
    assert spoken_syllables("qwerty1234") == 5


def test_the_lost_line_of_chapter_106_reads_at_a_normal_pace() -> None:
    speakable = spoken_speakable_chars(LOST_LINE_106)
    syllables = spoken_syllables(LOST_LINE_106)
    assert (speakable, syllables) == (88, 26), "70 ký tự / 17 âm tiết là con số cũ, và nó làm mất chương"
    # Đúng thời lượng của bản thu đã mất: 70 ký tự cũ ở 12,35 kt/s.
    speech_seconds = 70 / 12.35
    rate = speakable / speech_seconds
    syllable_rate = syllables / speech_seconds
    assert rate > NORMAL[0] and syllable_rate > PACE_SYLLABLES_PER_SECOND_FLOOR["normal"]
    assert not pace_is_outlier(rate, syllable_rate, "normal", NORMAL)


def test_a_genuinely_slow_take_is_still_caught() -> None:
    speakable = spoken_speakable_chars(LOST_LINE_106)
    syllables = spoken_syllables(LOST_LINE_106)
    speech_seconds = speakable / 8.0
    assert pace_is_outlier(8.0, syllables / speech_seconds, "normal", NORMAL)


def test_the_transcript_fold_still_leaves_a_year_as_written() -> None:
    """ASR không đổi: gộp số trong bản ghi vẫn dừng ở trần cũ."""
    assert NUMBER_FOLD_CEILING == 999
    assert normalize_transcript("năm 2026") == "năm 2026"
'''
write_atomic(root / "tests" / "test_a_number_is_read_in_full.py", TEST)
print("da tao", root / "tests" / "test_a_number_is_read_in_full.py")
