from __future__ import annotations

import json
import os
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Sequence

from .models import BookStatus, ChapterStatus, SegmentStatus


# Version 1 is the legacy pre-QA layout. Existing projects did not persist a
# user_version, so they migrate from 0 directly to this version 2 schema.
SCHEMA_VERSION = 2
QUALITY_SCOPE_SEGMENT = "segment"
QUALITY_SCOPE_CHAPTER = "chapter"
QUALITY_SCOPES = {QUALITY_SCOPE_SEGMENT, QUALITY_SCOPE_CHAPTER}
SEGMENT_AUDIO_QUALITY_STAGE = "segment_audio_v1"
CHAPTER_POST_ENCODE_QUALITY_STAGE = "chapter_post_encode_v1"
QUALITY_VERDICT_PASS = "pass"
QUALITY_VERDICTS = {
    QUALITY_VERDICT_PASS,
    "repair",
    "inconclusive",
    "fail",
}


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
    casting_finalized INTEGER NOT NULL DEFAULT 0
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
    pitch_semitones INTEGER NOT NULL DEFAULT 0,
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

CREATE TABLE IF NOT EXISTS quality_policies (
    policy_hash TEXT PRIMARY KEY,
    policy_version INTEGER NOT NULL,
    policy_json TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 0 CHECK (active IN (0, 1)),
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS quality_checks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scope TEXT NOT NULL CHECK (scope IN ('segment', 'chapter')),
    stage TEXT NOT NULL,
    segment_id INTEGER REFERENCES segments(id) ON DELETE CASCADE,
    chapter_id INTEGER REFERENCES chapters(id) ON DELETE CASCADE,
    artifact_sha256 TEXT NOT NULL,
    policy_hash TEXT NOT NULL REFERENCES quality_policies(policy_hash),
    policy_version INTEGER NOT NULL,
    verdict TEXT NOT NULL CHECK (verdict IN ('pass', 'repair', 'inconclusive', 'fail')),
    metrics_json TEXT NOT NULL DEFAULT '{}',
    failure_codes_json TEXT NOT NULL DEFAULT '[]',
    repair_action TEXT,
    attempt INTEGER NOT NULL DEFAULT 1 CHECK (attempt >= 1),
    created_at REAL NOT NULL,
    CHECK (
        (scope = 'segment' AND segment_id IS NOT NULL AND chapter_id IS NULL)
        OR (scope = 'chapter' AND chapter_id IS NOT NULL AND segment_id IS NULL)
    )
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
CREATE UNIQUE INDEX IF NOT EXISTS idx_quality_policies_active
    ON quality_policies(active) WHERE active = 1;
CREATE INDEX IF NOT EXISTS idx_quality_checks_segment
    ON quality_checks(segment_id, stage, policy_hash, id);
CREATE INDEX IF NOT EXISTS idx_quality_checks_chapter
    ON quality_checks(chapter_id, stage, policy_hash, id);
"""


class ProjectDB:
    def __init__(self, path: Path, synchronous: str = "FULL") -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.synchronous = synchronous.upper()
        if self.synchronous not in {"OFF", "NORMAL", "FULL", "EXTRA"}:
            raise ValueError(f"Unsupported SQLite synchronous mode: {synchronous}")
        with self.connect() as conn:
            schema_version = int(conn.execute("PRAGMA user_version").fetchone()[0])
            if schema_version > SCHEMA_VERSION:
                raise RuntimeError(
                    f"Project schema version {schema_version} is newer than supported version "
                    f"{SCHEMA_VERSION}"
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
            if has_user_tables and schema_version < SCHEMA_VERSION:
                self._create_migration_backup(conn, schema_version)
            conn.executescript(SCHEMA)
            conn.execute("BEGIN IMMEDIATE")
            try:
                self._migrate_schema(conn)
                conn.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
                conn.execute("COMMIT")
            except Exception:
                conn.execute("ROLLBACK")
                raise

    def _migration_backup_path(self, source_version: int) -> Path:
        return self.path.with_name(
            f"{self.path.name}.pre-v{source_version}-to-v{SCHEMA_VERSION}.bak"
        )

    def _create_migration_backup(
        self,
        conn: sqlite3.Connection,
        source_version: int,
    ) -> Path:
        backup_path = self._migration_backup_path(source_version)
        if backup_path.exists():
            return backup_path
        temp = backup_path.with_name(backup_path.name + ".part")
        temp.unlink(missing_ok=True)
        try:
            backup = sqlite3.connect(temp)
            try:
                conn.backup(backup)
                result = backup.execute("PRAGMA integrity_check").fetchone()
                if result is None or str(result[0]).casefold() != "ok":
                    raise RuntimeError("SQLite migration backup failed integrity_check")
            finally:
                backup.close()
            os.replace(temp, backup_path)
            return backup_path
        finally:
            temp.unlink(missing_ok=True)

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
        if error is not None or status == BookStatus.COMPLETED.value:
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

    def chapter_progress_counts(self) -> dict[int, dict[str, int]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT chapter_id,
                    SUM(CASE WHEN status <> 'pending' OR voice_profile_id IS NOT NULL THEN 1 ELSE 0 END)
                        AS analyzed,
                    SUM(CASE WHEN wav_path IS NOT NULL THEN 1 ELSE 0 END) AS audio
                FROM segments
                GROUP BY chapter_id
                """
            )
            return {
                int(row["chapter_id"]): {
                    "analysis": int(row["analyzed"] or 0),
                    "audio": int(row["audio"] or 0),
                }
                for row in rows
            }

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

    @staticmethod
    def _without_audio_attempt_warnings(existing: str | None) -> str | None:
        values = []
        for value in str(existing or "").split("|"):
            if not value:
                continue
            if value == "SEGMENT_FAILED" or value == "NON_SPEAKABLE_SEGMENT":
                continue
            if value.startswith("TTS_") or value.startswith("ASR_"):
                continue
            values.append(value)
        return "|".join(values) or None

    @staticmethod
    def _without_asr_warnings(existing: str | None) -> str | None:
        values = [
            value
            for value in str(existing or "").split("|")
            if value and not value.startswith("ASR_")
        ]
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

    def mark_generating(self, segment_id: int, seed: int) -> None:
        with self.transaction() as conn:
            row = conn.execute(
                "SELECT chapter_id,warning_code FROM segments WHERE id=?", (segment_id,)
            ).fetchone()
            if row is None:
                raise KeyError(f"Unknown segment id: {segment_id}")
            retained_warning = self._without_audio_attempt_warnings(
                str(row["warning_code"]) if row["warning_code"] else None
            )
            conn.execute(
                """
                UPDATE segments SET status=?,attempt_count=attempt_count+1,generation_seed=?,
                    asr_text=NULL,asr_similarity=NULL,asr_wer=NULL,
                    warning_code=?,error=NULL,updated_at=? WHERE id=?
                """,
                (
                    SegmentStatus.GENERATING.value,
                    seed,
                    retained_warning,
                    time.time(),
                    segment_id,
                ),
            )
            self._refresh_chapter_counts_conn(conn, int(row["chapter_id"]))

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
                UPDATE segments SET status=(
                        CASE WHEN voice_profile_id IS NOT NULL AND kind IS NOT NULL AND speaker IS NOT NULL
                            THEN ? ELSE ? END
                    ),wav_path=NULL,wav_sha256=NULL,wav_duration=NULL,
                    signal_json=NULL,asr_text=NULL,asr_similarity=NULL,asr_wer=NULL,
                    warning_code=NULL,generation_seed=NULL,error=?,updated_at=?
                WHERE id=?
                """,
                (
                    SegmentStatus.ANALYZED.value,
                    SegmentStatus.PENDING.value,
                    reason[-2000:],
                    time.time(),
                    segment_id,
                ),
            )
            row = conn.execute("SELECT chapter_id FROM segments WHERE id=?", (segment_id,)).fetchone()
            if row is not None:
                self._refresh_chapter_counts_conn(conn, int(row["chapter_id"]))

    def requeue_segment_for_asr(self, segment_id: int, reason: str) -> None:
        with self.transaction() as conn:
            row = conn.execute(
                """
                SELECT chapter_id,status,wav_path,wav_sha256,wav_duration,
                       signal_json,warning_code
                FROM segments WHERE id=?
                """,
                (segment_id,),
            ).fetchone()
            if row is None:
                raise KeyError(f"Unknown segment id: {segment_id}")
            if str(row["status"]) not in {
                SegmentStatus.VERIFIED.value,
                SegmentStatus.WARNING.value,
            }:
                raise RuntimeError("ASR-only requeue requires a verified or warning segment")
            if (
                not str(row["wav_path"] or "").strip()
                or not str(row["wav_sha256"] or "").strip()
                or row["wav_duration"] is None
                or row["signal_json"] is None
            ):
                raise RuntimeError("ASR-only requeue requires a committed signal-validated WAV")
            retained_warning = self._without_asr_warnings(
                str(row["warning_code"]) if row["warning_code"] else None
            )
            conn.execute(
                """
                UPDATE segments SET status=?,asr_text=NULL,asr_similarity=NULL,asr_wer=NULL,
                    warning_code=?,error=?,updated_at=?
                WHERE id=?
                """,
                (
                    SegmentStatus.SIGNAL_PASSED.value,
                    retained_warning,
                    str(reason)[-2000:],
                    time.time(),
                    segment_id,
                ),
            )
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
        locked: bool = False,
    ) -> None:
        now = time.time()
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO pronunciations(
                    surface,normalized_surface,spoken_form,confidence,source,locked,created_at,updated_at
                ) VALUES(?,?,?,?,?,?,?,?)
                ON CONFLICT(normalized_surface) DO UPDATE SET
                    surface=CASE
                        WHEN pronunciations.locked=0
                             AND (excluded.locked=1 OR excluded.confidence >= pronunciations.confidence)
                        THEN excluded.surface
                        ELSE pronunciations.surface
                    END,
                    spoken_form=CASE
                        WHEN pronunciations.locked=0
                             AND (excluded.locked=1 OR excluded.confidence >= pronunciations.confidence)
                        THEN excluded.spoken_form ELSE pronunciations.spoken_form
                    END,
                    confidence=MAX(pronunciations.confidence, excluded.confidence),
                    source=CASE
                        WHEN pronunciations.locked=0
                             AND (excluded.locked=1 OR excluded.confidence >= pronunciations.confidence)
                        THEN excluded.source ELSE pronunciations.source
                    END,
                    locked=MAX(pronunciations.locked, excluded.locked),
                    updated_at=excluded.updated_at
                """,
                (surface, normalized_surface, spoken_form, confidence, source, int(locked), now, now),
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
                int(data.get("pitch_semitones", 0)),
                data.get("status", "planned"),
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
                    or int(existing["pitch_semitones"]) != int(data.get("pitch_semitones", 0))
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
                return profile_id
            cursor = conn.execute(
                """
                INSERT INTO voice_profiles(
                    voice_key,engine,preset_name,description,seed,pitch_semitones,status,created_at,updated_at
                ) VALUES(?,?,?,?,?,?,?,?,?)
                """,
                (data["voice_key"], *values, now, now),
            )
            return int(cursor.lastrowid)

    def list_voice_profiles(self) -> list[sqlite3.Row]:
        with self.connect() as conn:
            return list(conn.execute("SELECT * FROM voice_profiles ORDER BY id"))

    def voice_profile(self, profile_id: int) -> sqlite3.Row:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM voice_profiles WHERE id=?", (profile_id,)).fetchone()
            if row is None:
                raise KeyError(profile_id)
            return row

    def voice_profile_by_key(self, voice_key: str) -> sqlite3.Row:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM voice_profiles WHERE voice_key=?",
                (voice_key,),
            ).fetchone()
            if row is None:
                raise KeyError(voice_key)
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
                UPDATE segments SET status=(
                        CASE WHEN voice_profile_id IS NOT NULL AND kind IS NOT NULL AND speaker IS NOT NULL
                            THEN 'analyzed' ELSE 'pending' END
                    ),wav_path=NULL,wav_sha256=NULL,wav_duration=NULL,
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

    def artifact_by_key(self, artifact_key: str) -> sqlite3.Row | None:
        with self.connect() as conn:
            return conn.execute(
                "SELECT * FROM artifacts WHERE artifact_key=?", (artifact_key,)
            ).fetchone()

    def set_current_quality_policy(
        self,
        *,
        policy_hash: str,
        policy_version: int,
        policy: dict[str, Any],
    ) -> None:
        normalized_hash = str(policy_hash).strip()
        normalized_version = int(policy_version)
        if not normalized_hash:
            raise ValueError("quality policy hash must not be empty")
        if normalized_version < 1:
            raise ValueError("quality policy version must be positive")
        payload = json.dumps(
            policy,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        now = time.time()
        with self.transaction() as conn:
            existing = conn.execute(
                "SELECT policy_version,policy_json FROM quality_policies WHERE policy_hash=?",
                (normalized_hash,),
            ).fetchone()
            if existing is not None and (
                int(existing["policy_version"]) != normalized_version
                or str(existing["policy_json"]) != payload
            ):
                raise ValueError("quality policy hash is already registered with different content")
            conn.execute("UPDATE quality_policies SET active=0,updated_at=? WHERE active=1", (now,))
            conn.execute(
                """
                INSERT INTO quality_policies(
                    policy_hash,policy_version,policy_json,active,created_at,updated_at
                ) VALUES(?,?,?,?,?,?)
                ON CONFLICT(policy_hash) DO UPDATE SET
                    policy_version=excluded.policy_version,
                    policy_json=excluded.policy_json,
                    active=1,
                    updated_at=excluded.updated_at
                """,
                (
                    normalized_hash,
                    normalized_version,
                    payload,
                    1,
                    now,
                    now,
                ),
            )

    def current_quality_policy(self) -> sqlite3.Row | None:
        with self.connect() as conn:
            return conn.execute(
                "SELECT * FROM quality_policies WHERE active=1"
            ).fetchone()

    def quality_metadata_for_current_policy(
        self,
        verdict: str = QUALITY_VERDICT_PASS,
    ) -> dict[str, Any]:
        normalized_verdict = str(verdict).strip().casefold()
        if normalized_verdict not in QUALITY_VERDICTS:
            raise ValueError(f"Unsupported quality verdict: {verdict}")
        policy = self.current_quality_policy()
        if policy is None:
            raise RuntimeError("No active quality policy is locked for this project")
        return {
            "policy_hash": str(policy["policy_hash"]),
            "policy_version": int(policy["policy_version"]),
            "verdict": normalized_verdict,
        }

    def record_quality_check(
        self,
        *,
        scope: str,
        stage: str,
        artifact_sha256: str,
        policy_hash: str,
        policy_version: int,
        verdict: str,
        segment_id: int | None = None,
        chapter_id: int | None = None,
        metrics: dict[str, Any] | None = None,
        failure_codes: Sequence[str] = (),
        repair_action: str | None = None,
        attempt: int = 1,
    ) -> int:
        normalized_scope = str(scope).strip().casefold()
        normalized_stage = str(stage).strip()
        normalized_hash = str(policy_hash).strip()
        normalized_verdict = str(verdict).strip().casefold()
        normalized_version = int(policy_version)
        normalized_attempt = int(attempt)
        if normalized_scope not in QUALITY_SCOPES:
            raise ValueError(f"Unsupported quality scope: {scope}")
        if not normalized_stage:
            raise ValueError("quality check stage must not be empty")
        if not str(artifact_sha256).strip():
            raise ValueError("quality check artifact checksum must not be empty")
        if normalized_verdict not in QUALITY_VERDICTS:
            raise ValueError(f"Unsupported quality verdict: {verdict}")
        if normalized_version < 1 or normalized_attempt < 1:
            raise ValueError("quality policy version and attempt must be positive")
        if normalized_scope == QUALITY_SCOPE_SEGMENT:
            if segment_id is None or chapter_id is not None:
                raise ValueError("segment quality checks require only segment_id")
        elif chapter_id is None or segment_id is not None:
            raise ValueError("chapter quality checks require only chapter_id")

        with self.transaction() as conn:
            policy = conn.execute(
                "SELECT policy_version FROM quality_policies WHERE policy_hash=?",
                (normalized_hash,),
            ).fetchone()
            if policy is None or int(policy["policy_version"]) != normalized_version:
                raise ValueError("quality check policy hash/version is not registered")
            cursor = conn.execute(
                """
                INSERT INTO quality_checks(
                    scope,stage,segment_id,chapter_id,artifact_sha256,
                    policy_hash,policy_version,verdict,metrics_json,
                    failure_codes_json,repair_action,attempt,created_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    normalized_scope,
                    normalized_stage,
                    segment_id,
                    chapter_id,
                    str(artifact_sha256).strip(),
                    normalized_hash,
                    normalized_version,
                    normalized_verdict,
                    json.dumps(metrics or {}, ensure_ascii=False, sort_keys=True),
                    json.dumps(list(failure_codes), ensure_ascii=False),
                    repair_action,
                    normalized_attempt,
                    time.time(),
                ),
            )
            return int(cursor.lastrowid)

    def latest_quality_check(
        self,
        *,
        scope: str,
        stage: str,
        segment_id: int | None = None,
        chapter_id: int | None = None,
        current_policy_only: bool = True,
    ) -> sqlite3.Row | None:
        normalized_scope = str(scope).strip().casefold()
        if normalized_scope not in QUALITY_SCOPES:
            raise ValueError(f"Unsupported quality scope: {scope}")
        if normalized_scope == QUALITY_SCOPE_SEGMENT:
            if segment_id is None or chapter_id is not None:
                raise ValueError("segment quality lookup requires only segment_id")
            subject_clause = "quality_checks.segment_id=?"
            subject_id = int(segment_id)
        else:
            if chapter_id is None or segment_id is not None:
                raise ValueError("chapter quality lookup requires only chapter_id")
            subject_clause = "quality_checks.chapter_id=?"
            subject_id = int(chapter_id)
        policy_clause = " AND quality_policies.active=1" if current_policy_only else ""
        with self.connect() as conn:
            return conn.execute(
                f"""
                SELECT quality_checks.*
                FROM quality_checks
                JOIN quality_policies USING(policy_hash)
                WHERE quality_checks.scope=?
                  AND quality_checks.stage=?
                  AND {subject_clause}
                  {policy_clause}
                ORDER BY quality_checks.id DESC
                LIMIT 1
                """,
                (normalized_scope, str(stage).strip(), subject_id),
            ).fetchone()

    @staticmethod
    def _quality_check_is_current_pass_conn(
        conn: sqlite3.Connection,
        *,
        scope: str,
        stage: str,
        artifact_sha256: str,
        segment_id: int | None = None,
        chapter_id: int | None = None,
    ) -> bool:
        if scope == QUALITY_SCOPE_SEGMENT:
            subject_clause = "quality_checks.segment_id=?"
            subject_id = segment_id
        else:
            subject_clause = "quality_checks.chapter_id=?"
            subject_id = chapter_id
        if subject_id is None:
            return False
        row = conn.execute(
            f"""
            SELECT quality_checks.verdict
            FROM quality_checks
            JOIN quality_policies
              ON quality_policies.policy_hash=quality_checks.policy_hash
             AND quality_policies.policy_version=quality_checks.policy_version
            WHERE quality_policies.active=1
              AND quality_checks.scope=?
              AND quality_checks.stage=?
              AND quality_checks.artifact_sha256=?
              AND {subject_clause}
            ORDER BY quality_checks.id DESC
            LIMIT 1
            """,
            (scope, stage, artifact_sha256, int(subject_id)),
        ).fetchone()
        return bool(row and str(row["verdict"]) == QUALITY_VERDICT_PASS)

    def segment_audio_is_current_qa_verified(
        self,
        segment_id: int,
        artifact_sha256: str,
        stage: str = SEGMENT_AUDIO_QUALITY_STAGE,
    ) -> bool:
        normalized_sha256 = str(artifact_sha256).strip()
        normalized_stage = str(stage).strip()
        if not normalized_sha256 or not normalized_stage:
            return False
        with self.connect() as conn:
            segment = conn.execute(
                "SELECT wav_sha256 FROM segments WHERE id=?",
                (int(segment_id),),
            ).fetchone()
            if segment is None or str(segment["wav_sha256"] or "") != normalized_sha256:
                return False
            return self._quality_check_is_current_pass_conn(
                conn,
                scope=QUALITY_SCOPE_SEGMENT,
                stage=normalized_stage,
                artifact_sha256=normalized_sha256,
                segment_id=int(segment_id),
            )

    def chapter_segments_have_current_audio_qa(
        self,
        chapter_id: int,
        stage: str = SEGMENT_AUDIO_QUALITY_STAGE,
    ) -> bool:
        normalized_stage = str(stage).strip()
        if not normalized_stage:
            return False
        with self.connect() as conn:
            rows = list(
                conn.execute(
                    "SELECT id,status,wav_sha256 FROM segments WHERE chapter_id=? ORDER BY seq",
                    (int(chapter_id),),
                )
            )
            if not rows:
                return False
            for row in rows:
                if str(row["status"]) not in {
                    SegmentStatus.VERIFIED.value,
                    SegmentStatus.WARNING.value,
                }:
                    return False
                artifact_sha256 = str(row["wav_sha256"] or "").strip()
                if not artifact_sha256 or not self._quality_check_is_current_pass_conn(
                    conn,
                    scope=QUALITY_SCOPE_SEGMENT,
                    stage=normalized_stage,
                    artifact_sha256=artifact_sha256,
                    segment_id=int(row["id"]),
                ):
                    return False
            return True

    def chapter_artifact_is_current_qa_verified(
        self,
        chapter_index: int,
        stage: str = CHAPTER_POST_ENCODE_QUALITY_STAGE,
    ) -> bool:
        artifact_key = f"chapter_mp3:{int(chapter_index)}"
        normalized_stage = str(stage).strip()
        if not normalized_stage:
            return False
        with self.connect() as conn:
            artifact = conn.execute(
                "SELECT * FROM artifacts WHERE artifact_key=?",
                (artifact_key,),
            ).fetchone()
            chapter = conn.execute(
                "SELECT id FROM chapters WHERE chapter_index=?",
                (int(chapter_index),),
            ).fetchone()
            policy = conn.execute(
                "SELECT * FROM quality_policies WHERE active=1"
            ).fetchone()
            if (
                artifact is None
                or chapter is None
                or policy is None
                or str(artifact["kind"]) != "chapter_mp3"
                or not bool(artifact["verified"])
                or not str(artifact["sha256"] or "").strip()
            ):
                return False
            try:
                metadata = json.loads(str(artifact["metadata_json"] or "{}"))
                quality = metadata.get("quality") if isinstance(metadata, dict) else None
                metadata_passes = bool(
                    isinstance(quality, dict)
                    and str(quality.get("policy_hash", "")) == str(policy["policy_hash"])
                    and int(quality.get("policy_version", -1)) == int(policy["policy_version"])
                    and str(quality.get("verdict", "")).casefold() == QUALITY_VERDICT_PASS
                )
            except (TypeError, ValueError, json.JSONDecodeError):
                return False
            return bool(
                metadata_passes
                and self._quality_check_is_current_pass_conn(
                    conn,
                    scope=QUALITY_SCOPE_CHAPTER,
                    stage=normalized_stage,
                    artifact_sha256=str(artifact["sha256"]),
                    chapter_id=int(chapter["id"]),
                )
            )

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

    def rewrite_segment_speakers(
        self,
        segment_ids: list[int],
        *,
        speaker: str,
        gender: str,
        age: str,
        analysis_notes: str,
    ) -> int:
        if not segment_ids:
            return 0
        placeholders = ",".join("?" for _segment_id in segment_ids)
        with self.connect() as conn:
            cursor = conn.execute(
                f"""
                UPDATE segments SET speaker=?,gender=?,age=?,analysis_notes=?,
                    canonical_character_id=NULL,voice_profile_id=NULL,updated_at=?
                WHERE id IN ({placeholders})
                """,
                (
                    speaker,
                    gender,
                    age,
                    analysis_notes[:500],
                    time.time(),
                    *segment_ids,
                ),
            )
            return int(cursor.rowcount)

    def normalize_thought_speakers(self) -> int:
        with self.connect() as conn:
            cursor = conn.execute(
                """
                UPDATE segments SET speaker='NARRATOR',gender='unknown',age='unknown',
                    canonical_character_id=NULL,voice_profile_id=NULL,updated_at=?
                WHERE kind='thought' AND (
                    speaker!='NARRATOR' OR gender!='unknown' OR age!='unknown'
                    OR canonical_character_id IS NOT NULL OR voice_profile_id IS NOT NULL
                )
                """,
                (time.time(),),
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

    def set_character_and_voice_for_segments(
        self,
        segment_ids: list[int],
        character_id: int,
        profile_id: int,
    ) -> int:
        updated = 0
        now = time.time()
        with self.transaction() as conn:
            for offset in range(0, len(segment_ids), 500):
                batch = segment_ids[offset : offset + 500]
                if not batch:
                    continue
                placeholders = ",".join("?" for _ in batch)
                cursor = conn.execute(
                    f"""
                    UPDATE segments SET canonical_character_id=?,voice_profile_id=?,updated_at=?
                    WHERE id IN ({placeholders})
                    """,
                    (character_id, profile_id, now, *batch),
                )
                updated += int(cursor.rowcount)
        return updated

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
