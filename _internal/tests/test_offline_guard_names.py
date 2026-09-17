"""Lớp chặn tải mạng của `worker.py` chạm vào tên NỘI BỘ của thư viện - phép kiểm này giữ chúng thật.

`_apply_model_network_policy` và `_apply_model_cache_policy` đặt cờ offline / đường dẫn cache trực tiếp
lên các module đã nạp, và mỗi lần đặt đều đi qua `hasattr(...)`. Guard ấy biến một lần ĐỔI TÊN ở thượng
nguồn thành **im lặng**: vòng lặp bỏ qua, phép kiểm cũ (dựng module giả bằng `SimpleNamespace` trong
`test_worker_safety.py`) vẫn xanh, và không ai biết đã mất một lớp.

Và đã mất thật. `transformers` 5.16.1 không còn `utils._is_offline_mode`, `utils.hub._is_offline_mode`,
`utils.import_utils._is_offline_mode` hay `utils.HF_HUB_CACHE`: cả hai việc ấy đã dọn về
`huggingface_hub.constants`, nên **ba mục transformers trong `worker.py` là mục chết** - phát hiện
18-09 02:0x, chính bằng phép kiểm này. Dây chuyền không hở, vì lớp thật là biến môi trường
`HF_HUB_OFFLINE` cộng với `huggingface_hub.constants` (vẫn còn, vẫn được đặt), và
`test_the_remaining_belt_really_switches_transformers_offline` dưới đây chứng minh lớp ấy điều khiển
được transformers. Dọn năm mục chết khỏi `worker.py` là việc ở RANH GIỚI: file này không bị khoá theo hash, nhưng lô
đang bay sinh worker mới liên tục, nên sửa giữa lô là để nửa lô sau chạy mã khác nửa trước.

Nâng gói mà phép kiểm này đỏ: đọc changelog, tìm tên mới, sửa cả `worker.py` và danh sách dưới đây.
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

WORKER_SOURCE = (Path(__file__).resolve().parent.parent / "ebook_reader" / "worker.py").read_text(encoding="utf-8")

# Còn sống: đây là lớp đang thật sự chặn.
LIVE = [
    ("huggingface_hub.constants", "HF_HUB_OFFLINE"),
    ("huggingface_hub.constants", "HF_HOME"),
    ("huggingface_hub.constants", "HF_HUB_CACHE"),
    ("datasets.config", "HF_DATASETS_OFFLINE"),
]
# Đã chết ở phiên bản đang cài - `worker.py` vẫn liệt kê, và chỉ bỏ được ở ranh giới.
GONE = [
    ("transformers.utils", "_is_offline_mode"),
    ("transformers.utils.hub", "_is_offline_mode"),
    ("transformers.utils.import_utils", "_is_offline_mode"),
    ("transformers.utils", "HF_HUB_CACHE"),
    ("transformers.utils.hub", "HF_HUB_CACHE"),
]


def load(module_name: str):
    try:
        return importlib.import_module(module_name)
    except ImportError as error:  # môi trường không có gói ấy thì không có gì để chặn
        pytest.skip(f"{module_name} khong co trong moi truong nay: {error}")


@pytest.mark.parametrize("module_name, attribute", LIVE + GONE)
def test_the_worker_still_names_it(module_name: str, attribute: str) -> None:
    assert f'("{module_name}", "{attribute}"' in WORKER_SOURCE, (
        f"worker.py khong con nhac {module_name}.{attribute}; danh sach trong phep kiem nay da lac hau."
    )


@pytest.mark.parametrize("module_name, attribute", LIVE)
def test_the_attribute_that_still_does_the_work_exists(module_name: str, attribute: str) -> None:
    assert hasattr(load(module_name), attribute), (
        f"{module_name}.{attribute} khong con - lop chan offline trong worker.py da im lang bo qua no. "
        "Doc changelog cua goi, tim ten moi, sua ca worker.py va danh sach trong phep kiem nay."
    )


@pytest.mark.parametrize("module_name, attribute", GONE)
def test_a_dead_entry_stays_dead_or_we_want_to_know(module_name: str, attribute: str) -> None:
    # Đỏ ở đây là tin TỐT: thượng nguồn đã trả tên ấy về, và `worker.py` lại đặt được cờ - hãy
    # chuyển mục này sang LIVE. Đỏ theo chiều ngược (mục LIVE mất) mới là việc phải sửa gấp.
    assert not hasattr(load(module_name), attribute), (
        f"{module_name}.{attribute} da song lai - chuyen muc nay tu GONE sang LIVE."
    )


def test_the_remaining_belt_really_switches_transformers_offline(monkeypatch: pytest.MonkeyPatch) -> None:
    constants = load("huggingface_hub.constants")
    hub = load("transformers.utils.hub")
    monkeypatch.setattr(constants, "HF_HUB_OFFLINE", False, raising=True)
    assert hub.is_offline_mode() is False
    monkeypatch.setattr(constants, "HF_HUB_OFFLINE", True, raising=True)
    assert hub.is_offline_mode() is True, (
        "Dat huggingface_hub.constants.HF_HUB_OFFLINE khong con lam transformers offline; "
        "lop chan cuoi cung chi con bien moi truong."
    )


def test_the_worker_guards_every_write_with_hasattr() -> None:
    # Guard ấy là lý do một lần đổi tên trở thành im lặng thay vì nổ giữa một lô đang chạy: giữ nó,
    # và để các phép kiểm ở trên làm phần "biết mà sửa".
    assert WORKER_SOURCE.count("hasattr(module, attribute)") == 2
