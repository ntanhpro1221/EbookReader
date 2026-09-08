"""Va pipeline.py: cong chuong khong duoc phu nhan nhuong bo ma chinh duong ong vua lam.

CHUA AP. Lo 1b dang tong hop luc viet.

Chuong 007 cua lo 1 chet vi `TTS_PACE_BAND` tren mot doan mang nhan
`TTS_PACE_BAND_RELAXED` - tuc nhan ma duong ong gan SAU KHI da quyet dinh chap nhan ban thu ay.
"""
import io
import os
import sys
import tempfile
from pathlib import Path


def write_atomic(path: Path, text: str) -> None:
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    os.close(fd)
    io.open(tmp, "w", encoding="utf-8").write(text)
    os.replace(tmp, path)


root = Path(sys.argv[1])
p = root / "ebook_reader" / "pipeline.py"
s = io.open(p, encoding="utf-8").read()

OLD = """        ASR_TRANSCRIPT_TIMELINE_IMPOSSIBLE,
    }
)"""
NEW = '''        ASR_TRANSCRIPT_TIMELINE_IMPOSSIBLE,
        # Và một mã khác hẳn bốn mã trên: bốn mã kia nghĩa là *phép kiểm không có ý kiến*,
        # còn mã này nghĩa là **đường ống đã có ý kiến và ý kiến ấy là chấp nhận**.
        #
        # `_retry_in_normal_pace_band` chạy khi một đoạn không đạt băng nhịp được yêu cầu. Nó
        # thu lại tối đa bốn lần, chấm theo sàn `normal` thay vì băng đã xin, và chỉ giữ bản
        # thu **nếu bản ấy nằm trong băng normal** - nhánh `if metrics.get("pace_outlier"):
        # continue` bảo đảm điều đó. Gắn nhãn `TTS_PACE_BAND_RELAXED` là bước cuối cùng của
        # một quyết định chấp nhận, không phải một lời than.
        #
        # Chương 007 của lô 1 chết vì cổng này phủ nhận đúng quyết định ấy. Số liệu của chính
        # đoạn đó: `chars_per_second = 13,06`, `pace_outlier = 0`, `pace_band_relaxed = 1`;
        # băng `normal` là [12,5 – 24,5] còn `fast` là [14,0 – 30,0]. Phân tích xin `fast`,
        # model giao 13,06, bốn lần thu lại không lần nào chạm 14,0, và đường ống chấp nhận nó
        # theo băng normal — rồi cổng giết cả chương vì đúng cái nhãn ghi lại việc ấy.
        #
        # Để nó chặn thì phải bỏ luôn `_retry_in_normal_pace_band`, vì giữ cả hai là để đường
        # ống nhượng bộ rồi tự phủ nhận. Giữ nhượng bộ, bỏ mâu thuẫn.
        PACE_BAND_RELAXED_WARNING,
    }
)'''
assert OLD in s, "khong khop danh sach cho qua"
s = s.replace(OLD, NEW, 1)

# hằng số phải được định nghĩa TRƯỚC danh sách
OLD = """HIGH_QUALITY_ALLOWED_SEGMENT_WARNINGS = frozenset("""
NEW = """PACE_BAND_RELAXED_WARNING = "TTS_PACE_BAND_RELAXED"

HIGH_QUALITY_ALLOWED_SEGMENT_WARNINGS = frozenset("""
assert OLD in s, "khong khop cho chen hang so"
s = s.replace(OLD, NEW, 1)

# bỏ định nghĩa cũ ở dưới để khỏi trùng
OLD = """PACE_BAND_RELAXED_METRIC = "pace_band_relaxed"
PACE_BAND_RELAXED_WARNING = "TTS_PACE_BAND_RELAXED"
PACE_BAND_RELAX_ATTEMPTS = 4"""
NEW = """PACE_BAND_RELAXED_METRIC = "pace_band_relaxed"
PACE_BAND_RELAX_ATTEMPTS = 4"""
assert OLD in s, "khong khop dinh nghia cu"
s = s.replace(OLD, NEW, 1)

write_atomic(p, s)
print(f"da va {p}")

q = root / "tests" / "test_relaxed_pace_is_a_decision.py"
write_atomic(
    q,
    '''"""Cổng chương không được phủ nhận nhượng bộ mà chính đường ống vừa làm.

Chương 007 của lô 1 chết ngày 2026-09-09 vì `TTS_PACE_BAND`, trên một đoạn mang nhãn
`TTS_PACE_BAND_RELAXED`. Số liệu của chính đoạn ấy:

    chars_per_second 13,06   pace_outlier 0   pace_band_relaxed 1
    băng normal [12,5–24,5]  ·  băng fast [14,0–30,0]

Phân tích xin `fast`, model giao 13,06, `_retry_in_normal_pace_band` thu lại bốn lần không lần
nào chạm 14,0, rồi **chấp nhận** bản thu theo băng normal và gắn nhãn. Cổng giết chương vì đúng
cái nhãn ghi lại quyết định ấy.
"""
from __future__ import annotations

from ebook_reader.pipeline import (
    HIGH_QUALITY_ALLOWED_SEGMENT_WARNINGS,
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


def test_the_relaxed_tag_no_longer_blocks() -> None:
    """Đúng ca đã giết chương 007."""
    assert _blocking(PACE_BAND_RELAXED_WARNING) == []


def test_a_real_pace_outlier_still_blocks() -> None:
    """Nhượng bộ chỉ áp cho bản thu đã ĐẠT băng normal; ra ngoài băng thì vẫn chặn."""
    assert _blocking("TTS_PACE_OUTLIER") != []


def test_it_is_in_the_allowed_list_for_a_different_reason_than_the_others() -> None:
    """Bốn mã kia nghĩa là *phép kiểm không có ý kiến*; mã này nghĩa là *đã chấp nhận*.

    Ghi lại phân biệt ấy ở đây vì nó là lý do duy nhất khiến việc thêm mã này không phải là
    nới lỏng chính sách.
    """
    assert PACE_BAND_RELAXED_WARNING in HIGH_QUALITY_ALLOWED_SEGMENT_WARNINGS
    assert "TTS_PACE_OUTLIER" not in HIGH_QUALITY_ALLOWED_SEGMENT_WARNINGS


def test_the_concession_and_the_gate_cannot_disagree() -> None:
    """Nếu ai đó bỏ mã này khỏi danh sách thì phải bỏ luôn vòng thu lại nới lỏng.

    Giữ cả hai là để đường ống nhượng bộ rồi tự phủ nhận, và cái giá của mâu thuẫn ấy là cả
    một chương.
    """
    import inspect

    from ebook_reader import pipeline

    source = inspect.getsource(pipeline)
    has_relaxed_retry = "_retry_in_normal_pace_band" in source
    gate_allows = PACE_BAND_RELAXED_WARNING in pipeline.HIGH_QUALITY_ALLOWED_SEGMENT_WARNINGS
    assert has_relaxed_retry == gate_allows
''',
)
print(f"da tao {q}")
