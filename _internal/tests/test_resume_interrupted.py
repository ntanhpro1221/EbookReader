"""A book interrupted by a shutdown must come back; one deliberately stopped must not.

The pipeline checkpoints constantly and `resume` picks up where it left off, but nothing
pressed the button: the supervisor runs a single worker and exits when it dies, and there is
no Task Scheduler entry. A machine that slept or restarted mid-book left it stopped.

get_status already distinguishes the cases, because it validates the recorded supervisor
against the process actually holding that pid: a record that says active while the process
is gone comes back as "lost". These pin that the script acts on exactly that state and
nothing else - restarting a run somebody asked to stop would be worse than the gap it fills.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import resume_interrupted  # noqa: E402


def _project(root: Path, name: str, state: dict) -> Path:
    project = root / f"v0.2.0-{name}" / f"{name}_hash"
    (project / "runtime" / "background").mkdir(parents=True, exist_ok=True)
    (project / "project.sqlite3").write_bytes(b"")
    (project / "runtime" / "background" / "state.json").write_text(
        json.dumps(state), encoding="utf-8"
    )
    return project


def test_it_finds_every_project_under_the_versions_root(tmp_path: Path) -> None:
    _project(tmp_path, "alpha.1", {"state": "finished"})
    _project(tmp_path, "alpha.2", {"state": "running"})
    (tmp_path / "not-a-version").mkdir()

    found = resume_interrupted.projects_under(tmp_path)

    assert len(found) == 2
    assert all((p / "project.sqlite3").is_file() for p in found)


def test_an_empty_root_is_not_an_error(tmp_path: Path) -> None:
    assert resume_interrupted.projects_under(tmp_path) == []
    assert resume_interrupted.main([str(tmp_path)]) == 0


def test_a_lost_run_is_resumed(tmp_path: Path, monkeypatch) -> None:
    """"lost" is the record saying active while the process holding that pid is gone."""
    project = _project(
        tmp_path, "alpha.9", {"state": "running", "supervisor_pid": 999_999, "detail": "x"}
    )
    started: list[Path] = []
    monkeypatch.setattr(resume_interrupted, "start_background", lambda p: started.append(Path(p)))

    resume_interrupted.main([str(tmp_path)])

    assert started == [project], "an interrupted run must come back"


def test_a_stop_request_is_never_overridden(tmp_path: Path, monkeypatch) -> None:
    """Someone asked it to stop. Coming back after a reboot would be worse than the gap."""
    _project(
        tmp_path,
        "alpha.9",
        {"state": "running", "supervisor_pid": 999_999, "stop_requested": True},
    )
    started: list[Path] = []
    monkeypatch.setattr(resume_interrupted, "start_background", lambda p: started.append(Path(p)))

    resume_interrupted.main([str(tmp_path)])

    assert started == []


@pytest.mark.parametrize("state", ["finished", "failed", "stopped"])
def test_a_run_that_ended_is_left_alone(tmp_path: Path, monkeypatch, state: str) -> None:
    _project(tmp_path, "alpha.9", {"state": state})
    started: list[Path] = []
    monkeypatch.setattr(resume_interrupted, "start_background", lambda p: started.append(Path(p)))

    resume_interrupted.main([str(tmp_path)])

    assert started == []


def test_dry_run_starts_nothing(tmp_path: Path, monkeypatch) -> None:
    _project(tmp_path, "alpha.9", {"state": "running", "supervisor_pid": 999_999})
    started: list[Path] = []
    monkeypatch.setattr(resume_interrupted, "start_background", lambda p: started.append(Path(p)))

    resume_interrupted.main([str(tmp_path), "--dry-run"])

    assert started == []


def test_one_failure_does_not_stop_the_rest(tmp_path: Path, monkeypatch) -> None:
    """A project that cannot restart must not strand the others behind it."""
    _project(tmp_path, "alpha.1", {"state": "running", "supervisor_pid": 999_999})
    _project(tmp_path, "alpha.2", {"state": "running", "supervisor_pid": 999_998})
    seen: list[Path] = []

    def flaky(project):
        seen.append(Path(project))
        if "alpha.1" in str(project):
            raise RuntimeError("locked")

    monkeypatch.setattr(resume_interrupted, "start_background", flaky)
    assert resume_interrupted.main([str(tmp_path)]) == 0
    assert len(seen) == 2


def test_it_records_what_it_did_beside_the_projects(tmp_path: Path, monkeypatch) -> None:
    """At logon nobody reads stdout, so the decision has to survive somewhere."""
    _project(tmp_path, "alpha.9", {"state": "running", "supervisor_pid": 999_999})
    monkeypatch.setattr(resume_interrupted, "start_background", lambda p: None)

    resume_interrupted.main([str(tmp_path)])

    log = (tmp_path / resume_interrupted.LOG_NAME).read_text(encoding="utf-8")
    assert "TIẾP TỤC" in log and "alpha.9" in log


def test_the_log_file_is_not_mistaken_for_a_project(tmp_path: Path, monkeypatch) -> None:
    """It lives in the directory being scanned, so the scan has to step over it."""
    _project(tmp_path, "alpha.9", {"state": "finished"})
    monkeypatch.setattr(resume_interrupted, "start_background", lambda p: None)

    resume_interrupted.main([str(tmp_path)])
    assert (tmp_path / resume_interrupted.LOG_NAME).is_file()

    assert len(resume_interrupted.projects_under(tmp_path)) == 1
    assert resume_interrupted.main([str(tmp_path)]) == 0


def test_a_log_that_cannot_be_written_still_resumes_the_book(tmp_path: Path, monkeypatch) -> None:
    """Logging is for us. Failing to log must never cost the user a night of audio."""
    project = _project(tmp_path, "alpha.9", {"state": "running", "supervisor_pid": 999_999})
    started: list[Path] = []
    monkeypatch.setattr(resume_interrupted, "start_background", lambda p: started.append(Path(p)))
    (tmp_path / resume_interrupted.LOG_NAME).mkdir()  # open() on a directory raises OSError

    assert resume_interrupted.main([str(tmp_path)]) == 0
    assert started == [project]
