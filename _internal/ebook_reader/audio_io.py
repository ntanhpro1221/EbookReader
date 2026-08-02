from __future__ import annotations

import math
import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pyloudnorm as pyln
import soundfile as sf

from .io_utils import atomic_write_text, ffmpeg_executable, run_hidden, sha256_file
from .text_processing import SPECIAL_AUDIO_KINDS


class AudioQualityError(RuntimeError):
    pass


EMOTION_LEVEL_OFFSETS_DB = {
    "angry": 1.5,
    "excited": 1.0,
    "surprised": 0.7,
    "whispering": -2.5,
    "tired": -1.0,
    "tender": -0.5,
}
LOUDNESS_EMOTION_OFFSETS_DB = {
    "angry": 0.8,
    "excited": 0.6,
    "surprised": 0.4,
    "whispering": -2.0,
    "tired": -0.7,
    "tender": -0.3,
}
LOUDNESS_BLOCK_SECONDS = 0.4
RATE_HARD_MIN_FACTOR = 0.55
RATE_HARD_MAX_FACTOR = 1.50
VIENEU_V3_CODEC_SAMPLE_RATE = 48_000
VIENEU_V3_CODEC_SAMPLES_PER_FRAME = 3_840
VIENEU_V3_FRAME_SECONDS = VIENEU_V3_CODEC_SAMPLES_PER_FRAME / VIENEU_V3_CODEC_SAMPLE_RATE
MIN_GENERATION_FRAMES = 48
MAX_GENERATION_FRAMES = 300
GENERATION_PADDING_SECONDS = 2.0
MIN_GENERATION_SECONDS = 3.0
MIN_VALIDATION_SECONDS = 5.0
VALIDATION_PADDING_SECONDS = 8.0
SPECIAL_AUDIO_GENERATION_SECONDS = 4.5
SPECIAL_AUDIO_VALIDATION_SECONDS = 5.0
SPECIAL_AUDIO_FADE_SECONDS = 0.12
DEFAULT_PACE_LOWER_BOUNDS = {"slow": 6.0, "normal": 10.5, "fast": 12.0}


@dataclass(frozen=True, slots=True)
class SegmentDurationPolicy:
    generation_max_frames: int
    validation_max_seconds: float

    @property
    def generation_ceiling_seconds(self) -> float:
        return self.generation_max_frames * VIENEU_V3_FRAME_SECONDS


def _segment_value(segment: Any, key: str, default: Any) -> Any:
    try:
        value = segment[key]
    except (KeyError, TypeError):
        return default
    return default if value is None else value


def segment_duration_policy(
    text: str,
    settings: dict[str, Any] | None,
    segment: Any | None = None,
) -> SegmentDurationPolicy:
    tts = (settings or {}).get("tts", {})
    kind = str(_segment_value(segment, "kind", "")) if segment is not None else ""
    if kind in SPECIAL_AUDIO_KINDS:
        generation_seconds = SPECIAL_AUDIO_GENERATION_SECONDS
        validation_seconds = SPECIAL_AUDIO_VALIDATION_SECONDS
    else:
        pace = str(_segment_value(segment, "pace", "normal")) if segment is not None else "normal"
        configured_bounds = tts.get("pace_chars_per_second", {})
        configured = configured_bounds.get(pace, DEFAULT_PACE_LOWER_BOUNDS.get(pace, 10.5))
        lower_bound = float(configured[0] if isinstance(configured, (list, tuple)) else configured)
        speakable_chars = max(1, sum(char.isalnum() for char in text))
        generation_seconds = max(
            MIN_GENERATION_SECONDS,
            speakable_chars / max(1.0, lower_bound) + GENERATION_PADDING_SECONDS,
        )
        chars = max(1, len(text.strip()))
        max_seconds_per_100_chars = float(tts.get("max_seconds_per_100_chars", 13.0))
        validation_seconds = max(
            MIN_VALIDATION_SECONDS,
            chars / 100 * max_seconds_per_100_chars + VALIDATION_PADDING_SECONDS,
        )

    requested_frames = math.ceil(generation_seconds / VIENEU_V3_FRAME_SECONDS)
    safe_frames = math.floor(
        (validation_seconds - VIENEU_V3_FRAME_SECONDS) / VIENEU_V3_FRAME_SECONDS
    )
    max_frames = max(
        MIN_GENERATION_FRAMES,
        min(MAX_GENERATION_FRAMES, requested_frames, safe_frames),
    )
    policy = SegmentDurationPolicy(
        generation_max_frames=max_frames,
        validation_max_seconds=validation_seconds,
    )
    if policy.generation_ceiling_seconds >= policy.validation_max_seconds:
        raise ValueError("VieNeu generation budget must stay below the audio validation limit")
    return policy


def constrain_special_audio_duration(
    audio: Any,
    sample_rate: int,
    text: str,
    settings: dict[str, Any],
    segment: Any | None,
) -> tuple[np.ndarray, bool]:
    array = np.asarray(audio, dtype=np.float32)
    kind = str(_segment_value(segment, "kind", "")) if segment is not None else ""
    if kind not in SPECIAL_AUDIO_KINDS or array.ndim != 1 or sample_rate <= 0:
        return array, False
    policy = segment_duration_policy(text, settings, segment)
    safe_seconds = policy.validation_max_seconds - VIENEU_V3_FRAME_SECONDS
    safe_samples = max(1, int(math.floor(safe_seconds * sample_rate)))
    if array.size <= safe_samples:
        return array, False
    limited = array[:safe_samples].copy()
    fade_samples = min(limited.size, max(1, int(round(SPECIAL_AUDIO_FADE_SECONDS * sample_rate))))
    limited[-fade_samples:] *= np.linspace(1.0, 0.0, fade_samples, dtype=np.float32)
    return limited, True


def signal_metrics(audio: np.ndarray, sample_rate: int) -> dict[str, float]:
    array = np.asarray(audio, dtype=np.float32)
    if array.ndim == 2 and 1 in array.shape:
        array = array.reshape(-1)
    if array.ndim != 1:
        raise AudioQualityError(f"audio must be mono, got shape {array.shape}")
    if array.size == 0:
        return {"duration": 0.0, "rms": 0.0, "peak": 0.0, "clipping_fraction": 0.0}
    return {
        "duration": float(array.size / sample_rate),
        "rms": float(math.sqrt(float(np.mean(np.square(array.astype(np.float64)))))) if array.size else 0.0,
        "peak": float(np.max(np.abs(array))),
        "clipping_fraction": float(np.mean(np.abs(array) >= 0.999)),
    }


def _active_rms(audio: np.ndarray, sample_rate: int, floor_dbfs: float) -> float:
    frame_size = max(1, int(sample_rate * 0.02))
    usable_size = audio.size - (audio.size % frame_size)
    if usable_size <= 0:
        return 0.0
    frames = audio[:usable_size].astype(np.float64).reshape(-1, frame_size)
    frame_rms = np.sqrt(np.mean(np.square(frames), axis=1))
    active = frame_rms[frame_rms >= 10 ** (floor_dbfs / 20.0)]
    return float(math.sqrt(float(np.mean(np.square(active))))) if active.size else 0.0


@lru_cache(maxsize=4)
def _loudness_meter(sample_rate: int) -> pyln.Meter:
    return pyln.Meter(sample_rate, block_size=LOUDNESS_BLOCK_SECONDS)


def integrated_loudness_lufs(audio: np.ndarray, sample_rate: int) -> float | None:
    array = np.asarray(audio, dtype=np.float64).reshape(-1)
    if sample_rate <= 0 or array.size < int(round(sample_rate * LOUDNESS_BLOCK_SECONDS)):
        return None
    try:
        loudness = float(_loudness_meter(sample_rate).integrated_loudness(array))
    except (ValueError, ZeroDivisionError):
        return None
    return loudness if math.isfinite(loudness) else None


def normalize_segment_level(
    audio: np.ndarray,
    sample_rate: int,
    segment: Any,
    settings: dict[str, Any],
) -> np.ndarray:
    array = np.asarray(audio, dtype=np.float32).reshape(-1)
    if not array.size:
        return array
    audio_cfg = settings["audio"]
    active_rms = _active_rms(
        array,
        sample_rate,
        float(audio_cfg.get("segment_active_floor_dbfs", -45.0)),
    )
    if active_rms <= 0:
        return array
    volume = str(_segment_value(segment, "volume", "normal"))
    lufs_targets = audio_cfg.get("segment_target_lufs")
    if isinstance(lufs_targets, dict) and "normal" in lufs_targets:
        target_level = float(lufs_targets.get(volume, lufs_targets["normal"]))
        kind = str(_segment_value(segment, "kind", ""))
        speaker = str(_segment_value(segment, "speaker", ""))
        if speaker == "NARRATOR" and kind not in SPECIAL_AUDIO_KINDS:
            target_level += float(audio_cfg.get("segment_narrator_offset_db", 0.0))
        if volume == "normal":
            emotion = str(_segment_value(segment, "emotion", "neutral"))
            intensity = max(0, min(3, int(_segment_value(segment, "intensity", 0))))
            target_level += LOUDNESS_EMOTION_OFFSETS_DB.get(emotion, 0.0) * intensity / 3.0
        measured_level = integrated_loudness_lufs(array, sample_rate)
        if measured_level is None:
            measured_level = 20.0 * math.log10(active_rms)
    else:
        # Locked books created before LUFS leveling retain their original RMS policy.
        targets = audio_cfg["segment_target_dbfs"]
        target_level = float(targets.get(volume, targets["normal"]))
        if volume == "normal":
            emotion = str(_segment_value(segment, "emotion", "neutral"))
            intensity = max(0, min(3, int(_segment_value(segment, "intensity", 0))))
            target_level += EMOTION_LEVEL_OFFSETS_DB.get(emotion, 0.0) * intensity / 3.0
        measured_level = 20.0 * math.log10(active_rms)
    desired_gain = 10 ** ((target_level - measured_level) / 20.0)
    peak = float(np.max(np.abs(array)))
    peak_limit = 10 ** (float(audio_cfg.get("segment_peak_dbfs", -2.0)) / 20.0)
    peak_safe_gain = peak_limit / peak if peak > 0 else desired_gain
    gain = min(desired_gain, peak_safe_gain)
    return np.asarray(array * gain, dtype=np.float32)


def validate_audio_array(
    audio: Any,
    text: str,
    settings: dict[str, Any],
    sample_rate: int,
    segment: Any | None = None,
) -> tuple[np.ndarray, dict[str, float]]:
    if sample_rate <= 0:
        raise AudioQualityError(f"invalid sample rate: {sample_rate}")
    array = np.asarray(audio, dtype=np.float32)
    if array.ndim == 2 and 1 in array.shape:
        array = array.reshape(-1)
    if array.ndim != 1:
        raise AudioQualityError(f"audio must be mono, got shape {array.shape}")
    if array.size == 0:
        raise AudioQualityError("model returned empty audio")
    if not np.isfinite(array).all():
        raise AudioQualityError("audio contains NaN or infinity")
    metrics = signal_metrics(array, sample_rate)
    loudness = integrated_loudness_lufs(array, sample_rate)
    if loudness is not None:
        metrics["loudness_lufs"] = loudness
    chars = max(1, len(text.strip()))
    min_duration = max(0.20, chars / 100 * float(settings["tts"]["min_seconds_per_100_chars"]))
    kind = str(_segment_value(segment, "kind", "")) if segment is not None else ""
    max_duration = segment_duration_policy(text, settings, segment).validation_max_seconds
    if metrics["duration"] < min_duration:
        raise AudioQualityError(f"audio too short: {metrics['duration']:.2f}s < {min_duration:.2f}s")
    if metrics["duration"] > max_duration:
        raise AudioQualityError(f"audio unusually long: {metrics['duration']:.2f}s > {max_duration:.2f}s")
    if metrics["rms"] < float(settings["tts"]["min_rms"]):
        raise AudioQualityError(f"audio RMS too low: {metrics['rms']:.6f}")
    if metrics["clipping_fraction"] > float(settings["tts"]["max_clipping_fraction"]):
        raise AudioQualityError(f"audio clipping: {metrics['clipping_fraction']:.4%}")
    speakable_chars = sum(char.isalnum() for char in text)
    if (
        segment is not None
        and kind not in SPECIAL_AUDIO_KINDS
        and speakable_chars >= int(settings["tts"].get("rate_check_min_chars", 24))
    ):
        pace = str(_segment_value(segment, "pace", "normal"))
        bounds = settings["tts"]["pace_chars_per_second"].get(
            pace,
            settings["tts"]["pace_chars_per_second"]["normal"],
        )
        rate = speakable_chars / metrics["duration"]
        lower_bound = float(bounds[0])
        upper_bound = float(bounds[1])
        hard_lower = lower_bound * RATE_HARD_MIN_FACTOR
        hard_upper = upper_bound * RATE_HARD_MAX_FACTOR
        if rate < hard_lower or rate > hard_upper:
            raise AudioQualityError(
                f"speech rate far outside {pace} safety range: {rate:.2f} chars/s not in "
                f"[{hard_lower:.2f}, {hard_upper:.2f}]"
            )
        metrics["chars_per_second"] = float(rate)
        metrics["pace_outlier"] = float(rate < lower_bound or rate > upper_bound)
    return array, metrics


def inspect_wav(
    path: Path,
    text: str,
    settings: dict[str, Any],
    segment: Any | None = None,
) -> tuple[bool, dict[str, float], str]:
    try:
        audio, sample_rate = sf.read(path, dtype="float32", always_2d=False)
        _, metrics = validate_audio_array(audio, text, settings, sample_rate, segment=segment)
        return True, metrics, "ok"
    except Exception as exc:  # noqa: BLE001
        return False, {}, str(exc)


def atomic_write_wav(
    path: Path,
    audio: Any,
    sample_rate: int,
    text: str,
    settings: dict[str, Any],
    segment: Any | None = None,
) -> tuple[str, dict[str, float]]:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.stem + ".part" + path.suffix)
    temp.unlink(missing_ok=True)
    array, _ = validate_audio_array(audio, text, settings, sample_rate, segment=segment)
    if segment is not None:
        array = normalize_segment_level(array, sample_rate, segment, settings)
    array, _ = validate_audio_array(array, text, settings, sample_rate, segment=segment)
    sf.write(temp, array, sample_rate, subtype="PCM_16")
    # Windows rejects fsync on a read-only descriptor (WinError 9).
    with temp.open("rb+") as handle:
        os.fsync(handle.fileno())
    valid, metrics, reason = inspect_wav(temp, text, settings, segment=segment)
    if not valid:
        temp.unlink(missing_ok=True)
        raise AudioQualityError(f"temporary WAV failed validation: {reason}")
    checksum = sha256_file(temp)
    os.replace(temp, path)
    return checksum, metrics


def merge_wav_parts_atomic(
    parts: list[Path],
    destination: Path,
    text: str,
    settings: dict[str, Any],
    pause_seconds: float = 0.12,
    segment: Any | None = None,
) -> tuple[str, dict[str, float]]:
    if not parts:
        raise AudioQualityError("no WAV parts to merge")
    arrays: list[np.ndarray] = []
    sample_rate: int | None = None
    for index, part in enumerate(parts):
        audio, sr = sf.read(part, dtype="float32", always_2d=False)
        if np.asarray(audio).ndim != 1:
            raise AudioQualityError(f"WAV part is not mono: {part}")
        if sample_rate is None:
            sample_rate = int(sr)
        elif int(sr) != sample_rate:
            raise AudioQualityError("WAV parts have different sample rates")
        arrays.append(np.asarray(audio, dtype=np.float32))
        if index + 1 < len(parts):
            arrays.append(np.zeros(int(sample_rate * pause_seconds), dtype=np.float32))
    assert sample_rate is not None
    merged = np.concatenate(arrays)
    return atomic_write_wav(destination, merged, sample_rate, text, settings, segment=segment)


def verify_mp3(path: Path) -> tuple[bool, str]:
    if not path.exists() or path.stat().st_size < 4096:
        return False, "MP3 missing or too small"
    ffmpeg = ffmpeg_executable()
    try:
        result = run_hidden(
            [ffmpeg, "-hide_banner", "-loglevel", "error", "-i", str(path), "-f", "null", "-"],
            timeout=3600,
            check=False,
        )
        if result.returncode != 0:
            return False, result.stderr[-3000:]
        return True, "ok"
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)


def _concat_line(path: Path) -> str:
    escaped = path.resolve().as_posix().replace("'", "'\\''")
    return f"file '{escaped}'"


def _silence_file(work_dir: Path, milliseconds: int, sample_rate: int) -> Path:
    milliseconds = max(0, int(milliseconds))
    work_dir.mkdir(parents=True, exist_ok=True)
    path = work_dir / f"silence_{milliseconds:04d}ms_{sample_rate}.wav"
    if path.exists() and path.stat().st_size > 128:
        return path
    samples = np.zeros(int(sample_rate * milliseconds / 1000), dtype=np.float32)
    temp = path.with_name(path.stem + ".part" + path.suffix)
    temp.unlink(missing_ok=True)
    sf.write(temp, samples, sample_rate, subtype="PCM_16")
    with temp.open("rb+") as handle:
        os.fsync(handle.fileno())
    os.replace(temp, path)
    return path


def assemble_chapter_atomic(
    wavs: Iterable[Path | tuple[Path, int]],
    output: Path,
    settings: dict[str, Any],
    *,
    title: str,
    book_title: str,
    track: int,
    work_dir: Path | None = None,
) -> str:
    entries: list[tuple[Path, int]] = []
    for item in wavs:
        if isinstance(item, tuple):
            path, break_ms = item
            entries.append((Path(path), max(0, int(break_ms))))
        else:
            entries.append((Path(item), 0))
    if not entries:
        raise AudioQualityError("chapter has no WAV files")
    for path, _ in entries:
        if not path.exists():
            raise AudioQualityError(f"missing WAV: {path}")

    output.parent.mkdir(parents=True, exist_ok=True)
    concat = output.with_suffix(".concat.part.txt")
    temp = output.with_name(output.stem + ".part" + output.suffix)
    sample_rate = int(settings["tts"]["sample_rate"])
    silence_dir = work_dir or output.parent / ".silence_cache"

    concat_paths: list[Path] = []
    for index, (path, break_ms) in enumerate(entries):
        concat_paths.append(path)
        if index + 1 < len(entries) and break_ms > 0:
            concat_paths.append(_silence_file(silence_dir, break_ms, sample_rate))
    atomic_write_text(concat, "\n".join(_concat_line(path) for path in concat_paths) + "\n")

    temp.unlink(missing_ok=True)
    audio = settings["audio"]
    ffmpeg = ffmpeg_executable()
    command = [
        ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
        "-f", "concat", "-safe", "0", "-i", str(concat),
        "-af", f"loudnorm=I={audio['loudness_lufs']}:TP={audio['true_peak_db']}:LRA={audio['lra']}",
        "-ar", str(sample_rate), "-ac", "1",
        "-codec:a", "libmp3lame", "-b:a", str(audio["mp3_bitrate"]),
        "-metadata", f"album={book_title}", "-metadata", f"title={title}",
        "-metadata", f"track={track}", str(temp),
    ]
    try:
        result = run_hidden(command, timeout=7200, check=False)
        if result.returncode != 0:
            raise AudioQualityError(f"FFmpeg chapter assembly failed: {result.stderr[-3000:]}")
        valid, reason = verify_mp3(temp)
        if not valid:
            raise AudioQualityError(f"temporary MP3 failed decode verification: {reason}")
        checksum = sha256_file(temp)
        os.replace(temp, output)
        return checksum
    finally:
        concat.unlink(missing_ok=True)
        if temp.exists() and temp != output:
            temp.unlink(missing_ok=True)


def write_playlist_atomic(chapter_files: list[Path], output: Path) -> None:
    rows = ["#EXTM3U"] + [f"chapters/{path.name}" for path in chapter_files]
    atomic_write_text(output, "\n".join(rows) + "\n")


def export_json_atomic(path: Path, payload: Any) -> None:
    from .io_utils import atomic_write_json

    atomic_write_json(path, payload)
