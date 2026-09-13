"""Restart Ollama when it is loaded, answering, and unable to generate a single token.

Sleeping the machine destroys CUDA contexts. The worker survives that - see
docs/SURVIVING_AN_INTERRUPTION.md - but Ollama is a separate service holding its own
context, and it dies in a nastier way: it wedges *while still looking healthy*.

Measured on 2026-09-05, ~90 seconds after a real wake:

    GET  /api/tags      -> HTTP 200 in 17ms          (that path never touches the GPU)
    GET  /api/ps        -> qwen3:8b, size_vram 6.03 GB, still "loaded"
    nvidia-smi          -> 6762 MiB held, 0% utilization
    POST /api/generate  -> nothing at all after 20s

So every cheap liveness check says yes and the only honest question - can it produce a
token - says no. The pipeline retries a dropped connection correctly and says so in its
own comments, but it was retrying into a corpse with a bounded budget: two attempts for the
director critic, three for the batch. Left alone it would have failed the book within
minutes. Restarting ollama.exe fixed it in one step, because a new process gets a new
context. Nothing else can.

Deliberately reluctant, because restarting a healthy Ollama evicts a 6 GB model that then
has to be reloaded, and a probe that queues behind a genuine request looks exactly like a
wedge:

  - does nothing unless a project is actually running
  - does nothing until that project's log has been silent for STALL_SECONDS
  - waits PROBE_TIMEOUT_SECONDS for the probe, long enough for a real request to finish
    ahead of it, before believing the answer

    python scripts/ollama_watchdog.py [versions_root] [--dry-run]

Written for the same Task Scheduler entry as resume_interrupted.py; safe by hand any time.
"""
from __future__ import annotations

import datetime as _dt
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ebook_reader.background_runner import get_status  # noqa: E402

try:
    from scripts.book_paths import VERSIONS as _BOOK_VERSIONS  # noqa: E402
except ImportError:  # chạy trực tiếp: python scripts/x.py
    from book_paths import VERSIONS as _BOOK_VERSIONS  # noqa: E402
DEFAULT_VERSIONS_ROOT = _BOOK_VERSIONS
LOG_NAME = "_ollama_watchdog.log"
OLLAMA_BASE_URL = "http://127.0.0.1:11434"
OLLAMA_EXE_FALLBACK = Path(
    "C:/Users/NGDtuanh/AppData/Local/Programs/Ollama/ollama.exe"
)
# A quiet log is the first signal. Analysis batches land every 5-20 seconds and synthesis
# is noisier still, so ten minutes of silence is far outside normal for either phase.
STALL_SECONDS = 600
# The second signal. Long on purpose: Ollama serves one request at a time by default, so a
# probe can sit behind a real generation. Anything under a minute would call a busy service
# dead and evict its model for nothing.
PROBE_TIMEOUT_SECONDS = 120
PROBE_PROMPT = "1+1="
RESTART_SETTLE_SECONDS = 90
# Ba câu trả lời của probe. Chỉ TIMEOUT là chữ ký treo; xem probe_verdict.
PROBE_OK = "ok"
PROBE_TIMEOUT = "timeout"
PROBE_ERROR = "error"


def _log_line(root: Path, line: str) -> None:
    """Nothing watches stdout under Task Scheduler; leave the reasoning somewhere."""
    stamp = _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        with (root / LOG_NAME).open("a", encoding="utf-8") as handle:
            handle.write(f"{stamp}  {line}\n")
    except OSError:
        pass


def _say_safely(line: str) -> None:
    """Windows hands scripts a cp1252 stdout and every message here is Vietnamese."""
    try:
        print(line)
    except (UnicodeEncodeError, OSError, ValueError):
        try:
            sys.stdout.buffer.write(line.encode("utf-8", "replace") + b"\n")
        except Exception:  # noqa: BLE001 - under pythonw there is no console at all
            pass


def running_projects(root: Path) -> list[Path]:
    found: list[Path] = []
    if not root.is_dir():
        return found
    for version in sorted(root.iterdir()):
        if not version.is_dir():
            continue
        for candidate in sorted(version.iterdir()):
            if not (candidate / "project.sqlite3").is_file():
                continue
            try:
                if get_status(candidate).running:
                    found.append(candidate)
            except Exception:  # noqa: BLE001 - one unreadable project must not blind us
                continue
    return found


def seconds_since_progress(project: Path) -> float | None:
    """How long the worker's log has been silent, or None when there is no log yet."""
    log = project / "logs" / "ebook_reader.log"
    try:
        return max(0.0, time.time() - log.stat().st_mtime)
    except OSError:
        return None


def loaded_models() -> list[str]:
    """What Ollama says it is holding. This answers even when generation cannot."""
    try:
        with urllib.request.urlopen(f"{OLLAMA_BASE_URL}/api/ps", timeout=10) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, ValueError, TimeoutError):
        return []
    models = payload.get("models")
    if not isinstance(models, list):
        return []
    return [str(entry.get("model") or entry.get("name") or "") for entry in models]


def probe_verdict(model: str, timeout: float = PROBE_TIMEOUT_SECONDS) -> tuple[str, str]:
    """Does a token come out - and if not, HOW did it fail. The how is the whole point.

    The wedge this watchdog exists for has exactly one signature, measured on 2026-09-05:
    the request *hangs*. Nothing after 20 s, nothing after 120 s. A probe that comes back
    in fifteen seconds with an HTTP error or a reset connection is a different animal - a
    server that is busy, restarting, or refusing - and none of those is cured by killing
    it. The old boolean version folded every failure into "no token", and on 2026-09-11 at
    23:14:08 it answered "no token" after 15 s (the log shows the restart 15 s after the
    probe began, not 120) and restarted a healthy Ollama that was busy with batch 5's real
    analysis. The silence gate had already been fooled: the system clock had just been
    corrected forward by 4 h 17 min, so a log written 55 s earlier looked 258 min old.
    Two gates exist so that one fooled gate is not enough; this makes the second gate
    actually ask its question.

    And the second gate had been broken since the model became qwen3:8b, a *thinking*
    model: its first tokens go into the `thinking` field, `response` stays empty, and the
    old probe read a healthy server as "no token" every single time - the 15 s at 23:14
    was simply the model loading and answering. So every trip of the silence gate was a
    guaranteed restart. The probe now sends think=false and counts eval_count.

    Returns (verdict, detail): PROBE_OK, PROBE_TIMEOUT (the signature), or PROBE_ERROR
    with what actually happened.
    """
    body = json.dumps(
        {
            "model": model,
            "prompt": PROBE_PROMPT,
            "stream": False,
            "options": {"num_predict": 4},
            # qwen3 is a thinking model: without this, all four tokens go into the
            # `thinking` field and `response` stays empty. Measured 2026-09-12 08:41 on a
            # healthy server - default: response '' thinking 'Okay,' eval_count 4;
            # think false: response '1 + 1'. The old probe read the first as "no token".
            "think": False,
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        f"{OLLAMA_BASE_URL}/api/generate",
        data=body,
        headers={"Content-Type": "application/json"},
    )
    started = time.monotonic()
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            if response.status != 200:
                return PROBE_ERROR, f"HTTP {response.status} sau {time.monotonic() - started:.0f}s"
            payload = json.loads(response.read().decode("utf-8"))
    except TimeoutError:
        return PROBE_TIMEOUT, f"im lặng {time.monotonic() - started:.0f}s"
    except urllib.error.URLError as exc:
        reason = getattr(exc, "reason", exc)
        if isinstance(reason, TimeoutError):
            return PROBE_TIMEOUT, f"im lặng {time.monotonic() - started:.0f}s (kết nối)"
        return PROBE_ERROR, f"{type(exc).__name__}: {reason} sau {time.monotonic() - started:.0f}s"
    except (OSError, ValueError) as exc:
        return PROBE_ERROR, f"{type(exc).__name__}: {exc} sau {time.monotonic() - started:.0f}s"
    # A token is a token wherever the server put it. eval_count is the honest counter;
    # response and thinking are the two places the text can land.
    tokens = int(payload.get("eval_count") or 0)
    if tokens > 0 or str(payload.get("response") or "") or str(payload.get("thinking") or ""):
        return PROBE_OK, f"có chữ ({tokens} token)"
    return PROBE_ERROR, "HTTP 200 nhưng không có token nào"


def can_generate(model: str, timeout: float = PROBE_TIMEOUT_SECONDS) -> bool:
    """The yes/no form, kept for callers that only want the yes."""
    return probe_verdict(model, timeout)[0] == PROBE_OK


def _ollama_processes():
    try:
        import psutil
    except ImportError:
        return []
    found = []
    for process in psutil.process_iter(["pid", "name", "exe"]):
        name = str(process.info.get("name") or "").lower()
        if name.startswith("ollama"):
            found.append(process)
    return found


def _hidden_creation_flags() -> int:
    """A server with a hidden console of its own - never a server with no console at all.

    The old value was CREATE_NO_WINDOW | DETACHED_PROCESS, and on Windows the second flag
    cancels the first: a detached process has no console, so every console program it
    starts gets a brand-new one, and Windows 11 opens Windows Terminal to show it. Ollama
    starts a runner (llama-server.exe) plus a gpu-discover helper every time it loads a
    model, so from the restart of 2026-09-11 23:14 until this fix every model load flashed
    three terminal windows at the owner, 0.4-0.6 s apiece - measured with a window sampler
    on 2026-09-12 at 08:27:24, :25 and :26, one window per Ollama child.

    Measured on this machine from a parent with no console, cmd /c (cmd /c exit), does the
    grandchild open a visible window:

        CREATE_NO_WINDOW | DETACHED_PROCESS | NEW_PROCESS_GROUP   YES   (the old flags)
        CREATE_NO_WINDOW | NEW_PROCESS_GROUP                      no    (these flags)
        CREATE_NO_WINDOW                                          no    (what analysis.py uses)
        no flags at all                                           no

    Surviving the watchdog's exit never needed DETACHED_PROCESS: a Windows child outlives
    its parent unless a job object says otherwise, and the 23:14 server outlived its parent
    by nine hours. CREATE_NEW_PROCESS_GROUP stays so a Ctrl+C aimed at the watchdog cannot
    reach the server.
    """
    if os.name != "nt":
        return 0
    return getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000) | getattr(
        subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200
    )


def restart_ollama() -> bool:
    """Kill the wedged server and start a new one, which is the only thing that helps.

    The context is gone for the lifetime of that process; there is no in-process cure to
    try first. Started with a hidden console of its own - see _hidden_creation_flags for
    why "detached" was the wrong word and what it cost.
    """
    processes = _ollama_processes()
    executable = OLLAMA_EXE_FALLBACK
    for process in processes:
        candidate = process.info.get("exe")
        if candidate:
            executable = Path(str(candidate))
            break
    for process in processes:
        try:
            process.kill()
        except Exception:  # noqa: BLE001 - already gone is the outcome we wanted
            pass
    for process in processes:
        try:
            process.wait(timeout=15)
        except Exception:  # noqa: BLE001
            pass

    if not executable.is_file():
        return False
    creation_flags = _hidden_creation_flags()
    try:
        subprocess.Popen(  # noqa: S603 - fixed argv, no shell
            [str(executable), "serve"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=creation_flags,
        )
    except OSError:
        return False

    deadline = time.monotonic() + RESTART_SETTLE_SECONDS
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(f"{OLLAMA_BASE_URL}/api/tags", timeout=5) as response:
                if response.status == 200:
                    return True
        except (urllib.error.URLError, OSError, ValueError, TimeoutError):
            pass
        time.sleep(2)
    return False


def main(argv: list[str]) -> int:
    dry_run = "--dry-run" in argv
    positional = [value for value in argv if not value.startswith("--")]
    root = Path(positional[0]) if positional else DEFAULT_VERSIONS_ROOT

    def say(line: str) -> None:
        _log_line(root, line)
        _say_safely(line)

    running = running_projects(root)
    if not running:
        _say_safely("không có project nào đang chạy; không đụng tới Ollama")
        return 0

    stalled = []
    for project in running:
        quiet = seconds_since_progress(project)
        label = f"{project.parent.name}/{project.name}"
        if quiet is None:
            _say_safely(f"  {label}: chưa có log, bỏ qua")
            continue
        if quiet < STALL_SECONDS:
            _say_safely(f"  {label}: log vừa chạy {quiet:.0f}s trước, khỏe")
            continue
        stalled.append((label, quiet))

    if not stalled:
        return 0

    for label, quiet in stalled:
        say(f"{label}: log im {quiet / 60:.1f} phút, đang dò Ollama")

    models = loaded_models()
    if not models:
        # Nothing loaded means nothing is wedged around a dead context. A worker that
        # needs Ollama will load a model itself, and evicting nothing helps nobody.
        say("Ollama không giữ model nào; không phải kiểu treo này, không khởi động lại")
        return 0

    model = models[0]
    verdict, detail = probe_verdict(model)
    if verdict == PROBE_OK:
        say(f"Ollama vẫn sinh được chữ với {model}; đứng im là do việc khác")
        return 0
    if verdict != PROBE_TIMEOUT:
        # Một lỗi trả về NHANH không phải chữ ký treo: treo là im lặng đủ 120 giây. Ollama
        # đang bận, đang khởi động lại, hay từ chối - không cái nào chữa được bằng giết nó.
        say(f"Ollama giữ {model}, probe lỗi ({detail}) - không phải kiểu treo, không khởi động lại")
        return 0

    say(
        f"Ollama giữ {model} nhưng không sinh nổi một token trong "
        f"{PROBE_TIMEOUT_SECONDS}s ({detail}) - đúng kiểu treo sau khi máy ngủ"
    )
    if dry_run:
        say("  (thử khan, không khởi động lại)")
        return 0

    if restart_ollama():
        say("  đã khởi động lại Ollama, API trả lời trở lại")
        return 0
    say("  KHỞI ĐỘNG LẠI THẤT BẠI - cần người xem")
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
