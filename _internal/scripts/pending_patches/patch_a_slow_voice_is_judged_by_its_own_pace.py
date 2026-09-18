"""Vá voice_catalog.py + audio_io.py + tts.py + pipeline.py: cổng nhịp đo một giọng chậm theo nhịp của chính nó.

Chạy: python patch_a_slow_voice_is_judged_by_its_own_pace.py <root>

**XẾP Ở RANH GIỚI 6, SAU `patch_a_slow_voice_reads_at_its_own_speed.py`** (neo vào hàm và hằng số
bản ấy thêm). Như bản ấy, bản này chỉ thêm CƠ CHẾ: `PRESET_PACE_SCALE` để rỗng, mọi giọng hệ số 1,0
và cổng y như trước. Con số do bản vá thêm giọng điền.

## Vì sao (18-09)

Chủ sách nghe từng nấc tốc độ của bốn giọng kể chuyện và chọn bằng tai: Đức Trí ×1,10, Thiền Tâm
Đức ×1,05, Kim Thanh ×1,10, Mỹ Duyên giữ nguyên. Ở đúng các nấc ấy, cổng nhịp của app vẫn gọi 8, 9,
13 và 8 trên 25 câu thử là "đọc chậm". Trong `high_quality` mỗi lời kết tội ấy là một lần thu lại,
rồi nới băng, rồi hỏng - cho những câu chủ sách đã nghe và nhận.

Cổng không sai về số đo mà sai về **thước**: băng 12,5..24,5 kt/s là phân vị 2 của những gì 7 giọng
đang chạy tạo ra (config.py), tức một băng khớp cho giọng đọc ở nhịp ~1,0 lần trung vị ấy. Đo trên
cùng 25 câu bằng chính `validate_audio_array` (scratchpad `voice_pace_calibration.py`): mốc 7 giọng
15,64 kt/s, 4,73 âm tiết/s; 7 giọng ấy nằm trong 0,94..1,16 lần mốc. Bốn giọng kể chuyện ở nấc chủ
sách chọn: Đức Trí 0,807, Thiền Tâm Đức 0,788, Kim Thanh 0,770, Mỹ Duyên 0,810 - nhịp tự nhiên của
chúng thấp hơn cả băng.

Nên mỗi giọng có một hệ số nhịp, và cổng nhân **sàn** (chữ lẫn âm tiết) với hệ số ấy: một câu bị
gọi chậm khi nó chậm so với chính giọng đọc nó, ở cùng phân vị như mọi giọng khác. Một chiều, như
mọi lần sửa cổng trước: hệ số ≤ 1, chỉ bớt lời kết tội "chậm". Cận trên và cận cứng
(`RATE_HARD_MIN_FACTOR`) giữ nguyên - cận cứng quyết định bản thu có HỢP LỆ không, và
`recovery.py` xét nó trên hàng không mang tên giọng; hai chỗ phải ra cùng một câu trả lời.

## Ngân sách sinh tiếng

`segment_duration_policy` cấp khung sinh theo cùng sàn ấy: `chữ / sàn + 2 giây`. Giọng chậm sinh
bản thô còn chậm hơn nữa - tốc độ được tăng SAU khi sinh - nên Đức Trí thô (11,39 kt/s ở câu thử)
chạm trần ngân sách ở câu dài và bị cắt cụt. Sàn của ngân sách vì thế nhân `hệ số nhịp / hệ số tốc
độ`, tức nhịp THÔ của giọng. Vẫn kẹp dưới trần `safe_frames` như cũ, nên không vượt giới hạn thẩm
định.

## Mọi chỗ soi một bản thu phải biết giọng

Hàng đoạn chỉ mang `voice_profile_id`. `synthesize_atomic` ghi tên preset vào `spoken_row` trước khi
tính ngân sách và trước khi cổng chạy. Bốn chỗ `inspect_wav` của pipeline (mở lại bản thu cũ, cứu
nhịp, hai đường tách câu) đi qua `_segment_for_audio_check`: không thế thì một bản thu được nhận lúc
tổng hợp sẽ bị gọi lệch nhịp lần sau worker mở lại nó, và `_recheckpoint_segment_for_current_audio_qa`
ghi lời kết tội ấy vào sổ.
"""
import io
import sys
from pathlib import Path

root = Path(sys.argv[1])


def replace_once(path: Path, old: str, new: str) -> None:
    text = io.open(path, encoding="utf-8").read()
    assert text.count(old) == 1, f"{path.name}: khong khop mot lan duy nhat: {old.splitlines()[0]!r}"
    io.open(path, "w", encoding="utf-8").write(text.replace(old, new, 1))


def replace_exactly(path: Path, old: str, new: str, count: int) -> None:
    text = io.open(path, encoding="utf-8").read()
    assert text.count(old) == count, f"{path.name}: can {count} cho, thay {text.count(old)}: {old.splitlines()[0]!r}"
    io.open(path, "w", encoding="utf-8").write(text.replace(old, new))


# ------------------------------------------------------------------ voice_catalog.py
catalog = root / "ebook_reader" / "voice_catalog.py"
replace_once(catalog, '''PRESET_SPEED_FACTOR: dict[str, float] = {}
SPEED_FACTOR_MIN = 0.80
SPEED_FACTOR_MAX = 1.50
''', '''PRESET_SPEED_FACTOR: dict[str, float] = {}
SPEED_FACTOR_MIN = 0.80
SPEED_FACTOR_MAX = 1.50
# How fast this preset reads at its calibrated speed, relative to the voices the pace band was
# fitted on (the median of the seven presets in use on book 2, measured on the same 25 test
# lines with the pipeline's own gate). The pace gate multiplies its FLOOR - characters and
# syllables - by this, so a storytelling voice is called slow when it is slow for itself, at
# the same percentile as every other voice. One-directional: at most 1.0, and the ceiling and
# the hard bounds do not move. Measured 2026-09-18 after the owner chose each speed by ear.
PRESET_PACE_SCALE: dict[str, float] = {}
PACE_SCALE_MIN = 0.65
PACE_SCALE_MAX = 1.0
''')
replace_once(catalog, '''def speed_factor_for_preset(preset_name: str) -> float:
    """The calibrated reading speed for this preset; 1.0 when none was set."""
    return float(PRESET_SPEED_FACTOR.get(str(preset_name), 1.0))
''', '''def speed_factor_for_preset(preset_name: str) -> float:
    """The calibrated reading speed for this preset; 1.0 when none was set."""
    return float(PRESET_SPEED_FACTOR.get(str(preset_name), 1.0))


def pace_scale_for_preset(preset_name: str) -> float:
    """This preset's own tempo as a fraction of the pace band's; 1.0 when none was measured."""
    return float(PRESET_PACE_SCALE.get(str(preset_name), 1.0))
''')

# ------------------------------------------------------------------ audio_io.py
audio = root / "ebook_reader" / "audio_io.py"
replace_once(audio, '''from .text_processing import VIETNAMESE_UNITS, vietnamese_number_words
''', '''from .text_processing import VIETNAMESE_UNITS, vietnamese_number_words
from .voice_catalog import pace_scale_for_preset, speed_factor_for_preset
''')
replace_once(audio, '''DEFAULT_PACE_LOWER_BOUNDS = {"slow": 6.0, "normal": 10.5, "fast": 12.0}
''', '''DEFAULT_PACE_LOWER_BOUNDS = {"slow": 6.0, "normal": 10.5, "fast": 12.0}
# Tên preset đọc đoạn này, ghi vào hàng đoạn trước khi soi bản thu (`synthesize_atomic`,
# `Pipeline._segment_for_audio_check`). Hàng trong DB chỉ mang `voice_profile_id`; vắng trường này
# thì hệ số nhịp là 1,0 và cổng y như trước.
VOICE_PRESET_FIELD = "voice_preset"


def _voice_preset(segment: Any) -> str:
    """Tên preset trong hàng đoạn, rỗng khi hàng không mang nó.

    Không dùng `_segment_value`: hàng `sqlite3.Row` báo thiếu cột bằng `IndexError`, không phải
    `KeyError`, và mọi hàng đi thẳng từ DB (ghép chương, recovery) đều thiếu cột này. Bản thử đầu
    dùng `_segment_value` và làm mọi lần soi trên hàng DB ném lỗi - chương không xuất được MP3.
    """
    if segment is None:
        return ""
    try:
        value = segment[VOICE_PRESET_FIELD]
    except (IndexError, KeyError, TypeError):
        return ""
    return str(value or "")
''')
replace_once(audio, '''    configured = configured_bounds.get(pace, DEFAULT_PACE_LOWER_BOUNDS.get(pace, 10.5))
    lower_bound = float(configured[0] if isinstance(configured, (list, tuple)) else configured)
''', '''    configured = configured_bounds.get(pace, DEFAULT_PACE_LOWER_BOUNDS.get(pace, 10.5))
    lower_bound = float(configured[0] if isinstance(configured, (list, tuple)) else configured)
    # Sàn của NHỊP THÔ: một giọng chậm (`PRESET_PACE_SCALE`) sinh bản thu chậm hơn băng, và tốc
    # độ của nó (`PRESET_SPEED_FACTOR`) chỉ được tăng SAU khi sinh. Cấp khung theo sàn chung thì
    # câu dài của Đức Trí (11,39 kt/s thô) chạm trần và bị cắt cụt.
    preset = _voice_preset(segment)
    if preset:
        lower_bound *= pace_scale_for_preset(preset) / speed_factor_for_preset(preset)
''')
replace_once(audio, '''    fast_rate: float | None = None,
) -> bool:
    """Chậm chỉ khi chậm theo CẢ chữ lẫn âm tiết; nhanh vẫn xét theo chữ như cũ.
''', '''    fast_rate: float | None = None,
    *,
    floor_scale: float = 1.0,
) -> bool:
    """Chậm chỉ khi chậm theo CẢ chữ lẫn âm tiết; nhanh vẫn xét theo chữ như cũ.

    `floor_scale` là nhịp riêng của giọng (`PRESET_PACE_SCALE`): cả hai sàn nhân với nó, cận trên
    thì không. Mặc định 1,0 - mọi chỗ gọi cũ ra đúng câu trả lời cũ.
''')
replace_once(audio, '''    lower_bound = float(bounds[0])
    upper_bound = float(bounds[1])
    syllable_floor = PACE_SYLLABLES_PER_SECOND_FLOOR.get(
        pace, PACE_SYLLABLES_PER_SECOND_FLOOR["normal"]
    )
    too_slow = rate < lower_bound and syllable_rate < syllable_floor
''', '''    lower_bound = float(bounds[0]) * float(floor_scale)
    upper_bound = float(bounds[1])
    syllable_floor = PACE_SYLLABLES_PER_SECOND_FLOOR.get(
        pace, PACE_SYLLABLES_PER_SECOND_FLOOR["normal"]
    ) * float(floor_scale)
    too_slow = rate < lower_bound and syllable_rate < syllable_floor
''')
replace_once(audio, '''        metrics["pace_outlier"] = float(
            pace_is_outlier(rate, syllable_rate, pace, bounds, fast_rate=heard_rate)
        )
''', '''        pace_scale = pace_scale_for_preset(_voice_preset(segment))
        if pace_scale != 1.0:
            metrics["pace_scale"] = float(pace_scale)
        metrics["pace_outlier"] = float(
            pace_is_outlier(
                rate,
                syllable_rate,
                pace,
                bounds,
                fast_rate=heard_rate,
                floor_scale=pace_scale,
            )
        )
''')

# ------------------------------------------------------------------ tts.py
tts = root / "ebook_reader" / "tts.py"
replace_once(tts, '''from .audio_io import (
''', '''from .audio_io import (
    VOICE_PRESET_FIELD,
''')
replace_once(tts, '''            spoken_row = self._spoken_row(
                row,
                pronunciation_delivery_variant=normalized_pronunciation_variant,
            )
''', '''            spoken_row = self._spoken_row(
                row,
                pronunciation_delivery_variant=normalized_pronunciation_variant,
            )
            # Trước ngân sách sinh và trước cổng: cả hai đo một giọng chậm theo nhịp của nó.
            spoken_row[VOICE_PRESET_FIELD] = str(_row_value(profile, "preset_name", "") or "")
''')

# ------------------------------------------------------------------ pipeline.py
pipeline = root / "ebook_reader" / "pipeline.py"
replace_once(pipeline, '''from .audio_io import (
''', '''from .audio_io import (
    VOICE_PRESET_FIELD,
''')
replace_once(pipeline, '''    def _inspect_existing_segment(self, row: Any) -> tuple[bool, dict[str, float]]:
''', '''    def _segment_for_audio_check(self, row: Any) -> Any:
        """Hàng đoạn cộng tên preset đọc nó - cho cổng nhịp (`PRESET_PACE_SCALE`).

        `synthesize_atomic` ghi đúng trường này trước lần soi của nó; mọi lần soi SAU phải dùng
        cùng một băng, không thì bản thu được nhận lúc tổng hợp bị gọi lệch nhịp lần sau worker
        mở lại nó. Không tra được giọng thì trả hàng nguyên vẹn: hệ số 1,0, băng cũ.
        """
        try:
            if str(row["kind"] or "narration") == "thought":
                profile = self.db.voice_profile_by_key("narrator")
            else:
                profile = self.db.voice_profile(int(row["voice_profile_id"]))
            preset = str(profile["preset_name"] or "")
        except (AttributeError, IndexError, KeyError, TypeError, ValueError):
            return row
        segment = dict(row)
        segment[VOICE_PRESET_FIELD] = preset
        return segment

    def _inspect_existing_segment(self, row: Any) -> tuple[bool, dict[str, float]]:
''')
replace_once(pipeline, '''        valid, metrics, _ = inspect_wav(
            wav,
            expected_text,
            self.settings,
            segment=row,
        )
''', '''        valid, metrics, _ = inspect_wav(
            wav,
            expected_text,
            self.settings,
            segment=self._segment_for_audio_check(row),
        )
''')
replace_once(pipeline, '''            valid, metrics, reason = inspect_wav(
                output,
                spoken_text,
                self.settings,
                segment=row,
            )
''', '''            valid, metrics, reason = inspect_wav(
                output,
                spoken_text,
                self.settings,
                segment=self._segment_for_audio_check(row),
            )
''')
replace_exactly(pipeline, '''                valid, metrics, reason = inspect_wav(
                    output,
                    spoken_text,
                    self.settings,
                    segment=row,
                )
''', '''                valid, metrics, reason = inspect_wav(
                    output,
                    spoken_text,
                    self.settings,
                    segment=self._segment_for_audio_check(row),
                )
''', 2)

# ------------------------------------------------------------------ test
test = root / "tests" / "test_a_slow_voice_is_judged_by_its_own_pace.py"
test.write_text('''"""Cổng nhịp đo một giọng chậm theo nhịp của chính nó - và chỉ sàn, chỉ một chiều."""
from __future__ import annotations

import inspect
import re

import numpy as np
import pytest

from ebook_reader import audio_io, pipeline, tts, voice_catalog
from ebook_reader.audio_io import (
    VOICE_PRESET_FIELD,
    pace_is_outlier,
    segment_duration_policy,
    spoken_speakable_chars,
    validate_audio_array,
)
from ebook_reader.config import build_settings
from ebook_reader.voice_catalog import (
    PACE_SCALE_MAX,
    PACE_SCALE_MIN,
    PRESET_PACE_SCALE,
    VIENEU_PRESETS,
    pace_scale_for_preset,
)

NORMAL = (12.5, 24.5)
RATE = 48_000
SLOW_VOICE = "Giọng Kể Chậm"
# Không dấu câu nên không có ngân sách nghỉ: nhịp = ký tự đọc được / thời lượng.
LINE = "Người kể chuyện đọc thật chậm rãi từng chữ một trong đêm dài"


def _tone(seconds: float) -> np.ndarray:
    count = int(round(RATE * seconds))
    return (0.3 * np.sin(np.linspace(0.0, 2 * np.pi * 180 * seconds, count))).astype(np.float32)


def test_the_floor_moves_with_the_voice() -> None:
    # 11 kt/s, 3,3 âm tiết/s: chậm theo băng chung, bình thường với một giọng 0,81.
    assert pace_is_outlier(11.0, 3.3, "normal", NORMAL)
    assert not pace_is_outlier(11.0, 3.3, "normal", NORMAL, floor_scale=0.81)


def test_the_ceiling_does_not() -> None:
    assert pace_is_outlier(26.0, 7.0, "normal", NORMAL, floor_scale=0.81)
    assert not pace_is_outlier(20.0, 6.0, "normal", NORMAL, floor_scale=0.81)


def test_a_voice_nobody_measured_keeps_the_shared_band() -> None:
    assert pace_scale_for_preset("a preset nobody measured") == 1.0
    assert pace_scale_for_preset("") == 1.0


def test_every_catalogued_scale_only_loosens_and_names_a_real_preset() -> None:
    names = {preset["name"] for preset in VIENEU_PRESETS}
    for name, scale in PRESET_PACE_SCALE.items():
        assert name in names, name
        assert PACE_SCALE_MIN <= scale <= PACE_SCALE_MAX, name


def test_the_gate_reads_the_voice_from_the_segment(monkeypatch) -> None:
    monkeypatch.setitem(PRESET_PACE_SCALE, SLOW_VOICE, 0.81)
    settings = build_settings("high_quality")
    audio = _tone(spoken_speakable_chars(LINE) / 11.0)
    plain = {"pace": "normal", "kind": "narration", "text": LINE}
    _, shared = validate_audio_array(audio, LINE, settings, RATE, plain)
    _, own = validate_audio_array(audio, LINE, settings, RATE, {**plain, VOICE_PRESET_FIELD: SLOW_VOICE})
    assert shared["chars_per_second"] == pytest.approx(11.0, rel=0.02)
    assert shared["pace_outlier"] == 1.0
    assert own["pace_outlier"] == 0.0
    assert own["pace_scale"] == 0.81
    assert "pace_scale" not in shared


def test_a_database_row_without_the_field_is_judged_by_the_shared_band() -> None:
    import sqlite3

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT 'normal' AS pace, 'narration' AS kind, ? AS text", (LINE,)).fetchone()
    settings = build_settings("high_quality")
    audio = _tone(spoken_speakable_chars(LINE) / 11.0)
    _, metrics = validate_audio_array(audio, LINE, settings, RATE, row)
    assert metrics["pace_outlier"] == 1.0
    segment_duration_policy(LINE, settings, row)


def test_a_slow_voice_gets_the_frames_its_raw_take_needs(monkeypatch) -> None:
    monkeypatch.setitem(PRESET_PACE_SCALE, SLOW_VOICE, 0.81)
    monkeypatch.setitem(voice_catalog.PRESET_SPEED_FACTOR, SLOW_VOICE, 1.10)
    settings = build_settings("high_quality")
    text = LINE + " " + LINE
    plain = {"pace": "normal", "kind": "narration", "text": text}
    shared = segment_duration_policy(text, settings, plain).generation_max_frames
    own = segment_duration_policy(text, settings, {**plain, VOICE_PRESET_FIELD: SLOW_VOICE})
    assert own.generation_max_frames > shared
    assert own.generation_ceiling_seconds < own.validation_max_seconds


def test_synthesis_names_the_voice_before_the_budget_and_the_gate() -> None:
    source = inspect.getsource(tts.TTSCoordinator.synthesize_atomic)
    named = source.index("spoken_row[VOICE_PRESET_FIELD]")
    assert named < source.index("vieneu_sampling_for_segment(")
    assert named < source.index("segment_duration_policy(")
    assert named < source.index("atomic_write_wav(")


def test_every_later_look_at_a_take_uses_the_same_band() -> None:
    source = inspect.getsource(pipeline)
    calls = re.findall(r"inspect_wav\\((.*?)\\n\\s*\\)", source, flags=re.S)
    assert calls, "khong tim thay loi goi inspect_wav nao"
    for call in calls:
        assert "segment=self._segment_for_audio_check(row)" in call, call
''', encoding="utf-8")
print("ok: PRESET_PACE_SCALE + san theo giong o cong nhip + ngan sach sinh + 4 cho soi + test")
