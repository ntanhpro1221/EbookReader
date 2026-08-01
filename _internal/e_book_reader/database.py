from __future__ import annotations

import json
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Sequence

from .models import BookStatus, ChapterStatus, SegmentStatus


DB_SCHEMA_VERSION = 4


SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS book (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    title TEXT NOT NULL,
    project_root TEXT NOT NULL,
    settings_hash TEXT NOT NULL,
    settings_json TEXT NOT NULL,
    status TEXT NOT NULL,
    stage TEXT NOT NULL DEFAULT 'created',
    input_manifest_hash TEXT NOT NULL,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    last_error TEXT,
    run_generation INTEGER NOT NULL DEFAULT 0,
    casting_finalized INTEGER NOT NULL DEFAULT 0,
    runtime_fingerprint_hash TEXT,
    runtime_fingerprint_json TEXT
);

CREATE TABLE IF NOT EXISTS chapters (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chapter_index INTEGER NOT NULL UNIQUE,
    title TEXT NOT NULL,
    input_path TEXT NOT NULL,
    input_sha256 TEXT NOT NULL,
    input_size INTEGER NOT NULL,
    output_mp3 TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    total_segments INTEGER NOT NULL DEFAULT 0,
    verified_segments INTEGER NOT NULL DEFAULT 0,
    warning_segments INTEGER NOT NULL DEFAULT 0,
    failed_segments INTEGER NOT NULL DEFAULT 0,
    started_at REAL,
    completed_at REAL,
    last_error TEXT
);

CREATE TABLE IF NOT EXISTS segments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    stable_id TEXT NOT NULL UNIQUE,
    chapter_id INTEGER NOT NULL REFERENCES chapters(id) ON DELETE CASCADE,
    seq INTEGER NOT NULL,
    paragraph_index INTEGER NOT NULL DEFAULT 0,
    break_ms INTEGER NOT NULL DEFAULT 220,
    text TEXT NOT NULL,
    text_sha256 TEXT NOT NULL,
    kind_hint TEXT NOT NULL,
    kind TEXT NOT NULL DEFAULT 'narration',
    speaker TEXT NOT NULL DEFAULT 'NARRATOR',
    canonical_character_id INTEGER REFERENCES characters(id),
    gender TEXT NOT NULL DEFAULT 'unknown',
    age TEXT NOT NULL DEFAULT 'unknown',
    emotion TEXT NOT NULL DEFAULT 'neutral',
    intensity INTEGER NOT NULL DEFAULT 1,
    pace TEXT NOT NULL DEFAULT 'normal',
    volume TEXT NOT NULL DEFAULT 'normal',
    confidence REAL NOT NULL DEFAULT 0.5,
    analysis_notes TEXT NOT NULL DEFAULT '',
    voice_profile_id INTEGER REFERENCES voice_profiles(id),
    status TEXT NOT NULL DEFAULT 'pending',
    attempt_count INTEGER NOT NULL DEFAULT 0,
    generation_seed INTEGER,
    wav_path TEXT,
    wav_sha256 TEXT,
    wav_duration REAL,
    signal_json TEXT,
    asr_text TEXT,
    asr_similarity REAL,
    asr_wer REAL,
    warning_code TEXT,
    error TEXT,
    updated_at REAL NOT NULL,
    UNIQUE(chapter_id, seq)
);

CREATE TABLE IF NOT EXISTS characters (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    canonical_name TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL,
    gender TEXT NOT NULL DEFAULT 'unknown',
    age TEXT NOT NULL DEFAULT 'unknown',
    personality TEXT NOT NULL DEFAULT '',
    importance TEXT NOT NULL DEFAULT 'minor',
    mention_count INTEGER NOT NULL DEFAULT 0,
    confidence REAL NOT NULL DEFAULT 0.5,
    locked INTEGER NOT NULL DEFAULT 0,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS character_aliases (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    character_id INTEGER NOT NULL REFERENCES characters(id) ON DELETE CASCADE,
    alias TEXT NOT NULL,
    normalized_alias TEXT NOT NULL UNIQUE,
    confidence REAL NOT NULL DEFAULT 0.5,
    source TEXT NOT NULL DEFAULT 'analysis'
);

CREATE TABLE IF NOT EXISTS pronunciations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    surface TEXT NOT NULL,
    normalized_surface TEXT NOT NULL UNIQUE,
    spoken_form TEXT NOT NULL,
    confidence REAL NOT NULL DEFAULT 0.5,
    source TEXT NOT NULL DEFAULT 'analysis',
    locked INTEGER NOT NULL DEFAULT 0,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS voice_profiles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    voice_key TEXT NOT NULL UNIQUE,
    engine TEXT NOT NULL,
    preset_name TEXT,
    description TEXT NOT NULL DEFAULT '',
    seed INTEGER NOT NULL,
    reference_wav TEXT,
    reference_sha256 TEXT,
    status TEXT NOT NULL DEFAULT 'planned',
    locked INTEGER NOT NULL DEFAULT 1,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS artifacts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    artifact_key TEXT NOT NULL UNIQUE,
    kind TEXT NOT NULL,
    path TEXT NOT NULL,
    sha256 TEXT,
    size_bytes INTEGER,
    verified INTEGER NOT NULL DEFAULT 0,
    metadata_json TEXT,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS runtime_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp REAL NOT NULL,
    level TEXT NOT NULL,
    code TEXT NOT NULL,
    message TEXT NOT NULL,
    details_json TEXT
);

CREATE TABLE IF NOT EXISTS worker_leases (
    worker_name TEXT PRIMARY KEY,
    pid INTEGER NOT NULL,
    generation INTEGER NOT NULL,
    state TEXT NOT NULL,
    heartbeat_at REAL NOT NULL,
    current_item TEXT,
    metadata_json TEXT
);

CREATE INDEX IF NOT EXISTS idx_segments_chapter_status ON segments(chapter_id, status, seq);
CREATE INDEX IF NOT EXISTS idx_segments_status ON segments(status);
CREATE INDEX IF NOT EXISTS idx_segments_speaker ON segments(speaker);
CREATE INDEX IF NOT EXISTS idx_runtime_events_time ON runtime_events(timestamp);
"""


class ProjectDB:
    def __init__(self, path: Path, synchronous: str = "FULL") -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.synchronous = synchronous.upper()
        if self.synchronous not in {"OFF", "NORMAL", "FULL", "EXTRA"}:
            raise ValueError(f"Unsupported SQLite synchronous mode: {synchronous}")
        with self.connect() as conn:
            current_version = int(conn.execute("PRAGMA user_version").fetchone()[0])
            if current_version > DB_SCHEMA_VERSION:
                raise RuntimeError(
                    f"Project database schema {current_version} is newer than supported {DB_SCHEMA_VERSION}"
                )
            has_user_tables = bool(
                conn.execute(
                    """
                    SELECT 1 FROM sqlite_master
                    WHERE type='table' AND name NOT LIKE 'sqlite_%'
                    LIMIT 1
                    """
                ).fetchone()
            )
            if current_version < DB_SCHEMA_VERSION and has_user_tables:
                backup_path = self.path.with_suffix(
                    self.path.suffix + f".schema-v{current_version}.bak"
                )
                if not backup_path.exists():
                    with sqlite3.connect(backup_path) as backup:
                        conn.backup(backup)
            conn.executescript(SCHEMA)
            self._migrate_schema(conn)

    @staticmethod
    def _migrate_schema(conn: sqlite3.Connection) -> None:
        segment_columns = {str(row[1]) for row in conn.execute("PRAGMA table_info(segments)")}
        if "break_ms" not in segment_columns:
            conn.execute("ALTER TABLE segments ADD COLUMN break_ms INTEGER NOT NULL DEFAULT 220")

        book_columns = {str(row[1]) for row in conn.execute("PRAGMA table_info(book)")}
        if "casting_finalized" not in book_columns:
            conn.execute("ALTER TABLE book ADD COLUMN casting_finalized INTEGER NOT NULL DEFAULT 0")
            conn.execute(
                """
                UPDATE book SET casting_finalized=1
                WHERE EXISTS(
                    SELECT 1 FROM segments
                    WHERE voice_profile_id IS NOT NULL
                      AND status IN ('signal_passed','asr_passed','verified','warning','failed')
                )
                """
            )
        book_columns = {str(row[1]) for row in conn.execute("PRAGMA table_info(book)")}
        if "runtime_fingerprint_hash" not in book_columns:
            conn.execute("ALTER TABLE book ADD COLUMN runtime_fingerprint_hash TEXT")
        if "runtime_fingerprint_json" not in book_columns:
            conn.execute("ALTER TABLE book ADD COLUMN runtime_fingerprint_json TEXT")
        conn.execute(f"PRAGMA user_version={DB_SCHEMA_VERSION}")

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path, timeout=60, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout=60000")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute(f"PRAGMA synchronous={self.synchronous}")
        try:
            yield conn
        finally:
            conn.close()

    @contextmanager
    def transaction(self, immediate: bool = True) -> Iterator[sqlite3.Connection]:
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE" if immediate else "BEGIN")
            try:
                yield conn
                conn.execute("COMMIT")
            except Exception:
                conn.execute("ROLLBACK")
                raise

    def initialize_book(
        self,
        *,
        title: str,
        project_root: Path,
        settings: dict[str, Any],
        settings_hash: str,
        input_manifest_hash: str,
    ) -> None:
        now = time.time()
        payload = json.dumps(settings, ensure_ascii=False, sort_keys=True)
        with self.transaction() as conn:
            existing = conn.execute("SELECT * FROM book WHERE id=1").fetchone()
            if existing:
                if existing["settings_hash"] != settings_hash:
                    raise RuntimeError(
                        "Book settings are locked. Resume must use the exact original settings; "
                        "clone the project to change them."
                    )
                if existing["input_manifest_hash"] != input_manifest_hash:
                    raise RuntimeError("Input file list or content changed after this book project was created.")
                return
            conn.execute(
                """
                INSERT INTO book(
                    id,title,project_root,settings_hash,settings_json,status,stage,
                    input_manifest_hash,created_at,updated_at,run_generation
                ) VALUES(1,?,?,?,?,?,?,?,?,?,0)
                """,
                (
                    title,
                    str(project_root.resolve()),
                    settings_hash,
                    payload,
                    BookStatus.CREATED.value,
                    "created",
                    input_manifest_hash,
                    now,
                    now,
                ),
            )

    def book(self) -> sqlite3.Row:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM book WHERE id=1").fetchone()
            if row is None:
                raise RuntimeError("Project database has not been initialized")
            return row

    def update_book(self, *, status: str | None = None, stage: str | None = None, error: str | None = None) -> None:
        fields = ["updated_at=?"]
        params: list[Any] = [time.time()]
        if status is not None:
            fields.append("status=?")
            params.append(status)
        if stage is not None:
            fields.append("stage=?")
            params.append(stage)
        if error is not None or status in {BookStatus.COMPLETED.value, BookStatus.ANALYZED.value}:
            fields.append("last_error=?")
            params.append(error)
        params.append(1)
        with self.connect() as conn:
            conn.execute(f"UPDATE book SET {', '.join(fields)} WHERE id=?", params)

    def begin_run_generation(self) -> int:
        with self.transaction() as conn:
            conn.execute(
                "UPDATE book SET run_generation=run_generation+1, updated_at=? WHERE id=1",
                (time.time(),),
            )
            return int(conn.execute("SELECT run_generation FROM book WHERE id=1").fetchone()[0])

    def casting_is_finalized(self) -> bool:
        return bool(int(self.book()["casting_finalized"]))

    def finalize_casting(self) -> None:
        with self.connect() as conn:
            conn.execute(
                "UPDATE book SET casting_finalized=1,stage='voice_cast_locked',updated_at=? WHERE id=1",
                (time.time(),),
            )

    def bind_runtime_fingerprint(self, payload: dict[str, Any], fingerprint_hash: str) -> None:
        serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        with self.transaction() as conn:
            row = conn.execute(
                "SELECT runtime_fingerprint_hash FROM book WHERE id=1"
            ).fetchone()
            if row is None:
                raise RuntimeError("Project database has not been initialized")
            existing = str(row["runtime_fingerprint_hash"] or "")
            if existing and existing != fingerprint_hash:
                raise RuntimeError(
                    "Runtime/model fingerprint khác lần chạy đầu; từ chối resume để giữ chất lượng và giọng"
                )
            if not existing:
                conn.execute(
                    """
                    UPDATE book SET runtime_fingerprint_hash=?,runtime_fingerprint_json=?,updated_at=?
                    WHERE id=1
                    """,
                    (fingerprint_hash, serialized, time.time()),
                )

    def ensure_chapters(self, rows: Sequence[dict[str, Any]]) -> list[int]:
        ids: list[int] = []
        with self.transaction() as conn:
            for row in rows:
                existing = conn.execute(
                    "SELECT * FROM chapters WHERE chapter_index=?", (int(row["chapter_index"]),)
                ).fetchone()
                if existing:
                    if existing["input_sha256"] != row["input_sha256"]:
                        raise RuntimeError(f"Chapter source changed: {row['input_path']}")
                    ids.append(int(existing["id"]))
                    continue
                cursor = conn.execute(
                    """
                    INSERT INTO chapters(
                        chapter_index,title,input_path,input_sha256,input_size,output_mp3,status
                    ) VALUES(?,?,?,?,?,?,?)
                    """,
                    (
                        int(row["chapter_index"]),
                        str(row["title"]),
                        str(Path(row["input_path"]).resolve()),
                        str(row["input_sha256"]),
                        int(row["input_size"]),
                        str(Path(row["output_mp3"]).resolve()),
                        ChapterStatus.PENDING.value,
                    ),
                )
                ids.append(int(cursor.lastrowid))
        return ids

    def list_chapters(self) -> list[sqlite3.Row]:
        with self.connect() as conn:
            return list(conn.execute("SELECT * FROM chapters ORDER BY chapter_index"))

    def get_chapter(self, chapter_id: int) -> sqlite3.Row:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM chapters WHERE id=?", (chapter_id,)).fetchone()
            if row is None:
                raise KeyError(chapter_id)
            return row

    def update_chapter_status(self, chapter_id: int, status: str, error: str | None = None) -> None:
        now = time.time()
        with self.connect() as conn:
            if status == ChapterStatus.SYNTHESIZING.value:
                conn.execute(
                    "UPDATE chapters SET status=?, started_at=COALESCE(started_at,?), last_error=? WHERE id=?",
                    (status, now, error, chapter_id),
                )
            elif status == ChapterStatus.COMPLETED.value:
                conn.execute(
                    "UPDATE chapters SET status=?, completed_at=?, last_error=NULL WHERE id=?",
                    (status, now, chapter_id),
                )
            else:
                conn.execute(
                    "UPDATE chapters SET status=?, last_error=? WHERE id=?", (status, error, chapter_id)
                )

    def replace_chapter_segments(self, chapter_id: int, rows: Sequence[dict[str, Any]]) -> None:
        now = time.time()
        with self.transaction() as conn:
            existing_count = int(
                conn.execute("SELECT COUNT(*) FROM segments WHERE chapter_id=?", (chapter_id,)).fetchone()[0]
            )
            if existing_count:
                return
            conn.executemany(
                """
                INSERT INTO segments(
                    stable_id,chapter_id,seq,paragraph_index,break_ms,text,text_sha256,kind_hint,
                    kind,speaker,gender,age,emotion,intensity,pace,volume,confidence,
                    analysis_notes,status,updated_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                [
                    (
                        row["stable_id"],
                        chapter_id,
                        int(row["seq"]),
                        int(row.get("paragraph_index", 0)),
                        int(row.get("break_ms", 220)),
                        row["text"],
                        row["text_sha256"],
                        row.get("kind_hint", "narration"),
                        row.get("kind", row.get("kind_hint", "narration")),
                        row.get("speaker", "NARRATOR"),
                        row.get("gender", "unknown"),
                        row.get("age", "unknown"),
                        row.get("emotion", "neutral"),
                        int(row.get("intensity", 1)),
                        row.get("pace", "normal"),
                        row.get("volume", "normal"),
                        float(row.get("confidence", 0.5)),
                        row.get("analysis_notes", ""),
                        row.get("status", SegmentStatus.PENDING.value),
                        now,
                    )
                    for row in rows
                ],
            )
            conn.execute(
                "UPDATE chapters SET total_segments=?, status=? WHERE id=?",
                (len(rows), ChapterStatus.PENDING.value, chapter_id),
            )

    def list_segments(
        self,
        chapter_id: int | None = None,
        statuses: Sequence[str] | None = None,
    ) -> list[sqlite3.Row]:
        clauses: list[str] = []
        params: list[Any] = []
        if chapter_id is not None:
            clauses.append("chapter_id=?")
            params.append(chapter_id)
        if statuses:
            marks = ",".join("?" for _ in statuses)
            clauses.append(f"status IN ({marks})")
            params.extend(statuses)
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        with self.connect() as conn:
            return list(conn.execute(f"SELECT * FROM segments{where} ORDER BY chapter_id,seq", params))

    def get_segment(self, segment_id: int) -> sqlite3.Row:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM segments WHERE id=?", (segment_id,)).fetchone()
        if row is None:
            raise KeyError(f"Unknown segment id: {segment_id}")
        return row

    @staticmethod
    def _merge_warning_codes(existing: str | None, warning_code: str | None) -> str | None:
        values = [value for value in str(existing or "").split("|") if value]
        for value in str(warning_code or "").split("|"):
            if value and value not in values:
                values.append(value)
        return "|".join(values) or None

    def update_analysis(
        self,
        segment_id: int,
        data: dict[str, Any],
        low_confidence_threshold: float = 0.58,
    ) -> None:
        confidence = float(data.get("confidence", 0.5))
        warning = "LOW_ANALYSIS_CONFIDENCE" if confidence < low_confidence_threshold else None
        status = SegmentStatus.WARNING.value if warning else SegmentStatus.ANALYZED.value
        personality = str(data.get("personality_hint", "")).strip()
        notes = str(data.get("notes", "")).strip()
        analysis_notes = "; ".join(
            value for value in (
                f"personality={personality}" if personality else "",
                notes,
            )
            if value
        )
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE segments SET
                    kind=?,speaker=?,gender=?,age=?,emotion=?,intensity=?,pace=?,volume=?,
                    confidence=?,analysis_notes=?,warning_code=?,status=?,updated_at=?
                WHERE id=?
                """,
                (
                    data.get("kind", "narration"),
                    data.get("speaker", "NARRATOR"),
                    data.get("gender", "unknown"),
                    data.get("age", "unknown"),
                    data.get("emotion", "neutral"),
                    int(data.get("intensity", 1)),
                    data.get("pace", "normal"),
                    data.get("volume", "normal"),
                    confidence,
                    analysis_notes,
                    warning,
                    status,
                    time.time(),
                    segment_id,
                ),
            )

    def set_segment_character(self, segment_id: int, character_id: int | None) -> None:
        with self.connect() as conn:
            conn.execute(
                "UPDATE segments SET canonical_character_id=?, updated_at=? WHERE id=?",
                (character_id, time.time(), segment_id),
            )

    def mark_generating(self, segment_id: int, seed: int) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE segments SET status=?,attempt_count=attempt_count+1,generation_seed=?,
                    error=NULL,updated_at=? WHERE id=?
                """,
                (SegmentStatus.GENERATING.value, seed, time.time(), segment_id),
            )

    def mark_signal_passed(
        self,
        segment_id: int,
        *,
        wav_path: Path,
        wav_sha256: str,
        duration: float,
        signal: dict[str, Any],
        generation_seed: int | None = None,
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE segments SET status=?,wav_path=?,wav_sha256=?,wav_duration=?,signal_json=?,
                    generation_seed=COALESCE(?,generation_seed),error=NULL,updated_at=? WHERE id=?
                """,
                (
                    SegmentStatus.SIGNAL_PASSED.value,
                    str(wav_path.resolve()),
                    wav_sha256,
                    duration,
                    json.dumps(signal, ensure_ascii=False),
                    generation_seed,
                    time.time(),
                    segment_id,
                ),
            )

    def mark_asr_result(
        self,
        segment_id: int,
        *,
        passed: bool,
        transcript: str,
        similarity: float,
        wer: float,
        warning_code: str | None = None,
    ) -> None:
        with self.transaction() as conn:
            existing = conn.execute(
                "SELECT warning_code FROM segments WHERE id=?", (segment_id,)
            ).fetchone()
            merged_warning = self._merge_warning_codes(
                str(existing["warning_code"]) if existing and existing["warning_code"] else None,
                warning_code,
            )
            status = (
                SegmentStatus.ASR_PASSED.value
                if passed and merged_warning is None
                else SegmentStatus.WARNING.value
            )
            conn.execute(
                """
                UPDATE segments SET status=?,asr_text=?,asr_similarity=?,asr_wer=?,warning_code=?,updated_at=?
                WHERE id=?
                """,
                (status, transcript, similarity, wer, merged_warning, time.time(), segment_id),
            )

    def mark_verified(self, segment_id: int, warning_code: str | None = None) -> None:
        with self.transaction() as conn:
            existing = conn.execute(
                "SELECT chapter_id,warning_code FROM segments WHERE id=?", (segment_id,)
            ).fetchone()
            if existing is None:
                raise KeyError(f"Unknown segment id: {segment_id}")
            merged_warning = self._merge_warning_codes(
                str(existing["warning_code"]) if existing["warning_code"] else None,
                warning_code,
            )
            status = SegmentStatus.WARNING.value if merged_warning else SegmentStatus.VERIFIED.value
            conn.execute(
                "UPDATE segments SET status=?,warning_code=?,error=NULL,updated_at=? WHERE id=?",
                (status, merged_warning, time.time(), segment_id),
            )
            chapter_id = int(existing["chapter_id"])
            self._refresh_chapter_counts_conn(conn, chapter_id)

    def set_segment_warning_code(self, segment_id: int, warning_code: str) -> None:
        with self.transaction() as conn:
            row = conn.execute("SELECT warning_code FROM segments WHERE id=?", (segment_id,)).fetchone()
            if row is None:
                raise KeyError(f"Unknown segment id: {segment_id}")
            merged_warning = self._merge_warning_codes(
                str(row["warning_code"]) if row["warning_code"] else None,
                warning_code,
            )
            conn.execute(
                "UPDATE segments SET warning_code=?,updated_at=? WHERE id=?",
                (merged_warning, time.time(), segment_id),
            )

    def mark_failed(self, segment_id: int, error: str, warning_code: str = "SEGMENT_FAILED") -> None:
        with self.transaction() as conn:
            existing = conn.execute(
                "SELECT chapter_id,warning_code FROM segments WHERE id=?", (segment_id,)
            ).fetchone()
            if existing is None:
                raise KeyError(f"Unknown segment id: {segment_id}")
            merged_warning = self._merge_warning_codes(
                str(existing["warning_code"]) if existing["warning_code"] else None,
                warning_code,
            )
            conn.execute(
                "UPDATE segments SET status=?,warning_code=?,error=?,updated_at=? WHERE id=?",
                (SegmentStatus.FAILED.value, merged_warning, error[-8000:], time.time(), segment_id),
            )
            chapter_id = int(existing["chapter_id"])
            self._refresh_chapter_counts_conn(conn, chapter_id)

    def reset_segment_pending(self, segment_id: int, reason: str) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE segments SET status=?,wav_path=NULL,wav_sha256=NULL,wav_duration=NULL,
                    signal_json=NULL,asr_text=NULL,asr_similarity=NULL,asr_wer=NULL,
                    warning_code=NULL,generation_seed=NULL,error=?,updated_at=?
                WHERE id=?
                """,
                (SegmentStatus.PENDING.value, reason[-2000:], time.time(), segment_id),
            )
            row = conn.execute("SELECT chapter_id FROM segments WHERE id=?", (segment_id,)).fetchone()
            if row is not None:
                self._refresh_chapter_counts_conn(conn, int(row["chapter_id"]))

    def _refresh_chapter_counts_conn(self, conn: sqlite3.Connection, chapter_id: int) -> None:
        row = conn.execute(
            """
            SELECT
              SUM(CASE WHEN status='verified' THEN 1 ELSE 0 END) AS verified,
              SUM(CASE WHEN status='warning' THEN 1 ELSE 0 END) AS warnings,
              SUM(CASE WHEN status='failed' THEN 1 ELSE 0 END) AS failed
            FROM segments WHERE chapter_id=?
            """,
            (chapter_id,),
        ).fetchone()
        conn.execute(
            "UPDATE chapters SET verified_segments=?,warning_segments=?,failed_segments=? WHERE id=?",
            (int(row["verified"] or 0), int(row["warnings"] or 0), int(row["failed"] or 0), chapter_id),
        )

    def chapter_is_publishable(self, chapter_id: int) -> bool:
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT COUNT(*) AS total,
                       SUM(CASE WHEN status IN ('verified','warning') THEN 1 ELSE 0 END) AS accepted,
                       SUM(CASE WHEN status='failed' THEN 1 ELSE 0 END) AS failed
                FROM segments WHERE chapter_id=?
                """,
                (chapter_id,),
            ).fetchone()
            return bool(row and row["total"] and row["total"] == row["accepted"] and not row["failed"])

    def upsert_character(
        self,
        *,
        canonical_name: str,
        display_name: str,
        gender: str,
        age: str,
        personality: str,
        mentions: int,
        importance: str,
        confidence: float,
    ) -> int:
        now = time.time()
        with self.transaction() as conn:
            row = conn.execute(
                "SELECT id FROM characters WHERE canonical_name=?", (canonical_name,)
            ).fetchone()
            if row:
                character_id = int(row["id"])
                conn.execute(
                    """
                    UPDATE characters SET display_name=?,gender=?,age=?,personality=?,importance=?,
                        mention_count=?,confidence=?,updated_at=? WHERE id=?
                    """,
                    (
                        display_name,
                        gender,
                        age,
                        personality,
                        importance,
                        mentions,
                        confidence,
                        now,
                        character_id,
                    ),
                )
                return character_id
            cursor = conn.execute(
                """
                INSERT INTO characters(
                    canonical_name,display_name,gender,age,personality,importance,mention_count,
                    confidence,created_at,updated_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    canonical_name,
                    display_name,
                    gender,
                    age,
                    personality,
                    importance,
                    mentions,
                    confidence,
                    now,
                    now,
                ),
            )
            return int(cursor.lastrowid)

    def add_alias(self, character_id: int, alias: str, normalized_alias: str, confidence: float, source: str) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO character_aliases(character_id,alias,normalized_alias,confidence,source)
                VALUES(?,?,?,?,?)
                ON CONFLICT(normalized_alias) DO UPDATE SET
                    character_id=excluded.character_id,
                    alias=excluded.alias,
                    confidence=MAX(character_aliases.confidence, excluded.confidence),
                    source=excluded.source
                """,
                (character_id, alias, normalized_alias, confidence, source),
            )

    def list_characters(self) -> list[sqlite3.Row]:
        with self.connect() as conn:
            return list(conn.execute("SELECT * FROM characters ORDER BY importance,mention_count DESC"))

    def upsert_pronunciation(
        self,
        *,
        surface: str,
        normalized_surface: str,
        spoken_form: str,
        confidence: float,
        source: str = "analysis",
    ) -> None:
        now = time.time()
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO pronunciations(
                    surface,normalized_surface,spoken_form,confidence,source,created_at,updated_at
                ) VALUES(?,?,?,?,?,?,?)
                ON CONFLICT(normalized_surface) DO UPDATE SET
                    surface=CASE
                        WHEN excluded.confidence >= pronunciations.confidence THEN excluded.surface
                        ELSE pronunciations.surface
                    END,
                    spoken_form=CASE
                        WHEN pronunciations.locked=0 AND excluded.confidence >= pronunciations.confidence
                        THEN excluded.spoken_form ELSE pronunciations.spoken_form
                    END,
                    confidence=MAX(pronunciations.confidence, excluded.confidence),
                    source=CASE
                        WHEN pronunciations.locked=0 AND excluded.confidence >= pronunciations.confidence
                        THEN excluded.source ELSE pronunciations.source
                    END,
                    updated_at=excluded.updated_at
                """,
                (surface, normalized_surface, spoken_form, confidence, source, now, now),
            )

    def list_pronunciations(self, minimum_confidence: float = 0.0) -> list[sqlite3.Row]:
        with self.connect() as conn:
            return list(
                conn.execute(
                    """
                    SELECT * FROM pronunciations
                    WHERE locked=1 OR confidence>=?
                    ORDER BY LENGTH(surface) DESC, normalized_surface
                    """,
                    (minimum_confidence,),
                )
            )

    def get_character_by_name_or_alias(self, normalized_name: str) -> sqlite3.Row | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM characters WHERE canonical_name=?", (normalized_name,)
            ).fetchone()
            if row:
                return row
            return conn.execute(
                """
                SELECT c.* FROM character_aliases a JOIN characters c ON c.id=a.character_id
                WHERE a.normalized_alias=?
                """,
                (normalized_name,),
            ).fetchone()

    def upsert_voice_profile(self, data: dict[str, Any]) -> int:
        now = time.time()
        with self.transaction() as conn:
            row = conn.execute(
                "SELECT id FROM voice_profiles WHERE voice_key=?", (data["voice_key"],)
            ).fetchone()
            values = (
                data["engine"],
                data.get("preset_name"),
                data.get("description", ""),
                int(data.get("seed", 1)),
                data.get("reference_wav"),
                data.get("reference_sha256"),
                data.get("status", "planned"),
                now,
            )
            if row:
                profile_id = int(row["id"])
                existing = conn.execute(
                    "SELECT * FROM voice_profiles WHERE id=?", (profile_id,)
                ).fetchone()
                assert existing is not None
                identity_changed = bool(
                    existing["engine"] != data["engine"]
                    or existing["description"] != data.get("description", "")
                    or int(existing["seed"]) != int(data.get("seed", 1))
                )
                requested_preset = data.get("preset_name")
                preset_changed = bool(
                    requested_preset is not None
                    and str(existing["preset_name"] or "") != str(requested_preset)
                )
                if identity_changed or preset_changed:
                    raise RuntimeError(
                        f"Voice profile {data['voice_key']} is locked and cannot change during resume"
                    )
                # Preserve reference WAV, checksum and readiness. Rebuilding the registry on resume
                # must not erase an already committed voice reference.
                return profile_id
            cursor = conn.execute(
                """
                INSERT INTO voice_profiles(
                    voice_key,engine,preset_name,description,seed,reference_wav,reference_sha256,
                    status,created_at,updated_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?)
                """,
                (data["voice_key"], *values[:-1], now, now),
            )
            return int(cursor.lastrowid)

    def assign_voice_profile(self, segment_id: int, profile_id: int) -> None:
        with self.connect() as conn:
            conn.execute(
                "UPDATE segments SET voice_profile_id=?,updated_at=? WHERE id=?",
                (profile_id, time.time(), segment_id),
            )

    def list_voice_profiles(self) -> list[sqlite3.Row]:
        with self.connect() as conn:
            return list(conn.execute("SELECT * FROM voice_profiles ORDER BY id"))

    def update_voice_reference(
        self, profile_id: int, *, reference_wav: Path, reference_sha256: str, status: str = "ready"
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                "UPDATE voice_profiles SET reference_wav=?,reference_sha256=?,status=?,updated_at=? WHERE id=?",
                (str(reference_wav.resolve()), reference_sha256, status, time.time(), profile_id),
            )

    def invalidate_voice_reference(self, profile_id: int, reason: str) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE voice_profiles SET reference_wav=NULL,reference_sha256=NULL,
                    status='planned',updated_at=? WHERE id=?
                """,
                (time.time(), profile_id),
            )
            conn.execute(
                "INSERT INTO runtime_events(timestamp,level,code,message,details_json) VALUES(?,?,?,?,?)",
                (time.time(), "warning", "VOICE_REFERENCE_INVALIDATED", reason, None),
            )

    def lock_voice_preset(self, profile_id: int, preset_name: str) -> None:
        value = preset_name.strip()
        if not value:
            raise ValueError("A locked voice preset cannot be empty")
        with self.transaction() as conn:
            row = conn.execute(
                "SELECT preset_name FROM voice_profiles WHERE id=?", (profile_id,)
            ).fetchone()
            if row is None:
                raise KeyError(profile_id)
            existing = str(row["preset_name"] or "").strip()
            if existing and existing != value:
                raise RuntimeError(
                    f"Voice preset is locked to {existing!r} and cannot change to {value!r}"
                )
            if not existing:
                conn.execute(
                    "UPDATE voice_profiles SET preset_name=?,updated_at=? WHERE id=?",
                    (value, time.time(), profile_id),
                )

    def voice_profile(self, profile_id: int) -> sqlite3.Row:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM voice_profiles WHERE id=?", (profile_id,)).fetchone()
            if row is None:
                raise KeyError(profile_id)
            return row

    def event(self, level: str, code: str, message: str, details: dict[str, Any] | None = None) -> None:
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO runtime_events(timestamp,level,code,message,details_json) VALUES(?,?,?,?,?)",
                (time.time(), level, code, message, json.dumps(details, ensure_ascii=False) if details else None),
            )

    def list_events(self, level: str | None = None) -> list[sqlite3.Row]:
        with self.connect() as conn:
            if level is None:
                return list(conn.execute("SELECT * FROM runtime_events ORDER BY id"))
            return list(conn.execute("SELECT * FROM runtime_events WHERE level=? ORDER BY id", (level,)))

    def lease_worker(
        self,
        worker_name: str,
        pid: int,
        generation: int,
        state: str,
        current_item: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO worker_leases(worker_name,pid,generation,state,heartbeat_at,current_item,metadata_json)
                VALUES(?,?,?,?,?,?,?)
                ON CONFLICT(worker_name) DO UPDATE SET
                    pid=excluded.pid,generation=excluded.generation,state=excluded.state,
                    heartbeat_at=excluded.heartbeat_at,current_item=excluded.current_item,
                    metadata_json=excluded.metadata_json
                """,
                (
                    worker_name,
                    pid,
                    generation,
                    state,
                    time.time(),
                    current_item,
                    json.dumps(metadata, ensure_ascii=False) if metadata else None,
                ),
            )

    def clear_worker_lease(self, worker_name: str) -> None:
        with self.connect() as conn:
            conn.execute("DELETE FROM worker_leases WHERE worker_name=?", (worker_name,))

    def list_worker_leases(self) -> list[sqlite3.Row]:
        with self.connect() as conn:
            return list(conn.execute("SELECT * FROM worker_leases ORDER BY worker_name"))

    def reset_in_progress_segments(self, reason: str = "Interrupted before commit") -> int:
        with self.connect() as conn:
            chapter_ids = [
                int(row[0])
                for row in conn.execute(
                    "SELECT DISTINCT chapter_id FROM segments WHERE status IN ('generating','asr_passed')"
                )
            ]
            cursor = conn.execute(
                """
                UPDATE segments SET status='pending',wav_path=NULL,wav_sha256=NULL,wav_duration=NULL,
                    signal_json=NULL,asr_text=NULL,asr_similarity=NULL,asr_wer=NULL,
                    warning_code=NULL,generation_seed=NULL,error=?,updated_at=?
                WHERE status='generating'
                """,
                (reason, time.time()),
            )
            # If the process died between ASR pass and the final verified commit, keep the WAV
            # but rerun ASR rather than trusting an incomplete transaction boundary.
            conn.execute(
                "UPDATE segments SET status='signal_passed',updated_at=? WHERE status='asr_passed'",
                (time.time(),),
            )
            for chapter_id in chapter_ids:
                self._refresh_chapter_counts_conn(conn, chapter_id)
            return int(cursor.rowcount)

    def list_artifacts(self) -> list[sqlite3.Row]:
        with self.connect() as conn:
            return list(conn.execute("SELECT * FROM artifacts ORDER BY id"))

    def artifact_by_key(self, artifact_key: str) -> sqlite3.Row | None:
        with self.connect() as conn:
            return conn.execute(
                "SELECT * FROM artifacts WHERE artifact_key=?", (artifact_key,)
            ).fetchone()

    def clear_all_worker_leases(self) -> int:
        with self.connect() as conn:
            cursor = conn.execute("DELETE FROM worker_leases")
            return int(cursor.rowcount)

    def register_artifact(
        self,
        *,
        artifact_key: str,
        kind: str,
        path: Path,
        sha256: str | None,
        verified: bool,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        now = time.time()
        size = path.stat().st_size if path.exists() else None
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO artifacts(
                    artifact_key,kind,path,sha256,size_bytes,verified,metadata_json,created_at,updated_at
                ) VALUES(?,?,?,?,?,?,?,?,?)
                ON CONFLICT(artifact_key) DO UPDATE SET
                    path=excluded.path,sha256=excluded.sha256,size_bytes=excluded.size_bytes,
                    verified=excluded.verified,metadata_json=excluded.metadata_json,updated_at=excluded.updated_at
                """,
                (
                    artifact_key,
                    kind,
                    str(path.resolve()),
                    sha256,
                    size,
                    1 if verified else 0,
                    json.dumps(metadata, ensure_ascii=False) if metadata else None,
                    now,
                    now,
                ),
            )

    def rewrite_speaker(self, old_name: str, canonical_name: str) -> int:
        with self.connect() as conn:
            cursor = conn.execute(
                "UPDATE segments SET speaker=?,updated_at=? WHERE speaker=?",
                (canonical_name, time.time(), old_name),
            )
            return int(cursor.rowcount)

    def set_character_for_speaker(self, speaker: str, character_id: int) -> int:
        with self.connect() as conn:
            cursor = conn.execute(
                "UPDATE segments SET canonical_character_id=?,updated_at=? WHERE speaker=?",
                (character_id, time.time(), speaker),
            )
            return int(cursor.rowcount)

    def set_voice_for_character_segments(self, character_id: int, profile_id: int) -> int:
        with self.connect() as conn:
            cursor = conn.execute(
                "UPDATE segments SET voice_profile_id=?,updated_at=? WHERE canonical_character_id=?",
                (profile_id, time.time(), character_id),
            )
            return int(cursor.rowcount)

    def integrity_check(self) -> list[str]:
        errors: list[str] = []
        with self.connect() as conn:
            result = conn.execute("PRAGMA integrity_check").fetchall()
            for row in result:
                if str(row[0]).lower() != "ok":
                    errors.append(str(row[0]))
            fk = conn.execute("PRAGMA foreign_key_check").fetchall()
            errors.extend(f"foreign_key_check: {tuple(row)}" for row in fk)
        return errors
