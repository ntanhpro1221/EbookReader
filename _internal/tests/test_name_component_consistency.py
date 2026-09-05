"""One character must not have two readings because their name appeared in two surfaces.

Readings are proposed per surface and validated per surface, so nothing compared
"Theosbane" with the "Theosbane" inside "Samael Kaizer Theosbane". alpha.47 locked both:
`theo-bên` in the full names, `Thê-ô-ban` alone. The owner had asked twice for theo-bên.

_local_name_fallback's docstring names this exact defect - "two readings of one name in one
book" - as the reason its whole route exists. It arrived through a door nobody was watching.
"""
from __future__ import annotations

from ebook_reader.analysis import name_component_corrections


def test_the_alpha47_case() -> None:
    """The real rows, from the real run."""
    corrections = name_component_corrections({
        "Theosbane": "Thê-ô-ban",
        "Arthur Kaizer Theosbane": "A-thờ cai-dờ theo-bên",
        "Samael Kaizer Theosbane": "Xa-men cai-dờ theo-bên",
    })

    assert corrections == {"Theosbane": "theo-bên"}


def test_agreement_produces_no_correction() -> None:
    """The normal case, and it must stay silent rather than churn locked rows."""
    assert name_component_corrections({
        "Theosbane": "theo-bên",
        "Samael Kaizer Theosbane": "Xa-men cai-dờ theo-bên",
    }) == {}


def test_case_alone_is_not_a_second_reading() -> None:
    """A name capitalised at the start of a phrase and lowercase inside one is one reading."""
    assert name_component_corrections({
        "Blade": "Bờ-lết",
        "Elijah Blade": "E-lai-gia bờ-lết",
    }) == {}


def test_a_reading_that_cannot_be_aligned_is_left_alone() -> None:
    """Three words against two groups: the component boundary is a guess, so don't."""
    assert name_component_corrections({
        "Theosbane": "Thê-ô-ban",
        "Samael Kaizer Theosbane": "Xa-men theo-bên",
    }) == {}


def test_a_component_with_no_standalone_entry_is_ignored() -> None:
    """Nothing to reconcile, and inventing a row here would lock a name nobody asked for."""
    assert name_component_corrections({
        "Samael Kaizer Theosbane": "Xa-men cai-dờ theo-bên",
    }) == {}


def test_every_disagreeing_component_is_reported() -> None:
    corrections = name_component_corrections({
        "Kaizer": "cai-dơ",
        "Theosbane": "Thê-ô-ban",
        "Samael Kaizer Theosbane": "Xa-men cai-dờ theo-bên",
    })

    assert corrections == {"Kaizer": "cai-dờ", "Theosbane": "theo-bên"}


def test_an_empty_table_is_not_an_error() -> None:
    assert name_component_corrections({}) == {}
