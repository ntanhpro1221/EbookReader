"""Bản đúc lại chỉ lên sách khi giúp nhiều hơn hại - xem docstring của `scripts/ship_only_recasts_that_help.py`.

Số đo thật mà cổng phải tái hiện (17-09, bốn project ranh giới 5 đã dời ra bằng tay):
010 tốt 0 / xấu 2, 027 0 / 0, 094 1 / 5, 136 0 / 1 - cả bốn KHÔNG lên sách; 105 tốt 1 / xấu 0 thì lên.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

import scripts.ship_only_recasts_that_help as gate


def _rows(*items: tuple[str, str, str, int], project: str = "book") -> list[dict]:
    return [
        {"chapter": chapter, "name": name, "voice": voice, "lines": lines, "project": project}
        for chapter, name, voice, lines in items
    ]


BOOK = _rows(
    ("094", "EVANS", "f104", 5),
    ("094", "LOTT", "f104b", 3),
    ("101", "EVANS", "f097", 2),
    ("102", "EVANS", "f097", 2),
    ("101", "LOTT", "f104b", 2),
    ("103", "LOTT", "f104b", 1),
    project="lo02_batch",
)


def test_moving_someone_to_their_majority_is_better_and_off_it_is_worse() -> None:
    recast = _rows(("094", "EVANS", "f097", 5), ("094", "LOTT", "f100", 3), project="lo02r_094")

    verdicts = {v[0]: v[4] for v in gate.judge("094", BOOK, recast)}

    assert verdicts == {"EVANS": gate.BETTER, "LOTT": gate.WORSE}


def test_the_majority_leaves_the_judged_chapter_out() -> None:
    """Không tự chứng minh: nếu đếm cả chương 094 thì giọng MỚI tự cộng một phiếu cho mình."""
    book = _rows(("094", "WOLF", "a", 1), ("101", "WOLF", "b", 1), project="lo01_batch")
    recast = _rows(("094", "WOLF", "b", 1), project="lo01r_094")

    assert gate.judge("094", book, recast)[0][4] == gate.BETTER


def test_a_person_whose_voice_did_not_change_is_not_judged() -> None:
    recast = _rows(("094", "EVANS", "f104", 5), ("094", "LOTT", "f104b", 3), project="lo02r_094")

    assert gate.judge("094", BOOK, recast) == []


def _project(tmp_path: Path, name: str, chapter: str = "094") -> Path:
    target = tmp_path / "_versions" / "v0.3.0-lo02r" / name
    target.mkdir(parents=True)
    connection = sqlite3.connect(target / "project.sqlite3")
    connection.execute("CREATE TABLE chapters (title TEXT, status TEXT)")
    connection.execute("INSERT INTO chapters VALUES (?, 'completed')", (chapter,))
    connection.commit()
    connection.close()
    return target


@pytest.mark.parametrize(
    ("recast", "ships"),
    [
        (_rows(("094", "EVANS", "f097", 5), ("094", "LOTT", "f104b", 3), project="lo02r_094"), True),
        (_rows(("094", "EVANS", "f097", 5), ("094", "LOTT", "f100", 3), project="lo02r_094"), False),
        (_rows(("094", "EVANS", "f104", 5), ("094", "LOTT", "f104b", 3), project="lo02r_094"), False),
    ],
    ids=["tot 1 xau 0 - len sach", "tot 1 xau 1 - khong", "khong sua duoc ai - khong"],
)
def test_apply_ships_only_when_better_outnumbers_worse(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, recast: list[dict], ships: bool
) -> None:
    target = _project(tmp_path, "lo02r_094_test")
    monkeypatch.setattr(gate, "rows_as_they_will_ship", lambda exclude=None: BOOK)
    monkeypatch.setattr(gate, "read_rows", lambda _project: recast)

    code = gate.decide(target, apply=True, root=tmp_path)

    moved = gate.quarantine_path(target, tmp_path)
    if ships:
        assert code == 0 and target.is_dir() and not moved.exists()
    else:
        assert code == gate.HARMFUL and not target.exists() and (moved / "project.sqlite3").is_file()
        assert "_versions" not in moved.parts, "phải ra NGOÀI _versions, nếu không bước 7 vẫn thấy nó"


def test_a_dry_run_moves_nothing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    target = _project(tmp_path, "lo02r_094_test")
    monkeypatch.setattr(gate, "rows_as_they_will_ship", lambda exclude=None: BOOK)
    monkeypatch.setattr(gate, "read_rows", lambda _p: _rows(("094", "LOTT", "f100", 3), project="x"))

    assert gate.decide(target, apply=False, root=tmp_path) == gate.HARMFUL
    assert target.is_dir()


def test_a_project_already_on_the_book_or_a_chapter_never_shipped_is_left_alone(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    shipped_here = _project(tmp_path, "lo02r_094_test")
    monkeypatch.setattr(gate, "rows_as_they_will_ship", lambda exclude=None: _rows(("094", "LOTT", "f104b", 3), project="lo02r_094_test"))
    monkeypatch.setattr(gate, "read_rows", lambda _p: _rows(("094", "LOTT", "f100", 3), project="lo02r_094_test"))
    assert gate.decide(shipped_here, apply=True, root=tmp_path) == 0

    never = _project(tmp_path, "lo06r_250_test", chapter="250")
    assert gate.decide(never, apply=True, root=tmp_path) == 0
    assert shipped_here.is_dir() and never.is_dir()


def test_launch_repair_gates_a_recast_before_it_seeds_the_next_chapter() -> None:
    text = (Path(__file__).resolve().parents[1] / "scripts" / "launch_repair.sh").read_text(encoding="utf-8")

    call = text.index("scripts/ship_only_recasts_that_help.py")
    assert text.index('wait_for_run "$PROJECT"') < call < text.index('PREV="$PROJECT"', call)
    harmful = text.index('if [ "$GATE" = 10 ]; then', call)
    assert "continue" in text[harmful : text.index("elif", harmful)], "mã 10 phải bỏ qua PREV=\"$PROJECT\""
    assert "|| GATE=$?" in text, "mã khác 0 trong $(...) phải được bắt, nếu không một `set -e` sau này sẽ giết cả vòng"


# Chương 228 ranh giới 6: LUCIEN và NPC một chương cùng `thanh_binh_f100`. Lượt đúc lại đặt lại mã NPC
# (tên khác hẳn giữa hai bản), nên chỉ phép đếm cặp thấy được việc sửa.
BOOK_228 = _rows(
    ("228", "LUCIEN", "thanh_binh_f100", 5),
    ("228", "NPC_LOCAL::C00010::R2401::ÔNG GIÀ", "thanh_binh_f100", 1),
    ("229", "LUCIEN", "thanh_binh_f100", 9),
    ("230", "LUCIEN", "thanh_binh_f100", 7),
    project="lo06_batch",
)


def test_pairs_count_distinct_people_on_one_voice_in_the_chapter() -> None:
    assert gate.same_chapter_pairs(BOOK_228, "228") == 1
    assert gate.same_chapter_pairs(BOOK_228, "229") == 0
    three = _rows(("1", "A", "v", 1), ("1", "B", "v", 1), ("1", "C", "v", 1), ("1", "D", "w", 1))
    assert gate.same_chapter_pairs(three, "1") == 3


def test_one_person_spelled_two_ways_is_not_a_pair() -> None:
    rows = _rows(("062", "THỦ LÃNH", "f100", 5), ("062", "THU LÃNH", "f100", 2))
    assert gate.same_chapter_pairs(rows, "062") == 0


@pytest.mark.parametrize(
    ("recast", "ships"),
    [
        (
            _rows(
                ("228", "LUCIEN", "thanh_binh_f100", 6),
                ("228", "NPC_LOCAL::C00001::R1F90::ÔNG GIÀ", "adam_bua_f100", 1),
                project="lo06r_228",
            ),
            True,
        ),
        (
            _rows(
                ("228", "LUCIEN", "thanh_binh_f100", 6),
                ("228", "NPC_LOCAL::C00001::R1F90::ÔNG GIÀ", "thanh_binh_f100", 1),
                project="lo06r_228",
            ),
            False,
        ),
    ],
    ids=["tach duoc NPC khoi giong LUCIEN - len sach", "van trung - khong"],
)
def test_a_collision_fixed_inside_the_chapter_ships(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, recast: list[dict], ships: bool
) -> None:
    target = _project(tmp_path, "lo06r_228_test", chapter="228")
    monkeypatch.setattr(gate, "rows_as_they_will_ship", lambda exclude=None: BOOK_228)
    # `read_rows` lọc NPC ra - đúng như bộ đọc thật - nên thước cũ không thấy gì để phán.
    monkeypatch.setattr(gate, "read_rows", lambda _project: [r for r in recast if not r["name"].startswith("NPC_")])
    monkeypatch.setattr(gate, "book_project", lambda name: Path(name))
    monkeypatch.setattr(
        gate, "everyone_in_chapter", lambda project, chapter: recast if project == target else BOOK_228
    )

    assert (gate.decide(target, apply=True, root=tmp_path) == 0) is ships


def test_a_recast_that_creates_a_collision_is_worse() -> None:
    book = _rows(("300", "A", "v1", 3), ("300", "B", "v2", 3), project="lo07_batch")
    recast = _rows(("300", "A", "v1", 3), ("300", "B", "v1", 3), project="lo07r_300")
    assert gate.same_chapter_pairs(book, "300") == 0
    assert gate.same_chapter_pairs(recast, "300") == 1


def test_the_pair_count_reads_npcs_the_shared_reader_leaves_out(tmp_path: Path) -> None:
    """Lần sửa đầu đếm bằng `read_rows` và ra `0 -> 0` cho chương 228: bộ đọc ấy bỏ mọi tên `NPC_`."""
    target = tmp_path / "lo06_test"
    target.mkdir()
    connection = sqlite3.connect(target / "project.sqlite3")
    connection.executescript(
        """
        CREATE TABLE chapters (id INTEGER PRIMARY KEY, title TEXT, status TEXT);
        CREATE TABLE characters (id INTEGER PRIMARY KEY, canonical_name TEXT);
        CREATE TABLE voice_profiles (id INTEGER PRIMARY KEY, voice_key TEXT);
        CREATE TABLE segments (id INTEGER PRIMARY KEY, chapter_id INT, canonical_character_id INT,
                               voice_profile_id INT, kind TEXT);
        INSERT INTO chapters VALUES (1, '228', 'completed');
        INSERT INTO characters VALUES (1, 'LUCIEN'), (2, 'NPC_LOCAL::C00010::R2401::ÔNG GIÀ'), (3, 'NARRATOR');
        INSERT INTO voice_profiles VALUES (1, 'preset_thanh_binh_f100_p-04'), (2, 'narrator');
        INSERT INTO segments VALUES (1, 1, 1, 1, 'dialogue'), (2, 1, 2, 1, 'dialogue'), (3, 1, 3, 2, 'narration');
        """
    )
    connection.commit()
    connection.close()

    everyone = gate.everyone_in_chapter(target, "228")

    assert {row["name"] for row in everyone} == {"LUCIEN", "NPC_LOCAL::C00010::R2401::ÔNG GIÀ"}
    assert gate.same_chapter_pairs(everyone, "228") == 1
    assert gate.everyone_in_chapter(None, "228") == []
    assert gate.everyone_in_chapter(tmp_path / "missing", "228") == []
