"""Một tên rơi dấu vẫn là tên ấy — bản dùng cho các script gieo, khớp với `character_registry`.

`character_registry.dropped_marks_variant_of` là bản chính (vào cây ở bản vá
`patch_dropped_marks_are_the_same_name`). Bản này tồn tại vì `port_casting.py` phải gộp được
hai cách viết **ngay bây giờ**, trước ranh giới lô — lô 3 đang chạy và mang trong `characters`
cả NGUOI TRA LOI (160 lần) lẫn NGƯỜI TRẢ LỜI (46), cả THU LÃNH (66) lẫn THỦ LÃNH (32). Gieo
nguyên như thế sang lô 4 là mang cái tách đôi đi tiếp, kể cả sau khi registry đã được vá.

`tests/test_name_marks_agree.py` ghim rằng hai bản cho cùng câu trả lời trên cùng một bộ mẫu,
để lúc registry đổi luật thì file này không lặng lẽ lệch đi.
"""
from __future__ import annotations

import unicodedata


def _normalize(name: str) -> str:
    return " ".join(str(name).strip().casefold().split())


def stripped_and_marks(name: str) -> tuple[str, tuple[tuple[int, str], ...]]:
    """Tên bỏ hết dấu, và danh sách (vị trí, dấu) đã bỏ."""
    decomposed = unicodedata.normalize("NFD", _normalize(name))
    letters: list[str] = []
    marks: list[tuple[int, str]] = []
    for char in decomposed:
        if unicodedata.combining(char):
            marks.append((len(letters) - 1, char))
        else:
            letters.append(char)
    return "".join(letters), tuple(marks)


def dropped_marks_variant_of(loser: str, winner: str) -> bool:
    """`loser` có phải `winner` bị rơi bớt dấu không — và chỉ rơi, không đổi.

    Chữ cái trần giống hệt, mọi dấu `loser` còn giữ đều có đúng vị trí trong `winner`, và
    `winner` nhiều dấu hơn. "THU LÃNH" là "THỦ LÃNH" rơi dấu hỏi; "MÁ" **không** phải "MÀ" rơi
    gì cả — dấu sắc của nó không có trong "MÀ", nên đó là hai từ.
    """
    stripped_loser, marks_loser = stripped_and_marks(loser)
    stripped_winner, marks_winner = stripped_and_marks(winner)
    if stripped_loser != stripped_winner:
        return False
    if len(marks_winner) <= len(marks_loser):
        return False
    return set(marks_loser) <= set(marks_winner)


def fold_dropped_marks(names: list[str], weight: dict[str, int] | None = None) -> dict[str, str]:
    """{tên thua: tên thắng} cho mọi cặp rơi dấu trong `names`. Tên không dính cặp nào thì vắng.

    Người thắng là bản **nhiều dấu nhất**; `weight` (số lần nhắc) chỉ phá hoà giữa hai bản cùng
    số dấu. Không chọn theo số lần, vì số lần đã bị nhiễm: lô 3 có NGUOI TRA LOI 160 lần còn
    NGƯỜI TRẢ LỜI 46, và chọn theo số lần là để bản sai thắng rồi lớn thêm ở lô sau.
    """
    weight = weight or {}
    by_stripped: dict[str, list[str]] = {}
    for name in names:
        by_stripped.setdefault(stripped_and_marks(name)[0], []).append(name)
    folded: dict[str, str] = {}
    for group in by_stripped.values():
        if len(group) < 2:
            continue
        for name in group:
            better = [other for other in group if other != name and dropped_marks_variant_of(name, other)]
            if not better:
                continue
            folded[name] = max(
                better,
                key=lambda candidate: (
                    len(stripped_and_marks(candidate)[1]),
                    int(weight.get(candidate, 0)),
                    candidate,
                ),
            )
    return folded
