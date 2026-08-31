"""An ASR verdict nobody can collect must not block a chapter.

Whisper needs something to transcribe. Measured over 4528 committed segments, a reference
under ten speakable characters gets a median similarity of 0.27 against 0.94 for a normal
sentence, and hallucinates a transcript three times too long 30% of the time - a rank label
"SSS" came back as a request to subscribe to a YouTube channel. The same engine produced
both sets of audio, so that is the verifier failing rather than the reading.
"""

from __future__ import annotations

import inspect

from ebook_reader.asr import ASR_MIN_VERIFIABLE_CHARS, asr_verdict_is_unverifiable
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


def test_only_asr_warnings_are_forgiven() -> None:
    """Everything that can still answer on two syllables keeps its power to block."""
    source = inspect.getsource(BookPipeline._high_quality_blocking_segment_warnings)
    assert 'code.startswith("ASR_")' in source
    assert "asr_verdict_is_unverifiable" in source


def test_a_long_segment_is_never_forgiven() -> None:
    """An inconclusive verdict on a full sentence means something odd happened."""
    long_text = "Anh ta bước qua hành lang rất dài và dừng lại trước cánh cửa bằng đồng."
    assert not asr_verdict_is_unverifiable(long_text)


def test_empty_text_is_unverifiable_rather_than_crashing() -> None:
    assert asr_verdict_is_unverifiable("")
    assert asr_verdict_is_unverifiable(None)
