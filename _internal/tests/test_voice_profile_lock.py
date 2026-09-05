from __future__ import annotations

import hashlib
import sys
from pathlib import Path
from types import ModuleType

import numpy as np
import pytest

import ebook_reader.tts as tts_module
from ebook_reader.audio_io import (
    VIENEU_V3_CODEC_SAMPLES_PER_FRAME,
    AudioQualityError,
    segment_duration_policy,
)
from ebook_reader.config import build_settings
from ebook_reader.database import ProjectDB
from ebook_reader.tts import (
    CLARITY_MAX_TEMPERATURE,
    CLARITY_MAX_TOP_P,
    DELIVERY_CLARITY,
    GENERATION_TEMPERATURE,
    GENERATION_TOP_P,
    HA_VOCALIZATION_MAX_TEMPERATURE,
    SHORT_UTTERANCE_MAX_TEMPERATURE,
    SHORT_UTTERANCE_MAX_TOP_P,
    TTSCoordinator,
    VieNeuEngine,
    apply_pitch_variant,
    is_fatal_tts_error,
    is_transient_tts_memory_error,
    vieneu_sampling_for_segment,
)
from ebook_reader.tts_contract import (
    HA_VOCALIZATION_DELIVERY_PROFILE,
    HA_VOCALIZATION_FINAL_SAMPLES_FIELD,
    HA_VOCALIZATION_MAX_NEW_FRAMES,
    HA_VOCALIZATION_MAX_NEW_FRAMES_FIELD,
    HA_VOCALIZATION_MAX_TOP_P,
    HA_VOCALIZATION_ORIGINAL_SAMPLES_FIELD,
    HA_VOCALIZATION_PADDING_SAMPLES_FIELD,
    HA_VOCALIZATION_PROFILE_FIELD,
    HA_VOCALIZATION_SAMPLE_RATE_FIELD,
    HA_VOCALIZATION_TARGET_SAMPLES_FIELD,
    HA_VOCALIZATION_TEMPERATURE_FIELD,
    HA_VOCALIZATION_TOP_P_FIELD,
)


class FakeVieNeuRuntime:
    def __init__(self) -> None:
        self.calls = []
        self.sample_rate = 48_000

    def list_preset_voices(self):
        return [
            ("Phạm Tuyên — Nam · Bắc · Phong cách tự nhiên", "Phạm Tuyên"),
            ("Thái Sơn — Nam · Nam · Phong cách kể chuyện", "Thái Sơn"),
        ]

    def infer(self, text, **kwargs):
        self.calls.append((text, kwargs))
        return np.asarray([0.1, -0.1], dtype=np.float32)


def test_voice_profile_resume_preserves_locked_vieneu_preset(tmp_path: Path) -> None:
    db = ProjectDB(tmp_path / "project.sqlite3")
    profile = {
        "voice_key": "char_lan",
        "engine": "vieneu",
        "preset_name": "Ngọc Linh",
        "description": "Nữ · Bắc · Kể chuyện",
        "seed": 1234,
        "status": "ready",
    }
    profile_id = db.upsert_voice_profile(profile)

    same_id = db.upsert_voice_profile(profile)
    fresh = db.voice_profile(same_id)

    assert same_id == profile_id
    assert fresh["engine"] == "vieneu"
    assert fresh["preset_name"] == "Ngọc Linh"
    assert fresh["pitch_semitones"] == 0
    assert fresh["status"] == "ready"


def test_vieneu_uses_voice_id_instead_of_display_label(monkeypatch) -> None:
    runtime = FakeVieNeuRuntime()
    vieneu_module = ModuleType("vieneu")
    vieneu_module.Vieneu = lambda **_kwargs: runtime
    monkeypatch.setitem(sys.modules, "vieneu", vieneu_module)
    engine = VieNeuEngine(build_settings(), lambda _message: None)

    engine.load()

    assert engine.voices == ["Phạm Tuyên", "Thái Sơn"]
    assert engine.voice_for_profile(
        {"engine": "vieneu", "preset_name": "Phạm Tuyên", "voice_key": "narrator"},
    ) == "Phạm Tuyên"


def test_emotion_and_intensity_no_longer_reach_sampling(monkeypatch) -> None:
    """Delivery metadata must not move the sampler, because it never meant anything there.

    VieNeu has no emotion input. Emotion used to index a table of temperatures, so angry
    and surprised shared 0.86 and produced byte-identical audio for the same line - the
    label selected a randomness level, not a delivery. intensity added 0.015 per step to
    temperature and top_p, and a listener identified the higher settings as sounding
    broken rather than emphatic. Every segment now generates at one stable temperature.
    """
    runtime = FakeVieNeuRuntime()
    vieneu_module = ModuleType("vieneu")
    vieneu_module.Vieneu = lambda **_kwargs: runtime
    monkeypatch.setitem(sys.modules, "vieneu", vieneu_module)
    monkeypatch.setattr(tts_module, "_set_generation_seed", lambda _seed: None)
    engine = VieNeuEngine(build_settings(), lambda _message: None)
    profile = {
        "engine": "vieneu",
        "preset_name": "Thái Sơn",
        "voice_key": "preset_thai_son",
    }
    neutral = {
        "text": "Tôi đã hiểu rồi.",
        "speaker": "Nhân vật",
        "emotion": "neutral",
        "intensity": 0,
    }
    excited = {**neutral, "emotion": "excited", "intensity": 3}
    engine.generate_one(neutral, profile, 1)
    engine.generate_one(excited, profile, 2)

    assert [call[1]["voice"] for call in runtime.calls] == ["Thái Sơn", "Thái Sơn"]
    assert runtime.calls[0][0] == neutral["text"]
    assert runtime.calls[1][0] == neutral["text"]
    # The locked voice is unchanged, and so now is everything the sampler sees.
    assert runtime.calls[1][1]["temperature"] == runtime.calls[0][1]["temperature"]
    assert (
        vieneu_sampling_for_segment(excited)["top_p"]
        == vieneu_sampling_for_segment(neutral)["top_p"]
    )
    assert (
        vieneu_sampling_for_segment(excited)["temperature"]
        == vieneu_sampling_for_segment(neutral)["temperature"]
        == pytest.approx(GENERATION_TEMPERATURE)
    )
    # pace still shapes silence, which is a real effect on the audio rather than a
    # relabelling of randomness, so it keeps its influence.
    assert vieneu_sampling_for_segment({**neutral, "pace": "slow"})["silence_p"] > (
        vieneu_sampling_for_segment({**neutral, "pace": "fast"})["silence_p"]
    )


def test_short_utterance_uses_conservative_sampling() -> None:
    sampling = vieneu_sampling_for_segment(
        {
            "text": "Ha...",
            "speaker": "Nhân vật",
            "emotion": "excited",
            "intensity": 3,
            "pace": "normal",
        }
    )

    assert sampling["max_new_frames"] == 24
    assert sampling["temperature"] == pytest.approx(0.72)
    assert sampling["top_p"] == pytest.approx(0.90)


def test_standalone_gasp_profile_uses_empirically_locked_sampling() -> None:
    row = {
        "text": "Ha ha.",
        "speaker": "Nhân vật",
        "emotion": "excited",
        "intensity": 3,
        "pace": "normal",
    }

    ordinary = vieneu_sampling_for_segment(row)
    profiled = vieneu_sampling_for_segment(
        row,
        vocalization_delivery_profile=HA_VOCALIZATION_DELIVERY_PROFILE,
    )
    clarity = vieneu_sampling_for_segment(
        row,
        delivery_mode=DELIVERY_CLARITY,
        vocalization_delivery_profile=HA_VOCALIZATION_DELIVERY_PROFILE,
    )

    assert ordinary["temperature"] == pytest.approx(0.72)
    assert ordinary["top_p"] == pytest.approx(0.90)
    assert profiled["temperature"] == pytest.approx(0.55)
    assert profiled["top_p"] == pytest.approx(0.82)
    assert profiled["max_new_frames"] == HA_VOCALIZATION_MAX_NEW_FRAMES
    assert clarity["temperature"] == pytest.approx(0.55)
    assert clarity["top_p"] == pytest.approx(0.82)
    assert clarity["max_new_frames"] == HA_VOCALIZATION_MAX_NEW_FRAMES
    with pytest.raises(ValueError, match="Unsupported TTS vocalization delivery profile"):
        vieneu_sampling_for_segment(
            row,
            vocalization_delivery_profile="unknown",
        )


def test_clarity_delivery_only_lowers_sampling_variance() -> None:
    row = {
        "text": "Thiêu chết ả phù thủy tà ác khốn kiếp đó đi!",
        "speaker": "Đám đông",
        "emotion": "angry",
        "intensity": 3,
        "pace": "normal",
    }

    primary = vieneu_sampling_for_segment(row)
    clarity = vieneu_sampling_for_segment(row, delivery_mode=DELIVERY_CLARITY)

    # The cap has to sit below the generation temperature or clarity repair does nothing.
    # It used to sit above it for every neutral segment, which was most of the book.
    assert primary["temperature"] > clarity["temperature"]
    assert primary["top_p"] > clarity["top_p"]
    assert clarity["temperature"] < GENERATION_TEMPERATURE
    assert clarity["temperature"] == pytest.approx(CLARITY_MAX_TEMPERATURE)
    assert clarity["top_p"] == pytest.approx(0.90)
    assert clarity["top_k"] == primary["top_k"]
    assert clarity["repetition_penalty"] == primary["repetition_penalty"]
    assert clarity["max_new_frames"] == primary["max_new_frames"]

    with pytest.raises(ValueError, match="Unsupported TTS delivery mode"):
        vieneu_sampling_for_segment(row, delivery_mode="unknown")


def test_clarity_delivery_preserves_locked_voice_pitch_and_spoken_text(
    tmp_path: Path,
    monkeypatch,
) -> None:
    db = ProjectDB(tmp_path / "project.sqlite3")
    profile_id = db.upsert_voice_profile(
        {
            "voice_key": "crowd",
            "engine": "vieneu",
            "preset_name": "Xuân Vĩnh",
            "description": "Đám đông",
            "seed": 1234,
            "pitch_semitones": -1,
            "status": "ready",
        }
    )
    coordinator = TTSCoordinator(build_settings(), db, lambda _message: None)
    row = {
        "voice_profile_id": profile_id,
        "stable_id": "clarity_1",
        "text": "Thiêu chết ả!",
        "kind": "dialogue",
        "speaker": "Đám đông",
        "emotion": "angry",
        "intensity": 3,
        "pace": "normal",
    }
    generated: list[tuple[dict, dict, dict]] = []
    pitch_steps: list[int] = []

    def generate_one(spoken_row, profile, _seed, *, sampling):
        generated.append((dict(spoken_row), dict(profile), dict(sampling)))
        return np.asarray([0.1, -0.1], dtype=np.float32)

    def apply_pitch(audio, _sample_rate, steps):
        pitch_steps.append(int(steps))
        return audio

    monkeypatch.setattr(coordinator.vieneu, "generate_one", generate_one)
    monkeypatch.setattr(coordinator, "generation_seed", lambda _row, _salt="": 1)
    monkeypatch.setattr(tts_module, "apply_pitch_variant", apply_pitch)
    monkeypatch.setattr(
        tts_module,
        "atomic_write_wav",
        lambda *_args, **_kwargs: ("checksum", {"duration": 1.0}),
    )

    _checksum, primary_metrics, _seed = coordinator.synthesize_atomic(
        row,
        tmp_path / "primary.wav",
    )
    _checksum, clarity_metrics, _seed = coordinator.synthesize_atomic(
        row,
        tmp_path / "clarity.wav",
        delivery_mode=DELIVERY_CLARITY,
    )

    assert generated[0][0] == generated[1][0]
    assert generated[0][1]["id"] == generated[1][1]["id"] == profile_id
    assert generated[0][2]["temperature"] > generated[1][2]["temperature"]
    assert generated[0][2]["top_p"] > generated[1][2]["top_p"]
    assert pitch_steps == [-1, -1]
    assert primary_metrics["spoken_text_sha256"] == clarity_metrics["spoken_text_sha256"]
    assert primary_metrics["voice_profile_id"] == clarity_metrics["voice_profile_id"]
    assert primary_metrics["pitch_semitones"] == clarity_metrics["pitch_semitones"] == -1
    assert clarity_metrics["pitch_variant_skipped"] == 0.0
    assert clarity_metrics["pitch_variant_mixed"] == 0.0
    assert clarity_metrics["tts_delivery_mode"] == DELIVERY_CLARITY


def test_short_utterance_repair_halves_a_persisted_generation_ceiling() -> None:
    sampling = vieneu_sampling_for_segment(
        {
            "text": "Vâng.",
            "speaker": "Nhân vật",
            "emotion": "neutral",
            "intensity": 3,
            "pace": "normal",
            "warning_code": "TTS_GENERATION_CEILING_REACHED|ASR_SEVERE_MISMATCH",
        },
        repair_short_utterance=True,
    )

    assert sampling["max_new_frames"] == 12


def test_short_utterance_attempt_count_does_not_enable_repair_budget() -> None:
    sampling = vieneu_sampling_for_segment(
        {
            "text": "Được rồi.",
            "speaker": "Nhân vật",
            "emotion": "neutral",
            "intensity": 3,
            "pace": "normal",
            "attempt_count": 2,
        },
        repair_short_utterance=True,
    )

    assert sampling["max_new_frames"] == 24


def test_persisted_generation_frame_cap_survives_without_attempt_warning() -> None:
    sampling = vieneu_sampling_for_segment(
        {
            "text": "Điên rồi!",
            "speaker": "Nhân vật",
            "emotion": "excited",
            "intensity": 3,
            "pace": "normal",
            "attempt_count": 9,
            "generation_frame_cap": 12,
        }
    )

    assert sampling["max_new_frames"] == 12


def test_short_utterance_ceiling_warning_only_caps_an_explicit_repair() -> None:
    row = {
        "text": "Được rồi.",
        "speaker": "Nhân vật",
        "emotion": "neutral",
        "intensity": 3,
        "pace": "normal",
        "warning_code": "TTS_GENERATION_CEILING_REACHED",
        "attempt_count": 9,
    }

    initial_sampling = vieneu_sampling_for_segment(row)
    repair_sampling = vieneu_sampling_for_segment(row, repair_short_utterance=True)

    assert initial_sampling["max_new_frames"] == 24
    assert repair_sampling["max_new_frames"] == 12


def test_single_syllable_repair_uses_a_micro_generation_budget() -> None:
    sampling = vieneu_sampling_for_segment(
        {
            "text": "Ừ?",
            "speaker": "Nhân vật",
            "emotion": "neutral",
            "intensity": 3,
            "pace": "normal",
            "warning_code": "TTS_GENERATION_CEILING_REACHED|ASR_SEVERE_MISMATCH",
        },
        repair_short_utterance=True,
    )

    assert sampling["max_new_frames"] == 6


def test_missing_locked_vieneu_preset_is_fatal() -> None:
    """A preset that is absent will still be absent after waiting, so stopping is right."""
    assert is_fatal_tts_error(
        RuntimeError("Locked VieNeu preset 'Phạm Tuyên' is unavailable; refusing to change voice silently")
    )


def test_an_allocation_failure_is_no_longer_fatal() -> None:
    """This assertion used to sit in the test above, and it was right when written.

    Retrying an out-of-memory error immediately just runs out of memory again, so with no
    way to release and wait, failing fast was the better of the two behaviours available.

    The pipeline now has a third: _recover_from_memory_pressure drops every model this
    process holds, waits up to half an hour for whoever took the memory to give it back,
    and retries the same attempt. That changes which classification is correct. The owner
    reported the old behaviour as a bug - opening Unity or Rider mid-run ended a book that
    had been running for hours - and asked for exactly this.

    Full split in test_memory_pressure_is_not_fatal.py.
    """
    message = "DefaultCPUAllocator: not enough memory: you tried to allocate 2442336000 bytes"
    assert not is_fatal_tts_error(RuntimeError(message))
    assert is_transient_tts_memory_error(RuntimeError(message))


def test_pitch_variant_preserves_duration_and_changes_waveform() -> None:
    sample_rate = 16_000
    time_axis = np.arange(sample_rate, dtype=np.float32) / sample_rate
    audio = sum(
        (1 / harmonic) * np.sin(2 * np.pi * 220 * harmonic * time_axis)
        for harmonic in range(1, 7)
    )
    audio = np.asarray(0.2 * audio / np.max(np.abs(audio)), dtype=np.float32)

    shifted = apply_pitch_variant(audio, sample_rate, 1)

    assert shifted.shape == audio.shape
    assert np.allclose(apply_pitch_variant(audio, sample_rate, 0), audio)
    assert not np.allclose(shifted, audio)
    input_peak = np.fft.rfftfreq(audio.size, 1 / sample_rate)[np.argmax(np.abs(np.fft.rfft(audio)))]
    shifted_peak = np.fft.rfftfreq(shifted.size, 1 / sample_rate)[
        np.argmax(np.abs(np.fft.rfft(shifted)))
    ]
    assert input_peak == pytest.approx(220.0, abs=2.0)
    assert shifted_peak == pytest.approx(220.0 * 2 ** (1 / 12), abs=2.0)


def test_world_pitch_variant_changes_f0_but_reuses_voice_envelopes(monkeypatch) -> None:
    source_f0 = np.asarray([0.0, 100.0, 110.0, 120.0, 0.0], dtype=np.float64)
    time_axis = np.arange(source_f0.size, dtype=np.float64) * 0.005
    spectral_envelope = np.full((source_f0.size, 4), 2.0, dtype=np.float64)
    aperiodicity = np.full((source_f0.size, 4), 3.0, dtype=np.float64)
    synthesized: dict[str, np.ndarray] = {}

    monkeypatch.setattr(
        tts_module.pyworld,
        "harvest",
        lambda *_args, **_kwargs: (source_f0.copy(), time_axis),
    )
    monkeypatch.setattr(
        tts_module.pyworld,
        "stonemask",
        lambda _audio, f0, _time_axis, _sample_rate: f0,
    )
    monkeypatch.setattr(
        tts_module.pyworld,
        "cheaptrick",
        lambda *_args, **_kwargs: spectral_envelope,
    )
    monkeypatch.setattr(
        tts_module.pyworld,
        "d4c",
        lambda *_args, **_kwargs: aperiodicity,
    )

    def synthesize(f0, envelope, periodicity, *_args, **_kwargs):
        synthesized["f0"] = f0
        synthesized["envelope"] = envelope
        synthesized["aperiodicity"] = periodicity
        return np.ones(800, dtype=np.float64)

    monkeypatch.setattr(tts_module.pyworld, "synthesize", synthesize)

    shifted = apply_pitch_variant(np.ones(800, dtype=np.float32), 16_000, -1)

    assert shifted.shape == (800,)
    assert synthesized["f0"][[0, 4]].tolist() == [0.0, 0.0]
    assert synthesized["f0"][1:4] == pytest.approx(source_f0[1:4] * 2 ** (-1 / 12))
    assert synthesized["envelope"] is spectral_envelope
    assert synthesized["aperiodicity"] is aperiodicity


def test_world_pitch_variant_strict_mode_rejects_zero_padding(monkeypatch) -> None:
    source_f0 = np.asarray([100.0, 105.0, 110.0], dtype=np.float64)
    time_axis = np.arange(source_f0.size, dtype=np.float64) * 0.005
    monkeypatch.setattr(
        tts_module.pyworld,
        "harvest",
        lambda *_args, **_kwargs: (source_f0.copy(), time_axis),
    )
    monkeypatch.setattr(
        tts_module.pyworld,
        "stonemask",
        lambda _audio, f0, _time_axis, _sample_rate: f0,
    )
    monkeypatch.setattr(
        tts_module.pyworld,
        "cheaptrick",
        lambda *_args, **_kwargs: np.ones((3, 4), dtype=np.float64),
    )
    monkeypatch.setattr(
        tts_module.pyworld,
        "d4c",
        lambda *_args, **_kwargs: np.ones((3, 4), dtype=np.float64),
    )
    monkeypatch.setattr(
        tts_module.pyworld,
        "synthesize",
        lambda *_args, **_kwargs: np.ones(7, dtype=np.float64),
    )
    audio = np.ones(8, dtype=np.float32)

    with pytest.raises(ValueError, match="no-padding"):
        apply_pitch_variant(audio, 16_000, 1, allow_padding=False)

    padded = apply_pitch_variant(audio, 16_000, 1)
    assert padded.shape == audio.shape
    assert padded[-1] == 0.0


def test_standalone_gasp_preserves_raw_audio_after_pitch_with_exact_provenance(
    tmp_path: Path,
    monkeypatch,
) -> None:
    db = ProjectDB(tmp_path / "project.sqlite3")
    profile_id = db.upsert_voice_profile({
        "voice_key": "gasp-speaker",
        "engine": "vieneu",
        "preset_name": "Xuân Vĩnh",
        "description": "Gasp test voice",
        "seed": 1234,
        "pitch_semitones": 1,
        "status": "ready",
    })
    settings = build_settings("high_quality")
    coordinator = TTSCoordinator(settings, db, lambda _message: None)
    sample_rate = coordinator.vieneu.sample_rate
    original_samples = int(round(1.44 * sample_rate))
    captured: dict[str, object] = {}

    def generate_one(spoken_row, _profile, _seed, *, sampling):
        captured["spoken_text"] = spoken_row["text"]
        captured["sampling"] = dict(sampling)
        return np.full(original_samples, 0.05, dtype=np.float32)

    def apply_pitch(
        audio,
        received_sample_rate,
        pitch_steps,
        *,
        allow_padding=True,
    ):
        captured["pitch_input_samples"] = np.asarray(audio).size
        captured["pitch_steps"] = pitch_steps
        captured["allow_padding"] = allow_padding
        assert received_sample_rate == sample_rate
        return np.asarray(audio, dtype=np.float32) * 2.0

    def write_wav(_output, audio, received_sample_rate, text, _settings, *, segment):
        array = np.asarray(audio, dtype=np.float32)
        captured["written_audio"] = array
        captured["written_text"] = text
        captured["written_segment"] = segment
        assert received_sample_rate == sample_rate
        return "checksum", {
            "duration": array.size / received_sample_rate,
            "trailing_rms": 0.0,
        }

    monkeypatch.setattr(coordinator, "generation_seed", lambda _row, _salt="": 44963260)
    monkeypatch.setattr(coordinator.vieneu, "generate_one", generate_one)
    monkeypatch.setattr(tts_module, "apply_pitch_variant", apply_pitch)
    monkeypatch.setattr(tts_module, "atomic_write_wav", write_wav)

    _checksum, metrics, seed = coordinator.synthesize_atomic(
        {
            "voice_profile_id": profile_id,
            "stable_id": "standalone_gasp_1",
            "text": "“Ha…”",
            "kind": "dialogue",
            "speaker": "Nhân vật",
        },
        tmp_path / "gasp.wav",
        delivery_mode=DELIVERY_CLARITY,
    )

    sampling = captured["sampling"]
    written_audio = captured["written_audio"]
    assert isinstance(sampling, dict)
    assert isinstance(written_audio, np.ndarray)
    assert seed == 44963260
    assert captured["spoken_text"] == "“Ha ha.”"
    assert captured["written_text"] == "“Ha ha.”"
    assert captured["pitch_input_samples"] == original_samples
    assert captured["pitch_steps"] == 1
    assert captured["allow_padding"] is False
    assert sampling["temperature"] == pytest.approx(0.55)
    assert sampling["top_p"] == pytest.approx(0.82)
    assert sampling["max_new_frames"] == HA_VOCALIZATION_MAX_NEW_FRAMES
    assert written_audio.size == original_samples
    assert np.allclose(written_audio, 0.10)
    assert metrics[HA_VOCALIZATION_PROFILE_FIELD] == (
        HA_VOCALIZATION_DELIVERY_PROFILE
    )
    assert metrics[HA_VOCALIZATION_TEMPERATURE_FIELD] == pytest.approx(0.55)
    assert metrics[HA_VOCALIZATION_TOP_P_FIELD] == pytest.approx(0.82)
    assert metrics[HA_VOCALIZATION_MAX_NEW_FRAMES_FIELD] == (
        HA_VOCALIZATION_MAX_NEW_FRAMES
    )
    assert metrics[HA_VOCALIZATION_SAMPLE_RATE_FIELD] == sample_rate
    assert metrics[HA_VOCALIZATION_ORIGINAL_SAMPLES_FIELD] == original_samples
    assert metrics[HA_VOCALIZATION_TARGET_SAMPLES_FIELD] == original_samples
    assert metrics[HA_VOCALIZATION_PADDING_SAMPLES_FIELD] == 0
    assert metrics[HA_VOCALIZATION_FINAL_SAMPLES_FIELD] == original_samples
    assert "generation_ceiling_hit" not in metrics
    assert metrics["generation_endpoint_active"] == 0.0


def test_standalone_gasp_discards_a_shortened_pitch_variant(
    tmp_path: Path,
    monkeypatch,
) -> None:
    db = ProjectDB(tmp_path / "project.sqlite3")
    profile_id = db.upsert_voice_profile({
        "voice_key": "gasp-short-pitch",
        "engine": "vieneu",
        "preset_name": "Xuân Vĩnh",
        "description": "Short pitch fallback voice",
        "seed": 4321,
        "pitch_semitones": 1,
        "status": "ready",
    })
    logs: list[str] = []
    coordinator = TTSCoordinator(build_settings("high_quality"), db, logs.append)
    raw_audio = np.full(2_400, 0.05, dtype=np.float32)
    captured: dict[str, object] = {}

    monkeypatch.setattr(coordinator, "generation_seed", lambda _row, _salt="": 17)
    monkeypatch.setattr(
        coordinator.vieneu,
        "generate_one",
        lambda *_args, **_kwargs: raw_audio.copy(),
    )

    def shorten_pitch(audio, _sample_rate, _steps, *, allow_padding=True):
        captured["allow_padding"] = allow_padding
        return np.asarray(audio, dtype=np.float32)[:-1]

    def write_wav(_output, audio, *_args, **_kwargs):
        captured["written_audio"] = np.asarray(audio, dtype=np.float32).copy()
        return "checksum", {"duration": 0.05, "trailing_rms": 0.0}

    monkeypatch.setattr(tts_module, "apply_pitch_variant", shorten_pitch)
    monkeypatch.setattr(tts_module, "atomic_write_wav", write_wav)

    _checksum, metrics, _seed = coordinator.synthesize_atomic(
        {
            "voice_profile_id": profile_id,
            "stable_id": "standalone_gasp_short_pitch",
            "text": "“Ha…”",
            "kind": "dialogue",
            "speaker": "Nhân vật",
        },
        tmp_path / "gasp-short-pitch.wav",
    )

    written_audio = captured["written_audio"]
    assert isinstance(written_audio, np.ndarray)
    assert captured["allow_padding"] is False
    assert np.array_equal(written_audio, raw_audio)
    assert metrics["pitch_variant_skipped"] == 1.0
    assert metrics["effective_pitch_semitones"] == 0
    assert metrics[HA_VOCALIZATION_ORIGINAL_SAMPLES_FIELD] == raw_audio.size
    assert metrics[HA_VOCALIZATION_TARGET_SAMPLES_FIELD] == raw_audio.size
    assert metrics[HA_VOCALIZATION_PADDING_SAMPLES_FIELD] == 0
    assert metrics[HA_VOCALIZATION_FINAL_SAMPLES_FIELD] == raw_audio.size
    assert any("Bỏ biến thể cao độ" in message for message in logs)


def test_coordinator_releases_inference_cache_after_success_and_failure(
    tmp_path: Path,
    monkeypatch,
) -> None:
    db = ProjectDB(tmp_path / "project.sqlite3")
    profile_id = db.upsert_voice_profile({
        "voice_key": "narrator",
        "engine": "vieneu",
        "preset_name": "Thái Sơn",
        "description": "Nam · Nam · Kể chuyện",
        "seed": 1234,
        "pitch_semitones": 1,
        "status": "ready",
    })
    logs: list[str] = []
    coordinator = TTSCoordinator(build_settings(), db, logs.append)
    row = {
        "voice_profile_id": profile_id,
        "stable_id": "segment_1",
        "text": "Một câu kiểm tra.",
        "kind": "narration",
    }
    release_calls = 0

    def release_cache() -> None:
        nonlocal release_calls
        release_calls += 1

    monkeypatch.setattr(coordinator, "release_inference_cache", release_cache)
    monkeypatch.setattr(coordinator, "generation_seed", lambda _row, _salt="": 1)
    monkeypatch.setattr(
        coordinator.vieneu,
        "generate_one",
        lambda _row, _profile, _seed, **_kwargs: np.asarray([0.1, -0.1], dtype=np.float32),
    )
    monkeypatch.setattr(tts_module, "apply_pitch_variant", lambda audio, *_args: audio)
    monkeypatch.setattr(
        tts_module,
        "atomic_write_wav",
        lambda *_args, **_kwargs: ("checksum", {"duration": 1.0}),
    )

    _checksum, primary_metrics, _seed = coordinator.synthesize_atomic(
        row,
        tmp_path / "segment.wav",
    )
    assert release_calls == 1
    assert primary_metrics["tts_delivery_mode"] == "primary"
    assert primary_metrics["spoken_text_sha256"] == hashlib.sha256(
        row["text"].encode("utf-8")
    ).hexdigest()
    assert primary_metrics["voice_profile_id"] == profile_id
    assert primary_metrics["pitch_semitones"] == 1
    assert primary_metrics["pitch_variant_skipped"] == 0.0
    assert primary_metrics["pitch_variant_mixed"] == 0.0

    monkeypatch.setattr(
        tts_module,
        "apply_pitch_variant",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            MemoryError("pitch allocation failed")
        ),
    )
    _checksum, fallback_metrics, _seed = coordinator.synthesize_atomic(
        row,
        tmp_path / "segment.wav",
    )
    assert fallback_metrics["pitch_variant_skipped"] == 1.0
    assert fallback_metrics["pitch_variant_mixed"] == 0.0
    assert any("Bỏ biến thể cao độ" in message for message in logs)
    assert release_calls == 2

    def fail_generation(*_args, **_kwargs) -> np.ndarray:
        raise AudioQualityError("inference failed")

    monkeypatch.setattr(coordinator.vieneu, "generate_one", fail_generation)
    with pytest.raises(AudioQualityError, match="inference failed"):
        coordinator.synthesize_atomic(row, tmp_path / "segment.wav")
    assert release_calls == 3

    ceiling_row = {**row, "text": "“Ha…”"}
    spoken_text = coordinator.spoken_text(ceiling_row)
    policy = segment_duration_policy(spoken_text, build_settings(), ceiling_row)
    monkeypatch.setattr(
        coordinator.vieneu,
        "generate_one",
        lambda *_args, **_kwargs: np.zeros(
            policy.generation_max_frames * VIENEU_V3_CODEC_SAMPLES_PER_FRAME,
            dtype=np.float32,
        ),
    )
    _checksum, ceiling_metrics, _seed = coordinator.synthesize_atomic(
        ceiling_row,
        tmp_path / "segment.wav",
    )
    assert ceiling_metrics["generation_ceiling_hit"] == 1.0
    assert release_calls == 4


def test_vieneu_unload_trims_process_working_set(monkeypatch) -> None:
    trims: list[bool] = []
    engine = VieNeuEngine(build_settings(), lambda _message: None)
    engine.tts = object()
    engine.voices = ["Phạm Tuyên"]
    monkeypatch.setattr(engine, "release_inference_cache", lambda: None)
    monkeypatch.setattr(tts_module, "trim_process_working_set", lambda: trims.append(True))

    engine.unload()

    assert engine.tts is None
    assert engine.voices == []
    assert trims == [True]


def test_vieneu_unload_without_model_is_a_no_op(monkeypatch) -> None:
    releases: list[bool] = []
    trims: list[bool] = []
    engine = VieNeuEngine(build_settings(), lambda _message: None)
    monkeypatch.setattr(engine, "release_inference_cache", lambda: releases.append(True))
    monkeypatch.setattr(tts_module, "trim_process_working_set", lambda: trims.append(True))

    engine.unload()

    assert releases == []
    assert trims == []


def test_repair_uses_effective_frame_cap_for_inference_and_ceiling_detection(
    tmp_path: Path,
    monkeypatch,
) -> None:
    db = ProjectDB(tmp_path / "project.sqlite3")
    profile_id = db.upsert_voice_profile({
        "voice_key": "narrator",
        "engine": "vieneu",
        "preset_name": "Thái Sơn",
        "description": "Nam · Nam · Kể chuyện",
        "seed": 1234,
        "pitch_semitones": 0,
        "status": "ready",
    })
    coordinator = TTSCoordinator(build_settings(), db, lambda _message: None)
    row = {
        "voice_profile_id": profile_id,
        "stable_id": "short_repair_1",
        "text": "Vâng.",
        "kind": "dialogue",
        "speaker": "Nhân vật",
        "warning_code": "TTS_GENERATION_CEILING_REACHED",
    }
    received_sampling: dict[str, float | int] = {}

    def generate_one(_row, _profile, _seed, *, sampling):
        received_sampling.update(sampling)
        return np.zeros(
            int(sampling["max_new_frames"]) * VIENEU_V3_CODEC_SAMPLES_PER_FRAME,
            dtype=np.float32,
        )

    monkeypatch.setattr(coordinator.vieneu, "generate_one", generate_one)
    monkeypatch.setattr(tts_module, "apply_pitch_variant", lambda audio, *_args: audio)
    monkeypatch.setattr(
        tts_module,
        "atomic_write_wav",
        lambda *_args, **_kwargs: (
            "checksum",
            {"duration": 0.96, "trailing_rms": 0.1},
        ),
    )

    _checksum, metrics, _seed = coordinator.synthesize_atomic(
        row,
        tmp_path / "short-repair.wav",
        repair_short_utterance=True,
    )

    assert received_sampling["max_new_frames"] == 12
    assert metrics["generation_ceiling_hit"] == 1.0
    assert metrics["generation_endpoint_active"] == 1.0


def test_thought_always_uses_narrator_profile_even_if_row_contains_character_cast(
    tmp_path: Path,
    monkeypatch,
) -> None:
    db = ProjectDB(tmp_path / "project.sqlite3")
    narrator_profile_id = db.upsert_voice_profile({
        "voice_key": "narrator",
        "engine": "vieneu",
        "preset_name": "Phạm Tuyên",
        "description": "Người kể",
        "seed": 1,
        "pitch_semitones": 0,
        "status": "ready",
    })
    character_profile_id = db.upsert_voice_profile({
        "voice_key": "lucien",
        "engine": "vieneu",
        "preset_name": "Thanh Bình",
        "description": "Lucien",
        "seed": 2,
        "pitch_semitones": 0,
        "status": "ready",
    })
    coordinator = TTSCoordinator(build_settings(), db, lambda _message: None)
    row = {
        "voice_profile_id": character_profile_id,
        "stable_id": "thought_1",
        "text": "‘Mình phải làm gì đây?’",
        "kind": "thought",
        "speaker": "Lucien",
    }
    generated: dict[str, object] = {}

    def generate(spoken_row, profile, _seed, **_kwargs):
        generated["row"] = spoken_row
        generated["profile"] = profile
        return np.asarray([0.1, -0.1], dtype=np.float32)

    monkeypatch.setattr(coordinator.vieneu, "generate_one", generate)
    monkeypatch.setattr(tts_module, "apply_pitch_variant", lambda audio, *_args: audio)
    monkeypatch.setattr(
        tts_module,
        "atomic_write_wav",
        lambda *_args, **_kwargs: ("checksum", {"duration": 1.0}),
    )

    coordinator.synthesize_atomic(row, tmp_path / "thought.wav")

    spoken_row = generated["row"]
    profile = generated["profile"]
    assert spoken_row["speaker"] == "NARRATOR"
    assert int(spoken_row["voice_profile_id"]) == narrator_profile_id
    assert str(profile["voice_key"]) == "narrator"


def test_every_sampling_cap_can_actually_bind() -> None:
    """A cap above the value it clamps is a rule that silently does nothing.

    Clarity repair sat at 0.78 while neutral generated at 0.74, so the mode meant to cut
    variance after an ASR failure was inert for most of the book and nobody noticed. The
    fix for one cap is worth little if the next one drifts the same way, so this pins the
    property for all of them: a cap exists to lower something, and must be able to.
    """
    caps = {
        "CLARITY_MAX_TEMPERATURE": (CLARITY_MAX_TEMPERATURE, GENERATION_TEMPERATURE),
        "CLARITY_MAX_TOP_P": (CLARITY_MAX_TOP_P, GENERATION_TOP_P),
        "SHORT_UTTERANCE_MAX_TEMPERATURE": (
            SHORT_UTTERANCE_MAX_TEMPERATURE,
            GENERATION_TEMPERATURE,
        ),
        "SHORT_UTTERANCE_MAX_TOP_P": (SHORT_UTTERANCE_MAX_TOP_P, GENERATION_TOP_P),
        "HA_VOCALIZATION_MAX_TEMPERATURE": (
            HA_VOCALIZATION_MAX_TEMPERATURE,
            GENERATION_TEMPERATURE,
        ),
        "HA_VOCALIZATION_MAX_TOP_P": (HA_VOCALIZATION_MAX_TOP_P, GENERATION_TOP_P),
    }
    inert = {
        name: (cap, generated)
        for name, (cap, generated) in caps.items()
        if cap >= generated
    }
    assert not inert, f"caps that can never lower anything: {inert}"
