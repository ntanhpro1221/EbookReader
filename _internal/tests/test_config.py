from __future__ import annotations

import pytest

from e_book_reader.config import build_settings, hydrate_settings, validate_settings


def test_unattended_safety_defaults() -> None:
    settings = build_settings("balanced")
    assert settings["interactive_prompts"] is False
    assert settings["safety"]["never_prompt_during_run"] is True
    assert settings["tts"]["allow_silent_replacement"] is False
    assert settings["audio"]["combine_full_book"] is False


def test_silent_replacement_is_rejected() -> None:
    settings = build_settings()
    settings["tts"]["allow_silent_replacement"] = True
    with pytest.raises(ValueError):
        validate_settings(settings)


def test_legacy_tts_failure_policy_remains_resume_compatible() -> None:
    settings = build_settings()
    settings["tts"]["failure_policy"] = "retry_split_fallback_fail"
    settings["tts"].pop("pace_chars_per_second")
    settings["tts"].pop("rate_check_min_chars")

    hydrated = hydrate_settings(settings)

    assert hydrated["tts"]["failure_policy"] == "retry_split_fallback_fail"
    assert hydrated["tts"]["pace_chars_per_second"]["normal"] == [10.5, 22.0]
    assert hydrated["tts"]["rate_check_min_chars"] == 24


def test_remote_analysis_requires_explicit_opt_in() -> None:
    with pytest.raises(ValueError, match="allow_remote_analysis"):
        build_settings(overrides={"analysis": {"base_url": "https://example.com"}})

    settings = build_settings(overrides={
        "analysis": {"base_url": "https://example.com"},
        "safety": {"allow_remote_analysis": True},
    })
    assert settings["safety"]["allow_remote_analysis"] is True
