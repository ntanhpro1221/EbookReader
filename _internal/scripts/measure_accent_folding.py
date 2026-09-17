"""Nếu phép so ASR gộp thêm các âm mà giọng MIỀN BẮC vốn không phân biệt, bao nhiêu đoạn đổi kết cục?

So bằng `tone_folded_transcript_metrics` - đúng hàm dây chuyền dùng, đã gộp thanh điệu qua âm vị.
Đo bằng `transcript_metrics` trần sẽ phóng đại, vì phép gộp thanh điệu có thể đã cứu sẵn đoạn ấy.

    runtime/.venv/Scripts/python.exe scripts/measure_accent_folding.py [--db <project.sqlite3>]

Chỉ đọc DB của lô và tính lại bằng chính hàm đo của dự án. Không sửa gì, không cần GPU.

Giọng Bắc nhập `tr`≈`ch`, `s`≈`x`, `r`≈`d`≈`gi`: đó là phát âm chuẩn của vùng ấy, không phải lỗi đọc.
Whisper chép theo cái nó nghe, nên "trán" thành "chán" là **cùng một âm**, giống đúng lý lẽ dự án đã
dùng khi gấp `gi`→`d` và `k`→`c`. Câu hỏi: gấp thêm thì cứu được bao nhiêu đoạn, và có làm hai từ
THẬT KHÁC nhau thành giống nhau ở đâu không.
"""
from __future__ import annotations

import re
import sqlite3
import sys
from pathlib import Path

ROOT = Path(r"D:\Novels\Ebook Reader\_internal")
sys.path.insert(0, str(ROOT))

from ebook_reader.asr import (  # noqa: E402
    normalize_transcript,
    tone_folded_transcript_metrics,
    transcript_metrics,
)

DB = sys.argv[sys.argv.index("--db") + 1] if "--db" in sys.argv else (
    "D:/Novels/Audiobooks/book2/_versions/v0.3.0-lo06/lo06_7ba27df135/project.sqlite3")
MIN_SIMILARITY, MAX_WER = 0.78, 0.30
# Cặp âm mà giọng Bắc không phân biệt. Thứ tự quan trọng: `gi`/`tr`/`ch` trước phụ âm đơn.
NORTHERN_FOLDS = (("tr", "ch"), ("gi", "d"), ("r", "d"), ("s", "x"))


def fold_northern(text: str) -> str:
    out = text.lower()
    for source, target in NORTHERN_FOLDS:
        out = re.sub(rf"\b{source}", target, out)
    return out


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    rows = list(con.execute(
        "select c.title, s.stable_id, s.text, s.asr_text, s.status, s.warning_code, s.asr_similarity, s.asr_wer"
        " from segments s join chapters c on c.id = s.chapter_id"
        " where s.asr_text is not null and s.asr_text <> '' and (s.status <> 'verified' or s.asr_similarity < 0.9)"))
    print(f"{len(rows)} doan de xem (chua dat hoac sat nguong)\n")
    flipped, unchanged, worse = [], 0, 0
    for title, stable_id, text, asr, status, code, sim, wer in rows:
        # Phải đo bằng ĐÚNG phép so dây chuyền dùng: `tone_folded_transcript_metrics`, đã gộp
        # thanh điệu qua âm vị sea-g2p. Bản đầu của script này so bằng `transcript_metrics` trần,
        # nên nó đếm cả những đoạn mà phép gộp thanh điệu vốn đã cứu - tức phóng đại lợi ích.
        plain_sim, plain_wer, _ = tone_folded_transcript_metrics(text, asr)
        folded_sim, folded_wer, _ = tone_folded_transcript_metrics(fold_northern(normalize_transcript(text)),
                                                                   fold_northern(normalize_transcript(asr)))
        plain_raw_sim, plain_raw_wer = transcript_metrics(text, asr)
        passed_before = plain_sim >= MIN_SIMILARITY and plain_wer <= MAX_WER
        passed_after = folded_sim >= MIN_SIMILARITY and folded_wer <= MAX_WER
        if passed_after and not passed_before:
            flipped.append((title, stable_id, text, asr, plain_sim, folded_sim, plain_wer, folded_wer, status, code))
        elif passed_before and not passed_after:
            worse += 1
        else:
            unchanged += 1
    print(f"doi tu TRUOT sang QUA: {len(flipped)}   |   tu QUA sang TRUOT: {worse}   |   khong doi: {unchanged}\n")
    for title, stable_id, text, asr, ps, fs, pw, fw, status, code in flipped[:25]:
        print(f"ch {title} {stable_id} [{status}/{code}] sim {ps:.2f}->{fs:.2f} wer {pw:.2f}->{fw:.2f}")
        print(f"   sach   : {text[:100]}")
        print(f"   Whisper: {asr[:100]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
