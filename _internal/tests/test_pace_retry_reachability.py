"""The reachability table must show the shape of the attempts, not only a bell fitted to them.

Chapter 140, 2026-09-12: ten attempts, four distinct values, none inside the band, and the
bell said 38.9% per attempt. The next run - a repair that re-analysed the chapter - passed on
its first attempt. Both facts belong in the output: the gap is real for that run, and a run
is not the line.
"""
from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import pace_retry_reachability as reach  # noqa: E402

CHAPTER_140 = [24.79, 29.70, 24.79, 27.03, 12.45, 29.70, 27.03, 29.70, 24.79, 29.70]
ALPHA_32 = [11.81, 10.44, 12.47, 12.13]


def test_chapter_140_is_four_values_with_the_band_in_a_gap() -> None:
    distinct, widest, in_gap = reach._shape(CHAPTER_140, 12.5, 24.5)

    assert distinct == 4
    assert abs(widest - (24.79 - 12.45)) < 1e-9
    assert in_gap is True


def test_the_bell_is_optimistic_on_that_data_and_the_table_says_so() -> None:
    """The bell's answer is kept - it was right about the next run - but flagged."""
    chance = reach._chance_per_attempt(CHAPTER_140, 24.5, too_fast=True)

    assert 0.30 < chance < 0.50


def test_alpha_32_sits_just_below_the_floor_and_is_not_a_gap_case() -> None:
    distinct, _widest, in_gap = reach._shape(ALPHA_32, 12.5, 24.5)

    assert distinct == 4
    assert in_gap is False


def test_an_attempt_inside_the_band_means_no_gap() -> None:
    assert reach._shape([10.0, 20.0, 30.0], 12.5, 24.5)[2] is False


def test_main_flags_the_gap_in_the_table(tmp_path: Path, capsys) -> None:
    logs = tmp_path / "logs"
    logs.mkdir()
    segment = "c00022_s0000036_e93ccefefacc"
    lines = [
        f"TTS segment {segment} chưa đạt lần {i}/10; đang tạo lại: high-quality TTS retry"
        f" required: speech pace {pace:.2f} chars/s"
        for i, pace in enumerate(CHAPTER_140, start=1)
    ]
    lines.append(f"TTS segment {segment} thất bại hoàn toàn")
    (logs / "ebook_reader.log").write_text("\n".join(lines), encoding="utf-8")

    assert reach.main(str(tmp_path)) == 0
    out = capsys.readouterr().out

    row = next(line for line in out.splitlines() if line.startswith(segment[:30]))
    assert " 4 " in row and "12.34*" in row
    assert "khoảng trống" in out and "phân tích lại" in out
