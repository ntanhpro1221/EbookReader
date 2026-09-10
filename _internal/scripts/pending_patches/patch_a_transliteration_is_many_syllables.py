r"""Va audio_io.py: "I-xo-ho-ta-ra" la NAM am tiet, khong phai mot.

CHUA AP luc viet - lo 4 dang chay. Ap o ranh gioi lo 4 -> 5, va no la ban va sua mot loi
CHINH TOI vua dua vao hom nay.

`patch_pace_counts_syllables_too` (ap 21:19 ngay 2026-09-10) dem am tiet bang `text.split()`, tuc
theo khoang trang. Cach doc tieng Anh trong du an nay luon viet bang **am tiet noi bang gach
ngang** - `Mai-co`, `A-ca-de-mi`, `I-xo-ho-ta-ra` - nen moi cai ten thanh MOT am tiet.

Chuong 084 tra gia trong vong bon tieng. Van ban doc that (sau khi thay cach doc):

    Chung toi dang den Thanh pho I-xo-ho-ta-ra (I-xo-ho-ta-ra Xi-ti).

    dem hien tai      45 ky tu   9 am tiet   -> 2,44 am tiet/giay   -> DUOI san 3,75, gan co
    dem tach gach     45 ky tu  18 am tiet   -> 4,88 am tiet/giay   -> tren san, le ra QUA

Ban thu bi tu 11 lan roi chuong that bai, va `assemble_book` phai lui chuong 084 ve ban cu cua
lo 3 - dan giong cua mot phien ban khac.

Bai hoc, ghi ra vi no dang: trong docstring cua bo dem toi viet rang dem thieu am tiet o ten
rieng la "chieu sai an toan", vi no chi lam GIU nguyen co chu khong tha them. Cau ay dung nhung
khong day du - an toan truoc viec tha nham, KHONG an toan truoc viec chan nham, va chan nham thi
mat ca chuong. Mot sai so mot chieu van la mot sai so; "an toan" phai noi ro la an toan cho ai.

Sua: tach am tiet o **ca gach ngang lan khoang trang**. Dung cung ho voi
`spoken_speakable_chars` (chu so) va `patch_pace_counts_syllables_too` (tu ngan): dem cai giong
doc PHAT RA, khong dem cai chu viet.
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

OLD = '''def spoken_syllables(text: str) -> int:
    """Số âm tiết đọc ra, xấp xỉ bằng số từ: tiếng Việt đơn âm, một từ là một âm tiết.

    Xấp xỉ này đếm THIẾU ở tên nước ngoài ("Alice" hai âm tiết) và chữ số ("22" đọc ba âm
    tiết), tức nhịp âm tiết đo ra thấp hơn thật. Đó là chiều sai an toàn cho việc nó được
    dùng: một bản thu chỉ được tha khi nhịp âm tiết đủ cao, nên đếm thiếu chỉ làm giữ nguyên
    cờ như cũ chứ không tha thêm.
    """
    return sum(1 for token in text.split() if any(char.isalnum() for char in token))'''
NEW = '''# Âm tiết tách nhau bằng khoảng trắng **hoặc gạch ngang**: cách đọc tiếng Anh trong dự án này
# luôn viết bằng âm tiết nối bằng gạch - `Mai-cồ`, `A-ca-đe-mi`, `I-xờ-hờ-ta-ra`.
_SYLLABLE_SPLIT = re.compile(r"[\\s\\-–—]+")


def spoken_syllables(text: str) -> int:
    """Số âm tiết đọc ra: tiếng Việt đơn âm, nên mỗi âm tiết là một cụm chữ giữa hai dấu tách.

    Tách ở **cả gạch ngang lẫn khoảng trắng**. Bản đầu chỉ tách khoảng trắng, và mọi cách đọc
    tên nước ngoài thành một âm tiết - `I-xờ-hờ-ta-ra` đếm 1 thay vì 5. Chương 084 của lô 3 mất
    vì đúng điều đó, bốn tiếng sau khi bộ đếm ấy vào cây: câu
    `Chúng tôi đang đến Thành phố I-xờ-hờ-ta-ra (I-xờ-hờ-ta-ra Xi-ti).` đếm 9 âm tiết thay vì
    18, ra 2,44 âm tiết/giây thay vì 4,88, và bị chặn dưới sàn 3,75 dù đọc hoàn toàn bình
    thường.

    Docstring cũ gọi việc đếm thiếu là "chiều sai an toàn" vì nó chỉ giữ nguyên cờ chứ không
    tha thêm. Câu ấy đúng mà thiếu: an toàn trước việc **tha nhầm**, không an toàn trước việc
    **chặn nhầm** - và chặn nhầm thì mất cả chương. Một sai số một chiều vẫn là sai số.

    Vẫn còn đếm thiếu ở chữ số (`22` đọc ba âm tiết mà viết là một cụm) và ở tên chưa có cách
    đọc trong sổ. Cả hai đều đo được và sửa được; không lấp bằng phỏng đoán ở đây.
    """
    return sum(
        1 for token in _SYLLABLE_SPLIT.split(text) if any(char.isalnum() for char in token)
    )'''
assert OLD in s, "khong khop spoken_syllables"
s = s.replace(OLD, NEW, 1)

write_atomic(p, s)
print("da va", p)

TEST = '''"""Một cách đọc nối bằng gạch ngang là NHIỀU âm tiết - `I-xờ-hờ-ta-ra` là năm, không phải một.

Chương 084 của lô 3 mất vì bộ đếm âm tiết đếm theo khoảng trắng, bốn tiếng sau khi chính bộ đếm
ấy vào cây để cứu chương 075. Cùng một hình dạng lỗi mà nó được viết ra để sửa: đếm chữ viết
thay vì đếm cái giọng đọc phát ra.
"""
from __future__ import annotations

from ebook_reader.audio_io import (
    PACE_SYLLABLES_PER_SECOND_FLOOR,
    pace_is_outlier,
    spoken_speakable_chars,
    spoken_syllables,
)

NORMAL = (12.5, 24.5)
# Đúng văn bản đọc của đoạn đã mất, sau khi thay cách đọc từ sổ phát âm.
LOST_LINE_084 = "Chúng tôi đang đến Thành phố I-xờ-hờ-ta-ra (I-xờ-hờ-ta-ra Xi-ti)."


def test_a_hyphenated_reading_counts_every_syllable() -> None:
    assert spoken_syllables("I-xờ-hờ-ta-ra") == 5
    assert spoken_syllables("Mai-cồ") == 2
    assert spoken_syllables("A-ca-đe-mi Xi-ti") == 6


def test_the_lost_line_of_chapter_084_reads_at_a_normal_pace() -> None:
    speakable = spoken_speakable_chars(LOST_LINE_084)
    syllables = spoken_syllables(LOST_LINE_084)
    assert (speakable, syllables) == (45, 18), "9 âm tiết là con số cũ, và nó làm mất chương"

    speech_seconds = speakable / 12.20
    rate = syllables / speech_seconds
    assert rate > PACE_SYLLABLES_PER_SECOND_FLOOR["normal"]
    assert not pace_is_outlier(12.20, rate, "normal", NORMAL), (
        "đọc 4,88 âm tiết/giây là bình thường; sàn chỉ nên bắt bản thu thật sự chậm"
    )


def test_a_genuinely_slow_take_is_still_caught() -> None:
    """Không phải nới sàn: cùng câu ấy đọc chậm thật thì vẫn bị bắt."""
    syllables = spoken_syllables(LOST_LINE_084)
    speech_seconds = spoken_speakable_chars(LOST_LINE_084) / 8.0
    assert pace_is_outlier(8.0, syllables / speech_seconds, "normal", NORMAL)


def test_plain_vietnamese_counts_exactly_as_before() -> None:
    """Câu không có gạch ngang phải đếm y hệt bản cũ - thay đổi chỉ chạm cách đọc nối gạch."""
    plain = "Và Alice đã ở đó để tận dụng sơ hở ấy."
    assert spoken_syllables(plain) == len(plain.split()) == 11


def test_an_em_dash_between_words_is_a_separator_not_a_syllable() -> None:
    assert spoken_syllables("KENG—!") == 1
    assert spoken_syllables("một — hai") == 2
'''
q = root / "tests" / "test_a_transliteration_is_many_syllables.py"
write_atomic(q, TEST)
print("da tao", q)
