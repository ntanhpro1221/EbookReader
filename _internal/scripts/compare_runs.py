"""Did a change alter what the machine hears, or only how fast it heard it?

Every engine or model change in this project has to clear two bars, and the second is the
one that is easy to skip. measure_batched_asr.py stated it: a decode that changes what the
voice is heard saying is a different engine, not an optimisation - and a different engine
costs a full re-verification of the book.

This compares two preserved runs of the same book segment by segment: how many transcripts
differ once normalised the way the pipeline normalises them, and whether each ASR warning
class comes out at the same count. Warning counts matter as much as transcripts: a change
that leaves the text alone but moves segments across a gate has still changed the book.

It compares only segments that both runs actually transcribed, so a run still in flight can
be compared against a finished one - the coverage line says how much of the book that is.

    python scripts/compare_runs.py <baseline_project_root> <candidate_project_root> [max_chapter]

Read-only: opens both databases read-only and writes nothing.
"""
from __future__ import annotations

import collections
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ebook_reader.asr import normalize_transcript  # noqa: E402

FIELDS = (
    "s.stable_id, s.status, s.warning_code, s.asr_text, s.text, s.wav_sha256, "
    "s.asr_similarity, s.asr_wer, s.generation_delivery_mode, c.chapter_index"
)


def _load(root: Path, max_chapter: int | None) -> dict[str, sqlite3.Row]:
    database = root / "project.sqlite3"
    if not database.is_file():
        raise SystemExit(f"không tìm thấy project: {database}")
    connection = sqlite3.connect(f"file:{database}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    query = f"SELECT {FIELDS} FROM segments s JOIN chapters c ON c.id = s.chapter_id"
    params: tuple = ()
    if max_chapter is not None:
        query += " WHERE c.chapter_index <= ?"
        params = (max_chapter,)
    rows = {row["stable_id"]: row for row in connection.execute(query, params)}
    connection.close()
    return rows


def _warning_counts(rows: dict, keys: list[str]) -> collections.Counter:
    counter: collections.Counter = collections.Counter()
    for key in keys:
        for code in str(rows[key]["warning_code"] or "").split("|"):
            if code:
                counter[code] += 1
    return counter


def main(baseline_root: str, candidate_root: str, max_chapter: int | None) -> int:
    baseline = _load(Path(baseline_root), max_chapter)
    candidate = _load(Path(candidate_root), max_chapter)

    shared = [
        key
        for key in candidate
        if key in baseline and candidate[key]["asr_text"] and baseline[key]["asr_text"]
    ]
    if not shared:
        print("không segment nào có bản ghi ASR ở cả hai lần chạy")
        return 1
    print(f"nền   : {Path(baseline_root).name}  ({len(baseline)} segment)")
    print(f"thử   : {Path(candidate_root).name}  ({len(candidate)} segment)")
    print(f"so được: {len(shared)} segment có bản ghi ở cả hai")

    differing = [
        key
        for key in shared
        if normalize_transcript(str(baseline[key]["asr_text"]))
        != normalize_transcript(str(candidate[key]["asr_text"]))
    ]
    print(f"\nbản ghi khác nhau sau chuẩn hoá: {len(differing)}/{len(shared)} "
          f"= {len(differing) / len(shared):.1%}")

    before, after = _warning_counts(baseline, shared), _warning_counts(candidate, shared)
    print("\nmã cảnh báo (chỉ trên các segment so được):")
    moved = False
    for code in sorted(set(before) | set(after)):
        mark = "" if before.get(code, 0) == after.get(code, 0) else "   <-- ĐỔI"
        if mark:
            moved = True
        print(f"  {before.get(code, 0):4d} -> {after.get(code, 0):4d}  {code}{mark}")

    for key in differing[:8]:
        left, right = baseline[key], candidate[key]
        print(f"\n  {key}")
        print(f"    văn bản: {str(left['text'])[:76]}")
        print(f"    nền    : {str(left['asr_text'])[:76]}")
        print(f"    thử    : {str(right['asr_text'])[:76]}")
        print(f"    similarity {left['asr_similarity']} -> {right['asr_similarity']}"
              f" | WER {left['asr_wer']} -> {right['asr_wer']}")
        # A different checksum means the runs judged different audio, so any warning that
        # moved with it belongs to the take rather than to the decode. Missing this is how
        # a perceptual failure gets blamed on an ASR engine.
        if str(left["wav_sha256"]) != str(right["wav_sha256"]):
            print(f"    ÂM THANH KHÁC: {str(left['generation_delivery_mode'])}"
                  f" -> {str(right['generation_delivery_mode'])}"
                  " - khác biệt ở đây không quy cho engine được")

    print()
    if differing or moved:
        print(
            "Có thay đổi. Trước khi gọi đây là một tối ưu, hãy tách hai chuyện: bản ghi đổi "
            "vì *giải mã* khác, hay vì *bản thu* khác (checksum khác). Chỉ chuyện đầu mới "
            "nói về engine."
        )
    else:
        print("Không đổi bản ghi, không đổi lớp cảnh báo - thay đổi này chỉ động tới tốc độ.")
    return 0


if __name__ == "__main__":
    if not 2 <= len(sys.argv) - 1 <= 3:
        print(__doc__)
        raise SystemExit(2)
    raise SystemExit(
        main(sys.argv[1], sys.argv[2], int(sys.argv[3]) if len(sys.argv) > 3 else None)
    )
