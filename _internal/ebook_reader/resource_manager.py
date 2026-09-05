from __future__ import annotations

import ctypes
import os
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import psutil

from .models import ResourceDecision, ResourceLevel


@dataclass(slots=True)
class ResourceSnapshot:
    cpu_percent: float
    free_ram_gb: float
    disk_free_gb: float
    disk_active_percent: float | None
    gpu_temp_c: int | None
    gpu_free_mb: int | None
    gpu_total_mb: int | None
    foreground_cpu_percent: float | None
    foreground_gpu_percent: float | None
    seconds_since_user_input: float | None


class WindowsActivityProbe:
    def __init__(self) -> None:
        self._process_samples: dict[int, psutil.Process] = {}

    @staticmethod
    def foreground_pid() -> int | None:
        if os.name != "nt":
            return None
        try:
            user32 = ctypes.windll.user32
            hwnd = user32.GetForegroundWindow()
            if not hwnd:
                return None
            pid = ctypes.c_ulong()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            return int(pid.value) or None
        except Exception:
            return None

    @staticmethod
    def seconds_since_input() -> float | None:
        if os.name != "nt":
            return None
        try:
            class LASTINPUTINFO(ctypes.Structure):
                _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]

            info = LASTINPUTINFO()
            info.cbSize = ctypes.sizeof(info)
            if not ctypes.windll.user32.GetLastInputInfo(ctypes.byref(info)):
                return None
            tick = ctypes.windll.kernel32.GetTickCount()
            return max(0.0, (tick - info.dwTime) / 1000.0)
        except Exception:
            return None

    def process_cpu(self, pid: int | None) -> float | None:
        if not pid:
            return None
        try:
            proc = self._process_samples.get(pid)
            if proc is None or not proc.is_running():
                proc = psutil.Process(pid)
                proc.cpu_percent(None)
                self._process_samples[pid] = proc
                return 0.0
            return proc.cpu_percent(None)
        except (psutil.Error, OSError):
            self._process_samples.pop(pid, None)
            return None


class NvidiaProbe:
    def __init__(self) -> None:
        self.executable = shutil.which("nvidia-smi")
        self._process_cache_pid: int | None = None
        self._process_cache_value: float | None = None
        self._process_cache_at = 0.0

    def gpu_temperature(self) -> int | None:
        if not self.executable:
            return None
        try:
            completed = subprocess.run(
                [
                    self.executable,
                    "--query-gpu=temperature.gpu",
                    "--format=csv,noheader,nounits",
                ],
                capture_output=True,
                text=True,
                timeout=5,
                check=True,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0,
            )
            return int(float(completed.stdout.strip().splitlines()[0]))
        except Exception:
            return None

    def gpu_memory(self) -> tuple[int | None, int | None]:
        """Free and total VRAM in MiB, or a pair of Nones on any machine without them.

        Nothing in this project could see VRAM before this. Every constant that depends on
        it - how many synthesis workers fit, how large a context window to reserve, whether
        Whisper can stay resident - was therefore fitted by hand against one 8 GiB card and
        written into the defaults, which is why they were right here and wrong anywhere
        else. A number that cannot be measured has to be guessed.

        Reported for the device as a whole, not for this process: the question these
        callers ask is how much room is left on the card, and the foreground program
        holding the rest of it does not report to us.
        """
        if not self.executable:
            return None, None
        try:
            completed = subprocess.run(
                [
                    self.executable,
                    "--query-gpu=memory.free,memory.total",
                    "--format=csv,noheader,nounits",
                ],
                capture_output=True,
                text=True,
                timeout=5,
                check=True,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0,
            )
            free_text, _separator, total_text = completed.stdout.strip().splitlines()[0].partition(",")
            return int(float(free_text)), int(float(total_text))
        except Exception:
            return None, None

    def process_gpu_percent(self, pid: int | None) -> float | None:
        if not self.executable or not pid:
            return None
        now = time.monotonic()
        if pid == self._process_cache_pid and now - self._process_cache_at < 8.0:
            return self._process_cache_value
        # pmon reports one-second per-process samples and includes graphics/compute utilization.
        try:
            completed = subprocess.run(
                [self.executable, "pmon", "-c", "1", "-s", "um"],
                capture_output=True,
                text=True,
                timeout=8,
                check=True,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0,
            )
            total = 0.0
            found = False
            for line in completed.stdout.splitlines():
                fields = line.split()
                if len(fields) < 5 or not fields[0].isdigit() or not fields[1].isdigit():
                    continue
                if int(fields[1]) != pid:
                    continue
                found = True
                for token in fields[3:5]:
                    if token != "-":
                        try:
                            total += float(token)
                        except ValueError:
                            pass
            value = min(100.0, total) if found else 0.0
            self._process_cache_pid = pid
            self._process_cache_value = value
            self._process_cache_at = now
            return value
        except Exception:
            return self._process_cache_value if pid == self._process_cache_pid else None


def trim_process_working_set() -> bool:
    """Return unused pages from this process to Windows after unloading large models."""
    if os.name != "nt":
        return False
    try:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        psapi = ctypes.WinDLL("psapi", use_last_error=True)
        get_current_process = kernel32.GetCurrentProcess
        get_current_process.argtypes = []
        get_current_process.restype = ctypes.c_void_p
        empty_working_set = psapi.EmptyWorkingSet
        empty_working_set.argtypes = [ctypes.c_void_p]
        empty_working_set.restype = ctypes.c_int
        return bool(empty_working_set(get_current_process()))
    except (AttributeError, OSError, ValueError):
        return False


class AdaptiveResourceManager:
    """Makes conservative, reversible resource decisions without user interaction."""

    def __init__(self, settings: dict[str, Any], project_root: Path) -> None:
        self.settings = settings["resources"]
        self.project_root = project_root
        self.windows = WindowsActivityProbe()
        self.nvidia = NvidiaProbe()
        self._last_disk_io = psutil.disk_io_counters()
        self._last_disk_time = time.monotonic()
        self._last_pressure_at = time.monotonic()
        self._last_level = ResourceLevel.MAXIMUM
        self._thermal_hold = False
        self._last_snapshot: ResourceSnapshot | None = None
        self._last_snapshot_at = 0.0

    def update_settings(self, resources: dict[str, Any]) -> None:
        self.settings = dict(resources)
        self._last_snapshot_at = 0.0

    def is_ram_only_critical(self, snapshot: ResourceSnapshot) -> bool:
        """Return whether unloading models can resolve the complete critical condition."""
        cfg = self.settings
        ram_critical = snapshot.free_ram_gb <= float(cfg["critical_free_ram_gb"])
        disk_critical = snapshot.disk_free_gb <= float(cfg["critical_free_disk_gb"])
        gpu_critical = bool(
            snapshot.gpu_temp_c is not None
            and snapshot.gpu_temp_c >= int(cfg["critical_gpu_temp_c"])
        )
        return ram_critical and not disk_critical and not gpu_critical

    def snapshot(self, force: bool = False) -> ResourceSnapshot:
        now = time.monotonic()
        if not force and self._last_snapshot is not None and now - self._last_snapshot_at < 1.5:
            return self._last_snapshot
        cpu = float(psutil.cpu_percent(interval=0.15))
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage(str(self.project_root.anchor or self.project_root))
        current_io = psutil.disk_io_counters()
        disk_active: float | None = None
        elapsed = max(0.001, now - self._last_disk_time)
        if current_io and self._last_disk_io and hasattr(current_io, "busy_time"):
            busy_delta = max(0, current_io.busy_time - self._last_disk_io.busy_time)
            disk_active = min(100.0, busy_delta / (elapsed * 10.0))
        self._last_disk_io = current_io
        self._last_disk_time = now

        gpu_temp = self.nvidia.gpu_temperature()
        gpu_free_mb, gpu_total_mb = self.nvidia.gpu_memory()
        pid = self.windows.foreground_pid()
        foreground_cpu = self.windows.process_cpu(pid)
        foreground_gpu = self.nvidia.process_gpu_percent(pid)
        snapshot = ResourceSnapshot(
            cpu_percent=cpu,
            free_ram_gb=memory.available / (1024**3),
            disk_free_gb=disk.free / (1024**3),
            disk_active_percent=disk_active,
            gpu_temp_c=gpu_temp,
            gpu_free_mb=gpu_free_mb,
            gpu_total_mb=gpu_total_mb,
            foreground_cpu_percent=foreground_cpu,
            foreground_gpu_percent=foreground_gpu,
            seconds_since_user_input=self.windows.seconds_since_input(),
        )
        self._last_snapshot = snapshot
        self._last_snapshot_at = now
        return snapshot

    def decide(self, snapshot: ResourceSnapshot | None = None) -> ResourceDecision:
        s = snapshot or self.snapshot()
        cfg = self.settings

        critical_reasons: list[str] = []
        if s.disk_free_gb <= float(cfg["critical_free_disk_gb"]):
            critical_reasons.append(f"disk free {s.disk_free_gb:.1f} GB")
        if s.free_ram_gb <= float(cfg["critical_free_ram_gb"]):
            critical_reasons.append(f"available RAM {s.free_ram_gb:.1f} GB")
        if s.gpu_temp_c is not None and s.gpu_temp_c >= int(cfg["critical_gpu_temp_c"]):
            critical_reasons.append(f"GPU temperature {s.gpu_temp_c}°C")
        if critical_reasons:
            self._last_pressure_at = time.monotonic()
            self._last_level = ResourceLevel.CRITICAL_STOP
            return ResourceDecision(
                ResourceLevel.CRITICAL_STOP,
                "; ".join(critical_reasons),
                gpu_batch_scale=0.0,
                allow_new_gpu_batch=False,
                unload_idle_models=True,
                critical=True,
            )

        max_temp = int(cfg["max_gpu_temp_c"])
        resume_temp = int(cfg["resume_gpu_temp_c"])
        if s.gpu_temp_c is not None and s.gpu_temp_c >= max_temp:
            self._thermal_hold = True
        if self._thermal_hold:
            if s.gpu_temp_c is None or s.gpu_temp_c > resume_temp:
                self._last_pressure_at = time.monotonic()
                self._last_level = ResourceLevel.PAUSE_NEW_WORK
                detail = "unknown" if s.gpu_temp_c is None else f"{s.gpu_temp_c}°C"
                return ResourceDecision(
                    ResourceLevel.PAUSE_NEW_WORK,
                    f"GPU cooling at {detail}; resume at {resume_temp}°C",
                    gpu_batch_scale=0.0,
                    allow_new_gpu_batch=False,
                    unload_idle_models=False,
                )
            self._thermal_hold = False
            self._last_pressure_at = time.monotonic()

        adaptive_foreground = str(cfg.get("mode", "max_safe_adaptive_foreground")) != "max_safe"
        heavy_reasons: list[str] = []
        foreground_gpu_pressure = bool(
            adaptive_foreground
            and s.foreground_gpu_percent is not None
            and s.foreground_gpu_percent >= float(cfg["foreground_gpu_trigger"])
        )
        if foreground_gpu_pressure:
            heavy_reasons.append(f"foreground GPU {s.foreground_gpu_percent:.0f}%")
        foreground_cpu_pressure = bool(
            adaptive_foreground
            and s.foreground_cpu_percent is not None
            and s.foreground_cpu_percent >= float(cfg["foreground_cpu_trigger"])
        )
        disk_io_pressure = bool(
            adaptive_foreground
            and s.disk_active_percent is not None
            and s.disk_active_percent >= float(cfg["system_disk_trigger"])
        )
        if foreground_cpu_pressure:
            heavy_reasons.append(f"foreground CPU {s.foreground_cpu_percent:.0f}%")
        if disk_io_pressure:
            heavy_reasons.append(f"disk active {s.disk_active_percent:.0f}%")
        memory_pressure = s.free_ram_gb <= float(cfg["min_free_ram_gb"])
        disk_space_pressure = s.disk_free_gb <= float(cfg["min_free_disk_gb"])
        if memory_pressure:
            heavy_reasons.append(f"available RAM {s.free_ram_gb:.1f} GB")
        if disk_space_pressure:
            heavy_reasons.append(f"disk free {s.disk_free_gb:.1f} GB")
        if heavy_reasons:
            self._last_pressure_at = time.monotonic()
            self._last_level = ResourceLevel.YIELD_HEAVY
            return ResourceDecision(
                ResourceLevel.YIELD_HEAVY,
                "; ".join(heavy_reasons),
                gpu_batch_scale=0.25,
                # Stop dispatching new GPU work when the foreground app is actually using GPU.
                allow_new_gpu_batch=not (
                    foreground_gpu_pressure or memory_pressure or disk_space_pressure
                ),
                allow_cpu_heavy_work=not (
                    foreground_cpu_pressure or disk_io_pressure or memory_pressure or disk_space_pressure
                ),
                unload_idle_models=bool(cfg.get("unload_model_for_foreground_vram", True))
                and ((s.foreground_gpu_percent or 0) >= 65 or memory_pressure),
            )

        user_active = s.seconds_since_user_input is not None and s.seconds_since_user_input < 8
        interactive_pressure = adaptive_foreground and user_active and s.cpu_percent >= 55.0
        if s.cpu_percent >= float(cfg["system_cpu_trigger"]) or interactive_pressure:
            self._last_pressure_at = time.monotonic()
            self._last_level = ResourceLevel.YIELD_LIGHT
            reason = f"system CPU {s.cpu_percent:.0f}%" if s.cpu_percent >= float(cfg["system_cpu_trigger"]) else "user is active"
            return ResourceDecision(
                ResourceLevel.YIELD_LIGHT,
                reason,
                gpu_batch_scale=0.70,
                allow_new_gpu_batch=True,
                # True, and it has to be. Reaching this branch already proves every CPU-side
                # pressure is absent: foreground_cpu_pressure, disk_io_pressure,
                # memory_pressure and disk_space_pressure are each False, or the YIELD_HEAVY
                # branch above would have returned instead. Blocking CPU work here made the
                # *lighter* yield stricter than the heavier one, which gates the same flag on
                # those pressures actually existing.
                #
                # Not a small inversion. pipeline._wait_for_resources sleeps two seconds and
                # re-asks whenever a checkpoint needs CPU I/O and this is False, so the run
                # simply stopped for as long as somebody used the machine. Measured across
                # alpha.46's first 4.4 hours:
                #
                #   maximum      452 segments in  80.6 min  =  5.60 /min
                #   yield_heavy   69 segments in  30.4 min  =  2.27 /min
                #   yield_light   57 segments in 150.2 min  =  0.38 /min
                #
                # One "user is active" stretch ran 21:44 to 23:36 - 112 minutes at a
                # fifteenth of full speed, for a level whose declared throttle is 0.70. The
                # GPU scale above is the yield this level is meant to apply; that is enough.
                allow_cpu_heavy_work=True,
            )

        stable_for = time.monotonic() - self._last_pressure_at
        ramp_wait = float(cfg.get("idle_seconds_before_ramp", 20))
        ramp_step = max(0.0, float(cfg.get("ramp_step_seconds", 8)))
        if stable_for < ramp_wait + ramp_step and self._last_level != ResourceLevel.MAXIMUM:
            ramp_progress = max(0.0, min(1.0, (stable_for - ramp_wait) / max(0.001, ramp_step)))
            gpu_scale = 0.60 + 0.30 * ramp_progress
            return ResourceDecision(
                ResourceLevel.YIELD_LIGHT,
                f"ramping after {stable_for:.0f}/{ramp_wait + ramp_step:.0f}s stable",
                gpu_batch_scale=gpu_scale,
                allow_new_gpu_batch=True,
            )

        self._last_level = ResourceLevel.MAXIMUM
        return ResourceDecision(ResourceLevel.MAXIMUM, "resources available")

def set_worker_priority(priority: str = "below_normal") -> None:
    try:
        proc = psutil.Process(os.getpid())
        if os.name == "nt":
            values = {
                "idle": psutil.IDLE_PRIORITY_CLASS,
                "below_normal": psutil.BELOW_NORMAL_PRIORITY_CLASS,
                "normal": psutil.NORMAL_PRIORITY_CLASS,
                "above_normal": psutil.ABOVE_NORMAL_PRIORITY_CLASS,
            }
            proc.nice(values.get(priority, psutil.BELOW_NORMAL_PRIORITY_CLASS))
        elif priority in {"idle", "below_normal"}:
            proc.nice(10 if priority == "idle" else 5)
    except Exception:
        pass
