from __future__ import annotations

import hashlib
import json
import os
import ipaddress
import math
from copy import deepcopy
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .database import ANALYSIS_CRITIC_CONFIDENCE_MAX


DEFAULT_SETTINGS: dict[str, Any] = {
    "quality_profile": "high_quality",
    "interactive_prompts": False,
    "analysis": {
        "enabled": True,
        "required": True,
        "model": "qwen3:8b",
        "base_url": "http://127.0.0.1:11434",
        "temperature": 0.1,
        "retry_policy_version": "adaptive_seeded_v2",
        "retry_temperatures": [0.1, 0.2, 0.3],
        "num_ctx": 16384,
        "batch_segments": 28,
        "batch_chars": 6200,
        "max_retries": 3,
        "timeout_seconds": 900,
        "low_confidence_threshold": 0.58,
        "low_confidence_policy": "auto_with_warning",
        "director_critic_enabled": False,
        "director_critic_required": False,
        "director_critic_temperature": 0.2,
        "director_critic_max_retries": 2,
        "director_confidence_cap": 0.95,
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
        # Worker processes that synthesize ahead of the committing loop. Three measured
        # 2.16x and took the GPU from 23% to 90%; five bought 1.3% more for 7318 of 8151
        # MiB, leaving nothing for the foreground. 0 or 1 keeps synthesis inline.
        # See docs/THROUGHPUT.md.
        "parallel_workers": 3,
        # How many segments to hand the pool at once. Pausing, stopping and the resource
        # gate are checked between batches rather than between segments, so this is the
        # granularity at which the run can yield - small multiples of the worker count keep
        # every worker fed without making a stop request wait on a long queue.
        "parallel_batch_size": 9,
        "min_seconds_per_100_chars": 2.1,
        "max_seconds_per_100_chars": 13.0,
        "min_rms": 0.002,
        "max_clipping_fraction": 0.003,
        # Bounds on speech rate with the pauses subtracted (see PAUSE_GROUP_SECONDS), so
        # they had to move with the metric. Compensation shifts the corpus median from 14.50
        # to 16.90 chars/s and the 99th percentile from 17.50 to 22.43 - keeping the old
        # numbers would have swapped a false positive at the bottom for a fresh one at the
        # top, where 22.0 previously never fired at all.
        #
        # These are no more permissive than before, only better aimed: 10.5 sat at the 2nd
        # percentile of the uncompensated distribution and 12.5 sits at the 2nd percentile
        # of the compensated one. Slow and fast are scaled by the same ratios, having too
        # few samples of their own to fit. Like the old numbers these are outlier bounds
        # drawn from what the system produces, not perceptual limits a listener set.
        "pace_chars_per_second": {
            "slow": [7.0, 19.0],
            "normal": [12.5, 24.5],
            "fast": [14.0, 30.0],
        },
        "rate_check_min_chars": 24,
        "failure_policy": "retry_split_fail",
        "allow_silent_replacement": False,
    },
    "asr": {
        "enabled": True,
        "required": True,
        # "openai" is what every run through alpha.32 used. "faster" runs the same
        # large-v3-turbo weights through CTranslate2: measured 2.07x over 200 takes with
        # zero verdict disagreements, and verified against the real runtime to produce
        # word-identical transcripts. Left at openai because changing it is a version
        # event - see docs/DEPENDENCIES.md - so a project opts in deliberately.
        "engine": "openai",
        "model": "turbo",
        "device": "cuda",
        "cpu_fallback": True,
        "download_root": str(Path(os.environ.get("EBOOK_READER_RUNTIME", "runtime")) / "models" / "whisper"),
        "beam_size": 5,
        "verify_short_dialogue": True,
        "min_words": 3,
        "min_similarity": 0.58,
        "max_wer": 0.58,
        "repair_rounds": 2,
        "failure_policy": "fail",
    },
    "perceptual_qa": {
        "enabled": False,
        "failure_policy": "inconclusive",
        "checkpoint_path": str(
            Path(os.environ.get("EBOOK_READER_RUNTIME", "runtime"))
            / "models"
            / "utmosv2"
            / "fold0_s42_best_model.pth"
        ),
        "model_config": "fusion_stage3",
        "fold": 0,
        "model_seed": 42,
        "device": "cpu",
        "predict_dataset": "sarulab",
        "review_delta": -0.8,
        "minimum_duration_seconds": 1.5,
        "num_repetitions": 3,
        "repair_rounds": 2,
        "inference_seed": 42,
        "remove_silent_section": True,
        # 0 keeps scoring in the pipeline process. Above that, whole segments are scored
        # in worker processes and the verdicts still happen here; measured 3.68x at 8
        # workers of 2 threads, with scores identical to the single-process run.
        "parallel_workers": 0,
        "worker_threads": 2,
    },
    "audio": {
        "mp3_bitrate": "192k",
        # Speech has a 17-20 dB crest factor, so a true-peak ceiling of -2 dBFS caps
        # integrated loudness near -20 LUFS. A measured chapter came out at -19.91 LUFS
        # with its peak already on the ceiling: the old -18.0 target was 1.91 dB beyond
        # what the content physically allows, which loudnorm can only miss. -20.0 is
        # reachable and sits squarely inside audiobook norms.
        "loudness_lufs": -20.0,
        "true_peak_db": -2.0,
        "lra": 11.0,
        "segment_active_floor_dbfs": -45.0,
        "segment_peak_dbfs": -2.0,
        # Detecting that VieNeu was still speaking at the frame ceiling compares the
        # trailing RMS of the *levelled* WAV against an absolute floor, so this floor
        # has to track the loudness anchors below. Keep the two 26.5 dB apart, as they
        # were when the anchors sat 6 dB higher, or the gate quietly loses sensitivity.
        "segment_endpoint_floor_dbfs": -51.0,
        "segment_target_dbfs": {
            "soft": -22.0,
            "normal": -19.0,
            "loud": -16.5,
        },
        # Levelling is `min(loudness_gain, peak_safe_gain)`, so anchors close to the
        # -2 dBFS peak ceiling are simply unreachable for speech: 77% of a measured
        # chapter's segments hit the ceiling instead of their target, missing by 1.22 dB
        # on average and 4.09 dB at worst. That inverted the intent - `loud` segments
        # came out quieter than `normal` ones and the narrator anchor vanished. Only the
        # relative levels matter, because the chapter is mastered to one target
        # afterwards, so the whole set sits 6 dB lower and every segment now reaches its
        # anchor exactly. UTMOSv2 is level-invariant (mean MOS delta -0.006 at -6 dB),
        # so this costs nothing perceptually and needs no compression.
        "segment_target_lufs": {
            "soft": -28.0,
            "normal": -25.0,
            "loud": -23.8,
        },
        "segment_narrator_offset_db": 0.5,
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


DIRECTOR_CRITIC_SETTING_KEYS = frozenset(
    {
        "director_critic_enabled",
        "director_critic_required",
        "director_critic_temperature",
        "director_critic_max_retries",
        "director_confidence_cap",
    }
)

ANALYSIS_RETRY_POLICY_VERSION = "adaptive_seeded_v2"
ANALYSIS_RETRY_SETTING_KEYS = frozenset(
    {
        "retry_policy_version",
        "retry_temperatures",
    }
)


PROFILE_OVERRIDES: dict[str, dict[str, Any]] = {
    "fast": {
        "analysis": {"model": "qwen3:4b", "batch_segments": 40},
        "asr": {"enabled": True, "min_words": 8, "repair_rounds": 1},
        "tts": {"batch_size": 16},
    },
    "balanced": {},
    "high_quality": {
        "analysis": {
            "batch_segments": 5,
            "low_confidence_threshold": 0.65,
            "low_confidence_policy": "fail",
            "director_critic_enabled": True,
            "director_critic_required": True,
        },
        "asr": {"min_words": 1, "min_similarity": 0.78, "max_wer": 0.30, "repair_rounds": 5},
        # 8 workers of 2 threads measured 3.68x over the single-process loop on 32 cores,
        # with identical scores. The pool shrinks itself for small batches, low RAM and a
        # GPU device, so this is a ceiling rather than a demand.
        "perceptual_qa": {
            "enabled": True,
            "failure_policy": "fail",
            "parallel_workers": 8,
        },
        # Ten, not four, and the two extra segments it buys are the reason.
        #
        # alpha.32 finished with three segments that never got audio: the pace gate refused
        # all four takes and the sentences were too short to split. Estimating from each
        # segment's own spread across those four (scripts/pace_retry_reachability.py), two
        # were losing to the budget rather than to the voice - one missed the floor by 0.03
        # chars/s - and clear it 88% and 73% of the time given ten. The third reads a rank
        # ladder aloud and no budget reaches it.
        #
        # Cheap because it only spends on segments already failing: three in the whole book
        # reach the budget at all, and eight more touch the gate and pass on the next try.
        # About 18 extra synthesis calls across 948 segments.
        #
        # Re-running never rescues these: synthesis is deterministic per
        # (stable_id, voice_key, seed_salt), and alpha.43 reproduced alpha.32's four takes
        # to the decimal. Attempts 5-10 are new salts, so they are six genuinely new takes -
        # a one-time question whose answer is then permanent for that segment.
        #
        # Safe only because a split candidate is now identified by generation_strategy: this
        # number used to double as the marker for "do not retry", so raising it handed 85
        # stored rows six attempts they were never meant to have.
        "tts": {"max_retries": 10, "batch_size": 8},
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


def is_legacy_director_settings(settings: dict[str, Any]) -> bool:
    analysis = settings.get("analysis", {})
    if not isinstance(analysis, dict):
        return False
    return DIRECTOR_CRITIC_SETTING_KEYS.isdisjoint(analysis)


def is_legacy_analysis_retry_settings(settings: dict[str, Any]) -> bool:
    analysis = settings.get("analysis", {})
    if not isinstance(analysis, dict):
        return False
    return ANALYSIS_RETRY_SETTING_KEYS.isdisjoint(analysis)


def normalize_legacy_locked_settings(settings: dict[str, Any]) -> dict[str, Any]:
    """Build effective settings for a pre-director project without rewriting its lock files."""
    effective = deepcopy(settings)
    analysis = effective.get("analysis")
    if not isinstance(analysis, dict):
        return effective
    defaults = DEFAULT_SETTINGS["analysis"]
    if is_legacy_director_settings(effective):
        for key in DIRECTOR_CRITIC_SETTING_KEYS:
            analysis[key] = deepcopy(defaults[key])
        if effective.get("quality_profile") == "high_quality":
            analysis["director_critic_enabled"] = True
            analysis["director_critic_required"] = True
            analysis["low_confidence_policy"] = "fail"
    if is_legacy_analysis_retry_settings(effective):
        for key in ANALYSIS_RETRY_SETTING_KEYS:
            analysis[key] = deepcopy(defaults[key])
    return effective


# The analysis prompt is a fixed instruction block plus a JSON schema plus the segments
# themselves, and only the last part varies with the batch. Anchored on measurement: a
# five-segment batch carrying 390 characters of text came back at 1,693 prompt tokens, and
# a larger one at 2,481, so the fixed part is roughly 1,500 tokens and Vietnamese text runs
# near 2.5 characters to the token. Both allowances here are deliberately above what was
# measured - a prompt that overruns num_ctx is truncated by Ollama in silence.
ANALYSIS_PROMPT_FIXED_TOKENS = 2048
ANALYSIS_PROMPT_CHARS_PER_TOKEN = 2.0
ANALYSIS_PROMPT_SCHEMA_TOKENS_PER_SEGMENT = 64
ANALYSIS_CONTEXT_GRANULARITY = 1024
ANALYSIS_CONTEXT_MINIMUM = 4096


def _analysis_request_shapes(analysis: dict[str, Any]) -> list[tuple[int, int]]:
    """Every kind of request the analysis phase makes, as (items, prompt characters).

    There is more than one, and the first version of this only knew about the segment
    batch. alpha.32 found the other one the hard way: normalising English names sends
    NAME_PRONUNCIATION_BATCH_SIZE of them at once, and 20 names ask for 4,352 output
    tokens - more than half of the 7,168 window derived from a five-segment batch. The
    ``num_ctx // 2`` term then cut the output allowance to exactly half the window, leaving
    the prompt the other half and not enough of it, and Ollama truncated the prompt in
    silence. The guard caught it and the batch recovered, but the window was simply wrong.

    Names are short, so that request carries almost no text and a great deal of answer;
    segments are the reverse. Sizing one window for both means taking each shape on its own
    terms rather than applying the segment allowance to a list of names.
    """
    from .analysis import NAME_PRONUNCIATION_BATCH_SIZE

    return [
        (max(1, int(analysis.get("batch_segments", 28))), max(0, int(analysis.get("batch_chars", 6200)))),
        # A name plus its context is a few dozen characters, not a paragraph.
        (int(NAME_PRONUNCIATION_BATCH_SIZE), int(NAME_PRONUNCIATION_BATCH_SIZE) * 80),
    ]


def analysis_context_window(analysis: dict[str, Any]) -> int:
    """The context this profile's analysis batches actually need.

    num_ctx was one constant, 16384, for every profile. It is the right size for the
    default profile, whose batches are 28 segments and whose output budget alone is 5,888
    tokens - but high_quality overrides the batch down to 5 and inherited the 16384 anyway.
    That reserves about 2.4 GB of KV cache in VRAM whether a prompt fills it or not, and on
    a card that cannot already hold the model, the context nobody uses is paid for in the
    slowest half of the work: the model spills onto the CPU and generation, which is 86% of
    Ollama's time, runs at 25.6 tokens a second instead of what the GPU could do.

    Two things have to fit, and the second is easy to miss: the output budget is
    ``min(512 + segments * 192, num_ctx // 2, 6144)``, so a context that merely exceeds the
    requested output would still have the ``// 2`` term quietly cut it in half. The window
    is therefore at least twice the requested output, and at least prompt plus output.
    """
    needed = 0
    for items, characters in _analysis_request_shapes(analysis):
        requested_output = min(512 + items * 192, 6144)
        prompt_allowance = (
            ANALYSIS_PROMPT_FIXED_TOKENS
            + int(characters / ANALYSIS_PROMPT_CHARS_PER_TOKEN)
            + items * ANALYSIS_PROMPT_SCHEMA_TOKENS_PER_SEGMENT
        )
        needed = max(needed, 2 * requested_output, prompt_allowance + requested_output)
    rounded = -(-needed // ANALYSIS_CONTEXT_GRANULARITY) * ANALYSIS_CONTEXT_GRANULARITY
    return max(ANALYSIS_CONTEXT_MINIMUM, rounded)


def build_settings(profile: str = "high_quality", overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    if profile not in PROFILE_OVERRIDES:
        raise ValueError(f"Unknown quality profile: {profile}")
    settings = deep_merge(DEFAULT_SETTINGS, PROFILE_OVERRIDES[profile])
    settings["quality_profile"] = profile
    if overrides:
        settings = deep_merge(settings, overrides)
    # Derived after the overrides, because the batch they may change is what decides it.
    # An explicit num_ctx in the overrides still wins: a caller naming a number means it.
    if not (overrides or {}).get("analysis", {}).get("num_ctx"):
        settings["analysis"]["num_ctx"] = analysis_context_window(settings["analysis"])
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
    if not isinstance(analysis, dict):
        raise ValueError("analysis settings must be an object")
    model_name = str(analysis.get("model", "")).strip()
    model_base, separator, model_tag = model_name.rpartition(":")
    if (
        not separator
        or not model_base
        or not model_tag
        or any(character.isspace() for character in model_name)
    ):
        raise ValueError("analysis.model must use an explicit canonical name:tag")
    missing_director_settings = DIRECTOR_CRITIC_SETTING_KEYS - set(analysis)
    if missing_director_settings:
        raise ValueError(
            "Missing analysis director critic settings: "
            + ", ".join(sorted(missing_director_settings))
        )
    missing_retry_settings = ANALYSIS_RETRY_SETTING_KEYS - set(analysis)
    if missing_retry_settings:
        raise ValueError(
            "Missing analysis retry settings: "
            + ", ".join(sorted(missing_retry_settings))
        )
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
    if int(analysis.get("max_retries", 0)) < 1 or float(analysis.get("timeout_seconds", 0)) <= 0:
        raise ValueError("Analysis retry and timeout settings must be positive")
    if analysis.get("retry_policy_version") != ANALYSIS_RETRY_POLICY_VERSION:
        raise ValueError(
            "analysis.retry_policy_version must name the supported adaptive retry policy"
        )
    retry_temperatures = analysis.get("retry_temperatures")
    if (
        not isinstance(retry_temperatures, list)
        or len(retry_temperatures) < int(analysis["max_retries"])
    ):
        raise ValueError(
            "analysis.retry_temperatures must contain at least analysis.max_retries values"
        )
    for temperature in retry_temperatures:
        if (
            type(temperature) not in {int, float}
            or not math.isfinite(float(temperature))
            or not 0.0 <= float(temperature) <= 1.0
        ):
            raise ValueError(
                "analysis.retry_temperatures values must be finite numbers between 0 and 1"
            )
    if int(analysis.get("director_critic_max_retries", 0)) < 1:
        raise ValueError("analysis.director_critic_max_retries must be positive")
    threshold = float(analysis.get("low_confidence_threshold", 0.58))
    if not 0.0 <= threshold <= 1.0:
        raise ValueError("analysis.low_confidence_threshold must be between 0 and 1")
    if analysis.get("low_confidence_policy") not in {"auto_with_warning", "fail"}:
        raise ValueError("Unsupported analysis.low_confidence_policy")
    director_cap = float(analysis.get("director_confidence_cap", 0.95))
    if not 0.0 < director_cap < 1.0:
        raise ValueError("analysis.director_confidence_cap must be between 0 and 1")
    if (
        analysis.get("low_confidence_policy") == "fail"
        and threshold > min(director_cap, ANALYSIS_CRITIC_CONFIDENCE_MAX)
    ):
        raise ValueError(
            "analysis.low_confidence_threshold must not exceed the director "
            "confidence cap or critic schema maximum under fail policy"
        )
    if analysis.get("director_critic_required") and not analysis.get("director_critic_enabled"):
        raise ValueError("Required analysis director critic cannot be disabled")
    if settings.get("quality_profile") == "high_quality" and (
        not analysis.get("enabled") or not analysis.get("required")
    ):
        raise ValueError("high_quality requires enabled mandatory book analysis")
    if settings.get("quality_profile") == "high_quality" and (
        not analysis.get("director_critic_enabled")
        or not analysis.get("director_critic_required")
    ):
        raise ValueError("high_quality requires the mandatory analysis director critic")
    if (
        settings.get("quality_profile") == "high_quality"
        and analysis.get("low_confidence_policy") != "fail"
    ):
        raise ValueError("high_quality requires analysis.low_confidence_policy=fail")

    voices = settings.get("voices", {})
    narrator_voice = str(voices.get("narrator_voice", "")).strip()
    if not narrator_voice:
        raise ValueError("voices.narrator_voice cannot be empty")
    from .voice_catalog import (
        STYLE_NEWS,
        narrator_presets,
        preset_by_name,
    )

    narrator = preset_by_name(narrator_voice)
    narrator_gender = str(voices.get("narrator_gender", ""))
    if narrator_gender != narrator["gender"]:
        raise ValueError("voices.narrator_gender must match voices.narrator_voice")
    if narrator["style"] == STYLE_NEWS:
        raise ValueError("Narrator cannot use a news voice")
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
    minimum_duration = float(tts.get("min_seconds_per_100_chars", 0))
    maximum_duration = float(tts.get("max_seconds_per_100_chars", 0))
    if (
        not math.isfinite(minimum_duration)
        or not math.isfinite(maximum_duration)
        or minimum_duration <= 0
        or maximum_duration <= minimum_duration
    ):
        raise ValueError(
            "TTS duration bounds must satisfy 0 < min_seconds_per_100_chars "
            "< max_seconds_per_100_chars"
        )
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
    if asr.get("required") and not asr.get("enabled"):
        raise ValueError("Required ASR cannot be disabled")
    if asr.get("required") and asr.get("failure_policy") != "fail":
        raise ValueError("Required ASR must use failure_policy=fail")
    if settings.get("quality_profile") == "high_quality" and (
        not asr.get("enabled")
        or not asr.get("required")
        or asr.get("failure_policy") != "fail"
    ):
        raise ValueError("high_quality requires enabled mandatory ASR with failure_policy=fail")

    perceptual = settings.get("perceptual_qa", {})
    if perceptual.get("failure_policy") not in {"inconclusive", "fail"}:
        raise ValueError("Unsupported perceptual_qa.failure_policy")
    checkpoint_path = str(perceptual.get("checkpoint_path", "")).strip()
    if perceptual.get("enabled") and not checkpoint_path:
        raise ValueError("Enabled perceptual QA requires an explicit checkpoint_path")
    review_delta = float(perceptual.get("review_delta", 0.0))
    if not math.isfinite(review_delta) or review_delta > 0.0:
        raise ValueError("perceptual_qa.review_delta must be finite and non-positive")
    minimum_perceptual_duration = float(perceptual.get("minimum_duration_seconds", 0.0))
    if not math.isfinite(minimum_perceptual_duration) or minimum_perceptual_duration <= 0.0:
        raise ValueError("perceptual_qa.minimum_duration_seconds must be positive")
    if int(perceptual.get("num_repetitions", 0)) < 1:
        raise ValueError("perceptual_qa.num_repetitions must be positive")
    if int(perceptual.get("repair_rounds", 0)) < 0:
        raise ValueError("perceptual_qa.repair_rounds must be non-negative")
    if int(perceptual.get("parallel_workers", 0)) < 0:
        raise ValueError("perceptual_qa.parallel_workers must be non-negative")
    if int(perceptual.get("worker_threads", 2)) < 1:
        raise ValueError("perceptual_qa.worker_threads must be positive")
    if settings.get("quality_profile") == "high_quality" and (
        not perceptual.get("enabled") or perceptual.get("failure_policy") != "fail"
    ):
        raise ValueError(
            "high_quality requires enabled perceptual QA with failure_policy=fail"
        )

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
    loudness_targets = audio.get("segment_target_lufs", {})
    if loudness_targets and not (
        float(loudness_targets.get("soft", 0))
        < float(loudness_targets.get("normal", 0))
        < float(loudness_targets.get("loud", 0))
        < 0.0
    ):
        raise ValueError("Segment LUFS targets must satisfy soft < normal < loud < 0")
    narrator_offset = float(audio.get("segment_narrator_offset_db", 0.0))
    if not math.isfinite(narrator_offset) or not 0.0 <= narrator_offset <= 2.0:
        raise ValueError("segment_narrator_offset_db must be between 0 and 2 dB")
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
    data = load_settings_raw(path)
    validate_settings(normalize_legacy_locked_settings(data))
    return data


def load_settings_raw(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Settings JSON must be an object")
    return data
