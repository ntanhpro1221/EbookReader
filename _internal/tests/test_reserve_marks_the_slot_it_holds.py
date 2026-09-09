"""Giữ chỗ một giọng đã ghim phải đánh dấu đúng bậc formant nó đang giữ.

Lô 1: Thanh Bình nhận 7 nhân vật trên 7 bậc formant và chỉ sinh ra **6** giọng — bậc 0,898
không bao giờ được cấp cho ai, trong khi f104 được phát cho cả CHA lẫn SỐ BA. Vì `reserve()`
chỉ nhận tên preset nên nó nhích bộ đếm qua một bậc bất kỳ thay vì đánh dấu bậc đang bị giữ.

Xem docs/TWO_CHARACTERS_ONE_VOICE.md.
"""
from __future__ import annotations

from ebook_reader.character_registry import PresetAllocator
from ebook_reader.voice_catalog import formant_variants_for_preset


def _allocator() -> PresetAllocator:
    return PresetAllocator(narrator_voice="Phạm Tuyên", max_pitch_shift=4)


def test_a_reserved_step_is_not_handed_out_again() -> None:
    """Giữ chỗ một bậc rồi cấp tiếp cho tới khi preset ấy quay lại lượt: bậc ấy không được ra.

    (Bản đầu của test này khẳng định lượt chọn **ngay sau** `reserve` phải rơi vào cùng preset,
    và nó đỏ — đúng ra là sai: `reserve` tăng `pool_usage`, nên preset vừa bị giữ chỗ phải
    **tụt hạng** và lượt sau sang preset khác. Đó là hành vi mong muốn, test mới thì đợi.)
    """
    probe = _allocator()
    preset, ratio, _pitch = probe.choose("male", npc=False)
    name = str(preset["name"])
    variants = formant_variants_for_preset(name)

    allocator = _allocator()
    allocator.reserve(name, ratio)
    seen: list[float] = []
    for _ in range(len(variants) * 4):
        chosen, step, _pitch = allocator.choose("male", npc=False)
        if str(chosen["name"]) == name:
            seen.append(round(step, 3))
            if len(seen) >= len(variants) - 1:
                break

    assert seen, "không lần nào quay lại preset đã giữ chỗ — test không kiểm được gì"
    assert all(abs(step - ratio) > 0.005 for step in seen), (
        f"bậc {ratio} đã bị giữ mà vẫn được phát lại: {seen}"
    )


def test_no_step_is_skipped_before_the_ladder_is_exhausted() -> None:
    """Đây là cái lô 1 mất: một bậc bỏ phí *và* một bậc phát hai lần, cùng một lúc."""
    allocator = _allocator()
    first, ratio, _pitch = allocator.choose("male", npc=False)
    name = str(first["name"])
    variants = formant_variants_for_preset(name)

    allocator.reserve(name, ratio)  # ghim đúng giọng vừa cấp, như port_casting làm
    issued = [round(ratio, 3)]
    for _ in range(len(variants) * 2):
        preset, step, _pitch = allocator.choose("male", npc=False)
        if str(preset["name"]) != name:
            continue
        if len(set(issued)) >= len(variants):
            break
        issued.append(round(step, 3))

    assert len(issued) == len(set(issued)), f"một bậc bị phát hai lần: {issued}"


def test_it_still_wraps_once_every_step_is_taken() -> None:
    """Cạn thật thì dùng lại là không tránh được; nó phải quay vòng chứ không được nổ."""
    allocator = _allocator()
    preset, _ratio, _pitch = allocator.choose("male", npc=False)
    name = str(preset["name"])
    variants = formant_variants_for_preset(name)
    for step in variants:
        allocator.reserve(name, step)

    chosen = allocator._first_free_variant(name, variants)

    assert chosen in variants


def test_reserve_without_a_step_behaves_as_before() -> None:
    """Chỗ gọi cũ không biết bậc thì chỉ nhích bộ đếm — không được đánh dấu nhầm bậc nào."""
    allocator = _allocator()
    allocator.reserve("Thái Sơn")

    assert allocator.taken_variants.get("Thái Sơn", set()) == set()
    assert allocator.variant_usage["Thái Sơn"] == 1
