from __future__ import annotations

import re
from collections import Counter, defaultdict
from typing import Any, Callable

from .analysis import (
    DIALOGUE_CLOSERS,
    DIALOGUE_OPENERS,
    LOCAL_SPEAKER_REQUEST_PREFIX,
    _canonical_speaker,
    _explicit_speaker_attribution,
    is_local_speaker,
    local_speaker_display,
    local_speaker_label,
)
from .database import (
    ProjectDB,
)
from .io_utils import slugify, stable_int
from .voice_catalog import (
    CASTING_REGIONS,
    AGE_PITCH_RANK_BUCKET,
    EXCLUDED_PRESETS,
    LAST_RESORT_PRESETS,
    STYLE_NEWS,
    VIENEU_PRESETS,
    casting_preset_priority,
    casting_presets,
    child_voice_preference,
    preset_by_name,
    base_pitch_for_preset,
    formant_ratio_for_age,
    formant_variants_for_preset,
    age_pitch_semitones,
    preset_reaches_age_pitch,
    preset_age_reach,
)


LOCAL_SPEAKER_CONTINUITY_MAX_SEGMENT_GAP = 12
LOCAL_CHILD_LABEL_PREFIXES = (
    "cậu bé",
    "cô bé",
    "đứa bé",
    "đứa trẻ",
    "trẻ em",
    "trẻ nhỏ",
)
LOCAL_LABEL_STOPWORDS = {"mac", "nguoi"}
CROWD_DIALOGUE_BLOCK_MAX_SEGMENTS = 8
CROWD_ATTRIBUTION_PATTERN = re.compile(
    r"(?:người dân|dân nghèo|dân chúng|đám đông|mọi người).{0,180}"
    r"(?:gào|hét|hô|la|thét|kêu)",
    flags=re.IGNORECASE,
)
LEGACY_PERSONALITY_PREFIX_PATTERN = re.compile(
    r"^personality=([^;=\r\n]{1,160})(?:;|$)"
)


PRONOUNS = {
    "hắn", "nàng", "cô ấy", "anh ấy", "ông ấy", "bà ấy", "người đó", "kẻ đó",
    "ta", "tôi", "mình", "chúng ta", "bọn họ",
}
RESERVED_SPEAKERS = {"narrator": "NARRATOR", "unknown": "UNKNOWN"}
HONORIFIC_PREFIX_PATTERN = re.compile(
    r"^(?:anh|chị|cô|dì|chú|bác|ông|bà|ngài|quý cô|quý ông|bá tước|công tước|đức ngài)\s+(.+)$",
    flags=re.IGNORECASE,
)
ASCII_PROPER_NAME_PATTERN = re.compile(
    r"[A-Z][A-Za-z]*(?:[\s'-][A-Z][A-Za-z]*)*"
)

def normalize_name(name: str) -> str:
    return " ".join(name.strip().casefold().split())


def canonical_key(name: str) -> str:
    return normalize_name(name).upper()


def _looks_like_proper_name(value: str) -> bool:
    return ASCII_PROPER_NAME_PATTERN.fullmatch(value.strip()) is not None


def _honorific_target(value: str) -> str | None:
    match = HONORIFIC_PREFIX_PATTERN.fullmatch(" ".join(value.split()))
    if match is None:
        return None
    candidate = match.group(1).strip()
    return candidate if _looks_like_proper_name(candidate) else None


def _canonicalize_named_speakers(
    db: ProjectDB,
    log: Callable[[str], None],
) -> dict[str, set[str]]:
    counts = Counter(str(row["speaker"]) for row in db.list_segments())
    cleaned_counts: Counter[str] = Counter()
    cleaned_by_original: dict[str, str] = {}
    for original, count in counts.items():
        cleaned = _canonical_speaker(original)
        cleaned_by_original[original] = cleaned
        normalized = normalize_name(cleaned)
        if (
            is_local_speaker(cleaned)
            or cleaned.casefold() in RESERVED_SPEAKERS
            or normalized in PRONOUNS
        ):
            continue
        cleaned_counts[cleaned] += count

    representatives: dict[str, str] = {}
    variants_by_key: dict[str, Counter[str]] = defaultdict(Counter)
    for cleaned, count in cleaned_counts.items():
        variants_by_key[normalize_name(cleaned)][cleaned] += count
    for key, variants in variants_by_key.items():
        representatives[key] = min(
            variants,
            key=lambda candidate: (-variants[candidate], candidate.casefold(), candidate),
        )

    aliases_by_target: dict[str, set[str]] = defaultdict(set)
    rewritten_segments = 0
    for original, cleaned in cleaned_by_original.items():
        normalized = normalize_name(cleaned)
        if (
            is_local_speaker(cleaned)
            or cleaned.casefold() in RESERVED_SPEAKERS
            or normalized in PRONOUNS
        ):
            continue
        target_key = normalized
        honorific_target = _honorific_target(cleaned)
        if honorific_target is not None:
            honorific_key = normalize_name(honorific_target)
            if honorific_key in representatives:
                target_key = honorific_key
        target = representatives[target_key]
        aliases_by_target[target].update((original, cleaned))
        if original != target:
            rewritten_segments += db.rewrite_speaker(original, target)

    if rewritten_segments:
        alias_count = sum(
            len(aliases - {target})
            for target, aliases in aliases_by_target.items()
        )
        log(
            f"Đã chuẩn hóa {rewritten_segments} segment thuộc {alias_count} alias nhân vật "
            "rõ ràng trước khi khóa voice."
        )
    return aliases_by_target


# Vietnamese marks gender in the words it uses for people far more reliably than an
# English pronoun does, and the narration is full of them. Only unambiguous ones are here:
# "em", "con", "bác" and "người" are used for either, so counting them would add noise
# rather than evidence.
MALE_PERSON_WORDS = frozenset(
    {"cậu", "anh", "ông", "hắn", "gã", "chàng", "thằng", "chú", "lão"}
)
FEMALE_PERSON_WORDS = frozenset(
    {"cô", "chị", "bà", "nàng", "ả", "mụ", "dì", "thím", "nữ"}
)
# A scene puts a character beside people of the other gender, so the words in the segments
# that name them are never pure. The margin has to be wide enough that the character's own
# pronoun dominates: Noah's 36 segments carry 40 male words to 4 female, because "ông" for
# his father and "bà" for his mother are there too and still lose ten to one.
GENDER_EVIDENCE_MINIMUM_HITS = 5
GENDER_EVIDENCE_MINIMUM_RATIO = 3.0
WORD_PATTERN = re.compile(r"[^\W\d_]+", flags=re.UNICODE)


def _gendered_word_evidence(rows: list[Any], names: set[str]) -> Counter[str]:
    """Count male and female person-words in every segment that names this character.

    Read from the text rather than from the model, because the model is what is in doubt
    by the time this is called: for Noah it answered male twice, female twice and unknown
    ten times across fourteen segments, while the narration says "cậu" eighteen times.
    """
    wanted = {name.casefold() for name in names if name}
    counts: Counter[str] = Counter()
    if not wanted:
        return counts
    for row in rows:
        text = str(row["text"] or "")
        lowered = text.casefold()
        if not any(name in lowered for name in wanted):
            continue
        for word in WORD_PATTERN.findall(lowered):
            if word in MALE_PERSON_WORDS:
                counts["male"] += 1
            elif word in FEMALE_PERSON_WORDS:
                counts["female"] += 1
    return counts


def _decisive(counts: Counter[str]) -> str | None:
    """The gender the evidence points at, or None when it does not point hard enough."""
    male, female = counts.get("male", 0), counts.get("female", 0)
    winner, loser = ("male", female) if male >= female else ("female", male)
    top = max(male, female)
    if top < GENDER_EVIDENCE_MINIMUM_HITS:
        return None
    if loser > 0 and top / loser < GENDER_EVIDENCE_MINIMUM_RATIO:
        return None
    return winner


def resolve_gender(
    identity_rows: list[Any],
    all_rows: list[Any],
    locked: dict[str, str] | None = None,
) -> tuple[str, str]:
    """One answer for a character's gender, used by the gate and by the casting alike.

    Two places used to decide this and they disagreed by construction: the gate refused any
    disagreement at all, while _majority() answered "unknown" on a tie. So a character the
    model split 2-2 could only ever fail the run, and passing the gate by loosening it
    would have cast that character with no gender at all. This is the single place now.

    A listener's pinned answer outranks everything: they have read the book and the model
    has not. Otherwise the model's own votes win when they have a majority, and when they
    tie - the case that used to kill a run after ninety minutes of analysis - the text is
    asked instead. It answers far better than the model does, because Vietnamese marks
    gender in nearly every word it uses for a person.
    """
    if locked:
        for row in identity_rows:
            pinned = locked.get(canonical_key(str(row["speaker"])))
            if pinned:
                return pinned, "listener"
    votes = Counter(
        str(row["gender"])
        for row in identity_rows
        if str(row["gender"]) in {"male", "female"}
    )
    ranked = votes.most_common()
    if len(ranked) == 1:
        return ranked[0][0], "model"
    if ranked and (len(ranked) == 1 or ranked[0][1] > ranked[1][1]):
        return ranked[0][0], "model_majority"
    names = {str(row["speaker"]) for row in identity_rows}
    evidence = _gendered_word_evidence(all_rows, names)
    decided = _decisive(evidence)
    if decided is not None:
        return decided, f"text:{evidence.get('male', 0)}nam/{evidence.get('female', 0)}nữ"
    return "unknown", "unresolved"


def _validate_casting_inputs(
    rows: list[Any],
    minimum_named_mentions: int,
    log: Callable[[str], None] = lambda _message: None,
    locked: dict[str, str] | None = None,
) -> None:
    rows_by_identity: dict[str, list[Any]] = defaultdict(list)
    for row in rows:
        speaker = str(row["speaker"])
        normalized = normalize_name(speaker)
        if speaker.casefold() in RESERVED_SPEAKERS or normalized in PRONOUNS:
            continue
        rows_by_identity[canonical_key(speaker)].append(row)

    gender_conflicts: dict[str, dict[str, Any]] = {}
    resolved_conflicts: dict[str, tuple[str, str, dict[str, int]]] = {}
    missing_named_genders: dict[str, int] = {}
    identity_instability: dict[str, dict[str, list[Any]]] = {}
    for identity, identity_rows in rows_by_identity.items():
        gender_counts = Counter(
            str(row["gender"])
            for row in identity_rows
            if str(row["gender"]) in {"male", "female"}
        )
        if len(gender_counts) > 1:
            # A disagreement is only fatal when nothing settles it. It used to be fatal
            # always: alpha.30 died here after ninety minutes of analysis because the model
            # called Noah male twice and female twice, while the narration says "cậu"
            # eighteen times. The resolver is the same one the casting uses, so passing
            # here means the character is cast as what passed rather than as "unknown".
            resolved, reason = resolve_gender(identity_rows, rows, locked)
            if resolved == "unknown":
                gender_conflicts[identity] = {
                    **dict(sorted(gender_counts.items())),
                    "text_evidence": dict(
                        _gendered_word_evidence(
                            rows, {str(row["speaker"]) for row in identity_rows}
                        )
                    ),
                }
            else:
                resolved_conflicts[identity] = (resolved, reason, dict(gender_counts))
        if (
            len(identity_rows) >= minimum_named_mentions
            and not gender_counts
            and not is_local_speaker(str(identity_rows[0]["speaker"]))
        ):
            missing_named_genders[identity] = len(identity_rows)

        surfaces = sorted({str(row["speaker"]) for row in identity_rows}, key=str.casefold)
        character_ids = sorted(
            {int(row["canonical_character_id"]) for row in identity_rows if row["canonical_character_id"] is not None}
        )
        profile_ids = sorted(
            {int(row["voice_profile_id"]) for row in identity_rows if row["voice_profile_id"] is not None}
        )
        if len(surfaces) > 1 or len(character_ids) > 1 or len(profile_ids) > 1:
            identity_instability[identity] = {
                "speakers": surfaces,
                "character_ids": character_ids,
                "voice_profile_ids": profile_ids,
            }

    for identity, (resolved, reason, votes) in sorted(resolved_conflicts.items()):
        log(
            f"Giới tính của {identity} bị model trả lời mâu thuẫn ({dict(votes)}); "
            f"đã xác định là {resolved} theo {reason}."
        )

    issues: list[str] = []
    if gender_conflicts:
        issues.append(f"gender conflicts={gender_conflicts}")
    if missing_named_genders:
        issues.append(f"named speakers missing gender={missing_named_genders}")
    if identity_instability:
        issues.append(f"voice identity instability={identity_instability}")
    if issues:
        raise RuntimeError("Casting input quality gate failed: " + "; ".join(issues))


def _majority(rows: list[Any], column: str, default: str = "unknown") -> str:
    counts = Counter(
        str(row[column])
        for row in rows
        if str(row[column]) not in {"", "unknown"}
    )
    if not counts:
        return default
    ranked = counts.most_common()
    if len(ranked) > 1 and ranked[0][1] == ranked[1][1]:
        return default
    return ranked[0][0]


def _preset_by_name(name: str) -> dict[str, str]:
    try:
        return preset_by_name(name)
    except ValueError as exc:
        raise ValueError(f"VieNeu narrator preset is not in the locked catalog: {name!r}") from exc


class PresetAllocator:
    def __init__(self, narrator_voice: str, max_pitch_shift: int) -> None:
        self.narrator_voice = narrator_voice
        self.max_pitch_shift = max(0, int(max_pitch_shift))
        self.pool_usage: dict[str, Counter[str]] = {
            "named": Counter(),
            "npc": Counter(),
        }
        self.variant_usage: Counter[str] = Counter()

    def choose(
        self,
        gender: str,
        *,
        npc: bool,
        age: str = "unknown",
        prominent: bool = False,
    ) -> tuple[dict[str, str], float, int]:
        """Pick a preset, the formant warp it needs, and the F0 offset its age implies.

        `age` used to be analysed, stored and then ignored here, so a child was read by
        whichever adult voice came next in the rotation and a listener described the boy
        as sounding like an old uncle. Age enters twice, because it is two different
        acoustic facts: a shorter vocal tract, which the formant warp reaches, and a
        higher or lower F0, which the register does.
        """
        # A character never shares the narrator's preset. Excluding it by name excludes
        # every variant of it too, which is the point: a pitch-shifted or formant-warped
        # narrator is still the narrator's voice to a listener, not a second character.
        candidates = [
            preset
            for preset in casting_presets(gender)
            if preset["name"] != self.narrator_voice
        ]
        # A preset whose pitch cannot reach the age is not a candidate for it. Warping the
        # tract to a child's size while the pitch stays adult makes a combination no throat
        # can produce, and a listener hears it as a defect rather than as a child.
        reachable = [
            preset
            for preset in candidates
            if preset_reaches_age_pitch(str(preset["name"]), age, gender)
        ]
        if reachable:
            candidates = reachable
        if str(age) == "child":
            # Before puberty the sexes barely differ: an eight-year-old boy and girl are
            # about 13.0 and 12.7 cm of vocal tract. Restricting a boy to the male presets
            # therefore restricts him to the *longest* tracts in the catalog, which cannot
            # reach a child even warped to their limit - they stop 0.8 cm short and sound
            # strained getting there. The short presets land on the target exactly, so the
            # pool widens across gender here and only here.
            candidates = [
                preset
                for preset in VIENEU_PRESETS
                if preset["name"] != self.narrator_voice
                and preset["style"] != STYLE_NEWS
                and preset["region"] in CASTING_REGIONS
                and preset["name"] not in EXCLUDED_PRESETS
                and preset_reaches_age_pitch(str(preset["name"]), age, gender)
            ]
        if not candidates:
            # Nothing of this gender is left, so widen across gender - but never across
            # the region allowlist. A fallback that reached the whole catalog would put
            # the excluded Central presets straight back into the book.
            candidates = [
                preset
                for preset in VIENEU_PRESETS
                if preset["name"] != self.narrator_voice
                and preset["style"] != STYLE_NEWS
                and preset["region"] in CASTING_REGIONS
                and preset["name"] not in EXCLUDED_PRESETS
            ]
        pool = "npc" if npc else "named"
        usage = self.pool_usage[pool]

        def rank(preset: dict[str, Any]) -> tuple[Any, ...]:
            name = str(preset["name"])
            return (
                # Demoted voices sort below every clean one, ahead of usage count rather
                # than blended into it: a gentler weighting would let them win as soon as
                # each clean preset had been used once, which is the second character in
                # the chapter.
                name in LAST_RESORT_PRESETS,
                usage[name],
                # A preset that cannot reach this age is a worse fit however available it
                # is: an adult male tract stops 0.8 cm short of an eight-year-old even
                # warped to its limit, while the shortest presets land exactly on it.
                # Bucketed to half a centimetre: two presets that both land near the
                # target are the same fit to a listener, and a 0.1 cm edge must not
                # outrank a voice being hard to follow.
                # A listener's own ranking of the voices they have heard as children
                # comes before either computed proxy. Reach and shift only estimate how
                # good the result will sound; this is a verdict on the result, and the
                # estimates have already been caught disagreeing with it.
                child_voice_preference(name, age, gender),
                round(preset_age_reach(name, age, gender) * 2.0) / 2.0,
                # Then the dearer of the two warps. Measured on four presets reading the
                # same line, the age pitch shift costs about 0.85 MOS against the formant
                # shift's 0.50, and the damage tracks the size of the shift: +2 semitones
                # lost 0.69 MOS, +11 lost 1.24. Ranking on tract reach alone was
                # optimising the cheaper axis and ignoring the dearer one.
                #
                # It still sorts below reach. Reach decides whether the result is a child
                # at all - a listener rejected an otherwise clean take with "giọng của
                # cậu bé nghe vẫn ra giọng của một ông chú" - and a clean voice that
                # sounds like the wrong person is not the cheaper option.
                #
                # Bucketed at four semitones so a one-semitone edge cannot outweigh
                # anything ranked above it.
                abs(age_pitch_semitones(age, gender, name)) // AGE_PITCH_RANK_BUCKET,
                *casting_preset_priority(preset),
            )

        selected = min(candidates, key=rank)
        name = str(selected["name"])
        usage[name] += 1
        # Formant, not pitch, is what makes a reused preset sound like a different
        # person. The ladder starts at 1.00 so a preset's first casting is the untouched
        # voice and pays no vocoder cost at all - but an age target overrides the ladder,
        # because reading a child at an adult tract length is not a variation, it is wrong.
        age_ratio = formant_ratio_for_age(name, age, gender)
        if abs(age_ratio - 1.0) > 1e-6:
            formant_ratio = age_ratio
        else:
            variants = formant_variants_for_preset(name)
            formant_ratio = variants[self.variant_usage[name] % len(variants)]
        self.variant_usage[name] += 1
        return selected, formant_ratio, age_pitch_semitones(age, gender, name)

    def reserve(self, preset_name: str, *, npc: bool) -> None:
        """Record that a preset is taken, for a character this allocator never chose.

        A pinned voice is invisible to the ranking unless it is counted here, and an unused
        preset always sorts first - so the very next character would be handed the voice
        somebody had just pinned to someone else. Two people, one voice, and nothing catches
        it: the invariant in `verify_casting` checks that one speaker resolves to one
        profile, which is the opposite direction.
        """
        self.pool_usage["npc" if npc else "named"][str(preset_name)] += 1
        self.variant_usage[str(preset_name)] += 1


def _pinned_profile_id(
    db: ProjectDB,
    locked_voices: dict[str, str],
    canonical: str,
    allocator: Any,
    local: bool,
    log: Any,
) -> int | None:
    """The voice a previous run gave this character, if somebody carried it over.

    Returns None when nothing is pinned, which is every character until `port_casting.py`
    runs - so a project that never used it casts exactly as it did before.

    A pinned key that names no profile in this project is reported and ignored rather than
    raising: the run should not die because a carried decision has gone stale, and casting
    afresh is a defensible answer. It is logged because silently re-casting a voice somebody
    chose is not.
    """
    # `canonical` has already been through canonical_key at the call site, and
    # locked_character_voices keys the same way; applying it again is idempotent and says so.
    voice_key = locked_voices.get(canonical_key(canonical), "")
    if not voice_key:
        return None
    try:
        row = db.voice_profile_by_key(voice_key)
    except KeyError:
        log(f"Giọng đã ghim {voice_key!r} cho {canonical!r} không có trong project; cấp phát lại.")
        return None
    allocator.reserve(str(row["preset_name"]), npc=local)
    return int(row["id"])


def _profile_for_preset(
    db: ProjectDB,
    preset: dict[str, str],
    formant_ratio: float,
    cache: dict[str, int],
    *,
    age_pitch: int = 0,
) -> int:
    name = preset["name"]
    # The preset's calibrated reading register, plus whatever the character's age asks
    # for: children speak about three semitones above an adult, and ageing moves men up
    # while it moves women down.
    base_pitch = base_pitch_for_preset(name) + int(age_pitch)
    formant_key = f"f{int(round(float(formant_ratio) * 100)):03d}"
    pitch_key = f"p{int(base_pitch):+03d}"
    profile_key = f"{name}::{formant_key}::{pitch_key}"
    if profile_key not in cache:
        if abs(float(formant_ratio) - 1.0) <= 1e-6:
            description = "âm sắc gốc"
        elif float(formant_ratio) < 1.0:
            description = f"âm sắc trầm hơn ({formant_ratio:.2f})"
        else:
            description = f"âm sắc sáng hơn ({formant_ratio:.2f})"
        cache[profile_key] = db.upsert_voice_profile(
            {
                "voice_key": f"preset_{slugify(name)}_{formant_key}_{pitch_key}",
                "engine": "vieneu",
                "preset_name": name,
                "description": f"{preset['description']} · {description}",
                "seed": stable_int(f"voice::vieneu::{name}::{formant_key}::{pitch_key}"),
                "pitch_semitones": base_pitch,
                "formant_ratio": float(formant_ratio),
                "status": "ready",
            }
        )
    return cache[profile_key]


def _legacy_personality_hint(note: Any) -> str | None:
    match = LEGACY_PERSONALITY_PREFIX_PATTERN.match(str(note or ""))
    if match is None:
        return None
    value = " ".join(match.group(1).split())
    if (
        not value
        or not any(character.isalpha() for character in value)
        or any(
            not (
                character.isalnum()
                or character.isspace()
                or character in {"_", "-", "'", "’"}
            )
            for character in value
        )
    ):
        return None
    return value


def _personality(rows: list[Any]) -> str:
    return next(
        (
            personality
            for row in rows
            if (personality := _legacy_personality_hint(row["analysis_notes"]))
            is not None
        ),
        "",
    )


def _merge_local_speakers_with_named_identity(
    db: ProjectDB,
    log: Callable[[str], None],
) -> None:
    rows = list(db.list_segments())
    named_by_chapter_and_label: dict[tuple[int, str], Counter[str]] = defaultdict(Counter)
    for row in rows:
        speaker = str(row["speaker"])
        normalized = normalize_name(speaker)
        if (
            is_local_speaker(speaker)
            or speaker.casefold() in RESERVED_SPEAKERS
            or normalized in PRONOUNS
        ):
            continue
        named_by_chapter_and_label[(int(row["chapter_id"]), normalized)][speaker] += 1

    local_speakers = {
        str(row["speaker"])
        for row in rows
        if is_local_speaker(row["speaker"])
    }
    for local_speaker in sorted(local_speakers, key=str.casefold):
        matching_rows = [row for row in rows if str(row["speaker"]) == local_speaker]
        if not matching_rows:
            continue
        chapter_id = int(matching_rows[0]["chapter_id"])
        label = normalize_name(local_speaker_label(local_speaker))
        candidates = named_by_chapter_and_label.get((chapter_id, label))
        if not candidates:
            continue
        named_speaker = sorted(
            candidates,
            key=lambda candidate: (-candidates[candidate], candidate.casefold()),
        )[0]
        rewritten = db.rewrite_speaker(local_speaker, named_speaker)
        if rewritten:
            log(
                f"Hợp nhất nhân vật cục bộ cùng chapter: "
                f"{local_speaker_display(local_speaker)} → {named_speaker} "
                f"({rewritten} segment)."
            )


def _compatible_local_traits(left: list[Any], right: list[Any], field: str) -> bool:
    left_values = {str(row[field]) for row in left if str(row[field]) != "unknown"}
    right_values = {str(row[field]) for row in right if str(row[field]) != "unknown"}
    return not left_values or not right_values or bool(left_values & right_values)


def _semantic_local_label(label: str) -> str:
    tokens = [
        token
        for token in slugify(label).split("_")
        if token and token not in LOCAL_LABEL_STOPWORDS
    ]
    return "_".join(tokens)


def _local_continuity_family(speaker: str, rows: list[Any]) -> str:
    label = normalize_name(local_speaker_label(speaker))
    if any(
        label == prefix or label.startswith(f"{prefix} ")
        for prefix in LOCAL_CHILD_LABEL_PREFIXES
    ):
        return f"child::{_majority(rows, 'gender')}"
    return f"label::{_semantic_local_label(label)}"


def _local_speaker_with_label(speaker: str, label: str) -> str | None:
    if not is_local_speaker(speaker):
        return None
    prefix, _separator, _old_label = speaker.rpartition("::")
    return f"{prefix}::{label}" if prefix else None


def _repair_cross_batch_dialogue_continuations(
    db: ProjectDB,
    log: Callable[[str], None],
) -> None:
    rows = sorted(db.list_segments(), key=lambda row: (int(row["chapter_id"]), int(row["seq"])))
    previous: dict[str, Any] | None = None
    repaired = 0
    for row in rows:
        current = {
            "row": row,
            "kind": str(row["kind"]),
            "speaker": str(row["speaker"]),
            "gender": str(row["gender"]),
            "age": str(row["age"]),
        }
        if previous is not None:
            previous_row = previous["row"]
            same_chapter = int(previous_row["chapter_id"]) == int(row["chapter_id"])
            adjacent_seq = int(row["seq"]) == int(previous_row["seq"]) + 1
            adjacent_paragraph = int(row["paragraph_index"]) == int(
                previous_row["paragraph_index"]
            ) + 1
            previous_text = str(previous_row["text"]).rstrip()
            text = str(row["text"]).lstrip()
            continuation = bool(
                same_chapter
                and adjacent_seq
                and adjacent_paragraph
                and previous["kind"] == "dialogue"
                and current["kind"] == "dialogue"
                and previous_text
                and text
                and previous_text[-1] not in DIALOGUE_CLOSERS
                and text[0] not in DIALOGUE_OPENERS
            )
            if continuation and current["speaker"] != previous["speaker"]:
                repaired += db.rewrite_segment_speakers(
                    [int(row["id"])],
                    speaker=str(previous["speaker"]),
                    gender=str(previous["gender"]),
                    age=str(previous["age"]),
                )
                current.update(
                    {
                        "speaker": previous["speaker"],
                        "gender": previous["gender"],
                        "age": previous["age"],
                    }
                )
        previous = current
    if repaired:
        log(f"Đã giữ identity xuyên batch cho {repaired} câu thoại nối tiếp.")


def _repair_crowd_dialogue_blocks(
    db: ProjectDB,
    log: Callable[[str], None],
) -> None:
    rows = sorted(db.list_segments(), key=lambda row: (int(row["chapter_id"]), int(row["seq"])))
    kinds_by_stable_id = {
        str(row["stable_id"]): {"kind": str(row["kind_hint"])}
        for row in rows
    }
    repaired = 0
    for index, row in enumerate(rows):
        if (
            str(row["kind_hint"]) != "narration"
            or str(row["kind"]) == "dialogue"
            or CROWD_ATTRIBUTION_PATTERN.search(str(row["text"])) is None
        ):
            continue
        block: list[Any] = []
        cursor = index - 1
        expected_seq = int(row["seq"]) - 1
        block_speaker: str | None = None
        while cursor >= 0 and len(block) < CROWD_DIALOGUE_BLOCK_MAX_SEGMENTS:
            candidate = rows[cursor]
            if int(candidate["chapter_id"]) != int(row["chapter_id"]):
                break
            if int(candidate["seq"]) != expected_seq:
                break
            if str(candidate["kind"]) != "dialogue":
                break
            candidate_speaker = str(candidate["speaker"])
            if block_speaker is None:
                block_speaker = candidate_speaker
            elif candidate_speaker != block_speaker:
                break
            attributed_speaker = _explicit_speaker_attribution(
                rows,
                cursor,
                kinds_by_stable_id,
            )
            if (
                attributed_speaker is not None
                and attributed_speaker.casefold()
                != f"{LOCAL_SPEAKER_REQUEST_PREFIX}người dân".casefold()
            ):
                break
            block.append(candidate)
            expected_seq -= 1
            cursor -= 1
        if not block:
            continue
        by_target: dict[str, list[int]] = defaultdict(list)
        for candidate in block:
            target = _local_speaker_with_label(str(candidate["speaker"]), "người dân")
            if target is not None:
                by_target[target].append(int(candidate["id"]))
        for target, segment_ids in by_target.items():
            candidates_by_id = {int(candidate["id"]): candidate for candidate in block}
            for segment_id in segment_ids:
                candidate = candidates_by_id[segment_id]
                repaired += db.rewrite_segment_speakers(
                    [segment_id],
                    speaker=target,
                    gender="unknown",
                    age="unknown",
                )
    if repaired:
        log(f"Đã sửa {repaired} câu hô của đám đông từ lời dẫn tập thể kế tiếp.")


def _merge_adjacent_local_speakers(
    db: ProjectDB,
    log: Callable[[str], None],
) -> None:
    rows = list(db.list_segments())
    identities: dict[tuple[int, str], list[Any]] = defaultdict(list)
    for row in rows:
        speaker = str(row["speaker"])
        if not is_local_speaker(speaker):
            continue
        identities[(int(row["chapter_id"]), speaker)].append(row)

    grouped: dict[tuple[int, str], dict[str, list[Any]]] = defaultdict(dict)
    for (chapter_id, speaker), speaker_rows in identities.items():
        family = _local_continuity_family(speaker, speaker_rows)
        grouped[(chapter_id, family)][speaker] = speaker_rows

    for (_chapter_id, family), identities in grouped.items():
        ordered = sorted(
            identities.items(),
            key=lambda item: min(int(row["seq"]) for row in item[1]),
        )
        if len(ordered) < 2:
            continue
        canonical_speaker, canonical_rows = ordered[0]
        canonical_last_seq = max(int(row["seq"]) for row in canonical_rows)
        for speaker, speaker_rows in ordered[1:]:
            first_seq = min(int(row["seq"]) for row in speaker_rows)
            compatible = _compatible_local_traits(
                canonical_rows,
                speaker_rows,
                "gender",
            ) and _compatible_local_traits(canonical_rows, speaker_rows, "age")
            gap = first_seq - canonical_last_seq
            if (
                gap <= 0
                or gap > LOCAL_SPEAKER_CONTINUITY_MAX_SEGMENT_GAP
                or not compatible
            ):
                canonical_speaker = speaker
                canonical_rows = speaker_rows
                canonical_last_seq = max(int(row["seq"]) for row in speaker_rows)
                continue
            rewritten = db.rewrite_speaker(speaker, canonical_speaker)
            if rewritten:
                log(
                    "Hợp nhất NPC cục bộ liền cảnh: "
                    f"{local_speaker_display(speaker)} → "
                    f"{local_speaker_display(canonical_speaker)} ({rewritten} segment)."
                )
            canonical_rows = [*canonical_rows, *speaker_rows]
            canonical_last_seq = max(
                canonical_last_seq,
                max(int(row["seq"]) for row in speaker_rows),
            )


def assert_voice_stability(db: ProjectDB) -> None:
    """Refuse a casting where one person would be read by two different voices."""
    # One character, one voice - checked on the resolved character rather than on the
    # speaker label. Checking labels was a blind spot with real consequences: a boy who
    # appeared as a named character in one chapter and as a local NPC in another held two
    # voices three semitones apart, and every label individually had exactly one voice, so
    # this reported success. Local labels were skipped outright, which made the gap worse.
    profiles_by_character: dict[int, set[int]] = defaultdict(set)
    profiles_by_speaker: dict[str, set[int]] = defaultdict(set)
    for row in db.list_segments():
        speaker = str(row["speaker"])
        normalized = normalize_name(speaker)
        profile_id = row["voice_profile_id"]
        character_id = row["canonical_character_id"]
        if speaker != "UNKNOWN" and not is_local_speaker(speaker) and normalized not in PRONOUNS:
            if profile_id is None:
                raise RuntimeError(f"Speaker {speaker!r} has no locked voice profile")
            profiles_by_speaker[normalized].add(int(profile_id))
        if character_id is not None and profile_id is not None:
            profiles_by_character[int(character_id)].add(int(profile_id))
    unstable = {
        speaker: sorted(profile_ids)
        for speaker, profile_ids in profiles_by_speaker.items()
        if len(profile_ids) != 1
    }
    if unstable:
        raise RuntimeError(f"A speaker name resolved to multiple voice profiles: {unstable}")
    split_characters = {
        character_id: sorted(profile_ids)
        for character_id, profile_ids in profiles_by_character.items()
        if len(profile_ids) != 1
    }
    if split_characters:
        raise RuntimeError(
            f"A character resolved to multiple voice profiles: {split_characters}"
        )


def build_registry_and_cast(
    db: ProjectDB,
    settings: dict[str, Any],
    log: Callable[[str], None],
) -> None:
    normalized_thoughts = db.normalize_thought_speakers()
    if normalized_thoughts:
        log(
            f"{normalized_thoughts} đoạn nội tâm không xác định được người nghĩ; "
            "giao cho người kể."
        )

    for speaker in {str(row["speaker"]) for row in db.list_segments()}:
        reserved = RESERVED_SPEAKERS.get(speaker.casefold())
        if reserved and speaker != reserved:
            db.rewrite_speaker(speaker, reserved)

    _repair_cross_batch_dialogue_continuations(db, log)
    _repair_crowd_dialogue_blocks(db, log)
    aliases_by_speaker = _canonicalize_named_speakers(db, log)
    _merge_adjacent_local_speakers(db, log)
    _merge_local_speakers_with_named_identity(db, log)

    rows = [row for row in db.list_segments() if str(row["status"]) != "pending"]
    voice_cfg = settings["voices"]
    minimum_main_mentions = int(voice_cfg["minimum_named_character_mentions"])
    locked_genders = db.locked_character_genders()
    locked_voices = db.locked_character_voices()
    _validate_casting_inputs(rows, minimum_main_mentions, log, locked_genders)
    by_speaker: dict[str, list[Any]] = defaultdict(list)
    anonymous_by_gender: dict[str, list[Any]] = defaultdict(list)
    for row in rows:
        speaker = str(row["speaker"])
        normalized = normalize_name(speaker)
        if speaker.casefold() == "unknown" or normalized in PRONOUNS:
            gender = str(row["gender"])
            anonymous_by_gender[gender if gender in {"male", "female"} else "unknown"].append(row)
        else:
            by_speaker[speaker].append(row)

    narrator_voice = str(voice_cfg["narrator_voice"])
    narrator_preset = _preset_by_name(narrator_voice)
    allocator = PresetAllocator(
        narrator_voice,
        int(voice_cfg.get("max_character_pitch_semitones", 2)),
    )
    profile_cache: dict[str, int] = {}

    narrator_rows = by_speaker.pop("NARRATOR", [])
    narrator_character_id = db.upsert_character(
        canonical_name="NARRATOR",
        display_name="Người kể",
        gender=narrator_preset["gender"],
        age="unknown",
        personality="professional audiobook narrator",
        mentions=len(narrator_rows),
        importance="narrator",
        confidence=1.0,
    )
    narrator_profile = db.upsert_voice_profile(
        {
            "voice_key": "narrator",
            "engine": "vieneu",
            "preset_name": narrator_voice,
            "description": str(voice_cfg["narrator_description"]),
            "seed": stable_int("voice::narrator"),
            "pitch_semitones": 0,
            "status": "ready",
        }
    )
    profile_cache[f"{narrator_voice}::p0"] = narrator_profile
    db.set_character_for_speaker("NARRATOR", narrator_character_id)
    db.set_voice_for_character_segments(narrator_character_id, narrator_profile)

    speaker_groups = sorted(
        by_speaker.items(),
        key=lambda item: (-len(item[1]), item[0].casefold()),
    )
    local_count = 0
    for speaker, speaker_rows in speaker_groups:
        # The same resolver the gate used, so a character that passed the gate on text
        # evidence is cast as what passed rather than as "unknown".
        gender, _reason = resolve_gender(speaker_rows, rows, locked_genders)
        age = _majority(speaker_rows, "age")
        local = is_local_speaker(speaker)
        display_name = local_speaker_display(speaker) if local else speaker
        canonical = canonical_key(speaker if local else display_name)
        confidence = sum(float(row["confidence"]) for row in speaker_rows) / max(1, len(speaker_rows))
        importance = "minor" if local or len(speaker_rows) < minimum_main_mentions else "main"
        character_id = db.upsert_character(
            canonical_name=canonical,
            display_name=display_name,
            gender=gender,
            age=age,
            personality=_personality(speaker_rows),
            mentions=len(speaker_rows),
            importance=importance,
            confidence=confidence,
        )
        for alias in sorted(aliases_by_speaker.get(speaker, {speaker}), key=str.casefold):
            db.add_alias(character_id, alias, normalize_name(alias), confidence, "analysis")
        db.set_character_for_speaker(speaker, character_id)
        profile_id = _pinned_profile_id(db, locked_voices, canonical, allocator, local, log)
        if profile_id is None:
            preset, formant_ratio, age_pitch = allocator.choose(
                gender,
                npc=local,
                age=age,
                prominent=importance == "main",
            )
            profile_id = _profile_for_preset(
                db, preset, formant_ratio, profile_cache, age_pitch=age_pitch
            )
        db.set_voice_for_character_segments(character_id, profile_id)
        local_count += int(local)

    anonymous_labels = {
        "male": "NPC vô danh nam",
        "female": "NPC vô danh nữ",
        "unknown": "NPC vô danh chưa rõ giới tính",
    }
    anonymous_count = 0
    for gender in ("male", "female", "unknown"):
        anonymous_rows = anonymous_by_gender.get(gender, [])
        if not anonymous_rows:
            continue
        display_name = anonymous_labels[gender]
        confidence = sum(float(row["confidence"]) for row in anonymous_rows) / len(anonymous_rows)
        character_id = db.upsert_character(
            canonical_name=f"ANONYMOUS_{gender.upper()}",
            display_name=display_name,
            gender=gender,
            age=_majority(anonymous_rows, "age"),
            personality="minor local characters without a stable identity",
            mentions=len(anonymous_rows),
            importance="minor",
            confidence=confidence,
        )
        preset, formant_ratio, age_pitch = allocator.choose(
            gender, npc=True, age=_majority(anonymous_rows, "age")
        )
        profile_id = _profile_for_preset(
            db, preset, formant_ratio, profile_cache, age_pitch=age_pitch
        )
        db.set_character_and_voice_for_segments(
            [int(row["id"]) for row in anonymous_rows],
            character_id,
            profile_id,
        )
        anonymous_count += 1

    used_voices = len({str(profile["preset_name"]) for profile in db.list_voice_profiles()})
    voice_variants = len(profile_cache)
    assert_voice_stability(db)
    log(
        f"Đã khóa voice casting VieNeu: dùng {used_voices}/{len(VIENEU_PRESETS)} preset; "
        f"{voice_variants} biến thể giọng; "
        f"{local_count} NPC có danh tính cục bộ, {anonymous_count} nhóm NPC generic theo giới tính."
    )
