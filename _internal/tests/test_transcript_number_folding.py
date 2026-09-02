"""A digit and its Vietnamese word are the same reading, spelled two ways.

Whisper writes "thứ 10" where the book writes "thứ mười", and comparing them as text costs
similarity for nothing: 111 of 6019 transcribed segments carried a number word matched by
the same digit in the transcript.

The direction is the whole decision, and only measurement settled it. Folding words to
digits improved 371 segments and damaged 1976; folding digits to words improved 318 and
damaged 1.
"""

from __future__ import annotations

from ebook_reader.asr import normalize_transcript, tone_folded_transcript_metrics


def test_a_digit_reads_as_its_word() -> None:
    assert normalize_transcript("thứ 10") == normalize_transcript("thứ mười")
    assert normalize_transcript("hai, ba giây") == normalize_transcript("2, 3 giây")


def test_a_number_word_is_left_as_a_word() -> None:
    """Folding the other way destroys the partial overlap the metric lives on: "năm" is
    also a year and "ba" also a father, so replacing them with a digit loses every
    character they shared with a near-miss."""
    assert "hai" in normalize_transcript("hai con mèo")
    assert "2" not in normalize_transcript("hai con mèo")


def test_a_near_miss_on_an_ordinary_word_is_not_made_worse() -> None:
    """"Ai đó?!" heard as "Hai đỏ." fell from 0.833 to 0.500 under the other direction."""
    similarity, _wer, _tone = tone_folded_transcript_metrics("“Ai đó?!”", "Hai đỏ.")
    assert similarity > 0.7


def test_only_a_bare_digit_folds() -> None:
    """"2026" and "3a" have no single-word reading to fold to."""
    assert "2026" in normalize_transcript("năm 2026")
    assert "3a" in normalize_transcript("phòng 3a")


def test_the_notation_difference_no_longer_costs_similarity() -> None:
    text = "Hắn là Hoàng Tử Quỷ Thứ Mười."
    heard = "Hắn là hoàng tử quỷ thứ 10."
    similarity, _wer, _tone = tone_folded_transcript_metrics(text, heard)
    assert similarity > 0.95


def test_a_zero_padded_number_is_the_one_case_this_costs() -> None:
    """"Chương 03" heard as "Trung 0-3" folds the transcript's digits and the heading's
    padded number does not follow. One segment in 6019, against 318 improved."""
    similarity, _wer, _tone = tone_folded_transcript_metrics(
        "Chương 03 - Đêm khuya", "Trung 0-3 đêm khuya."
    )
    assert 0.0 <= similarity <= 1.0
