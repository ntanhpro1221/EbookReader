"""Read-only perceptual audit of a committed audiobook project.

The pipeline already gates each segment on signal metrics, ASR agreement and
UTMOSv2 naturalness. This tool asks the complementary question a listener asks
about the finished chapter: does it *flow*? It measures speaking-rate spread,
the real silence at every join, loudness continuity between narration and
dialogue, and per-character voice/pitch consistency, then reports the outliers.

Findings here are diagnostic. Turning one into a publish gate means adding it to
`audio_io.py` (chapter signal) or `pipeline.py` (repair loop) with tests.

Usage:
    python scripts/audit_audiobook.py <project-root> [--json out.json] [--chapter N]
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sqlite3
import statistics
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

import numpy as np
import pyloudnorm as pyln
import soundfile as sf

from ebook_reader.audio_io import LOUDNESS_EMOTION_OFFSETS_DB, integrated_loudness_lufs
from ebook_reader.config import build_settings
from ebook_reader.text_processing import SPOKEN_WORD_PATTERN


DIGIT_PATTERN = re.compile(r"\d")


def spoken_syllable_count(text: str) -> int:
    """Approximate spoken syllables. Vietnamese is monosyllabic, so one word token
    is one syllable; each digit is read as its own syllable."""
    return len(SPOKEN_WORD_PATTERN.findall(text)) + len(DIGIT_PATTERN.findall(text))


SILENCE_FLOOR_DBFS = -50.0
SILENCE_FRAME_SECONDS = 0.010
# Vietnamese is monosyllabic; unhurried audiobook narration sits near 4.5-6.0
# syllables per second. These bounds bracket "sounds rushed" and "sounds slack".
RATE_FAST_SYLLABLES_PER_SECOND = 6.6
RATE_SLOW_SYLLABLES_PER_SECOND = 3.6
RATE_SPREAD_REVIEW = 1.6
EDGE_SILENCE_REVIEW_SECONDS = 0.45
JOIN_PAUSE_REVIEW_SECONDS = 1.30
LOUDNESS_SPREAD_REVIEW_LU = 3.0


def _read_mono(path: Path) -> tuple[np.ndarray, int]:
    audio, sample_rate = sf.read(path, dtype="float32", always_2d=False)
    array = np.asarray(audio, dtype=np.float32)
    if array.ndim == 2:
        array = array.mean(axis=1)
    return array, int(sample_rate)


def _frame_db(audio: np.ndarray, sample_rate: int) -> tuple[np.ndarray, int]:
    frame = max(1, int(round(SILENCE_FRAME_SECONDS * sample_rate)))
    usable = (audio.size // frame) * frame
    if usable <= 0:
        return np.zeros(0, dtype=np.float64), frame
    frames = audio[:usable].astype(np.float64).reshape(-1, frame)
    rms = np.sqrt(np.mean(np.square(frames), axis=1))
    return 20.0 * np.log10(np.maximum(rms, 1e-12)), frame


def _edge_silence(audio: np.ndarray, sample_rate: int) -> tuple[float, float]:
    levels, frame = _frame_db(audio, sample_rate)
    if levels.size == 0:
        return 0.0, 0.0
    voiced = np.flatnonzero(levels > SILENCE_FLOOR_DBFS)
    if voiced.size == 0:
        return float(audio.size / sample_rate), 0.0
    lead = float(voiced[0] * frame / sample_rate)
    tail = float((levels.size - 1 - voiced[-1]) * frame / sample_rate)
    return lead, tail


def _loudness(audio: np.ndarray, sample_rate: int) -> float | None:
    if audio.size < int(0.4 * sample_rate):
        return None
    try:
        meter = pyln.Meter(sample_rate)
        value = float(meter.integrated_loudness(audio.astype(np.float64)))
    except (ValueError, RuntimeError):
        return None
    return value if np.isfinite(value) else None


def _silence_runs(audio: np.ndarray, sample_rate: int) -> list[tuple[float, float]]:
    """Return (start_seconds, duration_seconds) for every silent run."""
    levels, frame = _frame_db(audio, sample_rate)
    if levels.size == 0:
        return []
    quiet = levels <= SILENCE_FLOOR_DBFS
    padded = np.concatenate(([False], quiet, [False]))
    edges = np.flatnonzero(padded[1:] != padded[:-1])
    runs = []
    for start, stop in zip(edges[::2], edges[1::2]):
        runs.append(
            (float(start * frame / sample_rate), float((stop - start) * frame / sample_rate))
        )
    return runs


def _voiced_seconds(audio: np.ndarray, sample_rate: int) -> float:
    """Seconds above the silence floor, i.e. time actually spent articulating.

    Gross rate (syllables over the whole span) moves when `silence_p` changes the
    pause proportion inside a segment. Articulation rate does not, so comparing the
    two separates "the director's pace changed the pauses" from "it changed how fast
    the voice actually speaks".
    """
    levels, frame = _frame_db(audio, sample_rate)
    if levels.size == 0:
        return 0.0
    return float(np.count_nonzero(levels > SILENCE_FLOOR_DBFS) * frame / sample_rate)


def _percentile(values: list[float], q: float) -> float:
    return float(np.percentile(np.asarray(values, dtype=np.float64), q)) if values else 0.0


def audit_segments(connection: sqlite3.Connection, chapter_filter: int | None) -> dict[str, Any]:
    query = """
        SELECT s.id, s.stable_id, s.chapter_id, s.seq, s.break_ms, s.text, s.kind,
               s.speaker, s.emotion, s.intensity, s.pace, s.volume, s.voice_profile_id,
               s.status, s.wav_path, s.wav_duration, s.signal_json,
               s.asr_similarity, s.asr_wer, c.chapter_index, c.title
        FROM segments s JOIN chapters c ON c.id = s.chapter_id
        WHERE s.wav_path IS NOT NULL
    """
    params: tuple[Any, ...] = ()
    if chapter_filter is not None:
        query += " AND c.chapter_index = ?"
        params = (chapter_filter,)
    query += " ORDER BY c.chapter_index, s.seq"

    per_chapter: dict[int, list[dict[str, Any]]] = defaultdict(list)
    findings: list[dict[str, Any]] = []
    speaker_voices: dict[str, set[str]] = defaultdict(set)
    speaker_pitch: dict[str, set[int]] = defaultdict(set)

    for row in connection.execute(query, params):
        path = Path(str(row["wav_path"]))
        if not path.is_file():
            findings.append(
                {
                    "code": "SEGMENT_WAV_MISSING",
                    "stable_id": str(row["stable_id"]),
                    "detail": str(path),
                }
            )
            continue
        audio, sample_rate = _read_mono(path)
        duration = audio.size / sample_rate if sample_rate else 0.0
        lead, tail = _edge_silence(audio, sample_rate)
        speech = max(duration - lead - tail, 1e-6)
        voiced = _voiced_seconds(audio, sample_rate)
        syllables = spoken_syllable_count(str(row["text"]))
        try:
            signal = json.loads(str(row["signal_json"] or "{}"))
        except json.JSONDecodeError:
            signal = {}
        pitch = signal.get("effective_pitch_semitones", signal.get("pitch_semitones"))
        record = {
            "stable_id": str(row["stable_id"]),
            "chapter_index": int(row["chapter_index"]),
            "seq": int(row["seq"]),
            "kind": str(row["kind"]),
            "speaker": str(row["speaker"]),
            "emotion": str(row["emotion"]),
            "pace": str(row["pace"]),
            "volume": str(row["volume"]),
            "voice_profile_id": str(row["voice_profile_id"] or ""),
            "pitch_semitones": int(pitch) if isinstance(pitch, (int, float)) else None,
            "break_ms": int(row["break_ms"]),
            "duration": duration,
            "lead_silence": lead,
            "tail_silence": tail,
            "syllables": syllables,
            "rate": syllables / speech if syllables else 0.0,
            "articulation_rate": (
                syllables / voiced if syllables and voiced > 0.05 else 0.0
            ),
            "voiced_seconds": voiced,
            "lufs": _loudness(audio, sample_rate),
            "postprocess": str(signal.get("postprocess_profile") or "none"),
            "asr_similarity": row["asr_similarity"],
            "text": str(row["text"])[:110],
        }
        per_chapter[record["chapter_index"]].append(record)
        if record["voice_profile_id"]:
            speaker_voices[record["speaker"]].add(record["voice_profile_id"])
        if record["pitch_semitones"] is not None:
            speaker_pitch[record["speaker"]].add(record["pitch_semitones"])

    for speaker, voices in sorted(speaker_voices.items()):
        if len(voices) > 1:
            findings.append(
                {
                    "code": "SPEAKER_VOICE_SPLIT",
                    "speaker": speaker,
                    "detail": f"{len(voices)} voice profiles: {sorted(voices)}",
                }
            )
    for speaker, pitches in sorted(speaker_pitch.items()):
        if len(pitches) > 1:
            findings.append(
                {
                    "code": "SPEAKER_PITCH_SPLIT",
                    "speaker": speaker,
                    "detail": f"pitch semitones {sorted(pitches)}",
                }
            )
    return {"per_chapter": dict(per_chapter), "findings": findings}


def summarise_chapter(records: list[dict[str, Any]]) -> dict[str, Any]:
    rates = [item["rate"] for item in records if item["syllables"] >= 3 and item["rate"] > 0]
    loudness = [item["lufs"] for item in records if item["lufs"] is not None]
    narration = [
        item["lufs"]
        for item in records
        if item["kind"] == "narration" and item["lufs"] is not None
    ]
    dialogue = [
        item["lufs"]
        for item in records
        if item["kind"] == "dialogue" and item["lufs"] is not None
    ]
    summary = {
        "segments": len(records),
        "audio_seconds": sum(item["duration"] for item in records),
        "syllables": sum(item["syllables"] for item in records),
        "rate_median": statistics.median(rates) if rates else 0.0,
        "rate_p05": _percentile(rates, 5),
        "rate_p95": _percentile(rates, 95),
        "rate_spread": (_percentile(rates, 95) - _percentile(rates, 5)) if rates else 0.0,
        "lufs_median": statistics.median(loudness) if loudness else None,
        "lufs_spread": (_percentile(loudness, 95) - _percentile(loudness, 5))
        if loudness
        else None,
        "narration_lufs_median": statistics.median(narration) if narration else None,
        "dialogue_lufs_median": statistics.median(dialogue) if dialogue else None,
        "lead_silence_median": statistics.median(
            [item["lead_silence"] for item in records]
        )
        if records
        else 0.0,
        "tail_silence_median": statistics.median(
            [item["tail_silence"] for item in records]
        )
        if records
        else 0.0,
        "tail_silence_p95": _percentile([item["tail_silence"] for item in records], 95),
        "postprocessed": sum(1 for item in records if item["postprocess"] != "none"),
    }
    # Does the director's pace decision actually reach the audio? If the medians for
    # slow/normal/fast sit on top of each other, pace is decorative and the listener
    # never hears the intent the analysis committed.
    summary["rate_by_pace"] = _grouped_rate(records, "pace")
    summary["rate_by_kind"] = _grouped_rate(records, "kind")
    summary["rate_by_emotion"] = _grouped_rate(records, "emotion")
    return summary


def _grouped_rate(records: list[dict[str, Any]], field: str) -> dict[str, dict[str, float]]:
    gross: dict[str, list[float]] = defaultdict(list)
    articulation: dict[str, list[float]] = defaultdict(list)
    pause: dict[str, list[float]] = defaultdict(list)
    for item in records:
        if item["syllables"] < 3 or item["rate"] <= 0:
            continue
        key = str(item[field])
        gross[key].append(item["rate"])
        if item["articulation_rate"] > 0:
            articulation[key].append(item["articulation_rate"])
        if item["duration"] > 0:
            pause[key].append(1.0 - item["voiced_seconds"] / item["duration"])
    return {
        key: {
            "count": len(values),
            "median": round(statistics.median(values), 3),
            "p05": round(_percentile(values, 5), 3),
            "p95": round(_percentile(values, 95), 3),
            "articulation_median": (
                round(statistics.median(articulation[key]), 3) if articulation[key] else 0.0
            ),
            "silence_fraction_median": (
                round(statistics.median(pause[key]), 3) if pause[key] else 0.0
            ),
        }
        for key, values in sorted(gross.items())
    }


def chapter_findings(chapter_index: int, records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    summary = summarise_chapter(records)
    if summary["rate_spread"] > RATE_SPREAD_REVIEW:
        findings.append(
            {
                "code": "CHAPTER_RATE_SPREAD",
                "chapter_index": chapter_index,
                "detail": (
                    f"p05={summary['rate_p05']:.2f} p95={summary['rate_p95']:.2f} "
                    f"syll/s spread={summary['rate_spread']:.2f}"
                ),
            }
        )
    if summary["lufs_spread"] is not None and summary["lufs_spread"] > LOUDNESS_SPREAD_REVIEW_LU:
        findings.append(
            {
                "code": "CHAPTER_LOUDNESS_SPREAD",
                "chapter_index": chapter_index,
                "detail": f"p05..p95 spread={summary['lufs_spread']:.2f} LU",
            }
        )
    for item in records:
        if item["syllables"] >= 4 and item["rate"] > RATE_FAST_SYLLABLES_PER_SECOND:
            findings.append(
                {
                    "code": "SEGMENT_RATE_FAST",
                    "chapter_index": chapter_index,
                    "stable_id": item["stable_id"],
                    "detail": f"{item['rate']:.2f} syll/s · {item['text']}",
                }
            )
        elif item["syllables"] >= 4 and 0 < item["rate"] < RATE_SLOW_SYLLABLES_PER_SECOND:
            findings.append(
                {
                    "code": "SEGMENT_RATE_SLOW",
                    "chapter_index": chapter_index,
                    "stable_id": item["stable_id"],
                    "detail": f"{item['rate']:.2f} syll/s · {item['text']}",
                }
            )
        if item["tail_silence"] > EDGE_SILENCE_REVIEW_SECONDS:
            findings.append(
                {
                    "code": "SEGMENT_TAIL_SILENCE",
                    "chapter_index": chapter_index,
                    "stable_id": item["stable_id"],
                    "detail": (
                        f"tail={item['tail_silence']:.2f}s then a {item['break_ms']}ms "
                        f"scripted break"
                    ),
                }
            )
        if item["lead_silence"] > EDGE_SILENCE_REVIEW_SECONDS:
            findings.append(
                {
                    "code": "SEGMENT_LEAD_SILENCE",
                    "chapter_index": chapter_index,
                    "stable_id": item["stable_id"],
                    "detail": f"lead={item['lead_silence']:.2f}s",
                }
            )
    return findings


def audit_joins(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Report the silence a listener actually hears between consecutive segments."""
    findings: list[dict[str, Any]] = []
    for current, following in zip(records, records[1:]):
        heard = current["tail_silence"] + current["break_ms"] / 1000.0 + following["lead_silence"]
        if heard > JOIN_PAUSE_REVIEW_SECONDS:
            findings.append(
                {
                    "code": "JOIN_PAUSE_LONG",
                    "chapter_index": current["chapter_index"],
                    "stable_id": current["stable_id"],
                    "detail": (
                        f"heard={heard:.2f}s = tail {current['tail_silence']:.2f}s "
                        f"+ break {current['break_ms']}ms "
                        f"+ lead {following['lead_silence']:.2f}s"
                    ),
                }
            )
    return findings


def _project_audio_settings(project_root: Path) -> dict[str, Any]:
    """Use the settings the book locked, not today's defaults.

    Settings are locked per book, so auditing an older project against current defaults
    would report a "miss" that is really just a version difference.
    """
    locked = project_root / "book_settings.json"
    if locked.is_file():
        try:
            return dict(json.loads(locked.read_text(encoding="utf-8"))["audio"])
        except (json.JSONDecodeError, KeyError, TypeError):
            pass
    return dict(build_settings("high_quality")["audio"])


def audit_loudness_intent(
    connection: sqlite3.Connection,
    chapter_filter: int | None,
    audio_cfg: dict[str, Any],
) -> dict[str, Any]:
    """Did each segment actually reach the level the director asked for?

    Levelling is `min(loudness_gain, peak_safe_gain)`. When the anchors sit too close to
    the peak ceiling for speech crest factor, the ceiling wins and the final level is
    decided by the waveform instead of by the intent - which is how `loud` segments ended
    up quieter than `normal` ones. This measures the miss directly.
    """
    targets = audio_cfg["segment_target_lufs"]
    narrator_offset = float(audio_cfg["segment_narrator_offset_db"])
    peak_ceiling = float(audio_cfg["segment_peak_dbfs"])
    peak_limit = 10 ** (peak_ceiling / 20.0)

    query = """
        SELECT s.speaker, s.kind, s.emotion, s.intensity, s.volume, s.wav_path
        FROM segments s JOIN chapters c ON c.id = s.chapter_id
        WHERE s.wav_path IS NOT NULL
    """
    params: tuple[Any, ...] = ()
    if chapter_filter is not None:
        query += " AND c.chapter_index = ?"
        params = (chapter_filter,)

    misses: list[float] = []
    crests: list[float] = []
    peak_limited = 0
    by_volume: dict[str, list[float]] = defaultdict(list)
    for row in connection.execute(query, params):
        path = Path(str(row["wav_path"]))
        if not path.is_file():
            continue
        audio, sample_rate = _read_mono(path)
        measured = integrated_loudness_lufs(audio, sample_rate)
        peak = float(np.max(np.abs(audio))) if audio.size else 0.0
        if measured is None or peak <= 0:
            continue
        volume = str(row["volume"])
        target = float(targets.get(volume, targets["normal"]))
        if str(row["speaker"]) == "NARRATOR":
            target += narrator_offset
        if volume == "normal":
            intensity = max(0, min(3, int(row["intensity"])))
            target += LOUDNESS_EMOTION_OFFSETS_DB.get(str(row["emotion"]), 0.0) * intensity / 3.0
        misses.append(measured - target)
        crests.append(20.0 * math.log10(peak) - measured)
        peak_limited += peak >= peak_limit * 0.999
        by_volume[volume].append(measured)

    if not misses:
        return {}
    return {
        "segments": len(misses),
        "peak_limited": peak_limited,
        "peak_limited_fraction": round(peak_limited / len(misses), 4),
        "miss_mean_db": round(float(np.mean(misses)), 3),
        "miss_median_db": round(float(np.median(misses)), 3),
        "miss_worst_db": round(float(np.min(misses)), 3),
        # "Reached" means landed on the anchor, in either direction. A segment 4 dB above
        # its target has missed just as surely as one 4 dB below.
        "reached_target": int(sum(1 for value in misses if abs(value) <= 0.15)),
        "crest_median_db": round(float(np.median(crests)), 2),
        "crest_max_db": round(float(np.max(crests)), 2),
        "median_lufs_by_volume": {
            key: round(float(np.median(values)), 2) for key, values in sorted(by_volume.items())
        },
    }


def audit_warnings(connection: sqlite3.Connection) -> dict[str, int]:
    """Count the review warnings a human is expected to act on."""
    counts: dict[str, int] = defaultdict(int)
    for row in connection.execute(
        "SELECT warning_code, status FROM segments WHERE warning_code IS NOT NULL AND warning_code != ''"
    ):
        for code in str(row["warning_code"]).split("|"):
            code = code.strip()
            if code:
                counts[f"{code} [{row['status']}]"] += 1
    return dict(sorted(counts.items(), key=lambda item: -item[1]))


def audit_chapter_mp3(connection: sqlite3.Connection, chapter_filter: int | None) -> list[dict[str, Any]]:
    query = "SELECT chapter_index, title, output_mp3, status FROM chapters WHERE output_mp3 IS NOT NULL"
    params: tuple[Any, ...] = ()
    if chapter_filter is not None:
        query += " AND chapter_index = ?"
        params = (chapter_filter,)
    reports = []
    for row in connection.execute(query + " ORDER BY chapter_index", params):
        path = Path(str(row["output_mp3"]))
        if not path.is_file():
            continue
        audio, sample_rate = _read_mono(path)
        duration = audio.size / sample_rate if sample_rate else 0.0
        runs = _silence_runs(audio, sample_rate)
        long_runs = sorted((run for run in runs if run[1] >= 1.0), key=lambda r: -r[1])[:8]
        lead, tail = _edge_silence(audio, sample_rate)
        reports.append(
            {
                "chapter_index": int(row["chapter_index"]),
                "title": str(row["title"]),
                "path": str(path),
                "duration_seconds": duration,
                "lufs": _loudness(audio, sample_rate),
                "peak": float(np.max(np.abs(audio))) if audio.size else 0.0,
                "lead_silence": lead,
                "tail_silence": tail,
                "silence_seconds_total": sum(run[1] for run in runs),
                "silence_fraction": (sum(run[1] for run in runs) / duration) if duration else 0.0,
                "longest_silences": [
                    {"at_seconds": round(start, 2), "seconds": round(length, 2)}
                    for start, length in long_runs
                ],
            }
        )
    return reports


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project_root", type=Path)
    parser.add_argument("--chapter", type=int, default=None)
    parser.add_argument("--json", dest="json_out", type=Path, default=None)
    parser.add_argument("--max-findings", type=int, default=25)
    args = parser.parse_args()

    database = (args.project_root / "project.sqlite3").resolve()
    if not database.is_file():
        print(f"No project database at {database}", file=sys.stderr)
        return 66
    connection = sqlite3.connect(f"file:{database.as_posix()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row

    segments = audit_segments(connection, args.chapter)
    findings = list(segments["findings"])
    chapters_summary = {}
    for chapter_index, records in sorted(segments["per_chapter"].items()):
        chapters_summary[chapter_index] = summarise_chapter(records)
        findings.extend(chapter_findings(chapter_index, records))
        findings.extend(audit_joins(records))
    mp3_reports = audit_chapter_mp3(connection, args.chapter)
    audio_cfg = _project_audio_settings(args.project_root)
    loudness_intent = audit_loudness_intent(connection, args.chapter, audio_cfg)
    warnings = audit_warnings(connection)

    report = {
        "project_root": str(args.project_root),
        "chapters": chapters_summary,
        "chapter_mp3": mp3_reports,
        "loudness_intent": loudness_intent,
        "warnings": warnings,
        "findings": findings,
        "finding_counts": {
            code: sum(1 for item in findings if item["code"] == code)
            for code in sorted({item["code"] for item in findings})
        },
    }

    print(f"=== Audiobook audit: {args.project_root} ===")
    for chapter_index, summary in chapters_summary.items():
        print(
            f"\nChapter {chapter_index}: {summary['segments']} segments, "
            f"{summary['audio_seconds'] / 60:.1f} min, "
            f"{summary['syllables']} syllables"
        )
        print(
            f"  rate    median={summary['rate_median']:.2f} "
            f"p05={summary['rate_p05']:.2f} p95={summary['rate_p95']:.2f} syll/s"
        )
        if summary["lufs_median"] is not None:
            print(
                f"  loudness median={summary['lufs_median']:.2f} LUFS "
                f"spread={summary['lufs_spread']:.2f} LU "
                f"narration={summary['narration_lufs_median']} "
                f"dialogue={summary['dialogue_lufs_median']}"
            )
        print(
            f"  edges   lead median={summary['lead_silence_median']:.3f}s "
            f"tail median={summary['tail_silence_median']:.3f}s "
            f"tail p95={summary['tail_silence_p95']:.3f}s"
        )
        if summary["postprocessed"]:
            print(f"  tempo rescue applied to {summary['postprocessed']} segment(s)")
        for field in ("rate_by_pace", "rate_by_kind", "rate_by_emotion"):
            grouped = summary[field]
            if len(grouped) < 2:
                continue
            rendered = "  ".join(
                f"{key}(n={stats['count']}) gross={stats['median']:.2f} "
                f"artic={stats['articulation_median']:.2f} "
                f"sil={stats['silence_fraction_median'] * 100:.0f}%"
                for key, stats in grouped.items()
            )
            print(f"  {field.replace('rate_by_', 'by '):12s} {rendered}")

    for entry in mp3_reports:
        print(
            f"\nChapter MP3 {entry['chapter_index']}: {entry['duration_seconds'] / 60:.1f} min, "
            f"{entry['lufs']:.2f} LUFS, peak {entry['peak']:.3f}, "
            f"silence {entry['silence_fraction'] * 100:.1f}%"
        )
        for item in entry["longest_silences"]:
            print(f"    long silence {item['seconds']}s at {item['at_seconds']}s")

    if loudness_intent:
        print("\n=== loudness intent ===")
        print(
            f"  reached target: {loudness_intent['reached_target']}/{loudness_intent['segments']}"
            f"   peak-limited: {loudness_intent['peak_limited']}"
            f" ({loudness_intent['peak_limited_fraction'] * 100:.0f}%)"
        )
        print(
            f"  miss vs target: mean {loudness_intent['miss_mean_db']:+.2f} dB"
            f"  median {loudness_intent['miss_median_db']:+.2f} dB"
            f"  worst {loudness_intent['miss_worst_db']:+.2f} dB"
        )
        print(
            f"  crest factor: median {loudness_intent['crest_median_db']:.2f} dB"
            f"  max {loudness_intent['crest_max_db']:.2f} dB"
        )
        print(f"  median LUFS by volume: {loudness_intent['median_lufs_by_volume']}")

    if warnings:
        print("\n=== segment warnings ===")
        for code, count in warnings.items():
            print(f"  {count:4d}  {code}")

    print("\n=== findings ===")
    if not findings:
        print("none")
    for code, count in report["finding_counts"].items():
        print(f"{code}: {count}")
    print()
    for item in findings[: args.max_findings]:
        print(f"- [{item['code']}] {item.get('stable_id') or item.get('speaker') or ''} {item['detail']}")
    if len(findings) > args.max_findings:
        print(f"... {len(findings) - args.max_findings} more")

    if args.json_out is not None:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"\nJSON written to {args.json_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
