"""`ASR_TRANSCRIPT_RATE_IMPOSSIBLE` phải được xử y như em ruột của nó.

Lô 2 mất hai chương (031, 043) vì mã này, và **cả hai đoạn là tiếng cười**:

```
'"Ahaha! Hahahaha! Ahahahaha!"'  ->  Whisper: 'huff huff huff huff ...'  x15
'"Aaahahahaha! Hahahahaha!"'     ->  Whisper: 'ah ah ah ah ah ...'       x26
```

Whisper lặp vòng trên tiếng phi-từ-vựng, và một vòng lặp thì dài hơn audio — nên phép kiểm nổ
**đúng** và nói một điều thật về *phiên bản*. Nó không nói gì về *bản thu*.

`_evaluate_transcript_core` trả hai mã cạnh nhau với hình dạng y hệt (`ASR_INCONCLUSIVE`,
`repairable: False`, `severe: False`). Cái kia được nâng từ chuỗi trần thành hằng số và đưa vào
danh sách không-chặn; cái này bị bỏ sót trong đúng lần dọn ấy.
"""
from __future__ import annotations

from ebook_reader.asr import (
    ASR_TRANSCRIPT_RATE_IMPOSSIBLE,
    ASR_TRANSCRIPT_TIMELINE_IMPOSSIBLE,
    asr_answer_is_about_other_audio,
    transcript_exceeds_physical_rate,
)
from ebook_reader.pipeline import (
    HIGH_QUALITY_ALLOWED_SEGMENT_WARNINGS,
    MACHINE_ACCEPTABLE_SEGMENT_WARNINGS,
)


def test_a_looping_transcript_is_not_about_the_audio() -> None:
    assert asr_answer_is_about_other_audio(ASR_TRANSCRIPT_RATE_IMPOSSIBLE)
    assert asr_answer_is_about_other_audio(ASR_TRANSCRIPT_TIMELINE_IMPOSSIBLE)


def test_it_does_not_block_a_chapter() -> None:
    """Cả hai danh sách, y như em ruột — khác đi là một quyết định mới cần lý do riêng."""
    assert ASR_TRANSCRIPT_RATE_IMPOSSIBLE in HIGH_QUALITY_ALLOWED_SEGMENT_WARNINGS
    assert ASR_TRANSCRIPT_RATE_IMPOSSIBLE in MACHINE_ACCEPTABLE_SEGMENT_WARNINGS


def test_the_two_codes_are_treated_identically_everywhere() -> None:
    """Nếu về sau ai tách chúng ra thì phải tách có chủ ý, không phải vì bỏ sót."""
    for collection in (HIGH_QUALITY_ALLOWED_SEGMENT_WARNINGS, MACHINE_ACCEPTABLE_SEGMENT_WARNINGS):
        assert (ASR_TRANSCRIPT_RATE_IMPOSSIBLE in collection) == (
            ASR_TRANSCRIPT_TIMELINE_IMPOSSIBLE in collection
        )


def test_batch_2_laughter_really_does_trip_the_rate_check() -> None:
    """Mẫu thật, chứ không phải mẫu bịa: hai phiên bản đã làm hỏng chương 031 và 043."""
    assert transcript_exceeds_physical_rate(" ".join(["huff"] * 15), 2.32)
    assert transcript_exceeds_physical_rate(" ".join(["ah"] * 26), 2.48)


def test_an_ordinary_transcript_does_not_trip_it() -> None:
    """Phép kiểm vẫn phải nổ đúng lúc — bản vá này không nới ngưỡng của nó."""
    assert not transcript_exceeds_physical_rate("Tôi nhếch mép.", 2.0)
    assert not transcript_exceeds_physical_rate("", 2.0)
