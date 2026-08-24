from __future__ import annotations

from ebook_reader.config import build_settings
from ebook_reader.quality_policy import (
    ANALYSIS_CASTING_IMPLEMENTATION_FILES,
    ANALYSIS_CASTING_STAGE,
    QUALITY_IMPLEMENTATION_FILES,
    TEXT_SEGMENTATION_IMPLEMENTATION_FILES,
    TEXT_SEGMENTATION_STAGE,
    analysis_casting_implementation_hash,
    build_quality_policy,
    quality_implementation_hash,
    quality_policy_hash,
    text_segmentation_implementation_hash,
)
from ebook_reader.runtime_contract import (
    CRITICAL_RUNTIME_DISTRIBUTIONS,
    TIMM_CACHE_REVISION,
    WAV2VEC2_CACHE_REVISION,
    installed_dependency_provenance,
)


def test_quality_policy_hash_is_stable_and_changes_with_content_thresholds() -> None:
    settings = build_settings()
    first = build_quality_policy(settings)
    second = build_quality_policy(build_settings())

    assert quality_policy_hash(first) == quality_policy_hash(second)

    changed = build_settings(overrides={"asr": {"min_similarity": 0.91}})
    assert quality_policy_hash(first) != quality_policy_hash(build_quality_policy(changed))
    assert first["algorithms"]["asr_content"] == (
        "evidence_gated_name_pronunciation_delivery_v8"
    )


def test_quality_policy_fingerprints_every_critical_implementation_file() -> None:
    assert "pipeline.py" in QUALITY_IMPLEMENTATION_FILES
    assert "audio_io.py" in QUALITY_IMPLEMENTATION_FILES
    assert "database.py" in QUALITY_IMPLEMENTATION_FILES
    assert "recovery.py" in QUALITY_IMPLEMENTATION_FILES
    assert "runtime_contract.py" in QUALITY_IMPLEMENTATION_FILES
    assert "voice_catalog.py" in QUALITY_IMPLEMENTATION_FILES
    assert "../pyproject.toml" in QUALITY_IMPLEMENTATION_FILES
    assert "../uv.lock" in QUALITY_IMPLEMENTATION_FILES
    assert len(quality_implementation_hash()) == 64


def test_quality_policy_locks_installed_dependency_versions_and_direct_urls() -> None:
    policy = build_quality_policy(build_settings())

    assert policy["runtime_dependencies"] == installed_dependency_provenance()
    assert set(policy["runtime_dependencies"]) == set(CRITICAL_RUNTIME_DISTRIBUTIONS)
    for evidence in policy["runtime_dependencies"].values():
        assert set(evidence) == {"version", "direct_url"}


def test_quality_policy_has_separate_parser_and_casting_fingerprints() -> None:
    policy = build_quality_policy(build_settings())

    assert ANALYSIS_CASTING_STAGE == "analysis_casting_v27"
    assert policy["algorithms"]["casting"] == (
        "canonical_identity_host_semantic_lock_director_ledger_v28"
    )
    assert TEXT_SEGMENTATION_IMPLEMENTATION_FILES == ("text_processing.py",)
    assert "analysis.py" in ANALYSIS_CASTING_IMPLEMENTATION_FILES
    assert "voice_catalog.py" in ANALYSIS_CASTING_IMPLEMENTATION_FILES
    assert policy["stage_fingerprints"][TEXT_SEGMENTATION_STAGE] == (
        text_segmentation_implementation_hash()
    )
    assert policy["stage_fingerprints"][ANALYSIS_CASTING_STAGE] == (
        analysis_casting_implementation_hash()
    )
    assert policy["settings"]["perceptual_qa"]["wav2vec2_revision"] == (
        WAV2VEC2_CACHE_REVISION
    )
    assert policy["settings"]["perceptual_qa"]["timm_backbone_revision"] == (
        TIMM_CACHE_REVISION
    )
    assert policy["settings"]["perceptual_qa"]["repair_rounds"] == 2
    assert policy["settings"]["asr"]["repair_rounds"] == 5
