from __future__ import annotations

import hashlib
import importlib
import importlib.metadata
import json
import os
from pathlib import Path
from typing import Any, Iterable


SETUP_SCHEMA_VERSION = 2
PERCEPTUAL_CACHE_SCHEMA_VERSION = 1
PERCEPTUAL_CACHE_MARKER_FILENAME = "cache_ready_v1.json"
UTMOS_CHECKPOINT_FILENAME = "fold0_s42_best_model.pth"
UTMOS_CHECKPOINT_REVISION = "506474f2b33dc77c234d668cc419be1861899cad"
UTMOS_CHECKPOINT_SHA256 = "c8149d988e4bbf3f347e6966b5d769de347a5f8c59ffca1dc4bd4bf5b8585e57"
UTMOS_SOURCE_COMMIT = "cc2700db57bb83ee13dc31ebe1b868c254e15d09"
UTMOS_SOURCE_URL = "https://github.com/sarulab-speech/UTMOSv2.git"
WAV2VEC2_CACHE_REPOSITORY = "models--facebook--wav2vec2-base"
WAV2VEC2_CACHE_REVISION = "0b5b8e868dd84f03fd87d01f9c4ff0f080fecfe8"
TIMM_CACHE_REPOSITORY = "models--timm--tf_efficientnetv2_s.in21k_ft_in1k"
TIMM_CACHE_REVISION = "ea9abc143ea2b9d8e1ec1de277bce02149b9cf0e"
UTMOS_MODEL_CONFIG = "fusion_stage3"
UTMOS_MODEL_FOLD = 0
UTMOS_MODEL_SEED = 42
UTMOS_INFERENCE_DEVICE = "cpu"
UTMOS_PREDICT_DATASET = "sarulab"

# These files are the complete base-model payload touched by the locked UTMOSv2
# fusion_stage3 smoke-load. Revisions, sizes and hashes are immutable together.
PERCEPTUAL_BASE_MODEL_FILES: tuple[tuple[str, str, str, int, str], ...] = (
    (
        WAV2VEC2_CACHE_REPOSITORY,
        WAV2VEC2_CACHE_REVISION,
        "config.json",
        1_842,
        "4937977e24d12d1bba70cdce8709c3c04807a8e4ae8ddac4229c48c436ae99ae",
    ),
    (
        WAV2VEC2_CACHE_REPOSITORY,
        WAV2VEC2_CACHE_REVISION,
        "preprocessor_config.json",
        159,
        "b225d617c025463b9e157e06afea8b90dc7078fc70b013c533328423e0486b4a",
    ),
    (
        WAV2VEC2_CACHE_REPOSITORY,
        WAV2VEC2_CACHE_REVISION,
        "pytorch_model.bin",
        380_267_417,
        "3249fe98bfc62fcbc26067f724716a6ec49d12c4728a2af1df659013905dff21",
    ),
    (
        TIMM_CACHE_REPOSITORY,
        TIMM_CACHE_REVISION,
        "model.safetensors",
        86_523_256,
        "6f1933fb6c0d760eae03863ad0110570393e16c0610f8fe94dc9f978e52ec59c",
    ),
)

# The version half of each entry must match the pin in pyproject.toml, and a test holds
# the two together - they are one fact written in two places, and they drifted once
# already during an upgrade, which made every check here read as a failure. The `+cu128`
# suffix is the part pyproject genuinely cannot express: PyPI serves a CPU torch on
# Windows, so the CUDA wheel has to come from the PyTorch index and only the installed
# metadata proves which one landed.
CRITICAL_RUNTIME_DISTRIBUTIONS: dict[str, tuple[str, str]] = {
    "torch": ("torch", "2.11.0+cu128"),
    "torchaudio": ("torchaudio", "2.11.0+cu128"),
    # UTMOS runs on CPU, so the ABI-compatible CPU or CUDA torchvision wheel is valid.
    "torchvision": ("torchvision", "0.26.0"),
    "huggingface-hub": ("huggingface_hub", "1.29.0"),
    "librosa": ("librosa", "0.11.0"),
    "timm": ("timm", "1.0.29"),
    "transformers": ("transformers", "5.16.1"),
    "utmosv2": ("utmosv2", "1.3.1.dev0"),
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _direct_url(distribution: importlib.metadata.Distribution) -> dict[str, Any] | None:
    raw = distribution.read_text("direct_url.json")
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {"invalid_json": raw.strip()}
    return parsed if isinstance(parsed, dict) else {"invalid_value": parsed}


def installed_dependency_provenance(
    names: Iterable[str] | None = None,
) -> dict[str, dict[str, Any]]:
    selected = tuple(names or CRITICAL_RUNTIME_DISTRIBUTIONS)
    provenance: dict[str, dict[str, Any]] = {}
    for name in selected:
        try:
            distribution = importlib.metadata.distribution(name)
        except importlib.metadata.PackageNotFoundError:
            provenance[name] = {"version": "MISSING", "direct_url": None}
            continue
        provenance[name] = {
            "version": distribution.version,
            "direct_url": _direct_url(distribution),
        }
    return provenance


def critical_dependency_checks() -> dict[str, dict[str, Any]]:
    checks: dict[str, dict[str, Any]] = {}
    provenance = installed_dependency_provenance()
    for distribution_name, (module_name, expected_version) in CRITICAL_RUNTIME_DISTRIBUTIONS.items():
        actual_version = str(provenance[distribution_name]["version"])
        try:
            module = importlib.import_module(module_name)
        except Exception as exc:  # noqa: BLE001
            checks[distribution_name] = {
                "ok": False,
                "detail": f"import failed: {type(exc).__name__}: {exc}",
            }
            continue
        module_path = str(getattr(module, "__file__", "unknown"))
        version_ok = actual_version == expected_version or (
            "+" not in expected_version
            and actual_version.startswith(f"{expected_version}+")
        )
        checks[distribution_name] = {
            "ok": version_ok,
            "detail": f"{actual_version} (expected {expected_version}); {module_path}",
        }

    torch_check = checks.get("torch", {"ok": False, "detail": "torch unavailable"})
    if torch_check["ok"]:
        import torch

        # What matters is that this torch can reach the GPU, not which CUDA minor it was
        # built against. Pinning the minor made this check fail on every torch upgrade
        # for a reason that was never the real risk. The real risk is the opposite and it
        # is silent: `uv pip install -e .` takes torch from PyPI, PyPI serves the CPU
        # build on Windows, and nothing raises - the pipeline simply runs tens of times
        # slower. Reinstall from https://download.pytorch.org/whl/cu128 when this fails,
        # and pass --reinstall, because uv treats 2.13.0+cpu as satisfying torch==2.13.0.
        cuda_build = str(torch.version.cuda or "")
        # A torch missing the accessor entirely is as unable to reach a GPU as one that
        # answers False, and this must report that rather than raise: the whole point is
        # to turn a silent CPU fallback into a visible failure.
        cuda_module = getattr(torch, "cuda", None)
        is_available = getattr(cuda_module, "is_available", None)
        cuda_reachable = bool(cuda_build) and bool(callable(is_available) and is_available())
        torch_check["ok"] = cuda_reachable
        torch_check["detail"] += (
            f"; CUDA build {cuda_build or 'none'}"
            f"; device {'reachable' if cuda_reachable else 'UNREACHABLE'}"
        )

    utmos = provenance.get("utmosv2", {})
    direct_url = utmos.get("direct_url")
    vcs_info = direct_url.get("vcs_info", {}) if isinstance(direct_url, dict) else {}
    source_url = str(direct_url.get("url", "")) if isinstance(direct_url, dict) else ""
    normalized_source_url = source_url.rstrip("/").removesuffix(".git").casefold()
    normalized_expected_url = UTMOS_SOURCE_URL.rstrip("/").removesuffix(".git").casefold()
    source_ok = (
        normalized_source_url == normalized_expected_url
        and str(vcs_info.get("commit_id", "")).casefold() == UTMOS_SOURCE_COMMIT.casefold()
    )
    checks["utmosv2_source"] = {
        "ok": source_ok,
        "detail": json.dumps(direct_url, sort_keys=True, ensure_ascii=False),
    }
    return checks


def _json_object(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    if not path.is_file():
        return None, f"missing: {path}"
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return None, f"invalid JSON ({path}): {exc}"
    if not isinstance(value, dict):
        return None, f"JSON root is not an object: {path}"
    return value, None


def setup_marker_check(runtime_root: Path) -> dict[str, Any]:
    marker = runtime_root / ".setup_complete"
    payload, error = _json_object(marker)
    schema_version = payload.get("schema_version") if payload is not None else None
    ok = error is None and schema_version == SETUP_SCHEMA_VERSION
    detail = error or f"schema_version={schema_version}; {marker}"
    return {"ok": ok, "detail": detail}


def perceptual_cache_check(runtime_root: Path) -> dict[str, Any]:
    model_root = runtime_root / "models" / "utmosv2"
    checkpoint = model_root / UTMOS_CHECKPOINT_FILENAME
    marker = model_root / PERCEPTUAL_CACHE_MARKER_FILENAME
    payload, marker_error = _json_object(marker)
    errors: list[str] = []
    if marker_error:
        errors.append(marker_error)
    else:
        expected_fields = {
            "schema_version": PERCEPTUAL_CACHE_SCHEMA_VERSION,
            "checkpoint_revision": UTMOS_CHECKPOINT_REVISION,
            "checkpoint_sha256": UTMOS_CHECKPOINT_SHA256.upper(),
            "wav2vec2_revision": WAV2VEC2_CACHE_REVISION,
            "timm_backbone_revision": TIMM_CACHE_REVISION,
            "model_config": UTMOS_MODEL_CONFIG,
            "fold": UTMOS_MODEL_FOLD,
            "seed": UTMOS_MODEL_SEED,
        }
        for key, expected in expected_fields.items():
            actual = payload.get(key)
            if actual != expected:
                errors.append(f"marker {key}={actual!r}, expected {expected!r}")
    hub_root = runtime_root / "models" / "huggingface" / "hub"
    cache_refs = {
        "wav2vec2": (
            hub_root / WAV2VEC2_CACHE_REPOSITORY / "refs" / "main",
            WAV2VEC2_CACHE_REVISION,
        ),
        "timm_backbone": (
            hub_root / TIMM_CACHE_REPOSITORY / "refs" / "main",
            TIMM_CACHE_REVISION,
        ),
    }
    for label, (ref_path, expected_revision) in cache_refs.items():
        try:
            actual_revision = ref_path.read_text(encoding="utf-8").strip()
        except (OSError, UnicodeError) as exc:
            errors.append(f"{label} cache ref unavailable ({ref_path}): {exc}")
            continue
        if actual_revision != expected_revision:
            errors.append(
                f"{label} cache revision={actual_revision!r}, expected {expected_revision!r}"
            )

    for repository, revision, filename, expected_size, expected_sha256 in (
        PERCEPTUAL_BASE_MODEL_FILES
    ):
        snapshot_file = hub_root / repository / "snapshots" / revision / filename
        if not snapshot_file.is_file():
            errors.append(f"missing pinned base-model file: {snapshot_file}")
            continue
        try:
            actual_size = snapshot_file.stat().st_size
        except OSError as exc:
            errors.append(f"base-model file unavailable ({snapshot_file}): {exc}")
            continue
        if actual_size != expected_size:
            errors.append(
                f"base-model size={actual_size} for {snapshot_file}, expected {expected_size}"
            )
            continue
        try:
            actual_sha256 = sha256_file(snapshot_file)
        except OSError as exc:
            errors.append(f"cannot hash base-model file ({snapshot_file}): {exc}")
            continue
        if actual_sha256 != expected_sha256:
            errors.append(
                f"base-model sha256={actual_sha256} for {snapshot_file}, "
                f"expected {expected_sha256}"
            )

    checkpoint_sha256: str | None = None
    if not checkpoint.is_file():
        errors.append(f"missing checkpoint: {checkpoint}")
    else:
        try:
            checkpoint_sha256 = sha256_file(checkpoint)
        except OSError as exc:
            errors.append(f"cannot hash checkpoint ({checkpoint}): {exc}")
        if checkpoint_sha256 is not None and checkpoint_sha256 != UTMOS_CHECKPOINT_SHA256:
            errors.append(
                f"checkpoint sha256={checkpoint_sha256}, expected {UTMOS_CHECKPOINT_SHA256}"
            )
    return {
        "ok": not errors,
        "detail": "; ".join(errors) if errors else f"ready: {marker}",
        "checkpoint_path": str(checkpoint.resolve()),
        "checkpoint_sha256": checkpoint_sha256,
    }


def _path_key(path: Path) -> str:
    return os.path.normcase(os.path.normpath(str(path.expanduser().resolve())))


def perceptual_settings_check(
    runtime_root: Path,
    settings: dict[str, Any],
    *,
    checkpoint_sha256: str | None = None,
) -> dict[str, Any]:
    perceptual = settings.get("perceptual_qa")
    if not isinstance(perceptual, dict):
        return {"ok": False, "detail": "perceptual_qa settings are missing or invalid"}

    if not perceptual.get("enabled"):
        # Nothing below is reachable with perceptual QA off: no model is loaded, no
        # checkpoint is read, and the inference settings describe work that never runs.
        # Verifying them anyway is how a disabled check still blocks a run - which is
        # exactly what happened the first time high_quality stopped requiring it, and cost
        # alpha.52 a create. The settings stay in the file so turning it back on is one
        # flag; they are only checked when they matter. docs/PERCEPTUAL_QA_COST.md.
        return {"ok": True, "detail": "perceptual QA is disabled; its settings are unused"}

    errors: list[str] = []
    expected_settings = {
        "enabled": True,
        "failure_policy": "fail",
        "model_config": UTMOS_MODEL_CONFIG,
        "fold": UTMOS_MODEL_FOLD,
        "model_seed": UTMOS_MODEL_SEED,
        "device": UTMOS_INFERENCE_DEVICE,
        "predict_dataset": UTMOS_PREDICT_DATASET,
    }
    for key, expected in expected_settings.items():
        actual = perceptual.get(key)
        if actual != expected or type(actual) is not type(expected):
            errors.append(f"perceptual_qa.{key}={actual!r}, expected {expected!r}")

    expected_checkpoint = (
        runtime_root / "models" / "utmosv2" / UTMOS_CHECKPOINT_FILENAME
    ).resolve()
    checkpoint_value = str(perceptual.get("checkpoint_path", "")).strip()
    configured_checkpoint = (
        Path(checkpoint_value).expanduser().resolve() if checkpoint_value else None
    )
    if configured_checkpoint is None:
        errors.append("perceptual_qa.checkpoint_path is empty")
    elif _path_key(configured_checkpoint) != _path_key(expected_checkpoint):
        errors.append(
            f"perceptual_qa.checkpoint_path resolves to {configured_checkpoint}, "
            f"expected {expected_checkpoint}"
        )

    actual_checkpoint_sha256 = checkpoint_sha256
    if configured_checkpoint is not None and actual_checkpoint_sha256 is None:
        if not configured_checkpoint.is_file():
            errors.append(f"configured checkpoint is missing: {configured_checkpoint}")
        else:
            try:
                actual_checkpoint_sha256 = sha256_file(configured_checkpoint)
            except OSError as exc:
                errors.append(f"cannot hash configured checkpoint ({configured_checkpoint}): {exc}")
    if (
        actual_checkpoint_sha256 is not None
        and actual_checkpoint_sha256 != UTMOS_CHECKPOINT_SHA256
    ):
        errors.append(
            f"configured checkpoint sha256={actual_checkpoint_sha256}, "
            f"expected {UTMOS_CHECKPOINT_SHA256}"
        )

    return {
        "ok": not errors,
        "detail": "; ".join(errors) if errors else "locked perceptual settings match runtime",
    }


def runtime_contract_errors(
    runtime_root: Path,
    *,
    settings: dict[str, Any] | None = None,
) -> list[str]:
    perceptual_cache = perceptual_cache_check(runtime_root)
    checks = {
        "setup_marker": setup_marker_check(runtime_root),
        "perceptual_cache": perceptual_cache,
        **{
            f"dependency:{name}": result
            for name, result in critical_dependency_checks().items()
        },
    }
    if settings is not None:
        checks["perceptual_settings"] = perceptual_settings_check(
            runtime_root,
            settings,
            checkpoint_sha256=perceptual_cache.get("checkpoint_sha256"),
        )
    return [f"{name}: {result['detail']}" for name, result in checks.items() if not result["ok"]]
