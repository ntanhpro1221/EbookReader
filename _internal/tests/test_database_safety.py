from __future__ import annotations

import copy
import json
import sqlite3
import unicodedata
from contextlib import closing
from pathlib import Path

import pytest

from ebook_reader.analysis import _analysis_context_hash, _original_neighbor_context
from ebook_reader.asr import (
    ASR_LOCKED_NAME_ANCHOR_MISMATCH,
    LOCKED_NAME_ANCHOR_METRICS_KEY,
    LOCKED_NAME_ANCHOR_METRICS_VERSION,
)
from ebook_reader.database import (
    ANALYSIS_CHAPTER_HEADING_CONFIDENCE,
    ANALYSIS_CHAPTER_HEADING_DELIVERY,
    ANALYSIS_CONTEXT_POLICY_NARRATION_BEFORE_NEXT_PARAGRAPH_THOUGHT,
    ANALYSIS_CONTEXT_POLICY_NARRATION_BEFORE_THOUGHT,
    ANALYSIS_CONTEXT_POLICY_PREVIOUS_ONLY,
    ANALYSIS_CONTEXT_SOURCE_KIND_RULE,
    ANALYSIS_SOURCE_DIALOGUE_KIND_RULE,
    ANALYSIS_CRITIC_EVIDENCE_POLICY_PER_ID_SOURCE_ANCHOR,
    ANALYSIS_CRITIC_EVIDENCE_POLICY_SINGLETON_SOURCE_ANCHOR,
    ANALYSIS_CRITIC_EVIDENCE_POLICY_SINGLETON_FULL_TARGET,
    ANALYSIS_CRITIC_EVIDENCE_QUOTE_MAX_LENGTH,
    ANALYSIS_DIRECTOR_CRITIC_POLICY_VERSION,
    ANALYSIS_DIRECTOR_RETRY_SCHEMA_POLICY_VERSION,
    ANALYSIS_HOST_AFFECT_POLICY_VERSION,
    ANALYSIS_HOST_SEMANTIC_POLICY_VERSION,
    ANALYSIS_HOST_STRUCTURAL_POLICY_VERSION,
    CHAPTER_POST_ENCODE_QUALITY_STAGE,
    CONTINUED_DIALOGUE_LOCK_NOTE,
    GENERATION_DELIVERY_CLARITY,
    GENERATION_DELIVERY_PRIMARY,
    QUALITY_SCOPE_CHAPTER,
    QUALITY_SCOPE_SEGMENT,
    QUALITY_VERDICT_PASS,
    SCHEMA_VERSION,
    SEGMENT_ASR_DECODE_QUALITY_STAGE,
    SEGMENT_AUDIO_QUALITY_STAGE,
    SEGMENT_PERCEPTUAL_QUALITY_STAGE,
    ProjectDB,
    analysis_critic_candidate_hash,
    analysis_critic_speaker_is_candidate_bound,
    analysis_expected_critic_compatibility_override,
    analysis_critic_anchor_set_sha256,
    analysis_critic_per_id_anchor_map_sha256,
    analysis_source_narration_precedes_next_paragraph_thought,
    analysis_source_narration_precedes_thought,
    analysis_source_has_recalled_persistent_fear,
    analysis_source_has_sleep_paralysis_helplessness,
    analysis_source_has_stunned_blank_mind,
    canonical_analysis_note,
    canonical_analysis_critic_allowed_speakers,
    canonical_analysis_critic_per_id_source_anchor_map,
    canonical_analysis_critic_source_anchors,
)
from ebook_reader.io_utils import sha256_file, sha256_text
from ebook_reader.models import CONTEXTUAL_ENGLISH_NAME_PRONUNCIATION_SOURCE
from ebook_reader.config import build_settings
from ebook_reader.tts import TTSCoordinator


ANALYSIS_MODEL_NAME = "qwen3:8b"
ANALYSIS_MODEL_DIGEST = "sha256:analysis-model"
ANALYSIS_MODEL_COMMIT = {
    "analysis_model_name": ANALYSIS_MODEL_NAME,
    "analysis_model_digest": ANALYSIS_MODEL_DIGEST,
}
ANALYSIS_POLICY_FINGERPRINT = "director-policy-v2"
ANALYSIS_GROUP_FINGERPRINT = "group-source-v1"
ANALYSIS_CONTEXT_HASH = "group-context-v1"
RECALLED_PERSISTENT_FEAR_TEXT = (
    "Giấc mơ này chân thực tới dị thường, khiến cho Hạ Phong đến giờ nghĩ lại "
    "vẫn tim đập chân run. Cộng thêm việc không cảm nhận thấy sự tồn tại của "
    "ngọn lửa, cậu bèn ngồi thừ người ra, một lúc lâu vẫn chưa hoàn hồn."
)
STUNNED_BLANK_MIND_TEXT = (
    "Nhưng tới khi Hạ Phong nhìn ra phía trước, chuẩn bị đứng lên và thu lại sách "
    "tham khảo để trở về ký túc xá, một cảnh tượng kỳ lạ không sao tưởng tượng "
    "được bỗng đập thẳng vào mắt cậu. Giống như thể bị một cây chùy lớn nện vào "
    "đầu, cậu đực mặt ra, đầu óc một mảng trắng xóa."
)
V28_SEQ10_SLEEP_PARALYSIS_TEXT = (
    "Giống như mấy lần bị bóng đè trước đây, cậu biết rõ mình đang nằm mơ, "
    "muốn thoát ra nhưng lại không có sức lực, không thể điều khiển bản thân."
)
V28_SEQ10_SLEEP_PARALYSIS_STABLE_ID = "c00001_s0000010_c5b601fe6b9d"
V28_SEQ10_SLEEP_PARALYSIS_TEXT_SHA256 = (
    "c5b601fe6b9dd8f87e3697be5f615b3392d9569a9b6cde44ca85b57e93587274"
)
DIRECT_NARRATION_AFFECT_LOCK_CASES = (
    (
        RECALLED_PERSISTENT_FEAR_TEXT,
        "narration_recalled_persistent_fear",
        "recalled_persistent_fear",
        ("afraid",),
        "afraid",
        "surprised",
    ),
    (
        STUNNED_BLANK_MIND_TEXT,
        "narration_stunned_blank_mind",
        "stunned_blank_mind",
        ("surprised",),
        "surprised",
        "afraid",
    ),
)
V21_SEQ12_PREVIOUS_TEXT = (
    "Sau khi quả tim đang đập bình bịch trong lồng ngực bình tĩnh trở lại, Hạ "
    "Phong mới tập trung tinh thần, nhớ ra bản thân đang thâu đêm làm dở bài "
    "luận văn tốt nghiệp tại phòng đọc mở cửa 24/24 trong thư viện tổng hợp của "
    "trường. Cậu bèn thầm cười giễu:"
)
V21_SEQ13_THOUGHT_TEXT = (
    "‘Mấy ngày gần đây toàn sinh hoạt bất quy tắc kiểu cú đêm thế này, bảo sao "
    "không mơ thấy ác mộng chân thực như vậy cơ chứ.’"
)
V21_SEQ12_STABLE_ID = "c00001_s0000012_040f30f9df84"
V21_SEQ13_STABLE_ID = "c00001_s0000013_3addf4e2e280"
V21_SEQ13_TEXT_SHA256 = (
    "3addf4e2e280f94186326177ddaa1a5b75c1fa6e7b6fa0f522de8b2bad1ab8b2"
)
V26_SEQ18_TEXT = (
    "Hạ Phong dù là một người tính cách có chút hướng nội, rụt rè, phản ứng không "
    "đủ nhanh, nhưng lúc này vẫn nhận thấy được mọi chuyện rất sai: dẫu cho có cháy "
    "thật, và cậu được người ta đưa tới bệnh viện đi chăng nữa, thì nơi này cũng "
    "chẳng giống bệnh viện tí nào!"
)
V26_SEQ18_TEXT_SHA256 = (
    "9acd51b63f0675c74dc5c0d91d75cd66fbb9af44a9815b381431f4d4598546c7"
)
V27_MAX_UNICODE_NO_WHITESPACE_TEXT = "".join(
    chr(0x4E00 + index) for index in range(340)
)
V27_SEQ31_PREVIOUS_TEXT = "“Thiêu chết ả phù thủy tà ác khốn kiếp đó đi!”"
V27_SEQ32_NARRATION_TEXT = (
    "Sợ hãi và phấn khích, hai thứ xúc cảm đối lập, hiện rõ trong giọng nói xa "
    "lạ đó. Nỗi lo sợ của Hạ Phong bị gián đoạn. Cảm thấy tò mò, cậu nghĩ thầm:"
)
V27_SEQ33_THOUGHT_TEXT = "‘Phù thủy? Thế giới này là cái quái gì vậy?’"
V27_SEQ32_STABLE_ID = "c00001_s0000032_ee14f5622d9a"
V29_SEQ37_PREVIOUS_TEXT = "“Anh tỉnh rồi?”"
V29_SEQ38_NARRATION_TEXT = (
    "Nhìn bộ trang phục mang phong cách cổ xưa khác hẳn với hiện đại của cậu bé, "
    "Hạ Phong máy móc gật đầu, trong tâm trí hỗn loạn nảy ra một ý nghĩ nực cười:"
)
V29_SEQ39_THOUGHT_TEXT = (
    "‘Lucien, phù thủy, giáo đường, thiêu chết… Lẽ nào mình thật sự đã chuyển sinh? "
    "Và còn chuyển sinh đến thời kỳ hắc ám có tục săn phù thủy ở châu Âu Trung Cổ nữa?’"
)
V29_SEQ38_STABLE_ID = "c00001_s0000038_6d1eebb237de"
V29_SEQ39_STABLE_ID = "c00001_s0000039_55abbb7a19a4"
V30_SEQ23_PREVIOUS_TEXT = (
    "Bên kia cánh cửa gỗ lung lay sắp rớt là một cái bếp lò nhìn không ra màu "
    "sắc ban đầu, bên trên treo một chiếc bình sành."
)
V30_SEQ24_NARRATION_TEXT = (
    "Mọi thứ đều thật xa lạ, Hạ Phong căn bản không thể đoán được mình đang ở "
    "đâu. Mà cảm giác yếu ớt cứ không ngừng lan ra càng khiến đầu óc cậu hỗn loạn."
)
V30_SEQ25_THOUGHT_TEXT = "‘Đây rốt cuộc là nơi nào?!"
V30_SEQ24_STABLE_ID = "c00001_s0000024_3ab59bb4bd38"
V30_SEQ25_STABLE_ID = "c00001_s0000025_1582edb61545"
V32_SEQ43_DIALOGUE_TEXT = (
    "“Mẹ vẫn không chịu tin em, nửa đêm cứ len lén khóc, mắt sưng vù lên hết cả. "
    "Bà ấy lặp đi lặp lại ‘Evans bé nhỏ tội nghiệp’ hết lần này đến lần khác, "
    "cứ như thể anh đã bị đem đi chôn ở nghĩa trang rồi ấy."
)


def _canonical_analysis_data(**overrides: object) -> dict:
    data = {
        "kind": "narration",
        "speaker": "NARRATOR",
        "gender": "unknown",
        "age": "unknown",
        "emotion": "neutral",
        "intensity": 1,
        "pace": "normal",
        "volume": "normal",
        "confidence": 0.9,
        "personality_hint": "",
        "notes": "",
    }
    data.update(overrides)
    data["notes"] = canonical_analysis_note(data)
    return data


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


def _analysis_batch_db(
    tmp_path: Path,
    *,
    lock_model: bool = True,
    texts: tuple[str, ...] = ("Text 1", "Text 2"),
    kind_hints: tuple[str, ...] | None = None,
) -> tuple[ProjectDB, list[dict]]:
    resolved_kind_hints = kind_hints or tuple("narration" for _text in texts)
    if len(resolved_kind_hints) != len(texts):
        raise ValueError("Analysis test texts and kind hints must have equal lengths")
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
                "stable_id": f"c1s{index}",
                "seq": index - 1,
                "text": text,
                "text_sha256": sha256_text(text),
                "kind_hint": kind_hint,
            }
            for index, (text, kind_hint) in enumerate(
                zip(texts, resolved_kind_hints, strict=True),
                1,
            )
        ],
    )
    if lock_model:
        db.lock_analysis_model(ANALYSIS_MODEL_NAME, ANALYSIS_MODEL_DIGEST)
    return db, [dict(row) for row in db.list_segments()]


def _analysis_acceptance_envelope(
    source_rows: list[dict],
    *,
    emotion: str = "neutral",
    previous_text_by_stable_id: dict[str, str] | None = None,
) -> dict:
    segments = []
    critic_rows = []
    source_by_position = {
        (int(row["chapter_id"]), int(row["seq"])): row for row in source_rows
    }
    previous_overrides = previous_text_by_stable_id or {}
    for index, row in enumerate(source_rows, 1):
        source_kind = str(row["kind_hint"])
        stable_id = str(row["stable_id"])
        previous = source_by_position.get(
            (int(row["chapter_id"]), int(row["seq"]) - 1)
        )
        next_row = source_by_position.get(
            (int(row["chapter_id"]), int(row["seq"]) + 1)
        )
        masks_following_thought = analysis_source_narration_precedes_thought(
            chapter_id=int(row["chapter_id"]),
            seq=int(row["seq"]),
            paragraph_index=int(row["paragraph_index"]),
            kind_hint=source_kind,
            next_chapter_id=(
                int(next_row["chapter_id"]) if next_row is not None else None
            ),
            next_seq=int(next_row["seq"]) if next_row is not None else None,
            next_paragraph_index=(
                int(next_row["paragraph_index"]) if next_row is not None else None
            ),
            next_kind_hint=(
                str(next_row["kind_hint"]) if next_row is not None else ""
            ),
        )
        masks_next_paragraph_thought = (
            analysis_source_narration_precedes_next_paragraph_thought(
                chapter_id=int(row["chapter_id"]),
                seq=int(row["seq"]),
                paragraph_index=int(row["paragraph_index"]),
                kind_hint=source_kind,
                next_chapter_id=(
                    int(next_row["chapter_id"]) if next_row is not None else None
                ),
                next_seq=int(next_row["seq"]) if next_row is not None else None,
                next_paragraph_index=(
                    int(next_row["paragraph_index"])
                    if next_row is not None
                    else None
                ),
                next_kind_hint=(
                    str(next_row["kind_hint"]) if next_row is not None else ""
                ),
            )
        )
        previous_text = previous_overrides.get(
            stable_id,
            str(previous["text"])[-500:] if previous is not None else "",
        )
        data = {
            "kind": "narration",
            "speaker": "NARRATOR",
            "gender": "unknown",
            "age": "unknown",
            "emotion": emotion,
            "intensity": 1,
            "pace": "normal",
            "volume": "normal",
            "confidence": 0.9,
            "personality_hint": "",
            "notes": "",
        }
        data["notes"] = canonical_analysis_note(data)
        segments.append(
            {
                "segment_id": int(row["id"]),
                "stable_id": stable_id,
                "text_sha256": str(row["text_sha256"]),
                "data": data,
            }
        )
        critic_rows.append(
            {
                "id": f"S{index:03d}",
                "paragraph": int(row["paragraph_index"]),
                "hint": source_kind,
                "source_role": "content",
                "context_policy": (
                    ANALYSIS_CONTEXT_POLICY_PREVIOUS_ONLY
                    if source_kind == "thought"
                    else ANALYSIS_CONTEXT_POLICY_NARRATION_BEFORE_THOUGHT
                    if masks_following_thought
                    else ANALYSIS_CONTEXT_POLICY_NARRATION_BEFORE_NEXT_PARAGRAPH_THOUGHT
                    if masks_next_paragraph_thought
                    else "adjacent_context"
                ),
                "host_locked_fields": (
                    {"kind": "narration"} if masks_following_thought else {}
                ),
                "previous_text": (
                    previous_text
                    if source_kind == "thought"
                    or masks_following_thought
                    or masks_next_paragraph_thought
                    else ""
                ),
                "text": str(row["text"]),
                "next_text": "",
                "candidate": {
                    key: data[key]
                    for key in ("kind", "speaker", "emotion", "intensity", "pace", "volume")
                },
                "batch_signature_count": len(source_rows),
            }
        )
    return {
        "segments": segments,
        "pronunciations": [],
        "critic_rows": critic_rows,
    }


def _thought_acceptance_envelope(
    source_rows: list[dict],
    *,
    previous_text_by_stable_id: dict[str, str] | None = None,
) -> dict:
    envelope = _analysis_acceptance_envelope(
        source_rows,
        previous_text_by_stable_id=previous_text_by_stable_id,
    )
    for index, source_row in enumerate(source_rows):
        if str(source_row["kind_hint"]) != "thought":
            raise ValueError("Thought envelope helper requires thought source rows")
        envelope["segments"][index]["data"].update(
            {"kind": "thought", "intensity": 0}
        )
        _refresh_analysis_note(envelope, index)
        envelope["critic_rows"][index]["candidate"].update(
            {"kind": "thought", "intensity": 0}
        )
    return envelope


def _dialogue_acceptance_envelope(source_rows: list[dict]) -> dict:
    envelope = _analysis_acceptance_envelope(source_rows)
    for index, source_row in enumerate(source_rows):
        if str(source_row["kind_hint"]) != "dialogue":
            raise ValueError("Dialogue envelope helper requires dialogue source rows")
        data = envelope["segments"][index]["data"]
        data.update(
            {
                "kind": "dialogue",
                "speaker": "NPC_LOCAL::c00001::v32-source-unit::cậu bé",
                "gender": "male",
                "age": "child",
                "emotion": "sad",
                "intensity": 2,
            }
        )
        _refresh_analysis_note(envelope, index)
        critic_row = envelope["critic_rows"][index]
        critic_row["candidate"].update(
            {
                "kind": "dialogue",
                "speaker": data["speaker"],
                "emotion": "sad",
                "intensity": 2,
            }
        )
        critic_row["host_locked_fields"] = {"kind": "dialogue"}
    return envelope


def _dialogue_kind_override_evidence(
    envelope: dict,
    *,
    corrected_speaker: str | None = None,
) -> dict:
    evidence = _accepted_critic_evidence(envelope)
    item = evidence["segments"][0]
    candidate = item["candidate"]
    item["critic"].update(
        {
            "accept": False,
            "kind": "thought",
            "rationale": "Critic nhầm lời thoại thành câu hỏi nội tâm.",
        }
    )
    corrected_fields = {"kind": "thought"}
    if corrected_speaker is not None:
        item["critic"]["speaker"] = corrected_speaker
        corrected_fields["speaker"] = corrected_speaker
    raw_deltas = [
        f"{field}:{candidate[field]}->{corrected_fields[field]}"
        for field in ("kind", "speaker", "emotion", "intensity", "pace", "volume")
        if field in corrected_fields and corrected_fields[field] != candidate[field]
    ]
    covered_deltas = [delta for delta in raw_deltas if delta.startswith("kind:")]
    unresolved_deltas = [
        delta for delta in raw_deltas if not delta.startswith("kind:")
    ]
    item["field_deltas"] = raw_deltas
    item["effective_accept"] = not unresolved_deltas
    item["host_source_kind_override"] = {
        "policy_version": ANALYSIS_HOST_SEMANTIC_POLICY_VERSION,
        "stable_id": item["stable_id"],
        "text_sha256": item["text_sha256"],
        "rule": ANALYSIS_SOURCE_DIALOGUE_KIND_RULE,
        "field": "kind",
        "candidate_value": "dialogue",
        "allowed_values": ["dialogue"],
        "raw_accept": False,
        "raw_field_deltas": raw_deltas,
        "covered_field_deltas": covered_deltas,
        "unresolved_field_deltas": unresolved_deltas,
    }
    return evidence


def _v21_thought_context_db(
    tmp_path: Path,
) -> tuple[ProjectDB, list[dict], dict]:
    db, _source_rows = _analysis_batch_db(
        tmp_path,
        texts=(V21_SEQ12_PREVIOUS_TEXT, V21_SEQ13_THOUGHT_TEXT),
        kind_hints=("narration", "thought"),
    )
    with db.connect() as conn:
        conn.execute(
            "UPDATE segments SET seq=seq+12,paragraph_index=paragraph_index+12"
        )
        conn.execute(
            "UPDATE segments SET stable_id=CASE seq WHEN 12 THEN ? ELSE ? END",
            (V21_SEQ12_STABLE_ID, V21_SEQ13_STABLE_ID),
        )
    source_rows = [dict(row) for row in db.list_segments()]
    previous_row, thought_row = source_rows
    envelope = _thought_acceptance_envelope(
        [thought_row],
        previous_text_by_stable_id={
            str(thought_row["stable_id"]): str(previous_row["text"])[-500:]
        },
    )
    return db, source_rows, envelope


def _v28_v27_narration_before_thought_db(
    tmp_path: Path,
) -> tuple[ProjectDB, list[dict], dict]:
    db, _source_rows = _analysis_batch_db(
        tmp_path,
        texts=(
            V27_SEQ31_PREVIOUS_TEXT,
            V27_SEQ32_NARRATION_TEXT,
            V27_SEQ33_THOUGHT_TEXT,
        ),
        kind_hints=("dialogue", "narration", "thought"),
    )
    with db.connect() as conn:
        conn.execute(
            "UPDATE segments SET seq=seq+31,"
            "paragraph_index=CASE seq WHEN 0 THEN 29 ELSE 30 END,"
            "stable_id=CASE seq WHEN 0 THEN 'c00001_s0000031_v28' "
            "WHEN 1 THEN ? ELSE 'c00001_s0000033_v28' END",
            (V27_SEQ32_STABLE_ID,),
        )
    source_rows = [dict(row) for row in db.list_segments()]
    envelope = _analysis_acceptance_envelope([source_rows[1]])
    target_critic_row = envelope["critic_rows"][0]
    target_critic_row["context_policy"] = (
        ANALYSIS_CONTEXT_POLICY_NARRATION_BEFORE_THOUGHT
    )
    target_critic_row["host_locked_fields"] = {"kind": "narration"}
    target_critic_row["previous_text"] = V27_SEQ31_PREVIOUS_TEXT[-500:]
    target_critic_row["next_text"] = ""
    return db, source_rows, envelope


def _v30_v29_seq38_narration_before_thought_db(
    tmp_path: Path,
) -> tuple[ProjectDB, list[dict], dict]:
    db, _source_rows = _analysis_batch_db(
        tmp_path,
        texts=(
            V29_SEQ37_PREVIOUS_TEXT,
            V29_SEQ38_NARRATION_TEXT,
            V29_SEQ39_THOUGHT_TEXT,
        ),
        kind_hints=("dialogue", "narration", "thought"),
    )
    with db.connect() as conn:
        conn.execute(
            "UPDATE segments SET seq=seq+37,"
            "paragraph_index=CASE seq WHEN 0 THEN 32 ELSE 33 END,"
            "stable_id=CASE seq WHEN 0 THEN 'c00001_s0000037_v30' "
            "WHEN 1 THEN ? ELSE ? END",
            (V29_SEQ38_STABLE_ID, V29_SEQ39_STABLE_ID),
        )
    source_rows = [dict(row) for row in db.list_segments()]
    envelope = _analysis_acceptance_envelope([source_rows[1]])
    target_critic_row = envelope["critic_rows"][0]
    target_critic_row["context_policy"] = (
        ANALYSIS_CONTEXT_POLICY_NARRATION_BEFORE_THOUGHT
    )
    target_critic_row["host_locked_fields"] = {"kind": "narration"}
    target_critic_row["previous_text"] = V29_SEQ37_PREVIOUS_TEXT
    target_critic_row["next_text"] = ""
    return db, source_rows, envelope


def _v31_v30_seq24_next_paragraph_thought_db(
    tmp_path: Path,
) -> tuple[ProjectDB, list[dict], dict, str]:
    db, _source_rows = _analysis_batch_db(
        tmp_path,
        texts=(
            V30_SEQ23_PREVIOUS_TEXT,
            V30_SEQ24_NARRATION_TEXT,
            V30_SEQ25_THOUGHT_TEXT,
        ),
        kind_hints=("narration", "narration", "thought"),
    )
    with db.connect() as conn:
        conn.execute(
            "UPDATE segments SET seq=seq+23,"
            "paragraph_index=CASE seq WHEN 0 THEN 20 WHEN 1 THEN 21 ELSE 22 END,"
            "stable_id=CASE seq WHEN 0 THEN 'c00001_s0000023_v31' "
            "WHEN 1 THEN ? ELSE ? END",
            (V30_SEQ24_STABLE_ID, V30_SEQ25_STABLE_ID),
        )
    source_rows = [dict(row) for row in db.list_segments()]
    envelope = _analysis_acceptance_envelope([source_rows[1]])
    target_critic_row = envelope["critic_rows"][0]
    target_critic_row["context_policy"] = (
        ANALYSIS_CONTEXT_POLICY_NARRATION_BEFORE_NEXT_PARAGRAPH_THOUGHT
    )
    target_critic_row["host_locked_fields"] = {}
    target_critic_row["previous_text"] = V30_SEQ23_PREVIOUS_TEXT
    target_critic_row["next_text"] = ""
    with db.connect() as conn:
        context_hash = db._analysis_candidate_context_hash_conn(conn, envelope)
    return db, source_rows, envelope, context_hash


def _v32_seq43_dialogue_db(
    tmp_path: Path,
) -> tuple[ProjectDB, list[dict], dict]:
    db, _source_rows = _analysis_batch_db(
        tmp_path,
        texts=(V32_SEQ43_DIALOGUE_TEXT,),
        kind_hints=("dialogue",),
    )
    with db.connect() as conn:
        conn.execute("UPDATE segments SET seq=43,paragraph_index=35 WHERE seq=0")
    source_rows = [dict(row) for row in db.list_segments()]
    envelope = _dialogue_acceptance_envelope(source_rows)
    return db, source_rows, envelope


def _v29_v28_seq10_sleep_paralysis_db(
    tmp_path: Path,
) -> tuple[ProjectDB, list[dict], dict, dict]:
    db, _source_rows = _analysis_batch_db(
        tmp_path,
        texts=(V28_SEQ10_SLEEP_PARALYSIS_TEXT,),
        kind_hints=("narration",),
    )
    with db.connect() as conn:
        conn.execute(
            "UPDATE segments SET seq=10,paragraph_index=9,stable_id=? WHERE seq=0",
            (V28_SEQ10_SLEEP_PARALYSIS_STABLE_ID,),
        )
    source_rows = [dict(row) for row in db.list_segments()]
    envelope = _semantic_lock_envelope(
        source_rows,
        candidate_emotion="afraid",
    )
    envelope["critic_rows"][0]["host_locked_fields"] = {
        "kind": "narration",
        "emotion": "afraid",
    }
    clearance = _host_semantic_clearance(
        envelope,
        rule="narration_sleep_paralysis_helplessness",
        cue_class="sleep_paralysis_helplessness",
        allowed_emotions=["afraid"],
    )
    return db, source_rows, envelope, clearance


def _canonical_hash(value: object) -> str:
    return sha256_text(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    )


def _deterministic_analysis_issues(
    source_rows: list[dict],
    clearance: dict | None = None,
) -> dict:
    del source_rows
    return {
        "host_affect_clearance": clearance,
        "semantic_issues": [],
    }


def _clean_host_clearance(envelope: dict) -> dict:
    return {
        "host_affect_clearance": {
            "policy_version": ANALYSIS_HOST_AFFECT_POLICY_VERSION,
            "status": "cleared",
            "candidate_hash": _canonical_hash(envelope["critic_rows"]),
            "checked_segment_count": len(envelope["segments"]),
            "matched_rule_count": 0,
            "evidence": [],
            "structural_locks": [],
            "semantic_locks": [],
        }
    }


def _refresh_analysis_note(envelope: dict, index: int) -> None:
    data = envelope["segments"][index]["data"]
    data["notes"] = canonical_analysis_note(data)


def _accepted_critic_contract(envelope: dict) -> dict:
    critic_rows = envelope["critic_rows"]
    singleton_text = (
        str(critic_rows[0]["text"])
        if len(critic_rows) == 1
        and 1 <= len(str(critic_rows[0]["text"]))
        else ""
    )
    anchors = (
        canonical_analysis_critic_source_anchors(singleton_text)
        if len(singleton_text) > ANALYSIS_CRITIC_EVIDENCE_QUOTE_MAX_LENGTH
        else ()
    )
    per_id_anchor_map = (
        canonical_analysis_critic_per_id_source_anchor_map(critic_rows)
        if len(critic_rows) > 1
        else ()
    )
    return {
        "policy_version": ANALYSIS_DIRECTOR_CRITIC_POLICY_VERSION,
        "director_policy_version": ANALYSIS_DIRECTOR_CRITIC_POLICY_VERSION,
        "schema_policy_version": ANALYSIS_DIRECTOR_RETRY_SCHEMA_POLICY_VERSION,
        "rejected_emotions_by_id": [],
        "confidence_floor": 0.65,
        "confidence_cap": 0.95,
        "evidence_policy": (
            ANALYSIS_CRITIC_EVIDENCE_POLICY_SINGLETON_SOURCE_ANCHOR
            if anchors
            else ANALYSIS_CRITIC_EVIDENCE_POLICY_SINGLETON_FULL_TARGET
            if singleton_text
            else ANALYSIS_CRITIC_EVIDENCE_POLICY_PER_ID_SOURCE_ANCHOR
        ),
        "evidence_text_sha256": sha256_text(singleton_text) if singleton_text else "",
        "evidence_anchor_set_sha256": (
            analysis_critic_anchor_set_sha256(anchors)
            if anchors
            else analysis_critic_per_id_anchor_map_sha256(per_id_anchor_map)
            if per_id_anchor_map
            else ""
        ),
        "evidence_anchor_count": (
            len(anchors)
            if anchors
            else sum(len(item["anchors"]) for item in per_id_anchor_map)
        ),
        "candidate_hash": _canonical_hash(critic_rows),
        "seed": 11,
        "temperature": 0.0,
    }


def _accepted_critic_evidence(envelope: dict) -> dict:
    rows = []
    for segment, critic_row in zip(
        envelope["segments"],
        envelope["critic_rows"],
        strict=True,
    ):
        candidate = dict(critic_row["candidate"])
        source_text = str(critic_row["text"])
        evidence_quote = (
            canonical_analysis_critic_source_anchors(source_text)[0]
            if len(source_text) > ANALYSIS_CRITIC_EVIDENCE_QUOTE_MAX_LENGTH
            else source_text
        )
        rows.append(
            {
                "stable_id": segment["stable_id"],
                "text_sha256": segment["text_sha256"],
                "candidate": candidate,
                "critic": {
                    **candidate,
                    "accept": True,
                    "rationale": "Đồng ý với delivery theo đúng bằng chứng nguồn.",
                    "evidence_quote": evidence_quote,
                    "confidence": segment["data"]["confidence"],
                },
                "field_deltas": [],
                "derived_confidence": segment["data"]["confidence"],
                "effective_accept": True,
            }
        )
    return {
        "candidate_hash": _canonical_hash(envelope["critic_rows"]),
        "critic_contract": _accepted_critic_contract(envelope),
        "segments": rows,
    }


def _rejected_critic_outcome(evidence: dict) -> dict:
    issues = {}
    for item in evidence["segments"]:
        if item.get("effective_accept") is not False:
            continue
        covered_fields = set()
        structural_override = item.get("host_structural_override")
        compatibility_override = item.get("host_critic_compatibility_override")
        source_kind_override = item.get("host_source_kind_override")
        semantic_override = item.get("host_semantic_override")
        if structural_override is not None or compatibility_override is not None:
            covered_fields.update(
                delta.split(":", 1)[0] for delta in item["field_deltas"]
            )
        if isinstance(source_kind_override, dict):
            covered_fields.update(
                delta.split(":", 1)[0]
                for delta in source_kind_override.get("covered_field_deltas", [])
            )
        if isinstance(semantic_override, dict):
            covered_fields.add(str(semantic_override["field"]))
        unresolved_fields = [
            delta.split(":", 1)[0]
            for delta in item["field_deltas"]
            if delta.split(":", 1)[0] not in covered_fields
        ]
        if unresolved_fields:
            issues[str(item["stable_id"])] = (
                "DIRECTOR_FIELD_MISMATCH fields=" + ",".join(unresolved_fields)
            )
    return {"issues": issues, "retryable_invalid": False}


def test_v41_critic_speaker_provenance_requires_exact_candidate_identity() -> None:
    candidate_speakers = (
        "NPC_LOCAL::c00001::source-a::áo đen",
        "NPC_LOCAL::c00001::source-a::áo trắng",
        "NARRATOR",
    )

    assert analysis_critic_speaker_is_candidate_bound(
        "NPC_LOCAL::c00001::source-a::áo trắng",
        candidate_speakers,
    )
    assert analysis_critic_speaker_is_candidate_bound("NARRATOR", candidate_speakers)
    assert analysis_critic_speaker_is_candidate_bound("UNKNOWN", candidate_speakers)
    assert not analysis_critic_speaker_is_candidate_bound("Lucien", candidate_speakers)
    assert not analysis_critic_speaker_is_candidate_bound(
        "NPC_LOCAL::c00001::source-a::áo women",
        candidate_speakers,
    )
    assert not analysis_critic_speaker_is_candidate_bound(
        "NPC_LOCAL:áo trắng",
        candidate_speakers,
    )
    assert canonical_analysis_critic_allowed_speakers(
        (
            {"candidate": {"speaker": candidate_speakers[0]}},
            {"candidate": {"speaker": "Lucien"}},
        )
    ) == (
        "Lucien",
        "NARRATOR",
        "NPC_LOCAL::c00001::source-a::áo đen",
        "UNKNOWN",
    )


def _critic_compatibility_override_evidence(envelope: dict) -> dict:
    evidence = _accepted_critic_evidence(envelope)
    item = evidence["segments"][0]
    critic_row = envelope["critic_rows"][0]
    candidate = item["candidate"]
    item["critic"].update(
        {
            "accept": False,
            "emotion": "afraid",
            "intensity": 2,
            "pace": "fast",
            "rationale": "Critic suy diễn sợ hãi từ trạng thái hỗn loạn.",
        }
    )
    raw_deltas = [
        "emotion:neutral->afraid",
        "intensity:1->2",
        "pace:normal->fast",
    ]
    item["field_deltas"] = raw_deltas
    override = analysis_expected_critic_compatibility_override(
        stable_id=str(item["stable_id"]),
        source_text=str(critic_row["text"]),
        text_sha256=str(item["text_sha256"]),
        source_kind=str(critic_row["hint"]),
        candidate=candidate,
        critic=item["critic"],
        raw_deltas=raw_deltas,
    )
    assert override is not None
    item["host_critic_compatibility_override"] = override
    return evidence


def _chapter_heading_envelope(source_rows: list[dict]) -> dict:
    envelope = _analysis_acceptance_envelope(source_rows)
    heading_segment = envelope["segments"][0]
    heading_row = envelope["critic_rows"][0]
    for field, value in ANALYSIS_CHAPTER_HEADING_DELIVERY.items():
        heading_segment["data"][field] = value
    heading_segment["data"]["confidence"] = ANALYSIS_CHAPTER_HEADING_CONFIDENCE
    heading_segment["data"]["notes"] = canonical_analysis_note(
        heading_segment["data"]
    )
    heading_row["source_role"] = "chapter_heading"
    heading_row["context_policy"] = "target_only"
    heading_row["host_locked_fields"] = dict(ANALYSIS_CHAPTER_HEADING_DELIVERY)
    heading_row["previous_text"] = ""
    heading_row["next_text"] = ""
    heading_row["candidate"] = dict(ANALYSIS_CHAPTER_HEADING_DELIVERY)
    return envelope


def _chapter_heading_clearance(
    envelope: dict,
    *,
    generator_confidence: float = 0.9,
) -> dict:
    segment = envelope["segments"][0]
    generator_fields = {
        "kind": "narration",
        "speaker": "NARRATOR",
        "emotion": "afraid",
        "intensity": 2,
        "pace": "fast",
        "volume": "loud",
    }
    return {
        "host_affect_clearance": {
            "policy_version": ANALYSIS_HOST_AFFECT_POLICY_VERSION,
            "status": "cleared",
            "candidate_hash": _canonical_hash(envelope["critic_rows"]),
            "checked_segment_count": len(envelope["segments"]),
            "matched_rule_count": 0,
            "evidence": [],
            "structural_locks": [
                {
                    "policy_version": ANALYSIS_HOST_STRUCTURAL_POLICY_VERSION,
                    "stable_id": segment["stable_id"],
                    "text_sha256": segment["text_sha256"],
                    "source_role": "chapter_heading",
                    "context_policy": "target_only",
                    "evidence_quote": envelope["critic_rows"][0]["text"],
                    "locked_fields": dict(ANALYSIS_CHAPTER_HEADING_DELIVERY),
                    "generator_fields": generator_fields,
                    "generator_notes": "raw generator audit note",
                    "generator_confidence": generator_confidence,
                    "locked_confidence": ANALYSIS_CHAPTER_HEADING_CONFIDENCE,
                }
            ],
            "semantic_locks": [],
        }
    }


def _heading_override_evidence(envelope: dict) -> dict:
    evidence = _accepted_critic_evidence(envelope)
    segment = envelope["segments"][0]
    item = evidence["segments"][0]
    critic = item["critic"]
    critic.update(
        {
            "accept": False,
            "emotion": "afraid",
            "intensity": 2,
            "pace": "fast",
            "rationale": "Tiêu đề có từ ngữ gợi cảm giác nguy hiểm.",
            "evidence_quote": envelope["critic_rows"][0]["text"],
        }
    )
    deltas = [
        "emotion:neutral->afraid",
        "intensity:0->2",
        "pace:normal->fast",
    ]
    item["field_deltas"] = deltas
    item["host_structural_override"] = {
        "policy_version": ANALYSIS_HOST_STRUCTURAL_POLICY_VERSION,
        "stable_id": segment["stable_id"],
        "text_sha256": segment["text_sha256"],
        "source_role": "chapter_heading",
        "context_policy": "target_only",
        "locked_fields": dict(ANALYSIS_CHAPTER_HEADING_DELIVERY),
        "locked_confidence": ANALYSIS_CHAPTER_HEADING_CONFIDENCE,
        "raw_accept": False,
        "raw_field_deltas": deltas,
    }
    return evidence


def _semantic_lock_envelope(
    source_rows: list[dict],
    *,
    locked_index: int = 0,
    candidate_emotion: str = "afraid",
) -> dict:
    envelope = _analysis_acceptance_envelope(source_rows)
    for index, source_row in enumerate(source_rows):
        source_kind = str(source_row["kind_hint"])
        envelope["segments"][index]["data"]["kind"] = source_kind
        _refresh_analysis_note(envelope, index)
        envelope["critic_rows"][index]["candidate"]["kind"] = source_kind
    segment = envelope["segments"][locked_index]
    critic_row = envelope["critic_rows"][locked_index]
    segment["data"]["emotion"] = candidate_emotion
    segment["data"]["intensity"] = 2
    _refresh_analysis_note(envelope, locked_index)
    critic_row["candidate"]["emotion"] = candidate_emotion
    critic_row["candidate"]["intensity"] = 2
    critic_row["host_locked_fields"] = {"emotion": candidate_emotion}
    return envelope


def _host_semantic_clearance(
    envelope: dict,
    *,
    locked_index: int = 0,
    rule: str = "respiratory_injury_with_consciousness_loss",
    cue_class: str = "physical_collapse",
    allowed_emotions: list[str] | None = None,
    related_index: int | None = None,
) -> dict:
    segment = envelope["segments"][locked_index]
    critic_row = envelope["critic_rows"][locked_index]
    related_segment = (
        envelope["segments"][related_index]
        if related_index is not None
        else None
    )
    semantic_lock = {
        "policy_version": ANALYSIS_HOST_SEMANTIC_POLICY_VERSION,
        "stable_id": segment["stable_id"],
        "text_sha256": segment["text_sha256"],
        "source_role": "content",
        "field": "emotion",
        "rule": rule,
        "cue_class": cue_class,
        "candidate_emotion": critic_row["candidate"]["emotion"],
        "allowed_emotions": allowed_emotions or ["afraid", "tired"],
        "related_stable_id": (
            related_segment["stable_id"]
            if related_segment is not None
            else ""
        ),
        "related_text_sha256": (
            related_segment["text_sha256"]
            if related_segment is not None
            else ""
        ),
    }
    semantic_evidence = {
        "stable_id": semantic_lock["stable_id"],
        "text_sha256": semantic_lock["text_sha256"],
        "rule": semantic_lock["rule"],
        "cue_class": semantic_lock["cue_class"],
        "candidate_emotion": semantic_lock["candidate_emotion"],
        "allowed_emotions": list(semantic_lock["allowed_emotions"]),
        "outcome": "pass",
    }
    if semantic_lock["related_stable_id"]:
        semantic_evidence["related_stable_id"] = semantic_lock["related_stable_id"]
    if semantic_lock["related_text_sha256"]:
        semantic_evidence["related_text_sha256"] = semantic_lock[
            "related_text_sha256"
        ]
    return {
        "host_affect_clearance": {
            "policy_version": ANALYSIS_HOST_AFFECT_POLICY_VERSION,
            "status": "cleared",
            "candidate_hash": _canonical_hash(envelope["critic_rows"]),
            "checked_segment_count": len(envelope["segments"]),
            "matched_rule_count": 1,
            "evidence": [semantic_evidence],
            "structural_locks": [],
            "semantic_locks": [semantic_lock],
        }
    }


def _merge_host_semantic_clearances(*clearances: dict) -> dict:
    merged = copy.deepcopy(clearances[0])
    host = merged["host_affect_clearance"]
    for clearance in clearances[1:]:
        incoming = clearance["host_affect_clearance"]
        assert incoming["candidate_hash"] == host["candidate_hash"]
        assert incoming["checked_segment_count"] == host["checked_segment_count"]
        host["evidence"].extend(copy.deepcopy(incoming["evidence"]))
        host["semantic_locks"].extend(copy.deepcopy(incoming["semantic_locks"]))
    host["matched_rule_count"] = len(host["semantic_locks"])
    return merged


def _semantic_override_evidence(
    envelope: dict,
    clearance: dict,
    *,
    locked_index: int = 0,
    corrected_emotion: str = "neutral",
) -> dict:
    evidence = _accepted_critic_evidence(envelope)
    item = evidence["segments"][locked_index]
    lock = clearance["host_affect_clearance"]["semantic_locks"][0]
    candidate_emotion = item["candidate"]["emotion"]
    item["critic"].update(
        {
            "accept": False,
            "emotion": corrected_emotion,
            "rationale": "Critic đề xuất cảm xúc khác với ràng buộc host.",
        }
    )
    deltas = [f"emotion:{candidate_emotion}->{corrected_emotion}"]
    item["field_deltas"] = deltas
    item["host_semantic_override"] = {
        "policy_version": ANALYSIS_HOST_SEMANTIC_POLICY_VERSION,
        "stable_id": item["stable_id"],
        "text_sha256": item["text_sha256"],
        "rule": lock["rule"],
        "field": "emotion",
        "candidate_value": candidate_emotion,
        "allowed_values": list(lock["allowed_emotions"]),
        "raw_accept": False,
        "raw_field_deltas": deltas,
    }
    return evidence


def _source_kind_override_evidence(
    envelope: dict,
    clearance: dict,
    *,
    corrected_kind: str = "thought",
    corrected_emotion: str | None = None,
    corrected_intensity: int | None = None,
    corrected_pace: str | None = None,
) -> dict:
    evidence = _accepted_critic_evidence(envelope)
    item = evidence["segments"][0]
    lock = clearance["host_affect_clearance"]["semantic_locks"][0]
    candidate = item["candidate"]
    item["critic"].update(
        {
            "accept": False,
            "kind": corrected_kind,
            "rationale": "Critic đổi loại nguồn dù host đã khóa narration.",
        }
    )
    corrected_fields = {"kind": corrected_kind}
    if corrected_emotion is not None:
        item["critic"]["emotion"] = corrected_emotion
        corrected_fields["emotion"] = corrected_emotion
    if corrected_intensity is not None:
        item["critic"]["intensity"] = corrected_intensity
        corrected_fields["intensity"] = corrected_intensity
    if corrected_pace is not None:
        item["critic"]["pace"] = corrected_pace
        corrected_fields["pace"] = corrected_pace
    raw_deltas = [
        f"{field}:{candidate[field]}->{corrected_fields[field]}"
        for field in ("kind", "speaker", "emotion", "intensity", "pace", "volume")
        if field in corrected_fields and corrected_fields[field] != candidate[field]
    ]
    covered_deltas = [
        delta for delta in raw_deltas if delta.startswith("kind:")
    ]
    unresolved_deltas = [
        delta for delta in raw_deltas if not delta.startswith("kind:")
    ]
    item["field_deltas"] = raw_deltas
    globally_unresolved_deltas = [
        delta
        for delta in raw_deltas
        if not delta.startswith(("kind:", "emotion:"))
    ]
    item["effective_accept"] = not globally_unresolved_deltas
    item["host_source_kind_override"] = {
        "policy_version": ANALYSIS_HOST_SEMANTIC_POLICY_VERSION,
        "stable_id": item["stable_id"],
        "text_sha256": item["text_sha256"],
        "rule": lock["rule"],
        "field": "kind",
        "candidate_value": candidate["kind"],
        "allowed_values": [candidate["kind"]],
        "raw_accept": False,
        "raw_field_deltas": raw_deltas,
        "covered_field_deltas": covered_deltas,
        "unresolved_field_deltas": unresolved_deltas,
    }
    if corrected_emotion is not None:
        item["host_semantic_override"] = {
            "policy_version": ANALYSIS_HOST_SEMANTIC_POLICY_VERSION,
            "stable_id": item["stable_id"],
            "text_sha256": item["text_sha256"],
            "rule": lock["rule"],
            "field": "emotion",
            "candidate_value": candidate["emotion"],
            "allowed_values": list(lock["allowed_emotions"]),
            "raw_accept": False,
            "raw_field_deltas": raw_deltas,
        }
    return evidence


def _context_source_kind_override_evidence(
    envelope: dict,
    related_row: dict,
    *,
    corrected_kind: str = "thought",
    corrected_emotion: str | None = None,
    corrected_intensity: int | None = None,
    corrected_pace: str | None = None,
    semantic_clearance: dict | None = None,
) -> dict:
    evidence = _accepted_critic_evidence(envelope)
    item = evidence["segments"][0]
    candidate = item["candidate"]
    item["critic"].update(
        {
            "accept": False,
            "kind": corrected_kind,
            "rationale": "Critic đổi câu kể dẫn thành thought.",
        }
    )
    corrected_fields: dict[str, object] = {"kind": corrected_kind}
    for field, value in (
        ("emotion", corrected_emotion),
        ("intensity", corrected_intensity),
        ("pace", corrected_pace),
    ):
        if value is not None:
            item["critic"][field] = value
            corrected_fields[field] = value
    raw_deltas = [
        f"{field}:{candidate[field]}->{corrected_fields[field]}"
        for field in ("kind", "speaker", "emotion", "intensity", "pace", "volume")
        if field in corrected_fields and corrected_fields[field] != candidate[field]
    ]
    covered_deltas = [
        delta for delta in raw_deltas if delta.startswith("kind:")
    ]
    unresolved_deltas = [
        delta for delta in raw_deltas if not delta.startswith("kind:")
    ]
    item["field_deltas"] = raw_deltas
    item["effective_accept"] = not [
        delta
        for delta in raw_deltas
        if not delta.startswith(
            ("kind:", "emotion:")
            if semantic_clearance is not None
            else ("kind:",)
        )
    ]
    item["host_source_kind_override"] = {
        "policy_version": ANALYSIS_HOST_SEMANTIC_POLICY_VERSION,
        "stable_id": item["stable_id"],
        "text_sha256": item["text_sha256"],
        "rule": ANALYSIS_CONTEXT_SOURCE_KIND_RULE,
        "field": "kind",
        "candidate_value": "narration",
        "allowed_values": ["narration"],
        "raw_accept": False,
        "raw_field_deltas": raw_deltas,
        "covered_field_deltas": covered_deltas,
        "unresolved_field_deltas": unresolved_deltas,
        "related_stable_id": str(related_row["stable_id"]),
        "related_text_sha256": str(related_row["text_sha256"]),
    }
    if corrected_emotion is not None and semantic_clearance is not None:
        semantic_lock = semantic_clearance["host_affect_clearance"][
            "semantic_locks"
        ][0]
        item["host_semantic_override"] = {
            "policy_version": ANALYSIS_HOST_SEMANTIC_POLICY_VERSION,
            "stable_id": item["stable_id"],
            "text_sha256": item["text_sha256"],
            "rule": semantic_lock["rule"],
            "field": "emotion",
            "candidate_value": candidate["emotion"],
            "allowed_values": list(semantic_lock["allowed_emotions"]),
            "raw_accept": False,
            "raw_field_deltas": raw_deltas,
        }
    return evidence


def _allocate_analysis_candidate(
    db: ProjectDB,
    source_rows: list[dict],
    *,
    context_hash: str = ANALYSIS_CONTEXT_HASH,
    candidate: dict | None = None,
    deterministic_issues: dict | None = None,
    critic_max_attempts: int = 2,
    generator_contract: dict | None = None,
):
    envelope = candidate or _analysis_acceptance_envelope(source_rows)
    durable_generator_contract = (
        generator_contract
        if generator_contract is not None
        else {"attempt": 1, "seed": 101}
    )
    return db.allocate_or_resume_analysis_candidate(
        policy_fingerprint=ANALYSIS_POLICY_FINGERPRINT,
        model_name=ANALYSIS_MODEL_NAME,
        model_digest=ANALYSIS_MODEL_DIGEST,
        group_fingerprint=ANALYSIS_GROUP_FINGERPRINT,
        context_hash=context_hash,
        candidate_hash=analysis_critic_candidate_hash(
            envelope["critic_rows"],
            durable_generator_contract.get("rejected_emotions_by_id"),
        ),
        candidate=envelope,
        generator_contract=durable_generator_contract,
        deterministic_issues=(
            _deterministic_analysis_issues(source_rows)
            if deterministic_issues is None
            else _deterministic_analysis_issues(
                source_rows,
                deterministic_issues.get("host_affect_clearance"),
            )
        ),
        critic_max_attempts=critic_max_attempts,
    )


def _candidate_db(tmp_path: Path) -> tuple[ProjectDB, int, str, Path]:
    db, segment_id = _segment_db(tmp_path)
    profile_id = db.upsert_voice_profile(
        {
            "voice_key": "candidate-narrator",
            "engine": "vieneu",
            "preset_name": "Candidate Voice",
            "description": "Candidate test voice",
            "seed": 7,
            "pitch_semitones": 0,
            "status": "ready",
        }
    )
    with db.connect() as conn:
        conn.execute(
            "UPDATE segments SET voice_profile_id=? WHERE id=?",
            (profile_id, segment_id),
        )
    incumbent_sha256 = "a" * 64
    incumbent_path = tmp_path / "incumbent.wav"
    db.mark_signal_passed(
        segment_id,
        wav_path=incumbent_path,
        wav_sha256=incumbent_sha256,
        duration=1.0,
        signal={"duration": 1.0, "spoken_text_sha256": "1" * 64},
        generation_seed=11,
    )
    db.set_current_quality_policy(
        policy_hash="candidate-policy-v1",
        policy_version=1,
        policy={"asr": {"repair_rounds": 2}},
    )
    return db, segment_id, incumbent_sha256, incumbent_path


def _checkpoint_candidate_signal(
    db: ProjectDB,
    candidate_id: int,
    *,
    repair_round: int,
    generation_seed: int,
    wav_path: Path,
    wav_sha256: str,
    signal_overrides: dict | None = None,
) -> None:
    candidate = db.get_segment_candidate(candidate_id)
    signal = {
        "duration": 1.25,
        "tts_delivery_mode": "clarity",
        "asr_clarity_repair_round": repair_round,
        "spoken_text_sha256": str(candidate["expected_spoken_text_sha256"]),
        "pronunciation_delivery_variant": str(
            candidate["pronunciation_delivery_variant"]
        ),
        "voice_profile_id": int(candidate["expected_voice_profile_id"]),
        "pitch_semitones": 0,
        "effective_pitch_semitones": 0,
        "pitch_variant_skipped": 0.0,
        "pitch_variant_mixed": 0.0,
    }
    signal.update(signal_overrides or {})
    db.checkpoint_segment_candidate_signal(
        candidate_id,
        expected_generation_seed=generation_seed,
        wav_path=wav_path,
        wav_sha256=wav_sha256,
        duration=1.25,
        signal=signal,
    )


def _candidate_decode_check(
    db: ProjectDB,
    *,
    segment_id: int,
    artifact_sha256: str,
    repair_round: int,
    generation_seed: int,
    confirmation: bool,
    verdict: str,
    reason: str,
    metrics_overrides: dict | None = None,
    failure_codes: tuple[str, ...] = (),
) -> int:
    segment = db.get_segment(segment_id)
    candidate = next(
        row
        for row in db.list_segment_candidates(
            segment_id=segment_id,
            policy_hash="candidate-policy-v1",
        )
        if int(row["repair_round"]) == int(repair_round)
    )
    metrics_verdict = (
        "pass" if verdict == "pass" else "inconclusive" if verdict == "inconclusive" else "mismatch"
    )
    metrics = {
        "verdict": metrics_verdict,
        "passed": verdict == "pass",
        "reason": reason,
        "decode_mode": "greedy" if confirmation else "beam5",
        "selected": True,
        "delivery_mode": "clarity",
        "repair_round": repair_round,
        "generation_seed": generation_seed,
        "spoken_text_sha256": str(candidate["expected_spoken_text_sha256"]),
        "pronunciation_delivery_variant": str(
            candidate["pronunciation_delivery_variant"]
        ),
        "voice_profile_id": int(segment["voice_profile_id"]),
        "pitch_semitones": 0,
        "effective_pitch_semitones": 0,
        "pitch_variant_skipped": False,
        "pitch_variant_mixed": False,
        "transcript": "Text",
        "similarity": 1.0 if verdict == "pass" else 0.2,
        "wer": 0.0 if verdict == "pass" else 1.0,
    }
    if failure_codes:
        metrics["failure_codes"] = list(failure_codes)
    metrics.update(metrics_overrides or {})
    return db.record_quality_check(
        scope=QUALITY_SCOPE_SEGMENT,
        stage=SEGMENT_ASR_DECODE_QUALITY_STAGE,
        segment_id=segment_id,
        artifact_sha256=artifact_sha256,
        policy_hash="candidate-policy-v1",
        policy_version=1,
        verdict=verdict,
        metrics=metrics,
        failure_codes=failure_codes,
    )


def _candidate_perceptual_check(
    db: ProjectDB,
    *,
    segment_id: int,
    artifact_sha256: str,
    verdict: str,
    perceptual_verdict: str,
    reason: str,
    review_required: bool,
    baseline_pitch_semitones: int = 0,
) -> int:
    return db.record_quality_check(
        scope=QUALITY_SCOPE_SEGMENT,
        stage=SEGMENT_PERCEPTUAL_QUALITY_STAGE,
        segment_id=segment_id,
        artifact_sha256=artifact_sha256,
        policy_hash="candidate-policy-v1",
        policy_version=1,
        verdict=verdict,
        metrics={
            "verdict": perceptual_verdict,
            "reason": reason,
            "review_required": review_required,
            "score": 3.8,
            "baseline_score": 4.0,
            "baseline_delta": -0.2,
            "baseline_pitch_semitones": baseline_pitch_semitones,
        },
    )


def _write_candidate_artifact(path: Path, label: str) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(f"candidate-audio:{label}".encode("utf-8"))
    return sha256_file(path)


def _dual_pass_candidate(
    db: ProjectDB,
    *,
    segment_id: int,
    incumbent_sha256: str,
    candidate_path: Path,
    generation_seed: int,
    perceptual_required: bool,
) -> tuple[sqlite3.Row, str]:
    candidate_sha256 = _write_candidate_artifact(candidate_path, str(generation_seed))
    candidate = db.allocate_segment_candidate(
        segment_id=segment_id,
        policy_hash="candidate-policy-v1",
        repair_round=0,
        max_repair_rounds=2,
        incumbent_sha256=incumbent_sha256,
        generation_seed=generation_seed,
        wav_path=candidate_path,
        candidates_root=candidate_path.parent,
        perceptual_required=perceptual_required,
    )
    candidate_id = int(candidate["id"])
    _checkpoint_candidate_signal(
        db,
        candidate_id,
        repair_round=0,
        generation_seed=generation_seed,
        wav_path=candidate_path,
        wav_sha256=candidate_sha256,
    )
    for confirmation in (False, True):
        check_id = _candidate_decode_check(
            db,
            segment_id=segment_id,
            artifact_sha256=candidate_sha256,
            repair_round=0,
            generation_seed=generation_seed,
            confirmation=confirmation,
            verdict="pass",
            reason="ok",
        )
        db.checkpoint_segment_candidate_decode(
            candidate_id,
            quality_check_id=check_id,
            confirmation=confirmation,
        )
    return db.get_segment_candidate(candidate_id), candidate_sha256


def _locked_name_dual_failed_candidate(
    db: ProjectDB,
    *,
    segment_id: int,
    incumbent_sha256: str,
    candidate_path: Path,
    generation_seed: int,
) -> sqlite3.Row:
    candidate_sha256 = _write_candidate_artifact(
        candidate_path,
        f"locked-name-{generation_seed}",
    )
    candidate = db.allocate_segment_candidate(
        segment_id=segment_id,
        policy_hash="candidate-policy-v1",
        repair_round=0,
        max_repair_rounds=2,
        incumbent_sha256=incumbent_sha256,
        generation_seed=generation_seed,
        wav_path=candidate_path,
        candidates_root=candidate_path.parent,
    )
    candidate_id = int(candidate["id"])
    _checkpoint_candidate_signal(
        db,
        candidate_id,
        repair_round=0,
        generation_seed=generation_seed,
        wav_path=candidate_path,
        wav_sha256=candidate_sha256,
    )
    failure_code = ASR_LOCKED_NAME_ANCHOR_MISMATCH
    beam_check = _candidate_decode_check(
        db,
        segment_id=segment_id,
        artifact_sha256=candidate_sha256,
        repair_round=0,
        generation_seed=generation_seed,
        confirmation=False,
        verdict="fail",
        reason=failure_code,
        failure_codes=(failure_code,),
        metrics_overrides={
            "repairable": True,
            LOCKED_NAME_ANCHOR_METRICS_KEY: {
                "version": LOCKED_NAME_ANCHOR_METRICS_VERSION,
                "status": "fail",
                "adjudicated": True,
                "passed": False,
                "failure_codes": [failure_code],
                "repeat_count": 1,
                "anchor_count": 1,
                "required_occurrence_count": 1,
                "matched_occurrence_count": 0,
            },
        },
    )
    db.checkpoint_segment_candidate_decode(
        candidate_id,
        quality_check_id=beam_check,
        confirmation=False,
    )
    greedy_check = _candidate_decode_check(
        db,
        segment_id=segment_id,
        artifact_sha256=candidate_sha256,
        repair_round=0,
        generation_seed=generation_seed,
        confirmation=True,
        verdict="pass",
        reason="ok",
    )
    failed = db.checkpoint_segment_candidate_decode(
        candidate_id,
        quality_check_id=greedy_check,
        confirmation=True,
    )
    assert failed["state"] == "dual_failed"
    return failed


def _downgrade_promoted_candidate_delivery_to_v8(
    db: ProjectDB,
    candidate_id: int,
    *,
    live_signal_damage: str | None = None,
) -> None:
    with sqlite3.connect(db.path) as conn:
        conn.row_factory = sqlite3.Row
        candidate = conn.execute(
            "SELECT * FROM segment_candidates WHERE id=?",
            (int(candidate_id),),
        ).fetchone()
        assert candidate is not None

        def without_delivery_variant(value: str) -> str:
            payload = json.loads(str(value))
            payload.pop("pronunciation_delivery_variant", None)
            payload.pop("expected_spoken_text_sha256", None)
            decode_evidence = payload.get("decode_evidence")
            if isinstance(decode_evidence, list):
                for evidence in decode_evidence:
                    if isinstance(evidence, dict):
                        evidence.pop("pronunciation_delivery_variant", None)
            return json.dumps(payload, ensure_ascii=False, sort_keys=True)

        for field in (
            "signal_json",
            "beam_result_json",
            "greedy_result_json",
        ):
            conn.execute(
                f"UPDATE segment_candidates SET {field}=? WHERE id=?",
                (without_delivery_variant(str(candidate[field])), int(candidate_id)),
            )
        for check_id_field in (
            "beam_check_id",
            "greedy_check_id",
            "final_check_id",
        ):
            check_id = candidate[check_id_field]
            assert check_id is not None
            metrics_json = conn.execute(
                "SELECT metrics_json FROM quality_checks WHERE id=?",
                (int(check_id),),
            ).fetchone()[0]
            conn.execute(
                "UPDATE quality_checks SET metrics_json=? WHERE id=?",
                (without_delivery_variant(str(metrics_json)), int(check_id)),
            )
        segment_signal = json.loads(
            str(
                conn.execute(
                    "SELECT signal_json FROM segments WHERE id=?",
                    (int(candidate["segment_id"]),),
                ).fetchone()[0]
            )
        )
        segment_signal.pop("pronunciation_delivery_variant", None)
        if live_signal_damage == "spoken_sha":
            segment_signal["spoken_text_sha256"] = "9" * 64
            encoded_segment_signal = json.dumps(
                segment_signal,
                ensure_ascii=False,
                sort_keys=True,
            )
        elif live_signal_damage == "malformed":
            encoded_segment_signal = "{broken"
        else:
            if live_signal_damage == "harmless_metric":
                segment_signal["same_wav_recheckpoint_metric"] = 123
            encoded_segment_signal = json.dumps(
                segment_signal,
                ensure_ascii=False,
                sort_keys=True,
            )
        conn.execute(
            "UPDATE segments SET signal_json=? WHERE id=?",
            (encoded_segment_signal, int(candidate["segment_id"])),
        )
        conn.execute(
            "ALTER TABLE segment_candidates DROP COLUMN pronunciation_delivery_variant"
        )
        conn.execute(
            "ALTER TABLE segment_candidates DROP COLUMN expected_spoken_text_sha256"
        )
        conn.execute("PRAGMA user_version=8")


def test_segment_speaker_rewrite_rebuilds_marker_free_canonical_note(
    tmp_path: Path,
) -> None:
    db, segment_id = _segment_db(tmp_path)
    with db.connect() as conn:
        row = db.get_segment(segment_id)
        legacy_note = canonical_analysis_note(
            {**dict(row), "kind": "dialogue"},
            (CONTINUED_DIALOGUE_LOCK_NOTE,),
        )
        conn.execute(
            "UPDATE segments SET kind='dialogue',analysis_notes=? WHERE id=?",
            (legacy_note, segment_id),
        )
    row = db.get_segment(segment_id)

    rewritten = db.rewrite_segment_speakers(
        [segment_id],
        speaker="ALISA",
        gender="female",
        age="adult",
    )

    result = db.get_segment(segment_id)
    assert rewritten == 1
    assert result["speaker"] == "ALISA"
    assert result["analysis_notes"] == canonical_analysis_note(dict(result))
    assert CONTINUED_DIALOGUE_LOCK_NOTE not in result["analysis_notes"]


def test_segment_speaker_rewrite_does_not_accept_analysis_notes_argument(
    tmp_path: Path,
) -> None:
    db, segment_id = _segment_db(tmp_path)

    with pytest.raises(TypeError, match="analysis_notes"):
        db.rewrite_segment_speakers(
            [segment_id],
            speaker="FORGED",
            gender="unknown",
            age="unknown",
            analysis_notes="copied director prose",
        )

    assert db.get_segment(segment_id)["speaker"] == "NARRATOR"


def test_segment_speaker_rewrite_rejects_dialogue_marker_on_narration(
    tmp_path: Path,
) -> None:
    db, segment_id = _segment_db(tmp_path)
    with pytest.raises(ValueError, match="dialogue segments"):
        db.rewrite_segment_speakers(
            [segment_id],
            speaker="FORGED",
            gender="unknown",
            age="unknown",
        )

    assert db.get_segment(segment_id)["speaker"] == "NARRATOR"


def test_segment_speaker_rewrite_rejects_noncanonical_current_note_atomically(
    tmp_path: Path,
) -> None:
    db, segment_id = _segment_db(tmp_path)
    with db.connect() as conn:
        conn.execute(
            "UPDATE segments SET kind='dialogue',analysis_notes='forged' WHERE id=?",
            (segment_id,),
        )

    with pytest.raises(ValueError, match="canonical delivery note"):
        db.rewrite_segment_speakers(
            [segment_id],
            speaker="FORGED",
            gender="unknown",
            age="unknown",
        )

    assert db.get_segment(segment_id)["speaker"] == "NARRATOR"


def test_segment_speaker_rewrite_rebuilds_each_row_note_from_its_own_delivery(
    tmp_path: Path,
) -> None:
    db, source_rows = _analysis_batch_db(tmp_path)
    first_id = int(source_rows[0]["id"])
    second_id = int(source_rows[1]["id"])
    with db.connect() as conn:
        conn.execute(
            "UPDATE segments SET kind='dialogue'"
        )
        conn.execute(
            "UPDATE segments SET emotion='angry',intensity=2 WHERE id=?", (second_id,)
        )

    rewritten = db.rewrite_segment_speakers(
        [first_id, second_id],
        speaker="ALISA",
        gender="female",
        age="adult",
    )

    rows = db.list_segments()
    assert rewritten == 2
    assert {row["speaker"] for row in rows} == {"ALISA"}
    assert all(
        row["analysis_notes"] == canonical_analysis_note(dict(row))
        for row in rows
    )
    assert rows[0]["analysis_notes"] != rows[1]["analysis_notes"]


def test_partial_analysis_update_merges_current_delivery_and_builds_canonical_note(
    tmp_path: Path,
) -> None:
    db, segment_id = _segment_db(tmp_path)

    db.update_analysis(segment_id, {"confidence": 0.9})

    row = db.get_segment(segment_id)
    assert row["kind"] == "narration"
    assert row["speaker"] == "NARRATOR"
    assert row["emotion"] == "neutral"
    assert row["confidence"] == 0.9
    assert row["analysis_notes"] == canonical_analysis_note(dict(row))


def test_partial_analysis_update_rebuilds_note_after_delivery_change(
    tmp_path: Path,
) -> None:
    db, segment_id = _segment_db(tmp_path)
    db.update_analysis(segment_id, {"confidence": 0.9})

    db.update_analysis(
        segment_id,
        {"emotion": "angry", "intensity": 2, "volume": "loud"},
    )

    row = db.get_segment(segment_id)
    assert row["emotion"] == "angry"
    assert row["intensity"] == 2
    assert row["volume"] == "loud"
    assert row["analysis_notes"] == canonical_analysis_note(dict(row))


@pytest.mark.parametrize(
    "updates",
    (
        {"personality_hint": "stoic"},
        {"notes": "director prose"},
    ),
)
def test_partial_analysis_update_rejects_untrusted_note_fields_atomically(
    tmp_path: Path,
    updates: dict,
) -> None:
    db, segment_id = _segment_db(tmp_path)
    before = dict(db.get_segment(segment_id))

    with pytest.raises(ValueError, match="personality_hint|canonical delivery note"):
        db.update_analysis(segment_id, updates)

    after = dict(db.get_segment(segment_id))
    assert after["kind"] == before["kind"]
    assert after["confidence"] == before["confidence"]
    assert after["analysis_notes"] == before["analysis_notes"]


def test_direct_analysis_update_rejects_recognized_marker_atomically(
    tmp_path: Path,
) -> None:
    db, segment_id = _segment_db(tmp_path)
    data = _canonical_analysis_data(kind="dialogue", speaker="ALISA")
    data["notes"] = canonical_analysis_note(
        data,
        (CONTINUED_DIALOGUE_LOCK_NOTE,),
    )

    with pytest.raises(ValueError, match="must not persist host markers"):
        db.update_analysis(segment_id, data)

    row = db.get_segment(segment_id)
    assert row["kind"] == "narration"
    assert row["speaker"] == "NARRATOR"
    assert row["analysis_notes"] == ""


def test_partial_analysis_update_strips_valid_legacy_marker_from_current_note(
    tmp_path: Path,
) -> None:
    db, segment_id = _segment_db(tmp_path)
    row = db.get_segment(segment_id)
    legacy_note = canonical_analysis_note(
        dict(row),
        (CONTINUED_DIALOGUE_LOCK_NOTE,),
    )
    with db.connect() as conn:
        conn.execute(
            "UPDATE segments SET analysis_notes=? WHERE id=?",
            (legacy_note, segment_id),
        )

    db.update_analysis(segment_id, {"confidence": 0.9})

    result = db.get_segment(segment_id)
    assert result["analysis_notes"] == canonical_analysis_note(dict(result))
    assert CONTINUED_DIALOGUE_LOCK_NOTE not in result["analysis_notes"]


def test_warning_codes_are_merged_without_duplicates(tmp_path: Path) -> None:
    db, segment_id = _segment_db(tmp_path)

    db.set_segment_warning_code(segment_id, "TTS_SPLIT_RECOVERY")
    db.mark_verified(segment_id, warning_code="ASR_ERROR")
    db.set_segment_warning_code(segment_id, "TTS_SPLIT_RECOVERY")

    assert db.get_segment(segment_id)["warning_code"] == "TTS_SPLIT_RECOVERY|ASR_ERROR"


def test_signal_checkpoint_commits_derived_warnings_atomically(tmp_path: Path) -> None:
    db, segment_id = _segment_db(tmp_path)
    wav_path = tmp_path / "segment.wav"
    wav_path.write_bytes(b"wav")

    db.mark_signal_passed(
        segment_id,
        wav_path=wav_path,
        wav_sha256="a" * 64,
        duration=1.0,
        signal={"pitch_variant_skipped": 1.0},
        generation_seed=17,
        warning_codes=(
            "TTS_SPLIT_RECOVERY",
            "TTS_PITCH_VARIANT_SKIPPED",
            "TTS_PITCH_VARIANT_SKIPPED",
        ),
    )

    row = db.get_segment(segment_id)
    assert row["status"] == "signal_passed"
    assert row["warning_code"] == (
        "TTS_SPLIT_RECOVERY|TTS_PITCH_VARIANT_SKIPPED"
    )


def test_analysis_director_batch_and_accept_event_commit_atomically(tmp_path: Path) -> None:
    db, source_rows = _analysis_batch_db(tmp_path)
    batch = [
        {
            "segment_id": row["id"],
            "stable_id": row["stable_id"],
            "text_sha256": row["text_sha256"],
            "expected_status": "pending",
            "data": _canonical_analysis_data(),
        }
        for row in source_rows
    ]

    db.update_analysis_batch_with_event(
        batch,
        low_confidence_threshold=0.65,
        event_level="info",
        event_code="ANALYSIS_DIRECTOR_CRITIC_ACCEPTED",
        event_message="accepted",
        event_details={"candidate_hash": "candidate"},
        **ANALYSIS_MODEL_COMMIT,
        pronunciations=[{
            "surface": "Michael",
            "normalized_surface": "michael",
            "spoken_form": "Mai-cồ",
            "confidence": 0.91,
            "source": "analysis",
        }],
    )

    assert {row["status"] for row in db.list_segments()} == {"analyzed"}
    event = db.list_events()[-1]
    assert event["code"] == "ANALYSIS_DIRECTOR_CRITIC_ACCEPTED"
    assert json.loads(event["details_json"])["candidate_hash"] == "candidate"
    pronunciation = db.list_pronunciations()[0]
    assert pronunciation["surface"] == "Michael"
    assert pronunciation["spoken_form"] == "Mai-cồ"


def test_analysis_candidate_reservation_survives_reopen_and_consumes_crashed_intent(
    tmp_path: Path,
) -> None:
    db, source_rows = _analysis_batch_db(tmp_path)
    assert db.has_analysis_candidates() is False
    candidate = _allocate_analysis_candidate(db, source_rows, critic_max_attempts=2)
    assert db.has_analysis_candidates() is True
    first = db.reserve_analysis_critic_attempt(
        int(candidate["id"]),
        expected_state="allocated",
        max_attempts=2,
        intent={"candidate_hash": str(candidate["candidate_hash"]), "attempt": 1},
        contract={
            **_accepted_critic_contract(_analysis_acceptance_envelope(source_rows)),
            "seed": 11,
            "temperature": 0.2,
        },
    )

    reopened = ProjectDB(db.path)
    resumable = reopened.find_resumable_analysis_candidate(
        policy_fingerprint=ANALYSIS_POLICY_FINGERPRINT,
        model_name=ANALYSIS_MODEL_NAME,
        model_digest=ANALYSIS_MODEL_DIGEST,
        group_fingerprint=ANALYSIS_GROUP_FINGERPRINT,
        context_hash=ANALYSIS_CONTEXT_HASH,
    )
    assert int(resumable["id"]) == int(candidate["id"])
    second = reopened.reserve_analysis_critic_attempt(
        int(candidate["id"]),
        expected_state="critic_in_flight",
        max_attempts=2,
        intent={"candidate_hash": str(candidate["candidate_hash"]), "attempt": 2},
        contract={
            **_accepted_critic_contract(_analysis_acceptance_envelope(source_rows)),
            "seed": 12,
            "temperature": 0.2,
        },
    )

    assert int(first["attempt_number"]) == 1
    assert int(second["attempt_number"]) == 2
    attempts = reopened.list_analysis_critic_attempts(int(candidate["id"]))
    assert [row["state"] for row in attempts] == ["abandoned", "reserved"]
    with pytest.raises(RuntimeError, match="budget is exhausted"):
        reopened.reserve_analysis_critic_attempt(
            int(candidate["id"]),
            expected_state="critic_in_flight",
            max_attempts=2,
            intent={
                "candidate_hash": str(candidate["candidate_hash"]),
                "attempt": 3,
            },
            contract={
                **_accepted_critic_contract(_analysis_acceptance_envelope(source_rows)),
                "seed": 13,
            },
        )


def test_analysis_candidate_records_generator_retries_without_resetting_critic_budget(
    tmp_path: Path,
) -> None:
    db, source_rows = _analysis_batch_db(tmp_path)
    candidate = _allocate_analysis_candidate(db, source_rows, critic_max_attempts=2)
    attempt = db.reserve_analysis_critic_attempt(
        int(candidate["id"]),
        expected_state="allocated",
        max_attempts=2,
        intent={"candidate_hash": str(candidate["candidate_hash"])},
        contract=_accepted_critic_contract(_analysis_acceptance_envelope(source_rows)),
    )
    retry_contract = {"attempt": 2, "seed": 202, "blind_envelope_hash": "changed"}

    db.record_analysis_candidate_generator_contract(int(candidate["id"]), retry_contract)
    replay = db.record_analysis_candidate_generator_contract(
        int(candidate["id"]),
        retry_contract,
    )

    contracts = db.list_analysis_candidate_generator_contracts(int(candidate["id"]))
    assert len(contracts) == 2
    assert {int(row["occurrence_count"]) for row in contracts} == {1}
    assert int(replay["critic_attempt_count"]) == int(attempt["attempt_number"]) == 1
    assert replay["state"] == "critic_in_flight"


def test_final_crashed_critic_intent_can_be_terminalized_after_budget_exhaustion(
    tmp_path: Path,
) -> None:
    db, source_rows = _analysis_batch_db(tmp_path)
    candidate = _allocate_analysis_candidate(db, source_rows, critic_max_attempts=1)
    db.reserve_analysis_critic_attempt(
        int(candidate["id"]),
        expected_state="allocated",
        max_attempts=1,
        intent={"candidate_hash": str(candidate["candidate_hash"])},
        contract=_accepted_critic_contract(_analysis_acceptance_envelope(source_rows)),
    )

    reopened = ProjectDB(db.path)
    terminal = reopened.finalize_exhausted_analysis_critic_candidate(
        int(candidate["id"]),
        reason="final critic request crashed",
    )
    replay = reopened.finalize_exhausted_analysis_critic_candidate(
        int(candidate["id"]),
        reason="final critic request crashed",
    )

    assert terminal["state"] == replay["state"] == "terminal"
    assert reopened.list_analysis_critic_attempts(int(candidate["id"]))[0]["state"] == (
        "abandoned"
    )


def test_analysis_candidate_completion_is_exact_idempotent_and_reopenable_without_model(
    tmp_path: Path,
) -> None:
    db, source_rows = _analysis_batch_db(tmp_path)
    candidate = _allocate_analysis_candidate(db, source_rows)
    attempt = db.reserve_analysis_critic_attempt(
        int(candidate["id"]),
        expected_state="allocated",
        max_attempts=2,
        intent={"candidate_hash": str(candidate["candidate_hash"])},
        contract=_accepted_critic_contract(_analysis_acceptance_envelope(source_rows)),
    )
    completion_kwargs = {
        "expected_intent_hash": str(attempt["intent_hash"]),
        "expected_contract_hash": str(attempt["contract_hash"]),
        "result_state": "critic_accepted",
        "outcome": {"accepted": True},
        "evidence": _accepted_critic_evidence(_analysis_acceptance_envelope(source_rows)),
        "commit_envelope": _analysis_acceptance_envelope(source_rows),
    }

    completed = db.complete_analysis_critic_attempt(
        int(candidate["id"]),
        1,
        **completion_kwargs,
    )
    replay = ProjectDB(db.path).complete_analysis_critic_attempt(
        int(candidate["id"]),
        1,
        **completion_kwargs,
    )

    assert replay["completion_hash"] == completed["completion_hash"]
    reopened = ProjectDB(db.path)
    resumable = reopened.find_resumable_analysis_candidate(
        policy_fingerprint=ANALYSIS_POLICY_FINGERPRINT,
        model_name=ANALYSIS_MODEL_NAME,
        model_digest=ANALYSIS_MODEL_DIGEST,
        group_fingerprint=ANALYSIS_GROUP_FINGERPRINT,
        context_hash=ANALYSIS_CONTEXT_HASH,
    )
    snapshot = reopened.analysis_candidate_acceptance_envelope(int(candidate["id"]))
    assert resumable["state"] == "critic_accepted"
    assert snapshot["candidate"] == _analysis_acceptance_envelope(source_rows)
    assert snapshot["critic_outcome"] == {
        "candidate_state": "critic_accepted",
        "payload": {"accepted": True},
    }
    different_evidence = _accepted_critic_evidence(
        _analysis_acceptance_envelope(source_rows)
    )
    different_evidence["segments"][0]["critic"]["rationale"] = "Khác nhưng vẫn hợp lệ."
    with pytest.raises(RuntimeError, match="replay payload differs"):
        reopened.complete_analysis_critic_attempt(
            int(candidate["id"]),
            1,
            **{**completion_kwargs, "evidence": different_evidence},
        )


def test_analysis_candidate_rejects_arbitrarily_lowered_derived_confidence(
    tmp_path: Path,
) -> None:
    db, source_rows = _analysis_batch_db(tmp_path)
    envelope = _analysis_acceptance_envelope(source_rows)
    candidate = _allocate_analysis_candidate(db, source_rows, candidate=envelope)
    attempt = db.reserve_analysis_critic_attempt(
        int(candidate["id"]),
        expected_state="allocated",
        max_attempts=2,
        intent={"candidate_hash": str(candidate["candidate_hash"])},
        contract=_accepted_critic_contract(envelope),
    )
    commit_envelope = copy.deepcopy(envelope)
    commit_envelope["segments"][0]["data"]["confidence"] = 0.7
    evidence = _accepted_critic_evidence(envelope)
    evidence["segments"][0]["derived_confidence"] = 0.7

    with pytest.raises(RuntimeError, match="exact delivery/confidence"):
        db.complete_analysis_critic_attempt(
            int(candidate["id"]),
            1,
            expected_intent_hash=str(attempt["intent_hash"]),
            expected_contract_hash=str(attempt["contract_hash"]),
            result_state="critic_accepted",
            outcome={"accepted": True},
            evidence=evidence,
            commit_envelope=commit_envelope,
        )


def test_v22_content_candidate_below_floor_is_rejected_before_critic_reserve(
    tmp_path: Path,
) -> None:
    db, source_rows = _analysis_batch_db(tmp_path)
    envelope = _analysis_acceptance_envelope(source_rows)
    envelope["segments"][0]["data"]["confidence"] = 0.64
    candidate = _allocate_analysis_candidate(db, source_rows, candidate=envelope)

    with pytest.raises(RuntimeError, match="below the reserved critic floor"):
        db.reserve_analysis_critic_attempt(
            int(candidate["id"]),
            expected_state="allocated",
            max_attempts=2,
            intent={"candidate_hash": str(candidate["candidate_hash"])},
            contract=_accepted_critic_contract(envelope),
        )

    reopened = ProjectDB(db.path)
    assert reopened.get_analysis_candidate(int(candidate["id"]))["state"] == "allocated"
    assert reopened.list_analysis_critic_attempts(int(candidate["id"])) == []


def test_v22_critic_below_floor_cannot_complete_an_accepted_candidate(
    tmp_path: Path,
) -> None:
    db, source_rows = _analysis_batch_db(tmp_path)
    envelope = _analysis_acceptance_envelope(source_rows)
    candidate = _allocate_analysis_candidate(db, source_rows, candidate=envelope)
    attempt = db.reserve_analysis_critic_attempt(
        int(candidate["id"]),
        expected_state="allocated",
        max_attempts=2,
        intent={"candidate_hash": str(candidate["candidate_hash"])},
        contract=_accepted_critic_contract(envelope),
    )
    evidence = _accepted_critic_evidence(envelope)
    commit_envelope = copy.deepcopy(envelope)
    for index, item in enumerate(evidence["segments"]):
        item["critic"]["confidence"] = 0.64
        item["derived_confidence"] = 0.64
        commit_envelope["segments"][index]["data"]["confidence"] = 0.64

    with pytest.raises(RuntimeError, match="exact delivery/confidence"):
        db.complete_analysis_critic_attempt(
            int(candidate["id"]),
            1,
            expected_intent_hash=str(attempt["intent_hash"]),
            expected_contract_hash=str(attempt["contract_hash"]),
            result_state="critic_accepted",
            outcome={"accepted": True},
            evidence=evidence,
            commit_envelope=commit_envelope,
        )

    assert db.get_analysis_candidate(int(candidate["id"]))["state"] == (
        "critic_in_flight"
    )


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("confidence_floor", None),
        ("confidence_floor", -0.01),
        ("confidence_cap", 1.01),
        ("confidence_floor", 0.96),
        ("confidence_floor", float("nan")),
    ),
)
def test_v22_critic_reserve_rejects_invalid_confidence_contract(
    tmp_path: Path,
    field: str,
    value: object,
) -> None:
    db, source_rows = _analysis_batch_db(tmp_path)
    candidate = _allocate_analysis_candidate(db, source_rows)
    contract = _accepted_critic_contract(_analysis_acceptance_envelope(source_rows))
    if value is None:
        del contract[field]
    else:
        contract[field] = value

    with pytest.raises(ValueError, match="confidence floor/cap"):
        db.reserve_analysis_critic_attempt(
            int(candidate["id"]),
            expected_state="allocated",
            max_attempts=2,
            intent={"candidate_hash": str(candidate["candidate_hash"])},
            contract=contract,
        )

    assert db.list_analysis_critic_attempts(int(candidate["id"])) == []


def test_v24_critic_reserve_rejects_floor_above_schema_maximum(
    tmp_path: Path,
) -> None:
    db, source_rows = _analysis_batch_db(tmp_path)
    candidate = _allocate_analysis_candidate(db, source_rows)
    contract = _accepted_critic_contract(_analysis_acceptance_envelope(source_rows))
    contract["confidence_floor"] = 0.995
    contract["confidence_cap"] = 0.999

    with pytest.raises(ValueError, match="critic schema maximum"):
        db.reserve_analysis_critic_attempt(
            int(candidate["id"]),
            expected_state="allocated",
            max_attempts=2,
            intent={"candidate_hash": str(candidate["candidate_hash"])},
            contract=contract,
        )

    assert db.list_analysis_critic_attempts(int(candidate["id"])) == []


@pytest.mark.parametrize(
    ("field", "value"),
    (("confidence_floor", 0.5), ("confidence_cap", 0.9)),
)
def test_v22_acceptance_rejects_critic_floor_or_cap_contract_tamper(
    tmp_path: Path,
    field: str,
    value: float,
) -> None:
    db, source_rows = _analysis_batch_db(tmp_path)
    envelope = _analysis_acceptance_envelope(source_rows)
    candidate = _allocate_analysis_candidate(db, source_rows, candidate=envelope)
    attempt = db.reserve_analysis_critic_attempt(
        int(candidate["id"]),
        expected_state="allocated",
        max_attempts=2,
        intent={"candidate_hash": str(candidate["candidate_hash"])},
        contract=_accepted_critic_contract(envelope),
    )
    evidence = _accepted_critic_evidence(envelope)
    evidence["critic_contract"][field] = value

    with pytest.raises(RuntimeError, match="differs from the reserved request contract"):
        db.complete_analysis_critic_attempt(
            int(candidate["id"]),
            1,
            expected_intent_hash=str(attempt["intent_hash"]),
            expected_contract_hash=str(attempt["contract_hash"]),
            result_state="critic_accepted",
            outcome={"accepted": True},
            evidence=evidence,
            commit_envelope=envelope,
        )
def test_v24_reopen_rejects_rehashed_critic_floor_above_schema_maximum(
    tmp_path: Path,
) -> None:
    db, source_rows = _analysis_batch_db(tmp_path)
    candidate = _allocate_analysis_candidate(db, source_rows)
    db.reserve_analysis_critic_attempt(
        int(candidate["id"]),
        expected_state="allocated",
        max_attempts=2,
        intent={"candidate_hash": str(candidate["candidate_hash"])},
        contract=_accepted_critic_contract(_analysis_acceptance_envelope(source_rows)),
    )
    tampered_contract = _accepted_critic_contract(
        _analysis_acceptance_envelope(source_rows)
    )
    tampered_contract["confidence_floor"] = 0.995
    tampered_contract["confidence_cap"] = 0.999
    tampered_json = json.dumps(
        tampered_contract,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    with db.connect() as conn:
        conn.execute(
            "UPDATE analysis_critic_attempts SET contract_json=?,contract_hash=? "
            "WHERE analysis_candidate_id=? AND attempt_number=1",
            (tampered_json, sha256_text(tampered_json), int(candidate["id"])),
        )

    with pytest.raises(RuntimeError, match="critic schema maximum"):
        ProjectDB(db.path).find_resumable_analysis_candidate(
            policy_fingerprint=ANALYSIS_POLICY_FINGERPRINT,
            model_name=ANALYSIS_MODEL_NAME,
            model_digest=ANALYSIS_MODEL_DIGEST,
            group_fingerprint=ANALYSIS_GROUP_FINGERPRINT,
            context_hash=ANALYSIS_CONTEXT_HASH,
        )


@pytest.mark.parametrize("policy_field", ("policy_version", "director_policy_version"))
def test_v23_critic_reserve_rejects_stale_v5_policy(
    tmp_path: Path,
    policy_field: str,
) -> None:
    db, source_rows = _analysis_batch_db(tmp_path)
    envelope = _analysis_acceptance_envelope(source_rows)
    candidate = _allocate_analysis_candidate(db, source_rows, candidate=envelope)
    contract = _accepted_critic_contract(envelope)
    contract[policy_field] = "second_pass_v5"

    with pytest.raises(ValueError, match="current director policy"):
        db.reserve_analysis_critic_attempt(
            int(candidate["id"]),
            expected_state="allocated",
            max_attempts=2,
            intent={"candidate_hash": str(candidate["candidate_hash"])},
            contract=contract,
        )

    assert db.list_analysis_critic_attempts(int(candidate["id"])) == []


def test_v36_critic_reserve_rejects_stale_retry_schema_policy(
    tmp_path: Path,
) -> None:
    db, source_rows = _analysis_batch_db(tmp_path)
    envelope = _analysis_acceptance_envelope(source_rows)
    candidate = _allocate_analysis_candidate(db, source_rows, candidate=envelope)
    contract = _accepted_critic_contract(envelope)
    contract["schema_policy_version"] = "per_id_direct_affect_rejection_v0"

    with pytest.raises(ValueError, match="invalid retry schema fields"):
        db.reserve_analysis_critic_attempt(
            int(candidate["id"]),
            expected_state="allocated",
            max_attempts=2,
            intent={"candidate_hash": str(candidate["candidate_hash"])},
            contract=contract,
        )

    assert db.list_analysis_critic_attempts(int(candidate["id"])) == []


def test_v36_critic_retry_schema_rejects_forged_direct_affect_id(
    tmp_path: Path,
) -> None:
    source_text = (
        "Một cậu bé nhìn thấy Hạ Phong đang đứng bên giường thì vô cùng kinh "
        "ngạc và mừng rỡ:"
    )
    db, source_rows = _analysis_batch_db(tmp_path, texts=(source_text,))
    envelope = _analysis_acceptance_envelope(source_rows)
    candidate = _allocate_analysis_candidate(db, source_rows, candidate=envelope)
    contract = _accepted_critic_contract(envelope)
    contract["rejected_emotions_by_id"] = [
        {"id": "S001", "emotions": ["neutral"]}
    ]

    assert contract["rejected_emotions_by_id"] == [
        {"id": "S001", "emotions": ["neutral"]}
    ]
    contract["rejected_emotions_by_id"] = [
        {"id": "S002", "emotions": ["neutral"]}
    ]

    with pytest.raises(ValueError, match="retry schema is not source-bound"):
        db.reserve_analysis_critic_attempt(
            int(candidate["id"]),
            expected_state="allocated",
            max_attempts=2,
            intent={"candidate_hash": str(candidate["candidate_hash"])},
            contract=contract,
        )

    assert db.list_analysis_critic_attempts(int(candidate["id"])) == []


def test_v37_critic_reserve_cannot_omit_generator_rejection_map(
    tmp_path: Path,
) -> None:
    source_text = (
        "Một cậu bé nhìn thấy Hạ Phong đang đứng bên giường thì vô cùng "
        "kinh ngạc và mừng rỡ:"
    )
    rejection_map = [{"id": "S001", "emotions": ["neutral"]}]
    db, source_rows = _analysis_batch_db(tmp_path, texts=(source_text,))
    envelope = _analysis_acceptance_envelope(source_rows, emotion="surprised")
    candidate = _allocate_analysis_candidate(
        db,
        source_rows,
        candidate=envelope,
        generator_contract={
            "attempt": 2,
            "seed": 101,
            "rejected_emotions_by_id": rejection_map,
        },
    )
    critic_contract = _accepted_critic_contract(envelope)

    with pytest.raises(ValueError, match="generator rejection contract"):
        db.reserve_analysis_critic_attempt(
            int(candidate["id"]),
            expected_state="allocated",
            max_attempts=2,
            intent={"candidate_hash": str(candidate["candidate_hash"])},
            contract=critic_contract,
        )

    assert db.list_analysis_critic_attempts(int(candidate["id"])) == []


def test_v39_generator_rejection_map_cannot_override_physical_collapse(
    tmp_path: Path,
) -> None:
    source_text = (
        "Phổi và yết hầu đang bị thiêu đốt, ý thức dần trở nên mơ hồ, "
        "nhưng ánh mắt cậu tràn ngập vẻ tự hào."
    )
    rejection_map = [{"id": "S001", "emotions": ["neutral"]}]
    db, source_rows = _analysis_batch_db(tmp_path, texts=(source_text,))
    envelope = _analysis_acceptance_envelope(source_rows, emotion="happy")

    with pytest.raises(ValueError, match="retry rejection schema is not source-bound"):
        _allocate_analysis_candidate(
            db,
            source_rows,
            candidate=envelope,
            generator_contract={
                "attempt": 2,
                "seed": 101,
                "rejected_emotions_by_id": rejection_map,
            },
        )

    assert db.has_analysis_candidates() is False


def test_v37_candidate_history_cannot_change_critic_rejection_schema(
    tmp_path: Path,
) -> None:
    source_text = (
        "Một cậu bé nhìn thấy Hạ Phong đang đứng bên giường thì vô cùng "
        "kinh ngạc và mừng rỡ:"
    )
    db, source_rows = _analysis_batch_db(tmp_path, texts=(source_text,))
    candidate = _allocate_analysis_candidate(db, source_rows)

    with pytest.raises(RuntimeError, match="changed its critic rejection schema"):
        db.record_analysis_candidate_generator_contract(
            int(candidate["id"]),
            {
                "attempt": 2,
                "seed": 202,
                "rejected_emotions_by_id": [
                    {"id": "S001", "emotions": ["neutral"]}
                ],
            },
        )

    assert len(db.list_analysis_candidate_generator_contracts(int(candidate["id"]))) == 1


def test_v38_rehashed_generator_history_cannot_change_rejection_schema(
    tmp_path: Path,
) -> None:
    source_text = (
        "Một cậu bé nhìn thấy Hạ Phong đang đứng bên giường thì vô cùng "
        "kinh ngạc và mừng rỡ:"
    )
    db, source_rows = _analysis_batch_db(tmp_path, texts=(source_text,))
    candidate = _allocate_analysis_candidate(db, source_rows)
    candidate_id = int(candidate["id"])
    db.record_analysis_candidate_generator_contract(
        candidate_id,
        {"attempt": 2, "seed": 202},
    )
    tampered = {
        "attempt": 2,
        "seed": 202,
        "rejected_emotions_by_id": [
            {"id": "S001", "emotions": ["neutral"]}
        ],
    }
    tampered_json = json.dumps(
        tampered,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    with db.connect() as conn:
        history_id = int(
            conn.execute(
                "SELECT id FROM analysis_candidate_generator_contracts "
                "WHERE analysis_candidate_id=? ORDER BY id DESC LIMIT 1",
                (candidate_id,),
            ).fetchone()["id"]
        )
        conn.execute(
            "UPDATE analysis_candidate_generator_contracts "
            "SET generator_contract_json=?,generator_contract_hash=? WHERE id=?",
            (tampered_json, sha256_text(tampered_json), history_id),
        )

    with pytest.raises(RuntimeError, match="changed its critic rejection schema"):
        ProjectDB(db.path).list_analysis_candidate_generator_contracts(candidate_id)


def test_v38_critic_intent_must_bind_parent_candidate_hash(tmp_path: Path) -> None:
    db, source_rows = _analysis_batch_db(tmp_path)
    envelope = _analysis_acceptance_envelope(source_rows)
    candidate = _allocate_analysis_candidate(db, source_rows, candidate=envelope)

    with pytest.raises(ValueError, match="bind its parent candidate hash"):
        db.reserve_analysis_critic_attempt(
            int(candidate["id"]),
            expected_state="allocated",
            max_attempts=2,
            intent={"candidate_hash": "0" * 64},
            contract=_accepted_critic_contract(envelope),
        )

    assert db.list_analysis_critic_attempts(int(candidate["id"])) == []


def test_v38_critic_contract_must_bind_parent_candidate_hash(tmp_path: Path) -> None:
    db, source_rows = _analysis_batch_db(tmp_path)
    envelope = _analysis_acceptance_envelope(source_rows)
    candidate = _allocate_analysis_candidate(db, source_rows, candidate=envelope)
    contract = _accepted_critic_contract(envelope)
    contract["candidate_hash"] = "0" * 64

    with pytest.raises(ValueError, match="contract must bind its parent candidate hash"):
        db.reserve_analysis_critic_attempt(
            int(candidate["id"]),
            expected_state="allocated",
            max_attempts=2,
            intent={"candidate_hash": str(candidate["candidate_hash"])},
            contract=contract,
        )

    assert db.list_analysis_critic_attempts(int(candidate["id"])) == []


def test_v38_rehashed_critic_contract_cannot_change_parent_candidate_hash(
    tmp_path: Path,
) -> None:
    db, source_rows = _analysis_batch_db(tmp_path)
    envelope = _analysis_acceptance_envelope(source_rows)
    candidate = _allocate_analysis_candidate(db, source_rows, candidate=envelope)
    db.reserve_analysis_critic_attempt(
        int(candidate["id"]),
        expected_state="allocated",
        max_attempts=2,
        intent={"candidate_hash": str(candidate["candidate_hash"])},
        contract=_accepted_critic_contract(envelope),
    )
    forged_contract = _accepted_critic_contract(envelope)
    forged_contract["candidate_hash"] = "0" * 64
    forged_json = json.dumps(
        forged_contract,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    with db.connect() as conn:
        conn.execute(
            "UPDATE analysis_critic_attempts SET contract_json=?,contract_hash=? "
            "WHERE analysis_candidate_id=? AND attempt_number=1",
            (forged_json, sha256_text(forged_json), int(candidate["id"])),
        )

    with pytest.raises(RuntimeError, match="contract is not bound"):
        ProjectDB(db.path).get_analysis_candidate(int(candidate["id"]))


def test_v38_rejected_completion_binds_candidate_contract_outcome_and_segments(
    tmp_path: Path,
) -> None:
    source_text = (
        "Một cậu bé nhìn thấy Hạ Phong đang đứng bên giường thì vô cùng "
        "kinh ngạc và mừng rỡ:"
    )
    rejection_map = [{"id": "S001", "emotions": ["neutral"]}]
    db, source_rows = _analysis_batch_db(tmp_path, texts=(source_text,))
    envelope = _analysis_acceptance_envelope(source_rows, emotion="surprised")
    candidate = _allocate_analysis_candidate(
        db,
        source_rows,
        candidate=envelope,
        generator_contract={
            "attempt": 2,
            "seed": 101,
            "rejected_emotions_by_id": rejection_map,
        },
    )
    candidate_id = int(candidate["id"])
    contract = _accepted_critic_contract(envelope)
    contract["rejected_emotions_by_id"] = copy.deepcopy(rejection_map)
    contract["candidate_hash"] = str(candidate["candidate_hash"])
    attempt = db.reserve_analysis_critic_attempt(
        candidate_id,
        expected_state="allocated",
        max_attempts=2,
        intent={"candidate_hash": str(candidate["candidate_hash"])},
        contract=contract,
    )

    with pytest.raises(RuntimeError, match="Rejected critic evidence"):
        db.complete_analysis_critic_attempt(
            candidate_id,
            1,
            expected_intent_hash=str(attempt["intent_hash"]),
            expected_contract_hash=str(attempt["contract_hash"]),
            result_state="critic_rejected",
            outcome={
                "issues": {
                    str(source_rows[0]["stable_id"]): (
                        "DIRECTOR_FIELD_MISMATCH fields=pace"
                    )
                },
                "retryable_invalid": False,
            },
            evidence={
                "candidate_hash": "0" * 64,
                "critic_contract": copy.deepcopy(contract),
                "segments": [],
            },
        )

    assert db.get_analysis_candidate(candidate_id)["state"] == "critic_in_flight"


def test_v38_accepted_completion_rejects_contradictory_outcome(
    tmp_path: Path,
) -> None:
    db, source_rows = _analysis_batch_db(tmp_path)
    envelope = _analysis_acceptance_envelope(source_rows)
    candidate = _allocate_analysis_candidate(db, source_rows, candidate=envelope)
    attempt = db.reserve_analysis_critic_attempt(
        int(candidate["id"]),
        expected_state="allocated",
        max_attempts=2,
        intent={"candidate_hash": str(candidate["candidate_hash"])},
        contract=_accepted_critic_contract(envelope),
    )

    with pytest.raises(RuntimeError, match="outcome contradicts"):
        db.complete_analysis_critic_attempt(
            int(candidate["id"]),
            1,
            expected_intent_hash=str(attempt["intent_hash"]),
            expected_contract_hash=str(attempt["contract_hash"]),
            result_state="critic_accepted",
            outcome={
                "issues": {
                    str(source_rows[0]["stable_id"]): (
                        "DIRECTOR_FIELD_MISMATCH fields=emotion"
                    )
                },
                "retryable_invalid": True,
            },
            evidence=_accepted_critic_evidence(envelope),
            commit_envelope=envelope,
        )

    with pytest.raises(RuntimeError, match="outcome contradicts"):
        db.complete_analysis_critic_attempt(
            int(candidate["id"]),
            1,
            expected_intent_hash=str(attempt["intent_hash"]),
            expected_contract_hash=str(attempt["contract_hash"]),
            result_state="critic_accepted",
            outcome={"accepted": False},
            evidence=_accepted_critic_evidence(envelope),
            commit_envelope=envelope,
        )

    assert db.get_analysis_candidate(int(candidate["id"]))["state"] == (
        "critic_in_flight"
    )


def test_v38_invalid_completion_rejects_acceptance_outcome(tmp_path: Path) -> None:
    db, source_rows = _analysis_batch_db(tmp_path)
    envelope = _analysis_acceptance_envelope(source_rows)
    candidate = _allocate_analysis_candidate(db, source_rows, candidate=envelope)
    attempt = db.reserve_analysis_critic_attempt(
        int(candidate["id"]),
        expected_state="allocated",
        max_attempts=2,
        intent={"candidate_hash": str(candidate["candidate_hash"])},
        contract=_accepted_critic_contract(envelope),
    )

    with pytest.raises(RuntimeError, match="outcome contradicts"):
        db.complete_analysis_critic_attempt(
            int(candidate["id"]),
            1,
            expected_intent_hash=str(attempt["intent_hash"]),
            expected_contract_hash=str(attempt["contract_hash"]),
            result_state="critic_invalid",
            outcome={"accepted": True},
            evidence={"reason": "schema"},
        )

    assert db.get_analysis_candidate(int(candidate["id"]))["state"] == (
        "critic_in_flight"
    )


def test_v38_terminal_candidate_rejects_rehashed_unknown_final_outcome(
    tmp_path: Path,
) -> None:
    db, source_rows = _analysis_batch_db(tmp_path)
    envelope = _analysis_acceptance_envelope(source_rows)
    candidate = _allocate_analysis_candidate(
        db,
        source_rows,
        candidate=envelope,
        critic_max_attempts=1,
    )
    candidate_id = int(candidate["id"])
    attempt = db.reserve_analysis_critic_attempt(
        candidate_id,
        expected_state="allocated",
        max_attempts=1,
        intent={"candidate_hash": str(candidate["candidate_hash"])},
        contract=_accepted_critic_contract(envelope),
    )
    db.complete_analysis_critic_attempt(
        candidate_id,
        1,
        expected_intent_hash=str(attempt["intent_hash"]),
        expected_contract_hash=str(attempt["contract_hash"]),
        result_state="critic_invalid",
        outcome={"accepted": False},
        evidence={"reason": "schema"},
    )
    db.finalize_exhausted_analysis_critic_candidate(
        candidate_id,
        reason="director_critic_attempt_budget_exhausted",
    )
    with db.connect() as conn:
        stored = conn.execute(
            "SELECT * FROM analysis_critic_attempts "
            "WHERE analysis_candidate_id=? AND attempt_number=1",
            (candidate_id,),
        ).fetchone()
        forged_outcome = {
            "candidate_state": "forged_unknown_state",
            "payload": {"accepted": False},
        }
        forged_outcome_json = json.dumps(
            forged_outcome,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        forged_outcome_hash = sha256_text(forged_outcome_json)
        completion_hash = _canonical_hash(
            {
                "commit_envelope_hash": None,
                "contract_hash": str(stored["contract_hash"]),
                "evidence_hash": str(stored["evidence_hash"]),
                "intent_hash": str(stored["intent_hash"]),
                "outcome_hash": forged_outcome_hash,
            }
        )
        conn.execute(
            "UPDATE analysis_critic_attempts "
            "SET outcome_json=?,outcome_hash=?,completion_hash=? "
            "WHERE analysis_candidate_id=? AND attempt_number=1",
            (
                forged_outcome_json,
                forged_outcome_hash,
                completion_hash,
                candidate_id,
            ),
        )

    with pytest.raises(RuntimeError, match="invalid candidate state"):
        ProjectDB(db.path).get_analysis_candidate(candidate_id)


def test_v37_accepted_evidence_rejects_neutral_schema_violation(
    tmp_path: Path,
) -> None:
    source_text = (
        "Một cậu bé nhìn thấy Hạ Phong đang đứng bên giường thì vô cùng "
        "kinh ngạc và mừng rỡ:"
    )
    rejection_map = [{"id": "S001", "emotions": ["neutral"]}]
    db, source_rows = _analysis_batch_db(tmp_path, texts=(source_text,))
    envelope = _analysis_acceptance_envelope(source_rows, emotion="surprised")
    candidate = _allocate_analysis_candidate(
        db,
        source_rows,
        candidate=envelope,
        generator_contract={
            "attempt": 2,
            "seed": 101,
            "rejected_emotions_by_id": rejection_map,
        },
    )
    contract = _accepted_critic_contract(envelope)
    contract["rejected_emotions_by_id"] = copy.deepcopy(rejection_map)
    contract["candidate_hash"] = str(candidate["candidate_hash"])
    attempt = db.reserve_analysis_critic_attempt(
        int(candidate["id"]),
        expected_state="allocated",
        max_attempts=2,
        intent={"candidate_hash": str(candidate["candidate_hash"])},
        contract=contract,
    )
    evidence = _accepted_critic_evidence(envelope)
    evidence["candidate_hash"] = str(candidate["candidate_hash"])
    evidence["critic_contract"] = copy.deepcopy(contract)
    evidence["segments"][0]["critic"]["emotion"] = "neutral"

    with pytest.raises(RuntimeError, match="violates its retry emotion schema"):
        db.complete_analysis_critic_attempt(
            int(candidate["id"]),
            1,
            expected_intent_hash=str(attempt["intent_hash"]),
            expected_contract_hash=str(attempt["contract_hash"]),
            result_state="critic_accepted",
            outcome={"accepted": True},
            evidence=evidence,
            commit_envelope=envelope,
        )

    assert db.get_analysis_candidate(int(candidate["id"]))["state"] == (
        "critic_in_flight"
    )
    assert db.list_analysis_critic_attempts(int(candidate["id"]))[0]["state"] == (
        "reserved"
    )


@pytest.mark.parametrize(
    ("field", "value", "error"),
    (
        (
            "evidence_policy",
            "target_substring_v1",
            "invalid evidence policy fields",
        ),
        (
            "evidence_text_sha256",
            "f" * 64,
            "evidence policy is not source-bound",
        ),
    ),
)
def test_v23_singleton_contract_rejects_forged_evidence_policy_or_hash(
    tmp_path: Path,
    field: str,
    value: str,
    error: str,
) -> None:
    db, source_rows = _analysis_batch_db(tmp_path, texts=("“Ha…”",))
    envelope = _analysis_acceptance_envelope(source_rows)
    candidate = _allocate_analysis_candidate(db, source_rows, candidate=envelope)
    contract = _accepted_critic_contract(envelope)
    contract[field] = value

    with pytest.raises(ValueError, match=error):
        db.reserve_analysis_critic_attempt(
            int(candidate["id"]),
            expected_state="allocated",
            max_attempts=2,
            intent={"candidate_hash": str(candidate["candidate_hash"])},
            contract=contract,
        )

    assert db.list_analysis_critic_attempts(int(candidate["id"])) == []


def test_v23_singleton_full_target_evidence_survives_crash_reopen_and_commit(
    tmp_path: Path,
) -> None:
    source_text = "“Ha…”"
    db, source_rows = _analysis_batch_db(tmp_path, texts=(source_text,))
    envelope = _analysis_acceptance_envelope(source_rows)
    candidate = _allocate_analysis_candidate(db, source_rows, candidate=envelope)
    candidate_id = int(candidate["id"])
    contract = _accepted_critic_contract(envelope)
    assert contract["policy_version"] == "second_pass_v18"
    assert contract["director_policy_version"] == "second_pass_v18"
    assert (
        contract["evidence_policy"]
        == ANALYSIS_CRITIC_EVIDENCE_POLICY_SINGLETON_FULL_TARGET
    )
    assert contract["evidence_text_sha256"] == sha256_text(source_text)
    attempt = db.reserve_analysis_critic_attempt(
        candidate_id,
        expected_state="allocated",
        max_attempts=2,
        intent={"candidate_hash": str(candidate["candidate_hash"])},
        contract=contract,
    )

    reopened_after_reserve = ProjectDB(db.path)
    evidence = _accepted_critic_evidence(envelope)
    assert evidence["segments"][0]["critic"]["evidence_quote"] == source_text
    assert evidence["segments"][0]["critic"]["accept"] is True
    reopened_after_reserve.complete_analysis_critic_attempt(
        candidate_id,
        1,
        expected_intent_hash=str(attempt["intent_hash"]),
        expected_contract_hash=str(attempt["contract_hash"]),
        result_state="critic_accepted",
        outcome={"accepted": True},
        evidence=evidence,
        commit_envelope=envelope,
    )

    reopened_after_accept = ProjectDB(db.path)
    snapshot = reopened_after_accept.analysis_candidate_acceptance_envelope(candidate_id)
    batch = [
        {
            "segment_id": segment["segment_id"],
            "stable_id": segment["stable_id"],
            "text_sha256": segment["text_sha256"],
            "expected_status": "pending",
            "data": dict(segment["data"]),
        }
        for segment in snapshot["commit_envelope"]["segments"]
    ]
    reopened_after_accept.update_analysis_batch_with_event(
        batch,
        low_confidence_threshold=0.65,
        event_level="info",
        event_code="ANALYSIS_DIRECTOR_CRITIC_ACCEPTED",
        event_message="accepted",
        event_details={"candidate_hash": str(candidate["candidate_hash"])},
        **ANALYSIS_MODEL_COMMIT,
        analysis_candidate_id=candidate_id,
        analysis_policy_fingerprint=ANALYSIS_POLICY_FINGERPRINT,
        analysis_group_fingerprint=ANALYSIS_GROUP_FINGERPRINT,
        analysis_context_hash=ANALYSIS_CONTEXT_HASH,
    )

    committed = ProjectDB(db.path).list_segments()[0]
    assert committed["status"] == "analyzed"
    assert ProjectDB(db.path).get_analysis_candidate(candidate_id)["state"] == "accepted"


@pytest.mark.parametrize(
    "forged_quote",
    (
        "Ha...",
        "“Ha...”",
        "Hạ Phong đột ngột bật dậy thở dốc.",
        "“Ha…” Hạ Phong đột ngột bật dậy thở dốc.",
    ),
)
def test_v23_singleton_full_target_rejects_normalized_or_context_quote(
    tmp_path: Path,
    forged_quote: str,
) -> None:
    db, source_rows = _analysis_batch_db(tmp_path, texts=("“Ha…”",))
    envelope = _analysis_acceptance_envelope(source_rows)
    candidate = _allocate_analysis_candidate(db, source_rows, candidate=envelope)
    attempt = db.reserve_analysis_critic_attempt(
        int(candidate["id"]),
        expected_state="allocated",
        max_attempts=2,
        intent={"candidate_hash": str(candidate["candidate_hash"])},
        contract=_accepted_critic_contract(envelope),
    )
    evidence = _accepted_critic_evidence(envelope)
    evidence["segments"][0]["critic"]["evidence_quote"] = forged_quote

    with pytest.raises(RuntimeError, match="exact delivery/confidence"):
        db.complete_analysis_critic_attempt(
            int(candidate["id"]),
            1,
            expected_intent_hash=str(attempt["intent_hash"]),
            expected_contract_hash=str(attempt["contract_hash"]),
            result_state="critic_accepted",
            outcome={"accepted": True},
            evidence=evidence,
            commit_envelope=envelope,
        )


def test_v23_db_recomputes_host_accept_from_exact_field_deltas(
    tmp_path: Path,
) -> None:
    db, source_rows = _analysis_batch_db(tmp_path, texts=("“Ha…”",))
    envelope = _analysis_acceptance_envelope(source_rows)
    candidate = _allocate_analysis_candidate(db, source_rows, candidate=envelope)
    attempt = db.reserve_analysis_critic_attempt(
        int(candidate["id"]),
        expected_state="allocated",
        max_attempts=2,
        intent={"candidate_hash": str(candidate["candidate_hash"])},
        contract=_accepted_critic_contract(envelope),
    )
    evidence = _accepted_critic_evidence(envelope)
    evidence["segments"][0]["critic"]["accept"] = False

    with pytest.raises(RuntimeError, match="exact delivery/confidence"):
        db.complete_analysis_critic_attempt(
            int(candidate["id"]),
            1,
            expected_intent_hash=str(attempt["intent_hash"]),
            expected_contract_hash=str(attempt["contract_hash"]),
            result_state="critic_accepted",
            outcome={"accepted": True},
            evidence=evidence,
            commit_envelope=envelope,
        )


def test_v27_v26_seq18_anchor_evidence_survives_reserve_reopen_accept_and_commit(
    tmp_path: Path,
) -> None:
    source_text = V26_SEQ18_TEXT
    assert len(source_text) == 261
    assert sha256_text(source_text) == V26_SEQ18_TEXT_SHA256
    anchors = canonical_analysis_critic_source_anchors(source_text)
    assert anchors == canonical_analysis_critic_source_anchors(source_text)
    assert len(anchors) == len(set(anchors))
    assert all(
        anchor in source_text
        and anchor.strip()
        and len(anchor) <= ANALYSIS_CRITIC_EVIDENCE_QUOTE_MAX_LENGTH
        for anchor in anchors
    )

    db, source_rows = _analysis_batch_db(tmp_path, texts=(source_text,))
    envelope = _analysis_acceptance_envelope(source_rows)
    contract = _accepted_critic_contract(envelope)
    assert (
        contract["evidence_policy"]
        == ANALYSIS_CRITIC_EVIDENCE_POLICY_SINGLETON_SOURCE_ANCHOR
    )
    assert contract["policy_version"] == "second_pass_v18"
    assert contract["director_policy_version"] == "second_pass_v18"
    assert contract["evidence_text_sha256"] == V26_SEQ18_TEXT_SHA256
    assert contract["evidence_anchor_set_sha256"] == (
        analysis_critic_anchor_set_sha256(anchors)
    )
    assert contract["evidence_anchor_count"] == len(anchors)

    candidate = _allocate_analysis_candidate(db, source_rows, candidate=envelope)
    candidate_id = int(candidate["id"])
    attempt = db.reserve_analysis_critic_attempt(
        candidate_id,
        expected_state="allocated",
        max_attempts=2,
        intent={"candidate_hash": str(candidate["candidate_hash"])},
        contract=contract,
    )

    reopened_after_reserve = ProjectDB(db.path)
    durable_attempt = reopened_after_reserve.list_analysis_critic_attempts(
        candidate_id
    )[0]
    assert durable_attempt["contract_hash"] == attempt["contract_hash"]
    evidence = _accepted_critic_evidence(envelope)
    assert evidence["segments"][0]["critic"]["evidence_quote"] in anchors
    reopened_after_reserve.complete_analysis_critic_attempt(
        candidate_id,
        1,
        expected_intent_hash=str(attempt["intent_hash"]),
        expected_contract_hash=str(attempt["contract_hash"]),
        result_state="critic_accepted",
        outcome={"accepted": True},
        evidence=evidence,
        commit_envelope=envelope,
    )

    reopened_after_accept = ProjectDB(db.path)
    snapshot = reopened_after_accept.analysis_candidate_acceptance_envelope(candidate_id)
    batch = [
        {
            "segment_id": segment["segment_id"],
            "stable_id": segment["stable_id"],
            "text_sha256": segment["text_sha256"],
            "expected_status": "pending",
            "data": dict(segment["data"]),
        }
        for segment in snapshot["commit_envelope"]["segments"]
    ]
    reopened_after_accept.update_analysis_batch_with_event(
        batch,
        low_confidence_threshold=0.65,
        event_level="info",
        event_code="ANALYSIS_DIRECTOR_CRITIC_ACCEPTED",
        event_message="accepted",
        event_details={"candidate_hash": str(candidate["candidate_hash"])},
        **ANALYSIS_MODEL_COMMIT,
        analysis_candidate_id=candidate_id,
        analysis_policy_fingerprint=ANALYSIS_POLICY_FINGERPRINT,
        analysis_group_fingerprint=ANALYSIS_GROUP_FINGERPRINT,
        analysis_context_hash=ANALYSIS_CONTEXT_HASH,
    )

    committed = ProjectDB(db.path).list_segments()[0]
    assert committed["status"] == "analyzed"
    assert ProjectDB(db.path).get_analysis_candidate(candidate_id)["state"] == "accepted"


@pytest.mark.parametrize(
    ("source_text", "expected_policy", "expected_anchor_count"),
    (
        (
            "ắ" * ANALYSIS_CRITIC_EVIDENCE_QUOTE_MAX_LENGTH,
            ANALYSIS_CRITIC_EVIDENCE_POLICY_SINGLETON_FULL_TARGET,
            0,
        ),
        (
            "ắ" * (ANALYSIS_CRITIC_EVIDENCE_QUOTE_MAX_LENGTH + 1),
            ANALYSIS_CRITIC_EVIDENCE_POLICY_SINGLETON_SOURCE_ANCHOR,
            2,
        ),
        (
            V27_MAX_UNICODE_NO_WHITESPACE_TEXT,
            ANALYSIS_CRITIC_EVIDENCE_POLICY_SINGLETON_SOURCE_ANCHOR,
            2,
        ),
    ),
)
def test_v27_singleton_anchor_policy_has_exact_unicode_length_boundary(
    tmp_path: Path,
    source_text: str,
    expected_policy: str,
    expected_anchor_count: int,
) -> None:
    db, source_rows = _analysis_batch_db(tmp_path, texts=(source_text,))
    envelope = _analysis_acceptance_envelope(source_rows)
    candidate = _allocate_analysis_candidate(db, source_rows, candidate=envelope)
    contract = _accepted_critic_contract(envelope)

    assert contract["evidence_policy"] == expected_policy
    assert contract["evidence_text_sha256"] == sha256_text(source_text)
    assert contract["evidence_anchor_count"] == expected_anchor_count
    if expected_anchor_count:
        anchors = canonical_analysis_critic_source_anchors(source_text)
        assert len(source_text) in {
            ANALYSIS_CRITIC_EVIDENCE_QUOTE_MAX_LENGTH + 1,
            340,
        }
        assert len(anchors) == len(set(anchors)) == expected_anchor_count
        assert all(anchor in source_text for anchor in anchors)
        assert "".join(anchors) == source_text
    db.reserve_analysis_critic_attempt(
        int(candidate["id"]),
        expected_state="allocated",
        max_attempts=2,
        intent={"candidate_hash": str(candidate["candidate_hash"])},
        contract=contract,
    )


@pytest.mark.parametrize(
    "field",
    (
        "evidence_text_sha256",
        "evidence_anchor_set_sha256",
        "evidence_anchor_count",
    ),
)
def test_v27_long_singleton_reserve_requires_every_anchor_contract_field(
    tmp_path: Path,
    field: str,
) -> None:
    db, source_rows = _analysis_batch_db(tmp_path, texts=(V26_SEQ18_TEXT,))
    envelope = _analysis_acceptance_envelope(source_rows)
    candidate = _allocate_analysis_candidate(db, source_rows, candidate=envelope)
    contract = _accepted_critic_contract(envelope)
    contract.pop(field)

    with pytest.raises(ValueError, match="invalid evidence policy fields"):
        db.reserve_analysis_critic_attempt(
            int(candidate["id"]),
            expected_state="allocated",
            max_attempts=2,
            intent={"candidate_hash": str(candidate["candidate_hash"])},
            contract=contract,
        )


@pytest.mark.parametrize(
    ("field", "value", "error"),
    (
        (
            "evidence_policy",
            ANALYSIS_CRITIC_EVIDENCE_POLICY_SINGLETON_FULL_TARGET,
            "invalid evidence policy fields",
        ),
        (
            "evidence_anchor_set_sha256",
            "f" * 64,
            "evidence policy is not source-bound",
        ),
        ("evidence_anchor_count", 99, "evidence policy is not source-bound"),
    ),
)
def test_v27_long_singleton_reserve_rejects_forged_anchor_contract(
    tmp_path: Path,
    field: str,
    value: object,
    error: str,
) -> None:
    db, source_rows = _analysis_batch_db(tmp_path, texts=(V26_SEQ18_TEXT,))
    envelope = _analysis_acceptance_envelope(source_rows)
    candidate = _allocate_analysis_candidate(db, source_rows, candidate=envelope)
    contract = _accepted_critic_contract(envelope)
    contract[field] = value

    with pytest.raises(ValueError, match=error):
        db.reserve_analysis_critic_attempt(
            int(candidate["id"]),
            expected_state="allocated",
            max_attempts=2,
            intent={"candidate_hash": str(candidate["candidate_hash"])},
            contract=contract,
        )


@pytest.mark.parametrize(
    "forged_quote",
    (
        "Hạ Phong",
        unicodedata.normalize(
            "NFD",
            canonical_analysis_critic_source_anchors(V26_SEQ18_TEXT)[0],
        ),
        "Hạ Phong dù là một người tính cách có chút hướng nội",
    ),
)
def test_v27_long_singleton_rejects_substring_or_normalized_quote_not_in_anchor_enum(
    tmp_path: Path,
    forged_quote: str,
) -> None:
    db, source_rows = _analysis_batch_db(tmp_path, texts=(V26_SEQ18_TEXT,))
    envelope = _analysis_acceptance_envelope(source_rows)
    candidate = _allocate_analysis_candidate(db, source_rows, candidate=envelope)
    attempt = db.reserve_analysis_critic_attempt(
        int(candidate["id"]),
        expected_state="allocated",
        max_attempts=2,
        intent={"candidate_hash": str(candidate["candidate_hash"])},
        contract=_accepted_critic_contract(envelope),
    )
    anchors = canonical_analysis_critic_source_anchors(V26_SEQ18_TEXT)
    assert forged_quote not in anchors
    evidence = _accepted_critic_evidence(envelope)
    evidence["segments"][0]["critic"]["evidence_quote"] = forged_quote

    with pytest.raises(RuntimeError, match="exact delivery/confidence"):
        db.complete_analysis_critic_attempt(
            int(candidate["id"]),
            1,
            expected_intent_hash=str(attempt["intent_hash"]),
            expected_contract_hash=str(attempt["contract_hash"]),
            result_state="critic_accepted",
            outcome={"accepted": True},
            evidence=evidence,
            commit_envelope=envelope,
        )


def test_v27_source_anchor_contract_deduplicates_repeated_exact_halves(
    tmp_path: Path,
) -> None:
    repeated_half = "A" * 169
    source_text = f"{repeated_half} {repeated_half}"
    assert len(source_text) == 339
    anchors = canonical_analysis_critic_source_anchors(source_text)
    assert anchors == (repeated_half,)

    db, source_rows = _analysis_batch_db(tmp_path, texts=(source_text,))
    envelope = _analysis_acceptance_envelope(source_rows)
    candidate = _allocate_analysis_candidate(db, source_rows, candidate=envelope)
    contract = _accepted_critic_contract(envelope)

    assert contract["evidence_anchor_count"] == 1
    assert contract["evidence_anchor_set_sha256"] == (
        analysis_critic_anchor_set_sha256(anchors)
    )
    db.reserve_analysis_critic_attempt(
        int(candidate["id"]),
        expected_state="allocated",
        max_attempts=2,
        intent={"candidate_hash": str(candidate["candidate_hash"])},
        contract=contract,
    )


def test_v27_reopen_rejects_rehashed_long_singleton_anchor_contract_tamper(
    tmp_path: Path,
) -> None:
    db, source_rows = _analysis_batch_db(tmp_path, texts=(V26_SEQ18_TEXT,))
    envelope = _analysis_acceptance_envelope(source_rows)
    candidate = _allocate_analysis_candidate(db, source_rows, candidate=envelope)
    candidate_id = int(candidate["id"])
    db.reserve_analysis_critic_attempt(
        candidate_id,
        expected_state="allocated",
        max_attempts=2,
        intent={"candidate_hash": str(candidate["candidate_hash"])},
        contract=_accepted_critic_contract(envelope),
    )
    tampered_contract = _accepted_critic_contract(envelope)
    tampered_contract["evidence_anchor_set_sha256"] = "f" * 64
    tampered_json = json.dumps(
        tampered_contract,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    with db.connect() as conn:
        conn.execute(
            "UPDATE analysis_critic_attempts SET contract_json=?,contract_hash=? "
            "WHERE analysis_candidate_id=? AND attempt_number=1",
            (tampered_json, sha256_text(tampered_json), candidate_id),
        )

    with pytest.raises(RuntimeError, match="evidence policy is not source-bound"):
        ProjectDB(db.path).find_resumable_analysis_candidate(
            policy_fingerprint=ANALYSIS_POLICY_FINGERPRINT,
            model_name=ANALYSIS_MODEL_NAME,
            model_digest=ANALYSIS_MODEL_DIGEST,
            group_fingerprint=ANALYSIS_GROUP_FINGERPRINT,
            context_hash=ANALYSIS_CONTEXT_HASH,
        )


def test_v28_per_id_anchor_map_binds_five_rows_through_reopen_and_commit(
    tmp_path: Path,
) -> None:
    texts = (
        "Ánh sáng phủ trên sân.",
        V26_SEQ18_TEXT,
        V27_MAX_UNICODE_NO_WHITESPACE_TEXT,
        "Một tiếng chuông vang lên.",
        "Cánh cửa khép lại nguyên vẹn.",
    )
    db, source_rows = _analysis_batch_db(tmp_path, texts=texts)
    envelope = _analysis_acceptance_envelope(source_rows)
    anchor_map = canonical_analysis_critic_per_id_source_anchor_map(
        envelope["critic_rows"]
    )
    assert [item["id"] for item in anchor_map] == [
        "S001",
        "S002",
        "S003",
        "S004",
        "S005",
    ]
    assert [item["text_sha256"] for item in anchor_map] == [
        sha256_text(text) for text in texts
    ]
    assert tuple(anchor_map[1]["anchors"]) == (
        canonical_analysis_critic_source_anchors(V26_SEQ18_TEXT)
    )
    assert tuple(anchor_map[2]["anchors"]) == (
        canonical_analysis_critic_source_anchors(V27_MAX_UNICODE_NO_WHITESPACE_TEXT)
    )

    contract = _accepted_critic_contract(envelope)
    assert contract["policy_version"] == "second_pass_v18"
    assert contract["evidence_policy"] == (
        ANALYSIS_CRITIC_EVIDENCE_POLICY_PER_ID_SOURCE_ANCHOR
    )
    assert contract["evidence_text_sha256"] == ""
    assert contract["evidence_anchor_set_sha256"] == (
        analysis_critic_per_id_anchor_map_sha256(anchor_map)
    )
    assert contract["evidence_anchor_count"] == sum(
        len(item["anchors"]) for item in anchor_map
    )

    candidate = _allocate_analysis_candidate(db, source_rows, candidate=envelope)
    candidate_id = int(candidate["id"])
    attempt = db.reserve_analysis_critic_attempt(
        candidate_id,
        expected_state="allocated",
        max_attempts=2,
        intent={"candidate_hash": str(candidate["candidate_hash"])},
        contract=contract,
    )
    reopened_after_reserve = ProjectDB(db.path)
    evidence = _accepted_critic_evidence(envelope)
    anchors_by_id = {
        str(item["id"]): frozenset(item["anchors"]) for item in anchor_map
    }
    for critic_row, evidence_row in zip(
        envelope["critic_rows"],
        evidence["segments"],
        strict=True,
    ):
        assert evidence_row["critic"]["evidence_quote"] in anchors_by_id[
            critic_row["id"]
        ]
    reopened_after_reserve.complete_analysis_critic_attempt(
        candidate_id,
        1,
        expected_intent_hash=str(attempt["intent_hash"]),
        expected_contract_hash=str(attempt["contract_hash"]),
        result_state="critic_accepted",
        outcome={"accepted": True},
        evidence=evidence,
        commit_envelope=envelope,
    )

    reopened_after_accept = ProjectDB(db.path)
    snapshot = reopened_after_accept.analysis_candidate_acceptance_envelope(candidate_id)
    batch = [
        {
            "segment_id": segment["segment_id"],
            "stable_id": segment["stable_id"],
            "text_sha256": segment["text_sha256"],
            "expected_status": "pending",
            "data": dict(segment["data"]),
        }
        for segment in snapshot["commit_envelope"]["segments"]
    ]
    reopened_after_accept.update_analysis_batch_with_event(
        batch,
        low_confidence_threshold=0.65,
        event_level="info",
        event_code="ANALYSIS_DIRECTOR_CRITIC_ACCEPTED",
        event_message="accepted",
        event_details={"candidate_hash": str(candidate["candidate_hash"])},
        **ANALYSIS_MODEL_COMMIT,
        analysis_candidate_id=candidate_id,
        analysis_policy_fingerprint=ANALYSIS_POLICY_FINGERPRINT,
        analysis_group_fingerprint=ANALYSIS_GROUP_FINGERPRINT,
        analysis_context_hash=ANALYSIS_CONTEXT_HASH,
    )
    assert {row["status"] for row in ProjectDB(db.path).list_segments()} == {
        "analyzed"
    }
    assert ProjectDB(db.path).get_analysis_candidate(candidate_id)["state"] == (
        "accepted"
    )


@pytest.mark.parametrize(
    "forged_quote",
    (
        "Hàng kế nói một câu khác.",
        "Ánh sáng",
        unicodedata.normalize("NFD", "Ánh sáng phủ trên sân."),
        "Ngữ cảnh hàng xóm không thuộc nguồn.",
    ),
)
def test_v28_multi_row_rejects_cross_id_arbitrary_normalized_or_context_quote(
    tmp_path: Path,
    forged_quote: str,
) -> None:
    texts = ("Ánh sáng phủ trên sân.", "Hàng kế nói một câu khác.")
    db, source_rows = _analysis_batch_db(tmp_path, texts=texts)
    envelope = _analysis_acceptance_envelope(source_rows)
    candidate = _allocate_analysis_candidate(db, source_rows, candidate=envelope)
    attempt = db.reserve_analysis_critic_attempt(
        int(candidate["id"]),
        expected_state="allocated",
        max_attempts=2,
        intent={"candidate_hash": str(candidate["candidate_hash"])},
        contract=_accepted_critic_contract(envelope),
    )
    first_anchors = canonical_analysis_critic_source_anchors(texts[0])
    assert forged_quote not in first_anchors
    evidence = _accepted_critic_evidence(envelope)
    evidence["segments"][0]["critic"]["evidence_quote"] = forged_quote

    with pytest.raises(RuntimeError, match="exact delivery/confidence"):
        db.complete_analysis_critic_attempt(
            int(candidate["id"]),
            1,
            expected_intent_hash=str(attempt["intent_hash"]),
            expected_contract_hash=str(attempt["contract_hash"]),
            result_state="critic_accepted",
            outcome={"accepted": True},
            evidence=evidence,
            commit_envelope=envelope,
        )


@pytest.mark.parametrize(
    ("mutation", "error"),
    (
        ("missing_hash", "invalid evidence policy fields"),
        ("forged_hash", "evidence policy is not source-bound"),
        ("forged_count", "evidence policy is not source-bound"),
        ("swapped_rows", "evidence policy is not source-bound"),
        ("swapped_anchors", "evidence policy is not source-bound"),
        ("rehashed_source", "evidence policy is not source-bound"),
    ),
)
def test_v28_multi_row_reserve_rejects_missing_forged_swapped_or_rehashed_map(
    tmp_path: Path,
    mutation: str,
    error: str,
) -> None:
    db, source_rows = _analysis_batch_db(
        tmp_path,
        texts=("Nguồn thứ nhất.", V26_SEQ18_TEXT),
    )
    envelope = _analysis_acceptance_envelope(source_rows)
    candidate = _allocate_analysis_candidate(db, source_rows, candidate=envelope)
    contract = _accepted_critic_contract(envelope)
    anchor_map = list(
        canonical_analysis_critic_per_id_source_anchor_map(envelope["critic_rows"])
    )
    if mutation == "missing_hash":
        del contract["evidence_anchor_set_sha256"]
    elif mutation == "forged_hash":
        contract["evidence_anchor_set_sha256"] = "f" * 64
    elif mutation == "forged_count":
        contract["evidence_anchor_count"] = int(contract["evidence_anchor_count"]) + 1
    elif mutation == "swapped_rows":
        contract["evidence_anchor_set_sha256"] = (
            analysis_critic_per_id_anchor_map_sha256(tuple(reversed(anchor_map)))
        )
    elif mutation == "swapped_anchors":
        forged_map = copy.deepcopy(anchor_map)
        forged_map[0]["anchors"], forged_map[1]["anchors"] = (
            forged_map[1]["anchors"],
            forged_map[0]["anchors"],
        )
        contract["evidence_anchor_set_sha256"] = (
            analysis_critic_per_id_anchor_map_sha256(forged_map)
        )
    elif mutation == "rehashed_source":
        forged_map = copy.deepcopy(anchor_map)
        forged_map[0]["text_sha256"] = "f" * 64
        contract["evidence_anchor_set_sha256"] = (
            analysis_critic_per_id_anchor_map_sha256(forged_map)
        )
    else:
        raise AssertionError(f"Unhandled mutation: {mutation}")

    with pytest.raises(ValueError, match=error):
        db.reserve_analysis_critic_attempt(
            int(candidate["id"]),
            expected_state="allocated",
            max_attempts=2,
            intent={"candidate_hash": str(candidate["candidate_hash"])},
            contract=contract,
        )
    assert db.list_analysis_critic_attempts(int(candidate["id"])) == []


def test_v28_multi_row_reserve_rejects_stale_v8_and_legacy_substring_policy(
    tmp_path: Path,
) -> None:
    db, source_rows = _analysis_batch_db(tmp_path)
    envelope = _analysis_acceptance_envelope(source_rows)
    candidate = _allocate_analysis_candidate(db, source_rows, candidate=envelope)
    stale = _accepted_critic_contract(envelope)
    stale["policy_version"] = "second_pass_v8"
    stale["director_policy_version"] = "second_pass_v8"
    with pytest.raises(ValueError, match="current director policy"):
        db.reserve_analysis_critic_attempt(
            int(candidate["id"]),
            expected_state="allocated",
            max_attempts=2,
            intent={"candidate_hash": str(candidate["candidate_hash"])},
            contract=stale,
        )

    legacy = _accepted_critic_contract(envelope)
    legacy.update(
        {
            "evidence_policy": "target_substring_v1",
            "evidence_anchor_set_sha256": "",
            "evidence_anchor_count": 0,
        }
    )
    with pytest.raises(ValueError, match="invalid evidence policy fields"):
        db.reserve_analysis_critic_attempt(
            int(candidate["id"]),
            expected_state="allocated",
            max_attempts=2,
            intent={"candidate_hash": str(candidate["candidate_hash"])},
            contract=legacy,
        )


@pytest.mark.parametrize(
    ("field", "value", "error"),
    (
        ("policy_version", "second_pass_v5", "current director policy"),
        ("director_policy_version", "second_pass_v5", "current director policy"),
        ("evidence_text_sha256", "f" * 64, "evidence policy is not source-bound"),
    ),
)
def test_v23_reopen_rejects_rehashed_policy_or_evidence_contract_tamper(
    tmp_path: Path,
    field: str,
    value: str,
    error: str,
) -> None:
    db, source_rows = _analysis_batch_db(tmp_path, texts=("“Ha…”",))
    envelope = _analysis_acceptance_envelope(source_rows)
    candidate = _allocate_analysis_candidate(db, source_rows, candidate=envelope)
    candidate_id = int(candidate["id"])
    db.reserve_analysis_critic_attempt(
        candidate_id,
        expected_state="allocated",
        max_attempts=2,
        intent={"candidate_hash": str(candidate["candidate_hash"])},
        contract=_accepted_critic_contract(envelope),
    )
    tampered_contract = _accepted_critic_contract(envelope)
    tampered_contract[field] = value
    tampered_json = json.dumps(
        tampered_contract,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    with db.connect() as conn:
        conn.execute(
            "UPDATE analysis_critic_attempts SET contract_json=?,contract_hash=? "
            "WHERE analysis_candidate_id=? AND attempt_number=1",
            (tampered_json, sha256_text(tampered_json), candidate_id),
        )

    with pytest.raises(RuntimeError, match=error):
        ProjectDB(db.path).find_resumable_analysis_candidate(
            policy_fingerprint=ANALYSIS_POLICY_FINGERPRINT,
            model_name=ANALYSIS_MODEL_NAME,
            model_digest=ANALYSIS_MODEL_DIGEST,
            group_fingerprint=ANALYSIS_GROUP_FINGERPRINT,
            context_hash=ANALYSIS_CONTEXT_HASH,
        )


def test_v23_reopen_and_commit_reject_rehashed_singleton_quote_tamper(
    tmp_path: Path,
) -> None:
    db, source_rows = _analysis_batch_db(tmp_path, texts=("“Ha…”",))
    envelope = _analysis_acceptance_envelope(source_rows)
    candidate = _allocate_analysis_candidate(db, source_rows, candidate=envelope)
    candidate_id = int(candidate["id"])
    attempt = db.reserve_analysis_critic_attempt(
        candidate_id,
        expected_state="allocated",
        max_attempts=2,
        intent={"candidate_hash": str(candidate["candidate_hash"])},
        contract=_accepted_critic_contract(envelope),
    )
    db.complete_analysis_critic_attempt(
        candidate_id,
        1,
        expected_intent_hash=str(attempt["intent_hash"]),
        expected_contract_hash=str(attempt["contract_hash"]),
        result_state="critic_accepted",
        outcome={"accepted": True},
        evidence=_accepted_critic_evidence(envelope),
        commit_envelope=envelope,
    )
    with db.connect() as conn:
        stored_attempt = conn.execute(
            "SELECT * FROM analysis_critic_attempts "
            "WHERE analysis_candidate_id=? AND attempt_number=1",
            (candidate_id,),
        ).fetchone()
        stored_candidate = conn.execute(
            "SELECT * FROM analysis_candidates WHERE id=?",
            (candidate_id,),
        ).fetchone()
        tampered_evidence = json.loads(str(stored_attempt["evidence_json"]))
        tampered_evidence["segments"][0]["critic"]["evidence_quote"] = "Ha..."
        evidence_json, evidence_hash = db._canonical_analysis_json(
            tampered_evidence,
            "tampered singleton evidence",
        )
        _completion_json, completion_hash = db._canonical_analysis_json(
            {
                "commit_envelope_hash": stored_candidate["commit_envelope_hash"],
                "contract_hash": stored_attempt["contract_hash"],
                "evidence_hash": evidence_hash,
                "intent_hash": stored_attempt["intent_hash"],
                "outcome_hash": stored_attempt["outcome_hash"],
            },
            "tampered singleton completion",
        )
        conn.execute(
            "UPDATE analysis_critic_attempts SET evidence_json=?,evidence_hash=?,"
            "completion_hash=? WHERE analysis_candidate_id=? AND attempt_number=1",
            (evidence_json, evidence_hash, completion_hash, candidate_id),
        )

    reopened = ProjectDB(db.path)
    with pytest.raises(RuntimeError, match="exact delivery/confidence"):
        reopened.get_analysis_candidate(candidate_id)
    batch = [
        {
            "segment_id": segment["segment_id"],
            "stable_id": segment["stable_id"],
            "text_sha256": segment["text_sha256"],
            "expected_status": "pending",
            "data": dict(segment["data"]),
        }
        for segment in envelope["segments"]
    ]
    with pytest.raises(RuntimeError, match="exact delivery/confidence"):
        reopened.update_analysis_batch_with_event(
            batch,
            low_confidence_threshold=0.65,
            event_level="info",
            event_code="ANALYSIS_DIRECTOR_CRITIC_ACCEPTED",
            event_message="must roll back",
            event_details={"candidate_hash": str(candidate["candidate_hash"])},
            **ANALYSIS_MODEL_COMMIT,
            analysis_candidate_id=candidate_id,
            analysis_policy_fingerprint=ANALYSIS_POLICY_FINGERPRINT,
            analysis_group_fingerprint=ANALYSIS_GROUP_FINGERPRINT,
            analysis_context_hash=ANALYSIS_CONTEXT_HASH,
        )
    assert ProjectDB(db.path).list_segments()[0]["status"] == "pending"


@pytest.mark.parametrize(
    ("field", "value", "error"),
    (
        ("personality_hint", "stoic", "personality_hint must be empty"),
        ("notes", "Director prose must not persist.", "canonical delivery note"),
        (
            "notes",
            "delivery_note_v1={\"kind\":\"narration\",\"emotion\":\"neutral\","
            "\"intensity\":1,\"pace\":\"normal\",\"volume\":\"normal\"}; forged",
            "unrecognized host marker",
        ),
    ),
)
def test_analysis_candidate_rejects_personality_and_noncanonical_notes(
    tmp_path: Path,
    field: str,
    value: str,
    error: str,
) -> None:
    db, source_rows = _analysis_batch_db(tmp_path)
    envelope = _analysis_acceptance_envelope(source_rows)
    envelope["segments"][0]["data"][field] = value

    with pytest.raises(ValueError, match=error):
        _allocate_analysis_candidate(db, source_rows, candidate=envelope)


def test_analysis_candidate_rejects_recognized_host_markers(
    tmp_path: Path,
) -> None:
    db, source_rows = _analysis_batch_db(tmp_path)
    envelope = _analysis_acceptance_envelope(source_rows)
    data = envelope["segments"][0]["data"]
    data["notes"] = canonical_analysis_note(
        data,
        (CONTINUED_DIALOGUE_LOCK_NOTE,),
    )

    with pytest.raises(ValueError, match="must not persist host markers"):
        _allocate_analysis_candidate(db, source_rows, candidate=envelope)


@pytest.mark.parametrize("field", ("personality_hint", "notes"))
def test_analysis_candidate_rejects_note_tamper_after_rehash(
    tmp_path: Path,
    field: str,
) -> None:
    db, source_rows = _analysis_batch_db(tmp_path)
    envelope = _analysis_acceptance_envelope(source_rows)
    candidate = _allocate_analysis_candidate(db, source_rows, candidate=envelope)
    tampered = copy.deepcopy(envelope)
    tampered["segments"][0]["data"][field] = "forged"
    tampered_json = json.dumps(
        tampered,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    with db.connect() as conn:
        conn.execute(
            "UPDATE analysis_candidates SET candidate_json=?,envelope_hash=? WHERE id=?",
            (tampered_json, sha256_text(tampered_json), int(candidate["id"])),
        )

    with pytest.raises(ValueError, match="personality_hint|canonical delivery note"):
        ProjectDB(db.path).get_analysis_candidate(int(candidate["id"]))


@pytest.mark.parametrize("field", ("personality_hint", "notes"))
def test_analysis_commit_rejects_personality_or_note_injection(
    tmp_path: Path,
    field: str,
) -> None:
    db, source_rows = _analysis_batch_db(tmp_path)
    envelope = _analysis_acceptance_envelope(source_rows)
    candidate = _allocate_analysis_candidate(db, source_rows, candidate=envelope)
    attempt = db.reserve_analysis_critic_attempt(
        int(candidate["id"]),
        expected_state="allocated",
        max_attempts=2,
        intent={"candidate_hash": str(candidate["candidate_hash"])},
        contract=_accepted_critic_contract(envelope),
    )
    commit_envelope = copy.deepcopy(envelope)
    commit_envelope["segments"][0]["data"][field] = "forged"

    with pytest.raises(ValueError, match="personality_hint|canonical delivery note"):
        db.complete_analysis_critic_attempt(
            int(candidate["id"]),
            1,
            expected_intent_hash=str(attempt["intent_hash"]),
            expected_contract_hash=str(attempt["contract_hash"]),
            result_state="critic_accepted",
            outcome={"accepted": True},
            evidence=_accepted_critic_evidence(envelope),
            commit_envelope=commit_envelope,
        )


def test_analysis_candidate_rejects_critic_quote_outside_current_source_text(
    tmp_path: Path,
) -> None:
    db, source_rows = _analysis_batch_db(tmp_path)
    envelope = _analysis_acceptance_envelope(source_rows)
    candidate = _allocate_analysis_candidate(db, source_rows, candidate=envelope)
    attempt = db.reserve_analysis_critic_attempt(
        int(candidate["id"]),
        expected_state="allocated",
        max_attempts=2,
        intent={"candidate_hash": str(candidate["candidate_hash"])},
        contract=_accepted_critic_contract(envelope),
    )
    evidence = _accepted_critic_evidence(envelope)
    evidence["segments"][0]["critic"]["evidence_quote"] = "Text 2"

    with pytest.raises(RuntimeError, match="exact delivery/confidence"):
        db.complete_analysis_critic_attempt(
            int(candidate["id"]),
            1,
            expected_intent_hash=str(attempt["intent_hash"]),
            expected_contract_hash=str(attempt["contract_hash"]),
            result_state="critic_accepted",
            outcome={"accepted": True},
            evidence=evidence,
            commit_envelope=envelope,
        )


@pytest.mark.parametrize(
    ("overrides", "expected"),
    (
        ({}, True),
        ({"next_paragraph_index": 31}, False),
        ({"next_kind_hint": "dialogue"}, False),
        ({"next_chapter_id": 2}, False),
        ({"next_seq": 34}, False),
        ({"kind_hint": "dialogue"}, False),
    ),
)
def test_v28_narration_before_thought_predicate_is_exact_source_metadata(
    overrides: dict[str, object],
    expected: bool,
) -> None:
    metadata = {
        "chapter_id": 1,
        "seq": 32,
        "paragraph_index": 30,
        "kind_hint": "narration",
        "next_chapter_id": 1,
        "next_seq": 33,
        "next_paragraph_index": 30,
        "next_kind_hint": "thought",
    }
    metadata.update(overrides)
    assert analysis_source_narration_precedes_thought(**metadata) is expected


@pytest.mark.parametrize(
    ("overrides", "expected"),
    (
        ({}, True),
        ({"next_paragraph_index": 21}, False),
        ({"next_paragraph_index": 23}, False),
        ({"next_kind_hint": "dialogue"}, False),
        ({"next_chapter_id": 2}, False),
        ({"next_seq": 26}, False),
        ({"kind_hint": "thought"}, False),
    ),
)
def test_v31_narration_before_next_paragraph_thought_predicate_is_exact(
    overrides: dict[str, object],
    expected: bool,
) -> None:
    metadata = {
        "chapter_id": 1,
        "seq": 24,
        "paragraph_index": 21,
        "kind_hint": "narration",
        "next_chapter_id": 1,
        "next_seq": 25,
        "next_paragraph_index": 22,
        "next_kind_hint": "thought",
    }
    metadata.update(overrides)
    assert (
        analysis_source_narration_precedes_next_paragraph_thought(**metadata)
        is expected
    )


def test_v31_v30_seq24_mask_survives_reserve_reopen_accept_and_commit(
    tmp_path: Path,
) -> None:
    assert ANALYSIS_CONTEXT_POLICY_NARRATION_BEFORE_NEXT_PARAGRAPH_THOUGHT == (
        "narration_precedes_next_paragraph_thought"
    )
    db, source_rows, envelope, context_hash = (
        _v31_v30_seq24_next_paragraph_thought_db(tmp_path)
    )
    previous_row, target_row, thought_row = source_rows
    assert _analysis_context_hash(
        [target_row],
        _original_neighbor_context(source_rows),
    ) == context_hash
    assert [int(row["seq"]) for row in source_rows] == [23, 24, 25]
    assert [int(row["paragraph_index"]) for row in source_rows] == [20, 21, 22]
    assert target_row["stable_id"] == V30_SEQ24_STABLE_ID
    assert target_row["text_sha256"] == sha256_text(V30_SEQ24_NARRATION_TEXT)
    assert thought_row["stable_id"] == V30_SEQ25_STABLE_ID
    assert thought_row["text_sha256"] == sha256_text(V30_SEQ25_THOUGHT_TEXT)
    critic_row = envelope["critic_rows"][0]
    assert critic_row["context_policy"] == (
        ANALYSIS_CONTEXT_POLICY_NARRATION_BEFORE_NEXT_PARAGRAPH_THOUGHT
    )
    assert critic_row["previous_text"] == V30_SEQ23_PREVIOUS_TEXT
    assert critic_row["next_text"] == ""
    assert critic_row["host_locked_fields"] == {}

    candidate = _allocate_analysis_candidate(
        db,
        [target_row],
        context_hash=context_hash,
        candidate=envelope,
        deterministic_issues=_clean_host_clearance(envelope),
    )
    candidate_id = int(candidate["id"])
    attempt = db.reserve_analysis_critic_attempt(
        candidate_id,
        expected_state="allocated",
        max_attempts=2,
        intent={"candidate_hash": str(candidate["candidate_hash"])},
        contract=_accepted_critic_contract(envelope),
    )
    evidence = _accepted_critic_evidence(envelope)
    assert "host_source_kind_override" not in evidence["segments"][0]
    reopened = ProjectDB(db.path)
    reopened.complete_analysis_critic_attempt(
        candidate_id,
        1,
        expected_intent_hash=str(attempt["intent_hash"]),
        expected_contract_hash=str(attempt["contract_hash"]),
        result_state="critic_accepted",
        outcome={"accepted": True, "next_paragraph_thought_masked": True},
        evidence=evidence,
        commit_envelope=envelope,
    )
    snapshot = ProjectDB(db.path).analysis_candidate_acceptance_envelope(
        candidate_id
    )
    durable_row = snapshot["commit_envelope"]["critic_rows"][0]
    assert durable_row["next_text"] == ""
    assert durable_row["host_locked_fields"] == {}
    segment = snapshot["commit_envelope"]["segments"][0]
    ProjectDB(db.path).update_analysis_batch_with_event(
        [
            {
                "segment_id": segment["segment_id"],
                "stable_id": segment["stable_id"],
                "text_sha256": segment["text_sha256"],
                "expected_status": "pending",
                "data": dict(segment["data"]),
            }
        ],
        low_confidence_threshold=0.65,
        event_level="info",
        event_code="ANALYSIS_DIRECTOR_CRITIC_ACCEPTED",
        event_message="V31 seq24 next-paragraph mask accepted",
        event_details={"candidate_hash": str(candidate["candidate_hash"])},
        **ANALYSIS_MODEL_COMMIT,
        analysis_candidate_id=candidate_id,
        analysis_policy_fingerprint=ANALYSIS_POLICY_FINGERPRINT,
        analysis_group_fingerprint=ANALYSIS_GROUP_FINGERPRINT,
        analysis_context_hash=context_hash,
    )
    committed = {str(row["stable_id"]): row for row in db.list_segments()}
    assert committed[V30_SEQ24_STABLE_ID]["status"] == "analyzed"
    assert committed[V30_SEQ24_STABLE_ID]["kind"] == "narration"
    assert committed[str(previous_row["stable_id"])]["status"] == "pending"
    assert committed[V30_SEQ25_STABLE_ID]["status"] == "pending"


def test_v31_seq24_mask_does_not_cover_critic_kind_dissent(tmp_path: Path) -> None:
    db, source_rows, envelope, context_hash = (
        _v31_v30_seq24_next_paragraph_thought_db(tmp_path)
    )
    target_row = source_rows[1]
    candidate = _allocate_analysis_candidate(
        db,
        [target_row],
        context_hash=context_hash,
        candidate=envelope,
        deterministic_issues=_clean_host_clearance(envelope),
    )
    attempt = db.reserve_analysis_critic_attempt(
        int(candidate["id"]),
        expected_state="allocated",
        max_attempts=2,
        intent={"candidate_hash": str(candidate["candidate_hash"])},
        contract=_accepted_critic_contract(envelope),
    )
    evidence = _accepted_critic_evidence(envelope)
    item = evidence["segments"][0]
    item["critic"].update(
        {
            "accept": False,
            "kind": "thought",
            "rationale": "Critic vẫn đổi câu kể thành thought.",
        }
    )
    item["field_deltas"] = ["kind:narration->thought"]
    item["effective_accept"] = False
    with pytest.raises(RuntimeError, match="exact delivery/confidence"):
        db.complete_analysis_critic_attempt(
            int(candidate["id"]),
            1,
            expected_intent_hash=str(attempt["intent_hash"]),
            expected_contract_hash=str(attempt["contract_hash"]),
            result_state="critic_accepted",
            outcome={"accepted": True},
            evidence=evidence,
            commit_envelope=envelope,
        )
    item["host_source_kind_override"] = {
        "policy_version": ANALYSIS_HOST_SEMANTIC_POLICY_VERSION,
        "rule": ANALYSIS_CONTEXT_SOURCE_KIND_RULE,
    }
    with pytest.raises(RuntimeError, match="unprotected override"):
        db.complete_analysis_critic_attempt(
            int(candidate["id"]),
            1,
            expected_intent_hash=str(attempt["intent_hash"]),
            expected_contract_hash=str(attempt["contract_hash"]),
            result_state="critic_rejected",
            outcome=_rejected_critic_outcome(evidence),
            evidence=evidence,
        )
    del item["host_source_kind_override"]
    db.complete_analysis_critic_attempt(
        int(candidate["id"]),
        1,
        expected_intent_hash=str(attempt["intent_hash"]),
        expected_contract_hash=str(attempt["contract_hash"]),
        result_state="critic_rejected",
        outcome=_rejected_critic_outcome(evidence),
        evidence=evidence,
    )
    assert ProjectDB(db.path).get_analysis_candidate(int(candidate["id"]))[
        "state"
    ] == "critic_rejected"


def test_v33_seq24_compatibility_override_survives_reopen_and_commit(
    tmp_path: Path,
) -> None:
    db, source_rows, envelope, context_hash = (
        _v31_v30_seq24_next_paragraph_thought_db(tmp_path)
    )
    target_row = source_rows[1]
    candidate = _allocate_analysis_candidate(
        db,
        [target_row],
        context_hash=context_hash,
        candidate=envelope,
        deterministic_issues=_clean_host_clearance(envelope),
    )
    candidate_id = int(candidate["id"])
    attempt = db.reserve_analysis_critic_attempt(
        candidate_id,
        expected_state="allocated",
        max_attempts=2,
        intent={"candidate_hash": str(candidate["candidate_hash"])},
        contract=_accepted_critic_contract(envelope),
    )
    evidence = _critic_compatibility_override_evidence(envelope)

    ProjectDB(db.path).complete_analysis_critic_attempt(
        candidate_id,
        1,
        expected_intent_hash=str(attempt["intent_hash"]),
        expected_contract_hash=str(attempt["contract_hash"]),
        result_state="critic_accepted",
        outcome={"accepted": True, "critic_compatibility_override": True},
        evidence=evidence,
        commit_envelope=envelope,
    )

    reopened = ProjectDB(db.path)
    snapshot = reopened.analysis_candidate_acceptance_envelope(candidate_id)
    stored_item = snapshot["critic_evidence"]["segments"][0]
    assert stored_item["critic"]["emotion"] == "afraid"
    assert stored_item["effective_accept"] is True
    assert stored_item["host_critic_compatibility_override"]["source_cue_quote"] == (
        "hỗn loạn"
    )
    segment = snapshot["commit_envelope"]["segments"][0]
    reopened.update_analysis_batch_with_event(
        [
            {
                "segment_id": segment["segment_id"],
                "stable_id": segment["stable_id"],
                "text_sha256": segment["text_sha256"],
                "expected_status": "pending",
                "data": dict(segment["data"]),
            }
        ],
        low_confidence_threshold=0.65,
        event_level="info",
        event_code="ANALYSIS_DIRECTOR_CRITIC_ACCEPTED",
        event_message="V33 seq24 compatibility override accepted",
        event_details={"candidate_hash": str(candidate["candidate_hash"])},
        **ANALYSIS_MODEL_COMMIT,
        analysis_candidate_id=candidate_id,
        analysis_policy_fingerprint=ANALYSIS_POLICY_FINGERPRINT,
        analysis_group_fingerprint=ANALYSIS_GROUP_FINGERPRINT,
        analysis_context_hash=context_hash,
    )

    committed = {
        str(row["stable_id"]): row for row in reopened.list_segments()
    }
    assert committed[V30_SEQ24_STABLE_ID]["status"] == "analyzed"
    assert committed[V30_SEQ24_STABLE_ID]["emotion"] == "neutral"
    assert committed[V30_SEQ24_STABLE_ID]["intensity"] == 1
    assert committed[V30_SEQ24_STABLE_ID]["pace"] == "normal"


@pytest.mark.parametrize(
    ("tamper_field", "tamper_value"),
    (
        ("policy_version", "host_critic_compatibility_v0"),
        ("source_cue_quote", "xa lạ"),
        ("covered_field_deltas", ["emotion:neutral->afraid"]),
    ),
)
def test_v33_seq24_compatibility_override_rejects_forged_evidence(
    tmp_path: Path,
    tamper_field: str,
    tamper_value: object,
) -> None:
    db, source_rows, envelope, context_hash = (
        _v31_v30_seq24_next_paragraph_thought_db(tmp_path)
    )
    candidate = _allocate_analysis_candidate(
        db,
        [source_rows[1]],
        context_hash=context_hash,
        candidate=envelope,
        deterministic_issues=_clean_host_clearance(envelope),
    )
    attempt = db.reserve_analysis_critic_attempt(
        int(candidate["id"]),
        expected_state="allocated",
        max_attempts=2,
        intent={"candidate_hash": str(candidate["candidate_hash"])},
        contract=_accepted_critic_contract(envelope),
    )
    evidence = _critic_compatibility_override_evidence(envelope)
    evidence["segments"][0]["host_critic_compatibility_override"][
        tamper_field
    ] = tamper_value

    with pytest.raises(RuntimeError, match="exact delivery/confidence"):
        db.complete_analysis_critic_attempt(
            int(candidate["id"]),
            1,
            expected_intent_hash=str(attempt["intent_hash"]),
            expected_contract_hash=str(attempt["contract_hash"]),
            result_state="critic_accepted",
            outcome={"accepted": True},
            evidence=evidence,
            commit_envelope=envelope,
        )
    with pytest.raises(RuntimeError, match="contains a compatibility override"):
        db.complete_analysis_critic_attempt(
            int(candidate["id"]),
            1,
            expected_intent_hash=str(attempt["intent_hash"]),
            expected_contract_hash=str(attempt["contract_hash"]),
            result_state="critic_rejected",
            outcome=_rejected_critic_outcome(evidence),
            evidence=evidence,
        )


def test_v38_source_bound_compatibility_row_can_share_rejected_batch(
    tmp_path: Path,
) -> None:
    texts = (
        "Đầu óc hắn hỗn loạn, hắn thậm chí không thể phân biệt được "
        "mình đang nằm mơ hay đã tỉnh.",
        "Cậu bước tới bên giường.",
    )
    db, source_rows = _analysis_batch_db(tmp_path, texts=texts)
    envelope = _analysis_acceptance_envelope(source_rows)
    candidate = _allocate_analysis_candidate(db, source_rows, candidate=envelope)
    candidate_id = int(candidate["id"])
    contract = _accepted_critic_contract(envelope)
    attempt = db.reserve_analysis_critic_attempt(
        candidate_id,
        expected_state="allocated",
        max_attempts=2,
        intent={"candidate_hash": str(candidate["candidate_hash"])},
        contract=contract,
    )
    evidence = _accepted_critic_evidence(envelope)
    compatible = evidence["segments"][0]
    compatible["critic"].update(
        {
            "accept": False,
            "emotion": "afraid",
            "intensity": 2,
            "pace": "fast",
            "rationale": "Critic thấy dấu hiệu hỗn loạn cần delivery mạnh hơn.",
        }
    )
    compatible_deltas = [
        "emotion:neutral->afraid",
        "intensity:1->2",
        "pace:normal->fast",
    ]
    compatible["field_deltas"] = compatible_deltas
    compatible["effective_accept"] = True
    critic_row = envelope["critic_rows"][0]
    compatible["host_critic_compatibility_override"] = (
        analysis_expected_critic_compatibility_override(
            stable_id=str(compatible["stable_id"]),
            source_text=str(critic_row["text"]),
            text_sha256=str(compatible["text_sha256"]),
            source_kind=str(critic_row["hint"]),
            candidate=compatible["candidate"],
            critic=compatible["critic"],
            raw_deltas=compatible_deltas,
        )
    )
    assert compatible["host_critic_compatibility_override"] is not None

    unresolved = evidence["segments"][1]
    unresolved["critic"].update(
        {
            "accept": False,
            "pace": "slow",
            "rationale": "Critic không đồng ý về nhịp đọc hiện tại.",
        }
    )
    unresolved["field_deltas"] = ["pace:normal->slow"]
    unresolved["effective_accept"] = False

    db.complete_analysis_critic_attempt(
        candidate_id,
        1,
        expected_intent_hash=str(attempt["intent_hash"]),
        expected_contract_hash=str(attempt["contract_hash"]),
        result_state="critic_rejected",
        outcome=_rejected_critic_outcome(evidence),
        evidence=evidence,
    )

    reopened = ProjectDB(db.path).get_analysis_candidate(candidate_id)
    assert reopened["state"] == "critic_rejected"


def test_v38_rejected_multi_field_direct_affect_does_not_require_semantic_override(
    tmp_path: Path,
) -> None:
    texts = (
        "Được ánh sáng đó chiếu rọi, Hạ Phong cảm thấy sức lực của mình "
        "dần hồi phục, vì vậy cậu tuyệt vọng gắng gượng đến gần ánh sáng đó.",
        "Cậu bước tiếp về phía trước.",
    )
    db, source_rows = _analysis_batch_db(tmp_path, texts=texts)
    envelope = _semantic_lock_envelope(
        source_rows,
        candidate_emotion="tired",
    )
    clearance = _host_semantic_clearance(
        envelope,
        rule="narration_desperate_exertion",
        cue_class="desperate_exertion",
        allowed_emotions=["afraid", "sad", "tired"],
    )
    candidate = _allocate_analysis_candidate(
        db,
        source_rows,
        candidate=envelope,
        deterministic_issues=clearance,
    )
    candidate_id = int(candidate["id"])
    attempt = db.reserve_analysis_critic_attempt(
        candidate_id,
        expected_state="allocated",
        max_attempts=2,
        intent={"candidate_hash": str(candidate["candidate_hash"])},
        contract=_accepted_critic_contract(envelope),
    )
    evidence = _accepted_critic_evidence(envelope)
    item = evidence["segments"][0]
    item["critic"].update(
        {
            "accept": False,
            "emotion": "neutral",
            "pace": "slow",
            "rationale": "Critic không đồng ý cả cảm xúc lẫn nhịp đọc.",
        }
    )
    item["field_deltas"] = [
        "emotion:tired->neutral",
        "pace:normal->slow",
    ]
    item["effective_accept"] = False
    assert "host_semantic_override" not in item

    db.complete_analysis_critic_attempt(
        candidate_id,
        1,
        expected_intent_hash=str(attempt["intent_hash"]),
        expected_contract_hash=str(attempt["contract_hash"]),
        result_state="critic_rejected",
        outcome=_rejected_critic_outcome(evidence),
        evidence=evidence,
    )

    assert ProjectDB(db.path).get_analysis_candidate(candidate_id)["state"] == (
        "critic_rejected"
    )


@pytest.mark.parametrize(
    ("field", "value", "error"),
    (
        ("context_policy", "adjacent_context", "source-ledger-bound"),
        (
            "context_policy",
            ANALYSIS_CONTEXT_POLICY_NARRATION_BEFORE_THOUGHT,
            "candidate-bound",
        ),
        ("next_text", V30_SEQ25_THOUGHT_TEXT, "source IDs/hashes/delivery"),
        ("previous_text", "forged predecessor", "source-ledger-bound"),
        (
            "host_locked_fields",
            {"kind": "narration"},
            "source-derived protections",
        ),
    ),
)
def test_v31_seq24_mask_rejects_injected_policy_lock_or_context(
    tmp_path: Path,
    field: str,
    value: object,
    error: str,
) -> None:
    db, source_rows, envelope, context_hash = (
        _v31_v30_seq24_next_paragraph_thought_db(tmp_path)
    )
    envelope["critic_rows"][0][field] = value
    with pytest.raises((ValueError, RuntimeError), match=error):
        _allocate_analysis_candidate(
            db,
            [source_rows[1]],
            context_hash=context_hash,
            candidate=envelope,
            deterministic_issues=_clean_host_clearance(envelope),
        )
    assert db.has_analysis_candidates() is False


@pytest.mark.parametrize(
    ("column", "value", "rehash", "error"),
    (
        ("text", "‘Thought đã bị thay nội dung.’", False, "source text hash"),
        ("text", "‘Thought đã bị thay và rehash.’", True, "context hash"),
        ("text_sha256", "e" * 64, False, "source text hash"),
        ("stable_id", "c00001_s0000025_changed", False, "context hash"),
        ("paragraph_index", 23, False, "context hash"),
        ("kind_hint", "dialogue", False, "context hash"),
        ("seq", 26, False, "context hash"),
    ),
)
def test_v31_seq24_mask_revalidates_next_source_on_reopen(
    tmp_path: Path,
    column: str,
    value: object,
    rehash: bool,
    error: str,
) -> None:
    db, source_rows, envelope, context_hash = (
        _v31_v30_seq24_next_paragraph_thought_db(tmp_path)
    )
    candidate = _allocate_analysis_candidate(
        db,
        [source_rows[1]],
        context_hash=context_hash,
        candidate=envelope,
        deterministic_issues=_clean_host_clearance(envelope),
    )
    thought_row = source_rows[2]
    with db.connect() as conn:
        conn.execute(
            f"UPDATE segments SET {column}=? WHERE id=?",
            (value, int(thought_row["id"])),
        )
        if rehash:
            conn.execute(
                "UPDATE segments SET text_sha256=? WHERE id=?",
                (sha256_text(str(value)), int(thought_row["id"])),
            )
    with pytest.raises(RuntimeError, match=error):
        ProjectDB(db.path).get_analysis_candidate(int(candidate["id"]))


@pytest.mark.parametrize(
    ("column", "value", "rehash", "error"),
    (
        ("text", "Previous đã bị thay nội dung.", False, "source text hash"),
        ("text", "Previous đã bị thay và rehash.", True, "context hash"),
        ("text_sha256", "d" * 64, False, "source text hash"),
        ("stable_id", "c00001_s0000023_changed", False, "context hash"),
        ("paragraph_index", 19, False, "context hash"),
        ("kind_hint", "dialogue", False, "context hash"),
        ("seq", 22, False, "context hash"),
    ),
)
def test_v31_seq24_mask_revalidates_previous_source_on_reopen_and_accept(
    tmp_path: Path,
    column: str,
    value: object,
    rehash: bool,
    error: str,
) -> None:
    db, source_rows, envelope, context_hash = (
        _v31_v30_seq24_next_paragraph_thought_db(tmp_path)
    )
    candidate = _allocate_analysis_candidate(
        db,
        [source_rows[1]],
        context_hash=context_hash,
        candidate=envelope,
        deterministic_issues=_clean_host_clearance(envelope),
    )
    attempt = db.reserve_analysis_critic_attempt(
        int(candidate["id"]),
        expected_state="allocated",
        max_attempts=2,
        intent={"candidate_hash": str(candidate["candidate_hash"])},
        contract=_accepted_critic_contract(envelope),
    )
    previous_row = source_rows[0]
    with db.connect() as conn:
        conn.execute(
            f"UPDATE segments SET {column}=? WHERE id=?",
            (value, int(previous_row["id"])),
        )
        if rehash:
            conn.execute(
                "UPDATE segments SET text_sha256=? WHERE id=?",
                (sha256_text(str(value)), int(previous_row["id"])),
            )
    with pytest.raises(RuntimeError, match=error):
        ProjectDB(db.path).get_analysis_candidate(int(candidate["id"]))
    with pytest.raises(RuntimeError, match=error):
        db.complete_analysis_critic_attempt(
            int(candidate["id"]),
            1,
            expected_intent_hash=str(attempt["intent_hash"]),
            expected_contract_hash=str(attempt["contract_hash"]),
            result_state="critic_accepted",
            outcome={"accepted": True},
            evidence=_accepted_critic_evidence(envelope),
            commit_envelope=envelope,
        )


@pytest.mark.parametrize("result_state", ("critic_accepted", "critic_rejected"))
def test_v31_seq24_mask_revalidates_source_before_critic_completion(
    tmp_path: Path,
    result_state: str,
) -> None:
    db, source_rows, envelope, context_hash = (
        _v31_v30_seq24_next_paragraph_thought_db(tmp_path)
    )
    candidate = _allocate_analysis_candidate(
        db,
        [source_rows[1]],
        context_hash=context_hash,
        candidate=envelope,
        deterministic_issues=_clean_host_clearance(envelope),
    )
    attempt = db.reserve_analysis_critic_attempt(
        int(candidate["id"]),
        expected_state="allocated",
        max_attempts=2,
        intent={"candidate_hash": str(candidate["candidate_hash"])},
        contract=_accepted_critic_contract(envelope),
    )
    with db.connect() as conn:
        conn.execute(
            "UPDATE segments SET paragraph_index=23 WHERE id=?",
            (int(source_rows[2]["id"]),),
        )
    with pytest.raises(RuntimeError, match="context hash"):
        db.complete_analysis_critic_attempt(
            int(candidate["id"]),
            1,
            expected_intent_hash=str(attempt["intent_hash"]),
            expected_contract_hash=str(attempt["contract_hash"]),
            result_state=result_state,
            outcome={"accepted": result_state == "critic_accepted"},
            evidence=_accepted_critic_evidence(envelope),
            commit_envelope=(envelope if result_state == "critic_accepted" else None),
        )


def test_v31_seq24_mask_revalidates_rehashed_next_source_before_commit(
    tmp_path: Path,
) -> None:
    db, source_rows, envelope, context_hash = (
        _v31_v30_seq24_next_paragraph_thought_db(tmp_path)
    )
    candidate = _allocate_analysis_candidate(
        db,
        [source_rows[1]],
        context_hash=context_hash,
        candidate=envelope,
        deterministic_issues=_clean_host_clearance(envelope),
    )
    candidate_id = int(candidate["id"])
    attempt = db.reserve_analysis_critic_attempt(
        candidate_id,
        expected_state="allocated",
        max_attempts=2,
        intent={"candidate_hash": str(candidate["candidate_hash"])},
        contract=_accepted_critic_contract(envelope),
    )
    db.complete_analysis_critic_attempt(
        candidate_id,
        1,
        expected_intent_hash=str(attempt["intent_hash"]),
        expected_contract_hash=str(attempt["contract_hash"]),
        result_state="critic_accepted",
        outcome={"accepted": True},
        evidence=_accepted_critic_evidence(envelope),
        commit_envelope=envelope,
    )
    replacement = "‘Thought đã bị thay sau khi critic chấp nhận.’"
    with db.connect() as conn:
        conn.execute(
            "UPDATE segments SET text=?,text_sha256=? WHERE id=?",
            (
                replacement,
                sha256_text(replacement),
                int(source_rows[2]["id"]),
            ),
        )
    reopened = ProjectDB(db.path)
    with pytest.raises(RuntimeError, match="context hash"):
        reopened.analysis_candidate_acceptance_envelope(candidate_id)
    segment = envelope["segments"][0]
    with pytest.raises(RuntimeError, match="context hash"):
        reopened.update_analysis_batch_with_event(
            [
                {
                    "segment_id": segment["segment_id"],
                    "stable_id": segment["stable_id"],
                    "text_sha256": segment["text_sha256"],
                    "expected_status": "pending",
                    "data": dict(segment["data"]),
                }
            ],
            low_confidence_threshold=0.65,
            event_level="info",
            event_code="ANALYSIS_DIRECTOR_CRITIC_ACCEPTED",
            event_message="must roll back V31 source tamper",
            event_details={"candidate_hash": str(candidate["candidate_hash"])},
            **ANALYSIS_MODEL_COMMIT,
            analysis_candidate_id=candidate_id,
            analysis_policy_fingerprint=ANALYSIS_POLICY_FINGERPRINT,
            analysis_group_fingerprint=ANALYSIS_GROUP_FINGERPRINT,
            analysis_context_hash=context_hash,
        )
    assert reopened.get_segment(int(source_rows[1]["id"]))["status"] == "pending"


def test_v31_cross_paragraph_mask_preserves_independent_semantic_lock(
    tmp_path: Path,
) -> None:
    thought_text = "‘Mình vẫn chưa hiểu chuyện gì vừa xảy ra.’"
    db, _source_rows = _analysis_batch_db(
        tmp_path,
        texts=(RECALLED_PERSISTENT_FEAR_TEXT, thought_text),
        kind_hints=("narration", "thought"),
    )
    with db.connect() as conn:
        conn.execute(
            "UPDATE segments SET paragraph_index=CASE seq WHEN 0 THEN 7 ELSE 8 END"
        )
    source_rows = [dict(row) for row in db.list_segments()]
    target_row = source_rows[0]
    envelope = _semantic_lock_envelope(
        [target_row],
        candidate_emotion="afraid",
    )
    critic_row = envelope["critic_rows"][0]
    critic_row["context_policy"] = (
        ANALYSIS_CONTEXT_POLICY_NARRATION_BEFORE_NEXT_PARAGRAPH_THOUGHT
    )
    critic_row["previous_text"] = ""
    critic_row["next_text"] = ""
    assert critic_row["host_locked_fields"] == {"emotion": "afraid"}
    clearance = _host_semantic_clearance(
        envelope,
        rule="narration_recalled_persistent_fear",
        cue_class="recalled_persistent_fear",
        allowed_emotions=["afraid"],
    )
    with db.connect() as conn:
        context_hash = db._analysis_candidate_context_hash_conn(conn, envelope)
    candidate = _allocate_analysis_candidate(
        db,
        [target_row],
        context_hash=context_hash,
        candidate=envelope,
        deterministic_issues=clearance,
    )
    assert candidate["state"] == "allocated"

    neutral_envelope = copy.deepcopy(envelope)
    neutral_envelope["segments"][0]["data"]["emotion"] = "neutral"
    _refresh_analysis_note(neutral_envelope, 0)
    neutral_row = neutral_envelope["critic_rows"][0]
    neutral_row["candidate"]["emotion"] = "neutral"
    neutral_row["host_locked_fields"] = {}
    with pytest.raises(RuntimeError, match="mandatory host semantic"):
        _allocate_analysis_candidate(
            db,
            [target_row],
            context_hash=context_hash,
            candidate=neutral_envelope,
            deterministic_issues=_clean_host_clearance(neutral_envelope),
        )


def test_v28_v27_seq32_context_survives_reserve_reopen_accept_and_commit(
    tmp_path: Path,
) -> None:
    assert ANALYSIS_CONTEXT_POLICY_NARRATION_BEFORE_THOUGHT == (
        "narration_before_thought_previous_only"
    )
    db, source_rows, envelope = _v28_v27_narration_before_thought_db(tmp_path)
    previous_row, target_row, thought_row = source_rows
    assert [int(row["seq"]) for row in source_rows] == [31, 32, 33]
    assert [int(row["paragraph_index"]) for row in source_rows] == [29, 30, 30]
    assert str(target_row["stable_id"]) == V27_SEQ32_STABLE_ID
    assert str(target_row["text"]) == V27_SEQ32_NARRATION_TEXT
    assert str(thought_row["text"]) == V27_SEQ33_THOUGHT_TEXT
    critic_row = envelope["critic_rows"][0]
    assert critic_row["context_policy"] == (
        ANALYSIS_CONTEXT_POLICY_NARRATION_BEFORE_THOUGHT
    )
    assert critic_row["previous_text"] == str(previous_row["text"])[-500:]
    assert critic_row["next_text"] == ""
    assert critic_row["candidate"]["kind"] == "narration"
    assert critic_row["host_locked_fields"] == {"kind": "narration"}

    candidate = _allocate_analysis_candidate(
        db,
        [target_row],
        candidate=envelope,
    )
    candidate_id = int(candidate["id"])
    attempt = db.reserve_analysis_critic_attempt(
        candidate_id,
        expected_state="allocated",
        max_attempts=2,
        intent={"candidate_hash": str(candidate["candidate_hash"])},
        contract=_accepted_critic_contract(envelope),
    )
    reopened_after_reserve = ProjectDB(db.path)
    reopened_after_reserve.complete_analysis_critic_attempt(
        candidate_id,
        1,
        expected_intent_hash=str(attempt["intent_hash"]),
        expected_contract_hash=str(attempt["contract_hash"]),
        result_state="critic_accepted",
        outcome={"accepted": True},
        evidence=_accepted_critic_evidence(envelope),
        commit_envelope=envelope,
    )

    reopened_after_accept = ProjectDB(db.path)
    snapshot = reopened_after_accept.analysis_candidate_acceptance_envelope(candidate_id)
    durable_row = snapshot["commit_envelope"]["critic_rows"][0]
    assert durable_row["context_policy"] == (
        ANALYSIS_CONTEXT_POLICY_NARRATION_BEFORE_THOUGHT
    )
    assert durable_row["previous_text"] == V27_SEQ31_PREVIOUS_TEXT
    assert durable_row["next_text"] == ""
    segment = snapshot["commit_envelope"]["segments"][0]
    reopened_after_accept.update_analysis_batch_with_event(
        [
            {
                "segment_id": segment["segment_id"],
                "stable_id": segment["stable_id"],
                "text_sha256": segment["text_sha256"],
                "expected_status": "pending",
                "data": dict(segment["data"]),
            }
        ],
        low_confidence_threshold=0.65,
        event_level="info",
        event_code="ANALYSIS_DIRECTOR_CRITIC_ACCEPTED",
        event_message="V28 narration lead-in context accepted",
        event_details={"candidate_hash": str(candidate["candidate_hash"])},
        **ANALYSIS_MODEL_COMMIT,
        analysis_candidate_id=candidate_id,
        analysis_policy_fingerprint=ANALYSIS_POLICY_FINGERPRINT,
        analysis_group_fingerprint=ANALYSIS_GROUP_FINGERPRINT,
        analysis_context_hash=ANALYSIS_CONTEXT_HASH,
    )
    committed = {
        str(row["stable_id"]): row for row in reopened_after_accept.list_segments()
    }
    assert committed[V27_SEQ32_STABLE_ID]["status"] == "analyzed"
    assert committed[V27_SEQ32_STABLE_ID]["kind"] == "narration"
    assert committed[str(previous_row["stable_id"])]["status"] == "pending"
    assert committed[str(thought_row["stable_id"])]["status"] == "pending"


def test_v30_v29_seq38_context_kind_override_survives_reopen_and_commit(
    tmp_path: Path,
) -> None:
    db, source_rows, envelope = _v30_v29_seq38_narration_before_thought_db(
        tmp_path
    )
    previous_row, target_row, thought_row = source_rows
    clearance = _clean_host_clearance(envelope)
    host_clearance = clearance["host_affect_clearance"]
    assert [int(row["seq"]) for row in source_rows] == [37, 38, 39]
    assert [int(row["paragraph_index"]) for row in source_rows] == [32, 33, 33]
    assert target_row["stable_id"] == V29_SEQ38_STABLE_ID
    assert target_row["text_sha256"] == sha256_text(V29_SEQ38_NARRATION_TEXT)
    assert thought_row["stable_id"] == V29_SEQ39_STABLE_ID
    assert thought_row["text_sha256"] == sha256_text(V29_SEQ39_THOUGHT_TEXT)
    assert host_clearance["matched_rule_count"] == 0
    assert host_clearance["semantic_locks"] == []
    assert envelope["critic_rows"][0]["host_locked_fields"] == {
        "kind": "narration"
    }

    candidate = _allocate_analysis_candidate(
        db,
        [target_row],
        candidate=envelope,
        deterministic_issues=clearance,
    )
    candidate_id = int(candidate["id"])
    attempt = db.reserve_analysis_critic_attempt(
        candidate_id,
        expected_state="allocated",
        max_attempts=2,
        intent={"candidate_hash": str(candidate["candidate_hash"])},
        contract=_accepted_critic_contract(envelope),
    )
    evidence = _context_source_kind_override_evidence(envelope, thought_row)
    override = evidence["segments"][0]["host_source_kind_override"]
    assert override["rule"] == ANALYSIS_CONTEXT_SOURCE_KIND_RULE
    assert override["covered_field_deltas"] == ["kind:narration->thought"]
    assert override["unresolved_field_deltas"] == []
    assert override["related_stable_id"] == V29_SEQ39_STABLE_ID
    assert override["related_text_sha256"] == sha256_text(V29_SEQ39_THOUGHT_TEXT)
    assert evidence["segments"][0]["effective_accept"] is True

    reopened = ProjectDB(db.path)
    reopened.complete_analysis_critic_attempt(
        candidate_id,
        1,
        expected_intent_hash=str(attempt["intent_hash"]),
        expected_contract_hash=str(attempt["contract_hash"]),
        result_state="critic_accepted",
        outcome={"accepted": True, "context_source_kind_override": True},
        evidence=evidence,
        commit_envelope=envelope,
    )
    snapshot = ProjectDB(db.path).analysis_candidate_acceptance_envelope(candidate_id)
    assert snapshot["critic_evidence"]["segments"][0]["critic"]["kind"] == (
        "thought"
    )
    segment = snapshot["commit_envelope"]["segments"][0]
    ProjectDB(db.path).update_analysis_batch_with_event(
        [
            {
                "segment_id": segment["segment_id"],
                "stable_id": segment["stable_id"],
                "text_sha256": segment["text_sha256"],
                "expected_status": "pending",
                "data": dict(segment["data"]),
            }
        ],
        low_confidence_threshold=0.65,
        event_level="info",
        event_code="ANALYSIS_DIRECTOR_CRITIC_ACCEPTED",
        event_message="V30 seq38 source-kind override accepted",
        event_details={"candidate_hash": str(candidate["candidate_hash"])},
        **ANALYSIS_MODEL_COMMIT,
        analysis_candidate_id=candidate_id,
        analysis_policy_fingerprint=ANALYSIS_POLICY_FINGERPRINT,
        analysis_group_fingerprint=ANALYSIS_GROUP_FINGERPRINT,
        analysis_context_hash=ANALYSIS_CONTEXT_HASH,
    )
    committed = {str(row["stable_id"]): row for row in db.list_segments()}
    assert committed[V29_SEQ38_STABLE_ID]["status"] == "analyzed"
    assert committed[V29_SEQ38_STABLE_ID]["kind"] == "narration"
    assert committed[str(previous_row["stable_id"])]["status"] == "pending"
    assert committed[V29_SEQ39_STABLE_ID]["status"] == "pending"
    assert db.get_analysis_candidate(candidate_id)["state"] == "accepted"


def test_v30_seq38_context_kind_override_preserves_other_rejected_deltas(
    tmp_path: Path,
) -> None:
    db, source_rows, envelope = _v30_v29_seq38_narration_before_thought_db(
        tmp_path
    )
    target_row, thought_row = source_rows[1:]
    clearance = _clean_host_clearance(envelope)
    candidate = _allocate_analysis_candidate(
        db,
        [target_row],
        candidate=envelope,
        deterministic_issues=clearance,
    )
    candidate_id = int(candidate["id"])
    attempt = db.reserve_analysis_critic_attempt(
        candidate_id,
        expected_state="allocated",
        max_attempts=2,
        intent={"candidate_hash": str(candidate["candidate_hash"])},
        contract=_accepted_critic_contract(envelope),
    )
    evidence = _context_source_kind_override_evidence(
        envelope,
        thought_row,
        corrected_intensity=2,
        corrected_pace="fast",
    )
    item = evidence["segments"][0]
    assert item["host_source_kind_override"]["unresolved_field_deltas"] == [
        "intensity:1->2",
        "pace:normal->fast",
    ]
    assert item["effective_accept"] is False

    with pytest.raises(RuntimeError, match="exact delivery/confidence"):
        db.complete_analysis_critic_attempt(
            candidate_id,
            1,
            expected_intent_hash=str(attempt["intent_hash"]),
            expected_contract_hash=str(attempt["contract_hash"]),
            result_state="critic_accepted",
            outcome={"accepted": True},
            evidence=evidence,
            commit_envelope=envelope,
        )
    db.complete_analysis_critic_attempt(
        candidate_id,
        1,
        expected_intent_hash=str(attempt["intent_hash"]),
        expected_contract_hash=str(attempt["contract_hash"]),
        result_state="critic_rejected",
        outcome=_rejected_critic_outcome(evidence),
        evidence=evidence,
    )
    assert ProjectDB(db.path).get_analysis_candidate(candidate_id)["state"] == (
        "critic_rejected"
    )


def test_v30_context_kind_and_non_sleep_semantic_overrides_compose(
    tmp_path: Path,
) -> None:
    thought_text = "‘Mình phải hiểu chuyện gì vừa xảy ra.’"
    db, _source_rows = _analysis_batch_db(
        tmp_path,
        texts=(RECALLED_PERSISTENT_FEAR_TEXT, thought_text),
        kind_hints=("narration", "thought"),
    )
    with db.connect() as conn:
        conn.execute(
            "UPDATE segments SET paragraph_index=0 WHERE seq=1"
        )
    source_rows = [dict(row) for row in db.list_segments()]
    target_row, thought_row = source_rows
    envelope = _semantic_lock_envelope(
        [target_row],
        candidate_emotion="afraid",
    )
    critic_row = envelope["critic_rows"][0]
    critic_row["context_policy"] = ANALYSIS_CONTEXT_POLICY_NARRATION_BEFORE_THOUGHT
    critic_row["host_locked_fields"] = {"kind": "narration", "emotion": "afraid"}
    critic_row["next_text"] = ""
    clearance = _host_semantic_clearance(
        envelope,
        rule="narration_recalled_persistent_fear",
        cue_class="recalled_persistent_fear",
        allowed_emotions=["afraid"],
    )
    candidate = _allocate_analysis_candidate(
        db,
        [target_row],
        candidate=envelope,
        deterministic_issues=clearance,
    )
    attempt = db.reserve_analysis_critic_attempt(
        int(candidate["id"]),
        expected_state="allocated",
        max_attempts=2,
        intent={"candidate_hash": str(candidate["candidate_hash"])},
        contract=_accepted_critic_contract(envelope),
    )
    evidence = _context_source_kind_override_evidence(
        envelope,
        thought_row,
        corrected_emotion="neutral",
        semantic_clearance=clearance,
    )
    item = evidence["segments"][0]
    assert item["host_source_kind_override"]["rule"] == (
        ANALYSIS_CONTEXT_SOURCE_KIND_RULE
    )
    assert item["host_semantic_override"]["rule"] == (
        "narration_recalled_persistent_fear"
    )
    assert item["field_deltas"] == [
        "kind:narration->thought",
        "emotion:afraid->neutral",
    ]
    assert item["effective_accept"] is True

    db.complete_analysis_critic_attempt(
        int(candidate["id"]),
        1,
        expected_intent_hash=str(attempt["intent_hash"]),
        expected_contract_hash=str(attempt["contract_hash"]),
        result_state="critic_accepted",
        outcome={"accepted": True, "composed_host_overrides": True},
        evidence=evidence,
        commit_envelope=envelope,
    )
    snapshot = ProjectDB(db.path).analysis_candidate_acceptance_envelope(
        int(candidate["id"])
    )
    assert snapshot["commit_envelope"]["segments"][0]["data"]["kind"] == (
        "narration"
    )
    assert snapshot["commit_envelope"]["segments"][0]["data"]["emotion"] == (
        "afraid"
    )


@pytest.mark.parametrize(
    "mutation",
    ("missing", "forged_rule", "related_stable_id", "related_text_sha256", "partition"),
)
def test_v30_seq38_context_kind_override_rejects_forged_protocol(
    tmp_path: Path,
    mutation: str,
) -> None:
    db, source_rows, envelope = _v30_v29_seq38_narration_before_thought_db(
        tmp_path
    )
    target_row, thought_row = source_rows[1:]
    candidate = _allocate_analysis_candidate(
        db,
        [target_row],
        candidate=envelope,
        deterministic_issues=_clean_host_clearance(envelope),
    )
    attempt = db.reserve_analysis_critic_attempt(
        int(candidate["id"]),
        expected_state="allocated",
        max_attempts=2,
        intent={"candidate_hash": str(candidate["candidate_hash"])},
        contract=_accepted_critic_contract(envelope),
    )
    evidence = _context_source_kind_override_evidence(envelope, thought_row)
    item = evidence["segments"][0]
    override = item["host_source_kind_override"]
    if mutation == "missing":
        del item["host_source_kind_override"]
    elif mutation == "forged_rule":
        override["rule"] = "narration_sleep_paralysis_helplessness"
    elif mutation == "related_stable_id":
        override["related_stable_id"] = "c00001_s0000039_swapped"
    elif mutation == "related_text_sha256":
        override["related_text_sha256"] = "f" * 64
    else:
        override["covered_field_deltas"] = []

    with pytest.raises(RuntimeError, match="exact delivery/confidence"):
        db.complete_analysis_critic_attempt(
            int(candidate["id"]),
            1,
            expected_intent_hash=str(attempt["intent_hash"]),
            expected_contract_hash=str(attempt["contract_hash"]),
            result_state="critic_accepted",
            outcome={"accepted": True},
            evidence=evidence,
            commit_envelope=envelope,
        )


@pytest.mark.parametrize(
    ("column", "value", "expected_error"),
    (
        (
            "stable_id",
            "c00001_s0000039_changed",
            "exact delivery/confidence",
        ),
        ("text_sha256", "e" * 64, "related source text hash"),
        ("text", "‘Nội dung thought đã bị thay đổi.’", "related source text hash"),
    ),
)
def test_v30_context_override_revalidates_related_source_on_reopen_and_commit(
    tmp_path: Path,
    column: str,
    value: str,
    expected_error: str,
) -> None:
    db, source_rows, envelope = _v30_v29_seq38_narration_before_thought_db(
        tmp_path
    )
    target_row, thought_row = source_rows[1:]
    candidate = _allocate_analysis_candidate(
        db,
        [target_row],
        candidate=envelope,
        deterministic_issues=_clean_host_clearance(envelope),
    )
    candidate_id = int(candidate["id"])
    attempt = db.reserve_analysis_critic_attempt(
        candidate_id,
        expected_state="allocated",
        max_attempts=2,
        intent={"candidate_hash": str(candidate["candidate_hash"])},
        contract=_accepted_critic_contract(envelope),
    )
    db.complete_analysis_critic_attempt(
        candidate_id,
        1,
        expected_intent_hash=str(attempt["intent_hash"]),
        expected_contract_hash=str(attempt["contract_hash"]),
        result_state="critic_accepted",
        outcome={"accepted": True},
        evidence=_context_source_kind_override_evidence(envelope, thought_row),
        commit_envelope=envelope,
    )
    with db.connect() as conn:
        conn.execute(
            f"UPDATE segments SET {column}=? WHERE id=?",
            (value, int(thought_row["id"])),
        )

    reopened = ProjectDB(db.path)
    with pytest.raises(RuntimeError, match=expected_error):
        reopened.analysis_candidate_acceptance_envelope(candidate_id)
    target_segment = envelope["segments"][0]
    with pytest.raises(RuntimeError, match=expected_error):
        reopened.update_analysis_batch_with_event(
            [
                {
                    "segment_id": target_segment["segment_id"],
                    "stable_id": target_segment["stable_id"],
                    "text_sha256": target_segment["text_sha256"],
                    "expected_status": "pending",
                    "data": dict(target_segment["data"]),
                }
            ],
            low_confidence_threshold=0.65,
            event_level="info",
            event_code="ANALYSIS_DIRECTOR_CRITIC_ACCEPTED",
            event_message="must roll back",
            event_details={"candidate_hash": str(candidate["candidate_hash"])},
            **ANALYSIS_MODEL_COMMIT,
            analysis_candidate_id=candidate_id,
            analysis_policy_fingerprint=ANALYSIS_POLICY_FINGERPRINT,
            analysis_group_fingerprint=ANALYSIS_GROUP_FINGERPRINT,
            analysis_context_hash=ANALYSIS_CONTEXT_HASH,
        )
    assert reopened.get_segment(int(target_row["id"]))["status"] == "pending"


def test_v30_context_override_rejects_rehashed_related_provenance_tamper(
    tmp_path: Path,
) -> None:
    db, source_rows, envelope = _v30_v29_seq38_narration_before_thought_db(
        tmp_path
    )
    target_row, thought_row = source_rows[1:]
    candidate = _allocate_analysis_candidate(
        db,
        [target_row],
        candidate=envelope,
        deterministic_issues=_clean_host_clearance(envelope),
    )
    candidate_id = int(candidate["id"])
    attempt = db.reserve_analysis_critic_attempt(
        candidate_id,
        expected_state="allocated",
        max_attempts=2,
        intent={"candidate_hash": str(candidate["candidate_hash"])},
        contract=_accepted_critic_contract(envelope),
    )
    db.complete_analysis_critic_attempt(
        candidate_id,
        1,
        expected_intent_hash=str(attempt["intent_hash"]),
        expected_contract_hash=str(attempt["contract_hash"]),
        result_state="critic_accepted",
        outcome={"accepted": True},
        evidence=_context_source_kind_override_evidence(envelope, thought_row),
        commit_envelope=envelope,
    )
    with db.connect() as conn:
        stored_attempt = conn.execute(
            "SELECT * FROM analysis_critic_attempts "
            "WHERE analysis_candidate_id=? AND attempt_number=1",
            (candidate_id,),
        ).fetchone()
        stored_candidate = conn.execute(
            "SELECT * FROM analysis_candidates WHERE id=?",
            (candidate_id,),
        ).fetchone()
        tampered = json.loads(str(stored_attempt["evidence_json"]))
        tampered["segments"][0]["host_source_kind_override"][
            "related_text_sha256"
        ] = "f" * 64
        evidence_json, evidence_hash = db._canonical_analysis_json(
            tampered,
            "tampered context source-kind critic evidence",
        )
        _completion_json, completion_hash = db._canonical_analysis_json(
            {
                "commit_envelope_hash": stored_candidate["commit_envelope_hash"],
                "contract_hash": stored_attempt["contract_hash"],
                "evidence_hash": evidence_hash,
                "intent_hash": stored_attempt["intent_hash"],
                "outcome_hash": stored_attempt["outcome_hash"],
            },
            "tampered context source-kind critic completion",
        )
        conn.execute(
            "UPDATE analysis_critic_attempts SET evidence_json=?,evidence_hash=?,"
            "completion_hash=? WHERE analysis_candidate_id=? AND attempt_number=1",
            (evidence_json, evidence_hash, completion_hash, candidate_id),
        )

    with pytest.raises(RuntimeError, match="exact delivery/confidence"):
        ProjectDB(db.path).analysis_candidate_acceptance_envelope(candidate_id)


@pytest.mark.parametrize(
    ("field", "value", "error"),
    (
        ("context_policy", "adjacent_context", "source-ledger-bound"),
        ("previous_text", "forged predecessor", "source-ledger-bound"),
        ("next_text", V27_SEQ33_THOUGHT_TEXT, "source IDs/hashes/delivery"),
    ),
)
def test_v28_v27_seq32_context_rejects_candidate_tamper(
    tmp_path: Path,
    field: str,
    value: str,
    error: str,
) -> None:
    db, source_rows, envelope = _v28_v27_narration_before_thought_db(tmp_path)
    envelope["critic_rows"][0][field] = value
    with pytest.raises((ValueError, RuntimeError), match=error):
        _allocate_analysis_candidate(
            db,
            [source_rows[1]],
            candidate=envelope,
        )
    assert db.has_analysis_candidates() is False


@pytest.mark.parametrize(
    ("column", "value"),
    (
        ("paragraph_index", 31),
        ("kind_hint", "dialogue"),
        ("seq", 99),
    ),
)
def test_v28_v27_seq32_context_revalidates_next_source_metadata_on_reopen(
    tmp_path: Path,
    column: str,
    value: object,
) -> None:
    db, source_rows, envelope = _v28_v27_narration_before_thought_db(tmp_path)
    candidate = _allocate_analysis_candidate(
        db,
        [source_rows[1]],
        candidate=envelope,
    )
    db.reserve_analysis_critic_attempt(
        int(candidate["id"]),
        expected_state="allocated",
        max_attempts=2,
        intent={"candidate_hash": str(candidate["candidate_hash"])},
        contract=_accepted_critic_contract(envelope),
    )
    with db.connect() as conn:
        conn.execute(
            f"UPDATE segments SET {column}=? WHERE text_sha256=?",
            (value, sha256_text(V27_SEQ33_THOUGHT_TEXT)),
        )

    with pytest.raises(RuntimeError, match="source-ledger-bound"):
        ProjectDB(db.path).find_resumable_analysis_candidate(
            policy_fingerprint=ANALYSIS_POLICY_FINGERPRINT,
            model_name=ANALYSIS_MODEL_NAME,
            model_digest=ANALYSIS_MODEL_DIGEST,
            group_fingerprint=ANALYSIS_GROUP_FINGERPRINT,
            context_hash=ANALYSIS_CONTEXT_HASH,
        )


@pytest.mark.parametrize(
    ("next_kind", "next_paragraph"),
    (("thought", 32), ("dialogue", 31)),
)
def test_v28_narration_control_keeps_adjacent_context_policy(
    tmp_path: Path,
    next_kind: str,
    next_paragraph: int,
) -> None:
    db, source_rows = _analysis_batch_db(
        tmp_path,
        texts=("Lời dẫn trung tính.", "Hàng kế tiếp."),
        kind_hints=("narration", next_kind),
    )
    with db.connect() as conn:
        conn.execute(
            "UPDATE segments SET paragraph_index=CASE seq WHEN 0 THEN 30 ELSE ? END",
            (next_paragraph,),
        )
    source_rows = [dict(row) for row in db.list_segments()]
    envelope = _analysis_acceptance_envelope([source_rows[0]])
    envelope["critic_rows"][0]["context_policy"] = "adjacent_context"
    candidate = _allocate_analysis_candidate(
        db,
        [source_rows[0]],
        candidate=envelope,
    )
    assert candidate["state"] == "allocated"


def test_v21_thought_context_survives_allocate_reopen_and_commit(
    tmp_path: Path,
) -> None:
    assert ANALYSIS_CONTEXT_POLICY_PREVIOUS_ONLY == "previous_context_only"
    assert sha256_text(V21_SEQ13_THOUGHT_TEXT) == V21_SEQ13_TEXT_SHA256
    db, source_rows, envelope = _v21_thought_context_db(tmp_path)
    previous_row, thought_row = source_rows
    assert int(previous_row["seq"]) == 12
    assert int(thought_row["seq"]) == 13
    assert str(thought_row["stable_id"]) == V21_SEQ13_STABLE_ID
    candidate = _allocate_analysis_candidate(
        db,
        [thought_row],
        candidate=envelope,
    )
    candidate_id = int(candidate["id"])
    critic_contract = _accepted_critic_contract(envelope)
    attempt = db.reserve_analysis_critic_attempt(
        candidate_id,
        expected_state="allocated",
        max_attempts=2,
        intent={"candidate_hash": str(candidate["candidate_hash"])},
        contract=critic_contract,
    )
    db.complete_analysis_critic_attempt(
        candidate_id,
        1,
        expected_intent_hash=str(attempt["intent_hash"]),
        expected_contract_hash=str(attempt["contract_hash"]),
        result_state="critic_accepted",
        outcome={"accepted": True},
        evidence=_accepted_critic_evidence(envelope),
        commit_envelope=envelope,
    )

    reopened = ProjectDB(db.path)
    snapshot = reopened.analysis_candidate_acceptance_envelope(candidate_id)
    critic_row = snapshot["commit_envelope"]["critic_rows"][0]
    assert critic_row["source_role"] == "content"
    assert critic_row["context_policy"] == ANALYSIS_CONTEXT_POLICY_PREVIOUS_ONLY
    assert critic_row["previous_text"] == V21_SEQ12_PREVIOUS_TEXT[-500:]
    assert critic_row["next_text"] == ""
    batch = [
        {
            "segment_id": segment["segment_id"],
            "stable_id": segment["stable_id"],
            "text_sha256": segment["text_sha256"],
            "expected_status": "pending",
            "data": dict(segment["data"]),
        }
        for segment in snapshot["commit_envelope"]["segments"]
    ]
    reopened.update_analysis_batch_with_event(
        batch,
        low_confidence_threshold=0.65,
        event_level="info",
        event_code="ANALYSIS_DIRECTOR_CRITIC_ACCEPTED",
        event_message="V21 thought context accepted",
        event_details={"candidate_hash": str(candidate["candidate_hash"])},
        **ANALYSIS_MODEL_COMMIT,
        analysis_candidate_id=candidate_id,
        analysis_policy_fingerprint=ANALYSIS_POLICY_FINGERPRINT,
        analysis_group_fingerprint=ANALYSIS_GROUP_FINGERPRINT,
        analysis_context_hash=ANALYSIS_CONTEXT_HASH,
    )

    committed = {
        str(row["stable_id"]): row for row in reopened.list_segments()
    }
    assert committed[V21_SEQ12_STABLE_ID]["status"] == "pending"
    assert committed[V21_SEQ13_STABLE_ID]["status"] == "analyzed"
    assert committed[V21_SEQ13_STABLE_ID]["emotion"] == "neutral"
    assert reopened.get_analysis_candidate(candidate_id)["state"] == "accepted"


@pytest.mark.parametrize(
    "mutation",
    (
        "omit_previous",
        "omit_policy",
        "forged_previous",
        "forged_next",
        "forged_policy",
    ),
)
def test_v21_thought_context_rejects_omitted_or_forged_allocation(
    tmp_path: Path,
    mutation: str,
) -> None:
    db, source_rows, envelope = _v21_thought_context_db(tmp_path)
    critic_row = envelope["critic_rows"][0]
    if mutation == "omit_previous":
        del critic_row["previous_text"]
    elif mutation == "omit_policy":
        del critic_row["context_policy"]
    elif mutation == "forged_previous":
        critic_row["previous_text"] = "forged previous source"
    elif mutation == "forged_next":
        critic_row["next_text"] = STUNNED_BLANK_MIND_TEXT
    else:
        critic_row["context_policy"] = "adjacent_context"

    with pytest.raises(
        (ValueError, RuntimeError),
        match="source IDs|source-ledger-bound",
    ):
        _allocate_analysis_candidate(
            db,
            [source_rows[1]],
            candidate=envelope,
        )


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("previous_text", "forged durable previous source"),
        ("next_text", STUNNED_BLANK_MIND_TEXT),
        ("context_policy", "adjacent_context"),
    ),
)
def test_v21_thought_context_revalidates_durable_candidate_on_reopen(
    tmp_path: Path,
    field: str,
    value: str,
) -> None:
    db, source_rows, envelope = _v21_thought_context_db(tmp_path)
    candidate = _allocate_analysis_candidate(
        db,
        [source_rows[1]],
        candidate=envelope,
    )
    tampered = copy.deepcopy(envelope)
    tampered["critic_rows"][0][field] = value
    tampered_json = json.dumps(
        tampered,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    with db.connect() as conn:
        conn.execute(
            "UPDATE analysis_candidates SET candidate_json=?,candidate_hash=?,"
            "envelope_hash=? WHERE id=?",
            (
                tampered_json,
                _canonical_hash(tampered["critic_rows"]),
                sha256_text(tampered_json),
                int(candidate["id"]),
            ),
        )

    with pytest.raises(
        (ValueError, RuntimeError),
        match="source IDs|source-ledger-bound",
    ):
        ProjectDB(db.path).get_analysis_candidate(int(candidate["id"]))


def test_thought_context_at_chapter_start_rejects_cross_chapter_predecessor(
    tmp_path: Path,
) -> None:
    db, first_chapter_rows = _analysis_batch_db(
        tmp_path,
        texts=(V21_SEQ12_PREVIOUS_TEXT,),
    )
    chapter_id = db.ensure_chapters(
        [
            {
                "chapter_index": 2,
                "title": "Two",
                "input_path": tmp_path / "two.txt",
                "input_sha256": "source-two",
                "input_size": 1,
                "output_mp3": tmp_path / "two.mp3",
            }
        ]
    )[0]
    db.replace_chapter_segments(
        chapter_id,
        [
            {
                "stable_id": V21_SEQ13_STABLE_ID,
                "seq": 0,
                "text": V21_SEQ13_THOUGHT_TEXT,
                "text_sha256": V21_SEQ13_TEXT_SHA256,
                "kind_hint": "thought",
            }
        ],
    )
    thought_row = dict(db.list_segments()[-1])
    envelope = _thought_acceptance_envelope([thought_row])
    candidate = _allocate_analysis_candidate(
        db,
        [thought_row],
        candidate=envelope,
    )
    assert candidate["state"] == "allocated"
    assert envelope["critic_rows"][0]["previous_text"] == ""

    forged = copy.deepcopy(envelope)
    forged["critic_rows"][0]["previous_text"] = str(
        first_chapter_rows[0]["text"]
    )[-500:]
    with pytest.raises(RuntimeError, match="source-ledger-bound"):
        _allocate_analysis_candidate(
            db,
            [thought_row],
            context_hash="cross-chapter-context",
            candidate=forged,
        )


def test_v21_thought_context_replays_predecessor_again_before_commit(
    tmp_path: Path,
) -> None:
    db, source_rows, envelope = _v21_thought_context_db(tmp_path)
    candidate = _allocate_analysis_candidate(
        db,
        [source_rows[1]],
        candidate=envelope,
    )
    candidate_id = int(candidate["id"])
    attempt = db.reserve_analysis_critic_attempt(
        candidate_id,
        expected_state="allocated",
        max_attempts=2,
        intent={"candidate_hash": str(candidate["candidate_hash"])},
        contract=_accepted_critic_contract(envelope),
    )
    db.complete_analysis_critic_attempt(
        candidate_id,
        1,
        expected_intent_hash=str(attempt["intent_hash"]),
        expected_contract_hash=str(attempt["contract_hash"]),
        result_state="critic_accepted",
        outcome={"accepted": True},
        evidence=_accepted_critic_evidence(envelope),
        commit_envelope=envelope,
    )
    forged_previous = "forged predecessor after critic acceptance"
    with db.connect() as conn:
        conn.execute(
            "UPDATE segments SET text=?,text_sha256=? WHERE stable_id=?",
            (
                forged_previous,
                sha256_text(forged_previous),
                V21_SEQ12_STABLE_ID,
            ),
        )
    segment = envelope["segments"][0]
    batch = [
        {
            "segment_id": segment["segment_id"],
            "stable_id": segment["stable_id"],
            "text_sha256": segment["text_sha256"],
            "expected_status": "pending",
            "data": dict(segment["data"]),
        }
    ]

    with pytest.raises(RuntimeError, match="source-ledger-bound"):
        db.update_analysis_batch_with_event(
            batch,
            low_confidence_threshold=0.65,
            event_level="info",
            event_code="ANALYSIS_DIRECTOR_CRITIC_ACCEPTED",
            event_message="must roll back",
            event_details={"candidate_hash": str(candidate["candidate_hash"])},
            **ANALYSIS_MODEL_COMMIT,
            analysis_candidate_id=candidate_id,
            analysis_policy_fingerprint=ANALYSIS_POLICY_FINGERPRINT,
            analysis_group_fingerprint=ANALYSIS_GROUP_FINGERPRINT,
            analysis_context_hash=ANALYSIS_CONTEXT_HASH,
        )

    thought = next(
        row
        for row in db.list_segments()
        if str(row["stable_id"]) == V21_SEQ13_STABLE_ID
    )
    assert thought["status"] == "pending"
    with db.connect() as conn:
        stored_state = conn.execute(
            "SELECT state FROM analysis_candidates WHERE id=?",
            (candidate_id,),
        ).fetchone()["state"]
    assert stored_state == "critic_accepted"


def test_analysis_candidate_accepts_source_bound_chapter_heading_override(
    tmp_path: Path,
) -> None:
    db, source_rows = _analysis_batch_db(
        tmp_path,
        texts=("Chương 01 - Giàn hỏa thiêu rực cháy", "Khói dày ngùn ngụt."),
    )
    envelope = _chapter_heading_envelope(source_rows)
    clearance = _chapter_heading_clearance(envelope)
    candidate = _allocate_analysis_candidate(
        db,
        source_rows,
        candidate=envelope,
        deterministic_issues=clearance,
    )
    attempt = db.reserve_analysis_critic_attempt(
        int(candidate["id"]),
        expected_state="allocated",
        max_attempts=2,
        intent={"candidate_hash": str(candidate["candidate_hash"])},
        contract=_accepted_critic_contract(envelope),
    )
    evidence = _heading_override_evidence(envelope)

    completed = db.complete_analysis_critic_attempt(
        int(candidate["id"]),
        1,
        expected_intent_hash=str(attempt["intent_hash"]),
        expected_contract_hash=str(attempt["contract_hash"]),
        result_state="critic_accepted",
        outcome={"accepted": True, "host_structural_override": True},
        evidence=evidence,
        commit_envelope=envelope,
    )

    assert completed["state"] == "completed"
    snapshot = ProjectDB(db.path).analysis_candidate_acceptance_envelope(
        int(candidate["id"])
    )
    stored_evidence = snapshot["critic_evidence"]
    assert stored_evidence["segments"][0]["critic"]["emotion"] == "afraid"
    assert stored_evidence["segments"][0]["host_structural_override"][
        "locked_fields"
    ] == ANALYSIS_CHAPTER_HEADING_DELIVERY
    assert snapshot["commit_envelope"]["segments"][0]["data"]["emotion"] == "neutral"


def test_v39_heading_override_rejects_unbound_local_speaker_evidence(
    tmp_path: Path,
) -> None:
    db, source_rows = _analysis_batch_db(
        tmp_path,
        texts=("Chương 01 - Giàn hỏa thiêu rực cháy", "Khói dày ngùn ngụt."),
    )
    envelope = _chapter_heading_envelope(source_rows)
    clearance = _chapter_heading_clearance(envelope)
    candidate = _allocate_analysis_candidate(
        db,
        source_rows,
        candidate=envelope,
        deterministic_issues=clearance,
    )
    attempt = db.reserve_analysis_critic_attempt(
        int(candidate["id"]),
        expected_state="allocated",
        max_attempts=2,
        intent={"candidate_hash": str(candidate["candidate_hash"])},
        contract=_accepted_critic_contract(envelope),
    )
    evidence = _heading_override_evidence(envelope)
    item = evidence["segments"][0]
    forged_speaker = "NPC_LOCAL::c00100::forged::phụ nữ áo đen"
    item["critic"]["speaker"] = forged_speaker
    item["field_deltas"] = [
        f"speaker:NARRATOR->{forged_speaker}",
        *item["field_deltas"],
    ]
    item["host_structural_override"]["raw_field_deltas"] = list(
        item["field_deltas"]
    )

    with pytest.raises(RuntimeError, match="exact delivery/confidence"):
        db.complete_analysis_critic_attempt(
            int(candidate["id"]),
            1,
            expected_intent_hash=str(attempt["intent_hash"]),
            expected_contract_hash=str(attempt["contract_hash"]),
            result_state="critic_accepted",
            outcome={"accepted": True, "host_structural_override": True},
            evidence=evidence,
            commit_envelope=envelope,
        )


def test_v24_heading_critic_confidence_preserves_lock_through_reopen_and_commit(
    tmp_path: Path,
) -> None:
    assert ANALYSIS_HOST_STRUCTURAL_POLICY_VERSION == "chapter_heading_lock_v2"
    assert ANALYSIS_CHAPTER_HEADING_CONFIDENCE == 0.95
    assert ANALYSIS_DIRECTOR_CRITIC_POLICY_VERSION == "second_pass_v18"
    db, source_rows = _analysis_batch_db(
        tmp_path,
        texts=("Chương 01 - Giàn hỏa thiêu rực cháy", "Khói dày ngùn ngụt."),
    )
    envelope = _chapter_heading_envelope(source_rows)
    clearance = _chapter_heading_clearance(
        envelope,
        generator_confidence=1e-16,
    )
    candidate = _allocate_analysis_candidate(
        db,
        source_rows,
        candidate=envelope,
        deterministic_issues=clearance,
    )
    candidate_id = int(candidate["id"])
    durable_candidate = json.loads(str(candidate["candidate_json"]))
    durable_clearance = json.loads(str(candidate["deterministic_issue_json"]))
    heading_lock = durable_clearance["host_affect_clearance"]["structural_locks"][0]
    assert durable_candidate["segments"][0]["data"]["confidence"] == 0.95
    assert heading_lock["generator_confidence"] == 1e-16
    assert heading_lock["locked_confidence"] == 0.95

    attempt = db.reserve_analysis_critic_attempt(
        candidate_id,
        expected_state="allocated",
        max_attempts=2,
        intent={"candidate_hash": str(candidate["candidate_hash"])},
        contract=_accepted_critic_contract(envelope),
    )
    reopened_after_reserve = ProjectDB(db.path)
    evidence = _accepted_critic_evidence(envelope)
    heading_evidence = evidence["segments"][0]
    heading_evidence["critic"]["confidence"] = 0.85
    assert heading_evidence["derived_confidence"] == 0.95

    forged_commit_envelope = copy.deepcopy(envelope)
    forged_commit_envelope["segments"][0]["data"]["confidence"] = 0.85
    with pytest.raises(ValueError, match="heading candidate confidence"):
        reopened_after_reserve.complete_analysis_critic_attempt(
            candidate_id,
            1,
            expected_intent_hash=str(attempt["intent_hash"]),
            expected_contract_hash=str(attempt["contract_hash"]),
            result_state="critic_accepted",
            outcome={"accepted": True},
            evidence=evidence,
            commit_envelope=forged_commit_envelope,
        )

    forged_evidence = copy.deepcopy(evidence)
    forged_evidence["segments"][0]["derived_confidence"] = 0.85
    with pytest.raises(RuntimeError, match="exact delivery/confidence"):
        reopened_after_reserve.complete_analysis_critic_attempt(
            candidate_id,
            1,
            expected_intent_hash=str(attempt["intent_hash"]),
            expected_contract_hash=str(attempt["contract_hash"]),
            result_state="critic_accepted",
            outcome={"accepted": True},
            evidence=forged_evidence,
            commit_envelope=envelope,
        )

    reopened_after_reserve.complete_analysis_critic_attempt(
        candidate_id,
        1,
        expected_intent_hash=str(attempt["intent_hash"]),
        expected_contract_hash=str(attempt["contract_hash"]),
        result_state="critic_accepted",
        outcome={"accepted": True},
        evidence=evidence,
        commit_envelope=envelope,
    )

    reopened_after_accept = ProjectDB(db.path)
    snapshot = reopened_after_accept.analysis_candidate_acceptance_envelope(candidate_id)
    assert snapshot["candidate"]["segments"][0]["data"]["confidence"] == 0.95
    assert snapshot["commit_envelope"]["segments"][0]["data"]["confidence"] == 0.95
    stored_heading_evidence = snapshot["critic_evidence"]["segments"][0]
    assert stored_heading_evidence["critic"]["confidence"] == 0.85
    assert stored_heading_evidence["derived_confidence"] == 0.95
    batch = [
        {
            "segment_id": segment["segment_id"],
            "stable_id": segment["stable_id"],
            "text_sha256": segment["text_sha256"],
            "expected_status": "pending",
            "data": dict(segment["data"]),
        }
        for segment in snapshot["commit_envelope"]["segments"]
    ]
    reopened_after_accept.update_analysis_batch_with_event(
        batch,
        low_confidence_threshold=0.65,
        event_level="info",
        event_code="ANALYSIS_DIRECTOR_CRITIC_ACCEPTED",
        event_message="accepted",
        event_details={"candidate_hash": str(candidate["candidate_hash"])},
        **ANALYSIS_MODEL_COMMIT,
        analysis_candidate_id=candidate_id,
        analysis_policy_fingerprint=ANALYSIS_POLICY_FINGERPRINT,
        analysis_group_fingerprint=ANALYSIS_GROUP_FINGERPRINT,
        analysis_context_hash=ANALYSIS_CONTEXT_HASH,
    )

    committed_heading = ProjectDB(db.path).list_segments()[0]
    assert committed_heading["confidence"] == 0.95
    assert committed_heading["status"] == "analyzed"
    assert ProjectDB(db.path).get_analysis_candidate(candidate_id)["state"] == "accepted"


@pytest.mark.parametrize(
    ("tamper_field", "tamper_value", "error"),
    (
        ("locked_confidence", 0.94, "structural clearance is not source-bound"),
        ("generator_confidence", -0.01, "structural clearance is not source-bound"),
        ("generator_confidence", 1.01, "structural clearance is not source-bound"),
        ("evidence_quote", "forged source", "structural clearance is not source-bound"),
    ),
)
def test_v22_heading_rejects_forged_structural_confidence_audit(
    tmp_path: Path,
    tamper_field: str,
    tamper_value: object,
    error: str,
) -> None:
    db, source_rows = _analysis_batch_db(
        tmp_path,
        texts=("Chương 01 - Khởi đầu", "Nội dung."),
    )
    envelope = _chapter_heading_envelope(source_rows)
    clearance = _chapter_heading_clearance(envelope)
    clearance["host_affect_clearance"]["structural_locks"][0][tamper_field] = (
        tamper_value
    )

    with pytest.raises(RuntimeError, match=error):
        _allocate_analysis_candidate(
            db,
            source_rows,
            candidate=envelope,
            deterministic_issues=clearance,
        )


@pytest.mark.parametrize("missing_field", ("generator_confidence", "locked_confidence"))
def test_v22_heading_rejects_missing_structural_confidence_fields(
    tmp_path: Path,
    missing_field: str,
) -> None:
    db, source_rows = _analysis_batch_db(
        tmp_path,
        texts=("Chương 01 - Khởi đầu", "Nội dung."),
    )
    envelope = _chapter_heading_envelope(source_rows)
    clearance = _chapter_heading_clearance(envelope)
    del clearance["host_affect_clearance"]["structural_locks"][0][missing_field]

    with pytest.raises(RuntimeError, match="structural clearance lock has invalid schema"):
        _allocate_analysis_candidate(
            db,
            source_rows,
            candidate=envelope,
            deterministic_issues=clearance,
        )


def test_v22_heading_rejects_incomplete_generator_delivery_audit(
    tmp_path: Path,
) -> None:
    db, source_rows = _analysis_batch_db(
        tmp_path,
        texts=("Chương 01 - Khởi đầu", "Nội dung."),
    )
    envelope = _chapter_heading_envelope(source_rows)
    clearance = _chapter_heading_clearance(envelope)
    del clearance["host_affect_clearance"]["structural_locks"][0][
        "generator_fields"
    ]["speaker"]

    with pytest.raises(RuntimeError, match="structural clearance is not source-bound"):
        _allocate_analysis_candidate(
            db,
            source_rows,
            candidate=envelope,
            deterministic_issues=clearance,
        )


def test_v22_heading_rejects_candidate_confidence_below_fixed_lock(
    tmp_path: Path,
) -> None:
    db, source_rows = _analysis_batch_db(
        tmp_path,
        texts=("Chương 01 - Khởi đầu", "Nội dung."),
    )
    envelope = _chapter_heading_envelope(source_rows)
    envelope["segments"][0]["data"]["confidence"] = 0.94

    with pytest.raises(ValueError, match="heading candidate confidence"):
        _allocate_analysis_candidate(
            db,
            source_rows,
            candidate=envelope,
            deterministic_issues=_chapter_heading_clearance(envelope),
        )


def test_v22_heading_revalidates_locked_confidence_on_reopen(
    tmp_path: Path,
) -> None:
    db, source_rows = _analysis_batch_db(
        tmp_path,
        texts=("Chương 01 - Khởi đầu", "Nội dung."),
    )
    envelope = _chapter_heading_envelope(source_rows)
    candidate = _allocate_analysis_candidate(
        db,
        source_rows,
        candidate=envelope,
        deterministic_issues=_chapter_heading_clearance(envelope),
    )
    tampered = json.loads(str(candidate["deterministic_issue_json"]))
    tampered["host_affect_clearance"]["structural_locks"][0][
        "locked_confidence"
    ] = 0.94
    tampered_json = json.dumps(
        tampered,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    with db.connect() as conn:
        conn.execute(
            "UPDATE analysis_candidates SET deterministic_issue_json=?,"
            "deterministic_issue_hash=? WHERE id=?",
            (tampered_json, sha256_text(tampered_json), int(candidate["id"])),
        )

    with pytest.raises(RuntimeError, match="structural clearance is not source-bound"):
        ProjectDB(db.path).get_analysis_candidate(int(candidate["id"]))


def test_analysis_candidate_rejects_heading_role_on_first_prose_segment(
    tmp_path: Path,
) -> None:
    db, source_rows = _analysis_batch_db(
        tmp_path,
        texts=("Khói dày phủ kín căn phòng.", "Hạ Phong bật tỉnh."),
    )
    envelope = _chapter_heading_envelope(source_rows)
    clearance = _chapter_heading_clearance(envelope)

    with pytest.raises(RuntimeError, match="not source-metadata-bound"):
        _allocate_analysis_candidate(
            db,
            source_rows,
            candidate=envelope,
            deterministic_issues=clearance,
        )


def test_analysis_candidate_rejects_forged_structural_override_on_content(
    tmp_path: Path,
) -> None:
    db, source_rows = _analysis_batch_db(tmp_path)
    envelope = _analysis_acceptance_envelope(source_rows)
    forged_clearance = _chapter_heading_clearance(envelope)
    with pytest.raises(
        RuntimeError,
        match="structural clearance differs from chapter-heading rows",
    ):
        _allocate_analysis_candidate(
            db,
            source_rows,
            candidate=envelope,
            deterministic_issues=forged_clearance,
        )


def test_analysis_candidate_rejects_tampered_heading_structural_clearance(
    tmp_path: Path,
) -> None:
    db, source_rows = _analysis_batch_db(
        tmp_path,
        texts=("Chương 01 - Giàn hỏa thiêu rực cháy", "Khói dày ngùn ngụt."),
    )
    envelope = _chapter_heading_envelope(source_rows)
    clearance = _chapter_heading_clearance(envelope)
    clearance["host_affect_clearance"]["structural_locks"][0][
        "text_sha256"
    ] = "f" * 64
    with pytest.raises(RuntimeError, match="structural clearance is not source-bound"):
        _allocate_analysis_candidate(
            db,
            source_rows,
            candidate=envelope,
            deterministic_issues=clearance,
        )


def test_analysis_candidate_rejects_mandatory_heading_lock_when_omitted(
    tmp_path: Path,
) -> None:
    db, source_rows = _analysis_batch_db(
        tmp_path,
        texts=("Chapter 01 - Beginning", "Ordinary prose follows."),
    )
    envelope = _analysis_acceptance_envelope(source_rows)

    with pytest.raises(RuntimeError, match="source-derived chapter headings"):
        _allocate_analysis_candidate(
            db,
            source_rows,
            candidate=envelope,
        )


def test_direct_narration_affect_source_authority_accepts_exact_smoke_rows() -> None:
    assert ANALYSIS_HOST_AFFECT_POLICY_VERSION == "host_affect_v10"
    assert ANALYSIS_HOST_SEMANTIC_POLICY_VERSION == "host_semantic_lock_v6"
    assert analysis_source_has_recalled_persistent_fear(
        RECALLED_PERSISTENT_FEAR_TEXT
    )
    assert analysis_source_has_stunned_blank_mind(STUNNED_BLANK_MIND_TEXT)
    assert not analysis_source_has_stunned_blank_mind(
        RECALLED_PERSISTENT_FEAR_TEXT
    )
    assert not analysis_source_has_recalled_persistent_fear(
        STUNNED_BLANK_MIND_TEXT
    )
    assert analysis_source_has_recalled_persistent_fear(
        "Hạ Phong đến giờ nghĩ lại vẫn tim đập chân run."
    )
    assert analysis_source_has_recalled_persistent_fear(
        "Đèn đã tắt. Hạ Phong nghĩ lại vẫn tim đập chân run."
    )
    assert analysis_source_has_recalled_persistent_fear(
        "Giấc mơ ấy chân thực đến dị thường, làm cho Hạ Phong nghĩ lại "
        "vẫn tim đập chân run."
    )
    assert analysis_source_has_stunned_blank_mind(
        "Cậu đực mặt ra, đầu óc một mảng trắng xóa."
    )
    assert analysis_source_has_stunned_blank_mind(
        "Đèn đã tắt. Cậu đực mặt ra, đầu óc một mảng trắng xóa."
    )
    assert analysis_source_has_stunned_blank_mind(
        "Giống như bị cây chùy nặng đập vào đầu, cậu đực mặt ra, "
        "đầu óc một mảng trắng xóa."
    )


def test_sleep_paralysis_source_authority_accepts_exact_v28_seq10() -> None:
    assert sha256_text(V28_SEQ10_SLEEP_PARALYSIS_TEXT) == (
        V28_SEQ10_SLEEP_PARALYSIS_TEXT_SHA256
    )
    assert analysis_source_has_sleep_paralysis_helplessness(
        V28_SEQ10_SLEEP_PARALYSIS_TEXT
    )
    assert analysis_source_has_sleep_paralysis_helplessness(
        "Cậu bị bóng đè, cậu biết rõ mình đang nằm mơ, "
        "muốn thoát ra nhưng không thể điều khiển bản thân."
    )
    assert analysis_source_has_sleep_paralysis_helplessness(
        "Giống như cậu bị bóng đè trước đây, cậu biết rõ mình đang nằm mơ, "
        "muốn thoát ra nhưng không thể điều khiển bản thân."
    )


@pytest.mark.parametrize(
    "text",
    (
        (
            "“Giống như mấy lần bị bóng đè trước đây, cậu biết rõ mình đang nằm "
            "mơ, muốn thoát ra nhưng không thể điều khiển bản thân.”"
        ),
        (
            "Giống như mấy lần bị bóng đè trước đây, cậu biết rõ mình đang nằm "
            "mơ, muốn thoát ra nhưng không thể điều khiển bản thân?"
        ),
        (
            "Nếu bị bóng đè, cậu biết rõ mình đang nằm mơ, muốn thoát ra nhưng "
            "không thể điều khiển bản thân."
        ),
        (
            "Cụm từ bóng đè mô tả việc cậu biết rõ mình đang nằm mơ, muốn thoát "
            "ra nhưng không thể điều khiển bản thân."
        ),
        (
            "Giống như mấy lần bị bóng đè trước đây, cậu biết rõ mình đang nằm "
            "mơ, muốn thoát ra nhưng không thể điều khiển bản thân. Cuối cùng "
            "cậu đã tỉnh dậy."
        ),
        (
            "Giống như mấy lần bị bóng đè trước đây, cậu biết rõ mình không nằm "
            "mơ, muốn thoát ra nhưng không thể điều khiển bản thân."
        ),
        (
            "Giống như mấy lần bị bóng đè trước đây, cậu biết rõ mình đang nằm "
            "mơ, không muốn thoát ra và không thể điều khiển bản thân."
        ),
        (
            "Cậu bị bóng đè, cậu biết rõ mình đang nằm mơ, muốn thoát ra nhưng "
            "không thể điều khiển bản thân, song cậu không hề sợ hãi."
        ),
        (
            "Cậu bị bóng đè, cậu biết rõ mình đang nằm mơ, muốn thoát ra nhưng "
            "không thể điều khiển bản thân, nhưng cậu không cảm thấy sợ hãi."
        ),
        (
            "Cậu bị bóng đè, cậu biết rõ mình đang nằm mơ, muốn thoát ra nhưng "
            "không thể điều khiển bản thân, nhưng cậu chẳng thấy sợ hãi."
        ),
        (
            "Cậu bị bóng đè, cậu biết rõ mình đang nằm mơ, muốn thoát ra nhưng "
            "không thể điều khiển bản thân, nhưng cậu vẫn hoàn toàn bình tĩnh."
        ),
        (
            "Cậu bị bóng đè, cậu biết rõ mình đang nằm mơ, muốn thoát ra nhưng "
            "không thể điều khiển bản thân, nhưng cậu vẫn hoàn toàn điềm tĩnh."
        ),
        (
            "Cậu bị bóng đè, cậu biết rõ mình đang nằm mơ, muốn thoát ra nhưng "
            "không thể điều khiển bản thân, nhưng cậu không có chút sợ hãi nào."
        ),
        (
            "Cậu bị bóng đè, cậu biết rõ mình đang nằm mơ, cậu không có chút kinh "
            "hãi nào, vẫn muốn thoát ra nhưng không thể điều khiển bản thân."
        ),
        (
            "Cậu bị bóng đè, cậu biết rõ mình đang nằm mơ, cậu chẳng thấy hoảng sợ, "
            "vẫn muốn thoát ra nhưng không thể điều khiển bản thân."
        ),
        (
            "Cậu bị bóng đè, cậu biết rõ mình đang nằm mơ, cậu không cảm thấy bất "
            "an, vẫn muốn thoát ra nhưng không thể điều khiển bản thân."
        ),
        (
            "Cậu bị bóng đè, cậu biết rõ mình đang nằm mơ, cậu bình tĩnh, vẫn muốn "
            "thoát ra nhưng không thể điều khiển bản thân."
        ),
        (
            "Cậu bị bóng đè, cậu biết rõ mình đang nằm mơ, cậu điềm tĩnh, vẫn muốn "
            "thoát ra nhưng không thể điều khiển bản thân."
        ),
        (
            "Không phải bị bóng đè, cậu biết rõ mình đang nằm mơ, muốn thoát ra "
            "nhưng không thể điều khiển bản thân."
        ),
        (
            "Cậu bị bóng đè, cậu biết rõ mình đang nằm mơ; Lan muốn thoát ra khỏi "
            "phòng, nhưng Nam không thể điều khiển bản thân vì say rượu."
        ),
        (
            "Lan đang bị bóng đè, cậu biết rõ mình đang nằm mơ, muốn thoát ra nhưng "
            "không thể điều khiển bản thân."
        ),
        (
            "Lan giống như bị bóng đè, cậu biết rõ mình đang nằm mơ, muốn thoát ra "
            "nhưng không thể điều khiển bản thân."
        ),
        (
            "Giống như Lan bị bóng đè trước đây, cậu biết rõ mình đang nằm mơ, "
            "muốn thoát ra nhưng không thể điều khiển bản thân."
        ),
        (
            "Lan, vào đêm ấy, bị bóng đè, Nam biết rõ mình đang nằm mơ, "
            "muốn thoát ra nhưng không thể điều khiển bản thân."
        ),
        (
            "Lan gặp hiện tượng lạ: bị bóng đè, Nam biết rõ mình đang nằm mơ, "
            "muốn thoát ra nhưng không thể điều khiển bản thân."
        ),
        (
            "Lan; bị bóng đè, Nam biết rõ mình đang nằm mơ, muốn thoát ra nhưng "
            "không thể điều khiển bản thân."
        ),
        (
            "Lan vừa cứu Nam rồi bị bóng đè, Nam biết rõ mình đang nằm mơ, "
            "muốn thoát ra nhưng không thể điều khiển bản thân."
        ),
        (
            "Giống như người lạ vừa cứu Nam rồi bị bóng đè, Nam biết rõ mình "
            "đang nằm mơ, muốn thoát ra nhưng không thể điều khiển bản thân."
        ),
        (
            "Cậu đâu có bị bóng đè, cậu biết rõ mình đang nằm mơ, muốn thoát ra "
            "nhưng không thể điều khiển bản thân."
        ),
        (
            "Cậu không hẳn bị bóng đè, cậu biết rõ mình đang nằm mơ, muốn thoát "
            "ra nhưng không thể điều khiển bản thân."
        ),
        (
            "Cậu chỉ suýt bị bóng đè, cậu biết rõ mình đang nằm mơ, muốn thoát ra "
            "nhưng không thể điều khiển bản thân."
        ),
        (
            "Cậu bị bóng đè, cậu biết rõ mình đang nằm mơ, muốn thoát ra nhưng "
            "không thể điều khiển bản thân, nhưng rồi cậu đã cử động được."
        ),
        (
            f"{V28_SEQ10_SLEEP_PARALYSIS_TEXT} "
            "Cậu vừa sợ hãi vừa phấn khích."
        ),
    ),
)
def test_sleep_paralysis_source_authority_rejects_unsafe_controls(
    text: str,
) -> None:
    assert not analysis_source_has_sleep_paralysis_helplessness(text)


def test_sleep_paralysis_source_authority_does_not_compose_neighbor_rows() -> None:
    source_rows = (
        "Giống như mấy lần bị bóng đè trước đây, cậu biết rõ mình đang nằm mơ.",
        "Cậu muốn thoát ra nhưng không thể điều khiển bản thân.",
    )

    assert not any(
        analysis_source_has_sleep_paralysis_helplessness(text)
        for text in source_rows
    )


def test_analysis_candidate_binds_exact_v28_seq10_sleep_paralysis_lock(
    tmp_path: Path,
) -> None:
    db, source_rows, envelope, clearance = _v29_v28_seq10_sleep_paralysis_db(
        tmp_path
    )

    candidate = _allocate_analysis_candidate(
        db,
        source_rows,
        candidate=envelope,
        deterministic_issues=clearance,
    )
    durable = json.loads(str(candidate["deterministic_issue_json"]))[
        "host_affect_clearance"
    ]
    lock = durable["semantic_locks"][0]

    assert source_rows[0]["stable_id"] == V28_SEQ10_SLEEP_PARALYSIS_STABLE_ID
    assert source_rows[0]["text_sha256"] == V28_SEQ10_SLEEP_PARALYSIS_TEXT_SHA256
    assert envelope["critic_rows"][0]["host_locked_fields"] == {
        "kind": "narration",
        "emotion": "afraid",
    }
    assert lock["rule"] == "narration_sleep_paralysis_helplessness"
    assert lock["cue_class"] == "sleep_paralysis_helplessness"
    assert lock["candidate_emotion"] == "afraid"
    assert lock["allowed_emotions"] == ["afraid"]
    assert ProjectDB(db.path).get_analysis_candidate(int(candidate["id"]))[
        "state"
    ] == "allocated"


def test_analysis_candidate_recalled_suffix_does_not_overlap_sleep_rule_on_replay(
    tmp_path: Path,
) -> None:
    overlap_text = (
        "Cậu bị bóng đè, cậu biết rõ mình đang nằm mơ, muốn thoát ra nhưng không "
        "thể điều khiển bản thân. Cậu nhớ lại vẫn tim đập chân run."
    )
    assert not analysis_source_has_sleep_paralysis_helplessness(overlap_text)
    assert analysis_source_has_recalled_persistent_fear(overlap_text)
    db, source_rows = _analysis_batch_db(tmp_path, texts=(overlap_text,))
    envelope = _semantic_lock_envelope(
        source_rows,
        candidate_emotion="afraid",
    )
    clearance = _host_semantic_clearance(
        envelope,
        rule="narration_recalled_persistent_fear",
        cue_class="recalled_persistent_fear",
        allowed_emotions=["afraid"],
    )

    candidate = _allocate_analysis_candidate(
        db,
        source_rows,
        candidate=envelope,
        deterministic_issues=clearance,
    )
    reopened = ProjectDB(db.path).get_analysis_candidate(int(candidate["id"]))
    durable = json.loads(str(reopened["deterministic_issue_json"]))[
        "host_affect_clearance"
    ]

    assert durable["semantic_locks"][0]["rule"] == (
        "narration_recalled_persistent_fear"
    )


def test_analysis_candidate_rejects_sleep_paralysis_lock_without_kind_field(
    tmp_path: Path,
) -> None:
    db, source_rows, envelope, clearance = _v29_v28_seq10_sleep_paralysis_db(
        tmp_path
    )
    envelope["critic_rows"][0]["host_locked_fields"] = {"emotion": "afraid"}
    clearance["host_affect_clearance"]["candidate_hash"] = _canonical_hash(
        envelope["critic_rows"]
    )

    with pytest.raises(RuntimeError, match="semantic clearance is not source-bound"):
        _allocate_analysis_candidate(
            db,
            source_rows,
            candidate=envelope,
            deterministic_issues=clearance,
        )


def test_analysis_candidate_rejects_sleep_paralysis_rule_for_thought_source(
    tmp_path: Path,
) -> None:
    db, source_rows = _analysis_batch_db(
        tmp_path,
        texts=(V28_SEQ10_SLEEP_PARALYSIS_TEXT,),
        kind_hints=("thought",),
    )
    envelope = _semantic_lock_envelope(
        source_rows,
        candidate_emotion="afraid",
    )
    clearance = _host_semantic_clearance(
        envelope,
        rule="narration_sleep_paralysis_helplessness",
        cue_class="sleep_paralysis_helplessness",
        allowed_emotions=["afraid"],
    )

    with pytest.raises(RuntimeError, match="semantic clearance is not source-bound"):
        _allocate_analysis_candidate(
            db,
            source_rows,
            candidate=envelope,
            deterministic_issues=clearance,
        )


@pytest.mark.parametrize(
    "text",
    (
        "Hạ Phong không còn nghĩ lại vẫn tim đập chân run.",
        "Hạ Phong từng nghĩ lại vẫn tim đập chân run.",
        "Nếu Hạ Phong nghĩ lại vẫn tim đập chân run, cậu sẽ xin nghỉ.",
        "Nghe nói Hạ Phong nghĩ lại vẫn tim đập chân run.",
        "Không phải Hạ Phong đến giờ nghĩ lại vẫn tim đập chân run.",
        "Không đúng là Hạ Phong đến giờ nghĩ lại vẫn tim đập chân run.",
        "Không chắc Hạ Phong đến giờ nghĩ lại vẫn tim đập chân run.",
        "Chưa chắc Hạ Phong đến giờ nghĩ lại vẫn tim đập chân run.",
        "Đâu phải Hạ Phong đến giờ nghĩ lại vẫn tim đập chân run.",
        "Cô phủ nhận Hạ Phong đến giờ nghĩ lại vẫn tim đập chân run.",
        "Cô nói Hạ Phong đến giờ nghĩ lại vẫn tim đập chân run.",
        "Cô nói rằng Hạ Phong đến giờ nghĩ lại vẫn tim đập chân run.",
        "Cô cho rằng Hạ Phong đến giờ nghĩ lại vẫn tim đập chân run.",
        "Cô nghi ngờ Hạ Phong đến giờ nghĩ lại vẫn tim đập chân run.",
        "Theo lời kể, Hạ Phong đến giờ nghĩ lại vẫn tim đập chân run.",
        "Có vẻ Hạ Phong đến giờ nghĩ lại vẫn tim đập chân run.",
        "Có vẻ như Hạ Phong đến giờ nghĩ lại vẫn tim đập chân run.",
        "Có vẻ là Hạ Phong đến giờ nghĩ lại vẫn tim đập chân run.",
        "Người ta đồn rằng Hạ Phong đến giờ nghĩ lại vẫn tim đập chân run.",
        "Theo tin đồn, Hạ Phong đến giờ nghĩ lại vẫn tim đập chân run.",
        "Theo lời đồn, Hạ Phong đến giờ nghĩ lại vẫn tim đập chân run.",
        "Nghe đồn Hạ Phong đến giờ nghĩ lại vẫn tim đập chân run.",
        "Tương truyền Hạ Phong đến giờ nghĩ lại vẫn tim đập chân run.",
        "Tưởng tượng rằng Hạ Phong đến giờ nghĩ lại vẫn tim đập chân run.",
        "Không có bằng chứng rằng Hạ Phong nghĩ lại vẫn tim đập chân run.",
        "Chưa có bằng chứng rằng Hạ Phong nghĩ lại vẫn tim đập chân run.",
        "Có vẻ một ký ức hiện lên, làm cho Hạ Phong nghĩ lại vẫn tim đập chân run.",
        "Không chắc một ký ức hiện lên, làm cho Hạ Phong nghĩ lại vẫn tim đập chân run.",
        "Theo lời đồn, một ký ức hiện lên, làm cho Hạ Phong nghĩ lại vẫn tim đập chân run.",
        "Cô phủ nhận chuyện một ký ức hiện lên, làm cho Hạ Phong nghĩ lại vẫn tim đập chân run.",
        "Nếu một ký ức hiện lên, làm cho Hạ Phong nghĩ lại vẫn tim đập chân run.",
        "Trước đây Hạ Phong nghĩ lại vẫn tim đập chân run.",
        "Ngày trước, Hạ Phong nghĩ lại vẫn tim đập chân run.",
        "Hồi ấy, Hạ Phong nghĩ lại vẫn tim đập chân run.",
        "Đã có lúc Hạ Phong nghĩ lại vẫn tim đập chân run.",
        "Khi đó Hạ Phong nghĩ lại vẫn tim đập chân run.",
        "Hồi đó Hạ Phong nghĩ lại vẫn tim đập chân run.",
        "Ngày ấy Hạ Phong nghĩ lại vẫn tim đập chân run.",
        "Thuở ấy Hạ Phong nghĩ lại vẫn tim đập chân run.",
        "Lúc trước Hạ Phong nghĩ lại vẫn tim đập chân run.",
        "Trước kia Hạ Phong nghĩ lại vẫn tim đập chân run.",
        "Năm xưa Hạ Phong nghĩ lại vẫn tim đập chân run.",
        "Xưa kia Hạ Phong nghĩ lại vẫn tim đập chân run.",
        "Trong quá khứ Hạ Phong nghĩ lại vẫn tim đập chân run.",
        "Hạ Phong giả vờ nghĩ lại vẫn tim đập chân run.",
        "Ông nhắc lại câu “Hạ Phong nghĩ lại vẫn tim đập chân run”.",
        "Cụm từ Hạ Phong nghĩ lại vẫn tim đập chân run được định nghĩa ở đây.",
        "Hạ Phong nghĩ lại vẫn tim đập chân run nhưng lại vui mừng nhẹ nhõm.",
        "Cô dịu dàng ôm đứa trẻ đang nghĩ lại vẫn tim đập chân run.",
        "Hạ Phong vẫn tim đập chân run.",
        "Liệu Hạ Phong nghĩ lại vẫn tim đập chân run?",
        (
            "Hạ Phong nghĩ lại vẫn tim đập chân run. "
            "Hạ Phong nghĩ lại vẫn tim đập chân run."
        ),
    ),
)
def test_recalled_persistent_fear_source_authority_excludes_ambiguous_rows(
    text: str,
) -> None:
    assert not analysis_source_has_recalled_persistent_fear(text)


@pytest.mark.parametrize(
    "text",
    (
        "Cậu không còn đực mặt ra, đầu óc một mảng trắng xóa.",
        "Cậu từng đực mặt ra, đầu óc một mảng trắng xóa.",
        "Nếu cậu đực mặt ra, đầu óc một mảng trắng xóa thì hãy ngồi xuống.",
        "Nghe nói cậu đực mặt ra, đầu óc một mảng trắng xóa.",
        "Không phải cậu đực mặt ra, đầu óc một mảng trắng xóa.",
        "Không đúng là cậu đực mặt ra, đầu óc một mảng trắng xóa.",
        "Không chắc cậu đực mặt ra, đầu óc một mảng trắng xóa.",
        "Chưa chắc cậu đực mặt ra, đầu óc một mảng trắng xóa.",
        "Đâu phải cậu đực mặt ra, đầu óc một mảng trắng xóa.",
        "Cô phủ nhận cậu đực mặt ra, đầu óc một mảng trắng xóa.",
        "Cô nói cậu đực mặt ra, đầu óc một mảng trắng xóa.",
        "Cô nói rằng cậu đực mặt ra, đầu óc một mảng trắng xóa.",
        "Cô cho rằng cậu đực mặt ra, đầu óc một mảng trắng xóa.",
        "Cô nghi ngờ cậu đực mặt ra, đầu óc một mảng trắng xóa.",
        "Theo lời kể, cậu đực mặt ra, đầu óc một mảng trắng xóa.",
        "Có vẻ cậu đực mặt ra, đầu óc một mảng trắng xóa.",
        "Có vẻ như cậu đực mặt ra, đầu óc một mảng trắng xóa.",
        "Có vẻ là cậu đực mặt ra, đầu óc một mảng trắng xóa.",
        "Người ta đồn rằng cậu đực mặt ra, đầu óc một mảng trắng xóa.",
        "Theo tin đồn, cậu đực mặt ra, đầu óc một mảng trắng xóa.",
        "Theo lời đồn, cậu đực mặt ra, đầu óc một mảng trắng xóa.",
        "Nghe đồn cậu đực mặt ra, đầu óc một mảng trắng xóa.",
        "Tương truyền cậu đực mặt ra, đầu óc một mảng trắng xóa.",
        "Tưởng tượng rằng cậu đực mặt ra, đầu óc một mảng trắng xóa.",
        "Không có bằng chứng rằng cậu đực mặt ra, đầu óc một mảng trắng xóa.",
        "Chưa có bằng chứng rằng cậu đực mặt ra, đầu óc một mảng trắng xóa.",
        "Trước đây cậu đực mặt ra, đầu óc một mảng trắng xóa.",
        "Ngày trước, cậu đực mặt ra, đầu óc một mảng trắng xóa.",
        "Hồi ấy, cậu đực mặt ra, đầu óc một mảng trắng xóa.",
        "Đã có lúc cậu đực mặt ra, đầu óc một mảng trắng xóa.",
        "Khi đó cậu đực mặt ra, đầu óc một mảng trắng xóa.",
        "Hồi đó cậu đực mặt ra, đầu óc một mảng trắng xóa.",
        "Ngày ấy cậu đực mặt ra, đầu óc một mảng trắng xóa.",
        "Thuở ấy cậu đực mặt ra, đầu óc một mảng trắng xóa.",
        "Lúc trước cậu đực mặt ra, đầu óc một mảng trắng xóa.",
        "Trước kia cậu đực mặt ra, đầu óc một mảng trắng xóa.",
        "Năm xưa cậu đực mặt ra, đầu óc một mảng trắng xóa.",
        "Xưa kia cậu đực mặt ra, đầu óc một mảng trắng xóa.",
        "Trong quá khứ cậu đực mặt ra, đầu óc một mảng trắng xóa.",
        "Cậu giả vờ đực mặt ra, đầu óc một mảng trắng xóa.",
        "Ông nhắc lại câu “cậu đực mặt ra, đầu óc một mảng trắng xóa”.",
        "Cậu đực mặt ra, đầu óc một mảng trắng xóa nhưng lại vui mừng.",
        (
            "Cậu đực mặt ra, đầu óc một mảng trắng xóa, "
            "tim đập chân run."
        ),
        "Cô dịu dàng ôm đứa trẻ đang đực mặt ra, đầu óc một mảng trắng xóa.",
        "Cậu đực mặt ra.",
        "Đầu óc cậu một mảng trắng xóa rồi cậu đực mặt ra.",
        "Liệu cậu đực mặt ra, đầu óc một mảng trắng xóa?",
    ),
)
def test_stunned_blank_mind_source_authority_excludes_ambiguous_rows(
    text: str,
) -> None:
    assert not analysis_source_has_stunned_blank_mind(text)


@pytest.mark.parametrize(
    "suffix",
    (
        ", nếu lời đồn là đúng.",
        ", theo lời đồn.",
        ", có lẽ vậy.",
        ", người ta nói thế.",
        ", nhưng đó chỉ là lời đồn.",
        ", nhưng điều đó không đúng.",
        ", nhưng đó không phải sự thật.",
        ", nhưng cậu chỉ giả vờ.",
        ", nhưng thực ra cậu hoàn toàn bình tĩnh.",
        "; tuy nhiên đó chỉ là giả thuyết.",
        ": đó chỉ là ví dụ.",
    ),
)
def test_direct_narration_affect_source_authority_rejects_outer_scope_suffix(
    suffix: str,
) -> None:
    assert not analysis_source_has_recalled_persistent_fear(
        f"Hạ Phong đến giờ nghĩ lại vẫn tim đập chân run{suffix}"
    )
    assert not analysis_source_has_stunned_blank_mind(
        f"Cậu đực mặt ra, đầu óc một mảng trắng xóa{suffix}"
    )


@pytest.mark.parametrize(
    "text",
    (
        "Cậu đực mặt ra, nhưng đó chỉ là giả vờ, đầu óc một mảng trắng xóa.",
        "Cậu đực mặt ra, người ta nói đầu óc một mảng trắng xóa.",
        "Cậu đực mặt ra, đầu óc có lẽ một mảng trắng xóa.",
        "Cậu đực mặt ra, đầu óc được đồn là trắng xóa.",
        "Cậu đực mặt ra, đầu óc không hề trắng xóa.",
        "Cậu đực mặt ra, đầu óc chưa từng trắng xóa.",
        "Cậu đực mặt ra, đầu óc giả vờ trắng xóa.",
    ),
)
def test_stunned_blank_mind_source_authority_rejects_nonassertive_bridge(
    text: str,
) -> None:
    assert not analysis_source_has_stunned_blank_mind(text)


@pytest.mark.parametrize(
    (
        "text",
        "rule",
        "cue_class",
        "allowed_emotions",
        "candidate_emotion",
        "wrong_emotion",
    ),
    DIRECT_NARRATION_AFFECT_LOCK_CASES,
)
def test_analysis_candidate_accepts_source_bound_direct_narration_affect_lock(
    tmp_path: Path,
    text: str,
    rule: str,
    cue_class: str,
    allowed_emotions: tuple[str, ...],
    candidate_emotion: str,
    wrong_emotion: str,
) -> None:
    del wrong_emotion
    db, source_rows = _analysis_batch_db(tmp_path, texts=(text,))
    envelope = _semantic_lock_envelope(
        source_rows,
        candidate_emotion=candidate_emotion,
    )
    clearance = _host_semantic_clearance(
        envelope,
        rule=rule,
        cue_class=cue_class,
        allowed_emotions=list(allowed_emotions),
    )

    candidate = _allocate_analysis_candidate(
        db,
        source_rows,
        candidate=envelope,
        deterministic_issues=clearance,
    )

    durable_clearance = json.loads(str(candidate["deterministic_issue_json"]))[
        "host_affect_clearance"
    ]
    assert candidate["state"] == "allocated"
    assert durable_clearance["policy_version"] == "host_affect_v10"
    assert durable_clearance["semantic_locks"] == clearance[
        "host_affect_clearance"
    ]["semantic_locks"]


@pytest.mark.parametrize(
    (
        "text",
        "rule",
        "cue_class",
        "allowed_emotions",
        "candidate_emotion",
        "wrong_emotion",
    ),
    DIRECT_NARRATION_AFFECT_LOCK_CASES,
)
def test_analysis_candidate_rejects_invalid_direct_narration_affect_emotion(
    tmp_path: Path,
    text: str,
    rule: str,
    cue_class: str,
    allowed_emotions: tuple[str, ...],
    candidate_emotion: str,
    wrong_emotion: str,
) -> None:
    del rule, cue_class, allowed_emotions, candidate_emotion
    db, source_rows = _analysis_batch_db(tmp_path, texts=(text,))
    envelope = _analysis_acceptance_envelope(source_rows, emotion=wrong_emotion)

    with pytest.raises(RuntimeError, match="mandatory host semantic emotion"):
        _allocate_analysis_candidate(db, source_rows, candidate=envelope)


@pytest.mark.parametrize(
    ("forged_field", "forged_value", "expected_error"),
    (
        ("rule", "forged_direct_narration_rule", "unknown rule"),
        ("cue_class", "forged_direct_affect", "source-bound"),
        ("allowed_emotions", ["afraid", "neutral"], "source-bound"),
        ("text_sha256", "f" * 64, "source-bound"),
    ),
)
@pytest.mark.parametrize(
    (
        "text",
        "rule",
        "cue_class",
        "allowed_emotions",
        "candidate_emotion",
        "wrong_emotion",
    ),
    DIRECT_NARRATION_AFFECT_LOCK_CASES,
)
def test_analysis_candidate_rejects_forged_direct_narration_affect_lock(
    tmp_path: Path,
    text: str,
    rule: str,
    cue_class: str,
    allowed_emotions: tuple[str, ...],
    candidate_emotion: str,
    wrong_emotion: str,
    forged_field: str,
    forged_value: object,
    expected_error: str,
) -> None:
    del wrong_emotion
    db, source_rows = _analysis_batch_db(tmp_path, texts=(text,))
    envelope = _semantic_lock_envelope(
        source_rows,
        candidate_emotion=candidate_emotion,
    )
    clearance = _host_semantic_clearance(
        envelope,
        rule=rule,
        cue_class=cue_class,
        allowed_emotions=list(allowed_emotions),
    )
    host_clearance = clearance["host_affect_clearance"]
    host_clearance["semantic_locks"][0][forged_field] = forged_value
    host_clearance["evidence"][0][forged_field] = forged_value

    with pytest.raises(RuntimeError, match=expected_error):
        _allocate_analysis_candidate(
            db,
            source_rows,
            candidate=envelope,
            deterministic_issues=clearance,
        )


@pytest.mark.parametrize(
    (
        "text",
        "rule",
        "cue_class",
        "allowed_emotions",
        "candidate_emotion",
        "wrong_emotion",
    ),
    DIRECT_NARRATION_AFFECT_LOCK_CASES,
)
def test_analysis_candidate_revalidates_direct_narration_affect_lock_on_reopen(
    tmp_path: Path,
    text: str,
    rule: str,
    cue_class: str,
    allowed_emotions: tuple[str, ...],
    candidate_emotion: str,
    wrong_emotion: str,
) -> None:
    db, source_rows = _analysis_batch_db(tmp_path, texts=(text,))
    envelope = _semantic_lock_envelope(
        source_rows,
        candidate_emotion=candidate_emotion,
    )
    clearance = _host_semantic_clearance(
        envelope,
        rule=rule,
        cue_class=cue_class,
        allowed_emotions=list(allowed_emotions),
    )
    candidate = _allocate_analysis_candidate(
        db,
        source_rows,
        candidate=envelope,
        deterministic_issues=clearance,
    )
    tampered = json.loads(str(candidate["deterministic_issue_json"]))
    forged_allowed = [*allowed_emotions, wrong_emotion]
    host_clearance = tampered["host_affect_clearance"]
    host_clearance["semantic_locks"][0]["allowed_emotions"] = forged_allowed
    host_clearance["evidence"][0]["allowed_emotions"] = forged_allowed
    tampered_json = json.dumps(
        tampered,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    with db.connect() as conn:
        conn.execute(
            "UPDATE analysis_candidates SET deterministic_issue_json=?,"
            "deterministic_issue_hash=? WHERE id=?",
            (tampered_json, sha256_text(tampered_json), int(candidate["id"])),
        )

    with pytest.raises(RuntimeError, match="semantic clearance is not source-bound"):
        ProjectDB(db.path).get_analysis_candidate(int(candidate["id"]))


@pytest.mark.parametrize(
    (
        "text",
        "rule",
        "cue_class",
        "allowed_emotions",
        "candidate_emotion",
        "wrong_emotion",
    ),
    DIRECT_NARRATION_AFFECT_LOCK_CASES,
)
def test_direct_narration_affect_critic_dissent_cannot_override_commit(
    tmp_path: Path,
    text: str,
    rule: str,
    cue_class: str,
    allowed_emotions: tuple[str, ...],
    candidate_emotion: str,
    wrong_emotion: str,
) -> None:
    db, source_rows = _analysis_batch_db(tmp_path, texts=(text,))
    envelope = _semantic_lock_envelope(
        source_rows,
        candidate_emotion=candidate_emotion,
    )
    clearance = _host_semantic_clearance(
        envelope,
        rule=rule,
        cue_class=cue_class,
        allowed_emotions=list(allowed_emotions),
    )
    candidate = _allocate_analysis_candidate(
        db,
        source_rows,
        candidate=envelope,
        deterministic_issues=clearance,
    )
    candidate_id = int(candidate["id"])
    critic_contract = _accepted_critic_contract(envelope)
    attempt = db.reserve_analysis_critic_attempt(
        candidate_id,
        expected_state="allocated",
        max_attempts=2,
        intent={"candidate_hash": str(candidate["candidate_hash"])},
        contract=critic_contract,
    )
    evidence = _semantic_override_evidence(
        envelope,
        clearance,
        corrected_emotion=wrong_emotion,
    )
    evidence["segments"][0]["critic"]["evidence_quote"] = (
        canonical_analysis_critic_source_anchors(text)[0]
        if critic_contract["evidence_policy"]
        == ANALYSIS_CRITIC_EVIDENCE_POLICY_SINGLETON_SOURCE_ANCHOR
        else text
    )
    db.complete_analysis_critic_attempt(
        candidate_id,
        1,
        expected_intent_hash=str(attempt["intent_hash"]),
        expected_contract_hash=str(attempt["contract_hash"]),
        result_state="critic_accepted",
        outcome={"accepted": True, "host_semantic_override": True},
        evidence=evidence,
        commit_envelope=envelope,
    )

    reopened = ProjectDB(db.path)
    snapshot = reopened.analysis_candidate_acceptance_envelope(candidate_id)
    stored_item = snapshot["critic_evidence"]["segments"][0]
    assert stored_item["critic"]["emotion"] == wrong_emotion
    assert stored_item["host_semantic_override"]["allowed_values"] == list(
        allowed_emotions
    )
    assert (
        snapshot["commit_envelope"]["segments"][0]["data"]["emotion"]
        == candidate_emotion
    )
    batch = [
        {
            "segment_id": segment["segment_id"],
            "stable_id": segment["stable_id"],
            "text_sha256": segment["text_sha256"],
            "expected_status": "pending",
            "data": dict(segment["data"]),
        }
        for segment in snapshot["commit_envelope"]["segments"]
    ]
    reopened.update_analysis_batch_with_event(
        batch,
        low_confidence_threshold=0.65,
        event_level="info",
        event_code="ANALYSIS_DIRECTOR_CRITIC_ACCEPTED",
        event_message="host-locked direct affect accepted",
        event_details={"candidate_hash": str(candidate["candidate_hash"])},
        **ANALYSIS_MODEL_COMMIT,
        analysis_candidate_id=candidate_id,
        analysis_policy_fingerprint=ANALYSIS_POLICY_FINGERPRINT,
        analysis_group_fingerprint=ANALYSIS_GROUP_FINGERPRINT,
        analysis_context_hash=ANALYSIS_CONTEXT_HASH,
    )

    committed = reopened.list_segments()[0]
    assert committed["status"] == "analyzed"
    assert committed["emotion"] == candidate_emotion
    assert reopened.get_analysis_candidate(candidate_id)["state"] == "accepted"


@pytest.mark.parametrize(
    ("text", "kind_hint", "candidate_emotion"),
    (
        (
            "‘Không được… Không được ngủ… sẽ chết mất.’",
            "thought",
            "afraid",
        ),
        (
            "Phổi và yết hầu đang bị thiêu đốt. Ý thức của anh liền mất dần.",
            "narration",
            "afraid",
        ),
        (
            "Cậu tuyệt vọng gắng gượng đến gần ánh sáng.",
            "narration",
            "afraid",
        ),
        (RECALLED_PERSISTENT_FEAR_TEXT, "narration", "afraid"),
        (STUNNED_BLANK_MIND_TEXT, "narration", "surprised"),
    ),
)
def test_analysis_candidate_rejects_mandatory_semantic_lock_when_omitted(
    tmp_path: Path,
    text: str,
    kind_hint: str,
    candidate_emotion: str,
) -> None:
    db, source_rows = _analysis_batch_db(
        tmp_path,
        texts=(text,),
        kind_hints=(kind_hint,),
    )
    envelope = _semantic_lock_envelope(
        source_rows,
        candidate_emotion=candidate_emotion,
    )
    envelope["critic_rows"][0]["host_locked_fields"] = {}

    with pytest.raises(RuntimeError, match="source-derived mandatory locks"):
        _allocate_analysis_candidate(
            db,
            source_rows,
            candidate=envelope,
        )


@pytest.mark.parametrize("candidate_emotion", ["afraid", "sad", "tired"])
def test_analysis_candidate_accepts_source_bound_desperate_exertion_lock(
    tmp_path: Path,
    candidate_emotion: str,
) -> None:
    db, source_rows = _analysis_batch_db(
        tmp_path,
        texts=(
            "Được ánh sáng đó chiếu rọi, Hạ Phong cảm thấy sức lực dần hồi phục, "
            "vì vậy cậu tuyệt vọng gắng gượng đến gần ánh sáng đó.",
        ),
    )
    envelope = _semantic_lock_envelope(
        source_rows,
        candidate_emotion=candidate_emotion,
    )
    clearance = _host_semantic_clearance(
        envelope,
        rule="narration_desperate_exertion",
        cue_class="desperate_exertion",
        allowed_emotions=["afraid", "sad", "tired"],
    )

    candidate = _allocate_analysis_candidate(
        db,
        source_rows,
        candidate=envelope,
        deterministic_issues=clearance,
    )

    assert candidate["state"] == "allocated"


@pytest.mark.parametrize("candidate_emotion", ["neutral", "surprised"])
def test_analysis_candidate_rejects_invalid_mandatory_desperate_exertion_emotion(
    tmp_path: Path,
    candidate_emotion: str,
) -> None:
    db, source_rows = _analysis_batch_db(
        tmp_path,
        texts=("Cậu tuyệt vọng gắng gượng đến gần ánh sáng.",),
    )
    envelope = _analysis_acceptance_envelope(source_rows, emotion=candidate_emotion)

    with pytest.raises(RuntimeError, match="mandatory host semantic emotion"):
        _allocate_analysis_candidate(
            db,
            source_rows,
            candidate=envelope,
        )


@pytest.mark.parametrize(
    "text",
    (
        "Cậu không còn tuyệt vọng gắng gượng đến gần ánh sáng.",
        "Cậu từng tuyệt vọng gắng gượng trong quãng đời trước.",
        "Ông nhắc lại câu “cậu tuyệt vọng gắng gượng” rồi giải thích.",
        "Cậu tuyệt vọng gắng gượng nhưng vẫn vui mừng vì mọi người an toàn.",
        "Một nỗ lực tuyệt vọng gắng gượng diễn ra trong im lặng.",
        "Cậu tuyệt vọng đến gần ánh sáng.",
        "Nếu cậu tuyệt vọng gắng gượng đến gần ánh sáng, cậu sẽ kiệt sức.",
        "Tôi không tin cậu tuyệt vọng gắng gượng đến gần ánh sáng.",
        "Không có chuyện cậu tuyệt vọng gắng gượng đến gần ánh sáng.",
        "Tôi không hề tin rằng cậu tuyệt vọng gắng gượng đến gần ánh sáng.",
        "Tôi không còn tin rằng cậu tuyệt vọng gắng gượng đến gần ánh sáng.",
        "Tôi chưa từng nghĩ rằng cậu tuyệt vọng gắng gượng đến gần ánh sáng.",
        "Không ai tin rằng cậu tuyệt vọng gắng gượng đến gần ánh sáng.",
        "Có lẽ cậu tuyệt vọng gắng gượng đến gần ánh sáng.",
        "Dường như cậu tuyệt vọng gắng gượng đến gần ánh sáng.",
        "Nghe nói cậu tuyệt vọng gắng gượng đến gần ánh sáng.",
        "Tôi nghi ngờ rằng cậu tuyệt vọng gắng gượng đến gần ánh sáng.",
        "Liệu cậu tuyệt vọng gắng gượng đến gần ánh sáng?",
    ),
)
def test_analysis_candidate_rejects_desperate_exertion_lock_on_ambiguous_source(
    tmp_path: Path,
    text: str,
) -> None:
    db, source_rows = _analysis_batch_db(tmp_path, texts=(text,))
    envelope = _semantic_lock_envelope(source_rows, candidate_emotion="sad")
    clearance = _host_semantic_clearance(
        envelope,
        rule="narration_desperate_exertion",
        cue_class="desperate_exertion",
        allowed_emotions=["afraid", "sad", "tired"],
    )

    with pytest.raises(RuntimeError, match="semantic clearance is not source-bound"):
        _allocate_analysis_candidate(
            db,
            source_rows,
            candidate=envelope,
            deterministic_issues=clearance,
        )


@pytest.mark.parametrize(
    ("texts", "kind_hints", "relabel_index", "preserve_thought_indexes"),
    [
        (
            ("‘Mình sẽ chết mất.’", "Nội dung tiếp theo."),
            ("thought", "narration"),
            0,
            (),
        ),
        (
            (
                "Phổi và yết hầu đang bị thiêu đốt. Ý thức của anh liền mất dần.",
                "Cậu cố mở mắt.",
            ),
            ("narration", "narration"),
            0,
            (),
        ),
        (
            (
                "Cậu tuyệt vọng gắng gượng đến gần ánh sáng.",
                "Ánh sáng vẫn ở phía trước.",
            ),
            ("narration", "narration"),
            0,
            (),
        ),
        (
            (RECALLED_PERSISTENT_FEAR_TEXT, "Nội dung tiếp theo."),
            ("narration", "narration"),
            0,
            (),
        ),
        (
            (STUNNED_BLANK_MIND_TEXT, "Nội dung tiếp theo."),
            ("narration", "narration"),
            0,
            (),
        ),
        (
            ("‘Mình sẽ chết mất.’", "‘Tỉnh dậy, phải tỉnh dậy!’"),
            ("thought", "thought"),
            1,
            (0,),
        ),
    ],
)
def test_analysis_candidate_rejects_mandatory_semantic_kind_lock_when_omitted(
    tmp_path: Path,
    texts: tuple[str, ...],
    kind_hints: tuple[str, ...],
    relabel_index: int,
    preserve_thought_indexes: tuple[int, ...],
) -> None:
    db, source_rows = _analysis_batch_db(
        tmp_path,
        texts=texts,
        kind_hints=kind_hints,
    )
    envelope = _analysis_acceptance_envelope(source_rows)
    for index in preserve_thought_indexes:
        envelope["segments"][index]["data"]["kind"] = "thought"
        _refresh_analysis_note(envelope, index)
        envelope["critic_rows"][index]["candidate"]["kind"] = "thought"
    target_kind = "thought" if kind_hints[relabel_index] == "narration" else "narration"
    envelope["segments"][relabel_index]["data"]["kind"] = target_kind
    _refresh_analysis_note(envelope, relabel_index)
    envelope["critic_rows"][relabel_index]["candidate"]["kind"] = target_kind

    with pytest.raises(RuntimeError, match="source-owned boundary"):
        _allocate_analysis_candidate(db, source_rows, candidate=envelope)


def test_analysis_candidate_allows_ordinary_narration_to_implicit_thought(
    tmp_path: Path,
) -> None:
    db, source_rows = _analysis_batch_db(
        tmp_path,
        texts=("Mình đang ở đâu thế này?", "Nội dung tiếp theo."),
    )
    envelope = _analysis_acceptance_envelope(source_rows)
    envelope["segments"][0]["data"]["kind"] = "thought"
    _refresh_analysis_note(envelope, 0)
    envelope["critic_rows"][0]["candidate"]["kind"] = "thought"

    candidate = _allocate_analysis_candidate(db, source_rows, candidate=envelope)

    assert str(candidate["state"]) == "allocated"


@pytest.mark.parametrize(
    "text",
    (
        "Phổi và yết hầu không còn bị thiêu đốt, ý thức đã tỉnh táo và anh vui mừng.",
        "Ông nhắc lại câu “cậu tuyệt vọng gắng gượng” rồi giải thích.",
        "Nếu cậu tuyệt vọng gắng gượng đến gần ánh sáng, cậu sẽ kiệt sức.",
    ),
)
def test_analysis_candidate_allows_ambiguous_narration_to_thought(
    tmp_path: Path,
    text: str,
) -> None:
    db, source_rows = _analysis_batch_db(tmp_path, texts=(text,))
    envelope = _analysis_acceptance_envelope(source_rows)
    envelope["segments"][0]["data"]["kind"] = "thought"
    _refresh_analysis_note(envelope, 0)
    envelope["critic_rows"][0]["candidate"]["kind"] = "thought"

    candidate = _allocate_analysis_candidate(db, source_rows, candidate=envelope)

    assert str(candidate["state"]) == "allocated"


def test_analysis_candidate_revalidates_source_owned_kind_after_reopen(
    tmp_path: Path,
) -> None:
    db, source_rows = _analysis_batch_db(
        tmp_path,
        texts=("‘Mình đang ở đâu?’", "Nội dung tiếp theo."),
        kind_hints=("thought", "narration"),
    )
    envelope = _analysis_acceptance_envelope(source_rows)
    envelope["segments"][0]["data"]["kind"] = "thought"
    _refresh_analysis_note(envelope, 0)
    envelope["critic_rows"][0]["candidate"]["kind"] = "thought"
    candidate = _allocate_analysis_candidate(db, source_rows, candidate=envelope)
    tampered = copy.deepcopy(envelope)
    tampered["segments"][0]["data"]["kind"] = "narration"
    _refresh_analysis_note(tampered, 0)
    tampered["critic_rows"][0]["candidate"]["kind"] = "narration"
    tampered_json = json.dumps(
        tampered,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    tampered_candidate_hash = _canonical_hash(tampered["critic_rows"])
    with db.connect() as conn:
        conn.execute(
            "UPDATE analysis_candidates SET candidate_json=?,candidate_hash=?,envelope_hash=? "
            "WHERE id=?",
            (
                tampered_json,
                tampered_candidate_hash,
                sha256_text(tampered_json),
                int(candidate["id"]),
            ),
        )

    with pytest.raises(RuntimeError, match="source-owned boundary"):
        ProjectDB(db.path).get_analysis_candidate(int(candidate["id"]))


def test_analysis_candidate_rejects_unsupported_durable_kind(tmp_path: Path) -> None:
    db, source_rows = _analysis_batch_db(tmp_path)
    envelope = _analysis_acceptance_envelope(source_rows)
    envelope["segments"][0]["data"]["kind"] = "unsupported"
    envelope["critic_rows"][0]["candidate"]["kind"] = "unsupported"

    with pytest.raises(ValueError, match="Unsupported analysis delivery note kind"):
        _allocate_analysis_candidate(db, source_rows, candidate=envelope)


@pytest.mark.parametrize(
    "text",
    (
        "Cậu không sợ hãi và kinh hoàng; sau đó cậu tuyệt vọng gắng gượng "
        "đến gần ánh sáng.",
        "Cậu không vui mừng và phấn khích; sau đó cậu tuyệt vọng gắng gượng "
        "đến gần ánh sáng.",
        "Cậu khóc rồi cậu tuyệt vọng gắng gượng đến gần ánh sáng.",
        "Đau lòng, cậu tuyệt vọng gắng gượng đến gần ánh sáng.",
    ),
)
def test_analysis_candidate_accepts_desperate_exertion_after_coordinated_negation(
    tmp_path: Path,
    text: str,
) -> None:
    db, source_rows = _analysis_batch_db(tmp_path, texts=(text,))
    envelope = _semantic_lock_envelope(source_rows, candidate_emotion="sad")
    clearance = _host_semantic_clearance(
        envelope,
        rule="narration_desperate_exertion",
        cue_class="desperate_exertion",
        allowed_emotions=["afraid", "sad", "tired"],
    )

    candidate = _allocate_analysis_candidate(
        db,
        source_rows,
        candidate=envelope,
        deterministic_issues=clearance,
    )

    assert candidate["state"] == "allocated"


def test_analysis_candidate_rejects_mandatory_adjacent_lock_when_omitted(
    tmp_path: Path,
) -> None:
    db, source_rows = _analysis_batch_db(
        tmp_path,
        texts=(
            "‘Không được… Không được ngủ… sẽ chết mất.’",
            "‘Tỉnh dậy, phải tỉnh dậy!’",
        ),
        kind_hints=("thought", "thought"),
    )
    with db.connect() as conn:
        conn.execute("UPDATE segments SET paragraph_index=seq WHERE chapter_id=1")
    source_rows = [dict(row) for row in db.list_segments()]
    wake_row = source_rows[1]
    envelope = _analysis_acceptance_envelope(
        [wake_row],
        emotion="afraid",
        previous_text_by_stable_id={
            str(wake_row["stable_id"]): str(source_rows[0]["text"])[-500:]
        },
    )
    envelope["segments"][0]["data"]["kind"] = "thought"
    _refresh_analysis_note(envelope, 0)
    envelope["critic_rows"][0]["candidate"]["kind"] = "thought"

    with pytest.raises(RuntimeError, match="source-derived mandatory locks"):
        _allocate_analysis_candidate(
            db,
            [wake_row],
            candidate=envelope,
        )


def test_analysis_candidate_rejects_invalid_mandatory_adjacent_emotion(
    tmp_path: Path,
) -> None:
    db, source_rows = _analysis_batch_db(
        tmp_path,
        texts=(
            "‘Không được… Không được ngủ… sẽ chết mất.’",
            "‘Tỉnh dậy, phải tỉnh dậy!’",
        ),
        kind_hints=("thought", "thought"),
    )
    with db.connect() as conn:
        conn.execute("UPDATE segments SET paragraph_index=seq WHERE chapter_id=1")
    source_rows = [dict(row) for row in db.list_segments()]
    wake_row = source_rows[1]
    envelope = _analysis_acceptance_envelope(
        [wake_row],
        previous_text_by_stable_id={
            str(wake_row["stable_id"]): str(source_rows[0]["text"])[-500:]
        },
    )
    envelope["segments"][0]["data"]["kind"] = "thought"
    _refresh_analysis_note(envelope, 0)
    envelope["critic_rows"][0]["candidate"]["kind"] = "thought"

    with pytest.raises(RuntimeError, match="mandatory host semantic emotion"):
        _allocate_analysis_candidate(
            db,
            [wake_row],
            candidate=envelope,
        )


@pytest.mark.parametrize(
    ("text", "kind_hint"),
    (
        (
            "‘Không được… Không được ngủ… sẽ chết mất.’",
            "thought",
        ),
        (
            "Phổi và yết hầu đang bị thiêu đốt. Ý thức của anh liền mất dần.",
            "narration",
        ),
    ),
)
def test_analysis_candidate_rejects_invalid_mandatory_semantic_emotion(
    tmp_path: Path,
    text: str,
    kind_hint: str,
) -> None:
    db, source_rows = _analysis_batch_db(
        tmp_path,
        texts=(text,),
        kind_hints=(kind_hint,),
    )
    envelope = _analysis_acceptance_envelope(source_rows)
    envelope["segments"][0]["data"]["kind"] = kind_hint
    _refresh_analysis_note(envelope, 0)
    envelope["critic_rows"][0]["candidate"]["kind"] = kind_hint

    with pytest.raises(RuntimeError, match="mandatory host semantic emotion"):
        _allocate_analysis_candidate(
            db,
            source_rows,
            candidate=envelope,
        )


def test_analysis_candidate_without_semantic_source_needs_no_host_clearance(
    tmp_path: Path,
) -> None:
    db, source_rows = _analysis_batch_db(
        tmp_path,
        texts=("The room remained quiet through the afternoon.",),
    )
    envelope = _analysis_acceptance_envelope(source_rows)

    candidate = _allocate_analysis_candidate(
        db,
        source_rows,
        candidate=envelope,
    )

    assert candidate["state"] == "allocated"


def test_analysis_candidate_accepts_source_bound_host_semantic_override(
    tmp_path: Path,
) -> None:
    physical_text = (
        "Phổi và yết hầu đang bị thiêu đốt. "
        "Ý thức của Hạ Phong rất nhanh liền trở nên mơ hồ."
    )
    db, source_rows = _analysis_batch_db(
        tmp_path,
        texts=(physical_text, "Cậu cố mở mắt."),
    )
    envelope = _semantic_lock_envelope(source_rows)
    clearance = _host_semantic_clearance(envelope)
    candidate = _allocate_analysis_candidate(
        db,
        source_rows,
        candidate=envelope,
        deterministic_issues=clearance,
    )
    attempt = db.reserve_analysis_critic_attempt(
        int(candidate["id"]),
        expected_state="allocated",
        max_attempts=2,
        intent={"candidate_hash": str(candidate["candidate_hash"])},
        contract=_accepted_critic_contract(envelope),
    )
    evidence = _semantic_override_evidence(envelope, clearance)

    db.complete_analysis_critic_attempt(
        int(candidate["id"]),
        1,
        expected_intent_hash=str(attempt["intent_hash"]),
        expected_contract_hash=str(attempt["contract_hash"]),
        result_state="critic_accepted",
        outcome={"accepted": True, "host_semantic_override": True},
        evidence=evidence,
        commit_envelope=envelope,
    )

    snapshot = ProjectDB(db.path).analysis_candidate_acceptance_envelope(
        int(candidate["id"])
    )
    stored_item = snapshot["critic_evidence"]["segments"][0]
    assert stored_item["critic"]["emotion"] == "neutral"
    assert stored_item["effective_accept"] is True
    assert stored_item["host_semantic_override"]["allowed_values"] == [
        "afraid",
        "tired",
    ]
    assert snapshot["commit_envelope"]["segments"][0]["data"]["emotion"] == "afraid"


def test_analysis_candidate_revalidates_semantic_override_protocol_after_reopen(
    tmp_path: Path,
) -> None:
    physical_text = (
        "Phổi và yết hầu đang bị thiêu đốt. "
        "Ý thức của anh nhanh chóng trở nên mơ hồ."
    )
    db, source_rows = _analysis_batch_db(
        tmp_path,
        texts=(physical_text, "Cậu cố mở mắt."),
    )
    envelope = _semantic_lock_envelope(source_rows)
    clearance = _host_semantic_clearance(envelope)
    candidate = _allocate_analysis_candidate(
        db,
        source_rows,
        candidate=envelope,
        deterministic_issues=clearance,
    )
    candidate_id = int(candidate["id"])
    attempt = db.reserve_analysis_critic_attempt(
        candidate_id,
        expected_state="allocated",
        max_attempts=2,
        intent={"candidate_hash": str(candidate["candidate_hash"])},
        contract=_accepted_critic_contract(envelope),
    )
    db.complete_analysis_critic_attempt(
        candidate_id,
        1,
        expected_intent_hash=str(attempt["intent_hash"]),
        expected_contract_hash=str(attempt["contract_hash"]),
        result_state="critic_accepted",
        outcome={"accepted": True},
        evidence=_semantic_override_evidence(envelope, clearance),
        commit_envelope=envelope,
    )

    with db.connect() as conn:
        stored_attempt = conn.execute(
            "SELECT * FROM analysis_critic_attempts "
            "WHERE analysis_candidate_id=? AND attempt_number=1",
            (candidate_id,),
        ).fetchone()
        stored_candidate = conn.execute(
            "SELECT * FROM analysis_candidates WHERE id=?",
            (candidate_id,),
        ).fetchone()
        tampered_evidence = json.loads(str(stored_attempt["evidence_json"]))
        tampered_item = tampered_evidence["segments"][0]
        tampered_item["critic"]["accept"] = True
        del tampered_item["host_semantic_override"]
        evidence_json, evidence_hash = db._canonical_analysis_json(
            tampered_evidence,
            "tampered semantic critic evidence",
        )
        _completion_json, completion_hash = db._canonical_analysis_json(
            {
                "commit_envelope_hash": stored_candidate["commit_envelope_hash"],
                "contract_hash": stored_attempt["contract_hash"],
                "evidence_hash": evidence_hash,
                "intent_hash": stored_attempt["intent_hash"],
                "outcome_hash": stored_attempt["outcome_hash"],
            },
            "tampered semantic critic completion",
        )
        conn.execute(
            "UPDATE analysis_critic_attempts SET evidence_json=?,evidence_hash=?,"
            "completion_hash=? WHERE analysis_candidate_id=? AND attempt_number=1",
            (evidence_json, evidence_hash, completion_hash, candidate_id),
        )

    reopened = ProjectDB(db.path)
    with pytest.raises(RuntimeError, match="exact delivery/confidence"):
        reopened.analysis_candidate_acceptance_envelope(candidate_id)
    batch = [
        {
            "segment_id": segment["segment_id"],
            "stable_id": segment["stable_id"],
            "text_sha256": segment["text_sha256"],
            "expected_status": "pending",
            "data": dict(segment["data"]),
        }
        for segment in envelope["segments"]
    ]
    with pytest.raises(RuntimeError, match="exact delivery/confidence"):
        reopened.update_analysis_batch_with_event(
            batch,
            low_confidence_threshold=0.65,
            event_level="info",
            event_code="ANALYSIS_DIRECTOR_CRITIC_ACCEPTED",
            event_message="must roll back",
            event_details={"candidate_hash": str(candidate["candidate_hash"])},
            **ANALYSIS_MODEL_COMMIT,
            analysis_candidate_id=candidate_id,
            analysis_policy_fingerprint=ANALYSIS_POLICY_FINGERPRINT,
            analysis_group_fingerprint=ANALYSIS_GROUP_FINGERPRINT,
            analysis_context_hash=ANALYSIS_CONTEXT_HASH,
        )

    assert {row["status"] for row in reopened.list_segments()} == {"pending"}
    with reopened.connect() as conn:
        stored_state = conn.execute(
            "SELECT state FROM analysis_candidates WHERE id=?",
            (candidate_id,),
        ).fetchone()["state"]
    assert stored_state == "critic_accepted"


@pytest.mark.parametrize(
    ("raw_accept", "corrected_emotion", "remove_delta"),
    (
        (True, "neutral", False),
        (False, "afraid", True),
        (False, "tired", False),
    ),
)
def test_analysis_candidate_semantic_override_rejects_invalid_critic_protocol(
    tmp_path: Path,
    raw_accept: bool,
    corrected_emotion: str,
    remove_delta: bool,
) -> None:
    physical_text = (
        "Phổi và yết hầu đang bị thiêu đốt. "
        "Ý thức của Hạ Phong nhanh chóng trở nên mơ hồ."
    )
    db, source_rows = _analysis_batch_db(
        tmp_path,
        texts=(physical_text, "Cậu cố mở mắt."),
    )
    envelope = _semantic_lock_envelope(source_rows)
    clearance = _host_semantic_clearance(envelope)
    candidate = _allocate_analysis_candidate(
        db,
        source_rows,
        candidate=envelope,
        deterministic_issues=clearance,
    )
    attempt = db.reserve_analysis_critic_attempt(
        int(candidate["id"]),
        expected_state="allocated",
        max_attempts=2,
        intent={"candidate_hash": str(candidate["candidate_hash"])},
        contract=_accepted_critic_contract(envelope),
    )
    evidence = _semantic_override_evidence(
        envelope,
        clearance,
        corrected_emotion=corrected_emotion,
    )
    item = evidence["segments"][0]
    item["critic"]["accept"] = raw_accept
    item["host_semantic_override"]["raw_accept"] = raw_accept
    if remove_delta:
        item["field_deltas"] = []
        item["host_semantic_override"]["raw_field_deltas"] = []

    with pytest.raises(RuntimeError, match="exact delivery/confidence"):
        db.complete_analysis_critic_attempt(
            int(candidate["id"]),
            1,
            expected_intent_hash=str(attempt["intent_hash"]),
            expected_contract_hash=str(attempt["contract_hash"]),
            result_state="critic_accepted",
            outcome={"accepted": True},
            evidence=evidence,
            commit_envelope=envelope,
        )


def test_v32_dialogue_kind_only_override_survives_reopen_and_commit(
    tmp_path: Path,
) -> None:
    db, source_rows, envelope = _v32_seq43_dialogue_db(tmp_path)
    candidate = _allocate_analysis_candidate(db, source_rows, candidate=envelope)
    candidate_id = int(candidate["id"])
    attempt = db.reserve_analysis_critic_attempt(
        candidate_id,
        expected_state="allocated",
        max_attempts=2,
        intent={"candidate_hash": str(candidate["candidate_hash"])},
        contract=_accepted_critic_contract(envelope),
    )

    ProjectDB(db.path).complete_analysis_critic_attempt(
        candidate_id,
        1,
        expected_intent_hash=str(attempt["intent_hash"]),
        expected_contract_hash=str(attempt["contract_hash"]),
        result_state="critic_accepted",
        outcome={"accepted": True, "dialogue_source_kind_override": True},
        evidence=_dialogue_kind_override_evidence(envelope),
        commit_envelope=envelope,
    )

    reopened = ProjectDB(db.path)
    snapshot = reopened.analysis_candidate_acceptance_envelope(candidate_id)
    item = snapshot["critic_evidence"]["segments"][0]
    assert item["field_deltas"] == ["kind:dialogue->thought"]
    assert item["effective_accept"] is True
    assert item["host_source_kind_override"]["rule"] == (
        ANALYSIS_SOURCE_DIALOGUE_KIND_RULE
    )
    assert item["host_source_kind_override"]["unresolved_field_deltas"] == []

    batch = [
        {
            "segment_id": segment["segment_id"],
            "stable_id": segment["stable_id"],
            "text_sha256": segment["text_sha256"],
            "expected_status": "pending",
            "data": dict(segment["data"]),
        }
        for segment in snapshot["commit_envelope"]["segments"]
    ]
    reopened.update_analysis_batch_with_event(
        batch,
        low_confidence_threshold=0.65,
        event_level="info",
        event_code="ANALYSIS_DIRECTOR_CRITIC_ACCEPTED",
        event_message="source-locked explicit dialogue accepted",
        event_details={"candidate_hash": str(candidate["candidate_hash"])},
        **ANALYSIS_MODEL_COMMIT,
        analysis_candidate_id=candidate_id,
        analysis_policy_fingerprint=ANALYSIS_POLICY_FINGERPRINT,
        analysis_group_fingerprint=ANALYSIS_GROUP_FINGERPRINT,
        analysis_context_hash=ANALYSIS_CONTEXT_HASH,
    )

    committed = reopened.list_segments()[0]
    assert committed["status"] == "analyzed"
    assert committed["kind"] == "dialogue"
    assert committed["speaker"].endswith("::cậu bé")
    assert reopened.get_analysis_candidate(candidate_id)["state"] == "accepted"


def test_v32_dialogue_kind_override_leaves_speaker_dissent_rejected(
    tmp_path: Path,
) -> None:
    db, source_rows, envelope = _v32_seq43_dialogue_db(tmp_path)
    candidate = _allocate_analysis_candidate(db, source_rows, candidate=envelope)
    candidate_id = int(candidate["id"])
    attempt = db.reserve_analysis_critic_attempt(
        candidate_id,
        expected_state="allocated",
        max_attempts=2,
        intent={"candidate_hash": str(candidate["candidate_hash"])},
        contract=_accepted_critic_contract(envelope),
    )
    evidence = _dialogue_kind_override_evidence(
        envelope,
        corrected_speaker="NARRATOR",
    )
    item = evidence["segments"][0]
    assert item["host_source_kind_override"]["covered_field_deltas"] == [
        "kind:dialogue->thought"
    ]
    assert item["host_source_kind_override"]["unresolved_field_deltas"] == [
        "speaker:NPC_LOCAL::c00001::v32-source-unit::cậu bé->NARRATOR"
    ]
    assert item["effective_accept"] is False

    with pytest.raises(RuntimeError, match="exact delivery/confidence"):
        db.complete_analysis_critic_attempt(
            candidate_id,
            1,
            expected_intent_hash=str(attempt["intent_hash"]),
            expected_contract_hash=str(attempt["contract_hash"]),
            result_state="critic_accepted",
            outcome={"accepted": True},
            evidence=evidence,
            commit_envelope=envelope,
        )

    db.complete_analysis_critic_attempt(
        candidate_id,
        1,
        expected_intent_hash=str(attempt["intent_hash"]),
        expected_contract_hash=str(attempt["contract_hash"]),
        result_state="critic_rejected",
        outcome=_rejected_critic_outcome(evidence),
        evidence=evidence,
    )
    reopened = ProjectDB(db.path).get_analysis_candidate(candidate_id)
    assert reopened["state"] == "critic_rejected"


def test_v39_rejected_evidence_refuses_unbound_local_speaker_id(
    tmp_path: Path,
) -> None:
    db, source_rows, envelope = _v32_seq43_dialogue_db(tmp_path)
    candidate = _allocate_analysis_candidate(db, source_rows, candidate=envelope)
    candidate_id = int(candidate["id"])
    attempt = db.reserve_analysis_critic_attempt(
        candidate_id,
        expected_state="allocated",
        max_attempts=2,
        intent={"candidate_hash": str(candidate["candidate_hash"])},
        contract=_accepted_critic_contract(envelope),
    )
    evidence = _dialogue_kind_override_evidence(
        envelope,
        corrected_speaker="NPC_LOCAL::c00100::forged::phụ nữ áo đen",
    )

    with pytest.raises(RuntimeError, match="invalid speaker provenance"):
        db.complete_analysis_critic_attempt(
            candidate_id,
            1,
            expected_intent_hash=str(attempt["intent_hash"]),
            expected_contract_hash=str(attempt["contract_hash"]),
            result_state="critic_rejected",
            outcome=_rejected_critic_outcome(evidence),
            evidence=evidence,
        )


def test_v32_dialogue_candidate_requires_mandatory_kind_lock(tmp_path: Path) -> None:
    db, source_rows, envelope = _v32_seq43_dialogue_db(tmp_path)
    envelope["critic_rows"][0]["host_locked_fields"] = {}

    with pytest.raises(RuntimeError, match="dialogue source kind lock"):
        _allocate_analysis_candidate(db, source_rows, candidate=envelope)


@pytest.mark.parametrize(
    "mutation",
    ("missing", "forged_rule", "forged_partition"),
)
def test_v32_dialogue_kind_override_rejects_forged_evidence(
    tmp_path: Path,
    mutation: str,
) -> None:
    db, source_rows, envelope = _v32_seq43_dialogue_db(tmp_path)
    candidate = _allocate_analysis_candidate(db, source_rows, candidate=envelope)
    attempt = db.reserve_analysis_critic_attempt(
        int(candidate["id"]),
        expected_state="allocated",
        max_attempts=2,
        intent={"candidate_hash": str(candidate["candidate_hash"])},
        contract=_accepted_critic_contract(envelope),
    )
    evidence = _dialogue_kind_override_evidence(envelope)
    item = evidence["segments"][0]
    if mutation == "missing":
        del item["host_source_kind_override"]
    elif mutation == "forged_rule":
        item["host_source_kind_override"]["rule"] = (
            ANALYSIS_CONTEXT_SOURCE_KIND_RULE
        )
    else:
        item["host_source_kind_override"]["unresolved_field_deltas"] = [
            "speaker:forged->NARRATOR"
        ]

    with pytest.raises(RuntimeError, match="exact delivery/confidence"):
        db.complete_analysis_critic_attempt(
            int(candidate["id"]),
            1,
            expected_intent_hash=str(attempt["intent_hash"]),
            expected_contract_hash=str(attempt["contract_hash"]),
            result_state="critic_accepted",
            outcome={"accepted": True},
            evidence=evidence,
            commit_envelope=envelope,
        )


def test_sleep_paralysis_kind_only_override_survives_reopen_and_commit(
    tmp_path: Path,
) -> None:
    db, source_rows, envelope, clearance = _v29_v28_seq10_sleep_paralysis_db(
        tmp_path
    )
    candidate = _allocate_analysis_candidate(
        db,
        source_rows,
        candidate=envelope,
        deterministic_issues=clearance,
    )
    candidate_id = int(candidate["id"])
    attempt = db.reserve_analysis_critic_attempt(
        candidate_id,
        expected_state="allocated",
        max_attempts=2,
        intent={"candidate_hash": str(candidate["candidate_hash"])},
        contract=_accepted_critic_contract(envelope),
    )

    reopened_after_reserve = ProjectDB(db.path)
    assert reopened_after_reserve.get_analysis_candidate(candidate_id)["state"] == (
        "critic_in_flight"
    )
    reopened_after_reserve.complete_analysis_critic_attempt(
        candidate_id,
        1,
        expected_intent_hash=str(attempt["intent_hash"]),
        expected_contract_hash=str(attempt["contract_hash"]),
        result_state="critic_accepted",
        outcome={"accepted": True, "host_source_kind_override": True},
        evidence=_source_kind_override_evidence(envelope, clearance),
        commit_envelope=envelope,
    )

    reopened = ProjectDB(db.path)
    snapshot = reopened.analysis_candidate_acceptance_envelope(candidate_id)
    item = snapshot["critic_evidence"]["segments"][0]
    override = item["host_source_kind_override"]
    assert item["critic"]["kind"] == "thought"
    assert item["field_deltas"] == ["kind:narration->thought"]
    assert item["effective_accept"] is True
    assert override["covered_field_deltas"] == ["kind:narration->thought"]
    assert override["unresolved_field_deltas"] == []
    assert snapshot["commit_envelope"]["segments"][0]["data"]["kind"] == (
        "narration"
    )

    batch = [
        {
            "segment_id": segment["segment_id"],
            "stable_id": segment["stable_id"],
            "text_sha256": segment["text_sha256"],
            "expected_status": "pending",
            "data": dict(segment["data"]),
        }
        for segment in snapshot["commit_envelope"]["segments"]
    ]
    reopened.update_analysis_batch_with_event(
        batch,
        low_confidence_threshold=0.65,
        event_level="info",
        event_code="ANALYSIS_DIRECTOR_CRITIC_ACCEPTED",
        event_message="source-locked sleep paralysis kind accepted",
        event_details={"candidate_hash": str(candidate["candidate_hash"])},
        **ANALYSIS_MODEL_COMMIT,
        analysis_candidate_id=candidate_id,
        analysis_policy_fingerprint=ANALYSIS_POLICY_FINGERPRINT,
        analysis_group_fingerprint=ANALYSIS_GROUP_FINGERPRINT,
        analysis_context_hash=ANALYSIS_CONTEXT_HASH,
    )

    committed = reopened.list_segments()[0]
    assert committed["status"] == "analyzed"
    assert committed["kind"] == "narration"
    assert committed["emotion"] == "afraid"
    assert reopened.get_analysis_candidate(candidate_id)["state"] == "accepted"


def test_sleep_paralysis_kind_and_emotion_overrides_compose_on_reopen(
    tmp_path: Path,
) -> None:
    db, source_rows, envelope, clearance = _v29_v28_seq10_sleep_paralysis_db(
        tmp_path
    )
    candidate = _allocate_analysis_candidate(
        db,
        source_rows,
        candidate=envelope,
        deterministic_issues=clearance,
    )
    attempt = db.reserve_analysis_critic_attempt(
        int(candidate["id"]),
        expected_state="allocated",
        max_attempts=2,
        intent={"candidate_hash": str(candidate["candidate_hash"])},
        contract=_accepted_critic_contract(envelope),
    )
    evidence = _source_kind_override_evidence(
        envelope,
        clearance,
        corrected_emotion="neutral",
    )
    item = evidence["segments"][0]
    assert item["host_source_kind_override"]["unresolved_field_deltas"] == [
        "emotion:afraid->neutral"
    ]
    assert item["host_semantic_override"]["raw_field_deltas"] == [
        "kind:narration->thought",
        "emotion:afraid->neutral",
    ]
    assert item["effective_accept"] is True

    db.complete_analysis_critic_attempt(
        int(candidate["id"]),
        1,
        expected_intent_hash=str(attempt["intent_hash"]),
        expected_contract_hash=str(attempt["contract_hash"]),
        result_state="critic_accepted",
        outcome={"accepted": True, "composed_host_overrides": True},
        evidence=evidence,
        commit_envelope=envelope,
    )

    snapshot = ProjectDB(db.path).analysis_candidate_acceptance_envelope(
        int(candidate["id"])
    )
    stored_item = snapshot["critic_evidence"]["segments"][0]
    assert stored_item["critic"]["kind"] == "thought"
    assert stored_item["critic"]["emotion"] == "neutral"
    assert stored_item["effective_accept"] is True
    assert snapshot["commit_envelope"]["segments"][0]["data"]["kind"] == (
        "narration"
    )
    assert snapshot["commit_envelope"]["segments"][0]["data"]["emotion"] == (
        "afraid"
    )


def test_sleep_paralysis_composed_overrides_leave_delivery_deltas_unresolved(
    tmp_path: Path,
) -> None:
    db, source_rows, envelope, clearance = _v29_v28_seq10_sleep_paralysis_db(
        tmp_path
    )
    candidate = _allocate_analysis_candidate(
        db,
        source_rows,
        candidate=envelope,
        deterministic_issues=clearance,
    )
    attempt = db.reserve_analysis_critic_attempt(
        int(candidate["id"]),
        expected_state="allocated",
        max_attempts=2,
        intent={"candidate_hash": str(candidate["candidate_hash"])},
        contract=_accepted_critic_contract(envelope),
    )
    evidence = _source_kind_override_evidence(
        envelope,
        clearance,
        corrected_emotion="neutral",
        corrected_intensity=3,
        corrected_pace="fast",
    )
    item = evidence["segments"][0]
    assert item["host_source_kind_override"]["unresolved_field_deltas"] == [
        "emotion:afraid->neutral",
        "intensity:2->3",
        "pace:normal->fast",
    ]
    assert item["host_semantic_override"]["raw_field_deltas"] == item[
        "field_deltas"
    ]
    assert item["effective_accept"] is False

    with pytest.raises(RuntimeError, match="exact delivery/confidence"):
        db.complete_analysis_critic_attempt(
            int(candidate["id"]),
            1,
            expected_intent_hash=str(attempt["intent_hash"]),
            expected_contract_hash=str(attempt["contract_hash"]),
            result_state="critic_accepted",
            outcome={"accepted": True},
            evidence=evidence,
            commit_envelope=envelope,
        )

    db.complete_analysis_critic_attempt(
        int(candidate["id"]),
        1,
        expected_intent_hash=str(attempt["intent_hash"]),
        expected_contract_hash=str(attempt["contract_hash"]),
        result_state="critic_rejected",
        outcome=_rejected_critic_outcome(evidence),
        evidence=evidence,
    )

    assert ProjectDB(db.path).get_analysis_candidate(int(candidate["id"]))[
        "state"
    ] == "critic_rejected"


@pytest.mark.parametrize("mutation", ("missing_semantic", "forged_semantic_raw"))
def test_sleep_paralysis_composed_overrides_reject_tampering(
    tmp_path: Path,
    mutation: str,
) -> None:
    db, source_rows, envelope, clearance = _v29_v28_seq10_sleep_paralysis_db(
        tmp_path
    )
    candidate = _allocate_analysis_candidate(
        db,
        source_rows,
        candidate=envelope,
        deterministic_issues=clearance,
    )
    attempt = db.reserve_analysis_critic_attempt(
        int(candidate["id"]),
        expected_state="allocated",
        max_attempts=2,
        intent={"candidate_hash": str(candidate["candidate_hash"])},
        contract=_accepted_critic_contract(envelope),
    )
    evidence = _source_kind_override_evidence(
        envelope,
        clearance,
        corrected_emotion="neutral",
    )
    item = evidence["segments"][0]
    if mutation == "missing_semantic":
        del item["host_semantic_override"]
    else:
        item["host_semantic_override"]["raw_field_deltas"] = [
            "emotion:afraid->neutral"
        ]

    with pytest.raises(RuntimeError, match="exact delivery/confidence"):
        db.complete_analysis_critic_attempt(
            int(candidate["id"]),
            1,
            expected_intent_hash=str(attempt["intent_hash"]),
            expected_contract_hash=str(attempt["contract_hash"]),
            result_state="critic_accepted",
            outcome={"accepted": True},
            evidence=evidence,
            commit_envelope=envelope,
        )


def test_sleep_paralysis_resolved_singleton_cannot_store_rejected_state(
    tmp_path: Path,
) -> None:
    db, source_rows, envelope, clearance = _v29_v28_seq10_sleep_paralysis_db(
        tmp_path
    )
    candidate = _allocate_analysis_candidate(
        db,
        source_rows,
        candidate=envelope,
        deterministic_issues=clearance,
    )
    attempt = db.reserve_analysis_critic_attempt(
        int(candidate["id"]),
        expected_state="allocated",
        max_attempts=2,
        intent={"candidate_hash": str(candidate["candidate_hash"])},
        contract=_accepted_critic_contract(envelope),
    )

    with pytest.raises(RuntimeError, match="no unresolved segment"):
        db.complete_analysis_critic_attempt(
            int(candidate["id"]),
            1,
            expected_intent_hash=str(attempt["intent_hash"]),
            expected_contract_hash=str(attempt["contract_hash"]),
            result_state="critic_rejected",
            outcome={"accepted": False},
            evidence=_source_kind_override_evidence(envelope, clearance),
        )

    assert db.get_analysis_candidate(int(candidate["id"]))["state"] == (
        "critic_in_flight"
    )


def test_sleep_paralysis_resolved_row_can_share_rejected_multirow_batch(
    tmp_path: Path,
) -> None:
    db, source_rows = _analysis_batch_db(
        tmp_path,
        texts=(
            V28_SEQ10_SLEEP_PARALYSIS_TEXT,
            "Cậu chậm rãi nhìn quanh căn phòng xa lạ.",
        ),
    )
    envelope = _semantic_lock_envelope(
        source_rows,
        candidate_emotion="afraid",
    )
    envelope["critic_rows"][0]["host_locked_fields"] = {
        "kind": "narration",
        "emotion": "afraid",
    }
    clearance = _host_semantic_clearance(
        envelope,
        rule="narration_sleep_paralysis_helplessness",
        cue_class="sleep_paralysis_helplessness",
        allowed_emotions=["afraid"],
    )
    candidate = _allocate_analysis_candidate(
        db,
        source_rows,
        candidate=envelope,
        deterministic_issues=clearance,
    )
    attempt = db.reserve_analysis_critic_attempt(
        int(candidate["id"]),
        expected_state="allocated",
        max_attempts=2,
        intent={"candidate_hash": str(candidate["candidate_hash"])},
        contract=_accepted_critic_contract(envelope),
    )
    evidence = _source_kind_override_evidence(envelope, clearance)
    rejected_item = evidence["segments"][1]
    rejected_item["critic"].update(
        {
            "accept": False,
            "emotion": "sad",
            "rationale": "Critic không đồng ý cảm xúc của hàng thứ hai.",
        }
    )
    rejected_item["field_deltas"] = ["emotion:neutral->sad"]
    rejected_item["effective_accept"] = False

    db.complete_analysis_critic_attempt(
        int(candidate["id"]),
        1,
        expected_intent_hash=str(attempt["intent_hash"]),
        expected_contract_hash=str(attempt["contract_hash"]),
        result_state="critic_rejected",
        outcome=_rejected_critic_outcome(evidence),
        evidence=evidence,
    )

    reopened = ProjectDB(db.path).get_analysis_candidate(int(candidate["id"]))
    assert reopened["state"] == "critic_rejected"


def test_sleep_paralysis_kind_override_cannot_cross_dialogue_boundary(
    tmp_path: Path,
) -> None:
    db, source_rows, envelope, clearance = _v29_v28_seq10_sleep_paralysis_db(
        tmp_path
    )
    candidate = _allocate_analysis_candidate(
        db,
        source_rows,
        candidate=envelope,
        deterministic_issues=clearance,
    )
    attempt = db.reserve_analysis_critic_attempt(
        int(candidate["id"]),
        expected_state="allocated",
        max_attempts=2,
        intent={"candidate_hash": str(candidate["candidate_hash"])},
        contract=_accepted_critic_contract(envelope),
    )
    evidence = _source_kind_override_evidence(
        envelope,
        clearance,
        corrected_kind="dialogue",
    )

    with pytest.raises(RuntimeError, match="exact delivery/confidence"):
        db.complete_analysis_critic_attempt(
            int(candidate["id"]),
            1,
            expected_intent_hash=str(attempt["intent_hash"]),
            expected_contract_hash=str(attempt["contract_hash"]),
            result_state="critic_accepted",
            outcome={"accepted": True},
            evidence=evidence,
            commit_envelope=envelope,
        )

    item = evidence["segments"][0]
    item["effective_accept"] = False
    del item["host_source_kind_override"]
    db.complete_analysis_critic_attempt(
        int(candidate["id"]),
        1,
        expected_intent_hash=str(attempt["intent_hash"]),
        expected_contract_hash=str(attempt["contract_hash"]),
        result_state="critic_rejected",
        outcome=_rejected_critic_outcome(evidence),
        evidence=evidence,
    )

    assert ProjectDB(db.path).get_analysis_candidate(int(candidate["id"]))[
        "state"
    ] == "critic_rejected"


@pytest.mark.parametrize(
    ("mutation", "expected_error"),
    (
        ("missing", "exact delivery/confidence"),
        ("forged_rule", "exact delivery/confidence"),
        ("swapped_stable_id", "exact delivery/confidence"),
        ("forged_partition", "exact delivery/confidence"),
    ),
)
def test_sleep_paralysis_kind_override_rejects_forged_protocol(
    tmp_path: Path,
    mutation: str,
    expected_error: str,
) -> None:
    db, source_rows, envelope, clearance = _v29_v28_seq10_sleep_paralysis_db(
        tmp_path
    )
    candidate = _allocate_analysis_candidate(
        db,
        source_rows,
        candidate=envelope,
        deterministic_issues=clearance,
    )
    attempt = db.reserve_analysis_critic_attempt(
        int(candidate["id"]),
        expected_state="allocated",
        max_attempts=2,
        intent={"candidate_hash": str(candidate["candidate_hash"])},
        contract=_accepted_critic_contract(envelope),
    )
    evidence = _source_kind_override_evidence(envelope, clearance)
    item = evidence["segments"][0]
    override = item["host_source_kind_override"]
    if mutation == "missing":
        del item["host_source_kind_override"]
    elif mutation == "forged_rule":
        override["rule"] = "narration_stunned_blank_mind"
    elif mutation == "swapped_stable_id":
        override["stable_id"] = "c00001_s0000011_swapped"
    else:
        override["unresolved_field_deltas"] = ["emotion:afraid->neutral"]

    with pytest.raises(RuntimeError, match=expected_error):
        db.complete_analysis_critic_attempt(
            int(candidate["id"]),
            1,
            expected_intent_hash=str(attempt["intent_hash"]),
            expected_contract_hash=str(attempt["contract_hash"]),
            result_state="critic_accepted",
            outcome={"accepted": True},
            evidence=evidence,
            commit_envelope=envelope,
        )


def test_sleep_paralysis_kind_override_rejects_rehashed_tampering_on_reopen(
    tmp_path: Path,
) -> None:
    db, source_rows, envelope, clearance = _v29_v28_seq10_sleep_paralysis_db(
        tmp_path
    )
    candidate = _allocate_analysis_candidate(
        db,
        source_rows,
        candidate=envelope,
        deterministic_issues=clearance,
    )
    candidate_id = int(candidate["id"])
    attempt = db.reserve_analysis_critic_attempt(
        candidate_id,
        expected_state="allocated",
        max_attempts=2,
        intent={"candidate_hash": str(candidate["candidate_hash"])},
        contract=_accepted_critic_contract(envelope),
    )
    db.complete_analysis_critic_attempt(
        candidate_id,
        1,
        expected_intent_hash=str(attempt["intent_hash"]),
        expected_contract_hash=str(attempt["contract_hash"]),
        result_state="critic_accepted",
        outcome={"accepted": True},
        evidence=_source_kind_override_evidence(envelope, clearance),
        commit_envelope=envelope,
    )

    with db.connect() as conn:
        stored_attempt = conn.execute(
            "SELECT * FROM analysis_critic_attempts "
            "WHERE analysis_candidate_id=? AND attempt_number=1",
            (candidate_id,),
        ).fetchone()
        stored_candidate = conn.execute(
            "SELECT * FROM analysis_candidates WHERE id=?",
            (candidate_id,),
        ).fetchone()
        tampered = json.loads(str(stored_attempt["evidence_json"]))
        tampered["segments"][0]["host_source_kind_override"][
            "allowed_values"
        ] = ["thought"]
        evidence_json, evidence_hash = db._canonical_analysis_json(
            tampered,
            "tampered source-kind critic evidence",
        )
        _completion_json, completion_hash = db._canonical_analysis_json(
            {
                "commit_envelope_hash": stored_candidate["commit_envelope_hash"],
                "contract_hash": stored_attempt["contract_hash"],
                "evidence_hash": evidence_hash,
                "intent_hash": stored_attempt["intent_hash"],
                "outcome_hash": stored_attempt["outcome_hash"],
            },
            "tampered source-kind critic completion",
        )
        conn.execute(
            "UPDATE analysis_critic_attempts SET evidence_json=?,evidence_hash=?,"
            "completion_hash=? WHERE analysis_candidate_id=? AND attempt_number=1",
            (evidence_json, evidence_hash, completion_hash, candidate_id),
        )

    with pytest.raises(RuntimeError, match="exact delivery/confidence"):
        ProjectDB(db.path).analysis_candidate_acceptance_envelope(candidate_id)


def test_analysis_candidate_rejects_semantic_lock_allowed_set_tampering(
    tmp_path: Path,
) -> None:
    physical_text = (
        "Phổi đang bị bỏng rát. Ý thức của anh rất nhanh liền lịm dần."
    )
    db, source_rows = _analysis_batch_db(
        tmp_path,
        texts=(physical_text, "Cậu cố mở mắt."),
    )
    envelope = _semantic_lock_envelope(source_rows)
    clearance = _host_semantic_clearance(
        envelope,
        allowed_emotions=["afraid", "neutral"],
    )

    with pytest.raises(RuntimeError, match="semantic clearance is not source-bound"):
        _allocate_analysis_candidate(
            db,
            source_rows,
            candidate=envelope,
            deterministic_issues=clearance,
        )


@pytest.mark.parametrize(
    ("field", "value", "expected_error"),
    (
        ("policy_version", "host_affect_stale_v3", "candidate-bound"),
        ("checked_segment_count", 999, "candidate-bound"),
        ("matched_rule_count", 999, "evidence is not lock-bound"),
        ("evidence", [], "evidence is not lock-bound"),
    ),
)
def test_analysis_candidate_rejects_tampered_host_clearance_metadata(
    tmp_path: Path,
    field: str,
    value: object,
    expected_error: str,
) -> None:
    physical_text = (
        "Phổi đang bị bỏng rát. Ý thức của anh nhanh chóng trở nên mơ hồ."
    )
    db, source_rows = _analysis_batch_db(
        tmp_path,
        texts=(physical_text, "Nội dung tiếp theo."),
    )
    envelope = _semantic_lock_envelope(source_rows)
    clearance = _host_semantic_clearance(envelope)
    clearance["host_affect_clearance"][field] = value

    with pytest.raises(RuntimeError, match=expected_error):
        _allocate_analysis_candidate(
            db,
            source_rows,
            candidate=envelope,
            deterministic_issues=clearance,
        )


@pytest.mark.parametrize(
    ("text", "kind_hint", "rule", "cue_class", "allowed_emotions"),
    (
        (
            "Hôm nay trời đẹp và yên tĩnh.",
            "thought",
            "thought_self_preservation_mortality",
            "self_preservation_mortality",
            ["afraid"],
        ),
        (
            "Bác sĩ ghi lại một quan sát lâm sàng bình thường.",
            "narration",
            "respiratory_injury_with_consciousness_loss",
            "physical_collapse",
            ["afraid", "tired"],
        ),
        (
            "Cậu đi về phía ánh sáng trong im lặng.",
            "narration",
            "narration_desperate_exertion",
            "desperate_exertion",
            ["afraid", "sad", "tired"],
        ),
        (
            "Hạ Phong bình tĩnh đọc sách trong thư viện.",
            "narration",
            "narration_recalled_persistent_fear",
            "recalled_persistent_fear",
            ["afraid"],
        ),
        (
            "Hạ Phong bình tĩnh đọc sách trong thư viện.",
            "narration",
            "narration_stunned_blank_mind",
            "stunned_blank_mind",
            ["surprised"],
        ),
    ),
)
def test_analysis_candidate_rejects_semantic_lock_on_arbitrary_source(
    tmp_path: Path,
    text: str,
    kind_hint: str,
    rule: str,
    cue_class: str,
    allowed_emotions: list[str],
) -> None:
    db, source_rows = _analysis_batch_db(
        tmp_path,
        texts=(text, "Nội dung tiếp theo."),
        kind_hints=(kind_hint, "narration"),
    )
    envelope = _semantic_lock_envelope(source_rows)
    clearance = _host_semantic_clearance(
        envelope,
        rule=rule,
        cue_class=cue_class,
        allowed_emotions=allowed_emotions,
    )

    with pytest.raises(RuntimeError, match="semantic clearance is not source-bound"):
        _allocate_analysis_candidate(
            db,
            source_rows,
            candidate=envelope,
            deterministic_issues=clearance,
        )


@pytest.mark.parametrize(
    "mixed_text",
    (
        (
            "Phổi và yết hầu đang bị thiêu đốt, ý thức của anh liền mơ hồ, "
            "nhưng anh lại vui mừng rỡ."
        ),
        (
            "Phổi và yết hầu đang bị thiêu đốt. Ý thức của anh liền mơ hồ "
            "và anh sợ hãi cực độ."
        ),
    ),
)
def test_analysis_candidate_rejects_physical_lock_with_mixed_affect_source(
    tmp_path: Path,
    mixed_text: str,
) -> None:
    db, source_rows = _analysis_batch_db(
        tmp_path,
        texts=(mixed_text, "Nội dung tiếp theo."),
    )
    envelope = _semantic_lock_envelope(source_rows)
    clearance = _host_semantic_clearance(envelope)

    with pytest.raises(RuntimeError, match="semantic clearance is not source-bound"):
        _allocate_analysis_candidate(
            db,
            source_rows,
            candidate=envelope,
            deterministic_issues=clearance,
        )


def test_analysis_candidate_binds_adjacent_semantic_lock_to_mortality_source(
    tmp_path: Path,
) -> None:
    db, source_rows = _analysis_batch_db(
        tmp_path,
        texts=(
            "‘Không được… Không được ngủ… sẽ chết mất.’",
            "‘Tỉnh dậy, phải tỉnh dậy!’",
        ),
        kind_hints=("thought", "thought"),
    )
    with db.connect() as conn:
        conn.execute(
            "UPDATE segments SET paragraph_index=seq WHERE chapter_id=1"
        )
    source_rows = [dict(row) for row in db.list_segments()]
    envelope = _semantic_lock_envelope(source_rows, locked_index=1)
    envelope["segments"][0]["data"].update({"emotion": "afraid", "intensity": 2})
    _refresh_analysis_note(envelope, 0)
    envelope["critic_rows"][0]["candidate"].update(
        {"emotion": "afraid", "intensity": 2}
    )
    envelope["critic_rows"][0]["host_locked_fields"] = {"emotion": "afraid"}
    direct_clearance = _host_semantic_clearance(
        envelope,
        rule="thought_self_preservation_mortality",
        cue_class="self_preservation_mortality",
        allowed_emotions=["afraid"],
    )
    adjacent_clearance = _host_semantic_clearance(
        envelope,
        locked_index=1,
        rule="adjacent_thought_wake_self_rescue",
        cue_class="wake_self_rescue_after_mortality",
        allowed_emotions=["afraid"],
        related_index=0,
    )
    clearance = _merge_host_semantic_clearances(
        direct_clearance,
        adjacent_clearance,
    )

    candidate = _allocate_analysis_candidate(
        db,
        source_rows,
        candidate=envelope,
        deterministic_issues=clearance,
    )
    assert candidate["state"] == "allocated"

    forged = copy.deepcopy(clearance)
    forged["host_affect_clearance"]["semantic_locks"][1][
        "related_text_sha256"
    ] = "f" * 64
    forged["host_affect_clearance"]["evidence"][1][
        "related_text_sha256"
    ] = "f" * 64
    with pytest.raises(RuntimeError, match="related provenance"):
        _allocate_analysis_candidate(
            db,
            source_rows,
            context_hash="forged-related-context",
            candidate=envelope,
            deterministic_issues=forged,
        )


def test_adjacent_semantic_lock_rejects_related_text_only_tamper_on_reopen(
    tmp_path: Path,
) -> None:
    neutral_prefix = "Một khoảng trống vô nghĩa cứ lặp lại trong tâm trí. " * 14
    mortality_text = f"‘{neutral_prefix}Mình sẽ chết mất.’"
    db, source_rows = _analysis_batch_db(
        tmp_path,
        texts=(
            mortality_text,
            "‘Tỉnh dậy, phải tỉnh dậy!’",
        ),
        kind_hints=("thought", "thought"),
    )
    with db.connect() as conn:
        conn.execute("UPDATE segments SET paragraph_index=seq WHERE chapter_id=1")
    source_rows = [dict(row) for row in db.list_segments()]
    related_row, target_row = source_rows
    envelope = _semantic_lock_envelope([target_row], candidate_emotion="afraid")
    envelope["critic_rows"][0]["previous_text"] = mortality_text[-500:]
    clearance = _host_semantic_clearance(
        envelope,
        rule="adjacent_thought_wake_self_rescue",
        cue_class="wake_self_rescue_after_mortality",
        allowed_emotions=["afraid"],
    )
    semantic_lock = clearance["host_affect_clearance"]["semantic_locks"][0]
    semantic_evidence = clearance["host_affect_clearance"]["evidence"][0]
    for item in (semantic_lock, semantic_evidence):
        item["related_stable_id"] = str(related_row["stable_id"])
        item["related_text_sha256"] = str(related_row["text_sha256"])
    candidate = _allocate_analysis_candidate(
        db,
        [target_row],
        candidate=envelope,
        deterministic_issues=clearance,
    )
    tampered_text = mortality_text.replace("Một khoảng trống", "Một ký ức lạ", 1)
    assert tampered_text != mortality_text
    assert tampered_text[-500:] == mortality_text[-500:]
    with db.connect() as conn:
        conn.execute(
            "UPDATE segments SET text=? WHERE id=?",
            (tampered_text, int(related_row["id"])),
        )

    with pytest.raises(RuntimeError, match="related source text hash"):
        ProjectDB(db.path).get_analysis_candidate(int(candidate["id"]))


def test_analysis_candidate_rejects_adjacent_semantic_lock_without_mortality_cue(
    tmp_path: Path,
) -> None:
    db, source_rows = _analysis_batch_db(
        tmp_path,
        texts=("‘Mình nên nghỉ ngơi một chút.’", "‘Tỉnh dậy, phải tỉnh dậy!’"),
        kind_hints=("thought", "thought"),
    )
    with db.connect() as conn:
        conn.execute(
            "UPDATE segments SET paragraph_index=seq WHERE chapter_id=1"
        )
    source_rows = [dict(row) for row in db.list_segments()]
    envelope = _semantic_lock_envelope(source_rows, locked_index=1)
    clearance = _host_semantic_clearance(
        envelope,
        locked_index=1,
        rule="adjacent_thought_wake_self_rescue",
        cue_class="wake_self_rescue_after_mortality",
        allowed_emotions=["afraid"],
        related_index=0,
    )

    with pytest.raises(RuntimeError, match="related provenance"):
        _allocate_analysis_candidate(
            db,
            source_rows,
            candidate=envelope,
            deterministic_issues=clearance,
        )


@pytest.mark.parametrize(
    "text",
    (
        "‘Mình sẽ chết.’",
        "‘Tôi không còn nghĩ rằng mình sẽ chết mất.’",
        "‘Tôi đã từng nghĩ mình sẽ chết mất, nhưng giờ đã an toàn.’",
        "‘Tôi không thể nghĩ mình sẽ chết mất.’",
        (
            "‘Mình sẽ chết mất.’ Phổi đang bị bỏng rát và ý thức của mình "
            "nhanh chóng trở nên mơ hồ."
        ),
    ),
)
def test_analysis_candidate_rejects_mortality_lock_without_exact_active_afraid_source(
    tmp_path: Path,
    text: str,
) -> None:
    db, source_rows = _analysis_batch_db(
        tmp_path,
        texts=(text, "Nội dung tiếp theo."),
        kind_hints=("thought", "narration"),
    )
    envelope = _semantic_lock_envelope(source_rows)
    clearance = _host_semantic_clearance(
        envelope,
        rule="thought_self_preservation_mortality",
        cue_class="self_preservation_mortality",
        allowed_emotions=["afraid"],
    )

    with pytest.raises(RuntimeError, match="semantic clearance is not source-bound"):
        _allocate_analysis_candidate(
            db,
            source_rows,
            candidate=envelope,
            deterministic_issues=clearance,
        )


def test_analysis_candidate_rejects_semantic_lock_when_candidate_kind_changes(
    tmp_path: Path,
) -> None:
    db, source_rows = _analysis_batch_db(
        tmp_path,
        texts=("‘Mình sẽ chết mất.’", "Nội dung tiếp theo."),
        kind_hints=("thought", "narration"),
    )
    envelope = _semantic_lock_envelope(source_rows)
    envelope["segments"][0]["data"]["kind"] = "dialogue"
    _refresh_analysis_note(envelope, 0)
    envelope["critic_rows"][0]["candidate"]["kind"] = "dialogue"
    clearance = _host_semantic_clearance(
        envelope,
        rule="thought_self_preservation_mortality",
        cue_class="self_preservation_mortality",
        allowed_emotions=["afraid"],
    )

    with pytest.raises(RuntimeError, match="semantic clearance is not source-bound"):
        _allocate_analysis_candidate(
            db,
            source_rows,
            candidate=envelope,
            deterministic_issues=clearance,
        )


def test_analysis_candidate_rejects_non_immediate_adjacent_semantic_source(
    tmp_path: Path,
) -> None:
    db, source_rows = _analysis_batch_db(
        tmp_path,
        texts=(
            "‘Mình sẽ chết mất.’",
            "Một ý nghĩ khác xen vào.",
            "‘Tỉnh dậy, phải tỉnh dậy!’",
        ),
        kind_hints=("thought", "thought", "thought"),
    )
    with db.connect() as conn:
        conn.execute(
            "UPDATE segments SET paragraph_index=CASE seq WHEN 0 THEN 1 WHEN 1 THEN 9 "
            "ELSE 2 END WHERE chapter_id=1"
        )
    source_rows = [dict(row) for row in db.list_segments()]
    envelope = _semantic_lock_envelope(source_rows, locked_index=2)
    envelope["segments"][0]["data"].update({"emotion": "afraid", "intensity": 2})
    _refresh_analysis_note(envelope, 0)
    envelope["critic_rows"][0]["candidate"].update(
        {"emotion": "afraid", "intensity": 2}
    )
    envelope["critic_rows"][0]["host_locked_fields"] = {"emotion": "afraid"}
    direct_clearance = _host_semantic_clearance(
        envelope,
        rule="thought_self_preservation_mortality",
        cue_class="self_preservation_mortality",
        allowed_emotions=["afraid"],
    )
    adjacent_clearance = _host_semantic_clearance(
        envelope,
        locked_index=2,
        rule="adjacent_thought_wake_self_rescue",
        cue_class="wake_self_rescue_after_mortality",
        allowed_emotions=["afraid"],
        related_index=0,
    )
    clearance = _merge_host_semantic_clearances(
        direct_clearance,
        adjacent_clearance,
    )

    with pytest.raises(RuntimeError, match="related provenance"):
        _allocate_analysis_candidate(
            db,
            source_rows,
            candidate=envelope,
            deterministic_issues=clearance,
        )


def test_analysis_candidate_revalidates_semantic_lock_on_reopen(
    tmp_path: Path,
) -> None:
    physical_text = (
        "Phổi và yết hầu đang bị thiêu đốt. Ý thức của anh liền mất dần."
    )
    db, source_rows = _analysis_batch_db(
        tmp_path,
        texts=(physical_text, "Cậu cố mở mắt."),
    )
    envelope = _semantic_lock_envelope(source_rows)
    clearance = _host_semantic_clearance(envelope)
    candidate = _allocate_analysis_candidate(
        db,
        source_rows,
        candidate=envelope,
        deterministic_issues=clearance,
    )
    tampered = json.loads(str(candidate["deterministic_issue_json"]))
    tampered["host_affect_clearance"]["semantic_locks"][0][
        "allowed_emotions"
    ] = ["afraid", "neutral"]
    tampered["host_affect_clearance"]["evidence"][0][
        "allowed_emotions"
    ] = ["afraid", "neutral"]
    tampered_json = json.dumps(
        tampered,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    with db.connect() as conn:
        conn.execute(
            "UPDATE analysis_candidates SET deterministic_issue_json=?,"
            "deterministic_issue_hash=? WHERE id=?",
            (tampered_json, sha256_text(tampered_json), int(candidate["id"])),
        )

    with pytest.raises(RuntimeError, match="semantic clearance is not source-bound"):
        ProjectDB(db.path).get_analysis_candidate(int(candidate["id"]))


def test_analysis_candidate_keeps_structural_and_semantic_lock_namespaces_disjoint(
    tmp_path: Path,
) -> None:
    db, source_rows = _analysis_batch_db(
        tmp_path,
        texts=("Chương 01 - Khởi đầu", "Nội dung."),
    )
    envelope = _chapter_heading_envelope(source_rows)
    clearance = _chapter_heading_clearance(envelope)
    heading_segment = envelope["segments"][0]
    clearance["host_affect_clearance"]["semantic_locks"] = [
        {
            "policy_version": ANALYSIS_HOST_SEMANTIC_POLICY_VERSION,
            "stable_id": heading_segment["stable_id"],
            "text_sha256": heading_segment["text_sha256"],
            "source_role": "content",
            "field": "emotion",
            "rule": "respiratory_injury_with_consciousness_loss",
            "cue_class": "physical_collapse",
            "candidate_emotion": "neutral",
            "allowed_emotions": ["afraid", "tired"],
            "related_stable_id": "",
            "related_text_sha256": "",
        }
    ]
    clearance["host_affect_clearance"]["matched_rule_count"] = 1
    clearance["host_affect_clearance"]["evidence"] = [
        {
            "stable_id": heading_segment["stable_id"],
            "text_sha256": heading_segment["text_sha256"],
            "rule": "respiratory_injury_with_consciousness_loss",
            "cue_class": "physical_collapse",
            "candidate_emotion": "neutral",
            "allowed_emotions": ["afraid", "tired"],
            "outcome": "pass",
        }
    ]

    with pytest.raises(RuntimeError, match="semantic clearance differs from locked content"):
        _allocate_analysis_candidate(
            db,
            source_rows,
            candidate=envelope,
            deterministic_issues=clearance,
        )


def test_analysis_candidate_rejects_evidence_contract_not_reserved_for_request(
    tmp_path: Path,
) -> None:
    db, source_rows = _analysis_batch_db(tmp_path)
    envelope = _analysis_acceptance_envelope(source_rows)
    candidate = _allocate_analysis_candidate(db, source_rows, candidate=envelope)
    attempt = db.reserve_analysis_critic_attempt(
        int(candidate["id"]),
        expected_state="allocated",
        max_attempts=2,
        intent={"candidate_hash": str(candidate["candidate_hash"])},
        contract=_accepted_critic_contract(envelope),
    )
    evidence = _accepted_critic_evidence(envelope)
    evidence["critic_contract"] = {
        **evidence["critic_contract"],
        "seed": 999,
        "temperature": 0.9,
    }

    with pytest.raises(RuntimeError, match="differs from the reserved request contract"):
        db.complete_analysis_critic_attempt(
            int(candidate["id"]),
            1,
            expected_intent_hash=str(attempt["intent_hash"]),
            expected_contract_hash=str(attempt["contract_hash"]),
            result_state="critic_accepted",
            outcome={"accepted": True},
            evidence=evidence,
            commit_envelope=envelope,
        )


def test_analysis_candidate_resume_rejects_tampered_child_ledgers(tmp_path: Path) -> None:
    db, source_rows = _analysis_batch_db(tmp_path)
    candidate = _allocate_analysis_candidate(db, source_rows)
    candidate_id = int(candidate["id"])
    db.reserve_analysis_critic_attempt(
        candidate_id,
        expected_state="allocated",
        max_attempts=2,
        intent={"candidate_hash": str(candidate["candidate_hash"])},
        contract=_accepted_critic_contract(_analysis_acceptance_envelope(source_rows)),
    )

    with db.connect() as conn:
        conn.execute(
            "UPDATE analysis_critic_attempts SET intent_json=? "
            "WHERE analysis_candidate_id=? AND attempt_number=1",
            ('{"candidate_hash":"tampered"}', candidate_id),
        )
    with pytest.raises(RuntimeError, match="intent hash verification"):
        db.reserve_analysis_critic_attempt(
            candidate_id,
            expected_state="critic_in_flight",
            max_attempts=2,
            intent={"candidate_hash": str(candidate["candidate_hash"])},
            contract={
                **_accepted_critic_contract(_analysis_acceptance_envelope(source_rows)),
                "seed": 12,
            },
        )

    untouched = _allocate_analysis_candidate(
        db,
        source_rows,
        context_hash="second-context",
    )
    untouched_id = int(untouched["id"])
    with db.connect() as conn:
        conn.execute(
            "UPDATE analysis_candidate_generator_contracts SET generator_contract_json=? "
            "WHERE analysis_candidate_id=?",
            ('{"attempt":999}', untouched_id),
        )
    with pytest.raises(RuntimeError, match="generator contract hash verification"):
        db.list_analysis_candidate_generator_contracts(untouched_id)
    with pytest.raises(RuntimeError, match="generator contract hash verification"):
        db.find_resumable_analysis_candidate(
            policy_fingerprint=ANALYSIS_POLICY_FINGERPRINT,
            model_name=ANALYSIS_MODEL_NAME,
            model_digest=ANALYSIS_MODEL_DIGEST,
            group_fingerprint=ANALYSIS_GROUP_FINGERPRINT,
            context_hash="second-context",
        )


def test_analysis_candidate_resume_rejects_tampered_completed_critic_evidence(
    tmp_path: Path,
) -> None:
    db, source_rows = _analysis_batch_db(tmp_path)
    candidate = _allocate_analysis_candidate(db, source_rows)
    candidate_id = int(candidate["id"])
    attempt = db.reserve_analysis_critic_attempt(
        candidate_id,
        expected_state="allocated",
        max_attempts=2,
        intent={"candidate_hash": str(candidate["candidate_hash"])},
        contract=_accepted_critic_contract(_analysis_acceptance_envelope(source_rows)),
    )
    db.complete_analysis_critic_attempt(
        candidate_id,
        1,
        expected_intent_hash=str(attempt["intent_hash"]),
        expected_contract_hash=str(attempt["contract_hash"]),
        result_state="critic_invalid",
        outcome={"accepted": False},
        evidence={"reason": "schema"},
    )
    with db.connect() as conn:
        conn.execute(
            "UPDATE analysis_critic_attempts SET evidence_json=? "
            "WHERE analysis_candidate_id=? AND attempt_number=1",
            ('{"reason":"tampered"}', candidate_id),
        )

    with pytest.raises(RuntimeError, match="completion hash verification"):
        db.find_resumable_analysis_candidate(
            policy_fingerprint=ANALYSIS_POLICY_FINGERPRINT,
            model_name=ANALYSIS_MODEL_NAME,
            model_digest=ANALYSIS_MODEL_DIGEST,
            group_fingerprint=ANALYSIS_GROUP_FINGERPRINT,
            context_hash=ANALYSIS_CONTEXT_HASH,
        )


def test_analysis_candidate_resume_rejects_parent_child_state_mismatch(
    tmp_path: Path,
) -> None:
    db, source_rows = _analysis_batch_db(tmp_path)
    candidate = _allocate_analysis_candidate(db, source_rows)
    candidate_id = int(candidate["id"])
    attempt = db.reserve_analysis_critic_attempt(
        candidate_id,
        expected_state="allocated",
        max_attempts=2,
        intent={"candidate_hash": str(candidate["candidate_hash"])},
        contract=_accepted_critic_contract(_analysis_acceptance_envelope(source_rows)),
    )
    db.complete_analysis_critic_attempt(
        candidate_id,
        1,
        expected_intent_hash=str(attempt["intent_hash"]),
        expected_contract_hash=str(attempt["contract_hash"]),
        result_state="critic_invalid",
        outcome={"accepted": False},
        evidence={"reason": "schema"},
    )
    with db.connect() as conn:
        conn.execute(
            "UPDATE analysis_critic_attempts SET state='abandoned',outcome_json=NULL,"
            "outcome_hash=NULL,evidence_json=NULL,evidence_hash=NULL,completion_hash=NULL "
            "WHERE analysis_candidate_id=? AND attempt_number=1",
            (candidate_id,),
        )

    with pytest.raises(RuntimeError, match="final critic attempt is not completed"):
        db.find_resumable_analysis_candidate(
            policy_fingerprint=ANALYSIS_POLICY_FINGERPRINT,
            model_name=ANALYSIS_MODEL_NAME,
            model_digest=ANALYSIS_MODEL_DIGEST,
            group_fingerprint=ANALYSIS_GROUP_FINGERPRINT,
            context_hash=ANALYSIS_CONTEXT_HASH,
        )


def test_analysis_candidate_completion_rehashes_prior_critic_attempts(
    tmp_path: Path,
) -> None:
    db, source_rows = _analysis_batch_db(tmp_path)
    envelope = _analysis_acceptance_envelope(source_rows)
    candidate = _allocate_analysis_candidate(db, source_rows, candidate=envelope)
    candidate_id = int(candidate["id"])
    first_attempt = db.reserve_analysis_critic_attempt(
        candidate_id,
        expected_state="allocated",
        max_attempts=2,
        intent={"candidate_hash": str(candidate["candidate_hash"])},
        contract=_accepted_critic_contract(envelope),
    )
    db.complete_analysis_critic_attempt(
        candidate_id,
        1,
        expected_intent_hash=str(first_attempt["intent_hash"]),
        expected_contract_hash=str(first_attempt["contract_hash"]),
        result_state="critic_invalid",
        outcome={"accepted": False},
        evidence={"reason": "schema"},
    )
    second_attempt = db.reserve_analysis_critic_attempt(
        candidate_id,
        expected_state="critic_invalid",
        max_attempts=2,
        intent={"candidate_hash": str(candidate["candidate_hash"])},
        contract=_accepted_critic_contract(envelope),
    )
    with db.connect() as conn:
        conn.execute(
            "UPDATE analysis_critic_attempts SET evidence_json=? "
            "WHERE analysis_candidate_id=? AND attempt_number=1",
            ('{"reason":"tampered"}', candidate_id),
        )

    with pytest.raises(RuntimeError, match="completion hash verification"):
        db.complete_analysis_critic_attempt(
            candidate_id,
            2,
            expected_intent_hash=str(second_attempt["intent_hash"]),
            expected_contract_hash=str(second_attempt["contract_hash"]),
            result_state="critic_accepted",
            outcome={"accepted": True},
            evidence=_accepted_critic_evidence(envelope),
            commit_envelope=envelope,
        )

    with pytest.raises(RuntimeError, match="completion hash verification"):
        db.get_analysis_candidate(candidate_id)
    with db.connect() as conn:
        assert conn.execute(
            "SELECT state FROM analysis_candidates WHERE id=?",
            (candidate_id,),
        ).fetchone()["state"] == "critic_in_flight"


@pytest.mark.parametrize(
    ("tamper_target", "expected_error"),
    (
        ("prior_critic_attempt", "completion hash verification"),
        ("generator_contract", "generator contract hash verification"),
    ),
)
def test_analysis_candidate_commit_rehashes_complete_child_history(
    tmp_path: Path,
    tamper_target: str,
    expected_error: str,
) -> None:
    db, source_rows = _analysis_batch_db(tmp_path)
    envelope = _analysis_acceptance_envelope(source_rows)
    candidate = _allocate_analysis_candidate(db, source_rows, candidate=envelope)
    candidate_id = int(candidate["id"])
    first_attempt = db.reserve_analysis_critic_attempt(
        candidate_id,
        expected_state="allocated",
        max_attempts=2,
        intent={"candidate_hash": str(candidate["candidate_hash"])},
        contract=_accepted_critic_contract(envelope),
    )
    db.complete_analysis_critic_attempt(
        candidate_id,
        1,
        expected_intent_hash=str(first_attempt["intent_hash"]),
        expected_contract_hash=str(first_attempt["contract_hash"]),
        result_state="critic_invalid",
        outcome={"accepted": False},
        evidence={"reason": "schema"},
    )
    second_attempt = db.reserve_analysis_critic_attempt(
        candidate_id,
        expected_state="critic_invalid",
        max_attempts=2,
        intent={"candidate_hash": str(candidate["candidate_hash"])},
        contract=_accepted_critic_contract(envelope),
    )
    db.complete_analysis_critic_attempt(
        candidate_id,
        2,
        expected_intent_hash=str(second_attempt["intent_hash"]),
        expected_contract_hash=str(second_attempt["contract_hash"]),
        result_state="critic_accepted",
        outcome={"accepted": True},
        evidence=_accepted_critic_evidence(envelope),
        commit_envelope=envelope,
    )
    with db.connect() as conn:
        if tamper_target == "prior_critic_attempt":
            conn.execute(
                "UPDATE analysis_critic_attempts SET evidence_json=? "
                "WHERE analysis_candidate_id=? AND attempt_number=1",
                ('{"reason":"tampered"}', candidate_id),
            )
        else:
            conn.execute(
                "UPDATE analysis_candidate_generator_contracts "
                "SET generator_contract_json=? WHERE analysis_candidate_id=?",
                ('{"attempt":999}', candidate_id),
            )
    batch = [
        {
            "segment_id": segment["segment_id"],
            "stable_id": segment["stable_id"],
            "text_sha256": segment["text_sha256"],
            "expected_status": "pending",
            "data": dict(segment["data"]),
        }
        for segment in envelope["segments"]
    ]

    with pytest.raises(RuntimeError, match=expected_error):
        db.analysis_candidate_acceptance_envelope(candidate_id)
    with pytest.raises(RuntimeError, match=expected_error):
        db.update_analysis_batch_with_event(
            batch,
            low_confidence_threshold=0.65,
            event_level="info",
            event_code="ANALYSIS_DIRECTOR_CRITIC_ACCEPTED",
            event_message="must roll back",
            event_details={"candidate_hash": str(candidate["candidate_hash"])},
            **ANALYSIS_MODEL_COMMIT,
            analysis_candidate_id=candidate_id,
            analysis_policy_fingerprint=ANALYSIS_POLICY_FINGERPRINT,
            analysis_group_fingerprint=ANALYSIS_GROUP_FINGERPRINT,
            analysis_context_hash=ANALYSIS_CONTEXT_HASH,
        )

    assert {row["status"] for row in db.list_segments()} == {"pending"}
    with pytest.raises(RuntimeError, match=expected_error):
        db.get_analysis_candidate(candidate_id)
    with db.connect() as conn:
        assert conn.execute(
            "SELECT state FROM analysis_candidates WHERE id=?",
            (candidate_id,),
        ).fetchone()["state"] == "critic_accepted"


def test_analysis_candidate_identity_is_strict_and_terminal_candidates_do_not_reopen(
    tmp_path: Path,
) -> None:
    db, source_rows = _analysis_batch_db(tmp_path)
    first = _allocate_analysis_candidate(db, source_rows)
    isolated = _allocate_analysis_candidate(
        db,
        source_rows,
        context_hash="different-context",
    )
    terminal = db.mark_analysis_candidate_terminal(
        int(first["id"]),
        expected_state="allocated",
        reason="deterministic mismatch repeated",
    )
    terminal_replay = db.mark_analysis_candidate_terminal(
        int(first["id"]),
        expected_state="allocated",
        reason="deterministic mismatch repeated",
    )
    replay = _allocate_analysis_candidate(db, source_rows)

    assert int(isolated["id"]) != int(first["id"])
    assert terminal["state"] == terminal_replay["state"] == replay["state"] == (
        "terminal"
    )
    assert db.find_resumable_analysis_candidate(
        policy_fingerprint=ANALYSIS_POLICY_FINGERPRINT,
        model_name=ANALYSIS_MODEL_NAME,
        model_digest=ANALYSIS_MODEL_DIGEST,
        group_fingerprint=ANALYSIS_GROUP_FINGERPRINT,
        context_hash=ANALYSIS_CONTEXT_HASH,
    ) is None
    assert db.get_analysis_candidate_exact(
        policy_fingerprint=ANALYSIS_POLICY_FINGERPRINT,
        model_name=ANALYSIS_MODEL_NAME,
        model_digest=ANALYSIS_MODEL_DIGEST,
        group_fingerprint=ANALYSIS_GROUP_FINGERPRINT,
        context_hash="different-context",
        candidate_hash=str(isolated["candidate_hash"]),
    )["id"] == isolated["id"]


def test_analysis_candidate_scope_allows_only_one_actionable_candidate(tmp_path: Path) -> None:
    db, source_rows = _analysis_batch_db(tmp_path)
    first = _allocate_analysis_candidate(db, source_rows)
    changed = _analysis_acceptance_envelope(source_rows, emotion="angry")

    with pytest.raises(sqlite3.IntegrityError, match="UNIQUE constraint failed"):
        _allocate_analysis_candidate(db, source_rows, candidate=changed)

    superseded = db.mark_analysis_candidate_superseded(
        int(first["id"]),
        expected_state="allocated",
        reason="generator produced a different critic-visible candidate",
    )
    superseded_replay = db.mark_analysis_candidate_superseded(
        int(first["id"]),
        expected_state="allocated",
        reason="generator produced a different critic-visible candidate",
    )
    second = _allocate_analysis_candidate(db, source_rows, candidate=changed)
    assert superseded["state"] == superseded_replay["state"] == "superseded"
    assert int(second["id"]) != int(first["id"])


@pytest.mark.parametrize(
    ("first_state", "second_state"),
    (("terminal", "superseded"), ("superseded", "terminal")),
)
def test_v43_analysis_candidate_final_states_are_absorbing(
    tmp_path: Path,
    first_state: str,
    second_state: str,
) -> None:
    db, source_rows = _analysis_batch_db(tmp_path)
    candidate = _allocate_analysis_candidate(db, source_rows)
    candidate_id = int(candidate["id"])
    first_reason = f"fixed as {first_state}"
    if first_state == "terminal":
        db.mark_analysis_candidate_terminal(
            candidate_id,
            expected_state="allocated",
            reason=first_reason,
        )
    else:
        db.mark_analysis_candidate_superseded(
            candidate_id,
            expected_state="allocated",
            reason=first_reason,
        )

    with pytest.raises(RuntimeError, match="final states are absorbing"):
        if second_state == "terminal":
            db.mark_analysis_candidate_terminal(
                candidate_id,
                expected_state=first_state,
                reason="must not replace the final state",
            )
        else:
            db.mark_analysis_candidate_superseded(
                candidate_id,
                expected_state=first_state,
                reason="must not replace the final state",
            )

    stored = db.get_analysis_candidate(candidate_id)
    assert stored["state"] == first_state
    assert stored["terminal_reason"] == first_reason


def test_v39_terminal_transition_rejects_accepted_critic_history(
    tmp_path: Path,
) -> None:
    db, source_rows = _analysis_batch_db(tmp_path)
    envelope = _analysis_acceptance_envelope(source_rows)
    candidate = _allocate_analysis_candidate(db, source_rows, candidate=envelope)
    candidate_id = int(candidate["id"])
    attempt = db.reserve_analysis_critic_attempt(
        candidate_id,
        expected_state="allocated",
        max_attempts=2,
        intent={"candidate_hash": str(candidate["candidate_hash"])},
        contract=_accepted_critic_contract(envelope),
    )
    db.complete_analysis_critic_attempt(
        candidate_id,
        1,
        expected_intent_hash=str(attempt["intent_hash"]),
        expected_contract_hash=str(attempt["contract_hash"]),
        result_state="critic_accepted",
        outcome={"accepted": True},
        evidence=_accepted_critic_evidence(envelope),
        commit_envelope=envelope,
    )

    with pytest.raises(RuntimeError, match="invalid final critic outcome"):
        db.mark_analysis_candidate_terminal(
            candidate_id,
            expected_state="critic_accepted",
            reason="must not discard accepted evidence",
        )

    assert db.get_analysis_candidate(candidate_id)["state"] == "critic_accepted"


def test_v41_superseded_transition_rejects_accepted_critic_history(
    tmp_path: Path,
) -> None:
    db, source_rows = _analysis_batch_db(tmp_path)
    envelope = _analysis_acceptance_envelope(source_rows)
    candidate = _allocate_analysis_candidate(db, source_rows, candidate=envelope)
    candidate_id = int(candidate["id"])
    attempt = db.reserve_analysis_critic_attempt(
        candidate_id,
        expected_state="allocated",
        max_attempts=2,
        intent={"candidate_hash": str(candidate["candidate_hash"])},
        contract=_accepted_critic_contract(envelope),
    )
    db.complete_analysis_critic_attempt(
        candidate_id,
        1,
        expected_intent_hash=str(attempt["intent_hash"]),
        expected_contract_hash=str(attempt["contract_hash"]),
        result_state="critic_accepted",
        outcome={"accepted": True},
        evidence=_accepted_critic_evidence(envelope),
        commit_envelope=envelope,
    )

    with pytest.raises(RuntimeError, match="invalid final critic outcome"):
        db.mark_analysis_candidate_superseded(
            candidate_id,
            expected_state="critic_accepted",
            reason="must not discard accepted evidence",
        )

    assert db.get_analysis_candidate(candidate_id)["state"] == "critic_accepted"


def test_v41_allocated_candidate_rejects_existing_critic_history(
    tmp_path: Path,
) -> None:
    db, source_rows = _analysis_batch_db(tmp_path)
    envelope = _analysis_acceptance_envelope(source_rows)
    candidate = _allocate_analysis_candidate(db, source_rows, candidate=envelope)
    candidate_id = int(candidate["id"])
    db.reserve_analysis_critic_attempt(
        candidate_id,
        expected_state="allocated",
        max_attempts=2,
        intent={"candidate_hash": str(candidate["candidate_hash"])},
        contract=_accepted_critic_contract(envelope),
    )
    with db.connect() as conn:
        conn.execute(
            "UPDATE analysis_candidates SET state='allocated' WHERE id=?",
            (candidate_id,),
        )

    with pytest.raises(
        RuntimeError,
        match="Allocated analysis candidate has critic attempt history",
    ):
        db.get_analysis_candidate(candidate_id)


def test_v41_accepted_candidate_requires_critic_acceptance_history(
    tmp_path: Path,
) -> None:
    db, source_rows = _analysis_batch_db(tmp_path)
    envelope = _analysis_acceptance_envelope(source_rows)
    candidate = _allocate_analysis_candidate(db, source_rows, candidate=envelope)
    candidate_id = int(candidate["id"])
    attempt = db.reserve_analysis_critic_attempt(
        candidate_id,
        expected_state="allocated",
        max_attempts=2,
        intent={"candidate_hash": str(candidate["candidate_hash"])},
        contract=_accepted_critic_contract(envelope),
    )
    db.complete_analysis_critic_attempt(
        candidate_id,
        1,
        expected_intent_hash=str(attempt["intent_hash"]),
        expected_contract_hash=str(attempt["contract_hash"]),
        result_state="critic_invalid",
        outcome={"accepted": False},
        evidence={"reason": "schema"},
    )
    commit_envelope_json = json.dumps(
        envelope,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    with db.connect() as conn:
        conn.execute(
            "UPDATE analysis_candidates SET state='accepted',accepted_at=1.0,"
            "commit_envelope_json=?,commit_envelope_hash=? WHERE id=?",
            (commit_envelope_json, _canonical_hash(envelope), candidate_id),
        )

    with pytest.raises(
        RuntimeError,
        match="lacks matching completed critic acceptance",
    ):
        db.get_analysis_candidate(candidate_id)


@pytest.mark.parametrize(
    "surface",
    ("get_exact", "record_generator", "allocate_replay"),
)
def test_v43_exact_replay_surfaces_reject_missing_critic_history_before_mutation(
    tmp_path: Path,
    surface: str,
) -> None:
    db, source_rows = _analysis_batch_db(tmp_path)
    envelope = _analysis_acceptance_envelope(source_rows)
    candidate = _allocate_analysis_candidate(db, source_rows, candidate=envelope)
    candidate_id = int(candidate["id"])
    attempt = db.reserve_analysis_critic_attempt(
        candidate_id,
        expected_state="allocated",
        max_attempts=2,
        intent={"candidate_hash": str(candidate["candidate_hash"])},
        contract=_accepted_critic_contract(envelope),
    )
    db.complete_analysis_critic_attempt(
        candidate_id,
        1,
        expected_intent_hash=str(attempt["intent_hash"]),
        expected_contract_hash=str(attempt["contract_hash"]),
        result_state="critic_invalid",
        outcome={"accepted": False},
        evidence={"reason": "schema"},
    )
    with db.connect() as conn:
        generator_history_count = int(
            conn.execute(
                "SELECT COUNT(*) FROM analysis_candidate_generator_contracts "
                "WHERE analysis_candidate_id=?",
                (candidate_id,),
            ).fetchone()[0]
        )
        conn.execute(
            "DELETE FROM analysis_critic_attempts WHERE analysis_candidate_id=?",
            (candidate_id,),
        )

    replay_generator_contract = {"attempt": 2, "seed": 202}
    with pytest.raises(RuntimeError, match="history is not contiguous"):
        if surface == "get_exact":
            db.get_analysis_candidate_exact(
                policy_fingerprint=ANALYSIS_POLICY_FINGERPRINT,
                model_name=ANALYSIS_MODEL_NAME,
                model_digest=ANALYSIS_MODEL_DIGEST,
                group_fingerprint=ANALYSIS_GROUP_FINGERPRINT,
                context_hash=ANALYSIS_CONTEXT_HASH,
                candidate_hash=str(candidate["candidate_hash"]),
            )
        elif surface == "record_generator":
            db.record_analysis_candidate_generator_contract(
                candidate_id,
                replay_generator_contract,
            )
        else:
            _allocate_analysis_candidate(
                db,
                source_rows,
                candidate=envelope,
                generator_contract=replay_generator_contract,
            )

    with db.connect() as conn:
        stored = conn.execute(
            "SELECT state FROM analysis_candidates WHERE id=?",
            (candidate_id,),
        ).fetchone()
        assert stored["state"] == "critic_invalid"
        assert int(
            conn.execute(
                "SELECT COUNT(*) FROM analysis_candidate_generator_contracts "
                "WHERE analysis_candidate_id=?",
                (candidate_id,),
            ).fetchone()[0]
        ) == generator_history_count


def test_analysis_candidate_read_rehashes_durable_json(tmp_path: Path) -> None:
    db, source_rows = _analysis_batch_db(tmp_path)
    candidate = _allocate_analysis_candidate(db, source_rows)
    with db.connect() as conn:
        conn.execute(
            "UPDATE analysis_candidates SET envelope_hash='tampered' WHERE id=?",
            (int(candidate["id"]),),
        )

    with pytest.raises(RuntimeError, match="hash verification failed"):
        db.get_analysis_candidate(int(candidate["id"]))


def test_analysis_candidate_acceptance_binds_exact_durable_rows_and_rolls_back(
    tmp_path: Path,
) -> None:
    db, source_rows = _analysis_batch_db(tmp_path)
    envelope = _analysis_acceptance_envelope(source_rows)
    candidate = _allocate_analysis_candidate(db, source_rows, candidate=envelope)
    attempt = db.reserve_analysis_critic_attempt(
        int(candidate["id"]),
        expected_state="allocated",
        max_attempts=2,
        intent={"candidate_hash": str(candidate["candidate_hash"])},
        contract=_accepted_critic_contract(envelope),
    )
    db.complete_analysis_critic_attempt(
        int(candidate["id"]),
        1,
        expected_intent_hash=str(attempt["intent_hash"]),
        expected_contract_hash=str(attempt["contract_hash"]),
        result_state="critic_accepted",
        outcome={"accepted": True},
        evidence=_accepted_critic_evidence(envelope),
        commit_envelope=envelope,
    )
    batch = [
        {
            "segment_id": segment["segment_id"],
            "stable_id": segment["stable_id"],
            "text_sha256": segment["text_sha256"],
            "expected_status": "pending",
            "data": dict(segment["data"]),
        }
        for segment in envelope["segments"]
    ]
    batch[1]["data"]["emotion"] = "angry"

    with pytest.raises(RuntimeError, match="differs from the durable candidate"):
        db.update_analysis_batch_with_event(
            batch,
            low_confidence_threshold=0.65,
            event_level="info",
            event_code="ANALYSIS_DIRECTOR_CRITIC_ACCEPTED",
            event_message="must roll back",
            event_details={"candidate_hash": str(candidate["candidate_hash"])},
            **ANALYSIS_MODEL_COMMIT,
            analysis_candidate_id=int(candidate["id"]),
            analysis_policy_fingerprint=ANALYSIS_POLICY_FINGERPRINT,
            analysis_group_fingerprint=ANALYSIS_GROUP_FINGERPRINT,
            analysis_context_hash=ANALYSIS_CONTEXT_HASH,
        )

    assert {row["status"] for row in db.list_segments()} == {"pending"}
    assert db.get_analysis_candidate(int(candidate["id"]))["state"] == "critic_accepted"
    assert not any(
        row["code"] == "ANALYSIS_DIRECTOR_CRITIC_ACCEPTED"
        for row in db.list_events()
    )


def test_analysis_candidate_acceptance_commits_envelope_rows_and_pronunciations(
    tmp_path: Path,
) -> None:
    db, source_rows = _analysis_batch_db(tmp_path)
    envelope = _analysis_acceptance_envelope(source_rows)
    envelope["pronunciations"] = [
        {
            "surface": "Michael",
            "normalized_surface": "michael",
            "spoken_form": "Mai-cồ",
            "confidence": 0.91,
            "source": "analysis",
            "locked": False,
        }
    ]
    candidate = _allocate_analysis_candidate(db, source_rows, candidate=envelope)
    attempt = db.reserve_analysis_critic_attempt(
        int(candidate["id"]),
        expected_state="allocated",
        max_attempts=2,
        intent={"candidate_hash": str(candidate["candidate_hash"])},
        contract=_accepted_critic_contract(envelope),
    )
    db.complete_analysis_critic_attempt(
        int(candidate["id"]),
        1,
        expected_intent_hash=str(attempt["intent_hash"]),
        expected_contract_hash=str(attempt["contract_hash"]),
        result_state="critic_accepted",
        outcome={"accepted": True},
        evidence=_accepted_critic_evidence(envelope),
        commit_envelope=envelope,
    )
    batch = [
        {
            "segment_id": segment["segment_id"],
            "stable_id": segment["stable_id"],
            "text_sha256": segment["text_sha256"],
            "expected_status": "pending",
            "data": dict(segment["data"]),
        }
        for segment in envelope["segments"]
    ]

    db.update_analysis_batch_with_event(
        batch,
        low_confidence_threshold=0.65,
        event_level="info",
        event_code="ANALYSIS_DIRECTOR_CRITIC_ACCEPTED",
        event_message="accepted",
        event_details={"candidate_hash": str(candidate["candidate_hash"])},
        **ANALYSIS_MODEL_COMMIT,
        pronunciations=envelope["pronunciations"],
        analysis_candidate_id=int(candidate["id"]),
        analysis_policy_fingerprint=ANALYSIS_POLICY_FINGERPRINT,
        analysis_group_fingerprint=ANALYSIS_GROUP_FINGERPRINT,
        analysis_context_hash=ANALYSIS_CONTEXT_HASH,
    )

    assert {row["status"] for row in db.list_segments()} == {"analyzed"}
    assert db.get_analysis_candidate(int(candidate["id"]))["state"] == "accepted"
    assert db.list_pronunciations()[0]["normalized_surface"] == "michael"
    event_details = json.loads(db.list_events()[-1]["details_json"])
    assert event_details["analysis_candidate_id"] == int(candidate["id"])
    assert event_details["critic_completion_hash"]
    assert event_details["critic_evidence_hash"]
    assert event_details["commit_envelope_hash"]


def test_analysis_candidate_acceptance_transition_rolls_back_with_event_trigger(
    tmp_path: Path,
) -> None:
    db, source_rows = _analysis_batch_db(tmp_path)
    envelope = _analysis_acceptance_envelope(source_rows)
    candidate = _allocate_analysis_candidate(db, source_rows, candidate=envelope)
    attempt = db.reserve_analysis_critic_attempt(
        int(candidate["id"]),
        expected_state="allocated",
        max_attempts=2,
        intent={"candidate_hash": str(candidate["candidate_hash"])},
        contract=_accepted_critic_contract(envelope),
    )
    db.complete_analysis_critic_attempt(
        int(candidate["id"]),
        1,
        expected_intent_hash=str(attempt["intent_hash"]),
        expected_contract_hash=str(attempt["contract_hash"]),
        result_state="critic_accepted",
        outcome={"accepted": True},
        evidence=_accepted_critic_evidence(envelope),
        commit_envelope=envelope,
    )
    with db.connect() as conn:
        conn.execute(
            """
            CREATE TRIGGER reject_candidate_accept_event
            BEFORE INSERT ON runtime_events
            WHEN NEW.code='ANALYSIS_DIRECTOR_CRITIC_ACCEPTED'
            BEGIN SELECT RAISE(ABORT, 'candidate accept crash'); END
            """
        )
    batch = [
        {
            "segment_id": segment["segment_id"],
            "stable_id": segment["stable_id"],
            "text_sha256": segment["text_sha256"],
            "expected_status": "pending",
            "data": dict(segment["data"]),
        }
        for segment in envelope["segments"]
    ]

    with pytest.raises(sqlite3.IntegrityError, match="candidate accept crash"):
        db.update_analysis_batch_with_event(
            batch,
            low_confidence_threshold=0.65,
            event_level="info",
            event_code="ANALYSIS_DIRECTOR_CRITIC_ACCEPTED",
            event_message="accepted",
            event_details={"candidate_hash": str(candidate["candidate_hash"])},
            **ANALYSIS_MODEL_COMMIT,
            analysis_candidate_id=int(candidate["id"]),
            analysis_policy_fingerprint=ANALYSIS_POLICY_FINGERPRINT,
            analysis_group_fingerprint=ANALYSIS_GROUP_FINGERPRINT,
            analysis_context_hash=ANALYSIS_CONTEXT_HASH,
        )

    assert {row["status"] for row in db.list_segments()} == {"pending"}
    assert db.get_analysis_candidate(int(candidate["id"]))["state"] == "critic_accepted"


def test_analysis_director_batch_trigger_failure_rolls_back_every_row_and_event(
    tmp_path: Path,
) -> None:
    db, source_rows = _analysis_batch_db(tmp_path)
    with db.connect() as conn:
        conn.execute(
            """
            CREATE TRIGGER reject_second_analysis
            BEFORE UPDATE ON segments
            WHEN NEW.stable_id='c1s2'
            BEGIN
                SELECT RAISE(ABORT, 'reject second analysis');
            END
            """
        )
    batch = [
        {
            "segment_id": row["id"],
            "stable_id": row["stable_id"],
            "text_sha256": row["text_sha256"],
            "expected_status": "pending",
            "data": _canonical_analysis_data(),
        }
        for row in source_rows
    ]

    with pytest.raises(sqlite3.IntegrityError, match="reject second analysis"):
        db.update_analysis_batch_with_event(
            batch,
            low_confidence_threshold=0.65,
            event_level="info",
            event_code="ANALYSIS_DIRECTOR_CRITIC_ACCEPTED",
            event_message="must roll back",
            event_details={"candidate_hash": "candidate"},
            **ANALYSIS_MODEL_COMMIT,
        )

    assert {row["status"] for row in db.list_segments()} == {"pending"}
    assert not any(
        row["code"] == "ANALYSIS_DIRECTOR_CRITIC_ACCEPTED"
        for row in db.list_events()
    )


def test_analysis_director_batch_cas_rejects_stale_source_without_partial_update(
    tmp_path: Path,
) -> None:
    db, source_rows = _analysis_batch_db(tmp_path)
    batch = [
        {
            "segment_id": row["id"],
            "stable_id": row["stable_id"],
            "text_sha256": "stale" if index == 1 else row["text_sha256"],
            "expected_status": "pending",
            "data": _canonical_analysis_data(),
        }
        for index, row in enumerate(source_rows)
    ]

    with pytest.raises(RuntimeError, match="CAS failed"):
        db.update_analysis_batch_with_event(
            batch,
            low_confidence_threshold=0.65,
            event_level="info",
            event_code="ANALYSIS_DIRECTOR_CRITIC_ACCEPTED",
            event_message="must roll back",
            event_details={"candidate_hash": "candidate"},
            **ANALYSIS_MODEL_COMMIT,
        )

    assert {row["status"] for row in db.list_segments()} == {"pending"}
    assert not any(
        row["code"] == "ANALYSIS_DIRECTOR_CRITIC_ACCEPTED"
        for row in db.list_events()
    )


def test_analysis_director_event_failure_rolls_back_pronunciation_and_segments(
    tmp_path: Path,
) -> None:
    db, source_rows = _analysis_batch_db(tmp_path)
    with db.connect() as conn:
        conn.execute(
            """
            CREATE TRIGGER reject_director_accept_event
            BEFORE INSERT ON runtime_events
            WHEN NEW.code='ANALYSIS_DIRECTOR_CRITIC_ACCEPTED'
            BEGIN
                SELECT RAISE(ABORT, 'reject director event');
            END
            """
        )
    batch = [
        {
            "segment_id": row["id"],
            "stable_id": row["stable_id"],
            "text_sha256": row["text_sha256"],
            "expected_status": "pending",
            "data": _canonical_analysis_data(),
        }
        for row in source_rows
    ]

    with pytest.raises(sqlite3.IntegrityError, match="reject director event"):
        db.update_analysis_batch_with_event(
            batch,
            low_confidence_threshold=0.65,
            event_level="info",
            event_code="ANALYSIS_DIRECTOR_CRITIC_ACCEPTED",
            event_message="must roll back",
            event_details={"candidate_hash": "candidate"},
            **ANALYSIS_MODEL_COMMIT,
            pronunciations=[{
                "surface": "Michael",
                "normalized_surface": "michael",
                "spoken_form": "Mai-cồ",
                "confidence": 0.91,
            }],
        )

    assert {row["status"] for row in db.list_segments()} == {"pending"}
    assert db.list_pronunciations() == []


def test_analysis_model_lock_is_idempotent_durable_and_rejects_drift(tmp_path: Path) -> None:
    db, _source_rows = _analysis_batch_db(tmp_path, lock_model=False)

    assert db.analysis_model_lock() is None
    db.lock_analysis_model("qwen3:8b", "sha256:first")
    first = db.analysis_model_lock()
    db.lock_analysis_model("qwen3:8b", "sha256:first")
    reopened = ProjectDB(db.path)

    assert reopened.analysis_model_lock() == first
    with pytest.raises(RuntimeError, match="differs from the model name/digest"):
        reopened.lock_analysis_model("qwen3:8b", "sha256:second")
    with pytest.raises(RuntimeError, match="differs from the model name/digest"):
        reopened.lock_analysis_model("qwen3:4b", "sha256:first")


def test_director_commit_rejects_missing_model_lock_without_partial_state(
    tmp_path: Path,
) -> None:
    db, source_rows = _analysis_batch_db(tmp_path)
    with db.connect() as conn:
        conn.execute(
            "UPDATE book SET analysis_model_name=NULL,analysis_model_digest=NULL,"
            "analysis_model_locked_at=NULL WHERE id=1"
        )
    batch = [
        {
            "segment_id": row["id"],
            "stable_id": row["stable_id"],
            "text_sha256": row["text_sha256"],
            "expected_status": "pending",
            "data": {"confidence": 0.9},
        }
        for row in source_rows
    ]

    with pytest.raises(RuntimeError, match="model lock changed"):
        db.update_analysis_batch_with_event(
            batch,
            low_confidence_threshold=0.65,
            event_level="info",
            event_code="ANALYSIS_DIRECTOR_CRITIC_ACCEPTED",
            event_message="must not commit",
            event_details={"candidate_hash": "candidate"},
            **ANALYSIS_MODEL_COMMIT,
            pronunciations=[{
                "surface": "Michael",
                "normalized_surface": "michael",
                "spoken_form": "Mai-cồ",
                "confidence": 0.91,
            }],
        )

    assert {row["status"] for row in db.list_segments()} == {"pending"}
    assert db.list_pronunciations() == []
    assert not any(
        row["code"] == "ANALYSIS_DIRECTOR_CRITIC_ACCEPTED"
        for row in db.list_events()
    )


def test_schema_v6_adds_empty_analysis_model_lock_columns(tmp_path: Path) -> None:
    path = tmp_path / "legacy-v6.sqlite3"
    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            CREATE TABLE book (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                title TEXT NOT NULL,
                project_root TEXT NOT NULL,
                settings_hash TEXT NOT NULL,
                settings_json TEXT NOT NULL,
                status TEXT NOT NULL,
                stage TEXT NOT NULL DEFAULT 'created',
                input_manifest_hash TEXT NOT NULL,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL,
                last_error TEXT,
                run_generation INTEGER NOT NULL DEFAULT 0,
                casting_finalized INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        conn.execute(
            """
            INSERT INTO book(
                id,title,project_root,settings_hash,settings_json,status,stage,
                input_manifest_hash,created_at,updated_at
            ) VALUES(1,'Legacy',?,'settings','{}','created','created','manifest',1,1)
            """,
            (str(tmp_path),),
        )
        conn.execute("PRAGMA user_version=6")

    migrated = ProjectDB(path)
    backup = path.with_name(f"{path.name}.pre-v6-to-v{SCHEMA_VERSION}.bak")
    with migrated.connect() as conn:
        columns = {str(row[1]) for row in conn.execute("PRAGMA table_info(book)")}

    assert backup.is_file()
    assert {
        "analysis_model_name",
        "analysis_model_digest",
        "analysis_model_locked_at",
    } <= columns
    assert migrated.analysis_model_lock() is None


def test_schema_v7_migrates_durable_analysis_candidate_ledger(tmp_path: Path) -> None:
    path = tmp_path / "legacy-v7.sqlite3"
    ProjectDB(path)
    with sqlite3.connect(path) as conn:
        conn.execute("DROP TABLE analysis_critic_attempts")
        conn.execute("DROP TABLE analysis_candidate_generator_contracts")
        conn.execute("DROP TABLE analysis_candidates")
        conn.execute("PRAGMA user_version=7")

    migrated = ProjectDB(path)
    backup = path.with_name(f"{path.name}.pre-v7-to-v{SCHEMA_VERSION}.bak")
    with migrated.connect() as conn:
        version = int(conn.execute("PRAGMA user_version").fetchone()[0])
        tables = {
            str(row[0])
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        candidate_columns = {
            str(row[1])
            for row in conn.execute("PRAGMA table_info(analysis_candidates)")
        }

    assert version == SCHEMA_VERSION
    assert backup.is_file()
    assert {
        "analysis_candidates",
        "analysis_candidate_generator_contracts",
        "analysis_critic_attempts",
    } <= tables
    assert {
        "policy_fingerprint",
        "model_digest",
        "group_fingerprint",
        "context_hash",
        "candidate_json",
        "critic_attempt_count",
    } <= candidate_columns


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


def test_short_ceiling_frame_cap_survives_interruption_and_reopen(tmp_path: Path) -> None:
    db, segment_id = _segment_db(tmp_path)
    db.set_segment_generation_frame_cap(segment_id, 12)
    db.mark_generating(segment_id, seed=17)

    reopened = ProjectDB(db.path)
    assert reopened.reset_in_progress_segments() == 1
    recovered = reopened.get_segment(segment_id)

    assert recovered["generation_frame_cap"] == 12
    reopened.mark_verified(segment_id)
    assert reopened.get_segment(segment_id)["generation_frame_cap"] is None


def test_clarity_generation_checkpoint_survives_interruption_until_explicit_reset(
    tmp_path: Path,
) -> None:
    db, segment_id = _segment_db(tmp_path)
    with pytest.raises(ValueError, match="clarity generation requires"):
        db.mark_generating(
            segment_id,
            seed=16,
            delivery_mode=GENERATION_DELIVERY_CLARITY,
            policy_hash="policy-v1",
        )
    db.mark_generating(
        segment_id,
        seed=17,
        delivery_mode=GENERATION_DELIVERY_CLARITY,
        repair_round=0,
        policy_hash="policy-v1",
    )

    reopened = ProjectDB(db.path)
    assert reopened.reset_in_progress_segments() == 1
    recovered = reopened.get_segment(segment_id)
    assert recovered["status"] == "pending"
    assert recovered["generation_delivery_mode"] == GENERATION_DELIVERY_CLARITY
    assert recovered["generation_repair_round"] == 0
    assert recovered["generation_policy_hash"] == "policy-v1"

    reopened.reset_segment_pending(segment_id, "explicit clean regeneration")
    reset = reopened.get_segment(segment_id)
    assert reset["generation_delivery_mode"] == GENERATION_DELIVERY_PRIMARY
    assert reset["generation_repair_round"] is None
    assert reset["generation_policy_hash"] is None


def test_audio_reset_keeps_locked_analysis_and_casting(tmp_path: Path) -> None:
    db, segment_id = _segment_db(tmp_path)
    db.update_analysis(
        segment_id,
        _canonical_analysis_data(
            kind="dialogue",
            speaker="LUCIEN",
            gender="male",
            age="adult",
            confidence=1.0,
        ),
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


def test_legacy_v0_migration_uses_a_versioned_backup_and_is_idempotent(tmp_path: Path) -> None:
    path = tmp_path / "project.sqlite3"
    legacy = ProjectDB(path)
    legacy.initialize_book(
        title="Legacy",
        project_root=tmp_path,
        settings={"locked": True},
        settings_hash="legacy-settings",
        input_manifest_hash="legacy-manifest",
    )
    chapter_id = legacy.ensure_chapters(
        [
            {
                "chapter_index": 1,
                "title": "Chapter",
                "input_path": tmp_path / "chapter.txt",
                "input_sha256": "source",
                "input_size": 123,
                "output_mp3": tmp_path / "chapter.mp3",
            }
        ]
    )[0]
    legacy.finalize_casting()
    legacy.update_book(status="synthesizing", stage="chapter_synthesis")
    legacy.update_chapter_status(chapter_id, "completed")
    before = dict(legacy.book())
    before_chapter = dict(legacy.list_chapters()[0])
    with legacy.connect() as conn:
        conn.execute("DROP TABLE quality_checks")
        conn.execute("DROP TABLE quality_policies")
        conn.execute("PRAGMA user_version=0")

    stale_backup = path.with_suffix(path.suffix + ".pre-migration.bak")
    with closing(sqlite3.connect(stale_backup)) as conn:
        conn.execute("CREATE TABLE stale_backup(marker TEXT NOT NULL)")
        conn.execute("INSERT INTO stale_backup(marker) VALUES('old')")
        conn.commit()

    migrated = ProjectDB(path)
    versioned_backup = path.with_name(
        f"{path.name}.pre-v0-to-v{SCHEMA_VERSION}.bak"
    )

    assert versioned_backup.is_file()
    assert versioned_backup != stale_backup
    with migrated.connect() as conn:
        assert int(conn.execute("PRAGMA user_version").fetchone()[0]) == SCHEMA_VERSION
        assert conn.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='quality_policies'"
        ).fetchone()[0] == 1
        assert conn.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='quality_checks'"
        ).fetchone()[0] == 1
    with closing(sqlite3.connect(versioned_backup)) as conn:
        conn.row_factory = sqlite3.Row
        backup_book = dict(conn.execute("SELECT * FROM book WHERE id=1").fetchone())
        backup_chapter = dict(conn.execute("SELECT * FROM chapters WHERE id=?", (chapter_id,)).fetchone())
        assert int(conn.execute("PRAGMA user_version").fetchone()[0]) == 0

    assert dict(migrated.book()) == before
    assert dict(migrated.list_chapters()[0]) == before_chapter
    assert backup_book == before
    assert backup_chapter == before_chapter
    backup_mtime = versioned_backup.stat().st_mtime_ns

    reopened = ProjectDB(path)

    assert reopened.current_quality_policy() is None
    assert versioned_backup.stat().st_mtime_ns == backup_mtime
    assert dict(reopened.book()) == before
    assert dict(reopened.list_chapters()[0]) == before_chapter


def test_schema_v2_without_generation_frame_cap_migrates_to_current(tmp_path: Path) -> None:
    path = tmp_path / "project.sqlite3"
    legacy = ProjectDB(path)
    with legacy.connect() as conn:
        conn.execute("ALTER TABLE segments DROP COLUMN generation_frame_cap")
        conn.execute("PRAGMA user_version=2")
        columns = {str(row[1]) for row in conn.execute("PRAGMA table_info(segments)")}
    assert "generation_frame_cap" not in columns

    migrated = ProjectDB(path)
    backup = path.with_name(f"{path.name}.pre-v2-to-v{SCHEMA_VERSION}.bak")
    with migrated.connect() as conn:
        columns = {str(row[1]) for row in conn.execute("PRAGMA table_info(segments)")}
        version = int(conn.execute("PRAGMA user_version").fetchone()[0])
    assert backup.is_file()
    with closing(sqlite3.connect(backup)) as conn:
        backup_columns = {
            str(row[1]) for row in conn.execute("PRAGMA table_info(segments)")
        }
        backup_version = int(conn.execute("PRAGMA user_version").fetchone()[0])

    assert "generation_frame_cap" in columns
    assert version == SCHEMA_VERSION
    assert "generation_frame_cap" not in backup_columns
    assert backup_version == 2


def test_schema_v3_adds_durable_generation_context(tmp_path: Path) -> None:
    path = tmp_path / "project.sqlite3"
    legacy = ProjectDB(path)
    context_columns = {
        "generation_delivery_mode",
        "generation_repair_round",
        "generation_policy_hash",
    }
    with legacy.connect() as conn:
        for column in reversed(tuple(context_columns)):
            conn.execute(f"ALTER TABLE segments DROP COLUMN {column}")
        conn.execute("PRAGMA user_version=3")
        columns = {str(row[1]) for row in conn.execute("PRAGMA table_info(segments)")}
    assert context_columns.isdisjoint(columns)

    migrated = ProjectDB(path)
    backup = path.with_name(f"{path.name}.pre-v3-to-v{SCHEMA_VERSION}.bak")
    with migrated.connect() as conn:
        columns = {str(row[1]) for row in conn.execute("PRAGMA table_info(segments)")}
        version = int(conn.execute("PRAGMA user_version").fetchone()[0])
    with closing(sqlite3.connect(backup)) as conn:
        backup_columns = {
            str(row[1]) for row in conn.execute("PRAGMA table_info(segments)")
        }
        backup_version = int(conn.execute("PRAGMA user_version").fetchone()[0])

    assert backup.is_file()
    assert context_columns.issubset(columns)
    assert version == SCHEMA_VERSION
    assert context_columns.isdisjoint(backup_columns)
    assert backup_version == 3


def test_chapter_artifact_requires_passing_metadata_for_the_current_quality_policy(
    tmp_path: Path,
) -> None:
    db, _segment_id = _segment_db(tmp_path)
    chapter = db.list_chapters()[0]
    chapter_id = int(chapter["id"])
    chapter_index = int(chapter["chapter_index"])
    output = Path(str(chapter["output_mp3"]))
    output.write_bytes(b"ID3" + b"x" * 5000)
    db.set_current_quality_policy(
        policy_hash="policy-v1",
        policy_version=1,
        policy={"profile": "audiobook"},
    )
    db.register_artifact(
        artifact_key=f"chapter_mp3:{chapter_index}",
        kind="chapter_mp3",
        path=output,
        sha256="a" * 64,
        verified=True,
        metadata={"chapter_id": chapter_id},
    )

    assert db.chapter_artifact_is_current_qa_verified(chapter_index) is False

    quality = db.quality_metadata_for_current_policy()
    db.register_artifact(
        artifact_key=f"chapter_mp3:{chapter_index}",
        kind="chapter_mp3",
        path=output,
        sha256="a" * 64,
        verified=True,
        metadata={"chapter_id": chapter_id, "quality": quality},
    )

    assert db.chapter_artifact_is_current_qa_verified(chapter_index) is False

    db.record_quality_check(
        scope=QUALITY_SCOPE_CHAPTER,
        stage=CHAPTER_POST_ENCODE_QUALITY_STAGE,
        artifact_sha256="b" * 64,
        policy_hash=str(quality["policy_hash"]),
        policy_version=int(quality["policy_version"]),
        verdict=QUALITY_VERDICT_PASS,
        chapter_id=chapter_id,
    )

    assert db.chapter_artifact_is_current_qa_verified(chapter_index) is False

    check_id = db.record_quality_check(
        scope=QUALITY_SCOPE_CHAPTER,
        stage=CHAPTER_POST_ENCODE_QUALITY_STAGE,
        artifact_sha256="a" * 64,
        policy_hash=str(quality["policy_hash"]),
        policy_version=int(quality["policy_version"]),
        verdict=QUALITY_VERDICT_PASS,
        chapter_id=chapter_id,
        metrics={"loudness_lufs": -18.0},
    )
    db.register_artifact(
        artifact_key=f"chapter_mp3:{chapter_index}",
        kind="chapter_mp3",
        path=output,
        sha256="a" * 64,
        verified=True,
        metadata={"chapter_id": chapter_id, "quality": quality},
    )

    latest = db.latest_quality_check(
        scope=QUALITY_SCOPE_CHAPTER,
        stage=CHAPTER_POST_ENCODE_QUALITY_STAGE,
        chapter_id=chapter_id,
    )
    assert latest is not None
    assert int(latest["id"]) == check_id
    assert latest["verdict"] == QUALITY_VERDICT_PASS
    assert db.chapter_artifact_is_current_qa_verified(chapter_index) is True

    db.set_current_quality_policy(
        policy_hash="policy-v2",
        policy_version=2,
        policy={"profile": "audiobook", "true_peak_db": -2.0},
    )

    assert db.chapter_artifact_is_current_qa_verified(chapter_index) is False
    assert db.latest_quality_check(
        scope=QUALITY_SCOPE_CHAPTER,
        stage=CHAPTER_POST_ENCODE_QUALITY_STAGE,
        chapter_id=chapter_id,
    ) is None


def test_segment_audio_requires_matching_current_policy_pass_check(tmp_path: Path) -> None:
    db, segment_id = _segment_db(tmp_path)
    wav_sha256 = "c" * 64
    db.mark_signal_passed(
        segment_id,
        wav_path=tmp_path / "segment.wav",
        wav_sha256=wav_sha256,
        duration=1.0,
        signal={"duration": 1.0},
    )
    db.set_current_quality_policy(
        policy_hash="segment-policy-v1",
        policy_version=1,
        policy={"profile": "audiobook"},
    )
    quality = db.quality_metadata_for_current_policy()

    assert db.segment_audio_is_current_qa_verified(
        segment_id,
        wav_sha256,
        SEGMENT_AUDIO_QUALITY_STAGE,
    ) is False

    db.record_quality_check(
        scope=QUALITY_SCOPE_SEGMENT,
        stage=SEGMENT_ASR_DECODE_QUALITY_STAGE,
        artifact_sha256=wav_sha256,
        policy_hash=str(quality["policy_hash"]),
        policy_version=int(quality["policy_version"]),
        verdict=QUALITY_VERDICT_PASS,
        segment_id=segment_id,
        metrics={"decode_mode": "beam5", "selected": True},
    )

    assert db.segment_audio_is_current_qa_verified(
        segment_id,
        wav_sha256,
        SEGMENT_AUDIO_QUALITY_STAGE,
    ) is False

    db.record_quality_check(
        scope=QUALITY_SCOPE_SEGMENT,
        stage=SEGMENT_AUDIO_QUALITY_STAGE,
        artifact_sha256="d" * 64,
        policy_hash=str(quality["policy_hash"]),
        policy_version=int(quality["policy_version"]),
        verdict=QUALITY_VERDICT_PASS,
        segment_id=segment_id,
    )

    assert db.segment_audio_is_current_qa_verified(
        segment_id,
        wav_sha256,
        SEGMENT_AUDIO_QUALITY_STAGE,
    ) is False

    db.record_quality_check(
        scope=QUALITY_SCOPE_SEGMENT,
        stage=SEGMENT_AUDIO_QUALITY_STAGE,
        artifact_sha256=wav_sha256,
        policy_hash=str(quality["policy_hash"]),
        policy_version=int(quality["policy_version"]),
        verdict=QUALITY_VERDICT_PASS,
        segment_id=segment_id,
    )

    assert db.segment_audio_is_current_qa_verified(
        segment_id,
        wav_sha256,
        SEGMENT_AUDIO_QUALITY_STAGE,
    ) is True

    db.set_current_quality_policy(
        policy_hash="segment-policy-v2",
        policy_version=2,
        policy={"profile": "audiobook", "strict": True},
    )

    assert db.segment_audio_is_current_qa_verified(
        segment_id,
        wav_sha256,
        SEGMENT_AUDIO_QUALITY_STAGE,
    ) is False


def test_schema_v4_migrates_candidate_ledger_with_versioned_backup(tmp_path: Path) -> None:
    path = tmp_path / "project.sqlite3"
    ProjectDB(path)
    with sqlite3.connect(path) as conn:
        conn.execute("DROP TABLE segment_candidates")
        conn.execute("PRAGMA user_version=4")

    migrated = ProjectDB(path)
    backup = path.with_name(f"{path.name}.pre-v4-to-v{SCHEMA_VERSION}.bak")

    with migrated.connect() as conn:
        columns = {str(row[1]) for row in conn.execute("PRAGMA table_info(segment_candidates)")}
        assert int(conn.execute("PRAGMA user_version").fetchone()[0]) == SCHEMA_VERSION
    with sqlite3.connect(backup) as conn:
        backup_table = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='segment_candidates'"
        ).fetchone()
        assert int(conn.execute("PRAGMA user_version").fetchone()[0]) == 4

    assert {
        "segment_id",
        "policy_hash",
        "repair_round",
        "expected_voice_profile_id",
        "expected_pitch_semitones",
        "state",
        "final_check_id",
    } <= columns
    assert backup_table is None
    assert ProjectDB(path).list_segment_candidates() == []


def test_schema_v5_migrates_existing_candidate_perceptual_ledger(tmp_path: Path) -> None:
    db, segment_id, incumbent_sha256, _incumbent_path = _candidate_db(tmp_path)
    candidate_path = tmp_path / "candidates" / "r0.wav"
    candidate = db.allocate_segment_candidate(
        segment_id=segment_id,
        policy_hash="candidate-policy-v1",
        repair_round=0,
        max_repair_rounds=2,
        incumbent_sha256=incumbent_sha256,
        generation_seed=71,
        wav_path=candidate_path,
        candidates_root=tmp_path / "candidates",
    )
    path = db.path
    with sqlite3.connect(path) as conn:
        conn.execute("ALTER TABLE segment_candidates RENAME TO segment_candidates_v6_source")
        conn.execute(
            """
            CREATE TABLE segment_candidates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                segment_id INTEGER NOT NULL REFERENCES segments(id) ON DELETE CASCADE,
                policy_hash TEXT NOT NULL REFERENCES quality_policies(policy_hash),
                repair_round INTEGER NOT NULL CHECK (repair_round >= 0),
                incumbent_sha256 TEXT NOT NULL,
                expected_voice_profile_id INTEGER NOT NULL REFERENCES voice_profiles(id),
                expected_pitch_semitones INTEGER NOT NULL,
                state TEXT NOT NULL,
                tts_attempt INTEGER NOT NULL DEFAULT 0 CHECK (tts_attempt >= 0),
                generation_seed INTEGER NOT NULL,
                wav_path TEXT NOT NULL UNIQUE,
                wav_sha256 TEXT,
                wav_duration REAL,
                signal_json TEXT,
                beam_result_json TEXT,
                greedy_result_json TEXT,
                beam_check_id INTEGER REFERENCES quality_checks(id),
                greedy_check_id INTEGER REFERENCES quality_checks(id),
                final_check_id INTEGER REFERENCES quality_checks(id),
                failure_reason TEXT,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL,
                promoted_at REAL,
                UNIQUE(segment_id, policy_hash, repair_round)
            )
            """
        )
        conn.execute(
            """
            INSERT INTO segment_candidates(
                id,segment_id,policy_hash,repair_round,incumbent_sha256,
                expected_voice_profile_id,expected_pitch_semitones,state,
                tts_attempt,generation_seed,wav_path,wav_sha256,wav_duration,
                signal_json,beam_result_json,greedy_result_json,beam_check_id,
                greedy_check_id,final_check_id,failure_reason,created_at,updated_at,promoted_at
            )
            SELECT
                id,segment_id,policy_hash,repair_round,incumbent_sha256,
                expected_voice_profile_id,expected_pitch_semitones,state,
                tts_attempt,generation_seed,wav_path,wav_sha256,wav_duration,
                signal_json,beam_result_json,greedy_result_json,beam_check_id,
                greedy_check_id,final_check_id,failure_reason,created_at,updated_at,promoted_at
            FROM segment_candidates_v6_source
            """
        )
        conn.execute("DROP TABLE segment_candidates_v6_source")
        conn.execute("PRAGMA user_version=5")

    migrated = ProjectDB(path)
    backup = path.with_name(f"{path.name}.pre-v5-to-v{SCHEMA_VERSION}.bak")
    migrated_candidate = migrated.get_segment_candidate(int(candidate["id"]))
    with migrated.connect() as conn:
        columns = {str(row[1]) for row in conn.execute("PRAGMA table_info(segment_candidates)")}
        version = int(conn.execute("PRAGMA user_version").fetchone()[0])
    with sqlite3.connect(backup) as conn:
        backup_columns = {
            str(row[1]) for row in conn.execute("PRAGMA table_info(segment_candidates)")
        }
        backup_version = int(conn.execute("PRAGMA user_version").fetchone()[0])

    assert version == SCHEMA_VERSION
    assert backup_version == 5
    assert {"repair_budget", "perceptual_required", "perceptual_result_json", "perceptual_check_id"} <= columns
    assert "repair_budget" not in backup_columns
    assert int(migrated_candidate["repair_budget"]) == 1
    assert int(migrated_candidate["perceptual_required"]) == 0
    assert migrated.segment_candidate_resume_plan(segment_id, "candidate-policy-v1")["action"] == "generate"


def test_schema_v8_binds_legacy_candidate_delivery_for_resume_and_report(
    tmp_path: Path,
) -> None:
    db, segment_id, incumbent_sha256, _incumbent_path = _candidate_db(tmp_path)
    failed_path = tmp_path / "candidates" / "legacy-r0.wav"
    failed_candidate = db.allocate_segment_candidate(
        segment_id=segment_id,
        policy_hash="candidate-policy-v1",
        repair_round=0,
        max_repair_rounds=2,
        incumbent_sha256=incumbent_sha256,
        generation_seed=80,
        wav_path=failed_path,
        candidates_root=tmp_path / "candidates",
    )
    db.mark_segment_candidate_tts_failed(
        int(failed_candidate["id"]),
        expected_generation_seed=80,
        error="legacy round zero failed",
    )
    candidate_path = tmp_path / "candidates" / "legacy-r1.wav"
    candidate_sha256 = _write_candidate_artifact(candidate_path, "legacy-candidate")
    candidate = db.allocate_segment_candidate(
        segment_id=segment_id,
        policy_hash="candidate-policy-v1",
        repair_round=1,
        max_repair_rounds=2,
        incumbent_sha256=incumbent_sha256,
        generation_seed=81,
        wav_path=candidate_path,
        candidates_root=tmp_path / "candidates",
    )
    _checkpoint_candidate_signal(
        db,
        int(candidate["id"]),
        repair_round=1,
        generation_seed=81,
        wav_path=candidate_path,
        wav_sha256=candidate_sha256,
    )
    path = db.path
    with sqlite3.connect(path) as conn:
        signal = json.loads(
            str(
                conn.execute(
                    "SELECT signal_json FROM segment_candidates WHERE id=?",
                    (int(candidate["id"]),),
                ).fetchone()[0]
            )
        )
        signal.pop("pronunciation_delivery_variant")
        conn.execute(
            "UPDATE segment_candidates SET signal_json=? WHERE id=?",
            (
                json.dumps(signal, ensure_ascii=False, sort_keys=True),
                int(candidate["id"]),
            ),
        )
        conn.execute(
            "ALTER TABLE segment_candidates DROP COLUMN pronunciation_delivery_variant"
        )
        conn.execute(
            "ALTER TABLE segment_candidates DROP COLUMN expected_spoken_text_sha256"
        )
        conn.execute("PRAGMA user_version=8")

    migrated = ProjectDB(path)
    backup = path.with_name(f"{path.name}.pre-v8-to-v{SCHEMA_VERSION}.bak")
    migrated_candidate = migrated.get_segment_candidate(int(candidate["id"]))
    migrated_signal = json.loads(str(migrated_candidate["signal_json"]))
    plan = migrated.segment_candidate_resume_plan(
        segment_id,
        "candidate-policy-v1",
    )
    report_attempts = migrated.segment_candidate_attempt_summary(
        segment_id,
        "candidate-policy-v1",
    )
    report_attempt = report_attempts[1]

    assert backup.is_file()
    with sqlite3.connect(backup) as conn:
        backup_columns = {
            str(row[1])
            for row in conn.execute("PRAGMA table_info(segment_candidates)")
        }
        assert int(conn.execute("PRAGMA user_version").fetchone()[0]) == 8
    assert "pronunciation_delivery_variant" not in backup_columns
    assert "expected_spoken_text_sha256" not in backup_columns
    assert migrated_candidate["pronunciation_delivery_variant"] == (
        "locked_spoken_v1"
    )
    assert migrated_candidate["expected_spoken_text_sha256"] == "1" * 64
    assert migrated_signal["pronunciation_delivery_variant"] == "locked_spoken_v1"
    assert plan["action"] == "decode_beam"
    assert plan["repair_round"] == 1
    assert plan["pronunciation_delivery_variant"] == "locked_spoken_v1"
    assert plan["expected_spoken_text_sha256"] == "1" * 64
    assert report_attempt["pronunciation_delivery_variant"] == "locked_spoken_v1"
    assert report_attempt["expected_spoken_text_sha256"] == "1" * 64
    assert report_attempt["signal"]["pronunciation_delivery_variant"] == (
        "locked_spoken_v1"
    )
    assert [attempt["state"] for attempt in report_attempts] == [
        "tts_failed",
        "signal_passed",
    ]


def test_schema_v8_promoted_candidate_migrates_nested_decode_provenance_and_replays(
    tmp_path: Path,
) -> None:
    db, segment_id, incumbent_sha256, _incumbent_path = _candidate_db(tmp_path)
    candidate, candidate_sha256 = _dual_pass_candidate(
        db,
        segment_id=segment_id,
        incumbent_sha256=incumbent_sha256,
        candidate_path=tmp_path / "candidates" / "legacy-promoted.wav",
        generation_seed=82,
        perceptual_required=False,
    )
    promoted = db.promote_segment_candidate(
        int(candidate["id"]),
        validated_wav_sha256=candidate_sha256,
        repair_action="clarity_repair",
        attempt=1,
        warning_code="ASR_CLARITY_REPAIR",
    )
    _downgrade_promoted_candidate_delivery_to_v8(
        db,
        int(promoted["id"]),
        live_signal_damage="harmless_metric",
    )

    migrated = ProjectDB(db.path)
    replay = migrated.promote_segment_candidate(
        int(promoted["id"]),
        validated_wav_sha256=candidate_sha256,
        repair_action="clarity_repair",
        attempt=1,
        warning_code="ASR_CLARITY_REPAIR",
    )
    final_check = migrated.latest_quality_check(
        scope=QUALITY_SCOPE_SEGMENT,
        stage=SEGMENT_AUDIO_QUALITY_STAGE,
        segment_id=segment_id,
    )
    final_metrics = json.loads(str(final_check["metrics_json"]))
    report_attempt = migrated.segment_candidate_attempt_summary(
        segment_id,
        "candidate-policy-v1",
    )[0]
    migrated_live_signal = json.loads(
        str(migrated.get_segment(segment_id)["signal_json"])
    )

    assert replay["state"] == "promoted"
    assert final_metrics["pronunciation_delivery_variant"] == "locked_spoken_v1"
    assert final_metrics["expected_spoken_text_sha256"] == "1" * 64
    assert [
        evidence["pronunciation_delivery_variant"]
        for evidence in final_metrics["decode_evidence"]
    ] == ["locked_spoken_v1", "locked_spoken_v1"]
    assert report_attempt["pronunciation_delivery_variant"] == "locked_spoken_v1"
    assert report_attempt["expected_spoken_text_sha256"] == "1" * 64
    assert report_attempt["beam_result"]["pronunciation_delivery_variant"] == (
        "locked_spoken_v1"
    )
    assert report_attempt["greedy_result"]["pronunciation_delivery_variant"] == (
        "locked_spoken_v1"
    )
    assert migrated_live_signal["same_wav_recheckpoint_metric"] == 123
    assert migrated_live_signal["pronunciation_delivery_variant"] == (
        "locked_spoken_v1"
    )


@pytest.mark.parametrize("live_signal_damage", ["spoken_sha", "malformed"])
def test_schema_v8_promoted_candidate_rejects_live_signal_damage_atomically(
    tmp_path: Path,
    live_signal_damage: str,
) -> None:
    db, segment_id, incumbent_sha256, _incumbent_path = _candidate_db(tmp_path)
    candidate, candidate_sha256 = _dual_pass_candidate(
        db,
        segment_id=segment_id,
        incumbent_sha256=incumbent_sha256,
        candidate_path=tmp_path / "candidates" / "legacy-damaged.wav",
        generation_seed=83,
        perceptual_required=False,
    )
    promoted = db.promote_segment_candidate(
        int(candidate["id"]),
        validated_wav_sha256=candidate_sha256,
        repair_action="clarity_repair",
        attempt=1,
    )
    _downgrade_promoted_candidate_delivery_to_v8(
        db,
        int(promoted["id"]),
        live_signal_damage=live_signal_damage,
    )

    with pytest.raises(RuntimeError, match="differs from the live segment"):
        ProjectDB(db.path)

    with sqlite3.connect(db.path) as conn:
        columns = {
            str(row[1])
            for row in conn.execute("PRAGMA table_info(segment_candidates)")
        }
        version = int(conn.execute("PRAGMA user_version").fetchone()[0])
    assert version == 8
    assert "pronunciation_delivery_variant" not in columns
    assert "expected_spoken_text_sha256" not in columns


def test_candidate_allocation_is_idempotent_budgeted_and_policy_scoped(tmp_path: Path) -> None:
    db, segment_id, incumbent_sha256, incumbent_path = _candidate_db(tmp_path)
    candidate_path = tmp_path / "candidates" / "r0.wav"
    with pytest.raises(RuntimeError, match="collides"):
        db.allocate_segment_candidate(
            segment_id=segment_id,
            policy_hash="candidate-policy-v1",
            repair_round=0,
            max_repair_rounds=2,
            incumbent_sha256=incumbent_sha256,
            generation_seed=100,
            wav_path=incumbent_path.with_name(incumbent_path.name.swapcase()),
            candidates_root=tmp_path,
        )
    first = db.allocate_segment_candidate(
        segment_id=segment_id,
        policy_hash="candidate-policy-v1",
        repair_round=0,
        max_repair_rounds=2,
        incumbent_sha256=incumbent_sha256,
        generation_seed=101,
        wav_path=candidate_path,
        candidates_root=tmp_path / "candidates",
    )
    replay = db.allocate_segment_candidate(
        segment_id=segment_id,
        policy_hash="candidate-policy-v1",
        repair_round=0,
        max_repair_rounds=2,
        incumbent_sha256=incumbent_sha256,
        generation_seed=101,
        wav_path=candidate_path,
        candidates_root=tmp_path / "candidates",
    )

    assert int(replay["id"]) == int(first["id"])
    assert db.segment_candidate_resume_plan(segment_id, "candidate-policy-v1", 2)["action"] == "generate"
    with pytest.raises(RuntimeError, match="resume metadata"):
        db.allocate_segment_candidate(
            segment_id=segment_id,
            policy_hash="candidate-policy-v1",
            repair_round=0,
            max_repair_rounds=2,
            incumbent_sha256=incumbent_sha256,
            generation_seed=102,
            wav_path=candidate_path,
            candidates_root=tmp_path / "candidates",
        )
    with pytest.raises(RuntimeError, match="terminal failure"):
        db.allocate_segment_candidate(
            segment_id=segment_id,
            policy_hash="candidate-policy-v1",
            repair_round=1,
            max_repair_rounds=2,
            incumbent_sha256=incumbent_sha256,
            generation_seed=202,
            wav_path=tmp_path / "candidates" / "r1.wav",
            candidates_root=tmp_path / "candidates",
        )

    advanced = db.restart_segment_candidate_generation(
        int(first["id"]),
        expected_generation_seed=101,
        generation_seed=102,
        tts_attempt=1,
    )
    replayed_advance = db.restart_segment_candidate_generation(
        int(first["id"]),
        expected_generation_seed=101,
        generation_seed=102,
        tts_attempt=1,
    )
    assert int(advanced["generation_seed"]) == 102
    assert int(replayed_advance["generation_seed"]) == 102
    db.mark_segment_candidate_tts_failed(
        int(first["id"]),
        expected_generation_seed=102,
        error="TTS failed",
    )
    replayed_failure = db.mark_segment_candidate_tts_failed(
        int(first["id"]),
        expected_generation_seed=102,
        error="TTS failed",
    )
    assert replayed_failure["state"] == "tts_failed"
    with pytest.raises(RuntimeError, match="replay payload"):
        db.mark_segment_candidate_tts_failed(
            int(first["id"]),
            expected_generation_seed=102,
            error="different TTS failure",
        )
    assert db.segment_candidate_resume_plan(segment_id, "candidate-policy-v1", 2) == {
        "segment_id": segment_id,
        "policy_hash": "candidate-policy-v1",
        "action": "allocate",
        "candidate_id": None,
        "repair_round": 1,
    }
    with db.connect() as conn:
        conn.execute("UPDATE segments SET wav_sha256=? WHERE id=?", ("d" * 64, segment_id))
    assert db.segment_candidate_resume_plan(segment_id, "candidate-policy-v1", 2)["action"] == (
        "stale_incumbent"
    )
    with pytest.raises(RuntimeError, match="stale incumbent"):
        db.allocate_segment_candidate(
            segment_id=segment_id,
            policy_hash="candidate-policy-v1",
            repair_round=1,
            max_repair_rounds=2,
            incumbent_sha256=incumbent_sha256,
            generation_seed=202,
            wav_path=tmp_path / "candidates" / "r1.wav",
            candidates_root=tmp_path / "candidates",
        )
    with db.connect() as conn:
        conn.execute("UPDATE segments SET wav_sha256=? WHERE id=?", (incumbent_sha256, segment_id))
    db.set_current_quality_policy(
        policy_hash="candidate-policy-v2",
        policy_version=1,
        policy={"asr": {"repair_rounds": 2}, "changed": True},
    )
    assert db.segment_candidate_resume_plan(segment_id, "candidate-policy-v1", 2)["action"] == (
        "stale_policy"
    )
    with pytest.raises(RuntimeError, match="no longer active"):
        db.restart_segment_candidate_generation(
            int(first["id"]),
            expected_generation_seed=101,
            generation_seed=102,
            tts_attempt=1,
        )


def test_previous_candidate_decode_evidence_is_durable_and_complete(
    tmp_path: Path,
) -> None:
    db, segment_id, incumbent_sha256, _incumbent_path = _candidate_db(tmp_path)
    candidate = _locked_name_dual_failed_candidate(
        db,
        segment_id=segment_id,
        incumbent_sha256=incumbent_sha256,
        candidate_path=tmp_path / "candidates" / "locked-r0.wav",
        generation_seed=501,
    )

    evidence = db.previous_segment_candidate_decode_evidence(
        segment_id=segment_id,
        policy_hash="candidate-policy-v1",
        repair_round=1,
    )

    assert len(evidence) == 2
    assert evidence[0]["reason"] == ASR_LOCKED_NAME_ANCHOR_MISMATCH
    assert evidence[0]["failure_codes"] == [
        ASR_LOCKED_NAME_ANCHOR_MISMATCH
    ]
    assert evidence[1]["verdict"] == "pass"
    assert int(candidate["beam_check_id"]) > 0


@pytest.mark.parametrize(
    ("tamper_target", "error"),
    [
        ("candidate_result", "stored candidate ASR result differs"),
        ("quality_failure_codes", "failure-code ledger contradicts"),
    ],
)
def test_previous_candidate_decode_evidence_rejects_ledger_tamper(
    tmp_path: Path,
    tamper_target: str,
    error: str,
) -> None:
    db, segment_id, incumbent_sha256, _incumbent_path = _candidate_db(tmp_path)
    candidate = _locked_name_dual_failed_candidate(
        db,
        segment_id=segment_id,
        incumbent_sha256=incumbent_sha256,
        candidate_path=tmp_path / "candidates" / "tampered-r0.wav",
        generation_seed=502,
    )
    with db.connect() as conn:
        if tamper_target == "candidate_result":
            stored = json.loads(str(candidate["beam_result_json"]))
            stored["transcript"] = "forged transcript"
            conn.execute(
                "UPDATE segment_candidates SET beam_result_json=? WHERE id=?",
                (
                    json.dumps(stored, ensure_ascii=False, sort_keys=True),
                    int(candidate["id"]),
                ),
            )
        else:
            conn.execute(
                "UPDATE quality_checks SET failure_codes_json=? WHERE id=?",
                (
                    json.dumps(["ASR_MISMATCH"]),
                    int(candidate["beam_check_id"]),
                ),
            )

    with pytest.raises(RuntimeError, match=error):
        db.previous_segment_candidate_decode_evidence(
            segment_id=segment_id,
            policy_hash="candidate-policy-v1",
            repair_round=1,
        )


@pytest.mark.parametrize(
    ("tampered_field", "tampered_value"),
    [
        ("pronunciation_delivery_variant", "locked_spoken_v1"),
        ("expected_spoken_text_sha256", "4" * 64),
    ],
)
def test_candidate_delivery_variant_and_spoken_sha_are_replay_and_resume_bound(
    tmp_path: Path,
    tampered_field: str,
    tampered_value: str,
) -> None:
    db, segment_id, incumbent_sha256, _incumbent_path = _candidate_db(tmp_path)
    candidate_path = tmp_path / "candidates" / "source-r0.wav"
    candidate_sha256 = _write_candidate_artifact(candidate_path, "source-delivery")
    candidate = db.allocate_segment_candidate(
        segment_id=segment_id,
        policy_hash="candidate-policy-v1",
        repair_round=0,
        max_repair_rounds=2,
        incumbent_sha256=incumbent_sha256,
        generation_seed=91,
        wav_path=candidate_path,
        candidates_root=tmp_path / "candidates",
        pronunciation_delivery_variant="source_spelling_v1",
        expected_spoken_text_sha256="3" * 64,
    )
    with pytest.raises(RuntimeError, match="resume metadata differs"):
        db.allocate_segment_candidate(
            segment_id=segment_id,
            policy_hash="candidate-policy-v1",
            repair_round=0,
            max_repair_rounds=2,
            incumbent_sha256=incumbent_sha256,
            generation_seed=91,
            wav_path=candidate_path,
            candidates_root=tmp_path / "candidates",
            pronunciation_delivery_variant="locked_spoken_v1",
            expected_spoken_text_sha256="3" * 64,
        )
    with pytest.raises(RuntimeError, match="differs from its allocation"):
        _checkpoint_candidate_signal(
            db,
            int(candidate["id"]),
            repair_round=0,
            generation_seed=91,
            wav_path=candidate_path,
            wav_sha256=candidate_sha256,
            signal_overrides={
                "pronunciation_delivery_variant": "locked_spoken_v1",
            },
        )
    _checkpoint_candidate_signal(
        db,
        int(candidate["id"]),
        repair_round=0,
        generation_seed=91,
        wav_path=candidate_path,
        wav_sha256=candidate_sha256,
    )
    with db.connect() as conn:
        conn.execute(
            f"UPDATE segment_candidates SET {tampered_field}=? WHERE id=?",
            (tampered_value, int(candidate["id"])),
        )

    with pytest.raises(RuntimeError, match="differs from its allocation"):
        db.segment_candidate_resume_plan(segment_id, "candidate-policy-v1")


@pytest.mark.parametrize(
    "tamper_kind",
    ["expected_spoken_sha", "candidate_signal", "final_metrics"],
)
def test_promoted_candidate_resume_revalidates_the_entire_committed_ledger(
    tmp_path: Path,
    tamper_kind: str,
) -> None:
    db, segment_id, incumbent_sha256, _incumbent_path = _candidate_db(tmp_path)
    candidate, candidate_sha256 = _dual_pass_candidate(
        db,
        segment_id=segment_id,
        incumbent_sha256=incumbent_sha256,
        candidate_path=tmp_path / "candidates" / "promoted-tamper.wav",
        generation_seed=92,
        perceptual_required=False,
    )
    promoted = db.promote_segment_candidate(
        int(candidate["id"]),
        validated_wav_sha256=candidate_sha256,
        repair_action="clarity_repair",
        attempt=1,
    )
    with db.connect() as conn:
        if tamper_kind == "expected_spoken_sha":
            conn.execute(
                """
                UPDATE segment_candidates SET expected_spoken_text_sha256=?
                WHERE id=?
                """,
                ("8" * 64, int(promoted["id"])),
            )
        elif tamper_kind == "candidate_signal":
            signal = json.loads(str(promoted["signal_json"]))
            signal["spoken_text_sha256"] = "8" * 64
            conn.execute(
                "UPDATE segment_candidates SET signal_json=? WHERE id=?",
                (
                    json.dumps(signal, ensure_ascii=False, sort_keys=True),
                    int(promoted["id"]),
                ),
            )
        else:
            final_metrics = json.loads(
                str(
                    conn.execute(
                        "SELECT metrics_json FROM quality_checks WHERE id=?",
                        (int(promoted["final_check_id"]),),
                    ).fetchone()[0]
                )
            )
            final_metrics["transcript"] = "tampered final transcript"
            conn.execute(
                "UPDATE quality_checks SET metrics_json=? WHERE id=?",
                (
                    json.dumps(final_metrics, ensure_ascii=False, sort_keys=True),
                    int(promoted["final_check_id"]),
                ),
            )

    with pytest.raises(RuntimeError):
        db.segment_candidate_resume_plan(segment_id, "candidate-policy-v1")
    with pytest.raises(RuntimeError):
        db.segment_candidate_attempt_summary(segment_id, "candidate-policy-v1")


def test_candidate_requires_locked_casting_and_thought_uses_narrator(tmp_path: Path) -> None:
    db, segment_id = _segment_db(tmp_path)
    incumbent_sha256 = "a" * 64
    db.mark_signal_passed(
        segment_id,
        wav_path=tmp_path / "incumbent.wav",
        wav_sha256=incumbent_sha256,
        duration=1.0,
        signal={"duration": 1.0, "spoken_text_sha256": "1" * 64},
        generation_seed=1,
    )
    db.set_current_quality_policy(
        policy_hash="candidate-policy-v1",
        policy_version=1,
        policy={"asr": {"repair_rounds": 1}},
    )
    with pytest.raises(RuntimeError, match="assigned locked voice"):
        db.allocate_segment_candidate(
            segment_id=segment_id,
            policy_hash="candidate-policy-v1",
            repair_round=0,
            max_repair_rounds=1,
            incumbent_sha256=incumbent_sha256,
            generation_seed=10,
            wav_path=tmp_path / "candidates" / "missing-cast.wav",
            candidates_root=tmp_path / "candidates",
        )

    character_profile = db.upsert_voice_profile(
        {
            "voice_key": "thought-character",
            "engine": "vieneu",
            "preset_name": "Character",
            "description": "Character voice",
            "seed": 2,
            "pitch_semitones": 0,
            "status": "ready",
        }
    )
    narrator_profile = db.upsert_voice_profile(
        {
            "voice_key": "NARRATOR",
            "engine": "vieneu",
            "preset_name": "Narrator",
            "description": "Narrator voice",
            "seed": 3,
            "pitch_semitones": -1,
            "status": "ready",
        }
    )
    with db.connect() as conn:
        conn.execute(
            "UPDATE segments SET kind='thought',voice_profile_id=? WHERE id=?",
            (character_profile, segment_id),
        )
    candidate = db.allocate_segment_candidate(
        segment_id=segment_id,
        policy_hash="candidate-policy-v1",
        repair_round=0,
        max_repair_rounds=1,
        incumbent_sha256=incumbent_sha256,
        generation_seed=11,
        wav_path=tmp_path / "candidates" / "thought.wav",
        candidates_root=tmp_path / "candidates",
    )
    assert int(candidate["expected_voice_profile_id"]) == narrator_profile
    assert int(candidate["expected_pitch_semitones"]) == -1


def test_candidate_rejects_casting_change_after_allocation(tmp_path: Path) -> None:
    db, segment_id, incumbent_sha256, _incumbent_path = _candidate_db(tmp_path)
    candidate_path = tmp_path / "candidates" / "casting.wav"
    candidate_sha256 = _write_candidate_artifact(candidate_path, "casting-change")
    candidate = db.allocate_segment_candidate(
        segment_id=segment_id,
        policy_hash="candidate-policy-v1",
        repair_round=0,
        max_repair_rounds=2,
        incumbent_sha256=incumbent_sha256,
        generation_seed=33,
        wav_path=candidate_path,
        candidates_root=tmp_path / "candidates",
    )
    replacement_profile = db.upsert_voice_profile(
        {
            "voice_key": "replacement-voice",
            "engine": "vieneu",
            "preset_name": "Replacement",
            "description": "Replacement voice",
            "seed": 4,
            "pitch_semitones": 0,
            "status": "ready",
        }
    )
    with db.connect() as conn:
        conn.execute(
            "UPDATE segments SET voice_profile_id=? WHERE id=?",
            (replacement_profile, segment_id),
        )
    with pytest.raises(RuntimeError, match="casting changed"):
        _checkpoint_candidate_signal(
            db,
            int(candidate["id"]),
            repair_round=0,
            generation_seed=33,
            wav_path=candidate_path,
            wav_sha256=candidate_sha256,
        )


def test_candidate_promotion_is_atomic_idempotent_and_preserves_incumbent_on_abort(
    tmp_path: Path,
) -> None:
    db, segment_id, incumbent_sha256, _incumbent_path = _candidate_db(tmp_path)
    candidate_path = tmp_path / "candidates" / "r0.wav"
    candidate_sha256 = _write_candidate_artifact(candidate_path, "atomic-promotion")
    candidate = db.allocate_segment_candidate(
        segment_id=segment_id,
        policy_hash="candidate-policy-v1",
        repair_round=0,
        max_repair_rounds=2,
        incumbent_sha256=incumbent_sha256,
        generation_seed=101,
        wav_path=candidate_path,
        candidates_root=tmp_path / "candidates",
    )
    candidate_id = int(candidate["id"])
    _checkpoint_candidate_signal(
        db,
        candidate_id,
        repair_round=0,
        generation_seed=101,
        wav_path=candidate_path,
        wav_sha256=candidate_sha256,
    )
    beam_check = _candidate_decode_check(
        db,
        segment_id=segment_id,
        artifact_sha256=candidate_sha256,
        repair_round=0,
        generation_seed=101,
        confirmation=False,
        verdict="pass",
        reason="ok",
    )
    db.checkpoint_segment_candidate_decode(
        candidate_id,
        quality_check_id=beam_check,
        confirmation=False,
    )
    assert db.get_segment(segment_id)["wav_sha256"] == incumbent_sha256
    assert db.segment_candidate_resume_plan(segment_id, "candidate-policy-v1", 2)["action"] == (
        "decode_greedy"
    )

    greedy_check = _candidate_decode_check(
        db,
        segment_id=segment_id,
        artifact_sha256=candidate_sha256,
        repair_round=0,
        generation_seed=101,
        confirmation=True,
        verdict="pass",
        reason="ok",
    )
    db.checkpoint_segment_candidate_decode(
        candidate_id,
        quality_check_id=greedy_check,
        confirmation=True,
    )
    with db.connect() as conn:
        conn.execute(
            f"""
            CREATE TRIGGER abort_candidate_promotion
            BEFORE UPDATE OF wav_sha256 ON segments
            WHEN NEW.wav_sha256='{candidate_sha256}'
            BEGIN SELECT RAISE(ABORT, 'simulated promotion crash'); END
            """
        )
    with pytest.raises(sqlite3.IntegrityError, match="simulated promotion crash"):
        db.promote_segment_candidate(
            candidate_id,
            validated_wav_sha256=candidate_sha256,
            repair_action="clarity_repair",
            attempt=1,
            warning_code="ASR_CLARITY_REPAIR",
        )
    with db.connect() as conn:
        stray_passes = conn.execute(
            """
            SELECT COUNT(*) FROM quality_checks
            WHERE stage=? AND artifact_sha256=? AND verdict='pass'
            """,
            (SEGMENT_AUDIO_QUALITY_STAGE, candidate_sha256),
        ).fetchone()[0]
        conn.execute("DROP TRIGGER abort_candidate_promotion")
    assert stray_passes == 0
    assert db.get_segment(segment_id)["wav_sha256"] == incumbent_sha256
    assert db.get_segment_candidate(candidate_id)["state"] == "dual_passed"

    promoted = db.promote_segment_candidate(
        candidate_id,
        validated_wav_sha256=candidate_sha256,
        repair_action="clarity_repair",
        attempt=1,
        warning_code="ASR_CLARITY_REPAIR",
    )
    replay = db.promote_segment_candidate(
        candidate_id,
        validated_wav_sha256=candidate_sha256,
        repair_action="clarity_repair",
        attempt=1,
        warning_code="ASR_CLARITY_REPAIR",
    )
    assert promoted["state"] == "promoted"
    assert int(replay["id"]) == candidate_id
    assert db.get_segment(segment_id)["wav_sha256"] == candidate_sha256
    assert db.segment_candidate_resume_plan(segment_id, "candidate-policy-v1", 2)["action"] == (
        "complete"
    )
    with db.connect() as conn:
        pass_count = conn.execute(
            """
            SELECT COUNT(*) FROM quality_checks
            WHERE stage=? AND artifact_sha256=? AND verdict='pass'
            """,
            (SEGMENT_AUDIO_QUALITY_STAGE, candidate_sha256),
        ).fetchone()[0]
    assert pass_count == 1
    final_check = db.latest_quality_check(
        scope=QUALITY_SCOPE_SEGMENT,
        stage=SEGMENT_AUDIO_QUALITY_STAGE,
        segment_id=segment_id,
    )
    final_metrics = json.loads(str(final_check["metrics_json"]))
    assert final_metrics["transcript"] == "Text"
    assert final_metrics["confirmation_verdicts"] == ["pass", "pass"]
    assert len(final_metrics["decode_evidence"]) == 2
    with pytest.raises(RuntimeError, match="replay"):
        db.promote_segment_candidate(
            candidate_id,
            validated_wav_sha256=candidate_sha256,
            repair_action="different_repair",
            attempt=1,
            warning_code="ASR_CLARITY_REPAIR",
        )
    with pytest.raises(RuntimeError, match="replay"):
        db.promote_segment_candidate(
            candidate_id,
            validated_wav_sha256=candidate_sha256,
            repair_action="clarity_repair",
            attempt=1,
            warning_code="DIFFERENT_WARNING",
        )


def test_candidate_requires_current_perceptual_pass_before_atomic_promotion(
    tmp_path: Path,
) -> None:
    db, segment_id, incumbent_sha256, _incumbent_path = _candidate_db(tmp_path)
    candidate, candidate_sha256 = _dual_pass_candidate(
        db,
        segment_id=segment_id,
        incumbent_sha256=incumbent_sha256,
        candidate_path=tmp_path / "candidates" / "perceptual-pass.wav",
        generation_seed=211,
        perceptual_required=True,
    )
    candidate_id = int(candidate["id"])

    assert db.segment_candidate_resume_plan(segment_id, "candidate-policy-v1") == {
        "segment_id": segment_id,
        "policy_hash": "candidate-policy-v1",
        "action": "verify_perceptual",
        "candidate_id": candidate_id,
        "repair_round": 0,
        "state": "dual_passed",
        "generation_seed": 211,
        "tts_attempt": 0,
        "wav_path": str((tmp_path / "candidates" / "perceptual-pass.wav").resolve()),
        "wav_sha256": candidate_sha256,
        "perceptual_required": True,
        "pronunciation_delivery_variant": "locked_spoken_v1",
        "expected_spoken_text_sha256": "1" * 64,
    }
    with pytest.raises(RuntimeError, match="before perceptual QA passes"):
        db.promote_segment_candidate(
            candidate_id,
            validated_wav_sha256=candidate_sha256,
            repair_action="clarity_repair",
            attempt=1,
        )

    perceptual_check_id = _candidate_perceptual_check(
        db,
        segment_id=segment_id,
        artifact_sha256=candidate_sha256,
        verdict="pass",
        perceptual_verdict="ok",
        reason="PERCEPTUAL_OK",
        review_required=False,
    )
    checkpointed = db.checkpoint_segment_candidate_perceptual(
        candidate_id,
        quality_check_id=perceptual_check_id,
    )
    replay = db.checkpoint_segment_candidate_perceptual(
        candidate_id,
        quality_check_id=perceptual_check_id,
    )

    assert checkpointed["state"] == "dual_passed"
    assert int(replay["perceptual_check_id"]) == perceptual_check_id
    assert db.segment_candidate_resume_plan(segment_id, "candidate-policy-v1")["action"] == (
        "promote"
    )
    promoted = db.promote_segment_candidate(
        candidate_id,
        validated_wav_sha256=candidate_sha256,
        repair_action="clarity_repair",
        attempt=1,
    )
    final_check = db.latest_quality_check(
        scope=QUALITY_SCOPE_SEGMENT,
        stage=SEGMENT_AUDIO_QUALITY_STAGE,
        segment_id=segment_id,
    )
    final_metrics = json.loads(str(final_check["metrics_json"]))

    assert promoted["state"] == "promoted"
    assert db.get_segment(segment_id)["wav_sha256"] == candidate_sha256
    assert db.segment_audio_is_current_qa_verified(
        segment_id,
        candidate_sha256,
        SEGMENT_PERCEPTUAL_QUALITY_STAGE,
    )
    assert final_metrics["perceptual_required"] is True
    assert final_metrics["perceptual_quality_check_id"] == perceptual_check_id
    assert final_metrics["perceptual_evidence"]["verdict"] == "ok"


def test_candidate_perceptual_review_is_terminal_and_advances_same_budget(
    tmp_path: Path,
) -> None:
    db, segment_id, incumbent_sha256, _incumbent_path = _candidate_db(tmp_path)
    candidate, candidate_sha256 = _dual_pass_candidate(
        db,
        segment_id=segment_id,
        incumbent_sha256=incumbent_sha256,
        candidate_path=tmp_path / "candidates" / "perceptual-review.wav",
        generation_seed=221,
        perceptual_required=True,
    )
    candidate_id = int(candidate["id"])
    wrong_pitch_check = _candidate_perceptual_check(
        db,
        segment_id=segment_id,
        artifact_sha256=candidate_sha256,
        verdict="pass",
        perceptual_verdict="ok",
        reason="PERCEPTUAL_OK",
        review_required=False,
        baseline_pitch_semitones=1,
    )
    with pytest.raises(RuntimeError, match="baseline pitch"):
        db.checkpoint_segment_candidate_perceptual(
            candidate_id,
            quality_check_id=wrong_pitch_check,
        )

    review_check = _candidate_perceptual_check(
        db,
        segment_id=segment_id,
        artifact_sha256=candidate_sha256,
        verdict="inconclusive",
        perceptual_verdict="review",
        reason="PERCEPTUAL_NATURALNESS_REVIEW",
        review_required=True,
    )
    reviewed = db.checkpoint_segment_candidate_perceptual(
        candidate_id,
        quality_check_id=review_check,
    )
    plan = db.segment_candidate_resume_plan(segment_id, "candidate-policy-v1")

    assert reviewed["state"] == "dual_failed"
    assert plan == {
        "segment_id": segment_id,
        "policy_hash": "candidate-policy-v1",
        "action": "allocate",
        "candidate_id": None,
        "repair_round": 1,
    }
    with pytest.raises(RuntimeError, match="repair budget differs"):
        db.segment_candidate_resume_plan(segment_id, "candidate-policy-v1", 1)
    with pytest.raises(RuntimeError, match="perceptual requirements"):
        db.allocate_segment_candidate(
            segment_id=segment_id,
            policy_hash="candidate-policy-v1",
            repair_round=1,
            max_repair_rounds=2,
            incumbent_sha256=incumbent_sha256,
            generation_seed=222,
            wav_path=tmp_path / "candidates" / "r1.wav",
            candidates_root=tmp_path / "candidates",
            perceptual_required=False,
        )


def test_candidate_decode_and_promotion_reject_tampered_locked_provenance(
    tmp_path: Path,
) -> None:
    db, segment_id, incumbent_sha256, _incumbent_path = _candidate_db(tmp_path)
    candidate_path = tmp_path / "candidates" / "r0.wav"
    candidate_sha256 = _write_candidate_artifact(candidate_path, "tampered-provenance")
    candidate = db.allocate_segment_candidate(
        segment_id=segment_id,
        policy_hash="candidate-policy-v1",
        repair_round=0,
        max_repair_rounds=2,
        incumbent_sha256=incumbent_sha256,
        generation_seed=301,
        wav_path=candidate_path,
        candidates_root=tmp_path / "candidates",
    )
    candidate_id = int(candidate["id"])
    _checkpoint_candidate_signal(
        db,
        candidate_id,
        repair_round=0,
        generation_seed=301,
        wav_path=candidate_path,
        wav_sha256=candidate_sha256,
    )
    contradictory_check = _candidate_decode_check(
        db,
        segment_id=segment_id,
        artifact_sha256=candidate_sha256,
        repair_round=0,
        generation_seed=301,
        confirmation=False,
        verdict="pass",
        reason="contradictory",
        metrics_overrides={"verdict": "mismatch", "passed": False},
    )
    with pytest.raises(RuntimeError, match="contradicts"):
        db.checkpoint_segment_candidate_decode(
            candidate_id,
            quality_check_id=contradictory_check,
            confirmation=False,
        )
    wrong_voice_check = db.record_quality_check(
        scope=QUALITY_SCOPE_SEGMENT,
        stage=SEGMENT_ASR_DECODE_QUALITY_STAGE,
        segment_id=segment_id,
        artifact_sha256=candidate_sha256,
        policy_hash="candidate-policy-v1",
        policy_version=1,
        verdict="pass",
        metrics={
            "verdict": "pass",
            "passed": True,
            "decode_mode": "beam5",
            "selected": True,
            "delivery_mode": "clarity",
            "repair_round": 0,
            "generation_seed": 301,
            "spoken_text_sha256": "2" * 64,
            "pronunciation_delivery_variant": "locked_spoken_v1",
            "voice_profile_id": 99,
            "pitch_semitones": 0,
            "effective_pitch_semitones": 0,
            "pitch_variant_skipped": False,
            "pitch_variant_mixed": False,
        },
    )
    with pytest.raises(RuntimeError, match="locked provenance"):
        db.checkpoint_segment_candidate_decode(
            candidate_id,
            quality_check_id=wrong_voice_check,
            confirmation=False,
        )
    missing_transcript_check = _candidate_decode_check(
        db,
        segment_id=segment_id,
        artifact_sha256=candidate_sha256,
        repair_round=0,
        generation_seed=301,
        confirmation=False,
        verdict="pass",
        reason="ok",
        metrics_overrides={"transcript": ""},
    )
    with pytest.raises(RuntimeError, match="requires a transcript"):
        db.checkpoint_segment_candidate_decode(
            candidate_id,
            quality_check_id=missing_transcript_check,
            confirmation=False,
        )
    assert db.get_segment_candidate(candidate_id)["state"] == "signal_passed"


@pytest.mark.parametrize("damage", ["missing", "tampered"])
def test_candidate_promotion_invalidates_missing_or_tampered_artifact(
    tmp_path: Path,
    damage: str,
) -> None:
    db, segment_id, incumbent_sha256, _incumbent_path = _candidate_db(tmp_path)
    candidate_path = tmp_path / "candidates" / "damaged.wav"
    candidate_sha256 = _write_candidate_artifact(candidate_path, damage)
    candidate = db.allocate_segment_candidate(
        segment_id=segment_id,
        policy_hash="candidate-policy-v1",
        repair_round=0,
        max_repair_rounds=2,
        incumbent_sha256=incumbent_sha256,
        generation_seed=321,
        wav_path=candidate_path,
        candidates_root=tmp_path / "candidates",
    )
    candidate_id = int(candidate["id"])
    _checkpoint_candidate_signal(
        db,
        candidate_id,
        repair_round=0,
        generation_seed=321,
        wav_path=candidate_path,
        wav_sha256=candidate_sha256,
    )
    for confirmation in (False, True):
        check_id = _candidate_decode_check(
            db,
            segment_id=segment_id,
            artifact_sha256=candidate_sha256,
            repair_round=0,
            generation_seed=321,
            confirmation=confirmation,
            verdict="pass",
            reason="ok",
        )
        db.checkpoint_segment_candidate_decode(
            candidate_id,
            quality_check_id=check_id,
            confirmation=confirmation,
        )
    if damage == "missing":
        candidate_path.unlink()
    else:
        candidate_path.write_bytes(b"tampered-candidate")

    invalid = db.promote_segment_candidate(
        candidate_id,
        validated_wav_sha256=candidate_sha256,
        attempt=1,
    )
    assert invalid["state"] == "invalid"
    expected_failure_text = "missing" if damage == "missing" else "checksum"
    assert expected_failure_text in str(invalid["failure_reason"])
    assert db.get_segment(segment_id)["wav_sha256"] == incumbent_sha256
    assert db.segment_candidate_resume_plan(segment_id, "candidate-policy-v1", 2)["action"] == (
        "allocate"
    )
    replay = db.mark_segment_candidate_invalid(
        candidate_id,
        expected_wav_sha256=candidate_sha256,
        reason=str(invalid["failure_reason"]),
    )
    assert replay["state"] == "invalid"
    with pytest.raises(RuntimeError, match="replay payload"):
        db.mark_segment_candidate_invalid(
            candidate_id,
            expected_wav_sha256=candidate_sha256,
            reason="different invalidation reason",
        )


@pytest.mark.parametrize(
    ("blocking_flag", "signal_overrides", "decode_overrides"),
    [
        (
            "pitch_variant_skipped",
            {"pitch_variant_skipped": 1.0},
            {"pitch_variant_skipped": True},
        ),
        (
            "pitch_variant_mixed",
            {"pitch_variant_mixed": 1.0, "effective_pitch_semitones": None},
            {"pitch_variant_mixed": True, "effective_pitch_semitones": None},
        ),
        ("generation_endpoint_active", {"generation_endpoint_active": 1.0}, {}),
        ("pace_outlier", {"pace_outlier": 1.0}, {}),
    ],
)
def test_candidate_promotion_rejects_blocking_signal_flags(
    tmp_path: Path,
    blocking_flag: str,
    signal_overrides: dict,
    decode_overrides: dict,
) -> None:
    db, segment_id, incumbent_sha256, _incumbent_path = _candidate_db(tmp_path)
    candidate_path = tmp_path / "candidates" / "r0.wav"
    candidate_sha256 = _write_candidate_artifact(
        candidate_path,
        f"blocking-{blocking_flag}",
    )
    candidate = db.allocate_segment_candidate(
        segment_id=segment_id,
        policy_hash="candidate-policy-v1",
        repair_round=0,
        max_repair_rounds=2,
        incumbent_sha256=incumbent_sha256,
        generation_seed=351,
        wav_path=candidate_path,
        candidates_root=tmp_path / "candidates",
    )
    candidate_id = int(candidate["id"])
    _checkpoint_candidate_signal(
        db,
        candidate_id,
        repair_round=0,
        generation_seed=351,
        wav_path=candidate_path,
        wav_sha256=candidate_sha256,
        signal_overrides=signal_overrides,
    )
    for confirmation in (False, True):
        check_id = _candidate_decode_check(
            db,
            segment_id=segment_id,
            artifact_sha256=candidate_sha256,
            repair_round=0,
            generation_seed=351,
            confirmation=confirmation,
            verdict="pass",
            reason="ok",
            metrics_overrides=decode_overrides,
        )
        db.checkpoint_segment_candidate_decode(
            candidate_id,
            quality_check_id=check_id,
            confirmation=confirmation,
        )
    blocked = db.get_segment_candidate(candidate_id)
    assert blocked["state"] == "dual_failed"
    assert blocking_flag in str(blocked["failure_reason"])
    with pytest.raises(RuntimeError, match="before both"):
        db.promote_segment_candidate(
            candidate_id,
            validated_wav_sha256=candidate_sha256,
            attempt=1,
        )
    assert db.get_segment(segment_id)["wav_sha256"] == incumbent_sha256
    assert db.get_segment_candidate(candidate_id)["state"] == "dual_failed"


def test_candidate_exhaustion_keeps_incumbent_and_uses_incumbent_evidence(
    tmp_path: Path,
) -> None:
    db, segment_id, incumbent_sha256, incumbent_path = _candidate_db(tmp_path)
    trigger_check = db.record_quality_check(
        scope=QUALITY_SCOPE_SEGMENT,
        stage=SEGMENT_AUDIO_QUALITY_STAGE,
        segment_id=segment_id,
        artifact_sha256=incumbent_sha256,
        policy_hash="candidate-policy-v1",
        policy_version=1,
        verdict="repair",
        metrics={
            "reason": "ASR_MISMATCH",
            "transcript": "primary transcript",
            "similarity": 0.7,
            "wer": 0.4,
        },
        failure_codes=("ASR_MISMATCH",),
    )
    first = db.allocate_segment_candidate(
        segment_id=segment_id,
        policy_hash="candidate-policy-v1",
        repair_round=0,
        max_repair_rounds=2,
        incumbent_sha256=incumbent_sha256,
        generation_seed=401,
        wav_path=tmp_path / "candidates" / "r0.wav",
        candidates_root=tmp_path / "candidates",
    )
    db.mark_segment_candidate_tts_failed(
        int(first["id"]),
        expected_generation_seed=401,
        error="round zero failed",
    )
    with pytest.raises(RuntimeError, match="every configured"):
        db.finalize_segment_candidate_exhaustion(
            segment_id=segment_id,
            policy_hash="candidate-policy-v1",
            max_repair_rounds=2,
            incumbent_sha256=incumbent_sha256,
            trigger_quality_check_id=trigger_check,
            error="repair exhausted",
            warning_code="ASR_MISMATCH_UNRESOLVED",
        )
    second = db.allocate_segment_candidate(
        segment_id=segment_id,
        policy_hash="candidate-policy-v1",
        repair_round=1,
        max_repair_rounds=2,
        incumbent_sha256=incumbent_sha256,
        generation_seed=402,
        wav_path=tmp_path / "candidates" / "r1.wav",
        candidates_root=tmp_path / "candidates",
    )
    db.mark_segment_candidate_tts_failed(
        int(second["id"]),
        expected_generation_seed=402,
        error="round one failed",
    )
    final_check_id = db.finalize_segment_candidate_exhaustion(
        segment_id=segment_id,
        policy_hash="candidate-policy-v1",
        max_repair_rounds=2,
        incumbent_sha256=incumbent_sha256,
        trigger_quality_check_id=trigger_check,
        error="repair exhausted",
        warning_code="ASR_MISMATCH_UNRESOLVED",
    )
    replay_check_id = db.finalize_segment_candidate_exhaustion(
        segment_id=segment_id,
        policy_hash="candidate-policy-v1",
        max_repair_rounds=2,
        incumbent_sha256=incumbent_sha256,
        trigger_quality_check_id=trigger_check,
        error="repair exhausted",
        warning_code="ASR_MISMATCH_UNRESOLVED",
    )
    final = db.get_segment(segment_id)
    check = db.latest_quality_check(
        scope=QUALITY_SCOPE_SEGMENT,
        stage=SEGMENT_AUDIO_QUALITY_STAGE,
        segment_id=segment_id,
    )
    metrics = json.loads(str(check["metrics_json"]))

    assert replay_check_id == final_check_id
    assert final["wav_path"] == str(incumbent_path.resolve())
    assert final["wav_sha256"] == incumbent_sha256
    assert final["asr_text"] == "primary transcript"
    assert metrics["incumbent_sha256"] == incumbent_sha256
    assert [attempt["state"] for attempt in metrics["candidate_attempts"]] == [
        "tts_failed",
        "tts_failed",
    ]
    for changed_payload in (
        {"error": "different error"},
        {"warning_code": "DIFFERENT_WARNING"},
        {"final_verdict": "inconclusive"},
        {"failure_codes": ("DIFFERENT_FAILURE",)},
    ):
        replay_payload = {
            "segment_id": segment_id,
            "policy_hash": "candidate-policy-v1",
            "max_repair_rounds": 2,
            "incumbent_sha256": incumbent_sha256,
            "trigger_quality_check_id": trigger_check,
            "error": "repair exhausted",
            "warning_code": "ASR_MISMATCH_UNRESOLVED",
            **changed_payload,
        }
        with pytest.raises(RuntimeError, match="replay payload"):
            db.finalize_segment_candidate_exhaustion(**replay_payload)
