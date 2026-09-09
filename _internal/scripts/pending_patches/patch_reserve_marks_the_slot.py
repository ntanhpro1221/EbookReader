r"""Va character_registry.py: giu cho DUNG bac formant dang bi giu, khong phai mot bac bat ky.

CHUA AP luc viet - lo va lo01v dang chay. Ap o ranh gioi lo, truoc lo 2.

Lo 1: Thanh Binh nhan 7 nhan vat tren 7 bac formant va chi sinh ra SAU giong - bac 0,898 bo
phi trong khi f104 phat cho ca CHA lan SO BA. Xem docs/TWO_CHARACTERS_ONE_VOICE.md, muc
*"Chỗ thứ hai: reserve() đánh dấu nhầm ô"*.
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

# ------------------------------------------------------------------ trang thai moi
OLD = """        self.variant_usage: Counter[str] = Counter()"""
NEW = '''        self.variant_usage: Counter[str] = Counter()
        # Bậc formant nào của preset nào đã có chủ. `variant_usage` đếm *bao nhiêu lần*, cái
        # này nhớ *bậc nào* - và chỉ cái sau mới trả lời được "bậc này còn trống không".
        #
        # Không gộp hai cái làm một: `variant_usage` vẫn cần cho đường quay vòng khi thang đã
        # cạn thật, và lúc ấy hành vi phải y hệt trước.
        self.taken_variants: dict[str, set[float]] = {}'''
assert OLD in s, "khong khop init"
s = s.replace(OLD, NEW, 1)

# ------------------------------------------------------------------ chon bac con trong
OLD = """            variants = formant_variants_for_preset(name)
            formant_ratio = variants[self.variant_usage[name] % len(variants)]
        self.variant_usage[name] += 1
        return selected, formant_ratio, age_pitch_semitones(age, gender, name)"""
NEW = '''            variants = formant_variants_for_preset(name)
            # Bậc còn trống đầu tiên theo thứ tự thang, chứ không phải bậc mà bộ đếm đang
            # chỉ vào. Hai cách chỉ khác nhau khi có bậc bị nhảy qua - và đúng chỗ ấy lô 1
            # mất một giọng: Thanh Bình nhận 7 người trên 7 bậc mà chỉ ra 6 giọng, bậc 0,898
            # bỏ phí trong khi f104 phát cho cả CHA lẫn SỐ BA.
            #
            # Thang bắt đầu ở 1,00 nên lần đúc đầu của một preset vẫn là giọng gốc không qua
            # vocoder; thứ tự thang không đổi, chỉ có việc bỏ qua bậc đã có chủ là mới.
            formant_ratio = self._first_free_variant(name, variants)
        self.variant_usage[name] += 1
        self.taken_variants.setdefault(name, set()).add(round(float(formant_ratio), 3))
        return selected, formant_ratio, age_pitch_semitones(age, gender, name)

    def _first_free_variant(self, preset_name: str, variants: tuple[float, ...]) -> float:
        """Bậc chưa ai giữ, theo thứ tự thang; cạn thật thì quay vòng như cũ.

        Đường quay vòng giữ nguyên `variant_usage[name] % len(variants)` **có chủ ý**: khi mọi
        bậc đã có chủ thì dùng lại là không tránh được, và lúc ấy đổi cách chọn chỉ đổi *ai*
        trùng với ai mà không giảm số lần trùng. Câu hỏi ấy cần đồ thị đồng hiện và là một
        thay đổi khác.

        So sánh có dung sai vì bậc đi qua `round(..., 3)` và qua cột REAL của SQLite; 0,005 là
        một nửa dung sai 0,01 mà chính `formant_variants_for_preset` dùng để khử trùng lặp.
        """
        taken = self.taken_variants.get(preset_name, set())
        for ratio in variants:
            if all(abs(ratio - held) > 0.005 for held in taken):
                return ratio
        return variants[self.variant_usage[preset_name] % len(variants)]'''
assert OLD in s, "khong khop cho chon bac"
s = s.replace(OLD, NEW, 1)

# ------------------------------------------------------------------ reserve nhan ca bac
OLD = '''        name = str(preset_name)
        for pool in self.pool_usage.values():
            pool[name] += 1
        self.variant_usage[name] += 1'''
NEW = '''        name = str(preset_name)
        for pool in self.pool_usage.values():
            pool[name] += 1
        self.variant_usage[name] += 1
        # Và đánh dấu **đúng** bậc đang bị giữ. Không có nó, `variant_usage` nhích lên một
        # tức nhảy qua một bậc *bất kỳ*: bậc bị nhảy qua thành bỏ phí, còn bậc thật sự có chủ
        # vẫn nằm trong vòng quay và được phát lại. Đo trên lô 1: đúng một va chạm sinh ra
        # như thế (CHA và SỐ BA), và nó tránh được mà không cần thêm giọng nào.
        #
        # `formant_ratio` để mặc định None cho những chỗ gọi cũ không biết bậc; khi ấy hành vi
        # y hệt trước bản vá này, tức chỉ nhích bộ đếm.
        if formant_ratio is not None:
            self.taken_variants.setdefault(name, set()).add(round(float(formant_ratio), 3))'''
assert OLD in s, "khong khop reserve"
s = s.replace(OLD, NEW, 1)

OLD = "    def reserve(self, preset_name: str) -> None:"
NEW = "    def reserve(self, preset_name: str, formant_ratio: float | None = None) -> None:"
assert OLD in s, "khong khop chu ky reserve"
s = s.replace(OLD, NEW, 1)

# ------------------------------------------------------------------ cho goi truyen bac di
OLD = '''        allocator.reserve(str(row["preset_name"]))'''
NEW = '''        # `row` là cả dòng voice_profiles, nên bậc formant có sẵn ở đây. Bản đầu chỉ truyền
        # tên preset đi và vứt nó, đó chính là chỗ hỏng.
        allocator.reserve(str(row["preset_name"]), float(row["formant_ratio"]))'''
assert OLD in s, "khong khop cho goi reserve"
s = s.replace(OLD, NEW, 1)

write_atomic(p, s)
print("da va", p)

TEST = '''"""Giữ chỗ một giọng đã ghim phải đánh dấu đúng bậc formant nó đang giữ.

Lô 1: Thanh Bình nhận 7 nhân vật trên 7 bậc formant và chỉ sinh ra **6** giọng — bậc 0,898
không bao giờ được cấp cho ai, trong khi f104 được phát cho cả CHA lẫn SỐ BA. Vì `reserve()`
chỉ nhận tên preset nên nó nhích bộ đếm qua một bậc bất kỳ thay vì đánh dấu bậc đang bị giữ.

Xem docs/TWO_CHARACTERS_ONE_VOICE.md.
"""
from __future__ import annotations

from ebook_reader.character_registry import PresetAllocator
from ebook_reader.voice_catalog import formant_variants_for_preset


def _allocator() -> PresetAllocator:
    return PresetAllocator(narrator_voice="Phạm Tuyên", max_pitch_shift=4)


def test_a_reserved_step_is_not_handed_out_again() -> None:
    """Giữ chỗ một bậc rồi cấp tiếp cho tới khi preset ấy quay lại lượt: bậc ấy không được ra.

    (Bản đầu của test này khẳng định lượt chọn **ngay sau** `reserve` phải rơi vào cùng preset,
    và nó đỏ — đúng ra là sai: `reserve` tăng `pool_usage`, nên preset vừa bị giữ chỗ phải
    **tụt hạng** và lượt sau sang preset khác. Đó là hành vi mong muốn, test mới thì đợi.)
    """
    probe = _allocator()
    preset, ratio, _pitch = probe.choose("male", npc=False)
    name = str(preset["name"])
    variants = formant_variants_for_preset(name)

    allocator = _allocator()
    allocator.reserve(name, ratio)
    seen: list[float] = []
    for _ in range(len(variants) * 4):
        chosen, step, _pitch = allocator.choose("male", npc=False)
        if str(chosen["name"]) == name:
            seen.append(round(step, 3))
            if len(seen) >= len(variants) - 1:
                break

    assert seen, "không lần nào quay lại preset đã giữ chỗ — test không kiểm được gì"
    assert all(abs(step - ratio) > 0.005 for step in seen), (
        f"bậc {ratio} đã bị giữ mà vẫn được phát lại: {seen}"
    )


def test_no_step_is_skipped_before_the_ladder_is_exhausted() -> None:
    """Đây là cái lô 1 mất: một bậc bỏ phí *và* một bậc phát hai lần, cùng một lúc."""
    allocator = _allocator()
    first, ratio, _pitch = allocator.choose("male", npc=False)
    name = str(first["name"])
    variants = formant_variants_for_preset(name)

    allocator.reserve(name, ratio)  # ghim đúng giọng vừa cấp, như port_casting làm
    issued = [round(ratio, 3)]
    for _ in range(len(variants) * 2):
        preset, step, _pitch = allocator.choose("male", npc=False)
        if str(preset["name"]) != name:
            continue
        if len(set(issued)) >= len(variants):
            break
        issued.append(round(step, 3))

    assert len(issued) == len(set(issued)), f"một bậc bị phát hai lần: {issued}"


def test_it_still_wraps_once_every_step_is_taken() -> None:
    """Cạn thật thì dùng lại là không tránh được; nó phải quay vòng chứ không được nổ."""
    allocator = _allocator()
    preset, _ratio, _pitch = allocator.choose("male", npc=False)
    name = str(preset["name"])
    variants = formant_variants_for_preset(name)
    for step in variants:
        allocator.reserve(name, step)

    chosen = allocator._first_free_variant(name, variants)

    assert chosen in variants


def test_reserve_without_a_step_behaves_as_before() -> None:
    """Chỗ gọi cũ không biết bậc thì chỉ nhích bộ đếm — không được đánh dấu nhầm bậc nào."""
    allocator = _allocator()
    allocator.reserve("Thái Sơn")

    assert allocator.taken_variants.get("Thái Sơn", set()) == set()
    assert allocator.variant_usage["Thái Sơn"] == 1
'''

q = root / "tests" / "test_reserve_marks_the_slot_it_holds.py"
write_atomic(q, TEST)
print("da tao", q)
