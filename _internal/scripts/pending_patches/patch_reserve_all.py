"""Va character_registry.py: giu cho MOI giong da ghim, ke ca cua nhan vat im lang."""
import io
import sys
from pathlib import Path

root = Path(sys.argv[1])
p = root / "ebook_reader" / "character_registry.py"
s = io.open(p, encoding="utf-8").read()

OLD_PINNED = '''    # `canonical` has already been through canonical_key at the call site, and
    # locked_character_voices keys the same way; applying it again is idempotent and says so.
    voice_key = locked_voices.get(canonical_key(canonical), "")
    if not voice_key:
        return None
    try:
        row = db.voice_profile_by_key(voice_key)
    except KeyError:
        log(f"Giọng đã ghim {voice_key!r} cho {canonical!r} không có trong project; cấp phát lại.")
        return None
    allocator.reserve(str(row["preset_name"]))
    return int(row["id"])'''

NEW_PINNED = '''    # `canonical` has already been through canonical_key at the call site, and
    # locked_character_voices keys the same way; applying it again is idempotent and says so.
    voice_key = locked_voices.get(canonical_key(canonical), "")
    if not voice_key:
        return None
    try:
        row = db.voice_profile_by_key(voice_key)
    except KeyError:
        log(f"Giọng đã ghim {voice_key!r} cho {canonical!r} không có trong project; cấp phát lại.")
        return None
    # No reserve() here: reserve_pinned_voices has already counted every pinned preset once,
    # before any casting began. Counting again for the characters that happen to speak would
    # make their voices look more used than the pinned voices of silent characters, which is
    # the ranking reading a difference that does not exist.
    del allocator
    return int(row["id"])


def reserve_pinned_voices(
    db: ProjectDB,
    locked_voices: dict[str, str],
    allocator: Any,
    log: Callable[[str], None],
) -> int:
    """Take every pinned voice out of circulation before a single character is cast.

    `reserve` explains why a pinned voice must be counted at all. This is the other half:
    counting it for **every** pinned character, not only the ones with something to say in
    this batch.

    A character who is pinned and silent used to leave its voice looking free, and an unused
    preset always sorts first. Measured on alpha.56: THEOSBANE said nothing across chapters
    010-018, so nothing reserved `preset_thanh_binh_f093_p-04`, and the allocator handed that
    exact voice to SAMAEL. alpha.55, whose pinned characters all spoke, had no collisions at
    all. THEOSBANE appears in 156 of the book's 478 chapters, so the two would have gone on
    sharing a voice for a third of the book.

    Returns how many were reserved. A pin naming a profile this project does not have is
    reported and skipped - the run should not die because a carried decision went stale, and
    it is said out loud because silently re-casting a voice somebody chose is not acceptable.
    """
    reserved = 0
    for canonical, voice_key in sorted(locked_voices.items()):
        if not voice_key:
            continue
        try:
            row = db.voice_profile_by_key(voice_key)
        except KeyError:
            log(
                f"Giọng đã ghim {voice_key!r} cho {canonical!r} không có trong project;"
                " bỏ qua khi giữ chỗ."
            )
            continue
        allocator.reserve(str(row["preset_name"]))
        reserved += 1
    return reserved'''

assert OLD_PINNED in s, "khong khop _pinned_profile_id"
s = s.replace(OLD_PINNED, NEW_PINNED, 1)

OLD_CALL = '''    allocator = PresetAllocator(
        narrator_voice,
        int(voice_cfg.get("max_character_pitch_semitones", 2)),
    )
    profile_cache: dict[str, int] = {}'''

NEW_CALL = '''    allocator = PresetAllocator(
        narrator_voice,
        int(voice_cfg.get("max_character_pitch_semitones", 2)),
    )
    # Before anyone is cast: a voice that belongs to somebody is taken, whether or not that
    # somebody speaks in this batch.
    reserved_pins = reserve_pinned_voices(db, locked_voices, allocator, log)
    if reserved_pins:
        log(f"Giữ chỗ {reserved_pins} giọng đã ghim trước khi phân vai.")
    profile_cache: dict[str, int] = {}'''

assert OLD_CALL in s, "khong khop cho tao allocator"
s = s.replace(OLD_CALL, NEW_CALL, 1)

io.open(p, "w", encoding="utf-8").write(s)
print(f"da va {p}")
