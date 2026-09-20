"""Tiêu đề chương lệch một trường không-nghe-được thì không sinh ghi-đè cấu trúc.

Ca thật: lô 11 chết 20-09 17:02 ở tiêu đề chương 461 - `deltas=['intensity:0->1']`, và phía sổ từ chối bản ghi
`structural_override` khai `raw_accept: False` trong khi host đã đồng ý. Cùng họ với sự cố đã ghi ở
`tests/test_critic_accept_coherence.py`, lần này qua nhánh tiêu đề.

Kiểm theo lối của file ấy - soi mã nguồn - vì đường phản biện tiêu đề nằm sâu trong một lượt gọi LLM.
"""
from __future__ import annotations

import inspect

from ebook_reader.analysis import _adjudicate_director_critic
from ebook_reader.database import AFFECT_CUE_DISAGREEMENT_BLOCKS, INAUDIBLE_DELIVERY_FIELDS, host_derived_accept


def _critic_source() -> str:
    source = inspect.getsource(_adjudicate_director_critic)
    assert "heading_delivery_is_locked" in source, "nhánh tiêu đề đã chuyển chỗ - đọc lại trước khi sửa test"
    return source


def test_the_heading_override_is_gated_on_blocking_deltas() -> None:
    source = _critic_source()
    assert "if heading_delivery_is_locked and blocking_deltas:" in source
    assert "if heading_delivery_is_locked and deltas:" not in source


def test_an_inaudible_only_delta_is_an_agreement() -> None:
    """Nếu ngày nào `AFFECT_CUE_DISAGREEMENT_BLOCKS` thành True thì bản vá này mất lý do tồn tại."""
    assert AFFECT_CUE_DISAGREEMENT_BLOCKS is False
    assert INAUDIBLE_DELIVERY_FIELDS == frozenset({"emotion", "intensity"})
    assert host_derived_accept(["intensity:0->1"]) is True
    assert host_derived_accept(["kind:narration->dialogue"]) is False
