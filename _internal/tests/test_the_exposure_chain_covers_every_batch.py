"""Sổ cộng dồn phải dựng từ MỌI lô — một lượt vá lô cũ không được thu nó lại thành một lô.

`port_casting` quyết ai giữ một giọng **dùng chung** bằng sổ `character_exposure`: số câu cộng dồn
qua cả chuỗi lô. Kho giọng của cuốn 2 đã cấp hết (nam 14/14) nên chia giọng là tất yếu, và ai giữ
thì người kia phải đúc lại — nên con số ấy quyết định trực tiếp việc một nhân vật có đổi giọng
giữa các chương hay không.

## Cái giá đã mất, 06:37 ngày 2026-09-16

`launch_repair.sh 1` (bước 4b của ranh giới 4, vá các chương của lô 1) dựng chuỗi bằng
`seed_chain.py "$BATCH" --chain` = `chain(1)` = **chỉ lô 1**, rồi `backfill_exposure.py` ghi sổ
mới ấy vào project gieo — tức **ghi đè** sổ đầy đủ của `lo04`:

    truoc:  NATASHA 382 cau / 3 lo   (lo03, do 19:23 ngay 15-09)
    sau:    NATASHA   8 cau / 1 lo   CHELY 9 cau / 1 lo

NATASHA nói ở **42 chương**; lô 1 là chương 000..049, nơi bà ấy im. Nên ở phép xếp hạng của
`port_casting`, **8 < 9** và `CHELY` — một nhân vật **một chương** — thắng giọng
`ngoc_linh_f093`. NATASHA mất pin, và chương 090 đúc lại xong thì lên sách bằng giọng thiểu số
của bà ấy (`scripts/measure_did_the_recast_help.py`: tốt hơn 9, xấu hơn 2, và đây là ca xấu).

Chữa xong (dựng lại sổ với `--chain-all`, 25 project) thì `port_casting` nói ngược lại:

    BO QUA CHELY (duoc nhac 9 lan): NATASHA (duoc nhac 389 lan) giu preset_ngoc_linh_f093_p+00

**Luật xếp hạng của `port_casting` không sai** — nó cân bằng đúng thứ đáng cân (người nghe đã
nghe ai nhiều hơn). Sai là **đầu vào**: một phép đo cộng dồn bị thu lại còn một lô.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from scripts import seed_chain

ROOT = Path(__file__).resolve().parents[1]


def _project(folder: Path, created: float) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(folder / "project.sqlite3")
    try:
        connection.execute("CREATE TABLE book(created_at REAL)")
        connection.execute("INSERT INTO book(created_at) VALUES(?)", (created,))
        connection.commit()
    finally:
        connection.close()
    return folder


@pytest.fixture()
def versions(tmp_path: Path) -> Path:
    """Bốn lô, lô 3 có một project đúc lại - đúng hình dạng của cuốn đang chạy."""
    root = tmp_path / "_versions"
    _project(root / f"{seed_chain.TAG_PREFIX}-lo01" / "lo01_aaa", 100.0)
    _project(root / f"{seed_chain.TAG_PREFIX}-lo02" / "lo02_bbb", 200.0)
    _project(root / f"{seed_chain.TAG_PREFIX}-lo03" / "lo03_ccc", 300.0)
    _project(root / f"{seed_chain.TAG_PREFIX}-lo03r" / "lo03r_066_ddd", 310.0)
    _project(root / f"{seed_chain.TAG_PREFIX}-lo04" / "lo04_eee", 400.0)
    return root


def test_the_highest_batch_is_the_last_one_with_a_project(versions: Path) -> None:
    assert seed_chain.highest_batch(versions) == 4


def test_the_highest_batch_counts_a_repair_only_directory(tmp_path: Path) -> None:
    """Một lô mới có thể có project vá trước khi có project lô (084 ở lô 3 là ca thật)."""
    root = tmp_path / "_versions"
    _project(root / f"{seed_chain.TAG_PREFIX}-lo01" / "lo01_aaa", 100.0)
    _project(root / f"{seed_chain.TAG_PREFIX}-lo07v" / "lo07v_200_zzz", 700.0)

    assert seed_chain.highest_batch(root) == 7


def test_no_batch_at_all_is_zero(tmp_path: Path) -> None:
    assert seed_chain.highest_batch(tmp_path / "trong") == 0


def test_chain_of_one_batch_is_the_trap_that_shrank_the_ledger(versions: Path) -> None:
    """`chain(1)` đúng cho một lượt phóng tiến lên và SAI cho một lượt vá lô cũ."""
    assert [p.name for p in seed_chain.chain(1, versions)] == ["lo01_aaa"]
    assert [p.name for p in seed_chain.chain(seed_chain.highest_batch(versions), versions)] == [
        "lo01_aaa",
        "lo02_bbb",
        "lo03_ccc",
        "lo03r_066_ddd",
        "lo04_eee",
    ]


def test_both_launchers_build_the_ledger_from_every_batch() -> None:
    """Bài này là chỗ duy nhất bắt được việc ai đó đổi lại về `<lô> --chain`.

    Không có nó, phép hồi quy im lặng: sổ vẫn được dựng, vẫn có số, chỉ là số nhỏ hơn sự thật -
    và cái giá hiện ra nhiều giờ sau, ở một chương đã lên sách với giọng sai.
    """
    for name in ("launch_repair.sh", "launch_batch.sh"):
        text = (ROOT / "scripts" / name).read_text(encoding="utf-8")
        live = [line for line in text.splitlines() if not line.lstrip().startswith("#")]
        chain_lines = [line for line in live if "seed_chain.py" in line and "CHAIN=" in line]
        assert chain_lines, f"{name}: không còn dòng dựng CHAIN?"
        for line in chain_lines:
            assert "--chain-all" in line, f"{name}: {line.strip()}"
            assert "--chain)" not in line, f"{name}: vẫn lấy chuỗi của MỘT lô: {line.strip()}"
