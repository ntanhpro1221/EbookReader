"""Một nhân vật phụ hai câu thoại không được giết cả cuốn sách.

Lô 1b, 2026-09-08: chết sau **4 giờ phân tích trọn vẹn 3.727 đoạn** tại cổng đúc giọng, vì
`SỐ SÁU` được model gán một câu nữ một câu nam. Văn bản nói rõ *"người phụ nữ… cô ta"*, nhưng
bằng chứng chỉ có 3 hit trong khi `GENDER_EVIDENCE_MINIMUM_HITS = 5`.

Ngưỡng ấy **không** được hạ - đo trên mọi project đã lưu, bằng chứng nhất trí ở 3 hit lệch với
model 5/13 lần. Cái phải đổi là hậu quả: không phán xử được thì đi tiếp và nói to, chứ không
dừng cả cuốn sách.
"""
from __future__ import annotations

import pytest

from ebook_reader.character_registry import _validate_casting_inputs, resolve_gender


class _Row(dict):
    pass


def _speaking(name: str, gender: str, text: str = "Một câu thoại đủ dài để đếm.") -> _Row:
    return _Row(
        {
            "speaker": name,
            "gender": gender,
            "text": text,
            "canonical_character_id": 1,
            "voice_profile_id": None,
        }
    )


def test_a_split_vote_no_longer_raises() -> None:
    """Đúng hình dạng đã giết lô 1b: hai câu, một nữ một nam, chứng cứ văn bản mỏng."""
    rows = [_speaking("SỐ SÁU", "female"), _speaking("SỐ SÁU", "male")]

    unresolved = _validate_casting_inputs(rows, 3, lambda _m: None, {})

    assert "SỐ SÁU" in unresolved


def test_it_is_reported_rather_than_swallowed() -> None:
    """Không chặn, nhưng cũng không im lặng - chỗ gọi phát `CASTING_GENDER_UNRESOLVED`."""
    said: list[str] = []
    rows = [_speaking("SỐ SÁU", "female"), _speaking("SỐ SÁU", "male")]

    _validate_casting_inputs(rows, 3, said.append, {})

    assert any("SỐ SÁU" in line for line in said)
    assert any("cli cast" in line for line in said), "phải nói cách sửa"


def test_a_listener_lock_still_wins() -> None:
    """Người nghe đã đọc sách; model thì chưa. Khoá tay vẫn đè lên tất cả."""
    rows = [_speaking("SỐ SÁU", "female"), _speaking("SỐ SÁU", "male")]

    gender, reason = resolve_gender(rows, rows, {"SỐ SÁU": "female"})

    assert (gender, reason) == ("female", "listener")


def test_the_evidence_threshold_is_not_lowered() -> None:
    """Ghim lại con số, vì hạ nó là hướng sai mà số liệu đã bác bỏ.

    Đo trên mọi project đã lưu: bằng chứng văn bản nhất trí ở 3 hit mâu thuẫn với model 5 lần
    trên 13; ở 1 hit là 17 khớp / 18 lệch, tức tung đồng xu.
    """
    from ebook_reader import character_registry

    assert character_registry.GENDER_EVIDENCE_MINIMUM_HITS == 5
    assert character_registry.GENDER_EVIDENCE_MINIMUM_RATIO == 3.0


def test_other_gate_failures_still_stop_the_run() -> None:
    """Bản vá cố ý hẹp: chỉ mâu thuẫn giới tính thôi.

    Một danh tính gắn với hai nhân vật hoặc hai giọng là hỏng dữ liệu thật, và chưa có bằng
    chứng nào nói nó nên được cho qua.
    """
    rows = [
        _Row({"speaker": "AN", "gender": "female", "text": "x",
              "canonical_character_id": 1, "voice_profile_id": 1}),
        _Row({"speaker": "AN", "gender": "female", "text": "x",
              "canonical_character_id": 2, "voice_profile_id": 2}),
    ]

    with pytest.raises(RuntimeError, match="identity instability"):
        _validate_casting_inputs(rows, 3, lambda _m: None, {})
