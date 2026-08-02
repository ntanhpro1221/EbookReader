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
CHARACTER_PITCH_VARIANTS = (0, -1, 1, -2, 2)
DEFAULT_NARRATOR_BY_GENDER = {
    GENDER_MALE: "Thái Sơn",
    GENDER_FEMALE: "Ngọc Linh",
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


def casting_presets(gender: str, *, include_regional: bool) -> list[dict[str, str]]:
    candidates = [
        preset
        for preset in VIENEU_PRESETS
        if preset["gender"] == gender
        and preset["style"] != STYLE_NEWS
        and (include_regional or preset["region"] in {REGION_NORTH, REGION_SOUTH})
    ]
    return sorted(candidates, key=preset_priority)
