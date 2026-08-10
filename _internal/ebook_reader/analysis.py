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
from .io_utils import run_hidden, sha256_text
from .models import (
    CONTEXTUAL_ENGLISH_NAME_PRONUNCIATION_SOURCE,
    ENGLISH_NAME_PRONUNCIATION_SOURCE,
)
from .process_utils import terminate_process_tree
from .text_processing import is_vocalization_only


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
LOCAL_SCOPE_HASH_LENGTH = 16
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
SHORT_NAME_MAX_CHARACTERS = 4
SHORT_NAME_MIN_CONFIDENCE = 0.9
AUTOMATIC_PRONUNCIATION_REPAIR_CONFIDENCE = 0.85
CMUDICT_TRANSLITERATION_CONFIDENCE = 0.98
LOCAL_NAME_FALLBACK_CONFIDENCE = 0.88
ADDRESSEE_REPAIR_NOTE = "đã tách người nói khỏi tên người được gọi"
EXPLICIT_ATTRIBUTION_NOTE = "đã khóa người nói từ lời dẫn cùng đoạn văn"
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
SENTENCE_INITIAL_PREFIX_PATTERN = re.compile(
    r"(?:^|[.!?…:\n])[\s\"'“”‘’()\[\]{}—-]*$"
)
ISOLATED_LATIN_DIALOGUE_PATTERN = re.compile(
    r"^\s*[\"'“‘—–-]?\s*(?P<token>[A-Z][A-Za-z'’-]{1,})\s*[.!?…]*\s*[\"'”’]?\s*$"
)
VIETNAMESE_SPOKEN_FORM_PATTERN = re.compile(
    r"^[A-Za-zÀ-ỹĐđ]+(?:[ -][A-Za-zÀ-ỹĐđ]+)*$"
)
NON_VIETNAMESE_SYLLABLE_CODA_PATTERN = re.compile(r"[fjlrsvwz]$", re.IGNORECASE)
VIETNAMESE_SYLLABLE_ONSETS = {
    "", "b", "c", "ch", "d", "g", "gh", "gi", "h", "k", "kh", "l", "m", "n",
    "ng", "ngh", "nh", "p", "ph", "q", "qu", "r", "s", "t", "th", "tr", "v", "x",
}
NAME_CANDIDATE_EXCLUSIONS = {
    "a", "ai", "an", "anh", "ba", "ban", "binh", "book", "cha", "chapter", "chau", "chi",
    "chu", "co", "con", "cung", "dao", "day", "dinh", "do", "dong", "duc", "giang", "ha", "hai",
    "haiz", "hieu", "hm", "hmm", "hmmm", "ho", "hoa", "hoang", "huhu", "huy", "khi",
    "khong", "khung", "lan", "linh",
    "long", "luc", "mai", "mau", "minh", "mot", "muoi", "nam", "narrator", "nga", "ngay", "nguoi",
    "nhung", "no", "npc", "ong", "phong", "phuc", "quan", "quang", "sau", "son", "ta", "thanh",
    "thao", "the", "thi", "thu", "tia", "tieng", "tim", "tinh", "toi", "trang", "trinh", "trong",
    "trung", "truoc", "tuan", "tuy", "unknown", "va", "vai", "van", "vi", "viet", "vinh", "voi",
    "he", "her", "him", "mm", "sh", "shh",
    "his", "lady", "lord", "miss", "mister", "mr", "mrs", "she", "sir", "their", "they",
}
CMUDICT_CONTEXT_ONLY = {"may"}
LATIN_PROPER_NAME_SURFACE_PATTERN = re.compile(
    r"[A-Z][A-Za-z]*(?:['’-][A-Za-z]+)*(?:\s+[A-Z][A-Za-z]*(?:['’-][A-Za-z]+)*)*"
)
CORRUPTED_NAME_JOINERS = frozenset(",;:")
ATTRIBUTION_SENTENCE_START_EXCLUSIONS = {
    "ban", "cùng", "dù", "khi", "lúc", "nếu", "ngoài", "sau", "suy", "thay",
    "theo", "trong", "trước", "tuy", "vì",
}
SPEECH_ATTRIBUTION_PATTERN = re.compile(
    rf"(?P<speaker>{LATIN_PROPER_NAME_SURFACE_PATTERN.pattern})\s+"
    r"(?:nói|hỏi|đáp|trả lời|lên tiếng|thì thầm|quát|kêu|thốt lên)\s*[:：]\s*$"
)
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
LATIN_NAME_VOWELS = frozenset("aeiouy")
LATIN_NAME_VOWEL_READINGS = {
    "a": "a",
    "aa": "a",
    "ae": "e",
    "ai": "ai",
    "au": "ao",
    "aw": "ao",
    "ay": "ây",
    "e": "ê",
    "ea": "i",
    "ee": "i",
    "ei": "ây",
    "eu": "iu",
    "ew": "iu",
    "ey": "ây",
    "i": "i",
    "ie": "i",
    "io": "iô",
    "o": "ô",
    "oa": "ô",
    "oe": "ô",
    "oi": "oi",
    "oo": "u",
    "ou": "ao",
    "ow": "ao",
    "oy": "oi",
    "u": "u",
    "ue": "u",
    "ui": "ui",
    "y": "i",
}
LATIN_NAME_ONSET_READINGS = {
    "ch": "ch",
    "ck": "c",
    "gn": "n",
    "kn": "n",
    "ph": "ph",
    "qu": "qu",
    "rh": "r",
    "sch": "x",
    "sh": "s",
    "tch": "ch",
    "th": "th",
    "wh": "u",
    "wr": "r",
}
LATIN_NAME_CONSONANT_READINGS = {
    "b": "b",
    "c": "c",
    "d": "đ",
    "f": "ph",
    "g": "g",
    "h": "h",
    "j": "gi",
    "k": "c",
    "l": "l",
    "m": "m",
    "n": "n",
    "p": "p",
    "q": "c",
    "r": "r",
    "s": "x",
    "t": "t",
    "v": "v",
    "w": "u",
    "x": "x",
    "z": "d",
}
LATIN_LETTER_NAMES = {
    "a": "a",
    "b": "bê",
    "c": "xê",
    "d": "đê",
    "e": "e",
    "f": "ép",
    "g": "giê",
    "h": "hát",
    "i": "i",
    "j": "giây",
    "k": "ca",
    "l": "e-lờ",
    "m": "em",
    "n": "en",
    "o": "ô",
    "p": "pê",
    "q": "quy",
    "r": "a-rờ",
    "s": "ét",
    "t": "tê",
    "u": "u",
    "v": "vê",
    "w": "đắp-liu",
    "x": "ích",
    "y": "oai",
    "z": "dét",
}
VOWELLESS_NAME_READINGS = {
    "hm": "Hừm",
    "hmm": "Hừm",
    "hmmm": "Hừm",
    "mm": "Ừm",
    "sh": "Suỵt",
    "shh": "Suỵt",
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
   Với nhân vật có tên, speaker chỉ chứa tên riêng chuẩn: không thêm tiền tố NPC, vai vế/xưng hô như dì/ông/quý cô,
   và không chèn dấu câu vào giữa tên. Phải giữ đúng gender đã biết của cùng tên qua mọi batch.
   Nếu nhân vật không có tên nhưng phân biệt được cục bộ trong đoạn hội thoại, dùng
   speaker=NPC_LOCAL:<nhãn ngắn>, ví dụ NPC_LOCAL:áo xanh hoặc NPC_LOCAL:lính gác 1.
   Giữ cùng nhãn cho cùng người trong các đoạn liên tiếp của batch; dùng nhãn khác cho người khác.
   Chỉ dùng UNKNOWN khi hoàn toàn không có dấu hiệu phân biệt người nói.
   Speaker là người phát ra câu, không phải người được gọi trong câu. Tên đứng sau cách xưng hô như
   “anh Lucien”, “chị Alisa”, hoặc tên ở đầu câu theo sau bởi dấu phẩy như “Iven, ...” thường là người
   nghe. Tuyệt đối không lấy tên đó làm speaker nếu lời kể lân cận cho thấy một người khác đang nói;
   nếu người nói chưa có tên, dùng NPC_LOCAL với nhãn mô tả người nói.
3. Độc thoại nội tâm dùng kind=thought và luôn dùng speaker=NARRATOR. Không xác định hoặc lưu danh tính
   nhân vật đang nghĩ; toàn bộ nội tâm trong mọi chapter đều do người kể đọc.
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
    speaker = re.sub(r"(?<=[A-Za-z]),(?=[A-Za-z])", "", speaker)
    npc_named = re.fullmatch(
        r"NPC(?:[\s:_-]+)([A-Z][A-Za-z]*(?:[\s'-][A-Z][A-Za-z]*)*)",
        speaker,
        flags=re.IGNORECASE,
    )
    if npc_named and any(character.isupper() for character in npc_named.group(1)):
        speaker = npc_named.group(1)
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


def _local_scope_for_group(group: list[Any]) -> str:
    if not group:
        raise ValueError("Cannot create a local speaker scope for an empty analysis group")
    first_id = str(group[0]["stable_id"])
    last_id = str(group[-1]["stable_id"])
    digest = sha256_text(f"{first_id}\0{last_id}")[:LOCAL_SCOPE_HASH_LENGTH]
    return f"r{digest}"


def _split_analysis_group(group: list[Any]) -> tuple[list[Any], list[Any]]:
    midpoint = len(group) // 2
    boundaries = [
        index
        for index in range(1, len(group))
        if not _same_paragraph(group[index - 1], group[index])
    ]
    split_at = min(boundaries, key=lambda index: (abs(index - midpoint), index)) if boundaries else midpoint
    return group[:split_at], group[split_at:]


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


def _same_paragraph(left: Any, right: Any) -> bool:
    try:
        return (
            int(left["chapter_id"]) == int(right["chapter_id"])
            and int(left["paragraph_index"]) == int(right["paragraph_index"])
        )
    except (KeyError, TypeError, ValueError):
        return False


def _leading_proper_name(text: str) -> str | None:
    stripped = text.lstrip()
    match = LATIN_PROPER_NAME_SURFACE_PATTERN.match(stripped)
    if match is None:
        return None
    speaker = match.group(0)
    tail = stripped[match.end() :]
    if not tail or not tail[0].isspace():
        return None
    remainder = tail.lstrip()
    if (
        not remainder
        or not remainder[0].islower()
        or _name_candidate_key(speaker) in NAME_CANDIDATE_EXCLUSIONS
        or _name_candidate_key(speaker.split()[0]) in ATTRIBUTION_SENTENCE_START_EXCLUSIONS
    ):
        return None
    return speaker


def _trailing_speech_attribution(text: str) -> str | None:
    match = SPEECH_ATTRIBUTION_PATTERN.search(text.strip())
    if match is None:
        return None
    speaker = match.group("speaker")
    if _name_candidate_key(speaker) in NAME_CANDIDATE_EXCLUSIONS:
        return None
    return speaker


def _repair_explicit_attribution(
    group: list[Any],
    result: dict[str, dict[str, Any]],
) -> None:
    for index, row in enumerate(group):
        seg_id = str(row["stable_id"])
        data = result.get(seg_id)
        if data is None or data["kind"] != "dialogue":
            continue
        attributed_speaker: str | None = None
        if index > 0 and _same_paragraph(group[index - 1], row):
            previous = group[index - 1]
            previous_data = result.get(str(previous["stable_id"]))
            if previous_data is not None and previous_data["kind"] == "narration":
                attributed_speaker = _trailing_speech_attribution(str(previous["text"]))
        if (
            attributed_speaker is None
            and index + 1 < len(group)
            and _same_paragraph(row, group[index + 1])
        ):
            following = group[index + 1]
            following_data = result.get(str(following["stable_id"]))
            if following_data is not None and following_data["kind"] == "narration":
                attributed_speaker = _leading_proper_name(str(following["text"]))
        if attributed_speaker is None:
            continue
        attributed_speaker = _canonical_speaker(attributed_speaker)
        previous_speaker = str(data["speaker"])
        known_rows = [
            candidate
            for candidate in result.values()
            if normalize_speaker_name(str(candidate["speaker"]))
            == normalize_speaker_name(attributed_speaker)
        ]
        data["speaker"] = attributed_speaker
        resolved_gender = _strong_majority_value(known_rows, "gender", {"male", "female"})
        resolved_age = _strong_majority_value(
            known_rows,
            "age",
            ALLOWED_AGES - {"unknown"},
        )
        if normalize_speaker_name(previous_speaker) != normalize_speaker_name(attributed_speaker):
            data["gender"] = resolved_gender
            data["age"] = resolved_age
        data["confidence"] = max(float(data.get("confidence", 0.0)), 0.95)
        notes = str(data.get("notes", ""))
        data["notes"] = (
            f"{notes}; {EXPLICIT_ATTRIBUTION_NOTE}" if notes else EXPLICIT_ATTRIBUTION_NOTE
        )[:500]


def normalize_speaker_name(value: str) -> str:
    return " ".join(value.casefold().split())


def _strong_majority_value(
    rows: list[dict[str, Any]],
    field: str,
    allowed: set[str],
) -> str:
    counts = Counter(str(row.get(field, "unknown")) for row in rows if str(row.get(field)) in allowed)
    if not counts:
        return "unknown"
    ranked = counts.most_common()
    if len(ranked) > 1 and ranked[0][1] == ranked[1][1]:
        return "unknown"
    return ranked[0][0]


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
        if EXPLICIT_ATTRIBUTION_NOTE in str(data.get("notes", "")):
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
    speaker = "NARRATOR" if kind in {"narration", "thought"} else "UNKNOWN"
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
        if kind in {"narration", "thought"}:
            speaker = "NARRATOR"
        else:
            speaker = _scope_local_speaker(speaker, rows_by_id[seg_id], local_scope)
        notes = str(item.get("notes", ""))[:500]
        result[seg_id] = {
            "kind": kind,
            "speaker": speaker,
            "gender": (
                "unknown"
                if speaker == "NARRATOR"
                else _safe_choice(item.get("gender"), ALLOWED_GENDERS, "unknown")
            ),
            "age": (
                "unknown"
                if speaker == "NARRATOR"
                else _safe_choice(item.get("age"), ALLOWED_AGES, "unknown")
            ),
            "emotion": _safe_choice(item.get("emotion"), ALLOWED_EMOTIONS, "neutral"),
            "intensity": max(0, min(3, int(item.get("intensity", 1)))),
            "pace": _safe_choice(item.get("pace"), ALLOWED_PACES, "normal"),
            "volume": _safe_choice(item.get("volume"), ALLOWED_VOLUMES, "normal"),
            "confidence": max(0.0, min(1.0, float(item.get("confidence", 0.5)))),
            "personality_hint": str(item.get("personality_hint", ""))[:300],
            "notes": notes[:500],
        }
    _repair_explicit_attribution(group, result)
    _repair_addressee_speakers(group, result, local_scope)
    return result


def _batch_id(index: int) -> str:
    return f"{BATCH_ID_PREFIX}{index:0{BATCH_ID_WIDTH}d}"


def _name_pronunciation_id(index: int) -> str:
    return f"{NAME_PRONUNCIATION_ID_PREFIX}{index:0{NAME_PRONUNCIATION_ID_WIDTH}d}"


def _name_candidate_key(value: str) -> str:
    return value.replace("’", "'").casefold()


def _latin_character_count(value: str) -> int:
    return sum(character.isascii() and character.isalpha() for character in value)


def _is_short_name(value: str) -> bool:
    return _latin_character_count(value) <= SHORT_NAME_MAX_CHARACTERS


def _is_proper_latin_name_surface(value: str) -> bool:
    surface = " ".join(value.strip().split())
    if LATIN_PROPER_NAME_SURFACE_PATTERN.fullmatch(surface) is None:
        return False
    return any(character.casefold() in LATIN_NAME_VOWELS for character in surface)


def _occurrence_has_corrupted_joiner(text: str, start: int, end: int) -> bool:
    if (
        end + 1 < len(text)
        and text[end] in CORRUPTED_NAME_JOINERS
        and text[end + 1].isascii()
        and text[end + 1].isalpha()
    ):
        return True
    return bool(
        start >= 2
        and text[start - 1] in CORRUPTED_NAME_JOINERS
        and text[start - 2].isascii()
        and text[start - 2].isalpha()
    )


def _whole_name_occurrences(text: str, surface: str) -> list[re.Match[str]]:
    pattern = re.compile(r"(?<!\w)" + re.escape(surface) + r"(?!\w)")
    return [
        match
        for match in pattern.finditer(text)
        if not _occurrence_has_corrupted_joiner(text, match.start(), match.end())
    ]


def _is_sentence_initial_token(text: str, start: int) -> bool:
    return SENTENCE_INITIAL_PREFIX_PATTERN.search(text[:start]) is not None


def _name_candidate_contexts(rows: list[Any]) -> list[dict[str, Any]]:
    forms: dict[str, Counter[str]] = defaultdict(Counter)
    occurrences: Counter[str] = Counter()
    text_occurrences: Counter[str] = Counter()
    sentence_initial_occurrences: Counter[str] = Counter()
    mid_sentence_occurrences: Counter[str] = Counter()
    examples: dict[str, list[str]] = defaultdict(list)
    speaker_keys: set[str] = set()
    lowercase_text_keys: set[str] = set()
    isolated_dialogue_keys: set[str] = set()
    dialogue_context_keys: set[str] = set()

    def register(
        surface: str,
        *,
        example: str = "",
        speaker: bool = False,
        sentence_initial: bool = False,
        text_occurrence: bool = False,
    ) -> None:
        value = surface.strip()
        if value.casefold().endswith(("'s", "’s")):
            value = value[:-2]
        key = _name_candidate_key(value)
        if (
            len(value) < 2
            or key in NAME_CANDIDATE_EXCLUSIONS
            or not _is_proper_latin_name_surface(value)
        ):
            return
        forms[key][value] += 1
        occurrences[key] += 1
        if speaker:
            speaker_keys.add(key)
        elif sentence_initial:
            sentence_initial_occurrences[key] += 1
        else:
            mid_sentence_occurrences[key] += 1
        if text_occurrence:
            text_occurrences[key] += 1
        normalized_example = " ".join(example.split())[:220]
        if normalized_example and normalized_example not in examples[key] and len(examples[key]) < 3:
            examples[key].append(normalized_example)

    for row in rows:
        speaker = _canonical_speaker(row["speaker"])
        if (
            speaker.casefold() not in RESERVED_SPEAKERS
            and not is_local_speaker(speaker)
            and _is_proper_latin_name_surface(speaker)
        ):
            register(speaker, speaker=True)

        text = str(row["text"])
        try:
            row_kind = str(row["kind"] or "")
        except (KeyError, TypeError):
            row_kind = ""
        if not row_kind:
            try:
                row_kind = str(row["kind_hint"] or "")
            except (KeyError, TypeError):
                row_kind = ""
        isolated_match = ISOLATED_LATIN_DIALOGUE_PATTERN.fullmatch(text)
        if (
            row_kind == "dialogue"
            and isolated_match is not None
            and not is_vocalization_only(text)
        ):
            isolated_dialogue_keys.add(_name_candidate_key(isolated_match.group("token")))
        for match in SPEAKER_NAME_TOKEN_PATTERN.finditer(text):
            value = match.group(1)
            if value[:1].islower():
                lowercase_text_keys.add(_name_candidate_key(value))
        for match in LATIN_PROPER_NAME_SURFACE_PATTERN.finditer(text):
            if _occurrence_has_corrupted_joiner(text, match.start(), match.end()):
                continue
            match_key = _name_candidate_key(match.group(0))
            if (
                row_kind == "dialogue"
                and speaker.casefold() not in RESERVED_SPEAKERS
                and not is_local_speaker(speaker)
            ):
                dialogue_context_keys.add(match_key)
            start = max(0, match.start() - 80)
            end = min(len(text), match.end() + 80)
            register(
                match.group(0),
                example=text[start:end],
                sentence_initial=_is_sentence_initial_token(text, match.start()),
                text_occurrence=True,
            )

    candidates: list[dict[str, Any]] = []
    text_keys = {key for key, count in text_occurrences.items() if count}
    for key in sorted(forms):
        if (
            key in speaker_keys
            and text_occurrences[key] == 0
            and any(other != key and other.startswith(key) for other in text_keys)
        ):
            continue
        if key not in speaker_keys and key in lowercase_text_keys:
            continue
        if (
            key not in speaker_keys
            and key not in isolated_dialogue_keys
            and mid_sentence_occurrences[key] == 0
        ):
            continue
        if key not in speaker_keys and occurrences[key] < NAME_PRONUNCIATION_MIN_OCCURRENCES:
            continue
        representative = max(forms[key], key=len)
        if (
            _is_short_name(representative)
            and key not in speaker_keys
            and key not in isolated_dialogue_keys
            and key not in dialogue_context_keys
            and key not in CMUDICT_CONTEXT_ONLY
            and text_occurrences[key] < 2
        ):
            continue
        surface = sorted(
            forms[key],
            key=lambda value: (-forms[key][value], value.isupper(), value.casefold()),
        )[0]
        candidates.append(
            {
                "surface": surface,
                "occurrences": int(occurrences[key]),
                "text_occurrences": int(text_occurrences[key]),
                "is_speaker": key in speaker_keys,
                "sentence_initial_occurrences": int(sentence_initial_occurrences[key]),
                "mid_sentence_occurrences": int(mid_sentence_occurrences[key]),
                "examples": examples[key],
            }
        )
    return candidates


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


def _latin_name_vowel_groups(value: str) -> list[tuple[int, int]]:
    groups: list[tuple[int, int]] = []
    index = 0
    while index < len(value):
        if value[index] not in LATIN_NAME_VOWELS:
            index += 1
            continue
        start = index
        index += 1
        while index < len(value) and value[index] in LATIN_NAME_VOWELS:
            index += 1
        groups.append((start, index))
    return groups


def _latin_name_syllables(value: str) -> list[tuple[str, str, str]]:
    vowel_groups = _latin_name_vowel_groups(value)
    if not vowel_groups:
        return []
    syllables: list[tuple[str, str, str]] = []
    onset_start = 0
    coda_candidates = ("ng", "ch", "n", "m", "p", "t", "c", "k")
    for group_index, (vowel_start, vowel_end) in enumerate(vowel_groups):
        onset = value[onset_start:vowel_start]
        if group_index + 1 >= len(vowel_groups):
            coda = value[vowel_end:]
            next_onset_start = len(value)
        else:
            next_vowel_start = vowel_groups[group_index + 1][0]
            between = value[vowel_end:next_vowel_start]
            if any(between.startswith(onset) for onset in LATIN_NAME_ONSET_READINGS):
                coda = ""
            else:
                coda = next(
                    (
                        candidate
                        for candidate in coda_candidates
                        if between.startswith(candidate) and len(between) > len(candidate)
                    ),
                    "",
                )
            next_onset_start = vowel_end + len(coda)
        syllables.append((onset, value[vowel_start:vowel_end], coda))
        onset_start = next_onset_start
    return syllables


def _latin_name_onset_reading(onset: str, vowel: str) -> str:
    collapsed = re.sub(r"(.)\1+", r"\1", onset.casefold())
    reading = LATIN_NAME_ONSET_READINGS.get(collapsed)
    if reading is None:
        reading = "".join(
            LATIN_NAME_CONSONANT_READINGS.get(character, "")
            for character in collapsed
        )
    if reading == "c" and vowel[:1] in {"e", "i", "y"}:
        return "k"
    if reading == "g" and vowel[:1] in {"e", "i", "y"}:
        return "gh"
    return reading


def _latin_name_vowel_reading(vowel: str) -> str:
    key = vowel.casefold()
    return LATIN_NAME_VOWEL_READINGS.get(
        key,
        "".join(LATIN_NAME_VOWEL_READINGS.get(character, character) for character in key),
    )


def _latin_name_coda_reading(coda: str) -> str:
    key = coda.casefold()
    if key.startswith("ng"):
        return "ng"
    if key.startswith("ch"):
        return "ch"
    if not key:
        return ""
    return {
        "c": "c",
        "f": "p",
        "g": "c",
        "k": "c",
        "l": "n",
        "m": "m",
        "n": "n",
        "p": "p",
        "q": "c",
        "r": "n",
        "s": "t",
        "t": "t",
        "v": "p",
        "w": "u",
        "x": "c",
        "z": "t",
    }.get(key[0], "")


def _vowelless_name_reading(value: str) -> str:
    override = VOWELLESS_NAME_READINGS.get(value.casefold())
    if override is not None:
        return override
    parts = [LATIN_LETTER_NAMES[character] for character in value.casefold() if character.isalpha()]
    return "-".join(parts)


def _local_name_fallback(surface: str) -> str:
    """Produce a safe Vietnamese-readable form for any Latin name accepted by the scanner."""
    rendered: list[str] = []
    for part in re.findall(r"[A-Za-z]+", surface):
        syllables = _latin_name_syllables(part.casefold())
        if not syllables:
            rendered.append(_vowelless_name_reading(part))
            continue
        rendered.extend(
            _latin_name_onset_reading(onset, vowel)
            + _latin_name_vowel_reading(vowel)
            + _latin_name_coda_reading(coda)
            for onset, vowel, coda in syllables
        )
    spoken_form = "-".join(part for part in rendered if part)
    if not spoken_form:
        raise ValueError(f"Tên không chứa ký tự Latin có thể đọc: {surface!r}")
    spoken_form = spoken_form[0].upper() + spoken_form[1:]
    if VIETNAMESE_SPOKEN_FORM_PATTERN.fullmatch(spoken_form) is None:
        raise ValueError(f"Fallback cục bộ tạo cách đọc không hợp lệ: {surface!r} → {spoken_form!r}")
    syllables = spoken_form.split("-")
    if any(NON_VIETNAMESE_SYLLABLE_CODA_PATTERN.search(syllable) for syllable in syllables):
        raise ValueError(f"Fallback cục bộ tạo âm cuối không hợp lệ: {surface!r} → {spoken_form!r}")
    return spoken_form


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
        return _local_name_fallback(surface)
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
    for syllable in syllables:
        normalized = "".join(
            character
            for character in unicodedata.normalize("NFD", syllable.casefold().replace("đ", "d"))
            if unicodedata.category(character) != "Mn"
        )
        vowel_indexes = [
            index for index, character in enumerate(normalized) if character in "aeiouy"
        ]
        if not vowel_indexes:
            return False
        onset = normalized[:vowel_indexes[0]]
        if onset not in VIETNAMESE_SYLLABLE_ONSETS:
            return False
    return True


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


def _short_name_cmu_is_safe(pronunciation: str) -> bool:
    return _arpabet_phones(pronunciation) in ARPABET_PRONUNCIATION_OVERRIDES


def _short_name_local_fallback_is_safe(candidate: dict[str, Any]) -> bool:
    surface = str(candidate["surface"])
    if (
        not _is_short_name(surface)
        or _name_candidate_key(surface) in CMUDICT_CONTEXT_ONLY
        or bool(candidate.get("cmu_pronunciation"))
    ):
        return False
    parts = re.findall(r"[A-Za-z]+", surface)
    if len(parts) != 1:
        return False
    value = parts[0].casefold()
    first_vowel = next(
        (index for index, character in enumerate(value) if character in LATIN_NAME_VOWELS),
        -1,
    )
    if first_vowel < 0:
        return False
    onset = value[:first_vowel]
    return len(onset) <= 1 or onset in LATIN_NAME_ONSET_READINGS


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
        self.quality_profile = str(settings.get("quality_profile", "balanced"))
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
        self._speaker_genders: dict[str, Counter[str]] = defaultdict(Counter)
        for row in existing:
            speaker = str(row["speaker"])
            gender = str(row["gender"])
            if (
                speaker.casefold() not in RESERVED_SPEAKERS
                and not is_local_speaker(speaker)
                and gender in {"male", "female"}
            ):
                self._speaker_genders[speaker][gender] += 1
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
            run_hidden([executable, "pull", self.model], check=True)
            return True
        except (OSError, subprocess.CalledProcessError):
            return False

    def _known_summary(self) -> str:
        if not self._speaker_counts:
            return "(Chưa có nhân vật đã biết)"
        lines = []
        for name, count in self._speaker_counts.most_common(80):
            genders = self._speaker_genders.get(name, Counter())
            locked_gender = genders.most_common(1)[0][0] if genders else "unknown"
            lines.append(f"- {name}; số lần đã gặp={count}; gender đã biết={locked_gender}")
        return "\n".join(lines)

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
        candidate_keys = {
            _name_candidate_key(str(candidate["surface"]))
            for candidate in _name_candidate_contexts(group)
        }
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
            if (
                not surface
                or not spoken_form
                or not _is_proper_latin_name_surface(surface)
                or _is_short_name(surface)
                or _name_candidate_key(surface) not in candidate_keys
                or not _whole_name_occurrences(source_text, surface)
            ):
                continue
            if surface.casefold() == spoken_form.casefold():
                continue
            if not _valid_vietnamese_spoken_form(surface, spoken_form):
                repaired = _repair_vietnamese_syllable_boundaries(surface, spoken_form)
                if repaired is None:
                    continue
                spoken_form = repaired
            self.db.upsert_pronunciation(
                surface=surface,
                normalized_surface=_name_candidate_key(surface),
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
        stable_groups: list[list[Any]] = []
        current: list[Any] = []
        chars = 0
        for row in all_rows:
            text_len = len(str(row["text"]))
            limit_reached = len(current) >= max_segments or chars + text_len > max_chars
            if current and limit_reached and not _same_paragraph(current[-1], row):
                stable_groups.append(current)
                current = []
                chars = 0
            current.append(row)
            chars += text_len
        if current:
            stable_groups.append(current)
        groups = [
            (
                [row for row in stable_group if str(row["status"]) == "pending"],
                _local_scope_for_group(stable_group),
            )
            for stable_group in stable_groups
            if any(str(row["status"]) == "pending" for row in stable_group)
        ]

        done = len(all_rows) - len(pending)
        total = len(all_rows)
        required = bool(self.settings.get("enabled", True) and self.settings.get("required", True))
        confidence_threshold = float(self.settings.get("low_confidence_threshold", 0.58))
        retry_count = int(self.settings.get("max_retries", 3))
        group_offset = 0
        while group_offset < len(groups):
            group_index = group_offset + 1
            group, local_scope = groups[group_offset]
            if stop_requested():
                return
            if before_batch is not None:
                before_batch(group_index)
            validated: dict[str, dict[str, Any]] = {}
            payload: dict[str, Any] = {}
            last_error = "AI analysis is unavailable"
            split_incomplete_stream = False
            received_incomplete_ids = False
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
                        validated = _validate(group, payload, local_scope=local_scope)
                        if len(validated) == len(group):
                            break
                        last_error = f"LLM returned {len(validated)}/{len(group)} IDs"
                        received_incomplete_ids = True
                    except AnalysisRequestStopped:
                        raise
                    except OllamaStreamIncompleteError as exc:
                        last_error = str(exc)
                        if len(group) > 1:
                            self.log(
                                f"Phân tích batch {group_index} lỗi lần {attempt_number}: "
                                f"{last_error}"
                            )
                            first_half, second_half = _split_analysis_group(group)
                            groups[group_offset : group_offset + 1] = [
                                (first_half, local_scope),
                                (second_half, local_scope),
                            ]
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
            if received_incomplete_ids and len(validated) != len(group) and len(group) > 1:
                first_half, second_half = _split_analysis_group(group)
                groups[group_offset : group_offset + 1] = [
                    (first_half, local_scope),
                    (second_half, local_scope),
                ]
                self.log(
                    f"Batch {group_index} vẫn trả thiếu ID sau {retry_count} lần; tự chia thành "
                    f"{len(first_half)} + {len(second_half)} segment. "
                    f"Tổng số batch còn lại hiện là {len(groups)}."
                )
                continue
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
            explicit_attribution_ids = [
                seg_id
                for seg_id, data in validated.items()
                if EXPLICIT_ATTRIBUTION_NOTE in str(data.get("notes", ""))
            ]
            if explicit_attribution_ids:
                message = (
                    f"Đã khóa người nói cho {len(explicit_attribution_ids)} đoạn thoại "
                    f"từ lời dẫn cùng paragraph ở batch {group_index}."
                )
                self.log(message)
                self.db.event(
                    "info",
                    "EXPLICIT_SPEAKER_ATTRIBUTION_LOCKED",
                    message,
                    {
                        "batch_index": group_index,
                        "segment_ids": explicit_attribution_ids,
                    },
                )
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
                    gender = str(data.get("gender", "unknown"))
                    if gender in {"male", "female"}:
                        self._speaker_genders[speaker][gender] += 1
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
            pronunciation = str(candidate["cmu_pronunciation"])
            candidate["requires_contextual_review"] = bool(
                _is_short_name(str(candidate["surface"]))
                and (
                    not pronunciation
                    or not _short_name_cmu_is_safe(pronunciation)
                )
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
                if self.quality_profile == "high_quality":
                    raise ValueError(
                        f"pronunciation confidence is below {minimum_confidence:.2f}: "
                        f"{surface!r}={confidence:.2f}"
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
            if not pronunciation or bool(candidate.get("requires_contextual_review")):
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
                            if (
                                bool(candidate.get("requires_contextual_review"))
                                and confidence < SHORT_NAME_MIN_CONFIDENCE
                            ):
                                raise ValueError(
                                    f"short name confidence is below {SHORT_NAME_MIN_CONFIDENCE:.2f}: "
                                    f"{surface!r}={confidence:.2f}"
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
                fallback_readings: dict[str, str] = {}
                skipped_surfaces: list[str] = []
                for candidate in pending.values():
                    surface = str(candidate["surface"])
                    if (
                        bool(candidate.get("requires_contextual_review"))
                        and not _short_name_local_fallback_is_safe(candidate)
                    ):
                        skipped_surfaces.append(surface)
                        continue
                    spoken_form = _local_name_fallback(surface)
                    checkpoint_pronunciation(
                        candidate,
                        spoken_form,
                        LOCAL_NAME_FALLBACK_CONFIDENCE,
                    )
                    fallback_readings[surface] = spoken_form
                if skipped_surfaces:
                    skipped_message = (
                        "Bỏ qua cách đọc tự động cho tên ngắn chưa đủ chắc chắn: "
                        f"{skipped_surfaces}. TTS sẽ đọc nguyên văn."
                    )
                    self.log(skipped_message)
                    self.db.event(
                        "warning",
                        "NAME_PRONUNCIATION_UNCERTAIN_SKIPPED",
                        skipped_message,
                        {
                            "batch_index": batch_index,
                            "surfaces": skipped_surfaces,
                            "last_error": last_error,
                        },
                    )
                    if self.quality_profile == "high_quality":
                        raise RuntimeError(
                            "High-quality pronunciation QA could not resolve: "
                            + ", ".join(skipped_surfaces)
                        )
                if fallback_readings:
                    message = (
                        f"Qwen không tạo được cách đọc hợp lệ ở batch {batch_index} cho {remaining}: "
                        f"{last_error}. Đã xử lý bằng bộ chuyển cục bộ: {fallback_readings}."
                    )
                    self.log(message)
                    self.db.event(
                        "warning",
                        "NAME_PRONUNCIATION_LOCAL_FALLBACK",
                        message,
                        {
                            "batch_index": batch_index,
                            "last_error": last_error,
                            "fallback_readings": fallback_readings,
                        },
                    )

        self.log(
            f"Đã khóa cách đọc thuần Việt cho {converted_count}/{len(candidates)} "
            "tên tiếng Anh hoặc fantasy cần xem xét."
        )
        return converted_count

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
