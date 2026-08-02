from __future__ import annotations

import sys
from pathlib import Path
from types import ModuleType

import numpy as np
import pytest

import ebook_reader.tts as tts_module
from ebook_reader.audio_io import AudioQualityError
from ebook_reader.config import build_settings
from ebook_reader.database import ProjectDB
from ebook_reader.tts import (
    TTSCoordinator,
    VieNeuEngine,
    apply_pitch_variant,
    is_fatal_tts_error,
    vieneu_sampling_for_segment,
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


def test_emotion_changes_delivery_but_not_locked_voice(monkeypatch) -> None:
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
    laughter = {
        **excited,
        "text": "“Ha…”",
        "kind": "vocal_effect",
    }

    engine.generate_one(neutral, profile, 1)
    engine.generate_one(excited, profile, 2)
    engine.generate_one(laughter, profile, 3)

    assert [call[1]["voice"] for call in runtime.calls] == ["Thái Sơn", "Thái Sơn", "Thái Sơn"]
    assert runtime.calls[0][0] == neutral["text"]
    assert runtime.calls[1][0] == neutral["text"]
    assert runtime.calls[2][0] == "[cười]"
    assert runtime.calls[1][1]["temperature"] > runtime.calls[0][1]["temperature"]
    assert runtime.calls[2][1]["max_new_frames"] < 300
    assert vieneu_sampling_for_segment(excited)["top_p"] > vieneu_sampling_for_segment(neutral)["top_p"]
    assert vieneu_sampling_for_segment({**neutral, "pace": "slow"})["silence_p"] > (
        vieneu_sampling_for_segment({**neutral, "pace": "fast"})["silence_p"]
    )


def test_missing_locked_vieneu_preset_is_fatal() -> None:
    assert is_fatal_tts_error(
        RuntimeError("Locked VieNeu preset 'Phạm Tuyên' is unavailable; refusing to change voice silently")
    )
    assert is_fatal_tts_error(
        RuntimeError("DefaultCPUAllocator: not enough memory: you tried to allocate 2442336000 bytes")
    )


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
        lambda _row, _profile, _seed: np.asarray([0.1, -0.1], dtype=np.float32),
    )
    monkeypatch.setattr(tts_module, "apply_pitch_variant", lambda audio, *_args: audio)
    monkeypatch.setattr(
        tts_module,
        "constrain_special_audio_duration",
        lambda audio, *_args: (audio, False),
    )
    monkeypatch.setattr(
        tts_module,
        "atomic_write_wav",
        lambda *_args, **_kwargs: ("checksum", {"duration": 1.0}),
    )

    coordinator.synthesize_atomic(row, tmp_path / "segment.wav")
    assert release_calls == 1

    monkeypatch.setattr(
        tts_module,
        "apply_pitch_variant",
        lambda *_args: (_ for _ in ()).throw(MemoryError("pitch allocation failed")),
    )
    _checksum, fallback_metrics, _seed = coordinator.synthesize_atomic(
        row,
        tmp_path / "segment.wav",
    )
    assert fallback_metrics["pitch_variant_skipped"] == 1.0
    assert any("Bỏ biến thể cao độ" in message for message in logs)
    assert release_calls == 2

    def fail_generation(*_args) -> np.ndarray:
        raise AudioQualityError("inference failed")

    monkeypatch.setattr(coordinator.vieneu, "generate_one", fail_generation)
    with pytest.raises(AudioQualityError, match="inference failed"):
        coordinator.synthesize_atomic(row, tmp_path / "segment.wav")
    assert release_calls == 3
