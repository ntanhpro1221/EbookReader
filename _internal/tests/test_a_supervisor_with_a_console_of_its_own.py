"""The supervisor gets a hidden console of its own, never no console at all.

DETACHED_PROCESS cancels CREATE_NO_WINDOW on Windows; a console-less parent makes every
console child open a visible window. The watchdog had exactly these flags and flashed three
terminal windows per model load until 9c5b123. Here it is latent - pythonw.exe never has a
console - but the python.exe fallback would turn it into a console window that lives for the
whole run.
"""
from __future__ import annotations

import os

from ebook_reader import background_runner


def test_the_supervisor_is_hidden_but_not_detached() -> None:
    flags = background_runner._detached_creation_flags()
    if os.name != "nt":
        assert flags == 0
        return
    assert flags & 0x08000000, "CREATE_NO_WINDOW"
    assert flags & 0x00000200, "CREATE_NEW_PROCESS_GROUP"
    assert not flags & 0x00000008, "DETACHED_PROCESS would cancel CREATE_NO_WINDOW"
