"""Dữ liệu một cuốn sách cho giao diện - CHỈ ĐỌC.

Mọi kết nối mở bằng URI `mode=ro` + `PRAGMA query_only`, không migrate, không ghi, không chạm file điều khiển
(AGENTS.md: nhánh quan sát là read-only; SQLite đang chạy đọc bằng `mode=ro`, không `immutable=1` vì có WAL).
Không dùng `_ReadOnlyProjectDB` của CLI: nó chép nguyên file DB (136 MB cho một lô 40 chương) mỗi lần mở -
đúng cho một lệnh chạy một lần, sai cho một giao diện hỏi trạng thái mỗi giây.

Mọi con số ở đây đo trên bảng thật: `segments.status` (không phải `speaker`, cột có mặc định), `wav_sha256`
cho "đã thu", `chapters.completed_at` cho mốc chương xong. Nhãn tiếng Việt nằm ở `humanize.py`.
"""
from __future__ import annotations

import json
import re
import sqlite3
import time
from collections import Counter, defaultdict
from contextlib import closing
from pathlib import Path
from typing import Any, Iterable

from . import humanize

DB_NAME = "project.sqlite3"
SETTINGS_NAME = "book_settings.json"
FINAL_SEGMENT_STATUSES = ("verified", "warning", "failed")
ACCEPTED_SEGMENT_STATUSES = ("verified", "warning")
# Tỉ trọng thời gian thật của hai pha trên máy này (lô 18, 26-09): phân tích 4,7 giờ, thu âm ~5 giờ.
ANALYSIS_WEIGHT = 0.47
RATE_WINDOW_SECONDS = 30 * 60.0
MIN_RATE_SAMPLES = 12
LEASE_FRESH_SECONDS = 120.0
STABLE_ID = re.compile(r"^c(\d+)_s(\d+)_")


def is_project(path: Path) -> bool:
    return (path / DB_NAME).is_file() and (path / SETTINGS_NAME).is_file()


def touched(project_root: Path) -> float:
    """Lần ghi cuối: mốc muộn hơn giữa file DB và `-wal` (WAL ghi vào `-wal` trước, file chính đổi khi checkpoint)."""
    database = project_root / DB_NAME
    stamps = []
    for candidate in (database, database.with_name(DB_NAME + "-wal")):
        try:
            stamps.append(candidate.stat().st_mtime)
        except OSError:
            pass
    return max(stamps) if stamps else 0.0


def connect(project_root: Path) -> sqlite3.Connection:
    uri = (project_root / DB_NAME).resolve().as_uri() + "?mode=ro"
    connection = sqlite3.connect(uri, uri=True, timeout=5.0)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only=ON")
    return connection


def _table_names(connection: sqlite3.Connection) -> set[str]:
    return {str(row[0]) for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}


def read_settings(project_root: Path) -> dict[str, Any]:
    try:
        return json.loads((project_root / SETTINGS_NAME).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def chapter_mp3(project_root: Path, recorded_path: str | None) -> Path | None:
    """File MP3 của chương, tìm theo TÊN trong chính thư mục sách - không tin đường dẫn tuyệt đối trong DB,
    vì sách có thể đã được chuyển chỗ (và server chỉ phát file nằm trong thư mục sách)."""
    if not recorded_path:
        return None
    name = Path(str(recorded_path).replace("\\", "/")).name
    candidate = project_root / "output" / "chapters" / name
    return candidate if candidate.is_file() else None


def segment_audio(project_root: Path, recorded_path: str | None) -> Path | None:
    """WAV của một câu, chỉ khi nó nằm trong thư mục sách."""
    if not recorded_path:
        return None
    path = Path(str(recorded_path))
    if not path.is_absolute():
        path = project_root / path
    try:
        resolved = path.resolve()
        resolved.relative_to(project_root.resolve())
    except (OSError, ValueError):
        return None
    return resolved if resolved.is_file() else None


def lease_age(connection: sqlite3.Connection, now: float) -> float | None:
    if "worker_leases" not in _table_names(connection):
        return None
    row = connection.execute("SELECT MAX(heartbeat_at) AS beat FROM worker_leases").fetchone()
    if row is None or row["beat"] is None:
        return None
    try:
        return max(0.0, now - float(row["beat"]))
    except (TypeError, ValueError):
        return None


def _rate(connection: sqlite3.Connection, where: str, now: float) -> float | None:
    """Số câu mỗi giây trong 30 phút gần nhất, hoặc None khi chưa đủ mẫu để nói gì."""
    row = connection.execute(
        f"SELECT COUNT(*) AS n, MIN(updated_at) AS first FROM segments WHERE updated_at >= ? AND ({where})",
        (now - RATE_WINDOW_SECONDS,),
    ).fetchone()
    count = int(row["n"] or 0)
    if count < MIN_RATE_SAMPLES or row["first"] is None:
        return None
    span = max(60.0, now - float(row["first"]))
    return count / span


def chapter_names(connection: sqlite3.Connection) -> dict[int, dict[str, Any]]:
    """chapter_id -> {index, name, subtitle, full} theo dòng tiêu đề đầu chương (xem `humanize.chapter_names`)."""
    headings = {
        int(row["chapter_id"]): str(row["text"] or "")
        for row in connection.execute("SELECT chapter_id, text, MIN(seq) FROM segments GROUP BY chapter_id")
    }
    out: dict[int, dict[str, Any]] = {}
    for row in connection.execute("SELECT id, chapter_index, title FROM chapters"):
        name, subtitle = humanize.chapter_names(str(row["title"]), headings.get(int(row["id"])))
        out[int(row["id"])] = {
            "index": int(row["chapter_index"]),
            "name": name,
            "subtitle": subtitle,
            "full": f"{name} · {subtitle}" if subtitle else name,
        }
    return out


def summarize(project_root: Path, *, running: bool = False, now: float | None = None) -> dict[str, Any]:
    """Tóm tắt một cuốn cho thư viện và phần đầu trang sách."""
    now = time.time() if now is None else now
    settings = read_settings(project_root)
    with closing(connect(project_root)) as connection:
        book = connection.execute("SELECT * FROM book WHERE id=1").fetchone()
        if book is None:
            raise ValueError(f"{project_root} chưa được khởi tạo")
        chapter_rows = connection.execute("SELECT status, COUNT(*) AS n FROM chapters GROUP BY status").fetchall()
        segments = connection.execute(
            "SELECT COUNT(*) AS total,"
            " SUM(status != 'pending') AS analyzed,"
            " SUM(wav_sha256 IS NOT NULL AND wav_sha256 != '') AS recorded,"
            f" SUM(status IN {FINAL_SEGMENT_STATUSES}) AS finished,"
            " SUM(status = 'failed') AS failed"
            " FROM segments"
        ).fetchone()
        audio = connection.execute(
            "SELECT COALESCE(SUM(s.wav_duration), 0) + COALESCE(SUM(s.break_ms), 0) / 1000.0 AS seconds"
            " FROM segments s JOIN chapters c ON c.id = s.chapter_id WHERE c.status = 'completed'"
        ).fetchone()
        beat_age = lease_age(connection, now)
        status = str(book["status"])
        stage = str(book["stage"] or "")
        phase = humanize.phase_of(status, stage)
        total = int(segments["total"] or 0)
        analyzed = int(segments["analyzed"] or 0)
        finished = int(segments["finished"] or 0)
        eta = None
        if running and phase == "analysis" and total:
            rate = _rate(connection, "status != 'pending'", now)
            if rate:
                eta = {"phase": "analysis", "seconds": round((total - analyzed) / rate)}
        elif running and phase == "synthesis" and total:
            rate = _rate(connection, f"status IN {FINAL_SEGMENT_STATUSES}", now)
            if rate:
                eta = {"phase": "synthesis", "seconds": round((total - finished) / rate)}

    chapters = Counter({str(row["status"]): int(row["n"]) for row in chapter_rows})
    chapter_total = sum(chapters.values())
    analysis_fraction = analyzed / total if total else 0.0
    synthesis_fraction = finished / total if total else 0.0
    if phase == "done":
        overall = 1.0
    else:
        overall = ANALYSIS_WEIGHT * analysis_fraction + (1 - ANALYSIS_WEIGHT) * synthesis_fraction
    active = running or (beat_age is not None and beat_age <= LEASE_FRESH_SECONDS and phase in humanize.WORKING_PHASES)
    voices = settings.get("voices", {}) if isinstance(settings.get("voices"), dict) else {}
    profile = str(settings.get("quality_profile") or "")
    return {
        "path": str(project_root),
        "title": str(book["title"]),
        "status": status,
        "stage": stage,
        "phase": phase,
        "statusLabel": humanize.status_label(phase, stage, active=active),
        "running": bool(active),
        "interrupted": phase in humanize.WORKING_PHASES and not active,
        "createdAt": float(book["created_at"] or 0) or None,
        "updatedAt": max(float(book["updated_at"] or 0), touched(project_root)) or None,
        "lastError": str(book["last_error"] or ""),
        "settings": {
            "profile": profile,
            "profileLabel": humanize.PROFILE_LABELS.get(profile, profile),
            "narrator": str(voices.get("narrator_voice") or ""),
        },
        "chapters": {
            "total": chapter_total,
            "completed": chapters.get("completed", 0),
            "failed": chapters.get("failed", 0),
            "working": chapters.get("synthesizing", 0) + chapters.get("verifying", 0),
        },
        "segments": {
            "total": total,
            "analyzed": analyzed,
            "recorded": int(segments["recorded"] or 0),
            "finished": finished,
            "failed": int(segments["failed"] or 0),
        },
        "progress": {
            "overall": round(overall, 4),
            "analysis": round(analysis_fraction, 4),
            "synthesis": round(synthesis_fraction, 4),
        },
        "audioSeconds": round(float(audio["seconds"] or 0.0), 1),
        "eta": eta,
    }


def chapters(project_root: Path) -> list[dict[str, Any]]:
    with closing(connect(project_root)) as connection:
        per_chapter = {
            int(row["chapter_id"]): row
            for row in connection.execute(
                "SELECT chapter_id,"
                " COUNT(*) AS total,"
                " SUM(status != 'pending') AS analyzed,"
                " SUM(wav_sha256 IS NOT NULL AND wav_sha256 != '') AS recorded,"
                f" SUM(status IN {FINAL_SEGMENT_STATUSES}) AS finished,"
                " SUM(status = 'failed') AS failed,"
                " SUM(status = 'warning') AS warnings,"
                " COALESCE(SUM(wav_duration), 0) + COALESCE(SUM(break_ms), 0) / 1000.0 AS seconds"
                " FROM segments GROUP BY chapter_id"
            )
        }
        rows = connection.execute(
            "SELECT id, chapter_index, title, status, total_segments, output_mp3, started_at, completed_at, last_error"
            " FROM chapters ORDER BY chapter_index"
        ).fetchall()
        names = chapter_names(connection)
    out = []
    for row in rows:
        counts = per_chapter.get(int(row["id"]))
        status = str(row["status"])
        mp3 = chapter_mp3(project_root, row["output_mp3"]) if status == "completed" else None
        out.append({
            "id": int(row["id"]),
            "index": int(row["chapter_index"]),
            "title": str(row["title"]),
            "displayTitle": names[int(row["id"])]["name"],
            "subtitle": names[int(row["id"])]["subtitle"],
            "fullTitle": names[int(row["id"])]["full"],
            "status": status,
            "statusLabel": humanize.CHAPTER_STATUS_LABELS.get(status, status),
            "segments": {
                "total": int(counts["total"]) if counts else int(row["total_segments"] or 0),
                "analyzed": int(counts["analyzed"] or 0) if counts else 0,
                "recorded": int(counts["recorded"] or 0) if counts else 0,
                "finished": int(counts["finished"] or 0) if counts else 0,
                "failed": int(counts["failed"] or 0) if counts else 0,
                "warnings": int(counts["warnings"] or 0) if counts else 0,
            },
            "seconds": round(float(counts["seconds"] or 0.0), 1) if counts else 0.0,
            "playable": mp3 is not None,
            "startedAt": float(row["started_at"]) if row["started_at"] else None,
            "completedAt": float(row["completed_at"]) if row["completed_at"] else None,
            "lastError": humanize.error_text(str(row["last_error"] or "")),
        })
    return out


_DURATION_CACHE: dict[tuple[str, float], float] = {}


def audio_duration(path: Path) -> float | None:
    """Độ dài thật của file audio (MP3 đọc bằng libsndfile >= 1.1, ~10 ms). Cache theo mtime."""
    try:
        stamp = path.stat().st_mtime
    except OSError:
        return None
    key = (str(path), stamp)
    if key not in _DURATION_CACHE:
        try:
            import soundfile

            _DURATION_CACHE[key] = float(soundfile.info(str(path)).duration)
        except Exception:  # noqa: BLE001 - không đọc được thì để kịch bản dùng tổng độ dài các câu
            return None
    return _DURATION_CACHE[key]


def chapter_script(project_root: Path, chapter_id: int) -> dict[str, Any] | None:
    """Văn bản chương theo từng câu, kèm mốc thời gian trong file MP3 - cho chế độ "đọc theo".

    Chương MP3 là các WAV câu nối nhau, sau mỗi câu (trừ câu cuối) là `break_ms` im lặng
    (`audio_io._source_timeline`). Tổng `wav_duration + break_ms` của chương 645 (lô 16) là 783,6 s, file MP3
    đo được 783,74 s: lệch 0,14 s trên 13 phút. Vẫn co giãn tuyến tính theo độ dài MP3 thật để phần lệch ấy
    không dồn về cuối chương.
    """
    with closing(connect(project_root)) as connection:
        chapter = connection.execute(
            "SELECT id, title, status, output_mp3 FROM chapters WHERE id = ?", (chapter_id,)
        ).fetchone()
        if chapter is None:
            return None
        rows = connection.execute(
            "SELECT id, seq, paragraph_index, text, kind, speaker, wav_duration, break_ms, status"
            " FROM segments WHERE chapter_id = ? ORDER BY seq",
            (chapter_id,),
        ).fetchall()
        names = {
            str(row["canonical_name"]): str(row["display_name"] or row["canonical_name"])
            for row in connection.execute("SELECT canonical_name, display_name FROM characters")
        }
        chapter_name = chapter_names(connection).get(int(chapter["id"]), {})
    timed = str(chapter["status"]) == "completed" and all(row["wav_duration"] for row in rows)
    starts: list[float] = []
    elapsed = 0.0
    for index, row in enumerate(rows):
        starts.append(elapsed)
        elapsed += float(row["wav_duration"] or 0.0)
        if index + 1 < len(rows):
            elapsed += float(row["break_ms"] or 0) / 1000.0
    mp3 = chapter_mp3(project_root, chapter["output_mp3"]) if timed else None
    real = audio_duration(mp3) if mp3 else None
    scale = (real / elapsed) if (real and elapsed) else 1.0
    segments = []
    for index, row in enumerate(rows):
        speaker = str(row["speaker"] or "")
        start = starts[index] * scale
        end = (starts[index] + float(row["wav_duration"] or 0.0)) * scale
        heading = index == 0 and humanize.is_heading(str(row["text"]))
        segments.append({
            "id": int(row["id"]),
            "paragraph": int(row["paragraph_index"] or 0),
            "text": str(row["text"]),
            "kind": "heading" if heading else str(row["kind"] or "narration"),
            "speaker": "" if speaker in ("", "NARRATOR") else humanize.person_name(names.get(speaker, speaker)),
            "start": round(start, 3) if timed else None,
            "end": round(end, 3) if timed else None,
            "status": str(row["status"]),
        })
    return {
        "chapterId": int(chapter["id"]),
        "title": chapter_name.get("full") or humanize.chapter_title(str(chapter["title"])),
        "timed": bool(timed and mp3),
        "duration": round(real if real else elapsed, 3),
        "segments": segments,
    }


def chapter_audio_path(project_root: Path, chapter_id: int) -> Path | None:
    with closing(connect(project_root)) as connection:
        row = connection.execute(
            "SELECT status, output_mp3 FROM chapters WHERE id = ?", (chapter_id,)
        ).fetchone()
    if row is None or str(row["status"]) != "completed":
        return None
    return chapter_mp3(project_root, row["output_mp3"])


def _voice_view(profile: sqlite3.Row | None) -> dict[str, Any] | None:
    if profile is None:
        return None
    formant = float(profile["formant_ratio"] or 1.0)
    pitch = float(profile["pitch_semitones"] or 0.0)
    return {
        "key": str(profile["voice_key"]),
        "preset": str(profile["preset_name"]),
        "tone": humanize.voice_tone(formant, pitch),
    }


def cast(project_root: Path) -> dict[str, Any]:
    """Ai nói trong CUỐN NÀY, bằng giọng nào. Sổ nhân vật của một lô là sổ cộng dồn cả sách (636 người ở lô 16,
    88 người thật sự lên tiếng), nên chỉ lấy những ai có câu trong bảng `segments` của project này."""
    settings = read_settings(project_root)
    voices = settings.get("voices", {}) if isinstance(settings.get("voices"), dict) else {}
    with closing(connect(project_root)) as connection:
        profiles = {int(row["id"]): row for row in connection.execute("SELECT * FROM voice_profiles")}
        characters = {
            str(row["canonical_name"]): row for row in connection.execute("SELECT * FROM characters")
        }
        spoken = connection.execute(
            "SELECT speaker, kind, voice_profile_id, COUNT(*) AS lines,"
            " COALESCE(SUM(wav_duration), 0) AS seconds, MIN(chapter_id) AS first_chapter"
            " FROM segments GROUP BY speaker, kind, voice_profile_id"
        ).fetchall()
        samples = {
            str(row["speaker"]): int(row["id"])
            for row in connection.execute(
                "SELECT speaker, id FROM ("
                "  SELECT speaker, id, ROW_NUMBER() OVER ("
                "    PARTITION BY speaker ORDER BY ABS(COALESCE(wav_duration, 0) - 4.0), id) AS rank"
                "  FROM segments WHERE kind = 'dialogue' AND status IN ('verified', 'warning')"
                "   AND wav_path IS NOT NULL AND wav_path != '' AND COALESCE(wav_duration, 0) >= 1.5"
                ") WHERE rank = 1"
            )
        }
        chapter_numbers = {chapter_id: item["name"] for chapter_id, item in chapter_names(connection).items()}
    lines: dict[str, int] = defaultdict(int)
    seconds: dict[str, float] = defaultdict(float)
    voice_votes: dict[str, Counter[int]] = defaultdict(Counter)
    first_seen: dict[str, int] = {}
    for row in spoken:
        speaker = str(row["speaker"] or "")
        lines[speaker] += int(row["lines"])
        seconds[speaker] += float(row["seconds"] or 0.0)
        if row["voice_profile_id"] is not None:
            voice_votes[speaker][int(row["voice_profile_id"])] += int(row["lines"])
        first = int(row["first_chapter"])
        first_seen[speaker] = min(first, first_seen.get(speaker, first))

    def voice_of(speaker: str) -> dict[str, Any] | None:
        votes = voice_votes.get(speaker)
        if not votes:
            return None
        return _voice_view(profiles.get(votes.most_common(1)[0][0]))

    narrator = {
        "voice": str(voices.get("narrator_voice") or ""),
        "lines": lines.get("NARRATOR", 0),
        "seconds": round(seconds.get("NARRATOR", 0.0), 1),
        "profile": voice_of("NARRATOR"),
    }
    main, extras = [], []
    for speaker, count in lines.items():
        if speaker in ("", "NARRATOR"):
            continue
        record = characters.get(speaker)
        entry = {
            "name": speaker,
            "displayName": humanize.person_name(str(record["display_name"] or speaker) if record else speaker),
            "gender": humanize.GENDER_LABELS.get(str(record["gender"] if record else ""), ""),
            "age": humanize.AGE_LABELS.get(str(record["age"] if record else ""), ""),
            "lines": count,
            "seconds": round(seconds[speaker], 1),
            "voice": voice_of(speaker),
            "sampleId": samples.get(speaker),
            "firstChapter": chapter_numbers.get(first_seen.get(speaker, -1), ""),
        }
        (main if record is not None else extras).append(entry)
    main.sort(key=lambda entry: (-entry["lines"], entry["displayName"]))
    extras.sort(key=lambda entry: (-entry["lines"], entry["displayName"]))
    return {"narrator": narrator, "characters": main, "extras": extras}


def sample_audio_path(project_root: Path, segment_id: int) -> Path | None:
    with closing(connect(project_root)) as connection:
        row = connection.execute("SELECT wav_path FROM segments WHERE id = ?", (segment_id,)).fetchone()
    return segment_audio(project_root, row["wav_path"]) if row else None


def activity(project_root: Path, *, technical: bool = False, limit: int = 200) -> list[dict[str, Any]]:
    """Nhật ký cho người đọc: mốc chương xong, lỗi và cảnh báo có nghĩa với người nghe. `technical=True` trả
    thẳng các dòng sự kiện gần nhất, không dịch."""
    with closing(connect(project_root)) as connection:
        tables = _table_names(connection)
        if technical:
            if "runtime_events" not in tables:
                return []
            rows = connection.execute(
                "SELECT id, timestamp, level, code, message FROM runtime_events ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
            return [
                {"id": f"e{row['id']}", "at": float(row["timestamp"] or 0), "level": str(row["level"]),
                 "code": str(row["code"]), "text": str(row["message"])}
                for row in rows
            ]
        names = chapter_names(connection)
        chapter_titles = {item["index"]: item["name"] for item in names.values()}
        items: list[dict[str, Any]] = []
        book = connection.execute("SELECT created_at FROM book WHERE id=1").fetchone()
        if book and book["created_at"]:
            items.append({"id": "created", "at": float(book["created_at"]), "level": "info", "kind": "created",
                          "text": "Đã tạo sách"})
        for row in connection.execute(
            "SELECT id, chapter_index, title, completed_at, status FROM chapters WHERE completed_at IS NOT NULL"
        ):
            items.append({
                "id": f"c{row['id']}", "at": float(row["completed_at"]), "level": "success", "kind": "chapter",
                "text": f"Xong {names.get(int(row['id']), {}).get('full', humanize.chapter_title(str(row['title'])))}",
            })
        if "runtime_events" in tables:
            placeholders = ",".join("?" for _ in humanize.EVENT_TEXT)
            for row in connection.execute(
                f"SELECT id, timestamp, level, code, message FROM runtime_events WHERE code IN ({placeholders})"
                " ORDER BY id DESC LIMIT 400",
                tuple(humanize.EVENT_TEXT),
            ):
                text = humanize.event_text(str(row["code"]), str(row["message"]), chapter_titles)
                if text:
                    items.append({"id": f"e{row['id']}", "at": float(row["timestamp"] or 0),
                                  "level": humanize.event_level(str(row["code"]), str(row["level"])),
                                  "kind": "event", "text": text})
    items.sort(key=lambda item: item["at"], reverse=True)
    return items[:limit]


def input_names(project_root: Path) -> Iterable[str]:
    with closing(connect(project_root)) as connection:
        for row in connection.execute("SELECT input_path FROM chapters ORDER BY chapter_index"):
            yield Path(str(row["input_path"])).name
