r"""Va character_registry.py: "ALICE VIC. DRAKEN" (1 cau) la "ALICE" (25 cau) bi model them ho.

CHUA AP luc viet - lo 3 dang chay. Ap o ranh gioi lo, truoc lo 4.

Ban dau tuyen bo "ap thu tu nao cung duoc" va sai: ap ban nay TRUOC thi neo cua
patch_dropped_marks truot, vi neo ay keo tu khoi chon dai dien xuong tan dong
`aliases_by_target` - dung dong ban nay chen truoc. Sua neo ben kia cho hep lai; hai thu tu deu
xanh sau do. Ghi lai vi tuyen bo doc lap ma khong thu la mot tuyen bo, khong phai mot phep do.

Dem tren ba lo (2026-09-10), cung gioi, ten ngan la tien to nguyen tu cua ten dai:

    lo 1   0 cap
    lo 2   1 cap   ALICE (3 cau)  <  ALICE DRACEN (2)
    lo 3   3 cap   ALICE (25)     <  ALICE DRACEN (0)
                   ALICE (25)     <  ALICE VIC. DRAKEN (1)
                   SELNE (32)     <  SELNE VALKRYN (3)

Dang lon, va ALICE co BA cach viet voi hai ho khac nhau - model khong chi them ho, no bia ho.
Huong gop NGUOC voi lop roi dau: ban ngan giu gan het cau, ban dai la nhan lac 0-3 cau. Moi nhan
lac chiem mot cho trong kho giong va co the va cham: ALICE VIC. DRAKEN da trung giong voi THALIA
o lo 3.
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
p = root / "ebook_reader" / "character_registry.py"
s = io.open(p, encoding="utf-8").read()

# ---------------------------------------------------------------- hang so + helper, tren _canonicalize
OLD = '''def _canonicalize_named_speakers('''
NEW = '''# Một nhãn dài là "tên ngắn + họ bịa" khi nó có tối đa ngần này câu...
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


def _canonicalize_named_speakers('''
assert OLD in s, "khong khop cho chen helper"
s = s.replace(OLD, NEW, 1)

# ---------------------------------------------------------------- pass gop, ngay truoc khi viet lai alias
OLD = '''    aliases_by_target: dict[str, set[str]] = defaultdict(set)
    rewritten_segments = 0'''
NEW = '''    # Nhãn "tên + họ bịa" trỏ về tên ngắn. Đặt ngay trước vòng viết lại để nó được xử như mọi
    # alias khác. Neo ở đây chứ không ở pass rơi dấu, để bản vá này và bản vá rơi dấu áp được
    # theo thứ tự nào cũng được - hai lớp lỗi độc lập thì hai bản vá phải độc lập.
    for loser_key, winner in merge_stray_surnames(representatives, cleaned_counts).items():
        representatives[loser_key] = winner

    aliases_by_target: dict[str, set[str]] = defaultdict(set)
    rewritten_segments = 0'''
assert OLD in s, "khong khop cho chen pass"
s = s.replace(OLD, NEW, 1)

write_atomic(p, s)
print("da va", p)

TEST = '''"""Một nhãn "tên + họ bịa" với một câu là chính nhân vật ấy, không phải người mới.

Đếm trên ba lô: ALICE (25 câu) còn có ALICE DRACEN (0) và ALICE VIC. DRAKEN (1) - hai cái họ
khác nhau cho cùng một người; SELNE (32) còn có SELNE VALKRYN (3). Mỗi nhãn lạc chiếm một chỗ
trong kho giọng và ALICE VIC. DRAKEN đã va chạm với THALIA ở lô 3.

Hai ngưỡng cùng lúc - dài ≤ 3 câu VÀ ngắn ≥ 10× - vì mỗi cái riêng lẻ đều gộp nhầm được, và bài
thứ ba ở đây là cái giữ JAKE / JAKE SMITH cha con không bị gộp.
"""
from __future__ import annotations

from pathlib import Path

from ebook_reader.character_registry import (
    STRAY_SURNAME_MAX_LINES,
    STRAY_SURNAME_MIN_RATIO,
    build_registry_and_cast,
)
from ebook_reader.config import build_settings

from tests.test_character_casting import _identity_db


def test_a_one_line_surname_label_folds_into_the_character(tmp_path: Path) -> None:
    db = _identity_db(
        tmp_path,
        [("ALICE", "female")] * 25 + [("ALICE VIC. DRAKEN", "female")] + [("THALIA", "female")],
    )

    build_registry_and_cast(db, build_settings(), lambda _message: None)

    rows = db.list_segments()
    assert {str(row["speaker"]) for row in rows} == {"ALICE", "THALIA"}
    alice = [row for row in rows if str(row["speaker"]) == "ALICE"]
    assert len(alice) == 26
    assert len({int(row["voice_profile_id"]) for row in alice}) == 1


def test_two_invented_surnames_both_fold_into_the_same_person(tmp_path: Path) -> None:
    """Lô 2 gọi là DRACEN, lô 3 gọi là DRAKEN. Cả hai về ALICE."""
    db = _identity_db(
        tmp_path,
        [("ALICE", "female")] * 30
        + [("ALICE DRACEN", "female")] * 2
        + [("ALICE VIC. DRAKEN", "female")],
    )

    build_registry_and_cast(db, build_settings(), lambda _message: None)

    assert {str(row["speaker"]) for row in db.list_segments()} == {"ALICE"}


def test_a_real_father_and_son_are_left_alone(tmp_path: Path) -> None:
    """JAKE 300 câu, JAKE SMITH 30 câu: tỉ lệ 10× lọt ngưỡng thứ hai, nhưng 30 > 3 nên ngưỡng
    thứ nhất giữ họ là hai người. Đây là bài quan trọng nhất trong file."""
    assert STRAY_SURNAME_MAX_LINES < 30 and 300 >= 30 * STRAY_SURNAME_MIN_RATIO
    db = _identity_db(
        tmp_path,
        [("JAKE", "male")] * 300 + [("JAKE SMITH", "male")] * 30,
    )

    build_registry_and_cast(db, build_settings(), lambda _message: None)

    assert {str(row["speaker"]) for row in db.list_segments()} == {"JAKE", "JAKE SMITH"}


def test_a_rare_short_name_does_not_swallow_a_long_one(tmp_path: Path) -> None:
    """Ngưỡng tỉ lệ: ALICE 5 câu không được nuốt ALICE VIC. DRAKEN 1 câu - 5 < 10×1."""
    db = _identity_db(
        tmp_path,
        [("ALICE", "female")] * 5 + [("ALICE VIC. DRAKEN", "female")],
    )

    build_registry_and_cast(db, build_settings(), lambda _message: None)

    assert {str(row["speaker"]) for row in db.list_segments()} == {"ALICE", "ALICE VIC. DRAKEN"}
'''
q = root / "tests" / "test_stray_surname_is_the_same_name.py"
write_atomic(q, TEST)
print("da tao", q)
