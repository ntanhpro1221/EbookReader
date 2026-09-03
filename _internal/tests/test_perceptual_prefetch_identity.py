"""A perceptual score belongs to audio, not to a path.

Scoring moved to run beside ASR, and ASR repair re-cuts segments: it writes a new take to
the same path the old score was filed under. Filing by path would hand the new take the
score of the take that was thrown away - a number the listener never had a chance to hear
standing in for one they did. Filing by checksum makes that impossible rather than
unlikely, because a replaced take simply is not in the map.
"""
from pathlib import Path

import numpy as np
import soundfile as sf

from ebook_reader.io_utils import sha256_file
from ebook_reader.perceptual_qa import (
    PerceptualScorePool,
    _score_worker_job,
    _WORKER,
)


def _wav(path: Path, seed: int) -> Path:
    generator = np.random.default_rng(seed)
    sf.write(path, generator.normal(0.0, 0.05, 24000).astype("float32"), 24000, subtype="PCM_16")
    return path


class _Scorer:
    def __init__(self, score: float) -> None:
        self.score = score

    def _score(self, _path: Path) -> float:
        return self.score


def _pool_settings() -> dict:
    return {"perceptual_qa": {"enabled": True, "device": "cpu", "checkpoint_path": "x"}}


def test_a_score_is_filed_under_the_audio_it_heard(tmp_path, monkeypatch) -> None:
    wav = _wav(tmp_path / "take.wav", 1)
    monkeypatch.setitem(_WORKER, "verifier", _Scorer(3.25))

    key, score = _score_worker_job(str(wav))

    assert score == 3.25
    assert key == sha256_file(wav)
    assert key != str(wav)


def test_recutting_a_segment_hides_the_old_score_rather_than_reusing_it(
    tmp_path, monkeypatch
) -> None:
    """The defect this design exists to prevent, played out in order."""
    wav = _wav(tmp_path / "take.wav", 1)
    monkeypatch.setitem(_WORKER, "verifier", _Scorer(2.10))
    key, _score = _score_worker_job(str(wav))
    scores = {key: 2.10}

    # ASR repair replaces the take. Same path, same segment row, different audio.
    _wav(wav, 2)
    checksum_now = sha256_file(wav)

    assert checksum_now != key
    assert scores.get(checksum_now) is None, "the parent must score the new take itself"


def test_a_file_that_cannot_be_scored_reports_nothing(tmp_path, monkeypatch) -> None:
    """A worker never decides anything, so a failure has to be indistinguishable from
    a file the pool was never given."""
    monkeypatch.setitem(_WORKER, "verifier", None)
    assert _score_worker_job(str(tmp_path / "missing.wav"))[1] is None


def test_workers_are_sized_below_what_a_stage_alongside_has_not_taken_yet(tmp_path) -> None:
    """Scoring beside ASR is sized from a snapshot; if that snapshot predates the model
    loading, the pool promises itself memory the model is about to want."""
    pool = PerceptualScorePool(_pool_settings(), lambda _m: None, workers=8)
    unreserved = pool.usable_for(24, 12.0)
    reserved = pool.usable_for(24, 12.0, reserve_ram_gb=6.0)

    assert unreserved > reserved >= 0
    assert pool.usable_for(24, 12.0, reserve_ram_gb=100.0) == 0


def test_a_negative_reserve_cannot_buy_extra_workers(tmp_path) -> None:
    pool = PerceptualScorePool(_pool_settings(), lambda _m: None, workers=8)
    assert pool.usable_for(24, 12.0, reserve_ram_gb=-50.0) == pool.usable_for(24, 12.0)


def test_a_worker_is_budgeted_for_what_it_actually_costs() -> None:
    """The number that decides how many workers a machine is offered.

    It was 1.0 GB. A worker's RSS after loading UTMOSv2 is 1.87 GB and peaks at 2.18 while
    scoring, and the marginal cost measured by watching system-wide free memory was 1.76 GB
    for the first worker and 1.52 for the second. At 1.0 the pool offered five workers on
    7.3 GB of free memory - about 8.8 GB of workers - which is not slow, it is how a run
    dies: alpha.26 stopped at 357 of 948 segments on "available RAM 1.1 GB".
    """
    from ebook_reader.perceptual_qa import PERCEPTUAL_WORKER_RAM_GB

    assert PERCEPTUAL_WORKER_RAM_GB >= 1.5, "below the smallest marginal cost measured"

    pool = PerceptualScorePool(_pool_settings(), lambda _m: None, workers=8)
    granted = pool.usable_for(95, 7.3)
    assert granted * PERCEPTUAL_WORKER_RAM_GB <= 7.3, "granted more memory than exists"


def test_the_pool_never_sizes_itself_into_the_throttle_it_lives_under() -> None:
    """decide() calls anything at or below resources.min_free_ram_gb memory pressure, and
    memory pressure turns off allow_cpu_heavy_work AND allow_new_gpu_batch together.

    A pool that spends the machine down to that band forbids its own work - and since
    scoring now runs beside ASR, it would stall the very ASR it is meant to hide behind.
    The old rule reserved a hardcoded 2.0 GB against a 3.5 GB threshold, so it landed
    squarely inside the band.
    """
    from ebook_reader.perceptual_qa import PERCEPTUAL_WORKER_RAM_GB

    settings = _pool_settings()
    settings["resources"] = {"min_free_ram_gb": 3.5}
    pool = PerceptualScorePool(settings, lambda _m: None, workers=8)

    for free_ram_gb in (4.0, 6.0, 7.3, 12.0, 24.0):
        granted = pool.usable_for(95, free_ram_gb)
        remaining = free_ram_gb - granted * PERCEPTUAL_WORKER_RAM_GB
        assert remaining >= 3.5, (free_ram_gb, granted, remaining)


def test_a_tighter_threshold_is_obeyed_rather_than_ignored() -> None:
    """The floor comes from the settings, so a project that raises it gets a smaller pool
    rather than a pool that argues with its own throttle."""
    generous = dict(_pool_settings(), resources={"min_free_ram_gb": 2.0})
    strict = dict(_pool_settings(), resources={"min_free_ram_gb": 8.0})
    assert PerceptualScorePool(generous, lambda _m: None, workers=8).usable_for(95, 12.0) > (
        PerceptualScorePool(strict, lambda _m: None, workers=8).usable_for(95, 12.0)
    )
