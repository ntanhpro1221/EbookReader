"""Test: giong da ghim cua nhan vat IM LANG cung phai duoc giu cho."""
import io
import sys
from pathlib import Path

root = Path(sys.argv[1])
p = root / "tests" / "test_cast_voice_lock.py"
s = io.open(p, encoding="utf-8").read()

TEST = '''

def test_a_pin_is_reserved_even_when_its_character_says_nothing(tmp_path: Path) -> None:
    """The half of the mechanism alpha.56 was missing, and it cost a collision.

    reserve() explains why a pinned voice has to be counted: an unused preset always sorts
    first, so the next character is handed the voice somebody just pinned. But it was only
    ever called from _pinned_profile_id, which runs while casting a character - so a
    character who is pinned and silent in this batch reserved nothing.

    THEOSBANE said nothing across chapters 010-018. Its pin was therefore never counted,
    preset_thanh_binh_f093_p-04 still looked free, and the allocator gave it to SAMAEL.
    alpha.55, where every pinned character spoke, had no collisions at all. THEOSBANE is in
    156 of the book's 478 chapters, so the two would have shared a voice for a third of it.
    """
    db = _project(tmp_path)
    db.upsert_voice_profile(
        {
            "voice_key": KEY,
            "engine": "vieneu",
            "preset_name": "Thanh Bình",
            "description": "",
            "seed": 7,
            "pitch_semitones": -1,
            "formant_ratio": 1.09,
            "status": "ready",
        }
    )
    # Pinned, and deliberately never given a segment: this character is silent here.
    db.set_locked_character_voice("THEOSBANE", KEY)

    allocator = PresetAllocator("Phạm Tuyên", 2)
    said: list[str] = []
    reserved = reserve_pinned_voices(db, db.locked_character_voices(), allocator, said.append)

    assert reserved == 1
    chosen, _ratio, _pitch = allocator.choose("female", npc=False)
    assert str(chosen["name"]) != "Thanh Bình", (
        "giọng của một nhân vật im lặng vẫn là giọng của nó"
    )


def test_a_stale_pin_is_skipped_out_loud_rather_than_killing_the_run(tmp_path: Path) -> None:
    """A carried decision that has gone stale must not stop a book, and must not be silent."""
    db = _project(tmp_path)
    db.set_locked_character_voice("AI ĐÓ", "preset_khong_ton_tai_f100_p+00")

    allocator = PresetAllocator("Phạm Tuyên", 2)
    said: list[str] = []
    reserved = reserve_pinned_voices(db, db.locked_character_voices(), allocator, said.append)

    assert reserved == 0
    assert any("preset_khong_ton_tai_f100_p+00" in line for line in said)
'''

s = s.replace(
    "from ebook_reader.character_registry import PresetAllocator",
    "from ebook_reader.character_registry import PresetAllocator, reserve_pinned_voices",
    1,
)
s = s.rstrip() + "\n" + TEST
io.open(p, "w", encoding="utf-8").write(s)
print(f"da va {p}")
