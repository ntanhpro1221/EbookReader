"""Người nghe đã ghim giới tính/tuổi thì giọng đa số chỉ tính trên các giọng KHÔNG trái với ghim.

Ca thật, đo 22-09 trên sách 533 chương: giọng đa số của mỗi người bị ghim chính là cái giọng sai người
nghe bảo sửa, vì phần lớn chương của họ được thu trước lúc ghim:

    CAMIL        ghim nữ        đa số thai_son_f093 (NAM) 12 chương | ngoc_huyen_f100 5, quynh_anh_f108 1
    CHRISTOPHER  ghim nam/già   đa số ngoc_linh_f107 (NỮ) 11 chương | thanh_binh_f090 5, thai_son_f104 4
    KAELYN       ghim nữ/lớn    đa số ngoc_linh_f109 (TRẺ CON) 4    | ngoc_linh_f093 1

`pin_the_book_cast` ghim giọng sai ấy, phân vai bỏ nó rồi rút thăm lại, và lô sau lặp lại - CAMIL nghe
bằng `quynh_anh_f108` ở lô 11 rồi `ngoc_huyen_f100` ở lô 12: đúng phái, hai giọng cho một người.
"""
from __future__ import annotations

from scripts.pin_the_book_cast import (
    majority_voices,
    pins_that_drifted,
    rows_the_listener_would_accept,
    voice_contradicts_a_person,
)

MALE = "preset_thai_son_f093_p+00"
FEMALE_A = "preset_ngoc_huyen_f100_p+00"
FEMALE_B = "preset_quynh_anh_f108_p+00"
CHILD = "preset_ngoc_linh_f109_p+04"
ADULT_F = "preset_ngoc_linh_f093_p+00"


def canonical(name: str) -> str:
    return name.upper()


def _rows(name: str, voice: str, chapters: range) -> list[dict]:
    return [{"name": name, "voice": voice, "chapter": str(c)} for c in chapters]


CAMIL_BOOK = (
    _rows("CAMIL", MALE, range(100, 112))        # 12 chương trước khi ghim
    + _rows("CAMIL", FEMALE_A, range(500, 505))   # 5 chương sau khi ghim
    + _rows("CAMIL", FEMALE_B, range(480, 481))   # 1 chương
)


def test_the_rule_is_the_same_as_casting() -> None:
    assert voice_contradicts_a_person(MALE, "female", None) is True
    assert voice_contradicts_a_person(FEMALE_A, "female", None) is False
    assert voice_contradicts_a_person(CHILD, "female", "adult") is True, "pitch trẻ con cho người lớn"
    assert voice_contradicts_a_person(CHILD, "male", "child") is False, "trẻ con đọc bằng preset nữ kéo cao"
    assert voice_contradicts_a_person(MALE, None, None) is False, "không ai ghim thì không kết tội"


def test_the_book_majority_ignores_voices_the_listener_rejected() -> None:
    assert majority_voices(CAMIL_BOOK)["CAMIL"][0] == MALE, "đây là lỗi cũ: đa số thô là giọng nam"
    accepted = rows_the_listener_would_accept(CAMIL_BOOK, {"CAMIL": ("female", None)}, canonical=canonical)
    assert majority_voices(accepted)["CAMIL"] == (FEMALE_A, 5, 6)


def test_people_nobody_pinned_are_untouched() -> None:
    rows = _rows("VERDI", MALE, range(1, 4))
    assert rows_the_listener_would_accept(rows, {"CAMIL": ("female", None)}, canonical=canonical) == rows


def test_a_pin_that_contradicts_the_person_is_replaced_by_the_best_accepted_voice() -> None:
    locked = {"CAMIL": ("female", None)}
    accepted = rows_the_listener_would_accept(CAMIL_BOOK, locked, canonical=canonical)
    drifted, _notes = pins_that_drifted(
        {"CAMIL": MALE}, accepted, {"534"}, canonical=canonical, presence=CAMIL_BOOK,
        rejects=lambda key, voice: voice_contradicts_a_person(voice, *locked.get(key, (None, None))),
    )
    assert drifted["CAMIL"][:2] == (MALE, FEMALE_A)


def test_one_accepted_chapter_is_enough_when_the_current_pin_is_wrong() -> None:
    """KAELYN: chỉ 1 chương giọng hợp lệ, dưới `min_chapters` - nhưng để nguyên ghim trẻ con thì phân
    vai chắc chắn bỏ nó và rút thăm lại, nên một chương hợp lệ vẫn tốt hơn."""
    book = _rows("KAELYN", CHILD, range(200, 204)) + _rows("KAELYN", ADULT_F, range(150, 151))
    locked = {"KAELYN": ("female", "adult")}
    accepted = rows_the_listener_would_accept(book, locked, canonical=canonical)
    drifted, _notes = pins_that_drifted(
        {"KAELYN": CHILD}, accepted, {"534"}, canonical=canonical, min_chapters=2, presence=book,
        rejects=lambda key, voice: voice_contradicts_a_person(voice, *locked.get(key, (None, None))),
    )
    assert drifted["KAELYN"][:2] == (CHILD, ADULT_F)


def test_without_rejects_the_old_narrow_rule_still_holds() -> None:
    """Không truyền `rejects` thì hành vi cũ giữ nguyên: 1 chương dưới ngưỡng thì không sửa."""
    book = _rows("KAELYN", CHILD, range(200, 204)) + _rows("KAELYN", ADULT_F, range(150, 151))
    drifted, _notes = pins_that_drifted({"KAELYN": CHILD}, book, {"534"}, canonical=canonical)
    assert drifted == {}, "đa số thô là chính pin hiện tại"


def test_collision_checks_use_every_chapter_the_person_was_present_in() -> None:
    """Người bị đọc bằng giọng SAI ở một chương vẫn có mặt ở chương ấy: phép kiểm va chạm phải thấy."""
    locked = {"CAMIL": ("female", None)}
    # NATASHA giữ FEMALE_A và gặp CAMIL ở chương 105 - nơi CAMIL còn bị đọc bằng giọng nam.
    book = CAMIL_BOOK + _rows("NATASHA", FEMALE_A, range(105, 106))
    accepted = rows_the_listener_would_accept(book, locked, canonical=canonical)
    drifted, notes = pins_that_drifted(
        {"CAMIL": MALE, "NATASHA": FEMALE_A}, accepted, {"105"}, canonical=canonical, presence=book,
        rejects=lambda key, voice: voice_contradicts_a_person(voice, *locked.get(key, (None, None))),
    )
    assert "CAMIL" not in drifted, "cùng chương 105 trong phạm vi lô này -> không được lấy giọng của NATASHA"
    assert any("105" in line for line in notes)
