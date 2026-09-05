"""Suspending the machine kills the CUDA context; that must not fail the book.

Windows destroys CUDA contexts when it suspends, and neither PyTorch nor CTranslate2 can
rebuild one inside the process that lost it. Before this, the first GPU call after a wake
raised, landed in the unrecoverable handler, and marked a fully checkpointed book failed -
so the overnight run was lost to a lid closing.

The work is resumable; only the process is unusable. So the worker ends the run as a clean
stop carrying a marker, and the watchdog starts a fresh process. The danger of that design
is a GPU that is actually broken restarting forever, which is what the attempt bound is for.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from ebook_reader.models import ProjectPaths
from ebook_reader.worker import (
    GPU_CONTEXT_LOST_FILE_NAME,
    GPU_CONTEXT_LOST_MAX_ATTEMPTS,
    _record_gpu_context_loss,
    is_lost_gpu_context,
)


class _Db:
    def __init__(self, audio_per_chapter: dict[int, int]) -> None:
        self._counts = audio_per_chapter

    def chapter_progress_counts(self) -> dict[int, dict[str, int]]:
        return {cid: {"analysis": n, "audio": n} for cid, n in self._counts.items()}


def _marker(root: Path) -> Path:
    return root / "runtime" / "background" / GPU_CONTEXT_LOST_FILE_NAME


@pytest.mark.parametrize(
    "message",
    [
        "CUDA error: unspecified launch failure",
        "CUDA error: unknown error",
        "CUDA error: initialization error",
        "CUDA driver error: CUDA_ERROR_INVALID_CONTEXT",
        "cuBLAS failure: the context is destroyed",
        "CTranslate2: CUDA failed with error invalid device context",
        "CUDA error: no CUDA-capable device is detected",
        "CUDA error: all CUDA-capable devices are busy or unavailable",
        "CUDA error: invalid resource handle",
    ],
)
def test_a_context_that_died_under_us_is_recognised(message: str) -> None:
    assert is_lost_gpu_context(RuntimeError(message))


@pytest.mark.parametrize(
    "message",
    [
        "CUDA driver version is insufficient for CUDA runtime version",
        "CUDA error: no kernel image is available for execution on the device",
        "CUDA error: device-side assert triggered",
        "CUDA error: an illegal memory access was encountered",
        "CUDA error: misaligned address",
    ],
)
def test_a_gpu_that_is_actually_broken_is_not(message: str) -> None:
    """These fail again in a fresh process, so restarting would loop forever."""
    assert not is_lost_gpu_context(RuntimeError(message))


@pytest.mark.parametrize(
    "message",
    [
        "unknown error while reading chapter 3",
        "initialization error in the settings loader",
        "Ollama trả về JSON hỏng",
        "the context is destroyed",
    ],
)
def test_an_error_that_is_not_about_the_gpu_is_not(message: str) -> None:
    """Some markers are generic; the message has to be about the GPU before they count."""
    assert not is_lost_gpu_context(RuntimeError(message))


def test_the_driver_error_is_found_underneath_the_pipeline_error() -> None:
    """The interesting string is rarely on the exception that surfaced."""
    try:
        try:
            raise RuntimeError("CUDA error: unspecified launch failure")
        except RuntimeError as cause:
            raise RuntimeError("Không tổng hợp được segment c1_s2") from cause
    except RuntimeError as surfaced:
        assert is_lost_gpu_context(surfaced)


def test_a_permanent_marker_wins_over_a_transient_one() -> None:
    """A chain can carry both; restarting on a broken driver is the worse mistake."""
    try:
        try:
            raise RuntimeError("CUDA driver version is insufficient")
        except RuntimeError as cause:
            raise RuntimeError("CUDA error: unknown error") from cause
    except RuntimeError as surfaced:
        assert not is_lost_gpu_context(surfaced)


def test_the_first_loss_is_attempt_one(tmp_path: Path) -> None:
    paths = ProjectPaths.build(tmp_path)
    record = _record_gpu_context_loss(paths, _Db({1: 40}))

    assert record["attempt"] == 1
    assert record["resumable"]
    assert record["segments_done"] == 40
    assert json.loads(_marker(tmp_path).read_text(encoding="utf-8"))["attempt"] == 1


def test_losses_that_produce_no_progress_accumulate(tmp_path: Path) -> None:
    paths = ProjectPaths.build(tmp_path)
    db = _Db({1: 40})

    attempts = [_record_gpu_context_loss(paths, db)["attempt"] for _ in range(3)]

    assert attempts == [1, 2, 3]


def test_progress_since_the_last_loss_resets_the_count(tmp_path: Path) -> None:
    """A machine that suspends every night must never approach the bound."""
    paths = ProjectPaths.build(tmp_path)
    _record_gpu_context_loss(paths, _Db({1: 40}))
    _record_gpu_context_loss(paths, _Db({1: 40}))

    record = _record_gpu_context_loss(paths, _Db({1: 41}))

    assert record["attempt"] == 1
    assert record["made_progress_since_last"]


def test_it_gives_up_after_enough_losses_with_no_progress(tmp_path: Path) -> None:
    """A GPU that cannot synthesize one segment must fail where a human sees it."""
    paths = ProjectPaths.build(tmp_path)
    db = _Db({1: 0})

    records = [
        _record_gpu_context_loss(paths, db) for _ in range(GPU_CONTEXT_LOST_MAX_ATTEMPTS + 1)
    ]

    assert all(r["resumable"] for r in records[:GPU_CONTEXT_LOST_MAX_ATTEMPTS])
    assert not records[-1]["resumable"]


def test_a_marker_that_cannot_be_written_still_lets_the_book_resume(tmp_path: Path) -> None:
    """Refusing to resume a book because a file would not write would be absurd."""
    paths = ProjectPaths.build(tmp_path)
    _marker(tmp_path).parent.mkdir(parents=True, exist_ok=True)
    _marker(tmp_path).mkdir()  # write_text on a directory raises OSError

    record = _record_gpu_context_loss(paths, _Db({1: 40}))

    assert record["attempt"] == 1
    assert record["resumable"]


def test_a_database_that_cannot_be_read_does_not_decide_the_run(tmp_path: Path) -> None:
    class _Broken:
        def chapter_progress_counts(self):
            raise RuntimeError("db locked")

    record = _record_gpu_context_loss(ProjectPaths.build(tmp_path), _Broken())

    assert record["resumable"]


def test_no_database_at_all_is_survivable(tmp_path: Path) -> None:
    assert _record_gpu_context_loss(ProjectPaths.build(tmp_path), None)["resumable"]


# --- the wiring, not just the helpers -------------------------------------------------
# The helpers above can all be right while run_worker still routes a lost context into the
# unrecoverable handler, which is the bug being fixed. These drive the real run_worker.

import os  # noqa: E402
from queue import Queue  # noqa: E402
from types import SimpleNamespace  # noqa: E402

from ebook_reader import worker as worker_module  # noqa: E402
from ebook_reader.config import build_settings, save_settings, settings_hash  # noqa: E402
from ebook_reader.database import ProjectDB  # noqa: E402
from ebook_reader.io_utils import sha256_file  # noqa: E402
from ebook_reader.models import BookStatus  # noqa: E402
from ebook_reader.pipeline import BookPipeline  # noqa: E402


def _book(tmp_path: Path):
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
    return paths, settings, db


def _run_worker_that_loses_the_gpu(monkeypatch, paths, message: str) -> list[dict]:
    class NoopThread:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        def start(self) -> None:
            pass

    class ContextLossPipeline:
        def __init__(self, *, paths, db, settings, **_kwargs) -> None:
            self.paths = paths
            self.db = db
            self.settings = settings

        def prepare_recovery(self) -> None:
            pass

        def run(self, *, recovery_already_run: bool) -> None:
            assert recovery_already_run is True
            try:
                raise RuntimeError(message)
            except RuntimeError as cause:
                raise RuntimeError("Không tổng hợp được segment c1_s2") from cause

        def refresh_terminal_reports(self) -> None:
            BookPipeline.refresh_terminal_reports_without_runtime(
                paths=self.paths,
                db=self.db,
                settings=self.settings,
            )

    monkeypatch.setattr(worker_module, "BookPipeline", ContextLossPipeline)
    monkeypatch.setattr(worker_module, "WorkerHeartbeat", NoopThread)
    monkeypatch.setattr(worker_module, "ParentWatchdog", NoopThread)
    monkeypatch.setattr(worker_module, "_configure_logging", lambda _path: None)
    monkeypatch.setattr(
        worker_module, "_apply_locked_model_cache_environment", lambda _settings: False
    )
    monkeypatch.setattr(worker_module, "_apply_model_network_policy", lambda _settings: False)
    monkeypatch.setattr(worker_module, "_validate_model_runtime_contract", lambda _settings: None)
    monkeypatch.setattr(worker_module, "set_worker_priority", lambda _priority: None)

    messages: Queue = Queue()
    event = SimpleNamespace(is_set=lambda: False)
    worker_module.run_worker(str(paths.root), messages, event, event, os.getpid())

    emitted = []
    while not messages.empty():
        emitted.append(messages.get_nowait())
    return [row for row in emitted if row["kind"] == "finished"]


def test_a_lost_context_ends_the_run_as_a_stop_not_a_failure(monkeypatch, tmp_path: Path) -> None:
    """The whole point: a fully checkpointed book must not be marked failed by a lid closing."""
    paths, _settings, db = _book(tmp_path)

    finished = _run_worker_that_loses_the_gpu(
        monkeypatch, paths, "CUDA error: unspecified launch failure"
    )

    assert len(finished) == 1
    payload = finished[0]
    assert payload["ok"] is True, "a failure here is what loses the night's work"
    assert payload["stopped"] is True, "the supervisor records 'stopped' from this"
    assert payload["gpu_context_lost"] is True, "and this is what tells the watchdog to restart"
    assert str(db.book()["status"]) == BookStatus.STOPPED.value
    codes = [str(row["code"]) for row in db.list_events()]
    assert "GPU_CONTEXT_LOST" in codes


def test_an_ordinary_error_still_fails_the_run(monkeypatch, tmp_path: Path) -> None:
    """The new branch must not swallow real failures into a silent restart loop."""
    paths, _settings, db = _book(tmp_path)

    finished = _run_worker_that_loses_the_gpu(monkeypatch, paths, "Ollama trả về JSON hỏng")

    assert finished[0]["ok"] is False
    assert finished[0]["critical"] is True
    assert str(db.book()["status"]) == BookStatus.ERROR.value


def test_a_gpu_that_never_makes_progress_eventually_fails(monkeypatch, tmp_path: Path) -> None:
    """Restarting is only right while it helps; a dead card must surface to a human."""
    paths, _settings, db = _book(tmp_path)
    marker = _marker(paths.root)
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(
        json.dumps({"attempt": GPU_CONTEXT_LOST_MAX_ATTEMPTS, "segments_done": 0}),
        encoding="utf-8",
    )

    finished = _run_worker_that_loses_the_gpu(
        monkeypatch, paths, "CUDA error: unspecified launch failure"
    )

    assert finished[0]["ok"] is False, "the sixth identical loss is not worth another restart"
    assert str(db.book()["status"]) == BookStatus.ERROR.value
