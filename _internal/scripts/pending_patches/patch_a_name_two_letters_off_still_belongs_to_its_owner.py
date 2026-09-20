"""Vá character_registry.py: nhãn vắng mặt trong sách mà lệch HAI ký tự vẫn được gom, nếu đích DUY NHẤT.

Chạy: python patch_a_name_two_letters_off_still_belongs_to_its_owner.py <root>

## Vì sao (20-09, 10:0x)

`fold_to_source_spelling` đã trỏ "tên không có trong sách" về "tên có trong sách", nhưng chỉ khi lệch ĐÚNG MỘT ký tự.
Model viết sai hai ký tự thì cái tên ấy sống sót thành một NHÂN VẬT RIÊNG, có giọng riêng, và sổ nhân vật mang nó qua
mọi lô sau. Đo trên lô 8, 9, 10 (187 nhãn người nói, 18 vắng mặt hẳn trong cả cuốn sách, luật cũ gom được 5):

| nhãn | câu | đích lệch 2 ký tự | luật cũ |
|---|---|---|---|
| `JOCLEYN` | 2 | `Jocelyn` (duy nhất) | thành nhân vật mới |
| `ARTELI` | 1 | `ARTIL` (duy nhất; `ARTIL`/`Artil` chỉ khác hoa thường) | thành nhân vật mới |

`ARTEL` (lệch 1) đã gom về `ARTIL` từ trước, nên một mình `ARTELI` đứng lại là vô nghĩa: cùng một người, hai lần viết
sai, một lần được sửa. Nguồn có "Artil" 88 lần, "Artel" 0, "Arteli" 0.

Mười ba nhãn vắng mặt còn lại KHÔNG có đích nào ở khoảng cách 2 (`PLANTAGENET_ULRICH`, `GRAND ARCANIEST`, `PROFESSOR`,
`BIG CHIEF`, `EMMA`, `HENSION`...), nên nới ngưỡng không kéo theo gì khác: đúng 2 nhãn đổi, cả hai đã kiểm bằng nguồn.

Vì sao nới an toàn: điều kiện KHÔNG đổi là *nhãn thua vắng mặt hẳn trong cả cuốn sách* - một cái tên tác giả chưa từng
viết thì không phải nhân vật, nên đây không phải chuyện "gộp hai nhân vật thật". Rủi ro duy nhất là gom về SAI người,
nên thêm hai chốt: đích phải **duy nhất** (mọi ứng viên cách 2 phải cùng một cách viết sau khi bỏ dấu và hạ chữ) và
nhãn phải dài **>= 5 ký tự** (hai ký tự trên năm là đã quá nhiều để gọi là viết sai). Lệch 1 vẫn được ưu tiên trước;
chỉ khi không có ứng viên lệch 1 mới xét lệch 2.
"""
import io
import sys
from pathlib import Path

root = Path(sys.argv[1])


def patch(path: Path, old: str, new: str) -> None:
    source = io.open(path, encoding="utf-8").read()
    assert source.count(old) == 1, f"khong khop mot lan duy nhat trong {path.name}: {old.splitlines()[0]!r}"
    io.open(path, "w", encoding="utf-8").write(source.replace(old, new, 1))
    print(f"da va {path}")


patch(
    root / "ebook_reader" / "character_registry.py",
    '''def fold_to_source_spelling(''',
    '''# Nhãn vắng mặt trong sách mà lệch HAI ký tự: vẫn là cùng một người viết sai, nhưng chỉ gom khi đích duy nhất và
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


def fold_to_source_spelling(''',
)

patch(
    root / "ebook_reader" / "character_registry.py",
    '''        if not candidates:
            continue
        redirected[name] = max(
            candidates,
            key=lambda other: (counted[other], int(counts.get(other, 0)), other),
        )''',
    '''        if not candidates:
            # Lệch hai ký tự: `JOCLEYN` -> `Jocelyn`, `ARTELI` -> `ARTIL` (bạn cùng lỗi của nó, `ARTEL`, đã gom
            # bằng luật lệch một - một mình `ARTELI` đứng lại thành nhân vật riêng là vô nghĩa).
            candidates = _two_edit_candidates(folded_name, present)
        if not candidates:
            continue
        redirected[name] = max(
            candidates,
            key=lambda other: (counted[other], int(counts.get(other, 0)), other),
        )''',
)

test = root / "tests" / "test_a_name_two_letters_off_still_belongs_to_its_owner.py"
test.write_text('''"""Nhãn vắng mặt trong sách lệch hai ký tự thì gom, nhưng chỉ khi đích duy nhất và nhãn đủ dài."""
from __future__ import annotations

from ebook_reader.character_registry import fold_for_source_search, fold_to_source_spelling

SOURCE = fold_for_source_search(
    "Jocelyn quay sang Artil. Artil im lặng. Jocelyn nói với Artil rằng Norman đã tới. "
    "Norman gật đầu với Jocelyn."
)


def test_two_letters_off_folds_to_the_one_spelling_in_the_book() -> None:
    folded = fold_to_source_spelling(["Jocelyn", "JOCLEYN", "ARTIL", "ARTELI", "Norman"], SOURCE)
    assert folded == {"JOCLEYN": "Jocelyn", "ARTELI": "ARTIL"}


def test_a_name_in_the_book_is_never_folded() -> None:
    assert fold_to_source_spelling(["Jocelyn", "Norman", "Artil"], SOURCE) == {}


def test_two_different_targets_are_not_guessed() -> None:
    source = fold_for_source_search("Marina và Karina cùng bước vào. Marina nói. Karina đáp.")
    # "SARINO" lệch đúng hai ký tự với CẢ Marina lẫn Karina -> hai đích khác nhau, không đoán.
    assert fold_to_source_spelling(["Marina", "Karina", "SARINO"], source) == {}


def test_a_short_label_is_not_folded_by_two_edits() -> None:
    source = fold_for_source_search("Tom bước vào. Tom nói. Tom đi ra.")
    # "TAP" lệch hai ký tự với "Tom" nhưng chỉ dài 3 -> không gom.
    assert fold_to_source_spelling(["Tom", "TAP"], source) == {}
    assert fold_to_source_spelling(["Tom", "ROM"], source) == {"ROM": "Tom"}  # lệch một, luật cũ
''', encoding="utf-8")
print(f"da viet {test}")
