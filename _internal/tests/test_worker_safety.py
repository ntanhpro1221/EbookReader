from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from queue import Queue
from types import SimpleNamespace

import pytest

from ebook_reader import worker as worker_module
from ebook_reader.config import build_settings, save_settings, settings_hash
from ebook_reader.database import ProjectDB
from ebook_reader.io_utils import sha256_file
from ebook_reader.models import ProjectPaths
from ebook_reader.worker import (
    ProjectRunLock,
    _apply_locked_model_cache_environment,
    _apply_model_network_policy,
    _apply_runtime_resource_overrides,
    _emit_pipeline_result,
    _load_locked_settings,
    _validate_model_runtime_contract,
    _validate_project_inputs,
)


def _project(tmp_path: Path):
    paths = ProjectPaths.build(tmp_path / "project")
    settings = build_settings()
    save_settings(paths.settings, settings)
    db = ProjectDB(paths.db)
    db.initialize_book(
        title="Book",
        project_root=paths.root,
        settings=settings,
        settings_hash=settings_hash(settings),
        input_manifest_hash="manifest",
    )
    source = tmp_path / "001.txt"
    source.write_text("Nội dung nguồn đã khóa.", encoding="utf-8")
    db.ensure_chapters([{
        "chapter_index": 1,
        "title": "001",
        "input_path": source,
        "input_sha256": sha256_file(source),
        "input_size": source.stat().st_size,
        "output_mp3": paths.chapters / "001.mp3",
    }])
    return paths, settings, db, source


def test_worker_rejects_external_settings_that_differ_from_sqlite(tmp_path: Path) -> None:
    paths, settings, db, _source = _project(tmp_path)
    tampered = json.loads(json.dumps(settings))
    tampered["tts"]["batch_size"] += 1
    save_settings(paths.settings, tampered)

    with pytest.raises(RuntimeError, match="khác settings đã khóa"):
        _load_locked_settings(paths, db)


def test_worker_rejects_changed_source_file(tmp_path: Path) -> None:
    paths, settings, db, source = _project(tmp_path)
    source.write_text("Nội dung nguồn đã bị thay đổi.", encoding="utf-8")

    with pytest.raises(RuntimeError, match="đã đổi kích thước|đã thay đổi nội dung"):
        _validate_project_inputs(paths, db, settings)


def test_runtime_resources_override_global_values_without_mutating_book_settings() -> None:
    locked = build_settings()
    updated = _apply_runtime_resource_overrides(
        locked,
        {
            "mode": "max_safe",
            "max_gpu_temp_c": 82,
            "resume_gpu_temp_c": 76,
            "critical_gpu_temp_c": 87,
        },
    )

    assert locked["resources"]["mode"] == "max_safe_adaptive_foreground"
    assert locked["resources"]["max_gpu_temp_c"] == 86
    assert updated["resources"]["mode"] == "max_safe"
    assert updated["resources"]["max_gpu_temp_c"] == 82
    assert updated["voices"] == locked["voices"]


def test_worker_applies_offline_policy_to_environment_and_cached_modules(monkeypatch) -> None:
    hub_constants = SimpleNamespace(HF_HUB_OFFLINE=False)
    transformers_hub = SimpleNamespace(_is_offline_mode=False)
    datasets_config = SimpleNamespace(HF_DATASETS_OFFLINE=False)
    monkeypatch.setitem(sys.modules, "huggingface_hub.constants", hub_constants)
    monkeypatch.setitem(sys.modules, "transformers.utils.hub", transformers_hub)
    monkeypatch.setitem(sys.modules, "datasets.config", datasets_config)
    for name in ("HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE", "HF_DATASETS_OFFLINE"):
        monkeypatch.setenv(name, "0")

    applied = _apply_model_network_policy(build_settings())

    assert applied is True
    assert all(
        value == "1"
        for value in (
            os.environ["HF_HUB_OFFLINE"],
            os.environ["TRANSFORMERS_OFFLINE"],
            os.environ["HF_DATASETS_OFFLINE"],
        )
    )
    assert hub_constants.HF_HUB_OFFLINE is True
    assert transformers_hub._is_offline_mode is True
    assert datasets_config.HF_DATASETS_OFFLINE is True


def test_high_quality_worker_forces_locked_model_cache_environment(
    monkeypatch,
    tmp_path: Path,
) -> None:
    hub_constants = SimpleNamespace(HF_HOME="old-home", HF_HUB_CACHE="old-hub")
    transformers_hub = SimpleNamespace(HF_HUB_CACHE="old-transformers-cache")
    monkeypatch.setitem(sys.modules, "huggingface_hub.constants", hub_constants)
    monkeypatch.setitem(sys.modules, "transformers.utils.hub", transformers_hub)
    monkeypatch.setenv("EBOOK_READER_RUNTIME", str(tmp_path))
    monkeypatch.setenv("HF_HOME", "C:\\global-hf")
    monkeypatch.setenv("HF_HUB_CACHE", "C:\\global-hub")
    monkeypatch.setenv("TORCH_HOME", "C:\\global-torch")

    applied = _apply_locked_model_cache_environment(build_settings())

    expected_hf_home = str(tmp_path / "models" / "huggingface")
    expected_hub = str(tmp_path / "models" / "huggingface" / "hub")
    assert applied is True
    assert os.environ["HF_HOME"] == expected_hf_home
    assert os.environ["HF_HUB_CACHE"] == expected_hub
    assert os.environ["TORCH_HOME"] == str(tmp_path / "models" / "torch")
    assert hub_constants.HF_HOME == expected_hf_home
    assert hub_constants.HF_HUB_CACHE == expected_hub
    assert transformers_hub.HF_HUB_CACHE == expected_hub


def test_balanced_worker_preserves_existing_model_cache_environment(
    monkeypatch,
) -> None:
    monkeypatch.setenv("HF_HOME", "C:\\balanced-hf")

    applied = _apply_locked_model_cache_environment(build_settings(profile="balanced"))

    assert applied is False
    assert os.environ["HF_HOME"] == "C:\\balanced-hf"


def test_worker_does_not_override_explicit_environment_when_downloads_are_allowed(
    monkeypatch,
) -> None:
    settings = build_settings(
        overrides={"safety": {"allow_network_downloads_during_job": True}}
    )
    monkeypatch.setenv("HF_HUB_OFFLINE", "0")

    applied = _apply_model_network_policy(settings)

    assert applied is False
    assert os.environ["HF_HUB_OFFLINE"] == "0"


def test_worker_rejects_stale_perceptual_base_cache(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("EBOOK_READER_RUNTIME", str(tmp_path))
    monkeypatch.setattr(
        worker_module,
        "runtime_contract_errors",
        lambda _root, *, settings: [
            f"wav2vec2 cache revision changed ({settings['quality_profile']})"
        ],
    )

    with pytest.raises(RuntimeError, match="wav2vec2 cache revision changed"):
        _validate_model_runtime_contract(build_settings())


def test_worker_skips_strict_runtime_contract_for_non_high_quality(monkeypatch) -> None:
    monkeypatch.setattr(
        worker_module,
        "runtime_contract_errors",
        lambda _root: pytest.fail("balanced worker must not require high-quality runtime assets"),
    )

    _validate_model_runtime_contract(build_settings(profile="balanced"))


def test_project_run_lock_is_exclusive(tmp_path: Path) -> None:
    first = ProjectRunLock(tmp_path / ".worker.lock")
    second = ProjectRunLock(tmp_path / ".worker.lock")
    first.acquire()
    try:
        with pytest.raises(RuntimeError, match="worker khác"):
            second.acquire()
    finally:
        first.release()


def test_worker_reports_completed_with_errors_as_failure(tmp_path: Path) -> None:
    _paths, _settings, db, _source = _project(tmp_path)
    db.update_book(
        status="error",
        stage="completed_with_errors",
        error="1 chapter chưa thể xuất MP3",
    )
    messages = Queue()

    _emit_pipeline_result(messages, db)

    message = messages.get_nowait()
    assert message["kind"] == "finished"
    assert message["ok"] is False
    assert message["critical"] is True
    assert "1 chapter chưa thể xuất MP3" in message["text"]
