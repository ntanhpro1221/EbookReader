from __future__ import annotations

from pathlib import Path

import pytest

from ebook_reader.character_registry import build_registry_and_cast
from ebook_reader.analysis import EXPLICIT_ATTRIBUTION_NOTE, local_speaker_label
from ebook_reader.config import build_settings
from ebook_reader.database import ProjectDB
from ebook_reader.voice_catalog import (
    GENDER_FEMALE,
    GENDER_MALE,
    PRESET_PREVIEW_MEDIAN_PITCH_HZ,
    PRESET_MIN_PITCH_SEMITONES,
    REGION_CENTRAL,
    REGION_NORTH,
    REGION_SOUTH,
    STYLE_NATURAL,
    STYLE_NEWS,
    STYLE_STORY,
    VIENEU_PRESETS,
    casting_presets,
    pitch_variants_for_preset,
    preset_by_name,
)


def _casting_db(tmp_path: Path) -> ProjectDB:
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
    speakers = [("NARRATOR", "unknown")]
    speakers.extend((f"Nam {index}", "male") for index in range(1, 7))
    speakers.extend((f"Nữ {index}", "female") for index in range(1, 8))
    speakers.extend(
        [
            ("NPC_LOCAL::c00001::b0001::áo xanh", "male"),
            ("NPC_LOCAL::c00001::b0001::áo đỏ", "male"),
            ("NPC_LOCAL::c00001::b0001::áo vàng", "male"),
            ("NPC_LOCAL::c00001::b0001::áo tím", "male"),
            ("NPC_LOCAL::c00001::b0002::giám mục", "male"),
            ("Giám mục", "male"),
            ("UNKNOWN", "male"),
            ("UNKNOWN", "female"),
        ]
    )
    rows = []
    for seq, (speaker, gender) in enumerate(speakers):
        rows.append(
            {
                "stable_id": f"c1s{seq}",
                "seq": seq,
                "text": f"Câu thoại thử nghiệm số {seq}.",
                "text_sha256": f"text{seq}",
                "kind_hint": "narration" if speaker == "NARRATOR" else "dialogue",
                "kind": "narration" if speaker == "NARRATOR" else "dialogue",
                "speaker": speaker,
                "gender": gender,
                "confidence": 0.95,
                "status": "analyzed",
            }
        )
    db.replace_chapter_segments(chapter_id, rows)
    return db


def _identity_db(tmp_path: Path, speakers: list[tuple[str, str]]) -> ProjectDB:
    db = ProjectDB(tmp_path / "identity-gate.sqlite3")
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
                "stable_id": f"c1s{seq}",
                "seq": seq,
                "text": f"Câu thoại {seq}.",
                "text_sha256": f"text-{seq}",
                "kind_hint": "dialogue",
                "kind": "dialogue",
                "speaker": speaker,
                "gender": gender,
                "confidence": 0.95,
                "status": "analyzed",
            }
            for seq, (speaker, gender) in enumerate(speakers, 1)
        ],
    )
    return db


def _reconciliation_db(tmp_path: Path) -> ProjectDB:
    db = ProjectDB(tmp_path / "reconciliation.sqlite3")
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
    rows = [
        (1, 1, "“Lời của người đàn ông.”", "NPC_LOCAL::c00001::a::người đàn ông trung niên", "male", "adult", "personality=priest"),
        (10, 10, "“Lời của giám mục.”", "NPC_LOCAL::c00001::b::giam muc", "male", "adult", "personality=priest"),
        (20, 20, "“Lời nguyền đầu tiên!”", "NPC_LOCAL::c00001::c::người phụ nữ mặc áo choàng đen", "female", "adult", f"personality=madwoman; {EXPLICIT_ATTRIBUTION_NOTE}"),
        (21, 21, "“Điên rồi!”", "NPC_LOCAL::c00001::c::phu nu ao choang den", "female", "unknown", "personality=madwoman"),
        (22, 22, "“Độc ác quá!”", "NPC_LOCAL::c00001::c::phu nu ao choang den", "female", "unknown", "personality=madwoman"),
        (23, 23, "“Thiêu ả đi!”", "NPC_LOCAL::c00001::c::phu nu ao choang den", "female", "unknown", "personality=madwoman"),
        (24, 24, "Những người dân nghèo trên quảng trường gào thét đến lạc giọng.", "NARRATOR", "unknown", "unknown", "personality=narrator"),
        (30, 30, "“Từ trong biển lửa, ta sẽ chứng kiến tất cả sụp đổ.", "NPC_LOCAL::c00001::d::phu nu ao choang den", "female", "adult", "personality=madwoman"),
        (31, 31, "Ta sẽ chứng kiến các ngươi trầm luân!”", "NPC_LOCAL::c00001::e::thần lửa", "male", "unknown", "personality=deity"),
    ]
    db.replace_chapter_segments(
        chapter_id,
        [
            {
                "stable_id": f"c1s{seq}",
                "seq": seq,
                "paragraph_index": paragraph,
                "text": text,
                "text_sha256": f"text-{seq}",
                "kind_hint": "narration" if speaker == "NARRATOR" else "dialogue",
                "kind": "narration" if speaker == "NARRATOR" else "dialogue",
                "speaker": speaker,
                "gender": gender,
                "age": age,
                "confidence": 0.95,
                "analysis_notes": notes,
                "status": "analyzed",
            }
            for seq, paragraph, text, speaker, gender, age, notes in rows
        ],
    )
    return db


def test_casting_prioritizes_standard_voices_reuses_with_pitch_and_limits_regional_to_npcs(
    tmp_path: Path,
) -> None:
    db = _casting_db(tmp_path)

    build_registry_and_cast(db, build_settings(), lambda _message: None)

    profiles = db.list_voice_profiles()
    assert all(preset_by_name(str(profile["preset_name"]))["style"] != STYLE_NEWS for profile in profiles)
    assert all(abs(int(profile["pitch_semitones"])) <= 2 for profile in profiles)
    assert all(
        int(profile["pitch_semitones"])
        >= PRESET_MIN_PITCH_SEMITONES.get(str(profile["preset_name"]), -2)
        for profile in profiles
    )
    rows = db.list_segments()
    local_rows = [row for row in rows if str(row["speaker"]).startswith("NPC_LOCAL::")]
    assert len({int(row["canonical_character_id"]) for row in local_rows}) == 4
    assert len({int(row["voice_profile_id"]) for row in local_rows}) == 4

    profile_by_id = {int(profile["id"]): profile for profile in profiles}
    named_rows = [
        row for row in rows
        if str(row["speaker"]) not in {"NARRATOR", "UNKNOWN"}
        and not str(row["speaker"]).startswith("NPC_LOCAL::")
    ]
    named_presets = [
        preset_by_name(str(profile_by_id[int(row["voice_profile_id"])]["preset_name"]))
        for row in named_rows
    ]
    assert {preset["region"] for preset in named_presets} <= {REGION_NORTH, REGION_SOUTH}

    local_presets = [
        preset_by_name(str(profile_by_id[int(row["voice_profile_id"])]["preset_name"]))
        for row in local_rows
    ]
    assert any(preset["region"] == REGION_CENTRAL for preset in local_presets)
    assert any(preset["region"] != REGION_CENTRAL for preset in local_presets)

    named_male_profiles = [
        profile_by_id[int(row["voice_profile_id"])]
        for row in named_rows
        if str(row["gender"]) == "male"
    ]
    pitches_by_preset: dict[str, set[int]] = {}
    for profile in named_male_profiles:
        pitches_by_preset.setdefault(str(profile["preset_name"]), set()).add(
            int(profile["pitch_semitones"])
        )
    assert any(len(pitches) > 1 for pitches in pitches_by_preset.values())

    anonymous = [row for row in rows if str(row["speaker"]) == "UNKNOWN"]
    assert len({int(row["canonical_character_id"]) for row in anonymous}) == 2
    assert {
        preset_by_name(str(profile_by_id[int(row["voice_profile_id"])]["preset_name"]))["gender"]
        for row in anonymous
    } == {"male", "female"}

    bishop_rows = [row for row in rows if str(row["speaker"]) == "Giám mục"]
    assert len(bishop_rows) == 2
    assert len({int(row["canonical_character_id"]) for row in bishop_rows}) == 1
    assert len({int(row["voice_profile_id"]) for row in bishop_rows}) == 1


def test_casting_prioritizes_natural_north_then_natural_south() -> None:
    male_order = [
        (preset["region"], preset["style"])
        for preset in casting_presets(GENDER_MALE, include_regional=True)
    ]
    female_order = [
        (preset["region"], preset["style"])
        for preset in casting_presets(GENDER_FEMALE, include_regional=True)
    ]

    assert male_order == [
        (REGION_NORTH, STYLE_NATURAL),
        (REGION_SOUTH, STYLE_NATURAL),
        (REGION_NORTH, STYLE_STORY),
        (REGION_SOUTH, STYLE_STORY),
        (REGION_CENTRAL, STYLE_NATURAL),
    ]
    assert female_order == [
        (REGION_NORTH, STYLE_NATURAL),
        (REGION_NORTH, STYLE_NATURAL),
        (REGION_NORTH, STYLE_STORY),
        (REGION_SOUTH, STYLE_STORY),
        (REGION_CENTRAL, STYLE_NATURAL),
    ]


def test_clear_named_aliases_lock_to_one_character_and_voice(tmp_path: Path) -> None:
    db = _identity_db(
        tmp_path,
        [
            ("ALISA", "female"),
            ("DÌ ALISA", "female"),
            ("NPC ALISA", "female"),
            ("NPC_LOCAL::c00001::stable::Alisa", "female"),
            ("VICTOR", "male"),
            ("VICT,OR", "male"),
        ],
    )

    build_registry_and_cast(db, build_settings(), lambda _message: None)

    rows = db.list_segments()
    assert {str(row["speaker"]) for row in rows} == {"ALISA", "VICTOR"}
    for speaker in ("ALISA", "VICTOR"):
        speaker_rows = [row for row in rows if str(row["speaker"]) == speaker]
        assert len({int(row["canonical_character_id"]) for row in speaker_rows}) == 1
        assert len({int(row["voice_profile_id"]) for row in speaker_rows}) == 1


def test_adjacent_local_child_scopes_merge_to_one_character_and_voice(tmp_path: Path) -> None:
    db = _identity_db(
        tmp_path,
        [
            ("NPC_LOCAL::c00001::batch-a::cậu bé", "male"),
            ("NPC_LOCAL::c00001::batch-b::trẻ em bụi bẩn", "male"),
        ],
    )

    build_registry_and_cast(db, build_settings(), lambda _message: None)

    rows = db.list_segments()
    assert len({str(row["speaker"]) for row in rows}) == 1
    assert len({int(row["canonical_character_id"]) for row in rows}) == 1
    assert len({int(row["voice_profile_id"]) for row in rows}) == 1


def test_interleaved_local_children_remain_distinct(tmp_path: Path) -> None:
    first = "NPC_LOCAL::c00001::batch-a::cậu bé áo xanh"
    second = "NPC_LOCAL::c00001::batch-b::trẻ em áo đỏ"
    db = _identity_db(
        tmp_path,
        [(first, "male"), (second, "male"), (first, "male"), (second, "male")],
    )

    build_registry_and_cast(db, build_settings(), lambda _message: None)

    rows = db.list_segments()
    assert len({str(row["speaker"]) for row in rows}) == 2
    assert len({int(row["canonical_character_id"]) for row in rows}) == 2


def test_reconciliation_repairs_crowd_continuation_and_role_aliases(tmp_path: Path) -> None:
    db = _reconciliation_db(tmp_path)

    build_registry_and_cast(db, build_settings(), lambda _message: None)

    rows = {int(row["seq"]): row for row in db.list_segments()}
    bishop_rows = [rows[1], rows[10]]
    witch_rows = [rows[20], rows[30], rows[31]]
    crowd_rows = [rows[21], rows[22], rows[23]]
    assert len({int(row["canonical_character_id"]) for row in bishop_rows}) == 1
    assert len({int(row["voice_profile_id"]) for row in bishop_rows}) == 1
    assert len({int(row["canonical_character_id"]) for row in witch_rows}) == 1
    assert len({int(row["voice_profile_id"]) for row in witch_rows}) == 1
    assert {local_speaker_label(row["speaker"]) for row in crowd_rows} == {"người dân"}
    assert {str(row["gender"]) for row in crowd_rows} == {"unknown"}


def test_relational_description_is_not_merged_with_named_character(tmp_path: Path) -> None:
    db = _identity_db(
        tmp_path,
        [("FELICIA", "female"), ("MẸ CỦA FELICIA", "female")],
    )

    build_registry_and_cast(db, build_settings(), lambda _message: None)

    rows = db.list_segments()
    assert {str(row["speaker"]) for row in rows} == {"FELICIA", "MẸ CỦA FELICIA"}
    assert len({int(row["canonical_character_id"]) for row in rows}) == 2


def test_gender_conflict_fails_before_voice_casting(tmp_path: Path) -> None:
    db = _identity_db(tmp_path, [("CAMIL", "female"), ("Camil", "male")])

    with pytest.raises(RuntimeError, match="gender conflicts"):
        build_registry_and_cast(db, build_settings(), lambda _message: None)

    assert db.list_voice_profiles() == []


def test_recurring_named_speaker_without_gender_fails_before_voice_casting(
    tmp_path: Path,
) -> None:
    db = _identity_db(tmp_path, [("Mag", "unknown")] * 3)

    with pytest.raises(RuntimeError, match="named speakers missing gender"):
        build_registry_and_cast(db, build_settings(), lambda _message: None)

    assert db.list_voice_profiles() == []


def test_existing_voice_identity_instability_fails_before_recasting(tmp_path: Path) -> None:
    db = _identity_db(tmp_path, [("Lucien", "male"), ("Lucien", "male")])
    character_id = db.upsert_character(
        canonical_name="LUCIEN",
        display_name="Lucien",
        gender="male",
        age="adult",
        personality="",
        mentions=2,
        importance="main",
        confidence=0.95,
    )
    first_profile = db.upsert_voice_profile(
        {
            "voice_key": "unstable-one",
            "engine": "vieneu",
            "preset_name": "Thái Sơn",
            "description": "one",
            "seed": 1,
            "pitch_semitones": 0,
            "status": "ready",
        }
    )
    second_profile = db.upsert_voice_profile(
        {
            "voice_key": "unstable-two",
            "engine": "vieneu",
            "preset_name": "Quang Sơn",
            "description": "two",
            "seed": 2,
            "pitch_semitones": 0,
            "status": "ready",
        }
    )
    rows = db.list_segments()
    db.set_character_and_voice_for_segments([int(rows[0]["id"])], character_id, first_profile)
    db.set_character_and_voice_for_segments([int(rows[1]["id"])], character_id, second_profile)

    with pytest.raises(RuntimeError, match="voice identity instability"):
        build_registry_and_cast(db, build_settings(), lambda _message: None)


def test_same_lucien_name_locks_one_voice_across_chapters_without_identity_merging(
    tmp_path: Path,
) -> None:
    db = ProjectDB(tmp_path / "identity.sqlite3")
    db.initialize_book(
        title="Book",
        project_root=tmp_path,
        settings={},
        settings_hash="settings",
        input_manifest_hash="manifest",
    )
    chapter_ids = db.ensure_chapters(
        [
            {
                "chapter_index": index,
                "title": title,
                "input_path": tmp_path / f"{title}.txt",
                "input_sha256": f"source-{index}",
                "input_size": 1,
                "output_mp3": tmp_path / f"{title}.mp3",
            }
            for index, title in enumerate(("000", "001"), 1)
        ]
    )
    db.replace_chapter_segments(
        chapter_ids[0],
        [
            {
                "stable_id": "c1s1",
                "seq": 1,
                "text": "Hạ Phong đang nói.",
                "text_sha256": "text-hp",
                "kind_hint": "dialogue",
                "kind": "dialogue",
                "speaker": "Hạ Phong",
                "gender": "male",
                "confidence": 0.99,
                "status": "analyzed",
            },
            {
                "stable_id": "c1s2",
                "seq": 2,
                "text": "Lucien xuất hiện ở chương đầu.",
                "text_sha256": "text-lucien-1",
                "kind_hint": "dialogue",
                "kind": "dialogue",
                "speaker": "Lucien",
                "gender": "male",
                "confidence": 0.99,
                "status": "analyzed",
            },
            {
                "stable_id": "c1s3",
                "seq": 3,
                "text": "‘Nội tâm này phải do người kể đọc.’",
                "text_sha256": "text-thought",
                "kind_hint": "thought",
                "kind": "thought",
                "speaker": "Lucien",
                "gender": "male",
                "confidence": 0.99,
                "status": "analyzed",
            },
        ],
    )
    db.replace_chapter_segments(
        chapter_ids[1],
        [
            {
                "stable_id": "c2s1",
                "seq": 1,
                "text": "Lucien tiếp tục nói ở chương sau.",
                "text_sha256": "text-lucien-2",
                "kind_hint": "dialogue",
                "kind": "dialogue",
                "speaker": "Lucien",
                "gender": "male",
                "confidence": 0.99,
                "status": "analyzed",
            }
        ],
    )

    build_registry_and_cast(
        db,
        build_settings(),
        lambda _message: None,
    )

    rows = db.list_segments()
    lucien_rows = [row for row in rows if str(row["speaker"]) == "Lucien"]
    ha_phong_rows = [row for row in rows if str(row["speaker"]) == "Hạ Phong"]
    thought_rows = [row for row in rows if str(row["kind"]) == "thought"]

    assert len(lucien_rows) == 2
    assert len({int(row["canonical_character_id"]) for row in lucien_rows}) == 1
    assert len({int(row["voice_profile_id"]) for row in lucien_rows}) == 1
    assert ha_phong_rows[0]["canonical_character_id"] != lucien_rows[0]["canonical_character_id"]
    assert {str(row["speaker"]) for row in thought_rows} == {"NARRATOR"}
    assert len({int(row["voice_profile_id"]) for row in thought_rows}) == 1


def test_pitch_ranges_follow_measured_preset_depth() -> None:
    supported_names = {
        preset["name"]
        for preset in VIENEU_PRESETS
        if preset["style"] != STYLE_NEWS
    }
    assert set(PRESET_PREVIEW_MEDIAN_PITCH_HZ) == supported_names
    assert PRESET_MIN_PITCH_SEMITONES == {
        "Phạm Tuyên": 0,
        "Xuân Vĩnh": -1,
        "Thái Sơn": -1,
        "Quang Sơn": -2,
        "Thanh Bình": -2,
        "Ngọc Trân": -1,
        "Ngọc Linh": -2,
        "Trúc Ly": -2,
        "Đoan Trang": -2,
        "Thục Đoan": -2,
    }
    assert pitch_variants_for_preset("Phạm Tuyên", 2) == (0, 1, 2)
    assert pitch_variants_for_preset("Xuân Vĩnh", 2) == (0, -1, 1, 2)
    assert pitch_variants_for_preset("Thái Sơn", 2) == (0, -1, 1, 2)
    assert pitch_variants_for_preset("Thanh Bình", 2) == (0, -1, 1, -2, 2)
    assert pitch_variants_for_preset("Ngọc Trân", 2) == (0, -1, 1, 2)
