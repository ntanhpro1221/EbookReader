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
    NON_VIETNAMESE_SYLLABLE_CODA_PATTERN,
    VIETNAMESE_SPOKEN_FORM_PATTERN,
    AnalysisRequestStopped,
    OllamaBookAnalyzer,
    OllamaStreamIncompleteError,
    _cmu_pronunciation_to_vietnamese,
    _cmu_pronunciations,
    _local_name_fallback,
    _name_candidate_contexts,
    _repair_vietnamese_syllable_boundaries,
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
