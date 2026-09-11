"""`apply_all --apply` tự rút hàng chờ của nó, trước bộ test — để cây được kiểm là cây được commit.

Ở ranh giới lô 2 việc này làm tay, sau khi vân tay lượt xanh đã ghi, nên `before_a_batch` chạy
lại cả bộ test trên một cây chỉ khác đúng chỗ hàng chờ. Và một ranh giới tự chạy
(`scripts/boundary.sh`) không có tay nào: cửa số 3 của gate đọc chính `ORDER`, hàng chờ còn tên
là lô sau không bao giờ bắt đầu.
"""
from __future__ import annotations

import importlib.util
import re
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[1]
APPLY_ALL = ROOT / "scripts" / "pending_patches" / "apply_all.py"

SAMPLE = '''"""doc"""
from pathlib import Path

HERE = Path(__file__).resolve().parent

# Lý do của nhóm đang chờ - dòng này phải đi theo tên xuống APPLIED.
# Dòng thứ hai của lý do.
ORDER: tuple[str, ...] = (
    # chú thích nằm trong tuple
    "patch_one.py",
    "patch_two.py",
)

APPLIED = (
    "patch_zero.py",
)


def main(argv):
    return 0
'''


def _load(path: Path, name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("newline", ["\n", "\r\n"], ids=["lf", "crlf"])
def test_names_and_their_comment_move_from_order_to_applied(tmp_path: Path, newline: str) -> None:
    copy = tmp_path / "apply_all_copy.py"
    copy.write_bytes(SAMPLE.replace("\n", newline).encode("utf-8"))
    apply_all = _load(APPLY_ALL, "apply_all_under_test")

    moved = apply_all.retire_queue(copy, ["patch_one.py", "patch_two.py"], "2026-09-10")

    assert moved == 2
    module = _load(copy, "apply_all_retired_copy")
    assert module.ORDER == ()
    assert module.APPLIED == ("patch_zero.py", "patch_one.py", "patch_two.py"), (
        "hồ sơ giữ thứ tự: cái cũ trước, cái vừa rút sau"
    )
    text = copy.read_bytes().decode("utf-8")
    assert text.index("APPLIED = (") < text.index("Lý do của nhóm đang chờ"), (
        "khối chú thích trên ORDER đi theo tên xuống APPLIED"
    )
    assert "chú thích nằm trong tuple" in text.split("APPLIED = (")[1]
    assert "Lý do của nhóm" not in text.split("ORDER: tuple")[0]
    assert (b"\r\n" in copy.read_bytes()) is (newline == "\r\n"), "giữ nguyên kiểu xuống dòng"


def test_a_one_line_queue_round_trips(tmp_path: Path) -> None:
    """Hàng chờ MỘT tên hay được viết gọn trên một dòng: `ORDER: tuple[str, ...] = ("x.py",)`.

    Bản đầu của `retire_queue` tìm dấu `)` đứng riêng một dòng, nhảy qua tuple một dòng tới dấu
    đóng của `APPLIED`, và ghi ra một file không import được - đúng dạng hàng chờ cây thật mang
    lúc 18:35 ngày 2026-09-11. Ranh giới tự chạy không có ai sửa tay.
    """
    copy = tmp_path / "apply_all_copy.py"
    one_line = SAMPLE.replace(
        'ORDER: tuple[str, ...] = (\n    # chú thích nằm trong tuple\n    "patch_one.py",\n    "patch_two.py",\n)',
        'ORDER: tuple[str, ...] = ("patch_one.py",)',
    )
    assert one_line != SAMPLE
    copy.write_text(one_line, encoding="utf-8")
    apply_all = _load(APPLY_ALL, "apply_all_under_test_one_line")

    assert apply_all.retire_queue(copy, ["patch_one.py"], "2026-09-11") == 1

    module = _load(copy, "apply_all_one_line_retired")
    assert module.ORDER == ()
    assert module.APPLIED == ("patch_zero.py", "patch_one.py")
    assert "Lý do của nhóm đang chờ" in copy.read_text(encoding="utf-8").split("APPLIED = (")[1]


def test_an_empty_queue_is_left_untouched(tmp_path: Path) -> None:
    copy = tmp_path / "apply_all_copy.py"
    copy.write_text(SAMPLE, encoding="utf-8")
    before = copy.read_bytes()
    apply_all = _load(APPLY_ALL, "apply_all_under_test_empty")

    assert apply_all.retire_queue(copy, [], "2026-09-10") == 0
    assert copy.read_bytes() == before


def test_the_real_file_layout_round_trips(tmp_path: Path) -> None:
    """Chạy trên chính apply_all.py (bản sao), để bố cục thật — chú thích dài trên ORDER, APPLIED
    nhiều nhóm — được kiểm chứ không chỉ bản mẫu. Hàng chờ thật có thể rỗng; khi ấy bơm hai tên
    giả vào bản sao, vì bài này kiểm bố cục chứ không kiểm nội dung hàng chờ."""
    text = APPLY_ALL.read_text(encoding="utf-8")
    # Chỉ dòng ở cột 0: chuỗi `ORDER: tuple[str, ...] = ()` còn xuất hiện trong mã nguồn của
    # chính `retire_queue` (thụt vào), và thay nhầm nó là làm hỏng hàm đang được kiểm.
    text = re.sub(
        r"^ORDER: tuple\[str, \.\.\.\] = \(\)$",
        'ORDER: tuple[str, ...] = (\n    "patch_fake_a.py",\n    "patch_fake_b.py",\n)',
        text,
        count=1,
        flags=re.MULTILINE,
    )
    copy = tmp_path / "apply_all_real_copy.py"
    copy.write_text(text, encoding="utf-8")
    original = _load(copy, "apply_all_real_copy_before")
    names = list(original.ORDER)
    assert names, "bản sao phải có hàng chờ để rút"
    apply_all = _load(APPLY_ALL, "apply_all_under_test_real")

    assert apply_all.retire_queue(copy, names, "2026-09-10") == len(names)

    retired = _load(copy, "apply_all_real_copy_after")
    assert retired.ORDER == ()
    assert retired.APPLIED[: len(original.APPLIED)] == original.APPLIED
    assert list(retired.APPLIED[len(original.APPLIED) :]) == names
