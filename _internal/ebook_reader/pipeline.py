from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any, Callable

from .analysis import AnalysisRequestStopped, OllamaBookAnalyzer
from .asr import ASR_INCONCLUSIVE, ASR_MISMATCH, ASR_PASS, WhisperVerifier
from .audio_io import (
    AudioQualityError,
    ChapterQualityError,
    assemble_chapter_atomic_with_metrics,
    export_json_atomic,
    inspect_wav,
    merge_wav_parts_atomic,
    verify_mp3,
    write_playlist_atomic,
)
from .character_registry import build_registry_and_cast
from .database import (
    QUALITY_SCOPE_CHAPTER,
    QUALITY_SCOPE_SEGMENT,
    QUALITY_VERDICT_PASS,
    SEGMENT_AUDIO_QUALITY_STAGE,
    ProjectDB,
)
from .io_utils import sha256_file
from .models import BookStatus, ChapterStatus, ProjectPaths, ResourceLevel, SegmentStatus
from .notifier import WindowsNotifier
from .text_processing import has_spoken_content, load_and_segment_chapter
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
from .tts import TTSCoordinator, is_fatal_tts_error


CRITICAL_RAM_RECOVERY_WAIT_SECONDS = 2.0
HIGH_QUALITY_ALLOWED_SEGMENT_WARNINGS = frozenset({"TTS_SPLIT_RECOVERY"})
CHAPTER_REVIEW_STATUS = "warning"
QUALITY_VERDICT_FAIL = "fail"
CHAPTER_AUDIO_PIPELINE_FAILURE_CODE = "CHAPTER_AUDIO_PIPELINE_FAILED"
CHAPTER_QUALITY_REPAIR_ACTION = "retry_after_quality_or_policy_change"


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
                if not decision.allow_new_gpu_batch and release_active is not None:
                    release_active()
                elif decision.allow_new_gpu_batch:
                    self.tts.unload_idle_models(keep_engine=keep_engine)
                else:
                    # At this point the previous inference already committed. Release even the active
                    # engine so a foreground renderer/game can reclaim VRAM without killing CUDA mid-kernel.
                    self.tts.unload_all()
            cpu_ok = (not require_cpu_io) or decision.allow_cpu_heavy_work
            if decision.allow_new_gpu_batch and cpu_ok:
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
            raise RuntimeError(
                "Text segmentation implementation changed after segments were checkpointed; "
                "create a clean project so stale text cannot be republished"
            )
        analysis_started = self.db.casting_is_finalized() or any(
            str(row["status"]) != SegmentStatus.PENDING.value for row in rows
        )
        if analysis_started and previous_stages.get(ANALYSIS_CASTING_STAGE) != current_stages.get(
            ANALYSIS_CASTING_STAGE
        ):
            raise RuntimeError(
                "Analysis/casting implementation changed after analysis started; create a clean project "
                "so stale speaker and voice assignments cannot be republished"
            )

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

        analyzer = OllamaBookAnalyzer(self.settings, self.db, self.log)
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

    def _next_segment_quality_attempt(self, segment_id: int) -> int:
        latest = self.db.latest_quality_check(
            scope=QUALITY_SCOPE_SEGMENT,
            stage=SEGMENT_AUDIO_QUALITY_STAGE,
            segment_id=segment_id,
        )
        return int(latest["attempt"]) + 1 if latest is not None else 1

    def _record_segment_audio_pass(
        self,
        item: dict[str, Any],
        result: dict[str, Any],
        *,
        confirmation: bool,
    ) -> None:
        segment_id = int(item["id"])
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
        self.db.record_quality_check(
            scope=QUALITY_SCOPE_SEGMENT,
            stage=SEGMENT_AUDIO_QUALITY_STAGE,
            segment_id=segment_id,
            artifact_sha256=artifact_sha256,
            policy_hash=self.quality_policy_hash,
            policy_version=QUALITY_POLICY_VERSION,
            verdict=QUALITY_VERDICT_PASS,
            metrics={
                "verdict": _asr_verdict(result),
                "reason": str(result.get("reason", "ok")),
                "transcript": str(result.get("transcript", "")),
                "similarity": float(result.get("similarity", 0.0)),
                "wer": float(result.get("wer", 0.0)),
                "confirmation_decode": bool(confirmation),
                "repeated_short_context": (
                    str(result.get("reason", "")) == "ASR_REPEATED_SHORT_PASS"
                ),
            },
            attempt=self._next_segment_quality_attempt(segment_id),
        )

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
        valid, metrics, _ = inspect_wav(
            wav,
            self.tts.spoken_text(row),
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
        return self.db.segment_audio_is_current_qa_verified(
            int(row["id"]),
            str(row["wav_sha256"]),
            SEGMENT_AUDIO_QUALITY_STAGE,
        )

    def _recheckpoint_segment_for_current_audio_qa(
        self,
        row: Any,
        metrics: dict[str, float],
    ) -> None:
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
            duration=float(metrics["duration"]),
            signal=metrics,
            generation_seed=generation_seed,
        )
        if metrics.get("pace_outlier"):
            self.db.set_segment_warning_code(int(row["id"]), "TTS_PACE_OUTLIER")

    def _process_chapter(self, chapter: Any, verifier: WhisperVerifier) -> None:
        chapter_id = int(chapter["id"])
        self._validate_chapter_source(chapter)
        output = Path(str(chapter["output_mp3"]))
        if chapter["status"] == ChapterStatus.COMPLETED.value:
            valid, _ = verify_mp3(output)
            quality_verified = self.db.chapter_artifact_is_current_qa_verified(
                int(chapter["chapter_index"])
            )
            segment_quality_verified = self.db.chapter_segments_have_current_audio_qa(
                chapter_id,
                SEGMENT_AUDIO_QUALITY_STAGE,
            )
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
                SegmentStatus.GENERATING.value,
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
            if (
                status in {SegmentStatus.VERIFIED.value, SegmentStatus.WARNING.value}
                and signal_valid
                and self.db.segment_audio_is_current_qa_verified(
                    int(row["id"]),
                    str(row["wav_sha256"]),
                    SEGMENT_AUDIO_QUALITY_STAGE,
                )
            ):
                continue
            if signal_valid and status in {
                SegmentStatus.SIGNAL_PASSED.value,
                SegmentStatus.ASR_PASSED.value,
                SegmentStatus.VERIFIED.value,
                SegmentStatus.WARNING.value,
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

        wavs = [(Path(str(row["wav_path"])), int(row["break_ms"])) for row in rows]
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

    def _process_single_segment(
        self,
        row: Any,
        chapter: Any,
        seed_salt_prefix: str = "primary",
        *,
        repair_short_utterance: bool = False,
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
                )
                checksum, metrics, seed = self.tts.synthesize_atomic(
                    row,
                    output,
                    seed_salt=seed_salt,
                    repair_short_utterance=repair_short_utterance,
                )
                if self.settings.get("quality_profile") == "high_quality":
                    retry_reasons = []
                    if metrics.get("pace_outlier"):
                        retry_reasons.append(
                            f"speech pace {metrics.get('chars_per_second', 0.0):.2f} chars/s"
                        )
                    if metrics.get("generation_ceiling_hit"):
                        retry_reasons.append("generation reached the frame ceiling")
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
                )
                self._reset_tts_failure_streak()
                if metrics.get("pace_outlier"):
                    self.db.set_segment_warning_code(int(row["id"]), "TTS_PACE_OUTLIER")
                    self.log(
                        f"TTS segment {row['stable_id']} lệch tốc độ mục tiêu "
                        f"({metrics['chars_per_second']:.2f} chars/s) nhưng vẫn trong giới hạn an toàn; "
                        "chuyển sang Whisper kiểm tra."
                    )
                if metrics.get("pitch_variant_skipped"):
                    self.db.set_segment_warning_code(
                        int(row["id"]),
                        "TTS_PITCH_VARIANT_SKIPPED",
                    )
                if metrics.get("generation_ceiling_hit"):
                    self.db.set_segment_warning_code(
                        int(row["id"]),
                        "TTS_GENERATION_CEILING_REACHED",
                    )
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

        self.log(
            f"TTS segment {row['stable_id']} đã lỗi {retries}/{retries}; "
            "đang thử chia nhỏ để cứu."
        )
        try:
            split_seed = self.tts.generation_seed(row, "split")
            self.db.mark_generating(int(row["id"]), split_seed)
            self._synthesize_split(row, output)
            valid, metrics, reason = inspect_wav(
                output,
                self.tts.spoken_text(row),
                self.settings,
                segment=row,
            )
            if not valid:
                raise AudioQualityError(reason)
            checksum = sha256_file(output)
            self.db.mark_signal_passed(
                int(row["id"]), wav_path=output, wav_sha256=checksum,
                duration=float(metrics["duration"]), signal=metrics, generation_seed=split_seed,
            )
            self._reset_tts_failure_streak()
            self.db.set_segment_warning_code(int(row["id"]), "TTS_SPLIT_RECOVERY")
            if metrics.get("pace_outlier"):
                self.db.set_segment_warning_code(int(row["id"]), "TTS_PACE_OUTLIER")
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

    def _synthesize_split(self, row: Any, output: Path) -> None:
        text = self.tts.spoken_text(row)
        if len(text) < 100:
            raise AudioQualityError("segment too short to split safely")
        words = text.split()
        pieces: list[str] = []
        current = ""
        for word in words:
            candidate = f"{current} {word}".strip()
            if current and len(candidate) > 170:
                pieces.append(current)
                current = word
            else:
                current = candidate
        if current:
            pieces.append(current)
        if len(pieces) < 2:
            raise AudioQualityError("split produced fewer than two pieces")
        part_paths: list[Path] = []
        try:
            for index, piece in enumerate(pieces):
                part_row = dict(row)
                part_row["text"] = piece
                part_row["stable_id"] = f"{row['stable_id']}_part{index:02d}"
                part_path = output.with_name(output.stem + f".split{index:02d}.wav")
                part_paths.append(part_path)
                self.tts.synthesize_atomic(part_row, part_path, seed_salt=f"split_{index}")
            merge_wav_parts_atomic(part_paths, output, text, self.settings, segment=row)
        finally:
            for path in part_paths:
                path.unlink(missing_ok=True)

    def _verify_chapter_audio(self, chapter: Any, verifier: WhisperVerifier) -> None:
        chapter_id = int(chapter["id"])
        rows = self.db.list_segments(chapter_id=chapter_id)
        pending: list[dict[str, Any]] = []
        last_results: dict[int, dict[str, Any]] = {}
        for row in rows:
            if str(row["status"]) == SegmentStatus.FAILED.value:
                continue
            if self._existing_segment_is_safe(row):
                continue
            if str(row["status"]) != SegmentStatus.SIGNAL_PASSED.value or not row["wav_path"]:
                self.db.mark_failed(int(row["id"]), "No signal-validated WAV available for ASR")
                continue
            pending.append(dict(row))

        def verify_rows(
            items: list[dict[str, Any]],
            label: str,
            *,
            confirmation: bool = False,
        ) -> list[dict[str, Any]]:
            issues: list[dict[str, Any]] = []
            self._progress(label, 0, len(items))
            for index, item in enumerate(items, 1):
                self._resource_gate(
                    f"Whisper chapter {chapter['chapter_index']} segment {item['seq']}",
                    release_active=verifier.unload,
                )
                expected_text = self.tts.spoken_text(item)
                result = verifier.verify(
                    expected_text,
                    Path(str(item["wav_path"])),
                    confirmation=confirmation,
                )
                if _asr_verdict(result) != ASR_PASS and verifier.can_verify_repeated_short(
                    expected_text
                ):
                    result = verifier.verify_repeated_short(
                        expected_text,
                        Path(str(item["wav_path"])),
                        confirmation=confirmation,
                    )
                last_results[int(item["id"])] = result
                existing_warning = str(item.get("warning_code") or "") or None
                if _asr_verdict(result) == ASR_PASS:
                    self.db.mark_asr_result(
                        int(item["id"]), passed=True, transcript=str(result["transcript"]),
                        similarity=float(result["similarity"]), wer=float(result["wer"]),
                    )
                    self._record_segment_audio_pass(
                        item,
                        result,
                        confirmation=confirmation,
                    )
                    self.db.mark_verified(int(item["id"]), warning_code=existing_warning)
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
            initial_results: dict[int, dict[str, Any]] = {}
            for item in candidates:
                result = last_results.get(int(item["id"]), {})
                if _asr_verdict(result) in {ASR_MISMATCH, ASR_INCONCLUSIVE}:
                    needs_confirmation.append(item)
                    initial_results[int(item["id"])] = dict(result)
                else:
                    rejected.append(item)
            confirmed_issues = (
                verify_rows(needs_confirmation, label, confirmation=True)
                if needs_confirmation
                else []
            )
            confirmed: list[dict[str, Any]] = []
            for item in confirmed_issues:
                segment_id = int(item["id"])
                first_result = initial_results.get(segment_id, {})
                result = last_results.get(segment_id, {})
                first_verdict = _asr_verdict(first_result)
                second_verdict = _asr_verdict(result)
                if (
                    first_verdict == ASR_MISMATCH
                    and second_verdict == ASR_MISMATCH
                    and bool(result.get("repairable", True))
                ):
                    confirmed.append(item)
                else:
                    if first_verdict != second_verdict:
                        last_results[segment_id] = {
                            **result,
                            "passed": False,
                            "verdict": ASR_INCONCLUSIVE,
                            "reason": "ASR_CONFIRMATION_DISAGREED",
                            "repairable": False,
                            "severe": False,
                        }
                    rejected.append(item)
            return confirmed, rejected

        verification_label = f"Kiểm tra phát âm chapter {chapter['chapter_index']}"
        issues = verify_rows(pending, verification_label)
        final_mismatches: list[dict[str, Any]] = []
        mismatches, unrepairable = confirm_repair_candidates(
            issues,
            f"Xác nhận lệch nội dung chapter {chapter['chapter_index']}",
        )
        final_mismatches.extend(unrepairable)
        repair_rounds = int(self.settings["asr"].get("repair_rounds", 2))
        for repair_round in range(repair_rounds):
            if not mismatches:
                break
            verifier.unload()
            regenerated: list[dict[str, Any]] = []
            repair_label = (
                f"Sửa audio chapter {chapter['chapter_index']} — vòng {repair_round + 1}"
            )
            self._progress(repair_label, 0, len(mismatches))
            for index, item in enumerate(mismatches, 1):
                self._resource_gate(
                    f"ASR repair chapter {chapter['chapter_index']} segment {item['seq']}",
                    keep_engine=None,
                )
                # Retry the locked primary voice with a different deterministic seed.
                self._process_single_segment(
                    item,
                    chapter,
                    seed_salt_prefix=f"asr_repair_{repair_round}",
                    repair_short_utterance=True,
                )
                fresh = self.db.get_segment(int(item["id"]))
                if str(fresh["status"]) == SegmentStatus.SIGNAL_PASSED.value:
                    regenerated.append(dict(fresh))
                self._progress(repair_label, index, len(mismatches))
            self.tts.unload_all()
            verified_mismatches = verify_rows(
                regenerated,
                f"Kiểm tra lại chapter {chapter['chapter_index']} — vòng {repair_round + 1}",
            )
            mismatches, unrepairable = confirm_repair_candidates(
                verified_mismatches,
                (
                    f"Xác nhận lệch nội dung chapter {chapter['chapter_index']} "
                    f"— vòng {repair_round + 1}"
                ),
            )
            final_mismatches.extend(unrepairable)

        final_mismatches.extend(mismatches)
        for item in sorted(final_mismatches, key=lambda row: int(row["seq"])):
            result = last_results.get(int(item["id"]), {})
            verdict = _asr_verdict(result)
            reason = str(result.get("reason", "ASR_INCONCLUSIVE"))
            warning = reason if verdict == ASR_INCONCLUSIVE else "ASR_MISMATCH_UNRESOLVED"
            severe = bool(result.get("severe", False))
            if severe:
                warning = "ASR_SEVERE_MISMATCH"
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
                    else "ASR mismatch remained after all configured repair rounds"
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
            self.db.event(
                "warning",
                "QUALITY_REPORT_EXPORT_FAILED",
                f"Could not export the incremental quality report: {exc}",
            )

    def _export_reports(self, *, incremental: bool = False) -> None:
        segments = [dict(row) for row in self.db.list_segments()]
        chapter_quality: list[dict[str, Any]] = []
        for chapter in self.db.list_chapters():
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

            chapter_segments = [
                row for row in segments if int(row["chapter_id"]) == int(chapter["id"])
            ]
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
                    "segment_audio_qa_complete": self.db.chapter_segments_have_current_audio_qa(
                        int(chapter["id"]),
                        SEGMENT_AUDIO_QUALITY_STAGE,
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
        completed_count = sum(
            row["status"] == ChapterStatus.COMPLETED.value for row in chapter_quality
        )
        failed_count = sum(row["status"] == ChapterStatus.FAILED.value for row in chapter_quality)
        review_count = sum(
            row["status"] not in {
                ChapterStatus.COMPLETED.value,
                ChapterStatus.FAILED.value,
            }
            and (
                row["status"] == CHAPTER_REVIEW_STATUS
                or bool(
                    row.get("latest_quality_check")
                    and row["latest_quality_check"]["verdict"] != QUALITY_VERDICT_PASS
                )
            )
            for row in chapter_quality
        )
        pending_count = len(chapter_quality) - completed_count - failed_count - review_count
        overall_verdict = (
            QUALITY_VERDICT_PASS
            if chapter_quality
            and completed_count == len(chapter_quality)
            and all(row["current_policy_verified"] for row in chapter_quality)
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
                    "passed": completed_count,
                    "review": review_count,
                    "failed": failed_count,
                    "pending": max(0, pending_count),
                },
                "global_gates": {
                    "casting_finalized": self.db.casting_is_finalized(),
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
                    ],
                    "segments": warnings,
                },
                "chapters": chapter_quality,
            },
        )
        export_json_atomic(
            self.paths.reports / "runtime_events.json",
            [dict(row) for row in self.db.list_events()],
        )
