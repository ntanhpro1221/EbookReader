"""Cổng nhịp đo một giọng chậm theo nhịp của chính nó - và chỉ sàn, chỉ một chiều."""
from __future__ import annotations

import inspect
import re

import numpy as np
import pytest

from ebook_reader import audio_io, pipeline, tts, voice_catalog
from ebook_reader.audio_io import (
    VOICE_PRESET_FIELD,
    pace_is_outlier,
    segment_duration_policy,
    spoken_speakable_chars,
    validate_audio_array,
)
from ebook_reader.config import build_settings
from ebook_reader.voice_catalog import (
    PACE_SCALE_MAX,
    PACE_SCALE_MIN,
    PRESET_PACE_SCALE,
    VIENEU_PRESETS,
    pace_scale_for_preset,
)

NORMAL = (12.5, 24.5)
RATE = 48_000
SLOW_VOICE = "Giọng Kể Chậm"
# Không dấu câu nên không có ngân sách nghỉ: nhịp = ký tự đọc được / thời lượng.
LINE = "Người kể chuyện đọc thật chậm rãi từng chữ một trong đêm dài"


def _tone(seconds: float) -> np.ndarray:
    count = int(round(RATE * seconds))
    return (0.3 * np.sin(np.linspace(0.0, 2 * np.pi * 180 * seconds, count))).astype(np.float32)


def test_the_floor_moves_with_the_voice() -> None:
    # 11 kt/s, 3,3 âm tiết/s: chậm theo băng chung, bình thường với một giọng 0,81.
    assert pace_is_outlier(11.0, 3.3, "normal", NORMAL)
    assert not pace_is_outlier(11.0, 3.3, "normal", NORMAL, floor_scale=0.81)


def test_the_ceiling_does_not() -> None:
    assert pace_is_outlier(26.0, 7.0, "normal", NORMAL, floor_scale=0.81)
    assert not pace_is_outlier(20.0, 6.0, "normal", NORMAL, floor_scale=0.81)


def test_a_voice_nobody_measured_keeps_the_shared_band() -> None:
    assert pace_scale_for_preset("a preset nobody measured") == 1.0
    assert pace_scale_for_preset("") == 1.0


def test_every_catalogued_scale_only_loosens_and_names_a_real_preset() -> None:
    names = {preset["name"] for preset in VIENEU_PRESETS}
    for name, scale in PRESET_PACE_SCALE.items():
        assert name in names, name
        assert PACE_SCALE_MIN <= scale <= PACE_SCALE_MAX, name


def test_the_gate_reads_the_voice_from_the_segment(monkeypatch) -> None:
    monkeypatch.setitem(PRESET_PACE_SCALE, SLOW_VOICE, 0.81)
    settings = build_settings("high_quality")
    audio = _tone(spoken_speakable_chars(LINE) / 11.0)
    plain = {"pace": "normal", "kind": "narration", "text": LINE}
    _, shared = validate_audio_array(audio, LINE, settings, RATE, plain)
    _, own = validate_audio_array(audio, LINE, settings, RATE, {**plain, VOICE_PRESET_FIELD: SLOW_VOICE})
    assert shared["chars_per_second"] == pytest.approx(11.0, rel=0.02)
    assert shared["pace_outlier"] == 1.0
    assert own["pace_outlier"] == 0.0
    assert own["pace_scale"] == 0.81
    assert "pace_scale" not in shared


def test_a_database_row_without_the_field_is_judged_by_the_shared_band() -> None:
    import sqlite3

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT 'normal' AS pace, 'narration' AS kind, ? AS text", (LINE,)).fetchone()
    settings = build_settings("high_quality")
    audio = _tone(spoken_speakable_chars(LINE) / 11.0)
    _, metrics = validate_audio_array(audio, LINE, settings, RATE, row)
    assert metrics["pace_outlier"] == 1.0
    segment_duration_policy(LINE, settings, row)


def test_a_slow_voice_gets_the_frames_its_raw_take_needs(monkeypatch) -> None:
    monkeypatch.setitem(PRESET_PACE_SCALE, SLOW_VOICE, 0.81)
    monkeypatch.setitem(voice_catalog.PRESET_SPEED_FACTOR, SLOW_VOICE, 1.10)
    settings = build_settings("high_quality")
    text = LINE + " " + LINE
    plain = {"pace": "normal", "kind": "narration", "text": text}
    shared = segment_duration_policy(text, settings, plain).generation_max_frames
    own = segment_duration_policy(text, settings, {**plain, VOICE_PRESET_FIELD: SLOW_VOICE})
    assert own.generation_max_frames > shared
    assert own.generation_ceiling_seconds < own.validation_max_seconds


def test_synthesis_names_the_voice_before_the_budget_and_the_gate() -> None:
    source = inspect.getsource(tts.TTSCoordinator.synthesize_atomic)
    named = source.index("spoken_row[VOICE_PRESET_FIELD]")
    assert named < source.index("vieneu_sampling_for_segment(")
    assert named < source.index("segment_duration_policy(")
    assert named < source.index("atomic_write_wav(")


def test_every_later_look_at_a_take_uses_the_same_band() -> None:
    source = inspect.getsource(pipeline)
    calls = re.findall(r"inspect_wav\((.*?)\n\s*\)", source, flags=re.S)
    assert calls, "khong tim thay loi goi inspect_wav nao"
    for call in calls:
        assert "segment=self._segment_for_audio_check(row)" in call, call
