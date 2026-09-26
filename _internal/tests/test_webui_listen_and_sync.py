"""Giao diện mới (ebook_reader/webui): dữ liệu chỉ đọc, trạng thái nghe, đồng bộ sang điện thoại.

Mọi phép thử dựng một project SQLite tối thiểu trong thư mục tạm - chỉ các bảng và cột mà webui đọc - nên không
phụ thuộc dữ liệu sản xuất và chạy được giữa lúc ranh giới đang sống.
"""
from __future__ import annotations

import http.client
import json
import socket
import sqlite3
import time
from pathlib import Path

import pytest

from ebook_reader.webui import humanize, listen_view, store
from ebook_reader.webui.library import Library, Preferences, book_id
from ebook_reader.webui.listening import Listening, book_progress, merge_states
from ebook_reader.webui.server import App, Server
from ebook_reader.webui.actions import FakeRunner
from ebook_reader.webui.sync import PAIRING_ATTEMPTS, Devices, SyncApp, SyncServer, manifest


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


def test_hearing_everything_produced_so_far_is_caught_up_not_finished() -> None:
    """Sách đang làm dở nghe hết phần đã có: chưa "nghe xong" (không vào bộ lọc Đã xong, không rơi khỏi Đang nghe
    dở), mà "đã theo kịp"."""
    chapters = [{"id": 1, "duration": 600.0}, {"id": 2, "duration": 600.0}]
    state = {"chapters": {"1": {"heard": 600, "done": True}, "2": {"heard": 600, "done": True}}}
    partial = book_progress(state, chapters, complete=False)
    assert not partial["finished"] and partial["caughtUp"]
    whole = book_progress(state, chapters, complete=True)
    assert whole["finished"] and not whole["caughtUp"]
    marked = book_progress({**state, "finished": True}, chapters, complete=False)
    assert marked["finished"] and not marked["caughtUp"], "người dùng tự đánh dấu nghe xong thì tôn trọng"


def test_two_bookmarks_at_the_same_spot_are_one(tmp_path: Path) -> None:
    listening = Listening(tmp_path / "listening.json")
    first = listening.add_bookmark("b", 3, 64.0)
    again = listening.add_bookmark("b", 3, 67.5, "đoạn hay")
    assert again["id"] == first["id"] and again["existing"]
    assert [mark["note"] for mark in listening.get("b")["bookmarks"]] == ["đoạn hay"]
    other = listening.add_bookmark("b", 3, 80.0)
    assert other["id"] != first["id"] and not other.get("existing")
    listening.delete_bookmark("b", first["id"])
    listening.restore_bookmark("b", first)
    state = listening.get("b")
    assert first["id"] in [mark["id"] for mark in state["bookmarks"]] and first["id"] not in state["deleted"]


def test_last_night_is_the_newest_undismissed_night(tmp_path: Path) -> None:
    listening = Listening(tmp_path / "listening.json")
    now = time.time()
    event = {"type": "timer", "at": now - 3600, "minutes": 30, "position": {"chapterId": 1, "seconds": 10}}
    listening.save_night("a", {"id": "n1", "startedAt": now - 3600, "events": [event]})
    listening.save_night("b", {"id": "n2", "startedAt": now - 1800, "events": [event]})
    assert listening.latest_night(now)["bookId"] == "b"
    listening.dismiss_night("b", "n2")
    assert listening.latest_night(now)["bookId"] == "a"
    assert listening.latest_night(now + 2 * 86400) is None, "đêm của mấy hôm trước không phải 'tối qua'"
    phone = {"night": {"id": "n1", "startedAt": now - 3600, "dismissed": True, "events": [event]}}
    listening.merge("a", phone)
    assert listening.latest_night(now) is None, "gạt đi trên điện thoại thì máy tính cũng thôi nhắc"


# ---- đồng bộ điện thoại ---------------------------------------------------------------------------------------


def test_a_pairing_code_works_once_and_expires(tmp_path: Path) -> None:
    devices = Devices(tmp_path / "devices.json")
    assert devices.pairing() is None, "chưa bấm Ghép điện thoại thì không có mã nào"
    code = devices.start_pairing()["code"]
    assert devices.pair("000000" if code != "000000" else "111111", "Điện thoại") is None
    token = devices.pair(f"{code[:3]} {code[3:]}", "Điện thoại của Anh")
    assert token and devices.check(token), "gõ mã có dấu cách như trên màn hình cũng được"
    assert devices.pair(code, "máy khác") is None, "mã ghép nối chỉ dùng một lần"
    assert devices.pair("٤٨٢٩١٣", "chữ số không phải ASCII") is None, "không được nổ TypeError của compare_digest"
    devices.revoke(devices.list()[0]["id"])
    assert not devices.check(token)


def test_guessing_the_pairing_code_burns_it(tmp_path: Path) -> None:
    """Một triệu khả năng: máy lạ trong mạng đoán mò được trong vài phút nếu mã cứ sống. Sai 5 lần là huỷ mã, và
    mã KHÔNG tự sinh lại - người dùng thấy lý do rồi chủ động tạo mã mới."""
    devices = Devices(tmp_path / "devices.json")
    code = devices.start_pairing()["code"]
    wrong = "000000" if code != "000000" else "111111"
    for _ in range(PAIRING_ATTEMPTS):
        assert devices.pair(wrong, "máy lạ") is None
    assert devices.blocked and devices.pairing() is None
    assert devices.pair(code, "chủ máy") is None, "mã đúng cũng hết giá trị sau khi bị đoán mò"
    fresh = devices.start_pairing()["code"]
    assert not devices.blocked
    assert devices.pair(fresh, "chủ máy")


def test_sync_remembers_what_the_user_chose_not_what_happened(library) -> None:
    """Tuỳ chọn là Ý MUỐN: đóng app hay cổng bận lúc mở không được lặng lẽ tắt đồng bộ của lần mở sau."""
    lib, _project, listening = library
    preferences = lib.preferences
    app = App(preferences=preferences, runner=FakeRunner(), token="t", listening=listening)
    app.sync_host, app.sync_port = "127.0.0.1", 0
    view = app.set_sync(True)
    assert view["enabled"] and preferences.get()["syncEnabled"]
    assert view["pairing"] is None, "mã chỉ có khi người dùng bấm Ghép điện thoại"
    app.close()
    assert preferences.get()["syncEnabled"], "đóng app không được tắt đồng bộ của lần mở sau"

    holder = socket.socket()
    holder.bind(("127.0.0.1", 0))
    holder.listen()
    try:
        app.sync_port = holder.getsockname()[1]
        view = app.set_sync(True)
    finally:
        holder.close()
    assert not view["enabled"] and view["error"] and view["wanted"], "cổng bận: báo lỗi, không cướp cổng"
    assert preferences.get()["syncEnabled"]
    assert not app.set_sync(False)["wanted"] and not preferences.get()["syncEnabled"]


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
        code = devices.start_pairing()["code"]
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


# ---- xuất sách, chỗ đọc, quét nguồn ---------------------------------------------------------------------------


def test_export_file_names_are_safe_and_keep_vietnamese() -> None:
    from ebook_reader.webui.export import safe_name

    assert safe_name('Chương 646: Trở về/1?') == "Chương 646 Trở về 1"
    assert safe_name('  "..."  ') == "Sach"


def test_export_takes_only_a_real_png_cover(tmp_path: Path) -> None:
    import base64

    from ebook_reader.webui.export import _cover_file

    gif = "data:image/png;base64," + base64.b64encode(b"GIF89a" + b"\0" * 20).decode()
    assert _cover_file(tmp_path, gif) is None, "đuôi PNG nhưng ruột không phải PNG"
    png = "data:image/png;base64," + base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"\0" * 20).decode()
    assert _cover_file(tmp_path, png) == tmp_path / "cover.png"


def test_the_reading_place_is_kept_and_the_newest_device_wins(tmp_path: Path) -> None:
    listening = Listening(tmp_path / "listening.json")
    listening.set_reading("b", 3, 24)
    mine = listening.get("b")["reading"]
    assert (mine["chapterId"], mine["index"]) == (3, 24)
    older = {"reading": {"chapterId": 1, "index": 5, "at": mine["at"] - 100}}
    assert listening.merge("b", older)["reading"]["chapterId"] == 3
    newer = {"reading": {"chapterId": 4, "index": 0, "at": mine["at"] + 100}}
    assert listening.merge("b", newer)["reading"]["chapterId"] == 4


def test_scanning_tells_a_missing_folder_from_a_parent_folder(tmp_path: Path) -> None:
    from ebook_reader.webui.actions import scan_inputs

    book = tmp_path / "Truyện" / "Tập 1"
    book.mkdir(parents=True)
    (book / "1.txt").write_text("Chương 1\nMở đầu.", encoding="utf-8")
    parent = scan_inputs([str(tmp_path / "Truyện")])
    assert parent["files"] == [] and parent["subfolders"] == [str(book)]
    quoted = scan_inputs([f'"{book}"'])
    assert len(quoted["files"]) == 1, "đường dẫn chép bằng Copy as path có ngoặc kép"
    missing = scan_inputs([str(tmp_path / "không có")])
    assert missing["missing"] == [str(tmp_path / "không có")]


def test_listening_sessions_are_kept_merged_and_left_out_of_lists(tmp_path: Path) -> None:
    listening = Listening(tmp_path / "listening.json")
    session = {"id": "s1", "device": "desktop", "startedAt": 100, "endedAt": 400, "listened": 300,
               "from": {"chapterId": 1, "seconds": 10}, "to": {"chapterId": 2, "seconds": 5}}
    listening.add_session("b", session)
    listening.add_session("b", {**session, "listened": 310})
    assert [item["listened"] for item in listening.sessions("b")] == [310], "cùng id là cùng một phiên"
    phone = {"sessions": [{**session, "id": "p1", "device": "phone", "startedAt": 50}]}
    merged = listening.merge("b", phone)
    assert [item["id"] for item in merged["sessions"]] == ["p1", "s1"]
