"""Measure how far audio can be tempo-shifted before it stops sounding natural.

The VieNeu Python library has no speaking-rate parameter (its desktop app's
0.5-3.0 speed control lives in the Rust layer), so the only way to make the
director's `pace` decision audible is pitch-preserving post-processing. FFmpeg
`atempo` does exactly that, and the existing tempo rescue already relies on it.

Before widening that from a rescue into a delivery lever, the usable factor
range has to be measured rather than guessed. This script takes committed
segment WAVs from a real project, renders each at a range of tempo factors, and
scores every result with the same UTMOSv2 verifier the pipeline uses, reporting
the MOS delta against the unmodified original.

Read-only with respect to the project: variants are written to a scratch
directory and the project's own WAVs are never touched.

Usage:
    python scripts/calibrate_tempo.py <project-root> --out <dir> [--device cpu]
        [--factors 0.88,0.92,0.94,0.97,1.03,1.06,1.10] [--segments 12]
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import statistics
import sys
from pathlib import Path
from typing import Any

import soundfile as sf

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ebook_reader.audio_io import signal_metrics  # noqa: E402
from ebook_reader.config import build_settings  # noqa: E402
from ebook_reader.io_utils import ffmpeg_executable, run_hidden  # noqa: E402
from ebook_reader.perceptual_qa import UTMOSNaturalnessVerifier  # noqa: E402


DEFAULT_FACTORS = (0.88, 0.92, 0.94, 0.97, 1.03, 1.06, 1.10)
# UTMOSv2 needs enough audio to be meaningful; the pipeline exempts anything shorter.
MIN_CALIBRATION_SECONDS = 2.0


def _ffmpeg_number(value: float) -> str:
    return f"{value:.6f}".rstrip("0").rstrip(".")


def render_tempo(source: Path, destination: Path, factor: float) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    command = [
        ffmpeg_executable(),
        "-hide_banner",
        "-nostats",
        "-loglevel",
        "error",
        "-nostdin",
        "-y",
        "-i",
        str(source),
        "-map",
        "0:a:0",
        "-vn",
        "-af",
        f"atempo={_ffmpeg_number(factor)}",
        "-ac",
        "1",
        "-c:a",
        "pcm_s16le",
        str(destination),
    ]
    result = run_hidden(command, timeout=600, check=False)
    if result.returncode != 0:
        raise RuntimeError(f"atempo {factor} failed: {result.stderr[-2000:]}")


def select_segments(connection: sqlite3.Connection, wanted: int) -> list[dict[str, Any]]:
    """Pick a spread of committed segments across kind, speaker and duration."""
    rows = list(
        connection.execute(
            """
            SELECT s.stable_id, s.kind, s.speaker, s.emotion, s.pace, s.text,
                   s.wav_path, s.wav_duration, s.voice_profile_id, s.signal_json
            FROM segments s
            WHERE s.wav_path IS NOT NULL AND s.status IN ('verified', 'warning')
            ORDER BY s.chapter_id, s.seq
            """
        )
    )
    usable = [
        dict(row)
        for row in rows
        if float(row["wav_duration"] or 0.0) >= MIN_CALIBRATION_SECONDS
        and Path(str(row["wav_path"])).is_file()
    ]
    if not usable:
        return []
    by_bucket: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for item in usable:
        key = (str(item["kind"]), str(item["voice_profile_id"] or ""))
        by_bucket.setdefault(key, []).append(item)
    picked: list[dict[str, Any]] = []
    while len(picked) < wanted and any(by_bucket.values()):
        for bucket in list(by_bucket.values()):
            if not bucket or len(picked) >= wanted:
                continue
            picked.append(bucket.pop(len(bucket) // 2))
    return picked


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project_root", type=Path)
    parser.add_argument("--out", type=Path, required=True, help="Scratch directory for variants")
    parser.add_argument("--segments", type=int, default=12)
    parser.add_argument("--device", default="cpu", help="UTMOSv2 device (cpu keeps the GPU free)")
    parser.add_argument("--factors", default=",".join(str(f) for f in DEFAULT_FACTORS))
    parser.add_argument("--json", dest="json_out", type=Path, default=None)
    args = parser.parse_args()

    factors = [float(part) for part in args.factors.split(",") if part.strip()]
    database = (args.project_root / "project.sqlite3").resolve()
    if not database.is_file():
        print(f"No project database at {database}", file=sys.stderr)
        return 66
    connection = sqlite3.connect(f"file:{database.as_posix()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    segments = select_segments(connection, args.segments)
    if not segments:
        print("No committed segment WAV long enough to calibrate.", file=sys.stderr)
        return 65
    print(f"Calibrating on {len(segments)} segment(s) at factors {factors}")

    settings = build_settings("high_quality")
    settings["perceptual_qa"] = {
        **settings.get("perceptual_qa", {}),
        "enabled": True,
        "device": args.device,
    }
    verifier = UTMOSNaturalnessVerifier(settings, lambda message: print(f"  {message}"))
    if not verifier.load():
        print("UTMOSv2 unavailable; cannot calibrate.", file=sys.stderr)
        return 69

    results: list[dict[str, Any]] = []
    try:
        for index, segment in enumerate(segments):
            source = Path(str(segment["wav_path"]))
            base_score = verifier._score(source)
            audio, sample_rate = sf.read(source, dtype="float32", always_2d=False)
            base_metrics = signal_metrics(audio, int(sample_rate))
            entry = {
                "stable_id": str(segment["stable_id"]),
                "kind": str(segment["kind"]),
                "speaker": str(segment["speaker"]),
                "pace": str(segment["pace"]),
                "duration": float(segment["wav_duration"] or 0.0),
                "base_mos": base_score,
                "base_rms": base_metrics["rms"],
                "variants": {},
            }
            for factor in factors:
                variant = args.out / f"{segment['stable_id']}_t{int(round(factor * 1000)):04d}.wav"
                render_tempo(source, variant, factor)
                score = verifier._score(variant)
                entry["variants"][f"{factor:.2f}"] = {
                    "mos": score,
                    "delta": score - base_score,
                }
            results.append(entry)
            print(
                f"[{index + 1}/{len(segments)}] {entry['stable_id']} "
                f"base={base_score:.3f} "
                + " ".join(
                    f"{key}:{value['delta']:+.3f}" for key, value in entry["variants"].items()
                )
            )
    finally:
        verifier.unload()

    print("\n=== mean MOS delta vs unmodified original ===")
    summary = {}
    for factor in factors:
        key = f"{factor:.2f}"
        deltas = [item["variants"][key]["delta"] for item in results]
        summary[key] = {
            "mean_delta": round(statistics.mean(deltas), 4),
            "median_delta": round(statistics.median(deltas), 4),
            "worst_delta": round(min(deltas), 4),
            "regressed": sum(1 for value in deltas if value < -0.10),
            "count": len(deltas),
        }
        stats = summary[key]
        print(
            f"  atempo {key}: mean {stats['mean_delta']:+.3f}  "
            f"median {stats['median_delta']:+.3f}  worst {stats['worst_delta']:+.3f}  "
            f"regressed>0.10: {stats['regressed']}/{stats['count']}"
        )

    if args.json_out is not None:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(
            json.dumps({"summary": summary, "segments": results}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"\nJSON written to {args.json_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
