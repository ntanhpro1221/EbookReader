r"""Va character_registry.py: cach viet co trong SACH thang cach viet khong co.

CHUA AP luc viet - ranh gioi lo 3 dang chay. Ap o ranh gioi lo 4 -> 5, **cung luc** voi viec noi
`scripts/source_spellings.py` vao `port_casting`. Hai nua phai di cung nhau, va day la ly do:

Gop ten o thoi diem gieo doi ca cai pin. `SELNE VALKRYN` se duoc ghim duoi ten `SELENE`; roi
phan tich cua lo sau, neu registry KHONG mang luat nay, lai sinh ra `SELNE`, khong khop pin, va
nhan vat ay bi duc GIONG MOI. Nghia la cai nua thu nhat mot minh gay ra dung cai lo lam no
duoc viet ra de chua.

Do ngay 2026-09-10 tren lo 3:

    Selene   198 lan trong nguon      SELENE    7 cau thoai
    Selne      0 lan                  SELNE    32 cau thoai   <- ban SAI dang thang

Nhan vat that ten Selene. Ban sai thang vi no noi nhieu hon - dung vong phan hoi da ghi cho lop
roi dau (`_known_summary` dua ban nhieu lan hon vao prompt lo sau, cai sai tu cung co). Lop roi
dau co mot tin hieu noi tai de pha vong ay (ban nhieu dau hon thang). Lop sai MOT ky tu thi
khong - nhung no khong can, vi co mot quan toa tot hon so cau va no nam ngay tren dia: chinh
cuon sach.

Tren 30 nhan vat co ten cua lo 3, dung 4 ten khong xuat hien lay mot lan trong 92 chuong nguon:
SELNE (32 cau), SELNE VALKRYN (3), SAMAELE (1), NARRATOR (1, mot vai bi lot). Khong mot nhan vat
that nao co 0 lan.

Vi sao KHONG dung khoang cach sua mot minh: `SO BA` (2 cau) va `SO BAY` (7 cau) lech nhau mot ky
tu sau khi bo dau, va la HAI NGUOI THAT - ca hai co trong nguon, nen luat nay khong cham toi
chung. Mot luat "lech mot ky tu thi gop" se nhap hai nhan vat lam mot.

Ban trong `scripts/source_spellings.py` da vao cay va duoc dung o thoi diem gieo; ban nay la ban
chinh trong registry. Hai ban cua mot luat thi som muon lech nhau, nen
`tests/test_source_spellings_agree.py` giu chung khong lech - cung cach `test_name_marks_agree.py`
giu luat roi dau.
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

# ---------------------------------------------------------------- import Path
OLD = "from typing import Any, Callable\n"
NEW = "from pathlib import Path\nfrom typing import Any, Callable\n"
assert OLD in s and "from pathlib import Path" not in s, "khong khop import Path"
s = s.replace(OLD, NEW, 1)

# ---------------------------------------------------------------- helper, ngay tren _canonicalize
OLD = "def _canonicalize_named_speakers("
NEW = '''def _folded_source_text(db: ProjectDB) -> str:
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
    return fold_for_source_search("\\n".join(chunks))


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


def _canonicalize_named_speakers('''
assert OLD in s and "fold_to_source_spelling" not in s, "khong khop cho chen helper"
s = s.replace(OLD, NEW, 1)

# ---------------------------------------------------------------- pass gop, sau hai pass kia
OLD = """    aliases_by_target: dict[str, set[str]] = defaultdict(set)
    rewritten_segments = 0"""
NEW = '''    # Pass cuối trong ba pass nhận dạng, và cố ý cuối: hai pass trên có thể đã trỏ một key về
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
    rewritten_segments = 0'''
assert OLD in s, "khong khop cho chen pass"
s = s.replace(OLD, NEW, 1)

write_atomic(p, s)
print("da va", p)

TEST = '''"""Cuốn sách quyết cách viết nào là thật - bản chính của luật, trong registry.

Nguồn ghi `Selene` 198 lần và `Selne` 0 lần, còn `SELNE` nói 32 câu và `SELENE` chỉ 7. Số câu là
đúng thứ vòng phản hồi làm nhiễm, nên nó không được quyết; cuốn sách thì quyết được.
"""
from __future__ import annotations

from pathlib import Path

from ebook_reader.character_registry import (
    build_registry_and_cast,
    fold_to_source_spelling,
    source_occurrences,
)
from ebook_reader.config import build_settings

from tests.test_character_casting import _identity_db


def test_the_spelling_in_the_book_wins_however_little_it_speaks() -> None:
    book = "selene buoc vao. " * 20
    folded = fold_to_source_spelling(
        ["SELNE", "SELENE", "SELNE VALKRYN"], book, {"SELNE": 32, "SELENE": 7}
    )

    assert folded == {"SELNE": "SELENE", "SELNE VALKRYN": "SELENE"}


def test_two_real_characters_one_letter_apart_are_left_alone() -> None:
    """`SỐ BA` và `SỐ BẢY` lệch một ký tự sau khi bỏ dấu và là hai người. Cả hai có trong nguồn,
    nên luật im lặng. Đây là bài quan trọng nhất trong file: một luật "lệch một ký tự thì gộp"
    sẽ nhập hai nhân vật thật làm một, tức lỗi ngược và tệ hơn."""
    book = "so ba noi. so bay dap. " * 5

    assert source_occurrences("SỐ BA", book) > 0
    assert source_occurrences("SỐ BẢY", book) > 0
    assert fold_to_source_spelling(["SỐ BA", "SỐ BẢY"], book, {"SỐ BA": 2, "SỐ BẢY": 7}) == {}


def test_no_source_means_no_folding() -> None:
    """Không đọc được nguồn thì luật phải TẮT, không được đoán."""
    assert fold_to_source_spelling(["SELNE", "SELENE"], "", {"SELNE": 32}) == {}


def test_a_name_with_no_close_neighbour_stays() -> None:
    assert fold_to_source_spelling(["NARRATOR", "SELENE"], "selene buoc vao.", {}) == {}


def test_the_two_spellings_cast_as_one_character(tmp_path: Path) -> None:
    """Đúng ca lô 3: bản sai nói nhiều hơn bản đúng, và bản đúng vẫn phải thắng vì sách viết nó."""
    # `_identity_db` trỏ `input_path` vào `tmp_path/"one.txt"` và không tạo file ấy; tạo nó ở
    # đây để luật có nguồn mà đọc. Không có file thì luật tự tắt, và bài này sẽ không kiểm gì.
    (tmp_path / "one.txt").write_text("Selene buoc vao. " * 30, encoding="utf-8")
    db = _identity_db(
        tmp_path,
        [("SELNE", "female")] * 6 + [("SELENE", "female")] * 2 + [("KANG", "male")],
    )

    build_registry_and_cast(db, build_settings(), lambda _message: None)

    rows = db.list_segments()
    assert {str(row["speaker"]) for row in rows} == {"SELENE", "KANG"}, (
        "người thắng là cách viết CÓ trong sách, dù ít câu hơn"
    )
    selene = [row for row in rows if str(row["speaker"]) == "SELENE"]
    assert len(selene) == 8
    assert len({int(row["voice_profile_id"]) for row in selene}) == 1
'''
q = root / "tests" / "test_the_book_decides_the_spelling.py"
write_atomic(q, TEST)
print("da tao", q)

AGREE = '''"""`scripts/source_spellings.py` và `character_registry` phải cho cùng câu trả lời.

Hai bản tồn tại vì lý do thời điểm, y như luật rơi dấu: script gieo phải gộp được ngay ở ranh
giới lô, còn registry chỉ đổi được khi có một ranh giới để áp bản vá. Hai bản của một luật thì
sớm muộn lệch nhau, và bài này là cái giữ chúng không lệch.
"""
from __future__ import annotations

import pytest

from scripts.source_spellings import fold_to_source_spelling as script_fold
from scripts.source_spellings import occurrences as script_occurrences

BOOK = "selene buoc vao. samael dap. so ba noi. so bay dap. " * 5

CASES = [
    (["SELNE", "SELENE"], {"SELNE": 32, "SELENE": 7}),
    (["SELNE VALKRYN", "SELENE"], {"SELNE VALKRYN": 3, "SELENE": 7}),
    (["SAMAELE", "SAMAEL"], {"SAMAELE": 1, "SAMAEL": 19}),
    (["SỐ BA", "SỐ BẢY"], {"SỐ BA": 2, "SỐ BẢY": 7}),
    (["NARRATOR", "SELENE"], {}),
    (["SELNE", "SELENE"], {}),
]


@pytest.mark.parametrize("names, counts", CASES)
def test_the_two_copies_agree(names: list[str], counts: dict[str, int]) -> None:
    registry = pytest.importorskip("ebook_reader.character_registry")
    if not hasattr(registry, "fold_to_source_spelling"):
        pytest.skip("registry chưa mang bản chính - patch_the_book_decides_the_spelling chưa áp")

    assert registry.fold_to_source_spelling(names, BOOK, counts) == script_fold(
        names, BOOK, counts
    )
    for name in names:
        assert registry.source_occurrences(name, BOOK) == script_occurrences(name, BOOK)
'''
r = root / "tests" / "test_source_spellings_agree.py"
write_atomic(r, AGREE)
print("da tao", r)
