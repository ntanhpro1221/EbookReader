"""Test cho phep dem theo chu DOC."""
import io
import sys
from pathlib import Path

root = Path(sys.argv[1])
p = root / "tests" / "test_audio_assembly.py"
s = io.open(p, encoding="utf-8").read()

TEST = '''

def test_spoken_speakable_chars_counts_a_number_as_it_is_said() -> None:
    """The bug that killed chapter 023's title, and with it the chapter.

    VieNeu reads 22 as "hai mươi hai" - two written characters, eleven spoken. The pace gate
    counted the written string against a floor calibrated on text without digits, so
    "Chương 22 - 22: Ấn tượng đầu tiên" measured 10.68 chars/s at 2.25 seconds and failed,
    eleven times running, while what a listener hears is 17.78 - comfortably inside the band.
    Eleven identical failures because it was arithmetic, not variance.
    """
    from ebook_reader.audio_io import spoken_speakable_chars

    title = "Chương 22 - 22: Ấn tượng đầu tiên"

    assert sum(char.isalnum() for char in title) == 24
    assert spoken_speakable_chars(title) == 40
    assert spoken_speakable_chars(title) / 2.25 > 12.5


def test_text_without_digits_is_counted_exactly_as_before() -> None:
    """The change must be invisible to every segment that has no number in it."""
    from ebook_reader.audio_io import spoken_speakable_chars

    for text in (
        "Không có chữ số nào ở đây cả.",
        '"Tiếp theo."',
        "Anh ta bước qua hành lang rất dài và dừng lại trước cánh cửa bằng đồng.",
    ):
        assert spoken_speakable_chars(text) == sum(char.isalnum() for char in text)


def test_a_number_too_large_to_spell_is_left_alone_rather_than_guessed() -> None:
    """vietnamese_number_words stops at 999 and raises above it.

    Those stay counted as written, so they are still undercounted - a known and deliberate
    gap. Inventing a multiplier for them would be guessing, and guessing is what produced
    this bug in the first place.
    """
    from ebook_reader.audio_io import spoken_speakable_chars

    text = "Chương 1000 - 1000: xa quá"

    assert spoken_speakable_chars(text) == sum(char.isalnum() for char in text)
'''

s = s.rstrip() + "\n" + TEST
io.open(p, "w", encoding="utf-8").write(s)
print(f"da va {p}")
