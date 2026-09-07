"""Va test dem: co cho thu ba ton trong luat 'qua ngan thi khong phan xu duoc'."""
import io
import sys
from pathlib import Path

root = Path(sys.argv[1])
p = root / "tests" / "test_asr_unverifiable_short_text.py"
s = io.open(p, encoding="utf-8").read()

OLD = '''def test_both_asr_failure_paths_know_the_rule() -> None:
    """The first-pass gate and the repair-exhaustion branch are separate code."""
    source = inspect.getsource(BookPipeline._verify_chapter_audio)
    assert source.count("asr_verdict_is_unverifiable") == 2, (
        "a segment ASR cannot judge must be forgiven wherever it is judged"
    )
'''

NEW = '''def test_every_asr_failure_path_knows_the_rule() -> None:
    """The first-pass gate, the repair-exhaustion branch, and the anchor are separate code.

    An exact count rather than a floor, on purpose: it makes anyone adding a fourth site say
    why, here, in the same commit. The third was added when a segment that is nothing but a
    short name turned out to be able to reach neither of the first two.

    asr_only_failure excluded ASR_LOCKED_NAME_ANCHOR_MISMATCH unconditionally, which shut the
    "too short for any verdict" door; the other door, locked_name_review, wants ordinary
    content that passed its canonical thresholds, and a segment that is only a name has none.
    So `"Juli!"` - 0.56 seconds, four letters - reached neither and blocked its chapter for
    good. The anchor is now excluded unless the reference is below ASR_MIN_VERIFIABLE_CHARS,
    which is the same rule the other two sites already apply.
    """
    source = inspect.getsource(BookPipeline._verify_chapter_audio)
    assert source.count("asr_verdict_is_unverifiable") == 3, (
        "a segment ASR cannot judge must be forgiven wherever it is judged"
    )


def test_a_long_anchor_mismatch_is_still_not_forgiven() -> None:
    """The narrowing must not reach the case where the anchor can actually see.

    The 20-second skill list of chapter 011 really is misread, and it carries far more than
    ASR_MIN_VERIFIABLE_CHARS, so it must keep blocking. If this ever passes, the anchor has
    been softened where it works rather than where it is blind.
    """
    misread_list = "Hỏa Cầu (Fireball) (Thường) || Sương Giáng (Mistfall) (Thường)"

    assert not asr_verdict_is_unverifiable(misread_list)
'''

assert OLD in s, "khong khop test dem"
s = s.replace(OLD, NEW, 1)
io.open(p, "w", encoding="utf-8").write(s)
print(f"da va {p}")
