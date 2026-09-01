"""The source boundary is stated in the schema, not enforced by rejection afterwards.

HOST_SOURCE_KIND_MISMATCH was 75% of all analysis rejections - around 32 per ten-chapter run
- and each one sent five segments back so that one could be corrected. The boundary is known
before the model answers, so the schema says it.
"""

from __future__ import annotations

import pytest

from ebook_reader.analysis import (
    ALLOWED_KINDS,
    _allowed_kinds_by_id,
    _output_schema_for_batch,
    _source_kind_transition_rule,
)


def _row(stable_id: str, kind_hint: str) -> dict[str, str]:
    return {"stable_id": stable_id, "kind_hint": kind_hint, "text": "Một câu."}


def _branch(schema: dict, stable_id: str) -> dict:
    items = schema["properties"]["segments"]["items"]
    return next(
        branch
        for branch in items["oneOf"]
        if branch["properties"]["id"]["enum"] == [stable_id]
    )


def test_a_dialogue_source_permits_only_dialogue() -> None:
    assert _allowed_kinds_by_id([_row("a", "dialogue")]) == {"a": ("dialogue",)}


def test_a_thought_source_permits_only_thought() -> None:
    assert _allowed_kinds_by_id([_row("a", "thought")]) == {"a": ("thought",)}


def test_a_narration_source_may_not_become_dialogue() -> None:
    allowed = _allowed_kinds_by_id([_row("a", "narration")])["a"]
    assert "dialogue" not in allowed
    assert "narration" in allowed


def test_the_allowed_set_comes_from_the_rule_that_rejects_crossings() -> None:
    """Schema and check must not be able to disagree about where the boundary is."""
    for hint in ("dialogue", "thought", "narration"):
        row = _row("a", hint)
        derived = _allowed_kinds_by_id([row]).get("a", tuple(sorted(ALLOWED_KINDS)))
        for kind in ALLOWED_KINDS:
            rejected = _source_kind_transition_rule(row, kind) is not None
            assert rejected == (kind not in derived), (hint, kind)


def test_an_unrestricted_segment_is_left_alone() -> None:
    """Only a real restriction is worth the larger schema."""
    row = _row("a", "narration")
    assert len(_allowed_kinds_by_id([row])["a"]) < len(ALLOWED_KINDS)


def test_the_schema_carries_the_constraint_per_segment() -> None:
    schema = _output_schema_for_batch(
        ["S000", "S001"],
        hard_kinds_by_id={"S000": ("dialogue",), "S001": ("narration", "thought")},
    )
    assert _branch(schema, "S000")["properties"]["kind"]["enum"] == ["dialogue"]
    assert _branch(schema, "S001")["properties"]["kind"]["enum"] == ["narration", "thought"]


def test_an_unconstrained_batch_keeps_the_flat_schema() -> None:
    """The branches cost 3.4x the schema size; they are only worth paying for a constraint."""
    schema = _output_schema_for_batch(["S000", "S001"])
    items = schema["properties"]["segments"]["items"]
    assert "oneOf" not in items
    assert items["properties"]["id"]["enum"] == ["S000", "S001"]


@pytest.mark.parametrize(
    "invalid",
    [
        {"S000": ()},
        {"S000": ("dialogue", "dialogue")},
        {"S000": ("shouting",)},
        {"S999": ("dialogue",)},
        {"S000": ["dialogue"]},
    ],
)
def test_an_invalid_constraint_is_refused_rather_than_shipped(invalid: dict) -> None:
    with pytest.raises(ValueError):
        _output_schema_for_batch(["S000", "S001"], hard_kinds_by_id=invalid)
