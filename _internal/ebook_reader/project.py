from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from .config import load_settings, save_settings, settings_hash
from .database import ProjectDB
from .io_utils import slugify
from .models import ProjectPaths
from .text_processing import build_chapter_manifest, input_manifest_hash


MAX_CREATION_LOCK_RETRIES = 3


class ProjectCreationLock:
    """Serialize creation of one title/manifest identity across GUI and CLI processes."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.handle: Any = None

    def __enter__(self) -> "ProjectCreationLock":
        self.acquire()
        return self

    def __exit__(self, _exc_type: Any, _exc: Any, _traceback: Any) -> None:
        self.release()

    def acquire(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.handle = self.path.open("a+b")
        self.handle.seek(0, os.SEEK_END)
        if self.handle.tell() == 0:
            self.handle.write(b"0")
            self.handle.flush()
        self.handle.seek(0)
        try:
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(self.handle.fileno(), msvcrt.LK_LOCK, 1)
            else:
                import fcntl

                fcntl.flock(self.handle.fileno(), fcntl.LOCK_EX)
        except (OSError, BlockingIOError):
            self.handle.close()
            self.handle = None
            raise

    def release(self) -> None:
        if self.handle is None:
            return
        try:
            self.handle.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(self.handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(self.handle.fileno(), fcntl.LOCK_UN)
        finally:
            self.handle.close()
            self.handle = None


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
    book_title = (title or infer_book_title(input_files)).strip() or "audiobook"
    requested_hash = settings_hash(requested_settings)
    for _attempt in range(MAX_CREATION_LOCK_RETRIES):
        initial_manifest = build_chapter_manifest(input_files, output_root)
        initial_manifest_hash = input_manifest_hash(initial_manifest)
        project_name = f"{slugify(book_title, 70)}_{initial_manifest_hash[:10]}"
        lock_path = output_root / ".ebook-reader-create-locks" / f"{project_name}.lock"
        with ProjectCreationLock(lock_path):
            # Sources can change while waiting for another creator. Re-evaluate the
            # identity under the lock and retry under the correct lock when needed.
            locked_manifest = build_chapter_manifest(input_files, output_root)
            manifest_hash = input_manifest_hash(locked_manifest)
            locked_project_name = f"{slugify(book_title, 70)}_{manifest_hash[:10]}"
            if locked_project_name != project_name:
                continue

            project_root = output_root / project_name
            paths = ProjectPaths.build(project_root)
            if paths.settings.exists() and settings_hash(load_settings(paths.settings)) != requested_hash:
                project_root = output_root / f"{project_name}_{requested_hash[:8]}"
                paths = ProjectPaths.build(project_root)

            manifest = [
                {
                    **row,
                    "output_mp3": str(
                        paths.chapters
                        / f"{int(row['chapter_index']):05d}_{slugify(Path(str(row['input_path'])).stem, 72)}.mp3"
                    ),
                }
                for row in locked_manifest
            ]
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
    raise RuntimeError("Input sources changed repeatedly while the project creation lock was acquired")
