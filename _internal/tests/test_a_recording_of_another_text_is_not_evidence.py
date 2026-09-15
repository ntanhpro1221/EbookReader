"""Một bản thu được làm từ chuỗi nói KHÁC thì recovery phải đặt lại, không giữ.

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
