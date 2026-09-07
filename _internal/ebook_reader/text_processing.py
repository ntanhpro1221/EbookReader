from __future__ import annotations

import re
import unicodedata
from pathlib import Path
from typing import Any

from .io_utils import decode_text_bytes, natural_key, sha256_bytes, sha256_file, sha256_text, slugify


QUOTE_PATTERN = re.compile(r"([“\"][^”\"]{1,1600}[”\"])", re.DOTALL)
THOUGHT_QUOTE_PATTERN = re.compile(r"(‘[^’]{1,1600}’)", re.DOTALL)
CURLY_QUOTE_SPECS = (
    ("“", "”", "dialogue"),
    ("‘", "’", "thought"),
)
QUOTE_CLOSING_MARKS = {"”", "’", '"'}
INLINE_REFERENCE_MARKER_PATTERN = re.compile(r"\[\s*note\d+\s*\]", re.IGNORECASE)
SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?…;:])\s+")
CLAUSE_BOUNDARY = re.compile(r"(?<=[.!?…;:,])\s+")
SENTENCE_SPLIT_STRATEGY = "sentence_v1"
SENTENCE_SPLIT_MAX_CHARS = 170
CLAUSE_SPLIT_STRATEGY = "clause_v1"
CLAUSE_SPLIT_MAX_CHARS = 120
CLAUSE_SPLIT_MIN_TAIL_CHARS = 32
SPLIT_STRATEGY_FIELD = "split_strategy"
SPLIT_MAX_CHARS_FIELD = "split_max_chars"
SPLIT_MAX_CHARS_BY_STRATEGY = {
    SENTENCE_SPLIT_STRATEGY: SENTENCE_SPLIT_MAX_CHARS,
    CLAUSE_SPLIT_STRATEGY: CLAUSE_SPLIT_MAX_CHARS,
}
SPEECH_VERB_PATTERN = re.compile(
    r"\b(?:nói|hỏi|đáp|trả lời|quát|hét|gào|thì thầm|lẩm bẩm|kêu|bảo|ra lệnh|cười)\b",
    re.IGNORECASE,
)
PUNCTUATION_BREAK_MS = {
    ",": 180,
    ".": 320,
    "…": 600,
}
VOCAL_CUE_SPOKEN_FORMS = {
    "cười": "Ha ha...",
    "chuckle": "Ha ha...",
    "thở dài": "Hầy...",
    "sigh": "Hầy...",
    "hắng giọng": "Khụ khụ...",
    "clear throat": "Khụ khụ...",
}
VOCAL_CUE_PATTERN = re.compile(
    r"\[(cười|chuckle|thở\s+dài|sigh|hắng\s+giọng|clear\s+throat)\]",
    re.IGNORECASE,
)
STRETCHED_SIGH_PATTERN = re.compile(r"(?<!\w)ha+i+z+(?!\w)", re.IGNORECASE)
STRETCHED_HUM_PATTERN = re.compile(r"(?<!\w)(?:hừ+m+|h+m+)(?!\w)", re.IGNORECASE)
COMPACT_VOCALIZATION_PATTERN = re.compile(
    r"(?<!\w)(?P<syllable>ha|he|hi|hu)(?P=syllable){1,7}(?!\w)",
    re.IGNORECASE,
)
STANDALONE_GASP_PATTERN = re.compile(
    r"^(?P<prefix>\s*[“\"'‘—–-]?\s*)ha(?:…|\.{2,})(?P<suffix>\s*[”\"'’]?\s*)$",
    re.IGNORECASE,
)
STRETCHED_OPEN_VOWEL_PATTERN = re.compile(
    r"(?<!\w)(?P<vowel>[aeiouyưăâêôơ])(?P=vowel){2,}h*(?!\w)",
    re.IGNORECASE,
)
SPOKEN_WORD_PATTERN = re.compile(r"[A-Za-zÀ-ỹĐđ]+")
SPEAKABLE_TOKEN_PATTERN = re.compile(r"[^\W_]+", re.UNICODE)
# The r/g cries of pain and effort - argh, aargh, ugh - which the vowel-and-h forms above
# cannot reach. Left out, they were taken for English names and locked as transliterations:
# "Argh" was read "A-rag", Whisper naturally failed to hear that in a scream, and the
# resulting anchor mismatch blocked a chapter. Twenty-four segments across the corpus.
#
# No Vietnamese word ends in -gh, so this cannot swallow one: ghe and nghe carry a vowel
# after the digraph and the token must end at the h.
PAIN_CRY_PATTERN = r"a+r*g+h*|u+r*g+h*|g+r+h*"
# The same cries, to be replaced rather than recognised. "Argh" is English on the page
# and a Vietnamese voice has nothing to say for it: handed the letters, the model ran to
# its frame ceiling on a two-second scream, the only take in 948 segments to do so, and
# the ceiling then counted as evidence the take was cut off. Vietnamese writes a cry of
# pain "Á".
PAIN_CRY_SPOKEN_PATTERN = re.compile(
    r"(?<![\w])(?:" + PAIN_CRY_PATTERN + r")(?![\w])",
    re.IGNORECASE,
)
PAIN_CRY_SPOKEN_FORM = "\u00c1"
FOLDED_VOCALIZATION_PATTERN = re.compile(
    r"^(?:a+h*|u+h*|o+h*|you|ha+|he+|hi+|hu+|huc|hac|hay|hum|hm+|khu+|ho+|"
    + PAIN_CRY_PATTERN
    + r"|[a-z])$",
    re.IGNORECASE,
)
# A held sound written out: the same vowel three times or more, anywhere in the token.
# Neither language repeats a vowel that many times, and the book bears it out - of 11,524
# distinct tokens across both books, 87 match and every one is a cry, a shout or a word
# stretched out ("Khôôôông", "Saaaaaaam"). The only other things that match are Roman
# numerals, which have their own guard.
#
# Narrower versions kept missing: anchoring at the start missed "Tuuuuu", and allowing only
# consonants in front missed "THWAAAM", "Booyaaa" and "ARAAAAH".
STRETCHED_SOUND_TOKEN_PATTERN = re.compile(
    r"(?P<vowel>[aeiouyăâêôơư])(?P=vowel){2,}",
    re.IGNORECASE,
)
# A regnal number, not a held sound. "III" folds to a run of one vowel and would otherwise
# be read as a scream; the book says "Benedict III" 164 times. Uppercase only, so a
# stretched "Iiii" is still a sound.
ROMAN_NUMERAL_TOKEN_PATTERN = re.compile(r"^[IVXLCDM]+$")
ROMAN_NUMERAL_VALUES = {
    "I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000,
}
# Vietnamese for the numbers a regnal name reaches. Beyond twenty the pattern is regular and
# built from these; nothing in a book needs more than that.
VIETNAMESE_UNITS = (
    "không", "một", "hai", "ba", "bốn", "năm", "sáu", "bảy", "tám", "chín",
)


# Ký tự sách có mà giọng đọc không đọc được. Chúng đi thẳng tới TTS và không tạo ra khoảng
# nghỉ nào, nên một chú thích bị nuốt vào thành một thành phần của câu: chủ sách nghe
# "Thường (Common) (C) » Hiếm" ra thành "Thường Common C hiếm" - dính liền, không nhịp.
#
# Có hai loại, và loại thứ hai là chỗ dễ làm sai:
#   - Ký tự MANG NGHĨA phải thành CHỮ. "↓ 1.000 Đơn vị" nghĩa là *giảm* 1.000 đơn vị; bỏ nó
#     đi là bỏ mất nghĩa của câu.
#   - Ký tự NGĂN CÁCH phải thành DẤU PHẨY, không được bỏ trần. Bỏ trần thì chú thích lẫn vào
#     câu văn như một thành phần bình thường, đúng cái lỗi đang phải sửa.
SPOKEN_SYMBOL_WORDS = {
    "↓": "giảm",
    "↑": "tăng",
}
# Ngoặc và mũi tên ngăn cách: thành dấu phẩy để giọng nghỉ đúng một nhịp trước và sau phần
# được ngăn. `,` và `()` đều đã nằm trong PAUSE_GROUP_PATTERN của audio_io nên số nhóm nghỉ
# không đổi - thay đổi duy nhất là giọng NGHỈ THẬT ở chỗ thước đo vốn đã luôn tính là có
# nghỉ. Trên c00009_s0000018 thước đo trừ 6,90s khoảng lặng của 11,80s âm thanh mà giọng
# không hề nghỉ, thổi nhịp từ 10,76 lên 25,92 chars/s và vượt cận trên 24,5.
# `|` is here because the voice reads it as mathematics. alpha.55 chapter 011 lists skills as
# "Hỏa Cầu (Fireball) (Thường) || Sương Giáng (Mistfall) …" and Whisper transcribed the take
# as "Fireball thường giá trị tuyệt đối của xương dáng" - the voice said "absolute value of"
# between every entry. In this book `||` separates list items; a pause is what it means.
# 24 of them across 4 chapters, so rare, and wrong every single time.
SPOKEN_SEPARATORS = "»«›‹→⇒▸▶►([{)]}|"
# Đầu dòng đánh dấu mục, không ngăn cách gì với thứ đứng trước vì không có gì đứng trước.
SPOKEN_DROPPED = "•▪◦*"
_SPOKEN_COMMA_RUN = re.compile(r"(?:\s*,)+(?=\s*,)")
_SPOKEN_SPACE_RUN = re.compile(r"[ \t]{2,}")
# A comma this introduced has to attach to the word before it. "C , B" puts the silence in
# the wrong place, which is the defect being fixed rather than a cosmetic detail.
_SPOKEN_SPACE_BEFORE_PUNCT = re.compile(r"\s+([,.!?;:…])")
# A separator immediately before real punctuation is a pause with nothing after it -
# "(Spirit Essence Units)." would otherwise close on a hanging comma.
#
# Deliberately NOT anchored at the end of the string, and there is no matching rule for the
# start, because this function must leave a *fragment* of its own output alone - see
# spoken_symbols_to_words. A boundary is the one piece of context a fragment does not share
# with the text it came from.
_SPOKEN_TRAILING_COMMA = re.compile(r",(\s*[.!?…:;])")
# A slash between words is an alternative and wants the pause a comma gives. Between digits
# it is a fraction, and Vietnamese reads that slash aloud as "trên" - "8.5/10" is "tám phẩy
# năm trên mười", which is right. The voice applies the fraction reading to both, so
# "Mạnh hơn / khó tìm hơn" came out "mạnh hơn TRÊN khó tìm hơn": the symbol stopped being a
# separator and became a word inside the sentence, which is the exact thing the owner
# refused - "cái đó nó bị lẫn vào làm một thành phần trong câu văn là không được".
#
# Letters on both sides only, so the book's one real fraction keeps its reading. Checked
# across all 948 segments: 8 word/word, 1 digit/digit.
_SPOKEN_WORD_SLASH = re.compile(r"(?<=[^\W\d_])\s*/\s*(?=[^\W\d_])", re.UNICODE)
# Separators sitting at either end of the whole text are removed before conversion rather
# than trimmed away as commas afterwards. Same result, but stable: a fragment of converted
# text contains no separators at all, so this can never fire a second time. ↓ and ↑ are not
# in here - they mean "giảm" and "tăng", and a word does not stop meaning something because
# it happens to start the line.
_SPOKEN_BOUNDARY_TRIM = SPOKEN_SEPARATORS + SPOKEN_DROPPED + " \t\r\n"


def _spoken_symbols_in_span(text: str) -> str:
    result = []
    for character in text:
        if character in SPOKEN_SYMBOL_WORDS:
            result.append(f" {SPOKEN_SYMBOL_WORDS[character]} ")
        elif character in SPOKEN_SEPARATORS:
            result.append(", ")
        elif character in SPOKEN_DROPPED:
            result.append("")
        else:
            result.append(character)
    return "".join(result)


def spoken_symbols_to_words(text: str) -> str:
    """Turn characters the voice cannot say into words it can, or into a pause.

    The book's own text is never changed - this is only what gets handed to the voice, and
    to the transcript comparison that has to match it.

    Square brackets carry two different jobs in this book and only one of them is a
    separator. "[A-rank]" is an annotation the voice should pause around; "[thở dài]" is a
    stage direction normalize_vocalizations_for_tts turns into an actual breath, "Hầy...".
    Converting the second kind to commas destroys the cue before that function ever sees it,
    which is what the anchor tests caught. Vocal cues are therefore passed through untouched
    and normalized later, as they always were.

    **Stable on its own output, including fragments of it.** The repair path splits a long
    segment into pieces of the already-converted text and then re-derives each piece to check
    the boundary text did not move; a rule that reads the start or end of the string sees a
    different context in a piece than in the text it came from, and the check fails. alpha.45
    died that way at chapter 2: "(Legendary)" became ", Legendary," which pushed the segment
    to 174 characters over a 170 cap, so the splitter cut at a comma this function had just
    created, and the second pass trimmed that now-trailing comma back off.

    So nothing here is anchored to a boundary. Separators at either end are removed *before*
    conversion instead, which reaches the same tidy result - a fragment of converted text has
    no separators left in it, so that rule cannot fire twice.
    """
    source = str(text)
    spans: list[tuple[str, bool]] = []
    position = 0
    for match in VOCAL_CUE_PATTERN.finditer(source):
        spans.append((source[position:match.start()], False))
        spans.append((match.group(0), True))
        position = match.end()
    spans.append((source[position:], False))
    # Trim the two ends of the whole text, never a vocal cue: the brackets delimiting
    # "[thở dài]" are separators too, and eating the opening one leaves a cue the later
    # vocalization pass no longer recognises - it read out "thở dài," as words.
    if not spans[0][1]:
        spans[0] = (spans[0][0].lstrip(_SPOKEN_BOUNDARY_TRIM), False)
    if not spans[-1][1]:
        spans[-1] = (spans[-1][0].rstrip(_SPOKEN_BOUNDARY_TRIM), False)
    out = "".join(
        span if is_cue else _spoken_symbols_in_span(span) for span, is_cue in spans
    )
    out = _SPOKEN_WORD_SLASH.sub(", ", out)
    out = _SPOKEN_SPACE_BEFORE_PUNCT.sub(r"\1", out)
    out = _SPOKEN_COMMA_RUN.sub("", out)
    out = _SPOKEN_TRAILING_COMMA.sub(r"\1", out)
    out = _SPOKEN_SPACE_RUN.sub(" ", out)
    return out.strip()


def roman_numeral_value(token: str) -> int | None:
    """The number a Roman numeral spells, or None when the token is not one.

    A single letter is only ever read as one when it is "I". This book ranks things
    "C » B » A » S", so a lone C or D or M is a grade rather than a hundred, and no
    monarch is numbered V without the letters around it to say so.
    """
    if ROMAN_NUMERAL_TOKEN_PATTERN.fullmatch(token) is None:
        return None
    if len(token) == 1 and token != "I":
        return None
    total = 0
    previous = 0
    for character in reversed(token):
        value = ROMAN_NUMERAL_VALUES[character]
        total += -value if value < previous else value
        previous = max(previous, value)
    return total or None


def vietnamese_number_words(value: int) -> str:
    """A number written the way it is said, for the numerals a book carries.

    Vietnamese changes the unit inside a compound: 15 is "mười lăm", not "mười năm", and
    from twenty up 1 becomes "mốt" and 4 "tư".
    """
    if value < 0:
        raise ValueError(value)
    if value < 10:
        return VIETNAMESE_UNITS[value]
    if value < 20:
        unit = value - 10
        if unit == 0:
            return "mười"
        return "mười " + ("lăm" if unit == 5 else VIETNAMESE_UNITS[unit])
    if value < 100:
        tens, unit = divmod(value, 10)
        head = f"{VIETNAMESE_UNITS[tens]} mươi"
        if unit == 0:
            return head
        if unit == 1:
            return head + " mốt"
        if unit == 4:
            return head + " tư"
        if unit == 5:
            return head + " lăm"
        return f"{head} {VIETNAMESE_UNITS[unit]}"
    if value < 1000:
        hundreds, rest = divmod(value, 100)
        head = f"{VIETNAMESE_UNITS[hundreds]} trăm"
        if rest == 0:
            return head
        # Vietnamese says "lẻ" for the empty tens: 105 is "một trăm lẻ năm".
        if rest < 10:
            return f"{head} lẻ {VIETNAMESE_UNITS[rest]}"
        return f"{head} {vietnamese_number_words(rest)}"
    raise ValueError(f"number beyond what a book numbers things with: {value}")
MAX_VOCALIZATION_REPETITIONS = 4


def normalize_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("\u00a0", " ").replace("\u200b", "")
    text = INLINE_REFERENCE_MARKER_PATTERN.sub("", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n[ \t]+", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def split_long_text(text: str, max_chars: int) -> list[str]:
    text = text.strip()
    if not text:
        return []
    if len(text) <= max_chars:
        return [text]
    result: list[str] = []
    current = ""
    for sentence in SENTENCE_BOUNDARY.split(text):
        sentence = sentence.strip()
        if not sentence:
            continue
        candidate = f"{current} {sentence}".strip()
        if len(candidate) <= max_chars:
            current = candidate
            continue
        if current:
            result.append(current)
            current = ""
        while len(sentence) > max_chars:
            cut = sentence.rfind(" ", 0, max_chars)
            if cut < max_chars // 2:
                cut = max_chars
            result.append(sentence[:cut].strip())
            sentence = sentence[cut:].strip()
        current = sentence
    if current:
        result.append(current)
    return result


def _split_unit_at_word_boundaries(text: str, max_chars: int) -> list[str]:
    words = text.split()
    if not words:
        return []
    chunks: list[str] = []
    current = ""
    for word in words:
        if len(word) > max_chars:
            raise ValueError(
                "clause split cannot preserve an unbroken token within max_chars"
            )
        candidate = f"{current} {word}".strip()
        if not current or len(candidate) <= max_chars:
            current = candidate
            continue
        chunks.append(current)
        current = word
    if current:
        chunks.append(current)
    return chunks


def _rebalance_short_clause_tail(
    part_units: list[list[str]],
    max_chars: int,
) -> list[list[str]]:
    if len(part_units) < 2:
        return part_units
    minimum_tail = min(CLAUSE_SPLIT_MIN_TAIL_CHARS, max_chars // 3)
    while len(" ".join(part_units[-1])) < minimum_tail:
        if len(part_units[-2]) < 2:
            break
        moved_unit = part_units[-2][-1]
        next_tail = " ".join([moved_unit, *part_units[-1]])
        next_previous = " ".join(part_units[-2][:-1])
        if len(next_tail) > max_chars or len(next_previous) < minimum_tail:
            break
        part_units[-2].pop()
        part_units[-1].insert(0, moved_unit)
    return part_units


def split_text_by_clauses(text: str, max_chars: int) -> list[str]:
    text = text.strip()
    if not text:
        return []
    if max_chars <= 0:
        raise ValueError("clause split max_chars must be positive")
    if len(text) <= max_chars:
        return [text]

    clauses = [clause.strip() for clause in CLAUSE_BOUNDARY.split(text) if clause.strip()]
    units: list[str] = []
    for clause in clauses:
        if len(clause) <= max_chars:
            units.append(clause)
        else:
            units.extend(_split_unit_at_word_boundaries(clause, max_chars))

    part_units: list[list[str]] = []
    current_units: list[str] = []
    for unit in units:
        candidate = " ".join([*current_units, unit])
        if not current_units or len(candidate) <= max_chars:
            current_units.append(unit)
            continue
        part_units.append(current_units)
        current_units = [unit]
    if current_units:
        part_units.append(current_units)
    part_units = _rebalance_short_clause_tail(part_units, max_chars)
    parts = [" ".join(part) for part in part_units]
    if " ".join(parts) != text:
        raise RuntimeError("clause-aware split changed the source text")
    return parts


def split_text_for_strategy(text: str, strategy: str) -> tuple[list[str], int]:
    try:
        max_chars = SPLIT_MAX_CHARS_BY_STRATEGY[strategy]
    except KeyError as exc:
        raise ValueError(f"Unsupported split strategy: {strategy}") from exc
    parts = (
        split_text_by_clauses(text, max_chars)
        if strategy == CLAUSE_SPLIT_STRATEGY
        else split_long_text(text, max_chars)
    )
    return parts, max_chars


def _split_long(text: str, max_chars: int) -> list[str]:
    return split_long_text(text, max_chars)


def has_spoken_content(text: str) -> bool:
    return any(char.isalnum() for char in text)


def _speakable_tokens(text: str) -> list[str]:
    return SPEAKABLE_TOKEN_PATTERN.findall(text)


def _fold_vocalization_token(token: str) -> str:
    decomposed = unicodedata.normalize("NFD", token.casefold().replace("đ", "d"))
    return "".join(char for char in decomposed if unicodedata.category(char) != "Mn")


def _is_vocalization_token(token: str) -> bool:
    if ROMAN_NUMERAL_TOKEN_PATTERN.fullmatch(token) is not None:
        return False
    folded = _fold_vocalization_token(token)
    return (
        FOLDED_VOCALIZATION_PATTERN.fullmatch(folded) is not None
        or COMPACT_VOCALIZATION_PATTERN.fullmatch(folded) is not None
        or STRETCHED_SOUND_TOKEN_PATTERN.search(token) is not None
    )


def is_vocalization_only(text: str) -> bool:
    tokens = SPOKEN_WORD_PATTERN.findall(text)
    return bool(tokens) and all(_is_vocalization_token(token) for token in tokens)


def is_standalone_ha_gasp(text: str) -> bool:
    return STANDALONE_GASP_PATTERN.fullmatch(text) is not None


def normalize_vocalizations_for_tts(text: str) -> str:
    """Turn stylized vocal spellings into ordinary pronounceable Vietnamese text.

    The source text remains untouched in SQLite. This function only prepares the
    copy sent to VieNeu and deliberately avoids the model's experimental
    non-verbal cue tokens.
    """

    def replace_cue(match: re.Match[str]) -> str:
        key = " ".join(match.group(1).casefold().split())
        return VOCAL_CUE_SPOKEN_FORMS[key]

    def separate_compact_vocalization(match: re.Match[str]) -> str:
        syllable = match.group("syllable").casefold()
        count = min(
            MAX_VOCALIZATION_REPETITIONS,
            len(match.group(0)) // len(match.group("syllable")),
        )
        return " ".join([syllable] * count).capitalize()

    def separate_stretched_vowel(match: re.Match[str]) -> str:
        vowel = match.group("vowel").casefold()
        return f"{vowel.upper()}... {vowel}"

    gasp = STANDALONE_GASP_PATTERN.fullmatch(text)
    if gasp is not None:
        return f"{gasp.group('prefix')}Ha ha.{gasp.group('suffix')}"

    result = VOCAL_CUE_PATTERN.sub(replace_cue, text)
    result = PAIN_CRY_SPOKEN_PATTERN.sub(PAIN_CRY_SPOKEN_FORM, result)
    result = STRETCHED_SIGH_PATTERN.sub("Hầy", result)
    result = STRETCHED_HUM_PATTERN.sub("Hừm", result)
    result = COMPACT_VOCALIZATION_PATTERN.sub(separate_compact_vocalization, result)
    result = STRETCHED_OPEN_VOWEL_PATTERN.sub(separate_stretched_vowel, result)
    return re.sub(r"\.{4,}", "...", result)


def _quoted_span_is_dialogue(line: str, match: re.Match[str]) -> bool:
    quoted = match.group(1).strip()
    inner = quoted[1:-1].strip()
    if not has_spoken_content(inner):
        return False
    if line.strip() == quoted:
        return True
    if any(mark in inner for mark in ("?", "!", "…")) or inner.endswith("."):
        return True
    before = line[: match.start()].rstrip()
    after = line[match.end() :].lstrip()
    if before.endswith(":"):
        return True
    context = f"{before[-100:]} {after[:100]}"
    return SPEECH_VERB_PATTERN.search(context) is not None


def _join_fragments(left: str, right: str) -> str:
    if not left:
        return right
    if not right:
        return left
    if right[0] in ",.;:!?…)]}”":
        return left + right
    return f"{left} {right}"


def _line_pieces(line: str) -> list[tuple[str, str]]:
    if re.match(r"^[—–-]\s*\S", line):
        return [(line, "dialogue")]
    matches = [
        (match, "dialogue" if _quoted_span_is_dialogue(line, match) else "narration")
        for match in QUOTE_PATTERN.finditer(line)
    ]
    matches.extend((match, "thought") for match in THOUGHT_QUOTE_PATTERN.finditer(line))
    matches.sort(key=lambda item: (item[0].start(), -item[0].end()))
    non_overlapping: list[tuple[re.Match[str], str]] = []
    occupied_until = -1
    for match, hint in matches:
        if match.start() < occupied_until:
            continue
        non_overlapping.append((match, hint))
        occupied_until = match.end()
    matches = non_overlapping
    if not matches:
        hint = "thought" if line.startswith("(") and line.endswith(")") else "narration"
        return [(line, hint)]

    raw: list[tuple[str, str]] = []
    cursor = 0
    for match, hint in matches:
        if match.start() > cursor:
            raw.append((line[cursor : match.start()], "narration"))
        raw.append((match.group(1), hint))
        cursor = match.end()
    if cursor < len(line):
        raw.append((line[cursor:], "narration"))

    merged: list[tuple[str, str]] = []
    pending_prefix = ""
    for text, hint in raw:
        text = text.strip()
        if not text:
            continue
        if not has_spoken_content(text):
            if merged:
                previous_text, previous_hint = merged[-1]
                merged[-1] = (_join_fragments(previous_text, text), previous_hint)
            else:
                pending_prefix = _join_fragments(pending_prefix, text)
            continue
        if pending_prefix:
            text = _join_fragments(pending_prefix, text)
            pending_prefix = ""
        if merged and merged[-1][1] == hint:
            previous_text, _ = merged[-1]
            merged[-1] = (_join_fragments(previous_text, text), hint)
        else:
            merged.append((text, hint))
    return merged


def _balanced_quote_spans(line: str) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    for opening_mark, closing_mark, _ in CURLY_QUOTE_SPECS:
        cursor = 0
        while cursor < len(line):
            opening_index = line.find(opening_mark, cursor)
            if opening_index < 0:
                break
            closing_index = line.find(closing_mark, opening_index + 1)
            if closing_index < 0:
                cursor = opening_index + 1
                continue
            spans.append((opening_index, closing_index + 1))
            cursor = closing_index + 1
    ascii_quote_positions = [index for index, char in enumerate(line) if char == '"']
    spans.extend(
        (opening_index, closing_index + 1)
        for opening_index, closing_index in zip(
            ascii_quote_positions[0::2],
            ascii_quote_positions[1::2],
        )
    )
    return spans


def _unmatched_curly_quote_openings(line: str) -> list[tuple[int, str, str]]:
    balanced_spans = _balanced_quote_spans(line)
    unmatched: list[tuple[int, str, str]] = []
    for opening_mark, closing_mark, hint in CURLY_QUOTE_SPECS:
        cursor = 0
        while cursor < len(line):
            opening_index = line.find(opening_mark, cursor)
            if opening_index < 0:
                break
            closing_index = line.find(closing_mark, opening_index + 1)
            if closing_index >= 0:
                cursor = closing_index + 1
                continue
            nested_in_balanced_quote = any(
                start < opening_index < end
                for start, end in balanced_spans
            )
            if not nested_in_balanced_quote:
                unmatched.append((opening_index, closing_mark, hint))
            cursor = opening_index + 1
    return unmatched


def _terminal_alternative_quote_closing(line: str, expected_closing_mark: str) -> int:
    stripped = line.rstrip()
    if not stripped:
        return -1
    terminal_mark = stripped[-1]
    if terminal_mark == expected_closing_mark or terminal_mark not in QUOTE_CLOSING_MARKS:
        return -1
    return len(stripped) - 1


def _line_pieces_with_quote_state(
    line: str,
    quote_state: tuple[str, str] | None,
) -> tuple[list[tuple[str, str]], tuple[str, str] | None]:
    if quote_state is not None:
        hint, closing_mark = quote_state
        closing_index = line.find(closing_mark)
        if closing_index < 0:
            alternative_closing_index = _terminal_alternative_quote_closing(
                line,
                closing_mark,
            )
            if alternative_closing_index >= 0:
                return [(line[: alternative_closing_index + 1], hint)], None
            return [(line, hint)], quote_state
        pieces = [(line[: closing_index + 1], hint)]
        remainder = line[closing_index + 1 :].strip()
        if not remainder:
            return pieces, None
        tail, next_state = _line_pieces_with_quote_state(remainder, None)
        return pieces + tail, next_state

    unmatched_openings = _unmatched_curly_quote_openings(line)
    ascii_quote_positions = [index for index, char in enumerate(line) if char == '"']
    if len(ascii_quote_positions) % 2:
        opening_index = ascii_quote_positions[-1]
        nested_in_balanced_quote = any(
            start < opening_index < end
            for start, end in _balanced_quote_spans(line)
        )
        if not nested_in_balanced_quote:
            unmatched_openings.append((opening_index, '"', "dialogue"))
    if not unmatched_openings:
        return _line_pieces(line), None

    opening_index, closing_mark, hint = min(unmatched_openings, key=lambda item: item[0])
    pieces = _line_pieces(line[:opening_index].strip()) if opening_index > 0 else []
    alternative_closing_index = _terminal_alternative_quote_closing(line, closing_mark)
    if alternative_closing_index > opening_index:
        quoted = line[opening_index : alternative_closing_index + 1].strip()
        if quoted:
            pieces.append((quoted, hint))
        remainder = line[alternative_closing_index + 1 :].strip()
        if remainder:
            tail, next_state = _line_pieces_with_quote_state(remainder, None)
            return pieces + tail, next_state
        return pieces, None
    quoted = line[opening_index:].strip()
    if quoted:
        pieces.append((quoted, hint))
    return pieces, (hint, closing_mark)


def _punctuation_break_ms(text: str) -> int:
    return max(
        (duration for mark, duration in PUNCTUATION_BREAK_MS.items() if mark in text),
        default=230,
    )


def segment_chapter_text(chapter_index: int, text: str, max_chars: int = 340) -> list[dict[str, Any]]:
    text = normalize_text(text)
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", text) if part.strip()]
    rows: list[dict[str, Any]] = []

    def append_piece(piece: str, hint: str, paragraph_index: int) -> None:
        if not has_spoken_content(piece):
            if rows:
                rows[-1]["break_ms"] = max(int(rows[-1]["break_ms"]), _punctuation_break_ms(piece))
            return
        for chunk in _split_long(piece.strip(), max_chars):
            seq = len(rows)
            stable_id = f"c{chapter_index:05d}_s{seq:07d}_{sha256_text(chunk)[:12]}"
            rows.append(
                {
                    "stable_id": stable_id,
                    "seq": seq,
                    "paragraph_index": paragraph_index,
                    "break_ms": 170 if hint == "dialogue" else (210 if hint == "thought" else 230),
                    "text": chunk,
                    "text_sha256": sha256_text(chunk),
                    "kind_hint": hint,
                    "kind": hint,
                    "speaker": "NARRATOR" if hint == "narration" else "UNKNOWN",
                    "status": "pending",
                }
            )

    quote_state: tuple[str, str] | None = None
    for paragraph_index, paragraph in enumerate(paragraphs):
        lines = [line.strip() for line in paragraph.splitlines() if line.strip()]
        for line in lines:
            pieces, quote_state = _line_pieces_with_quote_state(line, quote_state)
            if not pieces and rows:
                rows[-1]["break_ms"] = max(int(rows[-1]["break_ms"]), _punctuation_break_ms(line))
            for piece, hint in pieces:
                append_piece(piece, hint, paragraph_index)
    if quote_state is not None:
        hint, closing_mark = quote_state
        raise RuntimeError(
            f"Unclosed {hint} quote at the end of chapter {chapter_index}; "
            f"expected {closing_mark!r}"
        )
    for index, row in enumerate(rows):
        if index + 1 >= len(rows):
            row["break_ms"] = 0
        elif rows[index + 1]["paragraph_index"] != row["paragraph_index"]:
            row["break_ms"] = max(int(row["break_ms"]), 380)
    source_tokens = _speakable_tokens(text)
    segmented_tokens = [token for row in rows for token in _speakable_tokens(str(row["text"]))]
    if segmented_tokens != source_tokens:
        raise RuntimeError("Segmentation changed the spoken token sequence")
    return rows


def build_chapter_manifest(input_files: list[Path], chapters_output_dir: Path) -> list[dict[str, Any]]:
    paths = sorted((p.resolve() for p in input_files), key=lambda p: natural_key(p.name))
    manifest: list[dict[str, Any]] = []
    for index, path in enumerate(paths, 1):
        if not path.exists() or not path.is_file():
            raise FileNotFoundError(path)
        if path.suffix.lower() != ".txt":
            raise ValueError(f"Only .txt input is supported: {path}")
        manifest.append(
            {
                "chapter_index": index,
                "title": path.stem,
                "input_path": str(path),
                "input_sha256": sha256_file(path),
                "input_size": path.stat().st_size,
                "output_mp3": str(chapters_output_dir / f"{index:05d}_{slugify(path.stem, 72)}.mp3"),
            }
        )
    return manifest


def input_manifest_hash(manifest: list[dict[str, Any]]) -> str:
    canonical = "\n".join(
        f"{row['chapter_index']}|{row['input_path']}|{row['input_sha256']}|{row['input_size']}"
        for row in manifest
    )
    return sha256_text(canonical)


def load_and_segment_chapter(chapter: dict[str, Any], max_chars: int) -> list[dict[str, Any]]:
    source = Path(chapter["input_path"])
    raw = source.read_bytes()
    expected_size = int(chapter["input_size"])
    expected_sha256 = str(chapter["input_sha256"])
    if len(raw) != expected_size or sha256_bytes(raw) != expected_sha256:
        raise RuntimeError(f"Source chapter changed while it was being loaded: {source}")
    text = decode_text_bytes(raw)
    return segment_chapter_text(int(chapter["chapter_index"]), text, max_chars=max_chars)
