from __future__ import annotations

from pathlib import Path

from ebook_reader.config import build_settings
from ebook_reader.database import ProjectDB
from ebook_reader.models import (
    CONTEXTUAL_ENGLISH_NAME_PRONUNCIATION_SOURCE,
    ENGLISH_NAME_PRONUNCIATION_SOURCE,
)
from ebook_reader.tts import (
    PRONUNCIATION_DELIVERY_SOURCE,
    TTSCoordinator,
)


def _coordinator(tmp_path: Path) -> tuple[ProjectDB, TTSCoordinator]:
    db = ProjectDB(tmp_path / "project.sqlite3")
    return db, TTSCoordinator(build_settings(), db, lambda _message: None)


def test_spoken_text_traces_only_applied_locked_english_name_pronunciations(
    tmp_path: Path,
) -> None:
    db, coordinator = _coordinator(tmp_path)
    db.upsert_pronunciation(
        surface="Lucien",
        normalized_surface="lucien",
        spoken_form="Lu-si-en",
        confidence=0.95,
        source=ENGLISH_NAME_PRONUNCIATION_SOURCE,
        locked=True,
    )
    db.upsert_pronunciation(
        surface="May",
        normalized_surface="may",
        spoken_form="Mây",
        confidence=0.95,
        source=CONTEXTUAL_ENGLISH_NAME_PRONUNCIATION_SOURCE,
        locked=True,
    )
    db.upsert_pronunciation(
        surface="Edelweiss",
        normalized_surface="edelweiss",
        spoken_form="Ê đen vai",
        confidence=0.95,
        source="analysis",
        locked=True,
    )
    db.upsert_pronunciation(
        surface="Gary",
        normalized_surface="gary",
        spoken_form="Ga-ri",
        confidence=0.95,
        source=ENGLISH_NAME_PRONUNCIATION_SOURCE,
        locked=False,
    )
    source_text = "Lucien gặp May; lucien, may, Edelweiss và Gary."

    spoken_text, anchors = coordinator.spoken_text_with_anchors({"text": source_text})

    assert spoken_text == "Lu-si-en gặp Mây; Lu-si-en, may, Ê đen vai và Ga-ri."
    assert coordinator.spoken_text({"text": source_text}) == spoken_text
    assert [anchor["matched_surface"] for anchor in anchors] == [
        "Lucien",
        "May",
        "lucien",
    ]
    assert [anchor["spoken_form"] for anchor in anchors] == [
        "Lu-si-en",
        "Mây",
        "Lu-si-en",
    ]
    assert [anchor["source"] for anchor in anchors] == [
        ENGLISH_NAME_PRONUNCIATION_SOURCE,
        CONTEXTUAL_ENGLISH_NAME_PRONUNCIATION_SOURCE,
        ENGLISH_NAME_PRONUNCIATION_SOURCE,
    ]
    assert [anchor["order"] for anchor in anchors] == [1, 2, 3]
    assert [anchor["occurrence"] for anchor in anchors] == [1, 1, 2]
    assert all(
        source_text[anchor["source_start"] : anchor["source_end"]]
        == anchor["matched_surface"]
        for anchor in anchors
    )
    assert all(anchor["pronunciation_id"] > 0 for anchor in anchors)
    assert [
        spoken_text[anchor["spoken_start"] : anchor["spoken_end"]]
        for anchor in anchors
    ] == ["Lu-si-en", "Mây", "Lu-si-en"]
    assert [anchor["surface"] for anchor in anchors] == ["Lucien", "May", "Lucien"]
    assert [anchor["normalized_surface"] for anchor in anchors] == [
        "lucien",
        "may",
        "lucien",
    ]


def test_spoken_text_anchor_trace_does_not_mutate_source_or_infer_absent_names(
    tmp_path: Path,
) -> None:
    db, coordinator = _coordinator(tmp_path)
    db.upsert_pronunciation(
        surface="Michael",
        normalized_surface="michael",
        spoken_form="Mai-cồ",
        confidence=0.95,
        source=ENGLISH_NAME_PRONUNCIATION_SOURCE,
        locked=True,
    )
    db.upsert_pronunciation(
        surface="Wolf",
        normalized_surface="wolf",
        spoken_form="Uôn",
        confidence=0.95,
        source=ENGLISH_NAME_PRONUNCIATION_SOURCE,
        locked=True,
    )
    row = {"text": "[thở dài] Michael đã đi."}

    spoken_text, anchors = coordinator.spoken_text_with_anchors(row)

    assert spoken_text == "Hầy... Mai-cồ đã đi."
    assert row == {"text": "[thở dài] Michael đã đi."}
    assert [anchor["matched_surface"] for anchor in anchors] == ["Michael"]
    assert anchors[0]["source_start"] == row["text"].index("Michael")
    assert anchors[0]["source_end"] == anchors[0]["source_start"] + len("Michael")


def test_source_spelling_variant_preserves_every_locked_name_occurrence_and_anchor(
    tmp_path: Path,
) -> None:
    db, coordinator = _coordinator(tmp_path)
    db.upsert_pronunciation(
        surface="Tracy",
        normalized_surface="tracy",
        spoken_form="Trây-si",
        confidence=0.98,
        source=ENGLISH_NAME_PRONUNCIATION_SOURCE,
        locked=True,
    )
    db.upsert_pronunciation(
        surface="Gary",
        normalized_surface="gary",
        spoken_form="Ga-ri",
        confidence=0.98,
        source=ENGLISH_NAME_PRONUNCIATION_SOURCE,
        locked=False,
    )
    db.upsert_pronunciation(
        surface="Edelweiss",
        normalized_surface="edelweiss",
        spoken_form="Ê đen vai",
        confidence=0.98,
        source="analysis",
        locked=True,
    )
    row = {"text": "Tracy gọi Tracy, Gary và Edelweiss."}

    spoken_text, anchors = coordinator.spoken_text_with_anchors(
        row,
        pronunciation_delivery_variant=PRONUNCIATION_DELIVERY_SOURCE,
    )

    assert spoken_text == "Tracy gọi Tracy, Ga-ri và Ê đen vai."
    assert [anchor["matched_surface"] for anchor in anchors] == ["Tracy", "Tracy"]
    assert [anchor["spoken_form"] for anchor in anchors] == ["Tracy", "Tracy"]
    assert [anchor["canonical_spoken_form"] for anchor in anchors] == [
        "Trây-si",
        "Trây-si",
    ]
    assert [anchor["occurrence"] for anchor in anchors] == [1, 2]
    assert all(
        anchor["pronunciation_delivery_variant"] == PRONUNCIATION_DELIVERY_SOURCE
        for anchor in anchors
    )
    assert [
        spoken_text[anchor["spoken_start"] : anchor["spoken_end"]]
        for anchor in anchors
    ] == ["Tracy", "Tracy"]


def test_unchanged_locked_pronunciation_is_not_reported_as_an_applied_anchor(
    tmp_path: Path,
) -> None:
    db, coordinator = _coordinator(tmp_path)
    db.upsert_pronunciation(
        surface="Iven",
        normalized_surface="iven",
        spoken_form="Iven",
        confidence=0.95,
        source=ENGLISH_NAME_PRONUNCIATION_SOURCE,
        locked=True,
    )

    spoken_text, anchors = coordinator.spoken_text_with_anchors(
        {"text": "Iven chưa gọi Lucien."}
    )

    assert spoken_text == "Iven chưa gọi Lucien."
    assert anchors == []


def test_contextual_anchor_span_selects_the_replaced_identical_spoken_form(
    tmp_path: Path,
) -> None:
    db, coordinator = _coordinator(tmp_path)
    db.upsert_pronunciation(
        surface="May",
        normalized_surface="may",
        spoken_form="Mây",
        confidence=0.95,
        source=CONTEXTUAL_ENGLISH_NAME_PRONUNCIATION_SOURCE,
        locked=True,
    )

    spoken_text, anchors = coordinator.spoken_text_with_anchors(
        {"text": "Mây rồi May"}
    )

    assert spoken_text == "Mây rồi Mây"
    assert len(anchors) == 1
    anchor = anchors[0]
    assert anchor["spoken_start"] == spoken_text.rindex("Mây")
    assert anchor["spoken_end"] == len(spoken_text)
    assert spoken_text[anchor["spoken_start"] : anchor["spoken_end"]] == "Mây"


def test_contextual_anchor_span_survives_vocalization_expansion_before_it(
    tmp_path: Path,
) -> None:
    db, coordinator = _coordinator(tmp_path)
    db.upsert_pronunciation(
        surface="May",
        normalized_surface="may",
        spoken_form="Mây",
        confidence=0.95,
        source=CONTEXTUAL_ENGLISH_NAME_PRONUNCIATION_SOURCE,
        locked=True,
    )

    spoken_text, anchors = coordinator.spoken_text_with_anchors(
        {"text": "[thở dài] Mây rồi May"}
    )

    assert spoken_text == "Hầy... Mây rồi Mây"
    assert len(anchors) == 1
    anchor = anchors[0]
    assert anchor["spoken_start"] == spoken_text.rindex("Mây")
    assert anchor["spoken_end"] == len(spoken_text)
    assert spoken_text[anchor["spoken_start"] : anchor["spoken_end"]] == "Mây"
