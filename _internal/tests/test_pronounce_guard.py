"""Pinning a reading while the book is being read aloud kills the run.

alpha.47: `pronounce Theosbane "theo-bên"` at 03:33, and at 04:06 chapter 5 verification
raised "spoken-text checksum drifted before candidate or final verification". The pipeline
was carrying items whose checksum was taken before the change.

What makes it worth refusing rather than warning is that it leaves no evidence. Every
checksum on disk was consistent afterwards - 176 candidates and 440 segments, none drifted -
and a resume picked straight up. The traceback points into the pipeline and nothing anywhere
says a person edited a name half an hour earlier.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from ebook_reader import cli
from ebook_reader.config import build_settings, save_settings, settings_hash
from ebook_reader.database import ProjectDB
from ebook_reader.models import ProjectPaths


def _project(tmp_path: Path) -> Path:
    paths = ProjectPaths.build(tmp_path / "project")
    settings = build_settings()
    save_settings(paths.settings, settings)
    db = ProjectDB(paths.db)
    db.initialize_book(
        title="Book",
        project_root=paths.root,
        settings=settings,
        settings_hash=settings_hash(settings),
        input_manifest_hash="manifest",
    )
    return paths.root


def _args(root: Path) -> argparse.Namespace:
    return argparse.Namespace(
        project_root=str(root), surface="Theosbane", spoken="theo-bên", json=False
    )


class _Status:
    def __init__(self, running: bool) -> None:
        self.running = running
        self.state = "running" if running else "completed"


def test_a_running_project_refuses_the_edit(tmp_path: Path, monkeypatch) -> None:
    root = _project(tmp_path)
    monkeypatch.setattr(
        "ebook_reader.background_runner.get_status", lambda _p: _Status(True)
    )

    result = cli._command_pronounce(_args(root))

    assert result.exit_code != 0
    assert "đang chạy" in str(result.error)


def test_a_stopped_project_still_accepts_it(tmp_path: Path, monkeypatch) -> None:
    """The command exists so a listener can settle a name; the guard must not take that
    away, only move it to a moment when nothing is mid-verification."""
    root = _project(tmp_path)
    monkeypatch.setattr(
        "ebook_reader.background_runner.get_status", lambda _p: _Status(False)
    )

    result = cli._command_pronounce(_args(root))

    assert result.exit_code == 0, result.error
    assert result.data.get("spoken_form") == "theo-bên"


def test_the_refusal_names_the_way_out(tmp_path: Path, monkeypatch) -> None:
    """A refusal that does not say what to do instead is just an obstacle."""
    root = _project(tmp_path)
    monkeypatch.setattr(
        "ebook_reader.background_runner.get_status", lambda _p: _Status(True)
    )

    error = str(cli._command_pronounce(_args(root)).error)

    assert "stop" in error and "resume" in error
