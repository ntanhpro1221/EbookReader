"""Vá character_registry.py: giọng mang PITCH TRẺ CON không thuộc về người mà người nghe đã ghim là NGƯỜI LỚN.

Chạy: python patch_a_child_pitched_voice_does_not_belong_to_an_adult.py <root>

## Vì sao (20-09, 15:4x)

`_drop_pins_that_contradict_a_person` bỏ giọng ghim khi nó trái PHÁI mà người nghe đã ghim, và docstring của nó nói
rõ vì sao KHÔNG có luật thứ hai cho tuổi:

    "nhìn `voice_key` không phân biệt được preset nữ dành cho một đứa trẻ với preset nữ dành cho một phụ nữ
     trưởng thành, và đoán chính là thứ đã tạo ra cả lớp lỗi này."

Đúng với **formant**, sai với **pitch** - và đo được:

| | khớp đúng một phép biến đổi tuổi | không khớp tuổi nào |
|---|---|---|
| formant của 117 `voice_key` | 30 | **87** |
| pitch của 117 `voice_key` | **108** | 9 |

Formant bị bộ cấp giọng dùng để TÁCH hai người chung preset (`thanh_binh_f090` so với `f097`, `f100`), nên nó
không nói gì về tuổi. Pitch thì gần như chỉ đến từ tuổi. Và pitch TRẺ CON là dấu hiệu sắc nhất trong đó:

    ngoc_linh + female:  child f109 p+4 | teen f096 p+1 | young/adult f100 p+0 | elderly f100 p-3

Đếm trên lô 10: **đúng 1 trong 266** nhân vật có giọng ghim mang pitch trẻ con - KAELYN, `preset_ngoc_linh_f109_p+04`,
23 câu ở chương 140-144. Bà ấy là vợ của quản gia Nam tước ("thưa phu nhân", "Người phụ nữ gật đầu"), bị model gán
`age=child`, và tôi đã ghim `--age adult` giữa lô 10. Nhưng ghim ấy KHÔNG có tác dụng: luật hiện tại chỉ so phái,
mà preset nữ khớp nhãn nữ, nên giọng bé gái được giữ lại. **Một ghim của người nghe không làm gì cả** - đúng loại
lỗi im lặng mà luật kia sinh ra để dọn.

Vá: thêm đúng MỘT điều kiện nữa, hẹp nhất có thể - pitch của giọng ghim bằng pitch TRẺ CON của chính preset ấy,
trong khi người nghe đã ghim một tuổi KHÔNG phải trẻ con. Không dùng formant (87/117 là bước tách giọng). Không
suy ra "giọng này dành cho tuổi nào" (đó là chỗ docstring cũ cấm đoán, và cấm đúng).

Đo bản vá trên dữ liệu thật của lô 10 (266 giọng ghim, 11 ghim phái, 2 ghim tuổi): bỏ **2** giọng - CHRISTOPHER
(luật cũ đã bỏ, vì trái phái) và KAELYN (luật mới). Không ca nào khác bị chạm.
"""
import io
import sys
from pathlib import Path

root = Path(sys.argv[1])


def patch(path: Path, old: str, new: str) -> None:
    source = io.open(path, encoding="utf-8").read()
    assert source.count(old) == 1, f"khong khop mot lan duy nhat trong {path.name}: {old.splitlines()[0]!r}"
    io.open(path, "w", encoding="utf-8").write(source.replace(old, new, 1))
    print(f"da va {path}")


patch(
    root / "ebook_reader" / "character_registry.py",
    '''def _drop_pins_that_contradict_a_person(''',
    '''VOICE_KEY_SUFFIX_PATTERN = re.compile(r"^preset_(?P<body>.+)_f(?P<formant>\\d+)_p(?P<pitch>[+-]\\d+)$")


def voice_is_child_pitched(voice_key: str) -> bool:
    """Giọng này có mang đúng PITCH TRẺ CON của preset nó dùng không?

    Chỉ đọc pitch, cố ý không đọc formant: đo trên 117 `voice_key` của cuốn 2 thì 87 formant không khớp phép
    biến đổi tuổi nào - bộ cấp giọng dùng formant để TÁCH hai người chung preset - còn 108 pitch thì khớp.
    Và pitch trẻ con là dấu sắc nhất: đúng 1 trong 266 giọng ghim mang nó.
    """
    match = VOICE_KEY_SUFFIX_PATTERN.match(str(voice_key))
    if match is None:
        return False
    pitch = int(match.group("pitch"))
    for preset in VIENEU_PRESETS:
        if _preset_slug(str(preset["name"])) != match.group("body"):
            continue
        gender = str(preset["gender"])
        child = age_pitch_semitones("child", gender, str(preset["name"]))
        adult = age_pitch_semitones("adult", gender, str(preset["name"]))
        return pitch == child != adult
    return False


def _drop_pins_that_contradict_a_person(''',
)

patch(
    root / "ebook_reader" / "character_registry.py",
    '''        contradicts = bool(
            gender and preset and preset != gender and (age or "") != "child"
        )''',
    '''        contradicts = bool(
            gender and preset and preset != gender and (age or "") != "child"
        )
        # Luật THỨ HAI, thêm 20-09 và hẹp bằng một phép đo: giọng mang đúng pitch TRẺ CON của preset nó
        # dùng, trong khi người nghe đã ghim một tuổi KHÁC trẻ con. Không có nó thì ghim `--age adult` của
        # KAELYN không làm gì cả - preset nữ khớp nhãn nữ nên luật phái im lặng, và bà vẫn được đọc bằng
        # giọng bé gái. Chỉ đọc PITCH: formant là bước tách giọng (87/117 không khớp tuổi nào).
        child_pitched = bool(age and age != "child" and voice_is_child_pitched(voice_key))
        contradicts = contradicts or child_pitched''',
)

patch(
    root / "ebook_reader" / "character_registry.py",
    '''        log(
            f"Bỏ giọng ghim của {key}: {voice_key} là preset {preset}, còn người nghe đã ghim"
            f" {gender}" + (f"/{age}" if age else "") + " - cấp lại giọng."
        )''',
    '''        reason = (
            f"mang pitch trẻ con mà người nghe đã ghim tuổi {age}"
            if child_pitched
            else f"là preset {preset}, còn người nghe đã ghim {gender}" + (f"/{age}" if age else "")
        )
        log(f"Bỏ giọng ghim của {key}: {voice_key} {reason} - cấp lại giọng.")''',
)

test = root / "tests" / "test_a_child_pitched_voice_does_not_belong_to_an_adult.py"
test.write_text('''"""Giọng mang pitch trẻ con bị bỏ khi người nghe đã ghim một tuổi khác trẻ con."""
from __future__ import annotations

from ebook_reader.character_registry import _drop_pins_that_contradict_a_person, voice_is_child_pitched


class _Events:
    def __init__(self) -> None:
        self.rows: list[tuple] = []

    def event(self, level: str, code: str, message: str, detail: dict) -> None:
        self.rows.append((level, code, message, detail))


def test_the_child_pitch_is_read_from_the_voice_key() -> None:
    assert voice_is_child_pitched("preset_ngoc_linh_f109_p+04") is True
    assert voice_is_child_pitched("preset_ngoc_linh_f100_p+00") is False
    # Formant khác mà pitch vẫn là pitch trẻ con -> vẫn là giọng trẻ con: formant là bước TÁCH giọng.
    assert voice_is_child_pitched("preset_ngoc_linh_f093_p+04") is True
    assert voice_is_child_pitched("narrator") is False
    assert voice_is_child_pitched("preset_khong_co_that_f100_p+00") is False


def test_a_pinned_adult_loses_a_child_pitched_voice() -> None:
    events = _Events()
    logs: list[str] = []
    kept = _drop_pins_that_contradict_a_person(
        events,
        {"KAELYN": "preset_ngoc_linh_f109_p+04"},
        {"KAELYN": "female"},
        {"KAELYN": "adult"},
        logs.append,
    )
    assert kept == {}
    assert "pitch trẻ con" in logs[0]
    assert events.rows and events.rows[0][1] == "CASTING_PIN_CONTRADICTS_A_PERSON"


def test_a_pinned_child_keeps_it() -> None:
    logs: list[str] = []
    kept = _drop_pins_that_contradict_a_person(
        _Events(),
        {"EVERAN": "preset_ngoc_linh_f109_p+04"},
        {"EVERAN": "male"},
        {"EVERAN": "child"},
        logs.append,
    )
    assert kept == {"EVERAN": "preset_ngoc_linh_f109_p+04"}, "trẻ con đọc bằng preset nữ kéo cao là có chủ ý"
    assert logs == []


def test_an_adult_voice_for_a_pinned_adult_is_untouched() -> None:
    kept = _drop_pins_that_contradict_a_person(
        _Events(),
        {"NATASHA": "preset_ngoc_linh_f100_p+00"},
        {"NATASHA": "female"},
        {"NATASHA": "adult"},
        lambda line: None,
    )
    assert kept == {"NATASHA": "preset_ngoc_linh_f100_p+00"}


def test_nobody_pinned_an_age_so_nothing_is_dropped() -> None:
    kept = _drop_pins_that_contradict_a_person(
        _Events(),
        {"AI": "preset_ngoc_linh_f109_p+04"},
        {},
        {},
        lambda line: None,
    )
    assert kept == {"AI": "preset_ngoc_linh_f109_p+04"}, "không ai ghim thì không kết tội"
''', encoding="utf-8")
print(f"da viet {test}")
