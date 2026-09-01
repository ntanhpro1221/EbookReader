"""Run VieNeu synthesis in worker processes, so the GPU is not idle between segments.

VieNeu decodes autoregressively: every step is a small matmul that depends on the previous
one, so a single stream leaves the GPU at 23% no matter how fast the card is. Measured on
48 real segments, three worker processes reach 2.16x and take the GPU to 90%
(docs/THROUGHPUT.md). Threads cannot do this: _set_generation_seed seeds process-global
RNG, so two concurrent generations in one process would make a segment's audio depend on
its neighbours and destroy deterministic resume. Separate processes each own their RNG, and
the benchmark confirms byte-identical output at every pool size.

Two invariants shape the design:

- Only the parent writes SQLite. A worker is given ReadOnlyVoiceDB, which can answer the
  four questions synthesis asks and cannot do anything else. That is structural rather than
  a rule someone has to remember: there is no write method to call by mistake, and the
  connection is opened mode=ro so SQLite would refuse one anyway.
- A worker writes only its own output path. synthesize_atomic already writes through a
  temporary file and renames, so a crashed worker leaves no half-written WAV for the parent
  to mistake for a finished one.
"""

from __future__ import annotations

import multiprocessing as mp
import os
import sqlite3
from pathlib import Path
from typing import Any

TTS_POOL_WORKERS_DEFAULT = 3
"""Three, from measurement rather than from the core count.

Five workers were 1.3% faster and held 7318 of 8151 MiB, leaving no room for the foreground
or for keeping Whisper resident; three hold 5484 MiB at 90% GPU. See docs/THROUGHPUT.md.
"""

TTS_POOL_MIN_BATCH = 3
"""Below this many segments the pool is pure cost, measured warm and twice.

Two segments came out at 1.03x and 1.00x - no gain at all - while holding 3291 MiB
against the single worker's 1059. Three reproduces 1.12x, four 1.22x, nine 1.29x. The
first measurement of two segments said 2.54x and was the benchmark's own cold start:
two jobs appeared to take 35.4 s while four took 18.7 s, which is the model file
reaching the OS cache, not the pool being fast.
"""

TTS_POOL_WORKER_THREADS = 1
"""Torch claims one thread per core by default, so N workers ask for N x cores and spend the
difference context switching. The perceptual pool measured 4 workers at 1.66x unpinned and
3.08x pinned; a pool size is only meaningful once each member is bounded."""


class ReadOnlyVoiceDB:
    """The four reads synthesis needs, and nothing else.

    ProjectDB cannot be used here: its constructor runs the schema script, so merely
    building one in a worker would write to the database the parent owns.
    """

    def __init__(self, path: Path) -> None:
        self.path = Path(path)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(
            f"file:{self.path.as_posix()}?mode=ro",
            uri=True,
            timeout=30.0,
        )
        connection.row_factory = sqlite3.Row
        return connection

    def voice_profile(self, profile_id: int) -> sqlite3.Row:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM voice_profiles WHERE id=?", (int(profile_id),)
            ).fetchone()
        if row is None:
            raise KeyError(profile_id)
        return row

    def voice_profile_by_key(self, voice_key: str) -> sqlite3.Row:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM voice_profiles WHERE voice_key=?", (str(voice_key),)
            ).fetchone()
        if row is None:
            raise KeyError(voice_key)
        return row

    def list_voice_profiles(self) -> list[sqlite3.Row]:
        with self._connect() as connection:
            return list(connection.execute("SELECT * FROM voice_profiles ORDER BY id"))

    def list_pronunciations(self, minimum_confidence: float = 0.0) -> list[sqlite3.Row]:
        with self._connect() as connection:
            return list(
                connection.execute(
                    """
                    SELECT * FROM pronunciations
                    WHERE locked=1 OR confidence>=?
                    ORDER BY LENGTH(surface) DESC, normalized_surface
                    """,
                    (float(minimum_confidence),),
                )
            )


_COORDINATOR: list[Any] = []


def _worker_init(settings: dict[str, Any], database_path: str) -> None:
    import torch

    from .tts import TTSCoordinator

    torch.set_num_threads(
        max(1, int(os.environ.get("EBOOK_READER_WORKER_THREADS", TTS_POOL_WORKER_THREADS)))
    )
    coordinator = TTSCoordinator(
        settings,
        ReadOnlyVoiceDB(Path(database_path)),
        lambda _message: None,
    )
    coordinator.vieneu.load()
    _COORDINATOR.append(coordinator)


def _worker_job(payload: dict[str, Any]) -> dict[str, Any]:
    """Synthesize one segment, or report why it could not be synthesized.

    Failures are returned rather than raised so one bad segment cannot take the pool down
    with it. The parent re-raises in its own process, where the retry, split and quality
    machinery already lives; none of that is duplicated here.
    """
    coordinator = _COORDINATOR[0]
    row = dict(payload["row"])
    try:
        checksum, metrics, seed = coordinator.synthesize_atomic(
            row,
            Path(payload["output"]),
            payload.get("seed_salt", ""),
            **payload.get("kwargs", {}),
        )
    except Exception as exc:  # noqa: BLE001 - carried to the parent verbatim
        return {"stable_id": row.get("stable_id"), "error": f"{type(exc).__name__}: {exc}"}
    return {
        "stable_id": row.get("stable_id"),
        "checksum": checksum,
        "metrics": metrics,
        "seed": int(seed),
    }


class SynthesisPool:
    """A pool of synthesis workers, sized by measurement and restartable.

    Each worker caches pronunciations the first time it synthesizes, exactly as the inline
    coordinator does. When the parent learns a new pronunciation it must call restart(): a
    worker holding the old map would read a name one way while the parent believes it is
    read another, breaking "the same name never changes pronunciation" across a process
    boundary instead of across a chapter.
    """

    def __init__(
        self,
        settings: dict[str, Any],
        database_path: Path,
        workers: int = TTS_POOL_WORKERS_DEFAULT,
    ) -> None:
        if int(workers) < 1:
            raise ValueError("SynthesisPool needs at least one worker")
        self.settings = settings
        self.database_path = Path(database_path)
        self.workers = int(workers)
        self._pool: Any = None

    def start(self) -> None:
        if self._pool is not None:
            return
        context = mp.get_context("spawn")
        self._pool = context.Pool(
            processes=self.workers,
            initializer=_worker_init,
            initargs=(self.settings, str(self.database_path)),
        )

    def close(self) -> None:
        pool, self._pool = self._pool, None
        if pool is None:
            return
        pool.close()
        pool.join()

    def restart(self) -> None:
        self.close()
        self.start()

    def synthesize_many(self, jobs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Synthesize a batch and return the results in the order the jobs were given.

        Order is restored, not merely hoped for: workers finish out of order, and a caller
        that committed results in completion order would write segments to the database in
        an order that depends on timing. Resume compares what is committed against what the
        analysis says should be there, so that alone would make a resumed run diverge.
        """
        if not jobs:
            return []
        self.start()
        return list(self._pool.imap(_worker_job, jobs))

    def __enter__(self) -> SynthesisPool:
        self.start()
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()
