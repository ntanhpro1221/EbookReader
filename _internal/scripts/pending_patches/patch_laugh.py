"""Va text_processing.py: 'Ahaha' cung la tieng cuoi."""
import io
import sys
from pathlib import Path

root = Path(sys.argv[1])
p = root / "ebook_reader" / "text_processing.py"
s = io.open(p, encoding="utf-8").read()

OLD_PATTERN = '''COMPACT_VOCALIZATION_PATTERN = re.compile(
    r"(?<!\\w)(?P<syllable>ha|he|hi|hu)(?P=syllable){1,7}(?!\\w)",
    re.IGNORECASE,
)'''

NEW_PATTERN = '''COMPACT_VOCALIZATION_PATTERN = re.compile(
    r"(?<!\\w)(?P<syllable>ha|he|hi|hu)(?P=syllable){1,7}(?!\\w)",
    re.IGNORECASE,
)
# The same laugh with a vowel in front of it: "Ahaha", "Ohoho", "Ehehe". Recognising these
# is only safe for the *predicate*, never for the rewriter above, which counts repetitions
# by dividing the match length by the syllable length - a leading vowel would make it count
# one repetition too many and stretch the laugh.
#
# Why it matters: `"...Ha! Ahaha! Á á! Haha!"` is laughter in every token but "Ahaha", and
# one unrecognised token is enough for is_vocalization_only to say no. ASR then judged
# laughter as if it were words, could not match it, exhausted five repair rounds and blocked
# chapter 013 of alpha.55 - a chapter that was otherwise finished.
LEADING_VOWEL_LAUGH_PATTERN = re.compile(
    r"^(?P<lead>[aeou])(?P<syllable>ha|he|hi|hu)(?P=syllable){0,7}$",
    re.IGNORECASE,
)'''

assert OLD_PATTERN in s, "khong khop COMPACT_VOCALIZATION_PATTERN"
s = s.replace(OLD_PATTERN, NEW_PATTERN)

OLD_TOKEN = '''    folded = _fold_vocalization_token(token)
    return (
        FOLDED_VOCALIZATION_PATTERN.fullmatch(folded) is not None
        or COMPACT_VOCALIZATION_PATTERN.fullmatch(folded) is not None
        or STRETCHED_SOUND_TOKEN_PATTERN.search(token) is not None
    )'''

NEW_TOKEN = '''    folded = _fold_vocalization_token(token)
    return (
        FOLDED_VOCALIZATION_PATTERN.fullmatch(folded) is not None
        or COMPACT_VOCALIZATION_PATTERN.fullmatch(folded) is not None
        or LEADING_VOWEL_LAUGH_PATTERN.fullmatch(folded) is not None
        or STRETCHED_SOUND_TOKEN_PATTERN.search(token) is not None
    )'''

assert OLD_TOKEN in s, "khong khop _is_vocalization_token"
s = s.replace(OLD_TOKEN, NEW_TOKEN)

io.open(p, "w", encoding="utf-8").write(s)
print(f"da va {p}")
