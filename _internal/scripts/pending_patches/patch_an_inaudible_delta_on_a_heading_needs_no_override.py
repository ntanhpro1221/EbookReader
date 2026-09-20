"""Vá analysis.py: tiêu đề chương lệch MỘT trường không-nghe-được thì không cần "ghi đè cấu trúc" - và đừng chết.

Chạy: python patch_an_inaudible_delta_on_a_heading_needs_no_override.py <root>

## Ca thật đã giết lô 11 (20-09 17:02:06)

    [critical] UNRECOVERABLE_PIPELINE_ERROR: Accepted critic evidence does not bind exact delivery/confidence for
    c00002_s0000000_a79c6349067f: agreement_with_override, structural_override; deltas=['intensity:0->1']
    expected=['intensity:0->1']

Đoạn ấy là **tiêu đề chương 461**. Lô 11 chết ở đoạn 122/3.705 sau 10 phút; `run` lại thì đi qua (lượt phản biện
thứ hai không sinh delta nào), nên nó là một cái chết NGẪU NHIÊN theo dữ liệu, không phải chặn cố định.

## Vì sao, đọc từ hai phía

Phía phân tích (`analysis.py`): với tiêu đề có delivery bị khoá, `if heading_delivery_is_locked and deltas:` ghi một
`structural_override` khai cứng `"raw_accept": False`, rồi đặt `accepted = True`.

Phía sổ (`database.py`): `expected_structural_override` chỉ tồn tại khi `raw_accept_value is False`, và
`structural_override_valid` đòi bản ghi TRÙNG KHỚP nó. Ghi đè có mà không hợp lệ là một trong các lý do khiến
`_validate_analysis_acceptance_evidence` ném lỗi.

Hai phía chỉ khớp khi delta là **nghe được**: lúc ấy `blocking_deltas` không rỗng, host thật sự KHÔNG đồng ý, cờ
accept thô là False, bản ghi `raw_accept: False` đúng. Còn khi delta **chỉ** thuộc `INAUDIBLE_DELIVERY_FIELDS`
(`emotion`, `intensity`) thì `AFFECT_CUE_DISAGREEMENT_BLOCKS = False` làm `host_derived_agreement = True` - host
ĐỒNG Ý - nhưng nhánh tiêu đề vẫn ghi một ghi-đè khai rằng nó đã từ chối. Đó là mâu thuẫn, và tầng sổ bắt đúng nó.

Vì thế 11 lô mới nổ một lần: cần đúng tổ hợp *tiêu đề + delivery khoá + delta chỉ-không-nghe-được*. Cùng họ với hai
sự cố đã ghi trong mã (`database.py` cạnh `AFFECT_CUE_DISAGREEMENT_BLOCKS`, và `tests/test_critic_accept_coherence.py`:
"a candidate whose only differences were emotion and intensity was accepted by one and refused by the other. That
killed a run at the same segment three times across two sittings.") - lần này nó đến qua nhánh tiêu đề.

## Vá

Một điều kiện: ghi `structural_override` khi có delta **CHẶN**, không phải khi có delta bất kỳ. Delta không-nghe-được
trên tiêu đề đã được `host_derived_agreement` nhận, không có gì để ghi đè, và `accepted` vẫn là True qua đường cũ.
KHÔNG đụng `database.py`: phía sổ đang đúng - nó đòi bản ghi phải khớp với sự thật, và sự thật là host đã đồng ý.
"""
import io
import sys
from pathlib import Path

root = Path(sys.argv[1])


def patch(path: Path, old: str, new: str) -> None:
    source = io.open(path, encoding="utf-8").read()
    assert source.count(old) == 1, f"khong khop mot lan duy nhat trong {path.name}: {old.splitlines()[0]!r}"
    io.open(path, "w", encoding="utf-8").write(source.replace(old, new, 1))
    print(f"da va {path}")


patch(
    root / "ebook_reader" / "analysis.py",
    '''        if heading_delivery_is_locked and deltas:''',
    '''        # `blocking_deltas`, KHÔNG phải `deltas`: một tiêu đề lệch chỉ ở `emotion`/`intensity` đã được
        # `host_derived_agreement` nhận, nên không có gì để ghi đè - mà ghi một `structural_override` khai
        # `raw_accept: False` trong khi host ĐỒNG Ý là tự mâu thuẫn, và `_validate_analysis_acceptance_evidence`
        # bắt đúng nó: lô 11 chết 17:02 ngày 20-09 ở tiêu đề chương 461 với `deltas=['intensity:0->1']`.
        if heading_delivery_is_locked and blocking_deltas:''',
)

test = root / "tests" / "test_an_inaudible_delta_on_a_heading_needs_no_override.py"
test.write_text('''"""Tiêu đề chương lệch một trường không-nghe-được thì không sinh ghi-đè cấu trúc.

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
''', encoding="utf-8")
print(f"da viet {test}")
