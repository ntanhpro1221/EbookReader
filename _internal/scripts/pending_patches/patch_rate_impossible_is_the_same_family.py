r"""Va asr.py + pipeline.py: ASR_TRANSCRIPT_RATE_IMPOSSIBLE la em ruot cua TIMELINE_IMPOSSIBLE.

CHUA AP luc viet - lo 2 dang chay 4 chuong cuoi. Ap o ranh gioi lo, TRUOC lo va cho lo 2.

Lo 2 mat hai chuong (031, 043) vi ma nay, va ca hai doan la TIENG CUOI:

    '"Ahaha! Hahahaha! Ahahahaha!"'   -> Whisper: 'huff huff huff huff ...' x15
    '"Aaahahahaha! Hahahahaha!"'      -> Whisper: 'ah ah ah ah ah ...'      x26

Xem docs/WHAT_BLOCKS_A_CHAPTER.md.
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

# ================================================================= asr.py
p = root / "ebook_reader" / "asr.py"
s = io.open(p, encoding="utf-8").read()

OLD = '''# Whisper's own timestamps ran past the end of the file, which it can only do by
# wandering off the audio. Was a bare string in three places.
ASR_TRANSCRIPT_TIMELINE_IMPOSSIBLE = "ASR_TRANSCRIPT_TIMELINE_IMPOSSIBLE"'''
NEW = '''# Whisper's own timestamps ran past the end of the file, which it can only do by
# wandering off the audio. Was a bare string in three places.
ASR_TRANSCRIPT_TIMELINE_IMPOSSIBLE = "ASR_TRANSCRIPT_TIMELINE_IMPOSSIBLE"
# And the same conclusion from different evidence: the transcript holds more words than the
# duration can physically contain. `_evaluate_transcript_core` returns the two side by side
# with an identical shape - `ASR_INCONCLUSIVE`, `repairable: False`, `severe: False` - so they
# are one family, and the comment above says what happened to the other one: it was promoted
# out of being a bare string and into the non-blocking lists. This one was left behind in that
# cleanup, still a bare string in one place, still in neither list.
#
# Batch 2 charged two chapters for it, and both segments were **laughter**:
#
#   '"Ahaha! Hahahaha! Ahahahaha!"'  ->  'huff huff huff huff ...'  fifteen times
#   '"Aaahahahaha! Hahahahaha!"'     ->  'ah ah ah ah ah ...'       twenty-six times
#
# Whisper loops on non-lexical vocalisation, and a loop is longer than the audio - so the
# check fires **correctly** and says something true about the transcript. It says nothing at
# all about the take.
ASR_TRANSCRIPT_RATE_IMPOSSIBLE = "ASR_TRANSCRIPT_RATE_IMPOSSIBLE"'''
assert OLD in s, "khong khop hang so"
s = s.replace(OLD, NEW, 1)

OLD = '''    "Mẹ kiếp! A a a! Khốn nạn!" came back as "Cảm ơn các bạn đã theo dõi và hẹn gặp lại"
    twice, from two separately generated takes with different seeds. Whisper is deterministic
    about it, so another repair round cannot rescue a verdict that was never available.
    """
    return str(reason).strip() == ASR_TRANSCRIPT_TIMELINE_IMPOSSIBLE'''
NEW = '''    "Mẹ kiếp! A a a! Khốn nạn!" came back as "Cảm ơn các bạn đã theo dõi và hẹn gặp lại"
    twice, from two separately generated takes with different seeds. Whisper is deterministic
    about it, so another repair round cannot rescue a verdict that was never available.

    The rate check establishes the same thing from the other direction: the transcript holds
    more words than the duration can hold, which the decoder can only produce by looping.
    Batch 2 lost chapters 031 and 043 to it on two laughter lines. This function's own second
    paragraph already argued for exactly this - "the same unanswerable question, established
    by different evidence, and it deserves the same treatment" - it just said it about the
    short-reference case and not about this one.
    """
    return str(reason).strip() in {
        ASR_TRANSCRIPT_TIMELINE_IMPOSSIBLE,
        ASR_TRANSCRIPT_RATE_IMPOSSIBLE,
    }'''
assert OLD in s, "khong khop predicate"
s = s.replace(OLD, NEW, 1)

OLD = '''                "reason": "ASR_TRANSCRIPT_RATE_IMPOSSIBLE",'''
NEW = '''                "reason": ASR_TRANSCRIPT_RATE_IMPOSSIBLE,'''
assert OLD in s, "khong khop cho tra reason"
s = s.replace(OLD, NEW, 1)
write_atomic(p, s)
print("da va", p)

# ================================================================= pipeline.py
p = root / "ebook_reader" / "pipeline.py"
s = io.open(p, encoding="utf-8").read()

OLD = """    ASR_TRANSCRIPT_TIMELINE_IMPOSSIBLE,
    ASR_UNVERIFIABLE_SHORT_TEXT,"""
NEW = """    ASR_TRANSCRIPT_RATE_IMPOSSIBLE,
    ASR_TRANSCRIPT_TIMELINE_IMPOSSIBLE,
    ASR_UNVERIFIABLE_SHORT_TEXT,"""
assert OLD in s, "khong khop import"
s = s.replace(OLD, NEW, 1)

OLD = """        # lại" from two separately generated takes. That is evidence about Whisper, not
        # about the reading.
        ASR_TRANSCRIPT_TIMELINE_IMPOSSIBLE,
    }
)"""
NEW = """        # lại" from two separately generated takes. That is evidence about Whisper, not
        # about the reading.
        ASR_TRANSCRIPT_TIMELINE_IMPOSSIBLE,
        # And a fourth, which is the third one's sibling rather than a new idea: the
        # transcript holds more words than the duration can contain. Batch 2 charged two
        # chapters for it and both segments were laughter - Whisper loops on non-lexical
        # vocalisation, and a loop is longer than the audio. Same verdict
        # (`ASR_INCONCLUSIVE`), same `repairable: False`, same `severe: False`; it was simply
        # left out when the timeline code was promoted from a bare string into this list.
        ASR_TRANSCRIPT_RATE_IMPOSSIBLE,
    }
)"""
assert OLD in s, "khong khop ALLOWED"
s = s.replace(OLD, NEW, 1)

OLD = """        ASR_UNVERIFIABLE_SHORT_TEXT,
        ASR_TRANSCRIPT_TIMELINE_IMPOSSIBLE,
        PACE_BAND_RELAXED_WARNING,
    }
)"""
NEW = """        ASR_UNVERIFIABLE_SHORT_TEXT,
        ASR_TRANSCRIPT_TIMELINE_IMPOSSIBLE,
        ASR_TRANSCRIPT_RATE_IMPOSSIBLE,
        PACE_BAND_RELAXED_WARNING,
    }
)"""
assert OLD in s, "khong khop MACHINE"
s = s.replace(OLD, NEW, 1)

# --------------------------------------------------------- ghi dung bang chung, khong ghi nham
OLD = '''                        # Whisper's own timestamps ran past the end of the file, so its
                        # answer is not about this audio and carries no verdict either way.
                        # Another repair round cannot help: the same transcript came back
                        # from two separately generated takes with different seeds.
                        warning = ASR_TRANSCRIPT_TIMELINE_IMPOSSIBLE'''
NEW = '''                        # Whisper's answer is not about this audio and carries no verdict
                        # either way - either its own timestamps ran past the end of the
                        # file, or the transcript holds more words than the duration can.
                        # Another repair round cannot help: the same transcript came back
                        # from two separately generated takes with different seeds.
                        #
                        # Label it with **the reason that actually fired**, not with one of
                        # the two hardcoded. `_evaluate_transcript_core` puts the code itself
                        # in `reason`, so this stays correct when a third member joins the
                        # family - and a report that blamed the timestamps for a rate failure
                        # would send the next reader to the wrong check.
                        warning = str(reason).strip()'''
assert OLD in s, "khong khop nhan 5528"
s = s.replace(OLD, NEW, 1)

OLD = """                unanswerable_warning = (
                    ASR_TRANSCRIPT_TIMELINE_IMPOSSIBLE
                    if asr_answer_is_about_other_audio(str(reason))
                    else ASR_UNVERIFIABLE_SHORT_TEXT
                )"""
NEW = """                # Cùng lý do như chỗ trên: mã thật nằm trong `reason`, nên đừng cứng hoá
                # một trong hai. Nhánh còn lại vẫn phải là hằng số, vì ở đó `reason` nói về
                # một chuyện khác - văn bản quá ngắn để Whisper phán xử, không phải phiên bản
                # bất khả.
                unanswerable_warning = (
                    str(reason).strip()
                    if asr_answer_is_about_other_audio(str(reason))
                    else ASR_UNVERIFIABLE_SHORT_TEXT
                )"""
assert OLD in s, "khong khop nhan 5832"
s = s.replace(OLD, NEW, 1)
write_atomic(p, s)
print("da va", p)

TEST = '''"""`ASR_TRANSCRIPT_RATE_IMPOSSIBLE` phải được xử y như em ruột của nó.

Lô 2 mất hai chương (031, 043) vì mã này, và **cả hai đoạn là tiếng cười**:

```
'"Ahaha! Hahahaha! Ahahahaha!"'  ->  Whisper: 'huff huff huff huff ...'  x15
'"Aaahahahaha! Hahahahaha!"'     ->  Whisper: 'ah ah ah ah ah ...'       x26
```

Whisper lặp vòng trên tiếng phi-từ-vựng, và một vòng lặp thì dài hơn audio — nên phép kiểm nổ
**đúng** và nói một điều thật về *phiên bản*. Nó không nói gì về *bản thu*.

`_evaluate_transcript_core` trả hai mã cạnh nhau với hình dạng y hệt (`ASR_INCONCLUSIVE`,
`repairable: False`, `severe: False`). Cái kia được nâng từ chuỗi trần thành hằng số và đưa vào
danh sách không-chặn; cái này bị bỏ sót trong đúng lần dọn ấy.
"""
from __future__ import annotations

from ebook_reader.asr import (
    ASR_TRANSCRIPT_RATE_IMPOSSIBLE,
    ASR_TRANSCRIPT_TIMELINE_IMPOSSIBLE,
    asr_answer_is_about_other_audio,
    transcript_exceeds_physical_rate,
)
from ebook_reader.pipeline import (
    HIGH_QUALITY_ALLOWED_SEGMENT_WARNINGS,
    MACHINE_ACCEPTABLE_SEGMENT_WARNINGS,
)


def test_a_looping_transcript_is_not_about_the_audio() -> None:
    assert asr_answer_is_about_other_audio(ASR_TRANSCRIPT_RATE_IMPOSSIBLE)
    assert asr_answer_is_about_other_audio(ASR_TRANSCRIPT_TIMELINE_IMPOSSIBLE)


def test_it_does_not_block_a_chapter() -> None:
    """Cả hai danh sách, y như em ruột — khác đi là một quyết định mới cần lý do riêng."""
    assert ASR_TRANSCRIPT_RATE_IMPOSSIBLE in HIGH_QUALITY_ALLOWED_SEGMENT_WARNINGS
    assert ASR_TRANSCRIPT_RATE_IMPOSSIBLE in MACHINE_ACCEPTABLE_SEGMENT_WARNINGS


def test_the_two_codes_are_treated_identically_everywhere() -> None:
    """Nếu về sau ai tách chúng ra thì phải tách có chủ ý, không phải vì bỏ sót."""
    for collection in (HIGH_QUALITY_ALLOWED_SEGMENT_WARNINGS, MACHINE_ACCEPTABLE_SEGMENT_WARNINGS):
        assert (ASR_TRANSCRIPT_RATE_IMPOSSIBLE in collection) == (
            ASR_TRANSCRIPT_TIMELINE_IMPOSSIBLE in collection
        )


def test_batch_2_laughter_really_does_trip_the_rate_check() -> None:
    """Mẫu thật, chứ không phải mẫu bịa: hai phiên bản đã làm hỏng chương 031 và 043."""
    assert transcript_exceeds_physical_rate(" ".join(["huff"] * 15), 2.32)
    assert transcript_exceeds_physical_rate(" ".join(["ah"] * 26), 2.48)


def test_an_ordinary_transcript_does_not_trip_it() -> None:
    """Phép kiểm vẫn phải nổ đúng lúc — bản vá này không nới ngưỡng của nó."""
    assert not transcript_exceeds_physical_rate("Tôi nhếch mép.", 2.0)
    assert not transcript_exceeds_physical_rate("", 2.0)
'''

q = root / "tests" / "test_rate_impossible_is_the_same_family.py"
write_atomic(q, TEST)
print("da tao", q)
