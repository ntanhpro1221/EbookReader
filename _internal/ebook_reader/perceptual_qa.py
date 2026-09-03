from __future__ import annotations

import gc
import math
import os
import sys
import tempfile
from contextlib import ExitStack, contextmanager
from pathlib import Path
from typing import Any, Callable, Iterator

import numpy as np
import soundfile as sf

from .io_utils import sha256_file
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
# Measured resident size of one scoring worker, used to keep a pool from crowding RAM.
PERCEPTUAL_WORKER_RAM_GB = 1.0
# Torch takes one thread per core by default, so N workers ask for N x cores threads and
# spend the difference context switching. Measured on 32 cores over 24 segments: unpinned,
# 4 workers reached 1.66x and 8 fell back to 1.34x; pinned to 2 threads, 8 workers reached
# 3.68x. The pool size only means anything once each member is bounded.
DEFAULT_PERCEPTUAL_WORKER_THREADS = 2


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
def _headless_dependency_streams() -> Iterator[None]:
    """Give libraries non-interactive output streams while running under pythonw."""
    previous_stdout = sys.stdout
    previous_stderr = sys.stderr
    if previous_stdout is not None and previous_stderr is not None:
        yield
        return

    with ExitStack() as stack:
        stdout = previous_stdout
        stderr = previous_stderr
        if stdout is None:
            stdout = stack.enter_context(tempfile.TemporaryFile(mode="w", encoding="utf-8"))
        if stderr is None:
            stderr = stack.enter_context(tempfile.TemporaryFile(mode="w", encoding="utf-8"))
        sys.stdout = stdout
        sys.stderr = stderr
        try:
            yield
        finally:
            sys.stdout = previous_stdout
            sys.stderr = previous_stderr


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
        self.worker_threads = int(
            self.settings.get("worker_threads", DEFAULT_PERCEPTUAL_WORKER_THREADS)
        )
        if self.worker_threads < 1:
            raise ValueError("perceptual_qa.worker_threads must be positive")
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

    def _pin_threads(self) -> None:
        """Score at a fixed thread count, wherever the scoring happens.

        Torch splits a matmul across its threads and sums the pieces in whatever order
        they finish, so the same WAV scores differently at 1, 2 and 16 threads - measured
        here at around 5e-07. That was already true before any pool existed: the score
        quietly depended on how many cores the machine had. It only becomes a correctness
        problem once a take is scored in a worker while its preset baseline is scored in
        the parent, because the verdict is their difference and the two would then come
        from different arithmetic. Pinning both to one number removes the mismatch by
        construction rather than by tolerance.
        """
        if not self.device.startswith("cpu"):
            return
        try:
            import torch

            torch.set_num_threads(self.worker_threads)
        except Exception:  # noqa: BLE001
            # A torch that will not take a thread count still scores; it just scores at
            # whatever default it chose, which is exactly the old behaviour.
            return

    def load(self) -> bool:
        if not self.enabled:
            self._unavailable_reason = "PERCEPTUAL_QA_DISABLED"
            self._unavailable_message = "Perceptual QA is disabled"
            return False
        if self.model is not None:
            return True
        self._pin_threads()
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
            with _temporary_environment(offline_environment), _headless_dependency_streams():
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
        prefetched_score: float | None = None,
    ) -> dict[str, Any]:
        """Judge one take. `prefetched_score` is this file's UTMOSv2 score if a worker
        already computed it - the number only, never a verdict. Every gate below still
        runs here: a prefetched score changes who did the arithmetic, not what it means.
        """
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
            score = (
                self._score(wav_path)
                if prefetched_score is None
                else float(prefetched_score)
            )
            if not math.isfinite(score):
                raise ValueError(f"UTMOSv2 score is not finite for {wav_path.name}")
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


# --- parallel scoring ---------------------------------------------------------------
#
# Scoring a WAV is the whole cost of perceptual QA and it is a pure read: it takes a file
# and returns a number, touching no database row, no artifact and no pipeline state. That
# makes it the one stage that can be spread across the idle cores without renegotiating
# any invariant - every threshold, baseline and verdict stays in the parent, exactly where
# it is today, and only the number arrives from somewhere else.
#
# Processes, not threads. `_preserved_inference_rng` seeds process-global RNGs, so threads
# inside one process would make a segment's score depend on which segments happened to be
# scored beside it. Separate processes each own their RNG, which is why the measured
# scores are identical at every pool size.

_WORKER: dict[str, Any] = {}


def _score_worker_init(settings: dict[str, Any], threads: int) -> None:
    # The thread count travels inside the settings so a worker and the parent pin the
    # same number through the same code path; passing it separately invited them to drift.
    worker_settings = dict(settings)
    worker_settings["perceptual_qa"] = {
        **worker_settings.get("perceptual_qa", {}),
        "worker_threads": max(1, int(threads)),
    }
    verifier = UTMOSNaturalnessVerifier(worker_settings, lambda _message: None)
    if not verifier.load():
        raise RuntimeError("UTMOSv2 is unavailable in a scoring worker")
    _WORKER["verifier"] = verifier


def _score_worker_job(wav_path: str) -> tuple[str, float | None]:
    """Score one file and say which audio the score belongs to.

    A worker never decides anything. Returning None for a file it could not score leaves
    the parent to call its own scorer, which raises and classifies the failure through the
    same path it would have taken had no pool existed.

    The checksum is taken **after** scoring and is what the score is filed under, because
    a path is not an identity: ASR repair re-cuts a segment and writes a new take to the
    same path. A score filed under the path would then be read back for audio it never
    heard. WAVs are written to a .part file and renamed, so the reader sees one whole take
    or the other, never a torn one - and whichever it saw, the checksum names it.
    """
    verifier = _WORKER.get("verifier")
    if verifier is None:
        return wav_path, None
    try:
        score = float(verifier._score(Path(wav_path)))
        return sha256_file(Path(wav_path)), score
    except Exception:  # noqa: BLE001
        return wav_path, None


class PerceptualScorePool:
    """Score many WAVs across processes, falling back to nothing at all on any trouble."""

    def __init__(
        self,
        settings: dict[str, Any],
        log: Callable[[str], None],
        *,
        workers: int,
        threads: int = DEFAULT_PERCEPTUAL_WORKER_THREADS,
    ) -> None:
        self.settings = settings
        self.log = log
        self.workers = max(0, int(workers))
        self.threads = max(1, int(threads))

    def usable_for(
        self,
        job_count: int,
        free_ram_gb: float,
        *,
        reserve_ram_gb: float = 0.0,
    ) -> int:
        """How many workers this batch may actually have, or 0 to score in the parent.

        ``reserve_ram_gb`` is what a stage running alongside this pool has not allocated
        yet. Scoring beside ASR is measured from a snapshot taken while Whisper is still
        unloaded, so the free RAM it reports is RAM this pool would otherwise take from
        the model about to want it.
        """
        if self.workers < 2 or job_count < 2:
            return 0
        if str(self.settings.get("perceptual_qa", {}).get("device", "cpu")) != "cpu":
            # A GPU pool would multiply VRAM against the engines the pipeline still needs.
            return 0
        spare = free_ram_gb - 2.0 - max(0.0, float(reserve_ram_gb))
        affordable = int(max(0.0, spare) / PERCEPTUAL_WORKER_RAM_GB)
        return max(0, min(self.workers, job_count, affordable, (os.cpu_count() or 1) // 2))

    def score_many(
        self,
        wav_paths: list[str],
        *,
        free_ram_gb: float,
        reserve_ram_gb: float = 0.0,
    ) -> dict[str, float]:
        """Scores that succeeded, keyed by the checksum of the audio each one heard.

        Anything missing is the parent's to compute. A caller looks a score up by the
        checksum its row carries now, so a take replaced since scoring simply is not
        found - the staleness check is the key itself rather than a comparison somebody
        has to remember to write.
        """
        workers = self.usable_for(
            len(wav_paths), free_ram_gb, reserve_ram_gb=reserve_ram_gb
        )
        if workers < 2:
            return {}
        import multiprocessing as mp

        scores: dict[str, float] = {}
        try:
            context = mp.get_context("spawn")
            with context.Pool(
                processes=workers,
                initializer=_score_worker_init,
                initargs=(self.settings, self.threads),
            ) as pool:
                for checksum, score in pool.imap_unordered(_score_worker_job, wav_paths):
                    if score is not None:
                        scores[checksum] = float(score)
        except Exception as exc:  # noqa: BLE001
            # A pool that cannot start is a throughput problem, never a quality one: the
            # parent scores everything itself and the run is exactly what it always was.
            self.log(f"Không dựng được pool chấm perceptual ({exc}); chấm tuần tự.")
            return {}
        return scores
