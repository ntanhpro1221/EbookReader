r"""Chương nào xuất bản nhờ MÁY, chương nào nhờ PHÁN QUYẾT CŨ của người?

    python scripts/machine_credit.py <project_root> [--compare <project truoc>]

Một lượt chạy mang phán quyết từ lượt trước sẽ xuất bản nhiều chương hơn, và rất dễ đọc nhầm
con số ấy thành "máy khá lên". alpha.56 xuất 9/9 trong khi alpha.55 chỉ 5/9 — nhưng bốn chương
chênh lệch đi qua nhờ phán quyết chủ sách đã cho từ vòng trước, **bản thu vẫn mang trạng thái
`failed`, máy không đổi ý điều gì**.

Từ 2026-09-08 có **loại thứ ba**, và nó không thuộc về bên nào trong hai bên trên: máy tự cho
qua khi ASR là nhân chứng duy nhất (docs/SHIPPING_WITHOUT_A_LISTENER.md). Chương ấy xuất bản,
nhưng **không phải vì phép kiểm nào tán thành** — chỉ vì không còn ai để hỏi. Gộp nó vào "công
của máy" là đúng thứ nói dối mà cả file này sinh ra để chặn, nên nó được đếm riêng.

Script này tách ba thứ ấy ra. Với mỗi chương nó hỏi: *nếu bỏ hết phán quyết mang sang, chương
này còn xuất được không?* Trả lời bằng cách áp đúng luật của
`_high_quality_blocking_segment_warnings` — hai mã chặn, năm mã cho qua — lên trạng thái segment,
một lần có phán quyết và một lần không.

Chỉ đọc, không sửa gì.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ebook_reader.pipeline import HIGH_QUALITY_ALLOWED_SEGMENT_WARNINGS  # noqa: E402


def _say(line: str) -> None:
    try:
        print(line)
    except (UnicodeEncodeError, OSError, ValueError):
        sys.stdout.buffer.write(line.encode("utf-8", "replace") + b"\n")


def _open(root: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(f"file:{root / 'project.sqlite3'}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    return connection


def _blockers(connection: sqlite3.Connection, *, honour_verdicts: bool) -> dict[str, list[str]]:
    """Mã chặn còn lại của từng chương, theo đúng luật của bộ lọc trong pipeline."""
    accepted: set[tuple[str, str, str]] = set()
    if honour_verdicts:
        accepted = {
            (str(row["segment_stable_id"]), str(row["wav_sha256"]), str(row["warning_code"]))
            for row in connection.execute(
                "SELECT segment_stable_id, wav_sha256, warning_code"
                " FROM listener_audio_acceptances"
            )
        }
    blocked: dict[str, list[str]] = {}
    for row in connection.execute(
        "SELECT c.title AS title, s.stable_id AS stable_id, s.wav_sha256 AS wav_sha256,"
        "       s.warning_code AS warning_code"
        " FROM segments s JOIN chapters c ON c.id = s.chapter_id"
    ):
        codes = {value for value in str(row["warning_code"] or "").split("|") if value}
        remaining = sorted(codes - HIGH_QUALITY_ALLOWED_SEGMENT_WARNINGS)
        remaining = [
            code
            for code in remaining
            if (str(row["stable_id"]), str(row["wav_sha256"] or ""), code) not in accepted
        ]
        if remaining:
            blocked.setdefault(str(row["title"]), []).append(
                f"{row['stable_id'][:22]}={','.join(remaining)}"
            )
    return blocked


def _machine_accepted_chapters(connection: sqlite3.Connection) -> dict[str, int]:
    """Chương nào đi qua nhờ MÁY tự cho qua, và bao nhiêu đoạn.

    Không phải công của máy theo nghĩa file này dùng - "công của máy" là *phép kiểm tán thành*,
    còn đây là *không còn ai để hỏi*. Cũng không phải phán quyết của người. Cột riêng.
    """
    names = {r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if "machine_audio_acceptances" not in names:
        return {}
    accepted = {
        (str(a), str(b))
        for a, b in connection.execute(
            "SELECT segment_stable_id, wav_sha256 FROM machine_audio_acceptances"
        )
    }
    if not accepted:
        return {}
    counts: dict[str, int] = {}
    for row in connection.execute(
        "SELECT c.title AS title, s.stable_id AS stable_id, s.wav_sha256 AS wav_sha256"
        " FROM segments s JOIN chapters c ON c.id = s.chapter_id"
    ):
        if (str(row["stable_id"]), str(row["wav_sha256"] or "")) in accepted:
            counts[str(row["title"])] = counts.get(str(row["title"]), 0) + 1
    return counts


def _chapter_level_failures(connection: sqlite3.Connection) -> dict[str, str]:
    """Chương bị chặn bởi thứ KHÔNG phải cảnh báo segment.

    Điểm mù của chính script này, alpha.57 chỉ ra: nó đếm 5 chương bị chặn trong khi thật ra 6.
    Chương 022 trượt ở `CHAPTER_QA_REVIEW_REQUIRED` với "join discontinuity 0.183" - một phép
    kiểm ở tầng chương, đo chỗ nối giữa các segment khi ghép MP3, hoàn toàn nằm ngoài
    `_high_quality_blocking_segment_warnings`.

    Một thước đo tự tin mà mù một phần thì nguy hơn không có thước đo, nên nó được đếm riêng
    và gọi tên chứ không gộp im lặng.
    """
    titles = {
        int(row["id"]): str(row["title"])
        for row in connection.execute("SELECT id, title FROM chapters")
    }
    out: dict[str, str] = {}
    for row in connection.execute(
        "SELECT chapter_id, failure_codes_json, metrics_json FROM quality_checks"
        " WHERE scope='chapter' AND verdict<>'pass' ORDER BY id"
    ):
        codes = str(row["failure_codes_json"] or "")
        if "SEGMENT_QA_REVIEW_REQUIRED" in codes:
            continue  # đã tính ở cổng segment
        try:
            detail = str(json.loads(row["metrics_json"] or "{}").get("error", ""))
        except (TypeError, ValueError):
            detail = ""
        title = titles.get(int(row["chapter_id"] or -1), "?")
        out[title] = f"{codes}: {detail[:90]}"
    return out


def _report(root: Path, label: str) -> tuple[int, int, int]:
    connection = _open(root)
    try:
        chapter_rows = list(connection.execute("SELECT title, status FROM chapters"))
        titles = [str(row["title"]) for row in chapter_rows]
        # Chương chưa chạy thì chưa có mã cảnh báo nào, nên nó đọc thành "máy làm được" - và
        # con số "công của máy" phồng lên đúng bằng số chương còn lại. Cùng cái bẫy đã bịt ở
        # `compare_runs.py`, và tôi rơi vào nó một lần ở đây trước khi bịt.
        unfinished = [
            str(row["title"])
            for row in chapter_rows
            if str(row["status"]) in {"pending", "analyzing", "synthesizing", "verifying"}
        ]
        with_verdicts = _blockers(connection, honour_verdicts=True)
        without = _blockers(connection, honour_verdicts=False)
        chapter_level = _chapter_level_failures(connection)
        machine_accepted = _machine_accepted_chapters(connection)
        verdicts = connection.execute(
            "SELECT COUNT(*) FROM listener_audio_acceptances"
        ).fetchone()[0]
    finally:
        connection.close()

    _say(f"### {label}  ({len(titles)} chương, {verdicts} phán quyết trong database)")
    if unfinished:
        _say(
            f"  CHƯA CHẠY XONG: {len(unfinished)}/{len(titles)} chương "
            f"({', '.join(unfinished[:6])}...). Chương chưa chạy chưa có mã cảnh báo nào nên"
        )
        _say("   nó đọc thành 'máy làm được'; con số dưới đây phồng lên đúng bằng số ấy.")
    _say("  (Đây là trạng thái database LÚC NÀY, không phải kết cục lịch sử của lượt chạy:")
    _say("   phán quyết thêm vào SAU khi chạy vẫn nằm đây. alpha.55 thật ra chặn 4 chương,")
    _say("   rồi tôi mới nghe và chấp nhận, nên hôm nay nó chỉ còn 1.)")
    extra_count = len({t for t in chapter_level if t not in without})
    _say(f"  chặn ở cổng cảnh báo segment, tính phán quyết : {len(with_verdicts)}")
    _say(f"  chặn ở cổng ấy nếu BỎ phán quyết              : {len(without)}")
    _say(f"  chặn ở TẦNG CHƯƠNG (ngoài cổng ấy)            : {extra_count}")
    # Trừ cả chương đi qua nhờ máy tự cho qua. Chúng nằm trong `without` (mã cảnh báo vẫn còn
    # trên segment - máy không đổi ý điều gì), nên không trừ ra là kể công cho phép kiểm về
    # một chương mà không phép kiểm nào tán thành.
    unheard = {t for t in machine_accepted if t in without}
    earned = len(titles) - len(without) - extra_count
    _say(f"  đi qua nhờ MÁY TỰ CHO QUA (chưa ai nghe)     : {len(unheard)}")
    _say(f"  -> công của máy: {earned}/{len(titles)} chương"
         f"; phán quyết cứu thêm {len(without) - len(with_verdicts)}"
         f"; tự cho qua {len(unheard)}")
    if unheard:
        for title in sorted(unheard):
            _say(f"       ch{title}: {machine_accepted[title]} đoạn chưa ai nghe")
        _say("     (scripts/machine_acceptances.py in kèm mốc thời gian trong MP3)")
    for title in sorted(without):
        rescued = " (phán quyết cứu)" if title not in with_verdicts else ""
        _say(f"     {title}{rescued}: {'; '.join(without[title])}")
    extra = {t: d for t, d in chapter_level.items() if t not in without}
    if extra:
        _say(f"  + {len(extra)} chương bị chặn ở TẦNG CHƯƠNG, ngoài cổng cảnh báo segment:")
        for title, detail in sorted(extra.items()):
            _say(f"     {title}: {detail}")
        _say(f"  => tổng chương không xuất được: {len(without) + len(extra)}")
    _say("")
    return len(titles), len(with_verdicts), len(without) + len(extra)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("project_root", type=Path)
    parser.add_argument("--compare", type=Path, help="Project trước, để đặt cạnh nhau")
    args = parser.parse_args(argv)

    if args.compare:
        _report(args.compare.resolve(), args.compare.name)
    _report(args.project_root.resolve(), args.project_root.name)
    _say("Cột 'công của máy' mới là con số so được giữa hai phiên bản.")
    _say("Cột kia trộn công của máy với công của tai chủ sách từ những vòng trước.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
