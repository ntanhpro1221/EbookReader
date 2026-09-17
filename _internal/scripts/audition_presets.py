"""Cho MỌI giọng dựng sẵn của VieNeu đọc cùng một bộ câu, rồi đo: có vào được pool giọng nhân vật không?

    python scripts/audition_presets.py --out <thư mục nháp> [--presets "A,B"] [--json report.json] [--no-utmos]

Chạy bằng interpreter nào thì đo bản VieNeu của interpreter ấy - nên cùng một script so được hai bản
SDK (`runtime/.venv` = 3.3.0, `runtime/venv-vieneu381` = 3.8.1) trên cùng câu, cùng seed.

Chỉ ghi vào thư mục nháp của nó; không đụng project nào. Cần GPU rảnh: con số tốc độ đo khi đang có
lô chạy là con số của hai tiến trình tranh nhau.

## Vì sao có script này (17-09)

Chủ sách hỏi VieNeu có bản mới không. Tra ra 3.8.1, và hai điều: (1) ngay bản 3.3.0 đang dùng đã có
**20** giọng dựng sẵn mà `voice_catalog.VIENEU_PRESETS` chỉ biết **14**; (2) 3.8.1 có 25. Riêng giọng
**nam** là nhóm đang thiếu (lô 6: cần 13 bậc/14 để không ai trùng giọng trong chương, và mới chỉ có 3
preset nam được cast: Phạm Tuyên, Thái Sơn, Thanh Bình). Chủ sách: *"có thêm giọng mới à? có phù hợp
với các tiêu chí chọn giọng hiện tại không? có thể cho vào pool giọng không?"*.

## Tiêu chí - lấy từ luật đang có, không đặt mới

`voice_catalog.casting_presets` đã nói điều kiện CỨNG: đúng giới, không phải phong cách tin tức, vùng
Bắc hoặc Nam (Trung bị loại vì **sai thanh điệu trên từ thường**, đo bằng `compare_voice_regions.py`),
không nằm trong `EXCLUDED_PRESETS`. Script này đo những gì luật ấy dựa vào, cho giọng mới, **cạnh**
chính các giọng đang ở trong pool, trong cùng một lượt chạy. Ngưỡng là giọng TỆ NHẤT đang được cast,
không phải một con số tự đặt:

- **lỗi thanh điệu** và **WER** (Whisper), với các câu tự sự dày thanh điệu và không có tên riêng
  (dùng lại `PROBE_SENTENCES` của `compare_voice_regions.py`);
- **UTMOSv2** (độ tự nhiên, thang tuyệt đối), trung bình các câu;
- **F0 trung vị** và **độ dài thanh quản** ước từ F3 bằng Praat (`L = 5c / 4F3`, cùng mô hình ống với
  `PRESET_VOCAL_TRACT_CM`). Thanh quản ngoài `[VOCAL_TRACT_MIN_CM, VOCAL_TRACT_MAX_CM]` thì các bậc
  formant của giọng ấy không dùng được;
- **tốc độ**: giây sinh cho mỗi 100 ký tự, sau một lượt khởi động không tính (CUDA graph của 3.7+
  dựng ở lần gọi đầu).

Không đo được bằng máy, và cố ý không giả vờ: tai người nghe. Những luật đang có từ tai người nghe
(`EXCLUDED_PRESETS`, `LAST_RESORT_PRESETS`, `CHILD_VOICE_PREFERENCE`) giữ nguyên.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ebook_reader.asr import WhisperVerifier, normalize_transcript, transcript_metrics  # noqa: E402
from ebook_reader.audio_io import atomic_write_wav  # noqa: E402
from ebook_reader.config import build_settings  # noqa: E402
from ebook_reader.tts import VieNeuEngine  # noqa: E402
from ebook_reader.voice_catalog import (  # noqa: E402
    EXCLUDED_PRESETS,
    VOCAL_TRACT_MAX_CM,
    VOCAL_TRACT_MIN_CM,
    casting_presets,
)
from scripts.compare_voice_regions import PROBE_SENTENCES, SEED, tone_error_rate  # noqa: E402

SPEED_OF_SOUND_CM_PER_S = 35_000.0
REGIONS = ("Bắc", "Nam", "Trung")


def sdk_version() -> str:
    try:
        from importlib.metadata import version

        return version("vieneu")
    except Exception:  # noqa: BLE001
        return "?"


def preset_metadata(engine: VieNeuEngine) -> dict[str, dict[str, str]]:
    """{tên: {gender, region, style, description}} từ chính SDK đang nạp.

    3.8.1 ghi `gender` / `style` vào từng mục; vùng thì chỉ nằm trong `description`
    ("Nam · Bắc · Phong cách tự nhiên") ở cả hai bản, nên đọc từ đó.
    """
    voices = getattr(engine.tts, "_preset_voices", {}) or {}
    out: dict[str, dict[str, str]] = {}
    for name in engine.voices:
        entry = voices.get(name, {}) if isinstance(voices, dict) else {}
        description = str(entry.get("description", ""))
        parts = [part.strip() for part in description.split("·")]
        gender = str(entry.get("gender", "")) or (
            "male" if parts and parts[0] == "Nam" else "female" if parts and parts[0] == "Nữ" else ""
        )
        region = parts[1] if len(parts) > 1 and parts[1] in REGIONS else ""
        style = str(entry.get("style", ""))
        if "tin tức" in description.casefold():
            style = "tin_tuc"
        out[name] = {"gender": gender, "region": region, "style": style, "description": description}
    return out


def eligible(meta: dict[str, str], name: str) -> tuple[bool, str]:
    """Điều kiện CỨNG của `casting_presets`, áp lên metadata của SDK."""
    if meta["gender"] not in ("male", "female"):
        return False, "khong ro gioi"
    if meta["style"] == "tin_tuc":
        return False, "phong cach tin tuc"
    if meta["region"] not in ("Bắc", "Nam"):
        return False, f"vung {meta['region'] or '?'}"
    if name in EXCLUDED_PRESETS:
        return False, "nguoi nghe da loai"
    return True, ""


def acoustics(wavs: list[Path], gender: str) -> dict[str, float]:
    """F0 trung vị và F3 trung vị trên khung hữu thanh, gộp mọi câu của một giọng."""
    import parselmouth
    import soundfile as sf

    f0s: list[float] = []
    f3s: list[float] = []
    ceiling = 5000.0 if gender == "male" else 5500.0
    for path in wavs:
        audio, rate = sf.read(str(path), dtype="float64", always_2d=False)
        sound = parselmouth.Sound(np.asarray(audio).reshape(-1), sampling_frequency=float(rate))
        pitch = sound.to_pitch(pitch_floor=60.0, pitch_ceiling=500.0)
        formant = sound.to_formant_burg(max_number_of_formants=5, maximum_formant=ceiling)
        for index in range(pitch.get_number_of_frames()):
            time_s = pitch.get_time_from_frame_number(index + 1)
            f0 = pitch.get_value_in_frame(index + 1)
            if not np.isfinite(f0) or f0 <= 0:
                continue
            f0s.append(float(f0))
            f3 = formant.get_value_at_time(3, time_s)
            if np.isfinite(f3) and f3 > 0:
                f3s.append(float(f3))
    f0 = float(np.median(f0s)) if f0s else float("nan")
    f3 = float(np.median(f3s)) if f3s else float("nan")
    tract = 5.0 * SPEED_OF_SOUND_CM_PER_S / (4.0 * f3) if f3 == f3 and f3 > 0 else float("nan")
    return {"f0_median_hz": round(f0, 1), "f3_median_hz": round(f3, 1), "vocal_tract_cm": round(tract, 2)}


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--presets", default="")
    parser.add_argument("--json", dest="json_out", type=Path, default=None)
    parser.add_argument("--no-utmos", action="store_true")
    args = parser.parse_args()

    settings = build_settings("high_quality")
    args.out.mkdir(parents=True, exist_ok=True)
    log = lambda message: print(f"  {message}", flush=True)  # noqa: E731
    engine = VieNeuEngine(settings, log)
    engine.load()
    version = sdk_version()
    meta = preset_metadata(engine)
    pool = {str(p["name"]) for gender in ("male", "female") for p in casting_presets(gender)}
    wanted = {name.strip() for name in args.presets.split(",") if name.strip()}
    names = [n for n in engine.voices if (not wanted or n in wanted)]
    print(f"vieneu {version}: {len(engine.voices)} giong dung san; pool hien tai: {sorted(pool)}", flush=True)

    rows: list[dict[str, Any]] = []
    per_preset: dict[str, dict[str, Any]] = {}
    try:
        warm = {"kind": "narration", "speaker": "NARRATOR", "text": PROBE_SENTENCES[0], "emotion": "neutral",
                "intensity": 0, "pace": "normal", "volume": "normal", "warning_code": ""}
        engine.generate_one(warm, {"engine": "vieneu", "preset_name": names[0], "voice_key": "warm", "id": 0}, SEED)
        for name in names:
            ok, why = eligible(meta[name], name)
            per_preset[name] = {**meta[name], "eligible": ok, "why_not": why, "in_pool": name in pool,
                                "sdk": version, "gen_seconds": 0.0, "audio_seconds": 0.0, "chars": 0}
            if not ok and name not in pool:
                continue
            profile = {"engine": "vieneu", "preset_name": name, "voice_key": f"probe_{name}", "id": 0}
            for index, sentence in enumerate(PROBE_SENTENCES):
                row = dict(warm, text=sentence)
                started = time.perf_counter()
                audio = engine.generate_one(row, profile, SEED + index)
                elapsed = time.perf_counter() - started
                path = args.out / f"{name.replace(' ', '_')}_{index}.wav"
                atomic_write_wav(path, audio, engine.sample_rate, sentence, settings, segment=row)
                per_preset[name]["gen_seconds"] += elapsed
                per_preset[name]["audio_seconds"] += len(audio) / float(engine.sample_rate)
                per_preset[name]["chars"] += len(sentence)
                rows.append({"preset": name, "index": index, "text": sentence, "wav": str(path)})
            print(f"  {name}: {per_preset[name]['gen_seconds']:.1f}s sinh", flush=True)
    finally:
        engine.unload()

    verifier = WhisperVerifier(settings, log)
    try:
        verifier.load()
        for row in rows:
            result = verifier.verify(str(row["text"]), Path(str(row["wav"])))
            transcript = str(result.get("transcript", ""))
            similarity, wer = transcript_metrics(normalize_transcript(row["text"]), normalize_transcript(transcript))
            _rate, errors, compared = tone_error_rate(str(row["text"]), transcript)
            row.update({"transcript": transcript, "similarity": similarity, "wer": wer,
                        "tone_errors": errors, "words_compared": compared})
    finally:
        verifier.unload()

    if not args.no_utmos:
        from ebook_reader.perceptual_qa import UTMOSNaturalnessVerifier

        utmos = UTMOSNaturalnessVerifier(settings, log)
        if utmos.load():
            for row in rows:
                row["utmos"] = float(utmos._score(Path(str(row["wav"]))))

    for name, info in per_preset.items():
        mine = [r for r in rows if r["preset"] == name]
        if not mine:
            continue
        words = sum(int(r["words_compared"]) for r in mine)
        info.update(
            {
                "sentences": len(mine),
                "wer": round(sum(float(r["wer"]) for r in mine) / len(mine), 4),
                "similarity": round(sum(float(r["similarity"]) for r in mine) / len(mine), 4),
                "tone_error_rate": round(sum(int(r["tone_errors"]) for r in mine) / words, 4) if words else 0.0,
                "utmos": round(float(np.mean([r["utmos"] for r in mine])), 3) if all("utmos" in r for r in mine) else None,
                "seconds_per_100_chars": round(100.0 * info["gen_seconds"] / max(info["chars"], 1), 3),
                "real_time_factor": round(info["gen_seconds"] / max(info["audio_seconds"], 1e-9), 3),
                **acoustics([Path(str(r["wav"])) for r in mine], info["gender"]),
            }
        )

    measured = [info for info in per_preset.values() if "wer" in info]
    in_pool = [info for info in measured if info["in_pool"]]
    worst = {
        "tone_error_rate": max((i["tone_error_rate"] for i in in_pool), default=None),
        "wer": max((i["wer"] for i in in_pool), default=None),
        "utmos": min((i["utmos"] for i in in_pool if i["utmos"] is not None), default=None),
    }
    for info in measured:
        reasons = []
        if not info["eligible"]:
            reasons.append(info["why_not"])
        if worst["tone_error_rate"] is not None and info["tone_error_rate"] > worst["tone_error_rate"]:
            reasons.append("thanh dieu te hon gioi te nhat trong pool")
        if worst["wer"] is not None and info["wer"] > worst["wer"]:
            reasons.append("WER te hon gioi te nhat trong pool")
        if worst["utmos"] is not None and info["utmos"] is not None and info["utmos"] < worst["utmos"]:
            reasons.append("UTMOS thap hon gioi te nhat trong pool")
        tract = info["vocal_tract_cm"]
        if not (tract == tract and VOCAL_TRACT_MIN_CM <= tract <= VOCAL_TRACT_MAX_CM):
            reasons.append(f"thanh quan {tract} cm ngoai [{VOCAL_TRACT_MIN_CM}, {VOCAL_TRACT_MAX_CM}]")
        info["verdict"] = "VAO POOL DUOC" if not reasons else "khong"
        info["reasons"] = reasons

    print(f"\nvieneu {version} | nguong = gioi TE NHAT dang o pool: {worst}")
    print(f"{'giong':15s} {'gioi':6s} {'vung':4s} {'pool':4s} {'WER':>6s} {'thanh':>6s} {'UTMOS':>6s} "
          f"{'F0':>6s} {'tract':>6s} {'s/100':>6s}  ket luan")
    for info in sorted(measured, key=lambda i: (i["gender"], not i["in_pool"], i["wer"])):
        name = next(n for n, v in per_preset.items() if v is info)
        print(f"{name:15s} {info['gender']:6s} {info['region']:4s} {'co' if info['in_pool'] else '':4s} "
              f"{info['wer']:6.3f} {info['tone_error_rate']:6.3f} {info['utmos'] if info['utmos'] is not None else float('nan'):6.3f} "
              f"{info['f0_median_hz']:6.1f} {info['vocal_tract_cm']:6.2f} {info['seconds_per_100_chars']:6.2f}  "
              f"{info['verdict']}{' - ' + '; '.join(info['reasons']) if info['reasons'] else ''}")
    if args.json_out:
        args.json_out.write_text(json.dumps({"sdk": version, "worst_in_pool": worst, "presets": per_preset,
                                             "rows": rows}, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
