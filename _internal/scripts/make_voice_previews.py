"""Tạo clip nghe thử (preview) cho những giọng dựng sẵn chưa có, vào một thư mục CHỜ - không vào thẳng assets.

    python scripts/make_voice_previews.py --presets "Mạnh Dũng,Anh Khôi" [--out scripts/pending_patches/assets/voice_previews]

Chạy bằng interpreter mang đúng bản VieNeu sẽ dùng (17-09: `runtime/venv-vieneu381`). Cần GPU rảnh.

## Vì sao cần preview cho mỗi giọng trong pool

`perceptual_qa.UTMOSNaturalnessVerifier` chấm độ tự nhiên **tương đối**: điểm UTMOS của một bản thu so
với điểm của CHÍNH preview của giọng ấy (`VOICE_PREVIEW_FILENAMES`). Giọng không có preview thì cổng
ấy không có mốc để so. Nên đưa một giọng vào pool là phải kèm preview.

## Vì sao vào thư mục chờ

`quality_policy` băm `assets/voice_previews` (`voice_previews_sha256`). Ghi một file vào đó giữa lúc
một lô dở thì lần resume kế tiếp bị từ chối, và lô mất phần chưa xuất bản. Nên script chỉ ghi vào
thư mục chờ; bản vá nâng VieNeu chép chúng vào `ebook_reader/assets/voice_previews/` ở ranh giới.

## Nội dung clip

Các preview cũ (8–11 giây, 48 kHz, PCM_16, mono) KHÔNG phải mã giọng mẫu giải ra (mã v3 chỉ dài 3–5
giây), nên không tái tạo được đúng cách chúng ra đời. Preview mới là hai câu dò cố định của
`compare_voice_regions.py` (~8 giây), cùng seed, qua đúng `VieNeuEngine.generate_one` mà dây chuyền
dùng. Mốc là tương đối theo từng giọng, nên điều quan trọng là mọi preview mới làm theo CÙNG một cách.
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
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ebook_reader.config import build_settings  # noqa: E402
from ebook_reader.io_utils import slugify  # noqa: E402
from ebook_reader.tts import VieNeuEngine  # noqa: E402
from scripts.compare_voice_regions import PROBE_SENTENCES, SEED  # noqa: E402

DEFAULT_OUT = Path(__file__).resolve().parent / "pending_patches" / "assets" / "voice_previews"
PREVIEW_TEXT = f"{PROBE_SENTENCES[0]} {PROBE_SENTENCES[1]}"


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--presets", required=True)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    import soundfile as sf

    names = [name.strip() for name in args.presets.split(",") if name.strip()]
    args.out.mkdir(parents=True, exist_ok=True)
    settings = build_settings("high_quality")
    engine = VieNeuEngine(settings, lambda message: print(f"  {message}", flush=True))
    try:
        engine.load()
        row = {"kind": "narration", "speaker": "NARRATOR", "text": PREVIEW_TEXT, "emotion": "neutral",
               "intensity": 0, "pace": "normal", "volume": "normal", "warning_code": ""}
        for name in names:
            if name not in engine.voices:
                print(f"  bo qua {name}: SDK nay khong co")
                continue
            audio = engine.generate_one(row, {"engine": "vieneu", "preset_name": name, "voice_key": "preview", "id": 0}, SEED)
            path = args.out / f"{slugify(name)}.wav"
            sf.write(str(path), np.asarray(audio, dtype=np.float32), int(engine.sample_rate), subtype="PCM_16")
            print(f"  {name} -> {path.name} ({len(audio) / engine.sample_rate:.2f} s)", flush=True)
    finally:
        engine.unload()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
