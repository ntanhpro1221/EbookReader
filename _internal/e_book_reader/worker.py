from __future__ import annotations

import json
import hashlib
import logging
import os
import sys
import threading
import time
import traceback
import urllib.request
from importlib import metadata
from pathlib import Path
from queue import Queue
from typing import Any

import psutil

from .config import load_settings, settings_hash, validate_settings
from .database import ProjectDB
from .io_utils import sha256_file
from .models import BookStatus, ProjectPaths
from .notifier import WindowsNotifier
from .pipeline import BookPipeline, CriticalResourceStop, PipelineStopped
from .resource_manager import set_worker_priority


def _configure_logging(log_file: Path) -> None:
    log_file.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
        handlers=[logging.FileHandler(log_file, encoding="utf-8")],
        force=True,
    )


def _emit(queue: Queue, kind: str, payload: dict[str, Any] | None = None) -> None:
    try:
        queue.put({"kind": kind, **(payload or {})})
    except Exception:
        pass


class ProjectRunLock:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.handle: Any = None

    def acquire(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.handle = self.path.open("a+b")
        self.handle.seek(0, os.SEEK_END)
        if self.handle.tell() == 0:
            self.handle.write(b"0")
            self.handle.flush()
        self.handle.seek(0)
        try:
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(self.handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(self.handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (OSError, BlockingIOError) as exc:
            self.handle.close()
            self.handle = None
            raise RuntimeError("Project này đang được một worker khác xử lý") from exc

    def release(self) -> None:
        if self.handle is None:
            return
        try:
            self.handle.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(self.handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(self.handle.fileno(), fcntl.LOCK_UN)
        except OSError:
            pass
        finally:
            self.handle.close()
            self.handle = None


def _load_locked_settings(paths: ProjectPaths, db: ProjectDB) -> dict[str, Any]:
    external = load_settings(paths.settings)
    book = db.book()
    try:
        locked = json.loads(str(book["settings_json"]))
    except (TypeError, json.JSONDecodeError) as exc:
        raise RuntimeError("Settings trong SQLite bị hỏng") from exc
    validate_settings(locked)
    locked_hash = settings_hash(locked)
    if locked_hash != str(book["settings_hash"]):
        raise RuntimeError("Settings trong SQLite không khớp settings_hash đã khóa")
    if settings_hash(external) != locked_hash:
        raise RuntimeError(
            "book_settings.json khác settings đã khóa trong SQLite; từ chối resume để tránh đổi giọng/model"
        )
    return locked


def _validate_project_inputs(paths: ProjectPaths, db: ProjectDB, settings: dict[str, Any]) -> None:
    for chapter in db.list_chapters():
        output = Path(str(chapter["output_mp3"])).resolve()
        if output.suffix.casefold() != ".mp3" or not output.is_relative_to(paths.chapters.resolve()):
            raise RuntimeError(
                f"Output chapter không hợp lệ hoặc nằm ngoài output/chapters: {output}"
            )
        if not settings["safety"].get("stop_book_on_source_change", True):
            continue
        source = Path(str(chapter["input_path"]))
        if not source.exists() or not source.is_file():
            raise RuntimeError(f"Source chapter không còn tồn tại: {source}")
        if source.stat().st_size != int(chapter["input_size"]):
            raise RuntimeError(f"Source chapter đã đổi kích thước sau khi project được tạo: {source}")
        if sha256_file(source) != str(chapter["input_sha256"]):
            raise RuntimeError(f"Source chapter đã thay đổi nội dung sau khi project được tạo: {source}")


def _runtime_fingerprint(settings: dict[str, Any]) -> tuple[dict[str, Any], str]:
    package_names = (
        "e_book_reader",
        "torch",
        "torchaudio",
        "vieneu",
        "voxcpm",
        "openai-whisper",
        "PySide6",
        "numpy",
        "soundfile",
    )
    versions: dict[str, str] = {}
    for name in package_names:
        try:
            versions[name] = metadata.version(name)
        except metadata.PackageNotFoundError as exc:
            raise RuntimeError(f"Thiếu package runtime bắt buộc: {name}") from exc

    analysis = settings["analysis"]
    ollama_digest: str | None = None
    if analysis.get("enabled", True):
        url = f"{str(analysis['base_url']).rstrip('/')}/api/tags"
        try:
            with urllib.request.urlopen(url, timeout=10) as response:  # noqa: S310 - URL is validated.
                tags = json.loads(response.read().decode("utf-8"))
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError("Không đọc được Ollama model digest để khóa runtime") from exc
        model_name = str(analysis["model"])
        for item in tags.get("models", []):
            if str(item.get("name", "")) == model_name or str(item.get("model", "")) == model_name:
                ollama_digest = str(item.get("digest", "")) or None
                break
        if ollama_digest is None:
            raise RuntimeError(f"Không tìm thấy Ollama model để khóa runtime: {model_name}")

    payload: dict[str, Any] = {
        "python": sys.version.split()[0],
        "packages": versions,
        "analysis_model": str(analysis["model"]),
        "analysis_model_digest": ollama_digest,
        "voxcpm_model": str(settings["tts"]["voxcpm_model"]),
        "voxcpm_revision": str(settings["tts"]["voxcpm_revision"]),
        "whisper_model": str(settings["asr"]["model"]),
    }
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return payload, hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class WorkerHeartbeat(threading.Thread):
    def __init__(self, db: ProjectDB, stop_flag: threading.Event, generation: int) -> None:
        super().__init__(name="e-book-reader-heartbeat", daemon=True)
        self.db = db
        self.stop_flag = stop_flag
        self.generation = generation

    def run(self) -> None:
        while not self.stop_flag.wait(5.0):
            try:
                self.db.lease_worker(
                    "pipeline",
                    os.getpid(),
                    self.generation,
                    "running",
                    metadata={"thread": self.name},
                )
            except Exception:
                pass


class ParentWatchdog(threading.Thread):
    def __init__(
        self,
        parent_pid: int,
        external_stop_event: Any,
        local_stop: threading.Event,
        db: ProjectDB,
        project_root: Path,
        grace_seconds: float,
    ) -> None:
        super().__init__(name="e-book-reader-parent-watchdog", daemon=True)
        self.parent_pid = parent_pid
        self.external_stop_event = external_stop_event
        self.local_stop = local_stop
        self.db = db
        self.project_root = project_root
        self.grace_seconds = max(3.0, float(grace_seconds))

    def run(self) -> None:
        while not self.local_stop.wait(2.0):
            if not psutil.pid_exists(self.parent_pid):
                reason = "GUI process disappeared; worker is stopping from its last safe checkpoint"
                try:
                    self.db.event(
                        "warning",
                        "PARENT_PROCESS_EXITED",
                        reason,
                        {"parent_pid": self.parent_pid, "grace_seconds": self.grace_seconds},
                    )
                    WindowsNotifier().critical_stop(
                        str(self.db.book()["title"]), reason, self.project_root, "parent watchdog"
                    )
                except Exception:
                    pass
                self.external_stop_event.set()
                # If a native CUDA call never returns, do not leave an orphan worker indefinitely.
                # os._exit is safe here because all committed outputs are atomic and the current
                # generating segment will be reset by Recovery Scan.
                if not self.local_stop.wait(self.grace_seconds):
                    os._exit(17)
                return


def run_worker(
    project_root_str: str,
    message_queue: Queue,
    pause_event: Any,
    stop_event: Any,
    parent_pid: int,
) -> None:
    project_root = Path(project_root_str).resolve()
    paths = ProjectPaths.build(project_root)
    local_stop = threading.Event()
    notifier = WindowsNotifier()
    run_lock = ProjectRunLock(paths.root / ".worker.lock")
    db: ProjectDB | None = None

    def emit(kind: str, payload: dict[str, Any]) -> None:
        logging.info("EVENT %s %s", kind, payload)
        _emit(message_queue, kind, payload)

    try:
        run_lock.acquire()
        bootstrap_db = ProjectDB(paths.db, synchronous="FULL")
        settings = _load_locked_settings(paths, bootstrap_db)
        db = ProjectDB(
            paths.db,
            synchronous=str(settings["safety"].get("sqlite_synchronous", "FULL")),
        )
        _validate_project_inputs(paths, db, settings)
        runtime_payload, runtime_hash = _runtime_fingerprint(settings)
        db.bind_runtime_fingerprint(runtime_payload, runtime_hash)
        if not settings.get("safety", {}).get("allow_network_downloads_during_job", False):
            # Setup must prefetch models. A running book must not unexpectedly download or change model revisions.
            os.environ["HF_HUB_OFFLINE"] = "1"
            os.environ["TRANSFORMERS_OFFLINE"] = "1"
            os.environ["HF_DATASETS_OFFLINE"] = "1"
        _configure_logging(paths.logs / "e_book_reader.log")
        set_worker_priority(str(settings["resources"].get("worker_priority", "below_normal")))

        generation = int(db.book()["run_generation"]) + 1
        heartbeat = WorkerHeartbeat(db, local_stop, generation)
        parent_watchdog = ParentWatchdog(
            parent_pid,
            stop_event,
            local_stop,
            db,
            paths.root,
            float(settings["resources"].get("parent_exit_grace_seconds", 12)),
        )
        heartbeat.start()
        parent_watchdog.start()
        pipeline = BookPipeline(
            paths=paths,
            db=db,
            settings=settings,
            pause_requested=pause_event.is_set,
            stop_requested=stop_event.is_set,
            emit=emit,
        )
        pipeline.run()
        _emit(message_queue, "finished", {"ok": True, "text": "Pipeline kết thúc."})
    except PipelineStopped:
        assert db is not None
        db.update_book(status=BookStatus.STOPPED.value, stage="stopped_at_checkpoint", error="User/app stop requested")
        db.event("info", "PIPELINE_STOPPED", "Pipeline stopped at a safe checkpoint")
        _emit(
            message_queue,
            "finished",
            {"ok": True, "stopped": True, "text": "Đã dừng tại checkpoint; lần sau có thể tiếp tục."},
        )
    except CriticalResourceStop as exc:
        _emit(
            message_queue,
            "finished",
            {"ok": False, "critical": True, "text": f"Tự dừng an toàn: {exc}"},
        )
    except BaseException as exc:  # noqa: BLE001
        details = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
        logging.exception("Unrecoverable pipeline error")
        try:
            if db is None:
                raise RuntimeError("Database chưa mở được")
            db.update_book(status=BookStatus.ERROR.value, stage="unrecoverable_error", error=str(exc))
            db.event("critical", "UNRECOVERABLE_PIPELINE_ERROR", str(exc), {"traceback": details[-12000:]})
            notifier.critical_stop(str(db.book()["title"]), str(exc), paths.root)
        except Exception:
            pass
        _emit(message_queue, "log", {"text": details})
        _emit(message_queue, "finished", {"ok": False, "critical": True, "text": str(exc)})
    finally:
        local_stop.set()
        if db is not None:
            try:
                db.clear_worker_lease("pipeline")
            except Exception:
                pass
        run_lock.release()
