"""Khi một người có hai giọng đều nhiều chương như nhau, số CÂU quyết, không phải bảng chữ.

`minority_chapters` chọn giọng "đa số" để giữ và đúc lại phần còn lại. Bản trước xếp theo
`(-số chương, tên giọng)`, nên một thế hoà 3–3 do chuỗi `preset_thai_son…` đứng trước
`preset_thanh_binh…` quyết. Đo trên sách cuốn 2 lúc 09:55 ngày 2026-09-15: CORELLA (3 ch / 9 câu
so với 3 ch / 5 câu) và ATHY (3 ch / 8 câu so với 3 ch / 6 câu) đều hoà về số chương, và cả hai
lần bảng chữ tình cờ trùng với bằng chứng — nên danh sách đúc lại không đổi, nhưng nó đã có lý do
thay vì có may mắn.

Mỗi chương đúc lại tốn ~12 phút GPU, nên chọn sai phía là trả tiền thật.
"""
from __future__ import annotations

from scripts.one_person_one_voice import lines_by_name_voice, minority_chapters

# Bảng chữ thích "aaa_voice"; bằng chứng thích "zzz_voice" (nhiều câu hơn).
ALPHABET_FIRST = "preset_aaa_f100_p+00"
MORE_LINES = "preset_zzz_f100_p+00"


def test_lines_decide_a_chapter_tie_even_against_the_alphabet() -> None:
    across = {
        "CORELLA": {
            ALPHABET_FIRST: {"003", "004", "006"},
            MORE_LINES: {"060", "061", "092"},
        }
    }
    lines = {"CORELLA": {ALPHABET_FIRST: 5, MORE_LINES: 9}}

    majority, minority = minority_chapters(across, min_chapters=5, lines=lines)["CORELLA"]

    assert majority == MORE_LINES, "giọng nhiều câu hơn phải được giữ"
    assert minority == {ALPHABET_FIRST: {"003", "004", "006"}}


def test_without_line_evidence_the_old_order_still_applies() -> None:
    """Chỗ gọi nào chưa có số câu vẫn phải chạy y như trước."""
    across = {
        "CORELLA": {
            ALPHABET_FIRST: {"003", "004", "006"},
            MORE_LINES: {"060", "061", "092"},
        }
    }

    majority, _minority = minority_chapters(across, min_chapters=5)["CORELLA"]

    assert majority == ALPHABET_FIRST


def test_chapter_count_still_outranks_lines() -> None:
    """Số chương là bằng chứng chính: gặp ở nhiều chỗ hơn thắng, dù ít câu hơn."""
    across = {
        "OTHELLO": {
            "preset_many_chapters": {"056", "060", "061", "062", "069"},
            "preset_few_chapters": {"047"},
        }
    }
    lines = {"OTHELLO": {"preset_many_chapters": 25, "preset_few_chapters": 700}}

    majority, minority = minority_chapters(across, min_chapters=5, lines=lines)["OTHELLO"]

    assert majority == "preset_many_chapters"
    assert minority == {"preset_few_chapters": {"047"}}


def test_the_earliest_chapter_breaks_a_full_tie() -> None:
    """Hoà cả chương lẫn câu: giữ giọng người nghe làm quen trước."""
    across = {
        "IVEN": {
            "preset_later": {"050", "051", "052"},
            "preset_earlier": {"001", "011", "025"},
        }
    }
    lines = {"IVEN": {"preset_later": 7, "preset_earlier": 7}}

    majority, _minority = minority_chapters(across, min_chapters=5, lines=lines)["IVEN"]

    assert majority == "preset_earlier"


def test_line_totals_fold_a_name_that_lost_its_marks() -> None:
    """`Hạ Phong` và `Ha Phong` là một người; số câu phải cộng lại, không chia đôi.

    Đúng phép gộp mà `split_voices` dùng (`fold_dropped_marks`): nó gộp cách viết **rơi dấu**,
    không gộp khác hoa-thường — `Trang`/`TRANG` là hai khoá khác nhau ở cả hai chỗ, và bài này
    cố ý không đòi điều đó.
    """
    rows = [
        ("003", "Hạ Phong", ALPHABET_FIRST, 4),
        ("004", "Ha Phong", ALPHABET_FIRST, 5),
        ("060", "Hạ Phong", MORE_LINES, 2),
    ]

    totals = lines_by_name_voice(rows)

    assert len(totals) == 1, totals
    only = next(iter(totals.values()))
    assert only[ALPHABET_FIRST] == 9
    assert only[MORE_LINES] == 2
