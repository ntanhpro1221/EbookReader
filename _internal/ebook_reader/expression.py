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
        # Reported, not applied. Praat's overlap-add time-stretch is the one step in this
        # chain that is not deterministic - the same input twice differs by up to 0.08 -
        # and reproducible output is worth more than this lever is. A listener compared
        # tempo variants directly and could not tell them apart, it is bounded to 6%
        # anyway, and it is the lever that costs comprehension rather than adding to it.
        # The value is kept so the reason it is unused stays visible.
        "tempo": max(1.0 - tempo_limit, min(1.0 + tempo_limit, 1.0 + rate_percent / 100.0)),
        "tempo_applied": False,
        "gain_db": max(-gain_limit, min(gain_limit, gain_db)),
    }


# A pitch tracker gets some frames wrong, usually by an octave, and on real audio from
# this pipeline that is 7.7% of voiced frames sitting more than 8 semitones from the
# median - one measured at -27. Scaling the contour multiplies those errors along with the
# real excursions, and a frame at -43 semitones resynthesises as a word at an absurd
# pitch. The contour is therefore cleaned before it is shaped, and the shaping is measured
# from the median rather than the mean so a handful of bad frames cannot drag the centre.
OCTAVE_ERROR_SEMITONES = 8.0
MAX_DEVIATION_SEMITONES = 12.0
# The range a human voice can occupy, and the only thing a shifted pitch may be clamped
# to. Imported rather than restated: tts.py clamps the formant warp against the same
# fact, and the one time these two disagreed a word stopped being a word. A second copy
# is not a second opinion, it is a chance to drift.
from .tts import (  # noqa: E402 - deferred to the bottom of the import graph
    VOICE_VARIANT_PITCH_CEILING_HZ as PITCH_CEILING_HZ,
    VOICE_VARIANT_PITCH_FLOOR_HZ as PITCH_FLOOR_HZ,
)
MANIPULATION_TIME_STEP = 0.01


def shape_f0(
    audio: np.ndarray,
    rate: int,
    semitones: float,
    range_ratio: float,
) -> np.ndarray:
    """Move and widen the pitch contour with PSOLA, keeping the original waveform.

    This was a WORLD round trip first, and WORLD rebuilds the signal: it estimates a
    spectral envelope and resynthesises phase from scratch, which costs about 0.27 MOS
    before any modification and pushed one measured peak from 0.395 to 0.753. A listener
    heard it as words arriving with a crackle and the whole reading carrying a faint
    noise. PSOLA overlaps and adds pieces of the original waveform instead, so the timbre
    that survives is the one VieNeu produced rather than a reconstruction of it - on the
    same line and the same parameters, the peak moved 0.440 to 0.478 instead of to 0.601,
    and the listener called the difference plain.

    The scaling happens in log-F0 around the contour's own median, so widening by 1.4 adds
    the same proportion of semitones wherever in the range it sits. Doing it linearly in
    Hz would stretch the top of the contour far more than the bottom and sound like a
    fault.
    """
    import parselmouth
    from parselmouth.praat import call

    waveform = np.asarray(audio, dtype=np.float64).reshape(-1)
    if waveform.size < int(rate * 0.05):
        return np.asarray(audio, dtype=np.float32).reshape(-1)
    from .tts import praat_pitch_window

    sound = parselmouth.Sound(waveform, sampling_frequency=float(rate))
    # Same reason as the formant warp: a search window far wider than the voice invites an
    # octave error, and every pulse placed from that error is audible on the low words.
    floor_hz, ceiling_hz = praat_pitch_window(
        waveform, int(rate), PITCH_FLOOR_HZ, PITCH_CEILING_HZ
    )
    manipulation = call(
        sound, "To Manipulation", MANIPULATION_TIME_STEP, floor_hz, ceiling_hz
    )
    tier = call(manipulation, "Extract pitch tier")
    count = int(call(tier, "Get number of points"))
    if count >= 3:
        points = [
            (
                float(call(tier, "Get time from index", index)),
                float(call(tier, "Get value at index", index)),
            )
            for index in range(1, count + 1)
        ]
        voiced = np.array([value for _time, value in points if value > 0.0])
        if voiced.size >= 3:
            centre = float(np.median(np.log2(voiced)))
            call(tier, "Remove points between", 0.0, sound.get_total_duration() + 1.0)
            for time, value in points:
                if value <= 0.0:
                    continue
                deviation = (np.log2(value) - centre) * 12.0
                # Anything this far from the centre is a tracker error, not an
                # excursion, and widening it would only make the error louder.
                deviation = float(
                    np.clip(deviation, -MAX_DEVIATION_SEMITONES, MAX_DEVIATION_SEMITONES)
                )
                shaped = centre + (deviation * float(range_ratio) + float(semitones)) / 12.0
                call(
                    tier,
                    "Add point",
                    time,
                            # Clamped to what a voice can be, never to the analysis window: that
                    # window describes the pitch going *in*, and a shift of fifteen
                    # semitones deliberately lands far above it. Clamping the result to it
                    # flattened the contour and a word stopped being a word.
                    float(np.clip(2.0**shaped, PITCH_FLOOR_HZ, PITCH_CEILING_HZ)),
                )
            call([tier, manipulation], "Replace pitch tier")
    result = call(manipulation, "Get resynthesis (overlap-add)")
    out = np.asarray(result.values, dtype=np.float32).reshape(-1)
    # Chapters are assembled from these end to end, so a segment comes back at exactly
    # the length it went in.
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
    register_semitones: int = 0,
) -> tuple[np.ndarray, dict[str, float] | None]:
    """Shape a line, at full weight for a speaker and reduced weight for the narrator.

    `register_semitones` is the voice's own calibrated offset, folded into the same pass.
    Doing it separately meant a line with both a register and an affect went through two
    resyntheses on top of the formant warp, and every pass costs something; one pass
    applies both because they are the same operation on the same contour.
    """
    register = int(register_semitones)
    if emotion == "neutral" or int(intensity) == 0:
        if register == 0:
            return np.asarray(audio, dtype=np.float32).reshape(-1), None
        return shape_f0(audio, rate, float(register), 1.0), None
    weight = NARRATION_AFFECT_WEIGHT if kind == "narration" else 1.0
    seconds = len(np.asarray(audio).reshape(-1)) / float(rate) if rate else 10.0
    target = prosody_targets(emotion, intensity, weight=weight, seconds=seconds)
    shaped = shape_f0(
        audio,
        rate,
        target["pitch_semitones"] + register,
        target["range_ratio"],
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
