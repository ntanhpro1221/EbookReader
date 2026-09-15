"""`MẸ` bỏ dấu thành `ME`, nhưng mẹ và con trai không phải một người.

`fold_dropped_marks` gộp cách viết **rơi dấu**, và nó đúng cho `THU LÃNH`/`THỦ LÃNH` hay
`NGUOI TRA LOI`/`NGƯỜI TRẢ LỜI` — cùng một cái tên, một bản bị rụng dấu. Nhưng bỏ dấu thì `MẸ`
thành `ME`, và đo trên cuốn 1 lúc 00:55 ngày 2026-09-16 thì đó là hai người khác nhau:

    ME   24 chương, preset_thai_son_f093 + preset_thanh_binh_f108   (nam)  - nhãn của NHÂN VẬT CHÍNH
    MẸ    1 chương, preset_ngoc_linh_f093                            (nữ)  - mẹ cậu ta

Cái giá nếu không chặn: báo cáo gọi đó là "một người **ba** giọng / 25 chương" và đưa chương 003
vào danh sách đúc lại — tức đốt GPU để bắt **mẹ** đọc bằng **giọng nam của con trai**. Một phép
"sửa" tạo ra khuyết tật. Chặn xong: danh sách đi từ 42 xuống 41 chương, và `ME` vẫn còn nguyên
khuyết tật thật của nó (24 chương, hai giọng nam).

Hai bằng chứng, chỉ cần một cái nói là đủ:

- `characters.gender` khác nhau. Một mình nó **không đủ**: trong các project đã lên sách, `MẸ`
  được ghi `unknown` ở vài project, nên phép so có thể im.
- **Phái của preset đang đọc họ.** Luôn có, và mạnh hơn: một giọng nam và một giọng nữ không
  bao giờ đọc cùng một người — đó là luật dàn giọng của chính dự án.

Luật gộp tên **không** đổi ở đây: `fold_dropped_marks` là bản song sinh của
`character_registry.dropped_marks_variant_of`, và `tests/test_name_marks_agree.py` ghim hai bản
phải khớp. Chỗ để nói "hai người khác phái không phải một người" là tầng đo, nơi có dữ liệu.
"""
from __future__ import annotations

from scripts.one_person_one_voice import (
    folds_that_cross_a_gender,
    preset_gender_of_voice,
    split_voices,
)

MALE_A = "preset_thai_son_f093_p+00"
MALE_B = "preset_thanh_binh_f108_p-04"
FEMALE = "preset_ngoc_linh_f093_p+00"


def test_the_preset_name_says_which_gender_reads_it() -> None:
    assert preset_gender_of_voice(FEMALE) == "female"
    assert preset_gender_of_voice(MALE_A) == "male"
    assert preset_gender_of_voice(MALE_B) == "male"
    assert preset_gender_of_voice("narrator") == "unknown"
    assert preset_gender_of_voice("preset_khong_co_ai_f100_p+00") == "unknown"


def test_a_recorded_gender_conflict_keeps_two_spellings_apart() -> None:
    folded = {"ME": "MẸ"}
    genders = {"ME": {"male"}, "MẸ": {"female"}}

    assert folds_that_cross_a_gender(folded, genders) == {"ME", "MẸ"}


def test_the_reading_voice_decides_when_the_recorded_gender_is_unknown() -> None:
    """Ca thật: `MẸ` được ghi `unknown` trong project đã lên sách, nhưng đọc bằng giọng nữ."""
    folded = {"ME": "MẸ"}
    genders = {"ME": {"male"}}  # MẸ không có phái đã ghi

    apart = folds_that_cross_a_gender(folded, genders, {"ME": {MALE_A}, "MẸ": {FEMALE}})

    assert apart == {"ME", "MẸ"}


def test_two_spellings_of_one_name_still_fold() -> None:
    """`THU LÃNH`/`THỦ LÃNH`: cùng phái, cùng giọng - phép gộp phải giữ nguyên."""
    folded = {"THU LÃNH": "THỦ LÃNH"}
    genders = {"THU LÃNH": {"male"}, "THỦ LÃNH": {"male"}}

    assert folds_that_cross_a_gender(folded, genders, {"THU LÃNH": {MALE_A}}) == set()


def test_no_evidence_at_all_leaves_the_fold_alone() -> None:
    assert folds_that_cross_a_gender({"ME": "MẸ"}, None, None) == set()
    assert folds_that_cross_a_gender({}, {"ME": {"male"}}, None) == set()


def test_split_voices_reports_them_as_two_people() -> None:
    rows = [(f"{n:03d}", "ME", MALE_A, 3) for n in range(200, 216)]
    rows += [(f"{n:03d}", "ME", MALE_B, 2) for n in range(216, 224)]
    rows += [("003", "MẸ", FEMALE, 3)]
    genders = {"ME": {"male"}, "MẸ": {"female"}}

    _inside, across = split_voices(rows, genders)

    assert "ME" in across, across
    assert len(across["ME"]) == 2, "hai giọng NAM của ME vẫn là khuyết tật thật"
    assert "MẸ" not in across, "một chương một giọng thì không có gì để báo"


def test_the_voice_evidence_alone_is_enough() -> None:
    """Không truyền phái thì vẫn tách, vì `split_voices` tự lấy giọng từ chính dữ liệu.

    Bản đầu của bài này đòi điều ngược lại ("không truyền phái thì gộp y như cũ") và đỏ ngay -
    đúng ra là nên đỏ: một giọng nam và một giọng nữ không bao giờ đọc cùng một người, và dữ
    liệu ấy nằm sẵn trong `rows`, không cần chỗ gọi đưa thêm gì. Phép chặn chỉ **tách** những
    nhóm không thể là một người, nên nó không cần ai bật.
    """
    rows = [("200", "ME", MALE_A, 3), ("003", "MẸ", FEMALE, 3)]

    _inside, across = split_voices(rows)

    assert across == {}, "mỗi người một chương một giọng thì không có gì để báo"
