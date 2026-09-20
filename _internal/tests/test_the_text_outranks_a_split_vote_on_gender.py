"""Model chia phiếu về giới tính thì văn bản quyết, model nhất trí thì model quyết."""
from __future__ import annotations

from ebook_reader.character_registry import resolve_gender


def row(speaker: str, gender: str, text: str = "") -> dict[str, str]:
    return {"speaker": speaker, "gender": gender, "text": text}


def test_a_split_vote_loses_to_decisive_text() -> None:
    ident = [row("NEESHKA", "female"), row("NEESHKA", "female"), row("NEESHKA", "male")]
    text = [row("NARRATOR", "unknown", "Ông Neeshka hỏi. Ông ấy nhìn quanh. Neeshka và những quý ông khác đáp lời ông. "
                                       "Lão Neeshka gật đầu, ông cụ mỉm cười.")]
    gender, why = resolve_gender(ident, [*ident, *text])
    assert gender == "male", why
    assert why.startswith("text:")


def test_a_unanimous_vote_keeps_its_answer() -> None:
    # MILINA: model nhất trí nữ, quanh tên toàn chữ chỉ nam vì cô ngồi giữa một hội đồng đàn ông.
    ident = [row("MILINA", "female") for _ in range(4)]
    text = [row("NARRATOR", "unknown", "Ngài Neeshka, ngài Evans và ông Levski quay sang cô Milina.")]
    gender, why = resolve_gender(ident, [*ident, *text])
    assert gender == "female", why
    assert why == "model"


def test_a_split_vote_with_no_evidence_falls_back_to_the_majority() -> None:
    ident = [row("X", "female"), row("X", "female"), row("X", "male")]
    gender, why = resolve_gender(ident, ident)
    assert (gender, why) == ("female", "model_majority")


def test_a_pinned_answer_still_outranks_everything() -> None:
    ident = [row("NEESHKA", "female")]
    text = [row("NARRATOR", "unknown", "Ông Neeshka, ông ấy, quý ông, ông, lão Neeshka, ông ta, cậu ta.")]
    assert resolve_gender(ident, [*ident, *text], {"NEESHKA": "female"}) == ("female", "listener")
