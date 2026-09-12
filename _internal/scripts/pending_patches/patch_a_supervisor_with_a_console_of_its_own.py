"""Va background_runner.py: supervisor duoc mot console an cua rieng no, khong phai KHONG console.

Cung mot loi voi watchdog (sua o 9c5b123, xem docs/SURVIVING_AN_INTERRUPTION.md muc 23:14):
`CREATE_NO_WINDOW | DETACHED_PROCESS` - va tren Windows co thu hai vo hieu hoa co thu nhat.
Mot tien trinh detached khong co console, nen moi con console no sinh ra se mo console MOI,
va Win11 bat Windows Terminal len de hien no.

Hom nay vo hai vi supervisor la `pythonw.exe` (GUI subsystem, khong bao gio co console) va con
cua no deu pythonw hoac goi qua CREATE_NO_WINDOW. Nhung `_default_python_executable` roi ve
`python.exe` khi venv khong co pythonw, va khi ay worker `multiprocessing` (spawn voi co 0) se
mo mot cua so console song suot luot chay. Do 2026-09-12 08:35 tren may chu sach, cung mot
thi nghiem da chung minh cho watchdog: tu mot cha khong co console,

    CREATE_NO_WINDOW | DETACHED_PROCESS | NEW_GROUP   chau bat cua so: CO
    CREATE_NO_WINDOW | NEW_GROUP                      khong
    CREATE_NO_WINDOW                                  khong

Song sot sau khi cha thoat chua bao gio can DETACHED_PROCESS: con Windows song lau hon cha
tru khi co job object. CREATE_NEW_PROCESS_GROUP giu lai de Ctrl+C o terminal cua cha khong
toi supervisor; CREATE_NO_WINDOW cho no console rieng nen dong terminal cua cha cung khong
cham toi no - dung hai thu "detached" tung huong toi.

Khong xep hang som: file bi khoa, ap o ranh gioi 7 -> 8 hoac sau. Khong gap.
"""
import io
import sys
from pathlib import Path

root = Path(sys.argv[1])
p = root / "ebook_reader" / "background_runner.py"
s = io.open(p, encoding="utf-8").read()

OLD = '''def _detached_creation_flags() -> int:
    if os.name != "nt":
        return 0
    return (
        getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
        | getattr(subprocess, "DETACHED_PROCESS", 0x00000008)
        | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200)
    )
'''
NEW = '''def _detached_creation_flags() -> int:
    """A supervisor with a hidden console of its own - never one with no console at all.

    The old value added DETACHED_PROCESS, and on Windows that flag cancels CREATE_NO_WINDOW:
    a detached process has no console, so every console program it starts gets a brand-new
    one, and Windows 11 opens a terminal window to show it. The watchdog had the same flags
    and flashed three windows per model load from 2026-09-11 23:14 until 9c5b123 fixed it.

    Harmless here today only because the supervisor is pythonw.exe, which never has a
    console, and its children are pythonw or CREATE_NO_WINDOW. But _default_python_executable
    falls back to python.exe when the venv has no pythonw, and then the multiprocessing
    worker (spawned with flags 0) would open a console window for the life of the run.

    Surviving the parent's exit never needed DETACHED_PROCESS - a Windows child outlives its
    parent unless a job object says otherwise. CREATE_NEW_PROCESS_GROUP keeps a Ctrl+C in the
    parent's terminal away from the supervisor; CREATE_NO_WINDOW gives it a console of its
    own, so closing that terminal cannot reach it either. Both things "detached" was for.
    """
    if os.name != "nt":
        return 0
    return getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000) | getattr(
        subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200
    )
'''
assert s.count(OLD) == 1, "khong khop _detached_creation_flags"
s = s.replace(OLD, NEW, 1)
io.open(p, "w", encoding="utf-8", newline="\n").write(s)
print(f"da va {p}")

TEST = '''"""The supervisor gets a hidden console of its own, never no console at all.

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
'''
t = root / "tests" / "test_a_supervisor_with_a_console_of_its_own.py"
io.open(t, "w", encoding="utf-8", newline="\n").write(TEST)
print(f"da tao {t}")
