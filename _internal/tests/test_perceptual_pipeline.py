from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from ebook_reader.audio_io import ChapterQualityError
from ebook_reader.config import build_settings
from ebook_reader.database import (
    QUALITY_SCOPE_CHAPTER,
    QUALITY_SCOPE_SEGMENT,
    QUALITY_VERDICT_PASS,
    SEGMENT_AUDIO_QUALITY_STAGE,
    SEGMENT_PERCEPTUAL_QUALITY_STAGE,
)
from ebook_reader.io_utils import sha256_file
from ebook_reader.models import ResourceDecision, ResourceLevel
from ebook_reader.perceptual_qa import PerceptualQAUnavailable
from ebook_reader.pipeline import BookPipeline
from ebook_reader.project import create_or_open_project
from ebook_reader.quality_policy import CHAPTER_QUALITY_STAGE, QUALITY_POLICY_VERSION
from ebook_reader.voice_catalog import VOICE_PREVIEW_FILENAMES


class StaticPerceptualVerifier:
    def __init__(self, result: dict | Exception) -> None:
        self.result = result

    def verify(
        self,
        _wav_path: Path,
        _preset_name: str,
        *,
        pitch_semitones: int = 0,
    ) -> dict:
        if isinstance(self.result, Exception):
            raise self.result
        return {**self.result, "baseline_pitch_semitones": pitch_semitones}

    def unload(self) -> None:
        return None


class SequencePerceptualVerifier:
    def __init__(self, results: list[dict]) -> None:
        self.results = results
        self.verify_calls = 0

    def verify(
        self,
        _wav_path: Path,
        _preset_name: str,
        *,
        pitch_semitones: int = 0,
    ) -> dict:
        result = self.results[min(self.verify_calls, len(self.results) - 1)]
        self.verify_calls += 1
        return {**result, "baseline_pitch_semitones": pitch_semitones}

    def unload(self) -> None:
        return None


class RecordingPerceptualVerifier(StaticPerceptualVerifier):
    def __init__(self, result: dict) -> None:
        super().__init__(result)
        self.calls: list[tuple[str, int]] = []

    def verify(
        self,
        _wav_path: Path,
        preset_name: str,
        *,
        pitch_semitones: int = 0,
    ) -> dict:
        self.calls.append((preset_name, pitch_semitones))
        return super().verify(
            _wav_path,
            preset_name,
            pitch_semitones=pitch_semitones,
        )

class PassingWhisperVerifier:
    def __init__(self) -> None:
        self.verify_calls = 0

    def verify(
        self,
        expected_text: str,
        _wav_path: Path,
        *,
        confirmation: bool = False,
    ) -> dict:
        self.verify_calls += 1
        return {
            "passed": True,
            "verdict": "pass",
            "reason": "ASR_PASS",
            "transcript": expected_text,
            "similarity": 1.0,
            "wer": 0.0,
            "confirmation": confirmation,
        }

    def can_verify_repeated_short(self, _expected_text: str) -> bool:
        return False

    def unload(self) -> None:
        return None


def _pipeline_with_asr_evidence(tmp_path: Path) -> tuple[BookPipeline, object, object]:
    checkpoint = tmp_path / "utmos.pth"
    checkpoint.write_bytes(b"locked checkpoint")
    source = tmp_path / "001.txt"
    source.write_text("Một câu đủ dài để kiểm tra perceptual QA.", encoding="utf-8")
    settings = build_settings(
        overrides={
            "perceptual_qa": {"checkpoint_path": str(checkpoint), "device": "cpu"},
            "tts": {"min_seconds_per_100_chars": 0.2},
        }
    )
    paths, db, settings = create_or_open_project(
        [source],
        tmp_path / "out",
        settings,
        "Perceptual pipeline",
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
    chapter = db.list_chapters()[0]
    row = db.list_segments(chapter_id=int(chapter["id"]))[0]
    preset_name = next(iter(VOICE_PREVIEW_FILENAMES))
    profile_id = db.upsert_voice_profile(
        {
            "voice_key": "perceptual-test",
            "engine": "vieneu",
            "preset_name": preset_name,
            "description": "locked test voice",
            "seed": 1,
            "status": "ready",
        }
    )
    with db.connect() as conn:
        conn.execute(
            "UPDATE segments SET voice_profile_id=? WHERE id=?",
            (profile_id, int(row["id"])),
        )
    wav = paths.chunks / "chapter_00001" / "0000000.wav"
    wav.parent.mkdir(parents=True, exist_ok=True)
    sf.write(wav, np.zeros(16_000, dtype=np.float32), 16_000)
    checksum = sha256_file(wav)
    db.mark_signal_passed(
        int(row["id"]),
        wav_path=wav,
        wav_sha256=checksum,
        duration=1.0,
        signal={"duration": 1.0},
    )
    db.record_quality_check(
        scope=QUALITY_SCOPE_SEGMENT,
        stage=SEGMENT_AUDIO_QUALITY_STAGE,
        segment_id=int(row["id"]),
        artifact_sha256=checksum,
        policy_hash=pipeline.quality_policy_hash,
        policy_version=QUALITY_POLICY_VERSION,
        verdict=QUALITY_VERDICT_PASS,
    )
    db.mark_verified(int(row["id"]))
    pipeline._resource_gate = lambda *_args, **_kwargs: None  # type: ignore[method-assign]
    return pipeline, chapter, db.get_segment(int(row["id"]))


def _register_current_chapter_artifact(pipeline: BookPipeline, chapter) -> None:
    checksum = "a" * 64
    pipeline.db.record_quality_check(
        scope=QUALITY_SCOPE_CHAPTER,
        stage=CHAPTER_QUALITY_STAGE,
        chapter_id=int(chapter["id"]),
        artifact_sha256=checksum,
        policy_hash=pipeline.quality_policy_hash,
        policy_version=QUALITY_POLICY_VERSION,
        verdict=QUALITY_VERDICT_PASS,
    )
    pipeline.db.register_artifact(
        artifact_key=f"chapter_mp3:{chapter['chapter_index']}",
        kind="chapter_mp3",
        path=pipeline.paths.chapters / "chapter_00001.mp3",
        sha256=checksum,
        verified=True,
        metadata={"quality": pipeline.db.quality_metadata_for_current_policy()},
    )
    pipeline.db.update_chapter_status(int(chapter["id"]), "completed")


def _install_fake_repair_synthesis(
    pipeline: BookPipeline,
    monkeypatch,
) -> tuple[list[str], list[str]]:
    seed_salts: list[str] = []
    statuses_before_synthesis: list[str] = []

    def synthesize_candidate(row, candidate, _chapter, **_kwargs):
        segment_id = int(row["id"])
        statuses_before_synthesis.append(str(pipeline.db.get_segment(segment_id)["status"]))
        repair_round = int(candidate["repair_round"])
        seed_salts.append(pipeline._segment_candidate_seed_salt(repair_round, 0))
        wav = Path(str(candidate["wav_path"]))
        wav.parent.mkdir(parents=True, exist_ok=True)
        amplitude = 0.02 + (0.01 * len(seed_salts))
        sf.write(wav, np.full(16_000, amplitude, dtype=np.float32), 16_000)
        profile = pipeline.db.voice_profile(int(row["voice_profile_id"]))
        pitch_semitones = int(profile["pitch_semitones"] or 0)
        metrics = {
            "duration": 1.0,
            "tts_delivery_mode": "clarity",
            "asr_clarity_repair_round": repair_round,
            "spoken_text_sha256": str(candidate["expected_spoken_text_sha256"]),
            "pronunciation_delivery_variant": str(
                candidate["pronunciation_delivery_variant"]
            ),
            "voice_profile_id": int(profile["id"]),
            "pitch_semitones": pitch_semitones,
            "effective_pitch_semitones": pitch_semitones,
            "pitch_variant_skipped": 0.0,
            "pitch_variant_mixed": 0.0,
        }
        return pipeline._checkpoint_segment_candidate_signal(
            candidate,
            wav,
            sha256_file(wav),
            metrics,
            int(candidate["generation_seed"]),
        )

    monkeypatch.setattr(
        pipeline,
        "_inspect_existing_segment",
        lambda _row: (True, {"duration": 1.0}),
    )
    monkeypatch.setattr(pipeline, "_process_segment_candidate", synthesize_candidate)
    return seed_salts, statuses_before_synthesis


def test_short_perceptual_result_records_current_policy_exemption(tmp_path: Path) -> None:
    pipeline, chapter, row = _pipeline_with_asr_evidence(tmp_path)
    pipeline.perceptual_qa = StaticPerceptualVerifier(
        {
            "verdict": "inconclusive",
            "reason": "PERCEPTUAL_SHORT_AUDIO",
            "score": None,
            "baseline_score": None,
            "baseline_delta": None,
            "review_required": False,
            "duration_seconds": 0.5,
        }
    )

    pipeline._verify_chapter_perceptual_audio(chapter)

    fresh = pipeline.db.get_segment(int(row["id"]))
    check = pipeline.db.latest_quality_check(
        scope=QUALITY_SCOPE_SEGMENT,
        stage=SEGMENT_PERCEPTUAL_QUALITY_STAGE,
        segment_id=int(row["id"]),
    )
    assert check is not None
    assert check["verdict"] == QUALITY_VERDICT_PASS
    assert json.loads(str(check["metrics_json"]))["policy_exemption"] == "short_audio"
    assert fresh["status"] == "verified"
    assert pipeline._chapter_has_current_segment_audio_qa(int(chapter["id"])) is True
    pipeline._export_reports(incremental=True)
    report = json.loads(
        (pipeline.paths.reports / "audiobook_quality_report.json").read_text(
            encoding="utf-8"
        )
    )
    assert report["segment_perceptual_evidence"][0]["policy_exemption"] == "short_audio"


def test_ok_perceptual_result_records_separate_passing_evidence(tmp_path: Path) -> None:
    pipeline, chapter, row = _pipeline_with_asr_evidence(tmp_path)
    pipeline.perceptual_qa = StaticPerceptualVerifier(
        {
            "verdict": "ok",
            "reason": "PERCEPTUAL_WITHIN_VOICE_BASELINE",
            "score": 3.1,
            "baseline_score": 3.0,
            "baseline_delta": 0.1,
            "review_required": False,
            "duration_seconds": 1.0,
        }
    )

    pipeline._verify_chapter_perceptual_audio(chapter)

    check = pipeline.db.latest_quality_check(
        scope=QUALITY_SCOPE_SEGMENT,
        stage=SEGMENT_PERCEPTUAL_QUALITY_STAGE,
        segment_id=int(row["id"]),
    )
    assert check is not None
    assert check["verdict"] == QUALITY_VERDICT_PASS
    assert json.loads(str(check["metrics_json"]))["policy_exemption"] is None
    assert pipeline._chapter_has_current_segment_audio_qa(int(chapter["id"])) is True


def test_perceptual_qa_uses_narrator_profile_for_thought_segments(tmp_path: Path) -> None:
    pipeline, chapter, row = _pipeline_with_asr_evidence(tmp_path)
    presets = list(VOICE_PREVIEW_FILENAMES)
    narrator_preset = presets[1]
    pipeline.db.upsert_voice_profile(
        {
            "voice_key": "narrator",
            "engine": "vieneu",
            "preset_name": narrator_preset,
            "description": "narrator",
            "seed": 2,
            "pitch_semitones": -1,
            "status": "ready",
        }
    )
    with pipeline.db.connect() as conn:
        conn.execute(
            "UPDATE segments SET kind='thought' WHERE id=?",
            (int(row["id"]),),
        )
    verifier = RecordingPerceptualVerifier(
        {
            "verdict": "ok",
            "reason": "PERCEPTUAL_WITHIN_VOICE_BASELINE",
            "score": 3.0,
            "baseline_score": 3.0,
            "baseline_delta": 0.0,
            "review_required": False,
            "duration_seconds": 1.0,
        }
    )
    pipeline.perceptual_qa = verifier

    pipeline._verify_chapter_perceptual_audio(chapter)

    assert verifier.calls == [(narrator_preset, -1)]


def test_perceptual_qa_uses_unshifted_baseline_when_pitch_variant_was_skipped(
    tmp_path: Path,
) -> None:
    pipeline, chapter, row = _pipeline_with_asr_evidence(tmp_path)
    with pipeline.db.connect() as conn:
        conn.execute(
            "UPDATE voice_profiles SET pitch_semitones=2 WHERE id=?",
            (int(row["voice_profile_id"]),),
        )
        signal = json.loads(str(row["signal_json"]))
        signal["pitch_variant_skipped"] = 1.0
        conn.execute(
            "UPDATE segments SET signal_json=? WHERE id=?",
            (json.dumps(signal), int(row["id"])),
        )
    verifier = RecordingPerceptualVerifier(
        {
            "verdict": "ok",
            "reason": "PERCEPTUAL_WITHIN_VOICE_BASELINE",
            "score": 3.0,
            "baseline_score": 3.0,
            "baseline_delta": 0.0,
            "review_required": False,
            "duration_seconds": 1.0,
        }
    )
    pipeline.perceptual_qa = verifier

    pipeline._verify_chapter_perceptual_audio(chapter)

    assert verifier.calls == [(next(iter(VOICE_PREVIEW_FILENAMES)), 0)]
    check = pipeline.db.latest_quality_check(
        scope=QUALITY_SCOPE_SEGMENT,
        stage=SEGMENT_PERCEPTUAL_QUALITY_STAGE,
        segment_id=int(row["id"]),
    )
    assert check is not None
    assert json.loads(str(check["metrics_json"]))["baseline_pitch_semitones"] == 0


def test_perceptual_review_is_evidence_but_blocks_high_quality_publish(tmp_path: Path) -> None:
    pipeline, chapter, row = _pipeline_with_asr_evidence(tmp_path)
    pipeline.perceptual_qa = StaticPerceptualVerifier(
        {
            "verdict": "review",
            "reason": "PERCEPTUAL_BASELINE_DROP",
            "score": 1.9,
            "baseline_score": 3.0,
            "baseline_delta": -1.1,
            "review_required": True,
            "duration_seconds": 1.0,
        }
    )

    pipeline._verify_chapter_perceptual_audio(chapter)

    fresh = pipeline.db.get_segment(int(row["id"]))
    check = pipeline.db.latest_quality_check(
        scope=QUALITY_SCOPE_SEGMENT,
        stage=SEGMENT_PERCEPTUAL_QUALITY_STAGE,
        segment_id=int(row["id"]),
    )
    assert check is not None
    assert check["verdict"] == "inconclusive"
    assert fresh["status"] == "warning"
    assert "PERCEPTUAL_NATURALNESS_REVIEW" in str(fresh["warning_code"])
    assert pipeline._high_quality_blocking_segment_warnings([fresh])
    assert pipeline._chapter_has_current_segment_audio_qa(int(chapter["id"])) is False


def test_perceptual_review_regenerates_then_passes_in_same_chapter_cycle(
    tmp_path: Path,
    monkeypatch,
) -> None:
    pipeline, chapter, row = _pipeline_with_asr_evidence(tmp_path)
    pipeline.perceptual_qa = SequencePerceptualVerifier(
        [
            {
                "verdict": "review",
                "reason": "PERCEPTUAL_BASELINE_DROP",
                "score": 1.9,
                "baseline_score": 3.0,
                "baseline_delta": -1.1,
                "review_required": True,
                "duration_seconds": 1.0,
            },
            {
                "verdict": "ok",
                "reason": "PERCEPTUAL_WITHIN_VOICE_BASELINE",
                "score": 3.1,
                "baseline_score": 3.0,
                "baseline_delta": 0.1,
                "review_required": False,
                "duration_seconds": 1.0,
            },
        ]
    )
    verifier = PassingWhisperVerifier()
    incumbent_path = Path(str(row["wav_path"]))
    incumbent_sha256 = str(row["wav_sha256"])
    incumbent_bytes = incumbent_path.read_bytes()
    seed_salts, statuses_before_synthesis = _install_fake_repair_synthesis(
        pipeline,
        monkeypatch,
    )
    monkeypatch.setattr(pipeline.db, "chapter_is_publishable", lambda _chapter_id: False)

    pipeline._process_chapter(chapter, verifier)  # type: ignore[arg-type]

    fresh = pipeline.db.get_segment(int(row["id"]))
    check = pipeline.db.latest_quality_check(
        scope=QUALITY_SCOPE_SEGMENT,
        stage=SEGMENT_PERCEPTUAL_QUALITY_STAGE,
        segment_id=int(row["id"]),
    )
    assert seed_salts == ["asr_clarity_candidate_0_0"]
    assert statuses_before_synthesis == ["warning"]
    assert verifier.verify_calls == 2
    assert pipeline.perceptual_qa.verify_calls == 2
    assert check is not None
    assert check["verdict"] == QUALITY_VERDICT_PASS
    assert fresh["status"] == "verified"
    assert fresh["warning_code"] is None
    assert fresh["wav_sha256"] != incumbent_sha256
    assert Path(str(fresh["wav_path"])) != incumbent_path
    assert incumbent_path.read_bytes() == incumbent_bytes
    attempts = pipeline.db.segment_candidate_attempt_summary(
        int(row["id"]),
        pipeline.quality_policy_hash,
    )
    assert [attempt["state"] for attempt in attempts] == ["promoted"]
    assert attempts[0]["perceptual_result"]["verdict"] == "ok"


def test_persistent_perceptual_review_uses_bounded_repairs_then_blocks(
    tmp_path: Path,
    monkeypatch,
) -> None:
    pipeline, chapter, row = _pipeline_with_asr_evidence(tmp_path)
    pipeline.settings["perceptual_qa"]["repair_rounds"] = 2
    review = {
        "verdict": "review",
        "reason": "PERCEPTUAL_BASELINE_DROP",
        "score": 1.9,
        "baseline_score": 3.0,
        "baseline_delta": -1.1,
        "review_required": True,
        "duration_seconds": 1.0,
    }
    pipeline.perceptual_qa = SequencePerceptualVerifier([review])
    verifier = PassingWhisperVerifier()
    incumbent_path = Path(str(row["wav_path"]))
    incumbent_sha256 = str(row["wav_sha256"])
    incumbent_bytes = incumbent_path.read_bytes()
    seed_salts, statuses_before_synthesis = _install_fake_repair_synthesis(
        pipeline,
        monkeypatch,
    )

    with pytest.raises(ChapterQualityError, match="requires repair or review"):
        pipeline._process_chapter(chapter, verifier)  # type: ignore[arg-type]

    fresh = pipeline.db.get_segment(int(row["id"]))
    latest = pipeline.db.latest_quality_check(
        scope=QUALITY_SCOPE_SEGMENT,
        stage=SEGMENT_PERCEPTUAL_QUALITY_STAGE,
        segment_id=int(row["id"]),
    )
    assert seed_salts == ["asr_clarity_candidate_0_0", "asr_clarity_candidate_1_0"]
    assert statuses_before_synthesis == ["warning", "warning"]
    assert verifier.verify_calls == 4
    assert pipeline.perceptual_qa.verify_calls == 3
    assert latest is not None
    assert latest["attempt"] == 3
    assert latest["verdict"] == "inconclusive"
    assert fresh["status"] == "warning"
    assert "PERCEPTUAL_NATURALNESS_REVIEW" in str(fresh["warning_code"])
    assert fresh["wav_sha256"] == incumbent_sha256
    assert Path(str(fresh["wav_path"])) == incumbent_path
    assert incumbent_path.read_bytes() == incumbent_bytes
    attempts = pipeline.db.segment_candidate_attempt_summary(
        int(row["id"]),
        pipeline.quality_policy_hash,
    )
    assert [attempt["state"] for attempt in attempts] == ["dual_failed", "dual_failed"]
    assert all(
        attempt["perceptual_result"]["verdict"] == "review"
        for attempt in attempts
    )

    synthesis_count = len(seed_salts)
    decode_count = verifier.verify_calls
    with pytest.raises(ChapterQualityError, match="requires repair or review"):
        pipeline._process_chapter(chapter, verifier)  # type: ignore[arg-type]
    assert len(seed_salts) == synthesis_count
    assert verifier.verify_calls == decode_count
    assert pipeline.perceptual_qa.verify_calls == 4
    assert [
        attempt["state"]
        for attempt in pipeline.db.segment_candidate_attempt_summary(
            int(row["id"]),
            pipeline.quality_policy_hash,
        )
    ] == ["dual_failed", "dual_failed"]


def test_perceptual_inconclusive_does_not_trigger_regeneration(
    tmp_path: Path,
    monkeypatch,
) -> None:
    pipeline, chapter, _row = _pipeline_with_asr_evidence(tmp_path)
    pipeline.perceptual_qa = SequencePerceptualVerifier(
        [
            {
                "verdict": "inconclusive",
                "reason": "PERCEPTUAL_EVIDENCE_ERROR",
                "review_required": True,
                "duration_seconds": 1.0,
            }
        ]
    )
    verifier = PassingWhisperVerifier()
    seed_salts, _statuses = _install_fake_repair_synthesis(pipeline, monkeypatch)

    with pytest.raises(ChapterQualityError, match="requires repair or review"):
        pipeline._process_chapter(chapter, verifier)  # type: ignore[arg-type]

    assert seed_salts == []
    assert verifier.verify_calls == 0
    assert pipeline.perceptual_qa.verify_calls == 1


def test_unavailable_perceptual_model_is_contained_as_chapter_quality_failure(
    tmp_path: Path,
) -> None:
    pipeline, chapter, row = _pipeline_with_asr_evidence(tmp_path)
    pipeline.perceptual_qa = StaticPerceptualVerifier(
        PerceptualQAUnavailable("PERCEPTUAL_MODEL_LOAD_ERROR", "offline cache missing")
    )

    with pytest.raises(ChapterQualityError, match="Mandatory perceptual QA is unavailable"):
        pipeline._verify_chapter_perceptual_audio(chapter)

    check = pipeline.db.latest_quality_check(
        scope=QUALITY_SCOPE_SEGMENT,
        stage=SEGMENT_PERCEPTUAL_QUALITY_STAGE,
        segment_id=int(row["id"]),
    )
    fresh = pipeline.db.get_segment(int(row["id"]))
    assert check is not None
    assert check["verdict"] == "fail"
    assert "PERCEPTUAL_MODEL_LOAD_ERROR" in str(fresh["warning_code"])


@pytest.mark.parametrize(
    ("device", "require_gpu", "require_cpu_io"),
    [
        ("cpu", False, True),
        ("cuda:0", True, False),
    ],
)
def test_perceptual_resource_gate_matches_inference_device(
    tmp_path: Path,
    device: str,
    require_gpu: bool,
    require_cpu_io: bool,
) -> None:
    pipeline, chapter, _row = _pipeline_with_asr_evidence(tmp_path)
    pipeline.settings["perceptual_qa"]["device"] = device
    pipeline.perceptual_qa = StaticPerceptualVerifier(
        {
            "verdict": "inconclusive",
            "reason": "PERCEPTUAL_SHORT_AUDIO",
            "review_required": False,
            "duration_seconds": 0.5,
        }
    )
    gate_calls: list[dict] = []
    pipeline._resource_gate = (  # type: ignore[method-assign]
        lambda *_args, **kwargs: gate_calls.append(kwargs)
    )

    pipeline._verify_chapter_perceptual_audio(chapter)

    assert len(gate_calls) == 1
    assert gate_calls[0]["require_gpu"] is require_gpu
    assert gate_calls[0]["require_cpu_io"] is require_cpu_io


def test_cpu_resource_gate_can_run_during_gpu_only_pressure(tmp_path: Path, monkeypatch) -> None:
    pipeline, _chapter, _row = _pipeline_with_asr_evidence(tmp_path)
    decision = ResourceDecision(
        ResourceLevel.YIELD_HEAVY,
        "foreground GPU 90%",
        allow_new_gpu_batch=False,
        allow_cpu_heavy_work=True,
    )
    monkeypatch.setattr(pipeline.resources, "snapshot", lambda: object())
    monkeypatch.setattr(pipeline.resources, "decide", lambda _snapshot: decision)

    actual = BookPipeline._resource_gate(
        pipeline,
        "UTMOSv2 CPU",
        require_gpu=False,
        require_cpu_io=True,
    )

    assert actual is decision


def test_quality_report_exports_current_perceptual_evidence(tmp_path: Path) -> None:
    pipeline, chapter, row = _pipeline_with_asr_evidence(tmp_path)
    pipeline.perceptual_qa = StaticPerceptualVerifier(
        {
            "verdict": "ok",
            "reason": "PERCEPTUAL_WITHIN_VOICE_BASELINE",
            "score": 3.1,
            "baseline_score": 3.0,
            "baseline_delta": 0.1,
            "review_required": False,
            "duration_seconds": 1.0,
        }
    )
    pipeline._verify_chapter_perceptual_audio(chapter)
    _register_current_chapter_artifact(pipeline, chapter)

    pipeline._export_reports(incremental=True)

    report = json.loads(
        (pipeline.paths.reports / "audiobook_quality_report.json").read_text(
            encoding="utf-8"
        )
    )
    assert report["book"]["overall_verdict"] == QUALITY_VERDICT_PASS
    assert report["global_gates"]["segment_audio_qa_complete"] is True
    assert report["global_gates"]["all_chapters_publishable"] is True
    assert len(report["segment_perceptual_evidence"]) == 1
    evidence = report["segment_perceptual_evidence"][0]
    assert evidence["segment_id"] == int(row["id"])
    assert evidence["verdict"] == QUALITY_VERDICT_PASS
    assert evidence["current_policy_verified"] is True
    assert evidence["score"] == pytest.approx(3.1)
    assert evidence["baseline_score"] == pytest.approx(3.0)
    assert evidence["baseline_delta"] == pytest.approx(0.1)
    assert evidence["baseline_pitch_semitones"] == 0
    assert evidence["policy_exemption"] is None


def test_quality_report_does_not_pass_without_perceptual_evidence(tmp_path: Path) -> None:
    pipeline, chapter, row = _pipeline_with_asr_evidence(tmp_path)
    _register_current_chapter_artifact(pipeline, chapter)

    pipeline._export_reports(incremental=True)

    report = json.loads(
        (pipeline.paths.reports / "audiobook_quality_report.json").read_text(
            encoding="utf-8"
        )
    )
    assert report["book"]["overall_verdict"] == "review"
    assert report["book"]["passed"] == 0
    assert report["book"]["review"] == 1
    assert report["global_gates"]["segment_audio_qa_complete"] is False
    assert len(report["review_required"]["chapters"]) == 1
    assert len(report["segment_perceptual_evidence"]) == 1
    evidence = report["segment_perceptual_evidence"][0]
    assert evidence["segment_id"] == int(row["id"])
    assert evidence["evidence_present"] is False
    assert evidence["verdict"] == "missing"
    assert evidence["current_policy_verified"] is False
