from __future__ import annotations

import json
import re
import subprocess
from itertools import product

import pytest

from ebook_reader.analysis import (
    ADDRESSEE_REPAIR_NOTE,
    ANALYSIS_OUTPUT_MAX_TOKENS,
    CMUDICT_PATH,
    EXPLICIT_ATTRIBUTION_NOTE,
    NON_VIETNAMESE_SYLLABLE_CODA_PATTERN,
    VIETNAMESE_SPOKEN_FORM_PATTERN,
    AnalysisOutputBudgetError,
    AnalysisRequestStopped,
    AnalysisWallTimeoutError,
    OllamaBookAnalyzer,
    OllamaStreamIncompleteError,
    _cmu_pronunciation_to_vietnamese,
    _cmu_pronunciations,
    _local_scope_for_group,
    _local_name_fallback,
    _name_candidate_contexts,
    _repair_vietnamese_syllable_boundaries,
    _semantic_delivery_issues,
    _valid_vietnamese_spoken_form,
    _validate,
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
        "notes": "Ngữ cảnh phù hợp với cách thể hiện.",
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


def test_semantic_retry_feedback_uses_only_constrained_batch_ids() -> None:
    group = analysis_group()
    session = FakeSession({"segments": [analysis_item("S001"), analysis_item("S002")]})
    analyzer = OllamaBookAnalyzer(build_settings(), FakeDB(), lambda _message: None)
    analyzer.session = session

    analyzer._request(
        group,
        validation_feedback={
            str(group[0]["stable_id"]): "emotion=happy mâu thuẫn với cue afraid",
        },
    )

    assert session.request is not None
    prompt = session.request["json"]["prompt"]
    assert "- S001: emotion=happy mâu thuẫn với cue afraid" in prompt
    assert str(group[0]["stable_id"]) not in prompt


def test_name_candidates_include_speakers_and_one_off_capitalized_names() -> None:
    rows = [
        {
            "speaker": "Alisa",
            "text": "Alisa nhìn Michael bước vào cùng Alice.",
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


def test_sentence_initial_vietnamese_words_are_not_name_candidates() -> None:
    rows = [
        {
            "speaker": "NARRATOR",
            "text": (
                "Điều duy nhất cậu cảm thấy may mắn là mọi việc đã qua. "
                "May mắn thay, cậu vẫn ổn. Xen lẫn trong đó còn có tóc đỏ."
            ),
        },
        {
            "speaker": "Alisa",
            "text": "May mà chúng ta đến kịp.",
        },
    ]

    candidates = _name_candidate_contexts(rows)

    assert {candidate["surface"] for candidate in candidates} == {"Alisa"}


def test_name_at_sentence_start_is_kept_when_other_evidence_exists() -> None:
    rows = [
        {
            "speaker": "NARRATOR",
            "text": "Xen bước vào phòng. Tôi gọi Xen quay lại.",
        }
    ]

    candidates = _name_candidate_contexts(rows)

    assert len(candidates) == 1
    assert candidates[0]["surface"] == "Xen"
    assert candidates[0]["sentence_initial_occurrences"] == 1
    assert candidates[0]["mid_sentence_occurrences"] == 1


def test_isolated_fantasy_dialogue_is_a_pronunciation_candidate_but_a_scream_is_not() -> None:
    rows = [
        {"speaker": "Lucien", "kind": "dialogue", "text": "“Paso.”"},
        {"speaker": "Lucien", "kind": "dialogue", "text": "“Gaya.”"},
        {"speaker": "Lucien", "kind": "dialogue", "text": "“Aaaaah!”"},
    ]

    candidates = _name_candidate_contexts(rows)

    assert {candidate["surface"] for candidate in candidates} == {"Gaya", "Lucien", "Paso"}


def test_weak_short_names_and_corrupted_entities_are_not_candidates() -> None:
    rows = [
        {
            "speaker": "NARRATOR",
            "kind": "narration",
            "text": "Tôi gặp Wolf rồi Mag, Twal và Sol. VICT,OR đứng cạnh STHNTS.",
        }
    ]

    candidates = _name_candidate_contexts(rows)

    assert {candidate["surface"] for candidate in candidates}.isdisjoint(
        {"Wolf", "Mag", "Twal", "Sol", "VICT", "OR", "STHNTS"}
    )


def test_ascii_name_scanner_rejects_fragments_of_vietnamese_words() -> None:
    rows = [
        {
            "speaker": "NARRATOR",
            "kind": "narration",
            "text": "Giám mục kể về châu Âu thời Trung Cổ.",
        }
    ]

    candidates = _name_candidate_contexts(rows)

    assert {candidate["surface"] for candidate in candidates}.isdisjoint({"Gi", "Trung C"})


def test_batch_pronunciation_checkpoint_rejects_fragments_and_garbage() -> None:
    db = FakeDB()
    db.rows = [
        {
            "id": 1,
            "stable_id": "c1s1",
            "chapter_id": 1,
            "text": (
                "VICTOR gặp LUCIEN, NATASHA và Herodotus. "
                "STHNTS đứng cạnh Michael; VICT,OR quay đi."
            ),
            "kind_hint": "narration",
            "kind": "narration",
            "status": "pending",
            "speaker": "NARRATOR",
        }
    ]
    analyzer = OllamaBookAnalyzer(build_settings(), db, lambda _message: None)
    items = [
        {"surface": surface, "spoken_form": spoken, "confidence": 0.99}
        for surface, spoken in (
            ("VICT", "Vích"),
            ("LUCI", "Lu-xi"),
            ("NATASH", "Na-tát"),
            ("otus", "Ô-tút"),
            ("STHNTS", "Ét-thờ"),
            ("VICT,OR", "Vích-to"),
            ("Michael", "Mai-cồ"),
        )
    ]

    analyzer._checkpoint_pronunciations(db.rows, {"pronunciations": items})

    assert [(row["surface"], row["spoken_form"]) for row in db.pronunciations] == [
        ("Michael", "Mai-cồ")
    ]


def test_vietnamese_spoken_form_requires_an_explicit_phonetic_rewrite() -> None:
    assert _valid_vietnamese_spoken_form("Michael", "Mai-cồ") is True
    assert _valid_vietnamese_spoken_form("Gary", "Ga-ri") is True
    assert _valid_vietnamese_spoken_form("John", "Giôn") is True
    assert _valid_vietnamese_spoken_form("May", "Mai") is True
    assert _valid_vietnamese_spoken_form("John", "Jhon") is False
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


def test_every_bundled_cmudict_entry_has_a_safe_local_reading() -> None:
    failures: list[str] = []
    seen: set[str] = set()
    with CMUDICT_PATH.open("r", encoding="utf-8") as handle:
        for raw_line in handle:
            word, separator, raw_phones = raw_line.partition(" ")
            if not separator:
                continue
            surface = re.sub(r"\(\d+\)$", "", word.strip())
            key = surface.casefold()
            if key in seen:
                continue
            seen.add(key)
            pronunciation = raw_phones.partition("#")[0].strip()
            try:
                spoken_form = _cmu_pronunciation_to_vietnamese(surface, pronunciation)
                assert VIETNAMESE_SPOKEN_FORM_PATTERN.fullmatch(spoken_form) is not None
                assert all(
                    NON_VIETNAMESE_SYLLABLE_CODA_PATTERN.search(syllable) is None
                    for syllable in spoken_form.split("-")
                )
            except Exception as exc:  # noqa: BLE001
                failures.append(f"{surface} {pronunciation}: {exc}")

    assert len(seen) == 126_052
    assert failures == []


def test_hundreds_of_common_english_names_use_the_local_cmu_path() -> None:
    names = """
        James Robert Mary Patricia Jennifer Linda Elizabeth David William Richard Joseph Thomas
        Charles Christopher Daniel Matthew Anthony Donald Mark Paul Steven Andrew Kenneth Joshua
        Kevin Brian George Edward Ronald Timothy Jason Jeffrey Ryan Jacob Nicholas Eric Stephen
        Jonathan Larry Justin Scott Brandon Frank Raymond Gregory Samuel Patrick Alexander Jack
        Dennis Jerry Tyler Aaron Henry Douglas Peter Adam Nathan Zachary Walter Kyle Harold Carl
        Jeremy Keith Roger Gerald Ethan Arthur Terry Christian Sean Lawrence Austin Joe Noah Jesse
        Albert Bryan Billy Bruce Willie Jordan Dylan Alan Ralph Gabriel Roy Juan Wayne Eugene Logan
        Randy Louis Russell Vincent Philip Bobby Johnny Bradley Barbara Susan Jessica Sarah Karen
        Nancy Lisa Margaret Betty Sandra Ashley Kimberly Emily Donna Michelle Carol Amanda Melissa
        Deborah Stephanie Rebecca Sharon Laura Cynthia Kathleen Amy Shirley Angela Helen Anna Brenda
        Pamela Nicole Samantha Katherine Emma Ruth Christine Catherine Debra Rachel Carolyn Janet
        Virginia Maria Heather Diane Julie Joyce Victoria Kelly Christina Joan Evelyn Lauren Judith
        Megan Cheryl Andrea Hannah Jacqueline Martha Gloria Teresa Ann Sara Madison Frances Kathryn
        Janice Jean Abigail Alice Julia Judy Grace Denise Amber Marilyn Beverly Danielle Theresa
        Sophia Marie Diana Brittany Natalie Isabella Charlotte Rose Alexis Kayla Olivia Audrey
        Claire Vanessa Benjamin Michael Gary Joel John Murphy Alisa Tracy Simon Evans Lucien
    """.split()

    pronunciations = _cmu_pronunciations(names)

    assert len(names) == 207
    assert set(pronunciations) == {name.casefold() for name in names}
    for name in names:
        spoken_form = _cmu_pronunciation_to_vietnamese(
            name,
            pronunciations[name.casefold()],
        )
        assert VIETNAMESE_SPOKEN_FORM_PATTERN.fullmatch(spoken_form) is not None


def test_thousands_of_generated_fantasy_names_have_safe_fallbacks() -> None:
    prefixes = (
        "Ael", "Aer", "Astra", "Bel", "Cael", "Cor", "Dra", "Eld", "Fael", "Gal",
        "Ith", "Kael", "Lor", "Mor", "Nyth", "Or", "Quel", "Rhae", "Syl", "Thael",
        "Ul", "Vael", "Wyr", "Xy", "Yl", "Zyr",
    )
    suffixes = (
        "a", "adon", "ael", "aris", "dred", "dris", "en", "eria", "eth", "ian",
        "ion", "is", "ith", "oria", "os", "riel", "ron", "thas", "wen", "wyn",
    )
    middles = ("", "l", "m", "n", "r")

    for prefix in prefixes:
        for middle in middles:
            for suffix in suffixes:
                surface = prefix + middle + suffix
                spoken_form = _local_name_fallback(surface)
                assert VIETNAMESE_SPOKEN_FORM_PATTERN.fullmatch(spoken_form) is not None
                assert all(
                    NON_VIETNAMESE_SYLLABLE_CODA_PATTERN.search(syllable) is None
                    for syllable in spoken_form.split("-")
                )


def test_every_short_latin_letter_combination_has_a_safe_fallback() -> None:
    alphabet = "abcdefghijklmnopqrstuvwxyz"
    for length in range(1, 4):
        for letters in product(alphabet, repeat=length):
            spoken_form = _local_name_fallback("".join(letters).title())
            assert VIETNAMESE_SPOKEN_FORM_PATTERN.fullmatch(spoken_form) is not None
            assert all(
                NON_VIETNAMESE_SYLLABLE_CODA_PATTERN.search(syllable) is None
                for syllable in spoken_form.split("-")
            )


@pytest.mark.parametrize(
    ("surface", "pronunciation", "expected"),
    [
        ("Alisa", "AH0 L IY1 S AH0", "A-li-sa"),
        ("Benjamin", "B EH1 N JH AH0 M AH0 N", "Ben-gia-min"),
        ("Gary", "G EH1 R IY0", "Ga-ri"),
        ("Joel", "JH OW1 AH0 L", "Giô-en"),
        ("John", "JH AA1 N", "Giôn"),
        ("Michael", "M AY1 K AH0 L", "Mai-cồ"),
        ("Murphy", "M ER1 F IY0", "Mơ-phi"),
    ],
)
def test_cmu_arpabet_is_converted_locally(
    surface: str,
    pronunciation: str,
    expected: str,
) -> None:
    assert _cmu_pronunciation_to_vietnamese(surface, pronunciation) == expected


def test_required_cmu_names_are_checkpointed_without_qwen(monkeypatch) -> None:
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
    monkeypatch.setattr(
        analyzer,
        "ensure_available",
        lambda: pytest.fail("CMUdict names must not start Ollama"),
    )
    monkeypatch.setattr(
        analyzer,
        "_stream_json_response",
        lambda *_args, **_kwargs: pytest.fail("CMUdict names must not be sent to Qwen"),
    )

    assert analyzer.reconcile_name_pronunciations() == 2
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


def test_passthrough_name_decision_is_checkpointed_for_resume(monkeypatch) -> None:
    db = FakeDB()
    db.rows = [
        {
            "id": 1,
            "stable_id": "c1s1",
            "chapter_id": 1,
            "text": "Tôi biết May là một từ cần xét theo đúng ngữ cảnh.",
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
                    "convert": False,
                    "spoken_form": "May",
                    "confidence": 0.94,
                    "reason": "Từ trong ngữ cảnh tiếng Việt",
                }
            ]
        }

    monkeypatch.setattr(analyzer, "_stream_json_response", response)

    assert analyzer.reconcile_name_pronunciations() == 1
    assert analyzer.reconcile_name_pronunciations() == 0
    assert attempts == 1
    assert db.pronunciations[0]["spoken_form"] == "May"
    assert db.pronunciations[0]["source"] == "english_name_transliteration_case_sensitive"


def test_fantasy_name_uses_logged_local_fallback_after_targeted_retries(
    monkeypatch,
) -> None:
    db = FakeDB()
    db.rows = [
        {
            "id": 1,
            "stable_id": "c1s1",
            "chapter_id": 1,
            "text": "Gary gặp Xen trong hành lang.",
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
        assert ids == ["N001"]
        return {
            "names": [
                {
                    "id": "N001",
                    "convert": True,
                    "spoken_form": "Xen",
                    "confidence": 0.9,
                    "reason": "Cố ý không hợp lệ",
                }
            ]
        }

    monkeypatch.setattr(analyzer, "_stream_json_response", response)

    assert analyzer.reconcile_name_pronunciations() == 2

    assert requested_ids == [["N001"], ["N001"], ["N001"]]
    assert {
        row["surface"]: row["spoken_form"]
        for row in db.pronunciations
    } == {"Gary": "Ga-ri", "Xen": "Xên"}
    assert any(event[1] == "NAME_PRONUNCIATION_LOCAL_FALLBACK" for event in db.events)


def test_multiple_fantasy_names_recover_when_every_qwen_request_fails(monkeypatch) -> None:
    db = FakeDB()
    db.rows = [
        {
            "id": 1,
            "stable_id": "c1s1",
            "chapter_id": 1,
            "text": "Xen gặp Zytherion và Vaelorian.",
            "kind_hint": "dialogue",
            "status": "analyzed",
            "speaker": "Xen",
        }
    ]
    analyzer = OllamaBookAnalyzer(build_settings(), db, lambda _message: None)
    monkeypatch.setattr(analyzer, "ensure_available", lambda: True)
    monkeypatch.setattr("ebook_reader.analysis.time.sleep", lambda _seconds: None)
    attempts = 0

    def response(_request, **_kwargs):
        nonlocal attempts
        attempts += 1
        raise RuntimeError("Qwen response intentionally failed")

    monkeypatch.setattr(analyzer, "_stream_json_response", response)

    assert analyzer.reconcile_name_pronunciations() == 3
    assert attempts == 3
    assert {
        row["surface"]: row["spoken_form"]
        for row in db.pronunciations
    } == {
        "Vaelorian": "Ve-lô-rian",
        "Xen": "Xên",
        "Zytherion": "Di-thê-riôn",
    }
    fallback_event = next(
        event for event in db.events if event[1] == "NAME_PRONUNCIATION_LOCAL_FALLBACK"
    )
    assert "Qwen response intentionally failed" in fallback_event[2]


def test_uncertain_short_names_are_left_verbatim_when_reconciliation_fails(
    monkeypatch,
) -> None:
    db = FakeDB()
    db.rows = [
        {
            "id": 1,
            "stable_id": "c1s1",
            "chapter_id": 1,
            "text": "Wolf gặp Mag, Twal, Sol và Vaelorian.",
            "kind_hint": "dialogue",
            "kind": "dialogue",
            "status": "analyzed",
            "speaker": "Wolf",
        }
    ]
    analyzer = OllamaBookAnalyzer(build_settings(profile="balanced"), db, lambda _message: None)
    monkeypatch.setattr(analyzer, "ensure_available", lambda: True)
    monkeypatch.setattr("ebook_reader.analysis.time.sleep", lambda _seconds: None)
    attempts = 0

    def response(_request, **_kwargs):
        nonlocal attempts
        attempts += 1
        raise RuntimeError("pronunciation review unavailable")

    monkeypatch.setattr(analyzer, "_stream_json_response", response)

    assert analyzer.reconcile_name_pronunciations() == 1
    assert attempts == 3
    assert {
        row["surface"]: row["spoken_form"]
        for row in db.pronunciations
    } == {"Vaelorian": "Ve-lô-rian"}
    skipped = next(
        event for event in db.events if event[1] == "NAME_PRONUNCIATION_UNCERTAIN_SKIPPED"
    )
    assert set(skipped[3]["surfaces"]) == {"Wolf", "Mag", "Twal", "Sol"}


def test_high_quality_blocks_unresolved_short_name_pronunciation(monkeypatch) -> None:
    db = FakeDB()
    db.rows = [
        {
            "id": 1,
            "stable_id": "c1s1",
            "chapter_id": 1,
            "text": "Wolf gặp Mag trong đại sảnh.",
            "kind_hint": "dialogue",
            "kind": "dialogue",
            "status": "analyzed",
            "speaker": "Wolf",
        }
    ]
    analyzer = OllamaBookAnalyzer(build_settings(), db, lambda _message: None)
    monkeypatch.setattr(analyzer, "ensure_available", lambda: True)
    monkeypatch.setattr("ebook_reader.analysis.time.sleep", lambda _seconds: None)
    monkeypatch.setattr(
        analyzer,
        "_stream_json_response",
        lambda _request, **_kwargs: (_ for _ in ()).throw(
            RuntimeError("pronunciation review unavailable")
        ),
    )

    with pytest.raises(RuntimeError, match="High-quality pronunciation QA could not resolve"):
        analyzer.reconcile_name_pronunciations()

    assert any(
        event[1] == "NAME_PRONUNCIATION_UNCERTAIN_SKIPPED"
        for event in db.events
    )


def test_high_confidence_contextual_short_name_can_be_locked(monkeypatch) -> None:
    db = FakeDB()
    db.rows = [
        {
            "id": 1,
            "stable_id": "c1s1",
            "chapter_id": 1,
            "text": "Wolf bước vào phòng.",
            "kind_hint": "dialogue",
            "kind": "dialogue",
            "status": "analyzed",
            "speaker": "Wolf",
        }
    ]
    analyzer = OllamaBookAnalyzer(build_settings(), db, lambda _message: None)
    monkeypatch.setattr(analyzer, "ensure_available", lambda: True)
    monkeypatch.setattr(
        analyzer,
        "_stream_json_response",
        lambda _request, **_kwargs: {
            "names": [
                {
                    "id": "N001",
                    "convert": True,
                    "spoken_form": "Uôn",
                    "confidence": 0.96,
                    "reason": "Tên nhân vật rõ ràng trong ngữ cảnh",
                }
            ]
        },
    )

    assert analyzer.reconcile_name_pronunciations() == 1
    assert db.pronunciations[0]["surface"] == "Wolf"
    assert db.pronunciations[0]["spoken_form"] == "Uôn"


def test_local_npc_labels_are_distinct_and_scoped_to_batch() -> None:
    group = [{**row, "kind_hint": "dialogue"} for row in analysis_group()]
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


def test_local_scope_is_derived_from_stable_range_boundaries() -> None:
    group = analysis_group()

    scope = _local_scope_for_group(group)

    assert scope.startswith("r")
    assert scope == _local_scope_for_group(list(group))
    assert scope != _local_scope_for_group(group[:1])


def test_resume_uses_scope_from_original_full_book_partition(monkeypatch) -> None:
    db = FakeDB()
    db.rows = [
        {
            "id": index,
            "stable_id": f"c1s{index}",
            "chapter_id": 1,
            "text": f"Đoạn {index}.",
            "kind_hint": "dialogue",
            "status": "analyzed" if index <= 2 else "pending",
            "speaker": "NARRATOR" if index <= 2 else None,
        }
        for index in range(1, 5)
    ]
    settings = build_settings(
        overrides={"analysis": {"batch_segments": 2, "batch_chars": 10000}}
    )
    analyzer = OllamaBookAnalyzer(settings, db, lambda _message: None)
    monkeypatch.setattr(analyzer, "ensure_available", lambda: True)

    def request(group, **_kwargs):
        items = []
        for row in group:
            item = analysis_item(str(row["stable_id"]))
            item.update(
                {"kind": "dialogue", "speaker": "NPC_LOCAL:lính gác", "gender": "male"}
            )
            items.append(item)
        return {"segments": items}

    monkeypatch.setattr(analyzer, "_request", request)

    analyzer.analyze_all(lambda: False)

    speakers = {data["speaker"] for _segment_id, data, _threshold in db.updated}
    assert len(speakers) == 1
    assert _local_scope_for_group(db.rows[2:]) in next(iter(speakers))


def test_addressee_name_cannot_become_the_local_speaker_identity() -> None:
    group = [
        {
            **analysis_group()[0],
            "text": "“Anh Lucien!”",
            "kind_hint": "dialogue",
            "paragraph_index": 1,
        },
        {
            **analysis_group()[1],
            "text": "“Anh tỉnh rồi?”",
            "kind_hint": "dialogue",
            "paragraph_index": 1,
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
    assert ADDRESSEE_REPAIR_NOTE in validated[group[0]["stable_id"]]["notes"]


def test_same_paragraph_action_beats_override_wrong_dialogue_speakers() -> None:
    examples = [
        (
            "“Cha, cha và mẹ phải cẩn thận hơn trong một thời gian nữa đấy.”",
            "John có phần lo lắng.",
            "John",
        ),
        (
            "“Mẹ con và ta sẽ ổn thôi.”",
            "Joel chừa ra một khoảng trống để Alisa chữa trị vết thương cho Lucien.",
            "Joel",
        ),
        (
            "“Đến đây ăn sáng với bọn em đi!”",
            "Iven mở cửa.",
            "Iven",
        ),
    ]
    group = []
    items = []
    for paragraph_index, (dialogue, narration, _speaker) in enumerate(examples, 1):
        dialogue_id = f"d{paragraph_index}"
        narration_id = f"n{paragraph_index}"
        group.extend(
            [
                {
                    "stable_id": dialogue_id,
                    "chapter_id": 1,
                    "paragraph_index": paragraph_index,
                    "text": dialogue,
                    "kind_hint": "dialogue",
                },
                {
                    "stable_id": narration_id,
                    "chapter_id": 1,
                    "paragraph_index": paragraph_index,
                    "text": narration,
                    "kind_hint": "narration",
                },
            ]
        )
        dialogue_item = analysis_item(dialogue_id)
        dialogue_item.update({"kind": "dialogue", "speaker": "ALISA", "gender": "female"})
        items.extend((dialogue_item, analysis_item(narration_id)))

    validated = _validate(group, {"segments": items})

    for paragraph_index, (_dialogue, _narration, speaker) in enumerate(examples, 1):
        data = validated[f"d{paragraph_index}"]
        assert data["speaker"] == speaker
        assert data["gender"] == "unknown"
        assert EXPLICIT_ATTRIBUTION_NOTE in data["notes"]


def test_generic_speech_attribution_locks_bishop_descriptions() -> None:
    group = [
        {
            "stable_id": "d1",
            "chapter_id": 1,
            "paragraph_index": 1,
            "text": "“Ngươi sẽ bằng lòng sám hối chứ?”",
            "kind_hint": "dialogue",
        },
        {
            "stable_id": "n1",
            "chapter_id": 1,
            "paragraph_index": 1,
            "text": "Người đàn ông trung niên hỏi đầy ôn hòa và xót thương.",
            "kind_hint": "narration",
        },
        {
            "stable_id": "n2",
            "chapter_id": 1,
            "paragraph_index": 2,
            "text": "Giám mục cầu nguyện, sau đó lớn giọng:",
            "kind_hint": "narration",
        },
        {
            "stable_id": "d2",
            "chapter_id": 1,
            "paragraph_index": 2,
            "text": "“Hãy xuống địa ngục dưới thánh quang.”",
            "kind_hint": "dialogue",
        },
    ]
    items = [analysis_item(row["stable_id"]) for row in group]
    items[0].update(
        {"kind": "dialogue", "speaker": "NPC_LOCAL:áo choàng trắng", "gender": "male"}
    )
    items[2].update({"kind": "narration", "speaker": "NARRATOR"})
    items[3].update({"kind": "dialogue", "speaker": "NPC_LOCAL:giam muc", "gender": "male"})

    validated = _validate(group, {"segments": items}, local_scope="scene")

    assert local_speaker_display(validated["d1"]["speaker"]) == "NPC người đàn ông trung niên"
    assert validated["d1"]["gender"] == "male"
    assert validated["d1"]["age"] == "adult"
    assert local_speaker_display(validated["d2"]["speaker"]) == "NPC giám mục"
    assert validated["d2"]["gender"] == "male"
    assert validated["d2"]["age"] == "adult"


def test_speech_verb_before_quote_overrides_speaker_but_weak_context_does_not() -> None:
    group = [
        {
            "stable_id": "n1",
            "chapter_id": 1,
            "paragraph_index": 1,
            "text": "John hỏi:",
            "kind_hint": "narration",
        },
        {
            "stable_id": "d1",
            "chapter_id": 1,
            "paragraph_index": 1,
            "text": "“Cha có ổn không?”",
            "kind_hint": "dialogue",
        },
        {
            "stable_id": "d2",
            "chapter_id": 1,
            "paragraph_index": 2,
            "text": "“Tôi không biết.”",
            "kind_hint": "dialogue",
        },
        {
            "stable_id": "n2",
            "chapter_id": 1,
            "paragraph_index": 3,
            "text": "Sau đó Joel rời đi.",
            "kind_hint": "narration",
        },
    ]
    items = [analysis_item("n1"), analysis_item("d1"), analysis_item("d2"), analysis_item("n2")]
    items[1].update({"kind": "dialogue", "speaker": "ALISA", "gender": "female"})
    items[2].update({"kind": "dialogue", "speaker": "ALISA", "gender": "female"})

    validated = _validate(group, {"segments": items})

    assert validated["d1"]["speaker"] == "John"
    assert EXPLICIT_ATTRIBUTION_NOTE in validated["d1"]["notes"]
    assert validated["d2"]["speaker"] == "ALISA"
    assert EXPLICIT_ATTRIBUTION_NOTE not in validated["d2"]["notes"]


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


def test_titled_addressee_does_not_replace_an_established_local_identity() -> None:
    row = {
        **analysis_group()[0],
        "text": "“Đi thôi, anh Lucien. Chúng ta ra quảng trường.”",
        "kind_hint": "dialogue",
    }
    item = analysis_item(row["stable_id"])
    item.update(
        {
            "kind": "dialogue",
            "speaker": "NPC_LOCAL:trẻ em bụi bẩn",
            "gender": "male",
            "age": "child",
        }
    )

    validated = _validate([row], {"segments": [item]}, local_scope="stable")
    data = validated[row["stable_id"]]

    assert local_speaker_display(data["speaker"]) == "NPC trẻ em bụi bẩn"
    assert ADDRESSEE_REPAIR_NOTE not in data["notes"]


def test_generic_same_paragraph_attribution_locks_one_child_voice() -> None:
    group = [
        {
            "stable_id": "d1",
            "chapter_id": 1,
            "paragraph_index": 32,
            "text": "“Anh Lucien!”",
            "kind_hint": "dialogue",
        },
        {
            "stable_id": "n1",
            "chapter_id": 1,
            "paragraph_index": 32,
            "text": "Một cậu bé tóc nâu nhìn Hạ Phong, vô cùng mừng rỡ:",
            "kind_hint": "narration",
        },
        {
            "stable_id": "d2",
            "chapter_id": 1,
            "paragraph_index": 32,
            "text": "“Anh tỉnh rồi?”",
            "kind_hint": "dialogue",
        },
    ]
    items = [analysis_item(row["stable_id"]) for row in group]
    items[0].update(
        {"kind": "dialogue", "speaker": "NPC_LOCAL:người qua đường", "gender": "male"}
    )
    items[2].update({"kind": "dialogue", "speaker": "Lucien", "gender": "male"})

    validated = _validate(group, {"segments": items}, local_scope="stable")

    first = validated["d1"]
    second = validated["d2"]
    assert first["speaker"] == second["speaker"]
    assert local_speaker_display(first["speaker"]) == "NPC cậu bé"
    assert first["gender"] == second["gender"] == "male"
    assert first["age"] == second["age"] == "child"
    assert EXPLICIT_ATTRIBUTION_NOTE in first["notes"]
    assert EXPLICIT_ATTRIBUTION_NOTE in second["notes"]


def test_multiline_dialogue_keeps_previous_speaker_and_normalizes_child_label() -> None:
    group = [
        {
            "stable_id": "d1",
            "chapter_id": 1,
            "paragraph_index": 1,
            "text": "“Mẹ vẫn không chịu tin em.",
            "kind_hint": "dialogue",
        },
        {
            "stable_id": "d2",
            "chapter_id": 1,
            "paragraph_index": 2,
            "text": "Cha vừa sáng đã gọi anh hai về.”",
            "kind_hint": "dialogue",
        },
    ]
    items = [analysis_item(row["stable_id"]) for row in group]
    items[0].update(
        {
            "kind": "dialogue",
            "speaker": "NPC_LOCAL:trẻ em",
            "gender": "male",
            "age": "child",
        }
    )
    items[1].update(
        {"kind": "dialogue", "speaker": "NPC_LOCAL:người khác", "gender": "male"}
    )

    validated = _validate(group, {"segments": items}, local_scope="stable")

    assert validated["d1"]["speaker"] == validated["d2"]["speaker"]
    assert local_speaker_display(validated["d1"]["speaker"]) == "NPC cậu bé"


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


def test_analysis_retries_when_model_shifts_a_valid_kind_to_the_wrong_id() -> None:
    narration = {
        **analysis_group()[0],
        "kind_hint": "narration",
        "text": "Hạ Phong nhận ra đây không phải bệnh viện.",
    }
    dialogue = {
        **analysis_group()[1],
        "kind_hint": "dialogue",
        "text": "“Đây là đâu?”",
    }
    narration_item = analysis_item(narration["stable_id"])
    narration_item.update({"kind": "dialogue", "speaker": "Hạ Phong"})
    dialogue_item = analysis_item(dialogue["stable_id"])
    dialogue_item.update({"kind": "narration", "speaker": "NARRATOR"})

    validated = _validate(
        [narration, dialogue],
        {"segments": [narration_item, dialogue_item]},
    )

    assert validated == {}


@pytest.mark.parametrize(
    ("kind", "text", "emotion", "expected"),
    [
        ("narration", "Hạ Phong nhìn quanh căn phòng.", "neutral", 1),
        ("dialogue", "“Tôi hiểu rồi.”", "neutral", 1),
        ("dialogue", "“Ngươi đứng lại.”", "angry", 2),
        ("dialogue", "“Đứng lại ngay!”", "angry", 3),
    ],
)
def test_analysis_calibrates_repeated_maximum_intensity(
    kind: str,
    text: str,
    emotion: str,
    expected: int,
) -> None:
    row = {**analysis_group()[0], "kind_hint": kind, "text": text}
    item = analysis_item(row["stable_id"])
    item.update(
        {
            "kind": kind,
            "speaker": "NARRATOR" if kind == "narration" else "Lucien",
            "emotion": emotion,
            "intensity": 3,
        }
    )

    validated = _validate([row], {"segments": [item]})

    assert validated[row["stable_id"]]["intensity"] == expected


def test_semantic_delivery_rejects_v8_collapsed_happy_batch() -> None:
    texts = [
        "Cậu cảm thấy choáng váng yếu nhược, hai chân mềm nhũn, nghiêng ngả sắp ngã.",
        "Sắc mặt cậu trắng bệch, chỉ liếc nhìn đã vô cùng kinh hãi.",
        "Mọi thứ xa lạ khiến đầu óc cậu hỗn loạn.",
        "Cảm giác lo sợ cực độ nhanh chóng lên men.",
        "Một loại dự cảm xấu lặng lẽ nhen nhóm trong lòng.",
        "Trong tâm trí hỗn loạn nảy ra một ý nghĩ nực cười.",
        "“Anh tỉnh rồi?”",
        "Cậu bé nhìn thấy anh thì vô cùng kinh ngạc và mừng rỡ.",
    ]
    group = [
        {
            "id": index,
            "stable_id": f"v8s{index}",
            "chapter_id": 1,
            "text": text,
            "kind_hint": "narration",
        }
        for index, text in enumerate(texts)
    ]
    validated = {
        str(row["stable_id"]): {
            **analysis_item(str(row["stable_id"])),
            "emotion": "happy",
            "intensity": 2,
            "notes": ",",
        }
        for row in group
    }

    issues, batch_collapsed = _semantic_delivery_issues(group, validated)

    assert batch_collapsed is True
    assert set(issues) == {str(row["stable_id"]) for row in group}
    assert "emotion=happy" in issues["v8s0"]
    assert "notes" in issues["v8s6"]


def test_semantic_delivery_rejects_v9_all_neutral_zero_template() -> None:
    rows = [
        ("‘Không được ngủ… sẽ chết mất.’", "thought"),
        ("‘Tỉnh dậy, phải tỉnh dậy!’", "thought"),
        ("Cậu tuyệt vọng gắng gượng đến gần ánh sáng.", "narration"),
        ("Cậu bật dậy thở dốc sau cảnh hỏa hoạn kinh hoàng.", "narration"),
        ("Nghĩ lại cậu vẫn tim đập chân run.", "narration"),
        ("Cảnh tượng khiến cậu đực mặt ra.", "narration"),
        ("Tim thắt lại, cậu cuống quýt đứng dậy.", "narration"),
        ("Chiếc giường gỗ nằm cạnh cửa sổ.", "narration"),
    ]
    group = [
        {
            "stable_id": f"v9s{index}",
            "text": text,
            "kind_hint": kind,
        }
        for index, (text, kind) in enumerate(rows)
    ]
    validated = {
        str(row["stable_id"]): {
            **analysis_item(str(row["stable_id"])),
            "kind": row["kind_hint"],
            "emotion": "neutral",
            "intensity": 0,
            "notes": "Mô tả diễn biến của cảnh hiện tại.",
        }
        for row in group
    }

    issues, batch_collapsed = _semantic_delivery_issues(group, validated)

    assert batch_collapsed is True
    assert {"v9s0", "v9s2", "v9s3", "v9s4", "v9s5", "v9s6"} <= set(issues)
    assert 'afraid="sẽ chết mất"' in issues["v9s0"]


def test_semantic_delivery_does_not_collapse_v9_varied_neutral_one_batch() -> None:
    rows = [
        (
            "Nhưng ngay khi vừa đặt chân xuống đất, cậu liền cảm thấy choáng váng yếu nhược, "
            "hai chân mềm nhũn, nghiêng ngả sắp ngã.",
            "narration",
            "neutral",
            1,
            "normal",
        ),
        (
            "Hạ Phong vội vã vươn tay ra chống lên giường để giữ thăng bằng. Sắc mặt cậu "
            "trắng bệch, tinh thần không bình tĩnh lại được. Chỉ qua một thoáng liếc nhìn mà "
            "kinh hãi vừa rồi, cậu đã kịp quan sát hoàn chỉnh một lượt tứ phía.",
            "narration",
            "neutral",
            1,
            "normal",
        ),
        (
            "Đây là một cái lán chật hẹp, tồi tàn. Ngoài chiếc giường gỗ bên cạnh, nơi này "
            "chỉ có một chiếc bàn gỗ có thể gãy bất cứ lúc nào, hai cái ghế đẩu trông còn "
            "tương đối lành lặn cùng một cái thùng gỗ có một cái lỗ ở bên trên.",
            "narration",
            "neutral",
            1,
            "normal",
        ),
        (
            "Bên kia cánh cửa gỗ lung lay sắp rớt là một cái bếp lò nhìn không ra màu sắc "
            "ban đầu, bên trên treo một chiếc bình sành, củi bên dưới không biết đã tắt được "
            "bao lâu, chỉ còn một chút hơi nóng phả ra.",
            "narration",
            "neutral",
            1,
            "normal",
        ),
        (
            "Mọi thứ đều thật xa lạ, Hạ Phong căn bản không thể đoán được mình đang ở đâu. "
            "Mà cảm giác yếu ớt cứ không ngừng lan ra càng khiến đầu óc cậu hỗn loạn.",
            "narration",
            "neutral",
            1,
            "normal",
        ),
        ("‘Đây rốt cuộc là nơi nào?!", "thought", "neutral", 1, "normal"),
        (
            "Thân thể mình cứ như vừa khỏi một cơn bệnh nặng vậy, rất giống với cảm giác "
            "khi bị viêm phổi hồi học cấp ba.’",
            "thought",
            "neutral",
            1,
            "normal",
        ),
        (
            "Vô số suy nghĩ lướt như bay trong đầu, nhưng Hạ Phong chưa bao giờ rơi vào tình "
            "huống nào kỳ quặc như thế này. Tính cách có phần hướng nội khiến cậu không biết "
            "phải làm sao. Cảm giác lo sợ cực độ nhanh chóng lên men.",
            "narration",
            "neutral",
            1,
            "normal",
        ),
        (
            "Điều duy nhất Hạ Phong cảm thấy may mắn là không có điều gì khó chịu hay khủng "
            "khiếp xảy ra, giúp cho cậu có thể theo thói quen hít thở sâu mấy hơi để dằn nỗi "
            "lo sợ xuống. Đúng lúc ấy, những tiếng hô lớn bỗng vang lên từ xa xa bên ngoài lán:",
            "narration",
            "neutral",
            1,
            "normal",
        ),
        (
            "“Thiêu phù thủy! Giáo đường Aderon muốn thiêu phù thủy kìa!”",
            "dialogue",
            "angry",
            3,
            "loud",
        ),
        ("“Mọi người mau đi xem!”", "dialogue", "neutral", 1, "normal"),
        (
            "“Thiêu chết ả phù thủy tà ác khốn kiếp đó đi!”",
            "dialogue",
            "angry",
            3,
            "loud",
        ),
        (
            "Sợ hãi và phấn khích, hai thứ xúc cảm đối lập, hiện rõ trong giọng nói xa lạ "
            "đó. Nỗi lo sợ của Hạ Phong bị gián đoạn. Cảm thấy tò mò, cậu nghĩ thầm:",
            "narration",
            "neutral",
            1,
            "normal",
        ),
        ("‘Phù thủy? Thế giới này là cái quái gì vậy?’", "thought", "neutral", 1, "normal"),
        (
            "Là một người trưởng thành ưa thích tiểu thuyết, một loại dự cảm xấu lặng lẽ "
            "nhen nhóm trong lòng Hạ Phong. Nhưng còn chưa kịp nghĩ được gì sâu xa thì bỗng "
            "“rầm” một tiếng, cánh cửa gỗ tàn tạ đáng thương bật mở, một cậu bé chừng mười "
            "hai, mười ba tuổi vội vã chạy vào.",
            "narration",
            "neutral",
            1,
            "normal",
        ),
        ("“Anh Lucien!”", "dialogue", "happy", 2, "normal"),
        (
            "Một cậu bé tóc nâu ngắn, trên người mặc chiếc áo sơ mi vải thô dài tới đầu gối, "
            "nhìn thấy Hạ Phong đang đứng bên giường thì vô cùng kinh ngạc và mừng rỡ:",
            "narration",
            "neutral",
            1,
            "normal",
        ),
        ("“Anh tỉnh rồi?”", "dialogue", "happy", 2, "normal"),
        (
            "Nhìn bộ trang phục mang phong cách cổ xưa khác hẳn với hiện đại của cậu bé, Hạ "
            "Phong máy móc gật đầu, trong tâm trí hỗn loạn nảy ra một ý nghĩ nực cười:",
            "narration",
            "neutral",
            1,
            "normal",
        ),
        (
            "‘Lucien, phù thủy, giáo đường, thiêu chết… Lẽ nào mình thật sự đã chuyển sinh? "
            "Và còn chuyển sinh đến thời kỳ hắc ám có tục săn phù thủy ở châu Âu Trung Cổ nữa?’",
            "thought",
            "neutral",
            1,
            "normal",
        ),
    ]
    group = [
        {"stable_id": f"v9s{index + 20}", "text": text}
        for index, (text, _kind, _emotion, _intensity, _volume) in enumerate(rows)
    ]
    validated = {
        str(row["stable_id"]): {
            **analysis_item(str(row["stable_id"])),
            "kind": kind,
            "emotion": emotion,
            "intensity": intensity,
            "pace": "normal",
            "volume": volume,
            "notes": "Phân tích riêng diễn biến và cách thể hiện của segment.",
        }
        for row, (_text, kind, emotion, intensity, volume) in zip(
            group, rows, strict=True
        )
    }

    issues, batch_collapsed = _semantic_delivery_issues(group, validated)

    assert issues == {}
    assert batch_collapsed is False


def test_semantic_delivery_does_not_treat_recalled_terms_as_performed_anger() -> None:
    group = [
        {
            "stable_id": "recalled-terms",
            "text": "‘Lucien, phù thủy, giáo đường, thiêu chết… Lẽ nào mình đã chuyển sinh?’",
        }
    ]
    validated = {
        "recalled-terms": {
            **analysis_item("recalled-terms"),
            "kind": "thought",
            "emotion": "neutral",
            "intensity": 1,
            "notes": "Nhân vật đang liệt kê các khái niệm vừa nghe thấy.",
        }
    }

    assert _semantic_delivery_issues(group, validated) == ({}, False)


@pytest.mark.parametrize(
    ("emotion", "intensity"),
    [("happy", 2), ("neutral", 0)],
)
def test_semantic_delivery_rejects_direct_burn_command(
    emotion: str,
    intensity: int,
) -> None:
    group = [{"stable_id": "burn-command", "text": "“Thiêu chết hắn!”"}]
    validated = {
        "burn-command": {
            **analysis_item("burn-command"),
            "kind": "dialogue",
            "emotion": emotion,
            "intensity": intensity,
            "notes": "Người nói trực tiếp ra lệnh thiêu một người.",
        }
    }

    issues, batch_collapsed = _semantic_delivery_issues(group, validated)

    assert batch_collapsed is False
    assert 'angry="Thiêu chết"' in issues["burn-command"]


def test_semantic_delivery_keeps_neutral_physical_recovery_thought() -> None:
    group = [
        {
            "stable_id": "physical-recovery",
            "text": "‘Thân thể mình cứ như vừa khỏi một cơn bệnh nặng vậy.’",
        }
    ]
    validated = {
        "physical-recovery": {
            **analysis_item("physical-recovery"),
            "kind": "thought",
            "emotion": "neutral",
            "intensity": 1,
            "notes": "Nhân vật nhận xét trạng thái thể chất sau khi hồi phục.",
        }
    }

    assert _semantic_delivery_issues(group, validated) == ({}, False)


def test_semantic_delivery_rejects_neutral_direct_emotion_but_keeps_mixed_narration() -> None:
    group = [
        {"stable_id": "fear", "text": "‘Mình sẽ chết mất.’"},
        {
            "stable_id": "mixed-narration",
            "text": "Sợ hãi và phấn khích cùng hiện rõ trong giọng nói xa lạ.",
        },
    ]
    validated = {
        "fear": {
            **analysis_item("fear"),
            "kind": "thought",
            "emotion": "neutral",
            "notes": "Nhân vật trực tiếp nghĩ về cái chết.",
        },
        "mixed-narration": {
            **analysis_item("mixed-narration"),
            "kind": "narration",
            "emotion": "neutral",
            "notes": "Người kể mô tả hai cảm xúc đối lập.",
        },
    }

    issues, batch_collapsed = _semantic_delivery_issues(group, validated)

    assert set(issues) == {"fear"}
    assert batch_collapsed is False


def test_semantic_delivery_accepts_neutral_zero_mixed_affect_batch() -> None:
    group = [
        {
            "stable_id": f"mixed-{index}",
            "text": f"Sợ hãi và phấn khích cùng hiện rõ trong giọng nói số {index}.",
        }
        for index in range(8)
    ]
    validated = {
        str(row["stable_id"]): {
            **analysis_item(str(row["stable_id"])),
            "kind": "narration",
            "emotion": "neutral",
            "intensity": 0,
            "notes": "Người kể mô tả hai cảm xúc đối lập cùng tồn tại.",
        }
        for row in group
    }

    assert _semantic_delivery_issues(group, validated) == ({}, False)


@pytest.mark.parametrize(
    "text",
    [
        "Cô vừa sợ hãi vừa phấn khích.",
        "Trong lòng cậu, nỗi sợ hãi xen lẫn niềm vui.",
    ],
)
def test_semantic_delivery_accepts_explicit_same_experiencer_mixed_affect(
    text: str,
) -> None:
    group = [{"stable_id": "mixed-explicit", "text": text}]
    validated = {
        "mixed-explicit": {
            **analysis_item("mixed-explicit"),
            "emotion": "neutral",
            "intensity": 0,
            "notes": "Hai cảm xúc đối lập được nối rõ trong cùng một mệnh đề.",
        }
    }

    assert _semantic_delivery_issues(group, validated) == ({}, False)


def test_semantic_delivery_rejects_multiple_same_valence_cues_in_thought() -> None:
    group = [
        {
            "stable_id": "same-valence",
            "text": "‘Mình vừa sợ hãi vừa tuyệt vọng, không còn đường thoát.’",
        }
    ]
    validated = {
        "same-valence": {
            **analysis_item("same-valence"),
            "kind": "thought",
            "emotion": "neutral",
            "intensity": 1,
            "notes": "Hai cảm xúc tiêu cực được nêu trực tiếp trong suy nghĩ.",
        }
    }

    issues, batch_collapsed = _semantic_delivery_issues(group, validated)

    assert batch_collapsed is False
    assert 'afraid="sợ hãi"' in issues["same-valence"]
    assert 'sad="tuyệt vọng"' in issues["same-valence"]


def test_semantic_delivery_rejects_neutral_zero_physical_distress_in_narration() -> None:
    group = [
        {
            "stable_id": "distressed-narration",
            "text": "Cậu choáng váng yếu nhược, hai chân mềm nhũn và nghiêng ngả sắp ngã.",
        }
    ]
    validated = {
        "distressed-narration": {
            **analysis_item("distressed-narration"),
            "kind": "narration",
            "emotion": "neutral",
            "intensity": 0,
            "notes": "Người kể mô tả trạng thái thể chất suy kiệt rõ ràng.",
        }
    }

    issues, batch_collapsed = _semantic_delivery_issues(group, validated)

    assert batch_collapsed is False
    assert 'distressed="choáng váng"' in issues["distressed-narration"]


@pytest.mark.parametrize(
    "text",
    [
        "Cậu không tuyệt vọng trước tin xấu.",
        "Cô không vui trước tin ấy.",
        "Anh chẳng còn tuyệt vọng.",
        "Cậu chẳng hề kinh ngạc trước kết quả.",
        "Cậu chưa từng tuyệt vọng trong hoàn cảnh đó.",
        "Cô chưa từng kinh ngạc.",
        "Cô chưa từng vui trong căn nhà ấy.",
        "Sau lời giải thích, cậu hết tuyệt vọng.",
        "Nỗi tuyệt vọng đã hết khi mọi người trở về.",
        "Nỗi lo sợ đã hoàn toàn tan biến.",
        "‘Đừng giết anh ấy đi.’",
        "‘Chớ thiêu cô ấy thành tro đi.’",
        "‘Không được giết người vô tội đi.’",
        "‘Không được phép giết hắn đi.’",
        "‘Đừng vui mừng quá sớm.’",
        "Dòng chữ “KHÔNG THỂ TIN” hiện trên tờ giấy.",
        "Ông giải thích rằng “tuyệt vọng” là một danh từ.",
        "Anh đã từng sợ hãi, nhưng giờ hoàn toàn bình tĩnh.",
    ],
)
def test_semantic_delivery_masks_only_scoped_negated_affect_cues(text: str) -> None:
    group = [{"stable_id": "negated", "text": text}]
    validated = {
        "negated": {
            **analysis_item("negated"),
            "kind": "dialogue",
            "emotion": "neutral",
            "intensity": 0,
            "notes": "Câu phủ định hoặc ngăn cấm chính cue bề mặt.",
        }
    }

    assert _semantic_delivery_issues(group, validated) == ({}, False)


@pytest.mark.parametrize(
    "text",
    [
        "Cậu không nói gì. Trong lòng cậu vẫn tuyệt vọng.",
        "‘Đừng nói nữa; giết hắn đi!’",
        "‘Đừng giết hắn. Giết nó đi!’",
        "‘Không thể tin chuyện này lại xảy ra!’",
        "Cô chưa hết sợ hãi.",
        "Cô không khỏi sợ hãi.",
        "Cô không thể không vui mừng.",
        "Không chỉ sợ hãi mà còn tuyệt vọng.",
        "Cô không còn sợ hãi nhưng vẫn tuyệt vọng.",
        "Nhớ lại chuyện ấy, anh lại sợ hãi đến run rẩy.",
        "Ta vui vì ngươi tuyệt vọng.",
        "Cậu sợ hãi. Cô phấn khích.",
    ],
)
def test_semantic_delivery_does_not_mask_distant_or_intrinsic_cues(text: str) -> None:
    group = [{"stable_id": "unmasked", "text": text}]
    validated = {
        "unmasked": {
            **analysis_item("unmasked"),
            "kind": "thought",
            "emotion": "neutral",
            "intensity": 1,
            "notes": "Cue cảm xúc không nằm trong phạm vi phủ định cục bộ.",
        }
    }

    issues, batch_collapsed = _semantic_delivery_issues(group, validated)

    assert batch_collapsed is False
    assert "unmasked" in issues


def test_semantic_delivery_accepts_coherent_happy_and_neutral_batches() -> None:
    happy_group = [
        {
            "stable_id": f"happy{index}",
            "text": f"Mọi người vui mừng và nhẹ nhõm khi nhận tin tốt số {index}.",
        }
        for index in range(8)
    ]
    happy = {
        str(row["stable_id"]): {
            **analysis_item(str(row["stable_id"])),
            "emotion": "happy",
            "notes": "Niềm vui và sự nhẹ nhõm được nói rõ trong câu.",
        }
        for row in happy_group
    }
    neutral_group = [
        {"stable_id": f"neutral{index}", "text": f"Căn phòng có cửa sổ số {index}."}
        for index in range(8)
    ]
    neutral = {
        str(row["stable_id"]): analysis_item(str(row["stable_id"]))
        for row in neutral_group
    }

    assert _semantic_delivery_issues(happy_group, happy) == ({}, False)
    assert _semantic_delivery_issues(neutral_group, neutral) == ({}, False)


def test_semantic_delivery_does_not_treat_negated_fear_as_happy_contradiction() -> None:
    group = [
        {
            "stable_id": "relieved",
            "text": "Cô không còn sợ hãi, trong lòng vui mừng nhẹ nhõm.",
        }
    ]
    validated = {
        "relieved": {
            **analysis_item("relieved"),
            "emotion": "happy",
            "notes": "Cô đã hết sợ và cảm thấy vui mừng rõ ràng.",
        }
    }

    assert _semantic_delivery_issues(group, validated) == ({}, False)


@pytest.mark.parametrize(
    ("text", "expected_cue"),
    [
        (
            "Sợ hãi và phấn khích hiện rõ trong giọng nói, nỗi lo sợ vẫn chưa dứt.",
            "Sợ hãi",
        ),
        ("Cậu thấy may mắn nhưng vẫn phải dằn nỗi lo sợ xuống.", "lo sợ"),
    ],
)
def test_semantic_delivery_rejects_mixed_negative_affect_as_happy(
    text: str,
    expected_cue: str,
) -> None:
    group = [{"stable_id": "mixed", "text": text}]
    validated = {
        "mixed": {
            **analysis_item("mixed"),
            "emotion": "happy",
            "notes": "Câu chứa nhiều cảm xúc đan xen.",
        }
    }

    issues, _collapsed = _semantic_delivery_issues(group, validated)

    assert "mixed" in issues
    assert expected_cue in issues["mixed"]


def test_semantic_delivery_keeps_explicit_excitement_as_excited() -> None:
    group = [{"stable_id": "excited", "text": "Cậu vô cùng phấn khích khi cánh cửa mở ra."}]
    validated = {
        "excited": {
            **analysis_item("excited"),
            "emotion": "excited",
            "notes": "Sự phấn khích được nêu trực tiếp.",
        }
    }

    assert _semantic_delivery_issues(group, validated) == ({}, False)


def test_semantic_delivery_rejects_happy_crowd_condemnation_individually() -> None:
    texts = ["“Độc ác quá!”", "“Ả ta thật đáng chết!”", "“Thiêu ả thành tro đi!”"]
    group = [
        {"stable_id": f"crowd{index}", "text": text}
        for index, text in enumerate(texts)
    ]
    validated = {
        str(row["stable_id"]): {
            **analysis_item(str(row["stable_id"])),
            "emotion": "happy",
            "notes": "Đám đông đang đồng thanh kết tội người phụ nữ.",
        }
        for row in group
    }

    issues, batch_collapsed = _semantic_delivery_issues(group, validated)

    assert set(issues) == {"crowd0", "crowd1", "crowd2"}
    assert batch_collapsed is False


def test_semantic_delivery_feedback_retries_before_checkpoint(monkeypatch) -> None:
    db = FakeDB()
    db.rows = [
        {
            "id": index,
            "stable_id": f"semantic{index}",
            "chapter_id": 1,
            "text": text,
            "kind_hint": "narration",
            "status": "pending",
            "speaker": None,
        }
        for index, text in enumerate(
            (
                "Sắc mặt cậu trắng bệch vì kinh hãi.",
                "Cảm giác lo sợ cực độ dâng lên.",
                "Một dự cảm xấu khiến cô bất an.",
                "Tâm trí anh hỗn loạn vì hoảng sợ.",
            ),
            1,
        )
    ]
    settings = build_settings(
        overrides={"analysis": {"batch_segments": 4, "batch_chars": 10000, "max_retries": 2}}
    )
    analyzer = OllamaBookAnalyzer(settings, db, lambda _message: None)
    monkeypatch.setattr(analyzer, "ensure_available", lambda: True)
    monkeypatch.setattr("ebook_reader.analysis.time.sleep", lambda _seconds: None)
    feedback_seen: list[dict[str, str] | None] = []

    def request(group, **kwargs):
        feedback_seen.append(kwargs.get("validation_feedback"))
        items = []
        for row in group:
            item = analysis_item(str(row["stable_id"]))
            if len(feedback_seen) == 1:
                item.update({"emotion": "happy", "intensity": 2, "notes": ","})
            else:
                item.update(
                    {
                        "emotion": "afraid",
                        "intensity": 2,
                        "pace": "fast",
                        "notes": "Nỗi sợ được nêu trực tiếp trong câu.",
                    }
                )
            items.append(item)
        return {"segments": items}

    monkeypatch.setattr(analyzer, "_request", request)

    analyzer.analyze_all(lambda: False)

    assert feedback_seen[0] is None
    assert set(feedback_seen[1] or {}) == {str(row["stable_id"]) for row in db.rows}
    assert len(db.updated) == 4
    assert {data["emotion"] for _segment_id, data, _threshold in db.updated} == {"afraid"}
    assert any(event[1] == "ANALYSIS_SEMANTIC_REJECTED" for event in db.events)


def test_persistent_semantic_delivery_failure_splits_until_singletons(monkeypatch) -> None:
    db = FakeDB()
    db.rows = [
        {
            "id": index,
            "stable_id": f"split-semantic{index}",
            "chapter_id": 1,
            "text": f"Cảm giác lo sợ cực độ dâng lên lần {index}.",
            "kind_hint": "narration",
            "status": "pending",
            "speaker": None,
        }
        for index in range(1, 5)
    ]
    settings = build_settings(
        overrides={"analysis": {"batch_segments": 4, "batch_chars": 10000, "max_retries": 2}}
    )
    logs: list[str] = []
    analyzer = OllamaBookAnalyzer(settings, db, logs.append)
    monkeypatch.setattr(analyzer, "ensure_available", lambda: True)
    monkeypatch.setattr("ebook_reader.analysis.time.sleep", lambda _seconds: None)
    request_sizes: list[int] = []

    def request(group, **_kwargs):
        request_sizes.append(len(group))
        items = []
        for row in group:
            item = analysis_item(str(row["stable_id"]))
            if len(group) > 1:
                item.update({"emotion": "happy", "notes": ","})
            else:
                item.update(
                    {
                        "emotion": "afraid",
                        "pace": "fast",
                        "notes": "Nỗi sợ được nêu trực tiếp trong câu.",
                    }
                )
            items.append(item)
        return {"segments": items}

    monkeypatch.setattr(analyzer, "_request", request)

    analyzer.analyze_all(lambda: False)

    assert request_sizes == [4, 4, 2, 2, 1, 1, 2, 2, 1, 1]
    assert len(db.updated) == 4
    assert any("vẫn không qua semantic" in message for message in logs)


def test_persistent_neutral_zero_template_never_checkpoints_after_split(monkeypatch) -> None:
    db = FakeDB()
    db.rows = [
        {
            "id": index,
            "stable_id": f"neutral-zero-{index}",
            "chapter_id": 1,
            "text": f"Cậu vẫn sợ hãi và tuyệt vọng ở lần {index}.",
            "kind_hint": "narration",
            "status": "pending",
            "speaker": None,
        }
        for index in range(1, 9)
    ]
    settings = build_settings(
        overrides={"analysis": {"batch_segments": 8, "batch_chars": 10000, "max_retries": 2}}
    )
    analyzer = OllamaBookAnalyzer(settings, db, lambda _message: None)
    monkeypatch.setattr(analyzer, "ensure_available", lambda: True)
    monkeypatch.setattr("ebook_reader.analysis.time.sleep", lambda _seconds: None)
    request_sizes: list[int] = []

    def request(group, **_kwargs):
        request_sizes.append(len(group))
        return {
            "segments": [
                {
                    **analysis_item(str(row["stable_id"])),
                    "emotion": "neutral",
                    "intensity": 0,
                    "pace": "normal",
                    "volume": "normal",
                    "notes": "Mô tả diễn biến chung của cảnh hiện tại.",
                }
                for row in group
            ]
        }

    monkeypatch.setattr(analyzer, "_request", request)

    with pytest.raises(RuntimeError, match="Phân tích bắt buộc thất bại"):
        analyzer.analyze_all(lambda: False)

    assert request_sizes == [8, 8, 4, 4, 2, 2, 1, 1]
    assert db.updated == []
    assert any(event[1] == "REQUIRED_ANALYSIS_BATCH_FAILED" for event in db.events)


def test_every_thought_uses_narrator_without_character_identity() -> None:
    row = analysis_group()[0]
    narrator_thought = analysis_item(row["stable_id"])
    narrator_thought.update({"kind": "thought", "speaker": "NARRATOR"})

    fallback = _validate([row], {"segments": [narrator_thought]})
    assert fallback[row["stable_id"]]["speaker"] == "NARRATOR"
    assert fallback[row["stable_id"]]["gender"] == "unknown"
    assert fallback[row["stable_id"]]["age"] == "unknown"

    unknown_thought = {**narrator_thought, "speaker": "UNKNOWN"}
    fallback = _validate([row], {"segments": [unknown_thought]})
    assert fallback[row["stable_id"]]["speaker"] == "NARRATOR"

    character_thought = {**narrator_thought, "speaker": "Alisa", "gender": "female"}
    validated = _validate([row], {"segments": [character_thought]})

    assert validated[row["stable_id"]]["kind"] == "thought"
    assert validated[row["stable_id"]]["speaker"] == "NARRATOR"
    assert validated[row["stable_id"]]["gender"] == "unknown"


def test_thought_uses_narrator_without_retry_or_warning(monkeypatch) -> None:
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

    assert attempts == 1
    assert db.updated[0][1]["kind"] == "thought"
    assert db.updated[0][1]["speaker"] == "NARRATOR"
    assert db.events == []
    assert not any("không xác định" in message for message in logs)


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


def test_streaming_analysis_wall_timeout_raises_specific_error_and_closes_response(
    monkeypatch,
) -> None:
    group = analysis_group()
    session = FakeSession({"segments": [analysis_item("S001"), analysis_item("S002")]})
    analyzer = OllamaBookAnalyzer(build_settings(), FakeDB(), lambda _message: None)
    analyzer.session = session
    monotonic_values = iter((0.0, 421.0))
    monkeypatch.setattr("ebook_reader.analysis.time.monotonic", lambda: next(monotonic_values))

    with pytest.raises(AnalysisWallTimeoutError, match="420s wall-time limit"):
        analyzer._request(group)

    assert session.response.closed is True


def test_streaming_analysis_output_budget_raises_specific_error_and_closes_response() -> None:
    group = analysis_group()
    session = FakeSession({})

    class OutputBudgetResponse(FakeResponse):
        def iter_lines(self, decode_unicode=False):
            line = json.dumps(
                {
                    "response": '{"segments":[',
                    "done": True,
                    "done_reason": "length",
                    "eval_count": 1024,
                }
            )
            yield line if decode_unicode else line.encode("utf-8")

    session.response = OutputBudgetResponse({})
    analyzer = OllamaBookAnalyzer(build_settings(), FakeDB(), lambda _message: None)
    analyzer.session = session

    with pytest.raises(AnalysisOutputBudgetError, match="output-token budget"):
        analyzer._request(group)

    assert session.response.closed is True


def test_wall_timeout_splits_twenty_segment_batch_immediately_and_preserves_scope(
    monkeypatch,
) -> None:
    db = FakeDB()
    db.rows = [
        {
            "id": index,
            "stable_id": f"c1s{index}",
            "chapter_id": 1,
            "text": f"Đoạn {index}.",
            "kind_hint": "dialogue",
            "status": "pending",
            "speaker": None,
        }
        for index in range(1, 21)
    ]
    settings = build_settings(
        overrides={"analysis": {"batch_segments": 20, "batch_chars": 10000}}
    )
    logs: list[str] = []
    analyzer = OllamaBookAnalyzer(settings, db, logs.append)
    monkeypatch.setattr(analyzer, "ensure_available", lambda: True)
    request_sizes: list[int] = []

    def request(group, **_kwargs):
        request_sizes.append(len(group))
        if len(group) == 20:
            raise AnalysisWallTimeoutError("wall-time test timeout")
        items = []
        for row in group:
            item = analysis_item(str(row["stable_id"]))
            item.update(
                {"kind": "dialogue", "speaker": "NPC_LOCAL:lính gác", "gender": "male"}
            )
            items.append(item)
        return {"segments": items}

    monkeypatch.setattr(analyzer, "_request", request)

    analyzer.analyze_all(lambda: False)

    assert request_sizes == [20, 10, 10]
    speakers = {data["speaker"] for _segment_id, data, _threshold in db.updated}
    assert len(speakers) == 1
    assert _local_scope_for_group(db.rows) in next(iter(speakers))
    assert any("vượt giới hạn thời gian 1; tự chia thành 10 + 10 segment" in log for log in logs)


def test_wall_timeout_single_segment_uses_bounded_retries_without_split(monkeypatch) -> None:
    db = FakeDB()
    settings = build_settings(overrides={"analysis": {"max_retries": 3}})
    analyzer = OllamaBookAnalyzer(settings, db, lambda _message: None)
    monkeypatch.setattr(analyzer, "ensure_available", lambda: True)
    monkeypatch.setattr("ebook_reader.analysis.time.sleep", lambda _seconds: None)
    request_sizes: list[int] = []

    def request(group, **_kwargs):
        request_sizes.append(len(group))
        raise AnalysisWallTimeoutError("single-segment wall-time test timeout")

    monkeypatch.setattr(analyzer, "_request", request)

    with pytest.raises(RuntimeError, match="Phân tích bắt buộc thất bại"):
        analyzer.analyze_all(lambda: False)

    assert request_sizes == [1, 1, 1]
    assert any(event[1] == "REQUIRED_ANALYSIS_BATCH_FAILED" for event in db.events)


def test_output_budget_exhaustion_splits_batch_without_retrying_same_size(monkeypatch) -> None:
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
    analyzer = OllamaBookAnalyzer(settings, db, lambda _message: None)
    monkeypatch.setattr(analyzer, "ensure_available", lambda: True)
    request_sizes: list[int] = []

    def request(group, **_kwargs):
        request_sizes.append(len(group))
        if len(group) == 4:
            raise AnalysisOutputBudgetError("output budget test exhaustion")
        return {
            "segments": [analysis_item(str(row["stable_id"])) for row in group],
        }

    monkeypatch.setattr(analyzer, "_request", request)

    analyzer.analyze_all(lambda: False)

    assert request_sizes == [4, 2, 2]
    assert len(db.updated) == 4


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


def test_split_batches_keep_one_stable_local_identity_scope(monkeypatch) -> None:
    db = FakeDB()
    db.rows = [
        {
            "id": index,
            "stable_id": f"c1s{index}",
            "chapter_id": 1,
            "text": f"Đoạn {index}.",
            "kind_hint": "dialogue",
            "status": "pending",
            "speaker": None,
        }
        for index in range(1, 5)
    ]
    settings = build_settings(
        overrides={"analysis": {"batch_segments": 4, "batch_chars": 10000}}
    )
    analyzer = OllamaBookAnalyzer(settings, db, lambda _message: None)
    monkeypatch.setattr(analyzer, "ensure_available", lambda: True)

    def request(group, **_kwargs):
        if len(group) == 4:
            raise OllamaStreamIncompleteError("incomplete test stream")
        items = []
        for row in group:
            item = analysis_item(str(row["stable_id"]))
            item.update(
                {"kind": "dialogue", "speaker": "NPC_LOCAL:lính gác", "gender": "male"}
            )
            items.append(item)
        return {"segments": items}

    monkeypatch.setattr(analyzer, "_request", request)

    analyzer.analyze_all(lambda: False)

    speakers = {data["speaker"] for _segment_id, data, _threshold in db.updated}
    assert len(speakers) == 1
    assert _local_scope_for_group(db.rows) in next(iter(speakers))


def test_incomplete_id_response_splits_batch_after_retries(monkeypatch) -> None:
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
    monkeypatch.setattr("ebook_reader.analysis.time.sleep", lambda _seconds: None)
    request_sizes: list[int] = []

    def request(group, **_kwargs):
        request_sizes.append(len(group))
        rows = group[:-1] if len(group) == 4 else group
        return {
            "segments": [analysis_item(str(row["stable_id"])) for row in rows],
        }

    monkeypatch.setattr(analyzer, "_request", request)

    analyzer.analyze_all(lambda: False)

    assert request_sizes == [4, 4, 4, 2, 2]
    assert len(db.updated) == 4
    assert not any(event[1] == "REQUIRED_ANALYSIS_BATCH_FAILED" for event in db.events)
    assert any(
        "vẫn trả thiếu ID sau 3 lần; tự chia thành 2 + 2 segment" in message
        for message in logs
    )


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


def test_analyzer_pulls_an_allowed_missing_model_without_a_console(monkeypatch) -> None:
    settings = build_settings(
        "high_quality",
        {"safety": {"allow_network_downloads_during_job": True}},
    )
    analyzer = OllamaBookAnalyzer(settings, FakeDB(), lambda _message: None)
    monkeypatch.setattr(analyzer, "_available", lambda: True)
    monkeypatch.setattr("ebook_reader.analysis.shutil.which", lambda _name: "ollama.exe")

    class EmptyTagsResponse:
        @staticmethod
        def json():
            return {"models": []}

    class EmptyTagsSession:
        @staticmethod
        def get(_url, timeout):
            assert timeout == 10
            return EmptyTagsResponse()

    analyzer.session = EmptyTagsSession()
    calls: list[tuple[list[str], bool]] = []
    monkeypatch.setattr(
        "ebook_reader.analysis.run_hidden",
        lambda command, *, check: calls.append((list(command), check)),
    )

    assert analyzer.ensure_available() is True
    assert calls == [(["ollama.exe", "pull", "qwen3:8b"], True)]
