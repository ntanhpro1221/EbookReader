from __future__ import annotations

from pathlib import Path
import numpy as np
import pytest

from e_book_reader.audio_io import (
    AudioQualityError,
    atomic_write_wav,
    assemble_chapter_atomic,
    normalize_segment_level,
    signal_metrics,
    verify_mp3,
    validate_audio_array,
)
from e_book_reader.config import build_settings


def test_real_ffmpeg_chapter_assembly_is_atomic_and_decodable(tmp_path: Path) -> None:
    settings = build_settings(overrides={"tts": {"min_seconds_per_100_chars": 0.2}})
    sample_rate = int(settings["tts"]["sample_rate"])
    entries: list[tuple[Path, int]] = []
    for index, frequency in enumerate((220, 330), start=1):
        timeline = np.arange(int(sample_rate * 0.8), dtype=np.float32) / sample_rate
        audio = 0.12 * np.sin(2 * np.pi * frequency * timeline)
        wav = tmp_path / f"{index}.wav"
        atomic_write_wav(
            wav,
            audio,
            sample_rate,
            "Đây là một câu thử nghiệm đủ dài.",
            settings,
        )
        entries.append((wav, 300 if index == 1 else 0))

    output = tmp_path / "chapter_001.mp3"
    checksum = assemble_chapter_atomic(
        entries,
        output,
        settings,
        title="Chương 1",
        book_title="Sách thử",
        track=1,
        work_dir=tmp_path / "silence",
    )

    assert len(checksum) == 64
    assert verify_mp3(output) == (True, "ok")
    assert not list(tmp_path.rglob("*.part.*"))


def test_stereo_audio_is_rejected_instead_of_flattened() -> None:
    settings = build_settings(overrides={"tts": {"min_seconds_per_100_chars": 0.2}})
    stereo = np.zeros((48_000, 2), dtype=np.float32)

    with pytest.raises(AudioQualityError, match="mono"):
        validate_audio_array(stereo, "Một câu đủ dài để kiểm tra.", settings, 48_000)


def test_segment_leveling_does_not_hide_stereo_or_clipped_model_output(tmp_path: Path) -> None:
    settings = build_settings(overrides={"tts": {"min_seconds_per_100_chars": 0.2}})
    segment = {"pace": "normal", "volume": "normal", "emotion": "neutral", "intensity": 1}
    stereo = np.zeros((48_000, 2), dtype=np.float32)
    clipped = np.ones(48_000, dtype=np.float32)

    with pytest.raises(AudioQualityError, match="mono"):
        atomic_write_wav(tmp_path / "stereo.wav", stereo, 48_000, "Một câu kiểm tra.", settings, segment)
    with pytest.raises(AudioQualityError, match="clipping"):
        atomic_write_wav(tmp_path / "clipped.wav", clipped, 48_000, "Một câu kiểm tra.", settings, segment)


def test_segment_leveling_matches_neutral_voices_and_preserves_loud_intent() -> None:
    settings = build_settings()
    sample_rate = 48_000
    timeline = np.arange(sample_rate, dtype=np.float32) / sample_rate
    quiet = 0.03 * np.sin(2 * np.pi * 220 * timeline)
    strong = 0.20 * np.sin(2 * np.pi * 220 * timeline)
    neutral = {"volume": "normal", "emotion": "neutral", "intensity": 1}
    loud = {"volume": "loud", "emotion": "angry", "intensity": 3}

    quiet_normalized = normalize_segment_level(quiet, sample_rate, neutral, settings)
    strong_normalized = normalize_segment_level(strong, sample_rate, neutral, settings)
    loud_normalized = normalize_segment_level(quiet, sample_rate, loud, settings)
    quiet_db = 20 * np.log10(signal_metrics(quiet_normalized, sample_rate)["rms"])
    strong_db = 20 * np.log10(signal_metrics(strong_normalized, sample_rate)["rms"])
    loud_db = 20 * np.log10(signal_metrics(loud_normalized, sample_rate)["rms"])

    assert quiet_db == pytest.approx(strong_db, abs=0.15)
    assert loud_db > quiet_db + 2.0


def test_segment_rate_validation_rejects_wrong_pace() -> None:
    settings = build_settings(overrides={"tts": {"min_seconds_per_100_chars": 0.2}})
    audio = np.sin(np.linspace(0, 200, 48_000 * 6, dtype=np.float32)) * 0.12
    text = "a" * 60

    with pytest.raises(AudioQualityError, match="speech rate outside normal range"):
        validate_audio_array(
            audio,
            text,
            settings,
            48_000,
            segment={"pace": "normal"},
        )
