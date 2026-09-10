r"""Va: khi ASR khong the lam trong tai, giu ban thu bo sinh NOI XONG thay vi ban bi CAT.

CHUA AP luc viet - lo 2 dang chay ba chuong cuoi. Ap o ranh gioi lo, TRUOC lo va cho lo 2.

Ba ca trong 50.196 doan da luu, cung mot chu ky (duong nhiem dai dung 1,92s = 12 khung x 160ms):

    alpha.25 ch005  '"Arghh..."'
    alpha.60 ch021  '"Tiep theo."'
    lo02     ch053  '"Bat bai?"'

Xem docs/OPTIMISATION_QUEUE.md, muc *"Lo 2 tra loi, va cau tra loi doi ca cach phat bieu"*.
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

# ============================================================ asr_contract.py: mot dinh nghia
p = root / "ebook_reader" / "asr_contract.py"
s = io.open(p, encoding="utf-8").read()
OLD = "SHORT_CONTEXT_REPEAT_COUNT = 3"
NEW = '''# Dưới ngưỡng này một phán quyết ASR không mang thông tin, và đây là số **đo được** chứ không
# phải số chọn: trên 4.528 segment đã commit, tham chiếu ngắn hơn cho tương đồng trung vị 0,27
# so với 0,94 của một câu bình thường, trượt ngưỡng 75% số lần so với 0,2%, và trả về phiên bản
# dài hơn ba lần trong 30% số ca — nhãn hạng "SSS" từng quay về thành một lời mời đăng ký kênh
# YouTube.
#
# Nằm ở đây thay vì ở `asr.py` vì `database.py` cũng cần nó, và `database` nằm dưới `asr` trong
# thứ tự phụ thuộc nên không import lên được. Một hằng số đo được mà có hai bản sao thì sớm muộn
# hai bản sẽ khác nhau.
ASR_MIN_VERIFIABLE_CHARS = 10

SHORT_CONTEXT_REPEAT_COUNT = 3'''
assert OLD in s, "khong khop asr_contract"
s = s.replace(OLD, NEW, 1)
write_atomic(p, s)
print("da va", p)

# ============================================================ asr.py: dung ban trong contract
p = root / "ebook_reader" / "asr.py"
s = io.open(p, encoding="utf-8").read()
OLD = """ASR_MIN_VERIFIABLE_CHARS = 10
ASR_UNVERIFIABLE_SHORT_TEXT = "ASR_UNVERIFIABLE_SHORT_TEXT\""""
NEW = """# `ASR_MIN_VERIFIABLE_CHARS` đã chuyển sang `asr_contract` để `database` dùng được cùng một
# con số; phép đo đứng sau nó ghi ở đó. Tên vẫn xuất ra từ module này để mọi chỗ gọi cũ không
# phải đổi.
ASR_UNVERIFIABLE_SHORT_TEXT = "ASR_UNVERIFIABLE_SHORT_TEXT\""""
assert OLD in s, "khong khop asr.py hang so"
s = s.replace(OLD, NEW, 1)

OLD = """from .asr_contract import ("""
NEW = """from .asr_contract import (
    ASR_MIN_VERIFIABLE_CHARS,"""
assert OLD in s, "khong khop asr.py import"
s = s.replace(OLD, NEW, 1)
write_atomic(p, s)
print("da va", p)

# ============================================================ database.py
p = root / "ebook_reader" / "database.py"
s = io.open(p, encoding="utf-8").read()

OLD = """from .asr_contract import (
    COLLAPSED_SHORT_CONTEXT_EFFECTIVE_REPEAT_COUNT,"""
NEW = """from .asr_contract import (
    ASR_MIN_VERIFIABLE_CHARS,
    COLLAPSED_SHORT_CONTEXT_EFFECTIVE_REPEAT_COUNT,"""
assert OLD in s, "khong khop database import"
s = s.replace(OLD, NEW, 1)

# ---------------------------------------------------------------- bang rieng
OLD = """CREATE TABLE IF NOT EXISTS pronunciations ("""
NEW = """CREATE TABLE IF NOT EXISTS machine_take_substitutions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    segment_stable_id TEXT NOT NULL,
    incumbent_wav_sha256 TEXT NOT NULL,
    candidate_wav_sha256 TEXT NOT NULL,
    reason TEXT NOT NULL DEFAULT '',
    created_at REAL NOT NULL,
    UNIQUE (segment_stable_id, candidate_wav_sha256)
);

CREATE TABLE IF NOT EXISTS pronunciations ("""
assert OLD in s, "khong khop cho chen bang"
s = s.replace(OLD, NEW, 1)

# ---------------------------------------------------------------- helper doc ma trươt
OLD = """def require_all("""
NEW = '''SEGMENT_CEILING_METRIC_KEY = "generation_ceiling_hit"
"""Khoá trong `signal_json` mà bộ sinh dùng để tự khai nó chạy hết khung mà chưa dừng.

Chuỗi trần chứ không import từ `tts`: `database` nằm dưới `tts` trong thứ tự phụ thuộc. Đây là
tên một **khoá dữ liệu** đã nằm sẵn trong hàng nghìn hàng `signal_json` đã lưu, không phải một
ngưỡng ai có thể đổi ý - khác hẳn `ASR_MIN_VERIFIABLE_CHARS`, thứ đã được chuyển vào
`asr_contract` chính vì nó là một con số đo được.
"""


def _asr_only_failure_codes(reason: str) -> set[str] | None:
    """Mã trượt của ứng viên, hoặc None nếu có mã nào **không** phải mã ASR.

    `beam=X; greedy=Y; blocking_signal=Z` -> {X, Y, Z}. Một cờ sóng âm hay một mã TTS trong đó
    nói bản thu hỏng theo cách **nhìn thấy được mà không cần phiên âm**, nên văn bản ngắn không
    bào chữa cho nó; trả None để chốt chặn từ chối.

    Chuỗi rỗng cũng trả None: "không có mã nào" nghĩa là không biết vì sao ứng viên trượt, và
    không biết thì không được thay.
    """
    codes = {
        value
        for part in str(reason or "").split(";")
        if (value := part.partition("=")[2].strip()) and value.isupper()
    }
    if not codes:
        return None
    return codes if all(code.startswith("ASR_") for code in codes) else None


def require_all('''
assert OLD in s, "khong khop cho chen helper"
s = s.replace(OLD, NEW, 1)

# ---------------------------------------------------------------- dieu kien + accessor + chu ky
OLD = """    def promote_segment_candidate(
        self,
        candidate_id: int,
        *,
        validated_wav_sha256: str,
        repair_action: str | None = None,
        attempt: int,
        warning_code: str | None = None,
    ) -> sqlite3.Row:"""
NEW = '''    def _require_candidate_beats_a_cut_off_incumbent(
        self,
        candidate: sqlite3.Row,
        segment: sqlite3.Row,
    ) -> str:
        """Bốn điều kiện phải đúng cùng lúc mới được thay một bản thu chưa qua ASR.

        Kiểm ở tầng này chứ không ở đường ống, và kiểm từ **chính hai dòng dữ liệu** chứ không
        từ lời khai của người gọi: một chốt chặn mà người gọi tự khẳng định điều kiện thì không
        phải chốt chặn.

        1. Đương nhiệm **chạm trần khung** — bộ sinh tự khai nó bị cắt giữa câu. Đây là điều
           kiện làm cả cơ chế này hợp lẽ; không có nó thì đây chỉ là thay một bản thu tốt bằng
           một bản chưa chứng minh được.
        2. Ứng viên **không** chạm trần — nó tự kết thúc, tức một bản thu hoàn chỉnh.
        3. Văn bản tham chiếu ngắn hơn `ASR_MIN_VERIFIABLE_CHARS`, nên phán quyết ASR ở đó
           không mang thông tin. Nếu văn bản đủ dài thì ASR **có** ý kiến, và "ứng viên trượt
           ASR" là bằng chứng thật — lúc ấy không được thay.
        4. Mọi mã trượt của ứng viên đều là mã ASR.

        Trả về một dòng lý do, để nó đi thẳng vào bảng ghi và vào báo cáo.

        Đo trước khi viết, trên 50.196 đoạn đã lưu: đúng **14** đoạn có văn bản ngắn, có ứng
        viên **và** đương nhiệm chạm trần. 469 đoạn khác có văn bản ngắn và có ứng viên mà
        đương nhiệm không chạm trần — chúng là lý do điều 1 không được bỏ, và là lý do cách
        chữa rẻ hơn (nới cái cớ văn-bản-ngắn ở chỗ phán xử ứng viên) đã bị bác bỏ.
        """
        segment_signal = self._json_object(
            segment["signal_json"],
            "segment signal metrics",
        )
        candidate_signal = self._json_object(
            candidate["signal_json"],
            "candidate signal metrics",
        )
        text = str(segment["text"] or "")
        speakable = sum(char.isalnum() for char in text)
        codes = _asr_only_failure_codes(str(candidate["failure_reason"] or ""))
        require_all(
            "không được thay bản thu: điều kiện chưa đủ",
            (
                "đương nhiệm không chạm trần khung",
                not float(segment_signal.get(SEGMENT_CEILING_METRIC_KEY, 0.0) or 0.0),
            ),
            (
                "ứng viên cũng chạm trần khung",
                bool(float(candidate_signal.get(SEGMENT_CEILING_METRIC_KEY, 0.0) or 0.0)),
            ),
            ("văn bản đủ dài để ASR phán xử", speakable >= ASR_MIN_VERIFIABLE_CHARS),
            ("ứng viên trượt bằng mã ngoài ASR", codes is None),
            segment_stable_id=str(segment["stable_id"]),
            candidate_id=int(candidate["id"]),
        )
        return (
            f"đương nhiệm chạm trần khung ở {segment['wav_duration']}s; ứng viên vòng "
            f"{candidate['repair_round']} dài {candidate['wav_duration']}s tự kết thúc và chỉ "
            f"trượt bằng {', '.join(sorted(codes or ()))} trên văn bản {speakable} ký tự "
            f"chữ-số (ngưỡng ASR {ASR_MIN_VERIFIABLE_CHARS})"
        )

    def find_finished_take_over_a_cut_off_incumbent(
        self,
        segment_id: int,
        policy_hash: str,
    ) -> sqlite3.Row | None:
        """Ứng viên đầu tiên đủ điều kiện thay bản thu bị cắt, hoặc None.

        Không ném. Nó gọi **chính** hàm kiểm mà `promote_segment_candidate` gọi, và coi một lần
        ném là câu trả lời "không" — nên bốn điều kiện chỉ tồn tại ở một chỗ. Nếu đường ống tự
        kiểm lại bằng bản sao của bốn điều kiện thì hai bản sẽ trôi khỏi nhau, và bản trôi sẽ là
        bản không ai chạy test.

        Chọn theo `repair_round` nhỏ nhất chứ không theo thời lượng hay điểm nào: giữa hai bản
        thu hoàn chỉnh mà ASR không phán xử được, **không có bằng chứng nào** để xếp hạng. Một
        quy tắc tất định và nhàm chán ở đây trung thực hơn một quy tắc nghe có vẻ thông minh, và
        nó còn tái lập được giữa hai lượt chạy.
        """
        segment = self.get_segment(int(segment_id))
        candidates = self.list_segment_candidates(
            segment_id=int(segment_id),
            policy_hash=str(policy_hash),
        )
        for candidate in sorted(candidates, key=lambda row: int(row["repair_round"])):
            if str(candidate["state"]) != SEGMENT_CANDIDATE_DUAL_FAILED:
                continue
            try:
                self._require_candidate_beats_a_cut_off_incumbent(candidate, segment)
            except RuntimeError:
                continue
            return candidate
        return None

    def list_take_substitutions(self) -> list[sqlite3.Row]:
        """Mọi lần máy thay một bản thu bị cắt bằng một bản hoàn chỉnh chưa qua ASR.

        Bảng riêng, cùng lý do như `machine_audio_acceptances`: quên union một bảng mới thì báo
        cáo thiếu một dòng và ai đó nhận ra; quên lọc một cột `source` thì báo cáo nói rằng có
        người đã nghe thứ không ai nghe, và **im lặng**.
        """
        with self.connect() as conn:
            return list(
                conn.execute(
                    "SELECT * FROM machine_take_substitutions ORDER BY created_at, id"
                )
            )

    def promote_segment_candidate(
        self,
        candidate_id: int,
        *,
        validated_wav_sha256: str,
        repair_action: str | None = None,
        attempt: int,
        warning_code: str | None = None,
        over_a_cut_off_incumbent: bool = False,
    ) -> sqlite3.Row:'''
assert OLD in s, "khong khop chu ky promote"
s = s.replace(OLD, NEW, 1)

# ---------------------------------------------------------------- noi long dung mot bat bien
OLD = """            candidate_state = str(candidate["state"])
            if candidate_state not in {
                SEGMENT_CANDIDATE_DUAL_PASSED,
                SEGMENT_CANDIDATE_PROMOTED,
            }:
                raise RuntimeError("segment candidate cannot be promoted before both ASR decodes pass")"""
NEW = '''            candidate_state = str(candidate["state"])
            promotable = {SEGMENT_CANDIDATE_DUAL_PASSED, SEGMENT_CANDIDATE_PROMOTED}
            substitution_reason: str | None = None
            if over_a_cut_off_incumbent:
                # Nới **đúng một** bất biến, và chỉ sau khi bốn điều kiện được kiểm từ dữ liệu.
                # Mọi chốt chặn khác của hàm này — checksum khớp checkpoint, voice profile,
                # provenance của split / vocalization / delivery, yêu cầu cảm thụ — vẫn chạy
                # nguyên, vì chúng nói về **tính toàn vẹn**, không nói về ASR.
                #
                # Giữ trong cùng hàm chứ không nhân bản thành hàm thứ hai: một bản sao tám mươi
                # dòng sẽ lặng lẽ thiếu chốt chặn nào được thêm sau này, và đó là kiểu hỏng tệ
                # hơn hẳn kiểu mà bản sao ấy định tránh.
                substitution_reason = self._require_candidate_beats_a_cut_off_incumbent(
                    candidate,
                    segment,
                )
                promotable = promotable | {SEGMENT_CANDIDATE_DUAL_FAILED}
            if candidate_state not in promotable:
                raise RuntimeError("segment candidate cannot be promoted before both ASR decodes pass")
            if substitution_reason is not None:
                conn.execute(
                    "INSERT OR IGNORE INTO machine_take_substitutions "
                    "(segment_stable_id, incumbent_wav_sha256, candidate_wav_sha256, "
                    "reason, created_at) VALUES (?,?,?,?,?)",
                    (
                        str(segment["stable_id"]),
                        str(segment["wav_sha256"] or ""),
                        normalized_sha256,
                        substitution_reason,
                        time.time(),
                    ),
                )'''
assert OLD in s, "khong khop bat bien trang thai"
s = s.replace(OLD, NEW, 1)
write_atomic(p, s)
print("da va", p)

HELPER = """    def _promote_a_finished_take_over_a_cut_off_one(
        self,
        item: Any,
        segment_id: int,
        chapter_title: str,
    ) -> bool:
        \"\"\"Thay một bản thu bị cắt giữa câu bằng một ứng viên đã nói xong. True nếu thay.

        Chỉ chạy ở điểm **cạn ứng viên**, tức khi mọi vòng thu lại đã tiêu và đường ống sắp chốt
        lại đoạn này là hỏng. Ba ca trong 50.196 đoạn đã lưu rơi vào đây, và cả ba cùng một
        hình: đương nhiệm dài đúng 1,92 giây (12 khung x 160 ms) với `generation_ceiling_hit`,
        văn bản dưới ngưỡng ASR phán xử được, và trong số ứng viên bị vứt có bản **tự kết thúc**.

        Bốn điều kiện nằm ở `database`, không ở đây, và hàm tìm không ném. Đường ống chỉ **đề
        nghị**; tầng dữ liệu mới là nơi phán, và nó phán lại một lần nữa lúc thăng hạng.

        Mã cảnh báo ghi ra là `ASR_UNVERIFIABLE_SHORT_TEXT` - đó là sự thật về bản thu mới: nó
        hoàn chỉnh, sóng âm sạch, và **không ai xác minh được**. Mã ấy nằm trong
        `HIGH_QUALITY_ALLOWED_SEGMENT_WARNINGS` nên nó không chặn chương, còn việc thay được ghi
        riêng vào `machine_take_substitutions` để báo cáo không im lặng về nó.
        \"\"\"
        candidate = self.db.find_finished_take_over_a_cut_off_incumbent(
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
                reason="candidate failed signal validation immediately before substitution",
            )
            return False
        signal = self._segment_signal_provenance(candidate_item)
        codes = list(
            self._signal_warning_codes(
                signal,
                split_recovery=bool(signal.get("split_parts")),
            )
        )
        if ASR_UNVERIFIABLE_SHORT_TEXT not in codes:
            codes.append(ASR_UNVERIFIABLE_SHORT_TEXT)
        promoted = self.db.promote_segment_candidate(
            int(candidate["id"]),
            validated_wav_sha256=str(candidate["wav_sha256"]),
            repair_action="promote_finished_take_over_cut_off_incumbent",
            attempt=self._next_segment_quality_attempt(segment_id),
            warning_code="|".join(codes) or None,
            over_a_cut_off_incumbent=True,
        )
        if str(promoted["state"]) != SEGMENT_CANDIDATE_PROMOTED:
            return False
        self.log(
            f"Thay bản thu bị cắt của {item['stable_id']} bằng ứng viên vòng "
            f"{candidate['repair_round']} ({candidate['wav_duration']}s tự kết thúc); "
            "ASR không phán xử được văn bản này nên nó không xếp hạng được hai bản."
        )
        self.db.event(
            "warning",
            "SEGMENT_TAKE_SUBSTITUTED",
            f"Cut-off take replaced by a finished candidate for {item['stable_id']}",
            {
                "chapter": chapter_title,
                "segment_id": segment_id,
                "candidate_id": int(candidate["id"]),
                "repair_round": int(candidate["repair_round"]),
                "incumbent_duration": segment["wav_duration"],
                "candidate_duration": candidate["wav_duration"],
            },
        )
        return True

"""

CALLSITE = """                elif action == "exhausted":
                    # Trước khi chốt đoạn này là hỏng: có ứng viên nào bộ sinh đã **nói xong**
                    # không? Nhánh bên dưới lý luận đúng rằng trần khung là bằng chứng thật về
                    # đương nhiệm và văn bản ngắn không bào chữa được cho nó - nhưng nó không
                    # bao giờ hỏi câu ngược lại. Bốn điều kiện ở `database`; đây chỉ là một lần
                    # hỏi, và một lần hỏi ở đúng chỗ ba ca trong 50.196 đoạn đã dừng lại.
                    if self._promote_a_finished_take_over_a_cut_off_one(
                        item,
                        segment_id,
                        str(chapter["title"]),
                    ):
                        repair_targets.pop(segment_id, None)
                        progressed = True
                        continue
                    candidate_attempts = self.db.segment_candidate_attempt_summary(
                        segment_id,
                        self.quality_policy_hash,
                    )"""

# ============================================================ pipeline.py
p = root / "ebook_reader" / "pipeline.py"
s = io.open(p, encoding="utf-8").read()

OLD = """    def _segment_has_non_asr_failure_evidence(self, item: Any) -> bool:"""
NEW = HELPER + """    def _segment_has_non_asr_failure_evidence(self, item: Any) -> bool:"""
assert OLD in s, "khong khop cho chen helper pipeline"
s = s.replace(OLD, NEW, 1)

OLD = """                elif action == "exhausted":
                    candidate_attempts = self.db.segment_candidate_attempt_summary(
                        segment_id,
                        self.quality_policy_hash,
                    )"""
NEW = CALLSITE
assert OLD in s, "khong khop nhanh exhausted"
s = s.replace(OLD, NEW, 1)
write_atomic(p, s)
print("da va", p)

TEST_BODY = '"""Khi ASR không thể làm trọng tài, bản thu bộ sinh **nói xong** thắng bản bị **cắt**.\n\nBa ca trong 50.196 đoạn đã lưu, và cả ba cùng một hình: đương nhiệm dài đúng 1,92 giây\n(12 khung × 160 ms) với `generation_ceiling_hit`, văn bản dưới ngưỡng ASR phán xử được, và\ntrong số ứng viên bị vứt có bản tự kết thúc.\n\n```\nalpha.25 ch005  \'"Arghh..."\'\nalpha.60 ch021  \'"Tiếp theo."\'\nlo02     ch053  \'"Bất bại?"\'\n```\n\nBài này kiểm **bốn điều kiện** bằng row giả, vì đó là chỗ rủi ro nằm: mỗi điều kiện phải **tự\nmình** đủ để từ chối. Một chốt chặn bốn điều kiện mà chỉ có một bài test "đường thuận" thì ba\nđiều kiện kia có thể đã hỏng mà không ai biết.\n"""\nfrom __future__ import annotations\n\nfrom pathlib import Path\n\nimport pytest\n\nfrom ebook_reader.asr_contract import ASR_MIN_VERIFIABLE_CHARS\nfrom ebook_reader.config import build_settings\nfrom ebook_reader.database import (\n    SEGMENT_CANDIDATE_DUAL_FAILED,\n    SEGMENT_CANDIDATE_DUAL_PASSED,\n    ProjectDB,\n    _asr_only_failure_codes,\n)\nfrom ebook_reader.project import create_or_open_project\n\nCUT_OFF = {"generation_ceiling_hit": 1.0}\nFINISHED: dict[str, float] = {}\n\n\ndef _gate() -> ProjectDB:\n    """Chỉ cần `_json_object`, nên không dựng project thật cho phần kiểm điều kiện."""\n    return object.__new__(ProjectDB)\n\n\ndef _row(**fields):\n    import json\n\n    base = {\n        "id": 7,\n        "stable_id": "c00024_s0000078_0bab1636c786",\n        "wav_duration": 1.92,\n        "repair_round": 1,\n        "text": \'"Bất bại?"\',\n        "failure_reason": "beam=ASR_MISMATCH; greedy=ASR_MISMATCH",\n        "signal_json": json.dumps(CUT_OFF),\n    }\n    base.update(fields)\n    if isinstance(base["signal_json"], dict):\n        base["signal_json"] = json.dumps(base["signal_json"])\n    return base\n\n\ndef _check(gate, *, segment_over=None, candidate_over=None):\n    segment = _row(**(segment_over or {}))\n    candidate = _row(\n        **{\n            "wav_duration": 0.8,\n            "signal_json": FINISHED,\n            **(candidate_over or {}),\n        }\n    )\n    return gate._require_candidate_beats_a_cut_off_incumbent(candidate, segment)\n\n\ndef test_the_real_case_passes_the_gate() -> None:\n    """Chương 053 của lô 2, đúng như dữ liệu ghi lại."""\n    reason = _check(_gate())\n\n    assert "chạm trần" in reason\n    assert "tự kết thúc" in reason\n    assert str(ASR_MIN_VERIFIABLE_CHARS) in reason\n\n\ndef test_it_refuses_when_the_incumbent_finished() -> None:\n    """Điều kiện quan trọng nhất: không có nó thì đây là thay một bản thu tốt.\n\n    Đo trên 50.196 đoạn: 469 đoạn có văn bản ngắn và có ứng viên mà đương nhiệm **không** chạm\n    trần. Bỏ điều kiện này là trao quyền thay thế cho bốn trăm chỗ chẳng cần thay.\n    """\n    with pytest.raises(RuntimeError) as caught:\n        _check(_gate(), segment_over={"signal_json": FINISHED})\n\n    assert "đương nhiệm không chạm trần khung" in str(caught.value)\n\n\ndef test_it_refuses_when_the_candidate_was_also_cut_off() -> None:\n    with pytest.raises(RuntimeError) as caught:\n        _check(_gate(), candidate_over={"signal_json": CUT_OFF})\n\n    assert "ứng viên cũng chạm trần khung" in str(caught.value)\n\n\ndef test_it_refuses_when_asr_could_have_judged_the_text() -> None:\n    """Văn bản đủ dài thì ASR **có** ý kiến, và "ứng viên trượt ASR" là bằng chứng thật."""\n    long_enough = "Tôi nhếch mép và không nói gì thêm."\n    assert sum(ch.isalnum() for ch in long_enough) >= ASR_MIN_VERIFIABLE_CHARS\n\n    with pytest.raises(RuntimeError) as caught:\n        _check(_gate(), segment_over={"text": long_enough})\n\n    assert "văn bản đủ dài để ASR phán xử" in str(caught.value)\n\n\ndef test_it_refuses_a_candidate_that_failed_outside_asr() -> None:\n    """Một cờ sóng âm nói bản thu hỏng theo cách nhìn thấy được mà không cần phiên âm."""\n    with pytest.raises(RuntimeError) as caught:\n        _check(\n            _gate(),\n            candidate_over={\n                "failure_reason": "beam=ASR_MISMATCH; blocking_signal=TTS_CLIPPING"\n            },\n        )\n\n    assert "ứng viên trượt bằng mã ngoài ASR" in str(caught.value)\n\n\ndef test_it_refuses_a_candidate_with_no_recorded_reason() -> None:\n    """Không biết vì sao nó trượt thì không được thay - im lặng không phải một cái cớ."""\n    with pytest.raises(RuntimeError):\n        _check(_gate(), candidate_over={"failure_reason": ""})\n\n\ndef test_every_clause_is_named_separately() -> None:\n    """Bốn điều kiện phải hỏng riêng lẻ, không gộp sau một câu thông báo chung.\n\n    Đây là luật của repo (`require_all`, ghim bằng `test_no_new_blind_compound_check_is_added`)\n    và nó đã bắt tôi một lần khi tôi bê nguyên dáng `if a or b or c` sang chỗ khác.\n    """\n    messages = []\n    for over in (\n        {"segment_over": {"signal_json": FINISHED}},\n        {"candidate_over": {"signal_json": CUT_OFF}},\n        {"segment_over": {"text": "Một câu dài hơn ngưỡng ASR nhiều."}},\n        {"candidate_over": {"failure_reason": "beam=ASR_MISMATCH; blocking_signal=X_Y"}},\n    ):\n        with pytest.raises(RuntimeError) as caught:\n            _check(_gate(), **over)\n        messages.append(str(caught.value))\n\n    assert len(set(messages)) == 4, "bốn điều kiện phải cho bốn thông báo khác nhau"\n\n\ndef test_only_asr_codes_count_as_uninformative() -> None:\n    assert _asr_only_failure_codes("beam=ASR_MISMATCH; greedy=ASR_MISMATCH") == {\n        "ASR_MISMATCH"\n    }\n    assert _asr_only_failure_codes("beam=ASR_MISMATCH; blocking_signal=TTS_X") is None\n    assert _asr_only_failure_codes("") is None\n    assert _asr_only_failure_codes(None) is None\n\n\ndef test_the_finder_picks_the_lowest_round(monkeypatch: pytest.MonkeyPatch) -> None:\n    """Giữa hai bản thu hoàn chỉnh mà ASR không phán xử được, không có gì để xếp hạng.\n\n    Nên quy tắc là tất định và nhàm chán: vòng nhỏ nhất. Bài này cũng ghim rằng ứng viên\n    `dual_passed` **không** đi qua đường này - đường bình thường lo chúng.\n    """\n    gate = _gate()\n    segment = _row()\n    candidates = [\n        _row(id=1, repair_round=3, wav_duration=0.72, signal_json=FINISHED),\n        _row(id=2, repair_round=1, wav_duration=0.80, signal_json=FINISHED),\n        _row(id=3, repair_round=0, wav_duration=0.96, signal_json=CUT_OFF),\n    ]\n    for candidate in candidates:\n        candidate["state"] = SEGMENT_CANDIDATE_DUAL_FAILED\n    monkeypatch.setattr(ProjectDB, "get_segment", lambda self, _id: segment)\n    monkeypatch.setattr(\n        ProjectDB,\n        "list_segment_candidates",\n        lambda self, **_kwargs: candidates,\n    )\n\n    chosen = gate.find_finished_take_over_a_cut_off_incumbent(7, "policy")\n\n    assert chosen is not None\n    assert int(chosen["repair_round"]) == 1, "vòng 0 chạm trần nên phải bị bỏ qua"\n\n\ndef test_the_finder_ignores_candidates_that_already_passed(\n    monkeypatch: pytest.MonkeyPatch,\n) -> None:\n    gate = _gate()\n    segment = _row()\n    candidate = _row(id=2, repair_round=1, signal_json=FINISHED)\n    candidate["state"] = SEGMENT_CANDIDATE_DUAL_PASSED\n    monkeypatch.setattr(ProjectDB, "get_segment", lambda self, _id: segment)\n    monkeypatch.setattr(\n        ProjectDB, "list_segment_candidates", lambda self, **_kwargs: [candidate]\n    )\n\n    assert gate.find_finished_take_over_a_cut_off_incumbent(7, "policy") is None\n\n\ndef test_the_table_exists_and_the_accessor_reads_it(tmp_path: Path) -> None:\n    """Bảng phải thật sự có trong schema, không chỉ có trong bản vá.\n\n    Phần kiểm điều kiện ở trên dùng row giả nên nó không chạm vào SQL. Bài này chạm, vì một câu\n    INSERT sai chính tả sẽ chỉ nổ lúc chạy thật - và chạy thật là giữa một lô mười ba giờ.\n    """\n    tmp_path.mkdir(parents=True, exist_ok=True)\n    source = tmp_path / "001.txt"\n    source.write_text("Một câu để mở project.", encoding="utf-8")\n    _paths, db, _settings = create_or_open_project(\n        [source], tmp_path / "out", build_settings(), "Take substitution"\n    )\n\n    assert db.list_take_substitutions() == []\n\n    with db.transaction() as conn:\n        conn.execute(\n            "INSERT INTO machine_take_substitutions "\n            "(segment_stable_id, incumbent_wav_sha256, candidate_wav_sha256, reason, created_at)"\n            " VALUES (?,?,?,?,?)",\n            ("c1s1", "a" * 64, "b" * 64, "lý do", 1.0),\n        )\n\n    rows = db.list_take_substitutions()\n    assert len(rows) == 1\n    assert rows[0]["reason"] == "lý do"\n'

TEST = TEST_BODY
q = root / "tests" / "test_finished_take_beats_a_cut_off_one.py"
write_atomic(q, TEST)
print("da tao", q)
