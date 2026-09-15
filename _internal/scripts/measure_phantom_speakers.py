r"""Có bao nhiêu "nhân vật" thật ra là chữ mở đầu một câu tường thuật sau dấu đóng ngoặc kép?

    python scripts/measure_phantom_speakers.py
    python scripts/measure_phantom_speakers.py --min-lines 1 --all-books

Chỉ đọc: mở database project ở chế độ read-only, không ghi gì.

## Ca thật

Nguồn `“Là tôi, Victor.” Nghe giọng của Victor…` cho ra một "nhân vật" tên `Nghe` giữ 3 câu
thực ra của Victor và Nam tước Othello (14-09). Hai hệ quả: lời bị gán sai giọng, và cổng dàn
giọng chặn cả lô vì cái tên ấy không có giới tính. `Nghe` cũng góp một va chạm cùng chương ở lô
3 (chương 36, chia giọng với Camil).

## Phép đo

Hàng chờ tối ưu đòi **đo trước khi viết mã**, và đòi đúng thứ này: đừng lọc bằng "từ có nghĩa
tiếng Việt" nói chung, vì `Mật Ong Trắng`, `Triết Gia`, `Thủy Ngân`, `Hạ Phong` đều là tên nhân
vật thật trong cuốn này. Nên phép đo không dùng từ điển; nó dùng **hình của văn bản**:

    mở câu tường thuật : số đoạn tường thuật bắt đầu bằng đúng chữ ấy
    ngay sau ngoặc kép : trong số ấy, bao nhiêu đoạn liền trước kết thúc bằng `”`
    giữa câu          : số lần chữ ấy xuất hiện viết hoa mà KHÔNG ở đầu đoạn / sau `“`

Tên nhân vật thật xuất hiện viết hoa giữa câu rất nhiều (`của Victor`, `Felicia và Victor`).
Một chữ mở đầu câu tường thuật thì gần như chỉ xuất hiện ở đầu câu - giữa câu nó viết thường
(`nghe`, `thấy`, `nhìn`). Đó là dấu hiệu phân biệt, và nó không cần biết tiếng Việt.
"""
from __future__ import annotations

import argparse
import collections
import glob
import re
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

try:
    from scripts.book_paths import VERSIONS  # noqa: E402
except ImportError:  # chạy trực tiếp
    from book_paths import VERSIONS  # noqa: E402

CLOSING = ("”", '"', "’", "»")
OPENING = ("“", '"', "«")
RESERVED = {"narrator", "người dẫn truyện", "unknown", "", "none"}


def _say(line: str) -> None:
    try:
        print(line, flush=True)
    except UnicodeEncodeError:
        print(line.encode("ascii", "backslashreplace").decode("ascii"), flush=True)


def _first_word(text: str) -> str:
    stripped = text.lstrip("“\"«‘ \t—-–")
    match = re.match(r"[^\W\d_]+", stripped, re.UNICODE)
    return match.group(0) if match else ""


def _is_mid_sentence(text: str, at: int) -> bool:
    """Chữ ở vị trí `at` có đứng GIỮA một câu không, hay nó mở đầu một câu?

    Một đoạn chứa nhiều câu, nên "không ở đầu đoạn" là chưa đủ. Bản đầu của phép đo này chỉ bỏ
    đầu đoạn và dấu mở ngoặc kép, nên cả 13 lần `Nghe` viết hoa của cuốn 2 bị tính là "giữa
    câu" - trong khi đọc ra thì **cả 13** đứng ngay sau `.`, `?` hoặc `!`:

        ... trong lớp ghen tị. [Nghe] thấy lời khen của Victor...
        ... lại là một cuốn tập san? [Nghe] học thuật thế nào ấy nhỉ...

    Và vì thế `Nghe` - ca thật đã sinh ra cả mục hàng chờ này - lọt lưới chính phép đo đi tìm
    nó. Giữa câu = chữ liền trước (bỏ dấu cách) là **chữ, số, hoặc dấu phẩy**; mọi dấu kết câu,
    dấu hai chấm, gạch ngang và dấu mở ngoặc đều mở một câu mới.
    """
    head = text[:at].rstrip(" \t")
    if not head:
        return False
    previous = head[-1]
    return previous.isalnum() or previous == ","


def measure(database: Path) -> dict[str, dict[str, int]]:
    """Cho một project: với mỗi tên người nói một-từ, ba con số của phép đo trên."""
    connection = sqlite3.connect(f"file:{database.as_posix()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        rows = connection.execute(
            "SELECT chapter_id, seq, kind, speaker, text FROM segments ORDER BY chapter_id, seq"
        ).fetchall()
    except sqlite3.Error:
        return {}
    finally:
        connection.close()

    lines: collections.Counter[str] = collections.Counter()
    for row in rows:
        speaker = str(row["speaker"] or "").strip()
        if speaker and speaker.casefold() not in RESERVED:
            lines[speaker] += 1
    candidates = {name for name in lines if len(name.split()) == 1 and name[:1].isupper()}
    if not candidates:
        return {}

    opens: collections.Counter[str] = collections.Counter()
    after_quote: collections.Counter[str] = collections.Counter()
    mid_sentence: collections.Counter[str] = collections.Counter()
    lowercase: collections.Counter[str] = collections.Counter()
    folded = {name: name.lower() for name in candidates}
    previous: dict | None = None
    for row in rows:
        text = str(row["text"] or "")
        kind = str(row["kind"] or "")
        word = _first_word(text)
        if word in candidates and kind != "dialogue" and not text.lstrip().startswith(OPENING):
            opens[word] += 1
            if previous is not None and str(previous["text"] or "").rstrip().endswith(CLOSING):
                after_quote[word] += 1
        for name in candidates:
            for match in re.finditer(rf"(?<![^\W\d_]){re.escape(name)}(?![^\W\d_])", text):
                if _is_mid_sentence(text, match.start()):
                    mid_sentence[name] += 1
            # Cùng chữ ấy viết THƯỜNG ở đâu đó trong sách: `nghe`, `mình`, `tin` là từ thường
            # gặp của tiếng Việt, còn `Thompson` hay `Lucien` không bao giờ viết thường. Đây là
            # phép thử "từ này là một từ của ngôn ngữ" đo từ CHÍNH cuốn sách, không từ từ điển -
            # đúng điều hàng chờ dặn (`Mật Ong Trắng`, `Thủy Ngân` là tên thật).
            lowercase[name] += len(
                re.findall(rf"(?<![^\W\d_]){re.escape(folded[name])}(?![^\W\d_])", text)
            )
        previous = row

    return {
        name: {
            "lines": lines[name],
            "opens": opens[name],
            "after_quote": after_quote[name],
            "mid_sentence": mid_sentence[name],
            "lowercase": lowercase[name],
        }
        for name in candidates
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--min-lines", type=int, default=1, help="bỏ tên dưới bấy nhiêu câu")
    parser.add_argument("--versions", type=Path, default=VERSIONS)
    parser.add_argument(
        "--all-books",
        action="store_true",
        help="quét cả những `_versions` bên cạnh (cuốn khác), không riêng cuốn đang sản xuất",
    )
    args = parser.parse_args(argv)

    roots = [args.versions]
    if args.all_books:
        for base in (args.versions.parent, args.versions.parent.parent):
            if base.is_dir():
                roots.append(base / "_versions")
                roots.extend(sorted(base.glob("*/_versions")))
    seen_root: set[str] = set()
    databases: list[Path] = []
    for root in roots:
        key = str(root).casefold()
        if key in seen_root or not root.is_dir():
            continue
        seen_root.add(key)
        databases.extend(Path(p) for p in sorted(glob.glob(str(root / "*" / "*" / "project.sqlite3"))))

    total: dict[str, dict[str, int]] = {}
    for database in databases:
        for name, counts in measure(database).items():
            bucket = total.setdefault(
                name, {"lines": 0, "opens": 0, "after_quote": 0, "mid_sentence": 0, "lowercase": 0}
            )
            for key, value in counts.items():
                bucket[key] += value

    _say(f"{len(databases)} project, {len(total)} tên người nói một-từ")
    _say("")
    suspects = [
        (name, counts)
        for name, counts in total.items()
        if counts["lines"] >= args.min_lines
        and counts["after_quote"] > 0
        and counts["mid_sentence"] == 0
        and counts["lowercase"] > 0
    ]
    suspects.sort(key=lambda item: (-item[1]["lines"], item[0]))
    header = (
        f"{'tên':<18}{'câu':>5}{'mở câu tường thuật':>21}{'ngay sau ngoặc kép':>21}"
        f"{'giữa câu':>10}{'viết thường':>13}"
    )
    _say(header)
    for name, counts in suspects:
        _say(
            f"{name:<18}{counts['lines']:>5}{counts['opens']:>21}"
            f"{counts['after_quote']:>21}{counts['mid_sentence']:>10}{counts['lowercase']:>13}"
        )
    if not suspects:
        _say("   (không có)")
    _say("")
    _say("Đối chứng - vài tên chắc chắn là người thật, để thấy hai cột cuối khác hẳn:")
    _say(header)
    control = sorted(
        (item for item in total.items() if item[1]["mid_sentence"] > 0),
        key=lambda item: -item[1]["lines"],
    )[:6]
    for name, counts in control:
        _say(
            f"{name:<18}{counts['lines']:>5}{counts['opens']:>21}"
            f"{counts['after_quote']:>21}{counts['mid_sentence']:>10}{counts['lowercase']:>13}"
        )
    _say("")
    _say(
        "Nghi can = mở một câu tường thuật NGAY SAU ngoặc kép, không bao giờ viết hoa giữa câu, "
        "và chính chữ ấy có viết thường ở đâu đó trong sách."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
