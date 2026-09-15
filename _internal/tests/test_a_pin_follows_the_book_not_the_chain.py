"""Một pin đã trôi khỏi cuốn sách phải được sửa lại — nhưng chỉ ở chỗ không thể gây va chạm.

Ca thật, đo 21:00 ngày 2026-09-15 trên sách 139 chương của cuốn 2. Bước 4 của ranh giới 3 đúc
lại chương 110, và `patch_two_pins_do_not_share_a_chapter` bỏ pin của CHRISTOPHER ở đó (2 câu,
gặp VERDI 5 câu trên cùng `thanh_binh_f090`) — đúng doanh nghĩa dự án. Nhưng `port_casting` mang
giọng mới xuống project kế tiếp **như một pin**, và `pin_the_book_cast` không bao giờ xét lại
một pin đã có, nên một quyết định cục bộ một chương thành danh tính của cả chuỗi:

    VERDI        10 chương, TẤT CẢ thanh_binh_f090
    CHRISTOPHER   9 chương: f090 ở 6 chương / thai_son_f104 ở 110, 112, 114

Hai người chỉ gặp nhau ở 110 và 112. Chương **114 đổi giọng mà không mua được gì**.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from ebook_reader.character_registry import canonical_key
from scripts.pin_the_book_cast import chapters_by_voice, pins_that_drifted, project_chapters

F090 = "preset_thanh_binh_f090_p-04"
F104 = "preset_thai_son_f104_p+00"
OTHER = "preset_truc_ly_f100_p+00"


def _rows() -> list[dict]:
    """Đúng hình của sách: VERDI cả 10 chương một giọng, CHRISTOPHER 6 + 3."""
    rows: list[dict] = []
    for chapter in ("064", "065", "066", "110", "112", "124", "125", "126", "127", "130"):
        rows.append({"name": "VERDI", "voice": F090, "chapter": chapter})
    for chapter in ("094", "095", "096", "097", "109", "113"):
        rows.append({"name": "CHRISTOPHER", "voice": F090, "chapter": chapter})
    for chapter in ("110", "112", "114"):
        rows.append({"name": "CHRISTOPHER", "voice": F104, "chapter": chapter})
    return rows


def test_the_chapter_that_changed_voice_for_nothing_is_corrected() -> None:
    pins = {canonical_key("VERDI"): F090, canonical_key("CHRISTOPHER"): F104}

    drifted, notes = pins_that_drifted(pins, _rows(), {"114"}, canonical=canonical_key)

    assert set(drifted) == {"CHRISTOPHER"}, drifted
    current, wanted, here, there = drifted["CHRISTOPHER"]
    assert (current, wanted, here, there) == (F104, F090, 3, 6)
    assert any("114" not in line and "CHRISTOPHER" in line for line in notes), notes


def test_the_chapter_where_they_really_meet_keeps_its_pin() -> None:
    """Ở 110 và 112 hai người thật sự cùng chương: pin `f104` ở lại đúng chỗ nó sinh ra."""
    pins = {canonical_key("VERDI"): F090, canonical_key("CHRISTOPHER"): F104}

    for scope in ({"110"}, {"112"}, {"110", "112"}):
        drifted, notes = pins_that_drifted(pins, _rows(), scope, canonical=canonical_key)
        assert drifted == {}, (scope, drifted)
        assert any("cùng chương" in line for line in notes), notes


def test_a_whole_batch_scope_that_contains_the_meeting_is_refused() -> None:
    """Lô 40 chương chứa cả 110: không sửa, vì sửa là tạo lại đúng va chạm."""
    pins = {canonical_key("VERDI"): F090, canonical_key("CHRISTOPHER"): F104}
    scope = {f"{number:03d}" for number in range(100, 140)}

    drifted, _notes = pins_that_drifted(pins, _rows(), scope, canonical=canonical_key)

    assert drifted == {}


def test_a_pin_that_agrees_with_the_book_is_left_alone() -> None:
    pins = {canonical_key("VERDI"): F090, canonical_key("CHRISTOPHER"): F090}

    drifted, notes = pins_that_drifted(pins, _rows(), {"114"}, canonical=canonical_key)

    assert drifted == {}
    assert notes == []


def test_a_tie_keeps_the_pin_so_two_runs_answer_the_same() -> None:
    rows = [
        {"name": "ATHY", "voice": F090, "chapter": chapter} for chapter in ("017", "020", "047")
    ] + [
        {"name": "ATHY", "voice": F104, "chapter": chapter} for chapter in ("050", "055", "077")
    ]

    drifted, _notes = pins_that_drifted(
        {canonical_key("ATHY"): F104}, rows, {"017"}, canonical=canonical_key
    )

    assert drifted == {}, "hoà 3–3 thì không có 'đa số' nào để sửa về"


def test_someone_with_one_chapter_is_not_worth_correcting() -> None:
    rows = [{"name": "IGOR", "voice": F090, "chapter": "003"}]

    drifted, _notes = pins_that_drifted(
        {canonical_key("IGOR"): F104}, rows, {"003"}, canonical=canonical_key, min_chapters=2
    )

    assert drifted == {}


def test_a_majority_voice_nobody_holds_is_free_to_take_back() -> None:
    """SHARON: pin `ngoc_linh_f087` trôi từ một project đúc lại, đa số thật là `truc_ly_f100`."""
    rows = [
        {"name": "SHARON", "voice": OTHER, "chapter": chapter}
        for chapter in ("105", "107", "109", "111")
    ] + [
        {"name": "SHARON", "voice": "preset_ngoc_linh_f087_p+00", "chapter": chapter}
        for chapter in ("112", "114")
    ]

    drifted, _notes = pins_that_drifted(
        {canonical_key("SHARON"): "preset_ngoc_linh_f087_p+00"},
        rows,
        {"140"},
        canonical=canonical_key,
    )

    assert drifted["SHARON"][:2] == ("preset_ngoc_linh_f087_p+00", OTHER)


def test_an_unpinned_person_is_not_this_pass_s_business() -> None:
    """Người chưa có pin do `resolve_collisions` lo; phép sửa này chỉ xét pin đã có."""
    drifted, notes = pins_that_drifted({}, _rows(), {"114"}, canonical=canonical_key)

    assert drifted == {} and notes == []


def test_chapters_by_voice_drops_the_anonymous_crowd() -> None:
    rows = _rows() + [
        {"name": "ANONYMOUS_MALE", "voice": F090, "chapter": "110"},
        {"name": "NPC_LOCAL::rabc::người đàn ông", "voice": F104, "chapter": "110"},
    ]

    out = chapters_by_voice(rows)

    assert set(out) == {"VERDI", "CHRISTOPHER"}


def test_project_chapters_reads_the_project(tmp_path: Path) -> None:
    project = tmp_path / "lo03r_114_deadbeef"
    project.mkdir()
    connection = sqlite3.connect(project / "project.sqlite3")
    try:
        connection.execute("CREATE TABLE chapters (id INTEGER PRIMARY KEY, title TEXT)")
        connection.executemany(
            "INSERT INTO chapters (title) VALUES (?)", [("114",), ("115",)]
        )
        connection.commit()
    finally:
        connection.close()

    assert project_chapters(project) == {"114", "115"}
    assert project_chapters(tmp_path / "khong-co") == set()
