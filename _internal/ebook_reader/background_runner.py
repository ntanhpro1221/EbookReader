from __future__ import annotations

import argparse
import json
import multiprocessing as mp
import os
import subprocess
import sys
import time
import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from queue import Empty
from typing import Any, Callable, Mapping, Sequence

import psutil

from .io_utils import atomic_write_json
from .process_utils import terminate_process_tree


STATE_SCHEMA_VERSION = 1
BACKGROUND_DIRECTORY = Path("runtime") / "background"
STATE_FILE_NAME = "state.json"
HANDSHAKE_FILE_NAME = "handshake.json"
SUPERVISOR_LOCK_FILE_NAME = "supervisor.lock"
LAUNCH_LOCK_FILE_NAME = "launch.lock"
STOP_REQUEST_FILE_NAME = "stop.request"
EVENTS_FILE_NAME = "events.jsonl"
LOG_FILE_NAME = "supervisor.log"
ACTIVE_STATES = frozenset({"starting", "running", "stopping"})
TERMINAL_STATES = frozenset({"completed", "stopped", "failed", "lost"})
SUPERVISOR_MODULE = "ebook_reader.background_runner"
SUPERVISOR_COMMAND = "supervise"
DEFAULT_STARTUP_TIMEOUT_SECONDS = 45.0
DEFAULT_STOP_TIMEOUT_SECONDS = 30.0
WORKER_BOOTSTRAP_TIMEOUT_SECONDS = 30.0
STATUS_HEARTBEAT_SECONDS = 5.0
STATE_EVENT_FLUSH_SECONDS = 1.0
SUPERVISOR_POLL_SECONDS = 0.25
PROCESS_CREATE_TIME_TOLERANCE_SECONDS = 1.0
QUEUE_DRAIN_GRACE_SECONDS = 0.75
WORKER_READY_EVENT = "worker_ready"


class BackgroundAlreadyRunning(RuntimeError):
    pass


class BackgroundStartError(RuntimeError):
    pass


class BackgroundIdentityError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class BackgroundPaths:
    project_root: Path
    root: Path
    state: Path
    handshake: Path
    supervisor_lock: Path
    launch_lock: Path
    stop_request: Path
    events: Path
    log: Path

    @classmethod
    def for_project(cls, project_root: Path | str) -> "BackgroundPaths":
        """Build path values without touching the filesystem."""
        project = Path(project_root).expanduser().resolve()
        root = project / BACKGROUND_DIRECTORY
        return cls(
            project_root=project,
            root=root,
            state=root / STATE_FILE_NAME,
            handshake=root / HANDSHAKE_FILE_NAME,
            supervisor_lock=root / SUPERVISOR_LOCK_FILE_NAME,
            launch_lock=root / LAUNCH_LOCK_FILE_NAME,
            stop_request=root / STOP_REQUEST_FILE_NAME,
            events=root / EVENTS_FILE_NAME,
            log=root / LOG_FILE_NAME,
        )

    def ensure_root(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)


@dataclass(frozen=True, slots=True)
class BackgroundStatus:
    project_root: Path
    state: str
    running: bool
    instance_id: str | None = None
    supervisor_pid: int | None = None
    worker_pid: int | None = None
    started_at: str | None = None
    updated_at: str | None = None
    finished_at: str | None = None
    exit_code: int | None = None
    stop_requested: bool = False
    last_event: dict[str, Any] | None = None
    detail: str | None = None

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["project_root"] = str(self.project_root)
        return result


WorkerTarget = Callable[[str, Any, Any, Any, int, dict[str, Any] | None, Any], None]


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, UnicodeError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _append_line(path: Path, line: str) -> None:
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(line.rstrip("\r\n") + "\n")
        handle.flush()


def _append_log(paths: BackgroundPaths, message: str) -> None:
    _append_line(paths.log, f"{_utc_now()} | {message}")


def _append_event(paths: BackgroundPaths, event: Mapping[str, Any]) -> None:
    payload = json.dumps(dict(event), ensure_ascii=False, separators=(",", ":"), default=str)
    _append_line(paths.events, payload)
    _append_log(paths, f"EVENT {event.get('kind', 'unknown')} {payload}")


def _process_create_time(pid: int) -> float | None:
    try:
        return float(psutil.Process(pid).create_time())
    except (psutil.Error, ValueError, TypeError):
        return None


def _normal_path_text(path: Path | str) -> str:
    return os.path.normcase(os.path.normpath(str(path)))


def _validate_supervisor_identity(
    state: Mapping[str, Any],
    project_root: Path,
) -> tuple[bool, str]:
    try:
        pid = int(state["supervisor_pid"])
        expected_create_time = float(state["supervisor_create_time"])
        instance_id = str(state["instance_id"])
    except (KeyError, TypeError, ValueError):
        return False, "metadata tiến trình nền không đầy đủ"

    try:
        process = psutil.Process(pid)
        actual_create_time = float(process.create_time())
        command = process.cmdline()
    except psutil.NoSuchProcess:
        return False, "supervisor không còn chạy"
    except (psutil.AccessDenied, psutil.Error) as exc:
        return False, f"không thể xác minh supervisor: {exc}"

    if abs(actual_create_time - expected_create_time) > PROCESS_CREATE_TIME_TOLERANCE_SECONDS:
        return False, "PID đã được tái sử dụng bởi tiến trình khác"

    command_text = "\n".join(str(value) for value in command)
    command_folded = command_text.casefold()
    expected_project = _normal_path_text(project_root).casefold()
    normalized_command = _normal_path_text(command_text).casefold()
    required_tokens = (SUPERVISOR_MODULE.casefold(), SUPERVISOR_COMMAND, instance_id.casefold())
    if not all(token in command_folded for token in required_tokens):
        return False, "command line không khớp supervisor/token đã ghi"
    if expected_project not in normalized_command:
        return False, "command line không khớp project đã ghi"
    return True, "identity hợp lệ"


class _MetadataFileLock:
    """A one-byte OS lock with human-readable owner metadata in the same file."""

    def __init__(self, path: Path, *, purpose: str, instance_id: str, project_root: Path) -> None:
        self.path = path
        self.purpose = purpose
        self.instance_id = instance_id
        self.project_root = project_root
        self.handle: Any = None

    def acquire(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        handle = self.path.open("a+b")
        handle.seek(0, os.SEEK_END)
        if handle.tell() == 0:
            handle.write(b" ")
            handle.flush()
        handle.seek(0)
        try:
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (OSError, BlockingIOError) as exc:
            handle.close()
            raise BackgroundAlreadyRunning(f"{self.purpose} đang được tiến trình khác giữ") from exc

        self.handle = handle
        self._write_metadata(released_at=None)

    def _write_metadata(self, *, released_at: str | None) -> None:
        if self.handle is None:
            return
        payload = {
            "schema_version": STATE_SCHEMA_VERSION,
            "purpose": self.purpose,
            "instance_id": self.instance_id,
            "project_root": str(self.project_root),
            "pid": os.getpid(),
            "process_create_time": _process_create_time(os.getpid()),
            "acquired_at": _utc_now(),
            "released_at": released_at,
        }
        encoded = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self.handle.seek(0)
        self.handle.truncate()
        self.handle.write(encoded)
        self.handle.flush()
        os.fsync(self.handle.fileno())

    def release(self) -> None:
        if self.handle is None:
            return
        try:
            self._write_metadata(released_at=_utc_now())
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

    def __enter__(self) -> "_MetadataFileLock":
        self.acquire()
        return self

    def __exit__(self, _exc_type: Any, _exc: Any, _traceback: Any) -> None:
        self.release()


def _status_from_state(paths: BackgroundPaths, state: Mapping[str, Any]) -> BackgroundStatus:
    recorded_state = str(state.get("state", "lost"))
    active = recorded_state in ACTIVE_STATES
    identity_ok = False
    identity_detail: str | None = None
    if active and state.get("supervisor_pid") is not None:
        identity_ok, identity_detail = _validate_supervisor_identity(state, paths.project_root)

    if active and not identity_ok:
        if state.get("supervisor_pid") is None:
            detail = str(state.get("detail") or "supervisor chưa hoàn tất handshake")
            display_state = "starting"
        else:
            detail = identity_detail or "không thể xác minh supervisor"
            display_state = "lost"
        running = False
    else:
        detail = str(state["detail"]) if state.get("detail") is not None else None
        display_state = recorded_state
        running = active and identity_ok

    def optional_int(name: str) -> int | None:
        try:
            return int(state[name]) if state.get(name) is not None else None
        except (TypeError, ValueError):
            return None

    last_event = state.get("last_event")
    return BackgroundStatus(
        project_root=paths.project_root,
        state=display_state,
        running=running,
        instance_id=str(state["instance_id"]) if state.get("instance_id") else None,
        supervisor_pid=optional_int("supervisor_pid"),
        worker_pid=optional_int("worker_pid"),
        started_at=str(state["started_at"]) if state.get("started_at") else None,
        updated_at=str(state["updated_at"]) if state.get("updated_at") else None,
        finished_at=str(state["finished_at"]) if state.get("finished_at") else None,
        exit_code=optional_int("exit_code"),
        stop_requested=bool(state.get("stop_requested", False)),
        last_event=dict(last_event) if isinstance(last_event, dict) else None,
        detail=detail,
    )


def get_status(project_root: Path | str) -> BackgroundStatus:
    """Read background status without creating files or opening/migrating the project DB."""
    paths = BackgroundPaths.for_project(project_root)
    if not paths.state.is_file():
        return BackgroundStatus(project_root=paths.project_root, state="not_started", running=False)
    state = _read_json(paths.state)
    if state is None:
        return BackgroundStatus(
            project_root=paths.project_root,
            state="lost",
            running=False,
            detail="state.json không đọc được hoặc bị hỏng",
        )
    return _status_from_state(paths, state)


def _tail_lines(path: Path, lines: int) -> str:
    if lines <= 0 or not path.is_file():
        return ""
    block_size = 8192
    chunks: list[bytes] = []
    newline_count = 0
    with path.open("rb") as handle:
        handle.seek(0, os.SEEK_END)
        position = handle.tell()
        while position > 0 and newline_count <= lines:
            size = min(block_size, position)
            position -= size
            handle.seek(position)
            chunk = handle.read(size)
            chunks.append(chunk)
            newline_count += chunk.count(b"\n")
    text = b"".join(reversed(chunks)).decode("utf-8", errors="replace")
    return "\n".join(text.splitlines()[-lines:])


def tail_log(project_root: Path | str, *, lines: int = 100) -> str:
    """Return the last supervisor log lines without mutating the project."""
    paths = BackgroundPaths.for_project(project_root)
    return _tail_lines(paths.log, max(0, int(lines)))


def _default_python_executable() -> Path:
    current = Path(sys.executable).resolve()
    if os.name == "nt" and current.name.casefold() == "python.exe":
        pythonw = current.with_name("pythonw.exe")
        if pythonw.is_file():
            return pythonw
    return current


def _detached_creation_flags() -> int:
    if os.name != "nt":
        return 0
    return (
        getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
        | getattr(subprocess, "DETACHED_PROCESS", 0x00000008)
        | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200)
    )


def _spawn_detached_supervisor(
    paths: BackgroundPaths,
    instance_id: str,
    python_executable: Path,
) -> subprocess.Popen[bytes]:
    command = [
        str(python_executable),
        "-m",
        SUPERVISOR_MODULE,
        SUPERVISOR_COMMAND,
        "--project-root",
        str(paths.project_root),
        "--instance-id",
        instance_id,
    ]
    environment = os.environ.copy()
    environment["PYTHONUTF8"] = "1"
    package_root = Path(__file__).resolve().parents[1]
    log_handle = paths.log.open("ab", buffering=0)
    kwargs: dict[str, Any] = {
        "cwd": str(package_root),
        "env": environment,
        "stdin": subprocess.DEVNULL,
        "stdout": log_handle,
        "stderr": subprocess.STDOUT,
        "close_fds": True,
    }
    if os.name == "nt":
        kwargs["creationflags"] = _detached_creation_flags()
    else:
        kwargs["start_new_session"] = True
    try:
        return subprocess.Popen(command, **kwargs)
    finally:
        log_handle.close()


def _write_launching_state(paths: BackgroundPaths, instance_id: str) -> None:
    now = _utc_now()
    atomic_write_json(
        paths.state,
        {
            "schema_version": STATE_SCHEMA_VERSION,
            "project_root": str(paths.project_root),
            "instance_id": instance_id,
            "state": "starting",
            "supervisor_pid": None,
            "supervisor_create_time": None,
            "worker_pid": None,
            "worker_create_time": None,
            "started_at": now,
            "updated_at": now,
            "finished_at": None,
            "exit_code": None,
            "stop_requested": False,
            "last_event": None,
            "detail": "đang chờ supervisor handshake",
        },
    )


def _clear_stale_control_files(paths: BackgroundPaths, previous_status: BackgroundStatus) -> None:
    if previous_status.running:
        return
    for path in (paths.stop_request, paths.handshake):
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass


def _record_launch_failure(paths: BackgroundPaths, instance_id: str, detail: str) -> None:
    state = _read_json(paths.state) or {
        "schema_version": STATE_SCHEMA_VERSION,
        "project_root": str(paths.project_root),
        "instance_id": instance_id,
        "started_at": _utc_now(),
    }
    if state.get("instance_id") not in {None, instance_id}:
        return
    now = _utc_now()
    state.update(
        {
            "instance_id": instance_id,
            "state": "failed",
            "updated_at": now,
            "finished_at": now,
            "exit_code": 1,
            "detail": detail,
        }
    )
    atomic_write_json(paths.state, state)


def _terminate_owned_launch(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    terminate_process_tree(int(process.pid), include_parent=True, grace_seconds=4.0)
    try:
        process.wait(timeout=1.0)
    except (AttributeError, OSError, subprocess.TimeoutExpired):
        pass


def start_background(
    project_root: Path | str,
    *,
    python_executable: Path | str | None = None,
    startup_timeout: float = DEFAULT_STARTUP_TIMEOUT_SECONDS,
) -> BackgroundStatus:
    paths = BackgroundPaths.for_project(project_root)
    if not paths.project_root.is_dir():
        raise BackgroundStartError(f"Project không tồn tại: {paths.project_root}")
    for required in (paths.project_root / "project.sqlite3", paths.project_root / "book_settings.json"):
        if not required.is_file():
            raise BackgroundStartError(f"Project thiếu file bắt buộc: {required}")

    executable = (
        Path(python_executable).expanduser().resolve()
        if python_executable
        else _default_python_executable()
    )
    if not executable.is_file():
        raise BackgroundStartError(f"Không tìm thấy Python runtime: {executable}")

    paths.ensure_root()
    instance_id = uuid.uuid4().hex
    launch_lock = _MetadataFileLock(
        paths.launch_lock,
        purpose="background launch",
        instance_id=instance_id,
        project_root=paths.project_root,
    )
    with launch_lock:
        previous_status = get_status(paths.project_root)
        if previous_status.running:
            raise BackgroundAlreadyRunning(
                f"Project đã có background supervisor: {previous_status.supervisor_pid or 'đang khởi động'}"
            )
        _clear_stale_control_files(paths, previous_status)
        _write_launching_state(paths, instance_id)
        _append_log(paths, f"LAUNCH instance={instance_id} project={paths.project_root}")
        try:
            process = _spawn_detached_supervisor(paths, instance_id, executable)
        except OSError as exc:
            detail = f"không thể spawn supervisor: {exc}"
            _record_launch_failure(paths, instance_id, detail)
            raise BackgroundStartError(detail) from exc

        deadline = time.monotonic() + max(0.1, float(startup_timeout))
        while time.monotonic() < deadline:
            handshake = _read_json(paths.handshake)
            if handshake and handshake.get("instance_id") == instance_id:
                outcome = str(handshake.get("outcome", "")).casefold()
                if outcome == "ready":
                    status = get_status(paths.project_root)
                    if status.instance_id == instance_id:
                        if status.running or status.state in {"completed", "stopped"}:
                            return status
                        if status.state == "failed":
                            raise BackgroundStartError(
                                status.detail or "Background worker failed immediately after READY"
                            )
                    detail = status.detail or "READY handshake không có supervisor hợp lệ"
                    _terminate_owned_launch(process)
                    _record_launch_failure(paths, instance_id, detail)
                    raise BackgroundStartError(detail)
                if outcome == "error":
                    detail = str(handshake.get("detail") or "Supervisor khởi động thất bại")
                    _terminate_owned_launch(process)
                    _record_launch_failure(paths, instance_id, detail)
                    raise BackgroundStartError(detail)
            exit_code = process.poll()
            if exit_code is not None:
                log_tail = tail_log(paths.project_root, lines=30)
                detail = (
                    f"Supervisor kết thúc trước READY (exit code {exit_code})."
                    + (f"\n{log_tail}" if log_tail else "")
                )
                _record_launch_failure(paths, instance_id, detail)
                raise BackgroundStartError(detail)
            time.sleep(0.05)

        _terminate_owned_launch(process)
        log_tail = tail_log(paths.project_root, lines=30)
        detail = (
            f"Supervisor không gửi READY trong {float(startup_timeout):g} giây."
            + (f"\n{log_tail}" if log_tail else "")
        )
        _record_launch_failure(paths, instance_id, detail)
        raise BackgroundStartError(detail)


def _wait_for_terminal(project_root: Path, instance_id: str, timeout: float) -> BackgroundStatus:
    deadline = time.monotonic() + max(0.0, timeout)
    status = get_status(project_root)
    while status.instance_id == instance_id and status.running and time.monotonic() < deadline:
        time.sleep(0.1)
        status = get_status(project_root)
    return status


def request_stop(
    project_root: Path | str,
    *,
    wait: bool = True,
    timeout: float = DEFAULT_STOP_TIMEOUT_SECONDS,
    force: bool = False,
) -> BackgroundStatus:
    paths = BackgroundPaths.for_project(project_root)
    status = get_status(paths.project_root)
    if status.state == "not_started" or status.state in {"completed", "stopped", "failed"}:
        return status
    state = _read_json(paths.state)
    if state is None:
        raise BackgroundIdentityError("Không thể đọc state để xác minh supervisor")
    identity_ok, detail = _validate_supervisor_identity(state, paths.project_root)
    if not identity_ok:
        raise BackgroundIdentityError(f"Từ chối gửi stop: {detail}")

    instance_id = str(state["instance_id"])
    original_pid = int(state["supervisor_pid"])
    original_create_time = float(state["supervisor_create_time"])
    atomic_write_json(
        paths.stop_request,
        {
            "schema_version": STATE_SCHEMA_VERSION,
            "project_root": str(paths.project_root),
            "instance_id": instance_id,
            "requested_at": _utc_now(),
            "requester_pid": os.getpid(),
            "force": bool(force),
        },
    )
    if not wait:
        return get_status(paths.project_root)

    status = _wait_for_terminal(paths.project_root, instance_id, float(timeout))
    if status.running and force:
        force_lock = _MetadataFileLock(
            paths.launch_lock,
            purpose="background force stop",
            instance_id=instance_id,
            project_root=paths.project_root,
        )
        try:
            force_lock.acquire()
        except BackgroundAlreadyRunning as exc:
            raise BackgroundIdentityError(
                "Từ chối dừng cưỡng bức vì một lần launch khác đang thay đổi ownership"
            ) from exc
        try:
            latest = _read_json(paths.state)
            if latest is None:
                raise BackgroundIdentityError("State biến mất trước khi dừng cưỡng bức")
            try:
                latest_identity = (
                    str(latest["instance_id"]),
                    int(latest["supervisor_pid"]),
                    float(latest["supervisor_create_time"]),
                )
            except (KeyError, TypeError, ValueError) as exc:
                raise BackgroundIdentityError("State thiếu identity trước khi dừng cưỡng bức") from exc
            expected_identity = (instance_id, original_pid, original_create_time)
            if latest_identity != expected_identity:
                raise BackgroundIdentityError(
                    "Từ chối dừng cưỡng bức vì background instance đã thay đổi"
                )
            identity_ok, detail = _validate_supervisor_identity(latest, paths.project_root)
            if not identity_ok:
                raise BackgroundIdentityError(f"Từ chối dừng cưỡng bức: {detail}")
            terminate_process_tree(original_pid, include_parent=True, grace_seconds=4.0)

            current = _read_json(paths.state)
            if current is None or str(current.get("instance_id")) != instance_id:
                raise BackgroundIdentityError(
                    "Không ghi đè state vì background instance đã thay đổi sau khi dừng"
                )
            now = _utc_now()
            current.update(
                {
                    "state": "stopped",
                    "updated_at": now,
                    "finished_at": now,
                    "exit_code": -9,
                    "stop_requested": True,
                    "detail": "đã dừng cưỡng bức sau khi hết thời gian chờ stop sạch",
                }
            )
            atomic_write_json(paths.state, current)
            return _status_from_state(paths, current)
        finally:
            force_lock.release()
    return status


def _terminal_result(last_finished: Mapping[str, Any] | None, exit_code: int, stop_requested: bool) -> tuple[str, int, str]:
    if last_finished is not None:
        if bool(last_finished.get("ok")):
            if bool(last_finished.get("stopped")) or stop_requested:
                return "stopped", 0, str(last_finished.get("text") or "worker đã dừng sạch")
            return "completed", 0, str(last_finished.get("text") or "pipeline hoàn tất")
        return "failed", 1, str(last_finished.get("text") or "pipeline kết thúc với lỗi")
    if exit_code != 0:
        return "failed", 1, f"worker thoát với exit code {exit_code}"
    if stop_requested:
        return "stopped", 0, "worker đã dừng sau stop request"
    return "failed", 1, "worker thoát mà không gửi terminal event"


def _stop_request_matches(paths: BackgroundPaths, instance_id: str) -> bool:
    request = _read_json(paths.stop_request)
    if request is None:
        return False
    return (
        request.get("instance_id") == instance_id
        and _normal_path_text(str(request.get("project_root", ""))) == _normal_path_text(paths.project_root)
    )


def _write_handshake(paths: BackgroundPaths, instance_id: str, outcome: str, detail: str) -> None:
    atomic_write_json(
        paths.handshake,
        {
            "schema_version": STATE_SCHEMA_VERSION,
            "instance_id": instance_id,
            "project_root": str(paths.project_root),
            "outcome": outcome,
            "detail": detail,
            "written_at": _utc_now(),
        },
    )


def _record_worker_event(
    paths: BackgroundPaths,
    state: dict[str, Any],
    event: Mapping[str, Any],
) -> dict[str, Any]:
    normalized = {str(key): value for key, value in event.items()}
    normalized["observed_at"] = _utc_now()
    _append_event(paths, normalized)
    state["last_event"] = normalized
    return normalized


def run_supervisor(
    project_root: Path | str,
    instance_id: str,
    *,
    worker_target: WorkerTarget | None = None,
    poll_seconds: float = SUPERVISOR_POLL_SECONDS,
) -> int:
    """Run the foreground supervisor. Only the detached module entrypoint calls this in production."""
    paths = BackgroundPaths.for_project(project_root)
    paths.ensure_root()
    supervisor_lock = _MetadataFileLock(
        paths.supervisor_lock,
        purpose="background supervisor",
        instance_id=instance_id,
        project_root=paths.project_root,
    )
    worker: mp.Process | None = None
    message_queue: Any = None
    state: dict[str, Any] = {}
    handshake_written = False
    try:
        supervisor_lock.acquire()
        current = _read_json(paths.state)
        if current and current.get("instance_id") not in {None, instance_id}:
            raise BackgroundStartError("instance token không khớp launch request hiện tại")

        now = _utc_now()
        supervisor_pid = os.getpid()
        state = {
            "schema_version": STATE_SCHEMA_VERSION,
            "project_root": str(paths.project_root),
            "instance_id": instance_id,
            "state": "starting",
            "supervisor_pid": supervisor_pid,
            "supervisor_create_time": _process_create_time(supervisor_pid),
            "worker_pid": None,
            "worker_create_time": None,
            "started_at": str(current.get("started_at")) if current and current.get("started_at") else now,
            "updated_at": now,
            "finished_at": None,
            "exit_code": None,
            "stop_requested": False,
            "last_event": None,
            "detail": "supervisor đang khởi tạo worker",
        }
        atomic_write_json(paths.state, state)
        _append_log(paths, f"SUPERVISOR_START pid={supervisor_pid} instance={instance_id}")

        if worker_target is None:
            from .worker import run_worker

            worker_target = run_worker
        context = mp.get_context("spawn")
        message_queue = context.Queue()
        pause_event = context.Event()
        stop_event = context.Event()
        worker = context.Process(
            target=worker_target,
            args=(str(paths.project_root), message_queue, pause_event, stop_event, supervisor_pid, None, None),
            name="ebook-reader-background-worker",
            daemon=False,
        )
        worker.start()
        state.update(
            {
                "worker_pid": worker.pid,
                "worker_create_time": _process_create_time(int(worker.pid)),
                "updated_at": _utc_now(),
                "detail": "đang chờ worker khóa và xác minh project",
            }
        )
        atomic_write_json(paths.state, state)

        stop_requested = False
        last_finished: dict[str, Any] | None = None
        worker_ready = False
        bootstrap_deadline = time.monotonic() + WORKER_BOOTSTRAP_TIMEOUT_SECONDS
        while time.monotonic() < bootstrap_deadline:
            try:
                event = message_queue.get(timeout=max(0.01, float(poll_seconds)))
            except (Empty, EOFError, OSError, ValueError):
                event = None
            if isinstance(event, dict):
                normalized_event = _record_worker_event(paths, state, event)
                kind = str(normalized_event.get("kind", ""))
                if kind == "finished":
                    last_finished = normalized_event
                if kind == WORKER_READY_EVENT:
                    try:
                        ready_pid = int(normalized_event["pid"])
                        ready_project = Path(str(normalized_event["project_root"])).resolve()
                    except (KeyError, TypeError, ValueError) as exc:
                        raise BackgroundStartError("worker_ready thiếu identity bắt buộc") from exc
                    if ready_pid != int(worker.pid) or ready_project != paths.project_root:
                        raise BackgroundStartError("worker_ready không khớp worker/project đã spawn")
                    worker_ready = True
                    break
            if not worker.is_alive():
                break

        if not worker_ready:
            worker.join(timeout=1.0)
            if last_finished is not None:
                bootstrap_detail = str(
                    last_finished.get("text") or "worker lỗi trước khi xác minh project"
                )
            elif worker.is_alive():
                bootstrap_detail = (
                    f"worker không gửi {WORKER_READY_EVENT} trong "
                    f"{WORKER_BOOTSTRAP_TIMEOUT_SECONDS:g} giây"
                )
            else:
                bootstrap_detail = (
                    "worker thoát trước khi xác minh project"
                    f" (exit code {worker.exitcode})"
                )
            raise BackgroundStartError(bootstrap_detail)

        state.update(
            {
                "state": "running",
                "updated_at": _utc_now(),
                "detail": "background supervisor và worker đã xác minh project",
            }
        )
        atomic_write_json(paths.state, state)
        _write_handshake(paths, instance_id, "ready", "supervisor và worker đã khởi động")
        handshake_written = True
        _append_log(paths, f"READY supervisor_pid={supervisor_pid} worker_pid={worker.pid}")

        last_state_write = time.monotonic()
        next_heartbeat = last_state_write + STATUS_HEARTBEAT_SECONDS
        while worker.is_alive():
            if not stop_requested and _stop_request_matches(paths, instance_id):
                stop_requested = True
                stop_event.set()
                state.update(
                    {
                        "state": "stopping",
                        "stop_requested": True,
                        "updated_at": _utc_now(),
                        "detail": "đã chuyển stop request tới worker; đang chờ checkpoint sạch",
                    }
                )
                atomic_write_json(paths.state, state)
                _append_log(paths, "STOP_REQUEST forwarded to worker")

            try:
                event = message_queue.get(timeout=max(0.01, float(poll_seconds)))
            except (Empty, EOFError, OSError, ValueError):
                event = None
            if isinstance(event, dict):
                normalized_event = _record_worker_event(paths, state, event)
                if normalized_event.get("kind") == "finished":
                    last_finished = normalized_event

            monotonic_now = time.monotonic()
            if monotonic_now >= next_heartbeat or (
                event is not None and monotonic_now - last_state_write >= STATE_EVENT_FLUSH_SECONDS
            ):
                state["updated_at"] = _utc_now()
                atomic_write_json(paths.state, state)
                last_state_write = monotonic_now
                next_heartbeat = monotonic_now + STATUS_HEARTBEAT_SECONDS

        worker.join(timeout=1.0)
        drain_deadline = time.monotonic() + QUEUE_DRAIN_GRACE_SECONDS
        while time.monotonic() < drain_deadline:
            try:
                event = message_queue.get(timeout=0.05)
            except (Empty, EOFError, OSError, ValueError):
                continue
            if isinstance(event, dict):
                normalized_event = _record_worker_event(paths, state, event)
                if normalized_event.get("kind") == "finished":
                    last_finished = normalized_event

        worker_exit_code = int(worker.exitcode) if worker.exitcode is not None else 1
        terminal_state, supervisor_exit_code, detail = _terminal_result(
            last_finished,
            worker_exit_code,
            stop_requested,
        )
        finished_at = _utc_now()
        state.update(
            {
                "state": terminal_state,
                "updated_at": finished_at,
                "finished_at": finished_at,
                "exit_code": supervisor_exit_code,
                "stop_requested": stop_requested,
                "detail": detail,
            }
        )
        atomic_write_json(paths.state, state)
        _append_log(
            paths,
            f"SUPERVISOR_END state={terminal_state} worker_exit={worker_exit_code} exit={supervisor_exit_code}",
        )
        return supervisor_exit_code
    except BaseException as exc:  # noqa: BLE001
        detail = f"supervisor startup/runtime error: {type(exc).__name__}: {exc}"
        now = _utc_now()
        if not state:
            state = {
                "schema_version": STATE_SCHEMA_VERSION,
                "project_root": str(paths.project_root),
                "instance_id": instance_id,
                "started_at": now,
                "supervisor_pid": os.getpid(),
                "supervisor_create_time": _process_create_time(os.getpid()),
                "worker_pid": worker.pid if worker is not None else None,
                "worker_create_time": _process_create_time(int(worker.pid)) if worker and worker.pid else None,
                "stop_requested": False,
                "last_event": None,
            }
        state.update(
            {
                "state": "failed",
                "updated_at": now,
                "finished_at": now,
                "exit_code": 1,
                "detail": detail,
            }
        )
        try:
            atomic_write_json(paths.state, state)
            _append_log(paths, f"ERROR {detail}")
            if not handshake_written:
                _write_handshake(paths, instance_id, "error", detail)
        except OSError:
            pass
        return 1
    finally:
        if worker is not None and worker.is_alive():
            try:
                terminate_process_tree(int(worker.pid), include_parent=True, grace_seconds=4.0)
            except Exception:
                pass
        if message_queue is not None:
            try:
                message_queue.close()
                message_queue.join_thread()
            except (OSError, ValueError):
                pass
        supervisor_lock.release()


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Internal detached supervisor for Ebook Reader")
    subparsers = parser.add_subparsers(dest="command", required=True)
    supervise = subparsers.add_parser(SUPERVISOR_COMMAND, help=argparse.SUPPRESS)
    supervise.add_argument("--project-root", required=True)
    supervise.add_argument("--instance-id", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _build_parser().parse_args(argv)
    if arguments.command == SUPERVISOR_COMMAND:
        return run_supervisor(arguments.project_root, arguments.instance_id)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
