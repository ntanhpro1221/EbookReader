from __future__ import annotations

import sys
from types import SimpleNamespace
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from ebook_reader.asr import WhisperVerifier, is_asr_repair_candidate
from ebook_reader.config import build_settings


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


def test_whisper_receives_in_process_resampled_audio(tmp_path: Path) -> None:
    sample_rate = 48_000
    timeline = np.arange(sample_rate, dtype=np.float32) / sample_rate
    source = 0.1 * np.sin(2 * np.pi * 220 * timeline)
    wav = tmp_path / "speech.wav"
    sf.write(wav, source, sample_rate)

    received = {}

    class FakeModel:
        def transcribe(self, audio, **kwargs):
            received["audio"] = audio
            received["kwargs"] = kwargs
            return {"text": "xin chào"}

    verifier = WhisperVerifier(build_settings(), lambda _message: None)
    verifier.model = FakeModel()
    verifier.device = "cpu"

    assert verifier.transcribe(wav) == "xin chào"
    assert isinstance(received["audio"], np.ndarray)
    assert received["audio"].ndim == 1
    assert abs(len(received["audio"]) - 16_000) <= 1
    assert received["kwargs"]["fp16"] is False
