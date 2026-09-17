"""Mẫu nghe để CHỦ SÁCH so bằng tai: cùng câu, cùng seed, qua bản VieNeu của interpreter đang chạy.

    runtime/.venv/Scripts/python.exe          scripts/make_listening_samples.py --out D:/Novels/Voice_review_2026-09-18/pool --presets "Phạm Tuyên,..."
    runtime/venv-vieneu381/Scripts/python.exe scripts/make_listening_samples.py --out ... --presets "..."

Mỗi giọng một thư mục; mỗi file mang phiên bản SDK trong tên (`..._vieneu3.3.0.wav` / `..._vieneu3.8.1.wav`), nên
chạy hai lần bằng hai venv là có hai bản đặt cạnh nhau. Bốn clip: đoạn preview cố định (hai câu dò của
`compare_voice_regions.py`, giống `make_voice_previews.py`) và ba câu thật của sách - một câu hỏi, một câu cảm
thán, một câu tự sự - chọn từ `audition_presets.book_sentences(20)`, không có tên riêng.

Vì sao có (18-09 00:0x): chủ sách sẽ nghe lại cả pool trước khi quyết nhận giọng mới và nâng SDK - *"các giọng
đang dùng thì cũng chạy lại luôn, kèm bản cũ nữa để sáng mai … nghe hết một lượt"*. Chỉ đọc; ép offline để không
đổi cache model mà dây chuyền đang dùng (xem `audition_presets.py`).
"""
from __future__ import annotations

import os

os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

import argparse
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ebook_reader.config import build_settings  # noqa: E402
from ebook_reader.io_utils import slugify  # noqa: E402
from ebook_reader.tts import VieNeuEngine  # noqa: E402
from scripts.audition_presets import book_sentences, sdk_version  # noqa: E402
from scripts.compare_voice_regions import PROBE_SENTENCES, SEED  # noqa: E402

BOOK_PICKS = {7: "cau_hoi", 13: "cam_than", 18: "tu_su"}


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--presets", required=True)
    args = parser.parse_args()
    import soundfile as sf

    version = sdk_version()
    book = book_sentences(20)
    clips = [("00", "preview", f"{PROBE_SENTENCES[0]} {PROBE_SENTENCES[1]}", SEED)]
    clips += [(f"{10 + index:02d}", label, book[index], SEED + 5 + index) for index, label in BOOK_PICKS.items()]
    names = [name.strip() for name in args.presets.split(",") if name.strip()]
    settings = build_settings("high_quality")
    engine = VieNeuEngine(settings, lambda message: print(f"  {message}", flush=True))
    try:
        engine.load()
        for name in names:
            if name not in engine.voices:
                print(f"  bo qua {name}: vieneu {version} khong co giong nay")
                continue
            folder = args.out / slugify(name)
            folder.mkdir(parents=True, exist_ok=True)
            profile = {"engine": "vieneu", "preset_name": name, "voice_key": "listen", "id": 0}
            for number, label, text, seed in clips:
                row = {"kind": "narration", "speaker": "NARRATOR", "text": text, "emotion": "neutral",
                       "intensity": 0, "pace": "normal", "volume": "normal", "warning_code": ""}
                audio = engine.generate_one(row, profile, seed)
                path = folder / f"{number}_{label}_{slugify(name)}_vieneu{version}.wav"
                sf.write(str(path), np.asarray(audio, dtype=np.float32), int(engine.sample_rate), subtype="PCM_16")
            (args.out / "cau_da_doc.txt").write_text(
                "\n".join(f"{number}_{label}: {text}" for number, label, text, _seed in clips) + "\n", encoding="utf-8"
            )
            print(f"  {name}: {len(clips)} clip vieneu {version}", flush=True)
    finally:
        engine.unload()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
