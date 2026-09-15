"""Va asr.py: Whisper viet `10h30`, sach viet `muoi gio ba muoi` - cho hai ben gap nhau.

Chay: python patch_a_number_with_a_unit_is_read_out.py <root>

**CHI AP O MOT RANH GIOI.** `asr.py` nam trong `QUALITY_IMPLEMENTATION_FILES`, nen ghi vao no
giua lo se doi `quality_implementation_hash()` va lo dang bay bi tu choi khi resume (sang
15-09: 2.035 requeue + 30 MP3 phai lam lai).

## Ca that va so lieu

`normalize_transcript` da no **token toan chu so** thanh chu (`_fold_number_digits`, toi 999),
nen `24` gap `hai muoi bon` la khop. Nhung token co **don vi dinh lien** thi khong phai toan
chu so, va `%` thi bi xoa han:

    sach   : "Bay gio da la muoi hai gio ba muoi lam phut chieu."
    Whisper: "Bay gio da la 12h35 phut chieu."            do giong 0,53
    sach   : "Nhung chi danh cho mot phan tram dan so..."
    Whisper: "nhung chi danh cho 1% dan so..."            do giong 0,85

Do bang `scripts/measure_a_number_with_a_unit.py` tren **75.881 doan co ban ghi ASR** cua ca hai
cuon (136 project):

    126 doan co so dinh don vi o mot trong hai ben
     36 doan dang duoi 0,90
     19 doan duoc cuu len tren 0,90
      0 doan te hon

## Vi sao lay CACH DOC TOT HON cua hai, khong thay thang

Thay thang ban no vao thi **5 doan te hon**, va ca 5 la cung mot cau that:

    sach   : "Sau chin ruoi, phong khach cuoi cung cung yen tinh..."
    Whisper: "Sau 9h30, phong khach cuoi cung cung yen tinh..."
             0,9286 -> 0,9196   (vi "chin ruoi" khong phai "chin gio ba muoi")

Nen phep no chi **them mot cach doc**, roi lay cai tot hon: `similarity = max(...)`,
`wer = min(...)`. Dung ly le ma `_content_metrics_ignoring_tone` da ghi cho phep gop thanh
dieu - *"provably unable to fail anything the plain comparison passed"*. Mot phep chuan hoa chi
duoc them co hoi khop, khong duoc lay di.

Phep no chi chay khi mot trong hai ben co hinh ay (126/75.881 doan), nen no khong ton gi cho
phan con lai.
"""
import io
import sys
from pathlib import Path

root = Path(sys.argv[1])
p = root / "ebook_reader" / "asr.py"
s = io.open(p, encoding="utf-8").read()

OLD_ANCHOR = '''def normalize_transcript(text: str) -> str:'''
NEW_ANCHOR = '''# Số dính đơn vị: `10h`, `10h30`, `25%`, `12kg`. Whisper viết thế còn sách viết bằng chữ, và
# `_fold_number_digits` không chạm tới chúng vì token không phải toàn chữ số. Đo trên 75.881 đoạn
# có bản ghi ASR của cả hai cuốn: 126 đoạn có hình này, 36 đang dưới 0,90 và 19 được cứu.
#
# `%` là ca âm thầm nhất: `normalize_transcript` thay mọi ký tự không phải chữ/số bằng dấu cách,
# nên `25%` thành `25` rồi nở thành `hai mươi lăm`, và chữ "phần trăm" của sách không có gì để
# khớp - hai bên đọc giống nhau mà vẫn bị trừ điểm.
UNIT_NUMBER_PATTERN = re.compile(
    r"(?<![0-9A-Za-zÀ-ỹ])([0-9]{1,3})\\s*(h|%|kg|km|cm|m|°)(?![0-9A-Za-zÀ-ỹ])"
)
HOUR_MINUTE_PATTERN = re.compile(
    r"(?<![0-9A-Za-zÀ-ỹ])([0-9]{1,2})\\s*h\\s*([0-9]{1,2})(?![0-9A-Za-zÀ-ỹ])"
)
NUMBER_UNIT_WORDS = {
    "h": "giờ",
    "%": "phần trăm",
    "kg": "ki lô gam",
    "km": "ki lô mét",
    "cm": "xen ti mét",
    "m": "mét",
    "°": "độ",
}


def has_unit_number(text: str) -> bool:
    """Một trong hai bên có số dính đơn vị không? Không có thì khỏi tính cách đọc thứ hai."""
    return bool(UNIT_NUMBER_PATTERN.search(text) or HOUR_MINUTE_PATTERN.search(text))


def fold_number_units(text: str) -> str:
    """`10h30` → `mười giờ ba mươi`, `25%` → `hai mươi lăm phần trăm`.

    Giờ-phút xét trước, vì `10h30` cũng khớp mẫu một-đơn-vị và nếu để mẫu kia chạy trước thì
    `30` còn lại sẽ thành một con số lạc.
    """

    def _hour_minute(match: "re.Match[str]") -> str:
        hour, minute = int(match.group(1)), int(match.group(2))
        return f"{vietnamese_number_words(hour)} giờ {vietnamese_number_words(minute)}"

    def _unit(match: "re.Match[str]") -> str:
        value, unit = int(match.group(1)), match.group(2)
        return f"{vietnamese_number_words(value)} {NUMBER_UNIT_WORDS[unit]}"

    return UNIT_NUMBER_PATTERN.sub(_unit, HOUR_MINUTE_PATTERN.sub(_hour_minute, text))


def normalize_transcript(text: str) -> str:'''
assert s.count(OLD_ANCHOR) == 1, "khong khop normalize_transcript"
s = s.replace(OLD_ANCHOR, NEW_ANCHOR, 1)

OLD_METRICS = '''def transcript_metrics(expected: str, actual: str) -> tuple[float, float]:
    normalized_expected = normalize_transcript(expected)
    normalized_actual = normalize_transcript(actual)'''
NEW_METRICS = '''def transcript_metrics(expected: str, actual: str) -> tuple[float, float]:
    """Độ giống và WER, lấy **cách đọc tốt hơn** khi một bên viết số dính đơn vị.

    Whisper viết `12h35` còn sách viết `mười hai giờ ba mươi lăm`; cùng một câu đọc ra, mà phép
    so cho 0,53. Nở đơn vị ra chữ rồi so lần nữa, và giữ cái tốt hơn của hai lần: đo trên
    75.881 đoạn có bản ghi ASR thì 19 đoạn đi từ dưới 0,90 lên trên, và **0 đoạn tệ hơn**.

    Vì sao không thay thẳng bản nở vào: thế thì 5 đoạn tệ hơn, cả 5 là một câu thật - `Sau chín
    rưỡi` gặp `Sau 9h30` tụt từ 0,9286 xuống 0,9196, vì "chín rưỡi" không phải "chín giờ ba
    mươi". Một phép chuẩn hoá chỉ được thêm cơ hội khớp, không được lấy đi - cùng lý lẽ mà
    `_content_metrics_ignoring_tone` đã ghi cho phép gộp thanh điệu.
    """
    similarity, wer = _transcript_metrics_once(expected, actual)
    if has_unit_number(expected) or has_unit_number(actual):
        spoken_similarity, spoken_wer = _transcript_metrics_once(
            fold_number_units(expected), fold_number_units(actual)
        )
        similarity = max(similarity, spoken_similarity)
        wer = min(wer, spoken_wer)
    return float(similarity), float(wer)


def _transcript_metrics_once(expected: str, actual: str) -> tuple[float, float]:
    normalized_expected = normalize_transcript(expected)
    normalized_actual = normalize_transcript(actual)'''
assert s.count(OLD_METRICS) == 1, "khong khop transcript_metrics"
s = s.replace(OLD_METRICS, NEW_METRICS, 1)

assert "import re" in s, "asr.py phai da import re"
assert "vietnamese_number_words" in s, "asr.py phai da import vietnamese_number_words"
io.open(p, "w", encoding="utf-8", newline="\n").write(s)
print(f"da va {p}")

TEST = '''"""Whisper viết `10h30`, sách viết `mười giờ ba mươi` — cùng một câu đọc ra, phải khớp.

`normalize_transcript` đã nở token **toàn chữ số** thành chữ từ alpha.32 (`_fold_number_digits`,
tới 999), nên `24` gặp `hai mươi bốn` là khớp. Token có **đơn vị dính liền** thì không: `12h35`
không phải toàn chữ số, và `%` thì bị phép xoá dấu câu ăn mất, nên chữ "phần trăm" của sách
không còn gì để khớp.

Đo trên 75.881 đoạn có bản ghi ASR của cả hai cuốn (136 project): 126 đoạn có hình này, 36 đang
dưới 0,90, **19 được cứu**, **0 tệ hơn**.

Bài `test_the_sentence_that_would_get_worse_does_not` giữ lý do phép nở phải **thêm một cách
đọc** chứ không thay thẳng: `Sau chín rưỡi` gặp `Sau 9h30` tụt 0,9286 → 0,9196 nếu thay.
"""
from __future__ import annotations

from ebook_reader.asr import (
    fold_number_units,
    has_unit_number,
    normalize_transcript,
    transcript_metrics,
)


def test_the_hour_that_cost_half_the_score() -> None:
    book = "B\\u00e2y gi\\u1edd \\u0111\\u00e3 l\\u00e0 m\\u01b0\\u1eddi hai gi\\u1edd ba m\\u01b0\\u01a1i l\\u0103m ph\\u00fat chi\\u1ec1u."
    heard = "B\\u00e2y gi\\u1edd \\u0111\\u00e3 l\\u00e0 12h35 ph\\u00fat chi\\u1ec1u."

    similarity, wer = transcript_metrics(book, heard)

    assert similarity > 0.99, similarity
    assert wer < 0.01, wer


def test_the_percent_sign_the_punctuation_stripper_ate() -> None:
    book = "Nh\\u01b0ng ch\\u1ec9 d\\u00e0nh cho m\\u1ed9t ph\\u1ea7n tr\\u0103m d\\u00e2n s\\u1ed1 \\u0111\\u1ee9ng tr\\u00ean \\u0111\\u1ec9nh kim t\\u1ef1 th\\u00e1p."
    heard = "nh\\u01b0ng ch\\u1ec9 d\\u00e0nh cho 1% d\\u00e2n s\\u1ed1 \\u0111\\u1ee9ng tr\\u00ean \\u0111\\u1ec9nh kim t\\u1ef1 th\\u00e1p."

    similarity, _wer = transcript_metrics(book, heard)

    assert similarity > 0.99, similarity


def test_a_bare_hour_matches_too() -> None:
    book = "M\\u01b0\\u1eddi gi\\u1edd s\\u00e1ng. Ph\\u00f2ng t\\u1eadp c\\u1ee7a Victor."
    heard = "10h s\\u00e1ng, ph\\u00f2ng t\\u1eadp c\\u1ee7a Victor."

    similarity, _wer = transcript_metrics(book, heard)

    assert similarity > 0.99, similarity


def test_the_sentence_that_would_get_worse_does_not() -> None:
    """`chín rưỡi` không phải `chín giờ ba mươi`; phép nở chỉ được thêm, không được lấy đi."""
    book = (
        "Sau ch\\u00edn r\\u01b0\\u1ee1i, ph\\u00f2ng kh\\u00e1ch cu\\u1ed1i c\\u00f9ng c\\u0169ng y\\u00ean t\\u0129nh."
        " Lucien kh\\u00f3a tr\\u00e1i c\\u1eeda, th\\u1ed5i t\\u1eaft n\\u1ebfn r\\u1ed3i n\\u1eb1m xu\\u1ed1ng trong b\\u00f3ng t\\u1ed1i."
    )
    heard = (
        "Sau 9h30, ph\\u00f2ng kh\\u00e1ch cu\\u1ed1i c\\u00f9ng c\\u0169ng y\\u00ean t\\u0129nh."
        " Lucien kh\\u00f3a tr\\u00e1i c\\u1eeda, th\\u1ed5i t\\u1eaft n\\u1ebfn r\\u1ed3i n\\u1eb1m xu\\u1ed1ng trong b\\u00f3ng t\\u1ed1i."
    )

    similarity, _wer = transcript_metrics(book, heard)
    swapped, _swapped_wer = transcript_metrics(fold_number_units(book), fold_number_units(heard))

    assert swapped < similarity, "đúng ca thật: thay thẳng thì tệ hơn"
    assert similarity > 0.92, similarity


def test_the_second_reading_only_runs_when_the_shape_is_there() -> None:
    assert has_unit_number("l\\u00fac 10h30")
    assert has_unit_number("40% ti\\u1ec1n thu \\u0111\\u01b0\\u1ee3c")
    assert not has_unit_number("m\\u01b0\\u1eddi gi\\u1edd ba m\\u01b0\\u01a1i")
    assert not has_unit_number("Ch\\u01b0\\u01a1ng 100 - L\\u1ecbch s\\u1eed")
    assert not has_unit_number("n\\u0103m 2026")


def test_the_expansion_spells_the_number_the_way_the_book_does() -> None:
    assert fold_number_units("l\\u00fac 10h30") == "l\\u00fac m\\u01b0\\u1eddi gi\\u1edd ba m\\u01b0\\u01a1i"
    assert fold_number_units("10h s\\u00e1ng") == "m\\u01b0\\u1eddi gi\\u1edd s\\u00e1ng"
    assert fold_number_units("40% ti\\u1ec1n") == "b\\u1ed1n m\\u01b0\\u01a1i ph\\u1ea7n tr\\u0103m ti\\u1ec1n"
    assert fold_number_units("1% d\\u00e2n s\\u1ed1") == "m\\u1ed9t ph\\u1ea7n tr\\u0103m d\\u00e2n s\\u1ed1"


def test_a_year_or_a_chapter_number_is_left_alone() -> None:
    """`_fold_number_digits` đã cố ý không nở số trên 999; phép này không được mở lại cửa ấy."""
    assert fold_number_units("n\\u0103m 2026") == "n\\u0103m 2026"
    assert fold_number_units("Ch\\u01b0\\u01a1ng 100") == "Ch\\u01b0\\u01a1ng 100"
    # `normalize_transcript` hạ hoa-thường và đổi `đ`→`d`, **không** bỏ dấu: bản đầu của bài này
    # đòi "nam 2026" và đỏ ngay, vì tôi lẫn nó với phép gộp dấu ở chỗ khác.
    assert normalize_transcript("N\\u0103m 2026") == "n\\u0103m 2026"


def test_two_identical_sides_still_score_one() -> None:
    for text in ("l\\u00fac 10h30", "40% ti\\u1ec1n thu", "kh\\u00f4ng c\\u00f3 s\\u1ed1 n\\u00e0o"):
        similarity, wer = transcript_metrics(text, text)
        assert similarity == 1.0 and wer == 0.0, text
'''
t = root / "tests" / "test_a_number_with_a_unit_is_read_out.py"
io.open(t, "w", encoding="utf-8", newline="\n").write(TEST)
print(f"da tao {t}")
