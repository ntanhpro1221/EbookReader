"""Giọng có đúng là giọng của người ấy không — và luật giọng trẻ con không được đếm là lỗi.

Bài quan trọng nhất ở đây là bài miễn trừ: dự án đọc trẻ con bằng preset **nữ** kéo cao formant,
vì preset nam dừng cách ống âm của một đứa trẻ 0,8 cm (`voice_catalog.AGE_TARGET_PITCH_HZ`). Một
công cụ không biết luật ấy sẽ báo EVERAN (nam, `child`, 36 câu) là lỗi, và người đọc báo cáo sẽ
thôi tin chín con số còn lại.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from scripts.voice_matches_the_person import (
    age_drift,
    chapter_batches,
    fold_names,
    preset_gender,
    read_rows,
    recast_arguments,
    shipped_rows,
    wrong_gender,
)

# rows = [(chương, tên, phái, tuổi, voice_key, số câu)]
Row = tuple[str, str, str, str, str, int]


def _project(root: Path, name: str, rows: list[Row]) -> Path:
    project = root / name
    project.mkdir(parents=True)
    conn = sqlite3.connect(str(project / "project.sqlite3"))
    try:
        conn.executescript(
            """
            CREATE TABLE chapters (id INTEGER PRIMARY KEY, title TEXT);
            CREATE TABLE characters (
                id INTEGER PRIMARY KEY, canonical_name TEXT, gender TEXT, age TEXT
            );
            CREATE TABLE voice_profiles (id INTEGER PRIMARY KEY, voice_key TEXT);
            CREATE TABLE segments (
                id INTEGER PRIMARY KEY, chapter_id INTEGER, canonical_character_id INTEGER,
                voice_profile_id INTEGER, kind TEXT
            );
            """
        )
        ids: dict[tuple[str, str], int] = {}

        def chapter(title: str) -> int:
            if ("chapters", title) not in ids:
                cur = conn.execute("INSERT INTO chapters (title) VALUES (?)", (title,))
                ids[("chapters", title)] = int(cur.lastrowid or 0)
            return ids[("chapters", title)]

        def character(name_: str, gender: str, age: str) -> int:
            if ("characters", name_) not in ids:
                cur = conn.execute(
                    "INSERT INTO characters (canonical_name, gender, age) VALUES (?,?,?)",
                    (name_, gender, age),
                )
                ids[("characters", name_)] = int(cur.lastrowid or 0)
            return ids[("characters", name_)]

        def voice(key: str) -> int:
            if ("voice_profiles", key) not in ids:
                cur = conn.execute("INSERT INTO voice_profiles (voice_key) VALUES (?)", (key,))
                ids[("voice_profiles", key)] = int(cur.lastrowid or 0)
            return ids[("voice_profiles", key)]

        for title, name_, gender, age, voice_key, lines in rows:
            for _ in range(lines):
                conn.execute(
                    "INSERT INTO segments (chapter_id, canonical_character_id,"
                    " voice_profile_id, kind) VALUES (?,?,?,'dialogue')",
                    (chapter(title), character(name_, gender, age), voice(voice_key)),
                )
        conn.commit()
    finally:
        conn.close()
    return project


def _book(root: Path, entries: list[tuple[str, str, str]]) -> Path:
    book = root / "_book"
    book.mkdir()
    (book / "manifest.json").write_text(
        json.dumps(
            {
                "chapters": [
                    {"title": title, "version": version, "project": project}
                    for title, version, project in entries
                ]
            }
        ),
        encoding="utf-8",
    )
    return book


def test_a_child_on_a_womans_voice_is_the_rule_not_a_fault(tmp_path: Path) -> None:
    """EVERAN: nam, `child`, đọc bằng Ngọc Linh kéo cao - đúng cách dự án đọc trẻ con."""
    project = _project(
        tmp_path,
        "lo04_x",
        [("096", "EVERAN", "male", "child", "preset_ngoc_linh_f107_p+02", 13)],
    )

    rows = read_rows(project)

    assert len(rows) == 1 and rows[0]["lines"] == 13
    assert preset_gender("preset_ngoc_linh_f107_p+02") == "female"
    assert wrong_gender(rows) == []


def test_an_adult_man_on_a_womans_voice_is_reported(tmp_path: Path) -> None:
    """IVAN ở chương 062: `age=unknown`, 17 câu bằng giọng trẻ con nữ - con số thật của báo cáo."""
    project = _project(
        tmp_path,
        "lo03r_062_x",
        [
            ("062", "IVAN", "male", "unknown", "preset_ngoc_linh_f107_p+02", 17),
            ("062", "WILL", "male", "unknown", "preset_thai_son_f100_p+00", 5),
            ("062", "IRINA", "female", "adult", "preset_truc_ly_f100_p+00", 4),
        ],
    )

    bad = wrong_gender(read_rows(project))

    assert [(r["name"], r["lines"]) for r in bad] == [("IVAN", 17)]


def test_an_unknown_gender_is_not_accused(tmp_path: Path) -> None:
    """Không biết phái thì không kết tội: `unknown` được miễn, như `child`."""
    project = _project(
        tmp_path, "lo02_x", [("031", "NGƯỜI LẠ", "unknown", "unknown", "preset_ngoc_linh_f108_p+00", 9)]
    )

    assert wrong_gender(read_rows(project)) == []


def test_the_preset_behind_a_voice_key_is_read_longest_prefix_first() -> None:
    assert preset_gender("preset_thanh_binh_f100_p-04") == "male"
    assert preset_gender("preset_doan_trang_f115_p+00") == "female"
    assert preset_gender("preset_thai_son_f087_p+00") == "male"
    assert preset_gender("narrator") is None
    assert preset_gender("preset_khong_co_giong_nay_f100_p+00") is None


def test_age_drift_says_whether_the_voice_moved_with_it(tmp_path: Path) -> None:
    """Đổi tuổi là đổi họ giọng; công cụ phải nói rõ trường hợp nào thật sự đổi giọng.

    Tuổi nằm ở `characters`, MỘT dòng cho mỗi project - nên drift chỉ xảy ra **giữa các lô**,
    không xảy ra trong một project. Đúng ca thật: IVAN là `child` ở lô 3 (chương 072) và
    `unknown` ở bản đúc lại 060 của cùng lô, và hai bản ấy cho hai họ giọng khác nhau.
    """
    batch = _project(
        tmp_path,
        "lo03_x",
        [
            ("072", "IVAN", "male", "child", "preset_ngoc_linh_f107_p+02", 2),
            ("080", "MICHAEL", "male", "teen", "preset_thanh_binh_f100_p-04", 6),
            ("082", "LONE", "male", "adult", "preset_thanh_binh_f093_p-04", 2),
        ],
    )
    recast = _project(
        tmp_path,
        "lo03r_060_x",
        [
            ("060", "IVAN", "male", "unknown", "preset_thai_son_f100_p+00", 3),
            ("081", "MICHAEL", "male", "unknown", "preset_thanh_binh_f100_p-04", 4),
        ],
    )

    drift = age_drift(read_rows(batch) + read_rows(recast))

    assert set(drift) == {"IVAN", "MICHAEL"}, "LONE chỉ có một tuổi - không phải drift"
    assert len(drift["IVAN"]["voices"]) == 2, "IVAN đổi cả giọng"
    assert len(drift["MICHAEL"]["voices"]) == 1, "MICHAEL đổi tuổi mà giữ giọng"


def test_the_two_spellings_are_folded_before_comparing(tmp_path: Path) -> None:
    """`NGUOI TRA LOI` và `NGƯỜI TRẢ LỜI` là một người - không gộp thì không thấy drift nào."""
    project = _project(
        tmp_path,
        "lo02_x",
        [
            ("031", "NGUOI TRA LOI", "female", "young", "preset_ngoc_linh_f108_p+00", 3),
            ("032", "NGƯỜI TRẢ LỜI", "female", "unknown", "preset_doan_trang_f100_p+00", 4),
        ],
    )

    rows = read_rows(project)
    assert age_drift(rows) == {}, "chưa gộp thì thấy hai người, mỗi người một tuổi"
    assert set(age_drift(fold_names(rows))) == {"NGƯỜI TRẢ LỜI"}


def test_the_book_is_read_through_the_manifest_and_recast_names_the_batch(tmp_path: Path) -> None:
    versions = tmp_path / "_versions"
    _project(
        versions / "v0.2.0-lo03r",
        "lo03r_062_x",
        [("062", "IVAN", "male", "unknown", "preset_ngoc_linh_f107_p+02", 17)],
    )
    _project(
        versions / "v0.2.0-lo03",
        "lo03_x",
        [
            ("062", "IVAN", "male", "unknown", "preset_thai_son_f100_p+00", 17),
            ("072", "WILL", "male", "unknown", "preset_thai_son_f100_p+00", 5),
        ],
    )
    book = _book(tmp_path, [("062", "v0.2.0-lo03r", "lo03r_062_x"), ("072", "v0.2.0-lo03", "lo03_x")])

    rows = fold_names(shipped_rows(book=book, versions=versions))

    assert {r["chapter"] for r in rows} == {"062", "072"}, "bản cũ của 062 không được đếm"
    bad = wrong_gender(rows)
    assert [r["name"] for r in bad] == ["IVAN"]
    assert chapter_batches(book=book) == {"062": 3, "072": 3}
    assert recast_arguments(bad, chapter_batches(book=book)) == ["3:062"]


def test_a_missing_book_reads_as_nothing(tmp_path: Path) -> None:
    assert shipped_rows(book=tmp_path / "nowhere", versions=tmp_path / "nothing") == []
