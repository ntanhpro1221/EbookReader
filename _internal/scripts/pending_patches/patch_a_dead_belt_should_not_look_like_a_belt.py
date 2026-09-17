"""Vá worker.py: bỏ năm chốt chặn offline đã CHẾT của transformers, giữ lại đúng chốt còn tác dụng.

Chạy: python patch_a_dead_belt_should_not_look_like_a_belt.py <root>

**XẾP Ở MỘT RANH GIỚI.** `worker.py` KHÔNG nằm trong `QUALITY_IMPLEMENTATION_FILES` (kiểm 18-09:
danh sách ấy có 20 module + `pyproject.toml` + `uv.lock`, không có `worker.py`), nên ghi vào nó không
làm resume bị từ chối — nhưng lô đang bay **sinh worker mới liên tục**, nên sửa giữa lô là để nửa lô
sau chạy mã khác nửa trước mà không có gì ghi lại. Bản vá KHÔNG đổi hành vi, nên ranh giới nào cũng
được, kể cả 6.

## Ca thật (18-09 02:0x, tìm ra bằng `tests/test_offline_guard_names.py`)

`_apply_model_network_policy` và `_apply_model_cache_policy` đặt cờ offline / đường dẫn cache lên các
module đã nạp, mỗi lần đặt đều qua `hasattr(...)`. Guard ấy biến một lần đổi tên ở thượng nguồn thành
im lặng. Và `transformers` 5.x đã đổi thật: đo trên đúng bản đang cài (5.16.1),

    transformers.utils._is_offline_mode              -> khong con
    transformers.utils.hub._is_offline_mode          -> khong con
    transformers.utils.import_utils._is_offline_mode -> khong con
    transformers.utils.HF_HUB_CACHE                  -> khong con
    transformers.utils.hub.HF_HUB_CACHE              -> khong con

Năm dòng trong `worker.py` vì thế là năm dòng không làm gì. Chúng tệ hơn là không có: người đọc mã
tin rằng transformers đã bị chốt, trong khi thứ chốt nó là chỗ khác.

## Vì sao KHÔNG hở

`transformers.utils.hub.is_offline_mode()` nay trả về đúng `huggingface_hub.constants.HF_HUB_OFFLINE`,
và cache đọc `huggingface_hub.constants.HF_HUB_CACHE` - hai mục ấy `worker.py` vẫn đặt, cộng với biến
môi trường `HF_HUB_OFFLINE` / `TRANSFORMERS_OFFLINE` đặt ngay trước đó.
`test_the_remaining_belt_really_switches_transformers_offline` chứng minh bằng cách bật cờ và gọi
`is_offline_mode()`.

Bản vá cũng sửa phép kiểm: `test_the_worker_still_names_it` chỉ soi các mục CÒN SỐNG, và thêm một
phép kiểm mới bắt `worker.py` **không** nhắc lại các tên đã chết - để nếu thượng nguồn trả chúng về
(phép kiểm `a_dead_entry_stays_dead` sẽ đỏ) thì việc thêm lại chốt là một quyết định có chủ ý.
"""
import io
import sys
from pathlib import Path

root = Path(sys.argv[1])
p = root / "ebook_reader" / "worker.py"
s = io.open(p, encoding="utf-8").read()

OLD_PATHS = '''    cached_paths = (
        ("huggingface_hub.constants", "HF_HOME", locked_values["HF_HOME"]),
        ("huggingface_hub.constants", "HF_HUB_CACHE", locked_values["HF_HUB_CACHE"]),
        ("transformers.utils", "HF_HUB_CACHE", locked_values["HF_HUB_CACHE"]),
        ("transformers.utils.hub", "HF_HUB_CACHE", locked_values["HF_HUB_CACHE"]),
    )'''

NEW_PATHS = '''    # transformers 5.x doc duong dan cache tu huggingface_hub.constants, khong con ban sao rieng:
    # `transformers.utils.HF_HUB_CACHE` va `transformers.utils.hub.HF_HUB_CACHE` khong ton tai o
    # 5.16.1 (do 18-09). Dat chung chi lam mã đọc như có chốt. tests/test_offline_guard_names.py
    # giu danh sach nay dung voi thu vien that.
    cached_paths = (
        ("huggingface_hub.constants", "HF_HOME", locked_values["HF_HOME"]),
        ("huggingface_hub.constants", "HF_HUB_CACHE", locked_values["HF_HUB_CACHE"]),
    )'''

OLD_FLAGS = '''    cached_flags = (
        ("huggingface_hub.constants", "HF_HUB_OFFLINE"),
        ("transformers.utils", "_is_offline_mode"),
        ("transformers.utils.hub", "_is_offline_mode"),
        ("transformers.utils.import_utils", "_is_offline_mode"),
        ("datasets.config", "HF_DATASETS_OFFLINE"),
    )'''

NEW_FLAGS = '''    # transformers.utils.hub.is_offline_mode() nay tra ve chinh
    # huggingface_hub.constants.HF_HUB_OFFLINE, nen dat mot co la chot ca hai; ba ten
    # `_is_offline_mode` cu khong con ton tai o 5.16.1 (do 18-09, bang
    # tests/test_offline_guard_names.py).
    cached_flags = (
        ("huggingface_hub.constants", "HF_HUB_OFFLINE"),
        ("datasets.config", "HF_DATASETS_OFFLINE"),
    )'''

assert OLD_PATHS in s, "khong khop cached_paths trong _apply_model_cache_policy"
assert OLD_FLAGS in s, "khong khop cached_flags trong _apply_model_network_policy"
s = s.replace(OLD_PATHS, NEW_PATHS, 1).replace(OLD_FLAGS, NEW_FLAGS, 1)
io.open(p, "w", encoding="utf-8").write(s)
print(f"da va {p}")

# ---------------------------------------------------------------------- test
p = root / "tests" / "test_offline_guard_names.py"
s = io.open(p, encoding="utf-8").read()

OLD_TEST = '''@pytest.mark.parametrize("module_name, attribute", LIVE + GONE)
def test_the_worker_still_names_it(module_name: str, attribute: str) -> None:
    assert f'("{module_name}", "{attribute}"' in WORKER_SOURCE, (
        f"worker.py khong con nhac {module_name}.{attribute}; danh sach trong phep kiem nay da lac hau."
    )'''

NEW_TEST = '''@pytest.mark.parametrize("module_name, attribute", LIVE)
def test_the_worker_still_names_it(module_name: str, attribute: str) -> None:
    assert f'("{module_name}", "{attribute}"' in WORKER_SOURCE, (
        f"worker.py khong con nhac {module_name}.{attribute}; danh sach trong phep kiem nay da lac hau."
    )


@pytest.mark.parametrize("module_name, attribute", GONE)
def test_the_worker_no_longer_pretends_to_set_a_dead_name(module_name: str, attribute: str) -> None:
    # Bỏ ở ranh giới sau khi đo được chúng không còn tồn tại. Nếu thượng nguồn trả tên về thì
    # `a_dead_entry_stays_dead` đỏ trước, và thêm lại chốt là một quyết định có chủ ý.
    assert f'("{module_name}", "{attribute}"' not in WORKER_SOURCE, (
        f"worker.py lai dat {module_name}.{attribute}; neu co y do thi chuyen muc nay sang LIVE."
    )'''

assert OLD_TEST in s, "khong khop test_the_worker_still_names_it"
s = s.replace(OLD_TEST, NEW_TEST, 1)
OLD_DOC = '''Dọn năm mục chết khỏi `worker.py` là việc ở RANH GIỚI: file này không bị khoá theo hash, nhưng lô
đang bay sinh worker mới liên tục, nên sửa giữa lô là để nửa lô sau chạy mã khác nửa trước.'''
NEW_DOC = '''Năm mục chết đã dọn khỏi `worker.py` ở một ranh giới, bằng
`patch_a_dead_belt_should_not_look_like_a_belt.py`.'''
assert OLD_DOC in s, "khong khop cau mo ta trong docstring cua phep kiem"
s = s.replace(OLD_DOC, NEW_DOC, 1)
io.open(p, "w", encoding="utf-8").write(s)
print(f"da va {p}")
