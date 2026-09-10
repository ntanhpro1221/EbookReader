"""Một nhãn "tên + họ bịa" với một câu là chính nhân vật ấy, không phải người mới.

Đếm trên ba lô: ALICE (25 câu) còn có ALICE DRACEN (0) và ALICE VIC. DRAKEN (1) - hai cái họ
khác nhau cho cùng một người; SELNE (32) còn có SELNE VALKRYN (3). Mỗi nhãn lạc chiếm một chỗ
trong kho giọng và ALICE VIC. DRAKEN đã va chạm với THALIA ở lô 3.

Hai ngưỡng cùng lúc - dài ≤ 3 câu VÀ ngắn ≥ 10× - vì mỗi cái riêng lẻ đều gộp nhầm được, và bài
thứ ba ở đây là cái giữ JAKE / JAKE SMITH cha con không bị gộp.
"""
from __future__ import annotations

from pathlib import Path

from ebook_reader.character_registry import (
    STRAY_SURNAME_MAX_LINES,
    STRAY_SURNAME_MIN_RATIO,
    build_registry_and_cast,
)
from ebook_reader.config import build_settings

from tests.test_character_casting import _identity_db


def test_a_one_line_surname_label_folds_into_the_character(tmp_path: Path) -> None:
    db = _identity_db(
        tmp_path,
        [("ALICE", "female")] * 25 + [("ALICE VIC. DRAKEN", "female")] + [("THALIA", "female")],
    )

    build_registry_and_cast(db, build_settings(), lambda _message: None)

    rows = db.list_segments()
    assert {str(row["speaker"]) for row in rows} == {"ALICE", "THALIA"}
    alice = [row for row in rows if str(row["speaker"]) == "ALICE"]
    assert len(alice) == 26
    assert len({int(row["voice_profile_id"]) for row in alice}) == 1


def test_two_invented_surnames_both_fold_into_the_same_person(tmp_path: Path) -> None:
    """Lô 2 gọi là DRACEN, lô 3 gọi là DRAKEN. Cả hai về ALICE."""
    db = _identity_db(
        tmp_path,
        [("ALICE", "female")] * 30
        + [("ALICE DRACEN", "female")] * 2
        + [("ALICE VIC. DRAKEN", "female")],
    )

    build_registry_and_cast(db, build_settings(), lambda _message: None)

    assert {str(row["speaker"]) for row in db.list_segments()} == {"ALICE"}


def test_a_real_father_and_son_are_left_alone(tmp_path: Path) -> None:
    """JAKE 300 câu, JAKE SMITH 30 câu: tỉ lệ 10× lọt ngưỡng thứ hai, nhưng 30 > 3 nên ngưỡng
    thứ nhất giữ họ là hai người. Đây là bài quan trọng nhất trong file."""
    assert STRAY_SURNAME_MAX_LINES < 30 and 300 >= 30 * STRAY_SURNAME_MIN_RATIO
    db = _identity_db(
        tmp_path,
        [("JAKE", "male")] * 300 + [("JAKE SMITH", "male")] * 30,
    )

    build_registry_and_cast(db, build_settings(), lambda _message: None)

    assert {str(row["speaker"]) for row in db.list_segments()} == {"JAKE", "JAKE SMITH"}


def test_a_rare_short_name_does_not_swallow_a_long_one(tmp_path: Path) -> None:
    """Ngưỡng tỉ lệ: ALICE 5 câu không được nuốt ALICE VIC. DRAKEN 1 câu - 5 < 10×1."""
    db = _identity_db(
        tmp_path,
        [("ALICE", "female")] * 5 + [("ALICE VIC. DRAKEN", "female")],
    )

    build_registry_and_cast(db, build_settings(), lambda _message: None)

    assert {str(row["speaker"]) for row in db.list_segments()} == {"ALICE", "ALICE VIC. DRAKEN"}
