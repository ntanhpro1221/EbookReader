from __future__ import annotations

import math
import os
from pathlib import Path
from typing import Any, Iterable

import numpy as np
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
EFFECT_MAX_SECONDS = 5.0
RATE_HARD_MIN_FACTOR = 0.55
RATE_HARD_MAX_FACTOR = 1.50


def _segment_value(segment: Any, key: str, default: Any) -> Any:
    try:
        value = segment[key]
    except (KeyError, TypeError):
        return default
    return default if value is None else value


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
    targets = audio_cfg["segment_target_dbfs"]
    target_dbfs = float(targets.get(volume, targets["normal"]))
    if volume == "normal":
        emotion = str(_segment_value(segment, "emotion", "neutral"))
        intensity = max(0, min(3, int(_segment_value(segment, "intensity", 0))))
        target_dbfs += EMOTION_LEVEL_OFFSETS_DB.get(emotion, 0.0) * intensity / 3.0
    desired_gain = 10 ** ((target_dbfs - 20.0 * math.log10(active_rms)) / 20.0)
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
    chars = max(1, len(text.strip()))
    min_duration = max(0.20, chars / 100 * float(settings["tts"]["min_seconds_per_100_chars"]))
    kind = str(_segment_value(segment, "kind", "")) if segment is not None else ""
    if kind in SPECIAL_AUDIO_KINDS:
        max_duration = EFFECT_MAX_SECONDS
    else:
        max_duration = max(
            5.0,
            chars / 100 * float(settings["tts"]["max_seconds_per_100_chars"]) + 8.0,
        )
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
