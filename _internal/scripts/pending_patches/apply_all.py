r"""Áp toàn bộ bản vá đang chờ, đúng thứ tự, rồi chạy bộ test đầy đủ.

    python scripts/pending_patches/apply_all.py                 # thử, không ghi gì
    python scripts/pending_patches/apply_all.py --apply         # ghi thật rồi chạy test

**CHỈ CHẠY KHI KHÔNG CÓ LƯỢT `run` NÀO ĐANG BAY.** Bản vá trong `ORDER` sửa file nằm trong
`QUALITY_IMPLEMENTATION_FILES`, nên ghi vào chúng đổi `quality_implementation_hash()` và lượt
`resume` kế tiếp sẽ bị từ chối. Script tự kiểm điều này trước khi ghi, bằng nhịp tim của
`worker_leases` chứ không bằng file khoá.

`ORDER` là hàng chờ; `APPLIED` là hồ sơ những cái đã vào cây thật. Mỗi script `assert` chuỗi
gốc trước khi thay, nên áp sai thứ tự hay áp hai lần thì nó dừng chứ không làm hỏng file — đó
là lý do giữ lại `APPLIED` thay vì xoá.
"""
from __future__ import annotations

import argparse
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
VERSIONS = Path(r"D:\Novels\Audiobooks\_versions")
LEASE_STALE_SECONDS = 180.0

# `APPLIED` bên dưới ĐÃ vào cây thật; chúng assert chuỗi gốc nên chạy lại sẽ dừng chứ không
# hỏng gì.
#
# 2026-09-10, viết trong lúc lô 2 chạy bốn chương cuối. Áp ở ranh giới lô, **trước** lô vá cho
# lô 2 — nếu áp sau thì chương 031 và 043 lại hỏng đúng chỗ cũ.
#
# `ASR_TRANSCRIPT_RATE_IMPOSSIBLE` là em ruột của `ASR_TRANSCRIPT_TIMELINE_IMPOSSIBLE`:
# `_evaluate_transcript_core` trả hai mã cạnh nhau với hình dạng y hệt (`ASR_INCONCLUSIVE`,
# `repairable: False`, `severe: False`). Cái kia có chú thích ghi rõ nó "was a bare string in
# three places" — tức đã được nâng thành hằng số và đưa vào danh sách không-chặn; cái này bị bỏ
# sót trong đúng lần dọn ấy, vẫn là chuỗi trần ở một chỗ và không nằm trong danh sách nào.
#
# Lô 2 tính tiền hai chương cho chỗ bỏ sót ấy (031, 043), và cả hai đoạn là **tiếng cười**.
# Chạy thử trên bản sao: 266 test asr/policy/quality xanh.
ORDER: tuple[str, ...] = ("patch_rate_impossible_is_the_same_family.py",)

APPLIED = (
    "patch_reserve_all.py",
    "patch_reserve_test.py",
    "patch_name_no_halt.py",
    "patch_name_no_halt_test.py",
    "patch_pace_digits.py",
    "patch_pace_digits_test.py",
    "patch_ck_fold.py",
    "patch_ck_fold_test.py",
    "patch_ceiling_repairable.py",
    "patch_ceiling_repairable_test.py",
    "patch_quote_recovery.py",
    "patch_quote_tests.py",
    "patch_test2.py",
    "patch_short_anchor.py",
    "patch_anchor_test.py",
    "patch_laugh.py",
    "patch_known_carry.py",
    "patch_fakedb.py",
    # Cơ chế xuất bản khi không có ai để hỏi, 2026-09-08 12:2x. Bốn cái này là **một** thay
    # đổi và phải áp cùng nhau: bảng ở `_db`, cổng ở `_pipeline`, công tắc và cổng thứ sáu ở
    # `_wiring`, con số cho báo cáo ở `_report`. Áp thiếu `_wiring` thì bản quét recovery
    # không biết bảng mới và sẽ đánh hỏng lại đúng những đoạn vừa được cho qua.
    "patch_machine_accept_db.py",
    "patch_machine_accept_pipeline.py",
    "patch_machine_accept_wiring.py",
    "patch_machine_accept_report.py",
    # 2026-09-08 17:5x, tại ranh giới alpha.62 / lô 1.
    #
    # `patch_pin_voice_model` phải viết lại một lần: bản đầu nhét model giọng vào
    # `perceptual_cache_check` và `test_perceptual_cache_marker_requires_locked_revision_and_
    # checkpoint_hash` bắt ngay. Test ấy đúng - hàm kia đăng ký là `model:utmosv2_cache`, nên
    # thiếu ghim TTS sẽ báo thành lỗi perceptual. Bản sau có `voice_model_check` riêng.
    "patch_pin_voice_model.py",
    "patch_strip_zero_width.py",
    # 2026-09-08 19:4x, sau khi lô 1 chết ở đoạn 1.406/3.727 vì một nửa cặp surrogate lạc.
    "patch_lone_surrogate.py",
    # 2026-09-09 ~05:00, tại ranh giới lô 1 / lô vá. Năm cái này ra đời từ bốn kiểu hỏng thật
    # của lô 1, và bộ test bắt được HAI chỗ tôi đè lên quyết định cố ý của người trước:
    #
    #   - `patch_pace_relaxed_is_a_decision` ban đầu đưa `TTS_PACE_BAND_RELAXED` vào
    #     HIGH_QUALITY_ALLOWED_SEGMENT_WARNINGS. `test_the_warning_blocks_publication_so_a_
    #     person_hears_it` đỏ, và nó đúng: làm thế là biến mã ấy thành IM LẶNG, vứt mất tín
    #     hiệu "nên có người nghe". Sửa lại: cho vào MACHINE_ACCEPTABLE (có ghi sổ) thay vì
    #     ALLOWED (im lặng).
    #   - `patch_casting_gate_no_halt` làm `test_gender_conflict_fails_before_voice_casting`
    #     đỏ. Test ấy viết lại kèm lý do và cái giá, không xoá.
    "patch_asr_surrogate.py",
    "patch_casting_gate_no_halt.py",
    "patch_loudness_review_ships.py",
    "patch_pace_relaxed_is_a_decision.py",
    "patch_edge_fade.py",
    # 2026-09-09 ~10:50, tại ranh giới lô vá / lô 2. Hai bản vá **tài nguyên**, không phải chất
    # lượng — chúng không đổi một mẫu audio nào, chỉ đổi việc máy có chạy hay không và ai được
    # cấp giọng nào.
    #
    #   - `patch_pool_counts_its_own_ram`: pool TTS định cỡ chỉ theo VRAM. Đo giữa chương 007
    #     của lô vá: RAM trống 2,85 GB dưới sàn 3,5 GB, pool tự giữ 7,63 GB, GPU 0% và 4,6 W
    #     hơn nửa giờ với nhịp tim vẫn sống. Worker thứ ba là thứ làm cho không worker nào chạy
    #     được. Hằng số 2,65 GB không phải số mới: theo dõi đỉnh RSS 25 phút bắt được 14 worker
    #     TTS ở 2,68 cực đại / 2,57 trung vị, gần trùng phân bố worker cảm thụ mà người trước
    #     đã đo. Bản vá còn sửa một fixture cũ vốn thiếu trường `free_ram_gb` — thiếu đúng chỗ
    #     biến một hụt tài nguyên nhất thời thành cái chốt vĩnh viễn mà chính file test ấy cấm.
    #   - `patch_reserve_marks_the_slot`: `reserve()` chỉ nhận tên preset nên một giọng đã ghim
    #     nhích bộ đếm qua một bậc formant *bất kỳ*. Lô 1 mất bậc `0,898` của Thanh Bình trong
    #     khi `f104` phát cho cả CHA lẫn SỐ BA — một va chạm giọng tránh được hoàn toàn.
    "patch_reserve_marks_the_slot.py",
    "patch_pool_counts_its_own_ram.py",
)


def _say(line: str) -> None:
    try:
        print(line)
    except (UnicodeEncodeError, OSError, ValueError):
        sys.stdout.buffer.write(line.encode("utf-8", "replace") + b"\n")


def _runs_in_flight() -> list[tuple[Path, str]]:
    """Project nào thật sự đang chạy, kèm lý do - đọc nhịp tim, không đọc file khoá.

    Bản đầu của hàm này liệt kê mọi thư mục có `.worker.lock`, và gắn cờ **cả 41 project** kể
    cả những cái xong từ hôm kia: file khoá nằm lại sau khi tiến trình chết. Một bộ canh lúc
    nào cũng kêu thì tệ hơn không có bộ canh - nó chỉ dạy người ta gõ `--force`.

    Tín hiệu đúng nằm trong bảng `worker_leases`: một lượt đang bay có dòng `state='running'`
    với `heartbeat_at` vừa mới đây; một lượt đã xong không còn dòng nào. Đo lúc 00:24 ngày
    2026-09-08: alpha.56 nhịp cách 2 giây, alpha.50 không có dòng lease nào.

    Mở read-only để không chạm vào project đang chạy.
    """
    if not VERSIONS.is_dir():
        return []
    now = time.time()
    live: list[tuple[Path, str]] = []
    for database in sorted(VERSIONS.glob("*/*/project.sqlite3")):
        try:
            connection = sqlite3.connect(f"file:{database}?mode=ro", uri=True)
            connection.row_factory = sqlite3.Row
            try:
                rows = connection.execute(
                    "SELECT worker_name, pid, state, heartbeat_at FROM worker_leases"
                ).fetchall()
            finally:
                connection.close()
        except sqlite3.Error:
            # Một project hỏng hoặc đang bị khoá ghi không nói lên điều gì về việc nó có đang
            # chạy hay không; bỏ qua thay vì gắn cờ.
            continue
        for row in rows:
            if str(row["state"]) != "running":
                continue
            age = now - float(row["heartbeat_at"] or 0.0)
            if age <= LEASE_STALE_SECONDS:
                live.append(
                    (
                        database.parent,
                        f"lease {row['worker_name']} pid={row['pid']} nhịp cách {age:.0f}s",
                    )
                )
    return live


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--apply", action="store_true", help="Ghi thật thay vì chỉ liệt kê")
    parser.add_argument(
        "--skip-tests",
        action="store_true",
        help="Bỏ bước chạy test - chỉ dùng khi định chạy tay ngay sau đó",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Ghi kể cả khi phát hiện lượt chạy đang bay. Đừng.",
    )
    args = parser.parse_args(argv)

    if not ORDER:
        _say(f"Hàng chờ rỗng. {len(APPLIED)} bản vá đã vào cây thật; xem README.md.")
        return 0

    missing = [name for name in ORDER if not (HERE / name).is_file()]
    if missing:
        _say("thiếu bản vá: " + ", ".join(missing))
        return 2

    _say(f"{len(ORDER)} bản vá, theo thứ tự:")
    for index, name in enumerate(ORDER, 1):
        _say(f"  {index}. {name}")

    in_flight = _runs_in_flight()
    if in_flight:
        _say("")
        _say("CÓ LƯỢT CHẠY ĐANG BAY:")
        for path, why in in_flight:
            _say(f"   {path}")
            _say(f"      {why}")
        if not args.force:
            _say("")
            _say("Không ghi. Đợi nó xong, hoặc `stop` nó, rồi chạy lại.")
            return 1
        _say("   --force: ghi bất chấp. Lượt ấy sẽ không resume được.")
    else:
        _say("")
        _say("Không có lượt nào đang chạy.")

    if not args.apply:
        _say("")
        _say("Đây là lượt thử, chưa ghi gì. Thêm --apply để ghi thật.")
        return 0

    python = sys.executable
    for name in ORDER:
        _say("")
        _say(f"--- {name} ---")
        result = subprocess.run(
            [python, str(HERE / name), str(ROOT)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        _say((result.stdout or "").rstrip())
        if result.returncode != 0:
            _say((result.stderr or "").rstrip())
            _say("")
            _say(f"DỪNG ở {name}. Những bản vá trước nó ĐÃ được ghi - đừng chạy lại từ đầu,")
            _say("sửa cái này rồi áp nốt phần còn lại bằng tay.")
            return 1

    if args.skip_tests:
        _say("")
        _say("Đã áp hết. Bỏ qua test theo yêu cầu - hãy chạy chúng.")
        return 0

    _say("")
    _say("--- bộ test đầy đủ ---")
    tests = subprocess.run([python, "-m", "pytest", "-q"], cwd=str(ROOT), text=True)
    if tests.returncode != 0:
        _say("")
        _say("TEST ĐỎ. Đừng chạy lượt nào cho tới khi xanh lại.")
        return 1
    _say("")
    _say("Xanh hết. Giờ mới được chạy lượt mới.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
