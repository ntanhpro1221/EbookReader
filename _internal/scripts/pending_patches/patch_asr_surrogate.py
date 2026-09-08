"""Va cua thu tu: transcript cua Whisper cung la van ban do model sinh ra.

CHUA AP. Lo 1b dang chay luc viet - khong sua file thuc thi khi co luot dang bay.

`patch_lone_surrogate.py` don phan hoi cua Ollama. Nhung khi liet ke lai cac nguon du lieu tu
ben ngoai thi danh sach ba nguon cua toi thieu mot: **transcript ASR**. No cung do mot model
sinh ra, no di thang vao cot `asr_text`, va sqlite TU CHOI nua cap surrogate lac y het
`sha256_text`:

    sqlite3 INSERT -> UnicodeEncodeError: 'utf-8' codec can't encode character '\\ud83d'

Xac suat thap hon Ollama - Whisper giai ma BPE chu khong sinh escape JSON - nhung cai gia
khong doi xung: mot lan la mot lo 13 gio chet. Va chinh `_grant_machine_acceptances` moi viet
dua `asr_text` vao `reason` lan `db.event`, nen no se lan truyen.
"""
import io
import os
import sys
import tempfile
from pathlib import Path


def write_atomic(path: Path, text: str) -> None:
    """Không bao giờ cắt bản gốc trước khi bản mới nằm trọn trên đĩa.

    Xem scripts/pending_patches/README.md: `open(p, "w")` cắt file lúc mở rồi mới mã hoá, nên
    một `UnicodeEncodeError` giữa chừng xoá sạch file - đã xảy ra với
    `docs/PRODUCTION_PLAN.md` ngày 2026-09-08, do đúng ký tự mà bản vá này nói tới.
    """
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    os.close(fd)
    io.open(tmp, "w", encoding="utf-8").write(text)
    os.replace(tmp, path)


root = Path(sys.argv[1])

# ---------------------------------------------------- hàm dọn, đặt ở io_utils
p = root / "ebook_reader" / "io_utils.py"
s = io.open(p, encoding="utf-8").read()
OLD = '''def sha256_text(text: str) -> str:
    return sha256_bytes(text.encode("utf-8"))'''
NEW = '''LONE_SURROGATE_PATTERN = re.compile("[\\ud800-\\udfff]")


def strip_lone_surrogates(text: str) -> str:
    """Bỏ những code point là **một nửa** của cặp surrogate.

    Đặt ở đây chứ không ở `analysis.py` vì đã có **hai** nguồn cần nó: phản hồi Ollama và
    transcript của Whisper. Cả hai là văn bản do model sinh ra, và cả hai đều tạo ra được một
    `str` hợp lệ trong bộ nhớ mà **không mã hoá UTF-8 được** - thứ giết lô 1 ngày 2026-09-08
    ngay dưới đây ở `sha256_text`, và cũng bị chính sqlite từ chối lúc `INSERT`.

    Xoá đúng khoảng D800-DFFF: mọi cặp hợp lệ đã được bộ giải mã ghép thành ký tự thật, nên
    thứ còn sót trong khoảng ấy chắc chắn là nửa lạc.
    """
    return LONE_SURROGATE_PATTERN.sub("", text)


def sha256_text(text: str) -> str:
    return sha256_bytes(text.encode("utf-8"))'''
assert OLD in s, "khong khop sha256_text"
s = s.replace(OLD, NEW, 1)
if "\nimport re\n" not in s:
    s = s.replace("import hashlib", "import hashlib\nimport re", 1)
write_atomic(p, s)
print(f"da va {p}")

# ---------------------------------------------------- dọn ngay khi transcript ra đời
p = root / "ebook_reader" / "asr.py"
s = io.open(p, encoding="utf-8").read()

OLD = """        if self.engine == "faster":
            return self._transcribe_faster(audio, duration_seconds, decode_options)"""
NEW = """        if self.engine == "faster":
            # Dọn ở **cả hai** nhánh engine, tại chỗ transcript ra đời. `transcribe()` không
            # phải nơi duy nhất gọi hàm này - còn một chỗ nữa ở nhánh lặp câu ngắn - nên bọc
            # ở đây thay vì bọc chỗ gọi.
            return strip_lone_surrogates(
                self._transcribe_faster(audio, duration_seconds, decode_options)
            )"""
assert OLD in s, "khong khop nhanh faster"
s = s.replace(OLD, NEW, 1)

OLD = '''        return str(result.get("text", "")).strip()'''
NEW = '''        return strip_lone_surrogates(str(result.get("text", "")).strip())'''
assert OLD in s, "khong khop nhanh openai"
s = s.replace(OLD, NEW, 1)

if "strip_lone_surrogates" not in s.split("def _transcribe_audio")[0]:
    # thêm import; asr.py chưa import gì từ io_utils
    marker = "import numpy as np"
    assert marker in s, "khong tim thay cho chen import"
    s = s.replace(
        marker,
        marker + "\n\nfrom .io_utils import strip_lone_surrogates",
        1,
    )
write_atomic(p, s)
print(f"da va {p}")

# ---------------------------------------------------- analysis.py dùng lại hàm chung
p = root / "ebook_reader" / "analysis.py"
s = io.open(p, encoding="utf-8").read()
OLD = '''LONE_SURROGATE_PATTERN = re.compile("[\\ud800-\\udfff]")


def strip_lone_surrogates(value: Any) -> Any:'''
NEW = '''from .io_utils import strip_lone_surrogates as _strip_one_string

LONE_SURROGATE_PATTERN = re.compile("[\\ud800-\\udfff]")


def strip_lone_surrogates(value: Any) -> Any:'''
if OLD in s:
    s = s.replace(OLD, NEW, 1)
    s = s.replace(
        "    if isinstance(value, str):\n        return LONE_SURROGATE_PATTERN.sub(\"\", value)",
        "    if isinstance(value, str):\n        return _strip_one_string(value)",
        1,
    )
    write_atomic(p, s)
    print(f"da va {p}")
else:
    print(f"bo qua {p} - da o dang khac")

# ---------------------------------------------------- test
q = root / "tests" / "test_asr_surrogate_does_not_kill_the_book.py"
write_atomic(
    q,
    '''"""Transcript của Whisper cũng là văn bản do model sinh ra.

Nguồn thứ tư, tìm ra khi rà lại danh sách "dữ liệu nào từ bên ngoài đi vào mà không qua chỗ
làm sạch" — và danh sách ba nguồn ban đầu của tôi thiếu đúng cái này.

sqlite từ chối nửa cặp surrogate lạc y hệt `sha256_text`, nên một transcript hỏng ghi vào cột
`asr_text` là một lô 13 giờ chết. Và `_grant_machine_acceptances` đưa `asr_text` vào cả `reason`
lẫn `db.event`, nên nó còn lan xa hơn.
"""
from __future__ import annotations

import json
import sqlite3

import pytest

from ebook_reader.io_utils import sha256_text, strip_lone_surrogates

VO = json.loads('"\\\\ud83d"')


def test_sqlite_refuses_it_too_not_just_the_hash() -> None:
    """Lý do phải dọn ASR chứ không chỉ dọn Ollama."""
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE t(x TEXT)")
    with pytest.raises(UnicodeEncodeError):
        conn.execute("INSERT INTO t VALUES(?)", (f"nghe ra {VO} roi",))


def test_a_cleaned_transcript_reaches_sqlite_and_the_hash() -> None:
    cleaned = strip_lone_surrogates(f"nghe ra {VO} roi")
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE t(x TEXT)")
    conn.execute("INSERT INTO t VALUES(?)", (cleaned,))
    assert conn.execute("SELECT x FROM t").fetchone()[0] == "nghe ra  roi"
    sha256_text(cleaned)


def test_both_engine_branches_are_cleaned() -> None:
    """Hai nhánh engine, hai đường trả transcript. Dọn một nhánh là chưa dọn."""
    import inspect

    from ebook_reader import asr

    source = inspect.getsource(asr.WhisperVerifier._transcribe_audio)
    assert source.count("strip_lone_surrogates") == 2, (
        "cả nhánh faster lẫn nhánh openai đều phải dọn"
    )


def test_real_emoji_survive() -> None:
    text = json.loads('"\\\\ud83d\\\\ude00 xin chào"')
    assert strip_lone_surrogates(text) == text
''',
)
print(f"da tao {q}")
