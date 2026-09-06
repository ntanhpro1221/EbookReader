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

# The chapter error that means the perceptual repair loop never got to run.
ASR_EVIDENCE_ABORT = "Perceptual QA requires current ASR evidence"


def is_collateral_warning(chapter_error: str, code: str) -> bool:
    """True when this warning is what the repair loop would have removed on its own.

    `_verify_chapter_perceptual_audio` raises from inside its scoring loop, so a chapter that
    stops there never reaches the repair loop that follows. Every perceptual warning it
    leaves behind is therefore unrepaired-by-default rather than a judgement anyone needs to
    make - alpha.48 re-cut eleven of thirteen such takes in the same chapter and asked for
    none of them.

    Only perceptual codes qualify. An anchor mismatch is not something the perceptual repair
    loop would have touched, so it stays a real request no matter why the chapter stopped.
    """
    return ASR_EVIDENCE_ABORT in str(chapter_error or "") and str(code).startswith("PERCEPTUAL")


def _accepted(connection) -> set:
    """(stable_id, warning_code, wav_sha256) triples a listener has already ruled on.

    The pipeline subtracts these in _high_quality_blocking_segment_warnings, so a report
    that does not is describing a book the pipeline no longer sees - it keeps asking for
    decisions already made. Keyed by checksum, so re-cutting a take voids the decision
    exactly as it does everywhere else.
    """
    try:
        rows = connection.execute(
            "SELECT segment_stable_id, warning_code, wav_sha256 FROM listener_audio_acceptances"
        ).fetchall()
    except Exception:  # noqa: BLE001 - older projects have no such table
        return set()
    return {(str(r[0]), str(r[1]), str(r[2]).lower()) for r in rows}


def _stale_qa_failure(connection, row, accepted: set) -> bool:
    """Does this segment still carry a failed QA verdict nobody has overruled?

    The chapter gate wants a passing segment_audio check for every segment, so a row can
    look clean here - status warning, no blocking code left - and still stop its chapter.
    A listener's acceptance counts as the evidence instead, keyed by artifact like
    everywhere else.

    Best-effort: an older project without these tables simply reports nothing extra, since
    the point is to stop over-promising, not to invent a new way to fail.
    """
    checksum = str(row["wav_sha256"] or "").lower()
    if not checksum:
        return False
    if any(
        stable_id == str(row["stable_id"]) and wav == checksum
        for stable_id, _code, wav in accepted
    ):
        return False
    try:
        verdict = connection.execute(
            "SELECT verdict FROM quality_checks WHERE scope='segment' AND stage='segment_audio_v1' "
            "AND segment_id=(SELECT id FROM segments WHERE stable_id=?) "
            "ORDER BY id DESC LIMIT 1",
            (str(row["stable_id"]),),
        ).fetchone()
    except Exception:  # noqa: BLE001 - older projects have no such table
        return False
    return bool(verdict and str(verdict[0]) in {"fail", "asr_inconclusive"})


def main(project_root: str) -> int:
    root = Path(project_root)
    database = root / "project.sqlite3"
    if not database.is_file():
        print(f"không tìm thấy project: {database}")
        return 2

    connection = sqlite3.connect(f"file:{database}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    chapters = connection.execute(
        "SELECT id, chapter_index, status, output_mp3, last_error FROM chapters "
        "ORDER BY chapter_index"
    ).fetchall()

    # chapters.output_mp3 keeps the path of a file a previous pass wrote, and a chapter
    # that has since failed still carries it while the file itself is gone. Checked on
    # alpha.32: the five failed chapters all have a path and none of the files exist, so
    # nothing stale is sitting in the output folder waiting to be shipped. The file on
    # disk is the honest signal, not the column.
    def _published(row: sqlite3.Row) -> bool:
        path = str(row["output_mp3"] or "")
        return bool(path) and Path(path).is_file()

    accepted = _accepted(connection)
    published = [row for row in chapters if _published(row)]
    print(f"{len(published)}/{len(chapters)} chương có MP3 trên đĩa")
    print()

    blocked = 0
    # Two kinds of blocker need two different things from two different parties, and the
    # difference decides what the owner should do tonight. A segment that has audio can be
    # settled by listening. A segment with no audio at all has nothing to listen to - the
    # pace gate rejected every take - so no amount of ear helps and it needs more attempts.
    only_ear: list[int] = []
    needs_takes: list[int] = []
    needs_gate_fix: list[int] = []
    collateral = 0
    for chapter in chapters:
        if _published(chapter):
            continue
        # A chapter that died on the perceptual precondition never ran its repair loop, so
        # its perceptual warnings are what the loop would have re-cut rather than anything a
        # person needs to rule on. Saying otherwise spends the scarcest resource in the
        # project on work the machine does for free: alpha.50 chapter 3 listed four such
        # segments, and the same chapter in alpha.48 - where the loop did run - re-cut
        # eleven of thirteen and asked for none of them.
        segments = connection.execute(
            "SELECT stable_id, status, warning_code, wav_path, wav_duration, text, asr_text, "
            "wav_sha256 FROM segments WHERE chapter_id=? ORDER BY seq",
            (int(chapter["id"]),),
        ).fetchall()
        reasons: list[tuple[str, sqlite3.Row, str]] = []
        for row in segments:
            codes = {value for value in str(row["warning_code"] or "").split("|") if value}
            checksum = str(row["wav_sha256"] or "").lower()
            codes -= {
                code for code in codes
                if (str(row["stable_id"]), code, checksum) in accepted
            }
            if str(row["status"]) == "failed" and codes:
                # The machine gave up: five repair rounds and no take it would accept.
                reasons.append(("máy đã bó tay", row, sorted(codes)[0] if codes else "SEGMENT_FAILED"))
                continue
            blocking = sorted(codes - HIGH_QUALITY_ALLOWED_SEGMENT_WARNINGS)
            for code in blocking:
                is_collateral = is_collateral_warning(chapter["last_error"], code)
                reasons.append((
                    "chưa chắc cần nghe" if is_collateral else "cảnh báo chặn xuất bản",
                    row,
                    code,
                ))
            if not blocking and _stale_qa_failure(connection, row, accepted):
                # A layer this report used to be blind to, and it made the report lie.
                # chapter_segments_have_current_audio_qa demands a passing segment_audio
                # check for every segment; a row can sit at warning with no blocking code
                # while its stored verdict is still fail, and the chapter refuses with
                # SEGMENT_QA_EVIDENCE_MISSING. alpha.46 hit exactly that on chapter 9 while
                # this script was printing "không có gì chặn".
                reasons.append(("bằng chứng QA chưa đạt", row, "SEGMENT_QA_EVIDENCE_MISSING"))
        missing_audio = [
            row for _kind, row, _code in reasons
            if not (row["wav_path"] and Path(str(row["wav_path"])).is_file())
        ]
        if reasons:
            genuine = [item for item in reasons if item[0] != "chưa chắc cần nghe"]
            if not genuine:
                # Every blocker here is collateral from the aborted repair loop. Listening
                # would settle nothing; fixing the gate and re-running is what settles it.
                needs_gate_fix.append(int(chapter["chapter_index"]))
            else:
                (needs_takes if missing_audio else only_ear).append(int(chapter["chapter_index"]))
        if not reasons:
            # Nothing in this chapter needs a person; it simply has not been reached yet.
            print(f"ch{chapter['chapter_index']:<3} {chapter['status']} - chưa tới lượt, không có gì chặn")
            continue
        blocked += 1
        collateral_here = sum(1 for kind, _row, _code in reasons if kind == "chưa chắc cần nghe")
        collateral += collateral_here
        real_here = len(reasons) - collateral_here
        headline = f"{real_here} chỗ cần quyết định"
        if collateral_here:
            headline += (
                f", + {collateral_here} chỗ có lẽ KHÔNG cần: chương chết trước khi vòng sửa "
                "cảm thụ kịp chạy"
            )
        print(f"ch{chapter['chapter_index']:<3} {chapter['status']} - {headline}")
        for kind, row, code in reasons:
            print()
            print(f"    [{kind}] {row['stable_id']}  ({row['wav_duration'] or 0:.1f}s)  {code}")
            print(f"      nghe    : {row['wav_path']}")
            print(f"      văn bản : {str(row['text'] or '')[:110]}")
            print(f"      máy nghe: {str(row['asr_text'] or '(không có bản ghi)')[:110]}")
            # `accept` vouches for a recording, and checks the checksum to make sure it
            # vouches for the one that was heard. A segment with no audio has nothing to
            # vouch for, so printing the command here would hand the listener a line that
            # can only fail.
            if row["wav_path"] and Path(str(row["wav_path"])).is_file():
                print(
                    f"      chấp nhận: ebook-reader-headless accept \"{root}\" "
                    f"--segment {row['stable_id']} --warning {code} --note \"đã nghe\""
                )
            else:
                print(
                    "      KHÔNG có bản thu nào để nghe - cổng nhịp từ chối cả 4 lần thử. "
                    "`accept` sẽ báo lỗi vì không có checksum để đối chiếu; cần thêm lượt "
                    "thử (tts.max_retries), xem docs/PACE_METRIC.md."
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
    if collateral:
        print()
        print(
            f"BỎ QUA {collateral} chỗ đánh dấu [chưa chắc cần nghe]: chương của chúng chết ở "
            "tiền đề ASR của pha cảm thụ, nên vòng sửa cảm thụ chưa từng chạy. Đó là việc "
            "máy tự làm - alpha.48 tự cắt lại 11 trên 13 đoạn như vậy ở cùng một chương. "
            "Sửa cổng rồi chạy lại, còn sót cái nào thì lúc ấy hãy nghe."
        )

    count = len(published)
    print()
    print(f"Đang xuất bản được: {count}/{len(chapters)}")
    running = count
    if needs_gate_fix:
        running += len(needs_gate_fix)
        print(f"  chỉ cần bản sửa code   : +{len(needs_gate_fix)} chương {needs_gate_fix}"
              f"  => {running}/{len(chapters)}")
    if only_ear:
        running += len(only_ear)
        print(f"  cần tai người nghe     : +{len(only_ear)} chương {only_ear}"
              f"  => {running}/{len(chapters)}")
    if needs_takes:
        running += len(needs_takes)
        print(f"  cần bản thu mới trước  : +{len(needs_takes)} chương {needs_takes}"
              f"  => {running}/{len(chapters)}")
        print("    (những chương này có segment không có audio nào - cổng nhịp từ chối cả "
              "4 lần thử. Nghe không giải quyết được vì không có gì để nghe; xem "
              "docs/PACE_METRIC.md về việc nâng tts.max_retries.)")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__)
        raise SystemExit(2)
    raise SystemExit(main(sys.argv[1]))
