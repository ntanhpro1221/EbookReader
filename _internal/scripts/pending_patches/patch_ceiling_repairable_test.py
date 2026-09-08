"""Test: cham tran khung la bang chung ve BAN THU, khong phai ve ASR."""
import io
import sys
from pathlib import Path

root = Path(sys.argv[1])
p = root / "tests" / "test_pipeline_mock.py"
s = io.open(p, encoding="utf-8").read()

TEST = '''

def test_a_ceiling_hit_take_is_repairable_even_when_asr_cannot_judge_it() -> None:
    """The gap that cost alpha.60 chapter 026.

    An inconclusive ASR verdict usually means the take is fine and the check is blind - a
    two-word line, an interjection - and re-recording changes nothing, so refusing to repair
    is right. It is wrong when the generator has already said the take is bad.

    generation_ceiling_hit means the model generated until it ran out of frames without ever
    stopping on its own. That is evidence about the recording, independent of whether ASR
    could read it.

    "Gì cơ?" is two words and four speakable characters; the take ran 1.92 seconds, which is
    2.1 chars/s against a normal 16. It hit the ceiling, trailed off quietly so
    generation_endpoint_active was 0, and _ceiling_endpoint_requires_repair wants both - so
    it declined. The pace gate never ran either, because four characters is under
    rate_check_min_chars of 24. The segment got zero repair candidates and blocked its
    chapter.

    scripts/probe_frame_cap.py regenerated that exact line at five caps and four came back
    clean at 0.64-0.80s, ending naturally with no ceiling hit. A re-roll is the right cure.
    """
    from ebook_reader.pipeline import BookPipeline

    runaway = {
        "warning_code": "TTS_GENERATION_CEILING_REACHED|ASR_TRANSCRIPT_TIMELINE_IMPOSSIBLE",
        "signal_json": json.dumps(
            {
                "duration": 1.92,
                "generation_ceiling_hit": 1.0,
                "generation_endpoint_active": 0.0,
                "trailing_rms": 0.0005,
            }
        ),
    }

    assert BookPipeline._segment_generation_hit_ceiling(runaway)
    assert not BookPipeline._ceiling_endpoint_requires_repair(runaway), (
        "hàm cũ bỏ qua nó vì endpoint đã tắt - đó là lý do phải có hàm mới"
    )


def test_a_take_that_never_hit_the_ceiling_is_still_not_repaired() -> None:
    """The narrowing must not turn every blind ASR verdict into a re-record."""
    from ebook_reader.pipeline import BookPipeline

    ordinary_short_line = {
        "warning_code": "ASR_UNVERIFIABLE_SHORT_TEXT",
        "signal_json": json.dumps({"duration": 0.48, "generation_ceiling_hit": 0.0}),
    }

    assert not BookPipeline._segment_generation_hit_ceiling(ordinary_short_line)


def test_the_ceiling_warning_alone_is_enough_when_metrics_are_missing() -> None:
    """A row whose signal did not survive still carries its warning code."""
    from ebook_reader.pipeline import BookPipeline

    assert BookPipeline._segment_generation_hit_ceiling(
        {"warning_code": "TTS_GENERATION_CEILING_REACHED", "signal_json": None}
    )
    assert not BookPipeline._segment_generation_hit_ceiling(
        {"warning_code": "", "signal_json": "not json at all"}
    )
'''

if "\nimport json\n" not in s:
    s = s.replace("from __future__ import annotations\n", "from __future__ import annotations\n\nimport json\n", 1)
s = s.rstrip() + "\n" + TEST
io.open(p, "w", encoding="utf-8").write(s)
print(f"da va {p}")
