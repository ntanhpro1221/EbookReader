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
        SELECT stable_id, text, wav_path, wav_duration, voice_profile_id, generation_seed
        FROM segments
        WHERE wav_path IS NOT NULL AND wav_duration >= 2.0
        ORDER BY seq
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


def _perceptual_init() -> None:
    from ebook_reader.config import build_settings
    from ebook_reader.perceptual_qa import UTMOSNaturalnessVerifier

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


STAGES = {
    "perceptual": (_perceptual_init, _perceptual_job, lambda row: str(row["wav_path"])),
    "asr": (_asr_init, _asr_job, lambda row: (str(row["wav_path"]), str(row["text"]))),
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
        "results": sorted((str(key), round(float(value), 4)) for key, value in results),
    }


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project_root", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--stage", default="perceptual", choices=sorted(STAGES))
    parser.add_argument("--workers", default="1,2,4,6")
    parser.add_argument("--segments", type=int, default=12)
    parser.add_argument("--json", dest="json_out", type=Path, default=None)
    args = parser.parse_args()

    rows = _select_wavs(args.project_root, args.segments)
    if not rows:
        print("No committed WAV long enough to benchmark.", file=sys.stderr)
        return 65
    _initializer, _job, build = STAGES[args.stage]
    jobs = [build(row) for row in rows]
    args.out.mkdir(parents=True, exist_ok=True)

    idle = _gpu_snapshot()
    print(f"stage={args.stage}  jobs={len(jobs)}  cores={os.cpu_count()}")
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
