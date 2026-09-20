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
| HATHAWAY | 12 | male | nữ | "bà" x42, "cô" x48, không một "ngài/ông" | **SỔ sai** - giọng đúng |
| CHRISTOPHER | 8 | male | nữ | nam 86, "ngài" x29 | **GIỌNG sai** - và là ca rối nhất, xem dưới |
| AMELTON | 6 | male | nữ | "cô" x6, nữ 13 / nam 7 | **SỔ sai** - giọng đúng |
| ARTHUR DOYLE | 5 | female | nam | nam 13, nữ 0, "ngài/ông" | **SỔ sai** - giọng đúng |
| SALA | 2 | female | nam | nam 25, nữ 4 | **SỔ sai** - giọng đúng |
| MAG | 1 | female | nam | nam 10, nữ 0 | **SỔ sai** - giọng đúng |
| LAUREN | 2 | male | nữ | nam 95, "ngài" x15 | **GIỌNG sai** |
| DONA | 1 | male (lúc thu) | nữ | nam 15, nữ 3 | **GIỌNG sai** |

Tức trong 37 câu bị gắn cờ: **11 câu** là giọng sai thật (CHRISTOPHER 8, LAUREN 2, DONA 1) và **26 câu** là sổ ghi
sai với giọng đang ĐÚNG. Năm cái tên "sổ sai" đã ghim lại bằng `cli cast --character ... --gender ...` ngay giữa
lô 10 (dữ liệu, không phải mã; nhịp tim pipeline không hụt giây nào) nên nhãn nay thuận với giọng - và **không phải
đúc lại gì cả**. Nếu đọc báo cáo mà không đọc cột bằng chứng thì sẽ đúc lại 26 câu đang ĐÚNG thành sai; `--recast`
nay tự lọc bằng cột ấy (13 chương -> 5 chương).

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
    out: dict[str, str] = {}
    for name in names:
        title = name.title()
        windows = re.findall(rf"(?<![\wÀ-ỹ]).{{0,45}}{re.escape(title)}(?![\wÀ-ỹ]).{{0,45}}", source, re.IGNORECASE)
        male = female = 0
        for window in windows:
            low = window.casefold()
            male += sum(len(re.findall(rf"(?<![\wÀ-ỹ]){w}(?![\wÀ-ỹ])", low)) for w in MALE_WORDS_NEAR_NAME)
            female += sum(len(re.findall(rf"(?<![\wÀ-ỹ]){w}(?![\wÀ-ỹ])", low)) for w in FEMALE_WORDS_NEAR_NAME)
        titled = {
            word: len(re.findall(rf"(?<![\wÀ-ỹ]){word}\s+{re.escape(title)}(?![\wÀ-ỹ])", source, re.IGNORECASE))
            for word in HONORIFICS
        }
        out[name] = {"male": male, "female": female, "titled": {w: c for w, c in titled.items() if c}}
    return out


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
    """Chỉ những dòng mà VĂN BẢN thuận với `gender` - tức cái sai là GIỌNG, đúc lại mới có nghĩa.

    Đo 20-09 trên cuốn 2: 13 dòng sai phái, nhưng chỉ **2** dòng (LAUREN 328, DONA 189) là giọng sai. Mười một
    dòng còn lại là SỔ ghi sai với giọng đang ĐÚNG (HATHAWAY "bà" x42 / "cô" x48 mà sổ ghi male; AMELTON,
    ARTHUR DOYLE, SALA, MAG) - đúc lại chúng là đổi giọng đúng thành sai, và tốn GPU để làm việc ấy.
    Văn bản không chỉ rõ thì KHÔNG đúc lại: một lượt đúc lại đắt, còn im lặng thì không làm hỏng gì.
    """
    evidence = gender_evidence_in_source({r["name"] for r in rows})
    return [r for r in rows if text_verdict(evidence.get(r["name"], {"male": 0, "female": 0, "titled": {}}))
            == r["gender"]]


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
