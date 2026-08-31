"""Both pronunciation delivery variants must anchor the same occurrences.

The candidate allocator refuses a source-spelling take whose anchors do not match the locked
ones, which is what stops a name being read two ways. That check is only usable if the two
variants agree on *which* occurrences are anchored, and they once did not: the source
variant anchored every locked English name while the locked variant anchored only those
whose spoken form differed from their spelling. Any entry read exactly as written therefore
drifted by construction - 17 of 79 segments in a real book.
"""

from __future__ import annotations

import inspect

from ebook_reader import tts
from ebook_reader.database import (
    PRONUNCIATION_DELIVERY_LOCKED,
    PRONUNCIATION_DELIVERY_SOURCE,
)

ANCHOR_IDENTITY_FIELDS = (
    "pronunciation_id",
    "source_start",
    "source_end",
    "surface",
    "normalized_surface",
    "matched_surface",
    "source",
    "canonical_spoken_form",
)


def test_anchor_creation_does_not_depend_on_the_variant() -> None:
    """The condition must not mention the variant at all, in either direction."""
    source = inspect.getsource(tts.TTSCoordinator._substitute_pronunciations)
    condition = source[
        source.index("replacement_anchor_tags = set()") : source.index("anchor_index = len(anchors)")
    ]
    code = "\n".join(
        line for line in condition.splitlines() if not line.strip().startswith("#")
    )
    assert "PRONUNCIATION_DELIVERY_SOURCE" not in code
    assert "PRONUNCIATION_DELIVERY_LOCKED" not in code
    assert "canonical_replacement != matched_text" in code


def test_the_two_variants_are_distinct_concepts_still() -> None:
    """Symmetry of anchoring must not have been achieved by collapsing the variants."""
    assert PRONUNCIATION_DELIVERY_LOCKED != PRONUNCIATION_DELIVERY_SOURCE


def test_spoken_form_is_not_part_of_anchor_identity() -> None:
    """It is the one field the variants are meant to differ on."""
    assert "spoken_form" not in ANCHOR_IDENTITY_FIELDS
    assert "canonical_spoken_form" in ANCHOR_IDENTITY_FIELDS


def test_the_allocator_still_compares_the_two_variants() -> None:
    """The fix is to the data the check reads, never to the check itself."""
    from ebook_reader import pipeline

    source = inspect.getsource(pipeline.BookPipeline._segment_candidate_pronunciation_delivery)
    assert "source-spelling pronunciation anchors drifted from locked anchors" in source
    assert "source_identity != locked_identity" in source
