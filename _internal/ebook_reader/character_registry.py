from __future__ import annotations

import re
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Callable, Iterable

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


# Một đại từ không phải một nhân vật: `build_registry_and_cast` đẩy mọi dòng có tên là đại từ
# vào nhóm vô danh thay vì cast như một người. Nó làm việc ấy đúng - `Tôi` ở alpha55 **không**
# có dòng `characters` nào, 33 câu của nó đọc bằng giọng nhóm vô danh.
#
# `me` thêm vào 2026-09-15 vì đúng cái lỗ ấy: cuốn 1 kể ở ngôi thứ nhất và mô hình khai người
# nói là `ME` (tiếng Anh) cho **94 câu** thoại của chính nhân vật chính. "me" không nằm ở đây
# nên `ME` thành một nhân vật đầy đủ - `characters` có dòng riêng, `importance='main'`, 54 lần
# nhắc - và ở lô 8 nó còn **chia giọng với JAKE**. Đo trên cả hai cuốn: thêm những mục dưới đây
# chặn đúng **một** cái tên, `ME`; `tao`, `tui`, `tớ`, `chúng tôi`, `chúng mình` không khớp gì
# hôm nay và ở đây để lần sau khỏi phải sửa lại.
#
# `me` là tiếng Anh, nhưng một nhãn **toàn bộ** là "me" thì không bao giờ là tên người trong một
# cuốn tiếng Việt, và phép so này chỉ so với toàn bộ nhãn (`normalize_name`).
#
# Tiếng xưng hô ngôi thứ ba tiếng Việt (`bà`, `ông`, `cha`, `mẹ`) **không** ở đây: chúng là một
# NGƯỜI THẬT chưa được gọi tên - đọc ca thật, `BÀ` ở chương 21 cuốn 1 là người đàn bà giả làm
# mẹ và 3 câu ấy đúng là lời của bà - nên chỗ của chúng là `GENERIC_SPEAKER_TRAITS` +
# `NPC_LOCAL:`, sau một phép đo còn thiếu (xem docs/OPTIMISATION_QUEUE.md).
PRONOUNS = {
    "hắn", "nàng", "cô ấy", "anh ấy", "ông ấy", "bà ấy", "người đó", "kẻ đó",
    "ta", "tôi", "mình", "chúng ta", "bọn họ",
    "me", "tao", "tui", "tớ", "chúng tôi", "chúng mình",
}
# Đại từ ngôi thứ nhất SỐ ÍT, tập con của `PRONOUNS`. Một cuốn kể ngôi thứ nhất có thể nói cho
# dự án biết "tôi" là ai (`voices.first_person_identity`), và khi ấy những nhãn này là lời của
# CHÍNH người ấy - xem `resolve_first_person_labels`.
#
# Số nhiều không ở đây: một câu mang nhãn `chúng ta` / `chúng tôi` / `bọn họ` không phải lời của
# một người, nên viết lại nó về một danh tính là sai. Ngôi thứ ba (`hắn`, `nàng`, `cô ấy`) càng
# không: đó là người khác, và chỗ của chúng vẫn là nhóm vô danh.
FIRST_PERSON_PRONOUNS = {"tôi", "ta", "mình", "tớ", "tao", "tui", "me"}
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


# Nhãn vắng mặt trong sách mà lệch HAI ký tự: vẫn là cùng một người viết sai, nhưng chỉ gom khi đích duy nhất và
# nhãn đủ dài - hai ký tự trên bốn thì đã là một cái tên khác.
TWO_EDIT_MINIMUM_LENGTH = 5


def _within_two_edits(left: str, right: str) -> bool:
    """Lệch nhau đúng hai ký tự (thay/thêm/bớt). Bằng nhau hay lệch một thì KHÔNG tính - lệch một đã có luật riêng."""
    if left == right or abs(len(left) - len(right)) > 2 or _within_one_edit(left, right):
        return False
    previous = list(range(len(right) + 1))
    for index, letter in enumerate(left, 1):
        current = [index]
        for position, other in enumerate(right, 1):
            current.append(min(previous[position] + 1, current[position - 1] + 1,
                               previous[position - 1] + (letter != other)))
        previous = current
    return previous[-1] == 2


def _two_edit_candidates(folded_name: str, present: "Sequence[str]") -> list[str]:
    """Ứng viên cách hai ký tự, chỉ khi CHỈ CÓ MỘT cách viết đích - hai đích khác nhau thì không đoán."""
    if len(folded_name) < TWO_EDIT_MINIMUM_LENGTH:
        return []
    matches = [
        other
        for other in present
        if _within_two_edits(folded_name, fold_for_source_search(other).strip())
    ]
    if len({fold_for_source_search(other).strip() for other in matches}) != 1:
        return []
    return matches


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
            # Lệch hai ký tự: `JOCLEYN` -> `Jocelyn`, `ARTELI` -> `ARTIL` (bạn cùng lỗi của nó, `ARTEL`, đã gom
            # bằng luật lệch một - một mình `ARTELI` đứng lại thành nhân vật riêng là vô nghĩa).
            candidates = _two_edit_candidates(folded_name, present)
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
    # Phiếu CHIA (cả hai giới đều có phiếu) nghĩa là model đang lưỡng lự, nên hỏi văn bản TRƯỚC khi đếm đa số:
    # một đa số mỏng vẫn thắng được thì văn bản không bao giờ được hỏi, và NEESHKA (9 nam/12 nữ trong khi văn bản
    # 23 nam/7 nữ, gọi "Ngài Neeshka", "quý ông"), CHLOE, LAUREN đều bị đọc bằng giọng nữ vì thế.
    names = {str(row["speaker"]) for row in identity_rows}
    evidence = _gendered_word_evidence(all_rows, names)
    decided = _decisive(evidence)
    if decided is not None:
        return decided, f"text:{evidence.get('male', 0)}nam/{evidence.get('female', 0)}nữ"
    if ranked and ranked[0][1] > ranked[1][1]:
        return ranked[0][0], "model_majority"
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
            # Giới tính do NGƯỜI ghim (`cli cast --character X --gender ...`) là bằng chứng, và là
            # bằng chứng mạnh nhất có thể có. Không đọc nó thì chính cách chữa mà thông điệp lỗi
            # mách - và mà `_command_cast` tồn tại vì nó, "readable before casting has ever run" -
            # không mở được cổng: người nghe trả lời đúng câu hỏi ấy mà cổng vẫn chặn.
            and not str((locked or {}).get(identity, "")).strip()
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

    # Thiếu bằng chứng giới tính cũng **không** giết lượt chạy nữa, vì đúng lý lẽ đã viết ở trên
    # cho ca mâu thuẫn - và ca này còn nhẹ hơn: mâu thuẫn là model nói hai điều, thiếu là model
    # không nói gì. Cuốn 2 lô 2 chết ở đây lúc 19:30 ngày 14-09 sau 5,5 giờ phân tích trọn 3.749
    # đoạn, vì hai cái tên bảy câu thoại: `Luke` (người thật, model không đoán được) và `Nghe`
    # (không phải người - chữ mở đầu câu tường thuật ngay sau lời thoại bị nhận thành tên).
    #
    # Đường ra vẫn như ca mâu thuẫn: đúc bằng giọng trung tính, log to, và trả về cho chỗ gọi
    # phát `CASTING_GENDER_UNRESOLVED` để nó nằm trong báo cáo. Người nghe sửa bằng một lệnh.
    for identity, mention_count in sorted(missing_named_genders.items()):
        detail = {
            "gender_evidence": "none",
            "mentions": int(mention_count),
            "cast_as": "unknown",
        }
        log(
            f"Giới tính của {identity} không có bằng chứng nào ({mention_count} câu); đúc bằng "
            f"giọng trung tính và đi tiếp. Sửa bằng: cli cast --character {identity} --gender ..."
        )
        gender_conflicts.setdefault(identity, detail)
    # Một danh tính mang hai voice profile thì VẪN ném: đó là dữ liệu tự mâu thuẫn, không phải
    # một câu hỏi không trả lời được, và đi tiếp là xuất bản hai giọng cho một người.
    if identity_instability:
        raise RuntimeError(
            "Casting input quality gate failed: voice identity instability="
            f"{identity_instability}"
        )
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
    def __init__(
        self,
        narrator_voice: str,
        max_pitch_shift: int,
        other_narrators: Iterable[str] = (),
    ) -> None:
        self.narrator_voice = narrator_voice
        # Every voice that has narrated this book, not only the one narrating this project. A
        # book that changes narrator part-way (book 2: Phạm Tuyên for 000..303, Đức Trí from
        # 304) has taught the listener that the old voice IS the narration; a character who
        # speaks in it later sounds like the narrator cutting into the dialogue. Empty unless
        # `voices.other_narrators` says otherwise, so the set is `{narrator_voice}` as before.
        self.not_for_characters = frozenset(
            {str(narrator_voice), *(str(name) for name in other_narrators)}
        )
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
            if preset["name"] not in self.not_for_characters
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
                if preset["name"] not in self.not_for_characters
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
                if preset["name"] not in self.not_for_characters
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

        ranked_presets = sorted(candidates, key=rank)
        selected = ranked_presets[0]
        if who and abs(formant_ratio_for_age(str(selected["name"]), age, gender) - 1.0) > 1e-6:
            # Tuổi ấn định bậc formant, nên với trẻ con preset là trục đa dạng DUY NHẤT — và
            # `usage` đếm theo pool (có tên / NPC), nên một đứa trẻ có tên và một NPC trẻ con
            # cùng chương đều thấy Ngọc Linh "chưa ai dùng". Lô 7, chương 186: AEREN (3 câu)
            # và NPC CON TRAI (1 câu) cùng `ngoc_linh_f107_p+02` - người nghe lẫn. Cùng lớp với
            # CÔNG TƯỚC/ÔNG LÃO ở alpha.55: hai sổ, một giọng. Ở đây hỏi thẳng sổ người giữ -
            # cùng sổ mà `_first_free_variant` hỏi: preset hạng đầu mà bậc-theo-tuổi của nó đã
            # có người CÙNG CHƯƠNG giữ thì lấy preset kế tiếp; không preset nào rảnh thì về
            # hạng đầu như cũ. Đứa trẻ đầu tiên vẫn nhận đúng giọng người nghe ưa thích.
            mine = self.chapters_of.get(str(who), set())
            for preset in ranked_presets:
                preset_name = str(preset["name"])
                step = round(float(formant_ratio_for_age(preset_name, age, gender)), 3)
                held = self.holders.get(preset_name, {}).get(step, set())
                if not any(self.chapters_of.get(holder, set()) & mine for holder in held):
                    selected = preset
                    break
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
        # thì bậc ÍT người giữ hơn, rồi mới tới bậc thấp hơn trên thang (tất định, tái lập
        # được). Không biết gì về người sắp cast
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

        def crowd(ratio: float) -> int:
            return len(holders.get(round(ratio, 3), ()))

        # Hoà về chương chung (thường là 0: người mới chưa gặp ai) thì chọn bậc ÍT người giữ
        # hơn, rồi mới tới thứ tự thang. Bản trước hoà là lấy bậc thấp nhất, nên lô 6 xếp sáu
        # nhân vật phụ (KAIN REICHARDT, ERWIN, DAMIAN, LEON, GÃ, DORON) chồng lên đúng một bậc
        # thai_son_f100 trong khi bốn bậc khác cùng 0 chương chung chỉ có một người giữ. Không
        # ai cùng chương nên người nghe không lẫn trong lô ấy, nhưng sáu người một giọng là
        # mười lăm cặp có thể gặp nhau ở lô sau, và cảnh báo "nhiều nhân vật dùng chung một
        # giọng" đã bật. Đo 2026-09-12 15:27 trên lo06_99a908b8f8.
        ranked = sorted(
            enumerate(variants),
            key=lambda pair: (shared_chapters(pair[1]), crowd(pair[1]), pair[0]),
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


def _book_exposure(db: Any) -> dict[str, int]:
    """Số câu cộng dồn qua cả chuỗi lô, theo `canonical_key` - sổ `character_exposure`.

    Sổ do `scripts/backfill_exposure.py` ghi vào project trước mỗi lô; project không có sổ (cũ, test,
    một bản sao) trả rỗng, và mọi phép xếp hạng dùng nó trở về như khi chưa có nó.
    """
    try:
        with db.connect() as conn:
            rows = conn.execute("SELECT canonical_name, dialogue_lines FROM character_exposure").fetchall()
    except Exception:  # noqa: BLE001 - bảng vắng, db giả trong test: không có sổ thì không xếp theo sổ
        return {}
    exposure: dict[str, int] = {}
    for name, lines in rows:
        key = canonical_key(str(name))
        exposure[key] = max(exposure.get(key, 0), int(lines or 0))
    return exposure


def _drop_pins_that_share_a_chapter(
    rows: list[Any],
    locked_voices: dict[str, str],
    log: Any,
    exposure: dict[str, int] | None = None,
) -> dict[str, str]:
    """Bỏ pin của người ít câu hơn khi hai người CÙNG GHIM một giọng và CÙNG NÓI một chương.

    `_pinned_profile_id` tôn trọng pin vô điều kiện, và điều đó đúng cho tới khi pin được phép
    dùng chung: từ 11:00 ngày 2026-09-15 `pin_the_book_cast` cho hai người **chưa từng cùng
    chương** chia một giọng (đúng luật holder của bộ cấp giọng). Ở lô sau họ có thể gặp nhau, và
    lô 3 cuốn 2 gặp ngay: **5 va chạm cùng chương, cả 5 là pin gặp pin** — Verdi + Christopher ở
    chương 12 và 14, Rhine + ORVARIT ở 16, SMILE + SARD ở 32, Camil + Nghe ở 36.

    Doanh nghĩa của dự án xếp "hai người một giọng trong cùng chương" **nặng hơn** "một người đổi
    giọng giữa các chương" (người nghe tưởng là cùng một người, ngay trong một cảnh). Nên ở đúng
    chỗ hai điều ấy xung đột, nhất quán phải nhường.

    Ai giữ: người **quen hơn trên cả cuốn** - số câu cộng dồn qua chuỗi lô (`exposure`, sổ
    `character_exposure`), rồi mới tới số câu trong lô. Bản trước xếp theo số câu trong lô, và lô 8 cuốn 2
    (19-09) bỏ pin của VICTOR - 329 câu qua 18 lô, 64 chương một giọng - vì MORRIS (54 câu cả cuốn) nói
    nhiều hơn trong riêng lô ấy; VICTOR đổi giọng ở 4 chương. Không có sổ thì như cũ. Người kia mất pin và
    đi qua `allocator.choose()`, thứ đã tránh người cùng chương sẵn.
    """
    exposure = exposure or {}
    if not locked_voices:
        return locked_voices
    chapters: dict[str, set[int]] = {}
    lines: dict[str, int] = {}
    for row in rows:
        speaker = str(row["speaker"])
        if speaker.casefold() in RESERVED_SPEAKERS:
            continue
        identity = canonical_key(speaker)
        if identity not in locked_voices:
            continue
        chapters.setdefault(identity, set()).add(int(row["chapter_id"]))
        lines[identity] = lines.get(identity, 0) + 1
    by_voice: dict[str, list[str]] = {}
    for identity, voice in locked_voices.items():
        if identity in chapters:
            by_voice.setdefault(voice, []).append(identity)
    dropped: set[str] = set()
    for voice, identities in sorted(by_voice.items()):
        if len(identities) < 2:
            continue
        # Người quen hơn trên cả cuốn trước, rồi người nhiều câu trong lô; ai đã giữ thì người sau chỉ
        # mất pin nếu CHẠM chương của họ.
        ranked = sorted(
            identities,
            key=lambda name: (-exposure.get(name, 0), -lines.get(name, 0), name),
        )
        holders: list[str] = []
        for identity in ranked:
            clash = next(
                (
                    holder
                    for holder in holders
                    if chapters[identity] & chapters[holder]
                ),
                None,
            )
            if clash is None:
                holders.append(identity)
                continue
            dropped.add(identity)
            shared = sorted(chapters[identity] & chapters[clash])
            log(
                f"Bỏ giọng đã ghim của {identity} ({lines.get(identity, 0)} câu, "
                f"{exposure.get(identity, 0)} cả cuốn): trùng {voice} với {clash} "
                f"({lines.get(clash, 0)} câu, {exposure.get(clash, 0)} cả cuốn) ở chương {shared}. "
                "Hai người một giọng trong cùng chương nặng hơn một người đổi giọng."
            )
    if not dropped:
        return locked_voices
    return {name: voice for name, voice in locked_voices.items() if name not in dropped}


VOICE_KEY_SUFFIX_PATTERN = re.compile(r"^preset_(?P<body>.+)_f(?P<formant>\d+)_p(?P<pitch>[+-]\d+)$")


def voice_is_child_pitched(voice_key: str) -> bool:
    """Giọng này có mang đúng PITCH TRẺ CON của preset nó dùng không?

    Chỉ đọc pitch, cố ý không đọc formant: đo trên 117 `voice_key` của cuốn 2 thì 87 formant không khớp phép
    biến đổi tuổi nào - bộ cấp giọng dùng formant để TÁCH hai người chung preset - còn 108 pitch thì khớp.
    Và pitch trẻ con là dấu sắc nhất: đúng 1 trong 266 giọng ghim mang nó.
    """
    match = VOICE_KEY_SUFFIX_PATTERN.match(str(voice_key))
    if match is None:
        return False
    pitch = int(match.group("pitch"))
    for preset in VIENEU_PRESETS:
        if _preset_slug(str(preset["name"])) != match.group("body"):
            continue
        gender = str(preset["gender"])
        child = age_pitch_semitones("child", gender, str(preset["name"]))
        adult = age_pitch_semitones("adult", gender, str(preset["name"]))
        return pitch == child != adult
    return False


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
        # Luật THỨ HAI, thêm 20-09 và hẹp bằng một phép đo: giọng mang đúng pitch TRẺ CON của preset nó
        # dùng, trong khi người nghe đã ghim một tuổi KHÁC trẻ con. Không có nó thì ghim `--age adult` của
        # KAELYN không làm gì cả - preset nữ khớp nhãn nữ nên luật phái im lặng, và bà vẫn được đọc bằng
        # giọng bé gái. Chỉ đọc PITCH: formant là bước tách giọng (87/117 không khớp tuổi nào).
        child_pitched = bool(age and age != "child" and voice_is_child_pitched(voice_key))
        contradicts = contradicts or child_pitched
        if not contradicts:
            kept[key] = voice_key
            continue
        reason = (
            f"mang pitch trẻ con mà người nghe đã ghim tuổi {age}"
            if child_pitched
            else f"là preset {preset}, còn người nghe đã ghim {gender}" + (f"/{age}" if age else "")
        )
        log(f"Bỏ giọng ghim của {key}: {voice_key} {reason} - cấp lại giọng.")
        db.event(
            "warning",
            "CASTING_PIN_CONTRADICTS_A_PERSON",
            f"{key}: dropped ported voice {voice_key}",
            {"character": key, "voice_key": voice_key, "preset_gender": preset,
             "locked_gender": gender, "locked_age": age},
        )
    return kept


def resolve_first_person_labels(
    db: ProjectDB,
    settings: dict[str, Any],
    log: Callable[[str], None],
) -> int:
    """Một cuốn kể ngôi thứ nhất: nhãn `tôi` / `ta` / `me` là lời của CHÍNH người kể.

    Không có `voices.first_person_identity` thì hàm này không làm gì - và đó là mặc định, vì
    "tôi là ai" là **một sự thật về cuốn sách**, không phải thứ máy suy ra được. Cùng họ với
    `EBOOK_SOURCE_DIR`, `EBOOK_PLAN`, `EBOOK_ALBUM`: chủ sách nói, dự án ghi vào project.

    Đo lúc 04:00 ngày 2026-09-16 trên dữ liệu thật của hai cuốn, và hai cuốn cho hai câu trả lời
    trái nhau - đó là lý do phải có công tắc thay vì một luật chung:

    - **Cuốn 1** (kể ngôi thứ nhất): 129 câu mang nhãn ngôi thứ nhất, ba cách viết (`ME` 94,
      `Tôi` 34, `TÔI` 1), tất cả là lời của nhân vật chính. Trước bản vá chúng bị cast thành
      **hai giọng nam khác** anh ta; sau `patch_a_pronoun_is_not_a_character` chúng về nhóm vô
      danh - một giọng sai nhưng nhất quán; với `first_person_identity=SAMAEL` chúng về đúng
      giọng mà 451 câu khác của anh ta đang dùng.
    - **Cuốn 2** (kể ngôi thứ ba): 10 câu mang nhãn `Mình`, và **cả 10 là nhật ký của nữ phù
      thủy** mà Lucien đang đọc (chương 022/023/032) - tức lời của người thứ ba, không phải của
      người kể. Nếu luật này tự bật thì nó sẽ gán nhật ký ấy cho một danh tính sai. Cuốn 2 để
      trống công tắc và không đổi một chút nào.

    Viết lại nhãn trong SQLite (`rewrite_speaker`) chứ không chỉ đổi lúc phân vai: sau đó mọi
    tầng dưới - báo cáo, `one_person_one_voice`, số lần nhắc, pin - đều thấy cùng một người, và
    đó chính là lối `RESERVED_SPEAKERS` ở trên đã đi cho `NARRATOR`/`UNKNOWN`.
    """
    identity = str(settings.get("voices", {}).get("first_person_identity", "")).strip()
    if not identity:
        return 0
    if normalize_name(identity) in PRONOUNS:
        # Một đại từ không thể là câu trả lời cho "tôi là ai": phép so ở `build_registry_and_cast`
        # gấp chữ, nên dù có viết lại nhãn thành `TÔI` thì nó vẫn khớp `PRONOUNS` và vẫn về nhóm
        # vô danh - công tắc sẽ im lặng vô dụng. `cli create --first-person` từ chối thẳng; ở đây
        # thì nói ra rồi không làm gì, vì nổ giữa lúc phân tích là làm chết cả lô.
        log(f'"{identity}" là một đại từ, không phải một danh tính - bỏ qua first_person_identity.')
        db.event(
            "warning",
            "FIRST_PERSON_IDENTITY_IS_A_PRONOUN",
            f"voices.first_person_identity={identity!r} is a pronoun, not a character",
            {"identity": identity},
        )
        return 0
    canonical = canonical_key(identity)
    moved = 0
    labels: list[str] = []
    for speaker in sorted({str(row["speaker"]) for row in db.list_segments()}):
        if normalize_name(speaker) not in FIRST_PERSON_PRONOUNS:
            continue
        if canonical_key(speaker) == canonical:
            continue
        rewritten = db.rewrite_speaker(speaker, canonical)
        if rewritten:
            moved += rewritten
            labels.append(f"{speaker}={rewritten}")
    if moved:
        log(
            f"{moved} câu mang nhãn đại từ ngôi thứ nhất về {canonical} "
            f"({', '.join(labels)}): cuốn này kể ở ngôi thứ nhất."
        )
        db.event(
            "info",
            "FIRST_PERSON_LABELS_RESOLVED",
            f"{moved} first-person pronoun lines were attributed to {canonical}",
            {"identity": canonical, "labels": labels},
        )
    return moved


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

    resolve_first_person_labels(db, settings, log)

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
    # Sau khi pin đã qua phép kiểm "đúng phái", tới phép kiểm "không hai người một giọng trong
    # một chương". Thứ tự này có chủ ý: một pin sai phái thì bỏ dù có va chạm hay không, còn
    # phép kiểm dưới đây chỉ nói về những pin còn lại.
    locked_voices = _drop_pins_that_share_a_chapter(
        rows, locked_voices, log, exposure=_book_exposure(db)
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
        other_narrators=tuple(voice_cfg.get("other_narrators", ())),
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
    # Cả ba nhóm NPC vô danh cũng phải khai, vì chúng cũng được `choose()` - ở khối riêng bên
    # dưới - và "cho MỌI người" ở trên phải đúng nghĩa. Không khai thì `chapters_of` của chúng
    # rỗng, `shared_chapters` trả 0 cho mọi bậc, và khi thang bậc đã cạn chỗ trống thì tie-break
    # lùi về bậc thấp nhất - đúng bậc người đông lời nhất đang giữ. Cuốn 2 lô 1: nhóm "NPC vô
    # danh nam" rơi vào bậc 1,00 của Thanh Bình, tức giọng của LUCIEN, ở ba chương 022/023/032;
    # chương 022 đã lên sách với nhân vật chính tự nói với mình 6 câu.
    for anonymous_gender, anonymous_gender_rows in anonymous_by_gender.items():
        if not anonymous_gender_rows:
            continue
        allocator.note_chapters(
            f"ANONYMOUS_{anonymous_gender.upper()}",
            {int(row["chapter_id"]) for row in anonymous_gender_rows},
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
