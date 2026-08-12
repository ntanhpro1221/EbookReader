from __future__ import annotations

import json
import logging
import os
import sys
import threading
import traceback
from pathlib import Path
from queue import Empty, Queue
from typing import Any

import psutil

from .config import (
    deep_merge,
    is_legacy_director_settings,
    load_settings_raw,
    normalize_legacy_locked_settings,
    settings_hash,
    validate_settings,
)
from .database import ProjectDB
from .io_utils import sha256_file
from .models import BookStatus, ProjectPaths
from .notifier import WindowsNotifier
from .pipeline import BookPipeline, CriticalResourceStop, PipelineStopped
from .process_utils import terminate_process_tree
from .resource_manager import set_worker_priority
from .runtime_contract import runtime_contract_errors


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


def _emit_pipeline_result(message_queue: Queue, db: ProjectDB) -> None:
    book = db.book()
    if str(book["status"]) == BookStatus.ERROR.value:
        detail = str(book["last_error"] or "Pipeline kết thúc với lỗi.")
        _emit(
            message_queue,
            "finished",
            {
                "ok": False,
                "critical": True,
                "text": f"Pipeline kết thúc với lỗi: {detail}.",
            },
        )
        return
    _emit(message_queue, "finished", {"ok": True, "text": "Pipeline kết thúc."})


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
    external = load_settings_raw(paths.settings)
    book = db.book()
    try:
        locked = json.loads(str(book["settings_json"]))
    except (TypeError, json.JSONDecodeError) as exc:
        raise RuntimeError("Settings trong SQLite bị hỏng") from exc
    if not isinstance(locked, dict):
        raise RuntimeError("Settings trong SQLite phải là JSON object")
    locked_hash = settings_hash(locked)
    if locked_hash != str(book["settings_hash"]):
        raise RuntimeError("Settings trong SQLite không khớp settings_hash đã khóa")
    if settings_hash(external) != locked_hash:
        raise RuntimeError(
            "book_settings.json khác settings đã khóa trong SQLite; từ chối resume để tránh đổi giọng/model"
        )
    legacy_director_settings = is_legacy_director_settings(locked)
    effective = normalize_legacy_locked_settings(locked)
    validate_settings(effective)
    analysis_started = db.casting_is_finalized() or any(
        str(row["status"]) != "pending" for row in db.list_segments()
    )
    if effective.get("quality_profile") == "high_quality" and analysis_started:
        if legacy_director_settings:
            raise RuntimeError(
                "Project high_quality cũ đã có checkpoint phân tích nhưng chưa có "
                "director critic; hãy tạo project sạch để không trộn metadata cũ với policy mới"
            )
        model_lock = db.analysis_model_lock()
        expected_model = str(effective.get("analysis", {}).get("model", ""))
        if model_lock is None or str(model_lock["model_name"]) != expected_model:
            raise RuntimeError(
                "Project high_quality đã có checkpoint phân tích nhưng thiếu khóa model/digest hợp lệ"
            )
    return effective


def _apply_runtime_resource_overrides(
    locked_settings: dict[str, Any],
    resource_overrides: dict[str, Any] | None,
) -> dict[str, Any]:
    if not resource_overrides:
        return locked_settings
    settings = deep_merge(locked_settings, {"resources": resource_overrides})
    validate_settings(settings)
    return settings


def _apply_locked_model_cache_environment(settings: dict[str, Any]) -> bool:
    """Force high-quality inference to use the cache tree validated by the contract."""
    if settings.get("quality_profile") != "high_quality":
        return False

    runtime_root = Path(os.environ["EBOOK_READER_RUNTIME"]).resolve()
    locked_values = {
        "HF_HOME": str(runtime_root / "models" / "huggingface"),
        "HF_HUB_CACHE": str(runtime_root / "models" / "huggingface" / "hub"),
        "TORCH_HOME": str(runtime_root / "models" / "torch"),
    }
    os.environ.update(locked_values)

    # Normal worker startup reaches this before these modules are imported. Keep the
    # cached constants aligned as a defensive measure for embedded/test callers.
    cached_paths = (
        ("huggingface_hub.constants", "HF_HOME", locked_values["HF_HOME"]),
        ("huggingface_hub.constants", "HF_HUB_CACHE", locked_values["HF_HUB_CACHE"]),
        ("transformers.utils", "HF_HUB_CACHE", locked_values["HF_HUB_CACHE"]),
        ("transformers.utils.hub", "HF_HUB_CACHE", locked_values["HF_HUB_CACHE"]),
    )
    for module_name, attribute, value in cached_paths:
        module = sys.modules.get(module_name)
        if module is not None and hasattr(module, attribute):
            setattr(module, attribute, value)
    return True


def _apply_model_network_policy(settings: dict[str, Any]) -> bool:
    """Enforce the locked no-download policy before any model backend is loaded."""
    if settings.get("safety", {}).get("allow_network_downloads_during_job", False):
        return False

    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    os.environ["HF_DATASETS_OFFLINE"] = "1"

    cached_flags = (
        ("huggingface_hub.constants", "HF_HUB_OFFLINE"),
        ("transformers.utils", "_is_offline_mode"),
        ("transformers.utils.hub", "_is_offline_mode"),
        ("transformers.utils.import_utils", "_is_offline_mode"),
        ("datasets.config", "HF_DATASETS_OFFLINE"),
    )
    for module_name, attribute in cached_flags:
        module = sys.modules.get(module_name)
        if module is not None and hasattr(module, attribute):
            setattr(module, attribute, True)
    return True


def _validate_model_runtime_contract(settings: dict[str, Any]) -> None:
    if settings.get("quality_profile") != "high_quality":
        return
    runtime_root = Path(os.environ["EBOOK_READER_RUNTIME"]).resolve()
    errors = runtime_contract_errors(runtime_root, settings=settings)
    if errors:
        raise RuntimeError("High-quality runtime contract is invalid: " + "; ".join(errors))


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


class WorkerHeartbeat(threading.Thread):
    def __init__(self, db: ProjectDB, stop_flag: threading.Event, generation: int) -> None:
        super().__init__(name="ebook-reader-heartbeat", daemon=True)
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
        notify_on_critical_stop: bool,
    ) -> None:
        super().__init__(name="ebook-reader-parent-watchdog", daemon=True)
        self.parent_pid = parent_pid
        self.external_stop_event = external_stop_event
        self.local_stop = local_stop
        self.db = db
        self.project_root = project_root
        self.grace_seconds = max(3.0, float(grace_seconds))
        self.notify_on_critical_stop = notify_on_critical_stop

    def run(self) -> None:
        while not self.local_stop.wait(2.0):
            if not psutil.pid_exists(self.parent_pid):
                reason = "GUI process disappeared; worker is stopping and recovery will discard unfinished work"
                try:
                    self.db.event(
                        "warning",
                        "PARENT_PROCESS_EXITED",
                        reason,
                        {"parent_pid": self.parent_pid, "grace_seconds": self.grace_seconds},
                    )
                except Exception:
                    pass
                if self.notify_on_critical_stop:
                    try:
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
                    terminate_process_tree(os.getpid(), include_parent=False, grace_seconds=2.0)
                    os._exit(17)
                return


def run_worker(
    project_root_str: str,
    message_queue: Queue,
    pause_event: Any,
    stop_event: Any,
    parent_pid: int,
    runtime_resource_overrides: dict[str, Any] | None = None,
    resource_settings_queue: Any = None,
) -> None:
    project_root = Path(project_root_str).resolve()
    paths = ProjectPaths.build(project_root)
    local_stop = threading.Event()
    notifier = WindowsNotifier()
    run_lock = ProjectRunLock(paths.root / ".worker.lock")
    db: ProjectDB | None = None
    settings: dict[str, Any] | None = None

    def emit(kind: str, payload: dict[str, Any]) -> None:
        logging.info("EVENT %s %s", kind, payload)
        _emit(message_queue, kind, payload)

    try:
        run_lock.acquire()
        _configure_logging(paths.logs / "ebook_reader.log")
        bootstrap_db = ProjectDB(paths.db, synchronous="FULL")
        locked_settings = _load_locked_settings(paths, bootstrap_db)
        settings = _apply_runtime_resource_overrides(
            locked_settings,
            runtime_resource_overrides,
        )
        _apply_locked_model_cache_environment(settings)
        _apply_model_network_policy(settings)
        _validate_model_runtime_contract(settings)
        db = ProjectDB(
            paths.db,
            synchronous=str(settings["safety"].get("sqlite_synchronous", "FULL")),
        )
        _validate_project_inputs(paths, db, settings)
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
            bool(settings["safety"].get("notify_on_critical_stop", True)),
        )
        heartbeat.start()
        parent_watchdog.start()

        def poll_resource_updates() -> dict[str, Any] | None:
            if resource_settings_queue is None or settings is None:
                return None
            latest: dict[str, Any] | None = None
            while True:
                try:
                    candidate = resource_settings_queue.get_nowait()
                except (Empty, OSError, ValueError):
                    break
                if isinstance(candidate, dict):
                    latest = candidate
            if latest is None:
                return None
            updated = _apply_runtime_resource_overrides(settings, latest)
            settings["resources"] = updated["resources"]
            return dict(settings["resources"])

        pipeline = BookPipeline(
            paths=paths,
            db=db,
            settings=settings,
            pause_requested=pause_event.is_set,
            stop_requested=stop_event.is_set,
            emit=emit,
            resource_updates=poll_resource_updates,
        )
        _emit(
            message_queue,
            "worker_ready",
            {
                "pid": os.getpid(),
                "project_root": str(paths.root),
                "generation": generation,
            },
        )
        pipeline.prepare_recovery()
        pipeline.run(recovery_already_run=True)
        _emit_pipeline_result(message_queue, db)
    except PipelineStopped:
        assert db is not None
        db.update_book(status=BookStatus.STOPPED.value, stage="stopped", error="User/app stop requested")
        db.event("info", "PIPELINE_STOPPED", "Pipeline stopped after a stop request")
        _emit(
            message_queue,
            "finished",
            {"ok": True, "stopped": True, "text": "Đã dừng; lần sau có thể tiếp tục."},
        )
    except CriticalResourceStop as exc:
        _emit(
            message_queue,
            "finished",
            {"ok": False, "critical": True, "text": f"Đã dừng vì điều kiện an toàn: {exc}"},
        )
    except BaseException as exc:  # noqa: BLE001
        details = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
        logging.exception("Unrecoverable pipeline error")
        try:
            if db is None:
                raise RuntimeError("Database chưa mở được")
            db.update_book(status=BookStatus.ERROR.value, stage="unrecoverable_error", error=str(exc))
            db.event("critical", "UNRECOVERABLE_PIPELINE_ERROR", str(exc), {"traceback": details[-12000:]})
        except Exception:
            pass
        _emit(message_queue, "log", {"text": details})
        _emit(message_queue, "finished", {"ok": False, "critical": True, "text": str(exc)})
        if settings is None or settings.get("safety", {}).get("notify_on_critical_stop", True):
            try:
                title = str(db.book()["title"]) if db is not None else "Audiobook"
                notifier.critical_stop(title, str(exc), paths.root)
            except Exception:
                pass
    finally:
        local_stop.set()
        if db is not None:
            try:
                db.clear_worker_lease("pipeline")
            except Exception:
                pass
        run_lock.release()
