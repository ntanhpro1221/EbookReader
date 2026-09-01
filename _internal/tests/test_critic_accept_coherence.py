"""One definition of "would the host accept this", used by both validators.

The acceptance and rejection validators each decided it, differently, and a candidate whose
only differences were emotion and intensity was accepted by one and refused by the other.
That killed a run at the same segment three times across two sittings.
"""

from __future__ import annotations

import inspect

from ebook_reader.database import (
    AFFECT_CUE_DISAGREEMENT_BLOCKS,
    INAUDIBLE_DELIVERY_FIELDS,
    ProjectDB,
    host_derived_accept,
    rejected_accept_flag_is_coherent,
)

INAUDIBLE = ["emotion:surprised->neutral", "intensity:2->1"]
AUDIBLE = ["kind:narration->dialogue"]


def test_inaudible_differences_do_not_block_acceptance() -> None:
    assert host_derived_accept([]) is True
    assert host_derived_accept(INAUDIBLE) is True


def test_an_audible_difference_does_block_acceptance() -> None:
    assert host_derived_accept(AUDIBLE) is False
    assert host_derived_accept(AUDIBLE + INAUDIBLE) is False


def test_the_inaudible_fields_are_the_ones_that_were_named() -> None:
    assert INAUDIBLE_DELIVERY_FIELDS == frozenset({"emotion", "intensity"})
    assert AFFECT_CUE_DISAGREEMENT_BLOCKS is False


def test_a_critic_may_accept_while_recording_inaudible_differences() -> None:
    """The shape that killed the run."""
    assert rejected_accept_flag_is_coherent(True, INAUDIBLE)


def test_a_critic_may_not_accept_over_an_audible_difference() -> None:
    assert not rejected_accept_flag_is_coherent(True, AUDIBLE)


def test_a_critic_may_reject_on_an_inaudible_difference_alone() -> None:
    """A real case with a test of its own; the first fix broke it."""
    assert rejected_accept_flag_is_coherent(False, ["emotion:neutral->sad"])


def test_a_rejection_must_have_something_to_reject_over() -> None:
    assert not rejected_accept_flag_is_coherent(False, [])


def test_a_missing_or_non_boolean_flag_is_never_coherent() -> None:
    for value in (None, "true", 1, 0):
        assert not rejected_accept_flag_is_coherent(value, INAUDIBLE)


def test_neither_validator_recomputes_acceptance_for_itself() -> None:
    """The whole point: there is nothing left to copy."""
    for method in (
        ProjectDB._validate_analysis_acceptance_evidence,
        ProjectDB._validate_analysis_rejection_evidence,
    ):
        source = inspect.getsource(method)
        assert "not raw_deltas" not in source, method.__name__
