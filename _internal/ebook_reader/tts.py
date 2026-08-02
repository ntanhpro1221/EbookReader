from __future__ import annotations

import gc
import random
import re
from pathlib import Path
from typing import Any, Callable

import numpy as np
import pyworld

from .audio_io import (
    AudioQualityError,
    atomic_write_wav,
    is_short_utterance,
    segment_duration_policy,
    vieneu_generation_reached_frame_ceiling,
)
from .database import ProjectDB
from .io_utils import stable_int
from .models import CONTEXTUAL_ENGLISH_NAME_PRONUNCIATION_SOURCE
from .text_processing import normalize_vocalizations_for_tts


FATAL_TTS_MARKERS = (
    "cuda driver",
    "cublas",
    "cudnn",
    "no module named",
    "out of memory",
    "not enough memory",
    "defaultcpuallocator",
    "alloc_cpu.cpp",
    "thiếu vieneu",
    "locked vieneu preset",
    "only vieneu profiles",
)

EMOTION_TEMPERATURE = {
    "neutral": 0.74,
    "happy": 0.84,
    "sad": 0.70,
    "angry": 0.86,
    "afraid": 0.84,
    "surprised": 0.86,
    "tender": 0.70,
    "sarcastic": 0.80,
    "excited": 0.88,
    "tired": 0.68,
    "whispering": 0.66,
}
PACE_TEMPERATURE_OFFSETS = {"slow": -0.03, "normal": 0.0, "fast": 0.04}
PACE_SILENCE_PROPORTIONS = {"slow": 0.20, "normal": 0.15, "fast": 0.08}
WORLD_FRAME_PERIOD_MS = 5.0
WORLD_F0_FLOOR_HZ = 55.0
WORLD_F0_CEIL_HZ = 600.0
WORLD_MIN_VOICED_FRAMES = 3
SHORT_UTTERANCE_MAX_TEMPERATURE = 0.72
SHORT_UTTERANCE_MAX_TOP_P = 0.90


def is_fatal_tts_error(error: BaseException) -> bool:
    message = str(error).casefold()
    return any(marker in message for marker in FATAL_TTS_MARKERS)


def _set_generation_seed(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed % (2**32))
    try:
        import torch

        torch.manual_seed(seed)
        if torch.cuda.is_available():
            torch.cuda.manual_seed_all(seed)
    except ImportError:
        pass


def _row_value(row: Any, key: str, default: Any) -> Any:
    try:
        value = row[key]
    except (IndexError, KeyError, TypeError):
        return default
    return default if value is None else value


def apply_pitch_variant(audio: Any, sample_rate: int, pitch_semitones: int) -> np.ndarray:
    array = np.asarray(audio, dtype=np.float32).reshape(-1)
    steps = int(pitch_semitones)
    if steps == 0 or array.size == 0:
        return array
    if sample_rate < 8_000:
        raise ValueError(f"WORLD pitch shifting requires at least 8000 Hz, got {sample_rate}")
    waveform = np.asarray(array, dtype=np.float64)
    f0, time_axis = pyworld.harvest(
        waveform,
        sample_rate,
        f0_floor=WORLD_F0_FLOOR_HZ,
        f0_ceil=WORLD_F0_CEIL_HZ,
        frame_period=WORLD_FRAME_PERIOD_MS,
    )
    f0 = pyworld.stonemask(waveform, f0, time_axis, sample_rate)
    voiced = f0 > 0.0
    if int(np.count_nonzero(voiced)) < WORLD_MIN_VOICED_FRAMES:
        raise ValueError("WORLD could not find enough voiced frames for formant-preserving pitch shift")
    spectral_envelope = pyworld.cheaptrick(waveform, f0, time_axis, sample_rate)
    aperiodicity = pyworld.d4c(waveform, f0, time_axis, sample_rate)
    shifted_f0 = f0.copy()
    shifted_f0[voiced] *= 2.0 ** (float(steps) / 12.0)
    shifted = pyworld.synthesize(
        shifted_f0,
        spectral_envelope,
        aperiodicity,
        sample_rate,
        frame_period=WORLD_FRAME_PERIOD_MS,
    ).astype(np.float32, copy=False)
    if shifted.size >= array.size:
        return shifted[: array.size]
    return np.pad(shifted, (0, array.size - shifted.size)).astype(np.float32, copy=False)


def _max_new_frames(row: Any, settings: dict[str, Any] | None) -> int:
    return segment_duration_policy(
        str(_row_value(row, "text", "")),
        settings,
        row,
    ).generation_max_frames


def vieneu_sampling_for_segment(
    row: Any,
    settings: dict[str, Any] | None = None,
) -> dict[str, float | int]:
    emotion = str(_row_value(row, "emotion", "neutral"))
    pace = str(_row_value(row, "pace", "normal"))
    intensity = max(0, min(3, int(_row_value(row, "intensity", 0))))
    base_temperature = EMOTION_TEMPERATURE.get(emotion, EMOTION_TEMPERATURE["neutral"])
    temperature = min(
        0.92,
        base_temperature + PACE_TEMPERATURE_OFFSETS.get(pace, 0.0) + 0.015 * intensity,
    )
    top_p = min(0.98, 0.92 + 0.015 * intensity)
    if is_short_utterance(str(_row_value(row, "text", ""))):
        temperature = min(temperature, SHORT_UTTERANCE_MAX_TEMPERATURE)
        top_p = min(top_p, SHORT_UTTERANCE_MAX_TOP_P)
    return {
        "temperature": temperature,
        "top_k": 25,
        "top_p": top_p,
        "repetition_penalty": 1.2,
        "silence_p": PACE_SILENCE_PROPORTIONS.get(pace, PACE_SILENCE_PROPORTIONS["normal"]),
        "max_new_frames": _max_new_frames(row, settings),
    }


class VieNeuEngine:
    def __init__(self, settings: dict[str, Any], log: Callable[[str], None]) -> None:
        self.settings = settings
        self.log = log
        self.tts = None
        self.sample_rate = int(settings["tts"]["sample_rate"])
        self.voices: list[str] = []

    def load(self) -> None:
        if self.tts is not None:
            return
        try:
            from vieneu import Vieneu
        except ImportError as exc:
            raise RuntimeError("Thiếu VieNeu; hãy chạy Ebook Reader") from exc
        self.log("Nạp VieNeu-TTS.")
        self.tts = Vieneu(max_batch_size=max(1, int(self.settings["tts"]["batch_size"])))
        raw = list(self.tts.list_preset_voices())
        self.voices = []
        for item in raw:
            if isinstance(item, (tuple, list)) and item:
                voice_id = str((item[1] if len(item) > 1 else item[0]) or item[0]).strip()
            else:
                voice_id = str(item).strip()
            if voice_id and voice_id not in self.voices:
                self.voices.append(voice_id)
        if not self.voices:
            raise RuntimeError("VieNeu không cung cấp preset voice nào")
        self.sample_rate = int(getattr(self.tts, "sample_rate", self.sample_rate))

    def unload(self) -> None:
        self.tts = None
        self.voices = []
        self.release_inference_cache()

    @staticmethod
    def release_inference_cache() -> None:
        """Release temporary Python/CUDA allocations after a completed inference unit."""
        gc.collect()
        try:
            import torch

            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except Exception:
            pass

    def voice_for_profile(self, profile: Any) -> str:
        self.load()
        if str(profile["engine"]) != "vieneu":
            raise AudioQualityError(
                f"Only VieNeu profiles are supported; found {profile['engine']!r} for {profile['voice_key']}"
            )
        preset = str(profile["preset_name"] or "").strip()
        if not preset or preset not in self.voices:
            raise AudioQualityError(
                f"Locked VieNeu preset {preset!r} is unavailable; refusing to change voice silently"
            )
        return preset

    def generate_one(self, row: Any, profile: Any, seed: int) -> np.ndarray:
        self.load()
        _set_generation_seed(seed)
        voice = self.voice_for_profile(profile)
        style = "doc_truyen" if str(row["speaker"]) == "NARRATOR" else "tu_nhien"
        try:
            return np.asarray(
                self.tts.infer(
                    str(row["text"]),
                    voice=voice,
                    style=style,
                    **vieneu_sampling_for_segment(row, self.settings),
                ),
                dtype=np.float32,
            ).reshape(-1)
        except Exception as exc:  # noqa: BLE001
            raise AudioQualityError(str(exc)) from exc


class TTSCoordinator:
    def __init__(self, settings: dict[str, Any], db: ProjectDB, log: Callable[[str], None]) -> None:
        self.settings = settings
        self.db = db
        self.log = log
        self.vieneu = VieNeuEngine(settings, log)
        self._pronunciation_pattern: re.Pattern[str] | None = None
        self._pronunciation_map: dict[str, str] = {}
        self._exact_pronunciation_pattern: re.Pattern[str] | None = None
        self._exact_pronunciation_map: dict[str, str] = {}

    def unload_all(self) -> None:
        self.vieneu.unload()

    def release_inference_cache(self) -> None:
        self.vieneu.release_inference_cache()

    def unload_idle_models(self, keep_engine: str | None = None) -> None:
        if keep_engine != "vieneu":
            self.vieneu.unload()

    def generation_seed(self, row: Any, seed_salt: str = "") -> int:
        profile = self._voice_profile_for_row(row)
        return stable_int(f"segment::{row['stable_id']}::{profile['voice_key']}::{seed_salt}")

    def _voice_profile_for_row(self, row: Any) -> Any:
        if str(_row_value(row, "kind", "narration")) == "thought":
            return self.db.voice_profile_by_key("narrator")
        return self.db.voice_profile(int(row["voice_profile_id"]))

    def spoken_text(self, row: Any) -> str:
        if self._pronunciation_pattern is None:
            minimum = float(self.settings["analysis"].get("low_confidence_threshold", 0.58))
            pronunciations = self.db.list_pronunciations(minimum)
            exact_pronunciations = [
                item
                for item in pronunciations
                if str(item["source"]) == CONTEXTUAL_ENGLISH_NAME_PRONUNCIATION_SOURCE
            ]
            pronunciations = [
                item
                for item in pronunciations
                if str(item["source"]) != CONTEXTUAL_ENGLISH_NAME_PRONUNCIATION_SOURCE
            ]
            self._pronunciation_map = {
                " ".join(str(item["surface"]).casefold().split()): str(item["spoken_form"])
                for item in pronunciations
            }
            surfaces = [str(item["surface"]) for item in pronunciations]
            self._pronunciation_pattern = (
                re.compile(
                    r"(?<!\w)(?:" + "|".join(re.escape(value) for value in surfaces) + r")(?!\w)",
                    re.IGNORECASE,
                )
                if surfaces
                else re.compile(r"(?!x)x")
            )
            self._exact_pronunciation_map = {
                str(item["surface"]): str(item["spoken_form"])
                for item in exact_pronunciations
            }
            exact_surfaces = [str(item["surface"]) for item in exact_pronunciations]
            self._exact_pronunciation_pattern = (
                re.compile(r"(?<!\w)(?:" + "|".join(re.escape(value) for value in exact_surfaces) + r")(?!\w)")
                if exact_surfaces
                else re.compile(r"(?!x)x")
            )

        def replace(match: re.Match[str]) -> str:
            key = " ".join(match.group(0).casefold().split())
            return self._pronunciation_map.get(key, match.group(0))

        def replace_exact(match: re.Match[str]) -> str:
            return self._exact_pronunciation_map.get(match.group(0), match.group(0))

        text = self._exact_pronunciation_pattern.sub(replace_exact, str(row["text"]))
        text = self._pronunciation_pattern.sub(replace, text)
        return normalize_vocalizations_for_tts(text)

    def _spoken_row(self, row: Any) -> dict[str, Any]:
        result = dict(row)
        result["text"] = self.spoken_text(row)
        if str(_row_value(row, "kind", "narration")) == "thought":
            narrator_profile = self.db.voice_profile_by_key("narrator")
            result["speaker"] = "NARRATOR"
            result["voice_profile_id"] = int(narrator_profile["id"])
        return result

    def prepare_voice_presets(self) -> None:
        self.vieneu.load()
        profiles = self.db.list_voice_profiles()
        for profile in profiles:
            self.vieneu.voice_for_profile(profile)
        self.log(f"Đã xác minh {len(profiles)} voice profile VieNeu đã khóa.")

    def synthesize_atomic(
        self,
        row: Any,
        output: Path,
        seed_salt: str = "",
    ) -> tuple[str, dict[str, float], int]:
        try:
            profile = self._voice_profile_for_row(row)
            seed = self.generation_seed(row, seed_salt)
            spoken_row = self._spoken_row(row)
            audio = self.vieneu.generate_one(spoken_row, profile, seed)
            duration_policy = segment_duration_policy(
                str(spoken_row["text"]),
                self.settings,
                spoken_row,
            )
            if (
                is_short_utterance(str(spoken_row["text"]))
                and vieneu_generation_reached_frame_ceiling(audio, duration_policy)
            ):
                raise AudioQualityError(
                    "VieNeu reached max_new_frames without an early EOS; "
                    "refusing audio that may continue beyond the supplied text"
                )
            pitch_steps = int(_row_value(profile, "pitch_semitones", 0))
            pitch_variant_skipped = False
            try:
                audio = apply_pitch_variant(
                    audio,
                    self.vieneu.sample_rate,
                    pitch_steps,
                )
            except Exception as exc:  # noqa: BLE001
                # Pitch is optional voice diversification. The original waveform still contains
                # every spoken word, so preserve it instead of failing or retrying the whole TTS.
                pitch_variant_skipped = True
                self.log(
                    f"Bỏ biến thể cao độ {pitch_steps:+d} cho segment {row['stable_id']} "
                    f"vì xử lý pitch lỗi: {exc}"
                )
            checksum, metrics = atomic_write_wav(
                output,
                audio,
                self.vieneu.sample_rate,
                str(spoken_row["text"]),
                self.settings,
                segment=spoken_row,
            )
            if pitch_variant_skipped:
                metrics["pitch_variant_skipped"] = 1.0
            return checksum, metrics, seed
        finally:
            # VieNeu's PyTorch backend may retain allocator cache after returning a NumPy waveform.
            # The WAV is already committed (or the attempt has failed), so this is a safe boundary.
            self.release_inference_cache()
