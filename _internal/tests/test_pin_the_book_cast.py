"""Ghim giọng cho người cuốn sách đã nghe, và KHÔNG lật pin đã có.

Thứ tự là toàn bộ nội dung của bài này. Bản đầu xử va chạm giữa mọi giọng đa số trước rồi mới lọc
người đã có pin, nên nó "cho" KANG (13 chương) cái slot mà BOWDEN (6 chương) đang giữ pin và báo
BOWDEN là người nhường — lật đúng cái quyết định mà `port_casting` vừa mang sang.
"""
from __future__ import annotations

from scripts.pin_the_book_cast import majority_voices, resolve_collisions


def _rows(*triples: tuple[str, str, str]) -> list[dict]:
    """(chương, tên, giọng) -> dòng như `voice_matches_the_person` trả về."""
    return [
        {"chapter": chapter, "name": name, "voice": voice, "lines": 1}
        for chapter, name, voice in triples
    ]


def test_the_majority_voice_is_the_one_with_the_most_chapters() -> None:
    rows = _rows(
        ("065", "KANG", "preset_thanh_binh_f100_p-04"),
        ("071", "KANG", "preset_thanh_binh_f100_p-04"),
        ("066", "KANG", "preset_thanh_binh_f093_p-04"),
    )

    assert majority_voices(rows) == {"KANG": ("preset_thanh_binh_f100_p-04", 2, 3)}


def test_a_tie_goes_to_the_alphabetically_first_voice() -> None:
    rows = _rows(("001", "X", "preset_b_f100_p+00"), ("002", "X", "preset_a_f100_p+00"))

    assert majority_voices(rows)["X"][0] == "preset_a_f100_p+00"


def test_chapter_local_npcs_and_anonymous_are_left_out() -> None:
    rows = _rows(
        ("001", "NPC_LOCAL::C1::R2::LÍNH GÁC", "preset_a_f100_p+00"),
        ("001", "ANONYMOUS_UNKNOWN", "preset_b_f100_p+00"),
        ("001", "KANG", "preset_c_f100_p+00"),
    )

    assert set(majority_voices(rows)) == {"KANG"}


def test_an_existing_pin_is_never_overturned() -> None:
    """Đúng ca thật: KANG 13 chương, BOWDEN 6 chương và ĐANG giữ pin cái slot ấy.

    Không có `chapters_of` thì hàm coi như hai người có thể gặp nhau — thận trọng, và đúng hành
    vi cũ: pin đã có không bao giờ bị lật.
    """
    wanted = {
        "KANG": ("preset_thanh_binh_f100_p-04", 8, 13),
        "LYLE": ("preset_thai_son_f100_p+00", 3, 3),
    }
    owned = {"preset_thanh_binh_f100_p-04": "BOWDEN"}

    kept, dropped = resolve_collisions(wanted, owned)

    assert set(kept) == {"LYLE"}
    assert len(dropped) == 1
    assert "KANG" in dropped[0] and "BOWDEN đang giữ" in dropped[0]


def test_two_people_who_never_meet_may_share_one_pinned_voice() -> None:
    """Luật của dự án là "không hai người MỘT CHƯƠNG một giọng", không phải "một giọng một người".

    Bản trước bỏ mọi đề nghị rơi vào giọng đã có chủ, và trên lô 3 cuốn 2 nó bỏ **tất cả**: 0
    người được ghim, 21 lời "slot đã thuộc …" — tức tiếp tục đúng cái vòng đã đưa cuốn 1 từ 11
    lên 21 người mang hai giọng.
    """
    wanted = {"KANG": ("preset_thanh_binh_f100_p-04", 8, 13)}
    owned = {"preset_thanh_binh_f100_p-04": "BOWDEN"}
    chapters_of = {"KANG": {"010", "011"}, "BOWDEN": {"200", "201"}}

    kept, dropped = resolve_collisions(wanted, owned, chapters_of)

    assert set(kept) == {"KANG"}
    assert len(dropped) == 1
    assert "chia" in dropped[0] and "chưa từng cùng chương" in dropped[0]


def test_sharing_is_refused_when_the_two_do_meet() -> None:
    wanted = {"KANG": ("preset_thanh_binh_f100_p-04", 8, 13)}
    owned = {"preset_thanh_binh_f100_p-04": "BOWDEN"}
    chapters_of = {"KANG": {"010", "011"}, "BOWDEN": {"011", "200"}}

    kept, dropped = resolve_collisions(wanted, owned, chapters_of)

    assert kept == {}
    assert "có cùng chương" in dropped[0]


def test_two_new_proposals_that_never_meet_are_both_pinned() -> None:
    """Cùng luật ấy áp cho hai đề nghị mới đấu nhau, không chỉ cho đề nghị đấu với pin cũ."""
    wanted = {
        "KANG": ("preset_thanh_binh_f100_p-04", 8, 13),
        "LYLE": ("preset_thanh_binh_f100_p-04", 3, 3),
    }
    chapters_of = {"KANG": {"010", "011"}, "LYLE": {"300"}}

    kept, dropped = resolve_collisions(wanted, {}, chapters_of)

    assert set(kept) == {"KANG", "LYLE"}
    assert any("chia" in line for line in dropped)


def test_between_two_new_proposals_the_longer_running_character_wins() -> None:
    wanted = {
        "BIG": ("preset_a_f100_p+00", 5, 9),
        "SMALL": ("preset_a_f100_p+00", 2, 2),
        "ALONE": ("preset_b_f100_p+00", 1, 1),
    }

    kept, dropped = resolve_collisions(wanted, {})

    assert set(kept) == {"BIG", "ALONE"}
    assert len(dropped) == 1 and "SMALL" in dropped[0] and "nhường" in dropped[0]


def test_a_character_keeping_their_own_pin_is_not_treated_as_a_clash() -> None:
    wanted = {"KANG": ("preset_a_f100_p+00", 3, 3)}

    kept, dropped = resolve_collisions(wanted, {"preset_a_f100_p+00": "KANG"})

    assert set(kept) == {"KANG"} and dropped == []
