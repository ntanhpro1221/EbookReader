from __future__ import annotations

from pathlib import Path

import pytest

from ebook_reader.character_registry import (
    PresetAllocator,
    assert_voice_stability,
    build_registry_and_cast,
)
from ebook_reader.analysis import local_speaker_label
from ebook_reader.config import build_settings
from ebook_reader.database import (
    EXPLICIT_ATTRIBUTION_NOTE,
    ProjectDB,
    canonical_analysis_note,
)
from ebook_reader.voice_catalog import (
    EXCLUDED_PRESETS,
    voice_variant_deviation,
    formant_variants_for_preset,
    formant_ratio_bounds_for_preset,
    VOCAL_TRACT_MIN_CM,
    VOCAL_TRACT_MAX_CM,
    PRESET_VOCAL_TRACT_CM,
    REGISTER_FORMANT_TRADE_PER_SEMITONE,
    base_pitch_for_preset,
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


def _canonical_note(kind: str) -> str:
    return canonical_analysis_note(
        {
            "kind": kind,
            "emotion": "neutral",
            "intensity": 1,
            "pace": "normal",
            "volume": "normal",
        }
    )


def _repair_db(tmp_path: Path, rows: list[dict[str, object]]) -> ProjectDB:
    db = ProjectDB(tmp_path / "repair.sqlite3")
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
    segments = []
    for row in rows:
        kind = str(row["kind"])
        stable_id = str(row["stable_id"])
        segments.append(
            {
                "text_sha256": f"text-{stable_id}",
                "kind_hint": kind,
                "emotion": "neutral",
                "intensity": 1,
                "pace": "normal",
                "volume": "normal",
                "confidence": 0.95,
                "analysis_notes": _canonical_note(kind),
                "status": "analyzed",
                **row,
            }
        )
    db.replace_chapter_segments(chapter_id, segments)
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
        (1, 1, "“Lời của người đàn ông.”", "NPC_LOCAL::c00001::a::người đàn ông trung niên", "male", "adult"),
        (10, 10, "“Lời của giám mục.”", "NPC_LOCAL::c00001::b::giam muc", "male", "adult"),
        (20, 20, "“Lời nguyền đầu tiên!”", "NPC_LOCAL::c00001::c::người phụ nữ mặc áo choàng đen", "female", "adult"),
        (21, 21, "“Điên rồi!”", "NPC_LOCAL::c00001::crowd::phu nu ao choang den", "female", "unknown"),
        (22, 22, "“Độc ác quá!”", "NPC_LOCAL::c00001::crowd::phu nu ao choang den", "female", "unknown"),
        (23, 23, "“Thiêu ả đi!”", "NPC_LOCAL::c00001::crowd::phu nu ao choang den", "female", "unknown"),
        (24, 24, "Những người dân nghèo trên quảng trường gào thét đến lạc giọng.", "NARRATOR", "unknown", "unknown"),
        (30, 30, "“Từ trong biển lửa, ta sẽ chứng kiến tất cả sụp đổ.", "NPC_LOCAL::c00001::d::phu nu ao choang den", "female", "adult"),
        (31, 31, "Ta sẽ chứng kiến các ngươi trầm luân!”", "NPC_LOCAL::c00001::e::thần lửa", "male", "unknown"),
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
                "analysis_notes": _canonical_note(
                    "narration" if speaker == "NARRATOR" else "dialogue"
                ),
                "status": "analyzed",
            }
            for seq, paragraph, text, speaker, gender, age in rows
        ],
    )
    return db


def test_casting_reuses_presets_with_formant_variants_and_never_casts_central(
    tmp_path: Path,
) -> None:
    db = _casting_db(tmp_path)

    build_registry_and_cast(db, build_settings(), lambda _message: None)

    profiles = db.list_voice_profiles()
    assert all(preset_by_name(str(profile["preset_name"]))["style"] != STYLE_NEWS for profile in profiles)
    # Pitch is no longer a diversity axis - it reads as the same person in a different
    # state, not as a different person - so every profile of a preset carries exactly that
    # preset's calibrated reading register. That register comes from listening, and is
    # deliberately not bounded by PRESET_MIN_PITCH_SEMITONES, which bounded the old
    # variant ladder using a UTMOSv2 baseline that disagreed with the listener twice.
    assert all(
        int(profile["pitch_semitones"])
        == base_pitch_for_preset(str(profile["preset_name"]))
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
    # NPCs used to reach a wider pool that added the Central presets. Those voices are
    # excluded from casting entirely now, so the wider pool has to be gone for NPCs too -
    # including through the "nothing left of this gender" fallback.
    assert {preset["region"] for preset in local_presets} <= {REGION_NORTH, REGION_SOUTH}
    assert local_presets

    named_male_profiles = [
        profile_by_id[int(row["voice_profile_id"])]
        for row in named_rows
        if str(row["gender"]) == "male"
    ]
    # A reused preset must come back as a different-sounding person. Formant is the axis
    # that achieves that; pitch alone does not, because speaker identity lives in the
    # formants - a listener comparing -6 to +6 semitones heard the same person throughout.
    formants_by_preset: dict[str, set[float]] = {}
    for profile in named_male_profiles:
        formants_by_preset.setdefault(str(profile["preset_name"]), set()).add(
            round(float(profile["formant_ratio"]), 4)
        )
    assert any(len(formants) > 1 for formants in formants_by_preset.values())
    # The first casting of a preset must be its untouched voice, so it pays no vocoder cost.
    assert any(
        1.0 in formants for formants in formants_by_preset.values()
    )

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
        for preset in casting_presets(GENDER_MALE)
    ]
    female_order = [
        (preset["region"], preset["style"])
        for preset in casting_presets(GENDER_FEMALE)
    ]

    # The Southern natural male voice is Xuân Vĩnh, which a listener excluded outright,
    # so that rank is simply absent rather than filled by someone else.
    assert male_order == [
        (REGION_NORTH, STYLE_NATURAL),
        (REGION_NORTH, STYLE_STORY),
        (REGION_SOUTH, STYLE_STORY),
    ]
    assert female_order == [
        (REGION_NORTH, STYLE_NATURAL),
        (REGION_NORTH, STYLE_NATURAL),
        (REGION_NORTH, STYLE_STORY),
        (REGION_SOUTH, STYLE_STORY),
    ]
    assert REGION_CENTRAL not in {region for region, _style in male_order + female_order}


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


def test_reconciliation_repairs_crowd_and_continuation_without_note_markers(
    tmp_path: Path,
) -> None:
    db = _reconciliation_db(tmp_path)

    build_registry_and_cast(db, build_settings(), lambda _message: None)

    rows = {int(row["seq"]): row for row in db.list_segments()}
    bishop_rows = [rows[1], rows[10]]
    witch_rows = [rows[20], rows[30], rows[31]]
    crowd_rows = [rows[21], rows[22], rows[23]]
    assert len({int(row["canonical_character_id"]) for row in bishop_rows}) == 2
    assert len({int(row["canonical_character_id"]) for row in witch_rows}) == 1
    assert len({int(row["voice_profile_id"]) for row in witch_rows}) == 1
    assert {local_speaker_label(row["speaker"]) for row in crowd_rows} == {"người dân"}
    assert {str(row["gender"]) for row in crowd_rows} == {"unknown"}
    for row in crowd_rows:
        assert str(row["analysis_notes"]) == _canonical_note(str(row["kind"]))

    first_snapshot = {
        seq: (
            str(row["speaker"]),
            str(row["gender"]),
            str(row["age"]),
            str(row["analysis_notes"]),
            int(row["canonical_character_id"]),
            int(row["voice_profile_id"]),
        )
        for seq, row in rows.items()
    }

    build_registry_and_cast(db, build_settings(), lambda _message: None)

    assert {
        int(row["seq"]): (
            str(row["speaker"]),
            str(row["gender"]),
            str(row["age"]),
            str(row["analysis_notes"]),
            int(row["canonical_character_id"]),
            int(row["voice_profile_id"]),
        )
        for row in db.list_segments()
    } == first_snapshot


def test_collective_source_attribution_remains_eligible_for_crowd_repair(
    tmp_path: Path,
) -> None:
    speaker = "NPC_LOCAL::c00001::crowd::người phụ nữ"
    db = _repair_db(
        tmp_path,
        [
            {
                "stable_id": "dialogue",
                "seq": 1,
                "paragraph_index": 7,
                "text": "“Thiêu ả đi!”",
                "kind": "dialogue",
                "speaker": speaker,
                "gender": "female",
                "age": "adult",
            },
            {
                "stable_id": "crowd-attribution",
                "seq": 2,
                "paragraph_index": 7,
                "text": "Những người dân nghèo gào thét đến lạc giọng.",
                "kind": "narration",
                "speaker": "NARRATOR",
                "gender": "unknown",
                "age": "unknown",
            },
        ],
    )

    build_registry_and_cast(db, build_settings(), lambda _message: None)

    dialogue = next(row for row in db.list_segments() if int(row["seq"]) == 1)
    assert local_speaker_label(dialogue["speaker"]) == "người dân"
    assert dialogue["analysis_notes"] == _canonical_note("dialogue")


def test_crowd_repair_uses_source_narration_hint_when_final_kind_is_thought(
    tmp_path: Path,
) -> None:
    db = _repair_db(
        tmp_path,
        [
            {
                "stable_id": "dialogue",
                "seq": 1,
                "paragraph_index": 1,
                "text": "“Đuổi hắn đi!”",
                "kind": "dialogue",
                "speaker": "NPC_LOCAL::c00001::crowd::người đàn ông",
                "gender": "male",
                "age": "adult",
            },
            {
                "stable_id": "source-crowd-thought",
                "seq": 2,
                "paragraph_index": 2,
                "text": "Đám đông đồng loạt hô vang giữa quảng trường.",
                "kind_hint": "narration",
                "kind": "thought",
                "speaker": "NARRATOR",
                "gender": "unknown",
                "age": "unknown",
            },
        ],
    )

    build_registry_and_cast(db, build_settings(), lambda _message: None)

    dialogue = next(row for row in db.list_segments() if int(row["seq"]) == 1)
    assert local_speaker_label(dialogue["speaker"]) == "người dân"


def test_named_source_attribution_stops_crowd_repair_at_individual_boundary(
    tmp_path: Path,
) -> None:
    shared_speaker = "NPC_LOCAL::c00001::shared::người phụ nữ"
    db = _repair_db(
        tmp_path,
        [
            {
                "stable_id": "named-attribution",
                "seq": 1,
                "paragraph_index": 4,
                "text": "Alisa nói:",
                "kind": "narration",
                "speaker": "NARRATOR",
                "gender": "unknown",
                "age": "unknown",
            },
            {
                "stable_id": "protected-dialogue",
                "seq": 2,
                "paragraph_index": 4,
                "text": "“Không được.”",
                "kind": "dialogue",
                "speaker": shared_speaker,
                "gender": "female",
                "age": "adult",
            },
            {
                "stable_id": "crowd-dialogue",
                "seq": 3,
                "paragraph_index": 5,
                "text": "“Thiêu ả đi!”",
                "kind": "dialogue",
                "speaker": shared_speaker,
                "gender": "female",
                "age": "adult",
            },
            {
                "stable_id": "crowd-attribution",
                "seq": 4,
                "paragraph_index": 6,
                "text": "Người dân đồng loạt gào thét ngoài quảng trường.",
                "kind": "narration",
                "speaker": "NARRATOR",
                "gender": "unknown",
                "age": "unknown",
            },
        ],
    )

    build_registry_and_cast(db, build_settings(), lambda _message: None)

    rows = {int(row["seq"]): row for row in db.list_segments()}
    assert str(rows[2]["speaker"]) == shared_speaker
    assert local_speaker_label(rows[3]["speaker"]) == "người dân"


def test_crowd_repair_stops_at_nonconsecutive_source_gap(tmp_path: Path) -> None:
    speaker = "NPC_LOCAL::c00001::crowd::người phụ nữ"
    db = _repair_db(
        tmp_path,
        [
            {
                "stable_id": "before-gap",
                "seq": 1,
                "paragraph_index": 1,
                "text": "“Ta không tham gia.”",
                "kind": "dialogue",
                "speaker": speaker,
                "gender": "female",
                "age": "adult",
            },
            {
                "stable_id": "crowd-dialogue",
                "seq": 3,
                "paragraph_index": 3,
                "text": "“Đuổi hắn đi!”",
                "kind": "dialogue",
                "speaker": speaker,
                "gender": "female",
                "age": "adult",
            },
            {
                "stable_id": "crowd-attribution",
                "seq": 4,
                "paragraph_index": 4,
                "text": "Mọi người đồng loạt hô vang.",
                "kind": "narration",
                "speaker": "NARRATOR",
                "gender": "unknown",
                "age": "unknown",
            },
        ],
    )

    build_registry_and_cast(db, build_settings(), lambda _message: None)

    rows = {int(row["seq"]): row for row in db.list_segments()}
    assert str(rows[1]["speaker"]) == speaker
    assert local_speaker_label(rows[3]["speaker"]) == "người dân"


def test_crowd_repair_stops_at_exact_speaker_identity_boundary(tmp_path: Path) -> None:
    protected_speaker = "NPC_LOCAL::c00001::individual::người phụ nữ"
    crowd_speaker = "NPC_LOCAL::c00001::crowd::người phụ nữ"
    db = _repair_db(
        tmp_path,
        [
            {
                "stable_id": "individual-dialogue",
                "seq": 1,
                "paragraph_index": 1,
                "text": "“Ta không đồng ý.”",
                "kind": "dialogue",
                "speaker": protected_speaker,
                "gender": "female",
                "age": "adult",
            },
            {
                "stable_id": "crowd-dialogue",
                "seq": 2,
                "paragraph_index": 2,
                "text": "“Đuổi hắn đi!”",
                "kind": "dialogue",
                "speaker": crowd_speaker,
                "gender": "female",
                "age": "adult",
            },
            {
                "stable_id": "crowd-attribution",
                "seq": 3,
                "paragraph_index": 3,
                "text": "Dân chúng đồng loạt la hét.",
                "kind": "narration",
                "speaker": "NARRATOR",
                "gender": "unknown",
                "age": "unknown",
            },
        ],
    )

    build_registry_and_cast(db, build_settings(), lambda _message: None)

    rows = {int(row["seq"]): row for row in db.list_segments()}
    assert str(rows[1]["speaker"]) == protected_speaker
    assert local_speaker_label(rows[2]["speaker"]) == "người dân"


def test_cross_batch_continuation_does_not_cross_nonconsecutive_seq_gap(
    tmp_path: Path,
) -> None:
    first_speaker = "NPC_LOCAL::c00001::first::người phụ nữ"
    second_speaker = "NPC_LOCAL::c00001::second::ông lão"
    db = _repair_db(
        tmp_path,
        [
            {
                "stable_id": "before-gap",
                "seq": 1,
                "paragraph_index": 1,
                "text": "“Câu nói còn dang dở.",
                "kind": "dialogue",
                "speaker": first_speaker,
                "gender": "female",
                "age": "adult",
            },
            {
                "stable_id": "after-gap",
                "seq": 3,
                "paragraph_index": 2,
                "text": "Phần tiếp theo không có dấu mở đầu.”",
                "kind": "dialogue",
                "speaker": second_speaker,
                "gender": "male",
                "age": "elderly",
            },
        ],
    )

    build_registry_and_cast(db, build_settings(), lambda _message: None)

    assert {str(row["speaker"]) for row in db.list_segments()} == {
        first_speaker,
        second_speaker,
    }


@pytest.mark.parametrize(
    "analysis_note",
    (
        "Lượt phân tích này chỉ mô tả delivery của câu.",
        canonical_analysis_note(
            {
                "kind": "dialogue",
                "emotion": "neutral",
                "intensity": 1,
                "pace": "normal",
                "volume": "normal",
            },
            (EXPLICIT_ATTRIBUTION_NOTE,),
        ),
        "personality=calm=forged",
    ),
)
def test_casting_does_not_promote_delivery_notes_to_character_personality(
    tmp_path: Path,
    analysis_note: str,
) -> None:
    db = _identity_db(tmp_path, [("ALISA", "female"), ("ALISA", "female")])
    with db.connect() as conn:
        conn.execute("UPDATE segments SET analysis_notes=?", (analysis_note,))

    build_registry_and_cast(db, build_settings(), lambda _message: None)

    character = next(
        row for row in db.list_characters() if str(row["display_name"]) == "ALISA"
    )
    assert character["personality"] == ""
    assert {str(row["analysis_notes"]) for row in db.list_segments()} == {
        analysis_note
    }


def test_casting_accepts_only_validated_legacy_personality_prefix(
    tmp_path: Path,
) -> None:
    db = _identity_db(tmp_path, [("ALISA", "female"), ("ALISA", "female")])
    with db.connect() as conn:
        conn.execute(
            "UPDATE segments SET analysis_notes='personality=calm and deliberate'"
        )

    build_registry_and_cast(db, build_settings(), lambda _message: None)

    character = next(
        row for row in db.list_characters() if str(row["display_name"]) == "ALISA"
    )
    assert character["personality"] == "calm and deliberate"


def test_legacy_personality_metadata_does_not_merge_distinct_local_identities(
    tmp_path: Path,
) -> None:
    speakers = [
        "NPC_LOCAL::c00001::batch-a::người đàn ông trung niên",
        "NPC_LOCAL::c00001::batch-b::giám mục",
    ]
    db = _identity_db(tmp_path, [(speaker, "male") for speaker in speakers])
    with db.connect() as conn:
        conn.execute("UPDATE segments SET analysis_notes='personality=priest'")

    build_registry_and_cast(db, build_settings(), lambda _message: None)

    rows = db.list_segments()
    assert {str(row["speaker"]) for row in rows} == set(speakers)
    assert len({int(row["canonical_character_id"]) for row in rows}) == 2


def test_relational_description_is_not_merged_with_named_character(tmp_path: Path) -> None:
    db = _identity_db(
        tmp_path,
        [("FELICIA", "female"), ("MẸ CỦA FELICIA", "female")],
    )

    build_registry_and_cast(db, build_settings(), lambda _message: None)

    rows = db.list_segments()
    assert {str(row["speaker"]) for row in rows} == {"FELICIA", "MẸ CỦA FELICIA"}
    assert len({int(row["canonical_character_id"]) for row in rows}) == 2


def test_gender_conflict_no_longer_fails_the_whole_book(tmp_path: Path) -> None:
    """Cho tới 2026-09-09, chỗ này ném lỗi và **cả cuốn sách dừng**.

    Lý lẽ cũ đúng theo nghĩa của nó: đừng đúc giọng khi còn chưa biết nhân vật là nam hay nữ.
    Cái nó không lường là cái giá. Lô 1 chết ở đây **sau 4 giờ phân tích trọn vẹn 3.727 đoạn**,
    vì một nhân vật phụ có đúng hai câu thoại mà model gán một nữ một nam — và vì `resume` bị
    từ chối sau khi sửa mã, toàn bộ 4 giờ ấy mất trắng chứ không chỉ phần còn lại.

    Đây là cổng đắt nhất trong dự án: chương hỏng thì mất một chương, cổng này hỏng thì mất cả
    cuốn, ngay sau khi đã trả xong phần đắt nhất của lượt chạy. Và nó vi phạm nguyên tắc đã
    chốt ở docs/SHIPPING_WITHOUT_A_LISTENER.md — *một phép kiểm không phán xử được thì không
    được chặn*.

    **Ngưỡng bằng chứng KHÔNG được hạ** để bù. Đo trên mọi project đã lưu, bằng chứng văn bản
    nhất trí ở 3 hit mâu thuẫn với model 5 lần trên 13, ở 1 hit là 17 khớp / 18 lệch — tức tung
    đồng xu. `GENDER_EVIDENCE_MINIMUM_HITS = 5` không tuỳ tiện; hạ nó là mua một lỗi im lặng để
    tránh một lỗi ồn ào. Cái đổi là **hậu quả**, không phải ngưỡng.
    """
    said: list[str] = []
    db = _identity_db(tmp_path, [("CAMIL", "female"), ("Camil", "male")])

    build_registry_and_cast(db, build_settings(), said.append)

    assert db.list_voice_profiles(), "phải đúc giọng và đi tiếp, không dừng cả cuốn sách"
    assert any("CAMIL" in line for line in said), "và phải nói ra tên nhân vật ấy"
    assert any("cli cast" in line for line in said), "kèm cách sửa"
    codes = {str(row["code"]) for row in db.list_events()}
    assert "CASTING_GENDER_UNRESOLVED" in codes, "không im lặng: phải có sự kiện để vào báo cáo"


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

    # Lucien's spoken lines and his inner monologue are all his: a thought is read in the
    # voice of whoever is thinking it, so it no longer gets handed to the narrator.
    assert len(lucien_rows) == 3
    assert len({int(row["canonical_character_id"]) for row in lucien_rows}) == 1
    assert len({int(row["voice_profile_id"]) for row in lucien_rows}) == 1
    assert ha_phong_rows[0]["canonical_character_id"] != lucien_rows[0]["canonical_character_id"]
    # The thought keeps its thinker rather than being rewritten to NARRATOR, and it is
    # read in exactly the voice that speaker uses elsewhere.
    assert {str(row["speaker"]) for row in thought_rows} == {"Lucien"}
    assert {int(row["voice_profile_id"]) for row in thought_rows} == {
        int(lucien_rows[0]["voice_profile_id"])
    }


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


def test_central_presets_are_never_cast_through_any_path() -> None:
    """Removing a region is only real if every path that reaches presets respects it.

    `choose` has a fallback for when nothing of the requested gender is left, and that
    fallback used to scan the whole catalogue - which would have put the excluded Central
    presets straight back into the book.
    """
    for gender in (GENDER_MALE, GENDER_FEMALE):
        assert all(
            preset["region"] != REGION_CENTRAL for preset in casting_presets(gender)
        )

    central = [preset for preset in VIENEU_PRESETS if preset["region"] == REGION_CENTRAL]
    assert central, "the catalogue should still describe the presets VieNeu offers"
    for preset in central:
        # Still resolvable, so a book that locked one before the change keeps working.
        assert preset_by_name(str(preset["name"]))["region"] == REGION_CENTRAL


def test_formant_range_follows_each_preset_vocal_tract() -> None:
    """One shared warp range is wrong, and wrong in opposite directions per voice.

    A warp by ratio r reads as a vocal tract of length L/r. The male presets measure
    16.4-16.9 cm and the female ones 13.9-15.5 cm, so a male voice has little room left to
    go deeper while a female voice has little room to go brighter. The upper bound
    reproduces what a Vietnamese listener found by ear: Thanh Bình sounded muffled at 0.82,
    which is a 20.6 cm tract, and acceptable at 0.86, which is 19.7 cm.
    """
    for name, length in PRESET_VOCAL_TRACT_CM.items():
        lower, upper = formant_ratio_bounds_for_preset(name)
        # Anatomy: the warped tract stays inside the adult range. A preset whose register
        # was lowered stops short of the anatomical floor, never past it.
        assert VOCAL_TRACT_MIN_CM - 0.05 <= length / upper
        assert length / lower <= VOCAL_TRACT_MAX_CM + 0.05
        # The algorithm has its own limit regardless of anatomy, and it is asymmetric and
        # mirrored between the genders: a male voice tolerates being brightened further
        # than deepened, a female voice the reverse. The usable range is the intersection,
        # so neither constraint alone may be exceeded.
        down, up = voice_variant_deviation(name)
        assert lower >= 1.0 - down - 1e-6
        assert upper <= 1.0 + up + 1e-6
        for ratio in formant_variants_for_preset(name):
            assert lower - 1e-6 <= ratio <= upper + 1e-6

    # The two constraints bind opposite ends for the two genders: a long male tract is
    # held back by anatomy going deeper and by the algorithm going brighter, and a short
    # female tract the other way round. Read on a preset with no register shift, so the
    # anatomical bound is the only thing setting the floor.
    assert base_pitch_for_preset("Thái Sơn") == 0
    male_length = PRESET_VOCAL_TRACT_CM["Thái Sơn"]
    male_low, male_high = formant_ratio_bounds_for_preset("Thái Sơn")
    assert male_low == pytest.approx(male_length / VOCAL_TRACT_MAX_CM, abs=0.005)
    assert male_high == pytest.approx(1.0 + voice_variant_deviation("Thái Sơn")[1], abs=0.005)
    female_length = PRESET_VOCAL_TRACT_CM["Ngọc Linh"]
    female_low, female_high = formant_ratio_bounds_for_preset("Ngọc Linh")
    assert female_low == pytest.approx(1.0 - voice_variant_deviation("Ngọc Linh")[0], abs=0.005)
    assert female_high == pytest.approx(female_length / VOCAL_TRACT_MIN_CM, abs=0.005)

    # A long male tract cannot go as deep as a short female one, and vice versa.
    male_low, male_high = formant_ratio_bounds_for_preset("Thái Sơn")
    female_low, female_high = formant_ratio_bounds_for_preset("Ngọc Linh")
    assert male_low > female_low
    assert male_high > female_high

    # The two genders get mirrored allowances, which is the whole point of splitting them.
    assert voice_variant_deviation("Thái Sơn") == (0.15, 0.20)
    assert voice_variant_deviation("Ngọc Linh") == (0.20, 0.15)

    # Every preset keeps its untouched voice as the first casting.
    for name in PRESET_VOCAL_TRACT_CM:
        assert formant_variants_for_preset(name)[0] == 1.0


def test_a_lowered_register_spends_part_of_the_formant_range() -> None:
    """F0 and formants both make a speaker sound large, so they draw on one budget.

    Anatomy cannot see this. Lowering F0 leaves the spectral envelope alone, so the
    estimated vocal tract after a register shift is exactly what it was before - yet the
    voice is heard as deeper and has less room left to be deepened further. A Vietnamese
    listener put Thanh Bình's floor at 0.86 on the raw preview and at 0.90 once the -4
    semitone register was applied, which is the rate this encodes.
    """
    shifted = "Thanh Bình"
    assert base_pitch_for_preset(shifted) == -4
    lower, upper = formant_ratio_bounds_for_preset(shifted)
    length = PRESET_VOCAL_TRACT_CM[shifted]
    spent = 4 * REGISTER_FORMANT_TRADE_PER_SEMITONE

    # The floor sits above the anatomical one by exactly what the register spent.
    assert lower == pytest.approx(length / VOCAL_TRACT_MAX_CM + spent, abs=1e-6)
    assert lower == pytest.approx(0.90, abs=0.005)
    # The window moved, so the deepest reachable tract is shorter than anatomy alone allows.
    assert length / lower < VOCAL_TRACT_MAX_CM
    # The transform's own limit still caps the top; a moved window may not exceed it.
    assert upper == pytest.approx(1.0 + voice_variant_deviation(shifted)[1], abs=1e-6)
    for ratio in formant_variants_for_preset(shifted):
        assert lower - 1e-6 <= ratio <= upper + 1e-6

    # A preset at its native register is untouched by the rule.
    for name in PRESET_VOCAL_TRACT_CM:
        if base_pitch_for_preset(name):
            continue
        native_low, _ = formant_ratio_bounds_for_preset(name)
        anatomical = PRESET_VOCAL_TRACT_CM[name] / VOCAL_TRACT_MAX_CM
        algorithmic = 1.0 - voice_variant_deviation(name)[0]
        assert native_low == pytest.approx(max(anatomical, algorithmic), abs=1e-6)


def test_one_character_cannot_hold_two_voices_through_different_labels(tmp_path: Path) -> None:
    """The stability check must follow the character, not the label on each line.

    A boy in a real run appeared as a named character in one place and as a local NPC in
    another, and held two voices three semitones apart. Every label had exactly one voice,
    so a per-label check reported success - and local labels were skipped outright, which
    widened the hole rather than narrowing it. The guarantee is about people, not strings.
    """

    class _Rows:
        def __init__(self, rows):
            self._rows = rows

        def list_segments(self):
            return self._rows

    same_person = 7
    rows = [
        {
            "speaker": "NPC_LOCAL::c00001::rabc::cậu bé",
            "canonical_character_id": same_person,
            "voice_profile_id": 11,
        },
        {
            "speaker": "Iven",
            "canonical_character_id": same_person,
            "voice_profile_id": 12,
        },
    ]

    with pytest.raises(RuntimeError, match="character resolved to multiple voice profiles"):
        assert_voice_stability(_Rows(rows))

    # The same two lines with one voice between them are accepted.
    rows[1]["voice_profile_id"] = 11
    assert_voice_stability(_Rows(rows)) is None


def test_an_excluded_preset_is_unreachable_through_every_path() -> None:
    """A voice the listener rejected must not come back through a fallback.

    This exact shape of hole let the Central presets back in once: the main catalogue
    filtered them and two fallback pools iterated the raw preset list instead. A ranking
    penalty was tried first and was not enough either - it made the voice a last resort
    rather than never, and a last resort is still reached once the pool runs thin.
    """
    for gender in ("male", "female"):
        assert not {
            str(preset["name"]) for preset in casting_presets(gender)
        } & EXCLUDED_PRESETS

    chosen: set[str] = set()
    for narrator in ("Phạm Tuyên", "Thanh Bình"):
        allocator = PresetAllocator(narrator, 2)
        # Deep enough to exhaust every pool and force both fallback branches.
        for round_index in range(30):
            for gender in ("male", "female", "unknown"):
                for age in ("child", "teen", "adult", "elderly", "unknown"):
                    preset, _ratio, _pitch = allocator.choose(
                        gender, npc=round_index % 2 == 0, age=age
                    )
                    chosen.add(str(preset["name"]))

    assert chosen, "the sweep must actually cast something"
    assert not chosen & EXCLUDED_PRESETS
