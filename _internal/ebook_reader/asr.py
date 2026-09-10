from __future__ import annotations

import gc
import math
import re
import unicodedata
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Callable

import numpy as np

from .io_utils import strip_lone_surrogates
import soundfile as sf
from scipy.signal import resample_poly

from .asr_contract import (
    ASR_MIN_VERIFIABLE_CHARS,
    ASR_LOCKED_NAME_ANCHOR_REVIEW,
    COLLAPSED_SHORT_CONTEXT_EFFECTIVE_REPEAT_COUNT,
    LOCKED_NAME_ANCHOR_METRICS_VERSION,
    SHORT_CONTEXT_REPEAT_COUNT,
)
from .resource_manager import trim_process_working_set
from .text_processing import is_vocalization_only, vietnamese_number_words


ASR_REPAIR_MIN_WORDS = 1
SEVERE_MISMATCH_MAX_SIMILARITY = 0.35
SEVERE_MISMATCH_MIN_LENGTH_RATIO = 3.0
SEVERE_MISMATCH_MIN_EXTRA_WORDS = 4
WHISPER_SAMPLE_RATE = 16_000
MAX_PLAUSIBLE_TRANSCRIPT_WORDS_PER_SECOND = 5.0
TRANSCRIPT_WORD_MARGIN = 2
MIN_PLAUSIBLE_TRANSCRIPT_WORDS = 4
WHISPER_TIMELINE_ABSOLUTE_MARGIN_SECONDS = 1.0
WHISPER_TIMELINE_DURATION_FACTOR = 2.0
SHORT_CONTEXT_MAX_WORDS = 5
SHORT_CONTEXT_GAP_SECONDS = 0.50
# Where beam search stops helping and starts inventing. Measured, not chosen: see
# WhisperVerifier._beam_minimum_seconds.
BEAM_MINIMUM_SECONDS = 2.5

ASR_PASS = "pass"
ASR_MISMATCH = "mismatch"
ASR_INCONCLUSIVE = "inconclusive"

# Below this much reference text, Whisper cannot be asked the question at all.
#
# Measured over 4528 committed segments, by speakable characters in the reference:
#
#     chars    median similarity    below 0.5    transcript >3x too long
#      0-3            0.273            75.0%              30.0%
#      3-6            0.697            44.2%              32.7%
#     6-10            0.826            13.9%              15.6%
#    10-16            0.867             3.8%               2.4%
#    24-40            0.943             0.2%               0.0%
#      80+            0.974             0.3%               0.0%
#
# The cliff is at ten characters and it is steep. The same engine produced every one of
# those segments, so a 75% failure rate at three characters against 0.2% at thirty is the
# verifier failing, not the reading: there is not enough audio to transcribe, and Whisper
# fills the gap from its training data - a rank label "SSS" came back as a request to
# subscribe to a YouTube channel.
#
# This does not excuse the audio. It marks the ASR verdict as evidence nobody can collect,
# so it cannot block a chapter; every other check still applies.
# `ASR_MIN_VERIFIABLE_CHARS` đã chuyển sang `asr_contract` để `database` dùng được cùng một
# con số; phép đo đứng sau nó ghi ở đó. Tên vẫn xuất ra từ module này để mọi chỗ gọi cũ không
# phải đổi.
ASR_UNVERIFIABLE_SHORT_TEXT = "ASR_UNVERIFIABLE_SHORT_TEXT"
# Whisper's own timestamps ran past the end of the file, which it can only do by
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
ASR_TRANSCRIPT_RATE_IMPOSSIBLE = "ASR_TRANSCRIPT_RATE_IMPOSSIBLE"


def asr_verdict_is_unverifiable(text: str) -> bool:
    """Whether this reference is too short for an ASR verdict to mean anything."""
    return sum(char.isalnum() for char in str(text)) < ASR_MIN_VERIFIABLE_CHARS


def asr_answer_is_about_other_audio(reason: str) -> bool:
    """Whether Whisper has told us its answer is not about the audio it was given.

    The timeline check catches this: the transcript's own timestamps run past the end of the
    file, which can only happen when the decoder has wandered off the audio into something
    it was trained on. It is the same unanswerable question as a reference too short to
    transcribe, established by different evidence, and it deserves the same treatment -
    a listen rather than a failed chapter.

    "Mẹ kiếp! A a a! Khốn nạn!" came back as "Cảm ơn các bạn đã theo dõi và hẹn gặp lại"
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
    }
ASR_LOCKED_NAME_ANCHOR_MISMATCH = "ASR_LOCKED_NAME_ANCHOR_MISMATCH"
ASR_LOCKED_NAME_CANONICAL_PASS = "ASR_LOCKED_NAME_CANONICAL_PASS"
LOCKED_NAME_ANCHOR_METRICS_KEY = "locked_name_anchor_metrics"
ASR_WER_SIMILARITY_MARGIN = 0.12
ANCHOR_COMPARISON_NORMALIZED_EXACT = "normalized_exact"
ANCHOR_COMPARISON_DIACRITIC_FOLDED_EXACT = "diacritic_folded_exact"
ANCHOR_COMPARISON_VIETNAMESE_PHONEME_EXACT = "vietnamese_phoneme_exact"
ANCHOR_COMPARISON_COMPONENT_PHONEMES = "component_phonemes"
# Every exact form above compares Whisper's *spelling* to a Vietnamese transliteration, and
# those two can never agree on a name Whisper recognises: it writes "Kaiser" where the anchor
# holds "cai-dờ", and "Arthur" where the anchor holds "A-thờ". Same sound, different letters,
# scored as a pronunciation failure.
#
# alpha.51 showed what that costs. For "Tên tôi là Samael Kaizer Theosbane." the repair loop
# produced a take Whisper read back as "Samen Kaiser theo bên" - the correct reading, twice,
# in rounds 0 and 2 - rejected both, and kept the original, which Whisper read back as "Sam
# Min Kaiser theo bên". The owner listened on 2026-09-07 and confirmed the kept take is the
# broken one.
#
# Two approaches were measured and thrown away before this one. Sentence similarity cannot
# see the defect at all: the good take scored 0.818 and the broken one 0.816, because one
# wrong syllable dissolves into the spelling distance of the whole name. Character similarity
# scoped to the name separates those two (0.800 against 0.667) but cannot be thresholded:
# "Lucian" against a locked "Lucien" scores 0.833 - higher than the take that must pass - so
# any threshold that admits the good reading also admits a different name. The existing
# anchor tests pin that, and they were right to.
#
# So compare sounds, not letters, and do it per name component. "xa" and "sa" are the same
# phoneme in Vietnamese while "men" and "min" are not, which is exactly the distinction the
# ear made. No threshold is involved: the phoneme sequences match or they do not.
# Canonicalising an unmatched anchor removes it from the sentence metrics so the same
# disagreement is not punished twice. That is only sound while enough ordinary content
# remains to carry an independent verdict: in "Anh Lucy" the name is half the utterance,
# so waiving it would leave nothing to check. Below this many ordinary expected tokens
# the anchor keeps its hard-fail authority.
# Waiving an unmatched name is only sound while the rest of the utterance can carry a
# verdict on its own. An absolute token count got that wrong in both directions, so the
# rule is proportional: the name may not be the majority of what is being checked, and
# something has to be left. "Giô-en cười trừ" keeps two ordinary words against a two-token
# name and stays checkable; "Anh Lu-si-en" keeps one against three and does not.
CANONICAL_ANCHOR_WAIVER_MIN_ORDINARY_TOKENS = 2
_PHONEME_CACHE: dict[str, str] = {}
_PHONEMIZER: list[Any] = []


_VIETNAMESE_K_BEFORE_BACK_VOWEL = re.compile(
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


def _vietnamese_phonemes(token: str) -> str:
    """Deterministic phonemes for one token, or "" when phonemisation is unavailable.

    Vietnamese orthography spells the same sound more than one way - `gi` and `d` are
    both /z/, so a correct "Giôn" and Whisper's "dôn" are the same utterance. Comparing
    phonemes recognises exactly those spellings and nothing looser: this stays an
    equality test, so "Lucy" still cannot satisfy an anchor locked to "Lucien".
    """
    if not token:
        return ""
    cached = _PHONEME_CACHE.get(token)
    if cached is not None:
        return cached
    token = _fold_vietnamese_k_to_c(token)
    cached = _PHONEME_CACHE.get(token)
    if cached is not None:
        return cached
    if not _PHONEMIZER:
        try:
            from sea_g2p import G2P

            _PHONEMIZER.append(G2P(lang="vi"))
        except Exception:  # noqa: BLE001
            _PHONEMIZER.append(None)
    engine = _PHONEMIZER[0]
    if engine is None:
        return ""
    try:
        phonemes = str(engine.convert(token)).strip()
    except Exception:  # noqa: BLE001
        phonemes = ""
    _PHONEME_CACHE[token] = phonemes
    return phonemes


# Whisper writes a number as a digit; the book writes it as a word. "thứ mười" against
# "thứ 10" is one reading spelled two ways, and comparing them as text costs similarity for
# nothing: 111 of 6019 transcribed segments carry a number word matched by the same digit
# in the transcript, every one scored below 0.95.
#
# The direction decides whether this helps or hurts, and only measurement said which.
# Folding words to digits improved 371 segments and damaged 1976: Vietnamese number words
# are ordinary words with other meanings - "năm" is also a year, "ba" also a father - so
# replacing them with a digit destroys the partial character overlap the metric lives on.
# "Ai đó?!" heard as "Hai đỏ." fell from 0.833 to 0.500 that way.
#
# Folding digits to words improved 318 and damaged 1. A digit is only ever a number, and
# only the transcript produces one, so the substitution touches one side and cannot destroy
# a partial match.
# Spelt as the book spells them, diacritics and all, so the substitution matches at this
# level and not only after a later tone fold.
DIGIT_NUMBER_WORDS = {
    "0": "không", "1": "một", "2": "hai", "3": "ba", "4": "bốn", "5": "năm",
    "6": "sáu", "7": "bảy", "8": "tám", "9": "chín", "10": "mười",
}


# Above this, a number has no settled spoken form to fold to: a year is read as its own
# kind of thing and vietnamese_number_words does not claim to cover it either.
NUMBER_FOLD_CEILING = 999


def _fold_number_digits(text: str) -> str:
    """Spell a written number the way the book would, so the two can be compared.

    This used to reach only as far as ten, from an eleven-entry table, and that gap failed
    whole chapters. alpha.32's chapter 6 was refused over one segment:

        text:  "Hôm nay là ngày 24 tháng Mười hai."
        heard: "Hôm nay là ngày 24 tháng 12."

    The voice read it exactly right. Whisper writes digits where the book writes words, and
    "mười hai" against "12" was scored as an error because the table stopped at "10". The
    same gap turned "thứ Mười" into a near miss and "bốn mươi mốt" into a full one.

    vietnamese_number_words already spells anything up to 999, including the forms a table
    gets wrong - "hai mươi mốt" rather than "hai mươi một", "mười lăm" rather than "mười
    năm" - so this defers to it instead of keeping a second, shorter answer to the same
    question.

    Only a token that is entirely digits changes, and only within range: "2026" and "3a"
    are left alone, and so is anything with a leading zero, which is a designation rather
    than a count.
    """
    folded = []
    for token in text.split():
        if token.isdigit() and (token == "0" or not token.startswith("0")):
            value = int(token)
            if value <= NUMBER_FOLD_CEILING:
                folded.append(vietnamese_number_words(value))
                continue
        folded.append(token)
    return " ".join(folded)


def normalize_transcript(text: str) -> str:
    text = text.casefold().replace("đ", "d")
    text = re.sub(r"[^0-9a-zà-ỹ\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return _fold_number_digits(text)


def _json_safe_anchor_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else str(value)
    if isinstance(value, Mapping):
        return {str(key): _json_safe_anchor_value(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_json_safe_anchor_value(item) for item in value]
    return str(value)


def _diacritic_folded_token(token: str) -> str:
    return "".join(
        character
        for character in unicodedata.normalize("NFD", token)
        if unicodedata.category(character) != "Mn"
    )


def _locked_name_anchor_forms(
    anchor: Mapping[str, Any],
) -> list[tuple[str, tuple[str, ...], str]]:
    spoken_tokens = tuple(normalize_transcript(str(anchor.get("spoken_form", ""))).split())
    surface = str(anchor.get("surface", "")).strip()
    if not surface:
        surface = str(anchor.get("normalized_surface", "")).strip()
    surface_tokens = tuple(normalize_transcript(surface).split())
    folded_spoken_tokens = tuple(
        _diacritic_folded_token(token)
        for token in spoken_tokens
    )
    phoneme_spoken_tokens = tuple(_vietnamese_phonemes(token) for token in spoken_tokens)
    if not all(phoneme_spoken_tokens):
        phoneme_spoken_tokens = ()
    candidates = [
        ("spoken_form", spoken_tokens, ANCHOR_COMPARISON_NORMALIZED_EXACT),
        ("source_spelling", surface_tokens, ANCHOR_COMPARISON_NORMALIZED_EXACT),
        (
            "joined_spoken_form",
            ("".join(spoken_tokens),) if spoken_tokens else (),
            ANCHOR_COMPARISON_NORMALIZED_EXACT,
        ),
        (
            "spoken_form",
            folded_spoken_tokens,
            ANCHOR_COMPARISON_DIACRITIC_FOLDED_EXACT,
        ),
        (
            "joined_spoken_form",
            ("".join(folded_spoken_tokens),) if folded_spoken_tokens else (),
            ANCHOR_COMPARISON_DIACRITIC_FOLDED_EXACT,
        ),
        (
            "spoken_form",
            phoneme_spoken_tokens,
            ANCHOR_COMPARISON_VIETNAMESE_PHONEME_EXACT,
        ),
    ]
    forms: list[tuple[str, tuple[str, ...], str]] = []
    seen: set[tuple[tuple[str, ...], str]] = set()
    for kind, tokens, comparison_mode in candidates:
        key = (tokens, comparison_mode)
        if not tokens or key in seen:
            continue
        forms.append((kind, tokens, comparison_mode))
        seen.add(key)
    return forms


def _locked_name_anchor_components(
    anchor: Mapping[str, Any],
) -> list[tuple[str, tuple[str, ...]]]:
    """(source component, spoken syllables) per part of the name, or [] if they do not align.

    The mapping is already in the data and needs no lookup, because a spoken form hyphenates
    within a name part and spaces between them: "Xa-men cai-dờ theo-bên" splits on whitespace
    into exactly the three parts of "Samael Kaizer Theosbane", and each of those splits on
    its hyphens into the syllables to sound out.

    When the two do not split to the same length - a spoken form written without that
    convention - this returns nothing. A wrong alignment would score real names against the
    wrong parts, which is worse than not trying: the caller keeps the exact forms it already
    had and loses none of them.
    """
    surface = str(anchor.get("surface", "")).strip() or str(
        anchor.get("normalized_surface", "")
    ).strip()
    spoken_parts = str(anchor.get("spoken_form", "")).split()
    surface_parts = surface.split()
    if surface_parts and len(surface_parts) != len(spoken_parts):
        # The convention holds for names, and breaks for terms whose *English* spelling
        # carries the hyphen: "Safe-Zone" is one whitespace part against a spoken "Xây Dôn"
        # that is two. Splitting the surface on its hyphens too lines those up. Tried only
        # after the plain split has already failed, so it can never take apart a name the
        # convention already matched - "Jean-Luc" against a spoken "Giăng-Luých" stays one
        # part and keeps working. Measured on the book's 112 seeded readings: 107 aligned
        # without this, all 112 with it, and none changed.
        hyphen_split = [
            piece
            for piece in re.split(r"[-‐-―]|\s+", surface)
            if piece.strip()
        ]
        if len(hyphen_split) == len(spoken_parts):
            surface_parts = hyphen_split
    if not surface_parts or len(surface_parts) != len(spoken_parts):
        return []
    components: list[tuple[str, tuple[str, ...]]] = []
    for source_part, spoken_part in zip(surface_parts, spoken_parts):
        syllables = tuple(
            piece for piece in re.split(r"[-‐-―]", spoken_part) if piece.strip()
        )
        if not syllables:
            return []
        components.append((source_part, syllables))
    return components


def _anchor_component_key(value: str) -> str:
    """One name part reduced to bare letters, so only the sounds are left to disagree."""
    folded = _diacritic_folded_token(normalize_transcript(str(value)))
    return "".join(character for character in folded if character.isalnum())


def _anchor_component_phonemes(parts: Sequence[str]) -> tuple[str, ...] | None:
    """Phoneme per syllable, or None when any syllable cannot be sounded out."""
    sounds = [_vietnamese_phonemes(_anchor_component_key(part)) for part in parts]
    if not sounds or not all(sounds):
        return None
    return tuple(sounds)


def _anchor_component_splits(text: str, count: int) -> list[tuple[str, ...]]:
    """Every way to cut `text` into `count` non-empty pieces.

    Whisper decides its own word boundaries and does not know the anchor's: it wrote the
    two syllables of "Xa-men" as the single token "samen". Trying the cuts is what lets a
    two-syllable component be recognised inside one written word. Names are short, so this
    stays small - and it is bounded below in case one ever is not.
    """
    if count <= 0 or len(text) < count:
        return []
    if count == 1:
        return [(text,)]
    results: list[tuple[str, ...]] = []
    for cut in range(1, len(text) - count + 2):
        head = text[:cut]
        for tail in _anchor_component_splits(text[cut:], count - 1):
            results.append((head, *tail))
            if len(results) >= _ANCHOR_COMPONENT_SPLIT_LIMIT:
                return results
    return results


_ANCHOR_COMPONENT_SPLIT_LIMIT = 512


def _anchor_component_sounds_right(
    spoken_syllables: Sequence[str],
    source_component: str,
    span: str,
) -> bool:
    """Does this stretch of transcript sound like this part of the name?

    Two ways to be right, and a name only needs one of them.

    The transliteration is the intended reading, so its syllables are sounded out and the
    span is cut every way it can be cut into that many pieces - "samen" becomes "sa"+"men"
    and matches "Xa-men" exactly, while "sam min" cannot become anything that matches.

    The source spelling is the other way, and it is what rescues the case that started all
    this: Whisper writes an English name in English, and "kaiser" and "kaizer" sound out
    identically even though no amount of letter comparison will agree on them.
    """
    if not span:
        return False
    source_key = _anchor_component_key(source_component)
    # Sound alone is not quite enough, because the phonemiser is happy to drop letters that
    # do not change a sound: "enne" and "en" come out identical, so a locked "Lucien" would
    # otherwise swallow "Lusienne" - a different character with a different name. Requiring
    # the transcript's spelling to be no longer than the longest spelling the anchor itself
    # accepts costs nothing legitimate (Whisper's "samen" and "kaiser" are both shorter than
    # the forms they match) and keeps two similar names apart.
    longest_accepted = max(
        len(source_key),
        sum(len(_anchor_component_key(part)) for part in spoken_syllables),
    )
    if len(span) > longest_accepted:
        return False
    if source_key:
        source_sound = _vietnamese_phonemes(source_key)
        span_sound = _vietnamese_phonemes(span)
        if source_sound and span_sound and source_sound == span_sound:
            return True
    expected = _anchor_component_phonemes(spoken_syllables)
    if expected is None:
        return False
    for pieces in _anchor_component_splits(span, len(expected)):
        if _anchor_component_phonemes(pieces) == expected:
            return True
    return False


def _locked_name_anchor_component_match(
    anchor: Mapping[str, Any],
    transcript_tokens: Sequence[str],
    *,
    blocked_tokens: frozenset[int] | set[int] | None = None,
    from_token: int = 0,
) -> dict[str, Any] | None:
    """Does the transcript carry every part of this name, judged by sound rather than spelling?

    Deliberately post-hoc: it runs only after exact matching has already failed, and it never
    touches the alignment or the evidence that produced that failure. The exact forms stay
    the primary path because they are cheap and unambiguous; this is the rescue for the case
    they structurally cannot handle - a name Whisper recognises and therefore spells in
    English, against an anchor holding its Vietnamese transliteration.

    Every component must be found, in order, and each one consumes the tokens it matched.
    Three properties depend on that and each is pinned by a test the first draft of this
    broke: components of one name cannot be gathered out of order from across a sentence; a
    name required three times cannot be satisfied three times by one utterance of it; and
    occurrences stay monotonic, so the second reading of a repeated line binds to the second
    span rather than back to the first. `from_token` is where the previous occurrence
    stopped, and the returned `token_end` is where the next one may start.

    All components must match. A name is wrong if any part of it is wrong, and accepting a
    majority would let a badly-read first syllable hide behind two parts that came out fine -
    precisely how the broken alpha.51 take survived the sentence metric: "Sam Min" averaged
    away against "Kaiser theo bên".
    """
    components = _locked_name_anchor_components(anchor)
    if not components:
        return None
    tokens = [_anchor_component_key(token) for token in transcript_tokens]
    if not any(tokens):
        return None
    blocked = set(blocked_tokens or ())
    cursor = max(0, int(from_token))
    found: list[bool] = []
    token_start: int | None = None
    for position, (source_component, spoken_syllables) in enumerate(components):
        matched_end: int | None = None
        # The first part of a name may sit anywhere at or after the cursor; every later part
        # has to follow the one before it immediately, because a name is spoken as one run.
        #
        # Allowing gaps is not merely loose, it is actively unsafe once the caller folds the
        # matched span out of the sentence metrics: "samen đã giết rất nhiều người kaiser
        # theo bên" matched with the middle five words inside the span, and folding that away
        # would delete a whole clause from the comparison and hide whatever the take really
        # got wrong. A permissive name check that also erases its surroundings is worse than
        # no check.
        starts = range(cursor, len(tokens)) if position == 0 else (cursor,)
        for start_index in starts:
            if start_index in blocked:
                continue
            span = ""
            for end_index in range(start_index, len(tokens)):
                if end_index in blocked:
                    break
                span += tokens[end_index]
                if _anchor_component_sounds_right(
                    spoken_syllables, source_component, span
                ):
                    matched_end = end_index + 1
                    break
                if len(span) > _ANCHOR_COMPONENT_SPAN_SLACK + max(
                    len(_anchor_component_key(source_component)),
                    sum(len(_anchor_component_key(part)) for part in spoken_syllables),
                ):
                    # Longer than any spelling this component could wear; stop growing.
                    break
            if matched_end is not None:
                if token_start is None:
                    token_start = start_index
                cursor = matched_end
                break
        found.append(matched_end is not None)
        if matched_end is None:
            break
    return {
        "components": [source for source, _syllables in components],
        "component_matched": found,
        "passed": bool(len(found) == len(components) and all(found)),
        "token_start": token_start,
        "token_end": cursor,
    }


_ANCHOR_COMPONENT_SPAN_SLACK = 3


def _locked_name_anchor_token_span(
    expected_spoken_text: str,
    expected_tokens: list[str],
    anchor: Mapping[str, Any],
) -> tuple[int, int] | str:
    spoken_start = anchor.get("spoken_start")
    spoken_end = anchor.get("spoken_end")
    if spoken_start is None or spoken_end is None:
        return "missing_spoken_span"
    if (
        isinstance(spoken_start, bool)
        or not isinstance(spoken_start, int)
        or isinstance(spoken_end, bool)
        or not isinstance(spoken_end, int)
        or spoken_start < 0
        or spoken_end <= spoken_start
        or spoken_end > len(expected_spoken_text)
    ):
        return "invalid_spoken_span"

    normalized_spoken_form = normalize_transcript(
        str(anchor.get("spoken_form", ""))
    )
    normalized_span = normalize_transcript(
        expected_spoken_text[spoken_start:spoken_end]
    )
    if not normalized_spoken_form or normalized_span != normalized_spoken_form:
        return "spoken_span_text_mismatch"

    prefix_tokens = normalize_transcript(expected_spoken_text[:spoken_start]).split()
    span_tokens = normalized_span.split()
    suffix_tokens = normalize_transcript(expected_spoken_text[spoken_end:]).split()
    if prefix_tokens + span_tokens + suffix_tokens != expected_tokens:
        return "spoken_span_token_boundary_mismatch"
    return len(prefix_tokens), len(prefix_tokens) + len(span_tokens)


def _build_locked_name_alignment_units(
    expected_spoken_text: str,
    anchors: list[dict[str, Any]],
    repeat_count: int,
) -> tuple[list[dict[str, Any]], dict[tuple[int, int], str]]:
    expected_tokens = normalize_transcript(expected_spoken_text).split()
    base_units: list[dict[str, Any]] = []
    invalid_anchor_indexes: dict[int, str] = {}
    cursor = 0
    for anchor_index, anchor in enumerate(anchors):
        token_span = _locked_name_anchor_token_span(
            expected_spoken_text,
            expected_tokens,
            anchor,
        )
        if isinstance(token_span, str):
            invalid_anchor_indexes[anchor_index] = token_span
            continue
        anchor_start, anchor_end = token_span
        if anchor_start < cursor:
            invalid_anchor_indexes[anchor_index] = "spoken_span_order_invalid"
            continue
        base_units.extend(
            {"kind": "token", "token": token}
            for token in expected_tokens[cursor:anchor_start]
        )
        base_units.append(
            {
                "kind": "anchor",
                "anchor_index": anchor_index,
                "forms": _locked_name_anchor_forms(anchor),
            }
        )
        cursor = anchor_end
    base_units.extend(
        {"kind": "token", "token": token}
        for token in expected_tokens[cursor:]
    )

    units: list[dict[str, Any]] = []
    invalid_occurrences: dict[tuple[int, int], str] = {}
    for repeat_index in range(repeat_count):
        for unit in base_units:
            repeated_unit = dict(unit)
            if repeated_unit["kind"] == "anchor":
                repeated_unit["repeat_index"] = repeat_index
            units.append(repeated_unit)
        invalid_occurrences.update(
            {
                (repeat_index, anchor_index): reason
                for anchor_index, reason in invalid_anchor_indexes.items()
            }
        )
    return units, invalid_occurrences


def _minimum_cost_locked_name_alignment(
    units: list[dict[str, Any]],
    transcript_tokens: list[str],
) -> tuple[tuple[int, int, int, int], list[dict[str, Any]]]:
    """Align semantic expected units to tokens while preserving ordinary context.

    Score fields are edit cost, negative ordinary exact matches, negative exact
    anchor matches, and structural edit count. Ordinary exact matches deliberately
    precede anchor matches in the tie-break: an accepted anchor spelling cannot
    steal a later homograph that belongs to ordinary sentence context.
    """

    score_by_state: dict[tuple[int, int], tuple[int, int, int, int]] = {
        (0, 0): (0, 0, 0, 0)
    }
    predecessor: dict[
        tuple[int, int],
        tuple[tuple[int, int], dict[str, Any]],
    ] = {}

    def update(
        state: tuple[int, int],
        next_state: tuple[int, int],
        delta: tuple[int, int, int, int],
        operation: dict[str, Any],
    ) -> None:
        current = score_by_state[state]
        candidate = tuple(left + right for left, right in zip(current, delta))
        existing = score_by_state.get(next_state)
        if existing is not None and existing <= candidate:
            return
        score_by_state[next_state] = candidate
        predecessor[next_state] = (state, operation)

    for unit_index in range(len(units) + 1):
        for transcript_index in range(len(transcript_tokens) + 1):
            state = (unit_index, transcript_index)
            if state not in score_by_state:
                continue
            if transcript_index < len(transcript_tokens):
                update(
                    state,
                    (unit_index, transcript_index + 1),
                    (1, 0, 0, 1),
                    {"kind": "insert_transcript"},
                )
            if unit_index >= len(units):
                continue

            unit = units[unit_index]
            if unit["kind"] == "token":
                update(
                    state,
                    (unit_index + 1, transcript_index),
                    (1, 0, 0, 1),
                    {"kind": "delete_token"},
                )
                if transcript_index < len(transcript_tokens):
                    exact = unit["token"] == transcript_tokens[transcript_index]
                    update(
                        state,
                        (unit_index + 1, transcript_index + 1),
                        (0, -1, 0, 0) if exact else (1, 0, 0, 0),
                        {
                            "kind": "match_token" if exact else "substitute_token",
                            "token_start": transcript_index,
                            "token_end": transcript_index + 1,
                        },
                    )
                continue

            anchor_operation = {
                "anchor_index": unit["anchor_index"],
                "repeat_index": unit["repeat_index"],
            }
            update(
                state,
                (unit_index + 1, transcript_index),
                (1, 0, 0, 1),
                {
                    **anchor_operation,
                    "kind": "delete_anchor",
                    "token_start": transcript_index,
                    "token_end": transcript_index,
                },
            )
            if transcript_index < len(transcript_tokens):
                update(
                    state,
                    (unit_index + 1, transcript_index + 1),
                    (1, 0, 0, 0),
                    {
                        **anchor_operation,
                        "kind": "substitute_anchor",
                        "token_start": transcript_index,
                        "token_end": transcript_index + 1,
                    },
                )
            for form_kind, form_tokens, comparison_mode in unit["forms"]:
                form_end = transcript_index + len(form_tokens)
                matched_tokens = tuple(transcript_tokens[transcript_index:form_end])
                if comparison_mode == ANCHOR_COMPARISON_DIACRITIC_FOLDED_EXACT:
                    comparison_tokens = tuple(
                        _diacritic_folded_token(token) for token in matched_tokens
                    )
                elif comparison_mode == ANCHOR_COMPARISON_VIETNAMESE_PHONEME_EXACT:
                    comparison_tokens = tuple(
                        _vietnamese_phonemes(token) for token in matched_tokens
                    )
                    if not all(comparison_tokens):
                        continue
                else:
                    comparison_tokens = matched_tokens
                if comparison_tokens != form_tokens:
                    continue
                update(
                    state,
                    (unit_index + 1, form_end),
                    (0, 0, -1, 0),
                    {
                        **anchor_operation,
                        "kind": "match_anchor",
                        "form_kind": form_kind,
                        "comparison_mode": comparison_mode,
                        "form_tokens": form_tokens,
                        "matched_tokens": matched_tokens,
                        "token_start": transcript_index,
                        "token_end": form_end,
                    },
                )

    final_state = (len(units), len(transcript_tokens))
    operations: list[dict[str, Any]] = []
    state = final_state
    while state != (0, 0):
        previous_state, operation = predecessor[state]
        operations.append(operation)
        state = previous_state
    operations.reverse()
    return score_by_state[final_state], operations


def _semantic_anchor_token(
    repeat_index: int,
    anchor_index: int,
    anchor_count: int,
) -> str:
    ordinal = repeat_index * anchor_count + anchor_index
    if ordinal >= 65_534:
        raise ValueError("Too many locked-name anchor occurrences")
    return chr(0xF0000 + ordinal)


def _canonical_locked_name_metrics(
    units: list[dict[str, Any]],
    operations: list[dict[str, Any]],
    transcript_tokens: list[str],
    anchor_count: int,
    rescued_spans: dict[tuple[int, int], tuple[int, int]] | None = None,
) -> tuple[float, float, float]:
    """Sentence metrics with each locked name folded into one placeholder on both sides.

    `rescued_spans` names the occurrences the component-phoneme check matched after the
    alignment had already given up on them, mapped to the transcript tokens they cover. Those
    tokens have to be folded away like any other matched name, and the alignment cannot say
    so: it parked the anchor on a single substitution and left the rest of the name to be
    swept up as insertions.

    Skipping this is not a small error. On alpha.52's "Tên tôi là Samael Kaizer Theosbane."
    the name is four transcript tokens; counting three of them as insertions against a
    four-token canonical expectation gives WER 0.75 where the truth is 0.0, so the take the
    check had just accepted was refused by the content gate one step later - the anchor fix
    passed the name and changed nothing that anybody could see.
    """
    expected_tokens = [
        _semantic_anchor_token(
            int(unit["repeat_index"]),
            int(unit["anchor_index"]),
            anchor_count,
        )
        if unit["kind"] == "anchor"
        else str(unit["token"])
        for unit in units
    ]
    # Transcript index -> the occurrence whose rescued span covers it, so every operation
    # landing inside a rescued name folds into that name's single placeholder however the
    # alignment happened to distribute those tokens.
    rescued_by_index: dict[int, tuple[int, int]] = {}
    for occurrence, (span_start, span_end) in (rescued_spans or {}).items():
        for index in range(int(span_start), int(span_end)):
            rescued_by_index[index] = occurrence
    emitted_rescues: set[tuple[int, int]] = set()

    def _consume_rescued(index: int) -> bool:
        """Emit the placeholder once per rescued name and swallow the rest of its tokens."""
        occurrence = rescued_by_index.get(index)
        if occurrence is None:
            return False
        if occurrence not in emitted_rescues:
            emitted_rescues.add(occurrence)
            actual_tokens.append(
                _semantic_anchor_token(occurrence[0], occurrence[1], anchor_count)
            )
        return True

    actual_tokens: list[str] = []
    transcript_cursor = 0
    for operation in operations:
        kind = str(operation["kind"])
        if kind in {"insert_transcript", "match_token", "substitute_token"}:
            if not _consume_rescued(transcript_cursor):
                actual_tokens.append(transcript_tokens[transcript_cursor])
            transcript_cursor += 1
        elif kind == "match_anchor":
            actual_tokens.append(
                _semantic_anchor_token(
                    int(operation["repeat_index"]),
                    int(operation["anchor_index"]),
                    anchor_count,
                )
            )
            transcript_cursor += len(operation["matched_tokens"])
        elif kind == "substitute_anchor":
            # A name the transcript rendered differently is adjudicated by the anchor
            # evidence, which reports it for review. Letting it also count as an
            # ordinary substitution here would punish the same disagreement twice and
            # push short sentences past the WER gate on their names alone. A name the
            # transcript dropped entirely stays a `delete_anchor` and still counts.
            if not _consume_rescued(transcript_cursor):
                actual_tokens.append(
                    _semantic_anchor_token(
                        int(operation["repeat_index"]),
                        int(operation["anchor_index"]),
                        anchor_count,
                    )
                )
            transcript_cursor += 1
    if transcript_cursor != len(transcript_tokens):
        raise RuntimeError("Locked-name canonical alignment did not consume transcript")

    # Fold tone here too, for the same reason the ordinary metrics do: a tone difference
    # on the words around a name says nothing about whether the take was good. Taking the
    # better of the two readings keeps the fold from ever failing something plain
    # comparison passed. The anchor placeholders are not Vietnamese words, so they fold
    # to themselves and keep aligning.
    similarity, character_error_rate, word_error_rate = _sequence_metrics(
        expected_tokens,
        actual_tokens,
    )
    folded_similarity, folded_cer, folded_wer = _sequence_metrics(
        _tone_folded_words(expected_tokens),
        _tone_folded_words(actual_tokens),
    )
    return (
        float(max(similarity, folded_similarity)),
        float(min(character_error_rate, folded_cer)),
        float(min(word_error_rate, folded_wer)),
    )


def _sequence_metrics(
    expected_tokens: list[str],
    actual_tokens: list[str],
) -> tuple[float, float, float]:
    expected_characters = list(" ".join(expected_tokens))
    actual_characters = list(" ".join(actual_tokens))
    character_error_rate = _edit_distance(
        expected_characters,
        actual_characters,
    ) / max(1, len(expected_characters))
    word_error_rate = _edit_distance(
        expected_tokens,
        actual_tokens,
    ) / max(1, len(expected_tokens))
    return max(0.0, 1.0 - character_error_rate), character_error_rate, word_error_rate


def _passes_asr_content_thresholds(
    transcript_present: bool,
    similarity: float,
    wer: float,
    *,
    min_similarity: float,
    max_wer: float,
) -> bool:
    return transcript_present and not (
        similarity < min_similarity
        or (wer > max_wer and similarity < min_similarity + ASR_WER_SIMILARITY_MARGIN)
    )


def adjudicate_locked_name_anchors(
    expected_spoken_text: str,
    asr_result: dict[str, Any],
    anchors: Sequence[Mapping[str, Any]],
    repeat_count: int = 1,
    *,
    min_similarity: float | None = None,
    max_wer: float | None = None,
) -> dict[str, Any]:
    """Require exact locked-name forms in an ASR transcript without fuzzy aliases.

    Every anchor carries an end-exclusive character span into the exact
    ``expected_spoken_text``. Repeated-short ASR must pass the complete aligned
    sequence for every repeated copy, so callers pass its audio repeat count
    through ``repeat_count``.
    """

    if not anchors:
        return asr_result
    if isinstance(repeat_count, bool) or not isinstance(repeat_count, int) or repeat_count < 1:
        raise ValueError("repeat_count must be a positive integer")

    result = dict(asr_result)
    normalized_transcript = normalize_transcript(str(result.get("transcript", "")))
    transcript_tokens = normalized_transcript.split()
    normalized_expected = normalize_transcript(expected_spoken_text)
    safe_anchors = [
        {
            str(key): _json_safe_anchor_value(value)
            for key, value in anchor.items()
        }
        for anchor in anchors
    ]
    required_occurrence_count = len(safe_anchors) * repeat_count
    precedence_inconclusive = result.get("verdict") == ASR_INCONCLUSIVE
    evidence: list[dict[str, Any]] = []

    if precedence_inconclusive:
        for repeat_index in range(repeat_count):
            for anchor_index, anchor in enumerate(safe_anchors):
                evidence.append(
                    {
                        **anchor,
                        "repeat_index": repeat_index,
                        "required_order": len(evidence),
                        "anchor_index": anchor_index,
                        "status": "skipped_inconclusive",
                        "matched": False,
                    }
                )
        result[LOCKED_NAME_ANCHOR_METRICS_KEY] = {
            "version": LOCKED_NAME_ANCHOR_METRICS_VERSION,
            "status": "skipped_inconclusive",
            "adjudicated": False,
            "passed": None,
            "failure_codes": [],
            "repeat_count": repeat_count,
            "anchor_count": len(safe_anchors),
            "required_occurrence_count": required_occurrence_count,
            "matched_occurrence_count": 0,
            "expected_token_count": len(normalized_expected.split()),
            "transcript_token_count": len(transcript_tokens),
            "anchors": evidence,
        }
        return result

    units, invalid_occurrences = _build_locked_name_alignment_units(
        expected_spoken_text,
        safe_anchors,
        repeat_count,
    )
    alignment_score, operations = _minimum_cost_locked_name_alignment(
        units,
        transcript_tokens,
    )
    anchor_operations = {
        (operation["repeat_index"], operation["anchor_index"]): operation
        for operation in operations
        if operation["kind"]
        in {"match_anchor", "substitute_anchor", "delete_anchor"}
    }
    matched_occurrence_count = 0
    # Tokens an exact match has already claimed. The rescue below may not reuse them, and
    # the reason is not order alone: the alignment is free to match the *second* and *third*
    # occurrences of a repeated name and leave the first unassigned, so a cursor that only
    # moves forward as occurrences are visited would still let the first one re-find the
    # name inside the span the second had taken. Three requirements would then be met by two
    # readings. A test pins exactly that, and this is what it caught.
    # Occurrence -> transcript span, for the names the component-phoneme check matched after
    # the alignment gave up on them. The canonical metrics need it: without the span they
    # fold away one token of a multi-token name and count the rest as insertions.
    rescued_spans: dict[tuple[int, int], tuple[int, int]] = {}
    claimed_tokens: set[int] = {
        index
        for ordinary_operation in operations
        if ordinary_operation.get("kind") == "match_token"
        for index in range(
            int(ordinary_operation["token_start"]), int(ordinary_operation["token_end"])
        )
    }
    # And how far along the transcript the occurrences have read, which is a separate
    # requirement from what they consumed: anchors must appear in the order they were
    # written, so a later one may not match text an earlier one has already passed.
    component_cursor = 0
    for occurrence_operation in anchor_operations.values():
        if occurrence_operation.get("kind") == "match_anchor":
            claimed_tokens.update(
                range(
                    int(occurrence_operation["token_start"]),
                    int(occurrence_operation["token_end"]),
                )
            )
    for repeat_index in range(repeat_count):
        for anchor_index, anchor in enumerate(safe_anchors):
            forms = _locked_name_anchor_forms(anchor)
            occurrence = (repeat_index, anchor_index)
            operation = anchor_operations.get(occurrence)
            anchor_evidence = {
                **anchor,
                "repeat_index": repeat_index,
                "required_order": len(evidence),
                "anchor_index": anchor_index,
                "accepted_forms": [
                    {
                        "kind": kind,
                        "tokens": list(tokens),
                        "comparison_mode": comparison_mode,
                    }
                    for kind, tokens, comparison_mode in forms
                ],
            }
            if occurrence in invalid_occurrences:
                anchor_evidence.update(
                    {
                        "status": "invalid_expected_anchor_span",
                        "matched": False,
                        "span_validation_error": invalid_occurrences[occurrence],
                    }
                )
            elif operation is not None and operation["kind"] == "match_anchor":
                matched_occurrence_count += 1
                component_cursor = max(component_cursor, int(operation["token_end"]))
                anchor_evidence.update(
                    {
                        "status": "matched",
                        "matched": True,
                        "matched_form": operation["form_kind"],
                        "matched_comparison_mode": operation["comparison_mode"],
                        "matched_tokens": list(operation["matched_tokens"]),
                        "matched_token_start": operation["token_start"],
                        "matched_token_end": operation["token_end"],
                    }
                )
            else:
                component_match = _locked_name_anchor_component_match(
                    anchor,
                    transcript_tokens,
                    blocked_tokens=claimed_tokens,
                    from_token=component_cursor,
                )
                if component_match is not None and component_match["passed"]:
                    component_cursor = max(
                        component_cursor, int(component_match["token_end"])
                    )
                    rescued_spans[(repeat_index, anchor_index)] = (
                        int(component_match["token_start"] or 0),
                        int(component_match["token_end"]),
                    )
                    claimed_tokens.update(
                        range(
                            int(component_match["token_start"] or 0),
                            int(component_match["token_end"]),
                        )
                    )
                    # Exact matching cannot recognise this name, but every part of it is
                    # audibly present. Counted as matched and labelled distinctly, so the
                    # report still shows that the spelling disagreed.
                    matched_occurrence_count += 1
                    anchor_evidence.update(
                        {
                            "status": "matched_by_component_phonemes",
                            "matched": True,
                            "matched_form": "component_phonemes",
                            "matched_comparison_mode": (
                                ANCHOR_COMPARISON_COMPONENT_PHONEMES
                            ),
                            "component_phonemes": component_match,
                        }
                    )
                    evidence.append(anchor_evidence)
                    continue
                anchor_evidence.update(
                    {
                        "status": "missing_or_wrong",
                        "matched": False,
                    }
                )
                if component_match is not None:
                    anchor_evidence["component_phonemes"] = component_match
                if operation is not None:
                    token_start = operation["token_start"]
                    token_end = operation["token_end"]
                    anchor_evidence.update(
                        {
                            "alignment_operation": operation["kind"],
                            "aligned_token_start": token_start,
                            "aligned_token_end": token_end,
                            "aligned_tokens": transcript_tokens[token_start:token_end],
                        }
                    )
            evidence.append(anchor_evidence)

    anchors_passed = matched_occurrence_count == required_occurrence_count
    canonical_similarity: float | None = None
    canonical_cer: float | None = None
    canonical_wer: float | None = None
    canonical_threshold_passed: bool | None = None
    canonical_promoted = False
    canonical_demoted = False
    canonical_similarity, canonical_cer, canonical_wer = _canonical_locked_name_metrics(
        units,
        operations,
        transcript_tokens,
        len(safe_anchors),
        rescued_spans,
    )
    ordinary_expected_tokens = sum(1 for unit in units if unit["kind"] != "anchor")
    # An anchor unit stands in for however many written tokens its spoken form has, so
    # count those rather than counting one per anchor - a three-syllable name occupies
    # three of the tokens the sentence metric would otherwise have to work with.
    anchor_expected_tokens = sum(
        max(
            (len(form_tokens) for _kind, form_tokens, _mode in unit["forms"]),
            default=1,
        )
        for unit in units
        if unit["kind"] == "anchor"
    )
    canonical_waiver_available = (
        ordinary_expected_tokens >= CANONICAL_ANCHOR_WAIVER_MIN_ORDINARY_TOKENS
        and ordinary_expected_tokens >= anchor_expected_tokens
    )
    if min_similarity is not None and max_wer is not None and (
        anchors_passed or canonical_waiver_available
    ):
        canonical_threshold_passed = _passes_asr_content_thresholds(
            bool(transcript_tokens),
            canonical_similarity,
            canonical_wer,
            min_similarity=float(min_similarity),
            max_wer=float(max_wer),
        )
        if anchors_passed:
            canonical_promoted = bool(
                canonical_threshold_passed
                and result.get("verdict") == ASR_MISMATCH
                and result.get("reason") == "ASR_MISMATCH"
            )
            canonical_demoted = bool(
                not canonical_threshold_passed
                and result.get("verdict") == ASR_PASS
            )

    result[LOCKED_NAME_ANCHOR_METRICS_KEY] = {
        "version": LOCKED_NAME_ANCHOR_METRICS_VERSION,
        "status": (
            "pass"
            if anchors_passed
            else ("review_eligible" if canonical_threshold_passed else "fail")
        ),
        "adjudicated": True,
        "passed": anchors_passed,
        "failure_codes": [] if anchors_passed else [ASR_LOCKED_NAME_ANCHOR_MISMATCH],
        "review_codes": (
            [ASR_LOCKED_NAME_ANCHOR_REVIEW]
            if not anchors_passed and canonical_threshold_passed
            else []
        ),
        "repeat_count": repeat_count,
        "anchor_count": len(safe_anchors),
        "required_occurrence_count": required_occurrence_count,
        "matched_occurrence_count": matched_occurrence_count,
        "expected_token_count": len(normalized_expected.split()),
        "transcript_token_count": len(transcript_tokens),
        "alignment_edit_cost": alignment_score[0],
        "ordinary_exact_match_count": -alignment_score[1],
        "raw_similarity": result.get("similarity"),
        "raw_wer": result.get("wer"),
        "canonical_similarity": canonical_similarity,
        "canonical_cer": canonical_cer,
        "canonical_wer": canonical_wer,
        "canonical_min_similarity": min_similarity,
        "canonical_max_wer": max_wer,
        "canonical_threshold_passed": canonical_threshold_passed,
        "ordinary_expected_token_count": ordinary_expected_tokens,
        "anchor_expected_token_count": anchor_expected_tokens,
        "canonical_waiver_available": canonical_waiver_available,
        "canonical_promoted": canonical_promoted,
        "canonical_demoted": canonical_demoted,
        "anchors": evidence,
    }
    if anchors_passed:
        if canonical_promoted:
            result.update(
                {
                    "passed": True,
                    "verdict": ASR_PASS,
                    "reason": ASR_LOCKED_NAME_CANONICAL_PASS,
                    "repairable": False,
                    "severe": False,
                }
            )
        elif canonical_demoted:
            result.update(
                {
                    "passed": False,
                    "verdict": ASR_MISMATCH,
                    "reason": "ASR_MISMATCH",
                    "repairable": True,
                    "severe": False,
                }
            )
        return result

    # Anchors failed. Whisper's spelling for a foreign name read with Vietnamese
    # phonemes is not evidence about pronunciation, so the anchor reports review
    # evidence rather than failing the segment; the canonical sentence metrics, which
    # exclude the name spans, keep the hard-fail authority. Repair is not offered for
    # an anchor-only disagreement: the cause is the transcript's orthography, not the
    # audio, and re-generating cannot change it.
    if canonical_threshold_passed is None:
        # Either the caller did not opt into canonical gating, or the utterance is too
        # short for waiving the name to leave anything worth checking. Keep the strict
        # historical behaviour rather than letting an unmatched anchor through.
        result.update(
            {
                "locked_name_review_eligible": False,
                "passed": False,
                "verdict": ASR_MISMATCH,
                "reason": ASR_LOCKED_NAME_ANCHOR_MISMATCH,
                "repairable": True,
            }
        )
        return result
    # Repair still runs: a regenerated take may genuinely pronounce the name better,
    # and that chance is worth the attempts. What changes is the terminal state. When
    # the budget is exhausted and the canonical sentence metrics - which exclude the
    # name spans - are acceptable, the pipeline publishes the segment with review
    # evidence instead of failing it, because Whisper's spelling is not proof of
    # mispronunciation. `locked_name_review_eligible` carries that decision.
    result["locked_name_review_eligible"] = bool(canonical_threshold_passed)
    # The reason stays the anchor mismatch in both cases so the failure evidence remains
    # self-consistent for the candidate ledger, which requires reason, failure codes and
    # anchor status to agree. Whether the sentence content was independently acceptable
    # is carried by `locked_name_review_eligible`, and only the pipeline's exhaustion
    # handling reads it.
    result.update(
        {
            "passed": False,
            "verdict": ASR_MISMATCH,
            "reason": ASR_LOCKED_NAME_ANCHOR_MISMATCH,
            "repairable": True,
            "severe": False,
        }
    )
    return result


def adjudicate_collapsed_repeated_short(
    expected_spoken_text: str,
    asr_result: dict[str, Any],
    anchors: Sequence[Mapping[str, Any]],
    *,
    requested_repeat_count: int,
    min_similarity: float,
    max_wer: float,
) -> dict[str, Any] | None:
    """Re-adjudicate a decoder-collapsed repeat as one exact spoken copy.

    Whisper can collapse identical short-context repetitions into one transcript.
    This path remains limited to locked-name evidence and preserves both the
    requested and effective repeat counts in the durable adjudication metrics.
    """

    if requested_repeat_count != SHORT_CONTEXT_REPEAT_COUNT or isinstance(
        requested_repeat_count,
        bool,
    ):
        raise ValueError(
            "requested_repeat_count must match the repeated-short decode contract"
        )
    if not anchors:
        return None
    if LOCKED_NAME_ANCHOR_METRICS_KEY in asr_result:
        raise RuntimeError("collapsed repeated-short adjudication requires raw ASR evidence")
    transcript = asr_result.get("transcript")
    raw_evidence_is_eligible = (
        asr_result.get("verdict") == ASR_MISMATCH
        and asr_result.get("passed") is False
        and asr_result.get("reason") == "ASR_MISMATCH"
        and isinstance(transcript, str)
        and bool(transcript.strip())
    )
    if not raw_evidence_is_eligible:
        return None

    similarity, wer = transcript_metrics(expected_spoken_text, transcript)
    content_passed = _passes_asr_content_thresholds(
        True,
        similarity,
        wer,
        min_similarity=min_similarity,
        max_wer=max_wer,
    )
    rescored_result = {
        "passed": content_passed,
        "verdict": ASR_PASS if content_passed else ASR_MISMATCH,
        "transcript": transcript,
        "similarity": similarity,
        "wer": wer,
        "reason": "ok" if content_passed else "ASR_MISMATCH",
        "repairable": is_asr_repair_candidate(expected_spoken_text),
        "severe": not content_passed
        and is_severe_asr_mismatch(expected_spoken_text, transcript, similarity),
    }

    collapsed = adjudicate_locked_name_anchors(
        expected_spoken_text,
        rescored_result,
        anchors,
        repeat_count=1,
        min_similarity=min_similarity,
        max_wer=max_wer,
    )
    anchor_metrics = collapsed.get(LOCKED_NAME_ANCHOR_METRICS_KEY)
    if not isinstance(anchor_metrics, dict) or anchor_metrics.get("adjudicated") is not True:
        raise RuntimeError("collapsed repeated-short anchor evidence is incomplete")

    result = dict(collapsed)
    result[LOCKED_NAME_ANCHOR_METRICS_KEY] = {
        **anchor_metrics,
        "requested_repeat_count": requested_repeat_count,
        "effective_repeat_count": COLLAPSED_SHORT_CONTEXT_EFFECTIVE_REPEAT_COUNT,
    }
    result["requested_repeat_count"] = requested_repeat_count
    result["effective_repeat_count"] = (
        COLLAPSED_SHORT_CONTEXT_EFFECTIVE_REPEAT_COUNT
    )
    return result


def _edit_distance(left: list[str], right: list[str]) -> int:
    if len(left) < len(right):
        left, right = right, left
    previous = list(range(len(right) + 1))
    for i, token_left in enumerate(left, 1):
        current = [i]
        for j, token_right in enumerate(right, 1):
            current.append(
                min(
                    current[-1] + 1,
                    previous[j] + 1,
                    previous[j - 1] + (token_left != token_right),
                )
            )
        previous = current
    return previous[-1]


# Whisper's Vietnamese tone output is not reliable evidence about the audio. Measured
# over a whole book, tone-only differences appear across the segments that pass as well
# as the ones that fail - median 0.000 but p99 0.362 among verified segments, against a
# median of 0.296 among failed ones, with a verified segment reaching 1.000. The two
# populations do not separate, so a tone difference carries no signal about whether the
# take was good. Consonants and vowels, which Whisper does get right, carry that signal.
#
# Folding tone out of the comparison therefore removes noise, not evidence - and it also
# means the ASR gate no longer detects a TTS tone error. It did not reliably detect one
# before either, because it could not tell a TTS tone error from an ASR tone error;
# it simply failed segments when the noise happened to cross the threshold. UTMOSv2 and
# a human listening to the review queue are what cover that now.
VIETNAMESE_TONE_MARKERS = frozenset("2ɜ456")
PHONEME_STRESS_MARKERS = frozenset("ˈˌ")


def _segmental_phonemes(word: str) -> str | None:
    """The word's phonemes with tone and stress removed, or None when unavailable.

    sea-g2p detects language per token, so a token it does not read as Vietnamese comes
    back as English or spelled out. That makes the segmental form unusable for those
    tokens, which is why callers must treat None as "no opinion" rather than "different".
    """
    phonemes = _vietnamese_phonemes(word)
    if not phonemes:
        return None
    return "".join(
        character
        for character in phonemes
        if character not in VIETNAMESE_TONE_MARKERS
        and character not in PHONEME_STRESS_MARKERS
    )


def _tone_folded_words(words: list[str]) -> list[str]:
    folded = []
    for word in words:
        segmental = _segmental_phonemes(word)
        folded.append(segmental if segmental else word)
    return folded


def tone_folded_transcript_metrics(
    expected: str,
    actual: str,
) -> tuple[float, float, dict[str, float]]:
    """Content metrics that ignore tone, never scored worse than the plain comparison.

    A token sea-g2p cannot read as Vietnamese keeps its written form, so folding could in
    principle align two tokens worse than the letters did. Taking the better of the two
    readings makes the fold provably unable to fail anything the plain comparison passed.
    """
    raw_similarity, raw_wer = transcript_metrics(expected, actual)
    expected_words = normalize_transcript(expected).split()
    actual_words = normalize_transcript(actual).split()
    folded_expected = _tone_folded_words(expected_words)
    folded_actual = _tone_folded_words(actual_words)
    folded_wer = _edit_distance(folded_expected, folded_actual) / max(1, len(folded_expected))
    expected_characters = list(" ".join(folded_expected))
    actual_characters = list(" ".join(folded_actual))
    folded_similarity = max(
        0.0,
        1.0 - _edit_distance(expected_characters, actual_characters)
        / max(1, len(expected_characters)),
    )
    compared = min(len(expected_words), len(actual_words))
    tone_only = sum(
        1
        for index in range(compared)
        if expected_words[index] != actual_words[index]
        and folded_expected[index] == folded_actual[index]
        and _segmental_phonemes(expected_words[index]) is not None
    )
    similarity = max(raw_similarity, folded_similarity)
    wer = min(raw_wer, folded_wer)
    return (
        float(similarity),
        float(wer),
        {
            "raw_similarity": float(raw_similarity),
            "raw_wer": float(raw_wer),
            "tone_folded_similarity": float(folded_similarity),
            "tone_folded_wer": float(folded_wer),
            "tone_only_difference_rate": float(tone_only / compared) if compared else 0.0,
        },
    )


def transcript_metrics(expected: str, actual: str) -> tuple[float, float]:
    normalized_expected = normalize_transcript(expected)
    normalized_actual = normalize_transcript(actual)
    expected_characters = list(normalized_expected)
    actual_characters = list(normalized_actual)
    character_errors = _edit_distance(expected_characters, actual_characters)
    similarity = max(0.0, 1.0 - character_errors / max(1, len(expected_characters)))
    expected_words = normalized_expected.split()
    actual_words = normalized_actual.split()
    wer = _edit_distance(expected_words, actual_words) / max(1, len(expected_words))
    return float(similarity), float(wer)


def is_asr_repair_candidate(expected: str) -> bool:
    return len(normalize_transcript(expected).split()) >= ASR_REPAIR_MIN_WORDS


def is_severe_asr_mismatch(expected: str, actual: str, similarity: float) -> bool:
    expected_words = normalize_transcript(expected).split()
    actual_words = normalize_transcript(actual).split()
    if not expected_words:
        return False
    if not actual_words:
        return True
    minimum_actual_words = max(
        len(expected_words) + SEVERE_MISMATCH_MIN_EXTRA_WORDS,
        math.ceil(len(expected_words) * SEVERE_MISMATCH_MIN_LENGTH_RATIO),
    )
    return float(similarity) < SEVERE_MISMATCH_MAX_SIMILARITY and (
        len(actual_words) >= minimum_actual_words
        or abs(len(actual_words) - len(expected_words)) <= SEVERE_MISMATCH_MIN_EXTRA_WORDS
    )


def transcript_exceeds_physical_rate(actual: str, duration_seconds: float) -> bool:
    actual_words = normalize_transcript(actual).split()
    if not actual_words or duration_seconds <= 0:
        return False
    plausible_words = max(
        MIN_PLAUSIBLE_TRANSCRIPT_WORDS,
        math.ceil(duration_seconds * MAX_PLAUSIBLE_TRANSCRIPT_WORDS_PER_SECOND)
        + TRANSCRIPT_WORD_MARGIN,
    )
    return len(actual_words) > plausible_words


def transcription_exceeds_audio_timeline(
    segments: list[dict[str, Any]],
    duration_seconds: float,
) -> bool:
    if duration_seconds <= 0 or not segments:
        return False
    plausible_end = max(
        duration_seconds + WHISPER_TIMELINE_ABSOLUTE_MARGIN_SECONDS,
        duration_seconds * WHISPER_TIMELINE_DURATION_FACTOR,
    )
    for segment in segments:
        try:
            end = float(segment.get("end", 0.0))
        except (TypeError, ValueError):
            continue
        if end > plausible_end:
            return True
    return False


def load_audio_for_whisper(path: Path) -> np.ndarray:
    audio, sample_rate = sf.read(path, dtype="float32", always_2d=False)
    array = np.asarray(audio, dtype=np.float32)
    if array.ndim != 1:
        raise RuntimeError(f"Whisper input must be mono, got shape {array.shape}")
    if int(sample_rate) != WHISPER_SAMPLE_RATE:
        divisor = math.gcd(int(sample_rate), WHISPER_SAMPLE_RATE)
        array = resample_poly(
            array,
            WHISPER_SAMPLE_RATE // divisor,
            int(sample_rate) // divisor,
        ).astype(np.float32, copy=False)
    return array


class WhisperVerifier:
    def __init__(self, settings: dict[str, Any], log: Callable[[str], None]) -> None:
        self.settings = settings["asr"]
        self.allow_downloads = bool(settings.get("safety", {}).get("allow_network_downloads_during_job", False))
        self.log = log
        self.model = None
        self.device = str(self.settings.get("device", "cuda"))
        # "openai" is what every run so far used. "faster" runs the same large-v3-turbo
        # weights through CTranslate2, measured at 2.07x with zero verdict disagreements
        # over 200 takes - see docs/WHERE_A_RUN_SPENDS_ITS_TIME.md. It is opt-in because
        # adding the dependency is a version event and because nothing downstream should
        # have to know which runtime produced a transcript.
        self.engine = str(self.settings.get("engine", "openai")).strip().casefold()
        if self.engine not in {"openai", "faster"}:
            raise ValueError("asr.engine must be openai or faster")
        self._last_transcription_timeline_impossible = False

    def _load_faster(self) -> bool:
        """Load the CTranslate2 runtime, importing torch first on purpose.

        CTranslate2 links cuBLAS and cuDNN at load time and does not ship them; torch does,
        in its own lib directory. Importing torch first puts those DLLs in the process, and
        in a scratchpad venv without torch neither os.add_dll_directory nor a PATH entry was
        enough - the libraries had to sit beside the ctranslate2 package. That is the shape
        of failure to expect on a machine where this does not work.
        """
        import torch  # noqa: F401  - imported for its bundled CUDA libraries
        from faster_whisper import WhisperModel

        device = self.device
        if device.startswith("cuda") and not torch.cuda.is_available():
            if self.settings.get("cpu_fallback", True):
                device = "cpu"
            else:
                raise RuntimeError("CUDA unavailable for Whisper")
        model_name = str(self.settings["model"])
        compute_type = str(
            self.settings.get(
                "compute_type", "float16" if device.startswith("cuda") else "int8"
            )
        )
        self.log(f"Nạp faster-whisper {model_name} trên {device} ({compute_type}).")
        # local_files_only, for the same reason the openai path checks for its checkpoint
        # before loading: a job must never pull a model over the network while it runs. The
        # CTranslate2 weights are a different artifact from openai-whisper's .pt - they come
        # from the Hugging Face cache, not runtime/models/whisper - and alpha.43 fetched
        # about 1.5 GB mid-run without anything noticing, because this call had neither the
        # guard nor a root. Setup pre-fetches them; if they are absent, say so and stop
        # rather than start a download nobody asked for.
        try:
            self.model = WhisperModel(
                model_name,
                device=device,
                compute_type=compute_type,
                local_files_only=True,
            )
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(
                f"Thiếu faster-whisper {model_name} trong cache Hugging Face: {exc}. "
                "Job không được tự tải model giữa chừng. Chạy lại scripts/setup_windows.ps1 "
                "để tải sẵn, hoặc đặt asr.engine = \"openai\" để dùng checkpoint đã có "
                "trong runtime/models/whisper."
            ) from exc
        self.device = device
        return True

    def load(self) -> bool:
        if not self.settings.get("enabled", True):
            return False
        if self.model is not None:
            return True
        if self.engine == "faster":
            try:
                return self._load_faster()
            except Exception as exc:  # noqa: BLE001
                self.log(f"Không nạp được faster-whisper: {exc}")
                if self.settings.get("required", False) or self.settings.get("failure_policy") == "fail":
                    raise
                return False
        try:
            import torch
            import whisper

            device = self.device
            if device.startswith("cuda") and not torch.cuda.is_available():
                if self.settings.get("cpu_fallback", True):
                    device = "cpu"
                else:
                    raise RuntimeError("CUDA unavailable for Whisper")
            model_name = str(self.settings["model"])
            download_root = Path(str(self.settings.get("download_root", "models/whisper")))
            model_url = getattr(whisper, "_MODELS", {}).get(model_name)
            expected_model = download_root / str(model_url).rsplit("/", 1)[-1] if model_url else None
            if not self.allow_downloads and expected_model is not None and not expected_model.exists():
                message = (
                    f"Thiếu Whisper {model_name} trong {download_root}. Job không được tự tải model giữa chừng; "
                    "hãy chạy Ebook Reader trước."
                )
                self.log(message)
                if self.settings.get("required", False) or self.settings.get("failure_policy") == "fail":
                    raise RuntimeError(message)
                return False
            self.log(f"Nạp Whisper {model_name} trên {device}.")
            self.model = whisper.load_model(
                model_name,
                device=device,
                download_root=str(download_root),
            )
            self.device = device
            return True
        except Exception as exc:  # noqa: BLE001
            self.log(f"Không nạp được Whisper: {exc}")
            if self.settings.get("required", False) or self.settings.get("failure_policy") == "fail":
                raise
            return False

    def unload(self) -> None:
        had_model = self.model is not None
        self.model = None
        if not had_model:
            return
        gc.collect()
        try:
            import torch

            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except Exception:
            pass
        trim_process_working_set()

    def _transcribe_audio(
        self,
        audio: np.ndarray,
        duration_seconds: float,
        *,
        confirmation: bool,
    ) -> str:
        if self.model is None:
            raise RuntimeError("Whisper is not loaded")
        self._last_transcription_timeline_impossible = False
        decode_options: dict[str, Any] = {
            "language": "vi",
            "task": "transcribe",
            "fp16": self.device.startswith("cuda"),
            "temperature": 0.0,
            "condition_on_previous_text": False,
            "verbose": False,
        }
        if not confirmation and duration_seconds > self._beam_minimum_seconds():
            decode_options["beam_size"] = int(self.settings.get("beam_size", 5))
        if self.engine == "faster":
            # Dọn ở **cả hai** nhánh engine, tại chỗ transcript ra đời. `transcribe()` không
            # phải nơi duy nhất gọi hàm này - còn một chỗ nữa ở nhánh lặp câu ngắn - nên bọc
            # ở đây thay vì bọc chỗ gọi.
            return strip_lone_surrogates(
                self._transcribe_faster(audio, duration_seconds, decode_options)
            )
        result = self.model.transcribe(audio, **decode_options)
        raw_segments = result.get("segments", [])
        segments = [item for item in raw_segments if isinstance(item, dict)]
        self._last_transcription_timeline_impossible = transcription_exceeds_audio_timeline(
            segments,
            duration_seconds,
        )
        return strip_lone_surrogates(str(result.get("text", "")).strip())

    def _transcribe_faster(
        self,
        audio: np.ndarray,
        duration_seconds: float,
        decode_options: dict[str, Any],
    ) -> str:
        """The same request through CTranslate2, answered in the same shape.

        Nothing downstream may learn which runtime produced this. The timeline check reads
        segment end times, so the generator is drained into the dicts it expects; greedy is
        beam_size 1 rather than an absent argument; and fp16 is a load-time compute_type
        here rather than a decode option.
        """
        segments_iterator, _info = self.model.transcribe(
            audio,
            language=str(decode_options["language"]),
            task=str(decode_options["task"]),
            temperature=float(decode_options["temperature"]),
            condition_on_previous_text=bool(decode_options["condition_on_previous_text"]),
            beam_size=int(decode_options.get("beam_size", 1)),
        )
        parts: list[str] = []
        segments: list[dict[str, Any]] = []
        for item in segments_iterator:
            parts.append(str(getattr(item, "text", "")))
            segments.append(
                {
                    "start": float(getattr(item, "start", 0.0) or 0.0),
                    "end": float(getattr(item, "end", 0.0) or 0.0),
                }
            )
        self._last_transcription_timeline_impossible = transcription_exceeds_audio_timeline(
            segments,
            duration_seconds,
        )
        return "".join(parts).strip()

    def _beam_minimum_seconds(self) -> float:
        """Below this, the primary decode is greedy too.

        Beam search carries several hypotheses and keeps the most likely sequence, and on
        audio with little content in it the most likely sequence is boilerplate. Measured
        on 120 of alpha.25's takes shorter than 2.5 seconds, beam and greedy disagreed
        about seven of them and flipped the verdict on three - every one of the three in
        greedy's favour, with beam answering a two-syllable "Hờ." with "Hãy subscribe cho
        kênh Để không bỏ lỡ những video hấp dẫn", a sigh with "Ah yeah.", and "tôi" with
        "Đôi.". Not one short take came out better under beam.

        On longer audio it earns its keep: over 160 takes of every length the only
        disagreement that favoured beam was a full sentence, where it heard "rồng" where
        greedy heard "dòng". So the search is kept where content supports it and dropped
        where it invents content instead - which is 1.47x faster on those takes as well,
        though that is the smaller reason.
        """
        return float(self.settings.get("beam_minimum_seconds", BEAM_MINIMUM_SECONDS))

    def transcribe(self, path: Path, *, confirmation: bool = False) -> str:
        audio = load_audio_for_whisper(path)
        try:
            duration_seconds = float(sf.info(path).duration)
        except (RuntimeError, TypeError, ValueError):
            duration_seconds = float(audio.size / WHISPER_SAMPLE_RATE)
        return self._transcribe_audio(
            audio,
            duration_seconds,
            confirmation=confirmation,
        )

    def _evaluate_transcript(
        self,
        expected: str,
        transcript: str,
        duration_seconds: float,
    ) -> dict[str, Any]:
        """Evaluate a transcript, keeping the plain metrics alongside the graded ones."""
        _similarity, _wer, tone_evidence = tone_folded_transcript_metrics(
            expected,
            transcript,
        )
        result = self._evaluate_transcript_core(expected, transcript, duration_seconds)
        for key, value in tone_evidence.items():
            result.setdefault(key, value)
        return result

    def _evaluate_transcript_core(
        self,
        expected: str,
        transcript: str,
        duration_seconds: float,
    ) -> dict[str, Any]:
        similarity, wer, _tone_evidence = tone_folded_transcript_metrics(
            expected,
            transcript,
        )
        if self._last_transcription_timeline_impossible:
            return {
                "passed": False,
                "verdict": ASR_INCONCLUSIVE,
                "transcript": transcript,
                "similarity": similarity,
                "wer": wer,
                "reason": ASR_TRANSCRIPT_TIMELINE_IMPOSSIBLE,
                "repairable": False,
                "severe": False,
            }
        if transcript_exceeds_physical_rate(transcript, duration_seconds):
            return {
                "passed": False,
                "verdict": ASR_INCONCLUSIVE,
                "transcript": transcript,
                "similarity": similarity,
                "wer": wer,
                "reason": ASR_TRANSCRIPT_RATE_IMPOSSIBLE,
                "repairable": False,
                "severe": False,
            }
        if is_vocalization_only(expected) and (
            not normalize_transcript(transcript) or is_vocalization_only(transcript)
        ):
            return {
                "passed": True,
                "verdict": ASR_PASS,
                "transcript": transcript,
                "similarity": similarity,
                "wer": wer,
                "reason": "VOCALIZATION_ASR_COMPATIBLE",
                "repairable": False,
                "severe": False,
            }
        min_similarity = float(self.settings.get("min_similarity", 0.58))
        max_wer = float(self.settings.get("max_wer", 0.58))
        passed = _passes_asr_content_thresholds(
            bool(transcript),
            similarity,
            wer,
            min_similarity=min_similarity,
            max_wer=max_wer,
        )
        return {
            "passed": passed,
            "verdict": ASR_PASS if passed else ASR_MISMATCH,
            "transcript": transcript,
            "similarity": similarity,
            "wer": wer,
            "reason": "ok" if passed else "ASR_MISMATCH",
            "repairable": is_asr_repair_candidate(expected),
            "severe": not passed and is_severe_asr_mismatch(expected, transcript, similarity),
        }

    def can_verify_repeated_short(self, expected: str) -> bool:
        word_count = len(normalize_transcript(expected).split())
        return 0 < word_count <= SHORT_CONTEXT_MAX_WORDS

    def verify_repeated_short(
        self,
        expected: str,
        wav_path: Path,
        *,
        confirmation: bool = False,
    ) -> dict[str, Any]:
        if not self.can_verify_repeated_short(expected):
            raise ValueError("Repeated short-context ASR only supports one to five words")
        if not self.load():
            return {
                "passed": False,
                "verdict": ASR_INCONCLUSIVE,
                "transcript": "",
                "similarity": 0.0,
                "wer": 1.0,
                "reason": "ASR_NOT_RUN",
                "repairable": False,
                "severe": False,
            }
        audio = load_audio_for_whisper(wav_path)
        gap = np.zeros(
            int(round(WHISPER_SAMPLE_RATE * SHORT_CONTEXT_GAP_SECONDS)),
            dtype=np.float32,
        )
        pieces: list[np.ndarray] = []
        for index in range(SHORT_CONTEXT_REPEAT_COUNT):
            pieces.append(audio)
            if index + 1 < SHORT_CONTEXT_REPEAT_COUNT:
                pieces.append(gap)
        repeated_audio = np.concatenate(pieces).astype(np.float32, copy=False)
        transcript = self._transcribe_audio(
            repeated_audio,
            repeated_audio.size / WHISPER_SAMPLE_RATE,
            confirmation=confirmation,
        )
        repeated_expected = " ".join([expected] * SHORT_CONTEXT_REPEAT_COUNT)
        result = self._evaluate_transcript(
            repeated_expected,
            transcript,
            repeated_audio.size / WHISPER_SAMPLE_RATE,
        )
        if result["passed"]:
            result["reason"] = "ASR_REPEATED_SHORT_PASS"
        return result

    def verify(
        self,
        expected: str,
        wav_path: Path,
        *,
        confirmation: bool = False,
    ) -> dict[str, Any]:
        normalized_expected = normalize_transcript(expected)
        word_count = len(normalized_expected.split())
        if not normalized_expected:
            return {
                "passed": True,
                "verdict": ASR_PASS,
                "transcript": "",
                "similarity": 1.0,
                "wer": 0.0,
                "reason": "NON_LEXICAL_SKIP",
                "repairable": False,
                "severe": False,
            }
        if word_count < int(self.settings.get("min_words", 3)) and not self.settings.get("verify_short_dialogue", True):
            return {
                "passed": False,
                "verdict": ASR_INCONCLUSIVE,
                "transcript": "",
                "similarity": 1.0,
                "wer": 0.0,
                "reason": "short_skip",
                "repairable": False,
                "severe": False,
            }
        if not self.load():
            return {
                "passed": False,
                "verdict": ASR_INCONCLUSIVE,
                "transcript": "",
                "similarity": 0.0,
                "wer": 1.0,
                "reason": "ASR_NOT_RUN",
                "repairable": False,
                "severe": False,
            }
        self._last_transcription_timeline_impossible = False
        try:
            transcript = (
                self.transcribe(wav_path, confirmation=True)
                if confirmation
                else self.transcribe(wav_path)
            )
        except Exception as exc:  # noqa: BLE001
            self.log(f"Whisper inference lỗi cho {wav_path.name}: {exc}")
            if self.settings.get("required", False) or self.settings.get("failure_policy") == "fail":
                raise
            return {
                "passed": False,
                "verdict": ASR_INCONCLUSIVE,
                "transcript": "",
                "similarity": 0.0,
                "wer": 1.0,
                "reason": "ASR_ERROR",
                "repairable": False,
                "severe": False,
            }
        try:
            duration_seconds = float(sf.info(wav_path).duration)
        except (RuntimeError, TypeError, ValueError):
            duration_seconds = 0.0
        return self._evaluate_transcript(expected, transcript, duration_seconds)
