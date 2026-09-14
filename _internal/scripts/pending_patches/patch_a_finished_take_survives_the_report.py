"""Va database.py: ban-hoan-chinh-thay-ban-bi-cat da THANG phai song qua bo kiem luc xuat bao cao.

Cuon 2, lo 1, 06:55:57 ngay 14-09: chuong 029, doan c00030_s0000057_9bcd4224fd07 ("M... Ma!", 0,64 s).
Duong ong thay ban thu bi cat bang ung vien tu ket thuc - dung luat cua ban va lo 9
(`patch_a_finished_take_is_promoted_without_two_passing_checks.py`): `promote_segment_candidate(...,
over_a_cut_off_incumbent=True)` ghi check cuoi voi `repair_action =
"promote_finished_take_over_cut_off_incumbent"` va mot dong `machine_take_substitutions`. Roi
`refresh_terminal_reports` -> `segment_candidate_attempt_summary` -> `_validated_promoted_candidate_conn`
nem `promoted candidate dual-decode ledger is not passing: final_action_is_not_keep_locked_reading,
failure_codes_outside_the_locked_name_anchor`: bo kiem chi biet MOT dac cach (giu cach doc ghim), khong biet
dac cach thu hai ma chinh ham thang vua cho phep. UNRECOVERABLE_PIPELINE_ERROR, lo chet 30/49, ranh gioi
chay lai hai lan cung chet mot cho, thoat ma 4.

Cung mot bai hoc voi ban va lo 9, o mot tang khac: noi o cho thang ma khong noi o cho kiem. Ba cho goi bo
kiem nay (tong hop bao cao, `reconcile_segment_candidate_artifacts` luc recovery, `segment_candidate_resume_plan`)
deu se nem cung mot loi, nen chi sua bo kiem la du.

Sua: dac cach thu hai, doi dung bang chung ma luot thang de lai - (a) check cuoi mang action
`promote_finished_take_over_cut_off_incumbent`, (b) so phien co ma trượt va TAT CA la ma ASR (dieu kien 4
cua `_require_candidate_beats_a_cut_off_incumbent`, doc lai tu `failure_reason`), (c) co dong
`machine_take_substitutions` cho (doan, wav ung vien). Thieu mot trong ba thi tu choi nhu cu. Hang
`PROMOTE_FINISHED_TAKE_ACTION` dat canh `KEEP_LOCKED_READING_ACTION`; pipeline.py van ghi chuoi chu (test khang
dinh hai chuoi trung nhau).

Chay: python patch_a_finished_take_survives_the_report.py <root>
"""
import io
import sys
from pathlib import Path

root = Path(sys.argv[1])
p = root / "ebook_reader" / "database.py"
s = io.open(p, encoding="utf-8").read()

OLD_CONST = '''KEEP_LOCKED_READING_ACTION = "keep_locked_reading_over_spelling_take"
'''
NEW_CONST = '''KEEP_LOCKED_READING_ACTION = "keep_locked_reading_over_spelling_take"
# Đặc cách thứ hai của một ứng viên đã thăng mà sổ phiên không đạt: bản thu tự kết thúc thay bản
# bị cắt giữa câu (`promote_segment_candidate(..., over_a_cut_off_incumbent=True)`). Hai đường
# phiên trượt là ĐỊNH NGHĨA của ca ấy, nên bộ kiểm không được đòi chúng đạt - cuốn 2 lô 1 chết
# 30/49 vì bộ kiểm lúc xuất báo cáo chỉ biết đặc cách trên. pipeline.py ghi chuỗi này làm
# `repair_action` của check cuối.
PROMOTE_FINISHED_TAKE_ACTION = "promote_finished_take_over_cut_off_incumbent"
'''
assert s.count(OLD_CONST) == 1, "khong khop KEEP_LOCKED_READING_ACTION"
s = s.replace(OLD_CONST, NEW_CONST, 1)

OLD_CHECK = '''            require_all(
                "promoted candidate dual-decode ledger is not passing",
                (
                    "final_action_is_not_keep_locked_reading",
                    final_action is None
                    or str(final_action[0] or "") != KEEP_LOCKED_READING_ACTION,
                ),
                ("no_failure_codes_recorded", not ledger_codes),
                (
                    "failure_codes_outside_the_locked_name_anchor",
                    bool(ledger_codes - LOCKED_NAME_ANCHOR_CODES),
                ),
                candidate_id=int(candidate["id"]),
                failure_codes=sorted(ledger_codes),
            )
'''
NEW_CHECK = '''            action = str(final_action[0] or "") if final_action is not None else ""
            if action == PROMOTE_FINISHED_TAKE_ACTION:
                # Bản tự kết thúc thay bản bị cắt: hai đường phiên trượt là định nghĩa của ca
                # (văn bản dưới ngưỡng ASR phán xử), cùng lý do đã ghi ở `promote_segment_candidate`.
                # Bằng chứng bền của lượt thăng ấy là dòng `machine_take_substitutions` nó ghi
                # trong cùng transaction; không có dòng ấy thì đây không phải ca ấy.
                substitution = conn.execute(
                    "SELECT 1 FROM machine_take_substitutions "
                    "WHERE segment_stable_id=? AND candidate_wav_sha256=?",
                    (str(segment["stable_id"]), str(candidate["wav_sha256"] or "")),
                ).fetchone()
                require_all(
                    "promoted finished take lacks its substitution evidence",
                    ("no_failure_codes_recorded", not ledger_codes),
                    (
                        "failure_codes_outside_asr",
                        _asr_only_failure_codes(str(candidate["failure_reason"] or "")) is None,
                    ),
                    ("no_machine_take_substitution_row", substitution is None),
                    candidate_id=int(candidate["id"]),
                    failure_codes=sorted(ledger_codes),
                )
            else:
                require_all(
                    "promoted candidate dual-decode ledger is not passing",
                    (
                        "final_action_is_not_keep_locked_reading",
                        action != KEEP_LOCKED_READING_ACTION,
                    ),
                    ("no_failure_codes_recorded", not ledger_codes),
                    (
                        "failure_codes_outside_the_locked_name_anchor",
                        bool(ledger_codes - LOCKED_NAME_ANCHOR_CODES),
                    ),
                    candidate_id=int(candidate["id"]),
                    failure_codes=sorted(ledger_codes),
                )
'''
assert s.count(OLD_CHECK) == 1, "khong khop khoi require_all trong _validated_promoted_candidate_conn"
s = s.replace(OLD_CHECK, NEW_CHECK, 1)
io.open(p, "w", encoding="utf-8", newline="\n").write(s)
print(f"da va {p}")

TEST = '''"""A promoted finished take must survive every validator that runs after promotion.

Book 2, batch 1, 06:55 on 2026-09-14: the pipeline replaced a cut-off take with a finished one
exactly as the batch-9 patch allows, and the very next report export killed the run -
`_validated_promoted_candidate_conn` only knew the keep-locked-reading exemption. Same lesson
as batch 9, one layer down: relaxed at the promotion, not at the check.

Fixture: the frozen batch-9 copy (`_fixtures/lo09_223_cut_off`), chapter 223, "Gục đi!" - a real
cut-off incumbent with a real finished candidate. The promotion is the real one; then the three
call sites of the validator are exercised on its result.
"""
from __future__ import annotations

import re
import shutil
import sqlite3
from pathlib import Path

import pytest

from ebook_reader.database import (
    PROMOTE_FINISHED_TAKE_ACTION,
    SEGMENT_CANDIDATE_PROMOTED,
    ProjectDB,
)

FIXTURE = Path("D:/Novels/Audiobooks/_fixtures/lo09_223_cut_off")
SEGMENT_SUFFIX = "5b7f60a11624"  # "Gục đi!"
ROOT = Path(__file__).resolve().parents[1]


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


def _promote_the_real_finished_take(db: ProjectDB) -> tuple[int, str, int]:
    segment = _segment(db)
    policy_hash = str(db.current_quality_policy()["policy_hash"])
    candidate = db.find_finished_take_over_a_cut_off_incumbent(int(segment["id"]), policy_hash)
    assert candidate is not None, "fixture phải còn ứng viên đủ bốn điều kiện"
    if not Path(str(candidate["wav_path"])).is_file():
        pytest.skip("wav của ứng viên không còn trên đĩa (project lô 9 đã bị xoá?)")
    promoted = db.promote_segment_candidate(
        int(candidate["id"]),
        validated_wav_sha256=str(candidate["wav_sha256"]),
        repair_action=PROMOTE_FINISHED_TAKE_ACTION,
        attempt=_next_attempt(db, int(segment["id"])),
        warning_code="ASR_UNVERIFIABLE_SHORT_TEXT",
        over_a_cut_off_incumbent=True,
    )
    assert str(promoted["state"]) == SEGMENT_CANDIDATE_PROMOTED
    return int(segment["id"]), policy_hash, int(candidate["id"])


def test_the_promoted_finished_take_passes_every_validator_after_promotion(tmp_path: Path) -> None:
    db = _copy(tmp_path)
    segment_id, policy_hash, candidate_id = _promote_the_real_finished_take(db)

    # 1. The report export that killed the batch.
    summary = db.segment_candidate_attempt_summary(segment_id, policy_hash)
    assert any(
        int(row["candidate_id"]) == candidate_id and row.get("state") == SEGMENT_CANDIDATE_PROMOTED
        for row in summary
    )
    # 2. Recovery's artifact reconciliation, which validates every promoted candidate.
    db.reconcile_segment_candidate_artifacts(policy_hash)
    # 3. The resume plan, which validates the single promoted candidate before saying "complete".
    plan = db.segment_candidate_resume_plan(segment_id, policy_hash)
    assert plan["action"] == "complete"
    assert plan["candidate_id"] == candidate_id


def test_without_its_substitution_row_the_finished_take_is_refused(tmp_path: Path) -> None:
    """The exemption is bound to the evidence the promotion wrote, not to the action name alone."""
    db = _copy(tmp_path)
    segment_id, policy_hash, _candidate_id = _promote_the_real_finished_take(db)
    with db.transaction() as conn:
        conn.execute(
            "DELETE FROM machine_take_substitutions WHERE segment_stable_id LIKE ?",
            (f"%{SEGMENT_SUFFIX}",),
        )
    with pytest.raises(RuntimeError, match="substitution evidence.*no_machine_take_substitution_row"):
        db.segment_candidate_attempt_summary(segment_id, policy_hash)


def test_the_keep_locked_reading_exemption_is_unchanged(tmp_path: Path) -> None:
    """A promoted candidate with a failing ledger and neither action is still refused."""
    db = _copy(tmp_path)
    segment_id, policy_hash, candidate_id = _promote_the_real_finished_take(db)
    with db.transaction() as conn:
        final_check_id = conn.execute(
            "SELECT final_check_id FROM segment_candidates WHERE id=?", (candidate_id,)
        ).fetchone()[0]
        conn.execute(
            "UPDATE quality_checks SET repair_action='promote_dual_decode_clarity_candidate' WHERE id=?",
            (final_check_id,),
        )
    with pytest.raises(RuntimeError, match="dual-decode ledger is not passing"):
        db.segment_candidate_attempt_summary(segment_id, policy_hash)


def test_the_action_name_is_the_one_the_pipeline_writes() -> None:
    source = (ROOT / "ebook_reader" / "pipeline.py").read_text(encoding="utf-8")
    assert re.search(r'repair_action="' + re.escape(PROMOTE_FINISHED_TAKE_ACTION) + '"', source)
'''
t = root / "tests" / "test_a_finished_take_survives_the_report.py"
io.open(t, "w", encoding="utf-8", newline="\n").write(TEST)
print(f"da tao {t}")
