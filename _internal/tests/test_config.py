from __future__ import annotations

import pytest

from ebook_reader.config import (
    DIRECTOR_CRITIC_SETTING_KEYS,
    build_settings,
    load_settings,
    normalize_legacy_locked_settings,
    settings_hash,
    validate_settings,
)


def test_unattended_safety_defaults() -> None:
    settings = build_settings("balanced")
    assert settings["interactive_prompts"] is False
    assert settings["safety"]["never_prompt_during_run"] is True
    assert settings["tts"]["allow_silent_replacement"] is False
    assert "combine_full_book" not in settings["audio"]
    assert "keep_verified_wav" not in settings["audio"]
    assert settings["voices"]["narrator_gender"] == "male"
    assert settings["voices"]["narrator_voice"] == "Phạm Tuyên"
    assert settings["voices"]["max_character_pitch_semitones"] == 2
    assert settings["asr"]["enabled"] is True
    assert settings["asr"]["required"] is True
    assert settings["asr"]["failure_policy"] == "fail"
    assert settings["perceptual_qa"]["enabled"] is False

    high_quality = build_settings("high_quality")
    assert high_quality["analysis"]["director_critic_enabled"] is True
    assert high_quality["analysis"]["director_critic_required"] is True
    assert high_quality["analysis"]["director_confidence_cap"] == 0.95
    assert high_quality["analysis"]["low_confidence_policy"] == "fail"
    assert high_quality["perceptual_qa"]["enabled"] is True
    assert high_quality["perceptual_qa"]["failure_policy"] == "fail"
    assert high_quality["perceptual_qa"]["repair_rounds"] == 2
    # Live calibration: sub-1.5 s expressive phrases produced false MOS outliers,
    # while mandatory Whisper still verifies their spoken content.
    assert high_quality["perceptual_qa"]["minimum_duration_seconds"] == 1.5


def test_negative_perceptual_repair_rounds_are_rejected() -> None:
    with pytest.raises(ValueError, match="perceptual_qa.repair_rounds"):
        build_settings(overrides={"perceptual_qa": {"repair_rounds": -1}})


def test_narrator_gender_selects_a_safe_default_voice() -> None:
    settings = build_settings(overrides={"voices": {"narrator_gender": "female"}})

    assert settings["voices"]["narrator_gender"] == "female"
    assert settings["voices"]["narrator_voice"] == "Ngọc Linh"


def test_unknown_narrator_gender_is_rejected_cleanly() -> None:
    with pytest.raises(ValueError, match="Unsupported voices.narrator_gender"):
        build_settings(overrides={"voices": {"narrator_gender": "unknown"}})


def test_news_presets_are_rejected_but_regional_narrators_are_allowed() -> None:
    with pytest.raises(ValueError, match="cannot use a news voice"):
        build_settings(overrides={"voices": {"narrator_voice": "Minh Đức"}})

    settings = build_settings(overrides={"voices": {"narrator_voice": "Ngọc Trân"}})
    assert settings["voices"]["narrator_gender"] == "female"
    assert settings["voices"]["narrator_voice"] == "Ngọc Trân"


def test_silent_replacement_is_rejected() -> None:
    settings = build_settings()
    settings["tts"]["allow_silent_replacement"] = True
    with pytest.raises(ValueError):
        validate_settings(settings)


@pytest.mark.parametrize(
    "minimum,maximum",
    [
        (0.0, 13.0),
        (2.1, 2.1),
        (4.0, 3.0),
        (float("nan"), 13.0),
        (2.1, float("inf")),
    ],
)
def test_invalid_tts_duration_bounds_are_rejected(minimum: float, maximum: float) -> None:
    with pytest.raises(ValueError, match="duration bounds"):
        build_settings(overrides={
            "tts": {
                "min_seconds_per_100_chars": minimum,
                "max_seconds_per_100_chars": maximum,
            },
        })


def test_remote_analysis_requires_explicit_opt_in() -> None:
    with pytest.raises(ValueError, match="allow_remote_analysis"):
        build_settings(overrides={"analysis": {"base_url": "https://example.com"}})

    settings = build_settings(overrides={
        "analysis": {"base_url": "https://example.com"},
        "safety": {"allow_remote_analysis": True},
    })
    assert settings["safety"]["allow_remote_analysis"] is True


@pytest.mark.parametrize("model", ["qwen3", "qwen3:", ":8b", "qwen3:latest extra"])
def test_analysis_model_requires_an_explicit_canonical_tag(model: str) -> None:
    with pytest.raises(ValueError, match="canonical name:tag"):
        build_settings(overrides={"analysis": {"model": model}})


def test_required_asr_cannot_be_disabled_or_downgraded_to_warning() -> None:
    with pytest.raises(ValueError, match="cannot be disabled"):
        build_settings(overrides={"asr": {"enabled": False}})

    with pytest.raises(ValueError, match="failure_policy=fail"):
        build_settings(overrides={"asr": {"failure_policy": "warning_continue"}})

    settings = build_settings(profile="balanced", overrides={
        "asr": {
            "enabled": False,
            "required": False,
            "failure_policy": "warning_continue",
        }
    })
    assert settings["asr"]["enabled"] is False

    with pytest.raises(ValueError, match="high_quality requires enabled mandatory ASR"):
        build_settings(overrides={
            "asr": {
                "enabled": False,
                "required": False,
                "failure_policy": "warning_continue",
            }
        })


def test_high_quality_requires_mandatory_analysis() -> None:
    with pytest.raises(ValueError, match="mandatory book analysis"):
        build_settings(overrides={"analysis": {"enabled": False, "required": False}})

    with pytest.raises(ValueError, match="analysis director critic"):
        build_settings(overrides={"analysis": {"director_critic_enabled": False}})

    with pytest.raises(ValueError, match="low_confidence_policy=fail"):
        build_settings(overrides={"analysis": {"low_confidence_policy": "auto_with_warning"}})


def test_legacy_locked_settings_are_normalized_in_memory_without_changing_raw_hash(
    tmp_path,
) -> None:
    legacy = build_settings()
    for key in DIRECTOR_CRITIC_SETTING_KEYS:
        legacy["analysis"].pop(key)
    original_hash = settings_hash(legacy)
    path = tmp_path / "book_settings.json"
    path.write_text(__import__("json").dumps(legacy, ensure_ascii=False), encoding="utf-8")

    loaded = load_settings(path)
    effective = normalize_legacy_locked_settings(loaded)

    assert settings_hash(loaded) == original_hash
    assert DIRECTOR_CRITIC_SETTING_KEYS.isdisjoint(loaded["analysis"])
    assert effective["analysis"]["director_critic_enabled"] is True
    assert effective["analysis"]["director_critic_required"] is True
    assert effective["analysis"]["low_confidence_policy"] == "fail"
    assert settings_hash(legacy) == original_hash


def test_partially_missing_director_settings_are_not_treated_as_legacy() -> None:
    settings = build_settings()
    settings["analysis"].pop("director_confidence_cap")

    with pytest.raises(ValueError, match="Missing analysis director critic settings"):
        validate_settings(normalize_legacy_locked_settings(settings))
