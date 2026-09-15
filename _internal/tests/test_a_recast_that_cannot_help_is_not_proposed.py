"""Đừng đề nghị đúc lại một chương mà đúc lại không thể sửa được gì.

`--across` in ra những chương mang giọng **thiểu số** của một người để `boundary.sh --recast`
đọc lại chúng. Nhưng nếu giọng **đa số** của người ấy đang do người khác dùng **ngay trong
chương đó**, đúc lại không thể trả giọng ấy về: luật của dự án cấm hai người cùng chương dùng
một giọng (`_first_free_variant` → `shared_chapters`, và `_drop_pins_that_share_a_chapter` ở
tầng pin). Lần đúc lại ấy chỉ tái tạo đúng cái đánh đổi cũ.

Ca thật, đo 21:20 ngày 2026-09-15 trên sách 139 chương: CHRISTOPHER mang `thai_son_f104` ở
chương 110, 112, 114 còn đa số của anh là `thanh_binh_f090`. Ở 114 đúc lại là đúng — VERDI
không nói ở đó. Ở 110 và 112 thì VERDI đang dùng `f090` ngay trong chương ấy.

Trước phép lọc này danh sách đề nghị 15 chương; sau nó là 8, và 13 cặp (người, chương) được nói
rõ là không sửa được. Bảy chương ấy là ~1,5–2,5 giờ GPU để không đổi được gì.
"""
from __future__ import annotations

from scripts.one_person_one_voice import recast_arguments, voice_holders

F090 = "preset_thanh_binh_f090_p-04"
F104 = "preset_thai_son_f104_p+00"
BATCHES = {"110": 3, "112": 3, "114": 3, "047": 1}


def _shipped() -> list[tuple[str, str, str, int]]:
    """(chương, tên, giọng, số câu) như `shipped_voices` trả về."""
    return [
        ("110", "VERDI", F090, 10),
        ("110", "CHRISTOPHER", F104, 4),
        ("112", "VERDI", F090, 7),
        ("112", "CHRISTOPHER", F104, 17),
        ("114", "CHRISTOPHER", F104, 4),
        ("109", "CHRISTOPHER", F090, 7),
        ("113", "CHRISTOPHER", F090, 2),
    ]


MINORITY = {"CHRISTOPHER": (F090, {F104: {"110", "112", "114"}})}


def test_only_the_chapter_where_the_voice_is_free_is_proposed() -> None:
    skipped: list[str] = []

    arguments = recast_arguments(MINORITY, BATCHES, voice_holders(_shipped()), skipped)

    assert arguments == ["3:114"]
    assert len(skipped) == 2, skipped
    assert all("VERDI" in line for line in skipped)
    assert {"110", "112"} == {line.split()[1].rstrip(":") for line in skipped}


def test_without_the_holder_map_the_old_behaviour_stands() -> None:
    """Chỗ gọi nào chưa truyền bản đồ người giữ giọng vẫn chạy y như trước."""
    assert recast_arguments(MINORITY, BATCHES) == ["3:110", "3:112", "3:114"]


def test_a_chapter_survives_when_someone_else_there_can_be_fixed() -> None:
    """Chương 047 thật: HERODOTUS và OTHELLO đều không sửa được, nhưng ATHY thì được."""
    shipped = [
        ("047", "OTHELLO", "preset_thanh_binh_f108_p-04", 9),
        ("047", "HERODOTUS", "preset_thanh_binh_f093_p-04", 4),
        ("047", "ATHY", "preset_thanh_binh_f097_p-04", 3),
    ]
    minority = {
        # HERODOTUS muốn f108 mà OTHELLO đang dùng ở 047 -> không sửa được
        "HERODOTUS": ("preset_thanh_binh_f108_p-04", {"preset_thanh_binh_f093_p-04": {"047"}}),
        # ATHY muốn f090, không ai ở 047 dùng -> sửa được
        "ATHY": (F090, {"preset_thanh_binh_f097_p-04": {"047"}}),
    }
    skipped: list[str] = []

    arguments = recast_arguments(minority, BATCHES, voice_holders(shipped), skipped)

    assert arguments == ["1:047"]
    assert len(skipped) == 1 and "HERODOTUS" in skipped[0]


def test_the_person_holding_their_own_majority_voice_is_not_a_clash() -> None:
    """Chính người ấy dùng giọng ấy ở chương khác thì không phải va chạm với ai."""
    shipped = [("114", "CHRISTOPHER", F090, 4)]
    minority = {"CHRISTOPHER": (F090, {F104: {"114"}})}

    assert recast_arguments(minority, BATCHES, voice_holders(shipped)) == ["3:114"]


def test_a_chapter_with_no_known_batch_is_still_dropped() -> None:
    minority = {"CHRISTOPHER": (F090, {F104: {"999"}})}

    assert recast_arguments(minority, BATCHES, voice_holders(_shipped())) == []


def test_voice_holders_maps_chapter_to_voice_to_names() -> None:
    holders = voice_holders(_shipped())

    assert holders["110"][F090] == {"VERDI"}
    assert holders["110"][F104] == {"CHRISTOPHER"}
    assert "114" in holders and F090 not in holders["114"]
