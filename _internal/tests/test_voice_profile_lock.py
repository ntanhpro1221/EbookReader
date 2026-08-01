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
    VoxCPM2Engine,
    is_fatal_tts_error,
    voxcpm_prompt_for_segment,
)


class FakeVoxModel:
    def __init__(self) -> None:
        self.kwargs = None

    def generate(self, **kwargs):
        self.kwargs = kwargs
        return np.asarray([0.1, -0.1], dtype=np.float32)


class FakeVieNeuRuntime:
    def list_preset_voices(self):
        return [
            ("Phạm Tuyên — Nam · Bắc · Phong cách tự nhiên", "Phạm Tuyên"),
            ("Thái Sơn — Nam · Nam · Phong cách kể chuyện", "Thái Sơn"),
        ]


def test_voice_profile_resume_preserves_committed_reference(tmp_path: Path) -> None:
    db = ProjectDB(tmp_path / "project.sqlite3")
    profile = {
        "voice_key": "char_lan",
        "engine": "voxcpm2",
        "preset_name": None,
        "description": "Giọng nữ trẻ Việt Nam",
        "seed": 1234,
        "status": "planned",
    }
    profile_id = db.upsert_voice_profile(profile)
    reference = tmp_path / "lan.wav"
    reference.write_bytes(b"wav")
    db.update_voice_reference(profile_id, reference_wav=reference, reference_sha256="abc")

    same_id = db.upsert_voice_profile(profile)
    fresh = db.voice_profile(same_id)

    assert same_id == profile_id
    assert fresh["reference_wav"] == str(reference.resolve())
    assert fresh["reference_sha256"] == "abc"
    assert fresh["status"] == "ready"


def test_voxcpm_seeds_runtime_without_forwarding_unsupported_keyword(monkeypatch) -> None:
    applied_seeds = []
    monkeypatch.setattr(tts_module, "_set_generation_seed", applied_seeds.append)
    model = FakeVoxModel()
    engine = VoxCPM2Engine(build_settings(), lambda _message: None)
    engine.model = model

    audio = engine.generate("Một câu kiểm thử.", seed=1234)

    assert applied_seeds == [1234]
    assert model.kwargs is not None
    assert "seed" not in model.kwargs
    assert model.kwargs["text"] == "Một câu kiểm thử."
    assert np.array_equal(audio, np.asarray([0.1, -0.1], dtype=np.float32))


def test_voxcpm_omits_long_control_for_tiny_utterances() -> None:
    row = {
        "text": "“Ha…”",
        "emotion": "surprised",
        "pace": "normal",
        "volume": "normal",
        "intensity": 3,
        "kind": "dialogue",
    }

    assert voxcpm_prompt_for_segment(row) == "“Ha…”"

    row["text"] = "Tôi không thể tin chuyện này là thật."
    prompt = voxcpm_prompt_for_segment(row)
    assert prompt.startswith("(")
    assert prompt.endswith(row["text"])


def test_vieneu_uses_voice_id_instead_of_display_label(monkeypatch) -> None:
    vieneu_module = ModuleType("vieneu")
    vieneu_module.Vieneu = lambda **_kwargs: FakeVieNeuRuntime()
    monkeypatch.setitem(sys.modules, "vieneu", vieneu_module)
    engine = VieNeuEngine(build_settings(), lambda _message: None)

    engine.load()

    assert engine.voices == ["Phạm Tuyên", "Thái Sơn"]
    assert engine.voice_for_profile(
        {"preset_name": "Phạm Tuyên", "voice_key": "narrator"},
        {"gender": "unknown"},
    ) == "Phạm Tuyên"


def test_missing_locked_vieneu_preset_is_fatal() -> None:
    assert is_fatal_tts_error(
        RuntimeError("Locked VieNeu preset 'Phạm Tuyên' is unavailable; refusing to change voice silently")
    )
