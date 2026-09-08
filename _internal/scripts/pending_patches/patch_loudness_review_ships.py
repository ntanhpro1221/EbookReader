"""Va audio_io.py: lech do to duoi nguong CUNG khong chan chuong nua.

CHUA AP. Lo 1b dang tong hop luc viet.

Chuong dau tien cua lo 1 hong ngay:

    temporary MP3 requires review under high-quality policy: loudness delta 0.62 LU

Ca hai doan cua no deu `verified`. Cai chan la mot co REVIEW o tang chuong - nghia den la
"co the dang nghe, hoi mot nguoi" - ma khong co nguoi nao.

CO Y HEP. Xem phan CHON HEP trong ma nguon ben duoi.
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
p = root / "ebook_reader" / "audio_io.py"
s = io.open(p, encoding="utf-8").read()

OLD = '''        if settings.get("quality_profile") == "high_quality" and quality.review_flags:
            raise ChapterQualityError('''
NEW = '''        blocking_review_flags = chapter_review_flags_that_block(quality.review_flags)
        if settings.get("quality_profile") == "high_quality" and blocking_review_flags:
            raise ChapterQualityError('''
assert OLD in s, "khong khop cho chan chuong"
s = s.replace(OLD, NEW, 1)

OLD = '''                "temporary MP3 requires review under high-quality policy: "
                + "; ".join(quality.review_flags),'''
NEW = '''                "temporary MP3 requires review under high-quality policy: "
                + "; ".join(blocking_review_flags),'''
assert OLD in s, "khong khop thong bao"
s = s.replace(OLD, NEW, 1)

ANCHOR = "CHAPTER_LOUDNESS_REVIEW_TOLERANCE_LU = 0.30"
assert ANCHOR in s, "khong khop cho chen ham"
HELPER = '''CHAPTER_LOUDNESS_REVIEW_TOLERANCE_LU = 0.30
LOUDNESS_REVIEW_FLAG_PREFIX = "loudness delta"


def chapter_review_flags_that_block(review_flags) -> list:
    """Cờ review nào thật sự phải chặn chương, khi không có ai để hỏi.

    Trước 2026-09-09 mọi cờ review đều chặn dưới `high_quality`, và chương đầu tiên của lượt
    sản xuất chết vì `loudness delta 0.62 LU`. Nghĩa đen của một cờ review là *"có thể đáng
    nghe, hỏi một người"* — mà lệnh của chủ sách là **không phải nghe**
    (docs/SHIPPING_WITHOUT_A_LISTENER.md).

    **CHỌN HẸP, và đây là lý do.** Đếm trên mọi project đã lưu, chỉ ba loại cờ review tầng
    chương từng xuất hiện:

        4 lần   unexpected silence   vd 1,02s     <- NGHE THẤY, vẫn chặn
        2 lần   join discontinuity   vd 0,183     <- NGHE THẤY, vẫn chặn
        2 lần   loudness delta       vd 0,62 LU   <- không nghe thấy, cho qua

    Một công tắc gộp sẽ đẩy cả **một giây mất tiếng** vào sách, và sẽ vô hiệu hoá
    `join discontinuity` — phép kiểm mà chính dự án đã đo là hiệu chỉnh đúng (nổ 1/107 lần,
    đúng vào cực đại thật). Chỉ mình độ to là đại lượng có ngưỡng nghe được rõ ràng, và
    `CHAPTER_LOUDNESS_HARD_TOLERANCE_LU = 0.75` đã là vạch mà chính dự án đặt ra cho "quá mức
    này thì chắc chắn có vấn đề". Một cờ độ to nằm dưới vạch ấy là phép kiểm tự nhận nó chưa
    chắc — cùng lý lẽ với *"ASR là nhân chứng duy nhất"*, chỉ khác là nhân chứng thứ hai ở đây
    là ngưỡng cứng của chính nó.

    Chương vẫn đi tiếp **và vẫn kêu**: `pipeline` đã có sẵn sự kiện `CHAPTER_QA_REVIEW_FLAGS`
    ghi mọi cờ, kể cả cờ được cho qua ở đây.
    """
    return [
        flag
        for flag in review_flags
        if not str(flag).startswith(LOUDNESS_REVIEW_FLAG_PREFIX)
    ]'''
s = s.replace(ANCHOR, HELPER, 1)

write_atomic(p, s)
print(f"da va {p}")

q = root / "tests" / "test_loudness_review_does_not_block.py"
write_atomic(
    q,
    '''"""Lệch độ to dưới ngưỡng cứng không chặn chương; những cờ nghe thấy được thì vẫn chặn.

Chương đầu tiên của lượt sản xuất hỏng ngày 2026-09-09 vì `loudness delta 0.62 LU` — nằm giữa
ngưỡng review 0,30 và ngưỡng cứng 0,75, tức phép kiểm tự nhận nó chưa chắc. Cả hai đoạn của
chương đều `verified`.

Bản vá cố ý hẹp. Đếm trên mọi project đã lưu, chỉ ba loại cờ review tầng chương từng gặp:
`unexpected silence` (4), `join discontinuity` (2), `loudness delta` (2). Hai loại đầu nghe
thấy được và vẫn chặn.
"""
from __future__ import annotations

from ebook_reader.audio_io import (
    CHAPTER_LOUDNESS_HARD_TOLERANCE_LU,
    CHAPTER_LOUDNESS_REVIEW_TOLERANCE_LU,
    chapter_review_flags_that_block,
)


def test_a_loudness_flag_alone_no_longer_blocks() -> None:
    """Đúng ca đã giết chương 000 của lô 1."""
    assert chapter_review_flags_that_block(["loudness delta 0.62 LU"]) == []


def test_an_audible_silence_still_blocks() -> None:
    """Một giây mất tiếng thì nghe thấy. Không cho qua."""
    assert chapter_review_flags_that_block(["unexpected silence 1.02s"]) == [
        "unexpected silence 1.02s"
    ]


def test_a_join_click_still_blocks() -> None:
    """`join discontinuity` là phép kiểm đã đo được là hiệu chỉnh đúng - đừng vô hiệu hoá nó."""
    assert chapter_review_flags_that_block(["join discontinuity 0.183"]) == [
        "join discontinuity 0.183"
    ]


def test_a_mixed_chapter_still_blocks_on_the_audible_one() -> None:
    """Cho qua độ to không được kéo theo phần còn lại."""
    flags = ["loudness delta 0.40 LU", "unexpected silence 1.02s"]
    assert chapter_review_flags_that_block(flags) == ["unexpected silence 1.02s"]


def test_the_hard_line_is_what_makes_this_safe() -> None:
    """Ranh giới không phải do ai bịa: chính dự án đặt vạch cứng ở 0,75.

    Cờ review chỉ tồn tại trong khoảng giữa hai vạch; vượt vạch cứng là `hard_failures`, và
    đường đó không đi qua hàm này.
    """
    assert CHAPTER_LOUDNESS_REVIEW_TOLERANCE_LU < CHAPTER_LOUDNESS_HARD_TOLERANCE_LU
    assert CHAPTER_LOUDNESS_HARD_TOLERANCE_LU == 0.75
''',
)
print(f"da tao {q}")
