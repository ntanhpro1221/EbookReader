"""Một bậc giọng nhớ mọi người đang giữ nó - nếu không, người thứ ba lại vào đúng chỗ vừa chiếm.

Đo trên lô đúc lại giọng của lô 3 (2026-09-10, 23:24), lần đầu `patch_wrap_prefers_a_stranger`
chạy thật. Bốn trên năm chương sạch. Chương 071 còn một va chạm, và nó lộ ra nửa mù của bản vá:

    KANG        -> Thanh Bình bậc 1,00   (VIKTOR đang giữ, VIKTOR KHÔNG nói trong 071)  <- đúng
    THẰNG ĐIÊN  -> Thanh Bình bậc 1,00   (đọc bậc ấy thành "của VIKTOR", người lạ)      <- sai

`holders` là `dict[float, str]` ghi bằng `setdefault` nên chỉ nhớ người đầu, và KANG - kẻ đang ở
cùng chương 071 - vô hình với lần chọn kế tiếp.
"""
from __future__ import annotations

from ebook_reader.character_registry import PresetAllocator


def _allocator() -> PresetAllocator:
    return PresetAllocator(narrator_voice="Phạm Tuyên", max_pitch_shift=7)


def test_a_step_remembers_every_holder_not_just_the_first() -> None:
    allocator = _allocator()
    allocator.reserve("Thanh Bình", 1.0, who="VIKTOR")
    allocator.reserve("Thanh Bình", 0.93, who="SAMAEL")

    allocator.holders["Thanh Bình"].setdefault(1.0, set()).add("KANG")

    assert allocator.holders["Thanh Bình"][1.0] == {"VIKTOR", "KANG"}


def test_the_third_speaker_sees_the_second_one(tmp_path: None = None) -> None:
    """Đúng ca chương 071: bậc 1,00 do VIKTOR (người lạ) *và* KANG (cùng chương) cùng giữ.

    Người thứ ba ở chương 071 phải tránh bậc ấy và chọn bậc chỉ có người lạ.
    """
    allocator = _allocator()
    ladder = (1.0, 0.93)
    # Cả hai bậc đã có chủ, nên mọi lựa chọn đều là dùng chung.
    allocator.reserve("Thanh Bình", 1.0, who="VIKTOR")
    allocator.reserve("Thanh Bình", 0.93, who="JAY")
    # KANG vào bậc 1,00; VIKTOR và JAY im lặng ở chương 71.
    allocator.holders["Thanh Bình"].setdefault(1.0, set()).add("KANG")
    allocator.note_chapters("KANG", {71})
    allocator.note_chapters("THẰNG ĐIÊN", {71})

    chosen = allocator._first_free_variant("Thanh Bình", ladder, who="THẰNG ĐIÊN")

    assert chosen == 0.93, (
        "bậc 1,00 có KANG cùng chương 71; bậc 0,93 chỉ có JAY im lặng - phải chọn 0,93"
    )


def test_a_free_step_still_wins_over_any_sharing() -> None:
    """Luật cũ không đổi: còn bậc trống thì lấy bậc trống, không cân ai với ai."""
    allocator = _allocator()
    allocator.reserve("Thanh Bình", 1.0, who="VIKTOR")
    allocator.note_chapters("KANG", {71})

    assert allocator._first_free_variant("Thanh Bình", (1.0, 0.93), who="KANG") == 0.93


def test_without_who_it_wraps_the_old_way() -> None:
    """Không biết ai sắp được cast thì lùi về quay vòng cũ - hành vi ngoài đường ống không đổi."""
    allocator = _allocator()
    allocator.reserve("Thanh Bình", 1.0, who="VIKTOR")
    allocator.reserve("Thanh Bình", 0.93, who="JAY")

    chosen = allocator._first_free_variant("Thanh Bình", (1.0, 0.93))

    assert chosen in (1.0, 0.93)
