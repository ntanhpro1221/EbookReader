from __future__ import annotations

import json
import math
import os
import re
import sqlite3
import time
import wave
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Mapping, Sequence

from .asr_contract import (
    COLLAPSED_SHORT_CONTEXT_EFFECTIVE_REPEAT_COUNT,
    COLLAPSED_SHORT_CONTEXT_MODE,
    LOCKED_NAME_ANCHOR_METRICS_VERSION,
    SHORT_CONTEXT_REPEAT_COUNT,
)
from .audio_transform_contract import (
    POSTPROCESS_ALGORITHM,
    POSTPROCESS_OUTPUT_CODEC,
    POSTPROCESS_OUTPUT_SAMPLES_FIELD,
    POSTPROCESS_PROFILE_FIELD,
    POSTPROCESS_PROFILE_NONE,
    POSTPROCESS_PROFILE_TEMPO,
    POSTPROCESS_PROFILES,
    POSTPROCESS_SAMPLE_COUNT_RELATIVE_TOLERANCE,
    POSTPROCESS_SOURCE_CANDIDATE_ID_FIELD,
    POSTPROCESS_SOURCE_SAMPLE_RATE_FIELD,
    POSTPROCESS_SOURCE_SAMPLES_FIELD,
    POSTPROCESS_SOURCE_SHA256_FIELD,
    POSTPROCESS_TEMPO_DENOMINATOR,
    POSTPROCESS_TEMPO_FACTOR,
    POSTPROCESS_TEMPO_NUMERATOR,
)
from .io_utils import sha256_file, sha256_text, stable_int
from .models import BookStatus, ChapterStatus, SegmentStatus
from .perceptual_contract import (
    PERCEPTUAL_BASELINE_PITCH_SEMITONES,
    NATURALNESS_IMPROVEMENT_REQUIREMENT,
    NATURALNESS_REPAIR_ACTION,
    PERCEPTUAL_NATURALNESS_REVIEW_CODE,
    STANDARD_CANDIDATE_GATE_REQUIREMENT,
)
from .text_processing import (
    CLAUSE_SPLIT_STRATEGY,
    SENTENCE_SPLIT_STRATEGY,
    SPLIT_MAX_CHARS_BY_STRATEGY,
    SPLIT_MAX_CHARS_FIELD,
    SPLIT_STRATEGY_FIELD,
    is_standalone_ha_gasp,
)
from .tts_contract import (
    HA_VOCALIZATION_DELIVERY_PROFILE,
    HA_VOCALIZATION_FINAL_SAMPLES_FIELD,
    HA_VOCALIZATION_MAX_NEW_FRAMES,
    HA_VOCALIZATION_MAX_NEW_FRAMES_FIELD,
    HA_VOCALIZATION_MAX_TEMPERATURE,
    HA_VOCALIZATION_MAX_TOP_P,
    HA_VOCALIZATION_ORIGINAL_SAMPLES_FIELD,
    HA_VOCALIZATION_PADDING_PROVENANCE_FIELDS,
    HA_VOCALIZATION_PADDING_SAMPLES_FIELD,
    HA_VOCALIZATION_PROFILE_FIELD,
    HA_VOCALIZATION_PROVENANCE_FIELDS,
    HA_VOCALIZATION_SAMPLE_RATE_FIELD,
    HA_VOCALIZATION_SAMPLING_PROVENANCE_FIELDS,
    HA_VOCALIZATION_TARGET_SAMPLES_FIELD,
    HA_VOCALIZATION_TEMPERATURE_FIELD,
    HA_VOCALIZATION_TOP_P_FIELD,
)


# Version 1 is the legacy pre-QA layout. Existing projects did not persist a
# user_version, so they migrate from 0 through the current schema.
SCHEMA_VERSION = 12
QUALITY_SCOPE_SEGMENT = "segment"
QUALITY_SCOPE_CHAPTER = "chapter"
QUALITY_SCOPES = {QUALITY_SCOPE_SEGMENT, QUALITY_SCOPE_CHAPTER}
SEGMENT_AUDIO_QUALITY_STAGE = "segment_audio_v1"
SEGMENT_ASR_DECODE_QUALITY_STAGE = "segment_asr_decode_v1"
SEGMENT_PERCEPTUAL_QUALITY_STAGE = "segment_perceptual_v1"
CHAPTER_POST_ENCODE_QUALITY_STAGE = "chapter_post_encode_v1"
GENERATION_DELIVERY_PRIMARY = "primary"
GENERATION_DELIVERY_CLARITY = "clarity"
GENERATION_DELIVERY_MODES = frozenset(
    {GENERATION_DELIVERY_PRIMARY, GENERATION_DELIVERY_CLARITY}
)
GENERATION_STRATEGY_DIRECT = "direct_v1"
GENERATION_STRATEGY_SPLIT = "split_v1"
GENERATION_STRATEGIES = frozenset(
    {GENERATION_STRATEGY_DIRECT, GENERATION_STRATEGY_SPLIT}
)
PRONUNCIATION_DELIVERY_LOCKED = "locked_spoken_v1"
PRONUNCIATION_DELIVERY_SOURCE = "source_spelling_v1"
PRONUNCIATION_DELIVERY_VARIANTS = frozenset(
    {PRONUNCIATION_DELIVERY_LOCKED, PRONUNCIATION_DELIVERY_SOURCE}
)
QUALITY_VERDICT_PASS = "pass"
QUALITY_VERDICTS = {
    QUALITY_VERDICT_PASS,
    "repair",
    "inconclusive",
    "fail",
}
SEGMENT_CANDIDATE_GENERATING = "generating"
SEGMENT_CANDIDATE_SIGNAL_PASSED = "signal_passed"
SEGMENT_CANDIDATE_BEAM_RECORDED = "beam_recorded"
SEGMENT_CANDIDATE_DUAL_FAILED = "dual_failed"
SEGMENT_CANDIDATE_DUAL_PASSED = "dual_passed"
SEGMENT_CANDIDATE_TTS_FAILED = "tts_failed"
SEGMENT_CANDIDATE_INVALID = "invalid"
SEGMENT_CANDIDATE_PROMOTED = "promoted"
SEGMENT_CANDIDATE_STATES = frozenset(
    {
        SEGMENT_CANDIDATE_GENERATING,
        SEGMENT_CANDIDATE_SIGNAL_PASSED,
        SEGMENT_CANDIDATE_BEAM_RECORDED,
        SEGMENT_CANDIDATE_DUAL_FAILED,
        SEGMENT_CANDIDATE_DUAL_PASSED,
        SEGMENT_CANDIDATE_TTS_FAILED,
        SEGMENT_CANDIDATE_INVALID,
        SEGMENT_CANDIDATE_PROMOTED,
    }
)


def segment_candidate_split_seed_salt(
    repair_round: int,
    pronunciation_delivery_variant: str,
) -> str:
    normalized_round = int(repair_round)
    normalized_variant = str(pronunciation_delivery_variant).strip().casefold()
    if normalized_round < 0:
        raise ValueError("segment candidate repair round must be non-negative")
    if normalized_variant not in PRONUNCIATION_DELIVERY_VARIANTS:
        raise ValueError("unsupported pronunciation delivery variant")
    prefix = f"asr_clarity_candidate_{normalized_round}"
    if normalized_variant == PRONUNCIATION_DELIVERY_LOCKED:
        return f"{prefix}_split"
    return f"{prefix}_{normalized_variant}_split"
SEGMENT_CANDIDATE_FAILURE_STATES = frozenset(
    {
        SEGMENT_CANDIDATE_DUAL_FAILED,
        SEGMENT_CANDIDATE_TTS_FAILED,
        SEGMENT_CANDIDATE_INVALID,
    }
)
SEGMENT_CANDIDATE_EXHAUSTION_ACTION = "candidate_repair_exhausted"
TEMPO_RESCUE_ASR_FAILURE_REASON = "ASR_MISMATCH"
ANALYSIS_CANDIDATE_ALLOCATED = "allocated"
ANALYSIS_CANDIDATE_CRITIC_IN_FLIGHT = "critic_in_flight"
ANALYSIS_CANDIDATE_CRITIC_INVALID = "critic_invalid"
ANALYSIS_CANDIDATE_CRITIC_ACCEPTED = "critic_accepted"
ANALYSIS_CANDIDATE_CRITIC_REJECTED = "critic_rejected"
ANALYSIS_CANDIDATE_ACCEPTED = "accepted"
ANALYSIS_CANDIDATE_TERMINAL = "terminal"
ANALYSIS_CANDIDATE_SUPERSEDED = "superseded"
ANALYSIS_CANDIDATE_STATES = frozenset(
    {
        ANALYSIS_CANDIDATE_ALLOCATED,
        ANALYSIS_CANDIDATE_CRITIC_IN_FLIGHT,
        ANALYSIS_CANDIDATE_CRITIC_INVALID,
        ANALYSIS_CANDIDATE_CRITIC_ACCEPTED,
        ANALYSIS_CANDIDATE_CRITIC_REJECTED,
        ANALYSIS_CANDIDATE_ACCEPTED,
        ANALYSIS_CANDIDATE_TERMINAL,
        ANALYSIS_CANDIDATE_SUPERSEDED,
    }
)
ANALYSIS_CRITIC_ATTEMPT_RESERVED = "reserved"
ANALYSIS_CRITIC_ATTEMPT_COMPLETED = "completed"
ANALYSIS_CRITIC_ATTEMPT_ABANDONED = "abandoned"
ANALYSIS_CRITIC_ATTEMPT_STATES = frozenset(
    {
        ANALYSIS_CRITIC_ATTEMPT_RESERVED,
        ANALYSIS_CRITIC_ATTEMPT_COMPLETED,
        ANALYSIS_CRITIC_ATTEMPT_ABANDONED,
    }
)
ANALYSIS_ACCEPTED_DELIVERY_FIELDS = frozenset(
    {
        "kind",
        "speaker",
        "gender",
        "age",
        "emotion",
        "intensity",
        "pace",
        "volume",
        "confidence",
        "personality_hint",
        "notes",
    }
)
ANALYSIS_PRONUNCIATION_FIELDS = frozenset(
    {
        "surface",
        "normalized_surface",
        "spoken_form",
        "confidence",
        "source",
        "locked",
    }
)
ANALYSIS_CRITIC_DELIVERY_FIELDS = (
    "kind",
    "speaker",
    "emotion",
    "intensity",
    "pace",
    "volume",
)
# Fields whose value cannot move the audio enough to be worth a retry. `emotion` and
# `intensity` reach loudness only, through an offset measured at 0.80 dB on 5.5% of a real
# chapter set; `pace` shapes silence and `volume` sets the LUFS target outright, so neither
# of those belongs here. A disagreement confined to these is recorded and accepted rather
# than sent back to the model - it once ended a whole run on a single line's intensity.
#
# This lives beside the field list, not beside the code that first needed it. Analysis
# computes the deltas and the database recomputes them to verify what was stored; when the
# rule existed in only one of those two places they disagreed, and the run died on
# "Accepted critic evidence does not bind exact delivery".
AFFECT_CUE_DISAGREEMENT_BLOCKS = False
INAUDIBLE_DELIVERY_FIELDS = frozenset({"emotion", "intensity"})


def require_all(
    message: str,
    *clauses: tuple[str, bool],
    _error: type[Exception] = RuntimeError,
    **context: Any,
) -> None:
    """Raise naming the clauses that failed, instead of only that something did.

    This file has 70 checks that combine three or more conditions into one `if` and one
    message, several of them sixteen conditions long. Four fired in a single ten-chapter
    run and each cost a full analysis pass to diagnose: the message says a binding broke
    without saying which, and the evidence is in memory rather than on disk, so the only
    way to look is to run it again.

    Written as (name, failed) pairs rather than as an expression so the names cannot drift
    from the conditions - there is one list, and it is both the check and the explanation.

        require_all(
            "Rejected critic evidence is not exactly candidate-bound",
            ("text_sha256", item["text_sha256"] != segment["text_sha256"]),
            ("accept_flag", not accept_flag_is_coherent(accept, deltas)),
            deltas=deltas,
        )

    `context` is appended verbatim, for the values a reader needs and cannot recover.
    """
    failed = [name for name, did_fail in clauses if did_fail]
    if not failed:
        return
    detail = "; ".join(f"{key}={value!r}" for key, value in sorted(context.items()))
    # `_error` keeps the exception type each caller already raised. Converting a check
    # must not quietly turn a ValueError into a RuntimeError - callers catch these.
    raise _error(
        f"{message}: {', '.join(failed)}" + (f"; {detail}" if detail else "")
    )


def critic_delta_fields(blocking: bool) -> tuple[str, ...]:
    """The fields a critic disagreement is counted over."""
    if blocking:
        return ANALYSIS_CRITIC_DELIVERY_FIELDS
    return tuple(
        field
        for field in ANALYSIS_CRITIC_DELIVERY_FIELDS
        if field not in INAUDIBLE_DELIVERY_FIELDS
    )


def host_derived_accept(raw_deltas: Sequence[str]) -> bool:
    """Whether the host would accept a candidate, given the full list of deltas.

    Acceptance is decided on the blocking subset while `raw_deltas` stays the complete
    record: a difference confined to a field nobody can hear was never a reason to reject a
    candidate. The two validators must agree about that, and twice they have not - the
    accepted branch derived it this way while the rejected branch recomputed it from the
    full list, so a candidate differing only in emotion and intensity was accepted by one
    and refused by the other. That killed a run at the same segment three times across two
    sittings.

    It lives here, once, so there is nothing left to copy.
    """
    blocking = set(critic_delta_fields(AFFECT_CUE_DISAGREEMENT_BLOCKS))
    return not [
        delta for delta in raw_deltas if str(delta).split(":", 1)[0] in blocking
    ]


def accept_flag_is_coherent(accept: Any, fields: Sequence[str]) -> bool:
    """Whether an accept flag can be true of the disagreements recorded beside it.

    `fields` are the field names still in dispute - the deltas themselves, or the fields
    left unresolved after overrides. Two shapes are legal and any rule that derives the
    flag allows only one of them:

    - Accepted. Legal exactly when nothing in dispute blocks, which is the same subset
      acceptance is decided on everywhere else.
    - Refused. Legal whenever there was something to refuse over, and that something may
      be a field nobody can hear - refusing on emotion alone is a real case with a test.

    Both halves were learned the hard way, one run each: demanding the flag equal the
    host's verdict killed a run on a candidate differing only in emotion and intensity,
    and the obvious repair - deriving it from the blocking subset - then broke the row
    that refuses on emotion alone.
    """
    blocking = set(critic_delta_fields(AFFECT_CUE_DISAGREEMENT_BLOCKS))
    names = [str(field).split(":", 1)[0] for field in fields]
    if accept is True:
        return not [name for name in names if name in blocking]
    if accept is False:
        return bool(names)
    return False


def rejected_accept_flag_is_coherent(accept: Any, raw_deltas: Sequence[str]) -> bool:
    """Whether a rejection record's accept flag can be true of the deltas beside it.

    Two different things are legal here and the previous rule allowed only one:

    - The critic rejected. It must have recorded something to reject over, but that
      something may be a field nobody can hear - a rejection on emotion alone is a real
      case with a test of its own.
    - The critic accepted while recording differences. Legal exactly when none of them
      blocks, which is the same subset acceptance is decided on everywhere else.

    Demanding `accept == (not raw_deltas)` conflated the two and killed a ten-chapter run
    on a candidate whose only differences were emotion and intensity.
    """
    return accept_flag_is_coherent(accept, raw_deltas)


ANALYSIS_CRITIC_RESERVED_SPEAKERS = ("NARRATOR", "UNKNOWN")
ANALYSIS_DELIVERY_NOTE_VERSION = "delivery_note_v1"
ANALYSIS_DELIVERY_NOTE_PREFIX = f"{ANALYSIS_DELIVERY_NOTE_VERSION}="
ANALYSIS_DELIVERY_NOTE_FIELDS = (
    "kind",
    "emotion",
    "intensity",
    "pace",
    "volume",
)
ADDRESSEE_REPAIR_NOTE = "đã tách người nói khỏi tên người được gọi"
EXPLICIT_ATTRIBUTION_NOTE = "đã khóa người nói từ lời dẫn cùng đoạn văn"
PARAGRAPH_SPEAKER_LOCK_NOTE = "đã đồng nhất người nói trong cùng đoạn văn"
CONTINUED_DIALOGUE_LOCK_NOTE = "đã giữ người nói cho câu thoại nối tiếp"
CHAPTER_HEADING_NOTE = "Tiêu đề chương được khóa delivery trung tính."
CROWD_SPEAKER_LOCK_NOTE = "đã khóa người nói từ lời dẫn tập thể kế tiếp"
ANALYSIS_HOST_NOTE_MARKERS = (
    EXPLICIT_ATTRIBUTION_NOTE,
    ADDRESSEE_REPAIR_NOTE,
    PARAGRAPH_SPEAKER_LOCK_NOTE,
    CONTINUED_DIALOGUE_LOCK_NOTE,
    CHAPTER_HEADING_NOTE,
    CROWD_SPEAKER_LOCK_NOTE,
)
ANALYSIS_CANDIDATE_CONTENT_NOTE_MARKERS = frozenset(
    {
        EXPLICIT_ATTRIBUTION_NOTE,
        ADDRESSEE_REPAIR_NOTE,
        PARAGRAPH_SPEAKER_LOCK_NOTE,
        CONTINUED_DIALOGUE_LOCK_NOTE,
    }
)
ANALYSIS_SOURCE_ROLE_CONTENT = "content"
ANALYSIS_SOURCE_ROLE_CHAPTER_HEADING = "chapter_heading"
ANALYSIS_CONTEXT_POLICY_ADJACENT = "adjacent_context"
ANALYSIS_CONTEXT_POLICY_PREVIOUS_ONLY = "previous_context_only"
ANALYSIS_CONTEXT_POLICY_NARRATION_BEFORE_THOUGHT = (
    "narration_before_thought_previous_only"
)
ANALYSIS_CONTEXT_POLICY_NARRATION_BEFORE_NEXT_PARAGRAPH_THOUGHT = (
    "narration_precedes_next_paragraph_thought"
)
ANALYSIS_CONTEXT_POLICY_TARGET_ONLY = "target_only"
ANALYSIS_CONTEXT_SOURCE_KIND_RULE = "narration_precedes_immediate_thought"
ANALYSIS_SOURCE_DIALOGUE_KIND_RULE = "explicit_dialogue_boundary"
ANALYSIS_HOST_STRUCTURAL_POLICY_VERSION = "chapter_heading_lock_v2"
ANALYSIS_HOST_AFFECT_POLICY_VERSION = "host_affect_v10"
ANALYSIS_HOST_SEMANTIC_POLICY_VERSION = "host_semantic_lock_v6"
ANALYSIS_HOST_CRITIC_COMPATIBILITY_POLICY_VERSION = "host_critic_compatibility_v1"
ANALYSIS_DIRECTOR_CRITIC_POLICY_VERSION = "second_pass_v18"
ANALYSIS_DIRECTOR_RETRY_SCHEMA_POLICY_VERSION = (
    "per_id_direct_affect_candidate_speaker_enum_v4"
)
ANALYSIS_CRITIC_SUBJECT_HASH_VERSION = "critic_retry_schema_epoch_v1"
ANALYSIS_CRITIC_CONFIDENCE_MAX = 0.99
ANALYSIS_CRITIC_EVIDENCE_QUOTE_MAX_LENGTH = 240
ANALYSIS_CRITIC_EVIDENCE_POLICY_SINGLETON_FULL_TARGET = (
    "singleton_full_target_v1"
)
ANALYSIS_CRITIC_EVIDENCE_POLICY_SINGLETON_SOURCE_ANCHOR = (
    "singleton_source_anchor_enum_v1"
)
ANALYSIS_CRITIC_EVIDENCE_POLICY_PER_ID_SOURCE_ANCHOR = (
    "per_id_source_anchor_enum_v1"
)


def canonical_analysis_critic_source_anchors(source_text: str) -> tuple[str, ...]:
    """Return stable exact-source evidence choices bounded by the critic schema."""
    if not isinstance(source_text, str) or not source_text or not source_text.strip():
        raise ValueError("Analysis critic source text must contain visible characters")

    spans: list[tuple[int, int]] = []

    def split_span(start: int, end: int) -> None:
        if end - start <= ANALYSIS_CRITIC_EVIDENCE_QUOTE_MAX_LENGTH:
            spans.append((start, end))
            return

        midpoint = start + (end - start) // 2
        whitespace_runs = []
        for match in re.finditer(r"\s+", source_text[start:end]):
            run_start = start + match.start()
            run_end = start + match.end()
            if start < run_start and run_end < end:
                whitespace_runs.append((run_start, run_end))
        if whitespace_runs:
            split_start, split_end = min(
                whitespace_runs,
                key=lambda item: (
                    abs(item[0] + item[1] - 2 * midpoint),
                    item[0],
                ),
            )
        else:
            split_start = midpoint
            split_end = midpoint
        split_span(start, split_start)
        split_span(split_end, end)

    split_span(0, len(source_text))
    anchors: list[str] = []
    seen: set[str] = set()
    for start, end in spans:
        anchor = source_text[start:end]
        if not anchor or not anchor.strip() or anchor in seen:
            continue
        if (
            len(anchor) > ANALYSIS_CRITIC_EVIDENCE_QUOTE_MAX_LENGTH
            or anchor not in source_text
        ):
            raise RuntimeError("Analysis critic source anchor derivation is invalid")
        seen.add(anchor)
        anchors.append(anchor)
    if not anchors:
        raise ValueError("Analysis critic source text produced no usable evidence anchors")
    return tuple(anchors)


def analysis_critic_anchor_set_sha256(anchors: Sequence[str]) -> str:
    if isinstance(anchors, (str, bytes)):
        raise ValueError("Analysis critic anchors must be a sequence of exact strings")
    values = tuple(anchors)
    if (
        not values
        or any(
            not isinstance(anchor, str)
            or not anchor
            or not anchor.strip()
            or len(anchor) > ANALYSIS_CRITIC_EVIDENCE_QUOTE_MAX_LENGTH
            for anchor in values
        )
        or len(set(values)) != len(values)
    ):
        raise ValueError("Analysis critic anchors must be unique non-empty bounded strings")
    payload = json.dumps(
        list(values),
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    )
    return sha256_text(payload)


def canonical_analysis_critic_per_id_source_anchor_map(
    critic_rows: Sequence[Mapping[str, Any]],
) -> tuple[dict[str, Any], ...]:
    """Bind each multi-row critic ID to exact anchors from only its source text."""
    if isinstance(critic_rows, (str, bytes)):
        raise ValueError("Analysis critic rows must be an ordered sequence")
    rows = tuple(critic_rows)
    if len(rows) < 2:
        raise ValueError("Per-ID analysis critic anchors require multiple source rows")
    anchor_map: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for row in rows:
        if not isinstance(row, Mapping):
            raise ValueError("Analysis critic source rows must be mappings")
        critic_id = row.get("id")
        source_text = row.get("text")
        if (
            not isinstance(critic_id, str)
            or not critic_id
            or critic_id in seen_ids
            or not isinstance(source_text, str)
        ):
            raise ValueError("Analysis critic rows require unique IDs and source text")
        seen_ids.add(critic_id)
        anchor_map.append(
            {
                "id": critic_id,
                "text_sha256": sha256_text(source_text),
                "anchors": list(canonical_analysis_critic_source_anchors(source_text)),
            }
        )
    return tuple(anchor_map)


def analysis_critic_per_id_anchor_map_sha256(
    anchor_map: Sequence[Mapping[str, Any]],
) -> str:
    """Hash a canonical ordered per-ID source-anchor map without reordering rows."""
    if isinstance(anchor_map, (str, bytes)):
        raise ValueError("Analysis critic per-ID anchor map must be a sequence")
    items = tuple(anchor_map)
    if len(items) < 2:
        raise ValueError("Per-ID analysis critic anchor map requires multiple rows")
    canonical_items: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    sha256_pattern = re.compile(r"[0-9a-f]{64}")
    for item in items:
        if not isinstance(item, Mapping) or set(item) != {
            "id",
            "text_sha256",
            "anchors",
        }:
            raise ValueError("Analysis critic per-ID anchor map has invalid fields")
        critic_id = item.get("id")
        text_sha256 = item.get("text_sha256")
        anchors = item.get("anchors")
        if (
            not isinstance(critic_id, str)
            or not critic_id
            or critic_id in seen_ids
            or not isinstance(text_sha256, str)
            or sha256_pattern.fullmatch(text_sha256) is None
            or not isinstance(anchors, (list, tuple))
        ):
            raise ValueError("Analysis critic per-ID anchor map is invalid")
        anchor_values = tuple(anchors)
        analysis_critic_anchor_set_sha256(anchor_values)
        seen_ids.add(critic_id)
        canonical_items.append(
            {
                "id": critic_id,
                "text_sha256": text_sha256,
                "anchors": list(anchor_values),
            }
        )
    payload = json.dumps(
        canonical_items,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    return sha256_text(payload)


def analysis_source_narration_precedes_thought(
    *,
    chapter_id: int | None,
    seq: int | None,
    paragraph_index: int | None,
    kind_hint: str,
    next_chapter_id: int | None,
    next_seq: int | None,
    next_paragraph_index: int | None,
    next_kind_hint: str,
) -> bool:
    """Return whether immutable source metadata requires hiding a following thought."""
    return bool(
        type(chapter_id) is int
        and type(seq) is int
        and type(paragraph_index) is int
        and kind_hint == "narration"
        and type(next_chapter_id) is int
        and next_chapter_id == chapter_id
        and type(next_seq) is int
        and next_seq == seq + 1
        and type(next_paragraph_index) is int
        and next_paragraph_index == paragraph_index
        and next_kind_hint == "thought"
    )


def analysis_source_narration_precedes_next_paragraph_thought(
    *,
    chapter_id: int | None,
    seq: int | None,
    paragraph_index: int | None,
    kind_hint: str,
    next_chapter_id: int | None,
    next_seq: int | None,
    next_paragraph_index: int | None,
    next_kind_hint: str,
) -> bool:
    """Return whether a next-paragraph thought must be hidden from the critic."""
    return bool(
        type(chapter_id) is int
        and type(seq) is int
        and type(paragraph_index) is int
        and kind_hint == "narration"
        and type(next_chapter_id) is int
        and next_chapter_id == chapter_id
        and type(next_seq) is int
        and next_seq == seq + 1
        and type(next_paragraph_index) is int
        and next_paragraph_index == paragraph_index + 1
        and next_kind_hint == "thought"
    )


ANALYSIS_CHAPTER_HEADING_CONFIDENCE = 0.95
ANALYSIS_CHAPTER_HEADING_PATTERN = re.compile(
    r"^\s*(?:chương|chapter|hồi|phần|part|quyển|book|tập|volume)\s+"
    r"(?:\d{1,5}|[ivxlcdm]{1,12})"
    r"(?:\s*[-\u2013\u2014:]\s*\S(?:.*\S)?)?\s*$",
    flags=re.IGNORECASE,
)
ANALYSIS_CHAPTER_HEADING_DELIVERY = {
    "kind": "narration",
    "speaker": "NARRATOR",
    "emotion": "neutral",
    "intensity": 0,
    "pace": "normal",
    "volume": "normal",
}
ANALYSIS_HOST_STRUCTURAL_LOCK_FIELDS = frozenset(
    {
        "policy_version",
        "stable_id",
        "text_sha256",
        "source_role",
        "context_policy",
        "evidence_quote",
        "generator_fields",
        "generator_notes",
        "generator_confidence",
        "locked_fields",
        "locked_confidence",
    }
)
ANALYSIS_CRITIC_KINDS = frozenset({"narration", "dialogue", "thought"})
ANALYSIS_CRITIC_EMOTIONS = frozenset(
    {
        "neutral",
        "happy",
        "sad",
        "angry",
        "afraid",
        "surprised",
        "tender",
        "sarcastic",
        "excited",
        "tired",
        "whispering",
    }
)
ANALYSIS_CRITIC_PACES = frozenset({"slow", "normal", "fast"})
ANALYSIS_CRITIC_VOLUMES = frozenset({"soft", "normal", "loud"})
ANALYSIS_HOST_SEMANTIC_LOCK_FIELDS = frozenset(
    {
        "policy_version",
        "stable_id",
        "text_sha256",
        "source_role",
        "field",
        "rule",
        "cue_class",
        "candidate_emotion",
        "allowed_emotions",
        "related_stable_id",
        "related_text_sha256",
    }
)
ANALYSIS_HOST_CLEARANCE_FIELDS = frozenset(
    {
        "policy_version",
        "status",
        "candidate_hash",
        "checked_segment_count",
        "matched_rule_count",
        "evidence",
        "structural_locks",
        "semantic_locks",
    }
)
ANALYSIS_DETERMINISTIC_ISSUE_FIELDS = frozenset(
    {
        "host_affect_clearance",
        "semantic_issues",
    }
)
ANALYSIS_HOST_SEMANTIC_RULE_CONTRACTS = {
    "thought_self_preservation_mortality": {
        "cue_class": "self_preservation_mortality",
        "allowed_emotions": ("afraid",),
        "source_kind": "thought",
        "requires_related": False,
    },
    "adjacent_thought_wake_self_rescue": {
        "cue_class": "wake_self_rescue_after_mortality",
        "allowed_emotions": ("afraid",),
        "source_kind": "thought",
        "requires_related": True,
    },
    "respiratory_injury_with_consciousness_loss": {
        "cue_class": "physical_collapse",
        "allowed_emotions": ("afraid", "tired"),
        "source_kind": "narration",
        "requires_related": False,
    },
    "narration_desperate_exertion": {
        "cue_class": "desperate_exertion",
        "allowed_emotions": ("afraid", "sad", "tired"),
        "source_kind": "narration",
        "requires_related": False,
    },
    "narration_recalled_persistent_fear": {
        "cue_class": "recalled_persistent_fear",
        "allowed_emotions": ("afraid",),
        "source_kind": "narration",
        "requires_related": False,
    },
    "narration_stunned_blank_mind": {
        "cue_class": "stunned_blank_mind",
        "allowed_emotions": ("surprised",),
        "source_kind": "narration",
        "requires_related": False,
    },
    "narration_sleep_paralysis_helplessness": {
        "cue_class": "sleep_paralysis_helplessness",
        "allowed_emotions": ("afraid",),
        "source_kind": "narration",
        "requires_related": False,
        "protects_source_kind": True,
    },
}
ANALYSIS_HOST_MORTALITY_PATTERN = re.compile(
    r"\b(?:sẽ|sắp)\s+chết(?:\s+(?:mất|thôi))?\b",
    flags=re.IGNORECASE,
)
ANALYSIS_HOST_SUBJECTLESS_SELF_CONTROL_PATTERN = re.compile(
    r"^\s*[\"'“”‘’]*\s*không\s+được\s*(?:…|\.{3})\s*"
    r"không\s+được\s+ngủ\s*(?:…|\.{3})\s*"
    r"(?:sẽ|sắp)\s+chết\s+(?:mất|thôi)\s*[.!?…\"'“”‘’]*\s*$",
    flags=re.IGNORECASE,
)
ANALYSIS_HOST_EXPERIENCER_PATTERN = re.compile(
    r"\b(?:tôi|ta|mình|bản\s+thân|mày|mi|ngươi|hắn|nó|anh|chị|ông|bà|cô|"
    r"cậu|chúng\s+tôi|chúng\s+ta|chúng\s+mày|chúng\s+nó|họ)\b",
    flags=re.IGNORECASE,
)
ANALYSIS_HOST_SELF_EXPERIENCERS = frozenset(
    {"tôi", "ta", "mình", "bản thân", "chúng tôi", "chúng ta"}
)
ANALYSIS_HOST_MORTALITY_COGNITION_PREFIX_PATTERN = re.compile(
    r"\b(?:nghĩ|tưởng|cho\s+rằng|tin)(?:\s+rằng)?"
    r"(?:\s+(?:tôi|ta|mình|bản\s+thân|chúng\s+tôi|chúng\s+ta))?\s*$",
    flags=re.IGNORECASE,
)
ANALYSIS_HOST_MORTALITY_RESOLVED_COGNITION_PREFIX_PATTERN = re.compile(
    r"\b(?:đã\s+từng|từng|không\s+còn|chẳng\s+còn|không|chẳng|chưa)"
    r"(?:\s+(?:còn|hề|bao\s+giờ|từng|thật\s+sự|thực\s+sự|thể)){0,2}\s+"
    r"(?:nghĩ|tưởng|cho\s+rằng|tin)(?:\s+rằng)?"
    r"(?:\s+(?:tôi|ta|mình|bản\s+thân|chúng\s+tôi|chúng\s+ta))?\s*$",
    flags=re.IGNORECASE,
)
ANALYSIS_HOST_WAKE_PATTERN = re.compile(
    r"^\s*[\"'“”‘’]*\s*tỉnh\s+dậy\s*[,!?.…-]*\s*"
    r"(?:phải|mau|hãy|cố\s+)?\s*tỉnh\s+dậy\s*[!?.…\"'“”‘’]*\s*$",
    flags=re.IGNORECASE,
)
ANALYSIS_PHYSICAL_RESPIRATORY_INJURY_PATTERN = re.compile(
    r"\b(?:phổi(?:\s+và\s+yết\s+hầu)?|yết\s+hầu)"
    r"(?:\s+(?:đang|như|gần\s+như)){0,2}\s+(?:bị\s+)?"
    r"(?:thiêu\s+đốt|bỏng\s+rát)\b",
    flags=re.IGNORECASE,
)
ANALYSIS_PHYSICAL_CONSCIOUSNESS_LOSS_PATTERN = re.compile(
    r"\bý\s+thức(?:\s+(?!(?:không|chẳng|chưa|hết|khỏi)\b)[^\s.,!?;:…]+){0,10}\s+"
    r"(?:mơ\s+hồ|lịm\s+dần|mất\s+dần)\b",
    flags=re.IGNORECASE,
)
ANALYSIS_HOST_DESPERATE_EXERTION_PATTERN = re.compile(
    r"\b(?:tôi|ta|mình|bản\s+thân|anh|chị|ông|bà|cô|cậu|hắn|nó|họ)\s+"
    r"tuyệt\s+vọng\s+gắng\s+gượng\b",
    flags=re.IGNORECASE,
)
ANALYSIS_HOST_DESPERATE_EXERTION_QUOTE_CHARACTERS = frozenset("\"'“”‘’")
ANALYSIS_HOST_DESPERATE_EXERTION_NONASSERTIVE_PREFIX_PATTERN = re.compile(
    r"(?:^|[.!?…;:])[^.!?…;:]*\b(?:nếu|giả\s+(?:sử|như)|liệu|"
    r"phải\s+chăng|hay\s+là|có\s+lẽ|có\s+thể|dường\s+như|hình\s+như|"
    r"nghe\s+(?:nói|bảo)|(?:nghĩ|tưởng|tin|nghi\s+ngờ|nói|kể|bảo)"
    r"(?:\s+rằng)?|"
    r"(?:không\s+ai|(?:không|chẳng|chưa)(?:\s+(?:hề|còn|thể|từng|"
    r"bao\s+giờ|thật\s+sự|thực\s+sự|hoàn\s+toàn)){0,2})\s+"
    r"(?:(?:tin|nghĩ)(?:\s+rằng)?|cho\s+rằng)|không\s+có\s+chuyện)\b"
    r"[^.!?…;:]*$",
    flags=re.IGNORECASE,
)
ANALYSIS_HOST_DIRECT_AFFECT_QUOTE_CHARACTERS = frozenset("\"'“”‘’")
ANALYSIS_HOST_DIRECT_AFFECT_QUESTION_CHARACTERS = frozenset("?？")
ANALYSIS_HOST_DIRECT_AFFECT_SENTENCE_START_PREFIX_PATTERN = re.compile(
    r"(?:^|[.!?…])\s*$",
)
ANALYSIS_HOST_DIRECT_AFFECT_TERMINAL_SUFFIX_PATTERN = re.compile(
    r"\s*(?:[.!…])?\s*",
)
ANALYSIS_HOST_RECALLED_PERSISTENT_FEAR_PREFIX_PATTERN = re.compile(
    r"(?:^|[.!?…])\s*giấc\s+mơ\s+(?:này|ấy|đó)\s+chân\s+thực\s+"
    r"(?:tới|đến)\s+dị\s+thường,\s*(?:khiến|làm)\s+cho\s*$",
    flags=re.IGNORECASE,
)
ANALYSIS_HOST_RECALLED_PERSISTENT_FEAR_SUFFIX_PATTERN = re.compile(
    r"\.\s*Cộng\s+thêm\s+việc\s+không\s+cảm\s+nhận\s+thấy\s+sự\s+"
    r"tồn\s+tại\s+của\s+ngọn\s+lửa,\s*cậu\s+bèn\s+ngồi\s+thừ\s+"
    r"người\s+ra,\s*một\s+lúc\s+lâu\s+vẫn\s+chưa\s+hoàn\s+hồn\.\s*",
    flags=re.IGNORECASE,
)
ANALYSIS_HOST_STUNNED_BLANK_MIND_PREFIX_PATTERN = re.compile(
    r"(?:^|[.!?…])\s*giống\s+như(?:\s+thể)?\s+bị"
    r"\s+(?:một\s+)?cây\s+chùy"
    r"(?:\s+(?:lớn|nặng|khổng\s+lồ))?\s+(?:nện|đập)\s+vào\s+đầu,\s*$",
    flags=re.IGNORECASE,
)
ANALYSIS_HOST_VIETNAMESE_UPPERCASE_PATTERN = (
    r"[A-ZÀÁẢÃẠĂẰẮẲẴẶÂẦẤẨẪẬĐÈÉẺẼẸÊỀẾỂỄỆÌÍỈĨỊ"
    r"ÒÓỎÕỌÔỒỐỔỖỘƠỜỚỞỠỢÙÚỦŨỤƯỪỨỬỮỰỲÝỶỸỴ]"
)
ANALYSIS_HOST_DIRECT_AFFECT_SUBJECT_PATTERN = (
    r"(?:tôi|ta|mình|anh|chị|ông|bà|cô|cậu|hắn|nó|họ|"
    rf"(?-i:{ANALYSIS_HOST_VIETNAMESE_UPPERCASE_PATTERN}[A-Za-zÀ-ỹĐđ]*"
    rf"(?:\s+{ANALYSIS_HOST_VIETNAMESE_UPPERCASE_PATTERN}"
    r"[A-Za-zÀ-ỹĐđ]*){0,1}))"
)
ANALYSIS_HOST_RECALLED_PERSISTENT_FEAR_PATTERN = re.compile(
    rf"\b{ANALYSIS_HOST_DIRECT_AFFECT_SUBJECT_PATTERN}\s+"
    r"(?:(?:đến|tới)\s+giờ\s+)?(?:nghĩ|nhớ)\s+lại\s+vẫn"
    r"(?:\s+(?:còn|đang))?\s+tim\s+đập\s+chân\s+run\b",
    flags=re.IGNORECASE,
)
ANALYSIS_HOST_STUNNED_BLANK_MIND_PATTERN = re.compile(
    rf"\b{ANALYSIS_HOST_DIRECT_AFFECT_SUBJECT_PATTERN}\s+(?:đứng\s+)?"
    r"đực\s+mặt(?:\s+ra)?\s*,\s*đầu\s+óc"
    r"(?:\s+một\s+mảng)?\s+trắng\s+xóa\b",
    flags=re.IGNORECASE,
)
ANALYSIS_HOST_SLEEP_PARALYSIS_PATTERN = re.compile(
    r"\bbị\s+bóng\s+đè\b",
    flags=re.IGNORECASE,
)
ANALYSIS_HOST_DREAM_AWARENESS_PATTERN = re.compile(
    rf"\b{ANALYSIS_HOST_DIRECT_AFFECT_SUBJECT_PATTERN}\s+"
    r"(?:vẫn\s+)?(?:biết|nhận\s+thức)(?:\s+rõ)?\s+"
    r"(?:rằng\s+)?(?:mình|bản\s+thân)\s+đang\s+(?:nằm\s+)?mơ\b",
    flags=re.IGNORECASE,
)
ANALYSIS_HOST_DESIRE_ESCAPE_PATTERN = re.compile(
    r"\b(?:muốn|mong\s+muốn)\s+(?:tự\s+)?thoát\s+ra\b",
    flags=re.IGNORECASE,
)
ANALYSIS_HOST_MOTOR_HELPLESSNESS_PATTERN = re.compile(
    r"\b(?:không|chẳng)\s+thể\s+(?:tự\s+)?"
    r"(?:điều\s+khiển|kiểm\s+soát)\s+(?:được\s+)?"
    r"(?:bản\s+thân|cơ\s+thể|chính\s+mình)\b",
    flags=re.IGNORECASE,
)
ANALYSIS_HOST_SLEEP_PARALYSIS_NONASSERTIVE_PATTERN = re.compile(
    r"(?:^|[.!?…;:])[^.!?…;:]*\b(?:nếu|giả\s+(?:sử|như)|liệu|"
    r"phải\s+chăng|có\s+lẽ|có\s+thể|dường\s+như|hình\s+như|"
    r"nghe\s+(?:nói|bảo)|(?:nghĩ|tưởng|tin|nghi\s+ngờ|nói|kể|bảo)"
    r"(?:\s+rằng)?)\b",
    flags=re.IGNORECASE,
)
ANALYSIS_HOST_SLEEP_PARALYSIS_RESOLVED_PATTERN = re.compile(
    r"\b(?:(?:không|chẳng)\s+còn\s+(?:bị\s+)?bóng\s+đè|"
    r"(?:đã|vừa)\s+(?:thoát|tỉnh)(?:\s+ra|\s+dậy)?|"
    r"(?:giờ|nay)\s+(?:đã\s+)?(?:thoát|tỉnh|cử\s+động|điều\s+khiển))\b",
    flags=re.IGNORECASE,
)
ANALYSIS_HOST_SLEEP_PARALYSIS_META_PATTERN = re.compile(
    r"\b(?:dòng\s+chữ|từ|cụm\s+từ|khái\s+niệm|thuật\s+ngữ|"
    r"câu\s+chuyện|đoạn\s+văn)\b",
    flags=re.IGNORECASE,
)
ANALYSIS_HOST_SLEEP_PARALYSIS_NEGATED_STATE_PATTERN = re.compile(
    r"\b(?:không|chẳng)\s+phải\s+(?:là\s+)?(?:đang\s+)?(?:bị\s+)?"
    r"bóng\s+đè\b",
    flags=re.IGNORECASE,
)
ANALYSIS_HOST_SLEEP_PARALYSIS_AFFECT_CONTRADICTION_PATTERN = re.compile(
    r"\b(?:(?:không|chẳng)\s+(?:hề\s+)?(?:(?:cảm\s+)?thấy\s+)?"
    r"(?:sợ\s+hãi|lo\s+sợ|kinh\s+hãi|hoảng\s+sợ)|"
    r"(?:không|chẳng)\s+có\s+(?:một\s+)?chút\s+"
    r"(?:sợ\s+hãi|lo\s+sợ)(?:\s+nào)?|"
    r"(?:vẫn\s+(?:hoàn\s+toàn\s+)?|hoàn\s+toàn\s+)"
    r"(?:bình\s+tĩnh|điềm\s+tĩnh))\b",
    flags=re.IGNORECASE,
)
ANALYSIS_HOST_SLEEP_PARALYSIS_DENIED_AFFECT_PREFIX_PATTERN = re.compile(
    r"\b(?:không|chẳng)\s+(?:hề\s+)?"
    r"(?:(?:(?:cảm\s+)?thấy)\s+|(?:có\s+(?:một\s+)?chút)\s+)?$",
    flags=re.IGNORECASE,
)
ANALYSIS_HOST_SLEEP_PARALYSIS_EXPERIENCER_PATTERN = re.compile(
    rf"\b{ANALYSIS_HOST_DIRECT_AFFECT_SUBJECT_PATTERN}\b",
    flags=re.IGNORECASE,
)
ANALYSIS_HOST_SLEEP_PARALYSIS_CALM_ASSERTION_PATTERN = re.compile(
    rf"\b{ANALYSIS_HOST_DIRECT_AFFECT_SUBJECT_PATTERN}\s+"
    r"(?:(?:vẫn|hoàn\s+toàn)\s+){0,2}(?:bình\s+tĩnh|điềm\s+tĩnh)\b",
    flags=re.IGNORECASE,
)
ANALYSIS_HOST_SLEEP_TO_AWARENESS_BRIDGE_PATTERN = re.compile(
    r"\s*(?:trước\s+đây\s*)?,?\s*",
    flags=re.IGNORECASE,
)
ANALYSIS_HOST_AWARENESS_TO_DESIRE_BRIDGE_PATTERN = re.compile(
    r"\s*,?\s*",
)
ANALYSIS_HOST_DESIRE_TO_MOTOR_BRIDGE_PATTERN = re.compile(
    r"\s*,?\s*(?:nhưng|song)\s+(?:lại\s+)?"
    r"(?:không\s+có\s+sức\s+lực\s*,\s*)?",
    flags=re.IGNORECASE,
)
ANALYSIS_SCOPED_NEGATION_PREFIX_PATTERN = re.compile(
    r"(?:\b(?:không|chẳng|chưa)"
    r"(?:\s+(?:còn|hề|bao\s+giờ|từng|hoàn\s+toàn)){0,2}"
    r"|\bhết)\s*$",
    flags=re.IGNORECASE,
)
ANALYSIS_SCOPED_ASSERTION_PREFIX_PATTERN = re.compile(
    r"(?:\b(?:không|chẳng)\s+"
    r"(?:(?:thể|phải|được(?:\s+phép)?)\s+)?(?:không|chẳng)"
    r"|\b(?:không|chẳng|chưa)\s+(?:hết|khỏi|ngừng))\s*$",
    flags=re.IGNORECASE,
)
ANALYSIS_SCOPED_PROHIBITION_PREFIX_PATTERN = re.compile(
    r"\b(?:đừng|chớ|không\s+được(?:\s+phép)?)"
    r"(?:\s+(?:bao\s+giờ|vội|có)){0,2}\s*$",
    flags=re.IGNORECASE,
)
ANALYSIS_SCOPED_NEGATION_SUFFIX_PATTERN = re.compile(
    r"^\s+(?:(?:đã|hoàn\s+toàn)\s+){0,2}"
    r"(?:hết|tan\s+biến|biến\s+mất|không\s+còn(?:\s+nữa)?|chẳng\s+còn(?:\s+nữa)?)\b",
    flags=re.IGNORECASE,
)
ANALYSIS_SCOPED_HISTORICAL_PREFIX_PATTERN = re.compile(
    r"\b(?:đã\s+từng|từng)\s*$",
    flags=re.IGNORECASE,
)
ANALYSIS_SCOPED_META_PREFIX_PATTERN = re.compile(
    r"\b(?:dòng\s+chữ|từ|cụm\s+từ|khái\s+niệm|thuật\s+ngữ)\s+[\"“‘']?\s*$",
    flags=re.IGNORECASE,
)
ANALYSIS_SCOPED_META_SUFFIX_PATTERN = re.compile(
    r"^\s*[\"”’']?\s+(?:là\s+một\s+(?:danh|tính|động)\s+từ|được\s+định\s+nghĩa)\b",
    flags=re.IGNORECASE,
)
ANALYSIS_SCOPED_NEGATION_CONJUNCTION_PATTERN = re.compile(
    r"^\s*(?:và|hay|hoặc)\s*$",
    flags=re.IGNORECASE,
)
ANALYSIS_MIXED_AFFECT_BRIDGE_PATTERN = re.compile(
    r"^\s*,?\s*(?:"
    r"(?:và|nhưng|song)(?:\s+(?:vẫn|cũng|lại|rất|vô\s+cùng)){0,2}"
    r"|(?:lại\s+)?vừa"
    r"|(?:xen\s+lẫn|đan\s+xen)(?:\s+(?:với|niềm|nỗi))?"
    r"|(?:và\s+)?cùng\s+lúc|đồng\s+thời"
    r")\s*$",
    flags=re.IGNORECASE,
)
ANALYSIS_AFRAID_CUE_PATTERN = re.compile(
    r"\b(?:sợ\s+hãi|lo\s+sợ|kinh\s+hãi|sợ\s+cực\s+độ|hoảng(?:\s+loạn|\s+sợ)?|"
    r"run\s+rẩy|trắng\s+bệch|dự\s+cảm\s+xấu|bất\s+an|hốt\s+hoảng|cuống\s+quýt|"
    r"sẽ\s+chết\s+mất|sắp\s+chết(?:\s+mất|\s+thôi)|kinh\s+hoàng|"
    r"tim\s+đập\s+chân\s+run|tim\s+thắt)\b",
    flags=re.IGNORECASE,
)
ANALYSIS_SAD_CUE_PATTERN = re.compile(
    r"\b(?:khóc|nước\s+mắt|đau\s+lòng|tuyệt\s+vọng|đau\s+đớn|kêu\s+thảm\s+thiết)\b",
    flags=re.IGNORECASE,
)
ANALYSIS_ANGRY_CUE_PATTERN = re.compile(
    r"\b(?:độc\s+ác|khốn\s+kiếp|đáng\s+chết|nguyền\s+rủa|gào\s+thét|gào|quát|"
    r"chửi\s+rủa|thiêu\s+chết(?!\s*(?:…|\.{3}))|"
    r"thiêu(?:\s+[^\s.,!?;:…“”‘’]+){0,5}\s+đi|"
    r"giết(?:\s+[^\s.,!?;:…“”‘’]+){0,5}\s+đi|tan\s+nát)\b",
    flags=re.IGNORECASE,
)
ANALYSIS_SURPRISED_CUE_PATTERN = re.compile(
    r"\b(?:kinh\s+ngạc|sững\s+sờ|đực\s+mặt|không\s+thể\s+tin)\b",
    flags=re.IGNORECASE,
)
ANALYSIS_DISTRESSED_CUE_PATTERN = re.compile(
    r"\b(?:choáng\s+váng|yếu\s+nhược|mềm\s+nhũn|sắp\s+ngã|bệnh\s+nặng|tồi\s+tàn)\b",
    flags=re.IGNORECASE,
)
ANALYSIS_DISORIENTED_CUE_PATTERN = re.compile(
    r"\b(?:thất\s+thần|bàng\s+hoàng|hỗn\s+loạn)\b",
    flags=re.IGNORECASE,
)
ANALYSIS_ACTIVE_PRIDE_CUE_FRAGMENT = (
    r"tràn\s+ngập\s+vẻ\s+(?:tự\s+hào|hãnh\s+diện|kiêu\s+hãnh)"
    r"|lấp\s+lánh\s+niềm\s+(?:tự\s+hào|hãnh\s+diện|kiêu\s+hãnh)"
)
ANALYSIS_HAPPY_CUE_PATTERN = re.compile(
    r"\b(?:vui\s+mừng(?:\s+rỡ)?|vui(?:\s+vẻ|\s+sướng)?|mừng(?:\s+rỡ)?|"
    r"hạnh\s+phúc|hân\s+hoan|nhẹ\s+nhõm|sung\s+sướng|khoái\s+chí|"
    rf"{ANALYSIS_ACTIVE_PRIDE_CUE_FRAGMENT})\b",
    flags=re.IGNORECASE,
)
ANALYSIS_EXCITED_CUE_PATTERN = re.compile(
    r"\b(?:phấn\s+khích|háo\s+hức|nôn\s+nóng)\b",
    flags=re.IGNORECASE,
)
ANALYSIS_OTHER_AFFECT_CUE_PATTERNS = (
    ANALYSIS_ANGRY_CUE_PATTERN,
    ANALYSIS_SURPRISED_CUE_PATTERN,
    ANALYSIS_DISTRESSED_CUE_PATTERN,
    ANALYSIS_DISORIENTED_CUE_PATTERN,
    ANALYSIS_HAPPY_CUE_PATTERN,
    ANALYSIS_EXCITED_CUE_PATTERN,
)
ANALYSIS_NON_AFRAID_CUE_PATTERNS = (
    ANALYSIS_SAD_CUE_PATTERN,
    *ANALYSIS_OTHER_AFFECT_CUE_PATTERNS,
)
ANALYSIS_HOST_AFFECT_CUE_PATTERNS = {
    "afraid": ANALYSIS_AFRAID_CUE_PATTERN,
    "angry": ANALYSIS_ANGRY_CUE_PATTERN,
    "disoriented": ANALYSIS_DISORIENTED_CUE_PATTERN,
    "distressed": ANALYSIS_DISTRESSED_CUE_PATTERN,
    "excited": ANALYSIS_EXCITED_CUE_PATTERN,
    "happy": ANALYSIS_HAPPY_CUE_PATTERN,
    "sad": ANALYSIS_SAD_CUE_PATTERN,
    "surprised": ANALYSIS_SURPRISED_CUE_PATTERN,
}
ANALYSIS_DIRECT_NEUTRAL_AFFECT_CUES = frozenset(
    {"afraid", "angry", "excited", "happy", "sad", "surprised"}
)
ANALYSIS_NEGATIVE_AFFECT_CUES = frozenset(
    {"afraid", "angry", "disoriented", "distressed", "sad"}
)
ANALYSIS_POSITIVE_AFFECT_CUES = frozenset({"excited", "happy"})
ANALYSIS_SEMANTIC_REJECTED_EMOTIONS = ("neutral",)
ANALYSIS_HOST_CRITIC_COMPATIBILITY_RULE = (
    "disoriented_low_arousal_candidate_compatibility"
)
ANALYSIS_HOST_CRITIC_COMPATIBILITY_FIELDS = ("emotion", "intensity", "pace")
ANALYSIS_HOST_CRITIC_UNSUPPORTED_EMOTIONS = frozenset({"afraid"})


def canonical_analysis_note(
    data: dict[str, Any],
    markers: Sequence[str] = (),
) -> str:
    if not isinstance(data, dict):
        raise ValueError("Analysis delivery note data must be an object")
    missing = [field for field in ANALYSIS_DELIVERY_NOTE_FIELDS if field not in data]
    if missing:
        raise ValueError(
            "Analysis delivery note is missing fields: " + ", ".join(missing)
        )
    kind = data["kind"]
    emotion = data["emotion"]
    intensity = data["intensity"]
    pace = data["pace"]
    volume = data["volume"]
    if not isinstance(kind, str) or kind not in ANALYSIS_CRITIC_KINDS:
        raise ValueError(f"Unsupported analysis delivery note kind: {kind}")
    if not isinstance(emotion, str) or emotion not in ANALYSIS_CRITIC_EMOTIONS:
        raise ValueError(f"Unsupported analysis delivery note emotion: {emotion}")
    if type(intensity) is not int or not 0 <= intensity <= 3:
        raise ValueError("Analysis delivery note intensity must be an integer from 0 to 3")
    if not isinstance(pace, str) or pace not in ANALYSIS_CRITIC_PACES:
        raise ValueError(f"Unsupported analysis delivery note pace: {pace}")
    if not isinstance(volume, str) or volume not in ANALYSIS_CRITIC_VOLUMES:
        raise ValueError(f"Unsupported analysis delivery note volume: {volume}")
    if isinstance(markers, (str, bytes)):
        raise ValueError("Analysis delivery note markers must be a sequence")
    marker_values = tuple(markers)
    if any(not isinstance(marker, str) for marker in marker_values):
        raise ValueError("Analysis delivery note markers must be strings")
    unknown_markers = set(marker_values) - set(ANALYSIS_HOST_NOTE_MARKERS)
    if unknown_markers:
        raise ValueError("Analysis delivery note contains an unrecognized host marker")
    payload = {
        "kind": kind,
        "emotion": emotion,
        "intensity": intensity,
        "pace": pace,
        "volume": volume,
    }
    note = ANALYSIS_DELIVERY_NOTE_PREFIX + json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    )
    ordered_markers = tuple(
        marker for marker in ANALYSIS_HOST_NOTE_MARKERS if marker in marker_values
    )
    return "; ".join((note, *ordered_markers))


def analysis_note_markers(data: dict[str, Any]) -> tuple[str, ...]:
    if data.get("personality_hint") != "":
        raise ValueError("Analysis personality_hint must be empty")
    note = data.get("notes")
    if not isinstance(note, str):
        raise ValueError("Analysis notes must be a canonical delivery note")
    base_note = canonical_analysis_note(data)
    if note == base_note:
        return ()
    marker_prefix = f"{base_note}; "
    if not note.startswith(marker_prefix):
        raise ValueError("Analysis notes must use the canonical delivery note contract")
    markers = tuple(note[len(marker_prefix):].split("; "))
    if (
        not markers
        or any(not marker for marker in markers)
        or len(markers) != len(set(markers))
        or canonical_analysis_note(data, markers) != note
    ):
        raise ValueError(
            "Analysis notes may contain only ordered recognized host markers"
        )
    return markers


def _analysis_source_match_is_suppressed(text: str, match: re.Match[str]) -> bool:
    prefix = text[: match.start()]
    suffix = text[match.end() :]
    asserted_double_negative = (
        ANALYSIS_SCOPED_ASSERTION_PREFIX_PATTERN.search(prefix) is not None
    )
    return bool(
        (
            ANALYSIS_SCOPED_NEGATION_PREFIX_PATTERN.search(prefix) is not None
            and not asserted_double_negative
        )
        or ANALYSIS_SCOPED_PROHIBITION_PREFIX_PATTERN.search(prefix) is not None
        or ANALYSIS_SCOPED_NEGATION_SUFFIX_PATTERN.search(suffix) is not None
        or ANALYSIS_SCOPED_HISTORICAL_PREFIX_PATTERN.search(prefix) is not None
        or ANALYSIS_SCOPED_META_PREFIX_PATTERN.search(prefix) is not None
        or ANALYSIS_SCOPED_META_SUFFIX_PATTERN.search(suffix) is not None
    )


def _analysis_source_active_affect_matches(
    text: str,
) -> dict[str, re.Match[str]]:
    candidates = sorted(
        (
            (match.start(), -match.end(), label, match)
            for label, pattern in ANALYSIS_HOST_AFFECT_CUE_PATTERNS.items()
            for match in pattern.finditer(text)
        ),
        key=lambda item: (item[0], item[1], item[2]),
    )
    active: dict[str, re.Match[str]] = {}
    last_suppressed_end: int | None = None
    for _start, _negative_end, label, match in candidates:
        suppressed = _analysis_source_match_is_suppressed(text, match)
        if not suppressed and last_suppressed_end is not None:
            bridge = text[last_suppressed_end : match.start()]
            suppressed = (
                ANALYSIS_SCOPED_NEGATION_CONJUNCTION_PATTERN.fullmatch(bridge)
                is not None
            )
        if suppressed:
            last_suppressed_end = match.end()
            continue
        last_suppressed_end = None
        active.setdefault(label, match)
    return active


def analysis_direct_affect_rejected_emotions(source_text: str) -> tuple[str, ...]:
    """Return only delivery values deterministically rejected by active direct cues."""
    if not isinstance(source_text, str):
        raise ValueError("Analysis direct-affect source text must be a string")
    cue_matches = _analysis_source_active_affect_matches(source_text)
    if (
        _analysis_source_has_active_physical_pair(source_text)
        or not (set(cue_matches) & ANALYSIS_DIRECT_NEUTRAL_AFFECT_CUES)
    ):
        return ()
    negative_matches = [
        cue_matches[label]
        for label in ANALYSIS_NEGATIVE_AFFECT_CUES
        if label in cue_matches
    ]
    positive_matches = [
        cue_matches[label]
        for label in ANALYSIS_POSITIVE_AFFECT_CUES
        if label in cue_matches
    ]
    for negative_match in negative_matches:
        for positive_match in positive_matches:
            first, second = sorted(
                (negative_match, positive_match),
                key=lambda match: match.start(),
            )
            bridge = source_text[first.end() : second.start()]
            if ANALYSIS_MIXED_AFFECT_BRIDGE_PATTERN.fullmatch(bridge) is not None:
                return ()
    return ANALYSIS_SEMANTIC_REJECTED_EMOTIONS


def canonical_analysis_rejected_emotion_contract(
    rejected_emotions_by_id: Sequence[Mapping[str, Any]] | None,
) -> list[dict[str, Any]]:
    """Return the canonical per-ID emotion exclusions that define a critic epoch."""
    raw_items = [] if rejected_emotions_by_id is None else rejected_emotions_by_id
    if isinstance(raw_items, (str, bytes)) or not isinstance(raw_items, Sequence):
        raise ValueError("Analysis rejected-emotion contract must be a sequence")
    canonical: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in raw_items:
        if not isinstance(item, Mapping) or set(item) != {"id", "emotions"}:
            raise ValueError("Analysis rejected-emotion contract item is invalid")
        batch_id = item.get("id")
        emotions = item.get("emotions")
        if (
            not isinstance(batch_id, str)
            or re.fullmatch(r"S[0-9]+", batch_id) is None
            or batch_id in seen
            or isinstance(emotions, (str, bytes))
            or not isinstance(emotions, Sequence)
            or tuple(emotions) != ANALYSIS_SEMANTIC_REJECTED_EMOTIONS
        ):
            raise ValueError("Analysis rejected-emotion contract item is invalid")
        seen.add(batch_id)
        canonical.append(
            {
                "id": batch_id,
                "emotions": list(ANALYSIS_SEMANTIC_REJECTED_EMOTIONS),
            }
        )
    if [item["id"] for item in canonical] != sorted(seen):
        raise ValueError("Analysis rejected-emotion contract IDs are not canonical")
    return canonical


def analysis_critic_speaker_is_candidate_bound(
    critic_speaker: Any,
    candidate_speakers: Sequence[Any],
) -> bool:
    """Require every critic speaker identity to originate in its visible batch."""
    if not isinstance(critic_speaker, str):
        return False
    allowed = {
        speaker
        for speaker in candidate_speakers
        if isinstance(speaker, str) and speaker.strip()
    }
    allowed.update(ANALYSIS_CRITIC_RESERVED_SPEAKERS)
    return critic_speaker in allowed


def canonical_analysis_critic_allowed_speakers(
    critic_rows: Sequence[Mapping[str, Any]],
) -> tuple[str, ...]:
    """Return the exact candidate/reserved speaker enum for a critic request."""
    if isinstance(critic_rows, (str, bytes)) or not isinstance(
        critic_rows,
        Sequence,
    ) or not critic_rows:
        raise ValueError("Analysis critic rows must be a non-empty sequence")
    candidate_speakers: list[str] = []
    for row in critic_rows:
        candidate = row.get("candidate") if isinstance(row, Mapping) else None
        speaker = candidate.get("speaker") if isinstance(candidate, Mapping) else None
        if (
            not isinstance(speaker, str)
            or not speaker.strip()
            or len(speaker) > 120
        ):
            raise ValueError("Analysis critic candidate speaker is invalid")
        candidate_speakers.append(speaker)
    allowed = {*candidate_speakers, *ANALYSIS_CRITIC_RESERVED_SPEAKERS}
    return tuple(sorted(allowed))


def analysis_critic_candidate_hash(
    critic_rows: Sequence[Mapping[str, Any]],
    rejected_emotions_by_id: Sequence[Mapping[str, Any]] | None = None,
) -> str:
    """Hash the critic-visible projection and any retry schema that changes its meaning."""
    canonical_rejections = canonical_analysis_rejected_emotion_contract(
        rejected_emotions_by_id
    )
    critic_rows_json = json.dumps(
        list(critic_rows),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    if not canonical_rejections:
        return sha256_text(critic_rows_json)
    return sha256_text(
        json.dumps(
            {
                "projection_hash": sha256_text(critic_rows_json),
                "rejected_emotions_by_id": canonical_rejections,
                "schema_policy_version": ANALYSIS_DIRECTOR_RETRY_SCHEMA_POLICY_VERSION,
                "subject_hash_version": ANALYSIS_CRITIC_SUBJECT_HASH_VERSION,
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    )


def analysis_expected_critic_compatibility_override(
    *,
    stable_id: str,
    source_text: str,
    text_sha256: str,
    source_kind: str,
    candidate: dict[str, Any],
    critic: dict[str, Any],
    raw_deltas: list[str],
) -> dict[str, Any] | None:
    """Return the one conservative source-bound override allowed for critic dissent."""
    if (
        not stable_id
        or sha256_text(source_text) != text_sha256
        or any(mark in source_text for mark in ("?", "？", "!", "！"))
        or source_kind != "narration"
        or candidate.get("kind") != "narration"
        or candidate.get("speaker") != "NARRATOR"
        or candidate.get("emotion") != "neutral"
        or type(candidate.get("intensity")) is not int
        or candidate["intensity"] not in {0, 1}
        or candidate.get("pace") != "normal"
        or candidate.get("volume") != "normal"
    ):
        return None
    cue_matches = _analysis_source_active_affect_matches(source_text)
    if set(cue_matches) != {"disoriented"}:
        return None
    # The full field list on purpose. This builds a compatibility override, which exists
    # precisely to resolve an affect delta and rejects itself below if "emotion" is
    # absent - filtering affect out here would make every override impossible to create
    # and impossible to re-validate, including those already committed in a project from
    # before the policy changed.
    raw_delta_fields = [
        field
        for field in ANALYSIS_CRITIC_DELIVERY_FIELDS
        if critic.get(field) != candidate.get(field)
    ]
    if (
        not raw_delta_fields
        or "emotion" not in raw_delta_fields
        or len(raw_delta_fields) < 2
        or not set(raw_delta_fields) <= set(ANALYSIS_HOST_CRITIC_COMPATIBILITY_FIELDS)
        or critic.get("emotion") not in ANALYSIS_HOST_CRITIC_UNSUPPORTED_EMOTIONS
        or (
            "intensity" in raw_delta_fields
            and (
                type(critic.get("intensity")) is not int
                or critic["intensity"] <= candidate["intensity"]
            )
        )
        or ("pace" in raw_delta_fields and critic.get("pace") != "fast")
    ):
        return None
    expected_raw_deltas = [
        f"{field}:{candidate[field]}->{critic[field]}"
        for field in ANALYSIS_CRITIC_DELIVERY_FIELDS
        if critic.get(field) != candidate.get(field)
    ]
    if raw_deltas != expected_raw_deltas:
        return None
    cue_match = cue_matches["disoriented"]
    return {
        "policy_version": ANALYSIS_HOST_CRITIC_COMPATIBILITY_POLICY_VERSION,
        "stable_id": stable_id,
        "text_sha256": text_sha256,
        "rule": ANALYSIS_HOST_CRITIC_COMPATIBILITY_RULE,
        "source_cue_class": "disoriented",
        "source_cue_quote": cue_match.group(0),
        "candidate_values": {
            field: candidate[field]
            for field in ANALYSIS_HOST_CRITIC_COMPATIBILITY_FIELDS
        },
        "critic_values": {
            field: critic[field]
            for field in ANALYSIS_HOST_CRITIC_COMPATIBILITY_FIELDS
        },
        "raw_accept": False,
        "raw_field_deltas": raw_deltas,
        "covered_field_deltas": raw_deltas,
        "unresolved_field_deltas": [],
    }


def _analysis_source_has_narrow_direct_affect(
    text: str,
    *,
    pattern: re.Pattern[str],
    cue_class: str,
    allowed_outer_prefix_patterns: tuple[re.Pattern[str], ...] = (),
    allowed_suffix_patterns: tuple[re.Pattern[str], ...] = (),
) -> bool:
    if any(
        character in text
        for character in (
            *ANALYSIS_HOST_DIRECT_AFFECT_QUOTE_CHARACTERS,
            *ANALYSIS_HOST_DIRECT_AFFECT_QUESTION_CHARACTERS,
        )
    ):
        return False
    matches = list(pattern.finditer(text))
    if len(matches) != 1:
        return False
    match = matches[0]
    outer_prefix = text[: match.start()]
    if (
        ANALYSIS_HOST_DIRECT_AFFECT_SENTENCE_START_PREFIX_PATTERN.search(
            outer_prefix
        )
        is None
        and not any(
            prefix_pattern.search(outer_prefix) is not None
            for prefix_pattern in allowed_outer_prefix_patterns
        )
    ):
        return False
    suffix = text[match.end() :]
    if (
        ANALYSIS_HOST_DIRECT_AFFECT_TERMINAL_SUFFIX_PATTERN.fullmatch(suffix)
        is None
        and not any(
            suffix_pattern.fullmatch(suffix) is not None
            for suffix_pattern in allowed_suffix_patterns
        )
    ):
        return False
    if _analysis_source_match_is_suppressed(text, match):
        return False
    return set(_analysis_source_active_affect_matches(text)) == {cue_class}


def analysis_source_has_recalled_persistent_fear(text: str) -> bool:
    """Return whether narration directly asserts a still-active recalled fear."""
    return _analysis_source_has_narrow_direct_affect(
        text,
        pattern=ANALYSIS_HOST_RECALLED_PERSISTENT_FEAR_PATTERN,
        cue_class="afraid",
        allowed_outer_prefix_patterns=(
            ANALYSIS_HOST_RECALLED_PERSISTENT_FEAR_PREFIX_PATTERN,
        ),
        allowed_suffix_patterns=(
            ANALYSIS_HOST_RECALLED_PERSISTENT_FEAR_SUFFIX_PATTERN,
        ),
    )


def analysis_source_has_stunned_blank_mind(text: str) -> bool:
    """Return whether narration directly pairs a stunned stare with a blank mind."""
    return _analysis_source_has_narrow_direct_affect(
        text,
        pattern=ANALYSIS_HOST_STUNNED_BLANK_MIND_PATTERN,
        cue_class="surprised",
        allowed_outer_prefix_patterns=(
            ANALYSIS_HOST_STUNNED_BLANK_MIND_PREFIX_PATTERN,
        ),
    )


def analysis_source_has_sleep_paralysis_helplessness(text: str) -> bool:
    """Return whether one source row asserts lucid sleep-paralysis helplessness."""
    if (
        not isinstance(text, str)
        or any(
            character in text
            for character in (
                *ANALYSIS_HOST_DIRECT_AFFECT_QUOTE_CHARACTERS,
                *ANALYSIS_HOST_DIRECT_AFFECT_QUESTION_CHARACTERS,
            )
        )
        or ANALYSIS_HOST_SLEEP_PARALYSIS_NONASSERTIVE_PATTERN.search(text) is not None
        or ANALYSIS_HOST_SLEEP_PARALYSIS_RESOLVED_PATTERN.search(text) is not None
        or ANALYSIS_HOST_SLEEP_PARALYSIS_META_PATTERN.search(text) is not None
        or ANALYSIS_HOST_SLEEP_PARALYSIS_NEGATED_STATE_PATTERN.search(text)
        is not None
        or ANALYSIS_HOST_SLEEP_PARALYSIS_AFFECT_CONTRADICTION_PATTERN.search(text)
        is not None
        or ANALYSIS_HOST_SLEEP_PARALYSIS_CALM_ASSERTION_PATTERN.search(text)
        is not None
        or any(
            _analysis_source_match_is_suppressed(text, match)
            or ANALYSIS_HOST_SLEEP_PARALYSIS_DENIED_AFFECT_PREFIX_PATTERN.search(
                text[: match.start()]
            )
            is not None
            for match in ANALYSIS_AFRAID_CUE_PATTERN.finditer(text)
        )
    ):
        return False
    pattern_matches: list[re.Match[str]] = []
    for pattern in (
        ANALYSIS_HOST_SLEEP_PARALYSIS_PATTERN,
        ANALYSIS_HOST_DREAM_AWARENESS_PATTERN,
        ANALYSIS_HOST_DESIRE_ESCAPE_PATTERN,
        ANALYSIS_HOST_MOTOR_HELPLESSNESS_PATTERN,
    ):
        matches = list(pattern.finditer(text))
        if len(matches) != 1:
            return False
        pattern_matches.append(matches[0])
    if [match.start() for match in pattern_matches] != sorted(
        match.start() for match in pattern_matches
    ):
        return False
    sleep_match, awareness_match, desire_match, motor_match = pattern_matches
    if (
        ANALYSIS_HOST_DIRECT_AFFECT_TERMINAL_SUFFIX_PATTERN.fullmatch(
            text[motor_match.end() :]
        )
        is None
    ):
        return False
    awareness_subject = ANALYSIS_HOST_SLEEP_PARALYSIS_EXPERIENCER_PATTERN.search(
        awareness_match.group(0)
    )
    if awareness_subject is None:
        return False
    normalized_subject = " ".join(awareness_subject.group(0).casefold().split())
    normalized_sleep_prefix = " ".join(
        text[: sleep_match.start()].casefold().split()
    )
    if normalized_sleep_prefix not in {
        "giống như mấy lần",
        normalized_subject,
        f"giống như {normalized_subject}",
    }:
        return False
    subject_bridges = (
        text[sleep_match.end() : awareness_match.start()],
        text[awareness_match.end() : desire_match.start()],
        text[desire_match.end() : motor_match.start()],
    )
    if not all(
        pattern.fullmatch(bridge) is not None
        for pattern, bridge in zip(
            (
                ANALYSIS_HOST_SLEEP_TO_AWARENESS_BRIDGE_PATTERN,
                ANALYSIS_HOST_AWARENESS_TO_DESIRE_BRIDGE_PATTERN,
                ANALYSIS_HOST_DESIRE_TO_MOTOR_BRIDGE_PATTERN,
            ),
            subject_bridges,
            strict=True,
        )
    ):
        return False
    if any(
        " ".join(subject.group(0).casefold().split()) != normalized_subject
        for bridge in subject_bridges
        for subject in ANALYSIS_HOST_SLEEP_PARALYSIS_EXPERIENCER_PATTERN.finditer(
            bridge
        )
    ):
        return False
    if any(
        _analysis_source_match_is_suppressed(text, match)
        for match in pattern_matches[:-1]
    ):
        return False
    return set(_analysis_source_active_affect_matches(text)) <= {"afraid"}


def _analysis_source_has_physical_collapse(text: str) -> bool:
    respiratory = ANALYSIS_PHYSICAL_RESPIRATORY_INJURY_PATTERN.search(text)
    consciousness = ANALYSIS_PHYSICAL_CONSCIOUSNESS_LOSS_PATTERN.search(text)
    physical_match = bool(
        respiratory is not None
        and consciousness is not None
        and not _analysis_source_match_is_suppressed(text, respiratory)
        and not _analysis_source_match_is_suppressed(text, consciousness)
    )
    if not physical_match:
        return False
    for pattern in (ANALYSIS_AFRAID_CUE_PATTERN, *ANALYSIS_NON_AFRAID_CUE_PATTERNS):
        for other_match in pattern.finditer(text):
            if not _analysis_source_match_is_suppressed(text, other_match):
                return False
    return True


def _analysis_source_has_desperate_exertion(text: str) -> bool:
    if (
        any(
            character in text
            for character in ANALYSIS_HOST_DESPERATE_EXERTION_QUOTE_CHARACTERS
        )
        or text.rstrip().endswith("?")
    ):
        return False
    matches = list(ANALYSIS_HOST_DESPERATE_EXERTION_PATTERN.finditer(text))
    if len(matches) != 1:
        return False
    if ANALYSIS_HOST_DESPERATE_EXERTION_NONASSERTIVE_PREFIX_PATTERN.search(
        text[: matches[0].start()]
    ) is not None:
        return False
    if _analysis_source_match_is_suppressed(text, matches[0]):
        return False
    active_matches = _analysis_source_active_affect_matches(text)
    if set(active_matches) != {"sad"}:
        return False
    respiratory = ANALYSIS_PHYSICAL_RESPIRATORY_INJURY_PATTERN.search(text)
    consciousness = ANALYSIS_PHYSICAL_CONSCIOUSNESS_LOSS_PATTERN.search(text)
    return not (
        respiratory is not None
        and consciousness is not None
        and not _analysis_source_match_is_suppressed(text, respiratory)
        and not _analysis_source_match_is_suppressed(text, consciousness)
    )


def _analysis_source_has_active_physical_pair(text: str) -> bool:
    respiratory = ANALYSIS_PHYSICAL_RESPIRATORY_INJURY_PATTERN.search(text)
    consciousness = ANALYSIS_PHYSICAL_CONSCIOUSNESS_LOSS_PATTERN.search(text)
    return bool(
        respiratory is not None
        and consciousness is not None
        and not _analysis_source_match_is_suppressed(text, respiratory)
        and not _analysis_source_match_is_suppressed(text, consciousness)
    )


def _analysis_source_has_self_preservation_mortality(text: str) -> bool:
    matches = list(ANALYSIS_HOST_MORTALITY_PATTERN.finditer(text))
    if len(matches) != 1:
        return False
    match = matches[0]
    if _analysis_source_match_is_suppressed(text, match):
        return False
    experiencers = list(ANALYSIS_HOST_EXPERIENCER_PATTERN.finditer(text[: match.start()]))
    if experiencers:
        nearest = " ".join(experiencers[-1].group(0).casefold().split())
        if nearest not in ANALYSIS_HOST_SELF_EXPERIENCERS:
            return False
    elif ANALYSIS_HOST_SUBJECTLESS_SELF_CONTROL_PATTERN.fullmatch(text) is None:
        return False
    afraid_matches = [
        afraid_match
        for afraid_match in ANALYSIS_AFRAID_CUE_PATTERN.finditer(text)
        if not _analysis_source_match_is_suppressed(text, afraid_match)
    ]
    if not afraid_matches:
        return False
    prefix = text[: match.start()]
    cognition = ANALYSIS_HOST_MORTALITY_COGNITION_PREFIX_PATTERN.search(prefix)
    if (
        cognition is not None
        and ANALYSIS_HOST_MORTALITY_RESOLVED_COGNITION_PREFIX_PATTERN.search(
            prefix[: cognition.end()]
        )
        is not None
    ):
        return False
    for pattern in ANALYSIS_NON_AFRAID_CUE_PATTERNS:
        for other_match in pattern.finditer(text):
            if not _analysis_source_match_is_suppressed(text, other_match):
                return False
    return not _analysis_source_has_active_physical_pair(text)


def _analysis_source_matches_host_semantic_rule(text: str, rule: str) -> bool:
    if rule == "thought_self_preservation_mortality":
        return _analysis_source_has_self_preservation_mortality(text)
    if rule == "adjacent_thought_wake_self_rescue":
        return ANALYSIS_HOST_WAKE_PATTERN.fullmatch(text) is not None
    if rule == "respiratory_injury_with_consciousness_loss":
        return _analysis_source_has_physical_collapse(text)
    if rule == "narration_desperate_exertion":
        return _analysis_source_has_desperate_exertion(text)
    if rule == "narration_recalled_persistent_fear":
        return analysis_source_has_recalled_persistent_fear(text)
    if rule == "narration_stunned_blank_mind":
        return analysis_source_has_stunned_blank_mind(text)
    if rule == "narration_sleep_paralysis_helplessness":
        return analysis_source_has_sleep_paralysis_helplessness(text)
    return False


SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS book (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    title TEXT NOT NULL,
    project_root TEXT NOT NULL,
    settings_hash TEXT NOT NULL,
    settings_json TEXT NOT NULL,
    status TEXT NOT NULL,
    stage TEXT NOT NULL DEFAULT 'created',
    input_manifest_hash TEXT NOT NULL,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    last_error TEXT,
    run_generation INTEGER NOT NULL DEFAULT 0,
    casting_finalized INTEGER NOT NULL DEFAULT 0,
    analysis_model_name TEXT,
    analysis_model_digest TEXT,
    analysis_model_locked_at REAL,
    CHECK (
        (analysis_model_name IS NULL AND analysis_model_digest IS NULL AND analysis_model_locked_at IS NULL)
        OR (analysis_model_name IS NOT NULL AND analysis_model_digest IS NOT NULL
            AND analysis_model_locked_at IS NOT NULL)
    )
);

CREATE TABLE IF NOT EXISTS chapters (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chapter_index INTEGER NOT NULL UNIQUE,
    title TEXT NOT NULL,
    input_path TEXT NOT NULL,
    input_sha256 TEXT NOT NULL,
    input_size INTEGER NOT NULL,
    output_mp3 TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    total_segments INTEGER NOT NULL DEFAULT 0,
    verified_segments INTEGER NOT NULL DEFAULT 0,
    warning_segments INTEGER NOT NULL DEFAULT 0,
    failed_segments INTEGER NOT NULL DEFAULT 0,
    started_at REAL,
    completed_at REAL,
    last_error TEXT
);

CREATE TABLE IF NOT EXISTS segments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    stable_id TEXT NOT NULL UNIQUE,
    chapter_id INTEGER NOT NULL REFERENCES chapters(id) ON DELETE CASCADE,
    seq INTEGER NOT NULL,
    paragraph_index INTEGER NOT NULL DEFAULT 0,
    break_ms INTEGER NOT NULL DEFAULT 220,
    text TEXT NOT NULL,
    text_sha256 TEXT NOT NULL,
    kind_hint TEXT NOT NULL,
    kind TEXT NOT NULL DEFAULT 'narration',
    speaker TEXT NOT NULL DEFAULT 'NARRATOR',
    canonical_character_id INTEGER REFERENCES characters(id),
    gender TEXT NOT NULL DEFAULT 'unknown',
    age TEXT NOT NULL DEFAULT 'unknown',
    emotion TEXT NOT NULL DEFAULT 'neutral',
    intensity INTEGER NOT NULL DEFAULT 1,
    pace TEXT NOT NULL DEFAULT 'normal',
    volume TEXT NOT NULL DEFAULT 'normal',
    confidence REAL NOT NULL DEFAULT 0.5,
    analysis_notes TEXT NOT NULL DEFAULT '',
    voice_profile_id INTEGER REFERENCES voice_profiles(id),
    status TEXT NOT NULL DEFAULT 'pending',
    attempt_count INTEGER NOT NULL DEFAULT 0,
    generation_seed INTEGER,
    generation_frame_cap INTEGER CHECK(
        generation_frame_cap IS NULL OR generation_frame_cap > 0
    ),
    generation_delivery_mode TEXT NOT NULL DEFAULT 'primary' CHECK(
        generation_delivery_mode IN ('primary','clarity')
    ),
    generation_repair_round INTEGER CHECK(
        generation_repair_round IS NULL OR generation_repair_round >= 0
    ),
    generation_policy_hash TEXT,
    wav_path TEXT,
    wav_sha256 TEXT,
    wav_duration REAL,
    signal_json TEXT,
    asr_text TEXT,
    asr_similarity REAL,
    asr_wer REAL,
    warning_code TEXT,
    error TEXT,
    updated_at REAL NOT NULL,
    UNIQUE(chapter_id, seq)
);

CREATE TABLE IF NOT EXISTS characters (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    canonical_name TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL,
    gender TEXT NOT NULL DEFAULT 'unknown',
    age TEXT NOT NULL DEFAULT 'unknown',
    personality TEXT NOT NULL DEFAULT '',
    importance TEXT NOT NULL DEFAULT 'minor',
    mention_count INTEGER NOT NULL DEFAULT 0,
    confidence REAL NOT NULL DEFAULT 0.5,
    locked INTEGER NOT NULL DEFAULT 0,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS character_aliases (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    character_id INTEGER NOT NULL REFERENCES characters(id) ON DELETE CASCADE,
    alias TEXT NOT NULL,
    normalized_alias TEXT NOT NULL UNIQUE,
    confidence REAL NOT NULL DEFAULT 0.5,
    source TEXT NOT NULL DEFAULT 'analysis'
);

CREATE TABLE IF NOT EXISTS pronunciations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    surface TEXT NOT NULL,
    normalized_surface TEXT NOT NULL UNIQUE,
    spoken_form TEXT NOT NULL,
    confidence REAL NOT NULL DEFAULT 0.5,
    source TEXT NOT NULL DEFAULT 'analysis',
    locked INTEGER NOT NULL DEFAULT 0,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS voice_profiles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    voice_key TEXT NOT NULL UNIQUE,
    engine TEXT NOT NULL,
    preset_name TEXT,
    description TEXT NOT NULL DEFAULT '',
    seed INTEGER NOT NULL,
    pitch_semitones INTEGER NOT NULL DEFAULT 0,
    -- Frequency-axis scale for the spectral envelope. Below 1 enlarges the apparent
    -- vocal tract and reads deeper; above 1 shrinks it and reads brighter. This is what
    -- makes two characters sound like different people - pitch alone does not, because
    -- speaker identity lives in the formants.
    formant_ratio REAL NOT NULL DEFAULT 1.0,
    status TEXT NOT NULL DEFAULT 'planned',
    locked INTEGER NOT NULL DEFAULT 1,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS artifacts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    artifact_key TEXT NOT NULL UNIQUE,
    kind TEXT NOT NULL,
    path TEXT NOT NULL,
    sha256 TEXT,
    size_bytes INTEGER,
    verified INTEGER NOT NULL DEFAULT 0,
    metadata_json TEXT,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS quality_policies (
    policy_hash TEXT PRIMARY KEY,
    policy_version INTEGER NOT NULL,
    policy_json TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 0 CHECK (active IN (0, 1)),
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS quality_checks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scope TEXT NOT NULL CHECK (scope IN ('segment', 'chapter')),
    stage TEXT NOT NULL,
    segment_id INTEGER REFERENCES segments(id) ON DELETE CASCADE,
    chapter_id INTEGER REFERENCES chapters(id) ON DELETE CASCADE,
    artifact_sha256 TEXT NOT NULL,
    policy_hash TEXT NOT NULL REFERENCES quality_policies(policy_hash),
    policy_version INTEGER NOT NULL,
    verdict TEXT NOT NULL CHECK (verdict IN ('pass', 'repair', 'inconclusive', 'fail')),
    metrics_json TEXT NOT NULL DEFAULT '{}',
    failure_codes_json TEXT NOT NULL DEFAULT '[]',
    repair_action TEXT,
    attempt INTEGER NOT NULL DEFAULT 1 CHECK (attempt >= 1),
    created_at REAL NOT NULL,
    CHECK (
        (scope = 'segment' AND segment_id IS NOT NULL AND chapter_id IS NULL)
        OR (scope = 'chapter' AND chapter_id IS NOT NULL AND segment_id IS NULL)
    )
);

CREATE TABLE IF NOT EXISTS segment_candidates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    segment_id INTEGER NOT NULL REFERENCES segments(id) ON DELETE CASCADE,
    policy_hash TEXT NOT NULL REFERENCES quality_policies(policy_hash),
    repair_round INTEGER NOT NULL CHECK (repair_round >= 0),
    repair_budget INTEGER NOT NULL CHECK (repair_budget >= 1),
    incumbent_sha256 TEXT NOT NULL,
    expected_voice_profile_id INTEGER NOT NULL REFERENCES voice_profiles(id),
    expected_pitch_semitones INTEGER NOT NULL,
    pronunciation_delivery_variant TEXT NOT NULL,
    expected_spoken_text_sha256 TEXT NOT NULL,
    state TEXT NOT NULL CHECK (
        state IN (
            'generating','signal_passed','beam_recorded','dual_failed',
            'dual_passed','tts_failed','invalid','promoted'
        )
    ),
    generation_strategy TEXT NOT NULL DEFAULT 'direct_v1' CHECK(
        generation_strategy IN ('direct_v1','split_v1')
    ),
    postprocess_profile TEXT NOT NULL DEFAULT 'none' CHECK(
        postprocess_profile IN ('none','ffmpeg_atempo_0_94_pcm_s16le_v1')
    ),
    postprocess_source_candidate_id INTEGER REFERENCES segment_candidates(id),
    postprocess_source_sha256 TEXT,
    tts_attempt INTEGER NOT NULL DEFAULT 0 CHECK (tts_attempt >= 0),
    generation_seed INTEGER NOT NULL,
    wav_path TEXT NOT NULL UNIQUE,
    wav_sha256 TEXT,
    wav_duration REAL CHECK (wav_duration IS NULL OR wav_duration > 0),
    signal_json TEXT,
    beam_result_json TEXT,
    greedy_result_json TEXT,
    beam_check_id INTEGER REFERENCES quality_checks(id),
    greedy_check_id INTEGER REFERENCES quality_checks(id),
    perceptual_required INTEGER NOT NULL DEFAULT 0 CHECK (perceptual_required IN (0,1)),
    candidate_repair_requirement TEXT NOT NULL DEFAULT 'standard_candidate_gate_v1'
        CHECK (
            candidate_repair_requirement IN (
                'standard_candidate_gate_v1','naturalness_improvement_v1'
            )
        ),
    repair_trigger_check_id INTEGER REFERENCES quality_checks(id),
    perceptual_result_json TEXT,
    perceptual_check_id INTEGER REFERENCES quality_checks(id),
    final_check_id INTEGER REFERENCES quality_checks(id),
    failure_reason TEXT,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    promoted_at REAL,
    UNIQUE(segment_id, policy_hash, repair_round),
    CHECK (
        state IN ('generating','tts_failed')
        OR (
            wav_sha256 IS NOT NULL
            AND wav_duration IS NOT NULL
            AND signal_json IS NOT NULL
        )
    ),
    CHECK (
        (beam_check_id IS NULL AND beam_result_json IS NULL)
        OR (beam_check_id IS NOT NULL AND beam_result_json IS NOT NULL)
    ),
    CHECK (
        (greedy_check_id IS NULL AND greedy_result_json IS NULL)
        OR (greedy_check_id IS NOT NULL AND greedy_result_json IS NOT NULL)
    ),
    CHECK (
        (perceptual_check_id IS NULL AND perceptual_result_json IS NULL)
        OR (perceptual_check_id IS NOT NULL AND perceptual_result_json IS NOT NULL)
    ),
    CHECK (
        (
            postprocess_profile = 'none'
            AND postprocess_source_candidate_id IS NULL
            AND postprocess_source_sha256 IS NULL
        )
        OR (
            postprocess_profile = 'ffmpeg_atempo_0_94_pcm_s16le_v1'
            AND postprocess_source_candidate_id IS NOT NULL
            AND postprocess_source_sha256 IS NOT NULL
        )
    ),
    CHECK (
        (
            candidate_repair_requirement = 'standard_candidate_gate_v1'
            AND repair_trigger_check_id IS NULL
        )
        OR (
            candidate_repair_requirement = 'naturalness_improvement_v1'
            AND repair_trigger_check_id IS NOT NULL
            AND perceptual_required = 1
        )
    ),
    CHECK (
        state NOT IN ('beam_recorded','dual_failed','dual_passed','promoted')
        OR beam_check_id IS NOT NULL
    ),
    CHECK (
        state NOT IN ('dual_failed','dual_passed','promoted')
        OR greedy_check_id IS NOT NULL
    ),
    CHECK (
        (state = 'promoted' AND promoted_at IS NOT NULL AND final_check_id IS NOT NULL)
        OR (state <> 'promoted' AND promoted_at IS NULL)
    )
);

CREATE TABLE IF NOT EXISTS analysis_candidates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    policy_fingerprint TEXT NOT NULL,
    model_name TEXT NOT NULL,
    model_digest TEXT NOT NULL,
    group_fingerprint TEXT NOT NULL,
    context_hash TEXT NOT NULL,
    candidate_hash TEXT NOT NULL,
    candidate_json TEXT NOT NULL,
    envelope_hash TEXT NOT NULL,
    commit_envelope_json TEXT,
    commit_envelope_hash TEXT,
    state TEXT NOT NULL CHECK (
        state IN (
            'allocated','critic_in_flight','critic_invalid','critic_accepted',
            'critic_rejected','accepted','terminal','superseded'
        )
    ),
    initial_generator_contract_json TEXT NOT NULL,
    initial_generator_contract_hash TEXT NOT NULL,
    deterministic_issue_json TEXT NOT NULL,
    deterministic_issue_hash TEXT NOT NULL,
    critic_attempt_count INTEGER NOT NULL DEFAULT 0 CHECK (critic_attempt_count >= 0),
    critic_max_attempts INTEGER NOT NULL CHECK (critic_max_attempts >= 1),
    terminal_reason TEXT,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    accepted_at REAL,
    UNIQUE(
        policy_fingerprint,model_name,model_digest,group_fingerprint,context_hash,candidate_hash
    ),
    CHECK (critic_attempt_count <= critic_max_attempts),
    CHECK (
        (commit_envelope_json IS NULL AND commit_envelope_hash IS NULL)
        OR (commit_envelope_json IS NOT NULL AND commit_envelope_hash IS NOT NULL)
    ),
    CHECK (
        state NOT IN ('critic_accepted','accepted') OR commit_envelope_json IS NOT NULL
    ),
    CHECK (
        (state = 'accepted' AND accepted_at IS NOT NULL)
        OR (state <> 'accepted' AND accepted_at IS NULL)
    ),
    CHECK (
        state NOT IN ('terminal','superseded') OR terminal_reason IS NOT NULL
    )
);

CREATE TABLE IF NOT EXISTS analysis_candidate_generator_contracts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    analysis_candidate_id INTEGER NOT NULL
        REFERENCES analysis_candidates(id) ON DELETE CASCADE,
    generator_contract_hash TEXT NOT NULL,
    generator_contract_json TEXT NOT NULL,
    first_seen_at REAL NOT NULL,
    last_seen_at REAL NOT NULL,
    occurrence_count INTEGER NOT NULL DEFAULT 1 CHECK (occurrence_count >= 1),
    UNIQUE(analysis_candidate_id,generator_contract_hash)
);

CREATE TABLE IF NOT EXISTS analysis_critic_attempts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    analysis_candidate_id INTEGER NOT NULL
        REFERENCES analysis_candidates(id) ON DELETE CASCADE,
    attempt_number INTEGER NOT NULL CHECK (attempt_number >= 1),
    state TEXT NOT NULL CHECK (state IN ('reserved','completed','abandoned')),
    intent_json TEXT NOT NULL,
    intent_hash TEXT NOT NULL,
    contract_json TEXT NOT NULL,
    contract_hash TEXT NOT NULL,
    outcome_json TEXT,
    outcome_hash TEXT,
    evidence_json TEXT,
    evidence_hash TEXT,
    completion_hash TEXT,
    reserved_at REAL NOT NULL,
    completed_at REAL,
    UNIQUE(analysis_candidate_id,attempt_number),
    CHECK (
        (state = 'reserved' AND completed_at IS NULL AND outcome_json IS NULL
            AND outcome_hash IS NULL AND evidence_json IS NULL AND evidence_hash IS NULL
            AND completion_hash IS NULL)
        OR (state = 'completed' AND completed_at IS NOT NULL AND outcome_json IS NOT NULL
            AND outcome_hash IS NOT NULL AND evidence_json IS NOT NULL
            AND evidence_hash IS NOT NULL AND completion_hash IS NOT NULL)
        OR (state = 'abandoned' AND completed_at IS NOT NULL AND outcome_json IS NULL
            AND outcome_hash IS NULL AND evidence_json IS NULL AND evidence_hash IS NULL
            AND completion_hash IS NULL)
    )
);

CREATE TABLE IF NOT EXISTS runtime_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp REAL NOT NULL,
    level TEXT NOT NULL,
    code TEXT NOT NULL,
    message TEXT NOT NULL,
    details_json TEXT
);

CREATE TABLE IF NOT EXISTS worker_leases (
    worker_name TEXT PRIMARY KEY,
    pid INTEGER NOT NULL,
    generation INTEGER NOT NULL,
    state TEXT NOT NULL,
    heartbeat_at REAL NOT NULL,
    current_item TEXT,
    metadata_json TEXT
);

CREATE INDEX IF NOT EXISTS idx_segments_chapter_status ON segments(chapter_id, status, seq);
CREATE INDEX IF NOT EXISTS idx_segments_status ON segments(status);
CREATE INDEX IF NOT EXISTS idx_segments_speaker ON segments(speaker);
CREATE INDEX IF NOT EXISTS idx_runtime_events_time ON runtime_events(timestamp);
CREATE UNIQUE INDEX IF NOT EXISTS idx_quality_policies_active
    ON quality_policies(active) WHERE active = 1;
CREATE INDEX IF NOT EXISTS idx_quality_checks_segment
    ON quality_checks(segment_id, stage, policy_hash, id);
CREATE INDEX IF NOT EXISTS idx_quality_checks_chapter
    ON quality_checks(chapter_id, stage, policy_hash, id);
CREATE INDEX IF NOT EXISTS idx_segment_candidates_resume
    ON segment_candidates(segment_id, policy_hash, state, repair_round);
CREATE INDEX IF NOT EXISTS idx_analysis_candidates_exact
    ON analysis_candidates(
        policy_fingerprint,model_name,model_digest,group_fingerprint,context_hash,candidate_hash
    );
CREATE UNIQUE INDEX IF NOT EXISTS idx_analysis_candidates_actionable_scope
    ON analysis_candidates(
        policy_fingerprint,model_name,model_digest,group_fingerprint,context_hash
    )
    WHERE state IN ('allocated','critic_in_flight','critic_invalid','critic_accepted');
CREATE INDEX IF NOT EXISTS idx_analysis_critic_attempts_candidate
    ON analysis_critic_attempts(analysis_candidate_id,attempt_number);
"""


class ProjectDB:
    def __init__(self, path: Path, synchronous: str = "FULL") -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.synchronous = synchronous.upper()
        if self.synchronous not in {"OFF", "NORMAL", "FULL", "EXTRA"}:
            raise ValueError(f"Unsupported SQLite synchronous mode: {synchronous}")
        with self.connect() as conn:
            schema_version = int(conn.execute("PRAGMA user_version").fetchone()[0])
            if schema_version > SCHEMA_VERSION:
                raise RuntimeError(
                    f"Project schema version {schema_version} is newer than supported version "
                    f"{SCHEMA_VERSION}"
                )
            has_user_tables = bool(
                conn.execute(
                    """
                    SELECT 1 FROM sqlite_master
                    WHERE type='table' AND name NOT LIKE 'sqlite_%'
                    LIMIT 1
                    """
                ).fetchone()
            )
            if has_user_tables and schema_version < SCHEMA_VERSION:
                self._create_migration_backup(conn, schema_version)
            conn.executescript(SCHEMA)
            conn.execute("BEGIN IMMEDIATE")
            try:
                self._migrate_schema(conn)
                conn.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
                conn.execute("COMMIT")
            except Exception:
                conn.execute("ROLLBACK")
                raise

    def _migration_backup_path(self, source_version: int) -> Path:
        return self.path.with_name(
            f"{self.path.name}.pre-v{source_version}-to-v{SCHEMA_VERSION}.bak"
        )

    def _create_migration_backup(
        self,
        conn: sqlite3.Connection,
        source_version: int,
    ) -> Path:
        backup_path = self._migration_backup_path(source_version)
        if backup_path.exists():
            return backup_path
        temp = backup_path.with_name(backup_path.name + ".part")
        temp.unlink(missing_ok=True)
        try:
            backup = sqlite3.connect(temp)
            try:
                conn.backup(backup)
                result = backup.execute("PRAGMA integrity_check").fetchone()
                if result is None or str(result[0]).casefold() != "ok":
                    raise RuntimeError("SQLite migration backup failed integrity_check")
            finally:
                backup.close()
            os.replace(temp, backup_path)
            return backup_path
        finally:
            temp.unlink(missing_ok=True)

    @staticmethod
    def _migrate_schema(conn: sqlite3.Connection) -> None:
        segment_columns = {str(row[1]) for row in conn.execute("PRAGMA table_info(segments)")}
        if "break_ms" not in segment_columns:
            conn.execute("ALTER TABLE segments ADD COLUMN break_ms INTEGER NOT NULL DEFAULT 220")
        if "generation_frame_cap" not in segment_columns:
            conn.execute(
                """
                ALTER TABLE segments ADD COLUMN generation_frame_cap INTEGER
                CHECK(generation_frame_cap IS NULL OR generation_frame_cap > 0)
                """
            )
        if "generation_delivery_mode" not in segment_columns:
            conn.execute(
                """
                ALTER TABLE segments ADD COLUMN generation_delivery_mode TEXT
                NOT NULL DEFAULT 'primary'
                CHECK(generation_delivery_mode IN ('primary','clarity'))
                """
            )
        if "generation_repair_round" not in segment_columns:
            conn.execute(
                """
                ALTER TABLE segments ADD COLUMN generation_repair_round INTEGER
                CHECK(generation_repair_round IS NULL OR generation_repair_round >= 0)
                """
            )
        if "generation_policy_hash" not in segment_columns:
            conn.execute("ALTER TABLE segments ADD COLUMN generation_policy_hash TEXT")

        voice_columns = {
            str(row[1]) for row in conn.execute("PRAGMA table_info(voice_profiles)")
        }
        if "formant_ratio" not in voice_columns:
            conn.execute(
                "ALTER TABLE voice_profiles ADD COLUMN formant_ratio REAL NOT NULL DEFAULT 1.0"
            )
        book_columns = {str(row[1]) for row in conn.execute("PRAGMA table_info(book)")}
        if "casting_finalized" not in book_columns:
            conn.execute("ALTER TABLE book ADD COLUMN casting_finalized INTEGER NOT NULL DEFAULT 0")
            conn.execute(
                """
                UPDATE book SET casting_finalized=1
                WHERE EXISTS(
                    SELECT 1 FROM segments
                    WHERE voice_profile_id IS NOT NULL
                      AND status IN ('signal_passed','asr_passed','verified','warning','failed')
                )
                """
            )
        if "analysis_model_name" not in book_columns:
            conn.execute("ALTER TABLE book ADD COLUMN analysis_model_name TEXT")
        if "analysis_model_digest" not in book_columns:
            conn.execute("ALTER TABLE book ADD COLUMN analysis_model_digest TEXT")
        if "analysis_model_locked_at" not in book_columns:
            conn.execute("ALTER TABLE book ADD COLUMN analysis_model_locked_at REAL")

        candidate_columns = {
            str(row[1]) for row in conn.execute("PRAGMA table_info(segment_candidates)")
        }
        added_pronunciation_delivery_variant = False
        added_expected_spoken_text_sha256 = False
        added_generation_strategy = False
        if "repair_budget" not in candidate_columns:
            conn.execute(
                "ALTER TABLE segment_candidates ADD COLUMN repair_budget "
                "INTEGER NOT NULL DEFAULT 1 CHECK(repair_budget >= 1)"
            )
            conn.execute(
                "UPDATE segment_candidates SET repair_budget=repair_round + 1"
            )
        if "perceptual_required" not in candidate_columns:
            conn.execute(
                "ALTER TABLE segment_candidates ADD COLUMN perceptual_required "
                "INTEGER NOT NULL DEFAULT 0 CHECK(perceptual_required IN (0,1))"
            )
        if "generation_strategy" not in candidate_columns:
            conn.execute(
                "ALTER TABLE segment_candidates ADD COLUMN generation_strategy "
                f"TEXT NOT NULL DEFAULT '{GENERATION_STRATEGY_DIRECT}' "
                "CHECK(generation_strategy IN "
                f"('{GENERATION_STRATEGY_DIRECT}','{GENERATION_STRATEGY_SPLIT}'))"
            )
            added_generation_strategy = True
        if "postprocess_profile" not in candidate_columns:
            conn.execute(
                "ALTER TABLE segment_candidates ADD COLUMN postprocess_profile "
                f"TEXT NOT NULL DEFAULT '{POSTPROCESS_PROFILE_NONE}' "
                "CHECK(postprocess_profile IN "
                f"('{POSTPROCESS_PROFILE_NONE}','{POSTPROCESS_PROFILE_TEMPO}'))"
            )
        if "postprocess_source_candidate_id" not in candidate_columns:
            conn.execute(
                "ALTER TABLE segment_candidates ADD COLUMN "
                "postprocess_source_candidate_id INTEGER "
                "REFERENCES segment_candidates(id)"
            )
        if "postprocess_source_sha256" not in candidate_columns:
            conn.execute(
                "ALTER TABLE segment_candidates ADD COLUMN "
                "postprocess_source_sha256 TEXT"
            )
        if added_generation_strategy:
            pronunciation_projection = (
                "candidates.pronunciation_delivery_variant"
                if "pronunciation_delivery_variant" in candidate_columns
                else (
                    f"'{PRONUNCIATION_DELIVERY_LOCKED}' "
                    "AS pronunciation_delivery_variant"
                )
            )
            legacy_generation_rows = list(
                conn.execute(
                    f"""
                    SELECT
                        candidates.id,candidates.repair_round,
                        {pronunciation_projection},
                        candidates.generation_seed,candidates.signal_json,
                        segments.stable_id,profiles.voice_key
                    FROM segment_candidates AS candidates
                    JOIN segments ON segments.id=candidates.segment_id
                    JOIN voice_profiles AS profiles
                      ON profiles.id=candidates.expected_voice_profile_id
                    ORDER BY candidates.id
                    """
                )
            )
            for candidate in legacy_generation_rows:
                try:
                    signal = json.loads(str(candidate["signal_json"] or "{}"))
                except (TypeError, json.JSONDecodeError):
                    signal = {}
                split_fields_present = isinstance(signal, dict) and any(
                    signal.get(field) not in (None, [])
                    for field in (
                        "split_checkpoint_seed",
                        "split_seed_salt_prefix",
                        SPLIT_STRATEGY_FIELD,
                        SPLIT_MAX_CHARS_FIELD,
                        "split_parts",
                    )
                )
                split_seed_salt = segment_candidate_split_seed_salt(
                    int(candidate["repair_round"]),
                    str(candidate["pronunciation_delivery_variant"]),
                )
                expected_split_seed = stable_int(
                    "segment::"
                    f"{candidate['stable_id']}::{candidate['voice_key']}::"
                    f"{split_seed_salt}"
                )
                generation_strategy = (
                    GENERATION_STRATEGY_SPLIT
                    if split_fields_present
                    or int(candidate["generation_seed"]) == expected_split_seed
                    else GENERATION_STRATEGY_DIRECT
                )
                conn.execute(
                    "UPDATE segment_candidates SET generation_strategy=? WHERE id=?",
                    (generation_strategy, int(candidate["id"])),
                )
        if "candidate_repair_requirement" not in candidate_columns:
            conn.execute(
                "ALTER TABLE segment_candidates ADD COLUMN candidate_repair_requirement "
                f"TEXT NOT NULL DEFAULT '{STANDARD_CANDIDATE_GATE_REQUIREMENT}' "
                "CHECK(candidate_repair_requirement IN "
                f"('{STANDARD_CANDIDATE_GATE_REQUIREMENT}',"
                f"'{NATURALNESS_IMPROVEMENT_REQUIREMENT}'))"
            )
        if "repair_trigger_check_id" not in candidate_columns:
            conn.execute(
                "ALTER TABLE segment_candidates ADD COLUMN repair_trigger_check_id "
                "INTEGER REFERENCES quality_checks(id)"
            )
        conn.execute(
            f"""
            CREATE TRIGGER IF NOT EXISTS segment_candidates_repair_binding_insert
            BEFORE INSERT ON segment_candidates
            WHEN NOT (
                (
                    NEW.candidate_repair_requirement =
                        '{STANDARD_CANDIDATE_GATE_REQUIREMENT}'
                    AND NEW.repair_trigger_check_id IS NULL
                )
                OR (
                    NEW.candidate_repair_requirement =
                        '{NATURALNESS_IMPROVEMENT_REQUIREMENT}'
                    AND NEW.repair_trigger_check_id IS NOT NULL
                    AND NEW.perceptual_required = 1
                )
            )
            BEGIN
                SELECT RAISE(ABORT, 'invalid segment candidate repair binding');
            END
            """
        )
        conn.execute(
            f"""
            CREATE TRIGGER IF NOT EXISTS segment_candidates_repair_binding_update
            BEFORE UPDATE ON segment_candidates
            WHEN
                NEW.candidate_repair_requirement IS NOT
                    OLD.candidate_repair_requirement
                OR NEW.repair_trigger_check_id IS NOT OLD.repair_trigger_check_id
                OR NOT (
                    (
                        NEW.candidate_repair_requirement =
                            '{STANDARD_CANDIDATE_GATE_REQUIREMENT}'
                        AND NEW.repair_trigger_check_id IS NULL
                    )
                    OR (
                        NEW.candidate_repair_requirement =
                            '{NATURALNESS_IMPROVEMENT_REQUIREMENT}'
                        AND NEW.repair_trigger_check_id IS NOT NULL
                        AND NEW.perceptual_required = 1
                    )
                )
            BEGIN
                SELECT RAISE(ABORT, 'immutable segment candidate repair binding');
            END
            """
        )
        conn.execute(
            """
            CREATE TRIGGER IF NOT EXISTS segment_candidates_perceptual_required_update
            BEFORE UPDATE OF perceptual_required ON segment_candidates
            WHEN NEW.perceptual_required IS NOT OLD.perceptual_required
            BEGIN
                SELECT RAISE(ABORT, 'immutable segment candidate perceptual requirement');
            END
            """
        )
        conn.execute(
            """
            CREATE TRIGGER IF NOT EXISTS segment_candidates_generation_strategy_update
            BEFORE UPDATE OF generation_strategy ON segment_candidates
            WHEN
                NEW.generation_strategy IS NOT OLD.generation_strategy
                AND NOT (
                    OLD.state = 'generating'
                    AND NEW.state = 'generating'
                    AND OLD.generation_strategy = 'direct_v1'
                    AND NEW.generation_strategy = 'split_v1'
                    AND NEW.tts_attempt = OLD.tts_attempt + 1
                )
            BEGIN
                SELECT RAISE(ABORT, 'invalid segment candidate generation strategy transition');
            END
            """
        )
        conn.execute(
            f"""
            CREATE TRIGGER IF NOT EXISTS segment_candidates_postprocess_binding_insert
            BEFORE INSERT ON segment_candidates
            WHEN NOT (
                (
                    NEW.postprocess_profile = '{POSTPROCESS_PROFILE_NONE}'
                    AND NEW.postprocess_source_candidate_id IS NULL
                    AND NEW.postprocess_source_sha256 IS NULL
                )
                OR (
                    NEW.postprocess_profile = '{POSTPROCESS_PROFILE_TEMPO}'
                    AND NEW.postprocess_source_candidate_id IS NOT NULL
                    AND NEW.postprocess_source_sha256 IS NOT NULL
                )
            )
            BEGIN
                SELECT RAISE(ABORT, 'invalid segment candidate postprocess binding');
            END
            """
        )
        conn.execute(
            f"""
            CREATE TRIGGER IF NOT EXISTS segment_candidates_postprocess_binding_update
            BEFORE UPDATE ON segment_candidates
            WHEN
                NEW.postprocess_profile IS NOT OLD.postprocess_profile
                OR NEW.postprocess_source_candidate_id IS NOT
                    OLD.postprocess_source_candidate_id
                OR NEW.postprocess_source_sha256 IS NOT
                    OLD.postprocess_source_sha256
                OR NOT (
                    (
                        NEW.postprocess_profile = '{POSTPROCESS_PROFILE_NONE}'
                        AND NEW.postprocess_source_candidate_id IS NULL
                        AND NEW.postprocess_source_sha256 IS NULL
                    )
                    OR (
                        NEW.postprocess_profile = '{POSTPROCESS_PROFILE_TEMPO}'
                        AND NEW.postprocess_source_candidate_id IS NOT NULL
                        AND NEW.postprocess_source_sha256 IS NOT NULL
                    )
                )
            BEGIN
                SELECT RAISE(ABORT, 'immutable segment candidate postprocess binding');
            END
            """
        )
        if "perceptual_result_json" not in candidate_columns:
            conn.execute(
                "ALTER TABLE segment_candidates ADD COLUMN perceptual_result_json TEXT"
            )
        if "perceptual_check_id" not in candidate_columns:
            conn.execute(
                "ALTER TABLE segment_candidates ADD COLUMN perceptual_check_id "
                "INTEGER REFERENCES quality_checks(id)"
            )
        if "pronunciation_delivery_variant" not in candidate_columns:
            conn.execute(
                "ALTER TABLE segment_candidates ADD COLUMN pronunciation_delivery_variant "
                f"TEXT NOT NULL DEFAULT '{PRONUNCIATION_DELIVERY_LOCKED}'"
            )
            added_pronunciation_delivery_variant = True
        if "expected_spoken_text_sha256" not in candidate_columns:
            conn.execute(
                "ALTER TABLE segment_candidates ADD COLUMN expected_spoken_text_sha256 "
                "TEXT NOT NULL DEFAULT '0000000000000000000000000000000000000000000000000000000000000000'"
            )
            added_expected_spoken_text_sha256 = True
        if (
            added_pronunciation_delivery_variant
            or added_expected_spoken_text_sha256
        ):
            empty_sha256 = "0" * 64

            def decoded_object(value: Any) -> dict[str, Any] | None:
                try:
                    decoded = json.loads(str(value))
                except (TypeError, json.JSONDecodeError):
                    return None
                return decoded if isinstance(decoded, dict) else None

            def payload_spoken_sha256(payload: dict[str, Any] | None) -> str | None:
                value = str((payload or {}).get("spoken_text_sha256") or "")
                normalized = value.strip().casefold()
                if re.fullmatch(r"[0-9a-f]{64}", normalized):
                    return normalized
                return None

            legacy_rows = list(
                conn.execute(
                    """
                    SELECT
                        candidates.*,
                        segments.signal_json AS incumbent_signal_json,
                        segments.wav_sha256 AS current_segment_sha256
                    FROM segment_candidates AS candidates
                    JOIN segments ON segments.id=candidates.segment_id
                    ORDER BY candidates.id
                    """
                )
            )
            for candidate in legacy_rows:
                signal = decoded_object(candidate["signal_json"])
                incumbent_signal = decoded_object(candidate["incumbent_signal_json"])
                promoted_current_candidate = (
                    str(candidate["state"]) == SEGMENT_CANDIDATE_PROMOTED
                    and str(candidate["wav_sha256"] or "")
                    == str(candidate["current_segment_sha256"] or "")
                )
                if promoted_current_candidate:
                    candidate_spoken_sha256 = payload_spoken_sha256(signal)
                    incumbent_spoken_sha256 = payload_spoken_sha256(
                        incumbent_signal
                    )
                    if (
                        signal is None
                        or incumbent_signal is None
                        or candidate_spoken_sha256 is None
                        or incumbent_spoken_sha256 is None
                        or candidate_spoken_sha256 != incumbent_spoken_sha256
                        or ProjectDB._candidate_signal_immutable_projection(
                            signal,
                            default_pronunciation_variant=(
                                PRONUNCIATION_DELIVERY_LOCKED
                            ),
                        )
                        != ProjectDB._candidate_signal_immutable_projection(
                            incumbent_signal,
                            default_pronunciation_variant=(
                                PRONUNCIATION_DELIVERY_LOCKED
                            ),
                        )
                    ):
                        raise RuntimeError(
                            "promoted legacy candidate signal differs from the live segment"
                        )
                expected_spoken_sha256 = (
                    payload_spoken_sha256(signal)
                    or payload_spoken_sha256(incumbent_signal)
                    or empty_sha256
                )
                stored_variant = str(
                    candidate["pronunciation_delivery_variant"] or ""
                ).strip().casefold()
                pronunciation_variant = (
                    stored_variant
                    if stored_variant in PRONUNCIATION_DELIVERY_VARIANTS
                    else PRONUNCIATION_DELIVERY_LOCKED
                )
                encoded_payloads: dict[str, str | None] = {}
                for field in (
                    "signal_json",
                    "beam_result_json",
                    "greedy_result_json",
                ):
                    payload = decoded_object(candidate[field])
                    if payload is None:
                        encoded_payloads[field] = candidate[field]
                        continue
                    payload.setdefault(
                        "pronunciation_delivery_variant",
                        pronunciation_variant,
                    )
                    encoded_payloads[field] = json.dumps(
                        payload,
                        ensure_ascii=False,
                        sort_keys=True,
                    )
                conn.execute(
                    """
                    UPDATE segment_candidates SET
                        pronunciation_delivery_variant=?,
                        expected_spoken_text_sha256=?,
                        signal_json=?,beam_result_json=?,greedy_result_json=?
                    WHERE id=?
                    """,
                    (
                        pronunciation_variant,
                        expected_spoken_sha256,
                        encoded_payloads["signal_json"],
                        encoded_payloads["beam_result_json"],
                        encoded_payloads["greedy_result_json"],
                        int(candidate["id"]),
                    ),
                )
                for check_id_field in (
                    "beam_check_id",
                    "greedy_check_id",
                    "final_check_id",
                ):
                    check_id = candidate[check_id_field]
                    if check_id is None:
                        continue
                    check = conn.execute(
                        "SELECT metrics_json FROM quality_checks WHERE id=?",
                        (int(check_id),),
                    ).fetchone()
                    metrics = (
                        decoded_object(check["metrics_json"])
                        if check is not None
                        else None
                    )
                    if metrics is None:
                        continue
                    metrics.setdefault(
                        "pronunciation_delivery_variant",
                        pronunciation_variant,
                    )
                    if check_id_field == "final_check_id":
                        metrics.setdefault(
                            "expected_spoken_text_sha256",
                            expected_spoken_sha256,
                        )
                        decode_evidence = metrics.get("decode_evidence")
                        if isinstance(decode_evidence, list):
                            for evidence in decode_evidence:
                                if isinstance(evidence, dict):
                                    evidence.setdefault(
                                        "pronunciation_delivery_variant",
                                        pronunciation_variant,
                                    )
                    conn.execute(
                        "UPDATE quality_checks SET metrics_json=? WHERE id=?",
                        (
                            json.dumps(
                                metrics,
                                ensure_ascii=False,
                                sort_keys=True,
                            ),
                            int(check_id),
                        ),
                    )
                if promoted_current_candidate:
                    incumbent_signal.setdefault(
                        "pronunciation_delivery_variant",
                        pronunciation_variant,
                    )
                    conn.execute(
                        "UPDATE segments SET signal_json=? WHERE id=?",
                        (
                            json.dumps(
                                incumbent_signal,
                                ensure_ascii=False,
                                sort_keys=True,
                            ),
                            int(candidate["segment_id"]),
                        ),
                    )
        candidate_columns = {
            str(row[1]) for row in conn.execute("PRAGMA table_info(segment_candidates)")
        }
        required_candidate_columns = {
            "id",
            "segment_id",
            "policy_hash",
            "repair_round",
            "repair_budget",
            "incumbent_sha256",
            "expected_voice_profile_id",
            "expected_pitch_semitones",
            "pronunciation_delivery_variant",
            "expected_spoken_text_sha256",
            "state",
            "generation_strategy",
            "postprocess_profile",
            "postprocess_source_candidate_id",
            "postprocess_source_sha256",
            "tts_attempt",
            "generation_seed",
            "wav_path",
            "wav_sha256",
            "wav_duration",
            "signal_json",
            "beam_result_json",
            "greedy_result_json",
            "beam_check_id",
            "greedy_check_id",
            "perceptual_required",
            "candidate_repair_requirement",
            "repair_trigger_check_id",
            "perceptual_result_json",
            "perceptual_check_id",
            "final_check_id",
            "failure_reason",
            "created_at",
            "updated_at",
            "promoted_at",
        }
        missing_candidate_columns = required_candidate_columns - candidate_columns
        if missing_candidate_columns:
            raise RuntimeError(
                "segment_candidates schema is incomplete: "
                + ", ".join(sorted(missing_candidate_columns))
            )

        required_analysis_candidate_columns = {
            "id",
            "policy_fingerprint",
            "model_name",
            "model_digest",
            "group_fingerprint",
            "context_hash",
            "candidate_hash",
            "candidate_json",
            "envelope_hash",
            "commit_envelope_json",
            "commit_envelope_hash",
            "state",
            "initial_generator_contract_json",
            "initial_generator_contract_hash",
            "deterministic_issue_json",
            "deterministic_issue_hash",
            "critic_attempt_count",
            "critic_max_attempts",
            "terminal_reason",
            "created_at",
            "updated_at",
            "accepted_at",
        }
        analysis_candidate_columns = {
            str(row[1]) for row in conn.execute("PRAGMA table_info(analysis_candidates)")
        }
        if analysis_candidate_columns and "envelope_hash" not in analysis_candidate_columns:
            conn.execute("ALTER TABLE analysis_candidates ADD COLUMN envelope_hash TEXT")
            conn.execute(
                "UPDATE analysis_candidates SET envelope_hash=candidate_hash "
                "WHERE envelope_hash IS NULL"
            )
        if analysis_candidate_columns and "commit_envelope_json" not in analysis_candidate_columns:
            conn.execute(
                "ALTER TABLE analysis_candidates ADD COLUMN commit_envelope_json TEXT"
            )
        if analysis_candidate_columns and "commit_envelope_hash" not in analysis_candidate_columns:
            conn.execute(
                "ALTER TABLE analysis_candidates ADD COLUMN commit_envelope_hash TEXT"
            )
        analysis_candidate_columns = {
            str(row[1]) for row in conn.execute("PRAGMA table_info(analysis_candidates)")
        }
        missing_analysis_candidate_columns = (
            required_analysis_candidate_columns - analysis_candidate_columns
        )
        if missing_analysis_candidate_columns:
            raise RuntimeError(
                "analysis_candidates schema is incomplete: "
                + ", ".join(sorted(missing_analysis_candidate_columns))
            )
        required_analysis_attempt_columns = {
            "id",
            "analysis_candidate_id",
            "attempt_number",
            "state",
            "intent_json",
            "intent_hash",
            "contract_json",
            "contract_hash",
            "outcome_json",
            "outcome_hash",
            "evidence_json",
            "evidence_hash",
            "completion_hash",
            "reserved_at",
            "completed_at",
        }
        analysis_attempt_columns = {
            str(row[1]) for row in conn.execute("PRAGMA table_info(analysis_critic_attempts)")
        }
        missing_analysis_attempt_columns = (
            required_analysis_attempt_columns - analysis_attempt_columns
        )
        if missing_analysis_attempt_columns:
            raise RuntimeError(
                "analysis_critic_attempts schema is incomplete: "
                + ", ".join(sorted(missing_analysis_attempt_columns))
            )

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path, timeout=60, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout=60000")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute(f"PRAGMA synchronous={self.synchronous}")
        try:
            yield conn
        finally:
            conn.close()

    @contextmanager
    def transaction(self, immediate: bool = True) -> Iterator[sqlite3.Connection]:
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE" if immediate else "BEGIN")
            try:
                yield conn
                conn.execute("COMMIT")
            except Exception:
                conn.execute("ROLLBACK")
                raise

    def initialize_book(
        self,
        *,
        title: str,
        project_root: Path,
        settings: dict[str, Any],
        settings_hash: str,
        input_manifest_hash: str,
    ) -> None:
        now = time.time()
        payload = json.dumps(settings, ensure_ascii=False, sort_keys=True)
        with self.transaction() as conn:
            existing = conn.execute("SELECT * FROM book WHERE id=1").fetchone()
            if existing:
                if existing["settings_hash"] != settings_hash:
                    raise RuntimeError(
                        "Book settings are locked. Resume must use the exact original settings; "
                        "clone the project to change them."
                    )
                if existing["input_manifest_hash"] != input_manifest_hash:
                    raise RuntimeError("Input file list or content changed after this book project was created.")
                return
            conn.execute(
                """
                INSERT INTO book(
                    id,title,project_root,settings_hash,settings_json,status,stage,
                    input_manifest_hash,created_at,updated_at,run_generation
                ) VALUES(1,?,?,?,?,?,?,?,?,?,0)
                """,
                (
                    title,
                    str(project_root.resolve()),
                    settings_hash,
                    payload,
                    BookStatus.CREATED.value,
                    "created",
                    input_manifest_hash,
                    now,
                    now,
                ),
            )

    def book(self) -> sqlite3.Row:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM book WHERE id=1").fetchone()
            if row is None:
                raise RuntimeError("Project database has not been initialized")
            return row

    def update_book(self, *, status: str | None = None, stage: str | None = None, error: str | None = None) -> None:
        fields = ["updated_at=?"]
        params: list[Any] = [time.time()]
        if status is not None:
            fields.append("status=?")
            params.append(status)
        if stage is not None:
            fields.append("stage=?")
            params.append(stage)
        if error is not None or status == BookStatus.COMPLETED.value:
            fields.append("last_error=?")
            params.append(error)
        params.append(1)
        with self.connect() as conn:
            conn.execute(f"UPDATE book SET {', '.join(fields)} WHERE id=?", params)

    def begin_run_generation(self) -> int:
        with self.transaction() as conn:
            conn.execute(
                "UPDATE book SET run_generation=run_generation+1, updated_at=? WHERE id=1",
                (time.time(),),
            )
            return int(conn.execute("SELECT run_generation FROM book WHERE id=1").fetchone()[0])

    def casting_is_finalized(self) -> bool:
        return bool(int(self.book()["casting_finalized"]))

    def analysis_model_lock(self) -> dict[str, Any] | None:
        book = self.book()
        model_name = str(book["analysis_model_name"] or "").strip()
        model_digest = str(book["analysis_model_digest"] or "").strip()
        locked_at = book["analysis_model_locked_at"]
        if not model_name and not model_digest and locked_at is None:
            return None
        if not model_name or not model_digest or locked_at is None:
            raise RuntimeError("Analysis model lock is incomplete")
        return {
            "model_name": model_name,
            "model_digest": model_digest,
            "locked_at": float(locked_at),
        }

    def lock_analysis_model(self, model_name: str, model_digest: str) -> None:
        normalized_name = str(model_name).strip()
        normalized_digest = str(model_digest).strip()
        if not normalized_name or not normalized_digest:
            raise ValueError("Analysis model name and digest must be non-empty")
        with self.transaction() as conn:
            row = conn.execute(
                "SELECT analysis_model_name,analysis_model_digest,analysis_model_locked_at "
                "FROM book WHERE id=1"
            ).fetchone()
            if row is None:
                raise RuntimeError("Project database has not been initialized")
            locked_name = str(row["analysis_model_name"] or "").strip()
            locked_digest = str(row["analysis_model_digest"] or "").strip()
            locked_at = row["analysis_model_locked_at"]
            if not locked_name and not locked_digest and locked_at is None:
                conn.execute(
                    "UPDATE book SET analysis_model_name=?,analysis_model_digest=?,"
                    "analysis_model_locked_at=?,updated_at=? WHERE id=1",
                    (normalized_name, normalized_digest, time.time(), time.time()),
                )
                return
            if not locked_name or not locked_digest or locked_at is None:
                raise RuntimeError("Analysis model lock is incomplete")
            if locked_name != normalized_name or locked_digest != normalized_digest:
                raise RuntimeError(
                    "Analysis model differs from the model name/digest locked for this book"
                )

    def finalize_casting(self) -> None:
        with self.connect() as conn:
            conn.execute(
                "UPDATE book SET casting_finalized=1,stage='voice_cast_locked',updated_at=? WHERE id=1",
                (time.time(),),
            )

    def ensure_chapters(self, rows: Sequence[dict[str, Any]]) -> list[int]:
        ids: list[int] = []
        with self.transaction() as conn:
            for row in rows:
                existing = conn.execute(
                    "SELECT * FROM chapters WHERE chapter_index=?", (int(row["chapter_index"]),)
                ).fetchone()
                if existing:
                    if existing["input_sha256"] != row["input_sha256"]:
                        raise RuntimeError(f"Chapter source changed: {row['input_path']}")
                    ids.append(int(existing["id"]))
                    continue
                cursor = conn.execute(
                    """
                    INSERT INTO chapters(
                        chapter_index,title,input_path,input_sha256,input_size,output_mp3,status
                    ) VALUES(?,?,?,?,?,?,?)
                    """,
                    (
                        int(row["chapter_index"]),
                        str(row["title"]),
                        str(Path(row["input_path"]).resolve()),
                        str(row["input_sha256"]),
                        int(row["input_size"]),
                        str(Path(row["output_mp3"]).resolve()),
                        ChapterStatus.PENDING.value,
                    ),
                )
                ids.append(int(cursor.lastrowid))
        return ids

    def list_chapters(self) -> list[sqlite3.Row]:
        with self.connect() as conn:
            return list(conn.execute("SELECT * FROM chapters ORDER BY chapter_index"))

    def chapter_progress_counts(self) -> dict[int, dict[str, int]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT chapter_id,
                    SUM(CASE WHEN status <> 'pending' OR voice_profile_id IS NOT NULL THEN 1 ELSE 0 END)
                        AS analyzed,
                    SUM(CASE WHEN wav_path IS NOT NULL THEN 1 ELSE 0 END) AS audio
                FROM segments
                GROUP BY chapter_id
                """
            )
            return {
                int(row["chapter_id"]): {
                    "analysis": int(row["analyzed"] or 0),
                    "audio": int(row["audio"] or 0),
                }
                for row in rows
            }

    def update_chapter_status(self, chapter_id: int, status: str, error: str | None = None) -> None:
        now = time.time()
        with self.connect() as conn:
            if status == ChapterStatus.SYNTHESIZING.value:
                conn.execute(
                    "UPDATE chapters SET status=?, started_at=COALESCE(started_at,?), last_error=? WHERE id=?",
                    (status, now, error, chapter_id),
                )
            elif status == ChapterStatus.COMPLETED.value:
                conn.execute(
                    "UPDATE chapters SET status=?, completed_at=?, last_error=NULL WHERE id=?",
                    (status, now, chapter_id),
                )
            else:
                conn.execute(
                    "UPDATE chapters SET status=?, last_error=? WHERE id=?", (status, error, chapter_id)
                )

    def replace_chapter_segments(self, chapter_id: int, rows: Sequence[dict[str, Any]]) -> None:
        now = time.time()
        with self.transaction() as conn:
            existing_count = int(
                conn.execute("SELECT COUNT(*) FROM segments WHERE chapter_id=?", (chapter_id,)).fetchone()[0]
            )
            if existing_count:
                return
            conn.executemany(
                """
                INSERT INTO segments(
                    stable_id,chapter_id,seq,paragraph_index,break_ms,text,text_sha256,kind_hint,
                    kind,speaker,gender,age,emotion,intensity,pace,volume,confidence,
                    analysis_notes,status,updated_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                [
                    (
                        row["stable_id"],
                        chapter_id,
                        int(row["seq"]),
                        int(row.get("paragraph_index", 0)),
                        int(row.get("break_ms", 220)),
                        row["text"],
                        row["text_sha256"],
                        row.get("kind_hint", "narration"),
                        row.get("kind", row.get("kind_hint", "narration")),
                        row.get("speaker", "NARRATOR"),
                        row.get("gender", "unknown"),
                        row.get("age", "unknown"),
                        row.get("emotion", "neutral"),
                        int(row.get("intensity", 1)),
                        row.get("pace", "normal"),
                        row.get("volume", "normal"),
                        float(row.get("confidence", 0.5)),
                        row.get("analysis_notes", ""),
                        row.get("status", SegmentStatus.PENDING.value),
                        now,
                    )
                    for row in rows
                ],
            )
            conn.execute(
                "UPDATE chapters SET total_segments=?, status=? WHERE id=?",
                (len(rows), ChapterStatus.PENDING.value, chapter_id),
            )

    def list_segments(
        self,
        chapter_id: int | None = None,
        statuses: Sequence[str] | None = None,
    ) -> list[sqlite3.Row]:
        clauses: list[str] = []
        params: list[Any] = []
        if chapter_id is not None:
            clauses.append("chapter_id=?")
            params.append(chapter_id)
        if statuses:
            marks = ",".join("?" for _ in statuses)
            clauses.append(f"status IN ({marks})")
            params.extend(statuses)
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        with self.connect() as conn:
            return list(conn.execute(f"SELECT * FROM segments{where} ORDER BY chapter_id,seq", params))

    def get_segment(self, segment_id: int) -> sqlite3.Row:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM segments WHERE id=?", (segment_id,)).fetchone()
        if row is None:
            raise KeyError(f"Unknown segment id: {segment_id}")
        return row

    @staticmethod
    def _merge_warning_codes(existing: str | None, warning_code: str | None) -> str | None:
        values = [value for value in str(existing or "").split("|") if value]
        for value in str(warning_code or "").split("|"):
            if value and value not in values:
                values.append(value)
        return "|".join(values) or None

    @staticmethod
    def _without_audio_attempt_warnings(existing: str | None) -> str | None:
        values = []
        for value in str(existing or "").split("|"):
            if not value:
                continue
            if value == "SEGMENT_FAILED" or value == "NON_SPEAKABLE_SEGMENT":
                continue
            if (
                value.startswith("TTS_")
                or value.startswith("ASR_")
                or value.startswith("PERCEPTUAL_")
            ):
                continue
            values.append(value)
        return "|".join(values) or None

    @staticmethod
    def _without_asr_warnings(existing: str | None) -> str | None:
        values = [
            value
            for value in str(existing or "").split("|")
            if value and not value.startswith("ASR_")
        ]
        return "|".join(values) or None

    @staticmethod
    def _without_perceptual_warnings(existing: str | None) -> str | None:
        values = [
            value
            for value in str(existing or "").split("|")
            if value and not value.startswith("PERCEPTUAL_")
        ]
        return "|".join(values) or None

    @staticmethod
    def _canonical_analysis_json(value: Any, label: str) -> tuple[str, str]:
        try:
            payload = json.dumps(
                value,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            )
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{label} must be finite canonical JSON") from exc
        return payload, sha256_text(payload)

    @staticmethod
    def _analysis_critic_evidence_contract(
        candidate_json: str,
    ) -> tuple[str, str, str, int]:
        try:
            candidate = json.loads(candidate_json)
        except json.JSONDecodeError as exc:
            raise RuntimeError("Analysis critic evidence candidate JSON is invalid") from exc
        critic_rows = candidate.get("critic_rows") if isinstance(candidate, dict) else None
        if not isinstance(critic_rows, list) or not critic_rows:
            raise RuntimeError("Analysis critic evidence candidate rows are incomplete")
        if len(critic_rows) == 1:
            source_text = critic_rows[0].get("text")
            if isinstance(source_text, str) and 1 <= len(source_text):
                evidence_text_sha256 = sha256_text(source_text)
                if len(source_text) > ANALYSIS_CRITIC_EVIDENCE_QUOTE_MAX_LENGTH:
                    anchors = canonical_analysis_critic_source_anchors(source_text)
                    return (
                        ANALYSIS_CRITIC_EVIDENCE_POLICY_SINGLETON_SOURCE_ANCHOR,
                        evidence_text_sha256,
                        analysis_critic_anchor_set_sha256(anchors),
                        len(anchors),
                    )
                return (
                    ANALYSIS_CRITIC_EVIDENCE_POLICY_SINGLETON_FULL_TARGET,
                    evidence_text_sha256,
                    "",
                    0,
                )
        anchor_map = canonical_analysis_critic_per_id_source_anchor_map(critic_rows)
        return (
            ANALYSIS_CRITIC_EVIDENCE_POLICY_PER_ID_SOURCE_ANCHOR,
            "",
            analysis_critic_per_id_anchor_map_sha256(anchor_map),
            sum(len(item["anchors"]) for item in anchor_map),
        )

    @staticmethod
    def _analysis_critic_rejected_emotion_contract(
        candidate_json: str,
    ) -> list[dict[str, Any]]:
        try:
            candidate = json.loads(candidate_json)
        except json.JSONDecodeError as exc:
            raise RuntimeError("Analysis critic schema candidate JSON is invalid") from exc
        critic_rows = candidate.get("critic_rows") if isinstance(candidate, dict) else None
        if not isinstance(critic_rows, list) or not critic_rows:
            raise RuntimeError("Analysis critic schema candidate rows are incomplete")
        rejected: list[dict[str, Any]] = []
        for row in critic_rows:
            if not isinstance(row, dict):
                raise RuntimeError("Analysis critic schema candidate row is invalid")
            batch_id = row.get("id")
            source_text = row.get("text")
            if not isinstance(batch_id, str) or not isinstance(source_text, str):
                raise RuntimeError("Analysis critic schema candidate binding is invalid")
            emotions = analysis_direct_affect_rejected_emotions(source_text)
            if emotions:
                rejected.append(
                    {
                        "id": batch_id,
                        "emotions": list(emotions),
                    }
                )
        return rejected

    @classmethod
    def _analysis_generator_rejected_emotion_contract(
        cls,
        candidate_json: str,
        generator_contract: dict[str, Any],
        *,
        durable: bool,
    ) -> list[dict[str, Any]]:
        error_type = RuntimeError if durable else ValueError
        if not isinstance(generator_contract, dict):
            raise error_type("Analysis generator contract must be an object")
        try:
            canonical = canonical_analysis_rejected_emotion_contract(
                generator_contract.get("rejected_emotions_by_id")
            )
        except ValueError as exc:
            raise error_type(
                "Analysis generator contract has invalid retry rejection fields"
            ) from exc
        source_bound = {
            str(item["id"]): list(item["emotions"])
            for item in cls._analysis_critic_rejected_emotion_contract(candidate_json)
        }
        if any(
            source_bound.get(str(item["id"])) != item["emotions"]
            for item in canonical
        ):
            raise error_type(
                "Analysis generator retry rejection schema is not source-bound"
            )
        return canonical

    @classmethod
    def _validate_analysis_critic_generator_rejections(
        cls,
        *,
        candidate_json: str,
        generator_contract_json: str,
        critic_contract: dict[str, Any],
        durable: bool,
    ) -> None:
        error_type = RuntimeError if durable else ValueError
        try:
            generator_contract = json.loads(generator_contract_json)
        except json.JSONDecodeError as exc:
            raise error_type("Analysis generator contract JSON is invalid") from exc
        if not isinstance(generator_contract, dict):
            raise error_type("Analysis generator contract must be an object")
        generator_rejections = cls._analysis_generator_rejected_emotion_contract(
            candidate_json,
            generator_contract,
            durable=durable,
        )
        try:
            critic_rejections = canonical_analysis_rejected_emotion_contract(
                critic_contract.get("rejected_emotions_by_id")
            )
        except ValueError as exc:
            raise error_type(
                "Analysis critic contract has invalid retry rejection fields"
            ) from exc
        if critic_rejections != generator_rejections:
            raise error_type(
                "Analysis critic retry schema differs from its generator rejection contract"
            )

    @classmethod
    def _analysis_critic_confidence_bounds(
        cls,
        contract: dict[str, Any],
        *,
        durable: bool,
        candidate_json: str | None = None,
    ) -> tuple[float, float]:
        error_type = RuntimeError if durable else ValueError
        confidence_floor = contract.get("confidence_floor")
        confidence_cap = contract.get("confidence_cap")
        if (
            contract.get("policy_version")
            != ANALYSIS_DIRECTOR_CRITIC_POLICY_VERSION
            or contract.get("director_policy_version")
            != ANALYSIS_DIRECTOR_CRITIC_POLICY_VERSION
        ):
            raise error_type(
                "Analysis critic contract does not use the current director policy"
            )
        schema_policy_version = contract.get("schema_policy_version")
        rejected_emotions_by_id = contract.get("rejected_emotions_by_id")
        rejected_ids: list[str] = []
        if isinstance(rejected_emotions_by_id, list):
            for item in rejected_emotions_by_id:
                if not isinstance(item, dict) or set(item) != {"id", "emotions"}:
                    break
                batch_id = item.get("id")
                emotions = item.get("emotions")
                if (
                    not isinstance(batch_id, str)
                    or re.fullmatch(r"S[0-9]+", batch_id) is None
                    or not isinstance(emotions, list)
                    or tuple(emotions) != ANALYSIS_SEMANTIC_REJECTED_EMOTIONS
                ):
                    break
                rejected_ids.append(batch_id)
        schema_contract_valid = bool(
            schema_policy_version
            == ANALYSIS_DIRECTOR_RETRY_SCHEMA_POLICY_VERSION
            and isinstance(rejected_emotions_by_id, list)
            and len(rejected_ids) == len(rejected_emotions_by_id)
            and rejected_ids == sorted(set(rejected_ids))
        )
        if not schema_contract_valid:
            raise error_type("Analysis critic contract has invalid retry schema fields")
        if (
            type(confidence_floor) not in {int, float}
            or type(confidence_cap) not in {int, float}
            or not math.isfinite(float(confidence_floor))
            or not math.isfinite(float(confidence_cap))
            or not 0.0 <= float(confidence_floor) <= float(confidence_cap) <= 1.0
            or float(confidence_floor) > ANALYSIS_CRITIC_CONFIDENCE_MAX
        ):
            raise error_type(
                "Analysis critic confidence floor/cap must be finite ordered values within "
                "[0,1], and the floor cannot exceed the critic schema maximum"
            )
        evidence_policy = contract.get("evidence_policy")
        evidence_text_sha256 = contract.get("evidence_text_sha256")
        evidence_anchor_set_sha256 = contract.get("evidence_anchor_set_sha256")
        evidence_anchor_count = contract.get("evidence_anchor_count")
        if (
            evidence_policy
            not in {
                ANALYSIS_CRITIC_EVIDENCE_POLICY_SINGLETON_FULL_TARGET,
                ANALYSIS_CRITIC_EVIDENCE_POLICY_SINGLETON_SOURCE_ANCHOR,
                ANALYSIS_CRITIC_EVIDENCE_POLICY_PER_ID_SOURCE_ANCHOR,
            }
            or not isinstance(evidence_text_sha256, str)
            or not isinstance(evidence_anchor_set_sha256, str)
            or type(evidence_anchor_count) is not int
            or evidence_anchor_count < 0
        ):
            raise error_type("Analysis critic contract has invalid evidence policy fields")
        sha256_pattern = re.compile(r"[0-9a-f]{64}")
        if evidence_policy == ANALYSIS_CRITIC_EVIDENCE_POLICY_SINGLETON_FULL_TARGET:
            evidence_fields_valid = (
                sha256_pattern.fullmatch(evidence_text_sha256) is not None
                and evidence_anchor_set_sha256 == ""
                and evidence_anchor_count == 0
            )
        elif (
            evidence_policy
            == ANALYSIS_CRITIC_EVIDENCE_POLICY_SINGLETON_SOURCE_ANCHOR
        ):
            evidence_fields_valid = (
                sha256_pattern.fullmatch(evidence_text_sha256) is not None
                and sha256_pattern.fullmatch(evidence_anchor_set_sha256) is not None
                and evidence_anchor_count > 0
            )
        elif (
            evidence_policy
            == ANALYSIS_CRITIC_EVIDENCE_POLICY_PER_ID_SOURCE_ANCHOR
        ):
            evidence_fields_valid = (
                evidence_text_sha256 == ""
                and sha256_pattern.fullmatch(evidence_anchor_set_sha256) is not None
                and evidence_anchor_count > 0
            )
        else:
            evidence_fields_valid = False
        if not evidence_fields_valid:
            raise error_type("Analysis critic contract has invalid evidence policy fields")
        if candidate_json is not None:
            (
                expected_evidence_policy,
                expected_evidence_text_sha256,
                expected_evidence_anchor_set_sha256,
                expected_evidence_anchor_count,
            ) = cls._analysis_critic_evidence_contract(candidate_json)
            if (
                evidence_policy != expected_evidence_policy
                or evidence_text_sha256 != expected_evidence_text_sha256
                or evidence_anchor_set_sha256
                != expected_evidence_anchor_set_sha256
                or evidence_anchor_count != expected_evidence_anchor_count
            ):
                raise error_type(
                    "Analysis critic evidence policy is not source-bound"
                )
            source_bound_rejections = {
                str(item["id"]): list(item["emotions"])
                for item in cls._analysis_critic_rejected_emotion_contract(
                    candidate_json
                )
            }
            if any(
                source_bound_rejections.get(str(item["id"]))
                != item["emotions"]
                for item in rejected_emotions_by_id
            ):
                raise error_type(
                    "Analysis critic retry schema is not source-bound"
                )
        return float(confidence_floor), float(confidence_cap)

    @staticmethod
    def _analysis_candidate_identity(
        *,
        policy_fingerprint: str,
        model_name: str,
        model_digest: str,
        group_fingerprint: str,
        context_hash: str,
        candidate_hash: str,
    ) -> tuple[str, str, str, str, str, str]:
        identity = tuple(
            str(value).strip()
            for value in (
                policy_fingerprint,
                model_name,
                model_digest,
                group_fingerprint,
                context_hash,
                candidate_hash,
            )
        )
        if any(not value for value in identity):
            raise ValueError("Analysis candidate identity fields must be non-empty")
        return identity  # type: ignore[return-value]

    @classmethod
    def _analysis_candidate_commit_rows(
        cls,
        candidate_json: str,
    ) -> dict[str, dict[str, Any]]:
        try:
            candidate = json.loads(candidate_json)
        except (TypeError, json.JSONDecodeError) as exc:
            raise RuntimeError("Durable analysis candidate JSON is invalid") from exc
        if not isinstance(candidate, dict) or set(candidate) != {
            "segments",
            "pronunciations",
            "critic_rows",
        }:
            raise ValueError(
                "Analysis acceptance envelope requires exact segments/pronunciations/critic_rows"
            )
        segment_items = candidate.get("segments")
        if not isinstance(segment_items, list) or not segment_items:
            raise ValueError("Analysis candidate must contain a non-empty segments array")
        commit_rows: dict[str, dict[str, Any]] = {}
        for item in segment_items:
            if not isinstance(item, dict) or set(item) != {
                "segment_id",
                "stable_id",
                "text_sha256",
                "data",
            }:
                raise ValueError(
                    "Analysis candidate segments require exact segment_id/stable_id/"
                    "text_sha256/data fields"
                )
            stable_id = str(item["stable_id"]).strip()
            text_sha256 = str(item["text_sha256"]).strip()
            data = item["data"]
            if (
                type(item["segment_id"]) is not int
                or int(item["segment_id"]) < 1
                or not stable_id
                or not text_sha256
                or not isinstance(data, dict)
                or not data
            ):
                raise ValueError("Analysis candidate segment provenance is incomplete")
            if set(data) != ANALYSIS_ACCEPTED_DELIVERY_FIELDS:
                raise ValueError(
                    "Analysis candidate segment data does not contain the full validated delivery"
                )
            confidence = data.get("confidence")
            if (
                type(confidence) not in {int, float}
                or not math.isfinite(float(confidence))
                or not 0.0 <= float(confidence) <= 1.0
            ):
                raise ValueError(
                    "Analysis candidate confidence must be finite and within [0,1]"
                )
            note_markers = analysis_note_markers(data)
            if note_markers:
                raise ValueError("Analysis candidate notes must not persist host markers")
            if stable_id in commit_rows:
                raise ValueError("Analysis candidate contains duplicate stable IDs")
            data_json, _data_hash = cls._canonical_analysis_json(
                data,
                "analysis candidate segment data",
            )
            commit_rows[stable_id] = {
                "segment_id": int(item["segment_id"]),
                "stable_id": stable_id,
                "text_sha256": text_sha256,
                "data_json": data_json,
                "note_markers": note_markers,
            }
        pronunciation_items = candidate["pronunciations"]
        if not isinstance(pronunciation_items, list):
            raise ValueError("Analysis candidate pronunciations must be an array")
        normalized_surfaces: set[str] = set()
        for pronunciation in pronunciation_items:
            if (
                not isinstance(pronunciation, dict)
                or set(pronunciation) != ANALYSIS_PRONUNCIATION_FIELDS
            ):
                raise ValueError(
                    "Analysis candidate pronunciation does not contain validated fields"
                )
            normalized_surface = str(pronunciation["normalized_surface"]).strip()
            if not normalized_surface or normalized_surface in normalized_surfaces:
                raise ValueError(
                    "Analysis candidate pronunciations require unique normalized surfaces"
                )
            normalized_surfaces.add(normalized_surface)
        critic_rows = candidate["critic_rows"]
        if (
            not isinstance(critic_rows, list)
            or len(critic_rows) != len(segment_items)
            or any(not isinstance(row, dict) or not row for row in critic_rows)
        ):
            raise ValueError(
                "Analysis acceptance envelope requires one non-empty critic row per segment"
            )
        for index, (segment, critic_row) in enumerate(
            zip(segment_items, critic_rows, strict=True),
            1,
        ):
            candidate_delivery = critic_row.get("candidate")
            source_role = critic_row.get("source_role")
            context_policy = critic_row.get("context_policy")
            host_locked_fields = critic_row.get("host_locked_fields")
            content_host_lock_is_valid = (
                host_locked_fields == {}
                or (
                    isinstance(host_locked_fields, dict)
                    and isinstance(candidate_delivery, dict)
                    and (
                        (
                            set(host_locked_fields) == {"emotion"}
                            and host_locked_fields["emotion"]
                            == candidate_delivery.get("emotion")
                        )
                        or (
                            set(host_locked_fields) == {"kind"}
                            and host_locked_fields["kind"]
                            == candidate_delivery.get("kind")
                        )
                        or (
                            set(host_locked_fields) == {"kind", "emotion"}
                            and host_locked_fields["kind"]
                            == candidate_delivery.get("kind")
                            and host_locked_fields["emotion"]
                            == candidate_delivery.get("emotion")
                        )
                    )
                )
            )
            is_adjacent_content_row = (
                source_role == ANALYSIS_SOURCE_ROLE_CONTENT
                and context_policy == ANALYSIS_CONTEXT_POLICY_ADJACENT
                and critic_row.get("hint") != "thought"
                and content_host_lock_is_valid
            )
            is_previous_only_content_row = (
                source_role == ANALYSIS_SOURCE_ROLE_CONTENT
                and context_policy == ANALYSIS_CONTEXT_POLICY_PREVIOUS_ONLY
                and critic_row.get("hint") == "thought"
                and critic_row.get("next_text") == ""
                and content_host_lock_is_valid
            )
            is_narration_before_thought_content_row = (
                source_role == ANALYSIS_SOURCE_ROLE_CONTENT
                and context_policy
                == ANALYSIS_CONTEXT_POLICY_NARRATION_BEFORE_THOUGHT
                and critic_row.get("hint") == "narration"
                and critic_row.get("next_text") == ""
                and content_host_lock_is_valid
            )
            is_narration_before_next_paragraph_thought_content_row = (
                source_role == ANALYSIS_SOURCE_ROLE_CONTENT
                and context_policy
                == ANALYSIS_CONTEXT_POLICY_NARRATION_BEFORE_NEXT_PARAGRAPH_THOUGHT
                and critic_row.get("hint") == "narration"
                and critic_row.get("next_text") == ""
                and content_host_lock_is_valid
            )
            is_chapter_heading_row = (
                source_role == ANALYSIS_SOURCE_ROLE_CHAPTER_HEADING
                and context_policy == ANALYSIS_CONTEXT_POLICY_TARGET_ONLY
                and critic_row.get("host_locked_fields")
                == ANALYSIS_CHAPTER_HEADING_DELIVERY
                and critic_row.get("previous_text") == ""
                and critic_row.get("next_text") == ""
                and candidate_delivery == ANALYSIS_CHAPTER_HEADING_DELIVERY
            )
            if (
                is_chapter_heading_row
                and float(segment["data"]["confidence"])
                != ANALYSIS_CHAPTER_HEADING_CONFIDENCE
            ):
                raise ValueError(
                    "Analysis chapter heading candidate confidence must equal its host lock"
                )
            # Fifteen conditions behind one message, on the row shape the whole critic
            # contract rests on. See require_all.
            require_all(
                "Analysis critic rows do not map exactly to source IDs/hashes/delivery",
                ("row_keys", set(critic_row) != {
                    "id",
                    "paragraph",
                    "hint",
                    "source_role",
                    "context_policy",
                    "host_locked_fields",
                    "previous_text",
                    "text",
                    "next_text",
                    "candidate",
                    "batch_signature_count",
                }),
                ("row_id", str(critic_row.get("id", "")) != f"S{index:03d}"),
                ("paragraph_type", type(critic_row.get("paragraph")) is not int),
                ("paragraph_range", int(critic_row["paragraph"]) < 0),
                ("hint_type", not isinstance(critic_row.get("hint"), str)),
                ("previous_text_type",
                 not isinstance(critic_row.get("previous_text"), str)),
                ("text_type", not isinstance(critic_row.get("text"), str)),
                ("next_text_type", not isinstance(critic_row.get("next_text"), str)),
                ("signature_count_type",
                 type(critic_row.get("batch_signature_count")) is not int),
                ("signature_count_range",
                 int(critic_row["batch_signature_count"]) < 1),
                ("text_sha256",
                 sha256_text(str(critic_row["text"])) != str(segment["text_sha256"])),
                ("candidate_type", not isinstance(candidate_delivery, dict)),
                ("candidate_fields",
                 set(candidate_delivery) != set(ANALYSIS_CRITIC_DELIVERY_FIELDS)),
                ("candidate_values", any(
                    candidate_delivery[field] != segment["data"][field]
                    for field in ANALYSIS_CRITIC_DELIVERY_FIELDS
                )),
                ("no_matching_row_shape", not (
                    is_adjacent_content_row
                    or is_previous_only_content_row
                    or is_narration_before_thought_content_row
                    or is_narration_before_next_paragraph_thought_content_row
                    or is_chapter_heading_row
                )),
                _error=ValueError,
                row_id=critic_row.get("id"),
                index=index,
                source_role=source_role,
                context_policy=context_policy,
            )
        return commit_rows

    @classmethod
    def _analysis_host_lock_contract(
        cls,
        candidate_json: str,
        deterministic_issue_json: str,
    ) -> tuple[
        dict[str, dict[str, Any]],
        dict[str, dict[str, Any]],
        dict[str, dict[str, Any]],
    ]:
        try:
            candidate = json.loads(candidate_json)
            deterministic_issues = json.loads(deterministic_issue_json)
        except json.JSONDecodeError as exc:
            raise RuntimeError("Durable analysis host-lock JSON is invalid") from exc
        if not isinstance(candidate, dict) or not isinstance(deterministic_issues, dict):
            raise RuntimeError("Durable analysis host-lock contract must contain objects")
        if set(deterministic_issues) != ANALYSIS_DETERMINISTIC_ISSUE_FIELDS:
            raise RuntimeError("Durable deterministic analysis issues have invalid schema")
        segments = candidate.get("segments")
        critic_rows = candidate.get("critic_rows")
        if not isinstance(segments, list) or not isinstance(critic_rows, list):
            raise RuntimeError("Durable analysis host-lock candidate is incomplete")
        segment_by_stable = {
            str(segment["stable_id"]): segment for segment in segments
        }
        semantic_issues = deterministic_issues["semantic_issues"]
        if not isinstance(semantic_issues, list):
            raise RuntimeError("Durable semantic analysis issues must be an array")
        critic_row_by_stable = {
            str(segment["stable_id"]): critic_row
            for segment, critic_row in zip(segments, critic_rows, strict=True)
        }
        _critic_rows_json, candidate_hash = cls._canonical_analysis_json(
            critic_rows,
            "analysis host-lock critic rows",
        )
        heading_stable_ids = {
            stable_id
            for stable_id, critic_row in critic_row_by_stable.items()
            if critic_row["source_role"] == ANALYSIS_SOURCE_ROLE_CHAPTER_HEADING
        }
        context_kind_row_ids = {
            stable_id
            for stable_id, critic_row in critic_row_by_stable.items()
            if critic_row["source_role"] == ANALYSIS_SOURCE_ROLE_CONTENT
            and critic_row["context_policy"]
            == ANALYSIS_CONTEXT_POLICY_NARRATION_BEFORE_THOUGHT
        }
        dialogue_kind_row_ids = {
            stable_id
            for stable_id, critic_row in critic_row_by_stable.items()
            if critic_row["source_role"] == ANALYSIS_SOURCE_ROLE_CONTENT
            and critic_row["hint"] == "dialogue"
        }
        semantic_row_ids = {
            stable_id
            for stable_id, critic_row in critic_row_by_stable.items()
            if critic_row["source_role"] == ANALYSIS_SOURCE_ROLE_CONTENT
            and "emotion" in critic_row["host_locked_fields"]
        }
        kind_locked_row_ids = {
            stable_id
            for stable_id, critic_row in critic_row_by_stable.items()
            if critic_row["source_role"] == ANALYSIS_SOURCE_ROLE_CONTENT
            and "kind" in critic_row["host_locked_fields"]
        }
        source_kind_locks = {
            stable_id: {
                "policy_version": ANALYSIS_HOST_SEMANTIC_POLICY_VERSION,
                "rule": ANALYSIS_CONTEXT_SOURCE_KIND_RULE,
                "source_kind": "narration",
            }
            for stable_id in context_kind_row_ids
        }
        source_kind_locks.update(
            {
                stable_id: {
                    "policy_version": ANALYSIS_HOST_SEMANTIC_POLICY_VERSION,
                    "rule": ANALYSIS_SOURCE_DIALOGUE_KIND_RULE,
                    "source_kind": "dialogue",
                }
                for stable_id in dialogue_kind_row_ids
            }
        )
        if any(
            critic_row_by_stable[stable_id]["candidate"]["kind"] != "narration"
            or critic_row_by_stable[stable_id]["hint"] != "narration"
            or critic_row_by_stable[stable_id]["next_text"] != ""
            for stable_id in context_kind_row_ids
        ) or not context_kind_row_ids <= kind_locked_row_ids:
            raise RuntimeError(
                "Narration-before-thought context kind lock is not candidate-bound"
            )
        if any(
            critic_row_by_stable[stable_id]["candidate"]["kind"] != "dialogue"
            or critic_row_by_stable[stable_id]["context_policy"]
            != ANALYSIS_CONTEXT_POLICY_ADJACENT
            or critic_row_by_stable[stable_id]["host_locked_fields"].get("kind")
            != "dialogue"
            for stable_id in dialogue_kind_row_ids
        ):
            raise RuntimeError(
                "Explicit dialogue source kind lock is not candidate-bound"
            )
        clearance = deterministic_issues.get("host_affect_clearance")
        if clearance is None:
            if heading_stable_ids or semantic_row_ids:
                raise RuntimeError(
                    "Analysis host-locked rows require durable deterministic clearance"
                )
            if kind_locked_row_ids != context_kind_row_ids | dialogue_kind_row_ids:
                raise RuntimeError(
                    "Content source-kind lock is not source-ledger-bound"
                )
            return {}, {}, source_kind_locks
        if (
            not isinstance(clearance, dict)
            or set(clearance) != ANALYSIS_HOST_CLEARANCE_FIELDS
            or clearance.get("status") != "cleared"
            or clearance.get("policy_version") != ANALYSIS_HOST_AFFECT_POLICY_VERSION
            or clearance.get("candidate_hash") != candidate_hash
            or type(clearance.get("checked_segment_count")) is not int
            or int(clearance["checked_segment_count"]) != len(segments)
        ):
            raise RuntimeError("Analysis host clearance is not candidate-bound")
        structural_lock_items = clearance.get("structural_locks", [])
        semantic_lock_items = clearance.get("semantic_locks", [])
        if not isinstance(structural_lock_items, list):
            raise RuntimeError("Host structural clearance locks must be an array")
        if not isinstance(semantic_lock_items, list):
            raise RuntimeError("Host semantic clearance locks must be an array")
        structural_locks: dict[str, dict[str, Any]] = {}
        for lock in structural_lock_items:
            if (
                not isinstance(lock, dict)
                or set(lock) != ANALYSIS_HOST_STRUCTURAL_LOCK_FIELDS
            ):
                raise RuntimeError("Host structural clearance lock has invalid schema")
            stable_id = str(lock.get("stable_id", "")).strip()
            if not stable_id or stable_id in structural_locks:
                raise RuntimeError("Host structural clearance lock has invalid stable ID")
            structural_locks[stable_id] = lock
        semantic_locks: dict[str, dict[str, Any]] = {}
        for lock in semantic_lock_items:
            if not isinstance(lock, dict) or set(lock) != ANALYSIS_HOST_SEMANTIC_LOCK_FIELDS:
                raise RuntimeError("Host semantic clearance lock has invalid schema")
            stable_id = str(lock.get("stable_id", "")).strip()
            if not stable_id or stable_id in semantic_locks:
                raise RuntimeError("Host semantic clearance lock has invalid stable ID")
            semantic_locks[stable_id] = lock
        expected_semantic_evidence: list[dict[str, Any]] = []
        for lock in semantic_lock_items:
            item = {
                "stable_id": lock["stable_id"],
                "text_sha256": lock["text_sha256"],
                "rule": lock["rule"],
                "cue_class": lock["cue_class"],
                "candidate_emotion": lock["candidate_emotion"],
                "allowed_emotions": lock["allowed_emotions"],
                "outcome": "pass",
            }
            if lock["related_stable_id"]:
                item["related_stable_id"] = lock["related_stable_id"]
            if lock["related_text_sha256"]:
                item["related_text_sha256"] = lock["related_text_sha256"]
            expected_semantic_evidence.append(item)
        if (
            type(clearance.get("matched_rule_count")) is not int
            or int(clearance["matched_rule_count"]) != len(semantic_lock_items)
            or clearance.get("evidence") != expected_semantic_evidence
        ):
            raise RuntimeError("Analysis host clearance evidence is not lock-bound")
        if set(structural_locks) != heading_stable_ids:
            raise RuntimeError(
                "Host structural clearance differs from chapter-heading rows"
            )
        if set(semantic_locks) != semantic_row_ids:
            raise RuntimeError("Host semantic clearance differs from locked content rows")
        if set(structural_locks) & set(semantic_locks):
            raise RuntimeError("Structural and semantic host locks must be disjoint")
        for stable_id, lock in structural_locks.items():
            segment = segment_by_stable[stable_id]
            critic_row = critic_row_by_stable[stable_id]
            generator_fields = lock["generator_fields"]
            generator_confidence = lock["generator_confidence"]
            generator_delivery_valid = (
                isinstance(generator_fields, dict)
                and set(generator_fields) == set(ANALYSIS_CRITIC_DELIVERY_FIELDS)
                and isinstance(generator_fields.get("kind"), str)
                and generator_fields.get("kind") in ANALYSIS_CRITIC_KINDS
                and isinstance(generator_fields.get("speaker"), str)
                and len(generator_fields["speaker"]) <= 120
                and isinstance(generator_fields.get("emotion"), str)
                and generator_fields.get("emotion") in ANALYSIS_CRITIC_EMOTIONS
                and type(generator_fields.get("intensity")) is int
                and 0 <= int(generator_fields["intensity"]) <= 3
                and isinstance(generator_fields.get("pace"), str)
                and generator_fields.get("pace") in ANALYSIS_CRITIC_PACES
                and isinstance(generator_fields.get("volume"), str)
                and generator_fields.get("volume") in ANALYSIS_CRITIC_VOLUMES
            )
            expected_lock_fields = {
                "stable_id": stable_id,
                "text_sha256": str(segment["text_sha256"]),
                "source_role": ANALYSIS_SOURCE_ROLE_CHAPTER_HEADING,
                "context_policy": ANALYSIS_CONTEXT_POLICY_TARGET_ONLY,
                "policy_version": ANALYSIS_HOST_STRUCTURAL_POLICY_VERSION,
                "evidence_quote": str(critic_row["text"]),
                "locked_fields": ANALYSIS_CHAPTER_HEADING_DELIVERY,
                "locked_confidence": ANALYSIS_CHAPTER_HEADING_CONFIDENCE,
            }
            if (
                any(lock.get(key) != value for key, value in expected_lock_fields.items())
                or not generator_delivery_valid
                or not isinstance(lock["generator_notes"], str)
                or type(generator_confidence) not in {int, float}
                or not math.isfinite(float(generator_confidence))
                or not 0.0 <= float(generator_confidence) <= 1.0
            ):
                raise RuntimeError(
                    "Accepted chapter heading structural clearance is not source-bound"
                )
            if (
                critic_row["previous_text"] != ""
                or critic_row["next_text"] != ""
                or critic_row["host_locked_fields"]
                != ANALYSIS_CHAPTER_HEADING_DELIVERY
                or critic_row["candidate"] != ANALYSIS_CHAPTER_HEADING_DELIVERY
                or float(segment["data"]["confidence"])
                != ANALYSIS_CHAPTER_HEADING_CONFIDENCE
            ):
                raise RuntimeError(
                    "Accepted chapter heading violates target-only canonical delivery"
                )
        for stable_id, lock in semantic_locks.items():
            segment = segment_by_stable[stable_id]
            critic_row = critic_row_by_stable[stable_id]
            rule = str(lock["rule"])
            rule_contract = ANALYSIS_HOST_SEMANTIC_RULE_CONTRACTS.get(rule)
            if rule_contract is None:
                raise RuntimeError("Host semantic clearance uses an unknown rule")
            allowed_emotions = lock["allowed_emotions"]
            expected_allowed_emotions = list(rule_contract["allowed_emotions"])
            candidate_emotion = str(lock["candidate_emotion"])
            related_stable_id = lock["related_stable_id"]
            related_text_sha256 = lock["related_text_sha256"]
            requires_related = bool(rule_contract["requires_related"])
            source_text = str(critic_row["text"])
            source_semantics_valid = _analysis_source_matches_host_semantic_rule(
                source_text,
                rule,
            )
            # Fifteen conditions shared one message. The lock is derived here and not
            # written anywhere a reader can inspect, so a mismatch meant another full
            # analysis pass to learn which field moved.
            require_all(
                "Host semantic clearance is not source-bound",
                ("policy_version",
                 lock["policy_version"] != ANALYSIS_HOST_SEMANTIC_POLICY_VERSION),
                ("text_sha256", lock["text_sha256"] != str(segment["text_sha256"])),
                ("source_role", lock["source_role"] != ANALYSIS_SOURCE_ROLE_CONTENT),
                ("field", lock["field"] != "emotion"),
                ("cue_class", lock["cue_class"] != rule_contract["cue_class"]),
                ("allowed_emotions", allowed_emotions != expected_allowed_emotions),
                ("candidate_emotion_allowed",
                 candidate_emotion not in expected_allowed_emotions),
                ("candidate_emotion",
                 critic_row["candidate"]["emotion"] != candidate_emotion),
                ("candidate_kind",
                 critic_row["candidate"]["kind"] != rule_contract["source_kind"]),
                ("hint", critic_row["hint"] != rule_contract["source_kind"]),
                ("related_stable_id_type", not isinstance(related_stable_id, str)),
                ("related_sha256_type", not isinstance(related_text_sha256, str)),
                ("requires_related",
                 requires_related != bool(related_stable_id and related_text_sha256)),
                ("related_pair",
                 bool(related_stable_id) != bool(related_text_sha256)),
                ("source_semantics", not source_semantics_valid),
                stable_id=stable_id,
                rule=str(lock["rule"]),
                candidate_emotion=candidate_emotion,
                allowed=sorted(allowed_emotions or []),
                expected_allowed=sorted(expected_allowed_emotions or []),
            )
        semantic_source_kind_ids = {
            stable_id
            for stable_id, lock in semantic_locks.items()
            if bool(
                ANALYSIS_HOST_SEMANTIC_RULE_CONTRACTS[str(lock["rule"])].get(
                    "protects_source_kind",
                    False,
                )
            )
        }
        if not semantic_source_kind_ids <= kind_locked_row_ids:
            raise RuntimeError("Host semantic clearance is not source-bound")
        if kind_locked_row_ids != (
            context_kind_row_ids | dialogue_kind_row_ids | semantic_source_kind_ids
        ):
            raise RuntimeError(
                "Content source-kind locks differ from source-derived protections"
            )
        for stable_id, critic_row in critic_row_by_stable.items():
            if critic_row["source_role"] != ANALYSIS_SOURCE_ROLE_CONTENT:
                continue
            expected_host_locked_fields: dict[str, Any] = {}
            if stable_id in (
                context_kind_row_ids | dialogue_kind_row_ids | semantic_source_kind_ids
            ):
                expected_host_locked_fields["kind"] = critic_row["candidate"]["kind"]
            if stable_id in semantic_locks:
                expected_host_locked_fields["emotion"] = semantic_locks[stable_id][
                    "candidate_emotion"
                ]
            if critic_row["host_locked_fields"] != expected_host_locked_fields:
                raise RuntimeError(
                    "Content host-locked fields differ from durable source locks"
                )
        return structural_locks, semantic_locks, source_kind_locks

    @staticmethod
    def _analysis_following_thought_source_conn(
        conn: sqlite3.Connection,
        stored: sqlite3.Row,
    ) -> sqlite3.Row | None:
        next_source = conn.execute(
            "SELECT stable_id,text,text_sha256,chapter_id,seq,paragraph_index,kind_hint "
            "FROM segments WHERE chapter_id=? AND seq=?",
            (int(stored["chapter_id"]), int(stored["seq"]) + 1),
        ).fetchone()
        if next_source is None:
            return None
        if sha256_text(str(next_source["text"])) != str(next_source["text_sha256"]):
            raise RuntimeError(
                "Narration-before-thought related source text hash is invalid"
            )
        if not analysis_source_narration_precedes_thought(
            chapter_id=int(stored["chapter_id"]),
            seq=int(stored["seq"]),
            paragraph_index=int(stored["paragraph_index"]),
            kind_hint=str(stored["kind_hint"]),
            next_chapter_id=int(next_source["chapter_id"]),
            next_seq=int(next_source["seq"]),
            next_paragraph_index=int(next_source["paragraph_index"]),
            next_kind_hint=str(next_source["kind_hint"]),
        ):
            return None
        return next_source

    @staticmethod
    def _analysis_following_next_paragraph_thought_source_conn(
        conn: sqlite3.Connection,
        stored: sqlite3.Row,
    ) -> sqlite3.Row | None:
        next_source = conn.execute(
            "SELECT stable_id,text,text_sha256,chapter_id,seq,paragraph_index,kind_hint "
            "FROM segments WHERE chapter_id=? AND seq=?",
            (int(stored["chapter_id"]), int(stored["seq"]) + 1),
        ).fetchone()
        if next_source is None:
            return None
        if sha256_text(str(next_source["text"])) != str(next_source["text_sha256"]):
            raise RuntimeError(
                "Narration-before-next-paragraph-thought related source text hash "
                "is invalid"
            )
        if not analysis_source_narration_precedes_next_paragraph_thought(
            chapter_id=int(stored["chapter_id"]),
            seq=int(stored["seq"]),
            paragraph_index=int(stored["paragraph_index"]),
            kind_hint=str(stored["kind_hint"]),
            next_chapter_id=int(next_source["chapter_id"]),
            next_seq=int(next_source["seq"]),
            next_paragraph_index=int(next_source["paragraph_index"]),
            next_kind_hint=str(next_source["kind_hint"]),
        ):
            return None
        return next_source

    @staticmethod
    def _analysis_mandatory_semantic_lock_conn(
        conn: sqlite3.Connection,
        stored: sqlite3.Row,
        critic_row: dict[str, Any],
        *,
        is_chapter_heading: bool,
    ) -> dict[str, Any] | None:
        source_kind = str(stored["kind_hint"])
        candidate = critic_row["candidate"]
        candidate_kind = str(candidate["kind"])
        source_text = str(stored["text"])
        rule = ""
        related_stable_id = ""
        related_text_sha256 = ""
        if (
            source_kind == "narration"
            and not is_chapter_heading
            and _analysis_source_has_physical_collapse(source_text)
        ):
            rule = "respiratory_injury_with_consciousness_loss"
        elif (
            source_kind == "narration"
            and not is_chapter_heading
            and _analysis_source_has_desperate_exertion(source_text)
        ):
            rule = "narration_desperate_exertion"
        elif (
            source_kind == "narration"
            and not is_chapter_heading
            and analysis_source_has_sleep_paralysis_helplessness(source_text)
        ):
            rule = "narration_sleep_paralysis_helplessness"
        elif (
            source_kind == "narration"
            and not is_chapter_heading
            and analysis_source_has_recalled_persistent_fear(source_text)
        ):
            rule = "narration_recalled_persistent_fear"
        elif (
            source_kind == "narration"
            and not is_chapter_heading
            and analysis_source_has_stunned_blank_mind(source_text)
        ):
            rule = "narration_stunned_blank_mind"
        elif source_kind == "thought":
            if _analysis_source_has_self_preservation_mortality(source_text):
                rule = "thought_self_preservation_mortality"
            elif ANALYSIS_HOST_WAKE_PATTERN.fullmatch(source_text) is not None:
                related = conn.execute(
                    "SELECT stable_id,text,text_sha256,chapter_id,seq,paragraph_index,kind_hint "
                    "FROM segments WHERE chapter_id=? AND seq=?",
                    (int(stored["chapter_id"]), int(stored["seq"]) - 1),
                ).fetchone()
                if (
                    related is not None
                    and sha256_text(str(related["text"]))
                    != str(related["text_sha256"])
                ):
                    raise RuntimeError(
                        "Adjacent semantic related source text hash is invalid"
                    )
                if (
                    related is not None
                    and str(related["kind_hint"]) == "thought"
                    and int(related["chapter_id"]) == int(stored["chapter_id"])
                    and int(related["seq"]) + 1 == int(stored["seq"])
                    and int(related["paragraph_index"]) + 1
                    == int(stored["paragraph_index"])
                    and _analysis_source_has_self_preservation_mortality(
                        str(related["text"])
                    )
                ):
                    rule = "adjacent_thought_wake_self_rescue"
                    related_stable_id = str(related["stable_id"])
                    related_text_sha256 = str(related["text_sha256"])
        if not rule:
            return None
        rule_contract = ANALYSIS_HOST_SEMANTIC_RULE_CONTRACTS[rule]
        if candidate_kind != str(rule_contract["source_kind"]):
            raise RuntimeError("Analysis candidate kind violates a source-owned boundary")
        candidate_emotion = str(candidate["emotion"])
        allowed_emotions = list(rule_contract["allowed_emotions"])
        if candidate_emotion not in allowed_emotions:
            raise RuntimeError(
                "Analysis candidate violates a mandatory host semantic emotion"
            )
        return {
            "policy_version": ANALYSIS_HOST_SEMANTIC_POLICY_VERSION,
            "stable_id": str(stored["stable_id"]),
            "text_sha256": str(stored["text_sha256"]),
            "source_role": ANALYSIS_SOURCE_ROLE_CONTENT,
            "field": "emotion",
            "rule": rule,
            "cue_class": rule_contract["cue_class"],
            "candidate_emotion": candidate_emotion,
            "allowed_emotions": allowed_emotions,
            "related_stable_id": related_stable_id,
            "related_text_sha256": related_text_sha256,
        }

    @classmethod
    def _analysis_candidate_context_hash_conn(
        cls,
        conn: sqlite3.Connection,
        candidate: dict[str, Any],
    ) -> str:
        context: list[dict[str, Any]] = []
        for segment in candidate["segments"]:
            stored = conn.execute(
                "SELECT stable_id,text,text_sha256,chapter_id,seq,paragraph_index,kind_hint "
                "FROM segments WHERE id=?",
                (int(segment["segment_id"]),),
            ).fetchone()
            if stored is None:
                raise RuntimeError(
                    "Analysis candidate context source is missing from the segment ledger"
                )
            if sha256_text(str(stored["text"])) != str(stored["text_sha256"]):
                raise RuntimeError("Analysis candidate source text hash is invalid")
            previous = conn.execute(
                "SELECT stable_id,text,text_sha256,chapter_id,seq,paragraph_index,kind_hint "
                "FROM segments WHERE chapter_id=? AND seq=?",
                (int(stored["chapter_id"]), int(stored["seq"]) - 1),
            ).fetchone()
            next_source = conn.execute(
                "SELECT stable_id,text,text_sha256,chapter_id,seq,paragraph_index,kind_hint "
                "FROM segments WHERE chapter_id=? AND seq=?",
                (int(stored["chapter_id"]), int(stored["seq"]) + 1),
            ).fetchone()
            for neighbor in (previous, next_source):
                if (
                    neighbor is not None
                    and sha256_text(str(neighbor["text"]))
                    != str(neighbor["text_sha256"])
                ):
                    raise RuntimeError(
                        "Analysis candidate neighbor source text hash is invalid"
                    )
            previous_text = str(previous["text"])[-500:] if previous is not None else ""
            next_text = str(next_source["text"])[:500] if next_source is not None else ""
            context.append(
                {
                    "stable_id": str(stored["stable_id"]),
                    "chapter_id": int(stored["chapter_id"]),
                    "paragraph_index": int(stored["paragraph_index"]),
                    "kind_hint": str(stored["kind_hint"]),
                    "previous_stable_id": (
                        str(previous["stable_id"]) if previous is not None else ""
                    ),
                    "previous_text_sha256": sha256_text(previous_text),
                    "previous_source_text_sha256": (
                        str(previous["text_sha256"]) if previous is not None else ""
                    ),
                    "previous_chapter_id": (
                        int(previous["chapter_id"]) if previous is not None else None
                    ),
                    "previous_seq": int(previous["seq"]) if previous is not None else None,
                    "previous_paragraph_index": (
                        int(previous["paragraph_index"])
                        if previous is not None
                        else None
                    ),
                    "previous_kind_hint": (
                        str(previous["kind_hint"]) if previous is not None else ""
                    ),
                    "next_stable_id": (
                        str(next_source["stable_id"]) if next_source is not None else ""
                    ),
                    "next_text_sha256": sha256_text(next_text),
                    "next_source_text_sha256": (
                        str(next_source["text_sha256"])
                        if next_source is not None
                        else ""
                    ),
                    "next_chapter_id": (
                        int(next_source["chapter_id"])
                        if next_source is not None
                        else None
                    ),
                    "next_seq": (
                        int(next_source["seq"]) if next_source is not None else None
                    ),
                    "next_paragraph_index": (
                        int(next_source["paragraph_index"])
                        if next_source is not None
                        else None
                    ),
                    "next_kind_hint": (
                        str(next_source["kind_hint"])
                        if next_source is not None
                        else ""
                    ),
                }
            )
        _context_json, context_hash = cls._canonical_analysis_json(
            context,
            "analysis candidate source context",
        )
        return context_hash

    @classmethod
    def _validate_analysis_candidate_sources_conn(
        cls,
        conn: sqlite3.Connection,
        candidate_json: str,
        deterministic_issue_json: str,
        expected_context_hash: str | None = None,
    ) -> None:
        candidate = json.loads(candidate_json)
        if any(
            critic_row.get("context_policy")
            == ANALYSIS_CONTEXT_POLICY_NARRATION_BEFORE_NEXT_PARAGRAPH_THOUGHT
            for critic_row in candidate["critic_rows"]
        ):
            live_context_hash = cls._analysis_candidate_context_hash_conn(
                conn,
                candidate,
            )
            if (
                not isinstance(expected_context_hash, str)
                or not expected_context_hash
                or expected_context_hash != live_context_hash
            ):
                raise RuntimeError(
                    "Narration-before-next-paragraph-thought context hash is not "
                    "source-ledger-bound"
                )
        structural_locks, semantic_locks, context_kind_locks = (
            cls._analysis_host_lock_contract(
                candidate_json,
                deterministic_issue_json,
            )
        )
        stored_by_stable: dict[str, sqlite3.Row] = {}
        critic_row_by_stable: dict[str, dict[str, Any]] = {}
        for segment, critic_row in zip(
            candidate["segments"],
            candidate["critic_rows"],
            strict=True,
        ):
            stored = conn.execute(
                "SELECT stable_id,text,text_sha256,chapter_id,seq,paragraph_index,kind_hint "
                "FROM segments WHERE id=?",
                (int(segment["segment_id"]),),
            ).fetchone()
            if (
                stored is None
                or str(stored["stable_id"]) != str(segment["stable_id"])
                or sha256_text(str(stored["text"]))
                != str(stored["text_sha256"])
                or str(stored["text_sha256"]) != str(segment["text_sha256"])
                or str(stored["text"]) != str(critic_row["text"])
                or int(stored["paragraph_index"]) != int(critic_row["paragraph"])
                or str(stored["kind_hint"]) != str(critic_row["hint"])
            ):
                raise RuntimeError(
                    "Analysis candidate source metadata differs from the segment ledger"
                )
            source_kind = str(stored["kind_hint"])
            candidate_kind = str(critic_row["candidate"]["kind"])
            if (
                source_kind not in ANALYSIS_CRITIC_KINDS
                or candidate_kind not in ANALYSIS_CRITIC_KINDS
            ):
                raise RuntimeError("Analysis candidate kind is not supported")
            crosses_dialogue_boundary = (candidate_kind == "dialogue") != (
                source_kind == "dialogue"
            )
            loses_explicit_thought = (
                source_kind == "thought" and candidate_kind != "thought"
            )
            if crosses_dialogue_boundary or loses_explicit_thought:
                raise RuntimeError(
                    "Analysis candidate kind violates a source-owned boundary"
                )
            if source_kind == "dialogue":
                expected_dialogue_lock = {
                    "policy_version": ANALYSIS_HOST_SEMANTIC_POLICY_VERSION,
                    "rule": ANALYSIS_SOURCE_DIALOGUE_KIND_RULE,
                    "source_kind": "dialogue",
                }
                if (
                    context_kind_locks.get(str(stored["stable_id"]))
                    != expected_dialogue_lock
                ):
                    raise RuntimeError(
                        "Explicit dialogue source kind is not durably host-locked"
                    )
            if source_kind == "thought":
                previous = conn.execute(
                    "SELECT text FROM segments WHERE chapter_id=? AND seq=?",
                    (int(stored["chapter_id"]), int(stored["seq"]) - 1),
                ).fetchone()
                expected_previous_text = (
                    str(previous["text"])[-500:] if previous is not None else ""
                )
                if (
                    str(critic_row["source_role"])
                    != ANALYSIS_SOURCE_ROLE_CONTENT
                    or str(critic_row["context_policy"])
                    != ANALYSIS_CONTEXT_POLICY_PREVIOUS_ONLY
                    or str(critic_row["previous_text"]) != expected_previous_text
                    or str(critic_row["next_text"]) != ""
                ):
                    raise RuntimeError(
                        "Thought analysis context is not source-ledger-bound"
                    )
            elif str(critic_row["source_role"]) == ANALYSIS_SOURCE_ROLE_CONTENT:
                next_source = cls._analysis_following_thought_source_conn(conn, stored)
                masks_following_thought = next_source is not None
                next_paragraph_thought = (
                    None
                    if masks_following_thought
                    else cls._analysis_following_next_paragraph_thought_source_conn(
                        conn,
                        stored,
                    )
                )
                if masks_following_thought:
                    previous = conn.execute(
                        "SELECT text FROM segments WHERE chapter_id=? AND seq=?",
                        (int(stored["chapter_id"]), int(stored["seq"]) - 1),
                    ).fetchone()
                    expected_previous_text = (
                        str(previous["text"])[-500:] if previous is not None else ""
                    )
                    if (
                        str(critic_row["context_policy"])
                        != ANALYSIS_CONTEXT_POLICY_NARRATION_BEFORE_THOUGHT
                        or str(critic_row["previous_text"])
                        != expected_previous_text
                        or str(critic_row["next_text"]) != ""
                    ):
                        raise RuntimeError(
                            "Narration-before-thought context is not source-ledger-bound"
                        )
                    if str(stored["stable_id"]) not in context_kind_locks:
                        raise RuntimeError(
                            "Narration-before-thought source kind is not host-locked"
                        )
                elif next_paragraph_thought is not None:
                    previous = conn.execute(
                        "SELECT text FROM segments WHERE chapter_id=? AND seq=?",
                        (int(stored["chapter_id"]), int(stored["seq"]) - 1),
                    ).fetchone()
                    expected_previous_text = (
                        str(previous["text"])[-500:] if previous is not None else ""
                    )
                    if (
                        str(critic_row["context_policy"])
                        != ANALYSIS_CONTEXT_POLICY_NARRATION_BEFORE_NEXT_PARAGRAPH_THOUGHT
                        or str(critic_row["previous_text"])
                        != expected_previous_text
                        or str(critic_row["next_text"]) != ""
                    ):
                        raise RuntimeError(
                            "Narration-before-next-paragraph-thought context is not "
                            "source-ledger-bound"
                        )
                elif (
                    str(critic_row["context_policy"])
                    != ANALYSIS_CONTEXT_POLICY_ADJACENT
                ):
                    raise RuntimeError(
                        "Content analysis context policy is not source-ledger-bound"
                    )
            if str(critic_row["source_role"]) == ANALYSIS_SOURCE_ROLE_CHAPTER_HEADING:
                if (
                    int(stored["seq"]) != 0
                    or int(stored["paragraph_index"]) != 0
                    or str(stored["kind_hint"]) != "narration"
                    or ANALYSIS_CHAPTER_HEADING_PATTERN.fullmatch(str(stored["text"])) is None
                ):
                    raise RuntimeError(
                        "Chapter heading structural role is not source-metadata-bound"
                    )
            stored_by_stable[str(stored["stable_id"])] = stored
            critic_row_by_stable[str(stored["stable_id"])] = critic_row
        mandatory_heading_ids: set[str] = set()
        mandatory_semantic_locks: dict[str, dict[str, Any]] = {}
        for stable_id, stored in stored_by_stable.items():
            is_chapter_heading = bool(
                int(stored["seq"]) == 0
                and int(stored["paragraph_index"]) == 0
                and str(stored["kind_hint"]) == "narration"
                and ANALYSIS_CHAPTER_HEADING_PATTERN.fullmatch(str(stored["text"]))
                is not None
            )
            if is_chapter_heading:
                mandatory_heading_ids.add(stable_id)
            mandatory_lock = cls._analysis_mandatory_semantic_lock_conn(
                conn,
                stored,
                critic_row_by_stable[stable_id],
                is_chapter_heading=is_chapter_heading,
            )
            if mandatory_lock is not None:
                mandatory_semantic_locks[stable_id] = mandatory_lock
        for stable_id, lock in semantic_locks.items():
            related_stable_id = str(lock["related_stable_id"])
            if not related_stable_id:
                continue
            current = stored_by_stable[stable_id]
            related = conn.execute(
                "SELECT stable_id,text,text_sha256,chapter_id,seq,paragraph_index,kind_hint "
                "FROM segments WHERE stable_id=?",
                (related_stable_id,),
            ).fetchone()
            if (
                related is not None
                and sha256_text(str(related["text"]))
                != str(related["text_sha256"])
            ):
                raise RuntimeError(
                    "Adjacent semantic related source text hash is invalid"
                )
            if (
                related is None
                or str(related["text_sha256"]) != str(lock["related_text_sha256"])
                or str(related["kind_hint"]) != "thought"
                or str(current["kind_hint"]) != "thought"
                or int(related["chapter_id"]) != int(current["chapter_id"])
                or int(related["seq"]) + 1 != int(current["seq"])
                or int(related["paragraph_index"]) + 1
                != int(current["paragraph_index"])
                or not _analysis_source_has_self_preservation_mortality(
                    str(related["text"])
                )
            ):
                raise RuntimeError(
                    "Adjacent host semantic clearance has invalid related provenance"
                )
        if set(structural_locks) != mandatory_heading_ids:
            raise RuntimeError(
                "Host structural clearance differs from source-derived chapter headings"
            )
        if semantic_locks != mandatory_semantic_locks:
            raise RuntimeError(
                "Host semantic clearance differs from source-derived mandatory locks"
            )

    @classmethod
    def _analysis_expected_source_kind_override_conn(
        cls,
        conn: sqlite3.Connection,
        *,
        candidate_segment: dict[str, Any],
        critic_row: dict[str, Any],
        critic_delivery: dict[str, Any],
        raw_deltas: list[str],
        semantic_lock: dict[str, Any] | None,
        context_kind_lock: dict[str, Any] | None,
    ) -> dict[str, Any] | None:
        candidate_projection = critic_row["candidate"]
        covered_kind_deltas = [
            delta for delta in raw_deltas if delta.startswith("kind:")
        ]
        if len(covered_kind_deltas) != 1:
            return None
        related_provenance: dict[str, str] = {}
        if context_kind_lock is not None:
            stored = conn.execute(
                "SELECT stable_id,text,text_sha256,chapter_id,seq,paragraph_index,kind_hint "
                "FROM segments WHERE id=?",
                (int(candidate_segment["segment_id"]),),
            ).fetchone()
            if (
                stored is None
                or sha256_text(str(stored["text"])) != str(stored["text_sha256"])
                or str(stored["stable_id"])
                != str(candidate_segment["stable_id"])
                or str(stored["text_sha256"])
                != str(candidate_segment["text_sha256"])
            ):
                raise RuntimeError("Source-kind override target provenance is invalid")
            rule = str(context_kind_lock["rule"])
            source_kind = str(context_kind_lock["source_kind"])
            if rule == ANALYSIS_SOURCE_DIALOGUE_KIND_RULE:
                if (
                    source_kind != "dialogue"
                    or str(stored["kind_hint"]) != "dialogue"
                    or str(critic_row["hint"]) != "dialogue"
                    or candidate_projection["kind"] != "dialogue"
                    or critic_delivery.get("kind") == "dialogue"
                ):
                    raise RuntimeError(
                        "Explicit dialogue source-kind override is not source-bound"
                    )
            elif rule == ANALYSIS_CONTEXT_SOURCE_KIND_RULE:
                if (
                    source_kind != "narration"
                    or str(stored["kind_hint"]) != "narration"
                    or candidate_projection["kind"] != "narration"
                    or critic_delivery.get("kind") != "thought"
                ):
                    raise RuntimeError(
                        "Narration-before-thought source-kind override is not source-bound"
                    )
                next_source = cls._analysis_following_thought_source_conn(conn, stored)
                if next_source is None:
                    raise RuntimeError(
                        "Narration-before-thought source-kind override lost related provenance"
                    )
                related_provenance = {
                    "related_stable_id": str(next_source["stable_id"]),
                    "related_text_sha256": str(next_source["text_sha256"]),
                }
            else:
                raise RuntimeError(
                    "Source-kind override uses an unknown durable rule"
                )
        else:
            semantic_rule_contract = (
                ANALYSIS_HOST_SEMANTIC_RULE_CONTRACTS.get(str(semantic_lock["rule"]))
                if semantic_lock is not None
                else None
            )
            if not bool(
                semantic_rule_contract is not None
                and semantic_rule_contract.get("protects_source_kind", False)
            ):
                return None
            if (
                candidate_projection["kind"] != "narration"
                or critic_delivery.get("kind") != "thought"
            ):
                return None
            rule = str(semantic_lock["rule"])
            source_kind = "narration"
        unresolved_kind_deltas = [
            delta for delta in raw_deltas if not delta.startswith("kind:")
        ]
        return {
            "policy_version": ANALYSIS_HOST_SEMANTIC_POLICY_VERSION,
            "stable_id": str(candidate_segment["stable_id"]),
            "text_sha256": str(candidate_segment["text_sha256"]),
            "rule": rule,
            "field": "kind",
            "candidate_value": candidate_projection["kind"],
            "allowed_values": [candidate_projection["kind"]],
            "raw_accept": False,
            "raw_field_deltas": raw_deltas,
            "covered_field_deltas": covered_kind_deltas,
            "unresolved_field_deltas": unresolved_kind_deltas,
            **related_provenance,
        }

    @classmethod
    def _validate_analysis_acceptance_evidence(
        cls,
        conn: sqlite3.Connection,
        candidate_json: str,
        commit_envelope_json: str,
        evidence: dict[str, Any],
        reserved_contract_json: str,
        deterministic_issue_json: str,
    ) -> None:
        candidate = json.loads(candidate_json)
        commit = json.loads(commit_envelope_json)
        candidate_segments = {
            str(item["stable_id"]): item for item in candidate["segments"]
        }
        commit_segments = {
            str(item["stable_id"]): item for item in commit["segments"]
        }
        critic_rows = candidate["critic_rows"]
        candidate_speakers = tuple(
            critic_row["candidate"]["speaker"] for critic_row in critic_rows
        )
        critic_row_by_stable = {
            str(segment["stable_id"]): critic_row
            for segment, critic_row in zip(
                candidate["segments"],
                critic_rows,
                strict=True,
            )
        }
        critic_delivery_by_stable = {
            stable_id: dict(critic_row["candidate"])
            for stable_id, critic_row in critic_row_by_stable.items()
        }
        _structural_locks, semantic_locks, context_kind_locks = (
            cls._analysis_host_lock_contract(
                candidate_json,
                deterministic_issue_json,
            )
        )
        try:
            reserved_contract = json.loads(reserved_contract_json)
        except json.JSONDecodeError as exc:
            raise RuntimeError("Reserved critic contract JSON is invalid") from exc
        canonical_reserved_contract, _reserved_contract_hash = cls._canonical_analysis_json(
            reserved_contract,
            "reserved analysis critic contract",
        )
        critic_contract = evidence.get("critic_contract")
        if not isinstance(critic_contract, dict):
            raise ValueError("Accepted critic evidence requires its durable critic contract")
        canonical_evidence_contract, _evidence_contract_hash = cls._canonical_analysis_json(
            critic_contract,
            "accepted critic evidence contract",
        )
        if canonical_evidence_contract != canonical_reserved_contract:
            raise RuntimeError(
                "Accepted critic evidence contract differs from the reserved request contract"
            )
        confidence_floor, confidence_cap = cls._analysis_critic_confidence_bounds(
            critic_contract,
            durable=True,
            candidate_json=candidate_json,
        )
        candidate_hash = analysis_critic_candidate_hash(
            critic_rows,
            critic_contract["rejected_emotions_by_id"],
        )
        if str(evidence.get("candidate_hash", "")) != candidate_hash:
            raise RuntimeError("Accepted critic evidence candidate hash is invalid")
        rejected_emotions_by_batch = {
            str(item["id"]): frozenset(str(value) for value in item["emotions"])
            for item in critic_contract["rejected_emotions_by_id"]
        }
        evidence_policy = str(critic_contract["evidence_policy"])
        singleton_source_anchors = frozenset(
            canonical_analysis_critic_source_anchors(str(critic_rows[0]["text"]))
            if evidence_policy
            == ANALYSIS_CRITIC_EVIDENCE_POLICY_SINGLETON_SOURCE_ANCHOR
            else ()
        )
        per_id_source_anchors = {
            str(item["id"]): frozenset(item["anchors"])
            for item in (
                canonical_analysis_critic_per_id_source_anchor_map(critic_rows)
                if evidence_policy
                == ANALYSIS_CRITIC_EVIDENCE_POLICY_PER_ID_SOURCE_ANCHOR
                else ()
            )
        }
        evidence_segments = evidence.get("segments")
        if not isinstance(evidence_segments, list):
            raise ValueError("Accepted critic evidence requires a segments array")
        evidence_by_stable: dict[str, dict[str, Any]] = {}
        for item in evidence_segments:
            if not isinstance(item, dict):
                raise ValueError("Accepted critic segment evidence must be an object")
            stable_id = str(item.get("stable_id", ""))
            if not stable_id or stable_id in evidence_by_stable:
                raise ValueError("Accepted critic evidence contains invalid stable IDs")
            evidence_by_stable[stable_id] = item
        if set(evidence_by_stable) != set(candidate_segments):
            raise ValueError("Accepted critic evidence segment set differs from candidate")
        for stable_id, item in evidence_by_stable.items():
            candidate_projection = critic_delivery_by_stable[stable_id]
            critic_row = critic_row_by_stable[stable_id]
            critic = item.get("critic")
            derived_confidence = item.get("derived_confidence")
            generator_confidence = candidate_segments[stable_id]["data"].get("confidence")
            critic_confidence = critic.get("confidence") if isinstance(critic, dict) else None
            commit_confidence = commit_segments[stable_id]["data"].get("confidence")
            numeric_confidences = (
                generator_confidence,
                critic_confidence,
                confidence_cap,
                derived_confidence,
                commit_confidence,
            )
            critic_fields = {
                *ANALYSIS_CRITIC_DELIVERY_FIELDS,
                "accept",
                "rationale",
                "evidence_quote",
                "confidence",
            }
            evidence_quote = critic.get("evidence_quote") if isinstance(critic, dict) else None
            raw_delivery = (
                {field: critic.get(field) for field in ANALYSIS_CRITIC_DELIVERY_FIELDS}
                if isinstance(critic, dict)
                else {}
            )
            critic_schema_valid = (
                isinstance(critic, dict)
                and set(critic) == critic_fields
                and type(critic.get("accept")) is bool
                and isinstance(critic.get("kind"), str)
                and critic.get("kind") in ANALYSIS_CRITIC_KINDS
                and isinstance(critic.get("speaker"), str)
                and len(critic["speaker"]) <= 120
                and isinstance(critic.get("emotion"), str)
                and critic.get("emotion") in ANALYSIS_CRITIC_EMOTIONS
                and type(critic.get("intensity")) is int
                and 0 <= int(critic["intensity"]) <= 3
                and isinstance(critic.get("pace"), str)
                and critic.get("pace") in ANALYSIS_CRITIC_PACES
                and isinstance(critic.get("volume"), str)
                and critic.get("volume") in ANALYSIS_CRITIC_VOLUMES
                and isinstance(critic.get("rationale"), str)
                and sum(character.isalpha() for character in critic["rationale"]) >= 4
                and len(critic["rationale"]) <= 200
                and type(critic.get("confidence")) in {int, float}
                and math.isfinite(float(critic["confidence"]))
                and 0.0 <= float(critic["confidence"]) <= ANALYSIS_CRITIC_CONFIDENCE_MAX
            )
            if (
                critic_schema_valid
                and critic["emotion"]
                in rejected_emotions_by_batch.get(str(critic_row["id"]), frozenset())
            ):
                raise RuntimeError(
                    "Accepted critic evidence violates its retry emotion schema"
                )
            raw_deltas = [
                f"{field}:{candidate_projection[field]}->{raw_delivery[field]}"
                for field in ANALYSIS_CRITIC_DELIVERY_FIELDS
                if raw_delivery.get(field) != candidate_projection[field]
            ]
            raw_delta_fields = {
                field
                for field in ANALYSIS_CRITIC_DELIVERY_FIELDS
                if raw_delivery.get(field) != candidate_projection[field]
            }
            # Acceptance is decided on the same subset analysis decided it on. `raw_deltas`
            # stays the complete record - that is evidence and it is verified in full -
            # but a difference confined to a field nobody can hear was never a reason to
            # reject the candidate, and recomputing acceptance from the full list is what
            # made the two halves disagree and ended a run twice at the same segment.
            blocking_delta_fields = set(
                critic_delta_fields(AFFECT_CUE_DISAGREEMENT_BLOCKS)
            )
            derived_accept = host_derived_accept(raw_deltas)
            raw_agreement = (
                isinstance(critic, dict)
                and critic.get("accept") is derived_accept
                and derived_accept
            )
            raw_accept_value = critic.get("accept") if isinstance(critic, dict) else None
            is_heading = (
                critic_row["source_role"] == ANALYSIS_SOURCE_ROLE_CHAPTER_HEADING
            )
            structural_override = item.get("host_structural_override")
            expected_structural_override = (
                {
                    "policy_version": ANALYSIS_HOST_STRUCTURAL_POLICY_VERSION,
                    "stable_id": stable_id,
                    "text_sha256": str(candidate_segments[stable_id]["text_sha256"]),
                    "source_role": ANALYSIS_SOURCE_ROLE_CHAPTER_HEADING,
                    "context_policy": ANALYSIS_CONTEXT_POLICY_TARGET_ONLY,
                    "locked_fields": ANALYSIS_CHAPTER_HEADING_DELIVERY,
                    "locked_confidence": ANALYSIS_CHAPTER_HEADING_CONFIDENCE,
                    "raw_accept": raw_accept_value,
                    "raw_field_deltas": raw_deltas,
                }
                if is_heading and raw_accept_value is False and raw_deltas
                else None
            )
            structural_override_valid = (
                is_heading
                and raw_accept_value is False
                and bool(raw_deltas)
                and structural_override == expected_structural_override
            )
            semantic_lock = semantic_locks.get(stable_id)
            semantic_override = item.get("host_semantic_override")
            semantic_field = (
                str(semantic_lock["field"])
                if semantic_lock is not None
                else ""
            )
            semantic_allowed_values = (
                list(semantic_lock["allowed_emotions"])
                if semantic_lock is not None
                else []
            )
            semantic_rule_contract = (
                ANALYSIS_HOST_SEMANTIC_RULE_CONTRACTS.get(str(semantic_lock["rule"]))
                if semantic_lock is not None
                else None
            )
            semantic_rule_protects_source_kind = bool(
                semantic_rule_contract is not None
                and semantic_rule_contract.get("protects_source_kind", False)
            )
            context_kind_lock = context_kind_locks.get(stable_id)
            source_kind_is_protected = bool(
                context_kind_lock is not None or semantic_rule_protects_source_kind
            )
            expected_semantic_override = (
                {
                    "policy_version": ANALYSIS_HOST_SEMANTIC_POLICY_VERSION,
                    "stable_id": stable_id,
                    "text_sha256": str(candidate_segments[stable_id]["text_sha256"]),
                    "rule": semantic_lock["rule"],
                    "field": semantic_field,
                    "candidate_value": semantic_lock["candidate_emotion"],
                    "allowed_values": semantic_allowed_values,
                    "raw_accept": False,
                    "raw_field_deltas": raw_deltas,
                }
                if (
                    semantic_lock is not None
                    and raw_accept_value is False
                    and bool(raw_delta_fields)
                    and (
                        raw_delta_fields <= {semantic_field}
                        or (
                            source_kind_is_protected
                            and semantic_field in raw_delta_fields
                        )
                    )
                    and raw_delivery.get(semantic_field)
                    not in semantic_allowed_values
                )
                else None
            )
            semantic_override_valid = (
                expected_semantic_override is not None
                and semantic_override == expected_semantic_override
            )
            source_kind_override = item.get("host_source_kind_override")
            expected_source_kind_override = (
                cls._analysis_expected_source_kind_override_conn(
                    conn,
                    candidate_segment=candidate_segments[stable_id],
                    critic_row=critic_row,
                    critic_delivery=raw_delivery,
                    raw_deltas=raw_deltas,
                    semantic_lock=semantic_lock,
                    context_kind_lock=context_kind_lock,
                )
                if raw_accept_value is False
                else None
            )
            source_kind_override_valid = (
                expected_source_kind_override is not None
                and source_kind_override == expected_source_kind_override
            )
            critic_compatibility_override = item.get(
                "host_critic_compatibility_override"
            )
            expected_critic_compatibility_override = (
                analysis_expected_critic_compatibility_override(
                    stable_id=stable_id,
                    source_text=str(critic_row["text"]),
                    text_sha256=str(candidate_segments[stable_id]["text_sha256"]),
                    source_kind=str(critic_row["hint"]),
                    candidate=candidate_projection,
                    critic=raw_delivery,
                    raw_deltas=raw_deltas,
                )
                if raw_accept_value is False
                else None
            )
            critic_compatibility_override_valid = (
                expected_critic_compatibility_override is not None
                and critic_compatibility_override
                == expected_critic_compatibility_override
            )
            covered_override_fields = (
                set(raw_delta_fields)
                if (
                    structural_override_valid
                    or critic_compatibility_override_valid
                )
                else {
                    field
                    for field, valid in (
                        (semantic_field, semantic_override_valid),
                        ("kind", source_kind_override_valid),
                    )
                    if field and valid
                }
            )
            unresolved_override_fields = raw_delta_fields - covered_override_fields
            override_resolution_valid = (
                bool(covered_override_fields)
                and not unresolved_override_fields
            )
            if (
                str(item.get("text_sha256", ""))
                != str(candidate_segments[stable_id]["text_sha256"])
                or item.get("candidate") != candidate_projection
                or not critic_schema_valid
                or not analysis_critic_speaker_is_candidate_bound(
                    critic.get("speaker") if isinstance(critic, dict) else None,
                    candidate_speakers,
                )
                or not isinstance(evidence_quote, str)
                or not evidence_quote.strip()
                or len(evidence_quote) > ANALYSIS_CRITIC_EVIDENCE_QUOTE_MAX_LENGTH
                or (
                    evidence_policy
                    == ANALYSIS_CRITIC_EVIDENCE_POLICY_SINGLETON_FULL_TARGET
                    and evidence_quote != str(critic_row["text"])
                )
                or (
                    evidence_policy
                    == ANALYSIS_CRITIC_EVIDENCE_POLICY_SINGLETON_SOURCE_ANCHOR
                    and evidence_quote not in singleton_source_anchors
                )
                or (
                    evidence_policy
                    == ANALYSIS_CRITIC_EVIDENCE_POLICY_PER_ID_SOURCE_ANCHOR
                    and evidence_quote
                    not in per_id_source_anchors.get(str(critic_row["id"]), frozenset())
                )
                or critic.get("accept") is not derived_accept
                or item.get("field_deltas") != raw_deltas
                or item.get("effective_accept") is not True
                or (
                    raw_agreement
                    # An override that resolves only inaudible fields is redundant once
                    # those stop blocking, not contradictory: the evidence was recorded
                    # under a policy where they did block, and rejecting it would refuse
                    # every project committed before the policy changed. An override that
                    # claims a field still capable of blocking is a different matter and
                    # cannot coexist with agreement.
                    and bool(covered_override_fields & blocking_delta_fields)
                )
                or (
                    not raw_agreement
                    and not override_resolution_valid
                )
                or (
                    structural_override is not None
                    and not structural_override_valid
                )
                or (
                    semantic_override is not None
                    and not semantic_override_valid
                )
                or (
                    source_kind_override is not None
                    and not source_kind_override_valid
                )
                or (
                    critic_compatibility_override is not None
                    and not critic_compatibility_override_valid
                )
                or any(type(value) not in {int, float} for value in numeric_confidences)
                or any(not math.isfinite(float(value)) for value in numeric_confidences)
                or any(
                    float(value) < confidence_floor
                    for value in (
                        generator_confidence,
                        critic_confidence,
                        derived_confidence,
                        commit_confidence,
                    )
                )
                or float(derived_confidence)
                != (
                    ANALYSIS_CHAPTER_HEADING_CONFIDENCE
                    if is_heading
                    else min(
                        float(generator_confidence),
                        float(critic_confidence),
                        float(confidence_cap),
                    )
                )
                or float(commit_confidence) != float(derived_confidence)
            ):
                # Name the clause that failed. The bare message cost a debugging round:
                # a dozen conditions share it, so it says a binding broke without saying
                # which, and the evidence that failed is in memory rather than on disk.
                reasons = [
                    name
                    for name, failed in (
                        ("text_sha256", str(item.get("text_sha256", ""))
                         != str(candidate_segments[stable_id]["text_sha256"])),
                        ("candidate_projection", item.get("candidate") != candidate_projection),
                        ("critic_schema", not critic_schema_valid),
                        ("accept_flag", critic.get("accept") is not derived_accept),
                        ("field_deltas", item.get("field_deltas") != raw_deltas),
                        ("effective_accept", item.get("effective_accept") is not True),
                        ("agreement_with_override", bool(
                            raw_agreement
                            and (
                                structural_override is not None
                                or semantic_override is not None
                                or source_kind_override is not None
                                or critic_compatibility_override is not None
                            )
                        )),
                        ("unresolved_disagreement", bool(
                            not raw_agreement and not override_resolution_valid
                        )),
                        ("structural_override", structural_override is not None
                         and not structural_override_valid),
                        ("semantic_override", semantic_override is not None
                         and not semantic_override_valid),
                        ("source_kind_override", source_kind_override is not None
                         and not source_kind_override_valid),
                        ("compatibility_override", critic_compatibility_override is not None
                         and not critic_compatibility_override_valid),
                    )
                    if failed
                ]
                raise RuntimeError(
                    "Accepted critic evidence does not bind exact delivery/confidence for "
                    f"{stable_id}: {', '.join(reasons) or 'confidence'}; "
                    f"deltas={item.get('field_deltas')!r} expected={raw_deltas!r}"
                )

    @classmethod
    def _validate_analysis_rejection_evidence(
        cls,
        conn: sqlite3.Connection,
        candidate_json: str,
        evidence: dict[str, Any],
        outcome: dict[str, Any],
        reserved_contract_json: str,
        deterministic_issue_json: str,
    ) -> None:
        candidate = json.loads(candidate_json)
        evidence_segments = evidence.get("segments")
        try:
            reserved_contract = json.loads(reserved_contract_json)
        except json.JSONDecodeError as exc:
            raise RuntimeError("Reserved critic contract JSON is invalid") from exc
        canonical_reserved_contract, _reserved_contract_hash = cls._canonical_analysis_json(
            reserved_contract,
            "reserved analysis critic contract",
        )
        critic_contract = evidence.get("critic_contract")
        if not isinstance(critic_contract, dict):
            raise RuntimeError(
                "Rejected critic evidence requires its durable critic contract"
            )
        canonical_evidence_contract, _evidence_contract_hash = cls._canonical_analysis_json(
            critic_contract,
            "rejected critic evidence contract",
        )
        if canonical_evidence_contract != canonical_reserved_contract:
            raise RuntimeError(
                "Rejected critic evidence contract differs from the reserved request contract"
            )
        confidence_floor, confidence_cap = cls._analysis_critic_confidence_bounds(
            critic_contract,
            durable=True,
            candidate_json=candidate_json,
        )
        critic_rows = candidate["critic_rows"]
        candidate_speakers = tuple(
            critic_row["candidate"]["speaker"] for critic_row in critic_rows
        )
        candidate_hash = analysis_critic_candidate_hash(
            critic_rows,
            critic_contract["rejected_emotions_by_id"],
        )
        if str(evidence.get("candidate_hash", "")) != candidate_hash:
            raise RuntimeError("Rejected critic evidence candidate hash is invalid")
        rejected_emotions_by_batch = {
            str(item["id"]): frozenset(str(value) for value in item["emotions"])
            for item in critic_contract["rejected_emotions_by_id"]
        }
        evidence_policy = str(critic_contract["evidence_policy"])
        singleton_source_anchors = frozenset(
            canonical_analysis_critic_source_anchors(str(critic_rows[0]["text"]))
            if evidence_policy
            == ANALYSIS_CRITIC_EVIDENCE_POLICY_SINGLETON_SOURCE_ANCHOR
            else ()
        )
        per_id_source_anchors = {
            str(item["id"]): frozenset(item["anchors"])
            for item in (
                canonical_analysis_critic_per_id_source_anchor_map(critic_rows)
                if evidence_policy
                == ANALYSIS_CRITIC_EVIDENCE_POLICY_PER_ID_SOURCE_ANCHOR
                else ()
            )
        }
        if not isinstance(evidence_segments, list):
            raise RuntimeError("Rejected critic evidence requires a segments array")
        evidence_by_stable: dict[str, dict[str, Any]] = {}
        for item in evidence_segments:
            if not isinstance(item, dict):
                raise RuntimeError("Rejected critic segment evidence must be an object")
            stable_id = str(item.get("stable_id", ""))
            if not stable_id or stable_id in evidence_by_stable:
                raise RuntimeError(
                    "Rejected critic evidence contains invalid stable IDs"
                )
            evidence_by_stable[stable_id] = item
        candidate_segments = {
            str(item["stable_id"]): item for item in candidate["segments"]
        }
        critic_row_by_stable = {
            str(segment["stable_id"]): critic_row
            for segment, critic_row in zip(
                candidate["segments"],
                critic_rows,
                strict=True,
            )
        }
        if set(evidence_by_stable) != set(candidate_segments):
            raise RuntimeError(
                "Rejected critic evidence segment set differs from candidate"
            )
        critic_fields = {
            *ANALYSIS_CRITIC_DELIVERY_FIELDS,
            "accept",
            "rationale",
            "evidence_quote",
            "confidence",
        }
        raw_deltas_by_stable: dict[str, list[str]] = {}
        raw_delta_fields_by_stable: dict[str, set[str]] = {}
        for stable_id, item in evidence_by_stable.items():
            candidate_segment = candidate_segments[stable_id]
            critic_row = critic_row_by_stable[stable_id]
            candidate_projection = dict(critic_row["candidate"])
            critic = item.get("critic")
            evidence_quote = (
                critic.get("evidence_quote") if isinstance(critic, dict) else None
            )
            critic_confidence = (
                critic.get("confidence") if isinstance(critic, dict) else None
            )
            generator_confidence = candidate_segment["data"].get("confidence")
            derived_confidence = item.get("derived_confidence")
            numeric_confidences = (
                generator_confidence,
                critic_confidence,
                derived_confidence,
            )
            critic_schema_valid = (
                isinstance(critic, dict)
                and set(critic) == critic_fields
                and type(critic.get("accept")) is bool
                and isinstance(critic.get("kind"), str)
                and critic.get("kind") in ANALYSIS_CRITIC_KINDS
                and isinstance(critic.get("speaker"), str)
                and len(critic["speaker"]) <= 120
                and isinstance(critic.get("emotion"), str)
                and critic.get("emotion") in ANALYSIS_CRITIC_EMOTIONS
                and type(critic.get("intensity")) is int
                and 0 <= int(critic["intensity"]) <= 3
                and isinstance(critic.get("pace"), str)
                and critic.get("pace") in ANALYSIS_CRITIC_PACES
                and isinstance(critic.get("volume"), str)
                and critic.get("volume") in ANALYSIS_CRITIC_VOLUMES
                and isinstance(critic.get("rationale"), str)
                and sum(character.isalpha() for character in critic["rationale"]) >= 4
                and len(critic["rationale"]) <= 200
                and type(critic_confidence) in {int, float}
                and math.isfinite(float(critic_confidence))
                and confidence_floor
                <= float(critic_confidence)
                <= ANALYSIS_CRITIC_CONFIDENCE_MAX
            )
            if not critic_schema_valid:
                raise RuntimeError(
                    "Rejected critic evidence has invalid segment schema"
                )
            if not analysis_critic_speaker_is_candidate_bound(
                critic["speaker"],
                candidate_speakers,
            ):
                raise RuntimeError(
                    "Rejected critic evidence has invalid speaker provenance"
                )
            if critic["emotion"] in rejected_emotions_by_batch.get(
                str(critic_row["id"]),
                frozenset(),
            ):
                raise RuntimeError(
                    "Rejected critic evidence violates its retry emotion schema"
                )
            raw_delivery = {
                field: critic[field] for field in ANALYSIS_CRITIC_DELIVERY_FIELDS
            }
            raw_deltas = [
                f"{field}:{candidate_projection[field]}->{raw_delivery[field]}"
                for field in ANALYSIS_CRITIC_DELIVERY_FIELDS
                if raw_delivery[field] != candidate_projection[field]
            ]
            expected_derived_confidence = (
                ANALYSIS_CHAPTER_HEADING_CONFIDENCE
                if critic_row["source_role"] == ANALYSIS_SOURCE_ROLE_CHAPTER_HEADING
                else min(
                    float(generator_confidence),
                    float(critic_confidence),
                    float(confidence_cap),
                )
            )
            quote_valid = (
                isinstance(evidence_quote, str)
                and bool(evidence_quote.strip())
                and len(evidence_quote) <= ANALYSIS_CRITIC_EVIDENCE_QUOTE_MAX_LENGTH
                and (
                    evidence_policy
                    != ANALYSIS_CRITIC_EVIDENCE_POLICY_SINGLETON_FULL_TARGET
                    or evidence_quote == str(critic_row["text"])
                )
                and (
                    evidence_policy
                    != ANALYSIS_CRITIC_EVIDENCE_POLICY_SINGLETON_SOURCE_ANCHOR
                    or evidence_quote in singleton_source_anchors
                )
                and (
                    evidence_policy
                    != ANALYSIS_CRITIC_EVIDENCE_POLICY_PER_ID_SOURCE_ANCHOR
                    or evidence_quote
                    in per_id_source_anchors.get(str(critic_row["id"]), frozenset())
                )
            )
            if (
                str(item.get("text_sha256", ""))
                != str(candidate_segment["text_sha256"])
                or item.get("candidate") != candidate_projection
                or item.get("field_deltas") != raw_deltas
                or not rejected_accept_flag_is_coherent(
                    critic.get("accept"), raw_deltas
                )
                or type(item.get("effective_accept")) is not bool
                or not quote_valid
                or any(type(value) not in {int, float} for value in numeric_confidences)
                or any(not math.isfinite(float(value)) for value in numeric_confidences)
                or any(float(value) < confidence_floor for value in numeric_confidences)
                or float(derived_confidence) != expected_derived_confidence
            ):
                # Name the clause that failed, exactly as the accepted branch already does.
                # Eleven conditions share this message, so on its own it says a binding
                # broke without saying which - and the evidence is in memory, not on disk,
                # so a rerun is the only way to look. That cost a debugging round once
                # already on the sibling check.
                reasons = [
                    name
                    for name, failed in (
                        ("text_sha256", str(item.get("text_sha256", ""))
                         != str(candidate_segment["text_sha256"])),
                        ("candidate_projection", item.get("candidate") != candidate_projection),
                        ("field_deltas", item.get("field_deltas") != raw_deltas),
                        ("accept_flag", not rejected_accept_flag_is_coherent(
                            critic.get("accept"), raw_deltas
                        )),
                        ("effective_accept_type",
                         type(item.get("effective_accept")) is not bool),
                        ("evidence_quote", not quote_valid),
                        ("confidence_type", any(
                            type(value) not in {int, float} for value in numeric_confidences
                        )),
                        ("confidence_finite", any(
                            not math.isfinite(float(value)) for value in numeric_confidences
                        )),
                        ("confidence_floor", any(
                            float(value) < confidence_floor for value in numeric_confidences
                        )),
                        ("derived_confidence",
                         float(derived_confidence) != expected_derived_confidence),
                    )
                    if failed
                ]
                raise RuntimeError(
                    "Rejected critic evidence is not exactly candidate-bound for "
                    f"{stable_id}: {', '.join(reasons) or 'unknown'}; "
                    f"deltas={item.get('field_deltas')!r} expected={raw_deltas!r}; "
                    f"accept={critic.get('accept')!r} confidences={numeric_confidences!r} "
                    f"derived={derived_confidence!r} expected_derived="
                    f"{expected_derived_confidence!r}"
                )
            raw_deltas_by_stable[stable_id] = raw_deltas
            raw_delta_fields_by_stable[stable_id] = {
                delta.split(":", 1)[0] for delta in raw_deltas
            }
        structural_locks, semantic_locks, context_kind_locks = (
            cls._analysis_host_lock_contract(
                candidate_json,
                deterministic_issue_json,
            )
        )
        semantic_source_kind_ids = {
            stable_id
            for stable_id, lock in semantic_locks.items()
            if bool(
                ANALYSIS_HOST_SEMANTIC_RULE_CONTRACTS[str(lock["rule"])].get(
                    "protects_source_kind",
                    False,
                )
            )
        }
        protected_ids = set(context_kind_locks) | semantic_source_kind_ids
        if (
            any(
                item.get("host_source_kind_override") is not None
                for stable_id, item in evidence_by_stable.items()
                if stable_id not in protected_ids
            )
            or any(
                item.get("host_semantic_override") is not None
                for stable_id, item in evidence_by_stable.items()
                if stable_id not in semantic_locks
            )
            or any(
                item.get("host_structural_override") is not None
                for stable_id, item in evidence_by_stable.items()
                if stable_id not in structural_locks
            )
        ):
            raise RuntimeError(
                "Rejected source-kind critic evidence contains an unprotected override"
            )
        unresolved_fields_by_stable: dict[str, list[str]] = {}
        refused_ids: set[str] = set()
        for stable_id, item in evidence_by_stable.items():
            critic_row = critic_row_by_stable[stable_id]
            candidate_projection = critic_row["candidate"]
            critic = item.get("critic")
            raw_deltas = raw_deltas_by_stable[stable_id]
            raw_delta_fields = raw_delta_fields_by_stable[stable_id]
            expected_critic_compatibility_override = (
                analysis_expected_critic_compatibility_override(
                    stable_id=stable_id,
                    source_text=str(critic_row["text"]),
                    text_sha256=str(candidate_segments[stable_id]["text_sha256"]),
                    source_kind=str(critic_row["hint"]),
                    candidate=candidate_projection,
                    critic=critic,
                    raw_deltas=raw_deltas,
                )
                if raw_deltas
                else None
            )
            critic_compatibility_override = item.get(
                "host_critic_compatibility_override"
            )
            if (
                critic_compatibility_override
                != expected_critic_compatibility_override
            ):
                raise RuntimeError(
                    "Rejected critic evidence contains a compatibility override "
                    "that is not source-bound"
                )
            structural_lock = structural_locks.get(stable_id)
            if structural_lock is not None:
                expected_structural_override = (
                    {
                        "policy_version": ANALYSIS_HOST_STRUCTURAL_POLICY_VERSION,
                        "stable_id": stable_id,
                        "text_sha256": str(candidate_segments[stable_id]["text_sha256"]),
                        "source_role": ANALYSIS_SOURCE_ROLE_CHAPTER_HEADING,
                        "context_policy": ANALYSIS_CONTEXT_POLICY_TARGET_ONLY,
                        "locked_fields": ANALYSIS_CHAPTER_HEADING_DELIVERY,
                        "locked_confidence": ANALYSIS_CHAPTER_HEADING_CONFIDENCE,
                        "raw_accept": False,
                        "raw_field_deltas": raw_deltas,
                    }
                    if raw_deltas
                    else None
                )
                if (
                    item.get("host_structural_override")
                    != expected_structural_override
                    or item.get("host_semantic_override") is not None
                    or item.get("host_source_kind_override") is not None
                    or item.get("effective_accept") is not True
                ):
                    raise RuntimeError(
                        "Rejected structural critic override is not source-bound"
                    )
                unresolved_fields_by_stable[stable_id] = []
                continue
            semantic_lock = semantic_locks.get(stable_id)
            context_kind_lock = context_kind_locks.get(stable_id)
            expected_source_kind_override = (
                cls._analysis_expected_source_kind_override_conn(
                    conn,
                    candidate_segment=candidate_segments[stable_id],
                    critic_row=critic_row,
                    critic_delivery=critic,
                    raw_deltas=raw_deltas,
                    semantic_lock=semantic_lock,
                    context_kind_lock=context_kind_lock,
                )
            )
            allowed_emotions = (
                list(semantic_lock["allowed_emotions"])
                if semantic_lock is not None
                else []
            )
            semantic_rule_contract = (
                ANALYSIS_HOST_SEMANTIC_RULE_CONTRACTS.get(
                    str(semantic_lock["rule"])
                )
                if semantic_lock is not None
                else None
            )
            source_kind_is_protected = bool(
                context_kind_lock is not None
                or (
                    semantic_rule_contract is not None
                    and semantic_rule_contract.get("protects_source_kind", False)
                )
            )
            expected_semantic_override = (
                {
                    "policy_version": ANALYSIS_HOST_SEMANTIC_POLICY_VERSION,
                    "stable_id": stable_id,
                    "text_sha256": str(candidate_segments[stable_id]["text_sha256"]),
                    "rule": semantic_lock["rule"],
                    "field": "emotion",
                    "candidate_value": semantic_lock["candidate_emotion"],
                    "allowed_values": allowed_emotions,
                    "raw_accept": False,
                    "raw_field_deltas": raw_deltas,
                }
                if (
                    semantic_lock is not None
                    and "emotion" in raw_delta_fields
                    and (
                        raw_delta_fields <= {"emotion"}
                        or source_kind_is_protected
                    )
                    and candidate_projection["emotion"]
                    == semantic_lock["candidate_emotion"]
                    and critic.get("emotion") not in allowed_emotions
                )
                else None
            )
            source_kind_override_valid = (
                item.get("host_source_kind_override")
                == expected_source_kind_override
            )
            semantic_override_valid = (
                item.get("host_semantic_override") == expected_semantic_override
            )
            covered_fields = {
                field
                for field, valid in (
                    ("kind", source_kind_override_valid),
                    ("emotion", semantic_override_valid),
                )
                if valid
                and (
                    (field == "kind" and expected_source_kind_override is not None)
                    or (field == "emotion" and expected_semantic_override is not None)
                )
            }
            if expected_critic_compatibility_override is not None:
                covered_fields.update(raw_delta_fields)
            # Deliberately every delivery field, not the blocking subset. This is
            # evidence bookkeeping - "the critic disagreed here and no override explains
            # it" - and an inaudible field can be unresolved without being a reason to
            # refuse anything. Narrowing it to the blocking subset broke four tests that
            # exist precisely to keep affect deltas visible as unresolved.
            unresolved_fields = [
                field
                for field in ANALYSIS_CRITIC_DELIVERY_FIELDS
                if field in raw_delta_fields and field not in covered_fields
            ]
            # Bookkeeping and verdict are different questions over the same list.
            # `unresolved_fields` records every field the critic disagreed on that no
            # override explains, affect included, because four tests exist to keep those
            # visible. Acceptance is decided only on the fields a disagreement can block
            # on - the same subset host_derived_accept uses - because a difference nobody
            # can hear was never grounds to refuse a candidate.
            #
            # Narrowing the list itself was tried first and broke the bookkeeping. The two
            # have to stay separate.
            if (
                not source_kind_override_valid
                or not semantic_override_valid
                or not accept_flag_is_coherent(
                    item.get("effective_accept"), unresolved_fields
                )
                or item.get("host_structural_override") is not None
            ):
                # Name the clause, for the same reason as everywhere else in this file:
                # four conditions share the message and the evidence is not on disk.
                reasons = [
                    name
                    for name, failed in (
                        ("source_kind_override", not source_kind_override_valid),
                        ("semantic_override", not semantic_override_valid),
                        ("effective_accept", not accept_flag_is_coherent(
                            item.get("effective_accept"), unresolved_fields
                        )),
                        ("unexpected_structural_override",
                         item.get("host_structural_override") is not None),
                    )
                    if failed
                ]
                raise RuntimeError(
                    "Rejected source-kind critic override is not source-bound for "
                    f"{stable_id}: {', '.join(reasons) or 'unknown'}; "
                    f"unresolved={unresolved_fields!r} covered={sorted(covered_fields)!r} "
                    f"delta_fields={sorted(raw_delta_fields)!r} "
                    f"effective_accept={item.get('effective_accept')!r} "
                    f"blocking={sorted(set(critic_delta_fields(AFFECT_CUE_DISAGREEMENT_BLOCKS)))!r}"
                )
            unresolved_fields_by_stable[stable_id] = unresolved_fields
            if item.get("effective_accept") is False:
                refused_ids.add(stable_id)
        # An issue belongs to a segment the host did not effectively accept - not to
        # every segment with something unresolved, which is what this compared against and
        # what killed the run. In the failing batch four segments had unresolved fields and
        # exactly one issue was raised: the only one whose unresolved set held a blocking
        # field ("pace"), the others differing on emotion and intensity alone.
        #
        # Reading it off effective_accept rather than re-deriving it from the fields also
        # covers the legal case a blocking-subset rule got wrong: a host may refuse over an
        # inaudible difference, and then the issue is real however quiet the field.
        # `unresolved_fields_by_stable` stays the complete record; that is evidence.
        unresolved_ids = set(refused_ids)
        if not unresolved_ids:
            raise RuntimeError(
                "Rejected critic evidence has no unresolved segment"
            )
        issues = outcome.get("issues")
        if (
            set(outcome) != {"issues", "retryable_invalid"}
            or outcome.get("retryable_invalid") is not False
            or not isinstance(issues, dict)
            or not issues
            or set(issues) != unresolved_ids
        ):
            # Name the clause. Five conditions share this message and the outcome is not
            # on disk, so without this the only way to learn which broke is another full
            # analysis pass - which has cost three already in this validator alone.
            reasons = [
                name
                for name, failed in (
                    ("outcome_keys", set(outcome) != {"issues", "retryable_invalid"}),
                    ("retryable_invalid",
                     outcome.get("retryable_invalid") is not False),
                    ("issues_type", not isinstance(issues, dict)),
                    ("issues_empty", isinstance(issues, dict) and not issues),
                    ("issue_ids", isinstance(issues, dict)
                     and set(issues) != unresolved_ids),
                )
                if failed
            ]
            issue_ids = sorted(issues) if isinstance(issues, dict) else issues
            raise RuntimeError(
                "Rejected critic outcome does not match unresolved evidence: "
                f"{', '.join(reasons) or 'unknown'}; "
                f"outcome_keys={sorted(outcome)!r} issues={issue_ids!r} "
                f"unresolved={sorted(unresolved_ids)!r} "
                f"unresolved_fields={ {k: v for k, v in unresolved_fields_by_stable.items() if v} !r}"
            )
        for stable_id, fields in unresolved_fields_by_stable.items():
            # Same set as above: a segment with nothing blocking has no issue to match.
            # The reason string still names every unresolved field, blocking or not - the
            # evidence showed which segments carry an issue, not what the text says.
            if stable_id not in unresolved_ids:
                continue
            expected_reason = "DIRECTOR_FIELD_MISMATCH fields=" + ",".join(fields)
            if issues.get(stable_id) != expected_reason:
                raise RuntimeError(
                    "Rejected critic outcome is not a substantive field mismatch for "
                    f"{stable_id}: got {issues.get(stable_id)!r} "
                    f"expected {expected_reason!r}"
                )

    @classmethod
    def _validated_analysis_commit_envelope(
        cls,
        candidate_json: str,
        commit_envelope: dict[str, Any],
    ) -> tuple[str, str]:
        commit_json, commit_hash = cls._canonical_analysis_json(
            commit_envelope,
            "analysis commit envelope",
        )
        candidate_rows = cls._analysis_candidate_commit_rows(candidate_json)
        commit_rows = cls._analysis_candidate_commit_rows(commit_json)
        candidate = json.loads(candidate_json)
        commit = json.loads(commit_json)
        for field in ("critic_rows", "pronunciations"):
            candidate_field_json, _candidate_field_hash = cls._canonical_analysis_json(
                candidate[field],
                f"analysis candidate {field}",
            )
            commit_field_json, _commit_field_hash = cls._canonical_analysis_json(
                commit[field],
                f"analysis commit {field}",
            )
            if candidate_field_json != commit_field_json:
                raise RuntimeError(
                    f"Analysis commit envelope changed immutable {field}"
                )
        if set(candidate_rows) != set(commit_rows):
            raise RuntimeError("Analysis commit envelope changed the candidate segment set")
        candidate_segments = {
            str(item["stable_id"]): item for item in candidate["segments"]
        }
        commit_segments = {
            str(item["stable_id"]): item for item in commit["segments"]
        }
        for stable_id, candidate_row in candidate_rows.items():
            commit_row = commit_rows[stable_id]
            if (
                int(candidate_row["segment_id"]) != int(commit_row["segment_id"])
                or str(candidate_row["text_sha256"]) != str(commit_row["text_sha256"])
            ):
                raise RuntimeError(
                    "Analysis commit envelope changed segment source provenance"
                )
            candidate_data = dict(candidate_segments[stable_id]["data"])
            commit_data = dict(commit_segments[stable_id]["data"])
            candidate_confidence = candidate_data.pop("confidence")
            commit_confidence = commit_data.pop("confidence")
            if candidate_data != commit_data:
                raise RuntimeError(
                    "Analysis commit envelope changed critic-visible delivery data"
                )
            if (
                type(candidate_confidence) not in {int, float}
                or type(commit_confidence) not in {int, float}
                or not 0.0 <= float(commit_confidence) <= float(candidate_confidence) <= 1.0
            ):
                raise RuntimeError(
                    "Analysis commit envelope confidence is not a bounded critic cap"
                )
        return commit_json, commit_hash

    @classmethod
    def _analysis_candidate_row_conn(
        cls,
        conn: sqlite3.Connection,
        analysis_candidate_id: int,
        *,
        validate_completed_acceptance: bool = True,
    ) -> sqlite3.Row:
        row = conn.execute(
            "SELECT * FROM analysis_candidates WHERE id=?",
            (int(analysis_candidate_id),),
        ).fetchone()
        if row is None:
            raise KeyError(f"Unknown analysis candidate id: {analysis_candidate_id}")
        try:
            candidate = json.loads(str(row["candidate_json"]))
            generator_contract = json.loads(
                str(row["initial_generator_contract_json"])
            )
            deterministic_issues = json.loads(str(row["deterministic_issue_json"]))
        except json.JSONDecodeError as exc:
            raise RuntimeError("Analysis candidate ledger contains invalid JSON") from exc
        candidate_json, envelope_hash = cls._canonical_analysis_json(
            candidate,
            "stored analysis candidate",
        )
        cls._analysis_candidate_commit_rows(candidate_json)
        generator_json, generator_hash = cls._canonical_analysis_json(
            generator_contract,
            "stored analysis generator contract",
        )
        generator_rejections = cls._analysis_generator_rejected_emotion_contract(
            candidate_json,
            generator_contract,
            durable=True,
        )
        candidate_hash = analysis_critic_candidate_hash(
            candidate["critic_rows"],
            generator_rejections,
        )
        issue_json, issue_hash = cls._canonical_analysis_json(
            deterministic_issues,
            "stored deterministic analysis issues",
        )
        cls._validate_analysis_candidate_sources_conn(
            conn,
            candidate_json,
            issue_json,
            str(row["context_hash"]),
        )
        if (
            str(row["candidate_json"]) != candidate_json
            or str(row["candidate_hash"]) != candidate_hash
            or str(row["envelope_hash"]) != envelope_hash
            or str(row["initial_generator_contract_json"]) != generator_json
            or str(row["initial_generator_contract_hash"]) != generator_hash
            or str(row["deterministic_issue_json"]) != issue_json
            or str(row["deterministic_issue_hash"]) != issue_hash
        ):
            raise RuntimeError("Analysis candidate ledger hash verification failed")
        if row["commit_envelope_json"] is not None:
            try:
                commit_envelope = json.loads(str(row["commit_envelope_json"]))
            except json.JSONDecodeError as exc:
                raise RuntimeError("Analysis commit envelope contains invalid JSON") from exc
            commit_json, commit_hash = cls._validated_analysis_commit_envelope(
                candidate_json,
                commit_envelope,
            )
            if (
                str(row["commit_envelope_json"]) != commit_json
                or str(row["commit_envelope_hash"]) != commit_hash
            ):
                raise RuntimeError("Analysis commit envelope hash verification failed")
        if (
            validate_completed_acceptance
            and str(row["state"])
            in {ANALYSIS_CANDIDATE_CRITIC_ACCEPTED, ANALYSIS_CANDIDATE_ACCEPTED}
        ):
            attempt_number = int(row["critic_attempt_count"])
            if attempt_number < 1:
                raise RuntimeError(
                    "Accepted analysis candidate has no completed critic evidence"
                )
            final_attempt = cls._analysis_critic_attempt_row_conn(
                conn,
                analysis_candidate_id,
                attempt_number,
                candidate_row=row,
            )
            final_outcome = json.loads(str(final_attempt["outcome_json"]))
            if (
                str(final_attempt["state"])
                != ANALYSIS_CRITIC_ATTEMPT_COMPLETED
                or str(final_outcome.get("candidate_state", ""))
                != ANALYSIS_CANDIDATE_CRITIC_ACCEPTED
            ):
                raise RuntimeError(
                    "Accepted analysis candidate lacks matching completed critic acceptance"
                )
        return row

    @classmethod
    def _analysis_critic_attempt_row_conn(
        cls,
        conn: sqlite3.Connection,
        analysis_candidate_id: int,
        attempt_number: int,
        *,
        candidate_row: sqlite3.Row | None = None,
    ) -> sqlite3.Row:
        row = conn.execute(
            "SELECT * FROM analysis_critic_attempts "
            "WHERE analysis_candidate_id=? AND attempt_number=?",
            (int(analysis_candidate_id), int(attempt_number)),
        ).fetchone()
        if row is None:
            raise KeyError(
                "Unknown analysis critic attempt: "
                f"candidate={analysis_candidate_id}, attempt={attempt_number}"
            )
        try:
            intent = json.loads(str(row["intent_json"]))
            contract = json.loads(str(row["contract_json"]))
        except json.JSONDecodeError as exc:
            raise RuntimeError("Analysis critic intent ledger contains invalid JSON") from exc
        contract_candidate = candidate_row or conn.execute(
            "SELECT candidate_hash,candidate_json,initial_generator_contract_json "
            "FROM analysis_candidates WHERE id=?",
            (int(analysis_candidate_id),),
        ).fetchone()
        if contract_candidate is None:
            raise RuntimeError("Analysis critic contract has no parent candidate")
        cls._analysis_critic_confidence_bounds(
            contract,
            durable=True,
            candidate_json=str(contract_candidate["candidate_json"]),
        )
        cls._validate_analysis_critic_generator_rejections(
            candidate_json=str(contract_candidate["candidate_json"]),
            generator_contract_json=str(
                contract_candidate["initial_generator_contract_json"]
            ),
            critic_contract=contract,
            durable=True,
        )
        if str(contract.get("candidate_hash", "")) != str(
            contract_candidate["candidate_hash"]
        ):
            raise RuntimeError(
                "Analysis critic contract is not bound to its parent candidate hash"
            )
        intent_json, intent_hash = cls._canonical_analysis_json(
            intent,
            "stored analysis critic intent",
        )
        contract_json, contract_hash = cls._canonical_analysis_json(
            contract,
            "stored analysis critic contract",
        )
        if (
            str(row["intent_json"]) != intent_json
            or str(row["intent_hash"]) != intent_hash
            or str(row["contract_json"]) != contract_json
            or str(row["contract_hash"]) != contract_hash
        ):
            raise RuntimeError("Analysis critic intent hash verification failed")
        if (
            not isinstance(intent, dict)
            or str(intent.get("candidate_hash", ""))
            != str(contract_candidate["candidate_hash"])
        ):
            raise RuntimeError(
                "Analysis critic intent is not bound to its parent candidate hash"
            )
        if str(row["state"]) == ANALYSIS_CRITIC_ATTEMPT_COMPLETED:
            candidate = candidate_row or cls._analysis_candidate_row_conn(
                conn,
                analysis_candidate_id,
                validate_completed_acceptance=False,
            )
            try:
                outcome = json.loads(str(row["outcome_json"]))
                evidence = json.loads(str(row["evidence_json"]))
            except json.JSONDecodeError as exc:
                raise RuntimeError(
                    "Analysis critic completion ledger contains invalid JSON"
                ) from exc
            outcome_json, outcome_hash = cls._canonical_analysis_json(
                outcome,
                "stored analysis critic outcome",
            )
            evidence_json, evidence_hash = cls._canonical_analysis_json(
                evidence,
                "stored analysis critic evidence",
            )
            completion_candidate_state = str(outcome.get("candidate_state", ""))
            outcome_payload = outcome.get("payload")
            if not isinstance(outcome_payload, dict):
                raise RuntimeError("Stored analysis critic outcome payload is invalid")
            if completion_candidate_state not in {
                ANALYSIS_CANDIDATE_CRITIC_INVALID,
                ANALYSIS_CANDIDATE_CRITIC_ACCEPTED,
                ANALYSIS_CANDIDATE_CRITIC_REJECTED,
            }:
                raise RuntimeError(
                    "Stored analysis critic outcome has an invalid candidate state"
                )
            if completion_candidate_state == ANALYSIS_CANDIDATE_CRITIC_ACCEPTED and (
                outcome_payload.get("accepted") is False
                or outcome_payload.get("retryable_invalid") is True
                or bool(outcome_payload.get("issues"))
            ):
                raise RuntimeError(
                    "Accepted analysis critic outcome contradicts its durable state"
                )
            if completion_candidate_state == ANALYSIS_CANDIDATE_CRITIC_INVALID and (
                outcome_payload.get("accepted") is True
                or outcome_payload.get("retryable_invalid") is False
            ):
                raise RuntimeError(
                    "Invalid analysis critic outcome contradicts its durable state"
                )
            completion_envelope_hash = (
                candidate["commit_envelope_hash"]
                if completion_candidate_state == ANALYSIS_CANDIDATE_CRITIC_ACCEPTED
                else None
            )
            _completion_json, completion_hash = cls._canonical_analysis_json(
                {
                    "commit_envelope_hash": completion_envelope_hash,
                    "contract_hash": contract_hash,
                    "evidence_hash": evidence_hash,
                    "intent_hash": intent_hash,
                    "outcome_hash": outcome_hash,
                },
                "stored analysis critic completion",
            )
            if (
                str(row["outcome_json"]) != outcome_json
                or str(row["outcome_hash"]) != outcome_hash
                or str(row["evidence_json"]) != evidence_json
                or str(row["evidence_hash"]) != evidence_hash
                or str(row["completion_hash"]) != completion_hash
            ):
                raise RuntimeError("Analysis critic completion hash verification failed")
            if completion_candidate_state == ANALYSIS_CANDIDATE_CRITIC_ACCEPTED:
                if (
                    candidate["commit_envelope_json"] is None
                    or candidate["deterministic_issue_json"] is None
                ):
                    raise RuntimeError(
                        "Accepted analysis candidate lacks its durable acceptance envelope"
                    )
                cls._validate_analysis_acceptance_evidence(
                    conn,
                    str(candidate["candidate_json"]),
                    str(candidate["commit_envelope_json"]),
                    evidence,
                    contract_json,
                    str(candidate["deterministic_issue_json"]),
                )
            elif completion_candidate_state == ANALYSIS_CANDIDATE_CRITIC_REJECTED:
                cls._validate_analysis_rejection_evidence(
                    conn,
                    str(candidate["candidate_json"]),
                    evidence,
                    outcome_payload,
                    contract_json,
                    str(candidate["deterministic_issue_json"]),
                )
        return row

    @classmethod
    def _validate_analysis_critic_attempt_history_conn(
        cls,
        conn: sqlite3.Connection,
        analysis_candidate_id: int,
        expected_count: int,
        parent_state: str | None = None,
    ) -> list[sqlite3.Row]:
        rows = list(
            conn.execute(
                "SELECT * FROM analysis_critic_attempts "
                "WHERE analysis_candidate_id=? ORDER BY attempt_number",
                (int(analysis_candidate_id),),
            )
        )
        if len(rows) != int(expected_count) or [
            int(row["attempt_number"]) for row in rows
        ] != list(range(1, int(expected_count) + 1)):
            raise RuntimeError("Analysis critic attempt history is not contiguous")
        validated = [
            cls._analysis_critic_attempt_row_conn(
                conn,
                analysis_candidate_id,
                int(row["attempt_number"]),
            )
            for row in rows
        ]
        if not validated:
            if parent_state not in {
                None,
                ANALYSIS_CANDIDATE_ALLOCATED,
                ANALYSIS_CANDIDATE_TERMINAL,
                ANALYSIS_CANDIDATE_SUPERSEDED,
            }:
                raise RuntimeError("Analysis candidate state has no critic attempt history")
            return validated
        last = validated[-1]
        last_state = str(last["state"])
        if parent_state == ANALYSIS_CANDIDATE_CRITIC_IN_FLIGHT:
            if last_state != ANALYSIS_CRITIC_ATTEMPT_RESERVED:
                raise RuntimeError("In-flight analysis candidate lacks a reserved final attempt")
        elif parent_state in {
            ANALYSIS_CANDIDATE_CRITIC_INVALID,
            ANALYSIS_CANDIDATE_CRITIC_REJECTED,
            ANALYSIS_CANDIDATE_CRITIC_ACCEPTED,
        }:
            if last_state != ANALYSIS_CRITIC_ATTEMPT_COMPLETED:
                raise RuntimeError("Analysis candidate final critic attempt is not completed")
            outcome = json.loads(str(last["outcome_json"]))
            if str(outcome.get("candidate_state", "")) != parent_state:
                raise RuntimeError("Analysis candidate state differs from its final critic outcome")
        elif parent_state == ANALYSIS_CANDIDATE_ACCEPTED:
            if last_state != ANALYSIS_CRITIC_ATTEMPT_COMPLETED:
                raise RuntimeError(
                    "Accepted analysis candidate final critic attempt is not completed"
                )
            outcome = json.loads(str(last["outcome_json"]))
            if (
                str(outcome.get("candidate_state", ""))
                != ANALYSIS_CANDIDATE_CRITIC_ACCEPTED
            ):
                raise RuntimeError(
                    "Accepted analysis candidate lacks matching completed critic acceptance"
                )
        elif parent_state in {
            ANALYSIS_CANDIDATE_TERMINAL,
            ANALYSIS_CANDIDATE_SUPERSEDED,
        }:
            final_state_label = (
                "Terminal"
                if parent_state == ANALYSIS_CANDIDATE_TERMINAL
                else "Superseded"
            )
            if last_state == ANALYSIS_CRITIC_ATTEMPT_COMPLETED:
                outcome = json.loads(str(last["outcome_json"]))
                if str(outcome.get("candidate_state", "")) not in {
                    ANALYSIS_CANDIDATE_CRITIC_INVALID,
                    ANALYSIS_CANDIDATE_CRITIC_REJECTED,
                }:
                    raise RuntimeError(
                        f"{final_state_label} analysis candidate has an invalid "
                        "final critic outcome"
                    )
            elif last_state != ANALYSIS_CRITIC_ATTEMPT_ABANDONED:
                raise RuntimeError(
                    f"{final_state_label} analysis candidate has an invalid "
                    "final critic attempt"
                )
        elif parent_state == ANALYSIS_CANDIDATE_ALLOCATED:
            raise RuntimeError(
                "Allocated analysis candidate has critic attempt history"
            )
        elif parent_state is not None:
            raise RuntimeError("Unsupported analysis candidate parent state")
        for prior in validated[:-1]:
            if str(prior["state"]) == ANALYSIS_CRITIC_ATTEMPT_COMPLETED:
                outcome = json.loads(str(prior["outcome_json"]))
                if str(outcome.get("candidate_state", "")) != ANALYSIS_CANDIDATE_CRITIC_INVALID:
                    raise RuntimeError("Non-final critic completion is not a retryable invalid result")
            elif str(prior["state"]) != ANALYSIS_CRITIC_ATTEMPT_ABANDONED:
                raise RuntimeError("Non-final critic attempt has an invalid durable state")
        return validated

    @classmethod
    def _analysis_generator_contract_row(
        cls,
        row: sqlite3.Row,
    ) -> sqlite3.Row:
        try:
            contract = json.loads(str(row["generator_contract_json"]))
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                "Analysis generator contract ledger contains invalid JSON"
            ) from exc
        contract_json, contract_hash = cls._canonical_analysis_json(
            contract,
            "stored analysis generator contract",
        )
        if (
            str(row["generator_contract_json"]) != contract_json
            or str(row["generator_contract_hash"]) != contract_hash
        ):
            raise RuntimeError("Analysis generator contract hash verification failed")
        return row

    @classmethod
    def _validate_analysis_generator_contract_history_conn(
        cls,
        conn: sqlite3.Connection,
        analysis_candidate_id: int,
        *,
        require_nonempty: bool = True,
    ) -> list[sqlite3.Row]:
        rows = list(
            conn.execute(
                "SELECT * FROM analysis_candidate_generator_contracts "
                "WHERE analysis_candidate_id=? ORDER BY id",
                (int(analysis_candidate_id),),
            )
        )
        if require_nonempty and not rows:
            raise RuntimeError("Analysis candidate has no generator contract history")
        candidate = conn.execute(
            "SELECT candidate_json,initial_generator_contract_json,"
            "initial_generator_contract_hash FROM analysis_candidates WHERE id=?",
            (int(analysis_candidate_id),),
        ).fetchone()
        if candidate is None:
            raise KeyError(f"Unknown analysis candidate id: {analysis_candidate_id}")
        try:
            initial_contract = json.loads(
                str(candidate["initial_generator_contract_json"])
            )
        except json.JSONDecodeError as exc:
            raise RuntimeError("Analysis generator contract JSON is invalid") from exc
        initial_json, initial_hash = cls._canonical_analysis_json(
            initial_contract,
            "stored initial analysis generator contract",
        )
        if (
            str(candidate["initial_generator_contract_json"]) != initial_json
            or str(candidate["initial_generator_contract_hash"]) != initial_hash
        ):
            raise RuntimeError("Analysis generator contract hash verification failed")
        initial_rejections = cls._analysis_generator_rejected_emotion_contract(
            str(candidate["candidate_json"]),
            initial_contract,
            durable=True,
        )
        validated = [cls._analysis_generator_contract_row(row) for row in rows]
        for row in validated:
            contract = json.loads(str(row["generator_contract_json"]))
            rejections = cls._analysis_generator_rejected_emotion_contract(
                str(candidate["candidate_json"]),
                contract,
                durable=True,
            )
            if rejections != initial_rejections:
                raise RuntimeError(
                    "Analysis candidate generator history changed its critic rejection schema"
                )
        if validated and (
            str(validated[0]["generator_contract_json"]) != initial_json
            or str(validated[0]["generator_contract_hash"]) != initial_hash
        ):
            raise RuntimeError(
                "Analysis candidate generator history does not begin with its initial contract"
            )
        return validated

    @classmethod
    def _validate_analysis_candidate_history_conn(
        cls,
        conn: sqlite3.Connection,
        candidate: sqlite3.Row,
    ) -> tuple[list[sqlite3.Row], list[sqlite3.Row]]:
        """Validate both child ledgers against one already-validated parent row."""
        analysis_candidate_id = int(candidate["id"])
        generator_history = cls._validate_analysis_generator_contract_history_conn(
            conn,
            analysis_candidate_id,
        )
        critic_history = cls._validate_analysis_critic_attempt_history_conn(
            conn,
            analysis_candidate_id,
            int(candidate["critic_attempt_count"]),
            str(candidate["state"]),
        )
        return generator_history, critic_history

    @classmethod
    def _record_analysis_generator_contract_conn(
        cls,
        conn: sqlite3.Connection,
        analysis_candidate_id: int,
        contract_json: str,
        contract_hash: str,
        now: float,
    ) -> None:
        candidate = conn.execute(
            "SELECT candidate_json,initial_generator_contract_json "
            "FROM analysis_candidates WHERE id=?",
            (int(analysis_candidate_id),),
        ).fetchone()
        if candidate is None:
            raise KeyError(f"Unknown analysis candidate id: {analysis_candidate_id}")
        try:
            initial_contract = json.loads(
                str(candidate["initial_generator_contract_json"])
            )
            current_contract = json.loads(contract_json)
        except json.JSONDecodeError as exc:
            raise RuntimeError("Analysis generator contract JSON is invalid") from exc
        if not isinstance(initial_contract, dict) or not isinstance(current_contract, dict):
            raise RuntimeError("Analysis generator contract must be an object")
        initial_rejections = cls._analysis_generator_rejected_emotion_contract(
            str(candidate["candidate_json"]),
            initial_contract,
            durable=True,
        )
        current_rejections = cls._analysis_generator_rejected_emotion_contract(
            str(candidate["candidate_json"]),
            current_contract,
            durable=True,
        )
        if current_rejections != initial_rejections:
            raise RuntimeError(
                "Analysis candidate generator history changed its critic rejection schema"
            )
        rows = cls._validate_analysis_generator_contract_history_conn(
            conn,
            analysis_candidate_id,
            require_nonempty=False,
        )
        existing = next(
            (
                row
                for row in rows
                if str(row["generator_contract_hash"]) == contract_hash
            ),
            None,
        )
        if existing is not None:
            if str(existing["generator_contract_json"]) != contract_json:
                raise RuntimeError("Analysis generator contract hash collision")
            return
        conn.execute(
            """
            INSERT INTO analysis_candidate_generator_contracts(
                analysis_candidate_id,generator_contract_hash,generator_contract_json,
                first_seen_at,last_seen_at,occurrence_count
            ) VALUES(?,?,?,?,?,1)
            """,
            (int(analysis_candidate_id), contract_hash, contract_json, now, now),
        )

    def allocate_or_resume_analysis_candidate(
        self,
        *,
        policy_fingerprint: str,
        model_name: str,
        model_digest: str,
        group_fingerprint: str,
        context_hash: str,
        candidate_hash: str,
        candidate: Any,
        generator_contract: dict[str, Any],
        deterministic_issues: dict[str, Any],
        critic_max_attempts: int,
    ) -> sqlite3.Row:
        identity = self._analysis_candidate_identity(
            policy_fingerprint=policy_fingerprint,
            model_name=model_name,
            model_digest=model_digest,
            group_fingerprint=group_fingerprint,
            context_hash=context_hash,
            candidate_hash=candidate_hash,
        )
        if not isinstance(candidate, dict):
            raise ValueError("Analysis candidate must be a JSON object")
        if not isinstance(generator_contract, dict):
            raise ValueError("Analysis generator contract must be a JSON object")
        if not isinstance(deterministic_issues, dict):
            raise ValueError("Deterministic analysis issues must be a JSON object")
        normalized_budget = int(critic_max_attempts)
        if normalized_budget < 1:
            raise ValueError("Analysis critic attempt budget must be positive")
        candidate_json, envelope_hash = self._canonical_analysis_json(
            candidate,
            "analysis candidate",
        )
        self._analysis_candidate_commit_rows(candidate_json)
        generator_rejections = self._analysis_generator_rejected_emotion_contract(
            candidate_json,
            generator_contract,
            durable=False,
        )
        computed_candidate_hash = analysis_critic_candidate_hash(
            candidate["critic_rows"],
            generator_rejections,
        )
        if identity[-1] != computed_candidate_hash:
            raise ValueError(
                "Analysis candidate hash does not match its critic projection and retry schema"
            )
        generator_json, generator_hash = self._canonical_analysis_json(
            generator_contract,
            "analysis generator contract",
        )
        issue_json, issue_hash = self._canonical_analysis_json(
            deterministic_issues,
            "deterministic analysis issues",
        )
        now = time.time()
        with self.transaction() as conn:
            self._validate_analysis_candidate_sources_conn(
                conn,
                candidate_json,
                issue_json,
                identity[4],
            )
            existing = conn.execute(
                """
                SELECT * FROM analysis_candidates
                WHERE policy_fingerprint=? AND model_name=? AND model_digest=?
                  AND group_fingerprint=? AND context_hash=? AND candidate_hash=?
                """,
                identity,
            ).fetchone()
            if existing is None:
                cursor = conn.execute(
                    """
                    INSERT INTO analysis_candidates(
                        policy_fingerprint,model_name,model_digest,group_fingerprint,
                        context_hash,candidate_hash,candidate_json,envelope_hash,state,
                        initial_generator_contract_json,initial_generator_contract_hash,
                        deterministic_issue_json,deterministic_issue_hash,
                        critic_attempt_count,critic_max_attempts,created_at,updated_at
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,0,?,?,?)
                    """,
                    (
                        *identity,
                        candidate_json,
                        envelope_hash,
                        ANALYSIS_CANDIDATE_ALLOCATED,
                        generator_json,
                        generator_hash,
                        issue_json,
                        issue_hash,
                        normalized_budget,
                        now,
                        now,
                    ),
                )
                analysis_candidate_id = int(cursor.lastrowid)
            else:
                analysis_candidate_id = int(existing["id"])
                existing = self._analysis_candidate_row_conn(
                    conn,
                    analysis_candidate_id,
                )
                self._validate_analysis_candidate_history_conn(conn, existing)
                if (
                    str(existing["candidate_json"]) != candidate_json
                    or str(existing["envelope_hash"]) != envelope_hash
                    or str(existing["deterministic_issue_json"]) != issue_json
                    or str(existing["deterministic_issue_hash"]) != issue_hash
                    or int(existing["critic_max_attempts"]) != normalized_budget
                ):
                    raise RuntimeError(
                        "Analysis candidate replay differs from its durable identity ledger"
                    )
            self._record_analysis_generator_contract_conn(
                conn,
                analysis_candidate_id,
                generator_json,
                generator_hash,
                now,
            )
            candidate_row = self._analysis_candidate_row_conn(
                conn,
                analysis_candidate_id,
            )
            self._validate_analysis_candidate_history_conn(conn, candidate_row)
            return candidate_row

    def get_analysis_candidate(self, analysis_candidate_id: int) -> sqlite3.Row:
        with self.connect() as conn:
            candidate = self._analysis_candidate_row_conn(conn, analysis_candidate_id)
            self._validate_analysis_candidate_history_conn(conn, candidate)
            return candidate

    def has_analysis_candidates(self) -> bool:
        with self.connect() as conn:
            return conn.execute(
                "SELECT EXISTS(SELECT 1 FROM analysis_candidates LIMIT 1)"
            ).fetchone()[0] == 1

    def record_analysis_candidate_generator_contract(
        self,
        analysis_candidate_id: int,
        generator_contract: dict[str, Any],
    ) -> sqlite3.Row:
        if not isinstance(generator_contract, dict):
            raise ValueError("Analysis generator contract must be a JSON object")
        contract_json, contract_hash = self._canonical_analysis_json(
            generator_contract,
            "analysis generator contract",
        )
        now = time.time()
        with self.transaction() as conn:
            candidate = self._analysis_candidate_row_conn(conn, analysis_candidate_id)
            self._validate_analysis_candidate_history_conn(conn, candidate)
            self._record_analysis_generator_contract_conn(
                conn,
                int(candidate["id"]),
                contract_json,
                contract_hash,
                now,
            )
            candidate = self._analysis_candidate_row_conn(conn, analysis_candidate_id)
            self._validate_analysis_candidate_history_conn(conn, candidate)
            return candidate

    def get_analysis_candidate_exact(
        self,
        *,
        policy_fingerprint: str,
        model_name: str,
        model_digest: str,
        group_fingerprint: str,
        context_hash: str,
        candidate_hash: str,
    ) -> sqlite3.Row | None:
        identity = self._analysis_candidate_identity(
            policy_fingerprint=policy_fingerprint,
            model_name=model_name,
            model_digest=model_digest,
            group_fingerprint=group_fingerprint,
            context_hash=context_hash,
            candidate_hash=candidate_hash,
        )
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT * FROM analysis_candidates
                WHERE policy_fingerprint=? AND model_name=? AND model_digest=?
                  AND group_fingerprint=? AND context_hash=? AND candidate_hash=?
                """,
                identity,
            ).fetchone()
            if row is None:
                return None
            candidate = self._analysis_candidate_row_conn(conn, int(row["id"]))
            self._validate_analysis_candidate_history_conn(conn, candidate)
            return candidate

    def find_resumable_analysis_candidate(
        self,
        *,
        policy_fingerprint: str,
        model_name: str,
        model_digest: str,
        group_fingerprint: str,
        context_hash: str,
    ) -> sqlite3.Row | None:
        scope = tuple(
            str(value).strip()
            for value in (
                policy_fingerprint,
                model_name,
                model_digest,
                group_fingerprint,
                context_hash,
            )
        )
        if any(not value for value in scope):
            raise ValueError("Analysis candidate resume scope fields must be non-empty")
        actionable_states = (
            ANALYSIS_CANDIDATE_ALLOCATED,
            ANALYSIS_CANDIDATE_CRITIC_IN_FLIGHT,
            ANALYSIS_CANDIDATE_CRITIC_INVALID,
            ANALYSIS_CANDIDATE_CRITIC_ACCEPTED,
        )
        marks = ",".join("?" for _ in actionable_states)
        with self.connect() as conn:
            rows = list(
                conn.execute(
                    f"""
                    SELECT * FROM analysis_candidates
                    WHERE policy_fingerprint=? AND model_name=? AND model_digest=?
                      AND group_fingerprint=? AND context_hash=?
                      AND state IN ({marks})
                    ORDER BY id
                    """,
                    (*scope, *actionable_states),
                )
            )
            if len(rows) > 1:
                raise RuntimeError(
                    "Analysis resume scope contains multiple actionable candidates"
                )
            if not rows:
                return None
            candidate = self._analysis_candidate_row_conn(conn, int(rows[0]["id"]))
            self._validate_analysis_candidate_history_conn(conn, candidate)
            return candidate

    def analysis_candidate_acceptance_envelope(
        self,
        analysis_candidate_id: int,
    ) -> dict[str, Any]:
        with self.connect() as conn:
            candidate = self._analysis_candidate_row_conn(conn, analysis_candidate_id)
            self._validate_analysis_candidate_history_conn(conn, candidate)
            if str(candidate["state"]) not in {
                ANALYSIS_CANDIDATE_CRITIC_ACCEPTED,
                ANALYSIS_CANDIDATE_ACCEPTED,
            }:
                raise RuntimeError("Analysis candidate has not been accepted by the critic")
            attempts = list(
                conn.execute(
                    "SELECT * FROM analysis_critic_attempts "
                    "WHERE analysis_candidate_id=? ORDER BY attempt_number",
                    (int(analysis_candidate_id),),
                )
            )
            completed = [
                attempt
                for attempt in attempts
                if str(attempt["state"]) == ANALYSIS_CRITIC_ATTEMPT_COMPLETED
            ]
            if not completed:
                raise RuntimeError("Accepted analysis candidate has no completed critic evidence")
            final_attempt = self._analysis_critic_attempt_row_conn(
                conn,
                analysis_candidate_id,
                int(completed[-1]["attempt_number"]),
            )
        return {
            "candidate_id": int(candidate["id"]),
            "candidate_hash": str(candidate["candidate_hash"]),
            "policy_fingerprint": str(candidate["policy_fingerprint"]),
            "model_name": str(candidate["model_name"]),
            "model_digest": str(candidate["model_digest"]),
            "group_fingerprint": str(candidate["group_fingerprint"]),
            "context_hash": str(candidate["context_hash"]),
            "candidate": json.loads(str(candidate["candidate_json"])),
            "envelope_hash": str(candidate["envelope_hash"]),
            "commit_envelope": json.loads(str(candidate["commit_envelope_json"])),
            "commit_envelope_hash": str(candidate["commit_envelope_hash"]),
            "critic_outcome": json.loads(str(final_attempt["outcome_json"])),
            "critic_evidence": json.loads(str(final_attempt["evidence_json"])),
            "critic_attempt_number": int(final_attempt["attempt_number"]),
            "critic_completion_hash": str(final_attempt["completion_hash"]),
        }

    def list_analysis_candidate_generator_contracts(
        self,
        analysis_candidate_id: int,
    ) -> list[sqlite3.Row]:
        with self.connect() as conn:
            candidate = self._analysis_candidate_row_conn(
                conn,
                analysis_candidate_id,
            )
            generator_history, _critic_history = (
                self._validate_analysis_candidate_history_conn(conn, candidate)
            )
            return generator_history

    def list_analysis_critic_attempts(
        self,
        analysis_candidate_id: int,
    ) -> list[sqlite3.Row]:
        with self.connect() as conn:
            candidate = self._analysis_candidate_row_conn(
                conn,
                analysis_candidate_id,
            )
            _generator_history, critic_history = (
                self._validate_analysis_candidate_history_conn(conn, candidate)
            )
            return critic_history

    def reserve_analysis_critic_attempt(
        self,
        analysis_candidate_id: int,
        *,
        expected_state: str,
        max_attempts: int,
        intent: dict[str, Any],
        contract: dict[str, Any],
    ) -> sqlite3.Row:
        normalized_expected_state = str(expected_state).strip()
        if normalized_expected_state not in {
            ANALYSIS_CANDIDATE_ALLOCATED,
            ANALYSIS_CANDIDATE_CRITIC_INVALID,
            ANALYSIS_CANDIDATE_CRITIC_IN_FLIGHT,
        }:
            raise ValueError("Analysis critic reservation requires an actionable candidate state")
        if not isinstance(intent, dict) or not isinstance(contract, dict):
            raise ValueError("Analysis critic intent and contract must be JSON objects")
        normalized_budget = int(max_attempts)
        if normalized_budget < 1:
            raise ValueError("Analysis critic attempt budget must be positive")
        confidence_floor, _confidence_cap = self._analysis_critic_confidence_bounds(
            contract,
            durable=False,
        )
        intent_json, intent_hash = self._canonical_analysis_json(
            intent,
            "analysis critic intent",
        )
        contract_json, contract_hash = self._canonical_analysis_json(
            contract,
            "analysis critic contract",
        )
        now = time.time()
        with self.transaction() as conn:
            candidate = self._analysis_candidate_row_conn(conn, analysis_candidate_id)
            self._validate_analysis_candidate_history_conn(conn, candidate)
            if str(intent.get("candidate_hash", "")) != str(candidate["candidate_hash"]):
                raise ValueError(
                    "Analysis critic intent must bind its parent candidate hash"
                )
            confidence_floor, _confidence_cap = (
                self._analysis_critic_confidence_bounds(
                    contract,
                    durable=False,
                    candidate_json=str(candidate["candidate_json"]),
                )
            )
            self._validate_analysis_critic_generator_rejections(
                candidate_json=str(candidate["candidate_json"]),
                generator_contract_json=str(
                    candidate["initial_generator_contract_json"]
                ),
                critic_contract=contract,
                durable=False,
            )
            if str(contract.get("candidate_hash", "")) != str(
                candidate["candidate_hash"]
            ):
                raise ValueError(
                    "Analysis critic contract must bind its parent candidate hash"
                )
            candidate_payload = json.loads(str(candidate["candidate_json"]))
            below_floor_ids = [
                str(segment["stable_id"])
                for segment in candidate_payload["segments"]
                if float(segment["data"]["confidence"]) < confidence_floor
            ]
            if below_floor_ids:
                raise RuntimeError(
                    "Analysis candidate confidence is below the reserved critic floor: "
                    + ",".join(below_floor_ids)
                )
            state = str(candidate["state"])
            if state != normalized_expected_state:
                raise RuntimeError(
                    "Analysis critic reservation state CAS failed: "
                    f"expected {normalized_expected_state}, found {state}"
                )
            stored_budget = int(candidate["critic_max_attempts"])
            attempt_count = int(candidate["critic_attempt_count"])
            if stored_budget != normalized_budget:
                raise RuntimeError("Analysis critic attempt budget differs from its durable ledger")
            if attempt_count >= stored_budget:
                raise RuntimeError("Analysis critic attempt budget is exhausted")
            if state == ANALYSIS_CANDIDATE_CRITIC_IN_FLIGHT:
                self._analysis_critic_attempt_row_conn(
                    conn,
                    analysis_candidate_id,
                    attempt_count,
                )
                abandoned = conn.execute(
                    """
                    UPDATE analysis_critic_attempts
                    SET state=?,completed_at=?
                    WHERE analysis_candidate_id=? AND attempt_number=? AND state=?
                    """,
                    (
                        ANALYSIS_CRITIC_ATTEMPT_ABANDONED,
                        now,
                        int(analysis_candidate_id),
                        attempt_count,
                        ANALYSIS_CRITIC_ATTEMPT_RESERVED,
                    ),
                )
                if abandoned.rowcount != 1:
                    raise RuntimeError(
                        "Analysis critic in-flight candidate has no matching reserved intent"
                    )
            attempt_number = attempt_count + 1
            updated = conn.execute(
                """
                UPDATE analysis_candidates
                SET state=?,critic_attempt_count=?,updated_at=?
                WHERE id=? AND state=? AND critic_attempt_count=? AND critic_max_attempts=?
                """,
                (
                    ANALYSIS_CANDIDATE_CRITIC_IN_FLIGHT,
                    attempt_number,
                    now,
                    int(analysis_candidate_id),
                    normalized_expected_state,
                    attempt_count,
                    normalized_budget,
                ),
            )
            if updated.rowcount != 1:
                raise RuntimeError("Analysis critic attempt reservation CAS failed")
            conn.execute(
                """
                INSERT INTO analysis_critic_attempts(
                    analysis_candidate_id,attempt_number,state,intent_json,intent_hash,
                    contract_json,contract_hash,reserved_at
                ) VALUES(?,?,?,?,?,?,?,?)
                """,
                (
                    int(analysis_candidate_id),
                    attempt_number,
                    ANALYSIS_CRITIC_ATTEMPT_RESERVED,
                    intent_json,
                    intent_hash,
                    contract_json,
                    contract_hash,
                    now,
                ),
            )
            candidate = self._analysis_candidate_row_conn(
                conn,
                analysis_candidate_id,
            )
            self._validate_analysis_candidate_history_conn(conn, candidate)
            return self._analysis_critic_attempt_row_conn(
                conn,
                analysis_candidate_id,
                attempt_number,
            )

    def complete_analysis_critic_attempt(
        self,
        analysis_candidate_id: int,
        attempt_number: int,
        *,
        expected_intent_hash: str,
        expected_contract_hash: str,
        result_state: str,
        outcome: dict[str, Any],
        evidence: dict[str, Any],
        commit_envelope: dict[str, Any] | None = None,
    ) -> sqlite3.Row:
        normalized_result_state = str(result_state).strip()
        if normalized_result_state not in {
            ANALYSIS_CANDIDATE_CRITIC_INVALID,
            ANALYSIS_CANDIDATE_CRITIC_ACCEPTED,
            ANALYSIS_CANDIDATE_CRITIC_REJECTED,
        }:
            raise ValueError("Unsupported analysis critic completion state")
        if not isinstance(outcome, dict) or not isinstance(evidence, dict):
            raise ValueError("Analysis critic outcome and evidence must be JSON objects")
        normalized_intent_hash = str(expected_intent_hash).strip()
        normalized_contract_hash = str(expected_contract_hash).strip()
        if not normalized_intent_hash or not normalized_contract_hash:
            raise ValueError("Analysis critic completion requires intent and contract hashes")
        outcome_json, outcome_hash = self._canonical_analysis_json(
            {
                "candidate_state": normalized_result_state,
                "payload": outcome,
            },
            "analysis critic outcome",
        )
        evidence_json, evidence_hash = self._canonical_analysis_json(
            evidence,
            "analysis critic evidence",
        )
        now = time.time()
        with self.transaction() as conn:
            attempt = self._analysis_critic_attempt_row_conn(
                conn,
                analysis_candidate_id,
                attempt_number,
            )
            if (
                str(attempt["intent_hash"]) != normalized_intent_hash
                or str(attempt["contract_hash"]) != normalized_contract_hash
            ):
                raise RuntimeError("Analysis critic completion provenance hash CAS failed")
            attempt_state = str(attempt["state"])
            candidate = self._analysis_candidate_row_conn(conn, analysis_candidate_id)
            self._validate_analysis_candidate_history_conn(conn, candidate)
            if normalized_result_state == ANALYSIS_CANDIDATE_CRITIC_ACCEPTED:
                if (
                    outcome.get("accepted") is False
                    or outcome.get("retryable_invalid") is True
                    or bool(outcome.get("issues"))
                ):
                    raise RuntimeError(
                        "Accepted analysis critic outcome contradicts its requested state"
                    )
                if commit_envelope is None:
                    raise ValueError(
                        "Accepted analysis critic completion requires a commit envelope"
                    )
                commit_envelope_json, commit_envelope_hash = (
                    self._validated_analysis_commit_envelope(
                        str(candidate["candidate_json"]),
                        commit_envelope,
                    )
                )
                self._validate_analysis_acceptance_evidence(
                    conn,
                    str(candidate["candidate_json"]),
                    commit_envelope_json,
                    evidence,
                    str(attempt["contract_json"]),
                    str(candidate["deterministic_issue_json"]),
                )
            else:
                if normalized_result_state == ANALYSIS_CANDIDATE_CRITIC_INVALID and (
                    outcome.get("accepted") is True
                    or outcome.get("retryable_invalid") is False
                ):
                    raise RuntimeError(
                        "Invalid analysis critic outcome contradicts its requested state"
                    )
                if commit_envelope is not None:
                    raise ValueError(
                        "Only an accepted analysis critic completion may store a commit envelope"
                    )
                commit_envelope_json = None
                commit_envelope_hash = None
                if normalized_result_state == ANALYSIS_CANDIDATE_CRITIC_REJECTED:
                    self._validate_analysis_rejection_evidence(
                        conn,
                        str(candidate["candidate_json"]),
                        evidence,
                        outcome,
                        str(attempt["contract_json"]),
                        str(candidate["deterministic_issue_json"]),
                    )
            completion_json, completion_hash = self._canonical_analysis_json(
                {
                    "commit_envelope_hash": commit_envelope_hash,
                    "contract_hash": normalized_contract_hash,
                    "evidence_hash": evidence_hash,
                    "intent_hash": normalized_intent_hash,
                    "outcome_hash": outcome_hash,
                },
                "analysis critic completion",
            )
            del completion_json
            if attempt_state == ANALYSIS_CRITIC_ATTEMPT_COMPLETED:
                if (
                    str(attempt["completion_hash"] or "") == completion_hash
                    and str(attempt["outcome_json"] or "") == outcome_json
                    and str(attempt["evidence_json"] or "") == evidence_json
                    and (
                        normalized_result_state
                        != ANALYSIS_CANDIDATE_CRITIC_ACCEPTED
                        or (
                            str(candidate["commit_envelope_hash"] or "")
                            == str(commit_envelope_hash or "")
                            and str(candidate["commit_envelope_json"] or "")
                            == str(commit_envelope_json or "")
                        )
                    )
                ):
                    return attempt
                raise RuntimeError("Analysis critic completion replay payload differs")
            if attempt_state != ANALYSIS_CRITIC_ATTEMPT_RESERVED:
                raise RuntimeError("Abandoned analysis critic intent cannot be completed")
            if (
                str(candidate["state"]) != ANALYSIS_CANDIDATE_CRITIC_IN_FLIGHT
                or int(candidate["critic_attempt_count"]) != int(attempt_number)
            ):
                raise RuntimeError("Analysis critic completion candidate CAS failed")
            completed = conn.execute(
                """
                UPDATE analysis_critic_attempts
                SET state=?,outcome_json=?,outcome_hash=?,evidence_json=?,evidence_hash=?,
                    completion_hash=?,completed_at=?
                WHERE analysis_candidate_id=? AND attempt_number=? AND state=?
                  AND intent_hash=? AND contract_hash=?
                """,
                (
                    ANALYSIS_CRITIC_ATTEMPT_COMPLETED,
                    outcome_json,
                    outcome_hash,
                    evidence_json,
                    evidence_hash,
                    completion_hash,
                    now,
                    int(analysis_candidate_id),
                    int(attempt_number),
                    ANALYSIS_CRITIC_ATTEMPT_RESERVED,
                    normalized_intent_hash,
                    normalized_contract_hash,
                ),
            )
            if completed.rowcount != 1:
                raise RuntimeError("Analysis critic completion attempt CAS failed")
            updated = conn.execute(
                """
                UPDATE analysis_candidates
                SET state=?,commit_envelope_json=?,commit_envelope_hash=?,updated_at=?
                WHERE id=? AND state=? AND critic_attempt_count=?
                """,
                (
                    normalized_result_state,
                    commit_envelope_json,
                    commit_envelope_hash,
                    now,
                    int(analysis_candidate_id),
                    ANALYSIS_CANDIDATE_CRITIC_IN_FLIGHT,
                    int(attempt_number),
                ),
            )
            if updated.rowcount != 1:
                raise RuntimeError("Analysis critic completion state CAS failed")
            candidate = self._analysis_candidate_row_conn(
                conn,
                analysis_candidate_id,
            )
            self._validate_analysis_candidate_history_conn(conn, candidate)
            return self._analysis_critic_attempt_row_conn(
                conn,
                analysis_candidate_id,
                attempt_number,
            )

    def _mark_analysis_candidate_final_state(
        self,
        analysis_candidate_id: int,
        *,
        expected_state: str,
        final_state: str,
        reason: str,
    ) -> sqlite3.Row:
        normalized_expected_state = str(expected_state).strip()
        if normalized_expected_state not in ANALYSIS_CANDIDATE_STATES:
            raise ValueError("Unsupported expected analysis candidate state")
        if final_state not in {
            ANALYSIS_CANDIDATE_TERMINAL,
            ANALYSIS_CANDIDATE_SUPERSEDED,
        }:
            raise ValueError("Unsupported final analysis candidate state")
        normalized_reason = str(reason).strip()
        if not normalized_reason:
            raise ValueError("Final analysis candidate state requires a reason")
        now = time.time()
        with self.transaction() as conn:
            candidate = self._analysis_candidate_row_conn(conn, analysis_candidate_id)
            state = str(candidate["state"])
            attempt_count = int(candidate["critic_attempt_count"])
            self._validate_analysis_candidate_history_conn(conn, candidate)
            if state in {
                ANALYSIS_CANDIDATE_TERMINAL,
                ANALYSIS_CANDIDATE_SUPERSEDED,
            }:
                if state == final_state:
                    if str(candidate["terminal_reason"] or "") == normalized_reason:
                        return candidate
                    raise RuntimeError(
                        "Analysis candidate final-state replay reason differs"
                    )
                raise RuntimeError("Analysis candidate final states are absorbing")
            if state != normalized_expected_state:
                raise RuntimeError(
                    "Analysis candidate final-state CAS failed: "
                    f"expected {normalized_expected_state}, found {state}"
                )
            if state == ANALYSIS_CANDIDATE_CRITIC_IN_FLIGHT:
                abandoned = conn.execute(
                    """
                    UPDATE analysis_critic_attempts SET state=?,completed_at=?
                    WHERE analysis_candidate_id=? AND attempt_number=? AND state=?
                    """,
                    (
                        ANALYSIS_CRITIC_ATTEMPT_ABANDONED,
                        now,
                        int(analysis_candidate_id),
                        int(candidate["critic_attempt_count"]),
                        ANALYSIS_CRITIC_ATTEMPT_RESERVED,
                    ),
                )
                if abandoned.rowcount != 1:
                    raise RuntimeError(
                        "Analysis candidate has no reserved critic intent to terminate"
                    )
            if final_state in {
                ANALYSIS_CANDIDATE_TERMINAL,
                ANALYSIS_CANDIDATE_SUPERSEDED,
            }:
                self._validate_analysis_critic_attempt_history_conn(
                    conn,
                    analysis_candidate_id,
                    attempt_count,
                    final_state,
                )
            updated = conn.execute(
                """
                UPDATE analysis_candidates
                SET state=?,terminal_reason=?,updated_at=?
                WHERE id=? AND state=?
                """,
                (
                    final_state,
                    normalized_reason,
                    now,
                    int(analysis_candidate_id),
                    normalized_expected_state,
                ),
            )
            if updated.rowcount != 1:
                raise RuntimeError("Analysis candidate final-state update CAS failed")
            candidate = self._analysis_candidate_row_conn(
                conn,
                analysis_candidate_id,
            )
            self._validate_analysis_candidate_history_conn(conn, candidate)
            return candidate

    def mark_analysis_candidate_terminal(
        self,
        analysis_candidate_id: int,
        *,
        expected_state: str,
        reason: str,
    ) -> sqlite3.Row:
        return self._mark_analysis_candidate_final_state(
            analysis_candidate_id,
            expected_state=expected_state,
            final_state=ANALYSIS_CANDIDATE_TERMINAL,
            reason=reason,
        )

    def mark_analysis_candidate_superseded(
        self,
        analysis_candidate_id: int,
        *,
        expected_state: str,
        reason: str,
    ) -> sqlite3.Row:
        return self._mark_analysis_candidate_final_state(
            analysis_candidate_id,
            expected_state=expected_state,
            final_state=ANALYSIS_CANDIDATE_SUPERSEDED,
            reason=reason,
        )

    def finalize_exhausted_analysis_critic_candidate(
        self,
        analysis_candidate_id: int,
        *,
        reason: str,
    ) -> sqlite3.Row:
        normalized_reason = str(reason).strip()
        if not normalized_reason:
            raise ValueError("Exhausted analysis critic candidate requires a reason")
        now = time.time()
        with self.transaction() as conn:
            candidate = self._analysis_candidate_row_conn(conn, analysis_candidate_id)
            state = str(candidate["state"])
            attempt_count = int(candidate["critic_attempt_count"])
            self._validate_analysis_candidate_history_conn(conn, candidate)
            if state == ANALYSIS_CANDIDATE_TERMINAL:
                if str(candidate["terminal_reason"] or "") == normalized_reason:
                    return candidate
                raise RuntimeError("Analysis critic exhaustion replay reason differs")
            max_attempts = int(candidate["critic_max_attempts"])
            if attempt_count < max_attempts:
                raise RuntimeError("Analysis critic attempt budget is not exhausted")
            if state == ANALYSIS_CANDIDATE_CRITIC_IN_FLIGHT:
                abandoned = conn.execute(
                    """
                    UPDATE analysis_critic_attempts SET state=?,completed_at=?
                    WHERE analysis_candidate_id=? AND attempt_number=? AND state=?
                    """,
                    (
                        ANALYSIS_CRITIC_ATTEMPT_ABANDONED,
                        now,
                        int(analysis_candidate_id),
                        attempt_count,
                        ANALYSIS_CRITIC_ATTEMPT_RESERVED,
                    ),
                )
                if abandoned.rowcount != 1:
                    raise RuntimeError(
                        "Exhausted analysis critic candidate has no reserved final intent"
                    )
            elif state not in {
                ANALYSIS_CANDIDATE_CRITIC_INVALID,
                ANALYSIS_CANDIDATE_CRITIC_REJECTED,
            }:
                raise RuntimeError(
                    "Analysis critic candidate is not in an exhaustible state"
                )
            updated = conn.execute(
                """
                UPDATE analysis_candidates SET state=?,terminal_reason=?,updated_at=?
                WHERE id=? AND state=? AND critic_attempt_count=? AND critic_max_attempts=?
                """,
                (
                    ANALYSIS_CANDIDATE_TERMINAL,
                    normalized_reason,
                    now,
                    int(analysis_candidate_id),
                    state,
                    attempt_count,
                    max_attempts,
                ),
            )
            if updated.rowcount != 1:
                raise RuntimeError("Analysis critic exhaustion terminal CAS failed")
            candidate = self._analysis_candidate_row_conn(
                conn,
                analysis_candidate_id,
            )
            self._validate_analysis_candidate_history_conn(conn, candidate)
            return candidate

    def update_analysis(
        self,
        segment_id: int,
        data: dict[str, Any],
        low_confidence_threshold: float = 0.58,
    ) -> None:
        if not isinstance(data, dict):
            raise ValueError("Analysis update data must be an object")
        with self.transaction() as conn:
            current = conn.execute(
                "SELECT * FROM segments WHERE id=?",
                (int(segment_id),),
            ).fetchone()
            if current is None:
                raise KeyError(f"Unknown segment id: {segment_id}")
            merged = self._merged_analysis_update_data(current, data)
            values = self._analysis_update_values(
                merged,
                low_confidence_threshold,
                time.time(),
            )
            updated = conn.execute(
                """
                UPDATE segments SET
                    kind=?,speaker=?,gender=?,age=?,emotion=?,intensity=?,pace=?,volume=?,
                    confidence=?,analysis_notes=?,warning_code=?,status=?,updated_at=?
                WHERE id=?
                """,
                (*values, int(segment_id)),
            )
            if updated.rowcount != 1:
                raise RuntimeError("Analysis update segment CAS failed")

    @staticmethod
    def _merged_analysis_update_data(
        current: sqlite3.Row,
        updates: dict[str, Any],
    ) -> dict[str, Any]:
        allowed_fields = ANALYSIS_ACCEPTED_DELIVERY_FIELDS - {"personality_hint", "notes"}
        unknown_fields = set(updates) - ANALYSIS_ACCEPTED_DELIVERY_FIELDS
        if unknown_fields:
            raise ValueError("Analysis update contains unsupported fields")
        if updates.get("personality_hint", "") != "":
            raise ValueError("Analysis personality_hint must be empty")
        current_delivery = {
            "kind": str(current["kind"] or current["kind_hint"] or "narration"),
            "speaker": str(current["speaker"] or "NARRATOR"),
            "gender": str(current["gender"] or "unknown"),
            "age": str(current["age"] or "unknown"),
            "emotion": str(current["emotion"] or "neutral"),
            "intensity": int(current["intensity"] if current["intensity"] is not None else 1),
            "pace": str(current["pace"] or "normal"),
            "volume": str(current["volume"] or "normal"),
            "confidence": float(
                current["confidence"] if current["confidence"] is not None else 0.5
            ),
        }
        current_note = str(current["analysis_notes"] or "")
        current_note_data = {
            **current_delivery,
            "personality_hint": "",
            "notes": current_note,
        }
        if current_note:
            analysis_note_markers(current_note_data)
        merged = {
            **current_delivery,
            **{
                field: updates[field]
                for field in allowed_fields
                if field in updates
            },
            "personality_hint": "",
            "notes": "",
        }
        requested_note = updates.get("notes")
        if requested_note is not None:
            if not isinstance(requested_note, str):
                raise ValueError("Analysis notes must be a canonical delivery note")
            requested_note_data = {**merged, "notes": requested_note}
            requested_markers = analysis_note_markers(requested_note_data)
            if requested_markers:
                raise ValueError("Analysis update notes must not persist host markers")
        merged["notes"] = canonical_analysis_note(merged)
        return merged

    @staticmethod
    def _analysis_update_values(
        data: dict[str, Any],
        low_confidence_threshold: float,
        now: float,
    ) -> tuple[Any, ...]:
        confidence = float(data.get("confidence", 0.5))
        warning = "LOW_ANALYSIS_CONFIDENCE" if confidence < low_confidence_threshold else None
        status = SegmentStatus.WARNING.value if warning else SegmentStatus.ANALYZED.value
        analysis_note_markers(data)
        analysis_notes = data["notes"]
        return (
            data.get("kind", "narration"),
            data.get("speaker", "NARRATOR"),
            data.get("gender", "unknown"),
            data.get("age", "unknown"),
            data.get("emotion", "neutral"),
            int(data.get("intensity", 1)),
            data.get("pace", "normal"),
            data.get("volume", "normal"),
            confidence,
            analysis_notes,
            warning,
            status,
            now,
        )

    def update_analysis_batch_with_event(
        self,
        rows: Sequence[dict[str, Any]],
        *,
        low_confidence_threshold: float,
        event_level: str,
        event_code: str,
        event_message: str,
        event_details: dict[str, Any],
        analysis_model_name: str,
        analysis_model_digest: str,
        pronunciations: Sequence[dict[str, Any]] = (),
        analysis_candidate_id: int | None = None,
        expected_analysis_candidate_state: str = ANALYSIS_CANDIDATE_CRITIC_ACCEPTED,
        analysis_policy_fingerprint: str | None = None,
        analysis_group_fingerprint: str | None = None,
        analysis_context_hash: str | None = None,
    ) -> None:
        if not rows:
            raise ValueError("Analysis batch cannot be empty")
        if (
            analysis_candidate_id is not None
            and expected_analysis_candidate_state != ANALYSIS_CANDIDATE_CRITIC_ACCEPTED
        ):
            raise ValueError(
                "Director batch commit can only accept a critic_accepted analysis candidate"
            )
        expected_candidate_scope = tuple(
            str(value or "").strip()
            for value in (
                analysis_policy_fingerprint,
                analysis_group_fingerprint,
                analysis_context_hash,
            )
        )
        if analysis_candidate_id is not None and any(
            not value for value in expected_candidate_scope
        ):
            raise ValueError(
                "Director batch candidate commit requires policy/group/context fingerprints"
            )
        durable_event_details = dict(event_details)
        now = time.time()
        with self.transaction() as conn:
            model_lock = conn.execute(
                "SELECT analysis_model_name,analysis_model_digest FROM book WHERE id=1"
            ).fetchone()
            if (
                model_lock is None
                or str(model_lock["analysis_model_name"] or "") != str(analysis_model_name)
                or str(model_lock["analysis_model_digest"] or "") != str(analysis_model_digest)
            ):
                raise RuntimeError(
                    "Analysis model lock changed before director batch commit"
                )
            analysis_candidate: sqlite3.Row | None = None
            durable_commit_rows: dict[str, dict[str, Any]] | None = None
            if analysis_candidate_id is not None:
                analysis_candidate = self._analysis_candidate_row_conn(
                    conn,
                    analysis_candidate_id,
                )
                self._validate_analysis_candidate_history_conn(
                    conn,
                    analysis_candidate,
                )
                if (
                    str(analysis_candidate["state"])
                    != ANALYSIS_CANDIDATE_CRITIC_ACCEPTED
                    or str(analysis_candidate["model_name"]) != str(analysis_model_name)
                    or str(analysis_candidate["model_digest"])
                    != str(analysis_model_digest)
                    or str(analysis_candidate["policy_fingerprint"])
                    != expected_candidate_scope[0]
                    or str(analysis_candidate["group_fingerprint"])
                    != expected_candidate_scope[1]
                    or str(analysis_candidate["context_hash"])
                    != expected_candidate_scope[2]
                    or not str(analysis_candidate["commit_envelope_hash"] or "")
                    or not str(analysis_candidate["commit_envelope_json"] or "")
                ):
                    raise RuntimeError(
                        "Analysis candidate identity or critic_accepted state changed before batch commit"
                    )
                critic_attempt = self._analysis_critic_attempt_row_conn(
                    conn,
                    int(analysis_candidate["id"]),
                    int(analysis_candidate["critic_attempt_count"]),
                )
                critic_outcome = json.loads(str(critic_attempt["outcome_json"]))
                if (
                    str(critic_attempt["state"])
                    != ANALYSIS_CRITIC_ATTEMPT_COMPLETED
                    or str(critic_outcome.get("candidate_state", ""))
                    != ANALYSIS_CANDIDATE_CRITIC_ACCEPTED
                ):
                    raise RuntimeError(
                        "Analysis candidate lacks matching completed critic acceptance"
                    )
                durable_event_details.update(
                    {
                        "analysis_candidate_id": int(analysis_candidate["id"]),
                        "candidate_hash": str(analysis_candidate["candidate_hash"]),
                        "commit_envelope_hash": str(
                            analysis_candidate["commit_envelope_hash"]
                        ),
                        "critic_attempt_number": int(critic_attempt["attempt_number"]),
                        "critic_completion_hash": str(critic_attempt["completion_hash"]),
                        "critic_contract_hash": str(critic_attempt["contract_hash"]),
                        "critic_evidence_hash": str(critic_attempt["evidence_hash"]),
                        "critic_intent_hash": str(critic_attempt["intent_hash"]),
                        "policy_fingerprint": str(
                            analysis_candidate["policy_fingerprint"]
                        ),
                        "group_fingerprint": str(
                            analysis_candidate["group_fingerprint"]
                        ),
                        "context_hash": str(analysis_candidate["context_hash"]),
                    }
                )
                durable_commit_rows = self._analysis_candidate_commit_rows(
                    str(analysis_candidate["commit_envelope_json"]),
                )
                durable_envelope = json.loads(
                    str(analysis_candidate["commit_envelope_json"])
                )
                durable_pronunciation_json, _durable_pronunciation_hash = (
                    self._canonical_analysis_json(
                        durable_envelope["pronunciations"],
                        "durable analysis candidate pronunciations",
                    )
                )
                pronunciation_json, _pronunciation_hash = self._canonical_analysis_json(
                    list(pronunciations),
                    "analysis batch pronunciations",
                )
                if pronunciation_json != durable_pronunciation_json:
                    raise RuntimeError(
                        "Analysis batch pronunciations differ from the durable candidate"
                    )
                if len(durable_commit_rows) != len(rows):
                    raise RuntimeError(
                        "Analysis batch differs from the durable candidate segment set"
                    )
            for row in rows:
                if durable_commit_rows is not None:
                    stable_id = str(row["stable_id"])
                    durable_row = durable_commit_rows.get(stable_id)
                    row_data_json, _row_data_hash = self._canonical_analysis_json(
                        dict(row["data"]),
                        "analysis batch segment data",
                    )
                    if (
                        durable_row is None
                        or int(durable_row["segment_id"]) != int(row["segment_id"])
                        or str(durable_row["text_sha256"]) != str(row["text_sha256"])
                        or str(durable_row["data_json"]) != row_data_json
                    ):
                        raise RuntimeError(
                            "Analysis batch row/data differs from the durable candidate: "
                            f"{stable_id}"
                        )
                expected_status = str(row.get("expected_status", SegmentStatus.PENDING.value))
                cursor = conn.execute(
                    """
                    UPDATE segments SET
                        kind=?,speaker=?,gender=?,age=?,emotion=?,intensity=?,pace=?,volume=?,
                        confidence=?,analysis_notes=?,warning_code=?,status=?,updated_at=?
                    WHERE id=? AND stable_id=? AND text_sha256=? AND status=?
                    """,
                    (
                        *self._analysis_update_values(
                            dict(row["data"]),
                            low_confidence_threshold,
                            now,
                        ),
                        int(row["segment_id"]),
                        str(row["stable_id"]),
                        str(row["text_sha256"]),
                        expected_status,
                    ),
                )
                if cursor.rowcount != 1:
                    raise RuntimeError(
                        "Analysis batch CAS failed for "
                        f"{row['stable_id']}: status or source hash changed"
                    )
            for pronunciation in pronunciations:
                self._upsert_pronunciation_conn(conn, pronunciation, now)
            if analysis_candidate is not None:
                accepted = conn.execute(
                    """
                    UPDATE analysis_candidates
                    SET state=?,accepted_at=?,updated_at=?
                    WHERE id=? AND state=? AND model_name=? AND model_digest=?
                      AND candidate_hash=?
                    """,
                    (
                        ANALYSIS_CANDIDATE_ACCEPTED,
                        now,
                        now,
                        int(analysis_candidate["id"]),
                        ANALYSIS_CANDIDATE_CRITIC_ACCEPTED,
                        str(analysis_model_name),
                        str(analysis_model_digest),
                        str(analysis_candidate["candidate_hash"]),
                    ),
                )
                if accepted.rowcount != 1:
                    raise RuntimeError("Analysis candidate acceptance CAS failed")
                accepted_candidate = self._analysis_candidate_row_conn(
                    conn,
                    int(analysis_candidate["id"]),
                )
                self._validate_analysis_candidate_history_conn(
                    conn,
                    accepted_candidate,
                )
            conn.execute(
                """
                INSERT INTO runtime_events(timestamp,level,code,message,details_json)
                VALUES(?,?,?,?,?)
                """,
                (
                    now,
                    event_level,
                    event_code,
                    event_message,
                    json.dumps(durable_event_details, ensure_ascii=False),
                ),
            )

    def mark_generating(
        self,
        segment_id: int,
        seed: int,
        *,
        delivery_mode: str | None = None,
        repair_round: int | None = None,
        policy_hash: str | None = None,
    ) -> None:
        normalized_delivery = (
            str(delivery_mode).strip().casefold()
            if delivery_mode is not None
            else None
        )
        if (
            normalized_delivery is not None
            and normalized_delivery not in GENERATION_DELIVERY_MODES
        ):
            raise ValueError(f"Unsupported generation delivery mode: {delivery_mode}")
        normalized_round = int(repair_round) if repair_round is not None else None
        if normalized_round is not None and normalized_round < 0:
            raise ValueError("generation repair round must be non-negative")
        if normalized_delivery == GENERATION_DELIVERY_PRIMARY and normalized_round is not None:
            raise ValueError("primary generation cannot carry an ASR repair round")
        if normalized_delivery == GENERATION_DELIVERY_CLARITY and normalized_round is None:
            raise ValueError("clarity generation requires an ASR repair round")
        normalized_policy_hash = str(policy_hash or "").strip() or None
        if normalized_delivery is not None and normalized_policy_hash is None:
            raise ValueError("generation delivery checkpoints require a quality policy hash")
        with self.transaction() as conn:
            row = conn.execute(
                "SELECT chapter_id,warning_code FROM segments WHERE id=?", (segment_id,)
            ).fetchone()
            if row is None:
                raise KeyError(f"Unknown segment id: {segment_id}")
            retained_warning = self._without_audio_attempt_warnings(
                str(row["warning_code"]) if row["warning_code"] else None
            )
            if normalized_delivery is None:
                conn.execute(
                    """
                    UPDATE segments SET status=?,attempt_count=attempt_count+1,generation_seed=?,
                        asr_text=NULL,asr_similarity=NULL,asr_wer=NULL,
                        warning_code=?,error=NULL,updated_at=? WHERE id=?
                    """,
                    (
                        SegmentStatus.GENERATING.value,
                        seed,
                        retained_warning,
                        time.time(),
                        segment_id,
                    ),
                )
            else:
                conn.execute(
                    """
                    UPDATE segments SET status=?,attempt_count=attempt_count+1,generation_seed=?,
                        generation_delivery_mode=?,generation_repair_round=?,
                        generation_policy_hash=?,asr_text=NULL,asr_similarity=NULL,asr_wer=NULL,
                        warning_code=?,error=NULL,updated_at=? WHERE id=?
                    """,
                    (
                        SegmentStatus.GENERATING.value,
                        seed,
                        normalized_delivery,
                        normalized_round,
                        normalized_policy_hash,
                        retained_warning,
                        time.time(),
                        segment_id,
                    ),
                )
            self._refresh_chapter_counts_conn(conn, int(row["chapter_id"]))

    def mark_signal_passed(
        self,
        segment_id: int,
        *,
        wav_path: Path,
        wav_sha256: str,
        duration: float,
        signal: dict[str, Any],
        generation_seed: int | None = None,
        warning_codes: Sequence[str] = (),
    ) -> None:
        if not isinstance(signal, dict):
            raise ValueError("segment signal checkpoint must be a dictionary")
        with self.transaction() as conn:
            row = conn.execute(
                "SELECT warning_code,text FROM segments WHERE id=?",
                (segment_id,),
            ).fetchone()
            if row is None:
                raise KeyError(f"Unknown segment id: {segment_id}")
            self._require_vocalization_provenance(
                signal,
                required=is_standalone_ha_gasp(str(row["text"])),
            )
            merged_warning = (
                str(row["warning_code"])
                if row["warning_code"]
                else None
            )
            for warning_code in warning_codes:
                merged_warning = self._merge_warning_codes(
                    merged_warning,
                    str(warning_code),
                )
            conn.execute(
                """
                UPDATE segments SET status=?,wav_path=?,wav_sha256=?,wav_duration=?,signal_json=?,
                    generation_seed=COALESCE(?,generation_seed),warning_code=?,error=NULL,
                    updated_at=? WHERE id=?
                """,
                (
                    SegmentStatus.SIGNAL_PASSED.value,
                    str(wav_path.resolve()),
                    wav_sha256,
                    duration,
                    json.dumps(signal, ensure_ascii=False),
                    generation_seed,
                    merged_warning,
                    time.time(),
                    segment_id,
                ),
            )

    def mark_asr_result(
        self,
        segment_id: int,
        *,
        passed: bool,
        transcript: str,
        similarity: float,
        wer: float,
        warning_code: str | None = None,
    ) -> None:
        with self.transaction() as conn:
            existing = conn.execute(
                "SELECT warning_code FROM segments WHERE id=?", (segment_id,)
            ).fetchone()
            merged_warning = self._merge_warning_codes(
                str(existing["warning_code"]) if existing and existing["warning_code"] else None,
                warning_code,
            )
            status = (
                SegmentStatus.ASR_PASSED.value
                if passed and merged_warning is None
                else SegmentStatus.WARNING.value
            )
            conn.execute(
                """
                UPDATE segments SET status=?,asr_text=?,asr_similarity=?,asr_wer=?,warning_code=?,updated_at=?
                WHERE id=?
                """,
                (status, transcript, similarity, wer, merged_warning, time.time(), segment_id),
            )

    def mark_verified(self, segment_id: int, warning_code: str | None = None) -> None:
        with self.transaction() as conn:
            existing = conn.execute(
                "SELECT chapter_id,warning_code FROM segments WHERE id=?", (segment_id,)
            ).fetchone()
            if existing is None:
                raise KeyError(f"Unknown segment id: {segment_id}")
            merged_warning = self._merge_warning_codes(
                str(existing["warning_code"]) if existing["warning_code"] else None,
                warning_code,
            )
            status = SegmentStatus.WARNING.value if merged_warning else SegmentStatus.VERIFIED.value
            conn.execute(
                """
                UPDATE segments SET status=?,warning_code=?,generation_frame_cap=NULL,
                    error=NULL,updated_at=? WHERE id=?
                """,
                (status, merged_warning, time.time(), segment_id),
            )
            chapter_id = int(existing["chapter_id"])
            self._refresh_chapter_counts_conn(conn, chapter_id)

    def mark_perceptual_result(
        self,
        segment_id: int,
        *,
        warning_code: str | None = None,
    ) -> None:
        """Finalize a segment after perceptual QA while replacing stale stage warnings."""
        with self.transaction() as conn:
            existing = conn.execute(
                "SELECT chapter_id,warning_code FROM segments WHERE id=?", (segment_id,)
            ).fetchone()
            if existing is None:
                raise KeyError(f"Unknown segment id: {segment_id}")
            retained_warning = self._without_perceptual_warnings(
                str(existing["warning_code"]) if existing["warning_code"] else None
            )
            merged_warning = self._merge_warning_codes(retained_warning, warning_code)
            status = SegmentStatus.WARNING.value if merged_warning else SegmentStatus.VERIFIED.value
            conn.execute(
                "UPDATE segments SET status=?,warning_code=?,error=NULL,updated_at=? WHERE id=?",
                (status, merged_warning, time.time(), segment_id),
            )
            self._refresh_chapter_counts_conn(conn, int(existing["chapter_id"]))

    def set_segment_warning_code(self, segment_id: int, warning_code: str) -> None:
        with self.transaction() as conn:
            row = conn.execute("SELECT warning_code FROM segments WHERE id=?", (segment_id,)).fetchone()
            if row is None:
                raise KeyError(f"Unknown segment id: {segment_id}")
            merged_warning = self._merge_warning_codes(
                str(row["warning_code"]) if row["warning_code"] else None,
                warning_code,
            )
            conn.execute(
                "UPDATE segments SET warning_code=?,updated_at=? WHERE id=?",
                (merged_warning, time.time(), segment_id),
            )

    def set_segment_generation_frame_cap(self, segment_id: int, frame_cap: int) -> None:
        normalized_cap = int(frame_cap)
        if normalized_cap <= 0:
            raise ValueError("generation frame cap must be positive")
        with self.connect() as conn:
            cursor = conn.execute(
                "UPDATE segments SET generation_frame_cap=?,updated_at=? WHERE id=?",
                (normalized_cap, time.time(), segment_id),
            )
            if cursor.rowcount != 1:
                raise KeyError(f"Unknown segment id: {segment_id}")

    def mark_failed(self, segment_id: int, error: str, warning_code: str = "SEGMENT_FAILED") -> None:
        with self.transaction() as conn:
            existing = conn.execute(
                "SELECT chapter_id,warning_code FROM segments WHERE id=?", (segment_id,)
            ).fetchone()
            if existing is None:
                raise KeyError(f"Unknown segment id: {segment_id}")
            merged_warning = self._merge_warning_codes(
                str(existing["warning_code"]) if existing["warning_code"] else None,
                warning_code,
            )
            conn.execute(
                "UPDATE segments SET status=?,warning_code=?,error=?,updated_at=? WHERE id=?",
                (SegmentStatus.FAILED.value, merged_warning, error[-8000:], time.time(), segment_id),
            )
            chapter_id = int(existing["chapter_id"])
            self._refresh_chapter_counts_conn(conn, chapter_id)

    def reset_segment_pending(self, segment_id: int, reason: str) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE segments SET status=(
                        CASE WHEN voice_profile_id IS NOT NULL AND kind IS NOT NULL AND speaker IS NOT NULL
                            THEN ? ELSE ? END
                    ),wav_path=NULL,wav_sha256=NULL,wav_duration=NULL,
                    signal_json=NULL,asr_text=NULL,asr_similarity=NULL,asr_wer=NULL,
                    warning_code=NULL,generation_seed=NULL,generation_delivery_mode='primary',
                    generation_repair_round=NULL,generation_policy_hash=NULL,error=?,updated_at=?
                WHERE id=?
                """,
                (
                    SegmentStatus.ANALYZED.value,
                    SegmentStatus.PENDING.value,
                    reason[-2000:],
                    time.time(),
                    segment_id,
                ),
            )
            row = conn.execute("SELECT chapter_id FROM segments WHERE id=?", (segment_id,)).fetchone()
            if row is not None:
                self._refresh_chapter_counts_conn(conn, int(row["chapter_id"]))

    def requeue_segment_for_asr(self, segment_id: int, reason: str) -> None:
        with self.transaction() as conn:
            row = conn.execute(
                """
                SELECT chapter_id,status,wav_path,wav_sha256,wav_duration,
                       signal_json,warning_code
                FROM segments WHERE id=?
                """,
                (segment_id,),
            ).fetchone()
            if row is None:
                raise KeyError(f"Unknown segment id: {segment_id}")
            if str(row["status"]) not in {
                SegmentStatus.VERIFIED.value,
                SegmentStatus.WARNING.value,
            }:
                raise RuntimeError("ASR-only requeue requires a verified or warning segment")
            if (
                not str(row["wav_path"] or "").strip()
                or not str(row["wav_sha256"] or "").strip()
                or row["wav_duration"] is None
                or row["signal_json"] is None
            ):
                raise RuntimeError("ASR-only requeue requires a committed signal-validated WAV")
            retained_warning = self._without_perceptual_warnings(
                self._without_asr_warnings(
                    str(row["warning_code"]) if row["warning_code"] else None
                )
            )
            conn.execute(
                """
                UPDATE segments SET status=?,asr_text=NULL,asr_similarity=NULL,asr_wer=NULL,
                    warning_code=?,error=?,updated_at=?
                WHERE id=?
                """,
                (
                    SegmentStatus.SIGNAL_PASSED.value,
                    retained_warning,
                    str(reason)[-2000:],
                    time.time(),
                    segment_id,
                ),
            )
            self._refresh_chapter_counts_conn(conn, int(row["chapter_id"]))

    def _refresh_chapter_counts_conn(self, conn: sqlite3.Connection, chapter_id: int) -> None:
        row = conn.execute(
            """
            SELECT
              SUM(CASE WHEN status='verified' THEN 1 ELSE 0 END) AS verified,
              SUM(CASE WHEN status='warning' THEN 1 ELSE 0 END) AS warnings,
              SUM(CASE WHEN status='failed' THEN 1 ELSE 0 END) AS failed
            FROM segments WHERE chapter_id=?
            """,
            (chapter_id,),
        ).fetchone()
        conn.execute(
            "UPDATE chapters SET verified_segments=?,warning_segments=?,failed_segments=? WHERE id=?",
            (int(row["verified"] or 0), int(row["warnings"] or 0), int(row["failed"] or 0), chapter_id),
        )

    def chapter_is_publishable(self, chapter_id: int) -> bool:
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT COUNT(*) AS total,
                       SUM(CASE WHEN status IN ('verified','warning') THEN 1 ELSE 0 END) AS accepted,
                       SUM(CASE WHEN status='failed' THEN 1 ELSE 0 END) AS failed
                FROM segments WHERE chapter_id=?
                """,
                (chapter_id,),
            ).fetchone()
            return bool(row and row["total"] and row["total"] == row["accepted"] and not row["failed"])

    def upsert_character(
        self,
        *,
        canonical_name: str,
        display_name: str,
        gender: str,
        age: str,
        personality: str,
        mentions: int,
        importance: str,
        confidence: float,
    ) -> int:
        now = time.time()
        with self.transaction() as conn:
            row = conn.execute(
                "SELECT id FROM characters WHERE canonical_name=?", (canonical_name,)
            ).fetchone()
            if row:
                character_id = int(row["id"])
                conn.execute(
                    """
                    UPDATE characters SET display_name=?,gender=?,age=?,personality=?,importance=?,
                        mention_count=?,confidence=?,updated_at=? WHERE id=?
                    """,
                    (
                        display_name,
                        gender,
                        age,
                        personality,
                        importance,
                        mentions,
                        confidence,
                        now,
                        character_id,
                    ),
                )
                return character_id
            cursor = conn.execute(
                """
                INSERT INTO characters(
                    canonical_name,display_name,gender,age,personality,importance,mention_count,
                    confidence,created_at,updated_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    canonical_name,
                    display_name,
                    gender,
                    age,
                    personality,
                    importance,
                    mentions,
                    confidence,
                    now,
                    now,
                ),
            )
            return int(cursor.lastrowid)

    def add_alias(self, character_id: int, alias: str, normalized_alias: str, confidence: float, source: str) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO character_aliases(character_id,alias,normalized_alias,confidence,source)
                VALUES(?,?,?,?,?)
                ON CONFLICT(normalized_alias) DO UPDATE SET
                    character_id=excluded.character_id,
                    alias=excluded.alias,
                    confidence=MAX(character_aliases.confidence, excluded.confidence),
                    source=excluded.source
                """,
                (character_id, alias, normalized_alias, confidence, source),
            )

    def list_characters(self) -> list[sqlite3.Row]:
        with self.connect() as conn:
            return list(conn.execute("SELECT * FROM characters ORDER BY importance,mention_count DESC"))

    def set_listener_pronunciation(
        self,
        *,
        surface: str,
        normalized_surface: str,
        spoken_form: str,
        source: str,
    ) -> None:
        """Write a reading a person chose, over any lock already there.

        upsert_pronunciation refuses to touch a locked row, which is right when the
        machine is the one asking: a lock is what protects a human decision from being
        overwritten by a transliteration. It is wrong when the human is the one asking, and
        it made a person unable to correct their own earlier answer - the command reported
        success and changed nothing.
        """
        now = time.time()
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO pronunciations(
                    surface,normalized_surface,spoken_form,confidence,source,locked,
                    created_at,updated_at
                ) VALUES(?,?,?,1.0,?,1,?,?)
                ON CONFLICT(normalized_surface) DO UPDATE SET
                    surface=excluded.surface,
                    spoken_form=excluded.spoken_form,
                    confidence=1.0,
                    source=excluded.source,
                    locked=1,
                    updated_at=excluded.updated_at
                """,
                (surface, normalized_surface, spoken_form, source, now, now),
            )

    def upsert_pronunciation(
        self,
        *,
        surface: str,
        normalized_surface: str,
        spoken_form: str,
        confidence: float,
        source: str = "analysis",
        locked: bool = False,
    ) -> None:
        now = time.time()
        with self.connect() as conn:
            self._upsert_pronunciation_conn(
                conn,
                {
                    "surface": surface,
                    "normalized_surface": normalized_surface,
                    "spoken_form": spoken_form,
                    "confidence": confidence,
                    "source": source,
                    "locked": locked,
                },
                now,
            )

    @staticmethod
    def _upsert_pronunciation_conn(
        conn: sqlite3.Connection,
        pronunciation: dict[str, Any],
        now: float,
    ) -> None:
        conn.execute(
            """
                INSERT INTO pronunciations(
                    surface,normalized_surface,spoken_form,confidence,source,locked,created_at,updated_at
                ) VALUES(?,?,?,?,?,?,?,?)
                ON CONFLICT(normalized_surface) DO UPDATE SET
                    surface=CASE
                        WHEN pronunciations.locked=0
                             AND (excluded.locked=1 OR excluded.confidence >= pronunciations.confidence)
                        THEN excluded.surface
                        ELSE pronunciations.surface
                    END,
                    spoken_form=CASE
                        WHEN pronunciations.locked=0
                             AND (excluded.locked=1 OR excluded.confidence >= pronunciations.confidence)
                        THEN excluded.spoken_form ELSE pronunciations.spoken_form
                    END,
                    confidence=MAX(pronunciations.confidence, excluded.confidence),
                    source=CASE
                        WHEN pronunciations.locked=0
                             AND (excluded.locked=1 OR excluded.confidence >= pronunciations.confidence)
                        THEN excluded.source ELSE pronunciations.source
                    END,
                    locked=MAX(pronunciations.locked, excluded.locked),
                    updated_at=excluded.updated_at
            """,
            (
                str(pronunciation["surface"]),
                str(pronunciation["normalized_surface"]),
                str(pronunciation["spoken_form"]),
                float(pronunciation["confidence"]),
                str(pronunciation.get("source", "analysis")),
                int(bool(pronunciation.get("locked", False))),
                now,
                now,
            ),
        )

    def list_pronunciations(self, minimum_confidence: float = 0.0) -> list[sqlite3.Row]:
        with self.connect() as conn:
            return list(
                conn.execute(
                    """
                    SELECT * FROM pronunciations
                    WHERE locked=1 OR confidence>=?
                    ORDER BY LENGTH(surface) DESC, normalized_surface
                    """,
                    (minimum_confidence,),
                )
            )

    def upsert_voice_profile(self, data: dict[str, Any]) -> int:
        now = time.time()
        with self.transaction() as conn:
            row = conn.execute(
                "SELECT id FROM voice_profiles WHERE voice_key=?", (data["voice_key"],)
            ).fetchone()
            values = (
                data["engine"],
                data.get("preset_name"),
                data.get("description", ""),
                int(data.get("seed", 1)),
                int(data.get("pitch_semitones", 0)),
                float(data.get("formant_ratio", 1.0)),
                data.get("status", "planned"),
            )
            if row:
                profile_id = int(row["id"])
                existing = conn.execute(
                    "SELECT * FROM voice_profiles WHERE id=?", (profile_id,)
                ).fetchone()
                assert existing is not None
                identity_changed = bool(
                    existing["engine"] != data["engine"]
                    or existing["description"] != data.get("description", "")
                    or int(existing["seed"]) != int(data.get("seed", 1))
                    or int(existing["pitch_semitones"]) != int(data.get("pitch_semitones", 0))
                    or abs(
                        float(existing["formant_ratio"])
                        - float(data.get("formant_ratio", 1.0))
                    )
                    > 1e-6
                )
                requested_preset = data.get("preset_name")
                preset_changed = bool(
                    requested_preset is not None
                    and str(existing["preset_name"] or "") != str(requested_preset)
                )
                if identity_changed or preset_changed:
                    raise RuntimeError(
                        f"Voice profile {data['voice_key']} is locked and cannot change during resume"
                    )
                return profile_id
            cursor = conn.execute(
                """
                INSERT INTO voice_profiles(
                    voice_key,engine,preset_name,description,seed,pitch_semitones,formant_ratio,
                    status,created_at,updated_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?)
                """,
                (data["voice_key"], *values, now, now),
            )
            return int(cursor.lastrowid)

    def list_voice_profiles(self) -> list[sqlite3.Row]:
        with self.connect() as conn:
            return list(conn.execute("SELECT * FROM voice_profiles ORDER BY id"))

    def voice_profile(self, profile_id: int) -> sqlite3.Row:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM voice_profiles WHERE id=?", (profile_id,)).fetchone()
            if row is None:
                raise KeyError(profile_id)
            return row

    def voice_profile_by_key(self, voice_key: str) -> sqlite3.Row:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM voice_profiles WHERE voice_key=?",
                (voice_key,),
            ).fetchone()
            if row is None:
                raise KeyError(voice_key)
            return row

    def event(self, level: str, code: str, message: str, details: dict[str, Any] | None = None) -> None:
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO runtime_events(timestamp,level,code,message,details_json) VALUES(?,?,?,?,?)",
                (time.time(), level, code, message, json.dumps(details, ensure_ascii=False) if details else None),
            )

    def list_events(self, level: str | None = None) -> list[sqlite3.Row]:
        with self.connect() as conn:
            if level is None:
                return list(conn.execute("SELECT * FROM runtime_events ORDER BY id"))
            return list(conn.execute("SELECT * FROM runtime_events WHERE level=? ORDER BY id", (level,)))

    def lease_worker(
        self,
        worker_name: str,
        pid: int,
        generation: int,
        state: str,
        current_item: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO worker_leases(worker_name,pid,generation,state,heartbeat_at,current_item,metadata_json)
                VALUES(?,?,?,?,?,?,?)
                ON CONFLICT(worker_name) DO UPDATE SET
                    pid=excluded.pid,generation=excluded.generation,state=excluded.state,
                    heartbeat_at=excluded.heartbeat_at,current_item=excluded.current_item,
                    metadata_json=excluded.metadata_json
                """,
                (
                    worker_name,
                    pid,
                    generation,
                    state,
                    time.time(),
                    current_item,
                    json.dumps(metadata, ensure_ascii=False) if metadata else None,
                ),
            )

    def clear_worker_lease(self, worker_name: str) -> None:
        with self.connect() as conn:
            conn.execute("DELETE FROM worker_leases WHERE worker_name=?", (worker_name,))

    def reset_in_progress_segments(self, reason: str = "Interrupted before commit") -> int:
        with self.connect() as conn:
            chapter_ids = [
                int(row[0])
                for row in conn.execute(
                    "SELECT DISTINCT chapter_id FROM segments WHERE status IN ('generating','asr_passed')"
                )
            ]
            # Candidate generation owns a separate immutable path. If legacy orchestration happened
            # to mark the segment itself as generating, restore the retained incumbent checkpoint
            # instead of deleting it. Phase-2 orchestration never mutates the segment during clarity.
            conn.execute(
                """
                UPDATE segments SET status='signal_passed',
                    asr_text=NULL,asr_similarity=NULL,asr_wer=NULL,error=?,updated_at=?
                WHERE status='generating'
                  AND wav_path IS NOT NULL AND wav_sha256 IS NOT NULL
                  AND wav_duration IS NOT NULL AND signal_json IS NOT NULL
                  AND EXISTS(
                      SELECT 1 FROM segment_candidates
                      WHERE segment_candidates.segment_id=segments.id
                        AND segment_candidates.incumbent_sha256=segments.wav_sha256
                        AND segment_candidates.state<>'promoted'
                  )
                """,
                (reason, time.time()),
            )
            cursor = conn.execute(
                """
                UPDATE segments SET status=(
                        CASE WHEN voice_profile_id IS NOT NULL AND kind IS NOT NULL AND speaker IS NOT NULL
                            THEN 'analyzed' ELSE 'pending' END
                    ),wav_path=NULL,wav_sha256=NULL,wav_duration=NULL,
                    signal_json=NULL,asr_text=NULL,asr_similarity=NULL,asr_wer=NULL,
                    warning_code=NULL,generation_seed=NULL,error=?,updated_at=?
                WHERE status='generating'
                """,
                (reason, time.time()),
            )
            # If the process died between ASR pass and the final verified commit, keep the WAV
            # but rerun ASR rather than trusting an incomplete transaction boundary.
            conn.execute(
                "UPDATE segments SET status='signal_passed',updated_at=? WHERE status='asr_passed'",
                (time.time(),),
            )
            for chapter_id in chapter_ids:
                self._refresh_chapter_counts_conn(conn, chapter_id)
            return int(cursor.rowcount)

    def artifact_by_key(self, artifact_key: str) -> sqlite3.Row | None:
        with self.connect() as conn:
            return conn.execute(
                "SELECT * FROM artifacts WHERE artifact_key=?", (artifact_key,)
            ).fetchone()

    def set_current_quality_policy(
        self,
        *,
        policy_hash: str,
        policy_version: int,
        policy: dict[str, Any],
    ) -> None:
        normalized_hash = str(policy_hash).strip()
        normalized_version = int(policy_version)
        if not normalized_hash:
            raise ValueError("quality policy hash must not be empty")
        if normalized_version < 1:
            raise ValueError("quality policy version must be positive")
        payload = json.dumps(
            policy,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        now = time.time()
        with self.transaction() as conn:
            existing = conn.execute(
                "SELECT policy_version,policy_json FROM quality_policies WHERE policy_hash=?",
                (normalized_hash,),
            ).fetchone()
            if existing is not None and (
                int(existing["policy_version"]) != normalized_version
                or str(existing["policy_json"]) != payload
            ):
                raise ValueError("quality policy hash is already registered with different content")
            conn.execute("UPDATE quality_policies SET active=0,updated_at=? WHERE active=1", (now,))
            conn.execute(
                """
                INSERT INTO quality_policies(
                    policy_hash,policy_version,policy_json,active,created_at,updated_at
                ) VALUES(?,?,?,?,?,?)
                ON CONFLICT(policy_hash) DO UPDATE SET
                    policy_version=excluded.policy_version,
                    policy_json=excluded.policy_json,
                    active=1,
                    updated_at=excluded.updated_at
                """,
                (
                    normalized_hash,
                    normalized_version,
                    payload,
                    1,
                    now,
                    now,
                ),
            )

    def current_quality_policy(self) -> sqlite3.Row | None:
        with self.connect() as conn:
            return conn.execute(
                "SELECT * FROM quality_policies WHERE active=1"
            ).fetchone()

    def quality_metadata_for_current_policy(
        self,
        verdict: str = QUALITY_VERDICT_PASS,
    ) -> dict[str, Any]:
        normalized_verdict = str(verdict).strip().casefold()
        if normalized_verdict not in QUALITY_VERDICTS:
            raise ValueError(f"Unsupported quality verdict: {verdict}")
        policy = self.current_quality_policy()
        if policy is None:
            raise RuntimeError("No active quality policy is locked for this project")
        return {
            "policy_hash": str(policy["policy_hash"]),
            "policy_version": int(policy["policy_version"]),
            "verdict": normalized_verdict,
        }

    def record_quality_check(
        self,
        *,
        scope: str,
        stage: str,
        artifact_sha256: str,
        policy_hash: str,
        policy_version: int,
        verdict: str,
        segment_id: int | None = None,
        chapter_id: int | None = None,
        metrics: dict[str, Any] | None = None,
        failure_codes: Sequence[str] = (),
        repair_action: str | None = None,
        attempt: int = 1,
    ) -> int:
        normalized_scope = str(scope).strip().casefold()
        normalized_stage = str(stage).strip()
        normalized_hash = str(policy_hash).strip()
        normalized_verdict = str(verdict).strip().casefold()
        normalized_version = int(policy_version)
        normalized_attempt = int(attempt)
        if normalized_scope not in QUALITY_SCOPES:
            raise ValueError(f"Unsupported quality scope: {scope}")
        if not normalized_stage:
            raise ValueError("quality check stage must not be empty")
        if not str(artifact_sha256).strip():
            raise ValueError("quality check artifact checksum must not be empty")
        if normalized_verdict not in QUALITY_VERDICTS:
            raise ValueError(f"Unsupported quality verdict: {verdict}")
        if normalized_version < 1 or normalized_attempt < 1:
            raise ValueError("quality policy version and attempt must be positive")
        if normalized_scope == QUALITY_SCOPE_SEGMENT:
            if segment_id is None or chapter_id is not None:
                raise ValueError("segment quality checks require only segment_id")
        elif chapter_id is None or segment_id is not None:
            raise ValueError("chapter quality checks require only chapter_id")

        with self.transaction() as conn:
            policy = conn.execute(
                "SELECT policy_version FROM quality_policies WHERE policy_hash=?",
                (normalized_hash,),
            ).fetchone()
            if policy is None or int(policy["policy_version"]) != normalized_version:
                raise ValueError("quality check policy hash/version is not registered")
            cursor = conn.execute(
                """
                INSERT INTO quality_checks(
                    scope,stage,segment_id,chapter_id,artifact_sha256,
                    policy_hash,policy_version,verdict,metrics_json,
                    failure_codes_json,repair_action,attempt,created_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    normalized_scope,
                    normalized_stage,
                    segment_id,
                    chapter_id,
                    str(artifact_sha256).strip(),
                    normalized_hash,
                    normalized_version,
                    normalized_verdict,
                    json.dumps(metrics or {}, ensure_ascii=False, sort_keys=True),
                    json.dumps(list(failure_codes), ensure_ascii=False),
                    repair_action,
                    normalized_attempt,
                    time.time(),
                ),
            )
            return int(cursor.lastrowid)

    @staticmethod
    def _normalized_sha256(value: str, label: str) -> str:
        normalized = str(value or "").strip().casefold()
        if len(normalized) != 64 or any(character not in "0123456789abcdef" for character in normalized):
            raise ValueError(f"{label} must be a 64-character hexadecimal SHA-256")
        return normalized

    @staticmethod
    def _normalized_pronunciation_delivery_variant(value: str) -> str:
        normalized = str(value or "").strip().casefold()
        if normalized not in PRONUNCIATION_DELIVERY_VARIANTS:
            raise ValueError("unsupported pronunciation delivery variant")
        return normalized

    @staticmethod
    def _normalized_generation_strategy(value: str) -> str:
        normalized = str(value or "").strip().casefold()
        if normalized not in GENERATION_STRATEGIES:
            raise ValueError("unsupported segment candidate generation strategy")
        return normalized

    @staticmethod
    def _normalized_candidate_repair_requirement(value: str) -> str:
        normalized = str(value or "").strip().casefold()
        if normalized not in {
            STANDARD_CANDIDATE_GATE_REQUIREMENT,
            NATURALNESS_IMPROVEMENT_REQUIREMENT,
        }:
            raise ValueError("unsupported segment candidate repair requirement")
        return normalized

    @staticmethod
    def _json_object(value: Any, label: str) -> dict[str, Any]:
        try:
            decoded = json.loads(str(value or "{}"))
        except (TypeError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"{label} is not valid JSON") from exc
        if not isinstance(decoded, dict):
            raise RuntimeError(f"{label} must be a JSON object")
        return decoded

    @classmethod
    def _policy_perceptual_required_conn(
        cls,
        conn: sqlite3.Connection,
        policy_hash: str,
    ) -> bool | None:
        policy = conn.execute(
            "SELECT policy_json FROM quality_policies WHERE policy_hash=?",
            (str(policy_hash).strip(),),
        ).fetchone()
        if policy is None:
            raise RuntimeError("segment candidate quality policy is missing")
        payload = cls._json_object(
            policy["policy_json"],
            "segment candidate quality policy",
        )
        settings = payload.get("settings")
        if settings is None:
            return None
        if not isinstance(settings, dict):
            raise RuntimeError("segment candidate quality policy settings are malformed")
        perceptual = settings.get("perceptual_qa")
        if perceptual is None:
            return None
        if not isinstance(perceptual, dict):
            raise RuntimeError(
                "segment candidate perceptual quality policy is malformed"
            )
        enabled = perceptual.get("enabled")
        if enabled is None:
            return None
        if not isinstance(enabled, bool):
            raise RuntimeError(
                "segment candidate perceptual quality policy enabled flag is malformed"
            )
        return enabled

    @staticmethod
    def _candidate_signal_provenance(signal: dict[str, Any]) -> dict[str, Any]:
        required_fields = {
            "spoken_text_sha256",
            "pronunciation_delivery_variant",
            "voice_profile_id",
            "pitch_semitones",
            "effective_pitch_semitones",
            "pitch_variant_skipped",
            "pitch_variant_mixed",
        }
        missing = required_fields - signal.keys()
        if missing:
            raise ValueError(
                "segment candidate signal lacks locked provenance: "
                + ", ".join(sorted(missing))
            )
        spoken_text_sha256 = ProjectDB._normalized_sha256(
            str(signal["spoken_text_sha256"]),
            "segment candidate spoken-text checksum",
        )
        pronunciation_delivery_variant = (
            ProjectDB._normalized_pronunciation_delivery_variant(
                str(signal["pronunciation_delivery_variant"])
            )
        )
        try:
            voice_profile_id = int(signal["voice_profile_id"])
            pitch_semitones = int(signal["pitch_semitones"])
        except (TypeError, ValueError) as exc:
            raise ValueError("segment candidate voice and pitch provenance must be integers") from exc
        if voice_profile_id <= 0:
            raise ValueError("segment candidate voice profile id must be positive")
        for field in ("pitch_variant_skipped", "pitch_variant_mixed"):
            if signal[field] not in (False, True, 0, 1, 0.0, 1.0):
                raise ValueError(f"segment candidate {field} must be boolean")
        pitch_skipped = bool(signal["pitch_variant_skipped"])
        pitch_mixed = bool(signal["pitch_variant_mixed"])
        effective_value = signal["effective_pitch_semitones"]
        if pitch_mixed:
            if effective_value is not None:
                raise ValueError("mixed candidate pitch provenance requires a null effective pitch")
            effective_pitch = None
        else:
            try:
                effective_pitch = int(effective_value)
            except (TypeError, ValueError) as exc:
                raise ValueError("candidate effective pitch provenance must be an integer") from exc
        if pitch_skipped and effective_pitch != 0:
            raise ValueError("a skipped pitch transform must retain effective pitch zero")
        return {
            "spoken_text_sha256": spoken_text_sha256,
            "pronunciation_delivery_variant": pronunciation_delivery_variant,
            "voice_profile_id": voice_profile_id,
            "pitch_semitones": pitch_semitones,
            "effective_pitch_semitones": effective_pitch,
            "pitch_variant_skipped": pitch_skipped,
            "pitch_variant_mixed": pitch_mixed,
        }

    @staticmethod
    def _candidate_signal_immutable_projection(
        signal: Mapping[str, Any],
        *,
        default_pronunciation_variant: str | None = None,
    ) -> dict[str, Any]:
        pronunciation_variant = signal.get("pronunciation_delivery_variant")
        if pronunciation_variant is None:
            pronunciation_variant = default_pronunciation_variant
        return {
            "tts_delivery_mode": signal.get(
                "tts_delivery_mode",
                signal.get("delivery_mode"),
            ),
            "asr_clarity_repair_round": signal.get(
                "asr_clarity_repair_round",
                signal.get("repair_round"),
            ),
            "spoken_text_sha256": signal.get("spoken_text_sha256"),
            "pronunciation_delivery_variant": pronunciation_variant,
            "voice_profile_id": signal.get("voice_profile_id"),
            "pitch_semitones": signal.get("pitch_semitones"),
            "effective_pitch_semitones": signal.get(
                "effective_pitch_semitones"
            ),
            "pitch_variant_skipped": signal.get("pitch_variant_skipped"),
            "pitch_variant_mixed": signal.get("pitch_variant_mixed"),
            "generation_ceiling_hit": signal.get("generation_ceiling_hit"),
            "generation_endpoint_active": signal.get(
                "generation_endpoint_active"
            ),
            "split_checkpoint_seed": signal.get("split_checkpoint_seed"),
            "split_seed_salt_prefix": signal.get("split_seed_salt_prefix"),
            SPLIT_STRATEGY_FIELD: signal.get(SPLIT_STRATEGY_FIELD),
            SPLIT_MAX_CHARS_FIELD: signal.get(SPLIT_MAX_CHARS_FIELD),
            "split_parts": signal.get("split_parts") or [],
            POSTPROCESS_PROFILE_FIELD: signal.get(POSTPROCESS_PROFILE_FIELD),
            POSTPROCESS_SOURCE_CANDIDATE_ID_FIELD: signal.get(
                POSTPROCESS_SOURCE_CANDIDATE_ID_FIELD
            ),
            POSTPROCESS_SOURCE_SHA256_FIELD: signal.get(
                POSTPROCESS_SOURCE_SHA256_FIELD
            ),
            POSTPROCESS_SOURCE_SAMPLE_RATE_FIELD: signal.get(
                POSTPROCESS_SOURCE_SAMPLE_RATE_FIELD
            ),
            POSTPROCESS_SOURCE_SAMPLES_FIELD: signal.get(
                POSTPROCESS_SOURCE_SAMPLES_FIELD
            ),
            POSTPROCESS_OUTPUT_SAMPLES_FIELD: signal.get(
                POSTPROCESS_OUTPUT_SAMPLES_FIELD
            ),
            **{
                field: signal.get(field)
                for field in HA_VOCALIZATION_PROVENANCE_FIELDS
            },
        }

    @staticmethod
    def _require_vocalization_provenance(
        signal: Mapping[str, Any],
        *,
        required: bool,
    ) -> None:
        sampling_fields_present = {
            field
            for field in HA_VOCALIZATION_SAMPLING_PROVENANCE_FIELDS
            if signal.get(field) is not None
        }
        padding_fields_present = {
            field
            for field in HA_VOCALIZATION_PADDING_PROVENANCE_FIELDS
            if signal.get(field) is not None
        }
        if not sampling_fields_present and not padding_fields_present:
            if required:
                raise RuntimeError(
                    "standalone Ha gasp signal lacks its vocalization delivery provenance"
                )
            return
        if sampling_fields_present != set(
            HA_VOCALIZATION_SAMPLING_PROVENANCE_FIELDS
        ):
            raise RuntimeError(
                "vocalization sampling provenance must be complete"
            )
        if signal.get(HA_VOCALIZATION_PROFILE_FIELD) != (
            HA_VOCALIZATION_DELIVERY_PROFILE
        ):
            raise RuntimeError("vocalization delivery profile is unsupported")
        for field, expected in (
            (
                HA_VOCALIZATION_TEMPERATURE_FIELD,
                HA_VOCALIZATION_MAX_TEMPERATURE,
            ),
            (HA_VOCALIZATION_TOP_P_FIELD, HA_VOCALIZATION_MAX_TOP_P),
        ):
            value = signal.get(field)
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(float(value))
                or not math.isclose(float(value), expected, abs_tol=1e-9)
            ):
                raise RuntimeError(
                    f"vocalization sampling provenance field {field} drifted"
                )
        max_new_frames = signal.get(HA_VOCALIZATION_MAX_NEW_FRAMES_FIELD)
        if (
            isinstance(max_new_frames, bool)
            or not isinstance(max_new_frames, int)
            or max_new_frames != HA_VOCALIZATION_MAX_NEW_FRAMES
        ):
            raise RuntimeError(
                "vocalization generation frame cap differs from its locked profile"
            )
        if not required:
            raise RuntimeError(
                "vocalization delivery provenance is attached to a non-gasp segment"
            )
        if padding_fields_present != set(
            HA_VOCALIZATION_PADDING_PROVENANCE_FIELDS
        ):
            raise RuntimeError("vocalization raw-audio provenance must be complete")
        count_fields = (
            HA_VOCALIZATION_SAMPLE_RATE_FIELD,
            HA_VOCALIZATION_ORIGINAL_SAMPLES_FIELD,
            HA_VOCALIZATION_TARGET_SAMPLES_FIELD,
            HA_VOCALIZATION_PADDING_SAMPLES_FIELD,
            HA_VOCALIZATION_FINAL_SAMPLES_FIELD,
        )
        if any(
            isinstance(signal.get(field), bool)
            or not isinstance(signal.get(field), int)
            for field in count_fields
        ):
            raise RuntimeError("vocalization padding sample counts are malformed")
        sample_rate = int(signal[HA_VOCALIZATION_SAMPLE_RATE_FIELD])
        original_samples = int(signal[HA_VOCALIZATION_ORIGINAL_SAMPLES_FIELD])
        target_samples = int(signal[HA_VOCALIZATION_TARGET_SAMPLES_FIELD])
        padding_samples = int(signal[HA_VOCALIZATION_PADDING_SAMPLES_FIELD])
        final_samples = int(signal[HA_VOCALIZATION_FINAL_SAMPLES_FIELD])
        if (
            sample_rate <= 0
            or original_samples <= 0
            or target_samples <= 0
            or padding_samples < 0
            or final_samples <= 0
        ):
            raise RuntimeError("vocalization padding sample counts are outside their domain")
        if (
            target_samples != original_samples
            or padding_samples != 0
            or final_samples != original_samples
        ):
            raise RuntimeError(
                "vocalization profile must attest that no silence padding was added"
            )
        duration = signal.get("duration")
        if (
            isinstance(duration, bool)
            or not isinstance(duration, (int, float))
            or not math.isfinite(float(duration))
            or not math.isclose(
                float(duration),
                final_samples / sample_rate,
                abs_tol=1.0 / sample_rate,
            )
        ):
            raise RuntimeError("vocalization raw-audio duration differs from its samples")
        endpoint_active = signal.get("generation_endpoint_active")
        if endpoint_active not in (False, True, 0, 1, 0.0, 1.0):
            raise RuntimeError(
                "vocalization raw endpoint provenance must be boolean"
            )

    @classmethod
    def _require_candidate_vocalization_provenance_conn(
        cls,
        conn: sqlite3.Connection,
        candidate: sqlite3.Row,
        signal: Mapping[str, Any],
    ) -> None:
        segment = conn.execute(
            "SELECT text FROM segments WHERE id=?",
            (int(candidate["segment_id"]),),
        ).fetchone()
        if segment is None:
            raise KeyError(f"Unknown segment id: {candidate['segment_id']}")
        cls._require_vocalization_provenance(
            signal,
            required=is_standalone_ha_gasp(str(segment["text"])),
        )

    @staticmethod
    def _candidate_split_generation_expected_conn(
        conn: sqlite3.Connection,
        candidate: sqlite3.Row,
    ) -> bool:
        segment = conn.execute(
            "SELECT stable_id FROM segments WHERE id=?",
            (int(candidate["segment_id"]),),
        ).fetchone()
        profile = conn.execute(
            "SELECT voice_key FROM voice_profiles WHERE id=?",
            (int(candidate["expected_voice_profile_id"]),),
        ).fetchone()
        if segment is None or profile is None:
            raise RuntimeError(
                "candidate split schedule cannot resolve its stable voice identity"
            )
        seed_salt = segment_candidate_split_seed_salt(
            int(candidate["repair_round"]),
            str(candidate["pronunciation_delivery_variant"]),
        )
        expected_seed = stable_int(
            f"segment::{segment['stable_id']}::{profile['voice_key']}::{seed_salt}"
        )
        return int(candidate["generation_seed"]) == expected_seed

    @staticmethod
    def _candidate_split_part_expected_seed_conn(
        conn: sqlite3.Connection,
        candidate: sqlite3.Row,
        *,
        seed_salt_prefix: str,
        index: int,
    ) -> int:
        segment = conn.execute(
            "SELECT stable_id FROM segments WHERE id=?",
            (int(candidate["segment_id"]),),
        ).fetchone()
        profile = conn.execute(
            "SELECT voice_key FROM voice_profiles WHERE id=?",
            (int(candidate["expected_voice_profile_id"]),),
        ).fetchone()
        if segment is None or profile is None:
            raise RuntimeError(
                "candidate split part cannot resolve its stable voice identity"
            )
        part_stable_id = f"{segment['stable_id']}_part{index:02d}"
        part_seed_salt = f"{seed_salt_prefix}_part_{index}"
        return stable_int(
            f"segment::{part_stable_id}::{profile['voice_key']}::{part_seed_salt}"
        )

    @staticmethod
    def _require_candidate_split_provenance(
        conn: sqlite3.Connection,
        candidate: sqlite3.Row,
        signal: Mapping[str, Any],
    ) -> None:
        checkpoint_seed = signal.get("split_checkpoint_seed")
        seed_salt_prefix = signal.get("split_seed_salt_prefix")
        split_strategy = signal.get(SPLIT_STRATEGY_FIELD)
        split_max_chars = signal.get(SPLIT_MAX_CHARS_FIELD)
        split_parts = signal.get("split_parts")
        split_fields_present = (
            checkpoint_seed is not None
            or seed_salt_prefix is not None
            or split_strategy is not None
            or split_max_chars is not None
            or split_parts not in (None, [])
        )
        try:
            generation_strategy = ProjectDB._normalized_generation_strategy(
                str(candidate["generation_strategy"])
            )
        except ValueError as exc:
            raise RuntimeError(
                "segment candidate generation strategy is invalid"
            ) from exc
        if generation_strategy == GENERATION_STRATEGY_DIRECT:
            if split_fields_present:
                raise RuntimeError(
                    "direct candidate cannot carry split generation provenance"
                )
            return
        if not split_fields_present:
            raise RuntimeError(
                "candidate split generation lacks its immutable split provenance"
            )
        if not ProjectDB._candidate_split_generation_expected_conn(
            conn,
            candidate,
        ):
            raise RuntimeError(
                "candidate split generation seed differs from its deterministic schedule"
            )
        if (
            isinstance(checkpoint_seed, bool)
            or not isinstance(checkpoint_seed, int)
            or checkpoint_seed != int(candidate["generation_seed"])
        ):
            raise RuntimeError(
                "candidate split checkpoint seed differs from its generation ledger"
            )
        if not isinstance(seed_salt_prefix, str) or not seed_salt_prefix.strip():
            raise RuntimeError("candidate split seed-salt prefix is missing")
        expected_seed_salt_prefix = segment_candidate_split_seed_salt(
            int(candidate["repair_round"]),
            str(candidate["pronunciation_delivery_variant"]),
        )
        if seed_salt_prefix != expected_seed_salt_prefix:
            raise RuntimeError(
                "candidate split seed-salt prefix differs from its deterministic schedule"
            )
        expected_split_strategy = (
            CLAUSE_SPLIT_STRATEGY
            if (
                int(candidate["repair_round"]) + 1
                == int(candidate["repair_budget"])
                and str(candidate["pronunciation_delivery_variant"])
                == PRONUNCIATION_DELIVERY_SOURCE
            )
            else SENTENCE_SPLIT_STRATEGY
        )
        if split_strategy != expected_split_strategy:
            raise RuntimeError(
                "candidate split strategy differs from its deterministic schedule"
            )
        expected_split_max_chars = SPLIT_MAX_CHARS_BY_STRATEGY[
            expected_split_strategy
        ]
        if (
            isinstance(split_max_chars, bool)
            or not isinstance(split_max_chars, int)
            or split_max_chars != expected_split_max_chars
        ):
            raise RuntimeError(
                "candidate split max chars differs from its deterministic strategy"
            )
        if not isinstance(split_parts, list) or not split_parts:
            raise RuntimeError("candidate split provenance requires non-empty parts")
        for index, part in enumerate(split_parts):
            if (
                not isinstance(part, dict)
                or isinstance(part.get("index"), bool)
                or not isinstance(part.get("index"), int)
                or part.get("index") != index
            ):
                raise RuntimeError(
                    "candidate split provenance requires contiguous ordered parts"
                )
            if (
                isinstance(part.get("generation_seed"), bool)
                or not isinstance(part.get("generation_seed"), int)
            ):
                raise RuntimeError("candidate split part generation seed is malformed")
            expected_part_seed = (
                ProjectDB._candidate_split_part_expected_seed_conn(
                    conn,
                    candidate,
                    seed_salt_prefix=seed_salt_prefix,
                    index=index,
                )
            )
            if int(part["generation_seed"]) != expected_part_seed:
                raise RuntimeError(
                    "candidate split part generation seed differs from its "
                    "deterministic schedule"
                )
            if (
                str(part.get("pronunciation_delivery_variant") or "")
                != str(candidate["pronunciation_delivery_variant"])
            ):
                raise RuntimeError(
                    "candidate split part pronunciation variant differs from its allocation"
                )
            ProjectDB._normalized_sha256(
                str(part.get("spoken_text_sha256") or ""),
                "candidate split part spoken-text checksum",
            )

    @staticmethod
    def _normalized_postprocess_profile(value: str) -> str:
        normalized = str(value or "").strip()
        if normalized not in POSTPROCESS_PROFILES:
            raise ValueError("unsupported segment candidate postprocess profile")
        return normalized

    @classmethod
    def _policy_tempo_rescue_minimum_duration_conn(
        cls,
        conn: sqlite3.Connection,
        policy_hash: str,
    ) -> float | None:
        policy = cls._require_candidate_policy_conn(
            conn,
            policy_hash,
            active=False,
        )
        payload = cls._json_object(
            policy["policy_json"],
            "segment candidate quality policy",
        )
        algorithms = payload.get("algorithms")
        settings = payload.get("settings")
        if algorithms is None and settings is None:
            return None
        if not isinstance(algorithms, dict) or not isinstance(settings, dict):
            raise RuntimeError("segment candidate quality policy is malformed")
        algorithm = algorithms.get("candidate_postprocess")
        contract = settings.get("candidate_postprocess")
        if algorithm is None and contract is None:
            return None
        expected_contract = {
            "profile": POSTPROCESS_PROFILE_TEMPO,
            "tempo_numerator": POSTPROCESS_TEMPO_NUMERATOR,
            "tempo_denominator": POSTPROCESS_TEMPO_DENOMINATOR,
            "codec": POSTPROCESS_OUTPUT_CODEC,
        }
        if algorithm != POSTPROCESS_ALGORITHM or contract != expected_contract:
            raise RuntimeError("segment candidate tempo-rescue policy contract is malformed")
        perceptual = settings.get("perceptual_qa")
        if not isinstance(perceptual, dict):
            raise RuntimeError(
                "segment candidate tempo-rescue policy lacks perceptual settings"
            )
        if perceptual.get("enabled") is not True:
            return None
        try:
            minimum_duration = float(perceptual["minimum_duration_seconds"])
        except (KeyError, TypeError, ValueError) as exc:
            raise RuntimeError(
                "segment candidate tempo-rescue perceptual duration is malformed"
            ) from exc
        if not math.isfinite(minimum_duration) or minimum_duration <= 0.0:
            raise RuntimeError(
                "segment candidate tempo-rescue perceptual duration is invalid"
            )
        return minimum_duration

    @staticmethod
    def _pcm16_mono_wav_shape(path: Path, label: str) -> tuple[int, int]:
        try:
            with wave.open(str(path), "rb") as reader:
                channels = int(reader.getnchannels())
                sample_width = int(reader.getsampwidth())
                sample_rate = int(reader.getframerate())
                sample_count = int(reader.getnframes())
                compression = str(reader.getcomptype())
        except (OSError, wave.Error) as exc:
            raise RuntimeError(f"{label} is not a readable PCM WAV: {exc}") from exc
        if (
            channels != 1
            or sample_width != 2
            or sample_rate <= 0
            or sample_count <= 0
            or compression != "NONE"
        ):
            raise RuntimeError(f"{label} is not mono PCM16 audio")
        return sample_rate, sample_count

    @classmethod
    def _tempo_source_eligibility_reason_conn(
        cls,
        conn: sqlite3.Connection,
        candidate: sqlite3.Row,
        *,
        require_current_incumbent: bool = True,
    ) -> str | None:
        minimum_duration = cls._policy_tempo_rescue_minimum_duration_conn(
            conn,
            str(candidate["policy_hash"]),
        )
        if minimum_duration is None:
            return "the quality policy does not enable immutable tempo rescue"
        if str(candidate["postprocess_profile"]) != POSTPROCESS_PROFILE_NONE:
            return "tempo rescue cannot chain a postprocessed candidate"
        if int(candidate["repair_round"]) + 1 != int(candidate["repair_budget"]):
            return "tempo rescue requires the final ordinary repair candidate"
        if str(candidate["state"]) != SEGMENT_CANDIDATE_DUAL_FAILED:
            return "tempo rescue requires a terminal dual-decode failure"
        if str(candidate["generation_strategy"]) != GENERATION_STRATEGY_DIRECT:
            return "tempo rescue requires direct waveform provenance"
        if (
            str(candidate["pronunciation_delivery_variant"])
            != PRONUNCIATION_DELIVERY_LOCKED
        ):
            return "tempo rescue requires the locked pronunciation delivery"
        if (
            str(candidate["candidate_repair_requirement"])
            != STANDARD_CANDIDATE_GATE_REQUIREMENT
            or not bool(candidate["perceptual_required"])
            or candidate["perceptual_check_id"] is not None
        ):
            return "tempo rescue requires the standard mandatory perceptual gate"
        if float(candidate["wav_duration"] or 0.0) < minimum_duration:
            return "tempo rescue excludes short audio"
        if require_current_incumbent:
            segment = cls._require_candidate_incumbent_conn(conn, candidate)
        else:
            segment = conn.execute(
                "SELECT * FROM segments WHERE id=?",
                (int(candidate["segment_id"]),),
            ).fetchone()
            if segment is None:
                raise KeyError(f"Unknown segment id: {candidate['segment_id']}")
        if is_standalone_ha_gasp(str(segment["text"])):
            return "tempo rescue excludes standalone vocalizations"
        file_error = cls._candidate_file_error(candidate)
        if file_error:
            raise RuntimeError(file_error)
        signal = cls._json_object(candidate["signal_json"], "candidate signal metrics")
        cls._require_candidate_split_provenance(conn, candidate, signal)
        cls._require_candidate_vocalization_provenance_conn(conn, candidate, signal)
        signal_provenance = cls._candidate_signal_provenance(signal)
        cls._require_candidate_delivery_provenance(candidate, signal_provenance)
        if cls._candidate_blocking_signal_flags(signal):
            return "tempo rescue excludes a candidate with blocking signal flags"
        if candidate["beam_check_id"] is None or candidate["greedy_check_id"] is None:
            raise RuntimeError("tempo rescue source lacks complete dual-decode evidence")
        decoded: list[tuple[sqlite3.Row, dict[str, Any]]] = []
        for confirmation, check_field in ((False, "beam_check_id"), (True, "greedy_check_id")):
            decoded.append(
                cls._validated_candidate_decode_check_conn(
                    conn,
                    candidate,
                    int(candidate[check_field]),
                    confirmation=confirmation,
                )
            )
        passed = [item for item in decoded if str(item[0]["verdict"]) == QUALITY_VERDICT_PASS]
        failed = [item for item in decoded if str(item[0]["verdict"]) == "fail"]
        if len(passed) != 1 or len(failed) != 1:
            return "tempo rescue requires exactly one passing and one content-mismatch decode"

        def anchors_are_passing(metrics: Mapping[str, Any]) -> bool:
            anchors = metrics.get("locked_name_anchor_metrics")
            if not isinstance(anchors, dict):
                return False
            try:
                anchor_count = int(anchors["anchor_count"])
                required_count = int(anchors["required_occurrence_count"])
                matched_count = int(anchors["matched_occurrence_count"])
            except (KeyError, TypeError, ValueError):
                return False
            return (
                anchors.get("adjudicated") is True
                and anchors.get("passed") is True
                and anchors.get("status") == "pass"
                and anchors.get("failure_codes") == []
                and anchor_count >= 1
                and required_count == anchor_count
                and matched_count == required_count
            )

        if not all(anchors_are_passing(metrics) for _check, metrics in decoded):
            return "tempo rescue requires every locked-name anchor to pass"
        failed_metrics = failed[0][1]
        if (
            failed_metrics.get("verdict") != "mismatch"
            or failed_metrics.get("passed") is not False
            or failed_metrics.get("reason") != TEMPO_RESCUE_ASR_FAILURE_REASON
            or failed_metrics.get("repairable") is not True
            or failed_metrics.get("severe") is not False
            or failed_metrics.get("context_mode") != "direct"
            or failed_metrics.get("failure_codes")
            != [TEMPO_RESCUE_ASR_FAILURE_REASON]
        ):
            return "tempo rescue requires one ordinary repairable ASR content mismatch"
        return None

    @classmethod
    def _require_candidate_postprocess_provenance_conn(
        cls,
        conn: sqlite3.Connection,
        candidate: sqlite3.Row,
        signal: Mapping[str, Any],
    ) -> None:
        profile = cls._normalized_postprocess_profile(
            str(candidate["postprocess_profile"])
        )
        source_candidate_id = candidate["postprocess_source_candidate_id"]
        source_sha256 = candidate["postprocess_source_sha256"]
        if profile == POSTPROCESS_PROFILE_NONE:
            if source_candidate_id is not None or source_sha256 is not None:
                raise RuntimeError(
                    "identity candidate cannot bind a postprocess source artifact"
                )
            if signal.get(POSTPROCESS_PROFILE_FIELD) not in (
                None,
                POSTPROCESS_PROFILE_NONE,
            ) or any(
                signal.get(field) is not None
                for field in (
                    POSTPROCESS_SOURCE_CANDIDATE_ID_FIELD,
                    POSTPROCESS_SOURCE_SHA256_FIELD,
                    POSTPROCESS_SOURCE_SAMPLE_RATE_FIELD,
                    POSTPROCESS_SOURCE_SAMPLES_FIELD,
                    POSTPROCESS_OUTPUT_SAMPLES_FIELD,
                )
            ):
                raise RuntimeError(
                    "identity candidate carries unexpected postprocess provenance"
                )
            return

        if source_candidate_id is None:
            raise RuntimeError("tempo candidate has no source candidate binding")
        normalized_source_sha256 = cls._normalized_sha256(
            str(source_sha256 or ""),
            "tempo candidate source checksum",
        )
        if (
            signal.get(POSTPROCESS_PROFILE_FIELD) != POSTPROCESS_PROFILE_TEMPO
            or signal.get(POSTPROCESS_SOURCE_CANDIDATE_ID_FIELD)
            != int(source_candidate_id)
            or str(signal.get(POSTPROCESS_SOURCE_SHA256_FIELD) or "").casefold()
            != normalized_source_sha256
        ):
            raise RuntimeError(
                "tempo candidate signal differs from its immutable source binding"
            )
        sample_fields = (
            POSTPROCESS_SOURCE_SAMPLE_RATE_FIELD,
            POSTPROCESS_SOURCE_SAMPLES_FIELD,
            POSTPROCESS_OUTPUT_SAMPLES_FIELD,
        )
        if any(
            isinstance(signal.get(field), bool)
            or not isinstance(signal.get(field), int)
            or int(signal[field]) <= 0
            for field in sample_fields
        ):
            raise RuntimeError("tempo candidate sample provenance is malformed")
        source_sample_rate = int(signal[POSTPROCESS_SOURCE_SAMPLE_RATE_FIELD])
        source_samples = int(signal[POSTPROCESS_SOURCE_SAMPLES_FIELD])
        output_samples = int(signal[POSTPROCESS_OUTPUT_SAMPLES_FIELD])
        if output_samples <= source_samples:
            raise RuntimeError("tempo candidate did not lengthen its source waveform")
        expected_output_samples = source_samples / POSTPROCESS_TEMPO_FACTOR
        if (
            abs(output_samples - expected_output_samples) / expected_output_samples
            > POSTPROCESS_SAMPLE_COUNT_RELATIVE_TOLERANCE
        ):
            raise RuntimeError("tempo candidate sample count differs from its locked factor")
        source = cls._candidate_row_conn(conn, int(source_candidate_id))
        if int(source["id"]) == int(candidate["id"]):
            raise RuntimeError("tempo candidate cannot use itself as its source")
        require_all(
            "tempo candidate source binding is not a final direct candidate",
            ("postprocess_profile",
             str(source["postprocess_profile"]) != POSTPROCESS_PROFILE_NONE),
            ("source_sha256", str(source["wav_sha256"] or "").casefold()
             != normalized_source_sha256),
            ("segment_id", int(source["segment_id"]) != int(candidate["segment_id"])),
            ("policy_hash",
             str(source["policy_hash"]) != str(candidate["policy_hash"])),
            ("incumbent_sha256",
             str(source["incumbent_sha256"]) != str(candidate["incumbent_sha256"])),
            ("repair_budget",
             int(source["repair_budget"]) != int(candidate["repair_budget"])),
            ("repair_round_follows",
             int(source["repair_round"]) + 1 != int(candidate["repair_round"])),
            ("budget_exhausted",
             int(candidate["repair_round"]) != int(candidate["repair_budget"])),
            ("generation_strategy",
             str(source["generation_strategy"]) != GENERATION_STRATEGY_DIRECT),
            source_candidate_id=int(source["id"]),
            candidate_id=int(candidate["id"]),
            source_round=int(source["repair_round"]),
            candidate_round=int(candidate["repair_round"]),
        )
        for field in (
            "expected_voice_profile_id",
            "expected_pitch_semitones",
            "pronunciation_delivery_variant",
            "expected_spoken_text_sha256",
            "generation_strategy",
            "tts_attempt",
            "generation_seed",
            "perceptual_required",
            "candidate_repair_requirement",
            "repair_trigger_check_id",
        ):
            if candidate[field] != source[field]:
                raise RuntimeError(
                    "tempo candidate allocation provenance differs from its source"
                )
        eligibility_reason = cls._tempo_source_eligibility_reason_conn(
            conn,
            source,
            require_current_incumbent=False,
        )
        if eligibility_reason is not None:
            raise RuntimeError(
                "tempo candidate source is not eligible: " + eligibility_reason
            )
        source_rate, actual_source_samples = cls._pcm16_mono_wav_shape(
            Path(str(source["wav_path"])),
            "tempo candidate source WAV",
        )
        output_rate, actual_output_samples = cls._pcm16_mono_wav_shape(
            Path(str(candidate["wav_path"])),
            "tempo candidate output WAV",
        )
        if (
            source_rate != source_sample_rate
            or output_rate != source_sample_rate
            or actual_source_samples != source_samples
            or actual_output_samples != output_samples
        ):
            raise RuntimeError("tempo candidate WAV samples differ from its signal provenance")
        if not math.isclose(
            float(source["wav_duration"]),
            source_samples / source_sample_rate,
            rel_tol=0.0,
            abs_tol=2.0 / source_sample_rate,
        ) or not math.isclose(
            float(candidate["wav_duration"]),
            output_samples / source_sample_rate,
            rel_tol=0.0,
            abs_tol=2.0 / source_sample_rate,
        ):
            raise RuntimeError("tempo candidate WAV duration differs from its samples")

    @staticmethod
    def _require_candidate_delivery_provenance(
        candidate: sqlite3.Row,
        signal_provenance: dict[str, Any],
    ) -> None:
        if (
            str(candidate["pronunciation_delivery_variant"])
            != str(signal_provenance["pronunciation_delivery_variant"])
            or str(candidate["expected_spoken_text_sha256"])
            != str(signal_provenance["spoken_text_sha256"])
        ):
            raise RuntimeError(
                "candidate pronunciation variant or spoken-text checksum differs from its allocation"
            )

    @staticmethod
    def _candidate_blocking_signal_flags(signal: dict[str, Any]) -> tuple[str, ...]:
        blocking_flags: list[str] = []
        for field in (
            "pace_outlier",
            "pitch_variant_skipped",
            "pitch_variant_mixed",
            "generation_endpoint_active",
        ):
            value = signal.get(field, False)
            if value not in (False, True, 0, 1, 0.0, 1.0):
                raise RuntimeError(f"candidate signal flag {field} is not boolean")
            if bool(value):
                blocking_flags.append(field)
        return tuple(blocking_flags)

    @staticmethod
    def _candidate_final_metrics(
        candidate: sqlite3.Row,
        beam_metrics: dict[str, Any],
        greedy_metrics: dict[str, Any],
        *,
        warning_code: str | None,
    ) -> dict[str, Any]:
        final_metrics = dict(greedy_metrics)
        final_metrics.update(
            {
                "dual_decode_required": True,
                "dual_decode_passed": True,
                "confirmation_verdicts": [
                    str(beam_metrics.get("verdict", "")),
                    str(greedy_metrics.get("verdict", "")),
                ],
                "beam_quality_check_id": int(candidate["beam_check_id"]),
                "greedy_quality_check_id": int(candidate["greedy_check_id"]),
                "decode_evidence": [beam_metrics, greedy_metrics],
                "pronunciation_delivery_variant": str(
                    candidate["pronunciation_delivery_variant"]
                ),
                "expected_spoken_text_sha256": str(
                    candidate["expected_spoken_text_sha256"]
                ),
                "perceptual_required": bool(candidate["perceptual_required"]),
                "candidate_repair_requirement": str(
                    candidate["candidate_repair_requirement"]
                ),
                "repair_trigger_check_id": (
                    int(candidate["repair_trigger_check_id"])
                    if candidate["repair_trigger_check_id"] is not None
                    else None
                ),
                "perceptual_quality_check_id": (
                    int(candidate["perceptual_check_id"])
                    if candidate["perceptual_check_id"] is not None
                    else None
                ),
                "perceptual_evidence": (
                    ProjectDB._json_object(
                        candidate["perceptual_result_json"],
                        "candidate perceptual metrics",
                    )
                    if candidate["perceptual_result_json"] is not None
                    else None
                ),
                "promotion_warning_code": str(warning_code).strip() if warning_code else None,
            }
        )
        if str(candidate["postprocess_profile"]) == POSTPROCESS_PROFILE_TEMPO:
            final_metrics.update(
                {
                    POSTPROCESS_PROFILE_FIELD: POSTPROCESS_PROFILE_TEMPO,
                    POSTPROCESS_SOURCE_CANDIDATE_ID_FIELD: int(
                        candidate["postprocess_source_candidate_id"]
                    ),
                    POSTPROCESS_SOURCE_SHA256_FIELD: str(
                        candidate["postprocess_source_sha256"]
                    ),
                }
            )
        return final_metrics

    def _validated_promoted_candidate_conn(
        self,
        conn: sqlite3.Connection,
        candidate: sqlite3.Row,
    ) -> sqlite3.Row:
        if str(candidate["state"]) != SEGMENT_CANDIDATE_PROMOTED:
            raise RuntimeError("promoted candidate validation requires promoted state")
        self._candidate_perceptual_requirement_conn(conn, candidate)
        segment = conn.execute(
            "SELECT * FROM segments WHERE id=?",
            (int(candidate["segment_id"]),),
        ).fetchone()
        if segment is None:
            raise KeyError(f"Unknown segment id: {candidate['segment_id']}")
        if (
            str(segment["wav_path"] or "") != str(candidate["wav_path"])
            or str(segment["wav_sha256"] or "").casefold()
            != str(candidate["wav_sha256"] or "").casefold()
        ):
            raise RuntimeError(
                "promoted candidate is not the current segment artifact"
            )
        file_error = self._candidate_file_error(candidate)
        if file_error:
            raise RuntimeError(file_error)
        self._require_candidate_voice_profile_conn(conn, candidate, segment)
        signal = self._json_object(candidate["signal_json"], "candidate signal metrics")
        self._require_candidate_split_provenance(conn, candidate, signal)
        self._require_candidate_vocalization_provenance_conn(
            conn,
            candidate,
            signal,
        )
        signal_provenance = self._candidate_signal_provenance(signal)
        self._require_candidate_delivery_provenance(candidate, signal_provenance)
        self._require_candidate_postprocess_provenance_conn(
            conn,
            candidate,
            signal,
        )
        live_signal = self._json_object(
            segment["signal_json"],
            "promoted live segment signal metrics",
        )
        self._require_vocalization_provenance(
            live_signal,
            required=is_standalone_ha_gasp(str(segment["text"])),
        )
        live_signal_provenance = self._candidate_signal_provenance(live_signal)
        if (
            live_signal_provenance != signal_provenance
            or self._candidate_signal_immutable_projection(live_signal)
            != self._candidate_signal_immutable_projection(signal)
        ):
            raise RuntimeError(
                "promoted candidate immutable signal differs from the live segment"
            )
        blocking_signal_flags = self._candidate_blocking_signal_flags(signal)
        if blocking_signal_flags:
            raise RuntimeError(
                "promoted candidate signal retains blocking TTS flags: "
                + ", ".join(blocking_signal_flags)
            )
        if candidate["beam_check_id"] is None or candidate["greedy_check_id"] is None:
            raise RuntimeError("promoted candidate lacks dual-decode checkpoints")
        beam_check, beam_metrics = self._validated_candidate_decode_check_conn(
            conn,
            candidate,
            int(candidate["beam_check_id"]),
            confirmation=False,
        )
        greedy_check, greedy_metrics = self._validated_candidate_decode_check_conn(
            conn,
            candidate,
            int(candidate["greedy_check_id"]),
            confirmation=True,
        )
        if (
            str(beam_check["verdict"]) != QUALITY_VERDICT_PASS
            or str(greedy_check["verdict"]) != QUALITY_VERDICT_PASS
        ):
            raise RuntimeError(
                "promoted candidate dual-decode ledger is not passing"
            )
        if bool(candidate["perceptual_required"]):
            if candidate["perceptual_check_id"] is None:
                raise RuntimeError(
                    "promoted candidate lacks mandatory perceptual evidence"
                )
            perceptual_check, _perceptual_metrics = (
                self._validated_candidate_perceptual_check_conn(
                    conn,
                    candidate,
                    int(candidate["perceptual_check_id"]),
                )
            )
            if str(perceptual_check["verdict"]) != QUALITY_VERDICT_PASS:
                raise RuntimeError(
                    "promoted candidate perceptual ledger is not passing"
                )
        elif candidate["perceptual_check_id"] is not None:
            raise RuntimeError(
                "promoted candidate has unexpected perceptual evidence"
            )
        if candidate["final_check_id"] is None:
            raise RuntimeError("promoted candidate lacks its final quality checkpoint")
        final_check = conn.execute(
            "SELECT * FROM quality_checks WHERE id=?",
            (int(candidate["final_check_id"]),),
        ).fetchone()
        policy = conn.execute(
            "SELECT * FROM quality_policies WHERE policy_hash=?",
            (str(candidate["policy_hash"]),),
        ).fetchone()
        if final_check is None or policy is None:
            raise RuntimeError("promoted candidate final policy evidence is missing")
        require_all(
            "promoted candidate final quality checkpoint is not exact",
            ("scope", str(final_check["scope"]) != QUALITY_SCOPE_SEGMENT),
            ("stage", str(final_check["stage"]) != SEGMENT_AUDIO_QUALITY_STAGE),
            ("segment_id",
             int(final_check["segment_id"] or -1) != int(candidate["segment_id"])),
            ("chapter_id", final_check["chapter_id"] is not None),
            ("artifact_sha256", str(final_check["artifact_sha256"]).casefold()
             != str(candidate["wav_sha256"]).casefold()),
            ("policy_hash",
             str(final_check["policy_hash"]) != str(candidate["policy_hash"])),
            ("policy_version",
             int(final_check["policy_version"]) != int(policy["policy_version"])),
            ("verdict", str(final_check["verdict"]) != QUALITY_VERDICT_PASS),
            ("failure_codes", str(final_check["failure_codes_json"]) != "[]"),
            ("attempt", int(final_check["attempt"]) < 1),
            candidate_id=int(candidate["id"]),
            quality_check_id=int(final_check["id"]),
            verdict=str(final_check["verdict"]),
            failure_codes=str(final_check["failure_codes_json"]),
        )
        final_metrics = self._json_object(
            final_check["metrics_json"],
            "promoted candidate final metrics",
        )
        warning_code = final_metrics.get("promotion_warning_code")
        normalized_warning_code = (
            str(warning_code).strip() if warning_code else None
        )
        if normalized_warning_code and normalized_warning_code not in {
            code
            for code in str(segment["warning_code"] or "").split("|")
            if code
        }:
            raise RuntimeError(
                "promoted candidate warning provenance differs from the live segment"
            )
        expected_final_metrics = self._candidate_final_metrics(
            candidate,
            beam_metrics,
            greedy_metrics,
            warning_code=normalized_warning_code,
        )
        if str(final_check["metrics_json"]) != json.dumps(
            expected_final_metrics,
            ensure_ascii=False,
            sort_keys=True,
        ):
            raise RuntimeError(
                "promoted candidate final metrics differ from rebuilt evidence"
            )
        return segment

    @staticmethod
    def _candidate_row_conn(conn: sqlite3.Connection, candidate_id: int) -> sqlite3.Row:
        row = conn.execute(
            "SELECT * FROM segment_candidates WHERE id=?",
            (int(candidate_id),),
        ).fetchone()
        if row is None:
            raise KeyError(f"Unknown segment candidate id: {candidate_id}")
        return row

    @staticmethod
    def _require_candidate_policy_conn(
        conn: sqlite3.Connection,
        policy_hash: str,
        *,
        active: bool = True,
    ) -> sqlite3.Row:
        normalized_hash = str(policy_hash or "").strip()
        row = conn.execute(
            "SELECT * FROM quality_policies WHERE policy_hash=?",
            (normalized_hash,),
        ).fetchone()
        if row is None:
            raise ValueError("segment candidate quality policy is not registered")
        if active and not bool(row["active"]):
            raise RuntimeError("segment candidate quality policy is no longer active")
        return row

    @staticmethod
    def _require_candidate_incumbent_conn(
        conn: sqlite3.Connection,
        candidate: sqlite3.Row,
    ) -> sqlite3.Row:
        segment = conn.execute(
            "SELECT * FROM segments WHERE id=?",
            (int(candidate["segment_id"]),),
        ).fetchone()
        if segment is None:
            raise KeyError(f"Unknown segment id: {candidate['segment_id']}")
        if str(segment["wav_sha256"] or "").casefold() != str(candidate["incumbent_sha256"]):
            raise RuntimeError("segment candidate incumbent checksum changed")
        return segment

    @staticmethod
    def _expected_segment_voice_profile_conn(
        conn: sqlite3.Connection,
        segment: sqlite3.Row,
    ) -> sqlite3.Row:
        if str(segment["kind"] or "").strip().casefold() == "thought":
            profile = conn.execute(
                "SELECT * FROM voice_profiles WHERE voice_key=? COLLATE NOCASE",
                ("narrator",),
            ).fetchone()
            if profile is None:
                raise RuntimeError("thought candidate requires the locked narrator voice profile")
        else:
            if segment["voice_profile_id"] is None:
                raise RuntimeError("segment candidate requires an assigned locked voice profile")
            profile = conn.execute(
                "SELECT * FROM voice_profiles WHERE id=?",
                (int(segment["voice_profile_id"]),),
            ).fetchone()
            if profile is None:
                raise RuntimeError("segment candidate voice profile does not exist")
        if not bool(profile["locked"]):
            raise RuntimeError("segment candidate voice profile is not locked")
        return profile

    @classmethod
    def _require_candidate_voice_profile_conn(
        cls,
        conn: sqlite3.Connection,
        candidate: sqlite3.Row,
        segment: sqlite3.Row,
    ) -> sqlite3.Row:
        profile = cls._expected_segment_voice_profile_conn(conn, segment)
        if (
            int(candidate["expected_voice_profile_id"]) != int(profile["id"])
            or int(candidate["expected_pitch_semitones"])
            != int(profile["pitch_semitones"] or 0)
        ):
            raise RuntimeError("segment candidate voice casting changed after allocation")
        return profile

    @staticmethod
    def _candidate_file_error(candidate: sqlite3.Row) -> str | None:
        wav_path = Path(str(candidate["wav_path"] or ""))
        wav_sha256 = str(candidate["wav_sha256"] or "").strip().casefold()
        if not wav_sha256:
            return "candidate WAV checksum is missing"
        if not wav_path.is_file():
            return "candidate WAV is missing"
        try:
            if sha256_file(wav_path) != wav_sha256:
                return "candidate WAV checksum does not match its immutable checkpoint"
        except OSError as exc:
            return f"candidate WAV could not be read: {exc}"
        return None

    @staticmethod
    def _invalidate_candidate_conn(
        conn: sqlite3.Connection,
        candidate: sqlite3.Row,
        reason: str,
    ) -> sqlite3.Row:
        if str(candidate["state"]) == SEGMENT_CANDIDATE_PROMOTED:
            raise RuntimeError("a promoted segment candidate cannot be invalidated")
        conn.execute(
            """
            UPDATE segment_candidates SET state=?,failure_reason=?,updated_at=?
            WHERE id=? AND state=?
            """,
            (
                SEGMENT_CANDIDATE_INVALID,
                str(reason)[-8000:],
                time.time(),
                int(candidate["id"]),
                str(candidate["state"]),
            ),
        )
        return ProjectDB._candidate_row_conn(conn, int(candidate["id"]))

    @staticmethod
    def _candidate_summary(row: sqlite3.Row) -> dict[str, Any]:
        def decoded_result(field: str) -> dict[str, Any] | None:
            value = row[field]
            if value is None:
                return None
            try:
                decoded = json.loads(str(value))
            except (TypeError, json.JSONDecodeError):
                return {"invalid_json": True}
            return decoded if isinstance(decoded, dict) else {"invalid_json": True}

        return {
            "candidate_id": int(row["id"]),
            "repair_round": int(row["repair_round"]),
            "repair_budget": int(row["repair_budget"]),
            "state": str(row["state"]),
            "generation_strategy": str(row["generation_strategy"]),
            POSTPROCESS_PROFILE_FIELD: str(row["postprocess_profile"]),
            POSTPROCESS_SOURCE_CANDIDATE_ID_FIELD: (
                int(row["postprocess_source_candidate_id"])
                if row["postprocess_source_candidate_id"] is not None
                else None
            ),
            POSTPROCESS_SOURCE_SHA256_FIELD: (
                str(row["postprocess_source_sha256"])
                if row["postprocess_source_sha256"] is not None
                else None
            ),
            "incumbent_sha256": str(row["incumbent_sha256"]),
            "expected_voice_profile_id": int(row["expected_voice_profile_id"]),
            "expected_pitch_semitones": int(row["expected_pitch_semitones"]),
            "pronunciation_delivery_variant": str(
                row["pronunciation_delivery_variant"]
            ),
            "expected_spoken_text_sha256": str(row["expected_spoken_text_sha256"]),
            "wav_path": str(row["wav_path"]),
            "wav_sha256": str(row["wav_sha256"] or ""),
            "wav_duration": (
                float(row["wav_duration"]) if row["wav_duration"] is not None else None
            ),
            "generation_seed": int(row["generation_seed"]),
            "tts_attempt": int(row["tts_attempt"]),
            "beam_check_id": int(row["beam_check_id"]) if row["beam_check_id"] is not None else None,
            "greedy_check_id": (
                int(row["greedy_check_id"]) if row["greedy_check_id"] is not None else None
            ),
            "perceptual_required": bool(row["perceptual_required"]),
            "candidate_repair_requirement": str(
                row["candidate_repair_requirement"]
            ),
            "repair_trigger_check_id": (
                int(row["repair_trigger_check_id"])
                if row["repair_trigger_check_id"] is not None
                else None
            ),
            "perceptual_check_id": (
                int(row["perceptual_check_id"])
                if row["perceptual_check_id"] is not None
                else None
            ),
            "final_check_id": (
                int(row["final_check_id"]) if row["final_check_id"] is not None else None
            ),
            "signal": decoded_result("signal_json"),
            "beam_result": decoded_result("beam_result_json"),
            "greedy_result": decoded_result("greedy_result_json"),
            "perceptual_result": decoded_result("perceptual_result_json"),
            "failure_reason": str(row["failure_reason"] or ""),
            "promoted_at": (
                float(row["promoted_at"]) if row["promoted_at"] is not None else None
            ),
        }

    def allocate_segment_candidate(
        self,
        *,
        segment_id: int,
        policy_hash: str,
        repair_round: int,
        max_repair_rounds: int,
        incumbent_sha256: str,
        generation_seed: int,
        wav_path: Path,
        candidates_root: Path,
        pronunciation_delivery_variant: str = PRONUNCIATION_DELIVERY_LOCKED,
        expected_spoken_text_sha256: str | None = None,
        tts_attempt: int = 0,
        generation_strategy: str = GENERATION_STRATEGY_DIRECT,
        postprocess_profile: str = POSTPROCESS_PROFILE_NONE,
        postprocess_source_candidate_id: int | None = None,
        postprocess_source_sha256: str | None = None,
        perceptual_required: bool = False,
        candidate_repair_requirement: str = STANDARD_CANDIDATE_GATE_REQUIREMENT,
        repair_trigger_check_id: int | None = None,
    ) -> sqlite3.Row:
        normalized_round = int(repair_round)
        normalized_max = int(max_repair_rounds)
        normalized_attempt = int(tts_attempt)
        normalized_generation_strategy = self._normalized_generation_strategy(
            generation_strategy
        )
        normalized_postprocess_profile = self._normalized_postprocess_profile(
            postprocess_profile
        )
        normalized_postprocess_source_candidate_id = (
            int(postprocess_source_candidate_id)
            if postprocess_source_candidate_id is not None
            else None
        )
        normalized_postprocess_source_sha256 = (
            self._normalized_sha256(
                postprocess_source_sha256,
                "segment candidate postprocess source checksum",
            )
            if postprocess_source_sha256 is not None
            else None
        )
        normalized_perceptual_required = bool(perceptual_required)
        normalized_incumbent = self._normalized_sha256(
            incumbent_sha256,
            "segment candidate incumbent checksum",
        )
        normalized_pronunciation_variant = (
            self._normalized_pronunciation_delivery_variant(
                pronunciation_delivery_variant
            )
        )
        normalized_repair_requirement = (
            self._normalized_candidate_repair_requirement(
                candidate_repair_requirement
            )
        )
        normalized_repair_trigger_check_id = (
            int(repair_trigger_check_id)
            if repair_trigger_check_id is not None
            else None
        )
        normalized_expected_spoken_sha256 = (
            self._normalized_sha256(
                expected_spoken_text_sha256,
                "segment candidate expected spoken-text checksum",
            )
            if expected_spoken_text_sha256 is not None
            else None
        )
        normalized_path = str(wav_path.resolve())
        normalized_candidates_root = str(candidates_root.resolve())
        path_key = normalized_path.casefold()
        root_prefix = normalized_candidates_root.rstrip("\\/").casefold() + os.sep.casefold()
        if not path_key.startswith(root_prefix):
            raise ValueError("segment candidate WAV path must be under the dedicated candidates root")
        if normalized_max < 0:
            raise ValueError("ASR repair budget must be non-negative")
        if normalized_round < 0:
            raise ValueError("segment candidate repair round must be non-negative")
        if normalized_postprocess_profile == POSTPROCESS_PROFILE_NONE:
            if (
                normalized_postprocess_source_candidate_id is not None
                or normalized_postprocess_source_sha256 is not None
            ):
                raise ValueError(
                    "identity segment candidates cannot bind a postprocess source"
                )
            if normalized_round >= normalized_max:
                raise ValueError(
                    "segment candidate repair round exceeds the same-policy budget"
                )
        else:
            if (
                normalized_postprocess_source_candidate_id is None
                or normalized_postprocess_source_sha256 is None
            ):
                raise ValueError("tempo segment candidates require a source binding")
            if normalized_round != normalized_max:
                raise ValueError(
                    "tempo segment candidate must follow the exhausted ordinary budget"
                )
        if normalized_attempt < 0:
            raise ValueError("segment candidate TTS attempt must be non-negative")
        if (
            normalized_repair_trigger_check_id is not None
            and normalized_repair_trigger_check_id < 1
        ):
            raise ValueError("segment candidate repair trigger check id must be positive")
        if normalized_repair_requirement == STANDARD_CANDIDATE_GATE_REQUIREMENT:
            if normalized_repair_trigger_check_id is not None:
                raise ValueError(
                    "standard segment candidates cannot bind a naturalness trigger"
                )
        elif normalized_repair_trigger_check_id is None:
            raise ValueError(
                "naturalness-repair candidates require an exact trigger check id"
            )
        if (
            normalized_repair_requirement == NATURALNESS_IMPROVEMENT_REQUIREMENT
            and not normalized_perceptual_required
        ):
            raise ValueError(
                "naturalness-repair candidates require mandatory perceptual QA"
            )

        now = time.time()
        with self.transaction() as conn:
            self._require_candidate_policy_conn(conn, policy_hash)
            policy_perceptual_required = self._policy_perceptual_required_conn(
                conn,
                policy_hash,
            )
            if (
                policy_perceptual_required is not None
                and normalized_perceptual_required != policy_perceptual_required
            ):
                raise RuntimeError(
                    "segment candidate perceptual requirement differs from its "
                    "locked quality policy"
                )
            segment = conn.execute(
                "SELECT * FROM segments WHERE id=?",
                (int(segment_id),),
            ).fetchone()
            if segment is None:
                raise KeyError(f"Unknown segment id: {segment_id}")
            if str(segment["wav_sha256"] or "").casefold() != normalized_incumbent:
                raise RuntimeError("cannot allocate a candidate for a stale incumbent artifact")
            if normalized_expected_spoken_sha256 is None:
                incumbent_signal = self._json_object(
                    segment["signal_json"],
                    "segment candidate incumbent signal metrics",
                )
                normalized_expected_spoken_sha256 = self._normalized_sha256(
                    str(incumbent_signal.get("spoken_text_sha256", "")),
                    "segment candidate expected spoken-text checksum",
                )
            expected_profile = self._expected_segment_voice_profile_conn(conn, segment)
            expected_voice_profile_id = int(expected_profile["id"])
            expected_pitch_semitones = int(expected_profile["pitch_semitones"] or 0)

            rows = list(
                conn.execute(
                    """
                    SELECT * FROM segment_candidates
                    WHERE segment_id=? AND policy_hash=?
                    ORDER BY repair_round
                    """,
                    (int(segment_id), str(policy_hash).strip()),
                )
            )
            if normalized_repair_requirement == NATURALNESS_IMPROVEMENT_REQUIREMENT:
                self._validated_naturalness_repair_trigger_conn(
                    conn,
                    segment_id=int(segment_id),
                    incumbent_sha256=normalized_incumbent,
                    policy_hash=str(policy_hash).strip(),
                    quality_check_id=int(normalized_repair_trigger_check_id),
                )
            else:
                self._require_no_unbound_naturalness_trigger_conn(
                    conn,
                    segment_id=int(segment_id),
                    incumbent_sha256=normalized_incumbent,
                    policy_hash=str(policy_hash).strip(),
                )
            existing = next(
                (row for row in rows if int(row["repair_round"]) == normalized_round),
                None,
            )
            if existing is not None:
                # Sixteen conditions used to share one message and the row is not written
                # anywhere a reader can inspect, so a mismatch here meant rerunning to learn
                # which field moved. See require_all.
                require_all(
                    "candidate resume metadata differs from its durable checkpoint",
                    ("incumbent_sha256", str(existing["incumbent_sha256"]) != normalized_incumbent),
                    ("voice_profile_id", int(existing["expected_voice_profile_id"]) != expected_voice_profile_id),
                    ("pitch_semitones", int(existing["expected_pitch_semitones"]) != expected_pitch_semitones),
                    ("pronunciation_variant", str(existing["pronunciation_delivery_variant"])
                     != normalized_pronunciation_variant),
                    ("spoken_text_sha256", str(existing["expected_spoken_text_sha256"])
                     != normalized_expected_spoken_sha256),
                    ("repair_budget", int(existing["repair_budget"]) != normalized_max),
                    ("generation_strategy", str(existing["generation_strategy"]) != normalized_generation_strategy),
                    ("postprocess_profile", str(existing["postprocess_profile"]) != normalized_postprocess_profile),
                    ("postprocess_source_candidate_id", (
                         int(existing["postprocess_source_candidate_id"])
                         if existing["postprocess_source_candidate_id"] is not None
                         else None
                     )
                     != normalized_postprocess_source_candidate_id),
                    ("postprocess_source_sha256", (
                         str(existing["postprocess_source_sha256"])
                         if existing["postprocess_source_sha256"] is not None
                         else None
                     )
                     != normalized_postprocess_source_sha256),
                    ("perceptual_required", bool(existing["perceptual_required"]) != normalized_perceptual_required),
                    ("repair_requirement", str(existing["candidate_repair_requirement"])
                     != normalized_repair_requirement),
                    ("repair_trigger_check_id", (
                         int(existing["repair_trigger_check_id"])
                         if existing["repair_trigger_check_id"] is not None
                         else None
                     )
                     != normalized_repair_trigger_check_id),
                    ("generation_seed", int(existing["generation_seed"]) != int(generation_seed)),
                    ("tts_attempt", int(existing["tts_attempt"]) != normalized_attempt),
                    ("wav_path", str(existing["wav_path"]) != normalized_path),
                    candidate_id=int(existing["id"]),
                    repair_round=normalized_round,
                )
                return existing

            ordinary_rows = [
                row
                for row in rows
                if str(row["postprocess_profile"]) == POSTPROCESS_PROFILE_NONE
            ]
            tempo_rows = [
                row
                for row in rows
                if str(row["postprocess_profile"]) == POSTPROCESS_PROFILE_TEMPO
            ]
            if len(ordinary_rows) + len(tempo_rows) != len(rows):
                raise RuntimeError("stored candidate has an unsupported postprocess profile")
            ordinary_rounds = [int(row["repair_round"]) for row in ordinary_rows]
            if any(round_index >= normalized_max for round_index in ordinary_rounds):
                raise RuntimeError("stored ordinary candidate rounds exceed the supplied budget")
            if ordinary_rounds != list(range(len(ordinary_rows))):
                raise RuntimeError("stored ordinary candidate rounds are not contiguous")
            if len(tempo_rows) > 1 or any(
                int(row["repair_round"]) != normalized_max for row in tempo_rows
            ):
                raise RuntimeError("stored tempo candidate round is invalid")
            if any(str(row["incumbent_sha256"]) != normalized_incumbent for row in rows):
                raise RuntimeError("same-policy candidate rounds cannot mix incumbent artifacts")
            if any(int(row["repair_budget"]) != normalized_max for row in rows):
                raise RuntimeError("same-policy candidate rounds cannot mix repair budgets")
            if any(
                bool(row["perceptual_required"])
                != normalized_perceptual_required
                for row in rows
            ):
                raise RuntimeError("same-policy candidate rounds cannot mix perceptual requirements")
            if any(
                str(row["candidate_repair_requirement"])
                != normalized_repair_requirement
                or (
                    int(row["repair_trigger_check_id"])
                    if row["repair_trigger_check_id"] is not None
                    else None
                )
                != normalized_repair_trigger_check_id
                for row in rows
            ):
                raise RuntimeError(
                    "same-policy candidate rounds cannot mix repair trigger bindings"
                )
            if normalized_postprocess_profile == POSTPROCESS_PROFILE_NONE:
                if tempo_rows:
                    raise RuntimeError(
                        "ordinary candidate allocation cannot follow a tempo candidate"
                    )
                if ordinary_rounds != list(range(normalized_round)):
                    raise RuntimeError(
                        "candidate rounds must be contiguous and allocated in order"
                    )
                if any(
                    str(row["state"]) not in SEGMENT_CANDIDATE_FAILURE_STATES
                    for row in ordinary_rows
                ):
                    raise RuntimeError(
                        "the previous candidate round is not a terminal failure"
                    )
            else:
                if tempo_rows:
                    raise RuntimeError("tempo candidate allocation is already checkpointed")
                if ordinary_rounds != list(range(normalized_max)):
                    raise RuntimeError(
                        "tempo candidate requires every ordinary repair round"
                    )
                if any(
                    str(row["state"]) not in SEGMENT_CANDIDATE_FAILURE_STATES
                    for row in ordinary_rows
                ):
                    raise RuntimeError(
                        "tempo candidate requires terminal ordinary repair rounds"
                    )
                source = self._candidate_row_conn(
                    conn,
                    int(normalized_postprocess_source_candidate_id),
                )
                if not any(
                    int(row["id"]) == int(source["id"]) for row in ordinary_rows
                ):
                    raise RuntimeError(
                        "tempo candidate source is not in the ordinary repair ledger"
                    )
                if (
                    str(source["wav_sha256"] or "").casefold()
                    != normalized_postprocess_source_sha256
                ):
                    raise RuntimeError(
                        "tempo candidate source checksum differs from its durable artifact"
                    )
                require_all(
                    "tempo candidate allocation differs from its source provenance",
                    ("voice_profile_id", int(source["expected_voice_profile_id"])
                     != expected_voice_profile_id),
                    ("pitch_semitones", int(source["expected_pitch_semitones"])
                     != expected_pitch_semitones),
                    ("pronunciation_variant",
                     str(source["pronunciation_delivery_variant"])
                     != normalized_pronunciation_variant),
                    ("spoken_text_sha256",
                     str(source["expected_spoken_text_sha256"])
                     != normalized_expected_spoken_sha256),
                    ("generation_strategy", str(source["generation_strategy"])
                     != normalized_generation_strategy),
                    ("generation_seed",
                     int(source["generation_seed"]) != int(generation_seed)),
                    ("tts_attempt", int(source["tts_attempt"]) != normalized_attempt),
                    ("perceptual_required", bool(source["perceptual_required"])
                     != normalized_perceptual_required),
                    ("repair_requirement",
                     str(source["candidate_repair_requirement"])
                     != normalized_repair_requirement),
                    ("repair_trigger_check_id", (
                        int(source["repair_trigger_check_id"])
                        if source["repair_trigger_check_id"] is not None
                        else None
                    ) != normalized_repair_trigger_check_id),
                    source_candidate_id=int(source["id"]),
                    generation_seed=int(generation_seed),
                    tts_attempt=normalized_attempt,
                )
                eligibility_reason = self._tempo_source_eligibility_reason_conn(
                    conn,
                    source,
                )
                if eligibility_reason is not None:
                    raise RuntimeError(
                        "tempo candidate source is not eligible: " + eligibility_reason
                    )
            occupied_paths = [
                str(row[0])
                for row in conn.execute(
                    """
                    SELECT wav_path FROM segments WHERE wav_path IS NOT NULL
                    UNION ALL
                    SELECT wav_path FROM segment_candidates
                    """
                )
            ]
            if any(path.casefold() == path_key for path in occupied_paths):
                raise RuntimeError("segment candidate WAV path collides with an immutable audio artifact")

            try:
                cursor = conn.execute(
                    """
                    INSERT INTO segment_candidates(
                        segment_id,policy_hash,repair_round,repair_budget,incumbent_sha256,
                        expected_voice_profile_id,expected_pitch_semitones,
                        pronunciation_delivery_variant,expected_spoken_text_sha256,state,
                        generation_strategy,postprocess_profile,
                        postprocess_source_candidate_id,postprocess_source_sha256,
                        tts_attempt,generation_seed,wav_path,
                        perceptual_required,
                        candidate_repair_requirement,repair_trigger_check_id,
                        created_at,updated_at
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        int(segment_id),
                        str(policy_hash).strip(),
                        normalized_round,
                        normalized_max,
                        normalized_incumbent,
                        expected_voice_profile_id,
                        expected_pitch_semitones,
                        normalized_pronunciation_variant,
                        normalized_expected_spoken_sha256,
                        SEGMENT_CANDIDATE_GENERATING,
                        normalized_generation_strategy,
                        normalized_postprocess_profile,
                        normalized_postprocess_source_candidate_id,
                        normalized_postprocess_source_sha256,
                        normalized_attempt,
                        int(generation_seed),
                        normalized_path,
                        int(normalized_perceptual_required),
                        normalized_repair_requirement,
                        normalized_repair_trigger_check_id,
                        now,
                        now,
                    ),
                )
            except sqlite3.IntegrityError as exc:
                raise RuntimeError("segment candidate allocation conflicts with durable metadata") from exc
            return self._candidate_row_conn(conn, int(cursor.lastrowid))

    def restart_segment_candidate_generation(
        self,
        candidate_id: int,
        *,
        expected_generation_seed: int,
        generation_seed: int,
        tts_attempt: int,
        generation_strategy: str | None = None,
    ) -> sqlite3.Row:
        normalized_attempt = int(tts_attempt)
        with self.transaction() as conn:
            candidate = self._candidate_row_conn(conn, candidate_id)
            self._require_candidate_policy_conn(conn, str(candidate["policy_hash"]))
            segment = self._require_candidate_incumbent_conn(conn, candidate)
            self._require_candidate_voice_profile_conn(conn, candidate, segment)
            if str(candidate["state"]) != SEGMENT_CANDIDATE_GENERATING:
                raise RuntimeError("only an uncommitted generating candidate can restart TTS")
            if str(candidate["postprocess_profile"]) != POSTPROCESS_PROFILE_NONE:
                raise RuntimeError("tempo candidate generation cannot restart TTS")
            current_attempt = int(candidate["tts_attempt"])
            current_generation_strategy = self._normalized_generation_strategy(
                str(candidate["generation_strategy"])
            )
            normalized_generation_strategy = (
                current_generation_strategy
                if generation_strategy is None
                else self._normalized_generation_strategy(generation_strategy)
            )
            if (
                normalized_attempt == current_attempt
                and int(generation_seed) == int(candidate["generation_seed"])
                and normalized_generation_strategy == current_generation_strategy
            ):
                return candidate
            if int(candidate["generation_seed"]) != int(expected_generation_seed):
                raise RuntimeError("segment candidate generation seed CAS failed")
            if normalized_attempt != current_attempt + 1:
                raise RuntimeError("segment candidate TTS attempts must advance exactly once")
            if (
                normalized_generation_strategy != current_generation_strategy
                and not (
                    current_generation_strategy == GENERATION_STRATEGY_DIRECT
                    and normalized_generation_strategy == GENERATION_STRATEGY_SPLIT
                )
            ):
                raise RuntimeError(
                    "segment candidate generation strategy can only advance from direct to split"
                )
            conn.execute(
                """
                UPDATE segment_candidates
                SET generation_strategy=?,tts_attempt=?,generation_seed=?,updated_at=?
                WHERE id=? AND state=? AND generation_seed=? AND generation_strategy=?
                """,
                (
                    normalized_generation_strategy,
                    normalized_attempt,
                    int(generation_seed),
                    time.time(),
                    int(candidate_id),
                    SEGMENT_CANDIDATE_GENERATING,
                    int(expected_generation_seed),
                    current_generation_strategy,
                ),
            )
            return self._candidate_row_conn(conn, candidate_id)

    def checkpoint_segment_candidate_signal(
        self,
        candidate_id: int,
        *,
        expected_generation_seed: int,
        wav_path: Path,
        wav_sha256: str,
        duration: float,
        signal: dict[str, Any],
    ) -> sqlite3.Row:
        normalized_path = str(wav_path.resolve())
        normalized_sha256 = self._normalized_sha256(
            wav_sha256,
            "segment candidate WAV checksum",
        )
        normalized_duration = float(duration)
        if normalized_duration <= 0:
            raise ValueError("segment candidate WAV duration must be positive")
        if not isinstance(signal, dict):
            raise ValueError("segment candidate signal checkpoint must be a dictionary")
        if str(signal.get("tts_delivery_mode", "")).strip().casefold() != GENERATION_DELIVERY_CLARITY:
            raise ValueError("segment candidate signal must use clarity delivery")
        try:
            signal_round = int(signal["asr_clarity_repair_round"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("segment candidate signal lacks its clarity repair round") from exc
        signal_provenance = self._candidate_signal_provenance(signal)
        signal_json = json.dumps(signal, ensure_ascii=False, sort_keys=True)
        wav_file = Path(normalized_path)
        if not wav_file.is_file():
            raise RuntimeError("segment candidate WAV is missing before its signal checkpoint")
        if sha256_file(wav_file) != normalized_sha256:
            raise RuntimeError("segment candidate WAV checksum differs before its signal checkpoint")

        with self.transaction() as conn:
            candidate = self._candidate_row_conn(conn, candidate_id)
            self._require_candidate_policy_conn(conn, str(candidate["policy_hash"]))
            segment = self._require_candidate_incumbent_conn(conn, candidate)
            self._require_candidate_voice_profile_conn(conn, candidate, segment)
            self._require_candidate_delivery_provenance(
                candidate,
                signal_provenance,
            )
            self._require_candidate_split_provenance(conn, candidate, signal)
            self._require_candidate_vocalization_provenance_conn(
                conn,
                candidate,
                signal,
            )
            if (
                signal_provenance["voice_profile_id"]
                != int(candidate["expected_voice_profile_id"])
                or signal_provenance["pitch_semitones"]
                != int(candidate["expected_pitch_semitones"])
            ):
                raise ValueError("candidate signal voice provenance differs from locked casting")
            if (
                not signal_provenance["pitch_variant_skipped"]
                and not signal_provenance["pitch_variant_mixed"]
                and signal_provenance["effective_pitch_semitones"]
                != int(candidate["expected_pitch_semitones"])
            ):
                raise ValueError("candidate signal effective pitch differs from locked casting")
            if int(candidate["repair_round"]) != signal_round:
                raise ValueError("segment candidate signal repair round does not match its ledger row")
            if int(candidate["generation_seed"]) != int(expected_generation_seed):
                raise RuntimeError("segment candidate generation seed CAS failed")
            if str(candidate["wav_path"]) != normalized_path:
                raise RuntimeError("segment candidate WAV path differs from its allocation")
            state = str(candidate["state"])
            if state != SEGMENT_CANDIDATE_GENERATING:
                if (
                    state in SEGMENT_CANDIDATE_STATES - {SEGMENT_CANDIDATE_GENERATING}
                    and str(candidate["wav_sha256"] or "") == normalized_sha256
                    and float(candidate["wav_duration"] or 0.0) == normalized_duration
                    and str(candidate["signal_json"] or "") == signal_json
                ):
                    self._require_candidate_postprocess_provenance_conn(
                        conn,
                        candidate,
                        signal,
                    )
                    return candidate
                raise RuntimeError("segment candidate signal checkpoint transition CAS failed")
            conn.execute(
                """
                UPDATE segment_candidates
                SET state=?,wav_sha256=?,wav_duration=?,signal_json=?,updated_at=?
                WHERE id=? AND state=? AND generation_seed=?
                """,
                (
                    SEGMENT_CANDIDATE_SIGNAL_PASSED,
                    normalized_sha256,
                    normalized_duration,
                    signal_json,
                    time.time(),
                    int(candidate_id),
                    SEGMENT_CANDIDATE_GENERATING,
                    int(expected_generation_seed),
                ),
            )
            checkpointed = self._candidate_row_conn(conn, candidate_id)
            self._require_candidate_postprocess_provenance_conn(
                conn,
                checkpointed,
                signal,
            )
            return checkpointed

    @classmethod
    def _validated_candidate_decode_check_conn(
        cls,
        conn: sqlite3.Connection,
        candidate: sqlite3.Row,
        quality_check_id: int,
        *,
        confirmation: bool,
    ) -> tuple[sqlite3.Row, dict[str, Any]]:
        check = conn.execute(
            "SELECT * FROM quality_checks WHERE id=?",
            (int(quality_check_id),),
        ).fetchone()
        if check is None:
            raise KeyError(f"Unknown quality check id: {quality_check_id}")
        if (
            str(check["scope"]) != QUALITY_SCOPE_SEGMENT
            or str(check["stage"]) != SEGMENT_ASR_DECODE_QUALITY_STAGE
            or int(check["segment_id"] or -1) != int(candidate["segment_id"])
            or str(check["artifact_sha256"]).casefold() != str(candidate["wav_sha256"])
            or str(check["policy_hash"]) != str(candidate["policy_hash"])
        ):
            raise RuntimeError("ASR decode evidence does not belong to this segment candidate")
        metrics = cls._json_object(check["metrics_json"], "candidate ASR decode metrics")
        decode_mode = str(metrics.get("decode_mode", "")).strip().casefold()
        expected_mode = decode_mode == "greedy" if confirmation else decode_mode.startswith("beam")
        if not expected_mode or not bool(metrics.get("selected", False)):
            raise RuntimeError("candidate ASR checkpoint must reference the selected decode evidence")
        if (
            str(metrics.get("delivery_mode", "")).strip().casefold() != GENERATION_DELIVERY_CLARITY
            or int(metrics.get("repair_round", -1)) != int(candidate["repair_round"])
            or int(metrics.get("generation_seed", -1)) != int(candidate["generation_seed"])
        ):
            raise RuntimeError("candidate ASR decode provenance differs from its generation checkpoint")
        signal = cls._json_object(candidate["signal_json"], "candidate signal metrics")
        cls._require_candidate_split_provenance(conn, candidate, signal)
        cls._require_candidate_vocalization_provenance_conn(
            conn,
            candidate,
            signal,
        )
        signal_provenance = cls._candidate_signal_provenance(signal)
        cls._require_candidate_delivery_provenance(candidate, signal_provenance)
        cls._require_candidate_postprocess_provenance_conn(
            conn,
            candidate,
            signal,
        )
        try:
            decode_provenance = cls._candidate_signal_provenance(metrics)
        except ValueError as exc:
            raise RuntimeError("candidate ASR decode lacks locked voice or pitch provenance") from exc
        if decode_provenance != signal_provenance:
            raise RuntimeError("candidate ASR locked provenance differs from its signal checkpoint")
        if cls._candidate_signal_immutable_projection(
            metrics
        ) != cls._candidate_signal_immutable_projection(signal):
            raise RuntimeError(
                "candidate ASR immutable signal provenance differs from its checkpoint"
            )
        if check["verdict"] not in {QUALITY_VERDICT_PASS, "fail", "inconclusive"}:
            raise RuntimeError("candidate ASR decode evidence has an unsupported verdict")
        evidence_verdict = str(check["verdict"])
        metrics_verdict = str(metrics.get("verdict", "")).strip().casefold()
        metrics_passed = metrics.get("passed")
        verdict_consistent = (
            evidence_verdict == QUALITY_VERDICT_PASS
            and metrics_verdict == QUALITY_VERDICT_PASS
            and metrics_passed is True
        ) or (
            evidence_verdict == "fail"
            and metrics_verdict == "mismatch"
            and metrics_passed is False
        ) or (
            evidence_verdict == "inconclusive"
            and metrics_verdict == "inconclusive"
            and metrics_passed is False
        )
        if not verdict_consistent:
            raise RuntimeError("candidate ASR quality-check verdict contradicts its metrics")
        context_mode = str(metrics.get("context_mode") or "")
        requested_repeat_count = metrics.get("requested_repeat_count")
        effective_repeat_count = metrics.get("effective_repeat_count")
        collapsed_count_fields_present = (
            requested_repeat_count is not None or effective_repeat_count is not None
        )
        if context_mode == COLLAPSED_SHORT_CONTEXT_MODE:
            anchor_metrics = metrics.get("locked_name_anchor_metrics")
            if (
                evidence_verdict != QUALITY_VERDICT_PASS
                or isinstance(requested_repeat_count, bool)
                or requested_repeat_count != SHORT_CONTEXT_REPEAT_COUNT
                or isinstance(effective_repeat_count, bool)
                or effective_repeat_count
                != COLLAPSED_SHORT_CONTEXT_EFFECTIVE_REPEAT_COUNT
                or not isinstance(anchor_metrics, dict)
            ):
                raise RuntimeError(
                    "collapsed repeated-short candidate evidence violates its context contract"
                )
            count_fields = (
                "repeat_count",
                "anchor_count",
                "required_occurrence_count",
                "matched_occurrence_count",
                "requested_repeat_count",
                "effective_repeat_count",
            )
            if any(
                isinstance(anchor_metrics.get(field), bool)
                or not isinstance(anchor_metrics.get(field), int)
                for field in count_fields
            ):
                raise RuntimeError(
                    "collapsed repeated-short anchor counts are malformed"
                )
            anchor_count = int(anchor_metrics["anchor_count"])
            required_count = int(anchor_metrics["required_occurrence_count"])
            collapsed_anchor_evidence_is_valid = (
                anchor_metrics.get("version")
                == LOCKED_NAME_ANCHOR_METRICS_VERSION
                and anchor_metrics.get("adjudicated") is True
                and anchor_metrics.get("passed") is True
                and str(anchor_metrics.get("status") or "") == "pass"
                and anchor_metrics.get("failure_codes") == []
                and int(anchor_metrics["repeat_count"])
                == COLLAPSED_SHORT_CONTEXT_EFFECTIVE_REPEAT_COUNT
                and int(anchor_metrics["requested_repeat_count"])
                == SHORT_CONTEXT_REPEAT_COUNT
                and int(anchor_metrics["effective_repeat_count"])
                == COLLAPSED_SHORT_CONTEXT_EFFECTIVE_REPEAT_COUNT
                and anchor_count >= 1
                and required_count == anchor_count
                and int(anchor_metrics["matched_occurrence_count"])
                == required_count
                and anchor_metrics.get("canonical_threshold_passed") is True
                and metrics.get("failure_codes", []) == []
            )
            if not collapsed_anchor_evidence_is_valid:
                raise RuntimeError(
                    "collapsed repeated-short anchor evidence is internally inconsistent"
                )
        elif collapsed_count_fields_present:
            raise RuntimeError(
                "repeated-short collapse counts require the collapsed context mode"
            )
        if evidence_verdict == QUALITY_VERDICT_PASS:
            transcript = metrics.get("transcript")
            if not isinstance(transcript, str) or not transcript.strip():
                raise RuntimeError("passing candidate ASR evidence requires a transcript")
            try:
                similarity = float(metrics["similarity"])
                wer = float(metrics["wer"])
            except (KeyError, TypeError, ValueError) as exc:
                raise RuntimeError(
                    "passing candidate ASR evidence requires numeric similarity and WER"
                ) from exc
            if not math.isfinite(similarity) or not 0.0 <= similarity <= 1.0:
                raise RuntimeError("passing candidate ASR similarity is outside [0, 1]")
            if not math.isfinite(wer) or wer < 0.0:
                raise RuntimeError("passing candidate ASR WER must be finite and non-negative")
        return check, metrics

    def checkpoint_segment_candidate_decode(
        self,
        candidate_id: int,
        *,
        quality_check_id: int,
        confirmation: bool,
    ) -> sqlite3.Row:
        with self.transaction() as conn:
            candidate = self._candidate_row_conn(conn, candidate_id)
            self._require_candidate_policy_conn(conn, str(candidate["policy_hash"]))
            segment = self._require_candidate_incumbent_conn(conn, candidate)
            self._require_candidate_voice_profile_conn(conn, candidate, segment)
            check, metrics = self._validated_candidate_decode_check_conn(
                conn,
                candidate,
                quality_check_id,
                confirmation=confirmation,
            )
            state = str(candidate["state"])
            result_json = json.dumps(metrics, ensure_ascii=False, sort_keys=True)
            if not confirmation:
                if candidate["beam_check_id"] is not None:
                    if int(candidate["beam_check_id"]) == int(quality_check_id):
                        return candidate
                    raise RuntimeError("candidate beam decode was already checkpointed")
                if state != SEGMENT_CANDIDATE_SIGNAL_PASSED:
                    raise RuntimeError("candidate beam decode transition CAS failed")
                conn.execute(
                    """
                    UPDATE segment_candidates
                    SET state=?,beam_check_id=?,beam_result_json=?,updated_at=?
                    WHERE id=? AND state=? AND beam_check_id IS NULL
                    """,
                    (
                        SEGMENT_CANDIDATE_BEAM_RECORDED,
                        int(quality_check_id),
                        result_json,
                        time.time(),
                        int(candidate_id),
                        SEGMENT_CANDIDATE_SIGNAL_PASSED,
                    ),
                )
                return self._candidate_row_conn(conn, candidate_id)

            if candidate["greedy_check_id"] is not None:
                if int(candidate["greedy_check_id"]) == int(quality_check_id):
                    return candidate
                raise RuntimeError("candidate greedy decode was already checkpointed")
            if state != SEGMENT_CANDIDATE_BEAM_RECORDED or candidate["beam_check_id"] is None:
                raise RuntimeError("candidate greedy decode transition CAS failed")
            beam_check = conn.execute(
                "SELECT verdict FROM quality_checks WHERE id=?",
                (int(candidate["beam_check_id"]),),
            ).fetchone()
            if beam_check is None:
                raise RuntimeError("candidate beam decode evidence is missing")
            dual_passed = (
                str(beam_check["verdict"]) == QUALITY_VERDICT_PASS
                and str(check["verdict"]) == QUALITY_VERDICT_PASS
            )
            signal = self._json_object(candidate["signal_json"], "candidate signal metrics")
            blocking_signal_flags = self._candidate_blocking_signal_flags(signal)
            dual_passed = dual_passed and not blocking_signal_flags
            next_state = (
                SEGMENT_CANDIDATE_DUAL_PASSED
                if dual_passed
                else SEGMENT_CANDIDATE_DUAL_FAILED
            )
            failure_reason = None
            if not dual_passed:
                beam_metrics = self._json_object(
                    candidate["beam_result_json"],
                    "candidate beam result",
                )
                failure_reason = "; ".join(
                    value
                    for value in (
                        f"beam={beam_metrics.get('reason', beam_check['verdict'])}",
                        f"greedy={metrics.get('reason', check['verdict'])}",
                    )
                    if value
                )
                if blocking_signal_flags:
                    failure_reason = "; ".join(
                        value
                        for value in (
                            failure_reason,
                            "blocking_signal=" + ",".join(blocking_signal_flags),
                        )
                        if value
                    )
            conn.execute(
                """
                UPDATE segment_candidates
                SET state=?,greedy_check_id=?,greedy_result_json=?,failure_reason=?,updated_at=?
                WHERE id=? AND state=? AND greedy_check_id IS NULL
                """,
                (
                    next_state,
                    int(quality_check_id),
                    result_json,
                    failure_reason,
                    time.time(),
                    int(candidate_id),
                    SEGMENT_CANDIDATE_BEAM_RECORDED,
                ),
            )
            return self._candidate_row_conn(conn, candidate_id)

    def _perceptual_repair_trigger_payload(
        self,
        trigger: sqlite3.Row,
    ) -> tuple[dict[str, Any], list[str], bool]:
        metrics = self._json_object(
            trigger["metrics_json"],
            "incumbent perceptual trigger metrics",
        )
        try:
            failure_codes = json.loads(str(trigger["failure_codes_json"] or "[]"))
        except (TypeError, json.JSONDecodeError) as exc:
            raise RuntimeError(
                "incumbent perceptual trigger failure codes are invalid"
            ) from exc
        if not isinstance(failure_codes, list) or any(
            not isinstance(code, str) or not code.strip()
            for code in failure_codes
        ):
            raise RuntimeError(
                "incumbent perceptual trigger failure codes are malformed"
            )
        perceptual_verdict = str(metrics.get("verdict") or "").strip().casefold()
        review_shaped = (
            perceptual_verdict == "review"
            or PERCEPTUAL_NATURALNESS_REVIEW_CODE in failure_codes
            or str(trigger["repair_action"] or "") == NATURALNESS_REPAIR_ACTION
        )
        return metrics, failure_codes, review_shaped

    def _validated_naturalness_repair_trigger_conn(
        self,
        conn: sqlite3.Connection,
        *,
        segment_id: int,
        incumbent_sha256: str,
        policy_hash: str,
        quality_check_id: int,
    ) -> sqlite3.Row:
        trigger = conn.execute(
            "SELECT * FROM quality_checks WHERE id=?",
            (int(quality_check_id),),
        ).fetchone()
        if trigger is None:
            raise KeyError(f"Unknown quality check id: {quality_check_id}")
        if (
            str(trigger["scope"]) != QUALITY_SCOPE_SEGMENT
            or str(trigger["stage"]) != SEGMENT_PERCEPTUAL_QUALITY_STAGE
            or int(trigger["segment_id"] or -1) != int(segment_id)
            or trigger["chapter_id"] is not None
            or str(trigger["artifact_sha256"]).casefold()
            != str(incumbent_sha256).casefold()
            or str(trigger["policy_hash"]) != str(policy_hash).strip()
        ):
            raise RuntimeError(
                "naturalness-repair trigger does not belong to this candidate incumbent"
            )
        metrics, failure_codes, review_shaped = (
            self._perceptual_repair_trigger_payload(trigger)
        )
        if str(trigger["repair_action"] or "") != NATURALNESS_REPAIR_ACTION:
            if review_shaped:
                raise RuntimeError(
                    "incumbent perceptual review lacks its naturalness-repair action"
                )
            raise RuntimeError(
                "bound quality check does not authorize naturalness repair"
            )
        trigger_is_valid = (
            str(trigger["verdict"]) == "inconclusive"
            and str(metrics.get("verdict") or "").strip().casefold() == "review"
            and metrics.get("review_required") is True
            and failure_codes == [PERCEPTUAL_NATURALNESS_REVIEW_CODE]
        )
        if not trigger_is_valid:
            raise RuntimeError(
                "incumbent naturalness-repair trigger is internally inconsistent"
            )
        return trigger

    def _require_no_unbound_naturalness_trigger_conn(
        self,
        conn: sqlite3.Connection,
        *,
        segment_id: int,
        incumbent_sha256: str,
        policy_hash: str,
    ) -> None:
        trigger = self._unbound_naturalness_trigger_conn(
            conn,
            segment_id=int(segment_id),
            incumbent_sha256=str(incumbent_sha256),
            policy_hash=str(policy_hash),
        )
        if trigger is None:
            return
        self._validated_naturalness_repair_trigger_conn(
            conn,
            segment_id=int(segment_id),
            incumbent_sha256=str(incumbent_sha256),
            policy_hash=str(policy_hash),
            quality_check_id=int(trigger["id"]),
        )
        raise RuntimeError(
            "naturalness-repair candidate allocation must bind its exact trigger check id"
        )

    def _planned_candidate_repair_binding_conn(
        self,
        conn: sqlite3.Connection,
        *,
        segment_id: int,
        policy_hash: str,
        ordinary_rows: list[sqlite3.Row],
    ) -> dict[str, Any]:
        """Which kind of candidate the next round is owed, and what it binds to.

        The plan used to say nothing on the first allocation and to copy the previous
        candidate's answer after that, so each caller supplied its own default: the
        perceptual loop assumed a naturalness repair and the ASR loop assumed the standard
        gate. A segment whose outstanding trigger was a naturalness review and whose repair
        came round through the ASR loop therefore got a candidate with no trigger bound to
        it, which the database refused - and the next round repeated the mistake, because
        the plan copied it forward. Five rounds of that ended a ten-chapter run.

        The trigger itself is the one place that knows, so it is what is read.
        """
        segment = conn.execute(
            "SELECT wav_sha256 FROM segments WHERE id=?", (int(segment_id),)
        ).fetchone()
        incumbent = str(segment["wav_sha256"] or "") if segment is not None else ""
        if incumbent:
            trigger = self._unbound_naturalness_trigger_conn(
                conn,
                segment_id=int(segment_id),
                incumbent_sha256=incumbent,
                policy_hash=str(policy_hash),
            )
            if trigger is not None:
                return {
                    "candidate_repair_requirement": NATURALNESS_IMPROVEMENT_REQUIREMENT,
                    "repair_trigger_check_id": int(trigger["id"]),
                }
        if ordinary_rows:
            return {
                "candidate_repair_requirement": str(
                    ordinary_rows[0]["candidate_repair_requirement"]
                ),
                "repair_trigger_check_id": (
                    int(ordinary_rows[0]["repair_trigger_check_id"])
                    if ordinary_rows[0]["repair_trigger_check_id"] is not None
                    else None
                ),
            }
        return {
            "candidate_repair_requirement": STANDARD_CANDIDATE_GATE_REQUIREMENT,
            "repair_trigger_check_id": None,
        }

    def _unbound_naturalness_trigger_conn(
        self,
        conn: sqlite3.Connection,
        *,
        segment_id: int,
        incumbent_sha256: str,
        policy_hash: str,
    ) -> sqlite3.Row | None:
        """The naturalness review this audio still owes a candidate, if it owes one.

        Both the caller that refuses an unbound candidate and the one that plans the next
        allocation need to know this, and they used to work it out separately: the planner
        copied the requirement from whatever candidate came before, so one wrong choice
        repeated itself every round until the run ran out of them.
        """
        triggers = list(
            conn.execute(
                """
                SELECT * FROM quality_checks
                WHERE scope=? AND stage=? AND segment_id=?
                  AND artifact_sha256=? AND policy_hash=?
                ORDER BY attempt DESC,id DESC
                """,
                (
                    QUALITY_SCOPE_SEGMENT,
                    SEGMENT_PERCEPTUAL_QUALITY_STAGE,
                    int(segment_id),
                    str(incumbent_sha256).casefold(),
                    str(policy_hash).strip(),
                ),
            )
        )
        for trigger in triggers:
            metrics, _failure_codes, review_shaped = (
                self._perceptual_repair_trigger_payload(trigger)
            )
            if not review_shaped:
                continue
            candidate_evidence = False
            if "candidate_repair_requirement" in metrics:
                try:
                    self._normalized_candidate_repair_requirement(
                        str(metrics["candidate_repair_requirement"])
                    )
                except ValueError:
                    candidate_evidence = False
                else:
                    candidate_evidence = (
                        conn.execute(
                            """
                            SELECT 1 FROM segment_candidates
                            WHERE segment_id=? AND policy_hash=? AND wav_sha256=?
                            LIMIT 1
                            """,
                            (
                                int(segment_id),
                                str(policy_hash).strip(),
                                str(trigger["artifact_sha256"]).casefold(),
                            ),
                        ).fetchone()
                        is not None
                    )
            if candidate_evidence:
                continue
            return trigger
        return None

    def _candidate_perceptual_requirement_conn(
        self,
        conn: sqlite3.Connection,
        candidate: sqlite3.Row,
    ) -> str:
        policy_perceptual_required = self._policy_perceptual_required_conn(
            conn,
            str(candidate["policy_hash"]),
        )
        if (
            policy_perceptual_required is not None
            and bool(candidate["perceptual_required"])
            != policy_perceptual_required
        ):
            raise RuntimeError(
                "segment candidate perceptual requirement differs from its "
                "locked quality policy"
            )
        try:
            requirement = self._normalized_candidate_repair_requirement(
                str(candidate["candidate_repair_requirement"] or "")
            )
        except ValueError as exc:
            raise RuntimeError(
                "segment candidate repair requirement is invalid"
            ) from exc
        trigger_check_id = (
            int(candidate["repair_trigger_check_id"])
            if candidate["repair_trigger_check_id"] is not None
            else None
        )
        if requirement == STANDARD_CANDIDATE_GATE_REQUIREMENT:
            if trigger_check_id is not None:
                raise RuntimeError(
                    "standard segment candidate has an unexpected repair trigger"
                )
            self._require_no_unbound_naturalness_trigger_conn(
                conn,
                segment_id=int(candidate["segment_id"]),
                incumbent_sha256=str(candidate["incumbent_sha256"]),
                policy_hash=str(candidate["policy_hash"]),
            )
            return requirement
        if trigger_check_id is None:
            raise RuntimeError(
                "naturalness-repair candidate lacks its exact trigger check id"
            )
        if not bool(candidate["perceptual_required"]):
            raise RuntimeError(
                "naturalness-repair candidate lacks mandatory perceptual QA"
            )
        self._validated_naturalness_repair_trigger_conn(
            conn,
            segment_id=int(candidate["segment_id"]),
            incumbent_sha256=str(candidate["incumbent_sha256"]),
            policy_hash=str(candidate["policy_hash"]),
            quality_check_id=trigger_check_id,
        )
        return requirement

    def _validated_candidate_perceptual_check_conn(
        self,
        conn: sqlite3.Connection,
        candidate: sqlite3.Row,
        quality_check_id: int,
    ) -> tuple[sqlite3.Row, dict[str, Any]]:
        check = conn.execute(
            "SELECT * FROM quality_checks WHERE id=?",
            (int(quality_check_id),),
        ).fetchone()
        if check is None:
            raise KeyError(f"Unknown quality check id: {quality_check_id}")
        if (
            str(check["scope"]) != QUALITY_SCOPE_SEGMENT
            or str(check["stage"]) != SEGMENT_PERCEPTUAL_QUALITY_STAGE
            or int(check["segment_id"] or -1) != int(candidate["segment_id"])
            or str(check["artifact_sha256"]).casefold() != str(candidate["wav_sha256"])
            or str(check["policy_hash"]) != str(candidate["policy_hash"])
        ):
            raise RuntimeError(
                "perceptual evidence does not belong to this segment candidate"
            )
        candidate_requirement = self._candidate_perceptual_requirement_conn(
            conn,
            candidate,
        )
        evidence_verdict = str(check["verdict"])
        if evidence_verdict not in {QUALITY_VERDICT_PASS, "inconclusive", "fail"}:
            raise RuntimeError("candidate perceptual evidence has an unsupported verdict")
        metrics = self._json_object(
            check["metrics_json"],
            "candidate perceptual metrics",
        )
        perceptual_verdict = str(metrics.get("verdict", "")).strip().casefold()
        short_audio_exemption = (
            str(metrics.get("policy_exemption", "")).strip().casefold()
            == "short_audio"
        )
        strict_short_audio_gate = (
            candidate_requirement == NATURALNESS_IMPROVEMENT_REQUIREMENT
            or str(candidate["postprocess_profile"]) == POSTPROCESS_PROFILE_TEMPO
        )
        if str(metrics.get("candidate_repair_requirement") or "") != (
            candidate_requirement
        ):
            raise RuntimeError(
                "candidate perceptual requirement differs from its incumbent trigger"
            )
        if evidence_verdict == QUALITY_VERDICT_PASS:
            pass_is_supported = perceptual_verdict == "ok" or (
                candidate_requirement == STANDARD_CANDIDATE_GATE_REQUIREMENT
                and not strict_short_audio_gate
                and short_audio_exemption
            )
            if not pass_is_supported:
                raise RuntimeError(
                    "passing candidate perceptual evidence contradicts its metrics"
                )
            if bool(metrics.get("review_required", False)):
                raise RuntimeError(
                    "passing candidate perceptual evidence cannot require review"
                )
        elif perceptual_verdict == "ok" or (
            short_audio_exemption
            and candidate_requirement == STANDARD_CANDIDATE_GATE_REQUIREMENT
            and not strict_short_audio_gate
        ):
            raise RuntimeError(
                "failed candidate perceptual evidence contradicts its metrics"
            )
        signal = self._json_object(candidate["signal_json"], "candidate signal metrics")
        self._require_candidate_vocalization_provenance_conn(
            conn,
            candidate,
            signal,
        )
        signal_provenance = self._candidate_signal_provenance(signal)
        self._require_candidate_delivery_provenance(candidate, signal_provenance)
        self._require_candidate_postprocess_provenance_conn(
            conn,
            candidate,
            signal,
        )
        if str(candidate["postprocess_profile"]) == POSTPROCESS_PROFILE_TEMPO:
            if any(
                metrics.get(field) != signal.get(field)
                for field in (
                    POSTPROCESS_PROFILE_FIELD,
                    POSTPROCESS_SOURCE_CANDIDATE_ID_FIELD,
                    POSTPROCESS_SOURCE_SHA256_FIELD,
                    POSTPROCESS_SOURCE_SAMPLE_RATE_FIELD,
                    POSTPROCESS_SOURCE_SAMPLES_FIELD,
                    POSTPROCESS_OUTPUT_SAMPLES_FIELD,
                )
            ):
                raise RuntimeError(
                    "tempo candidate perceptual provenance differs from its signal checkpoint"
                )
        try:
            baseline_pitch = int(metrics["baseline_pitch_semitones"])
        except (KeyError, TypeError, ValueError) as exc:
            raise RuntimeError(
                "candidate perceptual evidence lacks baseline pitch provenance"
            ) from exc
        # Against the grading policy, not against the take. The perceptual score is
        # measured on the raw audio and compared to the preset's untouched preview, so the
        # baseline is that preview's register whatever pitch this particular take carries.
        #
        # Comparing it to the take's own effective pitch made the two impossible to satisfy
        # together for any voice with a register shift: seven candidates read at -1 semitone
        # stopped a ten-chapter run twice at the same line, while the pipeline was
        # deliberately setting the baseline to 0 four files away.
        if baseline_pitch != PERCEPTUAL_BASELINE_PITCH_SEMITONES:
            raise RuntimeError(
                "candidate perceptual baseline pitch is not the graded reference: "
                f"{baseline_pitch} != {PERCEPTUAL_BASELINE_PITCH_SEMITONES}"
            )
        return check, metrics

    def _validated_dual_failed_candidate_conn(
        self,
        conn: sqlite3.Connection,
        candidate: sqlite3.Row,
    ) -> bool:
        if str(candidate["state"]) != SEGMENT_CANDIDATE_DUAL_FAILED:
            raise RuntimeError("dual-failed validation requires dual-failed state")
        if candidate["beam_check_id"] is None or candidate["greedy_check_id"] is None:
            raise RuntimeError("dual-failed candidate lacks complete ASR checkpoints")

        decoded_checks: list[sqlite3.Row] = []
        for confirmation, check_field, result_field in (
            (False, "beam_check_id", "beam_result_json"),
            (True, "greedy_check_id", "greedy_result_json"),
        ):
            check, metrics = self._validated_candidate_decode_check_conn(
                conn,
                candidate,
                int(candidate[check_field]),
                confirmation=confirmation,
            )
            stored_metrics = self._json_object(
                candidate[result_field],
                "stored candidate ASR decode result",
            )
            if stored_metrics != metrics:
                raise RuntimeError(
                    "stored candidate ASR result differs from its quality-check evidence"
                )
            decoded_checks.append(check)

        dual_asr_passed = all(
            str(check["verdict"]) == QUALITY_VERDICT_PASS
            for check in decoded_checks
        )
        if candidate["perceptual_check_id"] is None:
            signal = self._json_object(
                candidate["signal_json"],
                "candidate signal metrics",
            )
            if dual_asr_passed and not self._candidate_blocking_signal_flags(signal):
                raise RuntimeError(
                    "dual-failed candidate has neither an ASR nor signal blocker"
                )
            return False

        if not dual_asr_passed:
            raise RuntimeError(
                "candidate perceptual evidence cannot follow a failed ASR decode"
            )
        perceptual_check, perceptual_metrics = (
            self._validated_candidate_perceptual_check_conn(
                conn,
                candidate,
                int(candidate["perceptual_check_id"]),
            )
        )
        stored_perceptual_metrics = self._json_object(
            candidate["perceptual_result_json"],
            "stored candidate perceptual result",
        )
        if stored_perceptual_metrics != perceptual_metrics:
            raise RuntimeError(
                "stored candidate perceptual result differs from its quality-check evidence"
            )
        if str(perceptual_check["verdict"]) == QUALITY_VERDICT_PASS:
            raise RuntimeError(
                "dual-failed candidate has passing perceptual evidence"
            )
        return (
            str(perceptual_metrics.get("verdict") or "").strip().casefold()
            == "review"
            and perceptual_metrics.get("review_required") is True
        )

    def checkpoint_segment_candidate_perceptual(
        self,
        candidate_id: int,
        *,
        quality_check_id: int,
    ) -> sqlite3.Row:
        with self.transaction() as conn:
            candidate = self._candidate_row_conn(conn, candidate_id)
            self._require_candidate_policy_conn(conn, str(candidate["policy_hash"]))
            segment = self._require_candidate_incumbent_conn(conn, candidate)
            self._require_candidate_voice_profile_conn(conn, candidate, segment)
            if not bool(candidate["perceptual_required"]):
                raise RuntimeError(
                    "segment candidate was not allocated with mandatory perceptual QA"
                )
            check, metrics = self._validated_candidate_perceptual_check_conn(
                conn,
                candidate,
                quality_check_id,
            )
            result_json = json.dumps(metrics, ensure_ascii=False, sort_keys=True)
            if candidate["perceptual_check_id"] is not None:
                if (
                    int(candidate["perceptual_check_id"]) == int(quality_check_id)
                    and str(candidate["perceptual_result_json"] or "") == result_json
                ):
                    return candidate
                raise RuntimeError(
                    "candidate perceptual evidence was already checkpointed"
                )
            if str(candidate["state"]) != SEGMENT_CANDIDATE_DUAL_PASSED:
                raise RuntimeError(
                    "candidate perceptual checkpoint requires two passing ASR decodes"
                )
            passed = str(check["verdict"]) == QUALITY_VERDICT_PASS
            next_state = (
                SEGMENT_CANDIDATE_DUAL_PASSED
                if passed
                else SEGMENT_CANDIDATE_DUAL_FAILED
            )
            failure_reason = (
                None
                if passed
                else f"perceptual={metrics.get('reason', check['verdict'])}"
            )
            cursor = conn.execute(
                """
                UPDATE segment_candidates
                SET state=?,perceptual_check_id=?,perceptual_result_json=?,
                    failure_reason=?,updated_at=?
                WHERE id=? AND state=? AND perceptual_check_id IS NULL
                """,
                (
                    next_state,
                    int(quality_check_id),
                    result_json,
                    failure_reason,
                    time.time(),
                    int(candidate_id),
                    SEGMENT_CANDIDATE_DUAL_PASSED,
                ),
            )
            if cursor.rowcount != 1:
                raise RuntimeError("candidate perceptual checkpoint transition CAS failed")
            return self._candidate_row_conn(conn, candidate_id)

    def mark_segment_candidate_tts_failed(
        self,
        candidate_id: int,
        *,
        expected_generation_seed: int,
        error: str,
    ) -> sqlite3.Row:
        normalized_error = str(error or "").strip()
        if not normalized_error:
            raise ValueError("segment candidate TTS failure must include a reason")
        with self.transaction() as conn:
            candidate = self._candidate_row_conn(conn, candidate_id)
            self._require_candidate_policy_conn(conn, str(candidate["policy_hash"]))
            segment = self._require_candidate_incumbent_conn(conn, candidate)
            self._require_candidate_voice_profile_conn(conn, candidate, segment)
            if str(candidate["state"]) == SEGMENT_CANDIDATE_TTS_FAILED:
                if (
                    int(candidate["generation_seed"]) == int(expected_generation_seed)
                    and str(candidate["failure_reason"] or "") == normalized_error[-8000:]
                ):
                    return candidate
                raise RuntimeError("segment candidate TTS failure replay payload differs")
            if (
                str(candidate["state"]) != SEGMENT_CANDIDATE_GENERATING
                or int(candidate["generation_seed"]) != int(expected_generation_seed)
            ):
                raise RuntimeError("segment candidate TTS failure transition CAS failed")
            conn.execute(
                """
                UPDATE segment_candidates
                SET state=?,failure_reason=?,updated_at=?
                WHERE id=? AND state=? AND generation_seed=?
                """,
                (
                    SEGMENT_CANDIDATE_TTS_FAILED,
                    normalized_error[-8000:],
                    time.time(),
                    int(candidate_id),
                    SEGMENT_CANDIDATE_GENERATING,
                    int(expected_generation_seed),
                ),
            )
            return self._candidate_row_conn(conn, candidate_id)

    def mark_segment_candidate_invalid(
        self,
        candidate_id: int,
        *,
        expected_wav_sha256: str,
        reason: str,
    ) -> sqlite3.Row:
        normalized_sha256 = self._normalized_sha256(
            expected_wav_sha256,
            "segment candidate invalidation checksum",
        )
        normalized_reason = str(reason or "").strip()
        if not normalized_reason:
            raise ValueError("segment candidate invalidation must include a reason")
        with self.transaction() as conn:
            candidate = self._candidate_row_conn(conn, candidate_id)
            self._require_candidate_policy_conn(conn, str(candidate["policy_hash"]))
            segment = self._require_candidate_incumbent_conn(conn, candidate)
            self._require_candidate_voice_profile_conn(conn, candidate, segment)
            state = str(candidate["state"])
            if state == SEGMENT_CANDIDATE_INVALID:
                if (
                    str(candidate["wav_sha256"] or "") == normalized_sha256
                    and str(candidate["failure_reason"] or "") == normalized_reason[-8000:]
                ):
                    return candidate
                raise RuntimeError("segment candidate invalidation replay payload differs")
            if state in {SEGMENT_CANDIDATE_GENERATING, SEGMENT_CANDIDATE_TTS_FAILED}:
                raise RuntimeError("candidate has no committed WAV to invalidate")
            if state == SEGMENT_CANDIDATE_PROMOTED:
                raise RuntimeError("a promoted segment candidate cannot be invalidated")
            if str(candidate["wav_sha256"] or "") != normalized_sha256:
                raise RuntimeError("segment candidate invalidation checksum CAS failed")
            conn.execute(
                """
                UPDATE segment_candidates
                SET state=?,failure_reason=?,updated_at=?
                WHERE id=? AND state=? AND wav_sha256=?
                """,
                (
                    SEGMENT_CANDIDATE_INVALID,
                    normalized_reason[-8000:],
                    time.time(),
                    int(candidate_id),
                    state,
                    normalized_sha256,
                ),
            )
            return self._candidate_row_conn(conn, candidate_id)

    def get_segment_candidate(self, candidate_id: int) -> sqlite3.Row:
        with self.connect() as conn:
            return self._candidate_row_conn(conn, candidate_id)

    def list_segment_candidates(
        self,
        *,
        segment_id: int | None = None,
        policy_hash: str | None = None,
    ) -> list[sqlite3.Row]:
        clauses: list[str] = []
        params: list[Any] = []
        if segment_id is not None:
            clauses.append("segment_id=?")
            params.append(int(segment_id))
        if policy_hash is not None:
            clauses.append("policy_hash=?")
            params.append(str(policy_hash).strip())
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        with self.connect() as conn:
            return list(
                conn.execute(
                    f"SELECT * FROM segment_candidates{where} ORDER BY segment_id,repair_round",
                    params,
                )
            )

    def previous_segment_candidate_decode_evidence(
        self,
        *,
        segment_id: int,
        policy_hash: str,
        repair_round: int,
    ) -> list[dict[str, Any]]:
        normalized_round = int(repair_round)
        if normalized_round < 0:
            raise ValueError("segment candidate repair round must be non-negative")
        if normalized_round == 0:
            return []

        with self.connect() as conn:
            self._require_candidate_policy_conn(conn, policy_hash)
            candidate = conn.execute(
                """
                SELECT * FROM segment_candidates
                WHERE segment_id=? AND policy_hash=? AND repair_round=?
                """,
                (
                    int(segment_id),
                    str(policy_hash).strip(),
                    normalized_round - 1,
                ),
            ).fetchone()
            if candidate is None:
                raise RuntimeError(
                    "previous segment candidate is missing before repair allocation"
                )
            state = str(candidate["state"])
            if state in {
                SEGMENT_CANDIDATE_TTS_FAILED,
                SEGMENT_CANDIDATE_INVALID,
            }:
                return []
            if state != SEGMENT_CANDIDATE_DUAL_FAILED:
                raise RuntimeError(
                    "previous segment candidate lacks a terminal dual-decode failure"
                )
            if (
                candidate["beam_check_id"] is None
                or candidate["greedy_check_id"] is None
                or candidate["beam_result_json"] is None
                or candidate["greedy_result_json"] is None
            ):
                raise RuntimeError(
                    "previous segment candidate lacks complete dual-decode evidence"
                )

            segment = self._require_candidate_incumbent_conn(conn, candidate)
            self._require_candidate_voice_profile_conn(conn, candidate, segment)
            evidence: list[dict[str, Any]] = []
            for confirmation, check_field, result_field in (
                (False, "beam_check_id", "beam_result_json"),
                (True, "greedy_check_id", "greedy_result_json"),
            ):
                check, metrics = self._validated_candidate_decode_check_conn(
                    conn,
                    candidate,
                    int(candidate[check_field]),
                    confirmation=confirmation,
                )
                stored_metrics = self._json_object(
                    candidate[result_field],
                    "stored candidate ASR decode result",
                )
                if stored_metrics != metrics:
                    raise RuntimeError(
                        "stored candidate ASR result differs from its quality-check evidence"
                    )
                try:
                    check_failure_codes = json.loads(
                        str(check["failure_codes_json"] or "[]")
                    )
                except (TypeError, json.JSONDecodeError) as exc:
                    raise RuntimeError(
                        "candidate ASR quality-check failure codes are not valid JSON"
                    ) from exc
                metrics_failure_codes = metrics.get("failure_codes", [])
                if (
                    not isinstance(check_failure_codes, list)
                    or not isinstance(metrics_failure_codes, list)
                    or any(
                        not isinstance(code, str) or not code.strip()
                        for code in [*check_failure_codes, *metrics_failure_codes]
                    )
                    or len(set(check_failure_codes)) != len(check_failure_codes)
                    or len(set(metrics_failure_codes)) != len(metrics_failure_codes)
                    or check_failure_codes != metrics_failure_codes
                ):
                    raise RuntimeError(
                        "candidate ASR failure-code ledger contradicts its decode metrics"
                    )
                evidence.append(dict(metrics))
            return evidence

    def reconcile_segment_candidate_artifacts(self, policy_hash: str) -> int:
        invalidated = 0
        with self.transaction() as conn:
            self._require_candidate_policy_conn(conn, policy_hash)
            promoted_candidates = list(
                conn.execute(
                    """
                    SELECT * FROM segment_candidates
                    WHERE policy_hash=? AND state='promoted'
                    ORDER BY segment_id,repair_round
                    """,
                    (str(policy_hash).strip(),),
                )
            )
            for promoted_candidate in promoted_candidates:
                self._candidate_perceptual_requirement_conn(
                    conn,
                    promoted_candidate,
                )
                self._validated_promoted_candidate_conn(
                    conn,
                    promoted_candidate,
                )
            candidates = list(
                conn.execute(
                    """
                    SELECT * FROM segment_candidates
                    WHERE policy_hash=? AND state NOT IN ('generating','tts_failed','invalid','promoted')
                    ORDER BY segment_id,repair_round
                    """,
                    (str(policy_hash).strip(),),
                )
            )
            for candidate in candidates:
                invalid_reason: str | None = None
                try:
                    self._candidate_perceptual_requirement_conn(conn, candidate)
                except (KeyError, RuntimeError) as exc:
                    invalid_reason = str(exc)
                try:
                    if invalid_reason is None:
                        segment = self._require_candidate_incumbent_conn(conn, candidate)
                        self._require_candidate_voice_profile_conn(
                            conn,
                            candidate,
                            segment,
                        )
                except (KeyError, RuntimeError) as exc:
                    invalid_reason = str(exc)
                if invalid_reason is None:
                    invalid_reason = self._candidate_file_error(candidate)
                if invalid_reason is None:
                    try:
                        signal = self._json_object(
                            candidate["signal_json"],
                            "candidate signal metrics",
                        )
                        self._require_candidate_split_provenance(
                            conn,
                            candidate,
                            signal,
                        )
                        self._require_candidate_vocalization_provenance_conn(
                            conn,
                            candidate,
                            signal,
                        )
                        signal_provenance = self._candidate_signal_provenance(signal)
                        self._require_candidate_delivery_provenance(
                            candidate,
                            signal_provenance,
                        )
                        self._require_candidate_postprocess_provenance_conn(
                            conn,
                            candidate,
                            signal,
                        )
                    except (RuntimeError, ValueError) as exc:
                        invalid_reason = str(exc)
                if invalid_reason is None and str(candidate["state"]) == SEGMENT_CANDIDATE_DUAL_PASSED:
                    try:
                        blocking_flags = self._candidate_blocking_signal_flags(signal)
                        if blocking_flags:
                            invalid_reason = (
                                "candidate signal retains blocking TTS flags: "
                                + ", ".join(blocking_flags)
                            )
                    except RuntimeError as exc:
                        invalid_reason = str(exc)
                if invalid_reason is None and candidate["perceptual_check_id"] is not None:
                    if not bool(candidate["perceptual_required"]):
                        invalid_reason = (
                            "candidate has perceptual evidence without a mandatory perceptual gate"
                        )
                    else:
                        try:
                            perceptual_check, _metrics = (
                                self._validated_candidate_perceptual_check_conn(
                                    conn,
                                    candidate,
                                    int(candidate["perceptual_check_id"]),
                                )
                            )
                            if (
                                str(candidate["state"])
                                == SEGMENT_CANDIDATE_DUAL_PASSED
                                and str(perceptual_check["verdict"])
                                != QUALITY_VERDICT_PASS
                            ):
                                invalid_reason = (
                                    "actionable candidate perceptual evidence is not passing"
                                )
                        except (KeyError, RuntimeError) as exc:
                            invalid_reason = str(exc)
                if invalid_reason:
                    self._invalidate_candidate_conn(conn, candidate, invalid_reason)
                    invalidated += 1
        return invalidated

    def segment_candidate_attempt_summary(
        self,
        segment_id: int,
        policy_hash: str,
    ) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = list(
                conn.execute(
                    """
                    SELECT * FROM segment_candidates
                    WHERE segment_id=? AND policy_hash=?
                    ORDER BY repair_round
                    """,
                    (int(segment_id), str(policy_hash).strip()),
                )
            )
            for row in rows:
                if str(row["state"]) == SEGMENT_CANDIDATE_PROMOTED:
                    self._validated_promoted_candidate_conn(conn, row)
                elif str(row["state"]) == SEGMENT_CANDIDATE_DUAL_FAILED:
                    self._validated_dual_failed_candidate_conn(conn, row)
            return [self._candidate_summary(row) for row in rows]

    def segment_candidate_resume_plan(
        self,
        segment_id: int,
        policy_hash: str,
        max_repair_rounds: int | None = None,
    ) -> dict[str, Any]:
        requested_max = (
            int(max_repair_rounds) if max_repair_rounds is not None else None
        )
        if requested_max is not None and requested_max < 0:
            raise ValueError("ASR repair budget must be non-negative")
        with self.connect() as conn:
            policy = self._require_candidate_policy_conn(conn, policy_hash, active=False)
            rows = list(
                conn.execute(
                    """
                    SELECT * FROM segment_candidates
                    WHERE segment_id=? AND policy_hash=?
                    ORDER BY repair_round
                    """,
                    (int(segment_id), str(policy_hash).strip()),
                )
            )
            if not bool(policy["active"]):
                return {
                    "segment_id": int(segment_id),
                    "policy_hash": str(policy_hash).strip(),
                    "action": "stale_policy",
                    "candidate_id": None,
                    "repair_round": None,
                }
            for row in rows:
                self._candidate_perceptual_requirement_conn(conn, row)
            if rows:
                repair_bindings = {
                    (
                        str(row["candidate_repair_requirement"]),
                        (
                            int(row["repair_trigger_check_id"])
                            if row["repair_trigger_check_id"] is not None
                            else None
                        ),
                    )
                    for row in rows
                }
                if len(repair_bindings) != 1:
                    raise RuntimeError(
                        "same-policy candidate rounds contain mixed repair trigger bindings"
                    )
                stored_budgets = {int(row["repair_budget"]) for row in rows}
                if len(stored_budgets) != 1:
                    raise RuntimeError(
                        "same-policy candidate rounds contain mixed repair budgets"
                    )
                normalized_max = next(iter(stored_budgets))
                if requested_max is not None and requested_max != normalized_max:
                    raise RuntimeError(
                        "stored candidate repair budget differs from the active repair context"
                    )
            else:
                if requested_max is None:
                    raise ValueError(
                        "a repair budget is required before the first candidate allocation"
                    )
                normalized_max = requested_max
            promoted = [row for row in rows if str(row["state"]) == SEGMENT_CANDIDATE_PROMOTED]
            if promoted:
                if len(promoted) != 1 or any(
                    str(row["state"])
                    not in SEGMENT_CANDIDATE_FAILURE_STATES | {SEGMENT_CANDIDATE_PROMOTED}
                    for row in rows
                ):
                    raise RuntimeError("promoted candidate ledger has another actionable candidate")
                self._validated_promoted_candidate_conn(conn, promoted[0])
                return {
                    "segment_id": int(segment_id),
                    "policy_hash": str(policy_hash).strip(),
                    "action": "complete",
                    "candidate_id": int(promoted[0]["id"]),
                    "repair_round": int(promoted[0]["repair_round"]),
                    "state": SEGMENT_CANDIDATE_PROMOTED,
                }
            if rows:
                incumbents = {str(row["incumbent_sha256"]) for row in rows}
                if len(incumbents) != 1:
                    raise RuntimeError("same-policy candidate rounds contain mixed incumbent artifacts")
                segment = conn.execute(
                    "SELECT wav_sha256 FROM segments WHERE id=?",
                    (int(segment_id),),
                ).fetchone()
                if segment is None:
                    raise KeyError(f"Unknown segment id: {segment_id}")
                if str(segment["wav_sha256"] or "").casefold() not in incumbents:
                    return {
                        "segment_id": int(segment_id),
                        "policy_hash": str(policy_hash).strip(),
                        "action": "stale_incumbent",
                        "candidate_id": None,
                        "repair_round": None,
                    }
            ordinary_rows = [
                row
                for row in rows
                if str(row["postprocess_profile"]) == POSTPROCESS_PROFILE_NONE
            ]
            tempo_rows = [
                row
                for row in rows
                if str(row["postprocess_profile"]) == POSTPROCESS_PROFILE_TEMPO
            ]
            if len(ordinary_rows) + len(tempo_rows) != len(rows):
                raise RuntimeError("stored candidate has an unsupported postprocess profile")
            if [int(row["repair_round"]) for row in ordinary_rows] != list(
                range(len(ordinary_rows))
            ) or any(int(row["repair_round"]) >= normalized_max for row in ordinary_rows):
                raise RuntimeError("stored ordinary candidate rounds are not contiguous")
            if len(tempo_rows) > 1 or any(
                int(row["repair_round"]) != normalized_max for row in tempo_rows
            ):
                raise RuntimeError("stored tempo candidate round is invalid")

            actionable = [
                row
                for row in rows
                if str(row["state"])
                not in SEGMENT_CANDIDATE_FAILURE_STATES | {SEGMENT_CANDIDATE_PROMOTED}
            ]
            if len(actionable) > 1:
                raise RuntimeError("multiple segment candidates are simultaneously actionable")
            if actionable:
                candidate = actionable[0]
                segment = self._require_candidate_incumbent_conn(conn, candidate)
                self._require_candidate_voice_profile_conn(conn, candidate, segment)
                state = str(candidate["state"])
                if str(candidate["postprocess_profile"]) == POSTPROCESS_PROFILE_TEMPO:
                    source = self._candidate_row_conn(
                        conn,
                        int(candidate["postprocess_source_candidate_id"]),
                    )
                    if (
                        str(source["wav_sha256"] or "").casefold()
                        != str(candidate["postprocess_source_sha256"] or "").casefold()
                    ):
                        raise RuntimeError(
                            "tempo candidate source checksum differs from its ledger"
                        )
                    eligibility_reason = self._tempo_source_eligibility_reason_conn(
                        conn,
                        source,
                    )
                    if eligibility_reason is not None:
                        raise RuntimeError(
                            "tempo candidate source is no longer eligible: "
                            + eligibility_reason
                        )
                if state != SEGMENT_CANDIDATE_GENERATING:
                    signal = self._json_object(
                        candidate["signal_json"],
                        "candidate signal metrics",
                    )
                    self._require_candidate_split_provenance(conn, candidate, signal)
                    self._require_candidate_vocalization_provenance_conn(
                        conn,
                        candidate,
                        signal,
                    )
                    signal_provenance = self._candidate_signal_provenance(signal)
                    self._require_candidate_delivery_provenance(
                        candidate,
                        signal_provenance,
                    )
                    self._require_candidate_postprocess_provenance_conn(
                        conn,
                        candidate,
                        signal,
                    )
                if state == SEGMENT_CANDIDATE_DUAL_PASSED:
                    action = (
                        "verify_perceptual"
                        if bool(candidate["perceptual_required"])
                        and candidate["perceptual_check_id"] is None
                        else "promote"
                    )
                else:
                    action = {
                        SEGMENT_CANDIDATE_GENERATING: "generate",
                        SEGMENT_CANDIDATE_SIGNAL_PASSED: "decode_beam",
                        SEGMENT_CANDIDATE_BEAM_RECORDED: "decode_greedy",
                    }.get(state)
                if action is None:
                    raise RuntimeError(f"unsupported actionable candidate state: {state}")
                plan = {
                    "segment_id": int(segment_id),
                    "policy_hash": str(policy_hash).strip(),
                    "action": action,
                    "candidate_id": int(candidate["id"]),
                    "repair_round": int(candidate["repair_round"]),
                    "state": state,
                    "generation_strategy": str(candidate["generation_strategy"]),
                    "generation_seed": int(candidate["generation_seed"]),
                    "tts_attempt": int(candidate["tts_attempt"]),
                    "wav_path": str(candidate["wav_path"]),
                    "wav_sha256": str(candidate["wav_sha256"] or ""),
                    "perceptual_required": bool(candidate["perceptual_required"]),
                    "pronunciation_delivery_variant": str(
                        candidate["pronunciation_delivery_variant"]
                    ),
                    "expected_spoken_text_sha256": str(
                        candidate["expected_spoken_text_sha256"]
                    ),
                }
                if str(candidate["postprocess_profile"]) == POSTPROCESS_PROFILE_TEMPO:
                    plan.update(
                        {
                            POSTPROCESS_PROFILE_FIELD: POSTPROCESS_PROFILE_TEMPO,
                            POSTPROCESS_SOURCE_CANDIDATE_ID_FIELD: int(
                                candidate["postprocess_source_candidate_id"]
                            ),
                            POSTPROCESS_SOURCE_SHA256_FIELD: str(
                                candidate["postprocess_source_sha256"]
                            ),
                        }
                    )
                return plan
            if len(ordinary_rows) < normalized_max:
                allocation_plan = {
                    "segment_id": int(segment_id),
                    "policy_hash": str(policy_hash).strip(),
                    "action": "allocate",
                    "candidate_id": None,
                    "repair_round": len(rows),
                }
                allocation_plan.update(
                    self._planned_candidate_repair_binding_conn(
                        conn,
                        segment_id=int(segment_id),
                        policy_hash=str(policy_hash).strip(),
                        ordinary_rows=ordinary_rows,
                    )
                )
                return allocation_plan
            if not tempo_rows:
                if any(
                    str(row["state"]) not in SEGMENT_CANDIDATE_FAILURE_STATES
                    for row in ordinary_rows
                ):
                    raise RuntimeError(
                        "ordinary candidate ledger has an unresolved nonterminal row"
                    )
                source = ordinary_rows[-1] if ordinary_rows else None
                if source is not None:
                    eligibility_reason = self._tempo_source_eligibility_reason_conn(
                        conn,
                        source,
                    )
                    if eligibility_reason is None:
                        return {
                            "segment_id": int(segment_id),
                            "policy_hash": str(policy_hash).strip(),
                            "action": "allocate_postprocess",
                            "candidate_id": None,
                            "repair_round": normalized_max,
                            POSTPROCESS_PROFILE_FIELD: POSTPROCESS_PROFILE_TEMPO,
                            POSTPROCESS_SOURCE_CANDIDATE_ID_FIELD: int(source["id"]),
                            POSTPROCESS_SOURCE_SHA256_FIELD: str(source["wav_sha256"]),
                        }
            return {
                "segment_id": int(segment_id),
                "policy_hash": str(policy_hash).strip(),
                "action": "exhausted",
                "candidate_id": None,
                "repair_round": None,
            }

    def list_segment_candidate_resume_plans(
        self,
        policy_hash: str,
        max_repair_rounds: int | None = None,
    ) -> list[dict[str, Any]]:
        with self.connect() as conn:
            segment_ids = [
                int(row[0])
                for row in conn.execute(
                    """
                    SELECT DISTINCT segment_id FROM segment_candidates
                    WHERE policy_hash=? ORDER BY segment_id
                    """,
                    (str(policy_hash).strip(),),
                )
            ]
        return [
            self.segment_candidate_resume_plan(segment_id, policy_hash, max_repair_rounds)
            for segment_id in segment_ids
        ]

    def count_stale_segment_candidates(self, active_policy_hash: str) -> int:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) FROM segment_candidates WHERE policy_hash<>? AND state<>'promoted'",
                (str(active_policy_hash).strip(),),
            ).fetchone()
            return int(row[0] if row is not None else 0)

    def promote_segment_candidate(
        self,
        candidate_id: int,
        *,
        validated_wav_sha256: str,
        repair_action: str | None = None,
        attempt: int,
        warning_code: str | None = None,
    ) -> sqlite3.Row:
        normalized_sha256 = self._normalized_sha256(
            validated_wav_sha256,
            "validated segment candidate checksum",
        )
        normalized_attempt = int(attempt)
        if normalized_attempt < 1:
            raise ValueError("candidate final audio attempt must be positive")
        normalized_repair_action = str(repair_action).strip() if repair_action else None
        normalized_warning_code = str(warning_code).strip() if warning_code else None
        with self.transaction() as conn:
            candidate = self._candidate_row_conn(conn, candidate_id)
            policy = self._require_candidate_policy_conn(conn, str(candidate["policy_hash"]))
            self._candidate_perceptual_requirement_conn(conn, candidate)
            segment = conn.execute(
                "SELECT * FROM segments WHERE id=?",
                (int(candidate["segment_id"]),),
            ).fetchone()
            if segment is None:
                raise KeyError(f"Unknown segment id: {candidate['segment_id']}")
            if str(candidate["wav_sha256"] or "") != normalized_sha256:
                raise RuntimeError("validated candidate checksum differs from the durable signal checkpoint")
            candidate_state = str(candidate["state"])
            if candidate_state not in {
                SEGMENT_CANDIDATE_DUAL_PASSED,
                SEGMENT_CANDIDATE_PROMOTED,
            }:
                raise RuntimeError("segment candidate cannot be promoted before both ASR decodes pass")
            self._require_candidate_voice_profile_conn(conn, candidate, segment)
            signal = self._json_object(
                candidate["signal_json"],
                "candidate signal metrics",
            )
            self._require_candidate_split_provenance(conn, candidate, signal)
            self._require_candidate_vocalization_provenance_conn(
                conn,
                candidate,
                signal,
            )
            signal_provenance = self._candidate_signal_provenance(signal)
            self._require_candidate_delivery_provenance(
                candidate,
                signal_provenance,
            )
            self._require_candidate_postprocess_provenance_conn(
                conn,
                candidate,
                signal,
            )
            beam_check, beam_metrics = self._validated_candidate_decode_check_conn(
                conn,
                candidate,
                int(candidate["beam_check_id"]),
                confirmation=False,
            )
            greedy_check, greedy_metrics = self._validated_candidate_decode_check_conn(
                conn,
                candidate,
                int(candidate["greedy_check_id"]),
                confirmation=True,
            )
            if (
                str(beam_check["verdict"]) != QUALITY_VERDICT_PASS
                or str(greedy_check["verdict"]) != QUALITY_VERDICT_PASS
            ):
                raise RuntimeError("candidate dual-decode ledger does not contain two passing checks")
            if bool(candidate["perceptual_required"]):
                if candidate["perceptual_check_id"] is None:
                    raise RuntimeError(
                        "segment candidate cannot be promoted before perceptual QA passes"
                    )
                perceptual_check, _perceptual_metrics = (
                    self._validated_candidate_perceptual_check_conn(
                        conn,
                        candidate,
                        int(candidate["perceptual_check_id"]),
                    )
                )
                if str(perceptual_check["verdict"]) != QUALITY_VERDICT_PASS:
                    raise RuntimeError(
                        "segment candidate perceptual ledger is not passing"
                    )
            elif candidate["perceptual_check_id"] is not None:
                raise RuntimeError(
                    "segment candidate has unexpected perceptual QA evidence"
                )
            final_metrics = self._candidate_final_metrics(
                candidate,
                beam_metrics,
                greedy_metrics,
                warning_code=normalized_warning_code,
            )
            final_metrics_json = json.dumps(final_metrics, ensure_ascii=False, sort_keys=True)
            if candidate_state == SEGMENT_CANDIDATE_PROMOTED:
                if (
                    str(segment["wav_sha256"] or "") == normalized_sha256
                    and candidate["final_check_id"] is not None
                ):
                    final_check = conn.execute(
                        "SELECT * FROM quality_checks WHERE id=?",
                        (int(candidate["final_check_id"]),),
                    ).fetchone()
                    if (
                        final_check is not None
                        and str(final_check["verdict"]) == QUALITY_VERDICT_PASS
                        and str(final_check["metrics_json"]) == final_metrics_json
                        and str(final_check["failure_codes_json"]) == "[]"
                        and final_check["repair_action"] == normalized_repair_action
                        and int(final_check["attempt"]) == normalized_attempt
                    ):
                        return candidate
                raise RuntimeError("segment candidate promotion replay does not match the committed result")
            if str(segment["wav_sha256"] or "").casefold() != str(candidate["incumbent_sha256"]):
                raise RuntimeError("segment candidate incumbent checksum changed")
            file_error = self._candidate_file_error(candidate)
            if file_error:
                return self._invalidate_candidate_conn(conn, candidate, file_error)
            blocking_signal_flags = self._candidate_blocking_signal_flags(signal)
            if blocking_signal_flags:
                return self._invalidate_candidate_conn(
                    conn,
                    candidate,
                    "candidate signal retains blocking TTS flags: "
                    + ", ".join(blocking_signal_flags),
                )
            final_check_cursor = conn.execute(
                """
                INSERT INTO quality_checks(
                    scope,stage,segment_id,chapter_id,artifact_sha256,
                    policy_hash,policy_version,verdict,metrics_json,
                    failure_codes_json,repair_action,attempt,created_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    QUALITY_SCOPE_SEGMENT,
                    SEGMENT_AUDIO_QUALITY_STAGE,
                    int(candidate["segment_id"]),
                    None,
                    normalized_sha256,
                    str(candidate["policy_hash"]),
                    int(policy["policy_version"]),
                    QUALITY_VERDICT_PASS,
                    final_metrics_json,
                    "[]",
                    normalized_repair_action,
                    normalized_attempt,
                    time.time(),
                ),
            )
            final_quality_check_id = int(final_check_cursor.lastrowid)
            retained_warning = self._without_audio_attempt_warnings(
                str(segment["warning_code"]) if segment["warning_code"] else None
            )
            merged_warning = self._merge_warning_codes(retained_warning, normalized_warning_code)
            status = SegmentStatus.WARNING.value if merged_warning else SegmentStatus.VERIFIED.value
            now = time.time()
            segment_cursor = conn.execute(
                """
                UPDATE segments SET
                    status=?,generation_seed=?,generation_frame_cap=NULL,
                    generation_delivery_mode=?,generation_repair_round=?,generation_policy_hash=?,
                    wav_path=?,wav_sha256=?,wav_duration=?,signal_json=?,
                    asr_text=?,asr_similarity=?,asr_wer=?,warning_code=?,error=NULL,updated_at=?
                WHERE id=? AND wav_sha256=?
                """,
                (
                    status,
                    int(candidate["generation_seed"]),
                    GENERATION_DELIVERY_CLARITY,
                    int(candidate["repair_round"]),
                    str(candidate["policy_hash"]),
                    str(candidate["wav_path"]),
                    normalized_sha256,
                    float(candidate["wav_duration"]),
                    str(candidate["signal_json"]),
                    str(final_metrics.get("transcript", "")),
                    float(final_metrics.get("similarity", 0.0)),
                    float(final_metrics.get("wer", 1.0)),
                    merged_warning,
                    now,
                    int(candidate["segment_id"]),
                    str(candidate["incumbent_sha256"]),
                ),
            )
            if segment_cursor.rowcount != 1:
                raise RuntimeError("segment candidate promotion lost the incumbent CAS")
            candidate_cursor = conn.execute(
                """
                UPDATE segment_candidates
                SET state=?,final_check_id=?,promoted_at=?,updated_at=?
                WHERE id=? AND state=?
                """,
                (
                    SEGMENT_CANDIDATE_PROMOTED,
                    final_quality_check_id,
                    now,
                    now,
                    int(candidate_id),
                    SEGMENT_CANDIDATE_DUAL_PASSED,
                ),
            )
            if candidate_cursor.rowcount != 1:
                raise RuntimeError("segment candidate promotion state CAS failed")
            self._refresh_chapter_counts_conn(conn, int(segment["chapter_id"]))
            return self._candidate_row_conn(conn, candidate_id)

    def finalize_segment_candidate_exhaustion(
        self,
        *,
        segment_id: int,
        policy_hash: str,
        max_repair_rounds: int,
        incumbent_sha256: str,
        trigger_quality_check_id: int,
        error: str,
        warning_code: str,
        final_verdict: str = "fail",
        publish_with_review: bool = False,
        failure_codes: Sequence[str] = (),
    ) -> int:
        normalized_max = int(max_repair_rounds)
        normalized_incumbent = self._normalized_sha256(
            incumbent_sha256,
            "repair exhaustion incumbent checksum",
        )
        normalized_verdict = str(final_verdict).strip().casefold()
        normalized_error = str(error or "").strip()[-8000:]
        normalized_warning_code = str(warning_code or "").strip()
        requested_failure_codes = [
            str(code).strip() for code in failure_codes if str(code).strip()
        ]
        if normalized_max < 0:
            raise ValueError("ASR repair budget must be non-negative")
        if publish_with_review:
            # The repair budget is spent, but the evidence that triggered it does not
            # have the authority to block publication - a locked-name anchor reports
            # review evidence, not proof of a bad take. The candidate ledger is closed
            # exactly as it is for a failure; only the segment's terminal status differs.
            if normalized_verdict != QUALITY_VERDICT_PASS:
                raise ValueError("repair exhaustion review must record a pass verdict")
            if requested_failure_codes:
                raise ValueError("repair exhaustion review cannot carry failure codes")
        elif normalized_verdict not in {"fail", "inconclusive"}:
            raise ValueError("repair exhaustion verdict must be fail or inconclusive")
        if not normalized_error or not normalized_warning_code:
            raise ValueError("repair exhaustion requires an error and warning code")

        with self.transaction() as conn:
            policy = self._require_candidate_policy_conn(conn, policy_hash)
            segment = conn.execute(
                "SELECT * FROM segments WHERE id=?",
                (int(segment_id),),
            ).fetchone()
            if segment is None:
                raise KeyError(f"Unknown segment id: {segment_id}")
            if str(segment["wav_sha256"] or "").casefold() != normalized_incumbent:
                raise RuntimeError("repair exhaustion incumbent checksum CAS failed")
            candidates = list(
                conn.execute(
                    """
                    SELECT * FROM segment_candidates
                    WHERE segment_id=? AND policy_hash=? ORDER BY repair_round
                    """,
                    (int(segment_id), str(policy_hash).strip()),
                )
            )
            ordinary_candidates = [
                candidate
                for candidate in candidates
                if str(candidate["postprocess_profile"]) == POSTPROCESS_PROFILE_NONE
            ]
            tempo_candidates = [
                candidate
                for candidate in candidates
                if str(candidate["postprocess_profile"]) == POSTPROCESS_PROFILE_TEMPO
            ]
            if len(ordinary_candidates) + len(tempo_candidates) != len(candidates):
                raise RuntimeError("repair exhaustion found an unsupported postprocess profile")
            if [int(row["repair_round"]) for row in ordinary_candidates] != list(
                range(normalized_max)
            ):
                raise RuntimeError(
                    "repair exhaustion requires every configured ordinary candidate round"
                )
            if len(tempo_candidates) > 1 or any(
                int(row["repair_round"]) != normalized_max
                for row in tempo_candidates
            ):
                raise RuntimeError("repair exhaustion tempo candidate round is invalid")
            if any(int(row["repair_budget"]) != normalized_max for row in candidates):
                raise RuntimeError("repair exhaustion candidate budget differs from its ledger")
            if any(str(row["state"]) not in SEGMENT_CANDIDATE_FAILURE_STATES for row in candidates):
                raise RuntimeError("repair exhaustion cannot finalize while a candidate remains actionable")
            if any(str(row["incumbent_sha256"]) != normalized_incumbent for row in candidates):
                raise RuntimeError("repair exhaustion candidates do not share the current incumbent")
            if ordinary_candidates:
                eligibility_reason = self._tempo_source_eligibility_reason_conn(
                    conn,
                    ordinary_candidates[-1],
                )
                if eligibility_reason is None and not tempo_candidates:
                    raise RuntimeError(
                        "repair exhaustion requires the eligible tempo-rescue candidate"
                    )
                if eligibility_reason is not None and tempo_candidates:
                    raise RuntimeError(
                        "repair exhaustion found a tempo candidate for an ineligible source"
                    )

            perceptual_review_blocked = False
            for candidate in candidates:
                if str(candidate["state"]) == SEGMENT_CANDIDATE_DUAL_FAILED:
                    perceptual_review_blocked = (
                        self._validated_dual_failed_candidate_conn(
                            conn,
                            candidate,
                        )
                        or perceptual_review_blocked
                    )
            if (
                normalized_warning_code == PERCEPTUAL_NATURALNESS_REVIEW_CODE
                and not perceptual_review_blocked
            ):
                raise RuntimeError(
                    "perceptual exhaustion label lacks a durable reviewed candidate"
                )
            if (
                normalized_warning_code == "ASR_MISMATCH_UNRESOLVED"
                and perceptual_review_blocked
            ):
                raise RuntimeError(
                    "ASR exhaustion label contradicts the durable perceptual blocker"
                )

            trigger = conn.execute(
                "SELECT * FROM quality_checks WHERE id=?",
                (int(trigger_quality_check_id),),
            ).fetchone()
            if trigger is None:
                raise KeyError(f"Unknown quality check id: {trigger_quality_check_id}")
            if (
                str(trigger["scope"]) != QUALITY_SCOPE_SEGMENT
                or str(trigger["stage"]) != SEGMENT_AUDIO_QUALITY_STAGE
                or int(trigger["segment_id"] or -1) != int(segment_id)
                or str(trigger["artifact_sha256"]).casefold() != normalized_incumbent
                or str(trigger["policy_hash"]) != str(policy_hash).strip()
                or str(trigger["verdict"]) != "repair"
            ):
                raise RuntimeError("repair trigger does not belong to the retained incumbent artifact")
            trigger_metrics = self._json_object(trigger["metrics_json"], "repair trigger metrics")
            try:
                trigger_failure_codes = json.loads(str(trigger["failure_codes_json"] or "[]"))
            except (TypeError, json.JSONDecodeError):
                trigger_failure_codes = []
            merged_failure_codes: list[str] = []
            for code in [*trigger_failure_codes, *requested_failure_codes]:
                normalized_code = str(code).strip()
                if normalized_code and normalized_code not in merged_failure_codes:
                    merged_failure_codes.append(normalized_code)
            summaries = [self._candidate_summary(row) for row in candidates]
            final_metrics = {
                **trigger_metrics,
                "repair_trigger_reason": trigger_metrics.get("reason"),
                "reason": normalized_warning_code,
                "repair_exhausted": True,
                "repair_trigger_quality_check_id": int(trigger_quality_check_id),
                "candidate_rounds_configured": normalized_max,
                "candidate_attempts": summaries,
                "incumbent_sha256": normalized_incumbent,
                "repair_exhaustion_verdict": normalized_verdict,
                "repair_exhaustion_error": normalized_error,
                "repair_exhaustion_warning_code": normalized_warning_code,
                "repair_exhaustion_failure_codes": merged_failure_codes,
            }
            final_metrics_json = json.dumps(final_metrics, ensure_ascii=False, sort_keys=True)
            failure_codes_json = json.dumps(merged_failure_codes, ensure_ascii=False)
            existing = list(
                conn.execute(
                    """
                    SELECT * FROM quality_checks
                    WHERE scope=? AND stage=? AND segment_id=? AND artifact_sha256=?
                      AND policy_hash=?
                    ORDER BY id DESC
                    """,
                    (
                        QUALITY_SCOPE_SEGMENT,
                        SEGMENT_AUDIO_QUALITY_STAGE,
                        int(segment_id),
                        normalized_incumbent,
                        str(policy_hash).strip(),
                    ),
                )
            )
            for check in existing:
                metrics = self._json_object(check["metrics_json"], "existing repair exhaustion metrics")
                if (
                    bool(metrics.get("repair_exhausted", False))
                    and int(metrics.get("repair_trigger_quality_check_id", -1))
                    == int(trigger_quality_check_id)
                ):
                    if (
                        str(check["verdict"]) == normalized_verdict
                        and str(check["metrics_json"]) == final_metrics_json
                        and str(check["failure_codes_json"]) == failure_codes_json
                        and str(check["repair_action"] or "")
                        == SEGMENT_CANDIDATE_EXHAUSTION_ACTION
                    ):
                        return int(check["id"])
                    raise RuntimeError("repair exhaustion replay payload differs")
            attempt_row = conn.execute(
                """
                SELECT MAX(attempt) FROM quality_checks
                WHERE scope=? AND stage=? AND segment_id=? AND policy_hash=?
                """,
                (
                    QUALITY_SCOPE_SEGMENT,
                    SEGMENT_AUDIO_QUALITY_STAGE,
                    int(segment_id),
                    str(policy_hash).strip(),
                ),
            ).fetchone()
            attempt = int(attempt_row[0] or 0) + 1
            cursor = conn.execute(
                """
                INSERT INTO quality_checks(
                    scope,stage,segment_id,chapter_id,artifact_sha256,
                    policy_hash,policy_version,verdict,metrics_json,
                    failure_codes_json,repair_action,attempt,created_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    QUALITY_SCOPE_SEGMENT,
                    SEGMENT_AUDIO_QUALITY_STAGE,
                    int(segment_id),
                    None,
                    normalized_incumbent,
                    str(policy_hash).strip(),
                    int(policy["policy_version"]),
                    normalized_verdict,
                    final_metrics_json,
                    failure_codes_json,
                    SEGMENT_CANDIDATE_EXHAUSTION_ACTION,
                    attempt,
                    time.time(),
                ),
            )
            retained_warning = self._without_audio_attempt_warnings(
                str(segment["warning_code"]) if segment["warning_code"] else None
            )
            merged_warning = self._merge_warning_codes(retained_warning, normalized_warning_code)
            segment_cursor = conn.execute(
                """
                UPDATE segments SET status=?,asr_text=?,asr_similarity=?,asr_wer=?,
                    warning_code=?,error=?,updated_at=?
                WHERE id=? AND wav_sha256=?
                """,
                (
                    (
                        SegmentStatus.VERIFIED.value
                        if publish_with_review
                        else SegmentStatus.FAILED.value
                    ),
                    str(trigger_metrics.get("transcript", "")),
                    float(trigger_metrics.get("similarity", 0.0)),
                    float(trigger_metrics.get("wer", 1.0)),
                    merged_warning,
                    "" if publish_with_review else normalized_error,
                    time.time(),
                    int(segment_id),
                    normalized_incumbent,
                ),
            )
            if segment_cursor.rowcount != 1:
                raise RuntimeError("repair exhaustion lost the incumbent CAS")
            self._refresh_chapter_counts_conn(conn, int(segment["chapter_id"]))
            return int(cursor.lastrowid)

    def latest_quality_check(
        self,
        *,
        scope: str,
        stage: str,
        segment_id: int | None = None,
        chapter_id: int | None = None,
        current_policy_only: bool = True,
    ) -> sqlite3.Row | None:
        normalized_scope = str(scope).strip().casefold()
        if normalized_scope not in QUALITY_SCOPES:
            raise ValueError(f"Unsupported quality scope: {scope}")
        if normalized_scope == QUALITY_SCOPE_SEGMENT:
            if segment_id is None or chapter_id is not None:
                raise ValueError("segment quality lookup requires only segment_id")
            subject_clause = "quality_checks.segment_id=?"
            subject_id = int(segment_id)
        else:
            if chapter_id is None or segment_id is not None:
                raise ValueError("chapter quality lookup requires only chapter_id")
            subject_clause = "quality_checks.chapter_id=?"
            subject_id = int(chapter_id)
        policy_clause = " AND quality_policies.active=1" if current_policy_only else ""
        with self.connect() as conn:
            return conn.execute(
                f"""
                SELECT quality_checks.*
                FROM quality_checks
                JOIN quality_policies USING(policy_hash)
                WHERE quality_checks.scope=?
                  AND quality_checks.stage=?
                  AND {subject_clause}
                  {policy_clause}
                ORDER BY quality_checks.id DESC
                LIMIT 1
                """,
                (normalized_scope, str(stage).strip(), subject_id),
            ).fetchone()

    def latest_segment_quality_checks(
        self,
        stage: str,
        *,
        current_policy_only: bool = True,
    ) -> dict[int, sqlite3.Row]:
        normalized_stage = str(stage).strip()
        if not normalized_stage:
            raise ValueError("segment quality lookup stage must not be empty")
        policy_clause = " AND quality_policies.active=1" if current_policy_only else ""
        with self.connect() as conn:
            rows = conn.execute(
                f"""
                SELECT quality_checks.*
                FROM quality_checks
                JOIN quality_policies
                  ON quality_policies.policy_hash=quality_checks.policy_hash
                 AND quality_policies.policy_version=quality_checks.policy_version
                WHERE quality_checks.scope=?
                  AND quality_checks.stage=?
                  {policy_clause}
                ORDER BY quality_checks.id
                """,
                (QUALITY_SCOPE_SEGMENT, normalized_stage),
            )
            latest: dict[int, sqlite3.Row] = {}
            for row in rows:
                if row["segment_id"] is not None:
                    latest[int(row["segment_id"])] = row
            return latest

    @staticmethod
    def _quality_check_is_current_pass_conn(
        conn: sqlite3.Connection,
        *,
        scope: str,
        stage: str,
        artifact_sha256: str,
        segment_id: int | None = None,
        chapter_id: int | None = None,
    ) -> bool:
        if scope == QUALITY_SCOPE_SEGMENT:
            subject_clause = "quality_checks.segment_id=?"
            subject_id = segment_id
        else:
            subject_clause = "quality_checks.chapter_id=?"
            subject_id = chapter_id
        if subject_id is None:
            return False
        row = conn.execute(
            f"""
            SELECT quality_checks.verdict
            FROM quality_checks
            JOIN quality_policies
              ON quality_policies.policy_hash=quality_checks.policy_hash
             AND quality_policies.policy_version=quality_checks.policy_version
            WHERE quality_policies.active=1
              AND quality_checks.scope=?
              AND quality_checks.stage=?
              AND quality_checks.artifact_sha256=?
              AND {subject_clause}
            ORDER BY quality_checks.id DESC
            LIMIT 1
            """,
            (scope, stage, artifact_sha256, int(subject_id)),
        ).fetchone()
        return bool(row and str(row["verdict"]) == QUALITY_VERDICT_PASS)

    def segment_audio_is_current_qa_verified(
        self,
        segment_id: int,
        artifact_sha256: str,
        stage: str = SEGMENT_AUDIO_QUALITY_STAGE,
    ) -> bool:
        normalized_sha256 = str(artifact_sha256).strip()
        normalized_stage = str(stage).strip()
        if not normalized_sha256 or not normalized_stage:
            return False
        with self.connect() as conn:
            segment = conn.execute(
                "SELECT wav_sha256 FROM segments WHERE id=?",
                (int(segment_id),),
            ).fetchone()
            if segment is None or str(segment["wav_sha256"] or "") != normalized_sha256:
                return False
            return self._quality_check_is_current_pass_conn(
                conn,
                scope=QUALITY_SCOPE_SEGMENT,
                stage=normalized_stage,
                artifact_sha256=normalized_sha256,
                segment_id=int(segment_id),
            )

    def chapter_segments_have_current_audio_qa(
        self,
        chapter_id: int,
        stage: str = SEGMENT_AUDIO_QUALITY_STAGE,
    ) -> bool:
        normalized_stage = str(stage).strip()
        if not normalized_stage:
            return False
        with self.connect() as conn:
            rows = list(
                conn.execute(
                    "SELECT id,status,wav_sha256 FROM segments WHERE chapter_id=? ORDER BY seq",
                    (int(chapter_id),),
                )
            )
            if not rows:
                return False
            for row in rows:
                if str(row["status"]) not in {
                    SegmentStatus.VERIFIED.value,
                    SegmentStatus.WARNING.value,
                }:
                    return False
                artifact_sha256 = str(row["wav_sha256"] or "").strip()
                if not artifact_sha256 or not self._quality_check_is_current_pass_conn(
                    conn,
                    scope=QUALITY_SCOPE_SEGMENT,
                    stage=normalized_stage,
                    artifact_sha256=artifact_sha256,
                    segment_id=int(row["id"]),
                ):
                    return False
            return True

    def chapter_artifact_is_current_qa_verified(
        self,
        chapter_index: int,
        stage: str = CHAPTER_POST_ENCODE_QUALITY_STAGE,
    ) -> bool:
        artifact_key = f"chapter_mp3:{int(chapter_index)}"
        normalized_stage = str(stage).strip()
        if not normalized_stage:
            return False
        with self.connect() as conn:
            artifact = conn.execute(
                "SELECT * FROM artifacts WHERE artifact_key=?",
                (artifact_key,),
            ).fetchone()
            chapter = conn.execute(
                "SELECT id FROM chapters WHERE chapter_index=?",
                (int(chapter_index),),
            ).fetchone()
            policy = conn.execute(
                "SELECT * FROM quality_policies WHERE active=1"
            ).fetchone()
            if (
                artifact is None
                or chapter is None
                or policy is None
                or str(artifact["kind"]) != "chapter_mp3"
                or not bool(artifact["verified"])
                or not str(artifact["sha256"] or "").strip()
            ):
                return False
            try:
                metadata = json.loads(str(artifact["metadata_json"] or "{}"))
                quality = metadata.get("quality") if isinstance(metadata, dict) else None
                metadata_passes = bool(
                    isinstance(quality, dict)
                    and str(quality.get("policy_hash", "")) == str(policy["policy_hash"])
                    and int(quality.get("policy_version", -1)) == int(policy["policy_version"])
                    and str(quality.get("verdict", "")).casefold() == QUALITY_VERDICT_PASS
                )
            except (TypeError, ValueError, json.JSONDecodeError):
                return False
            return bool(
                metadata_passes
                and self._quality_check_is_current_pass_conn(
                    conn,
                    scope=QUALITY_SCOPE_CHAPTER,
                    stage=normalized_stage,
                    artifact_sha256=str(artifact["sha256"]),
                    chapter_id=int(chapter["id"]),
                )
            )

    def clear_all_worker_leases(self) -> int:
        with self.connect() as conn:
            cursor = conn.execute("DELETE FROM worker_leases")
            return int(cursor.rowcount)

    def register_artifact(
        self,
        *,
        artifact_key: str,
        kind: str,
        path: Path,
        sha256: str | None,
        verified: bool,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        now = time.time()
        size = path.stat().st_size if path.exists() else None
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO artifacts(
                    artifact_key,kind,path,sha256,size_bytes,verified,metadata_json,created_at,updated_at
                ) VALUES(?,?,?,?,?,?,?,?,?)
                ON CONFLICT(artifact_key) DO UPDATE SET
                    path=excluded.path,sha256=excluded.sha256,size_bytes=excluded.size_bytes,
                    verified=excluded.verified,metadata_json=excluded.metadata_json,updated_at=excluded.updated_at
                """,
                (
                    artifact_key,
                    kind,
                    str(path.resolve()),
                    sha256,
                    size,
                    1 if verified else 0,
                    json.dumps(metadata, ensure_ascii=False) if metadata else None,
                    now,
                    now,
                ),
            )

    def rewrite_speaker(self, old_name: str, canonical_name: str) -> int:
        with self.connect() as conn:
            cursor = conn.execute(
                "UPDATE segments SET speaker=?,updated_at=? WHERE speaker=?",
                (canonical_name, time.time(), old_name),
            )
            return int(cursor.rowcount)

    def rewrite_segment_speakers(
        self,
        segment_ids: list[int],
        *,
        speaker: str,
        gender: str,
        age: str,
    ) -> int:
        if not segment_ids:
            return 0
        normalized_segment_ids = [int(segment_id) for segment_id in segment_ids]
        if len(normalized_segment_ids) != len(set(normalized_segment_ids)):
            raise ValueError("Segment speaker rewrite IDs must be unique")
        placeholders = ",".join("?" for _segment_id in segment_ids)
        with self.transaction() as conn:
            rows = list(
                conn.execute(
                    f"""
                    SELECT id,kind,emotion,intensity,pace,volume,analysis_notes
                    FROM segments WHERE id IN ({placeholders}) ORDER BY id
                    """,
                    normalized_segment_ids,
                )
            )
            if len(rows) != len(normalized_segment_ids):
                raise KeyError("Segment speaker rewrite contains an unknown segment ID")
            notes_by_id: dict[int, str] = {}
            for row in rows:
                current_delivery = {
                    "kind": str(row["kind"]),
                    "emotion": str(row["emotion"]),
                    "intensity": int(row["intensity"]),
                    "pace": str(row["pace"]),
                    "volume": str(row["volume"]),
                    "personality_hint": "",
                    "notes": str(row["analysis_notes"] or ""),
                }
                if current_delivery["kind"] != "dialogue":
                    raise ValueError("Segment speaker rewrite requires dialogue segments")
                if current_delivery["notes"]:
                    analysis_note_markers(current_delivery)
                notes_by_id[int(row["id"])] = canonical_analysis_note(current_delivery)
            now = time.time()
            rewritten = 0
            for segment_id in normalized_segment_ids:
                cursor = conn.execute(
                    """
                    UPDATE segments SET speaker=?,gender=?,age=?,analysis_notes=?,
                        canonical_character_id=NULL,voice_profile_id=NULL,updated_at=?
                    WHERE id=?
                    """,
                    (
                        speaker,
                        gender,
                        age,
                        notes_by_id[segment_id],
                        now,
                        segment_id,
                    ),
                )
                if cursor.rowcount != 1:
                    raise RuntimeError("Segment speaker rewrite CAS failed")
                rewritten += 1
            return rewritten

    def normalize_thought_speakers(self) -> int:
        """Inner monologue keeps the thinker's identity; only the unattributed is reset.

        This used to rewrite every kind='thought' row to the narrator and clear its voice,
        so a character's inner voice was read by someone else entirely. A thought belongs
        to whoever is thinking it and is read in their voice. Rows the analysis could not
        attribute still fall back to the narrator, because an unidentified thinker has no
        voice to use.
        """
        with self.connect() as conn:
            cursor = conn.execute(
                """
                UPDATE segments SET speaker='NARRATOR',gender='unknown',age='unknown',
                    canonical_character_id=NULL,voice_profile_id=NULL,updated_at=?
                WHERE kind='thought' AND speaker IN ('UNKNOWN','')
                """,
                (time.time(),),
            )
            return int(cursor.rowcount)

    def set_character_for_speaker(self, speaker: str, character_id: int) -> int:
        with self.connect() as conn:
            cursor = conn.execute(
                "UPDATE segments SET canonical_character_id=?,updated_at=? WHERE speaker=?",
                (character_id, time.time(), speaker),
            )
            return int(cursor.rowcount)

    def set_voice_for_character_segments(self, character_id: int, profile_id: int) -> int:
        with self.connect() as conn:
            cursor = conn.execute(
                "UPDATE segments SET voice_profile_id=?,updated_at=? WHERE canonical_character_id=?",
                (profile_id, time.time(), character_id),
            )
            return int(cursor.rowcount)

    def set_character_and_voice_for_segments(
        self,
        segment_ids: list[int],
        character_id: int,
        profile_id: int,
    ) -> int:
        updated = 0
        now = time.time()
        with self.transaction() as conn:
            for offset in range(0, len(segment_ids), 500):
                batch = segment_ids[offset : offset + 500]
                if not batch:
                    continue
                placeholders = ",".join("?" for _ in batch)
                cursor = conn.execute(
                    f"""
                    UPDATE segments SET canonical_character_id=?,voice_profile_id=?,updated_at=?
                    WHERE id IN ({placeholders})
                    """,
                    (character_id, profile_id, now, *batch),
                )
                updated += int(cursor.rowcount)
        return updated

    def integrity_check(self) -> list[str]:
        errors: list[str] = []
        with self.connect() as conn:
            result = conn.execute("PRAGMA integrity_check").fetchall()
            for row in result:
                if str(row[0]).lower() != "ok":
                    errors.append(str(row[0]))
            fk = conn.execute("PRAGMA foreign_key_check").fetchall()
            errors.extend(f"foreign_key_check: {tuple(row)}" for row in fk)
        return errors
