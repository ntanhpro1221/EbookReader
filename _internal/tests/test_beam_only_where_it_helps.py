"""The primary decode uses beam search only where beam search earns it.

Beam carries several hypotheses and keeps the most likely sequence. On audio with little
content in it the most likely sequence is boilerplate, and Whisper's boilerplate is
YouTube's: asked to transcribe a two-syllable "Hờ.", beam answered "Hãy subscribe cho kênh
Để không bỏ lỡ những video hấp dẫn".

Measured on alpha.25's own takes. Of 120 shorter than 2.5 seconds, the two decodes flipped
the verdict on three, all three in greedy's favour and none the other way. Over 160 takes
of every length, the only disagreement favouring beam was a full sentence - "rồng" where
greedy heard "dòng". So the search is kept where content supports it and dropped where it
invents content instead.
"""
from __future__ import annotations

from pathlib import Path

from ebook_reader.asr import BEAM_MINIMUM_SECONDS, WhisperVerifier


class _Recorder:
    """Stands in for the Whisper model and reports how it was asked to decode."""

    def __init__(self) -> None:
        self.calls: list[dict] = []

    def transcribe(self, _audio, **options):
        self.calls.append(dict(options))
        return {"text": "xin chào", "segments": []}


def _verifier(**asr_overrides) -> tuple[WhisperVerifier, _Recorder]:
    settings = {"asr": {"enabled": True, "device": "cpu", **asr_overrides}, "safety": {}}
    verifier = WhisperVerifier(settings, lambda _message: None)
    recorder = _Recorder()
    verifier.model = recorder
    return verifier, recorder


def _decode(verifier: WhisperVerifier, seconds: float, *, confirmation: bool = False) -> None:
    import numpy as np

    verifier._transcribe_audio(
        np.zeros(int(16_000 * seconds), dtype="float32"),
        seconds,
        confirmation=confirmation,
    )


def test_a_long_take_still_gets_the_search() -> None:
    verifier, recorder = _verifier(beam_size=5)
    _decode(verifier, BEAM_MINIMUM_SECONDS + 1.0)
    assert recorder.calls[0].get("beam_size") == 5


def test_a_short_take_does_not_get_the_search() -> None:
    """This is the case where beam invented a subscribe button."""
    verifier, recorder = _verifier(beam_size=5)
    _decode(verifier, BEAM_MINIMUM_SECONDS - 1.0)
    assert "beam_size" not in recorder.calls[0]


def test_the_boundary_belongs_to_greedy() -> None:
    """Exactly at the threshold there is no evidence beam helps, and it costs 1.47x."""
    verifier, recorder = _verifier(beam_size=5)
    _decode(verifier, BEAM_MINIMUM_SECONDS)
    assert "beam_size" not in recorder.calls[0]


def test_the_confirmation_decode_is_greedy_at_any_length() -> None:
    """Unchanged: the confirmation pass exists to be a different opinion, not a longer one."""
    verifier, recorder = _verifier(beam_size=5)
    _decode(verifier, 30.0, confirmation=True)
    assert "beam_size" not in recorder.calls[0]


def test_a_project_may_move_the_boundary() -> None:
    verifier, recorder = _verifier(beam_size=5, beam_minimum_seconds=0.0)
    _decode(verifier, 0.5)
    assert recorder.calls[0].get("beam_size") == 5


def test_language_and_temperature_are_untouched_by_any_of_this() -> None:
    verifier, recorder = _verifier(beam_size=5)
    _decode(verifier, 1.0)
    options = recorder.calls[0]
    assert options["language"] == "vi"
    assert options["temperature"] == 0.0
    assert options["condition_on_previous_text"] is False
