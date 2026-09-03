"""A number written two ways is one number, and it used to fail whole chapters.

alpha.32's chapter 6 was refused over one segment:

    text:  "Hôm nay là ngày 24 tháng Mười hai."
    heard: "Hôm nay là ngày 24 tháng 12."

The voice read it exactly right. Whisper writes digits where the book writes words, and the
folding table stopped at ten, so "mười hai" against "12" scored as an error. The same gap
turned "thứ Mười" into a near miss and "bốn mươi mốt" into a full one.
"""
from ebook_reader.asr import NUMBER_FOLD_CEILING, normalize_transcript
from ebook_reader.text_processing import vietnamese_number_words


def _same(left: str, right: str) -> bool:
    return normalize_transcript(left) == normalize_transcript(right)


def test_the_segment_that_failed_a_chapter_now_matches() -> None:
    assert _same("Hôm nay là ngày 24 tháng Mười hai.", "Hôm nay là ngày 24 tháng 12.")


def test_the_two_near_misses_from_the_same_run_match_too() -> None:
    assert _same("Hoàng Tử Quỷ Thứ Mười", "hoàng tử quỷ thứ 10")
    assert _same("trong cả bốn mươi mốt tuyến truyện", "trong cả 41 tuyến truyện")


def test_it_reaches_as_far_as_the_speller_does() -> None:
    """The old table held eleven entries and answered the same question worse."""
    for value in (0, 1, 10, 11, 15, 20, 21, 24, 41, 99, 100, 105, NUMBER_FOLD_CEILING):
        assert _same(str(value), vietnamese_number_words(value)), value


def test_a_year_is_left_as_it_was_written() -> None:
    """Above the speller's range there is no settled spoken form to fold to, and inventing
    one would make two different things compare equal."""
    assert normalize_transcript("năm 2026") == "năm 2026"
    assert normalize_transcript(str(NUMBER_FOLD_CEILING + 1)) == str(NUMBER_FOLD_CEILING + 1)


def test_a_designation_is_not_a_count() -> None:
    """"007" is a name written in digits; folding it to "bảy" would be a mistranslation."""
    assert normalize_transcript("phòng 007") == "phòng 007"
    assert normalize_transcript("00") == "00"
    assert normalize_transcript("0") == "không", "a bare zero really is a number"


def test_a_token_that_is_not_all_digits_is_untouched() -> None:
    assert normalize_transcript("3a") == "3a"
    assert normalize_transcript("b2") == "b2"


def test_folding_does_not_make_different_numbers_equal() -> None:
    assert not _same("12", "21")
    assert not _same("ngày 24 tháng 12", "ngày 12 tháng 24")
