"""Khi buộc phải dùng chung bậc và không ai cùng chương với người mới, rải ra - đừng chồng.

Lô 6, 2026-09-12: sáu nhân vật phụ không cùng chương với bất kỳ ai đều rơi về cùng một bậc
`thai_son_f100_p+00`, vì hoà về chương chung thì luật cũ lấy bậc thấp nhất. Không ai cùng chương
nên người nghe không lẫn, nhưng sáu người một giọng là mười lăm cặp có thể gặp nhau ở lô sau.
"""
from __future__ import annotations

from ebook_reader.character_registry import PresetAllocator
from ebook_reader.voice_catalog import formant_variants_for_preset


def _fill_every_male_preset(allocator: PresetAllocator) -> list[str]:
    """Cast người ở các chương rời nhau cho tới khi mọi preset nam hết bậc; trả về tên preset."""
    full: list[str] = []
    for index in range(60):
        who = f"P{index:02d}"
        allocator.note_chapters(who, {index})
        preset, _ratio, _pitch = allocator.choose("male", npc=False, who=who)
        name = str(preset["name"])
        if (
            name not in full
            and len(allocator.taken_variants.get(name, ())) >= len(formant_variants_for_preset(name))
        ):
            full.append(name)
        if len(full) >= 2:
            return full
    raise AssertionError("kho nam không đầy - fixture sai")


def test_strangers_spread_across_equally_empty_steps() -> None:
    allocator = PresetAllocator(narrator_voice="Phạm Tuyên", max_pitch_shift=4)
    name = _fill_every_male_preset(allocator)[0]
    variants = formant_variants_for_preset(name)

    landed = []
    for k in range(3):
        who = f"NEW{k}"
        allocator.note_chapters(who, {500 + k})  # chương riêng, không gặp ai
        step = allocator._first_free_variant(name, variants, who=who)
        allocator.holders[name].setdefault(round(step, 3), set()).add(who)
        landed.append(round(step, 3))

    assert len(set(landed)) == 3, f"ba người lạ phải ở ba bậc, không phải {landed}"


def test_a_scene_partner_still_outranks_crowding() -> None:
    """Khoá đầu không đổi: một bậc trống người nhưng có bạn diễn vẫn thua một bậc đông mà lạ."""
    allocator = PresetAllocator(narrator_voice="Phạm Tuyên", max_pitch_shift=4)
    name = _fill_every_male_preset(allocator)[0]
    variants = formant_variants_for_preset(name)
    steps = [round(v, 3) for v in variants]
    partner_step, crowded_step = steps[0], steps[1]
    partner = next(iter(allocator.holders[name][partner_step]))
    allocator.note_chapters(partner, {700})
    for k in range(3):  # bậc thứ hai đã đông, toàn người lạ
        who = f"CROWD{k}"
        allocator.note_chapters(who, {800 + k})
        allocator.holders[name][crowded_step].add(who)
    for step in steps[2:]:  # các bậc còn lại: mỗi bậc một người có mặt ở chương 700
        for who in allocator.holders[name][step]:
            allocator.note_chapters(who, {700})
    allocator.note_chapters("NEWCOMER", {700})

    step = round(allocator._first_free_variant(name, variants, who="NEWCOMER"), 3)

    assert step == crowded_step
