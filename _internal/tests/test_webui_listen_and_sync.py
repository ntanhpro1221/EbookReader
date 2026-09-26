"""Giao diện mới (ebook_reader/webui): dữ liệu chỉ đọc, trạng thái nghe, đồng bộ sang điện thoại.

Mọi phép thử dựng một project SQLite tối thiểu trong thư mục tạm - chỉ các bảng và cột mà webui đọc - nên không
phụ thuộc dữ liệu sản xuất và chạy được giữa lúc ranh giới đang sống.
"""
from __future__ import annotations

import http.client
import json
import sqlite3
import time
from pathlib import Path

import pytest

from ebook_reader.webui import humanize, listen_view, store
from ebook_reader.webui.library import Library, Preferences, book_id
from ebook_reader.webui.listening import Listening, merge_states
from ebook_reader.webui.server import App, Server
from ebook_reader.webui.actions import FakeRunner
from ebook_reader.webui.sync import Devices, SyncApp, SyncServer, manifest


def make_project(root: Path, title: str = "Sách thử · Tập 1") -> Path:
    """Một cuốn 2 chương: chương 1 đã xong (có MP3), chương 2 đang thu."""
    project = root / "sach_thu"
    (project / "output" / "chapters").mkdir(parents=True)
    (project / "work").mkdir()
    (project / "book_settings.json").write_text(
        json.dumps({"quality_profile": "high_quality", "voices": {"narrator_voice": "Đức Trí"}}), encoding="utf-8"
    )
    mp3 = project / "output" / "chapters" / "00001_645.mp3"
    mp3.write_bytes(b"ID3" + bytes(range(256)) * 40)
    sample = project / "work" / "s3.wav"
    sample.write_bytes(b"RIFF" + b"\0" * 400)
    db = sqlite3.connect(project / "project.sqlite3")
    db.executescript(
        """
        CREATE TABLE book (id INTEGER PRIMARY KEY, title TEXT, status TEXT, stage TEXT, created_at REAL,
                           updated_at REAL, last_error TEXT, settings_json TEXT);
        CREATE TABLE chapters (id INTEGER PRIMARY KEY, chapter_index INTEGER, title TEXT, input_path TEXT,
                               status TEXT, total_segments INTEGER, output_mp3 TEXT, started_at REAL,
                               completed_at REAL, last_error TEXT);
        CREATE TABLE segments (id INTEGER PRIMARY KEY, chapter_id INTEGER, seq INTEGER, paragraph_index INTEGER,
                               break_ms INTEGER, text TEXT, kind TEXT, speaker TEXT, voice_profile_id INTEGER,
                               status TEXT, wav_path TEXT, wav_sha256 TEXT, wav_duration REAL, updated_at REAL);
        CREATE TABLE characters (id INTEGER PRIMARY KEY, canonical_name TEXT, display_name TEXT, gender TEXT,
                                 age TEXT, importance TEXT, mention_count INTEGER, locked_voice_key TEXT);
        CREATE TABLE voice_profiles (id INTEGER PRIMARY KEY, voice_key TEXT, preset_name TEXT,
                                     pitch_semitones REAL, formant_ratio REAL);
        CREATE TABLE runtime_events (id INTEGER PRIMARY KEY, timestamp REAL, level TEXT, code TEXT, message TEXT);
        """
    )
    now = time.time()
    db.execute("INSERT INTO book VALUES (1, ?, 'synthesizing', 'chapter_synthesis', ?, ?, '', '{}')", (title, now - 90, now))
    db.execute("INSERT INTO chapters VALUES (1, 1, '645', 'a.txt', 'completed', 3, ?, ?, ?, '')", (str(mp3), now - 80, now - 60))
    db.execute("INSERT INTO chapters VALUES (2, 2, '646', 'b.txt', 'synthesizing', 2, '', ?, NULL, '')", (now - 50,))
    db.execute("INSERT INTO voice_profiles VALUES (1, 'narrator', 'Đức Trí', 0, 1.0)")
    db.execute("INSERT INTO voice_profiles VALUES (2, 'preset_thanh_binh_f087_p+00', 'Thanh Bình', 0, 0.87)")
    db.execute("INSERT INTO characters VALUES (1, 'LUCIEN', 'LUCIEN', 'male', 'young', 'main', 30, '')")
    rows = [
        (1, 1, 1, 0, 400, "Chương 646 - Trở về (1)", "narration", "NARRATOR", 1, "verified", "", "x", 2.0, now),
        (2, 1, 2, 1, 300, "Trời đã sáng.", "narration", "NARRATOR", 1, "verified", "", "x", 3.0, now),
        (3, 1, 3, 1, 0, "“Đi thôi.”", "dialogue", "LUCIEN", 2, "verified", str(sample), "x", 4.0, now),
        (4, 2, 1, 0, 400, "Chương 647 - Trở về (2)", "narration", "NARRATOR", 1, "verified", "", "x", 2.0, now),
        (5, 2, 2, 1, 0, "Chưa thu.", "narration", "NARRATOR", 1, "analyzed", "", "", None, now),
    ]
    db.executemany("INSERT INTO segments VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)
    db.commit()
    db.close()
    return project


@pytest.fixture()
def library(tmp_path: Path) -> tuple[Library, Path, Listening]:
    root = tmp_path / "thu_vien"
    root.mkdir()
    project = make_project(root)
    preferences = Preferences(tmp_path / "prefs" / "preferences.json")
    preferences.update({"libraryRoot": str(root)})
    return Library(preferences), project, Listening(tmp_path / "prefs" / "listening.json")


# ---- đọc chỉ-đọc ------------------------------------------------------------------------------------------


def test_chapter_names_come_from_the_heading_not_the_file(library) -> None:
    """File `645.txt` mở đầu bằng "Chương 646 - Trở về (1)" (nguồn cuốn 2 lệch một): người đọc thấy tên trong truyện."""
    _lib, project, _listening = library
    chapters = store.chapters(project)
    assert (chapters[0]["displayTitle"], chapters[0]["subtitle"]) == ("Chương 646", "Trở về (1)")
    assert chapters[0]["playable"] and not chapters[1]["playable"]
    assert humanize.chapter_names("7", "Lucien bước vào") == ("Chương 7", "")


def test_the_read_along_script_marks_the_heading_and_times_every_sentence(library) -> None:
    _lib, project, _listening = library
    script = store.chapter_script(project, 1)
    assert script["timed"]
    assert [segment["kind"] for segment in script["segments"]] == ["heading", "narration", "dialogue"]
    starts = [segment["start"] for segment in script["segments"]]
    # 2 s + 0,4 s nghỉ, rồi 3 s + 0,3 s nghỉ (MP3 giả không đọc được độ dài -> không co giãn).
    assert starts == [0.0, 2.4, 5.7]
    assert script["segments"][2]["speaker"] == "Lucien"


def test_the_store_never_writes_the_project(library) -> None:
    _lib, project, _listening = library
    before = (project / "project.sqlite3").stat().st_mtime_ns
    store.summarize(project)
    store.chapters(project)
    store.cast(project)
    store.activity(project)
    assert (project / "project.sqlite3").stat().st_mtime_ns == before
    assert not (project / "project.sqlite3-wal").exists()


# ---- trạng thái nghe ---------------------------------------------------------------------------------------


def test_listening_to_the_last_seconds_marks_the_chapter_heard(tmp_path: Path) -> None:
    listening = Listening(tmp_path / "listening.json")
    listening.progress("b", 1, 100.0, 400.0)
    assert listening.get("b")["chapters"]["1"]["done"] is False
    listening.progress("b", 1, 385.0, 400.0)
    assert listening.get("b")["chapters"]["1"]["done"] is True


def test_merging_two_devices_keeps_the_newest_of_each_part() -> None:
    desktop = {"last": {"chapterId": 1, "seconds": 50, "at": 100}, "chapters": {"1": {"heard": 50, "done": False, "at": 100}},
               "bookmarks": [{"id": "a", "chapterId": 1, "seconds": 10, "note": "", "at": 90}],
               "rate": 1.0, "rateAt": 10}
    phone = {"last": {"chapterId": 2, "seconds": 5, "at": 200}, "chapters": {"2": {"heard": 5, "done": False, "at": 200}},
             "bookmarks": [{"id": "b", "chapterId": 2, "seconds": 3, "note": "hay", "at": 150}],
             "deleted": {"a": 180}, "rate": 1.5, "rateAt": 20}
    merged = merge_states(desktop, phone)
    assert merged["last"]["chapterId"] == 2
    assert set(merged["chapters"]) == {"1", "2"}
    assert [mark["id"] for mark in merged["bookmarks"]] == ["b"], "dấu trang xoá trên điện thoại phải biến mất ở máy tính"
    assert merged["rate"] == 1.5


# ---- đồng bộ điện thoại ---------------------------------------------------------------------------------------


def test_a_pairing_code_works_once_and_expires(tmp_path: Path) -> None:
    devices = Devices(tmp_path / "devices.json")
    code = devices.pairing_code()["code"]
    assert devices.pair("000000" if code != "000000" else "111111", "Điện thoại") is None
    token = devices.pair(code, "Điện thoại của Anh")
    assert token and devices.check(token)
    assert devices.pair(code, "máy khác") is None, "mã ghép nối chỉ dùng một lần"
    devices.revoke(devices.list()[0]["id"])
    assert not devices.check(token)


def _request(port: int, method: str, path: str, token: str = "", body: dict | None = None, headers: dict | None = None):
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    all_headers = {"Authorization": f"Bearer {token}"} if token else {}
    all_headers.update(headers or {})
    payload = json.dumps(body).encode() if body is not None else None
    if payload is not None:
        all_headers["Content-Type"] = "application/json"
    connection.request(method, path, body=payload, headers=all_headers)
    response = connection.getresponse()
    data = response.read()
    connection.close()
    return response.status, data, dict(response.getheaders())


def test_a_paired_phone_downloads_a_book_and_syncs_its_place(library, tmp_path: Path) -> None:
    lib, project, listening = library
    devices = Devices(tmp_path / "devices.json")
    server = SyncServer(SyncApp(lib, listening, devices, "Máy thử"), host="127.0.0.1", port=0).start()
    try:
        status, _data, _ = _request(server.port, "GET", "/sync/v1/library")
        assert status == 401, "chưa ghép nối thì không thấy gì"
        code = devices.pairing_code()["code"]
        status, data, _ = _request(server.port, "POST", "/sync/v1/pair", body={"code": code, "device": "Pixel"})
        token = json.loads(data)["token"]
        status, data, _ = _request(server.port, "GET", "/sync/v1/library", token)
        books = json.loads(data)["books"]
        assert status == 200 and len(books) == 1 and books[0]["chaptersAvailable"] == 1
        identifier = books[0]["id"]
        status, data, _ = _request(server.port, "GET", f"/sync/v1/books/{identifier}/manifest", token)
        book = json.loads(data)
        chapter = book["chapters"][0]
        assert chapter["file"] == "chapters/00001_645.mp3" and book["samples"] == ["samples/3.wav"]
        status, data, headers = _request(server.port, "GET", f"/sync/v1/books/{identifier}/files/{chapter['file']}", token,
                                         headers={"Range": "bytes=10-19"})
        assert status == 206 and len(data) == 10 and headers["Content-Range"].startswith("bytes 10-19/")
        status, _data, _ = _request(server.port, "GET", f"/sync/v1/books/{identifier}/files/../book_settings.json", token)
        assert status == 404, "chỉ phát file có trong gói"
        status, data, _ = _request(server.port, "GET", f"/sync/v1/books/{identifier}/files/scripts/1.json", token)
        assert json.loads(data)["segments"][0]["kind"] == "heading"
        phone_state = {"last": {"chapterId": 1, "seconds": 42.0, "at": time.time()}, "chapters": {}, "bookmarks": []}
        status, data, _ = _request(server.port, "POST", f"/sync/v1/books/{identifier}/state", token, body=phone_state)
        assert status == 200 and listening.get(identifier)["last"]["seconds"] == 42.0
    finally:
        server.stop()


def test_the_ui_server_rejects_other_hosts_and_missing_tokens(library, tmp_path: Path) -> None:
    lib, _project, listening = library
    app = App(preferences=lib.preferences, runner=FakeRunner(), token="secret-token", listening=listening)
    server = Server(app, port=0).start()
    try:
        status, _data, _ = _request(server.port, "GET", "/api/library")
        assert status == 401
        status, data, _ = _request(server.port, "GET", "/api/library", headers={"X-Ebook-Token": "secret-token"})
        assert status == 200 and len(json.loads(data)["books"]) == 1
        status, _data, _ = _request(server.port, "GET", "/api/library?t=secret-token", headers={"Host": "evil.example:80"})
        assert status == 403, "Host lạ (DNS rebinding) phải bị từ chối"
    finally:
        server.stop()


def test_the_listen_view_lists_only_chapters_you_can_hear(library) -> None:
    _lib, project, listening = library
    summary = store.summarize(project)
    view = listen_view.book(project, book_id(project), summary, listening.get("x"))
    assert view["chaptersAvailable"] == 1 and view["chaptersTotal"] == 2
    assert view["duration"] == pytest.approx(9.7)
    assert manifest(project, book_id(project), listening)["chapters"][1]["file"] is None
