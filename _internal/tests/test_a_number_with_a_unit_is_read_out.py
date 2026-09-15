"""Whisper viết `10h30`, sách viết `mười giờ ba mươi` — cùng một câu đọc ra, phải khớp.

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
    book = "B\u00e2y gi\u1edd \u0111\u00e3 l\u00e0 m\u01b0\u1eddi hai gi\u1edd ba m\u01b0\u01a1i l\u0103m ph\u00fat chi\u1ec1u."
    heard = "B\u00e2y gi\u1edd \u0111\u00e3 l\u00e0 12h35 ph\u00fat chi\u1ec1u."

    similarity, wer = transcript_metrics(book, heard)

    assert similarity > 0.99, similarity
    assert wer < 0.01, wer


def test_the_percent_sign_the_punctuation_stripper_ate() -> None:
    book = "Nh\u01b0ng ch\u1ec9 d\u00e0nh cho m\u1ed9t ph\u1ea7n tr\u0103m d\u00e2n s\u1ed1 \u0111\u1ee9ng tr\u00ean \u0111\u1ec9nh kim t\u1ef1 th\u00e1p."
    heard = "nh\u01b0ng ch\u1ec9 d\u00e0nh cho 1% d\u00e2n s\u1ed1 \u0111\u1ee9ng tr\u00ean \u0111\u1ec9nh kim t\u1ef1 th\u00e1p."

    similarity, _wer = transcript_metrics(book, heard)

    assert similarity > 0.99, similarity


def test_a_bare_hour_matches_too() -> None:
    book = "M\u01b0\u1eddi gi\u1edd s\u00e1ng. Ph\u00f2ng t\u1eadp c\u1ee7a Victor."
    heard = "10h s\u00e1ng, ph\u00f2ng t\u1eadp c\u1ee7a Victor."

    similarity, _wer = transcript_metrics(book, heard)

    assert similarity > 0.99, similarity


def test_the_sentence_that_would_get_worse_does_not() -> None:
    """`chín rưỡi` không phải `chín giờ ba mươi`; phép nở chỉ được thêm, không được lấy đi."""
    book = (
        "Sau ch\u00edn r\u01b0\u1ee1i, ph\u00f2ng kh\u00e1ch cu\u1ed1i c\u00f9ng c\u0169ng y\u00ean t\u0129nh."
        " Lucien kh\u00f3a tr\u00e1i c\u1eeda, th\u1ed5i t\u1eaft n\u1ebfn r\u1ed3i n\u1eb1m xu\u1ed1ng trong b\u00f3ng t\u1ed1i."
    )
    heard = (
        "Sau 9h30, ph\u00f2ng kh\u00e1ch cu\u1ed1i c\u00f9ng c\u0169ng y\u00ean t\u0129nh."
        " Lucien kh\u00f3a tr\u00e1i c\u1eeda, th\u1ed5i t\u1eaft n\u1ebfn r\u1ed3i n\u1eb1m xu\u1ed1ng trong b\u00f3ng t\u1ed1i."
    )

    similarity, _wer = transcript_metrics(book, heard)
    swapped, _swapped_wer = transcript_metrics(fold_number_units(book), fold_number_units(heard))

    assert swapped < similarity, "đúng ca thật: thay thẳng thì tệ hơn"
    assert similarity > 0.92, similarity


def test_the_second_reading_only_runs_when_the_shape_is_there() -> None:
    assert has_unit_number("l\u00fac 10h30")
    assert has_unit_number("40% ti\u1ec1n thu \u0111\u01b0\u1ee3c")
    assert not has_unit_number("m\u01b0\u1eddi gi\u1edd ba m\u01b0\u01a1i")
    assert not has_unit_number("Ch\u01b0\u01a1ng 100 - L\u1ecbch s\u1eed")
    assert not has_unit_number("n\u0103m 2026")


def test_the_expansion_spells_the_number_the_way_the_book_does() -> None:
    assert fold_number_units("l\u00fac 10h30") == "l\u00fac m\u01b0\u1eddi gi\u1edd ba m\u01b0\u01a1i"
    assert fold_number_units("10h s\u00e1ng") == "m\u01b0\u1eddi gi\u1edd s\u00e1ng"
    assert fold_number_units("40% ti\u1ec1n") == "b\u1ed1n m\u01b0\u01a1i ph\u1ea7n tr\u0103m ti\u1ec1n"
    assert fold_number_units("1% d\u00e2n s\u1ed1") == "m\u1ed9t ph\u1ea7n tr\u0103m d\u00e2n s\u1ed1"


def test_a_year_or_a_chapter_number_is_left_alone() -> None:
    """`_fold_number_digits` đã cố ý không nở số trên 999; phép này không được mở lại cửa ấy."""
    assert fold_number_units("n\u0103m 2026") == "n\u0103m 2026"
    assert fold_number_units("Ch\u01b0\u01a1ng 100") == "Ch\u01b0\u01a1ng 100"
    # `normalize_transcript` hạ hoa-thường và đổi `đ`→`d`, **không** bỏ dấu: bản đầu của bài này
    # đòi "nam 2026" và đỏ ngay, vì tôi lẫn nó với phép gộp dấu ở chỗ khác.
    assert normalize_transcript("N\u0103m 2026") == "n\u0103m 2026"


def test_two_identical_sides_still_score_one() -> None:
    for text in ("l\u00fac 10h30", "40% ti\u1ec1n thu", "kh\u00f4ng c\u00f3 s\u1ed1 n\u00e0o"):
        similarity, wer = transcript_metrics(text, text)
        assert similarity == 1.0 and wer == 0.0, text
