from __future__ import annotations

import hashlib
import inspect
import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Callable

import numpy as np
import soundfile as sf

from .analysis import AnalysisRequestStopped, OllamaBookAnalyzer
from .asr import (
    ASR_INCONCLUSIVE,
    ASR_LOCKED_NAME_ANCHOR_MISMATCH,
    ASR_MISMATCH,
    ASR_PASS,
    LOCKED_NAME_ANCHOR_METRICS_KEY,
    LOCKED_NAME_ANCHOR_METRICS_VERSION,
    SHORT_CONTEXT_REPEAT_COUNT,
    WhisperVerifier,
    adjudicate_collapsed_repeated_short,
    adjudicate_locked_name_anchors,
)
from .asr_contract import (
    COLLAPSED_SHORT_CONTEXT_EFFECTIVE_REPEAT_COUNT,
    COLLAPSED_SHORT_CONTEXT_MODE,
)
from .audio_io import (
    AudioQualityError,
    ChapterQualityError,
    assemble_chapter_atomic_with_metrics,
    export_json_atomic,
    inspect_wav,
    is_short_utterance,
    merge_wav_parts_atomic,
    tempo_stretch_wav_atomic,
    verify_mp3,
    write_playlist_atomic,
)
from .audio_transform_contract import (
    POSTPROCESS_PROFILE_FIELD,
    POSTPROCESS_PROFILE_NONE,
    POSTPROCESS_PROFILE_TEMPO,
    POSTPROCESS_PROVENANCE_FIELDS,
    POSTPROCESS_SOURCE_CANDIDATE_ID_FIELD,
    POSTPROCESS_SOURCE_SHA256_FIELD,
)
from .asr_contract import (
    ASR_LOCKED_NAME_ANCHOR_REVIEW,
    LOCKED_NAME_ANCHOR_UNMATCHED_STATUSES,
)
from .character_registry import build_registry_and_cast
from .database import (
    GENERATION_STRATEGY_DIRECT,
    GENERATION_STRATEGY_SPLIT,
    QUALITY_SCOPE_CHAPTER,
    QUALITY_SCOPE_SEGMENT,
    QUALITY_VERDICT_PASS,
    SEGMENT_ASR_DECODE_QUALITY_STAGE,
    SEGMENT_AUDIO_QUALITY_STAGE,
    SEGMENT_CANDIDATE_DUAL_FAILED,
    SEGMENT_CANDIDATE_DUAL_PASSED,
    SEGMENT_CANDIDATE_GENERATING,
    SEGMENT_CANDIDATE_PROMOTED,
    SEGMENT_PERCEPTUAL_QUALITY_STAGE,
    ProjectDB,
    segment_candidate_split_seed_salt,
)
from .io_utils import sha256_file
from .models import BookStatus, ChapterStatus, ProjectPaths, ResourceLevel, SegmentStatus
from .notifier import WindowsNotifier
from .perceptual_qa import (
    PERCEPTUAL_INCONCLUSIVE,
    PERCEPTUAL_OK,
    PERCEPTUAL_REVIEW,
    PerceptualQAUnavailable,
    UTMOSNaturalnessVerifier,
)
from .perceptual_contract import (
    NATURALNESS_IMPROVEMENT_REQUIREMENT,
    NATURALNESS_REPAIR_ACTION,
    PERCEPTUAL_NATURALNESS_REVIEW_CODE,
    PERCEPTUAL_SHORT_AUDIO_REASON,
    STANDARD_CANDIDATE_GATE_REQUIREMENT,
)
from .text_processing import (
    CLAUSE_SPLIT_STRATEGY,
    SENTENCE_SPLIT_STRATEGY,
    SPLIT_MAX_CHARS_FIELD,
    SPLIT_STRATEGY_FIELD,
    has_spoken_content,
    is_standalone_ha_gasp,
    load_and_segment_chapter,
    split_text_for_strategy,
)
from .recovery import recover_project
from .resource_manager import AdaptiveResourceManager
from .quality_policy import (
    ANALYSIS_CASTING_STAGE,
    CHAPTER_QUALITY_STAGE,
    QUALITY_POLICY_VERSION,
    TEXT_SEGMENTATION_STAGE,
    build_quality_policy,
    quality_policy_hash,
)
from .tts import (
    DELIVERY_CLARITY,
    apply_pitch_variant,
    DELIVERY_PRIMARY,
    GENERATION_CEILING_METRIC,
    GENERATION_CEILING_WARNING,
    GENERATION_ENDPOINT_ACTIVE_METRIC,
    PRONUNCIATION_DELIVERY_LOCKED,
    PRONUNCIATION_DELIVERY_SOURCE,
    TTSCoordinator,
    is_fatal_tts_error,
    short_utterance_repair_frame_cap,
)
from .tts_contract import (
    HA_VOCALIZATION_MAX_NEW_FRAMES,
    HA_VOCALIZATION_PROVENANCE_FIELDS,
)


CRITICAL_RAM_RECOVERY_WAIT_SECONDS = 2.0
HIGH_QUALITY_ALLOWED_SEGMENT_WARNINGS = frozenset(
    {
        "TTS_SPLIT_RECOVERY",
        GENERATION_CEILING_WARNING,
        # A locked-name anchor reports review evidence, not proof of a bad take: Whisper
        # writes a correctly pronounced Vietnamese name back in Latin spelling. Letting
        # that block the chapter would undo the segment-level decision entirely - the
        # segment publishes and the chapter still refuses it. The name is listed in the
        # quality report for a human to listen to.
        ASR_LOCKED_NAME_ANCHOR_REVIEW,
    }
)
CHAPTER_REVIEW_STATUS = "warning"
QUALITY_VERDICT_FAIL = "fail"
CHAPTER_AUDIO_PIPELINE_FAILURE_CODE = "CHAPTER_AUDIO_PIPELINE_FAILED"
CHAPTER_QUALITY_REPAIR_ACTION = "retry_after_quality_or_policy_change"
ACTIVE_CEILING_ENDPOINT_REPAIR_REASON = "TTS_ACTIVE_ENDPOINT_AT_FRAME_CEILING"
ASR_CLARITY_REPAIR_ROUND_METRIC = "asr_clarity_repair_round"
PITCH_VARIANT_SKIPPED_WARNING = "TTS_PITCH_VARIANT_SKIPPED"
QUALITY_VERDICT_REPAIR = "repair"
SEGMENT_CANDIDATE_DIRECTORY = "candidates"
TTS_SIGNAL_PROVENANCE_FIELDS = (
    "tts_delivery_mode",
    ASR_CLARITY_REPAIR_ROUND_METRIC,
    "spoken_text_sha256",
    "pronunciation_delivery_variant",
    "voice_profile_id",
    "pitch_semitones",
    "effective_pitch_semitones",
    "pitch_variant_skipped",
    "pitch_variant_mixed",
    GENERATION_CEILING_METRIC,
    GENERATION_ENDPOINT_ACTIVE_METRIC,
    "split_checkpoint_seed",
    "split_seed_salt_prefix",
    SPLIT_STRATEGY_FIELD,
    SPLIT_MAX_CHARS_FIELD,
    "split_parts",
    *HA_VOCALIZATION_PROVENANCE_FIELDS,
)
SEGMENTATION_CHECKPOINT_FIELDS = (
    "stable_id",
    "seq",
    "paragraph_index",
    "break_ms",
    "text",
    "text_sha256",
    "kind_hint",
)


def unresolved_asr_is_fatal(result: dict[str, Any], failure_policy: str) -> bool:
    verdict = str(result.get("verdict", ""))
    if verdict:
        return verdict != ASR_PASS
    return not bool(result.get("passed", False)) or bool(result.get("severe", False)) or failure_policy == "fail"


def _asr_verdict(result: dict[str, Any]) -> str:
    verdict = str(result.get("verdict", ""))
    if verdict in {ASR_PASS, ASR_MISMATCH, ASR_INCONCLUSIVE}:
        return verdict
    if bool(result.get("passed", False)):
        return ASR_PASS
    return ASR_MISMATCH if str(result.get("reason", "")) == "ASR_MISMATCH" else ASR_INCONCLUSIVE


def _candidate_budget_exhausted_on_perceptual_review(
    attempts: list[dict[str, Any]],
) -> bool:
    for attempt in attempts:
        beam_result = attempt.get("beam_result")
        greedy_result = attempt.get("greedy_result")
        perceptual_result = attempt.get("perceptual_result")
        if (
            str(attempt.get("state") or "") == SEGMENT_CANDIDATE_DUAL_FAILED
            and isinstance(beam_result, dict)
            and isinstance(greedy_result, dict)
            and _asr_verdict(beam_result) == ASR_PASS
            and _asr_verdict(greedy_result) == ASR_PASS
            and isinstance(perceptual_result, dict)
            and str(perceptual_result.get("verdict") or "") == PERCEPTUAL_REVIEW
            and perceptual_result.get("review_required") is True
        ):
            return True
    return False


class PipelineStopped(RuntimeError):
    pass


class CriticalResourceStop(RuntimeError):
    pass


class BookPipeline:
    def __init__(
        self,
        *,
        paths: ProjectPaths,
        db: ProjectDB,
        settings: dict[str, Any],
        pause_requested: Callable[[], bool],
        stop_requested: Callable[[], bool],
        emit: Callable[[str, dict[str, Any]], None],
        resource_updates: Callable[[], dict[str, Any] | None] | None = None,
    ) -> None:
        self.paths = paths
        self.db = db
        self.settings = settings
        self.pause_requested = pause_requested
        self.stop_requested = stop_requested
        self.emit = emit
        self.resource_updates = resource_updates
        self.resources = AdaptiveResourceManager(settings, paths.root)
        self.notifier = WindowsNotifier()
        self.tts = TTSCoordinator(settings, db, self.log)
        self.perceptual_qa = UTMOSNaturalnessVerifier(settings, self.log)
        self._last_resource_level: ResourceLevel | None = None
        self._completed_noop = False
        self._last_tts_failure_signature: str | None = None
        self._tts_failure_streak = 0
        self.quality_policy = build_quality_policy(settings)
        self.quality_policy_hash = quality_policy_hash(self.quality_policy)

    def log(self, message: str) -> None:
        self.db.event("info", "LOG", message)
        self.emit("log", {"text": message})

    def _reset_tts_failure_streak(self) -> None:
        self._last_tts_failure_signature = None
        self._tts_failure_streak = 0

    def _record_tts_failure(self, error: str) -> int:
        signature = " ".join(error.casefold().split())[:240]
        if signature == self._last_tts_failure_signature:
            self._tts_failure_streak += 1
        else:
            self._last_tts_failure_signature = signature
            self._tts_failure_streak = 1
        return self._tts_failure_streak

    def _state(self, state: str, text: str) -> None:
        self.emit("state", {"state": state, "text": text})

    def _progress(
        self,
        label: str,
        done: int | None = None,
        total: int | None = None,
    ) -> None:
        self.emit("work_progress", {"label": label, "done": done, "total": total})

    def _wait_pause_or_stop(self) -> None:
        announced = False
        resume_status: str | None = None
        resume_stage: str | None = None
        while self.pause_requested():
            if self.stop_requested():
                raise PipelineStopped("Stop requested")
            if not announced:
                book = self.db.book()
                resume_status = str(book["status"])
                resume_stage = str(book["stage"])
                self.db.update_book(status=BookStatus.PAUSED.value, stage="paused")
                self._state("paused", "Đã tạm dừng.")
                announced = True
            time.sleep(0.25)
        if announced:
            self.db.update_book(status=resume_status, stage=resume_stage)
            self._state("running", "Đang tiếp tục từ checkpoint.")
        if self.stop_requested():
            raise PipelineStopped("Stop requested")

    def _resource_gate(
        self,
        checkpoint: str,
        *,
        keep_engine: str | None = None,
        release_active: Callable[[], None] | None = None,
        require_gpu: bool = True,
        require_cpu_io: bool = False,
    ):
        while True:
            self._wait_pause_or_stop()
            if self.resource_updates is not None:
                updated_resources = self.resource_updates()
                if updated_resources is not None:
                    self.settings["resources"] = updated_resources
                    self.resources.update_settings(updated_resources)
                    self.log(
                        "Đã áp dụng setting tài nguyên global: "
                        f"mode={updated_resources['mode']}, "
                        f"GPU tối đa={updated_resources['max_gpu_temp_c']}°C."
                    )
            snapshot = self.resources.snapshot()
            decision = self.resources.decide(snapshot)
            if decision.critical and self.resources.is_ram_only_critical(snapshot):
                before_ram_gb = snapshot.free_ram_gb
                self.log(
                    f"RAM khả dụng chỉ còn {before_ram_gb:.1f} GB; "
                    "đang giải phóng model và cache trước khi quyết định dừng."
                )
                if release_active is not None:
                    try:
                        release_active()
                    except Exception as exc:  # noqa: BLE001
                        self.log(f"Thu hồi model đang hoạt động gặp lỗi: {exc}")
                try:
                    self.tts.unload_all()
                except Exception as exc:  # noqa: BLE001
                    self.log(f"Thu hồi model TTS/cache gặp lỗi: {exc}")
                time.sleep(CRITICAL_RAM_RECOVERY_WAIT_SECONDS)
                snapshot = self.resources.snapshot(force=True)
                decision = self.resources.decide(snapshot)
                self.log(
                    f"Đã đo lại RAM sau thu hồi: {before_ram_gb:.1f} → "
                    f"{snapshot.free_ram_gb:.1f} GB khả dụng."
                )
            if decision.level != self._last_resource_level:
                self._last_resource_level = decision.level
                self.emit(
                    "resource",
                    {
                        "level": decision.level.value,
                        "reason": decision.reason,
                        "gpu_scale": decision.gpu_batch_scale,
                    },
                )
                self.log(f"Resource mode: {decision.level.value} — {decision.reason}")
                if "disk free" in decision.reason:
                    self.notifier.notify(
                        "Ebook Reader đang chờ tài nguyên",
                        f"{decision.reason}. Pipeline đã dừng cấp tác vụ mới tại checkpoint an toàn.",
                        project_path=self.paths.root,
                    )
            if decision.critical:
                book = self.db.book()
                self.db.update_book(status=BookStatus.STOPPED.value, stage="critical_stop", error=decision.reason)
                self.db.event(
                    "critical",
                    "CRITICAL_RESOURCE_STOP",
                    decision.reason,
                    {"checkpoint": checkpoint},
                )
                if self.settings["safety"].get("notify_on_critical_stop", True):
                    self.notifier.critical_stop(
                        str(book["title"]), decision.reason, self.paths.root, checkpoint
                    )
                raise CriticalResourceStop(decision.reason)
            if decision.unload_idle_models:
                active_resource_blocked = (
                    (require_gpu and not decision.allow_new_gpu_batch)
                    or (require_cpu_io and not decision.allow_cpu_heavy_work)
                )
                if active_resource_blocked and release_active is not None:
                    release_active()
                elif decision.allow_new_gpu_batch:
                    self.tts.unload_idle_models(keep_engine=keep_engine)
                else:
                    # At this point the previous inference already committed. Release even the active
                    # engine so a foreground renderer/game can reclaim VRAM without killing CUDA mid-kernel.
                    self.tts.unload_all()
            gpu_ok = (not require_gpu) or decision.allow_new_gpu_batch
            cpu_ok = (not require_cpu_io) or decision.allow_cpu_heavy_work
            if gpu_ok and cpu_ok:
                return decision
            time.sleep(2.0)

    def _ensure_segments(self) -> None:
        max_chars = int(self.settings["tts"]["max_segment_chars"])
        chapters = self.db.list_chapters()
        self._progress("Chuẩn bị và chia văn bản", 0, len(chapters))
        for index, chapter in enumerate(chapters, 1):
            self._validate_chapter_source(chapter)
            if int(chapter["total_segments"]) > 0:
                self._progress("Chuẩn bị và chia văn bản", index, len(chapters))
                continue
            self._wait_pause_or_stop()
            rows = load_and_segment_chapter(dict(chapter), max_chars=max_chars)
            if not rows:
                raise RuntimeError(f"Chapter has no readable content: {chapter['input_path']}")
            self.db.replace_chapter_segments(int(chapter["id"]), rows)
            self.log(f"Đã chia {chapter['title']} thành {len(rows):,} segment và checkpoint vào SQLite.")
            self._progress("Chuẩn bị và chia văn bản", index, len(chapters))

    def _chapter_delivery_wavs(
        self,
        chapter: Any,
        rows: list[Any],
    ) -> list[tuple[Path, int]]:
        """Apply each segment's locked voice variant on the way into the chapter.

        The verified segment WAV is never touched. Every gate graded the raw take, and
        the variant is deterministic post-processing that cannot change a single word, so
        grading its output would only measure the transform: the WORLD round trip costs
        about 0.27 MOS and 0.06 WER flat, whether it shifts by six semitones or by
        nothing at all. Keeping it out here is what stops that tax from failing segments
        whose audio is fine.
        """
        profiles = {
            int(profile["id"]): profile for profile in self.db.list_voice_profiles()
        }
        delivery_root = self.paths.work / "delivery" / f"chapter_{int(chapter['chapter_index']):05d}"
        rendered: list[tuple[Path, int]] = []
        transformed = 0
        for row in rows:
            source = Path(str(row["wav_path"]))
            break_ms = int(row["break_ms"])
            profile = profiles.get(int(row["voice_profile_id"] or 0))
            pitch_steps = int(profile["pitch_semitones"]) if profile is not None else 0
            formant_ratio = (
                float(profile["formant_ratio"]) if profile is not None else 1.0
            )
            if pitch_steps == 0 and abs(formant_ratio - 1.0) <= 1e-6:
                rendered.append((source, break_ms))
                continue
            delivery_root.mkdir(parents=True, exist_ok=True)
            destination = delivery_root / f"{int(row['seq']):07d}.wav"
            audio, sample_rate = sf.read(source, dtype="float32", always_2d=False)
            shifted = apply_pitch_variant(
                np.asarray(audio, dtype=np.float32).reshape(-1),
                int(sample_rate),
                pitch_steps,
                formant_ratio=formant_ratio,
            )
            temp = destination.with_suffix(".part.wav")
            sf.write(temp, shifted, int(sample_rate), subtype="PCM_16")
            os.replace(temp, destination)
            rendered.append((destination, break_ms))
            transformed += 1
        if transformed:
            self.log(
                f"Áp âm sắc nhân vật cho {transformed}/{len(rows)} segment của chapter "
                f"{chapter['chapter_index']} trước khi ghép."
            )
        return rendered

    def _validate_chapter_source(self, chapter: Any) -> None:
        if not self.settings["safety"].get("stop_book_on_source_change", True):
            return
        source = Path(str(chapter["input_path"]))
        if not source.is_file():
            raise RuntimeError(f"Source chapter is missing: {source}")
        if source.stat().st_size != int(chapter["input_size"]):
            raise RuntimeError(f"Source chapter size changed during the job: {source}")
        if sha256_file(source) != str(chapter["input_sha256"]):
            raise RuntimeError(f"Source chapter content changed during the job: {source}")

    def _recover(self) -> None:
        self._validate_resume_stage_fingerprints()
        self.db.set_current_quality_policy(
            policy_hash=self.quality_policy_hash,
            policy_version=QUALITY_POLICY_VERSION,
            policy=self.quality_policy,
        )
        report = recover_project(self.paths, self.db, self.settings)
        self._completed_noop = report.completed_verified
        if (
            report.reset_in_progress
            or report.reset_missing_or_corrupt
            or report.removed_part_files
        ):
            self.log(
                "Recovery: "
                f"giữ {report.recovered_verified} đoạn; "
                f"reset {report.reset_in_progress + report.reset_missing_or_corrupt} đoạn; "
                f"xóa {report.removed_part_files} file tạm."
            )
            if self.settings["safety"].get("notify_on_recovery", True):
                self.notifier.recovery_notice(
                    str(self.db.book()["title"]),
                    self.paths.root,
                    report.recovered_verified,
                    report.reset_in_progress + report.reset_missing_or_corrupt,
                )

    def _validate_resume_stage_fingerprints(self) -> None:
        rows = self.db.list_segments()
        if not rows:
            return
        previous = self.db.current_quality_policy()
        if previous is None:
            raise RuntimeError(
                "Existing segments have no parser/casting fingerprint; create a clean project "
                "instead of resuming checkpoints produced by an unknown implementation"
            )
        try:
            previous_policy = json.loads(str(previous["policy_json"]))
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                "Existing quality policy is unreadable; create a clean project before resuming"
            ) from exc
        previous_stages = (
            previous_policy.get("stage_fingerprints", {})
            if isinstance(previous_policy, dict)
            else {}
        )
        current_stages = self.quality_policy.get("stage_fingerprints", {})
        if not isinstance(previous_stages, dict) or not isinstance(current_stages, dict):
            raise RuntimeError(
                "Existing parser/casting fingerprints are invalid; create a clean project before resuming"
            )
        if previous_stages.get(TEXT_SEGMENTATION_STAGE) != current_stages.get(
            TEXT_SEGMENTATION_STAGE
        ):
            mismatch = self._segmentation_checkpoint_mismatch()
            if mismatch is not None:
                raise RuntimeError(
                    "Text segmentation implementation changed after segments were "
                    "checkpointed and the current parser does not reproduce the "
                    f"checkpoint exactly: {mismatch}"
                )
            self.log(
                "Text segmentation fingerprint changed, but the current parser "
                "reproduced every checkpointed segment exactly; safe resume allowed."
            )
        analysis_candidates_exist = getattr(self.db, "has_analysis_candidates", None)
        analysis_started = (
            self.db.casting_is_finalized()
            or (
                callable(analysis_candidates_exist)
                and bool(analysis_candidates_exist())
            )
            or any(str(row["status"]) != SegmentStatus.PENDING.value for row in rows)
        )
        if analysis_started and previous_stages.get(ANALYSIS_CASTING_STAGE) != current_stages.get(
            ANALYSIS_CASTING_STAGE
        ):
            raise RuntimeError(
                "Analysis/casting implementation changed after analysis started; create a clean project "
                "so stale speaker and voice assignments cannot be republished"
            )

    def _segmentation_checkpoint_mismatch(self) -> str | None:
        max_chars = int(self.settings["tts"]["max_segment_chars"])
        for chapter in self.db.list_chapters():
            expected_rows = load_and_segment_chapter(
                dict(chapter),
                max_chars=max_chars,
            )
            checkpoint_rows = self.db.list_segments(chapter_id=int(chapter["id"]))
            if len(expected_rows) != len(checkpoint_rows):
                return (
                    f"chapter {int(chapter['chapter_index'])} has "
                    f"{len(checkpoint_rows)} checkpointed segments instead of "
                    f"{len(expected_rows)}"
                )
            for expected, checkpoint in zip(expected_rows, checkpoint_rows):
                for field in SEGMENTATION_CHECKPOINT_FIELDS:
                    if expected[field] != checkpoint[field]:
                        return (
                            f"chapter {int(chapter['chapter_index'])} segment "
                            f"{int(checkpoint['seq'])} field {field} differs"
                        )
        return None

    def prepare_recovery(self) -> bool:
        self._recover()
        return self._completed_noop

    def run(self, *, recovery_already_run: bool = False) -> None:
        if not recovery_already_run:
            self._recover()
        if self._completed_noop:
            self._safe_export_reports(incremental=False)
            self._state("completed", "Project đã hoàn tất; artifact đã được xác minh.")
            return
        self.db.begin_run_generation()
        self._ensure_segments()
        self.db.update_book(status=BookStatus.ANALYZING.value, stage="full_book_analysis")
        self._state("running", "Đang phân tích toàn bộ book trước khi tạo audio.")

        analyzer = OllamaBookAnalyzer(
            self.settings,
            self.db,
            self.log,
            quality_policy_hash=self.quality_policy_hash,
        )
        try:
            analyzer.analyze_all(
                self.stop_requested,
                progress=lambda done, total: self.emit(
                    "analysis_progress", {"done": done, "total": total}
                ),
                before_batch=lambda index: self._resource_gate(
                    f"analysis batch {index}", release_active=analyzer.release_model
                ),
            )
            self._wait_pause_or_stop()
            if self.db.casting_is_finalized():
                self.log("Voice casting đã khóa từ lần chạy trước; giữ nguyên mapping khi resume.")
            else:
                self._state("running", "Đang khóa nhân vật theo tên và phân vai.")
                self._state("running", "Đang chuẩn hóa cách đọc tên tiếng Anh.")
                analyzer.reconcile_name_pronunciations(
                    before_batch=lambda index: self._resource_gate(
                        f"name pronunciation batch {index}",
                        release_active=analyzer.release_model,
                    ),
                    stop_requested=self.stop_requested,
                )
                build_registry_and_cast(self.db, self.settings, self.log)
                self.db.finalize_casting()
            self.db.update_book(status=BookStatus.CASTING.value, stage="voice_cast_locked")
        except AnalysisRequestStopped as exc:
            raise PipelineStopped("Stop requested during Ollama analysis") from exc
        finally:
            analyzer.unload()
            self._safe_export_reports(incremental=True)

        self._state("running", "Đang xác minh các giọng VieNeu đã khóa.")
        self._resource_gate("xác minh preset VieNeu", keep_engine="vieneu")
        self.tts.prepare_voice_presets()
        self.tts.unload_idle_models()
        self.db.update_book(status=BookStatus.SYNTHESIZING.value, stage="chapter_synthesis")

        verifier = WhisperVerifier(self.settings, self.log)
        try:
            self._process_all_chapters(verifier)
        finally:
            verifier.unload()
            self.perceptual_qa.unload()
            self.tts.unload_all()
            self._safe_export_reports(incremental=True)

        self._finalize_book()
        self._progress("Xuất báo cáo", 0, 1)
        self._export_reports()
        self._progress("Xuất báo cáo", 1, 1)

    def _process_all_chapters(self, verifier: WhisperVerifier) -> None:
        chapters = self.db.list_chapters()
        for chapter_no, chapter in enumerate(chapters, 1):
            self._wait_pause_or_stop()
            try:
                self._process_chapter(chapter, verifier)
            except AudioQualityError as exc:
                self._record_chapter_quality_failure(chapter, exc)
            finally:
                self.perceptual_qa.unload()
            self.emit(
                "chapter_progress",
                {"done": chapter_no, "total": len(chapters), "chapter_id": int(chapter["id"])},
            )
            self._safe_export_reports(incremental=True)

    def _next_chapter_quality_attempt(self, chapter_id: int) -> int:
        latest = self.db.latest_quality_check(
            scope=QUALITY_SCOPE_CHAPTER,
            stage=CHAPTER_QUALITY_STAGE,
            chapter_id=chapter_id,
        )
        return int(latest["attempt"]) + 1 if latest is not None else 1

    def _next_segment_quality_attempt(
        self,
        segment_id: int,
        stage: str = SEGMENT_AUDIO_QUALITY_STAGE,
    ) -> int:
        latest = self.db.latest_quality_check(
            scope=QUALITY_SCOPE_SEGMENT,
            stage=stage,
            segment_id=segment_id,
        )
        return int(latest["attempt"]) + 1 if latest is not None else 1

    def _record_segment_audio_pass(
        self,
        item: dict[str, Any],
        result: dict[str, Any],
        *,
        confirmation: bool,
        decode_evidence: list[dict[str, Any]] | None = None,
    ) -> int:
        return self._record_segment_audio_gate(
            item,
            result,
            verdict=QUALITY_VERDICT_PASS,
            confirmation=confirmation,
            decode_evidence=decode_evidence,
        )

    def _validated_segment_wav_identity(
        self,
        item: dict[str, Any],
    ) -> tuple[Path, str]:
        wav_path = Path(str(item["wav_path"] or ""))
        artifact_sha256 = str(item["wav_sha256"] or "").strip()
        if (
            not artifact_sha256
            or not wav_path.is_file()
            or sha256_file(wav_path) != artifact_sha256
        ):
            raise AudioQualityError(
                f"WAV changed before the ASR quality checkpoint for {item['stable_id']}"
            )
        return wav_path, artifact_sha256

    @staticmethod
    def _segment_signal_provenance(item: dict[str, Any]) -> dict[str, Any]:
        try:
            decoded = json.loads(str(item.get("signal_json") or "{}"))
        except (TypeError, json.JSONDecodeError):
            return {}
        if not isinstance(decoded, dict):
            return {}
        ProjectDB._require_vocalization_provenance(
            decoded,
            required=is_standalone_ha_gasp(str(item.get("text") or "")),
        )
        return decoded

    @staticmethod
    def _signal_warning_codes(
        signal: dict[str, Any],
        *,
        split_recovery: bool = False,
    ) -> tuple[str, ...]:
        warnings: list[str] = []
        if split_recovery:
            warnings.append("TTS_SPLIT_RECOVERY")
        if signal.get("pace_outlier"):
            warnings.append("TTS_PACE_OUTLIER")
        if signal.get("pitch_variant_skipped") or signal.get("pitch_variant_mixed"):
            warnings.append(PITCH_VARIANT_SKIPPED_WARNING)
        if signal.get(GENERATION_CEILING_METRIC):
            warnings.append(GENERATION_CEILING_WARNING)
        return tuple(warnings)

    @staticmethod
    def _context_repeat_count_provenance(
        result: dict[str, Any],
        context_mode: str,
    ) -> tuple[int | None, int | None]:
        requested_repeat_count = result.get("requested_repeat_count")
        effective_repeat_count = result.get("effective_repeat_count")
        if context_mode == COLLAPSED_SHORT_CONTEXT_MODE:
            if (
                isinstance(requested_repeat_count, bool)
                or requested_repeat_count != SHORT_CONTEXT_REPEAT_COUNT
                or isinstance(effective_repeat_count, bool)
                or effective_repeat_count
                != COLLAPSED_SHORT_CONTEXT_EFFECTIVE_REPEAT_COUNT
            ):
                raise RuntimeError(
                    "collapsed repeated-short result violates its repeat-count contract"
                )
            return (
                SHORT_CONTEXT_REPEAT_COUNT,
                COLLAPSED_SHORT_CONTEXT_EFFECTIVE_REPEAT_COUNT,
            )
        if requested_repeat_count is not None or effective_repeat_count is not None:
            raise RuntimeError(
                "repeated-short collapse counts require the collapsed context mode"
            )
        return None, None

    def _record_segment_asr_decode_evidence(
        self,
        item: dict[str, Any],
        result: dict[str, Any],
        *,
        confirmation: bool,
        context_mode: str,
        selected: bool,
        repair_round: int | None,
        delivery_mode: str,
    ) -> dict[str, Any]:
        segment_id = int(item["id"])
        _wav_path, artifact_sha256 = self._validated_segment_wav_identity(item)
        asr_verdict = _asr_verdict(result)
        evidence_verdict = (
            QUALITY_VERDICT_PASS
            if asr_verdict == ASR_PASS
            else ASR_INCONCLUSIVE
            if asr_verdict == ASR_INCONCLUSIVE
            else QUALITY_VERDICT_FAIL
        )
        signal = self._segment_signal_provenance(item)
        voice_provider = getattr(self.tts, "locked_voice_provenance", None)
        locked_voice = (
            dict(voice_provider(item))
            if callable(voice_provider)
            else {
                "voice_profile_id": item.get("voice_profile_id"),
                "pitch_semitones": None,
            }
        )
        warning_codes = set(str(item.get("warning_code") or "").split("|"))
        pitch_variant_skipped = bool(
            signal.get("pitch_variant_skipped", False)
            or PITCH_VARIANT_SKIPPED_WARNING in warning_codes
        )
        configured_pitch = signal.get(
            "pitch_semitones",
            locked_voice.get("pitch_semitones"),
        )
        effective_pitch = signal.get(
            "effective_pitch_semitones",
            0 if pitch_variant_skipped else configured_pitch,
        )
        spoken_text_sha256 = str(signal.get("spoken_text_sha256") or "")
        pronunciation_delivery_variant = str(
            signal.get("pronunciation_delivery_variant")
            or PRONUNCIATION_DELIVERY_LOCKED
        )
        if not spoken_text_sha256:
            spoken_text, _anchors = self._spoken_text_with_pronunciation_variant(
                item,
                pronunciation_delivery_variant,
            )
            spoken_text_sha256 = hashlib.sha256(
                spoken_text.encode("utf-8")
            ).hexdigest()
        decode_mode = (
            "greedy"
            if confirmation
            else f"beam{int(self.settings.get('asr', {}).get('beam_size', 5))}"
        )
        normalized_context_mode = str(context_mode)
        requested_repeat_count, effective_repeat_count = (
            self._context_repeat_count_provenance(
                result,
                normalized_context_mode,
            )
        )
        anchor_metrics = result.get(LOCKED_NAME_ANCHOR_METRICS_KEY)
        anchor_failure_codes = (
            [
                str(code)
                for code in anchor_metrics.get("failure_codes", [])
                if str(code).strip()
            ]
            if isinstance(anchor_metrics, dict)
            else []
        )
        metrics = {
            "verdict": asr_verdict,
            "passed": asr_verdict == ASR_PASS,
            "reason": str(result.get("reason", "ASR_INCONCLUSIVE")),
            "transcript": str(result.get("transcript", "")),
            "similarity": float(result.get("similarity", 0.0)),
            "wer": float(result.get("wer", 1.0)),
            "repairable": bool(result.get("repairable", False)),
            "severe": bool(result.get("severe", False)),
            "decode_mode": decode_mode,
            "context_mode": normalized_context_mode,
            "requested_repeat_count": requested_repeat_count,
            "effective_repeat_count": effective_repeat_count,
            "selected": bool(selected),
            "repair_round": repair_round,
            "delivery_mode": str(delivery_mode),
            "generation_seed": (
                int(item["generation_seed"])
                if item.get("generation_seed") is not None
                else None
            ),
            "spoken_text_sha256": spoken_text_sha256,
            "pronunciation_delivery_variant": pronunciation_delivery_variant,
            "voice_profile_id": signal.get(
                "voice_profile_id",
                locked_voice.get("voice_profile_id"),
            ),
            "pitch_semitones": configured_pitch,
            "effective_pitch_semitones": effective_pitch,
            "pitch_variant_skipped": pitch_variant_skipped,
            "pitch_variant_mixed": bool(signal.get("pitch_variant_mixed", False)),
            GENERATION_CEILING_METRIC: signal.get(GENERATION_CEILING_METRIC),
            GENERATION_ENDPOINT_ACTIVE_METRIC: signal.get(
                GENERATION_ENDPOINT_ACTIVE_METRIC
            ),
            "segment_candidate_id": item.get("segment_candidate_id"),
            "generation_kind": (
                "split" if signal.get("split_parts") else "direct"
            ),
            "split_checkpoint_seed": signal.get("split_checkpoint_seed"),
            "split_seed_salt_prefix": signal.get("split_seed_salt_prefix"),
            SPLIT_STRATEGY_FIELD: signal.get(SPLIT_STRATEGY_FIELD),
            SPLIT_MAX_CHARS_FIELD: signal.get(SPLIT_MAX_CHARS_FIELD),
            "split_parts": signal.get("split_parts", []),
            LOCKED_NAME_ANCHOR_METRICS_KEY: anchor_metrics,
            "failure_codes": anchor_failure_codes,
        }
        for field in HA_VOCALIZATION_PROVENANCE_FIELDS:
            metrics[field] = signal.get(field)
        for field in POSTPROCESS_PROVENANCE_FIELDS:
            metrics[field] = signal.get(field)
        evidence_failure_codes = list(anchor_failure_codes)
        if evidence_verdict != QUALITY_VERDICT_PASS:
            reason = str(metrics["reason"])
            if reason not in evidence_failure_codes:
                evidence_failure_codes.append(reason)
        metrics["failure_codes"] = list(evidence_failure_codes)
        check_id = self.db.record_quality_check(
            scope=QUALITY_SCOPE_SEGMENT,
            stage=SEGMENT_ASR_DECODE_QUALITY_STAGE,
            segment_id=segment_id,
            artifact_sha256=artifact_sha256,
            policy_hash=self.quality_policy_hash,
            policy_version=QUALITY_POLICY_VERSION,
            verdict=evidence_verdict,
            metrics=metrics,
            failure_codes=tuple(evidence_failure_codes),
            attempt=self._next_segment_quality_attempt(
                segment_id,
                SEGMENT_ASR_DECODE_QUALITY_STAGE,
            ),
        )
        return {
            "quality_check_id": check_id,
            "artifact_sha256": artifact_sha256,
            **metrics,
        }

    def _record_segment_audio_gate(
        self,
        item: dict[str, Any],
        result: dict[str, Any],
        *,
        verdict: str,
        confirmation: bool,
        decode_evidence: list[dict[str, Any]] | None = None,
        repair_action: str | None = None,
    ) -> int:
        segment_id = int(item["id"])
        _wav_path, artifact_sha256 = self._validated_segment_wav_identity(item)
        signal = self._segment_signal_provenance(item)
        reason = str(result.get("reason", "ok"))
        selected_context_mode = str(result.get("selected_context_mode", "direct"))
        requested_repeat_count, effective_repeat_count = (
            self._context_repeat_count_provenance(
                result,
                selected_context_mode,
            )
        )
        anchor_metrics = result.get(LOCKED_NAME_ANCHOR_METRICS_KEY)
        result_failure_codes: list[str] = []
        for code in result.get("failure_codes", []):
            normalized_code = str(code).strip()
            if normalized_code and normalized_code not in result_failure_codes:
                result_failure_codes.append(normalized_code)
        if isinstance(anchor_metrics, dict):
            for code in anchor_metrics.get("failure_codes", []):
                normalized_code = str(code).strip()
                if normalized_code and normalized_code not in result_failure_codes:
                    result_failure_codes.append(normalized_code)
        if verdict == QUALITY_VERDICT_PASS:
            result_failure_codes = []
        elif reason not in result_failure_codes:
            result_failure_codes.append(reason)
        return self.db.record_quality_check(
            scope=QUALITY_SCOPE_SEGMENT,
            stage=SEGMENT_AUDIO_QUALITY_STAGE,
            segment_id=segment_id,
            artifact_sha256=artifact_sha256,
            policy_hash=self.quality_policy_hash,
            policy_version=QUALITY_POLICY_VERSION,
            verdict=verdict,
            metrics={
                "verdict": _asr_verdict(result),
                "reason": reason,
                "transcript": str(result.get("transcript", "")),
                "similarity": float(result.get("similarity", 0.0)),
                "wer": float(result.get("wer", 0.0)),
                "confirmation_decode": bool(confirmation),
                "selected_context_mode": selected_context_mode,
                "requested_repeat_count": requested_repeat_count,
                "effective_repeat_count": effective_repeat_count,
                "dual_decode_required": bool(result.get("dual_decode_required", False)),
                "dual_decode_passed": bool(result.get("dual_decode_passed", False)),
                "confirmation_verdicts": list(
                    result.get("confirmation_verdicts", [])
                ),
                "tts_error": str(result.get("tts_error", "")),
                "decode_failure_reasons": list(
                    result.get("decode_failure_reasons", [])
                ),
                "decode_evidence": list(decode_evidence or []),
                "pronunciation_delivery_variant": str(
                    signal.get("pronunciation_delivery_variant")
                    or PRONUNCIATION_DELIVERY_LOCKED
                ),
                "spoken_text_sha256": str(signal.get("spoken_text_sha256") or ""),
                LOCKED_NAME_ANCHOR_METRICS_KEY: anchor_metrics,
                "repeated_short_context": (
                    selected_context_mode
                    in {"repeat3", COLLAPSED_SHORT_CONTEXT_MODE}
                    or str(result.get("reason", "")) == "ASR_REPEATED_SHORT_PASS"
                ),
            },
            failure_codes=tuple(result_failure_codes),
            repair_action=repair_action,
            attempt=self._next_segment_quality_attempt(segment_id),
        )

    def _perceptual_qa_enabled(self) -> bool:
        return bool(self.settings.get("perceptual_qa", {}).get("enabled", False))

    def _perceptual_qa_uses_gpu(self) -> bool:
        device = str(self.settings.get("perceptual_qa", {}).get("device", "cpu"))
        return device.strip().casefold().startswith("cuda")

    def _segment_has_current_content_qa(self, row: Any) -> bool:
        artifact_sha256 = str(row["wav_sha256"] or "").strip()
        return self.db.segment_audio_is_current_qa_verified(
            int(row["id"]),
            artifact_sha256,
            SEGMENT_AUDIO_QUALITY_STAGE,
        )

    def _segment_has_current_audio_qa(self, row: Any) -> bool:
        if not self._segment_has_current_content_qa(row):
            return False
        artifact_sha256 = str(row["wav_sha256"] or "").strip()
        return not self._perceptual_qa_enabled() or self.db.segment_audio_is_current_qa_verified(
            int(row["id"]),
            artifact_sha256,
            SEGMENT_PERCEPTUAL_QUALITY_STAGE,
        )

    def _segment_has_current_asr_failure(self, row: Any) -> bool:
        artifact_sha256 = str(row["wav_sha256"] or "").strip()
        if not artifact_sha256:
            return False
        check = self.db.latest_quality_check(
            scope=QUALITY_SCOPE_SEGMENT,
            stage=SEGMENT_AUDIO_QUALITY_STAGE,
            segment_id=int(row["id"]),
        )
        return bool(
            check is not None
            and str(check["artifact_sha256"] or "") == artifact_sha256
            and str(check["verdict"]) in {QUALITY_VERDICT_FAIL, ASR_INCONCLUSIVE}
        )

    def _chapter_has_current_segment_audio_qa(self, chapter_id: int) -> bool:
        if not self.db.chapter_segments_have_current_audio_qa(
            chapter_id,
            SEGMENT_AUDIO_QUALITY_STAGE,
        ):
            return False
        return not self._perceptual_qa_enabled() or self.db.chapter_segments_have_current_audio_qa(
            chapter_id,
            SEGMENT_PERCEPTUAL_QUALITY_STAGE,
        )

    def _record_segment_perceptual_evidence(
        self,
        item: Any,
        result: dict[str, Any],
        *,
        verdict: str,
        failure_codes: tuple[str, ...] = (),
        repair_action: str | None = None,
    ) -> int:
        segment_id = int(item["id"])
        artifact_sha256 = str(item["wav_sha256"] or "").strip()
        wav_path = Path(str(item["wav_path"] or ""))
        if (
            not artifact_sha256
            or not wav_path.is_file()
            or sha256_file(wav_path) != artifact_sha256
        ):
            raise AudioQualityError(
                f"WAV changed before perceptual QA evidence for {item['stable_id']}"
            )
        return self.db.record_quality_check(
            scope=QUALITY_SCOPE_SEGMENT,
            stage=SEGMENT_PERCEPTUAL_QUALITY_STAGE,
            segment_id=segment_id,
            artifact_sha256=artifact_sha256,
            policy_hash=self.quality_policy_hash,
            policy_version=QUALITY_POLICY_VERSION,
            verdict=verdict,
            metrics=result,
            failure_codes=failure_codes,
            repair_action=repair_action,
            attempt=self._next_segment_quality_attempt(
                segment_id,
                SEGMENT_PERCEPTUAL_QUALITY_STAGE,
            ),
        )

    def _effective_perceptual_profile(self, row: Any) -> tuple[Any, int]:
        profile = (
            self.db.voice_profile_by_key("narrator")
            if str(row["kind"] or "narration") == "thought"
            else self.db.voice_profile(int(row["voice_profile_id"]))
        )
        pitch_semitones = int(profile["pitch_semitones"] or 0)
        try:
            signal = json.loads(str(row["signal_json"] or "{}"))
        except (TypeError, json.JSONDecodeError):
            signal = {}
        if isinstance(signal, dict) and signal.get("pitch_variant_skipped"):
            pitch_semitones = 0
        return profile, pitch_semitones

    def _evaluate_perceptual_audio_item(
        self,
        row: Any,
        *,
        gate_label: str,
    ) -> dict[str, Any]:
        perceptual_uses_gpu = self._perceptual_qa_uses_gpu()
        self._resource_gate(
            gate_label,
            release_active=self.perceptual_qa.unload,
            require_gpu=perceptual_uses_gpu,
            require_cpu_io=not perceptual_uses_gpu,
        )
        profile, baseline_pitch_semitones = self._effective_perceptual_profile(row)
        preset_name = str(profile["preset_name"] or "").strip()
        result = self.perceptual_qa.verify(
            Path(str(row["wav_path"])),
            preset_name,
            pitch_semitones=baseline_pitch_semitones,
        )
        perceptual_verdict = str(result.get("verdict", PERCEPTUAL_INCONCLUSIVE))
        reason = str(result.get("reason", "PERCEPTUAL_EVIDENCE_ERROR"))
        short_audio_exemption = (
            perceptual_verdict == PERCEPTUAL_INCONCLUSIVE
            and reason == PERCEPTUAL_SHORT_AUDIO_REASON
        )
        return {
            **result,
            "baseline_pitch_semitones": baseline_pitch_semitones,
            "policy_exemption": "short_audio" if short_audio_exemption else None,
        }

    @staticmethod
    def _classify_perceptual_result(
        result: dict[str, Any],
        *,
        allow_short_audio_exemption: bool = True,
    ) -> tuple[str, tuple[str, ...]]:
        perceptual_verdict = str(result.get("verdict", PERCEPTUAL_INCONCLUSIVE))
        if perceptual_verdict == PERCEPTUAL_OK or (
            allow_short_audio_exemption
            and result.get("policy_exemption") == "short_audio"
        ):
            return QUALITY_VERDICT_PASS, ()
        reason = str(result.get("reason", "PERCEPTUAL_EVIDENCE_ERROR"))
        warning_code = (
            PERCEPTUAL_NATURALNESS_REVIEW_CODE
            if perceptual_verdict == PERCEPTUAL_REVIEW
            else reason
        )
        return "inconclusive", (warning_code,)

    def _verify_segment_candidate_perceptual(
        self,
        segment: Any,
        candidate: Any,
        chapter: Any,
    ) -> Any:
        candidate_item = self._segment_candidate_item(segment, candidate)
        candidate_repair_requirement = str(
            candidate["candidate_repair_requirement"]
        )
        require_naturalness_improvement = (
            candidate_repair_requirement == NATURALNESS_IMPROVEMENT_REQUIREMENT
        )
        require_strict_short_audio_gate = (
            require_naturalness_improvement
            or str(candidate["postprocess_profile"]) == POSTPROCESS_PROFILE_TEMPO
        )
        candidate_signal = json.loads(str(candidate["signal_json"] or "{}"))
        if not isinstance(candidate_signal, dict):
            raise RuntimeError("candidate perceptual signal provenance is invalid")
        baseline_pitch_semitones = 0
        try:
            result = self._evaluate_perceptual_audio_item(
                candidate_item,
                gate_label=(
                    f"UTMOSv2 candidate chapter {chapter['chapter_index']} "
                    f"segment {segment['seq']}"
                ),
            )
            result = {
                **result,
                "candidate_repair_requirement": candidate_repair_requirement,
            }
            for field in POSTPROCESS_PROVENANCE_FIELDS:
                result[field] = candidate_signal.get(field)
        except (PerceptualQAUnavailable, KeyError, TypeError, ValueError) as exc:
            reason = (
                exc.reason
                if isinstance(exc, PerceptualQAUnavailable)
                else "PERCEPTUAL_EVIDENCE_ERROR"
            )
            try:
                _profile, baseline_pitch_semitones = self._effective_perceptual_profile(
                    candidate_item
                )
            except (KeyError, TypeError, ValueError):
                baseline_pitch_semitones = 0
            result = {
                "verdict": PERCEPTUAL_INCONCLUSIVE,
                "reason": reason,
                "review_required": True,
                "baseline_pitch_semitones": baseline_pitch_semitones,
                "candidate_repair_requirement": candidate_repair_requirement,
                "error": str(exc),
            }
            for field in POSTPROCESS_PROVENANCE_FIELDS:
                result[field] = candidate_signal.get(field)
            self._record_segment_perceptual_evidence(
                candidate_item,
                result,
                verdict=QUALITY_VERDICT_FAIL,
                failure_codes=(reason,),
            )
            raise ChapterQualityError(
                f"Mandatory perceptual QA is unavailable for {segment['stable_id']}: {exc}",
                metrics={
                    "segment_id": int(segment["id"]),
                    "candidate_id": int(candidate["id"]),
                    **result,
                },
                failure_codes=(reason,),
                review_required=True,
            ) from exc

        evidence_verdict, failure_codes = self._classify_perceptual_result(
            result,
            allow_short_audio_exemption=not require_strict_short_audio_gate,
        )
        quality_check_id = self._record_segment_perceptual_evidence(
            candidate_item,
            result,
            verdict=evidence_verdict,
            failure_codes=failure_codes,
        )
        perceptual_verdict = str(result.get("verdict", PERCEPTUAL_INCONCLUSIVE))
        strict_short_audio = (
            require_strict_short_audio_gate
            and str(result.get("reason") or "") == PERCEPTUAL_SHORT_AUDIO_REASON
        )
        if (
            evidence_verdict != QUALITY_VERDICT_PASS
            and perceptual_verdict != PERCEPTUAL_REVIEW
            and not strict_short_audio
        ):
            reason = str(result.get("reason", "PERCEPTUAL_EVIDENCE_ERROR"))
            raise ChapterQualityError(
                f"Perceptual QA is inconclusive for {segment['stable_id']}: {reason}",
                metrics={
                    "segment_id": int(segment["id"]),
                    "candidate_id": int(candidate["id"]),
                    **result,
                },
                failure_codes=failure_codes,
                review_required=True,
            )
        return self.db.checkpoint_segment_candidate_perceptual(
            int(candidate["id"]),
            quality_check_id=quality_check_id,
        )

    def _verify_chapter_perceptual_audio(self, chapter: Any) -> list[dict[str, Any]]:
        if not self._perceptual_qa_enabled():
            return []
        chapter_id = int(chapter["id"])
        rows = self.db.list_segments(chapter_id=chapter_id)
        pending = [
            row
            for row in rows
            if str(row["status"]) != SegmentStatus.FAILED.value
            and not self.db.segment_audio_is_current_qa_verified(
                int(row["id"]),
                str(row["wav_sha256"] or ""),
                SEGMENT_PERCEPTUAL_QUALITY_STAGE,
            )
        ]
        label = f"Perceptual QA chapter {chapter['chapter_index']}"
        review_candidates: list[dict[str, Any]] = []
        self._progress(label, 0, len(pending))
        for index, row in enumerate(pending, 1):
            if not self.db.segment_audio_is_current_qa_verified(
                int(row["id"]),
                str(row["wav_sha256"] or ""),
                SEGMENT_AUDIO_QUALITY_STAGE,
            ):
                raise ChapterQualityError(
                    f"Perceptual QA requires current ASR evidence for {row['stable_id']}",
                    metrics={"segment_id": int(row["id"])},
                    failure_codes=("PERCEPTUAL_ASR_EVIDENCE_MISSING",),
                    review_required=True,
                )
            baseline_pitch_semitones = 0
            try:
                result = self._evaluate_perceptual_audio_item(
                    row,
                    gate_label=(
                        f"UTMOSv2 chapter {chapter['chapter_index']} segment {row['seq']}"
                    ),
                )
                baseline_pitch_semitones = int(
                    result.get("baseline_pitch_semitones", 0)
                )
            except (PerceptualQAUnavailable, KeyError, TypeError, ValueError) as exc:
                reason = (
                    exc.reason
                    if isinstance(exc, PerceptualQAUnavailable)
                    else "PERCEPTUAL_EVIDENCE_ERROR"
                )
                result = {
                    "verdict": PERCEPTUAL_INCONCLUSIVE,
                    "reason": reason,
                    "review_required": True,
                    "baseline_pitch_semitones": baseline_pitch_semitones,
                    "error": str(exc),
                }
                self._record_segment_perceptual_evidence(
                    row,
                    result,
                    verdict=QUALITY_VERDICT_FAIL,
                    failure_codes=(reason,),
                )
                self.db.mark_perceptual_result(int(row["id"]), warning_code=reason)
                raise ChapterQualityError(
                    f"Mandatory perceptual QA is unavailable for {row['stable_id']}: {exc}",
                    metrics={"segment_id": int(row["id"]), **result},
                    failure_codes=(reason,),
                    review_required=True,
                ) from exc

            perceptual_verdict = str(result.get("verdict", PERCEPTUAL_INCONCLUSIVE))
            evidence_verdict, failure_codes = self._classify_perceptual_result(result)
            if evidence_verdict == QUALITY_VERDICT_PASS:
                self._record_segment_perceptual_evidence(
                    row,
                    result,
                    verdict=QUALITY_VERDICT_PASS,
                )
                self.db.mark_perceptual_result(int(row["id"]))
            else:
                warning_code = failure_codes[0]
                quality_check_id = self._record_segment_perceptual_evidence(
                    row,
                    result,
                    verdict=evidence_verdict,
                    failure_codes=failure_codes,
                    repair_action=(
                        NATURALNESS_REPAIR_ACTION
                        if perceptual_verdict == PERCEPTUAL_REVIEW
                        else None
                    ),
                )
                self.db.mark_perceptual_result(
                    int(row["id"]),
                    warning_code=warning_code,
                )
                if perceptual_verdict == PERCEPTUAL_REVIEW:
                    review_item = dict(row)
                    review_item["perceptual_repair_trigger_check_id"] = (
                        quality_check_id
                    )
                    review_candidates.append(review_item)
            self._progress(label, index, len(pending))
        return review_candidates

    def _repair_chapter_perceptual_candidates(
        self,
        chapter: Any,
        verifier: WhisperVerifier,
        review_candidates: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        repair_rounds = int(
            self.settings.get("perceptual_qa", {}).get("repair_rounds", 0)
        )
        if repair_rounds <= 0:
            return review_candidates
        repair_targets = {
            int(item["id"]): dict(item)
            for item in review_candidates
        }
        chapter_segments = {
            int(item["id"]): dict(item)
            for item in self.db.list_segments(chapter_id=int(chapter["id"]))
        }
        durable_candidates: dict[int, list[Any]] = {}
        for candidate in self.db.list_segment_candidates(
            policy_hash=self.quality_policy_hash
        ):
            segment_id = int(candidate["segment_id"])
            if segment_id in chapter_segments:
                durable_candidates.setdefault(segment_id, []).append(candidate)
        for segment_id, candidates in durable_candidates.items():
            naturalness_candidates = [
                candidate
                for candidate in candidates
                if str(candidate["candidate_repair_requirement"])
                == NATURALNESS_IMPROVEMENT_REQUIREMENT
            ]
            if not naturalness_candidates:
                continue
            trigger_check_ids = {
                int(candidate["repair_trigger_check_id"])
                for candidate in naturalness_candidates
                if candidate["repair_trigger_check_id"] is not None
            }
            if (
                len(naturalness_candidates) != len(candidates)
                or len(trigger_check_ids) != 1
            ):
                raise RuntimeError(
                    "durable perceptual candidate ledger has mixed repair bindings"
                )
            repair_item = repair_targets.get(
                segment_id,
                dict(chapter_segments[segment_id]),
            )
            repair_item["perceptual_repair_trigger_check_id"] = next(
                iter(trigger_check_ids)
            )
            repair_targets[segment_id] = repair_item
        if not repair_targets:
            return review_candidates
        unresolved: list[dict[str, Any]] = []
        maximum_state_iterations = max(8, repair_rounds * 6 + 8)
        for _state_iteration in range(maximum_state_iterations):
            if not repair_targets:
                break
            self.db.reconcile_segment_candidate_artifacts(self.quality_policy_hash)
            generation_jobs: list[tuple[dict[str, Any], Any]] = []
            beam_jobs: list[tuple[dict[str, Any], Any]] = []
            greedy_jobs: list[tuple[dict[str, Any], Any]] = []
            perceptual_jobs: list[tuple[dict[str, Any], Any]] = []
            promotion_jobs: list[tuple[dict[str, Any], Any]] = []
            completed_ids: list[int] = []
            progressed = False

            for segment_id, repair_context in list(repair_targets.items()):
                segment = dict(self.db.get_segment(segment_id))
                plan = self.db.segment_candidate_resume_plan(
                    segment_id,
                    self.quality_policy_hash,
                    repair_rounds,
                )
                action = str(plan["action"])
                if action == "allocate":
                    candidate_repair_requirement = str(
                        plan.get(
                            "candidate_repair_requirement",
                            NATURALNESS_IMPROVEMENT_REQUIREMENT,
                        )
                    )
                    repair_trigger_check_id = plan.get(
                        "repair_trigger_check_id",
                        repair_context.get(
                            "perceptual_repair_trigger_check_id"
                        ),
                    )
                    if (
                        candidate_repair_requirement
                        != NATURALNESS_IMPROVEMENT_REQUIREMENT
                        or repair_trigger_check_id is None
                    ):
                        raise RuntimeError(
                            "perceptual candidate resume lacks its durable naturalness trigger"
                        )
                    candidate = self._allocate_segment_candidate(
                        segment,
                        int(plan["repair_round"]),
                        repair_rounds,
                        candidate_repair_requirement=(
                            candidate_repair_requirement
                        ),
                        repair_trigger_check_id=int(
                            repair_trigger_check_id
                        ),
                    )
                    generation_jobs.append((segment, candidate))
                    progressed = True
                elif action == "generate":
                    generation_jobs.append(
                        (
                            segment,
                            self.db.get_segment_candidate(int(plan["candidate_id"])),
                        )
                    )
                elif action == "decode_beam":
                    beam_jobs.append(
                        (segment, self.db.get_segment_candidate(int(plan["candidate_id"])))
                    )
                elif action == "decode_greedy":
                    greedy_jobs.append(
                        (segment, self.db.get_segment_candidate(int(plan["candidate_id"])))
                    )
                elif action == "verify_perceptual":
                    perceptual_jobs.append(
                        (segment, self.db.get_segment_candidate(int(plan["candidate_id"])))
                    )
                elif action == "promote":
                    promotion_jobs.append(
                        (segment, self.db.get_segment_candidate(int(plan["candidate_id"])))
                    )
                elif action == "exhausted":
                    unresolved.append(segment)
                    completed_ids.append(segment_id)
                    progressed = True
                elif action == "complete":
                    completed_ids.append(segment_id)
                    progressed = True
                elif action in {"stale_policy", "stale_incumbent"}:
                    raise RuntimeError(
                        f"perceptual candidate resume refused {action} for segment {segment_id}"
                    )
                else:
                    raise RuntimeError(
                        f"unsupported perceptual candidate resume action: {action}"
                    )

            for segment_id in completed_ids:
                repair_targets.pop(segment_id, None)

            if generation_jobs:
                verifier.unload()
                self.perceptual_qa.unload()
                label = f"Tạo candidate perceptual chapter {chapter['chapter_index']}"
                self._progress(label, 0, len(generation_jobs))
                for index, (segment, candidate) in enumerate(generation_jobs, 1):
                    self._resource_gate(
                        f"candidate perceptual chapter {chapter['chapter_index']} "
                        f"segment {segment['seq']}",
                        keep_engine=None,
                    )
                    self._process_segment_candidate(segment, candidate, chapter)
                    self._progress(label, index, len(generation_jobs))
                self.tts.unload_all()
                progressed = True
                continue

            if beam_jobs or greedy_jobs:
                self.tts.unload_all()
                decode_jobs = [
                    *[(False, item, candidate) for item, candidate in beam_jobs],
                    *[(True, item, candidate) for item, candidate in greedy_jobs],
                ]
                label = f"Whisper candidate perceptual chapter {chapter['chapter_index']}"
                self._progress(label, 0, len(decode_jobs))
                for index, (confirmation, segment, candidate) in enumerate(decode_jobs, 1):
                    candidate_item = self._segment_candidate_item(segment, candidate)
                    self._resource_gate(
                        f"Whisper candidate perceptual chapter {chapter['chapter_index']} "
                        f"segment {segment['seq']}",
                        release_active=verifier.unload,
                    )
                    result = self._decode_audio_candidate(
                        candidate_item,
                        verifier,
                        confirmation=confirmation,
                        repair_round=int(candidate["repair_round"]),
                        delivery_mode=DELIVERY_CLARITY,
                    )
                    self.db.checkpoint_segment_candidate_decode(
                        int(candidate["id"]),
                        quality_check_id=int(result["selected_quality_check_id"]),
                        confirmation=confirmation,
                    )
                    self._progress(label, index, len(decode_jobs))
                progressed = True
                continue

            if perceptual_jobs:
                verifier.unload()
                label = f"UTMOSv2 candidate perceptual chapter {chapter['chapter_index']}"
                self._progress(label, 0, len(perceptual_jobs))
                for index, (segment, candidate) in enumerate(perceptual_jobs, 1):
                    self._verify_segment_candidate_perceptual(
                        segment,
                        candidate,
                        chapter,
                    )
                    self._progress(label, index, len(perceptual_jobs))
                progressed = True
                continue

            if promotion_jobs:
                for segment, candidate in promotion_jobs:
                    candidate_item = self._segment_candidate_item(segment, candidate)
                    signal_valid, _signal_metrics = self._inspect_existing_segment(
                        candidate_item
                    )
                    if not signal_valid:
                        self.db.mark_segment_candidate_invalid(
                            int(candidate["id"]),
                            expected_wav_sha256=str(candidate["wav_sha256"]),
                            reason=(
                                "perceptual candidate failed signal validation immediately "
                                "before promotion"
                            ),
                        )
                        progressed = True
                        continue
                    signal = self._segment_signal_provenance(candidate_item)
                    warning_code = "|".join(
                        self._signal_warning_codes(
                            signal,
                            split_recovery=bool(signal.get("split_parts")),
                        )
                    ) or None
                    promoted = self.db.promote_segment_candidate(
                        int(candidate["id"]),
                        validated_wav_sha256=str(candidate["wav_sha256"]),
                        repair_action="promote_perceptual_repair_candidate",
                        attempt=self._next_segment_quality_attempt(int(segment["id"])),
                        warning_code=warning_code,
                    )
                    if str(promoted["state"]) == SEGMENT_CANDIDATE_PROMOTED:
                        repair_targets.pop(int(segment["id"]), None)
                        self.db.event(
                            "info",
                            "PERCEPTUAL_CANDIDATE_PROMOTED",
                            f"Immutable perceptual candidate promoted for {segment['stable_id']}",
                            {
                                "candidate_id": int(candidate["id"]),
                                "repair_round": int(candidate["repair_round"]),
                                "wav_sha256": str(candidate["wav_sha256"]),
                            },
                        )
                    progressed = True
                continue

            if not progressed:
                raise RuntimeError("perceptual candidate state machine made no progress")
        else:
            raise RuntimeError(
                "perceptual candidate state machine exceeded its finite transition budget"
            )
        if repair_targets:
            raise RuntimeError("perceptual candidate state machine stopped with unfinished repairs")
        return unresolved

    def _chapter_audio_evidence_sha256(self, chapter_id: int) -> str:
        digest = hashlib.sha256()
        digest.update(f"policy={self.quality_policy_hash}\nchapter={chapter_id}\n".encode("utf-8"))
        for row in self.db.list_segments(chapter_id=chapter_id):
            digest.update(
                (
                    f"{row['stable_id']}\t{row['wav_sha256'] or ''}\t"
                    f"{int(row['break_ms'])}\n"
                ).encode("utf-8")
            )
        return digest.hexdigest()

    def _high_quality_blocking_segment_warnings(
        self,
        rows: list[Any],
    ) -> list[dict[str, Any]]:
        if self.settings.get("quality_profile") != "high_quality":
            return []
        blocking: list[dict[str, Any]] = []
        for row in rows:
            warning_codes = {
                value
                for value in str(row["warning_code"] or "").split("|")
                if value
            }
            blocked_codes = sorted(warning_codes - HIGH_QUALITY_ALLOWED_SEGMENT_WARNINGS)
            if blocked_codes:
                blocking.append(
                    {
                        "segment_id": int(row["id"]),
                        "stable_id": str(row["stable_id"]),
                        "warning_codes": blocked_codes,
                    }
                )
        return blocking

    def _record_chapter_quality_failure(self, chapter: Any, error: AudioQualityError) -> None:
        chapter_id = int(chapter["id"])
        structured = error if isinstance(error, ChapterQualityError) else None
        candidate_checksum = structured.artifact_sha256 if structured is not None else None
        metrics = dict(structured.metrics) if structured is not None else {}
        metrics.setdefault("error", str(error))
        metrics["review_required"] = bool(structured and structured.review_required)
        metrics["evidence_kind"] = "encoded_candidate" if candidate_checksum else "chapter_wav_set"
        artifact_sha256 = candidate_checksum or self._chapter_audio_evidence_sha256(chapter_id)
        failure_codes = (
            structured.failure_codes
            if structured is not None and structured.failure_codes
            else (CHAPTER_AUDIO_PIPELINE_FAILURE_CODE,)
        )
        attempt = self._next_chapter_quality_attempt(chapter_id)
        self.db.record_quality_check(
            scope=QUALITY_SCOPE_CHAPTER,
            stage=CHAPTER_QUALITY_STAGE,
            chapter_id=chapter_id,
            artifact_sha256=artifact_sha256,
            policy_hash=self.quality_policy_hash,
            policy_version=QUALITY_POLICY_VERSION,
            verdict=QUALITY_VERDICT_FAIL,
            metrics=metrics,
            failure_codes=failure_codes,
            repair_action=CHAPTER_QUALITY_REPAIR_ACTION,
            attempt=attempt,
        )
        error_text = str(error)[-8000:]
        self.db.update_chapter_status(chapter_id, ChapterStatus.FAILED.value, error_text)
        event_code = (
            "CHAPTER_QA_REVIEW_REQUIRED"
            if structured is not None and structured.review_required
            else "CHAPTER_QA_FAILED"
        )
        self.db.event(
            "error",
            event_code,
            f"Chapter {chapter['title']} was not published: {error_text}",
            {
                "chapter_id": chapter_id,
                "chapter_index": int(chapter["chapter_index"]),
                "artifact_sha256": artifact_sha256,
                "failure_codes": list(failure_codes),
                "attempt": attempt,
                "metrics": metrics,
            },
        )
        self.emit(
            "chapter_failed",
            {
                "chapter_id": chapter_id,
                "title": str(chapter["title"]),
                "error": error_text,
                "review_required": bool(structured and structured.review_required),
            },
        )
        self.log(
            f"Không xuất chapter {chapter['title']} do QA audio: {error_text}. "
            "Pipeline sẽ tiếp tục chapter kế tiếp."
        )

    def _finalize_book(self) -> None:
        completed = [row for row in self.db.list_chapters() if row["status"] == ChapterStatus.COMPLETED.value]
        all_chapters = self.db.list_chapters()
        if completed and len(completed) == len(all_chapters):
            chapter_files = [Path(str(row["output_mp3"])) for row in completed]
            if self.settings["audio"].get("create_m3u8", True):
                write_playlist_atomic(chapter_files, self.paths.output / "playlist.m3u8")
            self.db.update_book(status=BookStatus.COMPLETED.value, stage="completed", error=None)
            self._state("completed", "Đã hoàn tất toàn bộ audiobook.")
            self.notifier.notify(
                "Ebook Reader đã hoàn tất",
                f"Book: {self.db.book()['title']}",
                project_path=self.paths.root,
            )
        else:
            failed = len([row for row in all_chapters if row["status"] == ChapterStatus.FAILED.value])
            error_text = f"Đã xử lý xong nhưng còn {failed} chapter lỗi."
            self.db.update_book(
                status=BookStatus.ERROR.value,
                stage="completed_with_errors",
                error=f"{failed} chapter chưa thể xuất MP3",
            )
            self.db.event(
                "error",
                "BOOK_COMPLETED_WITH_ERRORS",
                error_text,
                {"failed_chapters": failed},
            )
            self._state("error", error_text)
            if self.settings["safety"].get("notify_on_critical_stop", True):
                self.notifier.critical_stop(
                    str(self.db.book()["title"]),
                    error_text,
                    self.paths.root,
                    "kết thúc pipeline",
                )

    def _inspect_existing_segment(self, row: Any) -> tuple[bool, dict[str, float]]:
        wav_text = str(row["wav_path"] or "")
        if not wav_text:
            return False, {}
        wav = Path(wav_text)
        if not wav.exists():
            return False, {}
        wav_sha256 = str(row["wav_sha256"] or "").strip()
        if not wav_sha256 or sha256_file(wav) != wav_sha256:
            return False, {}
        expected_text, _anchors = self._spoken_text_and_anchors(dict(row))
        valid, metrics, _ = inspect_wav(
            wav,
            expected_text,
            self.settings,
            segment=row,
        )
        return valid, metrics if valid else {}

    def _existing_segment_is_safe(self, row: Any) -> bool:
        if str(row["status"]) not in {SegmentStatus.VERIFIED.value, SegmentStatus.WARNING.value}:
            return False
        valid, _ = self._inspect_existing_segment(row)
        if not valid:
            return False
        return self._segment_has_current_content_qa(row)

    def _recheckpoint_segment_for_current_audio_qa(
        self,
        row: Any,
        metrics: dict[str, float],
    ) -> None:
        checkpoint_metrics: dict[str, Any] = dict(metrics)
        existing_signal = self._segment_signal_provenance(dict(row))
        for field in TTS_SIGNAL_PROVENANCE_FIELDS:
            if field in existing_signal:
                checkpoint_metrics[field] = existing_signal[field]
        generation_seed = (
            int(row["generation_seed"])
            if row["generation_seed"] is not None
            else self.tts.generation_seed(row, "qa_recheck")
        )
        self.db.mark_generating(int(row["id"]), generation_seed)
        self.db.mark_signal_passed(
            int(row["id"]),
            wav_path=Path(str(row["wav_path"])),
            wav_sha256=str(row["wav_sha256"]),
            duration=float(checkpoint_metrics["duration"]),
            signal=checkpoint_metrics,
            generation_seed=generation_seed,
            warning_codes=self._signal_warning_codes(
                checkpoint_metrics,
                split_recovery=bool(checkpoint_metrics.get("split_parts")),
            ),
        )

    def _process_chapter(self, chapter: Any, verifier: WhisperVerifier) -> None:
        chapter_id = int(chapter["id"])
        self._validate_chapter_source(chapter)
        output = Path(str(chapter["output_mp3"]))
        if chapter["status"] == ChapterStatus.COMPLETED.value:
            valid, _ = verify_mp3(output)
            quality_verified = self.db.chapter_artifact_is_current_qa_verified(
                int(chapter["chapter_index"])
            )
            segment_quality_verified = self._chapter_has_current_segment_audio_qa(chapter_id)
            if valid and quality_verified and segment_quality_verified:
                self.log(f"Bỏ qua chapter đã hoàn tất: {chapter['title']}")
                return
            self.log(
                f"Chapter {chapter['title']} có MP3 legacy hoặc policy QA cũ; "
                "không bỏ qua chỉ dựa trên khả năng giải mã."
            )

        self.db.update_chapter_status(chapter_id, ChapterStatus.SYNTHESIZING.value)
        self.log(f"Tạo audio chapter {chapter['chapter_index']}: {chapter['title']}")
        rows = self.db.list_segments(chapter_id=chapter_id)
        for row in rows:
            if str(row["status"]) in {
                SegmentStatus.SIGNAL_PASSED.value,
                SegmentStatus.ASR_PASSED.value,
            } and not row["wav_path"]:
                self.db.reset_segment_pending(int(row["id"]), "Recovered unfinished stage before chapter processing")

        # Stage 1: synthesize sequentially with a stable seed so each checkpoint is reproducible.
        current_rows = self.db.list_segments(chapter_id=chapter_id)
        tts_label = f"Tạo audio chapter {chapter['chapter_index']}: {chapter['title']}"
        self._progress(tts_label, 0, len(current_rows))
        for index, row in enumerate(current_rows, 1):
            self._progress(tts_label, index - 1, len(current_rows))
            status = str(row["status"])
            signal_valid, signal_metrics = self._inspect_existing_segment(row)
            if signal_valid and self._segment_has_current_asr_failure(row):
                if status != SegmentStatus.FAILED.value:
                    self.db.mark_failed(
                        int(row["id"]),
                        "Current-policy ASR content gate already failed before worker interruption",
                        warning_code="ASR_CONTENT_GATE_FAILED",
                    )
                continue
            if (
                status in {SegmentStatus.VERIFIED.value, SegmentStatus.WARNING.value}
                and signal_valid
                and self._segment_has_current_content_qa(row)
            ):
                continue
            if signal_valid and status in {
                SegmentStatus.SIGNAL_PASSED.value,
                SegmentStatus.ASR_PASSED.value,
                SegmentStatus.VERIFIED.value,
                SegmentStatus.WARNING.value,
                SegmentStatus.FAILED.value,
            }:
                if status != SegmentStatus.SIGNAL_PASSED.value:
                    self._recheckpoint_segment_for_current_audio_qa(row, signal_metrics)
                continue
            if not has_spoken_content(str(row["text"])):
                self.db.mark_failed(
                    int(row["id"]),
                    "Legacy punctuation-only segment must be rebuilt by the corrected text parser",
                    warning_code="NON_SPEAKABLE_SEGMENT",
                )
                continue
            if row["voice_profile_id"] is None:
                self.db.mark_failed(int(row["id"]), "No locked voice profile")
                continue
            interrupted_clarity = (
                str(row["generation_delivery_mode"] or "") == DELIVERY_CLARITY
                and str(row["generation_policy_hash"] or "") == self.quality_policy_hash
                and row["generation_repair_round"] is not None
                and status
                in {
                    SegmentStatus.PENDING.value,
                    SegmentStatus.ANALYZED.value,
                    SegmentStatus.GENERATING.value,
                    SegmentStatus.FAILED.value,
                }
            )
            if interrupted_clarity:
                stored_round = int(row["generation_repair_round"])
                next_round = (
                    stored_round + 1
                    if status == SegmentStatus.FAILED.value
                    else stored_round
                )
                repair_rounds = int(self.settings["asr"].get("repair_rounds", 2))
                if next_round >= repair_rounds:
                    self.db.mark_failed(
                        int(row["id"]),
                        "ASR clarity repair budget was exhausted across worker restarts",
                        warning_code="ASR_CLARITY_REPAIR_BUDGET_EXHAUSTED",
                    )
                    continue
                self._resource_gate(
                    f"resume ASR clarity chapter {chapter['chapter_index']} segment {row['seq']}",
                    keep_engine="vieneu",
                )
                repair_item = self._checkpoint_short_ceiling_repair(row)
                self._process_single_segment(
                    repair_item,
                    chapter,
                    seed_salt_prefix=f"asr_clarity_repair_{next_round}",
                    repair_short_utterance=True,
                    delivery_mode=DELIVERY_CLARITY,
                    asr_repair_round=next_round,
                )
                continue
            self._resource_gate(
                f"chapter {chapter['chapter_index']} segment {row['seq']}",
                keep_engine="vieneu",
            )
            self._process_single_segment(row, chapter)
        self._progress(tts_label, len(current_rows), len(current_rows))

        # Stage 2: release TTS VRAM before loading Whisper, then verify the whole chapter.
        self.tts.unload_all()
        self.db.update_chapter_status(chapter_id, ChapterStatus.VERIFYING.value)
        self._verify_chapter_audio(chapter, verifier)
        verifier.unload()
        perceptual_reviews = self._verify_chapter_perceptual_audio(chapter)
        perceptual_reviews = self._repair_chapter_perceptual_candidates(
            chapter,
            verifier,
            perceptual_reviews,
        )

        rows = self.db.list_segments(chapter_id=chapter_id)
        blocking_warnings = self._high_quality_blocking_segment_warnings(rows)
        if blocking_warnings:
            raise ChapterQualityError(
                "High-quality policy requires repair or review for segment warnings: "
                + "; ".join(
                    f"{item['stable_id']}={','.join(item['warning_codes'])}"
                    for item in blocking_warnings
                ),
                metrics={"blocking_segment_warnings": blocking_warnings},
                failure_codes=("SEGMENT_QA_REVIEW_REQUIRED",),
                review_required=True,
            )
        if not self._chapter_has_current_segment_audio_qa(chapter_id):
            raise ChapterQualityError(
                "Current policy requires passing ASR and perceptual evidence for every segment",
                metrics={"chapter_id": chapter_id},
                failure_codes=("SEGMENT_QA_EVIDENCE_MISSING",),
                review_required=True,
            )
        if not self.db.chapter_is_publishable(chapter_id):
            failed = [row for row in rows if row["status"] == SegmentStatus.FAILED.value]
            self.db.update_chapter_status(
                chapter_id,
                ChapterStatus.FAILED.value,
                f"{len(failed)} segment failed; chapter MP3 intentionally not published",
            )
            self.log(f"Không xuất MP3 chapter {chapter['title']}: còn {len(failed)} segment lỗi.")
            return

        self._validate_chapter_source(chapter)

        wavs = self._chapter_delivery_wavs(chapter, rows)
        self._resource_gate(
            f"FFmpeg chapter {chapter['chapter_index']}",
            require_cpu_io=True,
        )
        assembly_label = f"Ghép và kiểm tra MP3 chapter {chapter['chapter_index']}"
        self._progress(assembly_label)
        assembly = assemble_chapter_atomic_with_metrics(
            wavs,
            output,
            self.settings,
            title=str(chapter["title"]),
            book_title=str(self.db.book()["title"]),
            track=int(chapter["chapter_index"]),
            work_dir=self.paths.work / "silence",
        )
        checksum = assembly.checksum
        quality_metrics = assembly.quality.to_dict()
        quality_metadata = self.db.quality_metadata_for_current_policy()
        self.db.record_quality_check(
            scope=QUALITY_SCOPE_CHAPTER,
            stage=CHAPTER_QUALITY_STAGE,
            chapter_id=chapter_id,
            artifact_sha256=checksum,
            policy_hash=self.quality_policy_hash,
            policy_version=QUALITY_POLICY_VERSION,
            verdict=QUALITY_VERDICT_PASS,
            metrics=quality_metrics,
            attempt=self._next_chapter_quality_attempt(chapter_id),
        )
        self.db.register_artifact(
            artifact_key=f"chapter_mp3:{chapter['chapter_index']}",
            kind="chapter_mp3",
            path=output,
            sha256=checksum,
            verified=True,
            metadata={
                "chapter_id": chapter_id,
                "title": str(chapter["title"]),
                "quality": quality_metadata,
                "quality_metrics": quality_metrics,
            },
        )
        if assembly.quality.review_flags:
            self.db.event(
                "warning",
                "CHAPTER_QA_REVIEW_FLAGS",
                f"Chapter {chapter['title']} passed hard QA with review flags",
                {
                    "chapter_id": chapter_id,
                    "flags": list(assembly.quality.review_flags),
                    "metrics": quality_metrics,
                },
            )
        self.db.update_chapter_status(chapter_id, ChapterStatus.COMPLETED.value)
        self._progress(assembly_label, 1, 1)
        self.log(f"Chapter MP3 đã hoàn tất và giải mã kiểm tra thành công: {output.name}")
        self.emit(
            "chapter_completed",
            {"chapter_id": chapter_id, "path": str(output), "title": str(chapter["title"])},
        )

    def _chunk_path(self, row: Any) -> Path:
        return self.paths.chunks / f"chapter_{int(row['chapter_id']):05d}" / f"{int(row['seq']):07d}.wav"

    @staticmethod
    def _ceiling_endpoint_requires_repair(row: Any) -> bool:
        try:
            warning_value = row["warning_code"]
        except (IndexError, KeyError, TypeError):
            warning_value = None
        has_ceiling_warning = GENERATION_CEILING_WARNING in str(warning_value or "").split("|")
        try:
            raw_metrics = row["signal_json"]
        except (IndexError, KeyError, TypeError):
            raw_metrics = None
        if not str(raw_metrics or "").strip():
            return has_ceiling_warning
        try:
            metrics = json.loads(str(raw_metrics))
        except (TypeError, json.JSONDecodeError):
            return has_ceiling_warning
        if not isinstance(metrics, dict):
            return has_ceiling_warning
        has_ceiling_evidence = bool(metrics.get(GENERATION_CEILING_METRIC))
        return (has_ceiling_evidence or has_ceiling_warning) and bool(
            metrics.get(GENERATION_ENDPOINT_ACTIVE_METRIC, True)
        )

    def _checkpoint_short_ceiling_repair(self, row: Any) -> dict[str, Any]:
        warning_codes = str(row["warning_code"] or "").split("|")
        persisted_cap = int(row["generation_frame_cap"] or 0)
        if GENERATION_CEILING_WARNING not in warning_codes and persisted_cap <= 0:
            return dict(row)
        frame_cap = (
            HA_VOCALIZATION_MAX_NEW_FRAMES
            if is_standalone_ha_gasp(str(row["text"]))
            else short_utterance_repair_frame_cap(self.tts.spoken_text(row))
        )
        if frame_cap is None:
            return dict(row)
        if persisted_cap != frame_cap:
            self.db.set_segment_generation_frame_cap(int(row["id"]), frame_cap)
        return dict(self.db.get_segment(int(row["id"])))

    def _segment_candidate_root(self) -> Path:
        return self.paths.work / SEGMENT_CANDIDATE_DIRECTORY

    def _segment_candidate_path(self, row: Any, repair_round: int) -> Path:
        policy_key = self.quality_policy_hash[:16]
        return (
            self._segment_candidate_root()
            / f"chapter_{int(row['chapter_id']):05d}"
            / f"segment_{int(row['id']):08d}"
            / policy_key
            / f"round_{int(repair_round):03d}.wav"
        )

    @staticmethod
    def _supports_pronunciation_delivery_variant(provider: Callable[..., Any]) -> bool:
        try:
            parameters = inspect.signature(provider).parameters.values()
        except (TypeError, ValueError):
            return False
        return any(
            parameter.name == "pronunciation_delivery_variant"
            or parameter.kind == inspect.Parameter.VAR_KEYWORD
            for parameter in parameters
        )

    def _spoken_text_with_pronunciation_variant(
        self,
        row: Any,
        pronunciation_delivery_variant: str,
    ) -> tuple[str, list[dict[str, Any]]]:
        provider = getattr(self.tts, "spoken_text_with_anchors", None)
        if callable(provider):
            if self._supports_pronunciation_delivery_variant(provider):
                spoken_text, raw_anchors = provider(
                    row,
                    pronunciation_delivery_variant=pronunciation_delivery_variant,
                )
            elif pronunciation_delivery_variant == PRONUNCIATION_DELIVERY_LOCKED:
                spoken_text, raw_anchors = provider(row)
            else:
                raise RuntimeError(
                    "TTS provider cannot reconstruct the allocated pronunciation variant"
                )
            anchors = [dict(anchor) for anchor in raw_anchors if isinstance(anchor, dict)]
            return str(spoken_text), anchors
        if pronunciation_delivery_variant != PRONUNCIATION_DELIVERY_LOCKED:
            raise RuntimeError(
                "TTS provider cannot materialize a source-spelling pronunciation variant"
            )
        return str(self.tts.spoken_text(row)), []

    def _synthesize_atomic_with_pronunciation_variant(
        self,
        row: Any,
        output: Path,
        *,
        pronunciation_delivery_variant: str,
        **kwargs: Any,
    ) -> tuple[str, dict[str, Any], int]:
        provider = self.tts.synthesize_atomic
        if self._supports_pronunciation_delivery_variant(provider):
            return provider(
                row,
                output,
                pronunciation_delivery_variant=pronunciation_delivery_variant,
                **kwargs,
            )
        if pronunciation_delivery_variant != PRONUNCIATION_DELIVERY_LOCKED:
            raise RuntimeError(
                "TTS provider cannot synthesize the allocated source-spelling variant"
            )
        checksum, metrics, seed = provider(row, output, **kwargs)
        metrics["pronunciation_delivery_variant"] = PRONUNCIATION_DELIVERY_LOCKED
        return checksum, metrics, seed

    def _segment_candidate_pronunciation_delivery(
        self,
        row: Any,
        repair_round: int,
        *,
        required_variant: str | None = None,
        source_variant_requested: bool = False,
    ) -> tuple[str, str, list[dict[str, Any]]]:
        if required_variant not in {
            None,
            PRONUNCIATION_DELIVERY_LOCKED,
            PRONUNCIATION_DELIVERY_SOURCE,
        }:
            raise RuntimeError("candidate has an unsupported pronunciation variant")
        locked_text, locked_anchors = self._spoken_text_with_pronunciation_variant(
            row,
            PRONUNCIATION_DELIVERY_LOCKED,
        )
        if required_variant == PRONUNCIATION_DELIVERY_LOCKED:
            return PRONUNCIATION_DELIVERY_LOCKED, locked_text, locked_anchors
        variant = PRONUNCIATION_DELIVERY_LOCKED
        spoken_text = locked_text
        anchors = locked_anchors
        provider = getattr(self.tts, "spoken_text_with_anchors", None)
        should_materialize_source = (
            required_variant == PRONUNCIATION_DELIVERY_SOURCE
            or required_variant is None
            and source_variant_requested
        )
        source_variant_available = (
            should_materialize_source
            and locked_anchors
            and callable(provider)
            and self._supports_pronunciation_delivery_variant(provider)
            and self._supports_pronunciation_delivery_variant(
                self.tts.synthesize_atomic
            )
        )
        if source_variant_available:
            source_text, source_anchors = self._spoken_text_with_pronunciation_variant(
                row,
                PRONUNCIATION_DELIVERY_SOURCE,
            )
            if source_text != locked_text:
                locked_identity = [
                    (
                        int(anchor.get("order", -1)),
                        int(anchor.get("pronunciation_id", -1)),
                        int(anchor.get("occurrence", -1)),
                        int(anchor.get("source_start", -1)),
                        int(anchor.get("source_end", -1)),
                        str(anchor.get("surface") or ""),
                        str(anchor.get("normalized_surface") or ""),
                        str(anchor.get("matched_surface") or ""),
                        str(anchor.get("source") or ""),
                        str(
                            anchor.get("canonical_spoken_form")
                            or anchor.get("spoken_form")
                            or ""
                        ),
                    )
                    for anchor in locked_anchors
                ]
                source_identity = [
                    (
                        int(anchor.get("order", -1)),
                        int(anchor.get("pronunciation_id", -1)),
                        int(anchor.get("occurrence", -1)),
                        int(anchor.get("source_start", -1)),
                        int(anchor.get("source_end", -1)),
                        str(anchor.get("surface") or ""),
                        str(anchor.get("normalized_surface") or ""),
                        str(anchor.get("matched_surface") or ""),
                        str(anchor.get("source") or ""),
                        str(anchor.get("canonical_spoken_form") or ""),
                    )
                    for anchor in source_anchors
                ]
                source_anchors_are_bound = all(
                    str(anchor.get("pronunciation_delivery_variant") or "")
                    == PRONUNCIATION_DELIVERY_SOURCE
                    and str(anchor.get("spoken_form") or "")
                    == str(anchor.get("matched_surface") or "")
                    for anchor in source_anchors
                )
                if (
                    source_identity != locked_identity
                    or not source_anchors_are_bound
                ):
                    raise RuntimeError(
                        "source-spelling pronunciation anchors drifted from locked anchors"
                    )
                variant = PRONUNCIATION_DELIVERY_SOURCE
                spoken_text = source_text
                anchors = source_anchors
        if required_variant == PRONUNCIATION_DELIVERY_SOURCE and (
            variant != PRONUNCIATION_DELIVERY_SOURCE
        ):
            raise RuntimeError(
                "stored source-spelling candidate cannot be reconstructed safely"
            )
        return variant, spoken_text, anchors

    @staticmethod
    def _decode_requests_source_pronunciation(
        result: dict[str, Any],
    ) -> bool:
        failure_code = ASR_LOCKED_NAME_ANCHOR_MISMATCH
        result_failure_codes = result.get("failure_codes", [])
        if not isinstance(result_failure_codes, list) or any(
            not isinstance(code, str) or not code.strip()
            for code in result_failure_codes
        ):
            raise RuntimeError(
                "candidate ASR result has malformed failure-code evidence"
            )
        anchor_metrics = result.get(LOCKED_NAME_ANCHOR_METRICS_KEY)
        result_claims_failure = (
            str(result.get("reason") or "") == failure_code
            or failure_code in result_failure_codes
        )
        if anchor_metrics is None:
            if result_claims_failure:
                raise RuntimeError(
                    "candidate ASR locked-name failure lacks structured anchor evidence"
                )
            return False
        if not isinstance(anchor_metrics, dict):
            raise RuntimeError(
                "candidate ASR locked-name anchor evidence must be an object"
            )
        anchor_failure_codes = anchor_metrics.get("failure_codes", [])
        if not isinstance(anchor_failure_codes, list) or any(
            not isinstance(code, str) or not code.strip()
            for code in anchor_failure_codes
        ):
            raise RuntimeError(
                "candidate ASR locked-name anchor failure codes are malformed"
            )
        anchor_claims_failure = (
            anchor_metrics.get("passed") is False
            or str(anchor_metrics.get("status") or "") == "fail"
            or failure_code in anchor_failure_codes
        )
        if not result_claims_failure and not anchor_claims_failure:
            valid_nonfailure_state = (
                anchor_metrics.get("adjudicated") is True
                and anchor_metrics.get("passed") is True
                and str(anchor_metrics.get("status") or "") == "pass"
                and not anchor_failure_codes
            ) or (
                anchor_metrics.get("adjudicated") is False
                and anchor_metrics.get("passed") is None
                and str(anchor_metrics.get("status") or "")
                == "skipped_inconclusive"
                and not anchor_failure_codes
            )
            if not valid_nonfailure_state:
                raise RuntimeError(
                    "candidate ASR locked-name anchor evidence is internally inconsistent"
                )
            return False

        count_fields = (
            "repeat_count",
            "anchor_count",
            "required_occurrence_count",
            "matched_occurrence_count",
        )
        if any(
            isinstance(anchor_metrics.get(field), bool)
            or not isinstance(anchor_metrics.get(field), int)
            for field in count_fields
        ):
            raise RuntimeError(
                "candidate ASR locked-name failure has malformed occurrence counts"
            )
        repeat_count = int(anchor_metrics["repeat_count"])
        anchor_count = int(anchor_metrics["anchor_count"])
        required_count = int(anchor_metrics["required_occurrence_count"])
        matched_count = int(anchor_metrics["matched_occurrence_count"])
        failure_is_consistent = (
            str(result.get("verdict") or "") == ASR_MISMATCH
            and result.get("passed") is False
            and str(result.get("reason") or "") == failure_code
            and result_failure_codes == [failure_code]
            and result.get("repairable") is True
            and anchor_metrics.get("version")
            == LOCKED_NAME_ANCHOR_METRICS_VERSION
            and anchor_metrics.get("adjudicated") is True
            and anchor_metrics.get("passed") is False
            and str(anchor_metrics.get("status") or "")
            in LOCKED_NAME_ANCHOR_UNMATCHED_STATUSES
            and anchor_failure_codes == [failure_code]
            and repeat_count >= 1
            and anchor_count >= 1
            and required_count == repeat_count * anchor_count
            and 0 <= matched_count < required_count
        )
        if not failure_is_consistent:
            raise RuntimeError(
                "candidate ASR locked-name failure evidence is internally inconsistent"
            )
        return True

    @classmethod
    def _prior_decodes_request_source_pronunciation(
        cls,
        evidence: list[dict[str, Any]],
    ) -> bool:
        requests = [
            cls._decode_requests_source_pronunciation(result)
            for result in evidence
        ]
        return len(requests) == 2 and all(requests)

    @staticmethod
    def _decode_is_complete_locked_name_pass(result: dict[str, Any]) -> bool:
        if str(result.get("verdict") or "") != ASR_PASS:
            return False
        anchor_metrics = result.get(LOCKED_NAME_ANCHOR_METRICS_KEY)
        result_failure_codes = result.get("failure_codes", [])
        if not isinstance(anchor_metrics, dict) or not isinstance(
            result_failure_codes,
            list,
        ):
            raise RuntimeError("candidate ASR pass lacks structured anchor evidence")
        count_fields = (
            "repeat_count",
            "anchor_count",
            "required_occurrence_count",
            "matched_occurrence_count",
        )
        if any(
            isinstance(anchor_metrics.get(field), bool)
            or not isinstance(anchor_metrics.get(field), int)
            for field in count_fields
        ):
            raise RuntimeError("candidate ASR pass has malformed anchor occurrence counts")
        repeat_count = int(anchor_metrics["repeat_count"])
        anchor_count = int(anchor_metrics["anchor_count"])
        required_count = int(anchor_metrics["required_occurrence_count"])
        matched_count = int(anchor_metrics["matched_occurrence_count"])
        pass_is_consistent = (
            result.get("passed") is True
            and isinstance(result.get("repairable"), bool)
            and not result_failure_codes
            and anchor_metrics.get("version") == LOCKED_NAME_ANCHOR_METRICS_VERSION
            and anchor_metrics.get("adjudicated") is True
            and anchor_metrics.get("passed") is True
            and str(anchor_metrics.get("status") or "") == "pass"
            and anchor_metrics.get("failure_codes") == []
            and repeat_count >= 1
            and anchor_count >= 1
            and required_count == repeat_count * anchor_count
            and matched_count == required_count
        )
        if not pass_is_consistent:
            raise RuntimeError("candidate ASR pass anchor evidence is internally inconsistent")
        return True

    @classmethod
    def _prior_source_candidate_requests_final_retry(
        cls,
        evidence: list[dict[str, Any]],
    ) -> bool:
        if len(evidence) != 2:
            return False
        variants = [
            str(result.get("pronunciation_delivery_variant") or "")
            for result in evidence
        ]
        if any(
            variant not in {
                PRONUNCIATION_DELIVERY_LOCKED,
                PRONUNCIATION_DELIVERY_SOURCE,
            }
            for variant in variants
        ):
            raise RuntimeError(
                "candidate ASR evidence has an unsupported pronunciation variant"
            )
        if any(variant != variants[0] for variant in variants):
            raise RuntimeError("candidate ASR evidence mixes pronunciation variants")
        if variants[0] != PRONUNCIATION_DELIVERY_SOURCE:
            return False
        requests = [
            cls._decode_requests_source_pronunciation(result)
            for result in evidence
        ]
        complete_passes = [
            cls._decode_is_complete_locked_name_pass(result)
            for result in evidence
        ]
        return (
            requests.count(True) == 1
            and complete_passes.count(True) == 1
            and all(
                request != complete_pass
                for request, complete_pass in zip(requests, complete_passes)
            )
        )

    @classmethod
    def _prior_source_candidate_requests_final_split(
        cls,
        evidence: list[dict[str, Any]],
    ) -> bool:
        if len(evidence) != 2:
            return False
        variants = [
            str(result.get("pronunciation_delivery_variant") or "")
            for result in evidence
        ]
        if any(
            variant not in {
                PRONUNCIATION_DELIVERY_LOCKED,
                PRONUNCIATION_DELIVERY_SOURCE,
            }
            for variant in variants
        ):
            raise RuntimeError(
                "candidate ASR evidence has an unsupported pronunciation variant"
            )
        if any(variant != variants[0] for variant in variants):
            raise RuntimeError("candidate ASR evidence mixes pronunciation variants")
        return (
            variants[0] == PRONUNCIATION_DELIVERY_SOURCE
            and all(
                cls._decode_requests_source_pronunciation(result)
                for result in evidence
            )
        )

    @staticmethod
    def _segment_candidate_split_seed_salt(
        repair_round: int,
        pronunciation_delivery_variant: str,
    ) -> str:
        return segment_candidate_split_seed_salt(
            repair_round,
            pronunciation_delivery_variant,
        )

    def _require_segment_candidate_pronunciation_delivery(
        self,
        row: Any,
        candidate: Any,
    ) -> tuple[str, str, list[dict[str, Any]]]:
        stored_variant = str(candidate["pronunciation_delivery_variant"])
        variant, spoken_text, anchors = (
            self._segment_candidate_pronunciation_delivery(
                row,
                int(candidate["repair_round"]),
                required_variant=stored_variant,
            )
        )
        spoken_text_sha256 = hashlib.sha256(spoken_text.encode("utf-8")).hexdigest()
        if (
            str(candidate["pronunciation_delivery_variant"]) != variant
            or str(candidate["expected_spoken_text_sha256"]) != spoken_text_sha256
        ):
            raise RuntimeError(
                "segment candidate pronunciation variant or spoken-text checksum drifted"
            )
        return variant, spoken_text, anchors

    @staticmethod
    def _segment_candidate_seed_salt(
        repair_round: int,
        tts_attempt: int,
        pronunciation_delivery_variant: str = PRONUNCIATION_DELIVERY_LOCKED,
    ) -> str:
        prefix = f"asr_clarity_candidate_{int(repair_round)}"
        if pronunciation_delivery_variant == PRONUNCIATION_DELIVERY_LOCKED:
            return f"{prefix}_{int(tts_attempt)}"
        return f"{prefix}_{pronunciation_delivery_variant}_{int(tts_attempt)}"

    @staticmethod
    def _segment_candidate_split_strategy(candidate: Any) -> str:
        is_final_source_candidate = (
            int(candidate["repair_round"]) + 1 == int(candidate["repair_budget"])
            and str(candidate["pronunciation_delivery_variant"])
            == PRONUNCIATION_DELIVERY_SOURCE
        )
        return (
            CLAUSE_SPLIT_STRATEGY
            if is_final_source_candidate
            else SENTENCE_SPLIT_STRATEGY
        )

    def _allocate_segment_candidate(
        self,
        row: Any,
        repair_round: int,
        max_repair_rounds: int,
        *,
        candidate_repair_requirement: str = STANDARD_CANDIDATE_GATE_REQUIREMENT,
        repair_trigger_check_id: int | None = None,
    ) -> Any:
        source_variant_requested = False
        force_clause_split = False
        prior_decode_evidence: list[dict[str, Any]] = []
        should_inspect_prior_evidence = int(repair_round) > 0 and (
            int(repair_round) % 2 == 1
            or int(repair_round) + 1 == int(max_repair_rounds)
        )
        if should_inspect_prior_evidence:
            prior_decode_evidence = (
                self.db.previous_segment_candidate_decode_evidence(
                    segment_id=int(row["id"]),
                    policy_hash=self.quality_policy_hash,
                    repair_round=int(repair_round),
                )
            )
            if int(repair_round) % 2 == 1:
                source_variant_requested = (
                    self._prior_decodes_request_source_pronunciation(
                        prior_decode_evidence
                    )
                )
            else:
                source_variant_requested = (
                    self._prior_source_candidate_requests_final_retry(
                        prior_decode_evidence
                    )
                )
                force_clause_split = (
                    not source_variant_requested
                    and self._prior_source_candidate_requests_final_split(
                        prior_decode_evidence
                    )
                )
                source_variant_requested = (
                    source_variant_requested or force_clause_split
                )
        pronunciation_variant, spoken_text, _anchors = (
            self._segment_candidate_pronunciation_delivery(
                row,
                repair_round,
                source_variant_requested=source_variant_requested,
            )
        )
        if (
            force_clause_split
            and self._clause_split_is_unavailable(spoken_text)
        ):
            force_clause_split = False
            pronunciation_variant, spoken_text, _anchors = (
                self._segment_candidate_pronunciation_delivery(
                    row,
                    repair_round,
                )
            )
        spoken_text_sha256 = hashlib.sha256(spoken_text.encode("utf-8")).hexdigest()
        tts_attempt = (
            int(self.settings["tts"]["max_retries"])
            if force_clause_split
            else 0
        )
        seed_salt = (
            self._segment_candidate_split_seed_salt(
                repair_round,
                pronunciation_variant,
            )
            if force_clause_split
            else self._segment_candidate_seed_salt(
                repair_round,
                tts_attempt,
                pronunciation_variant,
            )
        )
        return self.db.allocate_segment_candidate(
            segment_id=int(row["id"]),
            policy_hash=self.quality_policy_hash,
            repair_round=int(repair_round),
            max_repair_rounds=int(max_repair_rounds),
            incumbent_sha256=str(row["wav_sha256"] or ""),
            generation_seed=self.tts.generation_seed(row, seed_salt),
            wav_path=self._segment_candidate_path(row, repair_round),
            candidates_root=self._segment_candidate_root(),
            pronunciation_delivery_variant=pronunciation_variant,
            expected_spoken_text_sha256=spoken_text_sha256,
            tts_attempt=tts_attempt,
            generation_strategy=(
                GENERATION_STRATEGY_SPLIT
                if force_clause_split
                else GENERATION_STRATEGY_DIRECT
            ),
            perceptual_required=self._perceptual_qa_enabled(),
            candidate_repair_requirement=candidate_repair_requirement,
            repair_trigger_check_id=repair_trigger_check_id,
        )

    def _allocate_tempo_rescue_candidate(
        self,
        row: Any,
        source_candidate: Any,
        max_repair_rounds: int,
    ) -> Any:
        source = self.db.get_segment_candidate(int(source_candidate["id"]))
        if (
            str(source["postprocess_profile"]) != POSTPROCESS_PROFILE_NONE
            or int(source["repair_round"]) + 1 != int(source["repair_budget"])
        ):
            raise RuntimeError("tempo rescue source is not the final ordinary candidate")
        return self.db.allocate_segment_candidate(
            segment_id=int(row["id"]),
            policy_hash=self.quality_policy_hash,
            repair_round=int(max_repair_rounds),
            max_repair_rounds=int(max_repair_rounds),
            incumbent_sha256=str(row["wav_sha256"] or ""),
            generation_seed=int(source["generation_seed"]),
            wav_path=self._segment_candidate_path(row, max_repair_rounds),
            candidates_root=self._segment_candidate_root(),
            pronunciation_delivery_variant=str(
                source["pronunciation_delivery_variant"]
            ),
            expected_spoken_text_sha256=str(
                source["expected_spoken_text_sha256"]
            ),
            tts_attempt=int(source["tts_attempt"]),
            generation_strategy=str(source["generation_strategy"]),
            postprocess_profile=POSTPROCESS_PROFILE_TEMPO,
            postprocess_source_candidate_id=int(source["id"]),
            postprocess_source_sha256=str(source["wav_sha256"]),
            perceptual_required=bool(source["perceptual_required"]),
            candidate_repair_requirement=str(
                source["candidate_repair_requirement"]
            ),
            repair_trigger_check_id=(
                int(source["repair_trigger_check_id"])
                if source["repair_trigger_check_id"] is not None
                else None
            ),
        )

    @staticmethod
    def _clause_split_is_unavailable(spoken_text: str) -> bool:
        try:
            parts, _max_chars = split_text_for_strategy(
                spoken_text,
                CLAUSE_SPLIT_STRATEGY,
            )
        except ValueError:
            return True
        return len(parts) < 2

    def _segment_candidate_item(self, segment: Any, candidate: Any) -> dict[str, Any]:
        variant, _spoken_text, _anchors = (
            self._require_segment_candidate_pronunciation_delivery(segment, candidate)
        )
        item = dict(segment)
        candidate_signal_item = dict(segment)
        candidate_signal_item["signal_json"] = candidate["signal_json"]
        signal = self._segment_signal_provenance(candidate_signal_item)
        split_recovery = bool(signal.get("split_parts"))
        item.update(
            {
                "status": SegmentStatus.SIGNAL_PASSED.value,
                "wav_path": str(candidate["wav_path"]),
                "wav_sha256": str(candidate["wav_sha256"] or ""),
                "wav_duration": candidate["wav_duration"],
                "signal_json": candidate["signal_json"],
                "generation_seed": int(candidate["generation_seed"]),
                "generation_delivery_mode": DELIVERY_CLARITY,
                "generation_repair_round": int(candidate["repair_round"]),
                "generation_policy_hash": str(candidate["policy_hash"]),
                "segment_candidate_id": int(candidate["id"]),
                "pronunciation_delivery_variant": variant,
                "expected_spoken_text_sha256": str(
                    candidate["expected_spoken_text_sha256"]
                ),
                "warning_code": "|".join(
                    self._signal_warning_codes(
                        signal,
                        split_recovery=split_recovery,
                    )
                ),
            }
        )
        return item

    def _checkpoint_segment_candidate_signal(
        self,
        candidate: Any,
        output: Path,
        checksum: str,
        metrics: dict[str, Any],
        generation_seed: int,
    ) -> Any:
        repair_round = int(candidate["repair_round"])
        expected_variant = str(candidate["pronunciation_delivery_variant"])
        expected_spoken_sha256 = str(candidate["expected_spoken_text_sha256"])
        if (
            str(metrics.get("pronunciation_delivery_variant") or "")
            != expected_variant
            or str(metrics.get("spoken_text_sha256") or "")
            != expected_spoken_sha256
        ):
            raise RuntimeError(
                "TTS candidate signal differs from its allocated pronunciation delivery"
            )
        metrics["tts_delivery_mode"] = DELIVERY_CLARITY
        metrics[ASR_CLARITY_REPAIR_ROUND_METRIC] = repair_round
        return self.db.checkpoint_segment_candidate_signal(
            int(candidate["id"]),
            expected_generation_seed=int(generation_seed),
            wav_path=output,
            wav_sha256=checksum,
            duration=float(metrics["duration"]),
            signal=metrics,
        )

    def _process_tempo_rescue_candidate(
        self,
        row: Any,
        candidate: Any,
        chapter: Any,
    ) -> Any:
        source_candidate_id = candidate["postprocess_source_candidate_id"]
        source_sha256 = str(candidate["postprocess_source_sha256"] or "")
        if source_candidate_id is None or not source_sha256:
            raise RuntimeError("tempo rescue candidate lacks a locked source binding")
        source = self.db.get_segment_candidate(int(source_candidate_id))
        source_path = Path(str(source["wav_path"]))
        if (
            str(source["wav_sha256"] or "").casefold() != source_sha256.casefold()
            or not source_path.is_file()
            or sha256_file(source_path).casefold() != source_sha256.casefold()
        ):
            raise RuntimeError("tempo rescue source WAV no longer matches its checkpoint")
        try:
            source_signal = json.loads(str(source["signal_json"] or "{}"))
        except (TypeError, json.JSONDecodeError) as exc:
            raise RuntimeError("tempo rescue source signal metrics are invalid") from exc
        if not isinstance(source_signal, dict):
            raise RuntimeError("tempo rescue source signal metrics must be an object")
        _variant, spoken_text, _anchors = (
            self._require_segment_candidate_pronunciation_delivery(row, candidate)
        )
        output = Path(str(candidate["wav_path"]))
        try:
            checksum, transform_metrics = tempo_stretch_wav_atomic(source_path, output)
            valid, metrics, reason = inspect_wav(
                output,
                spoken_text,
                self.settings,
                segment=row,
            )
            if not valid:
                raise AudioQualityError(reason)
            for field in (
                "spoken_text_sha256",
                "pronunciation_delivery_variant",
                "voice_profile_id",
                "pitch_semitones",
                "effective_pitch_semitones",
                "pitch_variant_skipped",
                "pitch_variant_mixed",
            ):
                if field not in source_signal:
                    raise RuntimeError(
                        "tempo rescue source lacks locked signal provenance: " + field
                    )
                metrics[field] = source_signal[field]
            for field in (
                GENERATION_CEILING_METRIC,
                GENERATION_ENDPOINT_ACTIVE_METRIC,
            ):
                metrics[field] = source_signal.get(field, 0.0)
            metrics.update(transform_metrics)
            metrics.update(
                {
                    POSTPROCESS_PROFILE_FIELD: POSTPROCESS_PROFILE_TEMPO,
                    POSTPROCESS_SOURCE_CANDIDATE_ID_FIELD: int(source["id"]),
                    POSTPROCESS_SOURCE_SHA256_FIELD: source_sha256,
                }
            )
            return self._checkpoint_segment_candidate_signal(
                candidate,
                output,
                checksum,
                metrics,
                int(candidate["generation_seed"]),
            )
        except Exception as exc:  # noqa: BLE001
            failed = self.db.mark_segment_candidate_tts_failed(
                int(candidate["id"]),
                expected_generation_seed=int(candidate["generation_seed"]),
                error=f"tempo rescue failed: {exc}",
            )
            self.log(
                f"Tempo rescue candidate {row['stable_id']} failed: {exc}"
            )
            self.db.event(
                "error",
                "SEGMENT_CANDIDATE_TEMPO_RESCUE_FAILED",
                f"Immutable tempo rescue failed for {row['stable_id']}",
                {
                    "candidate_id": int(candidate["id"]),
                    "source_candidate_id": int(source["id"]),
                    "repair_round": int(candidate["repair_round"]),
                    "error": str(exc),
                    "chapter": str(chapter["title"]),
                },
            )
            return failed

    def _process_segment_candidate(
        self,
        row: Any,
        candidate: Any,
        chapter: Any,
        *,
        repair_short_utterance: bool = True,
    ) -> Any:
        candidate = self.db.get_segment_candidate(int(candidate["id"]))
        if str(candidate["state"]) != SEGMENT_CANDIDATE_GENERATING:
            return candidate
        postprocess_profile = str(candidate["postprocess_profile"])
        if postprocess_profile == POSTPROCESS_PROFILE_TEMPO:
            return self._process_tempo_rescue_candidate(row, candidate, chapter)
        if postprocess_profile != POSTPROCESS_PROFILE_NONE:
            raise RuntimeError("segment candidate has an unsupported postprocess profile")
        repair_round = int(candidate["repair_round"])
        pronunciation_variant, spoken_text, _anchors = (
            self._require_segment_candidate_pronunciation_delivery(row, candidate)
        )
        output = Path(str(candidate["wav_path"]))
        retries = int(self.settings["tts"]["max_retries"])
        current_attempt = int(candidate["tts_attempt"])
        if current_attempt > retries:
            raise RuntimeError("segment candidate TTS attempt exceeds the finite retry schedule")
        last_error = ""

        for attempt in range(current_attempt, retries):
            self._wait_pause_or_stop()
            seed_salt = self._segment_candidate_seed_salt(
                repair_round,
                attempt,
                pronunciation_variant,
            )
            expected_seed = self.tts.generation_seed(row, seed_salt)
            if int(candidate["generation_seed"]) != expected_seed:
                raise RuntimeError("segment candidate generation seed differs from its deterministic salt")
            try:
                checksum, metrics, seed = (
                    self._synthesize_atomic_with_pronunciation_variant(
                        row,
                        output,
                        pronunciation_delivery_variant=pronunciation_variant,
                        seed_salt=seed_salt,
                        repair_short_utterance=repair_short_utterance,
                        delivery_mode=DELIVERY_CLARITY,
                    )
                )
                if int(seed) != expected_seed:
                    raise RuntimeError("TTS returned a seed that differs from the candidate ledger")
                if (
                    self.settings.get("quality_profile") == "high_quality"
                    and metrics.get("pace_outlier")
                ):
                    raise AudioQualityError(
                        "high-quality TTS retry required: speech pace "
                        f"{metrics.get('chars_per_second', 0.0):.2f} chars/s"
                    )
                checkpoint = self._checkpoint_segment_candidate_signal(
                    candidate,
                    output,
                    checksum,
                    metrics,
                    seed,
                )
                self._reset_tts_failure_streak()
                return checkpoint
            except Exception as exc:  # noqa: BLE001
                if is_fatal_tts_error(exc):
                    raise RuntimeError(f"Fatal TTS engine failure: {exc}") from exc
                last_error = str(exc)
                self.log(
                    f"TTS candidate {row['stable_id']} round {repair_round + 1} "
                    f"failed attempt {attempt + 1}/{retries}: {last_error}"
                )
                if attempt + 1 < retries:
                    next_attempt = attempt + 1
                    next_salt = self._segment_candidate_seed_salt(
                        repair_round,
                        next_attempt,
                        pronunciation_variant,
                    )
                    candidate = self.db.restart_segment_candidate_generation(
                        int(candidate["id"]),
                        expected_generation_seed=int(candidate["generation_seed"]),
                        generation_seed=self.tts.generation_seed(row, next_salt),
                        tts_attempt=next_attempt,
                    )
                    time.sleep(min(8, 2**attempt))

        if is_short_utterance(spoken_text):
            last_error = f"{last_error}; split=short utterance is not splittable"
        else:
            split_attempt = retries
            split_strategy = self._segment_candidate_split_strategy(candidate)
            try:
                _split_parts, split_max_chars = split_text_for_strategy(
                    spoken_text,
                    split_strategy,
                )
            except ValueError:
                split_strategy = SENTENCE_SPLIT_STRATEGY
                _split_parts, split_max_chars = split_text_for_strategy(
                    spoken_text,
                    split_strategy,
                )
            split_seed_salt = self._segment_candidate_split_seed_salt(
                repair_round,
                pronunciation_variant,
            )
            split_seed = self.tts.generation_seed(row, split_seed_salt)
            if int(candidate["tts_attempt"]) < split_attempt:
                candidate = self.db.restart_segment_candidate_generation(
                    int(candidate["id"]),
                    expected_generation_seed=int(candidate["generation_seed"]),
                    generation_seed=split_seed,
                    tts_attempt=split_attempt,
                    generation_strategy=GENERATION_STRATEGY_SPLIT,
                )
            elif (
                int(candidate["tts_attempt"]) != split_attempt
                or int(candidate["generation_seed"]) != split_seed
            ):
                raise RuntimeError("segment candidate split checkpoint differs from its retry schedule")
            try:
                split_provenance = (
                    self._synthesize_split(
                        row,
                        output,
                        delivery_mode=DELIVERY_CLARITY,
                        seed_salt_prefix=split_seed_salt,
                        pronunciation_delivery_variant=pronunciation_variant,
                        split_strategy=split_strategy,
                    )
                    or []
                )
                valid, metrics, reason = inspect_wav(
                    output,
                    spoken_text,
                    self.settings,
                    segment=row,
                )
                if not valid:
                    raise AudioQualityError(reason)
                metrics["spoken_text_sha256"] = hashlib.sha256(
                    spoken_text.encode("utf-8")
                ).hexdigest()
                metrics["pronunciation_delivery_variant"] = pronunciation_variant
                metrics["split_checkpoint_seed"] = split_seed
                metrics["split_seed_salt_prefix"] = split_seed_salt
                metrics[SPLIT_STRATEGY_FIELD] = split_strategy
                metrics[SPLIT_MAX_CHARS_FIELD] = split_max_chars
                metrics["split_parts"] = split_provenance
                if split_provenance:
                    first_part = split_provenance[0]
                    metrics["voice_profile_id"] = first_part.get("voice_profile_id")
                    metrics["pitch_semitones"] = first_part.get("pitch_semitones")
                    effective_pitches = {
                        part.get("effective_pitch_semitones")
                        for part in split_provenance
                    }
                    metrics["effective_pitch_semitones"] = (
                        next(iter(effective_pitches))
                        if len(effective_pitches) == 1
                        else None
                    )
                    metrics["pitch_variant_mixed"] = float(len(effective_pitches) > 1)
                    metrics["pitch_variant_skipped"] = float(
                        any(part.get("pitch_variant_skipped") for part in split_provenance)
                    )
                    metrics[GENERATION_CEILING_METRIC] = float(
                        any(part.get(GENERATION_CEILING_METRIC) for part in split_provenance)
                    )
                    metrics[GENERATION_ENDPOINT_ACTIVE_METRIC] = float(
                        any(
                            part.get(GENERATION_CEILING_METRIC)
                            and part.get(GENERATION_ENDPOINT_ACTIVE_METRIC)
                            for part in split_provenance
                        )
                    )
                checkpoint = self._checkpoint_segment_candidate_signal(
                    candidate,
                    output,
                    sha256_file(output),
                    metrics,
                    split_seed,
                )
                self._reset_tts_failure_streak()
                return checkpoint
            except Exception as exc:  # noqa: BLE001
                last_error = f"{last_error}; split={exc}"

        failed = self.db.mark_segment_candidate_tts_failed(
            int(candidate["id"]),
            expected_generation_seed=int(candidate["generation_seed"]),
            error=last_error or "candidate TTS failed without a diagnostic",
        )
        self.log(
            f"TTS candidate {row['stable_id']} round {repair_round + 1} failed: {last_error}"
        )
        self.db.event(
            "error",
            "SEGMENT_CANDIDATE_TTS_FAILED",
            f"Immutable clarity candidate failed for {row['stable_id']}",
            {
                "candidate_id": int(candidate["id"]),
                "repair_round": repair_round,
                "error": last_error,
                "chapter": str(chapter["title"]),
            },
        )
        failure_streak = self._record_tts_failure(last_error)
        failure_limit = int(self.settings["tts"].get("fatal_failure_streak", 3))
        if failure_streak >= failure_limit:
            raise RuntimeError(
                f"TTS circuit breaker opened after {failure_limit} identical failures: {last_error}"
            )
        return failed

    def _process_single_segment(
        self,
        row: Any,
        chapter: Any,
        seed_salt_prefix: str = "primary",
        *,
        repair_short_utterance: bool = False,
        delivery_mode: str = DELIVERY_PRIMARY,
        asr_repair_round: int | None = None,
    ) -> None:
        output = self._chunk_path(row)
        last_error = ""
        retries = int(self.settings["tts"]["max_retries"])
        for attempt in range(retries):
            self._wait_pause_or_stop()
            try:
                seed_salt = f"{seed_salt_prefix}_{attempt}"
                self.db.mark_generating(
                    int(row["id"]),
                    self.tts.generation_seed(row, seed_salt),
                    delivery_mode=delivery_mode,
                    repair_round=asr_repair_round,
                    policy_hash=self.quality_policy_hash,
                )
                checksum, metrics, seed = self.tts.synthesize_atomic(
                    row,
                    output,
                    seed_salt=seed_salt,
                    repair_short_utterance=repair_short_utterance,
                    delivery_mode=delivery_mode,
                )
                metrics["tts_delivery_mode"] = delivery_mode
                if asr_repair_round is not None:
                    metrics[ASR_CLARITY_REPAIR_ROUND_METRIC] = int(asr_repair_round)
                if self.settings.get("quality_profile") == "high_quality":
                    retry_reasons = []
                    if metrics.get("pace_outlier"):
                        retry_reasons.append(
                            f"speech pace {metrics.get('chars_per_second', 0.0):.2f} chars/s"
                        )
                    if retry_reasons:
                        raise AudioQualityError(
                            "high-quality TTS retry required: " + "; ".join(retry_reasons)
                        )
                self.db.mark_signal_passed(
                    int(row["id"]),
                    wav_path=output,
                    wav_sha256=checksum,
                    duration=float(metrics["duration"]),
                    signal=metrics,
                    generation_seed=seed,
                    warning_codes=self._signal_warning_codes(metrics),
                )
                self._reset_tts_failure_streak()
                if metrics.get("pace_outlier"):
                    self.log(
                        f"TTS segment {row['stable_id']} lệch tốc độ mục tiêu "
                        f"({metrics['chars_per_second']:.2f} chars/s) nhưng vẫn trong giới hạn an toàn; "
                        "chuyển sang Whisper kiểm tra."
                    )
                if metrics.get("pitch_variant_skipped"):
                    self.log(
                        f"TTS segment {row['stable_id']} không thể áp dụng pitch đã khóa; "
                        "giữ waveform để QA chặn xuất bản high-quality."
                    )
                if metrics.get(GENERATION_CEILING_METRIC):
                    self.log(
                        f"TTS segment {row['stable_id']} dùng hết ngân sách frame; "
                        "giữ waveform để kiểm tra tín hiệu và Whisper thay vì tự kết luận audio sai."
                    )
                return
            except Exception as exc:  # noqa: BLE001
                if is_fatal_tts_error(exc):
                    raise RuntimeError(f"Fatal TTS engine failure: {exc}") from exc
                last_error = str(exc)
                if isinstance(exc, AudioQualityError):
                    self.log(
                        f"TTS segment {row['stable_id']} chưa đạt lần {attempt + 1}/{retries}; "
                        f"đang tạo lại: {last_error}"
                    )
                else:
                    self.log(
                        f"TTS segment {row['stable_id']} lỗi lần {attempt + 1}/{retries}: {last_error}"
                    )
                time.sleep(min(8, 2 ** attempt))

        spoken_text = self.tts.spoken_text(row)
        if is_short_utterance(spoken_text):
            last_error = f"{last_error}; split=short utterance is not splittable"
            self.log(
                f"TTS segment {row['stable_id']} đã lỗi {retries}/{retries}; "
                "không chia câu cảm thán ngắn vì sẽ làm sai nội dung."
            )
        else:
            self.log(
                f"TTS segment {row['stable_id']} đã lỗi {retries}/{retries}; "
                "đang thử chia nhỏ để cứu."
            )
            try:
                split_strategy = SENTENCE_SPLIT_STRATEGY
                _split_parts, split_max_chars = split_text_for_strategy(
                    spoken_text,
                    split_strategy,
                )
                split_seed_salt = f"{seed_salt_prefix}_split"
                split_seed = self.tts.generation_seed(row, split_seed_salt)
                self.db.mark_generating(
                    int(row["id"]),
                    split_seed,
                    delivery_mode=delivery_mode,
                    repair_round=asr_repair_round,
                    policy_hash=self.quality_policy_hash,
                )
                split_provenance = (
                    self._synthesize_split(
                        row,
                        output,
                        delivery_mode=delivery_mode,
                        seed_salt_prefix=split_seed_salt,
                        split_strategy=split_strategy,
                    )
                    or []
                )
                valid, metrics, reason = inspect_wav(
                    output,
                    spoken_text,
                    self.settings,
                    segment=row,
                )
                if not valid:
                    raise AudioQualityError(reason)
                metrics["tts_delivery_mode"] = delivery_mode
                if asr_repair_round is not None:
                    metrics[ASR_CLARITY_REPAIR_ROUND_METRIC] = int(asr_repair_round)
                metrics["spoken_text_sha256"] = hashlib.sha256(
                    spoken_text.encode("utf-8")
                ).hexdigest()
                metrics["split_checkpoint_seed"] = split_seed
                metrics["split_seed_salt_prefix"] = split_seed_salt
                metrics[SPLIT_STRATEGY_FIELD] = split_strategy
                metrics[SPLIT_MAX_CHARS_FIELD] = split_max_chars
                metrics["split_parts"] = split_provenance
                if split_provenance:
                    first_part = split_provenance[0]
                    metrics["voice_profile_id"] = first_part.get("voice_profile_id")
                    metrics["pitch_semitones"] = first_part.get("pitch_semitones")
                    effective_pitches = {
                        part.get("effective_pitch_semitones")
                        for part in split_provenance
                    }
                    metrics["effective_pitch_semitones"] = (
                        next(iter(effective_pitches))
                        if len(effective_pitches) == 1
                        else None
                    )
                    metrics["pitch_variant_mixed"] = float(len(effective_pitches) > 1)
                    metrics["pitch_variant_skipped"] = float(
                        any(part.get("pitch_variant_skipped") for part in split_provenance)
                    )
                    metrics[GENERATION_CEILING_METRIC] = float(
                        any(part.get(GENERATION_CEILING_METRIC) for part in split_provenance)
                    )
                    metrics[GENERATION_ENDPOINT_ACTIVE_METRIC] = float(
                        any(
                            part.get(GENERATION_CEILING_METRIC)
                            and part.get(GENERATION_ENDPOINT_ACTIVE_METRIC)
                            for part in split_provenance
                        )
                    )
                checksum = sha256_file(output)
                self.db.mark_signal_passed(
                    int(row["id"]), wav_path=output, wav_sha256=checksum,
                    duration=float(metrics["duration"]), signal=metrics, generation_seed=split_seed,
                    warning_codes=self._signal_warning_codes(
                        metrics,
                        split_recovery=True,
                    ),
                )
                self._reset_tts_failure_streak()
                self.log(f"Đã cứu TTS segment {row['stable_id']} bằng cách chia nhỏ.")
                return
            except Exception as exc:  # noqa: BLE001
                last_error = f"{last_error}; split={exc}"

        self.db.mark_failed(int(row["id"]), last_error)
        self.log(f"TTS segment {row['stable_id']} thất bại hoàn toàn: {last_error}")
        self.db.event(
            "error",
            "SEGMENT_TTS_FAILED",
            f"Segment {row['stable_id']} failed after all non-silent strategies",
            {"error": last_error, "chapter": str(chapter["title"]), "text": str(row["text"])},
        )
        failure_streak = self._record_tts_failure(last_error)
        failure_limit = int(self.settings["tts"].get("fatal_failure_streak", 3))
        if failure_streak >= failure_limit:
            raise RuntimeError(
                f"TTS circuit breaker opened after {failure_limit} identical failures: {last_error}"
            )

    def _synthesize_split(
        self,
        row: Any,
        output: Path,
        *,
        delivery_mode: str = DELIVERY_PRIMARY,
        seed_salt_prefix: str = "split",
        pronunciation_delivery_variant: str = PRONUNCIATION_DELIVERY_LOCKED,
        split_strategy: str = SENTENCE_SPLIT_STRATEGY,
    ) -> list[dict[str, Any]]:
        text, _anchors = self._spoken_text_with_pronunciation_variant(
            row,
            pronunciation_delivery_variant,
        )
        if len(text) < 100:
            raise AudioQualityError("segment too short to split safely")
        pieces, _split_max_chars = split_text_for_strategy(text, split_strategy)
        if len(pieces) < 2:
            raise AudioQualityError("split produced fewer than two pieces")
        if " ".join(pieces) != text:
            raise RuntimeError("configured split changed the spoken text")
        part_paths: list[Path] = []
        part_provenance: list[dict[str, Any]] = []
        try:
            for index, piece in enumerate(pieces):
                part_row = dict(row)
                part_row["text"] = piece
                part_row["stable_id"] = f"{row['stable_id']}_part{index:02d}"
                expected_part_text, _part_anchors = (
                    self._spoken_text_with_pronunciation_variant(
                        part_row,
                        pronunciation_delivery_variant,
                    )
                )
                if expected_part_text != piece:
                    raise RuntimeError(
                        "split part pronunciation materialization changed its boundary text"
                    )
                expected_part_sha256 = hashlib.sha256(
                    expected_part_text.encode("utf-8")
                ).hexdigest()
                part_path = output.with_name(output.stem + f".split{index:02d}.wav")
                part_paths.append(part_path)
                part_seed_salt = f"{seed_salt_prefix}_part_{index}"
                expected_part_seed = self.tts.generation_seed(
                    part_row,
                    part_seed_salt,
                )
                _checksum, part_metrics, part_seed = (
                    self._synthesize_atomic_with_pronunciation_variant(
                        part_row,
                        part_path,
                        pronunciation_delivery_variant=(
                            pronunciation_delivery_variant
                        ),
                        seed_salt=part_seed_salt,
                        delivery_mode=delivery_mode,
                    )
                )
                if (
                    isinstance(part_seed, bool)
                    or not isinstance(part_seed, int)
                    or part_seed != expected_part_seed
                ):
                    raise RuntimeError(
                        "split part generation seed differs from its deterministic salt"
                    )
                if (
                    str(
                        part_metrics.get("pronunciation_delivery_variant") or ""
                    )
                    != pronunciation_delivery_variant
                    or str(part_metrics.get("spoken_text_sha256") or "")
                    != expected_part_sha256
                ):
                    raise RuntimeError(
                        "split part TTS provenance differs from its pronunciation materialization"
                    )
                part_provenance.append(
                    {
                        "index": index,
                        "generation_seed": part_seed,
                        "spoken_text_sha256": part_metrics.get("spoken_text_sha256"),
                        "pronunciation_delivery_variant": part_metrics.get(
                            "pronunciation_delivery_variant",
                            pronunciation_delivery_variant,
                        ),
                        "voice_profile_id": part_metrics.get("voice_profile_id"),
                        "pitch_semitones": part_metrics.get("pitch_semitones"),
                        "effective_pitch_semitones": part_metrics.get(
                            "effective_pitch_semitones"
                        ),
                        "pitch_variant_skipped": part_metrics.get(
                            "pitch_variant_skipped",
                            0.0,
                        ),
                        GENERATION_CEILING_METRIC: part_metrics.get(
                            GENERATION_CEILING_METRIC,
                            0.0,
                        ),
                        GENERATION_ENDPOINT_ACTIVE_METRIC: part_metrics.get(
                            GENERATION_ENDPOINT_ACTIVE_METRIC,
                            0.0,
                        ),
                        "delivery_mode": part_metrics.get(
                            "tts_delivery_mode",
                            delivery_mode,
                        ),
                    }
                )
            merge_wav_parts_atomic(part_paths, output, text, self.settings, segment=row)
            return part_provenance
        finally:
            for path in part_paths:
                path.unlink(missing_ok=True)

    def _spoken_text_and_anchors(
        self,
        item: dict[str, Any],
    ) -> tuple[str, list[dict[str, Any]]]:
        signal = self._segment_signal_provenance(item)
        variant = str(
            item.get("pronunciation_delivery_variant")
            or signal.get("pronunciation_delivery_variant")
            or PRONUNCIATION_DELIVERY_LOCKED
        )
        spoken_text, anchors = self._spoken_text_with_pronunciation_variant(
            item,
            variant,
        )
        spoken_text_sha256 = hashlib.sha256(spoken_text.encode("utf-8")).hexdigest()
        expected_sha256 = str(
            item.get("expected_spoken_text_sha256")
            or signal.get("spoken_text_sha256")
            or ""
        )
        if expected_sha256 and spoken_text_sha256 != expected_sha256:
            raise RuntimeError(
                "spoken-text checksum drifted before candidate or final verification"
            )
        return spoken_text, anchors

    def _decode_audio_candidate(
        self,
        item: dict[str, Any],
        verifier: WhisperVerifier,
        *,
        confirmation: bool,
        repair_round: int | None,
        delivery_mode: str,
        evidence_sink: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        expected_text, locked_name_anchors = self._spoken_text_and_anchors(item)
        wav_path = Path(str(item["wav_path"]))
        direct = verifier.verify(
            expected_text,
            wav_path,
            confirmation=confirmation,
        )
        direct = adjudicate_locked_name_anchors(
            expected_text,
            direct,
            locked_name_anchors,
            min_similarity=float(self.settings["asr"]["min_similarity"]),
            max_wer=float(self.settings["asr"]["max_wer"]),
        )
        repeated: dict[str, Any] | None = None
        collapsed_repeated: dict[str, Any] | None = None
        selected = direct
        selected_context = "direct"
        if _asr_verdict(direct) != ASR_PASS and verifier.can_verify_repeated_short(
            expected_text
        ):
            repeated_raw = verifier.verify_repeated_short(
                expected_text,
                wav_path,
                confirmation=confirmation,
            )
            repeated = adjudicate_locked_name_anchors(
                expected_text,
                repeated_raw,
                locked_name_anchors,
                repeat_count=SHORT_CONTEXT_REPEAT_COUNT,
                min_similarity=float(self.settings["asr"]["min_similarity"]),
                max_wer=float(self.settings["asr"]["max_wer"]),
            )
            if _asr_verdict(repeated) == ASR_PASS:
                selected = repeated
                selected_context = "repeat3"
            else:
                collapsed_repeated = adjudicate_collapsed_repeated_short(
                    expected_text,
                    repeated_raw,
                    locked_name_anchors,
                    requested_repeat_count=SHORT_CONTEXT_REPEAT_COUNT,
                    min_similarity=float(self.settings["asr"]["min_similarity"]),
                    max_wer=float(self.settings["asr"]["max_wer"]),
                )
                if (
                    collapsed_repeated is not None
                    and _asr_verdict(collapsed_repeated) == ASR_PASS
                ):
                    selected = collapsed_repeated
                    selected_context = COLLAPSED_SHORT_CONTEXT_MODE

        candidates = [("direct", direct)]
        if repeated is not None:
            candidates.append(("repeat3", repeated))
        if collapsed_repeated is not None:
            candidates.append((COLLAPSED_SHORT_CONTEXT_MODE, collapsed_repeated))
        selected_evidence: dict[str, Any] | None = None
        for context_mode, candidate in candidates:
            evidence = self._record_segment_asr_decode_evidence(
                item,
                candidate,
                confirmation=confirmation,
                context_mode=context_mode,
                selected=context_mode == selected_context,
                repair_round=repair_round,
                delivery_mode=delivery_mode,
            )
            if evidence_sink is not None:
                evidence_sink.append(evidence)
            if context_mode == selected_context:
                selected_evidence = evidence
        if selected_evidence is None:
            raise RuntimeError("selected ASR decode evidence was not recorded")
        return {
            **selected,
            "selected_context_mode": selected_context,
            "confirmation_decode": confirmation,
            "selected_quality_check_id": int(selected_evidence["quality_check_id"]),
        }

    def _verify_chapter_audio(self, chapter: Any, verifier: WhisperVerifier) -> None:
        chapter_id = int(chapter["id"])
        rows = self.db.list_segments(chapter_id=chapter_id)
        pending: list[dict[str, Any]] = []
        last_results: dict[int, dict[str, Any]] = {}
        decode_histories: dict[tuple[int, str], list[dict[str, Any]]] = {}
        for row in rows:
            if str(row["status"]) == SegmentStatus.FAILED.value:
                continue
            if self._existing_segment_is_safe(row):
                continue
            if str(row["status"]) != SegmentStatus.SIGNAL_PASSED.value or not row["wav_path"]:
                self.db.mark_failed(int(row["id"]), "No signal-validated WAV available for ASR")
                continue
            pending.append(dict(row))

        def artifact_history(item: dict[str, Any]) -> list[dict[str, Any]]:
            key = (int(item["id"]), str(item.get("wav_sha256") or ""))
            return decode_histories.setdefault(key, [])

        def delivery_mode_for(item: dict[str, Any]) -> str:
            signal = self._segment_signal_provenance(item)
            mode = str(signal.get("tts_delivery_mode") or DELIVERY_PRIMARY).strip().casefold()
            return DELIVERY_CLARITY if mode == DELIVERY_CLARITY else DELIVERY_PRIMARY

        def completed_clarity_round(item: dict[str, Any]) -> int:
            signal = self._segment_signal_provenance(item)
            try:
                return max(-1, int(signal.get(ASR_CLARITY_REPAIR_ROUND_METRIC, -1)))
            except (TypeError, ValueError):
                return -1

        def aggregate_decode_failures(
            results: list[dict[str, Any]],
        ) -> dict[str, Any]:
            failed = [result for result in results if _asr_verdict(result) != ASR_PASS]
            if not failed:
                return dict(results[-1])
            anchor_failed = [
                result
                for result in failed
                if isinstance(result.get(LOCKED_NAME_ANCHOR_METRICS_KEY), dict)
                and result[LOCKED_NAME_ANCHOR_METRICS_KEY].get("passed") is False
            ]
            mismatches = [
                result for result in failed if _asr_verdict(result) == ASR_MISMATCH
            ]
            endpoint_failed = [
                result for result in failed if bool(result.get("endpoint_repair"))
            ]
            selected = (
                endpoint_failed[-1]
                if endpoint_failed
                else anchor_failed[-1]
                if anchor_failed
                else mismatches[-1]
                if mismatches
                else failed[-1]
            )
            failure_codes: list[str] = []
            failure_reasons: list[str] = []
            for result in failed:
                reason = str(result.get("reason", "ASR_INCONCLUSIVE"))
                if reason not in failure_reasons:
                    failure_reasons.append(reason)
                for code in result.get("failure_codes", []):
                    normalized_code = str(code).strip()
                    if normalized_code and normalized_code not in failure_codes:
                        failure_codes.append(normalized_code)
                anchor_metrics = result.get(LOCKED_NAME_ANCHOR_METRICS_KEY)
                if isinstance(anchor_metrics, dict):
                    for code in anchor_metrics.get("failure_codes", []):
                        normalized_code = str(code).strip()
                        if normalized_code and normalized_code not in failure_codes:
                            failure_codes.append(normalized_code)
                if reason not in failure_codes:
                    failure_codes.append(reason)
            combined = {
                **selected,
                "failure_codes": failure_codes,
                "decode_failure_reasons": failure_reasons,
                "endpoint_repair": bool(endpoint_failed),
            }
            if anchor_failed:
                combined[LOCKED_NAME_ANCHOR_METRICS_KEY] = anchor_failed[-1][
                    LOCKED_NAME_ANCHOR_METRICS_KEY
                ]
            return combined

        def decode_candidate(
            item: dict[str, Any],
            *,
            confirmation: bool,
            repair_round: int | None,
            delivery_mode: str,
        ) -> dict[str, Any]:
            return self._decode_audio_candidate(
                item,
                verifier,
                confirmation=confirmation,
                repair_round=repair_round,
                delivery_mode=delivery_mode,
                evidence_sink=artifact_history(item),
            )

        def require_endpoint_repair(
            item: dict[str, Any],
            result: dict[str, Any],
        ) -> dict[str, Any]:
            if not self._ceiling_endpoint_requires_repair(item):
                return result
            self.log(
                f"TTS segment {item['stable_id']} đã qua Whisper nhưng chạm trần khi "
                "endpoint còn hoạt động; bắt buộc tạo lại để tránh audio bị cắt."
            )
            return {
                **result,
                "passed": False,
                "verdict": ASR_MISMATCH,
                "reason": ACTIVE_CEILING_ENDPOINT_REPAIR_REASON,
                "repairable": True,
                "severe": False,
                "endpoint_repair": True,
            }

        def commit_pass(
            item: dict[str, Any],
            result: dict[str, Any],
            *,
            confirmation: bool,
        ) -> None:
            segment_id = int(item["id"])
            existing_warning = str(item.get("warning_code") or "") or None
            self.db.mark_asr_result(
                segment_id,
                passed=True,
                transcript=str(result["transcript"]),
                similarity=float(result["similarity"]),
                wer=float(result["wer"]),
            )
            self._record_segment_audio_pass(
                item,
                result,
                confirmation=confirmation,
                decode_evidence=artifact_history(item),
            )
            self.db.mark_verified(segment_id, warning_code=existing_warning)

        def verify_rows(
            items: list[dict[str, Any]],
            label: str,
            *,
            confirmation: bool = False,
            repair_round: int | None = None,
        ) -> list[dict[str, Any]]:
            issues: list[dict[str, Any]] = []
            self._progress(label, 0, len(items))
            for index, item in enumerate(items, 1):
                self._resource_gate(
                    f"Whisper chapter {chapter['chapter_index']} segment {item['seq']}",
                    release_active=verifier.unload,
                )
                result = decode_candidate(
                    item,
                    confirmation=confirmation,
                    repair_round=repair_round,
                    delivery_mode=delivery_mode_for(item),
                )
                result = require_endpoint_repair(item, result)
                last_results[int(item["id"])] = result
                if _asr_verdict(result) == ASR_PASS:
                    commit_pass(item, result, confirmation=confirmation)
                else:
                    issues.append(item)
                self._progress(label, index, len(items))
            return issues

        def confirm_repair_candidates(
            candidates: list[dict[str, Any]],
            label: str,
        ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
            needs_confirmation: list[dict[str, Any]] = []
            rejected: list[dict[str, Any]] = []
            confirmed: list[dict[str, Any]] = []
            initial_results: dict[int, dict[str, Any]] = {}
            for item in candidates:
                result = last_results.get(int(item["id"]), {})
                if bool(result.get("endpoint_repair")):
                    confirmed.append(item)
                elif _asr_verdict(result) in {ASR_MISMATCH, ASR_INCONCLUSIVE}:
                    needs_confirmation.append(item)
                    initial_results[int(item["id"])] = dict(result)
                else:
                    rejected.append(item)
            confirmed_issues = (
                verify_rows(needs_confirmation, label, confirmation=True)
                if needs_confirmation
                else []
            )
            for item in confirmed_issues:
                segment_id = int(item["id"])
                first_result = initial_results.get(segment_id, {})
                result = last_results.get(segment_id, {})
                first_verdict = _asr_verdict(first_result)
                second_verdict = _asr_verdict(result)
                if bool(result.get("endpoint_repair")):
                    confirmed.append(item)
                elif ASR_MISMATCH in {first_verdict, second_verdict}:
                    mismatch_result = aggregate_decode_failures(
                        [first_result, result]
                    )
                    last_results[segment_id] = {
                        **mismatch_result,
                        "passed": False,
                        "verdict": ASR_MISMATCH,
                        "repairable": True,
                        "confirmation_verdicts": [first_verdict, second_verdict],
                    }
                    confirmed.append(item)
                else:
                    inconclusive_result = aggregate_decode_failures(
                        [first_result, result]
                    )
                    last_results[segment_id] = {
                        **inconclusive_result,
                        "passed": False,
                        "verdict": ASR_INCONCLUSIVE,
                        "repairable": False,
                        "confirmation_verdicts": [first_verdict, second_verdict],
                    }
                    rejected.append(item)
            return confirmed, rejected

        def verify_clarity_rows(
            items: list[dict[str, Any]],
            label: str,
            *,
            repair_round: int | None,
        ) -> list[dict[str, Any]]:
            remaining: list[dict[str, Any]] = []
            self._progress(label, 0, len(items))
            for index, item in enumerate(items, 1):
                artifact_history(item).clear()
                item_repair_round = (
                    completed_clarity_round(item)
                    if repair_round is None
                    else repair_round
                )
                self._resource_gate(
                    f"Whisper clarity chapter {chapter['chapter_index']} segment {item['seq']}",
                    release_active=verifier.unload,
                )
                beam_result = decode_candidate(
                    item,
                    confirmation=False,
                    repair_round=item_repair_round,
                    delivery_mode=DELIVERY_CLARITY,
                )
                greedy_result = decode_candidate(
                    item,
                    confirmation=True,
                    repair_round=item_repair_round,
                    delivery_mode=DELIVERY_CLARITY,
                )
                beam_verdict = _asr_verdict(beam_result)
                greedy_verdict = _asr_verdict(greedy_result)
                if self._ceiling_endpoint_requires_repair(item):
                    result = {
                        **aggregate_decode_failures(
                            [
                                beam_result,
                                require_endpoint_repair(item, greedy_result),
                            ]
                        ),
                        "dual_decode_required": True,
                        "dual_decode_passed": False,
                        "confirmation_verdicts": [beam_verdict, greedy_verdict],
                    }
                elif beam_verdict == ASR_PASS and greedy_verdict == ASR_PASS:
                    result = {
                        **greedy_result,
                        "dual_decode_required": True,
                        "dual_decode_passed": True,
                        "confirmation_verdicts": [beam_verdict, greedy_verdict],
                    }
                    last_results[int(item["id"])] = result
                    commit_pass(item, result, confirmation=True)
                    self._progress(label, index, len(items))
                    continue
                else:
                    selected_failure = aggregate_decode_failures(
                        [beam_result, greedy_result]
                    )
                    result = {
                        **selected_failure,
                        "passed": False,
                        "dual_decode_required": True,
                        "dual_decode_passed": False,
                        "confirmation_verdicts": [beam_verdict, greedy_verdict],
                    }
                last_results[int(item["id"])] = result
                remaining.append(item)
                self._progress(label, index, len(items))
            return remaining

        def current_repair_trigger(item: dict[str, Any]) -> Any | None:
            check = self.db.latest_quality_check(
                scope=QUALITY_SCOPE_SEGMENT,
                stage=SEGMENT_AUDIO_QUALITY_STAGE,
                segment_id=int(item["id"]),
            )
            if not (
                check is not None
                and str(check["artifact_sha256"] or "") == str(item.get("wav_sha256") or "")
                and str(check["policy_hash"]) == self.quality_policy_hash
                and str(check["verdict"]) == QUALITY_VERDICT_REPAIR
            ):
                return None
            return check

        def trigger_result(check: Any) -> dict[str, Any]:
            try:
                metrics = json.loads(str(check["metrics_json"] or "{}"))
            except (TypeError, json.JSONDecodeError) as exc:
                raise RuntimeError("ASR repair trigger metrics are corrupt") from exc
            if not isinstance(metrics, dict):
                raise RuntimeError("ASR repair trigger metrics must be an object")
            return metrics

        verification_label = f"Kiểm tra phát âm chapter {chapter['chapter_index']}"
        repair_targets: dict[int, dict[str, Any]] = {}
        primary_pending: list[dict[str, Any]] = []
        legacy_clarity_pending: list[dict[str, Any]] = []
        for item in pending:
            trigger = current_repair_trigger(item)
            if trigger is not None:
                result = trigger_result(trigger)
                segment_id = int(item["id"])
                last_results[segment_id] = result
                stored_evidence = result.get("decode_evidence", [])
                if isinstance(stored_evidence, list):
                    artifact_history(item).extend(
                        evidence for evidence in stored_evidence if isinstance(evidence, dict)
                    )
                repair_targets[segment_id] = {
                    "item": item,
                    "trigger_quality_check_id": int(trigger["id"]),
                }
            elif delivery_mode_for(item) == DELIVERY_CLARITY:
                legacy_clarity_pending.append(item)
            else:
                primary_pending.append(item)

        issues = verify_rows(primary_pending, verification_label)
        legacy_clarity_mismatches = verify_clarity_rows(
            legacy_clarity_pending,
            f"Xác nhận clarity legacy chapter {chapter['chapter_index']}",
            repair_round=None,
        )
        mismatches, unrepairable = confirm_repair_candidates(
            issues,
            f"Xác nhận lệch nội dung chapter {chapter['chapter_index']}",
        )
        final_mismatches: list[dict[str, Any]] = list(unrepairable)
        for item in [*mismatches, *legacy_clarity_mismatches]:
            segment_id = int(item["id"])
            result = last_results.get(segment_id, {})
            trigger_id = self._record_segment_audio_gate(
                item,
                result,
                verdict=QUALITY_VERDICT_REPAIR,
                confirmation=bool(result.get("confirmation_decode", True)),
                decode_evidence=artifact_history(item),
                repair_action="generate_immutable_clarity_candidate",
            )
            repair_targets[segment_id] = {
                "item": item,
                "trigger_quality_check_id": trigger_id,
            }

        repair_rounds = int(self.settings["asr"].get("repair_rounds", 2))
        maximum_state_iterations = max(8, repair_rounds * 6 + 8)
        for _state_iteration in range(maximum_state_iterations):
            if not repair_targets:
                break
            self.db.reconcile_segment_candidate_artifacts(self.quality_policy_hash)
            generation_jobs: list[tuple[dict[str, Any], Any]] = []
            beam_jobs: list[tuple[dict[str, Any], Any]] = []
            greedy_jobs: list[tuple[dict[str, Any], Any]] = []
            perceptual_jobs: list[tuple[dict[str, Any], Any]] = []
            promotion_jobs: list[tuple[dict[str, Any], Any]] = []
            completed_ids: list[int] = []
            progressed = False

            for segment_id, context in list(repair_targets.items()):
                item = dict(self.db.get_segment(segment_id))
                context["item"] = item
                plan = self.db.segment_candidate_resume_plan(
                    segment_id,
                    self.quality_policy_hash,
                    repair_rounds,
                )
                action = str(plan["action"])
                if action == "allocate":
                    repair_item = self._checkpoint_short_ceiling_repair(item)
                    candidate = self._allocate_segment_candidate(
                        repair_item,
                        int(plan["repair_round"]),
                        repair_rounds,
                    )
                    generation_jobs.append((repair_item, candidate))
                    progressed = True
                elif action == "allocate_postprocess":
                    source_candidate = self.db.get_segment_candidate(
                        int(plan[POSTPROCESS_SOURCE_CANDIDATE_ID_FIELD])
                    )
                    candidate = self._allocate_tempo_rescue_candidate(
                        item,
                        source_candidate,
                        repair_rounds,
                    )
                    generation_jobs.append((item, candidate))
                    progressed = True
                elif action == "generate":
                    repair_item = self._checkpoint_short_ceiling_repair(item)
                    generation_jobs.append(
                        (
                            repair_item,
                            self.db.get_segment_candidate(int(plan["candidate_id"])),
                        )
                    )
                elif action == "decode_beam":
                    beam_jobs.append(
                        (item, self.db.get_segment_candidate(int(plan["candidate_id"])))
                    )
                elif action == "decode_greedy":
                    greedy_jobs.append(
                        (item, self.db.get_segment_candidate(int(plan["candidate_id"])))
                    )
                elif action == "verify_perceptual":
                    perceptual_jobs.append(
                        (item, self.db.get_segment_candidate(int(plan["candidate_id"])))
                    )
                elif action == "promote":
                    promotion_jobs.append(
                        (item, self.db.get_segment_candidate(int(plan["candidate_id"])))
                    )
                elif action == "exhausted":
                    candidate_attempts = self.db.segment_candidate_attempt_summary(
                        segment_id,
                        self.quality_policy_hash,
                    )
                    result = last_results.get(segment_id, {})
                    verdict = _asr_verdict(result)
                    reason = str(result.get("reason", "ASR_MISMATCH"))
                    perceptual_review_exhausted = (
                        _candidate_budget_exhausted_on_perceptual_review(
                            candidate_attempts
                        )
                    )
                    locked_name_review = bool(
                        result.get("locked_name_review_eligible")
                    ) and reason == ASR_LOCKED_NAME_ANCHOR_MISMATCH
                    if locked_name_review:
                        # Whisper kept spelling a correctly pronounced foreign name in
                        # Latin script. That is review evidence, not proof of a bad
                        # take, so the segment publishes carrying the warning instead
                        # of blocking its chapter forever.
                        warning = ASR_LOCKED_NAME_ANCHOR_REVIEW
                        error = (
                            "Locked-name pronunciation needs a listen; ordinary "
                            "content passed its canonical thresholds"
                        )
                        final_verdict = QUALITY_VERDICT_PASS
                        failure_codes = ()
                    elif perceptual_review_exhausted:
                        warning = PERCEPTUAL_NATURALNESS_REVIEW_CODE
                        error = (
                            "Perceptual naturalness review remained after all "
                            "immutable repair candidates"
                        )
                        final_verdict = QUALITY_VERDICT_FAIL
                        failure_codes = (PERCEPTUAL_NATURALNESS_REVIEW_CODE,)
                    else:
                        warning = (
                            reason
                            if verdict == ASR_INCONCLUSIVE
                            or reason
                            in {
                                ACTIVE_CEILING_ENDPOINT_REPAIR_REASON,
                                ASR_LOCKED_NAME_ANCHOR_MISMATCH,
                            }
                            else "ASR_MISMATCH_UNRESOLVED"
                        )
                        error = (
                            "ASR could not produce a trustworthy verdict after "
                            "immutable repairs"
                            if verdict == ASR_INCONCLUSIVE
                            else "ASR mismatch remained after all immutable repair candidates"
                        )
                        final_verdict = (
                            ASR_INCONCLUSIVE
                            if verdict == ASR_INCONCLUSIVE
                            else QUALITY_VERDICT_FAIL
                        )
                        failure_codes = tuple(
                            str(code)
                            for code in result.get("failure_codes", [])
                            if str(code).strip()
                        )
                    self.db.finalize_segment_candidate_exhaustion(
                        segment_id=segment_id,
                        policy_hash=self.quality_policy_hash,
                        max_repair_rounds=repair_rounds,
                        incumbent_sha256=str(item["wav_sha256"]),
                        trigger_quality_check_id=int(context["trigger_quality_check_id"]),
                        error=error,
                        warning_code=warning,
                        final_verdict=final_verdict,
                        failure_codes=failure_codes,
                        publish_with_review=locked_name_review,
                    )
                    self.db.event(
                        "warning" if locked_name_review else "error",
                        warning,
                        f"Immutable clarity repair budget exhausted for {item['stable_id']}",
                        {
                            "chapter": str(chapter["title"]),
                            "segment_id": segment_id,
                            "incumbent_sha256": str(item["wav_sha256"]),
                            "candidate_attempts": candidate_attempts,
                        },
                    )
                    completed_ids.append(segment_id)
                    progressed = True
                elif action == "complete":
                    completed_ids.append(segment_id)
                    progressed = True
                elif action in {"stale_policy", "stale_incumbent"}:
                    raise RuntimeError(
                        f"segment candidate resume refused {action} for segment {segment_id}"
                    )
                else:
                    raise RuntimeError(f"unsupported segment candidate resume action: {action}")

            for segment_id in completed_ids:
                repair_targets.pop(segment_id, None)

            if generation_jobs:
                verifier.unload()
                self.perceptual_qa.unload()
                repair_label = f"Tạo candidate clarity chapter {chapter['chapter_index']}"
                self._progress(repair_label, 0, len(generation_jobs))
                for index, (item, candidate) in enumerate(generation_jobs, 1):
                    self._resource_gate(
                        f"candidate clarity chapter {chapter['chapter_index']} segment {item['seq']}",
                        keep_engine=None,
                    )
                    self._process_segment_candidate(item, candidate, chapter)
                    self._progress(repair_label, index, len(generation_jobs))
                self.tts.unload_all()
                progressed = True
                continue

            if beam_jobs or greedy_jobs:
                self.tts.unload_all()
                decode_jobs = [
                    *[(False, item, candidate) for item, candidate in beam_jobs],
                    *[(True, item, candidate) for item, candidate in greedy_jobs],
                ]
                decode_label = f"Kiểm tra candidate clarity chapter {chapter['chapter_index']}"
                self._progress(decode_label, 0, len(decode_jobs))
                for index, (confirmation, segment, candidate) in enumerate(decode_jobs, 1):
                    candidate_item = self._segment_candidate_item(segment, candidate)
                    self._resource_gate(
                        f"Whisper candidate chapter {chapter['chapter_index']} segment {segment['seq']}",
                        release_active=verifier.unload,
                    )
                    result = decode_candidate(
                        candidate_item,
                        confirmation=confirmation,
                        repair_round=int(candidate["repair_round"]),
                        delivery_mode=DELIVERY_CLARITY,
                    )
                    checkpoint = self.db.checkpoint_segment_candidate_decode(
                        int(candidate["id"]),
                        quality_check_id=int(result["selected_quality_check_id"]),
                        confirmation=confirmation,
                    )
                    segment_id = int(segment["id"])
                    if confirmation:
                        beam_result = json.loads(str(checkpoint["beam_result_json"] or "{}"))
                        beam_verdict = _asr_verdict(beam_result)
                        greedy_verdict = _asr_verdict(result)
                        if str(checkpoint["state"]) == SEGMENT_CANDIDATE_DUAL_PASSED:
                            combined_result = {
                                **result,
                                "dual_decode_required": True,
                                "dual_decode_passed": True,
                                "confirmation_verdicts": [beam_verdict, greedy_verdict],
                            }
                        else:
                            combined_result = {
                                **aggregate_decode_failures([beam_result, result]),
                                "passed": False,
                                "dual_decode_required": True,
                                "dual_decode_passed": False,
                                "confirmation_verdicts": [beam_verdict, greedy_verdict],
                            }
                        last_results[segment_id] = combined_result
                    else:
                        last_results[segment_id] = result
                    self._progress(decode_label, index, len(decode_jobs))
                progressed = True
                continue

            if perceptual_jobs:
                verifier.unload()
                perceptual_label = (
                    f"Perceptual QA candidate clarity chapter {chapter['chapter_index']}"
                )
                self._progress(perceptual_label, 0, len(perceptual_jobs))
                for index, (segment, candidate) in enumerate(perceptual_jobs, 1):
                    self._verify_segment_candidate_perceptual(
                        segment,
                        candidate,
                        chapter,
                    )
                    self._progress(perceptual_label, index, len(perceptual_jobs))
                progressed = True
                continue

            if promotion_jobs:
                for segment, candidate in promotion_jobs:
                    candidate_item = self._segment_candidate_item(segment, candidate)
                    signal_valid, _signal_metrics = self._inspect_existing_segment(candidate_item)
                    if not signal_valid:
                        self.db.mark_segment_candidate_invalid(
                            int(candidate["id"]),
                            expected_wav_sha256=str(candidate["wav_sha256"]),
                            reason="candidate failed signal validation immediately before promotion",
                        )
                        progressed = True
                        continue
                    signal = self._segment_signal_provenance(candidate_item)
                    warning_code = "|".join(
                        self._signal_warning_codes(
                            signal,
                            split_recovery=bool(signal.get("split_parts")),
                        )
                    ) or None
                    promoted = self.db.promote_segment_candidate(
                        int(candidate["id"]),
                        validated_wav_sha256=str(candidate["wav_sha256"]),
                        repair_action="promote_dual_decode_clarity_candidate",
                        attempt=self._next_segment_quality_attempt(int(segment["id"])),
                        warning_code=warning_code,
                    )
                    if str(promoted["state"]) == SEGMENT_CANDIDATE_PROMOTED:
                        repair_targets.pop(int(segment["id"]), None)
                        self.db.event(
                            "info",
                            "SEGMENT_CANDIDATE_PROMOTED",
                            f"Immutable clarity candidate promoted for {segment['stable_id']}",
                            {
                                "candidate_id": int(candidate["id"]),
                                "repair_round": int(candidate["repair_round"]),
                                "wav_sha256": str(candidate["wav_sha256"]),
                            },
                        )
                    progressed = True
                continue

            if not progressed:
                raise RuntimeError("segment candidate state machine made no progress")
        else:
            raise RuntimeError("segment candidate state machine exceeded its finite transition budget")

        if repair_targets:
            raise RuntimeError("segment candidate state machine stopped with unfinished repairs")
        for item in sorted(final_mismatches, key=lambda row: int(row["seq"])):
            result = last_results.get(int(item["id"]), {})
            verdict = _asr_verdict(result)
            reason = str(result.get("reason", "ASR_INCONCLUSIVE"))
            if (
                reason == ASR_LOCKED_NAME_ANCHOR_MISMATCH
                and bool(result.get("locked_name_review_eligible"))
            ):
                # The repair budget is spent and the name still does not match the
                # transcript's spelling, but the canonical sentence metrics - measured
                # with the name spans removed - are inside their thresholds. Whisper's
                # choice of spelling for a foreign name read with Vietnamese phonemes
                # is not proof of mispronunciation, so this publishes with review
                # evidence rather than blocking the chapter forever.
                segment_id = int(item["id"])
                self.db.mark_asr_result(
                    segment_id,
                    passed=True,
                    transcript=str(result.get("transcript", "")),
                    similarity=float(result.get("similarity", 0.0)),
                    wer=float(result.get("wer", 1.0)),
                    warning_code=ASR_LOCKED_NAME_ANCHOR_REVIEW,
                )
                self._record_segment_audio_gate(
                    item,
                    result,
                    verdict=QUALITY_VERDICT_PASS,
                    confirmation=bool(result.get("confirmation_decode", False)),
                    decode_evidence=artifact_history(item),
                )
                self.db.mark_verified(
                    segment_id,
                    warning_code=ASR_LOCKED_NAME_ANCHOR_REVIEW,
                )
                self.db.event(
                    "warning",
                    ASR_LOCKED_NAME_ANCHOR_REVIEW,
                    f"Locked-name pronunciation needs a listen for {item['stable_id']}",
                    {
                        "segment_id": segment_id,
                        "similarity": float(result.get("similarity", 0.0)),
                        "wer": float(result.get("wer", 1.0)),
                        "transcript": str(result.get("transcript", ""))[:400],
                        "anchors": [
                            {
                                "surface": anchor.get("matched_surface"),
                                "spoken_form": anchor.get("canonical_spoken_form"),
                                "heard": anchor.get("aligned_tokens"),
                            }
                            for anchor in (
                                result.get(LOCKED_NAME_ANCHOR_METRICS_KEY) or {}
                            ).get("anchors", [])
                            if not anchor.get("matched")
                        ],
                    },
                )
                continue
            warning = (
                reason
                if verdict == ASR_INCONCLUSIVE
                or reason
                in {
                    ACTIVE_CEILING_ENDPOINT_REPAIR_REASON,
                    ASR_LOCKED_NAME_ANCHOR_MISMATCH,
                }
                else "ASR_MISMATCH_UNRESOLVED"
            )
            severe = bool(result.get("severe", False))
            if severe:
                warning = "ASR_SEVERE_MISMATCH"
            if bool(result.get("artifact_valid_for_asr_gate", True)):
                self._record_segment_audio_gate(
                    item,
                    result,
                    verdict=(
                        ASR_INCONCLUSIVE
                        if verdict == ASR_INCONCLUSIVE
                        else QUALITY_VERDICT_FAIL
                    ),
                    confirmation=bool(result.get("confirmation_decode", False)),
                    decode_evidence=artifact_history(item),
                )
            self.db.mark_asr_result(
                int(item["id"]), passed=False, transcript=str(result.get("transcript", "")),
                similarity=float(result.get("similarity", 0.0)), wer=float(result.get("wer", 1.0)),
                warning_code=warning,
            )
            self.db.mark_failed(
                int(item["id"]),
                (
                    "ASR could not produce a trustworthy verdict; refusing to publish"
                    if verdict == ASR_INCONCLUSIVE
                    else (
                        "Active endpoint remained at the TTS frame ceiling after all repair rounds"
                        if reason == ACTIVE_CEILING_ENDPOINT_REPAIR_REASON
                        else (
                            "Locked-name pronunciation remained mismatched after all repair rounds"
                            if reason == ASR_LOCKED_NAME_ANCHOR_MISMATCH
                            else "ASR mismatch remained after all configured repair rounds"
                        )
                    )
                ),
                warning_code=warning,
            )
            self.db.event(
                "error",
                warning,
                f"Mandatory content QA blocks publication for {item['stable_id']}",
                {
                    "chapter": str(chapter["title"]),
                    "text": str(item["text"]),
                    "transcript": str(result.get("transcript", "")),
                    "similarity": float(result.get("similarity", 0.0)),
                    "wer": float(result.get("wer", 1.0)),
                    "verdict": verdict,
                },
            )

    def _safe_export_reports(self, *, incremental: bool) -> None:
        try:
            self._export_reports(incremental=incremental)
        except Exception as exc:  # noqa: BLE001
            try:
                self.db.event(
                    "warning",
                    "QUALITY_REPORT_EXPORT_FAILED",
                    f"Could not export the incremental quality report: {exc}",
                )
            except Exception:  # noqa: BLE001
                logging.exception("Could not record quality report export failure")

    def refresh_terminal_reports(self) -> None:
        """Refresh JSON snapshots after the terminal DB state and event are committed.

        This deliberately uses only the report exporter. The worker owns the
        unrecoverable-error transition and must isolate any write failure so the
        original pipeline exception remains authoritative.
        """
        self._export_reports(incremental=True)

    @classmethod
    def refresh_terminal_reports_without_runtime(
        cls,
        *,
        paths: ProjectPaths,
        db: ProjectDB,
        settings: dict[str, Any],
    ) -> None:
        """Refresh reports before a normal pipeline instance can be constructed.

        The reporting view intentionally bypasses ``__init__`` so startup-error
        reporting cannot construct resource managers, TTS, perceptual QA, or model
        backends. ``_export_reports`` needs only these report-specific attributes.
        """
        reporter = object.__new__(cls)
        reporter.paths = paths
        reporter.db = db
        reporter.settings = settings
        reporter.quality_policy = build_quality_policy(settings)
        reporter.quality_policy_hash = quality_policy_hash(reporter.quality_policy)
        reporter._export_reports(incremental=True)

    def _export_reports(self, *, incremental: bool = False) -> None:
        segments = [dict(row) for row in self.db.list_segments()]
        chapters = self.db.list_chapters()
        segments_by_chapter: dict[int, list[dict[str, Any]]] = {}
        for segment in segments:
            segments_by_chapter.setdefault(int(segment["chapter_id"]), []).append(segment)
        chapter_quality: list[dict[str, Any]] = []
        for chapter in chapters:
            artifact = self.db.artifact_by_key(f"chapter_mp3:{chapter['chapter_index']}")
            metadata: dict[str, Any] = {}
            if artifact is not None:
                try:
                    decoded_metadata = json.loads(str(artifact["metadata_json"] or "{}"))
                except json.JSONDecodeError:
                    decoded_metadata = {}
                if isinstance(decoded_metadata, dict):
                    metadata = decoded_metadata

            latest_check = self.db.latest_quality_check(
                scope=QUALITY_SCOPE_CHAPTER,
                stage=CHAPTER_QUALITY_STAGE,
                chapter_id=int(chapter["id"]),
            )
            latest_quality_check: dict[str, Any] | None = None
            if latest_check is not None:
                try:
                    check_metrics = json.loads(str(latest_check["metrics_json"] or "{}"))
                except json.JSONDecodeError:
                    check_metrics = {}
                if not isinstance(check_metrics, dict):
                    check_metrics = {}
                try:
                    failure_codes = json.loads(str(latest_check["failure_codes_json"] or "[]"))
                except json.JSONDecodeError:
                    failure_codes = []
                if not isinstance(failure_codes, list):
                    failure_codes = []
                latest_quality_check = {
                    "verdict": str(latest_check["verdict"]),
                    "artifact_sha256": str(latest_check["artifact_sha256"]),
                    "policy_hash": str(latest_check["policy_hash"]),
                    "policy_version": int(latest_check["policy_version"]),
                    "attempt": int(latest_check["attempt"]),
                    "metrics": check_metrics,
                    "failure_codes": failure_codes,
                    "repair_action": str(latest_check["repair_action"] or ""),
                    "created_at": float(latest_check["created_at"]),
                }

            chapter_segments = segments_by_chapter.get(int(chapter["id"]), [])
            similarities = [
                float(row["asr_similarity"])
                for row in chapter_segments
                if row["asr_similarity"] is not None
            ]
            word_error_rates = [
                float(row["asr_wer"])
                for row in chapter_segments
                if row["asr_wer"] is not None
            ]
            blocking_segment_warnings = self._high_quality_blocking_segment_warnings(
                chapter_segments
            )
            chapter_quality.append(
                {
                    "chapter_id": int(chapter["id"]),
                    "chapter_index": int(chapter["chapter_index"]),
                    "title": str(chapter["title"]),
                    "status": str(chapter["status"]),
                    "last_error": str(chapter["last_error"] or ""),
                    "path": str(artifact["path"] if artifact is not None else chapter["output_mp3"]),
                    "sha256": str(artifact["sha256"] or "") if artifact is not None else "",
                    "artifact_verified": bool(artifact["verified"]) if artifact is not None else False,
                    "current_policy_verified": self.db.chapter_artifact_is_current_qa_verified(
                        int(chapter["chapter_index"])
                    ),
                    "segment_audio_qa_complete": self._chapter_has_current_segment_audio_qa(
                        int(chapter["id"])
                    ),
                    "publishable": self.db.chapter_is_publishable(int(chapter["id"]))
                    and not blocking_segment_warnings,
                    "segment_summary": {
                        "total": len(chapter_segments),
                        "failed": sum(
                            str(row["status"]) == SegmentStatus.FAILED.value
                            for row in chapter_segments
                        ),
                        "warning": sum(
                            bool(row["warning_code"])
                            or str(row["status"]) == SegmentStatus.WARNING.value
                            for row in chapter_segments
                        ),
                        "min_asr_similarity": min(similarities) if similarities else None,
                        "max_asr_wer": max(word_error_rates) if word_error_rates else None,
                        "blocking_warnings": blocking_segment_warnings,
                    },
                    "quality": metadata.get("quality", {}),
                    "metrics": metadata.get("quality_metrics", {}),
                    "latest_quality_check": latest_quality_check,
                }
            )
        content_checks = self.db.latest_segment_quality_checks(
            SEGMENT_AUDIO_QUALITY_STAGE
        )
        perceptual_checks = self.db.latest_segment_quality_checks(
            SEGMENT_PERCEPTUAL_QUALITY_STAGE
        )
        chapter_indexes = {
            int(chapter["id"]): int(chapter["chapter_index"])
            for chapter in chapters
        }
        content_evidence: list[dict[str, Any]] = []
        for row in segments:
            segment_id = int(row["id"])
            check = content_checks.get(segment_id)
            metrics: dict[str, Any] = {}
            failure_codes: list[Any] = []
            if check is not None:
                try:
                    decoded_metrics = json.loads(str(check["metrics_json"] or "{}"))
                except (TypeError, json.JSONDecodeError):
                    decoded_metrics = {}
                if isinstance(decoded_metrics, dict):
                    metrics = decoded_metrics
                try:
                    decoded_failure_codes = json.loads(
                        str(check["failure_codes_json"] or "[]")
                    )
                except (TypeError, json.JSONDecodeError):
                    decoded_failure_codes = []
                if isinstance(decoded_failure_codes, list):
                    failure_codes = decoded_failure_codes
            wav_sha256 = str(row["wav_sha256"] or "")
            evidence_sha256 = (
                str(check["artifact_sha256"] or "") if check is not None else ""
            )
            verdict = str(check["verdict"]) if check is not None else "missing"
            current_artifact = bool(evidence_sha256 and evidence_sha256 == wav_sha256)
            content_evidence.append(
                {
                    "segment_id": segment_id,
                    "stable_id": str(row["stable_id"]),
                    "chapter_id": int(row["chapter_id"]),
                    "chapter_index": chapter_indexes.get(int(row["chapter_id"])),
                    "seq": int(row["seq"]),
                    "wav_path": str(row["wav_path"] or ""),
                    "wav_sha256": wav_sha256,
                    "evidence_present": check is not None,
                    "evidence_artifact_sha256": evidence_sha256,
                    "current_artifact": current_artifact,
                    "current_policy_verified": (
                        current_artifact and verdict == QUALITY_VERDICT_PASS
                    ),
                    "verdict": verdict,
                    "reason": metrics.get("reason"),
                    "transcript": metrics.get("transcript"),
                    "similarity": metrics.get("similarity"),
                    "wer": metrics.get("wer"),
                    "confirmation_decode": metrics.get("confirmation_decode"),
                    "dual_decode_required": metrics.get("dual_decode_required"),
                    "dual_decode_passed": metrics.get("dual_decode_passed"),
                    "confirmation_verdicts": metrics.get(
                        "confirmation_verdicts",
                        [],
                    ),
                    "decode_failure_reasons": metrics.get(
                        "decode_failure_reasons",
                        [],
                    ),
                    LOCKED_NAME_ANCHOR_METRICS_KEY: metrics.get(
                        LOCKED_NAME_ANCHOR_METRICS_KEY
                    ),
                    "decode_evidence": metrics.get("decode_evidence", []),
                    "pronunciation_delivery_variant": metrics.get(
                        "pronunciation_delivery_variant"
                    ),
                    "spoken_text_sha256": metrics.get("spoken_text_sha256"),
                    "expected_spoken_text_sha256": metrics.get(
                        "expected_spoken_text_sha256"
                    ),
                    "failure_codes": failure_codes,
                    "attempt": int(check["attempt"]) if check is not None else None,
                    "policy_hash": str(check["policy_hash"]) if check is not None else None,
                    "policy_version": (
                        int(check["policy_version"]) if check is not None else None
                    ),
                }
            )
        perceptual_evidence: list[dict[str, Any]] = []
        if self._perceptual_qa_enabled():
            for row in segments:
                segment_id = int(row["id"])
                check = perceptual_checks.get(segment_id)
                metrics: dict[str, Any] = {}
                failure_codes: list[Any] = []
                if check is not None:
                    try:
                        decoded_metrics = json.loads(str(check["metrics_json"] or "{}"))
                    except (TypeError, json.JSONDecodeError):
                        decoded_metrics = {}
                    if isinstance(decoded_metrics, dict):
                        metrics = decoded_metrics
                    try:
                        decoded_failure_codes = json.loads(
                            str(check["failure_codes_json"] or "[]")
                        )
                    except (TypeError, json.JSONDecodeError):
                        decoded_failure_codes = []
                    if isinstance(decoded_failure_codes, list):
                        failure_codes = decoded_failure_codes
                wav_sha256 = str(row["wav_sha256"] or "")
                evidence_sha256 = (
                    str(check["artifact_sha256"] or "") if check is not None else ""
                )
                verdict = str(check["verdict"]) if check is not None else "missing"
                current_artifact = bool(evidence_sha256 and evidence_sha256 == wav_sha256)
                perceptual_evidence.append(
                    {
                        "segment_id": segment_id,
                        "stable_id": str(row["stable_id"]),
                        "chapter_id": int(row["chapter_id"]),
                        "chapter_index": chapter_indexes.get(int(row["chapter_id"])),
                        "seq": int(row["seq"]),
                        "wav_path": str(row["wav_path"] or ""),
                        "wav_sha256": wav_sha256,
                        "evidence_present": check is not None,
                        "evidence_artifact_sha256": evidence_sha256,
                        "current_artifact": current_artifact,
                        "current_policy_verified": (
                            current_artifact and verdict == QUALITY_VERDICT_PASS
                        ),
                        "verdict": verdict,
                        "reason": metrics.get("reason"),
                        "score": metrics.get("score"),
                        "baseline_score": metrics.get("baseline_score"),
                        "baseline_delta": metrics.get("baseline_delta"),
                        "baseline_pitch_semitones": metrics.get(
                            "baseline_pitch_semitones"
                        ),
                        "duration_seconds": metrics.get("duration_seconds"),
                        "policy_exemption": metrics.get("policy_exemption"),
                        "review_required": bool(metrics.get("review_required", False)),
                        "failure_codes": failure_codes,
                        "attempt": int(check["attempt"]) if check is not None else None,
                        "policy_hash": str(check["policy_hash"]) if check is not None else None,
                        "policy_version": (
                            int(check["policy_version"]) if check is not None else None
                        ),
                    }
                )
        segments_by_id = {int(row["id"]): row for row in segments}
        candidate_policy_pairs = sorted(
            {
                (int(candidate["segment_id"]), str(candidate["policy_hash"]))
                for candidate in self.db.list_segment_candidates()
            }
        )
        repair_candidate_evidence: list[dict[str, Any]] = []
        for segment_id, policy_hash in candidate_policy_pairs:
            segment = segments_by_id.get(segment_id)
            if segment is None:
                continue
            attempts = self.db.segment_candidate_attempt_summary(
                segment_id,
                policy_hash,
            )
            repair_candidate_evidence.append(
                {
                    "segment_id": segment_id,
                    "stable_id": str(segment["stable_id"]),
                    "chapter_id": int(segment["chapter_id"]),
                    "chapter_index": chapter_indexes.get(int(segment["chapter_id"])),
                    "seq": int(segment["seq"]),
                    "policy_hash": policy_hash,
                    "current_policy": policy_hash == self.quality_policy_hash,
                    "current_wav_path": str(segment["wav_path"] or ""),
                    "current_wav_sha256": str(segment["wav_sha256"] or ""),
                    "promoted": any(
                        str(attempt.get("state")) == SEGMENT_CANDIDATE_PROMOTED
                        for attempt in attempts
                    ),
                    "attempts": attempts,
                }
            )
        warnings = [
            {
                "stable_id": row["stable_id"],
                "chapter_id": row["chapter_id"],
                "seq": row["seq"],
                "text": row["text"],
                "warning_code": row["warning_code"],
                "error": row["error"],
                "asr_text": row["asr_text"],
                "asr_similarity": row["asr_similarity"],
                "asr_wer": row["asr_wer"],
            }
            for row in segments
            if row["status"] in {SegmentStatus.WARNING.value, SegmentStatus.FAILED.value}
            or row["warning_code"]
        ]
        if not incremental:
            export_json_atomic(
                self.paths.output / "characters.json",
                [dict(row) for row in self.db.list_characters()],
            )
            export_json_atomic(
                self.paths.output / "pronunciations.json",
                [dict(row) for row in self.db.list_pronunciations()],
            )
            if self.settings["audio"].get("export_metadata", True):
                export_json_atomic(self.paths.output / "transcript_metadata.json", segments)
        export_json_atomic(self.paths.reports / "review_required.json", warnings)
        export_json_atomic(self.paths.reports / "chapter_quality.json", chapter_quality)
        book = dict(self.db.book())
        quality_passed_count = sum(
            row["status"] == ChapterStatus.COMPLETED.value
            and row["current_policy_verified"]
            and row["segment_audio_qa_complete"]
            and row["publishable"]
            for row in chapter_quality
        )
        failed_count = sum(row["status"] == ChapterStatus.FAILED.value for row in chapter_quality)
        review_count = sum(
            row["status"] != ChapterStatus.FAILED.value
            and not (
                row["status"] == ChapterStatus.COMPLETED.value
                and row["current_policy_verified"]
                and row["segment_audio_qa_complete"]
                and row["publishable"]
            )
            and (
                row["status"] in {
                    ChapterStatus.COMPLETED.value,
                    CHAPTER_REVIEW_STATUS,
                }
                or bool(
                    row.get("latest_quality_check")
                    and row["latest_quality_check"]["verdict"] != QUALITY_VERDICT_PASS
                )
            )
            for row in chapter_quality
        )
        pending_count = len(chapter_quality) - quality_passed_count - failed_count - review_count
        overall_verdict = (
            QUALITY_VERDICT_PASS
            if chapter_quality
            and quality_passed_count == len(chapter_quality)
            else "fail"
            if failed_count
            else "review"
        )
        export_json_atomic(
            self.paths.reports / "audiobook_quality_report.json",
            {
                "schema_version": 1,
                "policy": {
                    "policy_hash": self.quality_policy_hash,
                    "policy_version": QUALITY_POLICY_VERSION,
                    "definition": self.quality_policy,
                },
                "book": {
                    "title": str(book["title"]),
                    "status": str(book["status"]),
                    "stage": str(book["stage"]),
                    "overall_verdict": overall_verdict,
                    "chapters_total": len(chapter_quality),
                    "passed": quality_passed_count,
                    "review": review_count,
                    "failed": failed_count,
                    "pending": max(0, pending_count),
                },
                "global_gates": {
                    "casting_finalized": self.db.casting_is_finalized(),
                    "segment_audio_qa_complete": bool(chapter_quality)
                    and all(row["segment_audio_qa_complete"] for row in chapter_quality),
                    "all_chapters_publishable": bool(chapter_quality)
                    and all(row["publishable"] for row in chapter_quality),
                    "text_segmentation_fingerprint": self.quality_policy[
                        "stage_fingerprints"
                    ][TEXT_SEGMENTATION_STAGE],
                    "analysis_casting_fingerprint": self.quality_policy[
                        "stage_fingerprints"
                    ][ANALYSIS_CASTING_STAGE],
                },
                "review_required": {
                    "chapters": [
                        row
                        for row in chapter_quality
                        if row["status"] != ChapterStatus.COMPLETED.value
                        or not row["current_policy_verified"]
                        or not row["segment_audio_qa_complete"]
                        or not row["publishable"]
                    ],
                    "segments": warnings,
                },
                "segment_content_evidence": content_evidence,
                "segment_perceptual_evidence": perceptual_evidence,
                "segment_repair_candidates": repair_candidate_evidence,
                "chapters": chapter_quality,
            },
        )
        export_json_atomic(
            self.paths.reports / "runtime_events.json",
            [dict(row) for row in self.db.list_events()],
        )
