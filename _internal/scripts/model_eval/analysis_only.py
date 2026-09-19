r"""Chạy RIÊNG khâu phân tích của một project nháp, đúng mã sản xuất, rồi dừng trước khâu phân vai.

    python scripts/model_eval/analysis_only.py <project>                  # chia đoạn + phân tích
    python scripts/model_eval/analysis_only.py <project> --segment-only   # chỉ chia đoạn

Dựng đúng như `worker.run_worker` + `BookPipeline.run` cho tới hết `reconcile_name_pronunciations`:
settings khoá của project, chia đoạn bằng `load_and_segment_chapter`, `OllamaBookAnalyzer` với
`quality_policy_hash` của chính settings ấy, rồi hai lượt hoà giải (danh tính NPC, cách đọc tên).
KHÔNG gọi `build_registry_and_cast`, KHÔNG nạp VieNeu/Whisper - nên không đụng giọng hay GPU của TTS.

Khác sản xuất đúng hai chỗ, đều không đổi một câu hỏi nào gửi Ollama:
  - `before_batch` là no-op: cổng tài nguyên của pipeline chỉ nhả model khi RAM/VRAM căng, và lúc
    đo không có gì khác chạy;
  - không có luồng nhịp tim `worker_leases` - đây không phải một lượt `run`, và các script theo dõi
    của sách không nhìn vào `_model_eval`.

Kết quả thời gian ghi vào `<project>/model_eval_run.json`; số liệu Ollama từng lượt ghi trong
`logs/ebook_reader.log` như sản xuất, đọc bằng `scripts/ollama_usage.py`.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ebook_reader.analysis import OllamaBookAnalyzer  # noqa: E402
from ebook_reader.database import ProjectDB  # noqa: E402
from ebook_reader.models import BookStatus, ProjectPaths  # noqa: E402
from ebook_reader.quality_policy import (  # noqa: E402
    QUALITY_POLICY_VERSION,
    build_quality_policy,
    quality_policy_hash,
)
from ebook_reader.text_processing import load_and_segment_chapter  # noqa: E402
from ebook_reader.worker import ProjectRunLock, _configure_logging, _load_locked_settings  # noqa: E402


def segment(db: ProjectDB, settings: dict, log) -> int:
    """`BookPipeline._ensure_segments` không kèm kiểm nguồn và thanh tiến độ."""
    max_chars = int(settings["tts"]["max_segment_chars"])
    made = 0
    for chapter in db.list_chapters():
        if int(chapter["total_segments"]) > 0:
            continue
        warnings: list[str] = []
        rows = load_and_segment_chapter(dict(chapter), max_chars=max_chars, warnings=warnings)
        if not rows:
            raise RuntimeError(f"Chapter has no readable content: {chapter['input_path']}")
        db.replace_chapter_segments(int(chapter["id"]), rows)
        for warning in warnings:
            log(f"NGUỒN HỎNG, ĐÃ TỰ PHỤC HỒI — {warning}")
        log(f"Đã chia {chapter['title']} thành {len(rows):,} segment.")
        made += len(rows)
    return made


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("project", type=Path)
    parser.add_argument("--segment-only", action="store_true")
    args = parser.parse_args(argv)

    paths = ProjectPaths.build(args.project.resolve())
    lock = ProjectRunLock(paths.root / ".worker.lock")
    lock.acquire()
    _configure_logging(paths.logs / "ebook_reader.log")
    db = ProjectDB(paths.db, synchronous="FULL")
    settings = _load_locked_settings(paths, db)
    policy = build_quality_policy(settings)
    policy_hash = quality_policy_hash(policy)

    def log(message: str) -> None:
        db.event("info", "LOG", message)
        logging.info("EVENT log %s", {"text": message})
        print(message, flush=True)

    db.set_current_quality_policy(policy_hash=policy_hash, policy_version=QUALITY_POLICY_VERSION, policy=policy)
    db.begin_run_generation()
    segment(db, settings, log)
    if args.segment_only:
        print(f"đã chia đoạn: {len(db.list_segments())} đoạn")
        return 0

    db.update_book(status=BookStatus.ANALYZING.value, stage="full_book_analysis")
    analyzer = OllamaBookAnalyzer(settings, db, log, quality_policy_hash=policy_hash)
    timings: dict[str, float] = {}

    def never() -> bool:
        return False

    def progress(done: int, total: int) -> None:
        if done == total or done % 25 == 0:
            print(f"  phân tích {done}/{total}", flush=True)

    try:
        started = time.perf_counter()
        analyzer.analyze_all(never, progress=progress, before_batch=lambda _index: None)
        timings["analyze_all"] = time.perf_counter() - started
        started = time.perf_counter()
        analyzer.reconcile_local_speaker_identities(before_batch=lambda _index: None, stop_requested=never)
        timings["local_identities"] = time.perf_counter() - started
        started = time.perf_counter()
        analyzer.reconcile_name_pronunciations(before_batch=lambda _index: None, stop_requested=never)
        timings["name_pronunciations"] = time.perf_counter() - started
    finally:
        analyzer.unload()
    db.update_book(status=BookStatus.CASTING.value, stage="model_eval_analysis_done")
    record = {
        "model": str(settings["analysis"]["model"]),
        "segments": len(db.list_segments()),
        "seconds": {key: round(value, 1) for key, value in timings.items()},
        "total_seconds": round(sum(timings.values()), 1),
        "finished_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    (paths.root / "model_eval_run.json").write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(record, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
