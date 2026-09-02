"""An ASR verdict nobody can collect must not block a chapter.

Whisper needs something to transcribe. Measured over 4528 committed segments, a reference
under ten speakable characters gets a median similarity of 0.27 against 0.94 for a normal
sentence, and hallucinates a transcript three times too long 30% of the time - a rank label
"SSS" came back as a request to subscribe to a YouTube channel. The same engine produced
both sets of audio, so that is the verifier failing rather than the reading.
"""

from __future__ import annotations

import inspect
import json

from ebook_reader.asr import (
    ASR_MIN_VERIFIABLE_CHARS,
    ASR_TRANSCRIPT_TIMELINE_IMPOSSIBLE,
    ASR_UNVERIFIABLE_SHORT_TEXT,
    asr_answer_is_about_other_audio,
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


def test_a_frame_ceiling_is_evidence_short_text_cannot_excuse() -> None:
    """The generator reporting it ran out of frames means the take may be cut off, which is
    visible without transcribing a word."""
    check = BookPipeline._segment_has_non_asr_failure_evidence
    assert check(None, {"signal_json": json.dumps({"generation_ceiling_hit": 1.0})})
    assert check(None, {"signal_json": json.dumps({"generation_endpoint_active": 1.0})})


def test_a_clean_signal_leaves_only_the_asr_verdict() -> None:
    check = BookPipeline._segment_has_non_asr_failure_evidence
    clean = json.dumps({"duration": 1.04, "rms": 0.09, "generation_ceiling_hit": 0.0})
    assert not check(None, {"signal_json": clean})
    assert not check(None, {"signal_json": "{}"})


def test_unreadable_evidence_is_not_an_excuse() -> None:
    """A missing or corrupt signal must fail closed, not forgive."""
    check = BookPipeline._segment_has_non_asr_failure_evidence
    assert check(None, {"signal_json": "not json at all"})
    assert check(None, {"signal_json": json.dumps([1, 2, 3])})
    assert not check(None, {})  # no field at all decodes as an empty signal


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


def test_both_asr_failure_paths_know_the_rule() -> None:
    """The first-pass gate and the repair-exhaustion branch are separate code."""
    source = inspect.getsource(BookPipeline._verify_chapter_audio)
    assert source.count("asr_verdict_is_unverifiable") == 2, (
        "a segment ASR cannot judge must be forgiven wherever it is judged"
    )


def test_publishing_with_review_is_derived_from_the_verdict() -> None:
    """Naming branches instead means the next one added fails silently."""
    source = inspect.getsource(BookPipeline._verify_chapter_audio)
    assert "publish_with_review=(final_verdict == QUALITY_VERDICT_PASS)" in source
    assert "publish_with_review=locked_name_review" not in source


def test_perceptual_failure_still_outranks_unverifiable_text() -> None:
    """Naturalness scoring works fine on two syllables, so it keeps its say."""
    source = inspect.getsource(BookPipeline._verify_chapter_audio)
    assert "elif perceptual_review_exhausted:" in source
    assert source.index("elif perceptual_review_exhausted:") < source.index(
        "elif asr_only_failure"
    )


def test_a_transcript_about_other_audio_is_also_unanswerable() -> None:
    """Whisper's own timestamps ran past the end of the file, so it left the audio.

    "M\u1eb9 ki\u1ebfp! A a a! Kh\u1ed1n n\u1ea1n!" came back as "C\u1ea3m \u01a1n c\u00e1c b\u1ea1n \u0111\u00e3 theo d\u00f5i v\u00e0 h\u1eb9n g\u1eb7p l\u1ea1i"
    - the sign-off of a video, which is what the model was trained on - from two separately
    generated takes with different seeds. The reference is 18 characters, well above the
    short-text floor, so the existing branch could not reach it and the chapter stayed
    unpublished over evidence about Whisper rather than about the reading.
    """
    assert asr_answer_is_about_other_audio(ASR_TRANSCRIPT_TIMELINE_IMPOSSIBLE)
    assert not asr_answer_is_about_other_audio("ASR_MISMATCH_UNRESOLVED")
    assert not asr_answer_is_about_other_audio("")


def test_the_off_audio_warning_does_not_block_a_high_quality_chapter() -> None:
    from ebook_reader.pipeline import HIGH_QUALITY_ALLOWED_SEGMENT_WARNINGS

    assert ASR_TRANSCRIPT_TIMELINE_IMPOSSIBLE in HIGH_QUALITY_ALLOWED_SEGMENT_WARNINGS
