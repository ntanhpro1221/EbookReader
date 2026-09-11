from __future__ import annotations

import subprocess
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
    tempo_stretch_wav_atomic,
    vieneu_generation_reached_frame_ceiling,
    verify_mp3,
    validate_audio_array,
)
from ebook_reader.audio_transform_contract import (
    POSTPROCESS_ALGORITHM,
    POSTPROCESS_OUTPUT_CODEC,
    POSTPROCESS_OUTPUT_SAMPLES_FIELD,
    POSTPROCESS_PROFILE_FIELD,
    POSTPROCESS_PROFILE_NONE,
    POSTPROCESS_PROFILE_TEMPO,
    POSTPROCESS_PROFILES,
    POSTPROCESS_PROVENANCE_FIELDS,
    POSTPROCESS_SAMPLE_COUNT_RELATIVE_TOLERANCE,
    POSTPROCESS_SOURCE_CANDIDATE_ID_FIELD,
    POSTPROCESS_SOURCE_SAMPLE_RATE_FIELD,
    POSTPROCESS_SOURCE_SAMPLES_FIELD,
    POSTPROCESS_SOURCE_SHA256_FIELD,
    POSTPROCESS_TEMPO_DENOMINATOR,
    POSTPROCESS_TEMPO_FACTOR,
    POSTPROCESS_TEMPO_NUMERATOR,
)
from ebook_reader.config import build_settings
from ebook_reader.io_utils import sha256_file


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


def test_audio_transform_contract_is_immutable_and_versioned() -> None:
    assert POSTPROCESS_ALGORITHM == "immutable_dual_decode_tempo_rescue_v1"
    assert POSTPROCESS_PROFILE_NONE == "none"
    assert POSTPROCESS_PROFILE_TEMPO == "ffmpeg_atempo_0_94_pcm_s16le_v1"
    assert POSTPROCESS_PROFILES == (
        POSTPROCESS_PROFILE_NONE,
        POSTPROCESS_PROFILE_TEMPO,
    )
    assert POSTPROCESS_TEMPO_NUMERATOR == 94
    assert POSTPROCESS_TEMPO_DENOMINATOR == 100
    assert POSTPROCESS_TEMPO_FACTOR == 0.94
    assert POSTPROCESS_SAMPLE_COUNT_RELATIVE_TOLERANCE == 0.01
    assert POSTPROCESS_OUTPUT_CODEC == "pcm_s16le"
    assert POSTPROCESS_PROFILE_FIELD == "postprocess_profile"
    assert POSTPROCESS_SOURCE_CANDIDATE_ID_FIELD == "postprocess_source_candidate_id"
    assert POSTPROCESS_SOURCE_SHA256_FIELD == "postprocess_source_sha256"
    assert POSTPROCESS_SOURCE_SAMPLE_RATE_FIELD == "postprocess_source_sample_rate"
    assert POSTPROCESS_SOURCE_SAMPLES_FIELD == "postprocess_source_samples"
    assert POSTPROCESS_OUTPUT_SAMPLES_FIELD == "postprocess_output_samples"
    assert POSTPROCESS_PROVENANCE_FIELDS == (
        POSTPROCESS_PROFILE_FIELD,
        POSTPROCESS_SOURCE_CANDIDATE_ID_FIELD,
        POSTPROCESS_SOURCE_SHA256_FIELD,
        POSTPROCESS_SOURCE_SAMPLE_RATE_FIELD,
        POSTPROCESS_SOURCE_SAMPLES_FIELD,
        POSTPROCESS_OUTPUT_SAMPLES_FIELD,
    )


def test_real_ffmpeg_tempo_transform_is_atomic_pcm16_mono_and_preserves_source(
    tmp_path: Path,
) -> None:
    settings = build_settings(overrides={"tts": {"min_seconds_per_100_chars": 0.2}})
    source = tmp_path / "source.wav"
    _write_test_tone(source, settings, 220, seconds=2.0)
    source_bytes = source.read_bytes()
    destination = tmp_path / "stretched.wav"

    checksum, metrics = tempo_stretch_wav_atomic(source, destination)

    info = audio_io.sf.info(destination)
    assert source.read_bytes() == source_bytes
    assert checksum == sha256_file(destination)
    assert info.format == "WAV"
    assert info.subtype == "PCM_16"
    assert info.channels == 1
    assert info.samplerate == 48_000
    assert metrics[POSTPROCESS_SOURCE_SAMPLE_RATE_FIELD] == info.samplerate
    assert metrics[POSTPROCESS_SOURCE_SAMPLES_FIELD] == 96_000
    assert metrics[POSTPROCESS_OUTPUT_SAMPLES_FIELD] == pytest.approx(
        96_000 / POSTPROCESS_TEMPO_FACTOR,
        rel=0.01,
    )
    assert metrics["rms"] > 0
    assert metrics["peak"] <= 1.0
    assert not list(tmp_path.glob("*.part.*"))


@pytest.mark.parametrize("invalid_output", ["stereo", "silent"])
def test_tempo_transform_rejects_invalid_signal_preserves_output_and_cleans_part(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    invalid_output: str,
) -> None:
    settings = build_settings(overrides={"tts": {"min_seconds_per_100_chars": 0.2}})
    source = tmp_path / "source.wav"
    _write_test_tone(source, settings, 220, seconds=2.0)
    source_bytes = source.read_bytes()
    destination = tmp_path / "stretched.wav"
    incumbent = b"previous verified audio"
    destination.write_bytes(incumbent)

    def write_invalid_output(
        command: list[str],
        **_: Any,
    ) -> subprocess.CompletedProcess[str]:
        output = Path(command[-1])
        channels = 2 if invalid_output == "stereo" else 1
        audio = np.zeros((102_128, channels), dtype=np.float32)
        if channels == 1:
            audio = audio.reshape(-1)
        audio_io.sf.write(output, audio, 48_000, subtype="PCM_16")
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(audio_io, "run_hidden", write_invalid_output)

    with pytest.raises(AudioQualityError, match="mono input|no audible signal"):
        tempo_stretch_wav_atomic(source, destination)

    assert source.read_bytes() == source_bytes
    assert destination.read_bytes() == incumbent
    assert not list(tmp_path.glob("*.part.*"))


def test_tempo_transform_rejects_in_place_overwrite(tmp_path: Path) -> None:
    settings = build_settings(overrides={"tts": {"min_seconds_per_100_chars": 0.2}})
    source = tmp_path / "source.wav"
    _write_test_tone(source, settings, 220, seconds=2.0)
    source_bytes = source.read_bytes()

    with pytest.raises(AudioQualityError, match="source and destination must differ"):
        tempo_stretch_wav_atomic(source, source)

    assert source.read_bytes() == source_bytes
    assert not list(tmp_path.glob("*.part.*"))


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

    # Read the anchors from settings rather than repeating them: what matters is that
    # levelling reaches each anchor exactly and preserves the intended ordering, not
    # the absolute numbers, which move whenever the peak-ceiling headroom is retuned.
    targets = settings["audio"]["segment_target_lufs"]
    narrator_offset = float(settings["audio"]["segment_narrator_offset_db"])

    assert quiet_lufs == pytest.approx(strong_lufs, abs=0.15)
    assert quiet_lufs == pytest.approx(float(targets["normal"]), abs=0.15)
    assert narrator_lufs == pytest.approx(
        float(targets["normal"]) + narrator_offset, abs=0.15
    )
    assert loud_lufs == pytest.approx(float(targets["loud"]), abs=0.15)
    # The whole point of the anchors: the director's intent has to survive levelling.
    assert loud_lufs > narrator_lufs > quiet_lufs


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

    normal_target = float(settings["audio"]["segment_target_lufs"]["normal"])
    assert integrated_loudness_lufs(low_normalized, sample_rate) == pytest.approx(
        normal_target, abs=0.15
    )
    assert integrated_loudness_lufs(bright_normalized, sample_rate) == pytest.approx(
        normal_target, abs=0.15
    )


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


def test_pronunciation_expansion_over_eight_chars_uses_normal_generation_budget() -> None:
    text = "“Anh Lu-si-en!”"
    policy = segment_duration_policy(
        text,
        build_settings(),
        {"kind": "dialogue", "pace": "normal"},
    )

    assert not audio_io.is_short_utterance(text)
    assert policy.generation_max_frames == 48


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


def test_signal_metrics_measure_the_unmodified_endpoint_window() -> None:
    sample_rate = 48_000
    active_tail = np.full(sample_rate, 0.1, dtype=np.float32)
    quiet_tail = active_tail.copy()
    quiet_tail[-int(sample_rate * audio_io.SEGMENT_ENDPOINT_WINDOW_SECONDS) :] = 0.0

    active_metrics = audio_io.signal_metrics(active_tail, sample_rate)
    quiet_metrics = audio_io.signal_metrics(quiet_tail, sample_rate)

    assert active_metrics["trailing_rms"] == pytest.approx(0.1)
    assert quiet_metrics["trailing_rms"] == 0.0


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


def test_loudness_targets_stay_inside_the_peak_ceiling_speech_allows() -> None:
    """Loudness targets must be reachable, not aspirational.

    Levelling is `min(loudness_gain, peak_safe_gain)` and mastering cannot exceed its
    true-peak ceiling either, so a target above `ceiling - crest_factor` can only be
    missed. Measured Vietnamese TTS speech runs at a 17.6 dB median crest factor, 20.6 dB
    at the worst segment, and 17.9 dB across a whole assembled chapter. A -18.0 LUFS
    chapter target against a -2 dBTP ceiling was 1.9 dB beyond what the content allows,
    and segment anchers near -19 LUFS put 77% of segments on the peak ceiling instead of
    their anchor - which inverted the intent, making `loud` quieter than `normal`.
    """
    settings = build_settings()
    audio = settings["audio"]
    segment_ceiling = float(audio["segment_peak_dbfs"])
    chapter_ceiling = float(audio["true_peak_db"])
    narrator_offset = float(audio["segment_narrator_offset_db"])
    targets = audio["segment_target_lufs"]
    measured_worst_segment_crest_db = 20.6
    measured_chapter_crest_db = 17.9

    highest_segment_target = max(float(value) for value in targets.values()) + narrator_offset
    assert highest_segment_target <= segment_ceiling - measured_worst_segment_crest_db

    assert float(audio["loudness_lufs"]) <= chapter_ceiling - measured_chapter_crest_db


def test_endpoint_floor_tracks_the_loudness_anchors() -> None:
    """The endpoint gate measures levelled audio, so it must move with the anchors.

    `generation_endpoint_active` compares the trailing RMS of the written WAV against an
    absolute dBFS floor. Lowering the loudness anchors without lowering this floor would
    silently make the gate less sensitive to VieNeu still speaking at the frame ceiling.
    """
    audio = build_settings()["audio"]
    endpoint_floor = float(audio["segment_endpoint_floor_dbfs"])
    normal_target = float(audio["segment_target_lufs"]["normal"])

    assert endpoint_floor < normal_target
    assert normal_target - endpoint_floor == pytest.approx(26.0, abs=1.0)
    # The active floor is measured before any gain, so it must not move with them.
    assert float(audio["segment_active_floor_dbfs"]) == pytest.approx(-45.0)


def test_a_failed_chapter_still_reports_the_edges_it_trimmed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The chapter that fails is the one somebody has to diagnose.

    `trimmed_segment_edges` used to be attached after the review check raised, so a failing
    chapter's metrics always showed an empty list - saying the edge cap had never run when it
    had. On alpha.53 chapter 10 that sent the diagnosis at the edge cap for several minutes;
    the real cause was 1.38s of silence *inside* a take, which the edge cap does not touch and
    was never claiming to.
    """
    settings = build_settings(overrides={"tts": {"min_seconds_per_100_chars": 0.2}})
    sample_rate = int(settings["tts"]["sample_rate"])
    source = tmp_path / "source.wav"
    timeline = np.arange(int(sample_rate * 1.0), dtype=np.float32) / sample_rate
    tone = 0.12 * np.sin(2 * np.pi * 220 * timeline)
    lead_in = np.zeros(int(sample_rate * 0.9), dtype=np.float32)
    atomic_write_wav(
        source,
        np.concatenate([lead_in, tone]),
        sample_rate,
        "A sufficiently long sentence for deterministic audio QA.",
        settings,
    )
    output = tmp_path / "chapter_001.mp3"
    evaluate = audio_io._evaluate_chapter_quality

    def force_review_flag(*args: Any, **kwargs: Any) -> audio_io.ChapterQualityMetrics:
        return replace(evaluate(*args, **kwargs), review_flags=("forced review",))

    monkeypatch.setattr(audio_io, "_evaluate_chapter_quality", force_review_flag)

    with pytest.raises(ChapterQualityError) as captured:
        assemble_chapter_atomic_with_metrics(
            [source],
            output,
            settings,
            title="Chapter 1",
            book_title="Test book",
            track=1,
            work_dir=tmp_path / "silence",
        )

    trimmed = captured.value.metrics["trimmed_segment_edges"]
    assert trimmed, "a failing chapter must still say what it trimmed"
    assert "source.wav" in trimmed[0]


def test_spoken_speakable_chars_counts_a_number_as_it_is_said() -> None:
    """The bug that killed chapter 023's title, and with it the chapter.

    VieNeu reads 22 as "hai mươi hai" - two written characters, eleven spoken. The pace gate
    counted the written string against a floor calibrated on text without digits, so
    "Chương 22 - 22: Ấn tượng đầu tiên" measured 10.68 chars/s at 2.25 seconds and failed,
    eleven times running, while what a listener hears is 17.78 - comfortably inside the band.
    Eleven identical failures because it was arithmetic, not variance.
    """
    from ebook_reader.audio_io import spoken_speakable_chars

    title = "Chương 22 - 22: Ấn tượng đầu tiên"

    assert sum(char.isalnum() for char in title) == 24
    assert spoken_speakable_chars(title) == 40
    assert spoken_speakable_chars(title) / 2.25 > 12.5


def test_text_without_digits_is_counted_exactly_as_before() -> None:
    """The change must be invisible to every segment that has no number in it."""
    from ebook_reader.audio_io import spoken_speakable_chars

    for text in (
        "Không có chữ số nào ở đây cả.",
        '"Tiếp theo."',
        "Anh ta bước qua hành lang rất dài và dừng lại trước cánh cửa bằng đồng.",
    ):
        assert spoken_speakable_chars(text) == sum(char.isalnum() for char in text)


def test_a_number_from_a_thousand_up_is_counted_as_it_is_read() -> None:
    """vietnamese_number_words used to stop at 999; the digits above it were counted as written.

    Chapter 106 of batch 4 died on "123456" counted as six characters and one syllable. The
    speller now reaches below 10^12 by the grammar of counting, and a digit run from 1000 up
    counts the shorter of its two possible readings - never a made-up multiplier.
    """
    from ebook_reader.audio_io import spoken_speakable_chars

    text = "Chương 1000 - 1000: xa quá"
    spoken = "Chương một nghìn - một nghìn: xa quá"

    assert spoken_speakable_chars(text) == sum(char.isalnum() for char in spoken)
    assert spoken_speakable_chars(text) > sum(char.isalnum() for char in text)
