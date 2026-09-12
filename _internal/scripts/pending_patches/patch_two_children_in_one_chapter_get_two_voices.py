"""Va character_registry.py: hai dua tre trong mot chuong phai la hai giong.

Do 2026-09-12 22:30 tren lo 7 (lo07_233ddd7f34), ngay sau khi khoa dan giong — va cham cung chuong
DUY NHAT cua lo, o chuong 186:

    ngoc_linh_f107_p+02   AEREN                        male  age=child   3 cau
    ngoc_linh_f107_p+02   NPC_LOCAL::...::CON TRAI     male  age=child   1 cau

Ca hai la tre con, ca hai nam, cung chuong, cung mot voice_key. Nguoi nghe lan.

Vi sao luat tranh-cung-chuong hien co khong do duoc: tuoi AN DINH bac formant
(`formant_ratio_for_age`), nen `_first_free_variant` — noi luat ay song — khong duoc goi cho tre
con. Voi tre con, preset la truc da dang DUY NHAT, va preset chon theo `rank` ma khoa thu hai la
`usage[name]` dem THEO POOL (co ten / NPC): dua tre co ten thay Ngoc Linh usage 0, NPC tre con thay
Ngoc Linh usage 0 (so cua no), ca hai cung chon Ngoc Linh, cung warp theo tuoi, cung pitch.
Cung lop voi CONG TUOC / ONG LAO o alpha.55 (`reserve` da sua cho pin): hai so, mot giong.

Sua: sau khi xep hang, neu tuoi an dinh bac formant thi hoi thang so nguoi giu (`holders`, cung
so ma `_first_free_variant` hoi): preset hang dau ma bac-theo-tuoi cua no da co nguoi CUNG CHUONG
giu -> lay preset ke tiep trong hang; khong preset nao ranh -> ve hang dau nhu cu. Dua tre dau
tien van nhan dung giong nguoi nghe ua thich; dua thu hai trong cung chuong nhan giong ua thich
thu hai. Hai dua o hai chuong khac nhau van duoc dung chung — nguoi nghe nghe tung chuong mot.

File bi khoa; xep hang cho ranh gioi 7 -> 8 cung hai ban va da xep.
"""
import io
import sys
from pathlib import Path

root = Path(sys.argv[1])
p = root / "ebook_reader" / "character_registry.py"
s = io.open(p, encoding="utf-8").read()

OLD = '''        selected = min(candidates, key=rank)
        name = str(selected["name"])
        usage[name] += 1
'''
NEW = '''        ranked_presets = sorted(candidates, key=rank)
        selected = ranked_presets[0]
        if who and abs(formant_ratio_for_age(str(selected["name"]), age, gender) - 1.0) > 1e-6:
            # Tuổi ấn định bậc formant, nên với trẻ con preset là trục đa dạng DUY NHẤT — và
            # `usage` đếm theo pool (có tên / NPC), nên một đứa trẻ có tên và một NPC trẻ con
            # cùng chương đều thấy Ngọc Linh "chưa ai dùng". Lô 7, chương 186: AEREN (3 câu)
            # và NPC CON TRAI (1 câu) cùng `ngoc_linh_f107_p+02` - người nghe lẫn. Cùng lớp với
            # CÔNG TƯỚC/ÔNG LÃO ở alpha.55: hai sổ, một giọng. Ở đây hỏi thẳng sổ người giữ -
            # cùng sổ mà `_first_free_variant` hỏi: preset hạng đầu mà bậc-theo-tuổi của nó đã
            # có người CÙNG CHƯƠNG giữ thì lấy preset kế tiếp; không preset nào rảnh thì về
            # hạng đầu như cũ. Đứa trẻ đầu tiên vẫn nhận đúng giọng người nghe ưa thích.
            mine = self.chapters_of.get(str(who), set())
            for preset in ranked_presets:
                preset_name = str(preset["name"])
                step = round(float(formant_ratio_for_age(preset_name, age, gender)), 3)
                held = self.holders.get(preset_name, {}).get(step, set())
                if not any(self.chapters_of.get(holder, set()) & mine for holder in held):
                    selected = preset
                    break
        name = str(selected["name"])
        usage[name] += 1
'''
assert s.count(OLD) == 1, "khong khop 'selected = min(candidates, key=rank)'"
s = s.replace(OLD, NEW, 1)
io.open(p, "w", encoding="utf-8", newline="\n").write(s)
print(f"da va {p}")

TEST = '''"""Hai đứa trẻ trong một chương phải là hai giọng.

Lô 7, chương 186: AEREN (nam, trẻ con, 3 câu) và NPC CON TRAI (nam, trẻ con, 1 câu) cùng
`ngoc_linh_f107_p+02`. Tuổi ấn định bậc formant nên luật tránh-cùng-chương của thang bậc không
chạm tới trẻ con, và `usage` đếm theo pool nên đứa có tên và NPC không thấy nhau.
"""
from __future__ import annotations

from ebook_reader.character_registry import PresetAllocator


def _key(choice) -> tuple[str, float, int]:
    preset, ratio, pitch = choice
    return (str(preset["name"]), round(float(ratio), 3), int(pitch))


def test_a_named_child_and_an_npc_child_in_one_chapter_get_different_voices() -> None:
    allocator = PresetAllocator(narrator_voice="Phạm Tuyên", max_pitch_shift=4)
    allocator.note_chapters("AEREN", {186})
    allocator.note_chapters("NPC_LOCAL::C00020::CON TRAI", {186})

    first = allocator.choose("male", npc=False, age="child", who="AEREN")
    second = allocator.choose("male", npc=True, age="child", who="NPC_LOCAL::C00020::CON TRAI")

    assert _key(first) != _key(second), "cùng chương, cùng tuổi, cùng giới - vẫn phải là hai giọng"


def test_the_first_child_still_gets_the_listener_preferred_voice() -> None:
    """Sửa chỉ chạm đứa trẻ thứ hai: đứa đầu vẫn nhận giọng người nghe đã xếp hạng nhất."""
    allocator = PresetAllocator(narrator_voice="Phạm Tuyên", max_pitch_shift=4)
    allocator.note_chapters("AEREN", {186})

    preset, _ratio, _pitch = allocator.choose("male", npc=False, age="child", who="AEREN")

    assert str(preset["name"]) == "Ngọc Linh"


def test_two_children_in_different_chapters_may_share_the_preferred_voice() -> None:
    """Người nghe nghe từng chương một; hai đứa trẻ không bao giờ gặp nhau được dùng chung giọng
    ưa thích thay vì bị đẩy sang giọng hạng hai."""
    allocator = PresetAllocator(narrator_voice="Phạm Tuyên", max_pitch_shift=4)
    allocator.note_chapters("A", {10})
    allocator.note_chapters("B", {20})

    first = allocator.choose("male", npc=False, age="child", who="A")
    second = allocator.choose("male", npc=True, age="child", who="B")

    assert _key(first) == _key(second)
'''
t = root / "tests" / "test_two_children_in_one_chapter_get_two_voices.py"
io.open(t, "w", encoding="utf-8", newline="\n").write(TEST)
print(f"da tao {t}")
