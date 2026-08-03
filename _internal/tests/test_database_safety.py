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


def test_new_generation_clears_old_audio_warnings_but_keeps_analysis_warning(
    tmp_path: Path,
) -> None:
    db, segment_id = _segment_db(tmp_path)
    db.set_segment_warning_code(segment_id, "LOW_ANALYSIS_CONFIDENCE")
    db.set_segment_warning_code(segment_id, "SEGMENT_FAILED")
    db.set_segment_warning_code(segment_id, "TTS_GENERATION_CEILING_REACHED")
    db.set_segment_warning_code(segment_id, "ASR_SEVERE_MISMATCH")
    db.mark_asr_result(
        segment_id,
        passed=False,
        transcript="wrong",
        similarity=0.0,
        wer=1.0,
        warning_code="ASR_MISMATCH_UNRESOLVED",
    )

    db.mark_generating(segment_id, seed=17)

    row = db.get_segment(segment_id)
    assert row["status"] == "generating"
    assert row["warning_code"] == "LOW_ANALYSIS_CONFIDENCE"
    assert row["asr_text"] is None
    assert row["asr_similarity"] is None
    assert row["asr_wer"] is None
    assert row["error"] is None


def test_audio_reset_keeps_locked_analysis_and_casting(tmp_path: Path) -> None:
    db, segment_id = _segment_db(tmp_path)
    db.update_analysis(
        segment_id,
        {
            "kind": "dialogue",
            "speaker": "LUCIEN",
            "gender": "male",
            "age": "adult",
            "emotion": "neutral",
            "intensity": 1,
            "pace": "normal",
            "volume": "normal",
            "confidence": 1.0,
        },
    )
    profile_id = db.upsert_voice_profile({
        "voice_key": "lucien",
        "engine": "vieneu",
        "preset_name": "Xuân Vĩnh",
        "description": "Lucien",
        "seed": 1,
        "pitch_semitones": 0,
        "status": "ready",
    })
    with db.connect() as conn:
        conn.execute(
            "UPDATE segments SET voice_profile_id=? WHERE id=?",
            (profile_id, segment_id),
        )

    db.reset_segment_pending(segment_id, "WAV needs regeneration")

    row = db.get_segment(segment_id)
    assert row["status"] == "analyzed"
    assert row["kind"] == "dialogue"
    assert row["speaker"] == "LUCIEN"
    assert row["voice_profile_id"] == profile_id

    db.mark_generating(segment_id, seed=23)
    assert db.reset_in_progress_segments("Interrupted generation") == 1

    recovered = db.get_segment(segment_id)
    assert recovered["status"] == "analyzed"
    assert recovered["kind"] == "dialogue"
    assert recovered["speaker"] == "LUCIEN"
    assert recovered["voice_profile_id"] == profile_id


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
