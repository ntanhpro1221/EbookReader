"""Sổ cộng dồn đếm mỗi chương một lần, và đi theo chuỗi gieo.

Chuỗi lô sắp có project đúc lại giọng của từng chương (`lo03r_062` ...) đứng sau lô của chúng.
Bản đầu của `backfill` cộng mọi project trong chuỗi: năm chương đúc lại là năm chương đếm đôi,
và người được cộng thêm đúng là người đang bị cân với người khác để giữ giọng. Chương lấy theo
tiêu đề, project đứng sau thắng — cùng luật với `assemble_book.py`.
"""
from __future__ import annotations

from collections import Counter
from pathlib import Path

from ebook_reader.character_registry import build_registry_and_cast
from ebook_reader.config import build_settings
from ebook_reader.database import ProjectDB

from scripts.backfill_exposure import (
    backfill,
    copy_ledger,
    dialogue_lines_by_chapter,
    read_ledger,
)


def _project(root: Path, name: str, chapters: dict[str, list[tuple[str, str]]]) -> Path:
    folder = root / name
    folder.mkdir()
    db = ProjectDB(folder / "project.sqlite3")
    db.initialize_book(
        title=name,
        project_root=folder,
        settings={},
        settings_hash="settings",
        input_manifest_hash="manifest",
    )
    ids = db.ensure_chapters(
        [
            {
                "chapter_index": index,
                "title": title,
                "input_path": folder / f"{title}.txt",
                "input_sha256": f"src-{title}",
                "input_size": 1,
                "output_mp3": folder / f"{title}.mp3",
            }
            for index, title in enumerate(chapters, 1)
        ]
    )
    for chapter_id, (title, speakers) in zip(ids, chapters.items()):
        db.replace_chapter_segments(
            chapter_id,
            [
                {
                    "stable_id": f"{title}s{seq}",
                    "seq": seq,
                    "text": f"Câu {seq}.",
                    "text_sha256": f"{title}-{seq}",
                    "kind_hint": "dialogue",
                    "kind": "dialogue",
                    "speaker": speaker,
                    "gender": gender,
                    "confidence": 0.95,
                    "status": "analyzed",
                }
                for seq, (speaker, gender) in enumerate(speakers, 1)
            ],
        )
    build_registry_and_cast(db, build_settings(), lambda _message: None)
    return folder


def test_lines_are_counted_per_chapter_title(tmp_path: Path) -> None:
    batch = _project(
        tmp_path,
        "lo03",
        {"062": [("KANG", "male")] * 5 + [("SAMAEL", "male")] * 3, "063": [("KANG", "male")] * 2},
    )

    assert dialogue_lines_by_chapter(batch) == {
        "062": Counter({"KANG": 5, "SAMAEL": 3}),
        "063": Counter({"KANG": 2}),
    }


def test_a_recast_chapter_replaces_the_batch_copy_instead_of_adding_to_it(tmp_path: Path) -> None:
    batch = _project(
        tmp_path,
        "lo03",
        {"062": [("KANG", "male")] * 5 + [("SAMAEL", "male")] * 3, "063": [("KANG", "male")] * 2},
    )
    recast = _project(
        tmp_path,
        "lo03r_062",
        {"062": [("KANG", "male")] * 5 + [("SAMAEL", "male")] * 3},
    )

    ledger = backfill([batch, recast])

    assert ledger["KANG"] == (7, 2), "063 từ lô, 062 từ project đúc lại - không phải 12"
    assert ledger["SAMAEL"] == (3, 1), "chỉ còn trong chương thắng của project đúc lại"
    assert read_ledger(recast) == {"KANG": 7, "SAMAEL": 3}


def test_the_ledger_is_copied_along_the_seed_chain(tmp_path: Path) -> None:
    source = _project(tmp_path, "lo03r_086", {"086": [("SELNE", "female")] * 4})
    backfill([source])
    target = _project(tmp_path, "lo04", {"092": [("SELNE", "female")]})

    assert copy_ledger(source, target) == 1
    assert read_ledger(target) == {"SELNE": 4}

    without = _project(tmp_path, "nothing", {"001": [("X", "male")]})
    assert copy_ledger(without, target) == 0, "nguồn không có sổ thì không chạm đích"
    assert read_ledger(target) == {"SELNE": 4}
