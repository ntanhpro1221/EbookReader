from __future__ import annotations

import re
import unicodedata
from pathlib import Path
from typing import Any

from .io_utils import decode_text_bytes, natural_key, sha256_bytes, sha256_file, sha256_text, slugify


QUOTE_PATTERN = re.compile(r"([“\"][^”\"]{1,1600}[”\"])", re.DOTALL)
THOUGHT_QUOTE_PATTERN = re.compile(r"(‘[^’]{1,1600}’)", re.DOTALL)
SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?…;:])\s+")
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
FOLDED_VOCALIZATION_PATTERN = re.compile(
    r"^(?:a+h*|u+h*|o+h*|you|ha+|he+|hi+|hu+|huc|hac|hay|hum|hm+|khu+|ho+|[a-z])$",
    re.IGNORECASE,
)
MAX_VOCALIZATION_REPETITIONS = 4


def normalize_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("\u00a0", " ").replace("\u200b", "")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n[ \t]+", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _split_long(text: str, max_chars: int) -> list[str]:
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


def has_spoken_content(text: str) -> bool:
    return any(char.isalnum() for char in text)


def _fold_vocalization_token(token: str) -> str:
    decomposed = unicodedata.normalize("NFD", token.casefold().replace("đ", "d"))
    return "".join(char for char in decomposed if unicodedata.category(char) != "Mn")


def is_vocalization_only(text: str) -> bool:
    tokens = SPOKEN_WORD_PATTERN.findall(text)
    return bool(tokens) and all(
        FOLDED_VOCALIZATION_PATTERN.fullmatch(_fold_vocalization_token(token)) is not None
        for token in tokens
    )


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
        return f"{gasp.group('prefix')}Hà... hà...{gasp.group('suffix')}"

    result = VOCAL_CUE_PATTERN.sub(replace_cue, text)
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
    matches.sort(key=lambda item: item[0].start())
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


def _line_pieces_with_quote_state(
    line: str,
    quote_state: tuple[str, str] | None,
) -> tuple[list[tuple[str, str]], tuple[str, str] | None]:
    if quote_state is not None:
        hint, closing_mark = quote_state
        closing_index = line.find(closing_mark)
        if closing_index < 0:
            return [(line, hint)], quote_state
        pieces = [(line[: closing_index + 1], hint)]
        remainder = line[closing_index + 1 :].strip()
        if not remainder:
            return pieces, None
        tail, next_state = _line_pieces_with_quote_state(remainder, None)
        return pieces + tail, next_state

    unmatched_openings: list[tuple[int, str, str]] = []
    for opening_mark, closing_mark, hint in (("“", "”", "dialogue"), ("‘", "’", "thought")):
        opening_index = line.find(opening_mark)
        if opening_index >= 0 and line.find(closing_mark, opening_index + 1) < 0:
            unmatched_openings.append((opening_index, closing_mark, hint))
    ascii_quote_positions = [index for index, char in enumerate(line) if char == '"']
    if len(ascii_quote_positions) % 2:
        unmatched_openings.append((ascii_quote_positions[-1], '"', "dialogue"))
    if not unmatched_openings:
        return _line_pieces(line), None

    opening_index, closing_mark, hint = min(unmatched_openings, key=lambda item: item[0])
    pieces = _line_pieces(line[:opening_index].strip()) if opening_index > 0 else []
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
    for index, row in enumerate(rows):
        if index + 1 >= len(rows):
            row["break_ms"] = 0
        elif rows[index + 1]["paragraph_index"] != row["paragraph_index"]:
            row["break_ms"] = max(int(row["break_ms"]), 380)
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
