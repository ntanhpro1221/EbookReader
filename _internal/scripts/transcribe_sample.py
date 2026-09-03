"""Transcribe the same takes with one ASR engine and write down what it heard.

ASR is the most expensive stage of a run - 3,870 seconds on alpha.25 against TTS's 2,055 -
and the project uses openai-whisper. faster-whisper runs the same weights through
CTranslate2 and is usually several times quicker on a GPU, but "usually" is not a
measurement and a transcriber that hears differently changes which takes pass. So this
writes down what one engine heard, and compare_asr_engines.py judges two such files
against the text the voice was actually given.

Two engines cannot share one virtual environment safely while a book job is running:
installing faster-whisper pulls ctranslate2 and tokenizers and may move numpy under a job
that is using it. So this script is deliberately small and dependency-light - it needs its
engine and soundfile, nothing from ebook_reader - and is meant to be run once per venv.

    <venv-a>/python scripts/transcribe_sample.py <project_root> openai out-openai.json 60
    <venv-b>/python scripts/transcribe_sample.py <project_root> faster out-faster.json 60
"""
from __future__ import annotations

import json
import os
import sqlite3
import sys
import time
from pathlib import Path


def _pick(database: Path, sample: int) -> list[tuple[str, str, float]]:
    connection = sqlite3.connect(f"file:{database}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    rows = connection.execute(
        "SELECT stable_id, wav_path, wav_duration FROM segments "
        "WHERE wav_path IS NOT NULL AND status != 'failed' "
        "ORDER BY (id * 2654435761) % 1000003 LIMIT ?",
        (sample,),
    ).fetchall()
    connection.close()
    return [
        (str(row["stable_id"]), str(row["wav_path"]), float(row["wav_duration"] or 0.0))
        for row in rows
    ]


def _openai(paths: list[tuple[str, str, float]]) -> list[dict]:
    import whisper

    model = whisper.load_model("turbo", device="cuda")
    results = []
    for stable_id, wav_path, duration in paths:
        started = time.perf_counter()
        # The same options the pipeline uses, including the length rule for beam search.
        options = {
            "language": "vi",
            "task": "transcribe",
            "fp16": True,
            "temperature": 0.0,
            "condition_on_previous_text": False,
            "verbose": False,
        }
        if duration > 2.5:
            options["beam_size"] = 5
        answer = model.transcribe(wav_path, **options)
        results.append(
            {
                "stable_id": stable_id,
                "transcript": str(answer.get("text", "")).strip(),
                "seconds": time.perf_counter() - started,
                "duration": duration,
            }
        )
    return results


def _faster(paths: list[tuple[str, str, float]]) -> list[dict]:
    # CTranslate2 links cuBLAS and cuDNN at load time and does not ship them. torch does,
    # in its own lib directory, so an isolated venv can borrow those without the two
    # environments sharing anything else. EBOOK_READER_TORCH_LIB names that directory.
    torch_lib = os.environ.get("EBOOK_READER_TORCH_LIB", "")
    if torch_lib and hasattr(os, "add_dll_directory") and Path(torch_lib).is_dir():
        os.add_dll_directory(torch_lib)

    from faster_whisper import WhisperModel

    # "turbo" resolves to the same large-v3-turbo weights the project already loads
    # through openai-whisper, so this compares two runtimes rather than two models.
    model = WhisperModel("turbo", device="cuda", compute_type="float16")
    results = []
    for stable_id, wav_path, duration in paths:
        started = time.perf_counter()
        segments, _info = model.transcribe(
            wav_path,
            language="vi",
            task="transcribe",
            temperature=0.0,
            condition_on_previous_text=False,
            beam_size=5 if duration > 2.5 else 1,
        )
        text = "".join(segment.text for segment in segments).strip()
        results.append(
            {
                "stable_id": stable_id,
                "transcript": text,
                "seconds": time.perf_counter() - started,
                "duration": duration,
            }
        )
    return results


def main(project_root: str, engine: str, out_path: str, sample: int) -> int:
    database = Path(project_root) / "project.sqlite3"
    if not database.is_file():
        print(f"không tìm thấy project: {database}")
        return 2
    paths = _pick(database, sample)
    paths = [item for item in paths if Path(item[1]).is_file()]
    if not paths:
        print("không có WAV nào")
        return 1

    runner = {"openai": _openai, "faster": _faster}.get(engine)
    if runner is None:
        print("engine phải là openai hoặc faster")
        return 2

    started = time.perf_counter()
    results = runner(paths)
    elapsed = time.perf_counter() - started
    Path(out_path).write_text(
        json.dumps(
            {"engine": engine, "total_seconds": elapsed, "results": results},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"{engine}: {len(results)} bản thu trong {elapsed:.1f}s -> {out_path}")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 5:
        print(__doc__)
        raise SystemExit(2)
    raise SystemExit(main(sys.argv[1], sys.argv[2], sys.argv[3], int(sys.argv[4])))
