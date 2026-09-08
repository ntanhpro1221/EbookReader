"""Va character_registry.py: mau thuan gioi tinh khong duoc giet ca cuon sach.

CHUA AP. Lo 1b dang tong hop luc viet.

Lo 1b chet lan thu hai sau 4 GIO phan tich tron ven 3.727 doan, tai cong duc giong:

    RuntimeError: Casting input quality gate failed:
    gender conflicts={'SỐ SÁU': {'female': 1, 'male': 1, 'text_evidence': {'female': 3}}}

Mot nhan vat PHU, HAI cau thoai.
"""
import io
import os
import sys
import tempfile
from pathlib import Path


def write_atomic(path: Path, text: str) -> None:
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    os.close(fd)
    io.open(tmp, "w", encoding="utf-8").write(text)
    os.replace(tmp, path)


root = Path(sys.argv[1])
p = root / "ebook_reader" / "character_registry.py"
s = io.open(p, encoding="utf-8").read()

OLD = """    issues: list[str] = []
    if gender_conflicts:
        issues.append(f"gender conflicts={gender_conflicts}")
    if missing_named_genders:"""

NEW = '''    # Mâu thuẫn giới tính **không** giết lượt chạy nữa.
    #
    # Nó đã giết lô 1b ngày 2026-09-08, sau **4 giờ phân tích trọn vẹn 3.727 đoạn**, vì một
    # nhân vật phụ có đúng hai câu thoại mà model gán một nữ một nam. Văn bản trả lời rõ ràng
    # (3 nữ / 0 nam, và narration viết thẳng *"người phụ nữ… cô ta"*) nhưng
    # `GENDER_EVIDENCE_MINIMUM_HITS = 5` nên `_decisive` không dám quyết.
    #
    # Cổng này vi phạm nguyên tắc dự án đã chốt ở docs/SHIPPING_WITHOUT_A_LISTENER.md — *một
    # phép kiểm không phán xử được thì không được chặn* — và vi phạm nặng hơn cổng cảnh báo
    # segment: chương hỏng thì mất một chương, cổng này hỏng thì mất **cả cuốn sách**, ngay
    # sau khi đã trả xong phần đắt nhất của lượt chạy.
    #
    # KHÔNG hạ `GENDER_EVIDENCE_MINIMUM_HITS`. Đã đo trên mọi project đã lưu: bằng chứng văn
    # bản nhất trí ở 3 hit **mâu thuẫn với model 5 lần trên 13**, ở 1 hit thì đúng bằng tung
    # đồng xu (17 khớp / 18 lệch). Ngưỡng 5 không tuỳ tiện; đổi nó là mua một lỗi im lặng để
    # tránh một lỗi ồn ào.
    #
    # Nên: đúc bằng `unknown` (đường ống đã hỗ trợ - `casting_presets` nới rộng khi thiếu
    # giọng), ghi log to, và trả danh sách ra cho chỗ gọi phát `db.event`. Người nghe sửa
    # sau bằng một lệnh: `cli cast --character X --gender female`.
    for identity, detail in sorted(gender_conflicts.items()):
        log(
            f"Giới tính của {identity} không phán xử được ({detail}); đúc bằng giọng "
            f"trung tính và đi tiếp. Sửa bằng: cli cast --character {identity} --gender ..."
        )

    issues: list[str] = []
    if missing_named_genders:'''

assert OLD in s, "khong khop cong duc giong"
s = s.replace(OLD, NEW, 1)

# trả danh sách ra ngoài để chỗ gọi ghi sự kiện
OLD = """    if issues:
        raise RuntimeError("Casting input quality gate failed: " + "; ".join(issues))"""
NEW = """    if issues:
        raise RuntimeError("Casting input quality gate failed: " + "; ".join(issues))
    return gender_conflicts"""
assert OLD in s, "khong khop cho tra ve"
s = s.replace(OLD, NEW, 1)

OLD = """def _validate_casting_inputs(
    rows: list[Any],
    minimum_named_mentions: int,
    log: Callable[[str], None] = lambda _message: None,
    locked: dict[str, str] | None = None,
) -> None:"""
NEW = """def _validate_casting_inputs(
    rows: list[Any],
    minimum_named_mentions: int,
    log: Callable[[str], None] = lambda _message: None,
    locked: dict[str, str] | None = None,
) -> dict[str, dict[str, Any]]:
    \"\"\"Trả về những nhân vật không phán xử được giới tính. Không còn ném lỗi vì chúng.\"\"\""""
assert OLD in s, "khong khop chu ky ham"
s = s.replace(OLD, NEW, 1)

OLD = """    _validate_casting_inputs(rows, minimum_main_mentions, log, locked_genders)"""
NEW = """    unresolved_genders = _validate_casting_inputs(
        rows, minimum_main_mentions, log, locked_genders
    )
    for identity, detail in sorted(unresolved_genders.items()):
        # Không im lặng: cùng khuôn với cơ chế máy tự cho qua. Chương vẫn ra sản phẩm, nhưng
        # con số này phải nằm trong báo cáo để người nghe biết mà sửa nếu muốn.
        db.event(
            "warning",
            "CASTING_GENDER_UNRESOLVED",
            f"{identity}: {detail}",
        )"""
assert OLD in s, "khong khop cho goi"
s = s.replace(OLD, NEW, 1)

write_atomic(p, s)
print(f"da va {p}")

# ---------------------------------------------------------------- test
q = root / "tests" / "test_casting_gate_does_not_kill_the_book.py"
write_atomic(
    q,
    '''"""Một nhân vật phụ hai câu thoại không được giết cả cuốn sách.

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
''',
)
print(f"da tao {q}")
