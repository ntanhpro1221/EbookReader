r"""Va database.py + cli.py + character_registry.py + port_casting.py: nguoi nghe ghim TUOI duoc,
va mot thuoc tinh da ghim thang giong mang sang tu lo truoc.

CHUA AP luc viet (2026-09-12 01:30) - lo 5 dang chay, ranh gioi 5 -> 6 dang cho o buoc 0. Ban va
nay KHONG xep hang cho dem nay: ba ban va kia da chung minh, con day la mot thay doi o tang
CASTING - tang dat nhat cua du an. Xep o ranh gioi 6 -> 7, sau khi lo 6 cho thay ba ban va kia
chay dung.

Bang chung (do bang `scripts/voice_matches_the_person.py` tren sach 116 chuong):

    IVAN   male, age=unknown, 17 cau o chuong 062 doc bang `ngoc_linh_f107_p+02`
           - preset NU keo cao, thu du an danh cho tre con

Duong di cua loi: lo 3 chuong 072 goi anh ta la `child` MOT lan (moi `segments.age` cua anh ta:
`unknown`), casting cap giong tre con, roi `port_casting` mang `locked_voice_key` ay sang moi lo
sau. Thoai cua anh ta: "T-Toi ten la Ivan," / "cau da m-muon mot it t-tien cua bon toi..." - mot
thanh nien hay lap. Khong lenh nao sua duoc: `cast` chi ghim PHAI, ma TUOI moi chon HO GIONG.

Ba viec, va hai su that da doi thiet ke (doc code truoc khi viet):

1. **Cot rieng cho tuoi da ghim.** `locked_character_genders()` loc `WHERE locked=1 AND gender IN
   ('male','female')`, tuc cot `locked` la cua PHAI. Ghim tuoi qua co ay se lang le cho moi nhan
   vat duoc ghim tuoi mot cai phai "do nguoi quyet" va lam cong kiem mau thuan phai thoi bao ve
   ho. Nen: `locked_age TEXT NOT NULL DEFAULT ''`, dung khuon `locked_voice_key`.

2. **Mang thuoc tinh da ghim theo chuoi gieo.** `port_casting` mang nhan vat da biet bang
   `upsert_character(...)` va docstring noi ro "Deliberately NOT locked"; `read_known_characters`
   khong doc co `locked`. Nen loi hua cua `cast` ("nguoi quyet, outrank mo hinh VINH VIEN") hien
   chi dung trong MOT project. Ban va mang ca phai lan tuoi da ghim di, nhu
   `port_pronunciations` mang cach doc.

3. **Da ghim thang ported.** O `build_registry_and_cast`, cho moi nhan vat co ca thuoc tinh da
   ghim lan `locked_voice_key` mang sang: neu preset cua giong ay khac PHAI cua nhan vat va nhan
   vat khong phai `child`, bo pin ay, ghi mot dong `runtime_events`, de allocator cap lai.

   MOT luat, va la luat duy nhat du lieu chung minh duoc: "preset phai dung phai, tru tre con".
   Luat "giong tre con cho nguoi lon" khong tra duoc tu `voice_key` (EVERAN va mot phu nu truong
   thanh deu dung preset nu; cai lam nen giong tre con la viec CHON preset nu cho mot dua tre
   trai). Bia them luat thu hai o day se la doan, va doan chinh la thu da tao ra ca lop loi nay.
"""
import io
import os
import sys
import tempfile
from pathlib import Path


def write_atomic(path: Path, text: str) -> None:
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    os.close(fd)
    io.open(tmp, "w", encoding="utf-8").write(text)
    os.replace(tmp, path)


root = Path(sys.argv[1])

# ============================================================ database.py
p = root / "ebook_reader" / "database.py"
s = io.open(p, encoding="utf-8").read()

# ---- 1a. schema cua project moi
OLD = """    locked_voice_key TEXT NOT NULL DEFAULT '',
    created_at REAL NOT NULL,
"""
NEW = """    locked_voice_key TEXT NOT NULL DEFAULT '',
    -- Tuổi người nghe đã ghim, rỗng nghĩa là chưa ai nói gì. Cột RIÊNG, không dùng `locked`:
    -- `locked` là của phái (`locked_character_genders` lọc theo nó), nên ghim tuổi qua đó sẽ
    -- cho nhân vật một cái phái "do người quyết" mà chưa ai quyết.
    locked_age TEXT NOT NULL DEFAULT '',
    created_at REAL NOT NULL,
"""
assert s.count(OLD) == 1, "khong khop schema characters"
s = s.replace(OLD, NEW, 1)

# ---- 1b. project cu
OLD = '''        if "locked_voice_key" not in character_columns:
            conn.execute(
                "ALTER TABLE characters ADD COLUMN locked_voice_key TEXT NOT NULL DEFAULT ''"
            )
'''
NEW = '''        if "locked_voice_key" not in character_columns:
            conn.execute(
                "ALTER TABLE characters ADD COLUMN locked_voice_key TEXT NOT NULL DEFAULT ''"
            )
        if "locked_age" not in character_columns:
            conn.execute(
                "ALTER TABLE characters ADD COLUMN locked_age TEXT NOT NULL DEFAULT ''"
            )
'''
assert s.count(OLD) == 1, "khong khop migration"
s = s.replace(OLD, NEW, 1)

# ---- 1c. hang so + hai method, ngay tren locked_character_voices
OLD = '''    def locked_character_voices(self) -> dict[str, str]:
        """Every voice pinned to a character, keyed the way casting keys characters.
'''
NEW = '''    def lock_character_age(self, canonical_name: str, age: str) -> None:
        """Ghi câu trả lời của người nghe về tuổi một nhân vật, và thôi hỏi nữa.

        `cast --gender` tồn tại vì mô hình đoán sai phái. Nó đoán sai TUỔI theo cùng một kiểu,
        và tuổi đắt hơn: tuổi chọn **họ giọng** (trẻ con được đọc bằng preset nữ kéo cao, vì
        preset nam dừng cách ống âm một đứa trẻ 0,8 cm - `voice_catalog.AGE_TARGET_PITCH_HZ`).
        Đo 2026-09-12: IVAN bị gọi là `child` một lần ở lô 3 và đọc bằng giọng con gái 17 câu
        ở chương 062, trong khi mọi `segments.age` của anh ta là `unknown` và thoại của anh ta
        là của một thanh niên hay lắp. Không lệnh nào sửa được điều đó cho tới bản vá này.

        `unknown` **không** ghim được: ghim một cái không-biết thì họ giọng vẫn không xác định,
        và một cột nói "người đã quyết" mà nội dung là "không biết" sẽ làm mọi người đọc sau
        hiểu sai. Muốn gỡ ghim thì xoá cột, chưa có lệnh, và chưa có ai cần.
        """
        normalized = str(age).strip().casefold()
        if normalized not in LOCKABLE_AGES:
            raise ValueError(f"age must be one of {sorted(LOCKABLE_AGES)}")
        key = _character_key(canonical_name)
        if not key:
            raise ValueError("canonical_name must not be empty")
        now = time.time()
        with self.transaction() as conn:
            # Ghi cả `age` lẫn `locked_age`: `age` là thứ mọi đường đọc sẵn, `locked_age` là thứ
            # nói rằng người đã quyết - và chỉ nó mới đi theo chuỗi gieo.
            updated = conn.execute(
                "UPDATE characters SET age=?, locked_age=?, updated_at=? WHERE canonical_name=?",
                (normalized, normalized, now, key),
            ).rowcount
            if not updated:
                conn.execute(
                    """
                    INSERT INTO characters
                        (canonical_name, display_name, age, locked_age, created_at, updated_at)
                    VALUES (?,?,?,?,?,?)
                    """,
                    (key, canonical_name.strip(), normalized, normalized, now, now),
                )

    def locked_character_ages(self) -> dict[str, str]:
        """Mọi tuổi người nghe đã ghim, khoá theo đúng cách casting khoá nhân vật."""
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT canonical_name, locked_age FROM characters WHERE locked_age <> ''"
            ).fetchall()
        return {_character_key(str(row["canonical_name"])): str(row["locked_age"]) for row in rows}

    def locked_character_voices(self) -> dict[str, str]:
        """Every voice pinned to a character, keyed the way casting keys characters.
'''
assert s.count(OLD) == 1, "khong khop cho chen method tuoi"
s = s.replace(OLD, NEW, 1)

OLD = "def _character_key(name: str) -> str:\n"
NEW = '''# Tuổi ghim được. `unknown` cố ý không có: xem `lock_character_age`. Danh sách này là tập con
# của `analysis.ALLOWED_AGES`; không import để `database` không phụ thuộc `analysis`, và bài thử
# `test_a_pinned_person_outranks_a_ported_voice` giữ hai bên không trôi khỏi nhau.
LOCKABLE_AGES = frozenset({"child", "teen", "young", "adult", "elderly"})


def _character_key(name: str) -> str:
'''
assert s.count(OLD) == 1, "khong khop cho chen LOCKABLE_AGES"
s = s.replace(OLD, NEW, 1)

write_atomic(p, s)
print("da va", p)

# ============================================================ cli.py
p = root / "ebook_reader" / "cli.py"
s = io.open(p, encoding="utf-8").read()

OLD = '''    paths = _existing_project_paths(args.project_root)
    character = str(args.character).strip()
    gender = str(args.gender).strip().casefold()
    if not character:
        return CommandResult(data={}, exit_code=EXIT_USAGE, error="--character must not be empty")
    if gender not in {"male", "female"}:
        return CommandResult(
            data={}, exit_code=EXIT_USAGE, error="--gender must be male or female"
        )
    database = ProjectDB(paths.db)
    database.lock_character_gender(character, gender)
    stored = database.locked_character_genders().get(character.strip().upper())
    if stored != gender:
        # Reporting a write that did not happen is worse than failing.
        return CommandResult(
            data={"character": character, "requested": gender, "stored": stored},
            exit_code=EXIT_VALIDATION_FAILED,
            error="Không ghi được giới tính đã ghim",
        )
    return CommandResult(
        data={"character": character, "gender": gender, "locked": True},
        exit_code=EXIT_OK,
    )'''
NEW = '''    paths = _existing_project_paths(args.project_root)
    character = str(args.character).strip()
    gender = str(getattr(args, "gender", "") or "").strip().casefold()
    age = str(getattr(args, "age", "") or "").strip().casefold()
    if not character:
        return CommandResult(data={}, exit_code=EXIT_USAGE, error="--character must not be empty")
    if not gender and not age:
        return CommandResult(
            data={}, exit_code=EXIT_USAGE, error="cần --gender hoặc --age (hoặc cả hai)"
        )
    if gender and gender not in {"male", "female"}:
        return CommandResult(
            data={}, exit_code=EXIT_USAGE, error="--gender must be male or female"
        )
    if age and age not in LOCKABLE_AGES:
        return CommandResult(
            data={}, exit_code=EXIT_USAGE, error=f"--age phải là một trong {sorted(LOCKABLE_AGES)}"
        )
    database = ProjectDB(paths.db)
    data: dict[str, Any] = {"character": character, "locked": True}
    if gender:
        database.lock_character_gender(character, gender)
        stored = database.locked_character_genders().get(_character_key(character))
        if stored != gender:
            # Reporting a write that did not happen is worse than failing.
            return CommandResult(
                data={"character": character, "requested": gender, "stored": stored},
                exit_code=EXIT_VALIDATION_FAILED,
                error="Không ghi được giới tính đã ghim",
            )
        data["gender"] = gender
    if age:
        database.lock_character_age(character, age)
        stored_age = database.locked_character_ages().get(_character_key(character))
        if stored_age != age:
            return CommandResult(
                data={"character": character, "requested": age, "stored": stored_age},
                exit_code=EXIT_VALIDATION_FAILED,
                error="Không ghi được tuổi đã ghim",
            )
        data["age"] = age
    return CommandResult(data=data, exit_code=EXIT_OK)'''
assert s.count(OLD) == 1, "khong khop than _command_cast"
s = s.replace(OLD, NEW, 1)

OLD = '''    This is `pronounce` for casting: locked, so nothing downstream asks again, and readable
    before casting has ever run so the answer can be given ahead of the failure rather than
    only after it.
    """'''
NEW = '''    This is `pronounce` for casting: locked, so nothing downstream asks again, and readable
    before casting has ever run so the answer can be given ahead of the failure rather than
    only after it.

    `--age` joined it for the same reason, one class of error later: the model called IVAN a
    child once in batch 3 and `port_casting` carried the resulting girl's voice into every
    batch after, 17 lines of it in chapter 062 alone. Age is the more expensive guess of the
    two, because it picks the voice **family** rather than a variant within one. Either flag
    may be given alone; both write a pin that travels along the seed chain.
    """'''
assert s.count(OLD) == 1, "khong khop docstring _command_cast"
s = s.replace(OLD, NEW, 1)

OLD = '''    cast = subparsers.add_parser(
        "cast",
        help="Pin a character's gender, as a listener decision rather than a model guess",
    )
    cast.add_argument("project_root", type=Path)
    cast.add_argument("--character", required=True, help="The character's name as cast")
    cast.add_argument("--gender", required=True, choices=("male", "female"))
'''
NEW = '''    cast = subparsers.add_parser(
        "cast",
        help="Pin a character's gender or age, as a listener decision rather than a model guess",
    )
    cast.add_argument("project_root", type=Path)
    cast.add_argument("--character", required=True, help="The character's name as cast")
    cast.add_argument("--gender", choices=("male", "female"))
    cast.add_argument(
        "--age",
        choices=tuple(sorted(LOCKABLE_AGES)),
        help="Tuổi, thứ chọn họ giọng (trẻ con đọc bằng preset nữ kéo cao)",
    )
'''
assert s.count(OLD) == 1, "khong khop parser cast"
s = s.replace(OLD, NEW, 1)

# `_character_key` là "the one way a character name becomes a key" theo chính docstring của
# nó (`database.py:2217`): `strip().upper()` của bản cũ đồng ý với nó cho "Noah" và KHÔNG
# đồng ý cho "Lê  Văn  A" - người nghe ghim được, được bảo là đã ghi, rồi lượt chạy bỏ qua
# trong im lặng. Một tên riêng thì phải dùng đúng một phép khoá, nên cli vay chính nó.
OLD = "from .database import (\n"
NEW = "from .database import (\n    LOCKABLE_AGES,\n    _character_key,\n"
assert s.count(OLD) >= 1, "khong khop import database trong cli"
s = s.replace(OLD, NEW, 1)

write_atomic(p, s)
print("da va", p)

# ============================================================ character_registry.py
p = root / "ebook_reader" / "character_registry.py"
s = io.open(p, encoding="utf-8").read()

OLD = '''    locked_genders = db.locked_character_genders()
    locked_voices = db.locked_character_voices()
'''
NEW = '''    locked_genders = db.locked_character_genders()
    locked_ages = db.locked_character_ages()
    locked_voices = db.locked_character_voices()
    locked_voices = _drop_pins_that_contradict_a_person(
        db, locked_voices, locked_genders, locked_ages, log
    )
'''
assert s.count(OLD) == 1, "khong khop cho doc locked_ages"
s = s.replace(OLD, NEW, 1)

OLD = "def build_registry_and_cast(\n"
NEW = '''def _drop_pins_that_contradict_a_person(
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
'''
assert s.count(OLD) == 1, "khong khop cho chen _drop_pins"
s = s.replace(OLD, NEW, 1)

OLD = "def _preset_by_name("
NEW = '''def preset_gender_of_voice_key(voice_key: str) -> str | None:
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


def _preset_by_name('''
assert s.count(OLD) == 1, "khong khop cho chen preset_gender_of_voice_key"
s = s.replace(OLD, NEW, 1)

if "import unicodedata" not in s.split("def ")[0]:
    OLD = "from collections import defaultdict"
    NEW = "import unicodedata\nfrom collections import defaultdict"
    assert s.count(OLD) == 1, "khong khop import unicodedata"
    s = s.replace(OLD, NEW, 1)

if "VIENEU_PRESETS" not in s.split("def ")[0]:
    OLD = "    child_voice_preference,\n"
    NEW = "    VIENEU_PRESETS,\n    child_voice_preference,\n"
    assert s.count(OLD) == 1, "khong khop import VIENEU_PRESETS"
    s = s.replace(OLD, NEW, 1)

write_atomic(p, s)
print("da va", p)

# ============================================================ scripts/port_casting.py
p = root / "scripts" / "port_casting.py"
s = io.open(p, encoding="utf-8").read()

OLD = '''            SELECT canonical_name, display_name, gender, age, personality,'''
NEW = '''            SELECT canonical_name, display_name, gender, age, personality, locked, locked_age,'''
assert s.count(OLD) == 1, "khong khop SELECT known characters"
s = s.replace(OLD, NEW, 1)

OLD = '''        database.upsert_character(
            canonical_name=str(character["canonical_name"]),
            display_name=str(character["display_name"] or character["canonical_name"]),
            gender=str(character["gender"]),
            age=str(character["age"] or "unknown"),
            personality=str(character["personality"] or ""),
            mentions=int(character["mention_count"] or 0),
            importance=str(character["importance"] or "minor"),
            confidence=float(character["confidence"] or 0.5),
        )'''
NEW = '''        database.upsert_character(
            canonical_name=str(character["canonical_name"]),
            display_name=str(character["display_name"] or character["canonical_name"]),
            gender=str(character["gender"]),
            age=str(character["age"] or "unknown"),
            personality=str(character["personality"] or ""),
            mentions=int(character["mention_count"] or 0),
            importance=str(character["importance"] or "minor"),
            confidence=float(character["confidence"] or 0.5),
        )
        # Thuộc tính NGƯỜI đã ghim thì đi theo chuỗi gieo, khác với thứ máy vừa học ở trên.
        # `cast` hứa trong docstring của nó rằng câu trả lời của người nghe outrank mô hình
        # **vĩnh viễn**; trước bản vá này lời hứa ấy chỉ đúng trong MỘT project, vì `port` mang
        # nhân vật sang "deliberately NOT locked" và lô sau phân tích lại rồi đổi ý.
        try:
            if int(character["locked"] or 0) and str(character["gender"]) in ("male", "female"):
                database.lock_character_gender(
                    str(character["canonical_name"]), str(character["gender"])
                )
            if str(character["locked_age"] or ""):
                database.lock_character_age(
                    str(character["canonical_name"]), str(character["locked_age"])
                )
        except (KeyError, IndexError, ValueError, AttributeError):
            # Project nguồn cũ hơn cột `locked_age`, hoặc một giá trị không ghim được: mang
            # được gì thì mang, đừng làm cả lượt port chết vì một hàng.
            pass'''
assert s.count(OLD) == 1, "khong khop upsert_character trong port"
s = s.replace(OLD, NEW, 1)

write_atomic(p, s)
print("da va", p)

# ============================================================ tests
TEST = '''"""Người nghe ghim được TUỔI, và thứ người đã ghim thắng giọng mang sang từ lô trước.

Ca thật: IVAN bị lô 3 gọi là `child` một lần (mọi `segments.age` của anh ta là `unknown`), được
cấp giọng nữ kéo cao, và `port_casting` mang giọng ấy sang mọi lô sau - 17 câu ở chương 062. Thoại
của anh ta là của một thanh niên hay lắp. Trước bản vá này không lệnh nào sửa được: `cast` chỉ
ghim phái, mà tuổi mới chọn họ giọng.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from ebook_reader.analysis import ALLOWED_AGES
from ebook_reader.character_registry import (
    _drop_pins_that_contradict_a_person,
    preset_gender_of_voice_key,
)
from ebook_reader.database import LOCKABLE_AGES, ProjectDB


class _Events:
    def __init__(self) -> None:
        self.said: list[str] = []
        self.events: list[tuple] = []

    def event(self, level, code, message, details=None) -> None:  # noqa: ANN001
        self.events.append((level, code, message, details))

    def log(self, message: str) -> None:
        self.said.append(message)


def test_the_lockable_ages_are_a_subset_of_what_analysis_allows() -> None:
    """Hai danh sách ở hai module không được trôi khỏi nhau; `unknown` cố ý không ghim được."""
    assert LOCKABLE_AGES <= ALLOWED_AGES
    assert "unknown" in ALLOWED_AGES and "unknown" not in LOCKABLE_AGES


def test_pinning_an_age_does_not_pin_a_gender(tmp_path: Path) -> None:
    """Cột `locked` là của phái. Ghim tuổi qua nó sẽ cho nhân vật một cái phái chưa ai quyết."""
    db = ProjectDB(tmp_path / "project.sqlite3")
    db.upsert_character(
        canonical_name="IVAN", display_name="Ivan", gender="male", age="child",
        personality="", mentions=22, importance="main", confidence=0.9,
    )

    db.lock_character_age("IVAN", "adult")

    assert db.locked_character_ages() == {"IVAN": "adult"}
    assert db.locked_character_genders() == {}, "chưa ai ghim phái của IVAN"
    assert str(db.list_characters()[0]["age"]) == "adult", "`age` cũng phải đổi, không chỉ cột ghim"


def test_an_age_outside_the_list_is_refused(tmp_path: Path) -> None:
    db = ProjectDB(tmp_path / "project.sqlite3")
    for bad in ("unknown", "grown-up", ""):
        with pytest.raises(ValueError):
            db.lock_character_age("IVAN", bad)


def test_pinning_before_analysis_creates_the_row(tmp_path: Path) -> None:
    """`port_casting` chạy giữa `create` và `run`, nên hàng có thể chưa tồn tại."""
    db = ProjectDB(tmp_path / "project.sqlite3")

    db.lock_character_age("  Ivan  ", "young")

    assert db.locked_character_ages() == {"IVAN": "young"}


def test_the_preset_behind_a_voice_key_is_read_longest_prefix_first() -> None:
    assert preset_gender_of_voice_key("preset_ngoc_linh_f107_p+02") == "female"
    assert preset_gender_of_voice_key("preset_thanh_binh_f100_p-04") == "male"
    assert preset_gender_of_voice_key("narrator") is None


def test_a_pinned_person_outranks_a_ported_voice(tmp_path: Path) -> None:
    """IVAN: người nghe ghim `male`/`adult`, giọng mang sang là preset nữ -> bỏ pin, cấp lại."""
    db = ProjectDB(tmp_path / "project.sqlite3")
    sink = _Events()
    db.event = sink.event  # type: ignore[method-assign]

    kept = _drop_pins_that_contradict_a_person(
        db,
        {"IVAN": "preset_ngoc_linh_f107_p+02", "WILL": "preset_thai_son_f100_p+00"},
        {"IVAN": "male", "WILL": "male"},
        {"IVAN": "adult"},
        sink.log,
    )

    assert kept == {"WILL": "preset_thai_son_f100_p+00"}
    assert [e[1] for e in sink.events] == ["CASTING_PIN_CONTRADICTS_A_PERSON"]
    assert "IVAN" in sink.said[0] and "cấp lại" in sink.said[0]


def test_a_child_keeps_a_cross_gender_voice(tmp_path: Path) -> None:
    """EVERAN là trẻ con thật: preset nữ kéo cao là ĐÚNG cách dự án đọc trẻ con, giữ pin."""
    db = ProjectDB(tmp_path / "project.sqlite3")
    sink = _Events()
    db.event = sink.event  # type: ignore[method-assign]

    kept = _drop_pins_that_contradict_a_person(
        db,
        {"EVERAN": "preset_ngoc_linh_f107_p+02"},
        {"EVERAN": "male"},
        {"EVERAN": "child"},
        sink.log,
    )

    assert kept == {"EVERAN": "preset_ngoc_linh_f107_p+02"}
    assert sink.events == []


def test_a_pin_nobody_ruled_on_is_left_alone(tmp_path: Path) -> None:
    """Không ai ghim phái thì không có gì để trái: giữ pin, đừng đoán."""
    db = ProjectDB(tmp_path / "project.sqlite3")
    sink = _Events()
    db.event = sink.event  # type: ignore[method-assign]

    kept = _drop_pins_that_contradict_a_person(
        db, {"IVAN": "preset_ngoc_linh_f107_p+02"}, {}, {"IVAN": "adult"}, sink.log
    )

    assert kept == {"IVAN": "preset_ngoc_linh_f107_p+02"}
    assert sink.events == []


def test_the_cast_command_takes_either_flag_or_both(tmp_path: Path) -> None:
    from types import SimpleNamespace

    from ebook_reader import cli

    root = tmp_path / "project"
    root.mkdir()
    ProjectDB(root / "project.sqlite3")
    (root / "book_settings.json").write_text("{}", encoding="utf-8")

    only_age = cli._command_cast(
        SimpleNamespace(project_root=root, character="IVAN", gender=None, age="adult", json=False)
    )
    only_gender = cli._command_cast(
        SimpleNamespace(project_root=root, character="WILL", gender="male", age=None, json=False)
    )
    neither = cli._command_cast(
        SimpleNamespace(project_root=root, character="NOBODY", gender=None, age=None, json=False)
    )
    both = cli._command_cast(
        SimpleNamespace(project_root=root, character="LILY", gender="female", age="teen", json=False)
    )

    assert only_age.ok and only_age.data["age"] == "adult" and "gender" not in only_age.data
    assert only_gender.ok and only_gender.data["gender"] == "male" and "age" not in only_gender.data
    assert not neither.ok and "--gender" in str(neither.error)
    assert both.ok and (both.data["gender"], both.data["age"]) == ("female", "teen")
    db = ProjectDB(root / "project.sqlite3")
    assert db.locked_character_ages() == {"IVAN": "adult", "LILY": "teen"}
    assert db.locked_character_genders() == {"WILL": "male", "LILY": "female"}


def test_a_project_older_than_the_column_is_migrated(tmp_path: Path) -> None:
    """Project của lô 1 không có cột `locked_age`; mở nó không được nổ."""
    path = tmp_path / "project.sqlite3"
    ProjectDB(path)
    with sqlite3.connect(str(path)) as conn:
        columns = {str(row[1]) for row in conn.execute("PRAGMA table_info(characters)")}
    assert "locked_age" in columns
'''
write_atomic(root / "tests" / "test_a_pinned_person_outranks_a_ported_voice.py", TEST)
print("da tao", root / "tests" / "test_a_pinned_person_outranks_a_ported_voice.py")
