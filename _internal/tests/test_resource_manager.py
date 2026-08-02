from __future__ import annotations

from pathlib import Path

from e_book_reader.config import build_settings
from e_book_reader.models import ResourceLevel
from e_book_reader.resource_manager import AdaptiveResourceManager, ResourceSnapshot


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


def test_gpu_temperature_uses_resume_hysteresis(tmp_path: Path) -> None:
    manager = AdaptiveResourceManager(build_settings(), tmp_path)

    hot = manager.decide(snapshot(gpu_temp_c=86))
    cooling = manager.decide(snapshot(gpu_temp_c=84))
    resumed = manager.decide(snapshot(gpu_temp_c=80))

    assert hot.level == ResourceLevel.PAUSE_NEW_WORK
    assert cooling.level == ResourceLevel.PAUSE_NEW_WORK
    assert cooling.allow_new_gpu_batch is False
    assert resumed.allow_new_gpu_batch is True
