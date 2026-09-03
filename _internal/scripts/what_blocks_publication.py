"""Which chapters will not publish, why, and the exact command that settles each one.

review_required.json lists every segment a person might want to hear - 56 of them in
alpha.32 - but most of those carry warnings the policy already allows and publish anyway.
Reading it does not tell you which four segments are actually holding four chapters shut,
and it does not tell you what to do about them.

This does both. For every chapter that cannot publish it names the segments responsible,
separates the two reasons they can be responsible, prints what the voice was asked to say
against what Whisper heard, and writes out the `accept` line for each - so the listener's
job is to play a clip, read two lines, and either paste a command or leave it alone.

Read-only: opens the project database read-only and writes nothing.

    python scripts/what_blocks_publication.py <project_root>
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ebook_reader.pipeline import HIGH_QUALITY_ALLOWED_SEGMENT_WARNINGS  # noqa: E402


def main(project_root: str) -> int:
    root = Path(project_root)
    database = root / "project.sqlite3"
    if not database.is_file():
        print(f"không tìm thấy project: {database}")
        return 2

    connection = sqlite3.connect(f"file:{database}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    chapters = connection.execute(
        "SELECT id, chapter_index, status, output_mp3 FROM chapters ORDER BY chapter_index"
    ).fetchall()

    # chapters.output_mp3 keeps the path of a file a previous pass wrote, and a chapter
    # that has since failed still carries it while the file itself is gone. Checked on
    # alpha.32: the five failed chapters all have a path and none of the files exist, so
    # nothing stale is sitting in the output folder waiting to be shipped. The file on
    # disk is the honest signal, not the column.
    def _published(row: sqlite3.Row) -> bool:
        path = str(row["output_mp3"] or "")
        return bool(path) and Path(path).is_file()

    published = [row for row in chapters if _published(row)]
    print(f"{len(published)}/{len(chapters)} chương có MP3 trên đĩa")
    print()

    blocked = 0
    for chapter in chapters:
        if _published(chapter):
            continue
        segments = connection.execute(
            "SELECT stable_id, status, warning_code, wav_path, wav_duration, text, asr_text "
            "FROM segments WHERE chapter_id=? ORDER BY seq",
            (int(chapter["id"]),),
        ).fetchall()
        reasons: list[tuple[str, sqlite3.Row, str]] = []
        for row in segments:
            codes = {value for value in str(row["warning_code"] or "").split("|") if value}
            if str(row["status"]) == "failed":
                # The machine gave up: five repair rounds and no take it would accept.
                reasons.append(("máy đã bó tay", row, sorted(codes)[0] if codes else "SEGMENT_FAILED"))
                continue
            blocking = sorted(codes - HIGH_QUALITY_ALLOWED_SEGMENT_WARNINGS)
            for code in blocking:
                reasons.append(("cảnh báo chặn xuất bản", row, code))
        if not reasons:
            # Nothing in this chapter needs a person; it simply has not been reached yet.
            print(f"ch{chapter['chapter_index']:<3} {chapter['status']} - chưa tới lượt, không có gì chặn")
            continue
        blocked += 1
        print(f"ch{chapter['chapter_index']:<3} {chapter['status']} - {len(reasons)} chỗ cần quyết định")
        for kind, row, code in reasons:
            print()
            print(f"    [{kind}] {row['stable_id']}  ({row['wav_duration'] or 0:.1f}s)  {code}")
            print(f"      nghe    : {row['wav_path']}")
            print(f"      văn bản : {str(row['text'] or '')[:110]}")
            print(f"      máy nghe: {str(row['asr_text'] or '(không có bản ghi)')[:110]}")
            print(
                f"      chấp nhận: ebook-reader-headless accept \"{root}\" "
                f"--segment {row['stable_id']} --warning {code} --note \"đã nghe\""
            )
        print()

    connection.close()
    if not blocked:
        print("Không chương nào đang chờ quyết định của người nghe.")
        return 0
    print(
        "Nghe từng file, đọc hai dòng văn bản/máy-nghe. Nếu giọng đọc đúng thì dán lệnh "
        "`accept`; nếu đọc sai thật thì để nguyên, hoặc `retry` để thu lại. Quyết định gắn "
        "với đúng bản thu đó - thu lại là nó hết hiệu lực."
    )
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__)
        raise SystemExit(2)
    raise SystemExit(main(sys.argv[1]))
