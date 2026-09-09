"""Pool TTS phải đếm chính RAM của nó, không chỉ VRAM của card.

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
