"""Transcript của Whisper cũng là văn bản do model sinh ra.

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

VO = json.loads('"\\ud83d"')


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
    text = json.loads('"\\ud83d\\ude00 xin chào"')
    assert strip_lone_surrogates(text) == text
