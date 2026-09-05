"""Ollama wedges after a sleep while every cheap check still says it is healthy.

Measured ~90s after a real wake on 2026-09-05: /api/tags answered in 17ms, /api/ps still
reported qwen3:8b resident in 6.03 GB of VRAM, nvidia-smi showed the memory held at 0%
utilization, and /api/generate produced nothing in 20 seconds. The pipeline retried the
dropped connection exactly as designed and would have exhausted its budget against a
corpse. Only a new process has a working CUDA context.

The risk runs the other way too: restarting a healthy Ollama evicts a 6 GB model, and a
probe queued behind a real request looks identical to a wedge. Most of these pin the
refusals rather than the restart.
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import ollama_watchdog  # noqa: E402


def _project(root: Path, name: str, *, running: bool, log_age: float | None) -> Path:
    """running is expressed through the get_status patch; the tree only carries the log."""
    project = root / f"v0.2.0-{name}" / f"{name}_hash"
    (project / "logs").mkdir(parents=True, exist_ok=True)
    (project / "project.sqlite3").write_bytes(b"")
    if log_age is not None:
        log = project / "logs" / "ebook_reader.log"
        log.write_text("x", encoding="utf-8")
        stamp = time.time() - log_age
        os.utime(log, (stamp, stamp))
    return project


class _Status:
    def __init__(self, running: bool) -> None:
        self.running = running


def _wire(monkeypatch, *, states: dict[str, bool], models, generates, restarts: list):
    monkeypatch.setattr(
        ollama_watchdog, "get_status", lambda p: _Status(states.get(Path(p).name, False))
    )
    monkeypatch.setattr(ollama_watchdog, "loaded_models", lambda: models)
    monkeypatch.setattr(ollama_watchdog, "can_generate", lambda m, **k: generates)
    monkeypatch.setattr(
        ollama_watchdog, "restart_ollama", lambda: (restarts.append(1), True)[1]
    )


def test_nothing_running_means_ollama_is_never_touched(tmp_path: Path, monkeypatch) -> None:
    """No book needs it, so evicting a 6 GB model would be pure cost."""
    _project(tmp_path, "alpha.9", running=False, log_age=99_999)
    restarts: list = []
    _wire(monkeypatch, states={}, models=["qwen3:8b"], generates=False, restarts=restarts)

    assert ollama_watchdog.main([str(tmp_path)]) == 0
    assert restarts == []


def test_a_progressing_run_is_never_probed(tmp_path: Path, monkeypatch) -> None:
    """A probe would queue behind real work and could time out on a healthy service."""
    _project(tmp_path, "alpha.9", running=True, log_age=5)
    probed: list = []
    restarts: list = []
    monkeypatch.setattr(ollama_watchdog, "get_status", lambda p: _Status(True))
    monkeypatch.setattr(ollama_watchdog, "loaded_models", lambda: (probed.append(1), [])[1])
    monkeypatch.setattr(ollama_watchdog, "restart_ollama", lambda: restarts.append(1))

    assert ollama_watchdog.main([str(tmp_path)]) == 0
    assert probed == [], "a log that moved seconds ago is not a stall"
    assert restarts == []


def test_a_stalled_run_with_a_working_ollama_is_left_alone(
    tmp_path: Path, monkeypatch
) -> None:
    """The stall is real but Ollama is not the cause; restarting it would help nothing."""
    _project(tmp_path, "alpha.9", running=True, log_age=ollama_watchdog.STALL_SECONDS + 60)
    restarts: list = []
    _wire(
        monkeypatch,
        states={"alpha.9_hash": True},
        models=["qwen3:8b"],
        generates=True,
        restarts=restarts,
    )

    assert ollama_watchdog.main([str(tmp_path)]) == 0
    assert restarts == []


def test_a_stall_with_nothing_loaded_is_not_this_failure(tmp_path: Path, monkeypatch) -> None:
    """The wedge is a *loaded* model that cannot generate. Nothing loaded, nothing stuck."""
    _project(tmp_path, "alpha.9", running=True, log_age=ollama_watchdog.STALL_SECONDS + 60)
    restarts: list = []
    _wire(
        monkeypatch,
        states={"alpha.9_hash": True},
        models=[],
        generates=False,
        restarts=restarts,
    )

    assert ollama_watchdog.main([str(tmp_path)]) == 0
    assert restarts == []


def test_loaded_but_unable_to_generate_is_restarted(tmp_path: Path, monkeypatch) -> None:
    """The measured post-wake state, and the one case where a restart is the only cure."""
    _project(tmp_path, "alpha.9", running=True, log_age=ollama_watchdog.STALL_SECONDS + 60)
    restarts: list = []
    _wire(
        monkeypatch,
        states={"alpha.9_hash": True},
        models=["qwen3:8b"],
        generates=False,
        restarts=restarts,
    )

    assert ollama_watchdog.main([str(tmp_path)]) == 0
    assert restarts == [1]


def test_dry_run_diagnoses_without_restarting(tmp_path: Path, monkeypatch) -> None:
    _project(tmp_path, "alpha.9", running=True, log_age=ollama_watchdog.STALL_SECONDS + 60)
    restarts: list = []
    _wire(
        monkeypatch,
        states={"alpha.9_hash": True},
        models=["qwen3:8b"],
        generates=False,
        restarts=restarts,
    )

    assert ollama_watchdog.main([str(tmp_path), "--dry-run"]) == 0
    assert restarts == []


def test_a_failed_restart_reports_a_nonzero_exit(tmp_path: Path, monkeypatch) -> None:
    """Silence here would look like a successful recovery that never happened."""
    _project(tmp_path, "alpha.9", running=True, log_age=ollama_watchdog.STALL_SECONDS + 60)
    monkeypatch.setattr(ollama_watchdog, "get_status", lambda p: _Status(True))
    monkeypatch.setattr(ollama_watchdog, "loaded_models", lambda: ["qwen3:8b"])
    monkeypatch.setattr(ollama_watchdog, "can_generate", lambda m, **k: False)
    monkeypatch.setattr(ollama_watchdog, "restart_ollama", lambda: False)

    assert ollama_watchdog.main([str(tmp_path)]) == 1


def test_a_project_with_no_log_yet_is_not_a_stall(tmp_path: Path, monkeypatch) -> None:
    _project(tmp_path, "alpha.9", running=True, log_age=None)
    restarts: list = []
    _wire(
        monkeypatch,
        states={"alpha.9_hash": True},
        models=["qwen3:8b"],
        generates=False,
        restarts=restarts,
    )

    assert ollama_watchdog.main([str(tmp_path)]) == 0
    assert restarts == []


def test_an_unreadable_project_does_not_blind_the_rest(tmp_path: Path, monkeypatch) -> None:
    """One bad status read must not hide a genuinely wedged service."""
    _project(tmp_path, "alpha.1", running=True, log_age=1)
    _project(tmp_path, "alpha.2", running=True, log_age=ollama_watchdog.STALL_SECONDS + 60)

    def flaky(project):
        if "alpha.1" in str(project):
            raise RuntimeError("state.json is corrupt")
        return _Status(True)

    restarts: list = []
    monkeypatch.setattr(ollama_watchdog, "get_status", flaky)
    monkeypatch.setattr(ollama_watchdog, "loaded_models", lambda: ["qwen3:8b"])
    monkeypatch.setattr(ollama_watchdog, "can_generate", lambda m, **k: False)
    monkeypatch.setattr(ollama_watchdog, "restart_ollama", lambda: restarts.append(1) or True)

    assert ollama_watchdog.main([str(tmp_path)]) == 0
    assert restarts == [1]


def test_the_probe_timeout_is_long_enough_to_outlast_a_real_request() -> None:
    """Ollama serves one request at a time by default; a short probe would call a busy
    service dead and evict its model. Batches in this book took up to ~16s."""
    assert ollama_watchdog.PROBE_TIMEOUT_SECONDS >= 60
    assert ollama_watchdog.STALL_SECONDS >= 300
