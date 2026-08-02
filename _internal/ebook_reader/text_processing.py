from __future__ import annotations

import re
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
VOCAL_EFFECT_KIND = "vocal_effect"
TEXT_SFX_KIND = "text_sfx"
SPECIAL_AUDIO_KINDS = frozenset({VOCAL_EFFECT_KIND, TEXT_SFX_KIND})
VOCAL_EFFECT_TAGS = {
    "cười": "[cười]",
    "chuckle": "[cười]",
    "thở dài": "[thở dài]",
    "sigh": "[thở dài]",
    "hắng giọng": "[hắng giọng]",
    "clear throat": "[hắng giọng]",
}
EXPLICIT_VOCAL_EFFECT = re.compile(
    r"\[(cười|chuckle|thở\s+dài|sigh|hắng\s+giọng|clear\s+throat)\]",
    re.IGNORECASE,
)
TEXT_SFX_WORDS = frozenset(
    {
        "ầm",
        "bốp",
        "bụp",
        "bùm",
        "cạch",
        "chát",
        "choang",
        "đoàng",
        "đùng",
        "keng",
        "rắc",
        "rầm",
        "rẹt",
        "uỳnh",
        "xoảng",
    }
)


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


def _effect_core(text: str) -> str:
    value = re.sub(r"^[—–-]\s*", "", text.strip())
    value = value.strip(" \t\r\n.,!?…;:'\"“”‘’(){}")
    return re.sub(r"\s+", " ", value.casefold()).strip()


def vocal_effect_tag(text: str) -> str | None:
    explicit = EXPLICIT_VOCAL_EFFECT.fullmatch(text.strip())
    if explicit:
        return VOCAL_EFFECT_TAGS[" ".join(explicit.group(1).casefold().split())]

    core = _effect_core(text)
    compact = re.sub(r"[\s-]+", "", core)
    has_ellipsis = "…" in text or ".." in text
    if re.fullmatch(r"(?:ha){2,6}|(?:hì){2,6}|(?:hề){2,6}|(?:he){2,6}", compact):
        return "[cười]"
    if compact == "ha" and has_ellipsis:
        return "[cười]"
    if re.fullmatch(r"ha+i+z+|ha+y+z+|hầy+|hừ+m*|h+m+", compact):
        return "[thở dài]"
    if re.fullmatch(r"(?:khụ){1,4}", compact):
        return "[hắng giọng]"
    return None


def is_text_sfx(text: str) -> bool:
    core = _effect_core(text)
    words = re.findall(r"[^\W\d_]+", core, re.UNICODE)
    return bool(words) and len(words) <= 4 and all(word in TEXT_SFX_WORDS for word in words)


def audio_unit_kind(text: str) -> str | None:
    if vocal_effect_tag(text):
        return VOCAL_EFFECT_KIND
    if is_text_sfx(text):
        return TEXT_SFX_KIND
    return None


def _split_special_audio_units(text: str, hint: str) -> list[tuple[str, str]]:
    result: list[tuple[str, str]] = []
    for fragment in EXPLICIT_VOCAL_EFFECT.split(text):
        if not fragment or not fragment.strip():
            continue
        explicit_tag = VOCAL_EFFECT_TAGS.get(" ".join(fragment.casefold().split()))
        if explicit_tag:
            result.append((explicit_tag, VOCAL_EFFECT_KIND))
            continue
        if not has_spoken_content(fragment):
            continue
        sentences = [part.strip() for part in SENTENCE_BOUNDARY.split(fragment) if part.strip()]
        if len(sentences) > 1 and any(audio_unit_kind(part) for part in sentences):
            result.extend((part, audio_unit_kind(part) or hint) for part in sentences)
        else:
            result.append((fragment.strip(), audio_unit_kind(fragment) or hint))
    return result


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
        for unit, unit_hint in _split_special_audio_units(piece.strip(), hint):
            for chunk in _split_long(unit, max_chars):
                seq = len(rows)
                stable_id = f"c{chapter_index:05d}_s{seq:07d}_{sha256_text(chunk)[:12]}"
                rows.append(
                    {
                        "stable_id": stable_id,
                        "seq": seq,
                        "paragraph_index": paragraph_index,
                        "break_ms": (
                            170 if unit_hint in {"dialogue", VOCAL_EFFECT_KIND}
                            else (210 if unit_hint == "thought" else 230)
                        ),
                        "text": chunk,
                        "text_sha256": sha256_text(chunk),
                        "kind_hint": unit_hint,
                        "kind": unit_hint,
                        "speaker": "NARRATOR" if unit_hint in {"narration", TEXT_SFX_KIND} else "UNKNOWN",
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
