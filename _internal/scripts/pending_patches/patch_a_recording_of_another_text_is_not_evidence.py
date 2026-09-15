"""Va recovery.py + pipeline.py: `cli run` tu chua duoc lech chuoi noi, khong cho ai nho chay script.

Chay: python patch_a_recording_of_another_text_is_not_evidence.py <root>

## Cai gia da mat

10:26 ngay 14-09, lo 1 cuon 2 chet o 25/49 chuong. Mot ban va doi `spoken_symbols_to_words` ("+"
doc thanh "cong"), va doan cong thuc duy nhat cua lo (chuong 025, `c00026_s0000015`) co san mot
ban thu duoc lam tu chuoi CU. `pipeline._spoken_text_and_anchors` bam lai chuoi tu ma hien tai,
so voi `signal_json.spoken_text_sha256`, va nem:

    RuntimeError: spoken-text checksum drifted before candidate or final verification
    -> UNRECOVERABLE_PIPELINE_ERROR

Cong kiem ay DUNG: van ban da doi thi ban thu cu khong con la ban thu cua van ban nay. Cai thieu
la mot duong chua. `scripts/resync_spoken_text.py` (14-09) dat lai dung nhung doan ay ve cho thu,
va bay gio bon cho goi no: `boundary.sh` buoc 0 va buoc 2b, `launch_batch.sh`, `launch_repair.sh`.

**Nhung bon cho goi mot script la bon cho co the quen.** `cli run` goi tay - thu chu sach lam,
thu toi lam khi vet mot chuong - khong di qua cho nao trong so ay. Va lop loi nay im: no chi noi
ra khi doan ay tinh den luot thu, tuc giua lo, tuc sau khi GPU da chay hang gio.

## Chua o dau

`recovery.recover_project` DA hoi dung cau hoi nay ba lan cho moi doan co ban thu:

    WAV con do khong? checksum con khop khong? co ban ghi QA theo policy dang hieu luc khong?

Tat ca deu la mot cau: *bang chung nay con noi ve van ban nay khong?* Lech chuoi noi cung ho, va
cung mot cach chua (`reset_segment_pending`). Cho dung la vong ay.

Khong tu viet lai phep dan chuoi: recovery nhan mot **ham hoi** (`spoken_text_drifted`) do
`pipeline._recover` truyen vao, tro thang tai `_spoken_text_and_anchors` ma duong ong dung. Mot
ban sao cua luat bam o recovery se lech khoi ban that dung vao ngay co ban va ke tiep - va ngay
ay chinh la ngay phep kiem nay can dung.

`reset_segment_pending` chu khong `requeue_segment_for_asr`: requeue GIU ban thu va bat ASR doc
lai no, tuc di thang vao dung cai `RuntimeError` ay lan nua.

## So lieu (do 03:50 ngay 2026-09-16, khong phai phong doan)

Phep dan chuoi cho **3.705 doan** cua lo 1 (moi doan deu co ban thu):

    script chay het               2,54 giay
    rieng phan import              1,15 giay
    -> phep quet                  ~1,4 giay, tuc ~0,38 ms moi doan

Recovery hien tai mat ~6,8 phut cho mot lo. Vay phep kiem them **~0,3%**. Con so "~40 giay" toi
tung ghi trong hang cho va trong chu thich `boundary.sh` la SAI - do khong phai do, va neu de no
dung do se la ly do mot nguoi sau nay khong dam dat phep kiem vao day. Da sua ca hai cho.

## Cho KHONG dat vao

Duong tat "project da completed va MP3 da tham tra" (`report.completed_verified`) tra ve som va
khong chay vong doan. De nguyen, co y: mot lo da xong, da tag, da ghep thi ban thu la bang chung
DA DONG - dat lai mot doan o do lam chuong mat tu cach xuat ban ma chang ai thu lai (project ay
khong chay nua). Do cung la ly do `resync_spoken_text.py` khong co `--all`.

## Khi phep dan chuoi that bai vi ly do KHAC

`_spoken_text_drifted` tra `False` va ghi mot su kien `SPOKEN_TEXT_DRIFT_CHECK_FAILED`. Khong nem:
mot loi la (thieu cach doc, du lieu la) khong duoc phep lam moi lo khong khoi dong duoc, va duong
ong van xu ly no tung doan nhu truoc. Nhung cung khong im - mot danh sach bi cat ngan trong im
lang la mot danh sach noi doi.
"""
import io
import sys
from pathlib import Path

root = Path(sys.argv[1])

# ---------------------------------------------------------------- 1. pipeline.py
p = root / "ebook_reader" / "pipeline.py"
s = io.open(p, encoding="utf-8").read()

OLD_CONST = '''QUALITY_VERDICT_REPAIR = "repair"
SEGMENT_CANDIDATE_DIRECTORY = "candidates"'''
NEW_CONST = '''QUALITY_VERDICT_REPAIR = "repair"
# Một cái tên cho lời của phép kiểm chuỗi nói, vì hai chỗ khác phải NHẬN RA nó: `_spoken_text_drifted`
# ở dưới, và `scripts/resync_spoken_text.py`. Một bản sao chuỗi ký tự ở mỗi chỗ là ba chỗ để lệch.
SPOKEN_TEXT_DRIFT_MESSAGE = (
    "spoken-text checksum drifted before candidate or final verification"
)
SEGMENT_CANDIDATE_DIRECTORY = "candidates"'''
assert s.count(OLD_CONST) == 1, "khong khop khoi hang so QUALITY_VERDICT_REPAIR"
s = s.replace(OLD_CONST, NEW_CONST, 1)

OLD_RAISE = '''        if expected_sha256 and spoken_text_sha256 != expected_sha256:
            raise RuntimeError(
                "spoken-text checksum drifted before candidate or final verification"
            )
        return spoken_text, anchors
'''
NEW_RAISE = '''        if expected_sha256 and spoken_text_sha256 != expected_sha256:
            raise RuntimeError(SPOKEN_TEXT_DRIFT_MESSAGE)
        return spoken_text, anchors

    def _spoken_text_drifted(self, row: Any) -> bool:
        """Bản thu của đoạn này có còn là bản thu của CHUỖI NÓI hiện tại không?

        Cùng một câu hỏi mà recovery đã hỏi ba lần (WAV còn đó, checksum còn khớp, QA còn hiệu
        lực), và recovery gọi hàm này để hỏi lần thứ tư - xem `recover_project`. Nó gọi thẳng
        `_spoken_text_and_anchors`, tức đúng phép dẫn chuỗi mà đường ống dùng: một bản sao của
        luật băm ở tầng recovery sẽ lệch khỏi bản thật đúng vào ngày có bản vá kế tiếp.

        Lỗi KHÁC thì trả `False` và ghi sổ. Một cách đọc thiếu hay một dữ liệu lạ không được phép
        làm cả lô không khởi động được; đường ống vẫn xử lý nó từng đoạn như trước.
        """
        item = dict(row)
        try:
            self._spoken_text_and_anchors(item)
        except RuntimeError as exc:
            if SPOKEN_TEXT_DRIFT_MESSAGE in str(exc):
                return True
            self._report_spoken_text_check_error(item, exc)
        except Exception as exc:  # noqa: BLE001 - xem docstring: không được nổ ở đây
            self._report_spoken_text_check_error(item, exc)
        return False

    def _report_spoken_text_check_error(self, item: dict[str, Any], exc: Exception) -> None:
        self.db.event(
            "warning",
            "SPOKEN_TEXT_DRIFT_CHECK_FAILED",
            "Recovery could not derive the spoken text for this segment; left it untouched",
            {
                "stable_id": str(item.get("stable_id") or ""),
                "error": f"{type(exc).__name__}: {exc}",
            },
        )
'''
assert s.count(OLD_RAISE) == 1, "khong khop cho nem cua _spoken_text_and_anchors"
s = s.replace(OLD_RAISE, NEW_RAISE, 1)

OLD_CALL = '''        report = recover_project(self.paths, self.db, self.settings)
        self._completed_noop = report.completed_verified
        if (
            report.reset_in_progress
            or report.reset_missing_or_corrupt
            or report.removed_part_files
        ):
            self.log(
                "Recovery: "
                f"giữ {report.recovered_verified} đoạn; "
                f"reset {report.reset_in_progress + report.reset_missing_or_corrupt} đoạn; "
                f"xóa {report.removed_part_files} file tạm."
            )'''
NEW_CALL = '''        report = recover_project(
            self.paths,
            self.db,
            self.settings,
            spoken_text_drifted=self._spoken_text_drifted,
        )
        self._completed_noop = report.completed_verified
        if (
            report.reset_in_progress
            or report.reset_missing_or_corrupt
            or report.reset_spoken_text_drift
            or report.removed_part_files
        ):
            self.log(
                "Recovery: "
                f"giữ {report.recovered_verified} đoạn; "
                f"reset {report.reset_in_progress + report.reset_missing_or_corrupt} đoạn; "
                f"đặt lại {report.reset_spoken_text_drift} đoạn lệch chuỗi nói; "
                f"xóa {report.removed_part_files} file tạm."
            )'''
assert s.count(OLD_CALL) == 1, "khong khop cho goi recover_project trong _recover"
s = s.replace(OLD_CALL, NEW_CALL, 1)

io.open(p, "w", encoding="utf-8", newline="\n").write(s)
print(f"da va {p}")

# ---------------------------------------------------------------- 2. recovery.py
p = root / "ebook_reader" / "recovery.py"
s = io.open(p, encoding="utf-8").read()

OLD_IMPORT = '''from dataclasses import dataclass, field
from pathlib import Path'''
NEW_IMPORT = '''from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path'''
assert s.count(OLD_IMPORT) == 1, "khong khop khoi import cua recovery.py"
s = s.replace(OLD_IMPORT, NEW_IMPORT, 1)

OLD_FIELDS = '''    stale_candidates: int = 0
    invalidated_candidates: int = 0'''
NEW_FIELDS = '''    stale_candidates: int = 0
    invalidated_candidates: int = 0
    reset_spoken_text_drift: int = 0'''
assert s.count(OLD_FIELDS) == 1, "khong khop cac truong cuoi cua RecoveryReport"
s = s.replace(OLD_FIELDS, NEW_FIELDS, 1)

OLD_SIGNATURE = '''def recover_project(paths: ProjectPaths, db: ProjectDB, settings: dict) -> RecoveryReport:'''
NEW_SIGNATURE = '''def recover_project(
    paths: ProjectPaths,
    db: ProjectDB,
    settings: dict,
    *,
    spoken_text_drifted: Callable[[dict], bool] | None = None,
) -> RecoveryReport:'''
assert s.count(OLD_SIGNATURE) == 1, "khong khop chu ky recover_project"
s = s.replace(OLD_SIGNATURE, NEW_SIGNATURE, 1)

OLD_SEGMENT_LOOP = '''        if valid:
            status = str(row["status"])
            quality_ok = _segment_has_current_audio_qa('''
NEW_SEGMENT_LOOP = '''        if valid and spoken_text_drifted is not None and spoken_text_drifted(row):
            # Bản thu còn nguyên, checksum còn khớp - nhưng nó được làm từ một CHUỖI NÓI khác
            # (một bản vá đã đổi `spoken_symbols_to_words` / chuẩn hoá tiếng / phiên âm). Cùng
            # một họ với "WAV mất" ở dưới: bằng chứng không còn nói về văn bản này.
            #
            # `reset_segment_pending` chứ không `requeue_segment_for_asr`: requeue giữ bản thu và
            # bắt ASR đọc lại nó, tức đi thẳng vào đúng `RuntimeError` ấy lần nữa - và lần này ở
            # giữa lô, sau hàng giờ GPU. Xem `pipeline._spoken_text_drifted`.
            db.reset_segment_pending(
                int(row["id"]),
                "Recovery found a recording made from a different spoken text",
            )
            report.reset_spoken_text_drift += 1
        elif valid:
            status = str(row["status"])
            quality_ok = _segment_has_current_audio_qa('''
assert s.count(OLD_SEGMENT_LOOP) == 1, "khong khop dau vong doan cua recovery"
s = s.replace(OLD_SEGMENT_LOOP, NEW_SEGMENT_LOOP, 1)

OLD_EVENT = '''            "invalidated_candidates": report.invalidated_candidates,'''
NEW_EVENT = '''            "invalidated_candidates": report.invalidated_candidates,
            "reset_spoken_text_drift": report.reset_spoken_text_drift,'''
assert s.count(OLD_EVENT) == 1, "khong khop so lieu RECOVERY_SCAN"
s = s.replace(OLD_EVENT, NEW_EVENT, 1)

io.open(p, "w", encoding="utf-8", newline="\n").write(s)
print(f"da va {p}")

# ---------------------------------------------------------------- 3. resync_spoken_text.py
# Script khong phai file khoa, nhung chuoi loi thi phai la MOT chuoi: no vua duoc dat ten.
p = root / "scripts" / "resync_spoken_text.py"
s = io.open(p, encoding="utf-8").read()

OLD_MESSAGE = '''DRIFT_MESSAGE = "spoken-text checksum drifted"'''
NEW_MESSAGE = '''# Cùng một chuỗi với `pipeline.SPOKEN_TEXT_DRIFT_MESSAGE`, nhập từ đó chứ không chép lại: hai
# bản sao là hai chỗ để lệch, và ngày chúng lệch là ngày phép so này im lặng bỏ sót mọi đoạn.
DRIFT_MESSAGE = SPOKEN_TEXT_DRIFT_MESSAGE'''
assert s.count(OLD_MESSAGE) == 1, "khong khop DRIFT_MESSAGE trong resync_spoken_text.py"
s = s.replace(OLD_MESSAGE, NEW_MESSAGE, 1)

OLD_PIPELINE_IMPORT = '''from ebook_reader.pipeline import BookPipeline  # noqa: E402'''
NEW_PIPELINE_IMPORT = '''from ebook_reader.pipeline import (  # noqa: E402
    SPOKEN_TEXT_DRIFT_MESSAGE,
    BookPipeline,
)'''
assert s.count(OLD_PIPELINE_IMPORT) == 1, "khong khop import BookPipeline"
s = s.replace(OLD_PIPELINE_IMPORT, NEW_PIPELINE_IMPORT, 1)

io.open(p, "w", encoding="utf-8", newline="\n").write(s)
print(f"da va {p}")

# Phan sua chu thich `boundary.sh` DA BI RUT khoi ban va nay (05:55 ngay 16-09): chinh
# `boundary.sh` la thu chay `apply_all.py`, va bash doc script dan dan theo offset file - sua mot
# .sh dang chay co the lam lech offset va cat mot dong lam hai. Con so da duoc sua bang mot commit
# binh thuong luc khong co ranh gioi nao chay. Dung them lai vao day.

# ---------------------------------------------------------------- 5. bai kiem
TEST = '''"""Một bản thu được làm từ chuỗi nói KHÁC thì recovery phải đặt lại, không giữ.

`pipeline._spoken_text_and_anchors` băm lại chuỗi giao cho TTS từ mã **hiện tại** và so với
`signal_json.spoken_text_sha256` ghi kèm bản thu. Lệch thì nó ném, và `UNRECOVERABLE_PIPELINE_ERROR`
làm chết cả lô - lô 1 cuốn 2, 10:26 ngày 14-09, chết ở 25/49 vì một đoạn công thức.

Cổng ấy đúng. Cái thiếu là đường chữa **tự động**: `scripts/resync_spoken_text.py` chữa được, nhưng
nó phải được ai đó gọi, và `cli run` gõ tay không đi qua chỗ nào gọi nó. Recovery thì đi qua mọi
lượt `run`, và nó đã hỏi đúng ba câu cùng họ cho từng đoạn có bản thu (WAV còn đó? checksum còn
khớp? QA còn hiệu lực?). Đây là câu thứ tư.

Vì sao truyền một HÀM vào chứ không tự kiểm trong recovery: luật băm chuỗi nói nằm trong đường ống,
và một bản sao của nó ở tầng recovery sẽ lệch khỏi bản thật đúng vào ngày có bản vá kế tiếp - ngày
mà phép kiểm này cần đúng nhất.
"""
from __future__ import annotations

import inspect
from pathlib import Path

import numpy as np

from ebook_reader.audio_io import atomic_write_wav
from ebook_reader.pipeline import SPOKEN_TEXT_DRIFT_MESSAGE, BookPipeline
from ebook_reader.recovery import recover_project
from tests.test_recovery import setup_db


class _Db:
    """Chỉ đủ để nhận sổ: `_spoken_text_drifted` không chạm gì khác của pipeline."""

    def __init__(self) -> None:
        self.events: list[tuple[str, str, str, dict]] = []

    def event(self, level: str, code: str, message: str, payload: dict) -> None:
        self.events.append((level, code, message, payload))


class _Pipeline(BookPipeline):
    """Không gọi `BookPipeline.__init__` - bài này chỉ hỏi về một phép dẫn chuỗi đã thay."""

    def __init__(self, exception: Exception | None) -> None:
        self.db = _Db()
        self._exception = exception

    def _spoken_text_and_anchors(self, item: dict) -> tuple[str, list]:
        if self._exception is not None:
            raise self._exception
        return "Xin chào", []


def _recorded(paths, db, settings, row):
    """Một đoạn có bản thu hợp lệ: đúng lối `test_recovery` dựng."""
    wav = paths.chunks / "c.wav"
    audio = np.sin(np.linspace(0, 30, 48000, dtype=np.float32)) * 0.1
    checksum, metrics = atomic_write_wav(wav, audio, 48000, row["text"], settings)
    db.mark_signal_passed(
        int(row["id"]),
        wav_path=wav,
        wav_sha256=checksum,
        duration=metrics["duration"],
        signal=metrics,
    )
    return wav


def test_a_drifted_recording_goes_back_to_pending(tmp_path: Path) -> None:
    paths, settings, db, row = setup_db(tmp_path)
    _recorded(paths, db, settings, row)

    asked: list[str] = []

    def drifted(segment) -> bool:
        asked.append(str(segment["stable_id"]))
        return True

    report = recover_project(paths, db, settings, spoken_text_drifted=drifted)

    assert asked == ["c1s1"], "phép kiểm phải được hỏi cho đúng đoạn có bản thu"
    assert report.reset_spoken_text_drift == 1
    fresh = db.list_segments()[0]
    assert fresh["status"] == "pending"
    assert not fresh["wav_sha256"], "bằng chứng của bản thu cũ phải đi cùng nó"


def test_a_recording_that_still_matches_is_kept(tmp_path: Path) -> None:
    paths, settings, db, row = setup_db(tmp_path)
    _recorded(paths, db, settings, row)

    report = recover_project(paths, db, settings, spoken_text_drifted=lambda _row: False)

    assert report.reset_spoken_text_drift == 0
    assert db.list_segments()[0]["status"] == "signal_passed"


def test_no_callable_means_exactly_the_old_behaviour(tmp_path: Path) -> None:
    """Chỗ gọi nào chưa truyền hàm hỏi thì recovery cư xử y như trước - không im lặng đặt lại."""
    paths, settings, db, row = setup_db(tmp_path)
    _recorded(paths, db, settings, row)

    report = recover_project(paths, db, settings)

    assert report.reset_spoken_text_drift == 0
    assert db.list_segments()[0]["status"] == "signal_passed"


def test_the_drift_message_is_what_the_pipeline_actually_raises() -> None:
    """Một chuỗi, một chỗ: phép so `in str(exc)` chỉ đúng khi nó so với chính lời được ném."""
    source = inspect.getsource(BookPipeline._spoken_text_and_anchors)

    assert "raise RuntimeError(SPOKEN_TEXT_DRIFT_MESSAGE)" in source
    assert "drifted" in SPOKEN_TEXT_DRIFT_MESSAGE


def test_the_drift_error_is_read_as_drift() -> None:
    pipeline = _Pipeline(RuntimeError(SPOKEN_TEXT_DRIFT_MESSAGE))

    assert pipeline._spoken_text_drifted({"stable_id": "c1s1"}) is True
    assert pipeline.db.events == [], "lệch chuỗi nói là chuyện recovery ghi sổ, không phải ở đây"


def test_another_error_does_not_stop_the_batch_and_does_not_go_quiet() -> None:
    """Một cách đọc thiếu không được phép làm cả lô không khởi động được - nhưng phải để lại dấu."""
    for exception in (RuntimeError("thiếu cách đọc cho 'Hearthmeer'"), KeyError("voice_key")):
        pipeline = _Pipeline(exception)

        assert pipeline._spoken_text_drifted({"stable_id": "c1s1"}) is False
        assert [event[1] for event in pipeline.db.events] == ["SPOKEN_TEXT_DRIFT_CHECK_FAILED"]
        payload = pipeline.db.events[0][3]
        assert payload["stable_id"] == "c1s1"
        assert type(exception).__name__ in payload["error"]


def test_a_matching_recording_is_not_asked_twice() -> None:
    pipeline = _Pipeline(None)

    assert pipeline._spoken_text_drifted({"stable_id": "c1s1"}) is False
    assert pipeline.db.events == []


def test_the_pipeline_hands_recovery_its_own_ruler() -> None:
    """Nếu `_recover` quên truyền hàm hỏi thì mọi bài trên vẫn xanh mà sản xuất vẫn chết."""
    source = inspect.getsource(BookPipeline._recover)

    assert "spoken_text_drifted=self._spoken_text_drifted" in source
    assert "reset_spoken_text_drift" in source, "số đoạn bị đặt lại phải hiện trong log recovery"
'''
t = root / "tests" / "test_a_recording_of_another_text_is_not_evidence.py"
t.write_text(TEST, encoding="utf-8", newline="\n")
print(f"da tao {t}")
