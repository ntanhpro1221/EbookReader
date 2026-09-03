"""Judge two ASR engines against the text the voice was actually given.

transcribe_sample.py writes down what one engine heard. This reads two of those files and
asks the only question that decides whether an engine can be swapped: **do they disagree
about which takes are acceptable?** Speed is reported too, but a faster transcriber that
fails a good take costs a re-synthesis and a slower one that passes a bad take ships a
defect - either wipes out the saving many times over.

The expected text is rebuilt with the project's own spoken_text_with_anchors, because names
and English terms are substituted before synthesis: comparing against the segment's source
text would score the substitution rather than the take. The verdicts come from the
project's own evaluation, so a disagreement here is a disagreement the pipeline would have
acted on.

    python scripts/compare_asr_engines.py <project_root> out-openai.json out-faster.json
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

from ebook_reader.asr import normalize_transcript  # noqa: E402
from ebook_reader.database import ProjectDB  # noqa: E402
from ebook_reader.tts import TTSCoordinator  # noqa: E402


def _similarity(expected: str, heard: str) -> float:
    from difflib import SequenceMatcher

    return SequenceMatcher(
        None, normalize_transcript(expected), normalize_transcript(heard)
    ).ratio()


def main(project_root: str, first_path: str, second_path: str) -> int:
    root = Path(project_root)
    database = root / "project.sqlite3"
    if not database.is_file():
        print(f"không tìm thấy project: {database}")
        return 2

    # ProjectDB migrates a schema older than its own, so a preserved version is read from a
    # copy rather than opened in place.
    workspace = Path(tempfile.mkdtemp(prefix="asr-engines-"))
    working = workspace / "project.sqlite3"
    shutil.copy2(database, working)
    settings = json.loads((root / "book_settings.json").read_text(encoding="utf-8"))
    db = ProjectDB(working)
    tts = TTSCoordinator(settings, db, lambda _message: None)

    connection = sqlite3.connect(f"file:{working}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    rows = {str(row["stable_id"]): row for row in connection.execute("SELECT * FROM segments")}
    connection.close()

    files = [json.loads(Path(path).read_text(encoding="utf-8")) for path in (first_path, second_path)]
    labels = [str(item["engine"]) for item in files]
    heard = [
        {str(entry["stable_id"]): entry for entry in item["results"]} for item in files
    ]
    shared = sorted(set(heard[0]) & set(heard[1]))
    if not shared:
        print("hai file không có bản thu nào chung")
        return 1

    threshold = float(settings["asr"].get("min_similarity", 0.78))
    verdict_pairs: Counter[tuple[str, str]] = Counter()
    disagreements: list[dict] = []
    seconds = [0.0, 0.0]

    for stable_id in shared:
        row = rows.get(stable_id)
        if row is None:
            continue
        try:
            expected, _anchors = tts.spoken_text_with_anchors(row)
        except Exception:  # noqa: BLE001
            continue
        scores = []
        for index in (0, 1):
            entry = heard[index][stable_id]
            seconds[index] += float(entry["seconds"])
            scores.append(_similarity(expected, str(entry["transcript"])))
        verdicts = ["pass" if score >= threshold else "fail" for score in scores]
        verdict_pairs[(verdicts[0], verdicts[1])] += 1
        if verdicts[0] != verdicts[1]:
            disagreements.append(
                {
                    "stable_id": stable_id,
                    "expected": expected[:110],
                    labels[0]: (verdicts[0], round(scores[0], 3), str(heard[0][stable_id]["transcript"])[:110]),
                    labels[1]: (verdicts[1], round(scores[1], 3), str(heard[1][stable_id]["transcript"])[:110]),
                }
            )

    print(f"{len(shared)} bản thu chung | ngưỡng similarity {threshold}")
    print(f"  {labels[0]:<10}{seconds[0]:8.1f}s ({seconds[0]/len(shared):5.2f}s/bản)")
    print(f"  {labels[1]:<10}{seconds[1]:8.1f}s ({seconds[1]/len(shared):5.2f}s/bản)")
    if seconds[1] > 0:
        print(f"  {labels[0]} chậm hơn {seconds[0]/seconds[1]:.2f} lần")
    print()
    print(f"  bất đồng đỗ/trượt: {len(disagreements)}/{len(shared)} "
          f"({len(disagreements)/len(shared):.1%})")
    for (left, right), count in verdict_pairs.most_common():
        mark = "  " if left == right else "≠ "
        print(f"    {mark}{labels[0]}={left:<6} {labels[1]}={right:<6} {count:>4}")

    for item in disagreements[:12]:
        print()
        print(f"  --- {item['stable_id']}")
        print(f"      mong đợi : {item['expected']}")
        for label in labels:
            verdict, score, text = item[label]
            print(f"      {label:<8} {verdict} {score}: {text}")

    print()
    print(
        "Đọc kết quả: nhanh hơn không đủ để đổi. Bất đồng 0% nghĩa là engine mới nghe "
        "giống hệt engine cũ ở mọi bản thu của tập này; khác 0 thì phải xem từng ca xem "
        "ai đúng trước khi đổi bất cứ thứ gì."
    )
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 4:
        print(__doc__)
        raise SystemExit(2)
    raise SystemExit(main(sys.argv[1], sys.argv[2], sys.argv[3]))
