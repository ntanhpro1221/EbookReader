"""doctor answers whether the machine can hold the work, not just start it.

It checked that every module imports and every asset exists, and said nothing about memory.
A machine too small for the job passed every check and then found out slowly: yielding to
its own throttle at every gate, spilling the analysis model onto the CPU, or stopping
mid-book on "available RAM 1.1 GB", which is how alpha.26 ended at 357 segments of 948.

The thresholds stay absolute on purpose - they guard allocations that are the same size on
every machine, and a fraction of the machine is the wrong unit for a fixed-size model. What
a small machine is owed is a straight answer up front, not a looser threshold.
"""
from __future__ import annotations

import ebook_reader.cli as cli
from ebook_reader.perceptual_qa import PERCEPTUAL_WORKER_RAM_GB
from ebook_reader.tts_pool import (
    TTS_POOL_BASE_VRAM_MB,
    TTS_POOL_FOREGROUND_RESERVE_MB,
    TTS_POOL_WORKER_VRAM_MB,
)


class _Memory:
    def __init__(self, total_gb: float) -> None:
        self.total = int(total_gb * 1024**3)


def _with_machine(monkeypatch, *, ram_gb: float, vram_mb: int | None) -> dict:
    import psutil

    monkeypatch.setattr(psutil, "virtual_memory", lambda: _Memory(ram_gb))
    monkeypatch.setattr(
        "ebook_reader.resource_manager.NvidiaProbe.gpu_memory",
        lambda _self: (None, None) if vram_mb is None else (vram_mb // 2, vram_mb),
    )
    return cli._headroom_checks()


def test_this_machine_is_reported_as_able_to_do_the_work(monkeypatch) -> None:
    checks = _with_machine(monkeypatch, ram_gb=31.3, vram_mb=8151)
    assert checks["headroom:ram"]["ok"] is True
    assert checks["headroom:vram"]["ok"] is True


def test_a_machine_too_small_for_a_scoring_pool_is_told_so(monkeypatch) -> None:
    """Below the yield threshold plus two workers, the pool can never start at all, and
    every gate that asks for CPU-heavy work waits instead."""
    barely_short = 3.5 + 2 * PERCEPTUAL_WORKER_RAM_GB - 0.5
    checks = _with_machine(monkeypatch, ram_gb=barely_short, vram_mb=8151)
    assert checks["headroom:ram"]["ok"] is False
    assert "cần" in checks["headroom:ram"]["detail"]


def test_a_card_too_small_for_two_synthesis_workers_is_told_so(monkeypatch) -> None:
    needed = TTS_POOL_BASE_VRAM_MB + 2 * TTS_POOL_WORKER_VRAM_MB + TTS_POOL_FOREGROUND_RESERVE_MB
    assert _with_machine(monkeypatch, ram_gb=31.3, vram_mb=needed - 1)["headroom:vram"]["ok"] is False
    assert _with_machine(monkeypatch, ram_gb=31.3, vram_mb=needed)["headroom:vram"]["ok"] is True


def test_a_machine_with_no_nvidia_card_is_not_accused_of_anything(monkeypatch) -> None:
    """An unanswered question is not a failing answer: every run before VRAM could be read
    worked without knowing this, and still does."""
    checks = _with_machine(monkeypatch, ram_gb=31.3, vram_mb=None)
    assert checks["headroom:vram"]["ok"] is True
    assert "không đọc được" in checks["headroom:vram"]["detail"]


def test_the_requirement_moves_with_the_constants_it_is_made_of(monkeypatch) -> None:
    """Written as a number instead, this would keep passing after the thing it describes
    grew - which is how the scoring pool came to promise five workers on memory that fits
    two."""
    monkeypatch.setattr("ebook_reader.perceptual_qa.PERCEPTUAL_WORKER_RAM_GB", 8.0)
    checks = _with_machine(monkeypatch, ram_gb=16.0, vram_mb=8151)
    assert checks["headroom:ram"]["ok"] is False
    assert "8.0" in checks["headroom:ram"]["detail"]


def test_the_detail_says_what_the_requirement_is_made_of(monkeypatch) -> None:
    """A failing check that only says "not enough" leaves the reader to guess what to
    change."""
    checks = _with_machine(monkeypatch, ram_gb=31.3, vram_mb=8151)
    assert "ngưỡng nhường" in checks["headroom:ram"]["detail"]
    assert "chừa foreground" in checks["headroom:vram"]["detail"]
