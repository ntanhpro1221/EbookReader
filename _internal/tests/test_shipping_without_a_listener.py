"""Máy tự cho qua khi ASR là nhân chứng duy nhất - và chỉ khi đó.

Chủ sách ra lệnh 2026-09-07: *"tôi không muốn phải tự nghe, project phải hoạt động toàn bộ
cho ra sản phẩm"*. Trước lệnh ấy, một đoạn mà ASR không đọc nổi chặn chương của nó vĩnh
viễn: vòng sửa cạn, cảnh báo không ai gỡ được, và lối thoát duy nhất - `accept` - đòi một
người ngồi nghe. Bức tường thứ chín của đúng hình dạng ấy kể từ alpha.25.

Đo trên tám đoạn chặn của alpha.60 thì thấy chúng chia làm hai nhóm rõ rệt, và cả cơ chế
này là cách viết lại ranh giới ấy thành code:

  sáu đoạn  không có **một tín hiệu nào** từ bộ sinh nói bản thu hỏng. `"Gia tộc Remis,"`
            nghe ra `"Gia tộc dây mít"` với sim 0,94; `"Golem Silian"` ra `"go lem xí lên"`.
            Lỗi phiên âm, không phải lỗi đọc, và năm vòng thu lại không đổi gì.
  hai đoạn  mang `generation_ceiling_hit=1.0` - bộ sinh tự khai nó chạy hết khung mà chưa
            dừng. `"Gì cơ?"` dài 1,92 giây và Whisper nghe ra `"Các bạn hãy đăng ký kênh để
            ủng hộ kênh của mình nhé"`. Ở đây có nhân chứng thứ hai, và máy phải im.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from ebook_reader.config import build_settings
from ebook_reader.project import create_or_open_project

ANCHOR = "ASR_LOCKED_NAME_ANCHOR_MISMATCH"
PERCEPTUAL = "PERCEPTUAL_NATURALNESS_REVIEW"


def _db(tmp_path: Path):
    source = tmp_path / "001.txt"
    source.write_text("Một câu để mở project.", encoding="utf-8")
    _paths, db, _settings = create_or_open_project(
        [source], tmp_path / "out", build_settings(), "May tu cho qua"
    )
    return db


# --------------------------------------------------------------------- nguồn gốc


def test_a_machine_acceptance_is_never_reported_as_a_person_having_listened(tmp_path) -> None:
    """Cái đắt nhất của thiết kế này, và lý do hai bảng chứ không một cột `source`.

    Quên union bảng máy thì một chương bị chặn oan - ồn ào, thấy ngay. Quên lọc một cột
    `source` thì báo cáo nói "người đã nghe" về bản thu chưa ai nghe: im lặng, và là nói dối
    chủ sách về đúng thứ ông ấy uỷ quyền.
    """
    db = _db(tmp_path)
    db.accept_segment_audio_as_machine(
        segment_stable_id="c00003_s0000001",
        wav_sha256="ABC123",
        warning_code=ANCHOR,
        reason="ASR là nhân chứng duy nhất",
    )

    assert db.accepted_segment_warnings() == {}, (
        "`accepted_` phải giữ nguyên nghĩa 'một người đã nghe' - mọi báo cáo đọc nó"
    )
    assert db.ruled_segment_warnings() == {("c00003_s0000001", "abc123"): {ANCHOR}}


def test_the_two_sources_add_up_rather_than_shadowing_each_other(tmp_path) -> None:
    db = _db(tmp_path)
    db.accept_segment_audio(
        segment_stable_id="c1s1", wav_sha256="aa", warning_code=PERCEPTUAL
    )
    db.accept_segment_audio_as_machine(
        segment_stable_id="c1s1", wav_sha256="aa", warning_code=ANCHOR, reason="vì thế"
    )

    assert db.ruled_segment_warnings()[("c1s1", "aa")] == {PERCEPTUAL, ANCHOR}
    assert db.ruled_segment_takes() == {("c1s1", "aa")}


def test_recutting_the_take_voids_a_machine_acceptance_too(tmp_path) -> None:
    """Khoá theo checksum như phán quyết của người: chấp nhận là chấp nhận một bản thu."""
    db = _db(tmp_path)
    db.accept_segment_audio_as_machine(
        segment_stable_id="c1s1", wav_sha256="cu", warning_code=ANCHOR, reason="vì thế"
    )
    ruled = db.ruled_segment_warnings()

    assert ruled.get(("c1s1", "cu")) == {ANCHOR}
    assert ruled.get(("c1s1", "moi")) is None


def test_a_machine_acceptance_must_say_why(tmp_path) -> None:
    """Ràng buộc thứ ba của thiết kế - không im lặng - có răng ở tầng ghi, không ở tầng gọi.

    Lý do đi thẳng vào báo cáo. Một hàng trống ở đây là một dòng báo cáo nói "máy đã cho
    qua" mà không nói được vì sao, và chủ sách không kiểm lại được gì.
    """
    db = _db(tmp_path)
    with pytest.raises(ValueError):
        db.accept_segment_audio_as_machine(
            segment_stable_id="c1s1", wav_sha256="aa", warning_code=ANCHOR, reason="   "
        )
    assert db.ruled_segment_warnings() == {}


def test_every_acceptance_is_listed_with_its_reason_and_timestamp(tmp_path) -> None:
    db = _db(tmp_path)
    db.accept_segment_audio_as_machine(
        segment_stable_id="c1s1",
        wav_sha256="aa",
        warning_code=ANCHOR,
        reason="nghe ra 'Gia tộc dây mít'",
    )
    (row,) = db.list_machine_acceptances()

    assert row["segment_stable_id"] == "c1s1"
    assert "dây mít" in row["reason"]
    assert float(row["created_at"]) > 0


# ------------------------------------------------------------------ ai được cho qua


class _Row(dict):
    """Đủ giống `sqlite3.Row` cho hàm cấp phép: truy cập theo tên cột."""


def _segment(**overrides) -> _Row:
    row = _Row(
        {
            "id": 1,
            "stable_id": "c00003_s0000093",
            "status": "failed",
            "warning_code": ANCHOR,
            "wav_sha256": "abc",
            "text": '"Gia tộc Remis,"',
            "asr_text": "Gia tộc dây mít",
            "signal_json": json.dumps({"rms": 0.053, "trailing_rms": 1.2e-05}),
        }
    )
    row.update(overrides)
    return row


class _FakeDB:
    def __init__(self, rows: list[_Row]) -> None:
        self._rows = rows
        self.accepted: list[dict] = []
        self.events: list[tuple] = []

    def list_segments(self, chapter_id: int) -> list[_Row]:
        return self._rows

    def ruled_segment_warnings(self) -> dict:
        return {
            (item["segment_stable_id"], item["wav_sha256"]): {item["warning_code"]}
            for item in self.accepted
        }

    def accept_segment_audio_as_machine(self, **kwargs) -> bool:
        assert kwargs["reason"].strip(), "lý do là bắt buộc"
        self.accepted.append(kwargs)
        return True

    def event(self, level, code, message, details=None) -> None:
        self.events.append((level, code, message))


def _grant(rows: list[_Row]) -> tuple[list[dict], _FakeDB]:
    from ebook_reader.pipeline import BookPipeline

    pipeline = BookPipeline.__new__(BookPipeline)
    pipeline.settings = {"quality_profile": "high_quality", "asr": {}}
    pipeline.db = _FakeDB(rows)
    pipeline.log = lambda *_args, **_kwargs: None
    granted = BookPipeline._grant_machine_acceptances(
        pipeline, _Row({"id": 7, "chapter_index": 3})
    )
    return granted, pipeline.db


def test_a_name_only_asr_can_not_spell_is_let_through(tmp_path) -> None:
    """`"Gia tộc Remis,"` -> `"Gia tộc dây mít"`, sim 0,94, năm vòng sửa không đổi gì.

    d và r lẫn nhau trong tiếng Việt miền Bắc. Không phép kiểm nào khác phàn nàn về bản thu
    này, và không có gì để thu lại cho khác đi.
    """
    granted, db = _grant([_segment()])

    assert [item["warning_codes"] for item in granted] == [[ANCHOR]]
    assert db.accepted[0]["warning_code"] == ANCHOR
    assert "MACHINE_ACCEPTED_WITHOUT_LISTENER" in {code for _l, code, _m in db.events}


def test_a_take_the_generator_says_it_botched_is_refused(tmp_path) -> None:
    """Nhân chứng thứ hai, và nó thắng.

    `"Gì cơ?"` của chương 008: 1,92 giây, `generation_ceiling_hit=1.0`, và Whisper ảo giác
    ra `"Các bạn hãy đăng ký kênh để ủng hộ kênh của mình nhé"` - một câu chào cuối video
    YouTube nó học được lúc huấn luyện. Bản thu ấy hỏng thật, và bản vá trần khung vừa cho
    nó được thu lại. Máy tuyệt đối không được cho nó đi tiếp.
    """
    granted, db = _grant(
        [
            _segment(
                stable_id="c00008_s0000066",
                warning_code="ASR_TRANSCRIPT_TIMELINE_IMPOSSIBLE",
                signal_json=json.dumps({"generation_ceiling_hit": 1.0}),
            )
        ]
    )

    assert granted == []
    assert db.accepted == []


def test_a_second_verifier_complaining_is_refused(tmp_path) -> None:
    """`PERCEPTUAL_NATURALNESS_REVIEW` là một máy chấm khác, độc lập với ASR.

    Cả cơ chế này chỉ có một lý lẽ - *ASR mù thì đừng để nó chặn* - và lý lẽ ấy tan ngay khi
    có phép kiểm thứ hai nói cùng một điều.
    """
    granted, _db = _grant([_segment(warning_code=f"{ANCHOR}|{PERCEPTUAL}")])
    assert granted == []


def test_a_segment_with_no_audio_is_never_let_through(tmp_path) -> None:
    """Cho qua ở đây là xuất bản một chương thiếu hẳn một câu.

    Mất chữ thì không phép kiểm nào ở hạ nguồn bắt lại được - MP3 vẫn ghép, vẫn đúng độ dài,
    vẫn qua kiểm sau khi mã hoá. Chỉ có người đọc phát hiện ra, bằng cách mất một câu.
    """
    granted, _db = _grant([_segment(wav_sha256="", status="failed")])
    assert granted == []


def test_a_verified_segment_is_left_alone(tmp_path) -> None:
    granted, _db = _grant([_segment(status="verified", warning_code="")])
    assert granted == []


def test_a_warning_that_was_never_blocking_is_not_dressed_up_as_a_rescue(tmp_path) -> None:
    """Cấp phép cho đoạn không chặn gì thì cơ chế vẫn chạy đúng - và báo cáo hoá kêu sói giả.

    Chạy thử trên dữ liệu thật của alpha.60 trước khi có câu chặn này: cấp 13 lượt, trong đó
    7 là đoạn `warning` mang mã nằm sẵn trong `HIGH_QUALITY_ALLOWED_SEGMENT_WARNINGS`. Chương
    007 và 009 vốn qua được mọi cổng sẽ bỗng mang nhãn "3 đoạn chưa ai nghe", và một con số
    kêu ở chỗ không có gì sai thì lần sau không ai đọc nó nữa. Sau khi thêm: 6 lượt, đúng 6
    đoạn đang chặn thật.
    """
    granted, db = _grant(
        [
            _segment(
                status="warning",
                warning_code="ASR_TRANSCRIPT_TIMELINE_IMPOSSIBLE",
                signal_json=json.dumps({"rms": 0.05}),
            )
        ]
    )

    assert granted == []
    assert db.accepted == []


def test_the_same_code_on_a_failed_row_is_still_rescued(tmp_path) -> None:
    """Cặp đôi của test trên: cùng mã, khác trạng thái, và trạng thái mới là cái chặn.

    `ASR_TRANSCRIPT_TIMELINE_IMPOSSIBLE` không chặn với tư cách mã cảnh báo, nhưng `failed`
    chặn với tư cách trạng thái - `chapter_is_publishable` đọc trạng thái. Bỏ sót vế này thì
    cơ chế bỏ rơi đúng loại đoạn nó sinh ra để cứu.
    """
    granted, _db = _grant(
        [
            _segment(
                status="failed",
                warning_code="ASR_TRANSCRIPT_TIMELINE_IMPOSSIBLE",
                signal_json=json.dumps({"rms": 0.05}),
            )
        ]
    )

    assert [item["warning_codes"] for item in granted] == [
        ["ASR_TRANSCRIPT_TIMELINE_IMPOSSIBLE"]
    ]


def test_nothing_is_granted_twice(tmp_path) -> None:
    """Chạy lại chương không được đẻ thêm hàng nào, và `resume` chạy lại rất nhiều lần."""
    rows = [_segment()]
    granted, db = _grant(rows)
    assert len(granted) == 1

    from ebook_reader.pipeline import BookPipeline

    again = BookPipeline._grant_machine_acceptances(
        type("P", (), {"settings": {"quality_profile": "high_quality", "asr": {}},
                       "db": db, "log": lambda *_a, **_k: None})(),
        _Row({"id": 7, "chapter_index": 3}),
    )
    assert again == []


def test_the_switch_turns_the_whole_thing_off(tmp_path) -> None:
    """Hành vi cũ phải quay lại nguyên vẹn bằng một cài đặt, không bằng một bản vá ngược."""
    from ebook_reader.pipeline import BookPipeline

    pipeline = BookPipeline.__new__(BookPipeline)
    pipeline.settings = {
        "quality_profile": "high_quality",
        "asr": {"ship_without_a_listener": False},
    }
    pipeline.db = _FakeDB([_segment()])
    pipeline.log = lambda *_args, **_kwargs: None

    assert BookPipeline._grant_machine_acceptances(
        pipeline, _Row({"id": 7, "chapter_index": 3})
    ) == []
    assert pipeline.db.accepted == []


def test_the_setting_ships_on(tmp_path) -> None:
    assert build_settings()["asr"]["ship_without_a_listener"] is True


def test_a_switch_you_can_only_turn_off_by_typing_the_right_type_is_not_a_switch() -> None:
    """`"ship_without_a_listener": "false"` là một chuỗi, và chuỗi rỗng khác là truthy.

    Ai sửa settings JSON bằng tay để **tắt** cơ chế sẽ vô tình **bật** nó, im lặng. Đây là
    công tắc an toàn duy nhất của toàn bộ cơ chế, nên nó phải nổ chứ không được đoán ý.
    """
    from ebook_reader.config import build_settings, validate_settings

    settings = build_settings()
    settings["asr"]["ship_without_a_listener"] = "false"
    with pytest.raises(ValueError, match="ship_without_a_listener"):
        validate_settings(settings)

    settings["asr"]["ship_without_a_listener"] = False
    validate_settings(settings)


# ------------------------------------------------------- ba cổng, trên ProjectDB thật


def _db_with_a_failed_segment(tmp_path: Path):
    """Một project thật, với một đoạn `failed` mang checksum.

    Mọi test trên đây dùng DB giả và kiểm **quyết định** cấp phép. Cái chúng không kiểm được
    là điều đã làm dự án mất chương sáu lần: cấp phép đúng rồi mà một cổng ở hạ nguồn không
    biết hỏi bảng mới, nên chương vẫn chặn. Chỉ `ProjectDB` thật trả lời được câu ấy.
    """
    tmp_path.mkdir(parents=True, exist_ok=True)
    source = tmp_path / "001.txt"
    paragraphs = [f"Doan van thu {index} du dai de tach ra segment." for index in range(1, 4)]
    source.write_text((chr(10) + chr(10)).join(paragraphs), encoding="utf-8")
    _paths, db, settings = create_or_open_project(
        [source], tmp_path / "out", build_settings(), "Ba cong"
    )
    from ebook_reader.text_processing import load_and_segment_chapter

    chapter = db.list_chapters()[0]
    rows = load_and_segment_chapter(
        dict(chapter), max_chars=int(settings["tts"]["max_segment_chars"])
    )
    db.replace_chapter_segments(int(chapter["id"]), rows)
    with db.connect() as conn:
        conn.execute(
            "UPDATE segments SET status='verified', wav_sha256='cafe', "
            "wav_duration=1.0 WHERE 1=1"
        )
        conn.execute(
            "UPDATE segments SET status='failed', warning_code=?, wav_sha256=? "
            "WHERE id=(SELECT id FROM segments ORDER BY seq LIMIT 1)",
            (ANCHOR, "abc123"),
        )
        row = conn.execute(
            "SELECT stable_id, chapter_id FROM segments ORDER BY seq LIMIT 1"
        ).fetchone()
    return db, str(row["stable_id"]), int(row["chapter_id"])


def test_the_publish_gate_opens_for_a_machine_acceptance(tmp_path) -> None:
    """`chapter_is_publishable` đọc **trạng thái**, và trạng thái vẫn là `failed`.

    Đây là cổng mà phương án đầu tiên của tôi bỏ sót. Tôi định làm cơ chế chỉ dập mã cảnh báo
    và tuyệt đối không đụng tới trạng thái, vì như thế "sạch" hơn. Truy vấn alpha.60 thì thấy
    **cả tám đoạn chặn đều `failed`** — nên cơ chế ấy sẽ chạy đúng, test xanh, và gỡ được đúng
    **không** chương nào.
    """
    db, stable_id, chapter_id = _db_with_a_failed_segment(tmp_path)

    assert not db.chapter_is_publishable(chapter_id), "chưa cho qua thì phải còn chặn"

    db.accept_segment_audio_as_machine(
        segment_stable_id=stable_id,
        wav_sha256="abc123",
        warning_code=ANCHOR,
        reason="ASR là nhân chứng duy nhất",
    )

    assert db.chapter_is_publishable(chapter_id)


def test_the_machine_keeps_its_verdict_on_the_row(tmp_path) -> None:
    """Chương đi tiếp, nhưng đoạn vẫn `failed` và vẫn mang mã. Máy không đổi ý điều gì."""
    db, stable_id, chapter_id = _db_with_a_failed_segment(tmp_path)
    db.accept_segment_audio_as_machine(
        segment_stable_id=stable_id, wav_sha256="abc123", warning_code=ANCHOR, reason="vì thế"
    )

    with db.connect() as conn:
        row = conn.execute(
            "SELECT status, warning_code FROM segments WHERE stable_id=?", (stable_id,)
        ).fetchone()

    assert str(row["status"]) == "failed"
    assert ANCHOR in str(row["warning_code"])


def test_recutting_the_take_shuts_the_publish_gate_again(tmp_path) -> None:
    """Chấp nhận là chấp nhận một bản thu. `retry` cắt lại thì nó hết hiệu lực ở mọi cổng."""
    db, stable_id, chapter_id = _db_with_a_failed_segment(tmp_path)
    db.accept_segment_audio_as_machine(
        segment_stable_id=stable_id, wav_sha256="abc123", warning_code=ANCHOR, reason="vì thế"
    )
    assert db.chapter_is_publishable(chapter_id)

    with db.connect() as conn:
        conn.execute(
            "UPDATE segments SET wav_sha256='banthumoi' WHERE stable_id=?", (stable_id,)
        )

    assert not db.chapter_is_publishable(chapter_id)


def test_a_person_and_the_machine_open_the_same_gate_from_different_tables(tmp_path) -> None:
    """Hai nguồn, một cổng — và cổng không cần biết nguồn nào.

    Đây là lý do có `ruled_segment_takes()`: sáu cổng đã lần lượt đè lên phán quyết của người
    nghe, mỗi lần vì một chỗ mới quên hỏi. Cổng thứ bảy gọi `ruled_` và không phải biết có mấy
    bảng.
    """
    db, stable_id, chapter_id = _db_with_a_failed_segment(tmp_path)
    db.accept_segment_audio(
        segment_stable_id=stable_id, wav_sha256="abc123", warning_code=ANCHOR
    )
    assert db.chapter_is_publishable(chapter_id), "phán quyết của người vẫn phải mở cổng"

    db2, stable_id2, chapter_id2 = _db_with_a_failed_segment(tmp_path / "khac")
    db2.accept_segment_audio_as_machine(
        segment_stable_id=stable_id2, wav_sha256="abc123", warning_code=ANCHOR, reason="vì thế"
    )
    assert db2.chapter_is_publishable(chapter_id2), "và chấp nhận của máy cũng thế"

    assert db2.accepted_segment_warnings() == {}, "nhưng báo cáo vẫn phải nói chưa ai nghe"
