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
# Xuân Vĩnh is labelled Nam in the catalogue but a Vietnamese listener hears it as
# Central, and the measurements agree that it does not behave like its label. Across two
# full runs it produced 4 of the 6 failed segments from 22 attempts - an 18.2% failure
# rate with a median WER of 0.333 - while the other two Nam presets, Thái Sơn and Thục
# Đoan, sat at 0% and 0.114/0.086, and every remaining preset failed nothing at all. The
# problem is this voice, not its region, so it is excluded by name.
EXCLUDED_CASTING_PRESETS = frozenset({"Xuân Vĩnh"})
CHARACTER_PITCH_VARIANTS = (0, -1, 1, -2, 2)
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
        and preset["name"] not in EXCLUDED_CASTING_PRESETS
    ]
    return sorted(candidates, key=casting_preset_priority)
