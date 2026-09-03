"""Is beam search worth what it costs on the primary ASR pass?

ASR is the most expensive stage of a run - 3,870 seconds on alpha.25 against TTS's 2,055 -
and the primary decode uses beam_size 5 while the confirmation decode is greedy. Beam is
the slower of the two by construction: it carries several hypotheses and scores them all.

The question is NOT whether greedy is faster. It obviously is. The question is whether the
two decodes disagree about which takes are acceptable, because a decode that passes a bad
take or fails a good one costs a re-synthesis or ships a defect, and either wipes out the
saving many times over. So this runs both against the same audio and the same expected
text, through the same verify() the pipeline uses, and reports the disagreements - not the
stopwatch alone.

Reads a finished run; writes nothing to it. Needs the GPU free, so run it when no book job
is going.

    python scripts/measure_beam_vs_greedy.py <finished_project_root> [sample]
"""
from __future__ import annotations

import json
import shutil
import sqlite3
import sys
import tempfile
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ebook_reader.asr import WhisperVerifier  # noqa: E402
from ebook_reader.config import build_settings  # noqa: E402
from ebook_reader.database import ProjectDB  # noqa: E402
from ebook_reader.tts import TTSCoordinator  # noqa: E402

DEFAULT_SAMPLE = 60


def _expected_spoken_text(tts: TTSCoordinator, row) -> str:
    """What the pipeline actually asked the voice to say.

    Not the segment's source text: names and English terms are substituted before
    synthesis, so comparing a transcript against the source would score the substitution
    rather than the take.
    """
    text, _anchors = tts.spoken_text_with_anchors(row)
    return text


def main(project_root: str, sample: int) -> int:
    root = Path(project_root)
    database = root / "project.sqlite3"
    if not database.is_file():
        print(f"không tìm thấy project: {database}")
        return 2

    settings_path = root / "book_settings.json"
    settings = (
        json.loads(settings_path.read_text(encoding="utf-8"))
        if settings_path.is_file()
        else build_settings("high_quality")
    )

    # ProjectDB opens a writable connection and will migrate a schema it finds older than
    # its own, so pointing it at a preserved version's project would edit the very thing
    # that version exists to preserve. It reads a copy instead. The WAV paths inside are
    # absolute, so the audio still comes from the original run.
    workspace = Path(tempfile.mkdtemp(prefix="beam-vs-greedy-"))
    working_database = workspace / "project.sqlite3"
    shutil.copy2(database, working_database)
    db = ProjectDB(working_database)
    tts = TTSCoordinator(settings, db, print)
    print(f"đọc bản sao tại {working_database} (bản gốc không bị chạm vào)")

    connection = sqlite3.connect(f"file:{working_database}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    # Segments whose audio survived, spread across the book rather than taken from one
    # chapter: decode difficulty tracks the writing, and one chapter is one style.
    rows = connection.execute(
        "SELECT * FROM segments WHERE wav_path IS NOT NULL AND status != 'failed' "
        "ORDER BY (id * 2654435761) % 1000003 LIMIT ?",
        (sample,),
    ).fetchall()
    connection.close()
    if not rows:
        print("không có segment nào có WAV")
        return 1

    verifier = WhisperVerifier(settings, print)
    if not verifier.load():
        print("không nạp được Whisper")
        return 1

    disagreements: list[dict] = []
    verdict_pairs: Counter[tuple[str, str]] = Counter()
    elapsed = {"beam": 0.0, "greedy": 0.0}
    considered = 0

    for row in rows:
        wav = Path(str(row["wav_path"]))
        if not wav.is_file():
            continue
        try:
            expected = _expected_spoken_text(tts, row)
        except Exception as exc:  # noqa: BLE001
            print(f"bỏ qua {row['stable_id']}: không dựng được văn bản đọc ({exc})")
            continue
        considered += 1

        results = {}
        for label, confirmation in (("beam", False), ("greedy", True)):
            started = time.perf_counter()
            results[label] = verifier.verify(expected, wav, confirmation=confirmation)
            elapsed[label] += time.perf_counter() - started

        beam, greedy = results["beam"], results["greedy"]
        verdict_pairs[(str(beam["verdict"]), str(greedy["verdict"]))] += 1
        if bool(beam["passed"]) != bool(greedy["passed"]):
            disagreements.append(
                {
                    "stable_id": str(row["stable_id"]),
                    "expected": expected[:110],
                    "beam": (beam["verdict"], round(float(beam["similarity"]), 3)),
                    "greedy": (greedy["verdict"], round(float(greedy["similarity"]), 3)),
                    "beam_transcript": str(beam["transcript"])[:110],
                    "greedy_transcript": str(greedy["transcript"])[:110],
                }
            )

    verifier.unload()
    if not considered:
        print("không đo được segment nào")
        return 1

    print()
    print(f"{considered} segment, mỗi cái giải mã hai lần")
    print(f"  beam   : {elapsed['beam']:7.1f}s ({elapsed['beam'] / considered:5.2f}s/segment)")
    print(f"  greedy : {elapsed['greedy']:7.1f}s ({elapsed['greedy'] / considered:5.2f}s/segment)")
    if elapsed["greedy"] > 0:
        print(f"  beam chậm hơn {elapsed['beam'] / elapsed['greedy']:.2f} lần")
    print()
    print(f"  bất đồng đỗ/trượt: {len(disagreements)}/{considered} "
          f"({len(disagreements) / considered:.1%})")
    print()
    print("  cặp verdict (beam -> greedy):")
    for (beam_verdict, greedy_verdict), count in verdict_pairs.most_common():
        mark = "  " if beam_verdict == greedy_verdict else "≠ "
        print(f"    {mark}{beam_verdict:<34} {greedy_verdict:<34} {count:>4}")

    for item in disagreements[:12]:
        print()
        print(f"  --- {item['stable_id']}")
        print(f"      mong đợi : {item['expected']}")
        print(f"      beam   {item['beam']}: {item['beam_transcript']}")
        print(f"      greedy {item['greedy']}: {item['greedy_transcript']}")

    print()
    print(
        "Đọc kết quả: bất đồng 0% nghĩa là beam không mua được gì trên tập này và lượt "
        "chính có thể dùng greedy. Bất đồng khác 0 thì phải xem từng ca - beam đúng hay "
        "greedy đúng - trước khi đổi bất cứ thứ gì."
    )
    return 0


if __name__ == "__main__":
    if len(sys.argv) not in (2, 3):
        print(__doc__)
        raise SystemExit(2)
    raise SystemExit(
        main(sys.argv[1], int(sys.argv[2]) if len(sys.argv) == 3 else DEFAULT_SAMPLE)
    )
