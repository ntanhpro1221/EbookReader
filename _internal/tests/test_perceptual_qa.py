from __future__ import annotations

import os
import sys
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from ebook_reader import perceptual_qa as perceptual_module
from ebook_reader.perceptual_qa import (
    PERCEPTUAL_INCONCLUSIVE,
    PERCEPTUAL_OK,
    PERCEPTUAL_REVIEW,
    PerceptualQAUnavailable,
    PerceptualScorePool,
    UTMOSNaturalnessVerifier,
)
from ebook_reader.voice_catalog import VOICE_PREVIEW_FILENAMES


PRESET_NAME = "Phạm Tuyên"


def _settings(
    checkpoint: Path | None,
    *,
    enabled: bool = True,
    failure_policy: str = "fail",
    minimum_duration_seconds: float = 0.6,
) -> dict:
    return {
        "perceptual_qa": {
            "enabled": enabled,
            "failure_policy": failure_policy,
            "checkpoint_path": str(checkpoint) if checkpoint is not None else "",
            "model_config": "fusion_stage3",
            "device": "cpu",
            "review_delta": -0.8,
            "minimum_duration_seconds": minimum_duration_seconds,
            "num_repetitions": 3,
            "inference_seed": 123,
        },
        "safety": {"allow_network_downloads_during_job": False},
    }


def _write_wav(path: Path, duration: float = 1.0) -> None:
    sf.write(path, np.zeros(round(16_000 * duration), dtype=np.float32), 16_000)


class FakeModel:
    def __init__(self, scores: dict[str, float]) -> None:
        self.scores = scores
        self.calls: list[tuple[str, dict]] = []

    def predict(self, *, input_path: Path, **kwargs):
        self.calls.append((input_path.name, kwargs))
        return self.scores[input_path.name]


def _configured_verifier(
    tmp_path: Path,
    scores: dict[str, float],
    *,
    duration: float = 1.0,
) -> tuple[UTMOSNaturalnessVerifier, FakeModel, Path]:
    checkpoint = tmp_path / "utmos.pth"
    checkpoint.touch()
    preview_name = VOICE_PREVIEW_FILENAMES[PRESET_NAME]
    _write_wav(tmp_path / preview_name, 2.0)
    generated = tmp_path / "generated.wav"
    _write_wav(generated, duration)
    model = FakeModel(scores)
    verifier = UTMOSNaturalnessVerifier(
        _settings(checkpoint),
        lambda _message: None,
        model_factory=lambda **_kwargs: model,
        preview_root=tmp_path,
    )
    return verifier, model, generated


def test_disabled_perceptual_qa_is_inconclusive_without_importing_model(tmp_path: Path) -> None:
    calls: list[dict] = []
    verifier = UTMOSNaturalnessVerifier(
        _settings(None, enabled=False),
        lambda _message: None,
        model_factory=lambda **kwargs: calls.append(kwargs),
    )

    result = verifier.verify(tmp_path / "missing.wav", PRESET_NAME)

    assert result["verdict"] == PERCEPTUAL_INCONCLUSIVE
    assert result["reason"] == "PERCEPTUAL_QA_DISABLED"
    assert result["review_required"] is False
    assert calls == []


@pytest.mark.parametrize(
    ("generated_score", "expected_verdict", "review_required"),
    [
        (2.21, PERCEPTUAL_OK, False),
        (2.20, PERCEPTUAL_REVIEW, True),
        (1.53, PERCEPTUAL_REVIEW, True),
    ],
)
def test_relative_voice_baseline_sets_review_at_point_eight_drop(
    generated_score: float,
    expected_verdict: str,
    review_required: bool,
    tmp_path: Path,
) -> None:
    preview_name = VOICE_PREVIEW_FILENAMES[PRESET_NAME]
    verifier, _model, generated = _configured_verifier(
        tmp_path,
        {preview_name: 3.0, "generated.wav": generated_score},
    )

    result = verifier.verify(generated, PRESET_NAME)

    assert result["verdict"] == expected_verdict
    assert result["review_required"] is review_required
    assert result["baseline_score"] == pytest.approx(3.0)
    assert result["baseline_delta"] == pytest.approx(generated_score - 3.0)
    assert "passed" not in result


def test_voice_preview_baseline_is_scored_once_and_predict_contract_is_bounded(tmp_path: Path) -> None:
    preview_name = VOICE_PREVIEW_FILENAMES[PRESET_NAME]
    verifier, model, generated = _configured_verifier(
        tmp_path,
        {preview_name: 2.965, "generated.wav": 3.02},
    )

    first = verifier.verify(generated, PRESET_NAME)
    second = verifier.verify(generated, PRESET_NAME)

    assert first["verdict"] == PERCEPTUAL_OK
    assert second["verdict"] == PERCEPTUAL_OK
    assert [name for name, _kwargs in model.calls] == [preview_name, "generated.wav", "generated.wav"]
    for _name, kwargs in model.calls:
        assert kwargs["device"] == "cpu"
        assert kwargs["num_workers"] == 0
        assert kwargs["batch_size"] == 1
        assert kwargs["num_repetitions"] == 3
        assert kwargs["verbose"] is False


def test_pitch_matched_baselines_use_distinct_cache_keys_and_cleanup_temp_wav(
    tmp_path: Path,
    monkeypatch,
) -> None:
    checkpoint = tmp_path / "utmos.pth"
    checkpoint.touch()
    preview_name = VOICE_PREVIEW_FILENAMES[PRESET_NAME]
    preview_path = tmp_path / preview_name
    _write_wav(preview_path, 2.0)
    generated = tmp_path / "generated.wav"
    _write_wav(generated)
    shift_calls: list[tuple[int, int]] = []
    temporary_paths: list[Path] = []

    def shift(audio, sample_rate: int, pitch_semitones: int):
        shift_calls.append((sample_rate, pitch_semitones))
        return np.asarray(audio, dtype=np.float32)

    class PitchAwareModel:
        def predict(self, *, input_path: Path, **_kwargs):
            if input_path == generated:
                return 3.1
            if input_path == preview_path:
                return 3.0
            temporary_paths.append(input_path)
            assert input_path.is_file()
            return 2.8

    monkeypatch.setattr(perceptual_module, "apply_pitch_variant", shift)
    verifier = UTMOSNaturalnessVerifier(
        _settings(checkpoint),
        lambda _message: None,
        model_factory=lambda **_kwargs: PitchAwareModel(),
        preview_root=tmp_path,
    )

    shifted_first = verifier.verify(generated, PRESET_NAME, pitch_semitones=-1)
    shifted_second = verifier.verify(generated, PRESET_NAME, pitch_semitones=-1)
    original = verifier.verify(generated, PRESET_NAME, pitch_semitones=0)

    assert shifted_first["baseline_score"] == pytest.approx(2.8)
    assert shifted_second["baseline_score"] == pytest.approx(2.8)
    assert shifted_first["baseline_pitch_semitones"] == -1
    assert original["baseline_score"] == pytest.approx(3.0)
    assert original["baseline_pitch_semitones"] == 0
    assert shift_calls == [(16_000, -1)]
    assert len(temporary_paths) == 1
    assert temporary_paths[0].exists() is False
    assert verifier._baseline_scores == {
        (PRESET_NAME, -1): pytest.approx(2.8),
        (PRESET_NAME, 0): pytest.approx(3.0),
    }


def test_short_audio_is_policy_exempt_without_loading_or_scoring_model(tmp_path: Path) -> None:
    preview_name = VOICE_PREVIEW_FILENAMES[PRESET_NAME]
    verifier, model, generated = _configured_verifier(
        tmp_path,
        {preview_name: 3.0, "generated.wav": 1.0},
        duration=0.59,
    )

    result = verifier.verify(generated, PRESET_NAME)

    assert result["verdict"] == PERCEPTUAL_INCONCLUSIVE
    assert result["reason"] == "PERCEPTUAL_SHORT_AUDIO"
    assert result["score"] is None
    assert result["baseline_score"] is None
    assert result["baseline_delta"] is None
    assert result["review_required"] is False
    assert model.calls == []


def test_missing_explicit_checkpoint_obeys_failure_policy(tmp_path: Path) -> None:
    generated = tmp_path / "generated.wav"
    _write_wav(generated)
    optional = UTMOSNaturalnessVerifier(
        _settings(tmp_path / "missing.pth", failure_policy="inconclusive"),
        lambda _message: None,
    )
    mandatory = UTMOSNaturalnessVerifier(
        _settings(tmp_path / "missing.pth", failure_policy="fail"),
        lambda _message: None,
    )

    optional_result = optional.verify(generated, PRESET_NAME)

    assert optional_result["verdict"] == PERCEPTUAL_INCONCLUSIVE
    assert optional_result["reason"] == "PERCEPTUAL_CHECKPOINT_MISSING"
    with pytest.raises(PerceptualQAUnavailable) as raised:
        mandatory.load()
    assert raised.value.reason == "PERCEPTUAL_CHECKPOINT_MISSING"


def test_enabled_model_without_configuration_never_implicitly_downloads(tmp_path: Path) -> None:
    generated = tmp_path / "generated.wav"
    _write_wav(generated)
    calls: list[dict] = []
    verifier = UTMOSNaturalnessVerifier(
        _settings(None, failure_policy="inconclusive"),
        lambda _message: None,
        model_factory=lambda **kwargs: calls.append(kwargs),
    )

    result = verifier.verify(generated, PRESET_NAME)

    assert result["reason"] == "PERCEPTUAL_MODEL_NOT_CONFIGURED"
    assert calls == []


def test_model_load_is_offline_and_environment_is_restored(tmp_path: Path, monkeypatch) -> None:
    checkpoint = tmp_path / "model.pth"
    checkpoint.touch()
    observed: dict[str, str | None] = {}
    monkeypatch.setenv("HF_HUB_OFFLINE", "previous")

    def factory(**_kwargs):
        observed["hf"] = os.environ.get("HF_HUB_OFFLINE")
        observed["transformers"] = os.environ.get("TRANSFORMERS_OFFLINE")
        return FakeModel({})

    verifier = UTMOSNaturalnessVerifier(
        _settings(checkpoint),
        lambda _message: None,
        model_factory=factory,
    )

    assert verifier.load() is True
    assert observed == {"hf": "1", "transformers": "1"}
    assert os.environ["HF_HUB_OFFLINE"] == "previous"
    assert "TRANSFORMERS_OFFLINE" not in os.environ


def test_model_load_supplies_noninteractive_streams_for_detached_pythonw(
    tmp_path: Path,
    monkeypatch,
) -> None:
    checkpoint = tmp_path / "model.pth"
    checkpoint.touch()
    observed: dict[str, object] = {}

    def factory(**_kwargs):
        observed["stdout"] = sys.stdout
        observed["stderr"] = sys.stderr
        observed["stdout_isatty"] = sys.stdout.isatty()
        observed["stderr_isatty"] = sys.stderr.isatty()
        return FakeModel({})

    verifier = UTMOSNaturalnessVerifier(
        _settings(checkpoint),
        lambda _message: None,
        model_factory=factory,
    )
    monkeypatch.setattr(sys, "stdout", None)
    monkeypatch.setattr(sys, "stderr", None)

    assert verifier.load() is True
    assert observed["stdout"] is not None
    assert observed["stderr"] is not None
    assert observed["stdout_isatty"] is False
    assert observed["stderr_isatty"] is False
    assert sys.stdout is None
    assert sys.stderr is None


def test_detached_streams_are_restored_when_model_load_fails(
    tmp_path: Path,
    monkeypatch,
) -> None:
    checkpoint = tmp_path / "model.pth"
    checkpoint.touch()

    def factory(**_kwargs):
        assert sys.stdout is not None
        raise RuntimeError("model load failed")

    verifier = UTMOSNaturalnessVerifier(
        _settings(checkpoint, failure_policy="inconclusive"),
        lambda _message: None,
        model_factory=factory,
    )
    monkeypatch.setattr(sys, "stdout", None)
    monkeypatch.setattr(sys, "stderr", None)

    assert verifier.load() is False
    assert sys.stdout is None
    assert sys.stderr is None


def test_model_factory_receives_only_explicit_checkpoint(tmp_path: Path) -> None:
    checkpoint = tmp_path / "model.pth"
    checkpoint.touch()
    calls: list[dict] = []

    def factory(**kwargs):
        calls.append(kwargs)
        return FakeModel({})

    verifier = UTMOSNaturalnessVerifier(
        _settings(checkpoint),
        lambda _message: None,
        model_factory=factory,
    )

    assert verifier.load() is True
    assert calls == [
        {
            "pretrained": True,
            "config": "fusion_stage3",
            "fold": 0,
            "checkpoint_path": checkpoint.resolve(),
            "seed": 42,
            "device": "cpu",
        }
    ]


def test_inference_preserves_cpu_rng_without_touching_accelerator_rng(
    tmp_path: Path,
    monkeypatch,
) -> None:
    import torch

    checkpoint = tmp_path / "model.pth"
    checkpoint.touch()
    preview_name = VOICE_PREVIEW_FILENAMES[PRESET_NAME]
    _write_wav(tmp_path / preview_name, 2.0)
    generated = tmp_path / "generated.wav"
    _write_wav(generated)
    observed: list[float] = []

    class RandomModel:
        def predict(self, **_kwargs):
            score = float(np.random.random())
            observed.append(score)
            return score

    verifier = UTMOSNaturalnessVerifier(
        _settings(checkpoint),
        lambda _message: None,
        model_factory=lambda **_kwargs: RandomModel(),
        preview_root=tmp_path,
    )
    global_seed_calls: list[int] = []
    cuda_seed_calls: list[int] = []
    monkeypatch.setattr(torch, "manual_seed", lambda seed: global_seed_calls.append(int(seed)))
    monkeypatch.setattr(
        torch.cuda,
        "manual_seed_all",
        lambda seed: cuda_seed_calls.append(int(seed)),
    )
    np.random.seed(999)
    expected_next = float(np.random.random())
    np.random.seed(999)
    torch.random.default_generator.manual_seed(999)
    torch_state = torch.random.get_rng_state().clone()

    verifier.verify(generated, PRESET_NAME)
    actual_next = float(np.random.random())

    assert observed[0] == observed[1]
    assert actual_next == expected_next
    assert torch.equal(torch.random.get_rng_state(), torch_state)
    assert global_seed_calls == []
    assert cuda_seed_calls == []


def test_non_finite_score_is_inconclusive_or_fatal_by_policy(tmp_path: Path) -> None:
    preview_name = VOICE_PREVIEW_FILENAMES[PRESET_NAME]
    verifier, _model, generated = _configured_verifier(
        tmp_path,
        {preview_name: 3.0, "generated.wav": float("nan")},
    )

    with pytest.raises(PerceptualQAUnavailable) as raised:
        verifier.verify(generated, PRESET_NAME)

    assert raised.value.reason == "PERCEPTUAL_SCORE_ERROR"


def test_unknown_preset_is_inconclusive_under_optional_policy(tmp_path: Path) -> None:
    checkpoint = tmp_path / "model.pth"
    checkpoint.touch()
    generated = tmp_path / "generated.wav"
    _write_wav(generated)
    verifier = UTMOSNaturalnessVerifier(
        _settings(checkpoint, failure_policy="inconclusive"),
        lambda _message: None,
        model_factory=lambda **_kwargs: FakeModel({}),
        preview_root=tmp_path,
    )

    result = verifier.verify(generated, "Unknown voice")

    assert result["verdict"] == PERCEPTUAL_INCONCLUSIVE
    assert result["reason"] == "PERCEPTUAL_PREVIEW_UNKNOWN"


def test_unload_preserves_voice_baselines_and_trims_working_set(tmp_path: Path, monkeypatch) -> None:
    preview_name = VOICE_PREVIEW_FILENAMES[PRESET_NAME]
    verifier, _model, generated = _configured_verifier(
        tmp_path,
        {preview_name: 3.0, "generated.wav": 3.0},
    )
    trims: list[bool] = []
    monkeypatch.setattr(perceptual_module, "trim_process_working_set", lambda: trims.append(True))
    verifier.verify(generated, PRESET_NAME)

    verifier.unload()

    assert verifier.model is None
    assert verifier._baseline_scores == {(PRESET_NAME, 0): pytest.approx(3.0)}
    assert trims == [True]


# --- parallel scoring ---------------------------------------------------------------


def _pool_settings(**overrides) -> dict:
    settings = {
        "perceptual_qa": {"enabled": True, "device": "cpu", **overrides},
    }
    return settings


def test_a_prefetched_score_reaches_the_same_verdict_as_scoring_here(
    tmp_path: Path,
) -> None:
    """A worker supplies the number and nothing else; every gate still runs in-process.

    This is the whole safety argument for the pool. If a prefetched score could reach a
    different verdict than the same score computed here, the pool would be moving
    judgement out of the pipeline rather than moving arithmetic off its critical path.
    """
    preview_name = VOICE_PREVIEW_FILENAMES[PRESET_NAME]
    scores = {preview_name: 3.0, "generated.wav": 2.5}

    verifier, model, generated = _configured_verifier(tmp_path, scores)
    local = verifier.verify(generated, PRESET_NAME)
    local_predict_calls = [name for name, _kwargs in model.calls]

    verifier, model, generated = _configured_verifier(tmp_path, scores)
    prefetched = verifier.verify(generated, PRESET_NAME, prefetched_score=2.5)

    assert prefetched == local
    assert local_predict_calls == [preview_name, "generated.wav"]
    # The take itself was never scored twice; only the preset baseline was still needed.
    assert [name for name, _kwargs in model.calls] == [preview_name]


def test_a_take_the_pool_skipped_is_scored_by_the_parent(tmp_path: Path) -> None:
    """A worker that fails returns nothing, and the parent takes its normal path.

    Worker trouble must never become a quality signal: scoring it here reproduces exactly
    the verdict the run would have reached with no pool at all.
    """
    preview_name = VOICE_PREVIEW_FILENAMES[PRESET_NAME]
    verifier, model, generated = _configured_verifier(
        tmp_path, {preview_name: 3.0, "generated.wav": 2.5}
    )

    result = verifier.verify(generated, PRESET_NAME, prefetched_score=None)

    assert "generated.wav" in [name for name, _kwargs in model.calls]
    assert result["score"] == pytest.approx(2.5)


def test_a_non_finite_prefetched_score_is_refused(tmp_path: Path) -> None:
    """A number from a worker is checked as strictly as one computed here.

    `_score` rejects a non-finite result. A prefetched score crossed a process boundary to
    get here, so it earns the same suspicion rather than less.
    """
    preview_name = VOICE_PREVIEW_FILENAMES[PRESET_NAME]
    checkpoint = tmp_path / "utmos.pth"
    checkpoint.touch()
    _write_wav(tmp_path / preview_name, 2.0)
    generated = tmp_path / "generated.wav"
    _write_wav(generated, 1.0)
    model = FakeModel({preview_name: 3.0, "generated.wav": 2.5})
    verifier = UTMOSNaturalnessVerifier(
        _settings(checkpoint, failure_policy="inconclusive"),
        lambda _message: None,
        model_factory=lambda **_kwargs: model,
        preview_root=tmp_path,
    )

    result = verifier.verify(generated, PRESET_NAME, prefetched_score=float("nan"))

    assert result["verdict"] == PERCEPTUAL_INCONCLUSIVE
    assert result["reason"] == "PERCEPTUAL_SCORE_ERROR"


@pytest.mark.parametrize(
    ("workers", "jobs", "free_ram_gb", "device", "expected"),
    [
        (8, 24, 32.0, "cpu", True),
        # One worker is the sequential loop with extra machinery attached.
        (1, 24, 32.0, "cpu", False),
        (0, 24, 32.0, "cpu", False),
        # A pool for a single file pays startup for nothing.
        (8, 1, 32.0, "cpu", False),
        # Each worker holds about a gigabyte, so RAM decides before the setting does.
        (8, 24, 2.5, "cpu", False),
        # A GPU pool would multiply VRAM against engines the pipeline still needs.
        (8, 24, 32.0, "cuda", False),
    ],
)
def test_the_pool_declines_itself_when_it_would_not_pay(
    workers: int,
    jobs: int,
    free_ram_gb: float,
    device: str,
    expected: bool,
) -> None:
    pool = PerceptualScorePool(
        _pool_settings(device=device), lambda _message: None, workers=workers
    )
    assert (pool.usable_for(jobs, free_ram_gb) >= 2) is expected


def test_worker_count_never_exceeds_what_the_moment_affords() -> None:
    """The configured number is a ceiling, never a demand.

    A run must be able to shrink when the machine is busy, so the pool sizes itself from
    free RAM at the moment the batch starts rather than from a number fixed at startup.

    The figures moved once the arithmetic underneath became honest. This used to call 6 GB
    the frugal case and expect two workers out of it, which was true only while a worker
    was budgeted at 1.0 GB and the reserve was a hardcoded 2.0. A worker costs 1.75 and the
    reserve is now resources.min_free_ram_gb, so 6 GB affords one - and one is not a pool.
    What the test is actually about is unchanged: more room means more workers, and there
    is always a point where the machine is too busy to be worth the processes.
    """
    pool = PerceptualScorePool(_pool_settings(), lambda _message: None, workers=8)

    generous = pool.usable_for(24, 32.0)
    frugal = pool.usable_for(24, 9.0)

    assert generous > frugal >= 2
    assert pool.usable_for(24, 6.0) < frugal
    assert generous <= 8
    # Never more workers than files, however much RAM is free.
    assert pool.usable_for(3, 64.0) <= 3


def test_a_pool_that_cannot_start_scores_nothing_rather_than_guessing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A broken pool degrades to the sequential path, never to an invented score."""
    messages: list[str] = []
    pool = PerceptualScorePool(_pool_settings(), messages.append, workers=8)

    def _explode(_name: str):
        raise OSError("no process handles left")

    import multiprocessing

    monkeypatch.setattr(multiprocessing, "get_context", _explode)

    scores = pool.score_many([str(tmp_path / f"{i}.wav") for i in range(8)], free_ram_gb=32.0)

    assert scores == {}
    assert messages and "tuần tự" in messages[0]
