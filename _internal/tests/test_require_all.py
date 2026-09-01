"""A failing check must say which clause failed.

Four run failures in one sitting shared this shape: three or more conditions behind one
message, evidence held in memory rather than on disk, so the only way to learn which
condition broke was to run the whole analysis again. Each cost a full pass.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from ebook_reader.database import require_all


def test_it_passes_when_nothing_failed() -> None:
    require_all("never seen", ("a", False), ("b", False))


def test_it_names_the_single_failing_clause() -> None:
    with pytest.raises(RuntimeError) as caught:
        require_all("bound broke", ("a", False), ("b", True), ("c", False))
    assert "bound broke: b" == str(caught.value)


def test_it_names_every_failing_clause_in_order() -> None:
    with pytest.raises(RuntimeError) as caught:
        require_all("bound broke", ("a", True), ("b", False), ("c", True))
    assert "bound broke: a, c" == str(caught.value)


def test_context_is_appended_for_values_a_reader_cannot_recover() -> None:
    with pytest.raises(RuntimeError) as caught:
        require_all("bound broke", ("a", True), seed=42, deltas=["emotion"])
    message = str(caught.value)
    assert "bound broke: a" in message
    assert "deltas=['emotion']" in message
    assert "seed=42" in message


def test_context_is_ordered_so_the_message_is_stable() -> None:
    with pytest.raises(RuntimeError) as caught:
        require_all("x", ("a", True), zebra=1, alpha=2)
    assert str(caught.value).index("alpha=") < str(caught.value).index("zebra=")


def test_truthiness_counts_not_just_true() -> None:
    """Conditions are often expressions, not bools."""
    with pytest.raises(RuntimeError):
        require_all("x", ("a", ["something"]))
    require_all("x", ("a", []), ("b", 0), ("c", None))


def test_no_new_blind_compound_check_is_added() -> None:
    """70 existed when this was written; the count may fall, never rise."""
    source = Path("ebook_reader/database.py").read_text(encoding="utf-8")
    blind = 0
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.If) or not isinstance(node.test, ast.BoolOp):
            continue
        if len(node.test.values) < 3:
            continue
        if len(node.body) == 1 and isinstance(node.body[0], ast.Raise):
            blind += 1
    assert blind <= 69, (
        f"{blind} checks combine three or more conditions behind one message; "
        "use require_all so the failing clause is named"
    )
