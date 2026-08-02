from __future__ import annotations

from pathlib import Path
import numpy as np
import pytest

from ebook_reader.audio_io import (
    AudioQualityError,
    VIENEU_V3_CODEC_SAMPLES_PER_FRAME,
    atomic_write_wav,
    assemble_chapter_atomic,
    integrated_loudness_lufs,
    normalize_segment_level,
    segment_duration_policy,
    verify_mp3,
    validate_audio_array,
)
from ebook_reader.config import build_settings


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
    neutral = {
        "kind": "dialogue",
        "speaker": "Nhân vật",
        "volume": "normal",
        "emotion": "neutral",
        "intensity": 1,
    }
    narrator = {**neutral, "kind": "narration", "speaker": "NARRATOR"}
    loud = {**neutral, "volume": "loud", "emotion": "angry", "intensity": 3}

    quiet_normalized = normalize_segment_level(quiet, sample_rate, neutral, settings)
    strong_normalized = normalize_segment_level(strong, sample_rate, neutral, settings)
    narrator_normalized = normalize_segment_level(quiet, sample_rate, narrator, settings)
    loud_normalized = normalize_segment_level(quiet, sample_rate, loud, settings)
    quiet_lufs = integrated_loudness_lufs(quiet_normalized, sample_rate)
    strong_lufs = integrated_loudness_lufs(strong_normalized, sample_rate)
    narrator_lufs = integrated_loudness_lufs(narrator_normalized, sample_rate)
    loud_lufs = integrated_loudness_lufs(loud_normalized, sample_rate)

    assert quiet_lufs == pytest.approx(strong_lufs, abs=0.15)
    assert quiet_lufs == pytest.approx(-19.0, abs=0.15)
    assert narrator_lufs == pytest.approx(-18.5, abs=0.15)
    assert loud_lufs == pytest.approx(-17.8, abs=0.15)


def test_lufs_leveling_matches_low_and_bright_voice_spectra() -> None:
    settings = build_settings()
    sample_rate = 48_000
    timeline = np.arange(sample_rate, dtype=np.float32) / sample_rate
    low_voice = 0.03 * np.sin(2 * np.pi * 100 * timeline)
    bright_voice = 0.03 * np.sin(2 * np.pi * 260 * timeline)
    segment = {
        "kind": "dialogue",
        "speaker": "Nhân vật",
        "volume": "normal",
        "emotion": "neutral",
        "intensity": 1,
    }

    low_normalized = normalize_segment_level(low_voice, sample_rate, segment, settings)
    bright_normalized = normalize_segment_level(bright_voice, sample_rate, segment, settings)

    assert integrated_loudness_lufs(low_normalized, sample_rate) == pytest.approx(-19.0, abs=0.15)
    assert integrated_loudness_lufs(bright_normalized, sample_rate) == pytest.approx(-19.0, abs=0.15)


def test_segment_rate_validation_warns_for_mild_outlier_and_rejects_extreme() -> None:
    settings = build_settings(overrides={"tts": {"min_seconds_per_100_chars": 0.2}})
    text = "a" * 60
    mildly_slow = np.sin(np.linspace(0, 200, 48_000 * 6, dtype=np.float32)) * 0.12
    extremely_slow = np.sin(np.linspace(0, 200, 48_000 * 12, dtype=np.float32)) * 0.12

    _, metrics = validate_audio_array(
        mildly_slow,
        text,
        settings,
        48_000,
        segment={"pace": "normal"},
    )

    assert metrics["pace_outlier"] == 1.0
    with pytest.raises(AudioQualityError, match="far outside normal safety range"):
        validate_audio_array(
            extremely_slow,
            text,
            settings,
            48_000,
            segment={"pace": "normal"},
        )


def test_vieneu_frame_budget_cannot_exceed_the_shared_validation_limit() -> None:
    settings = build_settings(overrides={"tts": {"min_seconds_per_100_chars": 0.2}})
    segment = {"kind": "dialogue", "pace": "normal"}
    policy = segment_duration_policy("“Ha…”", settings, segment)
    generated_samples = policy.generation_max_frames * VIENEU_V3_CODEC_SAMPLES_PER_FRAME
    audio = np.sin(np.linspace(0, 500, generated_samples, dtype=np.float32)) * 0.12

    _, metrics = validate_audio_array(audio, "“Ha…”", settings, 48_000, segment=segment)

    assert policy.generation_max_frames == 48
    assert policy.generation_ceiling_seconds < policy.validation_max_seconds
    assert metrics["duration"] == pytest.approx(3.84, abs=0.01)


@pytest.mark.parametrize("kind", ["narration", "dialogue", "thought"])
@pytest.mark.parametrize("pace", ["slow", "normal", "fast"])
@pytest.mark.parametrize("character_count", [1, 20, 100, 340])
def test_every_generation_budget_has_validation_headroom(
    kind: str,
    pace: str,
    character_count: int,
) -> None:
    settings = build_settings()
    policy = segment_duration_policy(
        "a" * character_count,
        settings,
        {"kind": kind, "pace": pace},
    )

    assert policy.generation_ceiling_seconds < policy.validation_max_seconds


def test_spoken_audio_is_never_trimmed_to_hide_an_overlong_result() -> None:
    settings = build_settings()
    audio = np.ones(48_000 * 10, dtype=np.float32) * 0.1

    with pytest.raises(AudioQualityError, match="audio unusually long"):
        validate_audio_array(
            audio,
            "Ha...",
            settings,
            48_000,
            segment={"kind": "dialogue", "pace": "normal"},
        )
