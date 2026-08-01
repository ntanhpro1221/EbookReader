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
    "schema_version": 1,
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
        "full_book_first": True,
        "low_confidence_threshold": 0.58,
        "low_confidence_policy": "auto_with_warning",
    },
    "voices": {
        "narrator_engine": "vieneu",
        "character_engine": "voxcpm2",
        "fallback_engine": "vieneu",
        "narrator_voice": "Phạm Tuyên",
        "max_unique_character_voices": 24,
        "minimum_named_character_mentions": 3,
        "reference_text": (
            "Đêm xuống rất chậm. Gió lướt qua hàng cây, mang theo mùi đất ẩm "
            "và một cảm giác yên bình khó gọi thành tên."
        ),
        "narrator_description": (
            "Giọng nam Việt Nam trưởng thành, trầm ấm, rõ chữ, giàu cảm xúc nhưng tiết chế, "
            "nhịp kể tự nhiên như audiobook chuyên nghiệp, phát âm chuẩn tiếng Việt"
        ),
    },
    "tts": {
        "voxcpm_model": "openbmb/VoxCPM2",
        "voxcpm_revision": "bffb3df5a29440629464e5e839f4d214c8714c3d",
        "device": "cuda",
        "sample_rate": 48000,
        "cfg_value": 2.0,
        "inference_timesteps": 10,
        "max_retries": 3,
        "fatal_failure_streak": 3,
        "max_segment_chars": 340,
        "batch_size": 12,
        "auto_tune_batch": True,
        "deterministic_vieneu": True,
        "min_seconds_per_100_chars": 2.1,
        "max_seconds_per_100_chars": 13.0,
        "min_rms": 0.002,
        "max_clipping_fraction": 0.003,
        "failure_policy": "retry_split_fallback_fail",
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
        "combine_full_book": True,
        "create_m3u8": True,
        "keep_verified_wav": True,
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
        "pause_on_battery": True,
        "parent_exit_grace_seconds": 12,
    },
    "safety": {
        "sqlite_synchronous": "FULL",
        "atomic_writes": True,
        "verify_checksums": True,
        "verify_mp3_decode": True,
        "checkpoint_every_segment": True,
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
        "voices": {"character_engine": "vieneu"},
        "asr": {"enabled": True, "min_words": 8, "repair_rounds": 1},
        "tts": {"batch_size": 16},
    },
    "balanced": {},
    "high_quality": {
        "analysis": {"batch_segments": 20, "low_confidence_threshold": 0.65},
        "asr": {"min_words": 1, "min_similarity": 0.64, "max_wer": 0.48, "repair_rounds": 3},
        "tts": {"max_retries": 4, "batch_size": 8},
        "audio": {"keep_verified_wav": True},
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
    if analysis.get("full_book_first") is not True:
        raise ValueError("analysis.full_book_first must remain true")
    if analysis.get("low_confidence_policy") not in {"auto_with_warning", "fail"}:
        raise ValueError("Unsupported analysis.low_confidence_policy")

    voices = settings.get("voices", {})
    supported_engines = {"vieneu", "voxcpm2"}
    for key in ("narrator_engine", "character_engine"):
        if voices.get(key) not in supported_engines:
            raise ValueError(f"Unsupported voices.{key}")
    if voices.get("fallback_engine") not in supported_engines:
        raise ValueError("Unsupported voices.fallback_engine")

    tts = settings.get("tts", {})
    if int(tts.get("sample_rate", 0)) < 8_000:
        raise ValueError("tts.sample_rate must be at least 8000 Hz")
    revision = str(tts.get("voxcpm_revision", ""))
    if len(revision) != 40 or any(char not in "0123456789abcdef" for char in revision.casefold()):
        raise ValueError("tts.voxcpm_revision must be a full 40-character commit hash")
    if int(tts.get("max_segment_chars", 0)) < 50:
        raise ValueError("tts.max_segment_chars must be at least 50")
    if int(tts.get("max_retries", 0)) < 1 or int(tts.get("batch_size", 0)) < 1:
        raise ValueError("TTS retry and batch settings must be positive")
    if int(tts.get("fatal_failure_streak", 0)) < 1:
        raise ValueError("tts.fatal_failure_streak must be positive")
    if tts.get("failure_policy") != "retry_split_fallback_fail":
        raise ValueError("Unsupported tts.failure_policy")

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
        "atomic_writes",
        "verify_checksums",
        "verify_mp3_decode",
        "checkpoint_every_segment",
        "stop_book_on_source_change",
    ):
        if safety.get(key) is not True:
            raise ValueError(f"safety.{key} must remain true")
    if settings.get("audio", {}).get("keep_verified_wav") is not True:
        raise ValueError("audio.keep_verified_wav must remain true until WAV-free recovery is implemented")
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
