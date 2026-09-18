"""Một cuốn đổi người dẫn chuyện ở một chương: lịch ở `book_paths`, cờ ở `cli create`.

Cuốn 2: Phạm Tuyên kể 000..303, Đức Trí từ 304 (chủ sách chọn 18-09, trang chấm giọng). Mọi project
tạo từ nay mang người kể CỦA DẢI mình và tên mọi người kể KHÁC của cuốn - để không nhân vật nào
được trao giọng người kể, dù ở phía nào của chỗ đổi. Phần bộ phân vai nằm trong bản vá khoá
`patch_a_book_can_change_its_narrator.py` và test của nó.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from scripts.book_paths import narrator_args, narrator_schedule

ROOT = Path(__file__).resolve().parent.parent
BOOK2 = "0=Phạm Tuyên;304=Đức Trí"


def test_a_book_without_a_schedule_passes_nothing() -> None:
    assert narrator_args(0, 915, "") == []


def test_each_side_of_the_switch_names_its_narrator_and_bars_the_other() -> None:
    assert narrator_args(219, 303, BOOK2) == ["--narrator", "Phạm Tuyên", "--other-narrator", "Đức Trí"]
    assert narrator_args(304, 343, BOOK2) == ["--narrator", "Đức Trí", "--other-narrator", "Phạm Tuyên"]
    # Vá một chương cũ sau khi đã đổi người kể: vẫn là người kể cũ.
    assert narrator_args(10, 10, BOOK2)[:2] == ["--narrator", "Phạm Tuyên"]


def test_a_range_across_the_switch_is_refused() -> None:
    with pytest.raises(ValueError, match="304"):
        narrator_args(300, 310, BOOK2)


def test_a_narrator_who_comes_back_is_named_once_and_not_barred_from_himself() -> None:
    assert narrator_args(250, 250, "0=Phạm Tuyên;100=Đức Trí;200=Phạm Tuyên") == [
        "--narrator",
        "Phạm Tuyên",
        "--other-narrator",
        "Đức Trí",
    ]


@pytest.mark.parametrize("spec", ["304=Đức Trí", "0=A;0=B", "0=A;x=B", "0=A;200=B;100=C", "0="])
def test_a_malformed_schedule_is_refused(spec: str) -> None:
    with pytest.raises(ValueError):
        narrator_schedule(spec)


def test_the_shell_reads_one_argument_per_line_without_carriage_returns() -> None:
    env = {**os.environ, "EBOOK_NARRATORS": BOOK2}
    done = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "book_paths.py"), "narrator-args", "304", "343"],
        env=env,
        capture_output=True,
        check=True,
    )
    assert done.stdout == "--narrator\nĐức Trí\n--other-narrator\nPhạm Tuyên\n".encode("utf-8")
    refused = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "book_paths.py"), "narrator-args", "300", "310"],
        env=env,
        capture_output=True,
    )
    assert refused.returncode == 2 and refused.stdout == b""


@pytest.mark.parametrize("script", ["launch_batch.sh", "launch_repair.sh"])
def test_both_launchers_ask_the_schedule_and_pass_it_to_create(script: str) -> None:
    source = (ROOT / "scripts" / script).read_text(encoding="utf-8")
    assert "scripts/book_paths.py narrator-args" in source
    create = source[source.index("-m ebook_reader.cli create"):]
    create = create[: create.index("--json")] + create[create.index("--json"): create.index("--json") + 120]
    assert '${NARR_ARGS[@]+"${NARR_ARGS[@]}"}' in create


def _args(**overrides: Any) -> argparse.Namespace:
    base: dict[str, Any] = {
        "settings_file": None,
        "profile": "high_quality",
        "first_person": "",
        "narrator": "",
        "other_narrator": [],
    }
    base.update(overrides)
    return argparse.Namespace(**base)


def test_the_command_line_writes_the_narrators_only_when_told() -> None:
    from ebook_reader.cli import _settings_from_args
    from ebook_reader.config import build_settings

    assert _settings_from_args(_args()) == build_settings("high_quality"), (
        "không truyền gì thì settings phải y hệt trước - `settings_hash` của project cũ không đổi"
    )
    chosen = _settings_from_args(_args(narrator=" Thanh Bình ", other_narrator=["Phạm Tuyên", " "]))
    assert chosen["voices"]["narrator_voice"] == "Thanh Bình"
    assert chosen["voices"]["other_narrators"] == ["Phạm Tuyên"]


@pytest.mark.parametrize(
    "overrides",
    [
        {"narrator": "Thanh Bình", "settings_file": "settings.json"},
        {"other_narrator": ["Phạm Tuyên"], "settings_file": "settings.json"},
    ],
)
def test_a_settings_file_cannot_be_mixed_with_narrator_flags(overrides: dict[str, Any]) -> None:
    from ebook_reader.cli import CliUsageError, _settings_from_args

    with pytest.raises(CliUsageError):
        _settings_from_args(_args(**overrides))
