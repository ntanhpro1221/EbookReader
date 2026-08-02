from __future__ import annotations

import gc
import re
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Callable

import numpy as np
import soundfile as sf


ASR_REPAIR_MIN_WORDS = 2
WHISPER_SAMPLE_RATE = 16_000


def normalize_transcript(text: str) -> str:
    text = text.casefold().replace("đ", "d")
    text = re.sub(r"[^0-9a-zà-ỹ\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _edit_distance(left: list[str], right: list[str]) -> int:
    if len(left) < len(right):
        left, right = right, left
    previous = list(range(len(right) + 1))
    for i, token_left in enumerate(left, 1):
        current = [i]
        for j, token_right in enumerate(right, 1):
            current.append(
                min(
                    current[-1] + 1,
                    previous[j] + 1,
                    previous[j - 1] + (token_left != token_right),
                )
            )
        previous = current
    return previous[-1]


def transcript_metrics(expected: str, actual: str) -> tuple[float, float]:
    normalized_expected = normalize_transcript(expected)
    normalized_actual = normalize_transcript(actual)
    similarity = SequenceMatcher(None, normalized_expected, normalized_actual).ratio()
    expected_words = normalized_expected.split()
    actual_words = normalized_actual.split()
    wer = _edit_distance(expected_words, actual_words) / max(1, len(expected_words))
    return float(similarity), float(wer)


def is_asr_repair_candidate(expected: str) -> bool:
    return len(normalize_transcript(expected).split()) >= ASR_REPAIR_MIN_WORDS


def load_audio_for_whisper(path: Path) -> np.ndarray:
    audio, sample_rate = sf.read(path, dtype="float32", always_2d=False)
    array = np.asarray(audio, dtype=np.float32)
    if array.ndim != 1:
        raise RuntimeError(f"Whisper input must be mono, got shape {array.shape}")
    if int(sample_rate) != WHISPER_SAMPLE_RATE:
        import torch
        import torchaudio.functional as audio_functional

        waveform = torch.from_numpy(array).unsqueeze(0)
        array = (
            audio_functional.resample(waveform, int(sample_rate), WHISPER_SAMPLE_RATE)
            .squeeze(0)
            .numpy()
            .astype(np.float32, copy=False)
        )
    return array


class WhisperVerifier:
    def __init__(self, settings: dict[str, Any], log: Callable[[str], None]) -> None:
        self.settings = settings["asr"]
        self.allow_downloads = bool(settings.get("safety", {}).get("allow_network_downloads_during_job", False))
        self.log = log
        self.model = None
        self.device = str(self.settings.get("device", "cuda"))

    def load(self) -> bool:
        if not self.settings.get("enabled", True):
            return False
        if self.model is not None:
            return True
        try:
            import torch
            import whisper

            device = self.device
            if device.startswith("cuda") and not torch.cuda.is_available():
                if self.settings.get("cpu_fallback", True):
                    device = "cpu"
                else:
                    raise RuntimeError("CUDA unavailable for Whisper")
            model_name = str(self.settings["model"])
            download_root = Path(str(self.settings.get("download_root", "models/whisper")))
            model_url = getattr(whisper, "_MODELS", {}).get(model_name)
            expected_model = download_root / str(model_url).rsplit("/", 1)[-1] if model_url else None
            if not self.allow_downloads and expected_model is not None and not expected_model.exists():
                message = (
                    f"Thiếu Whisper {model_name} trong {download_root}. Job không được tự tải model giữa chừng; "
                    "hãy chạy Ebook Reader trước."
                )
                self.log(message)
                if self.settings.get("required", False) or self.settings.get("failure_policy") == "fail":
                    raise RuntimeError(message)
                return False
            self.log(f"Nạp Whisper {model_name} trên {device}.")
            self.model = whisper.load_model(
                model_name,
                device=device,
                download_root=str(download_root),
            )
            self.device = device
            return True
        except Exception as exc:  # noqa: BLE001
            self.log(f"Không nạp được Whisper: {exc}")
            if self.settings.get("required", False) or self.settings.get("failure_policy") == "fail":
                raise
            return False

    def unload(self) -> None:
        self.model = None
        gc.collect()
        try:
            import torch

            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except Exception:
            pass

    def transcribe(self, path: Path) -> str:
        if self.model is None:
            raise RuntimeError("Whisper is not loaded")
        audio = load_audio_for_whisper(path)
        result = self.model.transcribe(
            audio,
            language="vi",
            task="transcribe",
            fp16=self.device.startswith("cuda"),
            temperature=0.0,
            beam_size=int(self.settings.get("beam_size", 5)),
            condition_on_previous_text=False,
            verbose=False,
        )
        return str(result.get("text", "")).strip()

    def verify(self, expected: str, wav_path: Path) -> dict[str, Any]:
        normalized_expected = normalize_transcript(expected)
        word_count = len(normalized_expected.split())
        if not normalized_expected:
            return {
                "passed": True,
                "transcript": "",
                "similarity": 1.0,
                "wer": 0.0,
                "reason": "NON_LEXICAL_SKIP",
                "repairable": False,
            }
        if word_count < int(self.settings.get("min_words", 3)) and not self.settings.get("verify_short_dialogue", True):
            return {
                "passed": True,
                "transcript": "",
                "similarity": 1.0,
                "wer": 0.0,
                "reason": "short_skip",
                "repairable": False,
            }
        if not self.load():
            return {
                "passed": not bool(self.settings.get("required", False)),
                "transcript": "",
                "similarity": 0.0,
                "wer": 1.0,
                "reason": "ASR_NOT_RUN",
                "repairable": False,
            }
        try:
            transcript = self.transcribe(wav_path)
        except Exception as exc:  # noqa: BLE001
            self.log(f"Whisper inference lỗi cho {wav_path.name}: {exc}")
            if self.settings.get("required", False) or self.settings.get("failure_policy") == "fail":
                raise
            return {
                "passed": True,
                "transcript": "",
                "similarity": 0.0,
                "wer": 1.0,
                "reason": "ASR_ERROR",
                "repairable": False,
            }
        similarity, wer = transcript_metrics(expected, transcript)
        min_similarity = float(self.settings.get("min_similarity", 0.58))
        max_wer = float(self.settings.get("max_wer", 0.58))
        passed = bool(transcript) and not (
            similarity < min_similarity or (wer > max_wer and similarity < min_similarity + 0.12)
        )
        return {
            "passed": passed,
            "transcript": transcript,
            "similarity": similarity,
            "wer": wer,
            "reason": "ok" if passed else "ASR_MISMATCH",
            "repairable": is_asr_repair_candidate(expected),
        }
