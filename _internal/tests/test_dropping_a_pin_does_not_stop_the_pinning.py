"""Bỏ pin của một nhãn không có trong nguồn KHÔNG được chặn vòng ghim giọng đa số phía sau.

Ca thật, ranh giới 5 tối 16-09: `pin_the_book_cast.py --apply` gọi
`set_locked_character_voice(name, "")` để bỏ pin `GIEDON`; hàm ấy từ chối giọng rỗng, script nổ
**trước** vòng ghim, và `launch_repair.sh` đi tiếp. Năm chương đúc lại lên dàn giọng thiếu pin đa
số - đo bằng `measure_did_the_recast_help.py`: tốt hơn 2, xấu hơn 7.

Các bài cũ của script này chỉ thử hàm thuần (`majority_voices`, `resolve_collisions`,
`names_absent_from_the_source`) và lượt không `--apply`; đường GHI chưa từng chạy trên một
`ProjectDB` thật. Bài này chạy đúng đường ấy.
"""
from __future__ import annotations

from pathlib import Path

import pytest

import scripts.pin_the_book_cast as cast
from ebook_reader.database import ProjectDB

PROFILE = {
    "engine": "vieneu",
    "preset_name": "thai_son",
    "description": "test",
    "seed": 7,
    "pitch_semitones": 0,
    "formant_ratio": 1.0,
}


@pytest.fixture
def project(tmp_path: Path) -> Path:
    target = tmp_path / "lo03r_105_test"
    target.mkdir()
    database = ProjectDB(target / "project.sqlite3")
    database.set_locked_character_voice("GIEDON", "preset_thanh_binh_f108_p-07")
    database.set_locked_character_voice("NARRATOR", "preset_pham_tuyen_f100_p+00")
    return target


def _book(monkeypatch: pytest.MonkeyPatch) -> None:
    rows = [
        {"chapter": "101", "name": "LOTT", "voice": "preset_thanh_binh_f104_p-04", "lines": 3},
        {"chapter": "102", "name": "LOTT", "voice": "preset_thanh_binh_f104_p-04", "lines": 2},
        {"chapter": "103", "name": "LOTT", "voice": "preset_thanh_binh_f104_p-04", "lines": 4},
    ]
    monkeypatch.setattr(cast, "shipped_rows", lambda **_kw: rows)
    monkeypatch.setattr(cast, "fold_names", lambda found: found)
    monkeypatch.setattr(cast, "voice_profile", lambda key, versions=None: dict(PROFILE, voice_key=key))
    monkeypatch.setattr(
        cast, "names_absent_from_the_source", lambda names, source=None: {"GIEDON"} & set(names)
    )


def test_unpin_character_clears_the_pin_on_a_real_database(project: Path) -> None:
    database = ProjectDB(project / "project.sqlite3")

    assert cast.unpin_character(database, "GIEDON") == 1

    pins = database.locked_character_voices()
    assert all("GIEDON" not in key.upper() for key in pins), pins
    assert any("NARRATOR" in key.upper() for key in pins), "chỉ bỏ đúng người được gọi tên"


def test_apply_drops_the_absent_label_and_still_pins_the_majority(
    project: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _book(monkeypatch)

    pinned = cast.pin(project, apply=True, book=tmp_path / "book", versions=tmp_path / "versions")

    database = ProjectDB(project / "project.sqlite3")
    pins = {key.upper(): voice for key, voice in database.locked_character_voices().items()}
    assert pinned == 1
    assert not any("GIEDON" in key for key in pins), "nhãn không có trong nguồn vẫn giữ pin"
    assert any("LOTT" in key and voice == "preset_thanh_binh_f104_p-04" for key, voice in pins.items()), (
        f"vòng ghim giọng đa số không chạy tới: {pins}"
    )
