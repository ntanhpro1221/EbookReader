"""An ASR verdict nobody can collect must not block a chapter.

Whisper needs something to transcribe. Measured over 4528 committed segments, a reference
under ten speakable characters gets a median similarity of 0.27 against 0.94 for a normal
sentence, and hallucinates a transcript three times too long 30% of the time - a rank label
"SSS" came back as a request to subscribe to a YouTube channel. The same engine produced
both sets of audio, so that is the verifier failing rather than the reading.
"""

from __future__ import annotations

import inspect

from ebook_reader.asr import (
    ASR_MIN_VERIFIABLE_CHARS,
    ASR_UNVERIFIABLE_SHORT_TEXT,
    asr_verdict_is_unverifiable,
)
from ebook_reader.pipeline import BookPipeline


def test_rank_labels_and_gasps_cannot_be_verified() -> None:
    for text in ("SS", "SSS", "C", "A", "Ha…", "•"):
        assert asr_verdict_is_unverifiable(text), text


def test_real_sentences_stay_verifiable_even_when_short() -> None:
    for text in (
        "Thôi được rồi",
        "• Spirit Realm (Linh Giới):",
        "Rare (Hiếm - B): Mạnh hơn / khó tìm hơn.",
    ):
        assert not asr_verdict_is_unverifiable(text), text


def test_only_speakable_characters_count_toward_the_threshold() -> None:
    """Punctuation is not something Whisper can hear."""
    assert asr_verdict_is_unverifiable("...!?-()[]{}...")
    assert asr_verdict_is_unverifiable("a, b. c! d?")


def test_the_threshold_sits_at_the_measured_cliff() -> None:
    """Failure rates: 13.9% below 0.5 at 6-10 chars, 3.8% at 10-16."""
    assert ASR_MIN_VERIFIABLE_CHARS == 10


def test_the_segment_is_verified_with_a_warning_not_failed() -> None:
    """A failed segment blocks its chapter on status alone, whatever the warning says."""
    source = inspect.getsource(BookPipeline._verify_chapter_audio)
    branch = source[source.index("asr_verdict_is_unverifiable") :]
    branch = branch[: branch.index("warning = (")]
    assert "mark_verified" in branch
    assert "mark_failed" not in branch
    assert "QUALITY_VERDICT_PASS" in branch


def test_the_warning_does_not_block_a_high_quality_chapter() -> None:
    """Otherwise the segment publishes and the chapter still refuses it."""
    from ebook_reader.pipeline import HIGH_QUALITY_ALLOWED_SEGMENT_WARNINGS

    assert ASR_UNVERIFIABLE_SHORT_TEXT in HIGH_QUALITY_ALLOWED_SEGMENT_WARNINGS


def test_the_decision_lives_in_exactly_one_place() -> None:
    """The chapter-level gate must not re-implement the same judgement."""
    source = inspect.getsource(BookPipeline._high_quality_blocking_segment_warnings)
    assert "asr_verdict_is_unverifiable" not in source


def test_other_warnings_still_block() -> None:
    from ebook_reader.pipeline import HIGH_QUALITY_ALLOWED_SEGMENT_WARNINGS

    for code in ("ASR_SEVERE_MISMATCH", "ASR_MISMATCH_UNRESOLVED", "SEGMENT_FAILED"):
        assert code not in HIGH_QUALITY_ALLOWED_SEGMENT_WARNINGS


def test_a_long_segment_is_never_forgiven() -> None:
    """An inconclusive verdict on a full sentence means something odd happened."""
    long_text = "Anh ta bước qua hành lang rất dài và dừng lại trước cánh cửa bằng đồng."
    assert not asr_verdict_is_unverifiable(long_text)


def test_empty_text_is_unverifiable_rather_than_crashing() -> None:
    assert asr_verdict_is_unverifiable("")
    assert asr_verdict_is_unverifiable(None)
