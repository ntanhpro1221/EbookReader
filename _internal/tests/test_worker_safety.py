from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from queue import Queue
from types import SimpleNamespace

import pytest

from ebook_reader import worker as worker_module
from ebook_reader.config import (
    DIRECTOR_CRITIC_SETTING_KEYS,
    build_settings,
    save_settings,
    settings_hash,
)
from ebook_reader.database import ProjectDB
from ebook_reader.io_utils import sha256_file
from ebook_reader.models import BookStatus, ProjectPaths
from ebook_reader.pipeline import BookPipeline
from ebook_reader.worker import (
    ProjectRunLock,
    _apply_locked_model_cache_environment,
    _apply_model_network_policy,
    _apply_runtime_resource_overrides,
    _emit_pipeline_result,
    _finalize_requested_stop,
    _finalize_unrecoverable_failure,
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


def _legacy_director_project(tmp_path: Path) -> tuple[ProjectPaths, dict, ProjectDB]:
    paths = ProjectPaths.build(tmp_path / "legacy-project")
    settings = build_settings()
    for key in DIRECTOR_CRITIC_SETTING_KEYS:
        settings["analysis"].pop(key)
    paths.settings.write_text(json.dumps(settings, ensure_ascii=False), encoding="utf-8")
    db = ProjectDB(paths.db)
    db.initialize_book(
        title="Legacy",
        project_root=paths.root,
        settings=settings,
        settings_hash=settings_hash(settings),
        input_manifest_hash="manifest",
    )
    return paths, settings, db


def test_worker_normalizes_legacy_director_settings_only_after_raw_lock_comparison(
    tmp_path: Path,
) -> None:
    paths, raw_settings, db = _legacy_director_project(tmp_path)
    original_file = paths.settings.read_bytes()
    original_hash = settings_hash(raw_settings)

    effective = _load_locked_settings(paths, db)

    assert effective["analysis"]["director_critic_enabled"] is True
    assert effective["analysis"]["director_critic_required"] is True
    assert effective["analysis"]["low_confidence_policy"] == "fail"
    assert paths.settings.read_bytes() == original_file
    assert str(db.book()["settings_hash"]) == original_hash


def test_worker_rejects_legacy_high_quality_project_after_analysis_started(
    tmp_path: Path,
) -> None:
    paths, _raw_settings, db = _legacy_director_project(tmp_path)
    chapter_id = db.ensure_chapters(
        [{
            "chapter_index": 1,
            "title": "One",
            "input_path": tmp_path / "one.txt",
            "input_sha256": "source",
            "input_size": 1,
            "output_mp3": paths.chapters / "one.mp3",
        }]
    )[0]
    db.replace_chapter_segments(
        chapter_id,
        [{
            "stable_id": "c1s1",
            "seq": 0,
            "text": "Text",
            "text_sha256": "text",
            "kind_hint": "narration",
        }],
    )
    segment_id = int(db.list_segments()[0]["id"])
    db.update_analysis(segment_id, {"confidence": 0.9})

    with pytest.raises(RuntimeError, match="tạo project sạch"):
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
    # `transformers.utils.hub._is_offline_mode` không còn tồn tại ở transformers 5.x - hàm
    # `is_offline_mode()` của nó đọc thẳng `huggingface_hub.constants.HF_HUB_OFFLINE` (đo 18-09,
    # `tests/test_offline_guard_names.py`). Worker thôi đặt tên ấy, nên module giả mang tên ấy
    # phải còn NGUYÊN: đặt vào một thuộc tính mà thư viện thật không đọc là giả vờ đang chốt.
    assert transformers_hub._is_offline_mode is False
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
    # transformers 5.x không giữ bản sao `HF_HUB_CACHE` riêng - nó đọc từ `huggingface_hub.constants`
    # (đo 18-09). Worker thôi ghi vào tên đã chết ấy; module giả phải còn nguyên giá trị cũ.
    assert transformers_hub.HF_HUB_CACHE == "old-transformers-cache"


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


def _reporting_pipeline(paths: ProjectPaths, settings: dict, db: ProjectDB) -> BookPipeline:
    return BookPipeline(
        paths=paths,
        db=db,
        settings=settings,
        pause_requested=lambda: False,
        stop_requested=lambda: False,
        emit=lambda _kind, _payload: None,
    )


def test_unrecoverable_failure_refreshes_reports_after_terminal_db_event(
    tmp_path: Path,
) -> None:
    paths, settings, db, _source = _project(tmp_path)
    pipeline = _reporting_pipeline(paths, settings, db)
    db.update_book(
        status=BookStatus.ANALYZING.value,
        stage="full_book_analysis",
    )
    pipeline.refresh_terminal_reports()
    initial_report = json.loads(
        (paths.reports / "audiobook_quality_report.json").read_text(encoding="utf-8")
    )
    assert initial_report["book"]["status"] == BookStatus.ANALYZING.value

    original_error = RuntimeError("director critic singleton failed")
    _finalize_unrecoverable_failure(
        paths=paths,
        db=db,
        settings=settings,
        pipeline=pipeline,
        error=original_error,
        traceback_details="traceback sentinel",
    )

    book = db.book()
    report = json.loads(
        (paths.reports / "audiobook_quality_report.json").read_text(encoding="utf-8")
    )
    runtime_events = json.loads(
        (paths.reports / "runtime_events.json").read_text(encoding="utf-8")
    )
    terminal_events = [
        row for row in runtime_events if row["code"] == "UNRECOVERABLE_PIPELINE_ERROR"
    ]
    assert str(book["status"]) == BookStatus.ERROR.value
    assert str(book["stage"]) == "unrecoverable_error"
    assert str(book["last_error"]) == str(original_error)
    assert report["book"]["status"] == BookStatus.ERROR.value
    assert report["book"]["stage"] == "unrecoverable_error"
    assert runtime_events[-1]["code"] == "UNRECOVERABLE_PIPELINE_ERROR"
    assert len(terminal_events) == 1
    assert terminal_events[0]["message"] == str(original_error)
    assert "traceback sentinel" in terminal_events[0]["details_json"]


def test_unrecoverable_failure_report_write_error_does_not_mask_or_duplicate_event(
    monkeypatch,
    caplog,
    tmp_path: Path,
) -> None:
    paths, settings, db, _source = _project(tmp_path)
    pipeline = _reporting_pipeline(paths, settings, db)
    db.update_book(
        status=BookStatus.ANALYZING.value,
        stage="full_book_analysis",
    )
    pipeline.refresh_terminal_reports()

    def fail_report_refresh() -> None:
        raise OSError("report volume is read-only")

    monkeypatch.setattr(pipeline, "refresh_terminal_reports", fail_report_refresh)
    original_error = RuntimeError("original pipeline failure")

    _finalize_unrecoverable_failure(
        paths=paths,
        db=db,
        settings=settings,
        pipeline=pipeline,
        error=original_error,
        traceback_details="original traceback",
    )

    book = db.book()
    db_events = [dict(row) for row in db.list_events()]
    stale_report = json.loads(
        (paths.reports / "audiobook_quality_report.json").read_text(encoding="utf-8")
    )
    terminal_events = [
        row for row in db_events if row["code"] == "UNRECOVERABLE_PIPELINE_ERROR"
    ]
    assert str(book["status"]) == BookStatus.ERROR.value
    assert str(book["last_error"]) == str(original_error)
    assert stale_report["book"]["status"] == BookStatus.ANALYZING.value
    assert len(terminal_events) == 1
    assert terminal_events[0]["message"] == str(original_error)
    assert not any(row["code"] == "QUALITY_REPORT_EXPORT_FAILED" for row in db_events)
    assert "Could not refresh reports after unrecoverable pipeline error" in caplog.text


def test_requested_stop_refreshes_reports_after_terminal_db_event(tmp_path: Path) -> None:
    paths, settings, db, _source = _project(tmp_path)
    pipeline = _reporting_pipeline(paths, settings, db)
    db.update_book(
        status=BookStatus.ANALYZING.value,
        stage="full_book_analysis",
    )
    pipeline.refresh_terminal_reports()

    _finalize_requested_stop(
        paths=paths,
        db=db,
        settings=settings,
        pipeline=pipeline,
    )

    report = json.loads(
        (paths.reports / "audiobook_quality_report.json").read_text(encoding="utf-8")
    )
    runtime_events = json.loads(
        (paths.reports / "runtime_events.json").read_text(encoding="utf-8")
    )
    stopped_events = [row for row in runtime_events if row["code"] == "PIPELINE_STOPPED"]
    assert str(db.book()["status"]) == BookStatus.STOPPED.value
    assert str(db.book()["stage"]) == "stopped"
    assert report["book"]["status"] == BookStatus.STOPPED.value
    assert report["book"]["stage"] == "stopped"
    assert runtime_events[-1]["code"] == "PIPELINE_STOPPED"
    assert len(stopped_events) == 1


def test_requested_stop_report_failure_preserves_stopped_result(
    monkeypatch,
    caplog,
    tmp_path: Path,
) -> None:
    paths, settings, db, _source = _project(tmp_path)
    pipeline = _reporting_pipeline(paths, settings, db)
    db.update_book(
        status=BookStatus.ANALYZING.value,
        stage="full_book_analysis",
    )
    pipeline.refresh_terminal_reports()

    def fail_report_refresh() -> None:
        raise OSError("report volume is read-only")

    monkeypatch.setattr(pipeline, "refresh_terminal_reports", fail_report_refresh)

    _finalize_requested_stop(
        paths=paths,
        db=db,
        settings=settings,
        pipeline=pipeline,
    )

    stale_report = json.loads(
        (paths.reports / "audiobook_quality_report.json").read_text(encoding="utf-8")
    )
    stopped_events = [
        dict(row) for row in db.list_events() if row["code"] == "PIPELINE_STOPPED"
    ]
    assert str(db.book()["status"]) == BookStatus.STOPPED.value
    assert str(db.book()["stage"]) == "stopped"
    assert stale_report["book"]["status"] == BookStatus.ANALYZING.value
    assert len(stopped_events) == 1
    assert "Could not refresh reports after requested pipeline stop" in caplog.text


def test_critical_resource_stop_refreshes_reports_without_changing_finished_payload(
    monkeypatch,
    tmp_path: Path,
) -> None:
    paths, _settings, db, _source = _project(tmp_path)
    reason = "available RAM 0.7 GB is below the critical threshold"

    class NoopThread:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        def start(self) -> None:
            pass

    class CriticalStopPipeline:
        def __init__(self, *, paths, db, settings, **_kwargs) -> None:
            self.paths = paths
            self.db = db
            self.settings = settings

        def prepare_recovery(self) -> None:
            self.db.update_book(
                status=BookStatus.CASTING.value,
                stage="voice_cast_locked",
            )
            BookPipeline.refresh_terminal_reports_without_runtime(
                paths=self.paths,
                db=self.db,
                settings=self.settings,
            )

        def run(self, *, recovery_already_run: bool) -> None:
            assert recovery_already_run is True
            self.db.update_book(
                status=BookStatus.STOPPED.value,
                stage="critical_stop",
                error=reason,
            )
            self.db.event(
                "critical",
                "CRITICAL_RESOURCE_STOP",
                reason,
                {"checkpoint": "xác minh preset VieNeu"},
            )
            raise worker_module.CriticalResourceStop(reason)

        def refresh_terminal_reports(self) -> None:
            BookPipeline.refresh_terminal_reports_without_runtime(
                paths=self.paths,
                db=self.db,
                settings=self.settings,
            )

    monkeypatch.setattr(worker_module, "BookPipeline", CriticalStopPipeline)
    monkeypatch.setattr(worker_module, "WorkerHeartbeat", NoopThread)
    monkeypatch.setattr(worker_module, "ParentWatchdog", NoopThread)
    monkeypatch.setattr(worker_module, "_configure_logging", lambda _path: None)
    monkeypatch.setattr(
        worker_module,
        "_apply_locked_model_cache_environment",
        lambda _settings: False,
    )
    monkeypatch.setattr(worker_module, "_apply_model_network_policy", lambda _settings: False)
    monkeypatch.setattr(worker_module, "_validate_model_runtime_contract", lambda _settings: None)
    monkeypatch.setattr(worker_module, "set_worker_priority", lambda _priority: None)
    messages = Queue()
    event = SimpleNamespace(is_set=lambda: False)

    worker_module.run_worker(
        str(paths.root),
        messages,
        event,
        event,
        os.getpid(),
    )

    emitted = []
    while not messages.empty():
        emitted.append(messages.get_nowait())
    finished = [row for row in emitted if row["kind"] == "finished"]
    report = json.loads(
        (paths.reports / "audiobook_quality_report.json").read_text(encoding="utf-8")
    )
    runtime_events = json.loads(
        (paths.reports / "runtime_events.json").read_text(encoding="utf-8")
    )
    critical_events = [row for row in runtime_events if row["code"] == "CRITICAL_RESOURCE_STOP"]

    assert finished == [{
        "kind": "finished",
        "ok": False,
        "critical": True,
        "text": f"Đã dừng vì điều kiện an toàn: {reason}",
    }]
    assert report["book"]["status"] == BookStatus.STOPPED.value
    assert report["book"]["stage"] == "critical_stop"
    assert runtime_events[-1]["code"] == "CRITICAL_RESOURCE_STOP"
    assert len(critical_events) == 1
    assert critical_events[0]["message"] == reason


def test_startup_failure_without_pipeline_uses_report_only_refresh(
    monkeypatch,
    tmp_path: Path,
) -> None:
    paths, settings, db, _source = _project(tmp_path)
    pipeline = _reporting_pipeline(paths, settings, db)
    db.update_book(
        status=BookStatus.ANALYZING.value,
        stage="startup_validation",
    )
    pipeline.refresh_terminal_reports()

    def fail_if_pipeline_runtime_is_constructed(*_args, **_kwargs) -> None:
        raise AssertionError("terminal reporting must not construct pipeline runtime")

    monkeypatch.setattr(BookPipeline, "__init__", fail_if_pipeline_runtime_is_constructed)
    original_error = RuntimeError("Source chapter changed before worker startup")

    _finalize_unrecoverable_failure(
        paths=paths,
        db=db,
        settings=settings,
        pipeline=None,
        error=original_error,
        traceback_details="startup traceback sentinel",
    )

    report = json.loads(
        (paths.reports / "audiobook_quality_report.json").read_text(encoding="utf-8")
    )
    runtime_events = json.loads(
        (paths.reports / "runtime_events.json").read_text(encoding="utf-8")
    )
    terminal_events = [
        row for row in runtime_events if row["code"] == "UNRECOVERABLE_PIPELINE_ERROR"
    ]
    assert str(db.book()["status"]) == BookStatus.ERROR.value
    assert str(db.book()["last_error"]) == str(original_error)
    assert report["book"]["status"] == BookStatus.ERROR.value
    assert report["book"]["stage"] == "unrecoverable_error"
    assert len(terminal_events) == 1
    assert terminal_events[0]["message"] == str(original_error)
    assert "startup traceback sentinel" in terminal_events[0]["details_json"]


def test_startup_report_only_refresh_error_preserves_original_failure(
    monkeypatch,
    caplog,
    tmp_path: Path,
) -> None:
    paths, settings, db, _source = _project(tmp_path)

    def fail_report_only_refresh(**_kwargs) -> None:
        raise OSError("report-only construction failed")

    monkeypatch.setattr(
        BookPipeline,
        "refresh_terminal_reports_without_runtime",
        staticmethod(fail_report_only_refresh),
    )
    original_error = RuntimeError("original startup validation failure")

    _finalize_unrecoverable_failure(
        paths=paths,
        db=db,
        settings=settings,
        pipeline=None,
        error=original_error,
        traceback_details="original startup traceback",
    )

    terminal_events = [
        dict(row)
        for row in db.list_events()
        if row["code"] == "UNRECOVERABLE_PIPELINE_ERROR"
    ]
    assert str(db.book()["status"]) == BookStatus.ERROR.value
    assert str(db.book()["stage"]) == "unrecoverable_error"
    assert str(db.book()["last_error"]) == str(original_error)
    assert len(terminal_events) == 1
    assert terminal_events[0]["message"] == str(original_error)
    assert "Could not refresh reports after unrecoverable pipeline error" in caplog.text


def test_safe_incremental_report_failure_cannot_be_replaced_by_event_write_failure(
    monkeypatch,
    caplog,
    tmp_path: Path,
) -> None:
    paths, settings, db, _source = _project(tmp_path)
    pipeline = _reporting_pipeline(paths, settings, db)

    def fail_report_export(*, incremental: bool) -> None:
        assert incremental is True
        raise OSError("report write failed")

    def fail_event_write(*_args, **_kwargs) -> None:
        raise OSError("event write failed")

    monkeypatch.setattr(pipeline, "_export_reports", fail_report_export)
    monkeypatch.setattr(db, "event", fail_event_write)

    pipeline._safe_export_reports(incremental=True)

    assert "Could not record quality report export failure" in caplog.text
