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

from .config import PROFILE_OVERRIDES, build_settings, load_settings, settings_hash, validate_settings
from .database import SEGMENT_AUDIO_QUALITY_STAGE, ProjectDB
from .io_utils import natural_key, sha256_file, slugify
from .models import BookStatus, ChapterStatus, ProjectPaths
from .project import create_or_open_project, infer_book_title
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
DEFAULT_BACKGROUND_STARTUP_TIMEOUT_SECONDS = 45.0
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
    external = load_settings(paths.settings)
    book = db.book()
    try:
        locked = json.loads(str(book["settings_json"]))
    except (TypeError, json.JSONDecodeError) as exc:
        raise RuntimeError("Settings JSON in SQLite is corrupt") from exc
    if not isinstance(locked, dict):
        raise RuntimeError("Settings JSON in SQLite must be an object")
    validate_settings(locked)
    locked_hash = settings_hash(locked)
    if locked_hash != str(book["settings_hash"]):
        raise RuntimeError("Settings JSON in SQLite does not match its locked settings_hash")
    if settings_hash(external) != locked_hash:
        raise RuntimeError("book_settings.json differs from the settings locked in SQLite")
    return locked


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
        segment_qa = db.chapter_segments_have_current_audio_qa(
            chapter_id,
            SEGMENT_AUDIO_QUALITY_STAGE,
        )
        publishable = db.chapter_is_publishable(chapter_id)
        passed = decoded and checksum_ok and chapter_qa and segment_qa and publishable
        if passed:
            completed_quality_pass += 1
        else:
            errors.append(
                f"Chapter {chapter_index} completed artifact failed validation "
                f"(decode={decoded}, checksum={checksum_ok}, chapter_qa={chapter_qa}, "
                f"segment_qa={segment_qa}, publishable={publishable}): {reason}"
            )
        artifact_results.append(
            {
                "chapter_index": chapter_index,
                "path": str(output),
                "decode": decoded,
                "checksum": checksum_ok,
                "chapter_qa": chapter_qa,
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
        "torch",
        "whisper",
        "vieneu",
    ):
        checks[f"module:{module}"] = _find_module(module)
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
