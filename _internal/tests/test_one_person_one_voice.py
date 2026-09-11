"""Câu ngược của `voice_pool_pressure`: một người có mang HAI giọng không.

Hai người dùng chung một giọng thì người nghe lẫn hai nhân vật. Một người đổi giọng giữa chương
thì người nghe **mất** nhân vật ấy — đắt hơn, và chưa ai kiểm. Đo lần đầu 2026-09-11 trên cuốn
sách 90 chương: 21 chương, 202 câu thoại, gần hết thuộc hai cái tên bị tách vì rơi dấu.

Bài quan trọng nhất ở đây là bài gộp tên: không gộp thì công cụ thấy hai cái tên, mỗi tên một
giọng, và báo "không có gì" — đúng cái mù đã để 202 câu đi vào sách.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from scripts.one_person_one_voice import read_voices, shipped_voices, split_voices


def _project(root: Path, name: str, rows: list[tuple[str, str, str, int]]) -> Path:
    """rows = [(chương, tên nhân vật, voice_key, số câu)]."""
    project = root / name
    project.mkdir(parents=True)
    conn = sqlite3.connect(str(project / "project.sqlite3"))
    try:
        conn.executescript(
            """
            CREATE TABLE chapters (id INTEGER PRIMARY KEY, title TEXT);
            CREATE TABLE characters (id INTEGER PRIMARY KEY, canonical_name TEXT);
            CREATE TABLE voice_profiles (id INTEGER PRIMARY KEY, voice_key TEXT);
            CREATE TABLE segments (
                id INTEGER PRIMARY KEY, chapter_id INTEGER, canonical_character_id INTEGER,
                voice_profile_id INTEGER, kind TEXT
            );
            """
        )
        ids: dict[tuple[str, str], int] = {}

        def key(table: str, column: str, value: str) -> int:
            if (table, value) not in ids:
                cur = conn.execute(f"INSERT INTO {table} ({column}) VALUES (?)", (value,))
                ids[(table, value)] = int(cur.lastrowid or 0)
            return ids[(table, value)]

        for chapter, name_, voice_key, lines in rows:
            for _ in range(lines):
                conn.execute(
                    "INSERT INTO segments (chapter_id, canonical_character_id,"
                    " voice_profile_id, kind) VALUES (?,?,?,'dialogue')",
                    (
                        key("chapters", "title", chapter),
                        key("characters", "canonical_name", name_),
                        key("voice_profiles", "voice_key", voice_key),
                    ),
                )
        conn.commit()
    finally:
        conn.close()
    return project


def test_the_two_spellings_are_folded_before_comparing() -> None:
    """Đúng ca chương 060: `THU LÃNH` 7 câu một giọng, `THỦ LÃNH` 5 câu giọng khác.

    Không gộp thì đây là hai người, mỗi người một giọng, và mọi cổng đều xanh.
    """
    rows = [
        ("060", "THU LÃNH", "preset_thanh_binh_f090_p-04", 7),
        ("060", "THỦ LÃNH", "preset_thanh_binh_f100_p-07", 5),
    ]

    inside, across = split_voices(rows)

    assert list(inside) == ["060"]
    assert inside["060"]["THỦ LÃNH"] == {
        "preset_thanh_binh_f090_p-04": 7,
        "preset_thanh_binh_f100_p-07": 5,
    }
    assert list(across) == ["THỦ LÃNH"]


def test_two_people_sharing_one_voice_is_not_this_tool_s_business() -> None:
    """Đó là câu của `voice_pool_pressure`; ở đây nó phải im."""
    rows = [
        ("066", "KANG", "preset_thanh_binh_f093_p-04", 3),
        ("066", "SAMAEL", "preset_thanh_binh_f093_p-04", 2),
    ]

    inside, across = split_voices(rows)

    assert inside == {} and across == {}


def test_a_voice_change_between_chapters_is_reported_apart(tmp_path: Path) -> None:
    """KANG: giọng f093 ở sáu chương, f100 ở chương 071 vì lô đúc lại bỏ pin của nó.

    Không nằm trong `inside` (không chương nào có hai giọng cùng lúc) nhưng vẫn phải hiện ra:
    người theo dõi nhân vật vẫn nghe nó đổi giọng.
    """
    rows = [
        ("065", "KANG", "preset_thanh_binh_f093_p-04", 3),
        ("066", "KANG", "preset_thanh_binh_f093_p-04", 3),
        ("071", "KANG", "preset_thanh_binh_f100_p-04", 1),
    ]

    inside, across = split_voices(rows)

    assert inside == {}
    assert across["KANG"]["preset_thanh_binh_f100_p-04"] == {"071"}
    assert across["KANG"]["preset_thanh_binh_f093_p-04"] == {"065", "066"}


def test_narrator_and_npcs_are_left_out(tmp_path: Path) -> None:
    project = _project(
        tmp_path,
        "lo03",
        [
            ("060", "NARRATOR", "narrator", 5),
            ("060", "NPC_LOCAL::C1::R2::CẬU BÉ", "preset_a_f100_p+00", 2),
            ("060", "ANONYMOUS_MALE", "preset_b_f100_p+00", 2),
            ("060", "KANG", "preset_c_f100_p+00", 2),
        ],
    )

    assert [row[1] for row in read_voices(project)] == ["KANG"]


def test_the_book_is_read_through_the_manifest(tmp_path: Path) -> None:
    """Một chương có nhiều bản; chỉ bản **trong sách** được tính. Hỏi bằng cả bốn bản là hỏi sai."""
    versions = tmp_path / "_versions"
    old = _project(versions / "v0.2.0-lo03", "lo03", [("062", "IGOR", "preset_old_f100_p+00", 3)])
    _project(versions / "v0.2.0-lo03r", "lo03r_062", [("062", "IGOR", "preset_new_f100_p+00", 3)])
    assert old.exists()
    book = tmp_path / "_book"
    book.mkdir()
    (book / "manifest.json").write_text(
        json.dumps({"chapters": [{"title": "062", "version": "v0.2.0-lo03r"}]}),
        encoding="utf-8",
    )

    rows = shipped_voices(book=book, versions=versions)

    assert rows == [("062", "IGOR", "preset_new_f100_p+00", 3)]


def test_a_superseded_sibling_in_the_same_folder_is_not_counted(tmp_path: Path) -> None:
    """`lo01r_007` (bị dừng dở, còn 12 câu giọng lệch) và `lo01r_007b` (lên sách) nằm cùng thư
    mục. Đọc cả hai là cộng bản bỏ đi vào chương sạch - đúng lỗi đo 17:41 ngày 2026-09-11."""
    versions = tmp_path / "_versions"
    _project(versions / "v0.2.0-lo01r", "lo01r_007_x", [("007", "NGƯỜI TRẢ LỜI", "preset_f115", 12)])
    _project(versions / "v0.2.0-lo01r", "lo01r_007b_x", [("007", "NGƯỜI TRẢ LỜI", "preset_f100", 15)])
    book = tmp_path / "_book"
    book.mkdir()
    (book / "manifest.json").write_text(
        json.dumps({"chapters": [{"title": "007", "version": "v0.2.0-lo01r", "project": "lo01r_007b_x"}]}),
        encoding="utf-8",
    )

    rows = shipped_voices(book=book, versions=versions)

    assert rows == [("007", "NGƯỜI TRẢ LỜI", "preset_f100", 15)]
    inside, _across = split_voices(rows)
    assert inside == {}, "bản bị bỏ không được làm chương sạch đọc thành hai giọng"


def test_a_missing_book_reads_as_nothing(tmp_path: Path) -> None:
    assert shipped_voices(book=tmp_path / "khong-co", versions=tmp_path) == []
    assert read_voices(tmp_path / "khong-co") == []
