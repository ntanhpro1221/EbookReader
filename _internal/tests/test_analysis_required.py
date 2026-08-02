from __future__ import annotations

import json
import subprocess

import pytest

from ebook_reader.analysis import (
    ANALYSIS_OUTPUT_MAX_TOKENS,
    AnalysisRequestStopped,
    OllamaBookAnalyzer,
    OllamaStreamIncompleteError,
    _validate,
    is_local_speaker,
    local_speaker_display,
)
from ebook_reader.config import build_settings


class FakeDB:
    def __init__(self):
        self.events = []
        self.updated = []
        self.rows = [
            {
                "id": 1,
                "stable_id": "c1s1",
                "chapter_id": 1,
                "text": "Một đoạn văn cần được phân tích.",
                "kind_hint": "narration",
                "status": "pending",
                "speaker": None,
            }
        ]

    def list_segments(self, statuses=None):
        if statuses is not None:
            return []
        return self.rows

    def list_chapters(self):
        return [{"id": 1, "title": "Chương 1"}]

    def event(self, level, code, message, details=None):
        self.events.append((level, code, message, details))

    def update_analysis(self, segment_id, data, low_confidence_threshold):
        self.updated.append((segment_id, data, low_confidence_threshold))


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload
        self.encoding = None
        self.closed = False

    def raise_for_status(self):
        return None

    def iter_lines(self, decode_unicode=False):
        line = json.dumps(
            {
                "response": json.dumps(self.payload, ensure_ascii=False),
                "done": True,
            },
            ensure_ascii=False,
        )
        yield line if decode_unicode else line.encode("utf-8")

    def close(self):
        self.closed = True


class FakeSession:
    def __init__(self, payload):
        self.payload = payload
        self.request = None
        self.response = FakeResponse(payload)

    def post(self, _url, *, json, timeout, stream):
        self.request = {"json": json, "timeout": timeout, "stream": stream}
        return self.response


def analysis_item(segment_id):
    return {
        "id": segment_id,
        "kind": "narration",
        "speaker": "NARRATOR",
        "gender": "unknown",
        "age": "unknown",
        "emotion": "neutral",
        "intensity": 0,
        "pace": "normal",
        "volume": "normal",
        "confidence": 1.0,
        "personality_hint": "",
        "notes": "",
    }


def analysis_group():
    return [
        {
            "id": 1,
            "stable_id": "c00001_s0000000_ba30c9fbb6b1",
            "chapter_id": 1,
            "text": "Đoạn đầu tiên.",
            "kind_hint": "narration",
        },
        {
            "id": 2,
            "stable_id": "c00001_s0000001_8039b1d43f9d",
            "chapter_id": 1,
            "text": "Đoạn thứ hai.",
            "kind_hint": "narration",
        },
    ]


def test_required_analysis_does_not_silently_fall_back(monkeypatch) -> None:
    analyzer = OllamaBookAnalyzer(build_settings(), FakeDB(), lambda _message: None)
    monkeypatch.setattr(analyzer, "ensure_available", lambda: False)
    with pytest.raises(RuntimeError, match="Pipeline dừng"):
        analyzer.analyze_all(lambda: False)


def test_required_analysis_stops_when_every_request_fails(monkeypatch) -> None:
    db = FakeDB()
    analyzer = OllamaBookAnalyzer(build_settings(), db, lambda _message: None)
    monkeypatch.setattr(analyzer, "ensure_available", lambda: True)
    monkeypatch.setattr(analyzer, "_request", lambda _group: (_ for _ in ()).throw(RuntimeError("timeout")))
    monkeypatch.setattr("ebook_reader.analysis.time.sleep", lambda _seconds: None)

    with pytest.raises(RuntimeError, match="Phân tích bắt buộc thất bại"):
        analyzer.analyze_all(lambda: False)

    assert any(event[1] == "REQUIRED_ANALYSIS_BATCH_FAILED" for event in db.events)


def test_request_uses_constrained_batch_ids_and_restores_stable_ids() -> None:
    group = analysis_group()
    session = FakeSession({"segments": [analysis_item("S001"), analysis_item("S002")]})
    analyzer = OllamaBookAnalyzer(build_settings(), FakeDB(), lambda _message: None)
    analyzer.session = session

    payload = analyzer._request(group)

    assert [item["id"] for item in payload["segments"]] == [row["stable_id"] for row in group]
    assert session.request is not None
    request = session.request["json"]
    segment_schema = request["format"]["properties"]["segments"]
    assert segment_schema["minItems"] == len(group)
    assert segment_schema["maxItems"] == len(group)
    assert segment_schema["items"]["properties"]["id"]["enum"] == ["S001", "S002"]
    assert request["format"]["properties"]["pronunciations"]["maxItems"] >= len(group)
    assert request["options"]["num_predict"] <= ANALYSIS_OUTPUT_MAX_TOKENS
    assert request["stream"] is True
    assert session.request["stream"] is True
    assert session.response.closed is True
    assert '"id": "S001"' in request["prompt"]
    assert group[0]["stable_id"] not in request["prompt"]


def test_unknown_batch_id_is_not_fuzzily_mapped() -> None:
    group = analysis_group()
    session = FakeSession({"segments": [analysis_item("S001"), analysis_item("S0002")]})
    analyzer = OllamaBookAnalyzer(build_settings(), FakeDB(), lambda _message: None)
    analyzer.session = session

    payload = analyzer._request(group)
    validated = _validate(group, payload)

    assert list(validated) == [group[0]["stable_id"]]


def test_local_npc_labels_are_distinct_and_scoped_to_batch() -> None:
    group = analysis_group()
    first = analysis_item(group[0]["stable_id"])
    first.update({"kind": "dialogue", "speaker": "NPC_LOCAL:áo xanh", "gender": "male"})
    second = analysis_item(group[1]["stable_id"])
    second.update({"kind": "dialogue", "speaker": "NPC_LOCAL:áo đỏ", "gender": "male"})

    validated = _validate(group, {"segments": [first, second]}, local_scope="b0007")
    speakers = [validated[row["stable_id"]]["speaker"] for row in group]

    assert speakers[0] != speakers[1]
    assert all(is_local_speaker(speaker) for speaker in speakers)
    assert "c00001::b0007" in speakers[0]
    assert local_speaker_display(speakers[0]) == "NPC áo xanh"


def test_source_effect_kinds_cannot_be_overwritten_by_analysis() -> None:
    vocal_row = {
        **analysis_group()[0],
        "kind_hint": "vocal_effect",
        "text": "“Ha…”",
    }
    effect_item = analysis_item(vocal_row["stable_id"])
    effect_item.update({"kind": "dialogue", "speaker": "Lucien"})
    sfx_row = {
        **analysis_group()[1],
        "kind_hint": "text_sfx",
        "text": "Rầm!",
    }
    sfx_item = analysis_item(sfx_row["stable_id"])
    sfx_item.update({"kind": "dialogue", "speaker": "UNKNOWN"})

    validated = _validate([vocal_row, sfx_row], {"segments": [effect_item, sfx_item]})

    assert validated[vocal_row["stable_id"]]["kind"] == "vocal_effect"
    assert validated[vocal_row["stable_id"]]["speaker"] == "Lucien"
    assert validated[sfx_row["stable_id"]]["kind"] == "text_sfx"
    assert validated[sfx_row["stable_id"]]["speaker"] == "NARRATOR"


def test_analysis_cannot_invent_an_unsupported_effect_kind() -> None:
    row = analysis_group()[0]
    item = analysis_item(row["stable_id"])
    item.update({"kind": "vocal_effect", "speaker": "Lucien"})

    validated = _validate([row], {"segments": [item]})

    assert validated[row["stable_id"]]["kind"] == row["kind_hint"]


def test_thought_uses_narrator_only_when_explicit_fallback_is_enabled() -> None:
    row = analysis_group()[0]
    narrator_thought = analysis_item(row["stable_id"])
    narrator_thought.update({"kind": "thought", "speaker": "NARRATOR"})

    assert _validate([row], {"segments": [narrator_thought]}) == {}
    fallback = _validate(
        [row],
        {"segments": [narrator_thought]},
        allow_unresolved_thought_narrator=True,
    )
    assert fallback[row["stable_id"]]["speaker"] == "NARRATOR"
    assert "không xác định được người đang nghĩ" in fallback[row["stable_id"]]["notes"]

    character_thought = {**narrator_thought, "speaker": "Alisa", "gender": "female"}
    validated = _validate([row], {"segments": [character_thought]})

    assert validated[row["stable_id"]]["kind"] == "thought"
    assert validated[row["stable_id"]]["speaker"] == "Alisa"


def test_unresolved_thought_retries_then_falls_back_to_narrator(monkeypatch) -> None:
    db = FakeDB()
    db.rows[0].update({"text": "(Mình nên làm gì bây giờ?)", "kind_hint": "thought"})
    settings = build_settings()
    logs: list[str] = []
    analyzer = OllamaBookAnalyzer(settings, db, logs.append)
    monkeypatch.setattr(analyzer, "ensure_available", lambda: True)
    monkeypatch.setattr("ebook_reader.analysis.time.sleep", lambda _seconds: None)
    attempts = 0

    def unresolved_request(_group, **_kwargs):
        nonlocal attempts
        attempts += 1
        item = analysis_item("c1s1")
        item.update({"kind": "thought", "speaker": "UNKNOWN"})
        return {"segments": [item]}

    monkeypatch.setattr(analyzer, "_request", unresolved_request)

    analyzer.analyze_all(lambda: False)

    assert attempts == settings["analysis"]["max_retries"]
    assert db.updated[0][1]["kind"] == "thought"
    assert db.updated[0][1]["speaker"] == "NARRATOR"
    assert any(event[1] == "THOUGHT_SPEAKER_NARRATOR_FALLBACK" for event in db.events)
    assert any("dùng giọng người kể" in message for message in logs)


def test_streaming_analysis_request_can_be_cancelled() -> None:
    group = analysis_group()
    session = FakeSession({"segments": [analysis_item("S001"), analysis_item("S002")]})
    analyzer = OllamaBookAnalyzer(build_settings(), FakeDB(), lambda _message: None)
    analyzer.session = session
    checks = 0

    def stop_requested() -> bool:
        nonlocal checks
        checks += 1
        return checks > 1

    with pytest.raises(AnalysisRequestStopped):
        analyzer._request(group, stop_requested=stop_requested)

    assert session.response.closed is True


def test_incomplete_stream_raises_specific_error_and_closes_response() -> None:
    group = analysis_group()
    session = FakeSession({"segments": [analysis_item("S001")]})

    class IncompleteResponse(FakeResponse):
        def iter_lines(self, decode_unicode=False):
            line = json.dumps({"response": '{"segments":[', "done": False})
            yield line if decode_unicode else line.encode("utf-8")

    session.response = IncompleteResponse({})
    analyzer = OllamaBookAnalyzer(build_settings(), FakeDB(), lambda _message: None)
    analyzer.session = session

    with pytest.raises(OllamaStreamIncompleteError, match="13 response chars"):
        analyzer._request(group)

    assert session.response.closed is True


def test_incomplete_stream_splits_batch_instead_of_retrying_same_size(monkeypatch) -> None:
    db = FakeDB()
    db.rows = [
        {
            "id": index,
            "stable_id": f"c1s{index}",
            "chapter_id": 1,
            "text": f"Đoạn {index}.",
            "kind_hint": "narration",
            "status": "pending",
            "speaker": None,
        }
        for index in range(1, 5)
    ]
    settings = build_settings(
        overrides={"analysis": {"batch_segments": 4, "batch_chars": 10000}}
    )
    logs: list[str] = []
    analyzer = OllamaBookAnalyzer(settings, db, logs.append)
    monkeypatch.setattr(analyzer, "ensure_available", lambda: True)
    request_sizes: list[int] = []

    def request(group, **_kwargs):
        request_sizes.append(len(group))
        if len(group) == 4:
            raise OllamaStreamIncompleteError("incomplete test stream")
        return {
            "segments": [analysis_item(str(row["stable_id"])) for row in group],
        }

    monkeypatch.setattr(analyzer, "_request", request)

    analyzer.analyze_all(lambda: False)

    assert request_sizes == [4, 2, 2]
    assert len(db.updated) == 4
    assert any("tự chia thành 2 + 2 segment" in message for message in logs)


def test_analyzer_starts_and_stops_only_its_managed_ollama_process(
    monkeypatch,
    tmp_path,
) -> None:
    logs: list[str] = []
    analyzer = OllamaBookAnalyzer(build_settings(), FakeDB(), logs.append)
    runtime_root = tmp_path / "runtime"
    monkeypatch.setenv("EBOOK_READER_RUNTIME", str(runtime_root))
    availability = iter((False, True))
    monkeypatch.setattr(analyzer, "_available", lambda: next(availability))
    monkeypatch.setattr("ebook_reader.analysis.shutil.which", lambda _name: "ollama.exe")

    class TagsResponse:
        @staticmethod
        def json():
            return {"models": [{"name": "qwen3:8b"}]}

    class StartupSession:
        @staticmethod
        def get(_url, timeout):
            assert timeout == 10
            return TagsResponse()

    class ManagedProcess:
        pid = 4242

        @staticmethod
        def poll():
            return None

    managed = ManagedProcess()
    popen_calls: list[tuple[str, object]] = []

    def start_managed_process(*_args, **kwargs):
        popen_calls.append((kwargs["stdout"].name, kwargs["stderr"]))
        return managed

    monkeypatch.setattr("ebook_reader.analysis.subprocess.Popen", start_managed_process)
    terminated: list[tuple[int, float]] = []
    monkeypatch.setattr(
        "ebook_reader.analysis.terminate_process_tree",
        lambda pid, *, grace_seconds: terminated.append((pid, grace_seconds)),
    )
    analyzer.session = StartupSession()

    assert analyzer.ensure_available() is True
    assert analyzer._managed_ollama_process is managed
    expected_log = runtime_root / "logs" / "ollama-server.log"
    assert analyzer._managed_ollama_log_path == expected_log
    assert popen_calls == [(str(expected_log), subprocess.STDOUT)]
    assert "Ebook Reader started Ollama" in expected_log.read_text(encoding="utf-8")
    analyzer._stop_managed_ollama()
    analyzer._stop_managed_ollama()

    assert terminated == [(managed.pid, 3.0)]
    assert any("tự khởi động Ollama ẩn" in message for message in logs)
    assert any("Đã dừng Ollama ẩn" in message for message in logs)
