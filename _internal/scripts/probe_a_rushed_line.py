r"""Vì sao một câu ngắn bị đọc VỘI ở mọi seed? — phép thử cần GPU, không sửa gì.

    python scripts/probe_a_rushed_line.py <project_root> --segment c00001_s0000041_fb0874d2f05b \
        --variant "“Tôi không biết xoay đâu, Felicia.”" --takes 5

**CHỈ CHẠY KHI MÁY RẢNH.** Nó nạp VieNeu lên GPU và sinh audio thật; chạy đè lên một lượt `run`
đang bay là tranh VRAM với chính lượt ấy.

## Câu hỏi

Bảy đoạn trong cả hai cuốn chưa bao giờ có bản thu, và cả bảy chết vì **cận trên** của thước nhịp
sau 10 seed (đo 2026-09-15 02:10). Hai ca của cuốn 2:

    “Tôi không biết ‘xoay’ đâu, Felicia.”      10/10 lần ở 29,0–33,9 kt/s   (7,2 âm tiết/giây)
    “Cảm ơn người rất nhiều, thưa Điện hạ.”    10/10 lần ở 25,6 kt/s        (7,3 âm tiết/giây)

Đổi seed không cứu được (project vá thu thêm 10 lần nữa, vẫn 31–32,5). Nới băng nhịp cũng không:
băng rộng nhất (`fast`) có cận trên 30,0, mà bản thu ở 31–32,5 nằm ngoài **mọi** băng — theo đúng
nguyên tắc đã ghi ở `MACHINE_ACCEPTABLE_SEGMENT_WARNINGS`, đó là **khuyết tật**, không phải đánh đổi,
nên máy không được tự cho qua. Và lệnh nhịp (`row["pace"]`) **không** tới bộ sinh: nó chỉ đổi cửa sổ
chấp nhận, nên "xin đọc chậm" là một việc không tồn tại.

Vậy còn lại một giả thuyết duy nhất đáng thử: **hình của văn bản** làm mô hình đọc vội. Ứng viên số
một là dấu ngoặc đơn lồng trong ngoặc kép (`‘xoay’`) — cùng họ với những ca đã ghi trong
docs/TWO_CHARACTERS_ONE_VOICE.md và `spoken_symbols_to_words`: ký tự mà giọng đọc không phát âm được
thì nó xử lý bằng cách nào đó không ai chọn.

## Cách đọc bảng

Mỗi biến thể được sinh `--takes` lần với **cùng tập seed salt**, nên cột `kt/s` so được trực tiếp.

- Biến thể bỏ ngoặc lồng về **trong băng** (≤ 24,5) mà bản gốc thì không → nguyên nhân là hình văn
  bản; sửa đúng nằm ở `spoken_symbols_to_words`, và ca `“Cảm ơn người…”` (không có ngoặc lồng) phải
  **vẫn vội** để khẳng định điều đó chỉ giải thích một trong hai ca.
- Mọi biến thể đều vội như nhau → không phải hình văn bản. Lúc ấy còn hai đường: hạ tempo bản thu
  bằng chính `POSTPROCESS_PROFILE_TEMPO` đã có (đổi audio, giữ nguyên thước), hoặc chấp nhận rằng
  câu này cần người nghe. Đừng nới cận trên: 7,2 âm tiết/giây so với trung vị kho 4,7 là vội thật.

Nó **không sửa gì**; audio ghi ra `work/rushed_line_probe/` để nghe lại.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import soundfile as sf  # noqa: E402

from ebook_reader.audio_io import spoken_speakable_chars, spoken_syllables  # noqa: E402
from ebook_reader.config import load_settings  # noqa: E402
from ebook_reader.database import ProjectDB  # noqa: E402
from ebook_reader.tts import TTSCoordinator  # noqa: E402


def _say(line: str) -> None:
    try:
        print(line, flush=True)
    except (UnicodeEncodeError, OSError, ValueError):
        sys.stdout.buffer.write(line.encode("utf-8", "replace") + b"\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("project_root", type=Path)
    parser.add_argument("--segment", required=True, help="stable_id của segment cần thử")
    parser.add_argument(
        "--variant",
        action="append",
        default=[],
        help="văn bản thay thế để so với bản gốc; lặp lại cờ này cho nhiều biến thể",
    )
    parser.add_argument("--takes", type=int, default=5, help="số lần sinh cho mỗi biến thể")
    args = parser.parse_args(argv)

    root = args.project_root.resolve()
    db = ProjectDB(root / "project.sqlite3")
    settings = load_settings(root / "book_settings.json")
    rows = [row for row in db.list_segments() if str(row["stable_id"]) == args.segment]
    if not rows:
        _say(f"không tìm thấy segment {args.segment}")
        return 2
    row = dict(rows[0])
    band = settings["tts"]["pace_chars_per_second"]
    out_dir = root / "work" / "rushed_line_probe"
    out_dir.mkdir(parents=True, exist_ok=True)

    _say(f"segment {args.segment}  (pace đã gán: {row.get('pace')})")
    _say(f"  băng chấp nhận: {band}")
    _say("")
    variants = [("gốc", str(row["text"]))] + [
        (f"biến thể {index}", text) for index, text in enumerate(args.variant, 1)
    ]
    coordinator = TTSCoordinator(settings, db, lambda _message: None)
    worst_ok = True
    try:
        for label, text in variants:
            chars = spoken_speakable_chars(text)
            syllables = spoken_syllables(text)
            _say(f"{label}: {text!r}")
            _say(f"   {chars} ký tự đọc được, {syllables} âm tiết")
            rates: list[float] = []
            for take in range(args.takes):
                probe_row = dict(row)
                probe_row["text"] = text
                output = out_dir / f"{label.replace(' ', '_')}_{take}.wav"
                try:
                    _checksum, metrics, _seed = coordinator.synthesize_atomic(
                        probe_row,
                        output,
                        seed_salt=f"rushed_probe_{take}",
                        repair_short_utterance=True,
                    )
                except Exception as exc:  # noqa: BLE001
                    # Cổng nhịp ném chính ở đây; vẫn đo được từ file đã ghi.
                    duration = float(sf.info(output).duration) if output.is_file() else 0.0
                    rate = chars / duration if duration else 0.0
                    rates.append(rate)
                    _say(
                        f"   lần {take}: {duration:5.2f}s  {rate:6.2f} kt/s  "
                        f"{(syllables / duration if duration else 0):5.2f} at/s  BỊ TỪ CHỐI: {str(exc)[:70]}"
                    )
                    continue
                duration = float(metrics.get("duration", 0.0)) or float(sf.info(output).duration)
                rate = float(metrics.get("chars_per_second", 0.0)) or (chars / duration)
                rates.append(rate)
                _say(
                    f"   lần {take}: {duration:5.2f}s  {rate:6.2f} kt/s  "
                    f"{(syllables / duration if duration else 0):5.2f} at/s  "
                    f"{'NGOÀI BĂNG' if metrics.get('pace_outlier') else 'đạt'}"
                )
            if rates:
                inside = sum(1 for r in rates if r <= float(band["normal"][1]))
                _say(
                    f"   → thấp nhất {min(rates):.2f} | cao nhất {max(rates):.2f} | "
                    f"{inside}/{len(rates)} lần trong băng normal (≤ {band['normal'][1]})"
                )
                worst_ok = worst_ok and inside > 0
            _say("")
    finally:
        coordinator.unload_all()
    _say(f"audio ở {out_dir}")
    return 0 if worst_ok else 1


if __name__ == "__main__":
    sys.exit(main())
