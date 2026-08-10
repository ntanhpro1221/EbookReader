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


def test_quality_policy_hash_is_stable_and_changes_with_content_thresholds() -> None:
    settings = build_settings()
    first = build_quality_policy(settings)
    second = build_quality_policy(build_settings())

    assert quality_policy_hash(first) == quality_policy_hash(second)

    changed = build_settings(overrides={"asr": {"min_similarity": 0.91}})
    assert quality_policy_hash(first) != quality_policy_hash(build_quality_policy(changed))


def test_quality_policy_fingerprints_every_critical_implementation_file() -> None:
    assert "pipeline.py" in QUALITY_IMPLEMENTATION_FILES
    assert "audio_io.py" in QUALITY_IMPLEMENTATION_FILES
    assert "database.py" in QUALITY_IMPLEMENTATION_FILES
    assert "recovery.py" in QUALITY_IMPLEMENTATION_FILES
    assert "voice_catalog.py" in QUALITY_IMPLEMENTATION_FILES
    assert "../pyproject.toml" in QUALITY_IMPLEMENTATION_FILES
    assert "../uv.lock" in QUALITY_IMPLEMENTATION_FILES
    assert len(quality_implementation_hash()) == 64


def test_quality_policy_has_separate_parser_and_casting_fingerprints() -> None:
    policy = build_quality_policy(build_settings())

    assert TEXT_SEGMENTATION_IMPLEMENTATION_FILES == ("text_processing.py",)
    assert "analysis.py" in ANALYSIS_CASTING_IMPLEMENTATION_FILES
    assert "voice_catalog.py" in ANALYSIS_CASTING_IMPLEMENTATION_FILES
    assert policy["stage_fingerprints"][TEXT_SEGMENTATION_STAGE] == (
        text_segmentation_implementation_hash()
    )
    assert policy["stage_fingerprints"][ANALYSIS_CASTING_STAGE] == (
        analysis_casting_implementation_hash()
    )
