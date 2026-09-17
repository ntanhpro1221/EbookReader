"""Cổng chọn giọng: loại một giọng vì chênh lệch nhỏ hơn độ phân giải của lượt đo là nhiễu, không phải kết luận.

Lượt 17-09 loại Quỳnh Anh trên 5 câu (~81 từ) vì thanh điệu tệ hơn ngưỡng đúng 1,2%, mà một lỗi đơn
lẻ ở đó cũng là 1,2%. Lượt 25 câu sau đó cho nó 1,4% - đạt. Các phép kiểm dưới đây khoá hành vi ấy.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ebook_reader.voice_catalog import VOCAL_TRACT_MAX_CM, VOCAL_TRACT_MIN_CM  # noqa: E402
from scripts.audition_presets import UNDECIDED, judge  # noqa: E402

WORST = {"tone_error_rate": 0.0167, "wer": 0.0769, "utmos": 2.558}


def measured(**overrides) -> dict:
    row = {"eligible": True, "why_not": "", "sentences": 25, "words_compared": 400,
           "tone_error_rate": 0.010, "wer": 0.030, "utmos": 3.0, "utmos_sem": 0.08,
           "vocal_tract_cm": 17.0}
    row.update(overrides)
    return row


def test_a_voice_inside_every_threshold_gets_in() -> None:
    assert judge(measured(), WORST) == {"verdict": "VAO POOL DUOC", "reasons": []}


def test_tone_worse_by_less_than_the_sampling_noise_is_not_a_verdict() -> None:
    # Anh Khôi, 18-09: 1,9% so với ngưỡng 1,67% trên 400 từ - lệch 0,26%, sai số của phép so là 0,94%.
    result = judge(measured(tone_error_rate=0.019), WORST)
    assert result["verdict"] == UNDECIDED
    assert "do them cau roi phan" in result["reasons"][0]


def test_tone_worse_by_more_than_the_sampling_noise_is_a_rejection() -> None:
    result = judge(measured(tone_error_rate=0.050), WORST)
    assert result["verdict"] == "khong"
    assert result["reasons"] == ["thanh dieu te hon gioi te nhat trong pool"]


def test_five_sentences_are_too_few_to_reject_on_tone() -> None:
    # Quỳnh Anh, lượt 5 câu: 4,9% so với ngưỡng 3,7%, 81 từ - sai số của phép so ở đó là 3,3%.
    five = measured(sentences=5, words_compared=81, tone_error_rate=0.049)
    assert judge(five, {**WORST, "tone_error_rate": 0.037})["verdict"] == UNDECIDED


def test_utmos_below_the_pool_floor_by_less_than_its_own_error_bar_waits() -> None:
    assert judge(measured(utmos=2.50, utmos_sem=0.20), WORST)["verdict"] == UNDECIDED
    assert judge(measured(utmos=2.50, utmos_sem=0.01), WORST)["verdict"] == "khong"


def test_a_hard_condition_still_rejects_outright() -> None:
    # Giọng đọc bản tin, vùng Trung, giọng chủ sách đã loại: không phải phép đo trên vài câu.
    result = judge(measured(eligible=False, why_not="phong cach tin tuc"), WORST)
    assert result["verdict"] == "khong"
    assert result["reasons"] == ["phong cach tin tuc"]


def test_a_rejection_beside_an_unresolved_margin_still_rejects() -> None:
    result = judge(measured(wer=0.200, tone_error_rate=0.019), WORST)
    assert result["verdict"] == "khong"
    assert result["reasons"][0] == "WER te hon gioi te nhat trong pool"
    assert any("do them cau roi phan" in reason for reason in result["reasons"])


def test_a_vocal_tract_outside_the_formant_model_rejects() -> None:
    for tract in (VOCAL_TRACT_MIN_CM - 0.5, VOCAL_TRACT_MAX_CM + 0.5, float("nan")):
        assert judge(measured(vocal_tract_cm=tract), WORST)["verdict"] == "khong"


def test_an_empty_pool_leaves_nothing_to_compare_against() -> None:
    empty = {"tone_error_rate": None, "wer": None, "utmos": None}
    assert judge(measured(tone_error_rate=0.5, wer=0.9, utmos=1.0), empty)["verdict"] == "VAO POOL DUOC"


def test_a_run_without_utmos_does_not_crash_the_gate() -> None:
    assert judge(measured(utmos=None, utmos_sem=None), WORST)["verdict"] == "VAO POOL DUOC"
