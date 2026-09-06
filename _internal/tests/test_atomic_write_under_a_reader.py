"""Reading a file must not be able to kill the process writing it.

alpha.50 died 44 minutes into its analysis on

    PermissionError: [WinError 5] Access is denied:
    'runtime/background/state.json.part' -> 'runtime/background/state.json'

On Windows a rename onto a file another process has open fails, and `atomic_write_bytes`
called `os.replace` once and let the error out. The reader that hit it was a polling script,
but nothing about that is special: `cli status` opens the same state file, so a person
checking on their own run could have ended it the same way.

The window is microseconds wide. Retrying briefly closes it without hiding anything: a
rename still blocked after twelve tries is not this race, and the error is raised unchanged.

What retrying does *not* do is beat a reader that holds the file open across the whole
window - the last test states that boundary rather than pretending it away.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from ebook_reader import io_utils
from ebook_reader.io_utils import atomic_write_json


def test_a_transient_permission_error_is_retried(tmp_path: Path, monkeypatch) -> None:
    """One reader holding the destination for a moment must not lose the write."""
    target = tmp_path / "state.json"
    target.write_text("{}", encoding="utf-8")
    calls: list[int] = []
    real_replace = os.replace

    def flaky(src, dst):  # noqa: ANN001
        calls.append(1)
        if len(calls) < 3:
            raise PermissionError(5, "Access is denied")
        return real_replace(src, dst)

    monkeypatch.setattr(io_utils.os, "replace", flaky)
    monkeypatch.setattr(io_utils, "REPLACE_RETRY_DELAY_SECONDS", 0.0)

    atomic_write_json(target, {"state": "running"})

    assert len(calls) == 3
    assert '"state": "running"' in target.read_text(encoding="utf-8")


def test_a_permanent_permission_error_is_still_raised(tmp_path: Path, monkeypatch) -> None:
    """A rename blocked for the whole window is not this race, and hiding it would turn a
    lost state write into silent divergence between the ledger and the disk."""
    target = tmp_path / "state.json"

    def always_denied(src, dst):  # noqa: ANN001
        raise PermissionError(5, "Access is denied")

    monkeypatch.setattr(io_utils.os, "replace", always_denied)
    monkeypatch.setattr(io_utils, "REPLACE_RETRY_DELAY_SECONDS", 0.0)

    with pytest.raises(PermissionError):
        atomic_write_json(target, {"state": "running"})


def test_the_write_still_lands_with_no_interference(tmp_path: Path) -> None:
    target = tmp_path / "nested" / "state.json"

    atomic_write_json(target, {"state": "finished", "exit_code": 0})

    assert target.is_file()
    assert not target.with_suffix(".json.part").exists()


def test_a_reader_that_opens_and_closes_is_survived(tmp_path: Path) -> None:
    """The shape the fix is actually for: a poller doing read_text in a loop holds the file
    for microseconds, and the retry window is six orders of magnitude wider than that."""
    target = tmp_path / "state.json"
    atomic_write_json(target, {"state": "running"})

    for _ in range(20):
        target.read_text(encoding="utf-8")
        atomic_write_json(target, {"state": "finished"})

    assert '"state": "finished"' in target.read_text(encoding="utf-8")


@pytest.mark.skipif(os.name != "nt", reason="only Windows refuses a rename onto an open file")
def test_a_reader_holding_the_file_open_still_wins(tmp_path: Path) -> None:
    """Stated as a limit, not fixed, because retrying cannot beat a sustained hold and
    pretending otherwise would be worse than the honest boundary.

    A reader that keeps the destination open across the whole retry window still blocks the
    rename. That is a bug in such a reader - nothing in this project needs to hold a state
    file open - and the loud PermissionError is the right outcome for it.
    """
    target = tmp_path / "state.json"
    atomic_write_json(target, {"state": "running"})

    with target.open("r", encoding="utf-8") as reader:
        reader.read()
        with pytest.raises(PermissionError):
            atomic_write_json(target, {"state": "finished"})
