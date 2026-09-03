"""Can concurrent decode calls fill the idle GPU without touching transcript boundaries?

Two measurements led here. Batching gave 1.11x, not the 3-5x an idle GPU implied. Then
padding tests showed why: the encoder charges per 30-second window regardless of what is in
it, and at a 4.8s median take, 84% of every window is padding. BatchedInferencePipeline
batches windows *within one file*, so it never shares that cost across segments.

Packing several segments into one window would share it - and would mix transcript
boundaries, which the locked-name anchors, the hallucination timeline check and the
per-segment similarity all forbid. This asks the cheaper question instead: keep one call per
segment, exactly as today, and simply run several calls at once.

Nothing downstream changes. Each segment still gets its own transcript from its own audio.
CTranslate2 executes concurrent translate() calls in parallel when the model is built with
num_workers > 1, so the only question is whether the card has the headroom to do it - and
whether the transcripts come back identical, because a decode that changes what the voice is
heard saying is not an optimisation.

    python scripts/measure_concurrent_asr.py <project_root> [sample] [max_workers]

Reads a finished project's WAVs and writes nothing.
"""
from __future__ import annotations

import sqlite3
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

DEFAULT_SAMPLE = 48
DEFAULT_MAX_WORKERS = 4


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


def main(project_root: str, sample: int, max_workers: int) -> int:
    database = Path(project_root) / "project.sqlite3"
    if not database.is_file():
        print(f"không tìm thấy project: {database}")
        return 2
    takes = _takes(database, sample)
    if len(takes) < 8:
        print("cần ít nhất 8 bản thu")
        return 1

    import torch  # noqa: F401  - imported for the CUDA libraries CTranslate2 links
    from faster_whisper import WhisperModel

    from ebook_reader.asr import load_audio_for_whisper, normalize_transcript

    options = {
        "language": "vi",
        "task": "transcribe",
        "temperature": 0.0,
        "condition_on_previous_text": False,
    }

    # Decoding is what is being timed, so the audio is loaded once up front. Loading is 0.7%
    # of a decode either way, but leaving it in would let thread contention on the CPU side
    # masquerade as a GPU result.
    audio = [(load_audio_for_whisper(Path(path)), duration) for path, duration in takes]

    def _run(model: WhisperModel, workers: int) -> tuple[float, list[str]]:
        def _one(item: tuple[object, float]) -> str:
            clip, duration = item
            segments, _info = model.transcribe(
                clip, beam_size=5 if duration > 2.5 else 1, **options
            )
            return "".join(part.text for part in segments).strip()

        started = time.perf_counter()
        if workers == 1:
            out = [_one(item) for item in audio]
        else:
            with ThreadPoolExecutor(max_workers=workers) as pool:
                out = list(pool.map(_one, audio))
        return time.perf_counter() - started, out

    count = len(takes)
    total_audio = sum(duration for _clip, duration in audio)
    print()
    print(f"{count} bản thu, {total_audio:.1f}s âm thanh")
    print()
    print(f"{'luồng':>6}  {'tổng':>9}  {'mỗi bản':>9}  {'nhanh hơn':>10}  {'bản ghi khác':>13}")

    baseline_seconds = 0.0
    baseline_text: list[str] = []
    for workers in [1] + [value for value in (2, 3, 4, 6, 8) if 1 < value <= max_workers]:
        # num_workers must match the concurrency: CTranslate2 serialises calls beyond it.
        model = WhisperModel(
            "turbo", device="cuda", compute_type="float16", num_workers=workers
        )
        model.transcribe(audio[0][0], beam_size=1, **options)[0].__next__()  # warm
        seconds, texts = _run(model, workers)
        if workers == 1:
            baseline_seconds, baseline_text = seconds, texts
            differing = 0
        else:
            differing = sum(
                1
                for left, right in zip(baseline_text, texts)
                if normalize_transcript(left) != normalize_transcript(right)
            )
        speedup = baseline_seconds / seconds if seconds else 0.0
        print(
            f"{workers:6d}  {seconds:8.1f}s  {seconds / count:8.3f}s"
            f"  {speedup:9.2f}x  {differing:6d}/{count}"
        )
        del model

    print()
    print(
        "Chỉ đáng làm khi nhanh hơn rõ VÀ cột bản ghi khác bằng 0. Khác một bản ghi thôi "
        "nghĩa là nó đã thành một engine khác, không còn là một tối ưu - và đổi engine thì "
        "phải xác minh lại cả quyển sách."
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
            int(sys.argv[3]) if len(sys.argv) > 3 else DEFAULT_MAX_WORKERS,
        )
    )
