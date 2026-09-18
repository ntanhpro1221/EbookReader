"""Vá character_registry.py + config.py: một cuốn sách đổi người dẫn chuyện giữa chừng.

Chạy: python patch_a_book_can_change_its_narrator.py <root>

**XẾP Ở RANH GIỚI 6**, cùng lượt với nâng VieNeu 3.8.1 và bản vá tốc độ giọng.

## Vì sao (18-09)

Chủ sách chọn Đức Trí làm người dẫn chuyện của cuốn 2 **từ chương 304** (lô 7). 303 chương đầu đã
lên sách với Phạm Tuyên đọc lời kể. `cli create --narrator` (không khoá, sửa thẳng trong cli.py) đổi
người kể cho project mới; bản vá này lo hệ quả thứ hai: khi Phạm Tuyên thôi dẫn chuyện, bộ phân vai
coi Phạm Tuyên là giọng rảnh và có thể trao cho một nhân vật mới. Người nghe đã nghe giọng ấy kể
suốt 303 chương - một nhân vật đột nhiên nói bằng giọng người kể cũ sẽ nghe như người kể chen vào
lời thoại, đúng cái lỗi mà luật "nhân vật không bao giờ dùng giọng người kể" đang chặn.

Nên settings có thêm `voices.other_narrators`: những giọng đã từng kể cuốn này. `PresetAllocator`
loại chúng khỏi cả ba chỗ đang loại người kể hiện tại (vòng thường, trẻ em qua giới, vét cạn qua
giới). Không có khoá thì tập loại trừ đúng bằng `{narrator_voice}` như cũ, và `settings_hash` của
mọi project cũ không đổi vì `cli` chỉ ghi khoá khi được truyền.

Nhân vật đã GHIM vào một giọng người kể cũ (không thể xảy ra ở cuốn 2: Phạm Tuyên chưa bao giờ rời
ghế kể) vẫn giữ giọng ấy - `reserve()` không đi qua bộ lọc này, và đổi giọng một người đã nói là
một lỗi to hơn.
"""
import io
import sys
from pathlib import Path

root = Path(sys.argv[1])


def replace_once(path: Path, old: str, new: str) -> None:
    text = io.open(path, encoding="utf-8").read()
    assert text.count(old) == 1, f"{path.name}: khong khop mot lan duy nhat: {old.splitlines()[0]!r}"
    io.open(path, "w", encoding="utf-8").write(text.replace(old, new, 1))


def replace_exactly(path: Path, old: str, new: str, count: int) -> None:
    text = io.open(path, encoding="utf-8").read()
    assert text.count(old) == count, f"{path.name}: can {count} cho, thay {text.count(old)}: {old!r}"
    io.open(path, "w", encoding="utf-8").write(text.replace(old, new))


# ------------------------------------------------------------------ character_registry.py
registry = root / "ebook_reader" / "character_registry.py"
replace_once(registry, '''from typing import Any, Callable
''', '''from typing import Any, Callable, Iterable
''')
replace_once(registry, '''class PresetAllocator:
    def __init__(self, narrator_voice: str, max_pitch_shift: int) -> None:
        self.narrator_voice = narrator_voice
''', '''class PresetAllocator:
    def __init__(
        self,
        narrator_voice: str,
        max_pitch_shift: int,
        other_narrators: Iterable[str] = (),
    ) -> None:
        self.narrator_voice = narrator_voice
        # Every voice that has narrated this book, not only the one narrating this project. A
        # book that changes narrator part-way (book 2: Phạm Tuyên for 000..303, Đức Trí from
        # 304) has taught the listener that the old voice IS the narration; a character who
        # speaks in it later sounds like the narrator cutting into the dialogue. Empty unless
        # `voices.other_narrators` says otherwise, so the set is `{narrator_voice}` as before.
        self.not_for_characters = frozenset(
            {str(narrator_voice), *(str(name) for name in other_narrators)}
        )
''')
replace_exactly(
    registry,
    '''if preset["name"] != self.narrator_voice
''',
    '''if preset["name"] not in self.not_for_characters
''',
    3,
)
replace_once(registry, '''    allocator = PresetAllocator(
        narrator_voice,
        int(voice_cfg.get("max_character_pitch_semitones", 2)),
    )
''', '''    allocator = PresetAllocator(
        narrator_voice,
        int(voice_cfg.get("max_character_pitch_semitones", 2)),
        other_narrators=tuple(voice_cfg.get("other_narrators", ())),
    )
''')

# ------------------------------------------------------------------ config.py
config = root / "ebook_reader" / "config.py"
replace_once(config, '''    if narrator_voice not in {preset["name"] for preset in narrator_presets(narrator_gender)}:
        raise ValueError("Unsupported narrator voice")
''', '''    if narrator_voice not in {preset["name"] for preset in narrator_presets(narrator_gender)}:
        raise ValueError("Unsupported narrator voice")
    # Absent on every project that never changed narrator; see `PresetAllocator` for why it
    # exists. A typo here would quietly keep the old narrator in the character pool, so every
    # name must be a real preset, and the current narrator is not its own predecessor.
    other_narrators = voices.get("other_narrators", [])
    if not isinstance(other_narrators, list) or not all(
        isinstance(name, str) and name.strip() for name in other_narrators
    ):
        raise ValueError("voices.other_narrators must be a list of preset names")
    for former in other_narrators:
        preset_by_name(former)
        if former == narrator_voice:
            raise ValueError("voices.other_narrators cannot name the current narrator")
''')

# ------------------------------------------------------------------ test
test = root / "tests" / "test_a_book_can_change_its_narrator.py"
test.write_text('''"""Một cuốn đổi người dẫn chuyện giữa chừng: người kể cũ không thành giọng nhân vật."""
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
''', encoding="utf-8")
print("ok: other_narrators o PresetAllocator + validate_settings + test")
