from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from ebook_reader import runtime_contract
from ebook_reader.config import build_settings
from ebook_reader.runtime_contract import perceptual_settings_check


class FakeDistribution:
    def __init__(self, version: str, direct_url: dict | None = None) -> None:
        self.version = version
        self.direct_url = direct_url

    def read_text(self, filename: str) -> str | None:
        if filename != "direct_url.json" or self.direct_url is None:
            return None
        return json.dumps(self.direct_url)


def _write_fake_base_model_files(tmp_path: Path, monkeypatch) -> list[Path]:
    fake_files = tuple(
        (
            repository,
            revision,
            filename,
            len(b"fake"),
            runtime_contract.UTMOS_CHECKPOINT_SHA256,
        )
        for repository, revision, filename, _size, _sha256 in (
            runtime_contract.PERCEPTUAL_BASE_MODEL_FILES
        )
    )
    monkeypatch.setattr(runtime_contract, "PERCEPTUAL_BASE_MODEL_FILES", fake_files)
    paths = []
    for repository, revision, filename, _size, _sha256 in fake_files:
        path = (
            tmp_path
            / "models"
            / "huggingface"
            / "hub"
            / repository
            / "snapshots"
            / revision
            / filename
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"fake")
        paths.append(path)
    return paths


def test_critical_dependency_checks_import_modules_and_lock_utmos_source(monkeypatch) -> None:
    distributions = {
        name: FakeDistribution(version)
        for name, (_module, version) in runtime_contract.CRITICAL_RUNTIME_DISTRIBUTIONS.items()
    }
    distributions["utmosv2"] = FakeDistribution(
        "1.3.1.dev0",
        {
            "url": runtime_contract.UTMOS_SOURCE_URL,
            "vcs_info": {"commit_id": runtime_contract.UTMOS_SOURCE_COMMIT, "vcs": "git"},
        },
    )
    imported: list[str] = []

    def fake_distribution(name: str):
        return distributions[name]

    def fake_import(name: str):
        imported.append(name)
        if name == "torch":
            return SimpleNamespace(
                __file__="torch.py",
                version=SimpleNamespace(cuda="12.8"),
                cuda=SimpleNamespace(is_available=lambda: True),
            )
        return SimpleNamespace(__file__=f"{name}.py")

    monkeypatch.setattr(runtime_contract.importlib.metadata, "distribution", fake_distribution)
    monkeypatch.setattr(runtime_contract.importlib, "import_module", fake_import)
    monkeypatch.setitem(
        sys.modules,
        "torch",
        SimpleNamespace(
            version=SimpleNamespace(cuda="12.8"),
            cuda=SimpleNamespace(is_available=lambda: True),
        ),
    )

    checks = runtime_contract.critical_dependency_checks()

    assert all(result["ok"] for result in checks.values())
    assert set(imported) == {
        module for module, _version in runtime_contract.CRITICAL_RUNTIME_DISTRIBUTIONS.values()
    }


def test_perceptual_cache_marker_requires_locked_revision_and_checkpoint_hash(
    tmp_path,
    monkeypatch,
) -> None:
    _write_fake_base_model_files(tmp_path, monkeypatch)
    model_root = tmp_path / "models" / "utmosv2"
    model_root.mkdir(parents=True)
    checkpoint = model_root / runtime_contract.UTMOS_CHECKPOINT_FILENAME
    checkpoint.write_bytes(b"locked checkpoint")
    marker = model_root / runtime_contract.PERCEPTUAL_CACHE_MARKER_FILENAME
    marker.write_text(
        json.dumps(
            {
                "schema_version": runtime_contract.PERCEPTUAL_CACHE_SCHEMA_VERSION,
                "checkpoint_revision": runtime_contract.UTMOS_CHECKPOINT_REVISION,
                "checkpoint_sha256": runtime_contract.UTMOS_CHECKPOINT_SHA256.upper(),
                "wav2vec2_revision": runtime_contract.WAV2VEC2_CACHE_REVISION,
                "timm_backbone_revision": runtime_contract.TIMM_CACHE_REVISION,
                "model_config": "fusion_stage3",
                "fold": 0,
                "seed": 42,
            }
        ),
        encoding="utf-8",
    )
    cache_refs = {
        runtime_contract.WAV2VEC2_CACHE_REPOSITORY: (
            runtime_contract.WAV2VEC2_CACHE_REVISION
        ),
        runtime_contract.TIMM_CACHE_REPOSITORY: runtime_contract.TIMM_CACHE_REVISION,
    }
    for repository, revision in cache_refs.items():
        ref_path = tmp_path / "models" / "huggingface" / "hub" / repository / "refs" / "main"
        ref_path.parent.mkdir(parents=True)
        ref_path.write_text(revision, encoding="utf-8")
    monkeypatch.setattr(
        runtime_contract,
        "sha256_file",
        lambda _path: runtime_contract.UTMOS_CHECKPOINT_SHA256,
    )

    assert runtime_contract.perceptual_cache_check(tmp_path)["ok"] is True

    payload = json.loads(marker.read_text(encoding="utf-8"))
    payload["checkpoint_revision"] = "mutable-main"
    marker.write_text(json.dumps(payload), encoding="utf-8")

    result = runtime_contract.perceptual_cache_check(tmp_path)
    assert result["ok"] is False
    assert "checkpoint_revision" in result["detail"]


def test_perceptual_cache_rejects_changed_base_model_ref(tmp_path, monkeypatch) -> None:
    _write_fake_base_model_files(tmp_path, monkeypatch)
    model_root = tmp_path / "models" / "utmosv2"
    model_root.mkdir(parents=True)
    (model_root / runtime_contract.UTMOS_CHECKPOINT_FILENAME).write_bytes(b"checkpoint")
    (model_root / runtime_contract.PERCEPTUAL_CACHE_MARKER_FILENAME).write_text(
        json.dumps(
            {
                "schema_version": runtime_contract.PERCEPTUAL_CACHE_SCHEMA_VERSION,
                "checkpoint_revision": runtime_contract.UTMOS_CHECKPOINT_REVISION,
                "checkpoint_sha256": runtime_contract.UTMOS_CHECKPOINT_SHA256.upper(),
                "wav2vec2_revision": runtime_contract.WAV2VEC2_CACHE_REVISION,
                "timm_backbone_revision": runtime_contract.TIMM_CACHE_REVISION,
                "model_config": "fusion_stage3",
                "fold": 0,
                "seed": 42,
            }
        ),
        encoding="utf-8",
    )
    refs = {
        runtime_contract.WAV2VEC2_CACHE_REPOSITORY: "changed-main",
        runtime_contract.TIMM_CACHE_REPOSITORY: runtime_contract.TIMM_CACHE_REVISION,
    }
    for repository, revision in refs.items():
        ref_path = tmp_path / "models" / "huggingface" / "hub" / repository / "refs" / "main"
        ref_path.parent.mkdir(parents=True)
        ref_path.write_text(revision, encoding="utf-8")
    monkeypatch.setattr(
        runtime_contract,
        "sha256_file",
        lambda _path: runtime_contract.UTMOS_CHECKPOINT_SHA256,
    )

    result = runtime_contract.perceptual_cache_check(tmp_path)

    assert result["ok"] is False
    assert "wav2vec2 cache revision='changed-main'" in result["detail"]


def test_perceptual_cache_rejects_missing_pinned_snapshot_file(tmp_path, monkeypatch) -> None:
    snapshot_files = _write_fake_base_model_files(tmp_path, monkeypatch)
    snapshot_files[0].unlink()
    model_root = tmp_path / "models" / "utmosv2"
    model_root.mkdir(parents=True)
    (model_root / runtime_contract.UTMOS_CHECKPOINT_FILENAME).write_bytes(b"checkpoint")
    (model_root / runtime_contract.PERCEPTUAL_CACHE_MARKER_FILENAME).write_text(
        json.dumps(
            {
                "schema_version": runtime_contract.PERCEPTUAL_CACHE_SCHEMA_VERSION,
                "checkpoint_revision": runtime_contract.UTMOS_CHECKPOINT_REVISION,
                "checkpoint_sha256": runtime_contract.UTMOS_CHECKPOINT_SHA256.upper(),
                "wav2vec2_revision": runtime_contract.WAV2VEC2_CACHE_REVISION,
                "timm_backbone_revision": runtime_contract.TIMM_CACHE_REVISION,
                "model_config": runtime_contract.UTMOS_MODEL_CONFIG,
                "fold": runtime_contract.UTMOS_MODEL_FOLD,
                "seed": runtime_contract.UTMOS_MODEL_SEED,
            }
        ),
        encoding="utf-8",
    )
    for repository, revision in (
        (
            runtime_contract.WAV2VEC2_CACHE_REPOSITORY,
            runtime_contract.WAV2VEC2_CACHE_REVISION,
        ),
        (runtime_contract.TIMM_CACHE_REPOSITORY, runtime_contract.TIMM_CACHE_REVISION),
    ):
        ref = tmp_path / "models" / "huggingface" / "hub" / repository / "refs" / "main"
        ref.parent.mkdir(parents=True)
        ref.write_text(revision, encoding="utf-8")
    monkeypatch.setattr(
        runtime_contract,
        "sha256_file",
        lambda _path: runtime_contract.UTMOS_CHECKPOINT_SHA256,
    )

    result = runtime_contract.perceptual_cache_check(tmp_path)

    assert result["ok"] is False
    assert "missing pinned base-model file" in result["detail"]


def test_perceptual_settings_require_calibrated_checkpoint_and_model_contract(
    tmp_path,
    monkeypatch,
) -> None:
    checkpoint = (
        tmp_path
        / "models"
        / "utmosv2"
        / runtime_contract.UTMOS_CHECKPOINT_FILENAME
    )
    checkpoint.parent.mkdir(parents=True)
    checkpoint.write_bytes(b"checkpoint")
    monkeypatch.setattr(
        runtime_contract,
        "sha256_file",
        lambda path: (
            runtime_contract.UTMOS_CHECKPOINT_SHA256
            if path == checkpoint
            else pytest.fail(f"unexpected hash path: {path}")
        ),
    )
    settings = {
        "perceptual_qa": {
            "enabled": True,
            "failure_policy": "fail",
            "checkpoint_path": str(checkpoint),
            "model_config": runtime_contract.UTMOS_MODEL_CONFIG,
            "fold": runtime_contract.UTMOS_MODEL_FOLD,
            "model_seed": runtime_contract.UTMOS_MODEL_SEED,
            "device": runtime_contract.UTMOS_INFERENCE_DEVICE,
            "predict_dataset": runtime_contract.UTMOS_PREDICT_DATASET,
        }
    }

    result = runtime_contract.perceptual_settings_check(tmp_path, settings)

    assert result["ok"] is True


def test_perceptual_settings_reject_different_checkpoint_and_uncalibrated_device(
    tmp_path,
) -> None:
    checkpoint = tmp_path / "other" / runtime_contract.UTMOS_CHECKPOINT_FILENAME
    checkpoint.parent.mkdir(parents=True)
    checkpoint.write_bytes(b"other")
    settings = {
        "perceptual_qa": {
            "enabled": True,
            "failure_policy": "fail",
            "checkpoint_path": str(checkpoint),
            "model_config": runtime_contract.UTMOS_MODEL_CONFIG,
            "fold": runtime_contract.UTMOS_MODEL_FOLD,
            "model_seed": runtime_contract.UTMOS_MODEL_SEED,
            "device": "cuda:0",
            "predict_dataset": runtime_contract.UTMOS_PREDICT_DATASET,
        }
    }

    result = runtime_contract.perceptual_settings_check(
        tmp_path,
        settings,
        checkpoint_sha256=runtime_contract.UTMOS_CHECKPOINT_SHA256,
    )

    assert result["ok"] is False
    assert "checkpoint_path resolves to" in result["detail"]
    assert "device='cuda:0'" in result["detail"]


def test_setup_marker_rejects_legacy_schema(tmp_path) -> None:
    marker = tmp_path / ".setup_complete"
    marker.write_text(json.dumps({"schema_version": 1}), encoding="utf-8")

    result = runtime_contract.setup_marker_check(tmp_path)

    assert result["ok"] is False
    assert "schema_version=1" in result["detail"]


def test_the_contract_table_agrees_with_the_pinned_versions() -> None:
    """One fact, written in two places, must not drift.

    `CRITICAL_RUNTIME_DISTRIBUTIONS` and the pins in pyproject.toml say the same thing,
    and during an upgrade only one of them was updated - every runtime check then reported
    a failure that was really just the table being stale. The `+cuXXX` suffix is exempt
    because pyproject cannot express it: PyPI serves a CPU torch on Windows and the CUDA
    wheel has to come from the PyTorch index.
    """
    import re
    import tomllib

    pyproject = Path(__file__).resolve().parent.parent / "pyproject.toml"
    data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    pinned: dict[str, str] = {}
    for requirement in data["project"]["dependencies"]:
        match = re.match(r"^([A-Za-z0-9._-]+)==([^\s;]+)", str(requirement))
        if match:
            pinned[match.group(1).casefold()] = match.group(2)

    drift = {}
    for name, (_module, expected) in runtime_contract.CRITICAL_RUNTIME_DISTRIBUTIONS.items():
        pin = pinned.get(name.casefold())
        if pin is None:
            continue  # installed from a URL rather than a version pin
        if expected.split("+", 1)[0] != pin:
            drift[name] = (expected, pin)
    assert not drift, f"contract table and pyproject disagree: {drift}"


def test_disabled_perceptual_qa_does_not_block_the_run(tmp_path: Path) -> None:
    """A check that is switched off must not be able to stop a run.

    high_quality stopped requiring perceptual QA on 2026-09-07, and this contract kept
    verifying its settings and its checkpoint anyway - so `run` refused to start with
    "perceptual_qa.enabled=False, expected True". The settings it was checking describe a
    model that is never loaded. Two enforcement points, and finding one is not finding both.
    """
    settings = build_settings("high_quality")
    assert settings["perceptual_qa"]["enabled"] is False

    result = perceptual_settings_check(tmp_path / "runtime", settings)

    assert result["ok"] is True


def test_enabled_perceptual_qa_is_still_verified_in_full(tmp_path: Path) -> None:
    """The skip is conditional, not a removal: turn it on and the checkpoint must be real."""
    settings = build_settings("high_quality", {"perceptual_qa": {"enabled": True}})

    result = perceptual_settings_check(tmp_path / "runtime", settings)

    assert result["ok"] is False
