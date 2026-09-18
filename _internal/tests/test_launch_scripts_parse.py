"""Ba script ranh giới phải ít nhất PHÂN TÍCH được — chúng chạy lúc không có ai nhìn.

`boundary.sh` được thả trước khi lô xong và đọc tiếp file khi tới bước sau; một lỗi cú pháp ở
bước 6 chỉ lộ ra lúc ba giờ sáng, sau khi bốn bản vá đã áp và hai lô vá đã chạy. `bash -n`
bắt đúng lớp lỗi ấy trong một phần mười giây. Bỏ qua (có nói lý do) khi máy không có bash.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ["boundary.sh", "launch_batch.sh", "launch_repair.sh"]


def _bash() -> str | None:
    found = shutil.which("bash")
    if found:
        return found
    git_bash = Path("C:/Program Files/Git/bin/bash.exe")
    return str(git_bash) if git_bash.is_file() else None


@pytest.mark.parametrize("name", SCRIPTS)
def test_the_script_parses(name: str) -> None:
    bash = _bash()
    if bash is None:
        pytest.skip("không có bash trên máy này")
    result = subprocess.run(
        [bash, "-n", str(ROOT / "scripts" / name)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    assert result.returncode == 0, result.stderr


def test_every_launcher_seeds_through_seed_chain() -> None:
    """Một luật cho cả ba: "gieo từ đâu" trả lời bởi seed_chain.py, không bởi `ls -dt`."""
    for name in SCRIPTS:
        text = (ROOT / "scripts" / name).read_text(encoding="utf-8")
        assert "seed_chain.py" in text, name
        assert "ls -dt" not in text, f"{name}: mtime thư mục không xếp được project (xem seed_chain.py)"


def test_no_next_actually_guards_the_launch() -> None:
    """`--no-next` phải CHẶN bước 6, không chỉ được nhận rồi bỏ quên.

    Một cờ được phân tích nhưng không ai đọc là cái bẫy tệ nhất trong họ này: người gõ nó tin là
    GPU sẽ trống cho cuốn khác, rồi quay lại thấy lô kế đã chạy hai tiếng. Bài này đòi ba thứ:
    cờ có trong bảng tham số, biến được khởi tạo (script chạy `set -u`), và lệnh
    `launch_batch.sh "$NEXT"` nằm trong một nhánh do chính biến ấy canh.

    Vì sao cần cờ: cuốn 1 dừng ở 261/478 và còn 18 chương của lô 10; luật "không chạy hai cuốn
    cùng lúc" nghĩa là cửa sổ duy nhất của nó là khoảng giữa hai lô của cuốn 2 - đúng khoảng mà
    bước 6 lập tức chiếm lấy.
    """
    text = (ROOT / "scripts" / "boundary.sh").read_text(encoding="utf-8")

    assert "--no-next) NO_NEXT=1" in text, "cờ chưa được phân tích"
    assert "\nNO_NEXT=0\n" in text, "biến chưa khởi tạo - `set -u` sẽ nổ khi không truyền cờ"

    launch = text.index('bash scripts/launch_batch.sh "$NEXT"')
    guard = text.index('if [ "$NO_NEXT" = 1 ]; then')
    step_six = text.index("# ---- 6. lo ke tiep")
    assert step_six < guard < launch, "phép canh phải nằm giữa đầu bước 6 và lệnh thả lô"
    assert "--no-next" in text[: text.index("shift\n")], "dòng usage phải nói ra cờ này"


def test_wait_only_stops_before_anything_changes() -> None:
    """`--wait-only` là người gác, không phải ranh giới: nó phải thoát TRƯỚC bước đầu tiên có ghi.

    Dùng để canh một lô lớn chạy qua đêm khi không còn nhịp tim (16-09: lô 6 = 219..343, ~30 giờ).
    Nếu cờ được nhận mà lối thoát nằm sau `apply_all` / `git add -A` / `launch_repair` /
    `launch_batch`, thì một lệnh "chỉ canh" sẽ tự áp bản vá, commit, đúc lại và thả lô 7 vào sáng
    thứ 6 mà không ai hỏi — đúng cái mà chủ sách bỏ nhịp tim để khỏi phải trông.
    """
    text = (ROOT / "scripts" / "boundary.sh").read_text(encoding="utf-8")

    assert "--wait-only) WAIT_ONLY=1" in text, "cờ chưa được phân tích"
    assert "\nWAIT_ONLY=0\n" in text, "biến chưa khởi tạo - `set -u` sẽ nổ khi không truyền cờ"
    assert "--wait-only" in text[: text.index("shift\n")], "dòng usage phải nói ra cờ này"

    step_zero_done = text.index('say "lo $BATCH xong: $(chapter_statuses)"')
    guard = text.index('if [ "$WAIT_ONLY" = 1 ]; then')
    exit_here = text.index("exit 0", guard)
    assert step_zero_done < guard, "phải canh XONG lô rồi mới thoát"
    for writer in (
        "apply_all.py --apply",
        "git add -A",
        "git commit",
        "bash scripts/launch_repair.sh",
        'bash scripts/launch_batch.sh "$NEXT"',
        "assemble_book.py --apply",
        "tag_here \"",
    ):
        assert exit_here < text.index(writer, step_zero_done), f"lối thoát phải nằm trước `{writer}`"


def test_the_book_is_assembled_before_the_next_batch_is_pinned_against_it() -> None:
    """`launch_batch.sh` ghim giọng theo SÁCH ĐÃ GHÉP (`pin_the_book_cast.py`), nên lô vừa xong phải
    lên sách TRƯỚC khi lô kế được thả. Ranh giới 6 làm ngược lại (thả lô 7 15:11, ghép lô 6 15:13) và
    mọi nhân vật chỉ có ở lô 6 sang lô 7 nhận giọng mới: danh sách một-người-nhiều-giọng 49 -> 66."""
    text = (Path(__file__).resolve().parents[1] / "scripts" / "boundary.sh").read_text(encoding="utf-8")
    assemble = text.index("py scripts/assemble_book.py --apply")
    locked_reading = text.index("py scripts/keep_the_locked_reading.py --book --apply")
    launch = text.index('bash scripts/launch_batch.sh "$NEXT" --seed-from "$SEED"')
    assert locked_reading < assemble < launch
    launcher = (Path(__file__).resolve().parents[1] / "scripts" / "launch_batch.sh").read_text(encoding="utf-8")
    assert "scripts/pin_the_book_cast.py" in launcher, "nếu lô kế không còn ghim theo sách thì test này hết lý do"
