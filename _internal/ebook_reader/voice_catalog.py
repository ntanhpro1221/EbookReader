from __future__ import annotations

import math

from typing import Any


GENDER_MALE = "male"
GENDER_FEMALE = "female"
GENDER_UNKNOWN = "unknown"
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
# The transform has its own limit, independent of anatomy: PSOLA resampling degrades once
# the ratio moves far from unity, whatever the voice started as. The listener found that
# limit asymmetric, and mirrored between the genders - a male voice tolerates being
# brightened further than it tolerates being deepened, and a female voice the reverse.
# The usable range is the intersection of the two constraints: anatomy says how far this
# particular voice may be stretched, the algorithm says how far anything may be.
VOICE_VARIANT_DEVIATION_BY_GENDER = {
    GENDER_MALE: (0.15, 0.20),
    GENDER_FEMALE: (0.20, 0.15),
}
FORMANT_RATIO_MIN = 1.0 - 0.20
FORMANT_RATIO_MAX = 1.0 + 0.20


def voice_variant_deviation(preset_name: str) -> tuple[float, float]:
    """How far down and up the transform may take this preset, before anatomy applies."""
    for preset in VIENEU_PRESETS:
        if preset["name"] == preset_name:
            gender = str(preset["gender"])
            break
    else:
        gender = GENDER_MALE
    return VOICE_VARIANT_DEVIATION_BY_GENDER.get(
        gender,
        VOICE_VARIANT_DEVIATION_BY_GENDER[GENDER_MALE],
    )
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


# F0 and formants both feed the impression of a large speaker, so a preset whose register
# was lowered has already spent part of that budget and has less room left to be deepened
# further. Anatomy alone cannot see this: lowering F0 leaves the formants, and therefore
# the estimated vocal tract, exactly where they were. The rate comes from listening -
# Thanh Bình dropped 4 semitones needed its floor raised from 0.86 to 0.90, so a semitone
# is worth 0.01 of formant ratio. The whole perceptual window moves; the algorithmic limit
# still caps it.
REGISTER_FORMANT_TRADE_PER_SEMITONE = 0.01


# --- age ---------------------------------------------------------------------------
#
# A character's age was analysed, stored, and then thrown away at casting time, so a
# child was read by whichever adult preset came next in the rotation. A listener put it
# plainly: the boy sounded like an old uncle.
#
# Age is two separate acoustic facts and they need different machinery.
#
# Vocal tract length, which sets the formants and therefore the apparent size of the
# speaker. From an anatomic MRI-based age model (Vorperian et al., PMC5966313): 12.3 cm
# at six years, 13.0 at eight, 13.8 at ten, 14.5 at twelve, against 17.6 for an adult man
# and 15.6 for an adult woman. Two things follow. Before puberty the sexes barely differ,
# so a boy must be cast from the *shortest* presets - the female ones at 13.9-15.5 cm -
# rather than from a male preset that would need a 1.29 warp to reach a child and would
# sound ruined long before it got there. And adult ageing does almost nothing here:
# "formant frequencies change little if at all across several decades of adult life"
# (PMC5832520), so an elderly character is not a formant problem at all.
VOCAL_TRACT_CM_BY_AGE: dict[str, dict[str, float]] = {
    # roughly eight years old, where a child speaking role usually sits
    "child": {GENDER_MALE: 13.0, GENDER_FEMALE: 12.7, GENDER_UNKNOWN: 12.9},
    # roughly fourteen: the male pharynx has begun its growth, the female has nearly
    # finished, which is where the sexes start to separate
    "teen": {GENDER_MALE: 15.5, GENDER_FEMALE: 14.5, GENDER_UNKNOWN: 15.0},
}

# Speaking F0 for an age, as an absolute target in hertz rather than an offset.
#
# It was an offset first - "+3 semitones, because a child speaks around 250 Hz against an
# adult woman's 205" - and that was wrong in a way a listener heard immediately. Applied to
# a male preset sitting at 120 Hz, +3 semitones lands at 143 Hz, nowhere near a child. The
# result was a 13.8 cm vocal tract speaking at 143 Hz: a combination no human throat can
# produce, and the ear rejects it as a fault rather than as a young voice. The listener
# described exactly that - the male presets "rè", crackly, "nghe như lỗi" - while the two
# presets that already sit at 246 Hz were called simply good.
#
# Children aged six to ten speak at 245-262 Hz with no significant difference between boys
# and girls. Ageing is not symmetric and the common intuition is half wrong: measured
# across cohorts (PMC5832520), women fall from about 205 Hz to 170 while men *rise* from
# 108 to about 125, so an elderly man reads higher than his younger self.
# Boys sit below girls even before puberty - a study of six-to-ten-year-olds measured
# about 262 Hz for boys against 281 for girls - and a listener heard the same thing from
# the other direction: a male preset carried to a single shared target read as a child but
# not as a *boy*, and asked for it slightly deeper. Both agree, so the target splits.
AGE_TARGET_PITCH_HZ: dict[str, dict[str, float]] = {
    "child": {GENDER_MALE: 240.0, GENDER_FEMALE: 258.0, GENDER_UNKNOWN: 248.0},
    "teen": {GENDER_MALE: 190.0, GENDER_FEMALE: 220.0, GENDER_UNKNOWN: 205.0},
    "elderly": {GENDER_MALE: 125.0, GENDER_FEMALE: 170.0, GENDER_UNKNOWN: 145.0},
}

# Usable, but only once everything else is taken. A listener judged these good enough to
# keep and not good enough to reach for: a slight crackle in one, a maturity the age warp
# cannot undo in the other. Unlike EXCLUDED_PRESETS this is a demotion, not a bar - a book
# with more characters than clean voices should still cast them rather than run out.
#
# It sorts ahead of usage count deliberately. A gentler weighting would let a demoted
# preset win as soon as the clean ones had each been used once, which is the second
# character in a chapter, and that is not what "bottom of the list" means.
LAST_RESORT_PRESETS = frozenset({"Thái Sơn", "Thục Đoan"})

# Casting prefers the preset needing the smallest age pitch shift, bucketed this wide.
# Four semitones is roughly 0.2 MOS by the measurements in docs/CHILD_VOICE_TRANSFORM.md -
# wide enough that a one-semitone edge cannot outrank voice diversity or tract fit, narrow
# enough that the gap between a +2 preset and a +11 one still decides.
AGE_PITCH_RANK_BUCKET = 4

# How far a preset's own F0 may be carried toward an age target.
#
# This was 6, invented rather than measured, and it was wrong: it barred all three male
# presets from the child pool, one of them by 2.3 semitones. Asked to judge them carried
# the whole way instead - +8.3, +12.6 and +15.8 - a listener called every one of them
# childlike, the deepest shift among the best. So the limit is set where the presets
# actually stop working rather than where a round number sat.
AGE_PITCH_MAX_SEMITONES = 16.0


# Presets barred from every role, for the same kind of reason the Central region is barred:
# a Vietnamese listener judged them, and that judgement is not something the code can
# second-guess. Xuân Vĩnh was first given a ranking penalty, which only made it a last
# resort rather than never - the listener's answer was that it should not be reachable at
# all, in any role, at any warp.
EXCLUDED_PRESETS = frozenset({"Xuân Vĩnh"})


def vocal_tract_target_cm(age: str, gender: str) -> float | None:
    """The tract length a character of this age should read as, or None for an adult."""
    by_gender = VOCAL_TRACT_CM_BY_AGE.get(str(age))
    if by_gender is None:
        return None
    return by_gender.get(str(gender), by_gender[GENDER_UNKNOWN])


def age_pitch_semitones(age: str, gender: str, preset_name: str = "") -> int:
    """The shift that carries this preset's own F0 to the target for this age.

    Computed per preset rather than fixed, because presets start 150 Hz apart: the same
    offset that lands one voice in a child's range leaves another at half of it.
    """
    by_gender = AGE_TARGET_PITCH_HZ.get(str(age))
    if by_gender is None:
        return 0
    target = float(by_gender.get(str(gender), by_gender[GENDER_UNKNOWN]))
    source = PRESET_PREVIEW_MEDIAN_PITCH_HZ.get(preset_name)
    if not source:
        return 0
    steps = 12.0 * math.log2(target / float(source))
    steps = max(-AGE_PITCH_MAX_SEMITONES, min(AGE_PITCH_MAX_SEMITONES, steps))
    # Rounded toward the preset's own pitch, never past the target. The shift is stored in
    # whole semitones, and rounding to the nearest one overshot: Thái Sơn needed 11.9 to
    # reach a boy's 240 Hz, took 12, and landed at 252 - the highest of the three male
    # presets, which a listener heard at once as "thanh mảnh hơn cả mấy giọng nam khác".
    # Falling short leaves a voice a little closer to its own register, which is the safer
    # side of a target that is itself a range.
    return int(math.floor(steps) if steps > 0 else math.ceil(steps))


def preset_reaches_age_pitch(preset_name: str, age: str, gender: str) -> bool:
    """Whether this preset can reach the age's F0 without an implausible shift.

    A voice that cannot is not a candidate for the age at all. Warping its vocal tract to
    a child's size while its pitch stays adult produces a combination no throat can make,
    and it is heard as a defect rather than as a child.
    """
    by_gender = AGE_TARGET_PITCH_HZ.get(str(age))
    source = PRESET_PREVIEW_MEDIAN_PITCH_HZ.get(preset_name)
    if by_gender is None or not source:
        return True
    target = float(by_gender.get(str(gender), by_gender[GENDER_UNKNOWN]))
    return abs(12.0 * math.log2(target / float(source))) <= AGE_PITCH_MAX_SEMITONES


def formant_ratio_for_age(preset_name: str, age: str, gender: str) -> float:
    """The warp that brings this preset to the target length, within what it can do.

    Clamped to the preset's own usable range rather than reaching for the target at any
    cost: a warp that lands the arithmetic but wrecks the voice is not an improvement.
    """
    target = vocal_tract_target_cm(age, gender)
    length = PRESET_VOCAL_TRACT_CM.get(preset_name)
    if target is None or length is None:
        return 1.0
    lower, upper = formant_ratio_bounds_for_preset(preset_name)
    return max(lower, min(upper, length / target))


def preset_age_reach(preset_name: str, age: str, gender: str) -> float:
    """How far this preset falls short of the target length, in cm. Lower is better."""
    target = vocal_tract_target_cm(age, gender)
    length = PRESET_VOCAL_TRACT_CM.get(preset_name)
    if target is None or length is None:
        return 0.0
    return abs(length / formant_ratio_for_age(preset_name, age, gender) - target)


def formant_ratio_bounds_for_preset(preset_name: str) -> tuple[float, float]:
    """The warp range that keeps this preset inside a plausible adult vocal tract.

    Three independent constraints intersect: anatomy bounds how far this particular tract
    may be stretched, the register shift moves that window because F0 already changed the
    perceived size, and the transform's own limit caps how far anything may be warped.
    """
    down, up = voice_variant_deviation(preset_name)
    algorithmic_low, algorithmic_high = 1.0 - down, 1.0 + up
    length = PRESET_VOCAL_TRACT_CM.get(preset_name)
    if length is None:
        return algorithmic_low, algorithmic_high
    register_offset = (
        -base_pitch_for_preset(preset_name) * REGISTER_FORMANT_TRADE_PER_SEMITONE
    )
    anatomical_low = length / VOCAL_TRACT_MAX_CM + register_offset
    anatomical_high = length / VOCAL_TRACT_MIN_CM + register_offset
    lower = max(algorithmic_low, anatomical_low)
    upper = min(algorithmic_high, anatomical_high)
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
        and preset["name"] not in EXCLUDED_PRESETS
    ]
    return sorted(candidates, key=casting_preset_priority)
