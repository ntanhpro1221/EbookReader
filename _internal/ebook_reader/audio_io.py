from __future__ import annotations

import json
import math
import os
import re
from dataclasses import asdict, dataclass, replace
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pyloudnorm as pyln
import soundfile as sf

from .audio_transform_contract import (
    POSTPROCESS_OUTPUT_CODEC,
    POSTPROCESS_OUTPUT_SAMPLES_FIELD,
    POSTPROCESS_SAMPLE_COUNT_RELATIVE_TOLERANCE,
    POSTPROCESS_SOURCE_SAMPLE_RATE_FIELD,
    POSTPROCESS_SOURCE_SAMPLES_FIELD,
    POSTPROCESS_TEMPO_FACTOR,
)
from .io_utils import atomic_write_text, ffmpeg_executable, run_hidden, sha256_file
from .text_processing import vietnamese_number_words


class AudioQualityError(RuntimeError):
    pass


class ChapterQualityError(AudioQualityError):
    def __init__(
        self,
        message: str,
        *,
        artifact_sha256: str | None = None,
        metrics: dict[str, Any] | None = None,
        failure_codes: Iterable[str] = (),
        review_required: bool = False,
    ) -> None:
        super().__init__(message)
        self.artifact_sha256 = str(artifact_sha256 or "").strip() or None
        self.metrics = dict(metrics or {})
        self.failure_codes = tuple(str(code) for code in failure_codes if str(code))
        self.review_required = bool(review_required)


CHAPTER_DURATION_HARD_TOLERANCE_SECONDS = 0.10
CHAPTER_LOUDNESS_HARD_TOLERANCE_LU = 0.75
CHAPTER_LOUDNESS_REVIEW_TOLERANCE_LU = 0.30
LOUDNESS_REVIEW_FLAG_PREFIX = "loudness delta"


def chapter_review_flags_that_block(review_flags) -> list:
    """Cờ review nào thật sự phải chặn chương, khi không có ai để hỏi.

    Trước 2026-09-09 mọi cờ review đều chặn dưới `high_quality`, và chương đầu tiên của lượt
    sản xuất chết vì `loudness delta 0.62 LU`. Nghĩa đen của một cờ review là *"có thể đáng
    nghe, hỏi một người"* — mà lệnh của chủ sách là **không phải nghe**
    (docs/SHIPPING_WITHOUT_A_LISTENER.md).

    **CHỌN HẸP, và đây là lý do.** Đếm trên mọi project đã lưu, chỉ ba loại cờ review tầng
    chương từng xuất hiện:

        4 lần   unexpected silence   vd 1,02s     <- NGHE THẤY, vẫn chặn
        2 lần   join discontinuity   vd 0,183     <- NGHE THẤY, vẫn chặn
        2 lần   loudness delta       vd 0,62 LU   <- không nghe thấy, cho qua

    Một công tắc gộp sẽ đẩy cả **một giây mất tiếng** vào sách, và sẽ vô hiệu hoá
    `join discontinuity` — phép kiểm mà chính dự án đã đo là hiệu chỉnh đúng (nổ 1/107 lần,
    đúng vào cực đại thật). Chỉ mình độ to là đại lượng có ngưỡng nghe được rõ ràng, và
    `CHAPTER_LOUDNESS_HARD_TOLERANCE_LU = 0.75` đã là vạch mà chính dự án đặt ra cho "quá mức
    này thì chắc chắn có vấn đề". Một cờ độ to nằm dưới vạch ấy là phép kiểm tự nhận nó chưa
    chắc — cùng lý lẽ với *"ASR là nhân chứng duy nhất"*, chỉ khác là nhân chứng thứ hai ở đây
    là ngưỡng cứng của chính nó.

    Chương vẫn đi tiếp **và vẫn kêu**: `pipeline` đã có sẵn sự kiện `CHAPTER_QA_REVIEW_FLAGS`
    ghi mọi cờ, kể cả cờ được cho qua ở đây.
    """
    return [
        flag
        for flag in review_flags
        if not str(flag).startswith(LOUDNESS_REVIEW_FLAG_PREFIX)
    ]
CHAPTER_TRUE_PEAK_HARD_MARGIN_DB = 0.50
CHAPTER_TRUE_PEAK_REVIEW_MARGIN_DB = 0.15
CHAPTER_CLIPPING_HARD_FRACTION = 0.0001
CHAPTER_DC_OFFSET_HARD = 0.05
CHAPTER_DC_OFFSET_REVIEW = 0.01
CHAPTER_MIN_RMS = 0.0001
CHAPTER_FLAT_TOP_DERIVATIVE = 0.0001
CHAPTER_FLAT_TOP_RELATIVE_LEVEL = 0.995
CHAPTER_FLAT_TOP_HARD_SECONDS = 0.010
CHAPTER_FLAT_TOP_REVIEW_SECONDS = 0.002
CHAPTER_SILENCE_FRAME_SECONDS = 0.020
CHAPTER_SILENCE_FLOOR_DBFS = -65.0
CHAPTER_DROPOUT_HARD_SECONDS = 5.0
CHAPTER_DROPOUT_REVIEW_SECONDS = 1.0
CHAPTER_EDGE_SILENCE_REVIEW_SECONDS = 2.0
# A take can open or close with dead air the assembler never asked for. It is rare and it is
# not the take's fault: identical text and identical spoken form, a different generation seed,
# and a leading ellipsis that the engine holds for twice as long. Measured over 841 takes of
# alpha.48 the leading silence is p50 0.11s, p99 0.22s, and exactly two takes exceed 0.5s.
# Those two are what pushed chapter 8 over the one-second chapter limit, on top of the 0.38s
# break and the previous take's tail.
#
# Capped rather than regenerated: alpha.46 drew a different seed for the same sentence and
# still opened with 0.51s, so a retry is not reliably a cure. Capped rather than removed: a
# line that opens on an ellipsis is meant to hesitate, and 0.35s in front of a 0.38s break
# still reads as one.
SEGMENT_EDGE_SILENCE_CAP_SECONDS = 0.35
# A pause *inside* a take, capped by what this book's own reading actually does. Measured
# over all 10,869 silences in alpha.53's 948 takes: median 0.04s, 99th percentile 0.60s,
# 99.5th 0.64s. Ten gaps in the whole book exceed 0.8s and exactly one exceeds 1.0s - the
# 1.20s after "công bằng" in chapter 10, which the owner picked out by ear as a dead spot.
#
# So this threshold is set by the distribution, not by the chapter check it happens to
# satisfy. Setting it just under CHAPTER_DROPOUT_REVIEW_SECONDS would be tuning the audio to
# silence an alarm; 0.65s says "longer than this book ever pauses on purpose" and leaves the
# other 99.5% of its prosody exactly as the voice performed it.
SEGMENT_INTERNAL_SILENCE_CAP_SECONDS = 0.65
CHAPTER_JOIN_WINDOW_SECONDS = 0.001
CHAPTER_JOIN_JUMP_HARD = 0.70
CHAPTER_JOIN_JUMP_REVIEW = 0.18


@dataclass(frozen=True, slots=True)
class ChapterQualityMetrics:
    expected_duration_seconds: float
    decoded_duration_seconds: float
    duration_error_seconds: float
    sample_rate: int
    channels: int
    mastering_input_lufs: float
    mastering_input_true_peak_db: float
    integrated_loudness_lufs: float
    true_peak_db: float
    loudness_range_lu: float
    rms: float
    peak: float
    clipping_fraction: float
    dc_offset: float
    flat_top_fraction: float
    longest_flat_top_seconds: float
    leading_silence_seconds: float
    trailing_silence_seconds: float
    longest_unexpected_silence_seconds: float
    max_join_jump: float
    max_join_jump_dbfs: float | None
    hard_failures: tuple[str, ...]
    review_flags: tuple[str, ...]
    # What the assembler trimmed off the takes' edges before joining them. Empty on almost
    # every chapter. Recorded because silently altering delivered audio and leaving no trace
    # is how a defect becomes a mystery three versions later.
    trimmed_segment_edges: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class ChapterAssemblyResult:
    checksum: str
    quality: ChapterQualityMetrics


EMOTION_LEVEL_OFFSETS_DB = {
    "angry": 1.5,
    "excited": 1.0,
    "surprised": 0.7,
    "whispering": -2.5,
    "tired": -1.0,
    "tender": -0.5,
}
LOUDNESS_EMOTION_OFFSETS_DB = {
    "angry": 0.8,
    "excited": 0.6,
    "surprised": 0.4,
    "whispering": -2.0,
    "tired": -0.7,
    "tender": -0.3,
}
LOUDNESS_BLOCK_SECONDS = 0.4
RATE_HARD_MIN_FACTOR = 0.55
RATE_HARD_MAX_FACTOR = 1.50
# Sàn nhịp theo ÂM TIẾT mỗi giây (từ = âm tiết), đo trên 8.301 bản thu đã qua của lô 1–3
# (2026-09-10): p0.5 3,22 · p1 3,51 · p2 3,76 · p50 4,67 · p98 6,07. Lấy p2, cùng cách chọn
# sàn 12,5 chars/s; slow/fast tỉ lệ theo dải chữ như cũ (7/12,5 và 14/12,5). Xem
# `pace_is_outlier` cho lý do có hai thước.
PACE_SYLLABLES_PER_SECOND_FLOOR = {"slow": 2.1, "normal": 3.75, "fast": 4.2}
VIENEU_V3_CODEC_SAMPLE_RATE = 48_000
VIENEU_V3_CODEC_SAMPLES_PER_FRAME = 3_840
VIENEU_V3_FRAME_SECONDS = VIENEU_V3_CODEC_SAMPLES_PER_FRAME / VIENEU_V3_CODEC_SAMPLE_RATE
MIN_GENERATION_FRAMES = 48
MAX_GENERATION_FRAMES = 300
GENERATION_PADDING_SECONDS = 2.0
MIN_GENERATION_SECONDS = 3.0
MIN_VALIDATION_SECONDS = 5.0
VALIDATION_PADDING_SECONDS = 8.0
DEFAULT_PACE_LOWER_BOUNDS = {"slow": 6.0, "normal": 10.5, "fast": 12.0}
SHORT_UTTERANCE_MAX_WORDS = 2
SHORT_UTTERANCE_MAX_SPEAKABLE_CHARS = 8
SHORT_UTTERANCE_MIN_GENERATION_FRAMES = 12
SHORT_UTTERANCE_MAX_GENERATION_FRAMES = 24
SEGMENT_ENDPOINT_WINDOW_SECONDS = 0.020

# What one pause costs, fitted on committed segments rather than chosen. Regressing
# duration on (speakable characters, pause groups) over 4095 of them gives 0.060 s per
# character - a pure speech rate of 16.6 chars/s - and 0.276 s per pause.
#
# Groups, not marks. Three models were fitted and the flat per-mark one left the corrected
# rate still correlated with punctuation density at +0.32, over-crediting dense text; a
# three-class model weighting sentence ends above clause breaks fitted marginally better by
# R-squared and was worse still at +0.38. Counting a run of adjacent punctuation as one
# pause left +0.12, because ") :" or " - " is one silence however many characters spell it.
# R-squared was not the objective: removing the confound was, and the best-fitting model was
# the second worst at it.
#
# The figure was 0.281 while syllable hyphens still counted as pauses. Excluding them moved
# it only to 0.276, because in-word hyphens are rare across the corpus - they are
# concentrated in the few segments carrying a transliterated term, which is exactly why
# those segments and only those were failing.
PAUSE_GROUP_SECONDS = 0.276
REPEATED_UTTERANCE_METRIC = "repeated_utterance_score"
# Above this, the two sides of the longest internal silence are saying the same thing.
#
# The owner heard "Mẹ kiếp!" read twice and asked why a real defect was not being fixed. The
# waveform shows it plainly - two syllables, 0.72s of silence, the same two syllables again -
# but nothing in the system saw it: ASR skips a six-character line, the pace gate skips
# anything under rate_check_min_chars, and the duration ceiling for that text is 9.30s.
#
# Duration alone cannot catch it. Measured over the book's 132 short segments, the doubled
# take ranks ninth in seconds-per-character, behind "C", "B" and "—RẦM!!", so any ceiling
# tight enough would reject single letters and sound effects. Energy envelope alone does not
# separate it either: it came 3rd by autocorrelation and outside the top 12 by half
# similarity.
#
# Comparing the MFCCs of the two halves does separate it, and cleanly. Over the 613 segments
# in this book with a long enough internal silence to split, the doubled take scores 0.441
# and ranks first; the next is 0.244 and the rest fall away. A sentence with an ordinary
# pause says different things either side, so its halves do not match. 0.35 sits in the gap
# with room on both sides and flags nothing else in the book.
REPEATED_UTTERANCE_THRESHOLD = 0.35
REPEATED_UTTERANCE_MIN_GAP_SECONDS = 0.25
REPEATED_UTTERANCE_SILENCE_DBFS = -30.0
REPEATED_UTTERANCE_HOP_SECONDS = 0.02
REPEATED_UTTERANCE_MIN_HALF_FRAMES = 4
PAUSE_GROUP_PATTERN = re.compile(r"[.!?…,;:()\[\]{}\-–—/\"'“”‘’]+")
# A hyphen joining two letters marks a syllable inside a transliterated word, not a silence.
SYLLABLE_HYPHEN_PATTERN = re.compile(r"(?<=[^\W\d_])[-–—](?=[^\W\d_])", re.UNICODE)
MIN_SPEECH_SECONDS = 0.05

# The pause budget may never claim more of a segment than this. Across the 3803 committed
# segments long enough for the rate check, the budget reached 52% of duration at the 99.9th
# percentile and 58.5% at most, so this cap is above anything real speech produced.
#
# It exists for the audio that is not real speech. Without it a segment that is mostly
# silence gets almost its whole duration subtracted, and the tiny remainder turns a slow
# reading into an enormous rate - the check would then report "far too fast" for a segment
# whose actual fault is that it is barely speaking at all.
MAX_PAUSE_FRACTION = 0.60


def pause_group_count(text: str) -> int:
    """How many separate silences the punctuation in this text asks for.

    A hyphen between two letters is not one of them. Transliterations are written with
    syllable hyphens - "Đê-phi-lê-ô-nêt" - and counting those as pauses charged this one
    name four silences it never takes: the budget for a single segment went from 0.56 s to
    1.69 s, the speech time left over collapsed, and the apparent rate rose past the
    "impossibly fast" bound. Five segments failed that way in one run, every one of them a
    Vietnamese sentence with an English term transliterated in brackets.

    A dash with space around it - like this one - is still a pause; only the in-word
    hyphen is exempt.
    """
    return len(PAUSE_GROUP_PATTERN.findall(SYLLABLE_HYPHEN_PATTERN.sub("", str(text))))

# An isolated click at the start of an utterance - a listener described it as "a drop of
# water hitting a steel bowl" - loud enough that the first syllable is lost behind it. It is
# a generation lottery, not a property of the voice: the same preset reading the same
# sentence produced a spike of 4.0x on one seed and none at all on two others, so the cure
# is to notice it and let the existing retry draw a different seed.
#
# Magnitude alone cannot find it. Across 2500 accepted segments the median onset spike is
# already 2.7x and the 90th percentile 4.1x, because a plosive (t, k, p) IS a burst of
# energy and a legitimate one. What separates them is width: a plosive carries its burst
# into aspiration and a formant transition and stays above half height for 9-14 ms, while a
# click is over in 5. So the test is tall AND narrow, and neither half is sufficient.
#
# The window is limited to the beginning of the utterance because that is where the defect
# was heard and where it does the most damage - the same word mid-sentence was judged fine.
SEGMENT_ONSET_CLICK_WINDOW_SECONDS = 0.45
SEGMENT_ONSET_CLICK_SHORT_SECONDS = 0.005
SEGMENT_ONSET_CLICK_LONG_SECONDS = 0.060
SEGMENT_ONSET_CLICK_ACTIVE_FRACTION = 0.02
SEGMENT_ONSET_CLICK_MIN_SECONDS = 0.120
# NOT a gate. An A/B listening test rejected it: the twelve segments this scored worst
# (9.8-11.7x) were judged to have no audible defect at all. The numbers are still
# recorded because they cost real measurement to obtain and may yet correlate with
# something, but nothing may fail a segment on them until a listener confirms they hear
# what it marks. See docs/ONSET_CLICK.md.
SEGMENT_ONSET_CLICK_RATIO = 4.0
SEGMENT_ONSET_CLICK_MAX_WIDTH_MS = 6.0


@dataclass(frozen=True, slots=True)
class SegmentDurationPolicy:
    generation_max_frames: int
    validation_max_seconds: float

    @property
    def generation_ceiling_seconds(self) -> float:
        return self.generation_max_frames * VIENEU_V3_FRAME_SECONDS


def _segment_value(segment: Any, key: str, default: Any) -> Any:
    try:
        value = segment[key]
    except (KeyError, TypeError):
        return default
    return default if value is None else value


_DIGIT_RUN = re.compile(r"\d+")


def spoken_syllables(text: str) -> int:
    """Số âm tiết đọc ra, xấp xỉ bằng số từ: tiếng Việt đơn âm, một từ là một âm tiết.

    Xấp xỉ này đếm THIẾU ở tên nước ngoài ("Alice" hai âm tiết) và chữ số ("22" đọc ba âm
    tiết), tức nhịp âm tiết đo ra thấp hơn thật. Đó là chiều sai an toàn cho việc nó được
    dùng: một bản thu chỉ được tha khi nhịp âm tiết đủ cao, nên đếm thiếu chỉ làm giữ nguyên
    cờ như cũ chứ không tha thêm.
    """
    return sum(1 for token in text.split() if any(char.isalnum() for char in token))


def pace_is_outlier(
    rate: float,
    syllable_rate: float,
    pace: str,
    bounds: "tuple[float, float] | list[float]",
) -> bool:
    """Chậm chỉ khi chậm theo CẢ chữ lẫn âm tiết; nhanh vẫn xét theo chữ như cũ.

    Chương 075 của lô 3 mất câu "Và Alice đã ở đó để tận dụng sơ hở ấy." sau 10/10 lần thử ở
    10,64–11,80 chars/s, sàn 12,5. Câu ấy có 2,25 chữ mỗi từ (trung vị kho: 3,33): cùng một
    tốc độ đọc thì câu toàn từ ngắn cho ra ít chữ mỗi giây hơn, và thước "chars/s" gọi nó là
    chậm. Đo theo âm tiết: 4,48/giây, gần trung vị kho (4,67). Bản thu không chậm; thước chậm.

    Cùng họ với `spoken_speakable_chars` (chữ số): thước chữ đếm sai cái nó nhận là đếm, và
    cách sửa là thêm phép đếm thứ hai rồi chỉ kết tội khi cả hai cùng nói. Thay đổi một chiều:
    chỉ bớt cờ, không thêm; bản thu được tha thêm phải có nhịp âm tiết trong dải bình thường
    (`PACE_SYLLABLES_PER_SECOND_FLOOR`). Cận trên giữ nguyên theo chữ - chưa có ca nào đòi hơn.
    """
    lower_bound = float(bounds[0])
    upper_bound = float(bounds[1])
    syllable_floor = PACE_SYLLABLES_PER_SECOND_FLOOR.get(
        pace, PACE_SYLLABLES_PER_SECOND_FLOOR["normal"]
    )
    too_slow = rate < lower_bound and syllable_rate < syllable_floor
    return bool(too_slow or rate > upper_bound)


def spoken_speakable_chars(text: str) -> int:
    """Ký tự đọc được, đếm như **giọng đọc phát ra**, không phải như chữ viết.

    VieNeu đọc `22` thành "hai mươi hai": hai ký tự viết, mười một ký tự nói. Đếm chuỗi viết
    làm mọi văn bản có chữ số trông chậm hơn thực tế, và phép kiểm nhịp thì so với một sàn
    tính trên văn bản không có số.

    alpha.57 mất tiêu đề chương 023 vì đúng chuyện đó: `Chương 22 - 22: Ấn tượng đầu tiên` là
    24 ký tự viết và 40 ký tự đọc, nên ở 2,25 giây nó đo ra 10,68 kt/s (dưới sàn 12,5) trong
    khi tai người nghe 17,78 kt/s (giữa dải). Mười một lần thử, mười một lần cùng con số -
    không phải xui mà là số học. Chương mất tiêu đề thì không xuất bản được.

    `asr.py` đã gọi `vietnamese_number_words` từ lâu, vì so bản ghi với văn bản cũng đòi nở số
    ra chữ trước. Đây là cùng một sự thật, áp cho phép đo nhịp.

    **Giới hạn còn lại, cố ý không lấp bằng phỏng đoán:** `vietnamese_number_words` chỉ nở tới
    999 và ném lỗi trên số lớn hơn. Số từ 1000 trở lên vẫn được đếm theo chữ viết, tức vẫn bị
    tính thiếu. Bịa một hệ số ước cho chúng sẽ là đoán, và đoán chính là thứ đã tạo ra lỗi này.
    """
    def expand(match: "re.Match[str]") -> str:
        try:
            return vietnamese_number_words(int(match.group()))
        except (ValueError, OverflowError):
            return match.group()

    return sum(char.isalnum() for char in _DIGIT_RUN.sub(expand, text))


def is_short_utterance(text: str) -> bool:
    words = re.findall(r"[^\W_]+(?:-[^\W_]+)*", text, re.UNICODE)
    speakable_chars = sum(char.isalnum() for char in text)
    if not words or speakable_chars > SHORT_UTTERANCE_MAX_SPEAKABLE_CHARS:
        return False
    return len(words) <= SHORT_UTTERANCE_MAX_WORDS


def segment_duration_policy(
    text: str,
    settings: dict[str, Any] | None,
    segment: Any | None = None,
) -> SegmentDurationPolicy:
    tts = (settings or {}).get("tts", {})
    pace = str(_segment_value(segment, "pace", "normal")) if segment is not None else "normal"
    configured_bounds = tts.get("pace_chars_per_second", {})
    configured = configured_bounds.get(pace, DEFAULT_PACE_LOWER_BOUNDS.get(pace, 10.5))
    lower_bound = float(configured[0] if isinstance(configured, (list, tuple)) else configured)
    speakable_chars = max(1, spoken_speakable_chars(text))
    generation_seconds = max(
        MIN_GENERATION_SECONDS,
        speakable_chars / max(1.0, lower_bound) + GENERATION_PADDING_SECONDS,
    )
    chars = max(1, len(text.strip()))
    max_seconds_per_100_chars = float(tts.get("max_seconds_per_100_chars", 13.0))
    validation_seconds = max(
        MIN_VALIDATION_SECONDS,
        chars / 100 * max_seconds_per_100_chars + VALIDATION_PADDING_SECONDS,
    )

    requested_frames = math.ceil(generation_seconds / VIENEU_V3_FRAME_SECONDS)
    safe_frames = math.floor(
        (validation_seconds - VIENEU_V3_FRAME_SECONDS) / VIENEU_V3_FRAME_SECONDS
    )
    if is_short_utterance(text):
        max_frames = max(
            SHORT_UTTERANCE_MIN_GENERATION_FRAMES,
            min(SHORT_UTTERANCE_MAX_GENERATION_FRAMES, requested_frames, safe_frames),
        )
    else:
        max_frames = max(
            MIN_GENERATION_FRAMES,
            min(MAX_GENERATION_FRAMES, requested_frames, safe_frames),
        )
    policy = SegmentDurationPolicy(
        generation_max_frames=max_frames,
        validation_max_seconds=validation_seconds,
    )
    if policy.generation_ceiling_seconds >= policy.validation_max_seconds:
        raise ValueError("VieNeu generation budget must stay below the audio validation limit")
    return policy


def vieneu_generation_reached_frame_ceiling(
    audio: Any,
    policy: SegmentDurationPolicy,
) -> bool:
    """Report that VieNeu returned every allowed codec frame; validation decides whether audio is usable."""
    generated_samples = np.asarray(audio).size
    ceiling_samples = policy.generation_max_frames * VIENEU_V3_CODEC_SAMPLES_PER_FRAME
    return generated_samples >= ceiling_samples


def onset_click_metrics(audio: np.ndarray, sample_rate: int) -> tuple[float, float]:
    """Measure the sharpest energy spike near the start of speech.

    Returns (ratio, width_ms) for the strongest candidate: how far a 5 ms window rises above
    its 60 ms surroundings, and how long it stays above half that height. See
    SEGMENT_ONSET_CLICK_RATIO for why both numbers are needed.
    """
    array = np.asarray(audio, dtype=np.float64).reshape(-1)
    if array.size < int(sample_rate * SEGMENT_ONSET_CLICK_MIN_SECONDS):
        return (0.0, 0.0)
    short_size = max(1, int(sample_rate * SEGMENT_ONSET_CLICK_SHORT_SECONDS))
    long_size = max(1, int(sample_rate * SEGMENT_ONSET_CLICK_LONG_SECONDS))
    power = np.square(array)
    short = np.convolve(power, np.ones(short_size) / short_size, mode="same")
    long = np.convolve(power, np.ones(long_size) / long_size, mode="same")
    peak = float(long.max())
    if peak <= 0.0:
        return (0.0, 0.0)
    voiced = np.flatnonzero(long > SEGMENT_ONSET_CLICK_ACTIVE_FRACTION * peak)
    if voiced.size == 0:
        return (0.0, 0.0)
    onset = int(voiced[0])
    end = min(array.size, onset + int(sample_rate * SEGMENT_ONSET_CLICK_WINDOW_SECONDS))
    ratios = short[onset:end] / np.maximum(long[onset:end], 1e-12)
    if ratios.size == 0:
        return (0.0, 0.0)
    index = int(np.argmax(ratios))
    ratio = float(ratios[index])
    half = ratio * 0.5
    left = index
    while left > 0 and ratios[left] > half:
        left -= 1
    right = index
    while right < ratios.size - 1 and ratios[right] > half:
        right += 1
    return (ratio, 1000.0 * float(right - left) / sample_rate)


def signal_metrics(audio: np.ndarray, sample_rate: int) -> dict[str, float]:
    array = np.asarray(audio, dtype=np.float32)
    if array.ndim == 2 and 1 in array.shape:
        array = array.reshape(-1)
    if array.ndim != 1:
        raise AudioQualityError(f"audio must be mono, got shape {array.shape}")
    if array.size == 0:
        return {
            "duration": 0.0,
            "rms": 0.0,
            "peak": 0.0,
            "clipping_fraction": 0.0,
            "trailing_rms": 0.0,
            "onset_click_ratio": 0.0,
            "onset_click_width_ms": 0.0,
        }
    endpoint_samples = min(
        array.size,
        max(1, int(round(sample_rate * SEGMENT_ENDPOINT_WINDOW_SECONDS))),
    )
    trailing = array[-endpoint_samples:].astype(np.float64)
    onset_ratio, onset_width = onset_click_metrics(array, sample_rate)
    return {
        "duration": float(array.size / sample_rate),
        "rms": float(math.sqrt(float(np.mean(np.square(array.astype(np.float64)))))) if array.size else 0.0,
        "peak": float(np.max(np.abs(array))),
        "clipping_fraction": float(np.mean(np.abs(array) >= 0.999)),
        "trailing_rms": float(math.sqrt(float(np.mean(np.square(trailing))))),
        "onset_click_ratio": onset_ratio,
        "onset_click_width_ms": onset_width,
    }


def _active_rms(audio: np.ndarray, sample_rate: int, floor_dbfs: float) -> float:
    frame_size = max(1, int(sample_rate * 0.02))
    usable_size = audio.size - (audio.size % frame_size)
    if usable_size <= 0:
        return 0.0
    frames = audio[:usable_size].astype(np.float64).reshape(-1, frame_size)
    frame_rms = np.sqrt(np.mean(np.square(frames), axis=1))
    active = frame_rms[frame_rms >= 10 ** (floor_dbfs / 20.0)]
    return float(math.sqrt(float(np.mean(np.square(active))))) if active.size else 0.0


@lru_cache(maxsize=4)
def _loudness_meter(sample_rate: int) -> pyln.Meter:
    return pyln.Meter(sample_rate, block_size=LOUDNESS_BLOCK_SECONDS)


def integrated_loudness_lufs(audio: np.ndarray, sample_rate: int) -> float | None:
    array = np.asarray(audio, dtype=np.float64).reshape(-1)
    if sample_rate <= 0 or array.size < int(round(sample_rate * LOUDNESS_BLOCK_SECONDS)):
        return None
    try:
        loudness = float(_loudness_meter(sample_rate).integrated_loudness(array))
    except (ValueError, ZeroDivisionError):
        return None
    return loudness if math.isfinite(loudness) else None


def normalize_segment_level(
    audio: np.ndarray,
    sample_rate: int,
    segment: Any,
    settings: dict[str, Any],
) -> np.ndarray:
    array = np.asarray(audio, dtype=np.float32).reshape(-1)
    if not array.size:
        return array
    audio_cfg = settings["audio"]
    active_rms = _active_rms(
        array,
        sample_rate,
        float(audio_cfg.get("segment_active_floor_dbfs", -45.0)),
    )
    if active_rms <= 0:
        return array
    volume = str(_segment_value(segment, "volume", "normal"))
    lufs_targets = audio_cfg.get("segment_target_lufs")
    if isinstance(lufs_targets, dict) and "normal" in lufs_targets:
        target_level = float(lufs_targets.get(volume, lufs_targets["normal"]))
        speaker = str(_segment_value(segment, "speaker", ""))
        if speaker == "NARRATOR":
            target_level += float(audio_cfg.get("segment_narrator_offset_db", 0.0))
        if volume == "normal":
            emotion = str(_segment_value(segment, "emotion", "neutral"))
            intensity = max(0, min(3, int(_segment_value(segment, "intensity", 0))))
            target_level += LOUDNESS_EMOTION_OFFSETS_DB.get(emotion, 0.0) * intensity / 3.0
        measured_level = integrated_loudness_lufs(array, sample_rate)
        if measured_level is None:
            measured_level = 20.0 * math.log10(active_rms)
    else:
        # Locked books created before LUFS leveling retain their original RMS policy.
        targets = audio_cfg["segment_target_dbfs"]
        target_level = float(targets.get(volume, targets["normal"]))
        if volume == "normal":
            emotion = str(_segment_value(segment, "emotion", "neutral"))
            intensity = max(0, min(3, int(_segment_value(segment, "intensity", 0))))
            target_level += EMOTION_LEVEL_OFFSETS_DB.get(emotion, 0.0) * intensity / 3.0
        measured_level = 20.0 * math.log10(active_rms)
    desired_gain = 10 ** ((target_level - measured_level) / 20.0)
    peak = float(np.max(np.abs(array)))
    peak_limit = 10 ** (float(audio_cfg.get("segment_peak_dbfs", -2.0)) / 20.0)
    peak_safe_gain = peak_limit / peak if peak > 0 else desired_gain
    gain = min(desired_gain, peak_safe_gain)
    return np.asarray(array * gain, dtype=np.float32)


def validate_audio_array(
    audio: Any,
    text: str,
    settings: dict[str, Any],
    sample_rate: int,
    segment: Any | None = None,
) -> tuple[np.ndarray, dict[str, float]]:
    if sample_rate <= 0:
        raise AudioQualityError(f"invalid sample rate: {sample_rate}")
    expected_sample_rate = int(settings["tts"]["sample_rate"])
    if sample_rate != expected_sample_rate:
        raise AudioQualityError(
            f"audio sample rate mismatch: {sample_rate} Hz, expected {expected_sample_rate} Hz"
        )
    array = np.asarray(audio, dtype=np.float32)
    if array.ndim == 2 and 1 in array.shape:
        array = array.reshape(-1)
    if array.ndim != 1:
        raise AudioQualityError(f"audio must be mono, got shape {array.shape}")
    if array.size == 0:
        raise AudioQualityError("model returned empty audio")
    if not np.isfinite(array).all():
        raise AudioQualityError("audio contains NaN or infinity")
    metrics = signal_metrics(array, sample_rate)
    loudness = integrated_loudness_lufs(array, sample_rate)
    if loudness is not None:
        metrics["loudness_lufs"] = loudness
    chars = max(1, len(text.strip()))
    min_duration = max(0.20, chars / 100 * float(settings["tts"]["min_seconds_per_100_chars"]))
    max_duration = segment_duration_policy(text, settings, segment).validation_max_seconds
    if metrics["duration"] < min_duration:
        raise AudioQualityError(f"audio too short: {metrics['duration']:.2f}s < {min_duration:.2f}s")
    if metrics["duration"] > max_duration:
        raise AudioQualityError(f"audio unusually long: {metrics['duration']:.2f}s > {max_duration:.2f}s")
    if metrics["rms"] < float(settings["tts"]["min_rms"]):
        raise AudioQualityError(f"audio RMS too low: {metrics['rms']:.6f}")
    if metrics["clipping_fraction"] > float(settings["tts"]["max_clipping_fraction"]):
        raise AudioQualityError(f"audio clipping: {metrics['clipping_fraction']:.4%}")
    speakable_chars = spoken_speakable_chars(text)
    if (
        segment is not None
        and speakable_chars >= int(settings["tts"].get("rate_check_min_chars", 24))
    ):
        pace = str(_segment_value(segment, "pace", "normal"))
        bounds = settings["tts"]["pace_chars_per_second"].get(
            pace,
            settings["tts"]["pace_chars_per_second"]["normal"],
        )
        # Charge the pauses punctuation forces to the pauses, not to the speaker. Dividing
        # characters by wall-clock time measures punctuation density as much as speed: over
        # 3781 real segments the two correlate at -0.62, and a segment in the densest tenth
        # was 260 times likelier to be called too slow than one in the lightest - 26.1%
        # against 0.1% - for reading its punctuation properly.
        pause_seconds = min(
            PAUSE_GROUP_SECONDS * pause_group_count(text),
            metrics["duration"] * MAX_PAUSE_FRACTION,
        )
        speech_seconds = max(metrics["duration"] - pause_seconds, MIN_SPEECH_SECONDS)
        rate = speakable_chars / speech_seconds
        metrics["pause_group_count"] = float(pause_group_count(text))
        lower_bound = float(bounds[0])
        upper_bound = float(bounds[1])
        hard_lower = lower_bound * RATE_HARD_MIN_FACTOR
        hard_upper = upper_bound * RATE_HARD_MAX_FACTOR
        if rate < hard_lower or rate > hard_upper:
            raise AudioQualityError(
                f"speech rate far outside {pace} safety range: {rate:.2f} chars/s not in "
                f"[{hard_lower:.2f}, {hard_upper:.2f}]"
            )
        syllable_rate = spoken_syllables(text) / speech_seconds
        metrics["chars_per_second"] = float(rate)
        metrics["syllables_per_second"] = float(syllable_rate)
        metrics["pace_outlier"] = float(pace_is_outlier(rate, syllable_rate, pace, bounds))
    score = repeated_utterance_score(array, sample_rate)
    if score is not None:
        metrics[REPEATED_UTTERANCE_METRIC] = float(score)
    return array, metrics


def repeated_utterance_score(audio: Any, sample_rate: int) -> float | None:
    """How alike the two sides of the longest internal silence sound.

    VieNeu occasionally says a short line twice. Nothing else in the pipeline can see it:
    the transcript check skips text this short, the pace gate skips it too, and the duration
    ceiling for a six-character line is nine seconds. See REPEATED_UTTERANCE_THRESHOLD for
    what was measured and what was ruled out.

    Returns None when there is no internal silence long enough to split on, which is most
    audio, and the caller records nothing.
    """
    try:
        import librosa
    except ImportError:  # pragma: no cover - librosa ships with the runtime
        return None
    array = np.asarray(audio, dtype=np.float32).reshape(-1)
    hop = max(1, int(sample_rate * REPEATED_UTTERANCE_HOP_SECONDS))
    if array.size < hop * 8:
        return None
    rms = librosa.feature.rms(y=array, frame_length=hop * 2, hop_length=hop)[0]
    peak = float(rms.max())
    if peak <= 0.0:
        return None
    quiet = 20.0 * np.log10(rms / peak + 1e-12) < REPEATED_UTTERANCE_SILENCE_DBFS

    # The longest quiet run that is not at either edge - leading and trailing silence say
    # nothing about repetition.
    longest, span, index = 0, None, 0
    while index < len(quiet):
        if not quiet[index]:
            index += 1
            continue
        end = index
        while end < len(quiet) and quiet[end]:
            end += 1
        if index > 2 and end < len(quiet) - 2 and (end - index) > longest:
            longest, span = end - index, (index, end)
        index = end
    if span is None or longest * REPEATED_UTTERANCE_HOP_SECONDS < REPEATED_UTTERANCE_MIN_GAP_SECONDS:
        return None

    coefficients = librosa.feature.mfcc(y=array, sr=sample_rate, n_mfcc=13, hop_length=hop)
    left, right = coefficients[:, : span[0]], coefficients[:, span[1] :]
    if left.shape[1] < REPEATED_UTTERANCE_MIN_HALF_FRAMES:
        return None
    if right.shape[1] < REPEATED_UTTERANCE_MIN_HALF_FRAMES:
        return None

    # Stretched to a common length: the two readings are the same words, not the same
    # duration, so comparing them frame for frame would miss on tempo alone.
    width = min(left.shape[1], right.shape[1])

    def resample(matrix: Any) -> Any:
        source = np.linspace(0.0, 1.0, matrix.shape[1])
        target = np.linspace(0.0, 1.0, width)
        return np.stack([np.interp(target, source, matrix[row]) for row in range(matrix.shape[0])])

    def standardize(matrix: Any) -> Any:
        return (matrix - matrix.mean(axis=1, keepdims=True)) / (
            matrix.std(axis=1, keepdims=True) + 1e-9
        )

    left, right = standardize(resample(left)), standardize(resample(right))
    return float(np.mean(np.sum(left * right, axis=1) / width))


def inspect_wav(
    path: Path,
    text: str,
    settings: dict[str, Any],
    segment: Any | None = None,
) -> tuple[bool, dict[str, float], str]:
    try:
        audio, sample_rate = sf.read(path, dtype="float32", always_2d=False)
        _, metrics = validate_audio_array(audio, text, settings, sample_rate, segment=segment)
        return True, metrics, "ok"
    except Exception as exc:  # noqa: BLE001
        return False, {}, str(exc)


def atomic_write_wav(
    path: Path,
    audio: Any,
    sample_rate: int,
    text: str,
    settings: dict[str, Any],
    segment: Any | None = None,
) -> tuple[str, dict[str, float]]:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.stem + ".part" + path.suffix)
    temp.unlink(missing_ok=True)
    array, _ = validate_audio_array(audio, text, settings, sample_rate, segment=segment)
    if segment is not None:
        array = normalize_segment_level(array, sample_rate, segment, settings)
    array, _ = validate_audio_array(array, text, settings, sample_rate, segment=segment)
    sf.write(temp, array, sample_rate, subtype="PCM_16")
    # Windows rejects fsync on a read-only descriptor (WinError 9).
    with temp.open("rb+") as handle:
        os.fsync(handle.fileno())
    valid, metrics, reason = inspect_wav(temp, text, settings, segment=segment)
    if not valid:
        temp.unlink(missing_ok=True)
        raise AudioQualityError(f"temporary WAV failed validation: {reason}")
    checksum = sha256_file(temp)
    os.replace(temp, path)
    return checksum, metrics


def _inspect_pcm16_mono_wav(path: Path) -> tuple[np.ndarray, int, dict[str, float]]:
    try:
        info = sf.info(path)
        audio, sample_rate = sf.read(path, dtype="float32", always_2d=False)
    except (OSError, RuntimeError, sf.LibsndfileError) as exc:
        raise AudioQualityError(f"cannot decode WAV: {path}") from exc
    if info.format != "WAV":
        raise AudioQualityError(f"audio transform requires WAV input, got {info.format or 'unknown'}")
    if info.subtype != "PCM_16":
        raise AudioQualityError(
            f"audio transform requires PCM_16 input, got {info.subtype or 'unknown'}"
        )
    if info.channels != 1:
        raise AudioQualityError(f"audio transform requires mono input, got {info.channels} channels")
    if sample_rate <= 0:
        raise AudioQualityError(f"audio transform has invalid sample rate: {sample_rate}")
    array = np.asarray(audio, dtype=np.float32)
    if array.ndim != 1:
        raise AudioQualityError(f"audio transform requires mono input, got shape {array.shape}")
    if array.size == 0:
        raise AudioQualityError("audio transform input is empty")
    if not np.isfinite(array).all():
        raise AudioQualityError("audio transform input contains NaN or infinity")
    metrics = signal_metrics(array, int(sample_rate))
    if metrics["rms"] <= 0:
        raise AudioQualityError("audio transform input has no audible signal")
    return array, int(sample_rate), metrics


def tempo_stretch_wav_atomic(
    source: Path,
    destination: Path,
) -> tuple[str, dict[str, float | int]]:
    """Apply the locked 0.94 atempo profile without modifying the source WAV."""
    source = source.resolve()
    destination = destination.resolve()
    if source == destination:
        raise AudioQualityError("audio transform source and destination must differ")
    if destination.suffix.casefold() != ".wav":
        raise AudioQualityError("audio transform destination must use the .wav extension")
    source_audio, source_sample_rate, _ = _inspect_pcm16_mono_wav(source)
    source_samples = int(source_audio.size)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp = destination.with_name(destination.stem + ".part" + destination.suffix)
    temp.unlink(missing_ok=True)
    ffmpeg = ffmpeg_executable()
    command = [
        ffmpeg,
        "-hide_banner",
        "-nostats",
        "-loglevel",
        "error",
        "-nostdin",
        "-y",
        "-i",
        str(source),
        "-map",
        "0:a:0",
        "-vn",
        "-af",
        f"atempo={_ffmpeg_number(POSTPROCESS_TEMPO_FACTOR)}",
        "-ac",
        "1",
        "-ar",
        str(source_sample_rate),
        "-c:a",
        POSTPROCESS_OUTPUT_CODEC,
        str(temp),
    ]
    try:
        result = run_hidden(command, timeout=3600, check=False)
        if result.returncode != 0:
            raise AudioQualityError(f"FFmpeg tempo transform failed: {result.stderr[-3000:]}")
        if not temp.exists():
            raise AudioQualityError("FFmpeg tempo transform did not produce a WAV")
        output_audio, output_sample_rate, output_metrics = _inspect_pcm16_mono_wav(temp)
        if output_sample_rate != source_sample_rate:
            raise AudioQualityError(
                "FFmpeg tempo transform changed the sample rate: "
                f"{output_sample_rate} Hz != {source_sample_rate} Hz"
            )
        output_samples = int(output_audio.size)
        expected_samples = source_samples / POSTPROCESS_TEMPO_FACTOR
        relative_error = abs(output_samples - expected_samples) / expected_samples
        if relative_error > POSTPROCESS_SAMPLE_COUNT_RELATIVE_TOLERANCE:
            raise AudioQualityError(
                "FFmpeg tempo transform returned an unexpected sample count: "
                f"{output_samples} != approximately {expected_samples:.0f}"
            )
        with temp.open("rb+") as handle:
            os.fsync(handle.fileno())
        checksum = sha256_file(temp)
        os.replace(temp, destination)
        return checksum, {
            POSTPROCESS_SOURCE_SAMPLE_RATE_FIELD: source_sample_rate,
            POSTPROCESS_SOURCE_SAMPLES_FIELD: source_samples,
            POSTPROCESS_OUTPUT_SAMPLES_FIELD: output_samples,
            **output_metrics,
        }
    finally:
        temp.unlink(missing_ok=True)


def merge_wav_parts_atomic(
    parts: list[Path],
    destination: Path,
    text: str,
    settings: dict[str, Any],
    pause_seconds: float = 0.12,
    segment: Any | None = None,
) -> tuple[str, dict[str, float]]:
    if not parts:
        raise AudioQualityError("no WAV parts to merge")
    arrays: list[np.ndarray] = []
    sample_rate: int | None = None
    for index, part in enumerate(parts):
        audio, sr = sf.read(part, dtype="float32", always_2d=False)
        if np.asarray(audio).ndim != 1:
            raise AudioQualityError(f"WAV part is not mono: {part}")
        if sample_rate is None:
            sample_rate = int(sr)
        elif int(sr) != sample_rate:
            raise AudioQualityError("WAV parts have different sample rates")
        arrays.append(np.asarray(audio, dtype=np.float32))
        if index + 1 < len(parts):
            arrays.append(np.zeros(int(sample_rate * pause_seconds), dtype=np.float32))
    assert sample_rate is not None
    merged = np.concatenate(arrays)
    return atomic_write_wav(destination, merged, sample_rate, text, settings, segment=segment)


def verify_mp3(path: Path) -> tuple[bool, str]:
    if not path.exists() or path.stat().st_size < 4096:
        return False, "MP3 missing or too small"
    ffmpeg = ffmpeg_executable()
    try:
        result = run_hidden(
            [ffmpeg, "-hide_banner", "-loglevel", "error", "-i", str(path), "-f", "null", "-"],
            timeout=3600,
            check=False,
        )
        if result.returncode != 0:
            return False, result.stderr[-3000:]
        return True, "ok"
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)


def _concat_line(path: Path) -> str:
    escaped = path.resolve().as_posix().replace("'", "'\\''")
    return f"file '{escaped}'"


def _silence_file(work_dir: Path, milliseconds: int, sample_rate: int) -> Path:
    milliseconds = max(0, int(milliseconds))
    work_dir.mkdir(parents=True, exist_ok=True)
    path = work_dir / f"silence_{milliseconds:04d}ms_{sample_rate}.wav"
    if path.exists() and path.stat().st_size > 128:
        return path
    samples = np.zeros(int(sample_rate * milliseconds / 1000), dtype=np.float32)
    temp = path.with_name(path.stem + ".part" + path.suffix)
    temp.unlink(missing_ok=True)
    sf.write(temp, samples, sample_rate, subtype="PCM_16")
    with temp.open("rb+") as handle:
        os.fsync(handle.fileno())
    os.replace(temp, path)
    return path


def _ffmpeg_number(value: float) -> str:
    if not math.isfinite(value):
        raise AudioQualityError(f"FFmpeg metric is not finite: {value}")
    return format(value, ".10g")


def _parse_loudnorm_metrics(stderr: str) -> dict[str, float]:
    matches = re.findall(r'\{\s*"input_i".*?\}', stderr, flags=re.DOTALL)
    if not matches:
        raise AudioQualityError(f"FFmpeg loudnorm did not return JSON metrics: {stderr[-3000:]}")
    try:
        raw = json.loads(matches[-1])
        metrics = {
            key: float(raw[key])
            for key in ("input_i", "input_tp", "input_lra", "input_thresh", "target_offset")
        }
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise AudioQualityError("FFmpeg loudnorm returned invalid metrics") from exc
    if not all(math.isfinite(value) for value in metrics.values()):
        raise AudioQualityError(f"FFmpeg loudnorm returned non-finite metrics: {metrics}")
    return metrics


def _measure_loudness(
    input_args: list[str],
    audio_cfg: dict[str, Any],
    *,
    timeout: float = 7200,
) -> dict[str, float]:
    ffmpeg = ffmpeg_executable()
    loudnorm = (
        f"loudnorm=I={_ffmpeg_number(float(audio_cfg['loudness_lufs']))}:"
        f"TP={_ffmpeg_number(float(audio_cfg['true_peak_db']))}:"
        f"LRA={_ffmpeg_number(float(audio_cfg['lra']))}:print_format=json"
    )
    command = [
        ffmpeg,
        "-hide_banner",
        "-nostats",
        "-loglevel",
        "info",
        "-nostdin",
        *input_args,
        "-map",
        "0:a:0",
        "-af",
        loudnorm,
        "-f",
        "null",
        "-",
    ]
    result = run_hidden(command, timeout=timeout, check=False)
    if result.returncode != 0:
        raise AudioQualityError(f"FFmpeg loudness measurement failed: {result.stderr[-3000:]}")
    return _parse_loudnorm_metrics(result.stderr)


def _second_pass_loudnorm_filter(
    audio_cfg: dict[str, Any],
    measured: dict[str, float],
) -> str:
    return "loudnorm=" + ":".join(
        (
            f"I={_ffmpeg_number(float(audio_cfg['loudness_lufs']))}",
            f"TP={_ffmpeg_number(float(audio_cfg['true_peak_db']))}",
            f"LRA={_ffmpeg_number(float(audio_cfg['lra']))}",
            f"measured_I={_ffmpeg_number(measured['input_i'])}",
            f"measured_TP={_ffmpeg_number(measured['input_tp'])}",
            f"measured_LRA={_ffmpeg_number(measured['input_lra'])}",
            f"measured_thresh={_ffmpeg_number(measured['input_thresh'])}",
            f"offset={_ffmpeg_number(measured['target_offset'])}",
            "linear=true",
            "print_format=summary",
        )
    )


def _source_timeline(
    entries: list[tuple[Path, int]],
    sample_rate: int,
) -> tuple[float, list[tuple[float, float]], list[float]]:
    elapsed = 0.0
    break_ranges: list[tuple[float, float]] = []
    join_times: list[float] = []
    for index, (path, break_ms) in enumerate(entries):
        try:
            info = sf.info(path)
        except Exception as exc:  # noqa: BLE001
            raise AudioQualityError(f"cannot inspect WAV: {path}: {exc}") from exc
        if info.channels != 1:
            raise AudioQualityError(f"chapter WAV is not mono: {path}")
        if info.samplerate != sample_rate:
            raise AudioQualityError(
                f"chapter WAV sample rate mismatch: {path}: {info.samplerate} != {sample_rate}"
            )
        if info.frames <= 0:
            raise AudioQualityError(f"chapter WAV is empty: {path}")
        elapsed += info.frames / sample_rate
        if index + 1 >= len(entries):
            continue
        join_times.append(elapsed)
        if break_ms <= 0:
            continue
        pause_seconds = break_ms / 1000.0
        break_ranges.append((elapsed, elapsed + pause_seconds))
        elapsed += pause_seconds
        join_times.append(elapsed)
    return elapsed, break_ranges, join_times


def _decode_mp3_candidate(candidate: Path, decoded_wav: Path) -> tuple[np.ndarray, int, int]:
    decoded_wav.unlink(missing_ok=True)
    command = [
        ffmpeg_executable(),
        "-hide_banner",
        "-nostats",
        "-loglevel",
        "error",
        "-nostdin",
        "-y",
        "-i",
        str(candidate),
        "-map",
        "0:a:0",
        "-codec:a",
        "pcm_f32le",
        str(decoded_wav),
    ]
    result = run_hidden(command, timeout=3600, check=False)
    if result.returncode != 0:
        raise AudioQualityError(f"temporary MP3 failed full decode: {result.stderr[-3000:]}")
    try:
        audio, sample_rate = sf.read(decoded_wav, dtype="float32", always_2d=True)
    except Exception as exc:  # noqa: BLE001
        raise AudioQualityError(f"cannot inspect decoded candidate: {exc}") from exc
    array = np.asarray(audio, dtype=np.float32)
    if array.ndim != 2 or array.shape[0] == 0:
        raise AudioQualityError(f"decoded candidate has invalid shape: {array.shape}")
    if not np.isfinite(array).all():
        raise AudioQualityError("decoded candidate contains NaN or infinity")
    return array, int(sample_rate), int(array.shape[1])


def _longest_true_run(mask: np.ndarray) -> int:
    values = np.asarray(mask, dtype=np.bool_)
    if not values.size or not values.any():
        return 0
    padded = np.concatenate((np.array([False]), values, np.array([False])))
    edges = np.flatnonzero(padded[1:] != padded[:-1])
    return int(np.max(edges[1::2] - edges[::2]))


def _flat_top_metrics(audio: np.ndarray, sample_rate: int) -> tuple[float, float]:
    if audio.size < 2:
        return 0.0, 0.0
    absolute = np.abs(audio.astype(np.float64))
    peak = float(np.max(absolute))
    if peak <= 0:
        return 0.0, 0.0
    high = absolute >= peak * CHAPTER_FLAT_TOP_RELATIVE_LEVEL
    derivative = np.abs(np.diff(audio.astype(np.float64), prepend=float(audio[0])))
    flat = high & (derivative <= CHAPTER_FLAT_TOP_DERIVATIVE)
    return float(np.mean(flat)), float(_longest_true_run(flat) / sample_rate)


def _silence_metrics(
    audio: np.ndarray,
    sample_rate: int,
    expected_breaks: list[tuple[float, float]],
) -> tuple[float, float, float]:
    frame_size = max(1, int(round(sample_rate * CHAPTER_SILENCE_FRAME_SECONDS)))
    frame_count = audio.size // frame_size
    if frame_count <= 0:
        return 0.0, 0.0, 0.0
    frames = audio[: frame_count * frame_size].astype(np.float64).reshape(frame_count, frame_size)
    rms = np.sqrt(np.mean(np.square(frames), axis=1))
    silent = rms <= 10 ** (CHAPTER_SILENCE_FLOOR_DBFS / 20.0)
    leading_frames = 0
    for value in silent:
        if not value:
            break
        leading_frames += 1
    trailing_frames = 0
    for value in silent[::-1]:
        if not value:
            break
        trailing_frames += 1
    centers = (np.arange(frame_count, dtype=np.float64) + 0.5) * frame_size / sample_rate
    expected = np.zeros(frame_count, dtype=np.bool_)
    for start, end in expected_breaks:
        expected |= (centers >= start) & (centers <= end)
    unexpected = silent & ~expected
    return (
        leading_frames * frame_size / sample_rate,
        trailing_frames * frame_size / sample_rate,
        _longest_true_run(unexpected) * frame_size / sample_rate,
    )


def _edge_silence_seconds(audio: np.ndarray, sample_rate: int) -> tuple[float, float]:
    """(leading, trailing) dead air, by the same floor the chapter check uses."""
    frame_size = max(1, int(round(sample_rate * CHAPTER_SILENCE_FRAME_SECONDS)))
    frame_count = audio.size // frame_size
    if frame_count <= 0:
        return 0.0, 0.0
    frames = audio[: frame_count * frame_size].astype(np.float64).reshape(frame_count, frame_size)
    rms = np.sqrt(np.mean(np.square(frames), axis=1))
    silent = rms <= 10 ** (CHAPTER_SILENCE_FLOOR_DBFS / 20.0)
    leading = 0
    for value in silent:
        if not value:
            break
        leading += 1
    trailing = 0
    for value in silent[::-1]:
        if not value:
            break
        trailing += 1
    if leading >= frame_count:
        return 0.0, 0.0  # nothing but silence: not this function's problem to solve
    return leading * frame_size / sample_rate, trailing * frame_size / sample_rate


def _internal_silence_runs(
    audio: np.ndarray,
    sample_rate: int,
) -> list[tuple[int, int]]:
    """(start_frame, end_frame) of every silent run that is not at either edge.

    Same floor as the edge measure and the chapter check, so all three agree on what silence
    is. Runs touching either end are excluded: those belong to `_edge_silence_seconds`, which
    caps them differently and for a different reason.
    """
    frame_size = max(1, int(round(sample_rate * CHAPTER_SILENCE_FRAME_SECONDS)))
    frame_count = audio.size // frame_size
    if frame_count <= 0:
        return []
    frames = audio[: frame_count * frame_size].astype(np.float64).reshape(
        frame_count, frame_size
    )
    rms = np.sqrt(np.mean(np.square(frames), axis=1))
    silent = rms <= 10 ** (CHAPTER_SILENCE_FLOOR_DBFS / 20.0)
    runs: list[tuple[int, int]] = []
    start: int | None = None
    for index, value in enumerate(silent):
        if value and start is None:
            start = index
        elif not value and start is not None:
            runs.append((start, index))
            start = None
    if start is not None:
        runs.append((start, len(silent)))
    return [run for run in runs if run[0] > 0 and run[1] < frame_count]


def _cap_internal_silence(
    audio: np.ndarray,
    sample_rate: int,
) -> tuple[np.ndarray, float]:
    """Shorten every over-long pause inside a take. Returns (audio, seconds removed).

    The pause is shortened, never removed: what is left is still the longest pause this book
    performs on purpose. A voice that stops for a second and a quarter mid-paragraph is not
    doing prosody, and the reader hears a dropout - but the sentence break itself is real and
    has to survive.
    """
    frame_size = max(1, int(round(sample_rate * CHAPTER_SILENCE_FRAME_SECONDS)))
    keep_frames = int(round(SEGMENT_INTERNAL_SILENCE_CAP_SECONDS / CHAPTER_SILENCE_FRAME_SECONDS))
    drop: list[tuple[int, int]] = []
    for start, end in _internal_silence_runs(audio, sample_rate):
        if end - start <= keep_frames:
            continue
        drop.append(((start + keep_frames) * frame_size, end * frame_size))
    if not drop:
        return audio, 0.0
    kept: list[np.ndarray] = []
    cursor = 0
    removed = 0
    for start, end in drop:
        kept.append(audio[cursor:start])
        removed += end - start
        cursor = end
    kept.append(audio[cursor:])
    return np.concatenate(kept), removed / sample_rate


def _cap_segment_edge_silence(
    entries: list[tuple[Path, int]],
    sample_rate: int,
    work_dir: Path,
) -> tuple[list[tuple[Path, int]], list[dict[str, Any]]]:
    """Substitute a trimmed copy for any take that opens or closes on too much dead air.

    The take on disk is never touched. It is the artifact every QA stage ruled on, its
    checksum is the key half the evidence in this project is filed under, and the silence is
    not a reason to re-judge the reading. What changes is only how much of that silence the
    assembler carries into the chapter.
    """
    capped: list[tuple[Path, int]] = []
    trimmed: list[dict[str, Any]] = []
    for index, (path, break_ms) in enumerate(entries):
        try:
            audio, rate = sf.read(path, dtype="float32", always_2d=False)
        except Exception as exc:  # noqa: BLE001
            raise AudioQualityError(f"cannot read WAV: {path}: {exc}") from exc
        samples = np.asarray(audio)
        leading, trailing = _edge_silence_seconds(samples, rate)
        start = int(round(max(0.0, leading - SEGMENT_EDGE_SILENCE_CAP_SECONDS) * rate))
        end = len(samples) - int(
            round(max(0.0, trailing - SEGMENT_EDGE_SILENCE_CAP_SECONDS) * rate)
        )
        edged = samples[start:end]
        removed_edges = (len(samples) - len(edged)) / rate
        # And the pauses inside it. A take can be perfectly framed and still stop dead in the
        # middle of a sentence, which is what chapter 10 of alpha.53 did after "công bằng" -
        # the single longest silence in 10,869 across the whole book, and the one the owner
        # picked out by ear.
        inner, removed_inner = _cap_internal_silence(edged, rate)
        if removed_edges <= 0.0 and removed_inner <= 0.0:
            capped.append((path, break_ms))
            continue
        work_dir.mkdir(parents=True, exist_ok=True)
        target = work_dir / f"trimmed_{index:05d}_{path.stem}.wav"
        sf.write(target, inner, rate, subtype="PCM_16")
        capped.append((target, break_ms))
        trimmed.append(
            {
                "source": str(path),
                "leading_silence_seconds": round(leading, 3),
                "trailing_silence_seconds": round(trailing, 3),
                "internal_removed_seconds": round(removed_inner, 3),
                "removed_seconds": round(removed_edges + removed_inner, 3),
            }
        )
    return capped, trimmed


def _max_join_jump(audio: np.ndarray, sample_rate: int, join_times: list[float]) -> float:
    if audio.size < 2 or not join_times:
        return 0.0
    differences = np.abs(np.diff(audio.astype(np.float64)))
    radius = max(1, int(round(sample_rate * CHAPTER_JOIN_WINDOW_SECONDS)))
    maximum = 0.0
    for join_time in join_times:
        center = int(round(join_time * sample_rate)) - 1
        start = max(0, center - radius)
        end = min(differences.size, center + radius + 1)
        if end > start:
            maximum = max(maximum, float(np.max(differences[start:end])))
    return maximum


def _evaluate_chapter_quality(
    decoded: np.ndarray,
    sample_rate: int,
    channels: int,
    expected_duration: float,
    expected_breaks: list[tuple[float, float]],
    join_times: list[float],
    audio_cfg: dict[str, Any],
    mastering_input: dict[str, float],
    mastered_output: dict[str, float],
) -> ChapterQualityMetrics:
    mono = decoded[:, 0] if channels == 1 else np.mean(decoded, axis=1)
    raw_metrics = signal_metrics(mono, sample_rate)
    duration = raw_metrics["duration"]
    duration_error = duration - expected_duration
    dc_offset = float(np.mean(mono.astype(np.float64)))
    flat_top_fraction, longest_flat_top = _flat_top_metrics(mono, sample_rate)
    leading_silence, trailing_silence, unexpected_silence = _silence_metrics(
        mono,
        sample_rate,
        expected_breaks,
    )
    join_jump = _max_join_jump(mono, sample_rate, join_times)
    join_jump_dbfs = 20.0 * math.log10(join_jump) if join_jump > 0 else None
    target_lufs = float(audio_cfg["loudness_lufs"])
    target_peak = float(audio_cfg["true_peak_db"])
    output_lufs = mastered_output["input_i"]
    output_peak = mastered_output["input_tp"]
    loudness_delta = abs(output_lufs - target_lufs)

    hard_failures: list[str] = []
    if channels != 1:
        hard_failures.append(f"channels={channels}, expected mono")
    expected_sample_rate = int(audio_cfg["_expected_sample_rate"])
    if sample_rate != expected_sample_rate:
        hard_failures.append(f"sample_rate={sample_rate}, expected {expected_sample_rate}")
    if abs(duration_error) > CHAPTER_DURATION_HARD_TOLERANCE_SECONDS:
        hard_failures.append(f"duration error {duration_error:+.3f}s")
    if raw_metrics["rms"] < CHAPTER_MIN_RMS:
        hard_failures.append(f"RMS too low: {raw_metrics['rms']:.6f}")
    if loudness_delta > CHAPTER_LOUDNESS_HARD_TOLERANCE_LU:
        hard_failures.append(f"integrated loudness off target by {loudness_delta:.2f} LU")
    if output_peak > target_peak + CHAPTER_TRUE_PEAK_HARD_MARGIN_DB:
        hard_failures.append(f"true peak too high: {output_peak:.2f} dBTP")
    if raw_metrics["clipping_fraction"] > CHAPTER_CLIPPING_HARD_FRACTION:
        hard_failures.append(f"clipping fraction {raw_metrics['clipping_fraction']:.4%}")
    if abs(dc_offset) > CHAPTER_DC_OFFSET_HARD:
        hard_failures.append(f"DC offset too high: {dc_offset:+.4f}")
    if longest_flat_top > CHAPTER_FLAT_TOP_HARD_SECONDS:
        hard_failures.append(f"flat top lasts {longest_flat_top:.3f}s")
    if unexpected_silence > CHAPTER_DROPOUT_HARD_SECONDS:
        hard_failures.append(f"unexpected silence lasts {unexpected_silence:.2f}s")
    if join_jump > CHAPTER_JOIN_JUMP_HARD:
        hard_failures.append(f"join discontinuity {join_jump:.3f}")

    review_flags: list[str] = []
    if loudness_delta > CHAPTER_LOUDNESS_REVIEW_TOLERANCE_LU:
        review_flags.append(f"loudness delta {loudness_delta:.2f} LU")
    if output_peak > target_peak + CHAPTER_TRUE_PEAK_REVIEW_MARGIN_DB:
        review_flags.append(f"true peak margin {output_peak - target_peak:+.2f} dB")
    if 0 < raw_metrics["clipping_fraction"] <= CHAPTER_CLIPPING_HARD_FRACTION:
        review_flags.append(f"nonzero clipping fraction {raw_metrics['clipping_fraction']:.4%}")
    if abs(dc_offset) > CHAPTER_DC_OFFSET_REVIEW:
        review_flags.append(f"DC offset {dc_offset:+.4f}")
    if longest_flat_top > CHAPTER_FLAT_TOP_REVIEW_SECONDS:
        review_flags.append(f"flat top {longest_flat_top:.3f}s")
    if unexpected_silence > CHAPTER_DROPOUT_REVIEW_SECONDS:
        review_flags.append(f"unexpected silence {unexpected_silence:.2f}s")
    if leading_silence > CHAPTER_EDGE_SILENCE_REVIEW_SECONDS:
        review_flags.append(f"leading silence {leading_silence:.2f}s")
    if trailing_silence > CHAPTER_EDGE_SILENCE_REVIEW_SECONDS:
        review_flags.append(f"trailing silence {trailing_silence:.2f}s")
    if join_jump > CHAPTER_JOIN_JUMP_REVIEW:
        review_flags.append(f"join discontinuity {join_jump:.3f}")

    return ChapterQualityMetrics(
        expected_duration_seconds=float(expected_duration),
        decoded_duration_seconds=float(duration),
        duration_error_seconds=float(duration_error),
        sample_rate=sample_rate,
        channels=channels,
        mastering_input_lufs=float(mastering_input["input_i"]),
        mastering_input_true_peak_db=float(mastering_input["input_tp"]),
        integrated_loudness_lufs=float(output_lufs),
        true_peak_db=float(output_peak),
        loudness_range_lu=float(mastered_output["input_lra"]),
        rms=float(raw_metrics["rms"]),
        peak=float(raw_metrics["peak"]),
        clipping_fraction=float(raw_metrics["clipping_fraction"]),
        dc_offset=dc_offset,
        flat_top_fraction=flat_top_fraction,
        longest_flat_top_seconds=longest_flat_top,
        leading_silence_seconds=leading_silence,
        trailing_silence_seconds=trailing_silence,
        longest_unexpected_silence_seconds=unexpected_silence,
        max_join_jump=join_jump,
        max_join_jump_dbfs=join_jump_dbfs,
        hard_failures=tuple(hard_failures),
        review_flags=tuple(review_flags),
    )


def assemble_chapter_atomic_with_metrics(
    wavs: Iterable[Path | tuple[Path, int]],
    output: Path,
    settings: dict[str, Any],
    *,
    title: str,
    book_title: str,
    track: int,
    work_dir: Path | None = None,
) -> ChapterAssemblyResult:
    entries: list[tuple[Path, int]] = []
    for item in wavs:
        if isinstance(item, tuple):
            path, break_ms = item
            entries.append((Path(path), max(0, int(break_ms))))
        else:
            entries.append((Path(item), 0))
    if not entries:
        raise AudioQualityError("chapter has no WAV files")
    for path, _ in entries:
        if not path.exists():
            raise AudioQualityError(f"missing WAV: {path}")

    output.parent.mkdir(parents=True, exist_ok=True)
    concat = output.with_suffix(".concat.part.txt")
    temp = output.with_name(output.stem + ".part" + output.suffix)
    decoded_temp = output.with_name(output.stem + ".qa.part.wav")
    sample_rate = int(settings["tts"]["sample_rate"])
    silence_dir = work_dir or output.parent / ".silence_cache"
    # Cap dead air at the take's edges before the timeline is measured, so the expected
    # duration and the break ranges describe what is actually going into the chapter.
    entries, trimmed_edges = _cap_segment_edge_silence(entries, sample_rate, silence_dir)
    expected_duration, expected_breaks, join_times = _source_timeline(entries, sample_rate)
    temp.unlink(missing_ok=True)
    decoded_temp.unlink(missing_ok=True)
    candidate_checksum: str | None = None
    audio = settings["audio"]
    ffmpeg = ffmpeg_executable()
    concat_input = ["-f", "concat", "-safe", "0", "-i", str(concat)]
    try:
        concat_paths: list[Path] = []
        for index, (path, break_ms) in enumerate(entries):
            concat_paths.append(path)
            if index + 1 < len(entries) and break_ms > 0:
                concat_paths.append(_silence_file(silence_dir, break_ms, sample_rate))
        atomic_write_text(concat, "\n".join(_concat_line(path) for path in concat_paths) + "\n")

        mastering_input = _measure_loudness(concat_input, audio)
        command = [
            ffmpeg,
            "-hide_banner",
            "-nostats",
            "-loglevel",
            "error",
            "-nostdin",
            "-y",
            *concat_input,
            "-map",
            "0:a:0",
            "-af",
            _second_pass_loudnorm_filter(audio, mastering_input),
            "-ar",
            str(sample_rate),
            "-ac",
            "1",
            "-codec:a",
            "libmp3lame",
            "-b:a",
            str(audio["mp3_bitrate"]),
            "-threads",
            "1",
            "-fflags",
            "+bitexact",
            "-flags:a",
            "+bitexact",
            "-map_metadata",
            "-1",
            "-id3v2_version",
            "3",
            "-write_id3v1",
            "0",
            "-metadata",
            f"album={book_title}",
            "-metadata",
            f"title={title}",
            "-metadata",
            f"track={track}",
            str(temp),
        ]
        result = run_hidden(command, timeout=7200, check=False)
        if result.returncode != 0:
            raise AudioQualityError(f"FFmpeg chapter assembly failed: {result.stderr[-3000:]}")
        if not temp.exists() or temp.stat().st_size < 4096:
            raise AudioQualityError("FFmpeg chapter assembly produced a missing or undersized MP3")
        candidate_checksum = sha256_file(temp)
        mastered_output = _measure_loudness(["-i", str(temp)], audio, timeout=3600)
        decoded, decoded_sample_rate, channels = _decode_mp3_candidate(temp, decoded_temp)
        quality_audio_cfg = {**audio, "_expected_sample_rate": sample_rate}
        quality = _evaluate_chapter_quality(
            decoded,
            decoded_sample_rate,
            channels,
            expected_duration,
            expected_breaks,
            join_times,
            quality_audio_cfg,
            mastering_input,
            mastered_output,
        )
        if quality.hard_failures:
            raise ChapterQualityError(
                "temporary MP3 failed chapter QA: " + "; ".join(quality.hard_failures),
                artifact_sha256=candidate_checksum,
                metrics=quality.to_dict(),
                failure_codes=("CHAPTER_QA_HARD_FAILURE",),
            )
        if trimmed_edges:
            # Attached before the review check, not after it. A chapter that fails is the one
            # somebody has to diagnose, and leaving this out of its metrics says the edges
            # were never trimmed when they were - which is exactly the wrong turn it caused
            # on alpha.53 chapter 10, where the real cause was silence *inside* a take and
            # the empty list pointed at the edge cap instead.
            quality = replace(
                quality,
                trimmed_segment_edges=tuple(
                    f"{Path(item['source']).name}: đầu {item['leading_silence_seconds']}s "
                    f"cuối {item['trailing_silence_seconds']}s, cắt bớt "
                    f"{item['removed_seconds']}s"
                    for item in trimmed_edges
                ),
            )
        blocking_review_flags = chapter_review_flags_that_block(quality.review_flags)
        if settings.get("quality_profile") == "high_quality" and blocking_review_flags:
            raise ChapterQualityError(
                "temporary MP3 requires review under high-quality policy: "
                + "; ".join(blocking_review_flags),
                artifact_sha256=candidate_checksum,
                metrics=quality.to_dict(),
                failure_codes=("CHAPTER_QA_REVIEW_REQUIRED",),
                review_required=True,
            )
        with temp.open("rb+") as handle:
            os.fsync(handle.fileno())
        os.replace(temp, output)
        return ChapterAssemblyResult(checksum=candidate_checksum, quality=quality)
    except ChapterQualityError:
        raise
    except AudioQualityError as exc:
        raise ChapterQualityError(
            str(exc),
            artifact_sha256=candidate_checksum,
            metrics={"assembly_error": str(exc)},
            failure_codes=("CHAPTER_ASSEMBLY_FAILED",),
        ) from exc
    finally:
        concat.unlink(missing_ok=True)
        decoded_temp.unlink(missing_ok=True)
        if temp.exists() and temp != output:
            temp.unlink(missing_ok=True)


def assemble_chapter_atomic(
    wavs: Iterable[Path | tuple[Path, int]],
    output: Path,
    settings: dict[str, Any],
    *,
    title: str,
    book_title: str,
    track: int,
    work_dir: Path | None = None,
) -> str:
    """Backward-compatible checksum-only wrapper for the pipeline currently in production."""
    result = assemble_chapter_atomic_with_metrics(
        wavs,
        output,
        settings,
        title=title,
        book_title=book_title,
        track=track,
        work_dir=work_dir,
    )
    return result.checksum


def write_playlist_atomic(chapter_files: list[Path], output: Path) -> None:
    rows = ["#EXTM3U"] + [f"chapters/{path.name}" for path in chapter_files]
    atomic_write_text(output, "\n".join(rows) + "\n")


def export_json_atomic(path: Path, payload: Any) -> None:
    from .io_utils import atomic_write_json

    atomic_write_json(path, payload)
