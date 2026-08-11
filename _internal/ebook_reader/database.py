from __future__ import annotations

import json
import math
import os
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Sequence

from .io_utils import sha256_file
from .models import BookStatus, ChapterStatus, SegmentStatus


# Version 1 is the legacy pre-QA layout. Existing projects did not persist a
# user_version, so they migrate from 0 through the current schema.
SCHEMA_VERSION = 5
QUALITY_SCOPE_SEGMENT = "segment"
QUALITY_SCOPE_CHAPTER = "chapter"
QUALITY_SCOPES = {QUALITY_SCOPE_SEGMENT, QUALITY_SCOPE_CHAPTER}
SEGMENT_AUDIO_QUALITY_STAGE = "segment_audio_v1"
SEGMENT_ASR_DECODE_QUALITY_STAGE = "segment_asr_decode_v1"
SEGMENT_PERCEPTUAL_QUALITY_STAGE = "segment_perceptual_v1"
CHAPTER_POST_ENCODE_QUALITY_STAGE = "chapter_post_encode_v1"
GENERATION_DELIVERY_PRIMARY = "primary"
GENERATION_DELIVERY_CLARITY = "clarity"
GENERATION_DELIVERY_MODES = frozenset(
    {GENERATION_DELIVERY_PRIMARY, GENERATION_DELIVERY_CLARITY}
)
QUALITY_VERDICT_PASS = "pass"
QUALITY_VERDICTS = {
    QUALITY_VERDICT_PASS,
    "repair",
    "inconclusive",
    "fail",
}
SEGMENT_CANDIDATE_GENERATING = "generating"
SEGMENT_CANDIDATE_SIGNAL_PASSED = "signal_passed"
SEGMENT_CANDIDATE_BEAM_RECORDED = "beam_recorded"
SEGMENT_CANDIDATE_DUAL_FAILED = "dual_failed"
SEGMENT_CANDIDATE_DUAL_PASSED = "dual_passed"
SEGMENT_CANDIDATE_TTS_FAILED = "tts_failed"
SEGMENT_CANDIDATE_INVALID = "invalid"
SEGMENT_CANDIDATE_PROMOTED = "promoted"
SEGMENT_CANDIDATE_STATES = frozenset(
    {
        SEGMENT_CANDIDATE_GENERATING,
        SEGMENT_CANDIDATE_SIGNAL_PASSED,
        SEGMENT_CANDIDATE_BEAM_RECORDED,
        SEGMENT_CANDIDATE_DUAL_FAILED,
        SEGMENT_CANDIDATE_DUAL_PASSED,
        SEGMENT_CANDIDATE_TTS_FAILED,
        SEGMENT_CANDIDATE_INVALID,
        SEGMENT_CANDIDATE_PROMOTED,
    }
)
SEGMENT_CANDIDATE_FAILURE_STATES = frozenset(
    {
        SEGMENT_CANDIDATE_DUAL_FAILED,
        SEGMENT_CANDIDATE_TTS_FAILED,
        SEGMENT_CANDIDATE_INVALID,
    }
)
SEGMENT_CANDIDATE_EXHAUSTION_ACTION = "candidate_repair_exhausted"


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
    generation_frame_cap INTEGER CHECK(
        generation_frame_cap IS NULL OR generation_frame_cap > 0
    ),
    generation_delivery_mode TEXT NOT NULL DEFAULT 'primary' CHECK(
        generation_delivery_mode IN ('primary','clarity')
    ),
    generation_repair_round INTEGER CHECK(
        generation_repair_round IS NULL OR generation_repair_round >= 0
    ),
    generation_policy_hash TEXT,
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

CREATE TABLE IF NOT EXISTS segment_candidates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    segment_id INTEGER NOT NULL REFERENCES segments(id) ON DELETE CASCADE,
    policy_hash TEXT NOT NULL REFERENCES quality_policies(policy_hash),
    repair_round INTEGER NOT NULL CHECK (repair_round >= 0),
    incumbent_sha256 TEXT NOT NULL,
    expected_voice_profile_id INTEGER NOT NULL REFERENCES voice_profiles(id),
    expected_pitch_semitones INTEGER NOT NULL,
    state TEXT NOT NULL CHECK (
        state IN (
            'generating','signal_passed','beam_recorded','dual_failed',
            'dual_passed','tts_failed','invalid','promoted'
        )
    ),
    tts_attempt INTEGER NOT NULL DEFAULT 0 CHECK (tts_attempt >= 0),
    generation_seed INTEGER NOT NULL,
    wav_path TEXT NOT NULL UNIQUE,
    wav_sha256 TEXT,
    wav_duration REAL CHECK (wav_duration IS NULL OR wav_duration > 0),
    signal_json TEXT,
    beam_result_json TEXT,
    greedy_result_json TEXT,
    beam_check_id INTEGER REFERENCES quality_checks(id),
    greedy_check_id INTEGER REFERENCES quality_checks(id),
    final_check_id INTEGER REFERENCES quality_checks(id),
    failure_reason TEXT,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    promoted_at REAL,
    UNIQUE(segment_id, policy_hash, repair_round),
    CHECK (
        state IN ('generating','tts_failed')
        OR (
            wav_sha256 IS NOT NULL
            AND wav_duration IS NOT NULL
            AND signal_json IS NOT NULL
        )
    ),
    CHECK (
        (beam_check_id IS NULL AND beam_result_json IS NULL)
        OR (beam_check_id IS NOT NULL AND beam_result_json IS NOT NULL)
    ),
    CHECK (
        (greedy_check_id IS NULL AND greedy_result_json IS NULL)
        OR (greedy_check_id IS NOT NULL AND greedy_result_json IS NOT NULL)
    ),
    CHECK (
        state NOT IN ('beam_recorded','dual_failed','dual_passed','promoted')
        OR beam_check_id IS NOT NULL
    ),
    CHECK (
        state NOT IN ('dual_failed','dual_passed','promoted')
        OR greedy_check_id IS NOT NULL
    ),
    CHECK (
        (state = 'promoted' AND promoted_at IS NOT NULL AND final_check_id IS NOT NULL)
        OR (state <> 'promoted' AND promoted_at IS NULL)
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
CREATE INDEX IF NOT EXISTS idx_segment_candidates_resume
    ON segment_candidates(segment_id, policy_hash, state, repair_round);
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
        if "generation_frame_cap" not in segment_columns:
            conn.execute(
                """
                ALTER TABLE segments ADD COLUMN generation_frame_cap INTEGER
                CHECK(generation_frame_cap IS NULL OR generation_frame_cap > 0)
                """
            )
        if "generation_delivery_mode" not in segment_columns:
            conn.execute(
                """
                ALTER TABLE segments ADD COLUMN generation_delivery_mode TEXT
                NOT NULL DEFAULT 'primary'
                CHECK(generation_delivery_mode IN ('primary','clarity'))
                """
            )
        if "generation_repair_round" not in segment_columns:
            conn.execute(
                """
                ALTER TABLE segments ADD COLUMN generation_repair_round INTEGER
                CHECK(generation_repair_round IS NULL OR generation_repair_round >= 0)
                """
            )
        if "generation_policy_hash" not in segment_columns:
            conn.execute("ALTER TABLE segments ADD COLUMN generation_policy_hash TEXT")

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

        candidate_columns = {
            str(row[1]) for row in conn.execute("PRAGMA table_info(segment_candidates)")
        }
        required_candidate_columns = {
            "id",
            "segment_id",
            "policy_hash",
            "repair_round",
            "incumbent_sha256",
            "expected_voice_profile_id",
            "expected_pitch_semitones",
            "state",
            "tts_attempt",
            "generation_seed",
            "wav_path",
            "wav_sha256",
            "wav_duration",
            "signal_json",
            "beam_result_json",
            "greedy_result_json",
            "beam_check_id",
            "greedy_check_id",
            "final_check_id",
            "failure_reason",
            "created_at",
            "updated_at",
            "promoted_at",
        }
        missing_candidate_columns = required_candidate_columns - candidate_columns
        if missing_candidate_columns:
            raise RuntimeError(
                "segment_candidates schema is incomplete: "
                + ", ".join(sorted(missing_candidate_columns))
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
            if (
                value.startswith("TTS_")
                or value.startswith("ASR_")
                or value.startswith("PERCEPTUAL_")
            ):
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

    @staticmethod
    def _without_perceptual_warnings(existing: str | None) -> str | None:
        values = [
            value
            for value in str(existing or "").split("|")
            if value and not value.startswith("PERCEPTUAL_")
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

    def mark_generating(
        self,
        segment_id: int,
        seed: int,
        *,
        delivery_mode: str | None = None,
        repair_round: int | None = None,
        policy_hash: str | None = None,
    ) -> None:
        normalized_delivery = (
            str(delivery_mode).strip().casefold()
            if delivery_mode is not None
            else None
        )
        if (
            normalized_delivery is not None
            and normalized_delivery not in GENERATION_DELIVERY_MODES
        ):
            raise ValueError(f"Unsupported generation delivery mode: {delivery_mode}")
        normalized_round = int(repair_round) if repair_round is not None else None
        if normalized_round is not None and normalized_round < 0:
            raise ValueError("generation repair round must be non-negative")
        if normalized_delivery == GENERATION_DELIVERY_PRIMARY and normalized_round is not None:
            raise ValueError("primary generation cannot carry an ASR repair round")
        if normalized_delivery == GENERATION_DELIVERY_CLARITY and normalized_round is None:
            raise ValueError("clarity generation requires an ASR repair round")
        normalized_policy_hash = str(policy_hash or "").strip() or None
        if normalized_delivery is not None and normalized_policy_hash is None:
            raise ValueError("generation delivery checkpoints require a quality policy hash")
        with self.transaction() as conn:
            row = conn.execute(
                "SELECT chapter_id,warning_code FROM segments WHERE id=?", (segment_id,)
            ).fetchone()
            if row is None:
                raise KeyError(f"Unknown segment id: {segment_id}")
            retained_warning = self._without_audio_attempt_warnings(
                str(row["warning_code"]) if row["warning_code"] else None
            )
            if normalized_delivery is None:
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
            else:
                conn.execute(
                    """
                    UPDATE segments SET status=?,attempt_count=attempt_count+1,generation_seed=?,
                        generation_delivery_mode=?,generation_repair_round=?,
                        generation_policy_hash=?,asr_text=NULL,asr_similarity=NULL,asr_wer=NULL,
                        warning_code=?,error=NULL,updated_at=? WHERE id=?
                    """,
                    (
                        SegmentStatus.GENERATING.value,
                        seed,
                        normalized_delivery,
                        normalized_round,
                        normalized_policy_hash,
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
        warning_codes: Sequence[str] = (),
    ) -> None:
        with self.transaction() as conn:
            row = conn.execute(
                "SELECT warning_code FROM segments WHERE id=?",
                (segment_id,),
            ).fetchone()
            if row is None:
                raise KeyError(f"Unknown segment id: {segment_id}")
            merged_warning = (
                str(row["warning_code"])
                if row["warning_code"]
                else None
            )
            for warning_code in warning_codes:
                merged_warning = self._merge_warning_codes(
                    merged_warning,
                    str(warning_code),
                )
            conn.execute(
                """
                UPDATE segments SET status=?,wav_path=?,wav_sha256=?,wav_duration=?,signal_json=?,
                    generation_seed=COALESCE(?,generation_seed),warning_code=?,error=NULL,
                    updated_at=? WHERE id=?
                """,
                (
                    SegmentStatus.SIGNAL_PASSED.value,
                    str(wav_path.resolve()),
                    wav_sha256,
                    duration,
                    json.dumps(signal, ensure_ascii=False),
                    generation_seed,
                    merged_warning,
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
                """
                UPDATE segments SET status=?,warning_code=?,generation_frame_cap=NULL,
                    error=NULL,updated_at=? WHERE id=?
                """,
                (status, merged_warning, time.time(), segment_id),
            )
            chapter_id = int(existing["chapter_id"])
            self._refresh_chapter_counts_conn(conn, chapter_id)

    def mark_perceptual_result(
        self,
        segment_id: int,
        *,
        warning_code: str | None = None,
    ) -> None:
        """Finalize a segment after perceptual QA while replacing stale stage warnings."""
        with self.transaction() as conn:
            existing = conn.execute(
                "SELECT chapter_id,warning_code FROM segments WHERE id=?", (segment_id,)
            ).fetchone()
            if existing is None:
                raise KeyError(f"Unknown segment id: {segment_id}")
            retained_warning = self._without_perceptual_warnings(
                str(existing["warning_code"]) if existing["warning_code"] else None
            )
            merged_warning = self._merge_warning_codes(retained_warning, warning_code)
            status = SegmentStatus.WARNING.value if merged_warning else SegmentStatus.VERIFIED.value
            conn.execute(
                "UPDATE segments SET status=?,warning_code=?,error=NULL,updated_at=? WHERE id=?",
                (status, merged_warning, time.time(), segment_id),
            )
            self._refresh_chapter_counts_conn(conn, int(existing["chapter_id"]))

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

    def set_segment_generation_frame_cap(self, segment_id: int, frame_cap: int) -> None:
        normalized_cap = int(frame_cap)
        if normalized_cap <= 0:
            raise ValueError("generation frame cap must be positive")
        with self.connect() as conn:
            cursor = conn.execute(
                "UPDATE segments SET generation_frame_cap=?,updated_at=? WHERE id=?",
                (normalized_cap, time.time(), segment_id),
            )
            if cursor.rowcount != 1:
                raise KeyError(f"Unknown segment id: {segment_id}")

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
                    warning_code=NULL,generation_seed=NULL,generation_delivery_mode='primary',
                    generation_repair_round=NULL,generation_policy_hash=NULL,error=?,updated_at=?
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
            retained_warning = self._without_perceptual_warnings(
                self._without_asr_warnings(
                    str(row["warning_code"]) if row["warning_code"] else None
                )
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
            # Candidate generation owns a separate immutable path. If legacy orchestration happened
            # to mark the segment itself as generating, restore the retained incumbent checkpoint
            # instead of deleting it. Phase-2 orchestration never mutates the segment during clarity.
            conn.execute(
                """
                UPDATE segments SET status='signal_passed',
                    asr_text=NULL,asr_similarity=NULL,asr_wer=NULL,error=?,updated_at=?
                WHERE status='generating'
                  AND wav_path IS NOT NULL AND wav_sha256 IS NOT NULL
                  AND wav_duration IS NOT NULL AND signal_json IS NOT NULL
                  AND EXISTS(
                      SELECT 1 FROM segment_candidates
                      WHERE segment_candidates.segment_id=segments.id
                        AND segment_candidates.incumbent_sha256=segments.wav_sha256
                        AND segment_candidates.state<>'promoted'
                  )
                """,
                (reason, time.time()),
            )
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

    @staticmethod
    def _normalized_sha256(value: str, label: str) -> str:
        normalized = str(value or "").strip().casefold()
        if len(normalized) != 64 or any(character not in "0123456789abcdef" for character in normalized):
            raise ValueError(f"{label} must be a 64-character hexadecimal SHA-256")
        return normalized

    @staticmethod
    def _json_object(value: Any, label: str) -> dict[str, Any]:
        try:
            decoded = json.loads(str(value or "{}"))
        except (TypeError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"{label} is not valid JSON") from exc
        if not isinstance(decoded, dict):
            raise RuntimeError(f"{label} must be a JSON object")
        return decoded

    @staticmethod
    def _candidate_signal_provenance(signal: dict[str, Any]) -> dict[str, Any]:
        required_fields = {
            "spoken_text_sha256",
            "voice_profile_id",
            "pitch_semitones",
            "effective_pitch_semitones",
            "pitch_variant_skipped",
            "pitch_variant_mixed",
        }
        missing = required_fields - signal.keys()
        if missing:
            raise ValueError(
                "segment candidate signal lacks locked provenance: "
                + ", ".join(sorted(missing))
            )
        ProjectDB._normalized_sha256(
            str(signal["spoken_text_sha256"]),
            "segment candidate spoken-text checksum",
        )
        try:
            voice_profile_id = int(signal["voice_profile_id"])
            pitch_semitones = int(signal["pitch_semitones"])
        except (TypeError, ValueError) as exc:
            raise ValueError("segment candidate voice and pitch provenance must be integers") from exc
        if voice_profile_id <= 0:
            raise ValueError("segment candidate voice profile id must be positive")
        for field in ("pitch_variant_skipped", "pitch_variant_mixed"):
            if signal[field] not in (False, True, 0, 1, 0.0, 1.0):
                raise ValueError(f"segment candidate {field} must be boolean")
        pitch_skipped = bool(signal["pitch_variant_skipped"])
        pitch_mixed = bool(signal["pitch_variant_mixed"])
        effective_value = signal["effective_pitch_semitones"]
        if pitch_mixed:
            if effective_value is not None:
                raise ValueError("mixed candidate pitch provenance requires a null effective pitch")
            effective_pitch = None
        else:
            try:
                effective_pitch = int(effective_value)
            except (TypeError, ValueError) as exc:
                raise ValueError("candidate effective pitch provenance must be an integer") from exc
        if pitch_skipped and effective_pitch != 0:
            raise ValueError("a skipped pitch transform must retain effective pitch zero")
        return {
            "spoken_text_sha256": str(signal["spoken_text_sha256"]).casefold(),
            "voice_profile_id": voice_profile_id,
            "pitch_semitones": pitch_semitones,
            "effective_pitch_semitones": effective_pitch,
            "pitch_variant_skipped": pitch_skipped,
            "pitch_variant_mixed": pitch_mixed,
        }

    @staticmethod
    def _candidate_blocking_signal_flags(signal: dict[str, Any]) -> tuple[str, ...]:
        blocking_flags: list[str] = []
        for field in (
            "pace_outlier",
            "pitch_variant_skipped",
            "pitch_variant_mixed",
            "generation_endpoint_active",
        ):
            value = signal.get(field, False)
            if value not in (False, True, 0, 1, 0.0, 1.0):
                raise RuntimeError(f"candidate signal flag {field} is not boolean")
            if bool(value):
                blocking_flags.append(field)
        return tuple(blocking_flags)

    @staticmethod
    def _candidate_final_metrics(
        candidate: sqlite3.Row,
        beam_metrics: dict[str, Any],
        greedy_metrics: dict[str, Any],
        *,
        warning_code: str | None,
    ) -> dict[str, Any]:
        final_metrics = dict(greedy_metrics)
        final_metrics.update(
            {
                "dual_decode_required": True,
                "dual_decode_passed": True,
                "confirmation_verdicts": [
                    str(beam_metrics.get("verdict", "")),
                    str(greedy_metrics.get("verdict", "")),
                ],
                "beam_quality_check_id": int(candidate["beam_check_id"]),
                "greedy_quality_check_id": int(candidate["greedy_check_id"]),
                "decode_evidence": [beam_metrics, greedy_metrics],
                "promotion_warning_code": str(warning_code).strip() if warning_code else None,
            }
        )
        return final_metrics

    @staticmethod
    def _candidate_row_conn(conn: sqlite3.Connection, candidate_id: int) -> sqlite3.Row:
        row = conn.execute(
            "SELECT * FROM segment_candidates WHERE id=?",
            (int(candidate_id),),
        ).fetchone()
        if row is None:
            raise KeyError(f"Unknown segment candidate id: {candidate_id}")
        return row

    @staticmethod
    def _require_candidate_policy_conn(
        conn: sqlite3.Connection,
        policy_hash: str,
        *,
        active: bool = True,
    ) -> sqlite3.Row:
        normalized_hash = str(policy_hash or "").strip()
        row = conn.execute(
            "SELECT * FROM quality_policies WHERE policy_hash=?",
            (normalized_hash,),
        ).fetchone()
        if row is None:
            raise ValueError("segment candidate quality policy is not registered")
        if active and not bool(row["active"]):
            raise RuntimeError("segment candidate quality policy is no longer active")
        return row

    @staticmethod
    def _require_candidate_incumbent_conn(
        conn: sqlite3.Connection,
        candidate: sqlite3.Row,
    ) -> sqlite3.Row:
        segment = conn.execute(
            "SELECT * FROM segments WHERE id=?",
            (int(candidate["segment_id"]),),
        ).fetchone()
        if segment is None:
            raise KeyError(f"Unknown segment id: {candidate['segment_id']}")
        if str(segment["wav_sha256"] or "").casefold() != str(candidate["incumbent_sha256"]):
            raise RuntimeError("segment candidate incumbent checksum changed")
        return segment

    @staticmethod
    def _expected_segment_voice_profile_conn(
        conn: sqlite3.Connection,
        segment: sqlite3.Row,
    ) -> sqlite3.Row:
        if str(segment["kind"] or "").strip().casefold() == "thought":
            profile = conn.execute(
                "SELECT * FROM voice_profiles WHERE voice_key=? COLLATE NOCASE",
                ("narrator",),
            ).fetchone()
            if profile is None:
                raise RuntimeError("thought candidate requires the locked narrator voice profile")
        else:
            if segment["voice_profile_id"] is None:
                raise RuntimeError("segment candidate requires an assigned locked voice profile")
            profile = conn.execute(
                "SELECT * FROM voice_profiles WHERE id=?",
                (int(segment["voice_profile_id"]),),
            ).fetchone()
            if profile is None:
                raise RuntimeError("segment candidate voice profile does not exist")
        if not bool(profile["locked"]):
            raise RuntimeError("segment candidate voice profile is not locked")
        return profile

    @classmethod
    def _require_candidate_voice_profile_conn(
        cls,
        conn: sqlite3.Connection,
        candidate: sqlite3.Row,
        segment: sqlite3.Row,
    ) -> sqlite3.Row:
        profile = cls._expected_segment_voice_profile_conn(conn, segment)
        if (
            int(candidate["expected_voice_profile_id"]) != int(profile["id"])
            or int(candidate["expected_pitch_semitones"])
            != int(profile["pitch_semitones"] or 0)
        ):
            raise RuntimeError("segment candidate voice casting changed after allocation")
        return profile

    @staticmethod
    def _candidate_file_error(candidate: sqlite3.Row) -> str | None:
        wav_path = Path(str(candidate["wav_path"] or ""))
        wav_sha256 = str(candidate["wav_sha256"] or "").strip().casefold()
        if not wav_sha256:
            return "candidate WAV checksum is missing"
        if not wav_path.is_file():
            return "candidate WAV is missing"
        try:
            if sha256_file(wav_path) != wav_sha256:
                return "candidate WAV checksum does not match its immutable checkpoint"
        except OSError as exc:
            return f"candidate WAV could not be read: {exc}"
        return None

    @staticmethod
    def _invalidate_candidate_conn(
        conn: sqlite3.Connection,
        candidate: sqlite3.Row,
        reason: str,
    ) -> sqlite3.Row:
        if str(candidate["state"]) == SEGMENT_CANDIDATE_PROMOTED:
            raise RuntimeError("a promoted segment candidate cannot be invalidated")
        conn.execute(
            """
            UPDATE segment_candidates SET state=?,failure_reason=?,updated_at=?
            WHERE id=? AND state=?
            """,
            (
                SEGMENT_CANDIDATE_INVALID,
                str(reason)[-8000:],
                time.time(),
                int(candidate["id"]),
                str(candidate["state"]),
            ),
        )
        return ProjectDB._candidate_row_conn(conn, int(candidate["id"]))

    @staticmethod
    def _candidate_summary(row: sqlite3.Row) -> dict[str, Any]:
        def decoded_result(field: str) -> dict[str, Any] | None:
            value = row[field]
            if value is None:
                return None
            try:
                decoded = json.loads(str(value))
            except (TypeError, json.JSONDecodeError):
                return {"invalid_json": True}
            return decoded if isinstance(decoded, dict) else {"invalid_json": True}

        return {
            "candidate_id": int(row["id"]),
            "repair_round": int(row["repair_round"]),
            "state": str(row["state"]),
            "incumbent_sha256": str(row["incumbent_sha256"]),
            "expected_voice_profile_id": int(row["expected_voice_profile_id"]),
            "expected_pitch_semitones": int(row["expected_pitch_semitones"]),
            "wav_path": str(row["wav_path"]),
            "wav_sha256": str(row["wav_sha256"] or ""),
            "wav_duration": (
                float(row["wav_duration"]) if row["wav_duration"] is not None else None
            ),
            "generation_seed": int(row["generation_seed"]),
            "tts_attempt": int(row["tts_attempt"]),
            "beam_check_id": int(row["beam_check_id"]) if row["beam_check_id"] is not None else None,
            "greedy_check_id": (
                int(row["greedy_check_id"]) if row["greedy_check_id"] is not None else None
            ),
            "final_check_id": (
                int(row["final_check_id"]) if row["final_check_id"] is not None else None
            ),
            "signal": decoded_result("signal_json"),
            "beam_result": decoded_result("beam_result_json"),
            "greedy_result": decoded_result("greedy_result_json"),
            "failure_reason": str(row["failure_reason"] or ""),
            "promoted_at": (
                float(row["promoted_at"]) if row["promoted_at"] is not None else None
            ),
        }

    def allocate_segment_candidate(
        self,
        *,
        segment_id: int,
        policy_hash: str,
        repair_round: int,
        max_repair_rounds: int,
        incumbent_sha256: str,
        generation_seed: int,
        wav_path: Path,
        candidates_root: Path,
        tts_attempt: int = 0,
    ) -> sqlite3.Row:
        normalized_round = int(repair_round)
        normalized_max = int(max_repair_rounds)
        normalized_attempt = int(tts_attempt)
        normalized_incumbent = self._normalized_sha256(
            incumbent_sha256,
            "segment candidate incumbent checksum",
        )
        normalized_path = str(wav_path.resolve())
        normalized_candidates_root = str(candidates_root.resolve())
        path_key = normalized_path.casefold()
        root_prefix = normalized_candidates_root.rstrip("\\/").casefold() + os.sep.casefold()
        if not path_key.startswith(root_prefix):
            raise ValueError("segment candidate WAV path must be under the dedicated candidates root")
        if normalized_max < 0:
            raise ValueError("ASR repair budget must be non-negative")
        if normalized_round < 0 or normalized_round >= normalized_max:
            raise ValueError("segment candidate repair round exceeds the same-policy budget")
        if normalized_attempt < 0:
            raise ValueError("segment candidate TTS attempt must be non-negative")

        now = time.time()
        with self.transaction() as conn:
            self._require_candidate_policy_conn(conn, policy_hash)
            segment = conn.execute(
                "SELECT * FROM segments WHERE id=?",
                (int(segment_id),),
            ).fetchone()
            if segment is None:
                raise KeyError(f"Unknown segment id: {segment_id}")
            if str(segment["wav_sha256"] or "").casefold() != normalized_incumbent:
                raise RuntimeError("cannot allocate a candidate for a stale incumbent artifact")
            expected_profile = self._expected_segment_voice_profile_conn(conn, segment)
            expected_voice_profile_id = int(expected_profile["id"])
            expected_pitch_semitones = int(expected_profile["pitch_semitones"] or 0)

            rows = list(
                conn.execute(
                    """
                    SELECT * FROM segment_candidates
                    WHERE segment_id=? AND policy_hash=?
                    ORDER BY repair_round
                    """,
                    (int(segment_id), str(policy_hash).strip()),
                )
            )
            existing = next(
                (row for row in rows if int(row["repair_round"]) == normalized_round),
                None,
            )
            if existing is not None:
                if (
                    str(existing["incumbent_sha256"]) != normalized_incumbent
                    or int(existing["expected_voice_profile_id"])
                    != expected_voice_profile_id
                    or int(existing["expected_pitch_semitones"])
                    != expected_pitch_semitones
                    or int(existing["generation_seed"]) != int(generation_seed)
                    or int(existing["tts_attempt"]) != normalized_attempt
                    or str(existing["wav_path"]) != normalized_path
                ):
                    raise RuntimeError("candidate resume metadata differs from its durable checkpoint")
                return existing

            rounds = [int(row["repair_round"]) for row in rows]
            if any(round_index >= normalized_max for round_index in rounds):
                raise RuntimeError("stored candidate rounds exceed the supplied same-policy budget")
            if rounds != list(range(normalized_round)):
                raise RuntimeError("candidate rounds must be contiguous and allocated in order")
            if any(str(row["incumbent_sha256"]) != normalized_incumbent for row in rows):
                raise RuntimeError("same-policy candidate rounds cannot mix incumbent artifacts")
            if any(str(row["state"]) not in SEGMENT_CANDIDATE_FAILURE_STATES for row in rows):
                raise RuntimeError("the previous candidate round is not a terminal failure")
            occupied_paths = [
                str(row[0])
                for row in conn.execute(
                    """
                    SELECT wav_path FROM segments WHERE wav_path IS NOT NULL
                    UNION ALL
                    SELECT wav_path FROM segment_candidates
                    """
                )
            ]
            if any(path.casefold() == path_key for path in occupied_paths):
                raise RuntimeError("segment candidate WAV path collides with an immutable audio artifact")

            try:
                cursor = conn.execute(
                    """
                    INSERT INTO segment_candidates(
                        segment_id,policy_hash,repair_round,incumbent_sha256,
                        expected_voice_profile_id,expected_pitch_semitones,state,
                        tts_attempt,generation_seed,wav_path,created_at,updated_at
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        int(segment_id),
                        str(policy_hash).strip(),
                        normalized_round,
                        normalized_incumbent,
                        expected_voice_profile_id,
                        expected_pitch_semitones,
                        SEGMENT_CANDIDATE_GENERATING,
                        normalized_attempt,
                        int(generation_seed),
                        normalized_path,
                        now,
                        now,
                    ),
                )
            except sqlite3.IntegrityError as exc:
                raise RuntimeError("segment candidate allocation conflicts with durable metadata") from exc
            return self._candidate_row_conn(conn, int(cursor.lastrowid))

    def restart_segment_candidate_generation(
        self,
        candidate_id: int,
        *,
        expected_generation_seed: int,
        generation_seed: int,
        tts_attempt: int,
    ) -> sqlite3.Row:
        normalized_attempt = int(tts_attempt)
        with self.transaction() as conn:
            candidate = self._candidate_row_conn(conn, candidate_id)
            self._require_candidate_policy_conn(conn, str(candidate["policy_hash"]))
            segment = self._require_candidate_incumbent_conn(conn, candidate)
            self._require_candidate_voice_profile_conn(conn, candidate, segment)
            if str(candidate["state"]) != SEGMENT_CANDIDATE_GENERATING:
                raise RuntimeError("only an uncommitted generating candidate can restart TTS")
            current_attempt = int(candidate["tts_attempt"])
            if normalized_attempt == current_attempt and int(generation_seed) == int(
                candidate["generation_seed"]
            ):
                return candidate
            if int(candidate["generation_seed"]) != int(expected_generation_seed):
                raise RuntimeError("segment candidate generation seed CAS failed")
            if normalized_attempt != current_attempt + 1:
                raise RuntimeError("segment candidate TTS attempts must advance exactly once")
            conn.execute(
                """
                UPDATE segment_candidates
                SET tts_attempt=?,generation_seed=?,updated_at=?
                WHERE id=? AND state=? AND generation_seed=?
                """,
                (
                    normalized_attempt,
                    int(generation_seed),
                    time.time(),
                    int(candidate_id),
                    SEGMENT_CANDIDATE_GENERATING,
                    int(expected_generation_seed),
                ),
            )
            return self._candidate_row_conn(conn, candidate_id)

    def checkpoint_segment_candidate_signal(
        self,
        candidate_id: int,
        *,
        expected_generation_seed: int,
        wav_path: Path,
        wav_sha256: str,
        duration: float,
        signal: dict[str, Any],
    ) -> sqlite3.Row:
        normalized_path = str(wav_path.resolve())
        normalized_sha256 = self._normalized_sha256(
            wav_sha256,
            "segment candidate WAV checksum",
        )
        normalized_duration = float(duration)
        if normalized_duration <= 0:
            raise ValueError("segment candidate WAV duration must be positive")
        if not isinstance(signal, dict):
            raise ValueError("segment candidate signal checkpoint must be a dictionary")
        if str(signal.get("tts_delivery_mode", "")).strip().casefold() != GENERATION_DELIVERY_CLARITY:
            raise ValueError("segment candidate signal must use clarity delivery")
        try:
            signal_round = int(signal["asr_clarity_repair_round"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("segment candidate signal lacks its clarity repair round") from exc
        signal_provenance = self._candidate_signal_provenance(signal)
        signal_json = json.dumps(signal, ensure_ascii=False, sort_keys=True)
        wav_file = Path(normalized_path)
        if not wav_file.is_file():
            raise RuntimeError("segment candidate WAV is missing before its signal checkpoint")
        if sha256_file(wav_file) != normalized_sha256:
            raise RuntimeError("segment candidate WAV checksum differs before its signal checkpoint")

        with self.transaction() as conn:
            candidate = self._candidate_row_conn(conn, candidate_id)
            self._require_candidate_policy_conn(conn, str(candidate["policy_hash"]))
            segment = self._require_candidate_incumbent_conn(conn, candidate)
            self._require_candidate_voice_profile_conn(conn, candidate, segment)
            if (
                signal_provenance["voice_profile_id"]
                != int(candidate["expected_voice_profile_id"])
                or signal_provenance["pitch_semitones"]
                != int(candidate["expected_pitch_semitones"])
            ):
                raise ValueError("candidate signal voice provenance differs from locked casting")
            if (
                not signal_provenance["pitch_variant_skipped"]
                and not signal_provenance["pitch_variant_mixed"]
                and signal_provenance["effective_pitch_semitones"]
                != int(candidate["expected_pitch_semitones"])
            ):
                raise ValueError("candidate signal effective pitch differs from locked casting")
            if int(candidate["repair_round"]) != signal_round:
                raise ValueError("segment candidate signal repair round does not match its ledger row")
            if int(candidate["generation_seed"]) != int(expected_generation_seed):
                raise RuntimeError("segment candidate generation seed CAS failed")
            if str(candidate["wav_path"]) != normalized_path:
                raise RuntimeError("segment candidate WAV path differs from its allocation")
            state = str(candidate["state"])
            if state != SEGMENT_CANDIDATE_GENERATING:
                if (
                    state in SEGMENT_CANDIDATE_STATES - {SEGMENT_CANDIDATE_GENERATING}
                    and str(candidate["wav_sha256"] or "") == normalized_sha256
                    and float(candidate["wav_duration"] or 0.0) == normalized_duration
                    and str(candidate["signal_json"] or "") == signal_json
                ):
                    return candidate
                raise RuntimeError("segment candidate signal checkpoint transition CAS failed")
            conn.execute(
                """
                UPDATE segment_candidates
                SET state=?,wav_sha256=?,wav_duration=?,signal_json=?,updated_at=?
                WHERE id=? AND state=? AND generation_seed=?
                """,
                (
                    SEGMENT_CANDIDATE_SIGNAL_PASSED,
                    normalized_sha256,
                    normalized_duration,
                    signal_json,
                    time.time(),
                    int(candidate_id),
                    SEGMENT_CANDIDATE_GENERATING,
                    int(expected_generation_seed),
                ),
            )
            return self._candidate_row_conn(conn, candidate_id)

    def _validated_candidate_decode_check_conn(
        self,
        conn: sqlite3.Connection,
        candidate: sqlite3.Row,
        quality_check_id: int,
        *,
        confirmation: bool,
    ) -> tuple[sqlite3.Row, dict[str, Any]]:
        check = conn.execute(
            "SELECT * FROM quality_checks WHERE id=?",
            (int(quality_check_id),),
        ).fetchone()
        if check is None:
            raise KeyError(f"Unknown quality check id: {quality_check_id}")
        if (
            str(check["scope"]) != QUALITY_SCOPE_SEGMENT
            or str(check["stage"]) != SEGMENT_ASR_DECODE_QUALITY_STAGE
            or int(check["segment_id"] or -1) != int(candidate["segment_id"])
            or str(check["artifact_sha256"]).casefold() != str(candidate["wav_sha256"])
            or str(check["policy_hash"]) != str(candidate["policy_hash"])
        ):
            raise RuntimeError("ASR decode evidence does not belong to this segment candidate")
        metrics = self._json_object(check["metrics_json"], "candidate ASR decode metrics")
        decode_mode = str(metrics.get("decode_mode", "")).strip().casefold()
        expected_mode = decode_mode == "greedy" if confirmation else decode_mode.startswith("beam")
        if not expected_mode or not bool(metrics.get("selected", False)):
            raise RuntimeError("candidate ASR checkpoint must reference the selected decode evidence")
        if (
            str(metrics.get("delivery_mode", "")).strip().casefold() != GENERATION_DELIVERY_CLARITY
            or int(metrics.get("repair_round", -1)) != int(candidate["repair_round"])
            or int(metrics.get("generation_seed", -1)) != int(candidate["generation_seed"])
        ):
            raise RuntimeError("candidate ASR decode provenance differs from its generation checkpoint")
        signal = self._json_object(candidate["signal_json"], "candidate signal metrics")
        signal_provenance = self._candidate_signal_provenance(signal)
        try:
            decode_provenance = self._candidate_signal_provenance(metrics)
        except ValueError as exc:
            raise RuntimeError("candidate ASR decode lacks locked voice or pitch provenance") from exc
        if decode_provenance != signal_provenance:
            raise RuntimeError("candidate ASR locked provenance differs from its signal checkpoint")
        if check["verdict"] not in {QUALITY_VERDICT_PASS, "fail", "inconclusive"}:
            raise RuntimeError("candidate ASR decode evidence has an unsupported verdict")
        evidence_verdict = str(check["verdict"])
        metrics_verdict = str(metrics.get("verdict", "")).strip().casefold()
        metrics_passed = metrics.get("passed")
        verdict_consistent = (
            evidence_verdict == QUALITY_VERDICT_PASS
            and metrics_verdict == QUALITY_VERDICT_PASS
            and metrics_passed is True
        ) or (
            evidence_verdict == "fail"
            and metrics_verdict == "mismatch"
            and metrics_passed is False
        ) or (
            evidence_verdict == "inconclusive"
            and metrics_verdict == "inconclusive"
            and metrics_passed is False
        )
        if not verdict_consistent:
            raise RuntimeError("candidate ASR quality-check verdict contradicts its metrics")
        if evidence_verdict == QUALITY_VERDICT_PASS:
            transcript = metrics.get("transcript")
            if not isinstance(transcript, str) or not transcript.strip():
                raise RuntimeError("passing candidate ASR evidence requires a transcript")
            try:
                similarity = float(metrics["similarity"])
                wer = float(metrics["wer"])
            except (KeyError, TypeError, ValueError) as exc:
                raise RuntimeError(
                    "passing candidate ASR evidence requires numeric similarity and WER"
                ) from exc
            if not math.isfinite(similarity) or not 0.0 <= similarity <= 1.0:
                raise RuntimeError("passing candidate ASR similarity is outside [0, 1]")
            if not math.isfinite(wer) or wer < 0.0:
                raise RuntimeError("passing candidate ASR WER must be finite and non-negative")
        return check, metrics

    def checkpoint_segment_candidate_decode(
        self,
        candidate_id: int,
        *,
        quality_check_id: int,
        confirmation: bool,
    ) -> sqlite3.Row:
        with self.transaction() as conn:
            candidate = self._candidate_row_conn(conn, candidate_id)
            self._require_candidate_policy_conn(conn, str(candidate["policy_hash"]))
            segment = self._require_candidate_incumbent_conn(conn, candidate)
            self._require_candidate_voice_profile_conn(conn, candidate, segment)
            check, metrics = self._validated_candidate_decode_check_conn(
                conn,
                candidate,
                quality_check_id,
                confirmation=confirmation,
            )
            state = str(candidate["state"])
            result_json = json.dumps(metrics, ensure_ascii=False, sort_keys=True)
            if not confirmation:
                if candidate["beam_check_id"] is not None:
                    if int(candidate["beam_check_id"]) == int(quality_check_id):
                        return candidate
                    raise RuntimeError("candidate beam decode was already checkpointed")
                if state != SEGMENT_CANDIDATE_SIGNAL_PASSED:
                    raise RuntimeError("candidate beam decode transition CAS failed")
                conn.execute(
                    """
                    UPDATE segment_candidates
                    SET state=?,beam_check_id=?,beam_result_json=?,updated_at=?
                    WHERE id=? AND state=? AND beam_check_id IS NULL
                    """,
                    (
                        SEGMENT_CANDIDATE_BEAM_RECORDED,
                        int(quality_check_id),
                        result_json,
                        time.time(),
                        int(candidate_id),
                        SEGMENT_CANDIDATE_SIGNAL_PASSED,
                    ),
                )
                return self._candidate_row_conn(conn, candidate_id)

            if candidate["greedy_check_id"] is not None:
                if int(candidate["greedy_check_id"]) == int(quality_check_id):
                    return candidate
                raise RuntimeError("candidate greedy decode was already checkpointed")
            if state != SEGMENT_CANDIDATE_BEAM_RECORDED or candidate["beam_check_id"] is None:
                raise RuntimeError("candidate greedy decode transition CAS failed")
            beam_check = conn.execute(
                "SELECT verdict FROM quality_checks WHERE id=?",
                (int(candidate["beam_check_id"]),),
            ).fetchone()
            if beam_check is None:
                raise RuntimeError("candidate beam decode evidence is missing")
            dual_passed = (
                str(beam_check["verdict"]) == QUALITY_VERDICT_PASS
                and str(check["verdict"]) == QUALITY_VERDICT_PASS
            )
            signal = self._json_object(candidate["signal_json"], "candidate signal metrics")
            blocking_signal_flags = self._candidate_blocking_signal_flags(signal)
            dual_passed = dual_passed and not blocking_signal_flags
            next_state = (
                SEGMENT_CANDIDATE_DUAL_PASSED
                if dual_passed
                else SEGMENT_CANDIDATE_DUAL_FAILED
            )
            failure_reason = None
            if not dual_passed:
                beam_metrics = self._json_object(
                    candidate["beam_result_json"],
                    "candidate beam result",
                )
                failure_reason = "; ".join(
                    value
                    for value in (
                        f"beam={beam_metrics.get('reason', beam_check['verdict'])}",
                        f"greedy={metrics.get('reason', check['verdict'])}",
                    )
                    if value
                )
                if blocking_signal_flags:
                    failure_reason = "; ".join(
                        value
                        for value in (
                            failure_reason,
                            "blocking_signal=" + ",".join(blocking_signal_flags),
                        )
                        if value
                    )
            conn.execute(
                """
                UPDATE segment_candidates
                SET state=?,greedy_check_id=?,greedy_result_json=?,failure_reason=?,updated_at=?
                WHERE id=? AND state=? AND greedy_check_id IS NULL
                """,
                (
                    next_state,
                    int(quality_check_id),
                    result_json,
                    failure_reason,
                    time.time(),
                    int(candidate_id),
                    SEGMENT_CANDIDATE_BEAM_RECORDED,
                ),
            )
            return self._candidate_row_conn(conn, candidate_id)

    def mark_segment_candidate_tts_failed(
        self,
        candidate_id: int,
        *,
        expected_generation_seed: int,
        error: str,
    ) -> sqlite3.Row:
        normalized_error = str(error or "").strip()
        if not normalized_error:
            raise ValueError("segment candidate TTS failure must include a reason")
        with self.transaction() as conn:
            candidate = self._candidate_row_conn(conn, candidate_id)
            self._require_candidate_policy_conn(conn, str(candidate["policy_hash"]))
            segment = self._require_candidate_incumbent_conn(conn, candidate)
            self._require_candidate_voice_profile_conn(conn, candidate, segment)
            if str(candidate["state"]) == SEGMENT_CANDIDATE_TTS_FAILED:
                if (
                    int(candidate["generation_seed"]) == int(expected_generation_seed)
                    and str(candidate["failure_reason"] or "") == normalized_error[-8000:]
                ):
                    return candidate
                raise RuntimeError("segment candidate TTS failure replay payload differs")
            if (
                str(candidate["state"]) != SEGMENT_CANDIDATE_GENERATING
                or int(candidate["generation_seed"]) != int(expected_generation_seed)
            ):
                raise RuntimeError("segment candidate TTS failure transition CAS failed")
            conn.execute(
                """
                UPDATE segment_candidates
                SET state=?,failure_reason=?,updated_at=?
                WHERE id=? AND state=? AND generation_seed=?
                """,
                (
                    SEGMENT_CANDIDATE_TTS_FAILED,
                    normalized_error[-8000:],
                    time.time(),
                    int(candidate_id),
                    SEGMENT_CANDIDATE_GENERATING,
                    int(expected_generation_seed),
                ),
            )
            return self._candidate_row_conn(conn, candidate_id)

    def mark_segment_candidate_invalid(
        self,
        candidate_id: int,
        *,
        expected_wav_sha256: str,
        reason: str,
    ) -> sqlite3.Row:
        normalized_sha256 = self._normalized_sha256(
            expected_wav_sha256,
            "segment candidate invalidation checksum",
        )
        normalized_reason = str(reason or "").strip()
        if not normalized_reason:
            raise ValueError("segment candidate invalidation must include a reason")
        with self.transaction() as conn:
            candidate = self._candidate_row_conn(conn, candidate_id)
            self._require_candidate_policy_conn(conn, str(candidate["policy_hash"]))
            segment = self._require_candidate_incumbent_conn(conn, candidate)
            self._require_candidate_voice_profile_conn(conn, candidate, segment)
            state = str(candidate["state"])
            if state == SEGMENT_CANDIDATE_INVALID:
                if (
                    str(candidate["wav_sha256"] or "") == normalized_sha256
                    and str(candidate["failure_reason"] or "") == normalized_reason[-8000:]
                ):
                    return candidate
                raise RuntimeError("segment candidate invalidation replay payload differs")
            if state in {SEGMENT_CANDIDATE_GENERATING, SEGMENT_CANDIDATE_TTS_FAILED}:
                raise RuntimeError("candidate has no committed WAV to invalidate")
            if state == SEGMENT_CANDIDATE_PROMOTED:
                raise RuntimeError("a promoted segment candidate cannot be invalidated")
            if str(candidate["wav_sha256"] or "") != normalized_sha256:
                raise RuntimeError("segment candidate invalidation checksum CAS failed")
            conn.execute(
                """
                UPDATE segment_candidates
                SET state=?,failure_reason=?,updated_at=?
                WHERE id=? AND state=? AND wav_sha256=?
                """,
                (
                    SEGMENT_CANDIDATE_INVALID,
                    normalized_reason[-8000:],
                    time.time(),
                    int(candidate_id),
                    state,
                    normalized_sha256,
                ),
            )
            return self._candidate_row_conn(conn, candidate_id)

    def get_segment_candidate(self, candidate_id: int) -> sqlite3.Row:
        with self.connect() as conn:
            return self._candidate_row_conn(conn, candidate_id)

    def list_segment_candidates(
        self,
        *,
        segment_id: int | None = None,
        policy_hash: str | None = None,
    ) -> list[sqlite3.Row]:
        clauses: list[str] = []
        params: list[Any] = []
        if segment_id is not None:
            clauses.append("segment_id=?")
            params.append(int(segment_id))
        if policy_hash is not None:
            clauses.append("policy_hash=?")
            params.append(str(policy_hash).strip())
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        with self.connect() as conn:
            return list(
                conn.execute(
                    f"SELECT * FROM segment_candidates{where} ORDER BY segment_id,repair_round",
                    params,
                )
            )

    def reconcile_segment_candidate_artifacts(self, policy_hash: str) -> int:
        invalidated = 0
        with self.transaction() as conn:
            self._require_candidate_policy_conn(conn, policy_hash)
            candidates = list(
                conn.execute(
                    """
                    SELECT * FROM segment_candidates
                    WHERE policy_hash=? AND state NOT IN ('generating','tts_failed','invalid','promoted')
                    ORDER BY segment_id,repair_round
                    """,
                    (str(policy_hash).strip(),),
                )
            )
            for candidate in candidates:
                invalid_reason: str | None = None
                try:
                    segment = self._require_candidate_incumbent_conn(conn, candidate)
                    self._require_candidate_voice_profile_conn(conn, candidate, segment)
                except (KeyError, RuntimeError) as exc:
                    invalid_reason = str(exc)
                if invalid_reason is None:
                    invalid_reason = self._candidate_file_error(candidate)
                if invalid_reason is None and str(candidate["state"]) == SEGMENT_CANDIDATE_DUAL_PASSED:
                    try:
                        signal = self._json_object(
                            candidate["signal_json"],
                            "candidate signal metrics",
                        )
                        blocking_flags = self._candidate_blocking_signal_flags(signal)
                        if blocking_flags:
                            invalid_reason = (
                                "candidate signal retains blocking TTS flags: "
                                + ", ".join(blocking_flags)
                            )
                    except RuntimeError as exc:
                        invalid_reason = str(exc)
                if invalid_reason:
                    self._invalidate_candidate_conn(conn, candidate, invalid_reason)
                    invalidated += 1
        return invalidated

    def segment_candidate_attempt_summary(
        self,
        segment_id: int,
        policy_hash: str,
    ) -> list[dict[str, Any]]:
        return [
            self._candidate_summary(row)
            for row in self.list_segment_candidates(
                segment_id=segment_id,
                policy_hash=policy_hash,
            )
        ]

    def segment_candidate_resume_plan(
        self,
        segment_id: int,
        policy_hash: str,
        max_repair_rounds: int,
    ) -> dict[str, Any]:
        normalized_max = int(max_repair_rounds)
        if normalized_max < 0:
            raise ValueError("ASR repair budget must be non-negative")
        with self.connect() as conn:
            policy = self._require_candidate_policy_conn(conn, policy_hash, active=False)
            rows = list(
                conn.execute(
                    """
                    SELECT * FROM segment_candidates
                    WHERE segment_id=? AND policy_hash=?
                    ORDER BY repair_round
                    """,
                    (int(segment_id), str(policy_hash).strip()),
                )
            )
            if not bool(policy["active"]):
                return {
                    "segment_id": int(segment_id),
                    "policy_hash": str(policy_hash).strip(),
                    "action": "stale_policy",
                    "candidate_id": None,
                    "repair_round": None,
                }
            promoted = [row for row in rows if str(row["state"]) == SEGMENT_CANDIDATE_PROMOTED]
            if promoted:
                if len(promoted) != 1 or any(
                    str(row["state"])
                    not in SEGMENT_CANDIDATE_FAILURE_STATES | {SEGMENT_CANDIDATE_PROMOTED}
                    for row in rows
                ):
                    raise RuntimeError("promoted candidate ledger has another actionable candidate")
                segment = conn.execute(
                    "SELECT wav_sha256 FROM segments WHERE id=?",
                    (int(segment_id),),
                ).fetchone()
                if segment is None or str(segment["wav_sha256"] or "") != str(
                    promoted[0]["wav_sha256"] or ""
                ):
                    raise RuntimeError("promoted candidate is not the current segment artifact")
                return {
                    "segment_id": int(segment_id),
                    "policy_hash": str(policy_hash).strip(),
                    "action": "complete",
                    "candidate_id": int(promoted[0]["id"]),
                    "repair_round": int(promoted[0]["repair_round"]),
                    "state": SEGMENT_CANDIDATE_PROMOTED,
                }
            if rows:
                incumbents = {str(row["incumbent_sha256"]) for row in rows}
                if len(incumbents) != 1:
                    raise RuntimeError("same-policy candidate rounds contain mixed incumbent artifacts")
                segment = conn.execute(
                    "SELECT wav_sha256 FROM segments WHERE id=?",
                    (int(segment_id),),
                ).fetchone()
                if segment is None:
                    raise KeyError(f"Unknown segment id: {segment_id}")
                if str(segment["wav_sha256"] or "").casefold() not in incumbents:
                    return {
                        "segment_id": int(segment_id),
                        "policy_hash": str(policy_hash).strip(),
                        "action": "stale_incumbent",
                        "candidate_id": None,
                        "repair_round": None,
                    }
            if any(int(row["repair_round"]) >= normalized_max for row in rows):
                raise RuntimeError("stored candidate rounds exceed the supplied same-policy budget")
            if [int(row["repair_round"]) for row in rows] != list(range(len(rows))):
                raise RuntimeError("stored candidate rounds are not contiguous")

            actionable = [
                row
                for row in rows
                if str(row["state"])
                not in SEGMENT_CANDIDATE_FAILURE_STATES | {SEGMENT_CANDIDATE_PROMOTED}
            ]
            if len(actionable) > 1:
                raise RuntimeError("multiple segment candidates are simultaneously actionable")
            if actionable:
                candidate = actionable[0]
                segment = self._require_candidate_incumbent_conn(conn, candidate)
                self._require_candidate_voice_profile_conn(conn, candidate, segment)
                state = str(candidate["state"])
                action = {
                    SEGMENT_CANDIDATE_GENERATING: "generate",
                    SEGMENT_CANDIDATE_SIGNAL_PASSED: "decode_beam",
                    SEGMENT_CANDIDATE_BEAM_RECORDED: "decode_greedy",
                    SEGMENT_CANDIDATE_DUAL_PASSED: "promote",
                }.get(state)
                if action is None:
                    raise RuntimeError(f"unsupported actionable candidate state: {state}")
                return {
                    "segment_id": int(segment_id),
                    "policy_hash": str(policy_hash).strip(),
                    "action": action,
                    "candidate_id": int(candidate["id"]),
                    "repair_round": int(candidate["repair_round"]),
                    "state": state,
                    "generation_seed": int(candidate["generation_seed"]),
                    "tts_attempt": int(candidate["tts_attempt"]),
                    "wav_path": str(candidate["wav_path"]),
                    "wav_sha256": str(candidate["wav_sha256"] or ""),
                }
            if len(rows) < normalized_max:
                return {
                    "segment_id": int(segment_id),
                    "policy_hash": str(policy_hash).strip(),
                    "action": "allocate",
                    "candidate_id": None,
                    "repair_round": len(rows),
                }
            return {
                "segment_id": int(segment_id),
                "policy_hash": str(policy_hash).strip(),
                "action": "exhausted",
                "candidate_id": None,
                "repair_round": None,
            }

    def list_segment_candidate_resume_plans(
        self,
        policy_hash: str,
        max_repair_rounds: int,
    ) -> list[dict[str, Any]]:
        with self.connect() as conn:
            segment_ids = [
                int(row[0])
                for row in conn.execute(
                    """
                    SELECT DISTINCT segment_id FROM segment_candidates
                    WHERE policy_hash=? ORDER BY segment_id
                    """,
                    (str(policy_hash).strip(),),
                )
            ]
        return [
            self.segment_candidate_resume_plan(segment_id, policy_hash, max_repair_rounds)
            for segment_id in segment_ids
        ]

    def count_stale_segment_candidates(self, active_policy_hash: str) -> int:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) FROM segment_candidates WHERE policy_hash<>? AND state<>'promoted'",
                (str(active_policy_hash).strip(),),
            ).fetchone()
            return int(row[0] if row is not None else 0)

    def promote_segment_candidate(
        self,
        candidate_id: int,
        *,
        validated_wav_sha256: str,
        repair_action: str | None = None,
        attempt: int,
        warning_code: str | None = None,
    ) -> sqlite3.Row:
        normalized_sha256 = self._normalized_sha256(
            validated_wav_sha256,
            "validated segment candidate checksum",
        )
        normalized_attempt = int(attempt)
        if normalized_attempt < 1:
            raise ValueError("candidate final audio attempt must be positive")
        normalized_repair_action = str(repair_action).strip() if repair_action else None
        normalized_warning_code = str(warning_code).strip() if warning_code else None
        with self.transaction() as conn:
            candidate = self._candidate_row_conn(conn, candidate_id)
            policy = self._require_candidate_policy_conn(conn, str(candidate["policy_hash"]))
            segment = conn.execute(
                "SELECT * FROM segments WHERE id=?",
                (int(candidate["segment_id"]),),
            ).fetchone()
            if segment is None:
                raise KeyError(f"Unknown segment id: {candidate['segment_id']}")
            if str(candidate["wav_sha256"] or "") != normalized_sha256:
                raise RuntimeError("validated candidate checksum differs from the durable signal checkpoint")
            candidate_state = str(candidate["state"])
            if candidate_state not in {
                SEGMENT_CANDIDATE_DUAL_PASSED,
                SEGMENT_CANDIDATE_PROMOTED,
            }:
                raise RuntimeError("segment candidate cannot be promoted before both ASR decodes pass")
            self._require_candidate_voice_profile_conn(conn, candidate, segment)
            beam_check, beam_metrics = self._validated_candidate_decode_check_conn(
                conn,
                candidate,
                int(candidate["beam_check_id"]),
                confirmation=False,
            )
            greedy_check, greedy_metrics = self._validated_candidate_decode_check_conn(
                conn,
                candidate,
                int(candidate["greedy_check_id"]),
                confirmation=True,
            )
            if (
                str(beam_check["verdict"]) != QUALITY_VERDICT_PASS
                or str(greedy_check["verdict"]) != QUALITY_VERDICT_PASS
            ):
                raise RuntimeError("candidate dual-decode ledger does not contain two passing checks")
            final_metrics = self._candidate_final_metrics(
                candidate,
                beam_metrics,
                greedy_metrics,
                warning_code=normalized_warning_code,
            )
            final_metrics_json = json.dumps(final_metrics, ensure_ascii=False, sort_keys=True)
            if candidate_state == SEGMENT_CANDIDATE_PROMOTED:
                if (
                    str(segment["wav_sha256"] or "") == normalized_sha256
                    and candidate["final_check_id"] is not None
                ):
                    final_check = conn.execute(
                        "SELECT * FROM quality_checks WHERE id=?",
                        (int(candidate["final_check_id"]),),
                    ).fetchone()
                    if (
                        final_check is not None
                        and str(final_check["verdict"]) == QUALITY_VERDICT_PASS
                        and str(final_check["metrics_json"]) == final_metrics_json
                        and str(final_check["failure_codes_json"]) == "[]"
                        and final_check["repair_action"] == normalized_repair_action
                        and int(final_check["attempt"]) == normalized_attempt
                    ):
                        return candidate
                raise RuntimeError("segment candidate promotion replay does not match the committed result")
            if str(segment["wav_sha256"] or "").casefold() != str(candidate["incumbent_sha256"]):
                raise RuntimeError("segment candidate incumbent checksum changed")
            file_error = self._candidate_file_error(candidate)
            if file_error:
                return self._invalidate_candidate_conn(conn, candidate, file_error)
            signal = self._json_object(candidate["signal_json"], "candidate signal metrics")
            self._candidate_signal_provenance(signal)
            blocking_signal_flags = self._candidate_blocking_signal_flags(signal)
            if blocking_signal_flags:
                return self._invalidate_candidate_conn(
                    conn,
                    candidate,
                    "candidate signal retains blocking TTS flags: "
                    + ", ".join(blocking_signal_flags),
                )
            final_check_cursor = conn.execute(
                """
                INSERT INTO quality_checks(
                    scope,stage,segment_id,chapter_id,artifact_sha256,
                    policy_hash,policy_version,verdict,metrics_json,
                    failure_codes_json,repair_action,attempt,created_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    QUALITY_SCOPE_SEGMENT,
                    SEGMENT_AUDIO_QUALITY_STAGE,
                    int(candidate["segment_id"]),
                    None,
                    normalized_sha256,
                    str(candidate["policy_hash"]),
                    int(policy["policy_version"]),
                    QUALITY_VERDICT_PASS,
                    final_metrics_json,
                    "[]",
                    normalized_repair_action,
                    normalized_attempt,
                    time.time(),
                ),
            )
            final_quality_check_id = int(final_check_cursor.lastrowid)
            retained_warning = self._without_audio_attempt_warnings(
                str(segment["warning_code"]) if segment["warning_code"] else None
            )
            merged_warning = self._merge_warning_codes(retained_warning, normalized_warning_code)
            status = SegmentStatus.WARNING.value if merged_warning else SegmentStatus.VERIFIED.value
            now = time.time()
            segment_cursor = conn.execute(
                """
                UPDATE segments SET
                    status=?,generation_seed=?,generation_frame_cap=NULL,
                    generation_delivery_mode=?,generation_repair_round=?,generation_policy_hash=?,
                    wav_path=?,wav_sha256=?,wav_duration=?,signal_json=?,
                    asr_text=?,asr_similarity=?,asr_wer=?,warning_code=?,error=NULL,updated_at=?
                WHERE id=? AND wav_sha256=?
                """,
                (
                    status,
                    int(candidate["generation_seed"]),
                    GENERATION_DELIVERY_CLARITY,
                    int(candidate["repair_round"]),
                    str(candidate["policy_hash"]),
                    str(candidate["wav_path"]),
                    normalized_sha256,
                    float(candidate["wav_duration"]),
                    str(candidate["signal_json"]),
                    str(final_metrics.get("transcript", "")),
                    float(final_metrics.get("similarity", 0.0)),
                    float(final_metrics.get("wer", 1.0)),
                    merged_warning,
                    now,
                    int(candidate["segment_id"]),
                    str(candidate["incumbent_sha256"]),
                ),
            )
            if segment_cursor.rowcount != 1:
                raise RuntimeError("segment candidate promotion lost the incumbent CAS")
            candidate_cursor = conn.execute(
                """
                UPDATE segment_candidates
                SET state=?,final_check_id=?,promoted_at=?,updated_at=?
                WHERE id=? AND state=?
                """,
                (
                    SEGMENT_CANDIDATE_PROMOTED,
                    final_quality_check_id,
                    now,
                    now,
                    int(candidate_id),
                    SEGMENT_CANDIDATE_DUAL_PASSED,
                ),
            )
            if candidate_cursor.rowcount != 1:
                raise RuntimeError("segment candidate promotion state CAS failed")
            self._refresh_chapter_counts_conn(conn, int(segment["chapter_id"]))
            return self._candidate_row_conn(conn, candidate_id)

    def finalize_segment_candidate_exhaustion(
        self,
        *,
        segment_id: int,
        policy_hash: str,
        max_repair_rounds: int,
        incumbent_sha256: str,
        trigger_quality_check_id: int,
        error: str,
        warning_code: str,
        final_verdict: str = "fail",
        failure_codes: Sequence[str] = (),
    ) -> int:
        normalized_max = int(max_repair_rounds)
        normalized_incumbent = self._normalized_sha256(
            incumbent_sha256,
            "repair exhaustion incumbent checksum",
        )
        normalized_verdict = str(final_verdict).strip().casefold()
        normalized_error = str(error or "").strip()[-8000:]
        normalized_warning_code = str(warning_code or "").strip()
        requested_failure_codes = [
            str(code).strip() for code in failure_codes if str(code).strip()
        ]
        if normalized_max < 0:
            raise ValueError("ASR repair budget must be non-negative")
        if normalized_verdict not in {"fail", "inconclusive"}:
            raise ValueError("repair exhaustion verdict must be fail or inconclusive")
        if not normalized_error or not normalized_warning_code:
            raise ValueError("repair exhaustion requires an error and warning code")

        with self.transaction() as conn:
            policy = self._require_candidate_policy_conn(conn, policy_hash)
            segment = conn.execute(
                "SELECT * FROM segments WHERE id=?",
                (int(segment_id),),
            ).fetchone()
            if segment is None:
                raise KeyError(f"Unknown segment id: {segment_id}")
            if str(segment["wav_sha256"] or "").casefold() != normalized_incumbent:
                raise RuntimeError("repair exhaustion incumbent checksum CAS failed")
            candidates = list(
                conn.execute(
                    """
                    SELECT * FROM segment_candidates
                    WHERE segment_id=? AND policy_hash=? ORDER BY repair_round
                    """,
                    (int(segment_id), str(policy_hash).strip()),
                )
            )
            if [int(row["repair_round"]) for row in candidates] != list(range(normalized_max)):
                raise RuntimeError("repair exhaustion requires every configured candidate round")
            if any(str(row["state"]) not in SEGMENT_CANDIDATE_FAILURE_STATES for row in candidates):
                raise RuntimeError("repair exhaustion cannot finalize while a candidate remains actionable")
            if any(str(row["incumbent_sha256"]) != normalized_incumbent for row in candidates):
                raise RuntimeError("repair exhaustion candidates do not share the current incumbent")

            trigger = conn.execute(
                "SELECT * FROM quality_checks WHERE id=?",
                (int(trigger_quality_check_id),),
            ).fetchone()
            if trigger is None:
                raise KeyError(f"Unknown quality check id: {trigger_quality_check_id}")
            if (
                str(trigger["scope"]) != QUALITY_SCOPE_SEGMENT
                or str(trigger["stage"]) != SEGMENT_AUDIO_QUALITY_STAGE
                or int(trigger["segment_id"] or -1) != int(segment_id)
                or str(trigger["artifact_sha256"]).casefold() != normalized_incumbent
                or str(trigger["policy_hash"]) != str(policy_hash).strip()
                or str(trigger["verdict"]) != "repair"
            ):
                raise RuntimeError("repair trigger does not belong to the retained incumbent artifact")
            trigger_metrics = self._json_object(trigger["metrics_json"], "repair trigger metrics")
            try:
                trigger_failure_codes = json.loads(str(trigger["failure_codes_json"] or "[]"))
            except (TypeError, json.JSONDecodeError):
                trigger_failure_codes = []
            merged_failure_codes: list[str] = []
            for code in [*trigger_failure_codes, *requested_failure_codes]:
                normalized_code = str(code).strip()
                if normalized_code and normalized_code not in merged_failure_codes:
                    merged_failure_codes.append(normalized_code)
            summaries = [self._candidate_summary(row) for row in candidates]
            final_metrics = {
                **trigger_metrics,
                "repair_exhausted": True,
                "repair_trigger_quality_check_id": int(trigger_quality_check_id),
                "candidate_rounds_configured": normalized_max,
                "candidate_attempts": summaries,
                "incumbent_sha256": normalized_incumbent,
                "repair_exhaustion_verdict": normalized_verdict,
                "repair_exhaustion_error": normalized_error,
                "repair_exhaustion_warning_code": normalized_warning_code,
                "repair_exhaustion_failure_codes": merged_failure_codes,
            }
            final_metrics_json = json.dumps(final_metrics, ensure_ascii=False, sort_keys=True)
            failure_codes_json = json.dumps(merged_failure_codes, ensure_ascii=False)
            existing = list(
                conn.execute(
                    """
                    SELECT * FROM quality_checks
                    WHERE scope=? AND stage=? AND segment_id=? AND artifact_sha256=?
                      AND policy_hash=?
                    ORDER BY id DESC
                    """,
                    (
                        QUALITY_SCOPE_SEGMENT,
                        SEGMENT_AUDIO_QUALITY_STAGE,
                        int(segment_id),
                        normalized_incumbent,
                        str(policy_hash).strip(),
                    ),
                )
            )
            for check in existing:
                metrics = self._json_object(check["metrics_json"], "existing repair exhaustion metrics")
                if (
                    bool(metrics.get("repair_exhausted", False))
                    and int(metrics.get("repair_trigger_quality_check_id", -1))
                    == int(trigger_quality_check_id)
                ):
                    if (
                        str(check["verdict"]) == normalized_verdict
                        and str(check["metrics_json"]) == final_metrics_json
                        and str(check["failure_codes_json"]) == failure_codes_json
                        and str(check["repair_action"] or "")
                        == SEGMENT_CANDIDATE_EXHAUSTION_ACTION
                    ):
                        return int(check["id"])
                    raise RuntimeError("repair exhaustion replay payload differs")
            attempt_row = conn.execute(
                """
                SELECT MAX(attempt) FROM quality_checks
                WHERE scope=? AND stage=? AND segment_id=? AND policy_hash=?
                """,
                (
                    QUALITY_SCOPE_SEGMENT,
                    SEGMENT_AUDIO_QUALITY_STAGE,
                    int(segment_id),
                    str(policy_hash).strip(),
                ),
            ).fetchone()
            attempt = int(attempt_row[0] or 0) + 1
            cursor = conn.execute(
                """
                INSERT INTO quality_checks(
                    scope,stage,segment_id,chapter_id,artifact_sha256,
                    policy_hash,policy_version,verdict,metrics_json,
                    failure_codes_json,repair_action,attempt,created_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    QUALITY_SCOPE_SEGMENT,
                    SEGMENT_AUDIO_QUALITY_STAGE,
                    int(segment_id),
                    None,
                    normalized_incumbent,
                    str(policy_hash).strip(),
                    int(policy["policy_version"]),
                    normalized_verdict,
                    final_metrics_json,
                    failure_codes_json,
                    SEGMENT_CANDIDATE_EXHAUSTION_ACTION,
                    attempt,
                    time.time(),
                ),
            )
            retained_warning = self._without_audio_attempt_warnings(
                str(segment["warning_code"]) if segment["warning_code"] else None
            )
            merged_warning = self._merge_warning_codes(retained_warning, normalized_warning_code)
            segment_cursor = conn.execute(
                """
                UPDATE segments SET status=?,asr_text=?,asr_similarity=?,asr_wer=?,
                    warning_code=?,error=?,updated_at=?
                WHERE id=? AND wav_sha256=?
                """,
                (
                    SegmentStatus.FAILED.value,
                    str(trigger_metrics.get("transcript", "")),
                    float(trigger_metrics.get("similarity", 0.0)),
                    float(trigger_metrics.get("wer", 1.0)),
                    merged_warning,
                    normalized_error,
                    time.time(),
                    int(segment_id),
                    normalized_incumbent,
                ),
            )
            if segment_cursor.rowcount != 1:
                raise RuntimeError("repair exhaustion lost the incumbent CAS")
            self._refresh_chapter_counts_conn(conn, int(segment["chapter_id"]))
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

    def latest_segment_quality_checks(
        self,
        stage: str,
        *,
        current_policy_only: bool = True,
    ) -> dict[int, sqlite3.Row]:
        normalized_stage = str(stage).strip()
        if not normalized_stage:
            raise ValueError("segment quality lookup stage must not be empty")
        policy_clause = " AND quality_policies.active=1" if current_policy_only else ""
        with self.connect() as conn:
            rows = conn.execute(
                f"""
                SELECT quality_checks.*
                FROM quality_checks
                JOIN quality_policies
                  ON quality_policies.policy_hash=quality_checks.policy_hash
                 AND quality_policies.policy_version=quality_checks.policy_version
                WHERE quality_checks.scope=?
                  AND quality_checks.stage=?
                  {policy_clause}
                ORDER BY quality_checks.id
                """,
                (QUALITY_SCOPE_SEGMENT, normalized_stage),
            )
            latest: dict[int, sqlite3.Row] = {}
            for row in rows:
                if row["segment_id"] is not None:
                    latest[int(row["segment_id"])] = row
            return latest

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
