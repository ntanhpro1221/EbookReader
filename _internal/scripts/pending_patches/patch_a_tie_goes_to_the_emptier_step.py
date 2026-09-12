"""Va character_registry.py: khi buoc phai dung chung bac, hoa ve chuong chung thi chon bac IT nguoi giu hon.

Do 2026-09-12 15:27 tren lo 6 (lo06_99a908b8f8), ngay sau khi khoa dan giong:

    nguoi/bac nhieu nhat: thai_son_f100_p+00 -> 6 nguoi
        KAIN REICHARDT 8 cau (160) · ERWIN 6 (150,152) · DAMIAN 4 (157) · LEON 2 (147,148)
        · GA 1 (166) · DORON 1 (149)
    giong da duc 10 / cap duoc 14 (nam)   0/5 va cham nam trong cung mot chuong
    CANH BAO "nhieu nhan vat dung chung mot giong" bat 1 lan

Khong ai trong sau nguoi ay cung chuong, nen trong lo 6 nguoi nghe khong lan. Nhung sau nguoi
mot giong la muoi lam cap co the gap nhau o lo sau, va bon bac khac cung 0 chuong chung chi co
mot nguoi giu. Nguyen nhan nam o mot dong: khi het bac trong, `_first_free_variant` xep theo
(so chuong chung, chi so bac). Nguoi moi chua gap ai thi moi bac deu 0 chuong chung, va hoa
thi lay bac THAP NHAT - nen tat ca cung roi ve mot bac.

Sua: chen "so nguoi dang giu bac" vao giua hai khoa. Van tat dinh, van uu tien khong-cung-
chuong tuyet doi (khoa dau khong doi), chi rai nguoi moi ra cac bac deu trong nhu nhau.

Bo qua neu khong co bac nao het: nhanh "con bac trong" o tren khong dung toi day.
File bi khoa - ap o ranh gioi 7 -> 8 cung cac ban va khac. Khong gap: khong co va cham that.
"""
import io
import sys
from pathlib import Path

root = Path(sys.argv[1])
p = root / "ebook_reader" / "character_registry.py"
s = io.open(p, encoding="utf-8").read()

OLD_COMMENT = '''        # Chọn bậc mà người đang giữ nó có ÍT chương chung nhất với người sắp được cast; hoà
        # thì bậc thấp hơn trên thang (tất định, tái lập được). Không biết gì về người sắp cast'''
NEW_COMMENT = '''        # Chọn bậc mà người đang giữ nó có ÍT chương chung nhất với người sắp được cast; hoà
        # thì bậc ÍT người giữ hơn, rồi mới tới bậc thấp hơn trên thang (tất định, tái lập
        # được). Không biết gì về người sắp cast'''
assert s.count(OLD_COMMENT) == 1, "khong khop comment _first_free_variant"
s = s.replace(OLD_COMMENT, NEW_COMMENT, 1)

OLD = '''        ranked = sorted(
            enumerate(variants),
            key=lambda pair: (shared_chapters(pair[1]), pair[0]),
        )
        return ranked[0][1]
'''
NEW = '''        def crowd(ratio: float) -> int:
            return len(holders.get(round(ratio, 3), ()))

        # Hoà về chương chung (thường là 0: người mới chưa gặp ai) thì chọn bậc ÍT người giữ
        # hơn, rồi mới tới thứ tự thang. Bản trước hoà là lấy bậc thấp nhất, nên lô 6 xếp sáu
        # nhân vật phụ (KAIN REICHARDT, ERWIN, DAMIAN, LEON, GÃ, DORON) chồng lên đúng một bậc
        # thai_son_f100 trong khi bốn bậc khác cùng 0 chương chung chỉ có một người giữ. Không
        # ai cùng chương nên người nghe không lẫn trong lô ấy, nhưng sáu người một giọng là
        # mười lăm cặp có thể gặp nhau ở lô sau, và cảnh báo "nhiều nhân vật dùng chung một
        # giọng" đã bật. Đo 2026-09-12 15:27 trên lo06_99a908b8f8.
        ranked = sorted(
            enumerate(variants),
            key=lambda pair: (shared_chapters(pair[1]), crowd(pair[1]), pair[0]),
        )
        return ranked[0][1]
'''
assert s.count(OLD) == 1, "khong khop ranked trong _first_free_variant"
s = s.replace(OLD, NEW, 1)
io.open(p, "w", encoding="utf-8", newline="\n").write(s)
print(f"da va {p}")

TEST = '''"""Khi buộc phải dùng chung bậc và không ai cùng chương với người mới, rải ra - đừng chồng.

Lô 6, 2026-09-12: sáu nhân vật phụ không cùng chương với bất kỳ ai đều rơi về cùng một bậc
`thai_son_f100_p+00`, vì hoà về chương chung thì luật cũ lấy bậc thấp nhất. Không ai cùng chương
nên người nghe không lẫn, nhưng sáu người một giọng là mười lăm cặp có thể gặp nhau ở lô sau.
"""
from __future__ import annotations

from ebook_reader.character_registry import PresetAllocator
from ebook_reader.voice_catalog import formant_variants_for_preset


def _fill_every_male_preset(allocator: PresetAllocator) -> list[str]:
    """Cast người ở các chương rời nhau cho tới khi mọi preset nam hết bậc; trả về tên preset."""
    full: list[str] = []
    for index in range(60):
        who = f"P{index:02d}"
        allocator.note_chapters(who, {index})
        preset, _ratio, _pitch = allocator.choose("male", npc=False, who=who)
        name = str(preset["name"])
        if (
            name not in full
            and len(allocator.taken_variants.get(name, ())) >= len(formant_variants_for_preset(name))
        ):
            full.append(name)
        if len(full) >= 2:
            return full
    raise AssertionError("kho nam không đầy - fixture sai")


def test_strangers_spread_across_equally_empty_steps() -> None:
    allocator = PresetAllocator(narrator_voice="Phạm Tuyên", max_pitch_shift=4)
    name = _fill_every_male_preset(allocator)[0]
    variants = formant_variants_for_preset(name)

    landed = []
    for k in range(3):
        who = f"NEW{k}"
        allocator.note_chapters(who, {500 + k})  # chương riêng, không gặp ai
        step = allocator._first_free_variant(name, variants, who=who)
        allocator.holders[name].setdefault(round(step, 3), set()).add(who)
        landed.append(round(step, 3))

    assert len(set(landed)) == 3, f"ba người lạ phải ở ba bậc, không phải {landed}"


def test_a_scene_partner_still_outranks_crowding() -> None:
    """Khoá đầu không đổi: một bậc trống người nhưng có bạn diễn vẫn thua một bậc đông mà lạ."""
    allocator = PresetAllocator(narrator_voice="Phạm Tuyên", max_pitch_shift=4)
    name = _fill_every_male_preset(allocator)[0]
    variants = formant_variants_for_preset(name)
    steps = [round(v, 3) for v in variants]
    partner_step, crowded_step = steps[0], steps[1]
    partner = next(iter(allocator.holders[name][partner_step]))
    allocator.note_chapters(partner, {700})
    for k in range(3):  # bậc thứ hai đã đông, toàn người lạ
        who = f"CROWD{k}"
        allocator.note_chapters(who, {800 + k})
        allocator.holders[name][crowded_step].add(who)
    for step in steps[2:]:  # các bậc còn lại: mỗi bậc một người có mặt ở chương 700
        for who in allocator.holders[name][step]:
            allocator.note_chapters(who, {700})
    allocator.note_chapters("NEWCOMER", {700})

    step = round(allocator._first_free_variant(name, variants, who="NEWCOMER"), 3)

    assert step == crowded_step
'''
t = root / "tests" / "test_a_tie_goes_to_the_emptier_step.py"
io.open(t, "w", encoding="utf-8", newline="\n").write(TEST)
print(f"da tao {t}")
