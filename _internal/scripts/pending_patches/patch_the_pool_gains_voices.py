"""Vá voice_catalog.py: 11 giọng mới, Xuân Vĩnh trở lại, và số chủ sách chọn bằng tai.

Chạy: python patch_the_pool_gains_voices.py <root>

**XẾP Ở RANH GIỚI 6, SAU** `patch_vieneu_3_8_1.py`, `patch_a_slow_voice_reads_at_its_own_speed.py` và
`patch_a_slow_voice_is_judged_by_its_own_pace.py` - bản này điền số vào hai bảng hai bản ấy thêm.
`voice_catalog.py` nằm trong `QUALITY_IMPLEMENTATION_FILES`, và thêm preset đổi `casting_presets` -
tức đổi cách phân vai của mọi project tạo sau đó.

## Chủ sách quyết (trang chấm giọng, 18-09)

- Nhận cả 11 giọng mới của VieNeu 3.8.1. Số đo sinh bằng `scripts/propose_a_new_voice.py` từ chính
  preview của từng giọng, đúng cách đo các giọng cũ (Praat: F0 trung vị, F3 "Get mean" cả clip → ống
  thanh L = 5c/4F3; `--verify` tái lập số cũ trong 0,81 lần ngưỡng):

      Adam            F0  87.1 Hz  ống 16.7 cm  bậc hạ  0  (giọng nam trầm nhất)
      Adam bựa        F0 146.9 Hz  ống 16.4 cm  bậc hạ -2
      Anh Khôi        F0 109.6 Hz  ống 16.5 cm  bậc hạ -2
      Đức Trí         F0  98.2 Hz  ống 16.6 cm  bậc hạ -1
      Kim Thanh       F0 230.6 Hz  ống 13.6 cm  bậc hạ -2
      Mạnh Dũng       F0 145.6 Hz  ống 16.6 cm  bậc hạ -2
      Minh Quân Pro   F0 151.7 Hz  ống 16.6 cm  bậc hạ -2
      Mỹ Duyên        F0 232.4 Hz  ống 14.8 cm  bậc hạ -2
      Ngọc Huyền      F0 207.7 Hz  ống 14.2 cm  bậc hạ -2
      Quỳnh Anh       F0 212.9 Hz  ống 14.1 cm  bậc hạ -2
      Thiền Tâm Đức   F0 104.4 Hz  ống 16.2 cm  bậc hạ -1

  Giọng mới nối vào CUỐI `VIENEU_PRESETS`: thứ tự các giọng cũ không đổi, nên mọi phép so hoà giữa
  chúng vẫn ra như trước.
- Mở lại Xuân Vĩnh: *"trong bản mới đã trở thành một giọng nam tự nhiên miền bắc"*. Vùng Nam → Bắc,
  bỏ khỏi `EXCLUDED_PRESETS`, và đo lại từ preview 3.8.1 (116,2 Hz / 16,6 cm → 103,2 Hz / 16,3 cm);
  preview mới thay preview cũ.
- Adam bựa và Mạnh Dũng hạ cao độ như Thanh Bình, chủ sách chọn -2 (nghe -1..-4).
- Tốc độ (nghe ×1,00..×1,20): Đức Trí ×1,10, Thiền Tâm Đức ×1,05, Kim Thanh ×1,10, Mỹ Duyên giữ.
- Nhịp riêng cho cổng (`PRESET_PACE_SCALE`), đo ở đúng nấc ấy trên 25 câu thử so với trung vị 7 giọng
  đang chạy (15,64 kt/s): Đức Trí 0,807, Thiền Tâm Đức 0,788, Kim Thanh 0,770, Mỹ Duyên 0,810.

## Trúc Ly đổi giọng ở 3.8.1

So bản thu THẬT của cùng 5 câu giữa 3.3.0 và 3.8.1: sáu giọng đang chạy lệch dưới 0,7 nửa cung, riêng
Trúc Ly lên 219,5 → 257,0 Hz (+2,7 nửa cung) và ống thanh 14,98 → 14,39 cm. Chủ sách chấm "như cũ"
và đã quyết nâng cấp; bảng số phải theo giọng mà engine thật sự phát ra, nên F0 của Trúc Ly được đo lại
từ preview 3.8.1 (213,7 → 240,0 Hz) và preview mới thay preview cũ. Ống thanh thì GIỮ 14,7 dù preview đo
14,4: nó đặt thang formant, 14,4 dời bậc sáng nhất 1,148 → 1,125, mà cuốn 2 đang có người ghim ở 1,148
(24 project) - người kế tiếp nhận 1,125 sẽ nghe như anh em sinh đôi của người ấy.

## Làm tròn thang formant

`formant_variants_for_preset` kẹp bậc vào biên rồi làm tròn 3 chữ số, và làm tròn có thể bước RA NGOÀI một
biên không tròn: Quỳnh Anh (14,1 cm) có trần 14,1/12,8 = 1,1015625, bậc 1,16 kẹp thành 1,102. Không giọng cũ
nào dính (mọi bậc cũ đã nằm trong biên - `test_formant_range_follows_each_preset_vocal_tract` giữ điều ấy),
nên sửa chỉ lùi đúng những bậc bước ra ngoài, 0,001 vào trong.

## Phạm Tuyên không còn là giọng nam trầm nhất

Adam (87,1 Hz) và Đức Trí (98,2 Hz) đều trầm hơn. Bậc hạ của Phạm Tuyên GIỮ 0: ở cuốn 2 giọng ấy không
bao giờ vào vai nhân vật (người kể 000..303, rồi `other_narrators`), và đổi nó thì đổi thang của cuốn
1 đang dừng. Chỉ sửa lời chú thích cho đúng sự thật.
"""
import io
import shutil
import sys
from pathlib import Path

root = Path(sys.argv[1])
p = root / "ebook_reader" / "voice_catalog.py"
s = io.open(p, encoding="utf-8").read()


def replace_once(old: str, new: str) -> None:
    global s
    assert s.count(old) == 1, f"khong khop mot lan duy nhat: {old.splitlines()[0]!r}"
    s = s.replace(old, new, 1)


# ------------------------------------------------------------------ giọng mới, cuối tuple
replace_once('''        "name": "Thùy Dung", "gender": GENDER_FEMALE, "region": REGION_SOUTH,
        "style": STYLE_NEWS, "description": "Nữ · Nam · Tin tức",
    },
)
''', '''        "name": "Thùy Dung", "gender": GENDER_FEMALE, "region": REGION_SOUTH,
        "style": STYLE_NEWS, "description": "Nữ · Nam · Tin tức",
    },
    # VieNeu 3.8.1, nhận ngày 2026-09-18 sau khi chủ sách nghe từng giọng.
    {
        "name": "Adam", "gender": GENDER_MALE, "region": REGION_SOUTH,
        "style": STYLE_NATURAL, "description": "Nam · Nam · Tự nhiên",
    },
    {
        "name": "Adam bựa", "gender": GENDER_MALE, "region": REGION_NORTH,
        "style": STYLE_NATURAL, "description": "Nam · Bắc · Tự nhiên",
    },
    {
        "name": "Anh Khôi", "gender": GENDER_MALE, "region": REGION_NORTH,
        "style": STYLE_STORY, "description": "Nam · Bắc · Kể chuyện",
    },
    {
        "name": "Đức Trí", "gender": GENDER_MALE, "region": REGION_SOUTH,
        "style": STYLE_STORY, "description": "Nam · Nam · Kể chuyện",
    },
    {
        "name": "Kim Thanh", "gender": GENDER_FEMALE, "region": REGION_SOUTH,
        "style": STYLE_STORY, "description": "Nữ · Nam · Kể chuyện",
    },
    {
        "name": "Mạnh Dũng", "gender": GENDER_MALE, "region": REGION_NORTH,
        "style": STYLE_NATURAL, "description": "Nam · Bắc · Tự nhiên",
    },
    {
        "name": "Minh Quân Pro", "gender": GENDER_MALE, "region": REGION_NORTH,
        "style": STYLE_NATURAL, "description": "Nam · Bắc · Tự nhiên",
    },
    {
        "name": "Mỹ Duyên", "gender": GENDER_FEMALE, "region": REGION_SOUTH,
        "style": STYLE_STORY, "description": "Nữ · Nam · Kể chuyện",
    },
    {
        "name": "Ngọc Huyền", "gender": GENDER_FEMALE, "region": REGION_NORTH,
        "style": STYLE_NATURAL, "description": "Nữ · Bắc · Tự nhiên",
    },
    {
        "name": "Quỳnh Anh", "gender": GENDER_FEMALE, "region": REGION_NORTH,
        "style": STYLE_STORY, "description": "Nữ · Bắc · Kể chuyện",
    },
    {
        "name": "Thiền Tâm Đức", "gender": GENDER_MALE, "region": REGION_NORTH,
        "style": STYLE_STORY, "description": "Nam · Bắc · Kể chuyện",
    },
)
''')

# ------------------------------------------------------------------ Xuân Vĩnh: Bắc, và không còn bị cấm
replace_once('''        "name": "Xuân Vĩnh", "gender": GENDER_MALE, "region": REGION_SOUTH,
        "style": STYLE_NATURAL, "description": "Nam · Nam · Tự nhiên",
''', '''        "name": "Xuân Vĩnh", "gender": GENDER_MALE, "region": REGION_NORTH,
        "style": STYLE_NATURAL, "description": "Nam · Bắc · Tự nhiên",
''')
replace_once('''# Presets barred from every role, for the same kind of reason the Central region is barred:
# a Vietnamese listener judged them, and that judgement is not something the code can
# second-guess. Xuân Vĩnh was first given a ranking penalty, which only made it a last
# resort rather than never - the listener's answer was that it should not be reachable at
# all, in any role, at any warp.
EXCLUDED_PRESETS = frozenset({"Xuân Vĩnh"})
''', '''# Presets barred from every role, for the same kind of reason the Central region is barred:
# a Vietnamese listener judged them, and that judgement is not something the code can
# second-guess. Xuân Vĩnh was first given a ranking penalty, which only made it a last
# resort rather than never - the listener's answer was that it should not be reachable at
# all, in any role, at any warp.
#
# Empty since VieNeu 3.8.1 (2026-09-18): the same listener heard Xuân Vĩnh again and found
# it had become a natural Northern male voice, "very good", and reopened it. The set stays
# so the next such verdict has somewhere to go.
EXCLUDED_PRESETS: frozenset[str] = frozenset()
''')

# ------------------------------------------------------------------ bảng số
replace_once('''PRESET_VOCAL_TRACT_CM = {
    "Phạm Tuyên": 16.5,
    "Thanh Bình": 16.9,
    "Xuân Vĩnh": 16.6,
    "Thái Sơn": 16.7,
    "Quang Sơn": 16.4,
    "Trúc Ly": 14.7,
''', '''PRESET_VOCAL_TRACT_CM = {
    "Phạm Tuyên": 16.5,
    "Thanh Bình": 16.9,
    # Xuân Vĩnh re-measured from its VieNeu 3.8.1 preview (was 16.6). Trúc Ly measures 14.4 on
    # its 3.8.1 preview but stays at 14.7 on purpose: the length sets its formant ladder, and
    # 14.4 would move its brightest step from 1.148 to 1.125 while book 2 has a character
    # pinned at 1.148 (24 projects) - the next one cast at 1.125 would sound like a twin.
    "Xuân Vĩnh": 16.3,
    "Thái Sơn": 16.7,
    "Quang Sơn": 16.4,
    "Trúc Ly": 14.7,
''')
replace_once('''    "Ngọc Trân": 15.5,
}
# A warp by ratio r reads as a vocal tract of length L/r''', '''    "Ngọc Trân": 15.5,
    "Adam": 16.7,
    "Adam bựa": 16.4,
    "Anh Khôi": 16.5,
    "Đức Trí": 16.6,
    "Kim Thanh": 13.6,
    "Mạnh Dũng": 16.6,
    "Minh Quân Pro": 16.6,
    "Mỹ Duyên": 14.8,
    "Ngọc Huyền": 14.2,
    "Quỳnh Anh": 14.1,
    "Thiền Tâm Đức": 16.2,
}
# A warp by ratio r reads as a vocal tract of length L/r''')
replace_once('''PRESET_PREVIEW_MEDIAN_PITCH_HZ = {
    "Phạm Tuyên": 100.6,
    "Xuân Vĩnh": 116.2,
''', '''PRESET_PREVIEW_MEDIAN_PITCH_HZ = {
    "Phạm Tuyên": 100.6,
    # Re-measured from the 3.8.1 preview (was 116.2), like Trúc Ly below (was 213.7).
    "Xuân Vĩnh": 103.2,
''')
replace_once('''    "Trúc Ly": 213.7,
    "Đoan Trang": 225.8,
    "Thục Đoan": 246.2,
}
''', '''    "Trúc Ly": 240.0,
    "Đoan Trang": 225.8,
    "Thục Đoan": 246.2,
    "Adam": 87.1,
    "Adam bựa": 146.9,
    "Anh Khôi": 109.6,
    "Đức Trí": 98.2,
    "Kim Thanh": 230.6,
    "Mạnh Dũng": 145.6,
    "Minh Quân Pro": 151.7,
    "Mỹ Duyên": 232.4,
    "Ngọc Huyền": 207.7,
    "Quỳnh Anh": 212.9,
    "Thiền Tâm Đức": 104.4,
}
''')
replace_once('''PRESET_MIN_PITCH_SEMITONES = {
    # Phạm Tuyên is already the lowest measured male preset; lowering it reduces intelligibility.
    "Phạm Tuyên": 0,
''', '''PRESET_MIN_PITCH_SEMITONES = {
    # Set when Phạm Tuyên was the lowest measured male preset, since lowering the lowest voice
    # costs intelligibility. Adam (87.1 Hz) and Đức Trí (98.2 Hz) are lower now; it stays 0
    # because it never plays a character in book 2 and moving it would move book 1's ladders.
    "Phạm Tuyên": 0,
''')
replace_once('''    "Thục Đoan": -2,
}
VOICE_PREVIEW_FILENAMES = {''', '''    "Thục Đoan": -2,
    # Same rule, applied by `scripts/propose_a_new_voice.py`: the lowest male voice 0, a male
    # voice within 3.5 semitones of it -1, everything else -2.
    "Adam": 0,
    "Adam bựa": -2,
    "Anh Khôi": -2,
    "Đức Trí": -1,
    "Kim Thanh": -2,
    "Mạnh Dũng": -2,
    "Minh Quân Pro": -2,
    "Mỹ Duyên": -2,
    "Ngọc Huyền": -2,
    "Quỳnh Anh": -2,
    "Thiền Tâm Đức": -1,
}
VOICE_PREVIEW_FILENAMES = {''')
replace_once('''    "Ngọc Trân": "ngoc_tran.wav",
}
''', '''    "Ngọc Trân": "ngoc_tran.wav",
    "Adam": "adam.wav",
    "Adam bựa": "adam_bua.wav",
    "Anh Khôi": "anh_khoi.wav",
    "Đức Trí": "duc_tri.wav",
    "Kim Thanh": "kim_thanh.wav",
    "Mạnh Dũng": "manh_dung.wav",
    "Minh Quân Pro": "minh_quan_pro.wav",
    "Mỹ Duyên": "my_duyen.wav",
    "Ngọc Huyền": "ngoc_huyen.wav",
    "Quỳnh Anh": "quynh_anh.wav",
    "Thiền Tâm Đức": "thien_tam_duc.wav",
}
''')

# ------------------------------------------------------------------ số chủ sách chọn bằng tai
replace_once('''# only Thanh Bình wanted correcting: at -4 semitones it reads calmer and more suited to
# storytelling. The other presets are already right at their natural register.
PRESET_BASE_PITCH_SEMITONES = {
    "Thanh Bình": -4,
}
''', '''# only Thanh Bình wanted correcting: at -4 semitones it reads calmer and more suited to
# storytelling. The other presets are already right at their natural register.
#
# Two of the VieNeu 3.8.1 voices wanted the same correction (2026-09-18): the listener heard
# Adam bựa and Mạnh Dũng at -1..-4 and chose -2 for both.
PRESET_BASE_PITCH_SEMITONES = {
    "Thanh Bình": -4,
    "Adam bựa": -2,
    "Mạnh Dũng": -2,
}
''')
replace_once('''PRESET_SPEED_FACTOR: dict[str, float] = {}
''', '''PRESET_SPEED_FACTOR: dict[str, float] = {
    # Heard at x1.00..x1.20 in steps of 0.05; Mỹ Duyên was kept at its own speed.
    "Đức Trí": 1.10,
    "Thiền Tâm Đức": 1.05,
    "Kim Thanh": 1.10,
}
''')
replace_once('''PRESET_PACE_SCALE: dict[str, float] = {}
''', '''PRESET_PACE_SCALE: dict[str, float] = {
    # Median chars/s at the chosen speed over 15.64, the median of the seven presets in use.
    # Those seven sit at 0.94-1.16 and need no entry.
    "Đức Trí": 0.807,
    "Thiền Tâm Đức": 0.788,
    "Kim Thanh": 0.770,
    "Mỹ Duyên": 0.810,
}
''')
replace_once('''    for step in CHARACTER_FORMANT_STEPS:
        ratio = round(min(max(step, lower), upper), 3)
        if all(abs(ratio - existing) > 0.01 for existing in variants):
''', '''    for step in CHARACTER_FORMANT_STEPS:
        ratio = round(min(max(step, lower), upper), 3)
        # Rounding can step just outside a bound that is not a round number - Quỳnh Anh's
        # ceiling is 14.1 / 12.8 = 1.1015625, which rounds to 1.102. Step back inside.
        if ratio > upper + 1e-6:
            ratio = round(ratio - 0.001, 3)
        elif ratio < lower - 1e-6:
            ratio = round(ratio + 0.001, 3)
        if all(abs(ratio - existing) > 0.01 for existing in variants):
''')
io.open(p, "w", encoding="utf-8").write(s)
print(f"da va {p}")

# Preview đi cùng: kho giọng đọc file theo tên trong VOICE_PREVIEW_FILENAMES, thiếu file là hỏng.
# Hai file cuối THAY file cũ: Xuân Vĩnh và Trúc Ly phát khác ở 3.8.1.
staged = root / "scripts" / "pending_patches" / "assets" / "voice_previews"
shipped = root / "ebook_reader" / "assets" / "voice_previews"
for filename in (
    "adam.wav",
    "adam_bua.wav",
    "anh_khoi.wav",
    "duc_tri.wav",
    "kim_thanh.wav",
    "manh_dung.wav",
    "minh_quan_pro.wav",
    "my_duyen.wav",
    "ngoc_huyen.wav",
    "quynh_anh.wav",
    "thien_tam_duc.wav",
    "xuan_vinh.wav",
    "truc_ly.wav",
):
    source = staged / filename
    assert source.exists(), f"thieu preview {source}"
    shutil.copy2(source, shipped / filename)
    print(f"da chep preview {filename}")


# ------------------------------------------------------------------ test ghi cứng kho cũ
def edit(relative: str, old: str, new: str) -> None:
    path = root / relative
    text = io.open(path, encoding="utf-8").read()
    assert text.count(old) == 1, f"{relative}: khong khop mot lan duy nhat: {old.splitlines()[0]!r}"
    io.open(path, "w", encoding="utf-8").write(text.replace(old, new, 1))
    print(f"da va {path}")


# Sáu nam không còn buộc phải dùng chung preset khi kho có mười giọng nam phân vai được ngoài
# người kể, nên phép thử "dùng lại preset thì phải khác formant" sẽ không còn gì để thử.
edit("tests/test_character_casting.py", '''    speakers.extend((f"Nam {index}", "male") for index in range(1, 7))
''', '''    # Đủ nhiều để buộc phải dùng lại preset: kho có mười giọng nam phân vai được ngoài người kể.
    speakers.extend((f"Nam {index}", "male") for index in range(1, 21))
''')
edit("tests/test_character_casting.py", '''    # The Southern natural male voice is Xuân Vĩnh, which a listener excluded outright,
    # so that rank is simply absent rather than filled by someone else.
    assert male_order == [
        (REGION_NORTH, STYLE_NATURAL),
        (REGION_NORTH, STYLE_STORY),
        (REGION_SOUTH, STYLE_STORY),
    ]
    assert female_order == [
        (REGION_NORTH, STYLE_NATURAL),
        (REGION_NORTH, STYLE_NATURAL),
        (REGION_NORTH, STYLE_STORY),
        (REGION_SOUTH, STYLE_STORY),
    ]
''', '''    # Natural before storytelling, North before South within each. Xuân Vĩnh is back as a
    # Northern natural voice since VieNeu 3.8.1, and Adam is the one Southern natural male.
    assert male_order == [
        *[(REGION_NORTH, STYLE_NATURAL)] * 5,
        (REGION_SOUTH, STYLE_NATURAL),
        *[(REGION_NORTH, STYLE_STORY)] * 3,
        *[(REGION_SOUTH, STYLE_STORY)] * 2,
    ]
    assert female_order == [
        *[(REGION_NORTH, STYLE_NATURAL)] * 3,
        *[(REGION_NORTH, STYLE_STORY)] * 2,
        *[(REGION_SOUTH, STYLE_STORY)] * 3,
    ]
''')
edit("tests/test_character_casting.py", '''        "Trúc Ly": -2,
        "Đoan Trang": -2,
        "Thục Đoan": -2,
    }
    assert pitch_variants_for_preset("Phạm Tuyên", 2) == (0, 1, 2)
''', '''        "Trúc Ly": -2,
        "Đoan Trang": -2,
        "Thục Đoan": -2,
        "Adam": 0,
        "Adam bựa": -2,
        "Anh Khôi": -2,
        "Đức Trí": -1,
        "Kim Thanh": -2,
        "Mạnh Dũng": -2,
        "Minh Quân Pro": -2,
        "Mỹ Duyên": -2,
        "Ngọc Huyền": -2,
        "Quỳnh Anh": -2,
        "Thiền Tâm Đức": -1,
    }
    assert pitch_variants_for_preset("Phạm Tuyên", 2) == (0, 1, 2)
''')
# Mười giọng không phải tin tức trước 3.8.1, hai mươi mốt sau: 11 giọng mới; Xuân Vĩnh vốn đã nằm
# trong danh sách người kể, chỉ bị cấm vào vai.
edit("tests/test_gui_layout.py", "    assert len(available_narrators) == 10\n", "    assert len(available_narrators) == 21\n")
edit("tests/test_gui_layout.py", "    assert len(VOICE_PREVIEW_FILENAMES) == 10\n", "    assert len(VOICE_PREVIEW_FILENAMES) == 21\n")
edit("tests/test_gui_layout.py", "    assert len(all_available) == 10\n", "    assert len(all_available) == 21\n")
edit(
    "tests/test_gui_layout.py",
    '''    assert available == {"Trúc Ly", "Đoan Trang", "Ngọc Linh", "Thục Đoan", "Ngọc Trân"}
''',
    '''    assert available == {
        "Trúc Ly", "Đoan Trang", "Ngọc Linh", "Thục Đoan", "Ngọc Trân",
        "Kim Thanh", "Mỹ Duyên", "Ngọc Huyền", "Quỳnh Anh",
    }
''',
)
# Làm đầy một preset nam cần tới 7 bậc x 10 preset lượt cast, không còn vừa trong 40.
edit("tests/test_wrap_prefers_a_stranger.py", "    for index in range(40):\n", "    for index in range(200):\n")
