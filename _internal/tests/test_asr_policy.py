from __future__ import annotations

import sys
from types import SimpleNamespace
from pathlib import Path

import pytest

from e_book_reader.asr import WhisperVerifier, is_asr_repair_candidate
from e_book_reader.config import build_settings


def test_optional_asr_inference_error_becomes_warning(monkeypatch) -> None:
    messages: list[str] = []
    verifier = WhisperVerifier(build_settings(), messages.append)
    verifier.model = object()
    monkeypatch.setattr(verifier, "load", lambda: True)
    monkeypatch.setattr(verifier, "transcribe", lambda _path: (_ for _ in ()).throw(RuntimeError("GPU error")))

    result = verifier.verify("Một câu cần kiểm tra.", Path("missing.wav"))

    assert result["reason"] == "ASR_ERROR"
    assert result["passed"] is True
    assert any("GPU error" in message for message in messages)


def test_asr_fail_policy_rejects_missing_model_cache(monkeypatch, tmp_path: Path) -> None:
    settings = build_settings(
        overrides={
            "asr": {
                "download_root": str(tmp_path),
                "failure_policy": "fail",
            }
        }
    )
    fake_torch = SimpleNamespace(cuda=SimpleNamespace(is_available=lambda: True))
    fake_whisper = SimpleNamespace(_MODELS={"turbo": "https://models.invalid/turbo.pt"})
    monkeypatch.setitem(sys.modules, "torch", fake_torch)
    monkeypatch.setitem(sys.modules, "whisper", fake_whisper)
    verifier = WhisperVerifier(settings, lambda _message: None)

    with pytest.raises(RuntimeError, match="Thiếu Whisper"):
        verifier.load()


def test_non_lexical_text_skips_whisper_and_one_word_is_not_repaired(monkeypatch) -> None:
    verifier = WhisperVerifier(build_settings(), lambda _message: None)
    monkeypatch.setattr(
        verifier,
        "load",
        lambda: (_ for _ in ()).throw(AssertionError("Whisper should not load")),
    )

    result = verifier.verify("……", Path("missing.wav"))

    assert result["passed"] is True
    assert result["reason"] == "NON_LEXICAL_SKIP"
    assert result["repairable"] is False
    assert is_asr_repair_candidate("rầm") is False
    assert is_asr_repair_candidate("Cánh cửa đổ rầm xuống.") is True
