from __future__ import annotations

import json
import hashlib
import io
import sqlite3
import subprocess
from pathlib import Path

import pytest

from ebook_reader import cli
from ebook_reader import background_runner
from ebook_reader.background_runner import BackgroundStatus
from ebook_reader.config import build_settings
from ebook_reader.database import ProjectDB
from ebook_reader.project import create_or_open_project


def _write_sources(root: Path, names: list[str]) -> list[Path]:
    root.mkdir(parents=True, exist_ok=True)
    paths = []
    for index, name in enumerate(names):
        path = root / name
        path.write_text(f"Chương {index + 1}. Nội dung kiểm thử.", encoding="utf-8")
        paths.append(path)
    return paths


def _create_project(tmp_path: Path, names: list[str] | None = None) -> Path:
    sources = _write_sources(tmp_path / "sources", names or ["000.txt", "001.txt"])
    paths, _db, _settings = create_or_open_project(
        sources,
        tmp_path / "out",
        build_settings("high_quality"),
        "CLI Test",
    )
    return paths.root


def test_numeric_range_is_inclusive_and_preserves_explicit_zero_padding() -> None:
    assert cli._numeric_range_names("000..003") == ["000", "001", "002", "003"]
    assert cli._numeric_range_names("0..3") == ["0", "1", "2", "3"]
    assert cli._numeric_range_names("0..3", width=3) == ["000", "001", "002", "003"]


def test_numeric_range_rejects_descending_or_excessive_selection() -> None:
    with pytest.raises(cli.CliUsageError, match="greater"):
        cli._numeric_range_names("9..1")
    with pytest.raises(cli.CliUsageError, match="cannot select"):
        cli._numeric_range_names(f"0..{cli.MAX_RANGE_ITEMS}")


def test_resolve_input_range_selects_exact_files_and_natural_sorts(tmp_path: Path) -> None:
    source_dir = tmp_path / "book"
    _write_sources(source_dir, ["002.txt", "000.txt", "001.txt", "100.txt"])

    selected = cli.resolve_input_selection(source_dir=source_dir, range_spec="000..002")

    assert [path.name for path in selected] == ["000.txt", "001.txt", "002.txt"]


def test_resolve_explicit_files_rejects_duplicates_and_missing_range_member(tmp_path: Path) -> None:
    paths = _write_sources(tmp_path / "book", ["000.txt"])
    with pytest.raises(cli.CliUsageError, match="Duplicate"):
        cli.resolve_input_selection(files=[paths[0], paths[0]])
    with pytest.raises(FileNotFoundError, match="001.txt"):
        cli.resolve_input_selection(source_dir=paths[0].parent, range_spec="000..001")


def test_create_dry_run_hashes_manifest_without_writing_output(tmp_path: Path, capsys) -> None:
    source_dir = tmp_path / "book"
    _write_sources(source_dir, ["000.txt", "001.txt", "002.txt"])
    output_root = tmp_path / "must-not-exist"

    exit_code = cli.main(
        [
            "create",
            "--source-dir",
            str(source_dir),
            "--range",
            "000..002",
            "--output-root",
            str(output_root),
            "--dry-run",
            "--json",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == cli.EXIT_OK
    assert payload["ok"] is True
    assert payload["data"]["chapter_count"] == 3
    assert len(payload["data"]["input_manifest_hash"]) == 64
    assert payload["data"]["dry_run"] is True
    assert not output_root.exists()


def test_create_range_writes_exactly_one_hundred_naturally_sorted_chapters(
    tmp_path: Path,
    capsys,
) -> None:
    source_dir = tmp_path / "book"
    _write_sources(source_dir, [f"{index:03d}.txt" for index in reversed(range(100))])

    exit_code = cli.main(
        [
            "create",
            "--source-dir",
            str(source_dir),
            "--range",
            "000..099",
            "--output-root",
            str(tmp_path / "out"),
            "--title",
            "One Hundred",
            "--json",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    project_root = Path(payload["data"]["project_root"])
    chapters = ProjectDB(project_root / "project.sqlite3").list_chapters()
    assert exit_code == cli.EXIT_OK
    assert len(chapters) == 100
    assert Path(str(chapters[0]["input_path"])).name == "000.txt"
    assert Path(str(chapters[-1]["input_path"])).name == "099.txt"


def test_status_and_integrity_validation_work_before_first_run(tmp_path: Path) -> None:
    project_root = _create_project(tmp_path)

    status = cli.collect_project_status(project_root)
    validation = cli.validate_project(project_root)

    assert status["book_status"] == "created"
    assert status["chapters"]["total"] == 2
    assert validation["ok"] is True
    assert validation["checks"]["source_files"] is True
    assert validation["checks"]["all_chapters_complete"] is False


def test_status_is_strictly_read_only_for_database_and_project_sidecars(tmp_path: Path) -> None:
    project_root = _create_project(tmp_path)

    def snapshot() -> dict[str, tuple[int, int, str]]:
        result: dict[str, tuple[int, int, str]] = {}
        for path in sorted((item for item in project_root.rglob("*") if item.is_file())):
            raw = path.read_bytes()
            stat = path.stat()
            result[str(path.relative_to(project_root))] = (
                stat.st_mtime_ns,
                stat.st_size,
                hashlib.sha256(raw).hexdigest(),
            )
        return result

    before = snapshot()
    status = cli.collect_project_status(project_root)
    after = snapshot()

    assert status["book_status"] == "created"
    assert after == before


def test_status_reads_live_wal_via_disposable_snapshot_without_touching_sidecars(tmp_path: Path) -> None:
    project_root = _create_project(tmp_path)
    database_path = project_root / "project.sqlite3"
    writer = sqlite3.connect(database_path)
    try:
        writer.execute("PRAGMA journal_mode=WAL")
        writer.execute("UPDATE book SET stage='live_wal_stage' WHERE id=1")
        writer.commit()

        def snapshot() -> dict[str, tuple[int, int, str]]:
            result = {}
            for path in project_root.glob("project.sqlite3*"):
                stat = path.stat()
                result[path.name] = (stat.st_mtime_ns, stat.st_size, hashlib.sha256(path.read_bytes()).hexdigest())
            return result

        before = snapshot()
        status = cli.collect_project_status(project_root)
        after = snapshot()
    finally:
        writer.close()

    assert status["stage"] == "live_wal_stage"
    assert after == before


def test_validate_detects_source_change_and_require_complete_gate(tmp_path: Path) -> None:
    project_root = _create_project(tmp_path)
    db = ProjectDB(project_root / "project.sqlite3")
    source = Path(str(db.list_chapters()[0]["input_path"]))
    source.write_text("Nội dung đã bị thay đổi.", encoding="utf-8")

    validation = cli.validate_project(project_root, require_complete=True)

    assert validation["ok"] is False
    assert any("Source chapter" in error for error in validation["errors"])
    assert any("Completion required" in error for error in validation["errors"])


def test_report_command_returns_compact_quality_summary(tmp_path: Path, capsys) -> None:
    project_root = _create_project(tmp_path)
    report_path = project_root / "output" / "reports" / "audiobook_quality_report.json"
    report_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "book": {"overall_verdict": "review", "chapters_total": 2},
                "global_gates": {"casting_finalized": False},
                "review_required": {"chapters": [{"chapter_index": 1}], "segments": [{"id": 1}]},
            }
        ),
        encoding="utf-8",
    )

    exit_code = cli.main(["report", str(project_root), "--json"])

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == cli.EXIT_OK
    assert payload["data"]["book"]["overall_verdict"] == "review"
    assert payload["data"]["review_required"] == {"chapter_count": 1, "segment_count": 1}


def test_test_component_mapping_and_subprocess_result_are_stable(
    tmp_path: Path,
    monkeypatch,
) -> None:
    paths, components = cli._selected_test_paths(["parser", "db", "parser"])
    assert components == ["parser", "db", "parser"]
    assert paths == ["tests/test_text_processing_safety.py", "tests/test_database_safety.py"]

    captured: dict[str, object] = {}

    def fake_run(command, **kwargs):
        captured["command"] = command
        captured["cwd"] = kwargs["cwd"]
        return subprocess.CompletedProcess(command, 0, "2 passed\n", "")

    monkeypatch.setattr(cli.subprocess, "run", fake_run)
    args = cli.build_parser().parse_args(["test", "config", "parser", "--json"])
    result = cli._command_test(args)

    assert result.ok is True
    assert result.data["returncode"] == 0
    assert result.data["components"] == ["config", "parser"]
    assert captured["command"] == [
        cli.sys.executable,
        "-m",
        "pytest",
        "-q",
        "tests/test_config.py",
        "tests/test_text_processing_safety.py",
    ]


def test_foreground_run_uses_production_worker_without_gui(
    tmp_path: Path,
    monkeypatch,
) -> None:
    project_root = _create_project(tmp_path)
    monkeypatch.setattr(cli, "_background_status", lambda _root: {"running": False})

    def fake_worker(project_root_str, message_queue, _pause_event, _stop_event, _parent_pid):
        db = ProjectDB(Path(project_root_str) / "project.sqlite3")
        db.update_book(status="stopped", stage="stopped")
        message_queue.put({"kind": "finished", "ok": True, "stopped": True, "text": "stopped"})

    monkeypatch.setattr(cli, "_invoke_production_worker", fake_worker)

    result = cli.run_project_foreground(project_root, echo=False)

    assert result.ok is True
    assert result.data["mode"] == "foreground"
    assert result.data["finished_event"]["stopped"] is True


def test_run_defaults_to_ready_handshaken_background_status(
    tmp_path: Path,
    monkeypatch,
) -> None:
    project_root = _create_project(tmp_path)
    expected = BackgroundStatus(
        project_root=project_root,
        state="running",
        running=True,
        instance_id="instance-1",
        supervisor_pid=123,
    )
    monkeypatch.setattr(background_runner, "start_background", lambda *_args, **_kwargs: expected)
    args = cli.build_parser().parse_args(["run", str(project_root), "--json"])

    result = cli._command_run(args)

    assert result.ok is True
    assert result.data["mode"] == "background"
    assert result.data["background"]["state"] == "running"
    assert result.data["background"]["instance_id"] == "instance-1"


def test_run_json_returns_nonzero_when_background_fails_immediately_after_ready(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    project_root = _create_project(tmp_path)

    def fail_after_ready(*_args, **_kwargs):
        raise background_runner.BackgroundStartError("worker failed immediately")

    monkeypatch.setattr(background_runner, "start_background", fail_after_ready)

    exit_code = cli.main(["run", str(project_root), "--json"])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == cli.EXIT_RUNTIME_ERROR
    assert payload["ok"] is False
    assert payload["exit_code"] == cli.EXIT_RUNTIME_ERROR
    assert payload["error"] == "worker failed immediately"


def test_waiting_stop_returns_nonzero_if_supervisor_is_still_running(
    tmp_path: Path,
    monkeypatch,
) -> None:
    project_root = _create_project(tmp_path)
    timed_out = BackgroundStatus(
        project_root=project_root,
        state="stopping",
        running=True,
        instance_id="instance-1",
    )
    monkeypatch.setattr(background_runner, "request_stop", lambda *_args, **_kwargs: timed_out)
    args = cli.build_parser().parse_args(["stop", str(project_root), "--timeout", "0.1", "--json"])

    result = cli._command_stop(args)

    assert result.exit_code == cli.EXIT_RUNTIME_ERROR
    assert "terminal state" in str(result.error)


def test_json_usage_error_has_stable_exit_code(capsys) -> None:
    exit_code = cli.main(["create", "--json"])

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == cli.EXIT_USAGE
    assert payload["schema_version"] == cli.CLI_SCHEMA_VERSION
    assert payload["exit_code"] == cli.EXIT_USAGE
    assert payload["ok"] is False


def test_corrupt_database_still_returns_one_json_runtime_error(tmp_path: Path, capsys) -> None:
    project_root = _create_project(tmp_path)
    (project_root / "project.sqlite3").write_bytes(b"not a sqlite database")

    exit_code = cli.main(["status", str(project_root), "--json"])

    output = capsys.readouterr().out
    payload = json.loads(output)
    assert output.count("\n") == 1
    assert exit_code == cli.EXIT_RUNTIME_ERROR
    assert payload["exit_code"] == cli.EXIT_RUNTIME_ERROR
    assert payload["ok"] is False


def test_unexpected_exception_and_ascii_console_still_emit_utf8_json(
    tmp_path: Path,
    monkeypatch,
) -> None:
    project_root = _create_project(tmp_path)
    output_buffer = io.BytesIO()
    error_buffer = io.BytesIO()
    output_stream = io.TextIOWrapper(output_buffer, encoding="ascii", errors="strict")
    error_stream = io.TextIOWrapper(error_buffer, encoding="ascii", errors="strict")
    monkeypatch.setattr(cli.sys, "stdout", output_stream)
    monkeypatch.setattr(cli.sys, "stderr", error_stream)

    def unexpected(_project_root):
        raise TypeError("lỗi tiếng Việt bất ngờ")

    monkeypatch.setattr(cli, "collect_project_status", unexpected)
    exit_code = cli.main(["status", str(project_root), "--json"])
    output_stream.flush()
    payload = json.loads(output_buffer.getvalue().decode("utf-8"))

    assert exit_code == cli.EXIT_RUNTIME_ERROR
    assert payload["error"] == "lỗi tiếng Việt bất ngờ"
    assert payload["exit_code"] == cli.EXIT_RUNTIME_ERROR
