"""Would batching the ASR decode fill the idle GPU, or is the idle time somewhere else?

Sampled during alpha.32's ASR phase, the GPU sat at 14-16% with 1.43 of 8.15 GB of VRAM
used, through the stage that costs 60% of a run. Whisper decodes one file at a time.
faster-whisper offers BatchedInferencePipeline, which decodes several at once, and the
obvious conclusion is that it would take that slack.

"Obvious" is what this project keeps being wrong about, and building it means changing
asr.py - a file whose every edit costs a full re-verification of the book. So the question
gets measured before anything is written: same takes, same options, one at a time against
several at a time, on the card as it actually is.

A batch is only worth building if the wall time per take drops materially. If the decode is
bound by something batching does not touch - the sequential mel/encoder path, or CPU-side
audio loading - the GPU will stay idle and the number will say so.

    python scripts/measure_batched_asr.py <project_root> [sample] [batch_size]

Reads a finished project's WAVs and writes nothing.
"""
from __future__ import annotations

import sqlite3
import sys
import time
from pathlib import Path

DEFAULT_SAMPLE = 48
DEFAULT_BATCH = 8


def _takes(database: Path, sample: int) -> list[tuple[str, float]]:
    connection = sqlite3.connect(f"file:{database}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    rows = connection.execute(
        "SELECT wav_path, wav_duration FROM segments "
        "WHERE wav_path IS NOT NULL AND wav_duration > 0 "
        "ORDER BY (id * 2654435761) % 1000003 LIMIT ?",
        (sample,),
    ).fetchall()
    connection.close()
    return [
        (str(row["wav_path"]), float(row["wav_duration"]))
        for row in rows
        if Path(str(row["wav_path"])).is_file()
    ]


def main(project_root: str, sample: int, batch_size: int) -> int:
    database = Path(project_root) / "project.sqlite3"
    if not database.is_file():
        print(f"không tìm thấy project: {database}")
        return 2
    takes = _takes(database, sample)
    if not takes:
        print("không có WAV nào")
        return 1

    import torch  # noqa: F401  - imported for the CUDA libraries CTranslate2 links
    from faster_whisper import BatchedInferencePipeline, WhisperModel

    model = WhisperModel("turbo", device="cuda", compute_type="float16")
    options = {
        "language": "vi",
        "task": "transcribe",
        "temperature": 0.0,
        "condition_on_previous_text": False,
    }

    # Warm the model so the first timing does not carry the load.
    list(model.transcribe(takes[0][0], beam_size=1, **options)[0])

    started = time.perf_counter()
    one_at_a_time: list[str] = []
    for path, duration in takes:
        segments, _info = model.transcribe(
            path, beam_size=5 if duration > 2.5 else 1, **options
        )
        one_at_a_time.append("".join(item.text for item in segments).strip())
    sequential_seconds = time.perf_counter() - started

    batched = BatchedInferencePipeline(model=model)
    started = time.perf_counter()
    batched_out: list[str] = []
    for path, duration in takes:
        segments, _info = batched.transcribe(
            path,
            batch_size=batch_size,
            beam_size=5 if duration > 2.5 else 1,
            **options,
        )
        batched_out.append("".join(item.text for item in segments).strip())
    batched_seconds = time.perf_counter() - started

    count = len(takes)
    print()
    print(f"{count} bản thu, batch_size={batch_size}")
    print(f"  một-lần-một : {sequential_seconds:7.1f}s  ({sequential_seconds / count:5.3f}s/bản)")
    print(f"  theo lô     : {batched_seconds:7.1f}s  ({batched_seconds / count:5.3f}s/bản)")
    if batched_seconds > 0:
        print(f"  nhanh hơn   : {sequential_seconds / batched_seconds:.2f} lần")

    # Raw text differs on punctuation alone, and the pipeline never compares raw text: it
    # normalises first, stripping everything but letters, digits and spaces. So the
    # difference that matters is the normalised one.
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from ebook_reader.asr import normalize_transcript

    raw_differing = sum(
        1 for left, right in zip(one_at_a_time, batched_out) if left != right
    )
    normalised_differing = 0
    first_real_difference: tuple[str, str] | None = None
    for left, right in zip(one_at_a_time, batched_out):
        if normalize_transcript(left) != normalize_transcript(right):
            normalised_differing += 1
            if first_real_difference is None:
                first_real_difference = (left, right)
    print()
    print(f"  bản ghi thô khác nhau      : {raw_differing}/{count} ({raw_differing / count:.1%})")
    print(
        f"  sau chuẩn hoá còn khác     : {normalised_differing}/{count} "
        f"({normalised_differing / count:.1%})"
    )
    if first_real_difference is not None:
        print(f"    một : {first_real_difference[0][:88]}")
        print(f"    lô  : {first_real_difference[1][:88]}")
    print()
    print(
        "Chỉ đáng xây khi giây/bản giảm rõ VÀ bản ghi không đổi. Một cái lô chia đôi mỗi "
        "đoạn dài thành nhiều lượt sẽ nhanh mà nghe khác - lúc ấy nó là một engine khác, "
        "không phải một tối ưu."
    )
    return 0


if __name__ == "__main__":
    if not 1 <= len(sys.argv) - 1 <= 3:
        print(__doc__)
        raise SystemExit(2)
    raise SystemExit(
        main(
            sys.argv[1],
            int(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_SAMPLE,
            int(sys.argv[3]) if len(sys.argv) > 3 else DEFAULT_BATCH,
        )
    )
