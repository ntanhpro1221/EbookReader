from __future__ import annotations

import copy
import json
import sqlite3
from contextlib import closing
from pathlib import Path

import pytest

from ebook_reader.database import (
    ANALYSIS_CHAPTER_HEADING_DELIVERY,
    ANALYSIS_HOST_AFFECT_POLICY_VERSION,
    ANALYSIS_HOST_SEMANTIC_POLICY_VERSION,
    ANALYSIS_HOST_STRUCTURAL_POLICY_VERSION,
    CHAPTER_POST_ENCODE_QUALITY_STAGE,
    CONTINUED_DIALOGUE_LOCK_NOTE,
    GENERATION_DELIVERY_CLARITY,
    GENERATION_DELIVERY_PRIMARY,
    QUALITY_SCOPE_CHAPTER,
    QUALITY_SCOPE_SEGMENT,
    QUALITY_VERDICT_PASS,
    SCHEMA_VERSION,
    SEGMENT_ASR_DECODE_QUALITY_STAGE,
    SEGMENT_AUDIO_QUALITY_STAGE,
    SEGMENT_PERCEPTUAL_QUALITY_STAGE,
    ProjectDB,
    analysis_source_has_recalled_persistent_fear,
    analysis_source_has_stunned_blank_mind,
    canonical_analysis_note,
)
from ebook_reader.io_utils import sha256_file, sha256_text
from ebook_reader.models import CONTEXTUAL_ENGLISH_NAME_PRONUNCIATION_SOURCE
from ebook_reader.config import build_settings
from ebook_reader.tts import TTSCoordinator


ANALYSIS_MODEL_NAME = "qwen3:8b"
ANALYSIS_MODEL_DIGEST = "sha256:analysis-model"
ANALYSIS_MODEL_COMMIT = {
    "analysis_model_name": ANALYSIS_MODEL_NAME,
    "analysis_model_digest": ANALYSIS_MODEL_DIGEST,
}
ANALYSIS_POLICY_FINGERPRINT = "director-policy-v2"
ANALYSIS_GROUP_FINGERPRINT = "group-source-v1"
ANALYSIS_CONTEXT_HASH = "group-context-v1"
RECALLED_PERSISTENT_FEAR_TEXT = (
    "Giấc mơ này chân thực tới dị thường, khiến cho Hạ Phong đến giờ nghĩ lại "
    "vẫn tim đập chân run. Cộng thêm việc không cảm nhận thấy sự tồn tại của "
    "ngọn lửa, cậu bèn ngồi thừ người ra, một lúc lâu vẫn chưa hoàn hồn."
)
STUNNED_BLANK_MIND_TEXT = (
    "Nhưng tới khi Hạ Phong nhìn ra phía trước, chuẩn bị đứng lên và thu lại sách "
    "tham khảo để trở về ký túc xá, một cảnh tượng kỳ lạ không sao tưởng tượng "
    "được bỗng đập thẳng vào mắt cậu. Giống như thể bị một cây chùy lớn nện vào "
    "đầu, cậu đực mặt ra, đầu óc một mảng trắng xóa."
)
DIRECT_NARRATION_AFFECT_LOCK_CASES = (
    (
        RECALLED_PERSISTENT_FEAR_TEXT,
        "narration_recalled_persistent_fear",
        "recalled_persistent_fear",
        ("afraid",),
        "afraid",
        "surprised",
    ),
    (
        STUNNED_BLANK_MIND_TEXT,
        "narration_stunned_blank_mind",
        "stunned_blank_mind",
        ("surprised",),
        "surprised",
        "afraid",
    ),
)


def _canonical_analysis_data(**overrides: object) -> dict:
    data = {
        "kind": "narration",
        "speaker": "NARRATOR",
        "gender": "unknown",
        "age": "unknown",
        "emotion": "neutral",
        "intensity": 1,
        "pace": "normal",
        "volume": "normal",
        "confidence": 0.9,
        "personality_hint": "",
        "notes": "",
    }
    data.update(overrides)
    data["notes"] = canonical_analysis_note(data)
    return data


def _segment_db(tmp_path: Path) -> tuple[ProjectDB, int]:
    db = ProjectDB(tmp_path / "project.sqlite3")
    db.initialize_book(
        title="Book",
        project_root=tmp_path,
        settings={},
        settings_hash="settings",
        input_manifest_hash="manifest",
    )
    chapter_id = db.ensure_chapters(
        [
            {
                "chapter_index": 1,
                "title": "One",
                "input_path": tmp_path / "one.txt",
                "input_sha256": "source",
                "input_size": 1,
                "output_mp3": tmp_path / "one.mp3",
            }
        ]
    )[0]
    db.replace_chapter_segments(
        chapter_id,
        [
            {
                "stable_id": "c1s1",
                "seq": 0,
                "text": "Text",
                "text_sha256": "text",
                "kind_hint": "narration",
            }
        ],
    )
    return db, int(db.list_segments()[0]["id"])


def _analysis_batch_db(
    tmp_path: Path,
    *,
    lock_model: bool = True,
    texts: tuple[str, ...] = ("Text 1", "Text 2"),
    kind_hints: tuple[str, ...] | None = None,
) -> tuple[ProjectDB, list[dict]]:
    resolved_kind_hints = kind_hints or tuple("narration" for _text in texts)
    if len(resolved_kind_hints) != len(texts):
        raise ValueError("Analysis test texts and kind hints must have equal lengths")
    db = ProjectDB(tmp_path / "project.sqlite3")
    db.initialize_book(
        title="Book",
        project_root=tmp_path,
        settings={},
        settings_hash="settings",
        input_manifest_hash="manifest",
    )
    chapter_id = db.ensure_chapters(
        [
            {
                "chapter_index": 1,
                "title": "One",
                "input_path": tmp_path / "one.txt",
                "input_sha256": "source",
                "input_size": 1,
                "output_mp3": tmp_path / "one.mp3",
            }
        ]
    )[0]
    db.replace_chapter_segments(
        chapter_id,
        [
            {
                "stable_id": f"c1s{index}",
                "seq": index - 1,
                "text": text,
                "text_sha256": sha256_text(text),
                "kind_hint": kind_hint,
            }
            for index, (text, kind_hint) in enumerate(
                zip(texts, resolved_kind_hints, strict=True),
                1,
            )
        ],
    )
    if lock_model:
        db.lock_analysis_model(ANALYSIS_MODEL_NAME, ANALYSIS_MODEL_DIGEST)
    return db, [dict(row) for row in db.list_segments()]


def _analysis_acceptance_envelope(
    source_rows: list[dict],
    *,
    emotion: str = "neutral",
) -> dict:
    segments = []
    critic_rows = []
    for index, row in enumerate(source_rows, 1):
        data = {
            "kind": "narration",
            "speaker": "NARRATOR",
            "gender": "unknown",
            "age": "unknown",
            "emotion": emotion,
            "intensity": 1,
            "pace": "normal",
            "volume": "normal",
            "confidence": 0.9,
            "personality_hint": "",
            "notes": "",
        }
        data["notes"] = canonical_analysis_note(data)
        segments.append(
            {
                "segment_id": int(row["id"]),
                "stable_id": str(row["stable_id"]),
                "text_sha256": str(row["text_sha256"]),
                "data": data,
            }
        )
        critic_rows.append(
            {
                "id": f"S{index:03d}",
                "paragraph": int(row["paragraph_index"]),
                "hint": str(row["kind_hint"]),
                "source_role": "content",
                "context_policy": "adjacent_context",
                "host_locked_fields": {},
                "previous_text": "",
                "text": str(row["text"]),
                "next_text": "",
                "candidate": {
                    key: data[key]
                    for key in ("kind", "speaker", "emotion", "intensity", "pace", "volume")
                },
                "batch_signature_count": len(source_rows),
            }
        )
    return {
        "segments": segments,
        "pronunciations": [],
        "critic_rows": critic_rows,
    }


def _canonical_hash(value: object) -> str:
    return sha256_text(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    )


def _deterministic_analysis_issues(
    source_rows: list[dict],
    clearance: dict | None = None,
) -> dict:
    del source_rows
    return {
        "host_affect_clearance": clearance,
        "semantic_issues": [],
    }


def _refresh_analysis_note(envelope: dict, index: int) -> None:
    data = envelope["segments"][index]["data"]
    data["notes"] = canonical_analysis_note(data)


def _accepted_critic_contract() -> dict:
    return {
        "policy_version": "second_pass_v1",
        "confidence_cap": 0.95,
        "seed": 11,
        "temperature": 0.0,
    }


def _accepted_critic_evidence(envelope: dict) -> dict:
    rows = []
    for segment, critic_row in zip(
        envelope["segments"],
        envelope["critic_rows"],
        strict=True,
    ):
        candidate = dict(critic_row["candidate"])
        rows.append(
            {
                "stable_id": segment["stable_id"],
                "text_sha256": segment["text_sha256"],
                "candidate": candidate,
                "critic": {
                    **candidate,
                    "accept": True,
                    "rationale": "Đồng ý với delivery theo đúng bằng chứng nguồn.",
                    "evidence_quote": critic_row["text"],
                    "confidence": segment["data"]["confidence"],
                },
                "field_deltas": [],
                "derived_confidence": segment["data"]["confidence"],
                "effective_accept": True,
            }
        )
    return {
        "candidate_hash": _canonical_hash(envelope["critic_rows"]),
        "critic_contract": _accepted_critic_contract(),
        "segments": rows,
    }


def _chapter_heading_envelope(source_rows: list[dict]) -> dict:
    envelope = _analysis_acceptance_envelope(source_rows)
    heading_segment = envelope["segments"][0]
    heading_row = envelope["critic_rows"][0]
    for field, value in ANALYSIS_CHAPTER_HEADING_DELIVERY.items():
        heading_segment["data"][field] = value
    heading_segment["data"]["notes"] = canonical_analysis_note(
        heading_segment["data"]
    )
    heading_row["source_role"] = "chapter_heading"
    heading_row["context_policy"] = "target_only"
    heading_row["host_locked_fields"] = dict(ANALYSIS_CHAPTER_HEADING_DELIVERY)
    heading_row["previous_text"] = ""
    heading_row["next_text"] = ""
    heading_row["candidate"] = dict(ANALYSIS_CHAPTER_HEADING_DELIVERY)
    return envelope


def _chapter_heading_clearance(envelope: dict) -> dict:
    segment = envelope["segments"][0]
    return {
        "host_affect_clearance": {
            "policy_version": ANALYSIS_HOST_AFFECT_POLICY_VERSION,
            "status": "cleared",
            "candidate_hash": _canonical_hash(envelope["critic_rows"]),
            "checked_segment_count": len(envelope["segments"]),
            "matched_rule_count": 0,
            "evidence": [],
            "structural_locks": [
                {
                    "policy_version": ANALYSIS_HOST_STRUCTURAL_POLICY_VERSION,
                    "stable_id": segment["stable_id"],
                    "text_sha256": segment["text_sha256"],
                    "source_role": "chapter_heading",
                    "context_policy": "target_only",
                    "locked_fields": dict(ANALYSIS_CHAPTER_HEADING_DELIVERY),
                    "generator_fields": {
                        "emotion": "afraid",
                        "intensity": 2,
                        "pace": "fast",
                    },
                }
            ],
            "semantic_locks": [],
        }
    }


def _heading_override_evidence(envelope: dict) -> dict:
    evidence = _accepted_critic_evidence(envelope)
    segment = envelope["segments"][0]
    item = evidence["segments"][0]
    critic = item["critic"]
    critic.update(
        {
            "accept": False,
            "emotion": "afraid",
            "intensity": 2,
            "pace": "fast",
            "rationale": "Tiêu đề có từ ngữ gợi cảm giác nguy hiểm.",
            "evidence_quote": envelope["critic_rows"][0]["text"],
        }
    )
    deltas = [
        "emotion:neutral->afraid",
        "intensity:0->2",
        "pace:normal->fast",
    ]
    item["field_deltas"] = deltas
    item["host_structural_override"] = {
        "policy_version": ANALYSIS_HOST_STRUCTURAL_POLICY_VERSION,
        "stable_id": segment["stable_id"],
        "text_sha256": segment["text_sha256"],
        "source_role": "chapter_heading",
        "context_policy": "target_only",
        "locked_fields": dict(ANALYSIS_CHAPTER_HEADING_DELIVERY),
        "raw_accept": False,
        "raw_field_deltas": deltas,
    }
    return evidence


def _semantic_lock_envelope(
    source_rows: list[dict],
    *,
    locked_index: int = 0,
    candidate_emotion: str = "afraid",
) -> dict:
    envelope = _analysis_acceptance_envelope(source_rows)
    for index, source_row in enumerate(source_rows):
        source_kind = str(source_row["kind_hint"])
        envelope["segments"][index]["data"]["kind"] = source_kind
        _refresh_analysis_note(envelope, index)
        envelope["critic_rows"][index]["candidate"]["kind"] = source_kind
    segment = envelope["segments"][locked_index]
    critic_row = envelope["critic_rows"][locked_index]
    segment["data"]["emotion"] = candidate_emotion
    segment["data"]["intensity"] = 2
    _refresh_analysis_note(envelope, locked_index)
    critic_row["candidate"]["emotion"] = candidate_emotion
    critic_row["candidate"]["intensity"] = 2
    critic_row["host_locked_fields"] = {"emotion": candidate_emotion}
    return envelope


def _host_semantic_clearance(
    envelope: dict,
    *,
    locked_index: int = 0,
    rule: str = "respiratory_injury_with_consciousness_loss",
    cue_class: str = "physical_collapse",
    allowed_emotions: list[str] | None = None,
    related_index: int | None = None,
) -> dict:
    segment = envelope["segments"][locked_index]
    critic_row = envelope["critic_rows"][locked_index]
    related_segment = (
        envelope["segments"][related_index]
        if related_index is not None
        else None
    )
    semantic_lock = {
        "policy_version": ANALYSIS_HOST_SEMANTIC_POLICY_VERSION,
        "stable_id": segment["stable_id"],
        "text_sha256": segment["text_sha256"],
        "source_role": "content",
        "field": "emotion",
        "rule": rule,
        "cue_class": cue_class,
        "candidate_emotion": critic_row["candidate"]["emotion"],
        "allowed_emotions": allowed_emotions or ["afraid", "tired"],
        "related_stable_id": (
            related_segment["stable_id"]
            if related_segment is not None
            else ""
        ),
        "related_text_sha256": (
            related_segment["text_sha256"]
            if related_segment is not None
            else ""
        ),
    }
    semantic_evidence = {
        "stable_id": semantic_lock["stable_id"],
        "text_sha256": semantic_lock["text_sha256"],
        "rule": semantic_lock["rule"],
        "cue_class": semantic_lock["cue_class"],
        "candidate_emotion": semantic_lock["candidate_emotion"],
        "allowed_emotions": list(semantic_lock["allowed_emotions"]),
        "outcome": "pass",
    }
    if semantic_lock["related_stable_id"]:
        semantic_evidence["related_stable_id"] = semantic_lock["related_stable_id"]
    if semantic_lock["related_text_sha256"]:
        semantic_evidence["related_text_sha256"] = semantic_lock[
            "related_text_sha256"
        ]
    return {
        "host_affect_clearance": {
            "policy_version": ANALYSIS_HOST_AFFECT_POLICY_VERSION,
            "status": "cleared",
            "candidate_hash": _canonical_hash(envelope["critic_rows"]),
            "checked_segment_count": len(envelope["segments"]),
            "matched_rule_count": 1,
            "evidence": [semantic_evidence],
            "structural_locks": [],
            "semantic_locks": [semantic_lock],
        }
    }


def _merge_host_semantic_clearances(*clearances: dict) -> dict:
    merged = copy.deepcopy(clearances[0])
    host = merged["host_affect_clearance"]
    for clearance in clearances[1:]:
        incoming = clearance["host_affect_clearance"]
        assert incoming["candidate_hash"] == host["candidate_hash"]
        assert incoming["checked_segment_count"] == host["checked_segment_count"]
        host["evidence"].extend(copy.deepcopy(incoming["evidence"]))
        host["semantic_locks"].extend(copy.deepcopy(incoming["semantic_locks"]))
    host["matched_rule_count"] = len(host["semantic_locks"])
    return merged


def _semantic_override_evidence(
    envelope: dict,
    clearance: dict,
    *,
    locked_index: int = 0,
    corrected_emotion: str = "neutral",
) -> dict:
    evidence = _accepted_critic_evidence(envelope)
    item = evidence["segments"][locked_index]
    lock = clearance["host_affect_clearance"]["semantic_locks"][0]
    candidate_emotion = item["candidate"]["emotion"]
    item["critic"].update(
        {
            "accept": False,
            "emotion": corrected_emotion,
            "rationale": "Critic đề xuất cảm xúc khác với ràng buộc host.",
        }
    )
    deltas = [f"emotion:{candidate_emotion}->{corrected_emotion}"]
    item["field_deltas"] = deltas
    item["host_semantic_override"] = {
        "policy_version": ANALYSIS_HOST_SEMANTIC_POLICY_VERSION,
        "stable_id": item["stable_id"],
        "text_sha256": item["text_sha256"],
        "rule": lock["rule"],
        "field": "emotion",
        "candidate_value": candidate_emotion,
        "allowed_values": list(lock["allowed_emotions"]),
        "raw_accept": False,
        "raw_field_deltas": deltas,
    }
    return evidence


def _allocate_analysis_candidate(
    db: ProjectDB,
    source_rows: list[dict],
    *,
    context_hash: str = ANALYSIS_CONTEXT_HASH,
    candidate: dict | None = None,
    deterministic_issues: dict | None = None,
    critic_max_attempts: int = 2,
):
    envelope = candidate or _analysis_acceptance_envelope(source_rows)
    return db.allocate_or_resume_analysis_candidate(
        policy_fingerprint=ANALYSIS_POLICY_FINGERPRINT,
        model_name=ANALYSIS_MODEL_NAME,
        model_digest=ANALYSIS_MODEL_DIGEST,
        group_fingerprint=ANALYSIS_GROUP_FINGERPRINT,
        context_hash=context_hash,
        candidate_hash=_canonical_hash(envelope["critic_rows"]),
        candidate=envelope,
        generator_contract={"attempt": 1, "seed": 101},
        deterministic_issues=(
            _deterministic_analysis_issues(source_rows)
            if deterministic_issues is None
            else _deterministic_analysis_issues(
                source_rows,
                deterministic_issues.get("host_affect_clearance"),
            )
        ),
        critic_max_attempts=critic_max_attempts,
    )


def _candidate_db(tmp_path: Path) -> tuple[ProjectDB, int, str, Path]:
    db, segment_id = _segment_db(tmp_path)
    profile_id = db.upsert_voice_profile(
        {
            "voice_key": "candidate-narrator",
            "engine": "vieneu",
            "preset_name": "Candidate Voice",
            "description": "Candidate test voice",
            "seed": 7,
            "pitch_semitones": 0,
            "status": "ready",
        }
    )
    with db.connect() as conn:
        conn.execute(
            "UPDATE segments SET voice_profile_id=? WHERE id=?",
            (profile_id, segment_id),
        )
    incumbent_sha256 = "a" * 64
    incumbent_path = tmp_path / "incumbent.wav"
    db.mark_signal_passed(
        segment_id,
        wav_path=incumbent_path,
        wav_sha256=incumbent_sha256,
        duration=1.0,
        signal={"duration": 1.0, "spoken_text_sha256": "1" * 64},
        generation_seed=11,
    )
    db.set_current_quality_policy(
        policy_hash="candidate-policy-v1",
        policy_version=1,
        policy={"asr": {"repair_rounds": 2}},
    )
    return db, segment_id, incumbent_sha256, incumbent_path


def _checkpoint_candidate_signal(
    db: ProjectDB,
    candidate_id: int,
    *,
    repair_round: int,
    generation_seed: int,
    wav_path: Path,
    wav_sha256: str,
    signal_overrides: dict | None = None,
) -> None:
    candidate = db.get_segment_candidate(candidate_id)
    signal = {
        "duration": 1.25,
        "tts_delivery_mode": "clarity",
        "asr_clarity_repair_round": repair_round,
        "spoken_text_sha256": "2" * 64,
        "voice_profile_id": int(candidate["expected_voice_profile_id"]),
        "pitch_semitones": 0,
        "effective_pitch_semitones": 0,
        "pitch_variant_skipped": 0.0,
        "pitch_variant_mixed": 0.0,
    }
    signal.update(signal_overrides or {})
    db.checkpoint_segment_candidate_signal(
        candidate_id,
        expected_generation_seed=generation_seed,
        wav_path=wav_path,
        wav_sha256=wav_sha256,
        duration=1.25,
        signal=signal,
    )


def _candidate_decode_check(
    db: ProjectDB,
    *,
    segment_id: int,
    artifact_sha256: str,
    repair_round: int,
    generation_seed: int,
    confirmation: bool,
    verdict: str,
    reason: str,
    metrics_overrides: dict | None = None,
) -> int:
    segment = db.get_segment(segment_id)
    metrics_verdict = (
        "pass" if verdict == "pass" else "inconclusive" if verdict == "inconclusive" else "mismatch"
    )
    metrics = {
        "verdict": metrics_verdict,
        "passed": verdict == "pass",
        "reason": reason,
        "decode_mode": "greedy" if confirmation else "beam5",
        "selected": True,
        "delivery_mode": "clarity",
        "repair_round": repair_round,
        "generation_seed": generation_seed,
        "spoken_text_sha256": "2" * 64,
        "voice_profile_id": int(segment["voice_profile_id"]),
        "pitch_semitones": 0,
        "effective_pitch_semitones": 0,
        "pitch_variant_skipped": False,
        "pitch_variant_mixed": False,
        "transcript": "Text",
        "similarity": 1.0 if verdict == "pass" else 0.2,
        "wer": 0.0 if verdict == "pass" else 1.0,
    }
    metrics.update(metrics_overrides or {})
    return db.record_quality_check(
        scope=QUALITY_SCOPE_SEGMENT,
        stage=SEGMENT_ASR_DECODE_QUALITY_STAGE,
        segment_id=segment_id,
        artifact_sha256=artifact_sha256,
        policy_hash="candidate-policy-v1",
        policy_version=1,
        verdict=verdict,
        metrics=metrics,
    )


def _candidate_perceptual_check(
    db: ProjectDB,
    *,
    segment_id: int,
    artifact_sha256: str,
    verdict: str,
    perceptual_verdict: str,
    reason: str,
    review_required: bool,
    baseline_pitch_semitones: int = 0,
) -> int:
    return db.record_quality_check(
        scope=QUALITY_SCOPE_SEGMENT,
        stage=SEGMENT_PERCEPTUAL_QUALITY_STAGE,
        segment_id=segment_id,
        artifact_sha256=artifact_sha256,
        policy_hash="candidate-policy-v1",
        policy_version=1,
        verdict=verdict,
        metrics={
            "verdict": perceptual_verdict,
            "reason": reason,
            "review_required": review_required,
            "score": 3.8,
            "baseline_score": 4.0,
            "baseline_delta": -0.2,
            "baseline_pitch_semitones": baseline_pitch_semitones,
        },
    )


def _write_candidate_artifact(path: Path, label: str) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(f"candidate-audio:{label}".encode("utf-8"))
    return sha256_file(path)


def _dual_pass_candidate(
    db: ProjectDB,
    *,
    segment_id: int,
    incumbent_sha256: str,
    candidate_path: Path,
    generation_seed: int,
    perceptual_required: bool,
) -> tuple[sqlite3.Row, str]:
    candidate_sha256 = _write_candidate_artifact(candidate_path, str(generation_seed))
    candidate = db.allocate_segment_candidate(
        segment_id=segment_id,
        policy_hash="candidate-policy-v1",
        repair_round=0,
        max_repair_rounds=2,
        incumbent_sha256=incumbent_sha256,
        generation_seed=generation_seed,
        wav_path=candidate_path,
        candidates_root=candidate_path.parent,
        perceptual_required=perceptual_required,
    )
    candidate_id = int(candidate["id"])
    _checkpoint_candidate_signal(
        db,
        candidate_id,
        repair_round=0,
        generation_seed=generation_seed,
        wav_path=candidate_path,
        wav_sha256=candidate_sha256,
    )
    for confirmation in (False, True):
        check_id = _candidate_decode_check(
            db,
            segment_id=segment_id,
            artifact_sha256=candidate_sha256,
            repair_round=0,
            generation_seed=generation_seed,
            confirmation=confirmation,
            verdict="pass",
            reason="ok",
        )
        db.checkpoint_segment_candidate_decode(
            candidate_id,
            quality_check_id=check_id,
            confirmation=confirmation,
        )
    return db.get_segment_candidate(candidate_id), candidate_sha256


def test_segment_speaker_rewrite_rebuilds_marker_free_canonical_note(
    tmp_path: Path,
) -> None:
    db, segment_id = _segment_db(tmp_path)
    with db.connect() as conn:
        row = db.get_segment(segment_id)
        legacy_note = canonical_analysis_note(
            {**dict(row), "kind": "dialogue"},
            (CONTINUED_DIALOGUE_LOCK_NOTE,),
        )
        conn.execute(
            "UPDATE segments SET kind='dialogue',analysis_notes=? WHERE id=?",
            (legacy_note, segment_id),
        )
    row = db.get_segment(segment_id)

    rewritten = db.rewrite_segment_speakers(
        [segment_id],
        speaker="ALISA",
        gender="female",
        age="adult",
    )

    result = db.get_segment(segment_id)
    assert rewritten == 1
    assert result["speaker"] == "ALISA"
    assert result["analysis_notes"] == canonical_analysis_note(dict(result))
    assert CONTINUED_DIALOGUE_LOCK_NOTE not in result["analysis_notes"]


def test_segment_speaker_rewrite_does_not_accept_analysis_notes_argument(
    tmp_path: Path,
) -> None:
    db, segment_id = _segment_db(tmp_path)

    with pytest.raises(TypeError, match="analysis_notes"):
        db.rewrite_segment_speakers(
            [segment_id],
            speaker="FORGED",
            gender="unknown",
            age="unknown",
            analysis_notes="copied director prose",
        )

    assert db.get_segment(segment_id)["speaker"] == "NARRATOR"


def test_segment_speaker_rewrite_rejects_dialogue_marker_on_narration(
    tmp_path: Path,
) -> None:
    db, segment_id = _segment_db(tmp_path)
    with pytest.raises(ValueError, match="dialogue segments"):
        db.rewrite_segment_speakers(
            [segment_id],
            speaker="FORGED",
            gender="unknown",
            age="unknown",
        )

    assert db.get_segment(segment_id)["speaker"] == "NARRATOR"


def test_segment_speaker_rewrite_rejects_noncanonical_current_note_atomically(
    tmp_path: Path,
) -> None:
    db, segment_id = _segment_db(tmp_path)
    with db.connect() as conn:
        conn.execute(
            "UPDATE segments SET kind='dialogue',analysis_notes='forged' WHERE id=?",
            (segment_id,),
        )

    with pytest.raises(ValueError, match="canonical delivery note"):
        db.rewrite_segment_speakers(
            [segment_id],
            speaker="FORGED",
            gender="unknown",
            age="unknown",
        )

    assert db.get_segment(segment_id)["speaker"] == "NARRATOR"


def test_segment_speaker_rewrite_rebuilds_each_row_note_from_its_own_delivery(
    tmp_path: Path,
) -> None:
    db, source_rows = _analysis_batch_db(tmp_path)
    first_id = int(source_rows[0]["id"])
    second_id = int(source_rows[1]["id"])
    with db.connect() as conn:
        conn.execute(
            "UPDATE segments SET kind='dialogue'"
        )
        conn.execute(
            "UPDATE segments SET emotion='angry',intensity=2 WHERE id=?", (second_id,)
        )

    rewritten = db.rewrite_segment_speakers(
        [first_id, second_id],
        speaker="ALISA",
        gender="female",
        age="adult",
    )

    rows = db.list_segments()
    assert rewritten == 2
    assert {row["speaker"] for row in rows} == {"ALISA"}
    assert all(
        row["analysis_notes"] == canonical_analysis_note(dict(row))
        for row in rows
    )
    assert rows[0]["analysis_notes"] != rows[1]["analysis_notes"]


def test_partial_analysis_update_merges_current_delivery_and_builds_canonical_note(
    tmp_path: Path,
) -> None:
    db, segment_id = _segment_db(tmp_path)

    db.update_analysis(segment_id, {"confidence": 0.9})

    row = db.get_segment(segment_id)
    assert row["kind"] == "narration"
    assert row["speaker"] == "NARRATOR"
    assert row["emotion"] == "neutral"
    assert row["confidence"] == 0.9
    assert row["analysis_notes"] == canonical_analysis_note(dict(row))


def test_partial_analysis_update_rebuilds_note_after_delivery_change(
    tmp_path: Path,
) -> None:
    db, segment_id = _segment_db(tmp_path)
    db.update_analysis(segment_id, {"confidence": 0.9})

    db.update_analysis(
        segment_id,
        {"emotion": "angry", "intensity": 2, "volume": "loud"},
    )

    row = db.get_segment(segment_id)
    assert row["emotion"] == "angry"
    assert row["intensity"] == 2
    assert row["volume"] == "loud"
    assert row["analysis_notes"] == canonical_analysis_note(dict(row))


@pytest.mark.parametrize(
    "updates",
    (
        {"personality_hint": "stoic"},
        {"notes": "director prose"},
    ),
)
def test_partial_analysis_update_rejects_untrusted_note_fields_atomically(
    tmp_path: Path,
    updates: dict,
) -> None:
    db, segment_id = _segment_db(tmp_path)
    before = dict(db.get_segment(segment_id))

    with pytest.raises(ValueError, match="personality_hint|canonical delivery note"):
        db.update_analysis(segment_id, updates)

    after = dict(db.get_segment(segment_id))
    assert after["kind"] == before["kind"]
    assert after["confidence"] == before["confidence"]
    assert after["analysis_notes"] == before["analysis_notes"]


def test_direct_analysis_update_rejects_recognized_marker_atomically(
    tmp_path: Path,
) -> None:
    db, segment_id = _segment_db(tmp_path)
    data = _canonical_analysis_data(kind="dialogue", speaker="ALISA")
    data["notes"] = canonical_analysis_note(
        data,
        (CONTINUED_DIALOGUE_LOCK_NOTE,),
    )

    with pytest.raises(ValueError, match="must not persist host markers"):
        db.update_analysis(segment_id, data)

    row = db.get_segment(segment_id)
    assert row["kind"] == "narration"
    assert row["speaker"] == "NARRATOR"
    assert row["analysis_notes"] == ""


def test_partial_analysis_update_strips_valid_legacy_marker_from_current_note(
    tmp_path: Path,
) -> None:
    db, segment_id = _segment_db(tmp_path)
    row = db.get_segment(segment_id)
    legacy_note = canonical_analysis_note(
        dict(row),
        (CONTINUED_DIALOGUE_LOCK_NOTE,),
    )
    with db.connect() as conn:
        conn.execute(
            "UPDATE segments SET analysis_notes=? WHERE id=?",
            (legacy_note, segment_id),
        )

    db.update_analysis(segment_id, {"confidence": 0.9})

    result = db.get_segment(segment_id)
    assert result["analysis_notes"] == canonical_analysis_note(dict(result))
    assert CONTINUED_DIALOGUE_LOCK_NOTE not in result["analysis_notes"]


def test_warning_codes_are_merged_without_duplicates(tmp_path: Path) -> None:
    db, segment_id = _segment_db(tmp_path)

    db.set_segment_warning_code(segment_id, "TTS_SPLIT_RECOVERY")
    db.mark_verified(segment_id, warning_code="ASR_ERROR")
    db.set_segment_warning_code(segment_id, "TTS_SPLIT_RECOVERY")

    assert db.get_segment(segment_id)["warning_code"] == "TTS_SPLIT_RECOVERY|ASR_ERROR"


def test_signal_checkpoint_commits_derived_warnings_atomically(tmp_path: Path) -> None:
    db, segment_id = _segment_db(tmp_path)
    wav_path = tmp_path / "segment.wav"
    wav_path.write_bytes(b"wav")

    db.mark_signal_passed(
        segment_id,
        wav_path=wav_path,
        wav_sha256="a" * 64,
        duration=1.0,
        signal={"pitch_variant_skipped": 1.0},
        generation_seed=17,
        warning_codes=(
            "TTS_SPLIT_RECOVERY",
            "TTS_PITCH_VARIANT_SKIPPED",
            "TTS_PITCH_VARIANT_SKIPPED",
        ),
    )

    row = db.get_segment(segment_id)
    assert row["status"] == "signal_passed"
    assert row["warning_code"] == (
        "TTS_SPLIT_RECOVERY|TTS_PITCH_VARIANT_SKIPPED"
    )


def test_analysis_director_batch_and_accept_event_commit_atomically(tmp_path: Path) -> None:
    db, source_rows = _analysis_batch_db(tmp_path)
    batch = [
        {
            "segment_id": row["id"],
            "stable_id": row["stable_id"],
            "text_sha256": row["text_sha256"],
            "expected_status": "pending",
            "data": _canonical_analysis_data(),
        }
        for row in source_rows
    ]

    db.update_analysis_batch_with_event(
        batch,
        low_confidence_threshold=0.65,
        event_level="info",
        event_code="ANALYSIS_DIRECTOR_CRITIC_ACCEPTED",
        event_message="accepted",
        event_details={"candidate_hash": "candidate"},
        **ANALYSIS_MODEL_COMMIT,
        pronunciations=[{
            "surface": "Michael",
            "normalized_surface": "michael",
            "spoken_form": "Mai-cồ",
            "confidence": 0.91,
            "source": "analysis",
        }],
    )

    assert {row["status"] for row in db.list_segments()} == {"analyzed"}
    event = db.list_events()[-1]
    assert event["code"] == "ANALYSIS_DIRECTOR_CRITIC_ACCEPTED"
    assert json.loads(event["details_json"])["candidate_hash"] == "candidate"
    pronunciation = db.list_pronunciations()[0]
    assert pronunciation["surface"] == "Michael"
    assert pronunciation["spoken_form"] == "Mai-cồ"


def test_analysis_candidate_reservation_survives_reopen_and_consumes_crashed_intent(
    tmp_path: Path,
) -> None:
    db, source_rows = _analysis_batch_db(tmp_path)
    assert db.has_analysis_candidates() is False
    candidate = _allocate_analysis_candidate(db, source_rows, critic_max_attempts=2)
    assert db.has_analysis_candidates() is True
    first = db.reserve_analysis_critic_attempt(
        int(candidate["id"]),
        expected_state="allocated",
        max_attempts=2,
        intent={"candidate_hash": str(candidate["candidate_hash"]), "attempt": 1},
        contract={"seed": 11, "temperature": 0.2},
    )

    reopened = ProjectDB(db.path)
    resumable = reopened.find_resumable_analysis_candidate(
        policy_fingerprint=ANALYSIS_POLICY_FINGERPRINT,
        model_name=ANALYSIS_MODEL_NAME,
        model_digest=ANALYSIS_MODEL_DIGEST,
        group_fingerprint=ANALYSIS_GROUP_FINGERPRINT,
        context_hash=ANALYSIS_CONTEXT_HASH,
    )
    assert int(resumable["id"]) == int(candidate["id"])
    second = reopened.reserve_analysis_critic_attempt(
        int(candidate["id"]),
        expected_state="critic_in_flight",
        max_attempts=2,
        intent={"candidate_hash": str(candidate["candidate_hash"]), "attempt": 2},
        contract={"seed": 12, "temperature": 0.2},
    )

    assert int(first["attempt_number"]) == 1
    assert int(second["attempt_number"]) == 2
    attempts = reopened.list_analysis_critic_attempts(int(candidate["id"]))
    assert [row["state"] for row in attempts] == ["abandoned", "reserved"]
    with pytest.raises(RuntimeError, match="budget is exhausted"):
        reopened.reserve_analysis_critic_attempt(
            int(candidate["id"]),
            expected_state="critic_in_flight",
            max_attempts=2,
            intent={"attempt": 3},
            contract={"seed": 13},
        )


def test_analysis_candidate_records_generator_retries_without_resetting_critic_budget(
    tmp_path: Path,
) -> None:
    db, source_rows = _analysis_batch_db(tmp_path)
    candidate = _allocate_analysis_candidate(db, source_rows, critic_max_attempts=2)
    attempt = db.reserve_analysis_critic_attempt(
        int(candidate["id"]),
        expected_state="allocated",
        max_attempts=2,
        intent={"candidate_hash": str(candidate["candidate_hash"])},
        contract=_accepted_critic_contract(),
    )
    retry_contract = {"attempt": 2, "seed": 202, "blind_envelope_hash": "changed"}

    db.record_analysis_candidate_generator_contract(int(candidate["id"]), retry_contract)
    replay = db.record_analysis_candidate_generator_contract(
        int(candidate["id"]),
        retry_contract,
    )

    contracts = db.list_analysis_candidate_generator_contracts(int(candidate["id"]))
    assert len(contracts) == 2
    assert {int(row["occurrence_count"]) for row in contracts} == {1}
    assert int(replay["critic_attempt_count"]) == int(attempt["attempt_number"]) == 1
    assert replay["state"] == "critic_in_flight"


def test_final_crashed_critic_intent_can_be_terminalized_after_budget_exhaustion(
    tmp_path: Path,
) -> None:
    db, source_rows = _analysis_batch_db(tmp_path)
    candidate = _allocate_analysis_candidate(db, source_rows, critic_max_attempts=1)
    db.reserve_analysis_critic_attempt(
        int(candidate["id"]),
        expected_state="allocated",
        max_attempts=1,
        intent={"candidate_hash": str(candidate["candidate_hash"])},
        contract=_accepted_critic_contract(),
    )

    reopened = ProjectDB(db.path)
    terminal = reopened.finalize_exhausted_analysis_critic_candidate(
        int(candidate["id"]),
        reason="final critic request crashed",
    )
    replay = reopened.finalize_exhausted_analysis_critic_candidate(
        int(candidate["id"]),
        reason="final critic request crashed",
    )

    assert terminal["state"] == replay["state"] == "terminal"
    assert reopened.list_analysis_critic_attempts(int(candidate["id"]))[0]["state"] == (
        "abandoned"
    )


def test_analysis_candidate_completion_is_exact_idempotent_and_reopenable_without_model(
    tmp_path: Path,
) -> None:
    db, source_rows = _analysis_batch_db(tmp_path)
    candidate = _allocate_analysis_candidate(db, source_rows)
    attempt = db.reserve_analysis_critic_attempt(
        int(candidate["id"]),
        expected_state="allocated",
        max_attempts=2,
        intent={"candidate_hash": str(candidate["candidate_hash"])},
        contract=_accepted_critic_contract(),
    )
    completion_kwargs = {
        "expected_intent_hash": str(attempt["intent_hash"]),
        "expected_contract_hash": str(attempt["contract_hash"]),
        "result_state": "critic_accepted",
        "outcome": {"accepted": True},
        "evidence": _accepted_critic_evidence(_analysis_acceptance_envelope(source_rows)),
        "commit_envelope": _analysis_acceptance_envelope(source_rows),
    }

    completed = db.complete_analysis_critic_attempt(
        int(candidate["id"]),
        1,
        **completion_kwargs,
    )
    replay = ProjectDB(db.path).complete_analysis_critic_attempt(
        int(candidate["id"]),
        1,
        **completion_kwargs,
    )

    assert replay["completion_hash"] == completed["completion_hash"]
    reopened = ProjectDB(db.path)
    resumable = reopened.find_resumable_analysis_candidate(
        policy_fingerprint=ANALYSIS_POLICY_FINGERPRINT,
        model_name=ANALYSIS_MODEL_NAME,
        model_digest=ANALYSIS_MODEL_DIGEST,
        group_fingerprint=ANALYSIS_GROUP_FINGERPRINT,
        context_hash=ANALYSIS_CONTEXT_HASH,
    )
    snapshot = reopened.analysis_candidate_acceptance_envelope(int(candidate["id"]))
    assert resumable["state"] == "critic_accepted"
    assert snapshot["candidate"] == _analysis_acceptance_envelope(source_rows)
    assert snapshot["critic_outcome"] == {
        "candidate_state": "critic_accepted",
        "payload": {"accepted": True},
    }
    different_evidence = _accepted_critic_evidence(
        _analysis_acceptance_envelope(source_rows)
    )
    different_evidence["segments"][0]["critic"]["rationale"] = "Khác nhưng vẫn hợp lệ."
    with pytest.raises(RuntimeError, match="replay payload differs"):
        reopened.complete_analysis_critic_attempt(
            int(candidate["id"]),
            1,
            **{**completion_kwargs, "evidence": different_evidence},
        )


def test_analysis_candidate_rejects_arbitrarily_lowered_derived_confidence(
    tmp_path: Path,
) -> None:
    db, source_rows = _analysis_batch_db(tmp_path)
    envelope = _analysis_acceptance_envelope(source_rows)
    candidate = _allocate_analysis_candidate(db, source_rows, candidate=envelope)
    attempt = db.reserve_analysis_critic_attempt(
        int(candidate["id"]),
        expected_state="allocated",
        max_attempts=2,
        intent={"candidate_hash": str(candidate["candidate_hash"])},
        contract=_accepted_critic_contract(),
    )
    commit_envelope = copy.deepcopy(envelope)
    commit_envelope["segments"][0]["data"]["confidence"] = 0.7
    evidence = _accepted_critic_evidence(envelope)
    evidence["segments"][0]["derived_confidence"] = 0.7

    with pytest.raises(RuntimeError, match="exact delivery/confidence"):
        db.complete_analysis_critic_attempt(
            int(candidate["id"]),
            1,
            expected_intent_hash=str(attempt["intent_hash"]),
            expected_contract_hash=str(attempt["contract_hash"]),
            result_state="critic_accepted",
            outcome={"accepted": True},
            evidence=evidence,
            commit_envelope=commit_envelope,
        )


@pytest.mark.parametrize(
    ("field", "value", "error"),
    (
        ("personality_hint", "stoic", "personality_hint must be empty"),
        ("notes", "Director prose must not persist.", "canonical delivery note"),
        (
            "notes",
            "delivery_note_v1={\"kind\":\"narration\",\"emotion\":\"neutral\","
            "\"intensity\":1,\"pace\":\"normal\",\"volume\":\"normal\"}; forged",
            "unrecognized host marker",
        ),
    ),
)
def test_analysis_candidate_rejects_personality_and_noncanonical_notes(
    tmp_path: Path,
    field: str,
    value: str,
    error: str,
) -> None:
    db, source_rows = _analysis_batch_db(tmp_path)
    envelope = _analysis_acceptance_envelope(source_rows)
    envelope["segments"][0]["data"][field] = value

    with pytest.raises(ValueError, match=error):
        _allocate_analysis_candidate(db, source_rows, candidate=envelope)


def test_analysis_candidate_rejects_recognized_host_markers(
    tmp_path: Path,
) -> None:
    db, source_rows = _analysis_batch_db(tmp_path)
    envelope = _analysis_acceptance_envelope(source_rows)
    data = envelope["segments"][0]["data"]
    data["notes"] = canonical_analysis_note(
        data,
        (CONTINUED_DIALOGUE_LOCK_NOTE,),
    )

    with pytest.raises(ValueError, match="must not persist host markers"):
        _allocate_analysis_candidate(db, source_rows, candidate=envelope)


@pytest.mark.parametrize("field", ("personality_hint", "notes"))
def test_analysis_candidate_rejects_note_tamper_after_rehash(
    tmp_path: Path,
    field: str,
) -> None:
    db, source_rows = _analysis_batch_db(tmp_path)
    envelope = _analysis_acceptance_envelope(source_rows)
    candidate = _allocate_analysis_candidate(db, source_rows, candidate=envelope)
    tampered = copy.deepcopy(envelope)
    tampered["segments"][0]["data"][field] = "forged"
    tampered_json = json.dumps(
        tampered,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    with db.connect() as conn:
        conn.execute(
            "UPDATE analysis_candidates SET candidate_json=?,envelope_hash=? WHERE id=?",
            (tampered_json, sha256_text(tampered_json), int(candidate["id"])),
        )

    with pytest.raises(ValueError, match="personality_hint|canonical delivery note"):
        ProjectDB(db.path).get_analysis_candidate(int(candidate["id"]))


@pytest.mark.parametrize("field", ("personality_hint", "notes"))
def test_analysis_commit_rejects_personality_or_note_injection(
    tmp_path: Path,
    field: str,
) -> None:
    db, source_rows = _analysis_batch_db(tmp_path)
    envelope = _analysis_acceptance_envelope(source_rows)
    candidate = _allocate_analysis_candidate(db, source_rows, candidate=envelope)
    attempt = db.reserve_analysis_critic_attempt(
        int(candidate["id"]),
        expected_state="allocated",
        max_attempts=2,
        intent={"candidate_hash": str(candidate["candidate_hash"])},
        contract=_accepted_critic_contract(),
    )
    commit_envelope = copy.deepcopy(envelope)
    commit_envelope["segments"][0]["data"][field] = "forged"

    with pytest.raises(ValueError, match="personality_hint|canonical delivery note"):
        db.complete_analysis_critic_attempt(
            int(candidate["id"]),
            1,
            expected_intent_hash=str(attempt["intent_hash"]),
            expected_contract_hash=str(attempt["contract_hash"]),
            result_state="critic_accepted",
            outcome={"accepted": True},
            evidence=_accepted_critic_evidence(envelope),
            commit_envelope=commit_envelope,
        )


def test_analysis_candidate_rejects_critic_quote_outside_current_source_text(
    tmp_path: Path,
) -> None:
    db, source_rows = _analysis_batch_db(tmp_path)
    envelope = _analysis_acceptance_envelope(source_rows)
    candidate = _allocate_analysis_candidate(db, source_rows, candidate=envelope)
    attempt = db.reserve_analysis_critic_attempt(
        int(candidate["id"]),
        expected_state="allocated",
        max_attempts=2,
        intent={"candidate_hash": str(candidate["candidate_hash"])},
        contract=_accepted_critic_contract(),
    )
    evidence = _accepted_critic_evidence(envelope)
    evidence["segments"][0]["critic"]["evidence_quote"] = "Text 2"

    with pytest.raises(RuntimeError, match="exact delivery/confidence"):
        db.complete_analysis_critic_attempt(
            int(candidate["id"]),
            1,
            expected_intent_hash=str(attempt["intent_hash"]),
            expected_contract_hash=str(attempt["contract_hash"]),
            result_state="critic_accepted",
            outcome={"accepted": True},
            evidence=evidence,
            commit_envelope=envelope,
        )


def test_analysis_candidate_accepts_source_bound_chapter_heading_override(
    tmp_path: Path,
) -> None:
    db, source_rows = _analysis_batch_db(
        tmp_path,
        texts=("Chương 01 - Giàn hỏa thiêu rực cháy", "Khói dày ngùn ngụt."),
    )
    envelope = _chapter_heading_envelope(source_rows)
    clearance = _chapter_heading_clearance(envelope)
    candidate = _allocate_analysis_candidate(
        db,
        source_rows,
        candidate=envelope,
        deterministic_issues=clearance,
    )
    attempt = db.reserve_analysis_critic_attempt(
        int(candidate["id"]),
        expected_state="allocated",
        max_attempts=2,
        intent={"candidate_hash": str(candidate["candidate_hash"])},
        contract=_accepted_critic_contract(),
    )
    evidence = _heading_override_evidence(envelope)

    completed = db.complete_analysis_critic_attempt(
        int(candidate["id"]),
        1,
        expected_intent_hash=str(attempt["intent_hash"]),
        expected_contract_hash=str(attempt["contract_hash"]),
        result_state="critic_accepted",
        outcome={"accepted": True, "host_structural_override": True},
        evidence=evidence,
        commit_envelope=envelope,
    )

    assert completed["state"] == "completed"
    snapshot = ProjectDB(db.path).analysis_candidate_acceptance_envelope(
        int(candidate["id"])
    )
    stored_evidence = snapshot["critic_evidence"]
    assert stored_evidence["segments"][0]["critic"]["emotion"] == "afraid"
    assert stored_evidence["segments"][0]["host_structural_override"][
        "locked_fields"
    ] == ANALYSIS_CHAPTER_HEADING_DELIVERY
    assert snapshot["commit_envelope"]["segments"][0]["data"]["emotion"] == "neutral"


def test_analysis_candidate_rejects_heading_role_on_first_prose_segment(
    tmp_path: Path,
) -> None:
    db, source_rows = _analysis_batch_db(
        tmp_path,
        texts=("Khói dày phủ kín căn phòng.", "Hạ Phong bật tỉnh."),
    )
    envelope = _chapter_heading_envelope(source_rows)
    clearance = _chapter_heading_clearance(envelope)

    with pytest.raises(RuntimeError, match="not source-metadata-bound"):
        _allocate_analysis_candidate(
            db,
            source_rows,
            candidate=envelope,
            deterministic_issues=clearance,
        )


def test_analysis_candidate_rejects_forged_structural_override_on_content(
    tmp_path: Path,
) -> None:
    db, source_rows = _analysis_batch_db(tmp_path)
    envelope = _analysis_acceptance_envelope(source_rows)
    forged_clearance = _chapter_heading_clearance(envelope)
    with pytest.raises(
        RuntimeError,
        match="structural clearance differs from chapter-heading rows",
    ):
        _allocate_analysis_candidate(
            db,
            source_rows,
            candidate=envelope,
            deterministic_issues=forged_clearance,
        )


def test_analysis_candidate_rejects_tampered_heading_structural_clearance(
    tmp_path: Path,
) -> None:
    db, source_rows = _analysis_batch_db(
        tmp_path,
        texts=("Chương 01 - Giàn hỏa thiêu rực cháy", "Khói dày ngùn ngụt."),
    )
    envelope = _chapter_heading_envelope(source_rows)
    clearance = _chapter_heading_clearance(envelope)
    clearance["host_affect_clearance"]["structural_locks"][0][
        "text_sha256"
    ] = "f" * 64
    with pytest.raises(RuntimeError, match="structural clearance is not source-bound"):
        _allocate_analysis_candidate(
            db,
            source_rows,
            candidate=envelope,
            deterministic_issues=clearance,
        )


def test_analysis_candidate_rejects_mandatory_heading_lock_when_omitted(
    tmp_path: Path,
) -> None:
    db, source_rows = _analysis_batch_db(
        tmp_path,
        texts=("Chapter 01 - Beginning", "Ordinary prose follows."),
    )
    envelope = _analysis_acceptance_envelope(source_rows)

    with pytest.raises(RuntimeError, match="source-derived chapter headings"):
        _allocate_analysis_candidate(
            db,
            source_rows,
            candidate=envelope,
        )


def test_direct_narration_affect_source_authority_accepts_exact_smoke_rows() -> None:
    assert ANALYSIS_HOST_AFFECT_POLICY_VERSION == "host_affect_v6"
    assert ANALYSIS_HOST_SEMANTIC_POLICY_VERSION == "host_semantic_lock_v3"
    assert analysis_source_has_recalled_persistent_fear(
        RECALLED_PERSISTENT_FEAR_TEXT
    )
    assert analysis_source_has_stunned_blank_mind(STUNNED_BLANK_MIND_TEXT)
    assert not analysis_source_has_stunned_blank_mind(
        RECALLED_PERSISTENT_FEAR_TEXT
    )
    assert not analysis_source_has_recalled_persistent_fear(
        STUNNED_BLANK_MIND_TEXT
    )
    assert analysis_source_has_recalled_persistent_fear(
        "Hạ Phong đến giờ nghĩ lại vẫn tim đập chân run."
    )
    assert analysis_source_has_recalled_persistent_fear(
        "Đèn đã tắt. Hạ Phong nghĩ lại vẫn tim đập chân run."
    )
    assert analysis_source_has_recalled_persistent_fear(
        "Giấc mơ ấy chân thực đến dị thường, làm cho Hạ Phong nghĩ lại "
        "vẫn tim đập chân run."
    )
    assert analysis_source_has_stunned_blank_mind(
        "Cậu đực mặt ra, đầu óc một mảng trắng xóa."
    )
    assert analysis_source_has_stunned_blank_mind(
        "Đèn đã tắt. Cậu đực mặt ra, đầu óc một mảng trắng xóa."
    )
    assert analysis_source_has_stunned_blank_mind(
        "Giống như bị cây chùy nặng đập vào đầu, cậu đực mặt ra, "
        "đầu óc một mảng trắng xóa."
    )


@pytest.mark.parametrize(
    "text",
    (
        "Hạ Phong không còn nghĩ lại vẫn tim đập chân run.",
        "Hạ Phong từng nghĩ lại vẫn tim đập chân run.",
        "Nếu Hạ Phong nghĩ lại vẫn tim đập chân run, cậu sẽ xin nghỉ.",
        "Nghe nói Hạ Phong nghĩ lại vẫn tim đập chân run.",
        "Không phải Hạ Phong đến giờ nghĩ lại vẫn tim đập chân run.",
        "Không đúng là Hạ Phong đến giờ nghĩ lại vẫn tim đập chân run.",
        "Không chắc Hạ Phong đến giờ nghĩ lại vẫn tim đập chân run.",
        "Chưa chắc Hạ Phong đến giờ nghĩ lại vẫn tim đập chân run.",
        "Đâu phải Hạ Phong đến giờ nghĩ lại vẫn tim đập chân run.",
        "Cô phủ nhận Hạ Phong đến giờ nghĩ lại vẫn tim đập chân run.",
        "Cô nói Hạ Phong đến giờ nghĩ lại vẫn tim đập chân run.",
        "Cô nói rằng Hạ Phong đến giờ nghĩ lại vẫn tim đập chân run.",
        "Cô cho rằng Hạ Phong đến giờ nghĩ lại vẫn tim đập chân run.",
        "Cô nghi ngờ Hạ Phong đến giờ nghĩ lại vẫn tim đập chân run.",
        "Theo lời kể, Hạ Phong đến giờ nghĩ lại vẫn tim đập chân run.",
        "Có vẻ Hạ Phong đến giờ nghĩ lại vẫn tim đập chân run.",
        "Có vẻ như Hạ Phong đến giờ nghĩ lại vẫn tim đập chân run.",
        "Có vẻ là Hạ Phong đến giờ nghĩ lại vẫn tim đập chân run.",
        "Người ta đồn rằng Hạ Phong đến giờ nghĩ lại vẫn tim đập chân run.",
        "Theo tin đồn, Hạ Phong đến giờ nghĩ lại vẫn tim đập chân run.",
        "Theo lời đồn, Hạ Phong đến giờ nghĩ lại vẫn tim đập chân run.",
        "Nghe đồn Hạ Phong đến giờ nghĩ lại vẫn tim đập chân run.",
        "Tương truyền Hạ Phong đến giờ nghĩ lại vẫn tim đập chân run.",
        "Tưởng tượng rằng Hạ Phong đến giờ nghĩ lại vẫn tim đập chân run.",
        "Không có bằng chứng rằng Hạ Phong nghĩ lại vẫn tim đập chân run.",
        "Chưa có bằng chứng rằng Hạ Phong nghĩ lại vẫn tim đập chân run.",
        "Có vẻ một ký ức hiện lên, làm cho Hạ Phong nghĩ lại vẫn tim đập chân run.",
        "Không chắc một ký ức hiện lên, làm cho Hạ Phong nghĩ lại vẫn tim đập chân run.",
        "Theo lời đồn, một ký ức hiện lên, làm cho Hạ Phong nghĩ lại vẫn tim đập chân run.",
        "Cô phủ nhận chuyện một ký ức hiện lên, làm cho Hạ Phong nghĩ lại vẫn tim đập chân run.",
        "Nếu một ký ức hiện lên, làm cho Hạ Phong nghĩ lại vẫn tim đập chân run.",
        "Trước đây Hạ Phong nghĩ lại vẫn tim đập chân run.",
        "Ngày trước, Hạ Phong nghĩ lại vẫn tim đập chân run.",
        "Hồi ấy, Hạ Phong nghĩ lại vẫn tim đập chân run.",
        "Đã có lúc Hạ Phong nghĩ lại vẫn tim đập chân run.",
        "Khi đó Hạ Phong nghĩ lại vẫn tim đập chân run.",
        "Hồi đó Hạ Phong nghĩ lại vẫn tim đập chân run.",
        "Ngày ấy Hạ Phong nghĩ lại vẫn tim đập chân run.",
        "Thuở ấy Hạ Phong nghĩ lại vẫn tim đập chân run.",
        "Lúc trước Hạ Phong nghĩ lại vẫn tim đập chân run.",
        "Trước kia Hạ Phong nghĩ lại vẫn tim đập chân run.",
        "Năm xưa Hạ Phong nghĩ lại vẫn tim đập chân run.",
        "Xưa kia Hạ Phong nghĩ lại vẫn tim đập chân run.",
        "Trong quá khứ Hạ Phong nghĩ lại vẫn tim đập chân run.",
        "Hạ Phong giả vờ nghĩ lại vẫn tim đập chân run.",
        "Ông nhắc lại câu “Hạ Phong nghĩ lại vẫn tim đập chân run”.",
        "Cụm từ Hạ Phong nghĩ lại vẫn tim đập chân run được định nghĩa ở đây.",
        "Hạ Phong nghĩ lại vẫn tim đập chân run nhưng lại vui mừng nhẹ nhõm.",
        "Cô dịu dàng ôm đứa trẻ đang nghĩ lại vẫn tim đập chân run.",
        "Hạ Phong vẫn tim đập chân run.",
        "Liệu Hạ Phong nghĩ lại vẫn tim đập chân run?",
        (
            "Hạ Phong nghĩ lại vẫn tim đập chân run. "
            "Hạ Phong nghĩ lại vẫn tim đập chân run."
        ),
    ),
)
def test_recalled_persistent_fear_source_authority_excludes_ambiguous_rows(
    text: str,
) -> None:
    assert not analysis_source_has_recalled_persistent_fear(text)


@pytest.mark.parametrize(
    "text",
    (
        "Cậu không còn đực mặt ra, đầu óc một mảng trắng xóa.",
        "Cậu từng đực mặt ra, đầu óc một mảng trắng xóa.",
        "Nếu cậu đực mặt ra, đầu óc một mảng trắng xóa thì hãy ngồi xuống.",
        "Nghe nói cậu đực mặt ra, đầu óc một mảng trắng xóa.",
        "Không phải cậu đực mặt ra, đầu óc một mảng trắng xóa.",
        "Không đúng là cậu đực mặt ra, đầu óc một mảng trắng xóa.",
        "Không chắc cậu đực mặt ra, đầu óc một mảng trắng xóa.",
        "Chưa chắc cậu đực mặt ra, đầu óc một mảng trắng xóa.",
        "Đâu phải cậu đực mặt ra, đầu óc một mảng trắng xóa.",
        "Cô phủ nhận cậu đực mặt ra, đầu óc một mảng trắng xóa.",
        "Cô nói cậu đực mặt ra, đầu óc một mảng trắng xóa.",
        "Cô nói rằng cậu đực mặt ra, đầu óc một mảng trắng xóa.",
        "Cô cho rằng cậu đực mặt ra, đầu óc một mảng trắng xóa.",
        "Cô nghi ngờ cậu đực mặt ra, đầu óc một mảng trắng xóa.",
        "Theo lời kể, cậu đực mặt ra, đầu óc một mảng trắng xóa.",
        "Có vẻ cậu đực mặt ra, đầu óc một mảng trắng xóa.",
        "Có vẻ như cậu đực mặt ra, đầu óc một mảng trắng xóa.",
        "Có vẻ là cậu đực mặt ra, đầu óc một mảng trắng xóa.",
        "Người ta đồn rằng cậu đực mặt ra, đầu óc một mảng trắng xóa.",
        "Theo tin đồn, cậu đực mặt ra, đầu óc một mảng trắng xóa.",
        "Theo lời đồn, cậu đực mặt ra, đầu óc một mảng trắng xóa.",
        "Nghe đồn cậu đực mặt ra, đầu óc một mảng trắng xóa.",
        "Tương truyền cậu đực mặt ra, đầu óc một mảng trắng xóa.",
        "Tưởng tượng rằng cậu đực mặt ra, đầu óc một mảng trắng xóa.",
        "Không có bằng chứng rằng cậu đực mặt ra, đầu óc một mảng trắng xóa.",
        "Chưa có bằng chứng rằng cậu đực mặt ra, đầu óc một mảng trắng xóa.",
        "Trước đây cậu đực mặt ra, đầu óc một mảng trắng xóa.",
        "Ngày trước, cậu đực mặt ra, đầu óc một mảng trắng xóa.",
        "Hồi ấy, cậu đực mặt ra, đầu óc một mảng trắng xóa.",
        "Đã có lúc cậu đực mặt ra, đầu óc một mảng trắng xóa.",
        "Khi đó cậu đực mặt ra, đầu óc một mảng trắng xóa.",
        "Hồi đó cậu đực mặt ra, đầu óc một mảng trắng xóa.",
        "Ngày ấy cậu đực mặt ra, đầu óc một mảng trắng xóa.",
        "Thuở ấy cậu đực mặt ra, đầu óc một mảng trắng xóa.",
        "Lúc trước cậu đực mặt ra, đầu óc một mảng trắng xóa.",
        "Trước kia cậu đực mặt ra, đầu óc một mảng trắng xóa.",
        "Năm xưa cậu đực mặt ra, đầu óc một mảng trắng xóa.",
        "Xưa kia cậu đực mặt ra, đầu óc một mảng trắng xóa.",
        "Trong quá khứ cậu đực mặt ra, đầu óc một mảng trắng xóa.",
        "Cậu giả vờ đực mặt ra, đầu óc một mảng trắng xóa.",
        "Ông nhắc lại câu “cậu đực mặt ra, đầu óc một mảng trắng xóa”.",
        "Cậu đực mặt ra, đầu óc một mảng trắng xóa nhưng lại vui mừng.",
        (
            "Cậu đực mặt ra, đầu óc một mảng trắng xóa, "
            "tim đập chân run."
        ),
        "Cô dịu dàng ôm đứa trẻ đang đực mặt ra, đầu óc một mảng trắng xóa.",
        "Cậu đực mặt ra.",
        "Đầu óc cậu một mảng trắng xóa rồi cậu đực mặt ra.",
        "Liệu cậu đực mặt ra, đầu óc một mảng trắng xóa?",
    ),
)
def test_stunned_blank_mind_source_authority_excludes_ambiguous_rows(
    text: str,
) -> None:
    assert not analysis_source_has_stunned_blank_mind(text)


@pytest.mark.parametrize(
    "suffix",
    (
        ", nếu lời đồn là đúng.",
        ", theo lời đồn.",
        ", có lẽ vậy.",
        ", người ta nói thế.",
        ", nhưng đó chỉ là lời đồn.",
        ", nhưng điều đó không đúng.",
        ", nhưng đó không phải sự thật.",
        ", nhưng cậu chỉ giả vờ.",
        ", nhưng thực ra cậu hoàn toàn bình tĩnh.",
        "; tuy nhiên đó chỉ là giả thuyết.",
        ": đó chỉ là ví dụ.",
    ),
)
def test_direct_narration_affect_source_authority_rejects_outer_scope_suffix(
    suffix: str,
) -> None:
    assert not analysis_source_has_recalled_persistent_fear(
        f"Hạ Phong đến giờ nghĩ lại vẫn tim đập chân run{suffix}"
    )
    assert not analysis_source_has_stunned_blank_mind(
        f"Cậu đực mặt ra, đầu óc một mảng trắng xóa{suffix}"
    )


@pytest.mark.parametrize(
    "text",
    (
        "Cậu đực mặt ra, nhưng đó chỉ là giả vờ, đầu óc một mảng trắng xóa.",
        "Cậu đực mặt ra, người ta nói đầu óc một mảng trắng xóa.",
        "Cậu đực mặt ra, đầu óc có lẽ một mảng trắng xóa.",
        "Cậu đực mặt ra, đầu óc được đồn là trắng xóa.",
        "Cậu đực mặt ra, đầu óc không hề trắng xóa.",
        "Cậu đực mặt ra, đầu óc chưa từng trắng xóa.",
        "Cậu đực mặt ra, đầu óc giả vờ trắng xóa.",
    ),
)
def test_stunned_blank_mind_source_authority_rejects_nonassertive_bridge(
    text: str,
) -> None:
    assert not analysis_source_has_stunned_blank_mind(text)


@pytest.mark.parametrize(
    (
        "text",
        "rule",
        "cue_class",
        "allowed_emotions",
        "candidate_emotion",
        "wrong_emotion",
    ),
    DIRECT_NARRATION_AFFECT_LOCK_CASES,
)
def test_analysis_candidate_accepts_source_bound_direct_narration_affect_lock(
    tmp_path: Path,
    text: str,
    rule: str,
    cue_class: str,
    allowed_emotions: tuple[str, ...],
    candidate_emotion: str,
    wrong_emotion: str,
) -> None:
    del wrong_emotion
    db, source_rows = _analysis_batch_db(tmp_path, texts=(text,))
    envelope = _semantic_lock_envelope(
        source_rows,
        candidate_emotion=candidate_emotion,
    )
    clearance = _host_semantic_clearance(
        envelope,
        rule=rule,
        cue_class=cue_class,
        allowed_emotions=list(allowed_emotions),
    )

    candidate = _allocate_analysis_candidate(
        db,
        source_rows,
        candidate=envelope,
        deterministic_issues=clearance,
    )

    durable_clearance = json.loads(str(candidate["deterministic_issue_json"]))[
        "host_affect_clearance"
    ]
    assert candidate["state"] == "allocated"
    assert durable_clearance["policy_version"] == "host_affect_v6"
    assert durable_clearance["semantic_locks"] == clearance[
        "host_affect_clearance"
    ]["semantic_locks"]


@pytest.mark.parametrize(
    (
        "text",
        "rule",
        "cue_class",
        "allowed_emotions",
        "candidate_emotion",
        "wrong_emotion",
    ),
    DIRECT_NARRATION_AFFECT_LOCK_CASES,
)
def test_analysis_candidate_rejects_invalid_direct_narration_affect_emotion(
    tmp_path: Path,
    text: str,
    rule: str,
    cue_class: str,
    allowed_emotions: tuple[str, ...],
    candidate_emotion: str,
    wrong_emotion: str,
) -> None:
    del rule, cue_class, allowed_emotions, candidate_emotion
    db, source_rows = _analysis_batch_db(tmp_path, texts=(text,))
    envelope = _analysis_acceptance_envelope(source_rows, emotion=wrong_emotion)

    with pytest.raises(RuntimeError, match="mandatory host semantic emotion"):
        _allocate_analysis_candidate(db, source_rows, candidate=envelope)


@pytest.mark.parametrize(
    ("forged_field", "forged_value", "expected_error"),
    (
        ("rule", "forged_direct_narration_rule", "unknown rule"),
        ("cue_class", "forged_direct_affect", "source-bound"),
        ("allowed_emotions", ["afraid", "neutral"], "source-bound"),
        ("text_sha256", "f" * 64, "source-bound"),
    ),
)
@pytest.mark.parametrize(
    (
        "text",
        "rule",
        "cue_class",
        "allowed_emotions",
        "candidate_emotion",
        "wrong_emotion",
    ),
    DIRECT_NARRATION_AFFECT_LOCK_CASES,
)
def test_analysis_candidate_rejects_forged_direct_narration_affect_lock(
    tmp_path: Path,
    text: str,
    rule: str,
    cue_class: str,
    allowed_emotions: tuple[str, ...],
    candidate_emotion: str,
    wrong_emotion: str,
    forged_field: str,
    forged_value: object,
    expected_error: str,
) -> None:
    del wrong_emotion
    db, source_rows = _analysis_batch_db(tmp_path, texts=(text,))
    envelope = _semantic_lock_envelope(
        source_rows,
        candidate_emotion=candidate_emotion,
    )
    clearance = _host_semantic_clearance(
        envelope,
        rule=rule,
        cue_class=cue_class,
        allowed_emotions=list(allowed_emotions),
    )
    host_clearance = clearance["host_affect_clearance"]
    host_clearance["semantic_locks"][0][forged_field] = forged_value
    host_clearance["evidence"][0][forged_field] = forged_value

    with pytest.raises(RuntimeError, match=expected_error):
        _allocate_analysis_candidate(
            db,
            source_rows,
            candidate=envelope,
            deterministic_issues=clearance,
        )


@pytest.mark.parametrize(
    (
        "text",
        "rule",
        "cue_class",
        "allowed_emotions",
        "candidate_emotion",
        "wrong_emotion",
    ),
    DIRECT_NARRATION_AFFECT_LOCK_CASES,
)
def test_analysis_candidate_revalidates_direct_narration_affect_lock_on_reopen(
    tmp_path: Path,
    text: str,
    rule: str,
    cue_class: str,
    allowed_emotions: tuple[str, ...],
    candidate_emotion: str,
    wrong_emotion: str,
) -> None:
    db, source_rows = _analysis_batch_db(tmp_path, texts=(text,))
    envelope = _semantic_lock_envelope(
        source_rows,
        candidate_emotion=candidate_emotion,
    )
    clearance = _host_semantic_clearance(
        envelope,
        rule=rule,
        cue_class=cue_class,
        allowed_emotions=list(allowed_emotions),
    )
    candidate = _allocate_analysis_candidate(
        db,
        source_rows,
        candidate=envelope,
        deterministic_issues=clearance,
    )
    tampered = json.loads(str(candidate["deterministic_issue_json"]))
    forged_allowed = [*allowed_emotions, wrong_emotion]
    host_clearance = tampered["host_affect_clearance"]
    host_clearance["semantic_locks"][0]["allowed_emotions"] = forged_allowed
    host_clearance["evidence"][0]["allowed_emotions"] = forged_allowed
    tampered_json = json.dumps(
        tampered,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    with db.connect() as conn:
        conn.execute(
            "UPDATE analysis_candidates SET deterministic_issue_json=?,"
            "deterministic_issue_hash=? WHERE id=?",
            (tampered_json, sha256_text(tampered_json), int(candidate["id"])),
        )

    with pytest.raises(RuntimeError, match="semantic clearance is not source-bound"):
        ProjectDB(db.path).get_analysis_candidate(int(candidate["id"]))


@pytest.mark.parametrize(
    (
        "text",
        "rule",
        "cue_class",
        "allowed_emotions",
        "candidate_emotion",
        "wrong_emotion",
    ),
    DIRECT_NARRATION_AFFECT_LOCK_CASES,
)
def test_direct_narration_affect_critic_dissent_cannot_override_commit(
    tmp_path: Path,
    text: str,
    rule: str,
    cue_class: str,
    allowed_emotions: tuple[str, ...],
    candidate_emotion: str,
    wrong_emotion: str,
) -> None:
    db, source_rows = _analysis_batch_db(tmp_path, texts=(text,))
    envelope = _semantic_lock_envelope(
        source_rows,
        candidate_emotion=candidate_emotion,
    )
    clearance = _host_semantic_clearance(
        envelope,
        rule=rule,
        cue_class=cue_class,
        allowed_emotions=list(allowed_emotions),
    )
    candidate = _allocate_analysis_candidate(
        db,
        source_rows,
        candidate=envelope,
        deterministic_issues=clearance,
    )
    candidate_id = int(candidate["id"])
    attempt = db.reserve_analysis_critic_attempt(
        candidate_id,
        expected_state="allocated",
        max_attempts=2,
        intent={"candidate_hash": str(candidate["candidate_hash"])},
        contract=_accepted_critic_contract(),
    )
    evidence = _semantic_override_evidence(
        envelope,
        clearance,
        corrected_emotion=wrong_emotion,
    )
    evidence["segments"][0]["critic"]["evidence_quote"] = text[-160:]
    db.complete_analysis_critic_attempt(
        candidate_id,
        1,
        expected_intent_hash=str(attempt["intent_hash"]),
        expected_contract_hash=str(attempt["contract_hash"]),
        result_state="critic_accepted",
        outcome={"accepted": True, "host_semantic_override": True},
        evidence=evidence,
        commit_envelope=envelope,
    )

    reopened = ProjectDB(db.path)
    snapshot = reopened.analysis_candidate_acceptance_envelope(candidate_id)
    stored_item = snapshot["critic_evidence"]["segments"][0]
    assert stored_item["critic"]["emotion"] == wrong_emotion
    assert stored_item["host_semantic_override"]["allowed_values"] == list(
        allowed_emotions
    )
    assert (
        snapshot["commit_envelope"]["segments"][0]["data"]["emotion"]
        == candidate_emotion
    )
    batch = [
        {
            "segment_id": segment["segment_id"],
            "stable_id": segment["stable_id"],
            "text_sha256": segment["text_sha256"],
            "expected_status": "pending",
            "data": dict(segment["data"]),
        }
        for segment in snapshot["commit_envelope"]["segments"]
    ]
    reopened.update_analysis_batch_with_event(
        batch,
        low_confidence_threshold=0.65,
        event_level="info",
        event_code="ANALYSIS_DIRECTOR_CRITIC_ACCEPTED",
        event_message="host-locked direct affect accepted",
        event_details={"candidate_hash": str(candidate["candidate_hash"])},
        **ANALYSIS_MODEL_COMMIT,
        analysis_candidate_id=candidate_id,
        analysis_policy_fingerprint=ANALYSIS_POLICY_FINGERPRINT,
        analysis_group_fingerprint=ANALYSIS_GROUP_FINGERPRINT,
        analysis_context_hash=ANALYSIS_CONTEXT_HASH,
    )

    committed = reopened.list_segments()[0]
    assert committed["status"] == "analyzed"
    assert committed["emotion"] == candidate_emotion
    assert reopened.get_analysis_candidate(candidate_id)["state"] == "accepted"


@pytest.mark.parametrize(
    ("text", "kind_hint", "candidate_emotion"),
    (
        (
            "‘Không được… Không được ngủ… sẽ chết mất.’",
            "thought",
            "afraid",
        ),
        (
            "Phổi và yết hầu đang bị thiêu đốt. Ý thức của anh liền mất dần.",
            "narration",
            "afraid",
        ),
        (
            "Cậu tuyệt vọng gắng gượng đến gần ánh sáng.",
            "narration",
            "afraid",
        ),
        (RECALLED_PERSISTENT_FEAR_TEXT, "narration", "afraid"),
        (STUNNED_BLANK_MIND_TEXT, "narration", "surprised"),
    ),
)
def test_analysis_candidate_rejects_mandatory_semantic_lock_when_omitted(
    tmp_path: Path,
    text: str,
    kind_hint: str,
    candidate_emotion: str,
) -> None:
    db, source_rows = _analysis_batch_db(
        tmp_path,
        texts=(text,),
        kind_hints=(kind_hint,),
    )
    envelope = _semantic_lock_envelope(
        source_rows,
        candidate_emotion=candidate_emotion,
    )
    envelope["critic_rows"][0]["host_locked_fields"] = {}

    with pytest.raises(RuntimeError, match="source-derived mandatory locks"):
        _allocate_analysis_candidate(
            db,
            source_rows,
            candidate=envelope,
        )


@pytest.mark.parametrize("candidate_emotion", ["afraid", "sad", "tired"])
def test_analysis_candidate_accepts_source_bound_desperate_exertion_lock(
    tmp_path: Path,
    candidate_emotion: str,
) -> None:
    db, source_rows = _analysis_batch_db(
        tmp_path,
        texts=(
            "Được ánh sáng đó chiếu rọi, Hạ Phong cảm thấy sức lực dần hồi phục, "
            "vì vậy cậu tuyệt vọng gắng gượng đến gần ánh sáng đó.",
        ),
    )
    envelope = _semantic_lock_envelope(
        source_rows,
        candidate_emotion=candidate_emotion,
    )
    clearance = _host_semantic_clearance(
        envelope,
        rule="narration_desperate_exertion",
        cue_class="desperate_exertion",
        allowed_emotions=["afraid", "sad", "tired"],
    )

    candidate = _allocate_analysis_candidate(
        db,
        source_rows,
        candidate=envelope,
        deterministic_issues=clearance,
    )

    assert candidate["state"] == "allocated"


@pytest.mark.parametrize("candidate_emotion", ["neutral", "surprised"])
def test_analysis_candidate_rejects_invalid_mandatory_desperate_exertion_emotion(
    tmp_path: Path,
    candidate_emotion: str,
) -> None:
    db, source_rows = _analysis_batch_db(
        tmp_path,
        texts=("Cậu tuyệt vọng gắng gượng đến gần ánh sáng.",),
    )
    envelope = _analysis_acceptance_envelope(source_rows, emotion=candidate_emotion)

    with pytest.raises(RuntimeError, match="mandatory host semantic emotion"):
        _allocate_analysis_candidate(
            db,
            source_rows,
            candidate=envelope,
        )


@pytest.mark.parametrize(
    "text",
    (
        "Cậu không còn tuyệt vọng gắng gượng đến gần ánh sáng.",
        "Cậu từng tuyệt vọng gắng gượng trong quãng đời trước.",
        "Ông nhắc lại câu “cậu tuyệt vọng gắng gượng” rồi giải thích.",
        "Cậu tuyệt vọng gắng gượng nhưng vẫn vui mừng vì mọi người an toàn.",
        "Một nỗ lực tuyệt vọng gắng gượng diễn ra trong im lặng.",
        "Cậu tuyệt vọng đến gần ánh sáng.",
        "Nếu cậu tuyệt vọng gắng gượng đến gần ánh sáng, cậu sẽ kiệt sức.",
        "Tôi không tin cậu tuyệt vọng gắng gượng đến gần ánh sáng.",
        "Không có chuyện cậu tuyệt vọng gắng gượng đến gần ánh sáng.",
        "Tôi không hề tin rằng cậu tuyệt vọng gắng gượng đến gần ánh sáng.",
        "Tôi không còn tin rằng cậu tuyệt vọng gắng gượng đến gần ánh sáng.",
        "Tôi chưa từng nghĩ rằng cậu tuyệt vọng gắng gượng đến gần ánh sáng.",
        "Không ai tin rằng cậu tuyệt vọng gắng gượng đến gần ánh sáng.",
        "Có lẽ cậu tuyệt vọng gắng gượng đến gần ánh sáng.",
        "Dường như cậu tuyệt vọng gắng gượng đến gần ánh sáng.",
        "Nghe nói cậu tuyệt vọng gắng gượng đến gần ánh sáng.",
        "Tôi nghi ngờ rằng cậu tuyệt vọng gắng gượng đến gần ánh sáng.",
        "Liệu cậu tuyệt vọng gắng gượng đến gần ánh sáng?",
    ),
)
def test_analysis_candidate_rejects_desperate_exertion_lock_on_ambiguous_source(
    tmp_path: Path,
    text: str,
) -> None:
    db, source_rows = _analysis_batch_db(tmp_path, texts=(text,))
    envelope = _semantic_lock_envelope(source_rows, candidate_emotion="sad")
    clearance = _host_semantic_clearance(
        envelope,
        rule="narration_desperate_exertion",
        cue_class="desperate_exertion",
        allowed_emotions=["afraid", "sad", "tired"],
    )

    with pytest.raises(RuntimeError, match="semantic clearance is not source-bound"):
        _allocate_analysis_candidate(
            db,
            source_rows,
            candidate=envelope,
            deterministic_issues=clearance,
        )


@pytest.mark.parametrize(
    ("texts", "kind_hints", "relabel_index", "preserve_thought_indexes"),
    [
        (
            ("‘Mình sẽ chết mất.’", "Nội dung tiếp theo."),
            ("thought", "narration"),
            0,
            (),
        ),
        (
            (
                "Phổi và yết hầu đang bị thiêu đốt. Ý thức của anh liền mất dần.",
                "Cậu cố mở mắt.",
            ),
            ("narration", "narration"),
            0,
            (),
        ),
        (
            (
                "Cậu tuyệt vọng gắng gượng đến gần ánh sáng.",
                "Ánh sáng vẫn ở phía trước.",
            ),
            ("narration", "narration"),
            0,
            (),
        ),
        (
            (RECALLED_PERSISTENT_FEAR_TEXT, "Nội dung tiếp theo."),
            ("narration", "narration"),
            0,
            (),
        ),
        (
            (STUNNED_BLANK_MIND_TEXT, "Nội dung tiếp theo."),
            ("narration", "narration"),
            0,
            (),
        ),
        (
            ("‘Mình sẽ chết mất.’", "‘Tỉnh dậy, phải tỉnh dậy!’"),
            ("thought", "thought"),
            1,
            (0,),
        ),
    ],
)
def test_analysis_candidate_rejects_mandatory_semantic_kind_lock_when_omitted(
    tmp_path: Path,
    texts: tuple[str, ...],
    kind_hints: tuple[str, ...],
    relabel_index: int,
    preserve_thought_indexes: tuple[int, ...],
) -> None:
    db, source_rows = _analysis_batch_db(
        tmp_path,
        texts=texts,
        kind_hints=kind_hints,
    )
    envelope = _analysis_acceptance_envelope(source_rows)
    for index in preserve_thought_indexes:
        envelope["segments"][index]["data"]["kind"] = "thought"
        _refresh_analysis_note(envelope, index)
        envelope["critic_rows"][index]["candidate"]["kind"] = "thought"
    target_kind = "thought" if kind_hints[relabel_index] == "narration" else "narration"
    envelope["segments"][relabel_index]["data"]["kind"] = target_kind
    _refresh_analysis_note(envelope, relabel_index)
    envelope["critic_rows"][relabel_index]["candidate"]["kind"] = target_kind

    with pytest.raises(RuntimeError, match="source-owned boundary"):
        _allocate_analysis_candidate(db, source_rows, candidate=envelope)


def test_analysis_candidate_allows_ordinary_narration_to_implicit_thought(
    tmp_path: Path,
) -> None:
    db, source_rows = _analysis_batch_db(
        tmp_path,
        texts=("Mình đang ở đâu thế này?", "Nội dung tiếp theo."),
    )
    envelope = _analysis_acceptance_envelope(source_rows)
    envelope["segments"][0]["data"]["kind"] = "thought"
    _refresh_analysis_note(envelope, 0)
    envelope["critic_rows"][0]["candidate"]["kind"] = "thought"

    candidate = _allocate_analysis_candidate(db, source_rows, candidate=envelope)

    assert str(candidate["state"]) == "allocated"


@pytest.mark.parametrize(
    "text",
    (
        "Phổi và yết hầu không còn bị thiêu đốt, ý thức đã tỉnh táo và anh vui mừng.",
        "Ông nhắc lại câu “cậu tuyệt vọng gắng gượng” rồi giải thích.",
        "Nếu cậu tuyệt vọng gắng gượng đến gần ánh sáng, cậu sẽ kiệt sức.",
    ),
)
def test_analysis_candidate_allows_ambiguous_narration_to_thought(
    tmp_path: Path,
    text: str,
) -> None:
    db, source_rows = _analysis_batch_db(tmp_path, texts=(text,))
    envelope = _analysis_acceptance_envelope(source_rows)
    envelope["segments"][0]["data"]["kind"] = "thought"
    _refresh_analysis_note(envelope, 0)
    envelope["critic_rows"][0]["candidate"]["kind"] = "thought"

    candidate = _allocate_analysis_candidate(db, source_rows, candidate=envelope)

    assert str(candidate["state"]) == "allocated"


def test_analysis_candidate_revalidates_source_owned_kind_after_reopen(
    tmp_path: Path,
) -> None:
    db, source_rows = _analysis_batch_db(
        tmp_path,
        texts=("‘Mình đang ở đâu?’", "Nội dung tiếp theo."),
        kind_hints=("thought", "narration"),
    )
    envelope = _analysis_acceptance_envelope(source_rows)
    envelope["segments"][0]["data"]["kind"] = "thought"
    _refresh_analysis_note(envelope, 0)
    envelope["critic_rows"][0]["candidate"]["kind"] = "thought"
    candidate = _allocate_analysis_candidate(db, source_rows, candidate=envelope)
    tampered = copy.deepcopy(envelope)
    tampered["segments"][0]["data"]["kind"] = "narration"
    _refresh_analysis_note(tampered, 0)
    tampered["critic_rows"][0]["candidate"]["kind"] = "narration"
    tampered_json = json.dumps(
        tampered,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    tampered_candidate_hash = _canonical_hash(tampered["critic_rows"])
    with db.connect() as conn:
        conn.execute(
            "UPDATE analysis_candidates SET candidate_json=?,candidate_hash=?,envelope_hash=? "
            "WHERE id=?",
            (
                tampered_json,
                tampered_candidate_hash,
                sha256_text(tampered_json),
                int(candidate["id"]),
            ),
        )

    with pytest.raises(RuntimeError, match="source-owned boundary"):
        ProjectDB(db.path).get_analysis_candidate(int(candidate["id"]))


def test_analysis_candidate_rejects_unsupported_durable_kind(tmp_path: Path) -> None:
    db, source_rows = _analysis_batch_db(tmp_path)
    envelope = _analysis_acceptance_envelope(source_rows)
    envelope["segments"][0]["data"]["kind"] = "unsupported"
    envelope["critic_rows"][0]["candidate"]["kind"] = "unsupported"

    with pytest.raises(ValueError, match="Unsupported analysis delivery note kind"):
        _allocate_analysis_candidate(db, source_rows, candidate=envelope)


@pytest.mark.parametrize(
    "text",
    (
        "Cậu không sợ hãi và kinh hoàng; sau đó cậu tuyệt vọng gắng gượng "
        "đến gần ánh sáng.",
        "Cậu không vui mừng và phấn khích; sau đó cậu tuyệt vọng gắng gượng "
        "đến gần ánh sáng.",
        "Cậu khóc rồi cậu tuyệt vọng gắng gượng đến gần ánh sáng.",
        "Đau lòng, cậu tuyệt vọng gắng gượng đến gần ánh sáng.",
    ),
)
def test_analysis_candidate_accepts_desperate_exertion_after_coordinated_negation(
    tmp_path: Path,
    text: str,
) -> None:
    db, source_rows = _analysis_batch_db(tmp_path, texts=(text,))
    envelope = _semantic_lock_envelope(source_rows, candidate_emotion="sad")
    clearance = _host_semantic_clearance(
        envelope,
        rule="narration_desperate_exertion",
        cue_class="desperate_exertion",
        allowed_emotions=["afraid", "sad", "tired"],
    )

    candidate = _allocate_analysis_candidate(
        db,
        source_rows,
        candidate=envelope,
        deterministic_issues=clearance,
    )

    assert candidate["state"] == "allocated"


def test_analysis_candidate_rejects_mandatory_adjacent_lock_when_omitted(
    tmp_path: Path,
) -> None:
    db, source_rows = _analysis_batch_db(
        tmp_path,
        texts=(
            "‘Không được… Không được ngủ… sẽ chết mất.’",
            "‘Tỉnh dậy, phải tỉnh dậy!’",
        ),
        kind_hints=("thought", "thought"),
    )
    with db.connect() as conn:
        conn.execute("UPDATE segments SET paragraph_index=seq WHERE chapter_id=1")
    source_rows = [dict(row) for row in db.list_segments()]
    wake_row = source_rows[1]
    envelope = _analysis_acceptance_envelope([wake_row], emotion="afraid")
    envelope["segments"][0]["data"]["kind"] = "thought"
    _refresh_analysis_note(envelope, 0)
    envelope["critic_rows"][0]["candidate"]["kind"] = "thought"

    with pytest.raises(RuntimeError, match="source-derived mandatory locks"):
        _allocate_analysis_candidate(
            db,
            [wake_row],
            candidate=envelope,
        )


def test_analysis_candidate_rejects_invalid_mandatory_adjacent_emotion(
    tmp_path: Path,
) -> None:
    db, source_rows = _analysis_batch_db(
        tmp_path,
        texts=(
            "‘Không được… Không được ngủ… sẽ chết mất.’",
            "‘Tỉnh dậy, phải tỉnh dậy!’",
        ),
        kind_hints=("thought", "thought"),
    )
    with db.connect() as conn:
        conn.execute("UPDATE segments SET paragraph_index=seq WHERE chapter_id=1")
    wake_row = dict(db.list_segments()[1])
    envelope = _analysis_acceptance_envelope([wake_row])
    envelope["segments"][0]["data"]["kind"] = "thought"
    _refresh_analysis_note(envelope, 0)
    envelope["critic_rows"][0]["candidate"]["kind"] = "thought"

    with pytest.raises(RuntimeError, match="mandatory host semantic emotion"):
        _allocate_analysis_candidate(
            db,
            [wake_row],
            candidate=envelope,
        )


@pytest.mark.parametrize(
    ("text", "kind_hint"),
    (
        (
            "‘Không được… Không được ngủ… sẽ chết mất.’",
            "thought",
        ),
        (
            "Phổi và yết hầu đang bị thiêu đốt. Ý thức của anh liền mất dần.",
            "narration",
        ),
    ),
)
def test_analysis_candidate_rejects_invalid_mandatory_semantic_emotion(
    tmp_path: Path,
    text: str,
    kind_hint: str,
) -> None:
    db, source_rows = _analysis_batch_db(
        tmp_path,
        texts=(text,),
        kind_hints=(kind_hint,),
    )
    envelope = _analysis_acceptance_envelope(source_rows)
    envelope["segments"][0]["data"]["kind"] = kind_hint
    _refresh_analysis_note(envelope, 0)
    envelope["critic_rows"][0]["candidate"]["kind"] = kind_hint

    with pytest.raises(RuntimeError, match="mandatory host semantic emotion"):
        _allocate_analysis_candidate(
            db,
            source_rows,
            candidate=envelope,
        )


def test_analysis_candidate_without_semantic_source_needs_no_host_clearance(
    tmp_path: Path,
) -> None:
    db, source_rows = _analysis_batch_db(
        tmp_path,
        texts=("The room remained quiet through the afternoon.",),
    )
    envelope = _analysis_acceptance_envelope(source_rows)

    candidate = _allocate_analysis_candidate(
        db,
        source_rows,
        candidate=envelope,
    )

    assert candidate["state"] == "allocated"


def test_analysis_candidate_accepts_source_bound_host_semantic_override(
    tmp_path: Path,
) -> None:
    physical_text = (
        "Phổi và yết hầu đang bị thiêu đốt. "
        "Ý thức của Hạ Phong rất nhanh liền trở nên mơ hồ."
    )
    db, source_rows = _analysis_batch_db(
        tmp_path,
        texts=(physical_text, "Cậu cố mở mắt."),
    )
    envelope = _semantic_lock_envelope(source_rows)
    clearance = _host_semantic_clearance(envelope)
    candidate = _allocate_analysis_candidate(
        db,
        source_rows,
        candidate=envelope,
        deterministic_issues=clearance,
    )
    attempt = db.reserve_analysis_critic_attempt(
        int(candidate["id"]),
        expected_state="allocated",
        max_attempts=2,
        intent={"candidate_hash": str(candidate["candidate_hash"])},
        contract=_accepted_critic_contract(),
    )
    evidence = _semantic_override_evidence(envelope, clearance)

    db.complete_analysis_critic_attempt(
        int(candidate["id"]),
        1,
        expected_intent_hash=str(attempt["intent_hash"]),
        expected_contract_hash=str(attempt["contract_hash"]),
        result_state="critic_accepted",
        outcome={"accepted": True, "host_semantic_override": True},
        evidence=evidence,
        commit_envelope=envelope,
    )

    snapshot = ProjectDB(db.path).analysis_candidate_acceptance_envelope(
        int(candidate["id"])
    )
    stored_item = snapshot["critic_evidence"]["segments"][0]
    assert stored_item["critic"]["emotion"] == "neutral"
    assert stored_item["effective_accept"] is True
    assert stored_item["host_semantic_override"]["allowed_values"] == [
        "afraid",
        "tired",
    ]
    assert snapshot["commit_envelope"]["segments"][0]["data"]["emotion"] == "afraid"


def test_analysis_candidate_revalidates_semantic_override_protocol_after_reopen(
    tmp_path: Path,
) -> None:
    physical_text = (
        "Phổi và yết hầu đang bị thiêu đốt. "
        "Ý thức của anh nhanh chóng trở nên mơ hồ."
    )
    db, source_rows = _analysis_batch_db(
        tmp_path,
        texts=(physical_text, "Cậu cố mở mắt."),
    )
    envelope = _semantic_lock_envelope(source_rows)
    clearance = _host_semantic_clearance(envelope)
    candidate = _allocate_analysis_candidate(
        db,
        source_rows,
        candidate=envelope,
        deterministic_issues=clearance,
    )
    candidate_id = int(candidate["id"])
    attempt = db.reserve_analysis_critic_attempt(
        candidate_id,
        expected_state="allocated",
        max_attempts=2,
        intent={"candidate_hash": str(candidate["candidate_hash"])},
        contract=_accepted_critic_contract(),
    )
    db.complete_analysis_critic_attempt(
        candidate_id,
        1,
        expected_intent_hash=str(attempt["intent_hash"]),
        expected_contract_hash=str(attempt["contract_hash"]),
        result_state="critic_accepted",
        outcome={"accepted": True},
        evidence=_semantic_override_evidence(envelope, clearance),
        commit_envelope=envelope,
    )

    with db.connect() as conn:
        stored_attempt = conn.execute(
            "SELECT * FROM analysis_critic_attempts "
            "WHERE analysis_candidate_id=? AND attempt_number=1",
            (candidate_id,),
        ).fetchone()
        stored_candidate = conn.execute(
            "SELECT * FROM analysis_candidates WHERE id=?",
            (candidate_id,),
        ).fetchone()
        tampered_evidence = json.loads(str(stored_attempt["evidence_json"]))
        tampered_item = tampered_evidence["segments"][0]
        tampered_item["critic"]["accept"] = True
        del tampered_item["host_semantic_override"]
        evidence_json, evidence_hash = db._canonical_analysis_json(
            tampered_evidence,
            "tampered semantic critic evidence",
        )
        _completion_json, completion_hash = db._canonical_analysis_json(
            {
                "commit_envelope_hash": stored_candidate["commit_envelope_hash"],
                "contract_hash": stored_attempt["contract_hash"],
                "evidence_hash": evidence_hash,
                "intent_hash": stored_attempt["intent_hash"],
                "outcome_hash": stored_attempt["outcome_hash"],
            },
            "tampered semantic critic completion",
        )
        conn.execute(
            "UPDATE analysis_critic_attempts SET evidence_json=?,evidence_hash=?,"
            "completion_hash=? WHERE analysis_candidate_id=? AND attempt_number=1",
            (evidence_json, evidence_hash, completion_hash, candidate_id),
        )

    reopened = ProjectDB(db.path)
    with pytest.raises(RuntimeError, match="exact delivery/confidence"):
        reopened.analysis_candidate_acceptance_envelope(candidate_id)
    batch = [
        {
            "segment_id": segment["segment_id"],
            "stable_id": segment["stable_id"],
            "text_sha256": segment["text_sha256"],
            "expected_status": "pending",
            "data": dict(segment["data"]),
        }
        for segment in envelope["segments"]
    ]
    with pytest.raises(RuntimeError, match="exact delivery/confidence"):
        reopened.update_analysis_batch_with_event(
            batch,
            low_confidence_threshold=0.65,
            event_level="info",
            event_code="ANALYSIS_DIRECTOR_CRITIC_ACCEPTED",
            event_message="must roll back",
            event_details={"candidate_hash": str(candidate["candidate_hash"])},
            **ANALYSIS_MODEL_COMMIT,
            analysis_candidate_id=candidate_id,
            analysis_policy_fingerprint=ANALYSIS_POLICY_FINGERPRINT,
            analysis_group_fingerprint=ANALYSIS_GROUP_FINGERPRINT,
            analysis_context_hash=ANALYSIS_CONTEXT_HASH,
        )

    assert {row["status"] for row in reopened.list_segments()} == {"pending"}
    with reopened.connect() as conn:
        stored_state = conn.execute(
            "SELECT state FROM analysis_candidates WHERE id=?",
            (candidate_id,),
        ).fetchone()["state"]
    assert stored_state == "critic_accepted"


@pytest.mark.parametrize(
    ("raw_accept", "corrected_emotion", "remove_delta"),
    (
        (True, "neutral", False),
        (False, "afraid", True),
        (False, "tired", False),
    ),
)
def test_analysis_candidate_semantic_override_rejects_invalid_critic_protocol(
    tmp_path: Path,
    raw_accept: bool,
    corrected_emotion: str,
    remove_delta: bool,
) -> None:
    physical_text = (
        "Phổi và yết hầu đang bị thiêu đốt. "
        "Ý thức của Hạ Phong nhanh chóng trở nên mơ hồ."
    )
    db, source_rows = _analysis_batch_db(
        tmp_path,
        texts=(physical_text, "Cậu cố mở mắt."),
    )
    envelope = _semantic_lock_envelope(source_rows)
    clearance = _host_semantic_clearance(envelope)
    candidate = _allocate_analysis_candidate(
        db,
        source_rows,
        candidate=envelope,
        deterministic_issues=clearance,
    )
    attempt = db.reserve_analysis_critic_attempt(
        int(candidate["id"]),
        expected_state="allocated",
        max_attempts=2,
        intent={"candidate_hash": str(candidate["candidate_hash"])},
        contract=_accepted_critic_contract(),
    )
    evidence = _semantic_override_evidence(
        envelope,
        clearance,
        corrected_emotion=corrected_emotion,
    )
    item = evidence["segments"][0]
    item["critic"]["accept"] = raw_accept
    item["host_semantic_override"]["raw_accept"] = raw_accept
    if remove_delta:
        item["field_deltas"] = []
        item["host_semantic_override"]["raw_field_deltas"] = []

    with pytest.raises(RuntimeError, match="exact delivery/confidence"):
        db.complete_analysis_critic_attempt(
            int(candidate["id"]),
            1,
            expected_intent_hash=str(attempt["intent_hash"]),
            expected_contract_hash=str(attempt["contract_hash"]),
            result_state="critic_accepted",
            outcome={"accepted": True},
            evidence=evidence,
            commit_envelope=envelope,
        )


def test_analysis_candidate_rejects_semantic_lock_allowed_set_tampering(
    tmp_path: Path,
) -> None:
    physical_text = (
        "Phổi đang bị bỏng rát. Ý thức của anh rất nhanh liền lịm dần."
    )
    db, source_rows = _analysis_batch_db(
        tmp_path,
        texts=(physical_text, "Cậu cố mở mắt."),
    )
    envelope = _semantic_lock_envelope(source_rows)
    clearance = _host_semantic_clearance(
        envelope,
        allowed_emotions=["afraid", "neutral"],
    )

    with pytest.raises(RuntimeError, match="semantic clearance is not source-bound"):
        _allocate_analysis_candidate(
            db,
            source_rows,
            candidate=envelope,
            deterministic_issues=clearance,
        )


@pytest.mark.parametrize(
    ("field", "value", "expected_error"),
    (
        ("policy_version", "host_affect_stale_v3", "candidate-bound"),
        ("checked_segment_count", 999, "candidate-bound"),
        ("matched_rule_count", 999, "evidence is not lock-bound"),
        ("evidence", [], "evidence is not lock-bound"),
    ),
)
def test_analysis_candidate_rejects_tampered_host_clearance_metadata(
    tmp_path: Path,
    field: str,
    value: object,
    expected_error: str,
) -> None:
    physical_text = (
        "Phổi đang bị bỏng rát. Ý thức của anh nhanh chóng trở nên mơ hồ."
    )
    db, source_rows = _analysis_batch_db(
        tmp_path,
        texts=(physical_text, "Nội dung tiếp theo."),
    )
    envelope = _semantic_lock_envelope(source_rows)
    clearance = _host_semantic_clearance(envelope)
    clearance["host_affect_clearance"][field] = value

    with pytest.raises(RuntimeError, match=expected_error):
        _allocate_analysis_candidate(
            db,
            source_rows,
            candidate=envelope,
            deterministic_issues=clearance,
        )


@pytest.mark.parametrize(
    ("text", "kind_hint", "rule", "cue_class", "allowed_emotions"),
    (
        (
            "Hôm nay trời đẹp và yên tĩnh.",
            "thought",
            "thought_self_preservation_mortality",
            "self_preservation_mortality",
            ["afraid"],
        ),
        (
            "Bác sĩ ghi lại một quan sát lâm sàng bình thường.",
            "narration",
            "respiratory_injury_with_consciousness_loss",
            "physical_collapse",
            ["afraid", "tired"],
        ),
        (
            "Cậu đi về phía ánh sáng trong im lặng.",
            "narration",
            "narration_desperate_exertion",
            "desperate_exertion",
            ["afraid", "sad", "tired"],
        ),
        (
            "Hạ Phong bình tĩnh đọc sách trong thư viện.",
            "narration",
            "narration_recalled_persistent_fear",
            "recalled_persistent_fear",
            ["afraid"],
        ),
        (
            "Hạ Phong bình tĩnh đọc sách trong thư viện.",
            "narration",
            "narration_stunned_blank_mind",
            "stunned_blank_mind",
            ["surprised"],
        ),
    ),
)
def test_analysis_candidate_rejects_semantic_lock_on_arbitrary_source(
    tmp_path: Path,
    text: str,
    kind_hint: str,
    rule: str,
    cue_class: str,
    allowed_emotions: list[str],
) -> None:
    db, source_rows = _analysis_batch_db(
        tmp_path,
        texts=(text, "Nội dung tiếp theo."),
        kind_hints=(kind_hint, "narration"),
    )
    envelope = _semantic_lock_envelope(source_rows)
    clearance = _host_semantic_clearance(
        envelope,
        rule=rule,
        cue_class=cue_class,
        allowed_emotions=allowed_emotions,
    )

    with pytest.raises(RuntimeError, match="semantic clearance is not source-bound"):
        _allocate_analysis_candidate(
            db,
            source_rows,
            candidate=envelope,
            deterministic_issues=clearance,
        )


@pytest.mark.parametrize(
    "mixed_text",
    (
        (
            "Phổi và yết hầu đang bị thiêu đốt, ý thức của anh liền mơ hồ, "
            "nhưng anh lại vui mừng rỡ."
        ),
        (
            "Phổi và yết hầu đang bị thiêu đốt. Ý thức của anh liền mơ hồ "
            "và anh sợ hãi cực độ."
        ),
    ),
)
def test_analysis_candidate_rejects_physical_lock_with_mixed_affect_source(
    tmp_path: Path,
    mixed_text: str,
) -> None:
    db, source_rows = _analysis_batch_db(
        tmp_path,
        texts=(mixed_text, "Nội dung tiếp theo."),
    )
    envelope = _semantic_lock_envelope(source_rows)
    clearance = _host_semantic_clearance(envelope)

    with pytest.raises(RuntimeError, match="semantic clearance is not source-bound"):
        _allocate_analysis_candidate(
            db,
            source_rows,
            candidate=envelope,
            deterministic_issues=clearance,
        )


def test_analysis_candidate_binds_adjacent_semantic_lock_to_mortality_source(
    tmp_path: Path,
) -> None:
    db, source_rows = _analysis_batch_db(
        tmp_path,
        texts=(
            "‘Không được… Không được ngủ… sẽ chết mất.’",
            "‘Tỉnh dậy, phải tỉnh dậy!’",
        ),
        kind_hints=("thought", "thought"),
    )
    with db.connect() as conn:
        conn.execute(
            "UPDATE segments SET paragraph_index=seq WHERE chapter_id=1"
        )
    source_rows = [dict(row) for row in db.list_segments()]
    envelope = _semantic_lock_envelope(source_rows, locked_index=1)
    envelope["segments"][0]["data"].update({"emotion": "afraid", "intensity": 2})
    _refresh_analysis_note(envelope, 0)
    envelope["critic_rows"][0]["candidate"].update(
        {"emotion": "afraid", "intensity": 2}
    )
    envelope["critic_rows"][0]["host_locked_fields"] = {"emotion": "afraid"}
    direct_clearance = _host_semantic_clearance(
        envelope,
        rule="thought_self_preservation_mortality",
        cue_class="self_preservation_mortality",
        allowed_emotions=["afraid"],
    )
    adjacent_clearance = _host_semantic_clearance(
        envelope,
        locked_index=1,
        rule="adjacent_thought_wake_self_rescue",
        cue_class="wake_self_rescue_after_mortality",
        allowed_emotions=["afraid"],
        related_index=0,
    )
    clearance = _merge_host_semantic_clearances(
        direct_clearance,
        adjacent_clearance,
    )

    candidate = _allocate_analysis_candidate(
        db,
        source_rows,
        candidate=envelope,
        deterministic_issues=clearance,
    )
    assert candidate["state"] == "allocated"

    forged = copy.deepcopy(clearance)
    forged["host_affect_clearance"]["semantic_locks"][1][
        "related_text_sha256"
    ] = "f" * 64
    forged["host_affect_clearance"]["evidence"][1][
        "related_text_sha256"
    ] = "f" * 64
    with pytest.raises(RuntimeError, match="related provenance"):
        _allocate_analysis_candidate(
            db,
            source_rows,
            context_hash="forged-related-context",
            candidate=envelope,
            deterministic_issues=forged,
        )


def test_analysis_candidate_rejects_adjacent_semantic_lock_without_mortality_cue(
    tmp_path: Path,
) -> None:
    db, source_rows = _analysis_batch_db(
        tmp_path,
        texts=("‘Mình nên nghỉ ngơi một chút.’", "‘Tỉnh dậy, phải tỉnh dậy!’"),
        kind_hints=("thought", "thought"),
    )
    with db.connect() as conn:
        conn.execute(
            "UPDATE segments SET paragraph_index=seq WHERE chapter_id=1"
        )
    source_rows = [dict(row) for row in db.list_segments()]
    envelope = _semantic_lock_envelope(source_rows, locked_index=1)
    clearance = _host_semantic_clearance(
        envelope,
        locked_index=1,
        rule="adjacent_thought_wake_self_rescue",
        cue_class="wake_self_rescue_after_mortality",
        allowed_emotions=["afraid"],
        related_index=0,
    )

    with pytest.raises(RuntimeError, match="related provenance"):
        _allocate_analysis_candidate(
            db,
            source_rows,
            candidate=envelope,
            deterministic_issues=clearance,
        )


@pytest.mark.parametrize(
    "text",
    (
        "‘Mình sẽ chết.’",
        "‘Tôi không còn nghĩ rằng mình sẽ chết mất.’",
        "‘Tôi đã từng nghĩ mình sẽ chết mất, nhưng giờ đã an toàn.’",
        "‘Tôi không thể nghĩ mình sẽ chết mất.’",
        (
            "‘Mình sẽ chết mất.’ Phổi đang bị bỏng rát và ý thức của mình "
            "nhanh chóng trở nên mơ hồ."
        ),
    ),
)
def test_analysis_candidate_rejects_mortality_lock_without_exact_active_afraid_source(
    tmp_path: Path,
    text: str,
) -> None:
    db, source_rows = _analysis_batch_db(
        tmp_path,
        texts=(text, "Nội dung tiếp theo."),
        kind_hints=("thought", "narration"),
    )
    envelope = _semantic_lock_envelope(source_rows)
    clearance = _host_semantic_clearance(
        envelope,
        rule="thought_self_preservation_mortality",
        cue_class="self_preservation_mortality",
        allowed_emotions=["afraid"],
    )

    with pytest.raises(RuntimeError, match="semantic clearance is not source-bound"):
        _allocate_analysis_candidate(
            db,
            source_rows,
            candidate=envelope,
            deterministic_issues=clearance,
        )


def test_analysis_candidate_rejects_semantic_lock_when_candidate_kind_changes(
    tmp_path: Path,
) -> None:
    db, source_rows = _analysis_batch_db(
        tmp_path,
        texts=("‘Mình sẽ chết mất.’", "Nội dung tiếp theo."),
        kind_hints=("thought", "narration"),
    )
    envelope = _semantic_lock_envelope(source_rows)
    envelope["segments"][0]["data"]["kind"] = "dialogue"
    _refresh_analysis_note(envelope, 0)
    envelope["critic_rows"][0]["candidate"]["kind"] = "dialogue"
    clearance = _host_semantic_clearance(
        envelope,
        rule="thought_self_preservation_mortality",
        cue_class="self_preservation_mortality",
        allowed_emotions=["afraid"],
    )

    with pytest.raises(RuntimeError, match="semantic clearance is not source-bound"):
        _allocate_analysis_candidate(
            db,
            source_rows,
            candidate=envelope,
            deterministic_issues=clearance,
        )


def test_analysis_candidate_rejects_non_immediate_adjacent_semantic_source(
    tmp_path: Path,
) -> None:
    db, source_rows = _analysis_batch_db(
        tmp_path,
        texts=(
            "‘Mình sẽ chết mất.’",
            "Một ý nghĩ khác xen vào.",
            "‘Tỉnh dậy, phải tỉnh dậy!’",
        ),
        kind_hints=("thought", "thought", "thought"),
    )
    with db.connect() as conn:
        conn.execute(
            "UPDATE segments SET paragraph_index=CASE seq WHEN 0 THEN 1 WHEN 1 THEN 9 "
            "ELSE 2 END WHERE chapter_id=1"
        )
    source_rows = [dict(row) for row in db.list_segments()]
    envelope = _semantic_lock_envelope(source_rows, locked_index=2)
    envelope["segments"][0]["data"].update({"emotion": "afraid", "intensity": 2})
    _refresh_analysis_note(envelope, 0)
    envelope["critic_rows"][0]["candidate"].update(
        {"emotion": "afraid", "intensity": 2}
    )
    envelope["critic_rows"][0]["host_locked_fields"] = {"emotion": "afraid"}
    direct_clearance = _host_semantic_clearance(
        envelope,
        rule="thought_self_preservation_mortality",
        cue_class="self_preservation_mortality",
        allowed_emotions=["afraid"],
    )
    adjacent_clearance = _host_semantic_clearance(
        envelope,
        locked_index=2,
        rule="adjacent_thought_wake_self_rescue",
        cue_class="wake_self_rescue_after_mortality",
        allowed_emotions=["afraid"],
        related_index=0,
    )
    clearance = _merge_host_semantic_clearances(
        direct_clearance,
        adjacent_clearance,
    )

    with pytest.raises(RuntimeError, match="related provenance"):
        _allocate_analysis_candidate(
            db,
            source_rows,
            candidate=envelope,
            deterministic_issues=clearance,
        )


def test_analysis_candidate_revalidates_semantic_lock_on_reopen(
    tmp_path: Path,
) -> None:
    physical_text = (
        "Phổi và yết hầu đang bị thiêu đốt. Ý thức của anh liền mất dần."
    )
    db, source_rows = _analysis_batch_db(
        tmp_path,
        texts=(physical_text, "Cậu cố mở mắt."),
    )
    envelope = _semantic_lock_envelope(source_rows)
    clearance = _host_semantic_clearance(envelope)
    candidate = _allocate_analysis_candidate(
        db,
        source_rows,
        candidate=envelope,
        deterministic_issues=clearance,
    )
    tampered = json.loads(str(candidate["deterministic_issue_json"]))
    tampered["host_affect_clearance"]["semantic_locks"][0][
        "allowed_emotions"
    ] = ["afraid", "neutral"]
    tampered["host_affect_clearance"]["evidence"][0][
        "allowed_emotions"
    ] = ["afraid", "neutral"]
    tampered_json = json.dumps(
        tampered,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    with db.connect() as conn:
        conn.execute(
            "UPDATE analysis_candidates SET deterministic_issue_json=?,"
            "deterministic_issue_hash=? WHERE id=?",
            (tampered_json, sha256_text(tampered_json), int(candidate["id"])),
        )

    with pytest.raises(RuntimeError, match="semantic clearance is not source-bound"):
        ProjectDB(db.path).get_analysis_candidate(int(candidate["id"]))


def test_analysis_candidate_keeps_structural_and_semantic_lock_namespaces_disjoint(
    tmp_path: Path,
) -> None:
    db, source_rows = _analysis_batch_db(
        tmp_path,
        texts=("Chương 01 - Khởi đầu", "Nội dung."),
    )
    envelope = _chapter_heading_envelope(source_rows)
    clearance = _chapter_heading_clearance(envelope)
    heading_segment = envelope["segments"][0]
    clearance["host_affect_clearance"]["semantic_locks"] = [
        {
            "policy_version": ANALYSIS_HOST_SEMANTIC_POLICY_VERSION,
            "stable_id": heading_segment["stable_id"],
            "text_sha256": heading_segment["text_sha256"],
            "source_role": "content",
            "field": "emotion",
            "rule": "respiratory_injury_with_consciousness_loss",
            "cue_class": "physical_collapse",
            "candidate_emotion": "neutral",
            "allowed_emotions": ["afraid", "tired"],
            "related_stable_id": "",
            "related_text_sha256": "",
        }
    ]
    clearance["host_affect_clearance"]["matched_rule_count"] = 1
    clearance["host_affect_clearance"]["evidence"] = [
        {
            "stable_id": heading_segment["stable_id"],
            "text_sha256": heading_segment["text_sha256"],
            "rule": "respiratory_injury_with_consciousness_loss",
            "cue_class": "physical_collapse",
            "candidate_emotion": "neutral",
            "allowed_emotions": ["afraid", "tired"],
            "outcome": "pass",
        }
    ]

    with pytest.raises(RuntimeError, match="semantic clearance differs from locked content"):
        _allocate_analysis_candidate(
            db,
            source_rows,
            candidate=envelope,
            deterministic_issues=clearance,
        )


def test_analysis_candidate_rejects_evidence_contract_not_reserved_for_request(
    tmp_path: Path,
) -> None:
    db, source_rows = _analysis_batch_db(tmp_path)
    envelope = _analysis_acceptance_envelope(source_rows)
    candidate = _allocate_analysis_candidate(db, source_rows, candidate=envelope)
    attempt = db.reserve_analysis_critic_attempt(
        int(candidate["id"]),
        expected_state="allocated",
        max_attempts=2,
        intent={"candidate_hash": str(candidate["candidate_hash"])},
        contract=_accepted_critic_contract(),
    )
    evidence = _accepted_critic_evidence(envelope)
    evidence["critic_contract"] = {
        **evidence["critic_contract"],
        "seed": 999,
        "temperature": 0.9,
    }

    with pytest.raises(RuntimeError, match="differs from the reserved request contract"):
        db.complete_analysis_critic_attempt(
            int(candidate["id"]),
            1,
            expected_intent_hash=str(attempt["intent_hash"]),
            expected_contract_hash=str(attempt["contract_hash"]),
            result_state="critic_accepted",
            outcome={"accepted": True},
            evidence=evidence,
            commit_envelope=envelope,
        )


def test_analysis_candidate_resume_rejects_tampered_child_ledgers(tmp_path: Path) -> None:
    db, source_rows = _analysis_batch_db(tmp_path)
    candidate = _allocate_analysis_candidate(db, source_rows)
    candidate_id = int(candidate["id"])
    db.reserve_analysis_critic_attempt(
        candidate_id,
        expected_state="allocated",
        max_attempts=2,
        intent={"candidate_hash": str(candidate["candidate_hash"])},
        contract=_accepted_critic_contract(),
    )

    with db.connect() as conn:
        conn.execute(
            "UPDATE analysis_critic_attempts SET intent_json=? "
            "WHERE analysis_candidate_id=? AND attempt_number=1",
            ('{"candidate_hash":"tampered"}', candidate_id),
        )
    with pytest.raises(RuntimeError, match="intent hash verification"):
        db.reserve_analysis_critic_attempt(
            candidate_id,
            expected_state="critic_in_flight",
            max_attempts=2,
            intent={"candidate_hash": str(candidate["candidate_hash"])},
            contract={"seed": 12},
        )

    untouched = _allocate_analysis_candidate(
        db,
        source_rows,
        context_hash="second-context",
    )
    untouched_id = int(untouched["id"])
    with db.connect() as conn:
        conn.execute(
            "UPDATE analysis_candidate_generator_contracts SET generator_contract_json=? "
            "WHERE analysis_candidate_id=?",
            ('{"attempt":999}', untouched_id),
        )
    with pytest.raises(RuntimeError, match="generator contract hash verification"):
        db.list_analysis_candidate_generator_contracts(untouched_id)
    with pytest.raises(RuntimeError, match="generator contract hash verification"):
        db.find_resumable_analysis_candidate(
            policy_fingerprint=ANALYSIS_POLICY_FINGERPRINT,
            model_name=ANALYSIS_MODEL_NAME,
            model_digest=ANALYSIS_MODEL_DIGEST,
            group_fingerprint=ANALYSIS_GROUP_FINGERPRINT,
            context_hash="second-context",
        )


def test_analysis_candidate_resume_rejects_tampered_completed_critic_evidence(
    tmp_path: Path,
) -> None:
    db, source_rows = _analysis_batch_db(tmp_path)
    candidate = _allocate_analysis_candidate(db, source_rows)
    candidate_id = int(candidate["id"])
    attempt = db.reserve_analysis_critic_attempt(
        candidate_id,
        expected_state="allocated",
        max_attempts=2,
        intent={"candidate_hash": str(candidate["candidate_hash"])},
        contract=_accepted_critic_contract(),
    )
    db.complete_analysis_critic_attempt(
        candidate_id,
        1,
        expected_intent_hash=str(attempt["intent_hash"]),
        expected_contract_hash=str(attempt["contract_hash"]),
        result_state="critic_invalid",
        outcome={"accepted": False},
        evidence={"reason": "schema"},
    )
    with db.connect() as conn:
        conn.execute(
            "UPDATE analysis_critic_attempts SET evidence_json=? "
            "WHERE analysis_candidate_id=? AND attempt_number=1",
            ('{"reason":"tampered"}', candidate_id),
        )

    with pytest.raises(RuntimeError, match="completion hash verification"):
        db.find_resumable_analysis_candidate(
            policy_fingerprint=ANALYSIS_POLICY_FINGERPRINT,
            model_name=ANALYSIS_MODEL_NAME,
            model_digest=ANALYSIS_MODEL_DIGEST,
            group_fingerprint=ANALYSIS_GROUP_FINGERPRINT,
            context_hash=ANALYSIS_CONTEXT_HASH,
        )


def test_analysis_candidate_resume_rejects_parent_child_state_mismatch(
    tmp_path: Path,
) -> None:
    db, source_rows = _analysis_batch_db(tmp_path)
    candidate = _allocate_analysis_candidate(db, source_rows)
    candidate_id = int(candidate["id"])
    attempt = db.reserve_analysis_critic_attempt(
        candidate_id,
        expected_state="allocated",
        max_attempts=2,
        intent={"candidate_hash": str(candidate["candidate_hash"])},
        contract=_accepted_critic_contract(),
    )
    db.complete_analysis_critic_attempt(
        candidate_id,
        1,
        expected_intent_hash=str(attempt["intent_hash"]),
        expected_contract_hash=str(attempt["contract_hash"]),
        result_state="critic_invalid",
        outcome={"accepted": False},
        evidence={"reason": "schema"},
    )
    with db.connect() as conn:
        conn.execute(
            "UPDATE analysis_critic_attempts SET state='abandoned',outcome_json=NULL,"
            "outcome_hash=NULL,evidence_json=NULL,evidence_hash=NULL,completion_hash=NULL "
            "WHERE analysis_candidate_id=? AND attempt_number=1",
            (candidate_id,),
        )

    with pytest.raises(RuntimeError, match="final critic attempt is not completed"):
        db.find_resumable_analysis_candidate(
            policy_fingerprint=ANALYSIS_POLICY_FINGERPRINT,
            model_name=ANALYSIS_MODEL_NAME,
            model_digest=ANALYSIS_MODEL_DIGEST,
            group_fingerprint=ANALYSIS_GROUP_FINGERPRINT,
            context_hash=ANALYSIS_CONTEXT_HASH,
        )


def test_analysis_candidate_completion_rehashes_prior_critic_attempts(
    tmp_path: Path,
) -> None:
    db, source_rows = _analysis_batch_db(tmp_path)
    envelope = _analysis_acceptance_envelope(source_rows)
    candidate = _allocate_analysis_candidate(db, source_rows, candidate=envelope)
    candidate_id = int(candidate["id"])
    first_attempt = db.reserve_analysis_critic_attempt(
        candidate_id,
        expected_state="allocated",
        max_attempts=2,
        intent={"candidate_hash": str(candidate["candidate_hash"])},
        contract=_accepted_critic_contract(),
    )
    db.complete_analysis_critic_attempt(
        candidate_id,
        1,
        expected_intent_hash=str(first_attempt["intent_hash"]),
        expected_contract_hash=str(first_attempt["contract_hash"]),
        result_state="critic_invalid",
        outcome={"accepted": False},
        evidence={"reason": "schema"},
    )
    second_attempt = db.reserve_analysis_critic_attempt(
        candidate_id,
        expected_state="critic_invalid",
        max_attempts=2,
        intent={"candidate_hash": str(candidate["candidate_hash"])},
        contract=_accepted_critic_contract(),
    )
    with db.connect() as conn:
        conn.execute(
            "UPDATE analysis_critic_attempts SET evidence_json=? "
            "WHERE analysis_candidate_id=? AND attempt_number=1",
            ('{"reason":"tampered"}', candidate_id),
        )

    with pytest.raises(RuntimeError, match="completion hash verification"):
        db.complete_analysis_critic_attempt(
            candidate_id,
            2,
            expected_intent_hash=str(second_attempt["intent_hash"]),
            expected_contract_hash=str(second_attempt["contract_hash"]),
            result_state="critic_accepted",
            outcome={"accepted": True},
            evidence=_accepted_critic_evidence(envelope),
            commit_envelope=envelope,
        )

    assert db.get_analysis_candidate(candidate_id)["state"] == "critic_in_flight"


@pytest.mark.parametrize(
    ("tamper_target", "expected_error"),
    (
        ("prior_critic_attempt", "completion hash verification"),
        ("generator_contract", "generator contract hash verification"),
    ),
)
def test_analysis_candidate_commit_rehashes_complete_child_history(
    tmp_path: Path,
    tamper_target: str,
    expected_error: str,
) -> None:
    db, source_rows = _analysis_batch_db(tmp_path)
    envelope = _analysis_acceptance_envelope(source_rows)
    candidate = _allocate_analysis_candidate(db, source_rows, candidate=envelope)
    candidate_id = int(candidate["id"])
    first_attempt = db.reserve_analysis_critic_attempt(
        candidate_id,
        expected_state="allocated",
        max_attempts=2,
        intent={"candidate_hash": str(candidate["candidate_hash"])},
        contract=_accepted_critic_contract(),
    )
    db.complete_analysis_critic_attempt(
        candidate_id,
        1,
        expected_intent_hash=str(first_attempt["intent_hash"]),
        expected_contract_hash=str(first_attempt["contract_hash"]),
        result_state="critic_invalid",
        outcome={"accepted": False},
        evidence={"reason": "schema"},
    )
    second_attempt = db.reserve_analysis_critic_attempt(
        candidate_id,
        expected_state="critic_invalid",
        max_attempts=2,
        intent={"candidate_hash": str(candidate["candidate_hash"])},
        contract=_accepted_critic_contract(),
    )
    db.complete_analysis_critic_attempt(
        candidate_id,
        2,
        expected_intent_hash=str(second_attempt["intent_hash"]),
        expected_contract_hash=str(second_attempt["contract_hash"]),
        result_state="critic_accepted",
        outcome={"accepted": True},
        evidence=_accepted_critic_evidence(envelope),
        commit_envelope=envelope,
    )
    with db.connect() as conn:
        if tamper_target == "prior_critic_attempt":
            conn.execute(
                "UPDATE analysis_critic_attempts SET evidence_json=? "
                "WHERE analysis_candidate_id=? AND attempt_number=1",
                ('{"reason":"tampered"}', candidate_id),
            )
        else:
            conn.execute(
                "UPDATE analysis_candidate_generator_contracts "
                "SET generator_contract_json=? WHERE analysis_candidate_id=?",
                ('{"attempt":999}', candidate_id),
            )
    batch = [
        {
            "segment_id": segment["segment_id"],
            "stable_id": segment["stable_id"],
            "text_sha256": segment["text_sha256"],
            "expected_status": "pending",
            "data": dict(segment["data"]),
        }
        for segment in envelope["segments"]
    ]

    with pytest.raises(RuntimeError, match=expected_error):
        db.analysis_candidate_acceptance_envelope(candidate_id)
    with pytest.raises(RuntimeError, match=expected_error):
        db.update_analysis_batch_with_event(
            batch,
            low_confidence_threshold=0.65,
            event_level="info",
            event_code="ANALYSIS_DIRECTOR_CRITIC_ACCEPTED",
            event_message="must roll back",
            event_details={"candidate_hash": str(candidate["candidate_hash"])},
            **ANALYSIS_MODEL_COMMIT,
            analysis_candidate_id=candidate_id,
            analysis_policy_fingerprint=ANALYSIS_POLICY_FINGERPRINT,
            analysis_group_fingerprint=ANALYSIS_GROUP_FINGERPRINT,
            analysis_context_hash=ANALYSIS_CONTEXT_HASH,
        )

    assert {row["status"] for row in db.list_segments()} == {"pending"}
    assert db.get_analysis_candidate(candidate_id)["state"] == "critic_accepted"


def test_analysis_candidate_identity_is_strict_and_terminal_candidates_do_not_reopen(
    tmp_path: Path,
) -> None:
    db, source_rows = _analysis_batch_db(tmp_path)
    first = _allocate_analysis_candidate(db, source_rows)
    isolated = _allocate_analysis_candidate(
        db,
        source_rows,
        context_hash="different-context",
    )
    terminal = db.mark_analysis_candidate_terminal(
        int(first["id"]),
        expected_state="allocated",
        reason="deterministic mismatch repeated",
    )
    replay = _allocate_analysis_candidate(db, source_rows)

    assert int(isolated["id"]) != int(first["id"])
    assert terminal["state"] == replay["state"] == "terminal"
    assert db.find_resumable_analysis_candidate(
        policy_fingerprint=ANALYSIS_POLICY_FINGERPRINT,
        model_name=ANALYSIS_MODEL_NAME,
        model_digest=ANALYSIS_MODEL_DIGEST,
        group_fingerprint=ANALYSIS_GROUP_FINGERPRINT,
        context_hash=ANALYSIS_CONTEXT_HASH,
    ) is None
    assert db.get_analysis_candidate_exact(
        policy_fingerprint=ANALYSIS_POLICY_FINGERPRINT,
        model_name=ANALYSIS_MODEL_NAME,
        model_digest=ANALYSIS_MODEL_DIGEST,
        group_fingerprint=ANALYSIS_GROUP_FINGERPRINT,
        context_hash="different-context",
        candidate_hash=str(isolated["candidate_hash"]),
    )["id"] == isolated["id"]


def test_analysis_candidate_scope_allows_only_one_actionable_candidate(tmp_path: Path) -> None:
    db, source_rows = _analysis_batch_db(tmp_path)
    first = _allocate_analysis_candidate(db, source_rows)
    changed = _analysis_acceptance_envelope(source_rows, emotion="angry")

    with pytest.raises(sqlite3.IntegrityError, match="UNIQUE constraint failed"):
        _allocate_analysis_candidate(db, source_rows, candidate=changed)

    db.mark_analysis_candidate_superseded(
        int(first["id"]),
        expected_state="allocated",
        reason="generator produced a different critic-visible candidate",
    )
    second = _allocate_analysis_candidate(db, source_rows, candidate=changed)
    assert int(second["id"]) != int(first["id"])


def test_analysis_candidate_read_rehashes_durable_json(tmp_path: Path) -> None:
    db, source_rows = _analysis_batch_db(tmp_path)
    candidate = _allocate_analysis_candidate(db, source_rows)
    with db.connect() as conn:
        conn.execute(
            "UPDATE analysis_candidates SET envelope_hash='tampered' WHERE id=?",
            (int(candidate["id"]),),
        )

    with pytest.raises(RuntimeError, match="hash verification failed"):
        db.get_analysis_candidate(int(candidate["id"]))


def test_analysis_candidate_acceptance_binds_exact_durable_rows_and_rolls_back(
    tmp_path: Path,
) -> None:
    db, source_rows = _analysis_batch_db(tmp_path)
    envelope = _analysis_acceptance_envelope(source_rows)
    candidate = _allocate_analysis_candidate(db, source_rows, candidate=envelope)
    attempt = db.reserve_analysis_critic_attempt(
        int(candidate["id"]),
        expected_state="allocated",
        max_attempts=2,
        intent={"candidate_hash": str(candidate["candidate_hash"])},
        contract=_accepted_critic_contract(),
    )
    db.complete_analysis_critic_attempt(
        int(candidate["id"]),
        1,
        expected_intent_hash=str(attempt["intent_hash"]),
        expected_contract_hash=str(attempt["contract_hash"]),
        result_state="critic_accepted",
        outcome={"accepted": True},
        evidence=_accepted_critic_evidence(envelope),
        commit_envelope=envelope,
    )
    batch = [
        {
            "segment_id": segment["segment_id"],
            "stable_id": segment["stable_id"],
            "text_sha256": segment["text_sha256"],
            "expected_status": "pending",
            "data": dict(segment["data"]),
        }
        for segment in envelope["segments"]
    ]
    batch[1]["data"]["emotion"] = "angry"

    with pytest.raises(RuntimeError, match="differs from the durable candidate"):
        db.update_analysis_batch_with_event(
            batch,
            low_confidence_threshold=0.65,
            event_level="info",
            event_code="ANALYSIS_DIRECTOR_CRITIC_ACCEPTED",
            event_message="must roll back",
            event_details={"candidate_hash": str(candidate["candidate_hash"])},
            **ANALYSIS_MODEL_COMMIT,
            analysis_candidate_id=int(candidate["id"]),
            analysis_policy_fingerprint=ANALYSIS_POLICY_FINGERPRINT,
            analysis_group_fingerprint=ANALYSIS_GROUP_FINGERPRINT,
            analysis_context_hash=ANALYSIS_CONTEXT_HASH,
        )

    assert {row["status"] for row in db.list_segments()} == {"pending"}
    assert db.get_analysis_candidate(int(candidate["id"]))["state"] == "critic_accepted"
    assert not any(
        row["code"] == "ANALYSIS_DIRECTOR_CRITIC_ACCEPTED"
        for row in db.list_events()
    )


def test_analysis_candidate_acceptance_commits_envelope_rows_and_pronunciations(
    tmp_path: Path,
) -> None:
    db, source_rows = _analysis_batch_db(tmp_path)
    envelope = _analysis_acceptance_envelope(source_rows)
    envelope["pronunciations"] = [
        {
            "surface": "Michael",
            "normalized_surface": "michael",
            "spoken_form": "Mai-cồ",
            "confidence": 0.91,
            "source": "analysis",
            "locked": False,
        }
    ]
    candidate = _allocate_analysis_candidate(db, source_rows, candidate=envelope)
    attempt = db.reserve_analysis_critic_attempt(
        int(candidate["id"]),
        expected_state="allocated",
        max_attempts=2,
        intent={"candidate_hash": str(candidate["candidate_hash"])},
        contract=_accepted_critic_contract(),
    )
    db.complete_analysis_critic_attempt(
        int(candidate["id"]),
        1,
        expected_intent_hash=str(attempt["intent_hash"]),
        expected_contract_hash=str(attempt["contract_hash"]),
        result_state="critic_accepted",
        outcome={"accepted": True},
        evidence=_accepted_critic_evidence(envelope),
        commit_envelope=envelope,
    )
    batch = [
        {
            "segment_id": segment["segment_id"],
            "stable_id": segment["stable_id"],
            "text_sha256": segment["text_sha256"],
            "expected_status": "pending",
            "data": dict(segment["data"]),
        }
        for segment in envelope["segments"]
    ]

    db.update_analysis_batch_with_event(
        batch,
        low_confidence_threshold=0.65,
        event_level="info",
        event_code="ANALYSIS_DIRECTOR_CRITIC_ACCEPTED",
        event_message="accepted",
        event_details={"candidate_hash": str(candidate["candidate_hash"])},
        **ANALYSIS_MODEL_COMMIT,
        pronunciations=envelope["pronunciations"],
        analysis_candidate_id=int(candidate["id"]),
        analysis_policy_fingerprint=ANALYSIS_POLICY_FINGERPRINT,
        analysis_group_fingerprint=ANALYSIS_GROUP_FINGERPRINT,
        analysis_context_hash=ANALYSIS_CONTEXT_HASH,
    )

    assert {row["status"] for row in db.list_segments()} == {"analyzed"}
    assert db.get_analysis_candidate(int(candidate["id"]))["state"] == "accepted"
    assert db.list_pronunciations()[0]["normalized_surface"] == "michael"
    event_details = json.loads(db.list_events()[-1]["details_json"])
    assert event_details["analysis_candidate_id"] == int(candidate["id"])
    assert event_details["critic_completion_hash"]
    assert event_details["critic_evidence_hash"]
    assert event_details["commit_envelope_hash"]


def test_analysis_candidate_acceptance_transition_rolls_back_with_event_trigger(
    tmp_path: Path,
) -> None:
    db, source_rows = _analysis_batch_db(tmp_path)
    envelope = _analysis_acceptance_envelope(source_rows)
    candidate = _allocate_analysis_candidate(db, source_rows, candidate=envelope)
    attempt = db.reserve_analysis_critic_attempt(
        int(candidate["id"]),
        expected_state="allocated",
        max_attempts=2,
        intent={"candidate_hash": str(candidate["candidate_hash"])},
        contract=_accepted_critic_contract(),
    )
    db.complete_analysis_critic_attempt(
        int(candidate["id"]),
        1,
        expected_intent_hash=str(attempt["intent_hash"]),
        expected_contract_hash=str(attempt["contract_hash"]),
        result_state="critic_accepted",
        outcome={"accepted": True},
        evidence=_accepted_critic_evidence(envelope),
        commit_envelope=envelope,
    )
    with db.connect() as conn:
        conn.execute(
            """
            CREATE TRIGGER reject_candidate_accept_event
            BEFORE INSERT ON runtime_events
            WHEN NEW.code='ANALYSIS_DIRECTOR_CRITIC_ACCEPTED'
            BEGIN SELECT RAISE(ABORT, 'candidate accept crash'); END
            """
        )
    batch = [
        {
            "segment_id": segment["segment_id"],
            "stable_id": segment["stable_id"],
            "text_sha256": segment["text_sha256"],
            "expected_status": "pending",
            "data": dict(segment["data"]),
        }
        for segment in envelope["segments"]
    ]

    with pytest.raises(sqlite3.IntegrityError, match="candidate accept crash"):
        db.update_analysis_batch_with_event(
            batch,
            low_confidence_threshold=0.65,
            event_level="info",
            event_code="ANALYSIS_DIRECTOR_CRITIC_ACCEPTED",
            event_message="accepted",
            event_details={"candidate_hash": str(candidate["candidate_hash"])},
            **ANALYSIS_MODEL_COMMIT,
            analysis_candidate_id=int(candidate["id"]),
            analysis_policy_fingerprint=ANALYSIS_POLICY_FINGERPRINT,
            analysis_group_fingerprint=ANALYSIS_GROUP_FINGERPRINT,
            analysis_context_hash=ANALYSIS_CONTEXT_HASH,
        )

    assert {row["status"] for row in db.list_segments()} == {"pending"}
    assert db.get_analysis_candidate(int(candidate["id"]))["state"] == "critic_accepted"


def test_analysis_director_batch_trigger_failure_rolls_back_every_row_and_event(
    tmp_path: Path,
) -> None:
    db, source_rows = _analysis_batch_db(tmp_path)
    with db.connect() as conn:
        conn.execute(
            """
            CREATE TRIGGER reject_second_analysis
            BEFORE UPDATE ON segments
            WHEN NEW.stable_id='c1s2'
            BEGIN
                SELECT RAISE(ABORT, 'reject second analysis');
            END
            """
        )
    batch = [
        {
            "segment_id": row["id"],
            "stable_id": row["stable_id"],
            "text_sha256": row["text_sha256"],
            "expected_status": "pending",
            "data": _canonical_analysis_data(),
        }
        for row in source_rows
    ]

    with pytest.raises(sqlite3.IntegrityError, match="reject second analysis"):
        db.update_analysis_batch_with_event(
            batch,
            low_confidence_threshold=0.65,
            event_level="info",
            event_code="ANALYSIS_DIRECTOR_CRITIC_ACCEPTED",
            event_message="must roll back",
            event_details={"candidate_hash": "candidate"},
            **ANALYSIS_MODEL_COMMIT,
        )

    assert {row["status"] for row in db.list_segments()} == {"pending"}
    assert not any(
        row["code"] == "ANALYSIS_DIRECTOR_CRITIC_ACCEPTED"
        for row in db.list_events()
    )


def test_analysis_director_batch_cas_rejects_stale_source_without_partial_update(
    tmp_path: Path,
) -> None:
    db, source_rows = _analysis_batch_db(tmp_path)
    batch = [
        {
            "segment_id": row["id"],
            "stable_id": row["stable_id"],
            "text_sha256": "stale" if index == 1 else row["text_sha256"],
            "expected_status": "pending",
            "data": _canonical_analysis_data(),
        }
        for index, row in enumerate(source_rows)
    ]

    with pytest.raises(RuntimeError, match="CAS failed"):
        db.update_analysis_batch_with_event(
            batch,
            low_confidence_threshold=0.65,
            event_level="info",
            event_code="ANALYSIS_DIRECTOR_CRITIC_ACCEPTED",
            event_message="must roll back",
            event_details={"candidate_hash": "candidate"},
            **ANALYSIS_MODEL_COMMIT,
        )

    assert {row["status"] for row in db.list_segments()} == {"pending"}
    assert not any(
        row["code"] == "ANALYSIS_DIRECTOR_CRITIC_ACCEPTED"
        for row in db.list_events()
    )


def test_analysis_director_event_failure_rolls_back_pronunciation_and_segments(
    tmp_path: Path,
) -> None:
    db, source_rows = _analysis_batch_db(tmp_path)
    with db.connect() as conn:
        conn.execute(
            """
            CREATE TRIGGER reject_director_accept_event
            BEFORE INSERT ON runtime_events
            WHEN NEW.code='ANALYSIS_DIRECTOR_CRITIC_ACCEPTED'
            BEGIN
                SELECT RAISE(ABORT, 'reject director event');
            END
            """
        )
    batch = [
        {
            "segment_id": row["id"],
            "stable_id": row["stable_id"],
            "text_sha256": row["text_sha256"],
            "expected_status": "pending",
            "data": _canonical_analysis_data(),
        }
        for row in source_rows
    ]

    with pytest.raises(sqlite3.IntegrityError, match="reject director event"):
        db.update_analysis_batch_with_event(
            batch,
            low_confidence_threshold=0.65,
            event_level="info",
            event_code="ANALYSIS_DIRECTOR_CRITIC_ACCEPTED",
            event_message="must roll back",
            event_details={"candidate_hash": "candidate"},
            **ANALYSIS_MODEL_COMMIT,
            pronunciations=[{
                "surface": "Michael",
                "normalized_surface": "michael",
                "spoken_form": "Mai-cồ",
                "confidence": 0.91,
            }],
        )

    assert {row["status"] for row in db.list_segments()} == {"pending"}
    assert db.list_pronunciations() == []


def test_analysis_model_lock_is_idempotent_durable_and_rejects_drift(tmp_path: Path) -> None:
    db, _source_rows = _analysis_batch_db(tmp_path, lock_model=False)

    assert db.analysis_model_lock() is None
    db.lock_analysis_model("qwen3:8b", "sha256:first")
    first = db.analysis_model_lock()
    db.lock_analysis_model("qwen3:8b", "sha256:first")
    reopened = ProjectDB(db.path)

    assert reopened.analysis_model_lock() == first
    with pytest.raises(RuntimeError, match="differs from the model name/digest"):
        reopened.lock_analysis_model("qwen3:8b", "sha256:second")
    with pytest.raises(RuntimeError, match="differs from the model name/digest"):
        reopened.lock_analysis_model("qwen3:4b", "sha256:first")


def test_director_commit_rejects_missing_model_lock_without_partial_state(
    tmp_path: Path,
) -> None:
    db, source_rows = _analysis_batch_db(tmp_path)
    with db.connect() as conn:
        conn.execute(
            "UPDATE book SET analysis_model_name=NULL,analysis_model_digest=NULL,"
            "analysis_model_locked_at=NULL WHERE id=1"
        )
    batch = [
        {
            "segment_id": row["id"],
            "stable_id": row["stable_id"],
            "text_sha256": row["text_sha256"],
            "expected_status": "pending",
            "data": {"confidence": 0.9},
        }
        for row in source_rows
    ]

    with pytest.raises(RuntimeError, match="model lock changed"):
        db.update_analysis_batch_with_event(
            batch,
            low_confidence_threshold=0.65,
            event_level="info",
            event_code="ANALYSIS_DIRECTOR_CRITIC_ACCEPTED",
            event_message="must not commit",
            event_details={"candidate_hash": "candidate"},
            **ANALYSIS_MODEL_COMMIT,
            pronunciations=[{
                "surface": "Michael",
                "normalized_surface": "michael",
                "spoken_form": "Mai-cồ",
                "confidence": 0.91,
            }],
        )

    assert {row["status"] for row in db.list_segments()} == {"pending"}
    assert db.list_pronunciations() == []
    assert not any(
        row["code"] == "ANALYSIS_DIRECTOR_CRITIC_ACCEPTED"
        for row in db.list_events()
    )


def test_schema_v6_adds_empty_analysis_model_lock_columns(tmp_path: Path) -> None:
    path = tmp_path / "legacy-v6.sqlite3"
    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            CREATE TABLE book (
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
                casting_finalized INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        conn.execute(
            """
            INSERT INTO book(
                id,title,project_root,settings_hash,settings_json,status,stage,
                input_manifest_hash,created_at,updated_at
            ) VALUES(1,'Legacy',?,'settings','{}','created','created','manifest',1,1)
            """,
            (str(tmp_path),),
        )
        conn.execute("PRAGMA user_version=6")

    migrated = ProjectDB(path)
    backup = path.with_name(f"{path.name}.pre-v6-to-v{SCHEMA_VERSION}.bak")
    with migrated.connect() as conn:
        columns = {str(row[1]) for row in conn.execute("PRAGMA table_info(book)")}

    assert backup.is_file()
    assert {
        "analysis_model_name",
        "analysis_model_digest",
        "analysis_model_locked_at",
    } <= columns
    assert migrated.analysis_model_lock() is None


def test_schema_v7_migrates_durable_analysis_candidate_ledger(tmp_path: Path) -> None:
    path = tmp_path / "legacy-v7.sqlite3"
    ProjectDB(path)
    with sqlite3.connect(path) as conn:
        conn.execute("DROP TABLE analysis_critic_attempts")
        conn.execute("DROP TABLE analysis_candidate_generator_contracts")
        conn.execute("DROP TABLE analysis_candidates")
        conn.execute("PRAGMA user_version=7")

    migrated = ProjectDB(path)
    backup = path.with_name(f"{path.name}.pre-v7-to-v{SCHEMA_VERSION}.bak")
    with migrated.connect() as conn:
        version = int(conn.execute("PRAGMA user_version").fetchone()[0])
        tables = {
            str(row[0])
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        candidate_columns = {
            str(row[1])
            for row in conn.execute("PRAGMA table_info(analysis_candidates)")
        }

    assert version == SCHEMA_VERSION
    assert backup.is_file()
    assert {
        "analysis_candidates",
        "analysis_candidate_generator_contracts",
        "analysis_critic_attempts",
    } <= tables
    assert {
        "policy_fingerprint",
        "model_digest",
        "group_fingerprint",
        "context_hash",
        "candidate_json",
        "critic_attempt_count",
    } <= candidate_columns


def test_new_generation_clears_old_audio_warnings_but_keeps_analysis_warning(
    tmp_path: Path,
) -> None:
    db, segment_id = _segment_db(tmp_path)
    db.set_segment_warning_code(segment_id, "LOW_ANALYSIS_CONFIDENCE")
    db.set_segment_warning_code(segment_id, "SEGMENT_FAILED")
    db.set_segment_warning_code(segment_id, "TTS_GENERATION_CEILING_REACHED")
    db.set_segment_warning_code(segment_id, "ASR_SEVERE_MISMATCH")
    db.mark_asr_result(
        segment_id,
        passed=False,
        transcript="wrong",
        similarity=0.0,
        wer=1.0,
        warning_code="ASR_MISMATCH_UNRESOLVED",
    )

    db.mark_generating(segment_id, seed=17)

    row = db.get_segment(segment_id)
    assert row["status"] == "generating"
    assert row["warning_code"] == "LOW_ANALYSIS_CONFIDENCE"
    assert row["asr_text"] is None
    assert row["asr_similarity"] is None
    assert row["asr_wer"] is None
    assert row["error"] is None


def test_short_ceiling_frame_cap_survives_interruption_and_reopen(tmp_path: Path) -> None:
    db, segment_id = _segment_db(tmp_path)
    db.set_segment_generation_frame_cap(segment_id, 12)
    db.mark_generating(segment_id, seed=17)

    reopened = ProjectDB(db.path)
    assert reopened.reset_in_progress_segments() == 1
    recovered = reopened.get_segment(segment_id)

    assert recovered["generation_frame_cap"] == 12
    reopened.mark_verified(segment_id)
    assert reopened.get_segment(segment_id)["generation_frame_cap"] is None


def test_clarity_generation_checkpoint_survives_interruption_until_explicit_reset(
    tmp_path: Path,
) -> None:
    db, segment_id = _segment_db(tmp_path)
    with pytest.raises(ValueError, match="clarity generation requires"):
        db.mark_generating(
            segment_id,
            seed=16,
            delivery_mode=GENERATION_DELIVERY_CLARITY,
            policy_hash="policy-v1",
        )
    db.mark_generating(
        segment_id,
        seed=17,
        delivery_mode=GENERATION_DELIVERY_CLARITY,
        repair_round=0,
        policy_hash="policy-v1",
    )

    reopened = ProjectDB(db.path)
    assert reopened.reset_in_progress_segments() == 1
    recovered = reopened.get_segment(segment_id)
    assert recovered["status"] == "pending"
    assert recovered["generation_delivery_mode"] == GENERATION_DELIVERY_CLARITY
    assert recovered["generation_repair_round"] == 0
    assert recovered["generation_policy_hash"] == "policy-v1"

    reopened.reset_segment_pending(segment_id, "explicit clean regeneration")
    reset = reopened.get_segment(segment_id)
    assert reset["generation_delivery_mode"] == GENERATION_DELIVERY_PRIMARY
    assert reset["generation_repair_round"] is None
    assert reset["generation_policy_hash"] is None


def test_audio_reset_keeps_locked_analysis_and_casting(tmp_path: Path) -> None:
    db, segment_id = _segment_db(tmp_path)
    db.update_analysis(
        segment_id,
        _canonical_analysis_data(
            kind="dialogue",
            speaker="LUCIEN",
            gender="male",
            age="adult",
            confidence=1.0,
        ),
    )
    profile_id = db.upsert_voice_profile({
        "voice_key": "lucien",
        "engine": "vieneu",
        "preset_name": "Xuân Vĩnh",
        "description": "Lucien",
        "seed": 1,
        "pitch_semitones": 0,
        "status": "ready",
    })
    with db.connect() as conn:
        conn.execute(
            "UPDATE segments SET voice_profile_id=? WHERE id=?",
            (profile_id, segment_id),
        )

    db.reset_segment_pending(segment_id, "WAV needs regeneration")

    row = db.get_segment(segment_id)
    assert row["status"] == "analyzed"
    assert row["kind"] == "dialogue"
    assert row["speaker"] == "LUCIEN"
    assert row["voice_profile_id"] == profile_id

    db.mark_generating(segment_id, seed=23)
    assert db.reset_in_progress_segments("Interrupted generation") == 1

    recovered = db.get_segment(segment_id)
    assert recovered["status"] == "analyzed"
    assert recovered["kind"] == "dialogue"
    assert recovered["speaker"] == "LUCIEN"
    assert recovered["voice_profile_id"] == profile_id


def test_pronunciation_keeps_higher_confidence_value(tmp_path: Path) -> None:
    db = ProjectDB(tmp_path / "project.sqlite3")
    db.upsert_pronunciation(
        surface="Edelweiss",
        normalized_surface="edelweiss",
        spoken_form="Ê đen vai",
        confidence=0.9,
    )
    db.upsert_pronunciation(
        surface="Edelweiss",
        normalized_surface="edelweiss",
        spoken_form="Sai",
        confidence=0.4,
    )

    row = db.list_pronunciations()[0]
    assert row["spoken_form"] == "Ê đen vai"
    assert row["confidence"] == pytest.approx(0.9)


def test_locked_name_pronunciation_is_applied_and_cannot_be_overwritten(tmp_path: Path) -> None:
    db = ProjectDB(tmp_path / "project.sqlite3")
    db.upsert_pronunciation(
        surface="Michael",
        normalized_surface="michael",
        spoken_form="Mai-cồ",
        confidence=0.55,
        source="english_name_transliteration",
        locked=True,
    )
    db.upsert_pronunciation(
        surface="Michael",
        normalized_surface="michael",
        spoken_form="Cách đọc sai",
        confidence=0.99,
        source="analysis",
    )

    row = db.list_pronunciations(minimum_confidence=0.95)[0]
    assert row["spoken_form"] == "Mai-cồ"
    assert row["source"] == "english_name_transliteration"
    assert row["locked"] == 1


def test_pronunciation_is_applied_by_vieneu_coordinator(tmp_path: Path) -> None:
    db = ProjectDB(tmp_path / "project.sqlite3")
    db.upsert_pronunciation(
        surface="Edelweiss",
        normalized_surface="edelweiss",
        spoken_form="Ê đen vai",
        confidence=0.95,
    )
    coordinator = TTSCoordinator(build_settings(), db, lambda _message: None)

    assert coordinator.spoken_text({"text": "Edelweiss nở hoa."}) == "Ê đen vai nở hoa."


def test_vocalization_normalization_is_applied_without_changing_source_row(tmp_path: Path) -> None:
    db = ProjectDB(tmp_path / "project.sqlite3")
    coordinator = TTSCoordinator(build_settings(), db, lambda _message: None)
    row = {"text": "[thở dài] Haizzzzz.... Tôi hiểu rồi."}

    assert coordinator.spoken_text(row) == "Hầy... Hầy... Tôi hiểu rồi."
    assert row["text"] == "[thở dài] Haizzzzz.... Tôi hiểu rồi."


def test_contextual_english_name_pronunciation_preserves_lowercase_vietnamese_word(
    tmp_path: Path,
) -> None:
    db = ProjectDB(tmp_path / "project.sqlite3")
    db.upsert_pronunciation(
        surface="May",
        normalized_surface="may",
        spoken_form="Mây",
        confidence=0.95,
        source=CONTEXTUAL_ENGLISH_NAME_PRONUNCIATION_SOURCE,
        locked=True,
    )
    coordinator = TTSCoordinator(build_settings(), db, lambda _message: None)

    assert coordinator.spoken_text({"text": "May đang may một chiếc áo."}) == "Mây đang may một chiếc áo."


def test_legacy_v0_migration_uses_a_versioned_backup_and_is_idempotent(tmp_path: Path) -> None:
    path = tmp_path / "project.sqlite3"
    legacy = ProjectDB(path)
    legacy.initialize_book(
        title="Legacy",
        project_root=tmp_path,
        settings={"locked": True},
        settings_hash="legacy-settings",
        input_manifest_hash="legacy-manifest",
    )
    chapter_id = legacy.ensure_chapters(
        [
            {
                "chapter_index": 1,
                "title": "Chapter",
                "input_path": tmp_path / "chapter.txt",
                "input_sha256": "source",
                "input_size": 123,
                "output_mp3": tmp_path / "chapter.mp3",
            }
        ]
    )[0]
    legacy.finalize_casting()
    legacy.update_book(status="synthesizing", stage="chapter_synthesis")
    legacy.update_chapter_status(chapter_id, "completed")
    before = dict(legacy.book())
    before_chapter = dict(legacy.list_chapters()[0])
    with legacy.connect() as conn:
        conn.execute("DROP TABLE quality_checks")
        conn.execute("DROP TABLE quality_policies")
        conn.execute("PRAGMA user_version=0")

    stale_backup = path.with_suffix(path.suffix + ".pre-migration.bak")
    with closing(sqlite3.connect(stale_backup)) as conn:
        conn.execute("CREATE TABLE stale_backup(marker TEXT NOT NULL)")
        conn.execute("INSERT INTO stale_backup(marker) VALUES('old')")
        conn.commit()

    migrated = ProjectDB(path)
    versioned_backup = path.with_name(
        f"{path.name}.pre-v0-to-v{SCHEMA_VERSION}.bak"
    )

    assert versioned_backup.is_file()
    assert versioned_backup != stale_backup
    with migrated.connect() as conn:
        assert int(conn.execute("PRAGMA user_version").fetchone()[0]) == SCHEMA_VERSION
        assert conn.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='quality_policies'"
        ).fetchone()[0] == 1
        assert conn.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='quality_checks'"
        ).fetchone()[0] == 1
    with closing(sqlite3.connect(versioned_backup)) as conn:
        conn.row_factory = sqlite3.Row
        backup_book = dict(conn.execute("SELECT * FROM book WHERE id=1").fetchone())
        backup_chapter = dict(conn.execute("SELECT * FROM chapters WHERE id=?", (chapter_id,)).fetchone())
        assert int(conn.execute("PRAGMA user_version").fetchone()[0]) == 0

    assert dict(migrated.book()) == before
    assert dict(migrated.list_chapters()[0]) == before_chapter
    assert backup_book == before
    assert backup_chapter == before_chapter
    backup_mtime = versioned_backup.stat().st_mtime_ns

    reopened = ProjectDB(path)

    assert reopened.current_quality_policy() is None
    assert versioned_backup.stat().st_mtime_ns == backup_mtime
    assert dict(reopened.book()) == before
    assert dict(reopened.list_chapters()[0]) == before_chapter


def test_schema_v2_without_generation_frame_cap_migrates_to_current(tmp_path: Path) -> None:
    path = tmp_path / "project.sqlite3"
    legacy = ProjectDB(path)
    with legacy.connect() as conn:
        conn.execute("ALTER TABLE segments DROP COLUMN generation_frame_cap")
        conn.execute("PRAGMA user_version=2")
        columns = {str(row[1]) for row in conn.execute("PRAGMA table_info(segments)")}
    assert "generation_frame_cap" not in columns

    migrated = ProjectDB(path)
    backup = path.with_name(f"{path.name}.pre-v2-to-v{SCHEMA_VERSION}.bak")
    with migrated.connect() as conn:
        columns = {str(row[1]) for row in conn.execute("PRAGMA table_info(segments)")}
        version = int(conn.execute("PRAGMA user_version").fetchone()[0])
    assert backup.is_file()
    with closing(sqlite3.connect(backup)) as conn:
        backup_columns = {
            str(row[1]) for row in conn.execute("PRAGMA table_info(segments)")
        }
        backup_version = int(conn.execute("PRAGMA user_version").fetchone()[0])

    assert "generation_frame_cap" in columns
    assert version == SCHEMA_VERSION
    assert "generation_frame_cap" not in backup_columns
    assert backup_version == 2


def test_schema_v3_adds_durable_generation_context(tmp_path: Path) -> None:
    path = tmp_path / "project.sqlite3"
    legacy = ProjectDB(path)
    context_columns = {
        "generation_delivery_mode",
        "generation_repair_round",
        "generation_policy_hash",
    }
    with legacy.connect() as conn:
        for column in reversed(tuple(context_columns)):
            conn.execute(f"ALTER TABLE segments DROP COLUMN {column}")
        conn.execute("PRAGMA user_version=3")
        columns = {str(row[1]) for row in conn.execute("PRAGMA table_info(segments)")}
    assert context_columns.isdisjoint(columns)

    migrated = ProjectDB(path)
    backup = path.with_name(f"{path.name}.pre-v3-to-v{SCHEMA_VERSION}.bak")
    with migrated.connect() as conn:
        columns = {str(row[1]) for row in conn.execute("PRAGMA table_info(segments)")}
        version = int(conn.execute("PRAGMA user_version").fetchone()[0])
    with closing(sqlite3.connect(backup)) as conn:
        backup_columns = {
            str(row[1]) for row in conn.execute("PRAGMA table_info(segments)")
        }
        backup_version = int(conn.execute("PRAGMA user_version").fetchone()[0])

    assert backup.is_file()
    assert context_columns.issubset(columns)
    assert version == SCHEMA_VERSION
    assert context_columns.isdisjoint(backup_columns)
    assert backup_version == 3


def test_chapter_artifact_requires_passing_metadata_for_the_current_quality_policy(
    tmp_path: Path,
) -> None:
    db, _segment_id = _segment_db(tmp_path)
    chapter = db.list_chapters()[0]
    chapter_id = int(chapter["id"])
    chapter_index = int(chapter["chapter_index"])
    output = Path(str(chapter["output_mp3"]))
    output.write_bytes(b"ID3" + b"x" * 5000)
    db.set_current_quality_policy(
        policy_hash="policy-v1",
        policy_version=1,
        policy={"profile": "audiobook"},
    )
    db.register_artifact(
        artifact_key=f"chapter_mp3:{chapter_index}",
        kind="chapter_mp3",
        path=output,
        sha256="a" * 64,
        verified=True,
        metadata={"chapter_id": chapter_id},
    )

    assert db.chapter_artifact_is_current_qa_verified(chapter_index) is False

    quality = db.quality_metadata_for_current_policy()
    db.register_artifact(
        artifact_key=f"chapter_mp3:{chapter_index}",
        kind="chapter_mp3",
        path=output,
        sha256="a" * 64,
        verified=True,
        metadata={"chapter_id": chapter_id, "quality": quality},
    )

    assert db.chapter_artifact_is_current_qa_verified(chapter_index) is False

    db.record_quality_check(
        scope=QUALITY_SCOPE_CHAPTER,
        stage=CHAPTER_POST_ENCODE_QUALITY_STAGE,
        artifact_sha256="b" * 64,
        policy_hash=str(quality["policy_hash"]),
        policy_version=int(quality["policy_version"]),
        verdict=QUALITY_VERDICT_PASS,
        chapter_id=chapter_id,
    )

    assert db.chapter_artifact_is_current_qa_verified(chapter_index) is False

    check_id = db.record_quality_check(
        scope=QUALITY_SCOPE_CHAPTER,
        stage=CHAPTER_POST_ENCODE_QUALITY_STAGE,
        artifact_sha256="a" * 64,
        policy_hash=str(quality["policy_hash"]),
        policy_version=int(quality["policy_version"]),
        verdict=QUALITY_VERDICT_PASS,
        chapter_id=chapter_id,
        metrics={"loudness_lufs": -18.0},
    )
    db.register_artifact(
        artifact_key=f"chapter_mp3:{chapter_index}",
        kind="chapter_mp3",
        path=output,
        sha256="a" * 64,
        verified=True,
        metadata={"chapter_id": chapter_id, "quality": quality},
    )

    latest = db.latest_quality_check(
        scope=QUALITY_SCOPE_CHAPTER,
        stage=CHAPTER_POST_ENCODE_QUALITY_STAGE,
        chapter_id=chapter_id,
    )
    assert latest is not None
    assert int(latest["id"]) == check_id
    assert latest["verdict"] == QUALITY_VERDICT_PASS
    assert db.chapter_artifact_is_current_qa_verified(chapter_index) is True

    db.set_current_quality_policy(
        policy_hash="policy-v2",
        policy_version=2,
        policy={"profile": "audiobook", "true_peak_db": -2.0},
    )

    assert db.chapter_artifact_is_current_qa_verified(chapter_index) is False
    assert db.latest_quality_check(
        scope=QUALITY_SCOPE_CHAPTER,
        stage=CHAPTER_POST_ENCODE_QUALITY_STAGE,
        chapter_id=chapter_id,
    ) is None


def test_segment_audio_requires_matching_current_policy_pass_check(tmp_path: Path) -> None:
    db, segment_id = _segment_db(tmp_path)
    wav_sha256 = "c" * 64
    db.mark_signal_passed(
        segment_id,
        wav_path=tmp_path / "segment.wav",
        wav_sha256=wav_sha256,
        duration=1.0,
        signal={"duration": 1.0},
    )
    db.set_current_quality_policy(
        policy_hash="segment-policy-v1",
        policy_version=1,
        policy={"profile": "audiobook"},
    )
    quality = db.quality_metadata_for_current_policy()

    assert db.segment_audio_is_current_qa_verified(
        segment_id,
        wav_sha256,
        SEGMENT_AUDIO_QUALITY_STAGE,
    ) is False

    db.record_quality_check(
        scope=QUALITY_SCOPE_SEGMENT,
        stage=SEGMENT_ASR_DECODE_QUALITY_STAGE,
        artifact_sha256=wav_sha256,
        policy_hash=str(quality["policy_hash"]),
        policy_version=int(quality["policy_version"]),
        verdict=QUALITY_VERDICT_PASS,
        segment_id=segment_id,
        metrics={"decode_mode": "beam5", "selected": True},
    )

    assert db.segment_audio_is_current_qa_verified(
        segment_id,
        wav_sha256,
        SEGMENT_AUDIO_QUALITY_STAGE,
    ) is False

    db.record_quality_check(
        scope=QUALITY_SCOPE_SEGMENT,
        stage=SEGMENT_AUDIO_QUALITY_STAGE,
        artifact_sha256="d" * 64,
        policy_hash=str(quality["policy_hash"]),
        policy_version=int(quality["policy_version"]),
        verdict=QUALITY_VERDICT_PASS,
        segment_id=segment_id,
    )

    assert db.segment_audio_is_current_qa_verified(
        segment_id,
        wav_sha256,
        SEGMENT_AUDIO_QUALITY_STAGE,
    ) is False

    db.record_quality_check(
        scope=QUALITY_SCOPE_SEGMENT,
        stage=SEGMENT_AUDIO_QUALITY_STAGE,
        artifact_sha256=wav_sha256,
        policy_hash=str(quality["policy_hash"]),
        policy_version=int(quality["policy_version"]),
        verdict=QUALITY_VERDICT_PASS,
        segment_id=segment_id,
    )

    assert db.segment_audio_is_current_qa_verified(
        segment_id,
        wav_sha256,
        SEGMENT_AUDIO_QUALITY_STAGE,
    ) is True

    db.set_current_quality_policy(
        policy_hash="segment-policy-v2",
        policy_version=2,
        policy={"profile": "audiobook", "strict": True},
    )

    assert db.segment_audio_is_current_qa_verified(
        segment_id,
        wav_sha256,
        SEGMENT_AUDIO_QUALITY_STAGE,
    ) is False


def test_schema_v4_migrates_candidate_ledger_with_versioned_backup(tmp_path: Path) -> None:
    path = tmp_path / "project.sqlite3"
    ProjectDB(path)
    with sqlite3.connect(path) as conn:
        conn.execute("DROP TABLE segment_candidates")
        conn.execute("PRAGMA user_version=4")

    migrated = ProjectDB(path)
    backup = path.with_name(f"{path.name}.pre-v4-to-v{SCHEMA_VERSION}.bak")

    with migrated.connect() as conn:
        columns = {str(row[1]) for row in conn.execute("PRAGMA table_info(segment_candidates)")}
        assert int(conn.execute("PRAGMA user_version").fetchone()[0]) == SCHEMA_VERSION
    with sqlite3.connect(backup) as conn:
        backup_table = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='segment_candidates'"
        ).fetchone()
        assert int(conn.execute("PRAGMA user_version").fetchone()[0]) == 4

    assert {
        "segment_id",
        "policy_hash",
        "repair_round",
        "expected_voice_profile_id",
        "expected_pitch_semitones",
        "state",
        "final_check_id",
    } <= columns
    assert backup_table is None
    assert ProjectDB(path).list_segment_candidates() == []


def test_schema_v5_migrates_existing_candidate_perceptual_ledger(tmp_path: Path) -> None:
    db, segment_id, incumbent_sha256, _incumbent_path = _candidate_db(tmp_path)
    candidate_path = tmp_path / "candidates" / "r0.wav"
    candidate = db.allocate_segment_candidate(
        segment_id=segment_id,
        policy_hash="candidate-policy-v1",
        repair_round=0,
        max_repair_rounds=2,
        incumbent_sha256=incumbent_sha256,
        generation_seed=71,
        wav_path=candidate_path,
        candidates_root=tmp_path / "candidates",
    )
    path = db.path
    with sqlite3.connect(path) as conn:
        conn.execute("ALTER TABLE segment_candidates RENAME TO segment_candidates_v6_source")
        conn.execute(
            """
            CREATE TABLE segment_candidates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                segment_id INTEGER NOT NULL REFERENCES segments(id) ON DELETE CASCADE,
                policy_hash TEXT NOT NULL REFERENCES quality_policies(policy_hash),
                repair_round INTEGER NOT NULL CHECK (repair_round >= 0),
                incumbent_sha256 TEXT NOT NULL,
                expected_voice_profile_id INTEGER NOT NULL REFERENCES voice_profiles(id),
                expected_pitch_semitones INTEGER NOT NULL,
                state TEXT NOT NULL,
                tts_attempt INTEGER NOT NULL DEFAULT 0 CHECK (tts_attempt >= 0),
                generation_seed INTEGER NOT NULL,
                wav_path TEXT NOT NULL UNIQUE,
                wav_sha256 TEXT,
                wav_duration REAL,
                signal_json TEXT,
                beam_result_json TEXT,
                greedy_result_json TEXT,
                beam_check_id INTEGER REFERENCES quality_checks(id),
                greedy_check_id INTEGER REFERENCES quality_checks(id),
                final_check_id INTEGER REFERENCES quality_checks(id),
                failure_reason TEXT,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL,
                promoted_at REAL,
                UNIQUE(segment_id, policy_hash, repair_round)
            )
            """
        )
        conn.execute(
            """
            INSERT INTO segment_candidates(
                id,segment_id,policy_hash,repair_round,incumbent_sha256,
                expected_voice_profile_id,expected_pitch_semitones,state,
                tts_attempt,generation_seed,wav_path,wav_sha256,wav_duration,
                signal_json,beam_result_json,greedy_result_json,beam_check_id,
                greedy_check_id,final_check_id,failure_reason,created_at,updated_at,promoted_at
            )
            SELECT
                id,segment_id,policy_hash,repair_round,incumbent_sha256,
                expected_voice_profile_id,expected_pitch_semitones,state,
                tts_attempt,generation_seed,wav_path,wav_sha256,wav_duration,
                signal_json,beam_result_json,greedy_result_json,beam_check_id,
                greedy_check_id,final_check_id,failure_reason,created_at,updated_at,promoted_at
            FROM segment_candidates_v6_source
            """
        )
        conn.execute("DROP TABLE segment_candidates_v6_source")
        conn.execute("PRAGMA user_version=5")

    migrated = ProjectDB(path)
    backup = path.with_name(f"{path.name}.pre-v5-to-v{SCHEMA_VERSION}.bak")
    migrated_candidate = migrated.get_segment_candidate(int(candidate["id"]))
    with migrated.connect() as conn:
        columns = {str(row[1]) for row in conn.execute("PRAGMA table_info(segment_candidates)")}
        version = int(conn.execute("PRAGMA user_version").fetchone()[0])
    with sqlite3.connect(backup) as conn:
        backup_columns = {
            str(row[1]) for row in conn.execute("PRAGMA table_info(segment_candidates)")
        }
        backup_version = int(conn.execute("PRAGMA user_version").fetchone()[0])

    assert version == SCHEMA_VERSION
    assert backup_version == 5
    assert {"repair_budget", "perceptual_required", "perceptual_result_json", "perceptual_check_id"} <= columns
    assert "repair_budget" not in backup_columns
    assert int(migrated_candidate["repair_budget"]) == 1
    assert int(migrated_candidate["perceptual_required"]) == 0
    assert migrated.segment_candidate_resume_plan(segment_id, "candidate-policy-v1")["action"] == "generate"


def test_candidate_allocation_is_idempotent_budgeted_and_policy_scoped(tmp_path: Path) -> None:
    db, segment_id, incumbent_sha256, incumbent_path = _candidate_db(tmp_path)
    candidate_path = tmp_path / "candidates" / "r0.wav"
    with pytest.raises(RuntimeError, match="collides"):
        db.allocate_segment_candidate(
            segment_id=segment_id,
            policy_hash="candidate-policy-v1",
            repair_round=0,
            max_repair_rounds=2,
            incumbent_sha256=incumbent_sha256,
            generation_seed=100,
            wav_path=incumbent_path.with_name(incumbent_path.name.swapcase()),
            candidates_root=tmp_path,
        )
    first = db.allocate_segment_candidate(
        segment_id=segment_id,
        policy_hash="candidate-policy-v1",
        repair_round=0,
        max_repair_rounds=2,
        incumbent_sha256=incumbent_sha256,
        generation_seed=101,
        wav_path=candidate_path,
        candidates_root=tmp_path / "candidates",
    )
    replay = db.allocate_segment_candidate(
        segment_id=segment_id,
        policy_hash="candidate-policy-v1",
        repair_round=0,
        max_repair_rounds=2,
        incumbent_sha256=incumbent_sha256,
        generation_seed=101,
        wav_path=candidate_path,
        candidates_root=tmp_path / "candidates",
    )

    assert int(replay["id"]) == int(first["id"])
    assert db.segment_candidate_resume_plan(segment_id, "candidate-policy-v1", 2)["action"] == "generate"
    with pytest.raises(RuntimeError, match="resume metadata"):
        db.allocate_segment_candidate(
            segment_id=segment_id,
            policy_hash="candidate-policy-v1",
            repair_round=0,
            max_repair_rounds=2,
            incumbent_sha256=incumbent_sha256,
            generation_seed=102,
            wav_path=candidate_path,
            candidates_root=tmp_path / "candidates",
        )
    with pytest.raises(RuntimeError, match="terminal failure"):
        db.allocate_segment_candidate(
            segment_id=segment_id,
            policy_hash="candidate-policy-v1",
            repair_round=1,
            max_repair_rounds=2,
            incumbent_sha256=incumbent_sha256,
            generation_seed=202,
            wav_path=tmp_path / "candidates" / "r1.wav",
            candidates_root=tmp_path / "candidates",
        )

    advanced = db.restart_segment_candidate_generation(
        int(first["id"]),
        expected_generation_seed=101,
        generation_seed=102,
        tts_attempt=1,
    )
    replayed_advance = db.restart_segment_candidate_generation(
        int(first["id"]),
        expected_generation_seed=101,
        generation_seed=102,
        tts_attempt=1,
    )
    assert int(advanced["generation_seed"]) == 102
    assert int(replayed_advance["generation_seed"]) == 102
    db.mark_segment_candidate_tts_failed(
        int(first["id"]),
        expected_generation_seed=102,
        error="TTS failed",
    )
    replayed_failure = db.mark_segment_candidate_tts_failed(
        int(first["id"]),
        expected_generation_seed=102,
        error="TTS failed",
    )
    assert replayed_failure["state"] == "tts_failed"
    with pytest.raises(RuntimeError, match="replay payload"):
        db.mark_segment_candidate_tts_failed(
            int(first["id"]),
            expected_generation_seed=102,
            error="different TTS failure",
        )
    assert db.segment_candidate_resume_plan(segment_id, "candidate-policy-v1", 2) == {
        "segment_id": segment_id,
        "policy_hash": "candidate-policy-v1",
        "action": "allocate",
        "candidate_id": None,
        "repair_round": 1,
    }
    with db.connect() as conn:
        conn.execute("UPDATE segments SET wav_sha256=? WHERE id=?", ("d" * 64, segment_id))
    assert db.segment_candidate_resume_plan(segment_id, "candidate-policy-v1", 2)["action"] == (
        "stale_incumbent"
    )
    with pytest.raises(RuntimeError, match="stale incumbent"):
        db.allocate_segment_candidate(
            segment_id=segment_id,
            policy_hash="candidate-policy-v1",
            repair_round=1,
            max_repair_rounds=2,
            incumbent_sha256=incumbent_sha256,
            generation_seed=202,
            wav_path=tmp_path / "candidates" / "r1.wav",
            candidates_root=tmp_path / "candidates",
        )
    with db.connect() as conn:
        conn.execute("UPDATE segments SET wav_sha256=? WHERE id=?", (incumbent_sha256, segment_id))
    db.set_current_quality_policy(
        policy_hash="candidate-policy-v2",
        policy_version=1,
        policy={"asr": {"repair_rounds": 2}, "changed": True},
    )
    assert db.segment_candidate_resume_plan(segment_id, "candidate-policy-v1", 2)["action"] == (
        "stale_policy"
    )
    with pytest.raises(RuntimeError, match="no longer active"):
        db.restart_segment_candidate_generation(
            int(first["id"]),
            expected_generation_seed=101,
            generation_seed=102,
            tts_attempt=1,
        )


def test_candidate_requires_locked_casting_and_thought_uses_narrator(tmp_path: Path) -> None:
    db, segment_id = _segment_db(tmp_path)
    incumbent_sha256 = "a" * 64
    db.mark_signal_passed(
        segment_id,
        wav_path=tmp_path / "incumbent.wav",
        wav_sha256=incumbent_sha256,
        duration=1.0,
        signal={"duration": 1.0},
        generation_seed=1,
    )
    db.set_current_quality_policy(
        policy_hash="candidate-policy-v1",
        policy_version=1,
        policy={"asr": {"repair_rounds": 1}},
    )
    with pytest.raises(RuntimeError, match="assigned locked voice"):
        db.allocate_segment_candidate(
            segment_id=segment_id,
            policy_hash="candidate-policy-v1",
            repair_round=0,
            max_repair_rounds=1,
            incumbent_sha256=incumbent_sha256,
            generation_seed=10,
            wav_path=tmp_path / "candidates" / "missing-cast.wav",
            candidates_root=tmp_path / "candidates",
        )

    character_profile = db.upsert_voice_profile(
        {
            "voice_key": "thought-character",
            "engine": "vieneu",
            "preset_name": "Character",
            "description": "Character voice",
            "seed": 2,
            "pitch_semitones": 0,
            "status": "ready",
        }
    )
    narrator_profile = db.upsert_voice_profile(
        {
            "voice_key": "NARRATOR",
            "engine": "vieneu",
            "preset_name": "Narrator",
            "description": "Narrator voice",
            "seed": 3,
            "pitch_semitones": -1,
            "status": "ready",
        }
    )
    with db.connect() as conn:
        conn.execute(
            "UPDATE segments SET kind='thought',voice_profile_id=? WHERE id=?",
            (character_profile, segment_id),
        )
    candidate = db.allocate_segment_candidate(
        segment_id=segment_id,
        policy_hash="candidate-policy-v1",
        repair_round=0,
        max_repair_rounds=1,
        incumbent_sha256=incumbent_sha256,
        generation_seed=11,
        wav_path=tmp_path / "candidates" / "thought.wav",
        candidates_root=tmp_path / "candidates",
    )
    assert int(candidate["expected_voice_profile_id"]) == narrator_profile
    assert int(candidate["expected_pitch_semitones"]) == -1


def test_candidate_rejects_casting_change_after_allocation(tmp_path: Path) -> None:
    db, segment_id, incumbent_sha256, _incumbent_path = _candidate_db(tmp_path)
    candidate_path = tmp_path / "candidates" / "casting.wav"
    candidate_sha256 = _write_candidate_artifact(candidate_path, "casting-change")
    candidate = db.allocate_segment_candidate(
        segment_id=segment_id,
        policy_hash="candidate-policy-v1",
        repair_round=0,
        max_repair_rounds=2,
        incumbent_sha256=incumbent_sha256,
        generation_seed=33,
        wav_path=candidate_path,
        candidates_root=tmp_path / "candidates",
    )
    replacement_profile = db.upsert_voice_profile(
        {
            "voice_key": "replacement-voice",
            "engine": "vieneu",
            "preset_name": "Replacement",
            "description": "Replacement voice",
            "seed": 4,
            "pitch_semitones": 0,
            "status": "ready",
        }
    )
    with db.connect() as conn:
        conn.execute(
            "UPDATE segments SET voice_profile_id=? WHERE id=?",
            (replacement_profile, segment_id),
        )
    with pytest.raises(RuntimeError, match="casting changed"):
        _checkpoint_candidate_signal(
            db,
            int(candidate["id"]),
            repair_round=0,
            generation_seed=33,
            wav_path=candidate_path,
            wav_sha256=candidate_sha256,
        )


def test_candidate_promotion_is_atomic_idempotent_and_preserves_incumbent_on_abort(
    tmp_path: Path,
) -> None:
    db, segment_id, incumbent_sha256, _incumbent_path = _candidate_db(tmp_path)
    candidate_path = tmp_path / "candidates" / "r0.wav"
    candidate_sha256 = _write_candidate_artifact(candidate_path, "atomic-promotion")
    candidate = db.allocate_segment_candidate(
        segment_id=segment_id,
        policy_hash="candidate-policy-v1",
        repair_round=0,
        max_repair_rounds=2,
        incumbent_sha256=incumbent_sha256,
        generation_seed=101,
        wav_path=candidate_path,
        candidates_root=tmp_path / "candidates",
    )
    candidate_id = int(candidate["id"])
    _checkpoint_candidate_signal(
        db,
        candidate_id,
        repair_round=0,
        generation_seed=101,
        wav_path=candidate_path,
        wav_sha256=candidate_sha256,
    )
    beam_check = _candidate_decode_check(
        db,
        segment_id=segment_id,
        artifact_sha256=candidate_sha256,
        repair_round=0,
        generation_seed=101,
        confirmation=False,
        verdict="pass",
        reason="ok",
    )
    db.checkpoint_segment_candidate_decode(
        candidate_id,
        quality_check_id=beam_check,
        confirmation=False,
    )
    assert db.get_segment(segment_id)["wav_sha256"] == incumbent_sha256
    assert db.segment_candidate_resume_plan(segment_id, "candidate-policy-v1", 2)["action"] == (
        "decode_greedy"
    )

    greedy_check = _candidate_decode_check(
        db,
        segment_id=segment_id,
        artifact_sha256=candidate_sha256,
        repair_round=0,
        generation_seed=101,
        confirmation=True,
        verdict="pass",
        reason="ok",
    )
    db.checkpoint_segment_candidate_decode(
        candidate_id,
        quality_check_id=greedy_check,
        confirmation=True,
    )
    with db.connect() as conn:
        conn.execute(
            f"""
            CREATE TRIGGER abort_candidate_promotion
            BEFORE UPDATE OF wav_sha256 ON segments
            WHEN NEW.wav_sha256='{candidate_sha256}'
            BEGIN SELECT RAISE(ABORT, 'simulated promotion crash'); END
            """
        )
    with pytest.raises(sqlite3.IntegrityError, match="simulated promotion crash"):
        db.promote_segment_candidate(
            candidate_id,
            validated_wav_sha256=candidate_sha256,
            repair_action="clarity_repair",
            attempt=1,
            warning_code="ASR_CLARITY_REPAIR",
        )
    with db.connect() as conn:
        stray_passes = conn.execute(
            """
            SELECT COUNT(*) FROM quality_checks
            WHERE stage=? AND artifact_sha256=? AND verdict='pass'
            """,
            (SEGMENT_AUDIO_QUALITY_STAGE, candidate_sha256),
        ).fetchone()[0]
        conn.execute("DROP TRIGGER abort_candidate_promotion")
    assert stray_passes == 0
    assert db.get_segment(segment_id)["wav_sha256"] == incumbent_sha256
    assert db.get_segment_candidate(candidate_id)["state"] == "dual_passed"

    promoted = db.promote_segment_candidate(
        candidate_id,
        validated_wav_sha256=candidate_sha256,
        repair_action="clarity_repair",
        attempt=1,
        warning_code="ASR_CLARITY_REPAIR",
    )
    replay = db.promote_segment_candidate(
        candidate_id,
        validated_wav_sha256=candidate_sha256,
        repair_action="clarity_repair",
        attempt=1,
        warning_code="ASR_CLARITY_REPAIR",
    )
    assert promoted["state"] == "promoted"
    assert int(replay["id"]) == candidate_id
    assert db.get_segment(segment_id)["wav_sha256"] == candidate_sha256
    assert db.segment_candidate_resume_plan(segment_id, "candidate-policy-v1", 2)["action"] == (
        "complete"
    )
    with db.connect() as conn:
        pass_count = conn.execute(
            """
            SELECT COUNT(*) FROM quality_checks
            WHERE stage=? AND artifact_sha256=? AND verdict='pass'
            """,
            (SEGMENT_AUDIO_QUALITY_STAGE, candidate_sha256),
        ).fetchone()[0]
    assert pass_count == 1
    final_check = db.latest_quality_check(
        scope=QUALITY_SCOPE_SEGMENT,
        stage=SEGMENT_AUDIO_QUALITY_STAGE,
        segment_id=segment_id,
    )
    final_metrics = json.loads(str(final_check["metrics_json"]))
    assert final_metrics["transcript"] == "Text"
    assert final_metrics["confirmation_verdicts"] == ["pass", "pass"]
    assert len(final_metrics["decode_evidence"]) == 2
    with pytest.raises(RuntimeError, match="replay"):
        db.promote_segment_candidate(
            candidate_id,
            validated_wav_sha256=candidate_sha256,
            repair_action="different_repair",
            attempt=1,
            warning_code="ASR_CLARITY_REPAIR",
        )
    with pytest.raises(RuntimeError, match="replay"):
        db.promote_segment_candidate(
            candidate_id,
            validated_wav_sha256=candidate_sha256,
            repair_action="clarity_repair",
            attempt=1,
            warning_code="DIFFERENT_WARNING",
        )


def test_candidate_requires_current_perceptual_pass_before_atomic_promotion(
    tmp_path: Path,
) -> None:
    db, segment_id, incumbent_sha256, _incumbent_path = _candidate_db(tmp_path)
    candidate, candidate_sha256 = _dual_pass_candidate(
        db,
        segment_id=segment_id,
        incumbent_sha256=incumbent_sha256,
        candidate_path=tmp_path / "candidates" / "perceptual-pass.wav",
        generation_seed=211,
        perceptual_required=True,
    )
    candidate_id = int(candidate["id"])

    assert db.segment_candidate_resume_plan(segment_id, "candidate-policy-v1") == {
        "segment_id": segment_id,
        "policy_hash": "candidate-policy-v1",
        "action": "verify_perceptual",
        "candidate_id": candidate_id,
        "repair_round": 0,
        "state": "dual_passed",
        "generation_seed": 211,
        "tts_attempt": 0,
        "wav_path": str((tmp_path / "candidates" / "perceptual-pass.wav").resolve()),
        "wav_sha256": candidate_sha256,
        "perceptual_required": True,
    }
    with pytest.raises(RuntimeError, match="before perceptual QA passes"):
        db.promote_segment_candidate(
            candidate_id,
            validated_wav_sha256=candidate_sha256,
            repair_action="clarity_repair",
            attempt=1,
        )

    perceptual_check_id = _candidate_perceptual_check(
        db,
        segment_id=segment_id,
        artifact_sha256=candidate_sha256,
        verdict="pass",
        perceptual_verdict="ok",
        reason="PERCEPTUAL_OK",
        review_required=False,
    )
    checkpointed = db.checkpoint_segment_candidate_perceptual(
        candidate_id,
        quality_check_id=perceptual_check_id,
    )
    replay = db.checkpoint_segment_candidate_perceptual(
        candidate_id,
        quality_check_id=perceptual_check_id,
    )

    assert checkpointed["state"] == "dual_passed"
    assert int(replay["perceptual_check_id"]) == perceptual_check_id
    assert db.segment_candidate_resume_plan(segment_id, "candidate-policy-v1")["action"] == (
        "promote"
    )
    promoted = db.promote_segment_candidate(
        candidate_id,
        validated_wav_sha256=candidate_sha256,
        repair_action="clarity_repair",
        attempt=1,
    )
    final_check = db.latest_quality_check(
        scope=QUALITY_SCOPE_SEGMENT,
        stage=SEGMENT_AUDIO_QUALITY_STAGE,
        segment_id=segment_id,
    )
    final_metrics = json.loads(str(final_check["metrics_json"]))

    assert promoted["state"] == "promoted"
    assert db.get_segment(segment_id)["wav_sha256"] == candidate_sha256
    assert db.segment_audio_is_current_qa_verified(
        segment_id,
        candidate_sha256,
        SEGMENT_PERCEPTUAL_QUALITY_STAGE,
    )
    assert final_metrics["perceptual_required"] is True
    assert final_metrics["perceptual_quality_check_id"] == perceptual_check_id
    assert final_metrics["perceptual_evidence"]["verdict"] == "ok"


def test_candidate_perceptual_review_is_terminal_and_advances_same_budget(
    tmp_path: Path,
) -> None:
    db, segment_id, incumbent_sha256, _incumbent_path = _candidate_db(tmp_path)
    candidate, candidate_sha256 = _dual_pass_candidate(
        db,
        segment_id=segment_id,
        incumbent_sha256=incumbent_sha256,
        candidate_path=tmp_path / "candidates" / "perceptual-review.wav",
        generation_seed=221,
        perceptual_required=True,
    )
    candidate_id = int(candidate["id"])
    wrong_pitch_check = _candidate_perceptual_check(
        db,
        segment_id=segment_id,
        artifact_sha256=candidate_sha256,
        verdict="pass",
        perceptual_verdict="ok",
        reason="PERCEPTUAL_OK",
        review_required=False,
        baseline_pitch_semitones=1,
    )
    with pytest.raises(RuntimeError, match="baseline pitch"):
        db.checkpoint_segment_candidate_perceptual(
            candidate_id,
            quality_check_id=wrong_pitch_check,
        )

    review_check = _candidate_perceptual_check(
        db,
        segment_id=segment_id,
        artifact_sha256=candidate_sha256,
        verdict="inconclusive",
        perceptual_verdict="review",
        reason="PERCEPTUAL_NATURALNESS_REVIEW",
        review_required=True,
    )
    reviewed = db.checkpoint_segment_candidate_perceptual(
        candidate_id,
        quality_check_id=review_check,
    )
    plan = db.segment_candidate_resume_plan(segment_id, "candidate-policy-v1")

    assert reviewed["state"] == "dual_failed"
    assert plan == {
        "segment_id": segment_id,
        "policy_hash": "candidate-policy-v1",
        "action": "allocate",
        "candidate_id": None,
        "repair_round": 1,
    }
    with pytest.raises(RuntimeError, match="repair budget differs"):
        db.segment_candidate_resume_plan(segment_id, "candidate-policy-v1", 1)
    with pytest.raises(RuntimeError, match="perceptual requirements"):
        db.allocate_segment_candidate(
            segment_id=segment_id,
            policy_hash="candidate-policy-v1",
            repair_round=1,
            max_repair_rounds=2,
            incumbent_sha256=incumbent_sha256,
            generation_seed=222,
            wav_path=tmp_path / "candidates" / "r1.wav",
            candidates_root=tmp_path / "candidates",
            perceptual_required=False,
        )


def test_candidate_decode_and_promotion_reject_tampered_locked_provenance(
    tmp_path: Path,
) -> None:
    db, segment_id, incumbent_sha256, _incumbent_path = _candidate_db(tmp_path)
    candidate_path = tmp_path / "candidates" / "r0.wav"
    candidate_sha256 = _write_candidate_artifact(candidate_path, "tampered-provenance")
    candidate = db.allocate_segment_candidate(
        segment_id=segment_id,
        policy_hash="candidate-policy-v1",
        repair_round=0,
        max_repair_rounds=2,
        incumbent_sha256=incumbent_sha256,
        generation_seed=301,
        wav_path=candidate_path,
        candidates_root=tmp_path / "candidates",
    )
    candidate_id = int(candidate["id"])
    _checkpoint_candidate_signal(
        db,
        candidate_id,
        repair_round=0,
        generation_seed=301,
        wav_path=candidate_path,
        wav_sha256=candidate_sha256,
    )
    contradictory_check = _candidate_decode_check(
        db,
        segment_id=segment_id,
        artifact_sha256=candidate_sha256,
        repair_round=0,
        generation_seed=301,
        confirmation=False,
        verdict="pass",
        reason="contradictory",
        metrics_overrides={"verdict": "mismatch", "passed": False},
    )
    with pytest.raises(RuntimeError, match="contradicts"):
        db.checkpoint_segment_candidate_decode(
            candidate_id,
            quality_check_id=contradictory_check,
            confirmation=False,
        )
    wrong_voice_check = db.record_quality_check(
        scope=QUALITY_SCOPE_SEGMENT,
        stage=SEGMENT_ASR_DECODE_QUALITY_STAGE,
        segment_id=segment_id,
        artifact_sha256=candidate_sha256,
        policy_hash="candidate-policy-v1",
        policy_version=1,
        verdict="pass",
        metrics={
            "verdict": "pass",
            "passed": True,
            "decode_mode": "beam5",
            "selected": True,
            "delivery_mode": "clarity",
            "repair_round": 0,
            "generation_seed": 301,
            "spoken_text_sha256": "2" * 64,
            "voice_profile_id": 99,
            "pitch_semitones": 0,
            "effective_pitch_semitones": 0,
            "pitch_variant_skipped": False,
            "pitch_variant_mixed": False,
        },
    )
    with pytest.raises(RuntimeError, match="locked provenance"):
        db.checkpoint_segment_candidate_decode(
            candidate_id,
            quality_check_id=wrong_voice_check,
            confirmation=False,
        )
    missing_transcript_check = _candidate_decode_check(
        db,
        segment_id=segment_id,
        artifact_sha256=candidate_sha256,
        repair_round=0,
        generation_seed=301,
        confirmation=False,
        verdict="pass",
        reason="ok",
        metrics_overrides={"transcript": ""},
    )
    with pytest.raises(RuntimeError, match="requires a transcript"):
        db.checkpoint_segment_candidate_decode(
            candidate_id,
            quality_check_id=missing_transcript_check,
            confirmation=False,
        )
    assert db.get_segment_candidate(candidate_id)["state"] == "signal_passed"


@pytest.mark.parametrize("damage", ["missing", "tampered"])
def test_candidate_promotion_invalidates_missing_or_tampered_artifact(
    tmp_path: Path,
    damage: str,
) -> None:
    db, segment_id, incumbent_sha256, _incumbent_path = _candidate_db(tmp_path)
    candidate_path = tmp_path / "candidates" / "damaged.wav"
    candidate_sha256 = _write_candidate_artifact(candidate_path, damage)
    candidate = db.allocate_segment_candidate(
        segment_id=segment_id,
        policy_hash="candidate-policy-v1",
        repair_round=0,
        max_repair_rounds=2,
        incumbent_sha256=incumbent_sha256,
        generation_seed=321,
        wav_path=candidate_path,
        candidates_root=tmp_path / "candidates",
    )
    candidate_id = int(candidate["id"])
    _checkpoint_candidate_signal(
        db,
        candidate_id,
        repair_round=0,
        generation_seed=321,
        wav_path=candidate_path,
        wav_sha256=candidate_sha256,
    )
    for confirmation in (False, True):
        check_id = _candidate_decode_check(
            db,
            segment_id=segment_id,
            artifact_sha256=candidate_sha256,
            repair_round=0,
            generation_seed=321,
            confirmation=confirmation,
            verdict="pass",
            reason="ok",
        )
        db.checkpoint_segment_candidate_decode(
            candidate_id,
            quality_check_id=check_id,
            confirmation=confirmation,
        )
    if damage == "missing":
        candidate_path.unlink()
    else:
        candidate_path.write_bytes(b"tampered-candidate")

    invalid = db.promote_segment_candidate(
        candidate_id,
        validated_wav_sha256=candidate_sha256,
        attempt=1,
    )
    assert invalid["state"] == "invalid"
    expected_failure_text = "missing" if damage == "missing" else "checksum"
    assert expected_failure_text in str(invalid["failure_reason"])
    assert db.get_segment(segment_id)["wav_sha256"] == incumbent_sha256
    assert db.segment_candidate_resume_plan(segment_id, "candidate-policy-v1", 2)["action"] == (
        "allocate"
    )
    replay = db.mark_segment_candidate_invalid(
        candidate_id,
        expected_wav_sha256=candidate_sha256,
        reason=str(invalid["failure_reason"]),
    )
    assert replay["state"] == "invalid"
    with pytest.raises(RuntimeError, match="replay payload"):
        db.mark_segment_candidate_invalid(
            candidate_id,
            expected_wav_sha256=candidate_sha256,
            reason="different invalidation reason",
        )


@pytest.mark.parametrize(
    ("blocking_flag", "signal_overrides", "decode_overrides"),
    [
        (
            "pitch_variant_skipped",
            {"pitch_variant_skipped": 1.0},
            {"pitch_variant_skipped": True},
        ),
        (
            "pitch_variant_mixed",
            {"pitch_variant_mixed": 1.0, "effective_pitch_semitones": None},
            {"pitch_variant_mixed": True, "effective_pitch_semitones": None},
        ),
        ("generation_endpoint_active", {"generation_endpoint_active": 1.0}, {}),
        ("pace_outlier", {"pace_outlier": 1.0}, {}),
    ],
)
def test_candidate_promotion_rejects_blocking_signal_flags(
    tmp_path: Path,
    blocking_flag: str,
    signal_overrides: dict,
    decode_overrides: dict,
) -> None:
    db, segment_id, incumbent_sha256, _incumbent_path = _candidate_db(tmp_path)
    candidate_path = tmp_path / "candidates" / "r0.wav"
    candidate_sha256 = _write_candidate_artifact(
        candidate_path,
        f"blocking-{blocking_flag}",
    )
    candidate = db.allocate_segment_candidate(
        segment_id=segment_id,
        policy_hash="candidate-policy-v1",
        repair_round=0,
        max_repair_rounds=2,
        incumbent_sha256=incumbent_sha256,
        generation_seed=351,
        wav_path=candidate_path,
        candidates_root=tmp_path / "candidates",
    )
    candidate_id = int(candidate["id"])
    _checkpoint_candidate_signal(
        db,
        candidate_id,
        repair_round=0,
        generation_seed=351,
        wav_path=candidate_path,
        wav_sha256=candidate_sha256,
        signal_overrides=signal_overrides,
    )
    for confirmation in (False, True):
        check_id = _candidate_decode_check(
            db,
            segment_id=segment_id,
            artifact_sha256=candidate_sha256,
            repair_round=0,
            generation_seed=351,
            confirmation=confirmation,
            verdict="pass",
            reason="ok",
            metrics_overrides=decode_overrides,
        )
        db.checkpoint_segment_candidate_decode(
            candidate_id,
            quality_check_id=check_id,
            confirmation=confirmation,
        )
    blocked = db.get_segment_candidate(candidate_id)
    assert blocked["state"] == "dual_failed"
    assert blocking_flag in str(blocked["failure_reason"])
    with pytest.raises(RuntimeError, match="before both"):
        db.promote_segment_candidate(
            candidate_id,
            validated_wav_sha256=candidate_sha256,
            attempt=1,
        )
    assert db.get_segment(segment_id)["wav_sha256"] == incumbent_sha256
    assert db.get_segment_candidate(candidate_id)["state"] == "dual_failed"


def test_candidate_exhaustion_keeps_incumbent_and_uses_incumbent_evidence(
    tmp_path: Path,
) -> None:
    db, segment_id, incumbent_sha256, incumbent_path = _candidate_db(tmp_path)
    trigger_check = db.record_quality_check(
        scope=QUALITY_SCOPE_SEGMENT,
        stage=SEGMENT_AUDIO_QUALITY_STAGE,
        segment_id=segment_id,
        artifact_sha256=incumbent_sha256,
        policy_hash="candidate-policy-v1",
        policy_version=1,
        verdict="repair",
        metrics={
            "reason": "ASR_MISMATCH",
            "transcript": "primary transcript",
            "similarity": 0.7,
            "wer": 0.4,
        },
        failure_codes=("ASR_MISMATCH",),
    )
    first = db.allocate_segment_candidate(
        segment_id=segment_id,
        policy_hash="candidate-policy-v1",
        repair_round=0,
        max_repair_rounds=2,
        incumbent_sha256=incumbent_sha256,
        generation_seed=401,
        wav_path=tmp_path / "candidates" / "r0.wav",
        candidates_root=tmp_path / "candidates",
    )
    db.mark_segment_candidate_tts_failed(
        int(first["id"]),
        expected_generation_seed=401,
        error="round zero failed",
    )
    with pytest.raises(RuntimeError, match="every configured"):
        db.finalize_segment_candidate_exhaustion(
            segment_id=segment_id,
            policy_hash="candidate-policy-v1",
            max_repair_rounds=2,
            incumbent_sha256=incumbent_sha256,
            trigger_quality_check_id=trigger_check,
            error="repair exhausted",
            warning_code="ASR_MISMATCH_UNRESOLVED",
        )
    second = db.allocate_segment_candidate(
        segment_id=segment_id,
        policy_hash="candidate-policy-v1",
        repair_round=1,
        max_repair_rounds=2,
        incumbent_sha256=incumbent_sha256,
        generation_seed=402,
        wav_path=tmp_path / "candidates" / "r1.wav",
        candidates_root=tmp_path / "candidates",
    )
    db.mark_segment_candidate_tts_failed(
        int(second["id"]),
        expected_generation_seed=402,
        error="round one failed",
    )
    final_check_id = db.finalize_segment_candidate_exhaustion(
        segment_id=segment_id,
        policy_hash="candidate-policy-v1",
        max_repair_rounds=2,
        incumbent_sha256=incumbent_sha256,
        trigger_quality_check_id=trigger_check,
        error="repair exhausted",
        warning_code="ASR_MISMATCH_UNRESOLVED",
    )
    replay_check_id = db.finalize_segment_candidate_exhaustion(
        segment_id=segment_id,
        policy_hash="candidate-policy-v1",
        max_repair_rounds=2,
        incumbent_sha256=incumbent_sha256,
        trigger_quality_check_id=trigger_check,
        error="repair exhausted",
        warning_code="ASR_MISMATCH_UNRESOLVED",
    )
    final = db.get_segment(segment_id)
    check = db.latest_quality_check(
        scope=QUALITY_SCOPE_SEGMENT,
        stage=SEGMENT_AUDIO_QUALITY_STAGE,
        segment_id=segment_id,
    )
    metrics = json.loads(str(check["metrics_json"]))

    assert replay_check_id == final_check_id
    assert final["wav_path"] == str(incumbent_path.resolve())
    assert final["wav_sha256"] == incumbent_sha256
    assert final["asr_text"] == "primary transcript"
    assert metrics["incumbent_sha256"] == incumbent_sha256
    assert [attempt["state"] for attempt in metrics["candidate_attempts"]] == [
        "tts_failed",
        "tts_failed",
    ]
    for changed_payload in (
        {"error": "different error"},
        {"warning_code": "DIFFERENT_WARNING"},
        {"final_verdict": "inconclusive"},
        {"failure_codes": ("DIFFERENT_FAILURE",)},
    ):
        replay_payload = {
            "segment_id": segment_id,
            "policy_hash": "candidate-policy-v1",
            "max_repair_rounds": 2,
            "incumbent_sha256": incumbent_sha256,
            "trigger_quality_check_id": trigger_check,
            "error": "repair exhausted",
            "warning_code": "ASR_MISMATCH_UNRESOLVED",
            **changed_payload,
        }
        with pytest.raises(RuntimeError, match="replay payload"):
            db.finalize_segment_candidate_exhaustion(**replay_payload)
