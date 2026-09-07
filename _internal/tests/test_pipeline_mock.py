from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

import ebook_reader.pipeline as pipeline_module
from ebook_reader.asr_contract import ASR_LOCKED_NAME_ANCHOR_REVIEW
from ebook_reader.asr import (
    adjudicate_locked_name_anchors,
    ASR_INCONCLUSIVE,
    ASR_LOCKED_NAME_ANCHOR_MISMATCH,
    ASR_LOCKED_NAME_CANONICAL_PASS,
    ASR_MISMATCH,
    ASR_PASS,
    LOCKED_NAME_ANCHOR_METRICS_KEY,
    LOCKED_NAME_ANCHOR_METRICS_VERSION,
)
from ebook_reader.asr_contract import COLLAPSED_SHORT_CONTEXT_MODE
from ebook_reader.audio_io import AudioQualityError, ChapterQualityError, atomic_write_wav
from ebook_reader.config import build_settings
from ebook_reader.database import (
    GENERATION_STRATEGY_SPLIT,
    PRONUNCIATION_DELIVERY_LOCKED,
    PRONUNCIATION_DELIVERY_SOURCE,
    QUALITY_SCOPE_CHAPTER,
    QUALITY_SCOPE_SEGMENT,
    SEGMENT_ASR_DECODE_QUALITY_STAGE,
    SEGMENT_AUDIO_QUALITY_STAGE,
)
from ebook_reader.io_utils import sha256_file, stable_int
from ebook_reader.models import ResourceLevel
from ebook_reader.pipeline import (
    HIGH_QUALITY_ALLOWED_SEGMENT_WARNINGS,
    BookPipeline,
    CriticalResourceStop,
    _candidate_budget_exhausted_on_perceptual_review,
    unresolved_asr_is_fatal,
)
from ebook_reader.perceptual_contract import PERCEPTUAL_NATURALNESS_REVIEW_CODE
from ebook_reader.project import create_or_open_project
from ebook_reader.quality_policy import (
    ANALYSIS_CASTING_STAGE,
    CHAPTER_QUALITY_STAGE,
    QUALITY_POLICY_VERSION,
    TEXT_SEGMENTATION_STAGE,
    quality_policy_hash,
)
from ebook_reader.resource_manager import ResourceSnapshot
from ebook_reader.text_processing import (
    CLAUSE_SPLIT_MAX_CHARS,
    CLAUSE_SPLIT_STRATEGY,
    SENTENCE_SPLIT_MAX_CHARS,
    SENTENCE_SPLIT_STRATEGY,
    SPLIT_MAX_CHARS_FIELD,
    SPLIT_STRATEGY_FIELD,
    split_text_for_strategy,
)
from ebook_reader.tts_contract import (
    HA_VOCALIZATION_DELIVERY_PROFILE,
    HA_VOCALIZATION_FINAL_SAMPLES_FIELD,
    HA_VOCALIZATION_MAX_NEW_FRAMES,
    HA_VOCALIZATION_MAX_NEW_FRAMES_FIELD,
    HA_VOCALIZATION_ORIGINAL_SAMPLES_FIELD,
    HA_VOCALIZATION_PADDING_SAMPLES_FIELD,
    HA_VOCALIZATION_PROFILE_FIELD,
    HA_VOCALIZATION_SAMPLE_RATE_FIELD,
    HA_VOCALIZATION_TARGET_SAMPLES_FIELD,
    HA_VOCALIZATION_TEMPERATURE_FIELD,
    HA_VOCALIZATION_TOP_P_FIELD,
)


def test_candidate_item_validates_vocalization_against_source_segment() -> None:
    pipeline = object.__new__(BookPipeline)
    pipeline._require_segment_candidate_pronunciation_delivery = (
        lambda _segment, _candidate: (
            PRONUNCIATION_DELIVERY_LOCKED,
            "“Ha ha.”",
            [],
        )
    )
    segment = {
        "id": 9,
        "seq": 8,
        "stable_id": "gasp-segment",
        "text": "“Ha…”",
        "signal_json": None,
    }
    signal = {
        "duration": 1.6,
        HA_VOCALIZATION_PROFILE_FIELD: HA_VOCALIZATION_DELIVERY_PROFILE,
        HA_VOCALIZATION_TEMPERATURE_FIELD: 0.55,
        HA_VOCALIZATION_TOP_P_FIELD: 0.82,
        HA_VOCALIZATION_MAX_NEW_FRAMES_FIELD: HA_VOCALIZATION_MAX_NEW_FRAMES,
        HA_VOCALIZATION_SAMPLE_RATE_FIELD: 48_000,
        HA_VOCALIZATION_ORIGINAL_SAMPLES_FIELD: 76_800,
        HA_VOCALIZATION_TARGET_SAMPLES_FIELD: 76_800,
        HA_VOCALIZATION_PADDING_SAMPLES_FIELD: 0,
        HA_VOCALIZATION_FINAL_SAMPLES_FIELD: 76_800,
        "generation_endpoint_active": 0.0,
    }
    candidate = {
        "id": 1,
        "wav_path": "gasp.wav",
        "wav_sha256": "a" * 64,
        "wav_duration": 1.6,
        "signal_json": json.dumps(signal),
        "generation_seed": 123,
        "repair_round": 0,
        "policy_hash": "policy",
        "pronunciation_delivery_variant": PRONUNCIATION_DELIVERY_LOCKED,
        "expected_spoken_text_sha256": "b" * 64,
    }

    item = pipeline._segment_candidate_item(segment, candidate)

    assert item["text"] == "“Ha…”"
    assert item["signal_json"] == candidate["signal_json"]
    assert item["segment_candidate_id"] == 1


class FakeTTS:
    def __init__(self, settings, db):
        self.settings = settings
        self.db = db
        self.unload_calls = 0
        self.synthesize_calls = 0
        self.delivery_modes: list[str] = []
        self.seed_salts: list[str] = []

    def prepare_voice_presets(self):
        return None

    def unload_idle_models(self, keep_engine=None):
        return None

    def unload_all(self):
        self.unload_calls += 1

    def generation_seed(self, row, seed_salt=""):
        if str(seed_salt).startswith("asr_clarity_candidate_"):
            profile = self.db.voice_profile(int(row["voice_profile_id"]))
            return stable_int(
                f"segment::{row['stable_id']}::{profile['voice_key']}::{seed_salt}"
            )
        return 1

    def spoken_text(self, row):
        spoken_text, _anchors = self.spoken_text_with_anchors(row)
        return spoken_text

    def spoken_text_with_anchors(self, row):
        return str(row["text"]), []

    def synthesize_atomic(
        self,
        row,
        output,
        seed_salt="",
        *,
        repair_short_utterance=False,
        delivery_mode="primary",
        pronunciation_delivery_variant=PRONUNCIATION_DELIVERY_LOCKED,
    ):
        self.synthesize_calls += 1
        self.delivery_modes.append(str(delivery_mode))
        self.seed_salts.append(str(seed_salt))
        seed = self.generation_seed(row, seed_salt)
        phase = float(seed % 997) / 997.0
        audio = np.sin(
            np.linspace(phase, 50 + phase, 96000, dtype=np.float32)
        ) * 0.12
        spoken_text = self.spoken_text(row)
        checksum, metrics = atomic_write_wav(
            output,
            audio,
            48000,
            spoken_text,
            self.settings,
            segment=row,
        )
        profile = self.db.voice_profile(int(row["voice_profile_id"]))
        pitch_semitones = int(profile["pitch_semitones"] or 0)
        metrics.update(
            {
                "tts_delivery_mode": str(delivery_mode).strip().casefold(),
                "spoken_text_sha256": hashlib.sha256(
                    spoken_text.encode("utf-8")
                ).hexdigest(),
                "pronunciation_delivery_variant": (
                    pronunciation_delivery_variant
                ),
                "voice_profile_id": int(profile["id"]),
                "pitch_semitones": pitch_semitones,
                "effective_pitch_semitones": pitch_semitones,
                "pitch_variant_skipped": 0.0,
                "pitch_variant_mixed": 0.0,
            }
        )
        return checksum, metrics, seed


class LockedNameVariantFakeTTS(FakeTTS):
    LOCKED_SURFACE = "Tracy"
    LOCKED_SPOKEN_FORM = "Trây-si"

    def spoken_text_with_anchors(
        self,
        row,
        *,
        pronunciation_delivery_variant=PRONUNCIATION_DELIVERY_LOCKED,
    ):
        source_text = str(row["text"])
        spoken_form = (
            self.LOCKED_SURFACE
            if pronunciation_delivery_variant == PRONUNCIATION_DELIVERY_SOURCE
            else self.LOCKED_SPOKEN_FORM
        )
        spoken_text = source_text.replace(self.LOCKED_SURFACE, spoken_form)
        anchors = []
        source_cursor = 0
        spoken_cursor = 0
        occurrence = 0
        while True:
            source_start = source_text.find(self.LOCKED_SURFACE, source_cursor)
            if source_start < 0:
                break
            occurrence += 1
            source_end = source_start + len(self.LOCKED_SURFACE)
            spoken_start = spoken_text.find(spoken_form, spoken_cursor)
            spoken_end = spoken_start + len(spoken_form)
            anchors.append(
                {
                    "pronunciation_id": 7,
                    "surface": self.LOCKED_SURFACE,
                    "normalized_surface": self.LOCKED_SURFACE.casefold(),
                    "matched_surface": self.LOCKED_SURFACE,
                    "spoken_form": spoken_form,
                    "canonical_spoken_form": self.LOCKED_SPOKEN_FORM,
                    "pronunciation_delivery_variant": (
                        pronunciation_delivery_variant
                    ),
                    "source": "english_name_transliteration",
                    "source_start": source_start,
                    "source_end": source_end,
                    "spoken_start": spoken_start,
                    "spoken_end": spoken_end,
                    "occurrence": occurrence,
                    "order": occurrence,
                }
            )
            source_cursor = source_end
            spoken_cursor = spoken_end
        return spoken_text, anchors

    def spoken_text(
        self,
        row,
        *,
        pronunciation_delivery_variant=PRONUNCIATION_DELIVERY_LOCKED,
    ):
        spoken_text, _anchors = self.spoken_text_with_anchors(
            row,
            pronunciation_delivery_variant=pronunciation_delivery_variant,
        )
        return spoken_text

    def synthesize_atomic(
        self,
        row,
        output,
        seed_salt="",
        *,
        repair_short_utterance=False,
        delivery_mode="primary",
        pronunciation_delivery_variant=PRONUNCIATION_DELIVERY_LOCKED,
    ):
        del repair_short_utterance
        self.synthesize_calls += 1
        self.delivery_modes.append(str(delivery_mode))
        self.seed_salts.append(str(seed_salt))
        seed = self.generation_seed(row, seed_salt)
        phase = float(seed % 997) / 997.0
        audio = np.sin(
            np.linspace(phase, 50 + phase, 96_000, dtype=np.float32)
        ) * 0.12
        spoken_text = self.spoken_text(
            row,
            pronunciation_delivery_variant=pronunciation_delivery_variant,
        )
        checksum, metrics = atomic_write_wav(
            output,
            audio,
            48_000,
            spoken_text,
            self.settings,
            segment=row,
        )
        profile = self.db.voice_profile(int(row["voice_profile_id"]))
        pitch_semitones = int(profile["pitch_semitones"] or 0)
        metrics.update(
            {
                "tts_delivery_mode": str(delivery_mode).strip().casefold(),
                "spoken_text_sha256": hashlib.sha256(
                    spoken_text.encode("utf-8")
                ).hexdigest(),
                "pronunciation_delivery_variant": (
                    pronunciation_delivery_variant
                ),
                "voice_profile_id": int(profile["id"]),
                "pitch_semitones": pitch_semitones,
                "effective_pitch_semitones": pitch_semitones,
                "pitch_variant_skipped": 0.0,
                "pitch_variant_mixed": 0.0,
            }
        )
        return checksum, metrics, seed


class PassPerceptualVerifier:
    def __init__(self) -> None:
        self.verify_calls = 0
        self.unload_calls = 0

    def verify(self, _wav, _preset, *, pitch_semitones=0, prefetched_score=None):
        self.verify_calls += 1
        return {
            "verdict": "ok",
            "reason": "PERCEPTUAL_WITHIN_VOICE_BASELINE",
            "score": 4.0,
            "baseline_score": 4.0,
            "baseline_delta": 0.0,
            "baseline_pitch_semitones": pitch_semitones,
            "review_required": False,
            "duration_seconds": 2.0,
        }

    def unload(self) -> None:
        self.unload_calls += 1


class FakeNotifier:
    def __init__(self):
        self.critical_calls = []

    def notify(self, *_args, **_kwargs):
        return True

    def critical_stop(self, *args, **kwargs):
        self.critical_calls.append((args, kwargs))


class ScriptedShortTTS:
    def __init__(self, outcomes: list[dict[str, float] | BaseException]) -> None:
        self.outcomes = list(outcomes)
        self.calls: list[dict[str, object]] = []
        self.generation_seed_salts: list[str] = []
        self.unload_calls = 0
        self.settings = None
        self.db = None

    def bind(self, settings, db):
        self.settings = settings
        self.db = db
        return self

    def _seed(self, seed_salt: str) -> int:
        return len(self.calls) + len(seed_salt) + 1

    def generation_seed(self, _row, seed_salt=""):
        self.generation_seed_salts.append(str(seed_salt))
        return self._seed(str(seed_salt))

    def spoken_text(self, row):
        return str(row["text"])

    def synthesize_atomic(
        self,
        row,
        output,
        seed_salt="",
        *,
        repair_short_utterance=False,
        delivery_mode="primary",
    ):
        seed = self._seed(str(seed_salt))
        self.calls.append(
            {
                "seed_salt": seed_salt,
                "repair_short_utterance": repair_short_utterance,
                "generation_frame_cap": row["generation_frame_cap"],
                "delivery_mode": delivery_mode,
            }
        )
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        if self.settings is None or self.db is None:
            return "a" * 64, dict(outcome), seed
        # Default to a duration this text could actually take to say. A flat 1.0 s stood in
        # for every length, so a 191-character sentence came out six times faster than human
        # speech; tests that care about duration still pass their own.
        duration = float(outcome.get("duration", _plausible_duration(str(row["text"]))))
        sample_rate = int(self.settings["tts"]["sample_rate"])
        sample_count = max(1, round(duration * sample_rate))
        audio = np.sin(np.linspace(0, 50, sample_count, dtype=np.float32)) * 0.12
        checksum, metrics = atomic_write_wav(
            output,
            audio,
            sample_rate,
            str(row["text"]),
            self.settings,
            segment=row,
        )
        metrics.update(dict(outcome))
        profile = self.db.voice_profile(int(row["voice_profile_id"]))
        pitch_semitones = int(profile["pitch_semitones"] or 0)
        metrics.update(
            {
                "tts_delivery_mode": str(delivery_mode).strip().casefold(),
                "spoken_text_sha256": hashlib.sha256(
                    str(row["text"]).encode("utf-8")
                ).hexdigest(),
                "voice_profile_id": int(profile["id"]),
                "pitch_semitones": pitch_semitones,
                "effective_pitch_semitones": pitch_semitones,
                "pitch_variant_skipped": 0.0,
                "pitch_variant_mixed": 0.0,
            }
        )
        return checksum, metrics, seed

    def unload_all(self):
        self.unload_calls += 1


class PassingShortVerifier:
    def __init__(self, first_verdict: str = ASR_PASS) -> None:
        self.calls = 0
        self.unload_calls = 0
        self.first_verdict = first_verdict

    def verify(self, expected, _wav_path, *, confirmation=False):
        self.calls += 1
        if self.calls == 1 and self.first_verdict != ASR_PASS:
            return {
                "passed": False,
                "verdict": self.first_verdict,
                "transcript": "sai nội dung",
                "similarity": 0.0,
                "wer": 1.0,
                "reason": (
                    "ASR_MISMATCH"
                    if self.first_verdict == ASR_MISMATCH
                    else "ASR_INCONCLUSIVE"
                ),
                "repairable": False,
                "severe": False,
                "confirmation": confirmation,
            }
        return {
            "passed": True,
            "verdict": ASR_PASS,
            "transcript": expected,
            "similarity": 1.0,
            "wer": 0.0,
            "reason": "ok",
            "repairable": False,
            "severe": False,
            "confirmation": confirmation,
        }

    def can_verify_repeated_short(self, _expected):
        return False

    def unload(self):
        self.unload_calls += 1


def _assign_locked_test_narrator(db) -> int:
    profile_id = db.upsert_voice_profile(
        {
            "voice_key": "narrator",
            "engine": "vieneu",
            "preset_name": "Xuân Vĩnh",
            "description": "Locked test narrator",
            "seed": 1,
            "pitch_semitones": 0,
            "status": "ready",
        }
    )
    with db.connect() as conn:
        conn.execute(
            "UPDATE segments SET voice_profile_id=?",
            (profile_id,),
        )
    return profile_id


def _short_tts_pipeline(
    tmp_path: Path,
    *,
    repair_rounds: int = 2,
    source_text: str = "“Điên rồi!”",
):
    source = tmp_path / "001.txt"
    source.write_text(source_text, encoding="utf-8")
    settings = build_settings(
        overrides={
            "tts": {"max_retries": 4},
            "asr": {"repair_rounds": repair_rounds},
        }
    )
    paths, db, settings = create_or_open_project(
        [source],
        tmp_path / "out",
        settings,
        "Short ceiling",
    )
    pipeline = BookPipeline(
        paths=paths,
        db=db,
        settings=settings,
        pause_requested=lambda: False,
        stop_requested=lambda: False,
        emit=lambda _kind, _payload: None,
    )
    pipeline._recover()
    pipeline._ensure_segments()
    _assign_locked_test_narrator(db)
    chapter = db.list_chapters()[0]
    row = db.list_segments(chapter_id=int(chapter["id"]))[0]
    pipeline._resource_gate = lambda *_args, **_kwargs: None
    pipeline._progress = lambda *_args, **_kwargs: None
    return pipeline, chapter, row


def _plausible_duration(text: str) -> float:
    """How long this text would actually take to read.

    A fixed 1.92 s used to stand in for any length of text, which made a 191-character
    sentence 5.9 times faster than human speech. Nothing checked, so nothing complained -
    until the rate check started subtracting pauses and the fake audio finally crossed the
    "impossibly fast" line it had always been on the wrong side of. Deriving the duration
    keeps the stand-in inside physics.
    """
    from ebook_reader.audio_io import PAUSE_GROUP_SECONDS, pause_group_count

    speakable = sum(char.isalnum() for char in str(text))
    return speakable / 16.9 + PAUSE_GROUP_SECONDS * pause_group_count(str(text))


def _checkpoint_short_ceiling_incumbent(
    pipeline: BookPipeline,
    row,
    *,
    duration: float | None = None,
) -> None:
    output = pipeline._chunk_path(row)
    if duration is None:
        duration = _plausible_duration(str(row["text"]))
    sample_rate = int(pipeline.settings["tts"]["sample_rate"])
    audio = np.sin(
        np.linspace(0, 50, round(duration * sample_rate), dtype=np.float32)
    ) * 0.12
    checksum, metrics = atomic_write_wav(
        output,
        audio,
        sample_rate,
        str(row["text"]),
        pipeline.settings,
        segment=row,
    )
    profile = pipeline.db.voice_profile(int(row["voice_profile_id"]))
    pitch_semitones = int(profile["pitch_semitones"] or 0)
    metrics.update(
        {
            "generation_ceiling_hit": 1.0,
            "generation_endpoint_active": 1.0,
            "trailing_rms": 0.05,
            "tts_delivery_mode": "primary",
            "spoken_text_sha256": hashlib.sha256(
                str(row["text"]).encode("utf-8")
            ).hexdigest(),
            "voice_profile_id": int(profile["id"]),
            "pitch_semitones": pitch_semitones,
            "effective_pitch_semitones": pitch_semitones,
            "pitch_variant_skipped": 0.0,
            "pitch_variant_mixed": 0.0,
        }
    )
    pipeline.db.mark_signal_passed(
        int(row["id"]),
        wav_path=output,
        wav_sha256=checksum,
        duration=float(metrics["duration"]),
        signal=metrics,
        generation_seed=1,
        warning_codes=["TTS_GENERATION_CEILING_REACHED"],
    )


def _asr_signal_pipeline(tmp_path: Path, *, repair_rounds: int):
    source = tmp_path / "001.txt"
    expected = "Một câu đủ dài để kiểm tra nội dung bằng hai lượt giải mã độc lập."
    source.write_text(expected, encoding="utf-8")
    settings = build_settings(
        overrides={
            "asr": {"repair_rounds": repair_rounds},
            # These tests read `perceptual_result` off the candidates they promote, so they
            # have to ask for perceptual QA: high_quality stopped enabling it on 2026-09-07.
            # docs/PERCEPTUAL_QA_COST.md.
            "perceptual_qa": {"enabled": True},
            "tts": {
                "min_seconds_per_100_chars": 0.2,
                "pace_chars_per_second": {"normal": [1.0, 100.0]},
            },
        }
    )
    paths, db, settings = create_or_open_project(
        [source],
        tmp_path / "out",
        settings,
        "ASR evidence",
    )
    pipeline = BookPipeline(
        paths=paths,
        db=db,
        settings=settings,
        pause_requested=lambda: False,
        stop_requested=lambda: False,
        emit=lambda _kind, _payload: None,
    )
    pipeline.tts = FakeTTS(settings, db)
    pipeline.perceptual_qa = PassPerceptualVerifier()
    pipeline._recover()
    pipeline._ensure_segments()
    _assign_locked_test_narrator(db)
    chapter = db.list_chapters()[0]
    row = db.list_segments(chapter_id=int(chapter["id"]))[0]
    wav = pipeline._chunk_path(row)
    audio = np.sin(np.linspace(0, 50, 96_000, dtype=np.float32)) * 0.12
    checksum, metrics = atomic_write_wav(
        wav,
        audio,
        48_000,
        str(row["text"]),
        settings,
        segment=row,
    )
    db.mark_signal_passed(
        int(row["id"]),
        wav_path=wav,
        wav_sha256=checksum,
        duration=float(metrics["duration"]),
        signal=metrics,
    )
    pipeline._resource_gate = lambda *_args, **_kwargs: None
    pipeline._progress = lambda *_args, **_kwargs: None
    return pipeline, chapter, dict(db.get_segment(int(row["id"]))), expected


def test_severe_asr_mismatch_is_fatal_even_under_warning_policy() -> None:
    assert unresolved_asr_is_fatal({"severe": True}, "warning_continue") is True
    assert unresolved_asr_is_fatal({"passed": False, "severe": False}, "warning_continue") is True
    assert unresolved_asr_is_fatal({"severe": False}, "fail") is True


def _asr_result(
    verdict: str,
    transcript: str,
    *,
    similarity: float,
    wer: float,
) -> dict[str, object]:
    return {
        "passed": verdict == ASR_PASS,
        "verdict": verdict,
        "transcript": transcript,
        "similarity": similarity,
        "wer": wer,
        "reason": "ok" if verdict == ASR_PASS else "ASR_MISMATCH",
        "repairable": verdict == ASR_MISMATCH,
        "severe": False,
    }


def _locked_lucien_anchor(*, spoken_start: int = 4) -> dict[str, object]:
    return {
        "pronunciation_id": 7,
        "surface": "Lucien",
        "normalized_surface": "lucien",
        "matched_surface": "Lucien",
        "spoken_form": "Lu-si-en",
        "source": "english_name_transliteration",
        "source_start": 4,
        "source_end": 10,
        "spoken_start": spoken_start,
        "spoken_end": spoken_start + len("Lu-si-en"),
        "occurrence": 1,
        "order": 1,
    }


class _VariantAnchorProbeTTS:
    def __init__(self, source_anchors: list[dict[str, object]]) -> None:
        self.source_anchors = source_anchors

    def spoken_text_with_anchors(
        self,
        _row,
        *,
        pronunciation_delivery_variant=PRONUNCIATION_DELIVERY_LOCKED,
    ):
        locked_anchor = {
            **_locked_lucien_anchor(spoken_start=0),
            "spoken_form": "Lu-si-en",
            "canonical_spoken_form": "Lu-si-en",
            "pronunciation_delivery_variant": PRONUNCIATION_DELIVERY_LOCKED,
            "source_start": 0,
            "source_end": 6,
        }
        if pronunciation_delivery_variant == PRONUNCIATION_DELIVERY_SOURCE:
            return "Lucien gọi.", [dict(anchor) for anchor in self.source_anchors]
        return "Lu-si-en gọi.", [locked_anchor]

    def synthesize_atomic(
        self,
        _row,
        _output,
        *,
        pronunciation_delivery_variant=PRONUNCIATION_DELIVERY_LOCKED,
    ):
        raise AssertionError(pronunciation_delivery_variant)


@pytest.mark.parametrize("source_anchors", [[], [_locked_lucien_anchor()]])
def test_source_variant_rejects_missing_or_drifted_locked_name_anchors(
    source_anchors: list[dict[str, object]],
) -> None:
    if source_anchors:
        source_anchors[0]["pronunciation_delivery_variant"] = (
            PRONUNCIATION_DELIVERY_SOURCE
        )
        source_anchors[0]["spoken_form"] = "Lucien"
        source_anchors[0]["source_start"] = 0
        source_anchors[0]["source_end"] = 5
    pipeline = BookPipeline.__new__(BookPipeline)
    pipeline.tts = _VariantAnchorProbeTTS(source_anchors)

    with pytest.raises(RuntimeError, match="anchors drifted"):
        pipeline._segment_candidate_pronunciation_delivery(
            {"text": "Lucien gọi."},
            1,
            source_variant_requested=True,
        )


@pytest.mark.parametrize(
    ("identity_field", "drifted_value"),
    [
        ("surface", "Lucy"),
        ("normalized_surface", "lucy"),
        ("matched_surface", "Lucian"),
        ("source", "analysis"),
        ("canonical_spoken_form", "Lu-xi-en"),
    ],
)
def test_source_variant_rejects_same_span_anchor_with_drifted_name_identity(
    identity_field: str,
    drifted_value: str,
) -> None:
    source_anchor = {
        **_locked_lucien_anchor(spoken_start=0),
        "spoken_form": "Lucien",
        "canonical_spoken_form": "Lu-si-en",
        "pronunciation_delivery_variant": PRONUNCIATION_DELIVERY_SOURCE,
        "source_start": 0,
        "source_end": 6,
    }
    source_anchor[identity_field] = drifted_value
    pipeline = BookPipeline.__new__(BookPipeline)
    pipeline.tts = _VariantAnchorProbeTTS([source_anchor])

    with pytest.raises(RuntimeError, match="anchors drifted"):
        pipeline._segment_candidate_pronunciation_delivery(
            {"text": "Lucien gọi."},
            1,
            source_variant_requested=True,
        )


def test_source_variant_is_not_scheduled_without_locked_name_anchors() -> None:
    class NoAnchorTTS:
        def spoken_text_with_anchors(
            self,
            row,
            *,
            pronunciation_delivery_variant=PRONUNCIATION_DELIVERY_LOCKED,
        ):
            if pronunciation_delivery_variant == PRONUNCIATION_DELIVERY_SOURCE:
                raise AssertionError("source variant must not be materialized")
            return str(row["text"]), []

        def synthesize_atomic(
            self,
            _row,
            _output,
            *,
            pronunciation_delivery_variant=PRONUNCIATION_DELIVERY_LOCKED,
        ):
            raise AssertionError(pronunciation_delivery_variant)

    pipeline = BookPipeline.__new__(BookPipeline)
    pipeline.tts = NoAnchorTTS()

    variant, spoken_text, anchors = (
        pipeline._segment_candidate_pronunciation_delivery(
            {"text": "Không có tên khóa."},
            1,
            source_variant_requested=True,
        )
    )

    assert variant == PRONUNCIATION_DELIVERY_LOCKED
    assert spoken_text == "Không có tên khóa."
    assert anchors == []


def test_odd_round_keeps_locked_pronunciation_without_failure_request() -> None:
    source_anchor = {
        **_locked_lucien_anchor(spoken_start=0),
        "spoken_form": "Lucien",
        "canonical_spoken_form": "Lu-si-en",
        "pronunciation_delivery_variant": PRONUNCIATION_DELIVERY_SOURCE,
        "source_start": 0,
        "source_end": 6,
    }
    pipeline = BookPipeline.__new__(BookPipeline)
    pipeline.tts = _VariantAnchorProbeTTS([source_anchor])

    variant, spoken_text, anchors = (
        pipeline._segment_candidate_pronunciation_delivery(
            {"text": "Lucien gọi."},
            1,
        )
    )

    assert variant == PRONUNCIATION_DELIVERY_LOCKED
    assert spoken_text == "Lu-si-en gọi."
    assert anchors[0]["spoken_form"] == "Lu-si-en"


def _locked_name_decode_failure() -> dict[str, object]:
    return {
        "verdict": ASR_MISMATCH,
        "passed": False,
        "reason": ASR_LOCKED_NAME_ANCHOR_MISMATCH,
        "repairable": True,
        "failure_codes": [ASR_LOCKED_NAME_ANCHOR_MISMATCH],
        LOCKED_NAME_ANCHOR_METRICS_KEY: {
            "version": LOCKED_NAME_ANCHOR_METRICS_VERSION,
            "status": "fail",
            "adjudicated": True,
            "passed": False,
            "failure_codes": [ASR_LOCKED_NAME_ANCHOR_MISMATCH],
            "repeat_count": 1,
            "anchor_count": 1,
            "required_occurrence_count": 1,
            "matched_occurrence_count": 0,
        },
    }


def _locked_name_decode_pass(
    *,
    pronunciation_variant: str = PRONUNCIATION_DELIVERY_SOURCE,
) -> dict[str, object]:
    return {
        "verdict": ASR_PASS,
        "passed": True,
        "reason": "ok",
        "repairable": False,
        "failure_codes": [],
        "pronunciation_delivery_variant": pronunciation_variant,
        LOCKED_NAME_ANCHOR_METRICS_KEY: {
            "version": LOCKED_NAME_ANCHOR_METRICS_VERSION,
            "status": "pass",
            "adjudicated": True,
            "passed": True,
            "failure_codes": [],
            "repeat_count": 1,
            "anchor_count": 1,
            "required_occurrence_count": 1,
            "matched_occurrence_count": 1,
        },
    }


@pytest.mark.parametrize("failure_index", [0, 1])
def test_mixed_prior_decodes_keep_locked_pronunciation(
    failure_index: int,
) -> None:
    evidence = [
        {
            "verdict": ASR_PASS,
            "passed": True,
            "reason": "ok",
            "repairable": False,
            "failure_codes": [],
            LOCKED_NAME_ANCHOR_METRICS_KEY: {
                "version": LOCKED_NAME_ANCHOR_METRICS_VERSION,
                "status": "pass",
                "adjudicated": True,
                "passed": True,
                "failure_codes": [],
            },
        },
        {
            "verdict": ASR_MISMATCH,
            "passed": False,
            "reason": "ASR_MISMATCH",
            "repairable": True,
            "failure_codes": ["ASR_MISMATCH"],
        },
    ]
    evidence[failure_index] = _locked_name_decode_failure()

    assert (
        BookPipeline._prior_decodes_request_source_pronunciation(evidence)
        is False
    )


def test_both_prior_decodes_must_request_source_pronunciation() -> None:
    evidence = [_locked_name_decode_failure(), _locked_name_decode_failure()]

    assert BookPipeline._prior_decodes_request_source_pronunciation(evidence) is True


def test_prior_decode_consensus_validates_both_evidence_rows() -> None:
    malformed = _locked_name_decode_failure()
    malformed[LOCKED_NAME_ANCHOR_METRICS_KEY]["matched_occurrence_count"] = 2

    with pytest.raises(RuntimeError, match="internally inconsistent"):
        BookPipeline._prior_decodes_request_source_pronunciation(
            [_locked_name_decode_failure(), malformed]
        )


def test_final_round_retries_source_after_one_complete_pass() -> None:
    failure = _locked_name_decode_failure()
    failure["pronunciation_delivery_variant"] = PRONUNCIATION_DELIVERY_SOURCE

    assert (
        BookPipeline._prior_source_candidate_requests_final_retry(
            [_locked_name_decode_pass(), failure]
        )
        is True
    )


def test_final_round_does_not_retain_source_after_dual_anchor_failure() -> None:
    failures = [_locked_name_decode_failure(), _locked_name_decode_failure()]
    for failure in failures:
        failure["pronunciation_delivery_variant"] = PRONUNCIATION_DELIVERY_SOURCE
        metrics = failure[LOCKED_NAME_ANCHOR_METRICS_KEY]
        metrics["anchor_count"] = 2
        metrics["required_occurrence_count"] = 2
        metrics["matched_occurrence_count"] = 1

    assert (
        BookPipeline._prior_source_candidate_requests_final_retry(failures)
        is False
    )


def test_final_round_ignores_plain_locked_passes_without_anchor_evidence() -> None:
    passing = {
        "verdict": ASR_PASS,
        "passed": True,
        "reason": "VOCALIZATION_ASR_COMPATIBLE",
        "repairable": False,
        "failure_codes": [],
        "pronunciation_delivery_variant": PRONUNCIATION_DELIVERY_LOCKED,
        LOCKED_NAME_ANCHOR_METRICS_KEY: None,
    }

    assert (
        BookPipeline._prior_source_candidate_requests_final_retry(
            [dict(passing), dict(passing)]
        )
        is False
    )


@pytest.mark.parametrize("anchor_evidence", [None, "missing"])
def test_source_pass_without_anchor_evidence_still_fails_closed(
    anchor_evidence: object,
) -> None:
    passing = _locked_name_decode_pass()
    if anchor_evidence == "missing":
        passing.pop(LOCKED_NAME_ANCHOR_METRICS_KEY)
    else:
        passing[LOCKED_NAME_ANCHOR_METRICS_KEY] = anchor_evidence
    failure = _locked_name_decode_failure()
    failure["pronunciation_delivery_variant"] = PRONUNCIATION_DELIVERY_SOURCE

    with pytest.raises(RuntimeError, match="lacks structured anchor evidence"):
        BookPipeline._prior_source_candidate_requests_final_retry(
            [passing, failure]
        )


def test_final_round_forces_split_after_dual_source_anchor_failure() -> None:
    failures = [_locked_name_decode_failure(), _locked_name_decode_failure()]
    for failure in failures:
        failure["pronunciation_delivery_variant"] = (
            PRONUNCIATION_DELIVERY_SOURCE
        )

    assert (
        BookPipeline._prior_source_candidate_requests_final_split(failures)
        is True
    )


def test_final_round_split_rejects_mixed_pronunciation_evidence() -> None:
    failures = [_locked_name_decode_failure(), _locked_name_decode_failure()]
    failures[0]["pronunciation_delivery_variant"] = (
        PRONUNCIATION_DELIVERY_SOURCE
    )
    failures[1]["pronunciation_delivery_variant"] = (
        PRONUNCIATION_DELIVERY_LOCKED
    )

    with pytest.raises(RuntimeError, match="mixes pronunciation variants"):
        BookPipeline._prior_source_candidate_requests_final_split(failures)


def test_final_round_source_retry_rejects_malformed_pass_evidence() -> None:
    passing = _locked_name_decode_pass()
    passing[LOCKED_NAME_ANCHOR_METRICS_KEY]["matched_occurrence_count"] = 0
    failure = _locked_name_decode_failure()
    failure["pronunciation_delivery_variant"] = PRONUNCIATION_DELIVERY_SOURCE

    with pytest.raises(RuntimeError, match="internally inconsistent"):
        BookPipeline._prior_source_candidate_requests_final_retry(
            [passing, failure]
        )


def test_plain_content_mismatch_does_not_request_source_pronunciation() -> None:
    result = {
        "verdict": ASR_MISMATCH,
        "passed": False,
        "reason": "ASR_MISMATCH",
        "repairable": True,
        "failure_codes": ["ASR_MISMATCH"],
        LOCKED_NAME_ANCHOR_METRICS_KEY: {
            "version": LOCKED_NAME_ANCHOR_METRICS_VERSION,
            "status": "pass",
            "adjudicated": True,
            "passed": True,
            "failure_codes": [],
        },
    }

    assert BookPipeline._decode_requests_source_pronunciation(result) is False


def test_inconsistent_locked_name_failure_evidence_fails_closed() -> None:
    result = _locked_name_decode_failure()
    result[LOCKED_NAME_ANCHOR_METRICS_KEY]["passed"] = True

    with pytest.raises(RuntimeError, match="internally inconsistent"):
        BookPipeline._decode_requests_source_pronunciation(result)


def test_migrated_odd_round_locked_candidate_reconstructs_stored_variant() -> None:
    pipeline = BookPipeline.__new__(BookPipeline)
    pipeline.tts = _VariantAnchorProbeTTS([])
    row = {"text": "Lucien gọi."}
    locked_text, _anchors = pipeline.tts.spoken_text_with_anchors(row)
    candidate = {
        "repair_round": 1,
        "pronunciation_delivery_variant": PRONUNCIATION_DELIVERY_LOCKED,
        "expected_spoken_text_sha256": hashlib.sha256(
            locked_text.encode("utf-8")
        ).hexdigest(),
    }

    variant, spoken_text, anchors = (
        pipeline._require_segment_candidate_pronunciation_delivery(
            row,
            candidate,
        )
    )

    assert variant == PRONUNCIATION_DELIVERY_LOCKED
    assert spoken_text == "Lu-si-en gọi."
    assert anchors[0]["pronunciation_delivery_variant"] == (
        PRONUNCIATION_DELIVERY_LOCKED
    )


def test_even_final_round_source_candidate_reconstructs_stored_variant() -> None:
    source_anchor = {
        **_locked_lucien_anchor(spoken_start=0),
        "spoken_form": "Lucien",
        "canonical_spoken_form": "Lu-si-en",
        "pronunciation_delivery_variant": PRONUNCIATION_DELIVERY_SOURCE,
        "source_start": 0,
        "source_end": 6,
    }
    pipeline = BookPipeline.__new__(BookPipeline)
    pipeline.tts = _VariantAnchorProbeTTS([source_anchor])
    row = {"text": "Lucien gọi."}
    source_text, _anchors = pipeline.tts.spoken_text_with_anchors(
        row,
        pronunciation_delivery_variant=PRONUNCIATION_DELIVERY_SOURCE,
    )
    candidate = {
        "repair_round": 4,
        "pronunciation_delivery_variant": PRONUNCIATION_DELIVERY_SOURCE,
        "expected_spoken_text_sha256": hashlib.sha256(
            source_text.encode("utf-8")
        ).hexdigest(),
    }

    variant, spoken_text, anchors = (
        pipeline._require_segment_candidate_pronunciation_delivery(
            row,
            candidate,
        )
    )

    assert variant == PRONUNCIATION_DELIVERY_SOURCE
    assert spoken_text == "Lucien gọi."
    assert anchors[0]["spoken_form"] == "Lucien"


def test_repeated_short_decode_cannot_replace_better_direct_failure(
    tmp_path: Path,
) -> None:
    pipeline, chapter, row, _expected = _asr_signal_pipeline(tmp_path, repair_rounds=0)

    class RepeatedVerifier:
        def unload(self) -> None:
            return None

        def can_verify_repeated_short(self, _text: str) -> bool:
            return True

        def verify(self, _text: str, _wav: Path, *, confirmation: bool = False):
            return _asr_result(
                ASR_MISMATCH,
                "kết quả trực tiếp gần đúng",
                similarity=0.81 if confirmation else 0.80,
                wer=0.60,
            )

        def verify_repeated_short(
            self,
            _text: str,
            _wav: Path,
            *,
            confirmation: bool = False,
        ):
            return _asr_result(
                ASR_MISMATCH,
                "kết quả lặp sai nặng",
                similarity=0.177,
                wer=1.0,
            )

    pipeline._verify_chapter_audio(chapter, RepeatedVerifier())

    fresh = pipeline.db.get_segment(int(row["id"]))
    assert fresh["status"] == "failed"
    assert float(fresh["asr_similarity"]) == pytest.approx(0.81)
    assert float(fresh["asr_wer"]) == pytest.approx(0.60)
    final_check = pipeline.db.latest_quality_check(
        scope=QUALITY_SCOPE_SEGMENT,
        stage=SEGMENT_AUDIO_QUALITY_STAGE,
        segment_id=int(row["id"]),
    )
    assert final_check is not None
    final_metrics = json.loads(str(final_check["metrics_json"]))
    assert final_metrics["transcript"] == "kết quả trực tiếp gần đúng"
    with pipeline.db.connect() as conn:
        checks = list(
            conn.execute(
                "SELECT metrics_json FROM quality_checks WHERE stage=? ORDER BY id",
                (SEGMENT_ASR_DECODE_QUALITY_STAGE,),
            )
        )
    metrics = [json.loads(str(check["metrics_json"])) for check in checks]
    assert [item["context_mode"] for item in metrics] == [
        "direct",
        "repeat3",
        "direct",
        "repeat3",
    ]
    assert [item["selected"] for item in metrics] == [True, False, True, False]
    assert all(len(item["spoken_text_sha256"]) == 64 for item in metrics)


def test_repeated_short_pass_can_promote_a_direct_mismatch(tmp_path: Path) -> None:
    pipeline, chapter, row, expected = _asr_signal_pipeline(tmp_path, repair_rounds=0)

    class RepeatedPassVerifier:
        direct_calls = 0
        repeated_calls = 0

        def unload(self) -> None:
            return None

        def can_verify_repeated_short(self, _text: str) -> bool:
            return True

        def verify(self, _text: str, _wav: Path, *, confirmation: bool = False):
            self.direct_calls += 1
            return _asr_result(
                ASR_MISMATCH,
                "không rõ",
                similarity=0.2,
                wer=1.0,
            )

        def verify_repeated_short(
            self,
            _text: str,
            _wav: Path,
            *,
            confirmation: bool = False,
        ):
            self.repeated_calls += 1
            return _asr_result(ASR_PASS, expected, similarity=1.0, wer=0.0)

    verifier = RepeatedPassVerifier()
    pipeline._verify_chapter_audio(chapter, verifier)

    fresh = pipeline.db.get_segment(int(row["id"]))
    assert fresh["status"] == "verified"
    assert verifier.direct_calls == 1
    assert verifier.repeated_calls == 1
    final_check = pipeline.db.latest_quality_check(
        scope=QUALITY_SCOPE_SEGMENT,
        stage=SEGMENT_AUDIO_QUALITY_STAGE,
        segment_id=int(row["id"]),
    )
    assert final_check is not None
    final_metrics = json.loads(str(final_check["metrics_json"]))
    assert final_metrics["repeated_short_context"] is True
    assert [item["selected"] for item in final_metrics["decode_evidence"]] == [
        False,
        True,
    ]


def test_locked_name_anchor_can_promote_exact_repeated_short_decode(
    tmp_path: Path,
) -> None:
    pipeline, chapter, row, _expected = _asr_signal_pipeline(tmp_path, repair_rounds=0)
    pipeline.tts.spoken_text_with_anchors = lambda _row: (
        "Lu-si-en!",
        [_locked_lucien_anchor(spoken_start=0)],
    )

    class RepeatedAnchorVerifier:
        def unload(self) -> None:
            return None

        def can_verify_repeated_short(self, _text: str) -> bool:
            return True

        def verify(self, _text: str, _wav: Path, *, confirmation: bool = False):
            return _asr_result(ASR_PASS, "Lucy", similarity=0.96, wer=0.1)

        def verify_repeated_short(
            self,
            _text: str,
            _wav: Path,
            *,
            confirmation: bool = False,
        ):
            return _asr_result(
                ASR_MISMATCH,
                "Lucien Lu-si-en Lusien",
                similarity=0.45,
                wer=2 / 3,
            )

    pipeline._verify_chapter_audio(chapter, RepeatedAnchorVerifier())

    fresh = pipeline.db.get_segment(int(row["id"]))
    assert fresh["status"] == "verified"
    final_check = pipeline.db.latest_quality_check(
        scope=QUALITY_SCOPE_SEGMENT,
        stage=SEGMENT_AUDIO_QUALITY_STAGE,
        segment_id=int(row["id"]),
    )
    assert final_check is not None
    final_metrics = json.loads(str(final_check["metrics_json"]))
    assert final_metrics["selected_context_mode"] == "repeat3"
    assert final_metrics["reason"] == ASR_LOCKED_NAME_CANONICAL_PASS
    assert final_metrics["locked_name_anchor_metrics"]["repeat_count"] == 3
    assert final_metrics["locked_name_anchor_metrics"]["passed"] is True
    assert final_metrics["locked_name_anchor_metrics"]["canonical_promoted"] is True
    assert [item["selected"] for item in final_metrics["decode_evidence"]] == [
        False,
        True,
    ]


def test_collapsed_repeated_short_locked_name_decode_is_auditable(
    tmp_path: Path,
) -> None:
    pipeline, chapter, row, _expected = _asr_signal_pipeline(
        tmp_path,
        repair_rounds=0,
    )
    pipeline.tts.spoken_text_with_anchors = lambda _row: (
        "Anh Lu-si-en!",
        [_locked_lucien_anchor(spoken_start=4)],
    )

    class CollapsedRepeatedVerifier:
        def unload(self) -> None:
            return None

        def can_verify_repeated_short(self, _text: str) -> bool:
            return True

        def verify(self, _text: str, _wav: Path, *, confirmation: bool = False):
            return _asr_result(ASR_PASS, "Anh Lucy", similarity=0.80, wer=0.50)

        def verify_repeated_short(
            self,
            _text: str,
            _wav: Path,
            *,
            confirmation: bool = False,
        ):
            return _asr_result(
                ASR_MISMATCH,
                "Anh Lũ Sĩ En",
                similarity=1 / 3,
                wer=2 / 3,
            )

    pipeline._verify_chapter_audio(chapter, CollapsedRepeatedVerifier())

    fresh = pipeline.db.get_segment(int(row["id"]))
    assert fresh["status"] == "verified"
    final_check = pipeline.db.latest_quality_check(
        scope=QUALITY_SCOPE_SEGMENT,
        stage=SEGMENT_AUDIO_QUALITY_STAGE,
        segment_id=int(row["id"]),
    )
    assert final_check is not None
    final_metrics = json.loads(str(final_check["metrics_json"]))
    assert final_metrics["selected_context_mode"] == COLLAPSED_SHORT_CONTEXT_MODE
    assert final_metrics["requested_repeat_count"] == 3
    assert final_metrics["effective_repeat_count"] == 1
    assert final_metrics["repeated_short_context"] is True
    assert [
        item["context_mode"] for item in final_metrics["decode_evidence"]
    ] == ["direct", "repeat3", COLLAPSED_SHORT_CONTEXT_MODE]
    assert [item["selected"] for item in final_metrics["decode_evidence"]] == [
        False,
        False,
        True,
    ]
    selected = final_metrics["decode_evidence"][-1]
    assert selected["requested_repeat_count"] == 3
    assert selected["effective_repeat_count"] == 1
    assert selected[LOCKED_NAME_ANCHOR_METRICS_KEY]["repeat_count"] == 1


def test_locked_name_canonical_metrics_preserve_the_v7_lucien_candidate(
    tmp_path: Path,
) -> None:
    pipeline, chapter, row, _expected = _asr_signal_pipeline(tmp_path, repair_rounds=0)
    pipeline.tts.spoken_text_with_anchors = lambda _row: (
        "Tên của mình là Lu-si-en.",
        [_locked_lucien_anchor(spoken_start=16)],
    )

    class CanonicalAnchorVerifier:
        def unload(self) -> None:
            return None

        def can_verify_repeated_short(self, _text: str) -> bool:
            return False

        def verify(self, _text: str, _wav: Path, *, confirmation: bool = False):
            return _asr_result(
                ASR_MISMATCH,
                "Tên của mình là Lucien.",
                similarity=0.875,
                wer=3 / 7,
            )

    pipeline._verify_chapter_audio(chapter, CanonicalAnchorVerifier())

    fresh = pipeline.db.get_segment(int(row["id"]))
    assert fresh["status"] == "verified"
    assert fresh["asr_similarity"] == 0.875
    assert fresh["asr_wer"] == 3 / 7
    final_check = pipeline.db.latest_quality_check(
        scope=QUALITY_SCOPE_SEGMENT,
        stage=SEGMENT_AUDIO_QUALITY_STAGE,
        segment_id=int(row["id"]),
    )
    assert final_check is not None
    final_metrics = json.loads(str(final_check["metrics_json"]))
    assert final_metrics["reason"] == ASR_LOCKED_NAME_CANONICAL_PASS
    anchor_metrics = final_metrics["locked_name_anchor_metrics"]
    assert anchor_metrics["canonical_min_similarity"] == 0.78
    assert anchor_metrics["canonical_max_wer"] == 0.3
    assert anchor_metrics["canonical_promoted"] is True


def test_confirmation_decode_can_use_locked_name_canonical_metrics(
    tmp_path: Path,
) -> None:
    pipeline, chapter, row, _expected = _asr_signal_pipeline(tmp_path, repair_rounds=1)
    pipeline.tts.spoken_text_with_anchors = lambda _row: (
        "Tên của mình là Lu-si-en.",
        [_locked_lucien_anchor(spoken_start=16)],
    )
    scripted_results = [
        _asr_result(ASR_PASS, "Tên của mình là Lucy.", similarity=0.92, wer=0.2),
        _asr_result(
            ASR_MISMATCH,
            "Tên của mình là Lucien.",
            similarity=0.875,
            wer=3 / 7,
        ),
    ]

    class ConfirmationAnchorVerifier:
        def unload(self) -> None:
            return None

        def can_verify_repeated_short(self, _text: str) -> bool:
            return False

        def verify(self, _text: str, _wav: Path, *, confirmation: bool = False):
            return scripted_results.pop(0)

    pipeline._verify_chapter_audio(chapter, ConfirmationAnchorVerifier())

    fresh = pipeline.db.get_segment(int(row["id"]))
    assert fresh["status"] == "verified"
    assert pipeline.tts.delivery_modes == []
    final_check = pipeline.db.latest_quality_check(
        scope=QUALITY_SCOPE_SEGMENT,
        stage=SEGMENT_AUDIO_QUALITY_STAGE,
        segment_id=int(row["id"]),
    )
    assert final_check is not None
    final_metrics = json.loads(str(final_check["metrics_json"]))
    assert final_metrics["confirmation_decode"] is True
    assert final_metrics["reason"] == ASR_LOCKED_NAME_CANONICAL_PASS
    assert [
        item["reason"] for item in final_metrics["decode_evidence"]
    ] == ["ASR_LOCKED_NAME_ANCHOR_MISMATCH", ASR_LOCKED_NAME_CANONICAL_PASS]


def test_locked_name_anchor_forces_clarity_after_two_aggregate_asr_passes(
    tmp_path: Path,
) -> None:
    pipeline, chapter, row, _expected = _asr_signal_pipeline(tmp_path, repair_rounds=1)
    pipeline.tts.spoken_text_with_anchors = lambda _row: (
        "Anh Lu-si-en đã đến.",
        [_locked_lucien_anchor()],
    )
    scripted_results = [
        _asr_result(ASR_PASS, "Anh Lucy đã đến.", similarity=0.96, wer=0.1),
        _asr_result(ASR_PASS, "Anh Lucian đã đến.", similarity=0.96, wer=0.1),
        _asr_result(ASR_PASS, "Anh Lucien đã đến.", similarity=1.0, wer=0.0),
        _asr_result(ASR_PASS, "Anh Lu-si-en đã đến.", similarity=1.0, wer=0.0),
    ]

    class AnchorVerifier:
        def unload(self) -> None:
            return None

        def can_verify_repeated_short(self, _text: str) -> bool:
            return False

        def verify(self, _text: str, _wav: Path, *, confirmation: bool = False):
            return scripted_results.pop(0)

    pipeline._verify_chapter_audio(chapter, AnchorVerifier())

    fresh = pipeline.db.get_segment(int(row["id"]))
    assert fresh["status"] == "verified"
    assert pipeline.tts.delivery_modes == ["clarity"]
    with pipeline.db.connect() as conn:
        decode_checks = list(
            conn.execute(
                "SELECT verdict,metrics_json FROM quality_checks WHERE stage=? ORDER BY id",
                (SEGMENT_ASR_DECODE_QUALITY_STAGE,),
            )
        )
    assert [str(check["verdict"]) for check in decode_checks] == [
        "fail",
        "fail",
        "pass",
        "pass",
    ]
    decode_metrics = [json.loads(str(check["metrics_json"])) for check in decode_checks]
    assert [item["reason"] for item in decode_metrics[:2]] == [
        "ASR_LOCKED_NAME_ANCHOR_MISMATCH",
        "ASR_LOCKED_NAME_ANCHOR_MISMATCH",
    ]
    assert all(
        item["locked_name_anchor_metrics"]["passed"] is True
        for item in decode_metrics[2:]
    )
    final_check = pipeline.db.latest_quality_check(
        scope=QUALITY_SCOPE_SEGMENT,
        stage=SEGMENT_AUDIO_QUALITY_STAGE,
        segment_id=int(row["id"]),
    )
    assert final_check is not None
    final_metrics = json.loads(str(final_check["metrics_json"]))
    assert final_check["verdict"] == "pass"
    assert final_metrics["dual_decode_passed"] is True
    assert final_metrics["locked_name_anchor_metrics"]["passed"] is True

    pipeline._export_reports(incremental=True)
    report = json.loads(
        (pipeline.paths.reports / "audiobook_quality_report.json").read_text(
            encoding="utf-8"
        )
    )
    report_evidence = report["segment_content_evidence"][0]
    assert report_evidence["locked_name_anchor_metrics"]["passed"] is True
    assert len(report_evidence["decode_evidence"]) == 2


def test_clarity_locked_name_mismatch_publishes_for_review(
    tmp_path: Path,
) -> None:
    """A name the transcript never matches publishes with review evidence.

    This is the accepted trade-off, not an oversight: nothing in a transcript
    distinguishes "Whisper wrote a correctly pronounced name in Latin script" from "the
    TTS said the wrong name", and holding every chapter on the first reading meant no
    chapter ever published. What the sentence metrics still guarantee is that the
    ordinary words around the name were read correctly;
    `test_short_utterance_keeps_the_anchor_hard_gate` keeps the case where waiving the
    name would leave nothing to check.
    """
    pipeline, chapter, row, _expected = _asr_signal_pipeline(tmp_path, repair_rounds=1)
    pipeline.tts.spoken_text_with_anchors = lambda _row: (
        "Anh Lu-si-en đã đến.",
        [_locked_lucien_anchor()],
    )
    scripted_results = [
        _asr_result(ASR_PASS, "Anh Lucy đã đến.", similarity=0.96, wer=0.1),
        _asr_result(ASR_PASS, "Anh Lucian đã đến.", similarity=0.96, wer=0.1),
        _asr_result(ASR_PASS, "Anh Lucien đã đến.", similarity=1.0, wer=0.0),
        _asr_result(ASR_PASS, "Anh Lucian đã đến.", similarity=0.96, wer=0.1),
    ]

    class AnchorVerifier:
        def unload(self) -> None:
            return None

        def can_verify_repeated_short(self, _text: str) -> bool:
            return False

        def verify(self, _text: str, _wav: Path, *, confirmation: bool = False):
            return scripted_results.pop(0)

    pipeline._verify_chapter_audio(chapter, AnchorVerifier())

    fresh = pipeline.db.get_segment(int(row["id"]))
    assert fresh["status"] != "failed"
    assert ASR_LOCKED_NAME_ANCHOR_REVIEW in str(fresh["warning_code"])
    # The anchor evidence still records that the name never matched, so the report can
    # put it in front of a person.
    final_check = pipeline.db.latest_quality_check(
        scope=QUALITY_SCOPE_SEGMENT,
        stage=SEGMENT_AUDIO_QUALITY_STAGE,
        segment_id=int(row["id"]),
    )
    assert final_check is not None
    final_metrics = json.loads(str(final_check["metrics_json"]))
    assert final_metrics["locked_name_anchor_metrics"]["passed"] is False


def test_locked_name_review_publishes_when_ordinary_content_stays_clean(
    tmp_path: Path,
) -> None:
    """A name Whisper keeps Latinising must not block the chapter forever.

    Every ordinary word here is transcribed correctly across every repair round; only
    the name comes back in English spelling, which is what real audio does. The segment
    publishes carrying review evidence instead of failing, while
    `test_clarity_locked_name_mismatch_blocks_publication` proves a short utterance -
    where waiving the name would leave nothing to check - still blocks.
    """
    pipeline, chapter, row, _expected = _asr_signal_pipeline(tmp_path, repair_rounds=1)
    pipeline.tts.spoken_text_with_anchors = lambda _row: (
        "Lúc chia tay, Lu-si-en len lén hỏi bạn đầy tò mò.",
        [_locked_lucien_anchor(spoken_start=14)],
    )
    latinised = "Lúc chia tay, Lucian len lén hỏi bạn đầy tò mò."
    scripted_results = [
        _asr_result(ASR_PASS, latinised, similarity=0.96, wer=0.1),
        _asr_result(ASR_PASS, latinised, similarity=0.96, wer=0.1),
        _asr_result(ASR_PASS, latinised, similarity=0.96, wer=0.1),
        _asr_result(ASR_PASS, latinised, similarity=0.96, wer=0.1),
    ]

    class AnchorVerifier:
        def unload(self) -> None:
            return None

        def can_verify_repeated_short(self, _text: str) -> bool:
            return False

        def verify(self, _text: str, _wav: Path, *, confirmation: bool = False):
            return scripted_results.pop(0)

    pipeline._verify_chapter_audio(chapter, AnchorVerifier())

    fresh = pipeline.db.get_segment(int(row["id"]))
    assert fresh["status"] != "failed"
    assert ASR_LOCKED_NAME_ANCHOR_REVIEW in str(fresh["warning_code"])


def test_clarity_final_gate_preserves_anchor_failure_from_either_decode(
    tmp_path: Path,
) -> None:
    pipeline, chapter, row, _expected = _asr_signal_pipeline(tmp_path, repair_rounds=1)
    pipeline.tts.spoken_text_with_anchors = lambda _row: (
        "Anh Lu-si-en đã đến.",
        [_locked_lucien_anchor()],
    )
    scripted_results = [
        _asr_result(ASR_MISMATCH, "sai ban đầu", similarity=0.1, wer=1.0),
        _asr_result(ASR_MISMATCH, "sai xác nhận", similarity=0.1, wer=1.0),
        _asr_result(ASR_PASS, "Anh Lucy đã đến.", similarity=0.96, wer=0.1),
        _asr_result(
            ASR_MISMATCH,
            "Anh Lucien nói sai phần còn lại.",
            similarity=0.5,
            wer=0.8,
        ),
    ]

    class AnchorVerifier:
        def unload(self) -> None:
            return None

        def can_verify_repeated_short(self, _text: str) -> bool:
            return False

        def verify(self, _text: str, _wav: Path, *, confirmation: bool = False):
            return scripted_results.pop(0)

    pipeline._verify_chapter_audio(chapter, AnchorVerifier())

    final_check = pipeline.db.latest_quality_check(
        scope=QUALITY_SCOPE_SEGMENT,
        stage=SEGMENT_AUDIO_QUALITY_STAGE,
        segment_id=int(row["id"]),
    )
    assert final_check is not None
    assert final_check["verdict"] == "fail"
    assert json.loads(str(final_check["failure_codes_json"])) == [
        "ASR_LOCKED_NAME_ANCHOR_MISMATCH",
        "ASR_MISMATCH",
    ]
    final_metrics = json.loads(str(final_check["metrics_json"]))
    assert final_metrics["reason"] == "ASR_LOCKED_NAME_ANCHOR_MISMATCH"
    assert final_metrics["locked_name_anchor_metrics"]["passed"] is False
    assert final_metrics["decode_failure_reasons"] == [
        "ASR_LOCKED_NAME_ANCHOR_MISMATCH"
    ]
    attempts = pipeline.db.segment_candidate_attempt_summary(
        int(row["id"]),
        pipeline.quality_policy_hash,
    )
    assert len(attempts) == 1
    assert attempts[0]["beam_result"]["reason"] == "ASR_LOCKED_NAME_ANCHOR_MISMATCH"
    assert attempts[0]["greedy_result"]["reason"] == "ASR_MISMATCH"
    assert attempts[0]["beam_result"]["locked_name_anchor_metrics"]["passed"] is False
    assert attempts[0]["greedy_result"]["locked_name_anchor_metrics"]["passed"] is True


def test_clarity_endpoint_failure_does_not_hide_beam_anchor_failure(
    tmp_path: Path,
) -> None:
    pipeline, chapter, row, _expected = _asr_signal_pipeline(tmp_path, repair_rounds=1)
    pipeline.tts.spoken_text_with_anchors = lambda _row: (
        "Anh Lu-si-en đã đến.",
        [_locked_lucien_anchor()],
    )
    original_synthesize = pipeline.tts.synthesize_atomic

    def synthesize_with_active_endpoint(*args, **kwargs):
        checksum, metrics, seed = original_synthesize(*args, **kwargs)
        metrics["generation_ceiling_hit"] = 1.0
        metrics["generation_endpoint_active"] = 1.0
        return checksum, metrics, seed

    pipeline.tts.synthesize_atomic = synthesize_with_active_endpoint
    scripted_results = [
        _asr_result(ASR_MISMATCH, "sai ban đầu", similarity=0.1, wer=1.0),
        _asr_result(ASR_MISMATCH, "sai xác nhận", similarity=0.1, wer=1.0),
        _asr_result(ASR_PASS, "Anh Lucy đã đến.", similarity=0.96, wer=0.1),
        _asr_result(ASR_PASS, "Anh Lucien đã đến.", similarity=1.0, wer=0.0),
    ]

    class AnchorVerifier:
        def unload(self) -> None:
            return None

        def can_verify_repeated_short(self, _text: str) -> bool:
            return False

        def verify(self, _text: str, _wav: Path, *, confirmation: bool = False):
            return scripted_results.pop(0)

    pipeline._verify_chapter_audio(chapter, AnchorVerifier())

    final_check = pipeline.db.latest_quality_check(
        scope=QUALITY_SCOPE_SEGMENT,
        stage=SEGMENT_AUDIO_QUALITY_STAGE,
        segment_id=int(row["id"]),
    )
    assert final_check is not None
    assert final_check["verdict"] == "fail"
    assert json.loads(str(final_check["failure_codes_json"])) == [
        "ASR_LOCKED_NAME_ANCHOR_MISMATCH"
    ]
    metrics = json.loads(str(final_check["metrics_json"]))
    assert metrics["reason"] == "ASR_LOCKED_NAME_ANCHOR_MISMATCH"
    assert metrics["locked_name_anchor_metrics"]["passed"] is False
    assert metrics["decode_failure_reasons"] == ["ASR_LOCKED_NAME_ANCHOR_MISMATCH"]
    assert metrics["dual_decode_required"] is False
    assert metrics["dual_decode_passed"] is False
    attempts = pipeline.db.segment_candidate_attempt_summary(
        int(row["id"]),
        pipeline.quality_policy_hash,
    )
    assert len(attempts) == 1
    assert attempts[0]["state"] == "dual_failed"
    assert attempts[0]["signal"]["generation_endpoint_active"] == 1.0
    assert "blocking_signal=generation_endpoint_active" in attempts[0]["failure_reason"]
    assert attempts[0]["beam_result"]["reason"] == "ASR_LOCKED_NAME_ANCHOR_MISMATCH"
    assert attempts[0]["greedy_result"]["verdict"] == ASR_PASS


@pytest.mark.parametrize(
    ("clarity_beam", "clarity_greedy", "expected_status", "expected_gate"),
    [
        (ASR_PASS, ASR_PASS, "verified", "pass"),
        (ASR_PASS, ASR_MISMATCH, "failed", "fail"),
        (ASR_MISMATCH, ASR_PASS, "failed", "fail"),
    ],
)
def test_clarity_repair_requires_two_independent_asr_passes(
    tmp_path: Path,
    clarity_beam: str,
    clarity_greedy: str,
    expected_status: str,
    expected_gate: str,
) -> None:
    pipeline, chapter, row, expected = _asr_signal_pipeline(tmp_path, repair_rounds=1)
    incumbent_path = Path(str(row["wav_path"]))
    incumbent_sha256 = str(row["wav_sha256"])
    incumbent_bytes = incumbent_path.read_bytes()
    scripted_results = [
        _asr_result(ASR_MISMATCH, "sai ban đầu", similarity=0.1, wer=1.0),
        _asr_result(ASR_MISMATCH, "sai xác nhận", similarity=0.1, wer=1.0),
        _asr_result(
            clarity_beam,
            expected if clarity_beam == ASR_PASS else "clarity beam sai",
            similarity=1.0 if clarity_beam == ASR_PASS else 0.1,
            wer=0.0 if clarity_beam == ASR_PASS else 1.0,
        ),
        _asr_result(
            clarity_greedy,
            expected if clarity_greedy == ASR_PASS else "clarity greedy sai",
            similarity=1.0 if clarity_greedy == ASR_PASS else 0.1,
            wer=0.0 if clarity_greedy == ASR_PASS else 1.0,
        ),
    ]

    class ScriptedVerifier:
        def unload(self) -> None:
            return None

        def can_verify_repeated_short(self, _text: str) -> bool:
            return False

        def verify(self, _text: str, _wav: Path, *, confirmation: bool = False):
            return scripted_results.pop(0)

    pipeline._verify_chapter_audio(chapter, ScriptedVerifier())

    fresh = pipeline.db.get_segment(int(row["id"]))
    assert fresh["status"] == expected_status
    assert pipeline.tts.delivery_modes == ["clarity"]
    assert pipeline.tts.seed_salts == ["asr_clarity_candidate_0_0"]
    assert incumbent_path.read_bytes() == incumbent_bytes
    assert sha256_file(incumbent_path) == incumbent_sha256
    final_check = pipeline.db.latest_quality_check(
        scope=QUALITY_SCOPE_SEGMENT,
        stage=SEGMENT_AUDIO_QUALITY_STAGE,
        segment_id=int(row["id"]),
    )
    assert final_check is not None
    assert final_check["verdict"] == expected_gate
    metrics = json.loads(str(final_check["metrics_json"]))
    attempts = pipeline.db.segment_candidate_attempt_summary(
        int(row["id"]),
        pipeline.quality_policy_hash,
    )
    assert len(attempts) == 1
    assert attempts[0]["beam_result"]["verdict"] == clarity_beam
    assert attempts[0]["greedy_result"]["verdict"] == clarity_greedy
    if expected_gate == "pass":
        assert metrics["dual_decode_required"] is True
        assert metrics["dual_decode_passed"] is True
        assert attempts[0]["state"] == "promoted"
        assert Path(str(fresh["wav_path"])) == Path(str(attempts[0]["wav_path"]))
        assert str(fresh["wav_sha256"]) != incumbent_sha256
    else:
        assert metrics["dual_decode_required"] is False
        assert metrics["dual_decode_passed"] is False
        assert attempts[0]["state"] == "dual_failed"
        assert Path(str(fresh["wav_path"])) == Path(str(row["wav_path"]))
        assert str(fresh["wav_sha256"]) == incumbent_sha256


def test_final_direct_candidate_uses_one_immutable_tempo_rescue(
    tmp_path: Path,
) -> None:
    pipeline, chapter, row, _expected = _asr_signal_pipeline(tmp_path, repair_rounds=1)
    spoken_text = "Anh Lu-si-en đã đến."
    pipeline.tts.spoken_text_with_anchors = lambda _row: (
        spoken_text,
        [_locked_lucien_anchor()],
    )
    scripted_results = [
        _asr_result(ASR_MISMATCH, "Anh sai rồi.", similarity=0.2, wer=0.8),
        _asr_result(ASR_MISMATCH, "Anh vẫn sai.", similarity=0.2, wer=0.8),
        _asr_result(ASR_PASS, spoken_text, similarity=1.0, wer=0.0),
        _asr_result(
            ASR_MISMATCH,
            "Anh Lu-si-en sai rồi.",
            similarity=0.7,
            wer=0.5,
        ),
        _asr_result(ASR_PASS, spoken_text, similarity=1.0, wer=0.0),
        _asr_result(ASR_PASS, spoken_text, similarity=1.0, wer=0.0),
    ]

    class TempoRescueVerifier:
        def unload(self) -> None:
            return None

        def can_verify_repeated_short(self, _text: str) -> bool:
            return False

        def verify(self, _text: str, _wav: Path, *, confirmation: bool = False):
            del confirmation
            return scripted_results.pop(0)

    pipeline._verify_chapter_audio(chapter, TempoRescueVerifier())

    attempts = pipeline.db.segment_candidate_attempt_summary(
        int(row["id"]),
        pipeline.quality_policy_hash,
    )
    assert [attempt["state"] for attempt in attempts] == ["dual_failed", "promoted"]
    source, rescued = attempts
    assert source["postprocess_profile"] == "none"
    assert rescued["postprocess_profile"] == "ffmpeg_atempo_0_94_pcm_s16le_v1"
    assert rescued["postprocess_source_candidate_id"] == source["candidate_id"]
    assert rescued["postprocess_source_sha256"] == source["wav_sha256"]
    assert rescued["wav_sha256"] != source["wav_sha256"]
    assert rescued["wav_duration"] > source["wav_duration"]
    assert rescued["signal"]["postprocess_source_samples"] < rescued["signal"][
        "postprocess_output_samples"
    ]
    assert rescued["perceptual_result"]["postprocess_profile"] == (
        "ffmpeg_atempo_0_94_pcm_s16le_v1"
    )
    assert pipeline.tts.synthesize_calls == 1
    assert scripted_results == []

    final = pipeline.db.get_segment(int(row["id"]))
    assert final["status"] == "verified"
    assert final["wav_sha256"] == rescued["wav_sha256"]


def _locked_name_variant_pipeline(
    tmp_path: Path,
    *,
    source_text: str = "Tracy gọi Tracy trong hành lang dài.",
    repair_rounds: int = 2,
):
    source = tmp_path / "001.txt"
    source.write_text(source_text, encoding="utf-8")
    settings = build_settings(
        overrides={
            "asr": {"repair_rounds": repair_rounds},
            # These tests read `perceptual_result` off the candidates they promote, so they
            # have to ask for perceptual QA: high_quality stopped enabling it on 2026-09-07.
            # docs/PERCEPTUAL_QA_COST.md.
            "perceptual_qa": {"enabled": True},
            "tts": {
                "min_seconds_per_100_chars": 0.2,
                "pace_chars_per_second": {"normal": [1.0, 100.0]},
            },
        }
    )
    paths, db, settings = create_or_open_project(
        [source],
        tmp_path / "out",
        settings,
        "Locked-name source delivery",
    )
    pipeline = BookPipeline(
        paths=paths,
        db=db,
        settings=settings,
        pause_requested=lambda: False,
        stop_requested=lambda: False,
        emit=lambda _kind, _payload: None,
    )
    pipeline.tts = LockedNameVariantFakeTTS(settings, db)
    pipeline.perceptual_qa = PassPerceptualVerifier()
    pipeline._recover()
    pipeline._ensure_segments()
    _assign_locked_test_narrator(db)
    chapter = db.list_chapters()[0]
    row = dict(db.list_segments(chapter_id=int(chapter["id"]))[0])
    canonical_text, canonical_anchors = pipeline.tts.spoken_text_with_anchors(row)
    incumbent_path = pipeline._chunk_path(row)
    audio = np.sin(
        np.linspace(0, 50, round(_plausible_duration(canonical_text) * 48_000), dtype=np.float32)
    ) * 0.12
    incumbent_sha256, incumbent_metrics = atomic_write_wav(
        incumbent_path,
        audio,
        48_000,
        canonical_text,
        settings,
        segment=row,
    )
    profile = db.voice_profile(int(db.get_segment(int(row["id"]))["voice_profile_id"]))
    pitch_semitones = int(profile["pitch_semitones"] or 0)
    incumbent_metrics.update(
        {
            "spoken_text_sha256": hashlib.sha256(
                canonical_text.encode("utf-8")
            ).hexdigest(),
            "pronunciation_delivery_variant": PRONUNCIATION_DELIVERY_LOCKED,
            "voice_profile_id": int(profile["id"]),
            "pitch_semitones": pitch_semitones,
            "effective_pitch_semitones": pitch_semitones,
            "pitch_variant_skipped": 0.0,
            "pitch_variant_mixed": 0.0,
        }
    )
    db.mark_signal_passed(
        int(row["id"]),
        wav_path=incumbent_path,
        wav_sha256=incumbent_sha256,
        duration=float(incumbent_metrics["duration"]),
        signal=incumbent_metrics,
        generation_seed=1,
    )
    pipeline._resource_gate = lambda *_args, **_kwargs: None
    pipeline._progress = lambda *_args, **_kwargs: None
    return pipeline, chapter, row, canonical_text, canonical_anchors, source_text


def test_final_locked_name_round_uses_audited_clause_split_and_promotes(
    tmp_path: Path,
) -> None:
    source_text = (
        "Tracy bước qua hành lang rất dài và dừng lại trước cánh cửa bằng đồng, "
        "nơi mọi người vẫn im lặng chờ một câu trả lời rõ ràng. "
        "Sau đó Tracy quay về phía cửa sổ, bình tĩnh nhắc lại kế hoạch để tất cả "
        "cùng nghe và hiểu chính xác điều phải làm tiếp theo."
    )
    pipeline, chapter, row, _canonical, _anchors, _source = (
        _locked_name_variant_pipeline(
            tmp_path,
            source_text=source_text,
            repair_rounds=5,
        )
    )

    class FinalSplitVerifier:
        calls = 0

        def unload(self) -> None:
            return None

        def can_verify_repeated_short(self, _text: str) -> bool:
            return False

        def verify(self, expected: str, _wav: Path, *, confirmation: bool = False):
            del confirmation
            self.calls += 1
            if self.calls <= 2:
                return _asr_result(
                    ASR_MISMATCH,
                    "sai nội dung ban đầu",
                    similarity=0.1,
                    wer=1.0,
                )
            if self.calls <= 10:
                transcript = expected.replace("Tracy", "Lucy").replace(
                    "Trây-si",
                    "Lucy",
                )
                return _asr_result(
                    ASR_PASS,
                    transcript,
                    similarity=0.96,
                    wer=0.1,
                )
            return _asr_result(
                ASR_PASS,
                expected,
                similarity=1.0,
                wer=0.0,
            )

    pipeline._verify_chapter_audio(chapter, FinalSplitVerifier())

    attempts = pipeline.db.segment_candidate_attempt_summary(
        int(row["id"]),
        pipeline.quality_policy_hash,
    )
    final = attempts[-1]
    signal = final["signal"]
    split_prefix = "asr_clarity_candidate_4_source_spelling_v1_split"
    assert [attempt["state"] for attempt in attempts] == [
        "dual_failed",
        "dual_failed",
        "dual_failed",
        "dual_failed",
        "promoted",
    ]
    assert [
        attempt["pronunciation_delivery_variant"] for attempt in attempts
    ] == [
        PRONUNCIATION_DELIVERY_LOCKED,
        PRONUNCIATION_DELIVERY_SOURCE,
        PRONUNCIATION_DELIVERY_LOCKED,
        PRONUNCIATION_DELIVERY_SOURCE,
        PRONUNCIATION_DELIVERY_SOURCE,
    ]
    assert final["tts_attempt"] == int(pipeline.settings["tts"]["max_retries"])
    assert final["generation_strategy"] == GENERATION_STRATEGY_SPLIT
    assert signal["split_checkpoint_seed"] == final["generation_seed"]
    assert signal["split_seed_salt_prefix"] == split_prefix
    expected_parts, expected_max_chars = split_text_for_strategy(
        source_text,
        CLAUSE_SPLIT_STRATEGY,
    )
    assert signal[SPLIT_STRATEGY_FIELD] == CLAUSE_SPLIT_STRATEGY
    assert signal[SPLIT_MAX_CHARS_FIELD] == CLAUSE_SPLIT_MAX_CHARS
    assert expected_max_chars == CLAUSE_SPLIT_MAX_CHARS
    assert len(signal["split_parts"]) == len(expected_parts) == 3
    assert [part["index"] for part in signal["split_parts"]] == [0, 1, 2]
    assert all(
        part["pronunciation_delivery_variant"]
        == PRONUNCIATION_DELIVERY_SOURCE
        for part in signal["split_parts"]
    )
    assert pipeline.tts.seed_salts[-len(expected_parts) :] == [
        f"{split_prefix}_part_{index}"
        for index in range(len(expected_parts))
    ]


def test_final_clause_split_falls_back_when_a_token_cannot_be_bounded() -> None:
    text = "a" * (CLAUSE_SPLIT_MAX_CHARS + 1)

    assert BookPipeline._clause_split_is_unavailable(text) is True


def test_locked_name_repair_alternates_canonical_then_source_and_promotes(
    tmp_path: Path,
) -> None:
    (
        pipeline,
        chapter,
        row,
        canonical_text,
        canonical_anchors,
        source_text,
    ) = _locked_name_variant_pipeline(tmp_path)
    db = pipeline.db

    class VariantVerifier:
        calls = 0

        def unload(self) -> None:
            return None

        def can_verify_repeated_short(self, _text: str) -> bool:
            return False

        def verify(self, expected: str, _wav: Path, *, confirmation: bool = False):
            del confirmation
            self.calls += 1
            if self.calls <= 2:
                return _asr_result(
                    ASR_MISMATCH,
                    "sai nội dung ban đầu",
                    similarity=0.1,
                    wer=1.0,
                )
            if self.calls <= 4:
                return _asr_result(
                    ASR_PASS,
                    "Lucy gọi Lucy trong hành lang dài.",
                    similarity=0.96,
                    wer=0.1,
                )
            return _asr_result(
                ASR_PASS,
                expected,
                similarity=1.0,
                wer=0.0,
            )

    pipeline._verify_chapter_audio(chapter, VariantVerifier())

    fresh = dict(db.get_segment(int(row["id"])))
    attempts = db.segment_candidate_attempt_summary(
        int(row["id"]),
        pipeline.quality_policy_hash,
    )
    source_text_sha256 = hashlib.sha256(source_text.encode("utf-8")).hexdigest()
    assert [attempt["state"] for attempt in attempts] == [
        "dual_failed",
        "promoted",
    ]
    assert [attempt["pronunciation_delivery_variant"] for attempt in attempts] == [
        PRONUNCIATION_DELIVERY_LOCKED,
        PRONUNCIATION_DELIVERY_SOURCE,
    ]
    assert attempts[0]["expected_spoken_text_sha256"] == hashlib.sha256(
        canonical_text.encode("utf-8")
    ).hexdigest()
    assert attempts[1]["expected_spoken_text_sha256"] == source_text_sha256
    assert attempts[0]["beam_result"]["reason"] == (
        "ASR_LOCKED_NAME_ANCHOR_MISMATCH"
    )
    assert attempts[1]["perceptual_result"]["verdict"] == "ok"
    assert pipeline.tts.seed_salts == [
        "asr_clarity_candidate_0_0",
        "asr_clarity_candidate_1_source_spelling_v1_0",
    ]
    promoted_signal = json.loads(str(fresh["signal_json"]))
    assert promoted_signal["pronunciation_delivery_variant"] == (
        PRONUNCIATION_DELIVERY_SOURCE
    )
    assert promoted_signal["spoken_text_sha256"] == source_text_sha256
    reconstructed_text, reconstructed_anchors = pipeline._spoken_text_and_anchors(
        fresh
    )
    assert reconstructed_text == source_text
    assert len(reconstructed_anchors) == len(canonical_anchors) == 2
    assert all(
        anchor["pronunciation_delivery_variant"]
        == PRONUNCIATION_DELIVERY_SOURCE
        for anchor in reconstructed_anchors
    )

    pipeline._export_reports(incremental=True)
    report = json.loads(
        (pipeline.paths.reports / "audiobook_quality_report.json").read_text(
            encoding="utf-8"
        )
    )
    report_attempts = report["segment_repair_candidates"][0]["attempts"]
    content_evidence = report["segment_content_evidence"][0]
    assert report_attempts[1]["pronunciation_delivery_variant"] == (
        PRONUNCIATION_DELIVERY_SOURCE
    )
    assert report_attempts[1]["expected_spoken_text_sha256"] == source_text_sha256
    assert content_evidence["pronunciation_delivery_variant"] == (
        PRONUNCIATION_DELIVERY_SOURCE
    )
    assert content_evidence["spoken_text_sha256"] == source_text_sha256
    assert content_evidence["expected_spoken_text_sha256"] == source_text_sha256
    assert all(
        evidence["pronunciation_delivery_variant"]
        == PRONUNCIATION_DELIVERY_SOURCE
        for evidence in content_evidence["decode_evidence"]
    )


def test_plain_content_failure_keeps_odd_repair_on_canonical_pronunciation(
    tmp_path: Path,
) -> None:
    pipeline, chapter, row, canonical_text, _anchors, _source_text = (
        _locked_name_variant_pipeline(tmp_path)
    )

    class ContentMismatchVerifier:
        calls = 0

        def unload(self) -> None:
            return None

        def can_verify_repeated_short(self, _text: str) -> bool:
            return False

        def verify(self, expected: str, _wav: Path, *, confirmation: bool = False):
            del confirmation
            self.calls += 1
            if self.calls <= 2:
                return _asr_result(
                    ASR_MISMATCH,
                    "sai nội dung ban đầu",
                    similarity=0.1,
                    wer=1.0,
                )
            if self.calls <= 4:
                return _asr_result(
                    ASR_MISMATCH,
                    "Trây-si gọi Trây-si trong sai sai sai.",
                    similarity=0.1,
                    wer=1.0,
                )
            return _asr_result(
                ASR_PASS,
                expected,
                similarity=1.0,
                wer=0.0,
            )

    pipeline._verify_chapter_audio(chapter, ContentMismatchVerifier())

    attempts = pipeline.db.segment_candidate_attempt_summary(
        int(row["id"]),
        pipeline.quality_policy_hash,
    )
    assert [attempt["state"] for attempt in attempts] == [
        "dual_failed",
        "promoted",
    ]
    assert [attempt["pronunciation_delivery_variant"] for attempt in attempts] == [
        PRONUNCIATION_DELIVERY_LOCKED,
        PRONUNCIATION_DELIVERY_LOCKED,
    ]
    assert attempts[0]["beam_result"]["reason"] == "ASR_MISMATCH"
    assert attempts[0]["beam_result"][LOCKED_NAME_ANCHOR_METRICS_KEY][
        "passed"
    ] is True
    assert attempts[1]["expected_spoken_text_sha256"] == hashlib.sha256(
        canonical_text.encode("utf-8")
    ).hexdigest()
    assert pipeline.tts.seed_salts == [
        "asr_clarity_candidate_0_0",
        "asr_clarity_candidate_1_0",
    ]


def test_asr_candidate_with_perceptual_review_never_replaces_incumbent(
    tmp_path: Path,
) -> None:
    pipeline, chapter, row, expected = _asr_signal_pipeline(tmp_path, repair_rounds=1)
    incumbent_path = Path(str(row["wav_path"]))
    incumbent_sha256 = str(row["wav_sha256"])
    incumbent_bytes = incumbent_path.read_bytes()
    scripted_results = [
        _asr_result(ASR_MISMATCH, "primary sai", similarity=0.1, wer=1.0),
        _asr_result(ASR_MISMATCH, "confirmation sai", similarity=0.1, wer=1.0),
        _asr_result(ASR_PASS, expected, similarity=1.0, wer=0.0),
        _asr_result(ASR_PASS, expected, similarity=1.0, wer=0.0),
    ]

    class ScriptedVerifier:
        def unload(self) -> None:
            return None

        def can_verify_repeated_short(self, _text: str) -> bool:
            return False

        def verify(self, _text: str, _wav: Path, *, confirmation: bool = False):
            return scripted_results.pop(0)

    class ReviewPerceptualVerifier:
        verify_calls = 0

        def verify(self, _wav, _preset, *, pitch_semitones=0, prefetched_score=None):
            self.verify_calls += 1
            return {
                "verdict": "review",
                "reason": "PERCEPTUAL_BASELINE_DROP",
                "score": 1.8,
                "baseline_score": 3.0,
                "baseline_delta": -1.2,
                "baseline_pitch_semitones": pitch_semitones,
                "review_required": True,
                "duration_seconds": 2.0,
            }

        def unload(self) -> None:
            return None

    pipeline.perceptual_qa = ReviewPerceptualVerifier()
    pipeline._verify_chapter_audio(chapter, ScriptedVerifier())

    fresh = pipeline.db.get_segment(int(row["id"]))
    attempts = pipeline.db.segment_candidate_attempt_summary(
        int(row["id"]),
        pipeline.quality_policy_hash,
    )
    final_check = pipeline.db.latest_quality_check(
        scope=QUALITY_SCOPE_SEGMENT,
        stage=SEGMENT_AUDIO_QUALITY_STAGE,
        segment_id=int(row["id"]),
    )
    assert final_check is not None
    final_metrics = json.loads(str(final_check["metrics_json"]))
    final_failure_codes = json.loads(str(final_check["failure_codes_json"]))

    assert pipeline.perceptual_qa.verify_calls == 1
    assert [attempt["state"] for attempt in attempts] == ["dual_failed"]
    assert attempts[0]["perceptual_result"]["verdict"] == "review"
    assert fresh["status"] == "failed"
    assert fresh["warning_code"] == PERCEPTUAL_NATURALNESS_REVIEW_CODE
    assert "Perceptual naturalness review remained" in str(fresh["error"])
    assert fresh["wav_path"] == row["wav_path"]
    assert fresh["wav_sha256"] == incumbent_sha256
    assert incumbent_path.read_bytes() == incumbent_bytes
    assert final_check["artifact_sha256"] == incumbent_sha256
    assert final_check["verdict"] == "fail"
    assert final_metrics["reason"] == PERCEPTUAL_NATURALNESS_REVIEW_CODE
    assert final_metrics["repair_trigger_reason"] == "ASR_MISMATCH"
    assert PERCEPTUAL_NATURALNESS_REVIEW_CODE in final_failure_codes
    assert "ASR_MISMATCH_UNRESOLVED" not in json.dumps(
        final_metrics,
        ensure_ascii=False,
    )
    with pytest.raises(RuntimeError, match="durable perceptual blocker"):
        pipeline.db.finalize_segment_candidate_exhaustion(
            segment_id=int(row["id"]),
            policy_hash=pipeline.quality_policy_hash,
            max_repair_rounds=1,
            incumbent_sha256=incumbent_sha256,
            trigger_quality_check_id=int(
                final_metrics["repair_trigger_quality_check_id"]
            ),
            error="ASR mismatch remained",
            warning_code="ASR_MISMATCH_UNRESOLVED",
        )


def test_perceptual_exhaustion_uses_durable_review_in_mixed_history() -> None:
    mismatch = _asr_result(
        ASR_MISMATCH,
        "sai nội dung",
        similarity=0.1,
        wer=1.0,
    )
    passing = _asr_result(ASR_PASS, "Ha ha.", similarity=1.0, wer=0.0)

    assert _candidate_budget_exhausted_on_perceptual_review(
        [
            {
                "state": "dual_failed",
                "beam_result": mismatch,
                "greedy_result": mismatch,
                "perceptual_result": None,
            },
            {
                "state": "dual_failed",
                "beam_result": passing,
                "greedy_result": passing,
                "perceptual_result": {
                    "verdict": "review",
                    "review_required": True,
                },
            },
        ]
    )


def test_resume_of_clarity_candidate_still_requires_both_decodes(
    tmp_path: Path,
) -> None:
    pipeline, chapter, row, expected = _asr_signal_pipeline(tmp_path, repair_rounds=1)

    class CrashAfterBeamVerifier:
        calls = 0

        def unload(self) -> None:
            return None

        def can_verify_repeated_short(self, _text: str) -> bool:
            return False

        def verify(self, _text: str, _wav: Path, *, confirmation: bool = False):
            self.calls += 1
            if self.calls <= 2:
                return _asr_result(ASR_MISMATCH, "primary sai", similarity=0.1, wer=1.0)
            if self.calls == 3:
                return _asr_result(ASR_PASS, expected, similarity=1.0, wer=0.0)
            raise RuntimeError("simulated crash between clarity decodes")

    with pytest.raises(RuntimeError, match="simulated crash"):
        pipeline._verify_chapter_audio(chapter, CrashAfterBeamVerifier())
    assert pipeline.db.get_segment(int(row["id"]))["status"] == "signal_passed"
    attempts = pipeline.db.segment_candidate_attempt_summary(
        int(row["id"]),
        pipeline.quality_policy_hash,
    )
    assert [attempt["state"] for attempt in attempts] == ["beam_recorded"]

    scripted_results = [
        _asr_result(ASR_MISMATCH, "greedy sai", similarity=0.1, wer=1.0),
    ]

    class ResumeVerifier:
        def unload(self) -> None:
            return None

        def can_verify_repeated_short(self, _text: str) -> bool:
            return False

        def verify(self, _text: str, _wav: Path, *, confirmation: bool = False):
            return scripted_results.pop(0)

    pipeline._verify_chapter_audio(chapter, ResumeVerifier())

    fresh = pipeline.db.get_segment(int(row["id"]))
    assert fresh["status"] == "failed"
    assert pipeline.tts.synthesize_calls == 1
    attempts = pipeline.db.segment_candidate_attempt_summary(
        int(row["id"]),
        pipeline.quality_policy_hash,
    )
    assert attempts[0]["state"] == "dual_failed"
    assert attempts[0]["beam_result"]["verdict"] == ASR_PASS
    assert attempts[0]["greedy_result"]["verdict"] == ASR_MISMATCH
    final_check = pipeline.db.latest_quality_check(
        scope=QUALITY_SCOPE_SEGMENT,
        stage=SEGMENT_AUDIO_QUALITY_STAGE,
        segment_id=int(row["id"]),
    )
    assert final_check is not None
    metrics = json.loads(str(final_check["metrics_json"]))
    assert metrics["dual_decode_required"] is False
    assert metrics["dual_decode_passed"] is False
    assert len(metrics["decode_evidence"]) == 2


def test_tampered_candidate_is_invalidated_before_next_round_is_promoted(
    tmp_path: Path,
    monkeypatch,
) -> None:
    pipeline, chapter, row, expected = _asr_signal_pipeline(tmp_path, repair_rounds=2)
    incumbent_path = Path(str(row["wav_path"]))
    incumbent_sha256 = str(row["wav_sha256"])
    incumbent_bytes = incumbent_path.read_bytes()

    class TriggerVerifier:
        calls = 0

        def unload(self) -> None:
            return None

        def can_verify_repeated_short(self, _text: str) -> bool:
            return False

        def verify(self, _text: str, _wav: Path, *, confirmation: bool = False):
            self.calls += 1
            if self.calls <= 2:
                return _asr_result(ASR_MISMATCH, "primary sai", similarity=0.1, wer=1.0)
            return _asr_result(ASR_PASS, expected, similarity=1.0, wer=0.0)

    original_record = pipeline._record_segment_asr_decode_evidence

    def crash_before_candidate_decode_checkpoint(item, *args, **kwargs):
        if item.get("segment_candidate_id") is not None:
            raise RuntimeError("simulated crash before candidate decode checkpoint")
        return original_record(item, *args, **kwargs)

    monkeypatch.setattr(
        pipeline,
        "_record_segment_asr_decode_evidence",
        crash_before_candidate_decode_checkpoint,
    )
    with pytest.raises(RuntimeError, match="before candidate decode checkpoint"):
        pipeline._verify_chapter_audio(chapter, TriggerVerifier())

    attempts = pipeline.db.segment_candidate_attempt_summary(
        int(row["id"]),
        pipeline.quality_policy_hash,
    )
    assert [attempt["state"] for attempt in attempts] == ["signal_passed"]
    first_candidate_path = Path(str(attempts[0]["wav_path"]))
    first_candidate_path.write_bytes(first_candidate_path.read_bytes() + b"tampered")

    monkeypatch.setattr(
        pipeline,
        "_record_segment_asr_decode_evidence",
        original_record,
    )

    class PassingVerifier:
        calls = 0

        def unload(self) -> None:
            return None

        def can_verify_repeated_short(self, _text: str) -> bool:
            return False

        def verify(self, _text: str, _wav: Path, *, confirmation: bool = False):
            self.calls += 1
            return _asr_result(ASR_PASS, expected, similarity=1.0, wer=0.0)

    verifier = PassingVerifier()
    pipeline._verify_chapter_audio(chapter, verifier)

    fresh = pipeline.db.get_segment(int(row["id"]))
    attempts = pipeline.db.segment_candidate_attempt_summary(
        int(row["id"]),
        pipeline.quality_policy_hash,
    )
    assert [attempt["state"] for attempt in attempts] == ["invalid", "promoted"]
    assert verifier.calls == 2
    assert pipeline.tts.seed_salts == [
        "asr_clarity_candidate_0_0",
        "asr_clarity_candidate_1_0",
    ]
    assert Path(str(fresh["wav_path"])) == Path(str(attempts[1]["wav_path"]))
    assert incumbent_path.read_bytes() == incumbent_bytes
    assert sha256_file(incumbent_path) == incumbent_sha256


def test_dual_passed_candidate_resumes_at_atomic_promotion_without_redecode(
    tmp_path: Path,
    monkeypatch,
) -> None:
    pipeline, chapter, row, expected = _asr_signal_pipeline(tmp_path, repair_rounds=1)
    incumbent_path = Path(str(row["wav_path"]))
    incumbent_sha256 = str(row["wav_sha256"])
    incumbent_bytes = incumbent_path.read_bytes()
    scripted_results = [
        _asr_result(ASR_MISMATCH, "primary sai", similarity=0.1, wer=1.0),
        _asr_result(ASR_MISMATCH, "confirmation sai", similarity=0.1, wer=1.0),
        _asr_result(ASR_PASS, expected, similarity=1.0, wer=0.0),
        _asr_result(ASR_PASS, expected, similarity=1.0, wer=0.0),
    ]

    class ScriptedVerifier:
        def unload(self) -> None:
            return None

        def can_verify_repeated_short(self, _text: str) -> bool:
            return False

        def verify(self, _text: str, _wav: Path, *, confirmation: bool = False):
            return scripted_results.pop(0)

    original_promote = pipeline.db.promote_segment_candidate
    monkeypatch.setattr(
        pipeline.db,
        "promote_segment_candidate",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            RuntimeError("simulated crash before atomic promotion")
        ),
    )
    with pytest.raises(RuntimeError, match="before atomic promotion"):
        pipeline._verify_chapter_audio(chapter, ScriptedVerifier())

    crashed = pipeline.db.get_segment(int(row["id"]))
    attempts = pipeline.db.segment_candidate_attempt_summary(
        int(row["id"]),
        pipeline.quality_policy_hash,
    )
    assert [attempt["state"] for attempt in attempts] == ["dual_passed"]
    assert attempts[0]["perceptual_result"]["verdict"] == "ok"
    assert attempts[0]["perceptual_check_id"] is not None
    perceptual_calls_before_resume = pipeline.perceptual_qa.verify_calls
    assert perceptual_calls_before_resume == 1
    assert crashed["wav_path"] == row["wav_path"]
    assert crashed["wav_sha256"] == row["wav_sha256"]
    assert incumbent_path.read_bytes() == incumbent_bytes

    monkeypatch.setattr(pipeline.db, "promote_segment_candidate", original_promote)

    class NoDecodeVerifier:
        def unload(self) -> None:
            return None

        def can_verify_repeated_short(self, _text: str) -> bool:
            raise AssertionError("promotion resume must not inspect ASR capability")

        def verify(self, *_args, **_kwargs):
            raise AssertionError("promotion resume must not rerun Whisper")

    calls_before_resume = pipeline.tts.synthesize_calls
    pipeline._verify_chapter_audio(chapter, NoDecodeVerifier())

    fresh = pipeline.db.get_segment(int(row["id"]))
    attempts = pipeline.db.segment_candidate_attempt_summary(
        int(row["id"]),
        pipeline.quality_policy_hash,
    )
    assert attempts[0]["state"] == "promoted"
    assert Path(str(fresh["wav_path"])) == Path(str(attempts[0]["wav_path"]))
    assert str(fresh["wav_sha256"]) != incumbent_sha256
    assert pipeline.tts.synthesize_calls == calls_before_resume
    assert pipeline.perceptual_qa.verify_calls == perceptual_calls_before_resume
    assert incumbent_path.read_bytes() == incumbent_bytes


def test_recheckpoint_preserves_clarity_provenance_after_partial_asr_commit(
    tmp_path: Path,
) -> None:
    pipeline, _chapter, row, expected = _asr_signal_pipeline(tmp_path, repair_rounds=2)
    original_signal = json.loads(str(row["signal_json"]))
    original_signal.update(
        {
            "tts_delivery_mode": "clarity",
            "asr_clarity_repair_round": 0,
            "spoken_text_sha256": "e" * 64,
            "voice_profile_id": 17,
            "pitch_semitones": -1,
            "effective_pitch_semitones": None,
            "pitch_variant_skipped": 1.0,
            "pitch_variant_mixed": 1.0,
            "generation_ceiling_hit": 1.0,
            "generation_endpoint_active": 1.0,
            "split_checkpoint_seed": 122,
            "split_seed_salt_prefix": "asr_clarity_repair_0_split",
            "split_parts": [
                {
                    "generation_seed": 121,
                    "effective_pitch_semitones": -1,
                    "pitch_variant_skipped": 0.0,
                },
                {
                    "generation_seed": 123,
                    "effective_pitch_semitones": 0,
                    "pitch_variant_skipped": 1.0,
                },
            ],
        }
    )
    pipeline.db.mark_signal_passed(
        int(row["id"]),
        wav_path=Path(str(row["wav_path"])),
        wav_sha256=str(row["wav_sha256"]),
        duration=float(row["wav_duration"]),
        signal=original_signal,
        generation_seed=123,
    )
    pipeline.db.mark_asr_result(
        int(row["id"]),
        passed=True,
        transcript=expected,
        similarity=1.0,
        wer=0.0,
    )
    partial = pipeline.db.get_segment(int(row["id"]))

    pipeline._recheckpoint_segment_for_current_audio_qa(
        partial,
        {"duration": float(row["wav_duration"]), "rms": 0.1},
    )

    fresh = pipeline.db.get_segment(int(row["id"]))
    signal = json.loads(str(fresh["signal_json"]))
    assert fresh["status"] == "signal_passed"
    assert signal["tts_delivery_mode"] == "clarity"
    assert signal["asr_clarity_repair_round"] == 0
    assert signal["spoken_text_sha256"] == "e" * 64
    assert signal["voice_profile_id"] == 17
    assert signal["pitch_semitones"] == -1
    assert signal["effective_pitch_semitones"] is None
    assert signal["pitch_variant_skipped"] == 1.0
    assert signal["pitch_variant_mixed"] == 1.0
    assert signal["generation_ceiling_hit"] == 1.0
    assert signal["generation_endpoint_active"] == 1.0
    assert signal["split_checkpoint_seed"] == 122
    assert signal["split_seed_salt_prefix"] == "asr_clarity_repair_0_split"
    assert [part["generation_seed"] for part in signal["split_parts"]] == [121, 123]
    assert set(str(fresh["warning_code"]).split("|")) == {
        "TTS_SPLIT_RECOVERY",
        "TTS_PITCH_VARIANT_SKIPPED",
        "TTS_GENERATION_CEILING_REACHED",
    }
    evidence = pipeline._record_segment_asr_decode_evidence(
        dict(fresh),
        _asr_result(ASR_PASS, expected, similarity=1.0, wer=0.0),
        confirmation=False,
        context_mode="direct",
        selected=True,
        repair_round=0,
        delivery_mode="clarity",
    )
    assert evidence["generation_kind"] == "split"
    assert evidence["split_checkpoint_seed"] == 122
    assert [part["generation_seed"] for part in evidence["split_parts"]] == [121, 123]


def test_crash_before_clarity_wav_commit_resumes_the_same_round(
    tmp_path: Path,
) -> None:
    pipeline, chapter, row, _expected = _asr_signal_pipeline(tmp_path, repair_rounds=1)
    profile_id = pipeline.db.upsert_voice_profile(
        {
            "voice_key": "resume_voice",
            "engine": "vieneu",
            "preset_name": "Xuân Vĩnh",
            "description": "Resume voice",
            "seed": 1,
            "pitch_semitones": 0,
            "status": "ready",
        }
    )
    with pipeline.db.connect() as conn:
        conn.execute(
            "UPDATE segments SET voice_profile_id=? WHERE id=?",
            (profile_id, int(row["id"])),
        )
    pipeline.db.mark_generating(
        int(row["id"]),
        seed=123,
        delivery_mode="clarity",
        repair_round=0,
        policy_hash=pipeline.quality_policy_hash,
    )
    assert pipeline.db.reset_in_progress_segments("simulated worker crash") == 1
    recovered = pipeline.db.get_segment(int(row["id"]))
    assert recovered["status"] == "analyzed"
    assert recovered["generation_repair_round"] == 0
    pipeline._verify_chapter_audio = lambda *_args, **_kwargs: (_ for _ in ()).throw(
        RuntimeError("stop after synthesis")
    )

    with pytest.raises(RuntimeError, match="stop after synthesis"):
        pipeline._process_chapter(chapter, SimpleNamespace(unload=lambda: None))

    fresh = pipeline.db.get_segment(int(row["id"]))
    assert pipeline.tts.delivery_modes == ["clarity"]
    assert pipeline.tts.seed_salts == ["asr_clarity_repair_0_0"]
    assert fresh["status"] == "signal_passed"
    assert fresh["generation_delivery_mode"] == "clarity"
    assert fresh["generation_repair_round"] == 0
    signal = json.loads(str(fresh["signal_json"]))
    assert signal["asr_clarity_repair_round"] == 0


def test_same_policy_final_asr_failure_is_not_regenerated_on_resume(
    tmp_path: Path,
) -> None:
    pipeline, chapter, row, _expected = _asr_signal_pipeline(tmp_path, repair_rounds=1)
    pipeline.db.mark_generating(
        int(row["id"]),
        seed=123,
        delivery_mode="clarity",
        repair_round=0,
        policy_hash=pipeline.quality_policy_hash,
    )
    pipeline.db.record_quality_check(
        scope=QUALITY_SCOPE_SEGMENT,
        stage=SEGMENT_AUDIO_QUALITY_STAGE,
        segment_id=int(row["id"]),
        artifact_sha256=str(row["wav_sha256"]),
        policy_hash=pipeline.quality_policy_hash,
        policy_version=QUALITY_POLICY_VERSION,
        verdict="fail",
        metrics={"reason": "ASR_MISMATCH_UNRESOLVED"},
    )
    pipeline.db.mark_failed(
        int(row["id"]),
        "ASR mismatch remained after all configured repair rounds",
        warning_code="ASR_MISMATCH_UNRESOLVED",
    )
    pipeline._verify_chapter_audio = lambda *_args, **_kwargs: (_ for _ in ()).throw(
        RuntimeError("stop after synthesis stage")
    )

    with pytest.raises(RuntimeError, match="stop after synthesis stage"):
        pipeline._process_chapter(chapter, SimpleNamespace(unload=lambda: None))

    assert pipeline.tts.synthesize_calls == 0
    fresh = pipeline.db.get_segment(int(row["id"]))
    assert fresh["status"] == "failed"
    assert fresh["generation_repair_round"] == 0


def test_previous_policy_asr_failure_does_not_freeze_current_policy_resume(
    tmp_path: Path,
) -> None:
    pipeline, _chapter, row, _expected = _asr_signal_pipeline(tmp_path, repair_rounds=1)
    pipeline.db.record_quality_check(
        scope=QUALITY_SCOPE_SEGMENT,
        stage=SEGMENT_AUDIO_QUALITY_STAGE,
        segment_id=int(row["id"]),
        artifact_sha256=str(row["wav_sha256"]),
        policy_hash=pipeline.quality_policy_hash,
        policy_version=QUALITY_POLICY_VERSION,
        verdict="fail",
        metrics={"reason": "ASR_MISMATCH_UNRESOLVED"},
    )
    assert pipeline._segment_has_current_asr_failure(row) is True

    replacement_policy = json.loads(json.dumps(pipeline.quality_policy))
    replacement_policy["algorithms"]["asr_content"] = "future-anchor-policy"
    replacement_hash = quality_policy_hash(replacement_policy)
    pipeline.db.set_current_quality_policy(
        policy_hash=replacement_hash,
        policy_version=QUALITY_POLICY_VERSION,
        policy=replacement_policy,
    )
    pipeline.quality_policy = replacement_policy
    pipeline.quality_policy_hash = replacement_hash

    assert pipeline._segment_has_current_asr_failure(row) is False


def test_crash_after_final_asr_failure_gate_is_fail_closed_on_resume(
    tmp_path: Path,
) -> None:
    pipeline, chapter, row, _expected = _asr_signal_pipeline(tmp_path, repair_rounds=1)
    pipeline.db.mark_asr_result(
        int(row["id"]),
        passed=False,
        transcript="sai nội dung",
        similarity=0.1,
        wer=1.0,
        warning_code="ASR_MISMATCH_UNRESOLVED",
    )
    pipeline.db.record_quality_check(
        scope=QUALITY_SCOPE_SEGMENT,
        stage=SEGMENT_AUDIO_QUALITY_STAGE,
        segment_id=int(row["id"]),
        artifact_sha256=str(row["wav_sha256"]),
        policy_hash=pipeline.quality_policy_hash,
        policy_version=QUALITY_POLICY_VERSION,
        verdict="fail",
        metrics={"reason": "ASR_MISMATCH_UNRESOLVED"},
    )
    pipeline._verify_chapter_audio = lambda *_args, **_kwargs: (_ for _ in ()).throw(
        RuntimeError("stop after synthesis stage")
    )

    with pytest.raises(RuntimeError, match="stop after synthesis stage"):
        pipeline._process_chapter(chapter, SimpleNamespace(unload=lambda: None))

    fresh = pipeline.db.get_segment(int(row["id"]))
    assert pipeline.tts.synthesize_calls == 0
    assert fresh["status"] == "failed"
    assert "ASR_MISMATCH_UNRESOLVED" in str(fresh["warning_code"])
    assert "ASR_CONTENT_GATE_FAILED" in str(fresh["warning_code"])


def test_tts_circuit_breaker_counts_only_consecutive_identical_complete_failures() -> None:
    pipeline = object.__new__(BookPipeline)
    pipeline._last_tts_failure_signature = None
    pipeline._tts_failure_streak = 0

    assert pipeline._record_tts_failure("same error") == 1
    assert pipeline._record_tts_failure("same   error") == 2
    pipeline._reset_tts_failure_streak()
    assert pipeline._record_tts_failure("same error") == 1
    assert pipeline._record_tts_failure("different error") == 1


def test_high_quality_blocks_unreviewed_segment_warnings() -> None:
    pipeline = object.__new__(BookPipeline)
    pipeline.settings = {"quality_profile": "high_quality"}

    class _NothingAccepted:
        """The check now asks what a listener has accepted; nobody has accepted anything
        here, which is the case this test has always been about."""

        @staticmethod
        def accepted_segment_warnings() -> dict:
            return {}

    pipeline.db = _NothingAccepted()
    rows = [
        {
            "id": 1,
            "stable_id": "c1s1",
            "wav_sha256": "aaa",
            "warning_code": "TTS_SPLIT_RECOVERY|TTS_GENERATION_CEILING_REACHED",
        },
        {
            "id": 2,
            "stable_id": "c1s2",
            "wav_sha256": "bbb",
            "warning_code": "LOW_ANALYSIS_CONFIDENCE|TTS_PACE_OUTLIER",
        },
    ]

    assert pipeline._high_quality_blocking_segment_warnings(rows) == [
        {
            "segment_id": 2,
            "stable_id": "c1s2",
            "warning_codes": ["LOW_ANALYSIS_CONFIDENCE", "TTS_PACE_OUTLIER"],
        }
    ]

    pipeline.settings = {"quality_profile": "balanced"}
    assert pipeline._high_quality_blocking_segment_warnings(rows) == []


def test_high_quality_ceiling_waveform_is_checkpointed_for_whisper(tmp_path: Path) -> None:
    pipeline, chapter, row = _short_tts_pipeline(tmp_path)
    scripted = ScriptedShortTTS(
        [
            {
                "duration": 1.92,
                "generation_ceiling_hit": 1.0,
                "generation_endpoint_active": 1.0,
                "trailing_rms": 0.05,
            }
        ]
    )
    pipeline.tts = scripted.bind(pipeline.settings, pipeline.db)

    pipeline._process_single_segment(row, chapter)

    updated = pipeline.db.get_segment(int(row["id"]))
    assert len(scripted.calls) == 1
    assert updated["status"] == "signal_passed"
    assert updated["warning_code"] == "TTS_GENERATION_CEILING_REACHED"
    assert json.loads(str(updated["signal_json"]))["generation_endpoint_active"] == 1.0


def test_legacy_ceiling_without_endpoint_evidence_fails_closed() -> None:
    assert BookPipeline._ceiling_endpoint_requires_repair(
        {"signal_json": json.dumps({"generation_ceiling_hit": 1.0})}
    )


@pytest.mark.parametrize("signal_json", [None, "", "{broken", "null", "[]"])
def test_ceiling_warning_with_invalid_signal_evidence_fails_closed(signal_json) -> None:
    assert BookPipeline._ceiling_endpoint_requires_repair(
        {
            "signal_json": signal_json,
            "warning_code": "LOW_ANALYSIS_CONFIDENCE|TTS_GENERATION_CEILING_REACHED",
        }
    )


@pytest.mark.parametrize("signal_json", [None, "", "{broken", "null", "[]"])
def test_invalid_signal_evidence_without_ceiling_warning_does_not_force_repair(
    signal_json,
) -> None:
    assert not BookPipeline._ceiling_endpoint_requires_repair(
        {"signal_json": signal_json, "warning_code": "LOW_ANALYSIS_CONFIDENCE"}
    )


def test_quiet_endpoint_evidence_overrides_the_durable_ceiling_warning() -> None:
    assert not BookPipeline._ceiling_endpoint_requires_repair(
        {
            "signal_json": json.dumps(
                {
                    "generation_ceiling_hit": 1.0,
                    "generation_endpoint_active": 0.0,
                }
            ),
            "warning_code": "TTS_GENERATION_CEILING_REACHED",
        }
    )


def test_standalone_ha_ceiling_repair_persists_calibrated_frame_cap(
    tmp_path: Path,
) -> None:
    pipeline, _chapter, row = _short_tts_pipeline(
        tmp_path,
        source_text="“Ha…”",
    )
    pipeline.tts = ScriptedShortTTS([]).bind(pipeline.settings, pipeline.db)
    with pipeline.db.connect() as conn:
        conn.execute(
            "UPDATE segments SET warning_code=? WHERE id=?",
            ("TTS_GENERATION_CEILING_REACHED", int(row["id"])),
        )
    row = pipeline.db.get_segment(int(row["id"]))

    repaired = pipeline._checkpoint_short_ceiling_repair(row)

    assert repaired["generation_frame_cap"] == HA_VOCALIZATION_MAX_NEW_FRAMES


@pytest.mark.parametrize("initial_verdict", [ASR_PASS, ASR_MISMATCH, ASR_INCONCLUSIVE])
def test_active_ceiling_endpoint_repairs_after_any_whisper_verdict_and_clears_cap(
    tmp_path: Path,
    initial_verdict: str,
) -> None:
    pipeline, chapter, row = _short_tts_pipeline(tmp_path)
    _checkpoint_short_ceiling_incumbent(pipeline, row)
    scripted = ScriptedShortTTS([{"duration": 0.88, "trailing_rms": 0.0}])
    verifier = PassingShortVerifier(initial_verdict)
    pipeline.tts = scripted.bind(pipeline.settings, pipeline.db)

    pipeline._verify_chapter_audio(chapter, verifier)

    updated = pipeline.db.get_segment(int(row["id"]))
    assert verifier.calls == 3
    assert [call["generation_frame_cap"] for call in scripted.calls] == [12]
    assert scripted.calls[0]["repair_short_utterance"] is True
    assert scripted.calls[0]["delivery_mode"] == "clarity"
    assert updated["status"] == "verified"
    assert updated["generation_frame_cap"] is None


def test_active_ceiling_endpoint_repairs_are_finite_and_remain_blocking(
    tmp_path: Path,
) -> None:
    pipeline, chapter, row = _short_tts_pipeline(tmp_path, repair_rounds=2)
    endpoint_metrics = {
        "duration": 0.96,
        "generation_ceiling_hit": 1.0,
        "generation_endpoint_active": 1.0,
        "trailing_rms": 0.05,
    }
    _checkpoint_short_ceiling_incumbent(pipeline, row)
    scripted = ScriptedShortTTS([endpoint_metrics, endpoint_metrics])
    verifier = PassingShortVerifier()
    pipeline.tts = scripted.bind(pipeline.settings, pipeline.db)

    pipeline._verify_chapter_audio(chapter, verifier)

    updated = pipeline.db.get_segment(int(row["id"]))
    assert len(scripted.calls) == 2
    assert verifier.calls == 5
    assert [call["generation_frame_cap"] for call in scripted.calls] == [12, 12]
    assert [call["delivery_mode"] for call in scripted.calls] == ["clarity", "clarity"]
    assert updated["status"] == "failed"
    assert updated["generation_frame_cap"] == 12
    assert updated["error"] == "ASR mismatch remained after all immutable repair candidates"
    attempts = pipeline.db.segment_candidate_attempt_summary(
        int(row["id"]),
        pipeline.quality_policy_hash,
    )
    assert [attempt["state"] for attempt in attempts] == ["dual_failed", "dual_failed"]
    assert all(
        attempt["signal"]["generation_endpoint_active"] == 1.0
        for attempt in attempts
    )


def test_short_tts_failure_does_not_attempt_semantic_split(
    tmp_path: Path,
    monkeypatch,
) -> None:
    pipeline, chapter, row = _short_tts_pipeline(tmp_path)
    scripted = ScriptedShortTTS(
        [AudioQualityError("generation failed") for _attempt in range(4)]
    )
    pipeline.tts = scripted.bind(pipeline.settings, pipeline.db)
    monkeypatch.setattr(pipeline_module.time, "sleep", lambda _seconds: None)
    pipeline._synthesize_split = lambda *_args, **_kwargs: pytest.fail(
        "short utterance must not be split"
    )

    pipeline._process_single_segment(row, chapter)

    updated = pipeline.db.get_segment(int(row["id"]))
    assert len(scripted.calls) == 4
    assert updated["status"] == "failed"
    assert "short utterance is not splittable" in str(updated["error"])


def test_non_short_tts_failure_keeps_existing_split_recovery(
    tmp_path: Path,
    monkeypatch,
) -> None:
    pipeline, chapter, row = _short_tts_pipeline(tmp_path)
    long_text = " ".join(["Nội dung đủ dài để chia an toàn"] * 8)
    with pipeline.db.connect() as conn:
        conn.execute("UPDATE segments SET text=? WHERE id=?", (long_text, int(row["id"])))
    row = pipeline.db.get_segment(int(row["id"]))
    scripted = ScriptedShortTTS(
        [AudioQualityError("generation failed") for _attempt in range(4)]
    )
    split_calls: list[tuple[str, str]] = []

    def fake_split(item, _output, **kwargs):
        split_calls.append(
            (str(item["stable_id"]), str(kwargs["split_strategy"]))
        )

    pipeline.tts = scripted.bind(pipeline.settings, pipeline.db)
    pipeline._synthesize_split = fake_split
    monkeypatch.setattr(pipeline_module.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(
        pipeline_module,
        "inspect_wav",
        lambda *_args, **_kwargs: (True, {"duration": 2.0}, "ok"),
    )
    monkeypatch.setattr(pipeline_module, "sha256_file", lambda _path: "d" * 64)

    pipeline._process_single_segment(row, chapter)

    updated = pipeline.db.get_segment(int(row["id"]))
    assert split_calls == [
        (str(row["stable_id"]), SENTENCE_SPLIT_STRATEGY)
    ]
    assert updated["status"] == "signal_passed"
    assert updated["warning_code"] == "TTS_SPLIT_RECOVERY"
    signal = json.loads(str(updated["signal_json"]))
    assert signal[SPLIT_STRATEGY_FIELD] == SENTENCE_SPLIT_STRATEGY
    assert signal[SPLIT_MAX_CHARS_FIELD] == SENTENCE_SPLIT_MAX_CHARS


def test_clarity_split_fallback_uses_distinct_round_seed_salts(
    tmp_path: Path,
    monkeypatch,
) -> None:
    pipeline, chapter, row = _short_tts_pipeline(tmp_path)
    long_text = " ".join(["Nội dung đủ dài để chia an toàn"] * 8)
    with pipeline.db.connect() as conn:
        conn.execute("UPDATE segments SET text=? WHERE id=?", (long_text, int(row["id"])))
    row = pipeline.db.get_segment(int(row["id"]))
    scripted = ScriptedShortTTS(
        [AudioQualityError("generation failed") for _attempt in range(8)]
    )
    split_prefixes: list[str] = []

    def fake_split(_item, _output, **kwargs):
        split_prefixes.append(str(kwargs["seed_salt_prefix"]))
        return []

    pipeline.tts = scripted.bind(pipeline.settings, pipeline.db)
    pipeline._synthesize_split = fake_split
    monkeypatch.setattr(pipeline_module.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(
        pipeline_module,
        "inspect_wav",
        lambda *_args, **_kwargs: (True, {"duration": 2.0}, "ok"),
    )
    monkeypatch.setattr(pipeline_module, "sha256_file", lambda _path: "d" * 64)

    pipeline._process_single_segment(
        row,
        chapter,
        seed_salt_prefix="asr_clarity_repair_0",
        delivery_mode="clarity",
        asr_repair_round=0,
    )
    fresh = pipeline.db.get_segment(int(row["id"]))
    pipeline._process_single_segment(
        fresh,
        chapter,
        seed_salt_prefix="asr_clarity_repair_1",
        delivery_mode="clarity",
        asr_repair_round=1,
    )

    assert split_prefixes == [
        "asr_clarity_repair_0_split",
        "asr_clarity_repair_1_split",
    ]
    assert "asr_clarity_repair_0_split" in scripted.generation_seed_salts
    assert "asr_clarity_repair_1_split" in scripted.generation_seed_salts


def test_source_split_rejects_part_provenance_from_canonical_delivery(
    tmp_path: Path,
) -> None:
    class SplitVariantDriftTTS:
        def generation_seed(self, _row, _seed_salt=""):
            return 1

        def spoken_text_with_anchors(
            self,
            row,
            *,
            pronunciation_delivery_variant=PRONUNCIATION_DELIVERY_LOCKED,
        ):
            del pronunciation_delivery_variant
            return str(row["text"]), []

        def synthesize_atomic(
            self,
            row,
            _output,
            *,
            pronunciation_delivery_variant=PRONUNCIATION_DELIVERY_LOCKED,
            **_kwargs,
        ):
            return (
                "a" * 64,
                {
                    "pronunciation_delivery_variant": (
                        PRONUNCIATION_DELIVERY_LOCKED
                    ),
                    "spoken_text_sha256": hashlib.sha256(
                        str(row["text"]).encode("utf-8")
                    ).hexdigest(),
                },
                1,
            )

    pipeline = BookPipeline.__new__(BookPipeline)
    pipeline.tts = SplitVariantDriftTTS()
    row = {
        "stable_id": "source-split",
        "text": " ".join(["Tracy đi qua hành lang rất dài"] * 10),
    }

    with pytest.raises(RuntimeError, match="split part TTS provenance differs"):
        pipeline._synthesize_split(
            row,
            tmp_path / "source-split.wav",
            pronunciation_delivery_variant=PRONUNCIATION_DELIVERY_SOURCE,
        )


def test_split_rejects_part_seed_that_drifts_from_its_deterministic_salt(
    tmp_path: Path,
) -> None:
    class SplitSeedDriftTTS:
        def generation_seed(self, _row, _seed_salt=""):
            return 7

        def spoken_text_with_anchors(
            self,
            row,
            *args,
            pronunciation_delivery_variant=PRONUNCIATION_DELIVERY_LOCKED,
        ):
            del args, pronunciation_delivery_variant
            return str(row["text"]), []

        def synthesize_atomic(self, row, _output, **_kwargs):
            return (
                "a" * 64,
                {
                    "pronunciation_delivery_variant": (
                        PRONUNCIATION_DELIVERY_LOCKED
                    ),
                    "spoken_text_sha256": hashlib.sha256(
                        str(row["text"]).encode("utf-8")
                    ).hexdigest(),
                },
                8,
            )

    pipeline = BookPipeline.__new__(BookPipeline)
    pipeline.tts = SplitSeedDriftTTS()
    row = {
        "stable_id": "seed-drift-split",
        "text": " ".join(["Nội dung đủ dài để chia an toàn"] * 10),
    }

    with pytest.raises(RuntimeError, match="deterministic salt"):
        pipeline._synthesize_split(
            row,
            tmp_path / "seed-drift-split.wav",
        )


def test_split_fallback_aggregates_later_part_pitch_and_ceiling_failures(
    tmp_path: Path,
    monkeypatch,
) -> None:
    pipeline, chapter, row = _short_tts_pipeline(tmp_path)
    long_text = " ".join(["Nội dung đủ dài để chia an toàn"] * 8)
    with pipeline.db.connect() as conn:
        conn.execute("UPDATE segments SET text=? WHERE id=?", (long_text, int(row["id"])))
    row = pipeline.db.get_segment(int(row["id"]))
    scripted = ScriptedShortTTS(
        [AudioQualityError("generation failed") for _attempt in range(4)]
    )

    def fake_split(_item, _output, **_kwargs):
        return [
            {
                "voice_profile_id": 7,
                "pitch_semitones": -1,
                "effective_pitch_semitones": -1,
                "pitch_variant_skipped": 0.0,
                "generation_ceiling_hit": 0.0,
                "generation_endpoint_active": 0.0,
            },
            {
                "voice_profile_id": 7,
                "pitch_semitones": -1,
                "effective_pitch_semitones": 0,
                "pitch_variant_skipped": 1.0,
                "generation_ceiling_hit": 1.0,
                "generation_endpoint_active": 1.0,
            },
        ]

    pipeline.tts = scripted.bind(pipeline.settings, pipeline.db)
    pipeline._synthesize_split = fake_split
    monkeypatch.setattr(pipeline_module.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(
        pipeline_module,
        "inspect_wav",
        lambda *_args, **_kwargs: (True, {"duration": 2.0}, "ok"),
    )
    monkeypatch.setattr(pipeline_module, "sha256_file", lambda _path: "d" * 64)

    pipeline._process_single_segment(row, chapter)

    fresh = pipeline.db.get_segment(int(row["id"]))
    warning_codes = set(str(fresh["warning_code"]).split("|"))
    signal = json.loads(str(fresh["signal_json"]))
    assert warning_codes == {
        "TTS_SPLIT_RECOVERY",
        "TTS_PITCH_VARIANT_SKIPPED",
        "TTS_GENERATION_CEILING_REACHED",
    }
    assert signal["pitch_variant_mixed"] == 1.0
    assert signal["pitch_variant_skipped"] == 1.0
    assert signal["effective_pitch_semitones"] is None
    assert signal["generation_ceiling_hit"] == 1.0
    assert signal["generation_endpoint_active"] == 1.0


def test_failed_clarity_tts_records_final_content_failure_for_retained_wav(
    tmp_path: Path,
    monkeypatch,
) -> None:
    pipeline, chapter, row, _expected = _asr_signal_pipeline(tmp_path, repair_rounds=1)
    scripted = ScriptedShortTTS(
        [
            AudioQualityError("clarity inference failed")
            for _attempt in range(int(pipeline.settings["tts"]["max_retries"]))
        ]
    )
    pipeline.tts = scripted.bind(pipeline.settings, pipeline.db)
    monkeypatch.setattr(pipeline_module.time, "sleep", lambda _seconds: None)

    class MismatchVerifier:
        def unload(self) -> None:
            return None

        def can_verify_repeated_short(self, _text: str) -> bool:
            return False

        def verify(self, _text: str, _wav: Path, *, confirmation: bool = False):
            return _asr_result(
                ASR_MISMATCH,
                "sai nội dung",
                similarity=0.1,
                wer=1.0,
            )

    pipeline._verify_chapter_audio(chapter, MismatchVerifier())

    fresh = pipeline.db.get_segment(int(row["id"]))
    assert fresh["status"] == "failed"
    final_check = pipeline.db.latest_quality_check(
        scope=QUALITY_SCOPE_SEGMENT,
        stage=SEGMENT_AUDIO_QUALITY_STAGE,
        segment_id=int(row["id"]),
    )
    assert final_check is not None
    assert final_check["verdict"] == "fail"
    assert final_check["artifact_sha256"] == row["wav_sha256"]
    metrics = json.loads(str(final_check["metrics_json"]))
    assert metrics["reason"] == "ASR_MISMATCH_UNRESOLVED"
    assert metrics["repair_trigger_reason"] == "ASR_MISMATCH"
    attempts = pipeline.db.segment_candidate_attempt_summary(
        int(row["id"]),
        pipeline.quality_policy_hash,
    )
    assert len(attempts) == 1
    assert attempts[0]["state"] == "tts_failed"
    assert "clarity inference failed" in attempts[0]["failure_reason"]

    pipeline._export_reports(incremental=True)
    report = json.loads(
        (pipeline.paths.reports / "audiobook_quality_report.json").read_text(
            encoding="utf-8"
        )
    )
    evidence = report["segment_content_evidence"][0]
    assert evidence["verdict"] == "fail"
    assert evidence["current_artifact"] is True
    assert evidence["current_policy_verified"] is False
    assert evidence["failure_codes"] == ["ASR_MISMATCH"]
    candidate_evidence = report["segment_repair_candidates"]
    assert len(candidate_evidence) == 1
    assert candidate_evidence[0]["current_policy"] is True
    assert candidate_evidence[0]["attempts"][0]["state"] == "tts_failed"
    assert "clarity inference failed" in candidate_evidence[0]["attempts"][0][
        "failure_reason"
    ]


def test_report_marks_prior_policy_candidate_history_as_stale(
    tmp_path: Path,
) -> None:
    pipeline, chapter, row, _expected = _asr_signal_pipeline(tmp_path, repair_rounds=1)

    class MismatchVerifier:
        def unload(self) -> None:
            return None

        def can_verify_repeated_short(self, _text: str) -> bool:
            return False

        def verify(self, _text: str, _wav: Path, *, confirmation: bool = False):
            return _asr_result(
                ASR_MISMATCH,
                "sai nội dung",
                similarity=0.1,
                wer=1.0,
            )

    pipeline._verify_chapter_audio(chapter, MismatchVerifier())
    old_policy_hash = pipeline.quality_policy_hash

    new_settings = json.loads(json.dumps(pipeline.settings))
    new_settings["asr"]["min_similarity"] = min(
        0.99,
        float(new_settings["asr"]["min_similarity"]) + 0.01,
    )
    refreshed = BookPipeline(
        paths=pipeline.paths,
        db=pipeline.db,
        settings=new_settings,
        pause_requested=lambda: False,
        stop_requested=lambda: False,
        emit=lambda _kind, _payload: None,
    )
    refreshed.tts = FakeTTS(new_settings, pipeline.db)
    refreshed._recover()
    assert refreshed.quality_policy_hash != old_policy_hash
    refreshed._export_reports(incremental=True)

    report = json.loads(
        (pipeline.paths.reports / "audiobook_quality_report.json").read_text(
            encoding="utf-8"
        )
    )
    candidate_evidence = report["segment_repair_candidates"]
    assert len(candidate_evidence) == 1
    assert candidate_evidence[0]["policy_hash"] == old_policy_hash
    assert candidate_evidence[0]["current_policy"] is False
    assert candidate_evidence[0]["attempts"][0]["state"] == "dual_failed"
    content_evidence = report["segment_content_evidence"][0]
    assert content_evidence["evidence_present"] is False
    assert content_evidence["current_policy_verified"] is False


def test_crash_before_atomic_exhaustion_keeps_candidate_budget_exhausted(
    tmp_path: Path,
    monkeypatch,
) -> None:
    pipeline, chapter, row, _expected = _asr_signal_pipeline(tmp_path, repair_rounds=1)
    scripted = ScriptedShortTTS(
        [
            AudioQualityError("clarity inference failed")
            for _attempt in range(int(pipeline.settings["tts"]["max_retries"]))
        ]
    )
    pipeline.tts = scripted.bind(pipeline.settings, pipeline.db)
    monkeypatch.setattr(pipeline_module.time, "sleep", lambda _seconds: None)

    class MismatchVerifier:
        def unload(self) -> None:
            return None

        def can_verify_repeated_short(self, _text: str) -> bool:
            return False

        def verify(self, _text: str, _wav: Path, *, confirmation: bool = False):
            return _asr_result(
                ASR_MISMATCH,
                "sai nội dung",
                similarity=0.1,
                wer=1.0,
            )

    original_finalize = pipeline.db.finalize_segment_candidate_exhaustion
    monkeypatch.setattr(
        pipeline.db,
        "finalize_segment_candidate_exhaustion",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            RuntimeError("simulated crash before atomic exhaustion")
        ),
    )
    with pytest.raises(RuntimeError, match="simulated crash before atomic exhaustion"):
        pipeline._verify_chapter_audio(chapter, MismatchVerifier())

    crashed = pipeline.db.get_segment(int(row["id"]))
    trigger_check = pipeline.db.latest_quality_check(
        scope=QUALITY_SCOPE_SEGMENT,
        stage=SEGMENT_AUDIO_QUALITY_STAGE,
        segment_id=int(row["id"]),
    )
    assert trigger_check is not None
    assert trigger_check["verdict"] == "repair"
    assert trigger_check["artifact_sha256"] == row["wav_sha256"]
    assert crashed["status"] == "signal_passed"
    assert crashed["wav_path"] == row["wav_path"]
    assert crashed["wav_sha256"] == row["wav_sha256"]
    attempts = pipeline.db.segment_candidate_attempt_summary(
        int(row["id"]),
        pipeline.quality_policy_hash,
    )
    assert [attempt["state"] for attempt in attempts] == ["tts_failed"]
    calls_before_resume = len(scripted.calls)

    monkeypatch.setattr(
        pipeline.db,
        "finalize_segment_candidate_exhaustion",
        original_finalize,
    )
    pipeline._verify_chapter_audio(chapter, MismatchVerifier())

    assert len(scripted.calls) == calls_before_resume
    resumed = pipeline.db.get_segment(int(row["id"]))
    assert resumed["status"] == "failed"
    assert resumed["wav_path"] == row["wav_path"]
    final_check = pipeline.db.latest_quality_check(
        scope=QUALITY_SCOPE_SEGMENT,
        stage=SEGMENT_AUDIO_QUALITY_STAGE,
        segment_id=int(row["id"]),
    )
    assert final_check is not None
    assert final_check["verdict"] == "fail"
    assert final_check["artifact_sha256"] == row["wav_sha256"]


def test_report_treats_previous_policy_content_evidence_as_missing(
    tmp_path: Path,
) -> None:
    pipeline, _chapter, row, expected = _asr_signal_pipeline(tmp_path, repair_rounds=0)
    pipeline._record_segment_audio_pass(
        dict(row),
        _asr_result(ASR_PASS, expected, similarity=1.0, wer=0.0),
        confirmation=False,
        decode_evidence=[],
    )
    replacement_policy = json.loads(json.dumps(pipeline.quality_policy))
    replacement_policy["algorithms"]["asr_content"] = "future-policy"
    replacement_hash = quality_policy_hash(replacement_policy)
    pipeline.db.set_current_quality_policy(
        policy_hash=replacement_hash,
        policy_version=QUALITY_POLICY_VERSION,
        policy=replacement_policy,
    )
    pipeline.quality_policy = replacement_policy
    pipeline.quality_policy_hash = replacement_hash

    pipeline._export_reports(incremental=True)

    report = json.loads(
        (pipeline.paths.reports / "audiobook_quality_report.json").read_text(
            encoding="utf-8"
        )
    )
    evidence = report["segment_content_evidence"][0]
    assert evidence["evidence_present"] is False
    assert evidence["verdict"] == "missing"
    assert evidence["current_artifact"] is False
    assert evidence["current_policy_verified"] is False


@pytest.mark.parametrize(
    ("initial_verdict", "initial_reason"),
    [
        (ASR_MISMATCH, "ASR_MISMATCH"),
        (ASR_INCONCLUSIVE, "ASR_TRANSCRIPT_TIMELINE_IMPOSSIBLE"),
    ],
)
def test_successful_confirmation_decode_clears_initial_asr_false_negative(
    tmp_path: Path,
    initial_verdict: str,
    initial_reason: str,
) -> None:
    source = tmp_path / "001.txt"
    expected = "Một câu đủ dài để xác nhận nội dung bằng Whisper lần thứ hai."
    source.write_text(expected, encoding="utf-8")
    settings = build_settings(overrides={"tts": {"min_seconds_per_100_chars": 0.2}})
    paths, db, settings = create_or_open_project(
        [source],
        tmp_path / "out",
        settings,
        "ASR confirmation",
    )
    pipeline = BookPipeline(
        paths=paths,
        db=db,
        settings=settings,
        pause_requested=lambda: False,
        stop_requested=lambda: False,
        emit=lambda _kind, _payload: None,
    )
    pipeline.tts = FakeTTS(settings, db)
    pipeline._recover()
    pipeline._ensure_segments()
    chapter = db.list_chapters()[0]
    row = db.list_segments(chapter_id=int(chapter["id"]))[0]
    wav = pipeline._chunk_path(row)
    audio = np.sin(np.linspace(0, 50, 96_000, dtype=np.float32)) * 0.12
    checksum, metrics = atomic_write_wav(
        wav,
        audio,
        48_000,
        str(row["text"]),
        settings,
        segment=row,
    )
    db.mark_signal_passed(
        int(row["id"]),
        wav_path=wav,
        wav_sha256=checksum,
        duration=float(metrics["duration"]),
        signal=metrics,
    )

    class ScriptedVerifier:
        def __init__(self) -> None:
            self.calls = 0

        def unload(self) -> None:
            return None

        def can_verify_repeated_short(self, _text: str) -> bool:
            return False

        def verify(self, _text: str, _wav: Path, *, confirmation: bool = False):
            self.calls += 1
            if not confirmation:
                return {
                    "passed": False,
                    "verdict": initial_verdict,
                    "transcript": "nội dung nhận nhầm",
                    "similarity": 0.1,
                    "wer": 0.9,
                    "reason": initial_reason,
                    "repairable": True,
                }
            return {
                "passed": True,
                "verdict": ASR_PASS,
                "transcript": expected,
                "similarity": 1.0,
                "wer": 0.0,
                "reason": "ok",
                "repairable": False,
            }

    verifier = ScriptedVerifier()
    pipeline._verify_chapter_audio(chapter, verifier)

    fresh = db.get_segment(int(row["id"]))
    assert verifier.calls == 2
    assert str(fresh["status"]) == "verified"
    assert pipeline.tts.synthesize_calls == 0
    assert db.segment_audio_is_current_qa_verified(
        int(row["id"]),
        str(fresh["wav_sha256"]),
        SEGMENT_AUDIO_QUALITY_STAGE,
    )


def resource_snapshot(free_ram_gb: float) -> ResourceSnapshot:
    return ResourceSnapshot(
        cpu_percent=20.0,
        free_ram_gb=free_ram_gb,
        disk_free_gb=100.0,
        disk_active_percent=5.0,
        gpu_temp_c=70,
        gpu_free_mb=6000,
        gpu_total_mb=8151,
        foreground_cpu_percent=5.0,
        foreground_gpu_percent=0.0,
        seconds_since_user_input=30.0,
    )


def test_mock_pipeline_completes_without_interactive_prompt(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "001.txt"
    source.write_text("Rầm! Cánh cửa mở ra.\n\nĐây là một đoạn kể chuyện đủ dài để kiểm tra pipeline.", encoding="utf-8")
    settings = build_settings(profile="balanced", overrides={
        "analysis": {"enabled": False},
        "asr": {
            "enabled": False,
            "required": False,
            "failure_policy": "warning_continue",
        },
        "resources": {"min_free_disk_gb": 0.01, "critical_free_disk_gb": 0.001},
        "tts": {"min_seconds_per_100_chars": 0.2},
    })
    paths, db, settings = create_or_open_project([source], tmp_path / "out", settings, "Test Book")
    pronunciation_passes = 0

    def fake_name_pronunciations(*_args, **_kwargs):
        nonlocal pronunciation_passes
        pronunciation_passes += 1
        return 0

    monkeypatch.setattr(
        "ebook_reader.analysis.OllamaBookAnalyzer.reconcile_name_pronunciations",
        fake_name_pronunciations,
    )

    def fake_chapter(wavs, output, settings, **kwargs):
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(b"ID3" + b"x" * 5000)
        quality = SimpleNamespace(
            to_dict=lambda: {"hard_failures": [], "review_flags": []},
            review_flags=(),
        )
        return SimpleNamespace(checksum="chapterhash", quality=quality)

    monkeypatch.setattr("ebook_reader.pipeline.assemble_chapter_atomic_with_metrics", fake_chapter)
    monkeypatch.setattr("ebook_reader.pipeline.verify_mp3", lambda path: (path.exists(), "ok"))
    verify_calls = 0
    verify_calls_by_path: dict[str, int] = {}
    verified_texts: list[str] = []

    def fake_verify(_verifier, expected, wav_path, *, confirmation=False):
        nonlocal verify_calls
        verify_calls += 1
        path_key = str(wav_path)
        verify_calls_by_path[path_key] = verify_calls_by_path.get(path_key, 0) + 1
        verified_texts.append(expected)
        passed = (
            "candidates" in Path(wav_path).parts
            or verify_calls_by_path[path_key] > 2
        )
        return {
            "passed": passed,
            "transcript": expected if passed else "sai nội dung",
            "similarity": 1.0 if passed else 0.0,
            "wer": 0.0 if passed else 1.0,
            "reason": "ok" if passed else "ASR_MISMATCH",
            "repairable": True,
        }

    monkeypatch.setattr("ebook_reader.pipeline.WhisperVerifier.verify", fake_verify)
    monkeypatch.setattr(
        "ebook_reader.pipeline.WhisperVerifier.can_verify_repeated_short",
        lambda _verifier, _expected: False,
    )

    events = []
    pipeline = BookPipeline(
        paths=paths,
        db=db,
        settings=settings,
        pause_requested=lambda: False,
        stop_requested=lambda: False,
        emit=lambda kind, payload: events.append((kind, payload)),
    )
    pipeline.tts = FakeTTS(settings, db)
    pipeline.run()

    assert db.book()["status"] == "completed"
    assert db.list_chapters()[0]["status"] == "completed"
    assert db.casting_is_finalized() is True
    segments = db.list_segments()
    assert int(segments[0]["generation_seed"]) != 1
    assert segments[0]["generation_delivery_mode"] == "clarity"
    assert "candidates" in Path(str(segments[0]["wav_path"])).parts
    assert segments[0]["kind"] == "narration"
    assert segments[0]["text"] == "Rầm! Cánh cửa mở ra."
    assert segments[0]["status"] in {"verified", "warning"}
    assert "Rầm! Cánh cửa mở ra." in verified_texts
    assert any(kind == "chapter_completed" for kind, _ in events)
    progress_labels = [
        str(payload["label"])
        for kind, payload in events
        if kind == "work_progress"
    ]
    assert any(label.startswith("Chuẩn bị và chia văn bản") for label in progress_labels)
    assert any(label.startswith("Tạo audio chapter") for label in progress_labels)
    assert any(label.startswith("Kiểm tra phát âm chapter") for label in progress_labels)
    assert any(label.startswith("Tạo candidate clarity chapter") for label in progress_labels)
    assert any(label.startswith("Ghép và kiểm tra MP3 chapter") for label in progress_labels)
    assert pronunciation_passes == 1
    quality_report = json.loads(
        (paths.reports / "audiobook_quality_report.json").read_text(encoding="utf-8")
    )
    content_evidence = quality_report["segment_content_evidence"]
    assert len(content_evidence) == len(segments)
    assert all(item["evidence_present"] for item in content_evidence)
    assert all(item["current_policy_verified"] for item in content_evidence)
    assert all(item["decode_evidence"] for item in content_evidence)
    repair_evidence = quality_report["segment_repair_candidates"]
    assert len(repair_evidence) == len(segments)
    assert all(item["current_policy"] for item in repair_evidence)
    assert all(item["promoted"] for item in repair_evidence)
    assert all(
        item["attempts"][0]["state"] == "promoted"
        for item in repair_evidence
    )

    # A full resume/reopen pass must preserve locked voice identities and skip valid output.
    resumed = BookPipeline(
        paths=paths,
        db=db,
        settings=settings,
        pause_requested=lambda: False,
        stop_requested=lambda: False,
        emit=lambda kind, payload: events.append((kind, payload)),
    )
    resumed.tts = FakeTTS(settings, db)
    resumed.run()
    assert pronunciation_passes == 1
    assert db.book()["status"] == "completed"

    # A legacy verified/warning WAV has no policy-bound segment QA evidence. Resume must
    # reuse the valid waveform, rerun ASR, and avoid paying for TTS generation again.
    with db.connect() as conn:
        conn.execute("DELETE FROM segment_candidates")
        conn.execute(
            "DELETE FROM quality_checks WHERE scope=?",
            (QUALITY_SCOPE_SEGMENT,),
        )
        legacy_segments = list(conn.execute("SELECT id,seq FROM segments ORDER BY seq"))
        for legacy_segment in legacy_segments:
            status = "verified" if int(legacy_segment["seq"]) % 2 == 0 else "warning"
            warning = None if status == "verified" else "ASR_TRANSCRIPT_TIMELINE_IMPOSSIBLE"
            conn.execute(
                "UPDATE segments SET status=?,warning_code=? WHERE id=?",
                (status, warning, int(legacy_segment["id"])),
            )
        conn.execute("UPDATE chapters SET status='failed'")
        conn.execute("UPDATE book SET status='error',stage='completed_with_errors'")

    calls_before_legacy_resume = verify_calls
    legacy_resume = BookPipeline(
        paths=paths,
        db=db,
        settings=settings,
        pause_requested=lambda: False,
        stop_requested=lambda: False,
        emit=lambda kind, payload: events.append((kind, payload)),
    )
    legacy_resume.tts = FakeTTS(settings, db)
    legacy_resume.run()

    assert legacy_resume.tts.synthesize_calls == 0
    assert verify_calls > calls_before_legacy_resume
    for segment in db.list_segments():
        assert db.segment_audio_is_current_qa_verified(
            int(segment["id"]),
            str(segment["wav_sha256"]),
            SEGMENT_AUDIO_QUALITY_STAGE,
        )
        assert "ASR_TRANSCRIPT_TIMELINE_IMPOSSIBLE" not in str(segment["warning_code"] or "")


def test_completed_with_errors_notifies_and_emits_error_state(tmp_path: Path) -> None:
    source = tmp_path / "001.txt"
    source.write_text("Nội dung chapter sẽ được đánh dấu lỗi.", encoding="utf-8")
    settings = build_settings()
    paths, db, settings = create_or_open_project([source], tmp_path / "out", settings, "Test Book")
    chapter = db.list_chapters()[0]
    db.update_chapter_status(int(chapter["id"]), "failed", error="segment lỗi")
    events = []
    notifier = FakeNotifier()
    pipeline = BookPipeline(
        paths=paths,
        db=db,
        settings=settings,
        pause_requested=lambda: False,
        stop_requested=lambda: False,
        emit=lambda kind, payload: events.append((kind, payload)),
    )
    pipeline.notifier = notifier

    pipeline._finalize_book()

    book = db.book()
    assert book["status"] == "error"
    assert book["stage"] == "completed_with_errors"
    assert len(notifier.critical_calls) == 1
    assert any(
        kind == "state" and payload["state"] == "error"
        for kind, payload in events
    )


def test_resume_accepts_identical_segments_from_a_different_parser_fingerprint(
    tmp_path: Path,
) -> None:
    source = tmp_path / "001.txt"
    source.write_text("Nội dung đủ dài để kiểm tra fingerprint parser.", encoding="utf-8")
    settings = build_settings()
    paths, db, settings = create_or_open_project(
        [source],
        tmp_path / "out",
        settings,
        "Parser fingerprint",
    )
    original = BookPipeline(
        paths=paths,
        db=db,
        settings=settings,
        pause_requested=lambda: False,
        stop_requested=lambda: False,
        emit=lambda _kind, _payload: None,
    )
    original._recover()
    original._ensure_segments()

    changed = BookPipeline(
        paths=paths,
        db=db,
        settings=settings,
        pause_requested=lambda: False,
        stop_requested=lambda: False,
        emit=lambda _kind, _payload: None,
    )
    changed.quality_policy["stage_fingerprints"][TEXT_SEGMENTATION_STAGE] = "changed"
    changed.quality_policy_hash = quality_policy_hash(changed.quality_policy)

    changed._recover()
    assert str(db.current_quality_policy()["policy_hash"]) == changed.quality_policy_hash


def test_resume_rejects_different_segments_from_a_different_parser_fingerprint(
    tmp_path: Path,
) -> None:
    source = tmp_path / "001.txt"
    source.write_text("Nội dung đủ dài để kiểm tra fingerprint parser.", encoding="utf-8")
    settings = build_settings()
    paths, db, settings = create_or_open_project(
        [source],
        tmp_path / "out",
        settings,
        "Parser fingerprint mismatch",
    )
    original = BookPipeline(
        paths=paths,
        db=db,
        settings=settings,
        pause_requested=lambda: False,
        stop_requested=lambda: False,
        emit=lambda _kind, _payload: None,
    )
    original._recover()
    original._ensure_segments()
    segment = db.list_segments()[0]
    with db.connect() as conn:
        conn.execute(
            "UPDATE segments SET break_ms=? WHERE id=?",
            (int(segment["break_ms"]) + 1, int(segment["id"])),
        )

    changed = BookPipeline(
        paths=paths,
        db=db,
        settings=settings,
        pause_requested=lambda: False,
        stop_requested=lambda: False,
        emit=lambda _kind, _payload: None,
    )
    changed.quality_policy["stage_fingerprints"][TEXT_SEGMENTATION_STAGE] = "changed"
    changed.quality_policy_hash = quality_policy_hash(changed.quality_policy)

    with pytest.raises(RuntimeError, match="does not reproduce the checkpoint exactly"):
        changed._recover()


def test_resume_rejects_locked_casting_from_a_different_fingerprint(tmp_path: Path) -> None:
    source = tmp_path / "001.txt"
    source.write_text("Nội dung đủ dài để kiểm tra fingerprint casting.", encoding="utf-8")
    settings = build_settings()
    paths, db, settings = create_or_open_project(
        [source],
        tmp_path / "out",
        settings,
        "Casting fingerprint",
    )
    original = BookPipeline(
        paths=paths,
        db=db,
        settings=settings,
        pause_requested=lambda: False,
        stop_requested=lambda: False,
        emit=lambda _kind, _payload: None,
    )
    original._recover()
    original._ensure_segments()
    db.finalize_casting()

    changed = BookPipeline(
        paths=paths,
        db=db,
        settings=settings,
        pause_requested=lambda: False,
        stop_requested=lambda: False,
        emit=lambda _kind, _payload: None,
    )
    changed.quality_policy["stage_fingerprints"][ANALYSIS_CASTING_STAGE] = "changed"
    changed.quality_policy_hash = quality_policy_hash(changed.quality_policy)

    with pytest.raises(RuntimeError, match="Analysis/casting implementation changed"):
        changed._recover()


def test_resume_rejects_old_analysis_candidate_even_when_segments_are_pending(
    tmp_path: Path,
    monkeypatch,
) -> None:
    source = tmp_path / "001.txt"
    source.write_text("Nội dung đủ dài để kiểm tra candidate fingerprint.", encoding="utf-8")
    settings = build_settings()
    paths, db, settings = create_or_open_project(
        [source],
        tmp_path / "out",
        settings,
        "Candidate fingerprint",
    )
    original = BookPipeline(
        paths=paths,
        db=db,
        settings=settings,
        pause_requested=lambda: False,
        stop_requested=lambda: False,
        emit=lambda _kind, _payload: None,
    )
    original._recover()
    original._ensure_segments()
    assert all(str(row["status"]) == "pending" for row in db.list_segments())
    monkeypatch.setattr(db, "has_analysis_candidates", lambda: True)

    changed = BookPipeline(
        paths=paths,
        db=db,
        settings=settings,
        pause_requested=lambda: False,
        stop_requested=lambda: False,
        emit=lambda _kind, _payload: None,
    )
    changed.quality_policy["stage_fingerprints"][ANALYSIS_CASTING_STAGE] = "changed"
    changed.quality_policy_hash = quality_policy_hash(changed.quality_policy)

    with pytest.raises(RuntimeError, match="Analysis/casting implementation changed"):
        changed._recover()


def test_chapter_quality_failure_is_checkpointed_and_later_chapters_continue(
    tmp_path: Path,
    monkeypatch,
) -> None:
    sources = []
    for index in range(2):
        source = tmp_path / f"{index:03d}.txt"
        source.write_text(f"Nội dung chapter {index + 1} đủ dài để kiểm tra.", encoding="utf-8")
        sources.append(source)
    settings = build_settings()
    paths, db, settings = create_or_open_project(
        sources,
        tmp_path / "out",
        settings,
        "Quality containment",
    )
    events = []
    pipeline = BookPipeline(
        paths=paths,
        db=db,
        settings=settings,
        pause_requested=lambda: False,
        stop_requested=lambda: False,
        emit=lambda kind, payload: events.append((kind, payload)),
    )
    db.set_current_quality_policy(
        policy_hash=pipeline.quality_policy_hash,
        policy_version=QUALITY_POLICY_VERSION,
        policy=pipeline.quality_policy,
    )
    processed: list[int] = []

    def fail_first_chapter(chapter, _verifier) -> None:
        chapter_index = int(chapter["chapter_index"])
        processed.append(chapter_index)
        if chapter_index == 1:
            raise ChapterQualityError(
                "forced perceptual review",
                artifact_sha256="f" * 64,
                metrics={"review_flags": ["join discontinuity"]},
                failure_codes=("CHAPTER_QA_REVIEW_REQUIRED",),
                review_required=True,
            )
        db.update_chapter_status(int(chapter["id"]), "completed")

    monkeypatch.setattr(pipeline, "_process_chapter", fail_first_chapter)

    pipeline._process_all_chapters(SimpleNamespace())

    chapters = db.list_chapters()
    assert processed == [1, 2]
    assert [str(chapter["status"]) for chapter in chapters] == ["failed", "completed"]
    assert "forced perceptual review" in str(chapters[0]["last_error"])
    failure = db.latest_quality_check(
        scope=QUALITY_SCOPE_CHAPTER,
        stage=CHAPTER_QUALITY_STAGE,
        chapter_id=int(chapters[0]["id"]),
    )
    assert failure is not None
    assert failure["verdict"] == "fail"
    assert failure["artifact_sha256"] == "f" * 64
    assert failure["failure_codes_json"] == '["CHAPTER_QA_REVIEW_REQUIRED"]'
    assert json.loads(str(failure["metrics_json"]))["review_required"] is True
    assert any(kind == "chapter_failed" for kind, _payload in events)
    assert len([kind for kind, _payload in events if kind == "chapter_progress"]) == 2

    pipeline._export_reports()
    chapter_report = json.loads(
        (paths.reports / "chapter_quality.json").read_text(encoding="utf-8")
    )
    assert len(chapter_report) == 2
    assert chapter_report[0]["status"] == "failed"
    assert chapter_report[0]["artifact_verified"] is False
    assert chapter_report[0]["current_policy_verified"] is False
    assert chapter_report[0]["latest_quality_check"]["verdict"] == "fail"
    assert chapter_report[0]["latest_quality_check"]["metrics"]["review_required"] is True
    assert chapter_report[1]["status"] == "completed"
    quality_report = json.loads(
        (paths.reports / "audiobook_quality_report.json").read_text(encoding="utf-8")
    )
    assert quality_report["schema_version"] == 1
    assert quality_report["book"]["chapters_total"] == 2
    assert quality_report["book"]["failed"] == 1
    assert len(quality_report["review_required"]["chapters"]) == 2

    resumed: list[int] = []

    def complete_failed_chapter(chapter, _verifier) -> None:
        if str(chapter["status"]) == "completed":
            return
        resumed.append(int(chapter["chapter_index"]))
        db.update_chapter_status(int(chapter["id"]), "completed")

    monkeypatch.setattr(pipeline, "_process_chapter", complete_failed_chapter)
    pipeline._process_all_chapters(SimpleNamespace())

    assert resumed == [1]
    assert [str(chapter["status"]) for chapter in db.list_chapters()] == [
        "completed",
        "completed",
    ]


def test_critical_ram_unloads_models_and_continues_after_recovery(
    tmp_path: Path,
    monkeypatch,
) -> None:
    source = tmp_path / "001.txt"
    source.write_text("Nội dung kiểm tra phục hồi RAM.", encoding="utf-8")
    settings = build_settings()
    paths, db, settings = create_or_open_project([source], tmp_path / "out", settings, "Test Book")
    events = []
    notifier = FakeNotifier()
    pipeline = BookPipeline(
        paths=paths,
        db=db,
        settings=settings,
        pause_requested=lambda: False,
        stop_requested=lambda: False,
        emit=lambda kind, payload: events.append((kind, payload)),
    )
    pipeline.tts = FakeTTS(settings, db)
    pipeline.notifier = notifier
    snapshots = iter((resource_snapshot(0.8), resource_snapshot(8.0)))
    monkeypatch.setattr(pipeline.resources, "snapshot", lambda force=False: next(snapshots))
    monkeypatch.setattr("ebook_reader.pipeline.time.sleep", lambda _seconds: None)

    decision = pipeline._resource_gate("chapter 1 segment 75", keep_engine="vieneu")

    assert decision.level != ResourceLevel.CRITICAL_STOP
    assert decision.critical is False
    assert decision.allow_new_gpu_batch is True
    assert pipeline.tts.unload_calls == 1
    assert notifier.critical_calls == []
    assert db.book()["status"] != "stopped"
    assert any(
        kind == "log" and "0.8 → 8.0 GB" in str(payload["text"])
        for kind, payload in events
    )


def test_critical_ram_stops_only_when_recovery_is_insufficient(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """Memory that never comes back still ends the run.

    "Insufficient" used to mean "still short after one two-second retry". It now means
    "still short after the wait window", because a shortage another program is holding
    ends when that program does, and alpha.26 threw away 357 segments of work to a
    shortage that was not its own. The window is set to zero here so this test keeps
    asking its original question - what happens when the memory is simply gone - and
    test_waiting_for_foreign_ram.py covers the waiting itself.
    """
    monkeypatch.setattr(
        "ebook_reader.pipeline.CRITICAL_RAM_WAIT_TIMEOUT_SECONDS", 0.0
    )
    source = tmp_path / "001.txt"
    source.write_text("Nội dung kiểm tra RAM vẫn thiếu.", encoding="utf-8")
    settings = build_settings()
    paths, db, settings = create_or_open_project([source], tmp_path / "out", settings, "Test Book")
    notifier = FakeNotifier()
    pipeline = BookPipeline(
        paths=paths,
        db=db,
        settings=settings,
        pause_requested=lambda: False,
        stop_requested=lambda: False,
        emit=lambda _kind, _payload: None,
    )
    pipeline.tts = FakeTTS(settings, db)
    pipeline.notifier = notifier
    snapshots = iter((resource_snapshot(0.8), resource_snapshot(0.7)))
    monkeypatch.setattr(pipeline.resources, "snapshot", lambda force=False: next(snapshots))
    monkeypatch.setattr("ebook_reader.pipeline.time.sleep", lambda _seconds: None)

    with pytest.raises(CriticalResourceStop, match="available RAM 0.7 GB"):
        pipeline._resource_gate("chapter 1 segment 75", keep_engine="vieneu")

    assert pipeline.tts.unload_calls == 1
    assert db.book()["status"] == "stopped"
    assert db.book()["stage"] == "critical_stop"
    assert len(notifier.critical_calls) == 1


def test_the_gate_carries_on_when_borrowed_memory_comes_back(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """The whole point of the wait, seen from the gate rather than from inside it.

    Three Unity editors were holding five and a half gigabytes when alpha.26 stopped. The
    run had already released its own models; there was nothing more it could give. Once
    the other program lets go, the gate has no reason left to refuse.
    """
    source = tmp_path / "001.txt"
    source.write_text("Nội dung kiểm tra RAM hồi phục.", encoding="utf-8")
    settings = build_settings()
    paths, db, settings = create_or_open_project(
        [source], tmp_path / "out", settings, "Test Book"
    )
    notifier = FakeNotifier()
    pipeline = BookPipeline(
        paths=paths,
        db=db,
        settings=settings,
        pause_requested=lambda: False,
        stop_requested=lambda: False,
        emit=lambda _kind, _payload: None,
    )
    pipeline.tts = FakeTTS(settings, db)
    pipeline.notifier = notifier
    # Short, still short after unloading, then the other program closes.
    snapshots = iter(
        (resource_snapshot(0.8), resource_snapshot(0.7), resource_snapshot(16.0))
    )
    monkeypatch.setattr(pipeline.resources, "snapshot", lambda force=False: next(snapshots))
    monkeypatch.setattr("ebook_reader.pipeline.time.sleep", lambda _seconds: None)

    decision = pipeline._resource_gate("chapter 1 segment 75", keep_engine="vieneu")

    assert decision.critical is False
    assert db.book()["status"] != "stopped"
    assert notifier.critical_calls == []


@pytest.mark.parametrize("ordinary_content_is_clean", [True, False])
def test_locked_name_failure_evidence_stays_self_consistent(
    ordinary_content_is_clean: bool,
) -> None:
    """The candidate ledger rejects evidence whose parts disagree.

    An earlier attempt at the review downgrade changed `reason` to ASR_MISMATCH when the
    canonical thresholds failed while `failure_codes` still named the anchor, and a real
    run died on `candidate ASR locked-name failure evidence is internally inconsistent`
    halfway through a chapter. Both review-eligible and not-eligible results must satisfy
    the same contract.
    """
    transcript = (
        "Lúc chia tay, Lucian len lén hỏi bạn đầy tò mò."
        if ordinary_content_is_clean
        # Segmental errors, not tone slips: tone differences are folded out of the
        # metrics because they carry no signal about the take, so a "dirty" example
        # built from them would now read as clean.
        else "Mây chia lìa, Lucian ben khén hỏi vàng đầu mù mò."
    )
    result = adjudicate_locked_name_anchors(
        "Lúc chia tay, Lu-si-en len lén hỏi bạn đầy tò mò.",
        {
            "passed": False,
            "verdict": ASR_MISMATCH,
            "transcript": transcript,
            "similarity": 0.96 if ordinary_content_is_clean else 0.70,
            "wer": 0.10 if ordinary_content_is_clean else 0.60,
            "reason": "ASR_MISMATCH",
            "repairable": True,
            "severe": False,
        },
        [_locked_lucien_anchor(spoken_start=14)],
        min_similarity=0.78,
        max_wer=0.30,
    )

    assert result["locked_name_review_eligible"] is ordinary_content_is_clean

    # Compose the decode evidence exactly as _record_segment_asr_evidence does: the
    # anchor's own failure codes, plus the result reason when the verdict is not a pass.
    anchor_metrics = result[LOCKED_NAME_ANCHOR_METRICS_KEY]
    assert isinstance(anchor_metrics, dict)
    evidence_failure_codes = list(anchor_metrics["failure_codes"])
    if str(result["reason"]) not in evidence_failure_codes:
        evidence_failure_codes.append(str(result["reason"]))
    evidence = {**result, "failure_codes": evidence_failure_codes}

    # Composition must collapse to exactly one code, or the ledger rejects the evidence.
    assert evidence_failure_codes == [ASR_LOCKED_NAME_ANCHOR_MISMATCH]
    assert BookPipeline._decode_requests_source_pronunciation(evidence) is True


def test_locked_name_review_does_not_block_its_chapter() -> None:
    """Publishing the segment is pointless if the chapter still refuses it.

    The first attempt at the review downgrade changed only the segment outcome, and a
    real run then held both chapters on exactly the warning that was supposed to let them
    through. The two decisions have to agree.
    """
    assert ASR_LOCKED_NAME_ANCHOR_REVIEW in HIGH_QUALITY_ALLOWED_SEGMENT_WARNINGS
    # A genuine mismatch still fails the segment, so it must not be waived here as well.
    assert ASR_LOCKED_NAME_ANCHOR_MISMATCH not in HIGH_QUALITY_ALLOWED_SEGMENT_WARNINGS
    assert PERCEPTUAL_NATURALNESS_REVIEW_CODE not in HIGH_QUALITY_ALLOWED_SEGMENT_WARNINGS


def test_a_take_the_listener_cleared_is_not_re_failed_by_the_next_resume(
    tmp_path: Path,
) -> None:
    """`accept` exists to remove a wall no machinery can get past, and the resume scan put
    it straight back.

    The acceptance lives in listener_audio_acceptances; the scan reads quality_checks. So a
    segment somebody had just cleared came back ASR_CONTENT_GATE_FAILED on the next resume,
    against the very wav_sha256 the acceptance names. alpha.46 showed it end to end: seven
    carried verdicts, three chapters reported unblocked, and the resume re-failed all three.
    """
    pipeline, _chapter, row, _expected = _asr_signal_pipeline(tmp_path, repair_rounds=1)
    pipeline.db.record_quality_check(
        scope=QUALITY_SCOPE_SEGMENT,
        stage=SEGMENT_AUDIO_QUALITY_STAGE,
        segment_id=int(row["id"]),
        artifact_sha256=str(row["wav_sha256"]),
        policy_hash=pipeline.quality_policy_hash,
        policy_version=QUALITY_POLICY_VERSION,
        verdict="fail",
        metrics={"reason": "ASR_MISMATCH_UNRESOLVED"},
    )
    assert pipeline._segment_has_current_asr_failure(row) is True

    pipeline.db.accept_segment_audio(
        segment_stable_id=str(row["stable_id"]),
        wav_sha256=str(row["wav_sha256"]),
        warning_code="ASR_LOCKED_NAME_ANCHOR_MISMATCH",
        note="chủ sách đã nghe: đọc đúng",
    )

    assert pipeline._segment_has_current_asr_failure(row) is False


def test_an_acceptance_does_not_survive_a_recut(tmp_path: Path) -> None:
    """Bound to the recording, not the row. A retry makes audio nobody has heard, and the
    stored failure must bite again."""
    pipeline, _chapter, row, _expected = _asr_signal_pipeline(tmp_path, repair_rounds=1)
    pipeline.db.record_quality_check(
        scope=QUALITY_SCOPE_SEGMENT,
        stage=SEGMENT_AUDIO_QUALITY_STAGE,
        segment_id=int(row["id"]),
        artifact_sha256=str(row["wav_sha256"]),
        policy_hash=pipeline.quality_policy_hash,
        policy_version=QUALITY_POLICY_VERSION,
        verdict="fail",
        metrics={"reason": "ASR_MISMATCH_UNRESOLVED"},
    )
    pipeline.db.accept_segment_audio(
        segment_stable_id=str(row["stable_id"]),
        wav_sha256="0" * 64,          # a different take entirely
        warning_code="ASR_LOCKED_NAME_ANCHOR_MISMATCH",
        note="nghe một bản thu khác",
    )

    assert pipeline._segment_has_current_asr_failure(row) is True


def test_a_chapter_counts_a_listener_cleared_take_as_evidence(tmp_path: Path) -> None:
    """The second gate with the same blindness, and the one that failed alpha.46's ch9.

    chapter_segments_have_current_audio_qa demanded a passing check for every segment. An
    acceptance leaves the machine's verdict at `fail` on purpose - a person overruled it,
    the machine did not change its mind - so the chapter refused the very segments `accept`
    had just released, under a different code: SEGMENT_QA_EVIDENCE_MISSING.
    """
    pipeline, chapter, row, _expected = _asr_signal_pipeline(tmp_path, repair_rounds=1)
    pipeline.db.record_quality_check(
        scope=QUALITY_SCOPE_SEGMENT,
        stage=SEGMENT_AUDIO_QUALITY_STAGE,
        segment_id=int(row["id"]),
        artifact_sha256=str(row["wav_sha256"]),
        policy_hash=pipeline.quality_policy_hash,
        policy_version=QUALITY_POLICY_VERSION,
        verdict="fail",
        metrics={"reason": "ASR_MISMATCH_UNRESOLVED"},
    )
    # As it stands after a real run: the listener accepts a segment that reached `warning`,
    # not one still mid-pipeline. Without this the gate refuses on the status check and
    # never reaches the question being tested.
    with pipeline.db.transaction() as conn:
        conn.execute("UPDATE segments SET status='warning' WHERE id=?", (int(row["id"]),))
    chapter_id = int(chapter["id"])
    assert pipeline.db.chapter_segments_have_current_audio_qa(chapter_id) is False

    pipeline.db.accept_segment_audio(
        segment_stable_id=str(row["stable_id"]),
        wav_sha256=str(row["wav_sha256"]),
        warning_code="ASR_LOCKED_NAME_ANCHOR_MISMATCH",
        note="chủ sách đã nghe: đọc đúng",
    )

    assert pipeline.db.chapter_segments_have_current_audio_qa(chapter_id) is True


def test_the_chapter_gate_ignores_an_acceptance_for_other_audio(tmp_path: Path) -> None:
    pipeline, chapter, row, _expected = _asr_signal_pipeline(tmp_path, repair_rounds=1)
    pipeline.db.record_quality_check(
        scope=QUALITY_SCOPE_SEGMENT,
        stage=SEGMENT_AUDIO_QUALITY_STAGE,
        segment_id=int(row["id"]),
        artifact_sha256=str(row["wav_sha256"]),
        policy_hash=pipeline.quality_policy_hash,
        policy_version=QUALITY_POLICY_VERSION,
        verdict="fail",
        metrics={"reason": "ASR_MISMATCH_UNRESOLVED"},
    )
    with pipeline.db.transaction() as conn:
        conn.execute("UPDATE segments SET status='warning' WHERE id=?", (int(row["id"]),))
    pipeline.db.accept_segment_audio(
        segment_stable_id=str(row["stable_id"]),
        wav_sha256="0" * 64,
        warning_code="ASR_LOCKED_NAME_ANCHOR_MISMATCH",
        note="một bản thu khác",
    )

    assert pipeline.db.chapter_segments_have_current_audio_qa(int(chapter["id"])) is False
