r"""Va character_registry.py: khi buoc phai dung chung giong, chon nguoi KHONG cung chuong.

CHUA AP luc viet - lo 3 dang chay. Ap o ranh gioi lo, truoc lo 4, SAU patch_dropped_marks.

Lo 3 (2026-09-10): 18 nguoi nam doi 14 cho, nac quay vong chay that, va 3 trong 7 va cham nam
cung chuong - KANG + SAMAEL (066, 071), IGOR + THU LANH (062, da vao audio: 3 + 23 cau). Nac
quay vong hien tai la `variants[variant_usage % len]`: mu hoan toan ve viec ai co mat o dau.

Nguoi nghe nghe tung chuong mot. Hai nguoi khong bao gio cung chuong ma trung giong thi khong ai
lan; hai nguoi cung chuong trung giong thi khong phan biet duoc ai dang noi. Nen khi PHAI dung
chung, cau hoi dung khong phai "co dung chung khong" ma la "AI dung chung voi ai".
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

# ---------------------------------------------------------------- trang thai: ai giu bac nao, ai o chuong nao
OLD = """        self.taken_variants: dict[str, set[float]] = {}"""
NEW = '''        self.taken_variants: dict[str, set[float]] = {}
        # Ai đang giữ bậc nào, và ai có mặt ở chương nào. `taken_variants` trả lời "bậc này còn
        # trống không"; hai cái này trả lời câu hỏi kế tiếp, chỉ đặt ra khi không còn bậc trống:
        # "dùng chung với ai thì ít hại nhất". Người nghe nghe từng chương một, nên hại đo bằng
        # số chương hai người cùng có mặt.
        self.holders: dict[str, dict[float, str]] = {}
        self.chapters_of: dict[str, set[int]] = {}

    def note_chapters(self, who: str, chapters: set[int]) -> None:
        """Ghi lại nhân vật này nói ở những chương nào. Gọi cho mọi người TRƯỚC lần chọn đầu.

        Một nhân vật đã ghim từ lô trước mà im lặng ở lô này thì không được ghi gì - tập rỗng -
        và như thế là đúng: người ấy không cùng chương với ai, nên là người lý tưởng để dùng
        chung giọng nếu buộc phải dùng chung.
        """
        self.chapters_of[str(who)] = set(int(c) for c in chapters)'''
assert OLD in s, "khong khop init"
s = s.replace(OLD, NEW, 1)

# ---------------------------------------------------------------- choose(): biet minh dang cast cho ai
OLD = """    def choose(
        self,
        gender: str,
        *,
        npc: bool,
        age: str = "unknown",
        prominent: bool = False,
    ) -> tuple[dict[str, str], float, int]:"""
NEW = """    def choose(
        self,
        gender: str,
        *,
        npc: bool,
        age: str = "unknown",
        prominent: bool = False,
        who: str = "",
    ) -> tuple[dict[str, str], float, int]:"""
assert OLD in s, "khong khop chu ky choose"
s = s.replace(OLD, NEW, 1)

OLD = """            formant_ratio = self._first_free_variant(name, variants)
        self.variant_usage[name] += 1
        self.taken_variants.setdefault(name, set()).add(round(float(formant_ratio), 3))
        return selected, formant_ratio, age_pitch_semitones(age, gender, name)"""
NEW = """            formant_ratio = self._first_free_variant(name, variants, who=who)
        self.variant_usage[name] += 1
        step = round(float(formant_ratio), 3)
        self.taken_variants.setdefault(name, set()).add(step)
        if who:
            self.holders.setdefault(name, {}).setdefault(step, str(who))
        return selected, formant_ratio, age_pitch_semitones(age, gender, name)"""
assert OLD in s, "khong khop cho ghi holder trong choose"
s = s.replace(OLD, NEW, 1)

# ---------------------------------------------------------------- nac quay vong: chon nguoi la
OLD = """    def _first_free_variant(self, preset_name: str, variants: tuple[float, ...]) -> float:"""
NEW = """    def _first_free_variant(
        self,
        preset_name: str,
        variants: tuple[float, ...],
        who: str = "",
    ) -> float:"""
assert OLD in s, "khong khop chu ky _first_free_variant"
s = s.replace(OLD, NEW, 1)

OLD = """        taken = self.taken_variants.get(preset_name, set())
        for ratio in variants:
            if all(abs(ratio - held) > 0.005 for held in taken):
                return ratio
        return variants[self.variant_usage[preset_name] % len(variants)]"""
NEW = '''        taken = self.taken_variants.get(preset_name, set())
        for ratio in variants:
            if all(abs(ratio - held) > 0.005 for held in taken):
                return ratio
        # Không còn bậc trống: PHẢI dùng chung. Đây là chỗ bản trước quay vòng mù -
        # `variants[variant_usage % len]` - và lô 3 trả giá: 3 trong 7 va chạm nằm cùng chương,
        # trong đó IGOR + THU LÃNH ở chương 062 (3 + 23 câu) đã vào audio trước khi ai kịp thấy.
        #
        # Chọn bậc mà người đang giữ nó có ÍT chương chung nhất với người sắp được cast; hoà
        # thì bậc thấp hơn trên thang (tất định, tái lập được). Không biết gì về người sắp cast
        # (không có `who`) hay không biết ai giữ bậc nào thì lùi về quay vòng cũ, để hành vi
        # ngoài đường ống chính không đổi.
        mine = self.chapters_of.get(str(who), set()) if who else None
        holders = self.holders.get(preset_name, {})
        if mine is None or not holders:
            return variants[self.variant_usage[preset_name] % len(variants)]
        ranked = sorted(
            enumerate(variants),
            key=lambda pair: (
                len(mine & self.chapters_of.get(holders.get(round(pair[1], 3), ""), set())),
                pair[0],
            ),
        )
        return ranked[0][1]'''
assert OLD in s, "khong khop than _first_free_variant"
s = s.replace(OLD, NEW, 1)

# ---------------------------------------------------------------- reserve(): ghi ai giu bac da ghim
OLD = """    def reserve(self, preset_name: str, formant_ratio: float | None = None) -> None:"""
NEW = """    def reserve(
        self,
        preset_name: str,
        formant_ratio: float | None = None,
        who: str | None = None,
    ) -> None:"""
assert OLD in s, "khong khop chu ky reserve"
s = s.replace(OLD, NEW, 1)

OLD = """        if formant_ratio is not None:
            self.taken_variants.setdefault(name, set()).add(round(float(formant_ratio), 3))"""
NEW = """        if formant_ratio is not None:
            step = round(float(formant_ratio), 3)
            self.taken_variants.setdefault(name, set()).add(step)
            if who:
                self.holders.setdefault(name, {}).setdefault(step, str(who))"""
assert OLD in s, "khong khop than reserve"
s = s.replace(OLD, NEW, 1)

OLD = """        allocator.reserve(str(row["preset_name"]), float(row["formant_ratio"]))"""
NEW = """        allocator.reserve(str(row["preset_name"]), float(row["formant_ratio"]), who=canonical)"""
assert OLD in s, "khong khop cho goi reserve"
s = s.replace(OLD, NEW, 1)

# ---------------------------------------------------------------- pre-pass: ai o chuong nao
OLD = """    speaker_groups = sorted(
        by_speaker.items(),
        key=lambda item: (-len(item[1]), item[0].casefold()),
    )"""
NEW = """    speaker_groups = sorted(
        by_speaker.items(),
        key=lambda item: (-len(item[1]), item[0].casefold()),
    )
    # Ai có mặt ở chương nào - cho MỌI người, trước lần `choose()` đầu tiên. Ghi theo tên chuẩn
    # vì đó là tên `choose()` và `reserve()` nhận. Thứ tự vòng lặp bên dưới là theo số câu giảm
    # dần, nên nếu ghi ở trong vòng thì một nhân vật xử lý sau sẽ vô hình với lần chọn ép buộc
    # của người xử lý trước - đúng lúc cần thấy nhất.
    for speaker, speaker_rows in speaker_groups:
        allocator.note_chapters(
            canonical_key(speaker),
            {int(row["chapter_id"]) for row in speaker_rows},
        )"""
assert OLD in s, "khong khop speaker_groups"
s = s.replace(OLD, NEW, 1)

OLD = """            preset, formant_ratio, age_pitch = allocator.choose(
                gender,
                npc=local,
                age=age,
                prominent=importance == "main",
            )"""
NEW = """            preset, formant_ratio, age_pitch = allocator.choose(
                gender,
                npc=local,
                age=age,
                prominent=importance == "main",
                who=canonical,
            )"""
assert OLD in s, "khong khop cho goi choose 1"
s = s.replace(OLD, NEW, 1)

OLD = """            preset, formant_ratio, age_pitch = allocator.choose(
                gender, npc=True, age=_majority(anonymous_rows, "age")
            )"""
NEW = """            preset, formant_ratio, age_pitch = allocator.choose(
                gender,
                npc=True,
                age=_majority(anonymous_rows, "age"),
                who=anonymous_canonical,
            )"""
assert OLD in s, "khong khop cho goi choose 2"
s = s.replace(OLD, NEW, 1)

write_atomic(p, s)
print("da va", p)

TEST = '''"""Khi buộc phải dùng chung giọng, chọn người KHÔNG cùng chương.

Lô 3: 18 người nam đòi 14 chỗ, nấc quay vòng chạy thật, và 3 trong 7 va chạm nằm cùng chương -
IGOR + THU LÃNH ở chương 062 (3 + 23 câu) đã vào audio. Nấc cũ là `variants[usage % len]`, mù
hoàn toàn về việc ai có mặt ở đâu. Người nghe nghe từng chương một, nên hại của một va chạm đo
bằng số chương hai người cùng có mặt - và khi PHẢI dùng chung thì câu hỏi là "với ai".
"""
from __future__ import annotations

from ebook_reader.character_registry import PresetAllocator
from ebook_reader.voice_catalog import formant_variants_for_preset


def _full_preset(allocator: PresetAllocator) -> tuple[str, list[str]]:
    """Cast người cho tới khi một preset nam hết bậc; trả về preset ấy và ai giữ bậc nào."""
    holders: list[str] = []
    for index in range(40):
        who = f"P{index:02d}"
        allocator.note_chapters(who, {index})  # mỗi người một chương riêng
        preset, _ratio, _pitch = allocator.choose("male", npc=False, who=who)
        holders.append((str(preset["name"]), who))
        name = str(preset["name"])
        if len(allocator.taken_variants.get(name, ())) >= len(formant_variants_for_preset(name)):
            return name, [w for n, w in holders if n == name]
    raise AssertionError("không preset nào đầy - fixture sai")


def test_a_forced_reuse_picks_someone_from_another_chapter() -> None:
    allocator = PresetAllocator(narrator_voice="Phạm Tuyên", max_pitch_shift=4)
    name, holders = _full_preset(allocator)
    variants = formant_variants_for_preset(name)
    # Người mới có mặt ở ĐÚNG chương của mọi người giữ bậc, trừ một người.
    stranger = holders[3]
    stranger_chapters = allocator.chapters_of[stranger]
    crowded = set()
    for who in holders:
        if who != stranger:
            crowded |= allocator.chapters_of[who]
    allocator.note_chapters("NEWCOMER", crowded)

    step = allocator._first_free_variant(name, variants, who="NEWCOMER")

    assert allocator.holders[name][round(step, 3)] == stranger, (
        "phải rơi vào bậc của người duy nhất không cùng chương"
    )
    assert not (allocator.chapters_of["NEWCOMER"] & stranger_chapters)


def test_the_real_lo03_shape_no_longer_lands_on_a_scene_partner() -> None:
    """SAMAEL đã ghim, nói ở 066 và 071; KANG mới, nói ở 066 và 071. Không được trùng."""
    allocator = PresetAllocator(narrator_voice="Phạm Tuyên", max_pitch_shift=4)
    name, holders = _full_preset(allocator)
    variants = formant_variants_for_preset(name)
    samael = holders[0]
    allocator.note_chapters(samael, {66, 71})
    allocator.note_chapters("KANG", {66, 71})
    # Mọi người khác ở chương khác hẳn.
    for who in holders[1:]:
        allocator.note_chapters(who, {900 + holders.index(who)})

    step = allocator._first_free_variant(name, variants, who="KANG")

    assert allocator.holders[name][round(step, 3)] != samael


def test_a_silent_pinned_character_is_the_ideal_partner() -> None:
    """Ai đã ghim mà im lặng lô này có tập chương rỗng - không cùng chương với bất kỳ ai."""
    allocator = PresetAllocator(narrator_voice="Phạm Tuyên", max_pitch_shift=4)
    name, holders = _full_preset(allocator)
    variants = formant_variants_for_preset(name)
    quiet = holders[5]
    allocator.note_chapters(quiet, set())
    everyone = set()
    for who in holders:
        everyone |= allocator.chapters_of[who]
    allocator.note_chapters("NEWCOMER", everyone)

    step = allocator._first_free_variant(name, variants, who="NEWCOMER")

    assert allocator.holders[name][round(step, 3)] == quiet


def test_without_a_name_it_wraps_exactly_as_before() -> None:
    """Không biết đang cast cho ai thì không được đoán - giữ nguyên quay vòng cũ."""
    allocator = PresetAllocator(narrator_voice="Phạm Tuyên", max_pitch_shift=4)
    name, _holders = _full_preset(allocator)
    variants = formant_variants_for_preset(name)
    expected = variants[allocator.variant_usage[name] % len(variants)]

    assert allocator._first_free_variant(name, variants) == expected


def test_a_free_step_still_wins_over_any_stranger() -> None:
    """Còn bậc trống thì không có chuyện dùng chung - phần 3 chỉ chạy khi phần 1 đã cạn."""
    allocator = PresetAllocator(narrator_voice="Phạm Tuyên", max_pitch_shift=4)
    preset, ratio, _pitch = allocator.choose("male", npc=False, who="A")
    name = str(preset["name"])
    variants = formant_variants_for_preset(name)
    allocator.note_chapters("A", {1})
    allocator.note_chapters("B", {2})

    step = allocator._first_free_variant(name, variants, who="B")

    assert abs(step - ratio) > 0.005
'''
q = root / "tests" / "test_wrap_prefers_a_stranger.py"
write_atomic(q, TEST)
print("da tao", q)
