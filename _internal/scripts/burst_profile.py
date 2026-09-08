"""In cấu trúc cụm tiếng của một bản thu: tiếng ở đâu, im ở đâu, mấy cụm rời nhau.

    python scripts/burst_profile.py <file.wav> [file.wav ...]
    python scripts/burst_profile.py <project_dir> --segment c00003_s0000129

Viết ra để trả lời một câu mà không có tai người thì tưởng không trả lời được: *bản thu này
có chứa tiếng nói lẽ ra không được có ở đó không?*

Cách đo: chia thành ô 20ms, lấy RMS, gọi ô là "có tiếng" nếu nó trên đỉnh 35 dB. Khoảng im từ
0,15 giây trở lên giữa hai ô có tiếng thì tách thành hai **cụm**.

Nó đã trả lời được ca `"Tiếp theo."` của alpha.60 chương 021 - hai từ, mà sóng âm cho:

    ..#####.##########.............................#####################################.......
    tiếng 0,04-0,36s | im 0,58s | tiếng 0,94-1,68s

Hai từ không nằm ở hai cụm cách nhau nửa giây. Cụm sau là tiếng thừa, đúng cái Whisper nghe ra
thành "À xong". Bốn trong năm ứng viên thu lại chỉ có **một** cụm.

**Nhưng đừng dùng số cụm làm phép kiểm.** Đo trên 205 đoạn ngắn `verified` của alpha.60 thì 27
đoạn cũng có ≥2 cụm, và chúng hoàn toàn bình thường - `"Sai bét. Tiếp theo!"`, `"Tốt! Tuyệt
vời!"` có dấu câu bên trong, còn `"Tại sao ư?"` thì chỉ là một quãng ngập ngừng. Hai phân bố
chồng nhau, y như nhịp đọc (xem docs/SHIPPING_WITHOUT_A_LISTENER.md).

Đây là **kính lúp để nhìn một ca**, không phải cổng để chặn hàng loạt. Thứ duy nhất tách sạch
được vẫn là lời tự khai của bộ sinh, `generation_ceiling_hit`.
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

import numpy as np
import soundfile as sf

FRAME_SECONDS = 0.02
FLOOR_BELOW_PEAK_DB = 35.0
GAP_SECONDS = 0.15


def profile(path: Path) -> dict:
    samples, rate = sf.read(str(path), dtype="float32")
    if samples.ndim > 1:
        samples = samples.mean(axis=1)
    window = int(rate * FRAME_SECONDS)
    frames = len(samples) // window
    if frames < 2:
        return {"duration": len(samples) / rate, "bursts": 1, "map": "#", "spans": []}
    rms = np.array(
        [
            np.sqrt(np.mean(samples[i * window : (i + 1) * window] ** 2) + 1e-12)
            for i in range(frames)
        ]
    )
    decibels = 20 * np.log10(rms + 1e-12)
    voiced = decibels > decibels.max() - FLOOR_BELOW_PEAK_DB
    lit = np.where(voiced)[0]
    if not len(lit):
        return {"duration": len(samples) / rate, "bursts": 0, "map": "." * frames, "spans": []}

    spans: list[tuple[float, float]] = []
    start = lit[0]
    silent = 0
    for index in range(lit[0], lit[-1] + 1):
        if voiced[index]:
            if silent * FRAME_SECONDS >= GAP_SECONDS:
                spans.append((start * FRAME_SECONDS, (index - silent) * FRAME_SECONDS))
                start = index
            silent = 0
        else:
            silent += 1
    spans.append((start * FRAME_SECONDS, (lit[-1] + 1) * FRAME_SECONDS))
    return {
        "duration": len(samples) / rate,
        "bursts": len(spans),
        "map": "".join("#" if v else "." for v in voiced),
        "spans": spans,
    }


def _resolve(project: Path, stable_id: str) -> list[tuple[str, Path]]:
    conn = sqlite3.connect(f"file:{project / 'project.sqlite3'}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    out: list[tuple[str, Path]] = []
    row = conn.execute(
        "SELECT id, stable_id, text, wav_path FROM segments WHERE stable_id LIKE ?",
        (f"{stable_id}%",),
    ).fetchone()
    if row is None:
        raise SystemExit(f"Không thấy segment {stable_id}")
    out.append((f"đương nhiệm — {str(row['text'])[:40]!r}", Path(str(row["wav_path"]))))
    for cand in conn.execute(
        "SELECT repair_round, wav_path, state FROM segment_candidates "
        "WHERE segment_id=? ORDER BY repair_round",
        (int(row["id"]),),
    ):
        out.append(
            (f"ứng viên vòng {cand['repair_round']} ({cand['state']})",
             Path(str(cand["wav_path"])))
        )
    return out


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("targets", nargs="+", type=Path)
    parser.add_argument("--segment", help="stable_id, khi target là thư mục project")
    args = parser.parse_args(argv)

    items: list[tuple[str, Path]] = []
    for target in args.targets:
        if args.segment and (target / "project.sqlite3").is_file():
            items.extend(_resolve(target, args.segment))
        else:
            items.append((target.name, target))

    for label, path in items:
        if not path.is_file():
            print(f"--- {label}: file không còn")
            continue
        data = profile(path)
        print(f"--- {label}   {data['duration']:.2f}s   {data['bursts']} cụm")
        print(f"    {data['map']}")
        for start, end in data["spans"]:
            print(f"      tiếng {start:.2f}-{end:.2f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
