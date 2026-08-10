from __future__ import annotations

import pytest

from ebook_reader.config import build_settings, validate_settings


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
