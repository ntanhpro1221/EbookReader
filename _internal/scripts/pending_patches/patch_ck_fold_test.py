"""Test cho phep gap k->c."""
import io
import sys
from pathlib import Path

root = Path(sys.argv[1])
p = root / "tests" / "test_locked_name_anchor_component_match.py"
s = io.open(p, encoding="utf-8").read()

TEST = '''

def test_k_before_a_back_vowel_sounds_like_c() -> None:
    """Vietnamese spells /k/ as `c` everywhere except before i, e, ê and y.

    So `kai` is not a Vietnamese spelling at all, and the phonemiser reads what it cannot
    take as Vietnamese as English instead: `cai` gives kˈaːj and `kai` gives kˈaɪ, `co`
    gives kˈɔ and `ko` gives kˈoʊ. Two spellings of one sound, landing nowhere near each
    other.
    """
    from ebook_reader.asr import _vietnamese_phonemes

    for vietnamese, whisper in (("cai", "kai"), ("ca", "ka"), ("co", "ko")):
        assert _vietnamese_phonemes(vietnamese) == _vietnamese_phonemes(whisper)


def test_k_before_a_front_vowel_is_left_alone() -> None:
    """`ke`, `kê`, `ki`, `ky` are correct Vietnamese and must not be rewritten."""
    from ebook_reader.asr import _fold_vietnamese_k_to_c

    for token in ("ke", "kê", "ki", "ky", "kỳ"):
        assert _fold_vietnamese_k_to_c(token) == token


def test_the_protagonists_name_survives_whispers_spelling() -> None:
    """The case that found this, and it cost a chapter.

    "Samael Kaizer Theosbane" is locked to "Xa-men cai-dờ theo-bên". Whisper wrote "Sa-men
    Kai dở theo bên" - that reading, correctly, in the spelling Whisper prefers. Samael and
    Theosbane matched on phonemes; Kaizer did not, so no anchor matched, the canonical fold
    could not happen, and a segment the content check scored 0.979 was blocked.

    The tone was never the problem: `caidở` matched the locked `cai-dờ` before this fix,
    despite dở and dờ carrying different tones. `k` against `c` was all of it.
    """
    from ebook_reader.asr import (
        _anchor_component_sounds_right,
        _locked_name_anchor_components,
    )

    anchor = {
        "surface": "Samael Kaizer Theosbane",
        "spoken_form": "Xa-men cai-dờ theo-bên",
    }
    heard = ["Sa-men", "Kai", "dở", "theo", "bên"]

    components = _locked_name_anchor_components(anchor)
    assert [source for source, _syllables in components] == [
        "Samael",
        "Kaizer",
        "Theosbane",
    ]

    matched = []
    for source, syllables in components:
        spans = (
            "".join(heard[index : index + width])
            for width in (1, 2, 3)
            for index in range(len(heard) - width + 1)
        )
        matched.append(
            any(_anchor_component_sounds_right(syllables, source, span) for span in spans)
        )

    assert matched == [True, True, True]


def test_the_fold_does_not_merge_two_different_names() -> None:
    """It stays an equality test on sound, and Lucien still does not swallow Lusienne."""
    from ebook_reader.asr import _anchor_component_sounds_right

    syllables = ["Lu", "xi", "en"]

    assert _anchor_component_sounds_right(syllables, "Lucien", "lucien")
    assert not _anchor_component_sounds_right(syllables, "Lucien", "lusienne")
'''

s = s.rstrip() + "\n" + TEST
io.open(p, "w", encoding="utf-8").write(s)
print(f"da va {p}")
