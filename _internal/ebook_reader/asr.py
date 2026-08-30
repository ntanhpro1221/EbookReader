from __future__ import annotations

import gc
import math
import re
import unicodedata
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Callable

import numpy as np
import soundfile as sf
from scipy.signal import resample_poly

from .asr_contract import (
    ASR_LOCKED_NAME_ANCHOR_REVIEW,
    COLLAPSED_SHORT_CONTEXT_EFFECTIVE_REPEAT_COUNT,
    LOCKED_NAME_ANCHOR_METRICS_VERSION,
    SHORT_CONTEXT_REPEAT_COUNT,
)
from .resource_manager import trim_process_working_set
from .text_processing import is_vocalization_only


ASR_REPAIR_MIN_WORDS = 1
SEVERE_MISMATCH_MAX_SIMILARITY = 0.35
SEVERE_MISMATCH_MIN_LENGTH_RATIO = 3.0
SEVERE_MISMATCH_MIN_EXTRA_WORDS = 4
WHISPER_SAMPLE_RATE = 16_000
MAX_PLAUSIBLE_TRANSCRIPT_WORDS_PER_SECOND = 5.0
TRANSCRIPT_WORD_MARGIN = 2
MIN_PLAUSIBLE_TRANSCRIPT_WORDS = 4
WHISPER_TIMELINE_ABSOLUTE_MARGIN_SECONDS = 1.0
WHISPER_TIMELINE_DURATION_FACTOR = 2.0
SHORT_CONTEXT_MAX_WORDS = 5
SHORT_CONTEXT_GAP_SECONDS = 0.50
ASR_PASS = "pass"
ASR_MISMATCH = "mismatch"
ASR_INCONCLUSIVE = "inconclusive"
ASR_LOCKED_NAME_ANCHOR_MISMATCH = "ASR_LOCKED_NAME_ANCHOR_MISMATCH"
ASR_LOCKED_NAME_CANONICAL_PASS = "ASR_LOCKED_NAME_CANONICAL_PASS"
LOCKED_NAME_ANCHOR_METRICS_KEY = "locked_name_anchor_metrics"
ASR_WER_SIMILARITY_MARGIN = 0.12
ANCHOR_COMPARISON_NORMALIZED_EXACT = "normalized_exact"
ANCHOR_COMPARISON_DIACRITIC_FOLDED_EXACT = "diacritic_folded_exact"
ANCHOR_COMPARISON_VIETNAMESE_PHONEME_EXACT = "vietnamese_phoneme_exact"
# Canonicalising an unmatched anchor removes it from the sentence metrics so the same
# disagreement is not punished twice. That is only sound while enough ordinary content
# remains to carry an independent verdict: in "Anh Lucy" the name is half the utterance,
# so waiving it would leave nothing to check. Below this many ordinary expected tokens
# the anchor keeps its hard-fail authority.
CANONICAL_ANCHOR_WAIVER_MIN_ORDINARY_TOKENS = 4
_PHONEME_CACHE: dict[str, str] = {}
_PHONEMIZER: list[Any] = []


def _vietnamese_phonemes(token: str) -> str:
    """Deterministic phonemes for one token, or "" when phonemisation is unavailable.

    Vietnamese orthography spells the same sound more than one way - `gi` and `d` are
    both /z/, so a correct "Giôn" and Whisper's "dôn" are the same utterance. Comparing
    phonemes recognises exactly those spellings and nothing looser: this stays an
    equality test, so "Lucy" still cannot satisfy an anchor locked to "Lucien".
    """
    if not token:
        return ""
    cached = _PHONEME_CACHE.get(token)
    if cached is not None:
        return cached
    if not _PHONEMIZER:
        try:
            from sea_g2p import G2P

            _PHONEMIZER.append(G2P(lang="vi"))
        except Exception:  # noqa: BLE001
            _PHONEMIZER.append(None)
    engine = _PHONEMIZER[0]
    if engine is None:
        return ""
    try:
        phonemes = str(engine.convert(token)).strip()
    except Exception:  # noqa: BLE001
        phonemes = ""
    _PHONEME_CACHE[token] = phonemes
    return phonemes


def normalize_transcript(text: str) -> str:
    text = text.casefold().replace("đ", "d")
    text = re.sub(r"[^0-9a-zà-ỹ\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _json_safe_anchor_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else str(value)
    if isinstance(value, Mapping):
        return {str(key): _json_safe_anchor_value(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_json_safe_anchor_value(item) for item in value]
    return str(value)


def _diacritic_folded_token(token: str) -> str:
    return "".join(
        character
        for character in unicodedata.normalize("NFD", token)
        if unicodedata.category(character) != "Mn"
    )


def _locked_name_anchor_forms(
    anchor: Mapping[str, Any],
) -> list[tuple[str, tuple[str, ...], str]]:
    spoken_tokens = tuple(normalize_transcript(str(anchor.get("spoken_form", ""))).split())
    surface = str(anchor.get("surface", "")).strip()
    if not surface:
        surface = str(anchor.get("normalized_surface", "")).strip()
    surface_tokens = tuple(normalize_transcript(surface).split())
    folded_spoken_tokens = tuple(
        _diacritic_folded_token(token)
        for token in spoken_tokens
    )
    phoneme_spoken_tokens = tuple(_vietnamese_phonemes(token) for token in spoken_tokens)
    if not all(phoneme_spoken_tokens):
        phoneme_spoken_tokens = ()
    candidates = [
        ("spoken_form", spoken_tokens, ANCHOR_COMPARISON_NORMALIZED_EXACT),
        ("source_spelling", surface_tokens, ANCHOR_COMPARISON_NORMALIZED_EXACT),
        (
            "joined_spoken_form",
            ("".join(spoken_tokens),) if spoken_tokens else (),
            ANCHOR_COMPARISON_NORMALIZED_EXACT,
        ),
        (
            "spoken_form",
            folded_spoken_tokens,
            ANCHOR_COMPARISON_DIACRITIC_FOLDED_EXACT,
        ),
        (
            "joined_spoken_form",
            ("".join(folded_spoken_tokens),) if folded_spoken_tokens else (),
            ANCHOR_COMPARISON_DIACRITIC_FOLDED_EXACT,
        ),
        (
            "spoken_form",
            phoneme_spoken_tokens,
            ANCHOR_COMPARISON_VIETNAMESE_PHONEME_EXACT,
        ),
    ]
    forms: list[tuple[str, tuple[str, ...], str]] = []
    seen: set[tuple[tuple[str, ...], str]] = set()
    for kind, tokens, comparison_mode in candidates:
        key = (tokens, comparison_mode)
        if not tokens or key in seen:
            continue
        forms.append((kind, tokens, comparison_mode))
        seen.add(key)
    return forms


def _locked_name_anchor_token_span(
    expected_spoken_text: str,
    expected_tokens: list[str],
    anchor: Mapping[str, Any],
) -> tuple[int, int] | str:
    spoken_start = anchor.get("spoken_start")
    spoken_end = anchor.get("spoken_end")
    if spoken_start is None or spoken_end is None:
        return "missing_spoken_span"
    if (
        isinstance(spoken_start, bool)
        or not isinstance(spoken_start, int)
        or isinstance(spoken_end, bool)
        or not isinstance(spoken_end, int)
        or spoken_start < 0
        or spoken_end <= spoken_start
        or spoken_end > len(expected_spoken_text)
    ):
        return "invalid_spoken_span"

    normalized_spoken_form = normalize_transcript(
        str(anchor.get("spoken_form", ""))
    )
    normalized_span = normalize_transcript(
        expected_spoken_text[spoken_start:spoken_end]
    )
    if not normalized_spoken_form or normalized_span != normalized_spoken_form:
        return "spoken_span_text_mismatch"

    prefix_tokens = normalize_transcript(expected_spoken_text[:spoken_start]).split()
    span_tokens = normalized_span.split()
    suffix_tokens = normalize_transcript(expected_spoken_text[spoken_end:]).split()
    if prefix_tokens + span_tokens + suffix_tokens != expected_tokens:
        return "spoken_span_token_boundary_mismatch"
    return len(prefix_tokens), len(prefix_tokens) + len(span_tokens)


def _build_locked_name_alignment_units(
    expected_spoken_text: str,
    anchors: list[dict[str, Any]],
    repeat_count: int,
) -> tuple[list[dict[str, Any]], dict[tuple[int, int], str]]:
    expected_tokens = normalize_transcript(expected_spoken_text).split()
    base_units: list[dict[str, Any]] = []
    invalid_anchor_indexes: dict[int, str] = {}
    cursor = 0
    for anchor_index, anchor in enumerate(anchors):
        token_span = _locked_name_anchor_token_span(
            expected_spoken_text,
            expected_tokens,
            anchor,
        )
        if isinstance(token_span, str):
            invalid_anchor_indexes[anchor_index] = token_span
            continue
        anchor_start, anchor_end = token_span
        if anchor_start < cursor:
            invalid_anchor_indexes[anchor_index] = "spoken_span_order_invalid"
            continue
        base_units.extend(
            {"kind": "token", "token": token}
            for token in expected_tokens[cursor:anchor_start]
        )
        base_units.append(
            {
                "kind": "anchor",
                "anchor_index": anchor_index,
                "forms": _locked_name_anchor_forms(anchor),
            }
        )
        cursor = anchor_end
    base_units.extend(
        {"kind": "token", "token": token}
        for token in expected_tokens[cursor:]
    )

    units: list[dict[str, Any]] = []
    invalid_occurrences: dict[tuple[int, int], str] = {}
    for repeat_index in range(repeat_count):
        for unit in base_units:
            repeated_unit = dict(unit)
            if repeated_unit["kind"] == "anchor":
                repeated_unit["repeat_index"] = repeat_index
            units.append(repeated_unit)
        invalid_occurrences.update(
            {
                (repeat_index, anchor_index): reason
                for anchor_index, reason in invalid_anchor_indexes.items()
            }
        )
    return units, invalid_occurrences


def _minimum_cost_locked_name_alignment(
    units: list[dict[str, Any]],
    transcript_tokens: list[str],
) -> tuple[tuple[int, int, int, int], list[dict[str, Any]]]:
    """Align semantic expected units to tokens while preserving ordinary context.

    Score fields are edit cost, negative ordinary exact matches, negative exact
    anchor matches, and structural edit count. Ordinary exact matches deliberately
    precede anchor matches in the tie-break: an accepted anchor spelling cannot
    steal a later homograph that belongs to ordinary sentence context.
    """

    score_by_state: dict[tuple[int, int], tuple[int, int, int, int]] = {
        (0, 0): (0, 0, 0, 0)
    }
    predecessor: dict[
        tuple[int, int],
        tuple[tuple[int, int], dict[str, Any]],
    ] = {}

    def update(
        state: tuple[int, int],
        next_state: tuple[int, int],
        delta: tuple[int, int, int, int],
        operation: dict[str, Any],
    ) -> None:
        current = score_by_state[state]
        candidate = tuple(left + right for left, right in zip(current, delta))
        existing = score_by_state.get(next_state)
        if existing is not None and existing <= candidate:
            return
        score_by_state[next_state] = candidate
        predecessor[next_state] = (state, operation)

    for unit_index in range(len(units) + 1):
        for transcript_index in range(len(transcript_tokens) + 1):
            state = (unit_index, transcript_index)
            if state not in score_by_state:
                continue
            if transcript_index < len(transcript_tokens):
                update(
                    state,
                    (unit_index, transcript_index + 1),
                    (1, 0, 0, 1),
                    {"kind": "insert_transcript"},
                )
            if unit_index >= len(units):
                continue

            unit = units[unit_index]
            if unit["kind"] == "token":
                update(
                    state,
                    (unit_index + 1, transcript_index),
                    (1, 0, 0, 1),
                    {"kind": "delete_token"},
                )
                if transcript_index < len(transcript_tokens):
                    exact = unit["token"] == transcript_tokens[transcript_index]
                    update(
                        state,
                        (unit_index + 1, transcript_index + 1),
                        (0, -1, 0, 0) if exact else (1, 0, 0, 0),
                        {"kind": "match_token" if exact else "substitute_token"},
                    )
                continue

            anchor_operation = {
                "anchor_index": unit["anchor_index"],
                "repeat_index": unit["repeat_index"],
            }
            update(
                state,
                (unit_index + 1, transcript_index),
                (1, 0, 0, 1),
                {
                    **anchor_operation,
                    "kind": "delete_anchor",
                    "token_start": transcript_index,
                    "token_end": transcript_index,
                },
            )
            if transcript_index < len(transcript_tokens):
                update(
                    state,
                    (unit_index + 1, transcript_index + 1),
                    (1, 0, 0, 0),
                    {
                        **anchor_operation,
                        "kind": "substitute_anchor",
                        "token_start": transcript_index,
                        "token_end": transcript_index + 1,
                    },
                )
            for form_kind, form_tokens, comparison_mode in unit["forms"]:
                form_end = transcript_index + len(form_tokens)
                matched_tokens = tuple(transcript_tokens[transcript_index:form_end])
                if comparison_mode == ANCHOR_COMPARISON_DIACRITIC_FOLDED_EXACT:
                    comparison_tokens = tuple(
                        _diacritic_folded_token(token) for token in matched_tokens
                    )
                elif comparison_mode == ANCHOR_COMPARISON_VIETNAMESE_PHONEME_EXACT:
                    comparison_tokens = tuple(
                        _vietnamese_phonemes(token) for token in matched_tokens
                    )
                    if not all(comparison_tokens):
                        continue
                else:
                    comparison_tokens = matched_tokens
                if comparison_tokens != form_tokens:
                    continue
                update(
                    state,
                    (unit_index + 1, form_end),
                    (0, 0, -1, 0),
                    {
                        **anchor_operation,
                        "kind": "match_anchor",
                        "form_kind": form_kind,
                        "comparison_mode": comparison_mode,
                        "form_tokens": form_tokens,
                        "matched_tokens": matched_tokens,
                        "token_start": transcript_index,
                        "token_end": form_end,
                    },
                )

    final_state = (len(units), len(transcript_tokens))
    operations: list[dict[str, Any]] = []
    state = final_state
    while state != (0, 0):
        previous_state, operation = predecessor[state]
        operations.append(operation)
        state = previous_state
    operations.reverse()
    return score_by_state[final_state], operations


def _semantic_anchor_token(
    repeat_index: int,
    anchor_index: int,
    anchor_count: int,
) -> str:
    ordinal = repeat_index * anchor_count + anchor_index
    if ordinal >= 65_534:
        raise ValueError("Too many locked-name anchor occurrences")
    return chr(0xF0000 + ordinal)


def _canonical_locked_name_metrics(
    units: list[dict[str, Any]],
    operations: list[dict[str, Any]],
    transcript_tokens: list[str],
    anchor_count: int,
) -> tuple[float, float, float]:
    expected_tokens = [
        _semantic_anchor_token(
            int(unit["repeat_index"]),
            int(unit["anchor_index"]),
            anchor_count,
        )
        if unit["kind"] == "anchor"
        else str(unit["token"])
        for unit in units
    ]
    actual_tokens: list[str] = []
    transcript_cursor = 0
    for operation in operations:
        kind = str(operation["kind"])
        if kind in {"insert_transcript", "match_token", "substitute_token"}:
            actual_tokens.append(transcript_tokens[transcript_cursor])
            transcript_cursor += 1
        elif kind == "match_anchor":
            actual_tokens.append(
                _semantic_anchor_token(
                    int(operation["repeat_index"]),
                    int(operation["anchor_index"]),
                    anchor_count,
                )
            )
            transcript_cursor += len(operation["matched_tokens"])
        elif kind == "substitute_anchor":
            # A name the transcript rendered differently is adjudicated by the anchor
            # evidence, which reports it for review. Letting it also count as an
            # ordinary substitution here would punish the same disagreement twice and
            # push short sentences past the WER gate on their names alone. A name the
            # transcript dropped entirely stays a `delete_anchor` and still counts.
            actual_tokens.append(
                _semantic_anchor_token(
                    int(operation["repeat_index"]),
                    int(operation["anchor_index"]),
                    anchor_count,
                )
            )
            transcript_cursor += 1
    if transcript_cursor != len(transcript_tokens):
        raise RuntimeError("Locked-name canonical alignment did not consume transcript")

    expected_characters = list(" ".join(expected_tokens))
    actual_characters = list(" ".join(actual_tokens))
    character_error_rate = _edit_distance(
        expected_characters,
        actual_characters,
    ) / max(1, len(expected_characters))
    similarity = max(0.0, 1.0 - character_error_rate)
    word_error_rate = _edit_distance(
        expected_tokens,
        actual_tokens,
    ) / max(1, len(expected_tokens))
    return float(similarity), float(character_error_rate), float(word_error_rate)


def _passes_asr_content_thresholds(
    transcript_present: bool,
    similarity: float,
    wer: float,
    *,
    min_similarity: float,
    max_wer: float,
) -> bool:
    return transcript_present and not (
        similarity < min_similarity
        or (wer > max_wer and similarity < min_similarity + ASR_WER_SIMILARITY_MARGIN)
    )


def adjudicate_locked_name_anchors(
    expected_spoken_text: str,
    asr_result: dict[str, Any],
    anchors: Sequence[Mapping[str, Any]],
    repeat_count: int = 1,
    *,
    min_similarity: float | None = None,
    max_wer: float | None = None,
) -> dict[str, Any]:
    """Require exact locked-name forms in an ASR transcript without fuzzy aliases.

    Every anchor carries an end-exclusive character span into the exact
    ``expected_spoken_text``. Repeated-short ASR must pass the complete aligned
    sequence for every repeated copy, so callers pass its audio repeat count
    through ``repeat_count``.
    """

    if not anchors:
        return asr_result
    if isinstance(repeat_count, bool) or not isinstance(repeat_count, int) or repeat_count < 1:
        raise ValueError("repeat_count must be a positive integer")

    result = dict(asr_result)
    normalized_transcript = normalize_transcript(str(result.get("transcript", "")))
    transcript_tokens = normalized_transcript.split()
    normalized_expected = normalize_transcript(expected_spoken_text)
    safe_anchors = [
        {
            str(key): _json_safe_anchor_value(value)
            for key, value in anchor.items()
        }
        for anchor in anchors
    ]
    required_occurrence_count = len(safe_anchors) * repeat_count
    precedence_inconclusive = result.get("verdict") == ASR_INCONCLUSIVE
    evidence: list[dict[str, Any]] = []

    if precedence_inconclusive:
        for repeat_index in range(repeat_count):
            for anchor_index, anchor in enumerate(safe_anchors):
                evidence.append(
                    {
                        **anchor,
                        "repeat_index": repeat_index,
                        "required_order": len(evidence),
                        "anchor_index": anchor_index,
                        "status": "skipped_inconclusive",
                        "matched": False,
                    }
                )
        result[LOCKED_NAME_ANCHOR_METRICS_KEY] = {
            "version": LOCKED_NAME_ANCHOR_METRICS_VERSION,
            "status": "skipped_inconclusive",
            "adjudicated": False,
            "passed": None,
            "failure_codes": [],
            "repeat_count": repeat_count,
            "anchor_count": len(safe_anchors),
            "required_occurrence_count": required_occurrence_count,
            "matched_occurrence_count": 0,
            "expected_token_count": len(normalized_expected.split()),
            "transcript_token_count": len(transcript_tokens),
            "anchors": evidence,
        }
        return result

    units, invalid_occurrences = _build_locked_name_alignment_units(
        expected_spoken_text,
        safe_anchors,
        repeat_count,
    )
    alignment_score, operations = _minimum_cost_locked_name_alignment(
        units,
        transcript_tokens,
    )
    anchor_operations = {
        (operation["repeat_index"], operation["anchor_index"]): operation
        for operation in operations
        if operation["kind"]
        in {"match_anchor", "substitute_anchor", "delete_anchor"}
    }
    matched_occurrence_count = 0
    for repeat_index in range(repeat_count):
        for anchor_index, anchor in enumerate(safe_anchors):
            forms = _locked_name_anchor_forms(anchor)
            occurrence = (repeat_index, anchor_index)
            operation = anchor_operations.get(occurrence)
            anchor_evidence = {
                **anchor,
                "repeat_index": repeat_index,
                "required_order": len(evidence),
                "anchor_index": anchor_index,
                "accepted_forms": [
                    {
                        "kind": kind,
                        "tokens": list(tokens),
                        "comparison_mode": comparison_mode,
                    }
                    for kind, tokens, comparison_mode in forms
                ],
            }
            if occurrence in invalid_occurrences:
                anchor_evidence.update(
                    {
                        "status": "invalid_expected_anchor_span",
                        "matched": False,
                        "span_validation_error": invalid_occurrences[occurrence],
                    }
                )
            elif operation is not None and operation["kind"] == "match_anchor":
                matched_occurrence_count += 1
                anchor_evidence.update(
                    {
                        "status": "matched",
                        "matched": True,
                        "matched_form": operation["form_kind"],
                        "matched_comparison_mode": operation["comparison_mode"],
                        "matched_tokens": list(operation["matched_tokens"]),
                        "matched_token_start": operation["token_start"],
                        "matched_token_end": operation["token_end"],
                    }
                )
            else:
                anchor_evidence.update(
                    {
                        "status": "missing_or_wrong",
                        "matched": False,
                    }
                )
                if operation is not None:
                    token_start = operation["token_start"]
                    token_end = operation["token_end"]
                    anchor_evidence.update(
                        {
                            "alignment_operation": operation["kind"],
                            "aligned_token_start": token_start,
                            "aligned_token_end": token_end,
                            "aligned_tokens": transcript_tokens[token_start:token_end],
                        }
                    )
            evidence.append(anchor_evidence)

    anchors_passed = matched_occurrence_count == required_occurrence_count
    canonical_similarity: float | None = None
    canonical_cer: float | None = None
    canonical_wer: float | None = None
    canonical_threshold_passed: bool | None = None
    canonical_promoted = False
    canonical_demoted = False
    canonical_similarity, canonical_cer, canonical_wer = _canonical_locked_name_metrics(
        units,
        operations,
        transcript_tokens,
        len(safe_anchors),
    )
    ordinary_expected_tokens = sum(1 for unit in units if unit["kind"] != "anchor")
    canonical_waiver_available = (
        ordinary_expected_tokens >= CANONICAL_ANCHOR_WAIVER_MIN_ORDINARY_TOKENS
    )
    if min_similarity is not None and max_wer is not None and (
        anchors_passed or canonical_waiver_available
    ):
        canonical_threshold_passed = _passes_asr_content_thresholds(
            bool(transcript_tokens),
            canonical_similarity,
            canonical_wer,
            min_similarity=float(min_similarity),
            max_wer=float(max_wer),
        )
        if anchors_passed:
            canonical_promoted = bool(
                canonical_threshold_passed
                and result.get("verdict") == ASR_MISMATCH
                and result.get("reason") == "ASR_MISMATCH"
            )
            canonical_demoted = bool(
                not canonical_threshold_passed
                and result.get("verdict") == ASR_PASS
            )

    result[LOCKED_NAME_ANCHOR_METRICS_KEY] = {
        "version": LOCKED_NAME_ANCHOR_METRICS_VERSION,
        "status": (
            "pass"
            if anchors_passed
            else ("review_eligible" if canonical_threshold_passed else "fail")
        ),
        "adjudicated": True,
        "passed": anchors_passed,
        "failure_codes": [] if anchors_passed else [ASR_LOCKED_NAME_ANCHOR_MISMATCH],
        "review_codes": (
            [ASR_LOCKED_NAME_ANCHOR_REVIEW]
            if not anchors_passed and canonical_threshold_passed
            else []
        ),
        "repeat_count": repeat_count,
        "anchor_count": len(safe_anchors),
        "required_occurrence_count": required_occurrence_count,
        "matched_occurrence_count": matched_occurrence_count,
        "expected_token_count": len(normalized_expected.split()),
        "transcript_token_count": len(transcript_tokens),
        "alignment_edit_cost": alignment_score[0],
        "ordinary_exact_match_count": -alignment_score[1],
        "raw_similarity": result.get("similarity"),
        "raw_wer": result.get("wer"),
        "canonical_similarity": canonical_similarity,
        "canonical_cer": canonical_cer,
        "canonical_wer": canonical_wer,
        "canonical_min_similarity": min_similarity,
        "canonical_max_wer": max_wer,
        "canonical_threshold_passed": canonical_threshold_passed,
        "ordinary_expected_token_count": ordinary_expected_tokens,
        "canonical_waiver_available": canonical_waiver_available,
        "canonical_promoted": canonical_promoted,
        "canonical_demoted": canonical_demoted,
        "anchors": evidence,
    }
    if anchors_passed:
        if canonical_promoted:
            result.update(
                {
                    "passed": True,
                    "verdict": ASR_PASS,
                    "reason": ASR_LOCKED_NAME_CANONICAL_PASS,
                    "repairable": False,
                    "severe": False,
                }
            )
        elif canonical_demoted:
            result.update(
                {
                    "passed": False,
                    "verdict": ASR_MISMATCH,
                    "reason": "ASR_MISMATCH",
                    "repairable": True,
                    "severe": False,
                }
            )
        return result

    # Anchors failed. Whisper's spelling for a foreign name read with Vietnamese
    # phonemes is not evidence about pronunciation, so the anchor reports review
    # evidence rather than failing the segment; the canonical sentence metrics, which
    # exclude the name spans, keep the hard-fail authority. Repair is not offered for
    # an anchor-only disagreement: the cause is the transcript's orthography, not the
    # audio, and re-generating cannot change it.
    if canonical_threshold_passed is None:
        # Either the caller did not opt into canonical gating, or the utterance is too
        # short for waiving the name to leave anything worth checking. Keep the strict
        # historical behaviour rather than letting an unmatched anchor through.
        result.update(
            {
                "locked_name_review_eligible": False,
                "passed": False,
                "verdict": ASR_MISMATCH,
                "reason": ASR_LOCKED_NAME_ANCHOR_MISMATCH,
                "repairable": True,
            }
        )
        return result
    # Repair still runs: a regenerated take may genuinely pronounce the name better,
    # and that chance is worth the attempts. What changes is the terminal state. When
    # the budget is exhausted and the canonical sentence metrics - which exclude the
    # name spans - are acceptable, the pipeline publishes the segment with review
    # evidence instead of failing it, because Whisper's spelling is not proof of
    # mispronunciation. `locked_name_review_eligible` carries that decision.
    result["locked_name_review_eligible"] = bool(canonical_threshold_passed)
    # The reason stays the anchor mismatch in both cases so the failure evidence remains
    # self-consistent for the candidate ledger, which requires reason, failure codes and
    # anchor status to agree. Whether the sentence content was independently acceptable
    # is carried by `locked_name_review_eligible`, and only the pipeline's exhaustion
    # handling reads it.
    result.update(
        {
            "passed": False,
            "verdict": ASR_MISMATCH,
            "reason": ASR_LOCKED_NAME_ANCHOR_MISMATCH,
            "repairable": True,
            "severe": False,
        }
    )
    return result


def adjudicate_collapsed_repeated_short(
    expected_spoken_text: str,
    asr_result: dict[str, Any],
    anchors: Sequence[Mapping[str, Any]],
    *,
    requested_repeat_count: int,
    min_similarity: float,
    max_wer: float,
) -> dict[str, Any] | None:
    """Re-adjudicate a decoder-collapsed repeat as one exact spoken copy.

    Whisper can collapse identical short-context repetitions into one transcript.
    This path remains limited to locked-name evidence and preserves both the
    requested and effective repeat counts in the durable adjudication metrics.
    """

    if requested_repeat_count != SHORT_CONTEXT_REPEAT_COUNT or isinstance(
        requested_repeat_count,
        bool,
    ):
        raise ValueError(
            "requested_repeat_count must match the repeated-short decode contract"
        )
    if not anchors:
        return None
    if LOCKED_NAME_ANCHOR_METRICS_KEY in asr_result:
        raise RuntimeError("collapsed repeated-short adjudication requires raw ASR evidence")
    transcript = asr_result.get("transcript")
    raw_evidence_is_eligible = (
        asr_result.get("verdict") == ASR_MISMATCH
        and asr_result.get("passed") is False
        and asr_result.get("reason") == "ASR_MISMATCH"
        and isinstance(transcript, str)
        and bool(transcript.strip())
    )
    if not raw_evidence_is_eligible:
        return None

    similarity, wer = transcript_metrics(expected_spoken_text, transcript)
    content_passed = _passes_asr_content_thresholds(
        True,
        similarity,
        wer,
        min_similarity=min_similarity,
        max_wer=max_wer,
    )
    rescored_result = {
        "passed": content_passed,
        "verdict": ASR_PASS if content_passed else ASR_MISMATCH,
        "transcript": transcript,
        "similarity": similarity,
        "wer": wer,
        "reason": "ok" if content_passed else "ASR_MISMATCH",
        "repairable": is_asr_repair_candidate(expected_spoken_text),
        "severe": not content_passed
        and is_severe_asr_mismatch(expected_spoken_text, transcript, similarity),
    }

    collapsed = adjudicate_locked_name_anchors(
        expected_spoken_text,
        rescored_result,
        anchors,
        repeat_count=1,
        min_similarity=min_similarity,
        max_wer=max_wer,
    )
    anchor_metrics = collapsed.get(LOCKED_NAME_ANCHOR_METRICS_KEY)
    if not isinstance(anchor_metrics, dict) or anchor_metrics.get("adjudicated") is not True:
        raise RuntimeError("collapsed repeated-short anchor evidence is incomplete")

    result = dict(collapsed)
    result[LOCKED_NAME_ANCHOR_METRICS_KEY] = {
        **anchor_metrics,
        "requested_repeat_count": requested_repeat_count,
        "effective_repeat_count": COLLAPSED_SHORT_CONTEXT_EFFECTIVE_REPEAT_COUNT,
    }
    result["requested_repeat_count"] = requested_repeat_count
    result["effective_repeat_count"] = (
        COLLAPSED_SHORT_CONTEXT_EFFECTIVE_REPEAT_COUNT
    )
    return result


def _edit_distance(left: list[str], right: list[str]) -> int:
    if len(left) < len(right):
        left, right = right, left
    previous = list(range(len(right) + 1))
    for i, token_left in enumerate(left, 1):
        current = [i]
        for j, token_right in enumerate(right, 1):
            current.append(
                min(
                    current[-1] + 1,
                    previous[j] + 1,
                    previous[j - 1] + (token_left != token_right),
                )
            )
        previous = current
    return previous[-1]


def transcript_metrics(expected: str, actual: str) -> tuple[float, float]:
    normalized_expected = normalize_transcript(expected)
    normalized_actual = normalize_transcript(actual)
    expected_characters = list(normalized_expected)
    actual_characters = list(normalized_actual)
    character_errors = _edit_distance(expected_characters, actual_characters)
    similarity = max(0.0, 1.0 - character_errors / max(1, len(expected_characters)))
    expected_words = normalized_expected.split()
    actual_words = normalized_actual.split()
    wer = _edit_distance(expected_words, actual_words) / max(1, len(expected_words))
    return float(similarity), float(wer)


def is_asr_repair_candidate(expected: str) -> bool:
    return len(normalize_transcript(expected).split()) >= ASR_REPAIR_MIN_WORDS


def is_severe_asr_mismatch(expected: str, actual: str, similarity: float) -> bool:
    expected_words = normalize_transcript(expected).split()
    actual_words = normalize_transcript(actual).split()
    if not expected_words:
        return False
    if not actual_words:
        return True
    minimum_actual_words = max(
        len(expected_words) + SEVERE_MISMATCH_MIN_EXTRA_WORDS,
        math.ceil(len(expected_words) * SEVERE_MISMATCH_MIN_LENGTH_RATIO),
    )
    return float(similarity) < SEVERE_MISMATCH_MAX_SIMILARITY and (
        len(actual_words) >= minimum_actual_words
        or abs(len(actual_words) - len(expected_words)) <= SEVERE_MISMATCH_MIN_EXTRA_WORDS
    )


def transcript_exceeds_physical_rate(actual: str, duration_seconds: float) -> bool:
    actual_words = normalize_transcript(actual).split()
    if not actual_words or duration_seconds <= 0:
        return False
    plausible_words = max(
        MIN_PLAUSIBLE_TRANSCRIPT_WORDS,
        math.ceil(duration_seconds * MAX_PLAUSIBLE_TRANSCRIPT_WORDS_PER_SECOND)
        + TRANSCRIPT_WORD_MARGIN,
    )
    return len(actual_words) > plausible_words


def transcription_exceeds_audio_timeline(
    segments: list[dict[str, Any]],
    duration_seconds: float,
) -> bool:
    if duration_seconds <= 0 or not segments:
        return False
    plausible_end = max(
        duration_seconds + WHISPER_TIMELINE_ABSOLUTE_MARGIN_SECONDS,
        duration_seconds * WHISPER_TIMELINE_DURATION_FACTOR,
    )
    for segment in segments:
        try:
            end = float(segment.get("end", 0.0))
        except (TypeError, ValueError):
            continue
        if end > plausible_end:
            return True
    return False


def load_audio_for_whisper(path: Path) -> np.ndarray:
    audio, sample_rate = sf.read(path, dtype="float32", always_2d=False)
    array = np.asarray(audio, dtype=np.float32)
    if array.ndim != 1:
        raise RuntimeError(f"Whisper input must be mono, got shape {array.shape}")
    if int(sample_rate) != WHISPER_SAMPLE_RATE:
        divisor = math.gcd(int(sample_rate), WHISPER_SAMPLE_RATE)
        array = resample_poly(
            array,
            WHISPER_SAMPLE_RATE // divisor,
            int(sample_rate) // divisor,
        ).astype(np.float32, copy=False)
    return array


class WhisperVerifier:
    def __init__(self, settings: dict[str, Any], log: Callable[[str], None]) -> None:
        self.settings = settings["asr"]
        self.allow_downloads = bool(settings.get("safety", {}).get("allow_network_downloads_during_job", False))
        self.log = log
        self.model = None
        self.device = str(self.settings.get("device", "cuda"))
        self._last_transcription_timeline_impossible = False

    def load(self) -> bool:
        if not self.settings.get("enabled", True):
            return False
        if self.model is not None:
            return True
        try:
            import torch
            import whisper

            device = self.device
            if device.startswith("cuda") and not torch.cuda.is_available():
                if self.settings.get("cpu_fallback", True):
                    device = "cpu"
                else:
                    raise RuntimeError("CUDA unavailable for Whisper")
            model_name = str(self.settings["model"])
            download_root = Path(str(self.settings.get("download_root", "models/whisper")))
            model_url = getattr(whisper, "_MODELS", {}).get(model_name)
            expected_model = download_root / str(model_url).rsplit("/", 1)[-1] if model_url else None
            if not self.allow_downloads and expected_model is not None and not expected_model.exists():
                message = (
                    f"Thiếu Whisper {model_name} trong {download_root}. Job không được tự tải model giữa chừng; "
                    "hãy chạy Ebook Reader trước."
                )
                self.log(message)
                if self.settings.get("required", False) or self.settings.get("failure_policy") == "fail":
                    raise RuntimeError(message)
                return False
            self.log(f"Nạp Whisper {model_name} trên {device}.")
            self.model = whisper.load_model(
                model_name,
                device=device,
                download_root=str(download_root),
            )
            self.device = device
            return True
        except Exception as exc:  # noqa: BLE001
            self.log(f"Không nạp được Whisper: {exc}")
            if self.settings.get("required", False) or self.settings.get("failure_policy") == "fail":
                raise
            return False

    def unload(self) -> None:
        had_model = self.model is not None
        self.model = None
        if not had_model:
            return
        gc.collect()
        try:
            import torch

            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except Exception:
            pass
        trim_process_working_set()

    def _transcribe_audio(
        self,
        audio: np.ndarray,
        duration_seconds: float,
        *,
        confirmation: bool,
    ) -> str:
        if self.model is None:
            raise RuntimeError("Whisper is not loaded")
        self._last_transcription_timeline_impossible = False
        decode_options: dict[str, Any] = {
            "language": "vi",
            "task": "transcribe",
            "fp16": self.device.startswith("cuda"),
            "temperature": 0.0,
            "condition_on_previous_text": False,
            "verbose": False,
        }
        if not confirmation:
            decode_options["beam_size"] = int(self.settings.get("beam_size", 5))
        result = self.model.transcribe(audio, **decode_options)
        raw_segments = result.get("segments", [])
        segments = [item for item in raw_segments if isinstance(item, dict)]
        self._last_transcription_timeline_impossible = transcription_exceeds_audio_timeline(
            segments,
            duration_seconds,
        )
        return str(result.get("text", "")).strip()

    def transcribe(self, path: Path, *, confirmation: bool = False) -> str:
        audio = load_audio_for_whisper(path)
        try:
            duration_seconds = float(sf.info(path).duration)
        except (RuntimeError, TypeError, ValueError):
            duration_seconds = float(audio.size / WHISPER_SAMPLE_RATE)
        return self._transcribe_audio(
            audio,
            duration_seconds,
            confirmation=confirmation,
        )

    def _evaluate_transcript(
        self,
        expected: str,
        transcript: str,
        duration_seconds: float,
    ) -> dict[str, Any]:
        similarity, wer = transcript_metrics(expected, transcript)
        if self._last_transcription_timeline_impossible:
            return {
                "passed": False,
                "verdict": ASR_INCONCLUSIVE,
                "transcript": transcript,
                "similarity": similarity,
                "wer": wer,
                "reason": "ASR_TRANSCRIPT_TIMELINE_IMPOSSIBLE",
                "repairable": False,
                "severe": False,
            }
        if transcript_exceeds_physical_rate(transcript, duration_seconds):
            return {
                "passed": False,
                "verdict": ASR_INCONCLUSIVE,
                "transcript": transcript,
                "similarity": similarity,
                "wer": wer,
                "reason": "ASR_TRANSCRIPT_RATE_IMPOSSIBLE",
                "repairable": False,
                "severe": False,
            }
        if is_vocalization_only(expected) and (
            not normalize_transcript(transcript) or is_vocalization_only(transcript)
        ):
            return {
                "passed": True,
                "verdict": ASR_PASS,
                "transcript": transcript,
                "similarity": similarity,
                "wer": wer,
                "reason": "VOCALIZATION_ASR_COMPATIBLE",
                "repairable": False,
                "severe": False,
            }
        min_similarity = float(self.settings.get("min_similarity", 0.58))
        max_wer = float(self.settings.get("max_wer", 0.58))
        passed = _passes_asr_content_thresholds(
            bool(transcript),
            similarity,
            wer,
            min_similarity=min_similarity,
            max_wer=max_wer,
        )
        return {
            "passed": passed,
            "verdict": ASR_PASS if passed else ASR_MISMATCH,
            "transcript": transcript,
            "similarity": similarity,
            "wer": wer,
            "reason": "ok" if passed else "ASR_MISMATCH",
            "repairable": is_asr_repair_candidate(expected),
            "severe": not passed and is_severe_asr_mismatch(expected, transcript, similarity),
        }

    def can_verify_repeated_short(self, expected: str) -> bool:
        word_count = len(normalize_transcript(expected).split())
        return 0 < word_count <= SHORT_CONTEXT_MAX_WORDS

    def verify_repeated_short(
        self,
        expected: str,
        wav_path: Path,
        *,
        confirmation: bool = False,
    ) -> dict[str, Any]:
        if not self.can_verify_repeated_short(expected):
            raise ValueError("Repeated short-context ASR only supports one to five words")
        if not self.load():
            return {
                "passed": False,
                "verdict": ASR_INCONCLUSIVE,
                "transcript": "",
                "similarity": 0.0,
                "wer": 1.0,
                "reason": "ASR_NOT_RUN",
                "repairable": False,
                "severe": False,
            }
        audio = load_audio_for_whisper(wav_path)
        gap = np.zeros(
            int(round(WHISPER_SAMPLE_RATE * SHORT_CONTEXT_GAP_SECONDS)),
            dtype=np.float32,
        )
        pieces: list[np.ndarray] = []
        for index in range(SHORT_CONTEXT_REPEAT_COUNT):
            pieces.append(audio)
            if index + 1 < SHORT_CONTEXT_REPEAT_COUNT:
                pieces.append(gap)
        repeated_audio = np.concatenate(pieces).astype(np.float32, copy=False)
        transcript = self._transcribe_audio(
            repeated_audio,
            repeated_audio.size / WHISPER_SAMPLE_RATE,
            confirmation=confirmation,
        )
        repeated_expected = " ".join([expected] * SHORT_CONTEXT_REPEAT_COUNT)
        result = self._evaluate_transcript(
            repeated_expected,
            transcript,
            repeated_audio.size / WHISPER_SAMPLE_RATE,
        )
        if result["passed"]:
            result["reason"] = "ASR_REPEATED_SHORT_PASS"
        return result

    def verify(
        self,
        expected: str,
        wav_path: Path,
        *,
        confirmation: bool = False,
    ) -> dict[str, Any]:
        normalized_expected = normalize_transcript(expected)
        word_count = len(normalized_expected.split())
        if not normalized_expected:
            return {
                "passed": True,
                "verdict": ASR_PASS,
                "transcript": "",
                "similarity": 1.0,
                "wer": 0.0,
                "reason": "NON_LEXICAL_SKIP",
                "repairable": False,
                "severe": False,
            }
        if word_count < int(self.settings.get("min_words", 3)) and not self.settings.get("verify_short_dialogue", True):
            return {
                "passed": False,
                "verdict": ASR_INCONCLUSIVE,
                "transcript": "",
                "similarity": 1.0,
                "wer": 0.0,
                "reason": "short_skip",
                "repairable": False,
                "severe": False,
            }
        if not self.load():
            return {
                "passed": False,
                "verdict": ASR_INCONCLUSIVE,
                "transcript": "",
                "similarity": 0.0,
                "wer": 1.0,
                "reason": "ASR_NOT_RUN",
                "repairable": False,
                "severe": False,
            }
        self._last_transcription_timeline_impossible = False
        try:
            transcript = (
                self.transcribe(wav_path, confirmation=True)
                if confirmation
                else self.transcribe(wav_path)
            )
        except Exception as exc:  # noqa: BLE001
            self.log(f"Whisper inference lỗi cho {wav_path.name}: {exc}")
            if self.settings.get("required", False) or self.settings.get("failure_policy") == "fail":
                raise
            return {
                "passed": False,
                "verdict": ASR_INCONCLUSIVE,
                "transcript": "",
                "similarity": 0.0,
                "wer": 1.0,
                "reason": "ASR_ERROR",
                "repairable": False,
                "severe": False,
            }
        try:
            duration_seconds = float(sf.info(wav_path).duration)
        except (RuntimeError, TypeError, ValueError):
            duration_seconds = 0.0
        return self._evaluate_transcript(expected, transcript, duration_seconds)
