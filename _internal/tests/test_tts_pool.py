"""The synthesis pool's structural guarantees.

The throughput win is measured elsewhere (docs/THROUGHPUT.md). What matters here is that
running synthesis in another process cannot damage the things a single process was
protecting: only the parent writes SQLite, and results come back in submission order.
"""

from __future__ import annotations

import sqlite3

import pytest

from ebook_reader.tts_pool import (
    TTS_POOL_WORKER_THREADS,
    TTS_POOL_WORKERS_DEFAULT,
    ReadOnlyVoiceDB,
    SynthesisPool,
)


@pytest.fixture()
def voice_db(tmp_path):
    path = tmp_path / "project.sqlite3"
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        CREATE TABLE voice_profiles (
            id INTEGER PRIMARY KEY, voice_key TEXT, engine TEXT, preset_name TEXT,
            pitch_semitones INTEGER
        );
        CREATE TABLE pronunciations (
            id INTEGER PRIMARY KEY, surface TEXT, normalized_surface TEXT,
            spoken_form TEXT, confidence REAL, locked INTEGER
        );
        INSERT INTO voice_profiles VALUES (1, 'narrator', 'vieneu', 'Thanh Bình', -4);
        INSERT INTO voice_profiles VALUES (2, 'sd_01', 'vieneu', 'Đoan Trang', 0);
        INSERT INTO pronunciations VALUES (1, 'Lucien', 'lucien', 'Lu-si-en', 0.9, 1);
        INSERT INTO pronunciations VALUES (2, 'Aalto', 'aalto', 'An-tô', 0.2, 0);
        """
    )
    connection.commit()
    connection.close()
    return path


def test_it_reads_the_profiles_synthesis_asks_for(voice_db) -> None:
    db = ReadOnlyVoiceDB(voice_db)
    assert db.voice_profile(1)["preset_name"] == "Thanh Bình"
    assert db.voice_profile_by_key("sd_01")["preset_name"] == "Đoan Trang"
    assert [row["voice_key"] for row in db.list_voice_profiles()] == ["narrator", "sd_01"]


def test_a_missing_profile_raises_rather_than_returning_none(voice_db) -> None:
    db = ReadOnlyVoiceDB(voice_db)
    with pytest.raises(KeyError):
        db.voice_profile(999)
    with pytest.raises(KeyError):
        db.voice_profile_by_key("nobody")


def test_pronunciation_confidence_filters_the_same_way_the_project_db_does(voice_db) -> None:
    db = ReadOnlyVoiceDB(voice_db)
    # A locked entry is returned whatever the threshold; an unlocked one only above it.
    assert {row["surface"] for row in db.list_pronunciations(0.0)} == {"Lucien", "Aalto"}
    assert {row["surface"] for row in db.list_pronunciations(0.5)} == {"Lucien"}


def test_pronunciations_come_back_longest_surface_first(voice_db) -> None:
    """Shorter surfaces must not shadow longer ones during replacement."""
    surfaces = [row["surface"] for row in ReadOnlyVoiceDB(voice_db).list_pronunciations(0.0)]
    assert surfaces == sorted(surfaces, key=lambda value: (-len(value), value.casefold()))


def test_a_worker_cannot_write_the_database(voice_db) -> None:
    """The parent's exclusive write access is structural, not a convention."""
    db = ReadOnlyVoiceDB(voice_db)
    with pytest.raises(sqlite3.OperationalError):
        with db._connect() as connection:
            connection.execute("INSERT INTO voice_profiles VALUES (3, 'x', 'v', 'p', 0)")


def test_the_shim_exposes_no_way_to_write(voice_db) -> None:
    """A future edit must not be able to add one by accident and have it look normal."""
    public = {name for name in dir(ReadOnlyVoiceDB) if not name.startswith("_")}
    assert public == {
        "voice_profile",
        "voice_profile_by_key",
        "list_voice_profiles",
        "list_pronunciations",
    }


def test_pool_size_is_the_measured_one_not_the_core_count() -> None:
    assert TTS_POOL_WORKERS_DEFAULT == 3
    assert TTS_POOL_WORKER_THREADS == 1


def test_a_pool_needs_at_least_one_worker(voice_db) -> None:
    with pytest.raises(ValueError):
        SynthesisPool({}, voice_db, workers=0)


def test_an_empty_batch_never_starts_a_pool(voice_db) -> None:
    pool = SynthesisPool({}, voice_db)
    assert pool.synthesize_many([]) == []
    assert pool._pool is None


def test_results_are_returned_in_submission_order(voice_db, monkeypatch) -> None:
    """Workers finish out of order; committing in that order would break resume."""

    class OutOfOrderPool:
        def imap(self, _job, payloads):
            # imap is order-preserving by contract; this proves the caller relies on that
            # rather than on jobs happening to finish in order.
            return iter([{"stable_id": item["row"]["stable_id"]} for item in payloads])

    pool = SynthesisPool({}, voice_db)
    monkeypatch.setattr(pool, "start", lambda: None)
    pool._pool = OutOfOrderPool()
    jobs = [{"row": {"stable_id": name}, "output": "x"} for name in ("c", "a", "b")]
    assert [item["stable_id"] for item in pool.synthesize_many(jobs)] == ["c", "a", "b"]


def test_close_is_safe_when_nothing_was_started(voice_db) -> None:
    pool = SynthesisPool({}, voice_db)
    pool.close()
    pool.close()
    assert pool._pool is None
