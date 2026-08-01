from __future__ import annotations

import hashlib
import sys
from pathlib import Path


INTERNAL_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = INTERNAL_ROOT.parent
MANIFEST_PATH = INTERNAL_ROOT / "SOURCE_MANIFEST.sha256"
IGNORED_DIRECTORY_NAMES = {".git", ".pytest_cache", ".ruff_cache", "__pycache__", "runtime"}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    failures: list[str] = []
    tracked: set[str] = set()
    for line_number, raw_line in enumerate(MANIFEST_PATH.read_text(encoding="utf-8").splitlines(), 1):
        line = raw_line.strip()
        if not line:
            continue
        try:
            expected, relative = line.split(maxsplit=1)
        except ValueError:
            failures.append(f"line {line_number}: invalid manifest entry")
            continue
        relative = relative.removeprefix("./")
        tracked.add(Path(relative).as_posix())
        target = (PROJECT_ROOT / relative).resolve()
        try:
            target.relative_to(PROJECT_ROOT)
        except ValueError:
            failures.append(f"line {line_number}: path escapes project root")
            continue
        if not target.is_file():
            failures.append(f"missing: {relative}")
        elif sha256_file(target) != expected.casefold():
            failures.append(f"checksum mismatch: {relative}")

    for target in PROJECT_ROOT.rglob("*"):
        if not target.is_file() or target == MANIFEST_PATH:
            continue
        relative_path = target.relative_to(PROJECT_ROOT)
        if any(part in IGNORED_DIRECTORY_NAMES for part in relative_path.parts):
            continue
        relative = relative_path.as_posix()
        if relative not in tracked:
            failures.append(f"unlisted source file: {relative}")

    if failures:
        print("Source integrity check failed:", file=sys.stderr)
        for failure in failures[:20]:
            print(f"- {failure}", file=sys.stderr)
        return 1
    print("Source manifest: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
