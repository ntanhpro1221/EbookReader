"""Read the same sentences in every preset and measure who stays faithful to the text.

Run data cannot answer whether a regional accent hurts, because each voice reads
different sentences: a preset with 4 segments looks bad if those 4 happen to be hard.
This removes that confound by giving every preset the *same* text.

What it measures, per preset:

- overall WER and similarity against the source text;
- **tone error rate** specifically - Vietnamese tone carries lexical meaning, so a voice
  whose tones drift from the written form is misheard by people, not just by Whisper.
  A tone error is a word that matches exactly once diacritics are stripped but differs
  with them, which separates "wrong tone" from "wrong word".

The distinction matters for the casting decision: Southern presets mostly trip Whisper on
names and on the s/x, d/gi mergers, which is instrument bias. Central presets appeared to
miss tones on ordinary vocabulary, which would be a real comprehension cost. This script
is what decides between those two stories.

Writes only into its own scratch directory; touches no project.

Usage:
    python scripts/compare_voice_regions.py --out <scratch-dir> [--presets "A,B"]
        [--json report.json]
"""

from __future__ import annotations

import argparse
import json
import sys
import unicodedata
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ebook_reader.asr import (  # noqa: E402
    WhisperVerifier,
    normalize_transcript,
    transcript_metrics,
)
from ebook_reader.audio_io import atomic_write_wav  # noqa: E402
from ebook_reader.config import build_settings  # noqa: E402
from ebook_reader.tts import VieNeuEngine  # noqa: E402
from ebook_reader.voice_catalog import VIENEU_PRESETS  # noqa: E402


# Ordinary narrative prose with a dense spread of tones, no foreign names: names would
# reintroduce exactly the Latin-spelling confound this script exists to remove.
PROBE_SENTENCES = (
    "Thứ mà ta truy cầu là chân lý của ma thuật, chứ không phải thần linh nào hết.",
    "Cô gái ấy ngày trước thuần khiết và nồng nhiệt, nhưng giờ đã khác hẳn.",
    "Con cứ coi như không nghe thấy gì là được, đừng bận tâm làm chi cho mệt.",
    "Trời vừa sáng, cha đã nhờ thằng nhóc hàng xóm báo tin tới tận nơi.",
    "Khói dày bốc lên, mỗi hơi hít vào đều khiến phổi và yết hầu bỏng rát.",
)
SEED = 20260831


def _strip_tones(word: str) -> str:
    return "".join(
        character
        for character in unicodedata.normalize("NFD", word)
        if unicodedata.category(character) != "Mn"
    )


def tone_error_rate(expected: str, actual: str) -> tuple[float, int, int]:
    """Fraction of aligned words that are right except for their tone.

    Compared position by position on equal-length runs only, so a dropped or inserted
    word does not silently shift every later word and inflate the count.
    """
    expected_words = normalize_transcript(expected).split()
    actual_words = normalize_transcript(actual).split()
    compared = min(len(expected_words), len(actual_words))
    tone_errors = 0
    for index in range(compared):
        left, right = expected_words[index], actual_words[index]
        if left != right and _strip_tones(left) == _strip_tones(right):
            tone_errors += 1
    return (tone_errors / compared if compared else 0.0), tone_errors, compared


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--presets", default="")
    parser.add_argument("--json", dest="json_out", type=Path, default=None)
    args = parser.parse_args()

    wanted = {name.strip() for name in args.presets.split(",") if name.strip()}
    presets = [
        preset
        for preset in VIENEU_PRESETS
        if not wanted or str(preset["name"]) in wanted
    ]
    if not presets:
        print("No preset selected.", file=sys.stderr)
        return 64

    settings = build_settings("high_quality")
    args.out.mkdir(parents=True, exist_ok=True)
    engine = VieNeuEngine(settings, lambda message: print(f"  {message}"))
    verifier = WhisperVerifier(settings, lambda message: print(f"  {message}"))

    rows: list[dict[str, Any]] = []
    try:
        engine.load()
        for preset in presets:
            name = str(preset["name"])
            if name not in engine.voices:
                print(f"  skip {name}: not offered by the installed VieNeu")
                continue
            profile = {
                "engine": "vieneu",
                "preset_name": name,
                "voice_key": f"probe_{name}",
                "id": 0,
            }
            for index, sentence in enumerate(PROBE_SENTENCES):
                row = {
                    "kind": "narration",
                    "speaker": "NARRATOR",
                    "text": sentence,
                    "emotion": "neutral",
                    "intensity": 0,
                    "pace": "normal",
                    "volume": "normal",
                    "warning_code": "",
                }
                audio = engine.generate_one(row, profile, SEED + index)
                path = args.out / f"{name.replace(' ', '_')}_{index}.wav"
                atomic_write_wav(
                    path,
                    audio,
                    engine.sample_rate,
                    sentence,
                    settings,
                    segment=row,
                )
                rows.append({"preset": name, "region": str(preset["region"]), "index": index,
                             "text": sentence, "wav": str(path)})
        engine.unload()

        verifier.load()
        for row in rows:
            result = verifier.verify(str(row["text"]), Path(str(row["wav"])))
            transcript = str(result.get("transcript", ""))
            similarity, wer = transcript_metrics(
                normalize_transcript(str(row["text"])),
                normalize_transcript(transcript),
            )
            rate, errors, compared = tone_error_rate(str(row["text"]), transcript)
            row.update(
                {
                    "transcript": transcript,
                    "similarity": similarity,
                    "wer": wer,
                    "tone_error_rate": rate,
                    "tone_errors": errors,
                    "words_compared": compared,
                }
            )
    finally:
        verifier.unload()
        engine.unload()

    by_preset: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        by_preset.setdefault(str(row["preset"]), []).append(row)

    print(f"\n{'preset':14s} {'region':8s} {'n':>3s} {'WER':>7s} {'sim':>7s} {'tone err':>9s}")
    print("-" * 56)
    summary = []
    for name, items in sorted(
        by_preset.items(),
        key=lambda kv: sum(float(item["wer"]) for item in kv[1]) / len(kv[1]),
    ):
        count = len(items)
        wer = sum(float(item["wer"]) for item in items) / count
        sim = sum(float(item["similarity"]) for item in items) / count
        tone = sum(int(item["tone_errors"]) for item in items)
        words = sum(int(item["words_compared"]) for item in items)
        region = str(items[0]["region"])
        print(
            f"{name:14s} {region:8s} {count:3d} {wer:7.3f} {sim:7.3f} "
            f"{tone / words if words else 0.0:8.3f} ({tone}/{words})"
        )
        summary.append(
            {
                "preset": name,
                "region": region,
                "sentences": count,
                "wer": round(wer, 4),
                "similarity": round(sim, 4),
                "tone_error_rate": round(tone / words if words else 0.0, 4),
                "tone_errors": tone,
                "words_compared": words,
            }
        )

    if args.json_out is not None:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(
            json.dumps({"summary": summary, "rows": rows}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"\nJSON written to {args.json_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
