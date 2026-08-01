from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .audio_io import inspect_wav, verify_mp3
from .database import ProjectDB
from .io_utils import remove_part_files, sha256_file
from .models import ProjectPaths


@dataclass(slots=True)
class RecoveryReport:
    removed_part_files: int = 0
    reset_in_progress: int = 0
    recovered_verified: int = 0
    reset_missing_or_corrupt: int = 0
    invalid_mp3: int = 0
    invalid_voice_references: int = 0
    stale_leases: int = 0
    completed_verified: bool = False


class RecoveryError(RuntimeError):
    pass


def recover_project(paths: ProjectPaths, db: ProjectDB, settings: dict) -> RecoveryReport:
    errors = db.integrity_check()
    if errors:
        raise RecoveryError("SQLite integrity check failed: " + "; ".join(errors[:10]))

    report = RecoveryReport()
    report.removed_part_files = len(remove_part_files(paths.root))
    report.reset_in_progress = db.reset_in_progress_segments()
    report.stale_leases = db.clear_all_worker_leases()

    if str(db.book()["status"]) == "completed":
        completed_ok = True
        chapters = db.list_chapters()
        for chapter in chapters:
            output = Path(str(chapter["output_mp3"] or ""))
            artifact = db.artifact_by_key(f"chapter_mp3:{chapter['chapter_index']}")
            valid, _ = verify_mp3(output)
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
            )
        if settings.get("audio", {}).get("combine_full_book", True):
            artifact = db.artifact_by_key("full_book_mp3")
            full_path = Path(str(artifact["path"])) if artifact and artifact["path"] else None
            full_path_safe = bool(
                full_path
                and full_path.resolve().is_relative_to(paths.output.resolve())
                and full_path.suffix.casefold() == ".mp3"
            )
            full_valid, _ = (
                verify_mp3(full_path) if full_path_safe and full_path else (False, "artifact missing or unsafe")
            )
            full_checksum_ok = bool(
                artifact
                and artifact["verified"]
                and artifact["sha256"]
                and full_path
                and full_path_safe
                and full_path.exists()
                and sha256_file(full_path) == str(artifact["sha256"])
            )
            completed_ok = completed_ok and full_valid and full_checksum_ok
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
            signal_ok, _, _ = inspect_wav(wav, str(row["text"]), settings)
            valid = checksum_ok and signal_ok
        if valid:
            report.recovered_verified += 1
        else:
            db.reset_segment_pending(int(row["id"]), "Recovery found missing/corrupt/checksum-mismatched WAV")
            report.reset_missing_or_corrupt += 1

    reference_text = str(settings["voices"]["reference_text"])
    for profile in db.list_voice_profiles():
        reference_value = str(profile["reference_wav"] or "")
        if not reference_value:
            continue
        reference = Path(reference_value)
        checksum_ok = bool(
            profile["reference_sha256"]
            and reference.exists()
            and sha256_file(reference) == str(profile["reference_sha256"])
        )
        signal_ok = False
        if reference.exists():
            signal_ok, _, _ = inspect_wav(reference, reference_text, settings)
        if not checksum_ok or not signal_ok:
            db.invalidate_voice_reference(
                int(profile["id"]),
                f"Voice reference không còn hợp lệ: {profile['voice_key']}",
            )
            report.invalid_voice_references += 1

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
            checksum_ok = bool(
                artifact
                and artifact["verified"]
                and artifact["sha256"]
                and output.exists()
                and sha256_file(output) == str(artifact["sha256"])
            )
            if not valid or not checksum_ok:
                details = reason if not valid else "artifact checksum missing or mismatched"
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
            "reset_missing_or_corrupt": report.reset_missing_or_corrupt,
            "invalid_mp3": report.invalid_mp3,
            "invalid_voice_references": report.invalid_voice_references,
            "stale_leases": report.stale_leases,
        },
    )
    return report
