"""Hai đứa trẻ trong một chương phải là hai giọng.

Lô 7, chương 186: AEREN (nam, trẻ con, 3 câu) và NPC CON TRAI (nam, trẻ con, 1 câu) cùng
`ngoc_linh_f107_p+02`. Tuổi ấn định bậc formant nên luật tránh-cùng-chương của thang bậc không
chạm tới trẻ con, và `usage` đếm theo pool nên đứa có tên và NPC không thấy nhau.
"""
from __future__ import annotations

from ebook_reader.character_registry import PresetAllocator


def _key(choice) -> tuple[str, float, int]:
    preset, ratio, pitch = choice
    return (str(preset["name"]), round(float(ratio), 3), int(pitch))


def test_a_named_child_and_an_npc_child_in_one_chapter_get_different_voices() -> None:
    allocator = PresetAllocator(narrator_voice="Phạm Tuyên", max_pitch_shift=4)
    allocator.note_chapters("AEREN", {186})
    allocator.note_chapters("NPC_LOCAL::C00020::CON TRAI", {186})

    first = allocator.choose("male", npc=False, age="child", who="AEREN")
    second = allocator.choose("male", npc=True, age="child", who="NPC_LOCAL::C00020::CON TRAI")

    assert _key(first) != _key(second), "cùng chương, cùng tuổi, cùng giới - vẫn phải là hai giọng"


def test_the_first_child_still_gets_the_listener_preferred_voice() -> None:
    """Sửa chỉ chạm đứa trẻ thứ hai: đứa đầu vẫn nhận giọng người nghe đã xếp hạng nhất."""
    allocator = PresetAllocator(narrator_voice="Phạm Tuyên", max_pitch_shift=4)
    allocator.note_chapters("AEREN", {186})

    preset, _ratio, _pitch = allocator.choose("male", npc=False, age="child", who="AEREN")

    assert str(preset["name"]) == "Ngọc Linh"


def test_two_children_in_different_chapters_may_share_the_preferred_voice() -> None:
    """Người nghe nghe từng chương một; hai đứa trẻ không bao giờ gặp nhau được dùng chung giọng
    ưa thích thay vì bị đẩy sang giọng hạng hai."""
    allocator = PresetAllocator(narrator_voice="Phạm Tuyên", max_pitch_shift=4)
    allocator.note_chapters("A", {10})
    allocator.note_chapters("B", {20})

    first = allocator.choose("male", npc=False, age="child", who="A")
    second = allocator.choose("male", npc=True, age="child", who="B")

    assert _key(first) == _key(second)
