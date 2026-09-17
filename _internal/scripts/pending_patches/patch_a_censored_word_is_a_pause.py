"""Vá text_processing.py: câu chửi bị CHE bằng ký hiệu đọc thành một khoảng ngừng, không đọc tên ký hiệu.

Chạy: python patch_a_censored_word_is_a_pause.py <root>

**CHỈ ÁP Ở MỘT RANH GIỚI, VÀ KHÔNG PHẢI RANH GIỚI 6.** `text_processing.py` nằm trong
`QUALITY_IMPLEMENTATION_FILES` (ghi giữa lô là resume bị từ chối). Hơn nữa, bản vá đổi CHUỖI NÓI của
đúng một đoạn đã thu: chương 225, đoạn 66, trong `lo06_7ba27df135`. Bước 2b của ranh giới 6 sẽ
`resync_spoken_text` project lô ấy và đặt đoạn ấy về chờ thu trong một chương đã `completed`.
Ranh giới 7 chỉ resync `lo07` (304..343, không có ký hiệu nào), còn chương đầu tiên cần bản vá là
385 ở lô 8. Nên xếp vào `ORDER` SAU KHI ranh giới 6 xong hẳn.

## Ca thật

Lô 6 cuốn 2, chương 225, đoạn 66, `ASR_MISMATCH_UNRESOLVED` (độ giống 0,42), máy đã cho qua:

    sách   : “Cái #&!@! Không phải lại nữa chứ?”
    Whisper: "Cái thằng và... À còng... Không phải lại nữa chứ."

Giọng đọc tự nở `#` → "thăng", `&` → "và", `@` → "a còng". `spoken_symbols_to_words` không biết ba ký
tự ấy, nên chúng đi thẳng tới giọng đọc. Người nghe nghe TÊN KÝ HIỆU ngay giữa một câu chửi. Đây là
đúng loại lỗi chủ sách đã từ chối: *"cái đó nó bị lẫn vào làm một thành phần trong câu văn là không được"*.

## Phạm vi, đo trên nguồn cả hai cuốn (17-09)

    cuon 2 (915 chuong): 225 "#&!@!"   385 "***"   386 "***"   699 "?**"
    cuon 1 (478 chuong): 339 "*?*"

`*` đã nằm trong `SPOKEN_DROPPED`, nên `?**` và `*?*` (dấu in đậm/nghiêng sót lại) đã đọc đúng thành
"?". Nhưng `***` thay cho một chữ bị che thì biến mất không để lại dấu vết: "đầu ngươi để dưới *** à?"
thành "đầu ngươi để dưới à?". Người nghe không biết có chữ nào vừa bị che.

## Luật

Một chuỗi liền >= 3 ký tự trong `#&@$%*!?` là **chữ bị che** khi nó có ít nhất một trong `#&@$`, hoặc
có ít nhất ba dấu `*`. Chuỗi ấy thành "…", tức một khoảng ngừng. Không đổi gì khác:

- `?**`, `*?*` - chỉ một hai dấu `*`, không `#&@$` → luật cũ (bỏ `*`, giữ dấu câu).
- `?!?`, `!!!` - không có ký tự che → giữ nguyên.
- `100%!!` - `%` không đủ để gọi là che (phần trăm đứng sau số) → giữ nguyên.
- Cả đoạn chỉ là ký hiệu, không một chữ cái nào (ví dụ một dòng `***` ngăn cảnh ở sách khác) → luật
  cũ (bỏ hết). Một đoạn chỉ còn "…" là một đoạn im lặng giao cho TTS.

Ổn định trên chính đầu ra và mọi mảnh của nó: "…" không phải ký tự luật này hay luật nào khác trong
hàm đổi, và luật không neo vào đầu hay cuối chuỗi.
"""
import io
import sys
from pathlib import Path

root = Path(sys.argv[1])
p = root / "ebook_reader" / "text_processing.py"
s = io.open(p, encoding="utf-8").read()

OLD_TRIM = '''_SPOKEN_BOUNDARY_TRIM = SPOKEN_SEPARATORS + SPOKEN_DROPPED + " \\t\\r\\n"
'''
NEW_TRIM = '''_SPOKEN_BOUNDARY_TRIM = SPOKEN_SEPARATORS + SPOKEN_DROPPED + " \\t\\r\\n"
# Chữ bị CHE bằng ký hiệu ("Cái #&!@!", "dưới *** à") là một khoảng ngừng, không phải tên ký hiệu.
# Lô 6 cuốn 2 chương 225: giọng đọc tự nở # & @ thành "thăng", "và", "a còng" ngay giữa câu chửi.
# Luật và các ca KHÔNG đụng tới: xem scripts/pending_patches/patch_a_censored_word_is_a_pause.py.
_CENSOR_RUN = re.compile(r"[#&@$%*!?]{3,}")
_CENSOR_MARKS = "#&@$"
_HAS_LETTER = re.compile(r"[^\\W\\d_]", re.UNICODE)


def _censored_words_as_pauses(text: str) -> str:
    if not _HAS_LETTER.search(text):
        return text

    def pause(match: re.Match[str]) -> str:
        run = match.group(0)
        if any(mark in run for mark in _CENSOR_MARKS) or run.count("*") >= 3:
            return "…"
        return run

    return _CENSOR_RUN.sub(pause, text)
'''
assert s.count(OLD_TRIM) == 1, "khong khop _SPOKEN_BOUNDARY_TRIM"
s = s.replace(OLD_TRIM, NEW_TRIM, 1)

OLD_SOURCE = '''    source = str(text).replace("=>", "→")
'''
NEW_SOURCE = '''    source = _censored_words_as_pauses(str(text).replace("=>", "→"))
'''
assert s.count(OLD_SOURCE) == 1, "khong khop dong source trong spoken_symbols_to_words"
s = s.replace(OLD_SOURCE, NEW_SOURCE, 1)
assert "import re" in s, "text_processing.py phai da import re"
io.open(p, "w", encoding="utf-8", newline="\n").write(s)
print(f"da va {p}")

TEST = '''"""Chữ bị che bằng ký hiệu đọc thành khoảng ngừng - xem patch_a_censored_word_is_a_pause.py."""
from __future__ import annotations

import pytest

from ebook_reader.text_processing import spoken_symbols_to_words


@pytest.mark.parametrize(
    ("text", "spoken"),
    [
        ("\\u201cC\\u00e1i #&!@! Kh\\u00f4ng ph\\u1ea3i l\\u1ea1i n\\u1eefa ch\\u1ee9?\\u201d",
         "\\u201cC\\u00e1i\\u2026 Kh\\u00f4ng ph\\u1ea3i l\\u1ea1i n\\u1eefa ch\\u1ee9?\\u201d"),
        ("\\u0111\\u1ea7u ng\\u01b0\\u01a1i \\u0111\\u1ec3 d\\u01b0\\u1edbi *** \\u00e0?",
         "\\u0111\\u1ea7u ng\\u01b0\\u01a1i \\u0111\\u1ec3 d\\u01b0\\u1edbi\\u2026 \\u00e0?"),
    ],
    ids=["chuong 225 #&!@!", "chuong 385 ***"],
)
def test_a_censored_word_becomes_a_pause(text: str, spoken: str) -> None:
    assert spoken_symbols_to_words(text) == spoken


@pytest.mark.parametrize(
    ("text", "spoken"),
    [
        ("Vua Tai H\\u1ecda Viken?**", "Vua Tai H\\u1ecda Viken?"),
        ("ch\\u1ec9 \\u1edf c\\u1ea5p A*?*", "ch\\u1ec9 \\u1edf c\\u1ea5p A?"),
        ("H\\u1ea3?!?", "H\\u1ea3?!?"),
        ("Tr\\u1eddi \\u01a1i!!!", "Tr\\u1eddi \\u01a1i!!!"),
        ("\\u0111\\u1ee7 100%!!", "\\u0111\\u1ee7 100%!!"),
        ("***", ""),
    ],
    ids=["dau in dam sot lai", "dau nghieng sot lai", "?!?", "!!!", "phan tram", "dong ngan canh"],
)
def test_what_is_not_a_censored_word_keeps_its_old_reading(text: str, spoken: str) -> None:
    assert spoken_symbols_to_words(text) == spoken


def test_the_pause_is_stable_on_its_own_output_and_on_its_fragments() -> None:
    once = spoken_symbols_to_words("\\u201cC\\u00e1i #&!@! Kh\\u00f4ng ph\\u1ea3i l\\u1ea1i n\\u1eefa ch\\u1ee9?\\u201d")
    assert spoken_symbols_to_words(once) == once
    for cut in range(1, len(once)):
        for piece in (once[:cut], once[cut:]):
            assert spoken_symbols_to_words(spoken_symbols_to_words(piece)) == spoken_symbols_to_words(piece)
'''
t = root / "tests" / "test_a_censored_word_is_a_pause.py"
io.open(t, "w", encoding="utf-8", newline="\n").write(TEST)
print(f"da tao {t}")
