"""Vá character_registry.py: khi hai người cùng ghim một giọng gặp nhau, người QUEN hơn trên cả cuốn giữ giọng.

Chạy: python patch_the_better_known_voice_keeps_its_pin.py <root>

**XẾP Ở RANH GIỚI 9.** `character_registry.py` nằm trong `QUALITY_IMPLEMENTATION_FILES`; lô 9 đã tạo
lúc 17:53 ngày 19-09 với luật cũ.

## Vì sao (19-09, 18:0x)

`_drop_pins_that_share_a_chapter` bỏ pin của một trong hai người cùng ghim một giọng khi họ nói cùng một
chương - đúng, vì hai người một giọng trong một cảnh là lỗi nặng nhất. Nhưng nó chọn người GIỮ theo **số
câu trong lô này**, và lô 8 cuốn 2 cho thấy cái giá:

    Bỏ giọng đã ghim của VICTOR (8 câu): trùng preset_thai_son_f100_p+00 với MORRIS (30 câu) ở chương [18]
    Bỏ giọng đã ghim của FELIPE (24 câu): trùng preset_thanh_binh_f097_p-04 với LAZAR (32 câu) ...
    Bỏ giọng đã ghim của ROCK (12 câu):   trùng preset_thanh_binh_f090_p-04 với ERIC (37 câu) ...

VICTOR là nhân vật chính: 64 chương bằng `thai_son_f100`, **329 câu qua 18 lô** theo sổ cộng dồn
(`character_exposure`). MORRIS: 54 câu. Vì MORRIS nói nhiều hơn trong riêng lô 8, VICTOR mất giọng cho CẢ
lô - 4 chương (361 371 373 378) đọc bằng `adam_bua`, và danh sách "một người nhiều giọng" nhận thêm 4 mục ở
người mà người nghe biết rõ nhất. Hai người ấy chia giọng từ hồi kho giọng nam chỉ có 2 preset (được phép
vì chưa từng cùng chương); kho mới có chỗ, nên người nên nhường là người ít quen.

Luật mới: xếp theo **số câu cộng dồn trên cả chuỗi lô** trước (sổ `character_exposure` mà
`scripts/backfill_exposure.py` ghi vào project trước mỗi lô), rồi mới tới số câu trong lô, rồi tên. Không
có sổ (project cũ, test, sổ chưa ghi) thì mọi người 0 và luật trở về đúng như cũ. Người mất pin vẫn đi qua
`allocator.choose()` như trước - thứ đã tránh người cùng chương sẵn.
"""
import io
import sys
from pathlib import Path

root = Path(sys.argv[1])
p = root / "ebook_reader" / "character_registry.py"
s = io.open(p, encoding="utf-8").read()


def replace_once(old: str, new: str) -> None:
    global s
    assert s.count(old) == 1, f"khong khop mot lan duy nhat: {old.splitlines()[0]!r}"
    s = s.replace(old, new, 1)


replace_once('''def _drop_pins_that_share_a_chapter(
    rows: list[Any],
    locked_voices: dict[str, str],
    log: Any,
) -> dict[str, str]:''', '''def _book_exposure(db: Any) -> dict[str, int]:
    """Số câu cộng dồn qua cả chuỗi lô, theo `canonical_key` - sổ `character_exposure`.

    Sổ do `scripts/backfill_exposure.py` ghi vào project trước mỗi lô; project không có sổ (cũ, test,
    một bản sao) trả rỗng, và mọi phép xếp hạng dùng nó trở về như khi chưa có nó.
    """
    try:
        with db.connect() as conn:
            rows = conn.execute("SELECT canonical_name, dialogue_lines FROM character_exposure").fetchall()
    except Exception:  # noqa: BLE001 - bảng vắng, db giả trong test: không có sổ thì không xếp theo sổ
        return {}
    exposure: dict[str, int] = {}
    for name, lines in rows:
        key = canonical_key(str(name))
        exposure[key] = max(exposure.get(key, 0), int(lines or 0))
    return exposure


def _drop_pins_that_share_a_chapter(
    rows: list[Any],
    locked_voices: dict[str, str],
    log: Any,
    exposure: dict[str, int] | None = None,
) -> dict[str, str]:''')
replace_once('''    Ai giữ: người **nhiều câu hơn trong cả lô** - đổi giọng của họ gây chú ý hơn. Người kia mất
    pin và đi qua `allocator.choose()`, thứ đã tránh người cùng chương sẵn.
    """''', '''    Ai giữ: người **quen hơn trên cả cuốn** - số câu cộng dồn qua chuỗi lô (`exposure`, sổ
    `character_exposure`), rồi mới tới số câu trong lô. Bản trước xếp theo số câu trong lô, và lô 8 cuốn 2
    (19-09) bỏ pin của VICTOR - 329 câu qua 18 lô, 64 chương một giọng - vì MORRIS (54 câu cả cuốn) nói
    nhiều hơn trong riêng lô ấy; VICTOR đổi giọng ở 4 chương. Không có sổ thì như cũ. Người kia mất pin và
    đi qua `allocator.choose()`, thứ đã tránh người cùng chương sẵn.
    """
    exposure = exposure or {}''')
replace_once('''        # Người nhiều câu trước; ai đã giữ thì người sau chỉ mất pin nếu CHẠM chương của họ.
        ranked = sorted(identities, key=lambda name: (-lines.get(name, 0), name))''', '''        # Người quen hơn trên cả cuốn trước, rồi người nhiều câu trong lô; ai đã giữ thì người sau chỉ
        # mất pin nếu CHẠM chương của họ.
        ranked = sorted(
            identities,
            key=lambda name: (-exposure.get(name, 0), -lines.get(name, 0), name),
        )''')
replace_once('''            log(
                f"Bỏ giọng đã ghim của {identity} ({lines.get(identity, 0)} câu): trùng "
                f"{voice} với {clash} ({lines.get(clash, 0)} câu) ở chương {shared}. "''', '''            log(
                f"Bỏ giọng đã ghim của {identity} ({lines.get(identity, 0)} câu, "
                f"{exposure.get(identity, 0)} cả cuốn): trùng {voice} với {clash} "
                f"({lines.get(clash, 0)} câu, {exposure.get(clash, 0)} cả cuốn) ở chương {shared}. "''')
replace_once('''    locked_voices = _drop_pins_that_share_a_chapter(rows, locked_voices, log)''', '''    locked_voices = _drop_pins_that_share_a_chapter(
        rows, locked_voices, log, exposure=_book_exposure(db)
    )''')
io.open(p, "w", encoding="utf-8").write(s)
print(f"da va {p}")

test = root / "tests" / "test_the_better_known_voice_keeps_its_pin.py"
test.write_text('''"""Hai người cùng ghim một giọng gặp nhau: người quen hơn TRÊN CẢ CUỐN giữ giọng (lô 8, VICTOR/MORRIS)."""
from __future__ import annotations

import sqlite3
from pathlib import Path

from ebook_reader.character_registry import _book_exposure, _drop_pins_that_share_a_chapter

VOICE = "preset_thai_son_f100_p+00"


def _rows() -> list[dict]:
    # Lô 8, chương 18 của project: VICTOR 1 câu, MORRIS 3 câu, cùng chương, cùng giọng đã ghim.
    return [
        {"speaker": "VICTOR", "chapter_id": 18},
        {"speaker": "MORRIS", "chapter_id": 18},
        {"speaker": "MORRIS", "chapter_id": 18},
        {"speaker": "MORRIS", "chapter_id": 19},
    ]


def test_without_a_ledger_the_one_with_more_lines_in_the_batch_keeps_it() -> None:
    kept = _drop_pins_that_share_a_chapter(_rows(), {"VICTOR": VOICE, "MORRIS": VOICE}, lambda _m: None)
    assert kept == {"MORRIS": VOICE}


def test_with_the_ledger_the_better_known_person_keeps_it() -> None:
    said: list[str] = []
    kept = _drop_pins_that_share_a_chapter(
        _rows(), {"VICTOR": VOICE, "MORRIS": VOICE}, said.append, exposure={"VICTOR": 329, "MORRIS": 54}
    )
    assert kept == {"VICTOR": VOICE}
    assert said and "MORRIS" in said[0] and "54 cả cuốn" in said[0] and "329 cả cuốn" in said[0]


class _DB:
    def __init__(self, path: Path) -> None:
        self.path = path

    def connect(self):
        return sqlite3.connect(self.path)


def test_the_ledger_is_read_by_canonical_key_and_is_optional(tmp_path: Path) -> None:
    database = tmp_path / "project.sqlite3"
    connection = sqlite3.connect(database)
    connection.execute("CREATE TABLE character_exposure (canonical_name TEXT, dialogue_lines INT, batches INT)")
    connection.executemany("INSERT INTO character_exposure VALUES (?, ?, ?)", [("Victor", 329, 18), ("MORRIS", 54, 5)])
    connection.commit()
    connection.close()

    assert _book_exposure(_DB(database)) == {"VICTOR": 329, "MORRIS": 54}
    assert _book_exposure(_DB(tmp_path / "empty.sqlite3")) == {}
    assert _book_exposure(object()) == {}
''', encoding="utf-8")
print(f"da viet {test}")
