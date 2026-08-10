from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from ebook_reader.config import build_settings
from ebook_reader.models import ResourceLevel
from ebook_reader import resource_manager
from ebook_reader.resource_manager import (
    AdaptiveResourceManager,
    ResourceSnapshot,
    trim_process_working_set,
)


def snapshot(**updates):
    values = dict(
        cpu_percent=20.0,
        free_ram_gb=12.0,
        disk_free_gb=100.0,
        disk_active_percent=5.0,
        gpu_temp_c=70,
        foreground_cpu_percent=5.0,
        foreground_gpu_percent=0.0,
        seconds_since_user_input=30.0,
    )
    values.update(updates)
    return ResourceSnapshot(**values)


def test_trim_process_working_set_calls_windows_api(monkeypatch) -> None:
    calls: list[tuple[str, object]] = []

    class FakeFunction:
        def __init__(self, name: str, result: object) -> None:
            self.name = name
            self.result = result
            self.argtypes = None
            self.restype = None

        def __call__(self, *args):
            calls.append((self.name, args))
            return self.result

    kernel32 = SimpleNamespace(GetCurrentProcess=FakeFunction("GetCurrentProcess", 123))
    psapi = SimpleNamespace(EmptyWorkingSet=FakeFunction("EmptyWorkingSet", 1))

    def fake_win_dll(name: str, **_kwargs):
        return {"kernel32": kernel32, "psapi": psapi}[name]

    monkeypatch.setattr(resource_manager.os, "name", "nt")
    monkeypatch.setattr(resource_manager.ctypes, "WinDLL", fake_win_dll, raising=False)

    assert trim_process_working_set() is True
    assert calls == [
        ("GetCurrentProcess", ()),
        ("EmptyWorkingSet", (123,)),
    ]


def test_critical_disk_stops(tmp_path: Path) -> None:
    manager = AdaptiveResourceManager(build_settings(), tmp_path)
    decision = manager.decide(snapshot(disk_free_gb=2.0))
    assert decision.level == ResourceLevel.CRITICAL_STOP
    assert decision.critical


def test_heavy_foreground_yields(tmp_path: Path) -> None:
    manager = AdaptiveResourceManager(build_settings(), tmp_path)
    decision = manager.decide(snapshot(foreground_gpu_percent=70.0))
    assert decision.level == ResourceLevel.YIELD_HEAVY
    assert decision.gpu_batch_scale < 1
    assert decision.allow_new_gpu_batch is False
    assert decision.unload_idle_models is True


def test_max_safe_mode_ignores_foreground_but_not_safety(tmp_path: Path) -> None:
    settings = build_settings(overrides={"resources": {"mode": "max_safe"}})
    manager = AdaptiveResourceManager(settings, tmp_path)
    decision = manager.decide(snapshot(foreground_gpu_percent=90.0, foreground_cpu_percent=90.0))
    assert decision.level in {ResourceLevel.MAXIMUM, ResourceLevel.YIELD_LIGHT}


def test_heavy_cpu_without_foreground_gpu_can_keep_gpu_working(tmp_path: Path) -> None:
    manager = AdaptiveResourceManager(build_settings(), tmp_path)
    decision = manager.decide(snapshot(foreground_cpu_percent=80.0, foreground_gpu_percent=0.0))
    assert decision.level == ResourceLevel.YIELD_HEAVY
    assert decision.allow_new_gpu_batch is True
    assert decision.allow_cpu_heavy_work is False


def test_low_noncritical_disk_pauses_new_work_until_space_is_freed(tmp_path: Path) -> None:
    manager = AdaptiveResourceManager(build_settings(), tmp_path)
    decision = manager.decide(snapshot(disk_free_gb=8.0))
    assert decision.level == ResourceLevel.YIELD_HEAVY
    assert decision.allow_new_gpu_batch is False
    assert decision.allow_cpu_heavy_work is False


def test_low_noncritical_ram_pauses_and_releases_models(tmp_path: Path) -> None:
    manager = AdaptiveResourceManager(build_settings(), tmp_path)
    decision = manager.decide(snapshot(free_ram_gb=2.5))
    assert decision.level == ResourceLevel.YIELD_HEAVY
    assert decision.allow_new_gpu_batch is False
    assert decision.unload_idle_models is True


def test_only_ram_critical_is_recoverable_by_unloading_models(tmp_path: Path) -> None:
    manager = AdaptiveResourceManager(build_settings(), tmp_path)

    assert manager.is_ram_only_critical(snapshot(free_ram_gb=0.8)) is True
    assert manager.is_ram_only_critical(snapshot(free_ram_gb=0.8, disk_free_gb=2.0)) is False
    assert manager.is_ram_only_critical(snapshot(free_ram_gb=0.8, gpu_temp_c=96)) is False


def test_gpu_temperature_uses_resume_hysteresis(tmp_path: Path) -> None:
    manager = AdaptiveResourceManager(build_settings(), tmp_path)

    hot = manager.decide(snapshot(gpu_temp_c=86))
    cooling = manager.decide(snapshot(gpu_temp_c=84))
    resumed = manager.decide(snapshot(gpu_temp_c=80))

    assert hot.level == ResourceLevel.PAUSE_NEW_WORK
    assert cooling.level == ResourceLevel.PAUSE_NEW_WORK
    assert cooling.allow_new_gpu_batch is False
    assert resumed.allow_new_gpu_batch is True


def test_global_resource_settings_can_be_updated_while_manager_is_alive(tmp_path: Path) -> None:
    manager = AdaptiveResourceManager(build_settings(), tmp_path)
    updated = build_settings(overrides={
        "resources": {
            "mode": "max_safe",
            "max_gpu_temp_c": 90,
            "resume_gpu_temp_c": 84,
            "critical_gpu_temp_c": 95,
        }
    })

    manager.update_settings(updated["resources"])
    decision = manager.decide(snapshot(foreground_gpu_percent=90.0, gpu_temp_c=85))

    assert manager.settings["mode"] == "max_safe"
    assert manager.settings["max_gpu_temp_c"] == 90
    assert decision.level != ResourceLevel.PAUSE_NEW_WORK
