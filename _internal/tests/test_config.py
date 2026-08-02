from __future__ import annotations

import pytest

from e_book_reader.config import build_settings, validate_settings


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


def test_narrator_gender_selects_a_safe_default_voice() -> None:
    settings = build_settings(overrides={"voices": {"narrator_gender": "female"}})

    assert settings["voices"]["narrator_gender"] == "female"
    assert settings["voices"]["narrator_voice"] == "Ngọc Linh"


def test_unknown_narrator_gender_is_rejected_cleanly() -> None:
    with pytest.raises(ValueError, match="Unsupported voices.narrator_gender"):
        build_settings(overrides={"voices": {"narrator_gender": "unknown"}})


def test_news_and_regional_presets_are_rejected_for_narrator() -> None:
    with pytest.raises(ValueError, match="standard natural or storytelling"):
        build_settings(overrides={"voices": {"narrator_voice": "Minh Đức"}})

    with pytest.raises(ValueError, match="standard natural or storytelling"):
        build_settings(overrides={"voices": {"narrator_voice": "Ngọc Trân"}})


def test_silent_replacement_is_rejected() -> None:
    settings = build_settings()
    settings["tts"]["allow_silent_replacement"] = True
    with pytest.raises(ValueError):
        validate_settings(settings)


def test_remote_analysis_requires_explicit_opt_in() -> None:
    with pytest.raises(ValueError, match="allow_remote_analysis"):
        build_settings(overrides={"analysis": {"base_url": "https://example.com"}})

    settings = build_settings(overrides={
        "analysis": {"base_url": "https://example.com"},
        "safety": {"allow_remote_analysis": True},
    })
    assert settings["safety"]["allow_remote_analysis"] is True
