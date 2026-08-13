from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from .config import canonical_json, settings_hash
from .runtime_contract import (
    TIMM_CACHE_REVISION,
    WAV2VEC2_CACHE_REVISION,
    installed_dependency_provenance,
)


QUALITY_POLICY_VERSION = 1
HASH_CHUNK_BYTES = 1024 * 1024
CHAPTER_QUALITY_STAGE = "chapter_post_encode_v1"
SEGMENT_CONTENT_STAGE = "segment_asr_content_v1"
TEXT_SEGMENTATION_STAGE = "text_segmentation_v1"
ANALYSIS_CASTING_STAGE = "analysis_casting_v5"
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
    "perceptual_qa.py",
    "quality_policy.py",
    "recovery.py",
    "runtime_contract.py",
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


def external_file_hash(path_value: str) -> str:
    path = Path(path_value).expanduser().resolve()
    if not path.is_file():
        return "MISSING"
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(HASH_CHUNK_BYTES):
            digest.update(chunk)
    return digest.hexdigest()


def voice_preview_assets_hash() -> str:
    preview_root = Path(__file__).resolve().parent / "assets" / "voice_previews"
    digest = hashlib.sha256()
    previews = sorted(preview_root.glob("*.wav"), key=lambda path: path.name.casefold())
    if not previews:
        return "MISSING"
    for preview in previews:
        digest.update(preview.name.encode("utf-8"))
        digest.update(b"\0")
        with preview.open("rb") as handle:
            while chunk := handle.read(HASH_CHUNK_BYTES):
                digest.update(chunk)
        digest.update(b"\0")
    return digest.hexdigest()


def build_quality_policy(settings: dict[str, Any]) -> dict[str, Any]:
    return {
        "policy_version": QUALITY_POLICY_VERSION,
        "implementation_hash": quality_implementation_hash(),
        "stage_fingerprints": {
            TEXT_SEGMENTATION_STAGE: text_segmentation_implementation_hash(),
            ANALYSIS_CASTING_STAGE: analysis_casting_implementation_hash(),
        },
        "settings_hash": settings_hash(settings),
        "runtime_dependencies": installed_dependency_provenance(),
        "algorithms": {
            "text_parser": "spoken_token_invariant_v2",
            "casting": "canonical_identity_host_semantic_lock_director_ledger_v6",
            "segment_signal": "signal_gate_v2",
            "asr_content": "locked_name_anchor_semantic_metrics_clarity_double_decode_v5",
            "perceptual_naturalness": "utmosv2_relative_voice_baseline_v1",
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
            "perceptual_qa": {
                "enabled": settings["perceptual_qa"]["enabled"],
                "failure_policy": settings["perceptual_qa"]["failure_policy"],
                "checkpoint_path": settings["perceptual_qa"]["checkpoint_path"],
                "checkpoint_sha256": external_file_hash(
                    str(settings["perceptual_qa"]["checkpoint_path"])
                ),
                "wav2vec2_revision": WAV2VEC2_CACHE_REVISION,
                "timm_backbone_revision": TIMM_CACHE_REVISION,
                "voice_previews_sha256": voice_preview_assets_hash(),
                "model_config": settings["perceptual_qa"]["model_config"],
                "fold": settings["perceptual_qa"]["fold"],
                "model_seed": settings["perceptual_qa"]["model_seed"],
                "device": settings["perceptual_qa"]["device"],
                "predict_dataset": settings["perceptual_qa"]["predict_dataset"],
                "review_delta": settings["perceptual_qa"]["review_delta"],
                "minimum_duration_seconds": settings["perceptual_qa"][
                    "minimum_duration_seconds"
                ],
                "num_repetitions": settings["perceptual_qa"]["num_repetitions"],
                "repair_rounds": settings["perceptual_qa"]["repair_rounds"],
                "inference_seed": settings["perceptual_qa"]["inference_seed"],
                "remove_silent_section": settings["perceptual_qa"][
                    "remove_silent_section"
                ],
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
