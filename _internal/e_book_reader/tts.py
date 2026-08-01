from __future__ import annotations

import gc
import random
import re
import time
from pathlib import Path
from typing import Any, Callable

import numpy as np

from .audio_io import AudioQualityError, atomic_write_wav, inspect_wav
from .database import ProjectDB
from .io_utils import stable_int


EMOTION_CONTROLS = {
    "neutral": "giọng tự nhiên, tiết chế",
    "happy": "giọng vui vẻ tự nhiên, có nụ cười nhẹ",
    "sad": "giọng buồn, mềm và chậm vừa",
    "angry": "giọng giận dữ rõ nhưng không vỡ tiếng",
    "afraid": "giọng sợ hãi, hơi căng và gấp",
    "surprised": "giọng ngạc nhiên tự nhiên",
    "tender": "giọng dịu dàng, ấm áp",
    "sarcastic": "giọng mỉa mai nhẹ, tự nhiên",
    "excited": "giọng phấn khích, giàu năng lượng",
    "tired": "giọng mệt mỏi, nhịp chậm nhẹ",
    "whispering": "giọng thì thầm rõ chữ",
}

FATAL_TTS_MARKERS = (
    "cuda driver",
    "cublas",
    "cudnn",
    "no module named",
    "out of memory",
    "pytorch không nhận cuda",
    "thiếu vieneu",
    "thiếu voxcpm2",
    "locked vieneu preset",
)

VOXCPM_CONTROL_MIN_ALNUM_CHARS = 12


def is_fatal_tts_error(error: BaseException) -> bool:
    message = str(error).casefold()
    return any(marker in message for marker in FATAL_TTS_MARKERS)


def is_oom_tts_error(error: BaseException) -> bool:
    return "out of memory" in str(error).casefold()


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


def control_for_segment(row: Any) -> str:
    emotion = EMOTION_CONTROLS.get(str(row["emotion"]), EMOTION_CONTROLS["neutral"])
    pace = {"slow": "nhịp chậm", "normal": "nhịp tự nhiên", "fast": "nhịp nhanh vừa phải"}.get(
        str(row["pace"]), "nhịp tự nhiên"
    )
    volume = {"soft": "âm lượng nhỏ", "normal": "âm lượng tự nhiên", "loud": "âm lượng mạnh nhưng không vỡ tiếng"}.get(
        str(row["volume"]), "âm lượng tự nhiên"
    )
    intensity = max(0, min(3, int(row["intensity"])))
    intensity_text = ["rất tiết chế", "tiết chế", "rõ cảm xúc", "cảm xúc mạnh nhưng tự nhiên"][intensity]
    thought = ", như độc thoại nội tâm" if str(row["kind"]) == "thought" else ""
    return f"{emotion}, {pace}, {volume}, {intensity_text}{thought}"


def voxcpm_prompt_for_segment(row: Any) -> str:
    text = str(row["text"])
    speakable_chars = sum(char.isalnum() for char in text)
    if speakable_chars < VOXCPM_CONTROL_MIN_ALNUM_CHARS:
        return text
    return f"({control_for_segment(row)}) {text}"


class VoxCPM2Engine:
    def __init__(self, settings: dict[str, Any], log: Callable[[str], None]) -> None:
        self.settings = settings
        self.log = log
        self.model = None
        self.sample_rate = int(settings["tts"]["sample_rate"])

    @staticmethod
    def clear_cuda() -> None:
        gc.collect()
        try:
            import torch

            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except Exception:
            pass

    def load(self) -> None:
        if self.model is not None:
            return
        try:
            import torch
            from voxcpm import VoxCPM
            from huggingface_hub import snapshot_download
        except ImportError as exc:
            raise RuntimeError("Thiếu VoxCPM2/PyTorch; hãy chạy START.vbs") from exc
        device = str(self.settings["tts"].get("device", "cuda"))
        if device.startswith("cuda") and not torch.cuda.is_available():
            raise RuntimeError("PyTorch không nhận CUDA")
        optimize = True
        if device.startswith("cuda"):
            total_gb = torch.cuda.get_device_properties(0).total_memory / (1024**3)
            self.log(f"Nạp VoxCPM2 trên {torch.cuda.get_device_name(0)}, VRAM {total_gb:.1f} GB.")
            if total_gb < 10:
                optimize = False
        model_id = str(self.settings["tts"]["voxcpm_model"])
        revision = str(self.settings["tts"]["voxcpm_revision"])
        local_model = snapshot_download(
            model_id,
            revision=revision,
            local_files_only=not bool(
                self.settings.get("safety", {}).get("allow_network_downloads_during_job", False)
            ),
        )
        try:
            self.model = VoxCPM.from_pretrained(
                local_model,
                load_denoiser=False,
                optimize=optimize,
                device=device,
            )
        except RuntimeError:
            if not optimize:
                raise
            self.clear_cuda()
            self.model = VoxCPM.from_pretrained(
                local_model,
                load_denoiser=False,
                optimize=False,
                device=device,
            )
        self.sample_rate = int(getattr(self.model.tts_model, "sample_rate", self.sample_rate))

    def unload(self) -> None:
        self.model = None
        self.clear_cuda()

    def generate(self, text: str, seed: int, reference_wav: Path | None = None) -> np.ndarray:
        self.load()
        _set_generation_seed(seed)
        kwargs: dict[str, Any] = {
            "text": text,
            "cfg_value": float(self.settings["tts"]["cfg_value"]),
            "inference_timesteps": int(self.settings["tts"]["inference_timesteps"]),
            "retry_badcase": True,
            "retry_badcase_max_times": 3,
            "normalize": False,
        }
        if reference_wav is not None:
            kwargs["reference_wav_path"] = str(reference_wav)
        try:
            audio = self.model.generate(**kwargs)
        except RuntimeError as exc:
            self.clear_cuda()
            raise AudioQualityError(str(exc)) from exc
        return np.asarray(audio, dtype=np.float32).reshape(-1)


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
            raise RuntimeError("Thiếu VieNeu; hãy chạy START.vbs") from exc
        self.log("Nạp VieNeu-TTS cho người kể/fallback.")
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
            self.voices = [str(self.settings["voices"]["narrator_voice"])]

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

    def voice_for_profile(self, profile: Any, segment: Any) -> str:
        self.load()
        preset = str(profile["preset_name"] or "").strip()
        if preset:
            if preset not in self.voices:
                raise AudioQualityError(
                    f"Locked VieNeu preset {preset!r} is unavailable; refusing to change voice silently"
                )
            return preset
        index = stable_int(f"vieneu::{profile['voice_key']}::{segment['gender']}", 0, len(self.voices))
        return self.voices[index]

    @staticmethod
    def _styled_text(row: Any) -> str:
        text = str(row["text"])
        emotion = str(row["emotion"])
        if emotion == "happy" and "[cười]" not in text.casefold():
            return f"[cười] {text}"
        if emotion == "sad" and "[thở dài]" not in text.casefold():
            return f"[thở dài] {text}"
        return text

    def generate_one(self, row: Any, profile: Any, seed: int) -> np.ndarray:
        self.load()
        _set_generation_seed(seed)
        voice = self.voice_for_profile(profile, row)
        style = "doc_truyen" if str(row["speaker"]) == "NARRATOR" else "tu_nhien"
        try:
            return np.asarray(self.tts.infer(self._styled_text(row), voice=voice, style=style), dtype=np.float32).reshape(-1)
        except Exception as exc:  # noqa: BLE001
            raise AudioQualityError(str(exc)) from exc

    def generate_batch(
        self, rows: list[Any], profile: Any, batch_size: int, seed: int
    ) -> list[np.ndarray]:
        self.load()
        if not rows:
            return []
        _set_generation_seed(seed)
        voice = self.voice_for_profile(profile, rows[0])
        style = "doc_truyen" if str(rows[0]["speaker"]) == "NARRATOR" else "tu_nhien"
        texts = [self._styled_text(row) for row in rows]
        try:
            try:
                outputs = self.tts.infer_batch(texts, voice=voice, style=style, batch_size=batch_size)
            except TypeError:
                outputs = self.tts.infer_batch(texts, voice=voice, style=style)
            arrays = [np.asarray(audio, dtype=np.float32).reshape(-1) for audio in outputs]
            if len(arrays) != len(rows):
                raise AudioQualityError(f"VieNeu returned {len(arrays)} audios for {len(rows)} rows")
            return arrays
        except Exception as exc:  # noqa: BLE001
            raise AudioQualityError(str(exc)) from exc


class TTSCoordinator:
    def __init__(self, settings: dict[str, Any], db: ProjectDB, voices_dir: Path, log: Callable[[str], None]) -> None:
        self.settings = settings
        self.db = db
        self.voices_dir = voices_dir
        self.log = log
        self.vox = VoxCPM2Engine(settings, log)
        self.vieneu = VieNeuEngine(settings, log)
        self._pronunciation_pattern: re.Pattern[str] | None = None
        self._pronunciation_map: dict[str, str] = {}

    def unload_all(self) -> None:
        self.vox.unload()
        self.vieneu.unload()

    def unload_idle_models(self, keep_engine: str | None = None) -> None:
        if keep_engine != "voxcpm2":
            self.vox.unload()
        if keep_engine != "vieneu":
            self.vieneu.unload()

    def _lock_vieneu_preset(self, profile: Any, row: Any, *, fallback: bool = False) -> Any:
        if str(profile["engine"]) != "vieneu" and not fallback:
            return profile
        selected = self.vieneu.voice_for_profile(profile, row)
        self.db.lock_voice_preset(int(profile["id"]), selected)
        return self.db.voice_profile(int(profile["id"]))

    def generation_seed(self, row: Any, seed_salt: str = "") -> int:
        profile = self.db.voice_profile(int(row["voice_profile_id"]))
        return stable_int(f"segment::{row['stable_id']}::{profile['voice_key']}::{seed_salt}")

    def _fallback_engine(self, profile: Any) -> str:
        primary = str(profile["engine"])
        configured = str(self.settings["voices"].get("fallback_engine", "vieneu"))
        if configured != primary:
            return configured
        return "voxcpm2" if primary == "vieneu" else "vieneu"

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

    def prepare_voice_references(
        self,
        stop_requested: Callable[[], bool],
        before_profile: Callable[[int, int], None] | None = None,
    ) -> None:
        reference_text = str(self.settings["voices"]["reference_text"])
        profiles = self.db.list_voice_profiles()
        vox_profiles = [
            profile
            for profile in profiles
            if str(profile["engine"]) == "voxcpm2" or self._fallback_engine(profile) == "voxcpm2"
        ]
        if not vox_profiles:
            return
        self.vox.load()
        for index, profile in enumerate(vox_profiles, 1):
            if stop_requested():
                return
            if before_profile is not None:
                before_profile(index, len(vox_profiles))
            existing = Path(str(profile["reference_wav"])) if profile["reference_wav"] else None
            if existing and existing.exists():
                valid, _, _ = inspect_wav(existing, reference_text, self.settings)
                if valid:
                    continue
            target = self.voices_dir / f"{profile['voice_key']}.wav"
            description = str(profile["description"] or "Giọng Việt Nam rõ chữ, tự nhiên")
            prompt = f"({description}) {reference_text}"
            last_error = ""
            for attempt in range(int(self.settings["tts"]["max_retries"])):
                seed = int(profile["seed"]) + attempt * 7919
                try:
                    audio = self.vox.generate(prompt, seed=seed)
                    checksum, _ = atomic_write_wav(target, audio, self.vox.sample_rate, reference_text, self.settings)
                    self.db.update_voice_reference(int(profile["id"]), reference_wav=target, reference_sha256=checksum)
                    self.log(f"Đã khóa voice reference {index}/{len(vox_profiles)}: {profile['voice_key']}")
                    break
                except Exception as exc:  # noqa: BLE001
                    last_error = str(exc)
                    time.sleep(min(8, 2 ** attempt))
            else:
                raise AudioQualityError(f"Không tạo được voice reference {profile['voice_key']}: {last_error}")

    def _primary_generate(self, row: Any, profile: Any, seed_salt: str = "") -> tuple[np.ndarray, int]:
        engine = str(profile["engine"])
        seed = self.generation_seed(row, seed_salt)
        spoken_row = self._spoken_row(row)
        if engine == "voxcpm2":
            reference = Path(str(profile["reference_wav"])) if profile["reference_wav"] else None
            if not reference or not reference.exists():
                raise AudioQualityError(f"Missing VoxCPM2 reference for {profile['voice_key']}")
            prompt = voxcpm_prompt_for_segment(spoken_row)
            return self.vox.generate(prompt, seed=seed, reference_wav=reference), self.vox.sample_rate
        if engine == "vieneu":
            profile = self._lock_vieneu_preset(profile, spoken_row)
            return self.vieneu.generate_one(spoken_row, profile, seed), self.vieneu.sample_rate
        raise AudioQualityError(f"Unsupported TTS engine: {engine}")

    def synthesize_vieneu_batch_atomic(
        self, rows: list[Any], outputs: list[Path], batch_size: int
    ) -> list[tuple[str, dict[str, float], int]]:
        if not rows or len(rows) != len(outputs):
            raise ValueError("rows and outputs must have the same non-zero length")
        profile = self.db.voice_profile(int(rows[0]["voice_profile_id"]))
        if str(profile["engine"]) != "vieneu":
            raise ValueError("batch synthesis is only available for VieNeu profiles")
        profile = self._lock_vieneu_preset(profile, rows[0])
        spoken_rows = [self._spoken_row(row) for row in rows]
        batch_seed = stable_int("vieneu-batch::" + "::".join(str(row["stable_id"]) for row in rows))
        arrays = self.vieneu.generate_batch(
            spoken_rows,
            profile,
            batch_size=max(1, batch_size),
            seed=batch_seed,
        )
        results: list[tuple[str, dict[str, float], int]] = []
        for row, output, audio in zip(rows, outputs, arrays):
            checksum, metrics = atomic_write_wav(
                output, audio, self.vieneu.sample_rate, str(row["text"]), self.settings
            )
            results.append((checksum, metrics, batch_seed))
        return results

    def synthesize_atomic(self, row: Any, output: Path, seed_salt: str = "") -> tuple[str, dict[str, float], int]:
        profile = self.db.voice_profile(int(row["voice_profile_id"]))
        audio, sample_rate = self._primary_generate(row, profile, seed_salt=seed_salt)
        checksum, metrics = atomic_write_wav(output, audio, sample_rate, str(row["text"]), self.settings)
        seed = self.generation_seed(row, seed_salt)
        return checksum, metrics, seed

    def fallback_atomic(self, row: Any, output: Path, seed_salt: str = "fallback") -> tuple[str, dict[str, float], int]:
        # Fallback never inserts silence. It uses a real Vietnamese preset and records a warning.
        profile = self.db.voice_profile(int(row["voice_profile_id"]))
        seed = self.generation_seed(row, seed_salt)
        spoken_row = self._spoken_row(row)
        fallback_engine = self._fallback_engine(profile)
        if fallback_engine == "vieneu":
            profile = self._lock_vieneu_preset(profile, spoken_row, fallback=True)
            audio = self.vieneu.generate_one(spoken_row, profile, seed)
            sample_rate = self.vieneu.sample_rate
        elif fallback_engine == "voxcpm2":
            reference = Path(str(profile["reference_wav"])) if profile["reference_wav"] else None
            if not reference or not reference.exists():
                raise AudioQualityError(f"Missing fallback VoxCPM2 reference for {profile['voice_key']}")
            prompt = voxcpm_prompt_for_segment(spoken_row)
            audio = self.vox.generate(prompt, seed=seed, reference_wav=reference)
            sample_rate = self.vox.sample_rate
        else:
            raise AudioQualityError(f"Unsupported fallback TTS engine: {fallback_engine}")
        checksum, metrics = atomic_write_wav(
            output, audio, sample_rate, str(row["text"]), self.settings
        )
        return checksum, metrics, seed
