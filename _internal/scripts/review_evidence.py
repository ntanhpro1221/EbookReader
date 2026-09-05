"""Everything the machine knows about one blocked segment, in the shape a person needs.

The review page used to show a warning code and two lines of text. A code like
PERCEPTUAL_NATURALNESS_REVIEW does not say what to listen for, and worse, it does not say
what the machine already checked and found fine - so the listener re-judges the whole clip
instead of the one thing in question.

This gathers the evidence per blocked segment: every quality check that ran, what passed,
what failed, the numbers behind each verdict, and for a locked-name anchor the syllables the
name was supposed to be read as. Written to JSON so a reviewer note can be built from
measured facts rather than from the code name.

    python scripts/review_evidence.py <project_root> [out_dir]

Read-only with respect to the project.
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ebook_reader.pipeline import HIGH_QUALITY_ALLOWED_SEGMENT_WARNINGS  # noqa: E402

INTERESTING_METRICS = (
    "score", "baseline_score", "baseline_delta", "duration_seconds", "reason",
    "chars_per_second", "similarity", "wer", "pace_outlier", "policy_exemption",
)


def _anchor_forms(metrics: dict) -> list[dict]:
    """The readings a locked name would have been accepted as."""
    anchors = (metrics.get("locked_name_anchor_metrics") or {}).get("anchors") or []
    out = []
    for anchor in anchors:
        forms = {}
        for form in anchor.get("accepted_forms") or []:
            kind = str(form.get("kind") or "")
            if kind in ("spoken_form", "source_spelling") and kind not in forms:
                forms[kind] = list(form.get("tokens") or [])
        if forms:
            out.append(forms)
    return out


def collect(root: Path) -> list[dict]:
    connection = sqlite3.connect(f"file:{root / 'project.sqlite3'}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    segments: list[dict] = []
    for chapter in connection.execute(
        "SELECT id, chapter_index, output_mp3 FROM chapters ORDER BY chapter_index"
    ):
        published = bool(chapter["output_mp3"]) and Path(str(chapter["output_mp3"])).is_file()
        if published:
            continue
        for row in connection.execute(
            "SELECT * FROM segments WHERE chapter_id=? ORDER BY seq", (int(chapter["id"]),)
        ):
            codes = {value for value in str(row["warning_code"] or "").split("|") if value}
            if str(row["status"]) == "failed":
                blocking = sorted(codes) or ["SEGMENT_FAILED"]
            else:
                blocking = sorted(codes - HIGH_QUALITY_ALLOWED_SEGMENT_WARNINGS)
            if not blocking:
                continue

            checks, anchors, best_similarity = [], [], None
            for check in connection.execute(
                "SELECT stage, verdict, metrics_json, failure_codes_json FROM quality_checks "
                "WHERE segment_id=? ORDER BY id",
                (int(row["id"]),),
            ):
                metrics = json.loads(str(check["metrics_json"] or "{}"))
                kept = {k: metrics[k] for k in INTERESTING_METRICS if k in metrics}
                checks.append({
                    "stage": str(check["stage"]),
                    "verdict": str(check["verdict"]),
                    "codes": json.loads(str(check["failure_codes_json"] or "[]")),
                    "metrics": kept,
                })
                if isinstance(metrics.get("similarity"), (int, float)):
                    value = float(metrics["similarity"])
                    best_similarity = value if best_similarity is None else max(best_similarity, value)
                anchors.extend(_anchor_forms(metrics))

            segments.append({
                "stable_id": str(row["stable_id"]),
                "chapter": int(chapter["chapter_index"]),
                "blocking_codes": blocking,
                "status": str(row["status"]),
                "text": str(row["text"] or ""),
                "asr_text": str(row["asr_text"] or ""),
                "similarity": row["asr_similarity"],
                "best_decode_similarity": best_similarity,
                "wer": row["asr_wer"],
                "duration": row["wav_duration"],
                "pace": str(row["pace"] or "normal"),
                "emotion": str(row["emotion"] or ""),
                "has_audio": bool(row["wav_sha256"]),
                "wav_path": str(row["wav_path"] or ""),
                # First anchor only: a segment with more than one locked name is rare, and
                # the note names the one that failed rather than enumerating.
                "anchor": anchors[0] if anchors else None,
                "decode_attempts": sum(1 for c in checks if c["stage"] == "segment_asr_decode_v1"),
                "checks": checks,
            })
    connection.close()
    return segments


def main(project_root: str, out_dir: str | None) -> int:
    root = Path(project_root)
    if not (root / "project.sqlite3").is_file():
        print(f"không tìm thấy project: {root}")
        return 2
    segments = collect(root)
    destination = Path(out_dir) if out_dir else root / "review_evidence"
    destination.mkdir(parents=True, exist_ok=True)
    for segment in segments:
        (destination / f"{segment['stable_id']}.json").write_text(
            json.dumps(segment, ensure_ascii=False, indent=1), encoding="utf-8"
        )
    (destination / "index.json").write_text(
        json.dumps([s["stable_id"] for s in segments], ensure_ascii=False, indent=1),
        encoding="utf-8",
    )
    print(f"{len(segments)} segment -> {destination}")
    for segment in segments:
        print(f"  ch{segment['chapter']:<3} {segment['stable_id'][:24]} {','.join(segment['blocking_codes'])}")
    return 0


if __name__ == "__main__":
    if not 1 <= len(sys.argv) - 1 <= 2:
        print(__doc__)
        raise SystemExit(2)
    raise SystemExit(main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None))
