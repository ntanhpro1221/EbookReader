from __future__ import annotations

import re
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Callable

from .analysis import (
    DIALOGUE_CLOSERS,
    DIALOGUE_OPENERS,
    LOCAL_SPEAKER_REQUEST_PREFIX,
    _canonical_speaker,
    _explicit_speaker_attribution,
    is_local_speaker,
    local_speaker_display,
    local_speaker_label,
)
from .database import (
    ProjectDB,
)
from .io_utils import slugify, stable_int
from .voice_catalog import (
    CASTING_REGIONS,
    AGE_PITCH_RANK_BUCKET,
    EXCLUDED_PRESETS,
    LAST_RESORT_PRESETS,
    STYLE_NEWS,
    VIENEU_PRESETS,
    casting_preset_priority,
    casting_presets,
    child_voice_preference,
    preset_by_name,
    base_pitch_for_preset,
    formant_ratio_for_age,
    formant_variants_for_preset,
    age_pitch_semitones,
    preset_reaches_age_pitch,
    preset_age_reach,
)


LOCAL_SPEAKER_CONTINUITY_MAX_SEGMENT_GAP = 12
LOCAL_CHILD_LABEL_PREFIXES = (
    "cậu bé",
    "cô bé",
    "đứa bé",
    "đứa trẻ",
    "trẻ em",
    "trẻ nhỏ",
)
LOCAL_LABEL_STOPWORDS = {"mac", "nguoi"}
CROWD_DIALOGUE_BLOCK_MAX_SEGMENTS = 8
CROWD_ATTRIBUTION_PATTERN = re.compile(
    r"(?:người dân|dân nghèo|dân chúng|đám đông|mọi người).{0,180}"
    r"(?:gào|hét|hô|la|thét|kêu)",
    flags=re.IGNORECASE,
)
LEGACY_PERSONALITY_PREFIX_PATTERN = re.compile(
    r"^personality=([^;=\r\n]{1,160})(?:;|$)"
)


PRONOUNS = {
    "hắn", "nàng", "cô ấy", "anh ấy", "ông ấy", "bà ấy", "người đó", "kẻ đó",
    "ta", "tôi", "mình", "chúng ta", "bọn họ",
}
RESERVED_SPEAKERS = {"narrator": "NARRATOR", "unknown": "UNKNOWN"}
HONORIFIC_PREFIX_PATTERN = re.compile(
    r"^(?:anh|chị|cô|dì|chú|bác|ông|bà|ngài|quý cô|quý ông|bá tước|công tước|đức ngài)\s+(.+)$",
    flags=re.IGNORECASE,
)
ASCII_PROPER_NAME_PATTERN = re.compile(
    r"[A-Z][A-Za-z]*(?:[\s'-][A-Z][A-Za-z]*)*"
)

def normalize_name(name: str) -> str:
    return " ".join(name.strip().casefold().split())


def canonical_key(name: str) -> str:
    return normalize_name(name).upper()


def identity_key(name: str) -> str:
    """Key để hỏi "hai cách viết này có phải một người không": gạch dưới là khoảng trắng.

    Đo 2026-09-11: `NGUOI_TRA_LOI` xuất hiện 45 câu trong bốn project, tất cả tạo sau khi danh
    sách "đã biết" bắt đầu đưa `NGƯỜI TRẢ LỜI` đủ dấu vào prompt - Ollama thỉnh thoảng trả về
    bản ASCII nối bằng gạch dưới. `normalize_name` gộp khoảng trắng chứ không gộp gạch dưới, nên
    nó thành một người thứ hai với một giọng mới, ngay trong chương đúc lại để xoá đúng lỗi ấy.

    Cố ý KHÔNG đổi `normalize_name`: `NPC_LOCAL::...` và `ANONYMOUS_MALE` mang gạch dưới theo
    thiết kế, và `is_local_speaker` kiểm tiền tố `NPC_LOCAL::`. Chỉ hai chỗ gom danh tính dùng
    key này.
    """
    return normalize_name(name.replace("_", " "))


def _stripped_and_marks(name: str) -> tuple[str, tuple[tuple[int, str], ...]]:
    """Tên bỏ hết dấu, và danh sách (vị trí, dấu) đã bỏ - để so hai cách viết với nhau.

    Chỉ so được hai tên khi phần chữ cái trần của chúng giống nhau; khi ấy các dấu là thứ duy
    nhất khác, và câu hỏi thành: dấu của tên này có phải **tập con** dấu của tên kia không.
    """
    decomposed = unicodedata.normalize("NFD", identity_key(name))
    letters: list[str] = []
    marks: list[tuple[int, str]] = []
    for char in decomposed:
        if unicodedata.combining(char):
            marks.append((len(letters) - 1, char))
        else:
            letters.append(char)
    return "".join(letters), tuple(marks)


def dropped_marks_variant_of(loser: str, winner: str) -> bool:
    """`loser` có phải `winner` bị rơi bớt dấu không - và chỉ rơi, không đổi.

    Tiếng Việt phân biệt từ bằng dấu, nên gộp hai tên chỉ vì bỏ dấu ra giống nhau là sai:
    "MÁ" và "MÀ" là hai từ. Luật hẹp hơn: `loser` được coi là biến thể rơi dấu của `winner` khi
    chữ cái trần giống hệt **và** mọi dấu `loser` còn giữ đều nằm đúng vị trí trong `winner`
    **và** `winner` có nhiều dấu hơn. "THU LÃNH" so với "THỦ LÃNH": chữ trần giống, dấu ngã
    trên Ã có ở cả hai, `winner` thêm dấu hỏi - đúng là rơi. "MÁ" so với "MÀ": chữ trần giống,
    nhưng dấu sắc của "MÁ" không có trong "MÀ" - không phải rơi, là khác từ.

    Đo trên lô 2 và lô 3 (2026-09-10): hai cặp như thế, THỦ LÃNH / THU LÃNH và NGƯỜI TRẢ LỜI /
    NGUOI TRA LOI, và nguồn văn bản không chứa chuỗi nào trong số ấy - là nhãn Ollama tự đặt và
    rơi dấu ngẫu nhiên. Ở lô 3 bản rơi dấu đã thành bản trội (66 so với 32, 160 so với 46), vì
    `_known_summary` đưa bản nhiều lần hơn vào prompt kế tiếp và cái sai tự củng cố.
    """
    stripped_loser, marks_loser = _stripped_and_marks(loser)
    stripped_winner, marks_winner = _stripped_and_marks(winner)
    if stripped_loser != stripped_winner:
        return False
    if len(marks_winner) <= len(marks_loser):
        return False
    return set(marks_loser) <= set(marks_winner)


def merge_dropped_mark_variants(
    representatives: dict[str, str],
    counts: "Counter[str]",
) -> dict[str, str]:
    """Trỏ mọi cách viết rơi dấu về cách viết đủ dấu. Trả về {key thua: đại diện thắng}.

    Người thắng là bản **nhiều dấu nhất**, không phải bản nhiều lần nhất - vì số lần đã bị vòng
    phản hồi làm nhiễm: ở lô 3 NGUOI TRA LOI (rơi hết dấu) có 160 lần còn NGƯỜI TRẢ LỜI chỉ 46,
    và nếu chọn theo số lần thì bản sai sẽ thắng, rồi lô 4 lại thấy nó trong danh sách "đã
    biết" với số lớn hơn nữa. Số lần chỉ dùng để phá hoà giữa hai bản cùng số dấu.
    """
    by_stripped: dict[str, list[str]] = defaultdict(list)
    for key, representative in representatives.items():
        by_stripped[_stripped_and_marks(representative)[0]].append(key)
    redirected: dict[str, str] = {}
    for keys in by_stripped.values():
        if len(keys) < 2:
            continue
        names = [representatives[key] for key in keys]
        for key, name in zip(keys, names):
            better = [
                other
                for other in names
                if other != name and dropped_marks_variant_of(name, other)
            ]
            if not better:
                continue
            winner = max(
                better,
                key=lambda candidate: (
                    len(_stripped_and_marks(candidate)[1]),
                    counts.get(candidate, 0),
                    candidate,
                ),
            )
            redirected[key] = winner
    return redirected


def _looks_like_proper_name(value: str) -> bool:
    return ASCII_PROPER_NAME_PATTERN.fullmatch(value.strip()) is not None


def _honorific_target(value: str) -> str | None:
    match = HONORIFIC_PREFIX_PATTERN.fullmatch(" ".join(value.split()))
    if match is None:
        return None
    candidate = match.group(1).strip()
    return candidate if _looks_like_proper_name(candidate) else None


# Một nhãn dài là "tên ngắn + họ bịa" khi nó có tối đa ngần này câu...
STRAY_SURNAME_MAX_LINES = 3
# ...và tên ngắn có ít nhất ngần này lần số câu của nó. Hai ngưỡng cùng lúc, vì mỗi cái riêng lẻ
# đều gộp nhầm được: chỉ "dài ≤ 3" thì gộp một nhân vật phụ thật vào một nhân vật chính tình cờ
# trùng tên; chỉ "ngắn ≥ 10×" thì gộp JAKE SMITH (30 câu) vào JAKE (300 câu) - hai người thật.
# Đo trên ba lô: bốn cặp nhãn lạc đều lọt cả hai ngưỡng; một cặp cha-con thật có cả hai bên nói
# thì không lọt ngưỡng đầu.
STRAY_SURNAME_MIN_RATIO = 10


def merge_stray_surnames(
    representatives: dict[str, str],
    counts: "Counter[str]",
) -> dict[str, str]:
    """Trỏ "ALICE VIC. DRAKEN" (1 câu) về "ALICE" (25 câu). Trả về {key thua: đại diện thắng}.

    Khác lớp rơi dấu ở hướng gộp: ở đây bản **ngắn** thắng, vì bản dài là nhãn lạc - model kể
    chuyện về ALICE suốt rồi bỗng gọi cô là "ALICE VIC. DRAKEN" đúng một câu, với một cái họ nó
    tự bịa (lô 2 gọi là DRACEN, lô 3 gọi là DRAKEN). Giữ nhãn ấy làm nhân vật riêng là cấp cho
    một câu thoại một giọng riêng, chiếm một chỗ trong kho, và ở lô 3 chỗ ấy va chạm với THALIA.

    Không có gender ở tầng này (gender được phân giải sau, trong vòng đúc giọng), nên hai ngưỡng
    số câu là toàn bộ chốt chặn - và chúng được đặt để một cặp cha-con thật (hai người đều nói)
    không bao giờ lọt.
    """
    names = list(representatives.values())
    redirected: dict[str, str] = {}
    for key, name in representatives.items():
        words = normalize_name(name).split()
        if len(words) < 2:
            continue
        long_lines = int(counts.get(name, 0))
        if long_lines > STRAY_SURNAME_MAX_LINES:
            continue
        shorter = [
            other
            for other in names
            if other != name
            and len(normalize_name(other).split()) < len(words)
            and words[: len(normalize_name(other).split())] == normalize_name(other).split()
            and int(counts.get(other, 0)) >= max(1, long_lines) * STRAY_SURNAME_MIN_RATIO
        ]
        if not shorter:
            continue
        # Nhiều tên ngắn cùng là tiền tố (hiếm): lấy tên NGẮN NHẤT nhiều câu nhất - đó là nhân
        # vật, những cái ở giữa cũng có thể là nhãn lạc và sẽ tự gộp về đúng chỗ ở lượt của nó.
        winner = min(
            shorter,
            key=lambda other: (len(normalize_name(other).split()), -int(counts.get(other, 0)), other),
        )
        redirected[key] = winner
    return redirected


def _folded_source_text(db: ProjectDB) -> str:
    """Văn bản nguồn của chính project, bỏ dấu và hạ chữ, để đếm một cái tên trong đó.

    Đọc **mọi** file .txt cùng thư mục với các chương của project, không chỉ những chương
    project ấy chạy: một project vá một chương chỉ trỏ tới một file, và hỏi "cái tên này có
    trong sách không" bằng một chương thì gần như luôn trả lời "không" - tức luật sẽ gộp bừa
    đúng lúc nó có ít bằng chứng nhất.

    Không đọc được gì thì trả về "" và luật tự tắt. Nó phải tắt được: một cái tên bị gộp sai là
    hai nhân vật nhập làm một, tệ hơn hẳn việc không gộp.
    """
    try:
        paths = {
            Path(str(row["input_path"]))
            for row in db.list_chapters()
            if row["input_path"]
        }
    except Exception:  # noqa: BLE001
        return ""
    folders = {path.parent for path in paths if path.parent.is_dir()}
    files = sorted({found for folder in folders for found in folder.glob("*.txt")})
    chunks: list[str] = []
    for path in files or sorted(path for path in paths if path.is_file()):
        try:
            chunks.append(path.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            continue
    return fold_for_source_search("\n".join(chunks))


def fold_for_source_search(text: str) -> str:
    """Chữ thường, bỏ hết dấu - để so một cái tên với văn xuôi viết hoa/thường tuỳ chỗ."""
    lowered = unicodedata.normalize("NFD", text.lower())
    return "".join(char for char in lowered if not unicodedata.combining(char))


def source_occurrences(name: str, folded_source: str) -> int:
    """Số lần một cái tên xuất hiện trong nguồn đã bỏ dấu."""
    needle = fold_for_source_search(name).strip()
    if not needle or not folded_source:
        return 0
    return len(re.findall(re.escape(needle), folded_source))


def _within_one_edit(left: str, right: str) -> bool:
    """Hai chuỗi lệch nhau đúng một ký tự (thay, thêm, hoặc bớt). Bằng nhau thì KHÔNG tính."""
    if left == right or abs(len(left) - len(right)) > 1:
        return False
    if len(left) == len(right):
        return sum(a != b for a, b in zip(left, right)) == 1
    longer, shorter = (left, right) if len(left) > len(right) else (right, left)
    return any(longer[:i] + longer[i + 1 :] == shorter for i in range(len(longer)))


def fold_to_source_spelling(
    names: "Sequence[str]",
    folded_source: str,
    counts: "Counter[str] | dict[str, int] | None" = None,
) -> dict[str, str]:
    """Trỏ cách viết KHÔNG có trong nguồn về cách viết CÓ. Trả về {tên thua: tên thắng}.

    Chỉ những tên vắng mặt hẳn (0 lần) mới được xét, và chỉ được trỏ về một tên **có mặt** mà
    lệch nó đúng một ký tự - hoặc lệch một ký tự với **từ đầu** của nó, để `SELNE VALKRYN` về
    được `SELENE` mà không cần biết `VALKRYN` là họ bịa.

    Người thắng là tên xuất hiện **nhiều nhất trong nguồn**; `counts` chỉ phá hoà - số câu thoại
    là đúng thứ đã bị vòng phản hồi làm nhiễm, nên nó không được quyết. Không bao giờ trỏ một
    tên có mặt về đâu cả: cuốn sách nói nó tồn tại thì nó tồn tại.
    """
    if not folded_source:
        return {}
    counted = {name: source_occurrences(name, folded_source) for name in names}
    present = [name for name, hits in counted.items() if hits > 0]
    if not present:
        return {}
    counts = counts or {}
    redirected: dict[str, str] = {}
    for name, hits in counted.items():
        if hits:
            continue
        folded_name = fold_for_source_search(name).strip()
        words = folded_name.split()
        first_word = words[0] if words else ""
        candidates = [
            other
            for other in present
            if _within_one_edit(folded_name, fold_for_source_search(other).strip())
            or (
                first_word
                and _within_one_edit(first_word, fold_for_source_search(other).strip())
            )
        ]
        if not candidates:
            continue
        redirected[name] = max(
            candidates,
            key=lambda other: (counted[other], int(counts.get(other, 0)), other),
        )
    return redirected


def _canonicalize_named_speakers(
    db: ProjectDB,
    log: Callable[[str], None],
) -> dict[str, set[str]]:
    counts = Counter(str(row["speaker"]) for row in db.list_segments())
    cleaned_counts: Counter[str] = Counter()
    cleaned_by_original: dict[str, str] = {}
    for original, count in counts.items():
        cleaned = _canonical_speaker(original)
        cleaned_by_original[original] = cleaned
        normalized = normalize_name(cleaned)
        if (
            is_local_speaker(cleaned)
            or cleaned.casefold() in RESERVED_SPEAKERS
            or normalized in PRONOUNS
        ):
            continue
        cleaned_counts[cleaned] += count

    representatives: dict[str, str] = {}
    variants_by_key: dict[str, Counter[str]] = defaultdict(Counter)
    for cleaned, count in cleaned_counts.items():
        variants_by_key[identity_key(cleaned)][cleaned] += count
    for key, variants in variants_by_key.items():
        representatives[key] = min(
            variants,
            key=lambda candidate: (-variants[candidate], candidate.casefold(), candidate),
        )
    # Pass thứ hai, sau khi mỗi key đã có đại diện: hai key mà một là bản rơi dấu của cái kia
    # thì trỏ về cùng một đại diện. Làm ở đây để vòng viết lại bên dưới xử nó y như mọi alias
    # khác - không có đường riêng để quên.
    for loser_key, winner in merge_dropped_mark_variants(representatives, cleaned_counts).items():
        representatives[loser_key] = winner

    # Nhãn "tên + họ bịa" trỏ về tên ngắn. Đặt ngay trước vòng viết lại để nó được xử như mọi
    # alias khác. Neo ở đây chứ không ở pass rơi dấu, để bản vá này và bản vá rơi dấu áp được
    # theo thứ tự nào cũng được - hai lớp lỗi độc lập thì hai bản vá phải độc lập.
    for loser_key, winner in merge_stray_surnames(representatives, cleaned_counts).items():
        representatives[loser_key] = winner

    # Pass cuối trong ba pass nhận dạng, và cố ý cuối: hai pass trên có thể đã trỏ một key về
    # `SELNE`, và pass này trỏ **giá trị** `SELNE` sang `SELENE`, nên nó dọn cả những key vừa
    # được trỏ tới - không cần đi vòng nào để nối hai luật lại.
    source_folded = fold_to_source_spelling(
        sorted(set(representatives.values())),
        _folded_source_text(db),
        cleaned_counts,
    )
    if source_folded:
        for key, name in list(representatives.items()):
            if name in source_folded:
                representatives[key] = source_folded[name]
        for loser, winner in sorted(source_folded.items()):
            log(f"  Tên {loser} không có trong sách; đọc thành {winner}.")

    aliases_by_target: dict[str, set[str]] = defaultdict(set)
    rewritten_segments = 0
    for original, cleaned in cleaned_by_original.items():
        normalized = identity_key(cleaned)
        if (
            is_local_speaker(cleaned)
            or cleaned.casefold() in RESERVED_SPEAKERS
            or normalized in PRONOUNS
        ):
            continue
        target_key = normalized
        honorific_target = _honorific_target(cleaned)
        if honorific_target is not None:
            honorific_key = identity_key(honorific_target)
            if honorific_key in representatives:
                target_key = honorific_key
        target = representatives[target_key]
        aliases_by_target[target].update((original, cleaned))
        if original != target:
            rewritten_segments += db.rewrite_speaker(original, target)

    if rewritten_segments:
        alias_count = sum(
            len(aliases - {target})
            for target, aliases in aliases_by_target.items()
        )
        log(
            f"Đã chuẩn hóa {rewritten_segments} segment thuộc {alias_count} alias nhân vật "
            "rõ ràng trước khi khóa voice."
        )
    return aliases_by_target


# Vietnamese marks gender in the words it uses for people far more reliably than an
# English pronoun does, and the narration is full of them. Only unambiguous ones are here:
# "em", "con", "bác" and "người" are used for either, so counting them would add noise
# rather than evidence.
MALE_PERSON_WORDS = frozenset(
    {"cậu", "anh", "ông", "hắn", "gã", "chàng", "thằng", "chú", "lão"}
)
FEMALE_PERSON_WORDS = frozenset(
    {"cô", "chị", "bà", "nàng", "ả", "mụ", "dì", "thím", "nữ"}
)
# A scene puts a character beside people of the other gender, so the words in the segments
# that name them are never pure. The margin has to be wide enough that the character's own
# pronoun dominates: Noah's 36 segments carry 40 male words to 4 female, because "ông" for
# his father and "bà" for his mother are there too and still lose ten to one.
GENDER_EVIDENCE_MINIMUM_HITS = 5
GENDER_EVIDENCE_MINIMUM_RATIO = 3.0
WORD_PATTERN = re.compile(r"[^\W\d_]+", flags=re.UNICODE)


def _gendered_word_evidence(rows: list[Any], names: set[str]) -> Counter[str]:
    """Count male and female person-words in every segment that names this character.

    Read from the text rather than from the model, because the model is what is in doubt
    by the time this is called: for Noah it answered male twice, female twice and unknown
    ten times across fourteen segments, while the narration says "cậu" eighteen times.
    """
    wanted = {name.casefold() for name in names if name}
    counts: Counter[str] = Counter()
    if not wanted:
        return counts
    for row in rows:
        text = str(row["text"] or "")
        lowered = text.casefold()
        if not any(name in lowered for name in wanted):
            continue
        for word in WORD_PATTERN.findall(lowered):
            if word in MALE_PERSON_WORDS:
                counts["male"] += 1
            elif word in FEMALE_PERSON_WORDS:
                counts["female"] += 1
    return counts


def _decisive(counts: Counter[str]) -> str | None:
    """The gender the evidence points at, or None when it does not point hard enough."""
    male, female = counts.get("male", 0), counts.get("female", 0)
    winner, loser = ("male", female) if male >= female else ("female", male)
    top = max(male, female)
    if top < GENDER_EVIDENCE_MINIMUM_HITS:
        return None
    if loser > 0 and top / loser < GENDER_EVIDENCE_MINIMUM_RATIO:
        return None
    return winner


def resolve_gender(
    identity_rows: list[Any],
    all_rows: list[Any],
    locked: dict[str, str] | None = None,
) -> tuple[str, str]:
    """One answer for a character's gender, used by the gate and by the casting alike.

    Two places used to decide this and they disagreed by construction: the gate refused any
    disagreement at all, while _majority() answered "unknown" on a tie. So a character the
    model split 2-2 could only ever fail the run, and passing the gate by loosening it
    would have cast that character with no gender at all. This is the single place now.

    A listener's pinned answer outranks everything: they have read the book and the model
    has not. Otherwise the model's own votes win when they have a majority, and when they
    tie - the case that used to kill a run after ninety minutes of analysis - the text is
    asked instead. It answers far better than the model does, because Vietnamese marks
    gender in nearly every word it uses for a person.
    """
    if locked:
        for row in identity_rows:
            pinned = locked.get(canonical_key(str(row["speaker"])))
            if pinned:
                return pinned, "listener"
    votes = Counter(
        str(row["gender"])
        for row in identity_rows
        if str(row["gender"]) in {"male", "female"}
    )
    ranked = votes.most_common()
    if len(ranked) == 1:
        return ranked[0][0], "model"
    if ranked and (len(ranked) == 1 or ranked[0][1] > ranked[1][1]):
        return ranked[0][0], "model_majority"
    names = {str(row["speaker"]) for row in identity_rows}
    evidence = _gendered_word_evidence(all_rows, names)
    decided = _decisive(evidence)
    if decided is not None:
        return decided, f"text:{evidence.get('male', 0)}nam/{evidence.get('female', 0)}nữ"
    return "unknown", "unresolved"


def _validate_casting_inputs(
    rows: list[Any],
    minimum_named_mentions: int,
    log: Callable[[str], None] = lambda _message: None,
    locked: dict[str, str] | None = None,
) -> dict[str, dict[str, Any]]:
    """Trả về những nhân vật không phán xử được giới tính. Không còn ném lỗi vì chúng."""
    rows_by_identity: dict[str, list[Any]] = defaultdict(list)
    for row in rows:
        speaker = str(row["speaker"])
        normalized = normalize_name(speaker)
        if speaker.casefold() in RESERVED_SPEAKERS or normalized in PRONOUNS:
            continue
        rows_by_identity[canonical_key(speaker)].append(row)

    gender_conflicts: dict[str, dict[str, Any]] = {}
    resolved_conflicts: dict[str, tuple[str, str, dict[str, int]]] = {}
    missing_named_genders: dict[str, int] = {}
    identity_instability: dict[str, dict[str, list[Any]]] = {}
    for identity, identity_rows in rows_by_identity.items():
        gender_counts = Counter(
            str(row["gender"])
            for row in identity_rows
            if str(row["gender"]) in {"male", "female"}
        )
        if len(gender_counts) > 1:
            # A disagreement is only fatal when nothing settles it. It used to be fatal
            # always: alpha.30 died here after ninety minutes of analysis because the model
            # called Noah male twice and female twice, while the narration says "cậu"
            # eighteen times. The resolver is the same one the casting uses, so passing
            # here means the character is cast as what passed rather than as "unknown".
            resolved, reason = resolve_gender(identity_rows, rows, locked)
            if resolved == "unknown":
                gender_conflicts[identity] = {
                    **dict(sorted(gender_counts.items())),
                    "text_evidence": dict(
                        _gendered_word_evidence(
                            rows, {str(row["speaker"]) for row in identity_rows}
                        )
                    ),
                }
            else:
                resolved_conflicts[identity] = (resolved, reason, dict(gender_counts))
        if (
            len(identity_rows) >= minimum_named_mentions
            and not gender_counts
            and not is_local_speaker(str(identity_rows[0]["speaker"]))
        ):
            missing_named_genders[identity] = len(identity_rows)

        surfaces = sorted({str(row["speaker"]) for row in identity_rows}, key=str.casefold)
        character_ids = sorted(
            {int(row["canonical_character_id"]) for row in identity_rows if row["canonical_character_id"] is not None}
        )
        profile_ids = sorted(
            {int(row["voice_profile_id"]) for row in identity_rows if row["voice_profile_id"] is not None}
        )
        if len(surfaces) > 1 or len(character_ids) > 1 or len(profile_ids) > 1:
            identity_instability[identity] = {
                "speakers": surfaces,
                "character_ids": character_ids,
                "voice_profile_ids": profile_ids,
            }

    for identity, (resolved, reason, votes) in sorted(resolved_conflicts.items()):
        log(
            f"Giới tính của {identity} bị model trả lời mâu thuẫn ({dict(votes)}); "
            f"đã xác định là {resolved} theo {reason}."
        )

    # Mâu thuẫn giới tính **không** giết lượt chạy nữa.
    #
    # Nó đã giết lô 1b ngày 2026-09-08, sau **4 giờ phân tích trọn vẹn 3.727 đoạn**, vì một
    # nhân vật phụ có đúng hai câu thoại mà model gán một nữ một nam. Văn bản trả lời rõ ràng
    # (3 nữ / 0 nam, và narration viết thẳng *"người phụ nữ… cô ta"*) nhưng
    # `GENDER_EVIDENCE_MINIMUM_HITS = 5` nên `_decisive` không dám quyết.
    #
    # Cổng này vi phạm nguyên tắc dự án đã chốt ở docs/SHIPPING_WITHOUT_A_LISTENER.md — *một
    # phép kiểm không phán xử được thì không được chặn* — và vi phạm nặng hơn cổng cảnh báo
    # segment: chương hỏng thì mất một chương, cổng này hỏng thì mất **cả cuốn sách**, ngay
    # sau khi đã trả xong phần đắt nhất của lượt chạy.
    #
    # KHÔNG hạ `GENDER_EVIDENCE_MINIMUM_HITS`. Đã đo trên mọi project đã lưu: bằng chứng văn
    # bản nhất trí ở 3 hit **mâu thuẫn với model 5 lần trên 13**, ở 1 hit thì đúng bằng tung
    # đồng xu (17 khớp / 18 lệch). Ngưỡng 5 không tuỳ tiện; đổi nó là mua một lỗi im lặng để
    # tránh một lỗi ồn ào.
    #
    # Nên: đúc bằng `unknown` (đường ống đã hỗ trợ - `casting_presets` nới rộng khi thiếu
    # giọng), ghi log to, và trả danh sách ra cho chỗ gọi phát `db.event`. Người nghe sửa
    # sau bằng một lệnh: `cli cast --character X --gender female`.
    for identity, detail in sorted(gender_conflicts.items()):
        log(
            f"Giới tính của {identity} không phán xử được ({detail}); đúc bằng giọng "
            f"trung tính và đi tiếp. Sửa bằng: cli cast --character {identity} --gender ..."
        )

    issues: list[str] = []
    if missing_named_genders:
        issues.append(f"named speakers missing gender={missing_named_genders}")
    if identity_instability:
        issues.append(f"voice identity instability={identity_instability}")
    if issues:
        raise RuntimeError("Casting input quality gate failed: " + "; ".join(issues))
    return gender_conflicts


def _majority(rows: list[Any], column: str, default: str = "unknown") -> str:
    counts = Counter(
        str(row[column])
        for row in rows
        if str(row[column]) not in {"", "unknown"}
    )
    if not counts:
        return default
    ranked = counts.most_common()
    if len(ranked) > 1 and ranked[0][1] == ranked[1][1]:
        return default
    return ranked[0][0]


def preset_gender_of_voice_key(voice_key: str) -> str | None:
    """Phái của preset đứng sau một `voice_key`, hoặc None nếu không tra được.

    `voice_key` là `preset_<slug>_f<formant>_p<pitch>`. So tiền tố DÀI trước, để một preset có
    tên là tiền tố của preset khác không nhận nhầm. Cùng phép tra với
    `scripts/voice_matches_the_person.py` - công cụ ấy báo đúng thứ luật này cấm.
    """
    key = str(voice_key)
    key = key[len("preset_") :] if key.startswith("preset_") else key
    for preset in sorted(VIENEU_PRESETS, key=lambda p: -len(_preset_slug(str(p["name"])))):
        if key.startswith(_preset_slug(str(preset["name"]))):
            return str(preset["gender"])
    return None


def _preset_slug(name: str) -> str:
    plain = unicodedata.normalize("NFD", str(name))
    plain = "".join(char for char in plain if not unicodedata.combining(char))
    return "_".join(plain.replace("Đ", "D").replace("đ", "d").lower().split())


def _preset_by_name(name: str) -> dict[str, str]:
    try:
        return preset_by_name(name)
    except ValueError as exc:
        raise ValueError(f"VieNeu narrator preset is not in the locked catalog: {name!r}") from exc


class PresetAllocator:
    def __init__(self, narrator_voice: str, max_pitch_shift: int) -> None:
        self.narrator_voice = narrator_voice
        self.max_pitch_shift = max(0, int(max_pitch_shift))
        self.pool_usage: dict[str, Counter[str]] = {
            "named": Counter(),
            "npc": Counter(),
        }
        self.variant_usage: Counter[str] = Counter()
        # Bậc formant nào của preset nào đã có chủ. `variant_usage` đếm *bao nhiêu lần*, cái
        # này nhớ *bậc nào* - và chỉ cái sau mới trả lời được "bậc này còn trống không".
        #
        # Không gộp hai cái làm một: `variant_usage` vẫn cần cho đường quay vòng khi thang đã
        # cạn thật, và lúc ấy hành vi phải y hệt trước.
        self.taken_variants: dict[str, set[float]] = {}
        # Ai đang giữ bậc nào, và ai có mặt ở chương nào. `taken_variants` trả lời "bậc này còn
        # trống không"; hai cái này trả lời câu hỏi kế tiếp, chỉ đặt ra khi không còn bậc trống:
        # "dùng chung với ai thì ít hại nhất". Người nghe nghe từng chương một, nên hại đo bằng
        # số chương hai người cùng có mặt.
        # Bậc -> **mọi** người đang giữ nó, không chỉ người đầu tiên. Bản đầu là
        # `dict[float, str]` ghi bằng `setdefault`, và lô đúc lại của lô 3 trả giá: sau khi
        # KANG vào bậc 1,00 của Thanh Bình, `holders[1.0]` vẫn là VIKTOR, nên NPC kế tiếp đọc
        # bậc ấy thành "người lạ đang giữ" và xếp vào đúng chỗ vừa bị chiếm - trong khi KANG,
        # kẻ đang ở cùng chương với nó, vô hình.
        self.holders: dict[str, dict[float, set[str]]] = {}
        self.chapters_of: dict[str, set[int]] = {}

    def note_chapters(self, who: str, chapters: set[int]) -> None:
        """Ghi lại nhân vật này nói ở những chương nào. Gọi cho mọi người TRƯỚC lần chọn đầu.

        Một nhân vật đã ghim từ lô trước mà im lặng ở lô này thì không được ghi gì - tập rỗng -
        và như thế là đúng: người ấy không cùng chương với ai, nên là người lý tưởng để dùng
        chung giọng nếu buộc phải dùng chung.
        """
        self.chapters_of[str(who)] = set(int(c) for c in chapters)

    def choose(
        self,
        gender: str,
        *,
        npc: bool,
        age: str = "unknown",
        prominent: bool = False,
        who: str = "",
    ) -> tuple[dict[str, str], float, int]:
        """Pick a preset, the formant warp it needs, and the F0 offset its age implies.

        `age` used to be analysed, stored and then ignored here, so a child was read by
        whichever adult voice came next in the rotation and a listener described the boy
        as sounding like an old uncle. Age enters twice, because it is two different
        acoustic facts: a shorter vocal tract, which the formant warp reaches, and a
        higher or lower F0, which the register does.
        """
        # A character never shares the narrator's preset. Excluding it by name excludes
        # every variant of it too, which is the point: a pitch-shifted or formant-warped
        # narrator is still the narrator's voice to a listener, not a second character.
        candidates = [
            preset
            for preset in casting_presets(gender)
            if preset["name"] != self.narrator_voice
        ]
        # A preset whose pitch cannot reach the age is not a candidate for it. Warping the
        # tract to a child's size while the pitch stays adult makes a combination no throat
        # can produce, and a listener hears it as a defect rather than as a child.
        reachable = [
            preset
            for preset in candidates
            if preset_reaches_age_pitch(str(preset["name"]), age, gender)
        ]
        if reachable:
            candidates = reachable
        if str(age) == "child":
            # Before puberty the sexes barely differ: an eight-year-old boy and girl are
            # about 13.0 and 12.7 cm of vocal tract. Restricting a boy to the male presets
            # therefore restricts him to the *longest* tracts in the catalog, which cannot
            # reach a child even warped to their limit - they stop 0.8 cm short and sound
            # strained getting there. The short presets land on the target exactly, so the
            # pool widens across gender here and only here.
            candidates = [
                preset
                for preset in VIENEU_PRESETS
                if preset["name"] != self.narrator_voice
                and preset["style"] != STYLE_NEWS
                and preset["region"] in CASTING_REGIONS
                and preset["name"] not in EXCLUDED_PRESETS
                and preset_reaches_age_pitch(str(preset["name"]), age, gender)
            ]
        if not candidates:
            # Nothing of this gender is left, so widen across gender - but never across
            # the region allowlist. A fallback that reached the whole catalog would put
            # the excluded Central presets straight back into the book.
            candidates = [
                preset
                for preset in VIENEU_PRESETS
                if preset["name"] != self.narrator_voice
                and preset["style"] != STYLE_NEWS
                and preset["region"] in CASTING_REGIONS
                and preset["name"] not in EXCLUDED_PRESETS
            ]
        pool = "npc" if npc else "named"
        usage = self.pool_usage[pool]

        def rank(preset: dict[str, Any]) -> tuple[Any, ...]:
            name = str(preset["name"])
            return (
                # Demoted voices sort below every clean one, ahead of usage count rather
                # than blended into it: a gentler weighting would let them win as soon as
                # each clean preset had been used once, which is the second character in
                # the chapter.
                name in LAST_RESORT_PRESETS,
                usage[name],
                # A preset that cannot reach this age is a worse fit however available it
                # is: an adult male tract stops 0.8 cm short of an eight-year-old even
                # warped to its limit, while the shortest presets land exactly on it.
                # Bucketed to half a centimetre: two presets that both land near the
                # target are the same fit to a listener, and a 0.1 cm edge must not
                # outrank a voice being hard to follow.
                # A listener's own ranking of the voices they have heard as children
                # comes before either computed proxy. Reach and shift only estimate how
                # good the result will sound; this is a verdict on the result, and the
                # estimates have already been caught disagreeing with it.
                child_voice_preference(name, age, gender),
                round(preset_age_reach(name, age, gender) * 2.0) / 2.0,
                # Then the dearer of the two warps. Measured on four presets reading the
                # same line, the age pitch shift costs about 0.85 MOS against the formant
                # shift's 0.50, and the damage tracks the size of the shift: +2 semitones
                # lost 0.69 MOS, +11 lost 1.24. Ranking on tract reach alone was
                # optimising the cheaper axis and ignoring the dearer one.
                #
                # It still sorts below reach. Reach decides whether the result is a child
                # at all - a listener rejected an otherwise clean take with "giọng của
                # cậu bé nghe vẫn ra giọng của một ông chú" - and a clean voice that
                # sounds like the wrong person is not the cheaper option.
                #
                # Bucketed at four semitones so a one-semitone edge cannot outweigh
                # anything ranked above it.
                abs(age_pitch_semitones(age, gender, name)) // AGE_PITCH_RANK_BUCKET,
                *casting_preset_priority(preset),
            )

        selected = min(candidates, key=rank)
        name = str(selected["name"])
        usage[name] += 1
        # Formant, not pitch, is what makes a reused preset sound like a different
        # person. The ladder starts at 1.00 so a preset's first casting is the untouched
        # voice and pays no vocoder cost at all - but an age target overrides the ladder,
        # because reading a child at an adult tract length is not a variation, it is wrong.
        age_ratio = formant_ratio_for_age(name, age, gender)
        if abs(age_ratio - 1.0) > 1e-6:
            formant_ratio = age_ratio
        else:
            variants = formant_variants_for_preset(name)
            # Bậc còn trống đầu tiên theo thứ tự thang, chứ không phải bậc mà bộ đếm đang
            # chỉ vào. Hai cách chỉ khác nhau khi có bậc bị nhảy qua - và đúng chỗ ấy lô 1
            # mất một giọng: Thanh Bình nhận 7 người trên 7 bậc mà chỉ ra 6 giọng, bậc 0,898
            # bỏ phí trong khi f104 phát cho cả CHA lẫn SỐ BA.
            #
            # Thang bắt đầu ở 1,00 nên lần đúc đầu của một preset vẫn là giọng gốc không qua
            # vocoder; thứ tự thang không đổi, chỉ có việc bỏ qua bậc đã có chủ là mới.
            formant_ratio = self._first_free_variant(name, variants, who=who)
        self.variant_usage[name] += 1
        step = round(float(formant_ratio), 3)
        self.taken_variants.setdefault(name, set()).add(step)
        if who:
            self.holders.setdefault(name, {}).setdefault(step, set()).add(str(who))
        return selected, formant_ratio, age_pitch_semitones(age, gender, name)

    def _first_free_variant(
        self,
        preset_name: str,
        variants: tuple[float, ...],
        who: str = "",
    ) -> float:
        """Bậc chưa ai giữ, theo thứ tự thang; cạn thật thì quay vòng như cũ.

        Đường quay vòng giữ nguyên `variant_usage[name] % len(variants)` **có chủ ý**: khi mọi
        bậc đã có chủ thì dùng lại là không tránh được, và lúc ấy đổi cách chọn chỉ đổi *ai*
        trùng với ai mà không giảm số lần trùng. Câu hỏi ấy cần đồ thị đồng hiện và là một
        thay đổi khác.

        So sánh có dung sai vì bậc đi qua `round(..., 3)` và qua cột REAL của SQLite; 0,005 là
        một nửa dung sai 0,01 mà chính `formant_variants_for_preset` dùng để khử trùng lặp.
        """
        taken = self.taken_variants.get(preset_name, set())
        for ratio in variants:
            if all(abs(ratio - held) > 0.005 for held in taken):
                return ratio
        # Không còn bậc trống: PHẢI dùng chung. Đây là chỗ bản trước quay vòng mù -
        # `variants[variant_usage % len]` - và lô 3 trả giá: 3 trong 7 va chạm nằm cùng chương,
        # trong đó IGOR + THU LÃNH ở chương 062 (3 + 23 câu) đã vào audio trước khi ai kịp thấy.
        #
        # Chọn bậc mà người đang giữ nó có ÍT chương chung nhất với người sắp được cast; hoà
        # thì bậc thấp hơn trên thang (tất định, tái lập được). Không biết gì về người sắp cast
        # (không có `who`) hay không biết ai giữ bậc nào thì lùi về quay vòng cũ, để hành vi
        # ngoài đường ống chính không đổi.
        mine = self.chapters_of.get(str(who), set()) if who else None
        holders = self.holders.get(preset_name, {})
        if mine is None or not holders:
            return variants[self.variant_usage[preset_name] % len(variants)]
        def shared_chapters(ratio: float) -> int:
            """Bao nhiêu chương của tôi có **một người nào đó** đang giữ bậc này cũng có mặt.

            Hợp của mọi người giữ bậc, không phải người đầu tiên: một bậc đã bị dùng chung thì
            người thứ ba phải thấy cả hai người kia. Đo trên lô đúc lại của lô 3 - THẰNG ĐIÊN
            xếp vào đúng bậc KANG vừa chiếm vì bậc ấy vẫn khai tên VIKTOR.
            """
            occupied: set[int] = set()
            for holder in holders.get(round(ratio, 3), set()):
                occupied |= self.chapters_of.get(holder, set())
            return len(mine & occupied)

        ranked = sorted(
            enumerate(variants),
            key=lambda pair: (shared_chapters(pair[1]), pair[0]),
        )
        return ranked[0][1]

    def reserve(
        self,
        preset_name: str,
        formant_ratio: float | None = None,
        who: str | None = None,
    ) -> None:
        """Record that a preset is taken, for a character this allocator never chose.

        A pinned voice is invisible to the ranking unless it is counted here, and an unused
        preset always sorts first - so the very next character would be handed the voice
        somebody had just pinned to someone else. Two people, one voice, and nothing catches
        it: the invariant in `verify_casting` checks that one speaker resolves to one
        profile, which is the opposite direction.

        **Both pools, not the character's own.** The first version took an `npc` flag and
        counted only that side, and alpha.55 showed what that costs: CÔNG TƯỚC was pinned to
        `preset_thai_son_f087_p+00` from the named pool, and ÔNG LÃO - an NPC, so a different
        counter - was handed the identical voice_key. alpha.54 cast the same book with no
        pinning and had no collisions at all, so this was introduced by the carry. A voice
        that belongs to somebody is taken everywhere, not taken in one ledger.
        """
        name = str(preset_name)
        for pool in self.pool_usage.values():
            pool[name] += 1
        self.variant_usage[name] += 1
        # Và đánh dấu **đúng** bậc đang bị giữ. Không có nó, `variant_usage` nhích lên một
        # tức nhảy qua một bậc *bất kỳ*: bậc bị nhảy qua thành bỏ phí, còn bậc thật sự có chủ
        # vẫn nằm trong vòng quay và được phát lại. Đo trên lô 1: đúng một va chạm sinh ra
        # như thế (CHA và SỐ BA), và nó tránh được mà không cần thêm giọng nào.
        #
        # `formant_ratio` để mặc định None cho những chỗ gọi cũ không biết bậc; khi ấy hành vi
        # y hệt trước bản vá này, tức chỉ nhích bộ đếm.
        if formant_ratio is not None:
            step = round(float(formant_ratio), 3)
            self.taken_variants.setdefault(name, set()).add(step)
            if who:
                self.holders.setdefault(name, {}).setdefault(step, set()).add(str(who))


def _pinned_profile_id(
    db: ProjectDB,
    locked_voices: dict[str, str],
    canonical: str,
    allocator: Any,
    local: bool,
    log: Any,
) -> int | None:
    """The voice a previous run gave this character, if somebody carried it over.

    Returns None when nothing is pinned, which is every character until `port_casting.py`
    runs - so a project that never used it casts exactly as it did before.

    A pinned key that names no profile in this project is reported and ignored rather than
    raising: the run should not die because a carried decision has gone stale, and casting
    afresh is a defensible answer. It is logged because silently re-casting a voice somebody
    chose is not.
    """
    # `canonical` has already been through canonical_key at the call site, and
    # locked_character_voices keys the same way; applying it again is idempotent and says so.
    voice_key = locked_voices.get(canonical_key(canonical), "")
    if not voice_key:
        return None
    try:
        row = db.voice_profile_by_key(voice_key)
    except KeyError:
        log(f"Giọng đã ghim {voice_key!r} cho {canonical!r} không có trong project; cấp phát lại.")
        return None
    # No reserve() here: reserve_pinned_voices has already counted every pinned preset once,
    # before any casting began. Counting again for the characters that happen to speak would
    # make their voices look more used than the pinned voices of silent characters, which is
    # the ranking reading a difference that does not exist.
    del allocator
    return int(row["id"])


def reserve_pinned_voices(
    db: ProjectDB,
    locked_voices: dict[str, str],
    allocator: Any,
    log: Callable[[str], None],
) -> int:
    """Take every pinned voice out of circulation before a single character is cast.

    `reserve` explains why a pinned voice must be counted at all. This is the other half:
    counting it for **every** pinned character, not only the ones with something to say in
    this batch.

    A character who is pinned and silent used to leave its voice looking free, and an unused
    preset always sorts first. Measured on alpha.56: THEOSBANE said nothing across chapters
    010-018, so nothing reserved `preset_thanh_binh_f093_p-04`, and the allocator handed that
    exact voice to SAMAEL. alpha.55, whose pinned characters all spoke, had no collisions at
    all. THEOSBANE appears in 156 of the book's 478 chapters, so the two would have gone on
    sharing a voice for a third of the book.

    Returns how many were reserved. A pin naming a profile this project does not have is
    reported and skipped - the run should not die because a carried decision went stale, and
    it is said out loud because silently re-casting a voice somebody chose is not acceptable.
    """
    reserved = 0
    for canonical, voice_key in sorted(locked_voices.items()):
        if not voice_key:
            continue
        try:
            row = db.voice_profile_by_key(voice_key)
        except KeyError:
            log(
                f"Giọng đã ghim {voice_key!r} cho {canonical!r} không có trong project;"
                " bỏ qua khi giữ chỗ."
            )
            continue
        # `row` là cả dòng voice_profiles, nên bậc formant có sẵn ở đây. Bản đầu chỉ truyền
        # tên preset đi và vứt nó, đó chính là chỗ hỏng.
        allocator.reserve(str(row["preset_name"]), float(row["formant_ratio"]), who=canonical)
        reserved += 1
    return reserved


def _profile_for_preset(
    db: ProjectDB,
    preset: dict[str, str],
    formant_ratio: float,
    cache: dict[str, int],
    *,
    age_pitch: int = 0,
) -> int:
    name = preset["name"]
    # The preset's calibrated reading register, plus whatever the character's age asks
    # for: children speak about three semitones above an adult, and ageing moves men up
    # while it moves women down.
    base_pitch = base_pitch_for_preset(name) + int(age_pitch)
    formant_key = f"f{int(round(float(formant_ratio) * 100)):03d}"
    pitch_key = f"p{int(base_pitch):+03d}"
    profile_key = f"{name}::{formant_key}::{pitch_key}"
    if profile_key not in cache:
        if abs(float(formant_ratio) - 1.0) <= 1e-6:
            description = "âm sắc gốc"
        elif float(formant_ratio) < 1.0:
            description = f"âm sắc trầm hơn ({formant_ratio:.2f})"
        else:
            description = f"âm sắc sáng hơn ({formant_ratio:.2f})"
        cache[profile_key] = db.upsert_voice_profile(
            {
                "voice_key": f"preset_{slugify(name)}_{formant_key}_{pitch_key}",
                "engine": "vieneu",
                "preset_name": name,
                "description": f"{preset['description']} · {description}",
                "seed": stable_int(f"voice::vieneu::{name}::{formant_key}::{pitch_key}"),
                "pitch_semitones": base_pitch,
                "formant_ratio": float(formant_ratio),
                "status": "ready",
            }
        )
    return cache[profile_key]


def _legacy_personality_hint(note: Any) -> str | None:
    match = LEGACY_PERSONALITY_PREFIX_PATTERN.match(str(note or ""))
    if match is None:
        return None
    value = " ".join(match.group(1).split())
    if (
        not value
        or not any(character.isalpha() for character in value)
        or any(
            not (
                character.isalnum()
                or character.isspace()
                or character in {"_", "-", "'", "’"}
            )
            for character in value
        )
    ):
        return None
    return value


def _personality(rows: list[Any]) -> str:
    return next(
        (
            personality
            for row in rows
            if (personality := _legacy_personality_hint(row["analysis_notes"]))
            is not None
        ),
        "",
    )


def _merge_local_speakers_with_named_identity(
    db: ProjectDB,
    log: Callable[[str], None],
) -> None:
    rows = list(db.list_segments())
    named_by_chapter_and_label: dict[tuple[int, str], Counter[str]] = defaultdict(Counter)
    for row in rows:
        speaker = str(row["speaker"])
        normalized = normalize_name(speaker)
        if (
            is_local_speaker(speaker)
            or speaker.casefold() in RESERVED_SPEAKERS
            or normalized in PRONOUNS
        ):
            continue
        named_by_chapter_and_label[(int(row["chapter_id"]), normalized)][speaker] += 1

    local_speakers = {
        str(row["speaker"])
        for row in rows
        if is_local_speaker(row["speaker"])
    }
    for local_speaker in sorted(local_speakers, key=str.casefold):
        matching_rows = [row for row in rows if str(row["speaker"]) == local_speaker]
        if not matching_rows:
            continue
        chapter_id = int(matching_rows[0]["chapter_id"])
        label = normalize_name(local_speaker_label(local_speaker))
        candidates = named_by_chapter_and_label.get((chapter_id, label))
        if not candidates:
            continue
        named_speaker = sorted(
            candidates,
            key=lambda candidate: (-candidates[candidate], candidate.casefold()),
        )[0]
        rewritten = db.rewrite_speaker(local_speaker, named_speaker)
        if rewritten:
            log(
                f"Hợp nhất nhân vật cục bộ cùng chapter: "
                f"{local_speaker_display(local_speaker)} → {named_speaker} "
                f"({rewritten} segment)."
            )


def _compatible_local_traits(left: list[Any], right: list[Any], field: str) -> bool:
    left_values = {str(row[field]) for row in left if str(row[field]) != "unknown"}
    right_values = {str(row[field]) for row in right if str(row[field]) != "unknown"}
    return not left_values or not right_values or bool(left_values & right_values)


def _semantic_local_label(label: str) -> str:
    tokens = [
        token
        for token in slugify(label).split("_")
        if token and token not in LOCAL_LABEL_STOPWORDS
    ]
    return "_".join(tokens)


def _local_continuity_family(speaker: str, rows: list[Any]) -> str:
    label = normalize_name(local_speaker_label(speaker))
    if any(
        label == prefix or label.startswith(f"{prefix} ")
        for prefix in LOCAL_CHILD_LABEL_PREFIXES
    ):
        return f"child::{_majority(rows, 'gender')}"
    return f"label::{_semantic_local_label(label)}"


def _local_speaker_with_label(speaker: str, label: str) -> str | None:
    if not is_local_speaker(speaker):
        return None
    prefix, _separator, _old_label = speaker.rpartition("::")
    return f"{prefix}::{label}" if prefix else None


def _repair_cross_batch_dialogue_continuations(
    db: ProjectDB,
    log: Callable[[str], None],
) -> None:
    rows = sorted(db.list_segments(), key=lambda row: (int(row["chapter_id"]), int(row["seq"])))
    previous: dict[str, Any] | None = None
    repaired = 0
    for row in rows:
        current = {
            "row": row,
            "kind": str(row["kind"]),
            "speaker": str(row["speaker"]),
            "gender": str(row["gender"]),
            "age": str(row["age"]),
        }
        if previous is not None:
            previous_row = previous["row"]
            same_chapter = int(previous_row["chapter_id"]) == int(row["chapter_id"])
            adjacent_seq = int(row["seq"]) == int(previous_row["seq"]) + 1
            adjacent_paragraph = int(row["paragraph_index"]) == int(
                previous_row["paragraph_index"]
            ) + 1
            previous_text = str(previous_row["text"]).rstrip()
            text = str(row["text"]).lstrip()
            continuation = bool(
                same_chapter
                and adjacent_seq
                and adjacent_paragraph
                and previous["kind"] == "dialogue"
                and current["kind"] == "dialogue"
                and previous_text
                and text
                and previous_text[-1] not in DIALOGUE_CLOSERS
                and text[0] not in DIALOGUE_OPENERS
            )
            if continuation and current["speaker"] != previous["speaker"]:
                repaired += db.rewrite_segment_speakers(
                    [int(row["id"])],
                    speaker=str(previous["speaker"]),
                    gender=str(previous["gender"]),
                    age=str(previous["age"]),
                )
                current.update(
                    {
                        "speaker": previous["speaker"],
                        "gender": previous["gender"],
                        "age": previous["age"],
                    }
                )
        previous = current
    if repaired:
        log(f"Đã giữ identity xuyên batch cho {repaired} câu thoại nối tiếp.")


def _repair_crowd_dialogue_blocks(
    db: ProjectDB,
    log: Callable[[str], None],
) -> None:
    rows = sorted(db.list_segments(), key=lambda row: (int(row["chapter_id"]), int(row["seq"])))
    kinds_by_stable_id = {
        str(row["stable_id"]): {"kind": str(row["kind_hint"])}
        for row in rows
    }
    repaired = 0
    for index, row in enumerate(rows):
        if (
            str(row["kind_hint"]) != "narration"
            or str(row["kind"]) == "dialogue"
            or CROWD_ATTRIBUTION_PATTERN.search(str(row["text"])) is None
        ):
            continue
        block: list[Any] = []
        cursor = index - 1
        expected_seq = int(row["seq"]) - 1
        block_speaker: str | None = None
        while cursor >= 0 and len(block) < CROWD_DIALOGUE_BLOCK_MAX_SEGMENTS:
            candidate = rows[cursor]
            if int(candidate["chapter_id"]) != int(row["chapter_id"]):
                break
            if int(candidate["seq"]) != expected_seq:
                break
            if str(candidate["kind"]) != "dialogue":
                break
            candidate_speaker = str(candidate["speaker"])
            if block_speaker is None:
                block_speaker = candidate_speaker
            elif candidate_speaker != block_speaker:
                break
            attributed_speaker = _explicit_speaker_attribution(
                rows,
                cursor,
                kinds_by_stable_id,
            )
            if (
                attributed_speaker is not None
                and attributed_speaker.casefold()
                != f"{LOCAL_SPEAKER_REQUEST_PREFIX}người dân".casefold()
            ):
                break
            block.append(candidate)
            expected_seq -= 1
            cursor -= 1
        if not block:
            continue
        by_target: dict[str, list[int]] = defaultdict(list)
        for candidate in block:
            target = _local_speaker_with_label(str(candidate["speaker"]), "người dân")
            if target is not None:
                by_target[target].append(int(candidate["id"]))
        for target, segment_ids in by_target.items():
            candidates_by_id = {int(candidate["id"]): candidate for candidate in block}
            for segment_id in segment_ids:
                candidate = candidates_by_id[segment_id]
                repaired += db.rewrite_segment_speakers(
                    [segment_id],
                    speaker=target,
                    gender="unknown",
                    age="unknown",
                )
    if repaired:
        log(f"Đã sửa {repaired} câu hô của đám đông từ lời dẫn tập thể kế tiếp.")


def _merge_adjacent_local_speakers(
    db: ProjectDB,
    log: Callable[[str], None],
) -> None:
    rows = list(db.list_segments())
    identities: dict[tuple[int, str], list[Any]] = defaultdict(list)
    for row in rows:
        speaker = str(row["speaker"])
        if not is_local_speaker(speaker):
            continue
        identities[(int(row["chapter_id"]), speaker)].append(row)

    grouped: dict[tuple[int, str], dict[str, list[Any]]] = defaultdict(dict)
    for (chapter_id, speaker), speaker_rows in identities.items():
        family = _local_continuity_family(speaker, speaker_rows)
        grouped[(chapter_id, family)][speaker] = speaker_rows

    for (_chapter_id, family), identities in grouped.items():
        ordered = sorted(
            identities.items(),
            key=lambda item: min(int(row["seq"]) for row in item[1]),
        )
        if len(ordered) < 2:
            continue
        canonical_speaker, canonical_rows = ordered[0]
        canonical_last_seq = max(int(row["seq"]) for row in canonical_rows)
        for speaker, speaker_rows in ordered[1:]:
            first_seq = min(int(row["seq"]) for row in speaker_rows)
            compatible = _compatible_local_traits(
                canonical_rows,
                speaker_rows,
                "gender",
            ) and _compatible_local_traits(canonical_rows, speaker_rows, "age")
            gap = first_seq - canonical_last_seq
            if (
                gap <= 0
                or gap > LOCAL_SPEAKER_CONTINUITY_MAX_SEGMENT_GAP
                or not compatible
            ):
                canonical_speaker = speaker
                canonical_rows = speaker_rows
                canonical_last_seq = max(int(row["seq"]) for row in speaker_rows)
                continue
            rewritten = db.rewrite_speaker(speaker, canonical_speaker)
            if rewritten:
                log(
                    "Hợp nhất NPC cục bộ liền cảnh: "
                    f"{local_speaker_display(speaker)} → "
                    f"{local_speaker_display(canonical_speaker)} ({rewritten} segment)."
                )
            canonical_rows = [*canonical_rows, *speaker_rows]
            canonical_last_seq = max(
                canonical_last_seq,
                max(int(row["seq"]) for row in speaker_rows),
            )


def assert_voice_stability(db: ProjectDB, log: Callable[[str], None] = lambda _m: None) -> None:
    """Refuse a casting where one person would be read by two different voices."""
    # One character, one voice - checked on the resolved character rather than on the
    # speaker label. Checking labels was a blind spot with real consequences: a boy who
    # appeared as a named character in one chapter and as a local NPC in another held two
    # voices three semitones apart, and every label individually had exactly one voice, so
    # this reported success. Local labels were skipped outright, which made the gap worse.
    profiles_by_character: dict[int, set[int]] = defaultdict(set)
    profiles_by_speaker: dict[str, set[int]] = defaultdict(set)
    for row in db.list_segments():
        speaker = str(row["speaker"])
        normalized = normalize_name(speaker)
        profile_id = row["voice_profile_id"]
        character_id = row["canonical_character_id"]
        if speaker != "UNKNOWN" and not is_local_speaker(speaker) and normalized not in PRONOUNS:
            if profile_id is None:
                raise RuntimeError(f"Speaker {speaker!r} has no locked voice profile")
            profiles_by_speaker[normalized].add(int(profile_id))
        if character_id is not None and profile_id is not None:
            profiles_by_character[int(character_id)].add(int(profile_id))
    unstable = {
        speaker: sorted(profile_ids)
        for speaker, profile_ids in profiles_by_speaker.items()
        if len(profile_ids) != 1
    }
    if unstable:
        raise RuntimeError(f"A speaker name resolved to multiple voice profiles: {unstable}")
    split_characters = {
        character_id: sorted(profile_ids)
        for character_id, profile_ids in profiles_by_character.items()
        if len(profile_ids) != 1
    }
    if split_characters:
        raise RuntimeError(
            f"A character resolved to multiple voice profiles: {split_characters}"
        )

    # And the other direction, which nothing checked until alpha.55 produced it. Two
    # characters on one profile sound like the same person, and no gate downstream can tell:
    # every segment is verified, every chapter publishes, and only a listener finds it.
    #
    # It is reported rather than raised because at some book size sharing becomes
    # unavoidable - there are only so many presets times formant variants - and killing a
    # run over an inevitability would be worse than saying so. alpha.54 cast 23 characters
    # into 23 distinct voices, so at this scale a collision means something is wrong, not
    # that the catalogue ran out.
    shared_profiles = {
        profile_id: sorted(character_ids)
        for profile_id, character_ids in _characters_by_profile(profiles_by_character).items()
        if len(character_ids) > 1
    }
    if shared_profiles:
        log(
            "CẢNH BÁO: nhiều nhân vật dùng chung một giọng, người nghe sẽ tưởng là cùng "
            f"một người: {shared_profiles}"
        )


def _characters_by_profile(
    profiles_by_character: dict[int, set[int]],
) -> dict[int, list[int]]:
    inverted: dict[int, list[int]] = defaultdict(list)
    for character_id, profile_ids in profiles_by_character.items():
        for profile_id in profile_ids:
            inverted[int(profile_id)].append(int(character_id))
    return inverted


def _drop_pins_that_contradict_a_person(
    db: Any,
    locked_voices: dict[str, str],
    locked_genders: dict[str, str],
    locked_ages: dict[str, str],
    log: Any,
) -> dict[str, str]:
    """Bỏ giọng đã ghim khi nó trái với thứ NGƯỜI đã ghim. Trả về bản đã lọc.

    Đây là chỗ duy nhất "nhất quán" phải nhường "đúng". `port_casting` mang `locked_voice_key`
    đi theo danh tính để người nghe không mất nhân vật giữa các lô - đúng, và nó cũng mang
    nguyên một lần đoán sai đi mãi: IVAN bị gọi là `child` một lần ở lô 3, được cấp giọng nữ
    kéo cao, và mang nó sang mọi lô sau (17 câu ở chương 062).

    MỘT luật, và là luật duy nhất dữ liệu chứng minh được: **preset phải đúng phái, trừ trẻ
    con.** Trẻ con được đọc bằng preset nữ kéo cao dù là con trai (`AGE_TARGET_PITCH_HZ`), nên
    ở đó lệch phái là đúng. Không bịa luật thứ hai kiểu "giọng trẻ con cho người lớn": nhìn
    `voice_key` không phân biệt được preset nữ dành cho một đứa trẻ với preset nữ dành cho một
    phụ nữ trưởng thành, và đoán chính là thứ đã tạo ra cả lớp lỗi này.
    """
    kept: dict[str, str] = {}
    for key, voice_key in locked_voices.items():
        gender = locked_genders.get(key)
        age = locked_ages.get(key)
        preset = preset_gender_of_voice_key(voice_key)
        contradicts = bool(
            gender and preset and preset != gender and (age or "") != "child"
        )
        if not contradicts:
            kept[key] = voice_key
            continue
        log(
            f"Bỏ giọng ghim của {key}: {voice_key} là preset {preset}, còn người nghe đã ghim"
            f" {gender}" + (f"/{age}" if age else "") + " - cấp lại giọng."
        )
        db.event(
            "warning",
            "CASTING_PIN_CONTRADICTS_A_PERSON",
            f"{key}: dropped ported voice {voice_key}",
            {"character": key, "voice_key": voice_key, "preset_gender": preset,
             "locked_gender": gender, "locked_age": age},
        )
    return kept


def build_registry_and_cast(
    db: ProjectDB,
    settings: dict[str, Any],
    log: Callable[[str], None],
) -> None:
    normalized_thoughts = db.normalize_thought_speakers()
    if normalized_thoughts:
        log(
            f"{normalized_thoughts} đoạn nội tâm không xác định được người nghĩ; "
            "giao cho người kể."
        )

    for speaker in {str(row["speaker"]) for row in db.list_segments()}:
        reserved = RESERVED_SPEAKERS.get(speaker.casefold())
        if reserved and speaker != reserved:
            db.rewrite_speaker(speaker, reserved)

    _repair_cross_batch_dialogue_continuations(db, log)
    _repair_crowd_dialogue_blocks(db, log)
    aliases_by_speaker = _canonicalize_named_speakers(db, log)
    _merge_adjacent_local_speakers(db, log)
    _merge_local_speakers_with_named_identity(db, log)

    rows = [row for row in db.list_segments() if str(row["status"]) != "pending"]
    voice_cfg = settings["voices"]
    minimum_main_mentions = int(voice_cfg["minimum_named_character_mentions"])
    locked_genders = db.locked_character_genders()
    locked_ages = db.locked_character_ages()
    locked_voices = db.locked_character_voices()
    locked_voices = _drop_pins_that_contradict_a_person(
        db, locked_voices, locked_genders, locked_ages, log
    )
    unresolved_genders = _validate_casting_inputs(
        rows, minimum_main_mentions, log, locked_genders
    )
    for identity, detail in sorted(unresolved_genders.items()):
        # Không im lặng: cùng khuôn với cơ chế máy tự cho qua. Chương vẫn ra sản phẩm, nhưng
        # con số này phải nằm trong báo cáo để người nghe biết mà sửa nếu muốn.
        db.event(
            "warning",
            "CASTING_GENDER_UNRESOLVED",
            f"{identity}: {detail}",
        )
    by_speaker: dict[str, list[Any]] = defaultdict(list)
    anonymous_by_gender: dict[str, list[Any]] = defaultdict(list)
    for row in rows:
        speaker = str(row["speaker"])
        normalized = normalize_name(speaker)
        if speaker.casefold() == "unknown" or normalized in PRONOUNS:
            gender = str(row["gender"])
            anonymous_by_gender[gender if gender in {"male", "female"} else "unknown"].append(row)
        else:
            by_speaker[speaker].append(row)

    narrator_voice = str(voice_cfg["narrator_voice"])
    narrator_preset = _preset_by_name(narrator_voice)
    allocator = PresetAllocator(
        narrator_voice,
        int(voice_cfg.get("max_character_pitch_semitones", 2)),
    )
    # Before anyone is cast: a voice that belongs to somebody is taken, whether or not that
    # somebody speaks in this batch.
    reserved_pins = reserve_pinned_voices(db, locked_voices, allocator, log)
    if reserved_pins:
        log(f"Giữ chỗ {reserved_pins} giọng đã ghim trước khi phân vai.")
    profile_cache: dict[str, int] = {}

    narrator_rows = by_speaker.pop("NARRATOR", [])
    narrator_character_id = db.upsert_character(
        canonical_name="NARRATOR",
        display_name="Người kể",
        gender=narrator_preset["gender"],
        age="unknown",
        personality="professional audiobook narrator",
        mentions=len(narrator_rows),
        importance="narrator",
        confidence=1.0,
    )
    narrator_profile = db.upsert_voice_profile(
        {
            "voice_key": "narrator",
            "engine": "vieneu",
            "preset_name": narrator_voice,
            "description": str(voice_cfg["narrator_description"]),
            "seed": stable_int("voice::narrator"),
            "pitch_semitones": 0,
            "status": "ready",
        }
    )
    profile_cache[f"{narrator_voice}::p0"] = narrator_profile
    db.set_character_for_speaker("NARRATOR", narrator_character_id)
    db.set_voice_for_character_segments(narrator_character_id, narrator_profile)

    speaker_groups = sorted(
        by_speaker.items(),
        key=lambda item: (-len(item[1]), item[0].casefold()),
    )
    # Ai có mặt ở chương nào - cho MỌI người, trước lần `choose()` đầu tiên. Ghi theo tên chuẩn
    # vì đó là tên `choose()` và `reserve()` nhận. Thứ tự vòng lặp bên dưới là theo số câu giảm
    # dần, nên nếu ghi ở trong vòng thì một nhân vật xử lý sau sẽ vô hình với lần chọn ép buộc
    # của người xử lý trước - đúng lúc cần thấy nhất.
    for speaker, speaker_rows in speaker_groups:
        allocator.note_chapters(
            canonical_key(speaker),
            {int(row["chapter_id"]) for row in speaker_rows},
        )
    local_count = 0
    for speaker, speaker_rows in speaker_groups:
        # The same resolver the gate used, so a character that passed the gate on text
        # evidence is cast as what passed rather than as "unknown".
        gender, _reason = resolve_gender(speaker_rows, rows, locked_genders)
        age = _majority(speaker_rows, "age")
        local = is_local_speaker(speaker)
        display_name = local_speaker_display(speaker) if local else speaker
        canonical = canonical_key(speaker if local else display_name)
        confidence = sum(float(row["confidence"]) for row in speaker_rows) / max(1, len(speaker_rows))
        importance = "minor" if local or len(speaker_rows) < minimum_main_mentions else "main"
        character_id = db.upsert_character(
            canonical_name=canonical,
            display_name=display_name,
            gender=gender,
            age=age,
            personality=_personality(speaker_rows),
            mentions=len(speaker_rows),
            importance=importance,
            confidence=confidence,
        )
        for alias in sorted(aliases_by_speaker.get(speaker, {speaker}), key=str.casefold):
            db.add_alias(character_id, alias, normalize_name(alias), confidence, "analysis")
        db.set_character_for_speaker(speaker, character_id)
        profile_id = _pinned_profile_id(db, locked_voices, canonical, allocator, local, log)
        if profile_id is None:
            preset, formant_ratio, age_pitch = allocator.choose(
                gender,
                npc=local,
                age=age,
                prominent=importance == "main",
                who=canonical,
            )
            profile_id = _profile_for_preset(
                db, preset, formant_ratio, profile_cache, age_pitch=age_pitch
            )
        db.set_voice_for_character_segments(character_id, profile_id)
        local_count += int(local)

    anonymous_labels = {
        "male": "NPC vô danh nam",
        "female": "NPC vô danh nữ",
        "unknown": "NPC vô danh chưa rõ giới tính",
    }
    anonymous_count = 0
    for gender in ("male", "female", "unknown"):
        anonymous_rows = anonymous_by_gender.get(gender, [])
        if not anonymous_rows:
            continue
        display_name = anonymous_labels[gender]
        confidence = sum(float(row["confidence"]) for row in anonymous_rows) / len(anonymous_rows)
        character_id = db.upsert_character(
            canonical_name=f"ANONYMOUS_{gender.upper()}",
            display_name=display_name,
            gender=gender,
            age=_majority(anonymous_rows, "age"),
            personality="minor local characters without a stable identity",
            mentions=len(anonymous_rows),
            importance="minor",
            confidence=confidence,
        )
        # The anonymous groups are cast here rather than in the loop above, and they carry
        # a pinned voice for the same reason a named character does: a listener hears "the
        # unnamed men in this scene" as a voice, and it changing between versions is the
        # same defect however minor the characters are.
        anonymous_canonical = f"ANONYMOUS_{gender.upper()}"
        profile_id = _pinned_profile_id(
            db, locked_voices, anonymous_canonical, allocator, True, log
        )
        if profile_id is None:
            preset, formant_ratio, age_pitch = allocator.choose(
                gender,
                npc=True,
                age=_majority(anonymous_rows, "age"),
                who=anonymous_canonical,
            )
            profile_id = _profile_for_preset(
                db, preset, formant_ratio, profile_cache, age_pitch=age_pitch
            )
        db.set_character_and_voice_for_segments(
            [int(row["id"]) for row in anonymous_rows],
            character_id,
            profile_id,
        )
        anonymous_count += 1

    used_voices = len({str(profile["preset_name"]) for profile in db.list_voice_profiles()})
    voice_variants = len(profile_cache)
    assert_voice_stability(db, log)
    log(
        f"Đã khóa voice casting VieNeu: dùng {used_voices}/{len(VIENEU_PRESETS)} preset; "
        f"{voice_variants} biến thể giọng; "
        f"{local_count} NPC có danh tính cục bộ, {anonymous_count} nhóm NPC generic theo giới tính."
    )
