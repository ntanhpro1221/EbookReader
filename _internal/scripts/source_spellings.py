"""Cách viết nào có trong chính cuốn sách? — quan toà cho những cái tên tranh nhau.

`scripts/name_marks.py` xử lớp **rơi dấu** bằng một tín hiệu nội tại: bản nhiều dấu hơn thắng.
Lớp **sai một ký tự** không có tín hiệu như thế, và số câu thoại thì đã bị nhiễm — model phân
tích nói nhiều bằng bản sai thì bản sai thắng, rồi `_known_summary` đưa nó vào prompt lô sau.
Đo ngày 2026-09-10 trên lô 3:

    Selene   198 lần trong nguồn      SELENE    7 câu thoại
    Selne      0 lần                  SELNE    32 câu thoại   <- bản sai đang thắng

Nhân vật thật tên **Selene**. Không cần đoán: trên 30 nhân vật có tên của lô 3, đúng **4** cái
tên không xuất hiện lấy một lần trong 92 chương nguồn — `SELNE`, `SELNE VALKRYN`, `SAMAELE` và
`NARRATOR` (một vai bị lọt). Không một nhân vật thật nào có 0 lần. Phép phân biệt dứt khoát,
và nó nằm ngay trên đĩa.

Luật: **cách viết có trong nguồn thắng cách viết không có.** Số câu chỉ dùng khi cả hai đều có
(hoặc cả hai đều không) — lúc ấy module này không nói gì và luật khác quyết.

Vì sao không dùng khoảng cách sửa một mình: `SỐ BA` (2 câu) và `SỐ BẢY` (7 câu) lệch nhau một ký
tự sau khi bỏ dấu, và là **hai người thật** — cả hai có trong nguồn, nên luật này không chạm tới
chúng. Một luật "lệch một ký tự thì gộp" sẽ nhập hai nhân vật làm một; ngưỡng tỉ lệ cứu được
(4×), nguồn văn bản cứu **chắc chắn**.
"""
from __future__ import annotations

import io
import re
import sqlite3
import unicodedata
from pathlib import Path


def fold(text: str) -> str:
    """Chữ thường, bỏ hết dấu — để so một cái tên với văn xuôi viết hoa/thường tuỳ chỗ."""
    lowered = unicodedata.normalize("NFD", text.lower())
    return "".join(ch for ch in lowered if not unicodedata.combining(ch))


def source_paths(project: Path) -> list[Path]:
    """Các file nguồn của chính project ấy, đọc từ `chapters.input_path`.

    Lấy từ project chứ không phải một đường dẫn ghi cứng: mỗi project biết nó đọc từ đâu, và
    một lô vá một chương chỉ trỏ tới một file. Xem `source_text` cho hệ quả.
    """
    try:
        conn = sqlite3.connect(f"file:{project / 'project.sqlite3'}?mode=ro", uri=True)
        try:
            rows = conn.execute("SELECT DISTINCT input_path FROM chapters").fetchall()
        finally:
            conn.close()
    except sqlite3.Error:
        return []
    found: list[Path] = []
    for (value,) in rows:
        if not value:
            continue
        path = Path(str(value))
        if path.is_file():
            found.append(path)
    return sorted(set(found))


def source_text(project: Path, *, whole_book: bool = True) -> str:
    """Văn bản nguồn đã bỏ dấu, để đếm. Rỗng nếu không đọc được file nào.

    `whole_book=True` (mặc định) đọc **mọi** file .txt cùng thư mục với các file của project,
    không chỉ những chương project ấy chạy. Lý do: một project vá một chương chỉ trỏ tới một
    file, và hỏi "cái tên này có trong sách không" bằng một chương thì gần như luôn trả lời
    "không" — tức luật sẽ gộp bừa đúng lúc nó có ít bằng chứng nhất.
    """
    paths = source_paths(project)
    if not paths:
        return ""
    if whole_book:
        folders = {path.parent for path in paths}
        paths = sorted({p for folder in folders for p in folder.glob("*.txt")}) or paths
    chunks: list[str] = []
    for path in paths:
        try:
            chunks.append(io.open(path, encoding="utf-8", errors="replace").read())
        except OSError:
            continue
    return fold("\n".join(chunks))


def occurrences(name: str, folded_source: str) -> int:
    """Số lần một cái tên xuất hiện trong nguồn đã bỏ dấu."""
    needle = fold(name).strip()
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
    names: list[str],
    folded_source: str,
    lines: dict[str, int] | None = None,
) -> dict[str, str]:
    """Trỏ cách viết KHÔNG có trong nguồn về cách viết CÓ. Trả về {tên thua: tên thắng}.

    Chỉ những tên vắng mặt hẳn (0 lần) mới được xét, và chỉ được trỏ về một tên **có mặt** mà
    lệch nó đúng một ký tự — hoặc lệch một ký tự với **từ đầu** của nó, để `SELNE VALKRYN` về
    được `SELENE` mà không cần biết `VALKRYN` là họ bịa.

    Người thắng là tên xuất hiện **nhiều nhất trong nguồn**; `lines` chỉ phá hoà. Không bao giờ
    trỏ một tên có mặt về đâu cả: cuốn sách nói nó tồn tại thì nó tồn tại.
    """
    if not folded_source:
        return {}
    counted = {name: occurrences(name, folded_source) for name in names}
    present = [name for name, hits in counted.items() if hits > 0]
    if not present:
        return {}
    lines = lines or {}
    redirected: dict[str, str] = {}
    for name, hits in counted.items():
        if hits:
            continue
        folded_name = fold(name).strip()
        first_word = folded_name.split()[0] if folded_name.split() else ""
        candidates = [
            other
            for other in present
            if _within_one_edit(folded_name, fold(other).strip())
            or (first_word and _within_one_edit(first_word, fold(other).strip()))
        ]
        if not candidates:
            continue
        redirected[name] = max(
            candidates,
            key=lambda other: (counted[other], int(lines.get(other, 0)), other),
        )
    return redirected
