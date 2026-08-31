"""Emotion shaping from published parameters rather than invented ones.

The first attempt used numbers I made up from vague recollection, and it sounded like
what it was. This one derives every value from two citable sources and does the
arithmetic in the open.

  1. Emotion category -> three dimensions
     Russell, J. A. and Mehrabian, A. (1977), "Evidence for a three-factor theory of
     emotions", Journal of Research in Personality 11(3). Pleasure, Arousal and Dominance
     on a -1..1 scale, for 22 emotion terms.

  2. Dimensions -> prosody
     Schröder's emotion module in MARY TTS, the rule set his dissertation describes:
        pitch  (%)        = 0.3*A + 0.1*V - 0.1*D
        range  (semitones)= 4 + 0.04*A          <- an absolute target, not a multiplier
        rate   (%)        = 0.5*A + 0.2*V
        volume            = 50 + 0.33*A         <- 0..100, 50 is neutral
     with the dimensions on -100..100.

The honest caveat, and it is a large one. "Going Retro" (arXiv:2307.02132) evaluated this
family of rules perceptually and found arousal is conveyed well while valence essentially
is not - Fleiss kappa around .46 for arousal against .07-.12 for valence. So this can make
a line sound activated or subdued, and it cannot make it sound pleasant or unpleasant.
Anger and joy sit at nearly the same arousal and will sound alike. That is a property of
prosody-only manipulation, not a defect in this implementation, and it bounds what any
amount of tuning here could achieve.

Narration is shaped, but at reduced weight, and the distinction matters. Montaño and Alías
(2013) analyse storytelling as discourse modes - narrative, descriptive, dialogue - with
narrative situations inside the narrative mode: neutral, post-character, suspense and
affective. What that framework says, and what a listener said independently, is that a
narrator does carry expression, but it is the *story's* expression rather than a
character's. A narrator describing terror is not terrified; they are conveying terror.

An earlier version shaped narration at full weight and the reading came out hurried and
unsteady. The version before that skipped narration entirely and lost the story's colour.
The weight below is an engineering choice rather than a measured constant, and it is meant
to be tuned by ear - the literature gives the direction and the categories, not a number
that would transfer to this voice and this language.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pyworld

FRAME_PERIOD_MS = 5.0
F0_FLOOR_HZ = 55.0
F0_CEIL_HZ = 600.0

# Russell & Mehrabian (1977), scale -1..1. `tired` has no entry in the 22 terms; the
# nearest published low-arousal negative term is used and flagged rather than invented.
PAD = {
    "neutral": (0.00, 0.00, 0.00),
    "angry": (-0.51, 0.59, 0.25),
    "afraid": (-0.64, 0.60, -0.43),
    "sad": (-0.64, -0.27, -0.33),
    "surprised": (0.40, 0.67, -0.13),
    "happy": (0.76, 0.48, 0.35),      # "joyful"
    "excited": (0.62, 0.75, 0.38),
    "tender": (0.64, 0.35, 0.24),     # "caring"
    "tired": (-0.66, -0.43, -0.32),   # proxy: "lonely", the lowest-arousal term available
    "sarcastic": (-0.28, 0.17, 0.04),  # proxy: "annoyed"
    "whispering": (0.00, -0.40, -0.20),  # not an emotion term; low arousal by definition
}

NEUTRAL_RANGE_SEMITONES = 4.0

# How much of a character's expression a narrator carries when relating the same feeling.
# A narrator conveys the story's affect rather than living it, so full-weight shaping
# reads as the narrator being agitated instead of the scene being agitating.
NARRATION_AFFECT_WEIGHT = 0.5

# Tempo and level are the two levers that cost comprehension, and they are therefore the
# two that get bounded hardest.
#
# This is a book being read aloud for hours. A listener has to take information in
# continuously, and speed and loudness wandering line to line is what makes that tiring -
# far more than a flat reading would. F0 and F0 range carry expression without touching
# intelligibility at all, so expression leans on those and treats the other two as
# seasoning.
#
# The wider bounds are for a short line only: an exclamation or a shout is over before it
# can wear anyone down, and holding it to the same limit as a paragraph would flatten the
# one place the extra range genuinely belongs.
EXPRESSION_TEMPO_LIMIT = 0.06
EXPRESSION_TEMPO_LIMIT_SHORT = 0.15
EXPRESSION_GAIN_LIMIT_DB = 1.0
EXPRESSION_GAIN_LIMIT_DB_SHORT = 2.0
SHORT_UTTERANCE_SECONDS = 2.0


def prosody_targets(
    emotion: str,
    intensity: int,
    *,
    weight: float = 1.0,
    seconds: float = 10.0,
) -> dict[str, float]:
    """Apply the MARY rules to a category, scaled by intensity and by who is speaking."""
    pleasure, arousal, dominance = PAD.get(emotion, PAD["neutral"])
    scale = max(0, min(3, int(intensity))) / 3.0 * float(weight)
    # The dimensions are defined on -100..100; intensity scales how far along we go.
    v, a, d = pleasure * 100.0 * scale, arousal * 100.0 * scale, dominance * 100.0 * scale
    pitch_percent = 0.3 * a + 0.1 * v - 0.1 * d
    range_semitones = NEUTRAL_RANGE_SEMITONES + 0.04 * a
    rate_percent = 0.5 * a + 0.2 * v
    volume = 50.0 + 0.33 * a
    short = float(seconds) <= SHORT_UTTERANCE_SECONDS
    tempo_limit = EXPRESSION_TEMPO_LIMIT_SHORT if short else EXPRESSION_TEMPO_LIMIT
    gain_limit = EXPRESSION_GAIN_LIMIT_DB_SHORT if short else EXPRESSION_GAIN_LIMIT_DB
    # MARY's volume is 0..100 with 50 neutral, which read as a level spans about 12 dB end
    # to end - far more than a book can carry between neighbouring lines.
    gain_db = (volume - 50.0) / 50.0 * 12.0 * 0.25
    return {
        "pitch_semitones": 12.0 * np.log2(1.0 + pitch_percent / 100.0),
        "range_ratio": range_semitones / NEUTRAL_RANGE_SEMITONES,
        "tempo": max(1.0 - tempo_limit, min(1.0 + tempo_limit, 1.0 + rate_percent / 100.0)),
        "gain_db": max(-gain_limit, min(gain_limit, gain_db)),
    }


# A pitch tracker gets some frames wrong, usually by an octave, and on real audio from
# this pipeline that is 7.7% of voiced frames sitting more than 8 semitones from the
# median - one measured at -27. Scaling the contour multiplies those errors along with
# the real excursions: at a range ratio of 1.59 that -27 becomes -43 semitones, which
# resynthesises as a word at an absurd pitch. That is what a listener heard as words
# arriving with the wrong timbre or breaking off. The contour is therefore cleaned before
# it is shaped, and the shaping is measured from the median rather than the mean so a
# handful of bad frames cannot drag the centre.
OCTAVE_ERROR_SEMITONES = 8.0
MAX_DEVIATION_SEMITONES = 12.0


def _clean_f0(f0: np.ndarray) -> np.ndarray:
    """Replace isolated octave errors with the local median of their neighbours."""
    voiced = f0 > 0.0
    if voiced.sum() < 5:
        return f0
    cleaned = f0.copy()
    values = np.log2(f0[voiced])
    centre = float(np.median(values))
    wrong = np.abs(values - centre) * 12.0 > OCTAVE_ERROR_SEMITONES
    if not wrong.any():
        return cleaned
    indices = np.flatnonzero(voiced)
    good = values[~wrong]
    fallback = float(np.median(good)) if good.size else centre
    repaired = values.copy()
    for position in np.flatnonzero(wrong):
        window = values[max(0, position - 4): position + 5]
        window = window[np.abs(window - centre) * 12.0 <= OCTAVE_ERROR_SEMITONES]
        repaired[position] = float(np.median(window)) if window.size else fallback
    cleaned[indices] = np.exp2(repaired)
    return cleaned


def shape_f0(
    audio: np.ndarray,
    rate: int,
    semitones: float,
    range_ratio: float,
    tempo: float = 1.0,
) -> np.ndarray:
    waveform = np.asarray(audio, dtype=np.float64).reshape(-1)
    f0, t = pyworld.harvest(
        waveform, rate, f0_floor=F0_FLOOR_HZ, f0_ceil=F0_CEIL_HZ,
        frame_period=FRAME_PERIOD_MS,
    )
    f0 = pyworld.stonemask(waveform, f0, t, rate)
    spectrum = pyworld.cheaptrick(waveform, f0, t, rate)
    aperiodicity = pyworld.d4c(waveform, f0, t, rate)
    f0 = _clean_f0(f0)
    voiced = f0 > 0.0
    if voiced.sum() >= 3:
        log_f0 = np.log2(f0[voiced])
        centre = float(np.median(log_f0))
        deviation = (log_f0 - centre) * 12.0
        # Anything still this far out after cleaning is not an excursion worth amplifying.
        deviation = np.clip(deviation, -MAX_DEVIATION_SEMITONES, MAX_DEVIATION_SEMITONES)
        shaped = centre + (deviation * float(range_ratio) + float(semitones)) / 12.0
        f0[voiced] = np.clip(np.exp2(shaped), F0_FLOOR_HZ, F0_CEIL_HZ)
    # Time-scaling happens here, by resampling the frame sequence, rather than through
    # ffmpeg's atempo afterwards. atempo is a phase-vocoder stretch: at the 1.19 an angry
    # line asks for it gave speech a mechanical edge a listener picked out on a single
    # final particle. Resampling WORLD's own frames stretches the articulation while every
    # frame keeps its exact spectral envelope, so nothing is re-estimated and there is no
    # phase to smear.
    if abs(float(tempo) - 1.0) > 1e-3:
        frames = f0.shape[0]
        stretched = max(1, int(round(frames / float(tempo))))
        source = np.linspace(0.0, frames - 1.0, stretched)
        base = np.arange(frames, dtype=np.float64)
        voiced_f0 = f0 > 0.0
        f0_out = np.interp(source, base, f0)
        # Interpolating across a voiced/unvoiced edge would invent pitch inside silence.
        f0_out[np.interp(source, base, voiced_f0.astype(np.float64)) < 0.5] = 0.0
        index = np.clip(np.rint(source).astype(int), 0, frames - 1)
        f0, spectrum, aperiodicity = f0_out, spectrum[index], aperiodicity[index]

    out = pyworld.synthesize(f0, spectrum, aperiodicity, rate, FRAME_PERIOD_MS)
    out = np.asarray(out, dtype=np.float32).reshape(-1)
    # WORLD returns one frame more than it was given; a book is assembled from these end
    # to end, so a segment that was not time-scaled must come back at exactly its length.
    if abs(float(tempo) - 1.0) <= 1e-3:
        if out.size > waveform.size:
            out = out[: waveform.size]
        elif out.size < waveform.size:
            out = np.pad(out, (0, waveform.size - out.size))
    return out


def apply_gain(audio: np.ndarray, gain_db: float) -> np.ndarray:
    scaled = np.asarray(audio, dtype=np.float32) * float(10.0 ** (gain_db / 20.0))
    peak = float(np.max(np.abs(scaled))) if scaled.size else 0.0
    if peak > 0.98:
        scaled *= 0.98 / peak
    return scaled.astype(np.float32)


def shape_segment(
    audio: np.ndarray,
    rate: int,
    emotion: str,
    intensity: int,
    kind: str,
) -> tuple[np.ndarray, dict[str, float] | None]:
    """Shape a line, at full weight for a speaker and reduced weight for the narrator."""
    if emotion == "neutral" or int(intensity) == 0:
        return np.asarray(audio, dtype=np.float32).reshape(-1), None
    weight = NARRATION_AFFECT_WEIGHT if kind == "narration" else 1.0
    seconds = len(np.asarray(audio).reshape(-1)) / float(rate) if rate else 10.0
    target = prosody_targets(emotion, intensity, weight=weight, seconds=seconds)
    shaped = shape_f0(
        audio,
        rate,
        target["pitch_semitones"],
        target["range_ratio"],
        target["tempo"],
    )
    return apply_gain(shaped, target["gain_db"]), target


# --- pauses -------------------------------------------------------------------------
#
# The structural pause is already decided from punctuation and paragraph shape: roughly
# 170-230 ms inside a paragraph, 380 at its end, 600 after strong punctuation. That is the
# grammar of the text and it is not touched here.
#
# What it cannot see is the shape of the story. Work on storytelling pause modelling
# (Sharma et al., "Analysis and modeling pauses for synthesis of storytelling speech based
# on discourse modes") classifies a storyteller's pauses into short, medium and long, and
# finds they are placed to emphasise emotion-salient material and to build suspense and
# climax. So a line that carries feeling earns a moment after it to land, and a moment
# before it to be arrived at.
#
# The adjustments are deliberately small. A book is listened to for hours and silence that
# keeps stretching and shrinking is its own kind of fatigue, so this nudges a pause into
# the next tier rather than inventing a new one.
NARRATIVE_PAUSE_AFTER_MS = 120
NARRATIVE_PAUSE_BEFORE_MS = 80
SPEECH_TAG_PAUSE_MS = -60
NARRATIVE_PAUSE_MIN_INTENSITY = 2
PAUSE_CEILING_MS = 900
SPEECH_TAG_MAX_CHARS = 48


def _carries_feeling(segment: dict[str, Any] | None) -> bool:
    if segment is None:
        return False
    return (
        str(segment.get("emotion") or "neutral") != "neutral"
        and int(segment.get("intensity") or 0) >= NARRATIVE_PAUSE_MIN_INTENSITY
    )


def _is_speech_tag(segment: dict[str, Any] | None, previous: dict[str, Any] | None) -> bool:
    """A short narration line right after dialogue - "Joel cười trừ:" and its kin.

    The literature calls this the post-character situation and finds it reduced rather than
    expanded: it is bookkeeping attached to the line it reports, and letting it sit behind
    a full pause detaches it from the speech it belongs to.
    """
    if segment is None or previous is None:
        return False
    if str(segment.get("kind") or "") != "narration":
        return False
    if str(previous.get("kind") or "") != "dialogue":
        return False
    text = str(segment.get("text") or "").strip()
    return 0 < len(text) <= SPEECH_TAG_MAX_CHARS


def narrative_break_ms(
    break_ms: int,
    segment: dict[str, Any],
    previous: dict[str, Any] | None = None,
    following: dict[str, Any] | None = None,
) -> int:
    """Adjust a structural pause for the shape of the story around it."""
    base = max(0, int(break_ms))
    if base == 0:
        # A zero break is a deliberate join - a clause split mid-sentence - and opening a
        # gap there would break the sentence rather than shape it.
        return 0
    adjusted = base
    if _carries_feeling(segment):
        adjusted += NARRATIVE_PAUSE_AFTER_MS
    if _carries_feeling(following):
        adjusted += NARRATIVE_PAUSE_BEFORE_MS
    if _is_speech_tag(segment, previous):
        adjusted += SPEECH_TAG_PAUSE_MS
    return max(0, min(PAUSE_CEILING_MS, adjusted))
