"""Measure how much of this machine each pipeline stage can actually use.

The pipeline runs one segment at a time everywhere, and a real run measured GPU at
14-18%, VRAM at 1.30 of 8.15 GB, CPU at 0.8 of 32 cores and the disk 99% idle. Nothing
is saturated because VieNeu and Whisper decode autoregressively: each step is a tiny
matmul that depends on the previous one, so the only way to raise utilisation is to run
several decodes at once.

Threads cannot do that here. `_set_generation_seed` and UTMOSv2's scoring both seed
*process-global* RNGs, so concurrency inside one process would make a segment's output
depend on its neighbours and break deterministic resume. Separate processes each own
their RNG, so this measures process pools.

This script answers, with numbers rather than estimates:

- how many concurrent workers of each kind fit in VRAM, including each process's own
  CUDA context, which is not free on Windows;
- what throughput each pool size actually delivers, and where it stops improving;
- whether the output stays byte-identical to the single-worker result.

Read-only with respect to any project: it reads committed WAVs and writes only into its
own scratch directory.

Usage:
    python scripts/benchmark_parallelism.py <project-root> --out <scratch-dir>
        [--stage perceptual|tts|asr] [--workers 1,2,3,4] [--segments 12]
"""

from __future__ import annotations

import argparse
import json
import multiprocessing as mp
import os
import sqlite3
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def _gpu_snapshot() -> dict[str, float]:
    """Best-effort GPU utilisation and VRAM, so a missing nvidia-smi is not fatal."""
    import subprocess

    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=utilization.gpu,memory.used,memory.total",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
        if result.returncode != 0:
            return {}
        parts = [part.strip() for part in result.stdout.strip().splitlines()[0].split(",")]
        return {
            "gpu_percent": float(parts[0]),
            "vram_used_mib": float(parts[1]),
            "vram_total_mib": float(parts[2]),
        }
    except Exception:  # noqa: BLE001
        return {}


def _select_wavs(project_root: Path, wanted: int) -> list[dict[str, Any]]:
    database = (project_root / "project.sqlite3").resolve()
    connection = sqlite3.connect(f"file:{database.as_posix()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    rows = connection.execute(
        """
        SELECT
            s.stable_id, s.text, s.wav_path, s.wav_duration, s.voice_profile_id,
            s.generation_seed, s.kind, s.speaker, s.emotion, s.intensity, s.pace,
            s.volume, s.warning_code,
            v.preset_name, v.engine, v.voice_key, v.pitch_semitones
        FROM segments AS s
        LEFT JOIN voice_profiles AS v ON v.id = s.voice_profile_id
        WHERE s.wav_path IS NOT NULL AND s.wav_duration >= 2.0
          AND v.preset_name IS NOT NULL AND s.generation_seed IS NOT NULL
        ORDER BY s.seq
        """
    ).fetchall()
    picked = []
    for row in rows:
        if not Path(str(row["wav_path"])).is_file():
            continue
        picked.append(dict(row))
        if len(picked) >= wanted:
            break
    return picked


# --- perceptual stage -------------------------------------------------------------

_VERIFIER: list[Any] = []


def _pin_worker_threads() -> None:
    """Stop each worker from claiming every core.

    Torch defaults to one thread per core, so N worker processes ask for N x 32 threads on
    this machine and spend the difference context switching. Measured: 4 workers reached
    1.66x, then 8 and 16 fell back towards the single-worker time. The pool size is only
    meaningful once each member is bounded.
    """
    import torch

    threads = max(1, int(os.environ.get("EBOOK_READER_WORKER_THREADS", "1")))
    torch.set_num_threads(threads)


def _perceptual_init() -> None:
    from ebook_reader.config import build_settings
    from ebook_reader.perceptual_qa import UTMOSNaturalnessVerifier

    _pin_worker_threads()

    settings = build_settings("high_quality")
    settings["perceptual_qa"] = {
        **settings["perceptual_qa"],
        "enabled": True,
        "device": "cpu",
    }
    verifier = UTMOSNaturalnessVerifier(settings, lambda _message: None)
    if not verifier.load():
        raise RuntimeError("UTMOSv2 unavailable in worker")
    _VERIFIER.append(verifier)


def _perceptual_job(wav_path: str) -> tuple[str, float]:
    return wav_path, float(_VERIFIER[0]._score(Path(wav_path)))


# --- ASR stage --------------------------------------------------------------------

_WHISPER: list[Any] = []


def _asr_init() -> None:
    from ebook_reader.config import build_settings
    from ebook_reader.asr import WhisperVerifier

    settings = build_settings("high_quality")
    verifier = WhisperVerifier(settings, lambda _message: None)
    verifier.load()
    _WHISPER.append(verifier)


def _asr_job(payload: tuple[str, str]) -> tuple[str, float]:
    wav_path, expected = payload
    result = _WHISPER[0].verify(expected, Path(wav_path))
    return wav_path, float(result.get("similarity", 0.0))


# --- TTS stage --------------------------------------------------------------------

_ENGINE: list[Any] = []


def _tts_init() -> None:
    from ebook_reader.config import build_settings
    from ebook_reader.tts import VieNeuEngine

    _pin_worker_threads()

    engine = VieNeuEngine(build_settings("high_quality"), lambda _message: None)
    engine.load()
    _ENGINE.append(engine)


def _tts_job(payload: dict[str, Any]) -> tuple[str, float]:
    """Regenerate one segment and return a checksum of the waveform.

    The seed and voice come from the committed row, so a correct pool reproduces the
    audio the single-worker run produced. The checksum is the first 48 bits of the
    SHA-256 as a float: 48 bits is exact in float64, so the comparison stays lossless
    while fitting the (name, number) shape every stage reports.
    """
    import hashlib

    import numpy as np

    row = dict(payload)
    audio = _ENGINE[0].generate_one(
        {
            "kind": row["kind"],
            "speaker": row["speaker"],
            "text": row["text"],
            "emotion": row["emotion"],
            "intensity": row["intensity"],
            "pace": row["pace"],
            "volume": row["volume"],
            "warning_code": row["warning_code"],
        },
        {
            "engine": row["engine"],
            "preset_name": row["preset_name"],
            "voice_key": row["voice_key"],
            "id": row["voice_profile_id"],
            "pitch_semitones": row["pitch_semitones"],
        },
        int(row["generation_seed"]),
    )
    array = np.asarray(audio, dtype=np.float32).reshape(-1)
    digest = hashlib.sha256(array.tobytes()).hexdigest()
    return str(row["stable_id"]), float(int(digest[:12], 16))


def _tts_payload(row: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "stable_id", "text", "kind", "speaker", "emotion", "intensity", "pace",
        "volume", "warning_code", "engine", "preset_name", "voice_key",
        "voice_profile_id", "pitch_semitones", "generation_seed",
    )
    return {key: row[key] for key in keys}


STAGES = {
    "perceptual": (_perceptual_init, _perceptual_job, lambda row: str(row["wav_path"])),
    "asr": (_asr_init, _asr_job, lambda row: (str(row["wav_path"]), str(row["text"]))),
    "tts": (_tts_init, _tts_job, _tts_payload),
}


def run_stage(stage: str, workers: int, jobs: list[Any]) -> dict[str, Any]:
    initializer, job, _build = STAGES[stage]
    started = time.monotonic()
    peak = {"gpu_percent": 0.0, "vram_used_mib": 0.0}
    results: list[Any] = []
    if workers <= 1:
        initializer()
        for item in jobs:
            results.append(job(item))
            snapshot = _gpu_snapshot()
            for key in peak:
                peak[key] = max(peak[key], snapshot.get(key, 0.0))
    else:
        context = mp.get_context("spawn")
        with context.Pool(processes=workers, initializer=initializer) as pool:
            pending = pool.imap_unordered(job, jobs)
            for value in pending:
                results.append(value)
                snapshot = _gpu_snapshot()
                for key in peak:
                    peak[key] = max(peak[key], snapshot.get(key, 0.0))
    elapsed = time.monotonic() - started
    return {
        "stage": stage,
        "workers": workers,
        "jobs": len(jobs),
        "seconds": round(elapsed, 2),
        "jobs_per_minute": round(len(jobs) / elapsed * 60.0, 2) if elapsed > 0 else 0.0,
        "peak_gpu_percent": peak["gpu_percent"],
        "peak_vram_mib": peak["vram_used_mib"],
        # Full precision, never rounded. An earlier version rounded to four decimals and
        # therefore reported "identical" across pool sizes while the scores actually
        # differed at 5e-07 - torch sums a matmul's pieces in thread completion order, so
        # the thread count changes the last bits. A comparison that cannot see that is
        # worse than no comparison, because it is believed.
        "results": sorted((str(key), float(value)) for key, value in results),
    }


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project_root", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--stage", default="perceptual", choices=sorted(STAGES))
    parser.add_argument("--workers", default="1,2,4,6")
    parser.add_argument("--segments", type=int, default=12)
    parser.add_argument(
        "--worker-threads",
        type=int,
        default=1,
        help="torch threads per worker process; 0 leaves torch at its default",
    )
    parser.add_argument("--json", dest="json_out", type=Path, default=None)
    args = parser.parse_args()

    if args.worker_threads:
        os.environ["EBOOK_READER_WORKER_THREADS"] = str(args.worker_threads)
    rows = _select_wavs(args.project_root, args.segments)
    if not rows:
        print("No committed WAV long enough to benchmark.", file=sys.stderr)
        return 65
    _initializer, _job, build = STAGES[args.stage]
    jobs = [build(row) for row in rows]
    args.out.mkdir(parents=True, exist_ok=True)

    idle = _gpu_snapshot()
    print(
        f"stage={args.stage}  jobs={len(jobs)}  cores={os.cpu_count()}  "
        f"threads/worker={args.worker_threads or 'torch default'}"
    )
    if idle:
        print(
            f"idle GPU {idle['gpu_percent']:.0f}%  "
            f"VRAM {idle['vram_used_mib']:.0f}/{idle['vram_total_mib']:.0f} MiB"
        )
    print()

    reports = []
    baseline: list[tuple[str, float]] | None = None
    for count in [int(part) for part in args.workers.split(",") if part.strip()]:
        report = run_stage(args.stage, count, jobs)
        if baseline is None:
            baseline = report["results"]
            report["identical_to_single_worker"] = True
        else:
            report["identical_to_single_worker"] = report["results"] == baseline
        reports.append(report)
        speedup = reports[0]["seconds"] / report["seconds"] if report["seconds"] else 0.0
        print(
            f"  workers={count:2d}  {report['seconds']:7.1f}s  "
            f"{report['jobs_per_minute']:6.1f} jobs/min  "
            f"speedup {speedup:4.2f}x  "
            f"peak GPU {report['peak_gpu_percent']:3.0f}%  "
            f"peak VRAM {report['peak_vram_mib']:5.0f} MiB  "
            f"{'identical' if report['identical_to_single_worker'] else 'OUTPUT DIFFERS'}"
        )

    if args.json_out is not None:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(
            json.dumps(reports, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"\nJSON written to {args.json_out}")
    return 0


if __name__ == "__main__":
    mp.freeze_support()
    raise SystemExit(main())
