r"""Va tts_pool.py + pipeline.py: pool TTS phai dem chinh RAM cua no truoc khi dung.

CHUA AP luc viet - lo01v dang chay. Ap o ranh gioi lo, truoc lo 2.

Do giua chuong 007 cua lo va: RAM trong 2,85 GB duoi san 3,5 GB, pool dang giu 7,63 GB, GPU
0% va 4,6 W trong hon nua gio. Worker thu ba chinh la thu day luot chay vao trang thai khong
worker nao duoc chay. Xem docs/A_POOL_THAT_FORBIDS_ITSELF.md.
"""
import io
import os
import sys
import tempfile
from pathlib import Path


def write_atomic(path: Path, text: str) -> None:
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    os.close(fd)
    io.open(tmp, "w", encoding="utf-8").write(text)
    os.replace(tmp, path)


root = Path(sys.argv[1])

# ================================================================= tts_pool.py
p = root / "ebook_reader" / "tts_pool.py"
s = io.open(p, encoding="utf-8").read()

OLD = """TTS_POOL_WORKER_THREADS = 1"""
NEW = '''def workers_for_ram(
    ceiling: int,
    free_ram_gb: float,
    floor_gb: float,
    worker_ram_gb: float,
) -> int:
    """How many workers the machine's RAM can hold above the throttle's own floor.

    `workers_for_vram` above asks whether the card can hold them. Nothing asked whether the
    machine could, and one synthesis worker costs about 2.3 GB of system RAM against roughly
    900 MiB of VRAM - so on this box RAM binds first and the VRAM answer was the only one
    anybody computed.

    Measured mid-chapter on the 2026-09-09 repair batch: 2.85 GB free against a 3.5 GB floor,
    the pool itself holding 7.63 GB, GPU at 0% and 4.6 W for over half an hour. Below the
    floor `decide()` reports memory pressure and turns off **both** `allow_new_gpu_batch` and
    `allow_cpu_heavy_work`, so the third worker is precisely what makes zero workers runnable.
    Two workers would have left 5.39 GB free and run without stopping.

    `floor_gb` is the throttle's own `resources.min_free_ram_gb`, passed in rather than read
    here, for the reason `perceptual_qa.usable_for` gives for doing the same: a pool that
    invents its own floor sizes itself into the band where the governor forbids its work. The
    same argument applies to `worker_ram_gb`, which is why this takes it instead of defining a
    second per-worker constant beside the one `perceptual_qa` already measured on peak RSS.

    That reuse is measured, not assumed. Tracking peak RSS per pid over 25 minutes caught 14
    synthesis workers at 2.68 GB max and 2.57 median, against the 2.68 max and 2.50 median
    `perceptual_qa` recorded for 31 scoring workers - near-identical distributions, and 2.65
    sits just under both maxima. The same window found free RAM below the 3.5 GB floor 36.5%
    of the time.

    Returns the ceiling untouched when RAM cannot be read as a positive number, matching
    `workers_for_vram`'s rule that measurement may only lower a ceiling, never raise or
    invent one.
    """
    ceiling = max(0, int(ceiling))
    if ceiling < 2 or worker_ram_gb <= 0 or free_ram_gb <= 0:
        return ceiling
    spare = float(free_ram_gb) - max(0.0, float(floor_gb))
    affordable = int(max(0.0, spare) // float(worker_ram_gb))
    if affordable < 2:
        # One worker in a pool is the sequential path with extra machinery around it - the
        # same rule `workers_for_vram` applies, for the same reason.
        return 0
    return min(ceiling, affordable)


TTS_POOL_WORKER_THREADS = 1'''
assert OLD in s, "khong khop cho chen workers_for_ram"
s = s.replace(OLD, NEW, 1)
write_atomic(p, s)
print("da va", p)

# ================================================================= pipeline.py
p = root / "ebook_reader" / "pipeline.py"
s = io.open(p, encoding="utf-8").read()

OLD = """            from .tts_pool import SynthesisPool, workers_for_vram"""
NEW = """            from .tts_pool import SynthesisPool, workers_for_ram, workers_for_vram"""
assert OLD in s, "khong khop import"
s = s.replace(OLD, NEW, 1)

OLD = """            snapshot = self.resources.snapshot()
            workers = workers_for_vram(
                ceiling, snapshot.gpu_free_mb, snapshot.gpu_total_mb
            )
            if workers < 2:"""
NEW = '''            snapshot = self.resources.snapshot()
            workers = workers_for_vram(
                ceiling, snapshot.gpu_free_mb, snapshot.gpu_total_mb
            )
            # And against the machine, not only the card. `_synthesis_pool_ram_reserve`
            # already knows what a synthesis worker costs in RAM - it hands that number to
            # the *perceptual* pool so scoring leaves room for this one. Nothing pointed it
            # the other way, so this pool could take the machine below the throttle's floor
            # and then be stopped by the throttle it had just tripped.
            #
            # The floor is the throttle's own, read from settings rather than chosen here.
            #
            # This reading is clean, and that is worth checking rather than assuming: a pool
            # sized while its own predecessor is still resident would under-read free RAM and
            # shrink itself a little further every round. `SynthesisPool.close()` calls
            # `pool.close()` then `pool.join()`, so the workers are gone before this returns,
            # and the only path back into this sizing block is through a close - a live pool
            # is returned above without re-sizing.
            floor_ram_gb = float(
                self.settings.get("resources", {}).get("min_free_ram_gb", 3.5)
            )
            by_ram = workers_for_ram(
                ceiling,
                float(snapshot.free_ram_gb),
                floor_ram_gb,
                PERCEPTUAL_WORKER_RAM_GB,
            )
            if by_ram < workers:
                self.log(
                    f"Pool TTS thu còn {by_ram}/{workers} worker: RAM trống "
                    f"{snapshot.free_ram_gb:.1f} GB, sàn {floor_ram_gb:.1f} GB, "
                    f"mỗi worker ~{PERCEPTUAL_WORKER_RAM_GB:.1f} GB."
                )
                workers = by_ram
            if workers < 2:'''
assert OLD in s, "khong khop cho tinh workers"
s = s.replace(OLD, NEW, 1)

# Thong bao cu chi noi ve VRAM; gio no co the sai ly do.
OLD = '''                self.log(
                    f"VRAM còn {snapshot.gpu_free_mb} MiB, không đủ cho pool TTS "
                    f"({ceiling} worker mong muốn); tổng hợp tuần tự chương này."
                )
                return None'''
NEW = '''                # Nói đúng cái đang thiếu. Bản trước luôn đổ cho VRAM, và từ khi RAM cũng
                # có thể là ràng buộc thì một dòng log sai lý do sẽ gửi người đọc đi tìm
                # nhầm chỗ - đúng chỗ mà chương 007 của lô vá đã làm tôi mất nửa giờ.
                short = "RAM" if by_ram < 2 else "VRAM"
                self.log(
                    f"{short} không đủ cho pool TTS ({ceiling} worker mong muốn): "
                    f"VRAM còn {snapshot.gpu_free_mb} MiB, RAM trống "
                    f"{snapshot.free_ram_gb:.1f} GB trên sàn {floor_ram_gb:.1f} GB; "
                    "tổng hợp tuần tự chương này."
                )
                return None'''
assert OLD in s, "khong khop log thieu vram"
s = s.replace(OLD, NEW, 1)
write_atomic(p, s)
print("da va", p)

TEST = '''"""Pool TTS phải đếm chính RAM của nó, không chỉ VRAM của card.

Đo giữa chương 007 của lô vá ngày 2026-09-09: RAM trống 2,85 GB dưới sàn 3,5 GB, pool giữ
7,63 GB, GPU 0% và 4,6 W hơn nửa giờ với nhịp tim vẫn sống. Dưới sàn, `decide()` tắt cả
`allow_new_gpu_batch` lẫn `allow_cpu_heavy_work` — nên worker thứ ba là thứ làm cho **không**
worker nào chạy được. Xem docs/A_POOL_THAT_FORBIDS_ITSELF.md.
"""
from __future__ import annotations

from ebook_reader.tts_pool import workers_for_ram

WORKER_GB = 2.65
FLOOR = 3.5


def test_the_case_that_stalled_chapter_007() -> None:
    """10,5 GB trống trước khi dựng pool: ba worker để lại 2,6 GB, dưới sàn."""
    assert workers_for_ram(3, 10.48, FLOOR, WORKER_GB) == 2


def test_a_machine_with_room_keeps_the_whole_ceiling() -> None:
    assert workers_for_ram(3, 20.0, FLOOR, WORKER_GB) == 3


def test_below_the_floor_there_is_no_pool_at_all() -> None:
    """Một worker trong pool là đường tuần tự kèm thêm máy móc — trả 0, không trả 1."""
    assert workers_for_ram(3, 4.0, FLOOR, WORKER_GB) == 0
    assert workers_for_ram(3, 3.0, FLOOR, WORKER_GB) == 0


def test_it_only_ever_lowers_the_ceiling() -> None:
    """Cùng luật `workers_for_vram` theo: phép đo chỉ được hạ trần, không được nâng."""
    assert workers_for_ram(2, 100.0, FLOOR, WORKER_GB) == 2
    assert workers_for_ram(0, 100.0, FLOOR, WORKER_GB) == 0


def test_an_unreadable_reading_does_not_shrink_anything() -> None:
    """Không đọc được RAM thì giữ nguyên trần, y như card không đọc được VRAM."""
    assert workers_for_ram(3, 0.0, FLOOR, WORKER_GB) == 3
    assert workers_for_ram(3, 20.0, FLOOR, 0.0) == 3


def test_the_floor_is_not_hardcoded() -> None:
    """Sàn đến từ `resources.min_free_ram_gb`; đổi sàn phải đổi câu trả lời.

    Đây là chỗ `perceptual_qa.usable_for` từng sai: nó dùng 2,0 cứng trong khi bộ điều tiết
    dùng 3,5, nên pool tự đặt máy vào đúng dải mà bộ điều tiết cấm làm việc.
    """
    assert workers_for_ram(3, 9.0, 0.0, WORKER_GB) == 3
    assert workers_for_ram(3, 9.0, 3.5, WORKER_GB) == 2
'''

q = root / "tests" / "test_pool_counts_its_own_ram.py"
write_atomic(q, TEST)
print("da tao", q)

# ---------------------------------------------------------------- fixture cu thieu truong
# `test_pool_vram_shortage_is_not_permanent` dung mot snapshot gia chi co hai truong VRAM.
# `ResourceSnapshot` that co `free_ram_gb`, nen fixture ay thieu chu khong phai bai vo hieu -
# nhung thieu o dung cho lam lo ra mot chuyen that: khoi ma tinh co worker nam TRONG `try`,
# nen mot AttributeError o do bien "thieu tai nguyen mot luc" thanh "pool hong ca luot chay",
# dung dieu file test ay sinh ra de cam.
p = root / "tests" / "test_pool_vram_shortage_is_not_permanent.py"
s = io.open(p, encoding="utf-8").read()
OLD = """    pipeline.resources = SimpleNamespace(
        snapshot=lambda: SimpleNamespace(gpu_free_mb=free_mb, gpu_total_mb=8151)
    )"""
NEW = """    # `free_ram_gb` là trường thật của `ResourceSnapshot`, và từ khi pool cũng đếm RAM thì
    # thiếu nó ở đây làm `_synthesis_pool` ném AttributeError bên trong `try` — tức biến một
    # thiếu hụt nhất thời thành cái chốt vĩnh viễn mà chính file này cấm. Cho dư RAM, vì bài
    # test này nói về VRAM.
    pipeline.resources = SimpleNamespace(
        snapshot=lambda: SimpleNamespace(
            gpu_free_mb=free_mb, gpu_total_mb=8151, free_ram_gb=20.0
        )
    )"""
assert OLD in s, "khong khop fixture snapshot"
s = s.replace(OLD, NEW, 1)

OLD = """def test_parallel_workers_below_two_still_returns_none() -> None:"""
NEW = """def test_a_ram_shortage_does_not_latch_either() -> None:
    \"\"\"Thiếu RAM cũng là đọc một khoảnh khắc, y như thiếu VRAM — không được chốt.

    Thêm cùng lúc với việc pool bắt đầu đếm RAM: nếu không có bài này thì đường mới sẽ là
    đường duy nhất trong hàm chưa ai kiểm xem nó có chốt hay không, và chốt là thứ đã tốn
    alpha.44 khoảng 2.037 giây.
    \"\"\"
    pipeline = _pipeline(8000)
    pipeline.resources = SimpleNamespace(
        snapshot=lambda: SimpleNamespace(
            gpu_free_mb=8000, gpu_total_mb=8151, free_ram_gb=3.6
        )
    )

    assert pipeline._synthesis_pool() is None
    assert pipeline._tts_pool_failed is False
    assert any("RAM" in line for line in pipeline.log.lines)


def test_parallel_workers_below_two_still_returns_none() -> None:"""
assert OLD in s, "khong khop cho chen bai test RAM"
s = s.replace(OLD, NEW, 1)
write_atomic(p, s)
print("da va", p)
