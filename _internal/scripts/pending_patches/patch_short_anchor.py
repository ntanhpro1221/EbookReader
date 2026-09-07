"""Va pipeline.py: neo ten tren doan qua ngan khong duoc chan chuong.

    python patch_short_anchor.py <thu muc chua ebook_reader/>
"""
import io
import sys
from pathlib import Path

root = Path(sys.argv[1])
p = root / "ebook_reader" / "pipeline.py"
s = io.open(p, encoding="utf-8").read()

OLD = '''                    # Only an ASR verdict can be forgiven for being unobtainable. A
                    # frame-ceiling endpoint is evidence from the generator itself -
                    # the take may simply be cut off - and short text says nothing
                    # about that.
                    asr_only_failure = reason not in {
                        ACTIVE_CEILING_ENDPOINT_REPAIR_REASON,
                        ASR_LOCKED_NAME_ANCHOR_MISMATCH,
                    } and not self._segment_has_non_asr_failure_evidence(item)'''

NEW = '''                    # Only an ASR verdict can be forgiven for being unobtainable. A
                    # frame-ceiling endpoint is evidence from the generator itself -
                    # the take may simply be cut off - and short text says nothing
                    # about that.
                    #
                    # The anchor is excluded for the same reason it exists: on a segment
                    # with real content, Whisper writing the wrong name is evidence about
                    # the name. But a segment that is NOTHING BUT a short name has no such
                    # content, and then the exclusion closes the only two doors at once -
                    # locked_name_review below needs ordinary content that passed its
                    # canonical thresholds, and there is none. `"Juli!"`, 0.56 seconds and
                    # four letters, could reach neither and blocked its chapter forever.
                    #
                    # So the anchor is excluded unless the reference is below
                    # ASR_MIN_VERIFIABLE_CHARS, where by this project's own established
                    # rule no ASR verdict carries information - the anchor's included.
                    # Measured on that take: six recordings, each decoded six ways, and the
                    # three context modes returned three different answers for the same
                    # file ("Đi" / "Thường đi x3" / "Từng đi x3"). A test with three answers
                    # has none.
                    #
                    # This does not soften the anchor where it works. The 20-second skill
                    # list that really is misread carries far more than ten characters and
                    # still blocks.
                    anchor_reference_too_short = (
                        reason == ASR_LOCKED_NAME_ANCHOR_MISMATCH
                        and asr_verdict_is_unverifiable(str(item["text"]))
                    )
                    asr_only_failure = (
                        reason
                        not in {
                            ACTIVE_CEILING_ENDPOINT_REPAIR_REASON,
                            ASR_LOCKED_NAME_ANCHOR_MISMATCH,
                        }
                        or anchor_reference_too_short
                    ) and not self._segment_has_non_asr_failure_evidence(item)'''

assert OLD in s, "khong khop asr_only_failure"
s = s.replace(OLD, NEW)
io.open(p, "w", encoding="utf-8").write(s)
print(f"da va {p}")
