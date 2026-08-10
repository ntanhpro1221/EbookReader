from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path
from typing import Any

import pytest

from ebook_reader import background_runner
from ebook_reader.background_runner import (
    BackgroundAlreadyRunning,
    BackgroundIdentityError,
    BackgroundPaths,
    BackgroundStartError,
    BackgroundStatus,
    _MetadataFileLock,
    _spawn_detached_supervisor,
    get_status,
    request_stop,
    run_supervisor,
    start_background,
    tail_log,
)
from ebook_reader.io_utils import atomic_write_json


def _fake_worker_success(
    project_root: str,
    message_queue: Any,
    _pause_event: Any,
    _stop_event: Any,
    _parent_pid: int,
    _resource_overrides: dict[str, Any] | None,
    _resource_queue: Any,
) -> None:
    message_queue.put(
        {"kind": "worker_ready", "pid": os.getpid(), "project_root": project_root}
    )
    message_queue.put({"kind": "progress", "text": "fake worker running"})
    message_queue.put({"kind": "finished", "ok": True, "text": "fake complete"})


def _fake_worker_wait_for_stop(
    project_root: str,
    message_queue: Any,
    _pause_event: Any,
    stop_event: Any,
    _parent_pid: int,
    _resource_overrides: dict[str, Any] | None,
    _resource_queue: Any,
) -> None:
    message_queue.put(
        {"kind": "worker_ready", "pid": os.getpid(), "project_root": project_root}
    )
    message_queue.put({"kind": "progress", "text": "waiting for fake stop"})
    if not stop_event.wait(5.0):
        message_queue.put({"kind": "finished", "ok": False, "text": "stop timeout"})
        return
    message_queue.put(
        {"kind": "finished", "ok": True, "stopped": True, "text": "fake stopped cleanly"}
    )


def _fake_worker_fails_before_ready(
    _project_root: str,
    message_queue: Any,
    _pause_event: Any,
    _stop_event: Any,
    _parent_pid: int,
    _resource_overrides: dict[str, Any] | None,
    _resource_queue: Any,
) -> None:
    message_queue.put(
        {"kind": "finished", "ok": False, "critical": True, "text": "bootstrap rejected"}
    )


def _make_project(tmp_path: Path) -> Path:
    project = tmp_path / "book_project"
    project.mkdir()
    (project / "project.sqlite3").write_bytes(b"test-placeholder")
    (project / "book_settings.json").write_text("{}", encoding="utf-8")
    return project


def _active_state(project: Path, instance_id: str = "run-token") -> dict[str, Any]:
    return {
        "schema_version": 1,
        "project_root": str(project.resolve()),
        "instance_id": instance_id,
        "state": "running",
        "supervisor_pid": os.getpid(),
        "supervisor_create_time": 1.0,
        "worker_pid": 1234,
        "worker_create_time": 2.0,
        "started_at": "2026-08-10T00:00:00Z",
        "updated_at": "2026-08-10T00:00:00Z",
        "finished_at": None,
        "exit_code": None,
        "stop_requested": False,
        "last_event": None,
        "detail": "running",
    }


def test_status_of_missing_project_is_read_only(tmp_path: Path) -> None:
    project = tmp_path / "does-not-exist"

    status = get_status(project)

    assert status.state == "not_started"
    assert status.running is False
    assert not project.exists()


def test_status_of_terminal_run_does_not_require_live_pid(tmp_path: Path) -> None:
    project = _make_project(tmp_path)
    paths = BackgroundPaths.for_project(project)
    paths.ensure_root()
    state = _active_state(project)
    state.update({"state": "completed", "finished_at": "2026-08-10T01:00:00Z", "exit_code": 0})
    atomic_write_json(paths.state, state)

    before = paths.state.read_bytes()
    status = get_status(project)

    assert status.state == "completed"
    assert status.running is False
    assert status.exit_code == 0
    assert paths.state.read_bytes() == before


def test_tail_log_returns_only_requested_utf8_lines(tmp_path: Path) -> None:
    project = _make_project(tmp_path)
    paths = BackgroundPaths.for_project(project)
    paths.ensure_root()
    paths.log.write_text("một\nhai\nba\nbốn\n", encoding="utf-8")

    assert tail_log(project, lines=2) == "ba\nbốn"
    assert tail_log(project, lines=0) == ""


def test_metadata_lock_rejects_simultaneous_owner(tmp_path: Path) -> None:
    project = _make_project(tmp_path)
    paths = BackgroundPaths.for_project(project)
    first = _MetadataFileLock(
        paths.launch_lock,
        purpose="test launch",
        instance_id="first",
        project_root=project,
    )
    second = _MetadataFileLock(
        paths.launch_lock,
        purpose="test launch",
        instance_id="second",
        project_root=project,
    )
    first.acquire()
    try:
        with pytest.raises(BackgroundAlreadyRunning):
            second.acquire()
    finally:
        first.release()
    metadata = json.loads(paths.launch_lock.read_text(encoding="utf-8"))
    assert metadata["instance_id"] == "first"
    assert metadata["pid"] == os.getpid()
    assert metadata["process_create_time"] is not None


def test_windows_detached_spawn_has_no_console_and_redirects_stdio(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = _make_project(tmp_path)
    paths = BackgroundPaths.for_project(project)
    paths.ensure_root()
    captured: dict[str, Any] = {}

    class FakeProcess:
        pid = 54321

    def fake_popen(command: list[str], **kwargs: Any) -> FakeProcess:
        captured["command"] = command
        captured["kwargs"] = kwargs
        return FakeProcess()

    monkeypatch.setattr(background_runner.subprocess, "Popen", fake_popen)
    executable = Path("C:/runtime/pythonw.exe") if os.name == "nt" else Path("/runtime/python")

    process = _spawn_detached_supervisor(paths, "safe-token", executable)

    assert process.pid == 54321
    assert captured["command"] == [
        str(executable),
        "-m",
        "ebook_reader.background_runner",
        "supervise",
        "--project-root",
        str(project.resolve()),
        "--instance-id",
        "safe-token",
    ]
    kwargs = captured["kwargs"]
    assert kwargs["stdin"] is subprocess.DEVNULL
    assert kwargs["stderr"] is subprocess.STDOUT
    assert kwargs["stdout"] is not subprocess.DEVNULL
    assert kwargs["close_fds"] is True
    if os.name == "nt":
        flags = int(kwargs["creationflags"])
        assert flags & background_runner._detached_creation_flags() == background_runner._detached_creation_flags()
    else:
        assert kwargs["start_new_session"] is True


def test_start_waits_for_matching_ready_handshake(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = _make_project(tmp_path)

    class FakeProcess:
        pid = os.getpid()

        @staticmethod
        def poll() -> None:
            return None

    def fake_spawn(paths: BackgroundPaths, instance_id: str, _python: Path) -> FakeProcess:
        state = _active_state(project, instance_id)
        atomic_write_json(paths.state, state)
        atomic_write_json(
            paths.handshake,
            {
                "schema_version": 1,
                "instance_id": instance_id,
                "project_root": str(project.resolve()),
                "outcome": "ready",
                "detail": "ready",
            },
        )
        return FakeProcess()

    monkeypatch.setattr(background_runner, "_spawn_detached_supervisor", fake_spawn)
    monkeypatch.setattr(background_runner, "_validate_supervisor_identity", lambda *_args: (True, "ok"))

    status = start_background(project, python_executable=Path(os.sys.executable), startup_timeout=1.0)

    assert status.state == "running"
    assert status.running is True
    assert status.instance_id is not None


def test_missing_python_runtime_does_not_publish_a_stuck_starting_state(tmp_path: Path) -> None:
    project = _make_project(tmp_path)
    paths = BackgroundPaths.for_project(project)

    with pytest.raises(BackgroundStartError, match="Python runtime"):
        start_background(
            project,
            python_executable=tmp_path / "missing-python.exe",
            startup_timeout=0.1,
        )

    assert not paths.state.exists()


def test_stale_starting_state_without_an_owner_can_be_relaunched(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = _make_project(tmp_path)
    paths = BackgroundPaths.for_project(project)
    paths.ensure_root()
    stale = _active_state(project, "stale-token")
    stale.update({"state": "starting", "supervisor_pid": None, "supervisor_create_time": None})
    atomic_write_json(paths.state, stale)
    atomic_write_json(paths.handshake, {"instance_id": "stale-token", "outcome": "ready"})

    class FakeProcess:
        pid = os.getpid()

        @staticmethod
        def poll() -> None:
            return None

    def fake_spawn(control: BackgroundPaths, instance_id: str, _python: Path) -> FakeProcess:
        atomic_write_json(control.state, _active_state(project, instance_id))
        atomic_write_json(
            control.handshake,
            {"instance_id": instance_id, "outcome": "ready", "project_root": str(project)},
        )
        return FakeProcess()

    monkeypatch.setattr(background_runner, "_spawn_detached_supervisor", fake_spawn)
    monkeypatch.setattr(background_runner, "_validate_supervisor_identity", lambda *_args: (True, "ok"))

    status = start_background(project, python_executable=Path(os.sys.executable), startup_timeout=1.0)

    assert status.running is True
    assert status.instance_id != "stale-token"


def test_start_timeout_terminates_owned_supervisor_and_marks_failed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = _make_project(tmp_path)

    class FakeProcess:
        pid = 54321

        @staticmethod
        def poll() -> None:
            return None

    fake_process = FakeProcess()
    terminated: list[int] = []
    monkeypatch.setattr(
        background_runner,
        "_spawn_detached_supervisor",
        lambda *_args: fake_process,
    )
    monkeypatch.setattr(
        background_runner,
        "_terminate_owned_launch",
        lambda process: terminated.append(int(process.pid)),
    )

    with pytest.raises(BackgroundStartError, match="không gửi READY"):
        start_background(project, python_executable=Path(os.sys.executable), startup_timeout=0.02)

    status = get_status(project)
    assert terminated == [54321]
    assert status.state == "failed"
    assert status.running is False


def test_no_wait_stop_writes_token_bound_request_only_after_identity_check(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = _make_project(tmp_path)
    paths = BackgroundPaths.for_project(project)
    paths.ensure_root()
    atomic_write_json(paths.state, _active_state(project, "expected-token"))
    monkeypatch.setattr(background_runner, "_validate_supervisor_identity", lambda *_args: (True, "ok"))

    status = request_stop(project, wait=False)

    request = json.loads(paths.stop_request.read_text(encoding="utf-8"))
    assert status.running is True
    assert request["instance_id"] == "expected-token"
    assert request["project_root"] == str(project.resolve())
    assert request["requester_pid"] == os.getpid()
    assert request["force"] is False


def test_stop_refuses_wrong_or_reused_pid_identity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = _make_project(tmp_path)
    paths = BackgroundPaths.for_project(project)
    paths.ensure_root()
    atomic_write_json(paths.state, _active_state(project))
    monkeypatch.setattr(
        background_runner,
        "_validate_supervisor_identity",
        lambda *_args: (False, "PID đã được tái sử dụng"),
    )

    with pytest.raises(BackgroundIdentityError, match="Từ chối gửi stop"):
        request_stop(project, wait=False, force=True)

    assert not paths.stop_request.exists()


def test_force_stop_never_kills_a_replacement_background_instance(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = _make_project(tmp_path)
    paths = BackgroundPaths.for_project(project)
    paths.ensure_root()
    atomic_write_json(paths.state, _active_state(project, "instance-a"))
    monkeypatch.setattr(background_runner, "_validate_supervisor_identity", lambda *_args: (True, "ok"))

    def replace_during_wait(_project: Path, _instance_id: str, _timeout: float) -> BackgroundStatus:
        replacement = _active_state(project, "instance-b")
        replacement["supervisor_pid"] = 5678
        replacement["supervisor_create_time"] = 9.0
        atomic_write_json(paths.state, replacement)
        return BackgroundStatus(
            project_root=project,
            state="running",
            running=True,
            instance_id="instance-b",
            supervisor_pid=5678,
        )

    terminated: list[int] = []
    monkeypatch.setattr(background_runner, "_wait_for_terminal", replace_during_wait)
    monkeypatch.setattr(
        background_runner,
        "terminate_process_tree",
        lambda pid, **_kwargs: terminated.append(pid),
    )

    with pytest.raises(BackgroundIdentityError, match="instance đã thay đổi"):
        request_stop(project, wait=True, timeout=0.0, force=True)

    assert terminated == []
    assert json.loads(paths.state.read_text(encoding="utf-8"))["instance_id"] == "instance-b"


def test_truncated_or_wrong_token_stop_request_is_ignored(tmp_path: Path) -> None:
    project = _make_project(tmp_path)
    paths = BackgroundPaths.for_project(project)
    paths.ensure_root()
    paths.stop_request.write_text('{"instance_id":', encoding="utf-8")
    assert background_runner._stop_request_matches(paths, "token") is False

    atomic_write_json(
        paths.stop_request,
        {
            "schema_version": 1,
            "instance_id": "other-token",
            "project_root": str(project.resolve()),
        },
    )
    assert background_runner._stop_request_matches(paths, "token") is False


def test_supervisor_records_fake_worker_completion_without_book_pipeline(tmp_path: Path) -> None:
    project = _make_project(tmp_path)

    exit_code = run_supervisor(project, "fake-success", worker_target=_fake_worker_success, poll_seconds=0.01)

    status = get_status(project)
    assert exit_code == 0
    assert status.state == "completed"
    assert status.running is False
    assert status.exit_code == 0
    assert status.last_event is not None
    assert status.last_event["kind"] == "finished"
    assert "READY" in tail_log(project, lines=20)
    assert "SUPERVISOR_END state=completed" in tail_log(project, lines=20)


def test_supervisor_never_sends_ready_when_worker_bootstrap_fails(tmp_path: Path) -> None:
    project = _make_project(tmp_path)
    paths = BackgroundPaths.for_project(project)

    exit_code = run_supervisor(
        project,
        "fake-bootstrap-failure",
        worker_target=_fake_worker_fails_before_ready,
        poll_seconds=0.01,
    )

    status = get_status(project)
    handshake = json.loads(paths.handshake.read_text(encoding="utf-8"))
    assert exit_code == 1
    assert status.state == "failed"
    assert status.running is False
    assert handshake["outcome"] == "error"
    assert "bootstrap rejected" in handshake["detail"]
    assert "READY" not in tail_log(project, lines=20)


def test_supervisor_forwards_persistent_stop_and_records_clean_stop(tmp_path: Path) -> None:
    project = _make_project(tmp_path)
    paths = BackgroundPaths.for_project(project)
    paths.ensure_root()
    atomic_write_json(
        paths.stop_request,
        {
            "schema_version": 1,
            "instance_id": "fake-stop",
            "project_root": str(project.resolve()),
            "requested_at": "2026-08-10T00:00:00Z",
            "requester_pid": os.getpid(),
            "force": False,
        },
    )

    started = time.monotonic()
    exit_code = run_supervisor(
        project,
        "fake-stop",
        worker_target=_fake_worker_wait_for_stop,
        poll_seconds=0.01,
    )

    status = get_status(project)
    assert time.monotonic() - started < 5.0
    assert exit_code == 0
    assert status.state == "stopped"
    assert status.stop_requested is True
    assert status.detail == "fake stopped cleanly"
    assert "STOP_REQUEST forwarded to worker" in tail_log(project, lines=30)
