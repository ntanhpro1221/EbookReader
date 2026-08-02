from __future__ import annotations

import hashlib
import json
import os
import ipaddress
from copy import deepcopy
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


DEFAULT_SETTINGS: dict[str, Any] = {
    "quality_profile": "balanced",
    "interactive_prompts": False,
    "analysis": {
        "enabled": True,
        "required": True,
        "model": "qwen3:8b",
        "base_url": "http://127.0.0.1:11434",
        "temperature": 0.1,
        "num_ctx": 16384,
        "batch_segments": 28,
        "batch_chars": 6200,
        "max_alias_candidates": 400,
        "max_retries": 3,
        "timeout_seconds": 900,
        "low_confidence_threshold": 0.58,
        "low_confidence_policy": "auto_with_warning",
    },
    "voices": {
        "narrator_gender": "male",
        "narrator_voice": "Phạm Tuyên",
        "minimum_named_character_mentions": 3,
        "max_character_pitch_semitones": 2,
        "narrator_description": (
            "Giọng nam Việt Nam trưởng thành, trầm ấm, rõ chữ, giàu cảm xúc nhưng tiết chế, "
            "nhịp kể tự nhiên như audiobook chuyên nghiệp, phát âm chuẩn tiếng Việt"
        ),
    },
    "tts": {
        "device": "cuda",
        "sample_rate": 48000,
        "max_retries": 3,
        "fatal_failure_streak": 3,
        "max_segment_chars": 340,
        "batch_size": 12,
        "min_seconds_per_100_chars": 2.1,
        "max_seconds_per_100_chars": 13.0,
        "min_rms": 0.002,
        "max_clipping_fraction": 0.003,
        "pace_chars_per_second": {
            "slow": [6.0, 17.0],
            "normal": [10.5, 22.0],
            "fast": [12.0, 27.0],
        },
        "rate_check_min_chars": 24,
        "failure_policy": "retry_split_fail",
        "allow_silent_replacement": False,
    },
    "asr": {
        "enabled": True,
        "required": False,
        "model": "turbo",
        "device": "cuda",
        "cpu_fallback": True,
        "download_root": str(Path(os.environ.get("E_BOOK_READER_RUNTIME", "runtime")) / "models" / "whisper"),
        "beam_size": 5,
        "verify_short_dialogue": True,
        "min_words": 3,
        "min_similarity": 0.58,
        "max_wer": 0.58,
        "repair_rounds": 2,
        "failure_policy": "warning_continue",
    },
    "audio": {
        "mp3_bitrate": "192k",
        "loudness_lufs": -18.0,
        "true_peak_db": -2.0,
        "lra": 11.0,
        "segment_active_floor_dbfs": -45.0,
        "segment_peak_dbfs": -2.0,
        "segment_target_dbfs": {
            "soft": -22.0,
            "normal": -19.0,
            "loud": -16.5,
        },
        "create_m3u8": True,
        "export_metadata": True,
    },
    "resources": {
        "mode": "max_safe_adaptive_foreground",
        "worker_priority": "below_normal",
        "max_gpu_temp_c": 86,
        "resume_gpu_temp_c": 80,
        "critical_gpu_temp_c": 91,
        "min_free_ram_gb": 3.5,
        "critical_free_ram_gb": 1.5,
        "min_free_disk_gb": 12.0,
        "critical_free_disk_gb": 5.0,
        "foreground_cpu_trigger": 35.0,
        "foreground_gpu_trigger": 25.0,
        "system_cpu_trigger": 82.0,
        "system_disk_trigger": 88.0,
        "idle_seconds_before_ramp": 20,
        "ramp_step_seconds": 8,
        "unload_model_for_foreground_vram": True,
        "parent_exit_grace_seconds": 12,
    },
    "safety": {
        "sqlite_synchronous": "FULL",
        "verify_checksums": True,
        "stop_book_on_source_change": True,
        "notify_on_critical_stop": True,
        "notify_on_recovery": True,
        "never_prompt_during_run": True,
        "allow_network_downloads_during_job": False,
        "allow_remote_analysis": False,
    },
}


PROFILE_OVERRIDES: dict[str, dict[str, Any]] = {
    "fast": {
        "analysis": {"model": "qwen3:4b", "batch_segments": 40},
        "asr": {"enabled": True, "min_words": 8, "repair_rounds": 1},
        "tts": {"batch_size": 16},
    },
    "balanced": {},
    "high_quality": {
        "analysis": {"batch_segments": 20, "low_confidence_threshold": 0.65},
        "asr": {"min_words": 1, "min_similarity": 0.64, "max_wer": 0.48, "repair_rounds": 3},
        "tts": {"max_retries": 4, "batch_size": 8},
    },
}


def deep_merge(base: dict[str, Any], update: dict[str, Any]) -> dict[str, Any]:
    result = deepcopy(base)
    for key, value in update.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = deepcopy(value)
    return result


def build_settings(profile: str = "balanced", overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    if profile not in PROFILE_OVERRIDES:
        raise ValueError(f"Unknown quality profile: {profile}")
    settings = deep_merge(DEFAULT_SETTINGS, PROFILE_OVERRIDES[profile])
    settings["quality_profile"] = profile
    if overrides:
        settings = deep_merge(settings, overrides)
    from .voice_catalog import DEFAULT_NARRATOR_BY_GENDER, preset_by_name

    voice_overrides = overrides.get("voices", {}) if overrides else {}
    if "narrator_gender" in voice_overrides and "narrator_voice" not in voice_overrides:
        requested_gender = str(voice_overrides["narrator_gender"])
        default_voice = DEFAULT_NARRATOR_BY_GENDER.get(requested_gender)
        if default_voice is None:
            raise ValueError("Unsupported voices.narrator_gender")
        settings["voices"]["narrator_voice"] = default_voice

    narrator = preset_by_name(str(settings["voices"]["narrator_voice"]))
    settings["voices"]["narrator_gender"] = narrator["gender"]
    settings["voices"]["narrator_description"] = (
        f"{narrator['description']} · Người kể audiobook rõ chữ, biểu cảm tiết chế, nhịp tự nhiên"
    )
    validate_settings(settings)
    return settings


def validate_settings(settings: dict[str, Any]) -> None:
    if settings.get("interactive_prompts"):
        raise ValueError("interactive_prompts must remain false for unattended book jobs")
    if settings.get("safety", {}).get("never_prompt_during_run") is not True:
        raise ValueError("safety.never_prompt_during_run must be true")
    if settings.get("tts", {}).get("allow_silent_replacement"):
        raise ValueError("Silent replacement is forbidden because it can hide missing narration")
    analysis = settings.get("analysis", {})
    parsed_url = urlparse(str(analysis.get("base_url", "")))
    if parsed_url.scheme not in {"http", "https"} or not parsed_url.hostname:
        raise ValueError("analysis.base_url must be a valid HTTP(S) URL")
    hostname = parsed_url.hostname.casefold()
    is_loopback = hostname == "localhost"
    if not is_loopback:
        try:
            is_loopback = ipaddress.ip_address(hostname).is_loopback
        except ValueError:
            is_loopback = False
    if not is_loopback and not settings.get("safety", {}).get("allow_remote_analysis", False):
        raise ValueError("Remote analysis requires safety.allow_remote_analysis=true")
    if int(analysis.get("batch_segments", 0)) < 1 or int(analysis.get("batch_chars", 0)) < 100:
        raise ValueError("Analysis batch limits must be positive")
    if int(analysis.get("max_alias_candidates", 0)) < 2:
        raise ValueError("analysis.max_alias_candidates must be at least 2")
    if int(analysis.get("max_retries", 0)) < 1 or float(analysis.get("timeout_seconds", 0)) <= 0:
        raise ValueError("Analysis retry and timeout settings must be positive")
    threshold = float(analysis.get("low_confidence_threshold", 0.58))
    if not 0.0 <= threshold <= 1.0:
        raise ValueError("analysis.low_confidence_threshold must be between 0 and 1")
    if analysis.get("low_confidence_policy") not in {"auto_with_warning", "fail"}:
        raise ValueError("Unsupported analysis.low_confidence_policy")

    voices = settings.get("voices", {})
    narrator_voice = str(voices.get("narrator_voice", "")).strip()
    if not narrator_voice:
        raise ValueError("voices.narrator_voice cannot be empty")
    from .voice_catalog import (
        REGION_CENTRAL,
        STYLE_NEWS,
        narrator_presets,
        preset_by_name,
    )

    narrator = preset_by_name(narrator_voice)
    narrator_gender = str(voices.get("narrator_gender", ""))
    if narrator_gender != narrator["gender"]:
        raise ValueError("voices.narrator_gender must match voices.narrator_voice")
    if narrator["style"] == STYLE_NEWS or narrator["region"] == REGION_CENTRAL:
        raise ValueError("Narrator must use a standard natural or storytelling voice")
    if narrator_voice not in {preset["name"] for preset in narrator_presets(narrator_gender)}:
        raise ValueError("Unsupported narrator voice")
    max_pitch_shift = int(voices.get("max_character_pitch_semitones", -1))
    if not 0 <= max_pitch_shift <= 2:
        raise ValueError("voices.max_character_pitch_semitones must be between 0 and 2")

    tts = settings.get("tts", {})
    if int(tts.get("sample_rate", 0)) < 8_000:
        raise ValueError("tts.sample_rate must be at least 8000 Hz")
    if int(tts.get("max_segment_chars", 0)) < 50:
        raise ValueError("tts.max_segment_chars must be at least 50")
    if int(tts.get("max_retries", 0)) < 1 or int(tts.get("batch_size", 0)) < 1:
        raise ValueError("TTS retry and batch settings must be positive")
    if int(tts.get("fatal_failure_streak", 0)) < 1:
        raise ValueError("tts.fatal_failure_streak must be positive")
    if tts.get("failure_policy") != "retry_split_fail":
        raise ValueError("Unsupported tts.failure_policy")
    pace_ranges = tts.get("pace_chars_per_second", {})
    for pace in ("slow", "normal", "fast"):
        bounds = pace_ranges.get(pace, [])
        if len(bounds) != 2 or float(bounds[0]) <= 0 or float(bounds[0]) >= float(bounds[1]):
            raise ValueError(f"tts.pace_chars_per_second.{pace} must contain increasing bounds")
    if int(tts.get("rate_check_min_chars", 0)) < 1:
        raise ValueError("tts.rate_check_min_chars must be positive")

    asr = settings.get("asr", {})
    if int(asr.get("repair_rounds", 0)) < 0 or int(asr.get("beam_size", 0)) < 1:
        raise ValueError("ASR repair_rounds and beam_size are invalid")
    for key in ("min_similarity", "max_wer"):
        if not 0.0 <= float(asr.get(key, 0.0)) <= 1.0:
            raise ValueError(f"asr.{key} must be between 0 and 1")
    if asr.get("failure_policy") not in {"warning_continue", "fail"}:
        raise ValueError("Unsupported asr.failure_policy")

    safety = settings.get("safety", {})
    for key in (
        "verify_checksums",
        "stop_book_on_source_change",
    ):
        if safety.get(key) is not True:
            raise ValueError(f"safety.{key} must remain true")
    audio = settings.get("audio", {})
    targets = audio.get("segment_target_dbfs", {})
    if not (
        float(targets.get("soft", 0))
        < float(targets.get("normal", 0))
        < float(targets.get("loud", 0))
        < float(audio.get("segment_peak_dbfs", 0))
    ):
        raise ValueError("Segment dBFS targets must satisfy soft < normal < loud < peak")
    resources = settings.get("resources", {})
    max_temp = int(resources.get("max_gpu_temp_c", 86))
    resume_temp = int(resources.get("resume_gpu_temp_c", 80))
    critical_temp = int(resources.get("critical_gpu_temp_c", 91))
    if not (40 <= resume_temp < max_temp < critical_temp <= 100):
        raise ValueError("GPU temperature thresholds must satisfy resume < max < critical")
    if float(resources.get("critical_free_disk_gb", 5)) >= float(resources.get("min_free_disk_gb", 12)):
        raise ValueError("critical_free_disk_gb must be lower than min_free_disk_gb")
    if float(resources.get("critical_free_ram_gb", 1.5)) >= float(resources.get("min_free_ram_gb", 3.5)):
        raise ValueError("critical_free_ram_gb must be lower than min_free_ram_gb")


def canonical_json(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def settings_hash(settings: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json(settings).encode("utf-8")).hexdigest()


def save_settings(path: Path, settings: dict[str, Any]) -> None:
    validate_settings(settings)
    from .io_utils import atomic_write_json

    atomic_write_json(path, settings)


def load_settings(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    validate_settings(data)
    return data
