"""Two pinned characters may not share a voice inside one chapter.

Batch 3 of book 2 produced five same-chapter collisions on 2026-09-15 and every one was pin
against pin: Verdi and Christopher both pinned to thanh_binh_f090 met in chapters 12 and 14,
Rhine and ORVARIT in 16, SMILE and SARD in 32, Camil and Nghe in 36. Shared pins arrived that
morning - pin_the_book_cast may now give one voice to two people who never met - and the new
batch is exactly where they meet.

The project ranks two people on one voice inside a chapter as the worse defect, so consistency
yields there: the pin of whoever speaks less in the batch is dropped and the allocator, which
already avoids same-chapter holders, gives them another variant.
"""
from __future__ import annotations

from ebook_reader.character_registry import _drop_pins_that_share_a_chapter

VOICE = "preset_thanh_binh_f090_p-04"
OTHER = "preset_thai_son_f100_p+00"


def _row(chapter: int, speaker: str):
    return {"chapter_id": chapter, "speaker": speaker}


def test_the_quieter_of_two_pins_in_one_chapter_loses_its_pin() -> None:
    said: list[str] = []
    rows = [_row(12, "Verdi")] * 5 + [_row(12, "Christopher")] * 2 + [_row(14, "Verdi")] * 3
    pins = {"VERDI": VOICE, "CHRISTOPHER": VOICE}

    kept = _drop_pins_that_share_a_chapter(rows, pins, said.append)

    assert kept == {"VERDI": VOICE}, kept
    assert any("CHRISTOPHER" in line and "chương [12]" in line for line in said), said


def test_two_pins_on_one_voice_that_never_meet_both_survive() -> None:
    rows = [_row(12, "Verdi")] * 5 + [_row(40, "Christopher")] * 9
    pins = {"VERDI": VOICE, "CHRISTOPHER": VOICE}

    kept = _drop_pins_that_share_a_chapter(rows, pins, lambda _m: None)

    assert kept == pins


def test_different_voices_in_one_chapter_are_untouched() -> None:
    rows = [_row(12, "Verdi")] * 5 + [_row(12, "Christopher")] * 9
    pins = {"VERDI": VOICE, "CHRISTOPHER": OTHER}

    assert _drop_pins_that_share_a_chapter(rows, pins, lambda _m: None) == pins


def test_a_silent_pinned_character_is_never_dropped() -> None:
    """Người im lặng trong lô này không va chạm với ai; pin của họ phải đi tiếp sang lô sau."""
    rows = [_row(12, "Verdi")] * 5
    pins = {"VERDI": VOICE, "CHRISTOPHER": VOICE}

    assert _drop_pins_that_share_a_chapter(rows, pins, lambda _m: None) == pins


def test_three_pins_on_one_voice_keep_the_two_who_do_not_meet() -> None:
    rows = (
        [_row(12, "Verdi")] * 10
        + [_row(12, "Christopher")] * 5
        + [_row(40, "Sard")] * 2
    )
    pins = {"VERDI": VOICE, "CHRISTOPHER": VOICE, "SARD": VOICE}

    kept = _drop_pins_that_share_a_chapter(rows, pins, lambda _m: None)

    assert kept == {"VERDI": VOICE, "SARD": VOICE}


def test_no_pins_is_a_no_op() -> None:
    assert _drop_pins_that_share_a_chapter([_row(1, "X")], {}, lambda _m: None) == {}
