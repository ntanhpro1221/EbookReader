from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from .config import canonical_json, settings_hash


QUALITY_POLICY_VERSION = 1
CHAPTER_QUALITY_STAGE = "chapter_post_encode_v1"
SEGMENT_CONTENT_STAGE = "segment_asr_content_v1"
TEXT_SEGMENTATION_STAGE = "text_segmentation_v1"
ANALYSIS_CASTING_STAGE = "analysis_casting_v1"
TEXT_SEGMENTATION_IMPLEMENTATION_FILES = (
    "text_processing.py",
)
ANALYSIS_CASTING_IMPLEMENTATION_FILES = (
    "analysis.py",
    "character_registry.py",
    "models.py",
    "voice_catalog.py",
)
QUALITY_IMPLEMENTATION_FILES = (
    "analysis.py",
    "asr.py",
    "audio_io.py",
    "character_registry.py",
    "config.py",
    "database.py",
    "models.py",
    "pipeline.py",
    "quality_policy.py",
    "recovery.py",
    "text_processing.py",
    "tts.py",
    "voice_catalog.py",
    "../pyproject.toml",
    "../uv.lock",
)


def implementation_files_hash(filenames: tuple[str, ...]) -> str:
    package_root = Path(__file__).resolve().parent
    digest = hashlib.sha256()
    for filename in filenames:
        path = (package_root / filename).resolve()
        digest.update(filename.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes() if path.is_file() else b"MISSING")
        digest.update(b"\0")
    return digest.hexdigest()


def quality_implementation_hash() -> str:
    return implementation_files_hash(QUALITY_IMPLEMENTATION_FILES)


def text_segmentation_implementation_hash() -> str:
    return implementation_files_hash(TEXT_SEGMENTATION_IMPLEMENTATION_FILES)


def analysis_casting_implementation_hash() -> str:
    return implementation_files_hash(ANALYSIS_CASTING_IMPLEMENTATION_FILES)


def build_quality_policy(settings: dict[str, Any]) -> dict[str, Any]:
    return {
        "policy_version": QUALITY_POLICY_VERSION,
        "implementation_hash": quality_implementation_hash(),
        "stage_fingerprints": {
            TEXT_SEGMENTATION_STAGE: text_segmentation_implementation_hash(),
            ANALYSIS_CASTING_STAGE: analysis_casting_implementation_hash(),
        },
        "settings_hash": settings_hash(settings),
        "algorithms": {
            "text_parser": "spoken_token_invariant_v2",
            "casting": "canonical_identity_gender_gate_v2",
            "segment_signal": "signal_gate_v2",
            "asr_content": "three_state_double_decode_cer_v2",
            "chapter_mastering": "two_pass_loudnorm_full_decode_v1",
        },
        "settings": {
            "quality_profile": settings["quality_profile"],
            "tts": {
                "sample_rate": settings["tts"]["sample_rate"],
                "min_rms": settings["tts"]["min_rms"],
                "max_clipping_fraction": settings["tts"]["max_clipping_fraction"],
            },
            "asr": {
                "model": settings["asr"]["model"],
                "required": settings["asr"]["required"],
                "beam_size": settings["asr"]["beam_size"],
                "min_similarity": settings["asr"]["min_similarity"],
                "max_wer": settings["asr"]["max_wer"],
                "repair_rounds": settings["asr"]["repair_rounds"],
                "failure_policy": settings["asr"]["failure_policy"],
            },
            "audio": {
                "mp3_bitrate": settings["audio"]["mp3_bitrate"],
                "loudness_lufs": settings["audio"]["loudness_lufs"],
                "true_peak_db": settings["audio"]["true_peak_db"],
                "lra": settings["audio"]["lra"],
            },
        },
    }


def quality_policy_hash(policy: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json(policy).encode("utf-8")).hexdigest()
