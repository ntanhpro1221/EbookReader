"""Một chương có tự đủ bằng chứng để phán "nhãn này không phải người" hay không?

    python scripts/measure_a_phantom_by_its_own_chapter.py [book2|book1]

Chỉ đọc. Thước: trong **chính chương ấy**, chữ ấy có xuất hiện dạng **viết thường** không, và nó có
bao giờ viết hoa **giữa câu** không.

    viet thuong > 0  VA  hoa giua cau == 0   ->  nghi la phantom

Cột "hoa giữa câu" là thứ bảo vệ tên thật: `của Trang`, `nhìn Lucien` — một cái tên luôn viết hoa ở
giữa câu. Còn một chữ thường bị viết hoa chỉ vì mở đầu câu tường thuật thì không bao giờ.

## Câu hỏi thiết kế mà script này trả lời

`patch_a_pronoun_is_not_a_character` (hàng chờ) chặn phantom bằng một **danh sách từ tiếng Việt**
chép tay (`ATTRIBUTION_SENTENCE_START_EXCLUSIONS` + `giai, im, nghe, tin`). Chủ sách đã dặn: *"nhỡ
sách khác cũng gặp chuyện thế này thì project phải tự xử lý được chứ?"* — và một danh sách chép tay
sẽ trượt ở cuốn thứ ba. `measure_phantom_speakers.py` phán bằng bằng chứng, nhưng nó đọc **cả cuốn**;
tầng phân tích chỉ thấy **một chương**. Nên: thước ấy còn đúng khi chỉ nhìn một chương?

## Kết quả (04:55 ngày 2026-09-16) — và vì sao vẫn KHÔNG vá

Có: một chương tự đủ bằng chứng, và đối chứng **sạch trên cả hai cuốn** (0 trong 292 nhãn một-từ bị
oan; `Lucien` 1.073 câu, `MICHAEL` 1.152 câu, `SAMAEL` 619 câu đều sạch ở **mọi** chương).

    cuon 2  gan co 7 nhan / 191:  Nghe 6 cau, Giai 4, Minh, Tin, Im, Tay, Cho
    cuon 1  gan co 7 nhan / 101:  Toi 70, ME 94 (1/36 chuong), CHA 9, BA 4, ME(MẸ) 3, GÃ 1, TÔI 1

Nhưng **hành động** phải khác nhau theo lớp, và một luật "phantom → UNKNOWN" sẽ làm sai hai lớp:

| lớp | ví dụ | chỗ đúng |
|---|---|---|
| chữ thường bị viết hoa vì mở đầu câu tường thuật | `Nghe`, `Giai`, `Tin`, `Im`, `Tay`, `Cho` | `UNKNOWN` — **không có ai ở đó** |
| đại từ ngôi thứ nhất | `Tôi`, `ME` | nhóm vô danh, hoặc `EBOOK_FIRST_PERSON` |
| xưng hô chỉ một NGƯỜI THẬT chưa có tên | `CHA`, `MẸ`, `BÀ`, `GÃ` | `NPC_LOCAL:` + `GENERIC_SPEAKER_TRAITS` |

Hai lớp dưới đã có đường chữa riêng trong hàng chờ, nên **giá trị thêm** của thước này trên hai cuốn
đang có là **3 câu** (`Tay`, `Cho` ở cuốn 2; `GÃ` ở cuốn 1) — cộng với tính tổng quát cho cuốn sau.
Đổi `analysis.py` (file khoá, họ dàn giọng) lấy 3 câu là không xứng, và gửi `CHA` về `UNKNOWN` còn
**tệ hơn hiện tại** (lời của người cha sẽ do người dẫn chuyện đọc). Nên: giữ thước, không vá — và
nếu một cuốn sau cho con số lớn, đây là công cụ có sẵn để quyết.

## Bản đầu của script này gắn cờ LUCIEN, và đó là phần đáng đọc nhất

Nhãn người nói trong SQLite là dạng **chuẩn hoá HOA** (`LUCIEN`), còn văn bản viết `Lucien`. Bản đầu
đếm "viết thường" bằng số khớp không phân biệt hoa thường **trừ** số khớp đúng-nguyên-dạng `LUCIEN`
— mà `LUCIEN` không có trong văn bản, nên hiệu số bằng **toàn bộ** số lần xuất hiện, và cột "hoa giữa
câu" (cũng so `LUCIEN`) bằng 0. Kết quả: thước gắn cờ nhân vật chính 378 câu, cùng FELIPE, FELICIA,
NATASHA, VICTOR — **67 trên 191 nhãn**.

Trước đó tôi đã thử thước trên 25 nghi can và **25/25 đều đúng**, nên nếu tin con số ấy rồi vá thì đã
biến nhân vật chính thành vô danh. **Đối chứng là thứ duy nhất bắt được nó.** Bản này phân loại từng
lần xuất hiện theo **chính dạng viết của nó trong văn bản**, không so với dạng của nhãn.
"""
from __future__ import annotations

import glob
import re
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

BOOK = sys.argv[1] if len(sys.argv) > 1 else "book2"
VERSIONS = (
    "D:/Novels/Audiobooks/book2/_versions" if BOOK == "book2" else "D:/Novels/Audiobooks/_versions"
)
RESERVED = {"NARRATOR", "UNKNOWN"}
# Ký tự đứng trước một chữ viết hoa MỞ ĐẦU câu (hoặc mở đầu lời tường thuật sau ngoặc kép).
SENTENCE_BOUNDARY = set(".!?…\"'”’«»\n\r\t—–-:;,")


def _say(line: str) -> None:
    try:
        print(line, flush=True)
    except UnicodeEncodeError:
        print(line.encode("ascii", "backslashreplace").decode("ascii"), flush=True)


def classify(word: str, text: str) -> tuple[int, int, int]:
    """(viết thường, viết hoa giữa câu, viết hoa đầu câu) - theo DẠNG VIẾT THẬT trong văn bản."""
    lower = mid = start = 0
    pattern = re.compile(rf"(?<!\w){re.escape(word)}(?!\w)", flags=re.IGNORECASE)
    for match in pattern.finditer(text):
        found = match.group(0)
        if found == found.casefold():
            lower += 1
            continue
        before = text[: match.start()].rstrip(" ")
        if not before or before[-1] in SENTENCE_BOUNDARY:
            start += 1
        else:
            mid += 1
    return lower, mid, start


def main() -> int:
    verdicts: dict[tuple[str, str], tuple[int, int, int]] = {}
    lines_of: dict[str, int] = defaultdict(int)
    for database in sorted(glob.glob(f"{VERSIONS}/*/*/project.sqlite3")):
        connection = sqlite3.connect(f"file:{Path(database).as_posix()}?mode=ro", uri=True)
        connection.row_factory = sqlite3.Row
        try:
            chapters = connection.execute("SELECT id, title FROM chapters ORDER BY title").fetchall()
        except sqlite3.Error:
            connection.close()
            continue
        for chapter in chapters:
            rows = connection.execute(
                "SELECT seq, speaker, text FROM segments WHERE chapter_id = ? ORDER BY seq",
                (int(chapter["id"]),),
            ).fetchall()
            text = "\n".join(str(row["text"] or "") for row in rows)
            for row in rows:
                speaker = str(row["speaker"] or "").strip()
                if (
                    not speaker
                    or speaker.upper() in RESERVED
                    or not re.fullmatch(r"[A-ZÀ-Ỹ][a-zà-ỹA-ZÀ-Ỹ]{1,20}", speaker)
                ):
                    continue
                lines_of[speaker] += 1
                key = (speaker, str(chapter["title"]))
                if key not in verdicts:
                    verdicts[key] = classify(speaker, text)
        connection.close()

    flagged: dict[str, list[str]] = defaultdict(list)
    clean: dict[str, list[str]] = defaultdict(list)
    for (speaker, title), (lower, mid, _start) in verdicts.items():
        (flagged if lower > 0 and mid == 0 else clean)[speaker].append(title)

    _say(f"{BOOK}: {len({s for s, _ in verdicts})} nhãn một-từ, {len(verdicts)} cặp (nhãn, chương)")
    _say("")
    _say(f"THƯỚC GẮN CỜ {len(flagged)} nhãn:")
    for speaker, titles in sorted(flagged.items(), key=lambda kv: -lines_of[kv[0]]):
        _say(
            f"   {speaker:<14} {lines_of[speaker]:>4} câu cả cuốn,"
            f" cờ ở {len(titles)}/{len(titles) + len(clean.get(speaker, []))} chương:"
            f" {', '.join(sorted(titles)[:8])}"
        )
    _say("")
    _say("Mười nhãn NHIỀU CÂU NHẤT mà thước không gắn cờ ở đâu cả (đối chứng):")
    only_clean = [s for s in clean if s not in flagged]
    for speaker in sorted(only_clean, key=lambda s: -lines_of[s])[:10]:
        _say(f"   {speaker:<14} {lines_of[speaker]:>4} câu, sạch ở {len(clean[speaker])} chương")
    return 0


if __name__ == "__main__":
    sys.exit(main())
