from __future__ import annotations

import sys
from pathlib import Path
from types import ModuleType

import numpy as np

import e_book_reader.tts as tts_module
from e_book_reader.config import build_settings
from e_book_reader.database import ProjectDB
from e_book_reader.tts import (
    VieNeuEngine,
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
