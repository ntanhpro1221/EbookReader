from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

import ebook_reader.pipeline as pipeline_module
from ebook_reader.asr import (
    ASR_INCONCLUSIVE,
    ASR_LOCKED_NAME_CANONICAL_PASS,
    ASR_MISMATCH,
    ASR_PASS,
)
from ebook_reader.audio_io import AudioQualityError, ChapterQualityError, atomic_write_wav
from ebook_reader.config import build_settings
from ebook_reader.database import (
    QUALITY_SCOPE_CHAPTER,
    QUALITY_SCOPE_SEGMENT,
    SEGMENT_ASR_DECODE_QUALITY_STAGE,
    SEGMENT_AUDIO_QUALITY_STAGE,
)
from ebook_reader.models import ResourceLevel
from ebook_reader.pipeline import BookPipeline, CriticalResourceStop, unresolved_asr_is_fatal
from ebook_reader.project import create_or_open_project
from ebook_reader.quality_policy import (
    ANALYSIS_CASTING_STAGE,
    CHAPTER_QUALITY_STAGE,
    QUALITY_POLICY_VERSION,
    TEXT_SEGMENTATION_STAGE,
    quality_policy_hash,
)
from ebook_reader.resource_manager import ResourceSnapshot


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
        return 1

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
        self.synthesize_calls += 1
        self.delivery_modes.append(str(delivery_mode))
        self.seed_salts.append(str(seed_salt))
        audio = np.sin(np.linspace(0, 50, 96000, dtype=np.float32)) * 0.12
        checksum, metrics = atomic_write_wav(
            output,
            audio,
            48000,
            row["text"],
            self.settings,
            segment=row,
        )
        return checksum, metrics, 1


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

    def generation_seed(self, _row, seed_salt=""):
        self.generation_seed_salts.append(str(seed_salt))
        return len(self.calls) + len(seed_salt) + 1

    def spoken_text(self, row):
        return str(row["text"])

    def synthesize_atomic(
        self,
        row,
        _output,
        seed_salt="",
        *,
        repair_short_utterance=False,
        delivery_mode="primary",
    ):
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
        return "a" * 64, dict(outcome), len(self.calls)

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


def _short_tts_pipeline(tmp_path: Path, *, repair_rounds: int = 2):
    source = tmp_path / "001.txt"
    source.write_text("“Điên rồi!”", encoding="utf-8")
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
    chapter = db.list_chapters()[0]
    row = db.list_segments(chapter_id=int(chapter["id"]))[0]
    pipeline._resource_gate = lambda *_args, **_kwargs: None
    pipeline._progress = lambda *_args, **_kwargs: None
    pipeline._record_segment_audio_pass = lambda *_args, **_kwargs: None
    pipeline._record_segment_audio_gate = lambda *_args, **_kwargs: None
    pipeline._record_segment_asr_decode_evidence = (
        lambda *_args, **_kwargs: {"quality_check_id": 1}
    )
    return pipeline, chapter, row


def _asr_signal_pipeline(tmp_path: Path, *, repair_rounds: int):
    source = tmp_path / "001.txt"
    expected = "Một câu đủ dài để kiểm tra nội dung bằng hai lượt giải mã độc lập."
    source.write_text(expected, encoding="utf-8")
    settings = build_settings(
        overrides={
            "asr": {"repair_rounds": repair_rounds},
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


def test_clarity_locked_name_mismatch_blocks_publication(
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
    assert fresh["status"] == "failed"
    assert "ASR_LOCKED_NAME_ANCHOR_MISMATCH" in str(fresh["warning_code"])
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
    final_metrics = json.loads(str(final_check["metrics_json"]))
    assert final_metrics["locked_name_anchor_metrics"]["passed"] is False
    assert final_metrics["dual_decode_passed"] is False

    pipeline._export_reports(incremental=True)
    report = json.loads(
        (pipeline.paths.reports / "audiobook_quality_report.json").read_text(
            encoding="utf-8"
        )
    )
    evidence = report["segment_content_evidence"][0]
    assert evidence["verdict"] == "fail"
    assert evidence["failure_codes"] == ["ASR_LOCKED_NAME_ANCHOR_MISMATCH"]
    assert evidence["locked_name_anchor_metrics"]["passed"] is False
    assert evidence["decode_evidence"][-1]["reason"] == (
        "ASR_LOCKED_NAME_ANCHOR_MISMATCH"
    )


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
        "ASR_LOCKED_NAME_ANCHOR_MISMATCH",
        "ASR_MISMATCH",
    ]
    assert [
        item["locked_name_anchor_metrics"]["passed"]
        for item in final_metrics["decode_evidence"]
    ] == [False, True]


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
        "ASR_LOCKED_NAME_ANCHOR_MISMATCH",
        "TTS_ACTIVE_ENDPOINT_AT_FRAME_CEILING",
    ]
    metrics = json.loads(str(final_check["metrics_json"]))
    assert metrics["reason"] == "TTS_ACTIVE_ENDPOINT_AT_FRAME_CEILING"
    assert metrics["locked_name_anchor_metrics"]["passed"] is False
    assert metrics["decode_failure_reasons"] == [
        "ASR_LOCKED_NAME_ANCHOR_MISMATCH",
        "TTS_ACTIVE_ENDPOINT_AT_FRAME_CEILING",
    ]
    assert metrics["dual_decode_required"] is True
    assert metrics["dual_decode_passed"] is False
    assert metrics["confirmation_verdicts"] == ["mismatch", "pass"]


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
    assert pipeline.tts.seed_salts == ["asr_clarity_repair_0_0"]
    final_check = pipeline.db.latest_quality_check(
        scope=QUALITY_SCOPE_SEGMENT,
        stage=SEGMENT_AUDIO_QUALITY_STAGE,
        segment_id=int(row["id"]),
    )
    assert final_check is not None
    assert final_check["verdict"] == expected_gate
    metrics = json.loads(str(final_check["metrics_json"]))
    assert metrics["dual_decode_required"] is True
    assert metrics["dual_decode_passed"] is (expected_gate == "pass")
    assert len(metrics["decode_evidence"]) == 2
    assert {item["decode_mode"] for item in metrics["decode_evidence"]} == {
        "beam5",
        "greedy",
    }
    assert {item["delivery_mode"] for item in metrics["decode_evidence"]} == {
        "clarity"
    }


def test_resume_of_clarity_candidate_still_requires_both_decodes(
    tmp_path: Path,
) -> None:
    pipeline, chapter, row, expected = _asr_signal_pipeline(tmp_path, repair_rounds=1)
    signal = json.loads(str(row["signal_json"]))
    signal.update(
        {
            "tts_delivery_mode": "clarity",
            "asr_clarity_repair_round": 0,
        }
    )
    pipeline.db.mark_signal_passed(
        int(row["id"]),
        wav_path=Path(str(row["wav_path"])),
        wav_sha256=str(row["wav_sha256"]),
        duration=float(row["wav_duration"]),
        signal=signal,
        generation_seed=int(row["generation_seed"] or 1),
    )

    class CrashAfterBeamVerifier:
        calls = 0

        def unload(self) -> None:
            return None

        def can_verify_repeated_short(self, _text: str) -> bool:
            return False

        def verify(self, _text: str, _wav: Path, *, confirmation: bool = False):
            self.calls += 1
            if self.calls == 1:
                return _asr_result(ASR_PASS, expected, similarity=1.0, wer=0.0)
            raise RuntimeError("simulated crash between clarity decodes")

    with pytest.raises(RuntimeError, match="simulated crash"):
        pipeline._verify_chapter_audio(chapter, CrashAfterBeamVerifier())
    assert pipeline.db.get_segment(int(row["id"]))["status"] == "signal_passed"

    scripted_results = [
        _asr_result(ASR_PASS, expected, similarity=1.0, wer=0.0),
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
    assert pipeline.tts.synthesize_calls == 0
    final_check = pipeline.db.latest_quality_check(
        scope=QUALITY_SCOPE_SEGMENT,
        stage=SEGMENT_AUDIO_QUALITY_STAGE,
        segment_id=int(row["id"]),
    )
    assert final_check is not None
    metrics = json.loads(str(final_check["metrics_json"]))
    assert metrics["dual_decode_required"] is True
    assert metrics["dual_decode_passed"] is False
    assert len(metrics["decode_evidence"]) == 2


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
    rows = [
        {
            "id": 1,
            "stable_id": "c1s1",
            "warning_code": "TTS_SPLIT_RECOVERY|TTS_GENERATION_CEILING_REACHED",
        },
        {
            "id": 2,
            "stable_id": "c1s2",
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
    pipeline.tts = scripted

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


@pytest.mark.parametrize("initial_verdict", [ASR_PASS, ASR_MISMATCH, ASR_INCONCLUSIVE])
def test_active_ceiling_endpoint_repairs_after_any_whisper_verdict_and_clears_cap(
    tmp_path: Path,
    initial_verdict: str,
) -> None:
    pipeline, chapter, row = _short_tts_pipeline(tmp_path)
    initial = pipeline._chunk_path(row)
    pipeline.db.mark_signal_passed(
        int(row["id"]),
        wav_path=initial,
        wav_sha256="b" * 64,
        duration=1.92,
        signal={
            "duration": 1.92,
            "generation_ceiling_hit": 1.0,
            "generation_endpoint_active": 1.0,
            "trailing_rms": 0.05,
        },
    )
    pipeline.db.set_segment_warning_code(int(row["id"]), "TTS_GENERATION_CEILING_REACHED")
    scripted = ScriptedShortTTS([{"duration": 0.88, "trailing_rms": 0.0}])
    verifier = PassingShortVerifier(initial_verdict)
    pipeline.tts = scripted

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
    initial = pipeline._chunk_path(row)
    endpoint_metrics = {
        "duration": 0.96,
        "generation_ceiling_hit": 1.0,
        "generation_endpoint_active": 1.0,
        "trailing_rms": 0.05,
    }
    pipeline.db.mark_signal_passed(
        int(row["id"]),
        wav_path=initial,
        wav_sha256="c" * 64,
        duration=1.92,
        signal={**endpoint_metrics, "duration": 1.92},
    )
    pipeline.db.set_segment_warning_code(int(row["id"]), "TTS_GENERATION_CEILING_REACHED")
    scripted = ScriptedShortTTS([endpoint_metrics, endpoint_metrics])
    verifier = PassingShortVerifier()
    pipeline.tts = scripted

    pipeline._verify_chapter_audio(chapter, verifier)

    updated = pipeline.db.get_segment(int(row["id"]))
    assert len(scripted.calls) == 2
    assert verifier.calls == 5
    assert [call["generation_frame_cap"] for call in scripted.calls] == [12, 12]
    assert [call["delivery_mode"] for call in scripted.calls] == ["clarity", "clarity"]
    assert updated["status"] == "failed"
    assert updated["generation_frame_cap"] == 12
    assert "Active endpoint remained" in str(updated["error"])


def test_short_tts_failure_does_not_attempt_semantic_split(
    tmp_path: Path,
    monkeypatch,
) -> None:
    pipeline, chapter, row = _short_tts_pipeline(tmp_path)
    scripted = ScriptedShortTTS(
        [AudioQualityError("generation failed") for _attempt in range(4)]
    )
    pipeline.tts = scripted
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
    split_calls: list[str] = []

    def fake_split(item, _output, **_kwargs):
        split_calls.append(str(item["stable_id"]))

    pipeline.tts = scripted
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
    assert split_calls == [str(row["stable_id"])]
    assert updated["status"] == "signal_passed"
    assert updated["warning_code"] == "TTS_SPLIT_RECOVERY"


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

    pipeline.tts = scripted
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

    pipeline.tts = scripted
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
    pipeline.tts = scripted
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
    assert metrics["reason"] == "ASR_CLARITY_TTS_REGENERATION_FAILED"
    assert "clarity inference failed" in metrics["tts_error"]

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
    assert evidence["failure_codes"] == [
        "ASR_MISMATCH",
        "ASR_CLARITY_TTS_REGENERATION_FAILED",
    ]


def test_crash_before_final_asr_status_keeps_retained_wav_budget_exhausted(
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
    pipeline.tts = scripted
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

    original_mark_asr_result = pipeline.db.mark_asr_result
    monkeypatch.setattr(
        pipeline.db,
        "mark_asr_result",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            RuntimeError("simulated crash after final gate")
        ),
    )
    with pytest.raises(RuntimeError, match="simulated crash after final gate"):
        pipeline._verify_chapter_audio(chapter, MismatchVerifier())

    crashed = pipeline.db.get_segment(int(row["id"]))
    final_check = pipeline.db.latest_quality_check(
        scope=QUALITY_SCOPE_SEGMENT,
        stage=SEGMENT_AUDIO_QUALITY_STAGE,
        segment_id=int(row["id"]),
    )
    assert final_check is not None
    assert final_check["verdict"] == "fail"
    assert final_check["artifact_sha256"] == row["wav_sha256"]
    assert crashed["status"] == "failed"
    assert crashed["generation_delivery_mode"] == "clarity"
    assert crashed["generation_repair_round"] == 0
    calls_before_resume = len(scripted.calls)

    monkeypatch.setattr(pipeline.db, "mark_asr_result", original_mark_asr_result)
    pipeline._verify_chapter_audio = lambda *_args, **_kwargs: (_ for _ in ()).throw(
        RuntimeError("stop after synthesis stage")
    )
    with pytest.raises(RuntimeError, match="stop after synthesis stage"):
        pipeline._process_chapter(chapter, SimpleNamespace(unload=lambda: None))

    assert len(scripted.calls) == calls_before_resume
    assert pipeline.db.get_segment(int(row["id"]))["status"] == "failed"


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
        passed = verify_calls_by_path[path_key] > 2
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
    assert int(segments[0]["generation_seed"]) == 1
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
    assert any(label.startswith("Sửa audio chapter") for label in progress_labels)
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


def test_resume_rejects_segments_from_a_different_parser_fingerprint(tmp_path: Path) -> None:
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

    with pytest.raises(RuntimeError, match="Text segmentation implementation changed"):
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
