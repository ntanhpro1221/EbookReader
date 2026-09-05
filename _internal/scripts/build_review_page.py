"""Build a local page for the one job only a person can do: listening.

`what_blocks_publication.py` prints every blocked segment with its WAV path and the `accept`
line that settles it. That is the right information in the wrong shape - the listener has to
copy a path into a player, play it, come back, find the matching two lines of text, then copy
a command. Ten segments of that is enough friction that the book stays unpublished.

This writes one HTML file next to the project with a player per segment, the sentence the
voice was asked to say, what Whisper heard, and the exact `accept` command behind a copy
button.

Deliberately local: nothing is uploaded, because the audio is the owner's book.

The audio is embedded as data: URIs rather than linked by relative path. A linked page only
plays where the viewer will fetch sibling files from disk, and the first version of this was
opened in a preview pane that renders local files as a static snapshot - every player showed
0:00 / 0:00 and the page was useless for the one job it exists for. Embedding costs about
4.5 MB for a book's worth of blocked segments and works anywhere.

The bytes go in verbatim, never re-encoded. Half these segments are flagged for a *perceptual*
judgement, so handing the listener a lossily compressed copy would be asking them to rule on
audio the pipeline never produced.

Each card carries a note saying why *this* segment needs an ear: what the machine measured,
what it already checked and found fine, the one thing to listen for, and how far to trust the
machine's own verdict here. A bare warning code does none of that - it does not even say
which half of the clip is in question, so the listener re-judges the whole thing.

Notes come from a JSON file (see scripts/review_evidence.py and the review-notes workflow).
Without one the page still builds, with the codes alone.

    python scripts/build_review_page.py <project_root> [output_html] [notes_json]

Read-only with respect to the project: opens the database read-only, writes only the page.
"""
from __future__ import annotations

import base64
import html
import json
import mimetypes
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ebook_reader.pipeline import HIGH_QUALITY_ALLOWED_SEGMENT_WARNINGS  # noqa: E402

PAGE_NAME = "review.html"


def _embedded_audio(path: Path) -> str:
    """The WAV as a data: URI, byte for byte.

    Returns "" when the file is missing, which the caller renders as "no recording" rather
    than as a silent player.
    """
    if not path.is_file():
        return ""
    kind = mimetypes.guess_type(path.name)[0] or "audio/wav"
    return f"data:{kind};base64," + base64.b64encode(path.read_bytes()).decode("ascii")


def _accepted(connection) -> set:
    """(stable_id, wav_sha256) pairs a listener has already ruled on.

    The pipeline subtracts these in _high_quality_blocking_segment_warnings, so a report
    that does not is describing a book the pipeline no longer sees - it would keep asking
    for decisions already made. Keyed by checksum, so re-cutting a take voids the decision
    exactly as it does everywhere else.
    """
    try:
        rows = connection.execute(
            "SELECT segment_stable_id, warning_code, wav_sha256 FROM listener_audio_acceptances"
        ).fetchall()
    except Exception:  # noqa: BLE001 - older projects have no such table
        return set()
    return {(str(r[0]), str(r[1]), str(r[2]).lower()) for r in rows}


def _blocking(row: sqlite3.Row) -> list[str]:
    codes = {value for value in str(row["warning_code"] or "").split("|") if value}
    if str(row["status"]) == "failed":
        return sorted(codes) or ["SEGMENT_FAILED"]
    return sorted(codes - HIGH_QUALITY_ALLOWED_SEGMENT_WARNINGS)


def _load_notes(path: str | None) -> dict[str, dict]:
    if not path or not Path(path).is_file():
        return {}
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    entries = raw.get("notes", raw) if isinstance(raw, dict) else raw
    return {str(n["stable_id"]): n for n in entries if n and n.get("stable_id")}


def main(project_root: str, output: str | None, notes_path: str | None = None) -> int:
    notes = _load_notes(notes_path)
    root = Path(project_root).resolve()
    database = root / "project.sqlite3"
    if not database.is_file():
        print(f"không tìm thấy project: {database}")
        return 2
    destination = Path(output).resolve() if output else root / PAGE_NAME

    connection = sqlite3.connect(f"file:{database}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    chapters = connection.execute(
        "SELECT id, chapter_index, status, output_mp3 FROM chapters ORDER BY chapter_index"
    ).fetchall()

    items: list[dict] = []
    for chapter in chapters:
        published = bool(chapter["output_mp3"]) and Path(str(chapter["output_mp3"])).is_file()
        if published:
            continue
        for row in connection.execute(
            "SELECT stable_id, status, warning_code, wav_path, wav_duration, text, asr_text "
            "FROM segments WHERE chapter_id=? ORDER BY seq",
            (int(chapter["id"]),),
        ):
            for code in _blocking(row):
                path = str(row["wav_path"] or "")
                href = _embedded_audio(Path(path)) if path else ""
                items.append({
                    "chapter": int(chapter["chapter_index"]),
                    "stable_id": str(row["stable_id"]),
                    "code": code,
                    "gave_up": str(row["status"]) == "failed",
                    "seconds": float(row["wav_duration"] or 0.0),
                    "href": href,
                    "text": str(row["text"] or ""),
                    "heard": str(row["asr_text"] or ""),
                    "note": notes.get(str(row["stable_id"])),
                    "command": (
                        f'ebook-reader-headless accept "{root}" --segment {row["stable_id"]} '
                        f'--warning {code} --note "đã nghe"'
                    ),
                })
    connection.close()

    cards = []
    for item in items:
        missing = "" if item["href"] else (
            '<p class="none">Không có bản thu - máy chưa tạo được audio nào cho câu này.</p>'
        )
        player = (
            # base64 is [A-Za-z0-9+/=], so nothing here needs escaping; preload="metadata"
            # so the duration shows without decoding every clip on load.
            f'<audio controls preload="metadata" src="{item["href"]}"></audio>'
            if item["href"] else ""
        )
        note = item["note"]
        trust = str(note.get("trust", "")) if note else ""
        note_block = ""
        if note:
            note_block = f"""
  <div class="why">
    <p><b>Máy thấy gì</b> {html.escape(str(note.get('trigger', '')))}</p>
    <p class="ok"><b>Đã kiểm, ổn</b> {html.escape(str(note.get('already_ok', '')))}</p>
    <p class="do"><b>Nghe cái gì</b> {html.escape(str(note.get('listen_for', '')))}</p>
    <p class="tw"><b>Tin máy tới đâu</b> {html.escape(str(note.get('trust_why', '')))}</p>
  </div>"""
        trust_chip = (
            f'<span class="trust t-{ {"thấp": "low", "vừa": "mid", "cao": "high"}.get(trust, "mid") }">'
            f"tin máy: {html.escape(trust)}</span>" if trust else ""
        )
        cards.append(f"""<article>
  <header>
    <span class="ch">ch{item['chapter']}</span>
    <code>{html.escape(item['stable_id'])}</code>
    <span class="tag {'gave' if item['gave_up'] else 'warn'}">{html.escape(item['code'])}</span>
    {trust_chip}
    <span class="dur">{item['seconds']:.1f}s</span>
  </header>
  {player}{missing}{note_block}
  <dl>
    <dt>Câu</dt><dd>{html.escape(item['text'])}</dd>
    <dt>Máy nghe</dt><dd class="heard">{html.escape(item['heard']) or '<i>(không có bản ghi)</i>'}</dd>
  </dl>
  <button data-cmd="{html.escape(item['command'])}">Chép lệnh chấp nhận</button>
</article>""")

    page = f"""<!doctype html>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Cần tai người nghe — {html.escape(root.name)}</title>
<style>
 :root {{ color-scheme: light dark; }}
 body {{ font: 15px/1.55 system-ui, sans-serif; margin: 0 auto; padding: 1.2rem; max-width: 46rem; }}
 h1 {{ font-size: 1.25rem; margin: 0 0 .3rem; }}
 .lede {{ opacity: .75; margin: 0 0 1.4rem; }}
 article {{ border: 1px solid color-mix(in oklab, currentColor 22%, transparent);
            border-radius: 10px; padding: .85rem 1rem; margin-bottom: 1rem; }}
 header {{ display: flex; gap: .55rem; align-items: center; flex-wrap: wrap; margin-bottom: .6rem; }}
 code {{ font-size: .82em; opacity: .8; }}
 .ch {{ font-weight: 700; }}
 .tag {{ font-size: .72em; padding: .12rem .45rem; border-radius: 999px;
         border: 1px solid currentColor; }}
 .tag.gave {{ color: #b3261e; }} .tag.warn {{ color: #8a6100; }}
 .dur {{ margin-left: auto; opacity: .6; font-size: .82em; }}
 audio {{ width: 100%; margin: .2rem 0 .7rem; }}
 dl {{ display: grid; grid-template-columns: max-content 1fr; gap: .2rem .8rem; margin: 0 0 .7rem; }}
 dt {{ opacity: .6; font-size: .82em; }} dd {{ margin: 0; }}
 .heard {{ font-style: italic; }}
 .why {{ border-left: 3px solid color-mix(in oklab, currentColor 25%, transparent);
         padding: .1rem 0 .1rem .75rem; margin: 0 0 .8rem; }}
 .why p {{ margin: .25rem 0; }}
 .why b {{ display: inline-block; min-width: 8.5rem; font-size: .78em; text-transform: uppercase;
           letter-spacing: .03em; opacity: .65; font-weight: 600; }}
 .why .do {{ font-weight: 600; }}
 .why .ok b, .why .ok {{ opacity: .95; }}
 .why .tw {{ opacity: .75; font-size: .93em; }}
 .trust {{ font-size: .72em; padding: .12rem .45rem; border-radius: 999px; border: 1px solid currentColor; }}
 .t-low {{ color: #6b7280; }} .t-mid {{ color: #8a6100; }} .t-high {{ color: #b3261e; }}
 .none {{ color: #b3261e; margin: .2rem 0 .7rem; }}
 button {{ font: inherit; padding: .35rem .7rem; border-radius: 7px; cursor: pointer;
           border: 1px solid color-mix(in oklab, currentColor 35%, transparent);
           background: transparent; color: inherit; }}
</style>
<h1>{len(items)} chỗ cần tai người nghe</h1>
<p class="lede">Mỗi thẻ nói rõ máy thấy gì, đã kiểm được gì là ổn, và cần nghe đúng cái gì.
Giọng đọc đúng thì chép lệnh và chạy; đọc sai thật thì để nguyên. Quyết định gắn với đúng bản
thu này — thu lại là nó hết hiệu lực. <b>tin máy: thấp</b> nghĩa là chính phép đo hay báo động
giả ở ca đó, không phải bản thu chắc chắn ổn.</p>
{"".join(cards) if cards else "<p>Không chương nào đang chờ quyết định.</p>"}
<script>
document.addEventListener('click', async (event) => {{
  const button = event.target.closest('button[data-cmd]');
  if (!button) return;
  try {{ await navigator.clipboard.writeText(button.dataset.cmd); }}
  catch {{ /* clipboard refused; the selection fallback below still works */ }}
  const was = button.textContent;
  button.textContent = 'Đã chép';
  setTimeout(() => {{ button.textContent = was; }}, 1400);
}});
</script>
"""
    destination.write_text(page, encoding="utf-8")
    print(f"{len(items)} chỗ cần nghe -> {destination}")
    if items:
        print("Mở file này trong trình duyệt. Không có gì được tải lên đâu cả.")
    return 0


if __name__ == "__main__":
    if not 1 <= len(sys.argv) - 1 <= 3:
        print(__doc__)
        raise SystemExit(2)
    raise SystemExit(
        main(
            sys.argv[1],
            sys.argv[2] if len(sys.argv) > 2 and sys.argv[2] != "-" else None,
            sys.argv[3] if len(sys.argv) > 3 else None,
        )
    )
