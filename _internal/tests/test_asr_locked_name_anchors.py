from __future__ import annotations

import json
from pathlib import Path

import pytest

from ebook_reader.asr import (
    ASR_INCONCLUSIVE,
    ASR_LOCKED_NAME_ANCHOR_MISMATCH,
    ASR_MISMATCH,
    ASR_PASS,
    LOCKED_NAME_ANCHOR_METRICS_KEY,
    adjudicate_locked_name_anchors,
)


def _asr_result(
    transcript: str,
    *,
    verdict: str = ASR_PASS,
    reason: str = "ok",
    repairable: bool = False,
) -> dict[str, object]:
    return {
        "passed": verdict == ASR_PASS,
        "verdict": verdict,
        "transcript": transcript,
        "similarity": 0.97,
        "wer": 0.04,
        "reason": reason,
        "repairable": repairable,
        "severe": False,
    }


def _anchor(
    surface: str,
    spoken_form: str,
    *,
    pronunciation_id: int = 7,
    occurrence_index: int = 0,
    spoken_start: int = 0,
    spoken_end: int | None = None,
) -> dict[str, object]:
    if spoken_end is None:
        spoken_end = spoken_start + len(spoken_form)
    return {
        "pronunciation_id": pronunciation_id,
        "surface": surface,
        "normalized_surface": surface.casefold(),
        "spoken_form": spoken_form,
        "source": "cmudict_vietnamese_transliteration",
        "occurrence_index": occurrence_index,
        "order": occurrence_index,
        "source_start": 4,
        "source_end": 4 + len(surface),
        "spoken_start": spoken_start,
        "spoken_end": spoken_end,
    }


def test_no_locked_name_anchors_leave_the_existing_result_unchanged() -> None:
    original = _asr_result("Một câu bình thường.")

    adjudicated = adjudicate_locked_name_anchors("Một câu bình thường.", original, [])

    assert adjudicated is original
    assert LOCKED_NAME_ANCHOR_METRICS_KEY not in original


@pytest.mark.parametrize(
    ("transcript", "matched_form"),
    [
        ("Anh Lu-si-en đã đến.", "spoken_form"),
        ("Anh Lucien đã đến.", "source_spelling"),
        ("Anh Lusien đã đến.", "joined_spoken_form"),
    ],
)
def test_locked_name_anchor_accepts_only_exact_supported_forms(
    transcript: str,
    matched_form: str,
) -> None:
    original = _asr_result(transcript)

    result = adjudicate_locked_name_anchors(
        "Anh Lu-si-en đã đến.",
        original,
        [_anchor("Lucien", "Lu-si-en", spoken_start=4)],
    )

    assert result["passed"] is True
    assert result["verdict"] == ASR_PASS
    metrics = result[LOCKED_NAME_ANCHOR_METRICS_KEY]
    assert isinstance(metrics, dict)
    assert metrics["status"] == "pass"
    assert metrics["matched_occurrence_count"] == 1
    assert metrics["anchors"][0]["matched_form"] == matched_form
    assert LOCKED_NAME_ANCHOR_METRICS_KEY not in original


@pytest.mark.parametrize(
    "wrong_name",
    [
        "Lucy",
        "Lucian",
        "Lusienne",
        "Lu-xi-en",
    ],
)
def test_locked_lucien_anchor_rejects_fuzzy_or_different_names(wrong_name: str) -> None:
    original = _asr_result(f"Anh {wrong_name} đã đến.")

    result = adjudicate_locked_name_anchors(
        "Anh Lu-si-en đã đến.",
        original,
        [_anchor("Lucien", "Lu-si-en", spoken_start=4)],
    )

    assert result["passed"] is False
    assert result["verdict"] == ASR_MISMATCH
    assert result["reason"] == ASR_LOCKED_NAME_ANCHOR_MISMATCH
    assert result["repairable"] is True
    assert result["similarity"] == original["similarity"]
    assert result["wer"] == original["wer"]
    assert original["passed"] is True
    assert original["verdict"] == ASR_PASS
    metrics = result[LOCKED_NAME_ANCHOR_METRICS_KEY]
    assert isinstance(metrics, dict)
    assert metrics["failure_codes"] == [ASR_LOCKED_NAME_ANCHOR_MISMATCH]
    assert metrics["matched_occurrence_count"] == 0
    assert metrics["anchors"][0]["status"] == "missing_or_wrong"


def test_anchor_alignment_does_not_hijack_a_later_ordinary_homograph() -> None:
    result = adjudicate_locked_name_anchors(
        "Mây may áo",
        _asr_result("Lucy may áo"),
        [_anchor("May", "Mây")],
    )

    assert result["passed"] is False
    assert result["reason"] == ASR_LOCKED_NAME_ANCHOR_MISMATCH
    metrics = result[LOCKED_NAME_ANCHOR_METRICS_KEY]
    assert isinstance(metrics, dict)
    assert metrics["ordinary_exact_match_count"] == 2
    assert metrics["anchors"][0]["aligned_tokens"] == ["lucy"]


@pytest.mark.parametrize("anchor_form", ["May", "Mây"])
def test_anchor_alignment_accepts_supported_form_in_its_expected_context(
    anchor_form: str,
) -> None:
    result = adjudicate_locked_name_anchors(
        "Mây may áo",
        _asr_result(f"{anchor_form} may áo"),
        [_anchor("May", "Mây")],
    )

    assert result["passed"] is True
    metrics = result[LOCKED_NAME_ANCHOR_METRICS_KEY]
    assert isinstance(metrics, dict)
    assert metrics["anchors"][0]["matched_token_start"] == 0


def test_anchor_alignment_tolerates_asr_insertions_before_the_correct_anchor() -> None:
    result = adjudicate_locked_name_anchors(
        "Mây may áo",
        _asr_result("ừ thì Mây may áo"),
        [_anchor("May", "Mây")],
    )

    assert result["passed"] is True
    metrics = result[LOCKED_NAME_ANCHOR_METRICS_KEY]
    assert isinstance(metrics, dict)
    assert metrics["alignment_edit_cost"] == 2
    assert metrics["anchors"][0]["matched_token_start"] == 2


def test_exact_spoken_span_binds_only_the_second_identical_occurrence() -> None:
    anchor = _anchor("May", "Mây", spoken_start=8)

    wrong_second_occurrence = adjudicate_locked_name_anchors(
        "Mây rồi Mây",
        _asr_result("Mây rồi Lucy"),
        [anchor],
    )
    correct_second_occurrence = adjudicate_locked_name_anchors(
        "Mây rồi Mây",
        _asr_result("Lucy rồi Mây"),
        [anchor],
    )

    assert wrong_second_occurrence["reason"] == ASR_LOCKED_NAME_ANCHOR_MISMATCH
    wrong_metrics = wrong_second_occurrence[LOCKED_NAME_ANCHOR_METRICS_KEY]
    assert isinstance(wrong_metrics, dict)
    assert wrong_metrics["ordinary_exact_match_count"] == 2
    assert wrong_metrics["anchors"][0]["aligned_tokens"] == ["lucy"]

    correct_metrics = correct_second_occurrence[LOCKED_NAME_ANCHOR_METRICS_KEY]
    assert isinstance(correct_metrics, dict)
    assert correct_metrics["passed"] is True
    assert correct_metrics["anchors"][0]["matched_token_start"] == 2


@pytest.mark.parametrize(
    ("spoken_start", "spoken_end", "validation_error"),
    [
        (None, 3, "missing_spoken_span"),
        (-1, 2, "invalid_spoken_span"),
        (4, 7, "spoken_span_text_mismatch"),
    ],
)
def test_anchor_adjudication_fails_closed_for_untrusted_spoken_spans(
    spoken_start: int | None,
    spoken_end: int,
    validation_error: str,
) -> None:
    anchor = _anchor("May", "Mây")
    anchor["spoken_start"] = spoken_start
    anchor["spoken_end"] = spoken_end

    result = adjudicate_locked_name_anchors(
        "Mây rồi Mây",
        _asr_result("Mây rồi Mây"),
        [anchor],
    )

    assert result["reason"] == ASR_LOCKED_NAME_ANCHOR_MISMATCH
    metrics = result[LOCKED_NAME_ANCHOR_METRICS_KEY]
    assert isinstance(metrics, dict)
    assert metrics["anchors"][0]["status"] == "invalid_expected_anchor_span"
    assert metrics["anchors"][0]["span_validation_error"] == validation_error


def test_passing_anchor_does_not_override_an_existing_asr_mismatch() -> None:
    original = _asr_result(
        "Lucien đã nói sai phần còn lại.",
        verdict=ASR_MISMATCH,
        reason="ASR_MISMATCH",
        repairable=True,
    )

    result = adjudicate_locked_name_anchors(
        "Lu-si-en đã nói đúng toàn bộ.",
        original,
        [_anchor("Lucien", "Lu-si-en")],
    )

    assert result["passed"] is False
    assert result["verdict"] == ASR_MISMATCH
    assert result["reason"] == "ASR_MISMATCH"
    metrics = result[LOCKED_NAME_ANCHOR_METRICS_KEY]
    assert isinstance(metrics, dict)
    assert metrics["status"] == "pass"


@pytest.mark.parametrize(
    "reason",
    [
        "ASR_TRANSCRIPT_TIMELINE_IMPOSSIBLE",
        "ASR_TRANSCRIPT_RATE_IMPOSSIBLE",
        "ASR_NOT_RUN",
        "ASR_ERROR",
        "short_skip",
    ],
)
def test_impossible_transcript_inconclusive_verdict_precedes_anchor_failure(reason: str) -> None:
    original = _asr_result(
        "Lucy",
        verdict=ASR_INCONCLUSIVE,
        reason=reason,
        repairable=False,
    )

    result = adjudicate_locked_name_anchors(
        "Lu-si-en",
        original,
        [_anchor("Lucien", "Lu-si-en")],
    )

    assert result["passed"] is False
    assert result["verdict"] == ASR_INCONCLUSIVE
    assert result["reason"] == reason
    assert result["repairable"] is False
    metrics = result[LOCKED_NAME_ANCHOR_METRICS_KEY]
    assert isinstance(metrics, dict)
    assert metrics["status"] == "skipped_inconclusive"
    assert metrics["adjudicated"] is False
    assert metrics["failure_codes"] == []


def test_locked_name_anchors_require_every_occurrence_in_monotonic_order() -> None:
    anchors = [
        _anchor("Lucien", "Lu-si-en", occurrence_index=0),
        _anchor(
            "Iven",
            "Ai-ven",
            pronunciation_id=8,
            occurrence_index=1,
            spoken_start=13,
        ),
        _anchor(
            "Lucien",
            "Lu-si-en",
            occurrence_index=2,
            spoken_start=28,
        ),
    ]
    expected = "Lu-si-en gặp Ai-ven rồi gọi Lu-si-en."

    passing = adjudicate_locked_name_anchors(
        expected,
        _asr_result("Lucien gặp Aiven rồi gọi Lusien."),
        anchors,
    )
    wrong_order = adjudicate_locked_name_anchors(
        expected,
        _asr_result("Iven gặp Lucien rồi gọi Lucien."),
        anchors,
    )
    missing_repeat = adjudicate_locked_name_anchors(
        expected,
        _asr_result("Lucien gặp Iven."),
        anchors,
    )

    assert passing["passed"] is True
    passing_metrics = passing[LOCKED_NAME_ANCHOR_METRICS_KEY]
    assert isinstance(passing_metrics, dict)
    assert passing_metrics["matched_occurrence_count"] == 3
    assert [item["matched_token_start"] for item in passing_metrics["anchors"]] == [0, 2, 5]
    assert wrong_order["reason"] == ASR_LOCKED_NAME_ANCHOR_MISMATCH
    assert missing_repeat["reason"] == ASR_LOCKED_NAME_ANCHOR_MISMATCH


def test_repeated_short_anchor_check_scales_required_occurrences() -> None:
    anchor = _anchor("Lucien", "Lu-si-en")

    passing = adjudicate_locked_name_anchors(
        "Lu-si-en!",
        _asr_result("Lucien Lu-si-en Lusien"),
        [anchor],
        repeat_count=3,
    )
    missing = adjudicate_locked_name_anchors(
        "Lu-si-en!",
        _asr_result("Lucien Lusien"),
        [anchor],
        repeat_count=3,
    )

    passing_metrics = passing[LOCKED_NAME_ANCHOR_METRICS_KEY]
    assert isinstance(passing_metrics, dict)
    assert passing["passed"] is True
    assert passing_metrics["required_occurrence_count"] == 3
    assert passing_metrics["matched_occurrence_count"] == 3
    assert [item["repeat_index"] for item in passing_metrics["anchors"]] == [0, 1, 2]
    assert missing["passed"] is False
    assert missing["reason"] == ASR_LOCKED_NAME_ANCHOR_MISMATCH


def test_anchor_evidence_preserves_extra_fields_as_json_safe_values() -> None:
    anchor = _anchor("Lucien", "Lu-si-en")
    anchor["review"] = {
        "artifact": Path("pronunciations.json"),
        "bounds": (4, 10),
        "score": float("inf"),
    }

    result = adjudicate_locked_name_anchors(
        "Lu-si-en",
        _asr_result("Lucien"),
        [anchor],
    )

    metrics = result[LOCKED_NAME_ANCHOR_METRICS_KEY]
    assert isinstance(metrics, dict)
    evidence = metrics["anchors"][0]
    assert evidence["pronunciation_id"] == 7
    assert evidence["review"] == {
        "artifact": "pronunciations.json",
        "bounds": [4, 10],
        "score": "inf",
    }
    json.dumps(metrics, ensure_ascii=False, allow_nan=False)


@pytest.mark.parametrize("repeat_count", [0, -1, True, 1.5])
def test_anchor_adjudication_rejects_invalid_repeat_count(repeat_count: object) -> None:
    with pytest.raises(ValueError, match="repeat_count must be a positive integer"):
        adjudicate_locked_name_anchors(
            "Lu-si-en",
            _asr_result("Lucien"),
            [_anchor("Lucien", "Lu-si-en")],
            repeat_count=repeat_count,  # type: ignore[arg-type]
        )
