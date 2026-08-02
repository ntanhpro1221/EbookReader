from __future__ import annotations

import copy
import json
import os
import re
import shutil
import subprocess
import time
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Callable

import requests

from .database import ProjectDB
from .models import (
    CONTEXTUAL_ENGLISH_NAME_PRONUNCIATION_SOURCE,
    ENGLISH_NAME_PRONUNCIATION_SOURCE,
)
from .process_utils import terminate_process_tree


ALLOWED_KINDS = {"narration", "dialogue", "thought"}
ALLOWED_GENDERS = {"male", "female", "unknown"}
ALLOWED_AGES = {"child", "teen", "young", "adult", "elderly", "unknown"}
ALLOWED_EMOTIONS = {
    "neutral", "happy", "sad", "angry", "afraid", "surprised", "tender",
    "sarcastic", "excited", "tired", "whispering",
}
ALLOWED_PACES = {"slow", "normal", "fast"}
ALLOWED_VOLUMES = {"soft", "normal", "loud"}
RESERVED_SPEAKERS = {"narrator": "NARRATOR", "unknown": "UNKNOWN"}
BATCH_ID_PREFIX = "S"
BATCH_ID_WIDTH = 3
LOCAL_SPEAKER_REQUEST_PREFIX = "NPC_LOCAL:"
LOCAL_SPEAKER_STORED_PREFIX = "NPC_LOCAL::"
ANALYSIS_OUTPUT_BASE_TOKENS = 512
ANALYSIS_OUTPUT_TOKENS_PER_SEGMENT = 192
ANALYSIS_OUTPUT_MIN_TOKENS = 1024
ANALYSIS_OUTPUT_MAX_TOKENS = 6144
ANALYSIS_REQUEST_MAX_SECONDS = 420.0
ANALYSIS_STREAM_IDLE_SECONDS = 90.0
ANALYSIS_ACTIVITY_SECONDS = 60.0
MAX_PRONUNCIATIONS_PER_BATCH = 32
NAME_PRONUNCIATION_BATCH_SIZE = 20
NAME_PRONUNCIATION_MIN_OCCURRENCES = 1
NAME_PRONUNCIATION_ID_PREFIX = "N"
NAME_PRONUNCIATION_ID_WIDTH = 3
AUTOMATIC_PRONUNCIATION_REPAIR_CONFIDENCE = 0.85
CMUDICT_TRANSLITERATION_CONFIDENCE = 0.98
IDENTITY_CONTEXT_RADIUS = 1
IDENTITY_CONTEXTS_PER_SPEAKER = 4
IDENTITY_CONTEXT_LINE_CHARS = 220
ALIAS_RECONCILIATION_BATCH_SIZE = 16
ADDRESSEE_REPAIR_NOTE = "đã tách người nói khỏi tên người được gọi"
DIRECT_ADDRESS_TITLES = (
    "anh", "chị", "ông", "bà", "ngài", "cô", "chú", "bác", "dì", "cậu", "em",
    "cha", "mẹ", "thầy", "sư phụ", "đại nhân", "đội trưởng",
)
NAME_TOKEN_PATTERN = re.compile(
    r"(?<![\wÀ-ỹĐđ])([A-Z][A-Za-z]*(?:['’-][A-Za-z]+)*)(?![\wÀ-ỹĐđ])"
)
SPEAKER_NAME_TOKEN_PATTERN = re.compile(
    r"(?<![\wÀ-ỹĐđ])([A-Za-z][A-Za-z]*(?:['’-][A-Za-z]+)*)(?![\wÀ-ỹĐđ])"
)
VIETNAMESE_SPOKEN_FORM_PATTERN = re.compile(
    r"^[A-Za-zÀ-ỹĐđ]+(?:[ -][A-Za-zÀ-ỹĐđ]+)*$"
)
NON_VIETNAMESE_SYLLABLE_CODA_PATTERN = re.compile(r"[fjlrsvwz]$", re.IGNORECASE)
NAME_CANDIDATE_EXCLUSIONS = {
    "a", "ai", "an", "anh", "ba", "ban", "binh", "book", "cha", "chapter", "chau", "chi",
    "chu", "co", "con", "cung", "dao", "day", "dinh", "do", "dong", "duc", "giang", "ha", "hai",
    "haiz", "hieu", "ho", "hoa", "hoang", "huhu", "huy", "khi", "khong", "khung", "lan", "linh",
    "long", "luc", "mai", "mau", "minh", "mot", "muoi", "nam", "narrator", "nga", "ngay", "nguoi",
    "nhung", "no", "npc", "ong", "phong", "phuc", "quan", "quang", "sau", "son", "ta", "thanh",
    "thao", "the", "thi", "thu", "tia", "tieng", "tim", "tinh", "toi", "trang", "trinh", "trong",
    "trung", "truoc", "tuan", "tuy", "unknown", "va", "vai", "van", "vi", "viet", "vinh", "voi",
    "he", "her", "him",
    "his", "lady", "lord", "miss", "mister", "mr", "mrs", "she", "sir", "their", "they",
}
CMUDICT_CONTEXT_ONLY = {"may"}
OLLAMA_LOG_FILENAME = "ollama-server.log"
DEFAULT_RUNTIME_ROOT = Path(__file__).resolve().parents[1] / "runtime"
CMUDICT_PATH = Path(__file__).resolve().parent / "assets" / "cmudict.dict"
ARPABET_VOWELS = frozenset(
    {
        "AA", "AE", "AH", "AO", "AW", "AY", "EH", "ER",
        "EY", "IH", "IY", "OW", "OY", "UH", "UW",
    }
)
ARPABET_PRONUNCIATION_OVERRIDES = {
    ("AA", "L", "T", "OW"): "An-tô",
    ("AH", "L", "IY", "S", "AH"): "A-li-sa",
    ("AY", "V", "AH", "N"): "Ai-vân",
    ("B", "EH", "N", "JH", "AH", "M", "AH", "N"): "Ben-gia-min",
    ("EH", "V", "AH", "N", "Z"): "E-vân",
    ("G", "EH", "R", "IY"): "Ga-ri",
    ("JH", "AA", "N"): "Giôn",
    ("JH", "OW", "AH", "L"): "Giô-en",
    ("L", "UW", "S", "IY", "AH", "N"): "Lu-si-en",
    ("M", "AY", "K", "AH", "L"): "Mai-cồ",
    ("M", "ER", "F", "IY"): "Mơ-phi",
    ("S", "AY", "M", "AH", "N"): "Sai-mân",
    ("T", "R", "EY", "S", "IY"): "Trây-si",
    ("W", "EY", "N"): "Uên",
}
ARPABET_ONSET_OVERRIDES = {
    ("B", "R"): "br",
    ("CH",): "ch",
    ("D", "R"): "đr",
    ("DH",): "đ",
    ("JH",): "gi",
    ("K", "L"): "cl",
    ("K", "R"): "cr",
    ("NG",): "ng",
    ("S", "K"): "x",
    ("S", "T"): "x",
    ("SH",): "s",
    ("T", "R"): "tr",
    ("TH",): "th",
    ("ZH",): "gi",
}
ARPABET_ONSETS = {
    "B": "b",
    "CH": "ch",
    "D": "đ",
    "DH": "đ",
    "F": "ph",
    "G": "g",
    "HH": "h",
    "JH": "gi",
    "K": "c",
    "L": "l",
    "M": "m",
    "N": "n",
    "NG": "ng",
    "P": "p",
    "R": "r",
    "S": "x",
    "SH": "s",
    "T": "t",
    "TH": "th",
    "V": "v",
    "W": "u",
    "Y": "d",
    "Z": "d",
    "ZH": "gi",
}
ARPABET_VOWEL_READINGS = {
    "AA": "a",
    "AE": "e",
    "AH": "a",
    "AO": "o",
    "AW": "ao",
    "AY": "ai",
    "EH": "e",
    "ER": "ơ",
    "EY": "ây",
    "IH": "i",
    "IY": "i",
    "OW": "ô",
    "OY": "oi",
    "UH": "u",
    "UW": "u",
}
ARPABET_CODAS = {
    "CH": "ch",
    "K": "c",
    "M": "m",
    "N": "n",
    "NG": "ng",
    "P": "p",
    "T": "t",
}


class AnalysisRequestStopped(RuntimeError):
    pass


class OllamaStreamIncompleteError(RuntimeError):
    pass


OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "segments": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "kind": {"type": "string", "enum": sorted(ALLOWED_KINDS)},
                    "speaker": {"type": "string", "maxLength": 120},
                    "gender": {"type": "string", "enum": sorted(ALLOWED_GENDERS)},
                    "age": {"type": "string", "enum": sorted(ALLOWED_AGES)},
                    "emotion": {"type": "string", "enum": sorted(ALLOWED_EMOTIONS)},
                    "intensity": {"type": "integer", "minimum": 0, "maximum": 3},
                    "pace": {"type": "string", "enum": sorted(ALLOWED_PACES)},
                    "volume": {"type": "string", "enum": sorted(ALLOWED_VOLUMES)},
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                    "personality_hint": {"type": "string", "maxLength": 160},
                    "notes": {"type": "string", "maxLength": 240},
                },
                "required": [
                    "id", "kind", "speaker", "gender", "age", "emotion", "intensity",
                    "pace", "volume", "confidence", "personality_hint", "notes",
                ],
                "additionalProperties": False,
            },
        },
        "pronunciations": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "surface": {"type": "string", "maxLength": 160},
                    "spoken_form": {"type": "string", "maxLength": 240},
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                    "reason": {"type": "string", "maxLength": 240},
                },
                "required": ["surface", "spoken_form", "confidence", "reason"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["segments"],
    "additionalProperties": False,
}


SYSTEM_PROMPT = """Bạn là đạo diễn audiobook tiếng Việt và biên tập viên light novel.
Phân tích từng đoạn theo đúng ID. Không hỏi người dùng và không bỏ sót ID.

Quy tắc:
1. Lời kể dùng speaker=NARRATOR.
2. Hội thoại dùng tên nhân vật nhất quán với danh sách đã biết.
   Nếu nhân vật không có tên nhưng phân biệt được cục bộ trong đoạn hội thoại, dùng
   speaker=NPC_LOCAL:<nhãn ngắn>, ví dụ NPC_LOCAL:áo xanh hoặc NPC_LOCAL:lính gác 1.
   Giữ cùng nhãn cho cùng người trong các đoạn liên tiếp của batch; dùng nhãn khác cho người khác.
   Chỉ dùng UNKNOWN khi hoàn toàn không có dấu hiệu phân biệt người nói.
   Speaker là người phát ra câu, không phải người được gọi trong câu. Tên đứng sau cách xưng hô như
   “anh Lucien”, “chị Alisa”, hoặc tên ở đầu câu theo sau bởi dấu phẩy như “Iven, ...” thường là người
   nghe. Tuyệt đối không lấy tên đó làm speaker nếu lời kể lân cận cho thấy một người khác đang nói;
   nếu người nói chưa có tên, dùng NPC_LOCAL với nhãn mô tả người nói.
3. Độc thoại nội tâm dùng kind=thought và speaker là nhân vật đang nghĩ. Hãy dùng ngữ cảnh lân cận
   và ngôi kể để xác định nhân vật; không dùng NARRATOR. Chỉ trả UNKNOWN khi thực sự không thể
   suy ra, không được bịa ra danh tính.
4. Chỉ dùng kind=narration, dialogue hoặc thought. Từ tượng thanh như rầm/uỳnh vẫn là một phần của câu
   người kể hoặc nhân vật đang đọc. Cụm cảm thán như ha/haiz/hừm và chỉ dẫn [cười]/[thở dài]/[hắng giọng]
   cũng là lời đọc bình thường của đúng speaker; không tạo kind hiệu ứng riêng và không tách chúng khỏi câu.
5. Không sửa văn bản. Không bịa nhân vật chỉ vì đại từ hắn/cô ấy/nàng.
6. Cảm xúc phải tiết chế; intensity=3 chỉ dùng ở cao trào rõ ràng. pace và volume phải phản ánh
   cách thể hiện: lời thì thầm thường soft, lời quát/giận dữ mạnh thường loud, không mặc định mọi câu là normal.
7. gender/age mô tả người nói, NARRATOR dùng unknown.
8. Với mọi tên riêng tiếng Anh hoặc tên fantasy phương Tây viết bằng chữ Latin, luôn thêm pronunciation,
   kể cả khi tên có vẻ ngắn hoặc quen thuộc. surface phải xuất hiện nguyên văn trong batch; spoken_form phải
   là cách ghi âm tiết thuần Việt giúp TTS đọc tự nhiên, không dịch nghĩa và không dùng IPA. Với thuật ngữ
   khó đọc khác cũng làm tương tự; không thêm từ phổ thông hoặc tên thuần Việt.
9. Trả JSON đúng schema, không có văn bản bên ngoài JSON.
"""


RECONCILE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "groups": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "canonical": {"type": "string", "maxLength": 120},
                    "aliases": {
                        "type": "array",
                        "items": {"type": "string", "maxLength": 120},
                    },
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                    "reason": {"type": "string", "maxLength": 240},
                },
                "required": ["canonical", "aliases", "confidence", "reason"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["groups"],
    "additionalProperties": False,
}


NAME_PRONUNCIATION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "names": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "convert": {"type": "boolean"},
                    "spoken_form": {"type": "string", "minLength": 1, "maxLength": 120},
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                    "reason": {"type": "string", "maxLength": 160},
                },
                "required": ["id", "convert", "spoken_form", "confidence", "reason"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["names"],
    "additionalProperties": False,
}


def _safe_choice(value: Any, allowed: set[str], default: str) -> str:
    normalized = str(value or "").strip().lower()
    return normalized if normalized in allowed else default


def _canonical_speaker(value: Any) -> str:
    speaker = str(value or "UNKNOWN").strip()[:120] or "UNKNOWN"
    return RESERVED_SPEAKERS.get(speaker.casefold(), speaker)


def is_local_speaker(value: Any) -> bool:
    return str(value or "").startswith(LOCAL_SPEAKER_STORED_PREFIX)


def local_speaker_label(value: Any) -> str:
    return str(value or "").rsplit("::", 1)[-1].strip()


def local_speaker_display(value: Any) -> str:
    label = local_speaker_label(value)
    return f"NPC {label}" if label else "NPC cục bộ"


def _scope_local_speaker(speaker: str, row: Any, local_scope: str) -> str:
    if not speaker.casefold().startswith(LOCAL_SPEAKER_REQUEST_PREFIX.casefold()):
        return speaker
    label = speaker[len(LOCAL_SPEAKER_REQUEST_PREFIX) :]
    label = re.sub(r"[\r\n:|]+", " ", label)
    label = re.sub(r"\s+", " ", label).strip()[:60]
    if not label:
        return "UNKNOWN"
    chapter_id = int(row["chapter_id"])
    return f"{LOCAL_SPEAKER_STORED_PREFIX}c{chapter_id:05d}::{local_scope}::{label}"


def _speaker_is_directly_addressed(text: str, speaker: str) -> bool:
    if speaker.casefold() in RESERVED_SPEAKERS:
        return False
    label = local_speaker_label(speaker) if is_local_speaker(speaker) else speaker
    label = " ".join(label.split())
    if not label or label.casefold().startswith(("người gọi ", "người nói")):
        return False
    escaped_label = re.escape(label).replace(r"\ ", r"\s+")
    quoted_start = rf"^[\s\"“”'‘’(\[]*{escaped_label}\s*[,!?:…]"
    if re.search(quoted_start, text, flags=re.IGNORECASE):
        return True
    title_pattern = "|".join(
        re.escape(title).replace(r"\ ", r"\s+")
        for title in DIRECT_ADDRESS_TITLES
    )
    titled_address = (
        rf"(?<![\wÀ-ỹĐđ])(?:{title_pattern})\s+{escaped_label}"
        rf"(?=\s*[,!?.:;…\"”’]|$)"
    )
    return re.search(titled_address, text, flags=re.IGNORECASE) is not None


def _repair_addressee_speakers(
    group: list[Any],
    result: dict[str, dict[str, Any]],
    local_scope: str,
) -> None:
    rows_by_id = {str(row["stable_id"]): row for row in group}
    local_replacements: dict[str, str] = {}
    direct_replacements: dict[str, str] = {}
    for seg_id, data in result.items():
        if data["kind"] != "dialogue":
            continue
        speaker = str(data["speaker"])
        row = rows_by_id[seg_id]
        if not _speaker_is_directly_addressed(str(row["text"]), speaker):
            continue
        label = local_speaker_label(speaker) if is_local_speaker(speaker) else speaker
        replacement = _scope_local_speaker(
            f"{LOCAL_SPEAKER_REQUEST_PREFIX}người gọi {label}",
            row,
            local_scope,
        )
        if is_local_speaker(speaker):
            local_replacements[speaker] = replacement
        else:
            direct_replacements[seg_id] = replacement

    for seg_id, data in result.items():
        speaker = str(data["speaker"])
        replacement = direct_replacements.get(seg_id) or local_replacements.get(speaker)
        if replacement is None:
            continue
        data["speaker"] = replacement
        notes = str(data.get("notes", ""))
        data["notes"] = (
            f"{notes}; {ADDRESSEE_REPAIR_NOTE}" if notes else ADDRESSEE_REPAIR_NOTE
        )[:500]


def _heuristic(row: Any) -> dict[str, Any]:
    text = str(row["text"])
    lowered = text.casefold()
    kind = str(row["kind_hint"])
    speaker = "NARRATOR" if kind == "narration" else "UNKNOWN"
    emotion, intensity, pace, volume = "neutral", 1, "normal", "normal"
    if any(word in lowered for word in ("khóc", "nước mắt", "đau lòng", "buồn", "tuyệt vọng")):
        emotion, pace, volume = "sad", "slow", "soft"
    elif any(word in lowered for word in ("giận", "tức", "quát", "gầm", "đồ khốn")):
        emotion, intensity, volume = "angry", 2, "loud"
    elif any(word in lowered for word in ("sợ", "run rẩy", "hoảng", "kinh hãi")):
        emotion, pace = "afraid", "fast"
    elif any(word in lowered for word in ("cười", "vui", "hạnh phúc", "mừng")):
        emotion = "happy"
    return {
        "id": row["stable_id"],
        "kind": kind,
        "speaker": speaker,
        "gender": "unknown",
        "age": "unknown",
        "emotion": emotion,
        "intensity": intensity,
        "pace": pace,
        "volume": volume,
        "confidence": 0.25,
        "personality_hint": "",
        "notes": "heuristic fallback",
    }


def _validate(
    group: list[Any],
    payload: dict[str, Any],
    local_scope: str = "b0000",
    *,
    allow_unresolved_thought_narrator: bool = False,
) -> dict[str, dict[str, Any]]:
    expected = {str(row["stable_id"]) for row in group}
    rows_by_id = {str(row["stable_id"]): row for row in group}
    result: dict[str, dict[str, Any]] = {}
    for item in payload.get("segments", []):
        seg_id = str(item.get("id", ""))
        if seg_id not in expected or seg_id in result:
            continue
        source_kind = str(rows_by_id[seg_id]["kind_hint"])
        source_default = source_kind if source_kind in ALLOWED_KINDS else "narration"
        kind = _safe_choice(item.get("kind"), ALLOWED_KINDS, source_default)
        speaker = _canonical_speaker(item.get("speaker"))
        unresolved_thought_fallback = False
        if kind == "narration":
            speaker = "NARRATOR"
        elif kind == "thought" and speaker in {"NARRATOR", "UNKNOWN"}:
            if not allow_unresolved_thought_narrator:
                continue
            speaker = "NARRATOR"
            unresolved_thought_fallback = True
        else:
            speaker = _scope_local_speaker(speaker, rows_by_id[seg_id], local_scope)
        notes = str(item.get("notes", ""))[:500]
        if unresolved_thought_fallback:
            notes = (notes + "; " if notes else "") + "không xác định được người đang nghĩ; dùng người kể"
        result[seg_id] = {
            "kind": kind,
            "speaker": speaker,
            "gender": _safe_choice(item.get("gender"), ALLOWED_GENDERS, "unknown"),
            "age": _safe_choice(item.get("age"), ALLOWED_AGES, "unknown"),
            "emotion": _safe_choice(item.get("emotion"), ALLOWED_EMOTIONS, "neutral"),
            "intensity": max(0, min(3, int(item.get("intensity", 1)))),
            "pace": _safe_choice(item.get("pace"), ALLOWED_PACES, "normal"),
            "volume": _safe_choice(item.get("volume"), ALLOWED_VOLUMES, "normal"),
            "confidence": max(0.0, min(1.0, float(item.get("confidence", 0.5)))),
            "personality_hint": str(item.get("personality_hint", ""))[:300],
            "notes": notes[:500],
        }
    _repair_addressee_speakers(group, result, local_scope)
    return result


def _batch_id(index: int) -> str:
    return f"{BATCH_ID_PREFIX}{index:0{BATCH_ID_WIDTH}d}"


def _name_pronunciation_id(index: int) -> str:
    return f"{NAME_PRONUNCIATION_ID_PREFIX}{index:0{NAME_PRONUNCIATION_ID_WIDTH}d}"


def _name_candidate_key(value: str) -> str:
    return value.replace("’", "'").casefold()


def _name_candidate_contexts(rows: list[Any]) -> list[dict[str, Any]]:
    forms: dict[str, Counter[str]] = defaultdict(Counter)
    occurrences: Counter[str] = Counter()
    examples: dict[str, list[str]] = defaultdict(list)
    speaker_keys: set[str] = set()

    def register(surface: str, *, example: str = "", speaker: bool = False) -> None:
        value = surface.strip()
        if value.casefold().endswith(("'s", "’s")):
            value = value[:-2]
        key = _name_candidate_key(value)
        if len(value) < 2 or key in NAME_CANDIDATE_EXCLUSIONS:
            return
        forms[key][value] += 1
        occurrences[key] += 1
        if speaker:
            speaker_keys.add(key)
        normalized_example = " ".join(example.split())[:220]
        if normalized_example and normalized_example not in examples[key] and len(examples[key]) < 3:
            examples[key].append(normalized_example)

    for row in rows:
        speaker = _canonical_speaker(row["speaker"])
        if speaker.casefold() not in RESERVED_SPEAKERS and not is_local_speaker(speaker):
            for match in SPEAKER_NAME_TOKEN_PATTERN.finditer(speaker):
                register(match.group(1), speaker=True)

        text = str(row["text"])
        for match in NAME_TOKEN_PATTERN.finditer(text):
            start = max(0, match.start() - 80)
            end = min(len(text), match.end() + 80)
            register(match.group(1), example=text[start:end])

    candidates: list[dict[str, Any]] = []
    for key in sorted(forms):
        if key not in speaker_keys and occurrences[key] < NAME_PRONUNCIATION_MIN_OCCURRENCES:
            continue
        surface = sorted(
            forms[key],
            key=lambda value: (-forms[key][value], value.isupper(), value.casefold()),
        )[0]
        candidates.append(
            {
                "surface": surface,
                "occurrences": int(occurrences[key]),
                "is_speaker": key in speaker_keys,
                "examples": examples[key],
            }
        )
    return candidates


def _identity_reconciliation_items(
    rows: list[Any],
    chapter_titles: dict[int, str],
) -> list[dict[str, Any]]:
    eligible_indexes: dict[str, list[int]] = defaultdict(list)
    first_seen: dict[str, int] = {}
    for index, row in enumerate(rows):
        speaker = _canonical_speaker(row["speaker"])
        if speaker.casefold() in RESERVED_SPEAKERS or is_local_speaker(speaker) or not speaker:
            continue
        eligible_indexes[speaker].append(index)
        first_seen.setdefault(speaker, index)

    items: list[dict[str, Any]] = []
    for speaker in sorted(eligible_indexes, key=lambda name: first_seen[name]):
        indexes = eligible_indexes[speaker]
        edge_count = max(1, IDENTITY_CONTEXTS_PER_SPEAKER // 2)
        selected_indexes = list(dict.fromkeys(indexes[:edge_count] + indexes[-edge_count:]))
        examples: list[str] = []
        for center in selected_indexes:
            center_row = rows[center]
            chapter_id = int(center_row["chapter_id"])
            context_lines: list[str] = []
            start = max(0, center - IDENTITY_CONTEXT_RADIUS)
            end = min(len(rows), center + IDENTITY_CONTEXT_RADIUS + 1)
            for nearby in rows[start:end]:
                if int(nearby["chapter_id"]) != chapter_id:
                    continue
                nearby_speaker = _canonical_speaker(nearby["speaker"])
                nearby_text = " ".join(str(nearby["text"]).split())[:IDENTITY_CONTEXT_LINE_CHARS]
                context_lines.append(f"{nearby_speaker}: {nearby_text}")
            try:
                seq = int(center_row["seq"])
            except (KeyError, TypeError, ValueError):
                seq = center
            chapter_title = chapter_titles.get(chapter_id, str(chapter_id))
            excerpt = f"[chapter={chapter_title}; seq={seq}]\n" + "\n".join(context_lines)
            if excerpt not in examples:
                examples.append(excerpt)
        items.append({"name": speaker, "examples": examples})
    return items


def _cmu_pronunciations(surfaces: list[str]) -> dict[str, str]:
    targets = {_name_candidate_key(surface) for surface in surfaces}
    if not targets:
        return {}
    if not CMUDICT_PATH.is_file():
        raise RuntimeError(f"Thiếu dữ liệu phát âm tiếng Anh: {CMUDICT_PATH}")
    result: dict[str, str] = {}
    with CMUDICT_PATH.open("r", encoding="utf-8") as handle:
        for raw_line in handle:
            word, separator, raw_phones = raw_line.partition(" ")
            if not separator:
                continue
            key = re.sub(r"\(\d+\)$", "", word.strip().casefold())
            if key not in targets or key in result:
                continue
            phones = raw_phones.partition("#")[0].strip()
            if phones:
                result[key] = phones
            if len(result) == len(targets):
                break
    return result


def _arpabet_phones(pronunciation: str) -> tuple[str, ...]:
    return tuple(
        re.sub(r"\d+$", "", phone.strip().upper())
        for phone in pronunciation.split()
        if phone.strip()
    )


def _arpabet_syllables(
    phones: tuple[str, ...],
) -> list[tuple[tuple[str, ...], str, tuple[str, ...]]]:
    vowel_indexes = [index for index, phone in enumerate(phones) if phone in ARPABET_VOWELS]
    if not vowel_indexes:
        return []
    syllables: list[tuple[tuple[str, ...], str, tuple[str, ...]]] = []
    onset_start = 0
    for vowel_offset, vowel_index in enumerate(vowel_indexes):
        onset = phones[onset_start:vowel_index]
        if vowel_offset + 1 >= len(vowel_indexes):
            coda = phones[vowel_index + 1 :]
            next_onset_start = len(phones)
        else:
            next_vowel_index = vowel_indexes[vowel_offset + 1]
            between = phones[vowel_index + 1 : next_vowel_index]
            if len(between) >= 2 and between[0] in ARPABET_CODAS:
                coda = between[:1]
                next_onset_start = vowel_index + 2
            else:
                coda = ()
                next_onset_start = vowel_index + 1
        syllables.append((onset, phones[vowel_index], coda))
        onset_start = next_onset_start
    return syllables


def _arpabet_onset_reading(onset: tuple[str, ...], vowel: str) -> str:
    if not onset:
        return ""
    reading = ARPABET_ONSET_OVERRIDES.get(onset)
    if reading is None:
        reading = "".join(ARPABET_ONSETS.get(phone, "") for phone in onset)
    if reading == "c" and vowel in {"EH", "IH", "IY"}:
        return "k"
    if reading == "g" and vowel in {"EH", "IH", "IY"}:
        return "gh"
    if reading == "ng" and vowel in {"EH", "IH", "IY"}:
        return "ngh"
    return reading


def _arpabet_vowel_reading(
    onset: tuple[str, ...],
    vowel: str,
    coda: tuple[str, ...],
) -> str:
    if vowel == "AA" and coda[:1] == ("N",):
        return "ô"
    if vowel == "AH" and coda[:1] == ("N",):
        return "â"
    if vowel == "AH" and coda[:1] == ("L",):
        return "ồ" if onset == ("K",) else "e"
    return ARPABET_VOWEL_READINGS[vowel]


def _arpabet_coda_reading(
    onset: tuple[str, ...],
    vowel: str,
    coda: tuple[str, ...],
) -> str:
    if vowel == "AH" and coda[:1] == ("L",):
        return "" if onset == ("K",) else "n"
    return next((ARPABET_CODAS[phone] for phone in coda if phone in ARPABET_CODAS), "")


def _cmu_pronunciation_to_vietnamese(surface: str, pronunciation: str) -> str:
    """Convert CMU ARPAbet locally so known English names never depend on an LLM retry."""
    phones = _arpabet_phones(pronunciation)
    override = ARPABET_PRONUNCIATION_OVERRIDES.get(phones)
    if override is not None:
        return override
    rendered: list[str] = []
    for onset, vowel, coda in _arpabet_syllables(phones):
        onset_reading = _arpabet_onset_reading(onset, vowel)
        vowel_reading = _arpabet_vowel_reading(onset, vowel, coda)
        if onset_reading == "gi" and vowel_reading == "i":
            vowel_reading = ""
        rendered.append(
            onset_reading
            + vowel_reading
            + _arpabet_coda_reading(onset, vowel, coda)
        )
    spoken_form = "-".join(part for part in rendered if part)
    if not spoken_form:
        raise ValueError(f"CMU pronunciation has no readable vowel for {surface!r}: {pronunciation!r}")
    spoken_form = spoken_form[0].upper() + spoken_form[1:]
    if VIETNAMESE_SPOKEN_FORM_PATTERN.fullmatch(spoken_form) is None:
        raise ValueError(
            f"CMU pronunciation produced an invalid Vietnamese form for {surface!r}: {spoken_form!r}"
        )
    syllables = spoken_form.split("-")
    if any(NON_VIETNAMESE_SYLLABLE_CODA_PATTERN.search(syllable) for syllable in syllables):
        raise ValueError(
            f"CMU pronunciation produced an invalid Vietnamese coda for {surface!r}: {spoken_form!r}"
        )
    return spoken_form


def _valid_vietnamese_spoken_form(surface: str, spoken_form: str) -> bool:
    value = " ".join(spoken_form.strip().split())
    if not value or _name_candidate_key(value) == _name_candidate_key(surface):
        return False
    if VIETNAMESE_SPOKEN_FORM_PATTERN.fullmatch(value) is None:
        return False
    syllables = re.split(r"[ -]", value)
    if any(NON_VIETNAMESE_SYLLABLE_CODA_PATTERN.search(syllable) for syllable in syllables):
        return False
    return "-" in value or " " in value or any(ord(character) > 127 for character in value)


def _starts_with_vowel(value: str) -> bool:
    if not value:
        return False
    base_character = unicodedata.normalize("NFD", value[0])[0].casefold()
    return base_character in "aeiouy"


def _repair_vietnamese_syllable_boundaries(surface: str, spoken_form: str) -> str | None:
    value = " ".join(spoken_form.strip().split())
    syllables = re.split(r"[ -]", value)
    if len(syllables) < 2 or any(not syllable for syllable in syllables):
        return None
    changed_indexes: set[int] = set()
    for index in range(len(syllables) - 1):
        coda = NON_VIETNAMESE_SYLLABLE_CODA_PATTERN.search(syllables[index])
        if coda is None or not _starts_with_vowel(syllables[index + 1]):
            continue
        consonant = coda.group(0)
        syllables[index] = syllables[index][:-1]
        syllables[index + 1] = consonant + syllables[index + 1]
        if not syllables[index]:
            return None
        changed_indexes.update((index, index + 1))
    if not changed_indexes:
        return None
    for index in changed_indexes:
        syllable = syllables[index]
        if len(syllable) >= 2 and syllable[0].casefold() == "d" and _starts_with_vowel(syllable[1:]):
            syllables[index] = ("Đ" if syllable[0].isupper() else "đ") + syllable[1:]
    repaired = "-".join(syllables)
    return repaired if _valid_vietnamese_spoken_form(surface, repaired) else None


def _output_schema_for_batch(batch_ids: list[str]) -> dict[str, Any]:
    schema = copy.deepcopy(OUTPUT_SCHEMA)
    segments = schema["properties"]["segments"]
    segments["minItems"] = len(batch_ids)
    segments["maxItems"] = len(batch_ids)
    segments["items"]["properties"]["id"]["enum"] = batch_ids
    pronunciations = schema["properties"]["pronunciations"]
    pronunciations["maxItems"] = min(
        MAX_PRONUNCIATIONS_PER_BATCH,
        max(8, len(batch_ids) * 2),
    )
    return schema


def _name_pronunciation_schema(batch_ids: list[str]) -> dict[str, Any]:
    schema = copy.deepcopy(NAME_PRONUNCIATION_SCHEMA)
    names = schema["properties"]["names"]
    names["minItems"] = len(batch_ids)
    names["maxItems"] = len(batch_ids)
    names["items"]["properties"]["id"]["enum"] = batch_ids
    return schema


def _analysis_output_token_limit(segment_count: int, num_ctx: int) -> int:
    requested = max(
        ANALYSIS_OUTPUT_MIN_TOKENS,
        ANALYSIS_OUTPUT_BASE_TOKENS + segment_count * ANALYSIS_OUTPUT_TOKENS_PER_SEGMENT,
    )
    context_limit = max(ANALYSIS_OUTPUT_MIN_TOKENS, num_ctx // 2)
    return min(requested, context_limit, ANALYSIS_OUTPUT_MAX_TOKENS)


class OllamaBookAnalyzer:
    def __init__(self, settings: dict[str, Any], db: ProjectDB, log: Callable[[str], None]) -> None:
        self.settings = settings["analysis"]
        self.allow_downloads = bool(settings.get("safety", {}).get("allow_network_downloads_during_job", False))
        self.db = db
        self.log = log
        self.base_url = str(self.settings["base_url"]).rstrip("/")
        self.model = str(self.settings["model"])
        self.session = requests.Session()
        self._managed_ollama_process: subprocess.Popen[bytes] | None = None
        self._managed_ollama_log_path: Path | None = None
        existing = self.db.list_segments(statuses=("analyzed", "warning", "signal_passed", "asr_passed", "verified"))
        self._speaker_counts = Counter(
            str(row["speaker"])
            for row in existing
            if str(row["speaker"]).casefold() not in RESERVED_SPEAKERS
            and not is_local_speaker(row["speaker"])
        )
        self._chapter_titles = {
            int(row["id"]): str(row["title"]) for row in self.db.list_chapters()
        }

    def _available(self) -> bool:
        try:
            return self.session.get(f"{self.base_url}/api/tags", timeout=5).ok
        except requests.RequestException:
            return False

    def ensure_available(self) -> bool:
        if not self.settings.get("enabled", True):
            return False
        executable = shutil.which("ollama")
        if not self._available():
            if not executable:
                return False
            try:
                runtime_root = Path(os.environ.get("EBOOK_READER_RUNTIME") or DEFAULT_RUNTIME_ROOT)
                ollama_log_path = runtime_root / "logs" / OLLAMA_LOG_FILENAME
                ollama_log_path.parent.mkdir(parents=True, exist_ok=True)
                with ollama_log_path.open("ab", buffering=0) as ollama_log:
                    started_at = time.strftime("%Y-%m-%d %H:%M:%S")
                    ollama_log.write(f"\n--- Ebook Reader started Ollama at {started_at} ---\n".encode())
                    self._managed_ollama_process = subprocess.Popen(
                        [executable, "serve"],
                        stdout=ollama_log,
                        stderr=subprocess.STDOUT,
                        creationflags=(
                            getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
                        ),
                    )
                self._managed_ollama_log_path = ollama_log_path
                self.log(f"Ebook Reader đã tự khởi động Ollama ẩn. Log kỹ thuật: {ollama_log_path}")
            except OSError:
                return False
            for _ in range(30):
                if self._available():
                    break
                time.sleep(1)
            else:
                self._stop_managed_ollama()
                return False
        try:
            response = self.session.get(f"{self.base_url}/api/tags", timeout=10)
            names = {str(item.get("name", "")) for item in response.json().get("models", [])}
            if self.model in names or any(name.split(":", 1)[0] == self.model for name in names):
                return True
        except requests.RequestException:
            return False
        if not executable or not self.allow_downloads:
            self.log(
                f"Thiếu Ollama model {self.model}. Job không được tự tải model sau khi đã bắt đầu; "
                "hãy mở lại Ebook Reader để kiểm tra/cài model."
            )
            return False
        self.log(f"Đang tải Ollama model {self.model} theo policy đã cho phép.")
        try:
            subprocess.run([executable, "pull", self.model], check=True)
            return True
        except (OSError, subprocess.CalledProcessError):
            return False

    def _known_summary(self) -> str:
        if not self._speaker_counts:
            return "(Chưa có nhân vật đã biết)"
        return "\n".join(
            f"- {name}; số lần đã gặp={count}" for name, count in self._speaker_counts.most_common(80)
        )

    def _stream_json_response(
        self,
        request: dict[str, Any],
        *,
        stop_requested: Callable[[], bool] | None = None,
        activity: Callable[[int, int], None] | None = None,
    ) -> dict[str, Any]:
        if stop_requested is not None and stop_requested():
            raise AnalysisRequestStopped("Stop requested before Ollama request")
        wall_timeout = min(
            float(self.settings.get("timeout_seconds", ANALYSIS_REQUEST_MAX_SECONDS)),
            ANALYSIS_REQUEST_MAX_SECONDS,
        )
        started = time.monotonic()
        last_activity = started
        parts: list[str] = []
        response: requests.Response | None = None
        completed = False
        request["stream"] = True
        try:
            response = self.session.post(
                f"{self.base_url}/api/generate",
                json=request,
                timeout=(10.0, min(ANALYSIS_STREAM_IDLE_SECONDS, wall_timeout)),
                stream=True,
            )
            response.raise_for_status()
            response.encoding = "utf-8"
            for raw_line in response.iter_lines(decode_unicode=True):
                if stop_requested is not None and stop_requested():
                    raise AnalysisRequestStopped("Stop requested during Ollama request")
                now = time.monotonic()
                elapsed = now - started
                if elapsed > wall_timeout:
                    raise TimeoutError(
                        f"Ollama analysis exceeded {wall_timeout:.0f}s wall-time limit"
                    )
                if raw_line:
                    line = raw_line.decode("utf-8") if isinstance(raw_line, bytes) else raw_line
                    envelope = json.loads(line)
                    if envelope.get("error"):
                        raise RuntimeError(str(envelope["error"]))
                    parts.append(str(envelope.get("response", "")))
                    completed = bool(envelope.get("done", False))
                if activity is not None and now - last_activity >= ANALYSIS_ACTIVITY_SECONDS:
                    activity(int(elapsed), sum(len(part) for part in parts))
                    last_activity = now
            if not completed:
                response_chars = sum(len(part) for part in parts)
                raise OllamaStreamIncompleteError(
                    "Ollama stream ended before the JSON response was complete "
                    f"({response_chars:,} response chars)"
                )
        finally:
            if response is not None:
                response.close()
        return json.loads("".join(parts) or "{}")

    def _request(
        self,
        group: list[Any],
        *,
        stop_requested: Callable[[], bool] | None = None,
        activity: Callable[[int, int], None] | None = None,
    ) -> dict[str, Any]:
        chapter_titles: list[str] = []
        rows: list[dict[str, Any]] = []
        batch_to_stable: dict[str, str] = {}
        for index, row in enumerate(group, 1):
            chapter_title = self._chapter_titles.get(int(row["chapter_id"]), "")
            if chapter_title not in chapter_titles:
                chapter_titles.append(chapter_title)
            batch_id = _batch_id(index)
            batch_to_stable[batch_id] = str(row["stable_id"])
            try:
                paragraph_index = int(row["paragraph_index"])
            except (KeyError, TypeError):
                paragraph_index = 0
            rows.append(
                {
                    "id": batch_id,
                    "paragraph": paragraph_index,
                    "hint": row["kind_hint"],
                    "text": row["text"],
                }
            )
        prompt = (
            f"Các chương hiện tại: {', '.join(chapter_titles)}\n\n"
            f"Nhân vật đã biết từ các phần trước:\n{self._known_summary()}\n\n"
            f"Các đoạn liên tiếp:\n{json.dumps(rows, ensure_ascii=False, indent=2)}"
        )
        request = {
            "model": self.model,
            "system": SYSTEM_PROMPT,
            "prompt": prompt,
            "format": _output_schema_for_batch(list(batch_to_stable)),
            "keep_alive": "30m",
            "options": {
                "temperature": float(self.settings.get("temperature", 0.1)),
                "num_ctx": int(self.settings.get("num_ctx", 16384)),
                "num_predict": _analysis_output_token_limit(
                    len(group),
                    int(self.settings.get("num_ctx", 16384)),
                ),
            },
        }
        payload = self._stream_json_response(
            request,
            stop_requested=stop_requested,
            activity=activity,
        )
        segments = payload.get("segments", [])
        if isinstance(segments, list):
            for item in segments:
                if not isinstance(item, dict):
                    continue
                batch_id = str(item.get("id", ""))
                if batch_id in batch_to_stable:
                    item["id"] = batch_to_stable[batch_id]
        return payload

    def _checkpoint_pronunciations(self, group: list[Any], payload: dict[str, Any]) -> None:
        source_text = "\n".join(str(row["text"]) for row in group)
        raw_items = payload.get("pronunciations", [])
        if not isinstance(raw_items, list):
            return
        for item in raw_items:
            if not isinstance(item, dict):
                continue
            surface = str(item.get("surface", "")).strip()[:160]
            spoken_form = str(item.get("spoken_form", "")).strip()[:240]
            try:
                confidence = max(0.0, min(1.0, float(item.get("confidence", 0.0))))
            except (TypeError, ValueError):
                continue
            if not surface or not spoken_form or surface not in source_text:
                continue
            if surface.casefold() == spoken_form.casefold():
                continue
            normalized_surface = " ".join(surface.casefold().split())
            self.db.upsert_pronunciation(
                surface=surface,
                normalized_surface=normalized_surface,
                spoken_form=spoken_form,
                confidence=confidence,
            )

    def analyze_all(
        self,
        stop_requested: Callable[[], bool],
        progress: Callable[[int, int], None] | None = None,
        before_batch: Callable[[int], None] | None = None,
    ) -> None:
        all_rows = self.db.list_segments()
        pending = [row for row in all_rows if row["status"] == "pending"]
        if not pending:
            self.log("Toàn bộ segment đã có checkpoint phân tích.")
            return
        llm_ready = self.ensure_available()
        if not llm_ready:
            if self.settings.get("enabled", True) and self.settings.get("required", True):
                raise RuntimeError(
                    f"Ollama/Qwen model {self.model} không sẵn sàng. "
                    "Pipeline dừng thay vì âm thầm hạ chất lượng phân tích toàn book."
                )
            self.log("Phân tích AI bị tắt/không bắt buộc; dùng heuristic và đánh warning, không dừng hỏi người dùng.")
        max_segments = int(self.settings.get("batch_segments", 28))
        max_chars = int(self.settings.get("batch_chars", 6200))
        groups: list[list[Any]] = []
        current: list[Any] = []
        chars = 0
        for row in pending:
            text_len = len(str(row["text"]))
            if current and (len(current) >= max_segments or chars + text_len > max_chars):
                groups.append(current)
                current = []
                chars = 0
            current.append(row)
            chars += text_len
        if current:
            groups.append(current)

        done = len(all_rows) - len(pending)
        total = len(all_rows)
        required = bool(self.settings.get("enabled", True) and self.settings.get("required", True))
        confidence_threshold = float(self.settings.get("low_confidence_threshold", 0.58))
        retry_count = int(self.settings.get("max_retries", 3))
        group_offset = 0
        while group_offset < len(groups):
            group_index = group_offset + 1
            group = groups[group_offset]
            if stop_requested():
                return
            if before_batch is not None:
                before_batch(group_index)
            validated: dict[str, dict[str, Any]] = {}
            payload: dict[str, Any] = {}
            last_error = "AI analysis is unavailable"
            split_incomplete_stream = False
            if llm_ready:
                for attempt in range(retry_count):
                    attempt_number = attempt + 1
                    self.log(
                        f"Đang phân tích batch {group_index}/{len(groups)} của phần còn lại: "
                        f"{len(group)} segment, lần {attempt_number}/{retry_count}."
                    )
                    try:
                        payload = self._request(
                            group,
                            stop_requested=stop_requested,
                            activity=lambda elapsed, chars, batch=group_index, current=attempt_number: self.log(
                                f"Phân tích batch {batch}/{len(groups)} lần {current}/{retry_count} "
                                f"vẫn đang chạy: {elapsed}s, đã nhận {chars:,} ký tự JSON."
                            ),
                        )
                        validated = _validate(group, payload, local_scope=f"b{group_index:04d}")
                        if len(validated) == len(group):
                            break
                        last_error = f"LLM returned {len(validated)}/{len(group)} IDs"
                    except AnalysisRequestStopped:
                        raise
                    except OllamaStreamIncompleteError as exc:
                        last_error = str(exc)
                        if len(group) > 1:
                            self.log(
                                f"Phân tích batch {group_index} lỗi lần {attempt_number}: "
                                f"{last_error}"
                            )
                            midpoint = len(group) // 2
                            first_half = group[:midpoint]
                            second_half = group[midpoint:]
                            groups[group_offset : group_offset + 1] = [first_half, second_half]
                            self.log(
                                f"Stream batch {group_index} bị ngắt; tự chia thành "
                                f"{len(first_half)} + {len(second_half)} segment. "
                                f"Tổng số batch còn lại hiện là {len(groups)}."
                            )
                            split_incomplete_stream = True
                            break
                    except Exception as exc:  # noqa: BLE001
                        last_error = str(exc)
                    self.log(f"Phân tích batch {group_index} lỗi lần {attempt_number}: {last_error}")
                    time.sleep(min(8, 2 ** attempt))
            if split_incomplete_stream:
                continue
            if len(validated) != len(group) and payload:
                fallback_validated = _validate(
                    group,
                    payload,
                    local_scope=f"b{group_index:04d}",
                    allow_unresolved_thought_narrator=True,
                )
                fallback_count = sum(
                    data["kind"] == "thought" and data["speaker"] == "NARRATOR"
                    for data in fallback_validated.values()
                )
                if len(fallback_validated) == len(group) and fallback_count:
                    validated = fallback_validated
                    message = (
                        f"Sau {retry_count} lần phân tích batch {group_index}, còn {fallback_count} "
                        "đoạn nội tâm không xác định được nhân vật; dùng giọng người kể."
                    )
                    self.log(message)
                    self.db.event(
                        "warning",
                        "THOUGHT_SPEAKER_NARRATOR_FALLBACK",
                        message,
                        {
                            "batch_index": group_index,
                            "fallback_segments": fallback_count,
                        },
                    )
            if len(validated) != len(group) and required:
                message = (
                    f"Phân tích bắt buộc thất bại ở batch {group_index}: "
                    f"nhận {len(validated)}/{len(group)} segment; lỗi cuối: {last_error}"
                )
                self.db.event(
                    "critical",
                    "REQUIRED_ANALYSIS_BATCH_FAILED",
                    message,
                    {
                        "batch_index": group_index,
                        "expected_segments": len(group),
                        "validated_segments": len(validated),
                    },
                )
                raise RuntimeError(message)
            repaired_addressee_ids = [
                seg_id
                for seg_id, data in validated.items()
                if ADDRESSEE_REPAIR_NOTE in str(data.get("notes", ""))
            ]
            if repaired_addressee_ids:
                message = (
                    f"Đã sửa {len(repaired_addressee_ids)} segment trong batch {group_index}: "
                    "tên người được gọi không còn bị dùng làm người nói."
                )
                self.log(message)
                self.db.event(
                    "warning",
                    "ADDRESSEE_SPEAKER_REPAIRED",
                    message,
                    {
                        "batch_index": group_index,
                        "segment_ids": repaired_addressee_ids,
                    },
                )
            if validated:
                self._checkpoint_pronunciations(group, payload)
            for row in group:
                data = validated.get(str(row["stable_id"])) or _heuristic(row)
                if (
                    float(data.get("confidence", 0.0)) < confidence_threshold
                    and self.settings.get("low_confidence_policy") == "fail"
                ):
                    raise RuntimeError(
                        f"Analysis confidence is below the locked threshold for {row['stable_id']}"
                    )
                self.db.update_analysis(
                    int(row["id"]),
                    data,
                    low_confidence_threshold=confidence_threshold,
                )
                speaker = _canonical_speaker(data.get("speaker", "UNKNOWN"))
                if (
                    speaker.casefold() not in RESERVED_SPEAKERS
                    and not is_local_speaker(speaker)
                    and speaker
                ):
                    self._speaker_counts[speaker] += 1
                done += 1
                if progress:
                    progress(done, total)
            self.log(f"Đã checkpoint phân tích {done:,}/{total:,} segment.")
            group_offset += 1

    def reconcile_name_pronunciations(
        self,
        before_batch: Callable[[int], None] | None = None,
        stop_requested: Callable[[], bool] | None = None,
    ) -> int:
        """Lock Vietnamese phonetic spellings for recurring English and western fantasy names."""
        if not self.settings.get("enabled", True):
            return 0
        rows = [row for row in self.db.list_segments() if str(row["status"]) != "pending"]
        existing = {
            _name_candidate_key(str(row["surface"]))
            for row in self.db.list_pronunciations()
            if bool(row["locked"])
        }
        minimum_confidence = float(self.settings.get("low_confidence_threshold", 0.58))
        candidates = [
            candidate
            for candidate in _name_candidate_contexts(rows)
            if _name_candidate_key(str(candidate["surface"])) not in existing
        ]
        if not candidates:
            self.log("Không còn tên tiếng Anh cần chuẩn hóa cách đọc.")
            return 0
        dictionary_pronunciations = _cmu_pronunciations(
            [str(candidate["surface"]) for candidate in candidates]
        )
        for candidate in candidates:
            candidate_key = _name_candidate_key(str(candidate["surface"]))
            candidate["cmu_pronunciation"] = (
                ""
                if candidate_key in CMUDICT_CONTEXT_ONLY
                else dictionary_pronunciations.get(candidate_key, "")
            )

        converted_count = 0

        def checkpoint_pronunciation(
            candidate: dict[str, Any],
            spoken_form: str,
            confidence: float,
            *,
            repaired_from: str = "",
        ) -> None:
            nonlocal converted_count
            surface = str(candidate["surface"])
            if repaired_from:
                message = (
                    f"Đã tự sửa ranh giới âm tiết cho {surface}: "
                    f"{repaired_from} → {spoken_form}."
                )
                self.log(message)
                self.db.event(
                    "warning",
                    "NAME_PRONUNCIATION_BOUNDARY_REPAIRED",
                    message,
                    {
                        "surface": surface,
                        "rejected_spoken_form": repaired_from,
                        "spoken_form": spoken_form,
                    },
                )
            if confidence < minimum_confidence:
                self.db.event(
                    "warning",
                    "NAME_PRONUNCIATION_LOW_CONFIDENCE",
                    f"Cách đọc thuần Việt cho {surface} có độ tin cậy thấp nhưng vẫn được khóa theo sách",
                    {"surface": surface, "spoken_form": spoken_form, "confidence": confidence},
                )
            self.db.upsert_pronunciation(
                surface=surface,
                normalized_surface=_name_candidate_key(surface),
                spoken_form=spoken_form,
                confidence=confidence,
                source=(
                    CONTEXTUAL_ENGLISH_NAME_PRONUNCIATION_SOURCE
                    if _name_candidate_key(surface) in CMUDICT_CONTEXT_ONLY
                    else ENGLISH_NAME_PRONUNCIATION_SOURCE
                ),
                locked=True,
            )
            converted_count += 1

        qwen_candidates: list[dict[str, Any]] = []
        cmu_count = 0
        for candidate in candidates:
            pronunciation = str(candidate.get("cmu_pronunciation", ""))
            if not pronunciation:
                qwen_candidates.append(candidate)
                continue
            surface = str(candidate["surface"])
            spoken_form = _cmu_pronunciation_to_vietnamese(surface, pronunciation)
            checkpoint_pronunciation(
                candidate,
                spoken_form,
                CMUDICT_TRANSLITERATION_CONFIDENCE,
            )
            cmu_count += 1
        if cmu_count:
            self.log(
                f"Đã chuẩn hóa cục bộ {cmu_count} tên từ âm vị CMUdict; "
                "không gửi các tên này cho Qwen."
            )
        if not qwen_candidates:
            self.log(
                f"Đã khóa cách đọc thuần Việt cho {converted_count}/{len(candidates)} "
                "tên tiếng Anh hoặc fantasy cần xem xét."
            )
            return converted_count
        if not self.ensure_available():
            message = "Ollama không còn sẵn sàng để chuẩn hóa cách đọc tên fantasy"
            self.db.event("error", "NAME_PRONUNCIATION_UNAVAILABLE", message)
            if self.settings.get("enabled", True) and self.settings.get("required", True):
                raise RuntimeError(message)
            return converted_count

        retry_count = int(self.settings.get("max_retries", 3))
        for batch_index, offset in enumerate(
            range(0, len(qwen_candidates), NAME_PRONUNCIATION_BATCH_SIZE),
            1,
        ):
            if before_batch is not None:
                before_batch(batch_index)
            batch = qwen_candidates[offset : offset + NAME_PRONUNCIATION_BATCH_SIZE]
            pending = {
                _name_pronunciation_id(index): candidate
                for index, candidate in enumerate(batch, 1)
            }
            feedback: dict[str, str] = {}
            last_error = ""
            for attempt in range(retry_count):
                if not pending:
                    break
                attempt_number = attempt + 1
                request_items = [
                    {"id": item_id, **candidate}
                    for item_id, candidate in pending.items()
                ]
                prompt = (
                    "Xác định và chuyển cách đọc tên riêng cho audiobook tiếng Việt. Với tên tiếng Anh hoặc "
                    "tên fantasy phương Tây viết chữ Latin, convert=true và spoken_form là cách ghi âm tiết "
                    "thuần Việt gần với cách phát âm tự nhiên; có thể dùng dấu tiếng Việt và dấu gạch nối. "
                    "cmu_pronunciation là chuỗi âm vị ARPAbet từ từ điển tiếng Anh: nếu trường này không rỗng "
                    "thì bắt buộc convert=true và phải dựa vào chuỗi âm vị đó, không được gọi tên này là tiếng Việt. "
                    "Không dịch nghĩa, không trả IPA, không thêm chú thích vào spoken_form. Ví dụ: "
                    "Michael→Mai-cồ, Benjamin→Ben-gia-min, Gary→Ga-ri, Corella→Cô-ren-la, "
                    "Aderon→A-đe-ron. Mỗi phần ngăn bằng gạch nối phải là một âm tiết người Việt đọc được; "
                    "không để lại âm tiết kiểu Anh như rel, der, th, sh. Với tên thuần Việt hoặc từ phổ thông, "
                    "convert=false và lặp nguyên surface vào spoken_form. Phải trả đúng một kết quả cho từng ID."
                )
                if feedback:
                    rejected = [
                        {
                            "id": item_id,
                            "surface": pending[item_id]["surface"],
                            "rejected_reason": feedback[item_id],
                        }
                        for item_id in pending
                    ]
                    prompt += (
                        "\n\nCác kết quả dưới đây đã bị validator từ chối. Không được lặp lại đáp án cũ; "
                        "hãy sửa đúng lỗi âm tiết được nêu:\n"
                        + json.dumps(rejected, ensure_ascii=False, indent=2)
                    )
                prompt += "\n\n" + json.dumps(request_items, ensure_ascii=False, indent=2)
                num_ctx = int(self.settings.get("num_ctx", 16384))
                request = {
                    "model": self.model,
                    "system": (
                        "Bạn là biên tập viên phát âm tên riêng cho TTS tiếng Việt. "
                        "Ưu tiên cách đọc thuần Việt dễ nghe và trả JSON đúng schema."
                    ),
                    "prompt": prompt,
                    "format": _name_pronunciation_schema(list(pending)),
                    "keep_alive": "10m",
                    "options": {
                        "temperature": 0.0 if attempt == 0 else 0.2,
                        "num_ctx": num_ctx,
                        "num_predict": _analysis_output_token_limit(len(pending), num_ctx),
                    },
                }
                self.log(
                    f"Đang chuẩn hóa tên tiếng Anh batch {batch_index}: "
                    f"{len(pending)} tên còn lại, lần {attempt_number}/{retry_count}."
                )
                try:
                    payload = self._stream_json_response(
                        request,
                        stop_requested=stop_requested,
                        activity=lambda elapsed, chars, batch_no=batch_index, current=attempt_number: self.log(
                            f"Chuẩn hóa tên batch {batch_no} lần {current}/{retry_count} "
                            f"vẫn đang chạy: {elapsed}s, đã nhận {chars:,} ký tự JSON."
                        ),
                    )
                    raw_names = payload.get("names", [])
                    if not isinstance(raw_names, list):
                        raise ValueError("response names is not a list")
                    by_id: dict[str, dict[str, Any]] = {}
                    for item in raw_names:
                        if not isinstance(item, dict):
                            raise ValueError("response contains a non-object name item")
                        item_id = str(item.get("id", ""))
                        if item_id not in pending or item_id in by_id:
                            raise ValueError(f"invalid or duplicate name ID: {item_id!r}")
                        by_id[item_id] = item
                    if set(by_id) != set(pending):
                        missing = sorted(set(pending) - set(by_id))
                        raise ValueError(f"response omitted name IDs: {missing}")

                    item_errors: dict[str, str] = {}
                    resolved_ids: list[str] = []
                    for item_id, candidate in pending.items():
                        item = by_id[item_id]
                        try:
                            must_convert = bool(candidate.get("cmu_pronunciation"))
                            should_convert = bool(item.get("convert", False))
                            if must_convert and not should_convert:
                                raise ValueError(
                                    f"dictionary English name was not converted: {candidate['surface']!r}"
                                )
                            if not should_convert:
                                surface = str(candidate["surface"])
                                confidence = max(
                                    0.0,
                                    min(1.0, float(item.get("confidence", 0.0))),
                                )
                                checkpoint_pronunciation(candidate, surface, confidence)
                                resolved_ids.append(item_id)
                                continue
                            spoken_form = " ".join(
                                str(item.get("spoken_form", "")).strip().split()
                            )
                            surface = str(candidate["surface"])
                            confidence = max(
                                0.0,
                                min(1.0, float(item.get("confidence", 0.0))),
                            )
                            if _valid_vietnamese_spoken_form(surface, spoken_form):
                                checkpoint_pronunciation(candidate, spoken_form, confidence)
                                resolved_ids.append(item_id)
                                continue
                            repaired = _repair_vietnamese_syllable_boundaries(surface, spoken_form)
                            if repaired is None:
                                raise ValueError(
                                    f"invalid Vietnamese spoken form for {surface!r}: {spoken_form!r}"
                                )
                            checkpoint_pronunciation(
                                candidate,
                                repaired,
                                min(confidence, AUTOMATIC_PRONUNCIATION_REPAIR_CONFIDENCE),
                                repaired_from=spoken_form,
                            )
                            resolved_ids.append(item_id)
                        except Exception as exc:  # noqa: BLE001
                            item_errors[item_id] = str(exc)
                    for item_id in resolved_ids:
                        pending.pop(item_id, None)
                    feedback = item_errors
                    if not pending:
                        break
                    last_error = "; ".join(feedback[item_id] for item_id in pending)
                except AnalysisRequestStopped:
                    raise
                except Exception as exc:  # noqa: BLE001
                    last_error = str(exc)
                    feedback = {}
                self.log(
                    f"Chuẩn hóa tên batch {batch_index} còn {len(pending)} tên lỗi "
                    f"sau lần {attempt_number}: {last_error}"
                )
                time.sleep(min(8, 2 ** attempt))

            if pending:
                remaining = [str(candidate["surface"]) for candidate in pending.values()]
                message = (
                    f"Chuẩn hóa cách đọc tên thất bại ở batch {batch_index}, "
                    f"còn lỗi {remaining}: {last_error}"
                )
                self.db.event("error", "NAME_PRONUNCIATION_FAILED", message)
                if self.settings.get("enabled", True) and self.settings.get("required", True):
                    raise RuntimeError(message)

        self.log(
            f"Đã khóa cách đọc thuần Việt cho {converted_count}/{len(candidates)} "
            "tên tiếng Anh hoặc fantasy cần xem xét."
        )
        return converted_count

    def reconcile_aliases(
        self,
        before_batch: Callable[[int], None] | None = None,
        stop_requested: Callable[[], bool] | None = None,
    ) -> dict[str, str]:
        """Conservative full-book reconciliation. It never merges low-confidence names automatically."""
        rows = [row for row in self.db.list_segments() if str(row["status"]) != "pending"]
        items = _identity_reconciliation_items(rows, self._chapter_titles)
        if len(items) < 2:
            return {}
        max_candidates = int(self.settings.get("max_alias_candidates", 400))
        if len(items) > max_candidates:
            message = (
                f"Alias reconciliation has {len(items)} candidates, above the locked safe limit "
                f"of {max_candidates}"
            )
            self.db.event("error", "ALIAS_CANDIDATE_LIMIT_EXCEEDED", message)
            if self.settings.get("enabled", True) and self.settings.get("required", True):
                raise RuntimeError(message)
            return {}
        if not self.ensure_available():
            if self.settings.get("enabled", True) and self.settings.get("required", True):
                raise RuntimeError("Ollama became unavailable before required alias reconciliation")
            return {}
        alias_map: dict[str, str] = {}
        all_names = [item["name"] for item in items]
        # Keep requests bounded. Only high-confidence merges are applied automatically.
        for batch_index, offset in enumerate(
            range(0, len(items), ALIAS_RECONCILIATION_BATCH_SIZE),
            1,
        ):
            if before_batch is not None:
                before_batch(batch_index)
            batch = items[offset : offset + ALIAS_RECONCILIATION_BATCH_SIZE]
            prompt = (
                "Hợp nhất bí danh của cùng một nhân vật trong audiobook dựa trên ngữ cảnh lân cận của toàn sách. "
                "Tên trước và sau khi chuyển sinh, trọng sinh, đổi thân phận, đổi tên hoặc dùng bí danh phải được "
                "xem là cùng một người khi ngữ cảnh xác nhận rõ. Ví dụ một nhân vật chôn ký ức quá khứ rồi chấp "
                "nhận tên/thân phận mới là một identity, không phải hai nhân vật. Không gộp đại từ chung như hắn, "
                "nàng, cô ấy; không gộp người nói với người chỉ được gọi tên trong lời thoại. Chỉ trả nhóm khi chắc "
                "chắn từ ngữ cảnh. Canonical phải là tên rõ nhất hoặc tên hiện tại trong aliases.\n\n"
                f"Toàn bộ tên ứng viên trong sách: {json.dumps(all_names, ensure_ascii=False)}\n\n"
                + json.dumps(batch, ensure_ascii=False, indent=2)
            )
            response_schema = copy.deepcopy(RECONCILE_SCHEMA)
            groups_schema = response_schema["properties"]["groups"]
            groups_schema["maxItems"] = len(batch)
            groups_schema["items"]["properties"]["aliases"]["maxItems"] = len(all_names)
            num_ctx = int(self.settings.get("num_ctx", 16384))
            request = {
                "model": self.model,
                "system": "Bạn là biên tập viên nhất quán nhân vật. Trả JSON đúng schema.",
                "prompt": prompt,
                "format": response_schema,
                "keep_alive": "10m",
                "options": {
                    "temperature": 0.0,
                    "num_ctx": num_ctx,
                    "num_predict": _analysis_output_token_limit(len(batch), num_ctx),
                },
            }
            last_error = ""
            payload: dict[str, Any] | None = None
            retry_count = int(self.settings.get("max_retries", 3))
            for attempt in range(retry_count):
                attempt_number = attempt + 1
                self.log(
                    f"Đang hợp nhất bí danh batch {batch_index}: "
                    f"{len(batch)} nhân vật, lần {attempt_number}/{retry_count}."
                )
                try:
                    payload = self._stream_json_response(
                        request,
                        stop_requested=stop_requested,
                        activity=lambda elapsed, chars, batch_no=batch_index, current=attempt_number: self.log(
                            f"Hợp nhất bí danh batch {batch_no} lần {current}/{retry_count} "
                            f"vẫn đang chạy: {elapsed}s, đã nhận {chars:,} ký tự JSON."
                        ),
                    )
                    break
                except AnalysisRequestStopped:
                    raise
                except Exception as exc:  # noqa: BLE001
                    last_error = str(exc)
                    time.sleep(min(8, 2 ** attempt))
            if payload is None:
                self.db.event("warning", "ALIAS_RECONCILIATION_FAILED", last_error)
                if self.settings.get("enabled", True) and self.settings.get("required", True):
                    raise RuntimeError(
                        f"Required alias reconciliation failed in batch {batch_index}: {last_error}"
                    )
                continue
            try:
                for group in payload.get("groups", []):
                    confidence = float(group.get("confidence", 0))
                    aliases = [_canonical_speaker(x) for x in group.get("aliases", []) if str(x).strip()]
                    canonical = _canonical_speaker(group.get("canonical", ""))
                    if confidence < 0.86 or canonical not in aliases or len(aliases) < 2:
                        continue
                    if any(alias.casefold() in RESERVED_SPEAKERS for alias in aliases):
                        continue
                    if any(alias not in all_names for alias in aliases):
                        continue
                    conflicts = {
                        alias: alias_map[alias]
                        for alias in aliases
                        if alias in alias_map and alias_map[alias] != canonical
                    }
                    if conflicts:
                        message = f"Conflicting alias groups for {canonical}: {conflicts}"
                        self.db.event("error", "ALIAS_RECONCILIATION_CONFLICT", message)
                        if self.settings.get("enabled", True) and self.settings.get("required", True):
                            raise RuntimeError(message)
                        continue
                    for alias in aliases:
                        if alias != canonical:
                            alias_map[alias] = canonical
                    self.db.event(
                        "info",
                        "ALIAS_RECONCILIATION_APPLIED",
                        f"High-confidence alias group: {canonical}",
                        {"canonical": canonical, "aliases": aliases, "confidence": confidence},
                    )
            except Exception as exc:  # noqa: BLE001
                self.db.event("warning", "ALIAS_RECONCILIATION_FAILED", str(exc))
                if self.settings.get("enabled", True) and self.settings.get("required", True):
                    raise RuntimeError(
                        f"Required alias reconciliation returned invalid data in batch {batch_index}: {exc}"
                    ) from exc
        # Resolve transitive mappings deterministically so A→B and B→C cannot leave A at B.
        resolved: dict[str, str] = {}
        for alias in sorted(alias_map, key=str.casefold):
            canonical = alias_map[alias]
            visited = {alias}
            while canonical in alias_map and canonical not in visited:
                visited.add(canonical)
                canonical = alias_map[canonical]
            if canonical not in visited:
                resolved[alias] = canonical
        return resolved

    def release_model(self) -> None:
        """Unload Qwen from Ollama VRAM while keeping the HTTP session reusable."""
        try:
            self.session.post(
                f"{self.base_url}/api/generate",
                json={"model": self.model, "prompt": "", "keep_alive": 0},
                timeout=20,
            )
        except requests.RequestException:
            pass

    def _stop_managed_ollama(self) -> None:
        process = self._managed_ollama_process
        self._managed_ollama_process = None
        if process is None or process.poll() is not None:
            return
        terminate_process_tree(process.pid, grace_seconds=3.0)
        self.log("Đã dừng Ollama ẩn do Ebook Reader tự khởi động.")

    def unload(self) -> None:
        try:
            self.release_model()
        finally:
            self.session.close()
            self._stop_managed_ollama()
