from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .io_utils import natural_key, read_text_auto, sha256_file, sha256_text


QUOTE_PATTERN = re.compile(r"([“\"][^”\"]{1,1600}[”\"])", re.DOTALL)
SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?…;:])\s+")


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


def segment_chapter_text(chapter_index: int, text: str, max_chars: int = 340) -> list[dict[str, Any]]:
    text = normalize_text(text)
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", text) if part.strip()]
    rows: list[dict[str, Any]] = []

    def append_piece(piece: str, hint: str, paragraph_index: int) -> None:
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

    for paragraph_index, paragraph in enumerate(paragraphs):
        lines = [line.strip() for line in paragraph.splitlines() if line.strip()]
        for line in lines:
            if re.match(r"^[—–-]\s*\S", line):
                append_piece(line, "dialogue", paragraph_index)
                continue
            cursor = 0
            matches = list(QUOTE_PATTERN.finditer(line))
            if not matches:
                hint = "thought" if line.startswith("(") and line.endswith(")") else "narration"
                append_piece(line, hint, paragraph_index)
                continue
            for match in matches:
                if match.start() > cursor:
                    append_piece(line[cursor : match.start()], "narration", paragraph_index)
                append_piece(match.group(1), "dialogue", paragraph_index)
                cursor = match.end()
            if cursor < len(line):
                append_piece(line[cursor:], "narration", paragraph_index)
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
                "output_mp3": str(chapters_output_dir / f"{index:05d}_{path.stem}.mp3"),
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
    text = read_text_auto(Path(chapter["input_path"]))
    return segment_chapter_text(int(chapter["chapter_index"]), text, max_chars=max_chars)
