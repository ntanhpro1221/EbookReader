from __future__ import annotations

import json
import subprocess

import pytest

from ebook_reader.analysis import (
    ADDRESSEE_REPAIR_NOTE,
    ANALYSIS_OUTPUT_MAX_TOKENS,
    AnalysisRequestStopped,
    OllamaBookAnalyzer,
    OllamaStreamIncompleteError,
    _cmu_pronunciations,
    _identity_reconciliation_items,
    _name_candidate_contexts,
    _repair_vietnamese_syllable_boundaries,
    _validate,
    _valid_vietnamese_spoken_form,
    is_local_speaker,
    local_speaker_display,
)
from ebook_reader.config import build_settings


class FakeDB:
    def __init__(self):
        self.events = []
        self.pronunciations = []
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
        self.chapters = [{"id": 1, "title": "Chương 1"}]

    def list_segments(self, statuses=None):
        if statuses is not None:
            return []
        return self.rows

    def list_chapters(self):
        return self.chapters

    def event(self, level, code, message, details=None):
        self.events.append((level, code, message, details))

    def update_analysis(self, segment_id, data, low_confidence_threshold):
        self.updated.append((segment_id, data, low_confidence_threshold))

    def list_pronunciations(self, minimum_confidence=0.0):
        return [
            row
            for row in self.pronunciations
            if bool(row.get("locked", 0)) or float(row["confidence"]) >= minimum_confidence
        ]

    def upsert_pronunciation(
        self,
        *,
        surface,
        normalized_surface,
        spoken_form,
        confidence,
        source="analysis",
        locked=False,
    ):
        self.pronunciations = [
            row
            for row in self.pronunciations
            if row["normalized_surface"] != normalized_surface
        ]
        self.pronunciations.append(
            {
                "surface": surface,
                "normalized_surface": normalized_surface,
                "spoken_form": spoken_form,
                "confidence": confidence,
                "source": source,
                "locked": int(locked),
            }
        )


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


def test_name_candidates_include_speakers_and_one_off_capitalized_names() -> None:
    rows = [
        {
            "speaker": "Alisa",
            "text": "Alisa nhìn Michael bước vào. Alice chỉ xuất hiện một lần.",
        },
        {
            "speaker": "NARRATOR",
            "text": "Michael quay lại, còn Minh vẫn đứng yên.",
        },
    ]

    candidates = _name_candidate_contexts(rows)
    by_surface = {candidate["surface"]: candidate for candidate in candidates}

    assert set(by_surface) == {"Alisa", "Alice", "Michael"}
    assert by_surface["Alisa"]["is_speaker"] is True
    assert by_surface["Michael"]["occurrences"] == 2
    assert by_surface["Alice"]["occurrences"] == 1
    assert "Minh" not in by_surface


def test_vietnamese_spoken_form_requires_an_explicit_phonetic_rewrite() -> None:
    assert _valid_vietnamese_spoken_form("Michael", "Mai-cồ") is True
    assert _valid_vietnamese_spoken_form("Gary", "Ga-ri") is True
    assert _valid_vietnamese_spoken_form("John", "Giôn") is True
    assert _valid_vietnamese_spoken_form("Corella", "Cô-ren-la") is True
    assert _valid_vietnamese_spoken_form("Corella", "Co-rel-la") is False
    assert _valid_vietnamese_spoken_form("Gary", "Gary") is False
    assert _valid_vietnamese_spoken_form("Gary", "/ˈɡɛri/") is False
    assert _repair_vietnamese_syllable_boundaries("Aderon", "A-der-on") == "A-đe-ron"
    assert _repair_vietnamese_syllable_boundaries("Corella", "Co-rel-la") is None


def test_bundled_cmudict_identifies_common_english_names() -> None:
    pronunciations = _cmu_pronunciations(["Gary", "Michael", "Phong"])

    assert pronunciations["gary"] == "G EH1 R IY0"
    assert pronunciations["michael"] == "M AY1 K AH0 L"
    assert "phong" not in pronunciations


def test_required_name_pronunciation_pass_checkpoints_vietnamese_readings(monkeypatch) -> None:
    db = FakeDB()
    db.rows = [
        {
            "id": 1,
            "stable_id": "c1s1",
            "chapter_id": 1,
            "text": "Gary gặp Michael trong hành lang.",
            "kind_hint": "dialogue",
            "status": "analyzed",
            "speaker": "Gary",
        },
        {
            "id": 2,
            "stable_id": "c1s2",
            "chapter_id": 1,
            "text": "Michael gật đầu với Gary.",
            "kind_hint": "narration",
            "status": "analyzed",
            "speaker": "NARRATOR",
        },
    ]
    db.pronunciations = [
        {
            "surface": "Gary",
            "normalized_surface": "gary",
            "spoken_form": "Cách đọc phân tích cũ",
            "confidence": 0.99,
            "source": "analysis",
            "locked": 0,
        }
    ]
    analyzer = OllamaBookAnalyzer(build_settings(), db, lambda _message: None)
    monkeypatch.setattr(analyzer, "ensure_available", lambda: True)
    monkeypatch.setattr("ebook_reader.analysis.time.sleep", lambda _seconds: None)
    attempts = 0

    def fake_response(request, **_kwargs):
        nonlocal attempts
        attempts += 1
        assert "Michael→Mai-cồ" in request["prompt"]
        assert "G EH1 R IY0" in request["prompt"]
        name_schema = request["format"]["properties"]["names"]
        if attempts == 1:
            assert "M AY1 K AH0 L" in request["prompt"]
            assert name_schema["minItems"] == 2
            assert name_schema["maxItems"] == 2
            assert name_schema["items"]["properties"]["id"]["enum"] == ["N001", "N002"]
            return {
                "names": [
                    {
                        "id": "N001",
                        "convert": False,
                        "spoken_form": "Gary",
                        "confidence": 0.95,
                        "reason": "Kết quả phân loại sai cần retry",
                    },
                    {
                        "id": "N002",
                        "convert": True,
                        "spoken_form": "Mai-cồ",
                        "confidence": 0.96,
                        "reason": "Tên tiếng Anh",
                    },
                ]
            }
        assert name_schema["minItems"] == 1
        assert name_schema["maxItems"] == 1
        assert name_schema["items"]["properties"]["id"]["enum"] == ["N001"]
        assert "Không được lặp lại đáp án cũ" in request["prompt"]
        assert any(row["surface"] == "Michael" for row in db.pronunciations)
        return {
            "names": [
                {
                    "id": "N001",
                    "convert": True,
                    "spoken_form": "Ga-ri",
                    "confidence": 0.95,
                    "reason": "Tên tiếng Anh",
                }
            ]
        }

    monkeypatch.setattr(analyzer, "_stream_json_response", fake_response)

    assert analyzer.reconcile_name_pronunciations() == 2
    assert attempts == 2
    assert {
        row["surface"]: (row["spoken_form"], row["source"], row["locked"])
        for row in db.pronunciations
    } == {
        "Gary": ("Ga-ri", "english_name_transliteration", 1),
        "Michael": ("Mai-cồ", "english_name_transliteration", 1),
    }


def test_invalid_aderon_boundary_is_repaired_without_repeating_the_request(monkeypatch) -> None:
    db = FakeDB()
    db.rows = [
        {
            "id": 1,
            "stable_id": "c1s1",
            "chapter_id": 1,
            "text": "Giáo đường Aderon nằm ở trung tâm thành phố.",
            "kind_hint": "narration",
            "status": "analyzed",
            "speaker": "NARRATOR",
        }
    ]
    analyzer = OllamaBookAnalyzer(build_settings(), db, lambda _message: None)
    monkeypatch.setattr(analyzer, "ensure_available", lambda: True)
    attempts = 0

    def response(_request, **_kwargs):
        nonlocal attempts
        attempts += 1
        return {
            "names": [
                {
                    "id": "N001",
                    "convert": True,
                    "spoken_form": "A-der-on",
                    "confidence": 0.96,
                    "reason": "Tên fantasy",
                }
            ]
        }

    monkeypatch.setattr(analyzer, "_stream_json_response", response)

    assert analyzer.reconcile_name_pronunciations() == 1
    assert attempts == 1
    assert db.pronunciations[0]["spoken_form"] == "A-đe-ron"
    assert any(event[1] == "NAME_PRONUNCIATION_BOUNDARY_REPAIRED" for event in db.events)


def test_valid_names_are_checkpointed_when_another_name_exhausts_targeted_retries(
    monkeypatch,
) -> None:
    db = FakeDB()
    db.rows = [
        {
            "id": 1,
            "stable_id": "c1s1",
            "chapter_id": 1,
            "text": "Gary gặp Corella trong hành lang.",
            "kind_hint": "dialogue",
            "status": "analyzed",
            "speaker": "Gary",
        }
    ]
    analyzer = OllamaBookAnalyzer(build_settings(), db, lambda _message: None)
    monkeypatch.setattr(analyzer, "ensure_available", lambda: True)
    monkeypatch.setattr("ebook_reader.analysis.time.sleep", lambda _seconds: None)
    requested_ids: list[list[str]] = []

    def response(request, **_kwargs):
        ids = request["format"]["properties"]["names"]["items"]["properties"]["id"]["enum"]
        requested_ids.append(ids)
        names = []
        for item_id in ids:
            if item_id == "N001":
                names.append(
                    {
                        "id": item_id,
                        "convert": True,
                        "spoken_form": "Cô-rel-la",
                        "confidence": 0.9,
                        "reason": "Cố ý không hợp lệ",
                    }
                )
            else:
                names.append(
                    {
                        "id": item_id,
                        "convert": True,
                        "spoken_form": "Ga-ri",
                        "confidence": 0.95,
                        "reason": "Tên tiếng Anh",
                    }
                )
        return {"names": names}

    monkeypatch.setattr(analyzer, "_stream_json_response", response)

    with pytest.raises(RuntimeError, match="Corella"):
        analyzer.reconcile_name_pronunciations()

    assert requested_ids == [["N001", "N002"], ["N001"], ["N001"]]
    assert {row["surface"] for row in db.pronunciations} == {"Gary"}


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


def test_addressee_name_cannot_become_the_local_speaker_identity() -> None:
    group = [
        {
            **analysis_group()[0],
            "text": "“Anh Lucien!”",
            "kind_hint": "dialogue",
        },
        {
            **analysis_group()[1],
            "text": "“Anh tỉnh rồi?”",
            "kind_hint": "dialogue",
        },
    ]
    items = []
    for row in group:
        item = analysis_item(row["stable_id"])
        item.update(
            {
                "kind": "dialogue",
                "speaker": "NPC_LOCAL:Lucien",
                "gender": "male",
            }
        )
        items.append(item)

    validated = _validate(group, {"segments": items}, local_scope="b0002")
    speakers = [validated[row["stable_id"]]["speaker"] for row in group]

    assert len(set(speakers)) == 1
    assert local_speaker_display(speakers[0]) == "NPC người gọi Lucien"
    assert all(ADDRESSEE_REPAIR_NOTE in validated[row["stable_id"]]["notes"] for row in group)


def test_bare_name_vocative_is_repaired_but_self_introduction_is_not() -> None:
    addressed = {
        **analysis_group()[0],
        "text": "“Iven, đỡ mẹ con rồi về nhà thôi.”",
        "kind_hint": "dialogue",
    }
    self_intro = {
        **analysis_group()[1],
        "text": "“Tôi là Lucien.”",
        "kind_hint": "dialogue",
    }
    addressed_item = analysis_item(addressed["stable_id"])
    addressed_item.update({"kind": "dialogue", "speaker": "Iven", "gender": "male"})
    self_intro_item = analysis_item(self_intro["stable_id"])
    self_intro_item.update({"kind": "dialogue", "speaker": "Lucien", "gender": "male"})

    validated = _validate(
        [addressed, self_intro],
        {"segments": [addressed_item, self_intro_item]},
        local_scope="b0003",
    )

    assert local_speaker_display(validated[addressed["stable_id"]]["speaker"]) == "NPC người gọi Iven"
    assert validated[self_intro["stable_id"]]["speaker"] == "Lucien"


def test_identity_reconciliation_uses_chapter_boundary_context_for_renamed_protagonist(
    monkeypatch,
) -> None:
    db = FakeDB()
    db.chapters = [
        {"id": 1, "title": "000"},
        {"id": 2, "title": "001"},
    ]
    db.rows = [
        {
            "id": 1,
            "stable_id": "c1s49",
            "chapter_id": 1,
            "seq": 49,
            "text": "Hạ Phong muốn được yên tĩnh suy nghĩ về cuộc đời mình.",
            "kind_hint": "narration",
            "status": "analyzed",
            "speaker": "NARRATOR",
        },
        {
            "id": 2,
            "stable_id": "c1s51",
            "chapter_id": 1,
            "seq": 51,
            "text": "‘Phù thủy đó có liên quan đến mình?’",
            "kind_hint": "thought",
            "status": "analyzed",
            "speaker": "Hạ Phong",
        },
        {
            "id": 3,
            "stable_id": "c2s4",
            "chapter_id": 2,
            "seq": 4,
            "text": (
                "Lucien đã chấp nhận thân phận của mình, chôn vùi mọi ký ức quá khứ trong lòng."
            ),
            "kind_hint": "narration",
            "status": "analyzed",
            "speaker": "NARRATOR",
        },
        {
            "id": 4,
            "stable_id": "c2s5",
            "chapter_id": 2,
            "seq": 5,
            "text": "‘Không biết mình có cơ hội nào học được thần thuật không nhỉ?’",
            "kind_hint": "thought",
            "status": "analyzed",
            "speaker": "Lucien",
        },
    ]
    analyzer = OllamaBookAnalyzer(build_settings(), db, lambda _message: None)
    monkeypatch.setattr(analyzer, "ensure_available", lambda: True)

    items = _identity_reconciliation_items(db.rows, {1: "000", 2: "001"})
    assert [item["name"] for item in items] == ["Hạ Phong", "Lucien"]

    def response(request, **_kwargs):
        prompt = request["prompt"]
        assert "Hạ Phong muốn được yên tĩnh" in prompt
        assert "Lucien đã chấp nhận thân phận" in prompt
        assert "Tên trước và sau khi chuyển sinh" in prompt
        return {
            "groups": [
                {
                    "canonical": "Lucien",
                    "aliases": ["Hạ Phong", "Lucien"],
                    "confidence": 0.98,
                    "reason": "Cùng một nhân vật sau khi chuyển sinh và nhận thân phận mới.",
                }
            ]
        }

    monkeypatch.setattr(analyzer, "_stream_json_response", response)

    assert analyzer.reconcile_aliases() == {"Hạ Phong": "Lucien"}


def test_onomatopoeia_remains_normal_narration() -> None:
    row = {
        **analysis_group()[0],
        "kind_hint": "narration",
        "text": "Rầm! Cánh cửa bật mở.",
    }
    item = analysis_item(row["stable_id"])
    item.update({"kind": "narration", "speaker": "UNKNOWN"})

    validated = _validate([row], {"segments": [item]})

    assert validated[row["stable_id"]]["kind"] == "narration"
    assert validated[row["stable_id"]]["speaker"] == "NARRATOR"


def test_analysis_cannot_invent_an_unsupported_effect_kind() -> None:
    row = {**analysis_group()[0], "kind_hint": "dialogue", "text": "“Ha…”"}
    item = analysis_item(row["stable_id"])
    item.update({"kind": "vocal_effect", "speaker": "Lucien"})

    validated = _validate([row], {"segments": [item]})

    assert validated[row["stable_id"]]["kind"] == "dialogue"
    assert validated[row["stable_id"]]["speaker"] == "Lucien"


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
