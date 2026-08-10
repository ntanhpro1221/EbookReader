from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any

import numpy as np
import pytest

import ebook_reader.audio_io as audio_io
from ebook_reader.audio_io import (
    AudioQualityError,
    ChapterQualityError,
    VIENEU_V3_CODEC_SAMPLES_PER_FRAME,
    atomic_write_wav,
    assemble_chapter_atomic,
    assemble_chapter_atomic_with_metrics,
    integrated_loudness_lufs,
    normalize_segment_level,
    segment_duration_policy,
    vieneu_generation_reached_frame_ceiling,
    verify_mp3,
    validate_audio_array,
)
from ebook_reader.config import build_settings


def _write_test_tone(
    path: Path,
    settings: dict[str, Any],
    frequency: float,
    seconds: float = 0.8,
) -> None:
    sample_rate = int(settings["tts"]["sample_rate"])
    timeline = np.arange(int(sample_rate * seconds), dtype=np.float32) / sample_rate
    audio = 0.12 * np.sin(2 * np.pi * frequency * timeline)
    atomic_write_wav(
        path,
        audio,
        sample_rate,
        "A sufficiently long sentence for deterministic audio QA.",
        settings,
    )


def test_real_ffmpeg_chapter_assembly_is_atomic_and_decodable(tmp_path: Path) -> None:
    settings = build_settings(overrides={"tts": {"min_seconds_per_100_chars": 0.2}})
    sample_rate = int(settings["tts"]["sample_rate"])
    entries: list[tuple[Path, int]] = []
    for index, frequency in enumerate((220, 330), start=1):
        wav = tmp_path / f"{index}.wav"
        _write_test_tone(wav, settings, frequency)
        entries.append((wav, 300 if index == 1 else 0))

    output = tmp_path / "chapter_001.mp3"
    result = assemble_chapter_atomic_with_metrics(
        entries,
        output,
        settings,
        title="Chương 1",
        book_title="Sách thử",
        track=1,
        work_dir=tmp_path / "silence",
    )

    assert len(result.checksum) == 64
    assert result.quality.hard_failures == ()
    assert result.quality.sample_rate == sample_rate
    assert result.quality.channels == 1
    assert result.quality.duration_error_seconds == pytest.approx(0.0, abs=0.05)
    assert result.quality.integrated_loudness_lufs == pytest.approx(
        settings["audio"]["loudness_lufs"],
        abs=0.3,
    )
    assert result.quality.true_peak_db <= settings["audio"]["true_peak_db"] + 0.15
    assert result.quality.clipping_fraction == 0.0
    assert abs(result.quality.dc_offset) < 0.01
    assert result.quality.longest_unexpected_silence_seconds < 1.0
    assert result.quality.max_join_jump < 0.18
    assert verify_mp3(output) == (True, "ok")

    repeated_output = tmp_path / "chapter_001_repeated.mp3"
    repeated_checksum = assemble_chapter_atomic(
        entries,
        repeated_output,
        settings,
        title="Chương 1",
        book_title="Sách thử",
        track=1,
        work_dir=tmp_path / "silence",
    )

    assert repeated_checksum == result.checksum
    assert not list(tmp_path.rglob("*.part.*"))


def test_chapter_qa_failure_preserves_existing_output_and_cleans_candidates(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = build_settings(overrides={"tts": {"min_seconds_per_100_chars": 0.2}})
    source = tmp_path / "source.wav"
    _write_test_tone(source, settings, 220, seconds=1.0)
    output = tmp_path / "chapter_001.mp3"
    original_output = b"previous verified chapter"
    output.write_bytes(original_output)
    evaluate = audio_io._evaluate_chapter_quality

    def force_hard_failure(*args: Any, **kwargs: Any) -> audio_io.ChapterQualityMetrics:
        quality = evaluate(*args, **kwargs)
        return replace(quality, hard_failures=("forced regression gate",))

    monkeypatch.setattr(audio_io, "_evaluate_chapter_quality", force_hard_failure)

    with pytest.raises(ChapterQualityError, match="forced regression gate") as captured:
        assemble_chapter_atomic_with_metrics(
            [source],
            output,
            settings,
            title="Chapter 1",
            book_title="Test book",
            track=1,
            work_dir=tmp_path / "silence",
        )

    assert captured.value.artifact_sha256 is not None
    assert captured.value.failure_codes == ("CHAPTER_QA_HARD_FAILURE",)
    assert captured.value.metrics["hard_failures"] == ("forced regression gate",)
    assert captured.value.review_required is False
    assert output.read_bytes() == original_output
    assert not list(tmp_path.rglob("*.part.*"))


def test_high_quality_review_flag_preserves_existing_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = build_settings(overrides={"tts": {"min_seconds_per_100_chars": 0.2}})
    source = tmp_path / "source.wav"
    _write_test_tone(source, settings, 220, seconds=1.0)
    output = tmp_path / "chapter_001.mp3"
    original_output = b"previous verified chapter"
    output.write_bytes(original_output)
    evaluate = audio_io._evaluate_chapter_quality

    def force_review_flag(*args: Any, **kwargs: Any) -> audio_io.ChapterQualityMetrics:
        quality = evaluate(*args, **kwargs)
        return replace(quality, review_flags=("forced perceptual review",))

    monkeypatch.setattr(audio_io, "_evaluate_chapter_quality", force_review_flag)

    with pytest.raises(ChapterQualityError, match="requires review") as captured:
        assemble_chapter_atomic_with_metrics(
            [source],
            output,
            settings,
            title="Chapter 1",
            book_title="Test book",
            track=1,
            work_dir=tmp_path / "silence",
        )

    assert captured.value.artifact_sha256 is not None
    assert captured.value.failure_codes == ("CHAPTER_QA_REVIEW_REQUIRED",)
    assert captured.value.metrics["review_flags"] == ("forced perceptual review",)
    assert captured.value.review_required is True
    assert output.read_bytes() == original_output
    assert not list(tmp_path.rglob("*.part.*"))


def test_chapter_qa_separates_review_indicators_from_hard_gates() -> None:
    sample_rate = 48_000
    timeline = np.arange(sample_rate * 2, dtype=np.float32) / sample_rate
    decoded = (0.05 * np.sin(2 * np.pi * 220 * timeline)).reshape(-1, 1)
    audio_cfg = {
        "loudness_lufs": -18.0,
        "true_peak_db": -2.0,
        "_expected_sample_rate": sample_rate,
    }
    mastering_input = {"input_i": -24.0, "input_tp": -10.0}
    review_measurement = {"input_i": -17.6, "input_tp": -2.0, "input_lra": 1.0}

    review_quality = audio_io._evaluate_chapter_quality(
        decoded,
        sample_rate,
        1,
        2.0,
        [],
        [],
        audio_cfg,
        mastering_input,
        review_measurement,
    )

    assert review_quality.hard_failures == ()
    assert any(flag.startswith("loudness delta") for flag in review_quality.review_flags)

    hard_measurement = {**review_measurement, "input_i": -16.5}
    hard_quality = audio_io._evaluate_chapter_quality(
        decoded,
        sample_rate,
        1,
        2.0,
        [],
        [],
        audio_cfg,
        mastering_input,
        hard_measurement,
    )

    assert any("integrated loudness" in failure for failure in hard_quality.hard_failures)


def test_stereo_audio_is_rejected_instead_of_flattened() -> None:
    settings = build_settings(overrides={"tts": {"min_seconds_per_100_chars": 0.2}})
    stereo = np.zeros((48_000, 2), dtype=np.float32)

    with pytest.raises(AudioQualityError, match="mono"):
        validate_audio_array(stereo, "Một câu đủ dài để kiểm tra.", settings, 48_000)


def test_segment_sample_rate_must_match_locked_tts_rate() -> None:
    settings = build_settings(overrides={"tts": {"min_seconds_per_100_chars": 0.2}})
    audio = np.sin(np.linspace(0.0, 20.0, 24_000, dtype=np.float32)) * 0.1

    with pytest.raises(AudioQualityError, match="24000 Hz, expected 48000 Hz"):
        validate_audio_array(audio, "Một câu đủ dài để kiểm tra.", settings, 24_000)


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

    assert policy.generation_max_frames == 24
    assert policy.generation_ceiling_seconds < policy.validation_max_seconds
    assert metrics["duration"] == pytest.approx(1.92, abs=0.01)


def test_two_word_short_dialogue_uses_the_short_generation_budget() -> None:
    policy = segment_duration_policy(
        "“Được rồi…”",
        build_settings(),
        {"kind": "dialogue", "pace": "normal"},
    )

    assert policy.generation_max_frames == 24


def test_vieneu_output_at_exact_frame_ceiling_is_reported_without_judging_content() -> None:
    policy = segment_duration_policy(
        "“Hà... hà...”",
        build_settings(),
        {"kind": "dialogue", "pace": "normal"},
    )
    ceiling_samples = policy.generation_max_frames * VIENEU_V3_CODEC_SAMPLES_PER_FRAME

    assert policy.generation_max_frames == 24
    assert vieneu_generation_reached_frame_ceiling(np.zeros(ceiling_samples), policy)
    assert not vieneu_generation_reached_frame_ceiling(
        np.zeros(ceiling_samples - VIENEU_V3_CODEC_SAMPLES_PER_FRAME),
        policy,
    )


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
