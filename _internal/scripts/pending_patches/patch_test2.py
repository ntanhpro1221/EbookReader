"""Viet lai test bi hong escape, dung ngoac thang nhu chuong 019 that."""
import io
import sys
from pathlib import Path

root = Path(sys.argv[1])
p = root / "tests" / "test_text_processing_safety.py"
s = io.open(p, encoding="utf-8").read()

start = s.index("def test_recovery_closes_the_offending_paragraph_not_the_innocent_one")
end = s.index("def test_recovery_terminates_on_a_chapter_of_nothing_but_open_quotes")

new = '''def test_recovery_closes_the_offending_paragraph_not_the_innocent_one() -> None:
    """Chapter 019's real shape, with the straight quotes it really uses.

    The oath opens in one paragraph and closes two later - legitimate, and only possible
    because the quote state crosses paragraphs. The real fault is a later paragraph ending
    with a mark it never opened. With straight quotes the opener and the closer are the same
    character, so that stray mark reads as an opening and hangs to the end of the chapter.
    That is the whole class of defect.

    A recovery that blamed the first odd paragraph would break the oath and leave the real
    fault in place - exactly what two earlier versions of check_sources.py did.
    """
    text = "\\n\\n".join(
        [
            '"Món nợ của Theosbane luôn được trả,',
            'Danh dự của Kallith còn quý hơn cả vàng."',
            "Trước khi hai người kia kịp phản hồi, gã nhóc lên tiếng.",
            'Đúng là vậy, nhưng tiền nong có hơi eo hẹp."',
            "À, đương nhiên rồi nhỉ.",
        ]
    )
    warnings: list[str] = []

    rows = segment_chapter_text(19, text, warnings=warnings)

    assert len(warnings) == 1, warnings
    assert "paragraph 4" in warnings[0], warnings[0]
    # lời thề vẫn là lời thoại trải hai đoạn, recovery không đụng vào
    assert rows[0]["kind_hint"] == "dialogue"
    assert str(rows[0]["text"]).startswith('"Món nợ')


'''

io.open(p, "w", encoding="utf-8").write(s[:start] + new + s[end:])
print("ok")
