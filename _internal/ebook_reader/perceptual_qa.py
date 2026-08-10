from __future__ import annotations

import gc
import math
import os
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Iterator

import numpy as np
import soundfile as sf

from .resource_manager import trim_process_working_set
from .tts import apply_pitch_variant
from .voice_catalog import VOICE_PREVIEW_FILENAMES


PERCEPTUAL_OK = "ok"
PERCEPTUAL_REVIEW = "review"
PERCEPTUAL_INCONCLUSIVE = "inconclusive"
DEFAULT_REVIEW_DELTA = -0.8
DEFAULT_MINIMUM_DURATION_SECONDS = 1.5
DEFAULT_INFERENCE_REPETITIONS = 3
DEFAULT_INFERENCE_SEED = 42


class PerceptualQAUnavailable(RuntimeError):
    """Raised when mandatory perceptual QA cannot produce trustworthy evidence."""

    def __init__(self, reason: str, message: str) -> None:
        super().__init__(message)
        self.reason = reason


@contextmanager
def _temporary_environment(updates: dict[str, str]) -> Iterator[None]:
    previous = {key: os.environ.get(key) for key in updates}
    os.environ.update(updates)
    try:
        yield
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


@contextmanager
def _preserved_inference_rng(seed: int, *, preserve_cuda: bool) -> Iterator[None]:
    numpy_state = np.random.get_state()
    np.random.seed(seed)
    try:
        try:
            import torch
        except Exception:  # pragma: no cover - torch is optional until the backend loads
            yield
        else:
            cuda_devices = (
                list(range(torch.cuda.device_count()))
                if preserve_cuda and torch.cuda.is_available()
                else []
            )
            with torch.random.fork_rng(devices=cuda_devices, enabled=True):
                torch.random.default_generator.manual_seed(seed)
                if cuda_devices:
                    torch.cuda.manual_seed_all(seed)
                yield
    finally:
        np.random.set_state(numpy_state)


def _create_utmosv2_model(**kwargs: Any) -> Any:
    from utmosv2 import create_model

    return create_model(**kwargs)


@contextmanager
def _pitch_matched_preview(preview_path: Path, pitch_semitones: int) -> Iterator[Path]:
    pitch_steps = int(pitch_semitones)
    if pitch_steps == 0:
        yield preview_path
        return

    temporary = tempfile.NamedTemporaryFile(
        prefix="ebook_reader_pitch_preview_",
        suffix=".wav",
        delete=False,
    )
    temporary_path = Path(temporary.name)
    temporary.close()
    try:
        audio, sample_rate = sf.read(preview_path, dtype="float32", always_2d=False)
        shifted = apply_pitch_variant(audio, int(sample_rate), pitch_steps)
        sf.write(temporary_path, shifted, int(sample_rate), subtype="PCM_16")
        yield temporary_path
    finally:
        temporary_path.unlink(missing_ok=True)


class UTMOSNaturalnessVerifier:
    """Relative, per-voice naturalness evidence backed by UTMOSv2.

    The verifier deliberately does not expose a ``passed`` result. A score close to a
    preset preview is useful corroborating evidence, but it cannot establish content,
    prosody, or speaker correctness. Only a large drop from that preset's own preview
    requests review.
    """

    def __init__(
        self,
        settings: dict[str, Any],
        log: Callable[[str], None],
        *,
        model_factory: Callable[..., Any] | None = None,
        preview_root: Path | None = None,
    ) -> None:
        self.settings = dict(settings.get("perceptual_qa", {}))
        self.enabled = bool(self.settings.get("enabled", False))
        self.failure_policy = str(self.settings.get("failure_policy", "inconclusive"))
        if self.failure_policy not in {"fail", "inconclusive"}:
            raise ValueError("Unsupported perceptual_qa.failure_policy")
        self.review_delta = float(self.settings.get("review_delta", DEFAULT_REVIEW_DELTA))
        if not math.isfinite(self.review_delta) or self.review_delta > 0.0:
            raise ValueError("perceptual_qa.review_delta must be finite and non-positive")
        self.minimum_duration_seconds = float(
            self.settings.get("minimum_duration_seconds", DEFAULT_MINIMUM_DURATION_SECONDS)
        )
        if not math.isfinite(self.minimum_duration_seconds) or self.minimum_duration_seconds <= 0.0:
            raise ValueError("perceptual_qa.minimum_duration_seconds must be positive")
        self.num_repetitions = int(
            self.settings.get("num_repetitions", DEFAULT_INFERENCE_REPETITIONS)
        )
        if self.num_repetitions < 1:
            raise ValueError("perceptual_qa.num_repetitions must be positive")
        self.inference_seed = int(self.settings.get("inference_seed", DEFAULT_INFERENCE_SEED))
        self.device = str(self.settings.get("device", "cuda"))
        self.predict_dataset = str(self.settings.get("predict_dataset", "sarulab"))
        self.remove_silent_section = bool(self.settings.get("remove_silent_section", True))
        self.allow_downloads = bool(
            settings.get("safety", {}).get("allow_network_downloads_during_job", False)
        )
        self.log = log
        self.model_factory = model_factory or _create_utmosv2_model
        self.preview_root = preview_root or Path(__file__).resolve().parent / "assets" / "voice_previews"
        self.model: Any | None = None
        self._baseline_scores: dict[tuple[str, int], float] = {}
        self._unavailable_reason = "PERCEPTUAL_MODEL_NOT_LOADED"
        self._unavailable_message = "UTMOSv2 has not been loaded"
        self._unavailable_latched = False

    def _unavailable(
        self,
        reason: str,
        message: str,
        *,
        cause: Exception | None = None,
        latch: bool = False,
    ) -> bool:
        self._unavailable_reason = reason
        self._unavailable_message = message
        self._unavailable_latched = self._unavailable_latched or latch
        self.log(message)
        if self.failure_policy == "fail":
            error = PerceptualQAUnavailable(reason, message)
            if cause is not None:
                raise error from cause
            raise error
        return False

    def load(self) -> bool:
        if not self.enabled:
            self._unavailable_reason = "PERCEPTUAL_QA_DISABLED"
            self._unavailable_message = "Perceptual QA is disabled"
            return False
        if self.model is not None:
            return True
        if self._unavailable_latched:
            if self.failure_policy == "fail":
                raise PerceptualQAUnavailable(
                    self._unavailable_reason,
                    self._unavailable_message,
                )
            return False
        checkpoint_value = str(self.settings.get("checkpoint_path", "")).strip()
        if not checkpoint_value:
            return self._unavailable(
                "PERCEPTUAL_MODEL_NOT_CONFIGURED",
                "UTMOSv2 is enabled but no explicit checkpoint_path is configured",
                latch=True,
            )
        checkpoint_path = Path(checkpoint_value).expanduser().resolve()
        if not checkpoint_path.is_file():
            return self._unavailable(
                "PERCEPTUAL_CHECKPOINT_MISSING",
                f"UTMOSv2 checkpoint is unavailable: {checkpoint_path}",
                latch=True,
            )
        offline_environment = (
            {}
            if self.allow_downloads
            else {
                "HF_HUB_OFFLINE": "1",
                "TRANSFORMERS_OFFLINE": "1",
                "HF_HUB_DISABLE_TELEMETRY": "1",
            }
        )
        try:
            with _temporary_environment(offline_environment):
                self.model = self.model_factory(
                    pretrained=True,
                    config=str(self.settings.get("model_config", "fusion_stage3")),
                    fold=int(self.settings.get("fold", 0)),
                    checkpoint_path=checkpoint_path,
                    seed=int(self.settings.get("model_seed", 42)),
                    device=self.device,
                )
        except Exception as exc:  # noqa: BLE001
            self.model = None
            return self._unavailable(
                "PERCEPTUAL_MODEL_LOAD_ERROR",
                f"Cannot load the configured UTMOSv2 model/cache: {exc}",
                cause=exc,
                latch=True,
            )
        self._unavailable_reason = ""
        self._unavailable_message = ""
        return True

    def reset_unavailable(self) -> None:
        """Allow an explicit retry after external cache/model repair."""
        self._unavailable_latched = False
        self._unavailable_reason = "PERCEPTUAL_MODEL_NOT_LOADED"
        self._unavailable_message = "UTMOSv2 has not been loaded"

    def unload(self) -> None:
        had_model = self.model is not None
        self.model = None
        if not had_model:
            return
        gc.collect()
        try:
            import torch

            if self.device.startswith("cuda") and torch.cuda.is_available():
                torch.cuda.empty_cache()
        except Exception:
            pass
        trim_process_working_set()

    def _score(self, wav_path: Path) -> float:
        if self.model is None:
            raise RuntimeError("UTMOSv2 is not loaded")
        with _preserved_inference_rng(
            self.inference_seed,
            preserve_cuda=self.device.startswith("cuda"),
        ):
            raw_score = self.model.predict(
                input_path=wav_path,
                predict_dataset=self.predict_dataset,
                device=self.device,
                num_workers=0,
                batch_size=1,
                num_repetitions=self.num_repetitions,
                remove_silent_section=self.remove_silent_section,
                verbose=False,
            )
        score = float(raw_score)
        if not math.isfinite(score):
            raise ValueError(f"UTMOSv2 returned a non-finite score for {wav_path.name}")
        return score

    def baseline_for_preset(
        self,
        preset_name: str,
        pitch_semitones: int = 0,
    ) -> float | None:
        pitch_steps = int(pitch_semitones)
        baseline_key = (preset_name, pitch_steps)
        if baseline_key in self._baseline_scores:
            return self._baseline_scores[baseline_key]
        preview_filename = VOICE_PREVIEW_FILENAMES.get(preset_name)
        if preview_filename is None:
            self._unavailable(
                "PERCEPTUAL_PREVIEW_UNKNOWN",
                f"No locked voice preview is registered for preset {preset_name!r}",
                latch=True,
            )
            return None
        preview_path = self.preview_root / preview_filename
        if not preview_path.is_file():
            self._unavailable(
                "PERCEPTUAL_PREVIEW_MISSING",
                f"Locked voice preview is unavailable: {preview_path}",
                latch=True,
            )
            return None
        try:
            with _pitch_matched_preview(preview_path, pitch_steps) as matched_preview:
                score = self._score(matched_preview)
        except Exception as exc:  # noqa: BLE001
            self._unavailable(
                "PERCEPTUAL_BASELINE_ERROR",
                (
                    f"Cannot score locked preview {preview_filename} at "
                    f"{pitch_steps:+d} semitones: {exc}"
                ),
                cause=exc,
                latch=True,
            )
            return None
        self._baseline_scores[baseline_key] = score
        return score

    def _inconclusive_result(
        self,
        reason: str,
        *,
        duration_seconds: float | None = None,
        score: float | None = None,
        baseline_score: float | None = None,
        baseline_delta: float | None = None,
        baseline_pitch_semitones: int = 0,
    ) -> dict[str, Any]:
        return {
            "verdict": PERCEPTUAL_INCONCLUSIVE,
            "reason": reason,
            "score": score,
            "baseline_score": baseline_score,
            "baseline_delta": baseline_delta,
            "baseline_pitch_semitones": int(baseline_pitch_semitones),
            "review_required": False,
            "duration_seconds": duration_seconds,
        }

    def verify(
        self,
        wav_path: Path,
        preset_name: str,
        *,
        pitch_semitones: int = 0,
    ) -> dict[str, Any]:
        pitch_steps = int(pitch_semitones)
        if not self.enabled:
            return self._inconclusive_result(
                "PERCEPTUAL_QA_DISABLED",
                baseline_pitch_semitones=pitch_steps,
            )
        try:
            duration_seconds = float(sf.info(wav_path).duration)
        except (OSError, RuntimeError, TypeError, ValueError) as exc:
            if self._unavailable(
                "PERCEPTUAL_AUDIO_INVALID",
                f"Cannot inspect audio for perceptual QA ({wav_path.name}): {exc}",
                cause=exc,
            ):
                raise AssertionError("unreachable")
            return self._inconclusive_result(
                "PERCEPTUAL_AUDIO_INVALID",
                baseline_pitch_semitones=pitch_steps,
            )

        if duration_seconds < self.minimum_duration_seconds:
            return self._inconclusive_result(
                "PERCEPTUAL_SHORT_AUDIO",
                duration_seconds=duration_seconds,
                baseline_pitch_semitones=pitch_steps,
            )
        if not self.load():
            return self._inconclusive_result(
                self._unavailable_reason,
                duration_seconds=duration_seconds,
                baseline_pitch_semitones=pitch_steps,
            )

        baseline_score = self.baseline_for_preset(preset_name, pitch_steps)
        if baseline_score is None:
            return self._inconclusive_result(
                self._unavailable_reason,
                duration_seconds=duration_seconds,
                baseline_pitch_semitones=pitch_steps,
            )
        try:
            score = self._score(wav_path)
        except Exception as exc:  # noqa: BLE001
            if self._unavailable(
                "PERCEPTUAL_SCORE_ERROR",
                f"Cannot score {wav_path.name} with UTMOSv2: {exc}",
                cause=exc,
            ):
                raise AssertionError("unreachable")
            return self._inconclusive_result(
                "PERCEPTUAL_SCORE_ERROR",
                duration_seconds=duration_seconds,
                baseline_score=baseline_score,
                baseline_pitch_semitones=pitch_steps,
            )
        baseline_delta = score - baseline_score
        review_required = baseline_delta < self.review_delta or math.isclose(
            baseline_delta,
            self.review_delta,
            rel_tol=0.0,
            abs_tol=1e-9,
        )
        return {
            "verdict": PERCEPTUAL_REVIEW if review_required else PERCEPTUAL_OK,
            "reason": (
                "PERCEPTUAL_BASELINE_DROP"
                if review_required
                else "PERCEPTUAL_WITHIN_VOICE_BASELINE"
            ),
            "score": score,
            "baseline_score": baseline_score,
            "baseline_delta": baseline_delta,
            "baseline_pitch_semitones": pitch_steps,
            "review_required": review_required,
            "duration_seconds": duration_seconds,
        }
