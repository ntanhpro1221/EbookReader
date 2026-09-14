"""Va character_registry.py: nhom NPC VO DANH cung phai khai no noi o chuong nao, truoc lan chon giong dau.

Luat tranh va cham cung chuong (`_first_free_variant` -> `shared_chapters`) doc `allocator.chapters_of`.
Khoi ghi no - dong 1583, kem chu thich "Ai co mat o chuong nao - cho MOI nguoi, truoc lan `choose()` dau
tien" - chi chay cho `speaker_groups`, tuc nguoi CO TEN. Ba nhom NPC vo danh (`ANONYMOUS_MALE` /
`_FEMALE` / `_UNKNOWN`) duoc cast o mot khoi rieng ben duoi va **khong bao gio** duoc khai chuong, nen voi
chung `mine` la tap rong, moi bac cho `shared_chapters = 0`, va khi thang bac da het cho trong thi tie-break
lui ve "bac thap nhat tren thang" - dung bac ma nguoi dong nhat thuong dang giu.

Ca that, cuon 2 lo 1: `Thanh Binh` co 7 bac (1.00, 0.93, 1.08, 0.898, 1.16, 0.97, 1.04) va 8 nguoi da ghim
chiem gan het; nhom `NPC vo danh nam` roi vao bac 1.00 - dung bac cua LUCIEN, nhan vat chinh. Ba chuong
(022, 023, 032) co Lucien va "nguoi dan ong vo danh" cung mot giong; buoc 4 ranh gioi duc lai va lam sach
hai chuong (vi lan phan tich moi khong sinh ra NPC vo danh), con chuong 022 tai dien y nguyen va **da len
sach** - nguoi nghe se thay nhan vat chinh tu noi voi minh 6 cau.

Do tren 14 project cua ca hai cuon: 12 va cham cung chuong, **4 co nhom vo danh**, va ca 4 deu o cuon 2
(3 o lo 1, 1 o project duc lai 022). Cuon 1 het va cham thuoc lop nay - tam giong nguoi co ten.

Sua: sau khoi ghi chuong cua nguoi co ten, ghi them cho ba nhom vo danh tu chinh `anonymous_by_gender`
(hang cua chung la hang segment, da co `chapter_id`). Mot dong logic, dat o **truoc** `choose()` dau tien
nhu chu thich goc da doi hoi. Khong doi cach chon, khong doi thu tu cast, khong doi gi khac.

Chay: python patch_the_nameless_crowd_says_where_it_speaks.py <root>
"""
import io
import sys
from pathlib import Path

root = Path(sys.argv[1])
p = root / "ebook_reader" / "character_registry.py"
s = io.open(p, encoding="utf-8").read()

OLD = '''    for speaker, speaker_rows in speaker_groups:
        allocator.note_chapters(
            canonical_key(speaker),
            {int(row["chapter_id"]) for row in speaker_rows},
        )
    local_count = 0
'''
NEW = '''    for speaker, speaker_rows in speaker_groups:
        allocator.note_chapters(
            canonical_key(speaker),
            {int(row["chapter_id"]) for row in speaker_rows},
        )
    # Cả ba nhóm NPC vô danh cũng phải khai, vì chúng cũng được `choose()` - ở khối riêng bên
    # dưới - và "cho MỌI người" ở trên phải đúng nghĩa. Không khai thì `chapters_of` của chúng
    # rỗng, `shared_chapters` trả 0 cho mọi bậc, và khi thang bậc đã cạn chỗ trống thì tie-break
    # lùi về bậc thấp nhất - đúng bậc người đông lời nhất đang giữ. Cuốn 2 lô 1: nhóm "NPC vô
    # danh nam" rơi vào bậc 1,00 của Thanh Bình, tức giọng của LUCIEN, ở ba chương 022/023/032;
    # chương 022 đã lên sách với nhân vật chính tự nói với mình 6 câu.
    for anonymous_gender, anonymous_gender_rows in anonymous_by_gender.items():
        if not anonymous_gender_rows:
            continue
        allocator.note_chapters(
            f"ANONYMOUS_{anonymous_gender.upper()}",
            {int(row["chapter_id"]) for row in anonymous_gender_rows},
        )
    local_count = 0
'''
assert s.count(OLD) == 1, "khong khop khoi note_chapters"
s = s.replace(OLD, NEW, 1)
io.open(p, "w", encoding="utf-8", newline="\n").write(s)
print(f"da va {p}")

TEST = '''"""The nameless crowd must say where it speaks, or it lands on the protagonist's voice.

`_first_free_variant` avoids a same-chapter holder by reading `allocator.chapters_of`. The registry
filled that for named speakers only, so the three anonymous NPC groups were invisible to the rule that
exists to stop two people sharing one voice inside a chapter. Book 2, batch 1: "NPC vô danh nam" landed
on Thanh Bình 1.00 - LUCIEN's voice - in chapters 022, 023 and 032, and chapter 022 shipped that way.
Measured across 14 projects of both books: 12 same-chapter collisions, 4 of them with an anonymous group.
"""
from __future__ import annotations

import re
from pathlib import Path

from ebook_reader.character_registry import PresetAllocator, formant_variants_for_preset

ROOT = Path(__file__).resolve().parents[1]
PRESET = "Thanh Bình"


def _allocator_with_a_full_ladder(*, tell_the_crowd_its_chapters: bool) -> PresetAllocator:
    """Đúng hình của lô 1: mọi bậc của một preset đã có chủ, và chủ bậc thấp nhất ở chương 22."""
    allocator = PresetAllocator(narrator_voice="Phạm Tuyên", max_pitch_shift=7)
    variants = formant_variants_for_preset(PRESET)
    holders = [f"NGUOI_{index}" for index in range(len(variants))]
    allocator.note_chapters(holders[0], {22})       # LUCIEN: cùng chương với nhóm vô danh
    for holder in holders[1:]:
        allocator.note_chapters(holder, {77})       # những người khác: chương khác hẳn
    for holder, ratio in zip(holders, variants):
        allocator.reserve(PRESET, ratio, who=holder)
    if tell_the_crowd_its_chapters:
        allocator.note_chapters("ANONYMOUS_MALE", {22})
    return allocator


def test_a_crowd_that_names_its_chapters_avoids_the_voice_in_the_room() -> None:
    allocator = _allocator_with_a_full_ladder(tell_the_crowd_its_chapters=True)
    variants = formant_variants_for_preset(PRESET)

    chosen = allocator._first_free_variant(PRESET, variants, who="ANONYMOUS_MALE")

    assert abs(chosen - variants[0]) > 0.005, (
        "nhóm vô danh nói ở chương 22 không được nhận bậc của người cũng nói ở chương 22"
    )


def test_a_silent_crowd_lands_exactly_on_the_protagonist() -> None:
    """Bài này giữ lại chứng cứ: không khai chương thì tie-break lùi về bậc thấp nhất."""
    allocator = _allocator_with_a_full_ladder(tell_the_crowd_its_chapters=False)
    variants = formant_variants_for_preset(PRESET)

    chosen = allocator._first_free_variant(PRESET, variants, who="ANONYMOUS_MALE")

    assert abs(chosen - variants[0]) < 0.005


def test_the_registry_notes_the_anonymous_groups_before_it_casts_them() -> None:
    """Chỗ ghi phải nằm TRƯỚC lần `choose()` đầu tiên, không phải cạnh khối cast nhóm vô danh."""
    source = (ROOT / "ebook_reader" / "character_registry.py").read_text(encoding="utf-8")
    note = source.index('f"ANONYMOUS_{anonymous_gender.upper()}"')
    first_choose = source.index("allocator.choose(")
    assert note < first_choose, "ghi chương cho nhóm vô danh phải đứng trước choose() đầu tiên"
    assert re.search(r"for anonymous_gender, anonymous_gender_rows in anonymous_by_gender", source)
'''
t = root / "tests" / "test_the_nameless_crowd_says_where_it_speaks.py"
io.open(t, "w", encoding="utf-8", newline="\n").write(TEST)
print(f"da tao {t}")
