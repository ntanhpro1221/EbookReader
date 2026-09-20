"""Giọng mang pitch trẻ con bị bỏ khi người nghe đã ghim một tuổi khác trẻ con."""
from __future__ import annotations

from ebook_reader.character_registry import _drop_pins_that_contradict_a_person, voice_is_child_pitched


class _Events:
    def __init__(self) -> None:
        self.rows: list[tuple] = []

    def event(self, level: str, code: str, message: str, detail: dict) -> None:
        self.rows.append((level, code, message, detail))


def test_the_child_pitch_is_read_from_the_voice_key() -> None:
    assert voice_is_child_pitched("preset_ngoc_linh_f109_p+04") is True
    assert voice_is_child_pitched("preset_ngoc_linh_f100_p+00") is False
    # Formant khác mà pitch vẫn là pitch trẻ con -> vẫn là giọng trẻ con: formant là bước TÁCH giọng.
    assert voice_is_child_pitched("preset_ngoc_linh_f093_p+04") is True
    assert voice_is_child_pitched("narrator") is False
    assert voice_is_child_pitched("preset_khong_co_that_f100_p+00") is False


def test_a_pinned_adult_loses_a_child_pitched_voice() -> None:
    events = _Events()
    logs: list[str] = []
    kept = _drop_pins_that_contradict_a_person(
        events,
        {"KAELYN": "preset_ngoc_linh_f109_p+04"},
        {"KAELYN": "female"},
        {"KAELYN": "adult"},
        logs.append,
    )
    assert kept == {}
    assert "pitch trẻ con" in logs[0]
    assert events.rows and events.rows[0][1] == "CASTING_PIN_CONTRADICTS_A_PERSON"


def test_a_pinned_child_keeps_it() -> None:
    logs: list[str] = []
    kept = _drop_pins_that_contradict_a_person(
        _Events(),
        {"EVERAN": "preset_ngoc_linh_f109_p+04"},
        {"EVERAN": "male"},
        {"EVERAN": "child"},
        logs.append,
    )
    assert kept == {"EVERAN": "preset_ngoc_linh_f109_p+04"}, "trẻ con đọc bằng preset nữ kéo cao là có chủ ý"
    assert logs == []


def test_an_adult_voice_for_a_pinned_adult_is_untouched() -> None:
    kept = _drop_pins_that_contradict_a_person(
        _Events(),
        {"NATASHA": "preset_ngoc_linh_f100_p+00"},
        {"NATASHA": "female"},
        {"NATASHA": "adult"},
        lambda line: None,
    )
    assert kept == {"NATASHA": "preset_ngoc_linh_f100_p+00"}


def test_nobody_pinned_an_age_so_nothing_is_dropped() -> None:
    kept = _drop_pins_that_contradict_a_person(
        _Events(),
        {"AI": "preset_ngoc_linh_f109_p+04"},
        {},
        {},
        lambda line: None,
    )
    assert kept == {"AI": "preset_ngoc_linh_f109_p+04"}, "không ai ghim thì không kết tội"
