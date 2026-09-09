"""Kho giọng còn bao nhiêu chỗ, và ai đang phải dùng chung giọng với ai.

    python scripts/voice_pool_pressure.py <project>

Sinh ra từ một phép đo trên lô 1 (docs/THE_MALE_VOICE_POOL_IS_FULL.md): **14 nhân vật nam có
tên, đúng 14 chỗ có thể cấp**, ở chương 029 của một cuốn 478 chương. Kho nam đầy từ lô đầu
tiên trong mười sáu, còn kho nữ mới dùng 6/27.

Cột đáng nhìn nhất không phải số va chạm mà là cột cuối: **có cùng chương không**. Người nghe
nghe từng chương một, nên hai nhân vật trùng giọng mà không bao giờ gặp nhau thì gần như vô
hại; trùng giọng trong cùng một chương mới là chỗ người nghe không phân biệt được ai đang nói.
Lô 1 có ba va chạm nhưng chỉ **một** nằm trong cùng chương.

Chỉ đọc; mở read-only nên chạy được cả khi project đang tổng hợp.
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ebook_reader import voice_catalog as vc  # noqa: E402


def _say(line: str) -> None:
    try:
        print(line)
    except (UnicodeEncodeError, OSError, ValueError):
        sys.stdout.buffer.write(line.encode("utf-8", "replace") + b"\n")


def _is_extra(name: str) -> bool:
    """NPC theo chương và các thùng đúc vai, không phải nhân vật có tên."""
    upper = name.upper()
    return upper.startswith("NPC_") or upper.startswith("ANONYMOUS")


def _capacity(narrator_preset: str) -> dict[str, int]:
    """Bao nhiêu giọng *khác nhau* bộ cấp phát có thể đúc cho nhân vật, theo giới.

    Không phải 7 nhân số preset: `formant_variants_for_preset` kẹp thang formant vào giới hạn
    giải phẫu của từng preset, nên Ngọc Linh chỉ ra 6 bậc chứ không phải 7.
    """
    out: dict[str, int] = {}
    for gender in (vc.GENDER_MALE, vc.GENDER_FEMALE):
        total = 0
        for preset in vc.casting_presets(gender):
            # Người dẫn chuyện giữ nguyên preset của mình; nhân vật không bao giờ dùng chung.
            if preset["name"] == narrator_preset:
                continue
            total += len(vc.formant_variants_for_preset(preset["name"]))
        out[gender] = total
    return out


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("project", type=Path)
    args = parser.parse_args(argv)

    database = args.project / "project.sqlite3"
    if not database.is_file():
        _say(f"Không thấy {database}")
        return 2
    conn = sqlite3.connect(f"file:{database}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row

    row = conn.execute(
        "SELECT preset_name FROM voice_profiles WHERE voice_key='narrator'"
    ).fetchone()
    narrator = str(row["preset_name"]) if row else ""
    capacity = _capacity(narrator)
    _say(f"giọng người dẫn chuyện: {narrator or '(chưa đúc)'}")

    speakers = conn.execute(
        """
        SELECT c.canonical_name AS name, c.gender AS gender, v.voice_key AS voice_key,
               ch.title AS chapter, count(*) AS lines
        FROM segments s
        JOIN characters c ON c.id = s.canonical_character_id
        JOIN voice_profiles v ON v.id = s.voice_profile_id
        JOIN chapters ch ON ch.id = s.chapter_id
        WHERE s.kind = 'dialogue' AND v.voice_key <> 'narrator'
        GROUP BY c.id, v.id, ch.id
        """
    ).fetchall()
    if not speakers:
        _say("Chưa có ai nói — project chưa tổng hợp xong.")
        return 0

    named: dict[str, set[str]] = {}
    where: dict[str, set[str]] = {}
    gender_of: dict[str, str] = {}
    extras: set[str] = set()
    voices_by_gender: dict[str, set[str]] = {}
    for row in speakers:
        name = str(row["name"])
        gender_of[name] = str(row["gender"])
        where.setdefault(name, set()).add(str(row["chapter"]))
        named.setdefault(name, set()).add(str(row["voice_key"]))
        voices_by_gender.setdefault(str(row["gender"]), set()).add(str(row["voice_key"]))
        if _is_extra(name):
            extras.add(name)

    _say("")
    for gender in (vc.GENDER_MALE, vc.GENDER_FEMALE):
        people = [n for n, g in gender_of.items() if g == gender]
        real = [n for n in people if n not in extras]
        used = len(voices_by_gender.get(gender, ()))
        room = capacity.get(gender, 0)
        bar = "ĐẦY" if len(real) >= room else f"còn {room - len(real)} chỗ"
        _say(
            f"{gender:7s} người nói {len(people):3d} (có tên {len(real):3d}, NPC "
            f"{len(people) - len(real):3d}) | giọng đã đúc {used:3d} / cấp được {room:3d}  {bar}"
        )

    # Cùng một voice_key, nhiều hơn một nhân vật. Đây là định nghĩa của va chạm; hai nhân vật
    # cùng preset nhưng khác formant KHÔNG phải va chạm, vì formant là trục thật sự làm hai
    # giọng nghe ra hai người.
    holders: dict[str, list[str]] = {}
    for name, keys in named.items():
        for key in keys:
            holders.setdefault(key, []).append(name)
    clashes = {key: sorted(names) for key, names in holders.items() if len(names) > 1}

    _say("")
    if not clashes:
        _say("Không có giọng nào bị hai nhân vật dùng chung.")
        return 0
    _say(f"{len(clashes)} giọng bị dùng chung:")
    hurts = 0
    for key, names in sorted(clashes.items()):
        shared_chapters: set[str] = set()
        for index, first in enumerate(names):
            for second in names[index + 1:]:
                shared_chapters |= where[first] & where[second]
        if shared_chapters:
            hurts += 1
            verdict = f"CÙNG CHƯƠNG {', '.join(sorted(shared_chapters))} — người nghe lẫn"
        else:
            verdict = "không cùng chương — gần như vô hại"
        _say(f"  {key:32s} {', '.join(names)}")
        _say(f"      {verdict}")

    _say("")
    _say(f"{hurts}/{len(clashes)} va chạm thật sự nằm trong cùng một chương.")
    if extras:
        _say("")
        _say(
            f"{len(extras)} NPC theo chương đang giữ một chỗ trong kho, ngang hàng với một nhân"
            " vật đi suốt cuốn sách:"
        )
        for name in sorted(extras):
            _say(f"  {name.split('::')[-1]}  (chương {', '.join(sorted(where[name]))})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
