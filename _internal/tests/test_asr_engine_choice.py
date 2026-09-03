"""Two runtimes, one interface: nothing downstream learns which one answered.

faster-whisper runs the same large-v3-turbo weights through CTranslate2 and measured 2.07x
against openai-whisper with zero verdict disagreements over 200 takes. Adding it is a
version event, so it is opt-in - and the point of the adapter is that choosing it changes
the speed and nothing else. The transcript, the timeline evidence and the beam rule all
have to come out identical in shape.
"""
from __future__ import annotations

import numpy as np
import pytest

from ebook_reader.asr import WhisperVerifier


class _FasterSegment:
    def __init__(self, text: str, start: float, end: float) -> None:
        self.text = text
        self.start = start
        self.end = end


class _FasterModel:
    """Stands in for faster_whisper.WhisperModel and records the decode it was asked for."""

    def __init__(self, segments: list[_FasterSegment]) -> None:
        self.segments = segments
        self.calls: list[dict] = []

    def transcribe(self, _audio, **options):
        self.calls.append(dict(options))
        return iter(self.segments), object()


def _verifier(segments: list[_FasterSegment], **asr_overrides):
    settings = {
        "asr": {"enabled": True, "device": "cpu", "engine": "faster", **asr_overrides},
        "safety": {},
    }
    verifier = WhisperVerifier(settings, lambda _message: None)
    model = _FasterModel(segments)
    verifier.model = model
    return verifier, model


def _decode(verifier: WhisperVerifier, seconds: float, *, confirmation: bool = False) -> str:
    return verifier._transcribe_audio(
        np.zeros(int(16_000 * seconds), dtype="float32"),
        seconds,
        confirmation=confirmation,
    )


def test_the_engine_must_be_one_of_the_two() -> None:
    with pytest.raises(ValueError, match="asr.engine"):
        WhisperVerifier(
            {"asr": {"engine": "whatever"}, "safety": {}}, lambda _message: None
        )


def test_openai_is_what_a_project_gets_unless_it_asks(monkeypatch) -> None:
    """Every run so far used it, and a settings file that says nothing must keep it."""
    verifier = WhisperVerifier({"asr": {}, "safety": {}}, lambda _message: None)
    assert verifier.engine == "openai"


def test_the_pieces_are_joined_into_one_transcript() -> None:
    verifier, _model = _verifier(
        [_FasterSegment("Hắn là", 0.0, 1.0), _FasterSegment(" hoàng tử.", 1.0, 2.0)]
    )
    assert _decode(verifier, 2.0) == "Hắn là hoàng tử."


def test_a_transcript_running_past_the_audio_is_still_caught() -> None:
    """The hallucination signal must survive the runtime change: a decoder that wanders
    off the end of the file reports timestamps the file cannot contain."""
    verifier, _model = _verifier([_FasterSegment("một câu rất dài", 0.0, 40.0)])
    _decode(verifier, 2.0)
    assert verifier._last_transcription_timeline_impossible is True

    verifier, _model = _verifier([_FasterSegment("ngắn thôi", 0.0, 1.5)])
    _decode(verifier, 2.0)
    assert verifier._last_transcription_timeline_impossible is False


def test_the_beam_rule_travels_with_the_transcript_not_with_the_runtime() -> None:
    """beam_minimum_seconds was measured on openai-whisper, and the reason for it - beam
    inventing boilerplate on short audio - is a property of beam search, not of a runtime."""
    verifier, model = _verifier([_FasterSegment("dài", 0.0, 1.0)], beam_size=5)
    _decode(verifier, 10.0)
    assert model.calls[-1]["beam_size"] == 5

    verifier, model = _verifier([_FasterSegment("ngắn", 0.0, 0.5)], beam_size=5)
    _decode(verifier, 1.0)
    assert model.calls[-1]["beam_size"] == 1, "greedy is beam_size 1 here, not an absent argument"


def test_the_confirmation_pass_is_greedy_here_too() -> None:
    verifier, model = _verifier([_FasterSegment("x", 0.0, 1.0)], beam_size=5)
    _decode(verifier, 30.0, confirmation=True)
    assert model.calls[-1]["beam_size"] == 1


def test_language_and_temperature_are_passed_through_unchanged() -> None:
    verifier, model = _verifier([_FasterSegment("x", 0.0, 1.0)])
    _decode(verifier, 5.0)
    options = model.calls[-1]
    assert options["language"] == "vi"
    assert options["temperature"] == 0.0
    assert options["condition_on_previous_text"] is False
