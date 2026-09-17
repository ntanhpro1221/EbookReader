"""Đúc lại một chương chỉ đổi người cần đổi - xem docstring của `scripts/keep_the_chapter_cast.py`.

Ca thật đằng sau từng bài: ranh giới 5 (16-09) đúc lại chương 094 để đưa EVANS về giọng đa số, và
đẩy CHRISTOPHER, LOTT, HERODOTUS, JULIAN, MEKANZI ra khỏi giọng đa số của họ.
"""
from __future__ import annotations

from pathlib import Path

import pytest

import scripts.keep_the_chapter_cast as keeper
from ebook_reader.database import ProjectDB


def _rows(*items: tuple[str, str, str, int]) -> list[dict]:
    """(chương, tên, giọng, số câu)."""
    return [
        {"chapter": chapter, "name": name, "voice": voice, "lines": lines}
        for chapter, name, voice, lines in items
    ]


def _targets(plan: list[tuple[str, str, str, str]]) -> dict[str, str]:
    return {name: target for name, _shipped, target, _why in plan}


def test_the_person_being_fixed_moves_and_everyone_else_keeps_their_voice() -> None:
    majority = {
        "EVANS": ("thai_son_f097", 22, 23),
        "LOTT": ("thanh_binh_f104", 14, 15),
        "CHRISTOPHER": ("thanh_binh_f090", 9, 10),
    }
    rows = _rows(
        ("094", "EVANS", "thai_son_f104", 5),
        ("094", "LOTT", "thanh_binh_f104", 3),
        ("094", "CHRISTOPHER", "thanh_binh_f090", 4),
    )

    targets = _targets(keeper.plan_chapter("094", rows, majority))

    assert targets == {
        "EVANS": "thai_son_f097",
        "LOTT": "thanh_binh_f104",
        "CHRISTOPHER": "thanh_binh_f090",
    }


def test_fixing_one_person_never_pushes_an_anchored_person_off_their_voice() -> None:
    """Chương 136: SIMON muốn `f116`, nhưng một người khác đang nói `f116` ở chính chương ấy.

    Nếu người kia là NEO (giọng ở đây đã là giọng đa số của họ, >= 2 chương) thì SIMON giữ giọng
    cũ - không ai bị làm hỏng để sửa một người. SIMON có NHIỀU chương hơn IM: xếp thuần theo hạng
    thì SIMON đi trước và lấy mất `f116`; phải là thứ tự nhóm mới giữ được IM.
    """
    majority = {"SIMON": ("f116", 8, 10), "IM": ("f116", 3, 3)}
    rows = _rows(("136", "SIMON", "f104", 2), ("136", "IM", "f116", 9))

    targets = _targets(keeper.plan_chapter("136", rows, majority))

    assert targets == {"IM": "f116", "SIMON": "f104"}


def test_a_one_chapter_speaker_yields_and_is_not_pinned() -> None:
    majority = {"SIMON": ("f116", 3, 4), "IM": ("f116", 1, 1), "BURT": ("f093", 1, 1)}
    rows = _rows(("136", "SIMON", "f104", 2), ("136", "IM", "f116", 9), ("136", "BURT", "f093", 1))

    targets = _targets(keeper.plan_chapter("136", rows, majority))

    # Giọng của BURT còn trống mà vẫn KHÔNG ghim - một pin là một chỗ giữ trên cả cuốn.
    assert targets == {"SIMON": "f116", "IM": "", "BURT": ""}


def test_a_minority_speaker_never_gets_a_third_voice() -> None:
    majority = {"A": ("x", 5, 5), "B": ("y", 5, 5), "C": ("x", 3, 4)}
    rows = _rows(("001", "A", "x", 5), ("001", "B", "y", 5), ("001", "C", "y", 1))

    plan = keeper.plan_chapter("001", rows, majority)

    assert _targets(plan)["C"] == "", "C không có giọng nào của mình còn trống - để bộ cấp giọng chọn"


def test_npcs_anonymous_and_the_narrator_are_left_alone() -> None:
    rows = _rows(
        ("001", "NPC_LOCAL::C1::R2::LÍNH GÁC", "x", 3),
        ("001", "ANONYMOUS_UNKNOWN", "y", 1),
        ("001", "NARRATOR", "z", 40),
    )

    assert keeper.plan_chapter("001", rows, {}) == []


@pytest.fixture
def recast(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    target = tmp_path / "lo02r_094b_test"
    target.mkdir()
    database = ProjectDB(target / "project.sqlite3")
    # Pin cũ mang từ project gieo: IM giữ `f116`, và ERIC (không nói ở 094) giữ `f090`.
    database.set_locked_character_voice("IM", "preset_f116")
    database.set_locked_character_voice("ERIC", "preset_f090")
    rows = _rows(
        ("094", "SIMON", "preset_f104", 3),
        ("094", "IM", "preset_f116", 2),
        ("094", "CHRISTOPHER", "preset_f090", 4),
        ("101", "SIMON", "preset_f116", 1),
        ("102", "SIMON", "preset_f116", 1),
        ("103", "CHRISTOPHER", "preset_f090", 1),
    )
    monkeypatch.setattr(keeper, "shipped_rows", lambda: rows)
    monkeypatch.setattr(keeper, "fold_names", lambda found: found)
    monkeypatch.setattr(keeper, "project_chapters", lambda _target: {"094"})
    monkeypatch.setattr(
        keeper,
        "voice_profile",
        lambda key, versions=None: {
            "engine": "vieneu",
            "preset_name": key,
            "description": "test",
            "seed": 3,
            "pitch_semitones": 0,
            "formant_ratio": 1.0,
        },
    )
    return target


def test_apply_pins_the_chapter_and_drops_a_carried_pin_that_would_clash(recast: Path) -> None:
    written = keeper.keep(recast, apply=True, versions=recast)

    pins = {key.upper(): voice for key, voice in ProjectDB(recast / "project.sqlite3").locked_character_voices().items()}
    assert written == 2
    assert pins.get("SIMON") == "preset_f116", pins
    assert pins.get("CHRISTOPHER") == "preset_f090", "ERIC giữ f090 nhưng không nói ở 094 - chia được"
    assert "IM" not in pins, "pin cũ của IM trùng giọng vừa gán cho SIMON trong cùng chương - phải bỏ"
    assert pins.get("ERIC") == "preset_f090", "người không nói trong chương thì không đụng tới"


def test_a_dry_run_writes_nothing(recast: Path) -> None:
    before = ProjectDB(recast / "project.sqlite3").locked_character_voices()

    keeper.keep(recast, apply=False, versions=recast)

    assert ProjectDB(recast / "project.sqlite3").locked_character_voices() == before


def test_a_chapter_not_on_the_book_is_left_to_the_allocator(recast: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(keeper, "project_chapters", lambda _target: {"250"})

    assert keeper.keep(recast, apply=True, versions=recast) == 0


def test_launch_repair_keeps_the_chapter_cast_before_it_runs_a_recast() -> None:
    """Nối đúng chỗ: sau hai bước gieo/ghim của cả cuốn (để nó có lời cuối), trước `run`; chỉ ở chế
    độ đúc lại; và thất bại thì BỎ CHƯƠNG - chạy đúc lại không có nó là đúng cái đã làm 094 tệ hơn."""
    text = (Path(__file__).resolve().parents[1] / "scripts" / "launch_repair.sh").read_text(encoding="utf-8")

    call = text.index("scripts/keep_the_chapter_cast.py")
    assert text.index('scripts/pin_the_book_cast.py "$PROJECT" --apply') < call
    assert call < text.index('-m ebook_reader.cli run "$PROJECT"')
    guard = text.rfind('if [ -n "$EXPLICIT" ] && [ "$AS_REPAIR" != 1 ]; then', 0, call)
    block_end = text.index("\n  fi\n", guard)
    assert guard != -1 and block_end > call, "chỉ chạy ở chế độ đúc lại"
    assert "continue" in text[call:block_end], "thất bại phải bỏ chương"
