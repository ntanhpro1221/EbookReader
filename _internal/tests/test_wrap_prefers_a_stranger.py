"""Khi buộc phải dùng chung giọng, chọn người KHÔNG cùng chương.

Lô 3: 18 người nam đòi 14 chỗ, nấc quay vòng chạy thật, và 3 trong 7 va chạm nằm cùng chương -
IGOR + THU LÃNH ở chương 062 (3 + 23 câu) đã vào audio. Nấc cũ là `variants[usage % len]`, mù
hoàn toàn về việc ai có mặt ở đâu. Người nghe nghe từng chương một, nên hại của một va chạm đo
bằng số chương hai người cùng có mặt - và khi PHẢI dùng chung thì câu hỏi là "với ai".
"""
from __future__ import annotations

from ebook_reader.character_registry import PresetAllocator
from ebook_reader.voice_catalog import formant_variants_for_preset


def _full_preset(allocator: PresetAllocator) -> tuple[str, list[str]]:
    """Cast người cho tới khi một preset nam hết bậc; trả về preset ấy và ai giữ bậc nào."""
    holders: list[str] = []
    for index in range(40):
        who = f"P{index:02d}"
        allocator.note_chapters(who, {index})  # mỗi người một chương riêng
        preset, _ratio, _pitch = allocator.choose("male", npc=False, who=who)
        holders.append((str(preset["name"]), who))
        name = str(preset["name"])
        if len(allocator.taken_variants.get(name, ())) >= len(formant_variants_for_preset(name)):
            return name, [w for n, w in holders if n == name]
    raise AssertionError("không preset nào đầy - fixture sai")


def test_a_forced_reuse_picks_someone_from_another_chapter() -> None:
    allocator = PresetAllocator(narrator_voice="Phạm Tuyên", max_pitch_shift=4)
    name, holders = _full_preset(allocator)
    variants = formant_variants_for_preset(name)
    # Người mới có mặt ở ĐÚNG chương của mọi người giữ bậc, trừ một người.
    stranger = holders[3]
    stranger_chapters = allocator.chapters_of[stranger]
    crowded = set()
    for who in holders:
        if who != stranger:
            crowded |= allocator.chapters_of[who]
    allocator.note_chapters("NEWCOMER", crowded)

    step = allocator._first_free_variant(name, variants, who="NEWCOMER")

    assert allocator.holders[name][round(step, 3)] == {stranger}, (
        "phải rơi vào bậc của người duy nhất không cùng chương"
    )
    assert not (allocator.chapters_of["NEWCOMER"] & stranger_chapters)


def test_the_real_lo03_shape_no_longer_lands_on_a_scene_partner() -> None:
    """SAMAEL đã ghim, nói ở 066 và 071; KANG mới, nói ở 066 và 071. Không được trùng."""
    allocator = PresetAllocator(narrator_voice="Phạm Tuyên", max_pitch_shift=4)
    name, holders = _full_preset(allocator)
    variants = formant_variants_for_preset(name)
    samael = holders[0]
    allocator.note_chapters(samael, {66, 71})
    allocator.note_chapters("KANG", {66, 71})
    # Mọi người khác ở chương khác hẳn.
    for who in holders[1:]:
        allocator.note_chapters(who, {900 + holders.index(who)})

    step = allocator._first_free_variant(name, variants, who="KANG")

    assert samael not in allocator.holders[name][round(step, 3)]


def test_a_silent_pinned_character_is_the_ideal_partner() -> None:
    """Ai đã ghim mà im lặng lô này có tập chương rỗng - không cùng chương với bất kỳ ai."""
    allocator = PresetAllocator(narrator_voice="Phạm Tuyên", max_pitch_shift=4)
    name, holders = _full_preset(allocator)
    variants = formant_variants_for_preset(name)
    quiet = holders[5]
    allocator.note_chapters(quiet, set())
    everyone = set()
    for who in holders:
        everyone |= allocator.chapters_of[who]
    allocator.note_chapters("NEWCOMER", everyone)

    step = allocator._first_free_variant(name, variants, who="NEWCOMER")

    assert allocator.holders[name][round(step, 3)] == {quiet}


def test_without_a_name_it_wraps_exactly_as_before() -> None:
    """Không biết đang cast cho ai thì không được đoán - giữ nguyên quay vòng cũ."""
    allocator = PresetAllocator(narrator_voice="Phạm Tuyên", max_pitch_shift=4)
    name, _holders = _full_preset(allocator)
    variants = formant_variants_for_preset(name)
    expected = variants[allocator.variant_usage[name] % len(variants)]

    assert allocator._first_free_variant(name, variants) == expected


def test_a_free_step_still_wins_over_any_stranger() -> None:
    """Còn bậc trống thì không có chuyện dùng chung - phần 3 chỉ chạy khi phần 1 đã cạn."""
    allocator = PresetAllocator(narrator_voice="Phạm Tuyên", max_pitch_shift=4)
    preset, ratio, _pitch = allocator.choose("male", npc=False, who="A")
    name = str(preset["name"])
    variants = formant_variants_for_preset(name)
    allocator.note_chapters("A", {1})
    allocator.note_chapters("B", {2})

    step = allocator._first_free_variant(name, variants, who="B")

    assert abs(step - ratio) > 0.005
