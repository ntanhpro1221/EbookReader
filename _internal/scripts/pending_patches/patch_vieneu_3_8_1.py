"""Nâng VieNeu 3.3.0 -> 3.8.1: pyproject, uv.lock, bảng phiên bản của hợp đồng chạy, và hai test ghim.

Chạy: python patch_vieneu_3_8_1.py <root>
Sau khi áp: `runtime/.venv/Scripts/python.exe -m pip install --no-deps vieneu==3.8.1` rồi
`pip uninstall -y perth`, RỒI mới chạy bộ test (test ghim phiên bản đọc gói ĐÃ CÀI).

**XẾP Ở RANH GIỚI 6.** pyproject.toml, uv.lock và runtime_contract.py đều nằm trong
`QUALITY_IMPLEMENTATION_FILES`, và đổi SDK là đổi giọng — nên làm giữa hai lô.

## Vì sao nâng (chủ sách quyết 18-09, trên trang chấm giọng)

Cùng preset, cùng seed, cùng câu, bản 3.3.0 và 3.8.1: chủ sách chấm cả bảy giọng đang dùng là
"như nhau" — luật đã hứa trên trang là không giọng nào tệ đi thì nâng. Cái được: sinh nhanh ~7,5 lần
trên máy này (0,44–0,52 so với 3,27–3,98 giây/100 ký tự), và 3.8 mới có các giọng chủ sách vừa nhận
(Mạnh Dũng, Anh Khôi, Minh Quân Pro, Thiền Tâm Đức, Adam bựa) cùng Xuân Vĩnh bản mới.

Trọng số model KHÔNG đổi (`VIENEU_CACHE_REVISION` giữ nguyên `8b7e9cff`): repo HF từ bản ghim tới
`main` chỉ đổi README và bản int8 cho CPU.

## uv.lock

Sinh bằng `uv lock --upgrade-package vieneu` trên bản sao pyproject đã đổi ghim, 18-09 10:4x:
đúng hai thay đổi — `vieneu 3.3.0 -> 3.8.1`, và `perth 1.0.0` bị gỡ. 3.8.1 dời bộ đóng dấu âm thanh
sang extra `watermark` (`resemble-perth`), dự án không dùng extra ấy và không import `perth` ở đâu.
File lock mới nằm ở `assets/uv.lock.vieneu381`; bản vá kiểm hash lock cũ trước khi thay.
"""
import hashlib
import io
import shutil
import sys
from pathlib import Path

root = Path(sys.argv[1])
here = Path(__file__).resolve().parent

OLD_LOCK_SHA256 = "68a30ac0e7404ed3496435def983e4c1c9c3fa6ff8a2574317732afc2b2a4952"


def replace_once(path: Path, old: str, new: str) -> None:
    text = io.open(path, encoding="utf-8").read()
    assert text.count(old) == 1, f"{path.name}: khong khop mot lan duy nhat: {old!r}"
    io.open(path, "w", encoding="utf-8").write(text.replace(old, new, 1))
    print(f"da va {path}")


replace_once(root / "pyproject.toml", '"vieneu==3.3.0"', '"vieneu==3.8.1"')

lock = root / "uv.lock"
digest = hashlib.sha256(lock.read_bytes()).hexdigest()
assert digest == OLD_LOCK_SHA256, f"uv.lock da doi tu luc sinh ban va ({digest[:16]}) - sinh lai lock"
shutil.copyfile(here / "assets" / "uv.lock.vieneu381", lock)
print(f"da thay {lock}")

replace_once(root / "ebook_reader" / "runtime_contract.py",
             '"vieneu": ("vieneu", "3.3.0"),', '"vieneu": ("vieneu", "3.8.1"),')
replace_once(root / "tests" / "test_one_click_startup.py", '"vieneu==3.3.0",', '"vieneu==3.8.1",')
replace_once(root / "tests" / "test_runtime_contract.py",
             'assert table.get("vieneu") == ("vieneu", "3.3.0")', 'assert table.get("vieneu") == ("vieneu", "3.8.1")')
