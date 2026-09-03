"""Try a constraint on the locked-name alignment against every real case at once.

The canonical metrics contradict each other. Both claim to measure the content with the
name excluded, and on alpha.32's chapter 3 the WER passed at 0.250 while the similarity
failed at 0.667 - for a sentence whose Vietnamese was transcribed perfectly. The cause is
in _minimum_cost_locked_name_alignment: substitute_anchor consumes exactly one transcript
token while match_anchor consumes the whole form, so a multi-word name heard differently
leaves its surplus tokens to be charged against the words around it.

The obvious fix - let the substitution consume as many tokens as the name was heard as -
was tried and reverted. It moves the blocked segments to review_eligible, and it also lets
the anchor swallow genuinely misread ordinary content, which
test_clarity_final_gate_preserves_anchor_failure_from_either_decode caught.

So the next attempt needs evidence, not another guess. This replays a candidate constraint
over every anchor case in a finished run and reports two numbers that matter together:

  - how many real anchor failures become review_eligible (the prize), and
  - whether the over-absorption case still fails (the guard).

A change that moves the first without breaking the second is worth shipping. One that moves
both is the mistake already made once.

    python scripts/replay_anchor_alignment.py <project_root> [<project_root> ...]

Read-only: opens a copy of each project, never the project.
"""
from __future__ import annotations

import json
import shutil
import sqlite3
import sys
import tempfile
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ebook_reader.asr import (  # noqa: E402
    ASR_MISMATCH,
    adjudicate_locked_name_anchors,
)
from ebook_reader.database import ProjectDB  # noqa: E402
from ebook_reader.tts import TTSCoordinator  # noqa: E402

# The scripted case from test_clarity_final_gate_preserves_anchor_failure_from_either_decode.
# The transcript does contain the name, so the anchor MATCHES; what is wrong is everything
# around it. That is the invariant a widened substitution threatens: given the option, the
# alignment may substitute the anchor across several tokens instead of matching it exactly,
# and the misread words around it then vanish into the name. The guard is therefore not
# "this still fails" but "the anchor still matches and the content failure survives".
OVER_ABSORPTION_GUARD = {
    "expected": "Anh Lu-si-en đã đến.",
    "transcript": "Anh Lucien nói sai phần còn lại.",
    "spoken_form": "Lu-si-en",
    "surface": "Lucien",
    "similarity": 0.5,
    "wer": 0.8,
}


def _anchor_payload(expected: str, spoken_form: str, surface: str) -> list[dict]:
    start = expected.find(spoken_form)
    if start < 0:
        return []
    return [
        {
            "pronunciation_id": 1,
            "spoken_form": spoken_form,
            "surface": surface,
            "normalized_surface": surface.casefold(),
            "spoken_start": start,
            "spoken_end": start + len(spoken_form),
            "source_start": 0,
            "source_end": 1,
        }
    ]


def _adjudicate(expected: str, transcript: str, anchors: list[dict], similarity: float, wer: float) -> dict:
    result = adjudicate_locked_name_anchors(
        expected,
        {
            "passed": False,
            "verdict": ASR_MISMATCH,
            "transcript": transcript,
            "similarity": similarity,
            "wer": wer,
            "reason": "ASR_MISMATCH",
            "repairable": True,
            "severe": False,
        },
        anchors,
        min_similarity=0.78,
        max_wer=0.30,
    )
    return result


def _status(expected: str, transcript: str, anchors: list[dict], similarity: float, wer: float) -> str:
    if not anchors:
        return "no_anchor"
    metrics = _adjudicate(expected, transcript, anchors, similarity, wer).get(
        "locked_name_anchor_metrics"
    ) or {}
    return str(metrics.get("status", "?"))


def _cases(root: Path) -> list[dict]:
    database = root / "project.sqlite3"
    if not database.is_file():
        return []
    workspace = Path(tempfile.mkdtemp(prefix="anchor-replay-"))
    working = workspace / "project.sqlite3"
    shutil.copy2(database, working)
    settings = json.loads((root / "book_settings.json").read_text(encoding="utf-8"))
    db = ProjectDB(working)
    tts = TTSCoordinator(settings, db, lambda _message: None)

    connection = sqlite3.connect(f"file:{working}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    rows = connection.execute(
        "SELECT * FROM segments WHERE asr_text IS NOT NULL AND warning_code LIKE '%LOCKED_NAME_ANCHOR%'"
    ).fetchall()
    connection.close()

    cases: list[dict] = []
    for row in rows:
        try:
            expected, anchors = tts.spoken_text_with_anchors(row)
        except Exception:  # noqa: BLE001
            continue
        if not anchors:
            continue
        cases.append(
            {
                "stable_id": str(row["stable_id"]),
                "expected": expected,
                "transcript": str(row["asr_text"] or ""),
                "anchors": [dict(anchor) for anchor in anchors],
                "similarity": float(row["asr_similarity"] or 0.0),
                "wer": float(row["asr_wer"] or 1.0),
                "recorded": str(row["warning_code"] or ""),
            }
        )
    return cases


def main(roots: list[str]) -> int:
    cases: list[dict] = []
    for value in roots:
        found = _cases(Path(value))
        print(f"{Path(value).name}: {len(found)} ca có neo tên")
        cases.extend(found)
    if not cases:
        print("không có ca nào để chạy lại")
        return 1

    tally: Counter[str] = Counter()
    print()
    for case in cases:
        status = _status(
            case["expected"],
            case["transcript"],
            case["anchors"],
            case["similarity"],
            case["wer"],
        )
        tally[status] += 1
        if status == "fail":
            print(f"  fail  {case['stable_id'][:26]}")
            print(f"        mong đợi : {case['expected'][:96]}")
            print(f"        nghe ra  : {case['transcript'][:96]}")

    print()
    print("trạng thái neo trên các ca thật:")
    for status, count in tally.most_common():
        print(f"  {status:<18} {count}")

    guard_anchors = _anchor_payload(
        OVER_ABSORPTION_GUARD["expected"],
        OVER_ABSORPTION_GUARD["spoken_form"],
        OVER_ABSORPTION_GUARD["surface"],
    )
    guard = _adjudicate(
        OVER_ABSORPTION_GUARD["expected"],
        OVER_ABSORPTION_GUARD["transcript"],
        guard_anchors,
        OVER_ABSORPTION_GUARD["similarity"],
        OVER_ABSORPTION_GUARD["wer"],
    )
    guard_metrics = guard.get("locked_name_anchor_metrics") or {}
    guard_status = str(guard_metrics.get("status", "?"))
    # The ordinary content failure lives in the verdict the adjudicator passes through,
    # not in the anchor's own failure codes.
    guard_verdict = str(guard.get("verdict", "?"))
    guard_demoted = bool(guard_metrics.get("canonical_demoted"))
    guard_promoted = bool(guard_metrics.get("canonical_promoted"))
    anchor_held = guard_status == "pass"
    content_failure_held = guard_verdict == ASR_MISMATCH and not guard_promoted
    print()
    print(
        f"  chốt: neo khớp = {guard_status} | verdict = {guard_verdict}"
        f" | promoted = {guard_promoted} | demoted = {guard_demoted}"
    )
    if anchor_held and content_failure_held:
        print("  (neo vẫn khớp chính xác và lỗi nội dung vẫn được báo - đúng như phải thế)")
    else:
        print(
            "  CẢNH BÁO: ràng buộc đang thử đã làm neo thôi khớp chính xác hoặc nuốt mất "
            "lỗi nội dung thường. Đó đúng là sai lầm đã mắc một lần."
        )
    print()
    print(
        "Đáng ship khi: số ca 'fail' giảm VÀ chốt vẫn giữ cả hai. Mất chốt là hỏng."
    )
    return 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        raise SystemExit(2)
    raise SystemExit(main(sys.argv[1:]))
