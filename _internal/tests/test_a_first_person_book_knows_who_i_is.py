"""Một cuốn kể ngôi thứ nhất cần biết "tôi" LÀ AI — và một cuốn kể ngôi thứ ba thì không.

Đo lúc 04:00 ngày 2026-09-16 trên dữ liệu thật của cả hai cuốn, và hai cuốn cho hai câu trả lời
**trái nhau** — đó là lý do đây là một công tắc của từng cuốn, không phải một luật chung:

| cuốn | câu mang nhãn ngôi thứ nhất | là ai |
|---|---|---|
| 1 (kể ngôi thứ nhất) | 129 (`ME` 94, `Tôi` 34, `TÔI` 1) | nhân vật chính, cả 129 |
| 2 (kể ngôi thứ ba) | 10 (`Mình`) | **nhật ký của nữ phù thủy** Lucien đang đọc |

Cuốn 1 trước hai bản vá: 129 câu ấy cast thành **hai giọng nam khác** anh ta (`ME` có dòng
`characters` riêng, `importance='main'`, và ở lô 8 còn chia giọng với JAKE). Sau
`patch_a_pronoun_is_not_a_character`: về nhóm vô danh — một giọng sai nhưng nhất quán. Với
`voices.first_person_identity=SAMAEL`: về đúng giọng mà 451 câu khác của anh ta đang dùng.

Cuốn 2 thì luật này **phải im**: gán 10 câu nhật ký cho một danh tính nào đó là bịa ra một người.
Thước sàng (`scripts/measure_the_first_person_labels.py`) lấy cụm "đọc hộ" quanh mỗi ca: cuốn 2
sáng 9/10 ca (nhật ký, ghi chép, bản thảo), cuốn 1 sáng **1** ca duy nhất — và đọc tay thì ca ấy
là `"Sao thế, Juli?"` của chính người kể, sáng chỉ vì chữ `midi thướt tha` chứa chuỗi `di thư`.
"""
from __future__ import annotations

import inspect
from typing import Any

from ebook_reader.character_registry import (
    FIRST_PERSON_PRONOUNS,
    PRONOUNS,
    build_registry_and_cast,
    resolve_first_person_labels,
)


class _Db:
    def __init__(self, speakers: list[str]) -> None:
        self.rows = [{"speaker": speaker} for speaker in speakers]
        self.rewrites: list[tuple[str, str]] = []
        self.events: list[tuple[str, str, str, dict]] = []

    def list_segments(self) -> list[dict[str, Any]]:
        return list(self.rows)

    def rewrite_speaker(self, old_name: str, canonical_name: str) -> int:
        moved = [row for row in self.rows if row["speaker"] == old_name]
        for row in moved:
            row["speaker"] = canonical_name
        self.rewrites.append((old_name, canonical_name))
        return len(moved)

    def event(self, level: str, code: str, message: str, payload: dict) -> None:
        self.events.append((level, code, message, payload))


def _settings(identity: str | None) -> dict[str, Any]:
    voices: dict[str, Any] = {"narrator_voice": "Phạm Tuyên"}
    if identity is not None:
        voices["first_person_identity"] = identity
    return {"voices": voices}


def _log(_message: str) -> None:
    return None


def test_three_spellings_of_one_narrator_become_one_person() -> None:
    """Ca thật của cuốn 1: `ME`, `Tôi`, `TÔI` - một người, ba cách viết."""
    db = _Db(["ME", "ME", "Tôi", "TÔI", "SAMAEL", "JAKE", "NARRATOR"])

    moved = resolve_first_person_labels(db, _settings("SAMAEL"), _log)

    assert moved == 4
    assert [row["speaker"] for row in db.rows] == [
        "SAMAEL", "SAMAEL", "SAMAEL", "SAMAEL", "SAMAEL", "JAKE", "NARRATOR",
    ]
    assert db.events and db.events[0][1] == "FIRST_PERSON_LABELS_RESOLVED"
    assert db.events[0][3]["identity"] == "SAMAEL"


def test_a_third_person_book_is_left_completely_alone() -> None:
    """Cuốn 2: không có công tắc thì 10 câu nhật ký `Mình` không bị ai gán cho ai."""
    for settings in (_settings(None), _settings(""), _settings("   ")):
        db = _Db(["Mình", "Mình", "LUCIEN", "NARRATOR"])

        assert resolve_first_person_labels(db, settings, _log) == 0
        assert db.rewrites == []
        assert db.events == []
        assert [row["speaker"] for row in db.rows] == ["Mình", "Mình", "LUCIEN", "NARRATOR"]


def test_the_identity_is_written_the_way_every_other_name_is() -> None:
    """`canonical_key`: chủ sách gõ `Samael` thì nhãn vẫn về `SAMAEL` như mọi tên khác."""
    db = _Db(["tôi", "Samael"])

    resolve_first_person_labels(db, _settings("Samael"), _log)

    assert [row["speaker"] for row in db.rows] == ["SAMAEL", "Samael"]
    assert db.rewrites == [("tôi", "SAMAEL")]


def test_a_pronoun_is_not_an_answer_to_who_i_am() -> None:
    """`--first-person "Tôi"` không cứu được gì: phép so ở tầng dưới gấp chữ, nên nhãn `TÔI` vẫn
    khớp `PRONOUNS` và vẫn về nhóm vô danh. Công tắc sẽ im lặng vô dụng - nên nói ra.

    `cli create` từ chối thẳng (bài dưới). Ở tầng phân tích thì **không nổ**: một lệnh gõ sai
    không được phép làm chết cả lô giữa đường.
    """
    db = _Db(["Tôi", "Tôi"])

    assert resolve_first_person_labels(db, _settings("Tôi"), _log) == 0
    assert db.rewrites == []
    assert [event[1] for event in db.events] == ["FIRST_PERSON_IDENTITY_IS_A_PRONOUN"]
    assert [row["speaker"] for row in db.rows] == ["Tôi", "Tôi"]


def test_the_command_line_refuses_what_cannot_work() -> None:
    import argparse

    from ebook_reader.cli import CliUsageError, _settings_from_args

    def _args(**overrides: Any) -> argparse.Namespace:
        base: dict[str, Any] = {
            "settings_file": None,
            "profile": "high_quality",
            "first_person": "",
        }
        base.update(overrides)
        return argparse.Namespace(**base)

    assert "first_person_identity" not in _settings_from_args(_args())["voices"], (
        "khoá này chỉ được xuất hiện khi cuốn sách NÓI RA nó - xem docstring của "
        "`_settings_from_args`: một khoá mặc định đổi `settings_hash` của mọi project"
    )
    chosen = _settings_from_args(_args(first_person="  Samael  "))
    assert chosen["voices"]["first_person_identity"] == "Samael"

    for bad in (
        _args(first_person="Tôi"),
        _args(first_person="mình"),
        _args(first_person="SAMAEL", settings_file="settings.json"),
    ):
        try:
            _settings_from_args(bad)
        except CliUsageError:
            continue
        raise AssertionError(f"phải từ chối: {bad}")


def test_only_singular_first_person_labels_move() -> None:
    """`chúng ta` / `chúng tôi` / `bọn họ` là số nhiều: một câu của họ không phải lời một người."""
    plural = ["chúng ta", "chúng tôi", "chúng mình", "bọn họ"]
    third = ["hắn", "nàng", "cô ấy", "anh ấy", "ông ấy", "bà ấy", "người đó", "kẻ đó"]
    db = _Db([*plural, *third, "tôi"])

    moved = resolve_first_person_labels(db, _settings("SAMAEL"), _log)

    assert moved == 1
    assert db.rewrites == [("tôi", "SAMAEL")]
    assert [row["speaker"] for row in db.rows] == [*plural, *third, "SAMAEL"]


def test_every_first_person_label_is_already_a_pronoun() -> None:
    """Tập con của `PRONOUNS`: một nhãn không nằm trong đó thì hôm nay đã là một nhân vật thật.

    Nếu ai thêm một mục vào `FIRST_PERSON_PRONOUNS` mà quên `PRONOUNS` thì cuốn kể ngôi thứ ba
    sẽ vẫn cast nó như một người, và bài này đỏ trước khi chuyện đó tới sản xuất.
    """
    assert FIRST_PERSON_PRONOUNS <= PRONOUNS, FIRST_PERSON_PRONOUNS - PRONOUNS
    assert "me" in FIRST_PERSON_PRONOUNS, "nhãn tiếng Anh của cuốn 1 - 94 câu"
    assert not {"chúng ta", "chúng tôi", "chúng mình", "bọn họ"} & FIRST_PERSON_PRONOUNS


def test_the_labels_are_resolved_before_anything_reads_them() -> None:
    """Phải chạy TRƯỚC các phép sửa/gộp: chúng đối xử với dòng-tên-đại-từ theo luật riêng."""
    source = inspect.getsource(build_registry_and_cast)
    resolved = source.index("resolve_first_person_labels(db, settings, log)")

    for later in (
        "_repair_cross_batch_dialogue_continuations(db, log)",
        "_canonicalize_named_speakers(db, log)",
        "anonymous_by_gender",
    ):
        assert resolved < source.index(later), later
