"""Cả CUỐN SÁCH đã ghép: bao nhiêu đoạn lên sách mang một phán quyết của MÁY, và thuộc lớp nào?

    python scripts/measure_what_the_machine_let_through.py

Chỉ đọc. `scripts/machine_acceptances.py` trả lời câu ấy cho **một project** và in kèm mốc thời
gian để tua tới. Phép đo này trả lời cho **cả cuốn sách người ta đang nghe**, vì đó là câu hợp với
lệnh của chủ sách: *"tôi không muốn phải tự nghe"* — không phải nghe thì được, **không biết** thì
không. Xem `docs/SHIPPING_WITHOUT_A_LISTENER.md`, ràng buộc thứ ba: *không im lặng*.

Chỉ đếm trong project **THẮNG** của mỗi chương (đọc `manifest.json`), không đếm các bản cũ đã bị
thay — nếu đếm cả thì con số phồng lên gấp đôi mà chẳng nói về cái sách đang phát.

## Kết quả (16:10 ngày 2026-09-16, sách 180 chương)

    14.807 doan tren sach
     3.637 doan mang mot ma canh bao  (24,6%),  rai tren ca 180 chuong

       3.452  ASR_LOCKED_NAME_ANCHOR_MISMATCH     <- 95% cua tat ca canh bao
         120  ASR_TRANSCRIPT_TIMELINE_IMPOSSIBLE
          35  ASR_UNVERIFIABLE_SHORT_TEXT
          27  ASR_MISMATCH_UNRESOLVED             <- lop dang doc that
           2  ASR_TRANSCRIPT_RATE_IMPOSSIBLE
           1  TTS_PACE_BAND_RELAXED

Và hai loại **quyết định** của máy, đếm theo ĐOẠN khác nhau (không phải theo dòng sổ):

    3.481  cho qua   - audio giu nguyen, chi cai chot chuong duoc mo
    3.453  thay thu  - audio tren sach la mot UNG VIEN, vi ban duong ong chon luc dau
                       bi cat giua cau va co mot ban da noi xong

Con số thứ hai lớn (23% số đoạn) và **không phải một lớp lỗi**: đó là cơ chế "bản nói xong thắng
bản bị cắt" đang làm việc ở quy mô cả cuốn. Đừng đọc nó như số đoạn hỏng.

Con số đáng nói với chủ sách không phải 24,6% mà là **27 trên 14.807 (0,18%)**: `LOCKED_NAME_ANCHOR`
là một **bài chính tả** — bản thu đọc tên theo cách đọc đã ghim còn Whisper viết theo chữ, nên phép
so lệch mà audio không sai (đo riêng: bắn trên 21–27% mọi đoạn, tốn ~0 GPU). `TIMELINE_IMPOSSIBLE`
và `UNVERIFIABLE_SHORT_TEXT` là câu quá ngắn để ASR phán. Còn `ASR_MISMATCH_UNRESOLVED` là chỗ
**audio có thể thật sự khác văn bản** và không ai nghe: 27 đoạn, mỗi đoạn có mốc thời gian trong
`machine_acceptances.py` của project tương ứng.
"""
from __future__ import annotations

import json
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

try:
    from scripts.book_paths import BOOK, VERSIONS, describe  # noqa: E402
except ImportError:  # chạy trực tiếp
    from book_paths import BOOK, VERSIONS, describe  # noqa: E402


def say(line: str = "") -> None:
    try:
        print(line, flush=True)
    except UnicodeEncodeError:
        print(line.encode("ascii", "backslashreplace").decode("ascii"), flush=True)


def main() -> int:
    say(describe())
    manifest_path = Path(BOOK) / "manifest.json"
    if not manifest_path.is_file():
        say(f"không có {manifest_path} - chưa ghép sách lần nào")
        return 1
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    rows = manifest.get("chapters", manifest)
    items = list(rows.values()) if isinstance(rows, dict) else list(rows)
    by_project: dict[str, list[str]] = defaultdict(list)
    for item in items:
        by_project[str(item["project"])].append(str(item["title"]))

    say("")
    say(f"{sum(len(v) for v in by_project.values())} chương trên sách, do {len(by_project)} project cấp")

    codes: Counter[str] = Counter()
    decisions: Counter[str] = Counter()
    total = 0
    for project, titles in by_project.items():
        found = list(Path(VERSIONS).glob(f"*/{project}/project.sqlite3"))
        if not found:
            say(f"  KHÔNG thấy project {project} - bỏ qua {len(titles)} chương")
            continue
        connection = sqlite3.connect(f"file:{found[0].as_posix()}?mode=ro", uri=True)
        connection.row_factory = sqlite3.Row
        marks = ",".join("?" for _ in titles)
        try:
            for row in connection.execute(
                "SELECT s.warning_code c, COUNT(*) n FROM segments s "
                f"JOIN chapters ch ON ch.id = s.chapter_id WHERE ch.title IN ({marks}) "
                "GROUP BY s.warning_code",
                titles,
            ):
                total += int(row["n"])
                if row["c"]:
                    codes[str(row["c"])] += int(row["n"])
            # Hai bảng quyết định: lọc theo `stable_id` của đúng các chương THẮNG, nếu không thì
            # đếm cả những chương project này đã bị thay và con số phồng lên vô nghĩa.
            for table, label in (
                ("machine_audio_acceptances", "cho qua (audio giữ nguyên)"),
                ("machine_take_substitutions", "thay bản thu"),
            ):
                # COUNT(DISTINCT ...): sổ có thể có nhiều dòng cho một đoạn, và câu hỏi là
                # "bao nhiêu ĐOẠN trên sách", không phải "bao nhiêu lần ghi sổ". Trên dữ liệu hôm
                # nay hai con số gần bằng nhau (3.482 dòng / 3.481 đoạn), nhưng đừng để nó đúng
                # nhờ may.
                for row in connection.execute(
                    f"SELECT COUNT(DISTINCT t.segment_stable_id) n FROM {table} t JOIN segments s "
                    "ON s.stable_id = t.segment_stable_id "
                    f"JOIN chapters ch ON ch.id = s.chapter_id WHERE ch.title IN ({marks})",
                    titles,
                ):
                    decisions[label] += int(row["n"])
        except sqlite3.Error as exc:
            say(f"  ({project}: {exc})")
        finally:
            connection.close()

    flagged = sum(codes.values())
    say("")
    say(f"{total} đoạn trên sách; {flagged} đoạn mang một mã cảnh báo "
        f"({100 * flagged / max(total, 1):.1f}%)")
    say("")
    for code, count in codes.most_common():
        note = ""
        if code == "ASR_LOCKED_NAME_ANCHOR_MISMATCH":
            note = "   <- bài chính tả, không phải audio sai"
        elif code == "ASR_MISMATCH_UNRESOLVED":
            note = "   <- lớp đáng đọc thật"
        say(f"  {count:>6}  {code}{note}")
    say("")
    for label, count in decisions.most_common():
        say(f"  {count:>6}  {label}")
    say("")
    say("Mốc thời gian từng đoạn: python scripts/machine_acceptances.py <project của chương ấy>")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
