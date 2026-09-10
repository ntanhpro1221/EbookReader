r"""Va character_registry.py: mot ten rot dau van la ten ay - THU LANH la THU LANH.

CHUA AP luc viet - lo 3 dang chay. Ap o ranh gioi lo, truoc lo 4.

Do tren lo 2 va lo 3 (2026-09-10):

    lo02   THU LANH 111 lan nhac  |  THU LANH (khong dau hoi)  14
    lo03   THU LANH  32           |  THU LANH (khong dau hoi)  66   <- ban SAI thanh ban troi
    lo02   NGUOI TRA LOI 185      |  NGUOI TRA LOI (bo het dau) 37
    lo03   NGUOI TRA LOI  46      |  NGUOI TRA LOI (bo het dau) 160

Nguon van ban KHONG chua chuoi nao trong so nay (0 lan trong 62 chuong): day la nhan Ollama tu
dat cho vai "thu linh" / "nguoi tra loi", va model rot dau mot cach ngau nhien. `_known_summary`
dua ban co so lan nhieu hon vao prompt lan sau, nen ban sai tu cung co qua tung lo.

Hau qua that: cung mot nguoi hai giong (THU LANH ghim f100_p-07, THU LANH-khong-dau ghim
f090_p-04), va moi ban tach mot chiem mot cho trong kho 14 giong nam - lo 3 het kho som hon
du kien mot phan vi the.
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

# ---------------------------------------------------------------- import unicodedata
OLD = "import re\n"
NEW = "import re\nimport unicodedata\n"
assert OLD in s and "import unicodedata" not in s, "khong khop import"
s = s.replace(OLD, NEW, 1)

# ---------------------------------------------------------------- helper ngay tren canonical_key
OLD = '''def canonical_key(name: str) -> str:
    return normalize_name(name).upper()'''
NEW = '''def canonical_key(name: str) -> str:
    return normalize_name(name).upper()


def _stripped_and_marks(name: str) -> tuple[str, tuple[tuple[int, str], ...]]:
    """Tên bỏ hết dấu, và danh sách (vị trí, dấu) đã bỏ - để so hai cách viết với nhau.

    Chỉ so được hai tên khi phần chữ cái trần của chúng giống nhau; khi ấy các dấu là thứ duy
    nhất khác, và câu hỏi thành: dấu của tên này có phải **tập con** dấu của tên kia không.
    """
    decomposed = unicodedata.normalize("NFD", normalize_name(name))
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
    return redirected'''
assert OLD in s, "khong khop canonical_key"
s = s.replace(OLD, NEW, 1)

# ---------------------------------------------------------------- dung no trong pass chuan hoa
# Neo CHỈ vào khối chọn đại diện, không kéo tới dòng `aliases_by_target` bên dưới: bản vá họ-bịa
# chèn một pass ngay trước dòng ấy, và neo dài hơn sẽ trượt nếu bản kia áp trước. Bài học đo được
# ngày 2026-09-10 - thứ tự ngược đỏ ngay lần thử đầu, và assert dừng đúng chỗ, không ghi gì.
OLD = '''    for key, variants in variants_by_key.items():
        representatives[key] = min(
            variants,
            key=lambda candidate: (-variants[candidate], candidate.casefold(), candidate),
        )
'''
NEW = '''    for key, variants in variants_by_key.items():
        representatives[key] = min(
            variants,
            key=lambda candidate: (-variants[candidate], candidate.casefold(), candidate),
        )
    # Pass thứ hai, sau khi mỗi key đã có đại diện: hai key mà một là bản rơi dấu của cái kia
    # thì trỏ về cùng một đại diện. Làm ở đây để vòng viết lại bên dưới xử nó y như mọi alias
    # khác - không có đường riêng để quên.
    for loser_key, winner in merge_dropped_mark_variants(representatives, cleaned_counts).items():
        representatives[loser_key] = winner
'''
assert OLD in s, "khong khop pass chuan hoa"
s = s.replace(OLD, NEW, 1)

write_atomic(p, s)
print("da va", p)

TEST = '''"""Một tên rơi dấu vẫn là tên ấy: THU LÃNH là THỦ LÃNH, và giọng phải là một.

Đo trên lô 2 và lô 3 (2026-09-10): hai cặp như thế, và ở lô 3 bản rơi dấu đã thành bản trội —
THU LÃNH 66 lần nhắc so với THỦ LÃNH 32, NGUOI TRA LOI 160 so với NGƯỜI TRẢ LỜI 46. Nguồn văn
bản không chứa chuỗi nào trong số ấy: là nhãn Ollama tự đặt và rơi dấu ngẫu nhiên, rồi
`_known_summary` đưa bản nhiều lần hơn vào prompt kế tiếp nên cái sai tự củng cố. Mỗi bản tách
một chiếm một chỗ trong kho 14 giọng nam, và cùng một người đọc bằng hai giọng.
"""
from __future__ import annotations

from pathlib import Path

from ebook_reader.character_registry import (
    build_registry_and_cast,
    dropped_marks_variant_of,
)
from ebook_reader.config import build_settings

from tests.test_character_casting import _identity_db


def test_a_dropped_tone_mark_is_the_same_name() -> None:
    assert dropped_marks_variant_of("THU LÃNH", "THỦ LÃNH")
    assert dropped_marks_variant_of("NGUOI TRA LOI", "NGƯỜI TRẢ LỜI")
    assert dropped_marks_variant_of("Thu Lãnh", "THỦ LÃNH"), "hoa/thường không đổi kết luận"


def test_it_only_goes_one_way() -> None:
    """Bản đủ dấu không phải biến thể của bản thiếu dấu - hướng gộp cố định."""
    assert not dropped_marks_variant_of("THỦ LÃNH", "THU LÃNH")


def test_two_different_words_are_not_merged() -> None:
    """Tiếng Việt phân biệt từ bằng dấu: MÁ và MÀ cùng chữ trần nhưng là hai từ.

    Luật chỉ nhận **tập con** dấu, không nhận "bỏ dấu ra giống nhau"; đây là chỗ một luật rộng
    hơn sẽ gộp nhầm hai nhân vật thành một, tức lỗi ngược và tệ hơn.
    """
    assert not dropped_marks_variant_of("MÁ", "MÀ")
    assert not dropped_marks_variant_of("MÀ", "MÁ")
    assert not dropped_marks_variant_of("SAMAEL", "SAMAELE")


def test_the_two_spellings_cast_as_one_character_with_one_voice(tmp_path: Path) -> None:
    """Đúng ca lô 3, kể cả tỉ lệ: bản rơi dấu nhiều hơn bản đúng, và bản đúng vẫn phải thắng."""
    db = _identity_db(
        tmp_path,
        [("THU LÃNH", "male")] * 3 + [("THỦ LÃNH", "male")] * 2 + [("KANG", "male")],
    )

    build_registry_and_cast(db, build_settings(), lambda _message: None)

    rows = db.list_segments()
    assert {str(row["speaker"]) for row in rows} == {"THỦ LÃNH", "KANG"}, (
        "người thắng là bản ĐỦ DẤU dù ít lần hơn, vì số lần đã bị vòng phản hồi làm nhiễm"
    )
    leader = [row for row in rows if str(row["speaker"]) == "THỦ LÃNH"]
    assert len(leader) == 5
    assert len({int(row["canonical_character_id"]) for row in leader}) == 1
    assert len({int(row["voice_profile_id"]) for row in leader}) == 1
'''
q = root / "tests" / "test_dropped_marks_are_the_same_name.py"
write_atomic(q, TEST)
print("da tao", q)
