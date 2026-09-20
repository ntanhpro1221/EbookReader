"""Carry a book's voice casting into the next version, before it starts.

`port_pronunciations.py` carries how names are read and `seed_listener_acceptances.py`
carries what a listener ruled. Casting had no equivalent, and that gap costs two things.

**It makes batching unsafe.** Every project analyses and casts from scratch, and the
allocator ranks on `usage[name]` - it depends on the character set that project happens to
see. Split a book into batches and the same character can get one voice in chapter 40 and
another in chapter 60. Measured on alpha.52: one label changing its name string, same room
id, moved a segment from voice 16 to voice 14.

**And it makes a casting decision unrepeatable.** alpha.52 lost chapter 6 because voice 14
cannot say "Mẹ kiếp" while voice 16 can, and there was no way to pin voice 16 back: `cast`
only changes gender, and the gender was already right.

    python scripts/port_casting.py <project nguồn> <project đích> [--dry-run]

Copies the voice profiles themselves as well as the mapping, because a pinned `voice_key`
has to resolve to a real profile in the target. The profiles are deterministic - preset,
formant ratio and pitch decide the key and the seed - so copying them reproduces the sound
rather than approximating it.

Run it between `create` and `run`, next to the other two.
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ebook_reader.database import ProjectDB  # noqa: E402

from scripts.port_listener_acceptances import _say_safely  # noqa: E402
from scripts.name_marks import fold_dropped_marks  # noqa: E402
from scripts.source_spellings import fold_to_source_spelling, source_text  # noqa: E402
from scripts.backfill_exposure import copy_ledger, read_ledger  # noqa: E402


SPOKE_HERE_SQL = """
    SELECT c.canonical_name AS canonical_name, v.*,
           sum(s.kind = 'dialogue') AS lines_here,
           max(c.mention_count) AS mentions_here
    FROM characters c
    JOIN segments s ON s.canonical_character_id = c.id
    JOIN voice_profiles v ON v.id = s.voice_profile_id
    GROUP BY c.id, v.id
    ORDER BY c.canonical_name
"""

PINNED_SQL = """
    SELECT DISTINCT c.canonical_name AS canonical_name, v.*,
           c.mention_count AS mentions_here
    FROM characters c
    JOIN voice_profiles v ON v.voice_key = c.locked_voice_key
    WHERE c.locked_voice_key <> ''
    ORDER BY c.canonical_name
"""


def _fold_names(names: list[str], source: Path, weight: dict[str, int] | None = None) -> dict[str, str]:
    """Gộp tên theo HAI luật, hợp thành: rơi dấu trước, rồi cách viết có trong nguồn.

    Hai luật trả lời hai câu khác nhau và không tranh nhau. Rơi dấu có tín hiệu nội tại (bản
    nhiều dấu hơn thắng) và dùng được cả khi nguồn không chứa chuỗi nào - đúng ca THỦ LÃNH, một
    nhãn Ollama tự đặt. Nguồn văn bản là quan toà cho lớp sai một ký tự, nơi số câu thoại đã bị
    vòng phản hồi làm nhiễm: lô 3 có `SELNE` 32 câu và `SELENE` 7 câu, mà nguồn ghi `Selene` 198
    lần và `Selne` 0 lần - nhân vật thật tên Selene, và luật cũ chọn theo số câu nên chọn sai.

    Hợp thành, không chỉ gộp hai dict: rơi dấu có thể nói A → B rồi nguồn nói B → C, và lúc ấy A
    phải về C chứ không về B.
    """
    by_marks = fold_dropped_marks(names, weight)
    survivors = [name for name in names if name not in by_marks]
    by_source = fold_to_source_spelling(survivors, source_text(source), weight or {})
    folded: dict[str, str] = {}
    for name in names:
        winner = name
        for _ in range(len(names) + 1):
            nxt = by_marks.get(winner) or by_source.get(winner)
            if not nxt or nxt == winner:
                break
            winner = nxt
        if winner != name:
            folded[name] = winner
    return folded


def read_casting(source: Path) -> list[tuple[str, str, dict]]:
    """(canonical_name, voice_key, profile row) for every character with a voice.

    Two queries, because either alone loses characters, in opposite directions.

    Asking only who **spoke in this batch** drops anyone already pinned who happened to be
    silent here. Measured on alpha.56: 38 characters carried a pin, 18 spoke, so 20 were
    dropped - fourteen of them chapter-local NPCs that should go, but five named characters
    that should not, including THEOSBANE, whose reading the owner chose personally.
    THEOSBANE appears in 156 of the book's 478 chapters, so it would simply have been recast
    with a different voice the next time it opened its mouth. That is the casting drift this
    script exists to prevent, arriving one batch later.

    Asking only who is **pinned** drops the other side: the allocator does not write
    locked_voice_key, only this script and the `cast` command do, so a character cast fresh
    in this batch has a voice and no pin. Measured on alpha.55: 15 of the 18 who spoke had no
    pin, ARTHUR among them.

    So both, with the voice actually used this batch winning any disagreement - a pin says
    what was decided, a segment says what was heard, and what was heard is what the listener
    accepted.
    """
    connection = sqlite3.connect(f"file:{source / 'project.sqlite3'}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        try:
            rows = list(connection.execute(SPOKE_HERE_SQL))
        except sqlite3.OperationalError:
            return []
        try:
            rows += list(connection.execute(PINNED_SQL))
        except sqlite3.OperationalError:
            # A project older than the locked_voice_key column has no pins to carry, which
            # is not an error - alpha.54 and earlier are in that state.
            pass
    finally:
        connection.close()
    from collections import Counter

    from ebook_reader.analysis import is_local_speaker

    # Hai cách viết của cùng một tên - THU LÃNH / THỦ LÃNH, NGUOI TRA LOI / NGƯỜI TRẢ LỜI - phải
    # về một tên TRƯỚC khi lọc va chạm, nếu không hai "người" ấy sẽ được coi là hai giọng hợp lệ
    # và mang cả hai sang. Đo lô 3 (2026-09-10): cả hai cặp đều có mặt trong `characters`, và
    # bản rơi dấu là bản nhiều lần hơn. Bản chính của luật này vào registry ở
    # `patch_dropped_marks_are_the_same_name`; đây là bản dùng ngay cho gieo, ghim khớp nhau bằng
    # `tests/test_name_marks_agree.py`.
    folded = _fold_names([str(row["canonical_name"]) for row in rows], source)
    for loser, winner in sorted(folded.items()):
        _say_safely(f"  GỘP   {loser} -> {winner} (cùng một người)")

    candidates: list[tuple[str, str, dict]] = []
    seen: set[str] = set()
    # Số câu thoại mỗi người nói **trong lô nguồn**. Chỉ có ở các dòng từ SPOKE_HERE_SQL; dòng
    # từ PINNED_SQL là người đã ghim mà im lặng ở lô này, và 0 câu là câu trả lời đúng cho họ.
    spoken: dict[str, int] = {}
    # Ai đang **giữ một pin** từ lô trước. Dòng nào không có `lines_here` là dòng từ PINNED_SQL,
    # tức một quyết định đã có sẵn — có thể do chính chủ sách chọn. Nó xếp trên số câu thoại khi
    # phải chọn ai giữ giọng; xem chỗ xử lý va chạm bên dưới.
    pinned: set[str] = set()
    # Bản đầu của chỗ này đọc `mention_count` và giải thích rằng nó "cộng dồn qua các lô". **Sai**:
    # `upsert_character` ghi đè nó bằng số câu của lô hiện tại. Đo 2026-09-10: SAMAEL 10 → 99 →
    # 19, THỦ LÃNH 178 → 111 → 32. Nó chỉ chạy đúng ở ranh giới lô 2 → 3 nhờ may, và ở ranh giới
    # lô 3 → 4 thì KANG (19 câu, mới) HOÀ SAMAEL (19 theo sổ sai, 128 theo sự thật) — chỉ nấc
    # phá hoà cuối cứu được nhân vật chính khỏi mất giọng.
    #
    # Thứ đáng cân là tổng số câu người nghe đã nghe **qua mọi lô**, và cái đó nằm trong sổ
    # `character_exposure` do `backfill_exposure.py` dựng từ cả chuỗi (nó nằm ngoài SCHEMA nên
    # phân tích không bao giờ ghi đè). Không có sổ thì lùi về `mention_count` - vẫn tốt hơn không
    # có gì, nhưng phải nói ra là đang lùi.
    ledger = read_ledger(source)
    if ledger:
        _say_safely(f"  sổ cộng dồn: {len(ledger)} nhân vật")
    else:
        _say_safely("  KHÔNG có sổ cộng dồn - xếp hạng theo mention_count của lô này, thứ bị ghi")
        _say_safely("  đè mỗi lô; chạy scripts/backfill_exposure.py trên cả chuỗi trước khi gieo.")
    mentions: dict[str, int] = {}
    for row in rows:
        keys = row.keys()
        name_here = str(row["canonical_name"])
        if "mentions_here" in keys and row["mentions_here"] is not None:
            mentions[name_here] = max(mentions.get(name_here, 0), int(row["mentions_here"]))
        # Sổ thắng `mention_count` khi có, vì nó là tổng thật; tra theo tên đã gộp rơi dấu.
        target_name = folded.get(name_here, name_here)
        if target_name in ledger:
            mentions[name_here] = max(mentions.get(name_here, 0), int(ledger[target_name]))
        if "lines_here" in keys and row["lines_here"] is not None:
            spoken[name_here] = max(spoken.get(name_here, 0), int(row["lines_here"]))
        else:
            pinned.add(name_here)
    # Dòng bị gộp (tên rơi dấu) xếp SAU dòng nguyên tên, để luật "dòng đầu thắng" bên dưới
    # chọn giọng của cách viết đúng. Không có bước này, `ORDER BY canonical_name` đưa "THU LÃNH"
    # lên trước "THỦ LÃNH" (U xếp trước Ủ) và giọng mà bản rơi dấu vừa được cấp ở lô này thắng
    # giọng đã theo THỦ LÃNH từ lô 1 - đo lô 3: f090_p-04 (mới, chỉ có ở lô 3) sẽ đè lên
    # f100_p-07 (lô 1, lô 2, và 32 câu của lô 3). Cách viết sai là cái bất thường; giọng của
    # nó cũng là giọng bất thường.
    rows = sorted(rows, key=lambda row: str(row["canonical_name"]) in folded)
    for row in rows:
        name = folded.get(str(row["canonical_name"]), str(row["canonical_name"]))
        # A chapter-local NPC is scoped to a chapter of the SOURCE batch; its id names
        # nothing in the target and carrying it only litters the characters table.
        if is_local_speaker(name):
            continue
        # The narrator's voice is the project's SETTING (`voices.narrator_voice`), and casting
        # rebuilds the `narrator` profile from it every run - it is not a person's pin to carry.
        # Carrying it was harmless while every batch had one narrator, because the seeded
        # profile matched the one casting builds. Book 2 changed narrator at chapter 304: batch 7
        # was seeded `NARRATOR -> narrator` (Phạm Tuyên) from lo05r_196, finished analysing 3719
        # lines, and died at casting at 22:41 on 18-09 - "Voice profile narrator is locked and
        # cannot change during resume" - because the locked profile could not become Đức Trí.
        if name.strip().upper() == "NARRATOR":
            continue
        if name in seen:
            # Two voices for one character. The first row wins because the spoke-here query
            # runs first: what was heard outranks what was pinned, since a listener verdict
            # was given on the audio. A genuine two-voice conflict inside one batch is a bug
            # the source project should have caught, and assert_voice_stability reports it.
            continue
        seen.add(name)
        candidates.append((name, str(row["voice_key"]), {key: row[key] for key in row.keys()}))

    # And the mirror case: one voice for two characters. alpha.55 had none of these among its
    # pinned characters; alpha.56 had one, THEOSBANE and SAMAEL both on
    # preset_thanh_binh_f093_p-04 - caused by this very script, in the version that carried
    # only characters who spoke. THEOSBANE was silent through chapters 010-018, so its pin
    # was dropped, and the allocator handed its voice to SAMAEL knowing nothing about it.
    #
    # Carrying both would make that permanent, and picking a winner means deciding which of
    # two characters changes voice on no evidence. So carry neither and say so, which is the
    # same rule this script already applies to a character holding two voices. Both get a
    # fresh non-colliding voice in the target, and the collision ends here instead of
    # propagating to every later batch.
    holders: dict[str, list[str]] = {}
    for name, voice_key, _profile in candidates:
        holders.setdefault(voice_key, []).append(name)
    lines = {name: int(spoken.get(name, 0)) for name, _k, _p in candidates}

    out: list[tuple[str, str, dict]] = []
    for name, voice_key, profile in candidates:
        sharing = holders[voice_key]
        if len(sharing) == 1:
            out.append((name, voice_key, profile))
            continue
        # Người nói nhiều nhất giữ giọng; những người kia được đúc lại.
        #
        # Luật cũ ở đây là **bỏ cả**, với lý do "picking a winner has no evidence". Có bằng
        # chứng: **số câu thoại**. Bỏ cả hai là đổi HAI giọng để chữa MỘT va chạm, còn bỏ người
        # ít lời hơn là đổi một — và đổi đúng cái giọng ít người nghe hơn. Tổng thiệt hại không
        # bao giờ lớn hơn, thường nhỏ hơn hẳn.
        #
        # Đo trên ranh giới lô 1 → lô 2: ba cặp va chạm làm **sáu** nhân vật mất giọng, trong
        # đó có CHA (8 câu, main) và NOAH (8 câu, main). Với luật này chỉ ba người bị đúc lại,
        # và cả ba là người ít lời hơn trong cặp của mình.
        #
        # Luật này chỉ an toàn nhờ `patch_reserve_marks_the_slot`: người thắng giữ giọng, và
        # `reserve()` giờ đánh dấu **đúng bậc formant** ấy, nên người thua chắc chắn được cấp
        # một bậc khác thay vì có thể quay vòng về đúng bậc vừa bị giữ.
        # Thứ tự bằng chứng: **số câu cộng dồn cả sách (sổ) → số câu trong lô này → có pin hay
        # không**. Khi không có sổ, nấc đầu lùi về `mention_count` của lô này.
        #
        # Bản đầu của luật này chỉ so số câu, và `test_two_characters_on_one_voice_are_both_
        # left_behind` bắt ngay: ở ca alpha.56, THEOSBANE im lặng trong lô ấy nên 0 câu, còn
        # SAMAEL nói 1 câu — luật chỉ-đếm-câu-trong-lô trao giọng cho SAMAEL và đúc lại
        # THEOSBANE, đúng lỗ hổng mà `test_the_carry_keeps_a_pin_whose_character_never_spoke`
        # tồn tại để chặn.
        #
        # Bản thứ hai xếp **pin lên trên số câu**, và nó cũng sai, chỉ theo hướng khác: chạy
        # thử trên dữ liệu thật cho `SỐ BA` (phụ, 2 câu) thắng `CHA` (chính, 4 câu) chỉ vì SỐ BA
        # tình cờ giữ pin từ lần chuyển trước. Không có cột nào phân biệt "người ghim" với
        # "script ghim": `locked=1` đánh dấu **giới tính** do người chọn, không phải giọng.
        #
        # Thứ đáng cân là *người nghe đã quen giọng ấy tới mức nào*, và số đo sẵn có gần nhất là
        # `mention_count` — nó cộng dồn qua các lô, nên THEOSBANE (156/478 chương) thắng SAMAEL
        # mà không cần biết ai đang giữ pin, còn CHA thắng SỐ BA vì đúng lý do.
        rank = {
            other: (mentions.get(other, 0), lines.get(other, 0), other in pinned)
            for other in sharing
        }
        best = max(rank.values())
        winners = [other for other in sharing if rank[other] == best]
        if len(winners) > 1:
            # Hoà thì đúng là không có bằng chứng, và lúc ấy luật cũ mới đúng: bỏ cả.
            _say_safely(
                f"  BỎ QUA {name}: giọng {voice_key} bị {', '.join(sorted(sharing))} dùng chung"
                f" và ngang bằng nhau — hoà thì không có căn cứ chọn, bỏ cả để cấp phát chia lại"
            )
            continue
        def _why(who: str) -> str:
            """Nói **thứ đã quyết**, không nói thứ tình cờ đúng.

            Bản đầu ghi "đã ghim" cho bất kỳ ai đang giữ pin, kể cả khi thứ hạng được quyết
            bằng `mention_count` từ trước đó - và pin chỉ là nấc thứ ba. Chạy trên lô 2 nó in
            ra `JAKE (đã ghim) thắng ...` trong khi JAKE thắng vì được nhắc nhiều hơn. Một dòng
            log nói sai lý do gửi người đọc sau đi tìm nhầm chỗ, đúng như hai chỗ cứng hoá tên
            mã trong `pipeline` đã làm.
            """
            counted = (mentions.get(who, 0), lines.get(who, 0))
            rivals = [rank[other] for other in sharing if other != who]
            if all(counted[0] > other[0] for other in rivals):
                return f"được nhắc {counted[0]} lần"
            if all(counted[:2] >= other[:2] for other in rivals) and counted[1] > max(
                (other[1] for other in rivals), default=-1
            ):
                return f"{counted[1]} câu"
            return "đã ghim"

        if name == winners[0]:
            others = sorted(other for other in sharing if other != name)
            _say_safely(
                f"  GIỮ   {name} ({_why(name)}) thắng {voice_key}; đúc lại {', '.join(others)}"
            )
            out.append((name, voice_key, profile))
            continue
        _say_safely(
            f"  BỎ QUA {name} (được nhắc {mentions.get(name, 0)} lần,"
            f" {lines.get(name, 0)} câu): {winners[0]} ({_why(winners[0])}) giữ {voice_key}"
        )
    return out


def read_pinned_characters(source: Path) -> list[dict]:
    """Mọi nhân vật NGƯỜI NGHE đã ghim, kể cả người không nói câu nào trong lô này.

    Cố ý KHÔNG lọc `mention_count > 0`: một ghim là câu trả lời của người nghe, và nó đúng dù người ấy
    im lặng suốt một lô. `read_known_characters` phải lọc (danh sách đưa vào prompt), nhưng dùng chung
    một phép đọc cho cả hai việc thì ghim của ARTHUR DOYLE - `locked=1`, 0 lần nhắc ở lô 10 - biến mất
    ở lô sau.
    """
    connection = sqlite3.connect(f"file:{source / 'project.sqlite3'}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        return [
            dict(row)
            for row in connection.execute(
                """
                SELECT canonical_name, gender, locked, locked_age
                FROM characters
                WHERE locked = 1 OR (locked_age IS NOT NULL AND locked_age <> '')
                ORDER BY canonical_name
                """
            )
        ]
    except sqlite3.OperationalError:
        # Project cũ hơn cột `locked_age`: không có ghim nào mang được, và đó không phải lỗi.
        return []
    finally:
        connection.close()


def read_known_characters(source: Path) -> list[dict]:
    """Every character the source batch established, with what it learnt about them.

    Casting is not the only thing a batch boundary throws away. The analysis prompt carries
    a section headed "Nhân vật đã biết từ các phần trước", built from the characters this
    project has already seen; a fresh batch starts that section empty and the model re-guesses
    a cast it should simply have been told about.

    Measured on this book's own text: from batch two onward, **80% of the proper nouns in a
    batch have already appeared in an earlier one**, and by batch nine it is 95%. So an empty
    known-character list is not a small loss at the seam - it is most of the cast.

    (An earlier measurement of mine said 6%. It compared analysed speaker labels between
    chapters 000-009 and 010-018, which is the least representative window in the book: the
    opening chapters introduce and discard people faster than anywhere else.)
    """
    connection = sqlite3.connect(f"file:{source / 'project.sqlite3'}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        rows = connection.execute(
            """
            SELECT canonical_name, display_name, gender, age, personality, locked, locked_age,
                   importance, mention_count, confidence
            FROM characters
            WHERE mention_count > 0 AND gender IN ('male','female')
            ORDER BY mention_count DESC
            """
        ).fetchall()
    except sqlite3.OperationalError:
        return []
    finally:
        connection.close()
    from ebook_reader.analysis import RESERVED_SPEAKERS, is_local_speaker

    # Gộp cách viết rơi dấu trước khi mang "đã biết" đi, cùng lý do như ở `read_casting`: đây
    # chính là danh sách `_known_summary` đưa vào prompt lô sau, tức chỗ cái sai tự củng cố.
    # Số lần nhắc của bản thua cộng vào bản thắng, để bản thắng không bị xếp dưới.
    folded = _fold_names(
        [str(row["canonical_name"]) for row in rows],
        source,
        {str(row["canonical_name"]): int(row["mention_count"] or 0) for row in rows},
    )
    extra_mentions: dict[str, int] = {}
    for loser, winner in folded.items():
        for row in rows:
            if str(row["canonical_name"]) == loser:
                extra_mentions[winner] = extra_mentions.get(winner, 0) + int(row["mention_count"] or 0)

    # Số câu cộng dồn thật từ sổ, nếu có: đưa vào `mentions` để danh sách "đã biết" của lô sau
    # thấy con số đúng, chứ không thấy số của riêng lô này.
    ledger = read_ledger(source)

    kept = []
    for row in rows:
        name = str(row["canonical_name"])
        if name in folded:
            continue
        # The same two filters _known_summary applies, for the same reasons. NARRATOR and
        # UNKNOWN are roles rather than people. A chapter-local NPC is scoped to a chapter of
        # the SOURCE batch - "NPC_LOCAL::C00001::..." names nothing in the next batch, and
        # carrying it would put a stranger at the top of the prompt.
        if name.casefold() in RESERVED_SPEAKERS or is_local_speaker(name):
            continue
        # ANONYMOUS_MALE and friends are casting buckets, not characters.
        if name.upper().startswith("ANONYMOUS"):
            continue
        record = {key: row[key] for key in row.keys()}
        if name in extra_mentions:
            record["mention_count"] = int(record["mention_count"] or 0) + extra_mentions[name]
        if name in ledger:
            record["mention_count"] = max(int(record["mention_count"] or 0), int(ledger[name]))
        kept.append(record)
    return kept


def carry_listener_pins(source: Path, database: "ProjectDB | None") -> int:
    """Mang MỌI ghim của người nghe sang project mới, kể cả người không nói câu nào trong lô gieo.

    `read_known_characters` lọc `mention_count > 0` - đúng cho danh sách "đã biết" đưa vào prompt, vì một
    cái tên không xuất hiện thì không đáng chiếm chỗ ở đó - nhưng cùng phép lọc ấy làm MẤT GHIM. Đo 20-09
    trên lô 10: ARTHUR DOYLE (`locked=1`, người nghe đã ghim `male`) có `mention_count = 0` vì ông không
    nói câu nào trong lô ấy, nên ghim của ông sẽ biến mất ở lô 11 và mô hình lại được quyền đổi ý. Đó là
    lời hứa "người nghe outrank mô hình vĩnh viễn" bị vỡ, và vỡ IM LẶNG.
    """
    if database is None:
        return 0
    carried = 0
    for pinned in read_pinned_characters(source):
        name = str(pinned["canonical_name"])
        try:
            if int(pinned["locked"] or 0) and str(pinned["gender"]) in ("male", "female"):
                database.lock_character_gender(name, str(pinned["gender"]))
                carried += 1
            if str(pinned["locked_age"] or ""):
                database.lock_character_age(name, str(pinned["locked_age"]))
                carried += 1
        except (KeyError, IndexError, ValueError, AttributeError):
            continue
    if carried:
        _say_safely(f"  mang sang {carried} ghim của người nghe (gồm cả người không nói ở lô gieo)")
    return carried


def port(source: Path, target: Path, *, dry_run: bool = False) -> tuple[int, int]:
    """Returns (characters pinned, characters already pinned)."""
    casting = read_casting(source)
    database = ProjectDB(target / "project.sqlite3") if not dry_run else None
    if not casting:
        # Ghim của người nghe phải đi trước chỗ này: một project có ghim mà CHƯA phân vai (ghim được làm
        # trước cả khi phân tích xong - xem `lock_character_gender`) thì thoát ở đây là bỏ mất ghim.
        carry_listener_pins(source, database)
        _say_safely("project nguồn chưa có casting để mang đi")
        return 0, 0
    already = (
        set(ProjectDB(target / "project.sqlite3").locked_character_voices())
        if (target / "project.sqlite3").is_file()
        else set()
    )
    from ebook_reader.character_registry import canonical_key

    pinned = skipped = 0
    for name, voice_key, profile in casting:
        if canonical_key(name) in already:
            skipped += 1
            continue
        _say_safely(f"  GHIM  {name} -> {voice_key}")
        pinned += 1
        if database is None:
            continue
        database.upsert_voice_profile(
            {
                "voice_key": voice_key,
                "engine": profile["engine"],
                "preset_name": profile["preset_name"],
                "description": profile["description"],
                "seed": profile["seed"],
                "pitch_semitones": profile["pitch_semitones"],
                "formant_ratio": profile["formant_ratio"],
                "status": "ready",
            }
        )
        database.set_locked_character_voice(name, voice_key)

    # Carry what the source batch learnt about who these people are, so the next batch's
    # analysis prompt opens with the cast instead of "(Chưa có nhân vật đã biết)".
    #
    # Deliberately NOT locked. `locked` means a person decided, and outranks the model
    # permanently; this is one machine telling the next what it worked out, which the model
    # should still be free to revise if the book says otherwise.
    known = read_known_characters(source)
    for character in known:
        _say_safely(
            f"  BIẾT  {character['canonical_name']}"
            f" ({character['gender']}, đã gặp {character['mention_count']})"
        )
        if database is None:
            continue
        database.upsert_character(
            canonical_name=str(character["canonical_name"]),
            display_name=str(character["display_name"] or character["canonical_name"]),
            gender=str(character["gender"]),
            age=str(character["age"] or "unknown"),
            personality=str(character["personality"] or ""),
            mentions=int(character["mention_count"] or 0),
            importance=str(character["importance"] or "minor"),
            confidence=float(character["confidence"] or 0.5),
        )
        # Thuộc tính NGƯỜI đã ghim thì đi theo chuỗi gieo, khác với thứ máy vừa học ở trên.
        # `cast` hứa trong docstring của nó rằng câu trả lời của người nghe outrank mô hình
        # **vĩnh viễn**; trước bản vá này lời hứa ấy chỉ đúng trong MỘT project, vì `port` mang
        # nhân vật sang "deliberately NOT locked" và lô sau phân tích lại rồi đổi ý.
        try:
            if int(character["locked"] or 0) and str(character["gender"]) in ("male", "female"):
                database.lock_character_gender(
                    str(character["canonical_name"]), str(character["gender"])
                )
            if str(character["locked_age"] or ""):
                database.lock_character_age(
                    str(character["canonical_name"]), str(character["locked_age"])
                )
        except (KeyError, IndexError, ValueError, AttributeError):
            # Project nguồn cũ hơn cột `locked_age`, hoặc một giá trị không ghim được: mang
            # được gì thì mang, đừng làm cả lượt port chết vì một hàng.
            pass
    if known:
        _say_safely(f"  mang sang {len(known)} nhân vật đã biết (tên, giới tính, số lần gặp)")

    carry_listener_pins(source, database)

    # Sổ cộng dồn đi theo chuỗi gieo. Không chép thì project đúc lại một chương (`lo03r_066`)
    # không có sổ, và lô sau gieo từ nó phải lùi về `mention_count` của MỘT chương - đúng cái
    # số sai mà sổ sinh ra để thay. `backfill_exposure.py` chạy trước lô vẫn tính lại từ đầu và
    # ghi đè bản chép này; chép chỉ để không có project nào trên chuỗi thiếu sổ.
    if database is not None:
        carried = copy_ledger(source, target)
        if carried:
            _say_safely(f"  mang sang sổ cộng dồn: {carried} nhân vật")
    return pinned, skipped


def main(argv: list[str]) -> int:
    dry_run = "--dry-run" in argv
    positional = [value for value in argv if not value.startswith("--")]
    if len(positional) != 2:
        _say_safely("dùng: port_casting.py <project nguồn> <project đích> [--dry-run]")
        return 2
    source, target = (Path(value).resolve() for value in positional)
    for project in (source, target):
        if not (project / "project.sqlite3").is_file():
            _say_safely(f"không phải project: {project}")
            return 2

    pinned, skipped = port(source, target, dry_run=dry_run)
    _say_safely("")
    _say_safely(
        f"{pinned} nhân vật được ghim giọng"
        + (f", {skipped} đã ghim từ trước" if skipped else "")
        + (" (chạy thử, chưa ghi)" if dry_run else "")
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
