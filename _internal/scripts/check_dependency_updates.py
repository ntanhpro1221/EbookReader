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
import time
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


def _supports_running_python(release_files: list[dict[str, Any]]) -> bool:
    """Whether any file in a release accepts the interpreter this project runs on."""
    from packaging.specifiers import InvalidSpecifier, SpecifierSet

    running = f"{sys.version_info.major}.{sys.version_info.minor}"
    saw_constraint = False
    for item in release_files:
        if item.get("yanked"):
            continue
        requires = item.get("requires_python") or ""
        if not requires:
            return True
        saw_constraint = True
        try:
            if SpecifierSet(requires).contains(running, prereleases=True):
                return True
        except InvalidSpecifier:
            return True
    return not saw_constraint


def _latest_installable(name: str) -> tuple[str, str]:
    """Return the newest release this interpreter can install, and the newest overall.

    Reporting only the newest overall is how this tool told me numpy 2.5.2 was available
    when it requires Python 3.12 and the project runs 3.11 - the upgrade then failed at
    resolution after the version had already been written into pyproject.toml. A version
    that cannot be installed is not an update.
    """
    from packaging.version import InvalidVersion, Version

    data = _get_json(f"https://pypi.org/pypi/{name}/json")
    newest_overall = str(data["info"]["version"])
    candidates = []
    for raw, files in (data.get("releases") or {}).items():
        if not files or not _supports_running_python(list(files)):
            continue
        try:
            parsed = Version(raw)
        except InvalidVersion:
            continue
        if parsed.is_prerelease:
            continue
        candidates.append((parsed, raw))
    if not candidates:
        return newest_overall, newest_overall
    return max(candidates)[1], newest_overall


def check_pypi(pins: list[tuple[str, str]], *, offline: bool) -> list[dict[str, Any]]:
    rows = []
    for name, pinned in pins:
        latest = "skipped" if offline else ""
        newest_overall = latest
        if not offline:
            try:
                latest, newest_overall = _latest_installable(name)
            except (urllib.error.URLError, KeyError, ValueError, TimeoutError) as exc:
                latest = f"unavailable ({exc.__class__.__name__})"
                newest_overall = latest
        rows.append(
            {
                "name": name,
                "pinned": pinned,
                "installed": local_version(name),
                "latest": latest,
                "newest_overall": newest_overall,
                "blocked_by_python": (
                    bool(latest)
                    and " " not in latest
                    and newest_overall != latest
                ),
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


# ---------------------------------------------------------------------------------------------
# Thêm ngày 2026-09-17. Bản trên chỉ hỏi PyPI và "release mới nhất" trên GitHub, và nó đã không
# được chạy từ 30-08: chủ sách phải tự hỏi "vietneu có bản mới chưa?". Khi chạy lại thì thấy nó mù
# đúng những chỗ đáng giá nhất:
#   - `vieneu` trên GitHub: "latest release" là bản APP desktop (`app-v0.18.2`), không phải SDK;
#     tag SDK là `vX.Y.Z`.
#   - torch: "installable" theo PyPI là 2.14.0, nhưng bản CUDA cho Windows cp311 thì tuỳ biến thể
#     CUDA (cu128 dừng ở 2.11.0, cu130 có 2.14.0), và biến thể nào dùng được là do DRIVER quyết.
#   - model Hugging Face đã ghim revision: không ai hỏi `main` đã đi tới đâu, file nào đổi.
#   - model Ollama: không hỏi tag có bị đẩy lại không, cũng không hỏi có thế hệ mới vừa VRAM không.
#   - UTMOSv2 ghim theo commit git: không hỏi nhánh chính đã đi trước bao nhiêu commit.
# ---------------------------------------------------------------------------------------------
TORCH_FAMILY = ("torch", "torchaudio", "torchvision")
HF_PINNED_MODELS = {
    # repo -> hằng số revision trong ebook_reader.runtime_contract (None = không ghim ở đó)
    "pnnbao-ump/VieNeu-TTS-v3-Turbo": "VIENEU_CACHE_REVISION",
    "facebook/wav2vec2-base": "WAV2VEC2_CACHE_REVISION",
    "timm/tf_efficientnetv2_s.in21k_ft_in1k": "TIMM_CACHE_REVISION",
    "mobiuslabsgmbh/faster-whisper-large-v3-turbo": None,
}
GIT_PINS = {"utmosv2": ("sarulab-speech/UTMOSv2", r"UTMOSv2\.git@([0-9a-f]{40})")}
OLLAMA_CONFIGURED_MODELS = ("qwen3:8b", "qwen3:4b")
VRAM_BUDGET_GB = 7.5


def _get_text(url: str, headers: dict[str, str] | None = None) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": "ebook-reader-dependency-audit", **(headers or {})})
    with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
        return response.read().decode("utf-8", "replace")


def driver_cuda() -> tuple[str, str]:
    """(phiên bản driver, CUDA cao nhất driver ấy chạy được) theo `nvidia-smi`; rỗng nếu không có."""
    import subprocess

    try:
        out = subprocess.run(["nvidia-smi"], capture_output=True, text=True, timeout=20).stdout
    except (OSError, subprocess.SubprocessError):
        return "", ""
    driver = re.search(r"Driver Version:\s*([0-9.]+)", out)
    cuda = re.search(r"CUDA Version:\s*([0-9.]+)", out)
    return (driver.group(1) if driver else ""), (cuda.group(1) if cuda else "")


def check_torch_cuda(*, offline: bool) -> list[dict[str, Any]]:
    """Bản mới nhất của torch/torchaudio/torchvision cho Windows + Python đang chạy, THEO biến thể CUDA."""
    if offline:
        return []
    tag = f"cp{sys.version_info.major}{sys.version_info.minor}"
    rows = []
    for package in TORCH_FAMILY:
        for variant in ("cu126", "cu128", "cu129", "cu130", "cu131"):
            try:
                html = _get_text(f"https://download.pytorch.org/whl/{variant}/{package}/")
            except (urllib.error.URLError, TimeoutError, ValueError):
                continue
            found = set(re.findall(rf"{package}-([0-9.]+)%2B{variant}-{tag}-{tag}-win_amd64", html))
            if found:
                newest = max(found, key=lambda v: [int(x) for x in v.split(".")])
                rows.append({"package": package, "variant": variant, "newest": newest})
    return rows


def check_hf_models(*, offline: bool) -> list[dict[str, Any]]:
    """Revision đang ghim so với `main`, và file nào khác nhau giữa hai bên."""
    if offline:
        return []
    try:
        sys.path.insert(0, str(PYPROJECT.parent))
        from ebook_reader import runtime_contract
    except Exception:  # noqa: BLE001
        runtime_contract = None
    rows = []
    for repo, constant in HF_PINNED_MODELS.items():
        pinned = str(getattr(runtime_contract, constant, "")) if (runtime_contract and constant) else ""
        row: dict[str, Any] = {"repo": repo, "pinned": pinned[:12], "main": "", "changed_files": []}
        try:
            info = _get_json(f"https://huggingface.co/api/models/{repo}")
            row["main"] = str(info.get("sha", ""))[:12]
            row["last_modified"] = str(info.get("lastModified", ""))[:10]
            if pinned and not str(info.get("sha", "")).startswith(pinned):
                def tree(rev: str) -> dict[str, str]:
                    items = _get_json(f"https://huggingface.co/api/models/{repo}/tree/{rev}?recursive=true")
                    return {
                        i["path"]: str((i.get("lfs") or {}).get("oid") or i.get("oid"))
                        for i in items
                        if i.get("type") == "file"
                    }

                old, new = tree(pinned), tree("main")
                row["changed_files"] = sorted(p for p in set(old) | set(new) if old.get(p) != new.get(p))
        except (urllib.error.URLError, KeyError, ValueError, TimeoutError) as exc:
            row["main"] = f"unavailable ({exc.__class__.__name__})"
        rows.append(row)
    return rows


def check_git_pins(*, offline: bool) -> list[dict[str, Any]]:
    if offline:
        return []
    text = PYPROJECT.read_text(encoding="utf-8")
    rows = []
    for name, (repo, pattern) in GIT_PINS.items():
        match = re.search(pattern, text)
        if not match:
            continue
        pinned = match.group(1)
        try:
            data = _get_json(f"https://api.github.com/repos/{repo}/compare/{pinned}...HEAD", github=True)
            rows.append({"name": name, "repo": repo, "pinned": pinned[:12], "status": data.get("status"),
                         "ahead_by": data.get("ahead_by")})
        except (urllib.error.URLError, KeyError, ValueError, TimeoutError) as exc:
            rows.append({"name": name, "repo": repo, "pinned": pinned[:12], "status": f"unavailable ({exc.__class__.__name__})"})
    return rows


def check_vieneu_sdk_tag(*, offline: bool) -> str:
    """Tag SDK mới nhất (`vX.Y.Z`); `releases/latest` của repo trả bản app desktop."""
    if offline:
        return "skipped"
    try:
        tags = _get_json("https://api.github.com/repos/pnnbao97/VieNeu-TTS/tags?per_page=50", github=True)
        sdk = [t["name"] for t in tags if re.fullmatch(r"v\d+\.\d+\.\d+", str(t.get("name", "")))]
        return max(sdk, key=lambda v: [int(x) for x in v[1:].split(".")]) if sdk else "none"
    except (urllib.error.URLError, KeyError, ValueError, TimeoutError) as exc:
        return f"unavailable ({exc.__class__.__name__})"


def check_ollama_models(*, offline: bool) -> list[dict[str, Any]]:
    """Tag đang dùng có bị đẩy lại trên registry không, đọc manifest trên đĩa - không cần server chạy."""
    import hashlib
    import os

    if offline:
        return []
    home = Path(os.environ.get("OLLAMA_MODELS", Path.home() / ".ollama" / "models"))
    rows = []
    for model in OLLAMA_CONFIGURED_MODELS:
        name, _, tag = model.partition(":")
        local = home / "manifests" / "registry.ollama.ai" / "library" / name / (tag or "latest")
        local_digest = hashlib.sha256(local.read_bytes()).hexdigest()[:12] if local.is_file() else "not pulled"
        try:
            remote = urllib.request.urlopen(
                urllib.request.Request(
                    f"https://registry.ollama.ai/v2/library/{name}/manifests/{tag or 'latest'}",
                    headers={"User-Agent": "x", "Accept": "application/vnd.docker.distribution.manifest.v2+json"},
                ),
                timeout=REQUEST_TIMEOUT_SECONDS,
            ).read()
            remote_digest = hashlib.sha256(remote).hexdigest()[:12]
        except (urllib.error.URLError, TimeoutError, ValueError) as exc:
            remote_digest = f"unavailable ({exc.__class__.__name__})"
        rows.append({"model": model, "local": local_digest, "registry": remote_digest,
                     "retagged": local_digest != remote_digest and "unavailable" not in remote_digest})
    return rows


def newer_llm_families(*, offline: bool, prefixes: tuple[str, ...] = ("qwen", "gemma")) -> list[dict[str, Any]]:
    """Họ model mới trên thư viện Ollama có bản vừa `VRAM_BUDGET_GB` - ỨNG VIÊN để đo, không phải để thay."""
    if offline:
        return []
    try:
        html = _get_text("https://ollama.com/library?sort=newest")
    except (urllib.error.URLError, TimeoutError, ValueError):
        return []
    families: list[str] = []
    for found in re.findall(r'href="/library/([a-z0-9.\-]+)"', html):
        if found.startswith(prefixes) and found not in families and not re.search(r"coder|embedding|vl|ocr|med", found):
            families.append(found)
    rows = []
    for family in families[:8]:
        try:
            page = _get_text(f"https://ollama.com/library/{family}/tags")
        except (urllib.error.URLError, TimeoutError, ValueError):
            continue
        fits = sorted(
            {
                (tag, size)
                for tag, size in re.findall(rf"{re.escape(family)}:([a-z0-9.\-_]+)</a>.*?(\d+(?:\.\d+)?)\s*GB", page, flags=re.S)
                if float(size) <= VRAM_BUDGET_GB and not re.search(r"mlx|bf16|fp8|nvfp4|cloud", tag)
            },
            key=lambda item: -float(item[1]),
        )
        if fits:
            rows.append({"family": family, "fits_vram": [f"{t} ({s} GB)" for t, s in fits[:4]]})
    return rows


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", dest="json_out", type=Path, default=None)
    parser.add_argument("--offline", action="store_true", help="Skip every network lookup")
    args = parser.parse_args()

    pypi = check_pypi(read_pins(), offline=args.offline)
    github = check_github(offline=args.offline)
    ollama = check_ollama()
    driver, driver_cuda_version = driver_cuda()
    torch_cuda = check_torch_cuda(offline=args.offline)
    hf_models = check_hf_models(offline=args.offline)
    git_pins = check_git_pins(offline=args.offline)
    vieneu_sdk = check_vieneu_sdk_tag(offline=args.offline)
    ollama_models = check_ollama_models(offline=args.offline)
    llm_families = newer_llm_families(offline=args.offline)

    running = f"{sys.version_info.major}.{sys.version_info.minor}"
    print(
        f"{'package':22s} {'pinned':16s} {'installed':16s} "
        f"{'installable':16s} (newest that runs on Python {running})"
    )
    print("-" * 86)
    for row in pypi:
        marker = " OUTDATED" if row["outdated"] else ""
        drift = " DRIFT" if row["installed"] not in {row["pinned"], f"{row['pinned']}+cu128"} else ""
        held = (
            f"  [PyPI has {row['newest_overall']}, needs a newer Python]"
            if row.get("blocked_by_python")
            else ""
        )
        print(
            f"{row['name']:22s} {row['pinned']:16s} {row['installed']:16s} "
            f"{row['latest']:16s}{marker}{drift}{held}"
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

    print(f"\nVieNeu SDK tag moi nhat: {vieneu_sdk}")

    print(f"\nGPU driver {driver or '?'} (chay duoc CUDA toi {driver_cuda_version or '?'}); ban Windows {sys.version_info.major}.{sys.version_info.minor}:")
    for package in TORCH_FAMILY:
        mine = [f"{r['variant']}={r['newest']}" for r in torch_cuda if r["package"] == package]
        print(f"  {package:12s} {'  '.join(mine) or '(khong doc duoc index)'}  | dang cai {local_version(package)}")

    print("\nModel Hugging Face (ghim so voi main)")
    for row in hf_models:
        state = "trung main" if row["pinned"] and row["main"].startswith(row["pinned"][:12]) else (
            f"main da doi {len(row['changed_files'])} file: {', '.join(row['changed_files'][:6])}" if row["pinned"] else f"khong ghim; main {row['main']} ({row.get('last_modified', '')})"
        )
        print(f"  {row['repo']:46s} {state}")

    print("\nGhim theo commit git")
    for row in git_pins:
        print(f"  {row['name']:10s} {row['repo']:28s} {row['pinned']} -> {row['status']} (di truoc {row.get('ahead_by')})")

    print("\nModel Ollama dang dung (manifest tren dia so voi registry)")
    for row in ollama_models:
        print(f"  {row['model']:12s} local {row['local']} registry {row['registry']}{'  TAG DA BI DAY LAI' if row['retagged'] else ''}")
    if llm_families:
        print(f"  ho model moi vua {VRAM_BUDGET_GB} GB VRAM (ung vien de DO, khong phai de thay):")
        for row in llm_families:
            print(f"    {row['family']:22s} {', '.join(row['fits_vram'])}")

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

    # Luôn để lại một dấu vết có giờ, để `heartbeat_tick.py` biết lần kiểm cuối cách đây bao lâu.
    # Công cụ này từng nằm im 18 ngày (30-08 → 17-09) trong khi VieNeu ra 16 bản; một nhắc nhở
    # xuất hiện ở MỌI nhịp tim thì không quên được.
    if not args.offline:
        audit = PYPROJECT.parent / "runtime" / "dependency_audit.json"
        try:
            audit.parent.mkdir(parents=True, exist_ok=True)
            audit.write_text(
                json.dumps(
                    {
                        "checked_at": time.time(),
                        "outdated_packages": outdated,
                        "drifted_packages": drifted,
                        "vieneu_sdk": vieneu_sdk,
                        "retagged_ollama_models": [r["model"] for r in ollama_models if r["retagged"]],
                        "hf_models_behind_main": [r["repo"] for r in hf_models if r["changed_files"]],
                        "git_pins_behind": [r["name"] for r in git_pins if r.get("ahead_by")],
                        "llm_candidates": [r["family"] for r in llm_families],
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
        except OSError as exc:
            print(f"(khong ghi duoc {audit}: {exc})")

    if args.json_out is not None:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(
            json.dumps(
                {"pypi": pypi, "github": github, "ollama": ollama, "driver": driver,
                 "driver_cuda": driver_cuda_version, "torch_cuda": torch_cuda, "hf_models": hf_models,
                 "git_pins": git_pins, "vieneu_sdk": vieneu_sdk, "ollama_models": ollama_models,
                 "llm_families": llm_families},
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        print(f"JSON written to {args.json_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
