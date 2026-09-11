"""Một tên nối bằng gạch dưới là tên ấy viết bằng khoảng trắng: NGUOI_TRA_LOI là NGƯỜI TRẢ LỜI.

Đo 2026-09-11: 45 câu trong bốn project, tất cả tạo sau khi prompt "đã biết" bắt đầu mang tên
đủ dấu. Chương 104 đúc lại có người ấy nói 10 câu bằng một giọng mới và 1 câu bằng giọng ghim -
một người hai giọng trong chính chương được đúc lại để xoá lỗi ấy.
"""
from __future__ import annotations

from pathlib import Path

from ebook_reader.character_registry import (
    build_registry_and_cast,
    canonical_key,
    dropped_marks_variant_of,
    identity_key,
)
from ebook_reader.config import build_settings

from tests.test_character_casting import _identity_db


def test_an_underscore_reads_as_a_space_for_identity_only() -> None:
    assert identity_key("NGUOI_TRA_LOI") == identity_key("NGUOI TRA LOI") == "nguoi tra loi"
    assert dropped_marks_variant_of("NGUOI_TRA_LOI", "NGƯỜI TRẢ LỜI")
    # `canonical_key` KHÔNG đổi: NPC và các key giữ chỗ/holders vẫn mang gạch dưới như cũ.
    assert canonical_key("NPC_LOCAL::C1::R2::LÍNH GÁC") == "NPC_LOCAL::C1::R2::LÍNH GÁC"


def test_the_underscore_spelling_casts_as_the_same_person(tmp_path: Path) -> None:
    """Đúng tỉ lệ chương 104: bản gạch dưới nói nhiều hơn, bản đủ dấu vẫn thắng và giọng là một."""
    db = _identity_db(
        tmp_path,
        [("NGUOI_TRA_LOI", "female")] * 10 + [("NGƯỜI TRẢ LỜI", "female")] * 1 + [("KANG", "male")],
    )

    build_registry_and_cast(db, build_settings(), lambda _message: None)

    rows = db.list_segments()
    assert {str(row["speaker"]) for row in rows} == {"NGƯỜI TRẢ LỜI", "KANG"}
    answerer = [row for row in rows if str(row["speaker"]) == "NGƯỜI TRẢ LỜI"]
    assert len(answerer) == 11
    assert len({int(row["canonical_character_id"]) for row in answerer}) == 1
    assert len({int(row["voice_profile_id"]) for row in answerer}) == 1


def test_local_npcs_keep_their_underscored_identity(tmp_path: Path) -> None:
    """Gạch dưới trong `NPC_LOCAL::` là thiết kế, không phải lỗi chính tả - không được gộp."""
    db = _identity_db(
        tmp_path,
        [("NPC_LOCAL::C00001::RAAAA::LÍNH GÁC", "male")] * 2 + [("KANG", "male")] * 3,
    )

    build_registry_and_cast(db, build_settings(), lambda _message: None)

    assert any(str(row["speaker"]).startswith("NPC_LOCAL::") for row in db.list_segments())
