"""A one-second hole in chapter 8, and nothing in the pipeline could shorten it.

alpha.48 chapter 8 failed the post-encode check on "unexpected silence 1.02s". The 1.02 is
one take's own leading silence, sitting in front of the 0.38s break and behind the previous
take's 0.17s tail - 1.57s of dead air in the middle of a chapter.

Nothing was wrong with the reading. Identical text, identical spoken form, a different
generation seed, and a line that opens on an ellipsis: alpha.46 drew 0.51s of lead-in for
the same sentence and alpha.47 drew 1.02s. So a retry is not a cure - the previous seed was
over the line too - and removing the pause outright would flatten a hesitation the ellipsis
is asking for. The assembler caps it instead.

Measured over 841 takes of alpha.48: leading silence p50 0.11s, p99 0.22s, and exactly two
takes above 0.5s.

The trailing edge is the one that fires in practice, and I understated it here at first. Its
p99 is 0.23s but its maximum is 0.44s, so takes above the 0.35s cap turn up occasionally
rather than almost never: over alpha.50's first four chapters the cap trimmed one take, by
0.07s. The chapter's own longest-silence measurement was unchanged by that trim, which is the
intervention behaving exactly as designed - small, local, and not disturbing the number it
exists to protect.
"""
from __future__ import annotations

import numpy as np
import soundfile as sf
import pytest

from ebook_reader.audio_io import (
    SEGMENT_EDGE_SILENCE_CAP_SECONDS,
    _cap_segment_edge_silence,
    _edge_silence_seconds,
)

RATE = 24000


def _tone(seconds: float) -> np.ndarray:
    t = np.linspace(0, seconds, int(RATE * seconds), endpoint=False)
    return (0.3 * np.sin(2 * np.pi * 220 * t)).astype(np.float32)


def _take(path, *, lead: float, speech: float, trail: float):
    audio = np.concatenate(
        [
            np.zeros(int(RATE * lead), dtype=np.float32),
            _tone(speech),
            np.zeros(int(RATE * trail), dtype=np.float32),
        ]
    )
    sf.write(path, audio, RATE, subtype="PCM_16")
    return path


def test_edges_are_measured_against_the_chapter_floor(tmp_path):
    path = _take(tmp_path / "a.wav", lead=0.5, speech=1.0, trail=0.3)
    audio, rate = sf.read(path, dtype="float32")
    leading, trailing = _edge_silence_seconds(audio, rate)
    assert leading == pytest.approx(0.5, abs=0.03)
    assert trailing == pytest.approx(0.3, abs=0.03)


def test_an_ordinary_take_is_passed_through_untouched(tmp_path):
    """p99 of a real book is 0.22s. The cap must be a path nothing ordinary takes."""
    path = _take(tmp_path / "a.wav", lead=0.12, speech=1.0, trail=0.18)
    entries, trimmed = _cap_segment_edge_silence([(path, 380)], RATE, tmp_path / "work")

    assert entries == [(path, 380)]
    assert trimmed == []


def test_the_chapter_8_lead_in_is_capped(tmp_path):
    """The take that failed the chapter: 1.02s of dead air before the first word."""
    path = _take(tmp_path / "a.wav", lead=1.02, speech=1.4, trail=0.17)
    entries, trimmed = _cap_segment_edge_silence([(path, 380)], RATE, tmp_path / "work")

    assert entries[0][0] != path, "the assembler must not use the untrimmed take"
    audio, rate = sf.read(entries[0][0], dtype="float32")
    leading, _trailing = _edge_silence_seconds(audio, rate)
    assert leading == pytest.approx(SEGMENT_EDGE_SILENCE_CAP_SECONDS, abs=0.03)
    assert trimmed[0]["leading_silence_seconds"] == pytest.approx(1.02, abs=0.03)


def test_the_break_still_reads_as_a_hesitation(tmp_path):
    """Capping, not removing. 0.35s in front of a 0.38s break is still a pause."""
    path = _take(tmp_path / "a.wav", lead=1.02, speech=1.0, trail=0.0)
    entries, _trimmed = _cap_segment_edge_silence([(path, 380)], RATE, tmp_path / "work")

    audio, rate = sf.read(entries[0][0], dtype="float32")
    leading, _ = _edge_silence_seconds(audio, rate)
    assert leading + 0.38 > 0.7


def test_a_capped_chapter_stays_under_the_one_second_limit(tmp_path):
    """tail + break + head is what the listener hears, and what the check measures."""
    first = _take(tmp_path / "a.wav", lead=0.10, speech=1.0, trail=0.17)
    second = _take(tmp_path / "b.wav", lead=1.02, speech=1.0, trail=0.12)
    entries, _trimmed = _cap_segment_edge_silence(
        [(first, 380), (second, 380)], RATE, tmp_path / "work"
    )

    _lead_a, tail = _edge_silence_seconds(*sf.read(entries[0][0], dtype="float32"))
    head, _trail_b = _edge_silence_seconds(*sf.read(entries[1][0], dtype="float32"))
    assert tail + 0.38 + head < 1.0


def test_the_take_on_disk_is_never_modified(tmp_path):
    """Its checksum is the key half the evidence in this project is filed under."""
    path = _take(tmp_path / "a.wav", lead=1.02, speech=1.0, trail=0.6)
    before = path.read_bytes()

    _cap_segment_edge_silence([(path, 380)], RATE, tmp_path / "work")

    assert path.read_bytes() == before


def test_a_take_that_is_all_silence_is_left_alone(tmp_path):
    """Trimming both edges of a silent take would compute a negative span."""
    sf.write(tmp_path / "a.wav", np.zeros(int(RATE * 1.5), dtype=np.float32), RATE, subtype="PCM_16")
    entries, trimmed = _cap_segment_edge_silence([(tmp_path / "a.wav", 380)], RATE, tmp_path / "w")

    assert entries[0][0] == tmp_path / "a.wav"
    assert trimmed == []
