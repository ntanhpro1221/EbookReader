"""Giữ cách đọc ghim cho những đoạn ĐÃ LÊN SÁCH: đề cử lại bản đọc-ghim rồi ghép lại chương.

    python scripts/keep_the_locked_reading.py <project> [<project> ...]   # thử: chỉ liệt kê
    python scripts/keep_the_locked_reading.py <project> --apply           # làm thật
    python scripts/keep_the_locked_reading.py --book [--apply]            # mọi project manifest.json của sách ghi

Vì sao có script này. Đo 2026-09-11 trên cuốn sách 92 chương đã ghép: 716 đoạn đi qua vòng sửa
ASR, và **348 (48%) được đề cử bản đọc tên theo chữ viết** (`Jake`, `Ishtara`) thay vì cách đọc
đã ghim (`Giếch`, `I-xờ-hờ-ta-ra`) - Jake 79 lần, Michael 35, Spirit 31. Cả 348 bản đọc-ghim
anh em đều còn WAV trên đĩa, qua cổng nhịp, và thua **chỉ** bài chính tả neo tên
(`ASR_LOCKED_NAME_ANCHOR_MISMATCH`) trên cả hai đường phiên. Người nghe nghe `Giếch` ở đoạn
này và `Jake` ở đoạn kế, tuỳ Whisper trượt ở đâu.

`patch_keep_the_locked_reading` dạy vòng sửa giữ cách đọc ghim cho các lô về sau. Những chương
đã đúc rồi thì bản vá không chạm tới - chúng chỉ được sửa khi có ai đề cử lại bản đọc-ghim và
ghép lại chương. Đó là việc của script này, và nó **không cần GPU**: mọi đoạn của một chương đã
hoàn thành đều đã có bằng chứng QA hiện hành, nên đuôi của `_process_chapter` chỉ còn ffmpeg.

Nó làm gì, theo thứ tự, cho từng chương:

  1. `find_locked_reading_that_lost_only_the_spelling_test` cho từng đoạn - năm điều kiện nằm
     ở `database`, script chỉ hỏi.
  2. `_keep_the_locked_reading(item)` của đường ống - **cùng một đường** vòng sửa dùng, nên
     phán quyết máy, sổ thay thế, cổng file và provenance đều giống hệt lô mới.
  3. Đánh dấu artifact MP3 của chương hết hiệu lực (`verified=0`, có lý do trong metadata):
     từ lúc này cả `cli run` lẫn `recover_project` đều biết chương phải ghép lại.
  4. Gọi `_publish_verified_chapter` - đuôi của `_process_chapter` sau mọi đường thu lại: cấp
     phép máy, ba cổng chặn, ffmpeg, sổ chất lượng chương, artifact, hoàn thành - trên một thể
     hiện đường ống **bị rào đường tổng hợp**: có đi tới chỗ thu lại là script ném chứ không
     bao giờ lặng lẽ nạp VieNeu bên cạnh một lô đang chạy.

Nó từ chối khi project đang chạy, và khi cây mã chưa có bản vá (không có gì để gọi).

Sau khi chạy xong với --apply:  python scripts/assemble_book.py --apply
(`assemble_book` chép lại chương khi kích thước MP3 đổi; một chương ghép lại mà tình cờ bằng
đúng số byte cũ sẽ bị bỏ qua - xác suất rất nhỏ, nhưng nếu nghi thì xoá file đích rồi chép lại.)
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ebook_reader.audio_io import AudioQualityError  # noqa: E402
from ebook_reader.background_runner import get_status  # noqa: E402
from ebook_reader.cli import _open_project  # noqa: E402
from ebook_reader.models import ChapterStatus, SegmentStatus  # noqa: E402
from ebook_reader.notifier import WindowsNotifier  # noqa: E402
from ebook_reader.perceptual_qa import UTMOSNaturalnessVerifier  # noqa: E402
from ebook_reader.pipeline import BookPipeline  # noqa: E402
from ebook_reader.quality_policy import QUALITY_POLICY_VERSION, quality_policy_hash  # noqa: E402
from ebook_reader.resource_manager import AdaptiveResourceManager  # noqa: E402
from ebook_reader.tts import TTSCoordinator  # noqa: E402

BOOK = Path("D:/Novels/Audiobooks/_book")
VERSIONS = Path("D:/Novels/Audiobooks/_versions")


def _say(line: str) -> None:
    try:
        print(line, flush=True)
    except (UnicodeEncodeError, OSError, ValueError):
        sys.stdout.buffer.write(line.encode("utf-8", "replace") + b"\n")


def _fence(what: str) -> Any:
    """Một hàm đứng chỗ đường tổng hợp: gọi tới nó là có đoạn cần thu lại, việc của `cli run`."""

    def refuse(*_args: Any, **_kwargs: Any) -> Any:
        raise RuntimeError(
            f"script giữ cách đọc ghim không tổng hợp audio (đường ống gọi {what}); "
            "chương này có đoạn cần thu lại - chạy `cli run` khi GPU rảnh"
        )

    return refuse


def bare_pipeline(paths: Any, db: Any, settings: dict[str, Any]) -> BookPipeline:
    """Một `BookPipeline` đủ để ghép lại chương, dựng như `refresh_terminal_reports_without_runtime`.

    Bỏ qua `__init__` vì nó dựng `TTSCoordinator` (và qua đó VieNeuEngine). Mọi thuộc tính khác
    của `__init__` được đặt y nguyên, để `_process_chapter`, `_resource_gate`, và
    `_grant_machine_acceptances` chạy đúng mã của chúng chứ không phải một bản chép.
    """
    pipeline = object.__new__(BookPipeline)
    pipeline.paths = paths
    pipeline.db = db
    pipeline.settings = settings
    pipeline.pause_requested = lambda: False
    pipeline.stop_requested = lambda: False
    pipeline.emit = lambda _kind, _payload: None
    pipeline.resource_updates = None
    pipeline.resources = AdaptiveResourceManager(settings, paths.root)
    pipeline.notifier = WindowsNotifier()
    # `TTSCoordinator` thật, vì đường ống hỏi nó cả về VĂN BẢN (`spoken_text_with_anchors`: cách
    # đọc ghim của từng đoạn) chứ không chỉ về audio; VieNeuEngine chỉ nạp model khi `load()`.
    # Rào đúng chỗ nạp model và mọi lối vào tổng hợp: có đi tới đó là có đoạn cần thu lại, và
    # script này không bao giờ lặng lẽ nạp VieNeu bên cạnh một lô đang bay.
    pipeline.tts = TTSCoordinator(settings, db, pipeline.log)
    pipeline.tts.vieneu.load = _fence("VieNeuEngine.load")
    for entry in (
        "_process_single_segment",
        "_prefetch_segment_batch",
        "_prefetch_candidate_batch",
        "_synthesize_atomic_with_pronunciation_variant",
        "_synthesize_split",
    ):
        setattr(pipeline, entry, _fence(f"BookPipeline.{entry}"))
    pipeline._tts_pool = None
    pipeline._tts_pool_failed = True
    pipeline.perceptual_qa = UTMOSNaturalnessVerifier(settings, pipeline.log)
    pipeline._perceptual_prefetch = None
    pipeline._last_resource_level = None
    pipeline._completed_noop = False
    pipeline._last_tts_failure_signature = None
    pipeline._tts_failure_streak = 0
    # Chính sách chất lượng của PROJECT, không phải của cây mã hiện tại. `implementation_hash`
    # nằm trong chính sách, nên mỗi bản vá đã áp từ lúc chương được đúc đổi mã băm ấy (đo
    # 18:25 2026-09-11 trên lo03r_084b: c7d785… theo cây mã, 054f8c… trong project). Với mã
    # băm của cây mã thì không ứng viên nào "thuộc chính sách đang hoạt động", không bằng
    # chứng nào là hiện hành, và MP3 mới cũng không. Lượt này ghép lại chương dưới đúng chính
    # sách chương ấy được đúc; nó không gọi `set_current_quality_policy`.
    active = db.current_quality_policy()
    if active is None:
        raise RuntimeError("project chưa khoá chính sách chất lượng nào")
    pipeline.quality_policy = json.loads(str(active["policy_json"]))
    pipeline.quality_policy_hash = str(active["policy_hash"])
    if quality_policy_hash(pipeline.quality_policy) != pipeline.quality_policy_hash:
        raise RuntimeError("chính sách lưu trong project không băm ra đúng mã của nó")
    if int(active["policy_version"]) != int(QUALITY_POLICY_VERSION):
        # Cổng ghép chương ghi `policy_version` của cây mã; lệch phiên bản là một chính sách
        # khác về cấu trúc, không chỉ khác mã băm - lượt này không dựng lại được nó.
        raise RuntimeError(
            f"project khoá chính sách phiên bản {active['policy_version']}, cây mã là "
            f"{QUALITY_POLICY_VERSION} - chạy `cli run` để đúc lại dưới chính sách mới"
        )
    return pipeline


def survey(db: Any, policy_hash: str) -> dict[int, list[tuple[dict[str, Any], dict[str, Any]]]]:
    """{chapter_id: [(đoạn, ứng viên đọc-ghim)]} - chỉ những đoạn có bản đọc-ghim đủ điều kiện."""
    found: dict[int, list[tuple[dict[str, Any], dict[str, Any]]]] = {}
    for row in db.list_segments():
        if str(row["status"]) == SegmentStatus.FAILED.value:
            continue
        candidate = db.find_locked_reading_that_lost_only_the_spelling_test(
            int(row["id"]),
            policy_hash,
        )
        if candidate is None:
            continue
        found.setdefault(int(row["chapter_id"]), []).append((dict(row), dict(candidate)))
    return found


def mark_chapter_stale(db: Any, chapter: Any, *, kept: int) -> bool:
    """Artifact MP3 của chương hết hiệu lực: `cli run` và `recover_project` sẽ ghép lại."""
    key = f"chapter_mp3:{int(chapter['chapter_index'])}"
    artifact = db.artifact_by_key(key)
    if artifact is None:
        return False
    try:
        metadata = json.loads(str(artifact["metadata_json"] or "{}"))
    except (TypeError, ValueError):
        metadata = {}
    if not isinstance(metadata, dict):
        metadata = {}
    metadata["stale"] = {
        "reason": "kept the locked reading on segments already shipped; the MP3 predates them",
        "segments": int(kept),
        "at": time.time(),
    }
    db.register_artifact(
        artifact_key=key,
        kind="chapter_mp3",
        path=Path(str(artifact["path"])),
        sha256=artifact["sha256"],
        verified=False,
        metadata=metadata,
    )
    return True


def reassemble(pipeline: BookPipeline, chapter: Any) -> tuple[bool, str]:
    """Ghép lại chương bằng chính đuôi của `_process_chapter`; (thành công?, lời).

    Không gọi cả `_process_chapter`: một chương đã hoàn thành vẫn có thể mang đoạn `failed`
    được máy cấp phép (084: `Selene Valkryn.` thua neo tên qua năm vòng), và bước tổng hợp
    của nó coi đoạn ấy là chưa có bằng chứng hiện hành, đặt lại thành `signal_passed` rồi gọi
    Whisper - đo 18:25 2026-09-11. `_publish_verified_chapter` là phần sau mọi đường thu lại:
    cấp phép máy, ba cổng chặn, ffmpeg, sổ chất lượng, artifact, hoàn thành - đúng thứ nó làm
    khi chương lên sách lần đầu.
    """
    db = pipeline.db
    chapter_id = int(chapter["id"])
    # Đang ghép lại: nếu bị ngắt giữa chừng thì chương không còn `completed` và artifact đã
    # hết hiệu lực, `cli run` sẽ tự ghép lại.
    db.update_chapter_status(chapter_id, ChapterStatus.VERIFYING.value)
    try:
        pipeline._publish_verified_chapter(chapter)
    except AudioQualityError as exc:
        pipeline._record_chapter_quality_failure(chapter, exc)
        return False, f"cổng chất lượng chương từ chối: {exc}"
    fresh = next(
        (row for row in db.list_chapters() if int(row["id"]) == int(chapter["id"])),
        None,
    )
    if fresh is None or str(fresh["status"]) != ChapterStatus.COMPLETED.value:
        return False, f"chương không về `completed` (đang {fresh['status'] if fresh else '?'})"
    if not db.chapter_artifact_is_current_qa_verified(int(chapter["chapter_index"])):
        return False, "MP3 mới không có bằng chứng QA hiện hành"
    artifact = db.artifact_by_key(f"chapter_mp3:{int(chapter['chapter_index'])}")
    size = Path(str(artifact["path"])).stat().st_size if artifact is not None else 0
    sha = str(artifact["sha256"] or "")[:12] if artifact is not None else "?"
    return True, f"MP3 mới {sha}… {size / 2**20:.1f} MB"


def _spelling_take_is_playing(segment: dict[str, Any], candidate: dict[str, Any]) -> bool:
    """Đoạn đang phát bản đọc-theo-chữ-viết (khác đương nhiệm mà bản đọc-ghim đã đấu với)?"""
    return str(segment["wav_sha256"] or "").casefold() != str(
        candidate["incumbent_sha256"] or ""
    ).casefold()


def run_project(
    root: Path,
    *,
    apply: bool,
    only_titles: set[str] | None = None,
    include_unchanged: bool = False,
) -> int:
    """0 = xong (hoặc không có gì); 1 = có chương ghép lại không được; 2 = từ chối.

    `only_titles`: chỉ những chương này (từ manifest). Một project lô có 31 chương nhưng sách
    chỉ lấy vài chương từ nó - phần còn lại đã bị bản đúc lại thay. Ghép lại một chương đã bị
    thay là phí, và tệ hơn phí: `assemble_book` chọn bản `completed_at` mới nhất, nên chương cũ
    vừa ghép lại sẽ đoạt lại chỗ của bản đúc lại - dàn giọng cũ quay về sách. Đo 18:50
    2026-09-11: không lọc thì lượt này chạm 142 chương-project cho một cuốn sách 116 chương.

    `include_unchanged`: mặc định chỉ chữa đoạn **đang phát bản đọc-theo-chữ-viết** - đó là lỗi
    người nghe nghe thấy (597 đoạn, đo cùng lúc). Đoạn vẫn phát bản gốc (`failed`, máy đã cấp
    phép) mà có bản đọc-ghim rõ tiếng chỉ thua bài chính tả (530 đoạn) thì để yên: hai bản cùng
    đọc ghim, cùng thua cùng một bài, không có bằng chứng nào xếp hạng chúng, và đổi audio đã
    lên sách mà không có lý do người nghe cảm được là đổi cho có. Vòng sửa đã vá sẽ đề cử bản
    ấy ở lô mới (ở đó chưa có gì lên sách); ở đây phải mở bằng cờ.
    """
    if not (root / "project.sqlite3").is_file():
        _say(f"{root.name}: không phải project")
        return 2
    if get_status(root).running:
        _say(f"{root.name}: project đang chạy - không chạm vào")
        return 2
    # Lượt thử mở project CHỈ ĐỌC: đếm trên các project đã lên sách không được để lại một dấu
    # vết nào (kể cả `runtime_events`), và một project đang được lô khác gieo đi thì càng không.
    paths, db, settings = _open_project(root, read_only=not apply)
    if (
        not hasattr(BookPipeline, "_keep_the_locked_reading")
        or not hasattr(BookPipeline, "_publish_verified_chapter")
        or not hasattr(db, "find_locked_reading_that_lost_only_the_spelling_test")
    ):
        _say("cây mã chưa có bản vá patch_keep_the_locked_reading - không có gì để gọi")
        return 2
    pipeline = bare_pipeline(paths, db, settings)
    chapters = {int(row["id"]): row for row in db.list_chapters()}
    found = survey(db, pipeline.quality_policy_hash)
    superseded = 0
    if only_titles is not None:
        before = len(found)
        found = {
            chapter_id: items
            for chapter_id, items in found.items()
            if str(chapters[chapter_id]["title"]) in only_titles
        }
        superseded = before - len(found)
    left_alone = 0
    if not include_unchanged:
        kept_only = {
            chapter_id: [pair for pair in items if _spelling_take_is_playing(*pair)]
            for chapter_id, items in found.items()
        }
        left_alone = sum(len(items) for items in found.values()) - sum(
            len(items) for items in kept_only.values()
        )
        found = {chapter_id: items for chapter_id, items in kept_only.items() if items}
    total = sum(len(items) for items in found.values())
    notes = []
    if left_alone:
        notes.append(f"để yên {left_alone} đoạn vẫn phát bản gốc")
    if superseded:
        notes.append(f"{superseded} chương đã bị bản khác thay trong sách")
    note = f" ({'; '.join(notes)})" if notes else ""
    if not found:
        _say(f"{root.name}: không đoạn nào đang phát bản đọc-theo-chữ-viết{note}.")
        return 0
    _say(
        f"{root.name}: {total} đoạn trong {len(found)} chương đang phát bản đọc-theo-chữ-viết"
        f" dù có bản đọc-ghim chỉ thua bài chính tả{note}:"
    )
    for chapter_id, items in sorted(found.items()):
        chapter = chapters[chapter_id]
        _say(f"  chương {chapter['title']}: {len(items)} đoạn")
        for segment, candidate in items[:3]:
            text = " ".join(str(segment["text"]).split())[:64]
            _say(
                f"     {str(segment['stable_id'])[-12:]}  vòng {candidate['repair_round']}  {text}"
            )
        if len(items) > 3:
            _say(f"     … và {len(items) - 3} đoạn nữa")
    if not apply:
        _say("Lượt thử, chưa đổi gì. Thêm --apply để đề cử lại và ghép lại chương.")
        return 0

    failures = 0
    for chapter_id, items in sorted(found.items()):
        chapter = chapters[chapter_id]
        kept = 0
        for segment, _candidate in items:
            item = dict(db.get_segment(int(segment["id"])))
            if pipeline._keep_the_locked_reading(item):
                kept += 1
        _say(f"  chương {chapter['title']}: giữ cách đọc ghim cho {kept}/{len(items)} đoạn")
        if kept == 0:
            continue
        if not mark_chapter_stale(db, chapter, kept=kept):
            _say("     không có artifact MP3 để đánh dấu - chương chưa từng ghép?")
        ok, word = reassemble(pipeline, chapter)
        _say(f"     {'ghép lại xong' if ok else 'CHƯA ghép lại'}: {word}")
        if not ok:
            failures += 1
    pipeline._safe_export_reports(incremental=False)
    return 1 if failures else 0


def shipped_projects(book: Path = BOOK, versions: Path = VERSIONS) -> dict[Path, set[str]]:
    """{project: {chương sách lấy từ nó}} theo `manifest.json` - đúng chương, không phải cả project."""
    try:
        payload = json.loads((book / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    entries = payload if isinstance(payload, list) else payload.get("chapters", [])
    roots: dict[Path, set[str]] = {}
    for item in entries:
        version = str(item.get("version") or "")
        project = str(item.get("project") or "")
        title = str(item.get("title") or "")
        if not version or not project or not title:
            _say(f"manifest: chương {item.get('title')} không ghi project - bỏ qua")
            continue
        roots.setdefault(versions / version / project, set()).add(title)
    return roots


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("projects", nargs="*", type=Path)
    parser.add_argument("--book", action="store_true", help="mọi project manifest.json của sách ghi")
    parser.add_argument("--apply", action="store_true", help="đề cử lại và ghép lại chương (mặc định chỉ liệt kê)")
    parser.add_argument(
        "--also-unchanged",
        action="store_true",
        help="chữa cả đoạn vẫn phát bản gốc (mặc định để yên - xem run_project)",
    )
    args = parser.parse_args(argv)
    targets: list[tuple[Path, set[str] | None]] = [(root, None) for root in args.projects]
    if args.book:
        targets.extend(sorted(shipped_projects().items()))
    if not targets:
        parser.error("cần ít nhất một project, hoặc --book")
    worst = 0
    for root, titles in targets:
        worst = max(
            worst,
            run_project(
                root.expanduser().resolve(),
                apply=args.apply,
                only_titles=titles,
                include_unchanged=args.also_unchanged,
            ),
        )
    return worst


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
