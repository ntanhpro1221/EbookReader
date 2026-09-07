"""Vá text_processing.py: bộ chia đoạn tự phục hồi thay vì ném lỗi.

    python patch_quote_recovery.py <thư mục chứa ebook_reader/>
"""
import io
import sys
from pathlib import Path

root = Path(sys.argv[1])
p = root / "ebook_reader" / "text_processing.py"
s = io.open(p, encoding="utf-8").read()

OLD_WALK = '''def segment_chapter_text(chapter_index: int, text: str, max_chars: int = 340) -> list[dict[str, Any]]:
    text = normalize_text(text)
    paragraphs = [part.strip() for part in re.split(r"\\n\\s*\\n", text) if part.strip()]
    rows: list[dict[str, Any]] = []

    def append_piece(piece: str, hint: str, paragraph_index: int) -> None:'''

NEW_WALK = '''def _walk_paragraphs(
    chapter_index: int,
    paragraphs: list[str],
    max_chars: int,
    close_at_end_of: frozenset[int],
) -> tuple[list[dict[str, Any]], tuple[str, str] | None, int | None]:
    """One pass over the chapter, returning its rows and how the quote state ended.

    ``close_at_end_of`` names the paragraphs whose quote is forced shut when the paragraph
    ends - the recovery lever. The third return value is the paragraph that opened whatever
    quote is still hanging at the end, which is the paragraph that needs the lever next.
    """
    rows: list[dict[str, Any]] = []

    def append_piece(piece: str, hint: str, paragraph_index: int) -> None:'''

assert OLD_WALK in s, "khong khop dau ham"
s = s.replace(OLD_WALK, NEW_WALK)

OLD_LOOP = '''    quote_state: tuple[str, str] | None = None
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
    for index, row in enumerate(rows):'''

NEW_LOOP = '''    quote_state: tuple[str, str] | None = None
    opened_at: int | None = None
    for paragraph_index, paragraph in enumerate(paragraphs):
        lines = [line.strip() for line in paragraph.splitlines() if line.strip()]
        for line in lines:
            was_open = quote_state is not None
            pieces, quote_state = _line_pieces_with_quote_state(line, quote_state)
            if quote_state is None:
                opened_at = None
            elif not was_open:
                opened_at = paragraph_index
            if not pieces and rows:
                rows[-1]["break_ms"] = max(int(rows[-1]["break_ms"]), _punctuation_break_ms(line))
            for piece, hint in pieces:
                append_piece(piece, hint, paragraph_index)
        if quote_state is not None and paragraph_index in close_at_end_of:
            quote_state = None
            opened_at = None
    return rows, quote_state, opened_at


def segment_chapter_text(
    chapter_index: int,
    text: str,
    max_chars: int = 340,
    *,
    warnings: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Split a chapter into segments, recovering from a source that never closes a quote.

    A quotation may legitimately run across blank-line-separated paragraphs, so the quote
    state is threaded through the whole chapter rather than reset at each paragraph. The
    price of that reach is that ONE missing quote mark leaves the state open all the way to
    the end, and this function used to raise and refuse the chapter - which stops a whole
    book on a single typo, in a source nobody here wrote. Eight of this book's 478 chapters
    trip it.

    So it recovers. The paragraph that opened the hanging quote has its quote forced shut
    where that paragraph ends, and the chapter is parsed again; if that is not enough the
    next culprit is added, and the last resort closes every paragraph at its own end, which
    cannot leave anything open. Recovery may read a stretch as dialogue that was narration
    or the reverse, which costs a voice. It cannot lose or reorder a word - the token check
    at the bottom of this function still proves that on every chapter, recovered or not.

    Pass ``warnings`` to hear about it; the list is appended to, never read.
    """
    text = normalize_text(text)
    paragraphs = [part.strip() for part in re.split(r"\\n\\s*\\n", text) if part.strip()]

    close_at_end_of: frozenset[int] = frozenset()
    rows, quote_state, opened_at = _walk_paragraphs(
        chapter_index, paragraphs, max_chars, close_at_end_of
    )
    while quote_state is not None:
        if opened_at is None or opened_at in close_at_end_of:
            close_at_end_of = frozenset(range(len(paragraphs)))
        else:
            close_at_end_of = close_at_end_of | {opened_at}
        rows, quote_state, opened_at = _walk_paragraphs(
            chapter_index, paragraphs, max_chars, close_at_end_of
        )
        if quote_state is not None and len(close_at_end_of) >= len(paragraphs):
            raise RuntimeError(
                f"Unclosed {quote_state[0]} quote at the end of chapter {chapter_index} "
                f"survived closing every paragraph; expected {quote_state[1]!r}"
            )

    if close_at_end_of and warnings is not None:
        where = ", ".join(str(index + 1) for index in sorted(close_at_end_of))
        warnings.append(
            f"Chapter {chapter_index}: unclosed quote recovered by closing it at the end of "
            f"paragraph {where}; a stretch of this chapter may be cast as the wrong voice."
        )

    for index, row in enumerate(rows):'''

assert OLD_LOOP in s, "khong khop vong lap"
s = s.replace(OLD_LOOP, NEW_LOOP)

OLD_SIG = '''def load_and_segment_chapter(chapter: dict[str, Any], max_chars: int) -> list[dict[str, Any]]:'''
NEW_SIG = '''def load_and_segment_chapter(
    chapter: dict[str, Any],
    max_chars: int,
    *,
    warnings: list[str] | None = None,
) -> list[dict[str, Any]]:'''
assert OLD_SIG in s, "khong khop chu ky load_and_segment_chapter"
s = s.replace(OLD_SIG, NEW_SIG)

OLD_CALL = '''    return segment_chapter_text(int(chapter["chapter_index"]), text, max_chars=max_chars)'''
NEW_CALL = '''    return segment_chapter_text(
        int(chapter["chapter_index"]),
        text,
        max_chars=max_chars,
        warnings=warnings,
    )'''
assert OLD_CALL in s, "khong khop loi goi"
s = s.replace(OLD_CALL, NEW_CALL)

io.open(p, "w", encoding="utf-8").write(s)
print(f"da va {p}")
