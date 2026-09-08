"""Va config.py + recovery.py: cong tat, va cong thu sau cung hoi ca hai nguon."""
import io
import sys
from pathlib import Path

root = Path(sys.argv[1])

# ------------------------------------------------------------------ config.py
p = root / "ebook_reader" / "config.py"
s = io.open(p, encoding="utf-8").read()

OLD = '''        "repair_rounds": 2,
        "failure_policy": "fail",
    },
    "perceptual_qa": {'''
NEW = '''        "repair_rounds": 2,
        "failure_policy": "fail",
        # Khi vòng sửa đã cạn và ASR vẫn không đọc được, ai quyết?
        #
        # Trước 2026-09-08 câu trả lời là "một người ngồi nghe", và khi không có người thì
        # chương ấy không bao giờ xuất bản. Chủ sách ra lệnh 2026-09-07: *"tôi không muốn
        # phải tự nghe, project phải hoạt động toàn bộ cho ra sản phẩm"*.
        #
        # Bật thì máy tự cho qua **những đoạn mà ASR là nhân chứng duy nhất** - xem
        # `MACHINE_ACCEPTABLE_SEGMENT_WARNINGS` và `_grant_machine_acceptances`. Nó không
        # sửa điểm số, không đổi trạng thái, không thăng bản thu nào: chỉ ghi một hàng nói
        # "chưa ai nghe cái này" rồi để chương đi tiếp. Tắt thì hành vi cũ trở lại nguyên
        # vẹn, và đó là lý do có công tắc chứ không phải xoá hẳn nhánh kia.
        "ship_without_a_listener": True,
    },
    "perceptual_qa": {'''
assert OLD in s, "khong khop asr block trong config"
s = s.replace(OLD, NEW, 1)
io.open(p, "w", encoding="utf-8").write(s)
print(f"da va {p}")

# ------------------------------------------------------------------ recovery.py
p = root / "ebook_reader" / "recovery.py"
s = io.open(p, encoding="utf-8").read()

OLD = '''def _listener_accepted_takes(db: ProjectDB) -> set[tuple[str, str]]:
    """(segment, checksum) pairs a person listened to and let stand.

    Loaded once per recovery scan rather than per segment: the scan walks every segment in
    the book and this is the same small table each time.
    """
    return set(db.accepted_segment_warnings())'''
NEW = '''def _listener_accepted_takes(db: ProjectDB) -> set[tuple[str, str]]:
    """(segment, checksum) pairs somebody - a person or the machine - has ruled on.

    Loaded once per recovery scan rather than per segment: the scan walks every segment in
    the book and this is the same small table each time.

    The sixth gate to consult an acceptance, and the last one to learn that the machine can
    now issue them too. It reads `ruled_` rather than `accepted_` for the same reason the
    other five do: the question here is whether anything still has to be re-decided, not who
    decided it. The name is left alone because every caller reads it as "already settled",
    which is still exactly what it means.
    """
    return db.ruled_segment_takes()'''
assert OLD in s, "khong khop _listener_accepted_takes"
s = s.replace(OLD, NEW, 1)
io.open(p, "w", encoding="utf-8").write(s)
print(f"da va {p}")
