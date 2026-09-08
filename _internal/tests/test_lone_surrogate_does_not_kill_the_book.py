"""Một emoji vỡ từ model không được giết cả cuốn sách.

Lô 1 của kế hoạch sản xuất chết lúc 19:3x ngày 2026-09-08, sau 1.406/3.727 đoạn:

    UnicodeEncodeError: 'utf-8' codec can't encode character '\\ud83d' - surrogates not allowed

`status=error`, `stage=unrecoverable_error`, không còn lease. Chuỗi hỏng vào từ
`json.loads(response_text)` của phản hồi Ollama, sống yên trong `str` của Python, rồi nổ tận
`sha256_text` lúc băm bằng chứng critic. Chỗ nổ chỉ là chỗ xui - nó có thể nổ ở bất cứ chỗ nào
ghi xuống sqlite hay ra file.
"""
from __future__ import annotations

import json

import pytest

from ebook_reader.analysis import contains_lone_surrogate, strip_lone_surrogates
from ebook_reader.io_utils import sha256_text

VO = json.loads('"\\ud83d"')  # đúng thứ model đã nhả ra: nửa đầu, không có nửa sau


def test_the_broken_half_really_does_kill_utf8() -> None:
    """Ghim lại chính cú nổ, để không ai tưởng đây là chuyện lý thuyết."""
    with pytest.raises(UnicodeEncodeError):
        sha256_text(VO)


def test_it_is_stripped_from_a_plain_string() -> None:
    assert strip_lone_surrogates(f"Nam{VO} 2026") == "Nam 2026"
    sha256_text(strip_lone_surrogates(f"Nam{VO} 2026"))  # không nổ nữa


def test_it_is_stripped_everywhere_in_a_nested_response() -> None:
    """Phản hồi phân tích là dict lồng list lồng dict; dọn một tầng là chưa dọn."""
    response = {
        "segments": [
            {"speaker": f"AN{VO}NA", "notes": ["ổn", f"vui{VO}"]},
            {"speaker": "BÌNH", "notes": []},
        ],
        f"khoa{VO}": "cả khoá cũng phải sạch",
    }

    cleaned = strip_lone_surrogates(response)

    assert not contains_lone_surrogate(cleaned)
    sha256_text(json.dumps(cleaned, ensure_ascii=False))
    assert cleaned["segments"][0]["speaker"] == "ANNA"
    assert cleaned["segments"][0]["notes"] == ["ổn", "vui"]
    assert "khoa" in cleaned


def test_real_emoji_survive() -> None:
    """Xoá đúng D800-DFFF, không quá tay: cặp hợp lệ đã thành ký tự thật từ `json.loads`."""
    text = json.loads('"\\ud83d\\ude00 xin chào"')  # 😀 - cặp đầy đủ
    assert strip_lone_surrogates(text) == text
    assert not contains_lone_surrogate(text)
    sha256_text(text)


def test_clean_input_is_returned_unchanged() -> None:
    payload = {"a": ["b", 1, None, True], "c": {"d": "ổn"}}
    assert strip_lone_surrogates(payload) == payload
    assert not contains_lone_surrogate(payload)
