"""Sổ cộng dồn: mỗi nhân vật đã nói bao nhiêu câu qua **mọi** lô — thứ `mention_count` không giữ.

    python scripts/backfill_exposure.py <project lô 1> <project lô 2> ... <project lô N>

Ghi bảng `character_exposure` vào project **cuối cùng** trong danh sách, tức project sắp được
gieo đi. Bảng ấy nằm ngoài `SCHEMA` của `database.py` và không module nào trong `ebook_reader`
đọc hay ghi nó — đó là lý do nó tồn tại.

Vì sao cần: `upsert_character` **ghi đè** `mention_count` bằng số câu của lô hiện tại. Đo ngày
2026-09-10:

```
              lô 1    lô 2    lô 3
SAMAEL          10      99      19      <- thật ra đã nói 128 câu
THỦ LÃNH       178     111      32      <- thật ra 321, chưa kể bản rơi dấu
```

`port_casting` từng xếp hạng "ai giữ giọng khi hai người trùng" theo `mention_count` với lời
giải thích rằng nó cộng dồn. Nó không cộng dồn. Trên ranh giới lô 3 → lô 4, KANG (19 câu, mới)
**hoà** SAMAEL (19 theo sổ sai, 128 theo sự thật) và chỉ nấc phá hoà cuối cùng cứu được SAMAEL.
Thêm một câu cho KANG là nhân vật chính đổi giọng, không cổng nào bắt được.

Tên được gộp theo luật rơi dấu (`scripts/name_marks.py`), nên THU LÃNH cộng vào THỦ LÃNH.
Idempotent: chạy lại thì tính lại từ đầu, không cộng chồng.

Chỉ đọc mọi project trừ project cuối; project cuối phải đã chạy xong (không còn lease sống).
"""
from __future__ import annotations

import sqlite3
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.name_marks import fold_dropped_marks  # noqa: E402

LEDGER_TABLE = "character_exposure"
LEDGER_DDL = f"""
CREATE TABLE IF NOT EXISTS {LEDGER_TABLE} (
    canonical_name TEXT PRIMARY KEY,
    dialogue_lines INTEGER NOT NULL,
    batches INTEGER NOT NULL,
    updated_at REAL NOT NULL
)
"""


def _say(line: str) -> None:
    try:
        print(line)
    except (UnicodeEncodeError, OSError, ValueError):
        sys.stdout.buffer.write(line.encode("utf-8", "replace") + b"\n")


def dialogue_lines(project: Path) -> Counter[str]:
    """Số câu thoại mỗi nhân vật có tên trong một project, đã gộp cách viết rơi dấu."""
    conn = sqlite3.connect(f"file:{project / 'project.sqlite3'}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            SELECT c.canonical_name AS name, count(*) AS n
            FROM segments s JOIN characters c ON c.id = s.canonical_character_id
            WHERE s.kind = 'dialogue'
              AND c.canonical_name NOT LIKE 'NPC/_%' ESCAPE '/'
              AND upper(c.canonical_name) NOT LIKE 'ANONYMOUS%'
            GROUP BY c.id
            """
        ).fetchall()
    finally:
        conn.close()
    raw = {str(r["name"]): int(r["n"]) for r in rows}
    folded = fold_dropped_marks(list(raw), raw)
    counts: Counter[str] = Counter()
    for name, n in raw.items():
        counts[folded.get(name, name)] += n
    return counts


def _alive(project: Path) -> bool:
    try:
        conn = sqlite3.connect(f"file:{project / 'project.sqlite3'}?mode=ro", uri=True)
        try:
            beats = [
                time.time() - float(r[0] or 0.0)
                for r in conn.execute("SELECT heartbeat_at FROM worker_leases")
            ]
        finally:
            conn.close()
    except sqlite3.Error:
        return False
    return bool(beats) and min(beats) < 180.0


def backfill(chain: list[Path]) -> dict[str, tuple[int, int]]:
    """Tổng qua cả chuỗi. Trả về {tên: (số câu, số lô có mặt)} sau khi đã ghi vào project cuối."""
    total: Counter[str] = Counter()
    present: Counter[str] = Counter()
    for project in chain:
        counts = dialogue_lines(project)
        for name, n in counts.items():
            total[name] += n
            present[name] += 1
        _say(f"  {project.name:28s} {sum(counts.values()):6d} câu  {len(counts):3d} nhân vật")
    # Gộp lần nữa TRÊN tổng, vì hai lô có thể viết cùng một tên theo hai cách khác nhau.
    folded = fold_dropped_marks(list(total), dict(total))
    merged: Counter[str] = Counter()
    seen_in: Counter[str] = Counter()
    for name, n in total.items():
        merged[folded.get(name, name)] += n
        seen_in[folded.get(name, name)] += present[name]

    target = chain[-1]
    conn = sqlite3.connect(str(target / "project.sqlite3"))
    try:
        conn.executescript(LEDGER_DDL)
        conn.execute(f"DELETE FROM {LEDGER_TABLE}")
        now = time.time()
        conn.executemany(
            f"INSERT INTO {LEDGER_TABLE} (canonical_name, dialogue_lines, batches, updated_at)"
            " VALUES (?,?,?,?)",
            [(name, int(n), int(seen_in[name]), now) for name, n in merged.items()],
        )
        conn.commit()
    finally:
        conn.close()
    return {name: (int(n), int(seen_in[name])) for name, n in merged.items()}


def read_ledger(project: Path) -> dict[str, int]:
    """{tên: số câu cộng dồn} nếu project có sổ, rỗng nếu chưa. Không bao giờ ném."""
    try:
        conn = sqlite3.connect(f"file:{project / 'project.sqlite3'}?mode=ro", uri=True)
        try:
            names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if LEDGER_TABLE not in names:
                return {}
            return {
                str(r[0]): int(r[1])
                for r in conn.execute(f"SELECT canonical_name, dialogue_lines FROM {LEDGER_TABLE}")
            }
        finally:
            conn.close()
    except sqlite3.Error:
        return {}


def main(argv: list[str]) -> int:
    chain = [Path(p) for p in argv if not p.startswith("--")]
    if not chain:
        _say("dùng: backfill_exposure.py <project lô 1> ... <project lô N>  (ghi vào N)")
        return 2
    for project in chain:
        if not (project / "project.sqlite3").is_file():
            _say(f"không phải project: {project}")
            return 2
    if _alive(chain[-1]):
        _say(f"{chain[-1].name} đang chạy - không ghi vào một project đang bay.")
        return 3
    _say(f"cộng dồn qua {len(chain)} lô, ghi vào {chain[-1].name}:")
    ledger = backfill(chain)
    top = sorted(ledger.items(), key=lambda kv: -kv[1][0])[:8]
    _say("")
    _say(f"{len(ledger)} nhân vật trong sổ. Nhiều câu nhất:")
    for name, (n, batches) in top:
        _say(f"  {name:20s} {n:5d} câu  qua {batches} lô")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
