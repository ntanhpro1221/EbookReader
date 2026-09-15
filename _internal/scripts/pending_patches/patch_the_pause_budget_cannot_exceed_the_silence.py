"""Va audio_io.py: can TREN cua phep kiem nhip doc theo khoang lang CO THAT, khong theo doan.

Chay: python patch_the_pause_budget_cannot_exceed_the_silence.py <root>

## Cai gia da mat

Ba doan cua cuon 2 mat han ban thu vi bi ket toi "doc qua nhanh" khi khong he nhanh:

    chuong 082  "Toi khong biet 'xoay' dau, Felicia."     22 lan thu, do ra 29-32,50 kt/s
    chuong 131  "Cha... Cau 'neu' nhieu that day, Lucien."  11 lan thu, do ra 26,37 kt/s
    chuong 090  (cung hinh)

`validate_audio_array` khong chia so ky tu cho thoi luong, no tru truoc mot NGAN SACH NGHI roi
moi chia: `pause = min(PAUSE_GROUP_SECONDS x so nhom dau cau, thoi luong x MAX_PAUSE_FRACTION)`.
Ngan sach ay dung - no sinh ra de go toi cho cau doc dung dau cau bi goi la cham, va no cuu that
- nhung no la mot PHONG DOAN: 0,276 giay moi nhom dau cau, chinh chuan tren cau dai.

Phep thu GPU 08:30 ngay 15-09 cho thay phong doan ay sai hang o cau ngan. Bon dang van ban cua
cung mot cau (co/khong nhay, co/khong ngoac don long) cho **cung mot thoi luong toi hai chu so
thap phan**: giong doc KHONG nghi o dau ngoac. Voi cau thoai 2 giay, ngan sach cham tran
MAX_PAUSE_FRACTION va an 60% thoi luong; nhip bi thoi tu ~16 len 30,09 kt/s. Chu thich cua
MAX_PAUSE_FRACTION noi ngan sach cao nhat cham 58,5% "tren 3803 doan da chot" - nhung 3803 doan
ay la nhung doan SONG SOT; doan bi ngan sach an het chinh la doan khong con trong bang de dem.

Hai cach chua hien nhien da bi so lieu bac bo (`measure_pause_budget_vs_silence.py` giu phep do):
rut dau ngoac khoi mau dem lam 248 doan "dat -> ngoai bang" de cuu 3, vi ngan sach duoc chinh
chuan *cung voi* nhung dau ay.

## Sua the nao

Them mot thuoc thu hai - khoang lang DO DUOC tren chinh song am - va **chi dung no cho can TREN**:

    pause_nghe  = min(ngan sach, khoang lang do duoc)      <= ngan sach, luon luon
    nhip_nghe   = ky tu / (thoi luong - pause_nghe)        <= nhip cu, luon luon

    can DUOI (cham) : van xet bang nhip cu, y nguyen        -> khong the them mot loi ket toi nao
    can TREN (nhanh): xet bang nhip_nghe                    -> chi ket toi khi CA HAI thuoc dong y

Day dung la doanh nghia da co san trong file nay: `pace_is_outlier` ket toi "cham" chi khi ca chu
lan am tiet cung noi, va `spoken_speakable_chars` sinh ra vi "thuoc chu dem sai cai no nhan la
dem". Thay doi mot chieu: chi bot co, khong them co.

## So lieu

Cuu, do tren 12 ban thu THAT cua dung cau bi mat (`work/rushed_line_probe` cua lo02v_082, phep
thu GPU sang nay): ca 12 di tu NGOAI BANG (29,02-32,50 kt/s) ve dat (14,05-16,46 kt/s, giua dai
12,5-24,5). Khoang lang do duoc 0,39-0,53 giay o cho ngan sach doi 1,20-1,34 giay. Con so 32,50
trung khop tung chu so voi loi ghi trong database, nen phep tinh nay la phep tinh cua chinh may.

Giet: 0, theo dinh nghia - can duoi khong doi. Neu chan ngan sach o CA HAI can (ban dau toi
tinh lam vay) thi tren 3000 doan da chot co 274 doan bi cat ngan sach va **2 doan dat -> ngoai
bang** o can duoi (`“Chao, Felicia. Va... cau o day sao, Lucien!”` 13,78 -> 10,28). Hai doan ay
la ly do can duoi giu nguyen thuoc cu: ngan sach sinh ra de bao ve dung chung.

Nguong do **so voi DINH cua chinh ban thu**, khong phai dBFS tuyet doi: `atomic_write_wav` goi
`validate_audio_array` hai lan - truoc va sau khi can am luong - va phep do phai cho cung mot cau
tra loi ca hai lan, neu khong cung mot ban thu se dat o lan nay va truot o lan kia. Nhan mot he
so vao toan song am khong doi ti so rms/dinh.
"""
import io
import sys
from pathlib import Path

root = Path(sys.argv[1])
p = root / "ebook_reader" / "audio_io.py"
s = io.open(p, encoding="utf-8").read()

OLD_CONSTANTS = '''MAX_PAUSE_FRACTION = 0.60


def pause_group_count(text: str) -> int:'''
NEW_CONSTANTS = '''MAX_PAUSE_FRACTION = 0.60

# Đo khoảng lặng có thật để chặn ngân sách nghỉ ở cận TRÊN. Xem `measured_silence_seconds`.
PACE_SILENCE_FRAME_SECONDS = 0.010
# Ngưỡng so với ĐỈNH của chính bản thu, không phải dBFS tuyệt đối: `atomic_write_wav` gọi
# `validate_audio_array` hai lần, một lần trước khi cân âm lượng và một lần sau, và phép đo
# phải cho cùng một câu trả lời ở cả hai lần - nếu không, cùng một bản thu sẽ đạt ở lần này
# và trượt ở lần kia. Nhân một hệ số vào toàn sóng âm không đổi tỉ số rms/đỉnh.
#
# -35 dB dưới đỉnh: đo trên 3000 đoạn đã chốt, ngưỡng này cắt ngân sách của 274 đoạn còn -30
# cắt 140 và -40 cắt 389. Ba ngưỡng cho cùng một kết luận về những câu đang bị mất (khoảng
# lặng thật 0,39-0,53 giây ở chỗ ngân sách đòi 1,20-1,34), nên chọn cái ở giữa.
PACE_SILENCE_FLOOR_BELOW_PEAK_DB = -35.0
# Ngắn hơn thế không phải một lần nghỉ mà là một khe giữa hai âm trong cùng một từ.
PACE_SILENCE_MIN_GAP_SECONDS = 0.05


def measured_silence_seconds(audio: Any, sample_rate: int) -> float:
    """Số giây giọng đọc thật sự im trong bản thu này.

    Thước thứ hai của phép kiểm nhịp, cho riêng cận TRÊN. Ngân sách nghỉ theo dấu câu là một
    phỏng đoán chỉnh chuẩn trên câu dài; ở câu thoại ngắn nó chạm trần `MAX_PAUSE_FRACTION`,
    ăn 60% thời lượng và thổi nhịp từ ~16 lên ~30 kt/s. Ba đoạn của cuốn 2 mất hẳn bản thu vì
    thế (chương 082, 131, 090), sau 11-22 lần thử đều cho cùng một con số - không phải xui mà
    là số học.

    Tổng các quãng liên tiếp nằm dưới `PACE_SILENCE_FLOOR_BELOW_PEAK_DB` so với đỉnh và dài
    hơn `PACE_SILENCE_MIN_GAP_SECONDS`. Tính cả khoảng lặng ở hai đầu: chặn chỉ được phép nới
    tay, nên đo rộng là đo an toàn.
    """
    array = np.asarray(audio, dtype=np.float32)
    if array.ndim == 2 and 1 in array.shape:
        array = array.reshape(-1)
    if array.ndim != 1 or array.size == 0 or sample_rate <= 0:
        return 0.0
    peak = float(np.max(np.abs(array)))
    if peak <= 0.0:
        return float(array.size / sample_rate)
    hop = max(1, int(round(sample_rate * PACE_SILENCE_FRAME_SECONDS)))
    usable = array.size - array.size % hop
    if usable < hop:
        return 0.0
    frames = array[:usable].reshape(-1, hop).astype(np.float64)
    rms = np.sqrt(np.maximum((frames**2).mean(axis=1), 1e-20))
    quiet = 20.0 * np.log10(rms / peak) < PACE_SILENCE_FLOOR_BELOW_PEAK_DB
    if not bool(quiet.any()):
        return 0.0
    padded = np.concatenate(([False], quiet, [False]))
    edges = np.flatnonzero(padded[1:] != padded[:-1])
    runs = edges[1::2] - edges[0::2]
    frame_seconds = hop / sample_rate
    # So bằng SỐ KHUNG, không bằng giây: 5 x 0.01 không đúng bằng 0.05 trong số thực nhị phân,
    # và một quãng đúng bằng ngưỡng thì được tính hay không sẽ tùy vào lỗi làm tròn.
    min_frames = max(1, int(round(PACE_SILENCE_MIN_GAP_SECONDS / frame_seconds)))
    return float(runs[runs >= min_frames].sum() * frame_seconds)


def pause_group_count(text: str) -> int:'''
assert s.count(OLD_CONSTANTS) == 1, "khong khop MAX_PAUSE_FRACTION / pause_group_count"
s = s.replace(OLD_CONSTANTS, NEW_CONSTANTS, 1)

OLD_OUTLIER_SIGNATURE = '''def pace_is_outlier(
    rate: float,
    syllable_rate: float,
    pace: str,
    bounds: "tuple[float, float] | list[float]",
) -> bool:'''
NEW_OUTLIER_SIGNATURE = '''def pace_is_outlier(
    rate: float,
    syllable_rate: float,
    pace: str,
    bounds: "tuple[float, float] | list[float]",
    fast_rate: float | None = None,
) -> bool:'''
assert s.count(OLD_OUTLIER_SIGNATURE) == 1, "khong khop chu ky pace_is_outlier"
s = s.replace(OLD_OUTLIER_SIGNATURE, NEW_OUTLIER_SIGNATURE, 1)

OLD_OUTLIER_BODY = '''    too_slow = rate < lower_bound and syllable_rate < syllable_floor
    return bool(too_slow or rate > upper_bound)'''
NEW_OUTLIER_BODY = '''    too_slow = rate < lower_bound and syllable_rate < syllable_floor
    # Cận trên xét bằng nhịp đo với khoảng lặng CÓ THẬT khi chỗ gọi đưa nó tới. Cùng một hình
    # với phép đếm âm tiết ở trên: thước thứ hai chỉ được bớt lời kết tội, không được thêm -
    # `fast_rate` luôn nhỏ hơn hoặc bằng `rate`, nên "nhanh" giờ đòi cả hai thước đồng ý.
    too_fast = (rate if fast_rate is None else fast_rate) > upper_bound
    return bool(too_slow or too_fast)'''
assert s.count(OLD_OUTLIER_BODY) == 1, "khong khop than pace_is_outlier"
s = s.replace(OLD_OUTLIER_BODY, NEW_OUTLIER_BODY, 1)

OLD_GATE = '''        pause_seconds = min(
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
        metrics["pace_outlier"] = float(pace_is_outlier(rate, syllable_rate, pace, bounds))'''
NEW_GATE = '''        pause_seconds = min(
            PAUSE_GROUP_SECONDS * pause_group_count(text),
            metrics["duration"] * MAX_PAUSE_FRACTION,
        )
        speech_seconds = max(metrics["duration"] - pause_seconds, MIN_SPEECH_SECONDS)
        rate = speakable_chars / speech_seconds
        # Ngân sách trên là một phỏng đoán, và ở câu thoại ngắn nó đòi nhiều hơn số giây giọng
        # thật sự im: đo trên 12 bản thu thật của câu chương 082 - câu đã mất sau 22 lần thử -
        # ngân sách đòi 1,20-1,34 giây ở chỗ chỉ có 0,39-0,53 giây khoảng lặng, và nhịp bị thổi
        # từ 14-16 lên 29-32 kt/s. Nên cận TRÊN xét thêm bằng khoảng lặng đo được.
        #
        # `heard_rate` luôn nhỏ hơn hoặc bằng `rate`, nên đây là thay đổi MỘT CHIỀU: chỉ bớt
        # lời kết tội "đọc quá nhanh", không thêm được lời nào. Cận DƯỚI giữ nguyên thước cũ,
        # vì ngân sách sinh ra để bảo vệ đúng chỗ ấy - đo trên 3000 đoạn đã chốt, chặn cả hai
        # cận sẽ biến 2 đoạn đang đạt thành ngoài băng ở cận dưới.
        silence_seconds = measured_silence_seconds(array, sample_rate)
        heard_pause_seconds = min(pause_seconds, silence_seconds)
        heard_speech_seconds = max(metrics["duration"] - heard_pause_seconds, MIN_SPEECH_SECONDS)
        heard_rate = speakable_chars / heard_speech_seconds
        metrics["pause_group_count"] = float(pause_group_count(text))
        metrics["measured_silence_seconds"] = float(silence_seconds)
        lower_bound = float(bounds[0])
        upper_bound = float(bounds[1])
        hard_lower = lower_bound * RATE_HARD_MIN_FACTOR
        hard_upper = upper_bound * RATE_HARD_MAX_FACTOR
        if rate < hard_lower or heard_rate > hard_upper:
            raise AudioQualityError(
                f"speech rate far outside {pace} safety range: {rate:.2f} chars/s "
                f"({heard_rate:.2f} với khoảng lặng đo được) not in "
                f"[{hard_lower:.2f}, {hard_upper:.2f}]"
            )
        syllable_rate = spoken_syllables(text) / speech_seconds
        metrics["chars_per_second"] = float(rate)
        metrics["chars_per_second_heard"] = float(heard_rate)
        metrics["syllables_per_second"] = float(syllable_rate)
        metrics["pace_outlier"] = float(
            pace_is_outlier(rate, syllable_rate, pace, bounds, fast_rate=heard_rate)
        )'''
assert s.count(OLD_GATE) == 1, "khong khop khoi kiem nhip trong validate_audio_array"
s = s.replace(OLD_GATE, NEW_GATE, 1)

io.open(p, "w", encoding="utf-8", newline="\n").write(s)
print(f"da va {p}")

TEST = '''"""Cận trên của phép kiểm nhịp phải xét khoảng lặng CÓ THẬT, không xét ngân sách đoán.

Ba đoạn của cuốn 2 mất hẳn bản thu vì bị kết tội "đọc quá nhanh" khi không hề nhanh: chương 082
(`“Tôi không biết ‘xoay’ đâu, Felicia.”`, 22 lần thử, 29–32,50 kt/s), chương 131 (`“Chà… Cậu
‘nếu’ nhiều thật đấy, Lucien.”`, 11 lần thử, 26,37) và chương 090.

Nhịp không phải ký tự chia thời lượng: `validate_audio_array` trừ trước một **ngân sách nghỉ**
0,276 giây mỗi nhóm dấu câu. Ngân sách ấy cứu những câu đọc đúng dấu câu khỏi bị gọi là chậm,
nhưng nó là phỏng đoán chỉnh chuẩn trên câu dài. Phép thử GPU 08:30 ngày 2026-09-15: bốn dạng
văn bản của cùng một câu (có/không nháy, có/không ngoặc đơn lồng) cho **cùng một thời lượng tới
hai chữ số thập phân** — giọng đọc không nghỉ ở dấu ngoặc. Với câu thoại 2,16 giây, ngân sách
chạm trần `MAX_PAUSE_FRACTION`, đòi 1,296 giây ở chỗ chỉ có 0,46 giây im lặng, và nhịp bị thổi
từ 15,29 lên 30,09 kt/s. Cả 12 bản thu thật của câu ấy đều đi từ NGOÀI BĂNG về đạt khi trừ đúng
số giây im lặng.

Nên cận TRÊN có thêm một thước: nhịp tính với khoảng lặng đo được. Nó luôn nhỏ hơn hoặc bằng
nhịp cũ, nên thay đổi là **một chiều** — chỉ bớt lời kết tội, không thêm. Cận DƯỚI giữ nguyên
thước cũ: đo trên 3000 đoạn đã chốt, chặn cả hai cận biến 2 đoạn đang đạt thành ngoài băng ở
cận dưới, và `“Chào, Felicia. Và… cậu ở đây sao, Lucien!”` (13,75 → 10,27) là một trong hai.
"""
from __future__ import annotations

import inspect

import numpy as np
import pytest

from ebook_reader import audio_io
from ebook_reader.audio_io import (
    MAX_PAUSE_FRACTION,
    MIN_SPEECH_SECONDS,
    PAUSE_GROUP_SECONDS,
    measured_silence_seconds,
    pace_is_outlier,
    pause_group_count,
    spoken_speakable_chars,
    spoken_syllables,
)

NORMAL = (12.5, 24.5)
SAMPLE_RATE = 24_000
# Đúng câu đã mất bản thu ở chương 082 sau 22 lần thử.
LOST_LINE = "\\u201cTôi không biết \\u2018xoay\\u2019 đâu, Felicia.\\u201d"
# Một trong hai đoạn mà chặn ở cận dưới sẽ giết; nó đang đạt và phải tiếp tục đạt.
SLOW_LINE = "\\u201cChào, Felicia. Và\\u2026 cậu ở đây sao, Lucien!\\u201d"
ONE_FRAME = 0.011


def _take(speech_seconds: float, silence_seconds: float, *, amplitude: float = 0.3) -> np.ndarray:
    """Sóng âm hình "nói - im - nói", đúng số giây yêu cầu ở mỗi phần."""
    half = max(1, int(round(SAMPLE_RATE * speech_seconds / 2)))
    quiet = int(round(SAMPLE_RATE * silence_seconds))
    tone = np.sin(np.linspace(0.0, 200.0 * np.pi, half, dtype=np.float32)) * amplitude
    return np.concatenate([tone, np.zeros(quiet, dtype=np.float32), tone])


def _budget(text: str, duration: float) -> float:
    return min(PAUSE_GROUP_SECONDS * pause_group_count(text), duration * MAX_PAUSE_FRACTION)


def _rate(text: str, duration: float, pause: float) -> float:
    return spoken_speakable_chars(text) / max(duration - pause, MIN_SPEECH_SECONDS)


def test_the_measured_silence_finds_the_gap() -> None:
    assert measured_silence_seconds(_take(1.70, 0.46), SAMPLE_RATE) == pytest.approx(
        0.46, abs=ONE_FRAME
    )


def test_a_gain_does_not_change_the_measured_silence() -> None:
    """`atomic_write_wav` đo cùng một bản thu hai lần, trước và sau khi cân âm lượng.

    Ngưỡng dBFS tuyệt đối sẽ cho hai con số khác nhau ở hai lần ấy, và cùng một bản thu có thể
    đạt ở lần này rồi trượt ở lần kia. Ngưỡng so với đỉnh thì miễn nhiễm với phép nhân.
    """
    take = _take(1.70, 0.46)

    assert (
        measured_silence_seconds(take, SAMPLE_RATE)
        == measured_silence_seconds(take * 0.12, SAMPLE_RATE)
        == measured_silence_seconds(take * 3.0, SAMPLE_RATE)
    )


def test_a_gap_too_short_to_be_a_pause_is_not_counted() -> None:
    assert measured_silence_seconds(_take(1.70, 0.02), SAMPLE_RATE) == 0.0


def test_speech_without_a_gap_measures_no_silence() -> None:
    assert measured_silence_seconds(_take(2.16, 0.0), SAMPLE_RATE) == 0.0


def test_an_empty_or_silent_take_does_not_raise() -> None:
    assert measured_silence_seconds(np.zeros(0, dtype=np.float32), SAMPLE_RATE) == 0.0
    assert measured_silence_seconds(np.zeros(SAMPLE_RATE, dtype=np.float32), SAMPLE_RATE) == 1.0
    assert measured_silence_seconds(_take(1.0, 0.5), 0) == 0.0


def test_the_lost_line_is_no_longer_called_too_fast() -> None:
    duration = 2.16  # một trong 12 bản thu thật của phép thử GPU sáng 2026-09-15
    silence = measured_silence_seconds(_take(duration - 0.46, 0.46), SAMPLE_RATE)
    budget = _budget(LOST_LINE, duration)
    charged = _rate(LOST_LINE, duration, budget)
    heard = _rate(LOST_LINE, duration, min(budget, silence))
    syllables = spoken_syllables(LOST_LINE) / max(duration - budget, MIN_SPEECH_SECONDS)

    assert budget == pytest.approx(1.296), "ngân sách chạm trần MAX_PAUSE_FRACTION"
    assert charged == pytest.approx(30.09, rel=0.001), "con số đã kết tội bản thu"
    assert heard == pytest.approx(15.29, rel=0.001), "nhịp thật, giữa dải 12,5-24,5"
    assert pace_is_outlier(charged, syllables, "normal", NORMAL), "thước cũ vẫn kết tội"
    assert not pace_is_outlier(charged, syllables, "normal", NORMAL, fast_rate=heard)


def test_a_take_that_really_is_rushed_is_still_rejected() -> None:
    """Cửa vẫn phải đóng: cùng văn bản ấy đọc trong 1 giây thì nhanh theo cả hai thước."""
    duration = 1.00
    silence = measured_silence_seconds(_take(0.95, 0.05), SAMPLE_RATE)
    budget = _budget(LOST_LINE, duration)
    charged = _rate(LOST_LINE, duration, budget)
    heard = _rate(LOST_LINE, duration, min(budget, silence))
    syllables = spoken_syllables(LOST_LINE) / max(duration - budget, MIN_SPEECH_SECONDS)

    assert heard > float(NORMAL[1]), heard
    assert pace_is_outlier(charged, syllables, "normal", NORMAL, fast_rate=heard)


def test_with_no_silence_at_all_the_rate_is_characters_over_duration() -> None:
    """Không có khoảng lặng nào thì không trừ gì, và 26 ký tự trong 2,16 giây không phải nhanh."""
    duration = 2.16
    silence = measured_silence_seconds(_take(duration, 0.0), SAMPLE_RATE)
    budget = _budget(LOST_LINE, duration)
    heard = _rate(LOST_LINE, duration, min(budget, silence))

    assert silence == 0.0
    assert heard == pytest.approx(spoken_speakable_chars(LOST_LINE) / duration)
    assert heard == pytest.approx(12.04, rel=0.001)


def test_the_second_ruler_can_only_remove_a_verdict() -> None:
    """Thước mới không được thêm một lời kết tội nào - `fast_rate` luôn <= `rate`."""
    assert not pace_is_outlier(30.0, 7.0, "normal", NORMAL, fast_rate=20.0)
    assert pace_is_outlier(30.0, 7.0, "normal", NORMAL, fast_rate=26.0)
    assert pace_is_outlier(30.0, 7.0, "normal", NORMAL)


def test_the_slow_side_keeps_the_old_ruler() -> None:
    """Đoạn `“Chào, Felicia...”`: 13,75 kt/s với ngân sách, 10,27 với khoảng lặng thật.

    Nó đang đạt. Nếu khoảng lặng đo được cũng chặn cận dưới thì nó thành "đọc quá chậm" - 1
    trong 2 đoạn như thế trên 3000 đoạn đã chốt, và đúng lý do cận dưới giữ thước cũ.
    """
    duration = spoken_speakable_chars(SLOW_LINE) / 13.75 + 1.656
    budget = _budget(SLOW_LINE, duration)
    charged = _rate(SLOW_LINE, duration, budget)
    heard = _rate(SLOW_LINE, duration, min(budget, 0.94))
    syllables = spoken_syllables(SLOW_LINE) / max(duration - budget, MIN_SPEECH_SECONDS)

    assert charged == pytest.approx(13.75, rel=0.001)
    assert heard < float(NORMAL[0]), "nhịp với khoảng lặng thật nằm dưới sàn"
    assert not pace_is_outlier(charged, syllables, "normal", NORMAL, fast_rate=heard)


def test_the_gate_reads_the_measured_silence_from_the_waveform() -> None:
    """Chỗ gọi phải đưa sóng âm vào phép đo, và chỉ đưa nó tới cận trên."""
    source = inspect.getsource(audio_io.validate_audio_array)

    assert "measured_silence_seconds(array, sample_rate)" in source
    assert "fast_rate=heard_rate" in source
    assert "if rate < hard_lower or heard_rate > hard_upper:" in source
'''
t = root / "tests" / "test_the_pause_budget_cannot_exceed_the_silence.py"
io.open(t, "w", encoding="utf-8", newline="\n").write(TEST)
print(f"da tao {t}")
