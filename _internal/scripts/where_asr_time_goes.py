"""If ASR's time is not parallelisable GPU work, what is it?

Batching the decode gave 1.11x, not the 3-5x an idle GPU implied, so the time is somewhere
batching does not reach. This asks where, before anyone builds anything else.

Two questions, both answerable by timing what already exists:

  - How much of a decode is the project's own CPU-side audio loading - soundfile read plus
    the polyphase resample to 16 kHz - rather than the model?
  - Does a decode cost scale with the length of the audio, or is it mostly a fixed price
    per call? A large intercept means the run pays for having 948 segments, not for having
    2,000 seconds of speech, and that changes what is worth optimising: fewer, longer calls
    rather than faster ones.

    python scripts/where_asr_time_goes.py <project_root> [sample]

Reads a finished project's WAVs and writes nothing.
"""
from __future__ import annotations

import sqlite3
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ebook_reader.asr import load_audio_for_whisper  # noqa: E402

DEFAULT_SAMPLE = 60


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


def _fit(xs: list[float], ys: list[float]) -> tuple[float, float]:
    """Least squares y = intercept + slope * x, written out to keep the deps light."""
    n = len(xs)
    mean_x = statistics.fmean(xs)
    mean_y = statistics.fmean(ys)
    denominator = sum((x - mean_x) ** 2 for x in xs)
    slope = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys)) / denominator if denominator else 0.0
    return mean_y - slope * mean_x, slope


def main(project_root: str, sample: int) -> int:
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

    model = WhisperModel("turbo", device="cuda", compute_type="float16")
    options = {
        "language": "vi",
        "task": "transcribe",
        "temperature": 0.0,
        "condition_on_previous_text": False,
    }
    load_audio_for_whisper(Path(takes[0][0]))
    list(model.transcribe(load_audio_for_whisper(Path(takes[0][0])), beam_size=1, **options)[0])

    durations: list[float] = []
    load_seconds: list[float] = []
    decode_seconds: list[float] = []
    for path, duration in takes:
        started = time.perf_counter()
        audio = load_audio_for_whisper(Path(path))
        loaded = time.perf_counter()
        segments, _info = model.transcribe(
            audio, beam_size=5 if duration > 2.5 else 1, **options
        )
        list(segments)  # the generator is where the work happens
        finished = time.perf_counter()
        durations.append(duration)
        load_seconds.append(loaded - started)
        decode_seconds.append(finished - loaded)

    total_load = sum(load_seconds)
    total_decode = sum(decode_seconds)
    total_audio = sum(durations)
    count = len(takes)

    print()
    print(f"{count} bản thu, {total_audio:.1f}s âm thanh")
    print(f"  nạp + resample : {total_load:7.2f}s  ({total_load / count * 1000:6.1f} ms/bản)"
          f"  {total_load / (total_load + total_decode):5.1%} tổng")
    print(f"  giải mã        : {total_decode:7.2f}s  ({total_decode / count * 1000:6.1f} ms/bản)"
          f"  {total_decode / (total_load + total_decode):5.1%} tổng")
    print(f"  tỉ lệ thời gian thực: {(total_load + total_decode) / total_audio:.3f}x")

    intercept, slope = _fit(durations, decode_seconds)
    print()
    print("  giải mã theo độ dài âm thanh (bình phương tối thiểu):")
    print(f"    phí cố định mỗi lượt : {intercept * 1000:7.1f} ms")
    print(f"    thêm mỗi giây âm thanh: {slope * 1000:7.1f} ms")
    median_duration = statistics.median(durations)
    fixed_share = intercept / (intercept + slope * median_duration) if (intercept + slope * median_duration) else 0.0
    print(f"    với bản thu trung vị {median_duration:.1f}s: phí cố định chiếm {fixed_share:.0%}")

    print()
    # Three readings, not two. The first version of this script asked `fixed_share > 0.5`
    # and printed "cost scales with audio length" for a measured 46% - a near-even split
    # read as one of its two extremes. A verdict that rounds 46 to zero is worse than no
    # verdict, so the middle band now says what it actually is.
    if fixed_share > 0.65:
        print(
            "Phần lớn chi phí là phí cố định mỗi lượt gọi, không phải xử lý âm thanh. Lần "
            "chạy đang trả tiền cho việc có bao nhiêu segment chứ không phải cho số giây "
            "tiếng nói - nên hướng đúng là gọi ít lần hơn, không phải gọi nhanh hơn."
        )
    elif fixed_share >= 0.35:
        print(
            f"Chi phí chia gần đôi: {fixed_share:.0%} cố định mỗi lượt, {1 - fixed_share:.0%} "
            "theo độ dài. Không có đòn bẩy nào một mình giải quyết được - và đây chính là "
            "lý do gộp lô chỉ được 1,11 lần: nó bỏ bớt một phần phí gọi mà không đụng tới "
            "nửa còn lại. Gói nhiều segment vào một cửa sổ mới chạm được phần cố định, "
            "nhưng nó trộn ranh giới bản ghi nên phải đo lợi ích thật trước."
        )
    else:
        print(
            "Chi phí tỉ lệ với độ dài âm thanh. Gọi ít lần hơn không giúp gì; muốn nhanh "
            "hơn thì phải xử lý mỗi giây âm thanh rẻ hơn."
        )
    return 0


if __name__ == "__main__":
    if not 1 <= len(sys.argv) - 1 <= 2:
        print(__doc__)
        raise SystemExit(2)
    raise SystemExit(
        main(sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_SAMPLE)
    )
