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

# SDK VieNeu 3.8.1 tự `hf_hub_download` bản `main` khi có mạng, và làm `refs/main` của cache trỏ sang
# revision mới. Lượt đo 17-09 đã làm đúng thế, và `cli run` sau đó bị hợp đồng runtime chặn
# ("voice model revision='5f2a3e93…', expected '8b7e9cff…'"). Script đo không được đổi cache mà
# dây chuyền đang dùng: ép offline TRƯỚC khi nạp gì.
import os

os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

import argparse
import json
import math
import re
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
from scripts.book_paths import SOURCE_DIR  # noqa: E402
from scripts.compare_voice_regions import PROBE_SENTENCES, SEED, tone_error_rate  # noqa: E402

SPEED_OF_SOUND_CM_PER_S = 35_000.0
# 5 câu dò là ~80 từ so sánh, nên MỘT lỗi thanh điệu ở đó là 1,2% - lớn hơn cả khoảng cách giữa các
# giọng. Mặc định thêm 20 câu sách: ~400 từ, một lỗi đơn lẻ còn 0,25%.
BOOK_SENTENCES_DEFAULT = 20
SQRT2 = math.sqrt(2.0)
REGIONS = ("Bắc", "Nam", "Trung")
OPENERS = "“\"'‘("
CLOSERS = (".", "!", "?", "…", ":", "“", "\"")
_SENTENCE = re.compile(r"[^.!?…]+[.!?…]")
def _has_proper_noun(sentence: str) -> bool:
    """Một từ viết HOA ở giữa câu (không đứng sau dấu kết câu hay ngoặc mở) - gần như luôn là tên riêng."""
    words = sentence.split()
    for previous, word in zip(words, words[1:]):
        letter = word.lstrip(OPENERS)[:1]
        if letter and letter.isupper() and not previous.endswith(CLOSERS):
            return True
    return False


def book_sentences(count: int, source: Path = SOURCE_DIR) -> list[str]:
    """`count` câu thật từ nguồn sách, chọn tất định: 40–110 ký tự, không chữ số, không tên riêng.

    Vì sao thêm: 5 câu dò của `compare_voice_regions.py` là ~80 từ, và ở đó MỘT lỗi thanh điệu là 0,012.
    Lượt đo 17-09 cho Quỳnh Anh 0,000 ở SDK 3.3.0 và 0,049 ở 3.8.1 trên đúng năm câu ấy - tức là nhiễu,
    không phải giọng. Câu thật của sách còn mang đúng nhịp đối thoại mà giọng sẽ phải đọc.
    Tên riêng bị loại vì cùng lý do với câu dò: chữ La-tinh là một biến nhiễu khác.
    """
    if count <= 0:
        return []
    picked: list[str] = []
    files = sorted(source.glob("*.txt"))
    step = max(1, len(files) // max(count, 1))
    for path in files[::step]:
        text = path.read_text(encoding="utf-8", errors="replace").replace("\n", " ")
        for raw in _SENTENCE.findall(text):
            sentence = raw.strip().strip("“”\"'‘’ ").strip()
            if not (40 <= len(sentence) <= 110) or re.search(r"[0-9#&@*/\\()\[\]]", sentence):
                continue
            if _has_proper_noun(sentence):
                continue
            picked.append(sentence)
            break
        if len(picked) >= count:
            break
    return picked


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
    """F0 trung vị trên khung hữu thanh, F3 **trung bình cả clip** - cùng thang với `voice_catalog`.

    F3 phải đo đúng cách đã đo các giọng đang dùng, vì số này bị so với
    `[VOCAL_TRACT_MIN_CM, VOCAL_TRACT_MAX_CM]` - hai hằng số lấy từ chính thang ấy. Không còn script
    gốc nào, nên 18-09 tôi dò ngược: chạy một lưới thiết lập Praat trên đúng 10 preview đang ship và
    so với 10 số trong `PRESET_VOCAL_TRACT_CM`.

        cach do F3                      lech trung binh   lech lon nhat
        "Get mean" ca clip, 5 formant         0,20%           0,31%   <- cach da dung
        "Get quantile 0.5" ca clip            2,03%           6,76%
        trung vi tren khung huu thanh         4,51%           9,75%   <- cach nay tung dung, SAI thang
        tran 5000 cho ca hai gioi             6,47%          17,83%

    Bản đầu của hàm này lấy trung vị trên khung hữu thanh, tức lệch ~4,5% so với thang của catalog -
    đủ để một giọng nằm sát biên bị gọi là ngoài biên hoặc ngược lại. Trần formant theo giới (5000 Hz
    cho nam, 5500 cho nữ) là phần quan trọng thứ hai: dùng một trần cho cả hai giới lệch 6,5%.

    F0 thì cách cũ đã đúng họ: trung vị trên khung hữu thanh lệch trung bình 1,2% (lớn nhất 3,2%),
    còn trung bình cả clip lệch 6,2% - nên giữ trung vị.
    """
    import parselmouth
    import soundfile as sf
    from parselmouth.praat import call

    f0s: list[float] = []
    f3s: list[float] = []
    ceiling = 5000.0 if gender == "male" else 5500.0
    for path in wavs:
        audio, rate = sf.read(str(path), dtype="float64", always_2d=False)
        sound = parselmouth.Sound(np.asarray(audio).reshape(-1), sampling_frequency=float(rate))
        pitch = sound.to_pitch(pitch_floor=60.0, pitch_ceiling=500.0)
        formant = sound.to_formant_burg(max_number_of_formants=5, maximum_formant=ceiling)
        for index in range(pitch.get_number_of_frames()):
            f0 = pitch.get_value_in_frame(index + 1)
            if np.isfinite(f0) and f0 > 0:
                f0s.append(float(f0))
        mean_f3 = call(formant, "Get mean", 3, 0, 0, "hertz")
        if np.isfinite(mean_f3) and mean_f3 > 0:
            f3s.append(float(mean_f3))
    f0 = float(np.median(f0s)) if f0s else float("nan")
    f3 = float(np.mean(f3s)) if f3s else float("nan")
    tract = 5.0 * SPEED_OF_SOUND_CM_PER_S / (4.0 * f3) if f3 == f3 and f3 > 0 else float("nan")
    return {"f0_median_hz": round(f0, 1), "f3_median_hz": round(f3, 1), "vocal_tract_cm": round(tract, 2)}


UNDECIDED = "CHUA KET LUAN"


def judge(measured: dict[str, Any], worst: dict[str, Any]) -> dict[str, Any]:
    """Phán quyết cho một giọng, và nói rõ khi lượt đo quá ngắn để phán.

    Vì sao có nhánh CHƯA KẾT LUẬN (18-09): lượt 5 câu loại Quỳnh Anh vì thanh điệu tệ hơn ngưỡng 1,2%,
    trên 81 từ - sai số của phép so ở đó là 3,3%, tức lệch nằm gọn trong nhiễu. Lượt 25 câu sau đó cho
    Quỳnh Anh 1,4% (đạt) và Anh Khôi 1,9% so với ngưỡng 1,67%: lệch 0,26% trong khi sai số là 0,91%.
    Loại một giọng vì chênh lệch nhỏ hơn sai số của chính phép đo thì không phải kết luận.

    Điều kiện CỨNG (giới, vùng, phong cách, danh sách chặn, thanh quản) thì loại thẳng - chúng không
    phải phép đo trên vài câu. Chỉ ba số đo có nhánh này.
    """
    reasons: list[str] = []
    undecided: list[str] = []
    if not measured["eligible"]:
        reasons.append(measured["why_not"])
    words = max(int(measured.get("words_compared") or 0), 1)
    sem = measured.get("utmos_sem") or 0.0
    for key, label in (("tone_error_rate", "thanh dieu"), ("wer", "WER"), ("utmos", "UTMOS")):
        limit = worst.get(key)
        value = measured.get(key)
        if limit is None or value is None:
            continue
        gap = (limit - value) if key == "utmos" else (value - limit)
        if gap <= 0:
            continue
        # Hai tỉ lệ đếm, mỗi cái sai số Poisson sqrt(k)/W = sqrt(ti le / so tu); sai số của HIỆU là hai
        # cái ấy cộng theo bình phương. UTMOS là trung bình các câu: lấy sai số chuẩn của trung bình,
        # cũng nhân sqrt(2) vì hiệu gồm hai lượt đo (giả định giọng kia có sai số tương đương).
        noise = sem * SQRT2 if key == "utmos" else math.hypot(math.sqrt(value / words), math.sqrt(limit / words))
        worse = f"{label} {'thap hon' if key == 'utmos' else 'te hon'} gioi te nhat trong pool"
        if gap <= noise:
            undecided.append(f"{worse} nhung chi {gap:.4f}, con sai so cua phep so la {noise:.4f} "
                             f"- do them cau roi phan")
        else:
            reasons.append(worse)
    tract = measured["vocal_tract_cm"]
    if not (tract == tract and VOCAL_TRACT_MIN_CM <= tract <= VOCAL_TRACT_MAX_CM):
        reasons.append(f"thanh quan {tract} cm ngoai [{VOCAL_TRACT_MIN_CM}, {VOCAL_TRACT_MAX_CM}]")
    verdict = "khong" if reasons else UNDECIDED if undecided else "VAO POOL DUOC"
    return {"verdict": verdict, "reasons": reasons + undecided}


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--presets", default="")
    parser.add_argument("--json", dest="json_out", type=Path, default=None)
    parser.add_argument("--no-utmos", action="store_true")
    parser.add_argument("--book-sentences", type=int, default=BOOK_SENTENCES_DEFAULT,
                        help=f"thêm N câu thật từ nguồn sách (tất định; mặc định {BOOK_SENTENCES_DEFAULT})")
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
    sentences = list(PROBE_SENTENCES) + book_sentences(args.book_sentences)
    print(f"{len(sentences)} cau moi giong ({len(PROBE_SENTENCES)} cau do + {len(sentences) - len(PROBE_SENTENCES)} cau sach)", flush=True)
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
            # Tên gọi đích danh bằng --presets thì vẫn đo, kể cả giọng bị loại: chủ sách muốn xem lại
            # Xuân Vĩnh (17-09) sau khi SDK 3.8.1 đổi dữ liệu giọng của nó. Phán quyết vẫn ghi rõ lý do loại.
            if not ok and name not in pool and name not in wanted:
                continue
            profile = {"engine": "vieneu", "preset_name": name, "voice_key": f"probe_{name}", "id": 0}
            for index, sentence in enumerate(sentences):
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

        # `perceptual_qa.enabled` mặc định False trong mọi profile - lượt đo đầu 17-09 in UTMOS "nan"
        # vì thế. Bật riêng cho verifier này, checkpoint lấy theo đường dẫn mặc định của config.
        scoring = dict(settings, perceptual_qa={**settings.get("perceptual_qa", {}), "enabled": True})
        utmos = UTMOSNaturalnessVerifier(scoring, log)
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
                "words_compared": words,
                "wer": round(sum(float(r["wer"]) for r in mine) / len(mine), 4),
                "similarity": round(sum(float(r["similarity"]) for r in mine) / len(mine), 4),
                "tone_error_rate": round(sum(int(r["tone_errors"]) for r in mine) / words, 4) if words else 0.0,
                "utmos": round(float(np.mean([r["utmos"] for r in mine])), 3) if all("utmos" in r for r in mine) else None,
                "utmos_sem": (round(float(np.std([r["utmos"] for r in mine], ddof=1) / np.sqrt(len(mine))), 3)
                              if len(mine) > 1 and all("utmos" in r for r in mine) else None),
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
        info.update(judge(info, worst))

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
