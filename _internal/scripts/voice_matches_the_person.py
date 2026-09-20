"""Giọng có đúng là giọng của người ấy không — phái, và tuổi, trên cả cuốn sách đã ghép.

    python scripts/voice_matches_the_person.py                 # báo cáo
    python scripts/voice_matches_the_person.py --recast         # in `B:NNN` cho boundary.sh
    python scripts/voice_matches_the_person.py <project>        # một project

Hai công cụ đã có đều hỏi về **tính nhất quán**: `voice_pool_pressure` hỏi "hai người có chung
một giọng không", `one_person_one_voice --across` hỏi "một người có hai giọng không". Không ai
hỏi câu đơn giản hơn: *giọng ấy có đúng không*. Một cuốn sách hoàn toàn nhất quán vẫn có thể đọc
một người đàn ông bằng giọng con gái ở mọi chương.

Đo lần đầu 23:00 ngày 2026-09-11 trên sách 116 chương: 451 dòng (chương × nhân vật × giọng), 61
tên. Kết quả và cái bẫy trong nó:

    lệch phái, thô               11 dòng / 5 tên
    trừ luật giọng trẻ con        1 dòng / 1 tên   <- con số thật
    đổi tuổi giữa các chương      5 tên, 3 trong đó đổi cả giọng

**Luật giọng trẻ con là có thật và có chủ ý** (`voice_catalog.AGE_TARGET_PITCH_HZ`,
`child_voice_preference`): preset nam không với tới được ống âm của một đứa trẻ — chúng dừng
cách 0,8 cm — nên một đứa trẻ trai được đọc bằng preset **nữ** kéo cao formant và pitch. Vậy
"nam đọc bằng giọng nữ" chỉ là lỗi khi `age` không phải `child`. Một công cụ không biết luật ấy
sẽ báo EVERAN (nam, `child`, 36 câu) là lỗi và làm người đọc báo cáo mất niềm tin vào chín con
số còn lại.

Đo lần hai, 2026-09-20 12:3x, trên **cuốn 2** đã ghép (417 chương, 2.304 dòng, 446 tên): 13 dòng giọng sai phái,
8 tên, 37 câu. Nhưng cột bằng chứng văn bản (thêm cùng ngày) cho thấy con số 37 ấy gộp BA thứ khác nhau, và cách
sửa của chúng ngược nhau:

| tên | câu | sổ ghi | giọng | văn bản | ai sai |
|---|---|---|---|---|---|
| HATHAWAY | 12 | male | nữ | "bà" x42, "cô" x48, không một "ngài/ông" nào | **SỔ sai** - giọng đúng |
| CHRISTOPHER | 8 | male | nữ | "ngài" x29, "thầy" x12 | **GIỌNG sai** - và là ca rối nhất, xem dưới |
| AMELTON | 6 | male | nữ | "cô" x6 so với "ngài" x1 | **SỔ sai** - giọng đúng |
| ARTHUR DOYLE | 5 | female | nam | "ngài" x1 + "ông" x2 | **SỔ sai** - giọng đúng |
| SALA | 2 | female | nam | không danh xưng nào | **chưa rõ** - giữ trong danh sách đúc lại |
| MAG | 1 | female | nam | không danh xưng nào | **chưa rõ** - giữ trong danh sách đúc lại |
| LAUREN | 2 | male | nữ | "ngài" x15 | **GIỌNG sai** |
| DONA | 1 | male (lúc thu) | nữ | không danh xưng nào | **chưa rõ** - giữ trong danh sách |

Tức trong 37 câu bị gắn cờ: **23 câu** danh xưng nói SỔ mới là bên sai (HATHAWAY, AMELTON, ARTHUR DOYLE - giọng
đang ĐÚNG, đúc lại là phá), **10 câu** là GIỌNG sai (CHRISTOPHER 8, LAUREN 2), và **4 câu** không danh xưng nào nên
chưa phán xử được (SALA, MAG, DONA). Ba cái tên "sổ sai" đã ghim lại bằng `cli cast --gender` ngay giữa lô 10 (dữ
liệu, không phải mã; nhịp tim pipeline không hụt giây nào) nên nhãn nay thuận với giọng - và **không phải đúc lại
gì cả**. `--recast` nay tự lọc: **13 chương -> 7 chương** (5 chắc + 2 chưa phán xử được). Chưa phán xử được thì
GIỮ LẠI chứ không bỏ: một danh sách rỗng im lặng nói "không có việc gì" trong khi có.

**CHRISTOPHER là ca rối nhất và CHƯA sửa được** - đọc lịch sử giọng của anh ta thì thấy đúng cái bẫy IVAN, nhưng
nặng hơn:

    chương 094        age=unknown  ngoc_linh_f107_p+02   3 câu   <- giọng trẻ/nữ
    chương 095-097    age=unknown  thanh_binh_f090_p-04  5 câu   <- giọng nam
    chương 109-149    age=unknown  thai_son / thanh_binh 22 câu  <- giọng nam
    chương 284-296    age=CHILD    ngoc_linh_f107_p+02   31 câu  <- luật trẻ con, có chủ ý
    chương 305-306    age=unknown  ngoc_linh_f107_p+02   5 câu   <- giọng trẻ NẰM LẠI sau khi hết `child`

Năm cách đọc cho một cái tên. **Đã đọc truyện và phân xử xong (20-09 13:3x): MỘT người, và là người lớn tuổi.**
Ông là chủ tịch Hiệp hội Nhạc sĩ - "ngài Chủ tịch Christopher", "bậc thầy Christopher", "bậc tiền bối", đã có
"buổi hòa nhạc cuối cùng trong sự nghiệp" (chương 109) rồi chuyển sang chủ tịch danh dự (chương 284). Không có
Christopher trẻ con nào; nhãn `age=child` ở 284-296 là model gán sai cho một ông già.

Đã ghim `cli cast --character CHRISTOPHER --gender male --age elderly`. Không cần bản vá nào: luật
`_drop_pins_that_contradict_a_person` trong `character_registry.py` đã bỏ giọng ghim khi nó trái với thứ NGƯỜI đã
ghim (trừ `age=child`, và nay age đã là `elderly`), nên giọng `ngoc_linh_f107_p+02` sẽ bị bỏ và ông được cấp lại
giọng nam lớn tuổi ở lượt phân vai kế. 39 câu ĐÃ THU vẫn giữ giọng cũ cho tới một lượt đúc lại thật.

Bài học về công cụ: cái thiếu không phải một luật mới mà là **một ghim của người nghe**, và báo cáo này chính là
thứ chỉ ra ai cần được ghim. Chạy nó sau mỗi vài lô.

## Trục TUỔI: soát nhãn `age=child` bằng văn bản (thêm 20-09 14:0x)

Báo cáo nay có thêm một mục. Vì sao nó phải có: **tuổi chọn HỌ GIỌNG** (trẻ con đọc bằng preset nữ kéo cao), mà
đáp án chuẩn chấm bảy trục và **tuổi không có trong đó** - nên một nhãn tuổi sai không có thước nào bắt, ngoài chỗ
này. Đo trên cuốn 2: bốn tên từng mang `age=child`, và ba trong bốn là SAI:

| tên | câu | danh xưng người lớn trong nguồn | chữ trẻ con | phán xử |
|---|---|---|---|---|
| CHRISTOPHER | 31 | ngài 29, thầy 12, chủ tịch 6, ông 3 | 0 | **sai** - chủ tịch Hiệp hội Nhạc sĩ, đã ghim `elderly` |
| KAELYN | 23 | phu nhân 3 | 2 | **sai** - "vợ của quản gia", "thưa phu nhân"; đã ghim `adult` |
| LUCIEN | 11 | ngài 88, thầy 2, giáo sư 2 | 39 | **sai** nhưng VÔ HẠI: giọng anh ta đã ghim từ trước nên nhãn không đổi được giọng nào |
| SPRINT | 6 | ngài 1 | 3 | chưa rõ - để lại |

Hai người bị đọc bằng giọng trẻ con **54 câu** vì một nhãn tuổi. Cả hai đã ghim bằng `cli cast --gender ... --age ...`
giữa lô 10, và `_drop_pins_that_contradict_a_person` sẽ bỏ giọng ghim trái ghim của người nghe ở lượt phân vai kế.

Chốt đọc bảng này: **danh xưng + tên là tín hiệu mạnh, chữ trẻ con quanh tên là tín hiệu yếu** - y như trục giới
tính. Chữ quanh tên nhiễm cả người khác cùng cảnh: hai chữ "trẻ con" cạnh KAELYN nói về Lena, cô em họ bà ấy tới
đón, chứ không nói về bà.

Con số thật: **IVAN**, `male`, `age=unknown`, 17 câu ở chương 062 đọc bằng `ngoc_linh_f107_p+02`
— giọng nữ kéo cao dành cho trẻ con. Đường đi của lỗi ấy, đọc từ dữ liệu:

    lô 3, chương 072   registry nói `age=child`  (mọi `segments.age` của anh ta: `unknown`)
    lô 3, chương 062   `age=unknown`, nhưng giọng ghim đã là giọng trẻ con -> 17 câu giọng nữ
    lô 3, chương 060   `age=unknown`, 3 câu, `thai_son_f100_p+00` — giọng nam, đúng
    lô 4               `age=unknown`, `locked_voice_key=ngoc_linh_f107_p+02` — port mang theo

Thoại của IVAN đọc như một thanh niên hay lắp: *"T-Tôi tên là Ivan,"*, *"cậu đã m-mượn một ít
t-tiền của bọn tôi…"*, *"Khỏe không, người anh em?"*. Một lần phân loại sai `child` ở lô 3 đã
theo anh ta sang mọi lô sau, vì `port_casting` mang `locked_voice_key` đi cùng danh tính — đúng
cơ chế giữ nhất quán, và nó giữ nguyên cả cái sai.

**ĐÃ CÓ cách sửa** (đoạn này viết lại 20-09 13:4x; bản cũ ghi "chưa có" và "không có `--age`" - sai
từ lúc `--age` được thêm, và một câu lỗi thời thì chặn đúng người định đi sửa). Nay:

    cli cast <project> --character IVAN --gender male --age young

ghim được CẢ tuổi, và `_drop_pins_that_contradict_a_person` (`character_registry.py`) tự bỏ giọng ghim
khi nó trái với thứ người nghe đã ghim - trừ `age=child`, đúng chỗ luật giọng trẻ con cần. Nên thứ tự
đúng vẫn là **ghim trước, đúc lại sau**: đúc lại mà port vẫn mang giọng cũ thì chỉ tốn GPU.

IVAN thuộc **cuốn 1** (đang dừng ở 253/478), nên ghim cho nó chỉ có nghĩa khi cuốn 1 chạy lại - lúc ấy
`source scripts/book1.env` rồi ghim vào project của cuốn 1, không phải project cuốn 2.
"""
from __future__ import annotations

import argparse
import collections
import json
import re
import sqlite3
import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ebook_reader.voice_catalog import VIENEU_PRESETS  # noqa: E402
from scripts.name_marks import fold_dropped_marks  # noqa: E402

try:
    from scripts.book_paths import BOOK, SOURCE_DIR, VERSIONS  # noqa: E402
except ImportError:  # chạy trực tiếp: python scripts/x.py
    from book_paths import BOOK, SOURCE_DIR, VERSIONS  # noqa: E402

VOICES_SQL = """
SELECT ch.title AS chapter, c.canonical_name AS name, c.gender AS gender, c.age AS age,
       v.voice_key AS voice_key, count(*) AS lines
FROM segments s
  JOIN characters c ON c.id = s.canonical_character_id
  JOIN voice_profiles v ON v.id = s.voice_profile_id
  JOIN chapters ch ON ch.id = s.chapter_id
WHERE s.kind = 'dialogue' AND v.voice_key <> 'narrator'
  AND c.canonical_name NOT LIKE 'NPC/_%' ESCAPE '/'
  AND upper(c.canonical_name) NOT LIKE 'ANONYMOUS%'
GROUP BY ch.id, c.id, v.id
"""


def _say(line: str) -> None:
    try:
        print(line)
    except (UnicodeEncodeError, OSError, ValueError):
        sys.stdout.buffer.write(line.encode("utf-8", "replace") + b"\n")


def _slug(name: str) -> str:
    plain = unicodedata.normalize("NFD", str(name))
    plain = "".join(ch for ch in plain if not unicodedata.combining(ch))
    return "_".join(plain.replace("Đ", "D").replace("đ", "d").lower().split())


PRESET_GENDER: dict[str, str] = {_slug(p["name"]): str(p["gender"]) for p in VIENEU_PRESETS}


def preset_gender(voice_key: str) -> str | None:
    """Phái của preset đứng sau một `voice_key`, hoặc None nếu không tra được.

    `voice_key` là `preset_<slug>_f<formant>_p<pitch>`; so tiền tố dài trước để `thanh_binh`
    không bị `thanh` (nếu có ngày thêm preset ấy) nhận nhầm.
    """
    key = str(voice_key)
    key = key[len("preset_") :] if key.startswith("preset_") else key
    for slug, gender in sorted(PRESET_GENDER.items(), key=lambda kv: -len(kv[0])):
        if key.startswith(slug):
            return gender
    return None


def read_rows(project: Path) -> list[dict]:
    """[{chapter, name, gender, age, voice, lines}] của một project; rỗng nếu không đọc được."""
    try:
        conn = sqlite3.connect(f"file:{project / 'project.sqlite3'}?mode=ro", uri=True)
    except sqlite3.Error:
        return []
    try:
        conn.row_factory = sqlite3.Row
        found = conn.execute(VOICES_SQL).fetchall()
    except sqlite3.Error:
        return []
    finally:
        conn.close()
    return [
        {
            "chapter": str(r["chapter"]),
            "name": str(r["name"]),
            "gender": str(r["gender"] or ""),
            "age": str(r["age"] or ""),
            "voice": str(r["voice_key"]),
            "lines": int(r["lines"]),
            "project": project.name,
        }
        for r in found
    ]


def shipped_rows(book: Path = BOOK, versions: Path = VERSIONS) -> list[dict]:
    """Các dòng của những chương ĐÃ LÊN SÁCH, theo `manifest.json` (đúng project nó ghi)."""
    try:
        payload = json.loads((book / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    entries = payload if isinstance(payload, list) else payload.get("chapters", [])
    want: dict[str, tuple[str, str]] = {}
    for item in entries:
        title = str(item.get("title") or "")
        if title:
            want[title] = (str(item.get("version") or ""), str(item.get("project") or ""))
    rows: list[dict] = []
    for version, project in sorted(set(want.values())):
        folder = versions / version / project
        if not (folder / "project.sqlite3").is_file():
            continue
        rows.extend(r for r in read_rows(folder) if want.get(r["chapter"]) == (version, project))
    return rows


def fold_names(rows: list[dict]) -> list[dict]:
    """Gộp cách viết rơi dấu, như `one_person_one_voice` - không gộp thì mỗi cách viết là một người."""
    folded = fold_dropped_marks(sorted({r["name"] for r in rows}))
    return [{**r, "name": folded.get(r["name"], r["name"])} for r in rows]


def wrong_gender(rows: list[dict]) -> list[dict]:
    """Dòng có giọng khác phái mà **luật giọng trẻ con không giải thích**.

    `age == "child"` được miễn: đó là cách dự án đọc trẻ con, có đo và có xếp hạng của người
    nghe (`voice_catalog`). Phái `unknown` cũng được miễn - không biết thì không kết tội.
    """
    return [
        r
        for r in rows
        if r["gender"] in ("male", "female")
        and r["age"] != "child"
        and preset_gender(r["voice"]) is not None
        and preset_gender(r["voice"]) != r["gender"]
    ]


MALE_WORDS_NEAR_NAME = ("ông", "anh", "hắn", "gã", "lão", "cậu", "chàng", "ngài", "thằng", "chú")
FEMALE_WORDS_NEAR_NAME = ("bà", "cô", "chị", "nàng", "ả", "phu nhân", "quý bà")
HONORIFICS = ("ngài", "ông", "bà", "cô", "anh", "chị")


def gender_evidence_in_source(names: set[str]) -> dict[str, str]:
    """Đếm chữ chỉ người quanh mỗi cái tên trong NGUỒN, để biết bên nào sai.

    Một dòng "giọng sai phái" có hai cách sai và cách sửa NGƯỢC nhau: nếu văn bản thuận với `gender` thì
    giọng sai (phải ghim giọng rồi đúc lại); nếu văn bản ngược với `gender` thì cái sai là SỔ, giọng đang
    đúng và đúc lại là làm hỏng. Đo 20-09 trên cuốn 2: trong 8 tên bị gắn cờ, HATHAWAY ("bà" x42, "cô" x48)
    và AMELTON ("cô" x6) là sổ sai chứ không phải giọng sai - đúc lại chúng là đổi giọng đúng thành sai.
    """
    try:
        source = "\n".join(
            path.read_text(encoding="utf-8", errors="ignore")
            for path in sorted(SOURCE_DIR.glob("*.txt"))
        )
    except OSError:
        return {}
    # MỘT lượt quét cho mọi tên - xem `_name_occurrences`. Bản đầu quét cả nguồn một lần cho mỗi tên và
    # báo cáo mất hơn mười phút với 317 tên, tức không dùng được trong nhịp tim.
    wanted = {name.casefold(): name for name in names if name}
    if not wanted:
        return {}
    male: collections.Counter = collections.Counter()
    female: collections.Counter = collections.Counter()
    titled: dict[str, collections.Counter] = {name: collections.Counter() for name in names}
    for match in _name_occurrences(source, wanted):
        name = wanted[match.group(0).casefold()]
        window = source[max(0, match.start() - 45): match.end() + 45].casefold()
        male[name] += sum(window.count(word) for word in MALE_WORDS_NEAR_NAME)
        female[name] += sum(window.count(word) for word in FEMALE_WORDS_NEAR_NAME)
        honorific = _title_right_before(source[max(0, match.start() - 12): match.start()].casefold(), HONORIFICS)
        if honorific:
            titled[name][honorific] += 1
    return {
        name: {"male": male[name], "female": female[name], "titled": dict(titled[name])}
        for name in names
    }


def describe_evidence(evidence: dict) -> str:
    decisive = ", ".join(f"{word} {count}" for word, count in evidence["titled"].items())
    return f"văn bản: nam {evidence['male']}, nữ {evidence['female']}" + (f" | {decisive}" if decisive else "")


MALE_HONORIFICS = ("ngài", "ông", "anh")
FEMALE_HONORIFICS = ("bà", "cô", "chị")
EVIDENCE_MINIMUM_HITS = 5
EVIDENCE_MINIMUM_RATIO = 3.0


def text_verdict(evidence: dict) -> str | None:
    """Phái mà VĂN BẢN chỉ ra, hoặc None khi nó không chỉ đủ rõ.

    Danh xưng + tên ("ngài Lauren", "bà Hathaway") được hỏi TRƯỚC: nó nói trực tiếp về người ấy, còn phép đếm
    chữ quanh tên thì nhiễm cả những người cùng cảnh - HATHAWAY có nam 145 / nữ 150 (gần bằng nhau) mà danh
    xưng thì 90 nữ / 0 nam. Ngưỡng của phép đếm lấy đúng ngưỡng dự án đã đo cho `_decisive` (>= 5 lần, tỉ lệ 3).
    """
    titled = evidence["titled"]
    male_titles = sum(titled.get(word, 0) for word in MALE_HONORIFICS)
    female_titles = sum(titled.get(word, 0) for word in FEMALE_HONORIFICS)
    for winner, mine, theirs in (("male", male_titles, female_titles), ("female", female_titles, male_titles)):
        if mine >= 3 and (theirs == 0 or mine / theirs >= EVIDENCE_MINIMUM_RATIO):
            return winner
    male, female = evidence["male"], evidence["female"]
    winner, mine, theirs = ("male", male, female) if male >= female else ("female", female, male)
    if mine >= EVIDENCE_MINIMUM_HITS and (theirs == 0 or mine / theirs >= EVIDENCE_MINIMUM_RATIO):
        return winner
    return None


def _name_occurrences(source: str, wanted: dict[str, str]):
    """Mọi lần xuất hiện của MỌI cái tên, trong MỘT lượt quét.

    Bản đầu quét cả nguồn 9 MB một lần cho mỗi tên: 317 tên x 9 MB nên báo cáo chạy hơn mười phút và
    không dùng được trong nhịp tim. Một alternation duy nhất đưa nó về một lượt.
    """
    alternation = "|".join(sorted((re.escape(key) for key in wanted), key=len, reverse=True))
    return re.finditer(rf"(?<![\wÀ-ỹ])(?:{alternation})(?![\wÀ-ỹ])", source, re.IGNORECASE)


def _title_right_before(before: str, titles: "tuple[str, ...]") -> str | None:
    """Danh xưng đứng NGAY TRƯỚC tên, nếu có. `before` đã hạ chữ và cắt sát mép tên."""
    stripped = before.rstrip()
    for title in sorted(titles, key=len, reverse=True):
        if stripped.endswith(title) and (
            len(stripped) == len(title) or not stripped[-len(title) - 1].isalpha()
        ):
            return title
    return None


ADULT_TITLES_BEFORE_NAME = ("ngài", "ông", "bà", "thầy", "lão", "cụ", "tiên sinh", "phu nhân",
                            "chủ tịch", "giáo sư", "hiệu trưởng", "công tước", "nam tước", "bá tước")
CHILD_WORDS_NEAR_NAME = ("cậu bé", "thằng bé", "con bé", "đứa trẻ", "bé gái", "bé trai", "trẻ con",
                         "đứa bé", "cô bé")


def age_evidence_in_source(names: set[str]) -> dict[str, tuple[dict[str, int], int]]:
    """{tên: ({danh xưng người lớn: số lần}, số chữ trẻ con quanh tên)} - soát nhãn `age=child`.

    Vì sao cần: tuổi chọn HỌ GIỌNG, mà đáp án chuẩn không có trục tuổi, nên một nhãn tuổi sai không có
    thước nào bắt. Đo 20-09 trên cuốn 2: bốn tên từng mang `age=child`, hai trong đó sai hẳn - CHRISTOPHER
    ("ngài" x29, "thầy" x12, "chủ tịch" x6, không một chữ trẻ con nào) là chủ tịch Hiệp hội Nhạc sĩ đã về
    danh dự, và KAELYN ("phu nhân" x3) là vợ của một quản gia. Hai người bị đọc bằng giọng trẻ con 54 câu.
    """
    try:
        source = "\n".join(
            path.read_text(encoding="utf-8", errors="ignore")
            for path in sorted(SOURCE_DIR.glob("*.txt"))
        )
    except OSError:
        return {}
    wanted = {name.casefold(): name for name in names if len(name) >= 3}
    if not wanted:
        return {}
    adult: dict[str, collections.Counter] = {name: collections.Counter() for name in names}
    child: collections.Counter = collections.Counter()
    for match in _name_occurrences(source, wanted):
        name = wanted[match.group(0).casefold()]
        before = source[max(0, match.start() - 24): match.start()].casefold()
        title = _title_right_before(before, ADULT_TITLES_BEFORE_NAME)
        if title:
            adult[name][title] += 1
        window = source[max(0, match.start() - 40): match.end() + 40].casefold()
        child[name] += sum(window.count(word) for word in CHILD_WORDS_NEAR_NAME)
    return {name: (dict(adult[name]), child[name]) for name in names}


def honorific_verdict(evidence: dict) -> str | None:
    """Phái mà DANH XƯNG + TÊN chỉ ra, hoặc None khi nó không chỉ đủ rõ.

    Tín hiệu MẠNH duy nhất của công cụ này: "ngài Lauren", "bà Hathaway" nói trực tiếp về người ấy. Phép
    đếm chữ quanh tên thì không - xem `blind_spot_labels`.
    """
    titled = evidence.get("titled", {})
    male = sum(titled.get(word, 0) for word in MALE_HONORIFICS)
    female = sum(titled.get(word, 0) for word in FEMALE_HONORIFICS)
    for winner, mine, theirs in (("male", male, female), ("female", female, male)):
        if mine >= 3 and (theirs == 0 or mine / theirs >= EVIDENCE_MINIMUM_RATIO):
            return winner
    return None


def blind_spot_labels(rows: list[dict]) -> list[tuple[int, str, str, str, dict[str, int]]]:
    """Nhãn giới SAI mà giọng đi theo nhãn sai - điểm mù của mọi phép kiểm phía trên.

    `wrong_gender` chỉ thấy khi GIỌNG trái NHÃN. Nếu nhãn sai và giọng đi theo nhãn sai thì hai bên đồng ý
    và không gì kêu, trong khi người nghe vẫn nghe sai giới. Ca đắt nhất tìm được (20-09 14:4x): **CAMIL**,
    36 câu, sổ ghi `male`, nhưng nguồn gọi "Quý cô Camil" 29 lần và mô tả "Camil trong chiếc váy dài màu
    đen" - một phụ nữ bị đọc bằng giọng đàn ông suốt 36 câu.

    **Chỉ dùng DANH XƯNG + TÊN, cố ý bỏ phép đếm chữ quanh tên.** Bản đầu của hàm này dùng phép đếm (như
    `text_verdict`) và cho 21 ca, 17 trong đó là rác: nó gọi "MỤ PHÙ THỦY GIÀ" là nam, vì cửa sổ 45 ký tự
    quanh một cái tên đầy chữ chỉ NGƯỜI KHÁC trong cảnh - mà nhân vật chính của cuốn này là đàn ông và có
    mặt ở khắp nơi. Lọc lại chỉ bằng danh xưng thì còn 4 ca, 3 đã biết và 1 mới (CAMIL) - tất cả kiểm được
    bằng mắt trong một phút. Một bộ canh kêu 21 lần để đúng 4 lần thì người ta sẽ tắt nó.
    """
    by_name: dict[str, dict] = {}
    for row in rows:
        entry = by_name.setdefault(row["name"], {"lines": 0, "gender": row["gender"], "voices": set()})
        entry["lines"] += row["lines"]
        entry["voices"].add(row["voice"])
        if row["gender"] in ("male", "female"):
            entry["gender"] = row["gender"]
    named = {name: entry for name, entry in by_name.items()
             if entry["lines"] >= 3 and entry["gender"] in ("male", "female")}
    evidence = gender_evidence_in_source(set(named))
    out: list[tuple[int, str, str, str, dict[str, int]]] = []
    for name, entry in named.items():
        titled = evidence.get(name, {"titled": {}})["titled"]
        verdict = honorific_verdict({"titled": titled})
        if verdict is None or verdict == entry["gender"]:
            continue
        # Điểm mù đúng nghĩa: mọi giọng của người ấy đều thuận NHÃN (nên `wrong_gender` im lặng).
        if {preset_gender(voice) for voice in entry["voices"]} != {entry["gender"]}:
            continue
        out.append((entry["lines"], name, entry["gender"], verdict, dict(titled)))
    return sorted(out, reverse=True)


def age_verdict(adult_titles: dict[str, int], child_words: int) -> str:
    """Phán xử một nhãn `age=child` từ bằng chứng văn bản.

    DANH XƯNG + TÊN là tín hiệu mạnh, chữ trẻ con quanh tên là tín hiệu yếu - đúng bài học của trục giới
    tính. Chữ quanh tên nhiễm cả người khác trong cùng cảnh: KAELYN có hai chữ "trẻ con" bên cạnh, nhưng
    chúng nói về Lena - cô em họ mà bà ấy tới đón - còn "phu nhân Kaelyn" thì nói về chính bà.
    """
    adult = sum(adult_titles.values())
    if adult >= 3 or (adult >= 1 and child_words <= 2):
        return "NGHI SAI - bằng chứng NGƯỜI LỚN"
    if child_words >= 3:
        return "trẻ con: văn bản thuận"
    return "chưa rõ"


def age_drift(rows: list[dict]) -> dict[str, dict]:
    """{tên: {ages: {tuổi: {chương}}, voices: {giọng: {chương}}}} cho người bị đổi tuổi giữa các chương.

    Đổi tuổi là đổi cả **họ giọng**, nên nó nặng hơn đổi formant: người nghe mất nhân vật y như
    lớp tách danh tính do rơi dấu. Chỉ báo khi có ít nhất hai giá trị tuổi khác rỗng.
    """
    ages: dict[str, dict[str, set[str]]] = collections.defaultdict(lambda: collections.defaultdict(set))
    voices: dict[str, dict[str, set[str]]] = collections.defaultdict(lambda: collections.defaultdict(set))
    for r in rows:
        ages[r["name"]][r["age"]].add(r["chapter"])
        voices[r["name"]][r["voice"]].add(r["chapter"])
    return {
        name: {"ages": dict(buckets), "voices": dict(voices[name])}
        for name, buckets in ages.items()
        if len([age for age in buckets if age]) > 1
    }


def chapter_batches(book: Path = BOOK) -> dict[str, int]:
    """{chương: số lô} theo tên phiên bản trong manifest (`v0.2.0-lo03r` → 3)."""
    try:
        payload = json.loads((book / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    entries = payload if isinstance(payload, list) else payload.get("chapters", [])
    out: dict[str, int] = {}
    for item in entries:
        match = re.search(r"lo(\d+)", str(item.get("version") or ""))
        title = str(item.get("title") or "")
        if match and title:
            out[title] = int(match.group(1))
    return out


def voice_is_the_wrong_side(rows: list[dict]) -> list[dict]:
    """Bỏ khỏi danh sách đúc lại những dòng mà DANH XƯNG trong nguồn nói SỔ mới là bên sai.

    Đo 20-09 trên cuốn 2: 13 dòng sai phái, và danh xưng loại được 6 dòng mà giọng đang ĐÚNG (HATHAWAY
    "bà" x42 / "cô" x48 mà sổ ghi male; AMELTON "cô" x6; ARTHUR DOYLE "ngài/ông" x3 mà sổ ghi female) -
    đúc lại chúng là đổi giọng đúng thành sai, và tốn GPU để làm việc ấy.

    **Không phán xử được thì GIỮ LẠI, không bỏ.** Bản đầu của hàm này giữ lại chỉ khi văn bản THUẬN với
    `gender`, và `test_the_book_is_read_through_the_manifest_and_recast_names_the_batch` đỏ ngay: IVAN
    thuộc cuốn 1 nên không có trong nguồn cuốn 2, không có danh xưng nào, và cả danh sách đúc lại thành
    RỖNG. Một danh sách rỗng im lặng thì tệ hơn một danh sách dài: nó nói "không có việc gì" trong khi có.
    Và chỉ dùng DANH XƯNG, không dùng phép đếm chữ quanh tên - xem `blind_spot_labels` để biết vì sao.
    """
    evidence = gender_evidence_in_source({r["name"] for r in rows})
    return [
        r
        for r in rows
        if honorific_verdict(evidence.get(r["name"], {"titled": {}})) in (None, r["gender"])
    ]


def recast_arguments(rows: list[dict], batches: dict[str, int]) -> list[str]:
    """`B:NNN` cho các chương mà GIỌNG là bên sai. Không gộp chương của `age_drift`.

    Vì sao chỉ lấy nhóm sai phái: một người đổi tuổi mà giọng vẫn nhất quán thì không có gì để
    đúc lại, và một người đổi cả giọng đã nằm trong danh sách của `one_person_one_voice
    --across`. Hai công cụ không nên đề nghị cùng một chương hai lần.

    Và vì sao lọc thêm bằng văn bản: xem `voice_is_the_wrong_side`.
    """
    titles = sorted({r["chapter"] for r in voice_is_the_wrong_side(rows)})
    return [f"{batches[title]}:{title}" for title in titles if title in batches]


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("project", nargs="?", type=Path, default=None)
    parser.add_argument("--recast", action="store_true", help="chỉ in `B:NNN` cho boundary.sh")
    args = parser.parse_args(argv)

    rows = fold_names(read_rows(args.project) if args.project else shipped_rows())
    where = args.project.name if args.project else "cuốn sách đã ghép"
    if not rows:
        _say(f"không đọc được giọng nào từ {where}")
        return 2

    bad = wrong_gender(rows)
    if args.recast:
        _say(" ".join(recast_arguments(bad, chapter_batches())))
        return 0

    chapters = {r["chapter"] for r in rows}
    _say(f"{where}: {len(rows)} dòng (chương × nhân vật × giọng), {len(chapters)} chương,"
         f" {len({r['name'] for r in rows})} tên.")
    _say("")
    excused = [r for r in rows if r["age"] == "child" and preset_gender(r["voice"]) != r["gender"]]
    if not bad:
        _say("Không nhân vật nào bị đọc bằng giọng khác phái (ngoài luật giọng trẻ con).")
    else:
        _say(f"{len(bad)} dòng GIỌNG SAI PHÁI, {len({r['name'] for r in bad})} tên,"
             f" {sum(r['lines'] for r in bad)} câu thoại:")
        evidence = gender_evidence_in_source({r["name"] for r in bad})
        for r in sorted(bad, key=lambda r: -r["lines"]):
            _say(f"  chương {r['chapter']}  {r['name']:20s} {r['gender']:6s} age={r['age']:8s}"
                 f" đọc bằng {r['voice'].replace('preset_', ''):26s} {r['lines']:3d} câu"
                 f"   | {describe_evidence(evidence[r['name']]) if r['name'] in evidence else 'văn bản: -'}"
                 f" -> {'GIỌNG sai' if text_verdict(evidence.get(r['name'], {'male': 0, 'female': 0, 'titled': {}})) == r['gender'] else 'SỔ sai / chưa rõ'}")
        _say("")
        _say("  Cột cuối là BẰNG CHỨNG VĂN BẢN quanh cái tên. Nó nói bên nào sai, và hai bên sai khác nhau hẳn:")
        _say("    văn bản thuận với `gender` -> GIỌNG sai, phải ghim giọng rồi đúc lại;")
        _say("    văn bản ngược với `gender` -> SỔ ghi sai, giọng đang đúng, đừng đúc lại gì cả.")
        _say("Đúc lại: bash scripts/boundary.sh <lô> --recast auto $(python"
             " scripts/voice_matches_the_person.py --recast)")
        _say("  NHƯNG chỉ sau khi ghim được tuổi/giọng cho những cái tên ấy: `port_casting` mang"
             " `locked_voice_key` theo danh tính, nên đúc lại trước khi ghim chỉ tốn GPU.")
    if excused:
        # Nói rõ "dòng KHÁC": các dòng đã in ở trên KHÔNG được miễn (chúng có `age != child`). Bản đầu ghi
        # "luật giọng trẻ con giải thích N dòng" ngay dưới bảng, và đọc thế thì tưởng bảng trên đã được giải
        # thích - trong khi CHRISTOPHER có 8 dòng `age=child` được miễn VÀ 8 dòng `age=unknown` vẫn là lỗi.
        _say(f"  ({len(excused)} dòng KHÁC được miễn vì `age=child` - không phải các dòng trên:"
             f" {', '.join(sorted({r['name'] for r in excused}))})")

    blind = blind_spot_labels(rows)
    if blind:
        _say("")
        _say("ĐIỂM MÙ: nhãn giới sai mà GIỌNG ĐI THEO nhãn sai - không phép kiểm nào ở trên thấy được,")
        _say("vì nhãn và giọng đồng ý với nhau. Chỉ nhận ca có DANH XƯNG + TÊN đủ mạnh (xem hàm):")
        for lines, name, label, verdict, titles in blind:
            _say(f"  {name:18s} {lines:3d} câu | sổ={label:7s} danh xưng nói {verdict:7s} | {titles}")

    child_rows = [r for r in rows if r["age"] == "child"]
    if child_rows:
        _say("")
        _say("Nhãn `age=child` soát lại bằng VĂN BẢN (tuổi chọn họ giọng, và đáp án chuẩn KHÔNG có trục tuổi -")
        _say("nên đây là chỗ DUY NHẤT một nhãn tuổi sai bị bắt):")
        evidence = age_evidence_in_source({r["name"] for r in child_rows})
        by_name: dict[str, tuple[int, set[str]]] = {}
        for r in child_rows:
            lines, chapters = by_name.get(r["name"], (0, set()))
            by_name[r["name"]] = (lines + r["lines"], chapters | {r["chapter"]})
        for name, (lines, chapters) in sorted(by_name.items(), key=lambda kv: -kv[1][0]):
            adult, child = evidence.get(name, ({}, 0))
            verdict = age_verdict(adult, child)
            titles = ", ".join(f"{word} {count}" for word, count in adult.items()) or "-"
            _say(f"  {name:18s} {lines:3d} câu / {len(chapters)} chương | danh xưng người lớn: {titles}"
                 f" | chữ trẻ con: {child} -> {verdict}")

    drift = age_drift(rows)
    if drift:
        _say("")
        _say(f"{len(drift)} người ĐỔI TUỔI giữa các chương (tuổi chọn họ giọng, nên nó đắt):")
        for name, detail in sorted(drift.items(), key=lambda kv: -sum(len(c) for c in kv[1]["ages"].values())):
            ages = "  ".join(
                f"{age or '?'}={len(chs)}ch"
                for age, chs in sorted(detail["ages"].items(), key=lambda kv: -len(kv[1]))
            )
            changed = "GIỌNG CŨNG ĐỔI" if len(detail["voices"]) > 1 else "giọng vẫn một"
            _say(f"  {name:20s} {ages:34s} {changed}")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
