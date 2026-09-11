r"""Va database.py + pipeline.py: mot doan chi co MOT ban duoc de cu, va moi loi cua duong
"thay ban thu" chi la "thoi khong thay".

CHUA AP luc viet (2026-09-12 01:10) - lo 5 dang chay. Ap o ranh gioi lo 5 -> 6, **sau**
`patch_keep_the_locked_reading` (no va vao doan ma ban va ay them) va sau
`patch_a_number_is_read_in_full`.

Hai vet cua cung mot viec: `patch_keep_the_locked_reading` sua CAS trang thai ung vien, va nho
the duong `over_a_cut_off_incumbent` - co san tu lau, CHUA TUNG chay thanh cong (0 dong
`machine_take_substitutions` tren 47 project lo, do 17:59 ngay 2026-09-11) - tu lo 6 tro di se
chay duoc lan dau. Hai cho ho no mang theo:

1. **Hai ban `promoted` cho mot doan.** `promote_segment_candidate` chi ha ban `promoted` cu khi
   `keeping_the_locked_reading`. Duong cut-off khong ha gi: neu duong nhiem cua doan lai chinh la
   mot ung vien da duoc de cu vong truoc, sau khi thay se co HAI dong `promoted` - va
   `segment_candidate_resume_plan` nem ("segment has more than one promoted candidate") o lan
   doc ke tiep, tuc luc resume hoac luc lap rap chuong. Bon dieu kien cua
   `_require_candidate_beats_a_cut_off_incumbent` khong noi gi ve viec duong nhiem la ai, nen
   khong co gi chan ca ay.

   Sua: viec ha anh em `promoted` mang dung checksum duong nhiem CU tro thanh **vo dieu kien**
   cho moi duong thang hang. Duong thuong khong co anh em nao nhu the -> 0 dong, vo hai. Chi
   duong "giu cach doc ghim" moi DOI dung mot dong (nhu cu). Bat bien phat bieu duoc thanh mot
   cau: *mot doan, nhieu nhat mot ung vien `promoted`*.

2. **Mot ngoai le o day giet ca chuong.** `_promote_a_finished_take_over_a_cut_off_one` goi
   `_segment_candidate_item`, va ham ay **nem that** khi checksum van ban doc troi ("segment
   candidate pronunciation variant or spoken-text checksum drifted" - alpha.47 lam dung the khi
   ghim mot cach doc giua luot chay). Day la mot CAI THIEN o diem can ung vien; moi loi cua no
   phai la "thoi khong thay", khong duoc la "chuong hong". Cung lop boc da chung minh cho
   `_keep_the_locked_reading` (xem docs/KEEP_THE_LOCKED_READING.md).
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

# ============================================================ database.py
p = root / "ebook_reader" / "database.py"
s = io.open(p, encoding="utf-8").read()

OLD = '''            if keeping_the_locked_reading:
                # Hạ anh em đọc-theo-chữ-viết khỏi `promoted`: một đoạn chỉ được có MỘT bản
                # được đề cử, và `_invalidate_candidate_conn` cố ý không hạ bản đã đề cử - nên
                # làm ở đây, có CAS theo checksum cũ, và chỉ khi đương nhiệm đã đổi. Ràng buộc
                # CHECK của bảng đòi `promoted_at IS NULL` khi không còn `promoted`; giữ
                # `final_check_id` để sổ vẫn kể được rằng bản ấy từng qua cổng cuối.
                old_incumbent = str(segment["wav_sha256"] or "")
                incumbent_moved = (
                    old_incumbent.casefold() != str(candidate["incumbent_sha256"] or "").casefold()
                )
                demoted = conn.execute(
                    """
                    UPDATE segment_candidates
                    SET state=?,failure_reason=?,updated_at=?,promoted_at=NULL
                    WHERE segment_id=? AND state=? AND lower(wav_sha256)=lower(?) AND id<>?
                    """,
                    (
                        SEGMENT_CANDIDATE_INVALID,
                        ("superseded: " + str(substitution_reason or ""))[-8000:],
                        now,
                        int(candidate["segment_id"]),
                        SEGMENT_CANDIDATE_PROMOTED,
                        old_incumbent,
                        int(candidate["id"]),
                    ),
                )
                if incumbent_moved and demoted.rowcount != 1:
                    raise RuntimeError(
                        "keeping the locked reading found no promoted spelling take to supersede"
                    )'''
NEW = '''            # MỘT đoạn, nhiều nhất MỘT ứng viên `promoted`. Hạ bản `promoted` đang giữ đúng
            # checksum đương nhiệm CŨ, không điều kiện: `_invalidate_candidate_conn` cố ý không
            # hạ bản đã đề cử, và `segment_candidate_resume_plan` nem khi thấy hai bản - tức
            # lỗi nổ ở lần ĐỌC sau, xa chỗ gây ra nó. Đường thường không có anh em như thế nên
            # câu lệnh khớp 0 dòng và vô hại; đường "giữ cách đọc ghim" đòi đúng một dòng (điều
            # kiện 5 của nó đã kiểm rằng anh em ấy tồn tại); đường "bản hoàn chỉnh thắng bản bị
            # cắt" - chạy được lần đầu từ lô 6 - hạ anh em nếu đương nhiệm của nó tình cờ cũng
            # là một ứng viên đã đề cử. Ràng buộc CHECK của bảng đòi `promoted_at IS NULL` khi
            # không còn `promoted`; giữ `final_check_id` để sổ vẫn kể được bản ấy từng qua cổng
            # cuối.
            old_incumbent = str(segment["wav_sha256"] or "")
            incumbent_moved = (
                old_incumbent.casefold() != str(candidate["incumbent_sha256"] or "").casefold()
            )
            demoted = conn.execute(
                """
                UPDATE segment_candidates
                SET state=?,failure_reason=?,updated_at=?,promoted_at=NULL
                WHERE segment_id=? AND state=? AND lower(wav_sha256)=lower(?) AND id<>?
                """,
                (
                    SEGMENT_CANDIDATE_INVALID,
                    (
                        "superseded: "
                        + str(
                            substitution_reason
                            or "another candidate was promoted for this segment"
                        )
                    )[-8000:],
                    now,
                    int(candidate["segment_id"]),
                    SEGMENT_CANDIDATE_PROMOTED,
                    old_incumbent,
                    int(candidate["id"]),
                ),
            )
            # Hai `if` lồng nhau chứ không phải một `if` ba mệnh đề: `test_no_new_blind_compound_
            # check_is_added` đếm đúng hình dạng ấy và không cho tăng, vì một lời từ chối gộp ba
            # điều kiện sau một thông điệp thì không nói được mệnh đề nào vỡ. `require_all` không
            # dùng được ở đây - nó ném khi MỘT mệnh đề đúng, còn chỗ này chỉ ném khi CẢ BA đúng.
            if keeping_the_locked_reading and incumbent_moved:
                if demoted.rowcount != 1:
                    raise RuntimeError(
                        "keeping the locked reading found no promoted spelling take to supersede"
                    )'''
assert s.count(OLD) == 1, "khong khop khoi ha anh em (can patch_keep_the_locked_reading truoc)"
s = s.replace(OLD, NEW, 1)

write_atomic(p, s)
print("da va", p)

# ============================================================ pipeline.py
p = root / "ebook_reader" / "pipeline.py"
t = io.open(p, encoding="utf-8").read()

OLD = '''    def _promote_a_finished_take_over_a_cut_off_one(
        self,
        item: Any,
        segment_id: int,
        chapter_title: str,
    ) -> bool:
        """Thay một bản thu bị cắt giữa câu bằng một ứng viên đã nói xong. True nếu thay.
'''
NEW = '''    def _promote_a_finished_take_over_a_cut_off_one(
        self,
        item: Any,
        segment_id: int,
        chapter_title: str,
    ) -> bool:
        """Thay nếu được, và **không bao giờ** làm hỏng chương nếu không được.

        Đây là một CẢI THIỆN ở điểm cạn ứng viên: nếu nó không làm được việc của nó thì đường
        ống phải chốt lại đoạn này y như trước khi có nó. `_segment_candidate_item` ném thật khi
        checksum văn bản đọc trôi (alpha.47: ghim một cách đọc giữa lượt chạy), và một ngoại lệ
        thoát ra từ đây giết chương đang phiên - đổi một bản thu cứu được lấy cả một chương.

        Đường này chạy được lần đầu từ lô 6 (CAS trạng thái ứng viên vừa được sửa trong
        `patch_keep_the_locked_reading`), nên lớp bọc này không phải đề phòng lý thuyết: trước
        đó mọi lần gọi đều chết ở CAS và cuộn lại, sau đó thì không.
        """
        try:
            return self._promote_a_finished_take_if_it_wins(item, segment_id, chapter_title)
        except Exception as exc:  # noqa: BLE001 - xem docstring
            self.log(
                f"Segment {item['stable_id']}: không thay được bản thu bị cắt - {exc}"
            )
            return False

    def _promote_a_finished_take_if_it_wins(
        self,
        item: Any,
        segment_id: int,
        chapter_title: str,
    ) -> bool:
        """Thay một bản thu bị cắt giữa câu bằng một ứng viên đã nói xong. True nếu thay.
'''
assert t.count(OLD) == 1, "khong khop chu ky _promote_a_finished_take_over_a_cut_off_one"
t = t.replace(OLD, NEW, 1)

write_atomic(p, t)
print("da va", p)

# ============================================================ tests
TEST = '''"""Một đoạn chỉ có MỘT bản được đề cử, và mọi lỗi của đường "thay bản thu" chỉ là "thôi không thay".

`patch_keep_the_locked_reading` sửa CAS trạng thái ứng viên, và nhờ thế đường
`over_a_cut_off_incumbent` - có sẵn từ lâu, chưa từng chạy thành công (0 dòng
`machine_take_substitutions` trên 47 project lô) - chạy được lần đầu từ lô 6. Hai chỗ hở nó mang
theo được vá ở đây: hai bản `promoted` cho một đoạn, và một ngoại lệ giết cả chương.
"""
from __future__ import annotations

import shutil
import sqlite3
import sys
from pathlib import Path

import pytest

from ebook_reader.cli import _open_project
from ebook_reader.database import (
    KEEP_LOCKED_READING_ACTION,
    SEGMENT_CANDIDATE_PROMOTED,
    ProjectDB,
)

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

REAL = Path("D:/Novels/Audiobooks/_versions/v0.2.0-lo03r/lo03r_084b_9455372a18")
LOST_LINE_SUFFIX = "feeb9dd9dda2"


def _copy(tmp_path: Path) -> Path:
    if not (REAL / "project.sqlite3").is_file() or not (REAL / "book_settings.json").is_file():
        pytest.skip(f"không có project thật {REAL.name} trên máy này")
    shutil.copyfile(REAL / "project.sqlite3", tmp_path / "project.sqlite3")
    shutil.copyfile(REAL / "book_settings.json", tmp_path / "book_settings.json")
    return tmp_path


def _promoted_per_segment(db: ProjectDB) -> dict[int, int]:
    with db.connect() as conn:
        return {
            int(row["segment_id"]): int(row["n"])
            for row in conn.execute(
                "SELECT segment_id, count(*) AS n FROM segment_candidates "
                "WHERE state=? GROUP BY segment_id",
                (SEGMENT_CANDIDATE_PROMOTED,),
            )
        }


def test_no_segment_ends_up_with_two_promoted_candidates(tmp_path: Path) -> None:
    """Bất biến phát biểu thành một câu, và kiểm trên cả project sau khi đề cử lại thật."""
    root = _copy(tmp_path)
    db = ProjectDB(root / "project.sqlite3")
    before = _promoted_per_segment(db)
    assert before and max(before.values()) == 1, "project thật phải đang thoả bất biến"

    with db.connect() as conn:
        segment = conn.execute(
            "SELECT * FROM segments WHERE stable_id LIKE ?", (f"%{LOST_LINE_SUFFIX}",)
        ).fetchone()
        attempt = int(
            conn.execute(
                "SELECT coalesce(max(attempt), 0) FROM quality_checks WHERE segment_id=?",
                (int(segment["id"]),),
            ).fetchone()[0]
        ) + 1
    candidate = db.find_locked_reading_that_lost_only_the_spelling_test(
        int(segment["id"]), str(segment["generation_policy_hash"])
    )
    assert candidate is not None

    db.promote_segment_candidate(
        int(candidate["id"]),
        validated_wav_sha256=str(candidate["wav_sha256"]),
        repair_action=KEEP_LOCKED_READING_ACTION,
        attempt=attempt,
        warning_code="ASR_LOCKED_NAME_ANCHOR_MISMATCH",
        keeping_the_locked_reading=True,
    )

    after = _promoted_per_segment(db)
    assert max(after.values()) == 1, "một đoạn, nhiều nhất một bản được đề cử"
    assert after[int(segment["id"])] == 1
    # Và kế hoạch tiếp tục dựng được cho mọi đoạn có bản được đề cử (nó ném khi thấy hai bản).
    for segment_id in after:
        with db.connect() as conn:
            policy_hash = str(
                conn.execute(
                    "SELECT generation_policy_hash FROM segments WHERE id=?", (segment_id,)
                ).fetchone()[0]
            )
        db.segment_candidate_resume_plan(segment_id, policy_hash)


def test_the_cut_off_substitution_swallows_its_own_failures(tmp_path: Path) -> None:
    """Lớp bọc: một ngoại lệ ở đây phải thành "thôi không thay", không phải "chương hỏng"."""
    from scripts.keep_the_locked_reading import bare_pipeline

    root = _copy(tmp_path)
    paths, db, settings = _open_project(root)
    pipeline = bare_pipeline(paths, db, settings)
    with db.connect() as conn:
        segment = conn.execute(
            "SELECT * FROM segments WHERE stable_id LIKE ?", (f"%{LOST_LINE_SUFFIX}",)
        ).fetchone()

    def boom(*_args, **_kwargs):
        raise RuntimeError("segment candidate pronunciation variant or spoken-text checksum drifted")

    db.find_finished_take_over_a_cut_off_incumbent = boom

    assert (
        pipeline._promote_a_finished_take_over_a_cut_off_one(
            dict(segment), int(segment["id"]), "084"
        )
        is False
    )
    assert str(db.get_segment(int(segment["id"]))["wav_sha256"]) == str(segment["wav_sha256"])
'''
write_atomic(root / "tests" / "test_one_promoted_take_and_one_way_to_fail.py", TEST)
print("da tao", root / "tests" / "test_one_promoted_take_and_one_way_to_fail.py")
