r"""Trần khung có đang cắt mất một câu đọc đúng không? — phép thử cần GPU.

    python scripts/probe_frame_cap.py <project_root> --segment c00007_s0000084_9aa0f033c506

**CHỈ CHẠY KHI MÁY RẢNH.** Nó nạp VieNeu lên GPU và sinh audio; chạy đè lên một lượt `run`
đang bay sẽ tranh VRAM với chính lượt ấy.

## Câu hỏi

`"Rồi, rồi,"` của alpha.55 có năm bản thu, **cả năm dài đúng 0,96 giây** — bằng trần khung 12 —
với `trailing_rms` gấp 20–40 lần sàn im lặng. Bản thu bị cắt thật, nên `generation_endpoint_
active` chặn là đúng. Nhưng vòng sửa dùng cùng một trần ở cả năm vòng, nên nó **không thể** thoát:
đổi seed không sửa được lỗi do trần gây ra. Chương 016 vì thế bị chặn vĩnh viễn.

Hai giả thuyết, và chúng đòi hai cách sửa khác hẳn nhau:

1. **Câu cần dài hơn 12 khung.** Nới trần thì nó kết thúc tự nhiên. Sửa đúng: trần căn theo độ
   dài lời chứ không phải một hằng số theo số ký tự.
2. **Mô hình không chịu dừng trên câu không hạ giọng.** Nới tới 32 khung nó vẫn còn to ở cuối,
   nghĩa là trần đang *che* một lỗi khác — và sửa đúng nằm ở chỗ đưa văn bản cho TTS, không
   phải ở trần.

Script này phân biệt hai giả thuyết ấy bằng cách sinh lại đúng segment đó ở nhiều trần khung
rồi báo: dài bao nhiêu, có chạm trần không, cuối còn to bao nhiêu.

**Đọc bảng thế nào.** Nếu thời lượng tăng theo trần rồi *dừng lại* ở một mức và `endpoint`
tắt — giả thuyết 1, nới trần là xong. Nếu thời lượng bám sát trần ở mọi mức và `endpoint` luôn
bật — giả thuyết 2, nới trần chỉ đổi chỗ vết cắt.

Nó **không sửa gì cả**, chỉ ghi ra `work/frame_cap_probe/` để nghe.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import soundfile as sf  # noqa: E402

from ebook_reader.audio_io import segment_duration_policy  # noqa: E402
from ebook_reader.config import load_settings  # noqa: E402
from ebook_reader.database import ProjectDB  # noqa: E402
from ebook_reader.tts import TTSCoordinator  # noqa: E402

CAPS = (12, 16, 20, 24, 32)


def _say(line: str) -> None:
    try:
        print(line)
    except (UnicodeEncodeError, OSError, ValueError):
        sys.stdout.buffer.write(line.encode("utf-8", "replace") + b"\n")


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__.splitlines()[0],
        epilog="Chi tiết ở đầu file, và ở docs/WHY_A_GOOD_TAKE_GETS_THROWN_AWAY.md.",
    )
    parser.add_argument("project_root", type=Path)
    parser.add_argument(
        "--segment",
        required=True,
        help="stable_id của segment cần thử",
    )
    parser.add_argument(
        "--caps",
        type=int,
        nargs="+",
        default=list(CAPS),
        help=f"các trần khung cần thử, mặc định {' '.join(str(c) for c in CAPS)}",
    )
    args = parser.parse_args(argv)

    root = args.project_root.resolve()
    db = ProjectDB(root / "project.sqlite3")
    settings = load_settings(root / "book_settings.json")

    rows = [
        row
        for row in db.list_segments()
        if str(row["stable_id"]) == args.segment
    ]
    if not rows:
        _say(f"không tìm thấy segment {args.segment}")
        return 2
    row = dict(rows[0])

    out_dir = root / "work" / "frame_cap_probe"
    out_dir.mkdir(parents=True, exist_ok=True)

    _say(f"segment {args.segment}")
    _say(f"  lời:        {str(row['text'])!r}")
    _say(f"  bản đang giữ: {row['wav_duration']}s")

    # _max_new_frames lấy min(policy_frames, trần). Nới trần cao hơn con số này thì bị kẹp,
    # và bảng dưới sẽ phẳng vì chính sách độ dài chứ không phải vì mô hình - đúng loại hiểu
    # nhầm mà tài liệu kèm theo được viết ra để cảnh báo.
    policy_frames = segment_duration_policy(
        str(row["text"]), settings, row
    ).generation_max_frames
    _say(f"  trần theo chính sách độ dài: {policy_frames} khung  <- trần thử cao hơn số này sẽ bị kẹp")
    _say("")
    _say(f"{'trần':>6} {'thời lượng':>11} {'chạm trần':>10} {'endpoint':>9} {'trailing_rms':>13}")

    coordinator = TTSCoordinator(settings, db, _say)
    try:
        for cap in args.caps:
            probe_row = dict(row)
            probe_row["generation_frame_cap"] = int(cap)
            output = out_dir / f"cap_{cap:03d}.wav"
            _checksum, metrics, _seed = coordinator.synthesize_atomic(
                probe_row,
                output,
                # MỘT seed cho mọi trần. Bản đầu đặt seed theo từng trần, tức đổi trần
                # LẪN seed cùng lúc - và bảng đầu tiên nó in ra có trần 24 và trần-32-kẹp-về-24
                # cho hai kết quả khác nhau, tức toàn bộ biến thiên quan sát được có thể chỉ là
                # phương sai của seed. Muốn đo tác động của trần thì mọi thứ khác phải đứng yên.
                seed_salt="frame_cap_probe",
                repair_short_utterance=True,
            )
            duration = float(metrics.get("duration", 0.0)) or float(
                sf.info(output).duration
            )
            hit = bool(metrics.get("generation_ceiling_hit"))
            endpoint = bool(metrics.get("generation_endpoint_active"))
            trailing = float(metrics.get("trailing_rms", 0.0))
            clamped = " (bị kẹp)" if cap > policy_frames else ""
            _say(
                f"{cap:>6} {duration:>10.2f}s {hit!s:>10} {endpoint!s:>9} {trailing:>13.4f}"
                f"{clamped}"
            )
    finally:
        coordinator.unload_all()

    _say("")
    _say(f"File để nghe: {out_dir}")
    _say(
        "Thời lượng tăng rồi dừng, endpoint tắt  -> giả thuyết 1, trần quá chặt.\n"
        "Thời lượng bám sát trần, endpoint luôn bật -> giả thuyết 2, trần đang che lỗi khác."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
