from __future__ import annotations

import sys
from types import SimpleNamespace
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from ebook_reader.asr import (
    WhisperVerifier,
    is_asr_repair_candidate,
    is_severe_asr_mismatch,
    transcript_exceeds_physical_rate,
)
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


def test_non_lexical_text_skips_whisper_and_one_word_can_be_repaired(monkeypatch) -> None:
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
    assert is_asr_repair_candidate("rầm") is True
    assert is_asr_repair_candidate("Cánh cửa đổ rầm xuống.") is True


def test_severe_mismatch_detects_impossibly_long_unrelated_transcript() -> None:
    assert is_severe_asr_mismatch(
        "Ha...",
        "Cảm ơn các bạn đã theo dõi và hẹn gặp lại.",
        0.0465,
    ) is True
    assert is_severe_asr_mismatch(
        "Anh Lu-xi-en!",
        "Hãy subscribe cho kênh La La School để không bỏ lỡ những video hấp dẫn.",
        0.22,
    ) is True
    assert is_severe_asr_mismatch("Độc ác quá!", "Nó bạc quá.", 0.60) is False


def test_transcript_word_rate_rejects_whisper_output_that_cannot_fit_the_wav() -> None:
    assert transcript_exceeds_physical_rate(
        "Hãy subscribe cho kênh La La School để không bỏ lỡ những video hấp dẫn.",
        0.88,
    )
    assert not transcript_exceeds_physical_rate("Ha, ha, ho.", 1.60)


@pytest.mark.parametrize(
    ("expected", "transcript", "duration", "reason"),
    [
        (
            "“S… Hự!”",
            "Hãy subscribe cho kênh La La School để không bỏ lỡ những video hấp dẫn",
            0.88,
            "ASR_TRANSCRIPT_RATE_IMPOSSIBLE",
        ),
        (
            "Hức hức hức, hức hức hức…",
            "Hắc hắc hắc, hắc hắc hắc.",
            1.44,
            "VOCALIZATION_ASR_COMPATIBLE",
        ),
        ("“A... a!”", "", 1.20, "VOCALIZATION_ASR_COMPATIBLE"),
    ],
)
def test_vocalization_verification_does_not_blame_tts_for_whisper_hallucination(
    expected: str,
    transcript: str,
    duration: float,
    reason: str,
    tmp_path: Path,
    monkeypatch,
) -> None:
    wav = tmp_path / "vocal.wav"
    sf.write(wav, np.zeros(round(48_000 * duration), dtype=np.float32), 48_000)
    verifier = WhisperVerifier(build_settings(), lambda _message: None)
    verifier.model = object()
    monkeypatch.setattr(verifier, "load", lambda: True)
    monkeypatch.setattr(verifier, "transcribe", lambda _path: transcript)

    result = verifier.verify(expected, wav)

    assert result["passed"] is True
    assert result["repairable"] is False
    assert result["severe"] is False
    assert result["reason"] == reason


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
