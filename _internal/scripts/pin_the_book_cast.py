"""Ghim giọng cho MỌI người đã nói trong sách, không chỉ những người nói trong project gieo.

    python scripts/pin_the_book_cast.py <project đích>            # thử, không ghi
    python scripts/pin_the_book_cast.py <project đích> --apply    # ghim thật

Chạy **sau** `port_casting.py` và **trước** `cli run` của một lô mới. `port_casting` mang quyết
định của **chuỗi gieo** đi; script này lấp chỗ chuỗi ấy bỏ quên, và nguồn của nó là **cuốn sách
đã ghép** — thứ người nghe thật sự đang nghe.

Vì sao cần: đo 03:25 ngày 2026-09-12 trên lô 5, ngay sau khi nó khoá dàn giọng.

    61  tên đã nói trong sách (118 chương)
    38  được ghim giọng trong lô 5
    26  KHÔNG được ghim — mỗi lô sau là một lần rút thăm lại giọng của họ

KANG dẫn đầu danh sách bị bỏ quên: **13 chương, 41 câu, không pin**. Rồi LYLE (3 chương), IVAN
(3), ROB (3), SAMAELE (3), VIKTOR (2 chương nhưng 18 câu), REXERD (13 câu).

Hai lỗ tạo ra nó, và cả hai đều nằm ở chỗ `port_casting` chỉ nhìn **một** project:

1. Một người không nói trong project gieo thì không có gì để mang đi. Project gieo thường là
   một project đúc lại **một chương** (luật gieo: lấy project cuối chuỗi), nên gần như ai cũng
   im lặng ở đó. Người đã được ghim từ trước thì vẫn đi tiếp (`PINNED_SQL`), nhưng người chưa
   từng được ghim thì không bao giờ bắt đầu — vì allocator **không** viết pin, chỉ
   `port_casting` và `cli cast` viết.
2. Luật va chạm bỏ pin của người ít lời hơn. Đúng cho một lần chuyển, nhưng người bị bỏ không
   được ghim lại ở lô sau, nên một lần thua là mất pin **mãi mãi**. KANG thua SAMAEL ở bậc
   `f093` (152 câu so với 41 — thua đúng), và từ đó không lô nào ghim anh ta nữa.

Script này trả lời bằng một nguồn khác: **giọng đa số của người ấy trên cả cuốn sách**. Đó là
thứ người nghe đã nghe nhiều nhất, và nó không phụ thuộc vào việc ai tình cờ nói trong project
nào. Nó chỉ **thêm** pin cho người chưa có; không bao giờ đè lên quyết định của `port_casting`
hay `cli cast`, vì hai đường ấy biết những điều script này không biết (người nghe vừa chọn, hay
lô vừa đúc lại).

**Trên dữ liệu hôm nay nó ghim được ĐÚNG 0 người, và đó là câu trả lời chứ không phải lỗi.**
Lượt thử 04:15 ngày 2026-09-12 trên bản sao lô 5: cả 26 người bị bỏ quên đều có giọng đa số
**đã thuộc về một người đang giữ pin** — ROB và JONES và MARK muốn `thanh_binh_f100_p-04` mà
BOWDEN giữ; LYLE và VICTOR và CHUA TÔ muốn `thai_son_f100_p+00` mà VALE giữ; IVAN muốn
`ngoc_linh_f107_p+02` mà EVERAN giữ. Đếm slot: **nam 14/14 đã có chủ, trống 0**; nữ 21/27, trống
6 (tất cả trên Thục Đoan, preset bị giáng cấp nên không ai dùng).

Nên script này hôm nay chỉ để **ghi lại một sự thật**: người bị bỏ quên không lấy lại được giọng
cũ của mình, vì giọng ấy giờ là của người khác. Nó sẽ ghim được thật vào ngày một slot trống ra
(một pin bị bỏ, hoặc pool rộng thêm), và lúc ấy nó ghim đúng người đúng giọng mà không cần ai nhớ.

Việc đáng làm hơn, đã ghi ở `docs/OPTIMISATION_QUEUE.md`: **xếp hạng pin theo mức người nghe đã
nghe.** 8 trong 16 pin nam đang do người **1–2 chương** giữ (IGOR 1 chương/3 câu giữ
`thanh_binh_f090_p-04`, VALE 1 chương giữ `thai_son_f100_p+00`, REICHARDT, DORON STORMWATCH,
SAM, JAY, ARTHUR, ĐẠI TƯ TẾ), trong khi 5 người **3–13 chương** không có pin nào: KANG (13),
SAMAELE, IVAN, ROB, LYLE (3 mỗi người). Đó là đúng thứ tự ngược.
"""
from __future__ import annotations

import argparse
import collections
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ebook_reader.database import ProjectDB  # noqa: E402
from scripts.voice_matches_the_person import BOOK, VERSIONS, fold_names, shipped_rows  # noqa: E402


def _say(line: str) -> None:
    try:
        print(line)
    except (UnicodeEncodeError, OSError, ValueError):
        sys.stdout.buffer.write(line.encode("utf-8", "replace") + b"\n")


def majority_voices(rows: list[dict]) -> dict[str, tuple[str, int, int]]:
    """{tên: (giọng đa số, số chương giọng ấy, tổng số chương)}.

    Đa số = giọng có nhiều chương nhất; hoà thì giọng đứng trước theo bảng chữ, để hai lần chạy
    cho cùng một câu trả lời. Bỏ NPC theo chương và người vô danh: NPC chỉ sống một chương nên
    ghim giọng cho nó là ghim một cái tên sẽ không bao giờ xuất hiện lại.
    """
    chapters: dict[str, dict[str, set[str]]] = collections.defaultdict(
        lambda: collections.defaultdict(set)
    )
    for row in rows:
        name = str(row["name"])
        if name.startswith("NPC_LOCAL::") or name.upper().startswith("ANONYMOUS"):
            continue
        chapters[name][str(row["voice"])].add(str(row["chapter"]))
    out: dict[str, tuple[str, int, int]] = {}
    for name, voices in chapters.items():
        voice, where = sorted(voices.items(), key=lambda kv: (-len(kv[1]), kv[0]))[0]
        out[name] = (voice, len(where), sum(len(c) for c in voices.values()))
    return out


def resolve_collisions(
    wanted: dict[str, tuple[str, int, int]],
    owned: dict[str, str] | None = None,
) -> tuple[dict[str, tuple[str, int, int]], list[str]]:
    """Ai được ghim, sau khi tôn trọng pin ĐÃ CÓ rồi mới xử va chạm giữa các đề nghị mới.

    Thứ tự quan trọng, và bản đầu của hàm này làm sai: nó xử va chạm giữa **mọi** giọng đa số
    trước, rồi mới lọc người đã có pin — nên nó "cho" KANG (13 chương) cái slot mà BOWDEN (6
    chương) **đang giữ pin**, và báo BOWDEN là người nhường. Ngược hẳn: một pin đã có là quyết
    định của `port_casting` hoặc của người nghe, và script này không có quyền lật.

    `owned` = {giọng: người đang giữ pin}. Đề nghị nào rơi vào giọng đã có chủ thì bỏ, nói ra.
    Còn lại mới so với nhau: người nhiều chương hơn giữ, người kia để allocator cấp giọng mới —
    nó biết bậc nào còn trống trong lô ấy, còn script này không.
    """
    owned = owned or {}
    kept: dict[str, tuple[str, int, int]] = {}
    dropped: list[str] = []
    free: dict[str, tuple[str, int, int]] = {}
    for name, detail in wanted.items():
        holder = owned.get(detail[0])
        if holder is not None and holder != name:
            dropped.append(
                f"{name} ({detail[2]} chương) không ghim được"
                f" {detail[0].replace('preset_', '')}: slot đã thuộc {holder}"
            )
            continue
        free[name] = detail
    by_voice: dict[str, list[str]] = collections.defaultdict(list)
    for name, (voice, _here, _total) in free.items():
        by_voice[voice].append(name)
    for voice, names in by_voice.items():
        if len(names) == 1:
            kept[names[0]] = free[names[0]]
            continue
        ranked = sorted(names, key=lambda n: (-free[n][2], -free[n][1], n))
        kept[ranked[0]] = free[ranked[0]]
        for loser in ranked[1:]:
            dropped.append(
                f"{loser} ({free[loser][2]} chương) nhường {voice.replace('preset_', '')}"
                f" cho {ranked[0]} ({free[ranked[0]][2]} chương)"
            )
    return kept, dropped


def voice_profile(voice_key: str, versions: Path = VERSIONS) -> dict | None:
    """Hàng `voice_profiles` của một `voice_key`, tìm trong các project của sách.

    Cần cả preset, seed, pitch và formant: `voice_key` mã hoá ba thứ nhưng `seed` thì không, và
    `seed` là thứ quyết định giọng nghe ra sao ở cùng một preset.
    """
    for db in sorted(versions.glob("v0.2.0-lo0*/*/project.sqlite3")):
        try:
            conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM voice_profiles WHERE voice_key=?", (str(voice_key),)
            ).fetchone()
            conn.close()
        except sqlite3.Error:
            continue
        if row is not None:
            return {key: row[key] for key in row.keys()}
    return None


def pin(target: Path, *, apply: bool, book: Path = BOOK, versions: Path = VERSIONS) -> int:
    """Ghim giọng đa số cho người chưa có pin. Trả về số người được ghim (hoặc sẽ được ghim)."""
    rows = fold_names(shipped_rows(book=book, versions=versions))
    if not rows:
        _say("không đọc được cuốn sách đã ghép - không có gì để ghim")
        return 0
    database = ProjectDB(target / "project.sqlite3")
    pins = database.locked_character_voices()
    from ebook_reader.character_registry import canonical_key

    # Pin đã có thắng trước: {giọng: người giữ}. Phải khoá tên theo đúng `canonical_key` vì
    # `locked_character_voices` khoá như thế, còn tên từ cuốn sách thì chưa.
    owned = {voice: name for name, voice in pins.items()}
    majority = majority_voices(rows)
    unpinned = {
        name: detail for name, detail in majority.items() if canonical_key(name) not in pins
    }
    todo, dropped = resolve_collisions(unpinned, owned)
    _say(
        f"sách có {len(majority)} người có giọng đa số; {len(pins)} đã được ghim trong"
        f" {target.name}; {len(unpinned)} chưa; ghim được {len(todo)}."
    )
    for line in dropped:
        _say(f"  VA CHẠM {line}")
    pinned = 0
    for name, (voice, here, total) in sorted(todo.items(), key=lambda kv: -kv[1][2]):
        profile = voice_profile(voice, versions)
        if profile is None:
            _say(f"  BỎ QUA {name}: không tìm thấy hàng voice_profiles cho {voice}")
            continue
        _say(f"  GHIM  {name:22s} -> {voice.replace('preset_', ''):28s} ({here}/{total} chương)")
        pinned += 1
        if not apply:
            continue
        database.upsert_voice_profile(
            {
                "voice_key": voice,
                "engine": profile["engine"],
                "preset_name": profile["preset_name"],
                "description": profile["description"],
                "seed": profile["seed"],
                "pitch_semitones": profile["pitch_semitones"],
                "formant_ratio": profile["formant_ratio"],
                "status": "ready",
            }
        )
        database.set_locked_character_voice(name, voice)
    _say("")
    _say(f"{pinned} người {'đã được ghim' if apply else 'sẽ được ghim'} vào {target.name}.")
    if not apply:
        _say("Lượt thử, chưa ghi gì. Thêm --apply để ghim.")
    return pinned


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("project", type=Path)
    parser.add_argument("--apply", action="store_true", help="ghim thật (mặc định chỉ liệt kê)")
    args = parser.parse_args(argv)
    target = args.project.expanduser().resolve()
    if not (target / "project.sqlite3").is_file():
        _say(f"không phải project: {target}")
        return 2
    from ebook_reader.background_runner import get_status

    if get_status(target).running:
        _say(f"{target.name} đang chạy - ghim giọng lúc này là đổi dàn giọng giữa lượt. Dừng.")
        return 3
    pin(target, apply=args.apply)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
