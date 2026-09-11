r"""Va database.py + pipeline.py: giu cach doc GHIM khi chi bai chinh ta neo ten phan nan.

CHUA AP luc viet - lo 5 dang chay. Ap o ranh gioi lo 5 -> 6. Dac ta day du trong
docs/OPTIMISATION_QUEUE.md ("Dac ta ban va: giu cach doc ghim ..."); tom tat:

Do 2026-09-11 tren cuon sach 92 chuong da ghep:

    716 ung vien duoc de cu (doan da qua vong sua)
    348 (48%) la `source_spelling_v1` - doc ten theo CHU VIET thay vi cach doc ghim
        Jake 79 · Michael 35 · Spirit 31 · Will 20 · Apex 19 · Willem 16 · Alice 13
    348 / 348 ban doc-ghim anh em: ca hai duong phien `fail` voi DUY NHAT mot ma
        ASR_LOCKED_NAME_ANCHOR_MISMATCH; nhip qua; WAV con nguyen tren dia

Co che, doc tu chuong 084 duc lai: ban doc-ghim (`I-xo-ho-ta-ra`) qua cong nhip, chet o cong neo
ten tren ca beam lan greedy; vong sua "ro tieng" sinh ung vien doc theo chu viet (`Ishtara`),
Whisper nghe duoc, ung vien ay duoc de cu. Chuong len sach voi thanh pho doc khac moi chuong
kia. Nguoi nghe nghe `Giech` o doan nay va `Jake` o doan ke, tuy Whisper truot o dau.

Vi sao duong chap nhan hien co khong cuu duoc: `_grant_machine_acceptances` chay o CUOI chuong,
sau vong sua (rang buoc so 2 cua no). Dung cho tran khung; sai cho neo ten, vi "cuu" bang cach
doi cach doc la doi thu nguoi nghe nghe. Hoc thuyet cua du an da coi
ASR_LOCKED_NAME_ANCHOR_MISMATCH la ma may chap nhan co ghi so o tang doan; ban va nay dua no
xuong tang ung vien, TRUOC khi vong sua thay cach doc.

Hai nua:

  database.py  - `find_locked_reading_that_lost_only_the_spelling_test(segment_id, policy_hash)`
                 khong nem; `promote_segment_candidate(..., keeping_the_locked_reading=True)`
                 noi dung BA bat bien (tap trang thai duoc de cu; hai check ASR phai PASS;
                 checksum duong nhiem) sau khi NAM dieu kien duoc kiem tu chinh du lieu bang
                 `require_all`. Moi chot chan toan ven khac giu nguyen, trong cung ham.
  pipeline.py  - `_keep_the_locked_reading(item)`: duong ong chi DE NGHI; goi o vong sua ASR
                 truoc khi cap phat ung vien vong le (vong ma bien the chu viet duoc yeu cau).
                 Ghi phan quyet may cho tung ma neo ten, ly do noi ro.

Luot de cu lai 348 doan da len sach di rieng: `scripts/keep_the_locked_reading.py` (viet sau khi
duong database nay da chung minh tren ban sao cua lo03r_084b).
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

# ---- hang so
OLD = 'PRONUNCIATION_DELIVERY_SOURCE = "source_spelling_v1"\n'
NEW = '''PRONUNCIATION_DELIVERY_SOURCE = "source_spelling_v1"
# Họ mã của **bài chính tả neo tên**: Whisper viết một cách đọc chuyển tự thành gì, so với chữ
# viết. Chúng nói về phiên bản, không nói bản thu hỏng - và cách đọc ghim không bao giờ đậu bài
# này (đo 2026-09-11: 348/348 bản đọc-ghim thua chỉ vì mã đầu tiên). Xem
# docs/LOCKED_NAME_ANCHOR_IS_A_SPELLING_TEST.md.
LOCKED_NAME_ANCHOR_CODES = frozenset(
    {"ASR_LOCKED_NAME_ANCHOR_MISMATCH", "ASR_LOCKED_NAME_ANCHOR_REVIEW"}
)
KEEP_LOCKED_READING_ACTION = "keep_locked_reading_over_spelling_take"
'''
assert OLD in s and "LOCKED_NAME_ANCHOR_CODES" not in s, "khong khop hang so"
s = s.replace(OLD, NEW, 1)

# ---- hai method moi, ngay tren find_finished_take_over_a_cut_off_incumbent
OLD = "    def find_finished_take_over_a_cut_off_incumbent(\n"
NEW = '''    def _check_failure_codes_conn(
        self,
        conn: sqlite3.Connection,
        quality_check_id: Any,
    ) -> set[str] | None:
        """Mã trượt của một check ASR, hoặc None nếu không có check / không đọc được."""
        if quality_check_id is None:
            return None
        row = conn.execute(
            "SELECT verdict, failure_codes_json FROM quality_checks WHERE id=?",
            (int(quality_check_id),),
        ).fetchone()
        if row is None:
            return None
        try:
            codes = json.loads(row["failure_codes_json"] or "[]")
        except ValueError:
            return None
        if not isinstance(codes, list):
            return None
        if str(row["verdict"]) == QUALITY_VERDICT_PASS and not codes:
            return set()
        return {str(code) for code in codes}

    def _require_locked_reading_lost_only_the_spelling_test(
        self,
        conn: sqlite3.Connection,
        candidate: sqlite3.Row,
        segment: sqlite3.Row,
    ) -> str:
        """Năm điều kiện phải đúng cùng lúc mới được đề cử một bản đọc-ghim đã trượt ASR.

        Kiểm ở tầng này, từ **chính các dòng dữ liệu**, không từ lời khai người gọi - cùng
        lý do với `_require_candidate_beats_a_cut_off_incumbent`.

        1. Ứng viên đọc theo **cách đọc ghim** (`locked_spoken_v1`). Bản đọc theo chữ viết không
           có gì để "giữ".
        2. Cả hai đường phiên đều có check, và mọi mã trượt của cả hai ⊆ họ neo tên. Một mã
           khác - `ASR_MISMATCH_UNRESOLVED`, trần khung, cờ sóng âm - nói bản thu **hỏng**, và
           lúc ấy bài chính tả không phải lý do duy nhất.
        3. Tín hiệu sạch: không cờ chặn, không chạm trần, không lệch nhịp. (Nhịp đã được kiểm
           lúc sinh; kiểm lại ở đây vì đây là chỗ quyết.)
        4. File WAV còn trên đĩa và checksum khớp. 307 trong 348 ca đo được đã bị đánh dấu
           `invalid` chỉ vì đương nhiệm đổi; file của chúng còn nguyên.
        5. Đương nhiệm hiện tại của đoạn hoặc là đúng đương nhiệm ứng viên đã đấu với (ca đang
           bay), hoặc là một anh em `source_spelling_v1` của **cùng đoạn** (ca đề cử lại) - tức
           chính bản thu đã thắng nhờ đổi cách đọc. Không đề cử đè lên thứ gì khác.

        Đo trước khi viết: 348 đoạn trong sách đủ cả năm; không đoạn nào có mã khác.
        """
        signal = self._json_object(candidate["signal_json"], "candidate signal metrics")
        beam_codes = self._check_failure_codes_conn(conn, candidate["beam_check_id"])
        greedy_codes = self._check_failure_codes_conn(conn, candidate["greedy_check_id"])
        codes = (beam_codes or set()) | (greedy_codes or set())
        current = str(segment["wav_sha256"] or "").casefold()
        incumbent_unchanged = current == str(candidate["incumbent_sha256"] or "").casefold()
        spelling_sibling = conn.execute(
            "SELECT id FROM segment_candidates WHERE segment_id=? AND "
            "pronunciation_delivery_variant=? AND state=? AND lower(wav_sha256)=?",
            (
                int(candidate["segment_id"]),
                PRONUNCIATION_DELIVERY_SOURCE,
                SEGMENT_CANDIDATE_PROMOTED,
                current,
            ),
        ).fetchone()
        require_all(
            "không giữ được cách đọc ghim: điều kiện chưa đủ",
            (
                "ứng viên không đọc theo cách đọc ghim",
                str(candidate["pronunciation_delivery_variant"] or "")
                != PRONUNCIATION_DELIVERY_LOCKED,
            ),
            ("thiếu check ASR của một đường phiên", beam_codes is None or greedy_codes is None),
            ("cả hai đường phiên đều qua - không có gì để giữ", not codes),
            (
                "có mã trượt ngoài họ neo tên",
                bool(codes - LOCKED_NAME_ANCHOR_CODES),
            ),
            ("tín hiệu mang cờ chặn", bool(self._candidate_blocking_signal_flags(signal))),
            (
                "ứng viên chạm trần khung",
                bool(float(signal.get(SEGMENT_CEILING_METRIC_KEY, 0.0) or 0.0)),
            ),
            ("ứng viên lệch nhịp", bool(float(signal.get("pace_outlier", 0.0) or 0.0))),
            ("file WAV thiếu hoặc checksum lệch", self._candidate_file_error(candidate) is not None),
            (
                "đương nhiệm hiện tại không phải bản đã đấu, cũng không phải anh em đọc-theo-chữ-viết",
                not incumbent_unchanged and spelling_sibling is None,
            ),
            segment_stable_id=str(segment["stable_id"]),
            candidate_id=int(candidate["id"]),
        )
        where = (
            "đương nhiệm chưa đổi"
            if incumbent_unchanged
            else f"đương nhiệm là anh em đọc-theo-chữ-viết (ứng viên #{int(spelling_sibling['id'])})"
        )
        return (
            f"giữ cách đọc ghim: bản thu vòng {candidate['repair_round']} chỉ trượt "
            f"{', '.join(sorted(codes))} - bài chính tả neo tên, không phải bằng chứng bản thu "
            f"hỏng; {where}"
        )

    def find_locked_reading_that_lost_only_the_spelling_test(
        self,
        segment_id: int,
        policy_hash: str,
    ) -> sqlite3.Row | None:
        """Ứng viên đọc-ghim mới nhất của đoạn đủ năm điều kiện trên, hoặc None. Không ném."""
        with self.connect() as conn:
            segment = conn.execute(
                "SELECT * FROM segments WHERE id=?", (int(segment_id),)
            ).fetchone()
            if segment is None:
                return None
            rows = conn.execute(
                "SELECT * FROM segment_candidates WHERE segment_id=? AND policy_hash=? "
                "AND pronunciation_delivery_variant=? AND state IN (?, ?) ORDER BY id DESC",
                (
                    int(segment_id),
                    str(policy_hash),
                    PRONUNCIATION_DELIVERY_LOCKED,
                    SEGMENT_CANDIDATE_DUAL_FAILED,
                    SEGMENT_CANDIDATE_INVALID,
                ),
            ).fetchall()
            for candidate in rows:
                try:
                    self._require_locked_reading_lost_only_the_spelling_test(
                        conn, candidate, segment
                    )
                except (RuntimeError, ValueError, KeyError):
                    continue
                return candidate
        return None

    def find_finished_take_over_a_cut_off_incumbent(
'''
assert OLD in s and "find_locked_reading_that_lost_only_the_spelling_test" not in s, "khong khop cho chen method"
s = s.replace(OLD, NEW, 1)

# ---- promote_segment_candidate: tham so moi
OLD = '''        warning_code: str | None = None,
        over_a_cut_off_incumbent: bool = False,
    ) -> sqlite3.Row:
        normalized_sha256 = self._normalized_sha256(
            validated_wav_sha256,
            "validated segment candidate checksum",
        )'''
NEW = '''        warning_code: str | None = None,
        over_a_cut_off_incumbent: bool = False,
        keeping_the_locked_reading: bool = False,
    ) -> sqlite3.Row:
        normalized_sha256 = self._normalized_sha256(
            validated_wav_sha256,
            "validated segment candidate checksum",
        )'''
assert s.count(OLD) == 1, "khong khop chu ky promote"
s = s.replace(OLD, NEW, 1)

# ---- noi tap trang thai + ghi substitution
OLD = '''                promotable = promotable | {SEGMENT_CANDIDATE_DUAL_FAILED}
            if candidate_state not in promotable:'''
NEW = '''                promotable = promotable | {SEGMENT_CANDIDATE_DUAL_FAILED}
            if keeping_the_locked_reading:
                # Nới BA bất biến - tập trạng thái, hai check ASR phải PASS, checksum đương
                # nhiệm - và chỉ sau khi năm điều kiện được kiểm từ dữ liệu. Cùng một hàm, cùng
                # lý do với `over_a_cut_off_incumbent`: mọi chốt chặn toàn vẹn khác vẫn chạy.
                substitution_reason = self._require_locked_reading_lost_only_the_spelling_test(
                    conn,
                    candidate,
                    segment,
                )
                promotable = promotable | {
                    SEGMENT_CANDIDATE_DUAL_FAILED,
                    SEGMENT_CANDIDATE_INVALID,
                }
            if candidate_state not in promotable:'''
assert s.count(OLD) == 1, "khong khop tap trang thai"
s = s.replace(OLD, NEW, 1)

# ---- hai check ASR phai PASS -> tru khi giu cach doc ghim va ma trot chi la neo ten
OLD = '''            if (
                str(beam_check["verdict"]) != QUALITY_VERDICT_PASS
                or str(greedy_check["verdict"]) != QUALITY_VERDICT_PASS
            ):
                raise RuntimeError("candidate dual-decode ledger does not contain two passing checks")'''
NEW = '''            if (
                str(beam_check["verdict"]) != QUALITY_VERDICT_PASS
                or str(greedy_check["verdict"]) != QUALITY_VERDICT_PASS
            ):
                if not keeping_the_locked_reading:
                    raise RuntimeError("candidate dual-decode ledger does not contain two passing checks")
                # Kiểm lại ngay tại chỗ nới, từ chính hai dòng check: mã trượt chỉ được là neo tên.
                ledger_codes = (
                    self._check_failure_codes_conn(conn, candidate["beam_check_id"]) or set()
                ) | (self._check_failure_codes_conn(conn, candidate["greedy_check_id"]) or set())
                if not ledger_codes or ledger_codes - LOCKED_NAME_ANCHOR_CODES:
                    raise RuntimeError(
                        "candidate dual-decode ledger fails on more than the locked-name spelling test"
                    )'''
assert s.count(OLD) == 1, "khong khop check PASS"
s = s.replace(OLD, NEW, 1)

# ---- checksum duong nhiem -> tru khi giu cach doc ghim (dieu kien 5 da kiem trong require)
OLD = '''            if str(segment["wav_sha256"] or "").casefold() != str(candidate["incumbent_sha256"]):
                raise RuntimeError("segment candidate incumbent checksum changed")
            file_error = self._candidate_file_error(candidate)'''
NEW = '''            if (
                not keeping_the_locked_reading
                and str(segment["wav_sha256"] or "").casefold() != str(candidate["incumbent_sha256"])
            ):
                raise RuntimeError("segment candidate incumbent checksum changed")
            file_error = self._candidate_file_error(candidate)'''
assert s.count(OLD) == 1, "khong khop checksum duong nhiem"
s = s.replace(OLD, NEW, 1)

# ---- CAS cuoi cung so voi duong nhiem HIEN TAI, va ha ban doc-theo-chu-viet khoi `promoted`
# `_invalidate_candidate_conn` tu choi ung vien `promoted`, va `segment_candidate_resume_plan`
# nem neu mot doan co hai ung vien `promoted` - nen duong nay phai tu ha anh em ay, trong cung
# giao dich, co CAS rieng.
OLD = '''                    merged_warning,
                    now,
                    int(candidate["segment_id"]),
                    str(candidate["incumbent_sha256"]),
                ),
            )
            if segment_cursor.rowcount != 1:
                raise RuntimeError("segment candidate promotion lost the incumbent CAS")'''
NEW = '''                    merged_warning,
                    now,
                    int(candidate["segment_id"]),
                    # Khi giữ cách đọc ghim, đương nhiệm hiện tại là anh em đọc-theo-chữ-viết
                    # (điều kiện 5 đã kiểm), không phải bản ứng viên đã đấu với. CAS phải so
                    # với đúng nó - nếu không thì "thắng" đọc thành "mất đương nhiệm".
                    str(segment["wav_sha256"] or "")
                    if keeping_the_locked_reading
                    else str(candidate["incumbent_sha256"]),
                ),
            )
            if segment_cursor.rowcount != 1:
                raise RuntimeError("segment candidate promotion lost the incumbent CAS")
            if keeping_the_locked_reading:
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
assert s.count(OLD) == 1, "khong khop CAS cuoi"
s = s.replace(OLD, NEW, 1)

# ---- CAS trang thai ung vien: so voi trang thai DA DOC dau giao dich, khong phai hang so
# `WHERE id=? AND state=?` voi hang so DUAL_PASSED dung cho duong thuong; nhung ca duong
# `over_a_cut_off_incumbent` (co san, CHUA TUNG chay that: 0 dong machine_take_substitutions
# tren 47 project lo, do 17:59 2026-09-11) lan duong nay de cu mot ung vien `dual_failed` /
# `invalid` - CAS ay tra 0 dong va nem "promotion state CAS failed" SAU khi bang segments da
# doi (giao dich cuon lai nen khong hong du lieu - chi la khong bao gio thanh cong). So voi
# `candidate_state` doc cung ket noi o dau ham: van la CAS, va dung cho ca ba duong.
OLD = '''                    int(candidate_id),
                    SEGMENT_CANDIDATE_DUAL_PASSED,
                ),
            )
            if candidate_cursor.rowcount != 1:'''
NEW = '''                    int(candidate_id),
                    # Trạng thái ĐÃ ĐỌC ở đầu giao dịch, không phải hằng số: đường "giữ cách đọc
                    # ghim" và đường "bản hoàn chỉnh thắng bản bị cắt" đề cử ứng viên
                    # `dual_failed`/`invalid`, và với hằng số DUAL_PASSED thì cả hai không bao
                    # giờ đi qua được dòng dưới.
                    candidate_state,
                ),
            )
            if candidate_cursor.rowcount != 1:'''
assert s.count(OLD) == 1, "khong khop CAS trang thai ung vien"
s = s.replace(OLD, NEW, 1)

# ---- _validated_promoted_candidate_conn: mot ban duoc de cu de GIU cach doc ghim co so phien
# truot (chi neo ten) - moi lan doc lai ke hoach tiep tuc / lap rap chuong deu di qua ham nay,
# nen no phai doc ly do tu chinh dong check cuoi (repair_action) thay vi nem.
OLD = '''        ):
            raise RuntimeError(
                "promoted candidate dual-decode ledger is not passing"
            )'''
NEW = '''        ):
            # Bản được đề cử để GIỮ cách đọc ghim mang sổ phiên trượt - và chỉ được trượt ở
            # bài chính tả neo tên. Lý do nằm ở chính dòng check cuối của nó; đọc từ đó chứ
            # không nới cho mọi bản.
            final_action = (
                conn.execute(
                    "SELECT repair_action FROM quality_checks WHERE id=?",
                    (int(candidate["final_check_id"]),),
                ).fetchone()
                if candidate["final_check_id"] is not None
                else None
            )
            ledger_codes = (
                self._check_failure_codes_conn(conn, candidate["beam_check_id"]) or set()
            ) | (self._check_failure_codes_conn(conn, candidate["greedy_check_id"]) or set())
            require_all(
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
            )'''
assert s.count(OLD) == 1, "khong khop kiem ban da de cu"
s = s.replace(OLD, NEW, 1)

write_atomic(p, s)
print("da va", p)

# ============================================================ pipeline.py
q = root / "ebook_reader" / "pipeline.py"
t = io.open(q, encoding="utf-8").read()

# Neo vao dau khoi import + ten dau tien: `    SEGMENT_ASR_DECODE_QUALITY_STAGE,` xuat hien them
# mot lan nua o dong 1328 voi thut sau hon, va neo 4 khoang trang la chuoi con cua no.
OLD = "from .database import (\n    GENERATION_STRATEGY_DIRECT,\n"
NEW = "from .database import (\n    GENERATION_STRATEGY_DIRECT,\n    KEEP_LOCKED_READING_ACTION,\n    LOCKED_NAME_ANCHOR_CODES,\n"
assert t.count(OLD) == 1 and "LOCKED_NAME_ANCHOR_CODES" not in t, "khong khop import"
t = t.replace(OLD, NEW, 1)

OLD = "    def _promote_a_finished_take_over_a_cut_off_one(\n"
NEW = '''    def _keep_the_locked_reading(self, item: Any) -> bool:
        """Đề cử bản đọc-ghim đã trượt **chỉ** bài chính tả neo tên, thay vì đổi cách đọc.

        Đo 2026-09-11 trên sách 92 chương: 348/716 đoạn được sửa (48%) đọc tên theo chữ viết,
        và cả 348 bản đọc-ghim thua chỉ vì `ASR_LOCKED_NAME_ANCHOR_MISMATCH` - Jake 79 lần,
        Michael 35, Spirit 31. Người nghe nghe `Giếch` ở đoạn này và `Jake` ở đoạn kế, tuỳ
        Whisper trượt ở đâu. Neo tên là bài chính tả, không phải bằng chứng bản thu hỏng
        (docs/LOCKED_NAME_ANCHOR_IS_A_SPELLING_TEST.md); đổi cách đọc để đậu nó là đổi thứ
        người nghe nghe.

        Gọi ở vòng sửa ASR, **trước** khi cấp phát ứng viên vòng lẻ - vòng mà biến thể đọc theo
        chữ viết được yêu cầu. Năm điều kiện nằm ở `database`; đây chỉ đề nghị. Phán quyết máy
        ghi cho từng mã neo tên, với lý do, để báo cáo không im lặng về nó.
        """
        segment_id = int(item["id"])
        candidate = self.db.find_locked_reading_that_lost_only_the_spelling_test(
            segment_id,
            self.quality_policy_hash,
        )
        if candidate is None:
            return False
        segment = dict(self.db.get_segment(segment_id))
        candidate_item = self._segment_candidate_item(segment, candidate)
        signal_valid, _metrics = self._inspect_existing_segment(candidate_item)
        if not signal_valid:
            self.db.mark_segment_candidate_invalid(
                int(candidate["id"]),
                expected_wav_sha256=str(candidate["wav_sha256"]),
                reason="candidate failed signal validation immediately before keeping its reading",
            )
            return False
        signal = self._segment_signal_provenance(candidate_item)
        codes = list(
            self._signal_warning_codes(
                signal,
                split_recovery=bool(signal.get("split_parts")),
            )
        )
        anchor_codes = sorted(
            LOCKED_NAME_ANCHOR_CODES
            & set(str(c) for c in _asr_only_failure_codes(str(candidate["failure_reason"] or "")) or ())
        ) or ["ASR_LOCKED_NAME_ANCHOR_MISMATCH"]
        for code in anchor_codes:
            if code not in codes:
                codes.append(code)
        try:
            promoted = self.db.promote_segment_candidate(
                int(candidate["id"]),
                validated_wav_sha256=str(candidate["wav_sha256"]),
                repair_action=KEEP_LOCKED_READING_ACTION,
                attempt=self._next_segment_quality_attempt(segment_id),
                warning_code="|".join(codes) or None,
                keeping_the_locked_reading=True,
            )
        except (RuntimeError, ValueError, KeyError) as exc:
            self.log(
                f"Segment {item['stable_id']}: không giữ được cách đọc ghim - {exc}"
            )
            return False
        if str(promoted["state"]) != SEGMENT_CANDIDATE_PROMOTED:
            return False
        reason = (
            "neo tên là bài chính tả; giữ cách đọc ghim để nhất quán toàn sách. "
            f"bản thu vòng {candidate['repair_round']} chỉ trượt {', '.join(anchor_codes)}"
        )
        for code in anchor_codes:
            self.db.accept_segment_audio_as_machine(
                segment_stable_id=str(item["stable_id"]),
                wav_sha256=str(candidate["wav_sha256"]),
                warning_code=code,
                reason=reason,
            )
        self.log(
            f"Giữ cách đọc ghim cho {item['stable_id']}: đề cử bản thu vòng "
            f"{candidate['repair_round']} thay vì đổi sang đọc theo chữ viết "
            f"({', '.join(anchor_codes)} - đã ghi phán quyết máy)."
        )
        return True

    def _promote_a_finished_take_over_a_cut_off_one(
'''
assert t.count(OLD) == 1, "khong khop cho chen _keep_the_locked_reading"
t = t.replace(OLD, NEW, 1)

# ---- import _asr_only_failure_codes neu chua co
if "_asr_only_failure_codes" not in t.split("class ")[0]:
    OLD = "from .database import (\n"
    NEW = "from .database import _asr_only_failure_codes\nfrom .database import (\n"
    assert t.count(OLD) == 1, "khong khop import database"
    t = t.replace(OLD, NEW, 1)

# ---- hook trong vong sua ASR (_verify_chapter_audio): truoc cap phat vong le
OLD = '''                action = str(plan["action"])
                if action == "allocate":
                    repair_item = self._checkpoint_short_ceiling_repair(item)'''
NEW = '''                action = str(plan["action"])
                if action == "allocate":
                    # Vòng lẻ là vòng biến thể đọc-theo-chữ-viết được yêu cầu. Trước khi cấp
                    # phát nó: nếu bản đọc-ghim vừa trượt CHỈ vì bài chính tả neo tên, giữ nó.
                    if int(plan["repair_round"]) % 2 == 1 and self._keep_the_locked_reading(item):
                        completed_ids.append(segment_id)
                        progressed = True
                        continue
                    repair_item = self._checkpoint_short_ceiling_repair(item)'''
assert t.count(OLD) == 1, "khong khop hook vong sua"
t = t.replace(OLD, NEW, 1)

# ---- tach duoi cua _process_chapter thanh _publish_verified_chapter (hai nguoi goi)
OLD = r'''        # Sau mọi đường thu lại, trước mọi cổng chặn: đây là chỗ duy nhất "hết ngân sách
        # sửa" là đúng theo cấu trúc chứ không phải theo một biến đếm ai đó phải nhớ tăng.
        self._grant_machine_acceptances(chapter)

        rows = self.db.list_segments(chapter_id=chapter_id)
        blocking_warnings = self._high_quality_blocking_segment_warnings(rows)
        if blocking_warnings:
            raise ChapterQualityError(
                "High-quality policy requires repair or review for segment warnings: "
                + "; ".join(
                    f"{item['stable_id']}={','.join(item['warning_codes'])}"
                    for item in blocking_warnings
                ),
                metrics={"blocking_segment_warnings": blocking_warnings},
                failure_codes=("SEGMENT_QA_REVIEW_REQUIRED",),
                review_required=True,
            )
        if not self._chapter_has_current_segment_audio_qa(chapter_id):
            raise ChapterQualityError(
                "Current policy requires passing ASR and perceptual evidence for every segment",
                metrics={"chapter_id": chapter_id},
                failure_codes=("SEGMENT_QA_EVIDENCE_MISSING",),
                review_required=True,
            )
        if not self.db.chapter_is_publishable(chapter_id):
            failed = [row for row in rows if row["status"] == SegmentStatus.FAILED.value]
            self.db.update_chapter_status(
                chapter_id,
                ChapterStatus.FAILED.value,
                f"{len(failed)} segment failed; chapter MP3 intentionally not published",
            )
            self.log(f"Không xuất MP3 chapter {chapter['title']}: còn {len(failed)} segment lỗi.")
            return

        self._validate_chapter_source(chapter)

        wavs = self._chapter_delivery_wavs(chapter, rows)
        self._resource_gate(
            f"FFmpeg chapter {chapter['chapter_index']}",
            require_cpu_io=True,
        )
        assembly_label = f"Ghép và kiểm tra MP3 chapter {chapter['chapter_index']}"
        self._progress(assembly_label)
        assembly = assemble_chapter_atomic_with_metrics(
            wavs,
            output,
            self.settings,
            title=str(chapter["title"]),
            book_title=str(self.db.book()["title"]),
            track=int(chapter["chapter_index"]),
            work_dir=self.paths.work / "silence",
        )
        checksum = assembly.checksum
        quality_metrics = assembly.quality.to_dict()
        quality_metadata = self.db.quality_metadata_for_current_policy()
        self.db.record_quality_check(
            scope=QUALITY_SCOPE_CHAPTER,
            stage=CHAPTER_QUALITY_STAGE,
            chapter_id=chapter_id,
            artifact_sha256=checksum,
            policy_hash=self.quality_policy_hash,
            policy_version=QUALITY_POLICY_VERSION,
            verdict=QUALITY_VERDICT_PASS,
            metrics=quality_metrics,
            attempt=self._next_chapter_quality_attempt(chapter_id),
        )
        self.db.register_artifact(
            artifact_key=f"chapter_mp3:{chapter['chapter_index']}",
            kind="chapter_mp3",
            path=output,
            sha256=checksum,
            verified=True,
            metadata={
                "chapter_id": chapter_id,
                "title": str(chapter["title"]),
                "quality": quality_metadata,
                "quality_metrics": quality_metrics,
            },
        )
        if assembly.quality.review_flags:
            self.db.event(
                "warning",
                "CHAPTER_QA_REVIEW_FLAGS",
                f"Chapter {chapter['title']} passed hard QA with review flags",
                {
                    "chapter_id": chapter_id,
                    "flags": list(assembly.quality.review_flags),
                    "metrics": quality_metrics,
                },
            )
        self.db.update_chapter_status(chapter_id, ChapterStatus.COMPLETED.value)
        self._progress(assembly_label, 1, 1)
        self.log(f"Chapter MP3 đã hoàn tất và giải mã kiểm tra thành công: {output.name}")
        self.emit(
            "chapter_completed",
            {"chapter_id": chapter_id, "path": str(output), "title": str(chapter["title"])},
        )
'''
NEW = r'''        self._publish_verified_chapter(chapter)
'''
assert t.count(OLD) == 1, "khong khop duoi _process_chapter"
t = t.replace(OLD, NEW, 1)
OLD = "    def _chunk_path(self, row: Any) -> Path:\n"
NEW = r'''    def _publish_verified_chapter(self, chapter: Any) -> None:
        """Đuôi của `_process_chapter`, sau mọi đường thu lại: cấp phép máy, ba cổng chặn, ghép
        MP3, ghi sổ chất lượng chương, đăng ký artifact, đánh dấu hoàn thành.

        Tách ra thành một hàm vì có hai người gọi. Đường ống gọi nó ở cuối `_process_chapter`.
        `scripts/keep_the_locked_reading.py` gọi nó để ghép lại một chương ĐÃ LÊN SÁCH sau khi
        đề cử lại bản đọc-ghim cho các đoạn của chương ấy - không thu lại đoạn nào, không
        nạp model nào. Chạy lại cả `_process_chapter` cho việc ấy là không được: một chương
        đã hoàn thành vẫn có thể mang đoạn `failed` được máy cấp phép (084: `Selene Valkryn.`
        thua neo tên qua năm vòng), và bước tổng hợp coi đoạn ấy là chưa có bằng chứng hiện
        hành, đặt lại thành `signal_passed` rồi gọi Whisper - đo 18:25 2026-09-11. Cùng một
        thân hàm, không chép: cổng nào thêm sau này thì cả hai người gọi cùng đi qua.
        """
        chapter_id = int(chapter["id"])
        output = Path(str(chapter["output_mp3"]))
        # Sau mọi đường thu lại, trước mọi cổng chặn: đây là chỗ duy nhất "hết ngân sách
        # sửa" là đúng theo cấu trúc chứ không phải theo một biến đếm ai đó phải nhớ tăng.
        self._grant_machine_acceptances(chapter)

        rows = self.db.list_segments(chapter_id=chapter_id)
        blocking_warnings = self._high_quality_blocking_segment_warnings(rows)
        if blocking_warnings:
            raise ChapterQualityError(
                "High-quality policy requires repair or review for segment warnings: "
                + "; ".join(
                    f"{item['stable_id']}={','.join(item['warning_codes'])}"
                    for item in blocking_warnings
                ),
                metrics={"blocking_segment_warnings": blocking_warnings},
                failure_codes=("SEGMENT_QA_REVIEW_REQUIRED",),
                review_required=True,
            )
        if not self._chapter_has_current_segment_audio_qa(chapter_id):
            raise ChapterQualityError(
                "Current policy requires passing ASR and perceptual evidence for every segment",
                metrics={"chapter_id": chapter_id},
                failure_codes=("SEGMENT_QA_EVIDENCE_MISSING",),
                review_required=True,
            )
        if not self.db.chapter_is_publishable(chapter_id):
            failed = [row for row in rows if row["status"] == SegmentStatus.FAILED.value]
            self.db.update_chapter_status(
                chapter_id,
                ChapterStatus.FAILED.value,
                f"{len(failed)} segment failed; chapter MP3 intentionally not published",
            )
            self.log(f"Không xuất MP3 chapter {chapter['title']}: còn {len(failed)} segment lỗi.")
            return

        self._validate_chapter_source(chapter)

        wavs = self._chapter_delivery_wavs(chapter, rows)
        self._resource_gate(
            f"FFmpeg chapter {chapter['chapter_index']}",
            require_cpu_io=True,
        )
        assembly_label = f"Ghép và kiểm tra MP3 chapter {chapter['chapter_index']}"
        self._progress(assembly_label)
        assembly = assemble_chapter_atomic_with_metrics(
            wavs,
            output,
            self.settings,
            title=str(chapter["title"]),
            book_title=str(self.db.book()["title"]),
            track=int(chapter["chapter_index"]),
            work_dir=self.paths.work / "silence",
        )
        checksum = assembly.checksum
        quality_metrics = assembly.quality.to_dict()
        quality_metadata = self.db.quality_metadata_for_current_policy()
        self.db.record_quality_check(
            scope=QUALITY_SCOPE_CHAPTER,
            stage=CHAPTER_QUALITY_STAGE,
            chapter_id=chapter_id,
            artifact_sha256=checksum,
            policy_hash=self.quality_policy_hash,
            policy_version=QUALITY_POLICY_VERSION,
            verdict=QUALITY_VERDICT_PASS,
            metrics=quality_metrics,
            attempt=self._next_chapter_quality_attempt(chapter_id),
        )
        self.db.register_artifact(
            artifact_key=f"chapter_mp3:{chapter['chapter_index']}",
            kind="chapter_mp3",
            path=output,
            sha256=checksum,
            verified=True,
            metadata={
                "chapter_id": chapter_id,
                "title": str(chapter["title"]),
                "quality": quality_metadata,
                "quality_metrics": quality_metrics,
            },
        )
        if assembly.quality.review_flags:
            self.db.event(
                "warning",
                "CHAPTER_QA_REVIEW_FLAGS",
                f"Chapter {chapter['title']} passed hard QA with review flags",
                {
                    "chapter_id": chapter_id,
                    "flags": list(assembly.quality.review_flags),
                    "metrics": quality_metrics,
                },
            )
        self.db.update_chapter_status(chapter_id, ChapterStatus.COMPLETED.value)
        self._progress(assembly_label, 1, 1)
        self.log(f"Chapter MP3 đã hoàn tất và giải mã kiểm tra thành công: {output.name}")
        self.emit(
            "chapter_completed",
            {"chapter_id": chapter_id, "path": str(output), "title": str(chapter["title"])},
        )

''' + OLD
assert t.count(OLD) == 1, "khong khop cho chen _publish_verified_chapter"
t = t.replace(OLD, NEW, 1)

write_atomic(q, t)
print("da va", q)

# ============================================================ tests
TEST = r'''
"""Giữ cách đọc ghim khi chỉ bài chính tả neo tên phàn nàn — thử trên bản sao của project THẬT.

Chương 084 đúc lại (`lo03r_084b`) là ca gốc: bản đọc-ghim `I-xờ-hờ-ta-ra` qua nhịp, chết ở neo
tên trên cả hai đường phiên (`dual_failed`), và bản đọc theo chữ viết được đề cử. Đồ thị ứng
viên với đủ provenance quá nặng để dựng tay, nên bài này chép project thật vào thư mục tạm và
đề cử lại ở đó — WAV được tham chiếu bằng đường dẫn tuyệt đối nên chốt chặn file vẫn chạy thật.
Bỏ qua (có nói lý do) khi máy không có project ấy.
"""
from __future__ import annotations

import json
import shutil
import sqlite3
from pathlib import Path

import pytest

from ebook_reader.database import (
    KEEP_LOCKED_READING_ACTION,
    PRONUNCIATION_DELIVERY_LOCKED,
    PRONUNCIATION_DELIVERY_SOURCE,
    SEGMENT_CANDIDATE_INVALID,
    SEGMENT_CANDIDATE_PROMOTED,
    ProjectDB,
)

REAL = Path("D:/Novels/Audiobooks/_versions/v0.2.0-lo03r/lo03r_084b_9455372a18")
LOST_LINE_SUFFIX = "feeb9dd9dda2"  # 'Chúng tôi đang đến Thành phố Ishtara (Ishtara City).'


def _copy(tmp_path: Path) -> ProjectDB:
    if not (REAL / "project.sqlite3").is_file():
        pytest.skip(f"không có project thật {REAL.name} trên máy này")
    target = tmp_path / "project.sqlite3"
    shutil.copyfile(REAL / "project.sqlite3", target)
    return ProjectDB(target)


def _segment(db: ProjectDB) -> sqlite3.Row:
    with db.connect() as conn:
        row = conn.execute(
            "SELECT * FROM segments WHERE stable_id LIKE ?", (f"%{LOST_LINE_SUFFIX}",)
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


def _promoted_rows(db: ProjectDB, segment_id: int) -> list[sqlite3.Row]:
    with db.connect() as conn:
        return list(
            conn.execute(
                "SELECT * FROM segment_candidates WHERE segment_id=? AND state=?",
                (segment_id, SEGMENT_CANDIDATE_PROMOTED),
            )
        )


def test_the_locked_reading_that_lost_only_the_spelling_test_is_found(tmp_path: Path) -> None:
    db = _copy(tmp_path)
    segment = _segment(db)

    candidate = db.find_locked_reading_that_lost_only_the_spelling_test(
        int(segment["id"]), str(segment["generation_policy_hash"])
    )

    assert candidate is not None
    assert str(candidate["pronunciation_delivery_variant"]) == PRONUNCIATION_DELIVERY_LOCKED
    assert "ASR_LOCKED_NAME_ANCHOR" in str(candidate["failure_reason"])
    # Đương nhiệm hiện tại là bản đọc theo chữ viết - đúng cái ta muốn thay.
    with db.connect() as conn:
        incumbent = conn.execute(
            "SELECT pronunciation_delivery_variant FROM segment_candidates "
            "WHERE segment_id=? AND state=? AND lower(wav_sha256)=lower(?)",
            (int(segment["id"]), SEGMENT_CANDIDATE_PROMOTED, str(segment["wav_sha256"])),
        ).fetchone()
    assert incumbent is not None and str(incumbent[0]) == PRONUNCIATION_DELIVERY_SOURCE


def test_keeping_the_locked_reading_moves_the_segment_onto_it(tmp_path: Path) -> None:
    db = _copy(tmp_path)
    segment = _segment(db)
    before = str(segment["wav_sha256"])
    candidate = db.find_locked_reading_that_lost_only_the_spelling_test(
        int(segment["id"]), str(segment["generation_policy_hash"])
    )
    assert candidate is not None
    assert len(_promoted_rows(db, int(segment["id"]))) == 1

    promoted = db.promote_segment_candidate(
        int(candidate["id"]),
        validated_wav_sha256=str(candidate["wav_sha256"]),
        repair_action=KEEP_LOCKED_READING_ACTION,
        attempt=_next_attempt(db, int(segment["id"])),
        warning_code="ASR_LOCKED_NAME_ANCHOR_MISMATCH",
        keeping_the_locked_reading=True,
    )

    assert str(promoted["state"]) == SEGMENT_CANDIDATE_PROMOTED
    after = db.get_segment(int(segment["id"]))
    assert str(after["wav_sha256"]).casefold() == str(candidate["wav_sha256"]).casefold()
    assert str(after["wav_sha256"]) != before
    assert str(after["wav_path"]) == str(candidate["wav_path"])
    # Một đoạn chỉ có MỘT bản được đề cử: bản đọc theo chữ viết bị hạ, có lý do, cùng giao dịch.
    still_promoted = _promoted_rows(db, int(segment["id"]))
    assert [int(r["id"]) for r in still_promoted] == [int(candidate["id"])]
    with db.connect() as conn:
        sibling = conn.execute(
            "SELECT state, failure_reason FROM segment_candidates "
            "WHERE segment_id=? AND lower(wav_sha256)=lower(?)",
            (int(segment["id"]), before),
        ).fetchone()
    assert str(sibling["state"]) == SEGMENT_CANDIDATE_INVALID
    assert str(sibling["failure_reason"]).startswith("superseded: ")
    # Kế hoạch tiếp tục của đoạn vẫn dựng được (nó ném nếu có hai bản được đề cử).
    db.segment_candidate_resume_plan(int(segment["id"]), str(segment["generation_policy_hash"]))
    # Việc thay được ghi vào sổ, có lý do - báo cáo không im lặng về nó.
    reasons = [str(r["reason"]) for r in db.list_take_substitutions()]
    assert any("giữ cách đọc ghim" in r for r in reasons)


def test_without_the_flag_the_old_contract_still_refuses(tmp_path: Path) -> None:
    db = _copy(tmp_path)
    segment = _segment(db)
    candidate = db.find_locked_reading_that_lost_only_the_spelling_test(
        int(segment["id"]), str(segment["generation_policy_hash"])
    )
    assert candidate is not None

    with pytest.raises(RuntimeError, match="cannot be promoted before both ASR decodes pass"):
        db.promote_segment_candidate(
            int(candidate["id"]),
            validated_wav_sha256=str(candidate["wav_sha256"]),
            repair_action=KEEP_LOCKED_READING_ACTION,
            attempt=_next_attempt(db, int(segment["id"])),
            warning_code="ASR_LOCKED_NAME_ANCHOR_MISMATCH",
        )
    # Và không có gì đổi: đương nhiệm vẫn là bản đọc theo chữ viết.
    assert str(db.get_segment(int(segment["id"]))["wav_sha256"]) == str(segment["wav_sha256"])


def test_any_other_failure_code_refuses_and_names_the_clause(tmp_path: Path) -> None:
    """Một mã ngoài họ neo tên nói bản thu HỎNG; lúc ấy bài chính tả không phải lý do duy nhất."""
    db = _copy(tmp_path)
    segment = _segment(db)
    candidate = db.find_locked_reading_that_lost_only_the_spelling_test(
        int(segment["id"]), str(segment["generation_policy_hash"])
    )
    assert candidate is not None
    with sqlite3.connect(str(tmp_path / "project.sqlite3")) as conn:
        row = conn.execute(
            "SELECT failure_codes_json FROM quality_checks WHERE id=?",
            (int(candidate["beam_check_id"]),),
        ).fetchone()
        codes = json.loads(row[0] or "[]") + ["ASR_MISMATCH_UNRESOLVED"]
        conn.execute(
            "UPDATE quality_checks SET failure_codes_json=? WHERE id=?",
            (json.dumps(codes), int(candidate["beam_check_id"])),
        )

    assert db.find_locked_reading_that_lost_only_the_spelling_test(
        int(segment["id"]), str(segment["generation_policy_hash"])
    ) is None
    with pytest.raises(RuntimeError, match="có mã trượt ngoài họ neo tên"):
        db.promote_segment_candidate(
            int(candidate["id"]),
            validated_wav_sha256=str(candidate["wav_sha256"]),
            repair_action=KEEP_LOCKED_READING_ACTION,
            attempt=_next_attempt(db, int(segment["id"])),
            warning_code="ASR_LOCKED_NAME_ANCHOR_MISMATCH",
            keeping_the_locked_reading=True,
        )


def test_a_missing_wav_refuses(tmp_path: Path) -> None:
    db = _copy(tmp_path)
    segment = _segment(db)
    candidate = db.find_locked_reading_that_lost_only_the_spelling_test(
        int(segment["id"]), str(segment["generation_policy_hash"])
    )
    assert candidate is not None
    with sqlite3.connect(str(tmp_path / "project.sqlite3")) as conn:
        conn.execute(
            "UPDATE segment_candidates SET wav_path=? WHERE id=?",
            (str(tmp_path / "khong-co.wav"), int(candidate["id"])),
        )

    assert db.find_locked_reading_that_lost_only_the_spelling_test(
        int(segment["id"]), str(segment["generation_policy_hash"])
    ) is None
'''
write_atomic(root / "tests" / "test_keep_the_locked_reading.py", TEST.lstrip())
print("da tao", root / "tests" / "test_keep_the_locked_reading.py")
