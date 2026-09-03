from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import shutil
import signal
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
from collections import Counter, deque
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator, Sequence

from .config import (
    PROFILE_OVERRIDES,
    build_settings,
    is_legacy_director_settings,
    load_settings,
    load_settings_raw,
    normalize_legacy_locked_settings,
    settings_hash,
    validate_settings,
)
from .database import (
    SEGMENT_AUDIO_QUALITY_STAGE,
    SEGMENT_PERCEPTUAL_QUALITY_STAGE,
    ProjectDB,
)
from .character_registry import normalize_name
from .io_utils import natural_key, sha256_file, slugify
from .models import BookStatus, ChapterStatus, ProjectPaths
from .project import create_or_open_project, infer_book_title
from .runtime_contract import (
    critical_dependency_checks,
    perceptual_cache_check,
    setup_marker_check,
)
from .text_processing import build_chapter_manifest, input_manifest_hash


CLI_SCHEMA_VERSION = 1
EXIT_OK = 0
EXIT_RUNTIME_ERROR = 1
EXIT_USAGE = 2
EXIT_VALIDATION_FAILED = 3
EXIT_TEST_FAILED = 4
EXIT_INTERRUPTED = 130

DEFAULT_RANGE_SUFFIX = ".txt"
RANGE_PATTERN = re.compile(r"^(?P<start>\d+)\.\.(?P<end>\d+)$")
MAX_RANGE_ITEMS = 100_000
DEFAULT_BACKGROUND_STARTUP_TIMEOUT_SECONDS = 120.0
DEEP_DOCTOR_TIMEOUT_SECONDS = 180.0

TEST_COMPONENTS: dict[str, tuple[str, ...]] = {
    "config": ("tests/test_config.py",),
    "parser": ("tests/test_text_processing_safety.py",),
    "analysis-contract": ("tests/test_analysis_required.py",),
    "asr-policy": ("tests/test_asr_policy.py",),
    "audio": ("tests/test_audio_assembly.py",),
    "casting": ("tests/test_character_casting.py", "tests/test_voice_profile_lock.py"),
    "quality": ("tests/test_quality_policy.py", "tests/test_audio_assembly.py"),
    "db": ("tests/test_database_safety.py",),
    "recovery": ("tests/test_recovery.py",),
    "pipeline-mocked": ("tests/test_pipeline_mock.py",),
    "resource": ("tests/test_resource_manager.py",),
    "worker": ("tests/test_worker_safety.py", "tests/test_project_lock.py"),
    "full": ("tests",),
}
DEFAULT_TEST_COMPONENTS = (
    "config",
    "parser",
    "analysis-contract",
    "asr-policy",
    "audio",
    "casting",
    "quality",
    "db",
    "recovery",
    "pipeline-mocked",
    "resource",
    "worker",
)


class CliUsageError(ValueError):
    pass


class HeadlessArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise CliUsageError(message)


@dataclass(slots=True)
class CommandResult:
    data: dict[str, Any]
    exit_code: int = EXIT_OK
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.exit_code == EXIT_OK


def _normalize_path_key(path: Path) -> str:
    return str(path.resolve()).casefold()


def _numeric_range_names(spec: str, width: int | None = None) -> list[str]:
    match = RANGE_PATTERN.fullmatch(str(spec).strip())
    if match is None:
        raise CliUsageError("--range must use inclusive numeric syntax such as 000..099")
    start_token = match.group("start")
    end_token = match.group("end")
    start = int(start_token)
    end = int(end_token)
    if start > end:
        raise CliUsageError("--range start must not be greater than its end")
    count = end - start + 1
    if count > MAX_RANGE_ITEMS:
        raise CliUsageError(f"--range cannot select more than {MAX_RANGE_ITEMS} files")
    if width is not None and width < 1:
        raise CliUsageError("--width must be a positive integer")

    has_explicit_padding = (
        (len(start_token) > 1 and start_token.startswith("0"))
        or (len(end_token) > 1 and end_token.startswith("0"))
    )
    effective_width = width or (max(len(start_token), len(end_token)) if has_explicit_padding else 0)
    if effective_width and len(str(end)) > effective_width:
        raise CliUsageError("--width is too small for the end of --range")
    if effective_width:
        return [f"{value:0{effective_width}d}" for value in range(start, end + 1)]
    return [str(value) for value in range(start, end + 1)]


def resolve_input_selection(
    *,
    files: Sequence[Path | str] | None = None,
    source_dir: Path | str | None = None,
    range_spec: str | None = None,
    width: int | None = None,
) -> list[Path]:
    explicit_files = [Path(path).expanduser() for path in (files or ())]
    has_range_selection = source_dir is not None or range_spec is not None
    if explicit_files and has_range_selection:
        raise CliUsageError("Use either --files or --source-dir with --range, not both")
    if not explicit_files and (source_dir is None or range_spec is None):
        raise CliUsageError("Select inputs with --files or with both --source-dir and --range")
    if width is not None and not has_range_selection:
        raise CliUsageError("--width is only valid with --source-dir and --range")

    if explicit_files:
        candidates = explicit_files
    else:
        directory = Path(str(source_dir)).expanduser().resolve()
        if not directory.exists():
            raise FileNotFoundError(directory)
        if not directory.is_dir():
            raise NotADirectoryError(directory)
        names = _numeric_range_names(str(range_spec), width)
        candidates = [directory / f"{name}{DEFAULT_RANGE_SUFFIX}" for name in names]

    resolved: list[Path] = []
    seen: set[str] = set()
    missing: list[Path] = []
    invalid: list[Path] = []
    for candidate in candidates:
        path = candidate.resolve()
        if not path.is_file():
            missing.append(path)
            continue
        if path.suffix.casefold() != DEFAULT_RANGE_SUFFIX:
            invalid.append(path)
            continue
        key = _normalize_path_key(path)
        if key in seen:
            raise CliUsageError(f"Duplicate input file: {path}")
        seen.add(key)
        resolved.append(path)
    if missing:
        sample = ", ".join(str(path) for path in missing[:5])
        extra = f" (+{len(missing) - 5} more)" if len(missing) > 5 else ""
        raise FileNotFoundError(f"Missing input TXT file(s): {sample}{extra}")
    if invalid:
        raise CliUsageError("Every input must be a .txt file: " + ", ".join(map(str, invalid[:5])))
    return sorted(resolved, key=lambda path: natural_key(path.name))


def preview_project_creation(
    input_files: Sequence[Path],
    output_root: Path,
    settings: dict[str, Any],
    title: str | None = None,
) -> dict[str, Any]:
    validate_settings(settings)
    files = list(input_files)
    if not files:
        raise CliUsageError("At least one TXT file is required")
    output = output_root.expanduser().resolve()
    preview_output = output / ".manifest-preview" / "chapters"
    manifest = build_chapter_manifest(files, preview_output)
    manifest_digest = input_manifest_hash(manifest)
    book_title = (title or infer_book_title(files)).strip() or "audiobook"
    requested_settings_hash = settings_hash(settings)
    project_name = f"{slugify(book_title, 70)}_{manifest_digest[:10]}"
    project_root = output / project_name
    if (project_root / "book_settings.json").is_file():
        existing_settings = load_settings(project_root / "book_settings.json")
        if settings_hash(existing_settings) != requested_settings_hash:
            project_root = output / f"{project_name}_{requested_settings_hash[:8]}"
    return {
        "title": book_title,
        "output_root": str(output),
        "project_root": str(project_root),
        "chapter_count": len(manifest),
        "first_input": str(Path(manifest[0]["input_path"])),
        "last_input": str(Path(manifest[-1]["input_path"])),
        "input_names": [Path(str(row["input_path"])).name for row in manifest],
        "input_manifest_hash": manifest_digest,
        "settings_hash": requested_settings_hash,
        "quality_profile": str(settings["quality_profile"]),
    }


def _existing_project_paths(project_root: Path | str) -> ProjectPaths:
    root = Path(project_root).expanduser().resolve()
    if not root.is_dir():
        raise FileNotFoundError(f"Project directory does not exist: {root}")
    db = root / "project.sqlite3"
    settings = root / "book_settings.json"
    if not db.is_file() or not settings.is_file():
        raise FileNotFoundError(
            f"Not an Ebook Reader project (project.sqlite3/book_settings.json missing): {root}"
        )
    return ProjectPaths(
        root=root,
        db=db,
        settings=settings,
        logs=root / "logs",
        work=root / "work",
        chunks=root / "work" / "chunks",
        chapters=root / "output" / "chapters",
        output=root / "output",
        reports=root / "output" / "reports",
    )


class _ReadOnlyProjectDB(ProjectDB):
    """ProjectDB query API backed by SQLite URI mode=ro, without schema migration."""

    def __init__(self, path: Path) -> None:
        self.source_path = path.resolve()
        self.path = self.source_path
        self.synchronous = "FULL"
        self._snapshot_directory: tempfile.TemporaryDirectory[str] | None = None
        if any(
            self.source_path.with_name(self.source_path.name + suffix).exists()
            for suffix in ("-wal", "-shm")
        ):
            self._materialize_live_snapshot()

    @staticmethod
    def _file_signature(path: Path) -> tuple[bool, int, int]:
        try:
            stat = path.stat()
        except FileNotFoundError:
            return False, 0, 0
        return True, int(stat.st_size), int(stat.st_mtime_ns)

    def _materialize_live_snapshot(self) -> None:
        source_wal = self.source_path.with_name(self.source_path.name + "-wal")
        for _attempt in range(3):
            before = (self._file_signature(self.source_path), self._file_signature(source_wal))
            snapshot_directory = tempfile.TemporaryDirectory(prefix="ebook-reader-status-")
            snapshot = Path(snapshot_directory.name) / self.source_path.name
            try:
                shutil.copyfile(self.source_path, snapshot)
                if source_wal.is_file():
                    shutil.copyfile(source_wal, snapshot.with_name(snapshot.name + "-wal"))
                after = (self._file_signature(self.source_path), self._file_signature(source_wal))
                if before != after:
                    snapshot_directory.cleanup()
                    continue
                # Apply the copied WAL only inside the disposable snapshot. All
                # subsequent reads can then be immutable and cannot touch the
                # live project's -wal/-shm files.
                snapshot_conn = sqlite3.connect(snapshot)
                try:
                    snapshot_conn.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
                    snapshot_conn.execute("SELECT 1").fetchone()
                finally:
                    snapshot_conn.close()
                self._snapshot_directory = snapshot_directory
                self.path = snapshot
                return
            except (OSError, sqlite3.DatabaseError):
                snapshot_directory.cleanup()
        raise RuntimeError("Could not capture a stable read-only SQLite snapshot while the worker was writing")

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        uri = self.path.as_uri() + "?mode=ro&immutable=1"
        conn = sqlite3.connect(uri, timeout=60, isolation_level=None, uri=True)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA query_only=ON")
        conn.execute("PRAGMA foreign_keys=ON")
        try:
            yield conn
        finally:
            conn.close()


def _open_project(
    project_root: Path | str,
    *,
    read_only: bool = False,
) -> tuple[ProjectPaths, ProjectDB, dict[str, Any]]:
    paths = _existing_project_paths(project_root)
    settings = load_settings(paths.settings)
    db: ProjectDB
    if read_only:
        db = _ReadOnlyProjectDB(paths.db)
    else:
        db = ProjectDB(paths.db, synchronous=str(settings["safety"].get("sqlite_synchronous", "FULL")))
    locked = _load_locked_settings_read_only(paths, db)
    return paths, db, locked


def _load_locked_settings_read_only(paths: ProjectPaths, db: ProjectDB) -> dict[str, Any]:
    external = load_settings_raw(paths.settings)
    book = db.book()
    try:
        locked = json.loads(str(book["settings_json"]))
    except (TypeError, json.JSONDecodeError) as exc:
        raise RuntimeError("Settings JSON in SQLite is corrupt") from exc
    if not isinstance(locked, dict):
        raise RuntimeError("Settings JSON in SQLite must be an object")
    locked_hash = settings_hash(locked)
    if locked_hash != str(book["settings_hash"]):
        raise RuntimeError("Settings JSON in SQLite does not match its locked settings_hash")
    if settings_hash(external) != locked_hash:
        raise RuntimeError("book_settings.json differs from the settings locked in SQLite")
    effective = normalize_legacy_locked_settings(locked)
    validate_settings(effective)
    return effective


def _validate_analysis_provenance_read_only(
    db: ProjectDB,
    settings: dict[str, Any],
) -> None:
    analysis_started = db.casting_is_finalized() or any(
        str(row["status"]) != "pending" for row in db.list_segments()
    )
    if settings.get("quality_profile") != "high_quality" or not analysis_started:
        return
    raw_locked = json.loads(str(db.book()["settings_json"]))
    if not isinstance(raw_locked, dict):
        raise RuntimeError("Settings JSON in SQLite must be an object")
    if is_legacy_director_settings(raw_locked):
        raise RuntimeError(
            "Legacy high_quality analysis checkpoints predate mandatory director critic"
        )
    model_lock = db.analysis_model_lock()
    expected_model = str(settings.get("analysis", {}).get("model", ""))
    if model_lock is None or str(model_lock["model_name"]) != expected_model:
        raise RuntimeError(
            "High-quality analysis checkpoints are missing the locked model name/digest"
        )


def _validate_project_inputs_read_only(
    paths: ProjectPaths,
    db: ProjectDB,
    settings: dict[str, Any],
) -> None:
    for chapter in db.list_chapters():
        output = Path(str(chapter["output_mp3"])).resolve()
        if output.suffix.casefold() != ".mp3" or not output.is_relative_to(paths.chapters.resolve()):
            raise RuntimeError(f"Invalid chapter output path outside output/chapters: {output}")
        if not settings["safety"].get("stop_book_on_source_change", True):
            continue
        source = Path(str(chapter["input_path"]))
        if not source.is_file():
            raise RuntimeError(f"Source chapter is missing: {source}")
        if source.stat().st_size != int(chapter["input_size"]):
            raise RuntimeError(f"Source chapter size changed after project creation: {source}")
        if sha256_file(source) != str(chapter["input_sha256"]):
            raise RuntimeError(f"Source chapter content changed after project creation: {source}")


def _invoke_production_worker(
    project_root: str,
    message_queue: Any,
    pause_event: Any,
    stop_event: Any,
    parent_pid: int,
) -> None:
    from .worker import run_worker

    run_worker(project_root, message_queue, pause_event, stop_event, parent_pid)


def _background_status(project_root: Path) -> dict[str, Any]:
    from .background_runner import get_status

    return get_status(project_root).to_dict()


def collect_project_status(project_root: Path | str) -> dict[str, Any]:
    paths = _existing_project_paths(project_root)
    db = _ReadOnlyProjectDB(paths.db)
    with db.connect() as conn:
        book = conn.execute("SELECT * FROM book WHERE id=1").fetchone()
        if book is None:
            raise RuntimeError("Project database has not been initialized")
        chapter_rows = list(
            conn.execute("SELECT status,COUNT(*) AS count FROM chapters GROUP BY status ORDER BY status")
        )
        segment_rows = list(
            conn.execute("SELECT status,COUNT(*) AS count FROM segments GROUP BY status ORDER BY status")
        )
        table_names = {
            str(row[0])
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        leases = (
            [dict(row) for row in conn.execute("SELECT * FROM worker_leases ORDER BY worker_name")]
            if "worker_leases" in table_names
            else []
        )
    chapter_statuses = Counter({str(row["status"]): int(row["count"]) for row in chapter_rows})
    segment_statuses = Counter({str(row["status"]): int(row["count"]) for row in segment_rows})
    book_keys = set(book.keys())
    try:
        background = _background_status(paths.root)
    except (ImportError, OSError, RuntimeError, ValueError) as exc:
        background = {"state": "unavailable", "running": False, "detail": str(exc)}
    return {
        "project_root": str(paths.root),
        "title": str(book["title"]),
        "book_status": str(book["status"]),
        "stage": str(book["stage"]),
        "last_error": str(book["last_error"] or ""),
        "run_generation": int(book["run_generation"]) if "run_generation" in book_keys else 0,
        "casting_finalized": bool(book["casting_finalized"]) if "casting_finalized" in book_keys else False,
        "chapters": {
            "total": sum(chapter_statuses.values()),
            "by_status": dict(sorted(chapter_statuses.items())),
            "completed": chapter_statuses[ChapterStatus.COMPLETED.value],
            "failed": chapter_statuses[ChapterStatus.FAILED.value],
        },
        "segments": {
            "total": sum(segment_statuses.values()),
            "by_status": dict(sorted(segment_statuses.items())),
        },
        "worker_leases": leases,
        "background": background,
        "quality_report": str(paths.reports / "audiobook_quality_report.json"),
    }


def validate_project(project_root: Path | str, *, require_complete: bool = False) -> dict[str, Any]:
    from .audio_io import verify_mp3

    paths, db, settings = _open_project(project_root, read_only=True)
    errors: list[str] = []
    warnings: list[str] = []
    checks: dict[str, Any] = {}

    integrity_errors = db.integrity_check()
    checks["sqlite_integrity"] = not integrity_errors
    errors.extend(f"SQLite: {item}" for item in integrity_errors)

    book = db.book()
    try:
        _load_locked_settings_read_only(paths, db)
        checks["settings_lock"] = True
    except (KeyError, TypeError, ValueError, RuntimeError) as exc:
        checks["settings_lock"] = False
        errors.append(str(exc))
    try:
        _validate_analysis_provenance_read_only(db, settings)
        checks["analysis_model_lock"] = True
    except (
        IndexError,
        KeyError,
        TypeError,
        ValueError,
        RuntimeError,
        json.JSONDecodeError,
    ) as exc:
        checks["analysis_model_lock"] = False
        errors.append(str(exc))

    recorded_root = Path(str(book["project_root"])).resolve()
    checks["project_root"] = _normalize_path_key(recorded_root) == _normalize_path_key(paths.root)
    if not checks["project_root"]:
        errors.append(f"SQLite project_root points to {recorded_root}, expected {paths.root}")

    chapters = db.list_chapters()
    checks["has_chapters"] = bool(chapters)
    if not chapters:
        errors.append("Project has no chapters")
    try:
        manifest_digest = input_manifest_hash([dict(row) for row in chapters])
        checks["input_manifest_hash"] = manifest_digest == str(book["input_manifest_hash"])
        if not checks["input_manifest_hash"]:
            errors.append("Chapter manifest no longer matches the locked input_manifest_hash")
    except (KeyError, TypeError, ValueError) as exc:
        checks["input_manifest_hash"] = False
        errors.append(f"Cannot reconstruct input manifest: {exc}")

    try:
        _validate_project_inputs_read_only(paths, db, settings)
        checks["source_files"] = True
    except (OSError, RuntimeError, ValueError) as exc:
        checks["source_files"] = False
        errors.append(str(exc))

    completed = 0
    completed_quality_pass = 0
    artifact_results: list[dict[str, Any]] = []
    for chapter in chapters:
        chapter_id = int(chapter["id"])
        chapter_index = int(chapter["chapter_index"])
        segments = db.list_segments(chapter_id=chapter_id)
        counts = Counter(str(row["status"]) for row in segments)
        if len(segments) != int(chapter["total_segments"]):
            errors.append(
                f"Chapter {chapter_index}: total_segments={chapter['total_segments']} but SQLite has {len(segments)}"
            )
        expected_counts = {
            "verified_segments": counts["verified"],
            "warning_segments": counts["warning"],
            "failed_segments": counts["failed"],
        }
        for column, expected in expected_counts.items():
            if int(chapter[column]) != expected:
                errors.append(
                    f"Chapter {chapter_index}: {column}={chapter[column]} but segment rows imply {expected}"
                )

        if str(chapter["status"]) != ChapterStatus.COMPLETED.value:
            if str(chapter["status"]) == ChapterStatus.FAILED.value:
                warnings.append(f"Chapter {chapter_index} is failed: {chapter['last_error'] or ''}")
            continue

        completed += 1
        output = Path(str(chapter["output_mp3"])).resolve()
        artifact = db.artifact_by_key(f"chapter_mp3:{chapter_index}")
        decoded, reason = verify_mp3(output)
        checksum_ok = bool(
            artifact
            and artifact["verified"]
            and artifact["sha256"]
            and output.is_file()
            and sha256_file(output) == str(artifact["sha256"])
        )
        chapter_qa = db.chapter_artifact_is_current_qa_verified(chapter_index)
        segment_audio_qa = db.chapter_segments_have_current_audio_qa(
            chapter_id,
            SEGMENT_AUDIO_QUALITY_STAGE,
        )
        perceptual_qa_enabled = bool(
            settings.get("perceptual_qa", {}).get("enabled", False)
        )
        segment_perceptual_qa = (
            not perceptual_qa_enabled
            or db.chapter_segments_have_current_audio_qa(
                chapter_id,
                SEGMENT_PERCEPTUAL_QUALITY_STAGE,
            )
        )
        segment_qa = segment_audio_qa and segment_perceptual_qa
        publishable = db.chapter_is_publishable(chapter_id)
        passed = decoded and checksum_ok and chapter_qa and segment_qa and publishable
        if passed:
            completed_quality_pass += 1
        else:
            errors.append(
                f"Chapter {chapter_index} completed artifact failed validation "
                f"(decode={decoded}, checksum={checksum_ok}, chapter_qa={chapter_qa}, "
                f"segment_audio_qa={segment_audio_qa}, "
                f"segment_perceptual_qa={segment_perceptual_qa}, "
                f"publishable={publishable}): {reason}"
            )
        artifact_results.append(
            {
                "chapter_index": chapter_index,
                "path": str(output),
                "decode": decoded,
                "checksum": checksum_ok,
                "chapter_qa": chapter_qa,
                "segment_audio_qa": segment_audio_qa,
                "segment_perceptual_qa": segment_perceptual_qa,
                "segment_qa": segment_qa,
                "publishable": publishable,
                "passed": passed,
            }
        )

    all_complete = bool(chapters) and completed == len(chapters)
    all_completed_quality_pass = all_complete and completed_quality_pass == len(chapters)
    checks["all_chapters_complete"] = all_complete
    checks["all_completed_artifacts_current_qa"] = all_completed_quality_pass
    if require_complete and not all_complete:
        errors.append(f"Completion required, but only {completed}/{len(chapters)} chapters are completed")
    if require_complete and not all_completed_quality_pass:
        errors.append("Completion required, but not every chapter has current passing artifact QA")

    active_policy = db.current_quality_policy()
    checks["active_quality_policy"] = active_policy is not None
    if require_complete and active_policy is None:
        errors.append("Completion required, but the project has no active quality policy")

    report_path = paths.reports / "audiobook_quality_report.json"
    checks["quality_report_present"] = report_path.is_file()
    if require_complete and not report_path.is_file():
        errors.append("Completion required, but audiobook_quality_report.json is missing")
    elif report_path.is_file():
        try:
            report = json.loads(report_path.read_text(encoding="utf-8"))
            checks["quality_report_json"] = isinstance(report, dict)
            if require_complete and report.get("book", {}).get("overall_verdict") != "pass":
                errors.append("Completion required, but the quality report verdict is not pass")
        except (OSError, json.JSONDecodeError) as exc:
            checks["quality_report_json"] = False
            errors.append(f"Quality report is unreadable: {exc}")

    return {
        "project_root": str(paths.root),
        "ok": not errors,
        "require_complete": require_complete,
        "checks": checks,
        "chapter_count": len(chapters),
        "completed_count": completed,
        "completed_quality_pass": completed_quality_pass,
        "artifacts": artifact_results,
        "warnings": warnings,
        "errors": errors,
    }


class _EventSink:
    def __init__(self, *, echo: bool, max_events: int = 200) -> None:
        self.echo = echo
        self.events: deque[dict[str, Any]] = deque(maxlen=max_events)
        self.finished: dict[str, Any] | None = None

    def put(self, event: dict[str, Any]) -> None:
        item = dict(event)
        self.events.append(item)
        if item.get("kind") == "finished":
            self.finished = item
        if not self.echo:
            return
        kind = str(item.get("kind", "event"))
        text = str(item.get("text") or item.get("label") or "").strip()
        done = item.get("done")
        total = item.get("total")
        progress = f" {done}/{total}" if done is not None and total is not None else ""
        if text or progress:
            print(f"[{kind}] {text}{progress}", flush=True)


@contextmanager
def _stop_signal_handlers(stop_event: threading.Event) -> Iterator[dict[str, bool]]:
    state = {"interrupted": False}
    previous: dict[int, Any] = {}

    def handle_signal(_signum: int, _frame: Any) -> None:
        state["interrupted"] = True
        stop_event.set()

    if threading.current_thread() is threading.main_thread():
        for signum in (signal.SIGINT, signal.SIGTERM):
            try:
                previous[signum] = signal.getsignal(signum)
                signal.signal(signum, handle_signal)
            except (OSError, ValueError):
                pass
    try:
        yield state
    finally:
        for signum, handler in previous.items():
            try:
                signal.signal(signum, handler)
            except (OSError, ValueError):
                pass


def run_project_foreground(project_root: Path | str, *, echo: bool = True) -> CommandResult:
    paths, _db, _settings = _open_project(project_root)
    try:
        background = _background_status(paths.root)
    except (ImportError, OSError, RuntimeError, ValueError):
        background = {"running": False}
    if bool(background.get("running")):
        raise RuntimeError("A background supervisor is already running this project")

    pause_event = threading.Event()
    stop_event = threading.Event()
    sink = _EventSink(echo=echo)
    with _stop_signal_handlers(stop_event) as signal_state:
        _invoke_production_worker(
            str(paths.root),
            sink,
            pause_event,
            stop_event,
            os.getpid(),
        )
    status = collect_project_status(paths.root)
    data = {
        "mode": "foreground",
        "project_root": str(paths.root),
        "finished_event": sink.finished,
        "recent_events": list(sink.events),
        "status": status,
    }
    if signal_state["interrupted"]:
        return CommandResult(data=data, exit_code=EXIT_INTERRUPTED, error="Interrupted; checkpoint preserved")
    if sink.finished is not None and not bool(sink.finished.get("ok", False)):
        return CommandResult(
            data=data,
            exit_code=EXIT_RUNTIME_ERROR,
            error=str(sink.finished.get("text") or "Pipeline failed"),
        )
    if status["book_status"] == BookStatus.ERROR.value:
        return CommandResult(data=data, exit_code=EXIT_RUNTIME_ERROR, error=status["last_error"] or "Pipeline failed")
    return CommandResult(data=data)


def _settings_from_args(args: argparse.Namespace) -> dict[str, Any]:
    if args.settings_file is not None:
        return load_settings(Path(args.settings_file).expanduser().resolve())
    return build_settings(str(args.profile))


def _command_create(args: argparse.Namespace) -> CommandResult:
    if args.dry_run and args.start:
        raise CliUsageError("--dry-run cannot be combined with --start")
    files = resolve_input_selection(
        files=args.files,
        source_dir=args.source_dir,
        range_spec=args.range_spec,
        width=args.width,
    )
    settings = _settings_from_args(args)
    output_root = Path(args.output_root)
    preview = preview_project_creation(files, output_root, settings, args.title)
    preview["dry_run"] = bool(args.dry_run)
    if args.dry_run:
        return CommandResult(data=preview)

    paths, db, used_settings = create_or_open_project(files, output_root, settings, args.title)
    book = db.book()
    chapters = db.list_chapters()
    created = dict(preview)
    created.update(
        {
            "project_root": str(paths.root),
            "title": str(book["title"]),
            "book_status": str(book["status"]),
            "chapter_count": len(chapters),
            "first_input": str(chapters[0]["input_path"]),
            "last_input": str(chapters[-1]["input_path"]),
            "input_names": [Path(str(row["input_path"])).name for row in chapters],
            "input_manifest_hash": str(book["input_manifest_hash"]),
            "settings_hash": settings_hash(used_settings),
        }
    )
    if args.start:
        from .background_runner import start_background

        background = start_background(paths.root, startup_timeout=float(args.startup_timeout))
        created["background"] = background.to_dict()
    return CommandResult(data=created)


def _command_run(args: argparse.Namespace) -> CommandResult:
    paths = _existing_project_paths(args.project_root)
    if args.foreground:
        return run_project_foreground(paths.root, echo=not args.json)
    from .background_runner import start_background

    status = start_background(paths.root, startup_timeout=float(args.startup_timeout))
    return CommandResult(
        data={
            "mode": "background",
            "operation": str(args.command),
            "project_root": str(paths.root),
            "background": status.to_dict(),
        }
    )


def _command_status(args: argparse.Namespace) -> CommandResult:
    return CommandResult(data=collect_project_status(args.project_root))


def _command_stop(args: argparse.Namespace) -> CommandResult:
    paths = _existing_project_paths(args.project_root)
    from .background_runner import request_stop

    status = request_stop(
        paths.root,
        wait=not args.no_wait,
        timeout=float(args.timeout),
        force=bool(args.force),
    )
    data = {"project_root": str(paths.root), "background": status.to_dict()}
    if not args.no_wait and bool(status.running):
        return CommandResult(
            data=data,
            exit_code=EXIT_RUNTIME_ERROR,
            error=f"Stop request did not reach a terminal state before the {float(args.timeout):g}s timeout",
        )
    return CommandResult(data=data)


def _command_log(args: argparse.Namespace) -> CommandResult:
    paths = _existing_project_paths(args.project_root)
    from .background_runner import tail_log

    content = tail_log(paths.root, lines=int(args.lines))
    return CommandResult(data={"project_root": str(paths.root), "lines": int(args.lines), "log": content})


LISTENER_PRONUNCIATION_SOURCE = "listener_choice"


def _command_retry(args: argparse.Namespace) -> CommandResult:
    """Send failed segments back to be re-cut, without redoing the analysis.

    A failed segment is failed for the life of the project: _verify_chapter_audio skips
    anything already marked failed, so resuming after fixing an ASR defect re-verifies
    nothing and the chapter fails again on the same segments. The only way to benefit from
    the fix was a clean run - an hour of analysis to re-cut five segments - and any code
    change able to fix the analysis itself invalidates the resume fingerprint on top.

    alpha.32 made that concrete twice over. Chapter 6 was refused over one segment whose
    voice read it correctly and whose transcript differed only in "tháng Mười hai" against
    "tháng 12". The fix for that landed while the run was still going, and there was no way
    to apply it to the segment it was written for.

    Resets to `analyzed`, so the analysis and the casting stay: only the audio and the ASR
    evidence go. Then `resume` re-cuts and re-verifies exactly those segments.
    """
    paths = _existing_project_paths(args.project_root)
    stable_id = str(getattr(args, "segment", "") or "").strip() or None
    database = ProjectDB(paths.db)
    reset = database.retry_failed_segments(
        f"retry requested: {str(getattr(args, 'note', '') or 'no reason given')}",
        stable_id=stable_id,
    )
    if not reset:
        return CommandResult(
            data={"segment": stable_id, "reset": []},
            exit_code=EXIT_USAGE,
            error=(
                "Không có segment nào đang ở trạng thái failed để thử lại"
                if stable_id is None
                else "Segment đó không ở trạng thái failed"
            ),
        )
    return CommandResult(data={"reset": reset, "count": len(reset)}, exit_code=EXIT_OK)


def _command_accept(args: argparse.Namespace) -> CommandResult:
    """Record that a person listened to a take and accepted it despite the warning.

    High-quality policy refuses to publish a chapter whose segments carry warnings it does
    not allow, and PERCEPTUAL_NATURALNESS_REVIEW is one of those. The verifier is honest
    about what it means - a score well below the preset's own preview, asking for a human
    ear, not proof of a bad take - and the repair loop re-cuts the segment and sometimes
    cannot do better. At that point nothing can clear the warning and the chapter never
    publishes. That is a wall, not a gate, and it is the third one of these: `pronounce`
    exists because a reading needed a person, `cast` because a gender did, and this because
    a recording does.

    Tied to the checksum of the audio that was heard. Re-cutting the take voids it, because
    what was accepted is a recording, not a row.
    """
    paths = _existing_project_paths(args.project_root)
    stable_id = str(args.segment).strip()
    code = str(args.warning).strip()
    if not stable_id or not code:
        return CommandResult(
            data={}, exit_code=EXIT_USAGE, error="--segment and --warning must be non-empty"
        )
    database = ProjectDB(paths.db)
    with database.connect() as conn:
        row = conn.execute(
            "SELECT stable_id, wav_sha256, warning_code, status FROM segments WHERE stable_id=?",
            (stable_id,),
        ).fetchone()
    if row is None:
        return CommandResult(
            data={"segment": stable_id}, exit_code=EXIT_USAGE, error="Không có segment này"
        )
    checksum = str(row["wav_sha256"] or "")
    if not checksum:
        # Accepting audio that does not exist yet would be accepting whatever is made next.
        return CommandResult(
            data={"segment": stable_id},
            exit_code=EXIT_USAGE,
            error="Segment chưa có bản thu nào để nghe",
        )
    present = {value for value in str(row["warning_code"] or "").split("|") if value}
    was_failed = str(row["status"]) == "failed"
    if code not in present:
        return CommandResult(
            data={"segment": stable_id, "warning": code, "hiện có": sorted(present)},
            exit_code=EXIT_USAGE,
            error="Segment không mang cảnh báo đó",
        )
    if was_failed:
        # A failed segment needs its status moved as well: a chapter publishes only when
        # nothing is failed, so suppressing the warning alone would leave it blocked.
        database.accept_failed_segment_audio(
            segment_stable_id=stable_id,
            wav_sha256=checksum,
            warning_code=code,
            note=str(getattr(args, "note", "") or ""),
        )
    else:
        database.accept_segment_audio(
            segment_stable_id=stable_id,
            wav_sha256=checksum,
            warning_code=code,
            note=str(getattr(args, "note", "") or ""),
        )
    stored = database.accepted_segment_warnings().get((stable_id, checksum), set())
    if code not in stored:
        return CommandResult(
            data={"segment": stable_id, "warning": code},
            exit_code=EXIT_VALIDATION_FAILED,
            error="Không ghi được quyết định chấp nhận",
        )
    return CommandResult(
        data={
            "segment": stable_id,
            "warning": code,
            "wav_sha256": checksum,
            "accepted": True,
            "was_failed": was_failed,
        },
        exit_code=EXIT_OK,
    )


def _command_cast(args: argparse.Namespace) -> CommandResult:
    """Pin a character's gender, on a listener's say-so rather than a model's.

    alpha.30 finished all 948 segments of its analysis and then refused to cast:

        Casting input quality gate failed: gender conflicts={'NOAH': {'female': 2, 'male': 2}}

    The refusal is right - a character voiced as the wrong sex for a whole book is worse
    than a run that stops - but there was nothing a person could do about it. The gender
    lives in the analysis, the analysis is fingerprinted, and any code change that could
    settle the tie invalidates the fingerprint and costs the whole phase again. So a model
    error that a listener could answer in one second cost an hour of machine time instead.

    This is `pronounce` for casting: locked, so nothing downstream asks again, and readable
    before casting has ever run so the answer can be given ahead of the failure rather than
    only after it.
    """
    paths = _existing_project_paths(args.project_root)
    character = str(args.character).strip()
    gender = str(args.gender).strip().casefold()
    if not character:
        return CommandResult(data={}, exit_code=EXIT_USAGE, error="--character must not be empty")
    if gender not in {"male", "female"}:
        return CommandResult(
            data={}, exit_code=EXIT_USAGE, error="--gender must be male or female"
        )
    database = ProjectDB(paths.db)
    database.lock_character_gender(character, gender)
    stored = database.locked_character_genders().get(character.strip().upper())
    if stored != gender:
        # Reporting a write that did not happen is worse than failing.
        return CommandResult(
            data={"character": character, "requested": gender, "stored": stored},
            exit_code=EXIT_VALIDATION_FAILED,
            error="Không ghi được giới tính đã ghim",
        )
    return CommandResult(
        data={"character": character, "gender": gender, "locked": True},
        exit_code=EXIT_OK,
    )


def _command_pronounce(args: argparse.Namespace) -> CommandResult:
    """Pin how a name is read, on a listener's say-so rather than a model's.

    A four-letter word once stopped a ten-chapter book: "Deck" was refused by the CMUdict
    path for needing contextual review and by the local fallback for having a CMUdict
    entry, and high-quality analysis will not publish a name it could not resolve. The
    caution is right - a character's name mispronounced through a whole book is worse than
    the reader saying the Latin letters - but there was no way for a person to settle it
    except editing SQLite by hand.

    Locked, so nothing downstream asks again, and recorded under its own source so a human
    decision is never mistaken for a transliteration the machine produced.
    """
    paths = _existing_project_paths(args.project_root)
    surface = str(args.surface).strip()
    spoken = str(args.spoken).strip()
    if not surface or not spoken:
        return CommandResult(
            data={},
            exit_code=EXIT_USAGE,
            error="--surface and --spoken must both be non-empty",
        )
    database = ProjectDB(paths.db)
    before = {
        str(row["surface"]): dict(row)
        for row in database.list_pronunciations(0.0)
        if str(row["surface"]) == surface
    }
    database.set_listener_pronunciation(
        surface=surface,
        normalized_surface=normalize_name(surface),
        spoken_form=spoken,
        source=LISTENER_PRONUNCIATION_SOURCE,
    )
    stored = next(
        (
            str(row["spoken_form"])
            for row in database.list_pronunciations(0.0)
            if str(row["surface"]) == surface
        ),
        None,
    )
    if stored != spoken:
        # Reporting a write that did not happen is worse than failing: the first version
        # of this command said "ok" while a lock silently discarded every word of it.
        return CommandResult(
            data={"surface": surface, "requested": spoken, "stored": stored},
            exit_code=EXIT_VALIDATION_FAILED,
            error=f"Pronunciation for {surface!r} did not take: stored {stored!r}",
        )
    database.event(
        "info",
        "PRONUNCIATION_SET_BY_LISTENER",
        f"Người nghe chốt cách đọc {surface!r} là {spoken!r}.",
        {"surface": surface, "spoken_form": spoken},
    )
    return CommandResult(
        data={
            "project_root": str(paths.root),
            "surface": surface,
            "spoken_form": spoken,
            "locked": True,
            "source": LISTENER_PRONUNCIATION_SOURCE,
            "replaced": bool(before),
            "previous_spoken_form": (
                str(next(iter(before.values()))["spoken_form"]) if before else None
            ),
        }
    )


def _command_validate(args: argparse.Namespace) -> CommandResult:
    result = validate_project(args.project_root, require_complete=bool(args.require_complete))
    if result["ok"]:
        return CommandResult(data=result)
    return CommandResult(
        data=result,
        exit_code=EXIT_VALIDATION_FAILED,
        error=f"Project validation failed with {len(result['errors'])} error(s)",
    )


def _command_report(args: argparse.Namespace) -> CommandResult:
    paths = _existing_project_paths(args.project_root)
    report_path = paths.reports / "audiobook_quality_report.json"
    if not report_path.is_file():
        return CommandResult(
            data={"project_root": str(paths.root), "report_path": str(report_path), "present": False},
            exit_code=EXIT_VALIDATION_FAILED,
            error="The pipeline has not exported audiobook_quality_report.json yet",
        )
    report = json.loads(report_path.read_text(encoding="utf-8"))
    if not isinstance(report, dict):
        raise ValueError("audiobook_quality_report.json must contain a JSON object")
    if args.full:
        data = {"project_root": str(paths.root), "report_path": str(report_path), "report": report}
    else:
        data = {
            "project_root": str(paths.root),
            "report_path": str(report_path),
            "schema_version": report.get("schema_version"),
            "book": report.get("book", {}),
            "global_gates": report.get("global_gates", {}),
            "review_required": {
                "chapter_count": len(report.get("review_required", {}).get("chapters", [])),
                "segment_count": len(report.get("review_required", {}).get("segments", [])),
            },
        }
    return CommandResult(data=data)


def _find_module(name: str) -> dict[str, Any]:
    try:
        spec = importlib.util.find_spec(name)
    except (ImportError, ModuleNotFoundError, ValueError) as exc:
        return {"ok": False, "detail": str(exc)}
    return {"ok": spec is not None, "detail": str(spec.origin if spec is not None else "not installed")}


def _headroom_checks() -> dict[str, dict[str, Any]]:
    """Can this machine actually hold the work, rather than merely start it?

    doctor checked that every module imports and every asset exists, and said nothing about
    memory. So a machine too small for the job passed every check and then discovered the
    truth slowly: yielding to its own throttle on every gate, spilling the analysis model
    onto the CPU, or stopping mid-book on "available RAM 1.1 GB" - which is how alpha.26
    ended, 357 segments of 948 in.

    The thresholds themselves stay absolute, and that is deliberate: they guard allocations
    that are the same size on every machine. qwen3:8b holds 6.0 GB of VRAM at the context
    this profile derives, three synthesis workers hold 5,484 MiB, a scoring worker costs
    1.75 GB of RAM. A fraction of the machine is the wrong unit for a fixed-size model.
    What a small machine is owed is not a looser threshold but a straight answer up front,
    which is what this is.

    Every number here is measured and lives in the module that uses it, so this cannot
    drift away from what the run will really ask for.
    """
    import psutil

    from .perceptual_qa import PERCEPTUAL_WORKER_RAM_GB
    from .resource_manager import NvidiaProbe
    from .tts_pool import (
        TTS_POOL_BASE_VRAM_MB,
        TTS_POOL_FOREGROUND_RESERVE_MB,
        TTS_POOL_WORKER_VRAM_MB,
    )

    settings = build_settings()
    checks: dict[str, dict[str, Any]] = {}

    minimum_free = float(settings["resources"]["min_free_ram_gb"])
    # Two workers is the smallest thing worth calling a pool; below that the scoring
    # never runs beside ASR and the run keeps the sequential timeline it always had.
    required_ram_gb = minimum_free + 2 * PERCEPTUAL_WORKER_RAM_GB
    total_ram_gb = psutil.virtual_memory().total / 1024**3
    checks["headroom:ram"] = {
        "ok": total_ram_gb >= required_ram_gb,
        "detail": (
            f"{total_ram_gb:.1f} GB tổng; cần {required_ram_gb:.1f} GB "
            f"({minimum_free:.1f} ngưỡng nhường + 2 x {PERCEPTUAL_WORKER_RAM_GB:.2f} worker chấm điểm)"
        ),
    }

    free_mb, total_mb = NvidiaProbe().gpu_memory()
    if total_mb is None:
        checks["headroom:vram"] = {
            "ok": True,
            "detail": "không đọc được VRAM; mọi thứ chạy như trước khi phép đo này tồn tại",
        }
    else:
        pool_mb = TTS_POOL_BASE_VRAM_MB + 2 * TTS_POOL_WORKER_VRAM_MB
        required_mb = pool_mb + TTS_POOL_FOREGROUND_RESERVE_MB
        checks["headroom:vram"] = {
            "ok": total_mb >= required_mb,
            "detail": (
                f"{total_mb} MiB tổng, {free_mb} MiB trống; cần {required_mb} MiB "
                f"(pool 2 worker {pool_mb} + {TTS_POOL_FOREGROUND_RESERVE_MB} chừa foreground)"
            ),
        }
    return checks


def _command_doctor(args: argparse.Namespace) -> CommandResult:
    package_root = Path(__file__).resolve().parents[1]
    checks: dict[str, dict[str, Any]] = {}
    version_ok = (3, 11) <= sys.version_info[:2] < (3, 13)
    checks["python"] = {"ok": version_ok, "detail": sys.version.split()[0]}
    for module in (
        "requests",
        "psutil",
        "numpy",
        "scipy",
        "soundfile",
        "pyloudnorm",
        "pyworld",
        "imageio_ffmpeg",
        "whisper",
        "vieneu",
    ):
        checks[f"module:{module}"] = _find_module(module)
    for dependency, result in critical_dependency_checks().items():
        checks[f"runtime:{dependency}"] = result
    for executable in ("nvidia-smi", "ollama"):
        resolved = shutil.which(executable)
        checks[f"executable:{executable}"] = {"ok": bool(resolved), "detail": resolved or "not found"}
    asset_root = Path(__file__).resolve().parent / "assets"
    cmudict = asset_root / "cmudict.dict"
    previews = list((asset_root / "voice_previews").glob("*.wav"))
    checks["asset:cmudict"] = {"ok": cmudict.is_file(), "detail": str(cmudict)}
    checks["asset:voice_previews"] = {
        "ok": bool(previews),
        "detail": f"{len(previews)} WAV preview(s)",
    }
    checks.update(_headroom_checks())
    runtime_root = Path(os.environ["EBOOK_READER_RUNTIME"]).resolve()
    checks["runtime:setup_marker"] = setup_marker_check(runtime_root)
    checks["model:utmosv2_cache"] = perceptual_cache_check(runtime_root)
    deep_output = ""
    deep_returncode: int | None = None
    if args.deep:
        checker = package_root / "scripts" / "check_system.py"
        completed = subprocess.run(
            [sys.executable, str(checker)],
            cwd=package_root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env={**os.environ, "PYTHONUTF8": "1"},
            timeout=DEEP_DOCTOR_TIMEOUT_SECONDS,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0,
            check=False,
        )
        deep_returncode = int(completed.returncode)
        deep_output = ((completed.stdout or "") + (completed.stderr or ""))[-40_000:]
        checks["deep_system_check"] = {
            "ok": completed.returncode == 0,
            "detail": f"exit code {completed.returncode}",
        }
    failures = [name for name, result in checks.items() if not bool(result["ok"])]
    data = {
        "package_root": str(package_root),
        "deep": bool(args.deep),
        "checks": checks,
        "failures": failures,
        "deep_returncode": deep_returncode,
        "deep_output": deep_output,
    }
    if failures:
        return CommandResult(
            data=data,
            exit_code=EXIT_VALIDATION_FAILED,
            error=f"Doctor found {len(failures)} failing check(s)",
        )
    return CommandResult(data=data)


def _selected_test_paths(components: Sequence[str]) -> tuple[list[str], list[str]]:
    selected = list(components) or list(DEFAULT_TEST_COMPONENTS)
    if "full" in selected:
        return ["tests"], ["full"]
    unknown = [component for component in selected if component not in TEST_COMPONENTS]
    if unknown:
        raise CliUsageError("Unknown test component(s): " + ", ".join(unknown))
    paths: list[str] = []
    for component in selected:
        for path in TEST_COMPONENTS[component]:
            if path not in paths:
                paths.append(path)
    return paths, selected


def _command_test(args: argparse.Namespace) -> CommandResult:
    package_root = Path(__file__).resolve().parents[1]
    test_paths, components = _selected_test_paths(args.components)
    missing = [path for path in test_paths if not (package_root / path).exists()]
    if missing:
        raise FileNotFoundError("Test path(s) not installed: " + ", ".join(missing))
    command = [sys.executable, "-m", "pytest"]
    if not args.verbose:
        command.append("-q")
    if args.fail_fast:
        command.append("-x")
    command.extend(test_paths)
    started = time.monotonic()
    completed = subprocess.run(
        command,
        cwd=package_root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env={**os.environ, "PYTHONUTF8": "1"},
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0,
        check=False,
    )
    duration = time.monotonic() - started
    output = ((completed.stdout or "") + (completed.stderr or ""))[-80_000:]
    data = {
        "components": components,
        "test_paths": test_paths,
        "returncode": int(completed.returncode),
        "duration_seconds": round(duration, 3),
        "output": output,
    }
    if completed.returncode:
        return CommandResult(
            data=data,
            exit_code=EXIT_TEST_FAILED,
            error=f"Component tests failed with pytest exit code {completed.returncode}",
        )
    return CommandResult(data=data)


def _add_json_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--json", action="store_true", help="Emit one stable JSON result envelope")


def build_parser() -> argparse.ArgumentParser:
    parser = HeadlessArgumentParser(
        prog="ebook-reader-headless",
        description="Headless project creation, execution, validation, and QA for Ebook Reader.",
    )
    _add_json_argument(parser)
    subparsers = parser.add_subparsers(dest="command", required=True)

    create = subparsers.add_parser("create", help="Create or reopen a project from an exact TXT selection")
    create.add_argument("--output-root", required=True, type=Path)
    create.add_argument("--files", nargs="+", type=Path)
    create.add_argument("--source-dir", type=Path)
    create.add_argument("--range", dest="range_spec")
    create.add_argument("--width", type=int, help="Optional zero-padding width for numeric ranges")
    create.add_argument("--title")
    create.add_argument("--profile", choices=tuple(PROFILE_OVERRIDES), default="high_quality")
    create.add_argument("--settings-file", type=Path, help="Use a fully validated settings JSON instead")
    create.add_argument("--dry-run", action="store_true", help="Hash and preview without writing anything")
    create.add_argument("--start", action="store_true", help="Start the new project in the background")
    create.add_argument(
        "--startup-timeout",
        type=float,
        default=DEFAULT_BACKGROUND_STARTUP_TIMEOUT_SECONDS,
    )
    _add_json_argument(create)
    create.set_defaults(handler=_command_create)

    for name, help_text in (
        ("run", "Start a project, in the background by default"),
        ("resume", "Resume a project from its crash-safe checkpoint"),
    ):
        command = subparsers.add_parser(name, help=help_text)
        command.add_argument("project_root", type=Path)
        command.add_argument("--foreground", action="store_true", help="Block in this process for debugging")
        command.add_argument(
            "--startup-timeout",
            type=float,
            default=DEFAULT_BACKGROUND_STARTUP_TIMEOUT_SECONDS,
        )
        _add_json_argument(command)
        command.set_defaults(handler=_command_run)

    status = subparsers.add_parser("status", help="Show database and background-runner status")
    status.add_argument("project_root", type=Path)
    _add_json_argument(status)
    status.set_defaults(handler=_command_status)

    stop = subparsers.add_parser("stop", help="Request a checkpoint-safe stop from the background runner")
    stop.add_argument("project_root", type=Path)
    stop.add_argument("--no-wait", action="store_true")
    stop.add_argument("--timeout", type=float, default=30.0)
    stop.add_argument("--force", action="store_true", help="Force stop only after verified process identity")
    _add_json_argument(stop)
    stop.set_defaults(handler=_command_stop)

    log = subparsers.add_parser("log", help="Tail the headless background event log")
    log.add_argument("project_root", type=Path)
    log.add_argument("--lines", type=int, default=100)
    _add_json_argument(log)
    log.set_defaults(handler=_command_log)

    pronounce = subparsers.add_parser(
        "pronounce",
        help="Pin how a name is read, as a listener decision rather than a model guess",
    )
    pronounce.add_argument("project_root", type=Path)
    pronounce.add_argument("--surface", required=True, help="The name as written")
    pronounce.add_argument("--spoken", required=True, help="How it should be read aloud")
    _add_json_argument(pronounce)
    pronounce.set_defaults(handler=_command_pronounce)

    cast = subparsers.add_parser(
        "cast",
        help="Pin a character's gender, as a listener decision rather than a model guess",
    )
    cast.add_argument("project_root", type=Path)
    cast.add_argument("--character", required=True, help="The character's name as cast")
    cast.add_argument("--gender", required=True, choices=("male", "female"))
    _add_json_argument(cast)
    cast.set_defaults(handler=_command_cast)

    accept = subparsers.add_parser(
        "accept",
        help="Accept a take a warning flagged, after listening to it",
    )
    accept.add_argument("project_root", type=Path)
    accept.add_argument("--segment", required=True, help="stable_id of the segment")
    accept.add_argument("--warning", required=True, help="The warning code being accepted")
    accept.add_argument("--note", default="", help="Why, for whoever reads this later")
    _add_json_argument(accept)
    accept.set_defaults(handler=_command_accept)

    retry = subparsers.add_parser(
        "retry",
        help="Send failed segments back to be re-cut, keeping the analysis",
    )
    retry.add_argument("project_root", type=Path)
    retry.add_argument(
        "--segment", default="", help="One stable_id; omit to retry every failed segment"
    )
    retry.add_argument("--note", default="", help="Why, for whoever reads this later")
    _add_json_argument(retry)
    retry.set_defaults(handler=_command_retry)

    validate = subparsers.add_parser("validate", help="Validate locked inputs, SQLite, and committed output QA")
    validate.add_argument("project_root", type=Path)
    validate.add_argument("--require-complete", action="store_true")
    _add_json_argument(validate)
    validate.set_defaults(handler=_command_validate)

    report = subparsers.add_parser("report", help="Read the latest incrementally exported quality report")
    report.add_argument("project_root", type=Path)
    report.add_argument("--full", action="store_true")
    _add_json_argument(report)
    report.set_defaults(handler=_command_report)

    doctor = subparsers.add_parser("doctor", help="Check the headless runtime without loading GPU models")
    doctor.add_argument("--deep", action="store_true", help="Also run the full existing system checker")
    _add_json_argument(doctor)
    doctor.set_defaults(handler=_command_doctor)

    test = subparsers.add_parser("test", help="Run mapped headless component tests without loading models")
    test.add_argument("components", nargs="*", metavar="COMPONENT")
    test.add_argument("--fail-fast", action="store_true")
    test.add_argument("--verbose", action="store_true")
    _add_json_argument(test)
    test.set_defaults(handler=_command_test)
    return parser


def _print_text_result(command: str, result: CommandResult) -> None:
    if command == "log" and result.ok:
        print(str(result.data.get("log", "")), end="" if str(result.data.get("log", "")).endswith("\n") else "\n")
        return
    if command == "test":
        output = str(result.data.get("output", ""))
        if output:
            print(output, end="" if output.endswith("\n") else "\n")
    elif command == "create":
        print(json.dumps(result.data, ensure_ascii=False, indent=2))
    elif command in {"status", "validate", "report", "doctor", "run", "resume", "stop"}:
        print(json.dumps(result.data, ensure_ascii=False, indent=2))
    if result.error:
        print(f"ERROR: {result.error}", file=sys.stderr)


def _print_json_result(command: str, result: CommandResult) -> None:
    envelope = {
        "schema_version": CLI_SCHEMA_VERSION,
        "command": command,
        "ok": result.ok,
        "exit_code": result.exit_code,
        "data": result.data,
        "error": result.error,
    }
    print(json.dumps(envelope, ensure_ascii=False, sort_keys=True))


def main(argv: Sequence[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except (OSError, ValueError):
                pass
    arguments = list(argv) if argv is not None else sys.argv[1:]
    json_requested = "--json" in arguments
    command = next((item for item in arguments if item and not item.startswith("-")), "unknown")
    try:
        args = build_parser().parse_args(arguments)
        args.json = json_requested
        command = str(args.command)
        result = args.handler(args)
    except CliUsageError as exc:
        result = CommandResult(data={}, exit_code=EXIT_USAGE, error=str(exc))
    except KeyboardInterrupt:
        result = CommandResult(data={}, exit_code=EXIT_INTERRUPTED, error="Interrupted; checkpoint preserved")
    except Exception as exc:  # noqa: BLE001 - CLI boundary must always return a stable envelope.
        result = CommandResult(data={}, exit_code=EXIT_RUNTIME_ERROR, error=str(exc))

    if json_requested:
        _print_json_result(command, result)
    else:
        _print_text_result(command, result)
    return result.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
