from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .audio_io import inspect_wav, verify_mp3
from .background_runner import BACKGROUND_DIRECTORY
from .database import (
    SEGMENT_AUDIO_QUALITY_STAGE,
    SEGMENT_PERCEPTUAL_QUALITY_STAGE,
    ProjectDB,
)
from .io_utils import remove_part_files, sha256_file
from .models import ProjectPaths, SegmentStatus


@dataclass(slots=True)
class RecoveryReport:
    removed_part_files: int = 0
    reset_in_progress: int = 0
    recovered_verified: int = 0
    requeued_asr: int = 0
    reset_missing_or_corrupt: int = 0
    invalid_mp3: int = 0
    stale_leases: int = 0
    completed_verified: bool = False
    candidate_resume_plans: list[dict] = field(default_factory=list)
    stale_candidates: int = 0
    invalidated_candidates: int = 0


class RecoveryError(RuntimeError):
    pass


def _perceptual_qa_enabled(settings: dict) -> bool:
    return bool(settings.get("perceptual_qa", {}).get("enabled", False))


def _segment_has_current_audio_qa(
    db: ProjectDB,
    settings: dict,
    *,
    segment_id: int,
    artifact_sha256: str,
) -> bool:
    if not db.segment_audio_is_current_qa_verified(
        segment_id,
        artifact_sha256,
        SEGMENT_AUDIO_QUALITY_STAGE,
    ):
        return False
    return not _perceptual_qa_enabled(settings) or db.segment_audio_is_current_qa_verified(
        segment_id,
        artifact_sha256,
        SEGMENT_PERCEPTUAL_QUALITY_STAGE,
    )


def _chapter_has_current_segment_audio_qa(
    db: ProjectDB,
    settings: dict,
    chapter_id: int,
) -> bool:
    if not db.chapter_segments_have_current_audio_qa(
        chapter_id,
        SEGMENT_AUDIO_QUALITY_STAGE,
    ):
        return False
    return not _perceptual_qa_enabled(settings) or db.chapter_segments_have_current_audio_qa(
        chapter_id,
        SEGMENT_PERCEPTUAL_QUALITY_STAGE,
    )


def _validate_chapter_source_for_completed_fast_path(chapter, settings: dict) -> None:
    if not settings.get("safety", {}).get("stop_book_on_source_change", True):
        return
    source = Path(str(chapter["input_path"] or ""))
    if not source.is_file():
        raise RecoveryError(f"Source chapter is missing: {source}")
    if source.stat().st_size != int(chapter["input_size"]):
        raise RecoveryError(f"Source chapter size changed after project creation: {source}")
    if sha256_file(source) != str(chapter["input_sha256"]):
        raise RecoveryError(f"Source chapter content changed after project creation: {source}")


def recover_project(paths: ProjectPaths, db: ProjectDB, settings: dict) -> RecoveryReport:
    errors = db.integrity_check()
    if errors:
        raise RecoveryError("SQLite integrity check failed: " + "; ".join(errors[:10]))

    report = RecoveryReport()
    report.removed_part_files = len(
        remove_part_files(
            paths.root,
            excluded_roots=(paths.root / BACKGROUND_DIRECTORY,),
        )
    )
    report.reset_in_progress = db.reset_in_progress_segments()
    report.stale_leases = db.clear_all_worker_leases()
    current_policy = db.current_quality_policy()
    if current_policy is not None:
        policy_hash = str(current_policy["policy_hash"])
        repair_rounds = int(settings.get("asr", {}).get("repair_rounds", 0))
        report.invalidated_candidates = db.reconcile_segment_candidate_artifacts(policy_hash)
        report.candidate_resume_plans = db.list_segment_candidate_resume_plans(
            policy_hash,
            repair_rounds,
        )
        report.stale_candidates = db.count_stale_segment_candidates(policy_hash)

    if str(db.book()["status"]) == "completed":
        completed_ok = True
        chapters = db.list_chapters()
        for chapter in chapters:
            _validate_chapter_source_for_completed_fast_path(chapter, settings)
            output = Path(str(chapter["output_mp3"] or ""))
            artifact = db.artifact_by_key(f"chapter_mp3:{chapter['chapter_index']}")
            valid, _ = verify_mp3(output)
            quality_ok = db.chapter_artifact_is_current_qa_verified(
                int(chapter["chapter_index"])
            )
            segment_quality_ok = _chapter_has_current_segment_audio_qa(
                db,
                settings,
                int(chapter["id"]),
            )
            checksum_ok = bool(
                artifact
                and artifact["verified"]
                and artifact["sha256"]
                and output.exists()
                and sha256_file(output) == str(artifact["sha256"])
            )
            completed_ok = (
                completed_ok
                and str(chapter["status"]) == "completed"
                and db.chapter_is_publishable(int(chapter["id"]))
                and valid
                and checksum_ok
                and quality_ok
                and segment_quality_ok
            )
        if completed_ok and chapters:
            report.completed_verified = True
            db.event(
                "info",
                "COMPLETED_PROJECT_VERIFIED",
                "Completed project artifacts verified; deep WAV recovery was skipped",
                {"chapters": len(chapters)},
            )
            return report

    for row in db.list_segments(statuses=("signal_passed", "verified", "warning")):
        wav_text = str(row["wav_path"] or "")
        wav = Path(wav_text) if wav_text else None
        valid = False
        if wav and wav.exists() and wav.stat().st_size > 1024:
            checksum_required = bool(settings.get("safety", {}).get("verify_checksums", True))
            checksum_ok = bool(row["wav_sha256"]) and sha256_file(wav) == str(row["wav_sha256"])
            if not checksum_required:
                checksum_ok = True
            signal_ok, _, _ = inspect_wav(wav, str(row["text"]), settings, segment=row)
            valid = checksum_ok and signal_ok
        if valid:
            status = str(row["status"])
            quality_ok = _segment_has_current_audio_qa(
                db,
                settings,
                segment_id=int(row["id"]),
                artifact_sha256=str(row["wav_sha256"] or ""),
            )
            if status in {
                SegmentStatus.VERIFIED.value,
                SegmentStatus.WARNING.value,
            } and not quality_ok:
                db.requeue_segment_for_asr(
                    int(row["id"]),
                    "Recovery requires ASR and perceptual QA under the current locked quality policy",
                )
                report.requeued_asr += 1
            else:
                report.recovered_verified += 1
        else:
            db.reset_segment_pending(int(row["id"]), "Recovery found missing/corrupt/checksum-mismatched WAV")
            report.reset_missing_or_corrupt += 1

    for chapter in db.list_chapters():
        output_text = str(chapter["output_mp3"] or "")
        if not output_text:
            continue
        output = Path(output_text)
        if chapter["status"] == "completed":
            if not db.chapter_is_publishable(int(chapter["id"])):
                db.update_chapter_status(
                    int(chapter["id"]),
                    "warning",
                    "MP3 must be rebuilt because one or more segment checkpoints are invalid",
                )
                report.invalid_mp3 += 1
                continue
            valid, reason = verify_mp3(output)
            artifact = db.artifact_by_key(f"chapter_mp3:{chapter['chapter_index']}")
            quality_ok = db.chapter_artifact_is_current_qa_verified(
                int(chapter["chapter_index"])
            )
            checksum_ok = bool(
                artifact
                and artifact["verified"]
                and artifact["sha256"]
                and output.exists()
                and sha256_file(output) == str(artifact["sha256"])
            )
            if not valid or not checksum_ok or not quality_ok:
                if not valid:
                    details = reason
                elif not checksum_ok:
                    details = "artifact checksum missing or mismatched"
                else:
                    details = "artifact has no passing QA record for the current locked quality policy"
                db.update_chapter_status(int(chapter["id"]), "warning", f"MP3 must be rebuilt: {details}")
                report.invalid_mp3 += 1

    db.event(
        "info",
        "RECOVERY_SCAN",
        "Project recovery scan completed",
        {
            "removed_part_files": report.removed_part_files,
            "reset_in_progress": report.reset_in_progress,
            "recovered_verified": report.recovered_verified,
            "requeued_asr": report.requeued_asr,
            "reset_missing_or_corrupt": report.reset_missing_or_corrupt,
            "invalid_mp3": report.invalid_mp3,
            "stale_leases": report.stale_leases,
            "candidate_resume_plans": report.candidate_resume_plans,
            "stale_candidates": report.stale_candidates,
            "invalidated_candidates": report.invalidated_candidates,
        },
    )
    return report
