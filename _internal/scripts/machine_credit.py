r"""Chương nào xuất bản nhờ MÁY, chương nào nhờ PHÁN QUYẾT CŨ của người?

    python scripts/machine_credit.py <project_root> [--compare <project truoc>]

Một lượt chạy mang phán quyết từ lượt trước sẽ xuất bản nhiều chương hơn, và rất dễ đọc nhầm
con số ấy thành "máy khá lên". alpha.56 xuất 9/9 trong khi alpha.55 chỉ 5/9 — nhưng bốn chương
chênh lệch đi qua nhờ phán quyết chủ sách đã cho từ vòng trước, **bản thu vẫn mang trạng thái
`failed`, máy không đổi ý điều gì**.

Script này tách hai thứ ấy ra. Với mỗi chương nó hỏi: *nếu bỏ hết phán quyết mang sang, chương
này còn xuất được không?* Trả lời bằng cách áp đúng luật của
`_high_quality_blocking_segment_warnings` — hai mã chặn, năm mã cho qua — lên trạng thái segment,
một lần có phán quyết và một lần không.

Chỉ đọc, không sửa gì.
"""
from __future__ import annotations

import argparse
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


def _report(root: Path, label: str) -> tuple[int, int, int]:
    connection = _open(root)
    try:
        titles = [str(row["title"]) for row in connection.execute("SELECT title FROM chapters")]
        with_verdicts = _blockers(connection, honour_verdicts=True)
        without = _blockers(connection, honour_verdicts=False)
        verdicts = connection.execute(
            "SELECT COUNT(*) FROM listener_audio_acceptances"
        ).fetchone()[0]
    finally:
        connection.close()

    _say(f"### {label}  ({len(titles)} chương, {verdicts} phán quyết trong database)")
    _say("  (Đây là trạng thái database LÚC NÀY, không phải kết cục lịch sử của lượt chạy:")
    _say("   phán quyết thêm vào SAU khi chạy vẫn nằm đây. alpha.55 thật ra chặn 4 chương,")
    _say("   rồi tôi mới nghe và chấp nhận, nên hôm nay nó chỉ còn 1.)")
    _say(f"  chặn kể cả khi tính phán quyết : {len(with_verdicts)}")
    _say(f"  chặn nếu BỎ phán quyết         : {len(without)}")
    _say(f"  -> công của máy: {len(titles) - len(without)}/{len(titles)} chương"
         f"; phán quyết cứu thêm {len(without) - len(with_verdicts)}")
    for title in sorted(without):
        rescued = " (phán quyết cứu)" if title not in with_verdicts else ""
        _say(f"     {title}{rescued}: {'; '.join(without[title])}")
    _say("")
    return len(titles), len(with_verdicts), len(without)


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
