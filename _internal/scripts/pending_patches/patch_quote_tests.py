"""Thay test khang dinh hanh vi cu bang cac test cua hanh vi phuc hoi."""
import io
import sys
from pathlib import Path

root = Path(sys.argv[1])
p = root / "tests" / "test_text_processing_safety.py"
s = io.open(p, encoding="utf-8").read()

OLD = '''def test_unclosed_quote_state_fails_closed_at_chapter_boundary() -> None:
    with pytest.raises(RuntimeError, match="Unclosed dialogue quote at the end of chapter 7"):
        segment_chapter_text(7, "“Câu thoại chưa được đóng.\\n\\nVẫn còn trong lời thoại.")
'''

NEW = '''def test_unclosed_quote_is_recovered_instead_of_refusing_the_chapter() -> None:
    """A missing quote mark used to refuse the chapter, which stops a whole book on a typo.

    Eight of this book's 478 chapters trip it, in a source nobody here wrote. The chapter has
    to come out; being cast slightly wrong is a smaller loss than not existing.
    """
    warnings: list[str] = []

    rows = segment_chapter_text(
        7,
        "“Câu thoại chưa được đóng.\\n\\nVẫn còn trong lời thoại.",
        warnings=warnings,
    )

    assert rows, "chương phải chia ra được, không được từ chối"
    assert warnings and "chapter 7" in warnings[0].lower()


def test_recovery_never_drops_a_spoken_word() -> None:
    """The point of the whole exercise: recover the casting, never the words.

    segment_chapter_text already proves this for itself on every chapter through its token
    check; this pins the promise so nobody relaxes that check later.
    """
    text = (
        "“Mở ra mà không đóng lại.\\n\\n"
        "Một đoạn kể bình thường ở giữa.\\n\\n"
        "“Một câu thoại khác, đóng đàng hoàng.”\\n\\n"
        "Đoạn kể cuối cùng."
    )

    rows = segment_chapter_text(3, text)
    spoken = " ".join(str(row["text"]) for row in rows)

    for word in ("Mở", "đóng", "bình", "thường", "đàng", "hoàng", "cuối", "cùng"):
        assert word in spoken


def test_a_quote_spanning_paragraphs_still_closes_where_it_should() -> None:
    """Recovery must not punish the legitimate case that made the state cross-paragraph.

    Chapter 019 of this book carries a six-line oath: one opening mark, five paragraphs, then
    the closing mark. That is not a defect and must keep its single dialogue reading.
    """
    text = (
        "“Món nợ của Theosbane luôn được trả,\\n\\n"
        "Lời hứa của Zynx không bao giờ lung lay,\\n\\n"
        "Danh dự của Kallith còn quý hơn cả vàng.”\\n\\n"
        "Tôi liếc xuống nhìn cậu ta."
    )
    warnings: list[str] = []

    rows = segment_chapter_text(19, text, warnings=warnings)

    assert warnings == [], "lời thề đóng đúng chỗ, không được coi là hỏng"
    assert [row["kind_hint"] for row in rows][-1] == "narration"
    assert rows[0]["kind_hint"] == "dialogue"


def test_recovery_closes_the_offending_paragraph_not_the_innocent_one() -> None:
    """The oath opens first and closes correctly; the fault is a later paragraph.

    This is chapter 019's real shape. A recovery that blamed the first odd paragraph would
    break the oath and leave the real fault in place - which is exactly what two earlier
    versions of check_sources.py did.
    """
    text = (
        "“Món nợ của Theosbane luôn được trả,\\n\\n"
        "Danh dự của Kallith còn quý hơn cả vàng.”\\n\\n"
        "Trước khi hai người kia kịp phản hồi, gã nhóc lên tiếng.\\n\\n"
        "Đúng là vậy, nhưng tiền nong có hơi eo hẹp.”\\n\\n"
        "À, đương nhiên rồi nhỉ."
    )
    warnings: list[str] = []

    rows = segment_chapter_text(19, text, warnings=warnings)

    assert len(warnings) == 1
    assert "paragraph 4" in warnings[0], warnings[0]
    assert rows[0]["kind_hint"] == "dialogue"


def test_recovery_terminates_on_a_chapter_of_nothing_but_open_quotes() -> None:
    """The lever is applied one paragraph at a time, so it has to be proved to terminate."""
    text = "\\n\\n".join(f"“Đoạn thứ {index} không bao giờ đóng." for index in range(12))
    warnings: list[str] = []

    rows = segment_chapter_text(4, text, warnings=warnings)

    assert rows
    assert len(warnings) == 1
'''

assert OLD in s, "khong tim thay test cu"
s = s.replace(OLD, NEW)
io.open(p, "w", encoding="utf-8").write(s)
print(f"da va {p}")
