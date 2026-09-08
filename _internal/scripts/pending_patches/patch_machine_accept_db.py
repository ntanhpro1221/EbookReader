"""Va database.py: chap nhan co nguon goc MAY, va MOT accessor cho moi cong goi."""
import io
import sys
from pathlib import Path

root = Path(sys.argv[1])
p = root / "ebook_reader" / "database.py"
s = io.open(p, encoding="utf-8").read()

OLD_SCHEMA = """CREATE TABLE IF NOT EXISTS listener_audio_acceptances (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    segment_stable_id TEXT NOT NULL,
    wav_sha256 TEXT NOT NULL,
    warning_code TEXT NOT NULL,
    note TEXT NOT NULL DEFAULT '',
    created_at REAL NOT NULL,
    UNIQUE (segment_stable_id, wav_sha256, warning_code)
);"""

NEW_SCHEMA = OLD_SCHEMA + """

-- Cùng khoá, cùng tác dụng lên các cổng, KHÁC nguồn gốc.
--
-- Cố ý là bảng riêng chứ không phải một cột `source` trên bảng trên. Hai kiểu hỏng, và
-- chúng không ngang nhau: quên union bảng này thì một chương bị chặn oan - ồn ào, thấy
-- ngay, sửa được. Quên lọc một cột `source` thì báo cáo nói "người đã nghe" về một bản
-- thu chưa ai nghe - im lặng, và là nói dối chủ sách về chính thứ ông ấy uỷ quyền.
-- Chọn kiểu hỏng ồn ào.
CREATE TABLE IF NOT EXISTS machine_audio_acceptances (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    segment_stable_id TEXT NOT NULL,
    wav_sha256 TEXT NOT NULL,
    warning_code TEXT NOT NULL,
    reason TEXT NOT NULL DEFAULT '',
    created_at REAL NOT NULL,
    UNIQUE (segment_stable_id, wav_sha256, warning_code)
);"""

assert OLD_SCHEMA in s, "khong khop schema"
s = s.replace(OLD_SCHEMA, NEW_SCHEMA, 1)

ANCHOR = "    def accepted_segment_warnings(self) -> dict[tuple[str, str], set[str]]:"
assert ANCHOR in s, "khong khop accepted_segment_warnings"

METHODS = '''    def accept_segment_audio_as_machine(
        self,
        *,
        segment_stable_id: str,
        wav_sha256: str,
        warning_code: str,
        reason: str,
    ) -> bool:
        """Máy tự cho một bản thu đi tiếp, vì không còn ai để hỏi. True nếu là lần đầu.

        Chủ sách ra lệnh 2026-09-07: *"tôi không muốn phải tự nghe, project phải hoạt động
        toàn bộ cho ra sản phẩm"*. Đây là cách thi hành lệnh ấy mà không nói dối về chất
        lượng. Bản thu **giữ nguyên** trạng thái `failed` và giữ nguyên mã cảnh báo của nó -
        máy không đổi ý điều gì, đúng như khi một người nghe đè lên nó; chỉ có cái chốt chặn
        chương là được mở, và mở ở chỗ ghi lại được là ai mở.

        Khoá theo checksum như mọi chấp nhận khác, nên `retry` cắt lại bản thu là chấp nhận
        này hết hiệu lực với bản mới. `reason` bắt buộc có: một dòng nói vì sao máy dám, và
        nó đi thẳng vào báo cáo.
        """
        stable_id = str(segment_stable_id).strip()
        checksum = str(wav_sha256).strip().casefold()
        code = str(warning_code).strip()
        justification = str(reason).strip()
        # `require_all` chứ không phải một `if a or b or c` - luật của repo, ghim bằng
        # `test_no_new_blind_compound_check_is_added`, và nó bắt được đúng dòng này khi tôi
        # bê nguyên dáng của `accept_segment_audio`. Bốn điều kiện sau một câu thông báo thì
        # người đọc lỗi phải chạy lại mới biết cái nào hỏng; ở đây cái nào hỏng thì gọi tên.
        require_all(
            "chấp nhận của máy thiếu thông tin bắt buộc",
            ("segment_stable_id", not stable_id),
            ("wav_sha256", not checksum),
            ("warning_code", not code),
            ("reason", not justification),
            _error=ValueError,
        )
        with self.transaction() as conn:
            cursor = conn.execute(
                """
                INSERT OR IGNORE INTO machine_audio_acceptances
                    (segment_stable_id, wav_sha256, warning_code, reason, created_at)
                VALUES (?,?,?,?,?)
                """,
                (stable_id, checksum, code, justification, time.time()),
            )
            return cursor.rowcount > 0

    def machine_accepted_segment_warnings(self) -> dict[tuple[str, str], set[str]]:
        """Cảnh báo MÁY đã tự cho qua. Tách hẳn khỏi `accepted_segment_warnings`."""
        accepted: dict[tuple[str, str], set[str]] = {}
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT segment_stable_id, wav_sha256, warning_code "
                "FROM machine_audio_acceptances"
            ).fetchall()
        for row in rows:
            key = (str(row["segment_stable_id"]), str(row["wav_sha256"]))
            accepted.setdefault(key, set()).add(str(row["warning_code"]))
        return accepted

    def list_machine_acceptances(self) -> list[sqlite3.Row]:
        """Từng lần máy tự cho qua, kèm lý do và mốc thời gian. Dành cho báo cáo."""
        with self.connect() as conn:
            return list(
                conn.execute(
                    "SELECT * FROM machine_audio_acceptances "
                    "ORDER BY segment_stable_id, warning_code"
                )
            )

    def ruled_segment_warnings(self) -> dict[tuple[str, str], set[str]]:
        """Cảnh báo đã có ai đó **phán xử** - người nghe hoặc máy - keyed theo (đoạn, bản thu).

        Đây là hàm mọi **cổng** phải gọi, và `accepted_segment_warnings` là hàm mọi **báo
        cáo** phải gọi. Hai cái tên khác nhau vì hai câu hỏi khác nhau, và trộn chúng là cách
        duy nhất cơ chế này có thể nói dối.

        Có một hàm chung ở đây, thay vì để từng cổng tự union hai bảng, là vì lịch sử: sáu
        cổng đã lần lượt đè lên phán quyết của người nghe - `chapter_is_publishable`,
        `chapter_segments_have_current_audio_qa`, `_listener_ruled_on_this_take`,
        `_repair_chapter_perceptual_candidates`, `_high_quality_blocking_segment_warnings`
        và bản quét recovery - mỗi lần vì một chỗ mới quên hỏi. Cổng thứ bảy gọi hàm này và
        không phải biết có mấy bảng.
        """
        ruled = {
            key: set(codes) for key, codes in self.accepted_segment_warnings().items()
        }
        for key, codes in self.machine_accepted_segment_warnings().items():
            ruled.setdefault(key, set()).update(codes)
        return ruled

    def ruled_segment_takes(self) -> set[tuple[str, str]]:
        """(đoạn, checksum) đã có ai đó phán xử. Dạng tập hợp cho cổng chỉ hỏi có/không."""
        return set(self.ruled_segment_warnings())

'''

s = s.replace(ANCHOR, METHODS + ANCHOR, 1)

OLD_GATE1 = '''            accepted_takes = {
                (str(a), str(b))
                for a, b in conn.execute(
                    "SELECT segment_stable_id, wav_sha256 FROM listener_audio_acceptances"
                )
            }'''
NEW_GATE1 = '''            # Cả hai nguồn phán xử, vì cổng này chỉ hỏi "bản thu đã được ai đó cho đi
            # tiếp chưa", không hỏi ai cho. Chỗ phân biệt nguồn là báo cáo, không phải đây.
            accepted_takes = self._ruled_takes_conn(conn)'''
assert OLD_GATE1 in s, "khong khop cong chapter_is_publishable"
s = s.replace(OLD_GATE1, NEW_GATE1, 1)

OLD_GATE2 = '''            accepted = {
                (str(a), str(b))
                for a, b in conn.execute(
                    "SELECT segment_stable_id, wav_sha256 FROM listener_audio_acceptances"
                )
            }'''
NEW_GATE2 = '''            accepted = self._ruled_takes_conn(conn)'''
assert OLD_GATE2 in s, "khong khop cong chapter_segments_have_current_audio_qa"
s = s.replace(OLD_GATE2, NEW_GATE2, 1)

HELPER_ANCHOR = (
    "    def _refresh_chapter_counts_conn"
    "(self, conn: sqlite3.Connection, chapter_id: int) -> None:"
)
assert HELPER_ANCHOR in s, "khong khop cho chen helper"
HELPER = '''    @staticmethod
    def _ruled_takes_conn(conn: sqlite3.Connection) -> set[tuple[str, str]]:
        """`ruled_segment_takes` nhưng dùng lại connection đang mở của cổng gọi nó."""
        return {
            (str(a), str(b))
            for a, b in conn.execute(
                "SELECT segment_stable_id, wav_sha256 FROM listener_audio_acceptances"
                " UNION "
                "SELECT segment_stable_id, wav_sha256 FROM machine_audio_acceptances"
            )
        }

'''
s = s.replace(HELPER_ANCHOR, HELPER + HELPER_ANCHOR, 1)

io.open(p, "w", encoding="utf-8").write(s)
print(f"da va {p}")
