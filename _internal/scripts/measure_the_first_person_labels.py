"""Nhãn đại từ ngôi thứ nhất: cuốn này có bao nhiêu câu như thế, và chúng là lời của AI?

    python scripts/measure_the_first_person_labels.py                      # sàng cuốn đang cấu hình
    python scripts/measure_the_first_person_labels.py --read ME --limit 6   # đọc ngữ cảnh từng ca
    source scripts/book1.env && python scripts/measure_the_first_person_labels.py

Chỉ đọc: mở mọi `project.sqlite3` của cuốn ở chế độ read-only, không ghi gì.

## Câu hỏi

`voices.first_person_identity` (đặt qua `EBOOK_FIRST_PERSON` → `cli create --first-person`) viết
lại mọi nhãn `tôi`/`ta`/`mình`/`me` về **một** danh tính. Điều đó đúng khi những câu ấy là lời của
người kể ngôi thứ nhất, và **sai** khi chúng là lời của người khác — ví dụ một trang nhật ký đang
được đọc hộ. Script này là phép đo để trả lời, trước khi bật công tắc cho một cuốn mới.

## Kết quả đã đo (04:00 ngày 2026-09-16)

    cuon 1 (ke ngoi thu nhat)  129 ca   ME 94, Toi 34, TOI 1   -> tat ca la loi nhan vat chinh
    cuon 2 (ke ngoi thu ba)     10 ca   Minh 10                -> CA 10 la nhat ky nu phu thuy
                                                                  (chuong 022/023/032)

Vì thế cuốn 1 đặt `EBOOK_FIRST_PERSON=SAMAEL` (xem `scripts/book1.env`) và cuốn 2 để trống.

## Thước, và giới hạn của nó

Quanh mỗi ca (±3 đoạn) tìm cụm nói rằng câu ấy đang được **đọc hộ**. Cuốn 2 là **mẫu dương**:
9/10 ca sáng. Một thước không bắt được mẫu dương thì kết luận "cuốn kia sạch" chẳng có giá trị gì.

Thước này chỉ **sàng**, không phán: cuốn 1 sáng đúng một ca, và đọc tay thì đó là `"Sao thế,
Juli?"` của chính người kể — sáng chỉ vì chuỗi `di thư` nằm trong chữ `midi thướt tha`. Luôn đọc
bằng `--read`. `khắc` và `trích` đã bị bỏ khỏi thước vì `khoảnh khắc` làm sáng 8 ca vô tội: một
thước hay kêu oan là thước không ai đọc nữa.
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
    from scripts.book_paths import VERSIONS, describe  # noqa: E402
except ImportError:  # chạy trực tiếp
    from book_paths import VERSIONS, describe  # noqa: E402

# Cùng danh sách với `character_registry.FIRST_PERSON_PRONOUNS`, và cố ý là một bản chép: script
# đo phải chạy được cả khi bản vá chưa vào cây (đó chính là lúc cần nó nhất).
FIRST_PERSON = {"tôi", "ta", "mình", "tớ", "tao", "tui", "me"}

READ_ALOUD = re.compile(
    r"nhật ký|ghi chép|lá thư|bức thư|thư viết|cuộn giấy|trang giấy|di thư|sổ tay"
    r"|viết rằng|viết ra|dòng chữ|bản thảo|đọc to|đọc lên|tấm bia",
    flags=re.IGNORECASE,
)


def _say(line: str) -> None:
    try:
        print(line, flush=True)
    except UnicodeEncodeError:
        print(line.encode("ascii", "backslashreplace").decode("ascii"), flush=True)


def _databases(versions: Path) -> list[str]:
    return sorted(glob.glob(str(versions / "*" / "*" / "project.sqlite3")))


def _open(database: str) -> sqlite3.Connection:
    connection = sqlite3.connect(f"file:{Path(database).as_posix()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    return connection


def _is_first_person(speaker: object) -> bool:
    # Gấp chữ trong Python, KHÔNG bằng `UPPER()` của SQLite: `upper()` ở đó chỉ ánh xạ a-z, nên
    # "Tôi" thành "TôI" và phép so với "TÔI" im lặng trượt. Bản đầu của script này tìm được 1 ca
    # trong khi có 71 câu.
    return " ".join(str(speaker or "").strip().casefold().split()) in FIRST_PERSON


def screen(versions: Path, window: int) -> int:
    seen: set[tuple[str, int]] = set()
    labels: Counter[str] = Counter()
    flagged: list[tuple[str, int, str, str]] = []
    for database in _databases(versions):
        connection = _open(database)
        try:
            rows = connection.execute(
                "SELECT s.seq, s.speaker, s.chapter_id, ch.title t "
                "FROM segments s JOIN chapters ch ON ch.id = s.chapter_id "
                "WHERE s.speaker IS NOT NULL"
            ).fetchall()
        except sqlite3.Error as exc:
            _say(f"(bỏ qua {Path(database).parent.name}: {exc})")
            connection.close()
            continue
        for row in rows:
            if not _is_first_person(row["speaker"]):
                continue
            key = (str(row["t"]), int(row["seq"]))
            if key in seen:
                continue  # project vá / đúc lại lặp lại cùng một chương
            seen.add(key)
            labels[str(row["speaker"]).strip()] += 1
            near = connection.execute(
                "SELECT seq, text FROM segments WHERE chapter_id = ? AND seq BETWEEN ? AND ? "
                "ORDER BY seq",
                (int(row["chapter_id"]), int(row["seq"]) - window, int(row["seq"]) + window),
            ).fetchall()
            cues = {
                match.group(0)
                for other in near
                if int(other["seq"]) != int(row["seq"])
                for match in [READ_ALOUD.search(str(other["text"] or ""))]
                if match
            }
            if cues:
                flagged.append((str(row["t"]), int(row["seq"]), str(row["speaker"]), ", ".join(sorted(cues))))

    _say(f"{len(seen)} ca khác nhau (theo chương+seq), theo nhãn: "
         + (", ".join(f"{name}={count}" for name, count in labels.most_common()) or "(không có)"))
    _say("")
    if not flagged:
        _say("KHÔNG ca nào có cụm 'đọc hộ' quanh nó - mọi ca đều có thể là lời người kể.")
    else:
        _say(f"{len(flagged)} ca có cụm 'đọc hộ' quanh nó - ĐỌC TAY bằng --read trước khi kết luận:")
        for title, seq, speaker, cues in sorted(flagged):
            _say(f"   chương {title}  seq {seq:>4}  [{speaker}]  <- {cues}")
    return 0


def read(versions: Path, label: str, limit: int, before: int) -> int:
    wanted = " ".join(label.strip().casefold().split())
    seen: set[tuple[str, int]] = set()
    shown = 0
    for database in _databases(versions):
        connection = _open(database)
        try:
            hits = [
                row
                for row in connection.execute(
                    "SELECT s.seq, s.speaker, s.chapter_id, ch.title t "
                    "FROM segments s JOIN chapters ch ON ch.id = s.chapter_id "
                    "WHERE s.speaker IS NOT NULL ORDER BY ch.title, s.seq"
                ).fetchall()
                if " ".join(str(row["speaker"]).strip().casefold().split()) == wanted
            ]
            for hit in hits:
                key = (str(hit["t"]), int(hit["seq"]))
                if key in seen:
                    continue
                seen.add(key)
                if shown >= limit:
                    continue
                shown += 1
                _say("")
                _say(f"--- chương {hit['t']}  seq {hit['seq']}  ({Path(database).parent.name})")
                for row in connection.execute(
                    "SELECT seq, speaker, kind, substr(text, 1, 110) text FROM segments "
                    "WHERE chapter_id = ? AND seq BETWEEN ? AND ? ORDER BY seq",
                    (int(hit["chapter_id"]), int(hit["seq"]) - before, int(hit["seq"]) + 1),
                ):
                    mark = ">>" if int(row["seq"]) == int(hit["seq"]) else "  "
                    speaker = str(row["speaker"] or "-")
                    kind = str(row["kind"] or "")
                    _say(f" {mark} {row['seq']:>4} [{speaker:<16}|{kind:<9}] {row['text']}")
        except sqlite3.Error as exc:
            _say(f"(bỏ qua {Path(database).parent.name}: {exc})")
        finally:
            connection.close()
    _say("")
    _say(f"tổng {len(seen)} ca mang nhãn {label!r}; đã in {shown}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--versions", type=Path, default=VERSIONS)
    parser.add_argument("--read", metavar="NHÃN", help="in ngữ cảnh từng ca của một nhãn")
    parser.add_argument("--limit", type=int, default=8)
    parser.add_argument("--window", type=int, default=3)
    args = parser.parse_args(argv)

    _say(describe())
    _say("")
    if args.read:
        return read(args.versions, args.read, args.limit, args.window)
    return screen(args.versions, args.window)


if __name__ == "__main__":
    sys.exit(main())
