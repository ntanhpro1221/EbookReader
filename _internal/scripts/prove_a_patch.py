"""Mã ấy có xuất hiện lại không, và nó đi đường nào? — câu đúng để hỏi sau một lô vá.

    python scripts/prove_a_patch.py <project cũ> <project mới> [--chapter 075] [--code TTS_...]

Sau lô vá của lô 1 tôi hỏi "chương xanh chưa?" và tự thuyết phục mình rằng bốn bản vá đã được
chứng minh; ba trong bốn thì không. Chương xanh chỉ nói *lần rút lá này* không hỏng, còn câu
hỏi thật là: **mã đã giết chương ấy có nổ lại không, và nếu có thì lần này nó đi đường nào** —
`failed` (chưa sửa được), `warning` + xuất bản (bản vá làm việc), hay không xuất hiện (không
chứng minh gì, vì lỗi phụ thuộc seed). Xem docs/PRODUCTION_PLAN.md, mục *"Lô vá là chỗ TỆ để
chứng minh"*.

Ghép đoạn giữa hai project theo **(tiêu đề chương, 12 ký tự hash văn bản)**, không theo
`stable_id` nguyên: `stable_id` là `cXXXXX_sXXXXXXX_<texthash12>`, và cả số chương lẫn số thứ
tự đều là của riêng project — chương 075 là `c00016` trong lô 3 và `c00001` trong project vá
một chương. Phần hash mới là nội dung, nên nó là thứ duy nhất ghép được.
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

PUBLISHED = "completed"
# Chương chưa chạy xong KHÁC chương bị chặn, và trộn hai thứ ấy là lỗi tôi vừa mắc: chạy công cụ
# này lúc chương đúc lại còn `verifying` thì mười đoạn đọc thành "VẪN CHẶN", tức báo một chương
# đang chạy là đã thất bại. `plan_repair_batch._cause` tách hai thứ ấy từ đầu vì cùng lý do.
UNFINISHED_CHAPTER_STATES = frozenset({"pending", "analyzing", "synthesizing", "verifying"})


def _warning_classes() -> tuple[frozenset[str], frozenset[str]]:
    """(mã được phép im lặng, mã máy chấp nhận CÓ GHI SỔ) — đọc từ chính đường ống.

    Hai lớp này là hai câu trả lời khác nhau cho "sao chương vẫn xuất bản dù có mã": lớp đầu
    không cần dòng nào trong bảng nào (`HIGH_QUALITY_ALLOWED_SEGMENT_WARNINGS`), lớp sau phải
    có (`MACHINE_ACCEPTABLE_SEGMENT_WARNINGS`). Không phân biệt được thì báo cáo nói "không
    bảng nào ghi" cho cả hai, và câu ấy đọc như một thiếu sót trong khi phân nửa là đúng thiết
    kế. Đọc từ `pipeline` chứ không chép lại, để hai bản không lệch nhau.
    """
    try:
        from ebook_reader.pipeline import (  # noqa: PLC0415
            HIGH_QUALITY_ALLOWED_SEGMENT_WARNINGS,
            MACHINE_ACCEPTABLE_SEGMENT_WARNINGS,
        )
    except Exception:  # noqa: BLE001
        return frozenset(), frozenset()
    return (
        frozenset(HIGH_QUALITY_ALLOWED_SEGMENT_WARNINGS),
        frozenset(MACHINE_ACCEPTABLE_SEGMENT_WARNINGS),
    )


SILENT_CODES, RECORDED_CODES = _warning_classes()


def _say(line: str) -> None:
    try:
        print(line)
    except (UnicodeEncodeError, OSError, ValueError):
        sys.stdout.buffer.write(line.encode("utf-8", "replace") + b"\n")


def text_key(stable_id: str) -> str:
    """12 ký tự hash cuối của `stable_id` — phần duy nhất không phụ thuộc project."""
    return str(stable_id).rsplit("_", 1)[-1]


def read_segments(project: Path) -> dict[tuple[str, str], dict[str, object]]:
    """{(tiêu đề chương, hash văn bản): thông tin đoạn}. Chỉ đoạn có tên chương thật."""
    conn = sqlite3.connect(f"file:{project / 'project.sqlite3'}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            SELECT ch.title AS chapter, ch.status AS chapter_status, s.stable_id AS stable_id,
                   s.status AS status, s.warning_code AS warning_code, s.error AS error,
                   s.attempt_count AS attempts, s.text AS text
            FROM segments s JOIN chapters ch ON ch.id = s.chapter_id
            """
        ).fetchall()
        accepted: dict[str, list[str]] = {}
        for table, label in (
            ("listener_audio_acceptances", "người nghe"),
            ("machine_audio_acceptances", "máy"),
            ("machine_take_substitutions", "thay bản thu"),
        ):
            try:
                for row in conn.execute(f"SELECT segment_stable_id FROM {table}"):
                    accepted.setdefault(text_key(row[0]), []).append(label)
            except sqlite3.Error:
                continue
    finally:
        conn.close()
    found: dict[tuple[str, str], dict[str, object]] = {}
    for row in rows:
        key = (str(row["chapter"]), text_key(row["stable_id"]))
        found[key] = {
            "stable_id": str(row["stable_id"]),
            "chapter": str(row["chapter"]),
            "chapter_status": str(row["chapter_status"]),
            "status": str(row["status"] or ""),
            "warning_code": str(row["warning_code"] or ""),
            "error": " ".join(str(row["error"] or "").split()),
            "attempts": int(row["attempts"] or 0),
            "text": str(row["text"] or ""),
            "accepted_by": accepted.get(key[1], []),
        }
    return found


def _who_let_it_through(row: dict[str, object]) -> str:
    """Ai cho đoạn này qua: một bảng chấp nhận, hay danh sách mã được phép im lặng."""
    recorded = list(row["accepted_by"]) if isinstance(row["accepted_by"], list) else []
    if recorded:
        return "ghi sổ bởi " + ", ".join(str(x) for x in recorded)
    code = str(row["warning_code"])
    if code in SILENT_CODES:
        return "mã được phép im lặng (không cần dòng nào)"
    if code in RECORDED_CODES:
        return "mã lẽ ra phải có dòng ghi sổ mà KHÔNG có - đáng đọc"
    return "không bảng nào ghi, và mã không thuộc hai danh sách"


def verdict(old: dict[str, object], new: dict[str, object] | None) -> tuple[str, str]:
    """(nhãn, một dòng giải thích) — bản vá làm được gì cho đúng đoạn ấy.

    Năm kết cục, và chỉ hai trong năm là bằng chứng cho một bản vá:

    - `KHÔNG TÁI DIỄN`: đoạn giờ sạch. Với lỗi phụ thuộc seed đây là kết cục thường gặp nhất,
      và nó **không** chứng minh gì — chỉ nói lần rút lá này khác. Ba trong bốn bản vá của lô
      vá lô 1 nằm đúng ô này, và tôi đã đọc chúng thành "đã chứng minh".
    - `ĐI ĐƯỜNG KHÁC`: mã vẫn nổ, chương vẫn xuất bản. **Bằng chứng**: phép kiểm vẫn nói điều
      nó thấy, quyết định thì đổi.
    - `HỎNG, CHƯƠNG VẪN XUẤT`: đoạn `failed` mà chương vẫn xuất bản - cơ chế xuất-bản-không-
      người-nghe, thứ gánh 14/27 chương của lô 2. Nhãn riêng vì bản đầu của hàm này kiểm
      `failed` TRƯỚC rồi trả "VẪN CHẶN", và nói một chương đã lên sách là bị chặn.
    - `VẪN CHẶN`: mã nổ lại và chương không xuất bản được. Bản vá không làm việc, hoặc chưa áp.
    - `CHƯA XONG`: chương vẫn đang chạy. Không phải một kết cục, chỉ là "hỏi quá sớm".
    - `MẤT ĐOẠN`: không tìm thấy đoạn cùng văn bản trong project mới (văn bản đổi, hoặc chương
      chưa chạy) - không phải "đã sửa".
    """
    if new is None:
        return "MẤT ĐOẠN", "không có đoạn nào cùng văn bản trong project mới"
    old_code = str(old.get("warning_code") or "")
    new_code = str(new["warning_code"])
    chapter_status = str(new["chapter_status"])
    if chapter_status in UNFINISHED_CHAPTER_STATES:
        return "CHƯA XONG", f"chương còn {chapter_status} - hỏi lại khi nó xong"
    published = chapter_status == PUBLISHED
    where = "chương xuất bản được" if published else f"chương {chapter_status}"
    if str(new["status"]) == "failed" or new_code == "SEGMENT_FAILED":
        why = f"đoạn vẫn failed sau {new['attempts']} lần thử: {str(new['error'])[:70]}"
        return ("HỎNG, CHƯƠNG VẪN XUẤT" if published else "VẪN CHẶN"), f"{why}; {where}"
    if not new_code:
        return "KHÔNG TÁI DIỄN", f"đoạn sạch, {where} — không chứng minh gì (lỗi phụ thuộc seed)"
    # Mã khác mã cũ là một sự thật khác hẳn "mã cũ nổ lại": nói ra chứ đừng để người đọc tự so
    # dòng tiêu đề với dòng phán quyết.
    changed = f"mã ĐỔI {old_code} → {new_code}" if old_code and new_code != old_code else new_code
    return (
        ("ĐI ĐƯỜNG KHÁC" if published else "VẪN CHẶN"),
        f"{changed}, {where}, {_who_let_it_through(new)}",
    )


def compare(
    old_project: Path,
    new_project: Path,
    *,
    chapters: set[str] | None = None,
    codes: set[str] | None = None,
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    """(những đoạn từng mang mã ở project cũ, những mã MỚI xuất hiện ở project mới)."""
    old = read_segments(old_project)
    new = read_segments(new_project)
    new_chapters = {key[0] for key in new}

    watched: list[dict[str, object]] = []
    for key, row in sorted(old.items()):
        chapter = key[0]
        if chapters is not None and chapter not in chapters:
            continue
        # Chỉ so những chương project mới thật sự có: một project vá một chương không nói gì
        # được về 31 chương còn lại, và liệt kê chúng là làm loãng đúng cái cần đọc.
        if chapter not in new_chapters:
            continue
        code = str(row["warning_code"])
        if not code and str(row["status"]) != "failed":
            continue
        if codes is not None and code not in codes:
            continue
        label, why = verdict(row, new.get(key))
        watched.append({**row, "verdict": label, "why": why, "new": new.get(key)})

    fresh: list[dict[str, object]] = []
    for key, row in sorted(new.items()):
        if chapters is not None and key[0] not in chapters:
            continue
        code = str(row["warning_code"])
        if not code:
            continue
        before = old.get(key)
        if before is not None and str(before["warning_code"]) == code:
            continue
        fresh.append(row)
    return watched, fresh


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("old", type=Path, help="project nơi lỗi xảy ra")
    parser.add_argument("new", type=Path, help="project chạy lại (lô vá / đúc lại giọng)")
    parser.add_argument(
        "--chapter",
        action="append",
        default=None,
        help="chỉ xét chương này (lặp lại được)",
    )
    parser.add_argument(
        "--code",
        action="append",
        default=None,
        help="chỉ xét mã cảnh báo này (lặp lại được)",
    )
    args = parser.parse_args(argv)

    for project in (args.old, args.new):
        if not (project / "project.sqlite3").is_file():
            _say(f"không phải project: {project}")
            return 2

    watched, fresh = compare(
        args.old,
        args.new,
        chapters=set(args.chapter) if args.chapter else None,
        codes=set(args.code) if args.code else None,
    )
    _say(f"cũ: {args.old.name}    mới: {args.new.name}")
    if not watched:
        _say("")
        _say("Không có đoạn nào mang mã ở project cũ trong những chương project mới có.")
    else:
        _say("")
        _say(f"{len(watched)} đoạn từng mang mã, và lần này chúng đi đường nào:")
        for row in watched:
            code = str(row["warning_code"]) or f"status={row['status']}"
            _say(f"  {row['chapter']}  {code}")
            _say(f"      {str(row['text'])[:72]!r}")
            _say(f"      {row['verdict']}: {row['why']}")
    counts: dict[str, int] = {}
    for row in watched:
        counts[str(row["verdict"])] = counts.get(str(row["verdict"]), 0) + 1
    if counts:
        _say("")
        _say("  ".join(f"{label}: {number}" for label, number in sorted(counts.items())))
        if counts.get("KHÔNG TÁI DIỄN"):
            _say(
                f"{counts['KHÔNG TÁI DIỄN']} đoạn không tái diễn - KHÔNG chứng minh bản vá nào."
                " Chỗ chứng minh là lô đầy đủ tiếp theo."
            )
        if counts.get("ĐI ĐƯỜNG KHÁC"):
            _say(
                f"{counts['ĐI ĐƯỜNG KHÁC']} đoạn: mã nổ lại mà chương vẫn lên sách - ĐÂY là"
                " bằng chứng, vì phép kiểm vẫn nói điều nó thấy còn quyết định thì đổi."
            )
    if fresh:
        _say("")
        _say(f"{len(fresh)} đoạn mang mã MỚI ở project mới (không có ở cũ):")
        for row in fresh[:12]:
            _say(f"  {row['chapter']}  {row['warning_code']}  {str(row['text'])[:60]!r}")
        if len(fresh) > 12:
            _say(f"  ... còn {len(fresh) - 12} đoạn nữa")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
