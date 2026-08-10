from __future__ import annotations

import gc
import math
import re
from pathlib import Path
from typing import Any, Callable

import numpy as np
import soundfile as sf
from scipy.signal import resample_poly

from .resource_manager import trim_process_working_set
from .text_processing import is_vocalization_only


ASR_REPAIR_MIN_WORDS = 1
SEVERE_MISMATCH_MAX_SIMILARITY = 0.35
SEVERE_MISMATCH_MIN_LENGTH_RATIO = 3.0
SEVERE_MISMATCH_MIN_EXTRA_WORDS = 4
WHISPER_SAMPLE_RATE = 16_000
MAX_PLAUSIBLE_TRANSCRIPT_WORDS_PER_SECOND = 5.0
TRANSCRIPT_WORD_MARGIN = 2
MIN_PLAUSIBLE_TRANSCRIPT_WORDS = 4
WHISPER_TIMELINE_ABSOLUTE_MARGIN_SECONDS = 1.0
WHISPER_TIMELINE_DURATION_FACTOR = 2.0
SHORT_CONTEXT_MAX_WORDS = 5
SHORT_CONTEXT_REPEAT_COUNT = 3
SHORT_CONTEXT_GAP_SECONDS = 0.24
ASR_PASS = "pass"
ASR_MISMATCH = "mismatch"
ASR_INCONCLUSIVE = "inconclusive"


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
    expected_characters = list(normalized_expected)
    actual_characters = list(normalized_actual)
    character_errors = _edit_distance(expected_characters, actual_characters)
    similarity = max(0.0, 1.0 - character_errors / max(1, len(expected_characters)))
    expected_words = normalized_expected.split()
    actual_words = normalized_actual.split()
    wer = _edit_distance(expected_words, actual_words) / max(1, len(expected_words))
    return float(similarity), float(wer)


def is_asr_repair_candidate(expected: str) -> bool:
    return len(normalize_transcript(expected).split()) >= ASR_REPAIR_MIN_WORDS


def is_severe_asr_mismatch(expected: str, actual: str, similarity: float) -> bool:
    expected_words = normalize_transcript(expected).split()
    actual_words = normalize_transcript(actual).split()
    if not expected_words:
        return False
    if not actual_words:
        return True
    minimum_actual_words = max(
        len(expected_words) + SEVERE_MISMATCH_MIN_EXTRA_WORDS,
        math.ceil(len(expected_words) * SEVERE_MISMATCH_MIN_LENGTH_RATIO),
    )
    return float(similarity) < SEVERE_MISMATCH_MAX_SIMILARITY and (
        len(actual_words) >= minimum_actual_words
        or abs(len(actual_words) - len(expected_words)) <= SEVERE_MISMATCH_MIN_EXTRA_WORDS
    )


def transcript_exceeds_physical_rate(actual: str, duration_seconds: float) -> bool:
    actual_words = normalize_transcript(actual).split()
    if not actual_words or duration_seconds <= 0:
        return False
    plausible_words = max(
        MIN_PLAUSIBLE_TRANSCRIPT_WORDS,
        math.ceil(duration_seconds * MAX_PLAUSIBLE_TRANSCRIPT_WORDS_PER_SECOND)
        + TRANSCRIPT_WORD_MARGIN,
    )
    return len(actual_words) > plausible_words


def transcription_exceeds_audio_timeline(
    segments: list[dict[str, Any]],
    duration_seconds: float,
) -> bool:
    if duration_seconds <= 0 or not segments:
        return False
    plausible_end = max(
        duration_seconds + WHISPER_TIMELINE_ABSOLUTE_MARGIN_SECONDS,
        duration_seconds * WHISPER_TIMELINE_DURATION_FACTOR,
    )
    for segment in segments:
        try:
            end = float(segment.get("end", 0.0))
        except (TypeError, ValueError):
            continue
        if end > plausible_end:
            return True
    return False


def load_audio_for_whisper(path: Path) -> np.ndarray:
    audio, sample_rate = sf.read(path, dtype="float32", always_2d=False)
    array = np.asarray(audio, dtype=np.float32)
    if array.ndim != 1:
        raise RuntimeError(f"Whisper input must be mono, got shape {array.shape}")
    if int(sample_rate) != WHISPER_SAMPLE_RATE:
        divisor = math.gcd(int(sample_rate), WHISPER_SAMPLE_RATE)
        array = resample_poly(
            array,
            WHISPER_SAMPLE_RATE // divisor,
            int(sample_rate) // divisor,
        ).astype(np.float32, copy=False)
    return array


class WhisperVerifier:
    def __init__(self, settings: dict[str, Any], log: Callable[[str], None]) -> None:
        self.settings = settings["asr"]
        self.allow_downloads = bool(settings.get("safety", {}).get("allow_network_downloads_during_job", False))
        self.log = log
        self.model = None
        self.device = str(self.settings.get("device", "cuda"))
        self._last_transcription_timeline_impossible = False

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
        had_model = self.model is not None
        self.model = None
        if not had_model:
            return
        gc.collect()
        try:
            import torch

            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except Exception:
            pass
        trim_process_working_set()

    def _transcribe_audio(
        self,
        audio: np.ndarray,
        duration_seconds: float,
        *,
        confirmation: bool,
    ) -> str:
        if self.model is None:
            raise RuntimeError("Whisper is not loaded")
        self._last_transcription_timeline_impossible = False
        decode_options: dict[str, Any] = {
            "language": "vi",
            "task": "transcribe",
            "fp16": self.device.startswith("cuda"),
            "temperature": 0.0,
            "condition_on_previous_text": False,
            "verbose": False,
        }
        if not confirmation:
            decode_options["beam_size"] = int(self.settings.get("beam_size", 5))
        result = self.model.transcribe(audio, **decode_options)
        raw_segments = result.get("segments", [])
        segments = [item for item in raw_segments if isinstance(item, dict)]
        self._last_transcription_timeline_impossible = transcription_exceeds_audio_timeline(
            segments,
            duration_seconds,
        )
        return str(result.get("text", "")).strip()

    def transcribe(self, path: Path, *, confirmation: bool = False) -> str:
        audio = load_audio_for_whisper(path)
        try:
            duration_seconds = float(sf.info(path).duration)
        except (RuntimeError, TypeError, ValueError):
            duration_seconds = float(audio.size / WHISPER_SAMPLE_RATE)
        return self._transcribe_audio(
            audio,
            duration_seconds,
            confirmation=confirmation,
        )

    def _evaluate_transcript(
        self,
        expected: str,
        transcript: str,
        duration_seconds: float,
    ) -> dict[str, Any]:
        similarity, wer = transcript_metrics(expected, transcript)
        if self._last_transcription_timeline_impossible:
            return {
                "passed": False,
                "verdict": ASR_INCONCLUSIVE,
                "transcript": transcript,
                "similarity": similarity,
                "wer": wer,
                "reason": "ASR_TRANSCRIPT_TIMELINE_IMPOSSIBLE",
                "repairable": False,
                "severe": False,
            }
        if transcript_exceeds_physical_rate(transcript, duration_seconds):
            return {
                "passed": False,
                "verdict": ASR_INCONCLUSIVE,
                "transcript": transcript,
                "similarity": similarity,
                "wer": wer,
                "reason": "ASR_TRANSCRIPT_RATE_IMPOSSIBLE",
                "repairable": False,
                "severe": False,
            }
        if is_vocalization_only(expected) and (
            not normalize_transcript(transcript) or is_vocalization_only(transcript)
        ):
            return {
                "passed": True,
                "verdict": ASR_PASS,
                "transcript": transcript,
                "similarity": similarity,
                "wer": wer,
                "reason": "VOCALIZATION_ASR_COMPATIBLE",
                "repairable": False,
                "severe": False,
            }
        min_similarity = float(self.settings.get("min_similarity", 0.58))
        max_wer = float(self.settings.get("max_wer", 0.58))
        passed = bool(transcript) and not (
            similarity < min_similarity or (wer > max_wer and similarity < min_similarity + 0.12)
        )
        return {
            "passed": passed,
            "verdict": ASR_PASS if passed else ASR_MISMATCH,
            "transcript": transcript,
            "similarity": similarity,
            "wer": wer,
            "reason": "ok" if passed else "ASR_MISMATCH",
            "repairable": is_asr_repair_candidate(expected),
            "severe": not passed and is_severe_asr_mismatch(expected, transcript, similarity),
        }

    def can_verify_repeated_short(self, expected: str) -> bool:
        word_count = len(normalize_transcript(expected).split())
        return 0 < word_count <= SHORT_CONTEXT_MAX_WORDS

    def verify_repeated_short(
        self,
        expected: str,
        wav_path: Path,
        *,
        confirmation: bool = False,
    ) -> dict[str, Any]:
        if not self.can_verify_repeated_short(expected):
            raise ValueError("Repeated short-context ASR only supports one to five words")
        if not self.load():
            return {
                "passed": False,
                "verdict": ASR_INCONCLUSIVE,
                "transcript": "",
                "similarity": 0.0,
                "wer": 1.0,
                "reason": "ASR_NOT_RUN",
                "repairable": False,
                "severe": False,
            }
        audio = load_audio_for_whisper(wav_path)
        gap = np.zeros(
            int(round(WHISPER_SAMPLE_RATE * SHORT_CONTEXT_GAP_SECONDS)),
            dtype=np.float32,
        )
        pieces: list[np.ndarray] = []
        for index in range(SHORT_CONTEXT_REPEAT_COUNT):
            pieces.append(audio)
            if index + 1 < SHORT_CONTEXT_REPEAT_COUNT:
                pieces.append(gap)
        repeated_audio = np.concatenate(pieces).astype(np.float32, copy=False)
        transcript = self._transcribe_audio(
            repeated_audio,
            repeated_audio.size / WHISPER_SAMPLE_RATE,
            confirmation=confirmation,
        )
        repeated_expected = " ".join([expected] * SHORT_CONTEXT_REPEAT_COUNT)
        result = self._evaluate_transcript(
            repeated_expected,
            transcript,
            repeated_audio.size / WHISPER_SAMPLE_RATE,
        )
        if result["passed"]:
            result["reason"] = "ASR_REPEATED_SHORT_PASS"
        return result

    def verify(
        self,
        expected: str,
        wav_path: Path,
        *,
        confirmation: bool = False,
    ) -> dict[str, Any]:
        normalized_expected = normalize_transcript(expected)
        word_count = len(normalized_expected.split())
        if not normalized_expected:
            return {
                "passed": True,
                "verdict": ASR_PASS,
                "transcript": "",
                "similarity": 1.0,
                "wer": 0.0,
                "reason": "NON_LEXICAL_SKIP",
                "repairable": False,
                "severe": False,
            }
        if word_count < int(self.settings.get("min_words", 3)) and not self.settings.get("verify_short_dialogue", True):
            return {
                "passed": False,
                "verdict": ASR_INCONCLUSIVE,
                "transcript": "",
                "similarity": 1.0,
                "wer": 0.0,
                "reason": "short_skip",
                "repairable": False,
                "severe": False,
            }
        if not self.load():
            return {
                "passed": False,
                "verdict": ASR_INCONCLUSIVE,
                "transcript": "",
                "similarity": 0.0,
                "wer": 1.0,
                "reason": "ASR_NOT_RUN",
                "repairable": False,
                "severe": False,
            }
        self._last_transcription_timeline_impossible = False
        try:
            transcript = (
                self.transcribe(wav_path, confirmation=True)
                if confirmation
                else self.transcribe(wav_path)
            )
        except Exception as exc:  # noqa: BLE001
            self.log(f"Whisper inference lỗi cho {wav_path.name}: {exc}")
            if self.settings.get("required", False) or self.settings.get("failure_policy") == "fail":
                raise
            return {
                "passed": False,
                "verdict": ASR_INCONCLUSIVE,
                "transcript": "",
                "similarity": 0.0,
                "wer": 1.0,
                "reason": "ASR_ERROR",
                "repairable": False,
                "severe": False,
            }
        try:
            duration_seconds = float(sf.info(wav_path).duration)
        except (RuntimeError, TypeError, ValueError):
            duration_seconds = 0.0
        return self._evaluate_transcript(expected, transcript, duration_seconds)
