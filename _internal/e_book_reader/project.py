from __future__ import annotations

from pathlib import Path
from typing import Any

from .config import load_settings, save_settings, settings_hash
from .database import ProjectDB
from .io_utils import slugify
from .models import ProjectPaths
from .text_processing import build_chapter_manifest, input_manifest_hash


def infer_book_title(input_files: list[Path]) -> str:
    paths = [path.resolve() for path in input_files]
    if len(paths) > 1:
        parents = {path.parent for path in paths}
        if len(parents) == 1 and next(iter(parents)).name:
            return next(iter(parents)).name
    return paths[0].stem if paths else "audiobook"


def create_or_open_project(
    input_files: list[Path],
    output_root: Path,
    requested_settings: dict[str, Any],
    title: str | None = None,
) -> tuple[ProjectPaths, ProjectDB, dict[str, Any]]:
    if not input_files:
        raise ValueError("At least one TXT file is required")
    output_root = output_root.expanduser().resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    manifest = build_chapter_manifest(input_files, output_root)
    manifest_hash = input_manifest_hash(manifest)
    book_title = (title or infer_book_title(input_files)).strip() or "audiobook"
    project_root = output_root / f"{slugify(book_title, 70)}_{manifest_hash[:10]}"
    paths = ProjectPaths.build(project_root)

    # Rebuild output paths now that the final project root is known.
    manifest = build_chapter_manifest(input_files, paths.chapters)
    manifest_hash = input_manifest_hash(manifest)
    if paths.settings.exists():
        settings = load_settings(paths.settings)
    else:
        settings = requested_settings
        save_settings(paths.settings, settings)

    db = ProjectDB(paths.db, synchronous=str(settings["safety"].get("sqlite_synchronous", "FULL")))
    db.initialize_book(
        title=book_title,
        project_root=project_root,
        settings=settings,
        settings_hash=settings_hash(settings),
        input_manifest_hash=manifest_hash,
    )
    db.ensure_chapters(manifest)
    return paths, db, settings
