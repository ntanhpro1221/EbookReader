from __future__ import annotations

from typing import Any


GENDER_MALE = "male"
GENDER_FEMALE = "female"
REGION_NORTH = "Bắc"
REGION_SOUTH = "Nam"
REGION_CENTRAL = "Trung"
STYLE_NATURAL = "tu_nhien"
STYLE_STORY = "doc_truyen"
STYLE_NEWS = "tin_tuc"

REGION_PRIORITY = {
    REGION_NORTH: 0,
    REGION_SOUTH: 1,
    REGION_CENTRAL: 2,
}
STYLE_PRIORITY = {
    STYLE_NATURAL: 0,
    STYLE_STORY: 1,
}
# Central Vietnamese is the least mutually intelligible of the three dialects, and its
# tone system diverges most from the written Northern-standard orthography an audiobook
# reads from. Measured on committed audio, the Central presets missed tones on ordinary
# vocabulary rather than on names - "khốn kiếp" heard as "khôn kiêp", "thuần khiết" as
# "thuân khiệt" - and tone carries lexical meaning, so that is a comprehension cost for
# listeners, not only for ASR. The presets stay in the catalog because VieNeu offers them
# and older books may have locked them; they are simply never cast.
CASTING_REGIONS = frozenset({REGION_NORTH, REGION_SOUTH})
CHARACTER_PITCH_VARIANTS = (0, -1, 1, -2, 2)
# Formant warping is the axis that actually makes two characters sound like different
# people. Pitch does not: a listener compared the same sentence from -6 to +6 semitones,
# F0 from 106 Hz to 206 Hz, and heard the same person throughout. Both limits were set by
# ear - 0.82 sounds muffled, 1.30 starts to strain - and 1.00 comes first so a preset's
# first casting needs no transform at all, and therefore pays no vocoder cost.
# Base register per preset, applied to every casting of that voice. This is not a
# diversity mechanism - it is calibration. Shifting F0 reads as the same person in a
# different state (calm, hurried), not as a different person, so it belongs here rather
# than in the variant ladder. A Vietnamese listener went through every preset and found
# only Thanh Bình wanted correcting: at -4 semitones it reads calmer and more suited to
# storytelling. The other presets are already right at their natural register.
PRESET_BASE_PITCH_SEMITONES = {
    "Thanh Bình": -4,
}
# Vocal tract length per preset, in centimetres, estimated from the third formant of its
# own preview clip with the odd-quarter-wavelength tube model L = 5c / (4*F3). Measured
# with Praat: the male presets cluster tightly at 16.4-16.9 cm and the female ones at
# 13.9-15.5 cm, which is why one shared warp range is wrong in both directions - a male
# voice has little room left to go deeper and a female voice little room to go brighter.
PRESET_VOCAL_TRACT_CM = {
    "Phạm Tuyên": 16.5,
    "Thanh Bình": 16.9,
    "Xuân Vĩnh": 16.6,
    "Thái Sơn": 16.7,
    "Quang Sơn": 16.4,
    "Trúc Ly": 14.7,
    "Đoan Trang": 14.7,
    "Ngọc Linh": 13.9,
    "Thục Đoan": 15.0,
    "Ngọc Trân": 15.5,
}
# A warp by ratio r reads as a vocal tract of length L/r, so the usable range is whatever
# keeps that inside a plausible adult tract. The upper bound reproduces the limit a
# Vietnamese listener found by ear: Thanh Bình at 16.9 cm sounded muffled at 0.82, which
# is a 20.6 cm tract, and acceptable at 0.86, which is 19.7 cm.
VOCAL_TRACT_MIN_CM = 12.8
VOCAL_TRACT_MAX_CM = 19.7
FORMANT_RATIO_MIN = 0.70
FORMANT_RATIO_MAX = 1.35
# Ladder of relative steps, natural first so a preset's first casting is untouched and
# pays no processing at all. Each step is clamped into the preset's own usable range.
CHARACTER_FORMANT_STEPS = (1.00, 0.93, 1.08, 0.87, 1.16, 0.97, 1.04)
DEFAULT_NARRATOR_BY_GENDER = {
    GENDER_MALE: "Phạm Tuyên",
    GENDER_FEMALE: "Ngọc Linh",
}
PRESET_PREVIEW_MEDIAN_PITCH_HZ = {
    "Phạm Tuyên": 100.6,
    "Xuân Vĩnh": 116.2,
    "Thái Sơn": 120.7,
    "Quang Sơn": 138.2,
    "Thanh Bình": 155.1,
    "Ngọc Trân": 181.3,
    "Ngọc Linh": 204.7,
    "Trúc Ly": 213.7,
    "Đoan Trang": 225.8,
    "Thục Đoan": 246.2,
}
PRESET_MIN_PITCH_SEMITONES = {
    # Phạm Tuyên is already the lowest measured male preset; lowering it reduces intelligibility.
    "Phạm Tuyên": 0,
    "Xuân Vĩnh": -1,
    "Thái Sơn": -1,
    "Quang Sơn": -2,
    "Thanh Bình": -2,
    # Ngọc Trân is the lowest measured female preset, so keep its downward variant conservative.
    "Ngọc Trân": -1,
    "Ngọc Linh": -2,
    "Trúc Ly": -2,
    "Đoan Trang": -2,
    "Thục Đoan": -2,
}
VOICE_PREVIEW_FILENAMES = {
    "Phạm Tuyên": "pham_tuyen.wav",
    "Thanh Bình": "thanh_binh.wav",
    "Xuân Vĩnh": "xuan_vinh.wav",
    "Thái Sơn": "thai_son.wav",
    "Quang Sơn": "quang_son.wav",
    "Trúc Ly": "truc_ly.wav",
    "Đoan Trang": "doan_trang.wav",
    "Ngọc Linh": "ngoc_linh.wav",
    "Thục Đoan": "thuc_doan.wav",
    "Ngọc Trân": "ngoc_tran.wav",
}

VIENEU_PRESETS: tuple[dict[str, str], ...] = (
    {
        "name": "Phạm Tuyên", "gender": GENDER_MALE, "region": REGION_NORTH,
        "style": STYLE_NATURAL, "description": "Nam · Bắc · Tự nhiên",
    },
    {
        "name": "Thái Sơn", "gender": GENDER_MALE, "region": REGION_SOUTH,
        "style": STYLE_STORY, "description": "Nam · Nam · Kể chuyện",
    },
    {
        "name": "Thanh Bình", "gender": GENDER_MALE, "region": REGION_NORTH,
        "style": STYLE_STORY, "description": "Nam · Bắc · Kể chuyện",
    },
    {
        "name": "Xuân Vĩnh", "gender": GENDER_MALE, "region": REGION_SOUTH,
        "style": STYLE_NATURAL, "description": "Nam · Nam · Tự nhiên",
    },
    {
        "name": "Quang Sơn", "gender": GENDER_MALE, "region": REGION_CENTRAL,
        "style": STYLE_NATURAL, "description": "Nam · Trung · Tự nhiên",
    },
    {
        "name": "Minh Đức", "gender": GENDER_MALE, "region": REGION_NORTH,
        "style": STYLE_NEWS, "description": "Nam · Bắc · Tin tức",
    },
    {
        "name": "Minh Triết", "gender": GENDER_MALE, "region": REGION_SOUTH,
        "style": STYLE_NEWS, "description": "Nam · Nam · Tin tức",
    },
    {
        "name": "Ngọc Linh", "gender": GENDER_FEMALE, "region": REGION_NORTH,
        "style": STYLE_STORY, "description": "Nữ · Bắc · Kể chuyện",
    },
    {
        "name": "Thục Đoan", "gender": GENDER_FEMALE, "region": REGION_SOUTH,
        "style": STYLE_STORY, "description": "Nữ · Nam · Kể chuyện",
    },
    {
        "name": "Trúc Ly", "gender": GENDER_FEMALE, "region": REGION_NORTH,
        "style": STYLE_NATURAL, "description": "Nữ · Bắc · Tự nhiên",
    },
    {
        "name": "Đoan Trang", "gender": GENDER_FEMALE, "region": REGION_NORTH,
        "style": STYLE_NATURAL, "description": "Nữ · Bắc · Tự nhiên",
    },
    {
        "name": "Ngọc Trân", "gender": GENDER_FEMALE, "region": REGION_CENTRAL,
        "style": STYLE_NATURAL, "description": "Nữ · Trung · Tự nhiên",
    },
    {
        "name": "Mai Anh", "gender": GENDER_FEMALE, "region": REGION_NORTH,
        "style": STYLE_NEWS, "description": "Nữ · Bắc · Tin tức",
    },
    {
        "name": "Thùy Dung", "gender": GENDER_FEMALE, "region": REGION_SOUTH,
        "style": STYLE_NEWS, "description": "Nữ · Nam · Tin tức",
    },
)


def preset_by_name(name: str) -> dict[str, str]:
    for preset in VIENEU_PRESETS:
        if preset["name"] == name:
            return preset
    raise ValueError(f"Unknown VieNeu preset: {name!r}")


def preset_priority(preset: dict[str, Any]) -> tuple[int, int, str]:
    return (
        REGION_PRIORITY.get(str(preset.get("region", "")), len(REGION_PRIORITY)),
        STYLE_PRIORITY.get(str(preset.get("style", "")), len(STYLE_PRIORITY)),
        str(preset.get("name", "")).casefold(),
    )


def casting_preset_priority(preset: dict[str, Any]) -> tuple[int, int, int, str]:
    region = str(preset.get("region", ""))
    style = str(preset.get("style", ""))
    return (
        0 if style == STYLE_NATURAL else 1,
        REGION_PRIORITY.get(region, len(REGION_PRIORITY)),
        STYLE_PRIORITY.get(style, len(STYLE_PRIORITY)),
        str(preset.get("name", "")).casefold(),
    )


def base_pitch_for_preset(preset_name: str) -> int:
    """The calibrated reading register for this preset, in semitones."""
    return int(PRESET_BASE_PITCH_SEMITONES.get(preset_name, 0))


def formant_ratio_bounds_for_preset(preset_name: str) -> tuple[float, float]:
    """The warp range that keeps this preset inside a plausible adult vocal tract."""
    length = PRESET_VOCAL_TRACT_CM.get(preset_name)
    if length is None:
        return FORMANT_RATIO_MIN, FORMANT_RATIO_MAX
    lower = max(FORMANT_RATIO_MIN, length / VOCAL_TRACT_MAX_CM)
    upper = min(FORMANT_RATIO_MAX, length / VOCAL_TRACT_MIN_CM)
    return (lower, upper) if lower < upper else (1.0, 1.0)


def formant_variants_for_preset(preset_name: str) -> tuple[float, ...]:
    """Formant ratios this preset may be cast with, natural first, no duplicates.

    The ladder is relative, but the bounds are not: a preset already at the long end of
    the human range has little room left to go deeper, and one at the short end little
    room to go brighter. Clamping rather than sharing one range is the difference between
    a voice that sounds like a different person and one that sounds like no person at all.
    """
    lower, upper = formant_ratio_bounds_for_preset(preset_name)
    variants: list[float] = []
    for step in CHARACTER_FORMANT_STEPS:
        ratio = round(min(max(step, lower), upper), 3)
        if all(abs(ratio - existing) > 0.01 for existing in variants):
            variants.append(ratio)
    return tuple(variants) or (1.0,)


def pitch_variants_for_preset(preset_name: str, max_abs_semitones: int) -> tuple[int, ...]:
    maximum = max(0, int(max_abs_semitones))
    minimum = max(-maximum, int(PRESET_MIN_PITCH_SEMITONES.get(preset_name, -maximum)))
    variants = tuple(
        steps
        for steps in CHARACTER_PITCH_VARIANTS
        if minimum <= steps <= maximum
    )
    return variants or (0,)


def narrator_presets(
    gender: str | None = None,
    region: str | None = None,
) -> list[dict[str, str]]:
    candidates = [
        preset
        for preset in VIENEU_PRESETS
        if preset["style"] != STYLE_NEWS
        and (not gender or preset["gender"] == gender)
        and (not region or preset["region"] == region)
    ]
    preferred_order = {
        DEFAULT_NARRATOR_BY_GENDER[GENDER_MALE]: 0,
        DEFAULT_NARRATOR_BY_GENDER[GENDER_FEMALE]: 1,
    }
    return sorted(
        candidates,
        key=lambda preset: (
            preferred_order.get(preset["name"], len(preferred_order)),
            *preset_priority(preset),
        ),
    )


def casting_presets(gender: str) -> list[dict[str, str]]:
    """Every preset eligible for casting, best first.

    There is one region allowlist for every role. NPCs used to reach a wider pool that
    added the Central presets; that pool is gone with them, so the distinction would now
    only be a parameter that never changes anything.
    """
    candidates = [
        preset
        for preset in VIENEU_PRESETS
        if preset["gender"] == gender
        and preset["style"] != STYLE_NEWS
        and preset["region"] in CASTING_REGIONS
    ]
    return sorted(candidates, key=casting_preset_priority)
