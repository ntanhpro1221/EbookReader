"""Va database.py: ca "ban hoan chinh thay ban bi cat" khong duoc doi hai duong phien ASR deu qua.

Lo 9, chuong 223, doan c00002_s0000033_5b7f60a11624 ("Guc di!"), 2026-09-13 14:0x:

    duong nhiem   1,92 s   generation_ceiling_hit = 1   (bi cat giua cau)
    ung vien #11  0,64 s   vong 0, tu ket thuc, dual_failed (ASR nghe ra "Di. Assalamualaikum.")
    finder        chon #11 - bon dieu kien du
    promote       TU CHOI: "candidate dual-decode ledger does not contain two passing checks"
    ket qua       chuong 223 hong, khong len sach

`promote_segment_candidate(..., over_a_cut_off_incumbent=True)` noi TAP TRANG THAI (them
dual_failed) sau khi kiem lai bon dieu kien, nhung chot "hai duong phien deu PASS" o duoi chi
noi cho `keeping_the_locked_reading`. Ma hai duong phien trot chinh la DINH NGHIA cua ca nay:
van ban ngan hon nguong ASR phan xu duoc, nen ASR khong co y kien - do la dieu kien 3 cua
`_require_candidate_beats_a_cut_off_incumbent`, da duoc kiem lai ngay trong cung ham. Mot chot
doi bang chung ma dieu kien vao da noi la khong the co.

Test cu (`test_finished_take_beats_a_cut_off_one.py`) kiem bon dieu kien va finder bang row
gia, chua bao gio goi promote that voi co ay - nen mau thuan song qua ca bo test xanh, tu lo 5
toi lo 9. Test moi goi promote that tren fixture dong bang tu chinh lo 9.

Sua: chot ay noi cho ca hai co; phan kiem lai "ma trot chi la neo ten" van chi thuoc ca
giu-cach-doc-ghim. Moi chot toan ven khac (checksum, voice profile, provenance, cam thu) khong doi.
"""
import io
import sys
from pathlib import Path

root = Path(sys.argv[1])
p = root / "ebook_reader" / "database.py"
s = io.open(p, encoding="utf-8").read()

OLD = '''                if not keeping_the_locked_reading:
                    raise RuntimeError("candidate dual-decode ledger does not contain two passing checks")
                # Kiểm lại ngay tại chỗ nới, từ chính hai dòng check: mã trượt chỉ được là neo tên.
                ledger_codes = (
                    self._check_failure_codes_conn(conn, candidate["beam_check_id"]) or set()
                ) | (self._check_failure_codes_conn(conn, candidate["greedy_check_id"]) or set())
                if not ledger_codes or ledger_codes - LOCKED_NAME_ANCHOR_CODES:
                    raise RuntimeError(
                        "candidate dual-decode ledger fails on more than the locked-name spelling test"
                    )
'''
NEW = '''                if not keeping_the_locked_reading and not over_a_cut_off_incumbent:
                    raise RuntimeError("candidate dual-decode ledger does not contain two passing checks")
                if keeping_the_locked_reading:
                    # Kiểm lại ngay tại chỗ nới, từ chính hai dòng check: mã trượt chỉ được là
                    # neo tên.
                    ledger_codes = (
                        self._check_failure_codes_conn(conn, candidate["beam_check_id"]) or set()
                    ) | (self._check_failure_codes_conn(conn, candidate["greedy_check_id"]) or set())
                    if not ledger_codes or ledger_codes - LOCKED_NAME_ANCHOR_CODES:
                        raise RuntimeError(
                            "candidate dual-decode ledger fails on more than the locked-name spelling test"
                        )
                # `over_a_cut_off_incumbent`: hai đường phiên trượt là ĐỊNH NGHĨA của ca này -
                # văn bản ngắn hơn ngưỡng ASR phán xử được, nên ASR không có ý kiến - và đó là
                # điều kiện 3 của `_require_candidate_beats_a_cut_off_incumbent`, vừa kiểm lại ở
                # trên trong cùng hàm. Đòi hai check PASS ở đây là đòi bằng chứng mà điều kiện
                # vào đã nói là không thể có. Lô 9 chương 223, "Gục đi!": finder chọn ứng viên
                # #11 (0,64 s tự kết thúc), chốt này từ chối, chương hỏng - ca thật đầu tiên,
                # sống qua bộ test xanh vì test chỉ kiểm bốn điều kiện bằng row giả.
'''
assert s.count(OLD) == 1, "khong khop chot 'two passing checks'"
s = s.replace(OLD, NEW, 1)
io.open(p, "w", encoding="utf-8", newline="\n").write(s)
print(f"da va {p}")

TEST = '''"""Bản thu tự kết thúc thay bản bị cắt: đề cử THẬT phải qua, không chỉ bốn điều kiện.

Fixture: bản sao đóng băng của lô 9 (`D:/Novels/Audiobooks/_fixtures/lo09_223_cut_off`), chương
223, đoạn "Gục đi!": đương nhiệm 1,92 s chạm trần, ứng viên #11 0,64 s tự kết thúc, hai đường
phiên ASR đều trượt vì văn bản dưới ngưỡng phán xử. Finder đã chọn #11 từ trước bản vá; cái hỏng
là chốt "hai đường phiên đều qua" trong `promote_segment_candidate`, và chỉ đề cử thật mới chạm
tới nó.
"""
from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path

import pytest

from ebook_reader.database import SEGMENT_CANDIDATE_PROMOTED, ProjectDB

FIXTURE = Path("D:/Novels/Audiobooks/_fixtures/lo09_223_cut_off")
SEGMENT_SUFFIX = "5b7f60a11624"  # "Gục đi!"


def _copy(tmp_path: Path) -> ProjectDB:
    if not (FIXTURE / "project.sqlite3").is_file():
        pytest.skip(f"không có fixture {FIXTURE.name} trên máy này")
    shutil.copyfile(FIXTURE / "project.sqlite3", tmp_path / "project.sqlite3")
    if (FIXTURE / "book_settings.json").is_file():
        shutil.copyfile(FIXTURE / "book_settings.json", tmp_path / "book_settings.json")
    return ProjectDB(tmp_path / "project.sqlite3")


def _segment(db: ProjectDB) -> sqlite3.Row:
    with db.connect() as conn:
        row = conn.execute(
            "SELECT * FROM segments WHERE stable_id LIKE ?", (f"%{SEGMENT_SUFFIX}",)
        ).fetchone()
    assert row is not None
    return row


def _next_attempt(db: ProjectDB, segment_id: int) -> int:
    with db.connect() as conn:
        row = conn.execute(
            "SELECT coalesce(max(attempt), 0) FROM quality_checks WHERE segment_id=?",
            (segment_id,),
        ).fetchone()
    return int(row[0]) + 1


def _eligible_candidate(db: ProjectDB, segment: sqlite3.Row) -> sqlite3.Row:
    policy_hash = str(db.current_quality_policy()["policy_hash"])
    candidate = db.find_finished_take_over_a_cut_off_incumbent(int(segment["id"]), policy_hash)
    assert candidate is not None, "fixture phải còn ứng viên đủ bốn điều kiện"
    if not Path(str(candidate["wav_path"])).is_file():
        pytest.skip("wav của ứng viên không còn trên đĩa (project lô 9 đã bị xoá?)")
    return candidate


def test_the_real_cut_off_case_is_promoted(tmp_path: Path) -> None:
    db = _copy(tmp_path)
    segment = _segment(db)
    candidate = _eligible_candidate(db, segment)

    promoted = db.promote_segment_candidate(
        int(candidate["id"]),
        validated_wav_sha256=str(candidate["wav_sha256"]),
        repair_action="promote_finished_take_over_cut_off_incumbent",
        attempt=_next_attempt(db, int(segment["id"])),
        warning_code="ASR_UNVERIFIABLE_SHORT_TEXT",
        over_a_cut_off_incumbent=True,
    )

    assert str(promoted["state"]) == SEGMENT_CANDIDATE_PROMOTED
    after = _segment(db)
    assert str(after["wav_sha256"]).casefold() == str(candidate["wav_sha256"]).casefold()


def test_without_the_flag_two_failed_decodes_still_refuse(tmp_path: Path) -> None:
    """Chốt không bị tháo: đề cử thường vẫn đòi hai đường phiên đều qua."""
    db = _copy(tmp_path)
    segment = _segment(db)
    candidate = _eligible_candidate(db, segment)

    # Không có cờ, cửa đóng ngay ở tập trạng thái (dual_failed không đề cử được) - trước cả chốt
    # "two passing checks". Cả hai thông điệp đều là "từ chối"; bài này khẳng định cửa đóng.
    with pytest.raises(RuntimeError, match="two passing checks|before both ASR decodes pass"):
        db.promote_segment_candidate(
            int(candidate["id"]),
            validated_wav_sha256=str(candidate["wav_sha256"]),
            repair_action="promote_dual_decode_clarity_candidate",
            attempt=_next_attempt(db, int(segment["id"])),
            warning_code=None,
        )
'''
t = root / "tests" / "test_a_finished_take_is_promoted_without_two_passing_checks.py"
io.open(t, "w", encoding="utf-8", newline="\n").write(TEST)
print(f"da tao {t}")
