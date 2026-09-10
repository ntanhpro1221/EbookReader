r"""Va character_registry.py: mot bac giong phai nho MOI nguoi dang giu no, khong chi nguoi dau.

CHUA AP luc viet - lo 4 dang chay. Ap o ranh gioi lo 4 -> 5.

Do tren chinh lo duc lai giong cua lo 3, 23:24 ngay 2026-09-10 - lan dau
`patch_wrap_prefers_a_stranger` chay that. Bon trong nam chuong sach: 0 va cham cung chuong.
Chuong 071 thi con 1, va duong di cua no cho thay bo cap phat lam DUNG mot nua roi mu nua sau.

Kho giong nam cua project duc lai: thang `Thanh Binh` co 7 bac va ca 7 deu da co chu (pin gieo
tu lo truoc: IGOR 0,898 · SAMAEL 0,93 · SAMAELE 0,97 · VIKTOR 1,00 · THU LANH 1,00@-7 ·
DORON 1,04 · JAKE 1,08 · JAY 1,16). KANG bi bo ghim khi thua SAMAEL nen phai duc lai, va:

    KANG        -> preset_thanh_binh_f100_p-04   (bac 1,00, VIKTOR dang giu)
    THANG DIEN  -> preset_thanh_binh_f100_p-04   (CUNG bac ay)   <- va cham trong chuong 071

Nua DUNG: KANG dung chung voi VIKTOR, va VIKTOR **khong noi cau nao trong chuong 071**. Do dung
la viec ban va duoc viet ra de lam - chon nguoi la, khong chon nguoi cung chuong. Bang chung
dau tien cho `patch_wrap_prefers_a_stranger`, tren audio that.

Nua MU: `holders` la `dict[float, str]` va duoc ghi bang `setdefault`, nen mot bac chi nho
**nguoi dau tien**. Sau khi KANG vao bac 1,00, `holders[1.0]` van la `VIKTOR`. Den luot THANG
DIEN (NPC song dung trong chuong 071), no do "bac 1,00 do ai giu?" -> `VIKTOR` -> nguoi la ->
0 chuong chung -> chon luon. KANG, ke DANG o cung chuong voi no, **vo hinh**.

Nen ban va truoc chi tranh duoc va cham DAU TIEN tren moi bac; tu nguoi thu ba tro di no lai
xep nguoi vao dung cho vua bi chiem, va no lam the mot cach tu tin vi cai ten no doc duoc la
mot nguoi la thuc su.

Sua: mot bac nho MOI nguoi giu no, va gia phai tra tinh tren HOP cua ho. "Bac nay co ai cung
chuong voi toi khong" moi la cau dung; "nguoi dau tien vao bac nay co cung chuong khong" la mot
cau khac va tinh co dung mot lan.
"""
import io
import os
import sys
import tempfile
from pathlib import Path


def write_atomic(path: Path, text: str) -> None:
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    os.close(fd)
    io.open(tmp, "w", encoding="utf-8").write(text)
    os.replace(tmp, path)


root = Path(sys.argv[1])
p = root / "ebook_reader" / "character_registry.py"
s = io.open(p, encoding="utf-8").read()

# ---------------------------------------------------------------- kieu cua holders
OLD = "        self.holders: dict[str, dict[float, str]] = {}"
NEW = """        # Bậc -> **mọi** người đang giữ nó, không chỉ người đầu tiên. Bản đầu là
        # `dict[float, str]` ghi bằng `setdefault`, và lô đúc lại của lô 3 trả giá: sau khi
        # KANG vào bậc 1,00 của Thanh Bình, `holders[1.0]` vẫn là VIKTOR, nên NPC kế tiếp đọc
        # bậc ấy thành "người lạ đang giữ" và xếp vào đúng chỗ vừa bị chiếm - trong khi KANG,
        # kẻ đang ở cùng chương với nó, vô hình.
        self.holders: dict[str, dict[float, set[str]]] = {}"""
assert OLD in s, "khong khop kieu holders"
s = s.replace(OLD, NEW, 1)

# ---------------------------------------------------------------- hai cho ghi (choose + reserve)
OLD = "                self.holders.setdefault(name, {}).setdefault(step, str(who))"
NEW = "                self.holders.setdefault(name, {}).setdefault(step, set()).add(str(who))"
assert s.count(OLD) == 1, "cho ghi trong reserve khong khop dung mot lan"
s = s.replace(OLD, NEW, 1)

OLD = "            self.holders.setdefault(name, {}).setdefault(step, str(who))"
NEW = "            self.holders.setdefault(name, {}).setdefault(step, set()).add(str(who))"
assert s.count(OLD) == 1, "cho ghi trong choose khong khop dung mot lan"
s = s.replace(OLD, NEW, 1)

# ---------------------------------------------------------------- gia phai tra tinh tren hop
OLD = """        ranked = sorted(
            enumerate(variants),
            key=lambda pair: (
                len(mine & self.chapters_of.get(holders.get(round(pair[1], 3), ""), set())),
                pair[0],
            ),
        )
        return ranked[0][1]"""
NEW = '''        def shared_chapters(ratio: float) -> int:
            """Bao nhiêu chương của tôi có **một người nào đó** đang giữ bậc này cũng có mặt.

            Hợp của mọi người giữ bậc, không phải người đầu tiên: một bậc đã bị dùng chung thì
            người thứ ba phải thấy cả hai người kia. Đo trên lô đúc lại của lô 3 - THẰNG ĐIÊN
            xếp vào đúng bậc KANG vừa chiếm vì bậc ấy vẫn khai tên VIKTOR.
            """
            occupied: set[int] = set()
            for holder in holders.get(round(ratio, 3), set()):
                occupied |= self.chapters_of.get(holder, set())
            return len(mine & occupied)

        ranked = sorted(
            enumerate(variants),
            key=lambda pair: (shared_chapters(pair[1]), pair[0]),
        )
        return ranked[0][1]'''
assert OLD in s, "khong khop cho tinh gia"
s = s.replace(OLD, NEW, 1)

write_atomic(p, s)
print("da va", p)

# ---------------------------------------------------------------- ba assert ghim HINH DANG cu
# `holders[step]` la mot set chu khong con la mot ten. Ba dong nay ghim hop dong cu, nen chung
# phai doi cung luc - de chung lai la de bo test do vi mot ly do dung.
t = root / "tests" / "test_wrap_prefers_a_stranger.py"
u = io.open(t, encoding="utf-8").read()
for OLD, NEW in (
    (
        "    assert allocator.holders[name][round(step, 3)] == stranger, (",
        "    assert allocator.holders[name][round(step, 3)] == {stranger}, (",
    ),
    (
        "    assert allocator.holders[name][round(step, 3)] != samael",
        "    assert samael not in allocator.holders[name][round(step, 3)]",
    ),
    (
        "    assert allocator.holders[name][round(step, 3)] == quiet",
        "    assert allocator.holders[name][round(step, 3)] == {quiet}",
    ),
):
    assert OLD in u, f"khong khop assert cu: {OLD[:60]}"
    u = u.replace(OLD, NEW, 1)
write_atomic(t, u)
print("da sua 3 assert trong", t)

TEST = '''"""Một bậc giọng nhớ mọi người đang giữ nó - nếu không, người thứ ba lại vào đúng chỗ vừa chiếm.

Đo trên lô đúc lại giọng của lô 3 (2026-09-10, 23:24), lần đầu `patch_wrap_prefers_a_stranger`
chạy thật. Bốn trên năm chương sạch. Chương 071 còn một va chạm, và nó lộ ra nửa mù của bản vá:

    KANG        -> Thanh Bình bậc 1,00   (VIKTOR đang giữ, VIKTOR KHÔNG nói trong 071)  <- đúng
    THẰNG ĐIÊN  -> Thanh Bình bậc 1,00   (đọc bậc ấy thành "của VIKTOR", người lạ)      <- sai

`holders` là `dict[float, str]` ghi bằng `setdefault` nên chỉ nhớ người đầu, và KANG - kẻ đang ở
cùng chương 071 - vô hình với lần chọn kế tiếp.
"""
from __future__ import annotations

from ebook_reader.character_registry import PresetAllocator


def _allocator() -> PresetAllocator:
    return PresetAllocator(narrator_voice="Phạm Tuyên", max_pitch_shift=7)


def test_a_step_remembers_every_holder_not_just_the_first() -> None:
    allocator = _allocator()
    allocator.reserve("Thanh Bình", 1.0, who="VIKTOR")
    allocator.reserve("Thanh Bình", 0.93, who="SAMAEL")

    allocator.holders["Thanh Bình"].setdefault(1.0, set()).add("KANG")

    assert allocator.holders["Thanh Bình"][1.0] == {"VIKTOR", "KANG"}


def test_the_third_speaker_sees_the_second_one(tmp_path: None = None) -> None:
    """Đúng ca chương 071: bậc 1,00 do VIKTOR (người lạ) *và* KANG (cùng chương) cùng giữ.

    Người thứ ba ở chương 071 phải tránh bậc ấy và chọn bậc chỉ có người lạ.
    """
    allocator = _allocator()
    ladder = (1.0, 0.93)
    # Cả hai bậc đã có chủ, nên mọi lựa chọn đều là dùng chung.
    allocator.reserve("Thanh Bình", 1.0, who="VIKTOR")
    allocator.reserve("Thanh Bình", 0.93, who="JAY")
    # KANG vào bậc 1,00; VIKTOR và JAY im lặng ở chương 71.
    allocator.holders["Thanh Bình"].setdefault(1.0, set()).add("KANG")
    allocator.note_chapters("KANG", {71})
    allocator.note_chapters("THẰNG ĐIÊN", {71})

    chosen = allocator._first_free_variant("Thanh Bình", ladder, who="THẰNG ĐIÊN")

    assert chosen == 0.93, (
        "bậc 1,00 có KANG cùng chương 71; bậc 0,93 chỉ có JAY im lặng - phải chọn 0,93"
    )


def test_a_free_step_still_wins_over_any_sharing() -> None:
    """Luật cũ không đổi: còn bậc trống thì lấy bậc trống, không cân ai với ai."""
    allocator = _allocator()
    allocator.reserve("Thanh Bình", 1.0, who="VIKTOR")
    allocator.note_chapters("KANG", {71})

    assert allocator._first_free_variant("Thanh Bình", (1.0, 0.93), who="KANG") == 0.93


def test_without_who_it_wraps_the_old_way() -> None:
    """Không biết ai sắp được cast thì lùi về quay vòng cũ - hành vi ngoài đường ống không đổi."""
    allocator = _allocator()
    allocator.reserve("Thanh Bình", 1.0, who="VIKTOR")
    allocator.reserve("Thanh Bình", 0.93, who="JAY")

    chosen = allocator._first_free_variant("Thanh Bình", (1.0, 0.93))

    assert chosen in (1.0, 0.93)
'''
q = root / "tests" / "test_a_step_remembers_every_holder.py"
write_atomic(q, TEST)
print("da tao", q)
