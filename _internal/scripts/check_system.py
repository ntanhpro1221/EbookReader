from __future__ import annotations

import importlib
import os
import shutil
import subprocess
import sys
from pathlib import Path

import psutil


def status(ok: bool, label: str, detail: str = "") -> None:
    mark = "OK" if ok else "FAIL"
    print(f"[{mark}] {label}" + (f": {detail}" if detail else ""))


def command_output(command: list[str], timeout: int = 20) -> tuple[bool, str]:
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0,
        )
        return result.returncode == 0, (result.stdout or result.stderr).strip()
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)


def main() -> int:
    failures = 0
    version_ok = (3, 11) <= sys.version_info[:2] < (3, 13)
    status(version_ok, "Python", sys.version.split()[0])
    failures += not version_ok

    memory_gb = psutil.virtual_memory().total / 1024**3
    status(memory_gb >= 24, "RAM", f"{memory_gb:.1f} GB")
    failures += memory_gb < 24

    disk_gb = psutil.disk_usage(str(Path.cwd().anchor or Path.cwd())).free / 1024**3
    status(disk_gb >= 30, "SSD free", f"{disk_gb:.1f} GB")
    if disk_gb < 12:
        failures += 1

    nvidia = shutil.which("nvidia-smi")
    status(bool(nvidia), "nvidia-smi", nvidia or "not found")
    if nvidia:
        ok, output = command_output([
            nvidia,
            "--query-gpu=name,memory.total,driver_version,temperature.gpu",
            "--format=csv,noheader",
        ])
        status(ok, "NVIDIA GPU", output.splitlines()[0] if output else "no output")
        failures += not ok
    else:
        failures += 1

    modules = [
        "PySide6", "requests", "psutil", "numpy", "soundfile", "imageio_ffmpeg",
        "torch", "torchaudio", "whisper", "vieneu",
    ]
    for name in modules:
        try:
            importlib.import_module(name)
            status(True, f"Python module {name}")
        except Exception as exc:  # noqa: BLE001
            status(False, f"Python module {name}", str(exc))
            failures += 1

    try:
        import torch

        cuda_ok = torch.cuda.is_available()
        detail = torch.cuda.get_device_name(0) if cuda_ok else "CUDA unavailable"
        status(cuda_ok, "PyTorch CUDA", detail)
        failures += not cuda_ok
        if cuda_ok:
            print(f"    PyTorch={torch.__version__}; CUDA runtime={torch.version.cuda}; "
                  f"VRAM={torch.cuda.get_device_properties(0).total_memory/1024**3:.1f} GB")
    except Exception:
        pass

    try:
        import imageio_ffmpeg

        ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
        ok, output = command_output([ffmpeg, "-version"])
        status(ok, "FFmpeg", output.splitlines()[0] if output else ffmpeg)
        failures += not ok
    except Exception as exc:  # noqa: BLE001
        status(False, "FFmpeg", str(exc))
        failures += 1

    ollama = shutil.which("ollama")
    status(bool(ollama), "Ollama", ollama or "not found")
    if ollama:
        ok, output = command_output([ollama, "list"], timeout=30)
        for model_name in ("qwen3:8b", "qwen3:4b"):
            has_qwen = ok and model_name in output
            status(has_qwen, f"Ollama model {model_name}", "installed" if has_qwen else output[:500])
            failures += not has_qwen
    else:
        failures += 1

    print()
    if failures:
        print(f"System check found {failures} blocking/missing item(s). Run START.vbs or inspect output above.")
        return 1
    print("System check passed. Start with one 2,000–5,000 word chapter before a full book.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
