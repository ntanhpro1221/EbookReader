"""Hai dòng log về cách đọc tên phải mang tên model thật, không phải nhãn "Qwen" cứng.

Ca thật: log lượt đo `gemma4:e2b-it-qat` chương 378 (21-09) nói "Qwen không tạo được cách đọc hợp lệ" trong
khi không có Qwen nào trong chương - bước cách-đọc-tên dùng `self.model`. Nhãn cứng vô hại khi chỉ có một
model, và nói sai đúng lúc ta so nhiều model.

Kiểm bằng soi mã nguồn vì hai dòng ấy nằm sau một lượt gọi LLM thất bại ba lần.
"""
from __future__ import annotations

import inspect

from ebook_reader.analysis import OllamaBookAnalyzer


def _source() -> str:
    return inspect.getsource(OllamaBookAnalyzer)


def test_no_hard_coded_model_name_in_the_pronunciation_warnings() -> None:
    source = _source()
    assert "vì Qwen thất bại" not in source
    assert "Qwen không tạo được cách đọc hợp lệ" not in source


def test_both_lines_name_the_model_in_hand() -> None:
    source = _source()
    assert "vì {self.model} thất bại" in source
    assert "{self.model} không tạo được cách đọc hợp lệ" in source


def test_the_event_codes_are_untouched() -> None:
    """Mã lỗi giữ nguyên để mọi bộ đếm và truy vấn cũ còn khớp."""
    source = _source()
    assert "NAME_PRONUNCIATION_LOCAL_FALLBACK" in source
    assert "NAME_PRONUNCIATION_FROM_DICTIONARY" in source
