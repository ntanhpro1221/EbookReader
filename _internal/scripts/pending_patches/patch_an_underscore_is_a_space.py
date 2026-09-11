r"""Va character_registry.py + scripts/name_marks.py: NGUOI_TRA_LOI la NGUOI TRA LOI - gach duoi la
khoang trang, va tu do la NGUOI TRA LOI roi dau, tuc NGƯỜI TRẢ LỜI.

CHUA AP luc viet - ranh gioi lo 4 dang chay lai. Ap ngay o buoc 1 cua no, TRUOC cac chuong duc
lai con lai va truoc lo 5.

Do 2026-09-11, 09:05, tren moi project:

    NGUOI_TRA_LOI   45 cau thoai   4 project   lo04v_097, lo04v_106, lo04r_104, lo01r_007

Ca bon project deu tao SAU khi ba ban va cua ranh gioi lo 4 ap luc 07:25 - truoc do khong co mot
ten nao mang gach duoi trong 100 project. Nghia la cai fold roi dau (dung) da doi hinh dang loi:
danh sach "da biet" gio dua `NGƯỜI TRẢ LỜI` du dau vao prompt, va Ollama thinh thoang tra ve ban
ASCII noi bang gach duoi. `normalize_name` gop khoang trang chu khong gop gach duoi, nen
`nguoi_tra_loi` va `nguoi tra loi` la hai key, `_stripped_and_marks` thay chu tran khac nhau
(co `_`), va khong pass nao gop no.

Hau qua da vao audio: chuong 104 duc lai co NGUOI_TRA_LOI noi 10 cau bang `doan_trang_f115`
(giong MOI, cap tuoi) va NGƯỜI TRẢ LỜI noi 1 cau bang giong ghim `f100` - mot nguoi hai giong
trong cung chuong, dung cai lo duc lai duoc thuc hien de xoa. `voice_pool_pressure` bao 0 va cham
vi no hoi cau nguoc; `one_person_one_voice` se bao, sau khi name_marks cung biet gach duoi.

Sua o dung hai cho va chi hai cho, khong dung `normalize_name` chung: `NPC_LOCAL::...` va
`ANONYMOUS_MALE` mang gach duoi theo thiet ke va `is_local_speaker` kiem tien to `NPC_LOCAL::`.
Mot helper `identity_key` (= normalize_name sau khi thay `_` bang khoang trang) dung cho viec
GOM key trong `_canonicalize_named_speakers` va cho `_stripped_and_marks`; moi cho khac giu
nguyen. Ban script `name_marks._normalize` doi cung cach, va bai `test_name_marks_agree` giu hai
ban khong lech.
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

# ============================================================ character_registry.py
p = root / "ebook_reader" / "character_registry.py"
s = io.open(p, encoding="utf-8").read()

OLD = '''def canonical_key(name: str) -> str:
    return normalize_name(name).upper()'''
NEW = '''def canonical_key(name: str) -> str:
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
    return normalize_name(name.replace("_", " "))'''
assert OLD in s, "khong khop canonical_key"
s = s.replace(OLD, NEW, 1)

OLD = '''    decomposed = unicodedata.normalize("NFD", normalize_name(name))'''
NEW = '''    decomposed = unicodedata.normalize("NFD", identity_key(name))'''
assert s.count(OLD) == 1, "khong khop _stripped_and_marks"
s = s.replace(OLD, NEW, 1)

OLD = '''        variants_by_key[normalize_name(cleaned)][cleaned] += count'''
NEW = '''        variants_by_key[identity_key(cleaned)][cleaned] += count'''
assert s.count(OLD) == 1, "khong khop gom key"
s = s.replace(OLD, NEW, 1)

# Vong viet lai: tra `representatives` bang cung mot key voi luc gom. Dong `normalized =
# normalize_name(cleaned)` co hai lan trong ham - lan dau (vong dem, kiem PRONOUNS) giu nguyen.
OLD = '''    for original, cleaned in cleaned_by_original.items():
        normalized = normalize_name(cleaned)'''
NEW = '''    for original, cleaned in cleaned_by_original.items():
        normalized = identity_key(cleaned)'''
assert s.count(OLD) == 1, "khong khop vong viet lai"
s = s.replace(OLD, NEW, 1)

OLD = '''            honorific_key = normalize_name(honorific_target)'''
NEW = '''            honorific_key = identity_key(honorific_target)'''
assert s.count(OLD) == 1, "khong khop honorific"
s = s.replace(OLD, NEW, 1)

write_atomic(p, s)
print("da va", p)

# ============================================================ scripts/name_marks.py
q = root / "scripts" / "name_marks.py"
t = io.open(q, encoding="utf-8").read()
OLD = '''def _normalize(name: str) -> str:
    return " ".join(str(name).strip().casefold().split())'''
NEW = '''def _normalize(name: str) -> str:
    # Gạch dưới là khoảng trắng - cùng luật với `character_registry.identity_key`; xem
    # `patch_an_underscore_is_a_space` cho số đo (NGUOI_TRA_LOI, 45 câu, 4 project).
    return " ".join(str(name).replace("_", " ").strip().casefold().split())'''
assert OLD in t, "khong khop name_marks._normalize"
t = t.replace(OLD, NEW, 1)
write_atomic(q, t)
print("da va", q)

# ============================================================ tests
a = root / "tests" / "test_name_marks_agree.py"
u = io.open(a, encoding="utf-8").read()
OLD = '''    ("SAMAEL", "SAMAEL", False),
]'''
NEW = '''    ("SAMAEL", "SAMAEL", False),
    # Gạch dưới là khoảng trắng: bản ASCII nối gạch của một tên đủ dấu là bản rơi dấu của nó.
    ("NGUOI_TRA_LOI", "NGƯỜI TRẢ LỜI", True),
    ("NGƯỜI_TRẢ_LỜI", "NGƯỜI TRẢ LỜI", False),
]'''
assert OLD in u, "khong khop PAIRS"
u = u.replace(OLD, NEW, 1)
write_atomic(a, u)
print("da them 2 cap vao", a)

TEST = '''"""Một tên nối bằng gạch dưới là tên ấy viết bằng khoảng trắng: NGUOI_TRA_LOI là NGƯỜI TRẢ LỜI.

Đo 2026-09-11: 45 câu trong bốn project, tất cả tạo sau khi prompt "đã biết" bắt đầu mang tên
đủ dấu. Chương 104 đúc lại có người ấy nói 10 câu bằng một giọng mới và 1 câu bằng giọng ghim -
một người hai giọng trong chính chương được đúc lại để xoá lỗi ấy.
"""
from __future__ import annotations

from pathlib import Path

from ebook_reader.character_registry import (
    build_registry_and_cast,
    canonical_key,
    dropped_marks_variant_of,
    identity_key,
)
from ebook_reader.config import build_settings

from tests.test_character_casting import _identity_db


def test_an_underscore_reads_as_a_space_for_identity_only() -> None:
    assert identity_key("NGUOI_TRA_LOI") == identity_key("NGUOI TRA LOI") == "nguoi tra loi"
    assert dropped_marks_variant_of("NGUOI_TRA_LOI", "NGƯỜI TRẢ LỜI")
    # `canonical_key` KHÔNG đổi: NPC và các key giữ chỗ/holders vẫn mang gạch dưới như cũ.
    assert canonical_key("NPC_LOCAL::C1::R2::LÍNH GÁC") == "NPC_LOCAL::C1::R2::LÍNH GÁC"


def test_the_underscore_spelling_casts_as_the_same_person(tmp_path: Path) -> None:
    """Đúng tỉ lệ chương 104: bản gạch dưới nói nhiều hơn, bản đủ dấu vẫn thắng và giọng là một."""
    db = _identity_db(
        tmp_path,
        [("NGUOI_TRA_LOI", "female")] * 10 + [("NGƯỜI TRẢ LỜI", "female")] * 1 + [("KANG", "male")],
    )

    build_registry_and_cast(db, build_settings(), lambda _message: None)

    rows = db.list_segments()
    assert {str(row["speaker"]) for row in rows} == {"NGƯỜI TRẢ LỜI", "KANG"}
    answerer = [row for row in rows if str(row["speaker"]) == "NGƯỜI TRẢ LỜI"]
    assert len(answerer) == 11
    assert len({int(row["canonical_character_id"]) for row in answerer}) == 1
    assert len({int(row["voice_profile_id"]) for row in answerer}) == 1


def test_local_npcs_keep_their_underscored_identity(tmp_path: Path) -> None:
    """Gạch dưới trong `NPC_LOCAL::` là thiết kế, không phải lỗi chính tả - không được gộp."""
    db = _identity_db(
        tmp_path,
        [("NPC_LOCAL::C00001::RAAAA::LÍNH GÁC", "male")] * 2 + [("KANG", "male")] * 3,
    )

    build_registry_and_cast(db, build_settings(), lambda _message: None)

    assert any(str(row["speaker"]).startswith("NPC_LOCAL::") for row in db.list_segments())
'''
write_atomic(root / "tests" / "test_an_underscore_is_a_space.py", TEST)
print("da tao", root / "tests" / "test_an_underscore_is_a_space.py")
