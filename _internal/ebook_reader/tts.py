from __future__ import annotations

import gc
import math
import random
import re
from pathlib import Path
from typing import Any, Callable

import numpy as np

from .audio_io import AudioQualityError, atomic_write_wav
from .database import ProjectDB
from .io_utils import stable_int
from .text_processing import SPECIAL_AUDIO_KINDS, VOCAL_EFFECT_KIND, vocal_effect_tag


FATAL_TTS_MARKERS = (
    "cuda driver",
    "cublas",
    "cudnn",
    "no module named",
    "out of memory",
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
VIENEU_FRAMES_PER_SECOND = 17.1
MIN_GENERATION_FRAMES = 48
MAX_GENERATION_FRAMES = 300
GENERATION_PADDING_SECONDS = 2.0
DEFAULT_EFFECT_MAX_SECONDS = 4.5
DEFAULT_PACE_LOWER_BOUNDS = {"slow": 6.0, "normal": 10.5, "fast": 12.0}


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
    import torch
    from torchaudio.functional import pitch_shift

    waveform = torch.from_numpy(array.copy()).unsqueeze(0)
    with torch.inference_mode():
        shifted = pitch_shift(waveform, sample_rate, n_steps=steps)
    return shifted.squeeze(0).cpu().numpy().astype(np.float32, copy=False)


def _max_new_frames(row: Any, settings: dict[str, Any] | None) -> int:
    kind = str(_row_value(row, "kind", "narration"))
    if kind in SPECIAL_AUDIO_KINDS:
        max_seconds = DEFAULT_EFFECT_MAX_SECONDS
    else:
        pace = str(_row_value(row, "pace", "normal"))
        configured_bounds = (settings or {}).get("tts", {}).get("pace_chars_per_second", {})
        configured = configured_bounds.get(pace, DEFAULT_PACE_LOWER_BOUNDS.get(pace, 10.5))
        lower_bound = float(configured[0] if isinstance(configured, (list, tuple)) else configured)
        speakable_chars = max(1, sum(char.isalnum() for char in str(_row_value(row, "text", ""))))
        max_seconds = max(3.0, speakable_chars / max(1.0, lower_bound) + GENERATION_PADDING_SECONDS)
    return max(
        MIN_GENERATION_FRAMES,
        min(MAX_GENERATION_FRAMES, math.ceil(max_seconds * VIENEU_FRAMES_PER_SECOND)),
    )


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
    return {
        "temperature": temperature,
        "top_k": 25,
        "top_p": min(0.98, 0.92 + 0.015 * intensity),
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

    @staticmethod
    def _styled_text(row: Any) -> str:
        text = str(row["text"])
        if str(_row_value(row, "kind", "")) == VOCAL_EFFECT_KIND:
            tag = vocal_effect_tag(text)
            if not tag:
                raise AudioQualityError(f"Unsupported vocal effect text: {text!r}")
            return tag
        return text

    def generate_one(self, row: Any, profile: Any, seed: int) -> np.ndarray:
        self.load()
        _set_generation_seed(seed)
        voice = self.voice_for_profile(profile)
        style = "doc_truyen" if str(row["speaker"]) == "NARRATOR" else "tu_nhien"
        try:
            return np.asarray(
                self.tts.infer(
                    self._styled_text(row),
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

    def unload_all(self) -> None:
        self.vieneu.unload()

    def unload_idle_models(self, keep_engine: str | None = None) -> None:
        if keep_engine != "vieneu":
            self.vieneu.unload()

    def generation_seed(self, row: Any, seed_salt: str = "") -> int:
        profile = self.db.voice_profile(int(row["voice_profile_id"]))
        return stable_int(f"segment::{row['stable_id']}::{profile['voice_key']}::{seed_salt}")

    def spoken_text(self, row: Any) -> str:
        if self._pronunciation_pattern is None:
            minimum = float(self.settings["analysis"].get("low_confidence_threshold", 0.58))
            pronunciations = self.db.list_pronunciations(minimum)
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

        def replace(match: re.Match[str]) -> str:
            key = " ".join(match.group(0).casefold().split())
            return self._pronunciation_map.get(key, match.group(0))

        return self._pronunciation_pattern.sub(replace, str(row["text"]))

    def _spoken_row(self, row: Any) -> dict[str, Any]:
        result = dict(row)
        result["text"] = self.spoken_text(row)
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
        profile = self.db.voice_profile(int(row["voice_profile_id"]))
        seed = self.generation_seed(row, seed_salt)
        spoken_row = self._spoken_row(row)
        audio = self.vieneu.generate_one(spoken_row, profile, seed)
        audio = apply_pitch_variant(
            audio,
            self.vieneu.sample_rate,
            int(_row_value(profile, "pitch_semitones", 0)),
        )
        checksum, metrics = atomic_write_wav(
            output,
            audio,
            self.vieneu.sample_rate,
            str(row["text"]),
            self.settings,
            segment=row,
        )
        return checksum, metrics, seed
