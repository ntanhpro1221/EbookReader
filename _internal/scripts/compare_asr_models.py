"""Compare ASR models head to head on audio this project already produced.

Whisper turbo transcribes Vietnamese consonants and vowels accurately but gets tones
wrong often enough to fail segments whose audio a listener confirmed was correct. Before
swapping the model in the pipeline - which changes the quality policy and forces clean
projects - this measures whether a Vietnamese-finetuned model actually does better, on
the same committed WAVs, against the same expected text.

Reports per model: word error rate, character similarity, the same two after folding tone
out of the comparison, and the tone-only difference rate. The gap between raw and folded
WER is the part of the error that is only about tone, which is what a Vietnamese-finetuned
model should shrink.

Downloads the compared model on first use. Nothing here touches a project or the pipeline.

Usage:
    python scripts/compare_asr_models.py <project-root> [--segments 60]
        [--model vinai/PhoWhisper-medium] [--json report.json]
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ebook_reader.asr import (  # noqa: E402
    normalize_transcript,
    tone_folded_transcript_metrics,
    transcript_metrics,
)


DEFAULT_MODEL = "vinai/PhoWhisper-medium"
TARGET_SAMPLE_RATE = 16_000


def _model_root() -> Path:
    runtime = Path(os.environ.get("EBOOK_READER_RUNTIME") or (
        Path(__file__).resolve().parent.parent / "runtime"
    ))
    return runtime / "models" / "asr_compare"


def select_segments(project_root: Path, wanted: int) -> list[dict[str, Any]]:
    database = (project_root / "project.sqlite3").resolve()
    connection = sqlite3.connect(f"file:{database.as_posix()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    rows = connection.execute(
        """
        SELECT stable_id, text, wav_path, wav_duration, status
        FROM segments
        WHERE wav_path IS NOT NULL AND wav_duration >= 1.0
        ORDER BY chapter_id, seq
        """
    ).fetchall()
    picked = [dict(row) for row in rows if Path(str(row["wav_path"])).is_file()]
    if len(picked) <= wanted:
        return picked
    # Spread the sample across the book rather than taking the first N, which would be
    # one chapter read mostly by the narrator.
    step = len(picked) / wanted
    return [picked[int(index * step)] for index in range(wanted)]


def _load_audio(path: Path) -> np.ndarray:
    import soundfile as sf
    from scipy.signal import resample_poly

    audio, sample_rate = sf.read(path, dtype="float32", always_2d=False)
    array = np.asarray(audio, dtype=np.float32).reshape(-1)
    if sample_rate != TARGET_SAMPLE_RATE:
        from math import gcd

        divisor = gcd(int(sample_rate), TARGET_SAMPLE_RATE)
        array = resample_poly(
            array, TARGET_SAMPLE_RATE // divisor, int(sample_rate) // divisor
        ).astype(np.float32)
    return array


def transcribe_baseline(rows: list[dict[str, Any]], device: str) -> dict[str, str]:
    import whisper

    from ebook_reader.config import build_settings

    settings = build_settings("high_quality")["asr"]
    model = whisper.load_model(
        str(settings.get("model", "turbo")),
        device=device,
        download_root=str(settings["download_root"]),
    )
    out: dict[str, str] = {}
    for index, row in enumerate(rows, 1):
        result = model.transcribe(
            _load_audio(Path(str(row["wav_path"]))),
            language="vi",
            task="transcribe",
            temperature=0.0,
            condition_on_previous_text=False,
            verbose=False,
            beam_size=int(settings.get("beam_size", 5)),
            fp16=device.startswith("cuda"),
        )
        out[str(row["stable_id"])] = str(result.get("text", "")).strip()
        if index % 20 == 0:
            print(f"    baseline {index}/{len(rows)}")
    del model
    return out


def transcribe_candidate(
    rows: list[dict[str, Any]],
    model_id: str,
    device: str,
) -> dict[str, str]:
    import torch
    from transformers import WhisperForConditionalGeneration, WhisperProcessor

    root = _model_root()
    root.mkdir(parents=True, exist_ok=True)
    processor = WhisperProcessor.from_pretrained(model_id, cache_dir=str(root))
    model = WhisperForConditionalGeneration.from_pretrained(
        model_id,
        cache_dir=str(root),
        dtype=torch.float16 if device.startswith("cuda") else torch.float32,
    ).to(device)
    model.eval()
    forced = processor.get_decoder_prompt_ids(language="vi", task="transcribe")
    out: dict[str, str] = {}
    for index, row in enumerate(rows, 1):
        audio = _load_audio(Path(str(row["wav_path"])))
        features = processor(
            audio, sampling_rate=TARGET_SAMPLE_RATE, return_tensors="pt"
        ).input_features.to(device, dtype=model.dtype)
        with torch.no_grad():
            tokens = model.generate(
                features,
                forced_decoder_ids=forced,
                num_beams=5,
                do_sample=False,
                max_new_tokens=256,
            )
        out[str(row["stable_id"])] = processor.batch_decode(
            tokens, skip_special_tokens=True
        )[0].strip()
        if index % 20 == 0:
            print(f"    {model_id} {index}/{len(rows)}")
    del model
    torch.cuda.empty_cache()
    return out


def score(rows: list[dict[str, Any]], transcripts: dict[str, str]) -> dict[str, Any]:
    raw_wers, raw_sims, folded_wers, folded_sims, tone_rates = [], [], [], [], []
    for row in rows:
        expected = str(row["text"])
        actual = transcripts.get(str(row["stable_id"]), "")
        if not normalize_transcript(actual):
            raw_wers.append(1.0)
            raw_sims.append(0.0)
            folded_wers.append(1.0)
            folded_sims.append(0.0)
            tone_rates.append(0.0)
            continue
        similarity, wer = transcript_metrics(expected, actual)
        folded_similarity, folded_wer, evidence = tone_folded_transcript_metrics(
            expected, actual
        )
        raw_wers.append(wer)
        raw_sims.append(similarity)
        folded_wers.append(folded_wer)
        folded_sims.append(folded_similarity)
        tone_rates.append(evidence["tone_only_difference_rate"])
    return {
        "segments": len(rows),
        "wer_median": round(float(np.median(raw_wers)), 4),
        "wer_mean": round(float(np.mean(raw_wers)), 4),
        "similarity_median": round(float(np.median(raw_sims)), 4),
        "tone_folded_wer_median": round(float(np.median(folded_wers)), 4),
        "tone_folded_wer_mean": round(float(np.mean(folded_wers)), 4),
        "tone_folded_similarity_median": round(float(np.median(folded_sims)), 4),
        "tone_only_rate_median": round(float(np.median(tone_rates)), 4),
        "tone_only_rate_mean": round(float(np.mean(tone_rates)), 4),
        "over_wer_030": int(sum(1 for value in raw_wers if value > 0.30)),
        "folded_over_wer_030": int(sum(1 for value in folded_wers if value > 0.30)),
    }


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project_root", type=Path)
    parser.add_argument("--segments", type=int, default=60)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--json", dest="json_out", type=Path, default=None)
    args = parser.parse_args()

    rows = select_segments(args.project_root, args.segments)
    if not rows:
        print("No committed WAV to compare.", file=sys.stderr)
        return 65
    print(f"comparing on {len(rows)} committed segments\n")

    started = time.monotonic()
    print("  transcribing with the current model")
    baseline = transcribe_baseline(rows, args.device)
    baseline_seconds = time.monotonic() - started

    started = time.monotonic()
    print(f"  transcribing with {args.model}")
    candidate = transcribe_candidate(rows, args.model, args.device)
    candidate_seconds = time.monotonic() - started

    report = {
        "current": {**score(rows, baseline), "seconds": round(baseline_seconds, 1)},
        args.model: {**score(rows, candidate), "seconds": round(candidate_seconds, 1)},
    }
    print()
    keys = (
        "wer_median", "wer_mean", "tone_folded_wer_median", "tone_only_rate_mean",
        "over_wer_030", "folded_over_wer_030", "seconds",
    )
    print(f"{'metric':28s} {'current':>12s} {args.model.split('/')[-1]:>22s}")
    print("-" * 66)
    for key in keys:
        left = report["current"][key]
        right = report[args.model][key]
        print(f"{key:28s} {left:>12} {right:>22}")

    if args.json_out is not None:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(
            json.dumps(
                {
                    "summary": report,
                    "transcripts": {
                        str(row["stable_id"]): {
                            "expected": str(row["text"]),
                            "current": baseline.get(str(row["stable_id"]), ""),
                            args.model: candidate.get(str(row["stable_id"]), ""),
                        }
                        for row in rows
                    },
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        print(f"\nJSON written to {args.json_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
