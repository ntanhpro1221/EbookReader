"""Bản vá đổi VĂN BẢN NÓI thì bản thu cũ của những đoạn ấy phải thu lại — tìm chúng, không đoán.

    python scripts/resync_spoken_text.py <project>            # chỉ xem
    python scripts/resync_spoken_text.py <project> --apply     # đặt lại các đoạn lệch về chờ thu
    python scripts/resync_spoken_text.py --batch 1 [--apply]   # project lô 1 của cuốn đang cấu hình

Vì sao có file này (2026-09-14, 10:26): bản vá `patch_a_formula_is_read_as_words.py` đổi
`spoken_symbols_to_words` để "+" đọc thành "cộng". Chuỗi giao cho TTS **là một phần của bằng chứng**:
mỗi bản thu ghi `signal_json.spoken_text_sha256` của chuỗi đã đọc, và trước khi dùng lại bản thu ấy,
`pipeline._spoken_text_and_anchors` băm lại chuỗi từ mã HIỆN TẠI rồi so. Sau bản vá, đoạn duy nhất
trong lô 1 cuốn 2 có dấu "+" (chương 025, `c00026_s0000015`) lệch checksum → `RuntimeError:
spoken-text checksum drifted before candidate or final verification` → `UNRECOVERABLE_PIPELINE_ERROR`,
lô chết ở 25/49, ranh giới `run lai` và chết lại đúng chỗ ấy. Cổng kiểm **đúng**: văn bản đã đổi thì
bản thu cũ không còn là bản thu của văn bản này. Cái thiếu là một đường chữa: đặt lại đúng những đoạn
ấy về chờ thu, rồi để đường ống thu lại.

Chủ sách đã dặn: *"nhỡ sách khác cũng gặp chuyện thế này thì project phải tự xử lý được chứ?"* — đây là
phần trả lời cho lớp lỗi ấy.

**Không tự viết lại phép dẫn chuỗi.** Nó gọi đúng `BookPipeline._spoken_text_and_anchors` mà đường ống
gọi, dựng một pipeline không có runtime theo đúng lối `refresh_terminal_reports_without_runtime` (bỏ qua
`__init__`, không có resource manager, không có perceptual QA) cộng một `TTSCoordinator` — engine VieNeu
nạp **lười** (`self.tts = None` tới khi `load()`), nên script này không chạm GPU và không nạp model.
Một bản sao của luật băm ở đây sẽ lệch khỏi bản thật đúng vào ngày có bản vá kế tiếp.

**Phạm vi có chủ ý: một project, không phải cả cuốn.** Một lô đã xong, đã tag, đã ghép vào sách thì bản
thu của nó là bằng chứng đã đóng; đặt lại một đoạn ở đó làm chương mất tư cách xuất bản mà chẳng ai thu
lại (project ấy không chạy nữa). Chỉ project **sắp chạy tiếp** cần đồng bộ. Vì thế không có `--all`.

Đoạn được đặt lại mất WAV, `signal_json`, kết quả ASR và mã cảnh báo (`reset_segment_pending`) — tức mọi
bằng chứng nói về bản thu cũ, và không mất gì nói về văn bản hay dàn giọng. Ứng viên sửa thuộc policy đã
hết hiệu lực nằm im: chúng vô hình với policy hiện hành.

Mã thoát: 0 nếu không đoạn nào lệch (hoặc đã đặt lại xong), 1 nếu có đoạn lệch mà chưa `--apply`.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from scripts.book_paths import VERSIONS  # noqa: E402
except ImportError:  # chạy trực tiếp: scripts/ là sys.path[0]
    from book_paths import VERSIONS  # noqa: E402

from ebook_reader.cli import _open_project  # noqa: E402
from ebook_reader.pipeline import BookPipeline  # noqa: E402
from ebook_reader.quality_policy import build_quality_policy, quality_policy_hash  # noqa: E402
from ebook_reader.tts import TTSCoordinator  # noqa: E402

DRIFT_MESSAGE = "spoken-text checksum drifted"


def _say(text: str) -> None:
    try:
        print(text, flush=True)
    except UnicodeEncodeError:
        print(text.encode("ascii", "backslashreplace").decode("ascii"), flush=True)


def _reader(paths, db, settings) -> BookPipeline:
    """Pipeline chỉ để DẪN CHUỖI: không runtime, không model, không ghi gì."""
    reader = object.__new__(BookPipeline)
    reader.paths = paths
    reader.db = db
    reader.settings = settings
    reader.quality_policy = build_quality_policy(settings)
    reader.quality_policy_hash = quality_policy_hash(reader.quality_policy)
    reader.log = lambda _message: None
    reader.tts = TTSCoordinator(settings, db, reader.log)
    return reader


def drifted(paths, db, settings) -> list[dict]:
    """Đoạn nào có bản thu mà chuỗi nói của mã hiện tại không còn khớp checksum đã ghi."""
    reader = _reader(paths, db, settings)
    out: list[dict] = []
    for row in db.list_segments():
        item = dict(row)
        if not item.get("wav_sha256") or not item.get("signal_json"):
            continue  # chưa có bản thu thì không có gì lệch
        try:
            reader._spoken_text_and_anchors(item)
        except RuntimeError as exc:
            if DRIFT_MESSAGE not in str(exc):
                raise
            out.append(item)
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("project", nargs="?", help="thư mục project")
    parser.add_argument("--batch", type=int, help="lấy project lô N của cuốn đang cấu hình")
    parser.add_argument("--apply", action="store_true", help="đặt lại các đoạn lệch (mặc định chỉ xem)")
    args = parser.parse_args(argv)

    root: Path | None = Path(args.project).resolve() if args.project else None
    if root is None and args.batch is not None:
        try:
            from scripts.seed_chain import batch_project  # noqa: PLC0415
        except ImportError:
            from seed_chain import batch_project  # noqa: PLC0415
        found = batch_project(args.batch, VERSIONS)
        if found is None:
            _say(f"không có project lô {args.batch} dưới {VERSIONS}")
            return 2
        root = Path(found)
    if root is None:
        parser.error("cần <project> hoặc --batch N")

    paths, db, settings = _open_project(root, read_only=not args.apply)
    rows = drifted(paths, db, settings)
    _say(f"project: {root}")
    if not rows:
        _say("  không đoạn nào lệch chuỗi nói.")
        return 0
    _say(f"  {len(rows)} đoạn lệch chuỗi nói ({'ĐẶT LẠI' if args.apply else 'chỉ xem'}):")
    for item in rows:
        _say(f"    {item['stable_id']}  [{item['status']}]  {str(item['text'])[:70]}")
        if args.apply:
            db.reset_segment_pending(
                int(item["id"]),
                "chuỗi nói đổi sau một bản vá: bản thu cũ không còn là bản thu của văn bản này",
            )
    if not args.apply:
        _say("  thêm --apply để đặt chúng về chờ thu (chỉ làm khi KHÔNG có lô nào đang bay).")
        return 1
    _say("  đã đặt lại; lượt `cli run` kế tiếp sẽ thu lại chúng.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
