"""Ask an ear the one question the perceptual check has never been asked.

`PERCEPTUAL_QA_COST.md` measures what UTMOSv2 costs: the largest non-TTS slice of a run.
This asks whether it is right. Over alpha.43 to alpha.48 it rejected a take and promoted a
re-cut in its place around thirty times per run. Every one of those is a claim the check
earned its keep, and not one has ever been checked by listening.

Both takes survive, so the claim is testable: play the take it rejected against the take it
promoted and see whether anybody can hear the difference it measured.

**Find the takes through the ledger, never by guessing a path.** The first version of this
built the candidate directory from the segment's `seq`, and the directory is named by
`segment_id`. The two agree often enough that the mistake produced a plausible-looking page
in which every card paired one segment's text with a different segment's audio. The ledger
knows: `segment_candidates` records `incumbent_sha256` - the take that was replaced - and
the promoted candidate's own checksum, so both are located by content, and a pair that
cannot be found by checksum is dropped rather than approximated.

**The page is blind.** Which take is A and which is B comes from a hash of the recording,
not from which one the machine preferred, and the page never says. A listener told "this is
the one the computer threw away" hears what they expect to hear, and the answer would be
worthless. The key is written beside the page and is not needed until the answers come back.

    python scripts/build_perceptual_ab_page.py <output_dir> [version ...] [--limit N]

Read-only with respect to every project it reads. Local only: the audio is the owner's book.
The bytes go in verbatim, never re-encoded - the question is about perceived quality, so a
lossy copy would be asking the listener to rule on audio nobody ever produced.
"""
from __future__ import annotations

import base64
import hashlib
import html
import json
import sqlite3
import sys
from pathlib import Path

VERSIONS_ROOT = Path("D:/Novels/Audiobooks/_versions")
DEFAULT_VERSIONS = [
    "v0.2.0-alpha.43",
    "v0.2.0-alpha.44",
    "v0.2.0-alpha.46",
    "v0.2.0-alpha.47",
    "v0.2.0-alpha.48",
]
NATURALNESS_REQUIREMENT = "naturalness_improvement_v1"


def _say_safely(line: str) -> None:
    """Windows hands scripts a cp1252 stdout and every message here is Vietnamese."""
    try:
        print(line)
    except (UnicodeEncodeError, OSError, ValueError):
        try:
            sys.stdout.buffer.write(line.encode("utf-8", "replace") + b"\n")
        except Exception:  # noqa: BLE001
            pass


def _embedded_audio(path: Path) -> str:
    return "data:audio/wav;base64," + base64.b64encode(path.read_bytes()).decode("ascii")


def _flipped(recording_sha256: str) -> bool:
    """Whether the rejected take is presented second. Deterministic, so it can be undone.

    Keyed on the recording, not on the segment: the same sentence turns up with genuinely
    different takes across runs, and keying on the segment id would put every one of them on
    the same side, turning three cards into one question asked three times.
    """
    return hashlib.sha256(recording_sha256.encode("utf-8")).digest()[0] % 2 == 1


def _wav_index(project: Path) -> dict[str, Path]:
    """Every wav in the project, by checksum. The ledger stores checksums, not paths."""
    index: dict[str, Path] = {}
    for path in project.rglob("*.wav"):
        try:
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
        except OSError:
            continue
        index.setdefault(digest, path)
    return index


def collect_pairs(project: Path) -> list[dict]:
    """Every take the perceptual check rejected in favour of a re-cut, with both recordings."""
    db = sqlite3.connect(f"file:{project / 'project.sqlite3'}?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    promoted = list(
        db.execute(
            "SELECT segment_id, incumbent_sha256, wav_sha256 FROM segment_candidates "
            "WHERE candidate_repair_requirement=? AND state='promoted' ORDER BY segment_id",
            (NATURALNESS_REQUIREMENT,),
        )
    )
    if not promoted:
        return []

    drops: dict[str, float] = {}
    for row in db.execute(
        "SELECT artifact_sha256, metrics_json FROM quality_checks "
        "WHERE stage='segment_perceptual_v1'"
    ):
        try:
            metrics = json.loads(row["metrics_json"] or "{}")
        except ValueError:
            continue
        if metrics.get("baseline_delta") is not None:
            drops[str(row["artifact_sha256"])] = -float(metrics["baseline_delta"])

    index = _wav_index(project)
    pairs: list[dict] = []
    for row in promoted:
        rejected_sha = str(row["incumbent_sha256"] or "")
        kept_sha = str(row["wav_sha256"] or "")
        rejected, kept = index.get(rejected_sha), index.get(kept_sha)
        if rejected is None or kept is None:
            continue
        segment = db.execute(
            "SELECT stable_id, text FROM segments WHERE id=?", (int(row["segment_id"]),)
        ).fetchone()
        if segment is None:
            continue
        pairs.append(
            {
                "version": project.parent.name,
                "stable_id": str(segment["stable_id"]),
                "text": str(segment["text"] or ""),
                "drop": drops.get(rejected_sha),
                "rejected": rejected,
                "rejected_sha": rejected_sha,
                "kept": kept,
                "kept_sha": kept_sha,
            }
        )
    return pairs


def build(output_dir: Path, versions: list[str], limit: int | None) -> int:
    pairs: list[dict] = []
    for name in versions:
        for project in sorted((VERSIONS_ROOT / name).glob("*/project.sqlite3")):
            found = collect_pairs(project.parent)
            _say_safely(f"  {name}: {len(found)} cặp")
            pairs.extend(found)
    if not pairs:
        _say_safely("không tìm được cặp nào")
        return 1

    # The pipeline is deterministic, so a segment reached by several runs yields the same two
    # takes every time. Listening is the scarce resource here, not disk.
    distinct: dict[tuple[str, str], dict] = {}
    for pair in pairs:
        key = (pair["rejected_sha"], pair["kept_sha"])
        seen = distinct.get(key)
        if seen is None:
            pair["also_in"] = []
            distinct[key] = pair
        else:
            seen["also_in"].append(pair["version"])
    pairs = sorted(distinct.values(), key=lambda item: -(item["drop"] or 0))
    if limit:
        pairs = pairs[:limit]

    cards, key_rows = [], []
    for index, pair in enumerate(pairs, start=1):
        flip = _flipped(pair["rejected_sha"])
        first = pair["kept"] if flip else pair["rejected"]
        second = pair["rejected"] if flip else pair["kept"]
        key_rows.append(
            {
                "n": index,
                "stable_id": pair["stable_id"],
                "version": pair["version"],
                "drop": round(pair["drop"], 3) if pair["drop"] is not None else None,
                "also_in": pair["also_in"],
                "rejected_is": "B" if flip else "A",
                "rejected_sha256": pair["rejected_sha"],
                "kept_sha256": pair["kept_sha"],
            }
        )
        repeats = f" +{len(pair['also_in'])} bản nữa" if pair["also_in"] else ""
        cards.append(f"""<article>
  <header><span class="n">{index}</span>
    <code>{html.escape(pair['stable_id'])}</code>
    <span class="dur">{html.escape(pair['version'])}{repeats}</span></header>
  <p class="say">{html.escape(pair['text'][:400])}</p>
  <div class="take"><span class="lbl">A</span><audio controls preload="none" src="{_embedded_audio(first)}"></audio></div>
  <div class="take"><span class="lbl">B</span><audio controls preload="none" src="{_embedded_audio(second)}"></audio></div>
  <div class="ask">
    <label><input type="radio" name="q{index}" value="A"> A nghe tệ hơn</label>
    <label><input type="radio" name="q{index}" value="="> nghe như nhau</label>
    <label><input type="radio" name="q{index}" value="B"> B nghe tệ hơn</label>
  </div>
</article>""")

    page = f"""<!doctype html>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Máy chấm cảm thụ có bắt được gì không?</title>
<style>
 :root {{ color-scheme: light dark; }}
 body {{ font: 15px/1.55 system-ui, sans-serif; margin: 0 auto; padding: 1.2rem; max-width: 46rem; }}
 h1 {{ font-size: 1.25rem; margin: 0 0 .3rem; }}
 .lede {{ opacity: .8; margin: 0 0 1.6rem; }}
 article {{ border: 1px solid color-mix(in oklab, currentColor 22%, transparent);
            border-radius: 10px; padding: .85rem 1rem; margin-bottom: 1rem; }}
 header {{ display: flex; gap: .55rem; align-items: center; margin-bottom: .55rem; }}
 .n {{ font-weight: 700; }}
 code {{ font-size: .82em; opacity: .75; }}
 .dur {{ margin-left: auto; opacity: .55; font-size: .82em; }}
 .say {{ margin: 0 0 .7rem; }}
 .take {{ display: flex; align-items: center; gap: .6rem; margin-bottom: .35rem; }}
 .lbl {{ font-weight: 700; width: 1.2rem; opacity: .7; }}
 audio {{ width: 100%; }}
 .ask {{ display: flex; gap: 1rem; flex-wrap: wrap; margin-top: .7rem; padding-top: .6rem;
         font-size: .93em;
         border-top: 1px solid color-mix(in oklab, currentColor 15%, transparent); }}
 button {{ font: inherit; padding: .4rem .8rem; border-radius: 7px; cursor: pointer;
           border: 1px solid color-mix(in oklab, currentColor 35%, transparent);
           background: transparent; color: inherit; }}
 #out {{ position: sticky; bottom: 0; padding: .8rem 0; background: Canvas; }}
</style>
<h1>{len(cards)} cặp — cùng một câu, hai bản thu</h1>
<p class="lede">Với mỗi cặp, máy đã <b>loại một bản và đưa bản kia lên thay</b>. Trang này
không nói bản nào là bản nào, và thứ tự A/B xáo theo mã bản thu — biết trước thì tai sẽ nghe
ra đúng cái mình chờ đợi, và câu trả lời thành vô nghĩa.<br><br>
Câu hỏi duy nhất: <b>có nghe ra bản nào tệ hơn không?</b> Không phải bản nào đọc đúng chữ —
cả hai đều đã qua kiểm tra ấy — mà bản nào nghe <i>khó chịu</i> hơn: méo tiếng, ngắt sai,
giọng lạc. <b>Nghe như nhau là một câu trả lời tốt</b> và rất có ích: nếu phần lớn là như
nhau thì phép kiểm tra đắt nhất ngoài TTS đang cắt lại những bản không ai phân biệt được.</p>
{''.join(cards)}
<div id="out"><button id="copy">Chép kết quả</button> <span id="msg"></span></div>
<script>
document.getElementById('copy').addEventListener('click', () => {{
  const lines = [];
  document.querySelectorAll('article').forEach(card => {{
    const n = card.querySelector('.n').textContent;
    const picked = card.querySelector('input:checked');
    lines.push(n + ': ' + (picked ? picked.value : '-'));
  }});
  navigator.clipboard.writeText(lines.join('\\n')).then(() => {{
    document.getElementById('msg').textContent = 'đã chép ' + lines.length + ' dòng';
  }});
}});
</script>
"""
    output_dir.mkdir(parents=True, exist_ok=True)
    page_path = output_dir / "perceptual_ab.html"
    key_path = output_dir / "perceptual_ab_key.json"
    page_path.write_text(page, encoding="utf-8")
    key_path.write_text(json.dumps(key_rows, ensure_ascii=False, indent=1), encoding="utf-8")
    _say_safely(f"{len(cards)} cặp -> {page_path}  ({page_path.stat().st_size / 1e6:.1f} MB)")
    _say_safely(f"khoá giải mã   -> {key_path}")
    return 0


def main(argv: list[str]) -> int:
    limit = None
    for index, value in enumerate(argv):
        if value == "--limit" and index + 1 < len(argv):
            limit = int(argv[index + 1])
    positional = [
        value
        for index, value in enumerate(argv)
        if not value.startswith("--") and not (index and argv[index - 1] == "--limit")
    ]
    if not positional:
        _say_safely("dùng: build_perceptual_ab_page.py <thư mục ra> [phiên bản ...] [--limit N]")
        return 2
    return build(Path(positional[0]).resolve(), positional[1:] or DEFAULT_VERSIONS, limit)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
