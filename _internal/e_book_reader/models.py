from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any


class BookStatus(StrEnum):
    CREATED = "created"
    ANALYZING = "analyzing"
    ANALYZED = "analyzed"
    CASTING = "casting"
    SYNTHESIZING = "synthesizing"
    VERIFYING = "verifying"
    COMPLETED = "completed"
    PAUSED = "paused"
    STOPPED = "stopped"
    ERROR = "error"
    RECOVERY_REQUIRED = "recovery_required"


class ChapterStatus(StrEnum):
    PENDING = "pending"
    ANALYZING = "analyzing"
    ANALYZED = "analyzed"
    SYNTHESIZING = "synthesizing"
    VERIFYING = "verifying"
    COMPLETED = "completed"
    WARNING = "warning"
    FAILED = "failed"


class SegmentStatus(StrEnum):
    PENDING = "pending"
    ANALYZED = "analyzed"
    GENERATING = "generating"
    SIGNAL_PASSED = "signal_passed"
    ASR_PASSED = "asr_passed"
    VERIFIED = "verified"
    WARNING = "warning"
    FAILED = "failed"


class ResourceLevel(StrEnum):
    MAXIMUM = "maximum"
    YIELD_LIGHT = "yield_light"
    YIELD_HEAVY = "yield_heavy"
    PAUSE_NEW_WORK = "pause_new_work"
    CRITICAL_STOP = "critical_stop"


@dataclass(slots=True)
class ResourceDecision:
    level: ResourceLevel
    reason: str
    cpu_workers_scale: float = 1.0
    gpu_batch_scale: float = 1.0
    allow_new_gpu_batch: bool = True
    allow_cpu_heavy_work: bool = True
    unload_idle_models: bool = False
    critical: bool = False


@dataclass(slots=True)
class ProjectPaths:
    root: Path
    db: Path
    settings: Path
    logs: Path
    work: Path
    chunks: Path
    voices: Path
    chapters: Path
    output: Path
    reports: Path

    @classmethod
    def build(cls, root: Path) -> "ProjectPaths":
        obj = cls(
            root=root,
            db=root / "project.sqlite3",
            settings=root / "book_settings.json",
            logs=root / "logs",
            work=root / "work",
            chunks=root / "work" / "chunks",
            voices=root / "work" / "voices",
            chapters=root / "output" / "chapters",
            output=root / "output",
            reports=root / "output" / "reports",
        )
        for path in (obj.root, obj.logs, obj.work, obj.chunks, obj.voices, obj.chapters, obj.output, obj.reports):
            path.mkdir(parents=True, exist_ok=True)
        return obj


@dataclass(slots=True)
class RuntimeEvent:
    level: str
    code: str
    message: str
    details: dict[str, Any] | None = None
