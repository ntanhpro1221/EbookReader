"""Report which pinned dependencies, models and tools have newer releases.

Read-only. Queries PyPI and the GitHub releases API, plus the locally running
Ollama server when one is already up (it never starts one, so this cannot make
an Ollama tray icon appear). Nothing is installed or changed.

Upgrading any pinned dependency changes the quality-policy hash and therefore
requires a clean project. Treat every upgrade as a version event and record it
in `docs/VERSIONS.md`; see `docs/DEPENDENCIES.md` for the risk assessment.

Usage:
    python scripts/check_dependency_updates.py [--json out.json] [--offline]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.request
from importlib.metadata import PackageNotFoundError, version as installed_version
from pathlib import Path
from typing import Any


PYPROJECT = Path(__file__).resolve().parent.parent / "pyproject.toml"
PIN_PATTERN = re.compile(r'"([A-Za-z0-9_.\-]+)==([^"]+)"')
GITHUB_PROJECTS = {
    "ollama": "ollama/ollama",
    "openai-whisper": "openai/whisper",
    "utmosv2": "sarulab-speech/UTMOSv2",
    "vieneu": "pnnbao97/VieNeu-TTS",
}
REQUEST_TIMEOUT_SECONDS = 30


def _get_json(url: str, *, github: bool = False) -> Any:
    headers = {"User-Agent": "ebook-reader-dependency-audit"}
    if github:
        headers["Accept"] = "application/vnd.github+json"
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
        return json.load(response)


def read_pins() -> list[tuple[str, str]]:
    text = PYPROJECT.read_text(encoding="utf-8")
    return PIN_PATTERN.findall(text)


def local_version(name: str) -> str:
    try:
        return installed_version(name)
    except PackageNotFoundError:
        return "not installed"


def check_pypi(pins: list[tuple[str, str]], *, offline: bool) -> list[dict[str, Any]]:
    rows = []
    for name, pinned in pins:
        latest = "skipped" if offline else ""
        if not offline:
            try:
                latest = str(_get_json(f"https://pypi.org/pypi/{name}/json")["info"]["version"])
            except (urllib.error.URLError, KeyError, ValueError, TimeoutError) as exc:
                latest = f"unavailable ({exc.__class__.__name__})"
        rows.append(
            {
                "name": name,
                "pinned": pinned,
                "installed": local_version(name),
                "latest": latest,
                "outdated": bool(latest) and latest != pinned and " " not in latest,
            }
        )
    return rows


def check_github(*, offline: bool) -> list[dict[str, Any]]:
    rows = []
    for label, repository in GITHUB_PROJECTS.items():
        if offline:
            rows.append({"name": label, "repository": repository, "latest": "skipped"})
            continue
        latest = ""
        try:
            release = _get_json(
                f"https://api.github.com/repos/{repository}/releases/latest",
                github=True,
            )
            latest = f"{release['tag_name']} ({release['published_at'][:10]})"
        except (urllib.error.URLError, KeyError, ValueError, TimeoutError) as exc:
            latest = f"unavailable ({exc.__class__.__name__})"
        rows.append({"name": label, "repository": repository, "latest": latest})
    return rows


def check_ollama() -> dict[str, Any]:
    """Ask an already-running Ollama server about itself; never start one."""
    result: dict[str, Any] = {"running": False, "version": None, "models": []}
    try:
        result["version"] = str(_get_json("http://127.0.0.1:11434/api/version")["version"])
        result["running"] = True
    except (urllib.error.URLError, KeyError, ValueError, TimeoutError):
        return result
    try:
        tags = _get_json("http://127.0.0.1:11434/api/tags")
    except (urllib.error.URLError, ValueError, TimeoutError):
        return result
    result["models"] = [
        {
            "name": str(item.get("name", "")),
            "digest": str(item.get("digest", ""))[:16],
            "size_gb": round(float(item.get("size", 0)) / 1e9, 2),
        }
        for item in tags.get("models", [])
        if isinstance(item, dict)
    ]
    return result


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", dest="json_out", type=Path, default=None)
    parser.add_argument("--offline", action="store_true", help="Skip every network lookup")
    args = parser.parse_args()

    pypi = check_pypi(read_pins(), offline=args.offline)
    github = check_github(offline=args.offline)
    ollama = check_ollama()

    print(f"{'package':22s} {'pinned':16s} {'installed':16s} {'latest':16s}")
    print("-" * 74)
    for row in pypi:
        marker = " OUTDATED" if row["outdated"] else ""
        drift = " DRIFT" if row["installed"] not in {row["pinned"], f"{row['pinned']}+cu128"} else ""
        print(
            f"{row['name']:22s} {row['pinned']:16s} {row['installed']:16s} "
            f"{row['latest']:16s}{marker}{drift}"
        )

    print("\nUpstream projects")
    for row in github:
        print(f"  {row['name']:16s} {row['repository']:28s} {row['latest']}")

    print("\nOllama")
    if not ollama["running"]:
        print("  no server responding on 127.0.0.1:11434 (not started by this tool)")
    else:
        print(f"  server {ollama['version']}")
        for model in ollama["models"]:
            print(f"    {model['name']:16s} {model['size_gb']:5.2f} GB  {model['digest']}")

    outdated = [row["name"] for row in pypi if row["outdated"]]
    drifted = [
        row["name"]
        for row in pypi
        if row["installed"] not in {row["pinned"], f"{row['pinned']}+cu128", "not installed"}
    ]
    print(f"\n{len(outdated)} pinned package(s) behind PyPI: {', '.join(outdated) or 'none'}")
    if drifted:
        print(f"INSTALLED VERSION DRIFT from the pins: {', '.join(drifted)}")
    print("Upgrading changes the quality-policy hash; see docs/DEPENDENCIES.md before acting.")

    if args.json_out is not None:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(
            json.dumps(
                {"pypi": pypi, "github": github, "ollama": ollama},
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        print(f"JSON written to {args.json_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
