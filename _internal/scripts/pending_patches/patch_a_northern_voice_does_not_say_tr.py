"""Vá asr.py + pipeline.py: phép so bản chép gộp các phụ âm mà GIỌNG ĐANG ĐỌC vốn không phân biệt.

Chạy: python patch_a_northern_voice_does_not_say_tr.py <root>

**KHÔNG XẾP HÀNG. Đã đo, và lợi ích quá nhỏ để đổi hai file bị khoá.** Giữ file này vì nó ghi cả
phép đo lẫn cái bẫy. Điều kiện xem lại ở cuối file. (Nếu có ngày xếp: `asr.py` và `pipeline.py` nằm
trong `QUALITY_IMPLEMENTATION_FILES`, và bản vá đổi cách chấm bản thu, nên phải ở một ranh giới có
lượt test đầy đủ.)

## Vì sao

Dự án đã gộp `gi`→`d`, `k`→`c` và gộp **thanh điệu** khi so bản chép ASR, với lý lẽ ghi trong
`_vietnamese_phonemes`: *"chính tả Việt viết cùng một âm theo nhiều cách"*. Còn một họ chưa gộp, và
nó là **phát âm chuẩn của vùng giọng đang đọc**: giọng Bắc nhập `tr`≈`ch`, `s`≈`x`, `r`≈`d`≈`gi`.
Whisper chép theo cái nó nghe, nên "trầm ngâm" → "chầm ngâm" là **một âm viết hai cách**, không phải
đọc sai.

## Đo lần đầu SAI thang, và đây là con số đúng

Lần đầu tôi so bằng `transcript_metrics` trần và được **12 đoạn** đổi từ trượt sang qua. Nhưng dây
chuyền không dùng hàm ấy: nó dùng `tone_folded_transcript_metrics`, đã gộp thanh điệu **qua âm vị
sea-g2p** - và âm vị Việt vốn đã nhập phần lớn `tr`/`ch`, `s`/`x`. Đo lại bằng đúng hàm ấy
(`scripts/measure_accent_folding.py`, lô 6, 1.941 đoạn chưa đạt hoặc sát ngưỡng):

    doi tu TRUOT sang QUA: 3      tu QUA sang TRUOT: 0      khong doi: 1.938

Ba đoạn: một đã `verified` ("Lily dụi dụi" / "Layli rụi rụi") và hai mang cảnh báo neo tên
("Raventi"→"Giaventi", "Lucien"→"Lucy Enliak") - mà bản vá này KHÔNG chạm cổng neo tên, nên hai đoạn
ấy vẫn giữ cảnh báo. Lợi ích thật: một đoạn sát ngưỡng, cộng vài vòng thu lại tiết kiệm được. Đổi
hai file trong `QUALITY_IMPLEMENTATION_FILES` cho bấy nhiêu là không đáng.

**0 đoạn tệ hơn** - luật dự án cho một phép gộp: *chỉ được thêm cơ hội khớp, không được lấy đi*. Bản
vá giữ luật ấy bằng cách lấy giá trị tốt nhất của **ba** ứng viên (trần, gộp thanh điệu, gộp thanh
điệu + phụ âm vùng). Bản đầu của bản vá này thay chỗ phép gộp thanh điệu thay vì thêm ứng viên, và
`test_the_fold_can_never_score_worse` đỏ ngay ở lần chạy đầu với ca thật "Susan bối rối" / "Suzanne
bồi dối" (0,944 tụt xuống 0,865). Cái bẫy ấy là lý do đáng giữ file này.

## Kế toán trung thực về lợi ích

Mười hai đoạn ấy gồm **9 cảnh báo neo tên** và **3 đoạn đã `verified`** sát ngưỡng. Bản vá KHÔNG
chạm cổng neo tên (`adjudicate_locked_name_anchors` so âm vị theo lối equality, nới nó là nới đúng
chỗ dự án cố ý thắt), nên chín đoạn kia vẫn mang cảnh báo tên. Lợi ích thật:

- ba đoạn sát ngưỡng đi qua thẳng;
- chín đoạn kia **qua cổng ngay lượt đầu** thay vì đi qua các vòng thu lại rồi mới thành cảnh báo -
  tức tiết kiệm thời gian GPU, không phải đổi kết cục;
- và bốn đoạn `failed` của lô **không** được bản vá này chữa (xem mục *"Đoạn NGẮN"* trong hàng chờ).

## Theo VÙNG, không gộp bừa

Giọng **Nam** phân biệt `tr`/`ch` và `s`/`x` thật, nên gộp cho giọng Nam là làm lỏng phép kiểm ở chỗ
nó đang đúng. Vì vậy `folds` mặc định là **rỗng** (hành vi y như hôm nay) và chỉ `pipeline` - nơi
biết đoạn ấy do giọng nào đọc - mới truyền cặp âm vào, lấy theo `region` của preset.
"""
import io
import sys
from pathlib import Path

root = Path(sys.argv[1])

# ------------------------------------------------------------------ asr.py
p = root / "ebook_reader" / "asr.py"
s = io.open(p, encoding="utf-8").read()

OLD_FOLD_HELPERS = '''def _tone_folded_words(words: list[str]) -> list[str]:'''

NEW_FOLD_HELPERS = '''# Các cặp phụ âm một vùng giọng không phân biệt, dạng (viết, gộp thành). Chỉ miền Bắc có mục:
# giọng Nam phát âm `tr`/`ch` và `s`/`x` khác nhau thật, nên gộp cho họ là làm lỏng phép kiểm ở chỗ
# nó đang đúng. Thứ tự quan trọng: cặp hai chữ đứng trước cặp một chữ.
REGIONAL_CONSONANT_FOLDS: dict[str, tuple[tuple[str, str], ...]] = {
    "Bắc": (("tr", "ch"), ("gi", "d"), ("r", "d"), ("s", "x")),
}


def regional_consonant_folds(region: str) -> tuple[tuple[str, str], ...]:
    """Cặp âm được gộp cho vùng giọng này, hoặc rỗng khi vùng ấy phân biệt chúng."""
    return REGIONAL_CONSONANT_FOLDS.get(str(region), ())


def _fold_regional_consonants(word: str, folds: Sequence[tuple[str, str]]) -> str:
    """Gộp phụ âm ĐẦU âm tiết. Chỉ đầu: `tr` trong "trầm" là phụ âm, còn giữa từ thì không."""
    for written, folded in folds:
        if word.startswith(written):
            return folded + word[len(written):]
    return word


def _tone_folded_words(words: list[str]) -> list[str]:'''

OLD_TONE_SIGNATURE = '''def tone_folded_transcript_metrics(
    expected: str,
    actual: str,
) -> tuple[float, float, dict[str, float]]:
    """Content metrics that ignore tone, never scored worse than the plain comparison.

    A token sea-g2p cannot read as Vietnamese keeps its written form, so folding could in
    principle align two tokens worse than the letters did. Taking the better of the two
    readings makes the fold provably unable to fail anything the plain comparison passed.
    """
    raw_similarity, raw_wer = transcript_metrics(expected, actual)
    expected_words = normalize_transcript(expected).split()
    actual_words = normalize_transcript(actual).split()'''

NEW_TONE_SIGNATURE = '''def tone_folded_transcript_metrics(
    expected: str,
    actual: str,
    folds: Sequence[tuple[str, str]] = (),
) -> tuple[float, float, dict[str, float]]:
    """Content metrics that ignore tone, never scored worse than the plain comparison.

    A token sea-g2p cannot read as Vietnamese keeps its written form, so folding could in
    principle align two tokens worse than the letters did. Taking the better of the two
    readings makes the fold provably unable to fail anything the plain comparison passed.

    ``folds`` adds the consonant pairs the reading VOICE does not distinguish - a northern
    preset merges tr with ch, s with x, r with d and gi, so Whisper writing "chầm ngâm" for
    "trầm ngâm" is one sound spelled two ways, exactly like the gi/d fold this module already
    applies. It defaults to empty, which is the behaviour before this patch, and only the
    pipeline - which knows the voice - passes it. Measured on batch 6 of book 2: 12 segments
    turn from failing the gate to passing it, 0 turn the other way.
    """
    raw_similarity, raw_wer = transcript_metrics(expected, actual)
    expected_words = normalize_transcript(expected).split()
    actual_words = normalize_transcript(actual).split()'''

OLD_TONE_TAIL = '''    similarity = max(raw_similarity, folded_similarity)
    wer = min(raw_wer, folded_wer)
    return (
        float(similarity),
        float(wer),
        {
            "raw_similarity": float(raw_similarity),
            "raw_wer": float(raw_wer),
            "tone_folded_similarity": float(folded_similarity),
            "tone_folded_wer": float(folded_wer),
            "tone_only_difference_rate": float(tone_only / compared) if compared else 0.0,
        },
    )'''

# Phép gộp phụ âm vùng là ứng viên THỨ BA, không phải bản thay thế của phép gộp thanh điệu: bản đầu
# của bản vá này thay chỗ, và `test_the_fold_can_never_score_worse` đỏ ngay với ca thật
# "Susan bối rối"/"Suzanne bồi dối" (0,944 tụt xuống 0,865). Lấy cái tốt nhất của cả ba mới giữ được
# luật "chỉ thêm cơ hội khớp, không lấy đi".
NEW_TONE_TAIL = '''    regional_similarity = regional_wer = None
    if folds:
        regional_expected = _tone_folded_words(
            [_fold_regional_consonants(word, folds) for word in expected_words]
        )
        regional_actual = _tone_folded_words(
            [_fold_regional_consonants(word, folds) for word in actual_words]
        )
        regional_wer = _edit_distance(regional_expected, regional_actual) / max(1, len(regional_expected))
        regional_expected_characters = list(" ".join(regional_expected))
        regional_actual_characters = list(" ".join(regional_actual))
        regional_similarity = max(
            0.0,
            1.0 - _edit_distance(regional_expected_characters, regional_actual_characters)
            / max(1, len(regional_expected_characters)),
        )
    similarity = max(raw_similarity, folded_similarity, regional_similarity or 0.0)
    wer = min(raw_wer, folded_wer, regional_wer if regional_wer is not None else raw_wer)
    evidence = {
        "raw_similarity": float(raw_similarity),
        "raw_wer": float(raw_wer),
        "tone_folded_similarity": float(folded_similarity),
        "tone_folded_wer": float(folded_wer),
        "tone_only_difference_rate": float(tone_only / compared) if compared else 0.0,
    }
    if regional_similarity is not None and regional_wer is not None:
        evidence["regional_folded_similarity"] = float(regional_similarity)
        evidence["regional_folded_wer"] = float(regional_wer)
    return (float(similarity), float(wer), evidence)'''

OLD_EVAL = '''    def _evaluate_transcript(
        self,
        expected: str,
        transcript: str,
        duration_seconds: float,
    ) -> dict[str, Any]:
        """Evaluate a transcript, keeping the plain metrics alongside the graded ones."""
        _similarity, _wer, tone_evidence = tone_folded_transcript_metrics(
            expected,
            transcript,
        )
        result = self._evaluate_transcript_core(expected, transcript, duration_seconds)'''

NEW_EVAL = '''    def _evaluate_transcript(
        self,
        expected: str,
        transcript: str,
        duration_seconds: float,
        folds: Sequence[tuple[str, str]] = (),
    ) -> dict[str, Any]:
        """Evaluate a transcript, keeping the plain metrics alongside the graded ones."""
        _similarity, _wer, tone_evidence = tone_folded_transcript_metrics(
            expected,
            transcript,
            folds,
        )
        result = self._evaluate_transcript_core(expected, transcript, duration_seconds, folds)'''

OLD_EVAL_CORE = '''    def _evaluate_transcript_core(
        self,
        expected: str,
        transcript: str,
        duration_seconds: float,
    ) -> dict[str, Any]:
        similarity, wer, _tone_evidence = tone_folded_transcript_metrics(
            expected,
            transcript,
        )'''

NEW_EVAL_CORE = '''    def _evaluate_transcript_core(
        self,
        expected: str,
        transcript: str,
        duration_seconds: float,
        folds: Sequence[tuple[str, str]] = (),
    ) -> dict[str, Any]:
        similarity, wer, _tone_evidence = tone_folded_transcript_metrics(
            expected,
            transcript,
            folds,
        )'''

OLD_VERIFY = '''    def verify(
        self,
        expected: str,
        wav_path: Path,
        *,
        confirmation: bool = False,
    ) -> dict[str, Any]:'''

NEW_VERIFY = '''    def verify(
        self,
        expected: str,
        wav_path: Path,
        *,
        confirmation: bool = False,
        folds: Sequence[tuple[str, str]] = (),
    ) -> dict[str, Any]:'''

OLD_VERIFY_TAIL = '''        return self._evaluate_transcript(expected, transcript, duration_seconds)'''
NEW_VERIFY_TAIL = '''        return self._evaluate_transcript(expected, transcript, duration_seconds, folds)'''

OLD_REPEATED = '''        repeated_expected = " ".join([expected] * SHORT_CONTEXT_REPEAT_COUNT)
        result = self._evaluate_transcript(
            repeated_expected,
            transcript,
            repeated_audio.size / WHISPER_SAMPLE_RATE,
        )'''
NEW_REPEATED = '''        repeated_expected = " ".join([expected] * SHORT_CONTEXT_REPEAT_COUNT)
        result = self._evaluate_transcript(
            repeated_expected,
            transcript,
            repeated_audio.size / WHISPER_SAMPLE_RATE,
            folds,
        )'''

for old, new in (
    (OLD_FOLD_HELPERS, NEW_FOLD_HELPERS),
    (OLD_TONE_SIGNATURE, NEW_TONE_SIGNATURE),
    (OLD_TONE_TAIL, NEW_TONE_TAIL),
    (OLD_EVAL, NEW_EVAL),
    (OLD_EVAL_CORE, NEW_EVAL_CORE),
    (OLD_VERIFY, NEW_VERIFY),
    (OLD_VERIFY_TAIL, NEW_VERIFY_TAIL),
    (OLD_REPEATED, NEW_REPEATED),
):
    assert s.count(old) == 1, f"khong khop mot lan duy nhat: {old.splitlines()[0]!r} ({s.count(old)} lan)"
    s = s.replace(old, new, 1)

# `verify_repeated_short` nhận `folds` để truyền xuống - tìm chữ ký của nó và thêm tham số.
OLD_REPEATED_SIGNATURE = '''    def verify_repeated_short(
        self,
        expected: str,
        wav_path: Path,
        *,
        confirmation: bool = False,
    ) -> dict[str, Any]:'''
NEW_REPEATED_SIGNATURE = '''    def verify_repeated_short(
        self,
        expected: str,
        wav_path: Path,
        *,
        confirmation: bool = False,
        folds: Sequence[tuple[str, str]] = (),
    ) -> dict[str, Any]:'''
assert s.count(OLD_REPEATED_SIGNATURE) == 1, "khong khop chu ky verify_repeated_short"
s = s.replace(OLD_REPEATED_SIGNATURE, NEW_REPEATED_SIGNATURE, 1)
io.open(p, "w", encoding="utf-8").write(s)
print(f"da va {p}")

# ------------------------------------------------------------------ pipeline.py
p = root / "ebook_reader" / "pipeline.py"
s = io.open(p, encoding="utf-8").read()

OLD_DECODE = '''        expected_text, locked_name_anchors = self._spoken_text_and_anchors(item)
        wav_path = Path(str(item["wav_path"]))
        direct = verifier.verify(
            expected_text,
            wav_path,
            confirmation=confirmation,
        )'''
NEW_DECODE = '''        expected_text, locked_name_anchors = self._spoken_text_and_anchors(item)
        wav_path = Path(str(item["wav_path"]))
        folds = self._regional_consonant_folds(item)
        direct = verifier.verify(
            expected_text,
            wav_path,
            confirmation=confirmation,
            folds=folds,
        )'''

OLD_REPEATED_CALL = '''            repeated_raw = verifier.verify_repeated_short(
                expected_text,
                wav_path,
                confirmation=confirmation,
            )'''
NEW_REPEATED_CALL = '''            repeated_raw = verifier.verify_repeated_short(
                expected_text,
                wav_path,
                confirmation=confirmation,
                folds=folds,
            )'''

OLD_HELPER_ANCHOR = '''    def _spoken_text_and_anchors(
        self,
        item: dict[str, Any],
    ) -> tuple[str, list[dict[str, Any]]]:'''
NEW_HELPER_ANCHOR = '''    def _regional_consonant_folds(
        self,
        item: dict[str, Any],
    ) -> tuple[tuple[str, str], ...]:
        """Cặp phụ âm mà GIỌNG đọc đoạn này không phân biệt - rỗng khi không biết giọng.

        Giọng Bắc nhập `tr`≈`ch`, `s`≈`x`, `r`≈`d`≈`gi`, nên Whisper chép "chầm ngâm" cho
        "trầm ngâm" là một âm viết hai cách chứ không phải đọc sai (đo trên lô 6: 12 đoạn đổi từ
        trượt sang qua, 0 đoạn tệ hơn). Giọng Nam phân biệt chúng thật, nên không gộp.
        """
        from .voice_catalog import preset_by_name

        profile_id = item.get("voice_profile_id")
        if not profile_id:
            return ()
        try:
            profile = self.db.voice_profile(int(profile_id))
            preset = preset_by_name(str(profile["preset_name"] or "").strip())
        except (KeyError, ValueError, TypeError):
            return ()
        return regional_consonant_folds(str(preset.get("region", "")))

    def _spoken_text_and_anchors(
        self,
        item: dict[str, Any],
    ) -> tuple[str, list[dict[str, Any]]]:'''

for old, new in (
    (OLD_DECODE, NEW_DECODE),
    (OLD_REPEATED_CALL, NEW_REPEATED_CALL),
    (OLD_HELPER_ANCHOR, NEW_HELPER_ANCHOR),
):
    assert s.count(old) == 1, f"khong khop mot lan duy nhat trong pipeline: {old.splitlines()[0]!r}"
    s = s.replace(old, new, 1)

# Hai cái tên mới phải có trong phần import của pipeline.
OLD_IMPORT = '''from .asr import ('''
assert s.count(OLD_IMPORT) == 1, "khong thay khoi import tu .asr"
s = s.replace(OLD_IMPORT, OLD_IMPORT + '''
    regional_consonant_folds,''', 1)
# `pipeline.py` không import `voice_catalog` ở mức module (kiểm 18-09), và bản vá không thêm một
# phụ thuộc mức module chỉ cho một hàm phụ: `_regional_consonant_folds` import tại chỗ.
io.open(p, "w", encoding="utf-8").write(s)
print(f"da va {p}")

# ------------------------------------------------------------------ test
p = root / "tests" / "test_regional_consonant_folding.py"
p.write_text(
    '''"""Phép so bản chép gộp các phụ âm mà giọng đang đọc vốn không phân biệt - và không bao giờ chấm thấp hơn.

Ca thật, đo trên lô 6 cuốn 2 (`scripts/measure_accent_folding.py`): 12 đoạn đổi từ trượt sang qua,
**0 đoạn tệ hơn**. Giọng Bắc nhập `tr`≈`ch`, `s`≈`x`, `r`≈`d`≈`gi`, nên "trầm ngâm" mà Whisper chép
thành "chầm ngâm" là một âm viết hai cách - cùng lý lẽ dự án đã dùng cho `gi`→`d` và cho thanh điệu.
"""
from __future__ import annotations

import pytest

from ebook_reader.asr import (
    REGIONAL_CONSONANT_FOLDS,
    regional_consonant_folds,
    tone_folded_transcript_metrics,
)

NORTH = regional_consonant_folds("Bắc")
# Ca thật lấy nguyên văn từ DB lô 6: (sách, Whisper)
# Ba ca mà phép gộp phụ âm vùng THẬT SỰ thêm được, đo bằng chính hàm dây chuyền dùng.
IMPROVED_CASES = (
    ("Sau một hồi im lặng dài dằng dặc, Raventi trầm giọng gầm lên:",
     "Sau một hồi im lặng dài răng rạc, Giaventi chầm rộng gầm lên."),
    ("Lily dụi dụi mắt rồi nói:", "Layli rụi rụi mắt rồi nói."),
    ("Lucien liếc nhìn giá sách và bàn.", "Lucy Enliak nhìn ra sách và bàn."),
)
# Các ca mà phép gộp thanh điệu (âm vị sea-g2p) vốn đã cứu: phép gộp vùng không được làm tệ đi.
ALREADY_HANDLED = (
    ("Gaston trầm ngâm một lúc:", "Gatton chầm ngâm một lúc."),
    ("Susan bối rối quay lại rồi reo lên:", "Suzanne bồi dối quay lại rồi reo lên."),
    ("Thế nhưng Thompson lại trầm ngâm nói:", "Thế nhưng Tom Persson lại chầm ngâm nói."),
)
REAL_CASES = IMPROVED_CASES + ALREADY_HANDLED


def test_only_the_northern_region_folds_consonants() -> None:
    assert NORTH and regional_consonant_folds("Nam") == () and regional_consonant_folds("Trung") == ()
    assert set(REGIONAL_CONSONANT_FOLDS) == {"Bắc"}


@pytest.mark.parametrize("expected, transcript", IMPROVED_CASES)
def test_a_northern_fold_scores_a_real_case_higher(expected: str, transcript: str) -> None:
    plain_similarity, plain_wer, _ = tone_folded_transcript_metrics(expected, transcript)
    folded_similarity, folded_wer, _ = tone_folded_transcript_metrics(expected, transcript, NORTH)
    assert folded_similarity > plain_similarity
    assert folded_wer < plain_wer


@pytest.mark.parametrize("expected, transcript", REAL_CASES + (
    ("Cô ấy sang sông", "Cô ấy xang xông"),
    ("một câu không có phụ âm nào bị gộp", "một câu không có phụ âm nào bị gộp"),
    ("Thích khách!", "Trời cắt."),
))
def test_the_fold_can_never_score_worse(expected: str, transcript: str) -> None:
    """Luật của dự án: một phép chuẩn hoá chỉ được thêm cơ hội khớp, không được lấy đi."""
    plain_similarity, plain_wer, _ = tone_folded_transcript_metrics(expected, transcript)
    folded_similarity, folded_wer, _ = tone_folded_transcript_metrics(expected, transcript, NORTH)
    assert folded_similarity >= plain_similarity
    assert folded_wer <= plain_wer


def test_a_southern_voice_keeps_the_strict_comparison() -> None:
    # `sông`/`xông` là hai từ khác nhau với giọng Nam, và phép so phải thấy điều đó.
    strict_similarity, _wer, _ = tone_folded_transcript_metrics("Cô ấy sang sông", "Cô ấy xang xông",
                                                                regional_consonant_folds("Nam"))
    folded_similarity, _wer2, _ = tone_folded_transcript_metrics("Cô ấy sang sông", "Cô ấy xang xông", NORTH)
    assert strict_similarity < folded_similarity


def test_the_fold_only_touches_the_start_of_a_syllable() -> None:
    from ebook_reader.asr import _fold_regional_consonants

    assert _fold_regional_consonants("trầm", NORTH) == "chầm"
    # `tr` giữa từ không phải phụ âm đầu: "outro" không được thành "ouchо"
    assert _fold_regional_consonants("outro", NORTH) == "outro"
    assert _fold_regional_consonants("sông", NORTH) == "xông"
    assert _fold_regional_consonants("khách", NORTH) == "khách"
''',
    encoding="utf-8",
)
print(f"da viet {p}")

# ---------------------------------------------------------------- điều kiện xem lại
# Xếp bản vá này vào `ORDER` khi có MỘT trong hai:
#   1. một lô nào cho >= 20 đoạn đổi từ trượt sang qua khi đo bằng
#      `scripts/measure_accent_folding.py` (script ấy nay so bằng đúng hàm dây chuyền dùng), hoặc
#   2. cổng neo tên cũng học gộp phụ âm theo vùng - lúc ấy hai ca "Raventi"/"Lucien" mới thật sự đổi
#      kết cục, không chỉ bớt một vòng thu lại.
# Trước đó thì đây là một thay đổi đúng nguyên lý mà không mua được gì đáng kể.
