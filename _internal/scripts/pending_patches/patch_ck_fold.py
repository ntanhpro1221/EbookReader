"""Va asr.py: 'k' truoc nguyen am sau la cung mot am voi 'c' trong tieng Viet."""
import io
import sys
from pathlib import Path

root = Path(sys.argv[1])
p = root / "ebook_reader" / "asr.py"
s = io.open(p, encoding="utf-8").read()

OLD = '''    if not token:
        return ""
    cached = _PHONEME_CACHE.get(token)
    if cached is not None:
        return cached'''

NEW = '''    if not token:
        return ""
    cached = _PHONEME_CACHE.get(token)
    if cached is not None:
        return cached
    token = _fold_vietnamese_k_to_c(token)
    cached = _PHONEME_CACHE.get(token)
    if cached is not None:
        return cached'''

assert OLD in s, "khong khop dau _vietnamese_phonemes"
s = s.replace(OLD, NEW, 1)

HELPER = '''_VIETNAMESE_K_BEFORE_BACK_VOWEL = re.compile(
    r"(?<![a-zà-ỹ])k(?=[aàáảãạăằắẳẵặâầấẩẫậoòóỏõọôồốổỗộơờớởỡợuùúủũụưừứửữự])",
    re.IGNORECASE,
)


def _fold_vietnamese_k_to_c(token: str) -> str:
    """`k` before a back vowel is spelled `c` in Vietnamese, and sounds the same.

    Vietnamese writes /k/ as `k` before i, e, ê and y, and as `c` everywhere else - so `kai`
    is not a Vietnamese spelling at all. The phonemiser treats what it cannot read as
    Vietnamese as English, and the two land nowhere near each other: `cai` gives kˈaːj while
    `kai` gives kˈaɪ, `co` gives kˈɔ while `ko` gives kˈoʊ.

    That cost the book's own protagonist. `Samael Kaizer Theosbane` is locked to
    `Xa-men cai-dờ theo-bên`; Whisper wrote `Sa-men Kai dở theo bên`, which is that reading,
    correctly, in a spelling Whisper prefers. Samael and Theosbane matched on phonemes and
    Kaizer did not, so the anchor found nothing, the canonical fold could not happen, and a
    segment the content check scored 0.979 was blocked.

    Measured on the failing case: the span `caidở` matches the locked `cai-dờ` and `Kaidở`
    does not, while `caidở` matches **despite** the tone differing between `dở` and `dờ`. So
    the tone was never the problem and `k` against `c` was all of it.

    This is the same fold the phonemiser's own docstring already claims for `gi` and `d`,
    applied to a pair it missed. It stays an equality test afterwards.
    """
    return _VIETNAMESE_K_BEFORE_BACK_VOWEL.sub(
        lambda match: "C" if match.group().isupper() else "c", token
    )


'''

ANCHOR = "def _vietnamese_phonemes(token: str) -> str:"
assert ANCHOR in s, "khong khop cho chen"
s = s.replace(ANCHOR, HELPER + ANCHOR, 1)

io.open(p, "w", encoding="utf-8").write(s)
print(f"da va {p}")
