"""Va pipeline.py: may tu cho qua khi khong con ai de hoi, va ba cong con lai hoi ca hai nguon."""
import io
import sys
from pathlib import Path

root = Path(sys.argv[1])
p = root / "ebook_reader" / "pipeline.py"
s = io.open(p, encoding="utf-8").read()

# ---------------------------------------------------------------- hằng số
ANCHOR_CONST = 'CHAPTER_REVIEW_STATUS = "warning"'
assert ANCHOR_CONST in s, "khong khop cho chen hang so"

CONST = '''MACHINE_ACCEPTABLE_SEGMENT_WARNINGS = frozenset(
    {
        "ASR_MISMATCH_UNRESOLVED",
        ASR_LOCKED_NAME_ANCHOR_MISMATCH,
        ASR_LOCKED_NAME_ANCHOR_REVIEW,
        ASR_UNVERIFIABLE_SHORT_TEXT,
        ASR_TRANSCRIPT_TIMELINE_IMPOSSIBLE,
    }
)
"""Mã cảnh báo mà **chỉ ASR** kêu, nên máy được phép tự cho qua khi hết cách hỏi.

Danh sách này toàn `ASR_*`, và đó là toàn bộ lý lẽ. Đo trên tám đoạn chặn của alpha.60:
sáu đoạn không mang **một tín hiệu nào** từ bộ sinh nói bản thu hỏng - chỉ ASR không đọc
được, và đọc kỹ thì thấy vì sao nó không đọc được:

    "Gia tộc Remis,"              -> "Gia tộc dây mít"      (sim 0,94; d/r lẫn nhau)
    "Golem Silian"                -> "go lem xí lên"        (sim 0,89; s/x đồng âm)
    "Selene Valkryn"              -> "Selenva L. Green"     (tên bịa, Whisper đánh vần Latin)
    "Kalbi kathub 'ala ramal."    -> "cao bê coa thúc..."   (tiếng Ả Rập chuyển tự)

Không phép kiểm nào khác phàn nàn về bốn bản thu ấy. Chúng là lỗi **phiên âm**, không phải
lỗi **đọc**, và năm vòng thu lại không đổi được gì vì chẳng có gì để đổi.

Cố ý **không** có ở đây: `PERCEPTUAL_NATURALNESS_REVIEW` (một máy chấm khác, độc lập với
ASR), `TTS_PACE_OUTLIER` (đo trên chính sóng âm), `SEGMENT_FAILED` (không có bản thu để
ship), và `TTS_GENERATION_CEILING_REACHED` (bộ sinh tự khai nó chạy hết khung). Nguyên tắc:
**máy chỉ được đè lên ASR khi ASR là nhân chứng duy nhất.**
"""
'''

s = s.replace(ANCHOR_CONST, CONST + ANCHOR_CONST, 1)

# ---------------------------------------------------------------- cổng 3: mã chặn
OLD = """        accepted = self.db.accepted_segment_warnings()
        for row in rows:
            warning_codes = {"""
NEW = """        # `ruled_`, không phải `accepted_`: cổng hỏi "đã có ai phán xử bản thu này chưa",
        # và câu trả lời gồm cả người nghe lẫn máy. Phân biệt nguồn là việc của báo cáo.
        accepted = self.db.ruled_segment_warnings()
        for row in rows:
            warning_codes = {"""
assert OLD in s, "khong khop cong _high_quality_blocking_segment_warnings"
s = s.replace(OLD, NEW, 1)

# ---------------------------------------------------------------- cổng 1: quét resume
OLD = """        accepted = self.db.accepted_segment_warnings()
        return bool(accepted.get((str(row["stable_id"]), artifact_sha256)))"""
NEW = """        accepted = self.db.ruled_segment_warnings()
        return bool(accepted.get((str(row["stable_id"]), artifact_sha256)))"""
assert OLD in s, "khong khop _listener_ruled_on_this_take"
s = s.replace(OLD, NEW, 1)

# ---------------------------------------------------------------- cổng 2: perceptual
OLD = """        accepted_takes = set(self.db.accepted_segment_warnings())"""
NEW = """        accepted_takes = self.db.ruled_segment_takes()"""
assert OLD in s, "khong khop tien dieu kien perceptual"
s = s.replace(OLD, NEW, 1)

# ---------------------------------------------------------------- cấp phép
GRANT = '''    def _grant_machine_acceptances(self, chapter: Any) -> list[dict[str, Any]]:
        """Cho những đoạn mà **chỉ ASR** phàn nàn đi tiếp, vì không còn ai để hỏi.

        Chủ sách ra lệnh 2026-09-07: *"tôi không muốn phải tự nghe, project phải hoạt động
        toàn bộ cho ra sản phẩm"*. Trước lệnh ấy, một đoạn mà ASR không đọc nổi sẽ chặn
        chương của nó **vĩnh viễn**: vòng sửa đã cạn, cảnh báo không ai gỡ được, và cái duy
        nhất còn mở là `accept` - đòi một người ngồi nghe. Đó là bức tường, không phải cái
        cổng.

        Ba ràng buộc, và chúng là phần đáng giá hơn cả cơ chế:

        1. **Chỉ khi ASR là nhân chứng duy nhất.** Xem
           `MACHINE_ACCEPTABLE_SEGMENT_WARNINGS`. Thêm một lớp nữa ở đây: nếu bộ sinh tự
           khai chạm trần khung thì từ chối, kể cả khi mã cảnh báo không nói ra điều đó -
           `generation_ceiling_hit` là lời khai về BẢN THU, độc lập với ASR.

           Đã thử một tiêu chí thứ ba và **bỏ** vì đo thấy sai: nhịp đọc. Ý tưởng là
           `"Tiếp theo."` dài 1,92 giây tức 4,7 ký tự/giây, quá chậm, nên chắc chạy loạn.
           Nhưng đo trên 205 đoạn ngắn `verified` của alpha.60 thì `"Tiếp theo!"` sạch nằm ở
           4,76 ký tự/giây, p5 của cả nhóm là 4,76, và thấp nhất là 1,56 (`"À!"`, 0,64s).
           Hai phân bố chồng lên nhau hoàn toàn. Một ngưỡng ở đấy chỉ là con số tôi bịa.

        2. **Chỉ sau khi hết ngân sách sửa.** Bảo đảm bằng vị trí gọi: hàm này chạy sau
           `_verify_chapter_audio` và sau `_repair_chapter_perceptual_candidates`, tức là
           sau khi mọi đường thu lại đã đi hết. Cấp phép sớm hơn là bỏ qua những vòng còn
           cứu được - đo được là vòng 2 trở đi cứu 106/641 đoạn (16,5%).

        3. **Không im lặng.** Mỗi lần cấp ghi một dòng log, một `db.event`, và một hàng có
           lý do lẫn mốc thời gian trong `machine_audio_acceptances`. Bản thu **giữ nguyên**
           trạng thái `failed` và mã cảnh báo - máy không đổi ý điều gì, y như khi một người
           nghe đè lên nó.
        """
        if not self.settings.get("asr", {}).get("ship_without_a_listener", True):
            return []
        if self.settings.get("quality_profile") != "high_quality":
            return []
        chapter_id = int(chapter["id"])
        granted: list[dict[str, Any]] = []
        already = self.db.ruled_segment_warnings()
        for row in self.db.list_segments(chapter_id=chapter_id):
            checksum = str(row["wav_sha256"] or "").strip()
            if not checksum:
                # Không có bản thu thì không có gì để ship. Cho qua ở đây là xuất bản một
                # chương thiếu hẳn một câu, và mất chữ thì không phép kiểm nào bắt lại được.
                continue
            codes = {
                value for value in str(row["warning_code"] or "").split("|") if value
            }
            outstanding = codes - already.get((str(row["stable_id"]), checksum), set())
            if not outstanding:
                continue
            if str(row["status"]) not in {
                SegmentStatus.FAILED.value,
                SegmentStatus.WARNING.value,
            }:
                continue
            # Chỉ cấp cho đoạn **thật sự đang chặn**. Bỏ qua câu này thì cơ chế chạy đúng
            # nhưng báo cáo hoá thành kêu sói giả: chạy thử trên alpha.60 nó cấp 13 lượt,
            # trong đó 7 là đoạn `warning` mang mã nằm sẵn trong
            # HIGH_QUALITY_ALLOWED_SEGMENT_WARNINGS - tức là những đoạn vẫn xuất bản bình
            # thường từ trước. Chương 007 và 009 đang qua được mọi cổng sẽ bỗng mang nhãn
            # "3 đoạn chưa ai nghe", và một con số kêu ở chỗ không có gì sai thì lần sau
            # chẳng ai đọc nó nữa. Còn 6 lượt sau khi thêm câu này, đúng 6 đoạn chặn thật.
            blocks_its_chapter = (
                str(row["status"]) == SegmentStatus.FAILED.value
                or bool(outstanding - HIGH_QUALITY_ALLOWED_SEGMENT_WARNINGS)
            )
            if not blocks_its_chapter:
                continue
            if not outstanding <= MACHINE_ACCEPTABLE_SEGMENT_WARNINGS:
                continue
            if self._segment_generation_hit_ceiling(row):
                self.log(
                    f"Segment {row['stable_id']}: không tự cho qua - bộ sinh khai chạm "
                    "trần khung, tức có nhân chứng ngoài ASR nói bản thu hỏng."
                )
                continue
            reason = (
                "ASR là nhân chứng duy nhất; vòng sửa đã cạn; bộ sinh không báo lỗi nào. "
                f"nghe ra: {str(row['asr_text'] or '')[:160]!r}"
            )
            for code in sorted(outstanding):
                self.db.accept_segment_audio_as_machine(
                    segment_stable_id=str(row["stable_id"]),
                    wav_sha256=checksum,
                    warning_code=code,
                    reason=reason,
                )
            granted.append(
                {
                    "stable_id": str(row["stable_id"]),
                    "wav_sha256": checksum,
                    "warning_codes": sorted(outstanding),
                    "text": str(row["text"] or "")[:200],
                    "asr_text": str(row["asr_text"] or "")[:200],
                }
            )
            self.log(
                f"Máy tự cho qua {row['stable_id']} ({','.join(sorted(outstanding))}): "
                "chưa ai nghe bản thu này."
            )
            self.db.event(
                "warning",
                "MACHINE_ACCEPTED_WITHOUT_LISTENER",
                f"{row['stable_id']} {','.join(sorted(outstanding))}",
                {
                    "chapter_id": chapter_id,
                    "chapter_index": int(chapter["chapter_index"]),
                    "wav_sha256": checksum,
                    "text": str(row["text"] or "")[:200],
                    "asr_text": str(row["asr_text"] or "")[:200],
                },
            )
        return granted

'''

GRANT_ANCHOR = "    def _record_chapter_quality_failure(self, chapter: Any, error: AudioQualityError) -> None:"
assert GRANT_ANCHOR in s, "khong khop cho chen _grant_machine_acceptances"
s = s.replace(GRANT_ANCHOR, GRANT + GRANT_ANCHOR, 1)

# ---------------------------------------------------------------- gọi, ngay trước cổng chặn
OLD = """        rows = self.db.list_segments(chapter_id=chapter_id)
        blocking_warnings = self._high_quality_blocking_segment_warnings(rows)"""
NEW = """        # Sau mọi đường thu lại, trước mọi cổng chặn: đây là chỗ duy nhất "hết ngân sách
        # sửa" là đúng theo cấu trúc chứ không phải theo một biến đếm ai đó phải nhớ tăng.
        self._grant_machine_acceptances(chapter)

        rows = self.db.list_segments(chapter_id=chapter_id)
        blocking_warnings = self._high_quality_blocking_segment_warnings(rows)"""
assert OLD in s, "khong khop cho goi _grant_machine_acceptances"
s = s.replace(OLD, NEW, 1)

io.open(p, "w", encoding="utf-8").write(s)
print(f"da va {p}")
