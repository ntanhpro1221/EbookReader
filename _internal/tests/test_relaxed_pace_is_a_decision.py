"""Nhịp bị làm nhạt là một **đánh đổi**, không phải một khuyết tật — nên máy được cho qua.

Chương 007 của lô 1 chết ngày 2026-09-09 vì `TTS_PACE_BAND`, trên một đoạn mang nhãn
`TTS_PACE_BAND_RELAXED`. Số liệu của chính đoạn ấy:

    chars_per_second 13,06   pace_outlier 0   pace_band_relaxed 1
    băng normal [12,5–24,5]  ·  băng fast [14,0–30,0]

Phân tích xin `fast`, model giao 13,06, `_retry_in_normal_pace_band` thu lại bốn lần không lần
nào chạm 14,0, rồi giữ bản thu ấy vì nó **nằm trong** băng normal.

Bản sửa đầu tiên của tôi đưa mã này vào `HIGH_QUALITY_ALLOWED_SEGMENT_WARNINGS`, và bộ test
bắt được: `test_the_warning_blocks_publication_so_a_person_hears_it` đã ghim từ trước rằng nó
**phải** chặn, với lý lẽ *"một cái đánh đổi thì nên có người nghe trước khi nó lên sách"*. Lý
lẽ ấy đúng. Cái đã đổi là giả định rằng có một người.

Nên nó không vào danh sách "được phép" (im lặng) mà vào danh sách "máy được tự cho qua" (có
ghi sổ) — chương lên được, và báo cáo vẫn nói chưa ai nghe.
"""
from __future__ import annotations

from ebook_reader.pipeline import (
    HIGH_QUALITY_ALLOWED_SEGMENT_WARNINGS,
    MACHINE_ACCEPTABLE_SEGMENT_WARNINGS,
    PACE_BAND_RELAXED_WARNING,
    BookPipeline,
)


class _Row(dict):
    pass


class _NothingRuledOn:
    @staticmethod
    def ruled_segment_warnings() -> dict:
        return {}


def _blocking(warning_code: str) -> list:
    pipeline = BookPipeline.__new__(BookPipeline)
    pipeline.settings = {"quality_profile": "high_quality"}
    pipeline.db = _NothingRuledOn()
    rows = [_Row({"id": 1, "stable_id": "c1s1", "wav_sha256": "aa", "warning_code": warning_code})]
    return BookPipeline._high_quality_blocking_segment_warnings(pipeline, rows)


def test_it_still_blocks_on_its_own() -> None:
    """Người viết vòng nới lỏng cố ý để nó chặn, và điều đó **không** bị bỏ."""
    assert _blocking(PACE_BAND_RELAXED_WARNING) != []
    assert PACE_BAND_RELAXED_WARNING not in HIGH_QUALITY_ALLOWED_SEGMENT_WARNINGS


def test_but_the_machine_may_accept_it_when_nobody_can_be_asked() -> None:
    assert PACE_BAND_RELAXED_WARNING in MACHINE_ACCEPTABLE_SEGMENT_WARNINGS


def test_a_take_outside_every_band_is_still_refused() -> None:
    """`TTS_PACE_OUTLIER` là khuyết tật, không phải đánh đổi. Máy không được đụng vào."""
    assert "TTS_PACE_OUTLIER" not in MACHINE_ACCEPTABLE_SEGMENT_WARNINGS
    assert _blocking("TTS_PACE_OUTLIER") != []


def test_the_machine_list_is_no_longer_only_asr_and_says_so() -> None:
    """Thêm một mã ngoài họ ASR buộc phải phát biểu lại nguyên tắc cho đúng.

    Không phải *"chỉ đè lên ASR"* mà là *"chỉ đè lên phép kiểm không nói bản thu hỏng"*. Nếu
    ai đó sửa lại docstring về câu cũ thì mã này không còn chỗ đứng trong danh sách.
    """
    from ebook_reader import pipeline

    doc = pipeline.__dict__.get("MACHINE_ACCEPTABLE_SEGMENT_WARNINGS")
    assert doc is not None
    import inspect

    source = inspect.getsource(pipeline)
    marker = "chỉ được đè lên một phép kiểm không nói rằng bản thu HỎNG"
    assert marker in source, "nguyên tắc phải được phát biểu lại ở chỗ khai báo"
