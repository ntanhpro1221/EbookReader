r"""Nguồn viết sai một cái tên đã có cách đọc — bao nhiêu chỗ, và có tới tai người nghe không?

    python scripts/measure_a_name_spelled_two_ways.py
    python scripts/measure_a_name_spelled_two_ways.py --min-length 6 --max-distance 1

Chỉ đọc: mở database project ở chế độ read-only và đọc thư mục nguồn; không ghi gì.

## Ca thật

Lô 4 cuốn 2, chương 148, đoạn `c00009_s0000015` thất bại với `ASR_MISMATCH_UNRESOLVED`:

    van ban : “Heartmeer? Đó là cái gì?”
    Whisper : Admir à, đó là cái gì?        (do giong 0,67)

Sổ cách đọc có **`Hearthmeer`** → `Hát-me-ờ` (khoá, nguồn `english_name_transliteration`), nhưng
văn bản ở đúng chương ấy viết **`Heartmeer`** — thiếu chữ `h`. Cùng một cái tên, hai cách viết
trong **cùng một chương**: `Hearthmeer` 2 lần, `Heartmeer` 1 lần. Cách viết sai không có cách
đọc nào, nên giọng đọc tự xử, và không phép so nào bắc được cầu qua đó.

Chương vẫn lên sách (mã ấy thuộc `MACHINE_ACCEPTABLE`, máy nhận và ghi sổ), nên cái giá là một
câu đọc sai tên chứ không phải một chương mất. Nhưng lớp lỗi thì đáng đếm: **một cái tên viết
sai trong nguồn không bao giờ có cách đọc**, và chuyện ấy im lặng.

## Cách đo

Lấy mọi `surface` đã ghim trong sổ cách đọc của các project, rồi quét nguồn tìm những token
viết hoa **không** có trong sổ mà chỉ cách một `surface` đã ghim đúng 1–2 phép sửa ký tự. Mỗi
cặp như thế là một ứng viên "nguồn viết sai tên đã biết".

Có nhiễu: hai cái tên thật khác nhau cũng có thể cách nhau một ký tự (`Alice`/`Alicia`,
`Karl`/`Carl`). Nên script in **cả cặp và số lần xuất hiện** để đọc bằng mắt, và mặc định chỉ
xét token dài ≥ 6 ký tự với khoảng cách 1 — chỗ mà trùng hợp là khó xảy ra nhất.

## Kết quả đo (02:50 ngày 2026-09-16, cuốn 2, 915 chương)

Danh sách rộng cho 30 cặp, nhưng đọc ra thì **phần lớn không phải lỗi**: `Francis`/`Francois`
(297 lần), `Lauren`/`Laurent` (233), `Andrei`/`Andre`, `Simeon`/`Simon` là những **người khác
nhau**, và phần còn lại nằm ở chương 466+, 633+, 839+ — chưa sản xuất, nên chưa có cách đọc là
đúng: cách đọc chỉ sinh ra khi phân tích tới chương ấy.

Xiết lại thành luật chặt — cách viết lạ xuất hiện **đúng một lần**, tên đã ghim xuất hiện trong
**chính chương ấy**, cách nhau **một** phép sửa — thì cả cuốn còn **2 ca**:

    chuong 148  'Heartmeer' (1 lan)  <->  'Hearthmeer' (2 lan, doc 'Hát-me-ờ')   <- da that bai that
    chuong 296  'Gosset'    (1 lan)  <->  'Gossett'    (13 lan, doc 'Go-xét')    <- chua san xuat

**Hai ca trên 915 chương thì không đáng viết mã**, và một luật lỏng hơn sẽ gán sai ngay:
`Simon`/`Simeon` và `Andre`/`Andrei` là người khác nhau. Script này ở lại để **đo**, không để
sửa; ai muốn xử ca 296 thì thêm một dòng vào sổ cách đọc của lô ấy là xong.
"""
from __future__ import annotations

import argparse
import glob
import re
import sqlite3
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

try:
    from scripts.book_paths import SOURCE_DIR, VERSIONS  # noqa: E402
except ImportError:  # chạy trực tiếp
    from book_paths import SOURCE_DIR, VERSIONS  # noqa: E402

# Không lấy dấu sở hữu vào token: bản đầu nhận `Evans’` là một token khác `Evans` và tự tạo ra
# tám "cặp viết sai" chỉ gồm `Evans’`, `Lucien’`, `Thanos’`, `Allyn’`, `Ether’`, `Silvia’`,
# `Brook’`, `Douglas’` — tám dòng nhiễu trong một danh sách 30 dòng.
TOKEN = re.compile(r"[A-Z][A-Za-z-]{2,}")


def _say(line: str) -> None:
    try:
        print(line, flush=True)
    except UnicodeEncodeError:
        print(line.encode("ascii", "backslashreplace").decode("ascii"), flush=True)


def pinned_surfaces(versions: Path) -> dict[str, str]:
    """{surface: spoken_form} gom từ mọi project - một cách đọc đã ghim ở đâu cũng là đã biết."""
    out: dict[str, str] = {}
    for database in sorted(glob.glob(str(versions / "*" / "*" / "project.sqlite3"))):
        connection = sqlite3.connect(f"file:{Path(database).as_posix()}?mode=ro", uri=True)
        connection.row_factory = sqlite3.Row
        try:
            rows = connection.execute(
                "SELECT surface, spoken_form FROM pronunciations WHERE spoken_form IS NOT NULL"
            ).fetchall()
        except sqlite3.Error:
            continue
        finally:
            connection.close()
        for row in rows:
            out.setdefault(str(row["surface"]), str(row["spoken_form"]))
    return out


def _within(left: str, right: str, limit: int) -> int | None:
    """Khoảng cách sửa ký tự, bỏ sớm khi đã vượt `limit`. None nếu vượt."""
    if abs(len(left) - len(right)) > limit:
        return None
    previous = list(range(len(right) + 1))
    for i, a in enumerate(left, 1):
        current = [i]
        for j, b in enumerate(right, 1):
            current.append(
                min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (a != b))
            )
        if min(current) > limit:
            return None
        previous = current
    return previous[-1] if previous[-1] <= limit else None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--source", type=Path, default=SOURCE_DIR)
    parser.add_argument("--versions", type=Path, default=VERSIONS)
    parser.add_argument("--min-length", type=int, default=6)
    parser.add_argument("--max-distance", type=int, default=1)
    args = parser.parse_args(argv)

    pinned = pinned_surfaces(args.versions)
    if not pinned:
        _say("không có cách đọc nào đã ghim - không có gì để so")
        return 0
    known = {surface.casefold() for surface in pinned}

    counts: Counter[str] = Counter()
    where: dict[str, set[str]] = {}
    for path in sorted(args.source.glob("*.txt")):
        text = path.read_text(encoding="utf-8", errors="replace")
        for token in TOKEN.findall(text):
            if len(token) < args.min_length or token.casefold() in known:
                continue
            counts[token] += 1
            where.setdefault(token, set()).add(path.stem)

    _say(f"{len(pinned)} cách đọc đã ghim; {len(counts)} token viết hoa chưa có cách đọc")
    _say("")
    hits: list[tuple[int, str, str, int]] = []
    for token, n in counts.items():
        best: tuple[int, str] | None = None
        for surface in pinned:
            if abs(len(surface) - len(token)) > args.max_distance:
                continue
            distance = _within(token.casefold(), surface.casefold(), args.max_distance)
            if distance is not None and distance > 0 and (best is None or distance < best[0]):
                best = (distance, surface)
        if best is not None:
            hits.append((best[0], token, best[1], n))

    hits.sort(key=lambda item: (item[0], -item[3], item[1]))
    _say(f"{len(hits)} token chỉ cách một cách đọc đã ghim ≤ {args.max_distance} phép sửa:")
    _say("")
    _say(f"{'khoảng cách':>11}  {'trong nguồn':<22}{'đã ghim':<22}{'số lần':>7}  chương")
    for distance, token, surface, n in hits:
        chapters = ", ".join(sorted(where[token])[:5])
        _say(f"{distance:>11}  {token:<22}{surface:<22}{n:>7}  {chapters}")
    _say("")
    _say("Hai tên thật khác nhau cũng có thể cách nhau một ký tự - đọc từng cặp, đừng sửa hàng loạt.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
