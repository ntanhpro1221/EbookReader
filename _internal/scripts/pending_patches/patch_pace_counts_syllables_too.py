r"""Va audio_io.py: mot ban thu chi "cham" khi no cham theo CA chu lan am tiet.

CHUA AP luc viet - lo 3 dang chay (chuong 075 vua chet vi dung loi nay). Ap o ranh gioi lo,
truoc lo va cho lo 3 - chuong 075 chay lai duoi ban va nay la phep thu dau tien.

Chuong 075 mat mot cau dan truyen, 10/10 lan thu, moi lan mot seed:

    "Và Alice đã ở đó để tận dụng sơ hở ấy."   27 ky tu doc, 11 tu, 1 cho nghi
    11,00  11,38  11,38  11,80  11,38  11,00  10,64  11,38  11,80  11,00 chars/s  (san 12,5)
    split = "segment too short to split safely" (38 < 100), pace_band = "already normal"

Muoi lan cung mot con so khong phai xui: la so hoc. Cau nay co 2,25 chu moi tu, trong khi
trung vi cua 8.301 ban thu da qua la 3,33. Cung mot toc do doc (am tiet moi giay) thi cau
toan tu ngan cho ra it chu moi giay hon, va phep do "chars/s" - vay muon cho "toc do doc" - goi
no la cham. Do lai theo am tiet (tu = am tiet, tieng Viet don am): 11 / (27/11,00) = 4,48
am tiet/giay, GAN TRUNG VI cua kho (4,67; p2 = 3,76; p98 = 6,07). Ban thu ay khong cham. Chi
co thuoc do cham.

Cung ho voi patch_pace_digits (chu so: 2 ky tu viet, 11 ky tu doc): mot lan nua chars/s dem
sai cai no nhan la dem. Sua o cung mot cho, cung mot cach: them mot phep dem nua va chi ket
toi khi CA HAI cung noi cham. Huong thay doi la mot chieu - chi BOT co, khong them - va ban
thu duoc tha them phai co nhip am tiet trong dai binh thuong.

San am tiet: p2 cua ban thu da qua (3,76 ~ 3,75), cung cach chon 12,5 truoc day ("2nd
percentile"). slow/fast ti le theo dai chu nhu cu: 7/12,5 va 14/12,5. Dem tu = so token co it
nhat mot ky tu doc duoc; ten nuoc ngoai ("Alice" hai am tiet) va chu so ("22" ba am tiet) bi
dem THIEU - tuc nhip am tiet do ra THAP hon that - nen sai so nghieng ve phia giu nguyen co
nhu cu, khong nghieng ve tha them.
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
p = root / "ebook_reader" / "audio_io.py"
s = io.open(p, encoding="utf-8").read()

# ---------------------------------------------------------------- hang so, canh hai he so cung
OLD = "RATE_HARD_MIN_FACTOR = 0.55\nRATE_HARD_MAX_FACTOR = 1.50\n"
NEW = '''RATE_HARD_MIN_FACTOR = 0.55
RATE_HARD_MAX_FACTOR = 1.50
# Sàn nhịp theo ÂM TIẾT mỗi giây (từ = âm tiết), đo trên 8.301 bản thu đã qua của lô 1–3
# (2026-09-10): p0.5 3,22 · p1 3,51 · p2 3,76 · p50 4,67 · p98 6,07. Lấy p2, cùng cách chọn
# sàn 12,5 chars/s; slow/fast tỉ lệ theo dải chữ như cũ (7/12,5 và 14/12,5). Xem
# `pace_is_outlier` cho lý do có hai thước.
PACE_SYLLABLES_PER_SECOND_FLOOR = {"slow": 2.1, "normal": 3.75, "fast": 4.2}
'''
assert OLD in s, "khong khop hang so"
s = s.replace(OLD, NEW, 1)

# ---------------------------------------------------------------- hai helper, ngay tren spoken_speakable_chars
OLD = "def spoken_speakable_chars(text: str) -> int:\n"
NEW = '''def spoken_syllables(text: str) -> int:
    """Số âm tiết đọc ra, xấp xỉ bằng số từ: tiếng Việt đơn âm, một từ là một âm tiết.

    Xấp xỉ này đếm THIẾU ở tên nước ngoài ("Alice" hai âm tiết) và chữ số ("22" đọc ba âm
    tiết), tức nhịp âm tiết đo ra thấp hơn thật. Đó là chiều sai an toàn cho việc nó được
    dùng: một bản thu chỉ được tha khi nhịp âm tiết đủ cao, nên đếm thiếu chỉ làm giữ nguyên
    cờ như cũ chứ không tha thêm.
    """
    return sum(1 for token in text.split() if any(char.isalnum() for char in token))


def pace_is_outlier(
    rate: float,
    syllable_rate: float,
    pace: str,
    bounds: "tuple[float, float] | list[float]",
) -> bool:
    """Chậm chỉ khi chậm theo CẢ chữ lẫn âm tiết; nhanh vẫn xét theo chữ như cũ.

    Chương 075 của lô 3 mất câu "Và Alice đã ở đó để tận dụng sơ hở ấy." sau 10/10 lần thử ở
    10,64–11,80 chars/s, sàn 12,5. Câu ấy có 2,25 chữ mỗi từ (trung vị kho: 3,33): cùng một
    tốc độ đọc thì câu toàn từ ngắn cho ra ít chữ mỗi giây hơn, và thước "chars/s" gọi nó là
    chậm. Đo theo âm tiết: 4,48/giây, gần trung vị kho (4,67). Bản thu không chậm; thước chậm.

    Cùng họ với `spoken_speakable_chars` (chữ số): thước chữ đếm sai cái nó nhận là đếm, và
    cách sửa là thêm phép đếm thứ hai rồi chỉ kết tội khi cả hai cùng nói. Thay đổi một chiều:
    chỉ bớt cờ, không thêm; bản thu được tha thêm phải có nhịp âm tiết trong dải bình thường
    (`PACE_SYLLABLES_PER_SECOND_FLOOR`). Cận trên giữ nguyên theo chữ - chưa có ca nào đòi hơn.
    """
    lower_bound = float(bounds[0])
    upper_bound = float(bounds[1])
    syllable_floor = PACE_SYLLABLES_PER_SECOND_FLOOR.get(
        pace, PACE_SYLLABLES_PER_SECOND_FLOOR["normal"]
    )
    too_slow = rate < lower_bound and syllable_rate < syllable_floor
    return bool(too_slow or rate > upper_bound)


def spoken_speakable_chars(text: str) -> int:
'''
assert OLD in s and "def spoken_syllables" not in s, "khong khop cho chen helper"
s = s.replace(OLD, NEW, 1)

# ---------------------------------------------------------------- dung no trong phep kiem
OLD = '''        metrics["chars_per_second"] = float(rate)
        metrics["pace_outlier"] = float(rate < lower_bound or rate > upper_bound)
'''
NEW = '''        syllable_rate = spoken_syllables(text) / speech_seconds
        metrics["chars_per_second"] = float(rate)
        metrics["syllables_per_second"] = float(syllable_rate)
        metrics["pace_outlier"] = float(pace_is_outlier(rate, syllable_rate, pace, bounds))
'''
assert OLD in s, "khong khop cho dung"
s = s.replace(OLD, NEW, 1)

write_atomic(p, s)
print("da va", p)

TEST = '''"""Một bản thu chỉ chậm khi chậm theo cả chữ lẫn âm tiết — chương 075 của lô 3 là ca gốc.

"Và Alice đã ở đó để tận dụng sơ hở ấy." mất 10/10 lần ở 10,64–11,80 chars/s (sàn 12,5) vì câu
có 2,25 chữ mỗi từ so với trung vị kho 3,33; theo âm tiết nó đọc 4,48/giây, gần trung vị kho
4,67. Cùng họ với lỗi chữ số (`spoken_speakable_chars`): thước đếm sai cái nó nhận là đếm.
"""
from __future__ import annotations

from ebook_reader.audio_io import (
    PACE_SYLLABLES_PER_SECOND_FLOOR,
    pace_is_outlier,
    spoken_speakable_chars,
    spoken_syllables,
)

NORMAL = (12.5, 24.5)
SENTENCE_075 = "Và Alice đã ở đó để tận dụng sơ hở ấy."


def test_the_lost_sentence_of_chapter_075_is_not_slow() -> None:
    speakable = spoken_speakable_chars(SENTENCE_075)
    syllables = spoken_syllables(SENTENCE_075)
    assert (speakable, syllables) == (27, 11)
    for chars_per_second in (10.64, 11.00, 11.38, 11.80):
        speech_seconds = speakable / chars_per_second
        syllable_rate = syllables / speech_seconds
        assert syllable_rate > PACE_SYLLABLES_PER_SECOND_FLOOR["normal"]
        assert not pace_is_outlier(chars_per_second, syllable_rate, "normal", NORMAL), (
            chars_per_second
        )


def test_a_take_slow_by_both_counts_is_still_slow() -> None:
    """Không phải nới sàn: một bản thu 11 chars/s VÀ 3,0 âm tiết/giây vẫn là chậm."""
    assert pace_is_outlier(11.0, 3.0, "normal", NORMAL)


def test_the_upper_bound_is_untouched() -> None:
    assert pace_is_outlier(26.0, 7.0, "normal", NORMAL)
    assert not pace_is_outlier(20.0, 6.0, "normal", NORMAL)


def test_bands_scale_like_the_character_bands() -> None:
    """slow và fast tỉ lệ theo dải chữ như cũ: 7/12,5 và 14/12,5."""
    normal = PACE_SYLLABLES_PER_SECOND_FLOOR["normal"]
    assert abs(PACE_SYLLABLES_PER_SECOND_FLOOR["slow"] - normal * 7.0 / 12.5) < 0.05
    assert abs(PACE_SYLLABLES_PER_SECOND_FLOOR["fast"] - normal * 14.0 / 12.5) < 0.05
    # 4,0 âm tiết/giây: đủ cho 'normal' (sàn 3,75), chưa đủ cho 'fast' (sàn 4,2).
    assert not pace_is_outlier(12.0, 4.0, "normal", NORMAL)
    assert pace_is_outlier(13.0, 4.0, "fast", (14.0, 30.0))


def test_syllables_are_counted_short_on_names_and_digits_on_purpose() -> None:
    """Đếm thiếu là chiều an toàn: nhịp âm tiết đo thấp hơn thật thì chỉ giữ cờ, không tha."""
    assert spoken_syllables("Alice") == 1
    assert spoken_syllables("Chương 22") == 2
    assert spoken_syllables("— …") == 0
'''
q = root / "tests" / "test_pace_counts_syllables_too.py"
write_atomic(q, TEST)
print("da tao", q)
