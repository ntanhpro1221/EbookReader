"""Va analysis.py: mot nua cap surrogate lac tu model khong duoc giet ca cuon sach.

Lo 1 cua ke hoach san xuat chet luc 19:3x ngay 2026-09-08, sau 1.406/3.727 doan:

    UnicodeEncodeError: 'utf-8' codec can't encode character '\\ud83d'
    position 4940: surrogates not allowed

`status=error`, `stage=unrecoverable_error`, khong con lease. Ca cuon sach dung.
"""
import io
import sys
from pathlib import Path

root = Path(sys.argv[1])
p = root / "ebook_reader" / "analysis.py"
s = io.open(p, encoding="utf-8").read()

# ------------------------------------------------------------------ hàm dọn
ANCHOR = "def _ollama_usage_line("
assert ANCHOR in s, "khong khop cho chen ham don"
HELPER = '''LONE_SURROGATE_PATTERN = re.compile("[\\ud800-\\udfff]")


def strip_lone_surrogates(value: Any) -> Any:
    """Bỏ những code point là **một nửa** của cặp surrogate, ở mọi chuỗi trong cấu trúc.

    Lô 1 của kế hoạch sản xuất chết ở đây, 2026-09-08, sau 1.406/3.727 đoạn:

        UnicodeEncodeError: 'utf-8' codec can't encode character '\\ud83d' - surrogates
        not allowed

    Model phân tích nhả ra một emoji vỡ - `\\ud83d` mà không có nửa sau. `json.loads` dựng nó
    thành một code point hợp lệ trong `str` của Python nhưng **không mã hoá UTF-8 được**, nên
    mọi thứ hạ nguồn kế thừa một quả mìn: hàm nổ là `sha256_text` lúc băm bằng chứng critic,
    nhưng nó có thể nổ ở bất cứ chỗ nào ghi xuống sqlite hay ra file.

    Dọn ngay tại **biên nhận**, không dọn ở chỗ nổ. Chỗ nổ chỉ là chỗ xui; biên nhận là chỗ
    duy nhất mà "sau điểm này, chuỗi luôn mã hoá được" trở thành một lời hứa giữ được.

    Xoá đúng khoảng D800-DFFF là đủ và không quá tay: `json.loads` đã ghép mọi cặp **hợp lệ**
    thành ký tự thật, nên thứ còn sót lại trong khoảng ấy chắc chắn là nửa lạc.
    """
    if isinstance(value, str):
        return LONE_SURROGATE_PATTERN.sub("", value)
    if isinstance(value, list):
        return [strip_lone_surrogates(item) for item in value]
    if isinstance(value, tuple):
        return tuple(strip_lone_surrogates(item) for item in value)
    if isinstance(value, dict):
        return {
            strip_lone_surrogates(key): strip_lone_surrogates(item)
            for key, item in value.items()
        }
    return value


def contains_lone_surrogate(value: Any) -> bool:
    """Có nửa surrogate lạc nào trong cấu trúc không? Dùng để log, không để quyết định."""
    if isinstance(value, str):
        return bool(LONE_SURROGATE_PATTERN.search(value))
    if isinstance(value, (list, tuple)):
        return any(contains_lone_surrogate(item) for item in value)
    if isinstance(value, dict):
        return any(
            contains_lone_surrogate(key) or contains_lone_surrogate(item)
            for key, item in value.items()
        )
    return False


def _ollama_usage_line('''
s = s.replace(ANCHOR, HELPER, 1)

# ------------------------------------------------------------------ biên nhận
OLD = """        try:
            return json.loads(response_text)
        except json.JSONDecodeError as exc:"""
NEW = """        try:
            decoded = json.loads(response_text)
        except json.JSONDecodeError as exc:"""
assert OLD in s, "khong khop bien nhan json"
s = s.replace(OLD, NEW, 1)

OLD = """                ) from exc
            raise
"""
NEW = """                ) from exc
            raise
        # Dọn trước khi trả về, nên không có gì hạ nguồn phải biết chuyện này tồn tại.
        if contains_lone_surrogate(decoded):
            self.log(
                "Model phân tích trả về nửa cặp surrogate lạc (emoji vỡ); đã bỏ chúng đi. "
                "Không dọn thì `sha256_text` nổ và cả cuốn sách dừng."
            )
            self.db.event(
                "warning",
                "ANALYSIS_LONE_SURROGATE_STRIPPED",
                "Bỏ nửa cặp surrogate lạc khỏi phản hồi phân tích",
            )
            decoded = strip_lone_surrogates(decoded)
        return decoded
"""
assert OLD in s, "khong khop cho chen don"
s = s.replace(OLD, NEW, 1)

io.open(p, "w", encoding="utf-8").write(s)
print(f"da va {p}")

# ------------------------------------------------------------------ test
q = root / "tests" / "test_lone_surrogate_does_not_kill_the_book.py"
q.write_text(
    '''"""Một emoji vỡ từ model không được giết cả cuốn sách.

Lô 1 của kế hoạch sản xuất chết lúc 19:3x ngày 2026-09-08, sau 1.406/3.727 đoạn:

    UnicodeEncodeError: 'utf-8' codec can't encode character '\\\\ud83d' - surrogates not allowed

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

VO = json.loads('"\\\\ud83d"')  # đúng thứ model đã nhả ra: nửa đầu, không có nửa sau


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
    text = json.loads('"\\\\ud83d\\\\ude00 xin chào"')  # 😀 - cặp đầy đủ
    assert strip_lone_surrogates(text) == text
    assert not contains_lone_surrogate(text)
    sha256_text(text)


def test_clean_input_is_returned_unchanged() -> None:
    payload = {"a": ["b", 1, None, True], "c": {"d": "ổn"}}
    assert strip_lone_surrogates(payload) == payload
    assert not contains_lone_surrogate(payload)
''',
    encoding="utf-8",
)
print(f"da tao {q}")
