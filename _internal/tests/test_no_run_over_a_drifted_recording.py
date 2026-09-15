"""Không `cli run` lên một bản thu đã lệch chuỗi nói — mọi đường vào `run` phải resync trước.

`pipeline._spoken_text_and_anchors` băm lại chuỗi giao cho TTS từ mã **hiện tại** và so với
checksum ghi kèm bản thu; lệch thì `RuntimeError: spoken-text checksum drifted` →
`UNRECOVERABLE_PIPELINE_ERROR`. Cổng ấy đúng, và `scripts/resync_spoken_text.py` là đường chữa:
đặt đúng những đoạn lệch về chờ thu rồi để đường ống thu lại.

Chỗ dễ sai là **ai gọi nó**. Tên project là nội-dung-địa-chỉ theo (tiêu đề, nguồn), nên chạy lại
cùng một lô — hay cạn vòng chữ cái trong `launch_repair.sh` — **mở lại project cũ cùng mọi bản thu
của nó**. Nếu giữa hai lần có một bản vá đổi `spoken_symbols_to_words` / chuẩn hoá tiếng / phiên âm
(đúng việc bước 1 của mỗi ranh giới làm), bản thu cũ trở thành bản thu của một văn bản khác. Đã xảy
ra thật hai lần:

- lô 1 cuốn 2, 10:26 ngày 14-09: lô chết ở 25/49, `run lai` của bước 0 chết lại đúng đoạn ấy;
- 106/007/084, sáng 11-09: `create` mở lại project cũ, `run` từ chối resume, cả chuỗi ghi "xong"
  trong hai phút mà không thu gì.

Bài này ghim **thứ tự văn bản**: trong mỗi script, lần gọi `resync_spoken_text.py` đầu tiên phải
đứng TRƯỚC lần gọi `cli run` cuối cùng. Thô nhưng bắt đúng lớp lỗi "ai đó thêm một đường `run` mới
mà quên resync" — lớp lỗi duy nhất ở đây, vì cả ba script đều tuyến tính.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ["boundary.sh", "launch_batch.sh", "launch_repair.sh"]

RESYNC = "scripts/resync_spoken_text.py"
RUN = "ebook_reader.cli run"


def _live_lines(name: str) -> list[str]:
    """Bỏ dòng chú thích: tên script xuất hiện đầy trong chú thích của nhau."""
    text = (ROOT / "scripts" / name).read_text(encoding="utf-8")
    return [line for line in text.splitlines() if not line.lstrip().startswith("#")]


def test_every_path_into_run_resyncs_first() -> None:
    for name in SCRIPTS:
        lines = _live_lines(name)
        resyncs = [i for i, line in enumerate(lines) if RESYNC in line]
        runs = [i for i, line in enumerate(lines) if RUN in line]
        assert runs, f"{name}: không còn gọi `cli run`? bài này phải được viết lại"
        assert resyncs, f"{name}: gọi `cli run` mà không resync chuỗi nói"
        assert resyncs[0] < runs[-1], (
            f"{name}: resync ở dòng {resyncs[0]} nằm SAU `cli run` ở dòng {runs[-1]}"
        )


def test_resync_is_applied_not_merely_inspected() -> None:
    """`--apply` mới đặt lại; thiếu nó thì script in ra rồi vẫn chạy `run` lên bản thu lệch."""
    for name in SCRIPTS:
        for line in _live_lines(name):
            if RESYNC in line:
                assert "--apply" in line, f"{name}: resync mà không --apply: {line.strip()}"


def test_the_repair_loop_says_when_it_reopens_a_project() -> None:
    """Cạn vòng chữ cái là đường duy nhất `launch_repair.sh` mở lại project cũ - đừng để nó im."""
    lines = _live_lines("launch_repair.sh")
    assert any("FREE=0" in line for line in lines), "mất cờ phân biệt 'lần đầu' với 'hết chữ cái'"
    assert any("HET chu cai" in line for line in lines), "hết chữ cái phải nói ra trong log"
