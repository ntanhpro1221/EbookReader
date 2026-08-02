from __future__ import annotations

import time
from collections import defaultdict
from pathlib import Path
from typing import Any, Callable

from .analysis import AnalysisRequestStopped, OllamaBookAnalyzer
from .asr import WhisperVerifier
from .audio_io import (
    AudioQualityError,
    assemble_chapter_atomic,
    export_json_atomic,
    inspect_wav,
    merge_wav_parts_atomic,
    verify_mp3,
    write_playlist_atomic,
)
from .character_registry import build_registry_and_cast
from .database import ProjectDB
from .io_utils import sha256_file
from .models import BookStatus, ChapterStatus, ProjectPaths, ResourceLevel, SegmentStatus
from .notifier import WindowsNotifier
from .text_processing import SPECIAL_AUDIO_KINDS, has_spoken_content, load_and_segment_chapter
from .recovery import recover_project
from .resource_manager import AdaptiveResourceManager
from .tts import TTSCoordinator, is_fatal_tts_error


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
    ) -> None:
        self.paths = paths
        self.db = db
        self.settings = settings
        self.pause_requested = pause_requested
        self.stop_requested = stop_requested
        self.emit = emit
        self.resources = AdaptiveResourceManager(settings, paths.root)
        self.notifier = WindowsNotifier()
        self.tts = TTSCoordinator(settings, db, self.log)
        self._last_resource_level: ResourceLevel | None = None
        self._completed_noop = False
        self._tts_failure_counts: dict[str, int] = defaultdict(int)

    def log(self, message: str) -> None:
        self.db.event("info", "LOG", message)
        self.emit("log", {"text": message})

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
            decision = self.resources.decide()
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
                        "E Book Reader đang chờ tài nguyên",
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

    def prepare_recovery(self) -> bool:
        self._recover()
        return self._completed_noop

    def run(self, *, recovery_already_run: bool = False) -> None:
        if not recovery_already_run:
            self._recover()
        if self._completed_noop:
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
                self._state("running", "Đang hợp nhất nhân vật và phân vai.")
                alias_map = analyzer.reconcile_aliases(
                    before_batch=lambda index: self._resource_gate(
                        f"alias reconciliation batch {index}",
                        release_active=analyzer.release_model,
                    ),
                    stop_requested=self.stop_requested,
                )
                build_registry_and_cast(self.db, self.settings, alias_map, self.log)
                self.db.finalize_casting()
            self.db.update_book(status=BookStatus.CASTING.value, stage="voice_cast_locked")
        except AnalysisRequestStopped as exc:
            raise PipelineStopped("Stop requested during Ollama analysis") from exc
        finally:
            analyzer.unload()

        self._state("running", "Đang xác minh các giọng VieNeu đã khóa.")
        self._resource_gate("xác minh preset VieNeu", keep_engine="vieneu")
        self.tts.prepare_voice_presets()
        self.tts.unload_idle_models()
        self.db.update_book(status=BookStatus.SYNTHESIZING.value, stage="chapter_synthesis")

        verifier = WhisperVerifier(self.settings, self.log)
        try:
            chapters = self.db.list_chapters()
            for chapter_no, chapter in enumerate(chapters, 1):
                self._wait_pause_or_stop()
                self._process_chapter(chapter, verifier)
                self.emit(
                    "chapter_progress",
                    {"done": chapter_no, "total": len(chapters), "chapter_id": int(chapter["id"])},
                )
        finally:
            verifier.unload()
            self.tts.unload_all()

        self._progress("Xuất báo cáo", 0, 1)
        self._export_reports()
        self._progress("Xuất báo cáo", 1, 1)
        completed = [row for row in self.db.list_chapters() if row["status"] == ChapterStatus.COMPLETED.value]
        all_chapters = self.db.list_chapters()
        if completed and len(completed) == len(all_chapters):
            chapter_files = [Path(str(row["output_mp3"])) for row in completed]
            if self.settings["audio"].get("create_m3u8", True):
                write_playlist_atomic(chapter_files, self.paths.output / "playlist.m3u8")
            self.db.update_book(status=BookStatus.COMPLETED.value, stage="completed", error=None)
            self._state("completed", "Đã hoàn tất toàn bộ audiobook.")
            self.notifier.notify(
                "E Book Reader đã hoàn tất",
                f"Book: {self.db.book()['title']}",
                project_path=self.paths.root,
            )
        else:
            failed = len([row for row in all_chapters if row["status"] == ChapterStatus.FAILED.value])
            self.db.update_book(
                status=BookStatus.ERROR.value,
                stage="completed_with_errors",
                error=f"{failed} chapter chưa thể xuất MP3",
            )
            self._state("error", f"Đã xử lý xong nhưng còn {failed} chapter lỗi.")

    def _existing_segment_is_safe(self, row: Any) -> bool:
        if str(row["status"]) not in {SegmentStatus.VERIFIED.value, SegmentStatus.WARNING.value}:
            return False
        wav_text = str(row["wav_path"] or "")
        if not wav_text:
            return False
        wav = Path(wav_text)
        if not wav.exists():
            return False
        if row["wav_sha256"] and sha256_file(wav) != str(row["wav_sha256"]):
            return False
        valid, _, _ = inspect_wav(wav, str(row["text"]), self.settings, segment=row)
        return valid

    def _process_chapter(self, chapter: Any, verifier: WhisperVerifier) -> None:
        chapter_id = int(chapter["id"])
        self._validate_chapter_source(chapter)
        output = Path(str(chapter["output_mp3"]))
        if chapter["status"] == ChapterStatus.COMPLETED.value:
            valid, _ = verify_mp3(output)
            if valid:
                self.log(f"Bỏ qua chapter đã hoàn tất: {chapter['title']}")
                return

        self.db.update_chapter_status(chapter_id, ChapterStatus.SYNTHESIZING.value)
        self.log(f"Tạo audio chapter {chapter['chapter_index']}: {chapter['title']}")
        rows = self.db.list_segments(chapter_id=chapter_id)
        for row in rows:
            if self._existing_segment_is_safe(row):
                continue
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
            if self._existing_segment_is_safe(row):
                continue
            # A valid signal_passed WAV can proceed directly to the chapter ASR stage after recovery.
            if str(row["status"]) == SegmentStatus.SIGNAL_PASSED.value and row["wav_path"]:
                valid, _, _ = inspect_wav(
                    Path(str(row["wav_path"])),
                    str(row["text"]),
                    self.settings,
                    segment=row,
                )
                if valid:
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
        checksum = assemble_chapter_atomic(
            wavs,
            output,
            self.settings,
            title=str(chapter["title"]),
            book_title=str(self.db.book()["title"]),
            track=int(chapter["chapter_index"]),
            work_dir=self.paths.work / "silence",
        )
        self.db.register_artifact(
            artifact_key=f"chapter_mp3:{chapter['chapter_index']}",
            kind="chapter_mp3",
            path=output,
            sha256=checksum,
            verified=True,
            metadata={"chapter_id": chapter_id, "title": str(chapter["title"])},
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

    def _process_single_segment(self, row: Any, chapter: Any, seed_salt_prefix: str = "primary") -> None:
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
                    row, output, seed_salt=seed_salt
                )
                self.db.mark_signal_passed(
                    int(row["id"]),
                    wav_path=output,
                    wav_sha256=checksum,
                    duration=float(metrics["duration"]),
                    signal=metrics,
                    generation_seed=seed,
                )
                if metrics.get("pace_outlier"):
                    self.db.set_segment_warning_code(int(row["id"]), "TTS_PACE_OUTLIER")
                    self.log(
                        f"TTS segment {row['stable_id']} lệch tốc độ mục tiêu "
                        f"({metrics['chars_per_second']:.2f} chars/s) nhưng vẫn trong giới hạn an toàn; "
                        "chuyển sang Whisper kiểm tra."
                    )
                return
            except Exception as exc:  # noqa: BLE001
                if is_fatal_tts_error(exc):
                    raise RuntimeError(f"Fatal TTS engine failure: {exc}") from exc
                last_error = str(exc)
                self.log(f"TTS segment {row['stable_id']} lỗi lần {attempt + 1}/{retries}: {last_error}")
                time.sleep(min(8, 2 ** attempt))

        if str(row["kind"]) in SPECIAL_AUDIO_KINDS:
            last_error = f"{last_error}; split=not applicable to {row['kind']}"
        else:
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
                    str(row["text"]),
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
        signature = " ".join(last_error.casefold().split())[:240]
        self._tts_failure_counts[signature] += 1
        failure_limit = int(self.settings["tts"].get("fatal_failure_streak", 3))
        if self._tts_failure_counts[signature] >= failure_limit:
            raise RuntimeError(
                f"TTS circuit breaker opened after {failure_limit} identical failures: {last_error}"
            )

    def _synthesize_split(self, row: Any, output: Path) -> None:
        text = str(row["text"])
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
        ) -> list[dict[str, Any]]:
            mismatches: list[dict[str, Any]] = []
            self._progress(label, 0, len(items))
            for index, item in enumerate(items, 1):
                if str(item["kind"]) in SPECIAL_AUDIO_KINDS:
                    self.db.mark_verified(int(item["id"]), warning_code=str(item.get("warning_code") or "") or None)
                    self._progress(label, index, len(items))
                    continue
                self._resource_gate(
                    f"Whisper chapter {chapter['chapter_index']} segment {item['seq']}",
                    release_active=verifier.unload,
                )
                result = verifier.verify(
                    self.tts.spoken_text(item), Path(str(item["wav_path"]))
                )
                last_results[int(item["id"])] = result
                existing_warning = str(item.get("warning_code") or "") or None
                if result["reason"] in {"ASR_NOT_RUN", "ASR_ERROR"}:
                    self.db.mark_verified(int(item["id"]), warning_code=str(result["reason"]))
                elif result["passed"]:
                    self.db.mark_asr_result(
                        int(item["id"]), passed=True, transcript=str(result["transcript"]),
                        similarity=float(result["similarity"]), wer=float(result["wer"]),
                    )
                    self.db.mark_verified(int(item["id"]), warning_code=existing_warning)
                else:
                    mismatches.append(item)
                self._progress(label, index, len(items))
            return mismatches

        verification_label = f"Kiểm tra phát âm chapter {chapter['chapter_index']}"
        mismatches = verify_rows(pending, verification_label)
        final_mismatches: list[dict[str, Any]] = []
        repairable_mismatches: list[dict[str, Any]] = []
        for item in mismatches:
            result = last_results.get(int(item["id"]), {})
            if bool(result.get("repairable", True)):
                repairable_mismatches.append(item)
            else:
                final_mismatches.append(item)
        mismatches = repairable_mismatches
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
                self._process_single_segment(item, chapter, seed_salt_prefix=f"asr_repair_{repair_round}")
                fresh = self.db.get_segment(int(item["id"]))
                if str(fresh["status"]) == SegmentStatus.SIGNAL_PASSED.value:
                    regenerated.append(dict(fresh))
                self._progress(repair_label, index, len(mismatches))
            self.tts.unload_all()
            verified_mismatches = verify_rows(
                regenerated,
                f"Kiểm tra lại chapter {chapter['chapter_index']} — vòng {repair_round + 1}",
            )
            mismatches = []
            for item in verified_mismatches:
                result = last_results.get(int(item["id"]), {})
                if bool(result.get("repairable", True)):
                    mismatches.append(item)
                else:
                    final_mismatches.append(item)

        final_mismatches.extend(mismatches)
        for item in sorted(final_mismatches, key=lambda row: int(row["seq"])):
            result = last_results.get(int(item["id"]), {})
            warning = "ASR_MISMATCH_UNRESOLVED"
            if self.settings["asr"].get("failure_policy") == "fail":
                self.db.mark_failed(
                    int(item["id"]),
                    "ASR mismatch remained after all configured repair rounds",
                    warning_code="ASR_MISMATCH_UNRESOLVED",
                )
                self.db.event(
                    "error",
                    "ASR_MISMATCH_UNRESOLVED",
                    f"ASR mismatch is fatal by policy for {item['stable_id']}",
                    {"chapter": str(chapter["title"]), "text": str(item["text"])},
                )
                continue
            self.db.mark_asr_result(
                int(item["id"]), passed=False, transcript=str(result.get("transcript", "")),
                similarity=float(result.get("similarity", 0.0)), wer=float(result.get("wer", 1.0)),
                warning_code=warning,
            )
            self.db.mark_verified(int(item["id"]), warning_code=warning)
            self.db.event(
                "warning",
                "ASR_MISMATCH_UNRESOLVED",
                f"ASR still differs for {item['stable_id']}; audio kept for later review",
                {
                    "chapter": str(chapter["title"]),
                    "text": str(item["text"]),
                    "transcript": str(result.get("transcript", "")),
                    "similarity": float(result.get("similarity", 0.0)),
                    "wer": float(result.get("wer", 1.0)),
                },
            )

    def _export_reports(self) -> None:
        characters = [dict(row) for row in self.db.list_characters()]
        segments = [dict(row) for row in self.db.list_segments()]
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
        export_json_atomic(self.paths.output / "characters.json", characters)
        export_json_atomic(
            self.paths.output / "pronunciations.json",
            [dict(row) for row in self.db.list_pronunciations()],
        )
        if self.settings["audio"].get("export_metadata", True):
            export_json_atomic(self.paths.output / "transcript_metadata.json", segments)
        export_json_atomic(self.paths.reports / "review_required.json", warnings)
        export_json_atomic(
            self.paths.reports / "runtime_events.json",
            [dict(row) for row in self.db.list_events()],
        )
