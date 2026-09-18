"""Một cuốn đổi người dẫn chuyện giữa chừng: người kể cũ không thành giọng nhân vật."""
from __future__ import annotations

import pytest

from ebook_reader.character_registry import PresetAllocator
from ebook_reader.config import build_settings, validate_settings

# Ba giọng nam phân vai được hôm nay: Phạm Tuyên, Thanh Bình, Thái Sơn. Thanh Bình kể, Phạm Tuyên
# từng kể - nên chỉ còn Thái Sơn cho nhân vật nam.
NARRATOR = "Thanh Bình"
FORMER = "Phạm Tuyên"


def _cast_many(allocator: PresetAllocator, **kwargs) -> set[str]:
    chosen = set()
    for index in range(24):
        preset, _warp, _offset = allocator.choose("male", npc=False, who=f"NGƯỜI {index}", **kwargs)
        chosen.add(str(preset["name"]))
    return chosen


def test_without_a_former_narrator_the_old_voice_is_in_the_pool() -> None:
    # Chứng minh phép thử bên dưới có nghĩa: không khai thì Phạm Tuyên CÓ được trao.
    assert FORMER in _cast_many(PresetAllocator(NARRATOR, 2))


def test_a_former_narrator_is_never_given_to_a_character() -> None:
    chosen = _cast_many(PresetAllocator(NARRATOR, 2, other_narrators=(FORMER,)))
    assert FORMER not in chosen
    assert NARRATOR not in chosen


def test_nor_to_a_child_cast_across_gender() -> None:
    allocator = PresetAllocator(NARRATOR, 2, other_narrators=(FORMER,))
    assert FORMER not in _cast_many(allocator, age="child")


def test_settings_carry_the_other_narrators_only_when_told() -> None:
    assert "other_narrators" not in build_settings("high_quality")["voices"]
    settings = build_settings(
        "high_quality",
        {"voices": {"narrator_voice": NARRATOR, "other_narrators": [FORMER]}},
    )
    assert settings["voices"]["other_narrators"] == [FORMER]


@pytest.mark.parametrize(
    "former",
    [[NARRATOR], ["Không Có Giọng Này"], "Phạm Tuyên", [""]],
)
def test_a_wrong_former_narrator_is_refused(former) -> None:
    settings = build_settings("high_quality", {"voices": {"narrator_voice": NARRATOR}})
    settings["voices"]["other_narrators"] = former
    with pytest.raises(ValueError):
        validate_settings(settings)
