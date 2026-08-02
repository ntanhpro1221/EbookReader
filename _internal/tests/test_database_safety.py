from __future__ import annotations

from pathlib import Path

import pytest

from ebook_reader.database import ProjectDB
from ebook_reader.models import CONTEXTUAL_ENGLISH_NAME_PRONUNCIATION_SOURCE
from ebook_reader.config import build_settings
from ebook_reader.tts import TTSCoordinator


def _segment_db(tmp_path: Path) -> tuple[ProjectDB, int]:
    db = ProjectDB(tmp_path / "project.sqlite3")
    db.initialize_book(
        title="Book",
        project_root=tmp_path,
        settings={},
        settings_hash="settings",
        input_manifest_hash="manifest",
    )
    chapter_id = db.ensure_chapters(
        [
            {
                "chapter_index": 1,
                "title": "One",
                "input_path": tmp_path / "one.txt",
                "input_sha256": "source",
                "input_size": 1,
                "output_mp3": tmp_path / "one.mp3",
            }
        ]
    )[0]
    db.replace_chapter_segments(
        chapter_id,
        [
            {
                "stable_id": "c1s1",
                "seq": 0,
                "text": "Text",
                "text_sha256": "text",
                "kind_hint": "narration",
            }
        ],
    )
    return db, int(db.list_segments()[0]["id"])


def test_warning_codes_are_merged_without_duplicates(tmp_path: Path) -> None:
    db, segment_id = _segment_db(tmp_path)

    db.set_segment_warning_code(segment_id, "TTS_SPLIT_RECOVERY")
    db.mark_verified(segment_id, warning_code="ASR_ERROR")
    db.set_segment_warning_code(segment_id, "TTS_SPLIT_RECOVERY")

    assert db.get_segment(segment_id)["warning_code"] == "TTS_SPLIT_RECOVERY|ASR_ERROR"


def test_pronunciation_keeps_higher_confidence_value(tmp_path: Path) -> None:
    db = ProjectDB(tmp_path / "project.sqlite3")
    db.upsert_pronunciation(
        surface="Edelweiss",
        normalized_surface="edelweiss",
        spoken_form="Ê đen vai",
        confidence=0.9,
    )
    db.upsert_pronunciation(
        surface="Edelweiss",
        normalized_surface="edelweiss",
        spoken_form="Sai",
        confidence=0.4,
    )

    row = db.list_pronunciations()[0]
    assert row["spoken_form"] == "Ê đen vai"
    assert row["confidence"] == pytest.approx(0.9)


def test_locked_name_pronunciation_is_applied_and_cannot_be_overwritten(tmp_path: Path) -> None:
    db = ProjectDB(tmp_path / "project.sqlite3")
    db.upsert_pronunciation(
        surface="Michael",
        normalized_surface="michael",
        spoken_form="Mai-cồ",
        confidence=0.55,
        source="english_name_transliteration",
        locked=True,
    )
    db.upsert_pronunciation(
        surface="Michael",
        normalized_surface="michael",
        spoken_form="Cách đọc sai",
        confidence=0.99,
        source="analysis",
    )

    row = db.list_pronunciations(minimum_confidence=0.95)[0]
    assert row["spoken_form"] == "Mai-cồ"
    assert row["source"] == "english_name_transliteration"
    assert row["locked"] == 1


def test_pronunciation_is_applied_by_vieneu_coordinator(tmp_path: Path) -> None:
    db = ProjectDB(tmp_path / "project.sqlite3")
    db.upsert_pronunciation(
        surface="Edelweiss",
        normalized_surface="edelweiss",
        spoken_form="Ê đen vai",
        confidence=0.95,
    )
    coordinator = TTSCoordinator(build_settings(), db, lambda _message: None)

    assert coordinator.spoken_text({"text": "Edelweiss nở hoa."}) == "Ê đen vai nở hoa."


def test_vocalization_normalization_is_applied_without_changing_source_row(tmp_path: Path) -> None:
    db = ProjectDB(tmp_path / "project.sqlite3")
    coordinator = TTSCoordinator(build_settings(), db, lambda _message: None)
    row = {"text": "[thở dài] Haizzzzz.... Tôi hiểu rồi."}

    assert coordinator.spoken_text(row) == "Hầy... Hầy... Tôi hiểu rồi."
    assert row["text"] == "[thở dài] Haizzzzz.... Tôi hiểu rồi."


def test_contextual_english_name_pronunciation_preserves_lowercase_vietnamese_word(
    tmp_path: Path,
) -> None:
    db = ProjectDB(tmp_path / "project.sqlite3")
    db.upsert_pronunciation(
        surface="May",
        normalized_surface="may",
        spoken_form="Mây",
        confidence=0.95,
        source=CONTEXTUAL_ENGLISH_NAME_PRONUNCIATION_SOURCE,
        locked=True,
    )
    coordinator = TTSCoordinator(build_settings(), db, lambda _message: None)

    assert coordinator.spoken_text({"text": "May đang may một chiếc áo."}) == "Mây đang may một chiếc áo."
