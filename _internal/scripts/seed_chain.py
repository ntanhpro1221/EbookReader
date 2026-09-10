"""Project nào là "mới nhất" của một lô, và chuỗi project nào để cộng dồn — cho các launcher.

    python scripts/seed_chain.py 3 --seed     # project để GIEO lần chạy kế tiếp: mới nhất trên lô, lô+v, lô+r
    python scripts/seed_chain.py 3 --batch    # project lô (thư mục thường) - nơi đọc danh sách chương hỏng
    python scripts/seed_chain.py 3 --chain    # chuỗi cho backfill_exposure.py, kết thúc ở --seed
    python scripts/seed_chain.py 3 --repairs  # các project v/r của lô 3, theo thứ tự tạo

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

VERSIONS_ROOT = Path("D:/Novels/Audiobooks/_versions")


def tag_of(batch: int) -> str:
    return f"v0.2.0-lo{int(batch):02d}"


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
    """Project lô của mọi lô trước, rồi lô này cùng các project v/r của nó theo thứ tự tạo.

    Kết thúc ở đúng `seed_project(batch)` theo cách dựng - cả hai xếp theo `created_at`.
    """
    earlier = [p for i in range(1, batch) if (p := batch_project(i, root)) is not None]
    own = repairs(batch, root)
    head = batch_project(batch, root)
    if head is not None:
        own.append(head)
    own.sort(key=lambda p: (created_at(p), p.name))
    return earlier + own


def main(argv: list[str]) -> int:
    positional = [a for a in argv if not a.startswith("--")]
    flags = {a for a in argv if a.startswith("--")}
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
