"""Project nào là "mới nhất" của một lô, và chuỗi project nào để cộng dồn — cho các launcher.

    python scripts/seed_chain.py 3 --seed     # project để GIEO lần chạy kế tiếp: mới nhất trên lô, lô+v, lô+r
    python scripts/seed_chain.py 3 --batch    # project lô (thư mục thường) - nơi đọc danh sách chương hỏng
    python scripts/seed_chain.py 3 --chain    # chuỗi cho backfill_exposure.py, kết thúc ở --seed
    python scripts/seed_chain.py --chain-all  # chuỗi phủ MỌI lô đang có - dùng khi vá/đúc lại lô cũ
    python scripts/seed_chain.py 3 --repairs  # các project v/r của lô 3, theo thứ tự tạo
    python scripts/seed_chain.py --newest <thư mục>   # project mới nhất trong một thư mục
    python scripts/seed_chain.py --newest <thư mục> --newer-than <project>   # ... chỉ khi mới hơn project ấy

Vì sao có file này: từ lô 3 có project ĐÚC LẠI GIỌNG từng chương (`lo03r_066` ...). Chúng gieo
từ lô và cấp giọng **mới** cho người thua khi hai người trùng giọng. Nếu lô 4 gieo từ chính lô 3
thì người ấy được cấp giọng lần nữa, độc lập, và có thể khác — một người hai giọng ở hai lô, lỗi
im lặng không cổng nào bắt. Nên (1) các project vá / đúc lại phải nối đuôi nhau, mỗi cái gieo từ
cái trước, và (2) lô sau gieo từ cái **cuối** chuỗi. Ba script cần cùng một câu trả lời cho "cái
cuối là cái nào", và chép tay ba lần là ba cơ hội lệch.

"Mới" đo bằng `book.created_at` trong project.sqlite3, KHÔNG bằng mtime thư mục: SQLite tạo và
xoá `-wal`/`-shm` mỗi lần ai đó mở DB, nên thư mục lô 2 trẻ hơn cả ba project vá của nó chỉ vì
tôi đọc nó sau. Đo 2026-09-10: `ls -dt` xếp `lo02_4d783ac744` trước `lo02v_053`.
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

try:
    from scripts.book_paths import VERSIONS as _BOOK_VERSIONS, TAG_PREFIX  # noqa: E402
except ImportError:  # chạy trực tiếp: python scripts/seed_chain.py
    from book_paths import VERSIONS as _BOOK_VERSIONS, TAG_PREFIX  # noqa: E402
VERSIONS_ROOT = _BOOK_VERSIONS


def tag_of(batch: int) -> str:
    return f"{TAG_PREFIX}-lo{int(batch):02d}"


def created_at(project: Path) -> float:
    """`book.created_at`; 0.0 (xếp trước hết) kèm một dòng cảnh báo nếu không đọc được."""
    try:
        conn = sqlite3.connect(f"file:{project / 'project.sqlite3'}?mode=ro", uri=True)
        try:
            row = conn.execute("SELECT created_at FROM book").fetchone()
        finally:
            conn.close()
        return float(row[0]) if row and row[0] is not None else 0.0
    except (sqlite3.Error, ValueError, TypeError):
        print(f"seed_chain: không đọc được book.created_at của {project}", file=sys.stderr)
        return 0.0


def projects_in(folder: Path) -> list[Path]:
    """Mọi project trong một thư mục phiên bản, cũ trước mới sau."""
    if not folder.is_dir():
        return []
    found = [p for p in folder.iterdir() if (p / "project.sqlite3").is_file()]
    return sorted(found, key=lambda p: (created_at(p), p.name))


def batch_project(batch: int, root: Path = VERSIONS_ROOT) -> Path | None:
    projects = projects_in(root / tag_of(batch))
    return projects[-1] if projects else None


def repairs(batch: int, root: Path = VERSIONS_ROOT) -> list[Path]:
    tag = tag_of(batch)
    found = projects_in(root / f"{tag}v") + projects_in(root / f"{tag}r")
    return sorted(found, key=lambda p: (created_at(p), p.name))


def seed_project(batch: int, root: Path = VERSIONS_ROOT) -> Path | None:
    """Mới nhất trên cả ba thư mục — cái mang casting đầy đủ nhất của lô."""
    candidates = repairs(batch, root)
    head = batch_project(batch, root)
    if head is not None:
        candidates.append(head)
    if not candidates:
        return None
    return max(candidates, key=lambda p: (created_at(p), p.name))


def chain(batch: int, root: Path = VERSIONS_ROOT) -> list[Path]:
    """Mọi project của mọi lô tới `batch`, cũ trước mới sau - kể cả project vá / đúc lại.

    Bản đầu chỉ lấy **project lô** của các lô trước và bỏ hết project vá / đúc lại của chúng.
    Đo 2026-09-11 trên chuỗi của lô 4: sáu project của lô 3 (`lo03v_075` và năm `lo03r_*`) bị
    bỏ, nên sổ cộng dồn gieo cho lô 4 đếm sáu chương ấy theo bản **trước** khi đúc lại - tức
    theo cách viết tên trước khi gộp (THU LÃNH chưa về THỦ LÃNH). Chương thì vẫn đủ, nhưng
    thuộc về ai thì sai.

    Không sợ đếm đôi: `backfill_exposure` lấy chương theo **tiêu đề** và project đứng sau
    thắng, nên thêm một project đúc lại cùng chương chỉ thay bản cũ chứ không cộng thêm.

    Kết thúc ở đúng `seed_project(batch)` theo cách dựng - cả hai xếp theo `created_at`.
    """
    links: list[Path] = []
    for index in range(1, batch + 1):
        own = repairs(index, root)
        head = batch_project(index, root)
        if head is not None:
            own.append(head)
        own.sort(key=lambda path: (created_at(path), path.name))
        links.extend(own)
    return links


def highest_batch(root: Path = VERSIONS_ROOT) -> int:
    """Số lô CAO NHẤT đang có project. 0 nếu chưa có lô nào.

    `chain(batch)` chỉ lấy tới `batch`, và đó là câu trả lời đúng cho một lượt phóng lô tiến về
    phía trước. Nó là câu trả lời SAI cho một lượt vá / đúc lại một lô CŨ: `launch_repair.sh 1`
    gọi `chain(1)` nên sổ cộng dồn được dựng lại từ **chỉ lô 1** rồi ghi đè lên sổ đầy đủ.

    Cái giá đã đo, 06:37 ngày 2026-09-16: sổ của lo04 bị ghi lại thành `NATASHA 8 câu / 1 lô`
    (thật: 389 câu / 10 lô, 42 chương) vì lô 1 không có bà ấy; `CHELY` có 9 câu / 1 lô. Lúc
    `port_casting` xếp hạng ai giữ giọng dùng chung, 8 < 9 nên **CHELY thắng** và NATASHA mất
    pin — rồi chương 090 lên sách với giọng thiểu số của bà ấy. Một nhân vật 42 chương thua một
    nhân vật 1 chương vì sổ bị thu nhỏ lại đúng một lô.
    """
    found = 0
    for index in range(1, 100):
        if batch_project(index, root) is not None or repairs(index, root):
            found = index
    return found


def main(argv: list[str]) -> int:
    positional = [a for a in argv if not a.startswith("--")]
    flags = {a for a in argv if a.startswith("--")}
    if flags == {"--chain-all"} and not positional:
        # Chuỗi cho `backfill_exposure.py` phủ MỌI lô đang có, không chỉ tới một lô. Xem
        # `highest_batch` cho cái giá của việc lấy thiếu.
        links = chain(highest_batch())
        if not links:
            return 1
        print(" ".join(p.as_posix() for p in links))
        return 0
    if flags == {"--newest", "--newer-than"} and len(positional) == 2:
        # `--newest <thư mục> --newer-than <project>`: chỉ trả project mới nhất của thư mục nếu nó
        # MỚI HƠN project đang làm gieo; không thì thoát 1 để launcher giữ gieo cũ (`|| echo "$SEED"`).
        #
        # Vì sao: từ 17-09, `launch_repair.sh` dời một bản đúc lại hại nhiều hơn giúp ra
        # `_quarantine_<ngày>` (`ship_only_recasts_that_help.py`). Khi ấy `--newest` trên thư mục
        # `loNNr` trả một bản đúc lại CŨ HƠN, có thể từ một ranh giới trước, và `boundary.sh` bước
        # 4b sẽ gieo lô kế tiếp từ đó thay vì từ project vừa xong.
        folder, current = Path(positional[0]), Path(positional[1])
        projects = projects_in(folder)
        if not projects:
            print(f"không có project nào trong {folder}", file=sys.stderr)
            return 1
        if created_at(projects[-1]) <= created_at(current):
            print(
                f"{projects[-1].name} không mới hơn {current.name} - giữ gieo cũ",
                file=sys.stderr,
            )
            return 1
        print(projects[-1].as_posix())
        return 0
    if flags == {"--newest"} and len(positional) == 1:
        # Project mới nhất trong MỘT thư mục bất kỳ - launch_repair.sh cần nó ngay sau `create`,
        # vì thư mục lô vá chứa cả các chương đã chạy trước đó trong cùng lượt.
        projects = projects_in(Path(positional[0]))
        if not projects:
            print(f"không có project nào trong {positional[0]}", file=sys.stderr)
            return 1
        print(projects[-1].as_posix())
        return 0
    if len(positional) != 1 or len(flags) != 1 or not positional[0].isdigit():
        print(__doc__.split("\n\n")[1], file=sys.stderr)
        return 2
    batch = int(positional[0])
    flag = flags.pop()
    if flag == "--seed":
        found = seed_project(batch)
        if found is None:
            print(f"không có project nào của lô {batch}", file=sys.stderr)
            return 1
        print(found.as_posix())
    elif flag == "--batch":
        found = batch_project(batch)
        if found is None:
            print(f"không có project lô trong {tag_of(batch)}", file=sys.stderr)
            return 1
        print(found.as_posix())
    elif flag == "--chain":
        links = chain(batch)
        if not links:
            return 1
        print(" ".join(p.as_posix() for p in links))
    elif flag == "--repairs":
        print(" ".join(p.as_posix() for p in repairs(batch)))
    else:
        print(f"cờ lạ: {flag}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
