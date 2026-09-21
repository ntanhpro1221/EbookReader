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
from collections import Counter
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
    parser.add_argument("--no-think", action="store_true",
                        help='gửi "think": false trong mọi yêu cầu Ollama (dòng qwen3/qwen3.5 nghĩ trước và trả 0 ID)')
    parser.add_argument("--no-mention-counts", action="store_true",
                        help="bỏ `số lần đã gặp` khỏi danh sách nhân vật đã biết và xếp theo TÊN thay vì theo "
                             "độ nổi tiếng - phép thử cho giả thuyết prompt tự gây thiên lệch (xem docs/LLM_EVAL.md)")
    parser.add_argument("--known-sorted-by-name", action="store_true",
                        help="GIỮ `số lần đã gặp` nhưng xếp theo TÊN - tách riêng ảnh hưởng của THỨ TỰ, "
                             "độ dài prompt gần như không đổi")
    parser.add_argument("--masked-mention-counts", action="store_true",
                        help="GIỮ thứ tự theo độ nổi tiếng nhưng thay mọi con số bằng `?` - tách riêng ảnh "
                             "hưởng của CON SỐ, độ dài prompt gần như không đổi")
    args = parser.parse_args(argv)
    variants = [args.no_mention_counts, args.known_sorted_by_name, args.masked_mention_counts]
    if sum(bool(flag) for flag in variants) > 1:
        parser.error("chỉ được một biến thể danh sách nhân vật mỗi lượt - nếu không thì đo hai thứ cùng lúc")

    if args.known_sorted_by_name or args.masked_mention_counts:
        # Hai biến thể TÁCH NHIỄU cho giả thuyết ở `docs/LLM_EVAL.md`. `--no-mention-counts` bỏ cả con số
        # lẫn thứ tự VÀ ~500 token, nên nếu nó thắng thì chưa biết nửa nào công. Hai cờ này giữ độ dài
        # prompt gần như nguyên: một cái chỉ đổi thứ tự, một cái chỉ xoá con số.
        by_name = bool(args.known_sorted_by_name)

        def _known_summary_variant(self) -> str:
            if not self._speaker_counts:
                return "(Chưa có nhân vật đã biết)"
            top = self._speaker_counts.most_common(80)
            if by_name:
                top = sorted(top, key=lambda pair: str(pair[0]).casefold())
            lines = []
            for name, count in top:
                genders = self._speaker_genders.get(name, Counter())
                locked_gender = genders.most_common(1)[0][0] if genders else "unknown"
                shown = count if by_name else "?"
                lines.append(f"- {name}; số lần đã gặp={shown}; gender đã biết={locked_gender}")
            return "\n".join(lines)

        OllamaBookAnalyzer._known_summary = _known_summary_variant

    if args.no_mention_counts:
        # Đo trên 3 model của lượt 21-09: khi model chọn SAI một nhân vật có tên, nhân vật ấy nằm ở top
        # 2-10% bảng độ nổi tiếng (hạng tương đối 0,02-0,10), còn khi chọn ĐÚNG thì 0,21-0,25. Prompt đưa
        # cho model đúng bảng xếp hạng ấy - cả con số lẫn thứ tự - trong khi luật của prompt chỉ đòi nhất
        # quán TÊN và GIỚI TÍNH. Cờ này bỏ con số và xếp theo tên, để xem lỗi có giảm hay không.
        # Đổi prompt KHÔNG đo được bằng phát lại, nên chỉ có đường chạy GPU thật.
        def _known_summary_without_counts(self) -> str:
            if not self._speaker_counts:
                return "(Chưa có nhân vật đã biết)"
            # Giữ ĐÚNG mức chặn 80 của bản gốc: chọn 80 người theo số lần gặp rồi mới xếp theo tên. Bỏ
            # mức chặn là đổi cả độ dài prompt, tức đo hai thứ cùng lúc.
            top = [name for name, _count in self._speaker_counts.most_common(80)]
            lines = []
            for name in sorted(top, key=lambda value: str(value).casefold()):
                genders = self._speaker_genders.get(name, Counter())
                locked_gender = genders.most_common(1)[0][0] if genders else "unknown"
                lines.append(f"- {name}; gender đã biết={locked_gender}")
            return "\n".join(lines)

        OllamaBookAnalyzer._known_summary = _known_summary_without_counts

    if args.no_think:
        original = OllamaBookAnalyzer._stream_json_response

        def without_thinking(self, request, **kwargs):
            return original(self, {**request, "think": False}, **kwargs)

        OllamaBookAnalyzer._stream_json_response = without_thinking

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
