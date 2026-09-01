"""Accepting a worker's take, and choosing which segments to hand it.

The pool is a speed feature; these pin the two places where it could quietly damage a book
instead - committing audio the ledger describes wrongly, and reading ahead past a decision
the loop has not made yet.
"""

from __future__ import annotations

import hashlib
from typing import Any

import pytest

from ebook_reader.pipeline import BookPipeline


class FakeTTS:
    def __init__(self, seed: int = 4242) -> None:
        self.seed = seed

    def generation_seed(self, _row: Any, _salt: str) -> int:
        return self.seed


class Claimer:
    """The smallest object _claim_prefetched_segment needs."""

    def __init__(self, seed: int = 4242) -> None:
        self.tts = FakeTTS(seed)

    claim = BookPipeline._claim_prefetched_segment


@pytest.fixture()
def take(tmp_path):
    wav = tmp_path / "0001.wav"
    wav.write_bytes(b"RIFF....WAVEfmt ")
    checksum = hashlib.sha256(wav.read_bytes()).hexdigest()
    return wav, {
        "stable_id": "seg-1",
        "checksum": checksum,
        "seed": 4242,
        "metrics": {"duration": 3.0},
    }


def test_a_matching_take_is_accepted(take) -> None:
    wav, prefetched = take
    result = Claimer().claim(prefetched, {"stable_id": "seg-1"}, wav, "primary_0")
    assert result is not None
    checksum, metrics, seed = result
    assert (checksum, seed) == (prefetched["checksum"], 4242)
    assert metrics == {"duration": 3.0}
    assert metrics is not prefetched["metrics"], "must not hand out the worker's own dict"


def test_a_take_for_another_segment_is_declined(take) -> None:
    wav, prefetched = take
    assert Claimer().claim(prefetched, {"stable_id": "seg-2"}, wav, "primary_0") is None


def test_a_take_from_a_different_seed_is_declined(take) -> None:
    """The seed decides the audio; a mismatch means this is not this attempt's take."""
    wav, prefetched = take
    assert Claimer(seed=9999).claim(prefetched, {"stable_id": "seg-1"}, wav, "primary_0") is None


def test_a_take_whose_file_was_changed_is_declined(take) -> None:
    wav, prefetched = take
    wav.write_bytes(b"something else entirely")
    assert Claimer().claim(prefetched, {"stable_id": "seg-1"}, wav, "primary_0") is None


def test_a_take_whose_file_is_missing_is_declined(take) -> None:
    wav, prefetched = take
    wav.unlink()
    assert Claimer().claim(prefetched, {"stable_id": "seg-1"}, wav, "primary_0") is None


def test_a_failed_take_is_declined(take) -> None:
    wav, prefetched = take
    assert Claimer().claim({"error": "boom"}, {"stable_id": "seg-1"}, wav, "primary_0") is None
    assert Claimer().claim(None, {"stable_id": "seg-1"}, wav, "primary_0") is None


def test_a_take_without_metrics_is_declined(take) -> None:
    wav, prefetched = take
    for broken in ({**prefetched, "metrics": None}, {**prefetched, "checksum": ""}):
        assert Claimer().claim(broken, {"stable_id": "seg-1"}, wav, "primary_0") is None


class Scanner:
    """The smallest object _next_plain_tts_rows needs."""

    def __init__(self, plain: set[str], limit: int = 9) -> None:
        self.plain = plain
        self.settings = {"tts": {"parallel_batch_size": limit}}

    def _segment_takes_plain_tts_path(self, row: Any) -> bool:
        return str(row["stable_id"]) in self.plain

    scan = BookPipeline._next_plain_tts_rows


def _rows(*names: str) -> list[dict[str, str]]:
    return [{"stable_id": name} for name in names]


def test_the_batch_stops_at_a_segment_that_needs_something_else() -> None:
    rows = _rows("a", "b", "repair", "c")
    scanner = Scanner({"a", "b", "c"})
    assert [row["stable_id"] for row in scanner.scan(rows, 0)] == ["a", "b"]


def test_the_batch_is_capped_at_the_configured_size() -> None:
    rows = _rows(*[str(index) for index in range(20)])
    scanner = Scanner({str(index) for index in range(20)}, limit=4)
    assert len(scanner.scan(rows, 0)) == 4


def test_scanning_starts_where_the_loop_is() -> None:
    rows = _rows("a", "b", "c")
    scanner = Scanner({"a", "b", "c"})
    assert [row["stable_id"] for row in scanner.scan(rows, 1)] == ["b", "c"]


def test_a_batch_is_never_smaller_than_the_measured_minimum() -> None:
    """Two segments measured 1.00x warm while holding three times the VRAM, so a batch
    configured below TTS_POOL_MIN_BATCH would run a pool for no gain at all."""
    from ebook_reader.tts_pool import TTS_POOL_MIN_BATCH

    rows = _rows("a", "b", "c", "d")
    assert len(Scanner({"a", "b", "c", "d"}, limit=1).scan(rows, 0)) == TTS_POOL_MIN_BATCH


def test_nothing_to_do_yields_an_empty_batch() -> None:
    assert Scanner(set()).scan(_rows("a", "b"), 0) == []
    assert Scanner({"a"}).scan(_rows("a"), 1) == []
