"""Ask an ear the one question the perceptual check has never been asked.

`PERCEPTUAL_QA_COST.md` measures what UTMOSv2 costs: the largest non-TTS slice of a run.
This asks whether it is right. Over alpha.43 to alpha.48 it flagged 180 takes and 152 of
them were replaced by a re-cut that scored acceptably. Every one of those is a claim the
check earned its keep, and not one has ever been checked by listening.

Both takes survive under `work/candidates/chapter_*/segment_*/*/round_*.wav`, so the claim
is testable: play the take it rejected against the take it accepted and see whether anybody
can hear the difference it measured.

**The page is blind.** Which take is A and which is B is decided by a hash of the segment
id, not by which one the machine preferred, and the page never says which is which. A
listener told "this is the one the computer threw away" hears what they expect to hear, and
the answer would be worthless. The key is written next to the page and is not needed until
the answers come back.

    python scripts/build_perceptual_ab_page.py <output_dir> [version ...]

Read-only with respect to every project it reads. Local only: the audio is the owner's book.
The bytes go in verbatim, never re-encoded - the question is about perceived quality, so
handing the listener a lossy copy would be asking them to rule on audio nobody produced.
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
    if not path.is_file():
        return ""
    return "data:audio/wav;base64," + base64.b64encode(path.read_bytes()).decode("ascii")


def _flipped(recording_sha256: str) -> bool:
    """Whether the rejected take is presented second. Deterministic, so it can be undone.

    Keyed on the recording, not on the segment. The same sentence can appear several times
    with genuinely different takes, and keying on the segment id would put every one of them
    on the same side - a listener who notices the repeat would then be answering one question
    three times instead of three independent ones.
    """
    return hashlib.sha256(recording_sha256.encode("utf-8")).digest()[0] % 2 == 1


def collect_pairs(project: Path) -> list[dict]:
    """Segments the perceptual check flagged, replaced, and whose both takes survive."""
    db = sqlite3.connect(f"file:{project / 'project.sqlite3'}?mode=ro", uri=True)
    db.row_factory = sqlite3.Row

    flagged: dict[int, list[tuple[str, float]]] = {}
    for row in db.execute(
        "SELECT segment_id, artifact_sha256, metrics_json FROM quality_checks "
        "WHERE stage='segment_perceptual_v1'"
    ):
        try:
            metrics = json.loads(row["metrics_json"] or "{}")
        except ValueError:
            continue
        if str(metrics.get("verdict")) != "review":
            continue
        flagged.setdefault(int(row["segment_id"]), []).append(
            (str(row["artifact_sha256"]), -float(metrics.get("baseline_delta") or 0.0))
        )

    pairs: list[dict] = []
    for segment_id, entries in flagged.items():
        row = db.execute(
            "SELECT s.stable_id, s.seq, s.text, s.wav_sha256, c.chapter_index "
            "FROM segments s JOIN chapters c ON c.id=s.chapter_id WHERE s.id=?",
            (segment_id,),
        ).fetchone()
        if row is None or str(row["wav_sha256"]) in {sha for sha, _ in entries}:
            # No row, or the flagged take is still the delivered one: nothing was replaced.
            continue
        directory = (
            project / "work" / "candidates"
            / f"chapter_{int(row['chapter_index']):05d}"
            / f"segment_{int(row['seq']):08d}"
        )
        takes = sorted(directory.glob("*/round_*.wav"))
        if len(takes) < 2:
            continue
        pairs.append(
            {
                "version": project.parent.name,
                "stable_id": str(row["stable_id"]),
                "text": str(row["text"] or ""),
                "drop": entries[0][1],
                "rejected": takes[0],
                "kept": takes[-1],
            }
        )
    return pairs


def build(output_dir: Path, versions: list[str]) -> int:
    pairs: list[dict] = []
    for name in versions:
        for project in sorted((VERSIONS_ROOT / name).glob("*/project.sqlite3")):
            pairs.extend(collect_pairs(project.parent))
    if not pairs:
        _say_safely("không tìm được cặp nào còn giữ cả hai bản thu")
        return 1
    pairs.sort(key=lambda item: (item["version"], item["stable_id"]))

    # The pipeline is deterministic, so the same segment produces the same two takes in
    # every version that reaches it. Thirteen cards across five runs are five recordings
    # asked about five times over; listening is the scarce resource here, not disk.
    distinct: dict[tuple[str, str], dict] = {}
    for pair in pairs:
        fingerprint = (
            hashlib.sha256(pair["rejected"].read_bytes()).hexdigest(),
            hashlib.sha256(pair["kept"].read_bytes()).hexdigest(),
        )
        seen = distinct.get(fingerprint)
        if seen is None:
            pair["also_in"] = []
            pair["fingerprint"] = fingerprint[0]
            distinct[fingerprint] = pair
        else:
            seen["also_in"].append(pair["version"])
    pairs = list(distinct.values())

    cards, key = [], []
    for index, pair in enumerate(pairs, start=1):
        flip = _flipped(pair["fingerprint"])
        first = pair["kept"] if flip else pair["rejected"]
        second = pair["rejected"] if flip else pair["kept"]
        key.append(
            {
                "n": index,
                "stable_id": pair["stable_id"],
                "version": pair["version"],
                "drop": round(pair["drop"], 3),
                "also_in": pair.get("also_in", []),
                "rejected_is": "B" if flip else "A",
            }
        )
        first_uri, second_uri = _embedded_audio(first), _embedded_audio(second)
        if not first_uri or not second_uri:
            continue
        cards.append(f"""<article>
  <header><span class="n">{index}</span>
    <code>{html.escape(pair['stable_id'])}</code>
    <span class="dur">{html.escape(pair['version'])}{
      f" +{len(pair['also_in'])} bản nữa" if pair.get('also_in') else ''}</span></header>
  <p class="say">{html.escape(pair['text'][:400])}</p>
  <div class="take"><span class="lbl">A</span><audio controls preload="none" src="{first_uri}"></audio></div>
  <div class="take"><span class="lbl">B</span><audio controls preload="none" src="{second_uri}"></audio></div>
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
 .ask {{ display: flex; gap: 1rem; flex-wrap: wrap; margin-top: .7rem;
         padding-top: .6rem; font-size: .93em;
         border-top: 1px solid color-mix(in oklab, currentColor 15%, transparent); }}
 button {{ font: inherit; padding: .4rem .8rem; border-radius: 7px; cursor: pointer;
           border: 1px solid color-mix(in oklab, currentColor 35%, transparent);
           background: transparent; color: inherit; }}
 #out {{ position: sticky; bottom: 0; padding: .8rem 0; background: Canvas; }}
</style>
<h1>{len(cards)} cặp — cùng một câu, hai bản thu</h1>
<p class="lede">Với mỗi cặp, máy đã <b>loại một bản và giữ bản kia</b>. Trang này không nói
bản nào là bản nào, và thứ tự A/B được xáo theo mã đoạn — nếu biết trước thì tai sẽ nghe ra
đúng cái mình chờ đợi, và câu trả lời thành vô nghĩa.<br><br>
Câu hỏi duy nhất: <b>có nghe ra bản nào tệ hơn không?</b> Không phải bản nào đọc đúng chữ —
cả hai đều đã qua kiểm tra ấy — mà bản nào nghe <i>khó chịu</i> hơn: méo tiếng, ngắt sai,
giọng lạc. Nghe như nhau là một câu trả lời tốt và rất có ích.</p>
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
    key_path.write_text(json.dumps(key, ensure_ascii=False, indent=1), encoding="utf-8")
    _say_safely(f"{len(cards)} cặp -> {page_path}  ({page_path.stat().st_size / 1e6:.1f} MB)")
    _say_safely(f"khoá giải mã   -> {key_path}")
    return 0


def main(argv: list[str]) -> int:
    if not argv:
        _say_safely("dùng: build_perceptual_ab_page.py <thư mục ra> [phiên bản ...]")
        return 2
    return build(Path(argv[0]).resolve(), argv[1:] or DEFAULT_VERSIONS)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
