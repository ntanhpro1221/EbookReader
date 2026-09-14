"""The nameless crowd must say where it speaks, or it lands on the protagonist's voice.

`_first_free_variant` avoids a same-chapter holder by reading `allocator.chapters_of`. The registry
filled that for named speakers only, so the three anonymous NPC groups were invisible to the rule that
exists to stop two people sharing one voice inside a chapter. Book 2, batch 1: "NPC vô danh nam" landed
on Thanh Bình 1.00 - LUCIEN's voice - in chapters 022, 023 and 032, and chapter 022 shipped that way.
Measured across 14 projects of both books: 12 same-chapter collisions, 4 of them with an anonymous group.
"""
from __future__ import annotations

import re
from pathlib import Path

from ebook_reader.character_registry import PresetAllocator, formant_variants_for_preset

ROOT = Path(__file__).resolve().parents[1]
PRESET = "Thanh Bình"


def _allocator_with_a_full_ladder(*, tell_the_crowd_its_chapters: bool) -> PresetAllocator:
    """Đúng hình của lô 1: mọi bậc của một preset đã có chủ, và chủ bậc thấp nhất ở chương 22."""
    allocator = PresetAllocator(narrator_voice="Phạm Tuyên", max_pitch_shift=7)
    variants = formant_variants_for_preset(PRESET)
    holders = [f"NGUOI_{index}" for index in range(len(variants))]
    allocator.note_chapters(holders[0], {22})       # LUCIEN: cùng chương với nhóm vô danh
    for holder in holders[1:]:
        allocator.note_chapters(holder, {77})       # những người khác: chương khác hẳn
    for holder, ratio in zip(holders, variants):
        allocator.reserve(PRESET, ratio, who=holder)
    if tell_the_crowd_its_chapters:
        allocator.note_chapters("ANONYMOUS_MALE", {22})
    return allocator


def test_a_crowd_that_names_its_chapters_avoids_the_voice_in_the_room() -> None:
    allocator = _allocator_with_a_full_ladder(tell_the_crowd_its_chapters=True)
    variants = formant_variants_for_preset(PRESET)

    chosen = allocator._first_free_variant(PRESET, variants, who="ANONYMOUS_MALE")

    assert abs(chosen - variants[0]) > 0.005, (
        "nhóm vô danh nói ở chương 22 không được nhận bậc của người cũng nói ở chương 22"
    )


def test_a_silent_crowd_lands_exactly_on_the_protagonist() -> None:
    """Bài này giữ lại chứng cứ: không khai chương thì tie-break lùi về bậc thấp nhất."""
    allocator = _allocator_with_a_full_ladder(tell_the_crowd_its_chapters=False)
    variants = formant_variants_for_preset(PRESET)

    chosen = allocator._first_free_variant(PRESET, variants, who="ANONYMOUS_MALE")

    assert abs(chosen - variants[0]) < 0.005


def test_the_registry_notes_the_anonymous_groups_before_it_casts_them() -> None:
    """Chỗ ghi phải nằm TRƯỚC lần `choose()` đầu tiên, không phải cạnh khối cast nhóm vô danh."""
    source = (ROOT / "ebook_reader" / "character_registry.py").read_text(encoding="utf-8")
    note = source.index('f"ANONYMOUS_{anonymous_gender.upper()}"')
    first_choose = source.index("allocator.choose(")
    assert note < first_choose, "ghi chương cho nhóm vô danh phải đứng trước choose() đầu tiên"
    assert re.search(r"for anonymous_gender, anonymous_gender_rows in anonymous_by_gender", source)
