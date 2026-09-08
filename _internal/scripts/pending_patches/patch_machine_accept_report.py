"""Va pipeline.py: bao cao chat luong phai noi ro chuong nao mang doan chua ai nghe."""
import io
import sys
from pathlib import Path

root = Path(sys.argv[1])
p = root / "ebook_reader" / "pipeline.py"
s = io.open(p, encoding="utf-8").read()

OLD = """            blocking_segment_warnings = self._high_quality_blocking_segment_warnings(
                chapter_segments
            )"""
NEW = """            blocking_segment_warnings = self._high_quality_blocking_segment_warnings(
                chapter_segments
            )
            # Ràng buộc thứ ba của cơ chế tự cho qua: **không im lặng**. Chủ sách ra lệnh
            # không phải nghe, chứ không ra lệnh không được biết - và một chương xuất bản
            # mang bản thu chưa ai xác nhận mà không nói ra thì con số `passed` ở đầu báo
            # cáo đang nói quá về chính nó.
            #
            # Đếm ở đây chứ không ở lúc cấp phép, vì con số phải đúng **lúc đọc báo cáo**:
            # một người nghe sau đó và chấp nhận thì đoạn ấy hết là "chưa ai nghe", còn một
            # bản thu bị cắt lại thì chấp nhận cũ vô hiệu và nó cũng hết được tính.
            heard_by_a_person = set(self.db.accepted_segment_warnings())
            accepted_by_machine = set(self.db.machine_accepted_segment_warnings())
            unheard = sorted(
                str(row["stable_id"])
                for row in chapter_segments
                if (str(row["stable_id"]), str(row["wav_sha256"] or "")) in accepted_by_machine
                and (str(row["stable_id"]), str(row["wav_sha256"] or "")) not in heard_by_a_person
            )"""
assert OLD in s, "khong khop cho chen dem unheard"
s = s.replace(OLD, NEW, 1)

OLD = """                        "blocking_warnings": blocking_segment_warnings,
                    },"""
NEW = """                        "blocking_warnings": blocking_segment_warnings,
                        # Những đoạn vào sách vì máy tự cho qua và tới giờ vẫn chưa ai
                        # nghe. `scripts/machine_acceptances.py` in ra chúng kèm mốc thời
                        # gian trong MP3, để nghe *nếu muốn* - không có gì đứng chờ.
                        "unheard_segments": unheard,
                    },"""
assert OLD in s, "khong khop segment_summary"
s = s.replace(OLD, NEW, 1)

io.open(p, "w", encoding="utf-8").write(s)
print(f"da va {p}")
