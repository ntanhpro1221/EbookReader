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
nào. Nó **thêm** pin cho người chưa có, và từ 21:00 ngày 2026-09-15 nó còn **sửa** một pin đã trôi
khỏi cuốn sách — nhưng chỉ trong một khe rất hẹp, xem `pins_that_drifted`. Câu viết ở đây trước
đó ("không bao giờ đè lên quyết định của `port_casting`") đã phải trả giá: một lần bỏ pin cục bộ
ở bước 4 ranh giới trôi xuống cả chuỗi và làm CHRISTOPHER đổi giọng ở chương 114, nơi không có
va chạm nào. Và lo ngại "cli cast biết điều script này không biết" thì không áp cho cột này:
`locked_voice_key` chỉ có hai chỗ ghi trong cả cây, `port_casting.py` và chính script này; người
nghe nói bằng `listener_audio_acceptances` và các khoá phái/tuổi.

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
from collections.abc import Callable
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ebook_reader.database import ProjectDB  # noqa: E402
from scripts.book_paths import TAG_PREFIX  # noqa: E402
from scripts.voice_matches_the_person import BOOK, VERSIONS, fold_names, shipped_rows  # noqa: E402


def _say(line: str) -> None:
    try:
        print(line)
    except (UnicodeEncodeError, OSError, ValueError):
        sys.stdout.buffer.write(line.encode("utf-8", "replace") + b"\n")


def chapters_by_voice(rows: list[dict]) -> dict[str, dict[str, set[str]]]:
    """{tên: {giọng: {chương}}} theo cuốn sách đã ghép.

    Bỏ NPC theo chương và người vô danh: NPC chỉ sống một chương nên ghim giọng cho nó là ghim
    một cái tên sẽ không bao giờ xuất hiện lại.
    """
    chapters: dict[str, dict[str, set[str]]] = collections.defaultdict(
        lambda: collections.defaultdict(set)
    )
    for row in rows:
        name = str(row["name"])
        if name.startswith("NPC_LOCAL::") or name.upper().startswith("ANONYMOUS"):
            continue
        chapters[name][str(row["voice"])].add(str(row["chapter"]))
    return {name: dict(voices) for name, voices in chapters.items()}


def majority_voices(rows: list[dict]) -> dict[str, tuple[str, int, int]]:
    """{tên: (giọng đa số, số chương giọng ấy, tổng số chương)}.

    Đa số = giọng có nhiều chương nhất; hoà thì giọng đứng trước theo bảng chữ, để hai lần chạy
    cho cùng một câu trả lời.
    """
    out: dict[str, tuple[str, int, int]] = {}
    for name, voices in chapters_by_voice(rows).items():
        voice, where = sorted(voices.items(), key=lambda kv: (-len(kv[1]), kv[0]))[0]
        out[name] = (voice, len(where), sum(len(c) for c in voices.values()))
    return out


def project_chapters(target: Path) -> set[str]:
    """Số chương của chính project này - có ngay sau `create`, trước khi phân tích chạy."""
    database = target / "project.sqlite3"
    if not database.is_file():
        return set()
    connection = sqlite3.connect(f"file:{database.as_posix()}?mode=ro", uri=True)
    try:
        return {str(row[0]) for row in connection.execute("SELECT title FROM chapters")}
    except sqlite3.Error:
        return set()
    finally:
        connection.close()


def pins_that_drifted(
    pins: dict[str, str],
    rows: list[dict],
    scope: set[str],
    *,
    canonical: Callable[[str], str],
    min_chapters: int = 2,
) -> tuple[dict[str, tuple[str, str, int, int]], list[str]]:
    """Pin nào đang trái với cuốn sách, và sửa lại được mà không gây va chạm trong lô này?

    Trả `{tên: (giọng đang ghim, giọng đa số, số chương của pin, số chương của đa số)}` và một
    danh sách dòng để log.

    ## Vì sao cần, đo 21:00 ngày 2026-09-15 trên sách 139 chương

    Một lần bỏ pin **cục bộ một chương** biến thành danh tính mới cho cả chuỗi. Bước 4 của ranh
    giới 3 đúc lại chương 110 và bản vá `patch_two_pins_do_not_share_a_chapter` bỏ pin của
    CHRISTOPHER ở đó (2 câu, gặp VERDI 5 câu trên cùng giọng `thanh_binh_f090`) — đúng doanh
    nghĩa. Nhưng `port_casting` mang giọng mới ấy (`thai_son_f104`) xuống project kế tiếp trong
    chuỗi như **pin**, và script này thì không bao giờ xét lại một pin đã có, nên:

        VERDI        10 chương, TẤT CẢ thanh_binh_f090      (nhất quán tuyệt đối)
        CHRISTOPHER   9 chương: f090 ở 6 chương / f104 ở 110, 112, 114

    Hai người chỉ gặp nhau ở **110 và 112**. Chương **114 đổi giọng mà không mua được gì** —
    VERDI không nói ở đó. Cùng cơ chế ấy đánh cả người chưa từng được ghim: SHARON mang pin
    `ngoc_linh_f087` trong khi đa số trên sách của cô là `truc_ly_f100` (4 chương), vì giọng bị
    rút thăm lại ở một project đúc lại rồi trôi xuống theo chuỗi.

    ## Điều kiện, hẹp có chủ ý

    Chỉ sửa khi **cuốn sách** nói rõ pin đang sai và việc sửa **không thể** gây va chạm cùng
    chương trong lô này:

    1. giọng đang ghim có **ít chương hơn hẳn** giọng đa số của chính người ấy (hoà thì giữ, để
       hai lần chạy cho cùng một câu trả lời);
    2. người ấy có ít nhất `min_chapters` chương trên sách - dưới thế thì không có gì để nhất quán;
    3. nếu giọng đa số đang có chủ ghim khác, thì chủ ấy và người này **không cùng chương nào
       nằm trong lô này** (`scope`). Ở project đúc lại chương 114, `scope = {114}` và VERDI không
       nói ở 114, nên sửa được; ở project 110 thì `scope = {110}` và họ gặp nhau ở đó, nên
       không sửa - pin `f104` ở lại đúng chỗ nó sinh ra.

    `locked_voice_key` **không** phải lựa chọn của người nghe: cả cây chỉ có hai chỗ ghi nó,
    `port_casting.py` và chính script này (`database.set_locked_character_voice`, một chỗ ghi
    duy nhất trong `database.py`). Người nghe nói bằng `listener_audio_acceptances` và các khoá
    phái/tuổi. Nên sửa một pin đã trôi không đè lên quyết định của ai cả.
    """
    by_voice = chapters_by_voice(rows)
    chapters_of_key: dict[str, set[str]] = collections.defaultdict(set)
    for name, voices in by_voice.items():
        for where in voices.values():
            chapters_of_key[canonical(name)] |= where
    owner_of: dict[str, str] = {voice: name for name, voice in pins.items()}

    drifted: dict[str, tuple[str, str, int, int]] = {}
    notes: list[str] = []
    for name, voices in sorted(by_voice.items()):
        key = canonical(name)
        current = pins.get(key)
        if current is None:
            continue
        total = sum(len(where) for where in voices.values())
        if total < int(min_chapters):
            continue
        best_voice, best_where = sorted(voices.items(), key=lambda kv: (-len(kv[1]), kv[0]))[0]
        if best_voice == current:
            continue
        here = len(voices.get(current, ()))
        if here >= len(best_where):
            continue
        holder = owner_of.get(best_voice)
        if holder is not None and holder != key:
            shared = chapters_of_key[key] & chapters_of_key.get(holder, set())
            if shared & scope:
                notes.append(
                    f"{name} vẫn giữ {current.replace('preset_', '')} ({here} chương):"
                    f" {holder} đang giữ {best_voice.replace('preset_', '')} và cùng chương"
                    f" {sorted(shared & scope)} trong lô này"
                )
                continue
        drifted[name] = (current, best_voice, here, len(best_where))
        holder_note = f"; {holder} cũng giữ nó nhưng không cùng chương trong lô này" if holder else ""
        notes.append(
            f"{name}: {current.replace('preset_', '')} ({here} chương)"
            f" -> {best_voice.replace('preset_', '')} ({len(best_where)} chương){holder_note}"
        )
    return drifted, notes


def resolve_collisions(
    wanted: dict[str, tuple[str, int, int]],
    owned: dict[str, str] | None = None,
    chapters_of: dict[str, set[str]] | None = None,
) -> tuple[dict[str, tuple[str, int, int]], list[str]]:
    """Ai được ghim, sau khi tôn trọng pin ĐÃ CÓ rồi mới xử va chạm giữa các đề nghị mới.

    Thứ tự quan trọng, và bản đầu của hàm này làm sai: nó xử va chạm giữa **mọi** giọng đa số
    trước, rồi mới lọc người đã có pin — nên nó "cho" KANG (13 chương) cái slot mà BOWDEN (6
    chương) **đang giữ pin**, và báo BOWDEN là người nhường. Ngược hẳn: một pin đã có là quyết
    định của `port_casting` hoặc của người nghe, và script này không có quyền lật.

    `owned` = {giọng: người đang giữ pin}. Còn lại mới so với nhau: người nhiều chương hơn giữ,
    người kia để allocator cấp giọng mới — nó biết bậc nào còn trống trong lô ấy, còn script này
    không.

    **Một giọng được phép có hai người ghim, nếu hai người ấy chưa từng cùng chương.** Bản trước
    bỏ *mọi* đề nghị rơi vào giọng đã có chủ, và đo 10:55 ngày 2026-09-15 trên lô 3 cuốn 2 thì
    nó bỏ **tất cả**: `0 người sẽ được ghim`, 21 lời "slot đã thuộc …". Hệ quả là đúng cái vòng
    đã làm cuốn 1 đắt dần — người không pin bị rút thăm lại giọng mỗi lô, và số người mang hơn
    một giọng qua cả sách đi 11 → 15 → 21.

    Nhưng "một giọng một người" **không phải** luật của dự án: bộ cấp giọng vẫn cho nhiều người
    dùng chung một bậc, và thứ nó cấm là hai người **cùng chương** dùng một giọng
    (`_first_free_variant` → `shared_chapters`). Pin phải theo đúng luật ấy, không nghiêm hơn:
    nghiêm hơn không cứu người nghe khỏi điều gì, mà đổi lấy việc giọng của một nhân vật phụ
    nhảy mỗi lô.

    `chapters_of` = {tên: {chương}} theo sách đã ghép. Không có nó thì hành vi lùi về đúng như
    cũ (coi như ai cũng có thể gặp nhau) — chỗ gọi cũ không đổi gì.
    """
    owned = owned or {}
    known_chapters = chapters_of or {}

    def _never_meet(left: str, right: str) -> bool:
        here, there = known_chapters.get(left), known_chapters.get(right)
        if not here or not there:
            return False
        return not (here & there)

    kept: dict[str, tuple[str, int, int]] = {}
    dropped: list[str] = []
    free: dict[str, tuple[str, int, int]] = {}
    for name, detail in wanted.items():
        holder = owned.get(detail[0])
        if holder is not None and holder != name:
            if _never_meet(name, holder):
                kept[name] = detail
                dropped.append(
                    f"{name} ({detail[2]} chương) chia {detail[0].replace('preset_', '')}"
                    f" với {holder} - chưa từng cùng chương"
                )
            else:
                dropped.append(
                    f"{name} ({detail[2]} chương) không ghim được"
                    f" {detail[0].replace('preset_', '')}: {holder} đang giữ và có cùng chương"
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
        holders = [ranked[0]]
        for loser in ranked[1:]:
            if all(_never_meet(loser, holder) for holder in holders):
                kept[loser] = free[loser]
                holders.append(loser)
                dropped.append(
                    f"{loser} ({free[loser][2]} chương) chia {voice.replace('preset_', '')}"
                    f" với {', '.join(holders[:-1])} - chưa từng cùng chương"
                )
                continue
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
    for db in sorted(versions.glob(f"{TAG_PREFIX}-lo*/*/project.sqlite3")):
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


def pin(
    target: Path,
    *,
    apply: bool,
    book: Path = BOOK,
    versions: Path = VERSIONS,
    min_chapters: int = 2,
) -> int:
    """Ghim giọng đa số cho người chưa có pin. Trả về số người được ghim (hoặc sẽ được ghim).

    `min_chapters` = 2: chỉ ghim người **người nghe có thể nhận ra là đổi giọng**. Đo 11:05 ngày
    2026-09-15 trên sách 98 chương của cuốn 2: ngưỡng 1 đề nghị 68 người và ghim được 66, nhưng
    35 trong số ấy chỉ nói trong **một** chương — ghim họ không cứu ai khỏi điều gì (không có
    chương thứ hai để so), mà mỗi pin là một lần chia giọng, tức một khả năng va chạm cùng
    chương ở 817 chương còn lại. Ngưỡng 2 ghim 31 người và phủ **cả 10** người đang mang hai
    giọng (EVANS và DURAGO đúng 2 chương, tám người kia 4–6).

    Đổi lấy gì: mọi pin ở đây đều **dùng chung** một giọng với người đã ghim (kho giọng của sách
    đã được ghim hết), nên cái giá là một va chạm cùng chương nếu hai người ấy gặp nhau ở một
    chương sau - bước 4 ranh giới tự đúc lại chương đó, ~12 phút GPU một ca. Cái mua được: một
    nhân vật phụ quay lại sau mười chương không còn đổi giọng.
    """
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

    # Trước khi lấp chỗ trống: sửa những pin đã TRÔI khỏi cuốn sách. Xem `pins_that_drifted` cho
    # phép đo và ba điều kiện; nó chỉ sửa khi sách nói rõ pin sai và việc sửa không thể gây va
    # chạm cùng chương trong lô này.
    scope = project_chapters(target)
    drifted, drift_notes = pins_that_drifted(
        pins, rows, scope, canonical=canonical_key, min_chapters=min_chapters
    )
    for line in drift_notes:
        _say(f"  PIN TRÔI {line}")
    fixed = 0
    for name, (current, wanted_voice, _here, _there) in sorted(drifted.items()):
        profile = voice_profile(wanted_voice, versions)
        if profile is None:
            _say(f"  BỎ QUA {name}: không tìm thấy hàng voice_profiles cho {wanted_voice}")
            continue
        fixed += 1
        key = canonical_key(name)
        pins[key] = wanted_voice
        if owned.get(current) == key:
            owned.pop(current, None)
        owned.setdefault(wanted_voice, key)
        if not apply:
            continue
        database.upsert_voice_profile(
            {
                "voice_key": wanted_voice,
                "engine": profile["engine"],
                "preset_name": profile["preset_name"],
                "description": profile["description"],
                "seed": profile["seed"],
                "pitch_semitones": profile["pitch_semitones"],
                "formant_ratio": profile["formant_ratio"],
                "status": "ready",
            }
        )
        database.set_locked_character_voice(name, wanted_voice)
    if fixed:
        _say(f"  {fixed} pin {'đã được sửa' if apply else 'sẽ được sửa'} về giọng đa số của sách.")

    majority = majority_voices(rows)
    unpinned = {
        name: detail
        for name, detail in majority.items()
        if canonical_key(name) not in pins and detail[2] >= int(min_chapters)
    }
    # Ai có mặt ở chương nào, theo sách đã ghép: đó là bằng chứng cho phép hai người ghim cùng
    # một giọng mà người nghe không lẫn. Cùng nguồn với `majority_voices`, nên không lệch nhau.
    chapters_of: dict[str, set[str]] = collections.defaultdict(set)
    for row in rows:
        chapters_of[str(row["name"])].add(str(row["chapter"]))
    todo, dropped = resolve_collisions(unpinned, owned, dict(chapters_of))
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
    parser.add_argument(
        "--min-chapters",
        type=int,
        default=2,
        help="chỉ ghim người nói ở ít nhất bấy nhiêu chương (mặc định 2 - xem docstring của pin())",
    )
    args = parser.parse_args(argv)
    target = args.project.expanduser().resolve()
    if not (target / "project.sqlite3").is_file():
        _say(f"không phải project: {target}")
        return 2
    from ebook_reader.background_runner import get_status

    if get_status(target).running:
        _say(f"{target.name} đang chạy - ghim giọng lúc này là đổi dàn giọng giữa lượt. Dừng.")
        return 3
    pin(target, apply=args.apply, min_chapters=args.min_chapters)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
