from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path
from types import ModuleType


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "check_system.py"


def _load_checker() -> ModuleType:
    spec = importlib.util.spec_from_file_location("ebook_reader_check_system", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_ollama_model_manifest_respects_the_configured_cache_root(
    tmp_path: Path,
    monkeypatch,
) -> None:
    checker = _load_checker()
    monkeypatch.setenv("OLLAMA_MODELS", str(tmp_path / "models"))

    manifest = checker.ollama_model_manifest("qwen3:8b")

    assert manifest == (
        tmp_path
        / "models"
        / "manifests"
        / "registry.ollama.ai"
        / "library"
        / "qwen3"
        / "8b"
    )


def test_command_timeout_terminates_the_whole_process_tree(monkeypatch) -> None:
    checker = _load_checker()
    terminated: list[tuple[int, bool, float]] = []

    class FakeStdout:
        closed = False

        def close(self) -> None:
            self.closed = True

    class FakeProcess:
        pid = 4242
        returncode = None
        stdout = FakeStdout()
        calls = 0

        def communicate(self, timeout):
            self.calls += 1
            if self.calls == 1:
                raise subprocess.TimeoutExpired(["ollama", "list"], timeout)
            return "partial output", None

    process = FakeProcess()
    monkeypatch.setattr(checker.subprocess, "Popen", lambda *_args, **_kwargs: process)
    monkeypatch.setattr(
        checker,
        "terminate_process_tree",
        lambda pid, *, include_parent, grace_seconds: terminated.append(
            (pid, include_parent, grace_seconds)
        ),
    )

    ok, detail = checker.command_output(["ollama", "list"], timeout=2)

    assert ok is False
    assert detail == "timed out after 2s: partial output"
    assert terminated == [(4242, True, 3.0)]
