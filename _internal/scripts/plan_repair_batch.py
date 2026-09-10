"""Chương nào của một lô cần chạy lại, và lệnh `create` để chạy lại đúng chúng.

    python scripts/plan_repair_batch.py <project cua lo vua chay>

Sinh ra từ lô 1 (docs/PRODUCTION_PLAN.md, mục *"Khi một lô có chương hỏng"*): chạy lại cả lô
tốn ~13 giờ, còn chạy lại riêng những chương hỏng tốn ~4. Chương đã `completed` là sản phẩm
hoàn chỉnh; việc `resume` bị từ chối sau khi vá chỉ chặn **project ấy**, không chặn việc tạo
một project mới bao đúng dải chương hỏng.

`--range` của CLI nhận một dải liên tục, nên script in ra **từng cụm liền nhau** — chương hỏng
thường rải rác, và ba cụm nhỏ chạy nhanh hơn một dải to bao cả những chương đã tốt.

Chỉ đọc; không tạo project, không chạy gì.
"""
from __future__ import annotations

import argparse
import re
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.discarded_cures import _scan as scan_discarded_cures  # noqa: E402


def _say(line: str) -> None:
    try:
        print(line)
    except (UnicodeEncodeError, OSError, ValueError):
        sys.stdout.buffer.write(line.encode("utf-8", "replace") + b"\n")


# Mã cảnh báo segment trông như `c00008_s0000058_b47b5843ed04=TTS_PACE_BAND_RELAXED`; phần
# trước dấu `=` là danh tính của đoạn, khác nhau ở mọi chương, nên gộp theo nó thì mỗi chương
# thành một nguyên nhân riêng và con số mất hết ý nghĩa.
_SEGMENT_WARNING = re.compile(r"=([A-Z_]+)")
# Cổng QA tầng chương nêu tên phép đo rồi tới con số; con số cũng khác nhau ở mọi chương.
_CHAPTER_FLAG = re.compile(r"policy:\s*([a-z ]+?)\s*[-0-9]")


def _cause(last_error: str) -> str:
    """Gộp `last_error` về **nguyên nhân**, bỏ đi phần khác nhau ở mỗi chương.

    Con số đáng đếm sau một lô không phải bao nhiêu chương hỏng mà bao nhiêu **nguyên nhân
    khác nhau**: một nguyên nhân đánh sáu chương thì rẻ hơn hẳn sáu nguyên nhân mỗi cái đánh
    một chương — cái đầu là một bản vá, cái sau là sáu. Xem docs/PRODUCTION_PLAN.md, mục dự
    đoán cho lô 2.

    Giữ nguyên chuỗi lạ thay vì nhét vào ô "khác": một nguyên nhân chưa từng thấy chính là
    thứ đáng đọc nhất sau một lô, và gộp nó đi là giấu mất nó.
    """
    text = " ".join(str(last_error or "").split())
    if not text:
        return "(không ghi lý do)"
    match = _SEGMENT_WARNING.search(text)
    if match:
        return f"cảnh báo segment: {match.group(1)}"
    match = _CHAPTER_FLAG.search(text)
    if match:
        return f"QA chương: {match.group(1).strip()}"
    return text[:70]


_FAILED_SEGMENT = re.compile(r"(c\d{5}_s\d{7}_[0-9a-f]{12})=SEGMENT_FAILED")
_NUMBER = re.compile(r"\d+(?:[.,]\d+)?")


def _segment_failure_detail(conn: sqlite3.Connection, last_error: str) -> str | None:
    """`SEGMENT_FAILED` nói "một đoạn chết", không nói vì sao; vì sao nằm ở `segments.error` của
    chính đoạn ấy. Chương 075 lô 3: "speech pace 11.00 chars/s; split=segment too short to
    split safely; pace_band=already normal". Lấy mệnh đề đầu và bỏ số, để hai chương cùng chết
    vì nhịp gộp về một nguyên nhân thay vì hai — đó là con số cần đếm sau một lô."""
    match = _FAILED_SEGMENT.search(last_error)
    if not match:
        return None
    row = conn.execute(
        "SELECT error FROM segments WHERE stable_id = ?", (match.group(1),)
    ).fetchone()
    if not row or not row[0]:
        return None
    text = " ".join(str(row[0]).split())
    prefix = "high-quality TTS retry required:"
    if text.startswith(prefix):
        text = text[len(prefix):]
    first = text.split(";", 1)[0].strip()
    return _NUMBER.sub("N", first)[:60] or None


def _runs(numbers: list[int]) -> list[tuple[int, int]]:
    """[0, 3, 7, 8, 9] -> [(0,0), (3,3), (7,9)]"""
    spans: list[tuple[int, int]] = []
    for number in sorted(numbers):
        if spans and number == spans[-1][1] + 1:
            spans[-1] = (spans[-1][0], number)
        else:
            spans.append((number, number))
    return spans


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("project", type=Path)
    parser.add_argument("--tag", default="<tag mới>", help="Tên phiên bản cho lô vá")
    args = parser.parse_args(argv)

    database = args.project / "project.sqlite3"
    if not database.is_file():
        _say(f"Không thấy {database}")
        return 2
    conn = sqlite3.connect(f"file:{database}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row

    rows = list(conn.execute("SELECT title, status, last_error FROM chapters ORDER BY title"))
    done = [r for r in rows if str(r["status"]) == "completed"]
    # Tách "hỏng" khỏi "chưa chạy". Chạy giữa chừng thì mọi chương chưa tới lượt đều đọc thành
    # cần vá, và một danh sách như thế đọc lúc năm giờ sáng là chạy lại thừa cả chục chương.
    unfinished = [
        r for r in rows
        if str(r["status"]) in {"pending", "analyzing", "synthesizing", "verifying"}
    ]
    broken = [
        r for r in rows
        if str(r["status"]) != "completed" and r not in unfinished
    ]

    _say(f"{len(done)}/{len(rows)} chương đã xong.")
    if unfinished:
        _say(
            f"  LƯU Ý: {len(unfinished)} chương CHƯA CHẠY XONG "
            f"({', '.join(str(r['title']) for r in unfinished[:8])}...) - đợi lô xong đã."
        )
    if not broken:
        _say("Không có chương nào hỏng.")
        return 0
    _say(f"{len(broken)} chương hỏng, cần chạy lại.")

    _say("")
    _say("Chương hỏng, kèm lý do:")
    for row in broken:
        _say(f"  {row['title']}  {str(row['last_error'] or '')[:96]}")

    causes: dict[str, list[str]] = {}
    for row in broken:
        last_error = str(row["last_error"] or "")
        cause = _cause(last_error)
        detail = _segment_failure_detail(conn, last_error)
        if detail:
            cause = f"{cause} — {detail}"
        causes.setdefault(cause, []).append(str(row["title"]))
    _say("")
    _say(f"{len(causes)} nguyên nhân khác nhau trên {len(broken)} chương:")
    for cause, titles in sorted(causes.items(), key=lambda kv: (-len(kv[1]), kv[0])):
        _say(f"  {len(titles)}x  {cause}   ({', '.join(titles)})")

    numbers: list[int] = []
    for row in broken:
        try:
            numbers.append(int(str(row["title"])))
        except ValueError:
            _say(f"  (bỏ qua {row['title']}: tiêu đề không phải số)")
    spans = _runs(numbers)

    _say("")
    _say(f"{len(spans)} cụm liền nhau. Lệnh cho từng cụm:")
    width = max((len(str(row["title"])) for row in broken), default=3)
    for first, last in spans:
        _say(
            f'  --range "{first:0{width}d}..{last:0{width}d}" --width {width} '
            f'--title "{args.tag}"'
        )

    # Có chương nào hỏng vì cái mẫu mà chạy lại KHÔNG chữa được không.
    #
    # Lô vá chạy lại đúng như cũ, nên nó chỉ chữa được thứ hỏng vì ngẫu nhiên hoặc vì một bản
    # vá đã vào cây. Mẫu "phương thuốc bị vứt" thì không: bản đương nhiệm chạm trần khung, các
    # ứng viên cứu được lại bị vứt vì mã mà chính sách đã tự xếp là không mang thông tin — và
    # luật ấy vẫn nguyên. Chạy lại có thể trúng một lần gieo khác và may mắn thoát, nhưng đó là
    # may chứ không phải chữa.
    #
    # In ra ở đây vì lập lô vá là đúng lúc người ta muốn biết, chứ không phải sau khi lô vá
    # thứ hai cũng hỏng ở cùng chỗ. Xem docs/OPTIMISATION_QUEUE.md, mục "phương thuốc bị vứt".
    broken_titles = {str(row["title"]) for row in broken}
    try:
        cures = [c for c in scan_discarded_cures(args.project) if c["chapter"] in broken_titles]
    except sqlite3.Error:
        cures = []
    if cures:
        _say("")
        _say(f"CẢNH BÁO: {len(cures)} đoạn hỏng theo mẫu mà chạy lại không chữa được:")
        for cure in cures:
            _say(f"  ch{cure['chapter']}  {cure['stable_id']}  {cure['text']!r}")
            _say(
                f"      đương nhiệm chạm trần khung ở {cure['incumbent_duration']}s;"
                f" {len(cure['rescues'])} ứng viên bị vứt"
                f" ({', '.join(str(r['duration']) + 's' for r in cure['rescues'])})"
            )
        _say("  Chạy lại vẫn nên làm — lần gieo khác có thể thoát — nhưng nếu chương ấy hỏng")
        _say("  lại ở đúng đoạn ấy thì đừng chạy lần thứ ba, đó là luật chứ không phải xui.")

    _say("")
    _say("Trước khi chạy: `python scripts/before_a_batch.py`, và gieo từ chính project này")
    _say("(port_pronunciations → port_casting → seed_listener_acceptances) để giọng không đổi.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
