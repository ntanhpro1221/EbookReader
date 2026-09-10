"""Khi ASR không thể làm trọng tài, bản thu bộ sinh **nói xong** thắng bản bị **cắt**.

Ba ca trong 50.196 đoạn đã lưu, và cả ba cùng một hình: đương nhiệm dài đúng 1,92 giây
(12 khung × 160 ms) với `generation_ceiling_hit`, văn bản dưới ngưỡng ASR phán xử được, và
trong số ứng viên bị vứt có bản tự kết thúc.

```
alpha.25 ch005  '"Arghh..."'
alpha.60 ch021  '"Tiếp theo."'
lo02     ch053  '"Bất bại?"'
```

Bài này kiểm **bốn điều kiện** bằng row giả, vì đó là chỗ rủi ro nằm: mỗi điều kiện phải **tự
mình** đủ để từ chối. Một chốt chặn bốn điều kiện mà chỉ có một bài test "đường thuận" thì ba
điều kiện kia có thể đã hỏng mà không ai biết.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from ebook_reader.asr_contract import ASR_MIN_VERIFIABLE_CHARS
from ebook_reader.config import build_settings
from ebook_reader.database import (
    SEGMENT_CANDIDATE_DUAL_FAILED,
    SEGMENT_CANDIDATE_DUAL_PASSED,
    ProjectDB,
    _asr_only_failure_codes,
)
from ebook_reader.project import create_or_open_project

CUT_OFF = {"generation_ceiling_hit": 1.0}
FINISHED: dict[str, float] = {}


def _gate() -> ProjectDB:
    """Chỉ cần `_json_object`, nên không dựng project thật cho phần kiểm điều kiện."""
    return object.__new__(ProjectDB)


def _row(**fields):
    import json

    base = {
        "id": 7,
        "stable_id": "c00024_s0000078_0bab1636c786",
        "wav_duration": 1.92,
        "repair_round": 1,
        "text": '"Bất bại?"',
        "failure_reason": "beam=ASR_MISMATCH; greedy=ASR_MISMATCH",
        "signal_json": json.dumps(CUT_OFF),
    }
    base.update(fields)
    if isinstance(base["signal_json"], dict):
        base["signal_json"] = json.dumps(base["signal_json"])
    return base


def _check(gate, *, segment_over=None, candidate_over=None):
    segment = _row(**(segment_over or {}))
    candidate = _row(
        **{
            "wav_duration": 0.8,
            "signal_json": FINISHED,
            **(candidate_over or {}),
        }
    )
    return gate._require_candidate_beats_a_cut_off_incumbent(candidate, segment)


def test_the_real_case_passes_the_gate() -> None:
    """Chương 053 của lô 2, đúng như dữ liệu ghi lại."""
    reason = _check(_gate())

    assert "chạm trần" in reason
    assert "tự kết thúc" in reason
    assert str(ASR_MIN_VERIFIABLE_CHARS) in reason


def test_it_refuses_when_the_incumbent_finished() -> None:
    """Điều kiện quan trọng nhất: không có nó thì đây là thay một bản thu tốt.

    Đo trên 50.196 đoạn: 469 đoạn có văn bản ngắn và có ứng viên mà đương nhiệm **không** chạm
    trần. Bỏ điều kiện này là trao quyền thay thế cho bốn trăm chỗ chẳng cần thay.
    """
    with pytest.raises(RuntimeError) as caught:
        _check(_gate(), segment_over={"signal_json": FINISHED})

    assert "đương nhiệm không chạm trần khung" in str(caught.value)


def test_it_refuses_when_the_candidate_was_also_cut_off() -> None:
    with pytest.raises(RuntimeError) as caught:
        _check(_gate(), candidate_over={"signal_json": CUT_OFF})

    assert "ứng viên cũng chạm trần khung" in str(caught.value)


def test_it_refuses_when_asr_could_have_judged_the_text() -> None:
    """Văn bản đủ dài thì ASR **có** ý kiến, và "ứng viên trượt ASR" là bằng chứng thật."""
    long_enough = "Tôi nhếch mép và không nói gì thêm."
    assert sum(ch.isalnum() for ch in long_enough) >= ASR_MIN_VERIFIABLE_CHARS

    with pytest.raises(RuntimeError) as caught:
        _check(_gate(), segment_over={"text": long_enough})

    assert "văn bản đủ dài để ASR phán xử" in str(caught.value)


def test_it_refuses_a_candidate_that_failed_outside_asr() -> None:
    """Một cờ sóng âm nói bản thu hỏng theo cách nhìn thấy được mà không cần phiên âm."""
    with pytest.raises(RuntimeError) as caught:
        _check(
            _gate(),
            candidate_over={
                "failure_reason": "beam=ASR_MISMATCH; blocking_signal=TTS_CLIPPING"
            },
        )

    assert "ứng viên trượt bằng mã ngoài ASR" in str(caught.value)


def test_it_refuses_a_candidate_with_no_recorded_reason() -> None:
    """Không biết vì sao nó trượt thì không được thay - im lặng không phải một cái cớ."""
    with pytest.raises(RuntimeError):
        _check(_gate(), candidate_over={"failure_reason": ""})


def test_every_clause_is_named_separately() -> None:
    """Bốn điều kiện phải hỏng riêng lẻ, không gộp sau một câu thông báo chung.

    Đây là luật của repo (`require_all`, ghim bằng `test_no_new_blind_compound_check_is_added`)
    và nó đã bắt tôi một lần khi tôi bê nguyên dáng `if a or b or c` sang chỗ khác.
    """
    messages = []
    for over in (
        {"segment_over": {"signal_json": FINISHED}},
        {"candidate_over": {"signal_json": CUT_OFF}},
        {"segment_over": {"text": "Một câu dài hơn ngưỡng ASR nhiều."}},
        {"candidate_over": {"failure_reason": "beam=ASR_MISMATCH; blocking_signal=X_Y"}},
    ):
        with pytest.raises(RuntimeError) as caught:
            _check(_gate(), **over)
        messages.append(str(caught.value))

    assert len(set(messages)) == 4, "bốn điều kiện phải cho bốn thông báo khác nhau"


def test_only_asr_codes_count_as_uninformative() -> None:
    assert _asr_only_failure_codes("beam=ASR_MISMATCH; greedy=ASR_MISMATCH") == {
        "ASR_MISMATCH"
    }
    assert _asr_only_failure_codes("beam=ASR_MISMATCH; blocking_signal=TTS_X") is None
    assert _asr_only_failure_codes("") is None
    assert _asr_only_failure_codes(None) is None


def test_the_finder_picks_the_lowest_round(monkeypatch: pytest.MonkeyPatch) -> None:
    """Giữa hai bản thu hoàn chỉnh mà ASR không phán xử được, không có gì để xếp hạng.

    Nên quy tắc là tất định và nhàm chán: vòng nhỏ nhất. Bài này cũng ghim rằng ứng viên
    `dual_passed` **không** đi qua đường này - đường bình thường lo chúng.
    """
    gate = _gate()
    segment = _row()
    candidates = [
        _row(id=1, repair_round=3, wav_duration=0.72, signal_json=FINISHED),
        _row(id=2, repair_round=1, wav_duration=0.80, signal_json=FINISHED),
        _row(id=3, repair_round=0, wav_duration=0.96, signal_json=CUT_OFF),
    ]
    for candidate in candidates:
        candidate["state"] = SEGMENT_CANDIDATE_DUAL_FAILED
    monkeypatch.setattr(ProjectDB, "get_segment", lambda self, _id: segment)
    monkeypatch.setattr(
        ProjectDB,
        "list_segment_candidates",
        lambda self, **_kwargs: candidates,
    )

    chosen = gate.find_finished_take_over_a_cut_off_incumbent(7, "policy")

    assert chosen is not None
    assert int(chosen["repair_round"]) == 1, "vòng 0 chạm trần nên phải bị bỏ qua"


def test_the_finder_ignores_candidates_that_already_passed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gate = _gate()
    segment = _row()
    candidate = _row(id=2, repair_round=1, signal_json=FINISHED)
    candidate["state"] = SEGMENT_CANDIDATE_DUAL_PASSED
    monkeypatch.setattr(ProjectDB, "get_segment", lambda self, _id: segment)
    monkeypatch.setattr(
        ProjectDB, "list_segment_candidates", lambda self, **_kwargs: [candidate]
    )

    assert gate.find_finished_take_over_a_cut_off_incumbent(7, "policy") is None


def test_the_table_exists_and_the_accessor_reads_it(tmp_path: Path) -> None:
    """Bảng phải thật sự có trong schema, không chỉ có trong bản vá.

    Phần kiểm điều kiện ở trên dùng row giả nên nó không chạm vào SQL. Bài này chạm, vì một câu
    INSERT sai chính tả sẽ chỉ nổ lúc chạy thật - và chạy thật là giữa một lô mười ba giờ.
    """
    tmp_path.mkdir(parents=True, exist_ok=True)
    source = tmp_path / "001.txt"
    source.write_text("Một câu để mở project.", encoding="utf-8")
    _paths, db, _settings = create_or_open_project(
        [source], tmp_path / "out", build_settings(), "Take substitution"
    )

    assert db.list_take_substitutions() == []

    with db.transaction() as conn:
        conn.execute(
            "INSERT INTO machine_take_substitutions "
            "(segment_stable_id, incumbent_wav_sha256, candidate_wav_sha256, reason, created_at)"
            " VALUES (?,?,?,?,?)",
            ("c1s1", "a" * 64, "b" * 64, "lý do", 1.0),
        )

    rows = db.list_take_substitutions()
    assert len(rows) == 1
    assert rows[0]["reason"] == "lý do"
