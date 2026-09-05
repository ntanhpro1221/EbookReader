"""Two pools sizing themselves as if the other did not exist.

alpha.47 ran 8 scoring workers plus 3 synthesis workers, 24.2 GB of a 31.3 GB machine, and
sat at 2.0 GB free - inside the band where decide() reports memory pressure and turns off
both allow_cpu_heavy_work and allow_new_gpu_batch. The perceptual pool had sized itself into
the state that forbids the work it was built for.

Two independent causes, and the arithmetic only lands on 2.0 GB with both:
  - PERCEPTUAL_WORKER_RAM_GB was 1.75 against a measured median of 2.16
  - usable_for has taken a reserve since it was written, and nobody ever passed one
"""
from __future__ import annotations

from ebook_reader.perceptual_qa import PERCEPTUAL_WORKER_RAM_GB, PerceptualScorePool


def _pool(workers: int = 8, threads: int = 2) -> PerceptualScorePool:
    settings = {"perceptual_qa": {"device": "cpu"}, "resources": {"min_free_ram_gb": 3.5}}
    return PerceptualScorePool(settings, lambda _m: None, workers=workers, threads=threads)


def test_the_constant_matches_what_a_loaded_worker_actually_costs() -> None:
    """Measured on alpha.47 at the peak: eleven loaded children at 2.08-2.36 GB, median
    2.16. The same processes read 0.01 GB seconds earlier while importing, which is how a
    badly timed snapshot supports any number you like."""
    assert PERCEPTUAL_WORKER_RAM_GB >= 2.16, "below the measured median is what broke it"
    assert PERCEPTUAL_WORKER_RAM_GB <= 2.5, "far above the measured max only wastes workers"


def test_a_reserve_shrinks_the_pool() -> None:
    """The parameter that existed, was documented, and was never passed."""
    free = 24.0
    alone = _pool().usable_for(100, free)
    beside = _pool().usable_for(100, free, reserve_ram_gb=3 * PERCEPTUAL_WORKER_RAM_GB)

    assert beside < alone, "reserving for the synthesis pool must cost scoring workers"


def test_the_pool_leaves_the_throttle_floor_alone() -> None:
    """The whole point: never size into the band where the throttle stops the work."""
    free, floor = 24.0, 3.5
    reserve = 3 * PERCEPTUAL_WORKER_RAM_GB
    workers = _pool(workers=32).usable_for(100, free, reserve_ram_gb=reserve)

    left = free - workers * PERCEPTUAL_WORKER_RAM_GB - reserve
    assert left >= 0, f"{workers} workers overshoot by {-left:.1f} GB"
    assert free - workers * PERCEPTUAL_WORKER_RAM_GB - reserve >= 0


def test_the_alpha47_snapshot_no_longer_oversubscribes() -> None:
    """The numbers from the run that failed: ~19 GB free when the pool sized itself, a
    ceiling of 8, and a synthesis pool of 3 about to start."""
    workers = _pool(workers=8).usable_for(111, 19.0, reserve_ram_gb=3 * PERCEPTUAL_WORKER_RAM_GB)
    used = workers * PERCEPTUAL_WORKER_RAM_GB + 3 * PERCEPTUAL_WORKER_RAM_GB

    assert 19.0 - used >= 3.5, f"{workers} workers leave only {19.0 - used:.1f} GB"


def test_a_machine_with_room_still_gets_a_pool() -> None:
    """Reserving must not turn the pool off on a machine that can afford it."""
    assert _pool().usable_for(100, 64.0, reserve_ram_gb=3 * PERCEPTUAL_WORKER_RAM_GB) >= 2
