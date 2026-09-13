"""Va text_processing.py: dau "+" va "=" trong mot cong thuc la CHU ("cong", "bang"), khong phai ky hieu de nguyen.

Cuon 2, lo 1, chuong 025 (chapter_index 26), doan c00026_s0000015_1e32f852fb08:

    "Nam xac chet + Mo nao thuy quy + Bui oan linh + Bui hoa hong anh trang = Linh Hon Than Khoc"

Giong doc phat ra dung nhu nguoi Viet doc cong thuc: "... cong mo nao thuy quy cong ... bang linh hon than
khoc" - Whisper viet lai y nhu the, bang CHU. Nhung chuoi doi chieu (`spoken_symbols_to_words(row["text"])`,
tts.py) con giu nguyen "+" va "=" vi `SPOKEN_SYMBOL_WORDS` chi biet hai mui ten ↓ ↑. Do giong 0,73 duoi
nguong, nam ung vien sua deu `beam=ASR_MISMATCH; greedy=ASR_MISMATCH`, ngan sach sua het, doan bi danh
`failed` roi may cho qua khong nguoi nghe. Ban thu KHONG hong; thuoc do sai - va mot thuoc sai thi lan sau
mot ban thu hong that o dung cho ay se khong bi bat.

Do truoc khi sua (2026-09-14, 06:45):
  - nguon cuon 2 (915 chuong): 40 dau "+", 26 dau "=", tren 28 dong cua 20 chuong - cong thuc gia kim,
    Goldbach "1+1"/"9+9", "E = mc^2", "N >= 3", "4 = 2 + 2"; "=>" dung lam mui ten (3 lan, 2 lan dau dong).
    Ngu canh khac cua "+" chi la dong ghi cong dich gia "Trans+Edit" - doc "cong" vo hai.
  - "%" KHONG can sua: cuon 1 co 6 doan "25%" deu verified (Whisper viet lai dung ky hieu %).
  - cuon 1 (lo 1..10, 30.926 doan) khong co "+" hay "=" nao - vi sao loi nay chua tung lo.

Sua:
  1. `SPOKEN_SYMBOL_WORDS` them "+" -> "cong", "=" -> "bang", ">=" (U+2265) -> "lon hon hoac bang",
     "<=" (U+2264) -> "nho hon hoac bang", "^" -> "mu", "x" (U+00D7) -> "nhan", "÷" -> "chia".
  2. "=>" duoc doi thanh "→" TRUOC moi buoc khac - "→" da nam trong SPOKEN_SEPARATORS nen dau dong thi
     bi cat, giua cau thi thanh dau phay; neu khong doi truoc, "=" trong "=>" se thanh "bang".
Ham van on dinh tren chinh output cua no: "cong"/"bang" la chu, chay lai khong doi gi.

Chay: python patch_a_formula_is_read_as_words.py <root>   (apply_all.py goi voi root la cay that)
"""
import io
import sys
from pathlib import Path

root = Path(sys.argv[1])
p = root / "ebook_reader" / "text_processing.py"
s = io.open(p, encoding="utf-8").read()

OLD_MAP = '''SPOKEN_SYMBOL_WORDS = {
    "↓": "giảm",
    "↑": "tăng",
}
'''
NEW_MAP = '''SPOKEN_SYMBOL_WORDS = {
    "↓": "giảm",
    "↑": "tăng",
    # Ký hiệu toán trong một công thức: giọng đọc phát ra CHỮ và Whisper viết lại CHỮ ("cộng",
    # "bằng"), nên chuỗi đối chiếu cũng phải là chữ - cuốn 2 lô 1 chương 025, "Nấm xác chết + Mô
    # não thủy quỷ + … = Linh Hồn Than Khóc" đo 0,73 với bản thu hoàn toàn đúng, năm ứng viên
    # sửa đều trượt cùng một cách, và đoạn bị đánh hỏng vì thước đo chứ không vì giọng.
    # "%" cố ý KHÔNG có ở đây: Whisper viết lại "25%" đúng ký hiệu (6/6 đoạn cuốn 1 verified).
    "+": "cộng",
    "=": "bằng",
    "≥": "lớn hơn hoặc bằng",
    "≤": "nhỏ hơn hoặc bằng",
    "^": "mũ",
    "×": "nhân",
    "÷": "chia",
}
'''
assert s.count(OLD_MAP) == 1, "khong khop SPOKEN_SYMBOL_WORDS"
s = s.replace(OLD_MAP, NEW_MAP, 1)

OLD_SOURCE = '''    source = str(text)
    spans: list[tuple[str, bool]] = []
    position = 0
    for match in VOCAL_CUE_PATTERN.finditer(source):
'''
NEW_SOURCE = '''    # "=>" là một mũi tên, không phải "bằng" rồi "lớn hơn": đổi thành → trước mọi bước khác, để
    # luật sẵn có của SPOKEN_SEPARATORS lo phần còn lại (đầu dòng thì cắt, giữa câu thì phẩy).
    source = str(text).replace("=>", "→")
    spans: list[tuple[str, bool]] = []
    position = 0
    for match in VOCAL_CUE_PATTERN.finditer(source):
'''
assert s.count(OLD_SOURCE) == 1, "khong khop dau ham spoken_symbols_to_words"
s = s.replace(OLD_SOURCE, NEW_SOURCE, 1)
io.open(p, "w", encoding="utf-8", newline="\n").write(s)
print(f"da va {p}")

TEST = '''"""A formula is read as words: "+" is "cộng" and "=" is "bằng", for the voice and for the check alike.

Book 2, batch 1, chapter 025: the alchemy recipe "A + B + C = D" was spoken correctly - Whisper
wrote "cộng" and "bằng" - and failed anyway, because the comparison string still carried the
symbols. Five repair candidates fell the same way. The take was right; the ruler was wrong.
Measured before patching: 40 "+" and 26 "=" across 28 lines of the 915-chapter source; "%" needs
nothing (Whisper writes "25%" back as a symbol, 6/6 verified in book 1).
"""
from __future__ import annotations

from ebook_reader.text_processing import spoken_symbols_to_words


def test_an_alchemy_recipe_is_read_as_words() -> None:
    assert (
        spoken_symbols_to_words("Nấm xác chết + Mô não thủy quỷ + Bụi oán linh = Linh Hồn Than Khóc")
        == "Nấm xác chết cộng Mô não thủy quỷ cộng Bụi oán linh bằng Linh Hồn Than Khóc"
    )


def test_goldbach_and_einstein() -> None:
    assert spoken_symbols_to_words("Ví dụ như 4 = 2 + 2, 10 = 7 + 3.") == "Ví dụ như 4 bằng 2 cộng 2, 10 bằng 7 cộng 3."
    assert spoken_symbols_to_words("chứng minh ‘1+1’ đó") == "chứng minh ‘1 cộng 1’ đó"
    assert spoken_symbols_to_words("“E = mc^2.”") == "“E bằng mc mũ 2.”"
    assert spoken_symbols_to_words("Nhưng với N ≥ 3, đặc biệt") == "Nhưng với N lớn hơn hoặc bằng 3, đặc biệt"


def test_a_double_arrow_is_a_pause_not_an_equals_sign() -> None:
    assert spoken_symbols_to_words("khác nhau => đưa 2 bình vào") == "khác nhau, đưa 2 bình vào"
    # Leading arrow: nothing precedes it, so nothing to separate - same as a bullet.
    assert spoken_symbols_to_words("=> Hiện tượng trên gây mâu thuẫn") == "Hiện tượng trên gây mâu thuẫn"


def test_percent_is_left_for_the_transcriber_to_write_back() -> None:
    assert spoken_symbols_to_words("bị trừ 25% điểm số") == "bị trừ 25% điểm số"


def test_stable_on_its_own_output() -> None:
    once = spoken_symbols_to_words("Dạng 1+2: 1 số nguyên tố + 2 số nguyên tố (ví dụ 10 = 5 + (2 + 3))")
    assert once == spoken_symbols_to_words(once)
    assert "+" not in once and "=" not in once


def test_a_vocal_cue_still_passes_through() -> None:
    assert spoken_symbols_to_words("[thở dài] 1 + 1 = 2") == "[thở dài] 1 cộng 1 bằng 2"
'''
t = root / "tests" / "test_a_formula_is_read_as_words.py"
io.open(t, "w", encoding="utf-8", newline="\n").write(TEST)
print(f"da tao {t}")
