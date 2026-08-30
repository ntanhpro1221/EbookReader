from __future__ import annotations


SHORT_CONTEXT_REPEAT_COUNT = 3
COLLAPSED_SHORT_CONTEXT_MODE = "repeat3_collapsed_v1"
COLLAPSED_SHORT_CONTEXT_EFFECTIVE_REPEAT_COUNT = 1
LOCKED_NAME_ANCHOR_METRICS_VERSION = 3

# Whisper is an English-biased multilingual model, so the spelling it chooses for a
# foreign name read with Vietnamese phonemes is not evidence about pronunciation:
# it wrote "joanne" for a correct "Giô-en" and "dôn" for a correct "Giôn". A locked
# name anchor therefore reports review evidence instead of holding hard-fail
# authority; sentence-level similarity and WER keep that authority, measured on
# canonical text so a name disagreement is never counted twice.
ASR_LOCKED_NAME_ANCHOR_REVIEW = "ASR_LOCKED_NAME_ANCHOR_REVIEW"

# An anchor that did not match reports one of these statuses. "fail" keeps the historic
# hard-fail authority; "review_eligible" additionally means the canonical sentence
# metrics, measured with the name spans removed, were acceptable.
LOCKED_NAME_ANCHOR_FAIL_STATUS = "fail"
LOCKED_NAME_ANCHOR_REVIEW_ELIGIBLE_STATUS = "review_eligible"
LOCKED_NAME_ANCHOR_UNMATCHED_STATUSES = (
    LOCKED_NAME_ANCHOR_FAIL_STATUS,
    LOCKED_NAME_ANCHOR_REVIEW_ELIGIBLE_STATUS,
)
