"""Người nghe ghim được TUỔI, và thứ người đã ghim thắng giọng mang sang từ lô trước.

Ca thật: IVAN bị lô 3 gọi là `child` một lần (mọi `segments.age` của anh ta là `unknown`), được
cấp giọng nữ kéo cao, và `port_casting` mang giọng ấy sang mọi lô sau - 17 câu ở chương 062. Thoại
của anh ta là của một thanh niên hay lắp. Trước bản vá này không lệnh nào sửa được: `cast` chỉ
ghim phái, mà tuổi mới chọn họ giọng.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from ebook_reader.analysis import ALLOWED_AGES
from ebook_reader.character_registry import (
    _drop_pins_that_contradict_a_person,
    preset_gender_of_voice_key,
)
from ebook_reader.database import LOCKABLE_AGES, ProjectDB


class _Events:
    def __init__(self) -> None:
        self.said: list[str] = []
        self.events: list[tuple] = []

    def event(self, level, code, message, details=None) -> None:  # noqa: ANN001
        self.events.append((level, code, message, details))

    def log(self, message: str) -> None:
        self.said.append(message)


def test_the_lockable_ages_are_a_subset_of_what_analysis_allows() -> None:
    """Hai danh sách ở hai module không được trôi khỏi nhau; `unknown` cố ý không ghim được."""
    assert LOCKABLE_AGES <= ALLOWED_AGES
    assert "unknown" in ALLOWED_AGES and "unknown" not in LOCKABLE_AGES


def test_pinning_an_age_does_not_pin_a_gender(tmp_path: Path) -> None:
    """Cột `locked` là của phái. Ghim tuổi qua nó sẽ cho nhân vật một cái phái chưa ai quyết."""
    db = ProjectDB(tmp_path / "project.sqlite3")
    db.upsert_character(
        canonical_name="IVAN", display_name="Ivan", gender="male", age="child",
        personality="", mentions=22, importance="main", confidence=0.9,
    )

    db.lock_character_age("IVAN", "adult")

    assert db.locked_character_ages() == {"IVAN": "adult"}
    assert db.locked_character_genders() == {}, "chưa ai ghim phái của IVAN"
    assert str(db.list_characters()[0]["age"]) == "adult", "`age` cũng phải đổi, không chỉ cột ghim"


def test_an_age_outside_the_list_is_refused(tmp_path: Path) -> None:
    db = ProjectDB(tmp_path / "project.sqlite3")
    for bad in ("unknown", "grown-up", ""):
        with pytest.raises(ValueError):
            db.lock_character_age("IVAN", bad)


def test_pinning_before_analysis_creates_the_row(tmp_path: Path) -> None:
    """`port_casting` chạy giữa `create` và `run`, nên hàng có thể chưa tồn tại."""
    db = ProjectDB(tmp_path / "project.sqlite3")

    db.lock_character_age("  Ivan  ", "young")

    assert db.locked_character_ages() == {"IVAN": "young"}


def test_the_preset_behind_a_voice_key_is_read_longest_prefix_first() -> None:
    assert preset_gender_of_voice_key("preset_ngoc_linh_f107_p+02") == "female"
    assert preset_gender_of_voice_key("preset_thanh_binh_f100_p-04") == "male"
    assert preset_gender_of_voice_key("narrator") is None


def test_a_pinned_person_outranks_a_ported_voice(tmp_path: Path) -> None:
    """IVAN: người nghe ghim `male`/`adult`, giọng mang sang là preset nữ -> bỏ pin, cấp lại."""
    db = ProjectDB(tmp_path / "project.sqlite3")
    sink = _Events()
    db.event = sink.event  # type: ignore[method-assign]

    kept = _drop_pins_that_contradict_a_person(
        db,
        {"IVAN": "preset_ngoc_linh_f107_p+02", "WILL": "preset_thai_son_f100_p+00"},
        {"IVAN": "male", "WILL": "male"},
        {"IVAN": "adult"},
        sink.log,
    )

    assert kept == {"WILL": "preset_thai_son_f100_p+00"}
    assert [e[1] for e in sink.events] == ["CASTING_PIN_CONTRADICTS_A_PERSON"]
    assert "IVAN" in sink.said[0] and "cấp lại" in sink.said[0]


def test_a_child_keeps_a_cross_gender_voice(tmp_path: Path) -> None:
    """EVERAN là trẻ con thật: preset nữ kéo cao là ĐÚNG cách dự án đọc trẻ con, giữ pin."""
    db = ProjectDB(tmp_path / "project.sqlite3")
    sink = _Events()
    db.event = sink.event  # type: ignore[method-assign]

    kept = _drop_pins_that_contradict_a_person(
        db,
        {"EVERAN": "preset_ngoc_linh_f107_p+02"},
        {"EVERAN": "male"},
        {"EVERAN": "child"},
        sink.log,
    )

    assert kept == {"EVERAN": "preset_ngoc_linh_f107_p+02"}
    assert sink.events == []


def test_a_pin_nobody_ruled_on_is_left_alone(tmp_path: Path) -> None:
    """Không ai ghim phái thì không có gì để trái: giữ pin, đừng đoán."""
    db = ProjectDB(tmp_path / "project.sqlite3")
    sink = _Events()
    db.event = sink.event  # type: ignore[method-assign]

    kept = _drop_pins_that_contradict_a_person(
        db, {"IVAN": "preset_ngoc_linh_f107_p+02"}, {}, {"IVAN": "adult"}, sink.log
    )

    assert kept == {"IVAN": "preset_ngoc_linh_f107_p+02"}
    assert sink.events == []


def test_the_cast_command_takes_either_flag_or_both(tmp_path: Path) -> None:
    from types import SimpleNamespace

    from ebook_reader import cli

    root = tmp_path / "project"
    root.mkdir()
    ProjectDB(root / "project.sqlite3")
    (root / "book_settings.json").write_text("{}", encoding="utf-8")

    only_age = cli._command_cast(
        SimpleNamespace(project_root=root, character="IVAN", gender=None, age="adult", json=False)
    )
    only_gender = cli._command_cast(
        SimpleNamespace(project_root=root, character="WILL", gender="male", age=None, json=False)
    )
    neither = cli._command_cast(
        SimpleNamespace(project_root=root, character="NOBODY", gender=None, age=None, json=False)
    )
    both = cli._command_cast(
        SimpleNamespace(project_root=root, character="LILY", gender="female", age="teen", json=False)
    )

    assert only_age.ok and only_age.data["age"] == "adult" and "gender" not in only_age.data
    assert only_gender.ok and only_gender.data["gender"] == "male" and "age" not in only_gender.data
    assert not neither.ok and "--gender" in str(neither.error)
    assert both.ok and (both.data["gender"], both.data["age"]) == ("female", "teen")
    db = ProjectDB(root / "project.sqlite3")
    assert db.locked_character_ages() == {"IVAN": "adult", "LILY": "teen"}
    assert db.locked_character_genders() == {"WILL": "male", "LILY": "female"}


def test_a_project_older_than_the_column_is_migrated(tmp_path: Path) -> None:
    """Project của lô 1 không có cột `locked_age`; mở nó không được nổ."""
    path = tmp_path / "project.sqlite3"
    ProjectDB(path)
    with sqlite3.connect(str(path)) as conn:
        columns = {str(row[1]) for row in conn.execute("PRAGMA table_info(characters)")}
    assert "locked_age" in columns
